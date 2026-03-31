#!/bin/bash
# Seed keyword queue from Ahrefs JSON into D1
# Usage: bash scripts/seed-keyword-queue.sh

cd "$(dirname "$0")/.."
INPUT="$HOME/Desktop/photonbuilder/data/seo/ahrefs/build-queue-ahrefs.json"

if [ ! -f "$INPUT" ]; then
  echo "❌ File not found: $INPUT"
  exit 1
fi

# Generate SQL insert statements in batches
node -e "
const fs = require('fs');
const data = JSON.parse(fs.readFileSync('$INPUT', 'utf8'));

// Build batch SQL (50 per batch to avoid command length limits)
const BATCH = 50;
for (let i = 0; i < data.length; i += BATCH) {
  const batch = data.slice(i, i + BATCH);
  const values = batch.map(k => {
    const slug = k.slug.replace(/'/g, \"''\");
    const pk = k.primary_keyword.replace(/'/g, \"''\");
    const sk = JSON.stringify(k.secondary_keywords || []).replace(/'/g, \"''\");
    const pt = (k.page_type || 'educational').replace(/'/g, \"''\");
    const ts = (k.site || '').replace(/'/g, \"''\");
    return \`('\${slug}', '\${pk}', '\${sk}', \${k.total_volume || 0}, \${k.avg_kd || 0}, \${k.max_cpc || 0}, \${k.score || 0}, '\${pt}', '\${ts}')\`;
  }).join(',\\n');
  const sql = \`INSERT OR IGNORE INTO keyword_queue (slug, primary_keyword, secondary_keywords, total_volume, avg_kd, max_cpc, score, page_type, target_site) VALUES \${values};\`;
  console.log(sql);
  console.log('---BATCH_SEPARATOR---');
}
" | while IFS= read -r line; do
  if [ "$line" = "---BATCH_SEPARATOR---" ]; then
    if [ -n "$SQL" ]; then
      npx wrangler d1 execute gab-ae-prod --remote --command "$SQL" 2>&1 | grep -o '"rows_written": [0-9]*'
    fi
    SQL=""
  else
    SQL="${SQL}${line}"
  fi
done

echo "✅ Keyword queue seeded"
