/**
 * LLM News Generator — Haiku-powered article creation
 * Fetches RSS → picks best story → Haiku writes structured article → inserts into D1
 * Runs on CF cron, 1 article per run.
 */

// ─── RSS Feeds ───
const FEEDS = [
  ['NPR', 'https://feeds.npr.org/1001/rss.xml', null],
  ['BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml', null],
  ['BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml', 'business'],
  ['NYT World', 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml', null],
  ['NYT Business', 'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml', 'business'],
  ['CNBC Top', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'business'],
  ['TechCrunch', 'https://techcrunch.com/feed/', 'tech'],
  ['Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index', 'tech'],
  ['Science Daily', 'https://www.sciencedaily.com/rss/all.xml', 'science'],
  ['NPR Health', 'https://feeds.npr.org/1128/rss.xml', 'health'],
  ['ESPN', 'https://www.espn.com/espn/rss/news', 'sports'],
  ['Skift', 'https://skift.com/feed/', 'travel'],
];

const UK_DOMESTIC = ['nhs', 'uk government', 'downing street', 'labour party', 'conservative party',
  'premier league', 'bbc weather', 'uk housing', 'ofsted', 'channel crossing'];

const PAYWALL_DOMAINS = ['nytimes.com', 'wsj.com', 'ft.com', 'bloomberg.com', 'economist.com', 'washingtonpost.com'];

// ─── Internal links for cross-linking ───
const INTERNAL_LINKS = {
  'mortgage': '/mortgage-calculator', 'inflation': '/fire-movement',
  'invest': '/capital-markets-wealth-guide-2026', 'stock': '/capital-markets-wealth-guide-2026',
  'crypto': '/cryptocurrency-investing-guide', 'bitcoin': '/cryptocurrency-investing-guide',
  'real estate': '/real-estate-investing', 'tariff': '/capital-markets-wealth-guide-2026',
  'ai': '/software-ai-infrastructure-guide-2026', 'technology': '/software-ai-infrastructure-guide-2026',
  'health': '/human-optimization-health-guide-2026', 'travel': '/global-mobility-geo-arbitrage-guide-2026',
};

// ─── RSS parsing ───
function parseRssItems(xml, source, hintCategory) {
  const items = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let match;
  while ((match = itemRegex.exec(xml)) !== null) {
    const block = match[1];
    const title = (block.match(/<title><!\[CDATA\[(.*?)\]\]>/) || block.match(/<title>(.*?)<\/title>/) || [])[1] || '';
    const link = (block.match(/<link>(.*?)<\/link>/) || [])[1] || '';
    const desc = (block.match(/<description><!\[CDATA\[(.*?)\]\]>/) || block.match(/<description>(.*?)<\/description>/) || [])[1] || '';
    if (title && link) {
      items.push({ title: title.trim(), link: link.trim(), description: desc.replace(/<[^>]+>/g, '').trim(), source, hintCategory });
    }
  }
  return items.slice(0, 10);
}

// ─── Fetch article text ───
async function fetchArticleText(url) {
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36' },
      signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) return '';
    const html = await resp.text();
    // Extract paragraph text
    const paragraphs = [];
    const pRegex = /<p[^>]*>([\s\S]*?)<\/p>/gi;
    let m;
    while ((m = pRegex.exec(html)) !== null) {
      const text = m[1].replace(/<[^>]+>/g, '').trim();
      if (text.length > 60 && text.length < 1000 && !text.includes('©') && !text.includes('cookie')) {
        paragraphs.push(text);
      }
    }
    return paragraphs.slice(0, 12).join('\n\n');
  } catch {
    return '';
  }
}

// ─── Slug generation ───
function slugify(text) {
  const year = new Date().getFullYear();
  let s = text.toLowerCase().replace(/['']/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  if (s.length > 80) s = s.slice(0, 80).replace(/-$/, '');
  return s.endsWith(String(year)) ? s : `${s}-${year}`;
}

// ─── Find internal links ───
function findInternalLinks(title, description) {
  const text = (title + ' ' + description).toLowerCase();
  const links = [];
  for (const [keyword, path] of Object.entries(INTERNAL_LINKS)) {
    if (text.includes(keyword)) links.push({ text: keyword, href: path });
  }
  return links.slice(0, 3);
}

// ─── Call Haiku ───
async function callHaiku(apiKey, systemPrompt, userPrompt) {
  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 2048,
      messages: [
        { role: 'user', content: `${systemPrompt}\n\n${userPrompt}` },
      ],
    }),
  });
  const data = await resp.json();
  if (data.error) throw new Error(`Haiku error: ${JSON.stringify(data.error)}`);
  return data.content?.[0]?.text || '';
}

// ─── Main ───
export async function llmNews(env) {
  const apiKey = env.ANTHROPIC_API_KEY;
  if (!apiKey) { console.log('❌ No ANTHROPIC_API_KEY'); return; }

  // 1. Get existing slugs for dedup
  const existingRows = await env.DB.prepare(
    "SELECT slug, source_url FROM news ORDER BY published_at DESC LIMIT 100"
  ).all();
  const existingSlugs = new Set(existingRows.results.map(r => r.slug));
  const existingUrls = new Set(existingRows.results.map(r => r.source_url).filter(Boolean));

  // 2. Fetch RSS feeds
  const allStories = [];
  const feedPromises = FEEDS.map(async ([name, url, hint]) => {
    try {
      const resp = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        signal: AbortSignal.timeout(8000),
      });
      if (!resp.ok) return [];
      return parseRssItems(await resp.text(), name, hint);
    } catch { return []; }
  });
  const results = await Promise.allSettled(feedPromises);
  for (const r of results) {
    if (r.status === 'fulfilled') allStories.push(...r.value);
  }
  console.log(`📡 Fetched ${allStories.length} stories`);
  if (!allStories.length) return;

  // 3. Filter: dedup, skip UK domestic, skip paywalled
  const candidates = allStories.filter(s => {
    const lower = s.title.toLowerCase();
    if (UK_DOMESTIC.some(kw => lower.includes(kw))) return false;
    if (existingUrls.has(s.link)) return false;
    const slug = slugify(s.title);
    if (existingSlugs.has(slug)) return false;
    try {
      const host = new URL(s.link).hostname;
      if (PAYWALL_DOMAINS.some(d => host.includes(d))) return false;
    } catch {}
    return true;
  });
  console.log(`✅ ${candidates.length} candidates after filtering`);
  if (!candidates.length) return;

  // 4. Pick top candidate (random from top 5 for variety)
  const top = candidates.slice(0, 5);
  const story = top[Math.floor(Math.random() * top.length)];
  console.log(`📰 Selected: ${story.title.slice(0, 80)}`);

  // 5. Fetch source article text
  const sourceText = await fetchArticleText(story.link);

  // 6. Call Haiku to write the article
  const systemPrompt = `You are a professional news journalist writing for gab.ae, a news and tools website. Write factual, clear articles. Never fabricate quotes or data — if you don't know, say so. null over fake data, always.`;

  const userPrompt = `Write a news article based on this source. Return ONLY valid JSON, no markdown fences.

SOURCE: ${story.source}
TITLE: ${story.title}
DESCRIPTION: ${story.description}
ARTICLE TEXT:
${sourceText.slice(0, 3000)}

Return this exact JSON structure:
{
  "title": "compelling headline, 60-80 chars",
  "description": "meta description, 120-155 chars",
  "category": "one of: business, world, politics, tech, health, science, travel, sports, entertainment",
  "lede": "opening sentence that hooks the reader, 100-200 chars",
  "sections": [
    {"heading": "What Happened", "paragraphs": ["paragraph 1", "paragraph 2", "paragraph 3"]},
    {"heading": "Why It Matters", "paragraphs": ["paragraph 1", "paragraph 2"]},
    {"heading": "What Comes Next", "paragraphs": ["paragraph 1", "paragraph 2"]}
  ],
  "tags": ["category", "topic1", "topic2", "topic3"],
  "faqs": [
    {"q": "specific question about this story?", "a": "1-2 sentence answer from article content"},
    {"q": "another relevant question?", "a": "1-2 sentence answer"},
    {"q": "third question?", "a": "1-2 sentence answer"}
  ]
}

Rules:
- Each section MUST have at least 2 paragraphs, each 80-200 words
- FAQs must be specific to THIS story, not generic
- Total article should be 600-800 words
- Category must match the actual topic
- Tags: first tag = category, then 2-3 specific topic tags
- Do not invent facts. If the source text is thin, say "details are still emerging"`;

  let article;
  try {
    const raw = await callHaiku(apiKey, systemPrompt, userPrompt);
    // Extract JSON from response (handle potential markdown fences)
    const jsonStr = raw.replace(/^```json?\s*/, '').replace(/\s*```$/, '').trim();
    article = JSON.parse(jsonStr);
  } catch (e) {
    console.log(`❌ Haiku parse error: ${e.message}`);
    return;
  }

  // 7. Validate
  if (!article.title || !article.sections || article.sections.length < 2) {
    console.log('❌ Invalid article structure');
    return;
  }

  // 8. Build slug and internal links
  const slug = slugify(article.title);
  if (existingSlugs.has(slug)) {
    console.log(`⏭️ Slug already exists: ${slug}`);
    return;
  }

  const internalLinks = findInternalLinks(article.title, article.description || '');

  // Add explore-more section if we have internal links
  if (internalLinks.length > 0) {
    const linksHtml = internalLinks.map(l => `<a href="${l.href}">${l.text}</a>`).join(' · ');
    article.sections.push({
      heading: 'Explore More',
      paragraphs: [`Related topics on gab.ae: ${linksHtml}`],
    });
  }

  // 9. Insert into D1
  await env.DB.prepare(
    `INSERT OR IGNORE INTO news (slug, title, description, category, lede, sections, tags, sources, faqs, source_url, published_at, updated_at, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'live')`
  ).bind(
    slug,
    article.title,
    article.description || '',
    article.category || 'world',
    article.lede || '',
    JSON.stringify(article.sections),
    JSON.stringify(article.tags || []),
    JSON.stringify([{ name: story.source, url: story.link }]),
    JSON.stringify(article.faqs || []),
    story.link,
  ).run();

  console.log(`✅ Published: ${slug} (${article.category})`);
  return { slug, title: article.title, category: article.category };
}
