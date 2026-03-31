#!/usr/bin/env node
/**
 * Seed keyword queue from Ahrefs JSON into D1
 * Usage: node scripts/seed-keyword-queue.js
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const INPUT = path.join(process.env.HOME, 'Desktop/photonbuilder/data/seo/ahrefs/build-queue-ahrefs.json');
const data = JSON.parse(fs.readFileSync(INPUT, 'utf8'));

console.log(`📦 Seeding ${data.length} keywords into D1...`);

const BATCH = 40;
let total = 0;

for (let i = 0; i < data.length; i += BATCH) {
  const batch = data.slice(i, i + BATCH);
  const values = batch.map(k => {
    const esc = s => (s || '').replace(/'/g, "''");
    return `('${esc(k.slug)}', '${esc(k.primary_keyword)}', '${esc(JSON.stringify(k.secondary_keywords || []))}', ${k.total_volume || 0}, ${k.avg_kd || 0}, ${k.max_cpc || 0}, ${k.score || 0}, '${esc(k.page_type || 'educational')}', '${esc(k.site || '')}')`;
  }).join(', ');

  const sql = `INSERT OR IGNORE INTO keyword_queue (slug, primary_keyword, secondary_keywords, total_volume, avg_kd, max_cpc, score, page_type, target_site) VALUES ${values};`;

  // Write to temp file to avoid shell escaping issues
  const tmpFile = path.join(__dirname, '.tmp-seed.sql');
  fs.writeFileSync(tmpFile, sql);

  try {
    execSync(`npx wrangler d1 execute gab-ae-prod --remote --file="${tmpFile}"`, {
      cwd: path.join(__dirname, '..'),
      stdio: 'pipe',
    });
    total += batch.length;
    console.log(`  ✅ Batch ${Math.floor(i / BATCH) + 1}: ${total}/${data.length}`);
  } catch (e) {
    console.error(`  ❌ Batch ${Math.floor(i / BATCH) + 1} failed: ${e.message.slice(0, 200)}`);
  }

  // Clean up
  try { fs.unlinkSync(tmpFile); } catch (_) {}
}

console.log(`\n✅ Done! Seeded ${total} keywords.`);
