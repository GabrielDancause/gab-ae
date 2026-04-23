import { callLLM } from './llm-client.js';

// ─── RSS parsing (supports both <item> RSS and <entry> Atom formats) ───
function parseRssItems(xml, source, hintCategory) {
  const items = [];
  const itemRegex  = /<item>([\s\S]*?)<\/item>/g;
  const entryRegex = /<entry>([\s\S]*?)<\/entry>/g;

  const parseBlock = (block) => {
    const title = (block.match(/<title><!\[CDATA\[(.*?)\]\]>/) || block.match(/<title[^>]*>(.*?)<\/title>/) || [])[1] || '';
    const link  = (block.match(/<link[^>]+href=["']([^"']+)["']/) || block.match(/<link>(.*?)<\/link>/) || [])[1] || '';
    const desc  = (block.match(/<description><!\[CDATA\[(.*?)\]\]>/) || block.match(/<description>(.*?)<\/description>/) || block.match(/<summary[^>]*>(.*?)<\/summary>/) || [])[1] || '';
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
  while ((m = itemRegex.exec(xml))  !== null) parseBlock(m[1]);
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

// ─── Pollinations.ai image fallback ───
function buildImageUrl(title, category, slug, site) {
  let seed = 0;
  for (let i = 0; i < slug.length; i++) seed = (seed * 31 + slug.charCodeAt(i)) & 0x7fffffff;
  const hint = site.imageHints[category] || site.defaultImageHint;
  const prompt = `${title}, ${hint}, ${site.imagePromptSuffix}`;
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=1200&height=675&nologo=true&seed=${seed}&model=flux`;
}

// ─── Slug generation ───
function slugify(text) {
  const year = new Date().getFullYear();
  let s = text.toLowerCase().replace(/['']/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  if (s.length > 80) s = s.slice(0, 80).replace(/-$/, '');
  return s.endsWith(String(year)) ? s : `${s}-${year}`;
}

// ─── Internal cross-link injection ───
function findInternalLinks(title, description, site) {
  const text = (title + ' ' + description).toLowerCase();
  const links = [];
  for (const [keyword, path] of Object.entries(site.internalLinks)) {
    if (text.includes(keyword)) links.push({ text: keyword, href: path });
  }
  return links.slice(0, 3);
}

// ─── Story relevance filter ───
function passesFilter(story, site) {
  const { filter } = site;
  if (!filter) return true;
  const text = (story.title + ' ' + story.description).toLowerCase();
  if (filter.type === 'exclude') {
    if (filter.keywords.some(kw => text.includes(kw))) return false;
    if (filter.paywallDomains.length) {
      try {
        const host = new URL(story.link).hostname;
        if (filter.paywallDomains.some(d => host.includes(d))) return false;
      } catch {}
    }
    return true;
  }
  if (filter.type === 'include') {
    return filter.keywords.some(kw => text.includes(kw));
  }
  return true;
}

// ─── SEO truncation ───
function enforceSeoBounds(article, site) {
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
    const fallback = site.dbSiteValue
      ? `${article.lede || article.title}. ${site.name}.`
      : `${article.lede || article.title + '. Latest news and analysis.'}`;
    article.description = fallback.slice(0, 155);
  }
}

// ─── Main generation function ───
export async function generateArticle(env, site) {
  const label = `[${site.id}]`;
  const apiKey = env.OPENROUTER_API_KEY || env.ANTHROPIC_API_KEY;
  if (!apiKey) { console.log(`❌ ${label} No API key`); return; }

  // 1. Dedup data — slugs always global (prevent cross-site collisions)
  // URL dedup is site-scoped for named sites, global for gab-ae (original behavior)
  const urlDedupQuery = site.dbSiteValue
    ? env.DB.prepare("SELECT source_url FROM news WHERE site = ? AND source_url IS NOT NULL ORDER BY published_at DESC LIMIT 2000").bind(site.dbSiteValue)
    : env.DB.prepare("SELECT source_url FROM news WHERE source_url IS NOT NULL ORDER BY published_at DESC LIMIT 2000");
  const [slugRows, urlRows] = await Promise.all([
    env.DB.prepare('SELECT slug FROM news ORDER BY published_at DESC LIMIT 500').all(),
    urlDedupQuery.all(),
  ]);
  const existingSlugs = new Set(slugRows.results.map(r => r.slug));
  const existingUrls  = new Set(urlRows.results.map(r => r.source_url).filter(Boolean));

  // 2. Fetch RSS feeds
  const allStories = [];
  const feedResults = await Promise.allSettled(site.feeds.map(async ([name, url, hint]) => {
    try {
      const resp = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(8000) });
      if (!resp.ok) return [];
      return parseRssItems(await resp.text(), name, hint);
    } catch { return []; }
  }));
  for (const r of feedResults) {
    if (r.status === 'fulfilled') allStories.push(...r.value);
  }
  console.log(`${label} 📡 Fetched ${allStories.length} stories`);
  if (!allStories.length) return;

  // 3. Filter: dedup + site-specific content filter
  const candidates = allStories.filter(s => {
    if (existingUrls.has(s.link)) return false;
    if (existingSlugs.has(slugify(s.title))) return false;
    return passesFilter(s, site);
  });
  console.log(`${label} ✅ ${candidates.length} candidates after filtering`);
  if (!candidates.length) return;

  // 4. Pick random from top 5
  const story = candidates.slice(0, 5)[Math.floor(Math.random() * Math.min(5, candidates.length))];
  console.log(`${label} 📰 Selected: ${story.title.slice(0, 80)}`);

  // 5. Fetch source article
  const { text: sourceText, image: fetchedImage } = await fetchArticleData(story.link);
  const sourceImage = story.image || fetchedImage || null;

  // 6. Build prompt from template
  const userPrompt = site.userPromptTemplate
    .replace('{source}', story.source)
    .replace('{hintCategory}', story.hintCategory || site.defaultCategory)
    .replace('{title}', story.title)
    .replace('{description}', story.description)
    .replace('{articleText}', sourceText.slice(0, 3000));

  // 7. Call LLM
  let article;
  try {
    const raw = await callLLM(apiKey, `${site.systemPrompt}\n\n${userPrompt}`, { maxTokens: 2048 });
    const trimmed = raw.trim();
    if (site.llmCanSkip && (trimmed === 'SKIP' || trimmed.startsWith('SKIP'))) {
      console.log(`${label} ⏭️ LLM skipped: ${story.title.slice(0, 60)}`);
      return;
    }
    article = JSON.parse(trimmed.replace(/^```json?\s*/, '').replace(/\s*```$/, '').trim());
  } catch (e) {
    console.log(`${label} ❌ LLM/parse error: ${e.message}`);
    return;
  }

  // 8. Validate structure
  if (!article.title || !article.sections || article.sections.length < 2) {
    console.log(`${label} ❌ Invalid article structure`);
    return;
  }
  enforceSeoBounds(article, site);

  // 9. Slug + final dedup
  const slug = slugify(article.title);
  if (existingSlugs.has(slug)) {
    console.log(`${label} ⏭️ Slug exists: ${slug}`);
    return;
  }

  // 10. Inject explore-more internal links
  const internalLinks = findInternalLinks(article.title, article.description || '', site);
  if (internalLinks.length > 0) {
    const linksHtml = internalLinks
      .map(l => `<a href="${site.pathPrefix}${l.href}">${l.text}</a>`)
      .join(' · ');
    article.sections.push({
      heading: site.exploreMoreHeading,
      paragraphs: [`${site.exploreMoreIntro}: ${linksHtml}`],
    });
  }

  // 11. Resolve image
  const imageUrl = sourceImage || buildImageUrl(article.title, article.category || site.defaultCategory, slug, site);

  // 12. Insert into D1
  const insertResult = await env.DB.prepare(
    `INSERT OR IGNORE INTO news
       (slug, title, description, category, lede, takeaways, key_stat, pull_quote,
        sections, tags, sources, faqs, source_url, image, published_at, updated_at, status, site)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'live', ?)`
  ).bind(
    slug,
    article.title,
    article.description || '',
    article.category || site.defaultCategory,
    article.lede || '',
    article.takeaways  ? JSON.stringify(article.takeaways)  : null,
    article.key_stat   ? JSON.stringify(article.key_stat)   : null,
    article.pull_quote || null,
    JSON.stringify(article.sections),
    JSON.stringify(article.tags    || []),
    JSON.stringify([{ name: story.source, url: story.link }]),
    JSON.stringify(article.faqs   || []),
    story.link,
    imageUrl,
    site.dbSiteValue,  // null for gab-ae, 'thenookienook' for nookie, etc.
  ).run();

  if (insertResult?.meta?.changes === 0) {
    console.log(`${label} ⏭️ Duplicate insert ignored: ${slug}`);
    return;
  }
  console.log(`${label} ✅ Published: ${slug} (${article.category})`);
  return { slug, title: article.title, category: article.category };
}
