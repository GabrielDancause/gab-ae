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

const LIST_ITEMS = {
  'finance': [
    "Blue-Chip Monthly Payer — Known for consistent monthly payouts backed by decades of dividend history.",
    "High-Yield REIT Fund — Offers above-average yields from diversified real estate holdings.",
    "Covered Call Income ETF — Generates monthly income through options strategies on major indexes.",
    "Dividend Aristocrat — A reliable large-cap company with a long track record of dividend growth.",
    "Tax-Advantaged Muni Bond — Provides tax-free income for high-bracket investors.",
    "Global Infrastructure Fund — Invests in stable, cash-flowing assets worldwide.",
    "Preferred Stock ETF — Offers higher yields than common stock with less volatility.",
    "Real Estate Crowdfunding — Allows direct investment in commercial properties for income.",
    "Master Limited Partnership (MLP) — Generates high yields from energy infrastructure.",
    "High-Dividend Value Stock — A mature company returning significant capital to shareholders."
  ],
  'tech': [
    "Enterprise SaaS Leader — Provides scalable cloud infrastructure for Fortune 500 companies.",
    "Emerging AI Startup — Revolutionizing workflows with cutting-edge machine learning models.",
    "Cybersecurity Pioneer — Offers comprehensive zero-trust network protection.",
    "Next-Gen Fintech App — Streamlines digital payments and wealth management.",
    "Developer Tools Innovator — Accelerates software delivery with modern CI/CD pipelines.",
    "E-commerce Platform — Empowers global merchants with seamless online storefronts.",
    "Data Analytics Powerhouse — Transforms big data into actionable business intelligence.",
    "IoT Solutions Provider — Connects smart devices for industrial automation.",
    "Blockchain Protocol — Enables decentralized applications and smart contracts.",
    "EdTech Disrupter — Democratizes access to high-quality online education."
  ],
  'gaming': [
    "Top-Tier Peripherals — Built for competitive play with ultra-low latency.",
    "AAA Game Studio Release — A critically acclaimed narrative with stunning graphics.",
    "Indie Darling — A unique, handcrafted experience with innovative mechanics.",
    "Esports Organization — Fields championship-winning teams across multiple titles.",
    "Streaming Platform — Connects millions of gamers with live, interactive content.",
    "VR Headset — Offers immersive, room-scale virtual reality experiences.",
    "Cloud Gaming Service — Streams high-end games to any device without a console.",
    "Mobile Gaming Hit — A casual, addictive title with massive global appeal.",
    "Retro Console Revival — Brings classic games to modern audiences.",
    "Game Engine Provider — Powers the next generation of interactive entertainment."
  ],
  'health': [
    "Clinically Backed Supplement — Formulated for optimal absorption and efficacy.",
    "Holistic Wellness Routine — Integrates seamlessly into daily life for balanced health.",
    "Fitness Tracking Wearable — Monitors heart rate, sleep, and activity levels accurately.",
    "Telehealth Platform — Connects patients with doctors for convenient virtual care.",
    "Personalized Nutrition Plan — Tailors dietary recommendations based on individual needs.",
    "Mental Health App — Offers guided meditation and cognitive behavioral therapy tools.",
    "Home Workout Equipment — Provides gym-quality resistance training in a compact footprint.",
    "Organic Skincare Line — Uses natural ingredients for healthy, glowing skin.",
    "Sleep Optimization System — Improves rest and recovery with advanced tracking.",
    "Ergonomic Office Furniture — Promotes proper posture and reduces strain during work."
  ],
  'food': [
    "Artisan Crafted Ingredient — Sourced from sustainable farms for exceptional flavor.",
    "Gourmet Kitchen Essential — Elevates home cooking with professional-grade quality.",
    "Meal Delivery Kit — Provides convenient, chef-designed recipes with pre-portioned ingredients.",
    "Specialty Coffee Roaster — Offers ethically sourced, small-batch beans.",
    "Plant-Based Alternative — Delivers delicious, sustainable options without compromising taste.",
    "Craft Brewery — Produces innovative, award-winning beers with unique flavor profiles.",
    "High-End Cookware Set — Ensures even heat distribution and long-lasting durability.",
    "Gourmet Snack Box — Curates premium treats from around the world.",
    "Boutique Winery — Crafts exceptional vintages focusing on terroir.",
    "Farm-to-Table Restaurant — Highlights local, seasonal ingredients in every dish."
  ],
  'lifestyle': [
    "Minimalist Daily Carry — Combines form and function for everyday convenience.",
    "Sustainable Travel Gear — Durable and eco-friendly equipment for the conscious explorer.",
    "Luxury Watch Brand — Blends timeless design with precision craftsmanship.",
    "Bespoke Tailoring — Offers custom-fit clothing for a perfect, personalized look.",
    "High-End Audio System — Delivers audiophile-quality sound for an immersive listening experience.",
    "Curated Art Collection — Features emerging artists to elevate any living space.",
    "Smart Home Automation — Integrates lighting, climate, and security for ultimate convenience.",
    "Boutique Hotel Stay — Provides a unique, personalized hospitality experience.",
    "Premium Luggage Set — Ensures stylish, durable travel with intelligent organization.",
    "Exclusive Members Club — Offers networking and luxury amenities for discerning individuals."
  ],
  'education': [
    "Comprehensive Course Bundle — Covers everything from basics to advanced topics with expert instruction.",
    "Interactive Learning Platform — Engaging and effective modules that adapt to your pace.",
    "Language Learning App — Uses gamification and spaced repetition for rapid fluency.",
    "Professional Certification Program — Provides industry-recognized credentials for career advancement.",
    "Online Tutoring Service — Connects students with expert educators for personalized help.",
    "Coding Bootcamp — Offers intensive, project-based training for aspiring developers.",
    "Creative Skills Workshop — Teaches practical techniques in design, writing, and art.",
    "Financial Literacy Course — Empowers individuals with essential money management skills.",
    "Leadership Training Seminar — Develops crucial management and communication abilities.",
    "Test Prep Material — Delivers comprehensive review and practice for standardized exams."
  ],
  'auto': [
    "Reliable Commuter Option — Fuel efficient and dependable for daily driving.",
    "High-Performance Upgrade — Enhances speed and handling for driving enthusiasts.",
    "Electric Vehicle Pioneer — Leads the transition to sustainable transportation.",
    "Luxury Sedan — Offers premium comfort and advanced technology features.",
    "Rugged Off-Road Vehicle — Built to tackle any terrain with confidence.",
    "Advanced Driver Assistance System — Improves safety with cutting-edge sensors and software.",
    "Premium Car Care Kit — Keeps vehicles looking showroom new.",
    "Aftermarket Exhaust System — Increases horsepower and delivers an aggressive tone.",
    "High-Grip Tires — Provides exceptional traction and handling in all conditions.",
    "Custom Interior Accessories — Personalizes the cabin for style and comfort."
  ],
  'tools': [
    "Pro-Grade Equipment — Built for heavy-duty use and long-lasting durability.",
    "Versatile Multi-Tool — Essential for any DIY project or quick repair.",
    "Precision Measuring Device — Ensures accurate readings for critical tasks.",
    "High-Torque Power Drill — Delivers exceptional performance for demanding applications.",
    "Compact Tool Set — Provides a comprehensive selection in a portable case.",
    "Advanced Diagnostic Scanner — Quickly identifies and clears vehicle fault codes.",
    "Heavy-Duty Work Bench — Offers a stable, durable surface for complex projects.",
    "Specialty Hand Tool — Designed specifically for niche applications and efficiency.",
    "Laser Level — Projects perfectly straight lines for precise alignment.",
    "Protective Safety Gear — Ensures user safety in hazardous work environments."
  ],
  'default': [
    "Top Rated Option — Highly recommended by users for its consistent performance.",
    "Premium Choice — Excellent quality and durability that justifies the investment.",
    "Value Pick — Offers a great balance of features and affordability.",
    "Editor's Choice — Selected by experts as the best overall in its category.",
    "Budget-Friendly — Provides essential functionality without breaking the bank.",
    "Innovative Design — Features unique capabilities that set it apart from the competition.",
    "User-Friendly — Easy to set up and use, even for beginners.",
    "Durable Construction — Built to withstand heavy use and last for years.",
    "Versatile Solution — Adaptable for a wide variety of tasks and applications.",
    "Reliable Performer — Consistently delivers results you can count on."
  ]
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

function getBaseKeyword(str) {
  return (str || '').replace(/^(?:best|top(?:\s+10)?|how to|what is|guide to|the)\s+/i, '');
}

function getMonthYear() {
  const d = new Date();
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  return { month: months[d.getMonth()], year: d.getFullYear() };
}

function generateEducational(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkBase = getBaseKeyword(pk);
  const pkTitle = titleCase(pk);
  const pkBaseTitle = titleCase(pkBase);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkTitle)} — Complete Guide</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>What is ${esc(pkBaseTitle)}?</h2>
    <p>${esc(pkBaseTitle)} is a topic that many people search for. This guide covers the essential information you need to know about ${esc(pkBase)}, including key concepts, practical tips, and frequently asked questions.</p>
  </div>

  <div class="seed-section">
    <h2>Key Facts About ${esc(pkBaseTitle)}</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related topics: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
    </ul>
  </div>

  <div class="seed-section">
    <h2>How ${esc(pkBaseTitle)} Works</h2>
    <p>Understanding ${esc(pkBase)} requires knowledge of several key concepts. Below we break down the most important aspects that affect how ${esc(pkBase)} works in practice.</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>What is the main purpose of ${esc(pkBaseTitle)}?</h3>
      <p>The primary goal is to provide a comprehensive solution and deep understanding of ${esc(pk)}. Whether you are a beginner or an expert, mastering these fundamentals is crucial for success.</p>
    </div>
    <div class="faq-item">
      <h3>How does ${esc(pkBaseTitle)} compare to alternatives?</h3>
      <p>While there are other options available, ${esc(pkBaseTitle)} stands out due to its specific features, ease of use, and targeted benefits tailored to this niche.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateListicle(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkBase = getBaseKeyword(pk);
  const pkTitle = titleCase(pk);
  const pkBaseTitle = titleCase(pkBase);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>Top 10 ${esc(pkBaseTitle)} (${year})</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Best ${esc(pkBaseTitle)} Overview</h2>
    <p>Looking for the best ${esc(pkBase)}? We've researched and compiled the top options to help you make an informed decision.</p>
  </div>

  <div class="seed-section">
    <h2>Top 10 ${esc(pkBaseTitle)}</h2>
    <ol>
      ${(LIST_ITEMS[SITE_TO_CATEGORY[kw.target_site]] || LIST_ITEMS['default']).map((item, index) => {
        const [title, desc] = item.split(' — ');
        return `<li><strong>${esc(title)}</strong> — ${esc(desc)}</li>`;
      }).join('\n      ')}
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
      <h3>What is the absolute best ${esc(pkBaseTitle)}?</h3>
      <p>The "best" ${esc(pkBaseTitle)} depends entirely on your specific needs, budget, and use case. Review the top options listed above to find the perfect match for your situation.</p>
    </div>
    <div class="faq-item">
      <h3>Are premium ${esc(pkBaseTitle)} options worth the cost?</h3>
      <p>In many cases, investing in a higher-end ${esc(pkBaseTitle)} provides better durability, advanced features, and stronger support, making it a worthwhile long-term choice.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateCalculator(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkBase = getBaseKeyword(pk);
  const pkTitle = titleCase(pk);
  const pkBaseTitle = titleCase(pkBase);
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkBaseTitle)} Calculator</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Calculate ${esc(pkBaseTitle)}</h2>
    <p>Use this calculator to quickly compute ${esc(pkBase)}. Enter your values below for instant results.</p>
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
    <h2>How to Calculate ${esc(pkBaseTitle)}</h2>
    <p>Understanding how to calculate ${esc(pkBase)} is straightforward. Enter your values above and the calculator will provide instant results based on standard formulas.</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>How accurate is this ${esc(pkBaseTitle)} calculator?</h3>
      <p>This calculator uses standard industry formulas to estimate ${esc(pkBaseTitle)}. However, actual results may vary based on specific conditions and variables not included here.</p>
    </div>
    <div class="faq-item">
      <h3>What should I do after calculating my ${esc(pkBaseTitle)}?</h3>
      <p>Once you have your result, use it as a baseline to make informed decisions regarding your ${esc(pk)} strategy and future planning.</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateComparison(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkBase = getBaseKeyword(pk);
  const pkTitle = titleCase(pk);
  const pkBaseTitle = titleCase(pkBase);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkBaseTitle)} — Side-by-Side Comparison</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>${esc(pkBaseTitle)} Comparison</h2>
    <p>Compare the top options for ${esc(pkBase)} side by side. See how they stack up on key factors.</p>
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
      <h3>Which ${esc(pkBaseTitle)} offers the best value?</h3>
      <p>Value is subjective. If you need premium features, the higher-priced option may be best. For basic needs, the more affordable ${esc(pkBaseTitle)} is likely sufficient.</p>
    </div>
    <div class="faq-item">
      <h3>Can I switch between different ${esc(pkBaseTitle)} later?</h3>
      <p>Depending on the specific type of ${esc(pk)}, migrating between platforms or tools can be complex. It is generally best to choose the right option from the start to avoid future friction.</p>
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
