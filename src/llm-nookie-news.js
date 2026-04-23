/**
 * LLM Nookie News Generator — Automated sex education article creation from RSS feeds
 *
 * HOW IT WORKS:
 * 1. Fetches RSS feeds covering sexual health, relationships, LGBTQ+, reproductive health
 * 2. Filters: dedup against existing nookie slugs, skips off-topic stories
 * 3. Picks a random story from top 5 candidates
 * 4. Fetches full article text from source URL
 * 5. Sends to LLM → structured JSON (title, sections, FAQs)
 * 6. Inserts into D1 `news` table with site='thenookienook', status='live'
 *
 * SCHEDULE: Every 5 minutes via worker.js cron
 * CATEGORIES: sexual-health, relationships, lgbtq, wellness, education,
 *             research, reproductive-health, culture, mental-health, body-literacy
 */

import { callLLM } from './llm-client.js';

// ─── RSS Feeds ───
const FEEDS = [
  // Education & general sex ed
  ['Scarleteen', 'https://www.scarleteen.com/feed', 'education'],
  ['Advocates for Youth', 'https://www.advocatesforyouth.org/feed', 'education'],
  ['Bedsider', 'https://bedsider.org/features.rss', 'reproductive-health'],

  // LGBTQ+
  ['GLSEN', 'https://www.glsen.org/rss.xml', 'lgbtq'],
  ['The Advocate', 'https://www.advocate.com/rss.xml', 'lgbtq'],
  ['PinkNews', 'https://www.thepinknews.com/feed/', 'lgbtq'],
  ['Autostraddle', 'https://www.autostraddle.com/feed/', 'lgbtq'],
  ['Out Magazine', 'https://www.out.com/rss.xml', 'lgbtq'],
  ['GLAAD', 'https://www.glaad.org/blog/feed', 'lgbtq'],

  // Reproductive health
  ['Rewire News', 'https://rewirenewsgroup.com/feed/', 'reproductive-health'],

  // Wellness & relationships
  ['Psychology Today', 'https://www.psychologytoday.com/us/articles/rss', 'relationships'],
  ['Healthline Sexual Health', 'https://www.healthline.com/rss/sexual-health', 'sexual-health'],
  ['Women\'s Health', 'https://www.womenshealthmag.com/rss/all.xml/', 'wellness'],
  ['Men\'s Health', 'https://www.menshealth.com/rss/all.xml/', 'sexual-health'],
  ['Bustle', 'https://www.bustle.com/feeds/health', 'relationships'],

  // Research & broader health (filtered by keyword)
  ['NPR Health', 'https://feeds.npr.org/1128/rss.xml', 'sexual-health'],
  ['Science Daily Health', 'https://www.sciencedaily.com/rss/health_medicine.xml', 'research'],
  ['Medical News Today', 'https://www.medicalnewstoday.com/rss', 'sexual-health'],
  ['The Conversation Health', 'https://theconversation.com/us/health/articles.atom', 'research'],
];

// ─── Topic relevance filter ───
// Only stories with a direct sexual health / sexuality / relationships angle.
// Intentionally excludes broad health terms (hormone, teen, body image, etc.)
// that produce general health articles with no sexual angle.
const RELEVANT_KEYWORDS = [
  'sex', 'sexual', 'sexuality', 'sexually', 'sexology',
  'intimate', 'intimacy', 'intercourse',
  'relationship', 'relationships', 'romantic partner',
  'reproductive health', 'reproductive rights', 'contraception', 'contraceptive',
  'birth control', 'abortion', 'planned parenthood',
  'sti', 'std', 'sexually transmitted', 'hiv', 'aids', 'herpes', 'chlamydia',
  'gonorrhea', 'syphilis', 'hpv',
  'lgbtq', 'transgender', 'queer', 'lesbian', 'gay', 'bisexual', 'nonbinary',
  'intersex', 'asexual', 'coming out', 'same-sex',
  'consent', 'pleasure', 'libido', 'arousal', 'orgasm', 'desire',
  'masturbation', 'pornography', 'sex ed', 'sex education',
  'safer sex', 'condom', 'iud', 'endometriosis', 'pcos',
  'erectile', 'vaginismus', 'dyspareunia', 'vulva', 'penis',
  'kink', 'bdsm', 'polyamory', 'infidelity', 'affair',
  'sex therapy', 'sex worker', 'menstrual', 'menstruation',
  'fertility', 'pregnancy', 'pelvic floor', 'cervical', 'prostate',
];

function isRelevantStory(title, description) {
  const text = (title + ' ' + description).toLowerCase();
  return RELEVANT_KEYWORDS.some(kw => text.includes(kw));
}

// ─── Category image hints ───
const CAT_IMAGE_HINTS = {
  'sexual-health': 'health education, medical wellness, clean modern design',
  'relationships': 'couple connection, partnership, warm human interaction',
  'lgbtq': 'pride colors, diversity, inclusive community',
  'wellness': 'personal wellness, mindfulness, self-care, body positivity',
  'education': 'learning, books, knowledge, educational setting',
  'research': 'scientific research, laboratory, data visualization, study',
  'reproductive-health': 'reproductive health, medical wellness, clinic setting',
  'culture': 'diverse people, society, community, culture',
  'mental-health': 'mental wellness, calm, therapy, supportive environment',
  'body-literacy': 'human anatomy illustration, body awareness, educational diagram',
};

// ─── RSS parsing (supports both <item> and <entry> formats) ───
function parseRssItems(xml, source, hintCategory) {
  const items = [];
  // Try <item> (RSS)
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  // Try <entry> (Atom)
  const entryRegex = /<entry>([\s\S]*?)<\/entry>/g;

  const parseBlock = (block) => {
    const title = (block.match(/<title><!\[CDATA\[(.*?)\]\]>/) || block.match(/<title[^>]*>(.*?)<\/title>/) || [])[1] || '';
    const link = (block.match(/<link[^>]+href=["']([^"']+)["']/) || block.match(/<link>(.*?)<\/link>/) || [])[1] || '';
    const desc = (block.match(/<description><!\[CDATA\[(.*?)\]\]>/) || block.match(/<description>(.*?)<\/description>/) || block.match(/<summary[^>]*>(.*?)<\/summary>/) || [])[1] || '';
    if (title && link) {
      items.push({
        title: title.trim().replace(/<[^>]+>/g, ''),
        link: link.trim(),
        description: desc.replace(/<[^>]+>/g, '').trim(),
        source,
        hintCategory,
      });
    }
  };

  let m;
  while ((m = itemRegex.exec(xml)) !== null) parseBlock(m[1]);
  while ((m = entryRegex.exec(xml)) !== null) parseBlock(m[1]);
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
    let pm;
    while ((pm = pRegex.exec(html)) !== null) {
      const text = pm[1].replace(/<[^>]+>/g, '').trim();
      if (text.length > 60 && text.length < 1000 && !text.includes('©') && !text.includes('cookie')) {
        paragraphs.push(text);
      }
    }
    return { text: paragraphs.slice(0, 12).join('\n\n'), image: ogImage };
  } catch {
    return { text: '', image: null };
  }
}

// ─── AI image via Pollinations.ai ───
function buildImageUrl(title, category, slug) {
  let seed = 0;
  for (let i = 0; i < slug.length; i++) seed = (seed * 31 + slug.charCodeAt(i)) & 0x7fffffff;
  const hint = CAT_IMAGE_HINTS[category] || 'health education illustration';
  const prompt = `${title}, ${hint}, professional editorial photography, clean modern, high quality`;
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=1200&height=675&nologo=true&seed=${seed}&model=flux`;
}

// ─── Slug generation ───
function slugify(text) {
  const year = new Date().getFullYear();
  let s = text.toLowerCase().replace(/['']/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  if (s.length > 80) s = s.slice(0, 80).replace(/-$/, '');
  return s.endsWith(String(year)) ? s : `${s}-${year}`;
}

// ─── Internal links for The Nookie Nook ───
const INTERNAL_LINKS = {
  'consent': '/sexual-health-guide',
  'birth control': '/contraception-guide',
  'sexual health': '/sexual-health-guide',
  'relationships': '/healthy-relationships-guide',
  'lgbtq': '/lgbtq-health-guide',
  'sex education': '/sex-education-resources',
  'reproductive': '/reproductive-health-guide',
  'mental health': '/mental-health-sexuality',
  'body image': '/body-positivity-guide',
  'safer sex': '/safer-sex-guide',
};

function findInternalLinks(title, description) {
  const text = (title + ' ' + description).toLowerCase();
  const links = [];
  for (const [keyword, path] of Object.entries(INTERNAL_LINKS)) {
    if (text.includes(keyword)) links.push({ text: keyword, href: path });
  }
  return links.slice(0, 3);
}

// ─── Main ───
export async function llmNookieNews(env) {
  const apiKey = env.OPENROUTER_API_KEY || env.ANTHROPIC_API_KEY;
  if (!apiKey) { console.log('❌ [Nookie] No API key'); return; }

  // 1. Get existing nookie slugs for dedup
  const [slugRows, urlRows] = await Promise.all([
    env.DB.prepare("SELECT slug FROM news WHERE site = 'thenookienook' ORDER BY published_at DESC LIMIT 500").all(),
    env.DB.prepare("SELECT source_url FROM news WHERE site = 'thenookienook' AND source_url IS NOT NULL ORDER BY published_at DESC LIMIT 2000").all(),
  ]);
  const existingSlugs = new Set(slugRows.results.map(r => r.slug));
  const existingUrls = new Set(urlRows.results.map(r => r.source_url).filter(Boolean));

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
  console.log(`[Nookie] 📡 Fetched ${allStories.length} stories`);
  if (!allStories.length) return;

  // 3. Filter: dedup + topic relevance
  const candidates = allStories.filter(s => {
    if (existingUrls.has(s.link)) return false;
    const slug = slugify(s.title);
    if (existingSlugs.has(slug)) return false;
    return isRelevantStory(s.title, s.description);
  });
  console.log(`[Nookie] ✅ ${candidates.length} relevant candidates`);
  if (!candidates.length) return;

  // 4. Pick top candidate (random from top 5)
  const top = candidates.slice(0, 5);
  const story = top[Math.floor(Math.random() * top.length)];
  console.log(`[Nookie] 📰 Selected: ${story.title.slice(0, 80)}`);

  // 5. Fetch source article
  const { text: sourceText, image: fetchedImage } = await fetchArticleData(story.link);
  const sourceImage = story.image || fetchedImage || null;

  // 6. Call LLM
  const systemPrompt = `You are a professional sex educator and health journalist writing for The Nookie Nook, an evidence-based sex education website. Write factual, inclusive, non-judgmental articles that help readers understand sexual health, relationships, and human sexuality. Be affirming of all identities and relationship structures. Never shame, never fabricate. Use accessible language — avoid jargon without explanation. null over fake data, always.

CRITICAL: Only write the article if the story has a DIRECT, EXPLICIT connection to one of: sexual health, human sexuality, intimate relationships, sex education, reproductive health (contraception/abortion/fertility/STIs), or LGBTQ+ health. General health stories (heart disease, cancer, obesity, mental illness, diet) are NOT relevant unless they directly and specifically discuss sexual function, sexual health outcomes, or intimate relationships. When in doubt — return SKIP. Return exactly: SKIP`;

  const userPrompt = `Write a sex education article based on this source. Return ONLY valid JSON (no markdown fences), or SKIP if not relevant.

SOURCE: ${story.source}
CATEGORY HINT: ${story.hintCategory || 'sexual-health'}
TITLE: ${story.title}
DESCRIPTION: ${story.description}
ARTICLE TEXT:
${sourceText.slice(0, 3000)}

Return this exact JSON structure:
{
  "title": "educational headline, STRICTLY 40-58 characters",
  "description": "meta description, STRICTLY 70-155 characters",
  "category": "one of: sexual-health, relationships, lgbtq, wellness, education, research, reproductive-health, culture, mental-health, body-literacy",
  "lede": "opening sentence that hooks the reader, 100-200 chars, inclusive and educational",
  "takeaways": ["one-sentence key point", "one-sentence key point", "one-sentence key point"],
  "key_stat": {"value": "a striking number or short phrase", "label": "brief context"},
  "pull_quote": "a compelling educational quote from the article, 80-160 chars",
  "sections": [
    {"heading": "What the Research Shows", "paragraphs": ["paragraph 1", "paragraph 2", "paragraph 3"]},
    {"heading": "Why This Matters", "paragraphs": ["paragraph 1", "paragraph 2"]},
    {"heading": "What You Can Do", "paragraphs": ["paragraph 1", "paragraph 2"]}
  ],
  "tags": ["category", "topic1", "topic2", "topic3"],
  "faqs": [
    {"q": "specific question about this topic?", "a": "1-2 sentence answer"},
    {"q": "another question a curious reader might have?", "a": "1-2 sentence answer"},
    {"q": "third practical question?", "a": "1-2 sentence answer"}
  ]
}

Rules:
- Inclusive language: use "people with vaginas/penises" when appropriate, not just gendered terms
- Each section MUST have at least 2 paragraphs, each 80-200 words
- FAQs should answer real questions people search about this topic
- Total article 600-800 words
- Do not invent facts or studies
- Normalize the topic — avoid sensationalism`;

  let article;
  try {
    const raw = await callLLM(apiKey, `${systemPrompt}\n\n${userPrompt}`, { maxTokens: 2048 });
    const trimmed = raw.trim();
    if (trimmed === 'SKIP' || trimmed.startsWith('SKIP')) {
      console.log(`[Nookie] ⏭️ Story not relevant, skipping: ${story.title.slice(0, 60)}`);
      return;
    }
    const jsonStr = trimmed.replace(/^```json?\s*/, '').replace(/\s*```$/, '').trim();
    article = JSON.parse(jsonStr);
  } catch (e) {
    console.log(`[Nookie] ❌ LLM/parse error: ${e.message}`);
    return;
  }

  // 7. Validate + enforce SEO constraints
  if (!article.title || !article.sections || article.sections.length < 2) {
    console.log('[Nookie] ❌ Invalid article structure');
    return;
  }
  if (article.title.length > 60) {
    const cut = article.title.slice(0, 59);
    const sp = cut.lastIndexOf(' ');
    article.title = (sp > 24 ? cut.slice(0, sp) : cut) + '…';
  }
  if (article.description && article.description.length > 155) {
    const cut = article.description.slice(0, 152);
    const sp = cut.lastIndexOf(' ');
    article.description = (sp > 60 ? cut.slice(0, sp) : cut) + '…';
  }
  if (!article.description || article.description.length < 50) {
    article.description = (article.lede || article.title + '. Sex education from The Nookie Nook.').slice(0, 155);
  }

  // 8. Build slug and check dedup
  const slug = slugify(article.title);
  if (existingSlugs.has(slug)) {
    console.log(`[Nookie] ⏭️ Slug exists: ${slug}`);
    return;
  }

  const internalLinks = findInternalLinks(article.title, article.description || '');
  const imageUrl = sourceImage || buildImageUrl(article.title, article.category || 'sexual-health', slug);

  if (internalLinks.length > 0) {
    const linksHtml = internalLinks.map(l => `<a href="/thenookienook${l.href}">${l.text}</a>`).join(' · ');
    article.sections.push({
      heading: 'Learn More',
      paragraphs: [`Related topics on The Nookie Nook: ${linksHtml}`],
    });
  }

  // 9. Insert into D1 with site='thenookienook'
  const insertResult = await env.DB.prepare(
    `INSERT OR IGNORE INTO news (slug, title, description, category, lede, takeaways, key_stat, pull_quote, sections, tags, sources, faqs, source_url, image, published_at, updated_at, status, site)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'live', 'thenookienook')`
  ).bind(
    slug,
    article.title,
    article.description || '',
    article.category || 'sexual-health',
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

  if (insertResult?.meta?.changes === 0) {
    console.log(`[Nookie] ⏭️ Duplicate insert ignored: ${slug}`);
    return;
  }
  console.log(`[Nookie] ✅ Published: ${slug} (${article.category})`);
  return { slug, title: article.title, category: article.category };
}
