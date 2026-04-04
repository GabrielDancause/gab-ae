/**
 * Shared HTML layout for all gab.ae pages
 */
export function layout({ title, description, canonical, schemaJson, body }) {
  const schema = schemaJson ? `<script type="application/ld+json">${JSON.stringify(schemaJson)}</script>` : '';
  
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  <link rel="canonical" href="${canonical}">
  <!-- Open Graph -->
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="gab.ae">
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(description)}">
  ${schema}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <!-- GA4 -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-24QTGCDKMH"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-24QTGCDKMH');</script>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
          colors: {
            surface: { DEFAULT: '#0a0a0a', card: '#141414', border: '#262626' },
            accent: { DEFAULT: '#3b82f6', hover: '#2563eb' },
          }
        }
      }
    }
  </script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    html { overflow-x: hidden; }
    body { font-family: 'Inter', system-ui, sans-serif; overflow-x: hidden; max-width: 100vw; }
    p, li, td, th, span, h1, h2, h3, h4, h5, h6, div, a, strong, em, blockquote {
      overflow-wrap: break-word;
      word-break: break-word;
    }
    img, video, canvas, svg { max-width: 100%; height: auto; }
    article a, .prose a, p a { color: #3b82f6; text-decoration: underline; text-underline-offset: 2px; }
    article a:hover, .prose a:hover, p a:hover { color: #60a5fa; }
    @media print {
      .no-print { display: none !important; }
      body { background: white; color: black; }
    }
    /* Seed page core styles (fallback for pages missing inline <style>) */
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
    /* Seed page links */
    .seed-section a, .seed-page a { color: #818cf8; text-decoration: underline; }
    .seed-section a:hover, .seed-page a:hover { color: #a5b4fc; }
    /* Mobile table fix — horizontal scroll */
    .seed-section table, .seed-page table, main table {
      display: block;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    .seed-section table th, .seed-section table td,
    .seed-page table th, .seed-page table td,
    main table th, main table td {
      min-width: 100px;
      white-space: normal;
    }
  </style>
</head>
<body class="bg-surface text-gray-200 min-h-screen">
  <!-- Nav -->
  <nav class="border-b border-surface-border px-4 py-3 no-print">
    <div class="max-w-5xl mx-auto flex items-center justify-between">
      <a href="/" class="text-xl font-bold text-white hover:text-accent transition-colors">GAB</a>
      <div class="flex gap-6 text-sm text-gray-400">
        <a href="/news" class="hover:text-white transition-colors">News</a>
        <a href="/resources" class="hover:text-white transition-colors">Resources</a>
      </div>
    </div>
  </nav>

  <!-- Main -->
  <main class="max-w-5xl mx-auto px-4 py-8">
    ${body}
  </main>

  <!-- Footer -->
  <footer class="border-t border-surface-border px-4 py-8 mt-16 no-print">
    <div class="max-w-5xl mx-auto">
      <div class="mb-6">
        <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Categories</h3>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-x-6 gap-y-2 text-sm">
          <a href="https://westmountfundamentals.com" class="text-gray-400 hover:text-white transition-colors">📊 Finance</a>
          <a href="https://firemaths.info" class="text-gray-400 hover:text-white transition-colors">🔥 Money & Calculators</a>
          <a href="https://siliconbased.dev" class="text-gray-400 hover:text-white transition-colors">⚡ Tech & Dev Tools</a>
          <a href="https://bodycount.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">❤️ Health</a>
          <a href="https://thenookienook.com" class="text-gray-400 hover:text-white transition-colors">💜 Sexual Health</a>
          <a href="https://migratingmammals.com" class="text-gray-400 hover:text-white transition-colors">🌍 Travel & Nomad</a>
          <a href="https://ijustwantto.live" class="text-gray-400 hover:text-white transition-colors">🏠 Home & DIY</a>
          <a href="https://28grams.vip" class="text-gray-400 hover:text-white transition-colors">🍳 Food & Cooking</a>
          <a href="https://leeroyjenkins.quest" class="text-gray-400 hover:text-white transition-colors">🎮 Gaming</a>
          <a href="https://sendnerds.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">📚 Education</a>
          <a href="https://getthebag.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">💼 Career</a>
          <a href="https://fixitwithducttape.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">🔧 AI & SaaS</a>
          <a href="https://justonemoment.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">⏱️ Timers</a>
          <a href="https://papyruspeople.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">📝 Text Tools</a>
          <a href="https://eeniemeenie.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">🎲 Random & Fun</a>
          <a href="https://pleasestartplease.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">🚗 Automotive</a>
        </div>
      </div>
      <div class="text-center text-sm text-gray-500">
        &copy; ${new Date().getFullYear()} gab.ae
      </div>
    </div>
  </footer>
</body>
</html>`;
}

export function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
