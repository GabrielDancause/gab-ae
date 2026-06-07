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
 * CRON (scheduled handler, runs every 5 minutes):
 *   - llmNews()          → Generate 1 news article from RSS (every tick)
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

import { siteLayout, esc } from './templates/site-layout.js';
// layout.js and nookie-layout.js replaced by site-layout.js (Phase 5)
import { renderCalculator } from './engines/calculator.js';
import { renderArticle } from './render-engine.js';
import { getSiteById, SITES } from './sites.js';
import { renderChangelog } from './engines/changelog.js';
import { upgradeTrigger } from './upgrade-trigger.js';
import { generateArticle } from './llm-engine.js';
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

const gabAeSite   = getSiteById('gab-ae');
const nookieSite  = getSiteById('thenookienook');
const parisSite      = getSiteById('paris');
const toolstackSite  = getSiteById('toolstack');

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
  // SECTION: Cron Scheduler (runs every 5 minutes via wrangler.toml)
  // Each pipeline has its own frequency gate inside.
  // ═══════════════════════════════════════════════════════════════
  async scheduled(event, env, ctx) {
    const nowMin = new Date().getUTCMinutes();

    // Article generation — Nookie Nook only (gab.ae pivoted away from news 2026-05-09)
    const nookieSiteForCron = getSiteById('thenookienook');
    if (nookieSiteForCron && nowMin % nookieSiteForCron.cronModulo === nookieSiteForCron.cronOffset) {
      try {
        await generateArticle(env, nookieSiteForCron);
      } catch (e) {
        console.log(`❌ [thenookienook] generateArticle error: ${e.message}`);
      }
    }

    // Prune view events older than 24h (every hour)
    const nowHour = new Date().getUTCHours();
    if (nowMin < 5) {
      await pruneOldViews(env);
    }

    // PAUSED: Rework top-traffic pages (Gemini 2.5 Pro too expensive — paused 2026-04-09)
    // Rewrites top-viewed LLM-generated pages with higher-quality content using Gemini 2.5 Pro.
    // Runs once daily at 4 AM UTC. To re-enable, uncomment the block below and redeploy.
    // if (nowHour === 4 && nowMin < 5) {
    //   try {
    //     await llmRework(env);
    //   } catch (e) {
    //     console.log(`❌ LLM Rework error: ${e.message}`);
    //   }
    // }

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
    const host = url.hostname;
    const path = url.pathname.replace(/\/$/, '') || '/';

    // ─── The Nookie Nook: hostname routing (thenookienook.com points here) ───
    const isNookieDomain = host === 'thenookienook.com' || host === 'www.thenookienook.com';
    if (isNookieDomain) {
      const nkPath = path || '/';
      if (nkPath === '/' || nkPath === '') return nookieIndex(env, '');
      const nkCatMatch = nkPath.match(/^\/category\/([a-z0-9-]+)$/);
      if (nkCatMatch) {
        const page = Math.max(1, parseInt(url.searchParams.get('page') || '1', 10));
        return nookieIndex(env, '', nkCatMatch[1], page);
      }
      const nkArticleMatch = nkPath.match(/^\/article\/([a-z0-9-]+)$/);
      if (nkArticleMatch) return nookieArticlePage(env, nkArticleMatch[1], '');
      if (nkPath === '/search') return nookieSearchPage(env, url.searchParams.get('q')?.trim() || '', '');
      if (nkPath === '/robots.txt') {
        return new Response(`User-agent: *\nAllow: /\n\nSitemap: https://thenookienook.com/sitemap.xml\n`, { headers: { 'content-type': 'text/plain' } });
      }
      if (nkPath === '/sitemap.xml') return nookieSitemap(env);
      // Fallback: 404 within nookie brand
      return new Response(siteLayout({ site: nookieSite, title: 'Page Not Found | The Nookie Nook', description: 'This page could not be found.', canonical: 'https://thenookienook.com/', basePath: '', body: '<p style="text-align:center;padding:80px 0;color:var(--nk-ink-light)">Page not found. <a href="/" style="color:var(--nk-accent)">Return home</a></p>' }), { status: 404, headers: { 'content-type': 'text/html;charset=UTF-8' } });
    }

    // Admin: trigger rework manually (secret path) — runs in background via waitUntil
    if (path === '/api/admin/rework' && request.method === 'POST') {
      ctx.waitUntil(llmRework(env).then(r => console.log('✅ Rework result:', JSON.stringify(r))).catch(e => console.log('❌ Rework error:', e.message)));
      return new Response(JSON.stringify({ message: 'Rework triggered in background — check logs' }), { headers: { 'content-type': 'application/json' } });
    }

    // Admin: trigger news generation manually
    if (path === '/api/admin/news' && request.method === 'POST') {
      const site = getSiteById(url.searchParams.get('site') || 'gab-ae');
      // sync=1 waits for result so caller can see output directly
      if (url.searchParams.get('sync') === '1') {
        const result = await generateArticle(env, site).catch(e => ({ error: e.message }));
        return new Response(JSON.stringify(result || { skipped: true }), { headers: { 'content-type': 'application/json' } });
      }
      ctx.waitUntil(generateArticle(env, site).then(r => console.log('✅ Result:', JSON.stringify(r))).catch(e => console.log('❌ Error:', e.message)));
      return new Response(JSON.stringify({ message: `${site.id} triggered in background — check logs` }), { headers: { 'content-type': 'application/json' } });
    }

    // Admin: debug RSS + filter pipeline for a site (no LLM, no DB write)
    if (path === '/api/admin/debug-feeds' && request.method === 'GET') {
      const siteId = url.searchParams.get('site') || 'paris';
      const debugSite = getSiteById(siteId);
      if (!debugSite) return new Response(JSON.stringify({ error: 'site not found' }), { status: 404, headers: { 'content-type': 'application/json' } });

      const slugRows = await env.DB.prepare('SELECT slug FROM news ORDER BY published_at DESC LIMIT 500').all();
      const existingSlugs = new Set(slugRows.results.map(r => r.slug));

      const allStories = [];
      const feedResults = await Promise.allSettled(debugSite.feeds.map(async ([name, feedUrl, hint]) => {
        try {
          const resp = await fetch(feedUrl, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(8000) });
          if (!resp.ok) return { name, error: `HTTP ${resp.status}` };
          const xml = await resp.text();
          const items = [];
          const parseOne = (block) => {
            const title = (block.match(/<title><!\[CDATA\[(.*?)\]\]>/) || block.match(/<title[^>]*>(.*?)<\/title>/) || [])[1] || '';
            const link  = (block.match(/<link[^>]+href=["']([^"']+)["']/) || block.match(/<link>(.*?)<\/link>/) || [])[1] || '';
            const desc  = (block.match(/<description><!\[CDATA\[(.*?)\]\]>/) || block.match(/<description>(.*?)<\/description>/) || [])[1] || '';
            if (title && link) items.push({ title: title.trim(), link: link.trim(), description: desc.replace(/<[^>]+>/g, '').trim(), source: name, hintCategory: hint });
          };
          let m;
          const ir = /<item>([\s\S]*?)<\/item>/g;
          const er = /<entry>([\s\S]*?)<\/entry>/g;
          while ((m = ir.exec(xml)) !== null) parseOne(m[1]);
          while ((m = er.exec(xml)) !== null) parseOne(m[1]);
          return { name, count: items.length, items: items.slice(0, 5) };
        } catch (e) { return { name, error: e.message }; }
      }));

      for (const r of feedResults) {
        if (r.status === 'fulfilled' && r.value.items) allStories.push(...r.value.items);
      }

      const filter = debugSite.filter;
      const candidates = allStories.filter(s => {
        if (existingSlugs.has(s.link)) return false;
        const text = (s.title + ' ' + s.description).toLowerCase();
        if (!filter) return true;
        if (filter.type === 'include') return filter.keywords.some(kw => text.includes(kw));
        if (filter.type === 'exclude') {
          if (filter.keywords.some(kw => text.includes(kw))) return false;
          try { const h = new URL(s.link).hostname; if (filter.paywallDomains?.some(d => h.includes(d))) return false; } catch {}
          return true;
        }
        return true;
      });

      return new Response(JSON.stringify({
        feeds: feedResults.map(r => r.status === 'fulfilled' ? { name: r.value.name, count: r.value.count, error: r.value.error } : { error: r.reason }),
        totalStories: allStories.length,
        candidates: candidates.length,
        sampleCandidates: candidates.slice(0, 5).map(s => ({ title: s.title, source: s.source })),
        slugPoolSize: existingSlugs.size,
      }, null, 2), { headers: { 'content-type': 'application/json' } });
    }

    // Admin: trigger nookie news generation manually (backward-compat alias)
    if (path === '/api/admin/nookie-news' && request.method === 'POST') {
      const result = await generateArticle(env, getSiteById('thenookienook')).catch(e => ({ error: e.message }));
      return new Response(JSON.stringify(result || { skipped: true }), { headers: { 'content-type': 'application/json' } });
    }

    // Shorts feed — today's tech + business articles for video generation
    if (path === '/api/shorts-feed') {
      const rows = await env.DB.prepare(`
        SELECT slug, title, lede, takeaways, key_stat, pull_quote, category, tags
        FROM news
        WHERE category IN ('tech', 'business')
        AND (site IS NULL OR site = '')
        AND status = 'live'
        AND published_at >= datetime('now', '-24 hours')
        ORDER BY published_at DESC
        LIMIT 15
      `).all();
      const articles = (rows.results || []).map(r => ({
        slug:       r.slug,
        title:      r.title,
        lede:       r.lede,
        takeaways:  r.takeaways  ? JSON.parse(r.takeaways)  : [],
        key_stat:   r.key_stat   ? JSON.parse(r.key_stat)   : null,
        pull_quote: r.pull_quote || null,
        category:   r.category,
        tags:       r.tags       ? JSON.parse(r.tags)       : [],
        url:        `https://gab.ae/news/${r.slug}`,
      }));
      return new Response(JSON.stringify(articles), {
        headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
      });
    }

    // Homepage — shorts grid
    if (path === '/') {
      return shortsHomepage(env);
    }

    // Videos page
    if (path === '/videos') {
      return videosPage(env);
    }

    // Session management page — /footage/session/[series] (unlisted, not in nav)
    if (path.startsWith('/footage/session/')) {
      const series = path.replace('/footage/session/', '').split('/')[0];
      if (series) return sessionPage(env, series);
    }

    // Public footage pages — /footage/[slug]
    if (path.startsWith('/footage/')) {
      const slug = path.replace('/footage/', '').split('/')[0];
      if (slug) return footagePage(env, slug);
    }

    // Vault — hidden page for private/raw footage preview (not linked from nav)
    if (path === '/vault' || path === '/vault/status' || path === '/vault/approve' || path.startsWith('/vault/review')) {
      const VAULT_KEY = env.VAULT_KEY || 'gabvault2026';
      const cookie = request.headers.get('Cookie') || '';
      const authed = cookie.split(';').some(c => c.trim() === `vk=${VAULT_KEY}`);
      if (!authed) {
        if (request.method === 'POST' && path === '/vault') {
          const form = await request.formData().catch(() => null);
          const key = form ? form.get('key') : null;
          if (key === VAULT_KEY) {
            return new Response(null, { status: 302, headers: {
              'Location': '/vault',
              'Set-Cookie': `vk=${VAULT_KEY}; Path=/; Max-Age=7776000; HttpOnly; SameSite=Strict`,
            }});
          }
          return vaultLoginPage(true);
        }
        return vaultLoginPage(false);
      }
      if (path === '/vault/status') return vaultStatusPage(env);
      if (path === '/vault/approve') return vaultApprovePage(env, request);
      if (path.startsWith('/vault/review/')) {
        const series = path.replace('/vault/review/', '').split('/')[0];
        return vaultReviewPage(env, series);
      }
      return vaultPage(env);
    }

    // Approve a processed clip → flip to live (appears on /videos)
    if (path === '/api/queue-youtube' && request.method === 'POST') {
      const { slug, ia_url, series } = await request.json().catch(() => ({}));
      if (!slug || !ia_url) return new Response(JSON.stringify({ error: 'missing slug or ia_url' }), { status: 400, headers: { 'content-type': 'application/json' } });
      await env.DB.prepare(
        "INSERT INTO yt_jobs (video_slug, series, ia_url, status) VALUES (?, ?, ?, 'queued')"
      ).bind(slug, series || '', ia_url).run();
      return new Response(JSON.stringify({ ok: true, slug }), { headers: { 'content-type': 'application/json' } });
    }

    if (path === '/api/approve-video' && request.method === 'POST') {
      const { slug } = await request.json().catch(() => ({}));
      if (!slug) return new Response('missing slug', { status: 400 });
      await env.DB.prepare(
        "UPDATE videos SET status='live', published_at=datetime('now') WHERE slug=? AND status='processed'"
      ).bind(slug).run();
      return new Response(JSON.stringify({ ok: true, slug }), { headers: { 'content-type': 'application/json' } });
    }

    // Thumbnail for a video (served from D1 blob)
    const vthumbMatch = path.match(/^\/vthumb\/([a-z0-9-]+)$/);
    if (vthumbMatch) {
      const row = await env.DB.prepare("SELECT thumb_b64 FROM videos WHERE slug = ?").bind(vthumbMatch[1]).first();
      if (!row?.thumb_b64) return new Response('Not found', { status: 404 });
      const bytes = Uint8Array.from(atob(row.thumb_b64), c => c.charCodeAt(0));
      return new Response(bytes, { headers: { 'content-type': 'image/jpeg', 'cache-control': 'public, max-age=86400' } });
    }

    // Thumbnail for a short (served from D1 blob)
    const thumbMatch = path.match(/^\/thumb\/([a-z0-9-]+)$/);
    if (thumbMatch) {
      const row = await env.DB.prepare("SELECT thumb_b64 FROM shorts WHERE slug = ?").bind(thumbMatch[1]).first();
      if (!row?.thumb_b64) return new Response('Not found', { status: 404 });
      const bytes = Uint8Array.from(atob(row.thumb_b64), c => c.charCodeAt(0));
      return new Response(bytes, { headers: { 'content-type': 'image/jpeg', 'cache-control': 'public, max-age=86400' } });
    }

    // Search page
    if (path === '/search') {
      const q = url.searchParams.get('q')?.trim() || '';
      return searchPage(env, q);
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

    if (path === '/api/library') {
      try {
        const vpsResp = await fetch('http://178.105.50.213:8765/library', { signal: AbortSignal.timeout(10000) });
        if (!vpsResp.ok) throw new Error(`VPS returned ${vpsResp.status}`);
        const data = await vpsResp.json();
        return new Response(JSON.stringify(data), {
          headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60' },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message, sessions: [] }), {
          status: 503,
          headers: { 'content-type': 'application/json' },
        });
      }
    }

    if (path === '/api/library/stats') {
      try {
        const vpsResp = await fetch('http://178.105.50.213:8765/library/stats', { signal: AbortSignal.timeout(5000) });
        if (!vpsResp.ok) throw new Error(`VPS returned ${vpsResp.status}`);
        const data = await vpsResp.json();
        return new Response(JSON.stringify(data), {
          headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60' },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), {
          status: 503,
          headers: { 'content-type': 'application/json' },
        });
      }
    }

    if (path === '/library') {
      return renderLibraryPage();
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
        // Rate limit: 1 request per 30s per IP
        const clientIP = request.headers.get('cf-connecting-ip') || request.headers.get('x-forwarded-for') || 'unknown';
        const RATE_LIMIT_SECONDS = 30;
        try {
          const rl = await env.DB.prepare(
            "SELECT last_request FROM rate_limits WHERE ip = ? AND endpoint = '/api/generate'"
          ).bind(clientIP).first();
          if (rl) {
            const elapsed = (Date.now() - new Date(rl.last_request).getTime()) / 1000;
            if (elapsed < RATE_LIMIT_SECONDS) {
              const retryAfter = Math.ceil(RATE_LIMIT_SECONDS - elapsed);
              return new Response(JSON.stringify({ error: 'Rate limited. Try again shortly.', retry_after: retryAfter }), {
                status: 429,
                headers: { 'content-type': 'application/json', 'retry-after': String(retryAfter) },
              });
            }
          }
          await env.DB.prepare(
            "INSERT INTO rate_limits (ip, endpoint, last_request) VALUES (?, '/api/generate', ?) ON CONFLICT(ip, endpoint) DO UPDATE SET last_request = excluded.last_request"
          ).bind(clientIP, new Date().toISOString()).run();
        } catch (e) {
          console.log(`⚠️ Rate limit check failed (non-blocking): ${e.message}`);
        }

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
      return new Response(`User-agent: *\nDisallow: /vault\nAllow: /\n\nSitemap: https://gab.ae/sitemap.xml\n`, {
        headers: { 'content-type': 'text/plain' },
      });
    }

    // Site health dashboard
    if (path === '/health') {
      if (url.searchParams.get('run') === '1') {
        ctx.waitUntil(scanAndFixLinks(env));
        return healthPage(env, true);
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

    // /news — news index (moved off homepage)
    if (path === '/news') {
      return newsIndex(env);
    }

    // News category
    const newsCatMatch = path.match(/^\/news\/category\/([a-z0-9-]+)$/);
    if (newsCatMatch) {
      const page = Math.max(1, parseInt(url.searchParams.get('page') || '1', 10));
      return newsIndex(env, newsCatMatch[1], page);
    }

    // News article
    const newsMatch = path.match(/^\/news\/([a-z0-9-]+)$/);
    if (newsMatch) {
      try {
        const article = await env.DB.prepare("SELECT * FROM news WHERE slug = ? AND status = 'live'").bind(newsMatch[1]).first();
        if (article) {
          ctx.waitUntil(trackView(env, 'news/' + newsMatch[1]));
          const html = renderArticle(article, getSiteById('gab-ae'));
          return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
        }
      } catch (e) {}
    }

    // ─── The Nookie Nook dev routes (at gab.ae/thenookienook) ───
    if (path === '/thenookienook' || path === '/thenookienook/') {
      return nookieIndex(env, '/thenookienook');
    }
    const nkDevCatMatch = path.match(/^\/thenookienook\/category\/([a-z0-9-]+)$/);
    if (nkDevCatMatch) {
      const page = Math.max(1, parseInt(url.searchParams.get('page') || '1', 10));
      return nookieIndex(env, '/thenookienook', nkDevCatMatch[1], page);
    }
    const nkDevArticleMatch = path.match(/^\/thenookienook\/article\/([a-z0-9-]+)$/);
    if (nkDevArticleMatch) return nookieArticlePage(env, nkDevArticleMatch[1], '/thenookienook');
    if (path === '/thenookienook/search') return nookieSearchPage(env, url.searchParams.get('q')?.trim() || '', '/thenookienook');
    if (path === '/thenookienook/sitemap.xml') return nookieSitemap(env);

    // ─── Paris Dispatch routes (at gab.ae/paris) ───
    if (path === '/paris' || path === '/paris/') {
      return siteIndex(env, parisSite, '/paris');
    }
    const parisDevCatMatch = path.match(/^\/paris\/category\/([a-z0-9-]+)$/);
    if (parisDevCatMatch) {
      const page = Math.max(1, parseInt(url.searchParams.get('page') || '1', 10));
      return siteIndex(env, parisSite, '/paris', parisDevCatMatch[1], page);
    }
    const parisDevArticleMatch = path.match(/^\/paris\/article\/([a-z0-9-]+)$/);
    if (parisDevArticleMatch) return siteArticlePage(env, parisSite, parisDevArticleMatch[1], '/paris');
    if (path === '/paris/search') return siteSearchPage(env, parisSite, url.searchParams.get('q')?.trim() || '', '/paris');
    if (path === '/paris/sitemap.xml') return siteSitemapXml(env, parisSite);
    if (path === '/paris/robots.txt') {
      return new Response(`User-agent: *\nAllow: /\n\nSitemap: https://gab.ae/paris/sitemap.xml\n`, { headers: { 'content-type': 'text/plain' } });
    }

    // ─── ToolStack routes (at gab.ae/toolstack) ───
    if (path === '/toolstack' || path === '/toolstack/') {
      return siteIndex(env, toolstackSite, '/toolstack');
    }
    const toolstackCatMatch = path.match(/^\/toolstack\/category\/([a-z0-9-]+)$/);
    if (toolstackCatMatch) {
      const page = Math.max(1, parseInt(url.searchParams.get('page') || '1', 10));
      return siteIndex(env, toolstackSite, '/toolstack', toolstackCatMatch[1], page);
    }
    const toolstackArticleMatch = path.match(/^\/toolstack\/article\/([a-z0-9-]+)$/);
    if (toolstackArticleMatch) return siteArticlePage(env, toolstackSite, toolstackArticleMatch[1], '/toolstack');
    if (path === '/toolstack/search') return siteSearchPage(env, toolstackSite, url.searchParams.get('q')?.trim() || '', '/toolstack');
    if (path === '/toolstack/sitemap.xml') return siteSitemapXml(env, toolstackSite);
    if (path === '/toolstack/robots.txt') {
      return new Response(`User-agent: *\nAllow: /\n\nSitemap: https://gab.ae/toolstack/sitemap.xml\n`, { headers: { 'content-type': 'text/plain' } });
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

      const html = siteLayout({ site: gabAeSite,
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

function renderLibraryPage() {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Footage Library — gab.ae</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { background: #0a0a0a; color: #e5e5e5; font-family: system-ui, sans-serif; }
    .card { background: #141414; border: 1px solid #222; border-radius: 12px; overflow: hidden; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
    .thumb { width: 100%; aspect-ratio: 9/16; object-fit: cover; background: #1a1a1a; }
    .thumb-wide { width: 100%; aspect-ratio: 16/9; object-fit: cover; background: #1a1a1a; }
    .score-bar { height: 3px; background: #222; border-radius: 2px; }
    .score-fill { height: 3px; border-radius: 2px; background: linear-gradient(90deg, #22c55e, #86efac); }
    .filter-btn { padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid #333; background: #141414; color: #999; cursor: pointer; transition: all .15s; }
    .filter-btn.active, .filter-btn:hover { background: #fff; color: #000; border-color: #fff; }
    .skeleton { background: linear-gradient(90deg, #1a1a1a 25%, #222 50%, #1a1a1a 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 8px; }
    @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
  </style>
</head>
<body class="min-h-screen">

  <!-- Header -->
  <div class="border-b border-[#222] px-6 py-4 flex items-center justify-between sticky top-0 z-10" style="background:#0a0a0aee;backdrop-filter:blur(12px)">
    <div class="flex items-center gap-3">
      <a href="/" class="text-gray-500 hover:text-white text-sm transition-colors">gab.ae</a>
      <span class="text-gray-700">/</span>
      <span class="text-white font-semibold">Footage Library</span>
    </div>
    <div id="stats" class="flex gap-4 text-xs text-gray-500"></div>
  </div>

  <!-- Filters -->
  <div class="px-6 py-4 flex flex-wrap gap-2 border-b border-[#1a1a1a]">
    <button class="filter-btn active" data-filter="all">All</button>
    <button class="filter-btn" data-filter="dji">DJI</button>
    <button class="filter-btn" data-filter="meta">Meta Glasses</button>
    <button class="filter-btn" data-filter="phone">Phone</button>
    <button class="filter-btn" data-filter="has_ali">Has Ali</button>
    <button class="filter-btn" data-filter="has_short">Has Short</button>
    <button class="filter-btn" data-filter="score_8">Score 8+</button>
  </div>

  <!-- Content -->
  <div class="px-6 py-6">
    <div id="loading" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
      ${Array(12).fill('<div class="skeleton" style="height:280px"></div>').join('')}
    </div>
    <div id="sessions" class="hidden space-y-8"></div>
    <div id="empty" class="hidden text-center py-20 text-gray-600">No clips match this filter.</div>
  </div>

  <script>
    let allSessions = [];
    let activeFilter = 'all';

    async function load() {
      const [libResp, statsResp] = await Promise.all([
        fetch('/api/library'),
        fetch('/api/library/stats'),
      ]);
      const { sessions } = await libResp.json();
      const stats = await statsResp.json();
      allSessions = sessions;

      document.getElementById('stats').innerHTML = \`
        <span>\${stats.total_clips} clips</span>
        <span class="text-gray-700">·</span>
        <span>\${stats.total_shorts} shorts</span>
        <span class="text-gray-700">·</span>
        <span>\${stats.processed_sessions}/\${stats.total_sessions} sessions done</span>
      \`;

      render();
    }

    function driveThumb(fileId, wide) {
      return \`https://drive.google.com/thumbnail?id=\${fileId}&sz=w400\`;
    }

    function driveLink(fileId) {
      return \`https://drive.google.com/file/d/\${fileId}/view\`;
    }

    function scoreColor(s) {
      if (s >= 8) return '#22c55e';
      if (s >= 5) return '#f59e0b';
      return '#6b7280';
    }

    function render() {
      const sessions = document.getElementById('sessions');
      const empty = document.getElementById('empty');
      document.getElementById('loading').classList.add('hidden');
      sessions.innerHTML = '';

      let anyVisible = false;

      for (const s of allSessions) {
        const clips = s.clips.filter(c => {
          if (activeFilter === 'dji') return c.device === 'dji';
          if (activeFilter === 'meta') return c.device === 'meta';
          if (activeFilter === 'phone') return c.device === 'phone';
          if (activeFilter === 'has_ali') return c.has_ali === 1;
          if (activeFilter === 'has_short') return !!c.short_drive_id;
          if (activeFilter === 'score_8') return c.short_score >= 8;
          return true;
        });
        if (!clips.length) continue;
        anyVisible = true;

        const date = s.started_at?.slice(0, 10) || '';
        const time = s.started_at?.slice(11, 16) || '';
        const dur = s.total_duration_seconds ? Math.round(s.total_duration_seconds / 60) + ' min' : '';
        const deviceLabel = { dji: 'DJI', meta: 'Meta Glasses', phone: 'Phone', unknown: 'Unknown' }[s.device] || s.device;

        sessions.innerHTML += \`
          <div class="session-block">
            <div class="flex items-center gap-3 mb-3">
              <span class="badge" style="background:#ffffff15;color:#aaa">\${deviceLabel}</span>
              <span class="text-sm font-semibold text-white">\${date} · \${time}</span>
              \${dur ? \`<span class="text-xs text-gray-500">\${dur}</span>\` : ''}
              \${s.activity ? \`<span class="text-xs text-gray-500 italic">\${s.activity}</span>\` : ''}
              \${s.has_ali ? \`<span class="badge" style="background:#7c3aed20;color:#a78bfa">Ali</span>\` : ''}
              \${s.processed_at ? \`<span class="badge" style="background:#16a34a20;color:#4ade80">Done</span>\` : \`<span class="badge" style="background:#d9770620;color:#fb923c">Processing</span>\`}
              <span class="text-xs text-gray-600">\${clips.length} clip\${clips.length > 1 ? 's' : ''}</span>
            </div>
            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
              \${clips.map(c => {
                const hasShort = !!c.short_drive_id;
                const tags = (c.ai_tags || []).slice(0, 3).join(', ');
                const dur = c.duration_seconds ? Math.round(c.duration_seconds) + 's' : '';
                return \`
                  <div class="card group">
                    <div class="relative overflow-hidden cursor-pointer" style="aspect-ratio:\${hasShort ? '9/16' : '16/9'}" onclick="window.open('\${c.youtube_url || (hasShort ? driveLink(c.short_drive_id) : (c.drive_file_id ? driveLink(c.drive_file_id) : '#'))}', '_blank')">
                      \${(c.short_drive_id || c.drive_file_id) ? \`
                        <img src="\${driveThumb(c.short_drive_id || c.drive_file_id)}"
                             class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                             onerror="this.style.display='none'">
                      \` : '<div class="w-full h-full bg-[#1a1a1a]"></div>'}
                      <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent"></div>
                      \${hasShort ? \`
                        <div class="absolute top-2 left-2 flex gap-1">
                          <span class="badge" style="background:#ffffff20;color:#fff;backdrop-filter:blur(4px)">SHORT</span>
                          \${c.youtube_url ? \`<span class="badge" style="background:#ff000080;color:#fff;backdrop-filter:blur(4px)">▶ YT</span>\` : ''}
                        </div>
                        \${c.short_score ? \`
                          <div class="absolute top-2 right-2 w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold" style="background:\${scoreColor(c.short_score)}25;color:\${scoreColor(c.short_score)};border:1px solid \${scoreColor(c.short_score)}50">
                            \${c.short_score}
                          </div>
                        \` : ''}
                      \` : ''}
                      \${c.has_ali ? \`<div class="absolute bottom-2 right-2"><span class="badge" style="background:#7c3aed30;color:#a78bfa;backdrop-filter:blur(4px)">Ali</span></div>\` : ''}
                      <div class="absolute bottom-2 left-2 text-[10px] text-gray-400">\${dur}</div>
                    </div>
                    <div class="p-2">
                      \${c.short_score ? \`
                        <div class="score-bar mb-1.5">
                          <div class="score-fill" style="width:\${c.short_score * 10}%;background:\${scoreColor(c.short_score)}"></div>
                        </div>
                      \` : ''}
                      \${tags ? \`<p class="text-[10px] text-gray-600 leading-tight line-clamp-2">\${tags}</p>\` : ''}
                      \${c.short_reason && c.short_score >= 5 ? \`<p class="text-[10px] text-gray-500 mt-1 leading-tight line-clamp-2 italic">\${c.short_reason}</p>\` : ''}
                      \${c.youtube_url ? \`<a href="\${c.youtube_url}" target="_blank" onclick="event.stopPropagation()" class="block mt-1.5 text-[10px] font-semibold text-red-400 hover:text-red-300 transition-colors">▶ Watch on YouTube</a>\` : ''}
                    </div>
                  </div>
                \`;
              }).join('')}
            </div>
          </div>
        \`;
      }

      sessions.classList.toggle('hidden', !anyVisible);
      empty.classList.toggle('hidden', anyVisible);
    }

    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        render();
      });
    });

    load();
  </script>
</body>
</html>`;
  return new Response(html, { headers: { 'content-type': 'text/html;charset=utf-8' } });
}

// ═══════════════════════════════════════════════════════════════
// SECTION: Page Handlers (full page builders called by router)
// Each returns a Response object with complete HTML.
// ═══════════════════════════════════════════════════════════════
async function searchPage(env, q) {
  let newsResults = [];
  let pageResults = [];

  if (q.length >= 2) {
    const pattern = `%${q.toLowerCase()}%`;
    try {
      const [nr, pr] = await Promise.all([
        env.DB.prepare(
          "SELECT slug, title, description, lede, category, published_at, image FROM news WHERE status='live' AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(category) LIKE ?) ORDER BY published_at DESC LIMIT 20"
        ).bind(pattern, pattern, pattern, pattern).all(),
        env.DB.prepare(
          "SELECT slug, title, description, category FROM pages WHERE status='live' AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(keyword) LIKE ?) ORDER BY title ASC LIMIT 6"
        ).bind(pattern, pattern, pattern).all(),
      ]);
      newsResults = nr?.results || [];
      pageResults = pr?.results || [];
    } catch (e) {
      console.log('❌ searchPage error:', e.message);
    }
  }

  const totalResults = newsResults.length + pageResults.length;

  const searchFormHtml = `
    <div style="padding:32px 0 28px;border-bottom:3px double var(--border)">
      <form method="GET" action="/search" style="display:flex;gap:10px;max-width:680px;margin:0 auto">
        <input
          type="search"
          name="q"
          value="${esc(q)}"
          placeholder="Search news, topics, categories…"
          autofocus
          style="flex:1;font-family:'DM Sans',sans-serif;font-size:16px;padding:12px 16px;border:2px solid var(--border);border-radius:4px;background:var(--paper);color:var(--ink);outline:none;transition:border-color 0.2s"
          onfocus="this.style.borderColor='var(--accent)'"
          onblur="this.style.borderColor='var(--border)'"
        >
        <button type="submit" style="font-family:'DM Sans',sans-serif;font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:12px 22px;background:var(--ink);color:#fff;border:none;border-radius:4px;cursor:pointer">Search</button>
      </form>
    </div>`;

  let resultsHtml = '';

  if (q.length >= 2) {
    if (totalResults === 0) {
      resultsHtml = `<p style="padding:48px 0;text-align:center;color:var(--ink-light);font-size:15px">No results found for <strong>"${esc(q)}"</strong> — try a different term.</p>`;
    } else {
      resultsHtml = `<p style="font-size:12px;letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-light);margin:24px 0 20px">${totalResults} result${totalResults !== 1 ? 's' : ''} for <strong style="color:var(--ink)">"${esc(q)}"</strong></p>`;

      if (newsResults.length > 0) {
        resultsHtml += `
          <div style="border-top:2px solid var(--ink);padding-top:16px;margin-bottom:24px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
              <span style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:var(--accent)">News Articles</span>
              <span style="font-size:12px;color:var(--ink-light)">${newsResults.length} found</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:0">
              ${newsResults.map(a => {
                const color = catColor(a.category);
                const label = catLabel(a.category);
                return `
                <div style="display:flex;gap:16px;padding:16px 0;border-bottom:1px solid var(--border-light);align-items:flex-start">
                  ${a.image ? `<a href="/news/${a.slug}" style="flex-shrink:0"><img src="${esc(a.image)}" alt="${esc(a.title)}" style="width:120px;height:68px;object-fit:cover;display:block" loading="lazy"></a>` : ''}
                  <div style="flex:1;min-width:0">
                    <div style="margin-bottom:6px"><span style="font-size:9px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#fff;background:${color};padding:2px 8px">${label}</span></div>
                    <a href="/news/${a.slug}" style="font-family:'Playfair Display',Georgia,serif;font-size:18px;font-weight:700;line-height:1.3;color:var(--ink);display:block;margin-bottom:5px">${esc(a.title)}</a>
                    ${(a.lede || a.description) ? `<p style="font-size:14px;color:var(--ink-mid);line-height:1.5;margin-bottom:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(a.lede || a.description)}</p>` : ''}
                    <span style="font-size:11px;color:var(--ink-light)">${timeAgo(a.published_at)}</span>
                  </div>
                </div>`;
              }).join('')}
            </div>
          </div>`;
      }

      if (pageResults.length > 0) {
        resultsHtml += `
          <div style="border-top:2px solid var(--ink);padding-top:16px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
              <span style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:var(--accent)">Tools & Guides</span>
              <span style="font-size:12px;color:var(--ink-light)">${pageResults.length} found</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
              ${pageResults.map(p => `
                <a href="/${p.slug}" style="display:block;padding:14px 16px;border:1px solid var(--border);border-radius:4px;transition:border-color 0.15s,background 0.15s" onmouseover="this.style.borderColor='var(--accent)';this.style.background='var(--paper-mid)'" onmouseout="this.style.borderColor='var(--border)';this.style.background='transparent'">
                  <div style="font-size:10px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:var(--ink-light);margin-bottom:5px">${esc(p.category || 'Guide')}</div>
                  <div style="font-family:'Playfair Display',Georgia,serif;font-size:16px;font-weight:700;line-height:1.3;color:var(--ink);margin-bottom:4px">${esc(p.title)}</div>
                  ${p.description ? `<p style="font-size:13px;color:var(--ink-mid);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(p.description)}</p>` : ''}
                </a>`).join('')}
            </div>
          </div>`;
      }
    }
  } else {
    // No query yet — show popular categories as suggestions
    resultsHtml = `
      <div style="padding:32px 0">
        <p style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:var(--ink-light);margin-bottom:16px">Browse by category</p>
        <div style="display:flex;flex-wrap:wrap;gap:10px">
          ${Object.entries(CAT_LABELS).map(([cat, label]) => `
            <a href="/search?q=${cat}" style="font-size:13px;font-weight:600;color:var(--ink);border:1px solid var(--border);border-radius:20px;padding:7px 18px;transition:background 0.15s,color 0.15s,border-color 0.15s" onmouseover="this.style.background='var(--ink)';this.style.color='#fff';this.style.borderColor='var(--ink)'" onmouseout="this.style.background='transparent';this.style.color='var(--ink)';this.style.borderColor='var(--border)'">${label}</a>
          `).join('')}
        </div>
      </div>`;
  }

  const body = `
    <div style="max-width:860px;margin:0 auto">
      ${searchFormHtml}
      ${resultsHtml}
    </div>`;

  const title = q ? `"${q}" — Search | GAB.AE` : 'Search | GAB.AE';
  const description = q
    ? `Search results for "${q}" on GAB.AE — news, tools, and guides.`
    : 'Search news, tools, and guides on GAB.AE.';

  return new Response(siteLayout({ site: gabAeSite,
    title,
    description,
    canonical: `https://gab.ae/search${q ? `?q=${encodeURIComponent(q)}` : ''}`,
    activeNav: 'search',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
}

// ═══════════════════════════════════════════════════════════════
async function vaultReviewPage(env, series) {
  let clips = [];
  let ytJobMap = {};
  try {
    const { results } = await env.DB.prepare(
      "SELECT slug, title, series, status, video_url, thumb_b64, tags FROM videos WHERE series=? ORDER BY slug ASC"
    ).bind(series).all();
    clips = results;
  } catch(e) {}
  try {
    const { results } = await env.DB.prepare(
      "SELECT video_slug, status, yt_url, yt_scheduled_at FROM yt_jobs WHERE video_slug IN (SELECT slug FROM videos WHERE series=?) ORDER BY id DESC"
    ).bind(series).all();
    for (const j of results) {
      if (!ytJobMap[j.video_slug]) ytJobMap[j.video_slug] = j;
    }
  } catch(e) {}

  if (!clips.length) {
    return new Response(siteLayout({
      site: gabAeSite, title: 'Review — Vault', description: '',
      canonical: `https://gab.ae/vault/review/${esc(series)}`,
      extraHead: '<meta name="robots" content="noindex,nofollow">',
      body: `<div style="padding:60px 0;text-align:center;color:var(--ink-light)">No clips found for series <strong>${esc(series)}</strong>. <a href="/vault/status" style="color:var(--ink)">← Back to status</a></div>`,
    }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' } });
  }

  const clipsJson = JSON.stringify(clips.map(c => ({
    slug: c.slug,
    title: c.title || c.slug,
    status: c.status,
    url: c.video_url || '',
    tags: (() => { try { return JSON.parse(c.tags || '{}'); } catch(e) { return {}; } })(),
    ytJob: ytJobMap[c.slug] || null,
  })));

  const body = `
  <style>
    .rv-wrap { display:grid; grid-template-columns:1fr 320px; gap:0; height:calc(100vh - 120px); min-height:500px; }
    .rv-main { display:flex; flex-direction:column; gap:0; border-right:2px solid var(--border); padding-right:24px; }
    .rv-header { padding:20px 0 12px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
    .rv-header h1 { font-family:'Playfair Display',Georgia,serif; font-size:clamp(16px,2.5vw,22px); font-weight:900; color:var(--ink); margin:0; flex:1; }
    .rv-back { font-size:12px; color:var(--ink-light); text-decoration:none; }
    .rv-back:hover { color:var(--ink); }
    .rv-player { flex:1; background:#000; border-radius:4px; overflow:hidden; position:relative; min-height:300px; }
    .rv-player iframe { width:100%; height:100%; border:0; display:block; }
    .rv-player-empty { width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:#666; font-size:14px; }
    .rv-meta { padding:10px 0 4px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .rv-meta-title { font-weight:700; font-size:15px; color:var(--ink); flex:1; }
    .rv-meta-tag { font-size:11px; background:var(--paper-mid); border:1px solid var(--border); border-radius:3px; padding:2px 7px; color:var(--ink-light); }
    .rv-actions { display:flex; gap:10px; padding:10px 0 16px; flex-wrap:wrap; }
    .rv-btn { display:inline-flex; align-items:center; gap:6px; padding:9px 18px; border-radius:4px; font-size:13px; font-weight:700; cursor:pointer; border:none; transition:opacity 0.15s; }
    .rv-btn:hover { opacity:0.85; }
    .rv-btn-yt  { background:#ff0000; color:#fff; }
    .rv-btn-ok  { background:#2e7d32; color:#fff; }
    .rv-btn-skip { background:var(--paper-mid); color:var(--ink-light); border:1px solid var(--border); }
    .rv-btn-disabled { opacity:0.4; cursor:not-allowed; }
    .rv-sidebar { padding:20px 0 0 20px; display:flex; flex-direction:column; gap:0; overflow:hidden; }
    .rv-sidebar-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--ink-light); padding-bottom:8px; border-bottom:2px solid var(--border); margin-bottom:8px; }
    .rv-clips { overflow-y:auto; flex:1; }
    .rv-clip { display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:4px; cursor:pointer; border:2px solid transparent; margin-bottom:4px; transition:background 0.1s; }
    .rv-clip:hover { background:var(--paper-mid); }
    .rv-clip.active { border-color:var(--ink); background:var(--paper-mid); }
    .rv-clip-thumb { width:56px; height:36px; object-fit:cover; border-radius:2px; background:#111; flex-shrink:0; }
    .rv-clip-thumb-placeholder { width:56px; height:36px; background:var(--border); border-radius:2px; flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:16px; }
    .rv-clip-info { flex:1; min-width:0; }
    .rv-clip-name { font-size:12px; font-weight:600; color:var(--ink); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .rv-clip-status { font-size:10px; font-weight:700; text-transform:uppercase; margin-top:2px; }
    .rv-clip-idx { font-size:10px; color:var(--ink-light); flex-shrink:0; }
    @media(max-width:700px) {
      .rv-wrap { grid-template-columns:1fr; height:auto; }
      .rv-main { padding-right:0; border-right:none; }
      .rv-sidebar { padding-left:0; padding-top:16px; border-top:2px solid var(--border); max-height:340px; }
    }
  </style>

  <div class="rv-header">
    <a href="/vault/status" class="rv-back">← Status</a>
    <h1 id="rv-series-title">Review: ${esc(series)}</h1>
    <span id="rv-counter" style="font-size:12px;color:var(--ink-light)"></span>
  </div>

  <div class="rv-wrap">
    <div class="rv-main">
      <div class="rv-player" id="rv-player">
        <div class="rv-player-empty">Select a clip</div>
      </div>
      <div class="rv-meta">
        <span class="rv-meta-title" id="rv-title">—</span>
        <span class="rv-meta-tag" id="rv-location" style="display:none"></span>
        <span class="rv-meta-tag" id="rv-mood" style="display:none"></span>
        <span class="rv-meta-tag" id="rv-time" style="display:none"></span>
      </div>
      <div class="rv-actions">
        <button class="rv-btn rv-btn-yt" id="btn-yt" onclick="scheduleYouTube()">
          ▶ Schedule on YouTube
        </button>
        <button class="rv-btn rv-btn-ok" id="btn-approve" onclick="approveClip()">
          ✓ Approve
        </button>
        <button class="rv-btn rv-btn-skip" id="btn-skip" onclick="nextClip()">
          → Skip
        </button>
      </div>
    </div>

    <div class="rv-sidebar">
      <div class="rv-sidebar-title">${clips.length} clip${clips.length > 1 ? 's' : ''}</div>
      <div class="rv-clips" id="rv-clips"></div>
    </div>
  </div>

  <script>
    const CLIPS = ${clipsJson};
    let current = -1;

    const statusColor = s => ({ vault:'#1565c0', live:'#2e7d32', processed:'#e65100' }[s] || '#888');

    function renderSidebar() {
      const el = document.getElementById('rv-clips');
      el.innerHTML = CLIPS.map((c,i) => {
        const sc = statusColor(c.status);
        return \`<div class="rv-clip\${i===current?' active':''}" id="clip-item-\${i}" onclick="loadClip(\${i})">
          <div class="rv-clip-thumb-placeholder">🎬</div>
          <div class="rv-clip-info">
            <div class="rv-clip-name" title="\${c.title}">\${c.title}</div>
            <div class="rv-clip-status" style="color:\${sc}">\${c.status}</div>
          </div>
          <div class="rv-clip-idx">\${i+1}</div>
        </div>\`;
      }).join('');
    }

    function loadClip(i) {
      current = i;
      const c = CLIPS[i];
      // update player
      const player = document.getElementById('rv-player');
      const isPhoto = c.tags && c.tags.media_type === 'photo';
      player.innerHTML = !c.url
        ? \`<div class="rv-player-empty">No URL</div>\`
        : isPhoto
        ? \`<img src="\${c.url}" alt="\${c.title}" style="width:100%;height:100%;object-fit:contain;background:#000">\`
        : \`<iframe src="\${c.url}" allowfullscreen allow="autoplay"></iframe>\`;
      // update meta
      document.getElementById('rv-title').textContent = c.title;
      const setTag = (id, val) => {
        const el = document.getElementById(id);
        el.style.display = val ? '' : 'none';
        el.textContent = val || '';
      };
      setTag('rv-location', c.tags.location);
      setTag('rv-mood', c.tags.mood);
      setTag('rv-time', c.tags.time_of_day);
      // update counter
      document.getElementById('rv-counter').textContent = \`\${i+1} / \${CLIPS.length}\`;
      // update youtube button
      const btn = document.getElementById('btn-yt');
      const job = c.ytJob;
      if (!job) {
        btn.textContent = '▶ Schedule on YouTube';
        btn.disabled = false;
        btn.style.background = '';
        btn.onclick = scheduleYouTube;
      } else if (job.status === 'scheduled' || job.status === 'done') {
        const when = job.yt_scheduled_at ? new Date(job.yt_scheduled_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '';
        btn.textContent = \`📅 Scheduled\${when ? ' ' + when : ''}\`;
        btn.disabled = true;
        btn.style.background = '#2e7d32';
        btn.onclick = null;
      } else {
        const labels = {queued:'⏳ Queued', downloading:'⬇ Downloading…', processing:'⚙ Processing…', uploading:'⬆ Uploading…', error:'✗ Error'};
        btn.textContent = labels[job.status] || job.status;
        btn.disabled = true;
        btn.style.background = job.status === 'error' ? '#c62828' : '#e65100';
        btn.onclick = null;
      }
      // re-render sidebar active state
      document.querySelectorAll('.rv-clip').forEach((el,j) => {
        el.classList.toggle('active', j===i);
      });
      // scroll into view
      const item = document.getElementById(\`clip-item-\${i}\`);
      if (item) item.scrollIntoView({ block:'nearest' });
    }

    function nextClip() {
      if (current < CLIPS.length - 1) loadClip(current + 1);
    }

    function scheduleYouTube() {
      if (current < 0) return;
      const c = CLIPS[current];
      const isPhoto = c.tags && c.tags.media_type === 'photo';
      if (isPhoto) { alert('Photos cannot be scheduled on YouTube.'); return; }
      if (!c.url) { alert('No source URL for this clip.'); return; }
      if (!confirm('Schedule "' + c.title + '" on YouTube?\\n\\nThe VPS will download from IA, apply slow-mo + color grade, then upload as a scheduled Short.')) return;
      const btn = document.getElementById('btn-yt');
      btn.textContent = '⏳ Queueing…';
      btn.disabled = true;
      fetch('/api/queue-youtube', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ slug: c.slug, ia_url: c.url, series: c.series }),
      }).then(r => r.json()).then(d => {
        if (d.ok) {
          btn.textContent = '✓ Queued';
          btn.style.background = '#2e7d32';
        } else {
          btn.textContent = '▶ Schedule on YouTube';
          btn.disabled = false;
          alert('Queue failed: ' + (d.error || 'unknown'));
        }
      }).catch(e => {
        btn.textContent = '▶ Schedule on YouTube';
        btn.disabled = false;
        alert('Error: ' + e);
      });
    }

    function approveClip() {
      if (current < 0) return;
      const c = CLIPS[current];
      fetch('/api/approve-video', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ slug: c.slug }),
      }).then(r => r.json()).then(d => {
        if (d.ok) {
          CLIPS[current].status = 'live';
          document.getElementById('rv-title').textContent = c.title + ' ✓';
          renderSidebar();
          loadClip(current); // re-highlight
          setTimeout(nextClip, 600);
        } else { alert('Approve failed: ' + (d.error || 'unknown')); }
      }).catch(e => alert('Error: ' + e));
    }

    renderSidebar();
    if (CLIPS.length) loadClip(0);
  </script>
  `;

  return new Response(siteLayout({
    site: gabAeSite,
    title: `Review: ${series} — Vault`,
    description: '',
    canonical: `https://gab.ae/vault/review/${esc(series)}`,
    extraHead: '<meta name="robots" content="noindex,nofollow">',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' } });
}

async function vaultStatusPage(env) {
  const fmtTime = iso => iso ? iso.replace('T',' ').replace('Z','') : '—';

  const [ytRow, seriesRow] = await Promise.all([
    env.DB.prepare("SELECT id, video_slug, series, status, progress, yt_url, yt_scheduled_at, error, created_at FROM yt_jobs ORDER BY id DESC LIMIT 20").all().catch(() => ({results:[]})),
    env.DB.prepare(`
      SELECT series,
        SUM(CASE WHEN status='vault' THEN 1 ELSE 0 END) as vault_count,
        SUM(CASE WHEN status='backed_up' THEN 1 ELSE 0 END) as backed_up_count,
        COUNT(*) as total
      FROM videos
      GROUP BY series
      ORDER BY series DESC
    `).all().catch(() => ({results:[]})),
  ]);

  const ytJobs = ytRow.results || [];
  const seriesList = seriesRow.results || [];

  const totalSeries   = seriesList.length;
  const fullVault     = seriesList.filter(s => s.backed_up_count === 0 && s.vault_count > 0).length;
  const awaitingTag   = seriesList.filter(s => s.backed_up_count > 0).length;
  const totalFiles    = seriesList.reduce((a, s) => a + s.total, 0);
  const taggedFiles   = seriesList.reduce((a, s) => a + s.vault_count, 0);
  const pendingFiles  = seriesList.reduce((a, s) => a + s.backed_up_count, 0);

  const seriesRows = seriesList.map(s => {
    const allTagged  = s.backed_up_count === 0 && s.vault_count > 0;
    const hasBackup  = s.backed_up_count > 0 || s.vault_count > 0;
    const pct        = s.total > 0 ? Math.round(s.vault_count / s.total * 100) : 0;
    const statusTxt  = allTagged ? 'tagged' : s.backed_up_count > 0 ? 'backed up' : 'backed up';
    const statusClr  = allTagged ? '#2e7d32' : '#1565c0';
    const statusIcon = allTagged ? '✓' : '⬆';
    const bar = s.total > 0 ? `
      <div style="height:3px;background:var(--border);border-radius:2px;margin-top:4px;width:120px">
        <div style="height:3px;background:${statusClr};border-radius:2px;width:${pct}%"></div>
      </div>` : '';
    const counts = `<span style="color:#2e7d32">${s.vault_count} tagged</span>${s.backed_up_count > 0 ? ` · <span style="color:#1565c0">${s.backed_up_count} pending</span>` : ''}`;
    const nameCell = `<a href="/vault/review/${esc(s.series)}" style="color:var(--ink);text-decoration:underline;text-decoration-style:dotted;font-weight:600">${esc(s.series.replace(/-/g,' '))}</a>`;
    return `<tr>
      <td style="padding:10px 14px">${nameCell}</td>
      <td style="padding:10px 14px;text-align:center;color:${statusClr};font-size:16px">${statusIcon}</td>
      <td style="padding:10px 14px;font-size:12px">${counts}${bar}</td>
      <td style="padding:10px 14px;color:var(--ink-light);text-align:right;font-size:13px">${s.total}</td>
      <td style="padding:10px 14px"><a href="https://archive.org/details/gab-raw-${esc(s.series)}" target="_blank" style="color:#888;font-size:11px">IA ↗</a></td>
    </tr>`;
  }).join('');

  const body = `
    <style>
      .status-header { padding: 28px 0 20px; }
      .status-header h1 { font-family:'Playfair Display',Georgia,serif; font-size:clamp(20px,3vw,28px); font-weight:900; color:var(--ink); margin-bottom:6px; }
      .status-meta { font-size:12px; color:var(--ink-light); margin-bottom:24px; display:flex; gap:20px; flex-wrap:wrap; }
      .status-meta span { display:flex; align-items:center; gap:5px; }
      .status-table { width:100%; border-collapse:collapse; font-size:13px; }
      .status-table th { padding:8px 14px; text-align:left; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--ink-light); border-bottom:2px solid var(--border); }
      .status-table tr:nth-child(even) { background:var(--paper-mid); }
      .status-table tr:hover { background:var(--paper-dark); }
      .section-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--ink-light); padding-bottom:10px; border-bottom:2px solid var(--border); margin-bottom:12px; }
      .status-back { display:inline-block; margin-bottom:20px; font-size:13px; color:var(--ink-light); text-decoration:none; }
      .status-back:hover { color:var(--ink); }
      .pill { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700; }
    </style>
    <div class="status-header">
      <a href="/vault" class="status-back">← Back to Vault</a>
      <h1>Pipeline Status</h1>
      <div class="status-meta">
        <span>📦 ${totalSeries} series in vault</span>
        <span>✓ ${taggedFiles} tagged · ⬆ ${pendingFiles} awaiting tagging</span>
        <span>🎞 ${totalFiles} total files</span>
        <span style="color:var(--ink-light);font-size:11px">Auto-refreshes every 30s</span>
      </div>
    </div>

    <div class="section-title">IA Backup — ${totalSeries} Series</div>
    ${seriesList.length ? `<table class="status-table">
      <thead><tr>
        <th>Series</th><th></th><th>Progress</th><th>Files</th><th>IA</th>
      </tr></thead>
      <tbody>${seriesRows}</tbody>
    </table>` : '<p style="color:var(--ink-light);padding:40px 0;text-align:center">No series backed up yet.</p>'}

    ${ytJobs.length ? `
    <div style="margin-top:40px">
      <div class="section-title">YouTube Queue</div>
      <table class="status-table">
        <thead><tr>
          <th>Clip</th><th>Status</th><th>Progress</th><th>Scheduled</th><th>Link</th>
        </tr></thead>
        <tbody>${ytJobs.map(j => {
          const ytColor = { queued:'#888', downloading:'#6a1b9a', processing:'#e65100', uploading:'#1565c0', scheduled:'#2e7d32', done:'#2e7d32', error:'#c62828' }[j.status] || '#888';
          const ytIcon  = { queued:'·', downloading:'⬇', processing:'⚙', uploading:'⬆', scheduled:'📅', done:'✓', error:'✗' }[j.status] || '?';
          return `<tr>
            <td style="padding:10px 14px;font-weight:600;color:var(--ink)">${esc(j.video_slug)}</td>
            <td style="padding:10px 14px;color:${ytColor};font-weight:700;font-size:12px;text-transform:uppercase">${ytIcon} ${esc(j.status)}</td>
            <td style="padding:10px 14px;color:var(--ink-light);font-size:12px">${esc(j.progress || '—')}</td>
            <td style="padding:10px 14px;color:var(--ink-light);font-size:12px">${j.yt_scheduled_at ? fmtTime(j.yt_scheduled_at) : '—'}</td>
            <td style="padding:10px 14px">${j.yt_url ? `<a href="${esc(j.yt_url)}" target="_blank" style="color:#ff0000;font-size:12px">▶ YouTube</a>` : (j.error ? `<span style="color:#c62828;font-size:11px">${esc(j.error.slice(0,60))}</span>` : '—')}</td>
          </tr>`;
        }).join('')}</tbody>
      </table>
    </div>` : ''}

    <script>
      setTimeout(()=>location.reload(), 30000);
    </script>
  `;

  return new Response(siteLayout({
    site: gabAeSite,
    title: 'Pipeline Status — Vault',
    description: '',
    canonical: 'https://gab.ae/vault/status',
    extraHead: '<meta name="robots" content="noindex,nofollow">',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' } });
}

async function vaultApprovePage(env, request) {
  // POST — schedule a single clip
  if (request.method === 'POST') {
    const form = await request.formData().catch(() => null);
    const slug = form?.get('slug');
    if (!slug) return new Response(JSON.stringify({ ok: false, error: 'missing slug' }), { headers: { 'content-type': 'application/json' } });
    const clip = await env.DB.prepare("SELECT slug, series, video_url FROM videos WHERE slug=?").bind(slug).first().catch(() => null);
    if (!clip) return new Response(JSON.stringify({ ok: false, error: 'not found' }), { headers: { 'content-type': 'application/json' } });
    await env.DB.prepare(
      "INSERT OR IGNORE INTO yt_jobs (video_slug, series, ia_url, effects, status, created_at, updated_at) VALUES (?, ?, ?, 'slowmo,colorgrade', 'queued', datetime('now'), datetime('now'))"
    ).bind(clip.slug, clip.series || '', clip.video_url || '').run();
    return new Response(JSON.stringify({ ok: true }), { headers: { 'content-type': 'application/json' } });
  }

  // GET — approval grid
  const [clipsRow, scheduledRow] = await Promise.all([
    env.DB.prepare("SELECT slug, title, series, thumb_b64, tags FROM videos WHERE status='vault' ORDER BY series DESC, slug ASC").all().catch(() => ({ results: [] })),
    env.DB.prepare("SELECT video_slug FROM yt_jobs").all().catch(() => ({ results: [] })),
  ]);

  const scheduled = new Set((scheduledRow.results || []).map(r => r.video_slug));
  const allClips  = (clipsRow.results || []).filter(c => {
    try { return JSON.parse(c.tags || '{}').media_type !== 'photo'; } catch { return true; }
  });
  const pending = allClips.filter(c => !scheduled.has(c.slug));
  const doneCount = allClips.length - pending.length;

  // Group by series
  const bySeries = {};
  for (const c of pending) {
    if (!bySeries[c.series]) bySeries[c.series] = [];
    bySeries[c.series].push(c);
  }

  const card = c => {
    const thumb = c.thumb_b64
      ? `<img src="data:image/jpeg;base64,${c.thumb_b64}" style="width:100%;height:100%;object-fit:cover;border-radius:6px">`
      : `<div style="width:100%;height:100%;background:#1a1a1a;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:22px">🎬</div>`;
    let tags = {};
    try { tags = JSON.parse(c.tags || '{}'); } catch {}
    const sub = [tags.time_of_day, tags.mood].filter(Boolean).join(' · ');
    return `<div class="card" id="card-${esc(c.slug)}" style="display:flex;align-items:center;gap:14px;padding:12px 0;border-bottom:1px solid #1c1c1c">
      <div style="width:88px;height:56px;flex-shrink:0;overflow:hidden">${thumb}</div>
      <div style="flex:1;min-width:0">
        <div style="font-size:14px;font-weight:600;color:#f0f0f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(c.title || c.slug)}</div>
        ${sub ? `<div style="font-size:11px;color:#666;margin-top:3px">${esc(sub)}</div>` : ''}
      </div>
      <button onclick="schedule('${esc(c.slug)}')" id="btn-${esc(c.slug)}"
        style="flex-shrink:0;background:#2563eb;color:#fff;border:none;border-radius:8px;padding:10px 20px;font-size:13px;font-weight:700;cursor:pointer;transition:background 0.15s">
        Schedule
      </button>
    </div>`;
  };

  const sections = Object.entries(bySeries).map(([series, clips]) => `
    <div style="margin-bottom:36px">
      <div style="display:flex;align-items:center;justify-content:space-between;padding-bottom:10px;border-bottom:2px solid #1c1c1c;margin-bottom:4px">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#555">${esc(series.replace(/-/g,' '))}</div>
        <button onclick="scheduleAll([${clips.map(c => `'${esc(c.slug)}'`).join(',')}])"
          style="background:#111;color:#666;border:1px solid #2a2a2a;border-radius:6px;padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer">
          Schedule all ${clips.length}
        </button>
      </div>
      ${clips.map(card).join('')}
    </div>`).join('');

  const body = `
    <style>
      body { background:#080808 !important; }
      .ap-wrap { max-width:680px; margin:0 auto; padding:32px 20px 80px; }
      h1 { font-family:'Playfair Display',Georgia,serif; font-size:28px; font-weight:900; color:#f0f0f0; margin-bottom:6px; }
      .ap-meta { font-size:12px; color:#555; margin-bottom:36px; display:flex; gap:20px; }
      button:hover { opacity:0.85; }
    </style>
    <div class="ap-wrap">
      <a href="/vault/status" style="font-size:13px;color:#444;text-decoration:none;display:block;margin-bottom:24px">← Pipeline status</a>
      <h1>Schedule for YouTube</h1>
      <div class="ap-meta">
        <span style="color:#f0f0f0;font-weight:700">${pending.length} clips to review</span>
        <span>✓ ${doneCount} already scheduled</span>
      </div>
      ${pending.length === 0
        ? '<p style="color:#444;text-align:center;padding:80px 0;font-size:16px">All clips scheduled 🎉</p>'
        : sections}
    </div>
    <script>
      async function schedule(slug) {
        const btn = document.getElementById('btn-' + slug);
        const card = document.getElementById('card-' + slug);
        btn.textContent = '…'; btn.disabled = true;
        const fd = new FormData();
        fd.append('slug', slug);
        const r = await fetch('/vault/approve', { method:'POST', body:fd });
        const d = await r.json().catch(() => ({}));
        if (d.ok) {
          card.style.transition = 'opacity 0.3s';
          card.style.opacity = '0.25';
          btn.textContent = '✓';
          btn.style.background = '#166534';
        } else {
          btn.textContent = 'Error'; btn.style.background = '#7f1d1d'; btn.disabled = false;
        }
      }
      async function scheduleAll(slugs) {
        for (const s of slugs) {
          const btn = document.getElementById('btn-' + s);
          if (btn && !btn.disabled) { await schedule(s); await new Promise(r => setTimeout(r, 150)); }
        }
      }
    </script>`;

  return new Response(siteLayout({
    site: gabAeSite, title: 'Schedule — Vault', description: '',
    canonical: 'https://gab.ae/vault/approve',
    extraHead: '<meta name="robots" content="noindex,nofollow">',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' } });
}

function vaultLoginPage(wrongKey = false) {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex,nofollow">
  <title>Vault</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0e0e0e; font-family: 'DM Sans', system-ui, sans-serif; }
    .login-box { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 14px; padding: 40px 36px; width: 100%; max-width: 340px; }
    h1 { font-size: 22px; font-weight: 800; color: #f0f0f0; margin-bottom: 6px; letter-spacing: -0.02em; }
    p { font-size: 13px; color: #888; margin-bottom: 28px; }
    label { display: block; font-size: 12px; font-weight: 600; color: #aaa; margin-bottom: 8px; }
    input[type=password] { width: 100%; padding: 11px 14px; background: #111; border: 1px solid #333; border-radius: 8px; color: #f0f0f0; font-size: 15px; outline: none; transition: border-color 0.15s; }
    input[type=password]:focus { border-color: #666; }
    button { margin-top: 16px; width: 100%; padding: 12px; background: #f0f0f0; color: #111; border: none; border-radius: 8px; font-size: 14px; font-weight: 700; cursor: pointer; transition: background 0.15s; }
    button:hover { background: #ddd; }
    .err { margin-top: 14px; font-size: 12px; color: #e05252; text-align: center; }
  </style>
</head>
<body>
  <div class="login-box">
    <h1>Vault</h1>
    <p>Private media archive. Enter the access key.</p>
    <form method="POST" action="/vault">
      <label for="key">Access key</label>
      <input type="password" id="key" name="key" autofocus autocomplete="current-password">
      <button type="submit">Enter</button>
      ${wrongKey ? '<p class="err">Wrong key — try again.</p>' : ''}
    </form>
  </div>
</body>
</html>`;
  return new Response(html, { status: wrongKey ? 401 : 200, headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' } });
}

async function vaultPage(env) {
  let seriesSummary = [], shorts = [];
  const [sumRow, srRow] = await Promise.all([
    env.DB.prepare("SELECT series, status, COUNT(*) as count FROM videos GROUP BY series, status ORDER BY series DESC").all().catch(() => ({results:[]})),
    env.DB.prepare("SELECT slug, title, series, video_url FROM shorts WHERE status='vault' ORDER BY id DESC LIMIT 50").all().catch(() => ({results:[]})),
  ]);
  shorts = srRow.results || [];
  // Build series summary map
  const seriesMap = {};
  for (const r of sumRow.results || []) {
    if (!seriesMap[r.series]) seriesMap[r.series] = { series: r.series, vault: 0, backed_up: 0, total: 0 };
    if (r.status === 'vault') seriesMap[r.series].vault += r.count;
    else if (r.status === 'backed_up') seriesMap[r.series].backed_up += r.count;
    seriesMap[r.series].total += r.count;
  }
  seriesSummary = Object.values(seriesMap).sort((a,b) => b.series.localeCompare(a.series));

  const totalClips = seriesSummary.reduce((a, s) => a + s.total, 0);
  const totalVault = seriesSummary.reduce((a, s) => a + s.vault, 0);

  const seriesCard = (s) => {
    const pct = s.total > 0 ? Math.round(s.vault / s.total * 100) : 0;
    const badge = s.vault > 0
      ? `<span style="background:#1a5c30;color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:6px">${s.vault} tagged</span>`
      : s.backed_up > 0 ? `<span style="background:#555;color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:6px">${s.backed_up} pending</span>` : '';
    return `<a href="/vault/review/${esc(s.series)}" style="display:block;text-decoration:none">
      <div style="background:var(--paper-mid);border:1px solid var(--border);border-radius:10px;padding:16px 18px;transition:border-color 0.15s" onmouseover="this.style.borderColor='var(--ink)'" onmouseout="this.style.borderColor='var(--border)'">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div style="font-size:14px;font-weight:700;color:var(--ink)">${esc(s.series)}${badge}</div>
          <div style="font-size:12px;color:var(--ink-light)">${s.total} clip${s.total!==1?'s':''}</div>
        </div>
        <div style="height:4px;background:var(--border);border-radius:2px">
          <div style="height:4px;background:#1a5c30;border-radius:2px;width:${pct}%"></div>
        </div>
      </div>
    </a>`;
  };

  const body = `
    <style>
      .vault-header { padding: 28px 0 20px; }
      .vault-header h1 { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(22px, 3vw, 32px); font-weight: 900; color: var(--ink); margin-bottom: 6px; }
      .vault-meta-bar { font-size: 12px; color: var(--ink-light); margin-bottom: 24px; display: flex; gap: 20px; }
      .vault-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; padding-bottom: 48px; }
      .vault-empty { text-align: center; padding: 80px 24px; color: var(--ink-light); font-size: 15px; }
    </style>
    <div class="vault-header">
      <h1>Vault</h1>
      <div class="vault-meta-bar">
        <span>${seriesSummary.length} series · ${totalClips} clips · ${totalVault} tagged</span>
        <a href="/vault/status" style="color:var(--ink-light);text-decoration:none;margin-left:auto">Pipeline status →</a>
      </div>
    </div>
    ${seriesSummary.length
      ? `<div class="vault-grid">${seriesSummary.map(seriesCard).join('')}</div>`
      : `<div class="vault-empty">No footage backed up yet.</div>`}
  `;

  return new Response(siteLayout({
    site: gabAeSite,
    title: 'Vault',
    description: '',
    canonical: 'https://gab.ae/vault',
    extraHead: '<meta name="robots" content="noindex,nofollow">',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'no-store' } });
}

async function videosPage(env) {
  let videos = [];
  try {
    const { results } = await env.DB.prepare(
      "SELECT slug, title, series, video_url FROM videos WHERE status='live' ORDER BY id DESC"
    ).all();
    videos = results || [];
  } catch (e) {}

  const cardHtml = (v) => `
    <div class="video-card" ${v.video_url ? `data-embed="${esc(v.video_url)}"` : ''} role="button" tabindex="0">
      <div class="video-thumb">
        <img src="/vthumb/${esc(v.slug)}" alt="${esc(v.title)}" loading="lazy" width="480" height="270">
        <div class="video-play-icon">&#9654;</div>
      </div>
      <div class="video-info"><span class="video-title">${esc(v.title)}</span></div>
    </div>`;

  const body = `
    <style>
      .videos-header { padding: 28px 0 16px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
      .videos-header h1 { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(22px, 3vw, 32px); font-weight: 900; color: var(--ink); letter-spacing: -0.02em; }
      .videos-header p { font-size: 13px; color: var(--ink-light); margin-top: 6px; }
      .videos-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding-bottom: 48px; }
      @media (min-width: 1024px) { .videos-grid { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); } }
      .video-card { display: block; border-radius: 10px; overflow: hidden; background: var(--paper-mid); cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease; }
      .video-card:hover { transform: translateY(-3px); box-shadow: 0 8px 28px rgba(0,0,0,0.15); }
      .video-thumb { position: relative; aspect-ratio: 16/9; overflow: hidden; }
      .video-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s ease; }
      .video-card:hover .video-thumb img { transform: scale(1.03); }
      .video-play-icon { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 48px; height: 48px; background: rgba(0,0,0,0.55); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 18px; opacity: 0; transition: opacity 0.2s; padding-left: 4px; }
      .video-card:hover .video-play-icon { opacity: 1; }
      .video-info { padding: 12px 14px 14px; }
      .video-title { font-size: 14px; font-weight: 600; color: var(--ink); line-height: 1.4; display: block; }
      .videos-empty { text-align: center; padding: 80px 24px; color: var(--ink-light); font-size: 15px; }
      /* Modal reuse */
      .shorts-modal { display: none; position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.88); align-items: center; justify-content: center; }
      .shorts-modal.open { display: flex; }
      .video-modal-inner { position: relative; width: min(800px, 92vw); aspect-ratio: 16/9; background: #000; border-radius: 12px; overflow: hidden; box-shadow: 0 24px 80px rgba(0,0,0,0.6); }
      .video-modal-inner iframe { width: 100%; height: 100%; border: none; display: block; }
      .shorts-modal-close { position: absolute; top: -40px; right: 0; background: none; border: none; color: #fff; font-size: 28px; cursor: pointer; line-height: 1; opacity: 0.8; }
      .shorts-modal-close:hover { opacity: 1; }
    </style>

    <div class="videos-header">
      <h1>Videos</h1>
      ${videos.length ? `<p>${videos.length} video${videos.length > 1 ? 's' : ''}</p>` : ''}
    </div>

    ${videos.length
      ? `<div class="videos-grid">${videos.map(cardHtml).join('')}</div>`
      : `<div class="videos-empty">No videos yet.</div>`
    }

    <div class="shorts-modal" id="video-modal">
      <div class="video-modal-inner">
        <button class="shorts-modal-close" id="video-modal-close" aria-label="Close">&times;</button>
        <iframe id="video-modal-iframe" src="" allowfullscreen allow="autoplay; fullscreen"></iframe>
      </div>
    </div>

    <script>
    (function() {
      var modal  = document.getElementById('video-modal');
      var iframe = document.getElementById('video-modal-iframe');
      function open(url)  { iframe.src = url; modal.classList.add('open'); document.body.style.overflow = 'hidden'; }
      function close()    { modal.classList.remove('open'); iframe.src = ''; document.body.style.overflow = ''; }
      document.querySelectorAll('.video-card[data-embed]').forEach(function(c) {
        c.addEventListener('click', function() { open(c.dataset.embed); });
        c.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') open(c.dataset.embed); });
      });
      document.getElementById('video-modal-close').addEventListener('click', close);
      modal.addEventListener('click', function(e) { if (e.target === modal) close(); });
      document.addEventListener('keydown', function(e) { if (e.key === 'Escape') close(); });
    })();
    </script>
  `;

  return new Response(siteLayout({
    site: gabAeSite,
    title: 'Videos — GAB adventures',
    description: 'Video clips by Gab.',
    canonical: 'https://gab.ae/videos',
    activeNav: 'videos',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=60' } });
}

async function shortsHomepage(env) {
  let shorts = [];
  try {
    const { results } = await env.DB.prepare(
      "SELECT slug, title, series, video_url FROM shorts WHERE status='live' ORDER BY id ASC"
    ).all();
    shorts = results || [];
  } catch (e) {}

  const cardHtml = (s) => {
    const embedUrl = esc(s.video_url || '');
    return `
      <div class="short-card" ${s.video_url ? `data-embed="${embedUrl}"` : ''} role="button" tabindex="0">
        <div class="short-thumb">
          <img src="/thumb/${esc(s.slug)}" alt="${esc(s.title)}" loading="lazy" width="270" height="480">
          <div class="short-play-icon">&#9654;</div>
          <div class="short-overlay"><span class="short-title">${esc(s.title)}</span></div>
        </div>
      </div>`;
  };

  const body = `
    <style>
      .shorts-header { padding: 28px 0 16px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
      .shorts-header h1 { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(22px, 3vw, 32px); font-weight: 900; color: var(--ink); letter-spacing: -0.02em; }
      .shorts-header p { font-size: 13px; color: var(--ink-light); margin-top: 6px; }
      .shorts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; padding-bottom: 48px; }
      @media (min-width: 640px)  { .shorts-grid { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 14px; } }
      @media (min-width: 1024px) { .shorts-grid { grid-template-columns: repeat(auto-fill, minmax(185px, 1fr)); gap: 16px; } }
      .short-card { display: block; border-radius: 10px; overflow: hidden; background: var(--paper-mid); cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease; }
      .short-card:hover { transform: scale(1.03); box-shadow: 0 8px 28px rgba(0,0,0,0.25); }
      .short-thumb { position: relative; aspect-ratio: 9/16; overflow: hidden; }
      .short-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s ease; }
      .short-card:hover .short-thumb img { transform: scale(1.05); }
      .short-play-icon { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 44px; height: 44px; background: rgba(0,0,0,0.55); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 16px; opacity: 0; transition: opacity 0.2s; padding-left: 3px; }
      .short-card:hover .short-play-icon { opacity: 1; }
      .short-overlay { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(transparent, rgba(0,0,0,0.72)); padding: 24px 10px 10px; }
      .short-title { display: block; font-size: 12px; font-weight: 600; color: #fff; line-height: 1.3; }
      .shorts-news-link { display: block; text-align: center; padding: 18px 0 36px; font-size: 13px; color: var(--ink-light); border-top: 1px solid var(--border); }
      .shorts-news-link a { color: var(--accent); }
      .shorts-news-link a:hover { text-decoration: underline; }
      .shorts-empty { text-align: center; padding: 80px 24px; color: var(--ink-light); font-size: 15px; }

      /* ── Modal player ── */
      .shorts-modal { display: none; position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.88); align-items: center; justify-content: center; }
      .shorts-modal.open { display: flex; }
      .shorts-modal-inner { position: relative; width: min(360px, 90vw); aspect-ratio: 9/16; background: #000; border-radius: 12px; overflow: hidden; box-shadow: 0 24px 80px rgba(0,0,0,0.6); }
      .shorts-modal-inner iframe { width: 100%; height: 100%; border: none; display: block; }
      .shorts-modal-close { position: absolute; top: -40px; right: 0; background: none; border: none; color: #fff; font-size: 28px; cursor: pointer; line-height: 1; opacity: 0.8; }
      .shorts-modal-close:hover { opacity: 1; }
    </style>

    <div class="shorts-header">
      <h1>Home</h1>
      ${shorts.length ? `<p>${shorts.length} clips</p>` : ''}
    </div>

    ${shorts.length
      ? `<div class="shorts-grid">${shorts.map(cardHtml).join('')}</div>`
      : `<div class="shorts-empty">No clips yet.</div>`
    }

    <div class="shorts-news-link">Looking for news? <a href="/news">Visit the newsroom &rarr;</a></div>

    <div class="shorts-modal" id="shorts-modal">
      <div class="shorts-modal-inner" id="shorts-modal-inner">
        <button class="shorts-modal-close" id="shorts-modal-close" aria-label="Close">&times;</button>
        <iframe id="shorts-modal-iframe" src="" allowfullscreen allow="autoplay; fullscreen"></iframe>
      </div>
    </div>

    <script>
    (function() {
      var modal = document.getElementById('shorts-modal');
      var iframe = document.getElementById('shorts-modal-iframe');
      var inner = document.getElementById('shorts-modal-inner');

      function openModal(url) {
        iframe.src = url;
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
      }
      function closeModal() {
        modal.classList.remove('open');
        iframe.src = '';
        document.body.style.overflow = '';
      }

      document.querySelectorAll('.short-card[data-embed]').forEach(function(card) {
        card.addEventListener('click', function() { openModal(card.dataset.embed); });
        card.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') openModal(card.dataset.embed); });
      });

      document.getElementById('shorts-modal-close').addEventListener('click', closeModal);
      modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
      document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });
    })();
    </script>
  `;

  return new Response(siteLayout({
    site: gabAeSite,
    title: 'gab.ae',
    description: 'Short clips by Gab — Paris, slowmo, and more.',
    canonical: 'https://gab.ae/',
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=60' } });
}

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

  return new Response(siteLayout({ site: gabAeSite,
    title: 'gab.ae — Search',
    description: 'Free tools, news, and expert guides across finance, tech, health, travel, gaming, and more. Built by a team of humans and AI agents answering your questions.',
    canonical: 'https://gab.ae/search',
    body,
  }), {
    headers: { 'content-type': 'text/html;charset=UTF-8' },
  });
}

const CAT_COLORS = {
  us: '#c8102e', world: '#1a5c8a', politics: '#3a2060',
  business: '#1a5c30', health: '#8a2020', entertainment: '#8a6020',
  travel: '#1a4a6a', sports: '#1a3a5c', science: '#2a1e5e',
  climate: '#1a5c30', tech: '#8a4020',
};
const CAT_LABELS = {
  us: 'U.S.', world: 'World', politics: 'Politics', business: 'Business',
  health: 'Health', entertainment: 'Entertainment', travel: 'Travel',
  sports: 'Sports', science: 'Science', climate: 'Climate', tech: 'Tech',
};

function catColor(cat) { return CAT_COLORS[cat] || '#c8102e'; }
function catLabel(cat) { return CAT_LABELS[cat] || (cat ? cat.charAt(0).toUpperCase() + cat.slice(1) : 'News'); }

function storyCardHtml(a) {
  return `
    <div>
      ${a.image ? `<a href="/news/${a.slug}" class="card-img-link"><img src="${esc(a.image)}" alt="${esc(a.title)}" class="card-thumb" loading="lazy" width="400" height="225"></a>` : ''}
      <a href="/news/${a.slug}" class="story-card-title">${esc(a.title)}</a>
      ${a.description ? `<p class="story-card-desc">${esc(a.description)}</p>` : ''}
      <div class="story-card-meta">${timeAgo(a.published_at)}</div>
    </div>`;
}

function catSectionHtml(catArticles, cat) {
  if (!catArticles.length) return '';
  const color = catColor(cat);
  const label = catLabel(cat);
  const lead = catArticles[0];
  const two = catArticles.slice(1, 3);
  const grid = catArticles.slice(3, 6);

  const leadPlusTwo = catArticles.length >= 2 ? `
    <div class="lead-plus-two">
      <div>
        ${lead.image ? `<a href="/news/${lead.slug}" class="card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
        <a href="/news/${lead.slug}" class="lead-story-title">${esc(lead.title)}</a>
        ${lead.description ? `<p class="lead-story-desc">${esc(lead.description)}</p>` : ''}
        <div class="lead-story-meta">${timeAgo(lead.published_at)}</div>
      </div>
      <div class="two-stack">
        ${two.map(a => `
          <div class="two-stack-item">
            <a href="/news/${a.slug}" class="two-stack-title">${esc(a.title)}</a>
            <div class="two-stack-meta">${timeAgo(a.published_at)}</div>
          </div>`).join('')}
      </div>
    </div>` : `
    <div style="margin-bottom:20px">
      ${lead.image ? `<a href="/news/${lead.slug}" class="card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
      <a href="/news/${lead.slug}" class="lead-story-title">${esc(lead.title)}</a>
      ${lead.description ? `<p class="lead-story-desc">${esc(lead.description)}</p>` : ''}
      <div class="lead-story-meta">${timeAgo(lead.published_at)}</div>
    </div>`;

  const gridHtml = grid.length >= 2 ? `
    <div class="three-col">
      ${grid.map(a => storyCardHtml(a)).join('')}
    </div>` : '';

  return `
    <div class="cat-section">
      <div class="section-header">
        <div class="section-header-left">
          <span class="section-label" style="background:${color}">${label}</span>
          <span class="section-h2">${label}</span>
        </div>
        <a href="/news/category/${cat}" class="see-all">See all →</a>
      </div>
      ${leadPlusTwo}
      ${gridHtml}
    </div>`;
}

async function newsIndex(env, category = null, page = 1) {
  const PAGE_SIZE = 60;
  const offset = (page - 1) * PAGE_SIZE;
  let articles = [];
  let totalCount = 0;
  try {
    const [result, countResult] = await Promise.all([
      category
        ? env.DB.prepare("SELECT id,slug,title,description,lede,category,published_at,image FROM news WHERE status='live' AND category=? ORDER BY published_at DESC LIMIT ? OFFSET ?").bind(category, PAGE_SIZE, offset).all()
        : env.DB.prepare("SELECT id,slug,title,description,lede,category,published_at,image FROM news WHERE status='live' ORDER BY published_at DESC LIMIT ? OFFSET ?").bind(PAGE_SIZE, offset).all(),
      category
        ? env.DB.prepare("SELECT COUNT(*) as cnt FROM news WHERE status='live' AND category=?").bind(category).first()
        : env.DB.prepare("SELECT COUNT(*) as cnt FROM news WHERE status='live'").first(),
    ]);
    articles = result?.results || [];
    totalCount = countResult?.cnt || 0;
  } catch (e) { console.log('❌ newsIndex error:', e.message, e.stack); }
  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  // ── Category page ──
  if (category) {
    const lead = articles[0];
    const two = articles.slice(1, 3);
    const rest = articles.slice(3);
    const color = catColor(category);
    const label = catLabel(category);

    const baseUrl = `/news/category/${category}`;
    const paginationHtml = totalPages > 1 ? `
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;padding:32px 0;border-top:1px solid var(--border-light);margin-top:20px">
        ${page > 1 ? `<a href="${baseUrl}?page=${page - 1}" style="padding:8px 16px;border:1px solid var(--border-light);border-radius:4px;color:var(--ink);text-decoration:none;font-size:14px">← Newer</a>` : '<span style="padding:8px 16px;opacity:0.3;font-size:14px">← Newer</span>'}
        <span style="font-size:14px;color:var(--ink-light)">Page ${page} of ${totalPages}</span>
        ${page < totalPages ? `<a href="${baseUrl}?page=${page + 1}" style="padding:8px 16px;border:1px solid var(--border-light);border-radius:4px;color:var(--ink);text-decoration:none;font-size:14px">Older →</a>` : '<span style="padding:8px 16px;opacity:0.3;font-size:14px">Older →</span>'}
      </div>` : '';

    const body = articles.length === 0
      ? `<div class="cat-page-header">
           <h1 class="cat-page-title">${label}</h1>
         </div>
         <p style="color:var(--ink-light);padding:48px 0;text-align:center">No articles yet — check back soon.</p>`
      : `<div class="cat-page-header">
           <div style="margin-bottom:8px"><span class="section-label" style="background:${color}">${label}</span></div>
           <h1 class="cat-page-title">${label}</h1>
           <div class="cat-page-count">${totalCount} article${totalCount !== 1 ? 's' : ''}</div>
         </div>
         ${page === 1 && articles.length >= 2 ? `
         <div class="lead-plus-two" style="margin-bottom:28px">
           <div>
             ${lead.image ? `<a href="/news/${lead.slug}" class="card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
             <a href="/news/${lead.slug}" class="lead-story-title">${esc(lead.title)}</a>
             ${lead.description ? `<p class="lead-story-desc">${esc(lead.description)}</p>` : ''}
             <div class="lead-story-meta">${timeAgo(lead.published_at)}</div>
           </div>
           <div class="two-stack">
             ${two.map(a => `
               <div class="two-stack-item">
                 <a href="/news/${a.slug}" class="two-stack-title">${esc(a.title)}</a>
                 <div class="two-stack-meta">${timeAgo(a.published_at)}</div>
               </div>`).join('')}
           </div>
         </div>` : page === 1 ? `
         <div style="margin-bottom:28px">
           ${lead.image ? `<a href="/news/${lead.slug}" class="card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
           <a href="/news/${lead.slug}" class="lead-story-title">${esc(lead.title)}</a>
           ${lead.description ? `<p class="lead-story-desc">${esc(lead.description)}</p>` : ''}
           <div class="lead-story-meta">${timeAgo(lead.published_at)}</div>
         </div>` : ''}
         ${(page === 1 ? rest : articles).length > 0 ? `
         <div class="three-col" style="border-top:1px solid var(--border-light);padding-top:20px">
           ${(page === 1 ? rest : articles).map(a => storyCardHtml(a)).join('')}
         </div>` : ''}
         ${paginationHtml}`;

    return new Response(siteLayout({ site: gabAeSite,
      title: `${label} News${page > 1 ? ` — Page ${page}` : ''} | GAB.AE`,
      description: `Latest ${label} news, breaking stories, and in-depth analysis.`,
      canonical: `https://gab.ae${baseUrl}${page > 1 ? `?page=${page}` : ''}`,
      activeNav: category,
      body,
    }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
  }

  // ── Homepage ──
  if (articles.length === 0) {
    return new Response(siteLayout({ site: gabAeSite,
      title: 'Latest News & Analysis | GAB.AE',
      description: 'US news and in-depth analysis across politics, business, tech, health, science, sports, and entertainment.',
      canonical: 'https://gab.ae/',
      activeNav: 'home',
      body: '<p style="color:var(--ink-light);padding:80px 0;text-align:center">No articles yet — check back soon.</p>',
    }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
  }

  const hero = articles[0];
  const sidebar = articles.slice(1, 4);
  const remaining = articles.slice(4);

  // Group remaining by category, preserving insertion order
  const byCategory = new Map();
  for (const a of remaining) {
    if (!byCategory.has(a.category)) byCategory.set(a.category, []);
    byCategory.get(a.category).push(a);
  }

  // Trending: top 8 categories by article count
  const catCounts = new Map();
  for (const a of articles) catCounts.set(a.category, (catCounts.get(a.category) || 0) + 1);
  const trendingCats = [...catCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([cat]) => cat);

  const heroColor = catColor(hero.category);
  const heroLabel = catLabel(hero.category);

  const heroHtml = `
    <div class="hero-section">
      <div class="hero-grid">
        <div class="hero-main">
          <span class="hero-cat-label" style="background:${heroColor}">${heroLabel}</span>
          ${hero.image ? `<a href="/news/${hero.slug}" class="hero-img-link"><img src="${esc(hero.image)}" alt="${esc(hero.title)}" class="hero-img" loading="eager" width="860" height="484"></a>` : ''}
          <a href="/news/${hero.slug}" class="hero-headline">${esc(hero.title)}</a>
          ${hero.lede ? `<p class="hero-deck">${esc(hero.lede)}</p>` : hero.description ? `<p class="hero-deck">${esc(hero.description)}</p>` : ''}
          <div class="hero-meta">${timeAgo(hero.published_at)}</div>
        </div>
        <div class="hero-sidebar">
          ${sidebar.map(a => `
            <div class="sidebar-story">
              <span class="sidebar-story-cat" style="background:${catColor(a.category)}">${catLabel(a.category)}</span>
              <a href="/news/${a.slug}" class="sidebar-story-title">${esc(a.title)}</a>
              <div class="sidebar-story-meta">${timeAgo(a.published_at)}</div>
            </div>`).join('')}
        </div>
      </div>
    </div>`;

  const trendingHtml = trendingCats.length ? `
    <div class="trending-bar">
      <div class="trending-inner">
        <span class="trending-label">Trending</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${trendingCats.map(cat => `<a href="/news/category/${cat}" class="trending-tag">${catLabel(cat)}</a>`).join('')}
        </div>
      </div>
    </div>` : '';

  const categorySectionsHtml = [...byCategory.entries()]
    .map(([cat, arts]) => catSectionHtml(arts, cat))
    .join('');

  const body = heroHtml + trendingHtml + categorySectionsHtml;

  return new Response(siteLayout({ site: gabAeSite,
    title: 'Latest News & Analysis | GAB.AE',
    description: 'US news and in-depth analysis across politics, business, tech, health, science, sports, and entertainment.',
    canonical: 'https://gab.ae/',
    activeNav: 'home',
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

    const html = siteLayout({ site: gabAeSite,
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
async function healthPage(env, triggered = false) {
  try {
    const [pendingRes, fixedTodayRes, unfixableRes, lastScanRes, pendingRowsRes, recentLogsRes] = await Promise.all([
      env.DB.prepare("SELECT COUNT(*) as cnt FROM broken_links WHERE status='pending'").first(),
      env.DB.prepare("SELECT COUNT(*) as cnt FROM broken_links WHERE status='fixed' AND date(fixed_at)=date('now')").first(),
      env.DB.prepare("SELECT COUNT(*) as cnt FROM broken_links WHERE status='removed'").first(),
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
      ${triggered ? `<div class="bg-blue-900 border border-blue-700 text-blue-200 rounded-xl px-5 py-3 mb-6 text-sm">Scan triggered — refresh in a minute to see results.</div>` : ''}

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
          <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Removed</div>
          <div class="text-3xl font-bold ${unfixableCount > 0 ? 'text-yellow-400' : 'text-gray-400'}">${unfixableCount}</div>
          <div class="text-xs text-gray-500 mt-1">anchor stripped</div>
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

    const html = siteLayout({ site: gabAeSite,
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
  // Clean up rate limit entries older than 5 minutes
  try {
    const rlCutoff = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    await env.DB.prepare(`DELETE FROM rate_limits WHERE last_request < ?`).bind(rlCutoff).run();
  } catch (e) {
    console.log(`❌ Rate limit prune error: ${e.message}`);
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

  const html = siteLayout({ site: gabAeSite,
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
  const html = siteLayout({ site: gabAeSite,
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

// ═══════════════════════════════════════════════════════════════
// SECTION: Generic Site Page Handlers
// Powers The Nookie Nook, Paris Dispatch, and all future sub-sites.
// nookieIndex/nookieArticlePage/etc. are thin wrappers at the bottom.
// ═══════════════════════════════════════════════════════════════

function siteCatColor(site, cat) {
  return site.categoryColors[cat] || site.theme.accent;
}

function siteCatLabel(site, cat) {
  if (!cat) return site.defaultCategory.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const nav = site.navItems.find(n => n.href.endsWith('/' + cat));
  return nav?.label || cat.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function siteStoryCardHtml(a, basePath, site) {
  return `
    <div>
      ${a.image ? `<a href="${basePath}/article/${a.slug}" class="nk-card-img-link"><img src="${esc(a.image)}" alt="${esc(a.title)}" class="nk-card-thumb" loading="lazy" width="400" height="225"></a>` : ''}
      <a href="${basePath}/article/${a.slug}" class="nk-story-card-title">${esc(a.title)}</a>
      ${a.description ? `<p class="nk-story-card-desc">${esc(a.description)}</p>` : ''}
      <div class="nk-story-card-meta">${timeAgo(a.published_at)}</div>
    </div>`;
}

function siteCatSectionHtml(catArticles, cat, basePath, site) {
  if (!catArticles.length) return '';
  const color = siteCatColor(site, cat);
  const label = siteCatLabel(site, cat);
  const lead = catArticles[0];
  const two = catArticles.slice(1, 3);
  const grid = catArticles.slice(3, 6);

  const leadPlusTwo = catArticles.length >= 2 ? `
    <div class="nk-lead-plus-two">
      <div>
        ${lead.image ? `<a href="${basePath}/article/${lead.slug}" class="nk-card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="nk-lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
        <a href="${basePath}/article/${lead.slug}" class="nk-lead-story-title">${esc(lead.title)}</a>
        ${lead.description ? `<p class="nk-lead-story-desc">${esc(lead.description)}</p>` : ''}
        <div class="nk-lead-story-meta">${timeAgo(lead.published_at)}</div>
      </div>
      <div class="nk-two-stack">
        ${two.map(a => `
          <div class="nk-two-stack-item">
            <a href="${basePath}/article/${a.slug}" class="nk-two-stack-title">${esc(a.title)}</a>
            <div class="nk-two-stack-meta">${timeAgo(a.published_at)}</div>
          </div>`).join('')}
      </div>
    </div>` : `
    <div style="margin-bottom:20px">
      ${lead.image ? `<a href="${basePath}/article/${lead.slug}" class="nk-card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="nk-lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
      <a href="${basePath}/article/${lead.slug}" class="nk-lead-story-title">${esc(lead.title)}</a>
      ${lead.description ? `<p class="nk-lead-story-desc">${esc(lead.description)}</p>` : ''}
      <div class="nk-lead-story-meta">${timeAgo(lead.published_at)}</div>
    </div>`;

  const gridHtml = grid.length >= 2 ? `
    <div class="nk-three-col">
      ${grid.map(a => siteStoryCardHtml(a, basePath, site)).join('')}
    </div>` : '';

  return `
    <div class="nk-cat-section">
      <div class="nk-section-header">
        <div class="nk-section-header-left">
          <span class="nk-section-label" style="background:${color}">${label}</span>
          <span class="nk-section-h2">${label}</span>
        </div>
        <a href="${basePath}/category/${cat}" class="nk-see-all">See all →</a>
      </div>
      ${leadPlusTwo}
      ${gridHtml}
    </div>`;
}

async function siteIndex(env, site, basePath, category = null, page = 1) {
  const PAGE_SIZE = 60;
  const offset = (page - 1) * PAGE_SIZE;
  let articles = [];
  let totalCount = 0;
  const canonicalBase = (basePath === '' && site.ownDomain)
    ? 'https://' + site.ownDomain
    : 'https://gab.ae' + basePath;

  try {
    const [result, countResult] = await Promise.all([
      category
        ? env.DB.prepare("SELECT id,slug,title,description,lede,category,published_at,image FROM news WHERE status='live' AND site=? AND category=? ORDER BY published_at DESC LIMIT ? OFFSET ?").bind(site.dbSiteValue, category, PAGE_SIZE, offset).all()
        : env.DB.prepare("SELECT id,slug,title,description,lede,category,published_at,image FROM news WHERE status='live' AND site=? ORDER BY published_at DESC LIMIT ? OFFSET ?").bind(site.dbSiteValue, PAGE_SIZE, offset).all(),
      category
        ? env.DB.prepare("SELECT COUNT(*) as cnt FROM news WHERE status='live' AND site=? AND category=?").bind(site.dbSiteValue, category).first()
        : env.DB.prepare("SELECT COUNT(*) as cnt FROM news WHERE status='live' AND site=?").bind(site.dbSiteValue).first(),
    ]);
    articles = result?.results || [];
    totalCount = countResult?.cnt || 0;
  } catch (e) { console.log(`❌ siteIndex [${site.id}] error:`, e.message); }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  // ── Category page ──
  if (category) {
    const lead = articles[0];
    const two = articles.slice(1, 3);
    const rest = articles.slice(3);
    const color = siteCatColor(site, category);
    const label = siteCatLabel(site, category);
    const baseUrl = `${basePath}/category/${category}`;

    const paginationHtml = totalPages > 1 ? `
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;padding:32px 0;border-top:1px solid var(--nk-border-light);margin-top:20px">
        ${page > 1 ? `<a href="${baseUrl}?page=${page - 1}" style="padding:8px 16px;border:1px solid var(--nk-border-light);border-radius:4px;color:var(--nk-ink);font-size:14px">← Newer</a>` : '<span style="padding:8px 16px;opacity:0.3;font-size:14px">← Newer</span>'}
        <span style="font-size:14px;color:var(--nk-ink-light)">Page ${page} of ${totalPages}</span>
        ${page < totalPages ? `<a href="${baseUrl}?page=${page + 1}" style="padding:8px 16px;border:1px solid var(--nk-border-light);border-radius:4px;color:var(--nk-ink);font-size:14px">Older →</a>` : '<span style="padding:8px 16px;opacity:0.3;font-size:14px">Older →</span>'}
      </div>` : '';

    const body = articles.length === 0
      ? `<div class="nk-cat-page-header"><h1 class="nk-cat-page-title">${label}</h1></div>
         <p style="color:var(--nk-ink-light);padding:48px 0;text-align:center">No articles yet — check back soon.</p>`
      : `<div class="nk-cat-page-header">
           <div style="margin-bottom:8px"><span class="nk-section-label" style="background:${color}">${label}</span></div>
           <h1 class="nk-cat-page-title">${label}</h1>
           <div class="nk-cat-page-count">${totalCount} article${totalCount !== 1 ? 's' : ''}</div>
         </div>
         ${page === 1 && lead && two.length ? `
         <div class="nk-lead-plus-two" style="margin-bottom:28px">
           <div>
             ${lead.image ? `<a href="${basePath}/article/${lead.slug}" class="nk-card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="nk-lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
             <a href="${basePath}/article/${lead.slug}" class="nk-lead-story-title">${esc(lead.title)}</a>
             ${lead.description ? `<p class="nk-lead-story-desc">${esc(lead.description)}</p>` : ''}
             <div class="nk-lead-story-meta">${timeAgo(lead.published_at)}</div>
           </div>
           <div class="nk-two-stack">
             ${two.map(a => `
               <div class="nk-two-stack-item">
                 <a href="${basePath}/article/${a.slug}" class="nk-two-stack-title">${esc(a.title)}</a>
                 <div class="nk-two-stack-meta">${timeAgo(a.published_at)}</div>
               </div>`).join('')}
           </div>
         </div>` : page === 1 && lead ? `
         <div style="margin-bottom:28px">
           ${lead.image ? `<a href="${basePath}/article/${lead.slug}" class="nk-card-img-link"><img src="${esc(lead.image)}" alt="${esc(lead.title)}" class="nk-lead-thumb" loading="lazy" width="600" height="338"></a>` : ''}
           <a href="${basePath}/article/${lead.slug}" class="nk-lead-story-title">${esc(lead.title)}</a>
           ${lead.description ? `<p class="nk-lead-story-desc">${esc(lead.description)}</p>` : ''}
           <div class="nk-lead-story-meta">${timeAgo(lead.published_at)}</div>
         </div>` : ''}
         ${(page === 1 ? rest : articles).length > 0 ? `
         <div class="nk-three-col" style="border-top:1px solid var(--nk-border-light);padding-top:20px">
           ${(page === 1 ? rest : articles).map(a => siteStoryCardHtml(a, basePath, site)).join('')}
         </div>` : ''}
         ${paginationHtml}`;

    return new Response(siteLayout({ site,
      title: `${label}${page > 1 ? ` — Page ${page}` : ''} | ${site.name}`,
      description: `${label} news and stories from ${site.name}.`,
      canonical: `${canonicalBase}/category/${category}${page > 1 ? `?page=${page}` : ''}`,
      activeNav: category,
      basePath,
      body,
    }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
  }

  // ── Homepage ──
  if (articles.length === 0) {
    return new Response(siteLayout({ site,
      title: `${site.name} — ${site.tagline}`,
      description: site.footerTagline,
      canonical: `${canonicalBase}/`,
      activeNav: 'home',
      basePath,
      body: `<p style="color:var(--nk-ink-light);padding:80px 0;text-align:center">Content coming soon — check back soon.</p>`,
    }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
  }

  const hero = articles[0];
  const sidebar = articles.slice(1, 4);
  const remaining = articles.slice(4);

  const byCategory = new Map();
  for (const a of remaining) {
    if (!byCategory.has(a.category)) byCategory.set(a.category, []);
    byCategory.get(a.category).push(a);
  }

  const catCounts = new Map();
  for (const a of articles) catCounts.set(a.category, (catCounts.get(a.category) || 0) + 1);
  const trendingCats = [...catCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([cat]) => cat);

  const heroColor = siteCatColor(site, hero.category);
  const heroLabel = siteCatLabel(site, hero.category);

  const heroHtml = `
    <div class="nk-hero">
      <div class="nk-hero-grid">
        <div class="nk-hero-main">
          <span class="nk-cat-label" style="background:${heroColor}">${heroLabel}</span>
          ${hero.image ? `<a href="${basePath}/article/${hero.slug}" class="nk-hero-img-link"><img src="${esc(hero.image)}" alt="${esc(hero.title)}" class="nk-hero-img" loading="eager" width="860" height="484"></a>` : ''}
          <a href="${basePath}/article/${hero.slug}" class="nk-hero-headline">${esc(hero.title)}</a>
          ${hero.lede ? `<p class="nk-hero-deck">${esc(hero.lede)}</p>` : hero.description ? `<p class="nk-hero-deck">${esc(hero.description)}</p>` : ''}
          <div class="nk-hero-meta">${timeAgo(hero.published_at)}</div>
        </div>
        <div class="nk-hero-sidebar">
          ${sidebar.map(a => `
            <div class="nk-sidebar-story">
              <span class="nk-sidebar-story-cat" style="background:${siteCatColor(site, a.category)}">${siteCatLabel(site, a.category)}</span>
              <a href="${basePath}/article/${a.slug}" class="nk-sidebar-story-title">${esc(a.title)}</a>
              <div class="nk-sidebar-story-meta">${timeAgo(a.published_at)}</div>
            </div>`).join('')}
        </div>
      </div>
    </div>`;

  const trendingHtml = trendingCats.length ? `
    <div class="nk-trending-bar">
      <div class="nk-trending-inner">
        <span class="nk-trending-label">Topics</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${trendingCats.map(cat => `<a href="${basePath}/category/${cat}" class="nk-trending-tag">${siteCatLabel(site, cat)}</a>`).join('')}
        </div>
      </div>
    </div>` : '';

  const categorySectionsHtml = [...byCategory.entries()]
    .map(([cat, arts]) => siteCatSectionHtml(arts, cat, basePath, site))
    .join('');

  const body = heroHtml + trendingHtml + categorySectionsHtml;

  return new Response(siteLayout({ site,
    title: `${site.name} — ${site.tagline}`,
    description: site.footerTagline,
    canonical: `${canonicalBase}/`,
    activeNav: 'home',
    basePath,
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
}

async function siteArticlePage(env, site, slug, basePath) {
  try {
    const article = await env.DB.prepare("SELECT * FROM news WHERE slug = ? AND site = ? AND status = 'live'").bind(slug, site.dbSiteValue).first();
    if (article) {
      const html = renderArticle(article, site, basePath);
      return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
    }
  } catch (e) { console.log(`❌ siteArticlePage [${site.id}] error:`, e.message); }
  const canonicalBase = (basePath === '' && site.ownDomain) ? 'https://' + site.ownDomain : 'https://gab.ae' + basePath;
  return new Response(siteLayout({ site,
    title: `Article Not Found | ${site.name}`,
    description: 'This article could not be found.',
    canonical: `${canonicalBase}/`,
    basePath,
    body: `<p style="text-align:center;padding:80px 0;color:var(--nk-ink-light)">Article not found. <a href="${basePath || '/'}" style="color:var(--nk-accent)">Return home</a></p>`,
  }), { status: 404, headers: { 'content-type': 'text/html;charset=UTF-8' } });
}

async function siteSearchPage(env, site, q, basePath) {
  let results = [];
  const canonicalBase = (basePath === '' && site.ownDomain) ? 'https://' + site.ownDomain : 'https://gab.ae' + basePath;
  if (q.length >= 2) {
    try {
      const pattern = `%${q.toLowerCase()}%`;
      const r = await env.DB.prepare(
        "SELECT slug, title, description, lede, category, published_at, image FROM news WHERE status='live' AND site=? AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ?) ORDER BY published_at DESC LIMIT 30"
      ).bind(site.dbSiteValue, pattern, pattern, pattern).all();
      results = r?.results || [];
    } catch (e) {}
  }

  const searchForm = `
    <div style="padding:32px 0 28px;border-bottom:3px double var(--nk-border)">
      <form method="GET" action="${basePath}/search" style="display:flex;gap:10px;max-width:680px;margin:0 auto">
        <input type="search" name="q" value="${esc(q)}" placeholder="Search ${esc(site.name)}…" autofocus
          style="flex:1;font-family:'DM Sans',sans-serif;font-size:16px;padding:12px 16px;border:2px solid var(--nk-border);border-radius:4px;background:var(--nk-paper);color:var(--nk-ink);outline:none"
          onfocus="this.style.borderColor='var(--nk-accent)'" onblur="this.style.borderColor='var(--nk-border)'">
        <button type="submit" style="font-family:'DM Sans',sans-serif;font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:12px 22px;background:var(--nk-ink);color:#fff;border:none;border-radius:4px;cursor:pointer">Search</button>
      </form>
    </div>`;

  const resultsHtml = q.length < 2
    ? `<p style="padding:32px 0;color:var(--nk-ink-light);text-align:center">Enter a topic to search.</p>`
    : results.length === 0
      ? `<p style="padding:48px 0;text-align:center;color:var(--nk-ink-light)">No results for <strong>"${esc(q)}"</strong>.</p>`
      : `<p style="font-size:12px;letter-spacing:0.12em;text-transform:uppercase;color:var(--nk-ink-light);margin:24px 0 20px">${results.length} result${results.length !== 1 ? 's' : ''} for <strong style="color:var(--nk-ink)">"${esc(q)}"</strong></p>
         <div style="display:flex;flex-direction:column;gap:0">
           ${results.map(a => `
             <div style="display:flex;gap:16px;padding:16px 0;border-bottom:1px solid var(--nk-border-light);align-items:flex-start">
               ${a.image ? `<a href="${basePath}/article/${a.slug}" style="flex-shrink:0"><img src="${esc(a.image)}" alt="${esc(a.title)}" style="width:120px;height:68px;object-fit:cover;display:block" loading="lazy"></a>` : ''}
               <div style="flex:1;min-width:0">
                 <div style="margin-bottom:6px"><span style="font-size:9px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#fff;background:${siteCatColor(site, a.category)};padding:2px 8px">${siteCatLabel(site, a.category)}</span></div>
                 <a href="${basePath}/article/${a.slug}" style="font-family:'Playfair Display',Georgia,serif;font-size:18px;font-weight:700;line-height:1.3;color:var(--nk-ink);display:block;margin-bottom:5px">${esc(a.title)}</a>
                 ${(a.lede || a.description) ? `<p style="font-size:14px;color:var(--nk-ink-mid);line-height:1.5;margin-bottom:6px">${esc(a.lede || a.description)}</p>` : ''}
                 <span style="font-size:11px;color:var(--nk-ink-light)">${timeAgo(a.published_at)}</span>
               </div>
             </div>`).join('')}
         </div>`;

  const body = `<div style="max-width:860px;margin:0 auto">${searchForm}${resultsHtml}</div>`;
  return new Response(siteLayout({ site,
    title: q ? `"${q}" — Search | ${site.name}` : `Search | ${site.name}`,
    description: q ? `Search results for "${q}" on ${site.name}.` : `Search ${site.name}.`,
    canonical: `${canonicalBase}/search${q ? `?q=${encodeURIComponent(q)}` : ''}`,
    activeNav: 'search',
    basePath,
    body,
  }), { headers: { 'content-type': 'text/html;charset=UTF-8' } });
}

async function siteSitemapXml(env, site) {
  const siteBase = site.ownDomain ? 'https://' + site.ownDomain : 'https://gab.ae' + site.pathPrefix;
  try {
    const { results } = await env.DB.prepare(
      "SELECT slug, updated_at, published_at FROM news WHERE status='live' AND site=? ORDER BY published_at DESC LIMIT 1000"
    ).bind(site.dbSiteValue).all();
    const urls = results.map(r => {
      const date = (r.updated_at || r.published_at || '').slice(0, 10);
      return `  <url><loc>${siteBase}/article/${r.slug}</loc>${date ? `<lastmod>${date}</lastmod>` : ''}<changefreq>weekly</changefreq></url>`;
    }).join('\n');
    const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${siteBase}/</loc><changefreq>hourly</changefreq></url>\n${urls}\n</urlset>`;
    return new Response(xml, { headers: { 'content-type': 'application/xml;charset=UTF-8' } });
  } catch (e) {
    return new Response('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>', { headers: { 'content-type': 'application/xml' } });
  }
}

// Thin nookie wrappers — kept so existing call sites in the router don't need changing
function nookieIndex(env, basePath, category, page) { return siteIndex(env, nookieSite, basePath, category, page); }
function nookieArticlePage(env, slug, basePath) { return siteArticlePage(env, nookieSite, slug, basePath); }
function nookieSearchPage(env, q, basePath) { return siteSearchPage(env, nookieSite, q, basePath); }
function nookieSitemap(env) { return siteSitemapXml(env, nookieSite); }


// ── Public footage page (/footage/[slug]) ─────────────────────────────────────

async function sessionPage(env, series) {
  // Unlisted management page — lists all files in a session backed up to IA
  const { results } = await env.DB.prepare(
    `SELECT slug, title, tags FROM videos WHERE series = ? ORDER BY slug ASC`
  ).bind(series).all();

  const rows = results || [];

  const rowsHtml = rows.map(r => {
    let tags = {};
    try { tags = JSON.parse(r.tags || '{}'); } catch(e) {}
    const fname    = tags.filename    || r.slug;
    const iaDown   = tags.ia_download || '';
    const iaPage   = tags.ia_page     || '';
    const size     = tags.size_mb     ? `${tags.size_mb} MB` : '';
    const dur      = tags.duration_s  ? `${Math.floor(tags.duration_s/60)}m${String(tags.duration_s%60).padStart(2,'0')}s` : '';
    const dims     = (tags.width && tags.height) ? `${tags.width}×${tags.height}` : '';
    const mtype    = tags.media_type  || 'file';
    const meta     = [dur, dims, size].filter(Boolean).join(' · ');
    return `
    <tr>
      <td style="padding:10px 12px;font-size:0.85rem;font-family:monospace;word-break:break-all">${esc(fname)}</td>
      <td style="padding:10px 12px;font-size:0.8rem;color:var(--ink-light);white-space:nowrap">${esc(meta)}</td>
      <td style="padding:10px 12px;white-space:nowrap">
        ${iaDown ? `<a href="${esc(iaDown)}" target="_blank" rel="noopener"
            style="font-size:0.8rem;color:var(--ink);margin-right:10px;text-decoration:none">↓ download</a>` : ''}
        ${iaPage ? `<a href="${esc(iaPage)}" target="_blank" rel="noopener"
            style="font-size:0.8rem;color:var(--ink-light);text-decoration:none">archive.org</a>` : ''}
      </td>
    </tr>`;
  }).join('');

  const iaItem = rows.length > 0 ? (() => {
    try { return JSON.parse(rows[0].tags || '{}').ia_page || ''; } catch(e){ return ''; }
  })() : '';
  // strip filename from ia_page to get item URL
  const iaItemUrl = iaItem.replace(/\/download\/[^\/]+\/.*$/, '').replace('/download/', '/details/');

  const body = `
<article style="max-width:900px;margin:0 auto;padding:40px 20px 80px">

  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:32px">
    <div>
      <p style="font-size:0.8rem;color:var(--ink-light);margin-bottom:6px;letter-spacing:.06em;text-transform:uppercase">Session backup</p>
      <h1 style="font-size:1.5rem;font-weight:700;margin:0">${esc(series)}</h1>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      ${iaItemUrl ? `<a href="${esc(iaItemUrl)}" target="_blank" rel="noopener"
          style="padding:8px 16px;border:1px solid var(--border);border-radius:3px;font-size:0.85rem;color:var(--ink);text-decoration:none">
          View on Archive.org</a>` : ''}
    </div>
  </div>

  <p style="font-size:0.85rem;color:var(--ink-light);margin-bottom:24px">
    ${rows.length} file${rows.length !== 1 ? 's' : ''} · Raw originals · Private IA backup (noindex)
  </p>

  ${rows.length === 0 ? `<p style="color:var(--ink-light)">No files found for this session yet.</p>` : `
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:0.9rem">
      <thead>
        <tr style="border-bottom:2px solid var(--border)">
          <th style="text-align:left;padding:8px 12px;font-size:0.75rem;text-transform:uppercase;letter-spacing:.06em">File</th>
          <th style="text-align:left;padding:8px 12px;font-size:0.75rem;text-transform:uppercase;letter-spacing:.06em">Info</th>
          <th style="text-align:left;padding:8px 12px;font-size:0.75rem;text-transform:uppercase;letter-spacing:.06em">Links</th>
        </tr>
      </thead>
      <tbody style="border-bottom:1px solid var(--border)">
        ${rowsHtml}
      </tbody>
    </table>
  </div>`}

  <p style="font-size:0.75rem;color:var(--ink-light);margin-top:32px">
    This page is unlisted. Files are stored on Internet Archive as private/noindex. Not linked from nav.
  </p>

</article>`;

  const html = siteLayout({
    site: gabAeSite,
    title: `Session: ${series} | gab.ae`,
    description: `Private session backup — ${rows.length} files`,
    canonical: `https://gab.ae/footage/session/${esc(series)}`,
    basePath: '',
    body,
  });

  return new Response(html, {
    headers: {
      'content-type': 'text/html;charset=UTF-8',
      'X-Robots-Tag': 'noindex, nofollow',
    }
  });
}

async function footagePage(env, slug) {
  // Fetch from D1
  const result = await env.DB.prepare(
    `SELECT slug, title, video_url, tags FROM videos WHERE slug = ? AND status = 'vault' LIMIT 1`
  ).bind(slug).first();

  if (!result) {
    const body = `<div style="text-align:center;padding:80px 20px;color:var(--ink-light)">
      <h1 style="font-size:1.4rem;margin-bottom:12px">Not found</h1>
      <p><a href="/" style="color:var(--ink)">← Back home</a></p>
    </div>`;
    return new Response(siteLayout({ site: gabAeSite, title: 'Not Found | gab.ae',
      description: '', canonical: `https://gab.ae/footage/${esc(slug)}`, basePath: '', body }),
      { status: 404, headers: { 'content-type': 'text/html;charset=UTF-8' } });
  }

  let tags = {};
  try { tags = JSON.parse(result.tags || '{}'); } catch(e) {}

  const ytId       = tags.yt_id || '';
  const iaDownload = tags.ia_download || '';
  const iaPage     = tags.ia_page || '';
  const duration   = tags.duration_s ? `${Math.floor(tags.duration_s/60)}m ${tags.duration_s%60}s` : '';
  const dims       = (tags.width && tags.height) ? `${tags.width}×${tags.height}` : '';
  const codec      = (tags.codec || '').toUpperCase();
  const orient     = tags.orientation || '';

  const metaParts = [duration, dims, codec, orient].filter(Boolean).join(' · ');

  const body = `
<article style="max-width:720px;margin:0 auto;padding:40px 20px 80px">

  <a href="/" style="display:inline-block;margin-bottom:28px;font-size:0.85rem;color:var(--ink-light);text-decoration:none">← gab.ae</a>

  <h1 style="font-size:1.6rem;font-weight:700;line-height:1.2;margin-bottom:8px">${esc(result.title)}</h1>
  ${metaParts ? `<p style="font-size:0.85rem;color:var(--ink-light);margin-bottom:28px;letter-spacing:.02em">${esc(metaParts)}</p>` : ''}

  ${ytId ? `
  <div style="position:relative;width:100%;padding-top:${orient==='vertical'?'177.78%':'56.25%'};background:#000;border-radius:4px;overflow:hidden;margin-bottom:28px">
    <iframe
      src="https://www.youtube.com/embed/${esc(ytId)}?autoplay=0&rel=0"
      style="position:absolute;top:0;left:0;width:100%;height:100%;border:0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen></iframe>
  </div>` : ''}

  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:40px">
    ${ytId ? `<a href="https://www.youtube.com/watch?v=${esc(ytId)}" target="_blank" rel="noopener"
        style="display:inline-flex;align-items:center;gap:6px;padding:10px 18px;background:#ff0000;color:#fff;border-radius:3px;font-size:0.9rem;font-weight:600;text-decoration:none">
        ▶ Watch on YouTube</a>` : ''}
    ${iaDownload ? `<a href="${esc(iaDownload)}" target="_blank" rel="noopener"
        style="display:inline-flex;align-items:center;gap:6px;padding:10px 18px;background:var(--ink);color:#fff;border-radius:3px;font-size:0.9rem;font-weight:600;text-decoration:none">
        ↓ Download original</a>` : ''}
    ${iaPage ? `<a href="${esc(iaPage)}" target="_blank" rel="noopener"
        style="display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border:1px solid var(--border);color:var(--ink);border-radius:3px;font-size:0.9rem;text-decoration:none">
        Archive.org page</a>` : ''}
  </div>

  <p style="font-size:0.8rem;color:var(--ink-light)">
    Original footage by <strong>Gab Dancause</strong>.
    ${iaDownload ? 'Original file available for download above.' : ''}
  </p>

</article>`;

  const html = siteLayout({
    site: gabAeSite,
    title: `${result.title} | gab.ae`,
    description: `${metaParts} — original footage by Gab Dancause.`,
    canonical: `https://gab.ae/footage/${esc(slug)}`,
    basePath: '',
    body,
  });

  return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8' } });
}
