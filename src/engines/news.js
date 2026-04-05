/**
 * News article renderer for gab.ae
 * 
 * Renders structured news articles from the `news` D1 table.
 * Articles are stored as JSON sections [{heading, paragraphs}]
 * and rendered into the shared layout shell.
 * 
 * Called by worker.js when a request matches /news/{slug}.
 * 
 * Data flow: RSS → llm-news.js writes JSON to D1 → this file renders it as HTML
 */
import { layout, esc } from '../templates/layout.js';

export function renderNews(page) {
  const sections = JSON.parse(page.sections || '[]');
  const tags = JSON.parse(page.tags || '[]');
  const sources = JSON.parse(page.sources || '[]');
  const faqs = JSON.parse(page.faqs || '[]');
  const published = page.published_at ? new Date(page.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) : '';

  const sectionsHtml = sections.map(s => `
    <div class="mb-6">
      <h2 class="text-xl font-bold text-white mb-3">${esc(s.heading)}</h2>
      ${(s.paragraphs || []).map(p => `<p class="text-gray-300 leading-relaxed mb-3">${(p.includes('<a ') || p.includes('<strong>')) ? p : esc(p)}</p>`).join('')}
    </div>
  `).join('');

  const tagsHtml = tags.length ? `
    <div class="flex flex-wrap gap-2 mb-6">
      ${tags.map(t => `<span class="text-xs bg-surface border border-surface-border text-gray-400 px-2 py-1 rounded-full">${esc(t)}</span>`).join('')}
    </div>` : '';

  const sourcesHtml = sources.length ? `
    <div class="border-t border-surface-border pt-4 mt-8">
      <p class="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wider">Sources</p>
      <div class="flex flex-wrap gap-3">
        ${sources.map(s => s.url 
          ? `<a href="${esc(s.url)}" target="_blank" rel="noopener nofollow" class="text-xs text-accent hover:underline">${esc(s.name)}</a>` 
          : `<span class="text-xs text-gray-500">${esc(s.name)}</span>`
        ).join('<span class="text-gray-700">·</span>')}
      </div>
    </div>` : '';

  const faqsHtml = faqs.length ? `
    <div class="border-t border-surface-border pt-6 mt-8">
      <h2 class="text-lg font-bold text-white mb-4">FAQ</h2>
      ${faqs.map(f => `
        <details class="mb-3 group">
          <summary class="cursor-pointer text-sm font-medium text-gray-200 hover:text-accent transition-colors">${esc(f.q)}</summary>
          <p class="text-sm text-gray-400 mt-2 pl-4">${esc(f.a)}</p>
        </details>
      `).join('')}
    </div>` : '';

  const faqSchema = faqs.length ? {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": faqs.map(f => ({
      "@type": "Question",
      "name": f.q,
      "acceptedAnswer": { "@type": "Answer", "text": f.a }
    }))
  } : null;

  const articleSchema = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": page.title,
    "description": page.description,
    "url": `https://gab.ae/news/${page.slug}`,
    "datePublished": page.published_at,
    "dateModified": page.updated_at || page.published_at,
    "image": page.image || undefined,
    "publisher": { "@type": "Organization", "name": "GAB", "url": "https://gab.ae" },
  };

  const schemaJson = faqSchema 
    ? [articleSchema, faqSchema] 
    : articleSchema;

  const body = `
    <article class="max-w-3xl mx-auto">
      <!-- Breadcrumb -->
      <div class="text-xs text-gray-500 mb-4">
        <a href="/" class="hover:text-accent">Home</a> 
        <span class="mx-1">›</span> 
        <a href="/news" class="hover:text-accent">News</a>
        <span class="mx-1">›</span>
        <a href="/news/category/${page.category}" class="hover:text-accent capitalize">${page.category}</a>
      </div>

      <!-- Headline -->
      <h1 class="text-2xl md:text-3xl font-bold text-white mb-3 leading-tight">${esc(page.title)}</h1>

      <!-- Meta -->
      <div class="flex items-center gap-3 text-xs text-gray-500 mb-6">
        <span class="capitalize bg-accent/10 text-accent px-2 py-0.5 rounded-full">${page.category}</span>
        <span>${published}</span>
      </div>

      ${tagsHtml}

      <!-- Category Banner -->
      <div class="w-full h-48 rounded-xl mb-6 bg-gradient-to-br ${({'world':'from-blue-900 to-blue-700','politics':'from-purple-900 to-purple-700','business':'from-emerald-900 to-emerald-700','health':'from-red-900 to-red-700','sports':'from-orange-900 to-orange-700','entertainment':'from-pink-900 to-pink-700','tech':'from-cyan-900 to-cyan-700','science':'from-indigo-900 to-indigo-700','climate':'from-green-900 to-green-700','travel':'from-amber-900 to-amber-700','us':'from-slate-900 to-slate-700'})[page.category] || 'from-gray-900 to-gray-700'} flex items-center justify-center"><span class="text-4xl font-black tracking-widest text-white/20">${(page.category || 'NEWS').toUpperCase()}</span></div>

      <!-- Lede -->
      ${page.lede ? `<p class="text-lg text-gray-200 font-medium leading-relaxed mb-6 border-l-2 border-accent pl-4">${esc(page.lede)}</p>` : ''}

      <!-- Sections -->
      ${sectionsHtml}

      ${sourcesHtml}
      ${faqsHtml}
    </article>

    <!-- Back to news -->
    <div class="max-w-3xl mx-auto mt-8">
      <a href="/news" class="text-sm text-accent hover:underline">← Back to News</a>
    </div>
  `;

  return layout({
    title: `${page.title} | GAB News`,
    description: page.description || page.lede || '',
    canonical: `https://gab.ae/news/${page.slug}`,
    schemaJson,
    body,
  });
}
