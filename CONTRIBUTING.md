# How to Make Changes to gab.ae

## Decision Tree: Where Do I Edit?

```
Want to change...
├── The nav bar, footer, or page chrome? → src/templates/layout.js
├── How calculators render?              → src/engines/calculator.js
├── How news articles render?            → src/engines/news.js
├── How the changelog renders?           → src/engines/changelog.js
├── The homepage?                        → src/worker.js → homepage()
├── The /resources page?                 → src/worker.js → resourcesPage()
├── The /news index?                     → src/worker.js → newsIndex()
├── URL routing?                         → src/worker.js → fetch() handler
├── Cron schedule/frequency?             → src/worker.js → scheduled() handler
├── How news articles are generated?     → src/llm-news.js
├── How pages get upgraded?              → src/llm-rework.js
├── Which LLM models are used?           → src/llm-client.js (FALLBACK_CHAIN)
├── The D1 database schema?              → schema.sql (then run migration)
└── Cron frequency?                      → wrangler.toml [triggers] crons
```

## Adding a New Page Type

1. Add a renderer in `src/engines/my-engine.js`
2. Import it in `src/worker.js` and add to the `ENGINES` object
3. Pages with `engine='my-engine'` in D1 will now use your renderer

## Adding a New Route

1. Add a `if (path === '/my-route')` block in the `fetch()` handler in `src/worker.js`
2. Create a handler function (follow the pattern of `homepage()`, `newsIndex()`, etc.)
3. Return a `new Response(html, { headers: ... })`

## Adding a New Cron Pipeline

1. Create the pipeline in `src/my-pipeline.js` (export an async function)
2. Import in `src/worker.js`
3. Call it in the `scheduled()` handler with appropriate frequency gate
4. Example frequency gates:
   - Every 5 minutes (every tick): no gate (just call it)
   - Every hour: `if (nowMin < 5) { ... }`
   - Daily at 4 AM UTC: `if (nowHour === 4 && nowMin < 5) { ... }`

## CSS Design System

DO NOT invent new CSS classes. Use these exact classes (defined in llm-seed-pages.js):

```css
.seed-page          → Page wrapper (max-width: 780px, centered)
.seed-section       → Content card (bg: #12121a, border: #1e1e2e, rounded)
.seed-section h2    → Section heading (color: #818cf8 indigo accent)
.seed-section h3    → Sub-heading (color: #e2e8f0 white)
.seed-section p     → Paragraph (color: #94a3b8 muted gray)
.seed-stat          → Stat card with .stat-value (big indigo number) + .stat-label
.seed-takeaway      → Highlighted insight box (gradient bg, indigo left border)
.seed-pros          → Green-tinted box for positives (border: #1a3a1a)
.seed-cons          → Red-tinted box for negatives (border: #3a1a1a)
.seed-meta          → Date/meta text (color: #64748b dimmed)
.seed-explore       → Footer links section
```

Color palette:
- Background: `#0a0a0f` (page bg, handled by layout)
- Card bg: `#12121a`
- Card border: `#1e1e2e` or `rgba(255,255,255,0.08)`
- Accent: `#818cf8` (indigo)
- Text main: `#e2e8f0`
- Text muted: `#94a3b8`
- Text dimmed: `#64748b`
- Success: `#4ade80`
- Danger: `#f87171`

## Inserting Content into D1

```bash
# Insert a calculator page
python3 scripts/insert-configs.py my-calculators.json

# Insert a news article
python3 scripts/insert-news.py my-articles.json

# Insert a raw HTML page
python3 scripts/insert-html-page.py page.html --slug "my-page" --title "My Page | gab.ae" --description "..." --category guide

# Import keywords from Ahrefs CSV
python3 scripts/import-keywords.py keywords.csv
```

## Deploying

```bash
cd ~/Desktop/gab-ae
npx wrangler deploy        # Deploy Worker to production
git add -A && git commit -m "description" && git push
```

Always deploy BEFORE pushing — if the deploy fails, you can fix it before the commit.

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `no such column` | D1 schema mismatch | Check schema.sql, run ALTER TABLE |
| `OPENROUTER_API_KEY undefined` | Missing secret | `npx wrangler secret put OPENROUTER_API_KEY` |
| `429 Too Many Requests` | OpenRouter rate limit | Wait. The fallback chain in llm-client.js tries other models. |
| `D1_ERROR: database is locked` | Too many concurrent writes | Reduce cron frequency or batch writes |
| Deploy succeeds but site 500s | Runtime error in Worker | Check `npx wrangler tail` for logs |

## DO NOT

- Use `:root` CSS variables (conflicts with layout)
- Use `<html>`, `<head>`, `<body>` tags in page content (layout.js adds these)
- Use HTML tables in seed pages (use lists or card sections)
- Add JavaScript to non-interactive pages (only `interactive_tool` intent gets JS)
- Hardcode dates — use `new Date()` for dynamic dates
- Invent statistics or data — `null` over fake data, always
