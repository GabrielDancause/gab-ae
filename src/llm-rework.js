/**
 * LLM Rework — Upgrades existing pages with a better model
 * 
 * HOW IT WORKS:
 * 1. Queries view_counts to find the highest-traffic page still at "llm" quality
 * 2. Fetches the page's current HTML from D1
 * 3. Gathers related pages (for internal linking) and related keywords (for FAQ)
 * 4. Sends the page to Gemini Pro via OpenRouter with instructions to rewrite it
 * 5. Validates the output (must be longer, must contain seed-page class)
 * 6. Updates the page in-place, setting quality='llm-sonnet' and engine='llm-sonnet'
 * 
 * SCHEDULE: Runs daily at 4 AM UTC (11 AM Bangkok) via worker.js cron
 * RATE: 1 page per run
 * 
 * ELIGIBLE PAGES: status='live', quality='llm', engine IN (llm-haiku, llm-gemini, 
 * llm-gemini-pro, seed), views_total > 0
 * 
 * Uses callLLM() from llm-client.js for the API call.
 */

import { callLLM } from './llm-client.js';

export async function llmRework(env) {
  const apiKey = env.OPENROUTER_API_KEY || env.ANTHROPIC_API_KEY;
  if (!apiKey) { console.log('❌ Rework: No OPENROUTER_API_KEY or ANTHROPIC_API_KEY'); return; }

  // 1. Find the top-traffic page that hasn't been reworked yet
  //    Join view_counts with pages, pick highest views_total, quality still 'llm'
  // First find the candidate (without html to avoid size issues)
  let candidate;
  try {
    // Debug: check if tables are accessible
    const testCount = await env.DB.prepare("SELECT COUNT(*) as c FROM view_counts WHERE views_total > 0").first();
    console.log(`🔍 Rework: ${testCount?.c || 0} pages with views`);
    candidate = await env.DB.prepare(
      `SELECT p.slug, p.title, p.keyword, p.category, p.page_type, p.description,
              vc.views_24h, vc.views_total
       FROM view_counts vc
       JOIN pages p ON vc.slug = p.slug
       WHERE p.status = 'live'
         AND p.quality = 'llm'
         AND p.engine IN ('llm-haiku','llm-gemini','llm-gemini-pro','seed')
         AND vc.views_total > 0
       ORDER BY vc.views_total DESC
       LIMIT 1`
    ).first();
  } catch (e) {
    console.log(`❌ Rework query error: ${e.message}`);
    return;
  }

  console.log(`🔍 Rework candidate: ${candidate ? candidate.slug : 'null'}`);
  if (!candidate) {
    console.log('✅ Rework: No pages need upgrading');
    return;
  }

  // Now fetch the html separately
  let page;
  try {
    page = await env.DB.prepare("SELECT html FROM pages WHERE slug = ?").bind(candidate.slug).first();
    page = { ...candidate, html: page?.html || '' };
  } catch (e) {
    console.log(`❌ Rework html fetch error: ${e.message}`);
    return;
  }

  console.log(`🔄 Reworking: "${page.slug}" (${page.views_total} total views, ${page.views_24h} today)`);

  // 2. Get related pages for internal linking
  let relatedPages = [];
  try {
    const relResult = await env.DB.prepare(
      `SELECT slug, title FROM pages 
       WHERE category = ? AND status = 'live' AND slug != ?
       ORDER BY published_at DESC LIMIT 5`
    ).bind(page.category || 'general', page.slug).all();
    relatedPages = relResult?.results || [];
  } catch (e) { /* ignore */ }

  if (relatedPages.length < 3) {
    try {
      const existingSlugs = relatedPages.map(p => p.slug);
      const fillResult = await env.DB.prepare(
        `SELECT slug, title FROM pages 
         WHERE status = 'live' AND slug != ?
         ORDER BY published_at DESC LIMIT 5`
      ).bind(page.slug).all();
      const fill = (fillResult?.results || []).filter(p => !existingSlugs.includes(p.slug));
      relatedPages = [...relatedPages, ...fill].slice(0, 5);
    } catch (e) { /* ignore */ }
  }

  const relatedLinksSection = relatedPages.length > 0
    ? `\n\nINTERNAL LINKS — Weave these naturally into your content and include a "Related Resources" section at the bottom:\n${relatedPages.map(p => `- <a href="/${p.slug}">${(p.title || '').replace(' | gab.ae', '')}</a>`).join('\n')}`
    : '';

  // 3. Mine related keywords for FAQ
  let relatedKeywords = [];
  if (page.keyword) {
    try {
      const coreWords = page.keyword.toLowerCase().split(/\s+/).filter(w => w.length > 3 && !['what','how','best','does','with','from','that','this','have','will','your','about','which','where','when'].includes(w));
      if (coreWords.length > 0) {
        const rkResult = await env.DB.prepare(
          `SELECT keyword, volume FROM keywords 
           WHERE keyword LIKE '%' || ? || '%' 
             AND keyword != ?
             AND volume >= 20
           ORDER BY volume DESC 
           LIMIT 5`
        ).bind(coreWords[0], page.keyword).all();
        relatedKeywords = rkResult?.results || [];
      }
    } catch (e) { /* ignore */ }
  }

  const relatedKeywordsPrompt = relatedKeywords.length > 0
    ? `\n\nFAQ KEYWORDS — Include these as exact questions in your FAQ section (real people search for these):\n${relatedKeywords.map(rk => `- "${rk.keyword}" (${rk.volume} monthly searches)`).join('\n')}`
    : '';

  // 4. Build the rework prompt — give Sonnet the existing HTML to improve
  const currentDate = new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  
  const pageType = page.page_type || 'educational';
  const jsAllowed = pageType === 'interactive_tool' || /\b(timer|stopwatch|countdown|generator|picker|converter|counter|checker|tester|builder|maker|encoder|decoder|formatter|validator|sorter)\b/.test((page.keyword || '').toLowerCase());

  const prompt = `You are rewriting an existing page on gab.ae to BEAT the top 5 Google results for this keyword. This page gets real traffic (${page.views_total} views), so quality matters.

Think about what currently ranks for "${page.keyword || page.slug}" — thin content, ads, missing subtopics, poor UX. Your rewrite must be more useful, more complete, and more engaging than anything on page 1.

CURRENT PAGE KEYWORD: "${page.keyword || page.slug}"
CURRENT PAGE TYPE: ${pageType}
CATEGORY: ${page.category || 'general'}

The current page is ${(page.html || '').length} characters long. DO NOT just reword it — create something dramatically better from scratch:

- Deeper analysis, more specific insights, better structure
- More authoritative tone — write like a recognized expert in this field
- Add concrete examples, case studies, or real-world applications
- Use visual components where appropriate (stat cards, takeaway boxes, pros/cons)
- Ensure all claims use qualified language ("approximately", "typically", ranges)
- NEVER invent study names, researcher names, or specific citations
- Keep the same keyword focus but make the content dramatically more useful

Return ONLY raw HTML (no markdown fences). Use these CSS classes:

<style>
.seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #e2e8f0; }
.seed-page h1 { font-size: 1.75rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; line-height: 1.2; }
.seed-meta { font-size: 0.8rem; color: #64748b; margin-bottom: 2rem; }
.seed-section { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.seed-section h2 { font-size: 1.15rem; font-weight: 700; color: #818cf8; margin-bottom: 0.75rem; }
.seed-section h3 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem; }
.seed-section p { font-size: 0.95rem; line-height: 1.7; color: #94a3b8; margin-bottom: 0.5rem; }
.seed-section ul, .seed-section ol { padding-left: 1.25rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.8; }
.seed-stat { display: flex; align-items: baseline; gap: 0.75rem; padding: 1rem; background: #0a0a14; border-radius: 10px; margin-bottom: 0.75rem; flex-wrap: wrap; }
.seed-stat .stat-value { font-size: 1.5rem; font-weight: 800; color: #818cf8; flex-shrink: 0; }
.seed-stat .stat-label { font-size: 0.9rem; color: #94a3b8; min-width: 0; }
.seed-takeaway { background: linear-gradient(135deg, #1a1a2e, #16213e); border-left: 3px solid #818cf8; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
.seed-takeaway p { color: #e2e8f0; font-weight: 500; margin: 0; }
.seed-pros { background: #0a1a0a; border: 1px solid #1a3a1a; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.5rem; }
.seed-pros h3 { color: #4ade80; }
.seed-cons { background: #1a0a0a; border: 1px solid #3a1a1a; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.5rem; }
.seed-cons h3 { color: #f87171; }
.seed-explore { text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #64748b; }
.seed-explore a { color: #818cf8; text-decoration: underline; }
</style>

Structure:
1. <div class="seed-page"> wrapper
2. <h1> with a compelling, specific title — MUST be under 50 characters (Google truncates after ~60 and we append " | gab.ae")
3. <p class="seed-meta"> with "Updated ${currentDate}"
4. Multiple <div class="seed-section"> blocks
5. Use .seed-stat, .seed-takeaway, .seed-pros, .seed-cons where appropriate
6. FAQ section with <h3> questions and <p> answers
7. Do NOT use HTML tables — use lists or card-style sections

Rules:
- The rewrite must be SUBSTANTIALLY better than the original — not just reworded
- Minimum 3000 characters (longer than original)
- The <h1> MUST be under 50 characters — short, punchy, keyword-focused. Non-negotiable.
- The first <p> after seed-meta MUST be 70-155 characters — it becomes the meta description
- Use exactly ONE <h1> tag (use <h2> for all section headings)
- ${jsAllowed ? 'JavaScript IS allowed and REQUIRED for this tool page — include <script> at the end with polished, working interactive logic. Make it delightful.' : 'No JavaScript, no script tags, no forms — content only.'}
- null over fake data${relatedLinksSection}${relatedKeywordsPrompt}`;

  let html;
  try {
    html = await callLLM(apiKey, prompt, { maxTokens: 16384, model: 'google/gemini-2.5-pro' });
    html = html.replace(/^```html?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
    html = html.replace(/Updated\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}/gi, 'Updated ' + currentDate);
  } catch (e) {
    console.log(`❌ Rework Sonnet error: ${e.message}`);
    return;
  }

  // 5. Validate — must be better (longer) and valid
  if (!html.includes('seed-page') || html.length < 1500) {
    console.log(`❌ Rework: Invalid output (${html.length} chars)`);
    return;
  }

  if (html.length < (page.html || '').length * 0.8) {
    console.log(`❌ Rework: Output shorter than original (${html.length} vs ${(page.html || '').length})`);
    return;
  }

  // 5b. Ensure related links fallback
  if (relatedPages.length > 0) {
    const linkedCount = relatedPages.filter(p => html.includes(`/${p.slug}`)).length;
    if (linkedCount < 2) {
      const relHtml = `<div class="seed-section">
  <h2>Related Resources</h2>
  <ul>${relatedPages.map(p => `<li><a href="/${p.slug}" style="color:#818cf8;text-decoration:underline;">${(p.title || '').replace(' | gab.ae', '')}</a></li>`).join('\n    ')}</ul>
</div>`;
      const seedPageClose = html.search(/<\/div>\s*$/);
      if (seedPageClose > -1) {
        html = html.slice(0, seedPageClose) + relHtml + '\n' + html.slice(seedPageClose);
      }
    }
  }

  // 6. Extract new title and description (with SEO length enforcement)
  const h1Match = html.match(/<h1[^>]*>(.*?)<\/h1>/);
  let title = h1Match ? h1Match[1].replace(/<[^>]+>/g, '').trim() : (page.keyword || page.slug);
  const titleSuffix = ' | gab.ae';
  const maxBase = 60 - titleSuffix.length;
  if (title.length > maxBase) {
    const cut = title.slice(0, maxBase - 1);
    const sp = cut.lastIndexOf(' ');
    title = (sp > maxBase * 0.4 ? cut.slice(0, sp) : cut) + '…';
  }
  const fullTitle = `${title}${titleSuffix}`;
  const firstP = html.match(/<p[^>]*class="[^"]*"[^>]*>([\s\S]*?)<\/p>/);
  const extractedDesc = firstP ? firstP[1].replace(/<[^>]+>/g, '').trim().slice(0, 155) : '';
  const description = extractedDesc.length > 50
    ? (extractedDesc.length > 155 ? extractedDesc.slice(0, 152) + '…' : extractedDesc)
    : `${title}. Expert guide with data, practical tips, and FAQs.`;

  // 7. JSON-LD
  const faqs = [];
  const faqRegex = /<h3[^>]*>([\s\S]*?)<\/h3>\s*<p[^>]*>([\s\S]*?)<\/p>/gi;
  let faqMatch;
  while ((faqMatch = faqRegex.exec(html)) !== null) {
    const q = faqMatch[1].replace(/<[^>]+>/g, '').trim();
    const a = faqMatch[2].replace(/<[^>]+>/g, '').trim();
    if (q.includes('?') || /^(how|what|why|is|can|do|does|should|which)/i.test(q)) {
      faqs.push({ q, a });
    }
  }
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      { '@type': 'Article', headline: title, description, datePublished: page.created_at || new Date().toISOString(), dateModified: new Date().toISOString(), author: { '@type': 'Organization', name: 'gab.ae' }, publisher: { '@type': 'Organization', name: 'gab.ae', url: 'https://gab.ae' }, mainEntityOfPage: { '@type': 'WebPage', '@id': `https://gab.ae/${page.slug}` } },
      ...(faqs.length > 0 ? [{ '@type': 'FAQPage', mainEntity: faqs.map(f => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })) }] : []),
      { '@type': 'BreadcrumbList', itemListElement: [{ '@type': 'ListItem', position: 1, name: 'Home', item: 'https://gab.ae/' }, { '@type': 'ListItem', position: 2, name: (page.category || 'Resources').charAt(0).toUpperCase() + (page.category || 'resources').slice(1), item: `https://gab.ae/category/${page.category || 'general'}` }, { '@type': 'ListItem', position: 3, name: title }] },
    ],
  };
  html = `<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>\n` + html;

  // 8. Update the page in-place
  const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
  await env.DB.prepare(
    `UPDATE pages SET html = ?, title = ?, description = ?, quality = 'llm-sonnet', engine = 'llm-sonnet', updated_at = ? WHERE slug = ?`
  ).bind(html, fullTitle, description, now, page.slug).run();

  console.log(`✅ Reworked: ${page.slug} (${(page.html || '').length} → ${html.length} chars, quality: llm → llm-sonnet)`);
  return { slug: page.slug, title, oldLen: (page.html || '').length, newLen: html.length };
}
