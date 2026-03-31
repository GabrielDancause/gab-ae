#!/usr/bin/env python3
"""
Insert news articles into gab-ae-prod D1.
Usage: python3 scripts/insert-news.py articles.json
"""
import json, sys, subprocess, os

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/insert-news.py <articles.json>")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)

    with open(path) as f:
        articles = json.load(f)

    if isinstance(articles, dict):
        articles = [articles]

    inserted = 0
    skipped = 0

    for a in articles:
        slug = a.get('slug', '')
        if not slug:
            print(f"  SKIP: no slug")
            skipped += 1
            continue

        sql = """INSERT OR REPLACE INTO news (slug, title, description, category, image, image_alt, lede, sections, tags, sources, faqs, published_at, updated_at, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 'live')"""

        values = [
            slug,
            a.get('title', ''),
            a.get('description', ''),
            a.get('category', 'world'),
            a.get('image', ''),
            a.get('imageAlt', ''),
            a.get('lede', ''),
            json.dumps(a.get('sections', [])),
            json.dumps(a.get('tags', [])),
            json.dumps(a.get('sources', [])),
            json.dumps(a.get('faqs', [])),
        ]

        # Build the command with proper escaping
        escaped_vals = []
        for v in values:
            escaped_vals.append(str(v).replace("'", "''"))

        # Extract source URL for dedup
        sources_list = a.get('sources', [])
        source_url = sources_list[0].get('url', '') if sources_list else ''
        escaped_source_url = source_url.replace("'", "''")

        full_sql = f"""INSERT OR REPLACE INTO news (slug, title, description, category, image, image_alt, lede, sections, tags, sources, faqs, source_url, published_at, updated_at, status)
VALUES ('{escaped_vals[0]}', '{escaped_vals[1]}', '{escaped_vals[2]}', '{escaped_vals[3]}', '{escaped_vals[4]}', '{escaped_vals[5]}', '{escaped_vals[6]}', '{escaped_vals[7]}', '{escaped_vals[8]}', '{escaped_vals[9]}', '{escaped_vals[10]}', '{escaped_source_url}', datetime('now'), datetime('now'), 'live')"""

        result = subprocess.run(
            ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote', '--command', full_sql],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        if 'error' in result.stderr.lower() or 'error' in result.stdout.lower():
            print(f"  ERROR {slug}: {result.stderr[-200:]}")
            skipped += 1
        else:
            print(f"  ✅ {slug}")
            inserted += 1

    print(f"\nDone: {inserted} inserted, {skipped} skipped")

if __name__ == '__main__':
    main()
