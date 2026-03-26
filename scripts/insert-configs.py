#!/usr/bin/env python3
"""Insert calculator configs from JSON file into D1."""
import json, subprocess, sys, os

GAB_AE = os.path.expanduser("~/Desktop/gab-ae")

def sq(s):
    if s is None: return 'NULL'
    return "'" + str(s).replace("'", "''") + "'"

def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(GAB_AE, "configs-batch-1.json")
    
    with open(config_file) as f:
        configs = json.load(f)
    
    print(f"Inserting {len(configs)} pages into D1...")
    
    statements = []
    kw_updates = []
    
    for c in configs:
        slug = c['slug']
        config_json = json.dumps(c['config'])
        content_json = json.dumps(c['content'])
        faqs_json = json.dumps(c['faqs'])
        schema_json = json.dumps(c['schema'])
        
        stmt = f"""INSERT OR REPLACE INTO pages (slug, engine, category, title, description, config, content, faqs, schema_json, status, published_at, updated_at)
VALUES ({sq(slug)}, 'calculator', {sq(c['category'])}, {sq(c['title'])}, {sq(c['description'])}, {sq(config_json)}, {sq(content_json)}, {sq(faqs_json)}, {sq(schema_json)}, 'live', datetime('now'), datetime('now'));"""
        statements.append(stmt)
        
        # Also update keyword status
        kw_updates.append(f"UPDATE keywords SET status='live', page_slug={sq(slug)}, built_at=datetime('now') WHERE target_slug={sq(slug)};")
    
    # Write SQL
    sql_file = os.path.join(GAB_AE, "insert-batch.sql")
    with open(sql_file, 'w') as f:
        f.write("\n".join(statements + kw_updates))
    
    # Execute
    result = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "gab-ae-prod", "--remote", f"--file={sql_file}"],
        capture_output=True, text=True, cwd=GAB_AE
    )
    
    if result.returncode == 0:
        print("✅ All pages inserted!")
        for c in configs:
            print(f"  → gab.ae/{c['slug']}")
    else:
        print(f"❌ Error: {result.stderr}")
        print(result.stdout[-500:] if result.stdout else "")

if __name__ == '__main__':
    main()
