/**
 * LLM News Generator — Automated article creation from RSS feeds
 *
 * HOW IT WORKS:
 * 1. Fetches 14 RSS feeds (US-centric: NPR, ABC, CBS, Fox, Politico, The Hill, CNBC, etc.)
 * 2. Filters: dedup against existing slugs/URLs, skip UK domestic, skip paywalled
 * 3. Picks a random story from top 5 candidates
 * 4. Fetches full article text from source URL (paragraph extraction)
 * 5. Sends to LLM via OpenRouter → gets structured JSON (title, sections, FAQs)
 * 6. Inserts into D1 `news` table with status='live'
 *
 * SCHEDULE: Every 5 minutes via worker.js cron
 * RATE: 1 article per run (skips if no new candidates)
 *
 * ARTICLE STRUCTURE in D1:
 *   sections: [{heading, paragraphs}]  — rendered by engines/news.js
 *   faqs: [{q, a}]                     — rendered as FAQ section
 *   sources: [{name, url}]             — attribution
 *
 * CATEGORIES: us, business, politics, tech, health, science, travel, sports, entertainment, world
 *
 * Uses callLLM() from llm-client.js for the API call.
 */

// ─── RSS Feeds ───
const FEEDS = [
  ['NPR', 'https://feeds.npr.org/1001/rss.xml', 'us'],
  ['NPR Politics', 'https://feeds.npr.org/1014/rss.xml', 'politics'],
  ['NPR Health', 'https://feeds.npr.org/1128/rss.xml', 'health'],
  ['ABC News', 'https://abcnews.go.com/abcnews/topstories', 'us'],
  ['CBS News', 'https://www.cbsnews.com/latest/rss/main', 'us'],
  ['Fox News', 'https://moxie.foxnews.com/google-publisher/latest.xml', 'us'],
  ['Politico', 'https://www.politico.com/rss/politicopicks.xml', 'politics'],
  ['The Hill', 'https://thehill.com/rss/syndicator/19109/feed/', 'politics'],
  ['CNBC Top', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'business'],
  ['TechCrunch', 'https://techcrunch.com/feed/', 'tech'],
  ['Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index', 'tech'],
  ['Science Daily', 'https://www.sciencedaily.com/rss/all.xml', 'science'],
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

// ─── Fetch article text + og:image ───
async function fetchArticleData(url) {
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36' },
      signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) return { text: '', image: null };
    const html = await resp.text();

    const ogImage = (
      html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i) ||
      html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']/i)
    )?.[1] || null;

    const paragraphs = [];
    const pRegex = /<p[^>]*>([\s\S]*?)<\/p>/gi;
    let m;
    while ((m = pRegex.exec(html)) !== null) {
      const text = m[1].replace(/<[^>]+>/g, '').trim();
      if (text.length > 60 && text.length < 1000 && !text.includes('©') && !text.includes('cookie')) {
        paragraphs.push(text);
      }
    }
    return { text: paragraphs.slice(0, 12).join('\n\n'), image: ogImage };
  } catch {
    return { text: '', image: null };
  }
}

// ─── AI image via Pollinations.ai (free, no API key, FLUX model) ───
const CAT_IMAGE_HINTS = {
  us: 'American cityscape, USA landmark',
  world: 'global news, international scene',
  politics: 'government building, capitol, politics',
  business: 'business district, financial market, economy',
  tech: 'technology, digital innovation, modern devices',
  health: 'healthcare, medicine, hospital, wellness',
  science: 'scientific research, laboratory, discovery',
  sports: 'sports action, athletic competition, stadium',
  entertainment: 'entertainment venue, media, performance',
  travel: 'travel destination, landscape, journey',
  climate: 'nature, environment, climate landscape',
};

function buildImageUrl(title, category, slug) {
  // Deterministic seed so the same article always gets the same image
  let seed = 0;
  for (let i = 0; i < slug.length; i++) seed = (seed * 31 + slug.charCodeAt(i)) & 0x7fffffff;
  const hint = CAT_IMAGE_HINTS[category] || 'news scene';
  const prompt = `${title}, ${hint}, professional photojournalism, editorial photography, high quality, cinematic`;
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=1200&height=675&nologo=true&seed=${seed}&model=flux`;
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
    const re = new RegExp(`\\b${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`);
    if (re.test(text)) links.push({ text: keyword, href: path });
  }
  return links.slice(0, 3);
}

import { callLLM } from './llm-client.js';

// ─── Main ───
export async function llmNews(env) {
  const apiKey = env.OPENROUTER_API_KEY || env.ANTHROPIC_API_KEY;
  if (!apiKey) { console.log('❌ No OPENROUTER_API_KEY or ANTHROPIC_API_KEY'); return; }

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

  // 5. Fetch source article text + image
  const { text: sourceText, image: fetchedImage } = await fetchArticleData(story.link);
  const sourceImage = story.image || fetchedImage || null;

  // 6. Call LLM to write the article
  const systemPrompt = `You are a professional news journalist writing for gab.ae, a US-centric news website. Write factual, clear articles aimed at an American audience. Never fabricate quotes or data — if you don't know, say so. null over fake data, always.`;

  const userPrompt = `Write a news article based on this source. Return ONLY valid JSON, no markdown fences.

SOURCE: ${story.source}
CATEGORY HINT: ${story.hintCategory || 'us'}
TITLE: ${story.title}
DESCRIPTION: ${story.description}
ARTICLE TEXT:
${sourceText.slice(0, 3000)}

Return this exact JSON structure:
{
  "title": "compelling headline, STRICTLY 40-58 characters (Google truncates at 60!)",
  "description": "meta description, STRICTLY 70-155 characters",
  "category": "one of: us, business, politics, tech, health, science, travel, sports, entertainment, world — use 'us' for US domestic news, 'world' only for purely international stories with no US angle",
  "lede": "opening sentence that hooks the reader, 100-200 chars",
  "takeaways": ["one-sentence key point", "one-sentence key point", "one-sentence key point"],
  "key_stat": {"value": "a striking number or short phrase, e.g. '$4.2B' or '23 states'", "label": "brief context for the number, e.g. 'in federal funding cut'"},
  "pull_quote": "a compelling sentence from the article body — the single most quotable line, 80-160 chars",
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
    const raw = await callLLM(apiKey, `${systemPrompt}\n\n${userPrompt}`, { maxTokens: 2048 });
    // Extract JSON from response (handle potential markdown fences)
    const jsonStr = raw.replace(/^```json?\s*/, '').replace(/\s*```$/, '').trim();
    article = JSON.parse(jsonStr);
  } catch (e) {
    console.log(`❌ News LLM/parse error: ${e.message}${e.cause ? ` | cause: ${e.cause}` : ''}`);
    return;
  }

  // 7. Validate structure and enforce SEO constraints
  if (!article.title || !article.sections || article.sections.length < 2) {
    console.log('❌ Invalid article structure');
    return;
  }
  // Enforce title ≤ 60 chars
  if (article.title.length > 60) {
    const cut = article.title.slice(0, 59);
    const sp = cut.lastIndexOf(' ');
    article.title = (sp > 24 ? cut.slice(0, sp) : cut) + '…';
  }
  // Enforce description 70-155 chars
  if (article.description && article.description.length > 155) {
    const cut = article.description.slice(0, 152);
    const sp = cut.lastIndexOf(' ');
    article.description = (sp > 60 ? cut.slice(0, sp) : cut) + '…';
  }
  if (!article.description || article.description.length < 50) {
    article.description = (article.lede || article.title + '. Latest news and analysis.').slice(0, 155);
  }

  // 8. Build slug and internal links
  const slug = slugify(article.title);
  if (existingSlugs.has(slug)) {
    console.log(`⏭️ Slug already exists: ${slug}`);
    return;
  }

  const internalLinks = findInternalLinks(article.title, article.description || '');

  // Resolve final image: source og:image → Pollinations.ai fallback
  const imageUrl = sourceImage || buildImageUrl(article.title, article.category || 'us', slug);

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
    `INSERT OR IGNORE INTO news (slug, title, description, category, lede, takeaways, key_stat, pull_quote, sections, tags, sources, faqs, source_url, image, published_at, updated_at, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'live')`
  ).bind(
    slug,
    article.title,
    article.description || '',
    article.category || 'us',
    article.lede || '',
    article.takeaways ? JSON.stringify(article.takeaways) : null,
    article.key_stat ? JSON.stringify(article.key_stat) : null,
    article.pull_quote || null,
    JSON.stringify(article.sections),
    JSON.stringify(article.tags || []),
    JSON.stringify([{ name: story.source, url: story.link }]),
    JSON.stringify(article.faqs || []),
    story.link,
    imageUrl,
  ).run();

  console.log(`✅ Published: ${slug} (${article.category})`);
  return { slug, title: article.title, category: article.category };
}
