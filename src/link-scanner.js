/**
 * Link Scanner — scans all live pages for broken internal links and auto-fixes them.
 *
 * Run from scheduled() at the top of every hour.
 *
 * Algorithm:
 *   1. Build a Set of all known live slugs (pages + news)
 *   2. Load all live page HTML in batches of 100
 *   3. For each page, extract all internal href values via regex
 *   4. Check each against the slug Set
 *   5. For broken hrefs: score against all known slugs by shared words
 *      - score >= 2: auto-fix (update HTML in D1, mark fixed)
 *      - score < 2: mark unfixable
 *   6. Upsert into broken_links (skip already-fixed rows)
 *   7. Insert a row into link_scan_log with summary counts
 */

const BATCH_SIZE = 100;

/**
 * Score how well a broken href matches a candidate slug.
 * Splits both into words and counts shared tokens (length > 2).
 */
function scoreMatch(brokenHref, candidateSlug) {
  const toWords = s => s.replace(/^\//, '').split(/[-_/]+/).filter(w => w.length > 2);
  const brokenWords = new Set(toWords(brokenHref));
  const candidateWords = toWords(candidateSlug);
  let score = 0;
  for (const w of candidateWords) {
    if (brokenWords.has(w)) score++;
  }
  return score;
}

/**
 * Find the best-matching slug for a broken href.
 * Returns { slug, score } or null if nothing scores >= 2.
 */
function findBestMatch(brokenHref, slugsArray) {
  let best = null;
  let bestScore = 0;
  for (const slug of slugsArray) {
    const s = scoreMatch(brokenHref, slug);
    if (s > bestScore) {
      bestScore = s;
      best = slug;
    }
  }
  if (bestScore >= 2) return { slug: best, score: bestScore };
  return null;
}

/**
 * Extract all internal href values from an HTML string.
 * Internal = starts with / and is not #, mailto:, http, //.
 * Strips query strings and hash fragments.
 */
function extractInternalHrefs(html) {
  const hrefs = new Set();
  const re = /href="([^"]+)"/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    const raw = m[1];
    if (!raw.startsWith('/')) continue;
    if (raw.startsWith('//')) continue;
    if (raw.startsWith('/#')) continue;
    // Strip query + hash
    const clean = raw.split('?')[0].split('#')[0];
    if (clean === '/') continue; // homepage — always valid
    hrefs.add(clean);
  }
  return hrefs;
}

export async function scanAndFixLinks(env) {
  // ── 1. Build known-slugs Set ──────────────────────────────────────────────
  const [pagesResult, newsResult] = await Promise.all([
    env.DB.prepare("SELECT slug FROM pages WHERE status='live'").all(),
    env.DB.prepare("SELECT slug FROM news WHERE status='live'").all(),
  ]);

  const knownSlugs = new Set();
  for (const r of (pagesResult.results || [])) knownSlugs.add('/' + r.slug);
  for (const r of (newsResult.results || [])) knownSlugs.add('/news/' + r.slug);

  const slugsArray = Array.from(knownSlugs);

  // ── 2. Load all live pages in batches ─────────────────────────────────────
  let offset = 0;
  let totalLinks = 0;
  let brokenFound = 0;
  let autoFixed = 0;
  let unfixable = 0;

  // Collect all broken links first, then batch-upsert
  const toUpsert = []; // { sourceSlug, brokenHref, suggestedSlug, status, fixedHtml? }

  while (true) {
    const { results: pages } = await env.DB.prepare(
      "SELECT slug, html FROM pages WHERE status='live' LIMIT ? OFFSET ?"
    ).bind(BATCH_SIZE, offset).all();

    if (!pages || pages.length === 0) break;
    offset += pages.length;

    for (const page of pages) {
      if (!page.html) continue;
      const hrefs = extractInternalHrefs(page.html);
      totalLinks += hrefs.size;

      const broken = [];
      for (const href of hrefs) {
        if (!knownSlugs.has(href)) broken.push(href);
      }

      if (broken.length === 0) continue;

      brokenFound += broken.length;
      let updatedHtml = page.html;
      let pageNeedsUpdate = false;

      for (const href of broken) {
        // Skip if already recorded as fixed or unfixable
        const existing = await env.DB.prepare(
          "SELECT id, status FROM broken_links WHERE source_slug=? AND broken_href=?"
        ).bind(page.slug, href).first();

        if (existing && (existing.status === 'fixed' || existing.status === 'unfixable')) {
          continue;
        }

        const match = findBestMatch(href, slugsArray);

        if (match) {
          autoFixed++;
          // Replace all occurrences of the broken href in HTML
          updatedHtml = updatedHtml.split(`href="${href}"`).join(`href="${match.slug}"`);
          pageNeedsUpdate = true;
          toUpsert.push({
            sourceSlug: page.slug,
            brokenHref: href,
            suggestedSlug: match.slug,
            status: 'fixed',
            existingId: existing?.id ?? null,
          });
        } else {
          unfixable++;
          toUpsert.push({
            sourceSlug: page.slug,
            brokenHref: href,
            suggestedSlug: null,
            status: 'unfixable',
            existingId: existing?.id ?? null,
          });
        }
      }

      if (pageNeedsUpdate) {
        await env.DB.prepare(
          "UPDATE pages SET html=?, updated_at=datetime('now') WHERE slug=?"
        ).bind(updatedHtml, page.slug).run();
      }
    }

    if (pages.length < BATCH_SIZE) break;
  }

  // ── 3. Upsert broken_links rows ───────────────────────────────────────────
  for (const row of toUpsert) {
    if (row.existingId) {
      // Update existing pending row
      if (row.status === 'fixed') {
        await env.DB.prepare(
          "UPDATE broken_links SET suggested_slug=?, status='fixed', fixed_at=datetime('now') WHERE id=?"
        ).bind(row.suggestedSlug, row.existingId).run();
      } else {
        await env.DB.prepare(
          "UPDATE broken_links SET status='unfixable' WHERE id=?"
        ).bind(row.existingId).run();
      }
    } else {
      await env.DB.prepare(
        "INSERT INTO broken_links (source_slug, broken_href, suggested_slug, status, fixed_at) VALUES (?,?,?,?,?)"
      ).bind(
        row.sourceSlug,
        row.brokenHref,
        row.suggestedSlug,
        row.status,
        row.status === 'fixed' ? new Date().toISOString().slice(0, 19).replace('T', ' ') : null
      ).run();
    }
  }

  // ── 4. Insert scan log row ────────────────────────────────────────────────
  await env.DB.prepare(
    "INSERT INTO link_scan_log (total_links, broken_found, auto_fixed, unfixable) VALUES (?,?,?,?)"
  ).bind(totalLinks, brokenFound, autoFixed, unfixable).run();

  console.log(`🔗 Link scan complete: ${totalLinks} links, ${brokenFound} broken, ${autoFixed} fixed, ${unfixable} unfixable`);

  return { totalLinks, brokenFound, autoFixed, unfixable };
}
