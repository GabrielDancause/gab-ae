/**
 * Upgrade Trigger — Detects template pages with 2+ sessions
 * and queues them for Sonnet rewrite.
 * Processes max 5 pages per call.
 */

/**
 * Check template pages for traffic and queue upgrades.
 * @param {Object} env - Worker env with DB binding
 * @returns {Object} Result summary
 */
export async function upgradeTrigger(env) {
  // 1. Get template pages that haven't been queued for upgrade yet
  const { results: candidates } = await env.DB.prepare(
    `SELECT slug, keyword, keyword_volume, target_site, page_type
     FROM pages
     WHERE quality = 'template'
       AND upgrade_queued_at IS NULL
     ORDER BY keyword_volume DESC
     LIMIT 5`
  ).all();

  if (!candidates || candidates.length === 0) {
    return { checked: 0, queued: [] };
  }

  const queued = [];

  for (const page of candidates) {
    // 2. Check page_metrics for traffic
    let sessions = 0;
    try {
      const metric = await env.DB.prepare(
        `SELECT ga_sessions FROM page_metrics
         WHERE domain = 'gab.ae' AND path = ?`
      ).bind('/' + page.slug).first();

      sessions = metric?.ga_sessions || 0;
    } catch (e) {
      // page_metrics might not have this page yet — skip
      continue;
    }

    // 3. If 2+ sessions, queue for upgrade
    if (sessions >= 2) {
      await env.DB.prepare(
        "UPDATE pages SET upgrade_queued_at = datetime('now') WHERE slug = ?"
      ).bind(page.slug).run();

      queued.push({
        slug: page.slug,
        keyword: page.keyword,
        sessions,
        pageType: page.page_type,
      });

      console.log(`⬆️ Upgrade queued: ${page.slug} (${sessions} sessions)`);
    }
  }

  console.log(`🔍 Upgrade check: ${candidates.length} checked, ${queued.length} queued`);

  return {
    checked: candidates.length,
    queued,
  };
}
