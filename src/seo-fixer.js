/**
 * SEO Fixer — Automatically repairs common SEO issues detected by the /health audit dashboard.
 *
 * HOW IT WORKS:
 *   Queries D1 for pages/news with SEO problems, fixes them in batches of 500.
 *   Runs every 6 hours via cron (0:30, 6:30, 12:30, 18:30 UTC) and on-demand via /health?fix=1.
 *   Returns a log object with counts of what was fixed.
 *
 * WHAT IT FIXES:
 *   1. Title too long (>60 chars)       → truncate at word boundary, preserve " | gab.ae" suffix
 *   2. Description too long (>160 chars) → truncate at word boundary + "…"
 *   3. Description missing              → extract from first <p> in HTML, or generate from title
 *   4. Description too short (<70 chars) → replace from first <p> in HTML, or generate from title
 *   5. H1 tag missing                   → inject <h1> with page title after seed-page div
 *   6. Multiple H1 tags                 → keep first H1, convert extras to <h2>
 *
 * WHY IT EXISTS:
 *   LLM-generated pages (llm-seed-pages.js, llm-rework.js, llm-news.js) sometimes produce
 *   titles/descriptions that exceed SEO limits despite prompt instructions. The prompts now
 *   include strict length rules AND the pipelines enforce limits in code after LLM output,
 *   but this fixer catches anything that slips through and cleans up legacy content.
 *
 * SEO LIMITS (must match /health audit checks in worker.js healthPage()):
 *   - Title:       ≤ 60 chars total (including " | gab.ae" = 9 chars, so base ≤ 51)
 *   - Description: 70-155 chars (Google truncates ~160, but 155 is safe)
 *   - H1:          Exactly one per page, should match or be close to <title>
 *
 * RELATED FILES:
 *   - worker.js healthPage()     → the /health audit dashboard that shows issues
 *   - llm-seed-pages.js          → seed page generation (prompt has SEO rules + code enforcement)
 *   - llm-rework.js              → page upgrade pipeline (same constraints)
 *   - llm-news.js                → news generation (same constraints)
 *   - link-scanner.js            → separate system for broken internal links
 */

const MAX_TITLE = 60;
const MAX_DESC = 155;
const MIN_DESC = 70;
const BATCH_SIZE = 500;

function truncateAtWord(str, max, suffix = '…') {
  if (str.length <= max) return str;
  const cut = str.slice(0, max - suffix.length);
  const lastSpace = cut.lastIndexOf(' ');
  return (lastSpace > max * 0.4 ? cut.slice(0, lastSpace) : cut) + suffix;
}

function stripTags(html) {
  return (html || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function extractFirstParagraph(html) {
  const match = html.match(/<p[^>]*>([\s\S]*?)<\/p>/i);
  return match ? stripTags(match[1]) : '';
}

export async function fixSeoIssues(env) {
  const log = { titleFixed: 0, descFixed: 0, h1Fixed: 0, multiH1Fixed: 0, total: 0 };

  // ── 1. Fix titles too long (pages) ──
  const longTitles = await env.DB.prepare(
    `SELECT slug, title FROM pages WHERE status='live' AND length(title) > ? LIMIT ?`
  ).bind(MAX_TITLE, BATCH_SIZE).all();

  for (const row of longTitles?.results ?? []) {
    // Remove " | gab.ae" suffix, truncate, re-add
    let base = row.title.replace(/\s*\|\s*gab\.ae$/i, '');
    const suffix = ' | gab.ae';
    const maxBase = MAX_TITLE - suffix.length;
    if (base.length > maxBase) {
      base = truncateAtWord(base, maxBase);
    }
    const newTitle = base + suffix;
    if (newTitle !== row.title) {
      await env.DB.prepare("UPDATE pages SET title = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(newTitle, row.slug).run();
      log.titleFixed++;
    }
  }

  // ── 1b. Fix titles too long (news) ──
  const longNewsTitles = await env.DB.prepare(
    `SELECT slug, title FROM news WHERE status='live' AND length(title) > ? LIMIT ?`
  ).bind(MAX_TITLE, BATCH_SIZE).all();

  for (const row of longNewsTitles?.results ?? []) {
    const newTitle = truncateAtWord(row.title, MAX_TITLE);
    if (newTitle !== row.title) {
      await env.DB.prepare("UPDATE news SET title = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(newTitle, row.slug).run();
      log.titleFixed++;
    }
  }

  // ── 2. Fix descriptions too long (pages) ──
  const longDescs = await env.DB.prepare(
    `SELECT slug, description FROM pages WHERE status='live' AND length(description) > ? LIMIT ?`
  ).bind(MAX_DESC + 5, BATCH_SIZE).all(); // +5 buffer for the ellipsis that's already there

  for (const row of longDescs?.results ?? []) {
    const newDesc = truncateAtWord(row.description, MAX_DESC);
    if (newDesc !== row.description) {
      await env.DB.prepare("UPDATE pages SET description = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(newDesc, row.slug).run();
      log.descFixed++;
    }
  }

  // ── 2b. Fix descriptions too long (news) ──
  const longNewsDescs = await env.DB.prepare(
    `SELECT slug, description FROM news WHERE status='live' AND length(description) > ? LIMIT ?`
  ).bind(MAX_DESC + 5, BATCH_SIZE).all();

  for (const row of longNewsDescs?.results ?? []) {
    const newDesc = truncateAtWord(row.description, MAX_DESC);
    if (newDesc !== row.description) {
      await env.DB.prepare("UPDATE news SET description = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(newDesc, row.slug).run();
      log.descFixed++;
    }
  }

  // ── 3. Fix descriptions missing (pages) ──
  const missingDescs = await env.DB.prepare(
    `SELECT slug, title, html FROM pages WHERE status='live' AND (description IS NULL OR description='') LIMIT ?`
  ).bind(BATCH_SIZE).all();

  for (const row of missingDescs?.results ?? []) {
    const firstP = extractFirstParagraph(row.html || '');
    let desc = firstP.length >= MIN_DESC
      ? truncateAtWord(firstP, MAX_DESC)
      : '';
    if (!desc) {
      // Fallback: use title + keyword-style description
      const baseTitle = (row.title || '').replace(/\s*\|\s*gab\.ae$/i, '');
      desc = truncateAtWord(`${baseTitle}. Expert guide with practical tips, key insights, and answers to common questions.`, MAX_DESC);
    }
    if (desc.length >= MIN_DESC) {
      await env.DB.prepare("UPDATE pages SET description = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(desc, row.slug).run();
      log.descFixed++;
    }
  }

  // ── 3b. Fix descriptions missing (news) ──
  const missingNewsDescs = await env.DB.prepare(
    `SELECT slug, title, lede FROM news WHERE status='live' AND (description IS NULL OR description='') LIMIT ?`
  ).bind(BATCH_SIZE).all();

  for (const row of missingNewsDescs?.results ?? []) {
    const lede = (row.lede || '').trim();
    let desc = lede.length >= MIN_DESC ? truncateAtWord(lede, MAX_DESC) : '';
    if (!desc) {
      desc = truncateAtWord(`${row.title}. Latest news and analysis on this developing story.`, MAX_DESC);
    }
    if (desc.length >= MIN_DESC) {
      await env.DB.prepare("UPDATE news SET description = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(desc, row.slug).run();
      log.descFixed++;
    }
  }

  // ── 4. Fix descriptions too short (pages) — extend from HTML or title ──
  const shortDescs = await env.DB.prepare(
    `SELECT slug, title, description, html FROM pages WHERE status='live' AND length(description) > 0 AND length(description) < ? LIMIT ?`
  ).bind(MIN_DESC, BATCH_SIZE).all();

  for (const row of shortDescs?.results ?? []) {
    let newDesc = '';
    const firstP = extractFirstParagraph(row.html || '');
    if (firstP.length >= MIN_DESC) {
      newDesc = truncateAtWord(firstP, MAX_DESC);
    }
    if (!newDesc || newDesc.length < MIN_DESC) {
      // Fallback: build from title
      const baseTitle = (row.title || row.slug).replace(/\s*\|\s*gab\.ae$/i, '');
      newDesc = truncateAtWord(
        `${baseTitle}. Comprehensive guide with expert insights, practical tips, detailed analysis, and frequently asked questions.`,
        MAX_DESC
      );
    }
    if (newDesc.length >= MIN_DESC && newDesc !== row.description) {
      await env.DB.prepare("UPDATE pages SET description = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(newDesc, row.slug).run();
      log.descFixed++;
    }
  }

  // ── 5. Fix H1 missing — inject into HTML ──
  const noH1 = await env.DB.prepare(
    `SELECT slug, title, html FROM pages WHERE status='live' AND html IS NOT NULL AND html != '' AND lower(html) NOT LIKE '%<h1%' LIMIT ?`
  ).bind(BATCH_SIZE).all();

  for (const row of noH1?.results ?? []) {
    const baseTitle = (row.title || row.slug).replace(/\s*\|\s*gab\.ae$/i, '');
    // Insert <h1> after the opening seed-page div
    let html = row.html;
    const insertPoint = html.indexOf('class="seed-page"');
    if (insertPoint > -1) {
      const afterTag = html.indexOf('>', insertPoint);
      if (afterTag > -1) {
        html = html.slice(0, afterTag + 1) + `\n<h1>${baseTitle}</h1>` + html.slice(afterTag + 1);
      }
    } else {
      // No seed-page div — prepend h1
      html = `<h1>${baseTitle}</h1>\n` + html;
    }
    await env.DB.prepare("UPDATE pages SET html = ?, updated_at = datetime('now') WHERE slug = ?")
      .bind(html, row.slug).run();
    log.h1Fixed++;
  }

  // ── 6. Fix multiple H1 tags — convert extras to <h2> ──
  const multiH1 = await env.DB.prepare(
    `SELECT slug, html FROM pages WHERE status='live' AND html IS NOT NULL
     AND (length(html) - length(replace(lower(html), '<h1', ''))) / 3 > 1 LIMIT ?`
  ).bind(BATCH_SIZE).all();

  for (const row of multiH1?.results ?? []) {
    let html = row.html;
    let count = 0;
    // Replace all <h1 with tracking — keep first, convert rest to <h2
    html = html.replace(/<h1(\s|>)/gi, (match, after) => {
      count++;
      if (count === 1) return match; // keep first
      return '<h2' + after;
    });
    html = html.replace(/<\/h1>/gi, () => {
      // We need to track which closings correspond to which openings
      // Simpler approach: replace from the end
      return '</h2>';
    });
    // Fix: the first </h1> should stay, rest become </h2>
    // Re-do more carefully
    let h1Count = 0;
    html = row.html.replace(/<h1([\s>])/gi, (m, after) => {
      h1Count++;
      return h1Count === 1 ? m : '<h2' + after;
    });
    let closeCount = 0;
    html = html.replace(/<\/h1>/gi, () => {
      closeCount++;
      return closeCount === 1 ? '</h1>' : '</h2>';
    });

    if (html !== row.html) {
      await env.DB.prepare("UPDATE pages SET html = ?, updated_at = datetime('now') WHERE slug = ?")
        .bind(html, row.slug).run();
      log.multiH1Fixed++;
    }
  }

  log.total = log.titleFixed + log.descFixed + log.h1Fixed + log.multiH1Fixed;
  console.log(`🔧 SEO Fixer: ${log.total} fixes (${log.titleFixed} titles, ${log.descFixed} descriptions, ${log.h1Fixed} H1s, ${log.multiH1Fixed} multi-H1s)`);
  return log;
}
