import { layout, esc } from './templates/layout.js';
import { renderCalculator } from './engines/calculator.js';
import { renderNews } from './engines/news.js';
import { renderChangelog } from './engines/changelog.js';
import { newsAutopilot } from './news-autopilot.js';
import { seedPages } from './seed-pages.js';
import { upgradeTrigger } from './upgrade-trigger.js';
import { llmNews } from './llm-news.js';
import { llmSeedPages } from './llm-seed-pages.js';

const ENGINES = {
  calculator: renderCalculator,
};


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
  async scheduled(event, env, ctx) {
    // LLM-powered content generation (Haiku)
    try {
      await llmNews(env);
    } catch (e) {
      console.log(`❌ LLM News error: ${e.message}`);
    }

    try {
      await llmSeedPages(env);
    } catch (e) {
      console.log(`❌ LLM Seed Pages error: ${e.message}`);
    }

    // Reset daily views at midnight UTC (first cron run of the day)
    const nowHour = new Date().getUTCHours();
    const nowMin = new Date().getUTCMinutes();
    if (nowHour === 0 && nowMin < 5) {
      await resetDailyViews(env);
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
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, '') || '/';

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
        const result = await seedPages(env);
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
        const existing = await env.DB.prepare("SELECT slug FROM pages WHERE slug = ? AND status = 'live'").bind(slug).first();
        if (existing) {
          return new Response(JSON.stringify({ slug, existing: true }), { headers: { 'content-type': 'application/json' } });
        }

        // Import and call the LLM seed page generator
        const apiKey = env.ANTHROPIC_API_KEY;
        if (!apiKey) {
          return new Response(JSON.stringify({ error: 'API not configured' }), { status: 500, headers: { 'content-type': 'application/json' } });
        }

        // Call Haiku directly
        const resp = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: { 'x-api-key': apiKey, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
          body: JSON.stringify({
            model: 'claude-haiku-4-5-20251001',
            max_tokens: 4096,
            messages: [{ role: 'user', content: `Create a comprehensive, expert-quality page about "${keyword}".

Return ONLY raw HTML using these CSS classes (no markdown, no backticks):

The page should include:
- Detailed explanation of what "${keyword}" is
- Key facts, data points, or comparisons
- A reference table if applicable
- Practical recommendations
- 3-5 FAQs that real people search for

Use this structure:
<style>
.seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #e2e8f0; }
.seed-page h1 { font-size: 1.75rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; line-height: 1.2; }
.seed-meta { font-size: 0.8rem; color: #64748b; margin-bottom: 2rem; }
.seed-section { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.seed-section h2 { font-size: 1.15rem; font-weight: 700; color: #818cf8; margin-bottom: 0.75rem; }
.seed-section h3 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem; }
.seed-section p { font-size: 0.95rem; line-height: 1.7; color: #94a3b8; margin-bottom: 0.5rem; }
.seed-section ul, .seed-section ol { padding-left: 1.25rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.8; }
.seed-compare-table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
.seed-compare-table th, .seed-compare-table td { padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid #1e1e2e; }
.seed-compare-table th { color: #818cf8; font-weight: 600; }
.seed-compare-table td { color: #94a3b8; }
</style>
<div class="seed-page">
  <h1>Compelling title about ${keyword}</h1>
  <p class="seed-meta">Updated ${new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</p>
  [sections with seed-section class]
  [FAQ section]
</div>

Rules:
- Write like a human expert — no template filler
- Do NOT include JavaScript, script tags, or interactive elements
- Minimum 2000 characters of content
- null over fake data` }],
          }),
        });
        const aiData = await resp.json();
        if (aiData.error) {
          return new Response(JSON.stringify({ error: 'AI generation failed' }), { status: 500, headers: { 'content-type': 'application/json' } });
        }

        let html = aiData.content?.[0]?.text || '';
        // Strip markdown code fences (```html ... ```)
        html = html.replace(/^```html?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
        // Fix wrong dates from Haiku (training data cutoff)
        const currentDate = new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
        html = html.replace(/Updated\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}/gi, 'Updated ' + currentDate);

        if (!html.includes('seed-page') || html.length < 500) {
          return new Response(JSON.stringify({ error: 'Generated content too short or invalid' }), { status: 500, headers: { 'content-type': 'application/json' } });
        }

        // Extract title from h1
        const h1 = (html.match(/<h1[^>]*>(.*?)<\/h1>/) || [])[1] || keyword;
        const title = h1.replace(/<[^>]+>/g, '').trim() + ' | gab.ae';
        const now = new Date().toISOString().replace('T', ' ').slice(0, 19);

        // Insert
        await env.DB.prepare(
          "INSERT INTO pages (slug, title, description, category, engine, html, status, quality, keyword, page_type, published_at, updated_at, created_at) VALUES (?, ?, ?, 'on-demand', 'llm-haiku', ?, 'live', 'llm', ?, 'educational', ?, ?, ?)"
        ).bind(slug, title, "Everything about " + keyword, html, keyword, now, now, now).run();

        return new Response(JSON.stringify({ slug, title: h1 }), { headers: { 'content-type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: { 'content-type': 'application/json' } });
      }
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
        return notFound();
      }

      ctx.waitUntil(trackView(env, slug));

      let body;
      let schemaJson = page.schema_json ? JSON.parse(page.schema_json) : null;

      if (page.html) {
        // Full HTML page stored in D1 — serve directly in layout shell
        body = page.html;
      } else {
        // Legacy config-driven engine
        const engine = ENGINES[page.engine];
        if (!engine) {
          return new Response(`Unknown engine: ${page.engine}`, { status: 500 });
        }
        body = engine(page);
      }
      
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
      btn.textContent = 'Creating...';
      status.classList.remove('hidden');
      status.textContent = '\u23f3 Generating your page \u2014 this takes about 10 seconds...';
      status.className = 'mt-3 text-sm text-accent text-center';

      try {
        var resp = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ keyword: keyword }),
        });
        var data = await resp.json();
        if (data.slug) {
          status.textContent = '\u2705 Page created! Redirecting...';
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
    description: 'My team of robots and I love to answer questions and give information. Ask anything.',
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
  } catch (e) {}

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
    title: category ? `${category.charAt(0).toUpperCase() + category.slice(1)} News | GAB` : 'News | GAB',
    description: 'Latest news, breaking stories and analysis.',
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
      return notFound();
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
      description: `Free ${category} tools, calculators, and resources. Fast, simple, useful.`,
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

// ─── View tracking ───
async function trackView(env, slug) {
  try {
    await env.DB.prepare(
      `INSERT INTO view_counts (slug, views_24h, views_total, last_reset) 
       VALUES (?, 1, 1, datetime('now'))
       ON CONFLICT(slug) DO UPDATE SET views_24h = views_24h + 1, views_total = views_total + 1`
    ).bind(slug).run();
  } catch (e) {
    // Non-critical — don't break page loads
  }
}

async function resetDailyViews(env) {
  try {
    await env.DB.prepare("UPDATE view_counts SET views_24h = 0, last_reset = datetime('now')").run();
    console.log('🔄 Daily view counts reset');
  } catch (e) {
    console.log(`❌ View reset error: ${e.message}`);
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
      "SELECT slug, title, category, page_type, keyword_volume, created_at FROM pages WHERE status='live' AND engine='llm-haiku' ORDER BY created_at DESC LIMIT 10"
    ).all();
    latestPages = results || [];
  } catch {}

  // Get most popular pages (from view_counts, last 24h)
  let popularPages = [];
  try {
    const { results } = await env.DB.prepare(
      `SELECT vc.slug, vc.views_24h, p.title, p.category, p.page_type, p.keyword_volume, p.created_at
       FROM view_counts vc 
       JOIN pages p ON vc.slug = p.slug 
       WHERE vc.views_24h > 0 AND p.status = 'live'
       ORDER BY vc.views_24h DESC LIMIT 10`
    ).all();
    popularPages = results || [];
  } catch {}
  
  // Also check news views
  try {
    const { results } = await env.DB.prepare(
      `SELECT vc.slug, vc.views_24h, n.title, n.category, 'news' as page_type, 0 as keyword_volume, n.published_at as created_at
       FROM view_counts vc 
       JOIN news n ON ('news/' || n.slug) = vc.slug 
       WHERE vc.views_24h > 0 AND n.status = 'live'
       ORDER BY vc.views_24h DESC LIMIT 10`
    ).all();
    popularPages = [...popularPages, ...(results || [])].sort((a, b) => b.views_24h - a.views_24h).slice(0, 10);
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
  const latestHtml = (latestPages.length > 0 || hasPopular) ? `
    <div class="mb-8">
      <div class="flex gap-2 mb-4">
        <button onclick="document.getElementById('tab-recent').style.display='block';document.getElementById('tab-popular').style.display='none';this.classList.add('bg-accent','text-white');this.classList.remove('bg-surface','text-gray-400');this.nextElementSibling.classList.remove('bg-accent','text-white');this.nextElementSibling.classList.add('bg-surface','text-gray-400')" class="px-4 py-1.5 rounded-full text-sm font-medium bg-accent text-white border border-surface-border transition-all">🆕 Recently Published</button>
        <button onclick="document.getElementById('tab-popular').style.display='block';document.getElementById('tab-recent').style.display='none';this.classList.add('bg-accent','text-white');this.classList.remove('bg-surface','text-gray-400');this.previousElementSibling.classList.remove('bg-accent','text-white');this.previousElementSibling.classList.add('bg-surface','text-gray-400')" class="px-4 py-1.5 rounded-full text-sm font-medium bg-surface text-gray-400 border border-surface-border transition-all">🔥 Most Popular (24h)</button>
      </div>
      <div id="tab-recent" class="space-y-3">
        ${latestPages.length > 0 ? renderPageList(latestPages) : '<p class="text-gray-500 text-sm">No pages yet — check back soon.</p>'}
      </div>
      <div id="tab-popular" class="space-y-3" style="display:none">
        ${hasPopular ? renderPageList(popularPages, true) : '<p class="text-gray-500 text-sm">No view data yet — analytics sync coming soon.</p>'}
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
    description: 'Free tools, calculators, guides, and data across finance, tech, health, travel, and more.',
    canonical: 'https://gab.ae/resources',
    body,
  });
  return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
}

function notFound() {
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
