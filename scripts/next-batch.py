#!/usr/bin/env python3
"""Pull next N unbuilt calculator keywords by volume from D1, excluding already-built slugs."""
import subprocess, json, sys, os

GAB_AE = os.path.expanduser("~/Desktop/gab-ae")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10

result = subprocess.run(
    ["npx", "wrangler", "d1", "execute", "gab-ae-prod", "--remote", "--json",
     "--command", f"""SELECT k.keyword, k.target_slug, k.volume, k.category 
FROM keywords k 
LEFT JOIN pages p ON p.slug = k.target_slug 
WHERE k.engine='calculator' AND k.status='new' AND p.slug IS NULL 
ORDER BY k.volume DESC LIMIT {N}"""],
    capture_output=True, text=True, cwd=GAB_AE
)

data = json.loads(result.stdout)
rows = []
for item in data:
    if 'results' in item:
        rows = item['results']
        break

if not rows:
    print("NO_KEYWORDS")
    sys.exit(0)

for r in rows:
    print(f"- **{r['keyword']}** (slug: {r['target_slug']}, category: {r['category']}, vol: {r['volume']:,})")

print(f"\n---\nTotal: {len(rows)} keywords ready to build")
