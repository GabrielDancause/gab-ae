import { describe, it, expect } from 'vitest';
import { esc, layout } from '../templates/layout.js';

describe('esc()', () => {
  it('returns empty string for falsy values', () => {
    expect(esc(null)).toBe('');
    expect(esc(undefined)).toBe('');
    expect(esc('')).toBe('');
    expect(esc(0)).toBe('');
  });

  it('escapes ampersands', () => {
    expect(esc('A & B')).toBe('A &amp; B');
  });

  it('escapes double quotes', () => {
    expect(esc('say "hello"')).toBe('say &quot;hello&quot;');
  });

  it('escapes less-than signs', () => {
    expect(esc('<script>')).toBe('&lt;script&gt;');
  });

  it('escapes greater-than signs', () => {
    expect(esc('a > b')).toBe('a &gt; b');
  });

  it('escapes all special characters together', () => {
    expect(esc('<a href="x">A & B</a>')).toBe('&lt;a href=&quot;x&quot;&gt;A &amp; B&lt;/a&gt;');
  });

  it('leaves plain text unchanged', () => {
    expect(esc('Hello World')).toBe('Hello World');
  });

  it('handles numeric input by returning empty string (falsy 0)', () => {
    expect(esc(0)).toBe('');
  });
});

describe('layout()', () => {
  const baseProps = {
    title: 'Test Page',
    description: 'A test description',
    canonical: 'https://gab.ae/test',
    schemaJson: null,
    body: '<p>Hello</p>',
  };

  it('returns a string starting with <!DOCTYPE html>', () => {
    const html = layout(baseProps);
    expect(html).toMatch(/^<!DOCTYPE html>/);
  });

  it('includes the page title (escaped) in a <title> tag', () => {
    const html = layout({ ...baseProps, title: 'My <Page> & "Title"' });
    expect(html).toContain('<title>My &lt;Page&gt; &amp; &quot;Title&quot;</title>');
  });

  it('includes the meta description (escaped)', () => {
    const html = layout({ ...baseProps, description: 'desc & more' });
    expect(html).toContain('content="desc &amp; more"');
  });

  it('includes the canonical URL', () => {
    const html = layout(baseProps);
    expect(html).toContain('<link rel="canonical" href="https://gab.ae/test">');
  });

  it('includes OG meta tags', () => {
    const html = layout(baseProps);
    expect(html).toContain('og:title');
    expect(html).toContain('og:description');
    expect(html).toContain('og:url');
    expect(html).toContain('og:type');
    expect(html).toContain('og:site_name');
  });

  it('includes Twitter Card meta tags', () => {
    const html = layout(baseProps);
    expect(html).toContain('twitter:card');
    expect(html).toContain('twitter:title');
    expect(html).toContain('twitter:description');
  });

  it('includes the body content in <main>', () => {
    const html = layout(baseProps);
    expect(html).toContain('<p>Hello</p>');
  });

  it('omits JSON-LD script when schemaJson is null', () => {
    const html = layout({ ...baseProps, schemaJson: null });
    expect(html).not.toContain('application/ld+json');
  });

  it('injects JSON-LD script tag when schemaJson is provided as object', () => {
    const schema = { '@context': 'https://schema.org', '@type': 'WebPage', name: 'Test' };
    const html = layout({ ...baseProps, schemaJson: schema });
    expect(html).toContain('<script type="application/ld+json">');
    expect(html).toContain('"@type":"WebPage"');
  });

  it('injects JSON-LD script tag when schemaJson is an array', () => {
    const schemas = [
      { '@context': 'https://schema.org', '@type': 'WebPage' },
      { '@context': 'https://schema.org', '@type': 'FAQPage' },
    ];
    const html = layout({ ...baseProps, schemaJson: schemas });
    expect(html).toContain('<script type="application/ld+json">');
    expect(html).toContain('"@type":"WebPage"');
    expect(html).toContain('"@type":"FAQPage"');
  });

  it('includes nav with GAB brand link', () => {
    const html = layout(baseProps);
    expect(html).toContain('<a href="/" class="text-xl font-bold text-white hover:text-accent transition-colors">GAB</a>');
  });

  it('includes nav links to /news and /resources', () => {
    const html = layout(baseProps);
    expect(html).toContain('href="/news"');
    expect(html).toContain('href="/resources"');
  });

  it('includes a footer', () => {
    const html = layout(baseProps);
    expect(html).toContain('<footer');
    expect(html).toContain('gab.ae');
  });

  it('includes the current year in footer copyright', () => {
    const html = layout(baseProps);
    expect(html).toContain(String(new Date().getFullYear()));
  });

  it('closes with </html>', () => {
    const html = layout(baseProps);
    expect(html.trimEnd()).toMatch(/<\/html>$/);
  });
});
