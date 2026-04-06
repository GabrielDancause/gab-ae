#!/usr/bin/env node
/**
 * Test script for the internal-link sanitizer.
 * Run with: node scripts/test-sanitize-links.mjs
 *
 * Tests that:
 *  - Allowed internal links remain intact.
 *  - Hallucinated (non-existent) internal links are unwrapped.
 *  - External links are left alone.
 *  - Always-allowed links (apex guide) are kept regardless of D1 presence.
 *  - The JSON-LD <script> block is not affected.
 *  - Edge cases (attributes, single quotes, rich inner HTML, root href) work.
 *  - sanitizeHtmlLinks correctly delegates to the D1 stub.
 */

import { sanitizeInternalLinks, extractInternalSlugs, sanitizeHtmlLinks } from '../src/utils/sanitize-internal-links.js';

let passed = 0;
let failed = 0;

function assert(description, actual, expected) {
  if (actual === expected) {
    console.log(`  ✅ ${description}`);
    passed++;
  } else {
    console.error(`  ❌ ${description}`);
    console.error(`     Expected : ${expected}`);
    console.error(`     Actual   : ${actual}`);
    failed++;
  }
}

const ALLOWED = new Set(['real-page', 'another-real-page', 'category/finance']);
const APEX    = ['apex-guide-2026'];

// ─── sanitizeInternalLinks ─────────────────────────────────────────────────

console.log('\n── sanitizeInternalLinks ──');

// 1. Allowed internal link (double-quoted href)
assert(
  'Allowed internal link remains',
  sanitizeInternalLinks('<a href="/real-page">Real Page</a>', ALLOWED, APEX),
  '<a href="/real-page">Real Page</a>'
);

// 2. Hallucinated internal link is unwrapped (text preserved)
assert(
  'Hallucinated link is unwrapped — text preserved',
  sanitizeInternalLinks('<a href="/fake-hallucinated-slug">Fake Page</a>', ALLOWED, APEX),
  'Fake Page'
);

// 3. External link is left alone
assert(
  'External link remains untouched',
  sanitizeInternalLinks('<a href="https://example.com/anything">External</a>', ALLOWED, APEX),
  '<a href="https://example.com/anything">External</a>'
);

// 4. Always-allowed (apex guide) is kept even if not in allowedSlugs
assert(
  'Always-allowed apex link remains',
  sanitizeInternalLinks('<a href="/apex-guide-2026">Apex Guide</a>', ALLOWED, APEX),
  '<a href="/apex-guide-2026">Apex Guide</a>'
);

// 5. https://gab.ae/ prefix treated as internal — allowed
assert(
  'https://gab.ae/ allowed slug remains',
  sanitizeInternalLinks('<a href="https://gab.ae/real-page">Real Page</a>', ALLOWED, APEX),
  '<a href="https://gab.ae/real-page">Real Page</a>'
);

// 6. https://gab.ae/ prefix treated as internal — hallucinated is unwrapped
assert(
  'https://gab.ae/ hallucinated slug is unwrapped',
  sanitizeInternalLinks('<a href="https://gab.ae/nonexistent">Ghost</a>', ALLOWED, APEX),
  'Ghost'
);

// 7. Single-quoted href
assert(
  'Single-quoted href is handled',
  sanitizeInternalLinks("<a href='/real-page'>Real Page</a>", ALLOWED, APEX),
  "<a href='/real-page'>Real Page</a>"
);

// 8. Hallucinated link with extra attributes
assert(
  'Hallucinated link with extra attributes is unwrapped',
  sanitizeInternalLinks('<a class="foo" href="/ghost-page" target="_blank">Ghost</a>', ALLOWED, APEX),
  'Ghost'
);

// 9. Allowed link with extra attributes retained as-is
assert(
  'Allowed link with extra attributes stays intact',
  sanitizeInternalLinks('<a style="color:#818cf8" href="/real-page">Real</a>', ALLOWED, APEX),
  '<a style="color:#818cf8" href="/real-page">Real</a>'
);

// 10. Rich inner HTML is preserved when unwrapping
assert(
  'Inner HTML is preserved when unwrapping',
  sanitizeInternalLinks('<a href="/ghost"><strong>Bold Ghost</strong></a>', ALLOWED, APEX),
  '<strong>Bold Ghost</strong>'
);

// 11. Root href "/" is kept (empty slug)
assert(
  'Root href "/" is always kept',
  sanitizeInternalLinks('<a href="/">Home</a>', ALLOWED, APEX),
  '<a href="/">Home</a>'
);

// 12. Fragment-only href is left alone (not internal path)
assert(
  'Fragment-only href is left alone',
  sanitizeInternalLinks('<a href="#section">Section</a>', ALLOWED, APEX),
  '<a href="#section">Section</a>'
);

// 13. Mixed HTML: allowed, hallucinated, and external in the same string
{
  const input  = '<p>See <a href="/real-page">this</a> and <a href="/ghost">that</a> and <a href="https://ext.com">ext</a>.</p>';
  const output = '<p>See <a href="/real-page">this</a> and that and <a href="https://ext.com">ext</a>.</p>';
  assert('Mixed HTML: allowed + hallucinated + external', sanitizeInternalLinks(input, ALLOWED, APEX), output);
}

// 14. JSON-LD script tag is not affected
{
  const jsonLd = '<script type="application/ld+json">{"@context":"https://schema.org","url":"https://gab.ae/ghost"}</script>\n';
  const body   = '<a href="/ghost">Ghost</a>';
  const result = sanitizeInternalLinks(jsonLd + body, ALLOWED, APEX);
  assert('JSON-LD script block is not modified', result, jsonLd + 'Ghost');
}

// ─── extractInternalSlugs ──────────────────────────────────────────────────

console.log('\n── extractInternalSlugs ──');

{
  const html = '<a href="/slug-a">A</a> <a href="https://gab.ae/slug-b">B</a> <a href="https://example.com/c">C</a>';
  const slugs = extractInternalSlugs(html);
  assert('Extracts internal slugs only', JSON.stringify(slugs.sort()), JSON.stringify(['slug-a', 'slug-b'].sort()));
}

{
  const html = '<a href="/slug-a">A</a> <a href="/slug-a">A again</a>';
  const slugs = extractInternalSlugs(html);
  assert('Deduplicates slugs', JSON.stringify(slugs), JSON.stringify(['slug-a']));
}

{
  const slugs = extractInternalSlugs('<p>No links here</p>');
  assert('Empty result when no links', JSON.stringify(slugs), '[]');
}

// ─── sanitizeHtmlLinks (with D1 stub) ─────────────────────────────────────

console.log('\n── sanitizeHtmlLinks ──');

// Minimal D1 stub that answers the IN (...) query from an in-memory set
function makeDb(liveSlugs) {
  return {
    prepare(sql) {
      return {
        bind(...args) {
          return {
            async all() {
              const results = args.filter(s => liveSlugs.has(s)).map(s => ({ slug: s }));
              return { results };
            },
          };
        },
      };
    },
  };
}

{
  const db = makeDb(new Set(['live-page']));
  const input  = '<a href="/live-page">Live</a> <a href="/ghost-page">Ghost</a>';
  const result = await sanitizeHtmlLinks(input, db);
  assert('sanitizeHtmlLinks keeps live, unwraps ghost', result, '<a href="/live-page">Live</a> Ghost');
}

{
  const db = makeDb(new Set());
  const input  = '<a href="/apex-slug">Apex</a>';
  const result = await sanitizeHtmlLinks(input, db, ['apex-slug']);
  assert('sanitizeHtmlLinks respects alwaysAllow', result, '<a href="/apex-slug">Apex</a>');
}

{
  // DB error → return html unchanged (fail-open)
  const brokenDb = {
    prepare() {
      return {
        bind() {
          return {
            all() { return Promise.reject(new Error('DB down')); },
          };
        },
      };
    },
  };
  const input  = '<a href="/ghost">Ghost</a>';
  const result = await sanitizeHtmlLinks(input, brokenDb);
  assert('sanitizeHtmlLinks is fail-open on DB error', result, input);
}

// ─── Summary ──────────────────────────────────────────────────────────────

console.log(`\n${passed + failed} tests — ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
