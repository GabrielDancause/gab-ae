export function nookieLayout({ title, description, canonical, schemaJson, body, activeNav = '', basePath = '/thenookienook' }) {
  const schema = schemaJson ? `<script type="application/ld+json">${JSON.stringify(schemaJson)}</script>` : '';

  function navItem(href, label) {
    const active = activeNav && (href.includes(activeNav) || (activeNav === 'home' && href === basePath + '/'));
    return `<a href="${href}" class="nk-nav-item${active ? ' active' : ''}">${label}</a>`;
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${nkEsc(title)}</title>
  <meta name="description" content="${nkEsc(description)}">
  <link rel="canonical" href="${canonical}">
  <meta property="og:title" content="${nkEsc(title)}">
  <meta property="og:description" content="${nkEsc(description)}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="The Nookie Nook">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${nkEsc(title)}">
  <meta name="twitter:description" content="${nkEsc(description)}">
  ${schema}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;900&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,400&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-24QTGCDKMH"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-24QTGCDKMH');</script>
  <style>
    :root {
      --nk-ink: #1e0a2e;
      --nk-ink-mid: #4a3568;
      --nk-ink-light: #9080b5;
      --nk-paper: #fdf8ff;
      --nk-paper-mid: #f5eeff;
      --nk-paper-dark: #ead9ff;
      --nk-accent: #c44ad9;
      --nk-accent-dark: #9b35b5;
      --nk-border: #d5c8e8;
      --nk-border-light: #e8d9ff;
      --nk-gap: 24px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { overflow-x: hidden; }
    body { font-family: 'DM Sans', system-ui, sans-serif; background: var(--nk-paper); color: var(--nk-ink); overflow-x: hidden; }
    a { color: inherit; text-decoration: none; }
    img, video, canvas, svg { max-width: 100%; height: auto; }
    p, li, h1, h2, h3, h4, h5, h6, div, a, strong, em, blockquote { overflow-wrap: break-word; word-break: break-word; }

    /* ── Masthead ── */
    .nk-masthead { text-align: center; padding: 28px 24px 20px; border-bottom: 3px double var(--nk-border); background: var(--nk-paper); }
    .nk-masthead-eyebrow { font-size: 10.5px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--nk-ink-light); margin-bottom: 8px; }
    .nk-masthead-logo { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(32px, 5vw, 60px); font-weight: 900; letter-spacing: -0.02em; color: var(--nk-ink); display: block; line-height: 1; }
    .nk-masthead-logo:hover { color: var(--nk-accent); transition: color 0.2s; }
    .nk-masthead-tagline { font-size: 12px; color: var(--nk-ink-light); margin-top: 8px; letter-spacing: 0.1em; }

    /* ── Primary nav ── */
    .nk-primary-nav { background: var(--nk-ink); position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 12px rgba(100,0,150,0.18); }
    .nk-primary-nav-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; overflow-x: auto; scrollbar-width: none; }
    .nk-primary-nav-inner::-webkit-scrollbar { display: none; }
    .nk-nav-item { font-size: 12px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.65); padding: 14px 15px; border-bottom: 3px solid transparent; white-space: nowrap; transition: color 0.2s, border-color 0.2s; display: block; }
    .nk-nav-item:hover, .nk-nav-item.active { color: #fff; border-bottom-color: var(--nk-accent); }

    /* ── Site container ── */
    .nk-main { max-width: 1280px; margin: 0 auto; padding: 0 24px; }

    /* ── Hero section ── */
    .nk-hero { padding: 28px 0 0; }
    .nk-hero-grid { display: grid; grid-template-columns: 1fr 300px; gap: var(--nk-gap); }
    .nk-hero-main { border-right: 1px solid var(--nk-border); padding-right: var(--nk-gap); }
    .nk-cat-label { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; margin-bottom: 14px; }
    .nk-hero-headline { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(24px, 3vw, 38px); font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; color: var(--nk-ink); display: block; margin-bottom: 14px; }
    .nk-hero-headline:hover { color: var(--nk-accent); }
    .nk-hero-deck { font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; font-weight: 300; color: var(--nk-ink-mid); line-height: 1.6; margin-bottom: 12px; }
    .nk-hero-meta { font-size: 12px; color: var(--nk-ink-light); }
    .nk-hero-sidebar { display: flex; flex-direction: column; }

    /* ── Images ── */
    .nk-hero-img-link { display: block; }
    .nk-hero-img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 16px; }
    .nk-card-img-link { display: block; }
    .nk-lead-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 10px; }
    .nk-card-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 8px; }
    .nk-article-hero-img { margin: 0 0 28px; }
    .nk-article-hero-img img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }

    /* ── Sidebar stories ── */
    .nk-sidebar-story { padding: 13px 0; border-bottom: 1px solid var(--nk-border-light); }
    .nk-sidebar-story:last-child { border-bottom: none; }
    .nk-sidebar-story-cat { font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: #fff; padding: 2px 8px; margin-bottom: 6px; display: inline-block; }
    .nk-sidebar-story-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 700; line-height: 1.3; color: var(--nk-ink); display: block; }
    .nk-sidebar-story-title:hover { color: var(--nk-accent); }
    .nk-sidebar-story-meta { font-size: 11px; color: var(--nk-ink-light); margin-top: 5px; }

    /* ── Category sections ── */
    .nk-cat-section { padding: 28px 0; border-bottom: 1px solid var(--nk-border); }
    .nk-section-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid var(--nk-ink); padding-bottom: 10px; margin-bottom: 20px; }
    .nk-section-header-left { display: flex; align-items: center; gap: 10px; }
    .nk-section-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; }
    .nk-section-h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; color: var(--nk-ink); }
    .nk-see-all { font-size: 12px; color: var(--nk-ink-light); }
    .nk-see-all:hover { color: var(--nk-accent); }

    /* ── Story grid layouts ── */
    .nk-lead-plus-two { display: grid; grid-template-columns: 1fr 260px; gap: var(--nk-gap); margin-bottom: 20px; }
    .nk-lead-story-title { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.25; color: var(--nk-ink); display: block; margin-bottom: 8px; }
    .nk-lead-story-title:hover { color: var(--nk-accent); }
    .nk-lead-story-desc { font-family: 'Source Serif 4', Georgia, serif; font-size: 14px; color: var(--nk-ink-mid); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .nk-lead-story-meta { font-size: 11px; color: var(--nk-ink-light); margin-top: 8px; }
    .nk-two-stack { border-left: 1px solid var(--nk-border-light); padding-left: var(--nk-gap); display: flex; flex-direction: column; }
    .nk-two-stack-item { padding: 10px 0; border-bottom: 1px solid var(--nk-border-light); }
    .nk-two-stack-item:last-child { border-bottom: none; }
    .nk-two-stack-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 700; line-height: 1.3; color: var(--nk-ink); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .nk-two-stack-title:hover { color: var(--nk-accent); }
    .nk-two-stack-meta { font-size: 11px; color: var(--nk-ink-light); margin-top: 5px; }
    .nk-three-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--nk-gap); border-top: 1px solid var(--nk-border-light); padding-top: 20px; }
    .nk-story-card-title { font-family: 'Playfair Display', Georgia, serif; font-size: 16px; font-weight: 700; line-height: 1.3; color: var(--nk-ink); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin-bottom: 6px; }
    .nk-story-card-title:hover { color: var(--nk-accent); }
    .nk-story-card-desc { font-family: 'Source Serif 4', Georgia, serif; font-size: 13px; color: var(--nk-ink-mid); line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .nk-story-card-meta { font-size: 11px; color: var(--nk-ink-light); margin-top: 6px; }

    /* ── Article page ── */
    .nk-article { max-width: 720px; margin: 0 auto; padding: 40px 24px 60px; }
    .nk-article-back { font-size: 13px; color: var(--nk-accent); display: inline-block; margin-bottom: 24px; }
    .nk-article-back:hover { text-decoration: underline; }
    .nk-article-meta-top { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
    .nk-article-cat-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; }
    .nk-article-date { font-size: 12px; color: var(--nk-ink-light); }
    .nk-article-headline { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(24px, 3.5vw, 36px); font-weight: 900; letter-spacing: -0.02em; line-height: 1.15; color: var(--nk-ink); margin-bottom: 18px; }
    .nk-article-lede { font-family: 'Source Serif 4', Georgia, serif; font-size: 18px; font-weight: 300; color: var(--nk-ink-mid); line-height: 1.65; border-left: 4px solid var(--nk-accent); padding-left: 20px; margin-bottom: 28px; }
    .nk-article-body h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 20px; font-weight: 700; color: var(--nk-ink); margin-top: 34px; margin-bottom: 13px; padding-top: 8px; border-top: 2px solid var(--nk-border); }
    .nk-article-body p { font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; line-height: 1.7; color: var(--nk-ink-mid); margin-bottom: 18px; }
    .nk-article-body a { color: var(--nk-accent); text-decoration: underline; }
    .nk-article-body a:hover { color: var(--nk-accent-dark); }
    .nk-article-faq { margin-top: 48px; border-top: 2px solid var(--nk-border); padding-top: 28px; }
    .nk-article-faq h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; margin-bottom: 20px; color: var(--nk-ink); }
    .nk-faq-item { border-bottom: 1px solid var(--nk-border-light); }
    .nk-faq-item summary { font-size: 15px; font-weight: 600; color: var(--nk-ink); padding: 14px 0; cursor: pointer; list-style: none; display: flex; align-items: center; gap: 8px; }
    .nk-faq-item summary::-webkit-details-marker { display: none; }
    .nk-faq-item summary::before { content: '▸'; color: var(--nk-accent); transition: transform 0.2s; flex-shrink: 0; }
    .nk-faq-item[open] summary::before { transform: rotate(90deg); }
    .nk-faq-item p { font-family: 'Source Serif 4', Georgia, serif; font-size: 15px; color: var(--nk-ink-mid); padding: 0 0 14px 22px; line-height: 1.65; }
    .nk-article-tags { margin-top: 28px; display: flex; flex-wrap: wrap; gap: 8px; }
    .nk-article-tag { font-size: 12px; color: var(--nk-ink-mid); border: 1px solid var(--nk-border); border-radius: 20px; padding: 4px 12px; }
    .nk-article-tag:hover { background: var(--nk-accent); color: #fff; border-color: var(--nk-accent); }
    .nk-article-sources { margin-top: 28px; border-top: 1px solid var(--nk-border); padding-top: 16px; }
    .nk-article-sources-label { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--nk-ink-light); margin-bottom: 10px; }
    .nk-article-sources a { font-size: 12px; color: var(--nk-accent); }
    .nk-article-sources a:hover { text-decoration: underline; }
    .nk-article-sources span { font-size: 12px; color: var(--nk-ink-light); }
    .nk-article-readtime { font-size: 12px; color: var(--nk-ink-light); }
    .nk-article-takeaways { background: var(--nk-paper-mid); border: 1px solid var(--nk-border); border-top: 3px solid var(--nk-ink); border-radius: 0 0 6px 6px; padding: 18px 22px; margin: 0 0 28px; }
    .nk-takeaways-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--nk-ink-light); margin-bottom: 10px; }
    .nk-article-takeaways ul { padding-left: 18px; }
    .nk-article-takeaways li { font-family: 'Source Serif 4', Georgia, serif; font-size: 15px; line-height: 1.6; color: var(--nk-ink-mid); margin-bottom: 6px; }
    .nk-article-keystat { display: flex; align-items: baseline; gap: 14px; background: var(--nk-paper-mid); border-left: 4px solid var(--nk-accent); border-radius: 0 8px 8px 0; padding: 16px 20px; margin: 0 0 28px; }
    .nk-keystat-value { font-family: 'Playfair Display', Georgia, serif; font-size: 2rem; font-weight: 900; color: var(--nk-accent); flex-shrink: 0; line-height: 1; }
    .nk-keystat-label { font-size: 14px; color: var(--nk-ink-mid); line-height: 1.4; }
    .nk-article-pullquote { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(17px, 2.5vw, 21px); font-style: italic; font-weight: 600; color: var(--nk-ink); border-top: 2px solid var(--nk-ink); border-bottom: 2px solid var(--nk-ink); padding: 20px 4px; margin: 32px 0; text-align: center; line-height: 1.45; }

    /* ── Category page header ── */
    .nk-cat-page-header { padding: 32px 0 24px; border-bottom: 2px solid var(--nk-ink); margin-bottom: 28px; }
    .nk-cat-page-title { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(26px, 4vw, 42px); font-weight: 700; color: var(--nk-ink); margin-bottom: 6px; }
    .nk-cat-page-count { font-size: 13px; color: var(--nk-ink-light); }

    /* ── Disclaimer banner ── */
    .nk-disclaimer { background: var(--nk-paper-mid); border: 1px solid var(--nk-border); border-left: 4px solid var(--nk-accent); padding: 10px 16px; margin: 16px 0; font-size: 12px; color: var(--nk-ink-light); border-radius: 0 6px 6px 0; }

    /* ── Footer ── */
    .nk-footer { background: var(--nk-ink); padding: 40px 24px; margin-top: 48px; }
    .nk-footer-inner { max-width: 1280px; margin: 0 auto; }
    .nk-footer-logo { font-family: 'Playfair Display', Georgia, serif; font-size: 26px; font-weight: 900; color: #fff; display: block; margin-bottom: 5px; }
    .nk-footer-logo:hover { color: var(--nk-accent); }
    .nk-footer-tagline { font-size: 12px; color: rgba(255,255,255,0.35); margin-bottom: 24px; }
    .nk-footer-cats { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-bottom: 28px; }
    .nk-footer-cat { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.4); }
    .nk-footer-cat:hover { color: #fff; }
    .nk-footer-bottom { border-top: 1px solid rgba(255,255,255,0.1); padding-top: 16px; font-size: 11.5px; color: rgba(255,255,255,0.25); }

    /* ── Trending bar ── */
    .nk-trending-bar { background: var(--nk-paper-mid); border-top: 1px solid var(--nk-border); border-bottom: 1px solid var(--nk-border); padding: 12px 0; margin: 24px 0; }
    .nk-trending-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
    .nk-trending-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--nk-accent); flex-shrink: 0; }
    .nk-trending-tag { font-size: 12px; color: var(--nk-ink-mid); border: 1px solid var(--nk-border); border-radius: 20px; padding: 4px 13px; transition: background 0.15s, color 0.15s; }
    .nk-trending-tag:hover { background: var(--nk-accent); color: #fff; border-color: var(--nk-accent); }

    /* ── Responsive ── */
    @media (max-width: 900px) {
      .nk-hero-grid { grid-template-columns: 1fr; }
      .nk-hero-main { border-right: none; padding-right: 0; border-bottom: 1px solid var(--nk-border); padding-bottom: var(--nk-gap); }
      .nk-lead-plus-two { grid-template-columns: 1fr; }
      .nk-two-stack { border-left: none; padding-left: 0; border-top: 1px solid var(--nk-border-light); padding-top: 16px; }
      .nk-three-col { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 600px) {
      .nk-three-col { grid-template-columns: 1fr; }
      .nk-masthead { padding: 20px 16px; }
      .nk-primary-nav-inner { padding: 0 12px; }
      .nk-main { padding: 0 16px; }
    }
    @media print {
      .nk-primary-nav, .nk-footer { display: none; }
      body { background: white; color: black; }
    }
  </style>
</head>
<body>
  <header class="nk-masthead">
    <div class="nk-masthead-eyebrow">Sex Education &amp; Sexual Health</div>
    <a href="${basePath}/" class="nk-masthead-logo">The Nookie Nook</a>
    <div class="nk-masthead-tagline">Evidence-based sex ed for everyone</div>
  </header>

  <nav class="nk-primary-nav">
    <div class="nk-primary-nav-inner">
      <a href="${basePath}/search" class="nk-nav-item" title="Search" style="font-size:18px">&#x2315;</a>
      ${navItem(basePath + '/', 'Home')}
      ${navItem(basePath + '/category/sexual-health', 'Sexual Health')}
      ${navItem(basePath + '/category/relationships', 'Relationships')}
      ${navItem(basePath + '/category/lgbtq', 'LGBTQ+')}
      ${navItem(basePath + '/category/wellness', 'Wellness')}
      ${navItem(basePath + '/category/education', 'Education')}
      ${navItem(basePath + '/category/reproductive-health', 'Reproductive')}
      ${navItem(basePath + '/category/research', 'Research')}
      ${navItem(basePath + '/category/culture', 'Culture')}
      ${navItem(basePath + '/category/mental-health', 'Mental Health')}
      ${navItem(basePath + '/category/body-literacy', 'Body Literacy')}
    </div>
  </nav>

  <main class="nk-main">
    ${body}
  </main>

  <footer class="nk-footer">
    <div class="nk-footer-inner">
      <a href="${basePath}/" class="nk-footer-logo">The Nookie Nook</a>
      <div class="nk-footer-tagline">Evidence-based sex education for curious adults.</div>
      <div class="nk-footer-cats">
        <a href="${basePath}/category/sexual-health" class="nk-footer-cat">Sexual Health</a>
        <a href="${basePath}/category/relationships" class="nk-footer-cat">Relationships</a>
        <a href="${basePath}/category/lgbtq" class="nk-footer-cat">LGBTQ+</a>
        <a href="${basePath}/category/wellness" class="nk-footer-cat">Wellness</a>
        <a href="${basePath}/category/education" class="nk-footer-cat">Education</a>
        <a href="${basePath}/category/reproductive-health" class="nk-footer-cat">Reproductive Health</a>
        <a href="${basePath}/category/research" class="nk-footer-cat">Research</a>
        <a href="${basePath}/category/culture" class="nk-footer-cat">Culture</a>
        <a href="${basePath}/category/mental-health" class="nk-footer-cat">Mental Health</a>
        <a href="${basePath}/category/body-literacy" class="nk-footer-cat">Body Literacy</a>
      </div>
      <div class="nk-footer-bottom">&copy; ${new Date().getFullYear()} The Nookie Nook &middot; Part of the <a href="https://gab.ae" style="color:rgba(255,255,255,0.4);text-decoration:underline">gab.ae</a> network &middot; For adults 18+</div>
    </div>
  </footer>
</body>
</html>`;
}

export function nkEsc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
