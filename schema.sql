-- gab.ae D1 Schema (complete, as of April 2026)
-- Database: gab-ae-prod (4e23e386-b430-4ffc-bf84-246a4e7bcdd1)

-- ═══════════════════════════════════════════════════════════════
-- CORE CONTENT TABLES
-- These store all the content served by the Worker.
-- ═══════════════════════════════════════════════════════════════

-- Pages: tools, calculators, guides, seed pages — everything except news
-- engine: 'calculator' uses renderCalculator(), everything else renders raw html column
-- quality: 'template' (initial), 'llm' (LLM-generated), 'llm-sonnet' (upgraded by rework)
-- engine values: 'calculator', 'llm-haiku', 'llm-gemini', 'llm-gemini-pro', 'llm-sonnet', 'seed', 'html'
CREATE TABLE IF NOT EXISTS pages (
  slug TEXT PRIMARY KEY,
  engine TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  config TEXT,                   -- JSON: calculator config {inputs, outputs, formula}
  content TEXT,                  -- JSON: content sections [{heading, body}] (legacy, mostly unused)
  faqs TEXT,                     -- JSON: [{q, a}] (legacy, most pages have FAQs in html)
  schema_json TEXT,              -- JSON-LD structured data
  status TEXT DEFAULT 'draft',   -- draft, live, archived
  published_at TEXT,
  updated_at TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  html TEXT,                     -- Full HTML body content (rendered inside layout shell)
  quality TEXT,                  -- template, llm, llm-sonnet, premium
  keyword TEXT,                  -- Target keyword this page was built for
  keyword_volume INTEGER,        -- Monthly search volume
  keyword_kd INTEGER,            -- Keyword difficulty (0-100)
  page_type TEXT,                -- calculator, interactive_tool, listicle, comparison, tutorial, etc.
  target_site TEXT,              -- Which site this keyword was originally from
  upgrade_queued_at TEXT         -- When this page was queued for Sonnet upgrade
);

CREATE INDEX IF NOT EXISTS idx_pages_engine ON pages(engine);
CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);
CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category);
CREATE INDEX IF NOT EXISTS idx_pages_keyword ON pages(keyword);
CREATE INDEX IF NOT EXISTS idx_pages_quality ON pages(quality);

-- News: structured articles generated from RSS feeds by llm-news.js
-- sections stored as JSON: [{heading: "...", paragraphs: ["...", "..."]}]
-- Rendered by engines/news.js
CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  category TEXT,                 -- business, world, politics, tech, health, science, travel, sports, entertainment
  image TEXT,                    -- Image URL (from RSS media tags)
  image_alt TEXT,
  lede TEXT,                     -- Opening sentence
  sections TEXT,                 -- JSON: [{heading, paragraphs}]
  tags TEXT,                     -- JSON: ["tag1", "tag2"]
  sources TEXT,                  -- JSON: [{name, url}]
  faqs TEXT,                     -- JSON: [{q, a}]
  published_at DATETIME DEFAULT (datetime('now')),
  updated_at DATETIME,
  status TEXT DEFAULT 'draft',   -- draft, live, archived
  source_url TEXT                -- Original RSS article URL (for dedup)
);

-- ═══════════════════════════════════════════════════════════════
-- KEYWORD TABLES
-- The keyword queue drives the seed page pipeline (llm-seed-pages.js).
-- 100K+ keywords imported from Ahrefs CSVs.
-- ═══════════════════════════════════════════════════════════════

-- Keywords: individual keywords from Ahrefs exports
-- status: 'new' (available), 'live' (page built), 'skip' (slug exists), 'blacklist' (excluded)
-- The seed page pipeline picks: status='new', kd<=20, volume>=50, ordered by (cpc*volume)/(kd+1)
CREATE TABLE IF NOT EXISTS keywords (
  keyword TEXT PRIMARY KEY,
  volume INTEGER,                -- Monthly search volume
  kd INTEGER,                    -- Keyword difficulty (0-100)
  cpc REAL,                      -- Cost per click ($)
  traffic_potential INTEGER,
  parent_topic TEXT,
  engine TEXT,                   -- Override for page type detection (optional)
  category TEXT,
  target_slug TEXT,              -- Pre-assigned slug (optional)
  status TEXT DEFAULT 'new',     -- new, live, skip, blacklist, done
  skip_reason TEXT,
  priority_score REAL,
  page_slug TEXT,                -- Slug of the page built for this keyword
  source TEXT,                   -- Which Ahrefs export this came from
  classified_by TEXT,
  classified_at TEXT,
  built_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Keyword queue: clustered/batched keywords (used by content-factory-v2, mostly legacy)
CREATE TABLE IF NOT EXISTS keyword_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT,
  primary_keyword TEXT,
  secondary_keywords TEXT,       -- JSON array
  total_volume INTEGER,
  avg_kd INTEGER,
  max_cpc REAL,
  score REAL,
  page_type TEXT,
  target_site TEXT,
  status TEXT DEFAULT 'queued',
  published_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════
-- ANALYTICS TABLES
-- Track page views and SEO performance.
-- ═══════════════════════════════════════════════════════════════

-- View events: rolling 24h window of page views (pruned hourly)
-- Used to calculate "popular today" on /resources
CREATE TABLE IF NOT EXISTS view_events (
  slug TEXT NOT NULL,
  hour_bucket TEXT NOT NULL,     -- ISO hour: "2026-04-05T14"
  views INTEGER DEFAULT 1,
  PRIMARY KEY (slug, hour_bucket)
);

-- View counts: cumulative totals per page
-- Used by llm-rework.js to find pages worth upgrading
CREATE TABLE IF NOT EXISTS view_counts (
  slug TEXT PRIMARY KEY,
  views_24h INTEGER DEFAULT 0,
  views_total INTEGER DEFAULT 0,
  last_reset TEXT
);

-- Page metrics: GSC + GA4 data imported by seo-tracker.py
CREATE TABLE IF NOT EXISTS page_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT,
  path TEXT,
  date TEXT,
  gsc_impressions INTEGER,
  gsc_clicks INTEGER,
  gsc_ctr REAL,
  gsc_position REAL,
  ga_sessions INTEGER,
  ga_users INTEGER,
  ga_pageviews INTEGER,
  ga_bounce_rate REAL,
  ga_avg_duration REAL
);

-- Keyword rankings: GSC query-level data imported by seo-tracker.py
CREATE TABLE IF NOT EXISTS keyword_rankings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT,
  path TEXT,
  query TEXT,
  date TEXT,
  impressions INTEGER,
  clicks INTEGER,
  ctr REAL,
  position REAL
);

-- ═══════════════════════════════════════════════════════════════
-- TRACKING & OPERATIONS TABLES
-- ═══════════════════════════════════════════════════════════════

-- Tracked pages: SEO tracking across all domains in the network
CREATE TABLE IF NOT EXISTS tracked_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT,
  path TEXT,
  title TEXT,
  description TEXT,
  category TEXT,
  apex_slug TEXT,                -- Which apex pillar guide this page belongs to
  cluster TEXT,                  -- Content cluster grouping
  first_seen TEXT,
  last_updated TEXT,
  last_crawled TEXT,
  indexed BOOLEAN DEFAULT 0,
  status TEXT DEFAULT 'active'   -- active, removed
);

-- SEO issues: detected problems (missing meta, thin content, etc.)
CREATE TABLE IF NOT EXISTS seo_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT,
  path TEXT,
  issue_type TEXT,               -- missing_meta, thin_content, broken_link, etc.
  severity TEXT,                 -- low, medium, high, critical
  details TEXT,
  detected_at TEXT,
  resolved_at TEXT,
  status TEXT DEFAULT 'open'     -- open, resolved, ignored
);

-- Changelog: public changelog rendered at /updates
CREATE TABLE IF NOT EXISTS changelog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT,
  action TEXT,                   -- upgrade, create, rework, fix, expand
  target_type TEXT,
  target_slug TEXT,
  target_domain TEXT,
  summary TEXT,
  details TEXT,
  cluster_news_slug TEXT,
  cluster_news_domain TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  status TEXT DEFAULT 'live'
);

-- 404 log: tracks not-found URLs for content gap analysis
CREATE TABLE IF NOT EXISTS not_found_log (
  path TEXT PRIMARY KEY,
  count INTEGER DEFAULT 1,
  last_seen TEXT
);

-- Engines: page engine registry (legacy, mostly unused — ENGINES const in worker.js)
CREATE TABLE IF NOT EXISTS engines (
  id TEXT PRIMARY KEY,
  name TEXT,
  description TEXT,
  template TEXT,
  default_config TEXT,
  page_count INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT
);
