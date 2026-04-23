import { nookieLayout, nkEsc } from '../templates/nookie-layout.js';

const CAT_COLORS = {
  'sexual-health': '#c44ad9',
  'relationships': '#e84393',
  'lgbtq': '#9b35b5',
  'wellness': '#7c3aed',
  'education': '#6366f1',
  'research': '#4f46e5',
  'reproductive-health': '#d946a8',
  'culture': '#a855f7',
  'mental-health': '#8b5cf6',
  'body-literacy': '#c026d3',
};

export function renderNookieNews(article, basePath = '/thenookienook') {
  const sections = JSON.parse(article.sections || '[]');
  const tags = JSON.parse(article.tags || '[]');
  const sources = JSON.parse(article.sources || '[]');
  const faqs = JSON.parse(article.faqs || '[]');
  const keyStat = article.key_stat ? JSON.parse(article.key_stat) : null;
  const pullQuote = article.pull_quote || null;
  const takeaways = article.takeaways ? JSON.parse(article.takeaways) : null;
  const published = article.published_at
    ? new Date(article.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' })
    : '';
  const catColor = CAT_COLORS[article.category] || '#c44ad9';
  const catLabel = (article.category || 'sexual-health').replace(/-/g, ' ').toUpperCase();

  const wordCount = sections.reduce((n, s) => n + (s.paragraphs || []).join(' ').split(/\s+/).length, 0);
  const readingTime = Math.max(1, Math.round(wordCount / 220));

  const isNookieDomain = basePath === '';
  const articleBase = isNookieDomain ? '/article/' : `${basePath}/article/`;
  const catBase = isNookieDomain ? '/category/' : `${basePath}/category/`;

  const sectionsHtml = sections.map((s, i) => `
    ${i === 1 && pullQuote ? `<blockquote class="nk-article-pullquote">${nkEsc(pullQuote)}</blockquote>` : ''}
    <div>
      <h2>${nkEsc(s.heading)}</h2>
      ${(s.paragraphs || []).map(p =>
        `<p>${(p.includes('<a ') || p.includes('<strong>')) ? p : nkEsc(p)}</p>`
      ).join('')}
    </div>
  `).join('');

  const faqsHtml = faqs.length ? `
    <div class="nk-article-faq">
      <h2>Frequently Asked Questions</h2>
      ${faqs.map(f => `
        <details class="nk-faq-item">
          <summary>${nkEsc(f.q)}</summary>
          <p>${nkEsc(f.a)}</p>
        </details>
      `).join('')}
    </div>` : '';

  const tagsHtml = tags.length ? `
    <div class="nk-article-tags">
      ${tags.map(t => `<a href="${catBase}${nkEsc(article.category)}" class="nk-article-tag">${nkEsc(t)}</a>`).join('')}
    </div>` : '';

  const sourcesHtml = sources.length ? `
    <div class="nk-article-sources">
      <p class="nk-article-sources-label">Sources</p>
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
        ${sources.map(s => s.url
          ? `<a href="${nkEsc(s.url)}" target="_blank" rel="noopener nofollow">${nkEsc(s.name)}</a>`
          : `<span>${nkEsc(s.name)}</span>`
        ).join('<span style="color:var(--nk-border)">·</span>')}
      </div>
    </div>` : '';

  const canonicalSlug = isNookieDomain
    ? `https://thenookienook.com/article/${article.slug}`
    : `https://thenookienook.com/article/${article.slug}`;

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
    '@type': 'Article',
    headline: article.title,
    description: article.description,
    url: canonicalSlug,
    datePublished: article.published_at,
    dateModified: article.updated_at || article.published_at,
    publisher: { '@type': 'Organization', name: 'The Nookie Nook', url: 'https://thenookienook.com' },
    about: { '@type': 'Thing', name: 'Sex Education' },
  };

  const body = `
    <article class="nk-article">
      <a href="${basePath}/" class="nk-article-back">← Back to The Nookie Nook</a>

      <div class="nk-article-meta-top">
        <span class="nk-article-cat-badge" style="background:${catColor}">${catLabel}</span>
        <span class="nk-article-date">${published}</span>
        <span class="nk-article-readtime">${readingTime} min read</span>
      </div>

      <h1 class="nk-article-headline">${nkEsc(article.title)}</h1>

      ${article.image ? `<figure class="nk-article-hero-img"><img src="${nkEsc(article.image)}" alt="${nkEsc(article.image_alt || article.title)}" loading="lazy" width="720" height="405"></figure>` : ''}

      <div class="nk-disclaimer">
        📚 Educational content for informational purposes. Consult a healthcare provider for medical advice.
      </div>

      ${article.lede ? `<p class="nk-article-lede">${nkEsc(article.lede)}</p>` : ''}

      ${takeaways && takeaways.length ? `
      <div class="nk-article-takeaways">
        <p class="nk-takeaways-label">Key Takeaways</p>
        <ul>${takeaways.map(t => `<li>${nkEsc(t)}</li>`).join('')}</ul>
      </div>` : ''}

      ${keyStat ? `
      <div class="nk-article-keystat">
        <span class="nk-keystat-value">${nkEsc(keyStat.value)}</span>
        <span class="nk-keystat-label">${nkEsc(keyStat.label)}</span>
      </div>` : ''}

      <div class="nk-article-body">
        ${sectionsHtml}
      </div>

      ${tagsHtml}
      ${sourcesHtml}
      ${faqsHtml}
    </article>
  `;

  return nookieLayout({
    title: `${article.title} | The Nookie Nook`,
    description: article.description || article.lede || '',
    canonical: canonicalSlug,
    schemaJson: faqSchema ? [articleSchema, faqSchema] : articleSchema,
    activeNav: article.category,
    basePath,
    body,
  });
}
