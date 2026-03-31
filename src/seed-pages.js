/**
 * Seed Pages — Template-based page generator
 * Creates basic pages from keyword queue with zero LLM tokens.
 * Processes 1 keyword per cron run.
 */

const SITE_TO_APEX = {
  'westmount': 'capital-markets-wealth-guide-2026',
  'firemaths': 'capital-markets-wealth-guide-2026',
  'siliconbased': 'software-ai-infrastructure-guide-2026',
  'fixitwithducttape': 'software-ai-infrastructure-guide-2026',
  'leeroyjenkins': 'digital-media-creator-economy-guide-2026',
  'bodycount': 'human-optimization-health-guide-2026',
  '28grams': 'fine-arts-design-creative-guide-2026',
  'migratingmammals': 'global-mobility-geo-arbitrage-guide-2026',
  'sendnerds': 'education-knowledge-commerce-guide-2026',
  'getthebag': 'ecommerce-supply-chain-guide-2026',
  'pleasestartplease': 'ecommerce-supply-chain-guide-2026',
  'nookienook': 'interpersonal-dynamics-intimacy-guide-2026',
  'ijustwantto': 'real-estate-hospitality-guide-2026',
  'eeniemeenie': 'digital-media-creator-economy-guide-2026',
  'papyruspeople': 'digital-media-creator-economy-guide-2026',
  'justonemoment': 'digital-media-creator-economy-guide-2026',
};

const APEX_NAMES = {
  'capital-markets-wealth-guide-2026': 'Capital Markets & Wealth Guide',
  'software-ai-infrastructure-guide-2026': 'Software & AI Infrastructure Guide',
  'digital-media-creator-economy-guide-2026': 'Digital Media & Creator Economy Guide',
  'human-optimization-health-guide-2026': 'Human Optimization & Health Guide',
  'fine-arts-design-creative-guide-2026': 'Fine Arts, Design & Creative Guide',
  'global-mobility-geo-arbitrage-guide-2026': 'Global Mobility & Geo-Arbitrage Guide',
  'education-knowledge-commerce-guide-2026': 'Education & Knowledge Commerce Guide',
  'ecommerce-supply-chain-guide-2026': 'E-Commerce & Supply Chain Guide',
  'interpersonal-dynamics-intimacy-guide-2026': 'Interpersonal Dynamics & Intimacy Guide',
  'real-estate-hospitality-guide-2026': 'Real Estate & Hospitality Guide',
};

// Site-to-category mapping for pages table
const SITE_TO_CATEGORY = {
  'westmount': 'finance',
  'firemaths': 'finance',
  'siliconbased': 'tech',
  'fixitwithducttape': 'tech',
  'leeroyjenkins': 'gaming',
  'bodycount': 'health',
  '28grams': 'food',
  'migratingmammals': 'lifestyle',
  'sendnerds': 'education',
  'getthebag': 'lifestyle',
  'pleasestartplease': 'auto',
  'nookienook': 'health',
  'ijustwantto': 'lifestyle',
  'eeniemeenie': 'tools',
  'papyruspeople': 'tools',
  'justonemoment': 'tools',
};

const SEED_CSS = `
<style>
.seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #e2e8f0; }
.seed-page h1 { font-size: 1.75rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; line-height: 1.2; }
.seed-meta { font-size: 0.8rem; color: #64748b; margin-bottom: 2rem; }
.seed-section { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.seed-section h2 { font-size: 1.15rem; font-weight: 700; color: #818cf8; margin-bottom: 0.75rem; }
.seed-section h3 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem; }
.seed-section p { font-size: 0.95rem; line-height: 1.7; color: #94a3b8; margin-bottom: 0.5rem; }
.seed-section ul, .seed-section ol { padding-left: 1.25rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.8; }
.seed-section li { margin-bottom: 0.25rem; }
.seed-section .faq-item { border-top: 1px solid #1e1e2e; padding-top: 0.75rem; margin-top: 0.75rem; }
.seed-section .faq-item:first-child { border-top: none; padding-top: 0; margin-top: 0; }
.seed-explore { text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #64748b; }
.seed-explore a { color: #818cf8; text-decoration: underline; }
.seed-calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin: 1rem 0; }
.seed-calc-input, .seed-calc-output { background: #0a0a0a; border: 1px solid #1e1e2e; border-radius: 8px; padding: 0.75rem; }
.seed-calc-input label, .seed-calc-output label { display: block; font-size: 0.8rem; color: #64748b; margin-bottom: 0.25rem; }
.seed-calc-input input { width: 100%; background: transparent; border: none; color: #fff; font-size: 1.1rem; outline: none; }
.seed-calc-output .value { font-size: 1.3rem; font-weight: 700; color: #818cf8; }
.seed-compare-table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
.seed-compare-table th, .seed-compare-table td { padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid #1e1e2e; }
.seed-compare-table th { color: #818cf8; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
.seed-compare-table td { color: #94a3b8; }
@media (max-width: 640px) {
  .seed-page h1 { font-size: 1.35rem; }
  .seed-calc-grid { grid-template-columns: 1fr; }
  .seed-compare-table { font-size: 0.8rem; }
  .seed-compare-table th, .seed-compare-table td { padding: 0.4rem 0.5rem; }
}
</style>`;

function titleCase(str) {
  return str.replace(/\b\w/g, c => c.toUpperCase());
}

function esc(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getMonthYear() {
  const d = new Date();
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  return { month: months[d.getMonth()], year: d.getFullYear() };
}

function generateEducational(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkTitle = titleCase(pk);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkTitle)} — Complete Guide</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>What is ${esc(pkTitle)}?</h2>
    <p>${esc(pkTitle)} is a topic that many people search for. This guide covers the essential information you need to know about ${esc(pk)}, including key concepts, practical tips, and frequently asked questions.</p>
  </div>

  <div class="seed-section">
    <h2>Key Facts About ${esc(pkTitle)}</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related topics: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
    </ul>
  </div>

  <div class="seed-section">
    <h2>How ${esc(pkTitle)} Works</h2>
    <p>Understanding ${esc(pk)} requires knowledge of several key concepts. Below we break down the most important aspects that affect how ${esc(pk)} works in practice.</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>What is ${esc(pk)}?</h3>
      <p>${esc(pkTitle)} is a commonly searched topic with ${(kw.total_volume || 0).toLocaleString()}+ monthly searches. This guide covers everything you need to know.</p>
    </div>
    <div class="faq-item">
      <h3>Why is ${esc(pk)} important?</h3>
      <p>Understanding ${esc(pk)} can help you make better decisions. Many people search for this topic to learn practical strategies and tips.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateListicle(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkTitle = titleCase(pk);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>Top 10 ${esc(pkTitle)} (${year})</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Best ${esc(pkTitle)} Overview</h2>
    <p>Looking for the best ${esc(pk)}? We've researched and compiled the top options to help you make an informed decision.</p>
  </div>

  <div class="seed-section">
    <h2>Top 10 ${esc(pkTitle)}</h2>
    <ol>
      ${[1,2,3,4,5,6,7,8,9,10].map(n => `<li><strong>Option ${n}</strong> — A popular choice for ${esc(pk)} with strong performance and reliability.</li>`).join('\n      ')}
    </ol>
  </div>

  <div class="seed-section">
    <h2>How We Ranked These</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related topics: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
      <li>Based on user reviews, expert analysis, and market data</li>
    </ul>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>What is the best ${esc(pk)}?</h3>
      <p>The best ${esc(pk)} depends on your specific needs. Our top 10 list covers options for various use cases and budgets.</p>
    </div>
    <div class="faq-item">
      <h3>How do I choose the right ${esc(pk)}?</h3>
      <p>Consider your budget, specific requirements, and long-term goals. Compare features and read reviews before deciding.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateCalculator(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkTitle = titleCase(pk);
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkTitle)} Calculator</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Calculate ${esc(pkTitle)}</h2>
    <p>Use this calculator to quickly compute ${esc(pk)}. Enter your values below for instant results.</p>
    <div class="seed-calc-grid">
      <div class="seed-calc-input">
        <label>Value A</label>
        <input type="number" id="seed-input-a" placeholder="Enter value" oninput="seedCalc()">
      </div>
      <div class="seed-calc-input">
        <label>Value B</label>
        <input type="number" id="seed-input-b" placeholder="Enter value" oninput="seedCalc()">
      </div>
      <div class="seed-calc-output">
        <label>Result</label>
        <div class="value" id="seed-result">—</div>
      </div>
    </div>
    <script>
    function seedCalc() {
      var a = parseFloat(document.getElementById('seed-input-a').value) || 0;
      var b = parseFloat(document.getElementById('seed-input-b').value) || 0;
      document.getElementById('seed-result').textContent = (a + b).toLocaleString();
    }
    </script>
  </div>

  <div class="seed-section">
    <h2>How to Calculate ${esc(pkTitle)}</h2>
    <p>Understanding how to calculate ${esc(pk)} is straightforward. Enter your values above and the calculator will provide instant results based on standard formulas.</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>How do I use this ${esc(pk)} calculator?</h3>
      <p>Simply enter your values in the input fields above. The calculator will automatically compute and display the result.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateComparison(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkTitle = titleCase(pk);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkTitle)} — Side-by-Side Comparison</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>${esc(pkTitle)} Comparison</h2>
    <p>Compare the top options for ${esc(pk)} side by side. See how they stack up on key factors.</p>
    <table class="seed-compare-table">
      <thead>
        <tr><th>Feature</th><th>Option A</th><th>Option B</th><th>Option C</th></tr>
      </thead>
      <tbody>
        <tr><td>Price</td><td>$$</td><td>$$$</td><td>$</td></tr>
        <tr><td>Quality</td><td>High</td><td>Premium</td><td>Good</td></tr>
        <tr><td>Popularity</td><td>★★★★</td><td>★★★★★</td><td>★★★</td></tr>
        <tr><td>Value</td><td>Great</td><td>Good</td><td>Best</td></tr>
      </tbody>
    </table>
  </div>

  <div class="seed-section">
    <h2>Key Differences</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related comparisons: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
      <li>Each option has unique strengths depending on your priorities</li>
    </ul>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>Which ${esc(pk)} is best?</h3>
      <p>The best option depends on your priorities — whether you value price, quality, or specific features. Compare the table above to find your match.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

const GENERATORS = {
  educational: generateEducational,
  listicle: generateListicle,
  calculator: generateCalculator,
  comparison: generateComparison,
};

/**
 * Main seed function — processes 1 queued keyword per call.
 * @param {Object} env - Worker env with DB binding
 * @returns {Object} Result summary
 */
export async function seedPages(env) {
  // 1. Get next queued keyword
  const kw = await env.DB.prepare(
    "SELECT * FROM keyword_queue WHERE status = 'queued' ORDER BY score DESC LIMIT 1"
  ).first();

  if (!kw) {
    return { seeded: false, reason: 'no queued keywords' };
  }

  // 2. Check if slug already exists in pages
  const existing = await env.DB.prepare(
    "SELECT slug FROM pages WHERE slug = ?"
  ).bind(kw.slug).first();

  if (existing) {
    // Mark as skipped in keyword_queue
    await env.DB.prepare(
      "UPDATE keyword_queue SET status = 'skipped' WHERE slug = ?"
    ).bind(kw.slug).run();
    return { seeded: false, reason: 'slug already exists', slug: kw.slug };
  }

  // 3. Generate template HTML
  const pageType = kw.page_type || 'educational';
  const generator = GENERATORS[pageType] || GENERATORS.educational;
  const html = generator(kw);

  // 4. Build page metadata
  const pkTitle = titleCase(kw.primary_keyword);
  const titleSuffix = {
    educational: `${pkTitle} — Complete Guide`,
    listicle: `Top 10 ${pkTitle} (${new Date().getFullYear()})`,
    calculator: `${pkTitle} Calculator`,
    comparison: `${pkTitle} — Comparison`,
  };
  const title = (titleSuffix[pageType] || pkTitle) + ' | gab.ae';
  const description = `Everything you need to know about ${kw.primary_keyword}. ${(kw.total_volume || 0).toLocaleString()}+ monthly searches.`;
  const category = SITE_TO_CATEGORY[kw.target_site] || 'tools';
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const now = new Date().toISOString().replace('T', ' ').slice(0, 19);

  // 5. Insert into pages table (engine column has NOT NULL constraint)
  await env.DB.prepare(
    `INSERT INTO pages (slug, title, description, category, engine, html, status, quality, keyword, keyword_volume, keyword_kd, page_type, target_site, published_at, updated_at, created_at)
     VALUES (?, ?, ?, ?, 'seed', ?, 'live', 'template', ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    kw.slug, title, description, category, html,
    kw.primary_keyword, kw.total_volume || 0, kw.avg_kd || 0, pageType, kw.target_site || '',
    now, now, now
  ).run();

  // 6. Insert into tracked_pages
  try {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO tracked_pages (domain, path, title, apex_slug, cluster, status)
       VALUES ('gab.ae', ?, ?, ?, ?, 'active')`
    ).bind('/' + kw.slug, title, apexSlug, pageType).run();
  } catch (e) {
    console.log(`⚠️ tracked_pages insert failed: ${e.message}`);
  }

  // 7. Update keyword_queue status
  await env.DB.prepare(
    "UPDATE keyword_queue SET status = 'published', published_at = ? WHERE slug = ?"
  ).bind(now, kw.slug).run();

  console.log(`🌱 Seeded template page: ${kw.slug} (${pageType}, vol=${kw.total_volume})`);

  return {
    seeded: true,
    slug: kw.slug,
    keyword: kw.primary_keyword,
    pageType,
    volume: kw.total_volume,
    apexSlug,
  };
}
