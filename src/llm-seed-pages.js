/**
 * LLM Seed Pages — Haiku-powered page generation
 * Picks best keyword from D1 → Haiku writes full HTML → inserts into D1
 * Runs on CF cron, 1 page per run.
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

const SITE_TO_CATEGORY = {
  'westmount': 'finance', 'firemaths': 'finance', 'siliconbased': 'tech',
  'fixitwithducttape': 'tech', 'leeroyjenkins': 'gaming', 'bodycount': 'health',
  '28grams': 'food', 'migratingmammals': 'travel', 'sendnerds': 'education',
  'getthebag': 'career', 'pleasestartplease': 'automotive', 'nookienook': 'health',
  'ijustwantto': 'home', 'eeniemeenie': 'tools', 'papyruspeople': 'tools',
  'justonemoment': 'tools',
};

const APEX_NAMES = {
  'capital-markets-wealth-guide-2026': 'Capital Markets & Wealth',
  'software-ai-infrastructure-guide-2026': 'Software & AI Infrastructure',
  'digital-media-creator-economy-guide-2026': 'Digital Media & Creator Economy',
  'human-optimization-health-guide-2026': 'Human Optimization & Health',
  'fine-arts-design-creative-guide-2026': 'Fine Arts, Design & Creative',
  'global-mobility-geo-arbitrage-guide-2026': 'Global Mobility & Geo-Arbitrage',
  'education-knowledge-commerce-guide-2026': 'Education & Knowledge Commerce',
  'ecommerce-supply-chain-guide-2026': 'E-Commerce & Supply Chain',
  'interpersonal-dynamics-intimacy-guide-2026': 'Interpersonal Dynamics & Intimacy',
  'real-estate-hospitality-guide-2026': 'Real Estate & Hospitality',
};

// ─── Call Haiku ───
async function callHaiku(apiKey, prompt) {
  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 4096,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  const data = await resp.json();
  if (data.error) throw new Error(`Haiku error: ${JSON.stringify(data.error)}`);
  return data.content?.[0]?.text || '';
}

// ─── Main ───
export async function llmSeedPages(env) {
  const apiKey = env.ANTHROPIC_API_KEY;
  if (!apiKey) { console.log('❌ No ANTHROPIC_API_KEY'); return; }

  // 1. Pick the best keyword: high CPC × volume, low KD
  const kw = await env.DB.prepare(
    `SELECT * FROM keyword_queue 
     WHERE status = 'queued' 
     ORDER BY score DESC 
     LIMIT 1`
  ).first();

  if (!kw) {
    console.log('❌ No queued keywords');
    return;
  }

  // 2. Check if slug already exists
  const existing = await env.DB.prepare(
    "SELECT slug FROM pages WHERE slug = ?"
  ).bind(kw.slug).first();

  if (existing) {
    await env.DB.prepare("UPDATE keyword_queue SET status = 'skipped' WHERE slug = ?").bind(kw.slug).run();
    console.log(`⏭️ Slug exists: ${kw.slug}`);
    return;
  }

  // 3. Get context — what apex/pillar does this keyword belong under?
  const targetSite = kw.target_site || 'siliconbased';
  const apexSlug = SITE_TO_APEX[targetSite] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'General';
  const category = SITE_TO_CATEGORY[targetSite] || 'tools';
  const pageType = kw.page_type || 'educational';

  console.log(`📝 Generating: "${kw.primary_keyword}" (${pageType}, ${category}, ${targetSite})`);

  // 4. Build the prompt based on page type
  const typeInstructions = {
    calculator: `Create a DATA-DRIVEN reference page about "${kw.primary_keyword}". Include:
- A clear explanation of what it measures/calculates and why it matters
- A reference table with common values, ranges, or benchmarks
- Step-by-step guide on how to calculate or interpret results manually
- Key factors that affect the result
- Do NOT include any JavaScript or interactive calculator — just informational content
- 3-5 FAQs specific to this topic`,

    educational: `Create a comprehensive EDUCATIONAL guide. Include:
- Clear explanation of what "${kw.primary_keyword}" is
- How it works (step-by-step if applicable)
- Key facts, statistics, or data points
- Practical tips or recommendations
- A comparison table if relevant (e.g. top options, plans, products)
- 3-5 FAQs that real people search for`,

    listicle: `Create a TOP 10 LISTICLE. Include:
- 10 items with name, key features, pros/cons, and a one-line verdict
- A quick comparison table at the top
- A "How We Picked" methodology section
- 3-5 FAQs about choosing the right option`,

    comparison: `Create a SIDE-BY-SIDE COMPARISON. Include:
- 2-4 options compared across multiple criteria
- A comparison table with clear winners per category
- Detailed analysis of each option
- A verdict: who should pick which option
- 3-5 FAQs about the comparison`,
  };

  const prompt = `You are a content writer for gab.ae. Create a high-quality ${pageType} page about "${kw.primary_keyword}".

This page sits under the "${apexName}" content hub in the ${category} category.

${typeInstructions[pageType] || typeInstructions.educational}

Return ONLY the raw HTML (no markdown fences, no explanation). The HTML must use these CSS classes:

<style>
.seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #e2e8f0; }
.seed-page h1 { font-size: 1.75rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; line-height: 1.2; }
.seed-meta { font-size: 0.8rem; color: #64748b; margin-bottom: 2rem; }
.seed-section { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.seed-section h2 { font-size: 1.15rem; font-weight: 700; color: #818cf8; margin-bottom: 0.75rem; }
.seed-section h3 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem; }
.seed-section p { font-size: 0.95rem; line-height: 1.7; color: #94a3b8; margin-bottom: 0.5rem; }
.seed-section ul, .seed-section ol { padding-left: 1.25rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.8; }
.seed-calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin: 1rem 0; }
.seed-calc-input { background: #0a0a0a; border: 1px solid #1e1e2e; border-radius: 8px; padding: 0.75rem; }
.seed-calc-input label { display: block; font-size: 0.8rem; color: #64748b; margin-bottom: 0.25rem; }
.seed-calc-input input, .seed-calc-input select { width: 100%; background: transparent; border: none; color: #fff; font-size: 1.1rem; outline: none; }
.seed-calc-output { background: #0a0a0a; border: 1px solid #1e1e2e; border-radius: 8px; padding: 0.75rem; }
.seed-calc-output .value { font-size: 1.3rem; font-weight: 700; color: #818cf8; }
.seed-explore { text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #64748b; }
.seed-explore a { color: #818cf8; text-decoration: underline; }
</style>

Structure:
1. <div class="seed-page"> wrapper
2. <h1> with a compelling title (NOT just the keyword repeated)
3. <p class="seed-meta"> with "Updated ${new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}"
4. Multiple <div class="seed-section"> blocks for content
5. FAQ section with <h3> questions and <p> answers
7. <p class="seed-explore"> with link to <a href="/${apexSlug}">${apexName} Guide</a>

Rules:
- Write like a human expert, not a template
- Use REAL data, stats, and specifics — not placeholder text
- If it's a calculator, the math MUST be correct
- Minimum 2000 characters of content
- Do NOT include any JavaScript, <script> tags, or interactive calculators
- Do NOT use HTML tables — use bullet lists, numbered lists, or card-style sections instead. Tables look terrible on mobile.
- No input fields, no forms — content only
- null over fake data — if you don't know exact numbers, use reasonable ranges with caveats`;

  let html;
  try {
    html = await callHaiku(apiKey, prompt);
    // Clean up: remove markdown fences if present
    html = html.replace(/^```html?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim();
    // Fix wrong dates from Haiku (training data cutoff)
    const currentDate = new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    html = html.replace(/Updated\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}/gi, 'Updated ' + currentDate);
  } catch (e) {
    console.log(`❌ Haiku error: ${e.message}`);
    return;
  }

  // 5. Validate
  if (!html.includes('seed-page') || html.length < 1000) {
    console.log(`❌ Invalid HTML output (${html.length} chars)`);
    return;
  }

  // 6. Build title and metadata
  // Extract h1 from generated HTML
  const h1Match = html.match(/<h1[^>]*>(.*?)<\/h1>/);
  const title = h1Match ? h1Match[1].replace(/<[^>]+>/g, '').trim() : kw.primary_keyword;
  const fullTitle = `${title} | gab.ae`;
  const description = `Everything you need to know about ${kw.primary_keyword}. Expert guide with tools, data, and FAQs.`;
  const now = new Date().toISOString().replace('T', ' ').slice(0, 19);

  // 7. Insert into pages
  await env.DB.prepare(
    `INSERT INTO pages (slug, title, description, category, engine, html, status, quality, keyword, keyword_volume, keyword_kd, page_type, target_site, published_at, updated_at, created_at)
     VALUES (?, ?, ?, ?, 'llm-haiku', ?, 'live', 'llm', ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    kw.slug, fullTitle, description, category, html,
    kw.primary_keyword, kw.total_volume || 0, kw.avg_kd || 0, pageType, targetSite,
    now, now, now
  ).run();

  // 8. Track page
  try {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO tracked_pages (domain, path, title, apex_slug, cluster, status)
       VALUES ('gab.ae', ?, ?, ?, ?, 'active')`
    ).bind('/' + kw.slug, fullTitle, apexSlug, pageType).run();
  } catch (e) {
    console.log(`⚠️ tracked_pages: ${e.message}`);
  }

  // 9. Update keyword queue
  await env.DB.prepare(
    "UPDATE keyword_queue SET status = 'published', published_at = ? WHERE slug = ?"
  ).bind(now, kw.slug).run();

  console.log(`✅ Published: ${kw.slug} (${pageType}, ${category}, ${kw.total_volume} vol)`);
  return { slug: kw.slug, title, pageType, category };
}
