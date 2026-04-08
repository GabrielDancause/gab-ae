# Portfolio Sites Migration Plan

Migration of all 18 external properties from the gab.ae footer into the main repo and D1 database.

## Sites to Migrate

### Standalone Domains (8)
| Domain | Category | Type |
|--------|----------|------|
| westmountfundamentals.com | Equity Research | Content + Tools |
| firemaths.info | Money Calculators | Tools |
| siliconbased.dev | Dev Tools | Tools |
| thenookienook.com | Sexual Health | Content + Tools |
| migratingmammals.com | Travel & Nomad | Content + Tools |
| ijustwantto.live | Home & DIY | Content + Tools |
| 28grams.vip | Kitchen Science | Content + Tools |
| leeroyjenkins.quest | Gaming | Content + Tools |

### Photonbuilder Subdomains (8)
| Subdomain | Category | Type |
|-----------|----------|------|
| bodycount.photonbuilder.com | Health Calculators | Tools |
| fixitwithducttape.photonbuilder.com | AI & SaaS Reviews | Content |
| sendnerds.photonbuilder.com | Education | Content + Tools |
| getthebag.photonbuilder.com | Career | Content + Tools |
| justonemoment.photonbuilder.com | Timers | Tools |
| papyruspeople.photonbuilder.com | Text Tools | Tools |
| eeniemeenie.photonbuilder.com | Random Generators | Tools |
| pleasestartplease.photonbuilder.com | Automotive | Content + Tools |

### Personal Brand Sites (2)
| Domain | Category | Type |
|--------|----------|------|
| aliimperiale.com | Personal Brand | Content |
| aubergedenosaieux.com | Hospitality | Content |

## Architecture

### What already exists in gab.ae
- D1 `pages` table with slug, category, html, engine support
- `calculator.js` engine for config-driven tools (inputs -> formula -> outputs)
- `layout.js` shared shell with nav, footer, meta tags, dark theme
- Category routing via `/category/{cat}`
- LLM content generation pipelines
- SEO tracking via `tracked_pages`, `page_metrics`, `keyword_rankings`

### What needs to change

**Schema:** Add a `domain` or `source` column to `pages` so tools retain their origin identity. This enables serving the same content on both gab.ae/slug and the original domain.

**Routing:** Add custom domain support in `wrangler.toml` or Cloudflare dashboard so each domain resolves to the same Worker. The Worker checks the `Host` header and serves the appropriate subset of pages.

**Redirects:** Build a redirect map per domain (old Astro URL -> new gab.ae slug) and serve 301s to preserve SEO equity.

## Migration Strategy

### Phase 1: Audit (per site)
- Inventory every page and tool on the site
- Classify each as: content-only, config-driven calculator, or custom interactive tool
- Note any external API dependencies, auth flows, or third-party integrations

### Phase 2: Content Pages
- Export HTML/markdown from Astro
- Bulk insert into D1 `pages` table with appropriate category and source domain
- Verify rendering in `layout.js` shell
- Smallest effort per page — mostly automated

### Phase 3: Config-Driven Tools
- Tools that fit the "inputs -> formula -> outputs" pattern
- Convert each to a calculator engine JSON config
- No custom code needed per tool — just a config row in D1
- Medium effort — requires understanding each tool's logic to write the config

### Phase 4: Custom Interactive Tools
- Tools with unique UI, multi-step flows, charts, or complex state
- Each needs manual porting from Astro components to vanilla JS
- Largest effort per tool — could range from hours to days each
- Consider keeping some as iframes or external embeds if porting cost is too high

### Phase 5: DNS & Redirects
- Point each domain to the Cloudflare Worker via custom domains
- Deploy 301 redirect map for all old URLs
- Verify with GSC that indexing shifts cleanly
- Monitor `page_metrics` for traffic continuity

## Effort Estimate

| Phase | Effort | Notes |
|-------|--------|-------|
| Audit | 1-2 days per site | Need to inventory every tool on every site |
| Content pages | ~1 day per site | Mostly bulk import |
| Config-driven tools | ~1-2 hours per tool | Write JSON config, test |
| Custom interactive tools | ~2-8 hours per tool | Full rewrite to vanilla JS |
| DNS & redirects | ~1 hour per domain | Cloudflare config + redirect map |

The total depends heavily on how many custom interactive tools exist across all 18 sites. A full audit of each site is the critical first step.

## Recommended Order

Start with the simplest sites (fewest custom tools) to build momentum and validate the migration pattern, then tackle the tool-heavy sites:

1. Content-heavy sites first (aliimperiale.com, aubergedenosaieux.com, fixitwithducttape)
2. Calculator-heavy sites next (firemaths.info, bodycount) — leverage the calculator engine
3. Custom tool sites last (siliconbased.dev, justonemoment, papyruspeople, eeniemeenie)

## Risks

- **SEO disruption:** Even with 301s, domain migrations cause temporary ranking drops. Migrate one site at a time and monitor before proceeding.
- **Tool fidelity:** Some Astro components may use features (SSR, client-side hydration, component islands) that don't map cleanly to vanilla JS. May need to expand the engine system.
- **Scope creep:** 18 sites is a lot. Set a clear cutoff for which sites are worth migrating vs. keeping as-is with just a link in the footer.
- **Westmount Fundamentals:** 661+ equity research reports and prospect scoring — likely the most complex single migration. May warrant its own dedicated plan.
