import { describe, it, expect } from 'vitest';
import { renderCalculator } from '../engines/calculator.js';

// Minimal helper to create a page object for renderCalculator
function makePage(overrides = {}) {
  return {
    title: 'Tip Calculator | gab.ae',
    description: 'Calculate your tip easily.',
    config: JSON.stringify({
      inputs: [
        { id: 'bill', label: 'Bill Amount', type: 'number', prefix: '$', default: 50 },
        { id: 'tipPct', label: 'Tip %', type: 'preset', options: [10, 15, 18, 20, 25], suffix: '%', default: 15 },
        { id: 'people', label: 'Number of People', type: 'number', default: 1, min: 1 },
      ],
      outputs: [
        { id: 'tip', label: 'Tip Amount', format: 'currency' },
        { id: 'total', label: 'Total', format: 'currency' },
        { id: 'perPerson', label: 'Per Person', format: 'currency' },
      ],
      formula: 'tip = bill * tipPct / 100; total = bill + tip; perPerson = total / people',
    }),
    content: null,
    faqs: null,
    ...overrides,
  };
}

describe('renderCalculator()', () => {
  it('returns a string (HTML)', () => {
    const html = renderCalculator(makePage());
    expect(typeof html).toBe('string');
    expect(html.length).toBeGreaterThan(0);
  });

  it('includes the page title (stripped of site suffix)', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('Tip Calculator');
    expect(html).not.toContain('| gab.ae');
  });

  it('includes the page description', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('Calculate your tip easily.');
  });

  it('renders a label for each input', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('Bill Amount');
    expect(html).toContain('Tip %');
    expect(html).toContain('Number of People');
  });

  it('renders input elements with the correct ids', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('id="bill"');
    expect(html).toContain('id="tipPct"');
    expect(html).toContain('id="people"');
  });

  it('renders preset buttons for preset-type input', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('preset-btn');
    expect(html).toContain('data-value="10"');
    expect(html).toContain('data-value="15"');
    expect(html).toContain('data-value="25"');
  });

  it('renders a prefix span for number inputs with prefix', () => {
    const html = renderCalculator(makePage());
    // The $ prefix for bill
    expect(html).toContain('<span class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">$</span>');
  });

  it('renders output placeholders for each output', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('id="out-tip"');
    expect(html).toContain('id="out-total"');
    expect(html).toContain('id="out-perPerson"');
  });

  it('renders output labels', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('Tip Amount');
    expect(html).toContain('Total');
    expect(html).toContain('Per Person');
  });

  it('inlines the formula string in the <script> block', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('tip = bill * tipPct / 100');
  });

  it('inlines input ids in the <script> block', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('"bill"');
    expect(html).toContain('"tipPct"');
    expect(html).toContain('"people"');
  });

  it('does not include a verdict block when config has no verdicts', () => {
    const html = renderCalculator(makePage());
    expect(html).not.toContain('id="verdict"');
  });

  it('renders a verdict block when config has verdicts', () => {
    const page = makePage({
      config: JSON.stringify({
        inputs: [{ id: 'score', label: 'Score', type: 'number', default: 50 }],
        outputs: [{ id: 'result', label: 'Result', format: 'number' }],
        formula: 'result = score',
        verdicts: [
          { max: 40, label: 'Low', color: 'red' },
          { max: 70, label: 'Medium', color: 'yellow' },
          { max: 100, label: 'High', color: 'green' },
        ],
        verdictOutput: 'result',
      }),
    });
    const html = renderCalculator(page);
    expect(html).toContain('id="verdict"');
  });

  it('renders content sections when provided', () => {
    const page = makePage({
      content: JSON.stringify([
        { heading: 'How It Works', body: '<p>Just enter numbers.</p>' },
      ]),
    });
    const html = renderCalculator(page);
    expect(html).toContain('How It Works');
    expect(html).toContain('Just enter numbers.');
  });

  it('renders content from sections key when content is an object with sections', () => {
    const page = makePage({
      content: JSON.stringify({ sections: [{ heading: 'Tips Section', body: '<p>Info</p>' }] }),
    });
    const html = renderCalculator(page);
    expect(html).toContain('Tips Section');
  });

  it('renders FAQ accordion when faqs are provided', () => {
    const page = makePage({
      faqs: JSON.stringify([
        { q: 'How do I tip?', a: 'Just enter the bill and tip percentage.' },
      ]),
    });
    const html = renderCalculator(page);
    expect(html).toContain('Frequently Asked Questions');
    expect(html).toContain('How do I tip?');
    expect(html).toContain('Just enter the bill and tip percentage.');
  });

  it('does not render FAQ section when faqs are empty', () => {
    const html = renderCalculator(makePage({ faqs: '[]' }));
    expect(html).not.toContain('Frequently Asked Questions');
  });

  it('escapes HTML in page title', () => {
    const page = makePage({ title: '<script>alert(1)</script>' });
    const html = renderCalculator(page);
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('sets min attribute when input has min defined', () => {
    const html = renderCalculator(makePage());
    expect(html).toContain('min="1"');
  });

  it('renders suffix span for preset inputs', () => {
    const html = renderCalculator(makePage());
    // The preset buttons show the suffix text e.g. "10%", "15%"
    expect(html).toContain('data-value="10"');
    // The suffix is appended to preset button text
    expect(html).toMatch(/10%/);
  });

  it('grid columns for outputs is capped at 3', () => {
    // With 3 outputs, should produce grid-cols-3
    const html = renderCalculator(makePage());
    expect(html).toContain('grid-cols-3');
  });

  it('grid columns is 1 when there is only one output', () => {
    const page = makePage({
      config: JSON.stringify({
        inputs: [{ id: 'x', label: 'X', type: 'number', default: 0 }],
        outputs: [{ id: 'y', label: 'Y', format: 'number' }],
        formula: 'y = x',
      }),
    });
    const html = renderCalculator(page);
    expect(html).toContain('grid-cols-1');
  });
});
