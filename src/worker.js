/**
 * gab.ae — Main Cloudflare Worker
 * 
 * This is the entire backend. It handles:
 * 
 * ROUTING (fetch handler):
 *   /                    → Homepage (featured content, stats, category grid)
 *   /resources           → All pages dashboard (recently published, popular, updated tabs)
 *   /news                → News index (all articles, filterable by category)
 *   /news/{slug}         → Single news article (rendered by engines/news.js)
 *   /{slug}              → Tool/guide/seed page (calculator engine or raw HTML from D1)
 *   /category/{cat}      → Category filter page
 *   /updates             → Public changelog (rendered by engines/changelog.js)
 *   /api/recent-seeds    → JSON: latest seed pages
 *   /api/seed-test       → JSON: manually trigger one seed page generation
 *   /api/search?q=       → JSON: search pages + news
 *   /sitemap.xml         → Auto-generated sitemap
 *   /robots.txt          → Robots file
 * 
 * CRON (scheduled handler, runs every minute):
 *   - llmNews()          → Generate 1 news article from RSS (every tick)
 *   - llmSeedPages()     → Generate 1 seed page from keyword queue (every tick)
 *   - pruneOldViews()    → Clean view_events older than 24h (hourly)
 *   - llmRework()        → Upgrade top-traffic page with better model (daily 4 AM UTC)
 *   - upgradeTrigger()   → Queue pages with 2+ sessions for upgrade (hourly)
 * 
 * DATA:
 *   All content lives in D1 (gab-ae-prod). Pages table stores HTML body content,
 *   news table stores structured JSON. The layout shell (nav, footer, CSS) is
 *   applied by templates/layout.js at render time.
 * 
 * ENV VARS:
 *   DB                   → D1 database binding
 *   OPENROUTER_API_KEY   → For LLM calls (seed pages, news, rework)
 *   ANTHROPIC_API_KEY    → Fallback for LLM calls
 */

import { layout, esc } from './templates/layout.js';
import { renderCalculator } from './engines/calculator.js';
import { renderNews } from './engines/news.js';
import { renderChangelog } from './engines/changelog.js';
import { upgradeTrigger } from './upgrade-trigger.js';
import { llmNews } from './llm-news.js';
import { llmSeedPages, detectIntent } from './llm-seed-pages.js';
import { llmRework } from './llm-rework.js';
import { callLLM } from './llm-client.js';
import { scanAndFixLinks } from './link-scanner.js';
// ═══════════════════════════════════════════════════════════════
// SECTION: Engine Registry
// Maps engine names (from D1 `pages.engine` column) to renderer functions.
// Only 'calculator' has a custom engine; everything else renders raw HTML.
// ═══════════════════════════════════════════════════════════════
const ENGINES = {
  calculator: renderCalculator,
};

// ═══════════════════════════════════════════════════════════════
// SECTION: Utilities
// ═══════════════════════════════════════════════════════════════
function timeAgo(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z');
  const now = new Date();
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  const hrs = Math.floor(diffMs / 3600000);
  const days = Math.floor(diffMs / 86400000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return mins + 'm ago';
  if (hrs < 24) return hrs + 'h ago';
  if (days < 7) return days + 'd ago';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

export default {
  // ═══════════════════════════════════════════════════════════════
  // SECTION: Cron Scheduler (runs every minute via wrangler.toml)
  // Each pipeline has its own frequency gate inside.
  // ═══════════════════════════════════════════════════════════════
  async scheduled(event, env, ctx) {
    // LLM News — every 5th minute
    if (new Date().getUTCMinutes() % 5 === 0) {
      try {
        await llmNews(env);
      } catch (e) {
        console.log(`❌ LLM News error: ${e.message}`);
      }
    }

    // LLM Seed Pages — every minute
    try {
      await llmSeedPages(env);
    } catch (e) {
      console.log(`❌ LLM Seed Pages error: ${e.message}`);
    }

    // Prune view events older than 24h (every hour)
    const nowHour = new Date().getUTCHours();
    const nowMin = new Date().getUTCMinutes();
    if (nowMin < 5) {
      await pruneOldViews(env);
    }

    // Rework top-traffic pages — once daily at 4 AM UTC (11 AM Bangkok)
    if (nowHour === 4 && nowMin < 5) {
      try {
        await llmRework(env);
      } catch (e) {
        console.log(`❌ LLM Rework error: ${e.message}`);
      }
    }

    // Upgrade trigger — check once per hour
    const hourCycle = Math.floor(Date.now() / 3600000);
    if (Date.now() % 3600000 < 300000) {
      try {
        await upgradeTrigger(env);
      } catch (e) {
        console.log(`❌ Upgrade Trigger cron error: ${e.message}`);
      }
    }

    // Link scanner — top of every hour
    if (nowMin === 0) {
      try {
        await scanAndFixLinks(env);
      } catch (e) {
        console.log(`❌ Link scanner error: ${e.message}`);
      }
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // SECTION: Request Router (fetch handler)
  // Routes incoming HTTP requests to the right handler.
  // Order matters — first match wins.
  // ═══════════════════════════════════════════════════════════════
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, '') || '/';

    // Admin: trigger rework manually (secret path) — runs in background via waitUntil
    if (path === '/api/admin/rework' && request.method === 'POST') {
      ctx.waitUntil(llmRework(env).then(r => console.log('✅ Rework result:', JSON.stringify(r))).catch(e => console.log('❌ Rework error:', e.message)));
      return new Response(JSON.stringify({ message: 'Rework triggered in background — check logs' }), { headers: { 'content-type': 'application/json' } });
    }

    // Homepage
    if (path === '/') {
      return homepage(env);
    }

    // Health check
    if (path === '/_health') {
      return new Response(JSON.stringify({ ok: true, ts: Date.now() }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    // Stats endpoint
    if (path === '/_stats') {
      return stats(env);
    }

    // Seed test endpoint
    if (path === '/api/recent-seeds') {
      try {
        const { results } = await env.DB.prepare(
          `SELECT slug, title, keyword, keyword_volume, page_type, quality, target_site, created_at 
           FROM pages WHERE quality IN ('template','premium') AND keyword IS NOT NULL 
           ORDER BY created_at DESC LIMIT 20`
        ).all();
        return new Response(JSON.stringify({ pages: results }), {
          headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60' }
        });
      } catch(e) {
        return new Response(JSON.stringify({ error: e.message }), { status: 500 });
      }
    }

    if (path === '/api/seed-test') {
      try {
        const result = await llmSeedPages(env);
        return new Response(JSON.stringify(result, null, 2), {
          headers: { 'content-type': 'application/json' },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message, stack: e.stack }), {
          status: 500,
          headers: { 'content-type': 'application/json' },
        });
      }
    }

    // SEO Dashboard API
    if (path === '/api/seo-dashboard') {
      return seoDashboardAPI(env);
    }

    // Site Tree API — full apex → cluster → page hierarchy
    if (path === '/api/site-tree') {
      return siteTreeAPI(env);
    }

    // Search API
    // On-demand page generation
    if (path === '/api/generate' && request.method === 'POST') {
      try {
        const { keyword } = await request.json();
        if (!keyword || keyword.length < 3 || keyword.length > 200) {
          return new Response(JSON.stringify({ error: 'Keyword must be 3-200 characters' }), { status: 400, headers: { 'content-type': 'application/json' } });
        }

        // Slugify
        const slug = keyword.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);

        // Check if page already exists
        const existing = await env.DB.prepare("SELECT slug, status FROM pages WHERE slug = ?").bind(slug).first();
        if (existing) {
          return new Response(JSON.stringify({ slug, existing: true }), { headers: { 'content-type': 'application/json' } });
        }

        // Import and call the LLM seed page generator
        const apiKey = env.OPENROUTER_API_KEY || env.ANTHROPIC_API_KEY;
        if (!apiKey) {
          return new Response(JSON.stringify({ error: 'API not configured' }), { status: 500, headers: { 'content-type': 'application/json' } });
        }

        // Find related pages for internal linking
        let onDemandRelated = [];
        try {
          const relResult = await env.DB.prepare(
            "SELECT slug, title FROM pages WHERE status = 'live' AND slug != ? ORDER BY published_at DESC LIMIT 5"
          ).bind(slug).all();
          onDemandRelated = relResult?.results || [];
        } catch (e) { /* ignore */ }
        const onDemandRelatedPrompt = onDemandRelated.length > 0
          ? `\n\nINTERNAL LINKS — Naturally weave these links into your content where relevant. Also include a "Related Resources" section at the bottom:\n${onDemandRelated.map(p => `- <a href="/${p.slug}">${(p.title || '').replace(' | gab.ae', '')}</a>`).join('\n')}`
          : '';

        // Mine related keywords for FAQ section
        let onDemandKeywords = [];
        try {
          const coreWords = keyword.toLowerCase().split(/\s+/).filter(w => w.length > 3 && !['what','how','best','does','with','from','that','this','have','will','your','about','which','where','when'].includes(w));
          if (coreWords.length > 0) {
            const rkResult = await env.DB.prepare(
              "SELECT keyword, volume FROM keywords WHERE keyword LIKE '%' || ? || '%' AND keyword != ? AND volume >= 20 ORDER BY volume DESC LIMIT 5"
            ).bind(coreWords[0], keyword).all();
            onDemandKeywords = rkResult?.results || [];
          }
        } catch (e) { /* ignore */ }
        const onDemandKeywordsPrompt = onDemandKeywords.length > 0
          ? `\n\nFAQ KEYWORDS — Include these as exact questions in your FAQ section (real people search for these):\n${onDemandKeywords.map(rk => `- "${rk.keyword}" (${rk.volume} monthly searches)`).join('\n')}`
          : '';

        // Call LLM via OpenRouter
        const onDemandPrompt = (() => {
              const intent = detectIntent(keyword);
              const jsAllowed = intent === 'interactive_tool';
              const intentInstructions = {
                interactive_tool: `Create a FULLY FUNCTIONAL INTERACTIVE TOOL for "${keyword}". JavaScript IS required. Build a beautiful, working tool — large animated displays for timers, instant output for generators, real-time conversion for converters. Include <script> at end. Add a brief explanation + 3-5 FAQs below the tool. Make it DELIGHTFUL.`,
                listicle: `Create a TOP LIST about "${keyword}". Include 7-10 items ranked with name, key features, pros/cons, and a one-line verdict. Start with a quick summary of the top 3 picks. Add a "How We Evaluated" section and 3-5 FAQs.`,
                comparison: `Create a SIDE-BY-SIDE COMPARISON for "${keyword}". Compare 2-4 options across multiple criteria. Lead with a summary verdict (who should pick what). Give each option its own section. End with 3-5 FAQs.`,
                tutorial: `Create a STEP-BY-STEP TUTORIAL for "${keyword}". Start with what you'll learn and why. Use numbered steps, each in its own section. Include common mistakes to avoid, prerequisites if any, and 3-5 FAQs.`,
                calculator: `Create a DATA-DRIVEN REFERENCE page about "${keyword}". Explain what it measures and why it matters. Include reference tables with common values/ranges/benchmarks, a manual calculation guide, key factors, and 3-5 FAQs. No JavaScript or interactive elements.`,
                definition: `Create a clear EXPLAINER page about "${keyword}". Start with a plain-English definition. Cover why it matters, how it works with examples, related concepts, common misconceptions, and 3-5 FAQs.`,
                review: `Create an HONEST REVIEW of "${keyword}". Lead with a verdict summary (who it's for, key takeaway). Cover what it does well, what it does poorly, who should/shouldn't use it, 2-3 alternatives, and 3-5 FAQs.`,
                list_query: `Create a COMPREHENSIVE LIST for "${keyword}". Brief intro on scope and selection criteria. Each item gets a short description. Organize by subcategory if applicable. Summarize key patterns and add 3-5 FAQs.`,
                educational: `Create a comprehensive EDUCATIONAL guide about "${keyword}". Cover what it is, how it works, key facts/data, practical tips, and 3-5 FAQs that real people search for.`,
              };
              return `You are a senior content strategist for gab.ae competing against the top 5 Google results for "${keyword}". Imagine what those pages look like — thin content, ads, missing subtopics. Build something better. ${intentInstructions[intent] || intentInstructions.educational}

Return ONLY raw HTML (no markdown fences, no explanation). Use these CSS classes:

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
</style>
<div class="seed-page">
  <h1>Compelling title about ${keyword}</h1>
  <p class="seed-meta">Updated ${new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</p>
  [sections with seed-section class]
  [FAQ section]
</div>

Visual components (use where appropriate):
- <div class="seed-stat"><span class="stat-value">78%</span><span class="stat-label">description</span></div> — for key statistics
- <div class="seed-takeaway"><p>Key insight</p></div> — for important takeaways
- <div class="seed-pros"><h3>✅ Pros</h3><ul>...</ul></div> and <div class="seed-cons"><h3>❌ Cons</h3><ul>...</ul></div> — for reviews/comparisons

Rules:
- Write like a human expert — no template filler
- ${jsAllowed ? 'JavaScript IS allowed and REQUIRED — include <script> at the end. Make it polished and delightful.' : 'Do NOT include JavaScript, script tags, or interactive elements.'}
- Do NOT use HTML tables — use bullet lists or card-style sections instead
- Minimum 2000 characters of content
- NEVER cite exact numbers without qualification — use "approximately", "typically", or ranges
- NEVER invent study names, researcher names, or specific citations
- Prefer verifiable general knowledge over specific unverifiable claims
- null over fake data — when uncertain, use ranges with explicit caveats${onDemandRelatedPrompt}${onDemandKeywordsPrompt}`;
            })();

        let html;
        try {
          html = await callLLM(apiKey, onDemandPrompt, { maxTokens: 8192, model: 'google/gemini-2.0-flash-001' });
        } catch (e) {
          return new Response(JSON.stringify({ error: 'AI generation failed' }), { status: 500, headers: { 'content-type': 'application/json' } });
        }
        // Strip markdown code fences (```html ... ```)
        html = html.replace(/^```html?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
        // Fix wrong dates from Haiku (training data cutoff)
        const currentDate = new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
        html = html.replace(/(?:Updated|Last updated:?)\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}/gi, 'Updated ' + currentDate);
        // Strip stray document tags Haiku might include — but preserve <style> blocks
        const genStyles = [];
        html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, m => { genStyles.push(m); return ''; });
        html = html.replace(/<!DOCTYPE[^>]*>/gi, '').replace(/<\/?html[^>]*>/gi, '').replace(/<head>[\s\S]*?<\/head>/gi, '').replace(/<\/?body[^>]*>/gi, '').replace(/<title>[\s\S]*?<\/title>/gi, '').replace(/<meta[^>]*>/gi, '');
        if (genStyles.length) html = genStyles.join('\n') + '\n' + html;

        // If Haiku omitted the <style> block, inject the standard seed page CSS
        if (!html.includes('<style')) {
          const fallbackCss = `<style>
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
</style>`;
          html = fallbackCss + '\n' + html;
        }

        if (!html.includes('seed-page') || html.length < 500) {
          return new Response(JSON.stringify({ error: 'Generated content too short or invalid' }), { status: 500, headers: { 'content-type': 'application/json' } });
        }

        // Ensure related links are present — inject fallback if Haiku skipped them
        if (onDemandRelated.length > 0) {
          const linkedCount = onDemandRelated.filter(p => html.includes(`/${p.slug}`)).length;
          if (linkedCount < 2) {
            const relHtml = `<div class="seed-section">
  <h2>Related Resources</h2>
  <ul>${onDemandRelated.map(p => `<li><a href="/${p.slug}" style="color:#818cf8;text-decoration:underline;">${(p.title || '').replace(' | gab.ae', '')}</a></li>`).join('\n    ')}</ul>
</div>`;
            const seedPageClose = html.search(/<\/div>\s*$/);
            if (seedPageClose > -1) html = html.slice(0, seedPageClose) + relHtml + '\n' + html.slice(seedPageClose);
          }
        }

        // Extract title from h1
        const h1 = (html.match(/<h1[^>]*>(.*?)<\/h1>/) || [])[1] || keyword;
        const titleClean = h1.replace(/<[^>]+>/g, '').trim();
        const title = titleClean + ' | gab.ae';
        // Generate unique description from first paragraph
        const onDemandFirstP = html.match(/<p[^>]*class="[^"]*"[^>]*>([\s\S]*?)<\/p>/);
        const onDemandDesc = onDemandFirstP ? onDemandFirstP[1].replace(/<[^>]+>/g, '').trim().slice(0, 155) : '';
        const description = onDemandDesc.length > 50
          ? onDemandDesc + (onDemandDesc.length >= 155 ? '…' : '')
          : `${titleClean}. Expert guide with data, practical tips, and FAQs about ${keyword}.`;

        // JSON-LD structured data
        const odFaqs = [];
        const odFaqRegex = /<h3[^>]*>([\s\S]*?)<\/h3>\s*<p[^>]*>([\s\S]*?)<\/p>/gi;
        let odFaqMatch;
        while ((odFaqMatch = odFaqRegex.exec(html)) !== null) {
          const q = odFaqMatch[1].replace(/<[^>]+>/g, '').trim();
          const a = odFaqMatch[2].replace(/<[^>]+>/g, '').trim();
          if (q.includes('?') || /^(how|what|why|is|can|do|does|should|which)/i.test(q)) {
            odFaqs.push({ q, a });
          }
        }
        const odJsonLd = {
          '@context': 'https://schema.org',
          '@graph': [
            { '@type': 'Article', headline: titleClean, description, datePublished: new Date().toISOString(), dateModified: new Date().toISOString(), author: { '@type': 'Organization', name: 'gab.ae' }, publisher: { '@type': 'Organization', name: 'gab.ae', url: 'https://gab.ae' }, mainEntityOfPage: { '@type': 'WebPage', '@id': `https://gab.ae/${slug}` } },
            ...(odFaqs.length > 0 ? [{ '@type': 'FAQPage', mainEntity: odFaqs.map(f => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })) }] : []),
            { '@type': 'BreadcrumbList', itemListElement: [{ '@type': 'ListItem', position: 1, name: 'Home', item: 'https://gab.ae/' }, { '@type': 'ListItem', position: 2, name: titleClean }] },
          ],
        };
        html = `<script type="application/ld+json">${JSON.stringify(odJsonLd)}</script>\n` + html;

        const now = new Date().toISOString().replace('T', ' ').slice(0, 19);

        // Insert
        await env.DB.prepare(
          "INSERT INTO pages (slug, title, description, category, engine, html, status, quality, keyword, page_type, published_at, updated_at, created_at) VALUES (?, ?, ?, 'on-demand', 'llm-haiku', ?, 'live', 'llm', ?, 'educational', ?, ?, ?)"
        ).bind(slug, title, description, html, keyword, now, now, now).run();

        return new Response(JSON.stringify({ slug, title: h1 }), { headers: { 'content-type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: { 'content-type': 'application/json' } });
      }
    }

    // Redirect /guides/* to /resources (these were planned but never created)
    if (path.startsWith('/guides/')) {
      return Response.redirect('https://gab.ae/resources', 301);
    }

    if (path === '/api/404s') {
      const { results } = await env.DB.prepare(
        "SELECT path, count, last_seen FROM not_found_log ORDER BY count DESC LIMIT 50"
      ).all();
      return new Response(JSON.stringify(results), { headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60' } });
    }

    if (path === '/_search') {
      const q = url.searchParams.get('q')?.toLowerCase() || '';
      if (q.length < 2) return new Response(JSON.stringify({ results: [] }), { headers: { 'content-type': 'application/json' } });
      try {
        const toolResults = await env.DB.prepare(
          "SELECT slug, title, category, 'tool' as type FROM pages WHERE status = 'live' AND (LOWER(title) LIKE ? OR LOWER(slug) LIKE ?) ORDER BY title ASC LIMIT 6"
        ).bind(`%${q}%`, `%${q}%`).all();
        const newsResults = await env.DB.prepare(
          "SELECT slug, title, category, 'news' as type FROM news WHERE status = 'live' AND (LOWER(title) LIKE ? OR LOWER(slug) LIKE ?) ORDER BY published_at DESC LIMIT 4"
        ).bind(`%${q}%`, `%${q}%`).all();
        const combined = [...(newsResults?.results || []), ...(toolResults?.results || [])];
        return new Response(JSON.stringify({ results: combined }), {
          headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60' },
        });
      } catch (e) {
        return new Response(JSON.stringify({ results: [], error: e.message }), { headers: { 'content-type': 'application/json' } });
      }
    }

    // Sitemap
    if (path === '/sitemap.xml') {
      return sitemap(env);
    }

    // Robots.txt
    if (path === '/robots.txt') {
      return new Response(`User-agent: *\nAllow: /\n\nSitemap: https://gab.ae/sitemap.xml\n`, {
        headers: { 'content-type': 'text/plain' },
      });
    }

    // Site health dashboard
    if (path === '/health') {
      if (url.searchParams.get('run') === '1') {
        await scanAndFixLinks(env);
      }
      return healthPage(env);
    }

        // Resources — apex guides hub
    if (path === '/resources') {
      return resourcesPage(env);
    }

    // Updates / Changelog
    if (path === '/updates') {
      try {
        const { results } = await env.DB.prepare("SELECT * FROM changelog WHERE status = 'live' ORDER BY created_at DESC LIMIT 50").all();
        const html = renderChangelog(results || []);
        return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
      } catch (e) {
        return new Response('Error loading updates', { status: 500 });
      }
    }

    // Category pages
    const catMatch = path.match(/^\/category\/([a-z0-9-]+)$/);
    if (catMatch) {
      return categoryPage(env, catMatch[1]);
    }

    // News index
    if (path === '/news') {
      return newsIndex(env);
    }

    // News category
    const newsCatMatch = path.match(/^\/news\/category\/([a-z0-9-]+)$/);
    if (newsCatMatch) {
      return newsIndex(env, newsCatMatch[1]);
    }

    // News article
    const newsMatch = path.match(/^\/news\/([a-z0-9-]+)$/);
    if (newsMatch) {
      try {
        const article = await env.DB.prepare("SELECT * FROM news WHERE slug = ? AND status = 'live'").bind(newsMatch[1]).first();
        if (article) {
          ctx.waitUntil(trackView(env, 'news/' + newsMatch[1]));
          const html = renderNews(article);
          return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
        }
      } catch (e) {}
    }

    // Strip leading slash for slug lookup
    const slug = path.slice(1);

    // Check for redirects (status='redirect')
    try {
      const redir = await env.DB.prepare("SELECT slug FROM pages WHERE slug = ? AND status = 'redirect'").bind(slug).first();
      if (redir) {
        // Duplicate apex slugs → guide-2026 versions
        const APEX_REDIRECTS = {
          'capital-markets-wealth': 'capital-markets-wealth-guide-2026',
          'digital-media-creator-economy': 'digital-media-creator-economy-guide-2026',
          'ecommerce-supply-chain': 'ecommerce-supply-chain-guide-2026',
          'education-knowledge-commerce': 'education-knowledge-commerce-guide-2026',
          'fine-arts-design-creative': 'fine-arts-design-creative-guide-2026',
          'global-mobility-geo-arbitrage': 'global-mobility-geo-arbitrage-guide-2026',
          'human-optimization-health': 'human-optimization-health-guide-2026',
          'interpersonal-dynamics-intimacy': 'interpersonal-dynamics-intimacy-guide-2026',
          'real-estate-hospitality': 'real-estate-hospitality-guide-2026',
          'software-ai-infrastructure': 'software-ai-infrastructure-guide-2026',
        };
        const target = APEX_REDIRECTS[slug] || slug;
        return Response.redirect(new URL('/' + target, url.origin).toString(), 301);
      }
    } catch(e) {}

    // Look up page in D1
    try {
      const page = await env.DB.prepare('SELECT * FROM pages WHERE slug = ? AND status = ?')
        .bind(slug, 'live')
        .first();

      if (!page) {
        return notFound(env, path);
      }

      ctx.waitUntil(trackView(env, slug));

      let body;
      let schemaJson = page.schema_json ? JSON.parse(page.schema_json) : null;

      if (page.html) {
        // Full HTML page stored in D1 — serve directly in layout shell
        // Extract <style> blocks before stripping <head> so CSS is preserved
        const styleBlocks = [];
        page.html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, m => { styleBlocks.push(m); return ''; });
        body = page.html
          .replace(/<!DOCTYPE[^>]*>/gi, '')
          .replace(/<\/?html[^>]*>/gi, '')
          .replace(/<head>[\s\S]*?<\/head>/gi, '')
          .replace(/<\/?body[^>]*>/gi, '')
          .replace(/<title>[\s\S]*?<\/title>/gi, '')
          .replace(/<meta[^>]*>/gi, '');
        if (styleBlocks.length) body = styleBlocks.join('\n') + '\n' + body;
      } else {
        // Legacy config-driven engine
        const engine = ENGINES[page.engine];
        if (!engine) {
          return new Response(`Unknown engine: ${page.engine}`, { status: 500 });
        }
        body = engine(page);
      }
      
      // Visible breadcrumb
      const cat = page.category || 'general';
      const catLabel = cat.charAt(0).toUpperCase() + cat.slice(1).replace(/-/g, ' ');
      const breadcrumb = `<nav aria-label="Breadcrumb" class="text-sm text-gray-500 mb-4 flex items-center gap-1.5 flex-wrap">
        <a href="/" class="hover:text-white transition-colors">Home</a>
        <span class="text-gray-600">›</span>
        <a href="/category/${esc(cat)}" class="hover:text-white transition-colors">${esc(catLabel)}</a>
        <span class="text-gray-600">›</span>
        <span class="text-gray-400">${esc((page.title || '').replace(' | gab.ae', ''))}</span>
      </nav>`;
      body = breadcrumb + body;

      const html = layout({
        title: page.title,
        description: page.description,
        canonical: `https://gab.ae/${page.slug}`,
        schemaJson,
        body,
      });

      return new Response(html, {
        headers: {
          'content-type': 'text/html;charset=UTF-8',
          'cache-control': 'public, max-age=3600, s-maxage=86400',
        },
      });
    } catch (err) {
      return new Response(`Error: ${err.message}`, { status: 500 });
    }
  },
};

// ═══════════════════════════════════════════════════════════════
// SECTION: HTML Renderers (helper functions that build page HTML)
// These are called by the route handlers above.
// ═══════════════════════════════════════════════════════════════
function renderNewsCards(articles) {
  if (!articles || !articles.length) return '';
  const cards = articles.map(function(a) {
    var date = timeAgo(a.published_at);
    var catGradients = { world: 'from-blue-900 to-blue-700', politics: 'from-purple-900 to-purple-700', business: 'from-emerald-900 to-emerald-700', health: 'from-red-900 to-red-700', sports: 'from-orange-900 to-orange-700', entertainment: 'from-pink-900 to-pink-700', tech: 'from-cyan-900 to-cyan-700', science: 'from-indigo-900 to-indigo-700', climate: 'from-green-900 to-green-700', travel: 'from-amber-900 to-amber-700', us: 'from-slate-900 to-slate-700' };
    var catLabels = { world: 'WORLD', politics: 'POLITICS', business: 'BIZ', health: 'HEALTH', sports: 'SPORTS', entertainment: 'ENTERTAINMENT', tech: 'TECH', science: 'SCIENCE', climate: 'CLIMATE', travel: 'TRAVEL', us: 'US' };
    var grad = catGradients[a.category] || 'from-gray-900 to-gray-700';
    var label = catLabels[a.category] || a.category.toUpperCase();
    var imgHtml = '<div class="w-full h-32 bg-gradient-to-br ' + grad + ' flex items-center justify-center"><span class="text-2xl font-black tracking-widest text-white/20">' + label + '</span></div>';
    return '<a href="/news/' + a.slug + '" class="group block bg-surface border border-surface-border rounded-xl overflow-hidden hover:border-accent/30 transition-all">'
      + imgHtml
      + '<div class="p-3">'
      + '<div class="flex items-center gap-2 text-[10px] text-gray-500 mb-1">'
      + '<span class="capitalize">' + a.category + '</span>'
      + '<span>·</span>'
      + '<span>' + date + '</span>'
      + '</div>'
      + '<h3 class="text-sm font-semibold text-white group-hover:text-accent transition-colors line-clamp-2">' + esc(a.title) + '</h3>'
      + '</div></a>';
  }).join('');

  return '<div class="mb-10">'
    + '<div class="flex items-center justify-between mb-4">'
    + '<h2 class="text-lg font-bold text-white flex items-center gap-2">'
    + '<span class="w-1 h-5 bg-accent rounded-full inline-block"></span>'
    + '📰 Latest News</h2>'
    + '<a href="/news" class="text-sm text-accent hover:underline">All news →</a>'
    + '</div>'
    + '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">'
    + cards + '</div></div>';
}

function renderPropertyCards() {
  const standalone = [
    { section: 'Portfolio', items: [
      { name: 'Ali Imperiale', url: 'https://aliimperiale.com', color: '#E8B4B8', icon: '✨', tag: 'Personal Brand', desc: 'Sex educator, content creator & speaker — workshops, coaching & educational content.' },
      { name: 'Auberge de nos Aïeux', url: 'https://aubergedenosaieux.com', color: '#8B7355', icon: '🏔️', tag: 'Hospitality', desc: '40+ room auberge in Les Éboulements, Charlevoix — van life, camping & nature getaways in the heart of Quebec.' },
    ]},
  ];

  const properties = [
    { section: 'Finance', items: [
      { name: 'Westmount Fundamentals', url: 'https://westmountfundamentals.com', color: '#4a8fe7', icon: '📊', tag: 'Equity Research', desc: 'Independent equity research — intrinsic value calculations, prospect scores & fundamental analysis across 600+ stocks.', stats: ['📈 661 IV Reports', '🎯 1,610 Prospect Scores', '🔬 2,600+ Pages'] },
      { name: 'Firemaths', url: 'https://firemaths.info', color: '#D4A017', icon: '🔥', tag: 'Money Calculators', desc: 'Finance & money calculators — compound interest, retirement planning, loan amortization & investment tools.' },
    ]},
    { section: 'Tech', items: [
      { name: 'SiliconBased', url: 'https://siliconbased.dev', color: '#818cf8', icon: '⚡', tag: 'Dev Tools', desc: 'Free developer tools & utilities — chmod, cron, regex builders, HTTP status references & performance benchmarks.' },
      { name: 'Fix It With Duct Tape', url: 'https://fixitwithducttape.photonbuilder.com', color: '#A0A0A0', icon: '🔧', tag: 'AI & SaaS Reviews', desc: 'AI tool reviews, SaaS comparisons & practical guides for building with modern software.' },
    ]},
    { section: 'Health & Wellness', items: [
      { name: 'Body Count', url: 'https://bodycount.photonbuilder.com', color: '#E05A5A', icon: '❤️', tag: 'Health Calculators', desc: 'Free health & body calculators — BMI, TDEE, macros, body fat & fitness tracking tools.' },
      { name: 'The Nookie Nook', url: 'https://thenookienook.com', color: '#E84393', icon: '💜', tag: 'Sexual Health', desc: 'Sexual health guides & tools — evidence-based information, calculators & educational resources.' },
    ]},
    { section: 'Lifestyle', items: [
      { name: 'Migrating Mammals', url: 'https://migratingmammals.com', color: '#C4956A', icon: '🌍', tag: 'Digital Nomad', desc: 'Digital nomad & travel tools — visa indexes, cost of living comparisons & remote work resources.' },
      { name: 'I Just Want To Live', url: 'https://ijustwantto.live', color: '#2DB89A', icon: '🏠', tag: 'Home & DIY', desc: 'Practical home & DIY calculators — mulch, paint, flooring, concrete & everyday project tools.' },
      { name: '28 Grams', url: 'https://28grams.vip', color: '#C2185B', icon: '🍳', tag: 'Kitchen Science', desc: 'Cooking tools, recipe calculators & kitchen science — from sourdough hydration to serving converters.' },
    ]},
    { section: 'Education & Career', items: [
      { name: 'Send Nerds', url: 'https://sendnerds.photonbuilder.com', color: '#3B82F6', icon: '📚', tag: 'Academic Tools', desc: 'Free education & academic calculators — GPA, grade averages, study planners & learning tools.' },
      { name: 'Get The Bag', url: 'https://getthebag.photonbuilder.com', color: '#3B82F6', icon: '💼', tag: 'Career Tools', desc: 'Career tools & job resources — salary comparisons, interview prep & professional development.' },
    ]},
    { section: 'Fun & Utility', items: [
      { name: 'Leeroy Jenkins', url: 'https://leeroyjenkins.quest', color: '#9333EA', icon: '🎮', tag: 'Gaming', desc: 'Gaming gear reviews, performance tools & benchmarks for PC and console gamers.' },
      { name: 'Just One Moment', url: 'https://justonemoment.photonbuilder.com', color: '#F59E0B', icon: '⏱️', tag: 'Timers', desc: 'Free online timers, countdowns & stopwatches for every occasion.' },
      { name: 'Papyrus People', url: 'https://papyruspeople.photonbuilder.com', color: '#D4A574', icon: '📝', tag: 'Text Tools', desc: 'Text tools & character generators — word counters, formatters & writing utilities.' },
      { name: 'Eenie Meenie', url: 'https://eeniemeenie.photonbuilder.com', color: '#E040FB', icon: '🎲', tag: 'Random Generators', desc: 'Random generators & decision tools — name pickers, coin flips & choice makers.' },
      { name: 'Please Start Please', url: 'https://pleasestartplease.photonbuilder.com', color: '#EF4444', icon: '🚗', tag: 'Automotive', desc: 'Car tools, guides & automotive data — maintenance calculators, specs & vehicle resources.' },
    ]},
  ];

  const allSections = [...properties, ...standalone];
  return allSections.map(section => `
    <div class="mb-6">
      <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">${section.section}</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        ${section.items.map(p => `
          <a href="${p.url}" target="_blank" rel="noopener" class="group flex items-start gap-4 bg-surface border border-surface-border rounded-xl p-4 hover:border-[${p.color}]/50 transition-all">
            <div class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-lg" style="background:${p.color}15">${p.icon}</div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-0.5">
                <span class="text-sm font-bold text-white group-hover:text-[${p.color}] transition-colors">${p.name}</span>
                <span class="text-[10px] font-medium px-1.5 py-0.5 rounded-full" style="background:${p.color}20;color:${p.color}">${p.tag}</span>
              </div>
              <p class="text-xs text-gray-500 line-clamp-2">${p.desc}</p>
              ${p.stats ? `<div class="flex flex-wrap gap-3 text-[10px] text-gray-600 mt-1.5">${p.stats.map(s => `<span>${s}</span>`).join('')}</div>` : ''}
            </div>
          </a>
        `).join('')}
      </div>
    </div>
  `).join('');
}

// ═══════════════════════════════════════════════════════════════
// SECTION: Page Handlers (full page builders called by router)
// Each returns a Response object with complete HTML.
// ═══════════════════════════════════════════════════════════════
async function homepage(env) {
  const body = `
    <div class="min-h-[60vh] flex flex-col items-center justify-center">
      <div class="max-w-2xl mx-auto text-center mb-8">
        <h1 class="text-4xl font-black text-white mb-4">Hi, my name is Gab</h1>
        <p class="text-lg text-gray-400">My team of robots and I love to answer questions and give information.</p>
      </div>

      <div class="w-full max-w-2xl">
        <form id="ask-form" class="flex gap-2" onsubmit="return handleAsk(event)">
          <input type="text" id="ask-input" placeholder="Ask us anything..." 
            class="flex-1 px-5 py-4 bg-surface border border-surface-border rounded-xl text-white text-lg focus:border-accent focus:outline-none transition-colors"
            autocomplete="off" required>
          <button type="submit" id="ask-btn" class="px-6 py-4 bg-accent text-white text-base font-medium rounded-xl hover:bg-accent/80 transition-colors whitespace-nowrap">
            Go
          </button>
        </form>
        <div id="ask-status" class="mt-3 text-sm text-gray-500 hidden text-center"></div>
      </div>
    </div>

    <script>
    function resetAskForm() {
      var input = document.getElementById('ask-input');
      var btn = document.getElementById('ask-btn');
      var status = document.getElementById('ask-status');
      if (input) input.value = '';
      if (btn) { btn.disabled = false; btn.textContent = 'Go'; }
      if (status) { status.classList.add('hidden'); status.textContent = ''; }
    }
    window.addEventListener('pageshow', resetAskForm);

    async function handleAsk(e) {
      e.preventDefault();
      var input = document.getElementById('ask-input');
      var btn = document.getElementById('ask-btn');
      var status = document.getElementById('ask-status');
      var keyword = input.value.trim();
      if (!keyword || keyword.length < 3) return false;

      btn.disabled = true;
      btn.textContent = 'Generating...';
      status.classList.remove('hidden');
      status.textContent = '\u23f3 Generating answer \u2014 this takes about 30 seconds...';
      status.className = 'mt-3 text-sm text-accent text-center';

      try {
        var resp = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ keyword: keyword }),
        });
        var data = await resp.json();
        if (data.slug) {
          status.textContent = data.existing ? '\u2705 Page found! Redirecting...' : '\u2705 Page created! Redirecting...';
          status.className = 'mt-3 text-sm text-green-400 text-center';
          setTimeout(function() { window.location.href = '/' + data.slug; }, 500);
        } else {
          status.textContent = '\u274c ' + (data.error || 'Something went wrong. Try again.');
          status.className = 'mt-3 text-sm text-red-400 text-center';
          btn.disabled = false;
          btn.textContent = 'Go';
        }
      } catch (err) {
        status.textContent = '\u274c Network error. Try again.';
        status.className = 'mt-3 text-sm text-red-400 text-center';
        btn.disabled = false;
        btn.textContent = 'Go';
      }
      return false;
    }
    </script>
  `;

  return new Response(layout({
    title: 'gab.ae — Ask the Team',
    description: 'Free tools, news, and expert guides across finance, tech, health, travel, gaming, and more. Built by a team of humans and AI agents answering your questions.',
    canonical: 'https://gab.ae/',
    body,
  }), {
    headers: { 'content-type': 'text/html;charset=UTF-8' },
  });
}

async function newsIndex(env, category = null) {
  let articles = [];
  let categories = [];
  try {
    const catQ = category 
      ? env.DB.prepare("SELECT * FROM news WHERE status='live' AND category=? ORDER BY published_at DESC LIMIT 50").bind(category)
      : env.DB.prepare("SELECT * FROM news WHERE status='live' ORDER BY published_at DESC LIMIT 50");
    const result = await catQ.all();
    articles = result?.results || [];
    const catResult = await env.DB.prepare("SELECT category, COUNT(*) as cnt FROM news WHERE status='live' GROUP BY category ORDER BY cnt DESC").all();
    categories = catResult?.results || [];
  } catch (e) { console.log('❌ newsIndex error:', e.message, e.stack); }

  const catIcons = { us: '🇺🇸', world: '🌍', politics: '🏛️', business: '💼', health: '🏥', entertainment: '🎬', travel: '✈️', sports: '⚽', science: '🔬', climate: '🌱', tech: '💻' };

  const catTabsHtml = categories.map(c => 
    `<a href="/news/category/${c.category}" class="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium ${category === c.category ? 'bg-accent text-white' : 'bg-surface border border-surface-border text-gray-400 hover:bg-accent/10 hover:text-white'} transition-all">
      ${catIcons[c.category] || '📰'} ${c.category.charAt(0).toUpperCase() + c.category.slice(1)} (${c.cnt})
    </a>`
  ).join('');

  const articlesHtml = articles.map(a => {
    const date = timeAgo(a.published_at);
    return `
      <a href="/news/${a.slug}" class="group block bg-surface border border-surface-border rounded-xl overflow-hidden hover:border-accent/30 transition-all">
        <div class="w-full h-40 bg-gradient-to-br ${({'world':'from-blue-900 to-blue-700','politics':'from-purple-900 to-purple-700','business':'from-emerald-900 to-emerald-700','health':'from-red-900 to-red-700','sports':'from-orange-900 to-orange-700','entertainment':'from-pink-900 to-pink-700','tech':'from-cyan-900 to-cyan-700','science':'from-indigo-900 to-indigo-700','climate':'from-green-900 to-green-700','travel':'from-amber-900 to-amber-700','us':'from-slate-900 to-slate-700'})[a.category] || 'from-gray-900 to-gray-700'} flex items-center justify-center"><span class="text-3xl font-black tracking-widest text-white/20">${(a.category || 'news').toUpperCase()}</span></div>
        <div class="p-4">
          <div class="flex items-center gap-2 text-xs text-gray-500 mb-2">
            <span class="capitalize">${a.category}</span>
            <span>·</span>
            <span>${date}</span>
          </div>
          <h3 class="text-sm font-bold text-white group-hover:text-accent transition-colors mb-1 line-clamp-2">${esc(a.title)}</h3>
          <p class="text-xs text-gray-500 line-clamp-2">${esc(a.description || '')}</p>
        </div>
      </a>`;
  }).join('');

  const heading = category ? `${catIcons[category] || '📰'} ${category.charAt(0).toUpperCase() + category.slice(1)} News` : '📰 Latest News';

  const body = `
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-white mb-2">${heading}</h1>
      <p class="text-gray-400 text-sm">Breaking stories and analysis</p>
    </div>
    <div class="flex gap-2 overflow-x-auto pb-2 mb-6 scrollbar-hide">
      <a href="/news" class="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium ${!category ? 'bg-accent text-white' : 'bg-surface border border-surface-border text-gray-400 hover:bg-accent/10 hover:text-white'} transition-all">All</a>
      ${catTabsHtml}
    </div>
    ${articles.length ? `<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">${articlesHtml}</div>` : '<p class="text-gray-500 text-center py-12">No articles yet — check back soon.</p>'}
    <style>.line-clamp-2{overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;}.scrollbar-hide::-webkit-scrollbar{display:none;}.scrollbar-hide{-ms-overflow-style:none;scrollbar-width:none;}</style>
  `;

  return new Response(layout({
    title: category ? `${category.charAt(0).toUpperCase() + category.slice(1)} News | gab.ae` : 'Latest News & Analysis | gab.ae',
    description: category ? `Latest ${category} news, breaking stories, and in-depth analysis. Updated every 5 minutes with AI-powered summaries and expert context.` : 'Latest news, breaking stories, and in-depth analysis across business, tech, world affairs, health, science, and entertainment. Updated every 5 minutes.',
    canonical: category ? `https://gab.ae/news/category/${category}` : 'https://gab.ae/news',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
}

async function stats(env) {
  try {
    const pages = await env.DB.prepare("SELECT engine, status, COUNT(*) as count FROM pages GROUP BY engine, status").all();
    const keywords = await env.DB.prepare("SELECT status, COUNT(*) as count FROM keywords GROUP BY status").all();
    return new Response(JSON.stringify({ pages: pages.results, keywords: keywords.results }, null, 2), {
      headers: { 'content-type': 'application/json' },
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: { 'content-type': 'application/json' } });
  }
}

async function sitemap(env) {
  try {
    const result = await env.DB.prepare(
      "SELECT slug, updated_at FROM pages WHERE status = 'live' ORDER BY slug ASC"
    ).all();
    const pages = result?.results || [];

    const urls = [
      `  <url>\n    <loc>https://gab.ae/</loc>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>`
    ];

    for (const p of pages) {
      const lastmod = p.updated_at ? `\n    <lastmod>${p.updated_at.split(' ')[0]}</lastmod>` : '';
      urls.push(`  <url>\n    <loc>https://gab.ae/${p.slug}</loc>${lastmod}\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>`);
    }

    // Add category pages
    const cats = await env.DB.prepare(
      "SELECT DISTINCT category FROM pages WHERE status = 'live' ORDER BY category ASC"
    ).all();
    for (const c of (cats?.results || [])) {
      urls.push(`  <url>\n    <loc>https://gab.ae/category/${c.category}</loc>\n    <changefreq>daily</changefreq>\n    <priority>0.6</priority>\n  </url>`);
    }

    const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>`;

    return new Response(xml, {
      headers: {
        'content-type': 'application/xml',
        'cache-control': 'public, max-age=3600, s-maxage=3600',
      },
    });
  } catch (err) {
    return new Response(`Error: ${err.message}`, { status: 500 });
  }
}

async function categoryPage(env, category) {
  try {
    const result = await env.DB.prepare(
      "SELECT slug, title, engine, category FROM pages WHERE status = 'live' AND category = ? ORDER BY title ASC LIMIT 200"
    ).bind(category).all();
    const pages = result?.results || [];

    if (pages.length === 0) {
      return notFound(env, path);
    }

    const pagesHtml = pages.map(p =>
      `<a href="/${p.slug}" class="block px-4 py-3 bg-surface border border-surface-border rounded-lg hover:border-accent transition-colors">
        <div class="text-gray-200 font-medium">${esc(p.title)}</div>
        <div class="text-sm text-gray-500 mt-1 capitalize">${p.engine}</div>
      </a>`
    ).join('');

    const catName = category.charAt(0).toUpperCase() + category.slice(1);
    const body = `
      <div class="mt-8 mb-8">
        <a href="/" class="text-accent hover:underline text-sm">&larr; All Categories</a>
        <h1 class="text-3xl md:text-4xl font-bold text-white mt-4 mb-2">${esc(catName)}</h1>
        <p class="text-gray-400 mb-8">${pages.length} tool${pages.length !== 1 ? 's' : ''}</p>
        <div class="space-y-2">${pagesHtml}</div>
      </div>`;

    const html = layout({
      title: `${catName} Tools | gab.ae`,
      description: `Free ${category} tools, calculators, guides, and resources. Expert-written content updated daily with data-driven insights and practical recommendations.`,
      canonical: `https://gab.ae/category/${category}`,
      body,
    });

    return new Response(html, {
      headers: {
        'content-type': 'text/html;charset=UTF-8',
        'cache-control': 'public, max-age=3600, s-maxage=86400',
      },
    });
  } catch (err) {
    return new Response(`Error: ${err.message}`, { status: 500 });
  }
}

// ─── View tracking (rolling 24h) ───
// ═══════════════════════════════════════════════════════════════
// SECTION: Analytics (view tracking + pruning)
// Tracks page views in view_events (rolling 24h) and view_counts (cumulative).
// ═══════════════════════════════════════════════════════════════
async function trackView(env, slug) {
  try {
    // Bucket by hour: "2026-04-03T00"
    const bucket = new Date().toISOString().slice(0, 13);
    await env.DB.batch([
      // Hourly bucket for rolling 24h
      env.DB.prepare(
        `INSERT INTO view_events (slug, hour_bucket, views) VALUES (?, ?, 1)
         ON CONFLICT(slug, hour_bucket) DO UPDATE SET views = views + 1`
      ).bind(slug, bucket),
      // Keep lifetime total
      env.DB.prepare(
        `INSERT INTO view_counts (slug, views_24h, views_total, last_reset) VALUES (?, 0, 1, datetime('now'))
         ON CONFLICT(slug) DO UPDATE SET views_total = views_total + 1`
      ).bind(slug),
    ]);
  } catch (e) {
    // Non-critical — don't break page loads
  }
}

// ═══════════════════════════════════════════════════════════════
// SECTION: /health — Site Health Dashboard
// ═══════════════════════════════════════════════════════════════
async function healthPage(env) {
  try {
    const [pendingRes, fixedTodayRes, unfixableRes, lastScanRes, pendingRowsRes, recentLogsRes] = await Promise.all([
      env.DB.prepare("SELECT COUNT(*) as cnt FROM broken_links WHERE status='pending'").first(),
      env.DB.prepare("SELECT COUNT(*) as cnt FROM broken_links WHERE status='fixed' AND date(fixed_at)=date('now')").first(),
      env.DB.prepare("SELECT COUNT(*) as cnt FROM broken_links WHERE status='unfixable'").first(),
      env.DB.prepare("SELECT scanned_at FROM link_scan_log ORDER BY id DESC LIMIT 1").first(),
      env.DB.prepare("SELECT source_slug, broken_href, suggested_slug, status, detected_at FROM broken_links WHERE status='pending' ORDER BY detected_at DESC LIMIT 100").all(),
      env.DB.prepare("SELECT scanned_at, total_links, broken_found, auto_fixed, unfixable FROM link_scan_log ORDER BY id DESC LIMIT 10").all(),
    ]);

    const pendingCount = pendingRes?.cnt ?? 0;
    const fixedToday = fixedTodayRes?.cnt ?? 0;
    const unfixableCount = unfixableRes?.cnt ?? 0;
    const lastScan = lastScanRes?.scanned_at ?? 'Never';
    const pendingRows = pendingRowsRes?.results ?? [];
    const recentLogs = recentLogsRes?.results ?? [];

    const pendingColor = pendingCount > 0 ? 'text-red-400' : 'text-green-400';

    const pendingTable = pendingRows.length === 0
      ? `<p class="text-gray-400 text-sm">No pending broken links.</p>`
      : `<div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 border-b border-surface-border">
                <th class="pb-2 pr-4">Source</th>
                <th class="pb-2 pr-4">Broken href</th>
                <th class="pb-2 pr-4">Suggested fix</th>
                <th class="pb-2">Detected</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-surface-border">
              ${pendingRows.map(r => `
                <tr class="text-gray-300">
                  <td class="py-2 pr-4"><a href="/${esc(r.source_slug)}" class="text-accent hover:underline">/${esc(r.source_slug)}</a></td>
                  <td class="py-2 pr-4 text-red-400 font-mono text-xs">${esc(r.broken_href)}</td>
                  <td class="py-2 pr-4 text-green-400 font-mono text-xs">${r.suggested_slug ? esc(r.suggested_slug) : '—'}</td>
                  <td class="py-2 text-gray-500 text-xs">${esc(r.detected_at ?? '')}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>`;

    const scanLogTable = recentLogs.length === 0
      ? `<p class="text-gray-400 text-sm">No scans yet.</p>`
      : `<div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 border-b border-surface-border">
                <th class="pb-2 pr-4">Scanned at</th>
                <th class="pb-2 pr-4">Total links</th>
                <th class="pb-2 pr-4">Broken</th>
                <th class="pb-2 pr-4">Auto-fixed</th>
                <th class="pb-2">Unfixable</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-surface-border">
              ${recentLogs.map(r => `
                <tr class="text-gray-300">
                  <td class="py-2 pr-4 text-xs text-gray-400">${esc(r.scanned_at ?? '')}</td>
                  <td class="py-2 pr-4">${r.total_links ?? 0}</td>
                  <td class="py-2 pr-4 ${(r.broken_found ?? 0) > 0 ? 'text-red-400' : 'text-gray-300'}">${r.broken_found ?? 0}</td>
                  <td class="py-2 pr-4 text-green-400">${r.auto_fixed ?? 0}</td>
                  <td class="py-2 text-yellow-400">${r.unfixable ?? 0}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>`;

    const body = `
      <h1 class="text-3xl font-bold text-white mb-8">Site Health</h1>

      <!-- Stat cards -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10">
        <div class="bg-surface-card border border-surface-border rounded-xl p-5">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">404 Links</div>
          <div class="text-3xl font-bold ${pendingColor}">${pendingCount}</div>
          <div class="text-xs text-gray-500 mt-1">pending fix</div>
        </div>
        <div class="bg-surface-card border border-surface-border rounded-xl p-5">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Auto-fixed today</div>
          <div class="text-3xl font-bold text-green-400">${fixedToday}</div>
          <div class="text-xs text-gray-500 mt-1">links corrected</div>
        </div>
        <div class="bg-surface-card border border-surface-border rounded-xl p-5">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Unfixable</div>
          <div class="text-3xl font-bold ${unfixableCount > 0 ? 'text-yellow-400' : 'text-gray-400'}">${unfixableCount}</div>
          <div class="text-xs text-gray-500 mt-1">no match found</div>
        </div>
        <div class="bg-surface-card border border-surface-border rounded-xl p-5">
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Last scan</div>
          <div class="text-sm font-medium text-gray-300 mt-2">${esc(lastScan)}</div>
          <div class="text-xs text-gray-500 mt-1">top of each hour</div>
        </div>
      </div>

      <!-- Broken links table -->
      <div class="bg-surface-card border border-surface-border rounded-xl p-6 mb-6">
        <h2 class="text-lg font-semibold text-white mb-4">Pending Broken Links</h2>
        ${pendingTable}
      </div>

      <!-- Scan log -->
      <div class="bg-surface-card border border-surface-border rounded-xl p-6">
        <h2 class="text-lg font-semibold text-white mb-4">Recent Scan Log</h2>
        ${scanLogTable}
      </div>
    `;

    const html = layout({
      title: 'Site Health | gab.ae',
      description: 'Internal site health dashboard — broken link scanner and auto-fix log.',
      canonical: 'https://gab.ae/health',
      body,
    });

    return new Response(html, {
      headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' },
    });
  } catch (e) {
    return new Response(`Health page error: ${e.message}`, { status: 500 });
  }
}

async function pruneOldViews(env) {
  try {
    const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 13);
    await env.DB.prepare(`DELETE FROM view_events WHERE hour_bucket < ?`).bind(cutoff).run();
    console.log('🧹 Pruned old view events');
  } catch (e) {
    console.log(`❌ View prune error: ${e.message}`);
  }
}

async function resourcesPage(env) {
  const APEX_GUIDES = [
    { slug: 'capital-markets-wealth-guide-2026', name: 'Capital Markets & Wealth', icon: '📊', desc: 'Investment analysis, market data, portfolio tools, and financial calculators.' },
    { slug: 'software-ai-infrastructure-guide-2026', name: 'Software & AI Infrastructure', icon: '⚡', desc: 'Developer tools, AI resources, performance benchmarks, and tech utilities.' },
    { slug: 'digital-media-creator-economy-guide-2026', name: 'Digital Media & Creator Economy', icon: '🎮', desc: 'Content creation tools, gaming resources, and digital media guides.' },
    { slug: 'human-optimization-health-guide-2026', name: 'Human Optimization & Health', icon: '❤️', desc: 'Health calculators, body metrics, fitness tools, and wellness guides.' },
    { slug: 'fine-arts-design-creative-guide-2026', name: 'Fine Arts, Design & Creative', icon: '🎨', desc: 'Creative tools, design resources, and artistic references.' },
    { slug: 'global-mobility-geo-arbitrage-guide-2026', name: 'Global Mobility & Geo-Arbitrage', icon: '🌍', desc: 'Travel tools, visa indexes, cost of living data, and nomad resources.' },
    { slug: 'education-knowledge-commerce-guide-2026', name: 'Education & Knowledge Commerce', icon: '📚', desc: 'Academic calculators, learning tools, and educational references.' },
    { slug: 'real-estate-hospitality-guide-2026', name: 'Real Estate & Hospitality', icon: '🏠', desc: 'Property tools, mortgage calculators, and home improvement guides.' },
    { slug: 'interpersonal-dynamics-intimacy-guide-2026', name: 'Interpersonal Dynamics & Intimacy', icon: '💜', desc: 'Relationship guides, sexual health tools, and interpersonal resources.' },
    { slug: 'ecommerce-supply-chain-guide-2026', name: 'E-Commerce & Supply Chain', icon: '🛒', desc: 'Business tools, career resources, and e-commerce guides.' },
  ];

  // Get page counts per apex
  let pageCounts = {};
  try {
    const { results } = await env.DB.prepare(
      "SELECT apex_slug, COUNT(*) as cnt FROM tracked_pages WHERE status='active' GROUP BY apex_slug"
    ).all();
    for (const r of results) pageCounts[r.apex_slug] = r.cnt;
  } catch {}

  // Get latest 10 LLM-generated pages
  let latestPages = [];
  try {
    const { results } = await env.DB.prepare(
      "SELECT slug, title, category, page_type, keyword_volume, created_at FROM pages WHERE status='live' AND engine IN ('llm-haiku','llm-gemini','llm-gemini-pro','llm-sonnet','seed') ORDER BY created_at DESC LIMIT 10"
    ).all();
    latestPages = results || [];
  } catch {}

  // Get most popular pages (rolling 24h from view_events)
  const cutoff24h = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 13);
  let popularPages = [];
  try {
    const { results } = await env.DB.prepare(
      `SELECT ve.slug, SUM(ve.views) as views_24h, p.title, p.category, p.page_type, p.keyword_volume, p.created_at
       FROM view_events ve
       JOIN pages p ON ve.slug = p.slug
       WHERE ve.hour_bucket >= ? AND p.status = 'live'
       GROUP BY ve.slug
       ORDER BY views_24h DESC LIMIT 10`
    ).bind(cutoff24h).all();
    popularPages = results || [];
  } catch {}
  
  // Also check news views (rolling 24h)
  try {
    const { results } = await env.DB.prepare(
      `SELECT ve.slug, SUM(ve.views) as views_24h, n.title, n.category, 'news' as page_type, 0 as keyword_volume, n.published_at as created_at
       FROM view_events ve
       JOIN news n ON ('news/' || n.slug) = ve.slug
       WHERE ve.hour_bucket >= ? AND n.status = 'live'
       GROUP BY ve.slug
       ORDER BY views_24h DESC LIMIT 10`
    ).bind(cutoff24h).all();
    popularPages = [...popularPages, ...(results || [])].sort((a, b) => b.views_24h - a.views_24h).slice(0, 10);
  } catch {}

  // Get recently updated pages (any update — reworks, edits, etc.)
  let reworkedPages = [];
  try {
    const { results } = await env.DB.prepare(
      `SELECT slug, title, category, page_type, keyword_volume, updated_at as created_at
       FROM pages 
       WHERE status = 'live' AND quality = 'llm-sonnet'
       ORDER BY updated_at DESC LIMIT 10`
    ).all();
    reworkedPages = results || [];
  } catch {}

  const guidesHtml = APEX_GUIDES.map(g => {
    const count = pageCounts[g.slug] || 0;
    return `
      <a href="/${g.slug}" class="group block bg-surface border border-surface-border rounded-xl p-6 hover:border-accent/30 transition-all">
        <div class="text-3xl mb-3">${g.icon}</div>
        <h2 class="text-lg font-bold text-white group-hover:text-accent transition-colors mb-2">${g.name}</h2>
        <p class="text-sm text-gray-400 mb-3">${g.desc}</p>
        ${count > 0 ? `<span class="text-xs text-gray-500">${count} pages</span>` : ''}
      </a>`;
  }).join('');

  function renderPageList(pages, showViews = false) {
    return pages.map(p => {
      const typeIcons = { educational: '📖', calculator: '🧮', listicle: '📋', comparison: '⚖️' };
      const icon = typeIcons[p.page_type] || '📄';
      const date = p.created_at ? new Date(p.created_at + 'Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
      const cleanTitle = (p.title || '').replace(' | gab.ae', '');
      const rightStat = showViews && p.views_24h
        ? `<span class="text-xs text-accent font-medium">${p.views_24h.toLocaleString()} views</span>`
        : p.keyword_volume ? `<span class="text-xs text-gray-600">${p.keyword_volume.toLocaleString()} vol</span>` : '';
      return `
        <a href="/${p.slug}" class="group flex items-center gap-3 bg-surface border border-surface-border rounded-lg px-4 py-3 hover:border-accent/30 transition-all">
          <span class="text-lg">${icon}</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-white group-hover:text-accent transition-colors truncate">${esc(cleanTitle)}</div>
            <div class="text-xs text-gray-500">${p.category || ''} · ${p.page_type || ''} · ${date}</div>
          </div>
          ${rightStat}
        </a>`;
    }).join('');
  }

  const hasPopular = popularPages.length > 0;
  const hasReworked = reworkedPages.length > 0;
  const latestHtml = (latestPages.length > 0 || hasPopular || hasReworked) ? `
    <div class="mb-8">
      <div class="flex gap-2 mb-4 flex-wrap">
        <button onclick="switchTab('recent',this)" class="tab-btn px-4 py-1.5 rounded-full text-sm font-medium bg-accent text-white border border-surface-border transition-all">🆕 Recently Published</button>
        <button onclick="switchTab('popular',this)" class="tab-btn px-4 py-1.5 rounded-full text-sm font-medium bg-surface text-gray-400 border border-surface-border transition-all">🔥 Most Popular (24h)</button>
        <button onclick="switchTab('updated',this)" class="tab-btn px-4 py-1.5 rounded-full text-sm font-medium bg-surface text-gray-400 border border-surface-border transition-all">✨ Recently Updated</button>
      </div>
      <script>
      function switchTab(id, btn) {
        document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('bg-accent','text-white'); b.classList.add('bg-surface','text-gray-400'); });
        document.getElementById('tab-' + id).style.display = 'block';
        btn.classList.add('bg-accent','text-white');
        btn.classList.remove('bg-surface','text-gray-400');
      }
      </script>
      <div id="tab-recent" class="tab-content space-y-3">
        ${latestPages.length > 0 ? renderPageList(latestPages) : '<p class="text-gray-500 text-sm">No pages yet — check back soon.</p>'}
      </div>
      <div id="tab-popular" class="tab-content space-y-3" style="display:none">
        ${hasPopular ? renderPageList(popularPages, true) : '<p class="text-gray-500 text-sm">No view data yet — analytics sync coming soon.</p>'}
      </div>
      <div id="tab-updated" class="tab-content space-y-3" style="display:none">
        ${hasReworked ? renderPageList(reworkedPages) : '<p class="text-gray-500 text-sm">No reworked pages yet — top-traffic pages are automatically upgraded every 6 hours.</p>'}
      </div>
    </div>` : '';

  const body = `
    <div class="max-w-4xl mx-auto">
      <h1 class="text-3xl font-black text-white mb-2">Resources</h1>
      <p class="text-gray-400 mb-8">In-depth guides, tools, and data across ${APEX_GUIDES.length} knowledge hubs.</p>
      ${latestHtml}
      <h2 class="text-xl font-bold text-white mb-4 mt-12">Knowledge Hubs</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        ${guidesHtml}
      </div>
    </div>`;

  const html = layout({
    title: 'Resources | gab.ae',
    description: 'Free tools, calculators, expert guides, and data across finance, tech, health, travel, gaming, education, and more. 10 knowledge hubs with thousands of pages updated daily.',
    canonical: 'https://gab.ae/resources',
    body,
  });
  return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
}

function notFound(env, path) {
  if (env && path) {
    try {
      env.DB.prepare(
        `INSERT INTO not_found_log (path, count, last_seen) VALUES (?, 1, datetime('now'))
         ON CONFLICT(path) DO UPDATE SET count = count + 1, last_seen = datetime('now')`
      ).bind(path).run();
    } catch {}
  }
  const html = layout({
    title: '404 — Not Found',
    description: 'Page not found',
    canonical: 'https://gab.ae/404',
    body: `
      <div class="text-center py-20">
        <h1 class="text-6xl font-bold text-white mb-4">404</h1>
        <p class="text-gray-400 text-lg">This page doesn't exist yet.</p>
        <a href="/" class="inline-block mt-6 px-6 py-3 bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors">Go Home</a>
      </div>`,
  });
  return new Response(html, { status: 404, headers: { 'content-type': 'text/html;charset=UTF-8' } });
}

// ═══════════════════════════════════════════════════════════════
// SECTION: API Endpoints (JSON responses for internal tools)
// ═══════════════════════════════════════════════════════════════
async function siteTreeAPI(env) {
  const headers = {
    'content-type': 'application/json',
    'cache-control': 'public, max-age=600',
    'access-control-allow-origin': '*',
  };

  const APEX_META = {
    'capital-markets-wealth-guide-2026': { name: 'Capital Markets & Wealth', icon: '📊' },
    'software-ai-infrastructure-guide-2026': { name: 'Software & AI Infrastructure', icon: '⚡' },
    'digital-media-creator-economy-guide-2026': { name: 'Digital Media & Creator Economy', icon: '🎮' },
    'human-optimization-health-guide-2026': { name: 'Human Optimization & Health', icon: '❤️' },
    'fine-arts-design-creative-guide-2026': { name: 'Fine Arts, Design & Creative', icon: '🎨' },
    'global-mobility-geo-arbitrage-guide-2026': { name: 'Global Mobility & Geo-Arbitrage', icon: '🌍' },
    'education-knowledge-commerce-guide-2026': { name: 'Education & Knowledge Commerce', icon: '📚' },
    'real-estate-hospitality-guide-2026': { name: 'Real Estate & Hospitality', icon: '🏠' },
    'interpersonal-dynamics-intimacy-guide-2026': { name: 'Interpersonal Dynamics & Intimacy', icon: '💜' },
    'ecommerce-supply-chain-guide-2026': { name: 'E-Commerce & Supply Chain', icon: '🛒' },
  };

  try {
    const { results } = await env.DB.prepare(
      `SELECT tp.apex_slug, tp.cluster, tp.domain, tp.path, tp.title
       FROM tracked_pages tp
       WHERE tp.apex_slug IS NOT NULL
       ORDER BY tp.apex_slug, tp.cluster, tp.domain, tp.path`
    ).all();

    // Group: apex → cluster → pages
    const apexMap = {};
    for (const row of results) {
      if (!apexMap[row.apex_slug]) {
        const meta = APEX_META[row.apex_slug] || { name: row.apex_slug, icon: '📄' };
        apexMap[row.apex_slug] = { slug: row.apex_slug, name: meta.name, icon: meta.icon, clusterMap: {} };
      }
      const apex = apexMap[row.apex_slug];
      const clusterName = row.cluster || 'uncategorized';
      if (!apex.clusterMap[clusterName]) {
        apex.clusterMap[clusterName] = [];
      }
      apex.clusterMap[clusterName].push({ domain: row.domain, path: row.path, title: row.title || `${row.domain}${row.path}` });
    }

    // Convert to array format — put sub-guides first, then sort rest by page count
    const apexes = Object.values(apexMap).map(a => {
      const clusters = Object.entries(a.clusterMap).map(([name, pages]) => ({ name, pages }));
      clusters.sort((x, y) => {
        if (x.name === 'sub-guide') return -1;
        if (y.name === 'sub-guide') return 1;
        return y.pages.length - x.pages.length;
      });
      return { slug: a.slug, name: a.name, icon: a.icon, clusters };
    });

    return new Response(JSON.stringify({ apexes }), { headers });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers });
  }
}

async function seoDashboardAPI(env) {
  const headers = {
    'content-type': 'application/json',
    'cache-control': 'public, max-age=300',
    'access-control-allow-origin': '*',
  };
  try {
    // Total pages and domains
    const totalResult = await env.DB.prepare(
      "SELECT COUNT(*) as total_pages, COUNT(DISTINCT domain) as total_domains FROM tracked_pages WHERE apex_slug IS NOT NULL"
    ).first();

    // Pages with metrics
    const metricsResult = await env.DB.prepare(
      "SELECT COUNT(DISTINCT pm.domain || pm.path) as total FROM page_metrics pm INNER JOIN tracked_pages tp ON pm.domain = tp.domain AND pm.path = tp.path WHERE tp.apex_slug IS NOT NULL"
    ).first();

    // Open issues
    const issuesResult = await env.DB.prepare(
      "SELECT COUNT(*) as total FROM seo_issues WHERE status != 'resolved'"
    ).first();

    // Clusters per apex
    const clusterRows = await env.DB.prepare(
      "SELECT apex_slug, cluster, COUNT(*) as pages FROM tracked_pages WHERE apex_slug IS NOT NULL GROUP BY apex_slug, cluster ORDER BY apex_slug, pages DESC"
    ).all();

    // Top pages by sessions per apex
    const topPagesRows = await env.DB.prepare(
      `SELECT tp.apex_slug, pm.domain, pm.path, MAX(pm.ga_sessions) as sessions
       FROM page_metrics pm
       INNER JOIN tracked_pages tp ON pm.domain = tp.domain AND pm.path = tp.path
       WHERE tp.apex_slug IS NOT NULL AND pm.ga_sessions > 0
       GROUP BY tp.apex_slug, pm.domain, pm.path
       ORDER BY tp.apex_slug, sessions DESC`
    ).all();

    // Domains per apex
    const domainRows = await env.DB.prepare(
      "SELECT apex_slug, domain, COUNT(*) as pages FROM tracked_pages WHERE apex_slug IS NOT NULL GROUP BY apex_slug, domain ORDER BY apex_slug, pages DESC"
    ).all();

    // GSC aggregate per apex
    const gscApexRows = await env.DB.prepare(
      `SELECT tp.apex_slug, 
              SUM(pm.gsc_impressions) as impressions, 
              SUM(pm.gsc_clicks) as clicks,
              CASE WHEN SUM(pm.gsc_impressions) > 0 THEN ROUND(CAST(SUM(pm.gsc_clicks) AS REAL) / SUM(pm.gsc_impressions) * 100, 2) ELSE 0 END as ctr,
              ROUND(AVG(CASE WHEN pm.gsc_position > 0 THEN pm.gsc_position END), 1) as avg_position
       FROM page_metrics pm
       INNER JOIN tracked_pages tp ON pm.domain = tp.domain AND pm.path = tp.path
       WHERE tp.apex_slug IS NOT NULL
       GROUP BY tp.apex_slug`
    ).all();

    // GA aggregate per apex
    const gaApexRows = await env.DB.prepare(
      `SELECT tp.apex_slug,
              SUM(pm.ga_sessions) as sessions,
              SUM(pm.ga_users) as users,
              SUM(pm.ga_pageviews) as pageviews,
              ROUND(AVG(CASE WHEN pm.ga_bounce_rate > 0 THEN pm.ga_bounce_rate END) * 100, 1) as avg_bounce,
              ROUND(AVG(CASE WHEN pm.ga_avg_duration > 0 THEN pm.ga_avg_duration END), 0) as avg_duration
       FROM page_metrics pm
       INNER JOIN tracked_pages tp ON pm.domain = tp.domain AND pm.path = tp.path
       WHERE tp.apex_slug IS NOT NULL
       GROUP BY tp.apex_slug`
    ).all();

    // GSC per domain
    const gscDomainRows = await env.DB.prepare(
      `SELECT pm.domain,
              SUM(pm.gsc_impressions) as impressions, 
              SUM(pm.gsc_clicks) as clicks,
              CASE WHEN SUM(pm.gsc_impressions) > 0 THEN ROUND(CAST(SUM(pm.gsc_clicks) AS REAL) / SUM(pm.gsc_impressions) * 100, 2) ELSE 0 END as ctr
       FROM page_metrics pm
       INNER JOIN tracked_pages tp ON pm.domain = tp.domain AND pm.path = tp.path
       WHERE tp.apex_slug IS NOT NULL
       GROUP BY pm.domain
       ORDER BY impressions DESC`
    ).all();

    // GA per domain
    const gaDomainRows = await env.DB.prepare(
      `SELECT pm.domain,
              SUM(pm.ga_sessions) as sessions,
              SUM(pm.ga_users) as users,
              SUM(pm.ga_pageviews) as pageviews
       FROM page_metrics pm
       INNER JOIN tracked_pages tp ON pm.domain = tp.domain AND pm.path = tp.path
       WHERE tp.apex_slug IS NOT NULL
       GROUP BY pm.domain
       ORDER BY sessions DESC`
    ).all();

    // Network totals
    const networkGsc = await env.DB.prepare(
      `SELECT SUM(gsc_impressions) as impressions, SUM(gsc_clicks) as clicks FROM page_metrics`
    ).first();
    const networkGa = await env.DB.prepare(
      `SELECT SUM(ga_sessions) as sessions, SUM(ga_users) as users, SUM(ga_pageviews) as pageviews FROM page_metrics`
    ).first();

    // Top pages network-wide (exclude homepages and ali)
    const topPagesNetwork = await env.DB.prepare(
      `SELECT pm.domain, pm.path, pm.ga_sessions as sessions, pm.ga_pageviews as pageviews, pm.ga_bounce_rate as bounce, pm.ga_avg_duration as duration
       FROM page_metrics pm
       WHERE pm.path != '/' 
         AND pm.domain NOT LIKE '%ali%'
         AND pm.ga_sessions > 0
         AND pm.date >= date('now', '-2 days')
       ORDER BY pm.ga_sessions DESC
       LIMIT 25`
    ).all();

    // Build apex map
    const apexNames = {
      'capital-markets-wealth-guide-2026': 'Capital Markets & Wealth',
      'software-ai-infrastructure-guide-2026': 'Software & AI Infrastructure',
      'digital-media-creator-economy-guide-2026': 'Digital Media & Creator Economy',
      'interpersonal-dynamics-intimacy-guide-2026': 'Interpersonal Dynamics & Intimacy',
      'ecommerce-supply-chain-guide-2026': 'E-Commerce & Supply Chain',
      'real-estate-hospitality-guide-2026': 'Real Estate & Hospitality',
      'human-optimization-health-guide-2026': 'Human Optimization & Health',
      'fine-arts-design-creative-guide-2026': 'Fine Arts, Design & Creative',
      'education-knowledge-commerce-guide-2026': 'Education & Knowledge Commerce',
      'global-mobility-geo-arbitrage-guide-2026': 'Global Mobility & Geo-Arbitrage',
    };

    const apexMap = {};
    for (const slug of Object.keys(apexNames)) {
      apexMap[slug] = { slug, name: apexNames[slug], pages: 0, domains: [], clusters: [], top_pages: [], gsc: {}, ga: {} };
    }

    // Fill GSC per apex
    for (const r of (gscApexRows?.results || [])) {
      if (apexMap[r.apex_slug]) {
        apexMap[r.apex_slug].gsc = { impressions: r.impressions || 0, clicks: r.clicks || 0, ctr: r.ctr || 0, avg_position: r.avg_position || 0 };
      }
    }

    // Fill GA per apex
    for (const r of (gaApexRows?.results || [])) {
      if (apexMap[r.apex_slug]) {
        apexMap[r.apex_slug].ga = { sessions: r.sessions || 0, users: r.users || 0, pageviews: r.pageviews || 0, avg_bounce: r.avg_bounce || 0, avg_duration: r.avg_duration || 0 };
      }
    }

    // Fill clusters
    for (const r of (clusterRows?.results || [])) {
      if (apexMap[r.apex_slug]) {
        apexMap[r.apex_slug].clusters.push({ name: r.cluster, pages: r.pages });
        apexMap[r.apex_slug].pages += r.pages;
      }
    }

    // Fill domains
    for (const r of (domainRows?.results || [])) {
      if (apexMap[r.apex_slug] && !apexMap[r.apex_slug].domains.includes(r.domain)) {
        apexMap[r.apex_slug].domains.push(r.domain);
      }
    }

    // Fill top pages (limit 5 per apex)
    const topPageCounts = {};
    for (const r of (topPagesRows?.results || [])) {
      if (apexMap[r.apex_slug]) {
        topPageCounts[r.apex_slug] = (topPageCounts[r.apex_slug] || 0) + 1;
        if (topPageCounts[r.apex_slug] <= 5) {
          apexMap[r.apex_slug].top_pages.push({ domain: r.domain, path: r.path, sessions: r.sessions });
        }
      }
    }

    const apexes = Object.values(apexMap).sort((a, b) => b.pages - a.pages);

    // Build domain metrics map
    const domainMetrics = {};
    for (const r of (gscDomainRows?.results || [])) {
      domainMetrics[r.domain] = { ...(domainMetrics[r.domain] || {}), gsc_impressions: r.impressions || 0, gsc_clicks: r.clicks || 0, gsc_ctr: r.ctr || 0 };
    }
    for (const r of (gaDomainRows?.results || [])) {
      domainMetrics[r.domain] = { ...(domainMetrics[r.domain] || {}), ga_sessions: r.sessions || 0, ga_users: r.users || 0, ga_pageviews: r.pageviews || 0 };
    }

    const response = {
      summary: {
        total_pages: totalResult?.total_pages || 0,
        total_domains: totalResult?.total_domains || 0,
        total_with_metrics: metricsResult?.total || 0,
        total_issues: issuesResult?.total || 0,
        network_gsc: { impressions: networkGsc?.impressions || 0, clicks: networkGsc?.clicks || 0 },
        network_ga: { sessions: networkGa?.sessions || 0, users: networkGa?.users || 0, pageviews: networkGa?.pageviews || 0 },
      },
      apexes,
      domain_metrics: domainMetrics,
      top_pages_network: (topPagesNetwork?.results || []),
      generated_at: new Date().toISOString(),
    };

    return new Response(JSON.stringify(response), { headers });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers });
  }
}

// esc imported from templates/layout.js
