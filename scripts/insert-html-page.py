#!/usr/bin/env python3
"""
Insert or update a full HTML page in the gab.ae D1 database.

Usage:
  python3 insert-html-page.py <html-file> --slug <slug> --title <title> --description <desc> --category <cat>
  python3 insert-html-page.py <json-file>   # JSON with {slug, title, description, category, html_file} or {slug, title, description, category, html}

The HTML should be the page BODY content only (everything inside <main>).
The Worker wraps it in the shared layout (nav, footer, GA4, Tailwind).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

WRANGLER_DIR = str(Path(__file__).parent.parent)

def run_d1(sql, params=None):
    """Execute SQL on D1 remote."""
    cmd = ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote', '--command', sql, '--json']
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=WRANGLER_DIR)
    if result.returncode != 0:
        print(f"D1 error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)

def upsert_page(slug, title, description, category, html, schema_json=None):
    """Insert or update a page with full HTML."""
    # Escape single quotes for SQL
    def esc(s):
        return s.replace("'", "''") if s else ''
    
    schema_str = json.dumps(schema_json) if schema_json else ''
    
    # Check if page exists
    check = run_d1(f"SELECT slug FROM pages WHERE slug = '{esc(slug)}'")
    exists = len(check[0]['results']) > 0 if isinstance(check, list) else False
    
    if exists:
        sql = f"""UPDATE pages SET 
            title = '{esc(title)}',
            description = '{esc(description)}',
            category = '{esc(category)}',
            html = '{esc(html)}',
            schema_json = '{esc(schema_str)}',
            engine = 'html',
            status = 'live',
            updated_at = datetime('now')
            WHERE slug = '{esc(slug)}'"""
        run_d1(sql)
        print(f"✅ Updated: gab.ae/{slug}")
    else:
        sql = f"""INSERT INTO pages (slug, engine, category, title, description, html, config, content, faqs, schema_json, status, published_at, updated_at, created_at)
            VALUES (
                '{esc(slug)}', 'html', '{esc(category)}', '{esc(title)}', '{esc(description)}',
                '{esc(html)}', '{{}}', '[]', '[]', '{esc(schema_str)}',
                'live', datetime('now'), datetime('now'), datetime('now')
            )"""
        run_d1(sql)
        print(f"✅ Inserted: gab.ae/{slug}")

def main():
    parser = argparse.ArgumentParser(description='Insert full HTML page into gab.ae D1')
    parser.add_argument('file', help='HTML file or JSON manifest')
    parser.add_argument('--slug', help='Page slug')
    parser.add_argument('--title', help='Page title')
    parser.add_argument('--description', help='Meta description')
    parser.add_argument('--category', default='finance', help='Category')
    args = parser.parse_args()
    
    filepath = Path(args.file)
    if not filepath.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    
    if filepath.suffix == '.json':
        # JSON manifest (single page or array)
        data = json.loads(filepath.read_text())
        pages = data if isinstance(data, list) else [data]
        
        for page in pages:
            html = page.get('html', '')
            if not html and page.get('html_file'):
                html_path = Path(page['html_file'])
                if not html_path.is_absolute():
                    html_path = filepath.parent / html_path
                html = html_path.read_text()
            
            upsert_page(
                slug=page['slug'],
                title=page['title'],
                description=page['description'],
                category=page.get('category', 'finance'),
                html=html,
                schema_json=page.get('schema'),
            )
    else:
        # Direct HTML file
        if not all([args.slug, args.title, args.description]):
            print("For HTML files, --slug, --title, and --description are required", file=sys.stderr)
            sys.exit(1)
        
        html = filepath.read_text()
        
        # If it's a full HTML document, extract just the body content
        if '<html' in html.lower() and '<body' in html.lower():
            import re
            # Extract between <body...> and </body>
            match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
            if match:
                body = match.group(1)
                # Also extract any <style> from <head>
                styles = re.findall(r'<style[^>]*>.*?</style>', html, re.DOTALL | re.IGNORECASE)
                # And any <script> that aren't analytics/tailwind
                scripts = re.findall(r'<script(?! (?:async )?src="https://(?:cdn\.tailwindcss|www\.googletagmanager))[^>]*>.*?</script>', html, re.DOTALL | re.IGNORECASE)
                html = '\n'.join(styles) + '\n' + body + '\n' + '\n'.join(scripts)
                # Clean up: remove nav and footer if they look like the shared layout ones
                html = re.sub(r'<nav[^>]*class="[^"]*no-print[^"]*"[^>]*>.*?</nav>', '', html, flags=re.DOTALL)
                html = re.sub(r'<footer[^>]*class="[^"]*no-print[^"]*"[^>]*>.*?</footer>', '', html, flags=re.DOTALL)
                # Remove the outer <main> wrapper if present
                html = re.sub(r'^\s*<main[^>]*>\s*', '', html)
                html = re.sub(r'\s*</main>\s*$', '', html)
        
        upsert_page(
            slug=args.slug,
            title=args.title,
            description=args.description,
            category=args.category,
            html=html.strip(),
        )

if __name__ == '__main__':
    main()
