// ─── Site Registry ───────────────────────────────────────────────────────────
// Each entry defines a complete news property.
// Adding a new site = add one object here. No new files needed.
//
// NOTE: If a site has an ownDomain, a matching [[routes]] entry must also be
// added manually in wrangler.toml (controls Cloudflare zone binding).
// ─────────────────────────────────────────────────────────────────────────────

export const SITES = [
  {
    // ── Identity ──
    id: 'gab-ae',
    dbSiteValue: null,           // stored in news.site; null = original gab.ae articles
    name: 'GAB.AE',
    eyebrow: 'Independent News & Analysis',
    tagline: 'All the stories that matter',
    footerTagline: 'Breaking news and analysis, updated daily.',
    footerCredit: 'Independent journalism powered by AI',

    // ── Routing ──
    pathPrefix: '',              // '' = root of domain
    ownDomain: 'gab.ae',
    articlePath: '/news',        // articles live at /news/:slug
    categoryPath: '/news/category',

    // ── Schema.org ──
    schemaType: 'NewsArticle',
    publisherName: 'GAB.AE',
    publisherUrl: 'https://gab.ae',
    aboutThing: null,

    // ── Generation schedule ──
    cronModulo: 5,               // fire every cron tick (cron runs every 5 min)
    cronOffset: 0,

    // ── RSS Sources ──
    feeds: [
      ['NPR',          'https://feeds.npr.org/1001/rss.xml',                                                             'us'],
      ['NPR Politics', 'https://feeds.npr.org/1014/rss.xml',                                                             'politics'],
      ['NPR Health',   'https://feeds.npr.org/1128/rss.xml',                                                             'health'],
      ['ABC News',     'https://abcnews.go.com/abcnews/topstories',                                                      'us'],
      ['CBS News',     'https://www.cbsnews.com/latest/rss/main',                                                        'us'],
      ['Fox News',     'https://moxie.foxnews.com/google-publisher/latest.xml',                                          'us'],
      ['Politico',     'https://www.politico.com/rss/politicopicks.xml',                                                 'politics'],
      ['The Hill',     'https://thehill.com/rss/syndicator/19109/feed/',                                                 'politics'],
      ['CNBC Top',     'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114',           'business'],
      ['TechCrunch',   'https://techcrunch.com/feed/',                                                                   'tech'],
      ['Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index',                                                'tech'],
      ['Science Daily','https://www.sciencedaily.com/rss/all.xml',                                                       'science'],
      ['ESPN',         'https://www.espn.com/espn/rss/news',                                                             'sports'],
      ['Skift',        'https://skift.com/feed/',                                                                        'travel'],
    ],

    // ── Content filter ──
    filter: {
      type: 'exclude',
      keywords: ['nhs', 'uk government', 'downing street', 'labour party', 'conservative party',
        'premier league', 'bbc weather', 'uk housing', 'ofsted', 'channel crossing'],
      paywallDomains: ['nytimes.com', 'wsj.com', 'ft.com', 'bloomberg.com', 'economist.com', 'washingtonpost.com'],
    },

    // ── LLM prompts ──
    systemPrompt: `You are a professional news journalist writing for gab.ae, a US-centric news website. Write factual, clear articles aimed at an American audience. Never fabricate quotes or data — if you don't know, say so. null over fake data, always.`,

    userPromptTemplate: `Write a news article based on this source. Return ONLY valid JSON, no markdown fences.

SOURCE: {source}
CATEGORY HINT: {hintCategory}
TITLE: {title}
DESCRIPTION: {description}
ARTICLE TEXT:
{articleText}

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
- Do not invent facts. If the source text is thin, say "details are still emerging"`,

    llmCanSkip: false,
    defaultCategory: 'us',

    // ── Image hints per category ──
    imageHints: {
      us:            'American cityscape, USA landmark',
      world:         'global news, international scene',
      politics:      'government building, capitol, politics',
      business:      'business district, financial market, economy',
      tech:          'technology, digital innovation, modern devices',
      health:        'healthcare, medicine, hospital, wellness',
      science:       'scientific research, laboratory, discovery',
      sports:        'sports action, athletic competition, stadium',
      entertainment: 'entertainment venue, media, performance',
      travel:        'travel destination, landscape, journey',
      climate:       'nature, environment, climate landscape',
    },
    defaultImageHint: 'news scene',
    imagePromptSuffix: 'professional photojournalism, editorial photography, high quality, cinematic',

    // ── Internal cross-links ──
    internalLinks: {
      'mortgage':    '/mortgage-calculator',
      'inflation':   '/fire-movement',
      'invest':      '/capital-markets-wealth-guide-2026',
      'stock':       '/capital-markets-wealth-guide-2026',
      'crypto':      '/cryptocurrency-investing-guide',
      'bitcoin':     '/cryptocurrency-investing-guide',
      'real estate': '/real-estate-investing',
      'tariff':      '/capital-markets-wealth-guide-2026',
      'ai':          '/software-ai-infrastructure-guide-2026',
      'technology':  '/software-ai-infrastructure-guide-2026',
      'health':      '/human-optimization-health-guide-2026',
      'travel':      '/global-mobility-geo-arbitrage-guide-2026',
    },
    exploreMoreHeading: 'Explore More',
    exploreMoreIntro:   'Related topics on gab.ae',

    // ── Article UI ──
    takeawaysLabel: 'At a Glance',
    disclaimer: null,

    // ── Theme ──
    theme: {
      ink:         '#111111',
      inkMid:      '#444444',
      inkLight:    '#888888',
      paper:       '#faf8f4',
      paperMid:    '#f0ede6',
      paperDark:   '#e8e4db',
      accent:      '#c8102e',
      accentDark:  '#9a0d23',
      border:      '#d4cfc5',
      borderLight: '#e8e4db',
    },

    categoryColors: {
      us:            '#c8102e',
      world:         '#1a5c8a',
      politics:      '#3a2060',
      business:      '#1a5c30',
      health:        '#8a2020',
      entertainment: '#8a6020',
      travel:        '#1a4a6a',
      sports:        '#1a3a5c',
      science:       '#2a1e5e',
      climate:       '#1a5c30',
      tech:          '#8a4020',
    },

    // ── Nav ──
    navItems: [
      { href: '/news/category/us',            label: 'U.S.' },
      { href: '/news/category/world',         label: 'World' },
      { href: '/news/category/politics',      label: 'Politics' },
      { href: '/news/category/business',      label: 'Business' },
      { href: '/news/category/tech',          label: 'Tech' },
      { href: '/news/category/health',        label: 'Health' },
      { href: '/news/category/science',       label: 'Science' },
      { href: '/news/category/entertainment', label: 'Entertainment' },
      { href: '/news/category/sports',        label: 'Sports' },
      { href: '/news/category/climate',       label: 'Climate' },
      { href: '/news/category/travel',        label: 'Travel' },
    ],

    // ── Meta ──
    ga4Id: 'G-24QTGCDKMH',
    twitterCard: 'summary',
    ogSiteName: 'gab.ae',
    adultContent: false,
  },

  {
    // ── Identity ──
    id: 'thenookienook',
    dbSiteValue: 'thenookienook',
    name: 'The Nookie Nook',
    eyebrow: 'Sex Education & Sexual Health',
    tagline: 'Evidence-based sex ed for everyone',
    footerTagline: 'Evidence-based sex education for curious adults.',
    footerCredit: 'For adults 18+ · Part of the gab.ae network',

    // ── Routing ──
    pathPrefix: '/thenookienook',
    ownDomain: 'thenookienook.com',
    articlePath: '/article',
    categoryPath: '/category',

    // ── Schema.org ──
    schemaType: 'Article',
    publisherName: 'The Nookie Nook',
    publisherUrl: 'https://thenookienook.com',
    aboutThing: { '@type': 'Thing', name: 'Sex Education' },

    // ── Generation schedule ──
    cronModulo: 15,
    cronOffset: 0,

    // ── RSS Sources ──
    feeds: [
      ['Scarleteen',                'https://www.scarleteen.com/feed',                                   'education'],
      ['Advocates for Youth',       'https://www.advocatesforyouth.org/feed',                            'education'],
      ['Bedsider',                  'https://bedsider.org/features.rss',                                 'reproductive-health'],
      ['GLSEN',                     'https://www.glsen.org/rss.xml',                                     'lgbtq'],
      ['The Advocate',              'https://www.advocate.com/rss.xml',                                  'lgbtq'],
      ['PinkNews',                  'https://www.thepinknews.com/feed/',                                 'lgbtq'],
      ['Autostraddle',              'https://www.autostraddle.com/feed/',                                'lgbtq'],
      ['Out Magazine',              'https://www.out.com/rss.xml',                                       'lgbtq'],
      ['GLAAD',                     'https://www.glaad.org/blog/feed',                                   'lgbtq'],
      ['Rewire News',               'https://rewirenewsgroup.com/feed/',                                 'reproductive-health'],
      ['Psychology Today',          'https://www.psychologytoday.com/us/articles/rss',                   'relationships'],
      ['Healthline Sexual Health',  'https://www.healthline.com/rss/sexual-health',                      'sexual-health'],
      ["Women's Health",            'https://www.womenshealthmag.com/rss/all.xml/',                      'wellness'],
      ["Men's Health",              'https://www.menshealth.com/rss/all.xml/',                           'sexual-health'],
      ['Bustle',                    'https://www.bustle.com/feeds/health',                               'relationships'],
      ['NPR Health',                'https://feeds.npr.org/1128/rss.xml',                                'sexual-health'],
      ['Science Daily Health',      'https://www.sciencedaily.com/rss/health_medicine.xml',              'research'],
      ['Medical News Today',        'https://www.medicalnewstoday.com/rss',                              'sexual-health'],
      ['The Conversation Health',   'https://theconversation.com/us/health/articles.atom',               'research'],
    ],

    // ── Content filter ──
    filter: {
      type: 'include',
      keywords: [
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
      ],
      paywallDomains: [],
    },

    // ── LLM prompts ──
    systemPrompt: `You are a professional sex educator and health journalist writing for The Nookie Nook, an evidence-based sex education website. Write factual, inclusive, non-judgmental articles that help readers understand sexual health, relationships, and human sexuality. Be affirming of all identities and relationship structures. Never shame, never fabricate. Use accessible language — avoid jargon without explanation. null over fake data, always.

CRITICAL: Only write the article if the story has a DIRECT, EXPLICIT connection to one of: sexual health, human sexuality, intimate relationships, sex education, reproductive health (contraception/abortion/fertility/STIs), or LGBTQ+ health. General health stories (heart disease, cancer, obesity, mental illness, diet) are NOT relevant unless they directly and specifically discuss sexual function, sexual health outcomes, or intimate relationships. When in doubt — return SKIP. Return exactly: SKIP`,

    userPromptTemplate: `Write a sex education article based on this source. Return ONLY valid JSON (no markdown fences), or SKIP if not relevant.

SOURCE: {source}
CATEGORY HINT: {hintCategory}
TITLE: {title}
DESCRIPTION: {description}
ARTICLE TEXT:
{articleText}

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
- Normalize the topic — avoid sensationalism`,

    llmCanSkip: true,
    defaultCategory: 'sexual-health',

    // ── Image hints per category ──
    imageHints: {
      'sexual-health':      'health education, medical wellness, clean modern design',
      'relationships':      'couple connection, partnership, warm human interaction',
      'lgbtq':              'pride colors, diversity, inclusive community',
      'wellness':           'personal wellness, mindfulness, self-care, body positivity',
      'education':          'learning, books, knowledge, educational setting',
      'research':           'scientific research, laboratory, data visualization, study',
      'reproductive-health':'reproductive health, medical wellness, clinic setting',
      'culture':            'diverse people, society, community, culture',
      'mental-health':      'mental wellness, calm, therapy, supportive environment',
      'body-literacy':      'human anatomy illustration, body awareness, educational diagram',
    },
    defaultImageHint: 'health education illustration',
    imagePromptSuffix: 'professional editorial photography, clean modern, high quality',

    // ── Internal cross-links ──
    internalLinks: {
      'consent':        '/sexual-health-guide',
      'birth control':  '/contraception-guide',
      'sexual health':  '/sexual-health-guide',
      'relationships':  '/healthy-relationships-guide',
      'lgbtq':          '/lgbtq-health-guide',
      'sex education':  '/sex-education-resources',
      'reproductive':   '/reproductive-health-guide',
      'mental health':  '/mental-health-sexuality',
      'body image':     '/body-positivity-guide',
      'safer sex':      '/safer-sex-guide',
    },
    exploreMoreHeading: 'Learn More',
    exploreMoreIntro:   'Related topics on The Nookie Nook',

    // ── Article UI ──
    takeawaysLabel: 'Key Takeaways',
    disclaimer: '📚 Educational content for informational purposes. Consult a healthcare provider for medical advice.',

    // ── Theme ──
    theme: {
      ink:         '#1e0a2e',
      inkMid:      '#4a3568',
      inkLight:    '#9080b5',
      paper:       '#fdf8ff',
      paperMid:    '#f5eeff',
      paperDark:   '#ead9ff',
      accent:      '#c44ad9',
      accentDark:  '#9b35b5',
      border:      '#d5c8e8',
      borderLight: '#e8d9ff',
    },

    categoryColors: {
      'sexual-health':      '#c44ad9',
      'relationships':      '#e84393',
      'lgbtq':              '#9b35b5',
      'wellness':           '#7c3aed',
      'education':          '#6366f1',
      'research':           '#4f46e5',
      'reproductive-health':'#d946a8',
      'culture':            '#a855f7',
      'mental-health':      '#8b5cf6',
      'body-literacy':      '#c026d3',
    },

    // ── Nav ──
    navItems: [
      { href: '/category/sexual-health',       label: 'Sexual Health' },
      { href: '/category/relationships',        label: 'Relationships' },
      { href: '/category/lgbtq',               label: 'LGBTQ+' },
      { href: '/category/wellness',            label: 'Wellness' },
      { href: '/category/education',           label: 'Education' },
      { href: '/category/reproductive-health', label: 'Reproductive' },
      { href: '/category/research',            label: 'Research' },
      { href: '/category/culture',             label: 'Culture' },
      { href: '/category/mental-health',       label: 'Mental Health' },
      { href: '/category/body-literacy',       label: 'Body Literacy' },
    ],

    // ── Meta ──
    ga4Id: 'G-24QTGCDKMH',
    twitterCard: 'summary_large_image',
    ogSiteName: 'The Nookie Nook',
    adultContent: true,
  },

  {
    // ── Identity ──
    id: 'paris',
    dbSiteValue: 'paris',
    name: 'Paris Dispatch',
    eyebrow: 'News from the City of Light',
    tagline: 'Paris & France, every day',
    footerTagline: 'Independent news from Paris and across France.',
    footerCredit: 'Part of the gab.ae network',

    // ── Routing ──
    pathPrefix: '/paris',
    ownDomain: null,
    articlePath: '/article',
    categoryPath: '/category',

    // ── Schema.org ──
    schemaType: 'NewsArticle',
    publisherName: 'Paris Dispatch',
    publisherUrl: 'https://gab.ae/paris',
    aboutThing: { '@type': 'Place', name: 'Paris, France' },

    // ── Generation schedule ──
    cronModulo: 30,
    cronOffset: 0,

    // ── RSS Sources ──
    feeds: [
      ['France 24',         'https://www.france24.com/en/rss',                                    'politics'],
      ['RFI English',       'https://www.rfi.fr/en/rss',                                          'world'],
      ['The Local France',  'https://www.thelocal.fr/france/feed/',                               'society'],
      ['Euronews',          'https://feeds.feedburner.com/euronews/en/news/',                     'world'],
      ['Connexion France',  'https://www.connexionfrance.com/rss',                                'society'],
      ['Le Monde English',  'https://www.lemonde.fr/en/rss/une.xml',                              'politics'],
      ['French Tribune',    'https://www.frenchtribune.com/feed',                                 'culture'],
    ],

    // ── Content filter ──
    filter: {
      type: 'include',
      keywords: [
        'paris', 'france', 'french', 'macron', 'élysée', 'elysee',
        'seine', 'louvre', 'versailles', 'montmartre', 'bastille',
        'assemblée', 'assemblee', 'sénat', 'senat', 'matignon',
        'hollande', 'sarkozy', 'le pen', 'mélenchon', 'melenchon',
        'banlieue', 'île-de-france', 'ile-de-france',
        'french economy', 'french culture', 'french politics',
        'french election', 'french government', 'french police',
        'caf', 'psg', 'roland garros', 'tour de france',
        'côte d\'azur', 'provence', 'alsace', 'normandy', 'lyon',
        'marseille', 'bordeaux', 'toulouse', 'nice', 'strasbourg',
      ],
      paywallDomains: [],
    },

    // ── LLM prompts ──
    systemPrompt: `You are a professional journalist writing for Paris Dispatch, an English-language news site covering Paris and France. Write clear, engaging articles for an international English-speaking audience interested in French news, culture, politics, and daily life. Provide context that helps non-French readers understand the story. Never fabricate facts. null over fake data, always.`,

    userPromptTemplate: `Write a news article about Paris or France based on this source. Return ONLY valid JSON, no markdown fences.

SOURCE: {source}
CATEGORY HINT: {hintCategory}
TITLE: {title}
DESCRIPTION: {description}
ARTICLE TEXT:
{articleText}

Return this exact JSON structure:
{
  "title": "compelling headline, STRICTLY 40-58 characters",
  "description": "meta description, STRICTLY 70-155 characters",
  "category": "one of: politics, culture, society, economy, travel, arts, sports, food",
  "lede": "opening sentence that hooks the reader, 100-200 chars",
  "takeaways": ["one-sentence key point", "one-sentence key point", "one-sentence key point"],
  "key_stat": {"value": "a striking number or short phrase", "label": "brief context"},
  "pull_quote": "a compelling sentence from the article, 80-160 chars",
  "sections": [
    {"heading": "What Happened", "paragraphs": ["paragraph 1", "paragraph 2", "paragraph 3"]},
    {"heading": "Why It Matters", "paragraphs": ["paragraph 1", "paragraph 2"]},
    {"heading": "Context", "paragraphs": ["paragraph 1", "paragraph 2"]}
  ],
  "tags": ["category", "topic1", "topic2", "topic3"],
  "faqs": [
    {"q": "specific question about this story?", "a": "1-2 sentence answer"},
    {"q": "another relevant question?", "a": "1-2 sentence answer"},
    {"q": "third question?", "a": "1-2 sentence answer"}
  ]
}

Rules:
- Always explain French political/cultural context for international readers
- Each section MUST have at least 2 paragraphs, each 80-200 words
- FAQs must be specific to THIS story
- Total article should be 600-800 words
- Do not invent facts. If source text is thin, say "details are still emerging"`,

    llmCanSkip: true,
    defaultCategory: 'politics',

    // ── Image hints per category ──
    imageHints: {
      politics:  'Paris government building, Elysée Palace, French parliament',
      culture:   'Paris street scene, French culture, art gallery, café',
      society:   'Paris neighborhood, French people, urban life',
      economy:   'Paris business district, La Défense, French economy',
      travel:    'Paris landmark, Eiffel Tower, Seine river, tourism',
      arts:      'Paris museum, Louvre, French art, performance',
      sports:    'PSG, Roland Garros, Tour de France, French sports',
      food:      'French cuisine, Paris restaurant, boulangerie, wine',
    },
    defaultImageHint: 'Paris cityscape, France',
    imagePromptSuffix: 'professional editorial photography, cinematic, high quality',

    // ── Internal cross-links ──
    internalLinks: {},
    exploreMoreHeading: 'Explore More',
    exploreMoreIntro: 'More from Paris Dispatch',

    // ── Article UI ──
    takeawaysLabel: 'Key Points',
    disclaimer: null,

    // ── Theme: Parisian dark navy + gold ──
    theme: {
      ink:         '#0f1b2d',
      inkMid:      '#3d4f63',
      inkLight:    '#7a8fa6',
      paper:       '#f8f6f0',
      paperMid:    '#ede9df',
      paperDark:   '#ddd8ca',
      accent:      '#c9a84c',
      accentDark:  '#a07830',
      border:      '#cdc8b8',
      borderLight: '#e0ddd2',
    },

    categoryColors: {
      politics: '#1a3a6b',
      culture:  '#c9a84c',
      society:  '#5c7a3e',
      economy:  '#2d5a8e',
      travel:   '#8e4a2d',
      arts:     '#6b3a7a',
      sports:   '#2d6b5a',
      food:     '#8e6a2d',
    },

    // ── Nav ──
    navItems: [
      { href: '/category/politics', label: 'Politics' },
      { href: '/category/culture',  label: 'Culture' },
      { href: '/category/society',  label: 'Society' },
      { href: '/category/economy',  label: 'Economy' },
      { href: '/category/travel',   label: 'Travel' },
      { href: '/category/arts',     label: 'Arts' },
      { href: '/category/sports',   label: 'Sports' },
      { href: '/category/food',     label: 'Food' },
    ],

    // ── Meta ──
    ga4Id: 'G-24QTGCDKMH',
    twitterCard: 'summary_large_image',
    ogSiteName: 'Paris Dispatch',
    adultContent: false,
  },

  {
    // ── Identity ──
    id: 'toolstack',
    dbSiteValue: 'toolstack',
    name: 'ToolStack',
    eyebrow: 'AI · Streaming · Management · SaaS',
    tagline: 'The tools powering modern work and content',
    footerTagline: 'Daily news on AI tools, live streaming, management software, and SaaS.',
    footerCredit: 'Part of the gab.ae network',

    // ── Routing ──
    pathPrefix: '/toolstack',
    ownDomain: null,
    articlePath: '/article',
    categoryPath: '/category',

    // ── Schema.org ──
    schemaType: 'NewsArticle',
    publisherName: 'ToolStack',
    publisherUrl: 'https://gab.ae/toolstack',
    aboutThing: null,

    // ── Generation schedule ──
    cronModulo: 10,
    cronOffset: 5,

    // ── RSS Sources ──
    feeds: [
      ['TechCrunch',        'https://techcrunch.com/feed/',                                          'ai'],
      ['The Verge',         'https://www.theverge.com/rss/index.xml',                               'tools'],
      ['VentureBeat',       'https://venturebeat.com/feed/',                                         'ai'],
      ['Wired',             'https://www.wired.com/feed/rss',                                        'management'],
      ['AI News',           'https://artificialintelligence-news.com/feed/',                         'ai'],
      ['Product Hunt',      'https://www.producthunt.com/feed',                                      'tools'],
      ['Hacker News',       'https://news.ycombinator.com/rss',                                      'saas'],
      ['The Information',   'https://www.theinformation.com/feed',                                   'management'],
    ],

    // ── Content filter ──
    filter: {
      type: 'include',
      keywords: [
        'ai tool', 'ai tools', 'artificial intelligence', 'machine learning', 'chatgpt', 'openai',
        'anthropic', 'gemini', 'llm', 'copilot', 'automation',
        'live stream', 'livestream', 'streaming', 'twitch', 'youtube', 'obs', 'streamlabs', 'creator',
        'management software', 'project management', 'notion', 'asana', 'linear', 'jira', 'clickup',
        'productivity', 'workflow', 'saas', 'software tool', 'no-code', 'low-code', 'platform launch',
        'app launch', 'startup tool', 'developer tool', 'devtool', 'api tool', 'content tool',
      ],
      paywallDomains: ['theinformation.com'],
    },

    // ── LLM prompts ──
    systemPrompt: `You are a sharp tech journalist writing for ToolStack, a publication covering AI tools, live streaming technology, management software, and SaaS. Your readers are operators, content creators, developers, and managers who want to stay on top of the best tools and how they're evolving. Be direct, practical, and opinionated. Highlight what the tool does, who it's for, and why it matters now. Never fabricate facts. null over fake data, always.`,

    userPromptTemplate: `Write a news article for ToolStack based on this source. Return ONLY valid JSON, no markdown fences.

SOURCE: {source}
CATEGORY HINT: {hintCategory}
TITLE: {title}
DESCRIPTION: {description}
ARTICLE TEXT:
{articleText}

Return this exact JSON structure:
{
  "title": "punchy headline, STRICTLY 40-58 characters",
  "description": "meta description, STRICTLY 70-155 characters",
  "category": "one of: ai, streaming, management, saas, automation, productivity, reviews, tools",
  "lede": "one-sentence hook that explains why this matters right now, 100-200 chars",
  "takeaways": ["key point", "key point", "key point"],
  "key_stat": {"value": "striking number or short phrase", "label": "brief context"},
  "pull_quote": "compelling sentence from the article, 80-160 chars",
  "sections": [
    {"heading": "What It Does", "paragraphs": ["paragraph 1", "paragraph 2", "paragraph 3"]},
    {"heading": "Why It Matters", "paragraphs": ["paragraph 1", "paragraph 2"]},
    {"heading": "Who Should Use It", "paragraphs": ["paragraph 1", "paragraph 2"]}
  ],
  "tags": ["category", "topic1", "topic2", "topic3"],
  "faqs": [
    {"q": "specific question about this tool or story?", "a": "1-2 sentence answer"},
    {"q": "another practical question?", "a": "1-2 sentence answer"},
    {"q": "third question?", "a": "1-2 sentence answer"}
  ]
}

Rules:
- Be specific about features, pricing, and use cases when available
- Each section MUST have at least 2 paragraphs, each 80-200 words
- FAQs must be practical and specific to THIS story
- Total article 600-800 words
- Do not invent features or pricing. If details are thin, say "details are still emerging"`,

    llmCanSkip: true,
    defaultCategory: 'tools',

    // ── Image hints per category ──
    imageHints: {
      ai:           'AI interface, neural network visualization, futuristic software UI',
      streaming:    'live streaming setup, OBS dashboard, ring light, microphone, creator workspace',
      management:   'project management dashboard, team collaboration, kanban board',
      saas:         'SaaS dashboard, cloud software interface, analytics screen',
      automation:   'workflow automation, connected apps, Zapier-style diagram, pipelines',
      productivity: 'clean desk setup, productivity app, task list, focus workspace',
      reviews:      'software review, laptop screen, rating stars, product comparison',
      tools:        'developer tools, software interface, command line, app icon grid',
    },
    defaultImageHint: 'modern software tool, clean UI, tech workspace',
    imagePromptSuffix: 'professional product photography, clean minimal aesthetic, high quality',

    // ── Internal cross-links ──
    internalLinks: {},
    exploreMoreHeading: 'More Tools',
    exploreMoreIntro: 'Related coverage on ToolStack',

    // ── Article UI ──
    takeawaysLabel: 'Key Takeaways',
    disclaimer: null,

    // ── Theme: dark charcoal + indigo ──
    theme: {
      ink:         '#0f0f14',
      inkMid:      '#3d3d52',
      inkLight:    '#7a7a99',
      paper:       '#f5f5fa',
      paperMid:    '#e8e8f0',
      paperDark:   '#d8d8e8',
      accent:      '#6366f1',
      accentDark:  '#4f46e5',
      border:      '#c8c8da',
      borderLight: '#dcdcec',
    },

    categoryColors: {
      ai:           '#6366f1',
      streaming:    '#ec4899',
      management:   '#0ea5e9',
      saas:         '#8b5cf6',
      automation:   '#f59e0b',
      productivity: '#10b981',
      reviews:      '#ef4444',
      tools:        '#3b82f6',
    },

    // ── Nav ──
    navItems: [
      { href: '/category/ai',           label: 'AI' },
      { href: '/category/streaming',    label: 'Streaming' },
      { href: '/category/management',   label: 'Management' },
      { href: '/category/saas',         label: 'SaaS' },
      { href: '/category/automation',   label: 'Automation' },
      { href: '/category/productivity', label: 'Productivity' },
      { href: '/category/reviews',      label: 'Reviews' },
      { href: '/category/tools',        label: 'Tools' },
    ],

    // ── Meta ──
    ga4Id: 'G-24QTGCDKMH',
    twitterCard: 'summary_large_image',
    ogSiteName: 'ToolStack',
    adultContent: false,
  },
];

// ─── Lookup helpers ───────────────────────────────────────────────────────────

export function getSiteById(id) {
  return SITES.find(s => s.id === id);
}

export function getSiteByDomain(hostname) {
  const bare = hostname.replace(/^www\./, '');
  return SITES.find(s => s.ownDomain === bare || s.ownDomain === hostname);
}

export function getSiteByPath(path) {
  return SITES
    .filter(s => s.pathPrefix && path.startsWith(s.pathPrefix))
    .sort((a, b) => b.pathPrefix.length - a.pathPrefix.length)[0];
}
