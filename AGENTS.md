# AGENTS.md — Guide for AI Agents Contributing to gab.ae

This document captures architecture, operational gotchas, and rules learned from real incidents. Read it before touching anything.

---

## 1. Architecture Overview

**gab.ae** is a Cloudflare Worker that serves a content site. Everything runs in a single Worker script (`src/worker.js`) with no external servers.

### Key files

| File | Purpose |
|---|---|
| `src/worker.js` | Main Worker: HTTP router + `scheduled()` cron handler |
| `src/llm-client.js` | OpenRouter API client with 3-model fallback chain |
| `src/llm-seed-pages.js` | Automated page generator — pulls keywords from D1, calls LLM, writes HTML to `pages` table |
| `src/llm-news.js` | Automated news generator — fetches RSS feeds, summarises with LLM, writes to `news` table |
| `src/llm-rework.js` | Upgrades existing low-quality pages using Gemini 2.5 Pro |
| `wrangler.toml` | Cloudflare Worker config: cron triggers, D1 binding, observability |

### Data flow

```
Cron tick (every minute)
  └─ scheduled() in worker.js
       ├─ llmSeedPages(env)   → picks keyword from D1 → calls callLLM() → inserts into pages table
       └─ llmNews(env)        → fetches RSS → calls callLLM() → inserts into news table
                                (only on minutes where UTCMinutes % 5 === 0)

HTTP request
  └─ fetch() router in worker.js
       ├─ GET /               → homepage (reads pages + news from D1)
       ├─ GET /resources      → dashboard (reads pages, news, view_events from D1)
       ├─ GET /{slug}         → serves a generated page from D1
       ├─ GET /news/{slug}    → serves a news article from D1
       └─ POST /api/generate  → on-demand page gen from homepage form → calls callLLM()
```

### Infrastructure

- **Runtime:** Cloudflare Workers (edge, no Node.js)
- **Database:** Cloudflare D1 (SQLite) — binding `env.DB`, database `gab-ae-prod`
- **LLM provider:** OpenRouter (`env.OPENROUTER_API_KEY`)
- **Auth for deploy:** OAuth session stored in `~/Library/Preferences/.wrangler/` via `wrangler login`

---

## 2. The Cron System

`wrangler.toml` registers **one cron**: `* * * * *` (every minute).

`scheduled()` in `worker.js` handles all timed work with in-process frequency gates:

```js
async scheduled(event, env, ctx) {
  // Seed pages — every tick (every minute)
  try { await llmSeedPages(env); } catch (e) { console.log(...) }

  // News — every 5th minute
  if (new Date().getUTCMinutes() % 5 === 0) {
    try { await llmNews(env); } catch (e) { console.log(...) }
  }

  // Rework — once daily at 4 AM UTC
  if (nowHour === 4 && nowMin < 5) { ... }
}
```

**Why this pattern instead of multiple crons:** Cloudflare's minimum cron resolution is 1 minute. Running one cron every minute and gating internally gives finer control and avoids Cloudflare-level scheduling complexity.

---

## 3. LLM Pipeline

### `llm-client.js` — fallback chain

```js
const FALLBACK_CHAIN = [
  'google/gemini-2.0-flash-001',     // primary
  'deepseek/deepseek-chat-v3-0324',  // backup
  'openai/gpt-4.1-mini',             // last resort
];
```

`callLLM()` tries each model in order. Logs `🤖 Trying model: <name>` before each attempt. On API error logs `⚠️ <model> failed: <error>`. Throws if all three fail — callers must handle this.

### `llm-rework.js` — direct model call

Uses `google/gemini-2.5-pro` directly (not the fallback chain). This is intentional — rework is a higher-quality pass on top-traffic pages and needs the stronger model.

### `/api/generate` — homepage "ask us anything" form

`worker.js:309`:
```js
html = await callLLM(apiKey, onDemandPrompt, { maxTokens: 8192 });
```

No `model` override — goes through the fallback chain, so it uses whatever is first in `FALLBACK_CHAIN`. **The primary model must stay `google/gemini-2.0-flash-001`.** Do not change this without explicit instruction.

---

## 4. Known Failure Modes

### Silent failures in `scheduled()`

Every pipeline call is wrapped in a `try/catch` that only logs — Cloudflare sees the Worker exit cleanly regardless. This means a fully broken pipeline looks identical to a healthy one in the Cloudflare dashboard triggers view. **Always check Worker Logs, not just trigger status.**

### Keywords stuck retrying on LLM error

Before the fix in commit `f14e8f6`, a failed LLM call in `llmSeedPages` would `return` without updating the keyword — leaving it `status='new'` and causing it to be retried every tick. The fix marks it `status='error'`:

```js
} catch (e) {
  console.log(`❌ Seed LLM error [${kw.keyword}]: ${e.message}`);
  await env.DB.prepare("UPDATE keywords SET status = 'error' WHERE keyword = ?").bind(kw.keyword).run();
  return;
}
```

**After any pipeline fix that clears a systematic LLM error, reset error keywords:**
```bash
npx wrangler d1 execute gab-ae-prod --remote --command "UPDATE keywords SET status='new' WHERE status='error'"
```

### Free OpenRouter models returning 404

PR #50 switched the fallback chain to `:free` tier models. All three returned `404 "No endpoints found"` from OpenRouter — the model IDs were invalid or the endpoints had been removed. This silently broke the pipeline for ~5 hours.

**Rule: never use `:free` tier OpenRouter model IDs without first confirming they are live in the OpenRouter model list.** The 404 manifests as `⚠️ <model> failed: {"message":"No endpoints found...","code":404}` in Worker Logs.

### Worktree deploys mis-registering the cron

Deploying from a git worktree (e.g. `/Users/gab/Desktop/gab-ae/.claude/worktrees/*/`) has shown the cron registering as `* * * * *` when `wrangler.toml` says `*/5 * * * *`, and vice versa. Always deploy from the main repo.

---

## 5. Deploy Instructions

**Always deploy from the main repo:**
```bash
cd /Users/gab/Desktop/gab-ae
npx wrangler deploy
```

**Never deploy from a worktree path** like `.claude/worktrees/interesting-agnesi/`. Worktree deploys have caused the cron trigger to register with the wrong schedule in Cloudflare.

**Always verify the `schedule:` line in deploy output** matches what is in `wrangler.toml`.

**After deploying, confirm the pipeline resumed** by running `wrangler tail gab-ae --format pretty` for ~90 seconds and checking for `📝 Generating:` log lines.

---

## 6. Observability

### Persistent logs

`wrangler.toml` has `[observability] enabled = true` — logs from all invocations (cron and HTTP) are stored and visible in the Cloudflare dashboard under **Workers & Pages → gab-ae → Logs**.

### Live log streaming

```bash
cd /Users/gab/Desktop/gab-ae
npx wrangler tail gab-ae --format pretty
```

Key log patterns to watch for:

| Log | Meaning |
|---|---|
| `📝 Generating: "<keyword>"` | Seed page pipeline fired successfully |
| `🤖 Trying model: <name>` | LLM call starting |
| `⚠️ <model> failed: ...` | That model failed, next in chain will be tried |
| `❌ Seed LLM error [<keyword>]` | All models failed, keyword marked error |
| `❌ News LLM/parse error` | News pipeline LLM or JSON parse failed |
| `✅ Published: <slug>` | Page or article successfully written to D1 |
| `"* * * * *" @ ...` | Cron invocation (confirms cron is firing) |

### Diagnosing a stalled pipeline

If pages stopped generating, check in order:
1. Is the cron firing? Look for `"* * * * *" @` in tail output.
2. Is the LLM failing? Look for `⚠️ ... failed` or `❌ Seed LLM error`.
3. Are keywords available? `SELECT COUNT(*) FROM keywords WHERE status='new'`
4. Are there stuck errors? `SELECT COUNT(*) FROM keywords WHERE status='error'`

---

## 7. D1 Database

Database name: `gab-ae-prod`
Database ID: `4e23e386-b430-4ffc-bf84-246a4e7bcdd1`
Always use `--remote` flag for production queries.

### Key tables

| Table | What it stores |
|---|---|
| `pages` | LLM-generated content pages. Key columns: `slug`, `title`, `html`, `engine`, `status`, `quality`, `keyword`, `category`, `page_type`, `created_at` |
| `keywords` | Keyword queue. Key columns: `keyword`, `status` (`new`/`live`/`skip`/`error`), `volume`, `kd`, `cpc`, `target_slug` |
| `news` | Generated news articles. Key columns: `slug`, `title`, `category`, `sections` (JSON), `published_at` |
| `tracked_pages` | SEO tracking — maps pages to apex hub slugs. Used by `/resources` page count badges |
| `view_events` | Rolling hourly view counts. Used for "Most Popular" tab on `/resources` |

### Useful debug queries

```bash
# How many live pages have been generated?
npx wrangler d1 execute gab-ae-prod --remote --command \
  "SELECT COUNT(*) as total, MAX(created_at) as latest FROM pages WHERE engine='llm-gemini' AND status='live'"

# Are keywords erroring?
npx wrangler d1 execute gab-ae-prod --remote --command \
  "SELECT COUNT(*) FROM keywords WHERE status='error'"

# How many keywords remain in queue?
npx wrangler d1 execute gab-ae-prod --remote --command \
  "SELECT COUNT(*) FROM keywords WHERE status='new'"

# Reset errored keywords after a pipeline fix
npx wrangler d1 execute gab-ae-prod --remote --command \
  "UPDATE keywords SET status='new' WHERE status='error'"

# Latest news articles
npx wrangler d1 execute gab-ae-prod --remote --command \
  "SELECT title, published_at FROM news ORDER BY published_at DESC LIMIT 5"
```

Note: the `news` table uses `published_at`, not `created_at`.

---

## 8. The /resources Page

`resourcesPage()` in `worker.js` runs 4–5 D1 queries and renders three tabs:

- **Recently Published** — `SELECT ... FROM pages WHERE status='live' AND engine IN ('llm-haiku','llm-gemini','llm-gemini-pro','llm-sonnet','seed') ORDER BY created_at DESC LIMIT 10`
- **Most Popular (24h)** — joins `view_events` with `pages` and `news` on rolling 24h window
- **Recently Updated** — `SELECT ... FROM pages WHERE quality='llm-sonnet' ORDER BY updated_at DESC LIMIT 10` (reworked pages only)

### Why new pages might not appear on /resources

1. **Wrong `engine` value** — the filter includes `'llm-gemini'` which is what `llmSeedPages` writes. If the engine column value ever changes, update the filter.
2. **Pipeline not running** — check `MAX(created_at)` against current time. If it's hours old, the pipeline is broken.
3. **Pages have wrong `status`** — the query filters `status='live'`. A failed insert or a bug that sets a different status will hide pages.

---

## 9. Rules

1. **Never change the homepage form model.** `/api/generate` calls `callLLM()` with no model override, so it uses `FALLBACK_CHAIN[0]`. That must stay `google/gemini-2.0-flash-001`. Changing it changes the user-facing "ask us anything" experience.

2. **Never switch to unvalidated free OpenRouter model IDs.** The `:free` suffix models are unreliable — endpoints appear and disappear without notice, returning 404. Validate any new model ID in the OpenRouter dashboard before putting it in the fallback chain.

3. **Always deploy from `/Users/gab/Desktop/gab-ae` (main repo), not a worktree.** Worktree deploys have caused cron schedule misregistration.

4. **Always reset error keywords after fixing a pipeline error.** After any fix that resolves a systematic LLM failure, run the `UPDATE keywords SET status='new' WHERE status='error'` query. Otherwise up to N keywords stay permanently poisoned.

5. **Verify the pipeline resumed after every deploy.** Run `wrangler tail` for ~90 seconds post-deploy and confirm `📝 Generating:` lines appear within the next cron tick.

6. **Check Worker Logs, not just trigger status.** The `scheduled()` handler catches all errors internally — Cloudflare always reports the trigger as succeeded. A green trigger status tells you nothing about whether content was actually generated.

## Link Scanner (`src/link-scanner.js`)

Added 2026-04-07. Scans all internal hrefs in `pages` HTML, validates against known slugs in D1.

- **Auto-fix:** broken links with a fuzzy slug match (≥2 shared words) get their href rewritten in the stored HTML
- **Remove:** links with no match get the `<a>` tag stripped, anchor text kept
- **Tables:** `broken_links` (source_slug, broken_href, suggested_slug, status, detected_at, fixed_at), `link_scan_log` (scanned_at, total_links, broken_found, auto_fixed, unfixable)
- **Trigger:** runs hourly via `nowMin === 0` in `scheduled()`, or manually via `curl https://gab.ae/health?run=1`
- **Time budget:** 25s hard limit to avoid Cloudflare worker kill — partial runs are safe, next run continues
- **Dashboard:** `GET /health` — shows 404 count, fixed today, removed, scan history

## Agent Workflow Warning: Worktree Deadlocks

**Never run more than one code task at a time on this repo.**

Each code session spawns a git worktree under `.claude/worktrees/`. Multiple concurrent worktrees fight over `.git/index.lock` and freeze all Bash operations indefinitely.

If sessions deadlock:
```bash
rm -f ~/Desktop/gab-ae/.git/index.lock
cd ~/Desktop/gab-ae && git worktree prune
```

**Always route follow-up work to the existing active session via send_message, not by spawning new sessions.**
