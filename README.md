# gab.ae

Cloudflare Worker + D1 site serving news articles, tools/calculators, educational content, and pillar guides at [gab.ae](https://gab.ae).

## Architecture

```
gab.ae (Cloudflare Worker)
├── D1 Database (gab-ae-prod) — all content stored here
│   ├── pages     — tools, guides, seed pages (engine: calculator, llm-gemini, llm-sonnet, seed, html)
│   ├── news      — structured news articles (JSON sections)
│   ├── keywords  — 100K+ Ahrefs keywords for seed page generation
│   ├── changelog — public changelog at /updates
│   └── view_counts / view_events — analytics
├── Worker (src/worker.js) — routing, rendering, cron scheduler
└── LLM Pipelines — auto-generate and upgrade content via OpenRouter
```

## Content Pipelines (Cron-driven)

All pipelines run on Cloudflare's `scheduled()` handler (cron: `* * * * *` = every minute).

| Pipeline | File | Frequency | What it does |
|----------|------|-----------|-------------|
| **Seed Pages** | `src/llm-seed-pages.js` | Every minute | Picks best keyword from D1 → LLM writes full HTML page → inserts into `pages` table |
| **News** | `src/llm-news.js` | Every minute | Fetches RSS feeds → picks best story → LLM writes structured article → inserts into `news` table |
| **Rework** | `src/llm-rework.js` | Daily at 4 AM UTC | Finds highest-traffic LLM pages → rewrites with better model (Gemini Pro) → updates in-place |
| **Upgrade Trigger** | `src/upgrade-trigger.js` | Hourly | Finds template pages with 2+ sessions → queues for Sonnet rewrite |

## Key Files

```
src/
├── worker.js              — Main Worker: routing, rendering, homepage, /resources, cron scheduler
├── llm-client.js          — OpenRouter API client with model fallback chain
├── llm-seed-pages.js      — Seed page generator (keyword → LLM → HTML → D1)
├── llm-news.js            — News article generator (RSS → LLM → structured JSON → D1)
├── llm-rework.js          — Page upgrader (finds traffic pages, rewrites with better model)
├── upgrade-trigger.js     — Detects pages with traffic, queues for upgrade
├── engines/
│   ├── calculator.js      — Calculator page renderer (config-driven: inputs → formula → outputs)
│   ├── news.js            — News article renderer (structured JSON → HTML)
│   └── changelog.js       — Changelog/updates renderer
└── templates/
    └── layout.js          — Shared HTML shell (nav, footer, dark theme, meta tags)

scripts/
├── insert-news.py         — CLI: insert news articles from JSON into D1
├── insert-html-page.py    — CLI: insert raw HTML pages into D1
├── insert-configs.py      — CLI: insert calculator configs from JSON into D1
├── import-keywords.py     — CLI: bulk import Ahrefs keyword CSVs into D1
├── seed-keyword-queue.js  — CLI: seed keyword queue from Ahrefs JSON
├── seed-keyword-queue.sh  — Shell wrapper for above
├── dedup-pages.py         — CLI: find and remove duplicate pages in D1
├── batch-rework.py        — CLI: batch rework pages via OpenRouter
├── seo-tracker.py         — CLI: SEO tracking across all domains
└── seo-tracker-schema.sql — Schema for SEO tracker tables

schema.sql                 — D1 database schema (pages, news, keywords, etc.)
wrangler.toml              — Cloudflare Worker config
backups/                   — Daily D1 database backups (auto-pruned to 7 days)
```

## Environment Variables (Cloudflare Worker secrets)

- `OPENROUTER_API_KEY` — OpenRouter API key for LLM calls
- `ANTHROPIC_API_KEY` — Fallback Anthropic key

## Design System

- Background: `#0a0a0f` (layout), Cards: `#12121a`, Borders: `#1e1e2e`
- Accent: `#818cf8` (indigo)
- Text: `#e2e8f0` (main), `#94a3b8` (muted), `#64748b` (dimmed)
- CSS classes: `.seed-page`, `.seed-section`, `.seed-stat`, `.seed-takeaway`, `.seed-pros`, `.seed-cons`

## Local Development

```bash
npx wrangler dev          # Local dev server
npx wrangler deploy       # Deploy to production
npx wrangler d1 execute gab-ae-prod --remote --command "SQL"  # Query D1
```

## Content Stats

- **100K+** keywords in queue
- **30K+** eligible for seed page generation (KD ≤ 20, volume ≥ 50)
- Pages auto-generated at ~1/minute via cron
