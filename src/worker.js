import { layout } from './templates/layout.js';
import { renderCalculator } from './engines/calculator.js';

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

      const engine = ENGINES[page.engine];
      if (!engine) {
        return new Response(`Unknown engine: ${page.engine}`, { status: 500 });
      }

      // Render page
      const body = engine(page);
      const schemaJson = page.schema_json ? JSON.parse(page.schema_json) : null;
      
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

async function homepage(env) {
  // Get counts
  let pageCount = 0;
  let categoryBreakdown = [];
  try {
    const countResult = await env.DB.prepare("SELECT COUNT(*) as count FROM pages WHERE status = 'live'").first();
    pageCount = countResult?.count || 0;
    
    const catResult = await env.DB.prepare("SELECT category, COUNT(*) as count FROM pages WHERE status = 'live' GROUP BY category ORDER BY count DESC LIMIT 10").all();
    categoryBreakdown = catResult?.results || [];
  } catch (e) {
    // DB might not be set up yet
  }

  // Get recent pages
  let recentPages = [];
  try {
    const recent = await env.DB.prepare("SELECT slug, title, engine, category FROM pages WHERE status = 'live' ORDER BY published_at DESC LIMIT 12").all();
    recentPages = recent?.results || [];
  } catch (e) {}

  const categoriesHtml = categoryBreakdown.map(c => 
    `<a href="/category/${c.category}" class="flex items-center justify-between px-4 py-3 bg-surface border border-surface-border rounded-lg hover:border-accent transition-colors">
      <span class="text-gray-200 capitalize">${c.category}</span>
      <span class="text-sm text-gray-500">${c.count}</span>
    </a>`
  ).join('');

  const recentHtml = recentPages.map(p =>
    `<a href="/${p.slug}" class="block px-4 py-3 bg-surface border border-surface-border rounded-lg hover:border-accent transition-colors">
      <div class="text-gray-200 font-medium">${esc(p.title)}</div>
      <div class="text-sm text-gray-500 mt-1 capitalize">${p.engine} · ${p.category}</div>
    </a>`
  ).join('');

  const body = `
    <div class="text-center mb-16 mt-8">
      <h1 class="text-4xl md:text-5xl font-bold text-white mb-4">gab.ae</h1>
      <p class="text-lg text-gray-400 mb-8">Tools, calculators, and answers. No ads, no tracking, just what you need.</p>
      <div class="max-w-xl mx-auto">
        <input type="text" id="search" placeholder="Search tools..." 
          class="w-full px-6 py-4 bg-surface border border-surface-border rounded-xl text-white text-lg focus:border-accent focus:outline-none transition-colors"
          autocomplete="off">
      </div>
    </div>

    ${pageCount > 0 ? `
    <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
      <div>
        <h2 class="text-xl font-semibold text-white mb-4">Categories</h2>
        <div class="space-y-2">${categoriesHtml}</div>
      </div>
      <div>
        <h2 class="text-xl font-semibold text-white mb-4">Recent</h2>
        <div class="space-y-2">${recentHtml}</div>
      </div>
    </div>
    ` : `
    <div class="text-center text-gray-500 py-16">
      <p class="text-lg">Building something big. Pages coming soon.</p>
      <p class="text-sm mt-2">${pageCount} pages live</p>
    </div>
    `}

    <script>
    document.getElementById('search')?.addEventListener('input', async function(e) {
      // TODO: implement search against D1
      console.log('Search:', e.target.value);
    });
    </script>`;

  const html = layout({
    title: 'gab.ae — Tools, Calculators & Answers',
    description: 'Free online tools, calculators, converters, and instant answers. No ads, no tracking.',
    canonical: 'https://gab.ae/',
    body,
  });

  return new Response(html, {
    headers: { 'content-type': 'text/html;charset=UTF-8' },
  });
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

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
