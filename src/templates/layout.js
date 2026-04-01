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
        <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Our Sites</h3>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-x-6 gap-y-2 text-sm">
          <a href="https://westmountfundamentals.com" class="text-gray-400 hover:text-white transition-colors">📊 Westmount Fundamentals</a>
          <a href="https://firemaths.info" class="text-gray-400 hover:text-white transition-colors">🔥 Firemaths</a>
          <a href="https://siliconbased.dev" class="text-gray-400 hover:text-white transition-colors">⚡ SiliconBased</a>
          <a href="https://bodycount.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">❤️ Body Count</a>
          <a href="https://thenookienook.com" class="text-gray-400 hover:text-white transition-colors">💜 The Nookie Nook</a>
          <a href="https://migratingmammals.com" class="text-gray-400 hover:text-white transition-colors">🌍 Migrating Mammals</a>
          <a href="https://ijustwantto.live" class="text-gray-400 hover:text-white transition-colors">🏠 I Just Want To Live</a>
          <a href="https://28grams.vip" class="text-gray-400 hover:text-white transition-colors">🍳 28 Grams</a>
          <a href="https://leeroyjenkins.quest" class="text-gray-400 hover:text-white transition-colors">🎮 Leeroy Jenkins</a>
          <a href="https://sendnerds.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">📚 Send Nerds</a>
          <a href="https://getthebag.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">💼 Get The Bag</a>
          <a href="https://fixitwithducttape.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">🔧 Fix It With Duct Tape</a>
          <a href="https://justonemoment.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">⏱️ Just One Moment</a>
          <a href="https://papyruspeople.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">📝 Papyrus People</a>
          <a href="https://eeniemeenie.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">🎲 Eenie Meenie</a>
          <a href="https://pleasestartplease.photonbuilder.com" class="text-gray-400 hover:text-white transition-colors">🚗 Please Start Please</a>
          <a href="https://aliimperiale.com" class="text-gray-400 hover:text-white transition-colors">✨ Ali Imperiale</a>
          <a href="https://aubergedenosaieux.com" class="text-gray-400 hover:text-white transition-colors">🏔️ Auberge de nos Aïeux</a>
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
