-- gab.ae D1 Schema

-- Pages: every page on the site is one row
CREATE TABLE IF NOT EXISTS pages (
  slug TEXT PRIMARY KEY,
  engine TEXT NOT NULL,          -- calculator, converter, timer, chart, knowledge, news
  category TEXT NOT NULL,        -- finance, education, health, tech, science, lifestyle, sports
  title TEXT NOT NULL,
  description TEXT,
  config TEXT,                   -- JSON: engine-specific configuration
  content TEXT,                  -- JSON: content sections [{heading, body}]
  faqs TEXT,                     -- JSON: [{q, a}]
  schema_json TEXT,              -- JSON-LD structured data
  status TEXT DEFAULT 'draft',   -- draft, live, archived
  published_at TEXT,
  updated_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pages_engine ON pages(engine);
CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category);
CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);

-- Keywords: the brain — what to build, what to skip
CREATE TABLE IF NOT EXISTS keywords (
  keyword TEXT PRIMARY KEY,
  volume INTEGER DEFAULT 0,
  kd INTEGER DEFAULT 0,
  cpc REAL DEFAULT 0,
  traffic_potential INTEGER DEFAULT 0,
  parent_topic TEXT,
  
  -- Classification
  engine TEXT,                    -- which engine would build this
  category TEXT,                  -- finance, education, health...
  target_slug TEXT,               -- what the URL slug would be
  
  -- Judgement
  status TEXT DEFAULT 'new',      -- new, queued, building, live, skip, blacklist, review
  skip_reason TEXT,               -- adult, branded, no_intent, too_competitive, duplicate
  priority_score REAL,            -- volume / (kd + 1) — auto-calculated
  
  -- Tracking
  page_slug TEXT,                 -- FK to pages.slug once built
  source TEXT,                    -- ahrefs_us_2026-03, dataforseo, manual
  classified_by TEXT,             -- auto, human
  classified_at TEXT,
  built_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kw_status ON keywords(status);
CREATE INDEX IF NOT EXISTS idx_kw_priority ON keywords(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_kw_engine ON keywords(engine);
CREATE INDEX IF NOT EXISTS idx_kw_category ON keywords(category);

-- Engines: template registry
CREATE TABLE IF NOT EXISTS engines (
  id TEXT PRIMARY KEY,            -- calculator, converter, timer, chart...
  name TEXT NOT NULL,
  description TEXT,
  template TEXT NOT NULL,         -- the HTML/JS template with {{placeholders}}
  default_config TEXT,            -- JSON: default values
  page_count INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT
);
