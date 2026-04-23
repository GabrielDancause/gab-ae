import { layout, esc } from '../templates/layout.js';

const CAT_COLORS = {
  us: '#c8102e', world: '#1a5c8a', politics: '#3a2060',
  business: '#1a5c30', health: '#8a2020', entertainment: '#8a6020',
  travel: '#1a4a6a', sports: '#1a3a5c', science: '#2a1e5e',
  climate: '#1a5c30', tech: '#8a4020',
};

export function renderNews(page) {
  const sections = JSON.parse(page.sections || '[]');
  const tags = JSON.parse(page.tags || '[]');
  const sources = JSON.parse(page.sources || '[]');
  const faqs = JSON.parse(page.faqs || '[]');
  const keyStat = page.key_stat ? JSON.parse(page.key_stat) : null;
  const pullQuote = page.pull_quote || null;
  const takeaways = page.takeaways ? JSON.parse(page.takeaways) : null;
  const published = page.published_at
    ? new Date(page.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' })
    : '';
  const catColor = CAT_COLORS[page.category] || '#c8102e';
  const catLabel = (page.category || 'news').toUpperCase();

  const wordCount = sections.reduce((n, s) => n + (s.paragraphs || []).join(' ').split(/\s+/).length, 0);
  const readingTime = Math.max(1, Math.round(wordCount / 220));

  const sectionsHtml = sections.map((s, i) => `
    ${i === 1 && pullQuote ? `<blockquote class="article-pullquote">${esc(pullQuote)}</blockquote>` : ''}
    <div>
      <h2>${esc(s.heading)}</h2>
      ${(s.paragraphs || []).map(p =>
        `<p>${(p.includes('<a ') || p.includes('<strong>')) ? p : esc(p)}</p>`
      ).join('')}
    </div>
  `).join('');

  const faqsHtml = faqs.length ? `
    <div class="article-faq">
      <h2>Frequently Asked Questions</h2>
      ${faqs.map(f => `
        <details class="faq-item">
          <summary>${esc(f.q)}</summary>
          <p>${esc(f.a)}</p>
        </details>
      `).join('')}
    </div>` : '';

  const tagsHtml = tags.length ? `
    <div class="article-tags">
      ${tags.map(t => `<a href="/news/category/${esc(page.category)}" class="article-tag">${esc(t)}</a>`).join('')}
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
    '@type': 'NewsArticle',
    headline: page.title,
    description: page.description,
    url: `https://gab.ae/news/${page.slug}`,
    datePublished: page.published_at,
    dateModified: page.updated_at || page.published_at,
    publisher: { '@type': 'Organization', name: 'GAB.AE', url: 'https://gab.ae' },
  };

  const body = `
    <article class="tp-article">
      <a href="/" class="article-back">← Back to News</a>

      <div class="article-meta-top">
        <span class="article-cat-badge" style="background:${catColor}">${catLabel}</span>
        <span class="article-date">${published}</span>
        <span class="article-readtime">${readingTime} min read</span>
      </div>

      <h1 class="article-headline">${esc(page.title)}</h1>

      ${page.image ? `<figure class="article-hero-img"><img src="${esc(page.image)}" alt="${esc(page.image_alt || page.title)}" loading="lazy" width="720" height="405"></figure>` : ''}

      ${page.lede ? `<p class="article-lede">${esc(page.lede)}</p>` : ''}

      ${takeaways && takeaways.length ? `
      <div class="article-takeaways">
        <p class="takeaways-label">At a Glance</p>
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
    </article>
  `;

  return layout({
    title: `${page.title} | GAB.AE`,
    description: page.description || page.lede || '',
    canonical: `https://gab.ae/news/${page.slug}`,
    schemaJson: faqSchema ? [articleSchema, faqSchema] : articleSchema,
    activeNav: page.category,
    body,
  });
}
