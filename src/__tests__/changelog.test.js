import { describe, it, expect } from 'vitest';
import { renderChangelog } from '../engines/changelog.js';

function makeEntry(overrides = {}) {
  return {
    action: 'create',
    target_type: 'tool',
    target_slug: 'tip-calculator',
    target_domain: 'firemaths.info',
    summary: 'Added a new tip calculator tool.',
    details: null,
    created_at: '2025-03-10T12:00:00Z',
    cluster_news_slug: null,
    cluster_news_domain: null,
    ...overrides,
  };
}

describe('renderChangelog()', () => {
  it('returns a full HTML page string', () => {
    const html = renderChangelog([makeEntry()]);
    expect(typeof html).toBe('string');
    expect(html).toMatch(/^<!DOCTYPE html>/);
  });

  it('includes the Site Updates heading', () => {
    const html = renderChangelog([makeEntry()]);
    expect(html).toContain('Site Updates');
  });

  it('shows count of updates in plural form', () => {
    const html = renderChangelog([makeEntry(), makeEntry({ target_slug: 'another' })]);
    expect(html).toContain('2 updates logged');
  });

  it('shows count of updates in singular form', () => {
    const html = renderChangelog([makeEntry()]);
    expect(html).toContain('1 update logged');
  });

  it('shows "No updates yet." when entries array is empty', () => {
    const html = renderChangelog([]);
    expect(html).toContain('No updates yet.');
  });

  it('renders target slug as a link', () => {
    const html = renderChangelog([makeEntry()]);
    expect(html).toContain('tip-calculator');
    expect(html).toContain('https://firemaths.info/tip-calculator');
  });

  it('renders target domain in the entry', () => {
    const html = renderChangelog([makeEntry()]);
    expect(html).toContain('firemaths.info');
  });

  it('renders the summary text', () => {
    const html = renderChangelog([makeEntry()]);
    expect(html).toContain('Added a new tip calculator tool.');
  });

  // ── Action labels ───────────────────────────────────────────
  it('renders "Created" label for create action', () => {
    const html = renderChangelog([makeEntry({ action: 'create' })]);
    expect(html).toContain('Created');
  });

  it('renders "Upgraded" label for upgrade action', () => {
    const html = renderChangelog([makeEntry({ action: 'upgrade' })]);
    expect(html).toContain('Upgraded');
  });

  it('renders "Reworked" label for rework action', () => {
    const html = renderChangelog([makeEntry({ action: 'rework' })]);
    expect(html).toContain('Reworked');
  });

  it('renders "Fixed" label for fix action', () => {
    const html = renderChangelog([makeEntry({ action: 'fix' })]);
    expect(html).toContain('Fixed');
  });

  it('renders "Expanded" label for expand action', () => {
    const html = renderChangelog([makeEntry({ action: 'expand' })]);
    expect(html).toContain('Expanded');
  });

  it('falls back to "Upgraded" label for unknown action', () => {
    const html = renderChangelog([makeEntry({ action: 'unknown_action' })]);
    expect(html).toContain('Upgraded');
  });

  // ── Type labels ─────────────────────────────────────────────
  it('renders 🔧 Tool type label for tool type', () => {
    const html = renderChangelog([makeEntry({ target_type: 'tool' })]);
    expect(html).toContain('🔧 Tool');
  });

  it('renders 📰 News type label for news type', () => {
    const html = renderChangelog([makeEntry({ target_type: 'news' })]);
    expect(html).toContain('📰 News');
  });

  it('renders 🧮 Calculator type label for calculator type', () => {
    const html = renderChangelog([makeEntry({ target_type: 'calculator' })]);
    expect(html).toContain('🧮 Calculator');
  });

  it('renders dynamic type label for unknown types', () => {
    const html = renderChangelog([makeEntry({ target_type: 'widget' })]);
    expect(html).toContain('📄 widget');
  });

  // ── Details ─────────────────────────────────────────────────
  it('renders a details/summary block when details are present', () => {
    const html = renderChangelog([makeEntry({ details: 'These are the full details.' })]);
    expect(html).toContain('<details');
    expect(html).toContain('These are the full details.');
    expect(html).toContain('Show details');
  });

  it('omits details block when details is null', () => {
    const html = renderChangelog([makeEntry({ details: null })]);
    expect(html).not.toContain('Show details');
  });

  // ── Cluster news ─────────────────────────────────────────────
  it('renders cluster article link when cluster_news_slug is set', () => {
    const html = renderChangelog([makeEntry({
      cluster_news_slug: 'some-news-article',
      cluster_news_domain: 'gab.ae',
    })]);
    expect(html).toContain('Cluster article');
    expect(html).toContain('some-news-article');
    expect(html).toContain('https://gab.ae/news/some-news-article');
  });

  it('omits cluster article block when cluster_news_slug is null', () => {
    const html = renderChangelog([makeEntry({ cluster_news_slug: null })]);
    expect(html).not.toContain('Cluster article');
  });

  it('defaults cluster domain to gab.ae when cluster_news_domain is null', () => {
    const html = renderChangelog([makeEntry({
      cluster_news_slug: 'my-article',
      cluster_news_domain: null,
    })]);
    expect(html).toContain('https://gab.ae/news/my-article');
  });

  // ── Date formatting ──────────────────────────────────────────
  it('formats the created_at date in human-readable form', () => {
    const html = renderChangelog([makeEntry({ created_at: '2025-03-10T12:00:00Z' })]);
    expect(html).toContain('March 10, 2025');
  });

  it('handles missing created_at gracefully', () => {
    const html = renderChangelog([makeEntry({ created_at: null })]);
    expect(html).toBeTruthy();
    expect(html).not.toContain('undefined');
  });

  // ── Escaping ─────────────────────────────────────────────────
  it('escapes HTML in target_slug', () => {
    const html = renderChangelog([makeEntry({ target_slug: '<script>xss</script>' })]);
    expect(html).not.toContain('<script>xss</script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('escapes HTML in summary', () => {
    const html = renderChangelog([makeEntry({ summary: '<b>Bold</b> & "quoted"' })]);
    expect(html).not.toContain('<b>Bold</b>');
    expect(html).toContain('&lt;b&gt;Bold&lt;/b&gt;');
    expect(html).toContain('&amp;');
  });

  // ── Schema ───────────────────────────────────────────────────
  it('includes WebPage JSON-LD schema', () => {
    const html = renderChangelog([]);
    expect(html).toContain('"@type":"WebPage"');
    expect(html).toContain('"name":"Site Updates | GAB"');
  });

  it('sets canonical to /updates', () => {
    const html = renderChangelog([]);
    expect(html).toContain('https://gab.ae/updates');
  });

  // ── Multiple entries ─────────────────────────────────────────
  it('renders multiple entries', () => {
    const entries = [
      makeEntry({ target_slug: 'page-one', summary: 'Summary one.' }),
      makeEntry({ target_slug: 'page-two', summary: 'Summary two.' }),
      makeEntry({ target_slug: 'page-three', summary: 'Summary three.' }),
    ];
    const html = renderChangelog(entries);
    expect(html).toContain('page-one');
    expect(html).toContain('page-two');
    expect(html).toContain('page-three');
    expect(html).toContain('Summary one.');
    expect(html).toContain('Summary two.');
    expect(html).toContain('Summary three.');
  });
});
