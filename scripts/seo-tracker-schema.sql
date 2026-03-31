-- SEO Tracker Schema for gab-ae-prod D1 database
-- Tracks all pages across ~18 PhotonBuilder network domains

-- Every page across all domains
CREATE TABLE IF NOT EXISTS tracked_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL,
  path TEXT NOT NULL,
  title TEXT,
  description TEXT,
  category TEXT,
  apex_slug TEXT,
  cluster TEXT,
  first_seen TEXT NOT NULL,
  last_updated TEXT,
  last_crawled TEXT,
  indexed BOOLEAN DEFAULT NULL,
  status TEXT DEFAULT 'active',
  UNIQUE(domain, path)
);

-- Daily metrics snapshots (one row per page per date)
CREATE TABLE IF NOT EXISTS page_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL,
  path TEXT NOT NULL,
  date TEXT NOT NULL,
  gsc_impressions INTEGER DEFAULT 0,
  gsc_clicks INTEGER DEFAULT 0,
  gsc_ctr REAL DEFAULT 0,
  gsc_position REAL DEFAULT 0,
  ga_sessions INTEGER DEFAULT 0,
  ga_users INTEGER DEFAULT 0,
  ga_pageviews INTEGER DEFAULT 0,
  ga_bounce_rate REAL DEFAULT 0,
  ga_avg_duration REAL DEFAULT 0,
  UNIQUE(domain, path, date)
);

-- Keyword-level data from GSC
CREATE TABLE IF NOT EXISTS keyword_rankings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL,
  path TEXT NOT NULL,
  query TEXT NOT NULL,
  date TEXT NOT NULL,
  impressions INTEGER DEFAULT 0,
  clicks INTEGER DEFAULT 0,
  ctr REAL DEFAULT 0,
  position REAL DEFAULT 0,
  UNIQUE(domain, path, query, date)
);

-- Auto-detected issues
CREATE TABLE IF NOT EXISTS seo_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL,
  path TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  details TEXT,
  detected_at TEXT NOT NULL,
  resolved_at TEXT,
  status TEXT DEFAULT 'open'
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tracked_pages_domain ON tracked_pages(domain);
CREATE INDEX IF NOT EXISTS idx_page_metrics_domain_date ON page_metrics(domain, date);
CREATE INDEX IF NOT EXISTS idx_page_metrics_date ON page_metrics(date);
CREATE INDEX IF NOT EXISTS idx_keyword_rankings_query ON keyword_rankings(query, date);
CREATE INDEX IF NOT EXISTS idx_keyword_rankings_domain_date ON keyword_rankings(domain, date);
CREATE INDEX IF NOT EXISTS idx_seo_issues_status ON seo_issues(status, severity);
CREATE INDEX IF NOT EXISTS idx_seo_issues_domain ON seo_issues(domain);
