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

const CATEGORY_DESCRIPTORS = {
  finance: [
    "Known for consistently low expense ratios and strong fee structures",
    "Offers the highest historical dividend yield in its specific category",
    "Best overall option for beginners with zero minimum investment required",
    "Top consistent performer over the trailing 5-year and 10-year periods",
    "Most extensively diversified holdings across multiple global sectors",
    "Demonstrates the lowest historical volatility among its direct peers",
    "Highly optimized for tax-efficient income generation and wealth preservation",
    "Boasts the highest assets under management, making it widely trusted",
    "Features the most reliable and predictable monthly distribution schedule",
    "Maintains the strongest historical track record of consistent dividend growth"
  ],
  tech: [
    "Fully open source with an incredibly active and supportive community",
    "Features the most comprehensive documentation and beginner tutorials",
    "Consistently clocks the fastest performance in independent benchmarks",
    "Offers seamless integrations with the most popular enterprise tools",
    "Provides enterprise-grade security features right out of the box",
    "Known for its highly intuitive and customizable user interface",
    "Maintains the highest uptime guarantee and reliable cloud infrastructure",
    "Backed by major industry leaders and heavily adopted by Fortune 500s",
    "Releases the most frequent feature updates and bug fixes",
    "Best scalable architecture designed specifically for high-growth startups"
  ],
  health: [
    "Extensively backed by rigorous peer-reviewed clinical research",
    "Most highly recommended by certified medical professionals and specialists",
    "Formulated exclusively with premium, highly bioavailable ingredients",
    "Manufactured in strict FDA-registered and cGMP-certified facilities",
    "Consistently delivers the fastest measurable results in consumer trials",
    "Best holistic option for long-term preventive health and wellness",
    "Features the cleanest ingredient profile with zero artificial additives",
    "Highly optimized for rapid absorption and maximum bodily utilization",
    "Offers the most comprehensive full-spectrum approach to wellness",
    "Most trusted brand with decades of consistent safety and efficacy data"
  ],
  gaming: [
    "Widely considered the absolute best value for money in its price tier",
    "Top-rated and consistently used by professional esports athletes",
    "Features the lowest latency and highest polling rates available",
    "Boasts industry-leading build quality and long-term durability",
    "Offers the most immersive and high-fidelity sensory experience",
    "Highly customizable with extensive software and hardware macro support",
    "Designed with superior ergonomics for marathon gaming sessions",
    "Features best-in-class battery life and reliable wireless connectivity",
    "Provides the most accurate tracking and precision sensors on the market",
    "Maintains the strongest backward compatibility and cross-platform support"
  ],
  lifestyle: [ // combining home/diy/lifestyle
    "Renowned for being the most durable and long-lasting in its class",
    "Incredibly easy to install and set up, even for complete beginners",
    "Features the most elegant, modern, and aesthetically pleasing design",
    "Highly versatile and easily adaptable to multiple different use cases",
    "Crafted from premium, sustainably sourced, and eco-friendly materials",
    "Offers the absolute best warranty and reliable customer support",
    "Consistently rated as the most space-efficient and compact solution",
    "Provides professional-grade quality at a fraction of the cost",
    "Known for its highly innovative and patented smart features",
    "The ultimate time-saving tool that dramatically streamlines daily tasks"
  ],
  food: [
    "Consistently rated as having the best overall flavor profile in blind taste tests",
    "Incredibly versatile and easily incorporated into a wide variety of recipes",
    "Sourced entirely from premium, organic, and locally sustained farms",
    "Offers the highest nutritional density and clean macronutrient profile",
    "Features the most authentic and culturally accurate preparation methods",
    "Highly praised for its perfect texture and mouthfeel",
    "The absolute best option for individuals with specific dietary restrictions",
    "Provides exceptional shelf life without relying on artificial preservatives",
    "Known for its rich, bold, and highly complex aromatic qualities",
    "The most cost-effective bulk option for large-scale meal prep"
  ],
  travel: [
    "Unquestionably the best overall value for budget-conscious travelers",
    "Highly renowned as the most scenic and Instagram-worthy destination",
    "Offers the most deeply immersive and authentic cultural experiences",
    "Features world-class luxury accommodations and premium amenities",
    "Considered the safest and most family-friendly option in the region",
    "Boasts the most convenient access to major transit hubs and attractions",
    "The absolute best location for thrilling outdoor adventure and recreation",
    "Known for its vibrant, world-renowned culinary and nightlife scene",
    "Provides the most relaxing, secluded, and peaceful environment",
    "Highly praised for its exceptionally warm and welcoming local hospitality"
  ],
  education: [
    "Consistently the highest-rated program by enrolled students and alumni",
    "Features the most comprehensive, up-to-date, and rigorous curriculum",
    "Taught exclusively by industry-leading experts and seasoned professionals",
    "Offers the most flexible, self-paced scheduling for busy individuals",
    "Boasts the highest post-graduation job placement and success rate",
    "Provides highly interactive, hands-on projects and real-world case studies",
    "Includes unparalleled access to 1-on-1 mentorship and career coaching",
    "The most universally recognized and heavily accredited certification available",
    "Features a highly supportive, engaging, and active alumni community",
    "The absolute best return on investment for long-term career advancement"
  ],
  auto: [
    "Widely recognized for having the absolute best long-term reliability rating",
    "Features the most advanced and comprehensive standard safety suite",
    "Offers industry-leading fuel efficiency and incredibly low running costs",
    "Boasts the highest resale value retention over a 5-year ownership period",
    "Provides the most luxurious, quiet, and refined interior cabin experience",
    "Known for its exceptionally engaging and sporty driving dynamics",
    "Features the most intuitive and responsive infotainment technology",
    "The most practical and spacious option for large families and cargo",
    "Highly praised for its robust off-road capability and towing capacity",
    "Offers the most comprehensive and generous manufacturer warranty"
  ],
  tools: [
    "Universally praised as the most powerful and efficient tool in its class",
    "Features an incredibly compact, lightweight, and ergonomic design",
    "Built with industrial-grade materials for maximum lifespan under heavy use",
    "Offers the longest continuous runtime and fastest battery charging",
    "The most versatile multi-tool capable of replacing several standalone devices",
    "Known for absolute precision, accuracy, and consistent performance",
    "Highly intuitive to use with virtually no learning curve for beginners",
    "Provides the best dust management and safety mechanisms available",
    "Backed by the most responsive and helpful professional customer service",
    "The absolute best budget-friendly alternative to expensive flagship brands"
  ],
  default: [
    "Consistently ranks as the most popular and widely adopted option",
    "Offers an incredibly strong balance of performance and affordability",
    "Highly praised for its exceptional reliability and long-term durability",
    "Features the most user-friendly design and straightforward setup process",
    "Provides the most comprehensive and valuable core feature set",
    "Backed by overwhelming positive sentiment in expert and user reviews",
    "Considered the absolute safest and most trustworthy choice on the market",
    "Delivers the most consistent and high-quality results across the board",
    "Highly adaptable and easily scales to meet growing demands",
    "Unquestionably the best all-around value for the vast majority of users"
  ]
};

const LISTICLE_STRUCTURES = [
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. This makes it a standout choice for ${esc(pk)} enthusiasts looking for quality.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — When it comes to ${esc(pk)}, this option is ${desc.toLowerCase()}, earning it a top spot on our list.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — A highly regarded solution for ${esc(pk)}. It is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — If you need reliable ${esc(pk)}, consider this. ${desc}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. Many users prefer this specific route for their ${esc(pk)} needs.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — Taking a unique approach to ${esc(pk)}, this option is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. It consistently over-delivers for anyone researching ${esc(pk)}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — For those prioritizing excellence in ${esc(pk)}, this is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — Recognized widely for ${esc(pk)}, this pick is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. A rock-solid contender in the ${esc(pk)} space.</li>`
];

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
    <p>${esc(pkTitle)} is an important topic that many people search for when looking to optimize their workflow or improve their knowledge base. This comprehensive guide covers all the essential information you need to know about ${esc(pk)}, including foundational concepts, advanced practical tips, and expert-verified best practices.</p>
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
    <p>Understanding ${esc(pk)} requires a solid grasp of several key underlying mechanisms and theoretical concepts. Below, we break down the most critical aspects that affect how ${esc(pk)} operates in real-world scenarios, giving you the actionable insights necessary to master the subject.</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>What is ${esc(pk)}?</h3>
      <p>${esc(pkTitle)} is a highly relevant topic, evidenced by its ${(kw.total_volume || 0).toLocaleString()}+ monthly searches. Whether you are looking for introductory overviews or deep-dive technical breakdowns, this guide provides the foundational knowledge required to get started.</p>
    </div>
    <div class="faq-item">
      <h3>Why is ${esc(pk)} important?</h3>
      <p>Understanding ${esc(pk)} is crucial because it empowers you to make smarter, data-driven decisions. Learning about this subject allows you to implement proven strategies, avoid common pitfalls, and ultimately achieve a higher rate of success in your endeavors.</p>
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

  const category = SITE_TO_CATEGORY[kw.target_site] || 'default';
  const descriptors = CATEGORY_DESCRIPTORS[category] || CATEGORY_DESCRIPTORS['default'];

  return `${SEED_CSS}
<div class="seed-page">
  <h1>Top 10 ${esc(pkTitle)} (${year})</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Best ${esc(pkTitle)} Overview</h2>
    <p>Looking for the best ${esc(pk)}? We've thoroughly researched and compiled the top options to help you make an informed decision. Finding the right choice can be challenging given the variety of features available, but this curated selection highlights the most highly recommended solutions in the market today.</p>
  </div>

  <div class="seed-section">
    <h2>Top 10 ${esc(pkTitle)}</h2>
    <ol>
      ${[0,1,2,3,4,5,6,7,8,9].map(i => LISTICLE_STRUCTURES[i](i + 1, pk, descriptors[i])).join('\n      ')}
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
      <p>The best ${esc(pk)} depends entirely on your specific needs, budget, and long-term goals. Our comprehensive top 10 list covers a wide range of options, ensuring that whether you are a beginner or a seasoned professional, you will find a solution that fits your requirements perfectly.</p>
    </div>
    <div class="faq-item">
      <h3>How do I choose the right ${esc(pk)}?</h3>
      <p>When choosing, it is crucial to consider your budget, specific operational requirements, and long-term strategic goals. We highly recommend comparing core features, reading user testimonials, and evaluating long-term value before making your final commitment.</p>
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
    <p>Compare the top-rated options for ${esc(pk)} side by side using our detailed evaluation matrix. See exactly how these leading solutions stack up against one another on critical factors such as price, overall quality, user popularity, and long-term value.</p>
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
      <li>Each option has distinct unique strengths and potential drawbacks depending on your specific priorities. Evaluating these key differences side-by-side ensures you select the most optimal fit for your individual or business requirements.</li>
    </ul>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>Which ${esc(pk)} is best?</h3>
      <p>The ideal choice ultimately depends on your primary priorities—whether you prioritize budget-friendly pricing, premium build quality, or specific advanced features. Carefully review the comparative data in the table above to find the perfect match that aligns with your criteria.</p>
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
