#!/usr/bin/env python3
"""
News dispatch helper for gab.ae cron.
Fetches RSS, checks for duplicates, outputs candidate stories.

Usage:
  python3 scripts/news-dispatch.py            # Get 3 candidate stories
  python3 scripts/news-dispatch.py --count 5  # Get 5 candidates
  python3 scripts/news-dispatch.py --slugs    # List existing news slugs
  python3 scripts/news-dispatch.py --calcs    # List calculator slugs for cross-linking
"""
import urllib.request
import xml.etree.ElementTree as ET
import subprocess
import json
import sys
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# US/World-centric RSS feeds
FEEDS = [
    ('AP News', 'https://rsshub.app/apnews/topics/apf-topnews'),
    ('NPR', 'https://feeds.npr.org/1001/rss.xml'),
    ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
    ('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
    ('NYT World', 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'),
    ('NYT Business', 'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml'),
    ('CNBC Top', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114'),
]

def get_existing_articles():
    """Get all existing news slugs, source URLs, and titles from D1."""
    slugs = set()
    source_urls = set()
    title_words = set()
    try:
        r = subprocess.run(
            ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote',
             '--command', "SELECT slug, source_url, title FROM news;"],
            capture_output=True, text=True, cwd=BASE
        )
        import re
        # Parse slugs
        for m in re.finditer(r'"slug":\s*"([^"]+)"', r.stdout):
            slugs.add(m.group(1))
        # Parse source URLs
        for m in re.finditer(r'"source_url":\s*"([^"]*)"', r.stdout):
            if m.group(1):
                source_urls.add(m.group(1).split('?')[0])  # Strip query params
        # Parse titles — extract key words for fuzzy matching
        for m in re.finditer(r'"title":\s*"([^"]+)"', r.stdout):
            words = set(re.findall(r'[a-z]{4,}', m.group(1).lower()))
            title_words.update(words)
    except:
        pass
    return slugs, source_urls, title_words

def get_calculator_slugs(limit=50):
    """Get random calculator slugs for cross-linking."""
    try:
        r = subprocess.run(
            ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote',
             '--command', f"SELECT slug, title, category FROM pages WHERE status='live' ORDER BY RANDOM() LIMIT {limit};"],
            capture_output=True, text=True, cwd=BASE
        )
        import re
        results_match = re.search(r'"results":\s*\[', r.stdout)
        if results_match:
            start = results_match.start()
            chunk = r.stdout[start+11:]
            end = chunk.find(']')
            arr = json.loads(chunk[:end+1])
            return arr
        return []
    except:
        return []

def get_top_calculators():
    """Get key calculator slugs organized by category for cross-linking."""
    cats = {
        'finance': ['mortgage-calculator', 'inflation-calculator', 'investment-calculator', 
                     'compound-interest-calculator', 'debt-payoff-calculator', 'retirement-calculator',
                     'savings-calculator', 'budget-calculator', 'cost-of-living-calculator',
                     'loan-calculator', 'interest-rate-calculator', 'mortgage-affordability-calculator',
                     'mortgage-amortization-calculator', 'gas-calculator', 'electricity-cost-calculator',
                     'paycheck-calculator', 'roth-ira-calculator', 'stocks-calculator',
                     'annual-income-calculator', 'car-payment-calculator', 'property-tax-calculator',
                     'tip-calculator', 'dividend-calculator-stock'],
        'health': ['bmi-calculator', 'calorie-calculator', 'body-fat-calculator',
                   'hydration-calculator', 'calorie-deficit-weight-loss-calculator'],
        'math': ['percentage-calculator', 'statistics-calculator'],
    }
    return cats

def fetch_rss():
    """Fetch all RSS feeds and return candidate stories."""
    stories = []
    for source_name, url in FEEDS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
            data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(data)
            for item in root.findall('.//item')[:10]:
                title = item.findtext('title', '').strip()
                link = item.findtext('link', '').strip()
                desc = item.findtext('description', '').strip()[:300]
                if title and link:
                    stories.append({
                        'source': source_name,
                        'title': title,
                        'link': link,
                        'description': desc,
                    })
        except Exception as e:
            sys.stderr.write(f"Feed error {source_name}: {e}\n")
    return stories

def slugify(title):
    """Simple slugify for dedup matching."""
    import re
    s = title.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s).strip('-')
    return s[:80]

def main():
    args = sys.argv[1:]
    
    if '--slugs' in args:
        slugs, _, _ = get_existing_articles()
        for s in sorted(slugs):
            print(s)
        return
    
    if '--calcs' in args:
        calcs = get_top_calculators()
        print(json.dumps(calcs, indent=2))
        return
    
    count = 3
    if '--count' in args:
        idx = args.index('--count')
        if idx + 1 < len(args):
            count = int(args[idx + 1])
    
    # Fetch stories
    stories = fetch_rss()
    existing_slugs, existing_urls, existing_words = get_existing_articles()
    
    # Filter: skip UK domestic, skip duplicates
    uk_domestic_keywords = ['nhs', 'uk government', 'downing street', 'british government', 
                            'england football', 'premier league', 'labour party', 'conservative party',
                            'bbc weather', 'uk housing', 'england doctors', 'octopus energy']
    
    candidates = []
    seen_titles = set()
    for s in stories:
        title_lower = s['title'].lower()
        
        # Skip UK domestic
        if any(kw in title_lower for kw in uk_domestic_keywords):
            continue
        
        # Skip if source URL already covered
        link_clean = s['link'].split('?')[0]
        if link_clean in existing_urls:
            continue
        
        # Skip if title has too much overlap with existing articles (>50% key words match)
        import re as _re
        story_words = set(_re.findall(r'[a-z]{4,}', title_lower))
        if story_words and existing_words:
            overlap = len(story_words & existing_words) / len(story_words)
            if overlap > 0.5:
                continue
        
        # Skip if slug looks like existing
        slug = slugify(s['title'])
        if slug in existing_slugs:
            continue
        
        # Skip duplicate titles within this batch
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)
        
        candidates.append(s)
    
    # Prioritize: world/finance first
    finance_keywords = ['stock', 'market', 'economy', 'gdp', 'inflation', 'fed', 'rate', 
                        'trade', 'tariff', 'oil', 'bank', 'invest', 'dollar', 'debt', 'tax']
    world_keywords = ['war', 'conflict', 'summit', 'sanctions', 'nato', 'un ', 'nuclear',
                      'china', 'russia', 'iran', 'trump', 'election', 'missile', 'treaty']
    
    def priority(s):
        t = s['title'].lower()
        score = 0
        if any(kw in t for kw in finance_keywords):
            score += 2
        if any(kw in t for kw in world_keywords):
            score += 2
        return score
    
    candidates.sort(key=priority, reverse=True)
    
    # Output top candidates
    output = {
        'candidates': candidates[:count],
        'existing_count': len(existing_slugs),
        'total_fetched': len(stories),
        'calculators': get_top_calculators(),
    }
    
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
