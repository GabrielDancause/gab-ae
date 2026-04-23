// Unified layout template for all news properties.
// Driven entirely by the site config object from sites.js.
// CSS covers both generic (gab.ae) and nk-* (nookie) class names during the
// Phase 2→3 transition; nk-* aliases can be dropped once engines are unified.

export function siteLayout({ site, title, description, canonical, schemaJson, body, activeNav = '', basePath = null }) {
  const prefix = basePath !== null ? basePath : site.pathPrefix;
  const schema = schemaJson ? `<script type="application/ld+json">${JSON.stringify(Array.isArray(schemaJson) ? schemaJson : schemaJson)}</script>` : '';
  const t = site.theme;

  function navItem(href, label) {
    const slug = href.split('/').filter(s => s).pop() || '';
    const active = activeNav && activeNav === slug;
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
  <meta property="og:site_name" content="${esc(site.ogSiteName)}">
  <meta name="twitter:card" content="${site.twitterCard}">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(description)}">
  ${schema}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;900&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,400&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script async src="https://www.googletagmanager.com/gtag/js?id=${site.ga4Id}"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${site.ga4Id}');</script>
  <style>
    :root {
      --ink: ${t.ink};
      --ink-mid: ${t.inkMid};
      --ink-light: ${t.inkLight};
      --paper: ${t.paper};
      --paper-mid: ${t.paperMid};
      --paper-dark: ${t.paperDark};
      --accent: ${t.accent};
      --accent-dark: ${t.accentDark};
      --border: ${t.border};
      --border-light: ${t.borderLight};
      --gap: 24px;
      /* nk-* aliases — backward compat with existing nookie engine HTML */
      --nk-ink: var(--ink); --nk-ink-mid: var(--ink-mid); --nk-ink-light: var(--ink-light);
      --nk-paper: var(--paper); --nk-paper-mid: var(--paper-mid); --nk-paper-dark: var(--paper-dark);
      --nk-accent: var(--accent); --nk-accent-dark: var(--accent-dark);
      --nk-border: var(--border); --nk-border-light: var(--border-light); --nk-gap: var(--gap);
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { overflow-x: hidden; }
    body { font-family: 'DM Sans', system-ui, sans-serif; background: var(--paper); color: var(--ink); overflow-x: hidden; }
    a { color: inherit; text-decoration: none; }
    img, video, canvas, svg { max-width: 100%; height: auto; }
    p, li, h1, h2, h3, h4, h5, h6, div, a, strong, em, blockquote { overflow-wrap: break-word; word-break: break-word; }

    /* ── Masthead ── */
    .masthead { text-align: center; padding: 28px 24px 20px; border-bottom: 3px double var(--border); background: var(--paper); }
    .masthead-eyebrow { font-size: 10.5px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-light); margin-bottom: 8px; }
    .masthead-logo { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(36px, 5.5vw, 68px); font-weight: 900; letter-spacing: -0.02em; color: var(--ink); display: block; line-height: 1; }
    .masthead-logo:hover { color: var(--accent); transition: color 0.2s; }
    .masthead-tagline { font-size: 12px; color: var(--ink-light); margin-top: 8px; letter-spacing: 0.1em; }

    /* ── Primary nav ── */
    .primary-nav { background: var(--ink); position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 12px rgba(0,0,0,0.15); }
    .primary-nav-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; overflow-x: auto; scrollbar-width: none; }
    .primary-nav-inner::-webkit-scrollbar { display: none; }
    .nav-item { font-size: 12px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.7); padding: 14px 15px; border-bottom: 3px solid transparent; white-space: nowrap; transition: color 0.2s, border-color 0.2s; display: block; }
    .nav-item:hover, .nav-item.active { color: #fff; border-bottom-color: var(--accent); }

    /* ── Site container ── */
    .site-main { max-width: 1280px; margin: 0 auto; padding: 0 24px; }

    /* ── Hero section (gab.ae + nk-* aliases) ── */
    .hero-section, .nk-hero { padding: 28px 0 0; }
    .hero-grid, .nk-hero-grid { display: grid; grid-template-columns: 1fr 300px; gap: var(--gap); }
    .hero-main, .nk-hero-main { border-right: 1px solid var(--border); padding-right: var(--gap); }
    .hero-cat-label, .nk-cat-label { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; margin-bottom: 14px; }
    .hero-headline, .nk-hero-headline { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(25px, 3vw, 39px); font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; color: var(--ink); display: block; margin-bottom: 14px; }
    .hero-headline:hover, .nk-hero-headline:hover { color: var(--accent); }
    .hero-deck, .nk-hero-deck { font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; font-weight: 300; color: var(--ink-mid); line-height: 1.6; margin-bottom: 12px; }
    .hero-meta, .nk-hero-meta { font-size: 12px; color: var(--ink-light); }
    .hero-sidebar, .nk-hero-sidebar { display: flex; flex-direction: column; }

    /* ── Sidebar stories ── */
    .sidebar-story, .nk-sidebar-story { padding: 13px 0; border-bottom: 1px solid var(--border-light); }
    .sidebar-story:last-child, .nk-sidebar-story:last-child { border-bottom: none; }
    .sidebar-story-cat, .nk-sidebar-story-cat { font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: #fff; padding: 2px 8px; margin-bottom: 6px; display: inline-block; }
    .sidebar-story-title, .nk-sidebar-story-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 700; line-height: 1.3; color: var(--ink); display: block; }
    .sidebar-story-title:hover, .nk-sidebar-story-title:hover { color: var(--accent); }
    .sidebar-story-meta, .nk-sidebar-story-meta { font-size: 11px; color: var(--ink-light); margin-top: 5px; }

    /* ── Images ── */
    .hero-img-link, .nk-hero-img-link { display: block; }
    .hero-img, .nk-hero-img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 16px; }
    .card-img-link, .nk-card-img-link { display: block; }
    .lead-thumb, .nk-lead-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 10px; }
    .card-thumb, .nk-card-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; margin-bottom: 8px; }
    .article-hero-img, .nk-article-hero-img { margin: 0 0 28px; }
    .article-hero-img img, .nk-article-hero-img img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }

    /* ── Trending bar ── */
    .trending-bar, .nk-trending-bar { background: var(--paper-mid); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 12px 0; margin: 24px 0; }
    .trending-inner, .nk-trending-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
    .trending-label, .nk-trending-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--accent); flex-shrink: 0; }
    .trending-tag, .nk-trending-tag { font-size: 12px; color: var(--ink-mid); border: 1px solid var(--border); border-radius: 20px; padding: 4px 13px; transition: background 0.15s, color 0.15s; }
    .trending-tag:hover, .nk-trending-tag:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

    /* ── Category sections ── */
    .cat-section, .nk-cat-section { padding: 28px 0; border-bottom: 1px solid var(--border); }
    .section-header, .nk-section-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid var(--ink); padding-bottom: 10px; margin-bottom: 20px; }
    .section-header-left, .nk-section-header-left { display: flex; align-items: center; gap: 10px; }
    .section-label, .nk-section-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; }
    .section-h2, .nk-section-h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; color: var(--ink); }
    .see-all, .nk-see-all { font-size: 12px; color: var(--ink-light); }
    .see-all:hover, .nk-see-all:hover { color: var(--accent); }

    /* ── Story grid layouts ── */
    .lead-plus-two, .nk-lead-plus-two { display: grid; grid-template-columns: 1fr 260px; gap: var(--gap); margin-bottom: 20px; }
    .lead-story-title, .nk-lead-story-title { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.25; color: var(--ink); display: block; margin-bottom: 8px; }
    .lead-story-title:hover, .nk-lead-story-title:hover { color: var(--accent); }
    .lead-story-desc, .nk-lead-story-desc { font-family: 'Source Serif 4', Georgia, serif; font-size: 14.5px; color: var(--ink-mid); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .lead-story-meta, .nk-lead-story-meta { font-size: 11px; color: var(--ink-light); margin-top: 8px; }
    .two-stack, .nk-two-stack { border-left: 1px solid var(--border-light); padding-left: var(--gap); display: flex; flex-direction: column; }
    .two-stack-item, .nk-two-stack-item { padding: 10px 0; border-bottom: 1px solid var(--border-light); }
    .two-stack-item:last-child, .nk-two-stack-item:last-child { border-bottom: none; }
    .two-stack-title, .nk-two-stack-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 700; line-height: 1.3; color: var(--ink); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .two-stack-title:hover, .nk-two-stack-title:hover { color: var(--accent); }
    .two-stack-meta, .nk-two-stack-meta { font-size: 11px; color: var(--ink-light); margin-top: 5px; }
    .three-col, .nk-three-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gap); border-top: 1px solid var(--border-light); padding-top: 20px; }
    .story-card-title, .nk-story-card-title { font-family: 'Playfair Display', Georgia, serif; font-size: 17px; font-weight: 700; line-height: 1.3; color: var(--ink); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin-bottom: 6px; }
    .story-card-title:hover, .nk-story-card-title:hover { color: var(--accent); }
    .story-card-desc, .nk-story-card-desc { font-family: 'Source Serif 4', Georgia, serif; font-size: 13.5px; color: var(--ink-mid); line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .story-card-meta, .nk-story-card-meta { font-size: 11px; color: var(--ink-light); margin-top: 6px; }

    /* ── Article page ── */
    .tp-article, .nk-article { max-width: 720px; margin: 0 auto; padding: 40px 24px 60px; }
    .article-back, .nk-article-back { font-size: 13px; color: var(--accent); display: inline-block; margin-bottom: 24px; }
    .article-back:hover, .nk-article-back:hover { text-decoration: underline; }
    .article-meta-top, .nk-article-meta-top { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
    .article-cat-badge, .nk-article-cat-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #fff; padding: 3px 10px; }
    .article-date, .nk-article-date { font-size: 12px; color: var(--ink-light); }
    .article-readtime, .nk-article-readtime { font-size: 12px; color: var(--ink-light); }
    .article-headline, .nk-article-headline { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(25px, 3.5vw, 37px); font-weight: 900; letter-spacing: -0.02em; line-height: 1.15; color: var(--ink); margin-bottom: 18px; }
    .article-lede, .nk-article-lede { font-family: 'Source Serif 4', Georgia, serif; font-size: 18px; font-weight: 300; color: var(--ink-mid); line-height: 1.65; border-left: 4px solid var(--accent); padding-left: 20px; margin-bottom: 28px; }

    /* ── Article body ── */
    .article-body h2, .nk-article-body h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 21px; font-weight: 700; color: var(--ink); margin-top: 34px; margin-bottom: 13px; padding-top: 8px; border-top: 2px solid var(--border); }
    .article-body p, .nk-article-body p { font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; line-height: 1.7; color: var(--ink-mid); margin-bottom: 18px; }
    .article-body a, .nk-article-body a { color: var(--accent); text-decoration: underline; }
    .article-body a:hover, .nk-article-body a:hover { color: var(--accent-dark); }
    .article-body > div:first-child > p:first-child, .nk-article-body > div:first-child > p:first-child { font-size: 18px; line-height: 1.7; color: var(--ink); }

    /* ── Article components ── */
    .article-pullquote, .nk-article-pullquote { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(17px, 2.5vw, 21px); font-style: italic; font-weight: 600; color: var(--ink); border-top: 2px solid var(--ink); border-bottom: 2px solid var(--ink); padding: 20px 4px; margin: 32px 0; text-align: center; line-height: 1.45; }
    .article-takeaways, .nk-article-takeaways { background: var(--paper-mid); border: 1px solid var(--border); border-top: 3px solid var(--ink); border-radius: 0 0 6px 6px; padding: 18px 22px; margin: 0 0 28px; }
    .takeaways-label, .nk-takeaways-label { font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-light); margin-bottom: 10px; }
    .article-takeaways ul, .nk-article-takeaways ul { padding-left: 18px; }
    .article-takeaways li, .nk-article-takeaways li { font-family: 'Source Serif 4', Georgia, serif; font-size: 15px; line-height: 1.6; color: var(--ink-mid); margin-bottom: 6px; }
    .article-takeaways li:last-child, .nk-article-takeaways li:last-child { margin-bottom: 0; }
    .article-keystat, .nk-article-keystat { display: flex; align-items: baseline; gap: 14px; background: var(--paper-mid); border-left: 4px solid var(--accent); border-radius: 0 8px 8px 0; padding: 16px 20px; margin: 0 0 28px; }
    .keystat-value, .nk-keystat-value { font-family: 'Playfair Display', Georgia, serif; font-size: 2rem; font-weight: 900; color: var(--accent); flex-shrink: 0; line-height: 1; }
    .keystat-label, .nk-keystat-label { font-size: 14px; color: var(--ink-mid); line-height: 1.4; }

    /* ── FAQ ── */
    .article-faq, .nk-article-faq { margin-top: 48px; border-top: 2px solid var(--border); padding-top: 28px; }
    .article-faq h2, .nk-article-faq h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 22px; font-weight: 700; margin-bottom: 20px; color: var(--ink); }
    .faq-item, .nk-faq-item { border-bottom: 1px solid var(--border-light); }
    .faq-item summary, .nk-faq-item summary { font-size: 15px; font-weight: 600; color: var(--ink); padding: 14px 0; cursor: pointer; list-style: none; display: flex; align-items: center; gap: 8px; }
    .faq-item summary::-webkit-details-marker, .nk-faq-item summary::-webkit-details-marker { display: none; }
    .faq-item summary::before, .nk-faq-item summary::before { content: '▸'; color: var(--accent); transition: transform 0.2s; flex-shrink: 0; }
    .faq-item[open] summary::before, .nk-faq-item[open] summary::before { transform: rotate(90deg); }
    .faq-item p, .nk-faq-item p { font-family: 'Source Serif 4', Georgia, serif; font-size: 15px; color: var(--ink-mid); padding: 0 0 14px 22px; line-height: 1.65; }

    /* ── Tags & sources ── */
    .article-tags, .nk-article-tags { margin-top: 28px; display: flex; flex-wrap: wrap; gap: 8px; }
    .article-tag, .nk-article-tag { font-size: 12px; color: var(--ink-mid); border: 1px solid var(--border); border-radius: 20px; padding: 4px 12px; }
    .article-tag:hover, .nk-article-tag:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
    .article-sources, .nk-article-sources { margin-top: 28px; border-top: 1px solid var(--border); padding-top: 16px; }
    .article-sources-label, .nk-article-sources-label { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-light); margin-bottom: 10px; }
    .article-sources a, .nk-article-sources a { font-size: 12px; color: var(--accent); }
    .article-sources a:hover, .nk-article-sources a:hover { text-decoration: underline; }
    .article-sources span, .nk-article-sources span { font-size: 12px; color: var(--ink-light); }
    .article-section-divider { border: none; border-top: 1px solid var(--border); margin: 32px 0 0; }

    /* ── Disclaimer (nookie) ── */
    .nk-disclaimer, .article-disclaimer { background: var(--paper-mid); border: 1px solid var(--border); border-left: 4px solid var(--accent); padding: 10px 16px; margin: 16px 0; font-size: 12px; color: var(--ink-light); border-radius: 0 6px 6px 0; }

    /* ── Category page header ── */
    .cat-page-header, .nk-cat-page-header { padding: 32px 0 24px; border-bottom: 2px solid var(--ink); margin-bottom: 28px; }
    .cat-page-title, .nk-cat-page-title { font-family: 'Playfair Display', Georgia, serif; font-size: clamp(27px, 4vw, 43px); font-weight: 700; color: var(--ink); margin-bottom: 6px; }
    .cat-page-count, .nk-cat-page-count { font-size: 13px; color: var(--ink-light); }

    /* ── Footer ── */
    .site-footer { background: var(--ink); padding: 40px 24px; margin-top: 48px; }
    .footer-inner { max-width: 1280px; margin: 0 auto; }
    .footer-logo { font-family: 'Playfair Display', Georgia, serif; font-size: 27px; font-weight: 900; color: #fff; display: block; margin-bottom: 5px; }
    .footer-logo:hover { color: var(--accent); }
    .footer-tagline { font-size: 12px; color: rgba(255,255,255,0.35); margin-bottom: 24px; }
    .footer-cats { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-bottom: 28px; }
    .footer-cat { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.45); }
    .footer-cat:hover { color: #fff; }
    .footer-bottom { border-top: 1px solid rgba(255,255,255,0.1); padding-top: 16px; font-size: 11.5px; color: rgba(255,255,255,0.25); }

    /* ── Seed/tool pages (gab.ae legacy) ── */
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
      .hero-grid, .nk-hero-grid { grid-template-columns: 1fr; }
      .hero-main, .nk-hero-main { border-right: none; padding-right: 0; border-bottom: 1px solid var(--border); padding-bottom: var(--gap); }
      .lead-plus-two, .nk-lead-plus-two { grid-template-columns: 1fr; }
      .two-stack, .nk-two-stack { border-left: none; padding-left: 0; border-top: 1px solid var(--border-light); padding-top: 16px; }
      .three-col, .nk-three-col { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 600px) {
      .three-col, .nk-three-col { grid-template-columns: 1fr; }
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
    <div class="masthead-eyebrow">${esc(site.eyebrow)}</div>
    <a href="${prefix}/" class="masthead-logo">${esc(site.name)}</a>
    <div class="masthead-tagline">${esc(site.tagline)}</div>
  </header>

  <nav class="primary-nav">
    <div class="primary-nav-inner">
      <a href="${prefix}/search" class="nav-item" title="Search" style="font-size:18px">&#x2315;</a>
      ${site.navItems.map(item => navItem(prefix + item.href, item.label)).join('\n      ')}
    </div>
  </nav>

  <main class="site-main">
    ${body}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <a href="${prefix}/" class="footer-logo">${esc(site.name)}</a>
      <div class="footer-tagline">${esc(site.footerTagline)}</div>
      <div class="footer-cats">
        ${site.navItems.map(item => `<a href="${prefix + item.href}" class="footer-cat">${esc(item.label)}</a>`).join('\n        ')}
      </div>
      <div class="footer-bottom">&copy; ${new Date().getFullYear()} ${esc(site.name)} &middot; ${esc(site.footerCredit)}${site.adultContent ? ` &middot; <a href="https://gab.ae" style="color:rgba(255,255,255,0.4);text-decoration:underline">gab.ae network</a>` : ''}</div>
    </div>
  </footer>
</body>
</html>`;
}

export function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
