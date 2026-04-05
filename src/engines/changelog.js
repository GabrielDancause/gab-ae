/**
 * Changelog / Updates renderer for gab.ae
 * 
 * Renders the public changelog at /updates from the `changelog` D1 table.
 * Each entry has: action (upgrade/create/rework/fix/expand), target, summary, details.
 * 
 * Called by worker.js when a request matches /updates.
 */
import { layout, esc } from '../templates/layout.js';

const ACTION_LABELS = {
  upgrade: { label: 'Upgraded', color: 'text-emerald-400', bg: 'bg-emerald-400/10' },
  create: { label: 'Created', color: 'text-blue-400', bg: 'bg-blue-400/10' },
  rework: { label: 'Reworked', color: 'text-amber-400', bg: 'bg-amber-400/10' },
  fix: { label: 'Fixed', color: 'text-red-400', bg: 'bg-red-400/10' },
  expand: { label: 'Expanded', color: 'text-purple-400', bg: 'bg-purple-400/10' },
};

const TYPE_LABELS = {
  tool: '🔧 Tool',
  news: '📰 News',
  page: '📄 Page',
  calculator: '🧮 Calculator',
  list: '📋 List',
  study: '📊 Study',
};

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

export function renderChangelog(entries) {
  const entriesHtml = entries.map(e => {
    const action = ACTION_LABELS[e.action] || ACTION_LABELS.upgrade;
    const typeLabel = TYPE_LABELS[e.target_type] || `📄 ${e.target_type}`;
    const targetUrl = `https://${e.target_domain}/${e.target_slug}`;
    const newsUrl = e.cluster_news_slug ? `https://${e.cluster_news_domain || 'gab.ae'}/news/${e.cluster_news_slug}` : null;

    return `
      <div class="border border-surface-border rounded-xl p-5 mb-4 hover:border-accent/30 transition-colors">
        <div class="flex items-center gap-3 mb-3">
          <span class="text-xs font-semibold px-2 py-0.5 rounded-full ${action.bg} ${action.color}">${action.label}</span>
          <span class="text-xs text-gray-500">${typeLabel}</span>
          <span class="text-xs text-gray-600 ml-auto">${formatDate(e.created_at)}</span>
        </div>
        <h3 class="text-base font-bold text-white mb-2">
          <a href="${esc(targetUrl)}" target="_blank" rel="noopener" class="hover:text-accent transition-colors">${esc(e.target_slug)}</a>
          <span class="text-xs text-gray-600 font-normal ml-2">${esc(e.target_domain)}</span>
        </h3>
        <p class="text-sm text-gray-300 leading-relaxed mb-3">${esc(e.summary)}</p>
        ${e.details ? `<details class="group"><summary class="text-xs text-gray-500 cursor-pointer hover:text-accent">Show details</summary><p class="text-xs text-gray-400 mt-2 pl-3 border-l border-surface-border leading-relaxed">${esc(e.details)}</p></details>` : ''}
        ${newsUrl ? `<div class="mt-3 pt-3 border-t border-surface-border"><span class="text-xs text-gray-500">Cluster article →</span> <a href="${esc(newsUrl)}" target="_blank" rel="noopener" class="text-xs text-accent hover:underline">${esc(e.cluster_news_slug)}</a></div>` : ''}
      </div>
    `;
  }).join('');

  const body = `
    <div class="max-w-3xl mx-auto">
      <div class="text-xs text-gray-500 mb-4">
        <a href="/" class="hover:text-accent">Home</a>
        <span class="mx-1">›</span>
        <span class="text-gray-400">Updates</span>
      </div>

      <h1 class="text-2xl md:text-3xl font-bold text-white mb-2">Site Updates</h1>
      <p class="text-gray-400 mb-8 text-sm">What's been built, upgraded, and reworked across the GAB network. Every change logged.</p>

      <div class="flex items-center gap-2 mb-6 text-xs text-gray-500">
        <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span>${entries.length} update${entries.length !== 1 ? 's' : ''} logged</span>
      </div>

      ${entriesHtml || '<p class="text-gray-500 text-sm">No updates yet.</p>'}
    </div>
  `;

  const schemaJson = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    "name": "Site Updates | GAB",
    "description": "Changelog of tools, pages, and content built and upgraded across the GAB network.",
    "url": "https://gab.ae/updates",
  };

  return layout({
    title: 'Site Updates | GAB',
    description: 'What\'s been built, upgraded, and reworked across the GAB network.',
    canonical: 'https://gab.ae/updates',
    schemaJson,
    body,
  });
}
