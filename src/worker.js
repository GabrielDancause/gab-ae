import { layout, esc } from './templates/layout.js';
import { renderCalculator } from './engines/calculator.js';
import { renderNews } from './engines/news.js';
import { renderChangelog } from './engines/changelog.js';

const ENGINES = {
  calculator: renderCalculator,
};

export default {
  async fetch(request, env) {
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

    // SEO Dashboard API
    if (path === '/api/seo-dashboard') {
      return seoDashboardAPI(env);
    }

    // Search API
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
          const html = renderNews(article);
          return new Response(html, { headers: { 'content-type': 'text/html;charset=UTF-8', 'cache-control': 'public, max-age=300' } });
        }
      } catch (e) {}
    }

    // Strip leading slash for slug lookup
    const slug = path.slice(1);

    // Look up page in D1
    try {
      const page = await env.DB.prepare('SELECT * FROM pages WHERE slug = ? AND status = ?')
        .bind(slug, 'live')
        .first();

      if (!page) {
        return notFound();
      }

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
    var date = a.published_at ? new Date(a.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
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
  // Get counts & categories
  let pageCount = 0;
  let categoryBreakdown = [];
  try {
    const countResult = await env.DB.prepare("SELECT COUNT(*) as count FROM pages WHERE status = 'live'").first();
    pageCount = countResult?.count || 0;
    const catResult = await env.DB.prepare("SELECT category, COUNT(*) as count FROM pages WHERE status = 'live' GROUP BY category ORDER BY count DESC").all();
    categoryBreakdown = catResult?.results || [];
  } catch (e) {}

  // Popular tools (high-value pages)
  let popularPages = [];
  try {
    const pop = await env.DB.prepare("SELECT slug, title, description, category FROM pages WHERE status = 'live' ORDER BY published_at ASC LIMIT 8").all();
    popularPages = pop?.results || [];
  } catch (e) {}

  // Per-category featured (top 6 per category, top 4 categories)
  const topCats = categoryBreakdown.slice(0, 6);
  const catSections = [];
  for (const cat of topCats) {
    try {
      const pages = await env.DB.prepare("SELECT slug, title, description FROM pages WHERE status = 'live' AND category = ? ORDER BY published_at ASC LIMIT 6").bind(cat.category).all();
      catSections.push({ name: cat.category, count: cat.count, pages: pages?.results || [] });
    } catch (e) {}
  }

  // Latest news
  let latestNews = [];
  try {
    const newsResult = await env.DB.prepare("SELECT slug, title, description, category, image, image_alt, published_at FROM news WHERE status='live' ORDER BY published_at DESC LIMIT 6").all();
    latestNews = newsResult?.results || [];
  } catch (e) {}

  // Category icons (15 categories — no "general")
  const catIcons = {
    finance: '💰', math: '🔢', health: '🏥', education: '📚',
    lifestyle: '🏠', gaming: '🎮', construction: '🔨',
    productivity: '📊', science: '🔬', food: '🍔',
    tools: '⚙️', shipping: '📦', tech: '💻', auto: '🚗',
    sports: '⚽',
  };

  // Category nav tabs
  const catTabsHtml = categoryBreakdown.map(c => 
    `<a href="/category/${c.category}" class="flex-shrink-0 px-4 py-2 rounded-full text-sm font-medium bg-surface border border-surface-border text-gray-300 hover:bg-accent hover:text-white hover:border-accent transition-all">
      ${catIcons[c.category] || '📁'} ${c.category.charAt(0).toUpperCase() + c.category.slice(1)}
    </a>`
  ).join('');

  // Popular tools grid
  const popularHtml = popularPages.map(p => 
    `<a href="/${p.slug}" class="group block bg-surface border border-surface-border rounded-xl p-4 hover:border-accent transition-all">
      <div class="text-white font-semibold group-hover:text-accent transition-colors mb-1">${esc(p.title.replace(' | gab.ae', ''))}</div>
      <div class="text-sm text-gray-500 line-clamp-2">${esc(p.description || '').slice(0, 80)}${(p.description || '').length > 80 ? '...' : ''}</div>
      <div class="mt-2 text-xs text-gray-600 capitalize">${p.category}</div>
    </a>`
  ).join('');

  // Category sections
  const catSectionsHtml = catSections.map(cat => `
    <div class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-bold text-white flex items-center gap-2">
          <span class="w-1 h-5 bg-accent rounded-full inline-block"></span>
          ${catIcons[cat.name] || '📁'} ${cat.name.charAt(0).toUpperCase() + cat.name.slice(1)}
        </h2>
        <a href="/category/${cat.name}" class="text-sm text-accent hover:underline">${cat.count} tools →</a>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        ${cat.pages.map(p => `
          <a href="/${p.slug}" class="group flex items-start gap-3 p-3 rounded-lg hover:bg-surface-card transition-colors">
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-gray-200 group-hover:text-accent transition-colors truncate">${esc(p.title.replace(' | gab.ae', ''))}</div>
              <div class="text-xs text-gray-500 mt-0.5 line-clamp-1">${esc(p.description || '').slice(0, 60)}</div>
            </div>
          </a>`).join('')}
      </div>
    </div>`).join('');

  const body = `
    <!-- Search -->
    <div class="mt-4 mb-8">
      <div class="max-w-2xl mx-auto relative">
        <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
        <input type="text" id="search" placeholder="Search news, tools & calculators..." 
          class="w-full pl-12 pr-6 py-4 bg-surface border border-surface-border rounded-xl text-white text-lg focus:border-accent focus:outline-none transition-colors"
          autocomplete="off">
        <div id="search-results" class="absolute left-0 right-0 top-full mt-2 bg-surface-card border border-surface-border rounded-xl shadow-2xl z-50 hidden max-h-80 overflow-y-auto"></div>
      </div>
    </div>

    <!-- Latest News -->
    ${renderNewsCards(latestNews)}

    <!-- Category Tabs -->
    <div class="flex gap-2 overflow-x-auto pb-2 mb-8 scrollbar-hide">
      ${catTabsHtml}
    </div>

    <!-- Popular Tools -->
    <div class="mb-10">
      <h2 class="text-lg font-bold text-white flex items-center gap-2 mb-4">
        <span class="w-1 h-5 bg-accent rounded-full inline-block"></span>
        🔥 Popular Tools
      </h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        ${popularHtml}
      </div>
    </div>

    <!-- Category Sections -->
    ${catSectionsHtml}

    <!-- Finance -->
    <div id="finance" class="mb-10 mt-4">
      <div class="flex items-center gap-2 mb-4">
        <h2 class="text-lg font-bold text-white flex items-center gap-2">
          <span class="w-1 h-5 bg-accent rounded-full inline-block"></span>
          💰 Finance
        </h2>
      </div>
      ${renderPropertyCards()}
    </div>

    <!-- Stats footer -->
    <div class="text-center py-8 border-t border-surface-border mt-8">
      <p class="text-gray-500 text-sm">${pageCount} free tools across ${categoryBreakdown.length} categories — growing every day</p>
    </div>

    <script>
    // Live search
    const searchInput = document.getElementById('search');
    const searchResults = document.getElementById('search-results');
    let searchTimeout;

    searchInput?.addEventListener('input', function(e) {
      clearTimeout(searchTimeout);
      const q = e.target.value.trim().toLowerCase();
      if (q.length < 2) { searchResults.classList.add('hidden'); return; }
      
      searchTimeout = setTimeout(async () => {
        try {
          const resp = await fetch('/_search?q=' + encodeURIComponent(q));
          const data = await resp.json();
          if (data.results?.length) {
            searchResults.innerHTML = data.results.map(r => {
              var href = r.type === 'news' ? '/news/' + r.slug : '/' + r.slug;
              var badge = r.type === 'news' ? '<span class="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded ml-2">NEWS</span>' : '';
              return '<a href="' + href + '" class="block px-4 py-3 hover:bg-surface border-b border-surface-border last:border-0 transition-colors">' +
              '<div class="text-white font-medium">' + r.title.replace(' | gab.ae', '') + badge + '</div>' +
              '<div class="text-xs text-gray-500 capitalize">' + r.category + '</div></a>';
            }).join('');
            searchResults.classList.remove('hidden');
          } else {
            searchResults.innerHTML = '<div class="px-4 py-3 text-gray-500">No results found</div>';
            searchResults.classList.remove('hidden');
          }
        } catch(e) { searchResults.classList.add('hidden'); }
      }, 200);
    });

    document.addEventListener('click', function(e) {
      if (!searchInput?.contains(e.target) && !searchResults?.contains(e.target)) {
        searchResults?.classList.add('hidden');
      }
    });
    </script>

    <style>
    .line-clamp-1 { overflow:hidden; display:-webkit-box; -webkit-line-clamp:1; -webkit-box-orient:vertical; }
    .line-clamp-2 { overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
    .scrollbar-hide::-webkit-scrollbar { display:none; }
    .scrollbar-hide { -ms-overflow-style:none; scrollbar-width:none; }
    </style>`;

  const html = layout({
    title: 'GAB — Tools, Calculators & Answers',
    description: 'Free online tools, calculators, converters, and instant answers. Fast, simple, useful.',
    canonical: 'https://gab.ae/',
    body,
  });

  return new Response(html, {
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
    const date = a.published_at ? new Date(a.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
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
