export function layout({ title, description, canonical, schemaJson, body, activeNav = '' }) {
  const schema = schemaJson ? `<script type="application/ld+json">${JSON.stringify(schemaJson)}</script>` : '';

  function navItem(href, label) {
    const slug = href.split('/').pop();
    const active = activeNav && (activeNav === slug || (activeNav === 'home' && href === '/'));
    return `<a href="${href}" class="nav-item${active ? ' active' : ''}">${label}</a>`;
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  <link rel="canonical" href="${canonical}">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="gab.ae">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(description)}">
  ${schema}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;900&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,400&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-24QTGCDKMH"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-24QTGCDKMH');</script>
  <style>
    :root {
      --ink: #111111;
      --ink-mid: #444444;
      --ink-light: #888888;
      --paper: #faf8f4;
      --paper-mid: #f0ede6;
      --paper-dark: #e8e4db;
      --accent: #c8102e;
      --accent-dark: #9a0d23;
      --border: #d4cfc5;
      --border-light: #e8e4db;
      --gap: 24px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { overflow-x: hidden; }
    body { font-family: 'DM Sans', system-ui, sans-serif; background: var(--paper); color: var(--ink); overflow-x: hidden; }
    a { color: inherit; text-decoration: none; }
    img, video, canvas, svg { max-width: 100%; height: auto; }
    p, li, h1, h2, h3, h4, h5, h6, div, a, strong, em, blockquote { overflow-wrap: break-word; word-break: break-word; }

    /* ── Masthead ── */
    .masthead { text-align: center; padding: 28px 24px 20px; border-bottom: 3px double var(--border); }
    .masthead-eyebrow { font-size: 10.5px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-light); margin-bottom: 8px; }
    .masthead-logo { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(40px, 6vw, 72px); font-weight: 900; letter-spacing: -0.02em; color: var(--ink); display: block; line-height: 1; }
    .masthead-logo:hover { color: var(--ink); }
    .masthead-tagline { font-size: 12px; color: var(--ink-light); margin-top: 8px; letter-spacing: 0.1em; }

    /* ── Primary nav ── */
    .primary-nav { background: var(--ink); position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 12px rgba(0,0,0,0.15); }
    .primary-nav-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; overflow-x: auto; scrollbar-width: none; }
    .primary-nav-inner::-webkit-scrollbar { display: none; }
    .nav-item { font-size: 12px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.7); padding: 14px 15px; border-bottom: 3px solid transparent; white-space: nowrap; transition: color 0.2s, border-color 0.2s; display: block; }
    .nav-item:hover, .nav-item.active { color: #fff; border-bottom-color: var(--accent); }

    /* ── Site container ── */
    .site-main { max-width: 1280px; margin: 0 auto; padding: 0 24px; }

    /* ── Hero section ── */
    .hero-section { padding: 28px 0 0; }
    .hero-grid { display: grid; grid-template-columns: 1fr 300px; gap: var(--gap); }
    .hero-main { border-right: 1px solid var(--border); padding-right: var(--gap); }
    .hero-cat-label { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; margin-bottom: 14px; }
    .hero-headline { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(26px, 3vw, 40px); font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; color: var(--ink); display: block; margin-bottom: 14px; }
    .hero-headline:hover { color: var(--accent); }
    .hero-deck { font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; font-weight: 300; color: var(--ink-mid); line-height: 1.6; margin-bottom: 12px; }
    .hero-meta { font-size: 12px; color: var(--ink-light); }
    .hero-sidebar { display: flex; flex-direction: column; }
    .sidebar-story { padding: 13px 0; border-bottom: 1px solid var(--border-light); }
    .sidebar-story:last-child { border-bottom: none; }
    .sidebar-story-cat { font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: #fff; padding: 2px 8px; margin-bottom: 6px; display: inline-block; }
    .sidebar-story-title { font-family: 'Playfair Display', Georgia, serif; font-size: 16px; font-weight: 700; line-height: 1.3; color: var(--ink); display: block; }
    .sidebar-story-title:hover { color: var(--accent); }
    .sidebar-story-meta { font-size: 11px; color: var(--ink-light); margin-top: 5px; }

    /* ── Images ── */
    .hero-img-link { display: block; }
    .hero-img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 16px; }
    .card-img-link { display: block; }
    .lead-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 10px; }
    .card-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 8px; }
    .article-hero-img { margin: 0 0 28px; }
    .article-hero-img img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }

    /* ── Trending bar ── */
    .trending-bar { background: var(--paper-mid); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 12px 0; margin: 24px 0; }
    .trending-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
    .trending-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--accent); flex-shrink: 0; }
    .trending-tag { font-size: 12px; color: var(--ink-mid); border: 1px solid var(--border); border-radius: 20px; padding: 4px 13px; transition: background 0.15s, color 0.15s; }
    .trending-tag:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

    /* ── Category sections ── */
    .cat-section { padding: 28px 0; border-bottom: 1px solid var(--border); }
    .section-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid var(--ink); padding-bottom: 10px; margin-bottom: 20px; }
    .section-header-left { display: flex; align-items: center; gap: 10px; }
    .section-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; }
    .section-h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; color: var(--ink); }
    .see-all { font-size: 12px; color: var(--ink-light); }
    .see-all:hover { color: var(--accent); }
    .lead-plus-two { display: grid; grid-template-columns: 1fr 260px; gap: var(--gap); margin-bottom: 20px; }
    .lead-story-title { font-family: 'Playfair Display', Georgia, serif; font-size: 23px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.25; color: var(--ink); display: block; margin-bottom: 8px; }
    .lead-story-title:hover { color: var(--accent); }
    .lead-story-desc { font-family: 'Source Serif 4', Georgia, serif; font-size: 14.5px; color: var(--ink-mid); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .lead-story-meta { font-size: 11px; color: var(--ink-light); margin-top: 8px; }
    .two-stack { border-left: 1px solid var(--border-light); padding-left: var(--gap); display: flex; flex-direction: column; }
    .two-stack-item { padding: 10px 0; border-bottom: 1px solid var(--border-light); }
    .two-stack-item:last-child { border-bottom: none; }
    .two-stack-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 700; line-height: 1.3; color: var(--ink); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .two-stack-title:hover { color: var(--accent); }
    .two-stack-meta { font-size: 11px; color: var(--ink-light); margin-top: 5px; }
    .three-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gap); border-top: 1px solid var(--border-light); padding-top: 20px; }
    .story-card-title { font-family: 'Playfair Display', Georgia, serif; font-size: 17px; font-weight: 700; line-height: 1.3; color: var(--ink); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin-bottom: 6px; }
    .story-card-title:hover { color: var(--accent); }
    .story-card-desc { font-family: 'Source Serif 4', Georgia, serif; font-size: 13.5px; color: var(--ink-mid); line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .story-card-meta { font-size: 11px; color: var(--ink-light); margin-top: 6px; }

    /* ── Article page ── */
    .tp-article { max-width: 720px; margin: 0 auto; padding: 40px 24px 60px; }
    .article-back { font-size: 13px; color: var(--accent); display: inline-block; margin-bottom: 24px; }
    .article-back:hover { text-decoration: underline; }
    .article-meta-top { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
    .article-cat-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; }
    .article-date { font-size: 12px; color: var(--ink-light); }
    .article-headline { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(26px, 3.5vw, 38px); font-weight: 900; letter-spacing: -0.02em; line-height: 1.15; color: var(--ink); margin-bottom: 18px; }
    .article-lede { font-family: 'Source Serif 4', Georgia, serif; font-size: 18px; font-weight: 300; color: var(--ink-mid); line-height: 1.65; border-left: 4px solid var(--accent); padding-left: 20px; margin-bottom: 28px; }
    .article-body h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 21px; font-weight: 700; color: var(--ink); margin-top: 34px; margin-bottom: 13px; padding-top: 8px; border-top: 2px solid var(--border); }
    .article-body p { font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; line-height: 1.7; color: var(--ink-mid); margin-bottom: 18px; }
    .article-body a { color: var(--accent); text-decoration: underline; }
    .article-body a:hover { color: var(--accent-dark); }
    .article-faq { margin-top: 48px; border-top: 2px solid var(--border); padding-top: 28px; }
    .article-faq h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; margin-bottom: 20px; color: var(--ink); }
    .faq-item { border-bottom: 1px solid var(--border-light); }
    .faq-item summary { font-size: 15px; font-weight: 600; color: var(--ink); padding: 14px 0; cursor: pointer; list-style: none; display: flex; align-items: center; gap: 8px; }
    .faq-item summary::-webkit-details-marker { display: none; }
    .faq-item summary::before { content: '▸'; color: var(--accent); transition: transform 0.2s; flex-shrink: 0; }
    .faq-item[open] summary::before { transform: rotate(90deg); }
    .faq-item p { font-family: 'Source Serif 4', Georgia, serif; font-size: 15px; color: var(--ink-mid); padding: 0 0 14px 22px; line-height: 1.65; }
    .article-tags { margin-top: 28px; display: flex; flex-wrap: wrap; gap: 8px; }
    .article-tag { font-size: 12px; color: var(--ink-mid); border: 1px solid var(--border); border-radius: 20px; padding: 4px 12px; }
    .article-tag:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
    .article-sources { margin-top: 28px; border-top: 1px solid var(--border); padding-top: 16px; }
    .article-sources-label { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-light); margin-bottom: 10px; }
    .article-sources a { font-size: 12px; color: var(--accent); }
    .article-sources a:hover { text-decoration: underline; }
    .article-sources span { font-size: 12px; color: var(--ink-light); }
    .article-readtime { font-size: 12px; color: var(--ink-light); }
    .article-takeaways { background: var(--paper-mid); border: 1px solid var(--border); border-top: 3px solid var(--ink); border-radius: 0 0 6px 6px; padding: 18px 22px; margin: 0 0 28px; }
    .takeaways-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-light); margin-bottom: 10px; }
    .article-takeaways ul { padding-left: 18px; }
    .article-takeaways li { font-family: 'Source Serif 4', Georgia, serif; font-size: 15px; line-height: 1.6; color: var(--ink-mid); margin-bottom: 6px; }
    .article-takeaways li:last-child { margin-bottom: 0; }
    .article-keystat { display: flex; align-items: baseline; gap: 14px; background: var(--paper-mid); border-left: 4px solid var(--accent); border-radius: 0 8px 8px 0; padding: 16px 20px; margin: 0 0 28px; }
    .keystat-value { font-family: 'Playfair Display', Georgia, serif; font-size: 2rem; font-weight: 900; color: var(--accent); flex-shrink: 0; line-height: 1; }
    .keystat-label { font-size: 14px; color: var(--ink-mid); line-height: 1.4; }
    .article-body > div:first-child > p:first-child { font-size: 18px; line-height: 1.7; color: var(--ink); }
    .article-pullquote { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(18px, 2.5vw, 22px); font-style: italic; font-weight: 600; color: var(--ink); border-top: 2px solid var(--ink); border-bottom: 2px solid var(--ink); padding: 20px 4px; margin: 32px 0; text-align: center; line-height: 1.45; }
    .article-section-divider { border: none; border-top: 1px solid var(--border); margin: 32px 0 0; }

    /* ── Category page header ── */
    .cat-page-header { padding: 32px 0 24px; border-bottom: 2px solid var(--ink); margin-bottom: 28px; }
    .cat-page-title { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(28px, 4vw, 44px); font-weight: 700; color: var(--ink); margin-bottom: 6px; }
    .cat-page-count { font-size: 13px; color: var(--ink-light); }

    /* ── Footer ── */
    .site-footer { background: var(--ink); padding: 40px 24px; margin-top: 48px; }
    .footer-inner { max-width: 1280px; margin: 0 auto; }
    .footer-logo { font-family: 'Playfair Display', Georgia, serif; font-size: 28px; font-weight: 900; color: #fff; display: block; margin-bottom: 5px; }
    .footer-tagline { font-size: 12px; color: rgba(255,255,255,0.35); margin-bottom: 24px; }
    .footer-cats { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-bottom: 28px; }
    .footer-cat { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.45); }
    .footer-cat:hover { color: #fff; }
    .footer-bottom { border-top: 1px solid rgba(255,255,255,0.1); padding-top: 16px; font-size: 11.5px; color: rgba(255,255,255,0.25); }

    /* ── Seed/tool page styles (legacy content) ── */
    .seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; color: var(--ink); }
    .seed-page h1 { font-family: 'Playfair Display', Georgia, serif; font-size: 1.75rem; font-weight: 800; color: var(--ink); margin-bottom: 0.5rem; line-height: 1.2; }
    .seed-meta { font-size: 0.8rem; color: var(--ink-light); margin-bottom: 2rem; }
    .seed-section { background: var(--paper-mid); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
    .seed-section h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 1.15rem; font-weight: 700; color: #3a2060; margin-bottom: 0.75rem; }
    .seed-section h3 { font-size: 1rem; font-weight: 600; color: var(--ink); margin-bottom: 0.5rem; }
    .seed-section p { font-family: 'Source Serif 4', Georgia, serif; font-size: 0.95rem; line-height: 1.7; color: var(--ink-mid); margin-bottom: 0.5rem; }
    .seed-section ul, .seed-section ol { padding-left: 1.25rem; color: var(--ink-mid); font-size: 0.95rem; line-height: 1.8; }
    .seed-stat { display: flex; align-items: baseline; gap: 0.75rem; padding: 1rem; background: var(--paper-dark); border-radius: 8px; margin-bottom: 0.75rem; flex-wrap: wrap; }
    .seed-stat .stat-value { font-size: 1.5rem; font-weight: 800; color: var(--accent); flex-shrink: 0; }
    .seed-stat .stat-label { font-size: 0.9rem; color: var(--ink-mid); min-width: 0; }
    .seed-takeaway { background: var(--paper-dark); border-left: 3px solid var(--accent); border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
    .seed-takeaway p { color: var(--ink); font-weight: 500; }
    .seed-pros { background: #f0faf0; border: 1px solid #c8e6c8; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 0.5rem; }
    .seed-pros h3 { color: #1a5c30; }
    .seed-cons { background: #fdf0f0; border: 1px solid #e8c8c8; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 0.5rem; }
    .seed-cons h3 { color: #8a2020; }
    .seed-explore { text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: var(--ink-light); }
    .seed-explore a { color: var(--accent); text-decoration: underline; }
    .seed-section a, .seed-page a { color: var(--accent); text-decoration: underline; }
    .seed-section a:hover, .seed-page a:hover { color: var(--accent-dark); }
    .seed-section table, .seed-page table, main table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .seed-section table th, .seed-section table td, .seed-page table th, .seed-page table td, main table th, main table td { min-width: 100px; white-space: normal; }

    /* ── Responsive ── */
    @media (max-width: 900px) {
      .hero-grid { grid-template-columns: 1fr; }
      .hero-main { border-right: none; padding-right: 0; border-bottom: 1px solid var(--border); padding-bottom: var(--gap); }
      .lead-plus-two { grid-template-columns: 1fr; }
      .two-stack { border-left: none; padding-left: 0; border-top: 1px solid var(--border-light); padding-top: 16px; }
      .three-col { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 600px) {
      .three-col { grid-template-columns: 1fr; }
      .masthead { padding: 20px 16px; }
      .primary-nav-inner { padding: 0 12px; }
      .site-main { padding: 0 16px; }
    }
    @media print {
      .primary-nav, .site-footer { display: none; }
      body { background: white; color: black; }
    }
  </style>
</head>
<body>
  <header class="masthead">
    <div class="masthead-eyebrow">Independent News &amp; Analysis</div>
    <a href="/" class="masthead-logo">GAB.AE</a>
    <div class="masthead-tagline">All the stories that matter</div>
  </header>

  <nav class="primary-nav">
    <div class="primary-nav-inner">
      <a href="/search" class="nav-item" title="Search" style="font-size:18px">&#x2315;</a>
      ${navItem('/', 'Home')}
      ${navItem('/news/category/us', 'U.S.')}
      ${navItem('/news/category/world', 'World')}
      ${navItem('/news/category/politics', 'Politics')}
      ${navItem('/news/category/business', 'Business')}
      ${navItem('/news/category/tech', 'Tech')}
      ${navItem('/news/category/health', 'Health')}
      ${navItem('/news/category/science', 'Science')}
      ${navItem('/news/category/entertainment', 'Entertainment')}
      ${navItem('/news/category/sports', 'Sports')}
      ${navItem('/news/category/climate', 'Climate')}
      ${navItem('/news/category/travel', 'Travel')}
    </div>
  </nav>

  <main class="site-main">
    ${body}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <a href="/" class="footer-logo">GAB.AE</a>
      <div class="footer-tagline">Breaking news and analysis, updated daily.</div>
      <div class="footer-cats">
        <a href="/news/category/us" class="footer-cat">U.S.</a>
        <a href="/news/category/world" class="footer-cat">World</a>
        <a href="/news/category/politics" class="footer-cat">Politics</a>
        <a href="/news/category/business" class="footer-cat">Business</a>
        <a href="/news/category/tech" class="footer-cat">Tech</a>
        <a href="/news/category/health" class="footer-cat">Health</a>
        <a href="/news/category/science" class="footer-cat">Science</a>
        <a href="/news/category/entertainment" class="footer-cat">Entertainment</a>
        <a href="/news/category/sports" class="footer-cat">Sports</a>
        <a href="/news/category/climate" class="footer-cat">Climate</a>
        <a href="/news/category/travel" class="footer-cat">Travel</a>
      </div>
      <div class="footer-bottom">&copy; ${new Date().getFullYear()} gab.ae &middot; Independent journalism powered by AI</div>
    </div>
  </footer>
</body>
</html>`;
}

export function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
