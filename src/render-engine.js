import { siteLayout, esc } from './templates/site-layout.js';

export function renderArticle(article, site, basePath = null) {
  const prefix = basePath !== null ? basePath : site.pathPrefix;

  const sections  = JSON.parse(article.sections  || '[]');
  const tags      = JSON.parse(article.tags       || '[]');
  const sources   = JSON.parse(article.sources    || '[]');
  const faqs      = JSON.parse(article.faqs       || '[]');
  const keyStat   = article.key_stat   ? JSON.parse(article.key_stat)   : null;
  const takeaways = article.takeaways  ? JSON.parse(article.takeaways)  : null;
  const pullQuote = article.pull_quote || null;

  const published = article.published_at
    ? new Date(article.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' })
    : '';

  const catColor = site.categoryColors[article.category] || site.theme.accent;
  const catLabel = (article.category || site.defaultCategory).replace(/-/g, ' ').toUpperCase();
  const wordCount = sections.reduce((n, s) => n + (s.paragraphs || []).join(' ').split(/\s+/).length, 0);
  const readingTime = Math.max(1, Math.round(wordCount / 220));

  // Canonical always points to own domain regardless of access path
  const canonical = `https://${site.ownDomain}${site.articlePath}/${article.slug}`;

  const sectionsHtml = sections.map((s, i) => `
    ${i === 1 && pullQuote ? `<blockquote class="article-pullquote">${esc(pullQuote)}</blockquote>` : ''}
    <div>
      <h2>${esc(s.heading)}</h2>
      ${(s.paragraphs || []).map(p =>
        `<p>${(p.includes('<a ') || p.includes('<strong>')) ? p : esc(p)}</p>`
      ).join('')}
    </div>`).join('');

  const faqsHtml = faqs.length ? `
    <div class="article-faq">
      <h2>Frequently Asked Questions</h2>
      ${faqs.map(f => `
        <details class="faq-item">
          <summary>${esc(f.q)}</summary>
          <p>${esc(f.a)}</p>
        </details>`).join('')}
    </div>` : '';

  const tagsHtml = tags.length ? `
    <div class="article-tags">
      ${tags.map(t => `<a href="${prefix}${site.categoryPath}/${esc(article.category)}" class="article-tag">${esc(t)}</a>`).join('')}
    </div>` : '';

  const sourcesHtml = sources.length ? `
    <div class="article-sources">
      <p class="article-sources-label">Sources</p>
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
        ${sources.map(s => s.url
          ? `<a href="${esc(s.url)}" target="_blank" rel="noopener nofollow">${esc(s.name)}</a>`
          : `<span>${esc(s.name)}</span>`
        ).join('<span style="color:var(--border)">·</span>')}
      </div>
    </div>` : '';

  const faqSchema = faqs.length ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map(f => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  } : null;

  const articleSchema = {
    '@context': 'https://schema.org',
    '@type': site.schemaType,
    headline: article.title,
    description: article.description,
    url: canonical,
    datePublished: article.published_at,
    dateModified: article.updated_at || article.published_at,
    publisher: { '@type': 'Organization', name: site.publisherName, url: site.publisherUrl },
    ...(site.aboutThing ? { about: site.aboutThing } : {}),
  };

  const body = `
    <article class="tp-article">
      <a href="${prefix}/" class="article-back">← Back to ${esc(site.name)}</a>

      <div class="article-meta-top">
        <span class="article-cat-badge" style="background:${catColor}">${catLabel}</span>
        <span class="article-date">${published}</span>
        <span class="article-readtime">${readingTime} min read</span>
      </div>

      <h1 class="article-headline">${esc(article.title)}</h1>

      ${article.image ? `<figure class="article-hero-img"><img src="${esc(article.image)}" alt="${esc(article.image_alt || article.title)}" loading="lazy" width="720" height="405"></figure>` : ''}

      ${site.disclaimer ? `<div class="article-disclaimer">${site.disclaimer}</div>` : ''}

      ${article.lede ? `<p class="article-lede">${esc(article.lede)}</p>` : ''}

      ${takeaways && takeaways.length ? `
      <div class="article-takeaways">
        <p class="takeaways-label">${esc(site.takeawaysLabel)}</p>
        <ul>${takeaways.map(t => `<li>${esc(t)}</li>`).join('')}</ul>
      </div>` : ''}

      ${keyStat ? `
      <div class="article-keystat">
        <span class="keystat-value">${esc(keyStat.value)}</span>
        <span class="keystat-label">${esc(keyStat.label)}</span>
      </div>` : ''}

      <div class="article-body">
        ${sectionsHtml}
      </div>

      ${tagsHtml}
      ${sourcesHtml}
      ${faqsHtml}
    </article>`;

  return siteLayout({
    site,
    title: `${article.title} | ${site.name}`,
    description: article.description || article.lede || '',
    canonical,
    schemaJson: faqSchema ? [articleSchema, faqSchema] : articleSchema,
    activeNav: article.category,
    basePath: prefix,
    body,
  });
}
