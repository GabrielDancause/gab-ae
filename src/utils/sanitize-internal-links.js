/**
 * sanitize-internal-links.js
 *
 * Strips hallucinated internal links from LLM-generated HTML.
 *
 * Rules:
 *  - External links (href not starting with "/" or "https://gab.ae/") are left alone.
 *  - Internal links whose slug is in `allowedSlugs` (live D1 pages) or in
 *    `alwaysAllow` (e.g. the apex guide slug) are kept as-is.
 *  - All other internal links are *unwrapped*: the <a>...</a> wrapper is removed
 *    but the inner HTML text content is preserved.
 *
 * Designed to be robust to arbitrary attribute ordering and single/double quotes.
 */

const GAB_AE_PREFIX = /^https?:\/\/gab\.ae\//i;

/**
 * Extract the slug from an internal href.
 * Returns null for external hrefs.
 *
 * @param {string} href
 * @returns {string|null}
 */
function hrefToSlug(href) {
  if (href.startsWith('/')) {
    // Strip leading slash, query string, and fragment
    return href.slice(1).split(/[?#]/)[0];
  }
  if (GAB_AE_PREFIX.test(href)) {
    return href.replace(GAB_AE_PREFIX, '').split(/[?#]/)[0];
  }
  return null; // external
}

/**
 * Extract all internal slugs referenced by <a href> attributes in `html`.
 * Useful for building a single bulk D1 IN (...) query.
 *
 * @param {string} html
 * @returns {string[]} deduplicated array of slugs
 */
export function extractInternalSlugs(html) {
  const slugs = new Set();
  // Match opening <a> tags and capture the href value (single or double quoted)
  const re = /<a\s[^>]*?\bhref=(["'])([^"']*)\1[^>]*>/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    const slug = hrefToSlug(m[2]);
    if (slug) slugs.add(slug);
  }
  return [...slugs];
}

/**
 * Sanitize internal links in LLM-generated HTML.
 *
 * @param {string} html            - Raw HTML to sanitize
 * @param {Set<string>} allowedSlugs - Set of slugs that exist as live pages in D1
 * @param {string[]} alwaysAllow   - Slugs to always allow (e.g. apex guide slug)
 * @returns {string}               - Sanitized HTML
 */
export function sanitizeInternalLinks(html, allowedSlugs, alwaysAllow = []) {
  // Match full <a ...>...</a> blocks (anchors cannot be nested in valid HTML)
  return html.replace(/<a(\s[^>]*)>([\s\S]*?)<\/a>/gi, (match, attrs, innerHtml) => {
    // Extract href value — only handle quoted hrefs (single or double) since
    // LLM-generated HTML always quotes attribute values.
    const hrefMatch = attrs.match(/\bhref=(["'])([^"']*)\1/i);
    if (!hrefMatch) return match; // no href attribute — leave as-is

    const href = hrefMatch[2];
    const slug = hrefToSlug(href);

    if (slug === null) return match; // external link — leave alone

    // Empty slug means href="/" (root) — always keep
    if (slug === '') return match;

    // Always-allowed list (apex guide, etc.)
    if (alwaysAllow.includes(slug)) return match;

    // Live page in D1 — keep
    if (allowedSlugs.has(slug)) return match;

    // Hallucinated / non-existent internal link — unwrap, keep inner HTML
    return innerHtml;
  });
}

/**
 * Convenience wrapper: query D1 for live slugs, then sanitize internal links.
 * Performs a single IN (...) query covering all internal hrefs found in `html`.
 * On DB error the HTML is returned unchanged (fail-open).
 *
 * @param {string}   html        - Raw HTML to sanitize
 * @param {object}   db          - Cloudflare D1 database binding
 * @param {string[]} alwaysAllow - Slugs to always allow (e.g. apex guide slug)
 * @returns {Promise<string>}    - Sanitized HTML
 */
export async function sanitizeHtmlLinks(html, db, alwaysAllow = []) {
  const internalSlugs = extractInternalSlugs(html);
  let allowedSlugSet = new Set();
  if (internalSlugs.length > 0) {
    try {
      const placeholders = internalSlugs.map(() => '?').join(',');
      const slugRows = await db.prepare(
        `SELECT slug FROM pages WHERE status = 'live' AND slug IN (${placeholders})`
      ).bind(...internalSlugs).all();
      allowedSlugSet = new Set((slugRows?.results || []).map(r => r.slug));
    } catch (e) {
      console.log(`⚠️ Link sanitization query failed: ${e.message}`);
      return html; // fail-open: don't drop content on DB error
    }
  }
  return sanitizeInternalLinks(html, allowedSlugSet, alwaysAllow);
}
