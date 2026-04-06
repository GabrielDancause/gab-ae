import { describe, it, expect } from 'vitest';
import { renderNews } from '../engines/news.js';

function makePage(overrides = {}) {
  return {
    title: 'Big News Today',
    description: 'Something important happened.',
    slug: 'big-news-today',
    category: 'tech',
    published_at: '2025-01-15T10:00:00Z',
    updated_at: null,
    image: null,
    lede: 'Here is the short intro.',
    sections: JSON.stringify([
      { heading: 'Background', paragraphs: ['This is paragraph one.', 'This is paragraph two.'] },
      { heading: 'Details', paragraphs: ['More info here.'] },
    ]),
    tags: JSON.stringify(['AI', 'Tech', 'News']),
    sources: JSON.stringify([
      { name: 'Reuters', url: 'https://reuters.com' },
      { name: 'AP News', url: null },
    ]),
    faqs: JSON.stringify([
      { q: 'Why does this matter?', a: 'Because it changes everything.' },
    ]),
    ...overrides,
  };
}

describe('renderNews()', () => {
  it('returns a full HTML page string', () => {
    const html = renderNews(makePage());
    expect(typeof html).toBe('string');
    expect(html).toMatch(/^<!DOCTYPE html>/);
  });

  it('includes the article title in a <h1> tag', () => {
    const html = renderNews(makePage());
    expect(html).toContain('<h1');
    expect(html).toContain('Big News Today');
  });

  it('includes the lede paragraph when provided', () => {
    const html = renderNews(makePage());
    expect(html).toContain('Here is the short intro.');
  });

  it('omits the lede block when lede is absent', () => {
    const html = renderNews(makePage({ lede: null }));
    // Lede block is wrapped in a specific border-l-2 border-accent style
    expect(html).not.toContain('border-l-2 border-accent pl-4');
  });

  it('renders section headings', () => {
    const html = renderNews(makePage());
    expect(html).toContain('Background');
    expect(html).toContain('Details');
  });

  it('renders section paragraphs', () => {
    const html = renderNews(makePage());
    expect(html).toContain('This is paragraph one.');
    expect(html).toContain('This is paragraph two.');
    expect(html).toContain('More info here.');
  });

  it('renders tags as pill spans', () => {
    const html = renderNews(makePage());
    expect(html).toContain('AI');
    expect(html).toContain('Tech');
    expect(html).toContain('News');
  });

  it('omits tags block when tags array is empty', () => {
    const html = renderNews(makePage({ tags: '[]' }));
    // The tags pill uses a specific class combo absent from other elements
    expect(html).not.toContain('bg-surface border border-surface-border text-gray-400 px-2 py-1 rounded-full');
  });

  it('renders sources with links when url is present', () => {
    const html = renderNews(makePage());
    expect(html).toContain('href="https://reuters.com"');
    expect(html).toContain('Reuters');
  });

  it('renders sources as plain text when url is absent', () => {
    const html = renderNews(makePage());
    expect(html).toContain('AP News');
    // Ensure it doesn't wrap AP News in a link
    expect(html).not.toContain('href="null"');
  });

  it('omits sources block when sources array is empty', () => {
    const html = renderNews(makePage({ sources: '[]' }));
    expect(html).not.toContain('Sources');
  });

  it('renders FAQ section when faqs are provided', () => {
    const html = renderNews(makePage());
    expect(html).toContain('FAQ');
    expect(html).toContain('Why does this matter?');
    expect(html).toContain('Because it changes everything.');
  });

  it('omits FAQ section when faqs are empty', () => {
    const html = renderNews(makePage({ faqs: '[]' }));
    expect(html).not.toContain('<h2 class="text-lg font-bold text-white mb-4">FAQ</h2>');
  });

  it('includes FAQPage JSON-LD schema when faqs are provided', () => {
    const html = renderNews(makePage());
    expect(html).toContain('"@type":"FAQPage"');
    expect(html).toContain('"@type":"Question"');
  });

  it('does not include FAQPage schema when faqs are empty', () => {
    const html = renderNews(makePage({ faqs: '[]' }));
    expect(html).not.toContain('"@type":"FAQPage"');
  });

  it('includes NewsArticle JSON-LD schema', () => {
    const html = renderNews(makePage());
    expect(html).toContain('"@type":"NewsArticle"');
    expect(html).toContain('"headline":"Big News Today"');
  });

  it('includes breadcrumb navigation with /news link', () => {
    const html = renderNews(makePage());
    expect(html).toContain('href="/news"');
    expect(html).toContain('href="/"');
  });

  it('includes category breadcrumb link', () => {
    const html = renderNews(makePage());
    expect(html).toContain('/news/category/tech');
  });

  it('includes the category color gradient in the banner', () => {
    const techHtml = renderNews(makePage({ category: 'tech' }));
    expect(techHtml).toContain('from-cyan-900 to-cyan-700');

    const businessHtml = renderNews(makePage({ category: 'business' }));
    expect(businessHtml).toContain('from-emerald-900 to-emerald-700');
  });

  it('falls back to gray gradient for unknown categories', () => {
    const html = renderNews(makePage({ category: 'unknown' }));
    expect(html).toContain('from-gray-900 to-gray-700');
  });

  it('formats the published date in human-readable form', () => {
    const html = renderNews(makePage({ published_at: '2025-01-15T10:00:00Z' }));
    expect(html).toContain('January 15, 2025');
  });

  it('handles missing published_at gracefully', () => {
    const html = renderNews(makePage({ published_at: null }));
    expect(html).toBeTruthy();
    // Should not contain a date — empty string is rendered
    expect(html).not.toContain('undefined');
  });

  it('escapes HTML special characters in title within page elements', () => {
    const html = renderNews(makePage({ title: '<b>Breaking</b> & "News"' }));
    // The h1 and <title> tags must contain the escaped form
    expect(html).toContain('&lt;b&gt;Breaking&lt;/b&gt;');
    expect(html).toContain('&amp;');
    // The literal unescaped tag must NOT appear in the h1 or <title> context
    // (JSON-LD schema may legitimately contain raw text; check the h1 specifically)
    expect(html).not.toMatch(/<h1[^>]*>.*<b>Breaking<\/b>.*<\/h1>/s);
  });

  it('escapes HTML special characters in tags', () => {
    const html = renderNews(makePage({ tags: JSON.stringify(['<script>xss</script>']) }));
    // The escaped form must appear (in the tags pill)
    expect(html).toContain('&lt;script&gt;xss&lt;/script&gt;');
    // The unescaped form must not appear inside a tags pill span
    expect(html).not.toMatch(/rounded-full">&lt;!--[\s\S]*?--&gt;/);
    expect(html).not.toMatch(/<span[^>]*rounded-full[^>]*><script>/);
  });

  it('sets canonical URL using the slug', () => {
    const html = renderNews(makePage({ slug: 'big-news-today' }));
    expect(html).toContain('https://gab.ae/news/big-news-today');
  });

  it('renders noopener nofollow on source links', () => {
    const html = renderNews(makePage());
    expect(html).toContain('rel="noopener nofollow"');
  });

  it('handles empty sections gracefully', () => {
    const html = renderNews(makePage({ sections: '[]' }));
    expect(typeof html).toBe('string');
    expect(html).toMatch(/^<!DOCTYPE html>/);
  });

  it('passes raw HTML in paragraphs through unescaped when it contains anchor tags', () => {
    const page = makePage({
      sections: JSON.stringify([
        { heading: 'With Link', paragraphs: ['Check <a href="https://example.com">this</a> out.'] },
      ]),
    });
    const html = renderNews(page);
    expect(html).toContain('<a href="https://example.com">this</a>');
  });

  it('escapes plain text paragraphs (no a/strong tags)', () => {
    const page = makePage({
      sections: JSON.stringify([
        { heading: 'Plain', paragraphs: ['<img src=x onerror=alert(1)>'] },
      ]),
    });
    const html = renderNews(page);
    expect(html).not.toContain('<img src=x onerror=alert(1)>');
    expect(html).toContain('&lt;img');
  });
});
