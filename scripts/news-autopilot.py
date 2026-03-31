#!/usr/bin/env python3
"""
Autonomous news pipeline for gab.ae — NO LLM tokens needed.
Fetches RSS, extracts article content, writes structured news, inserts into D1.

Usage:
  python3 scripts/news-autopilot.py              # Publish 3 articles
  python3 scripts/news-autopilot.py --count 5    # Publish 5 articles
  python3 scripts/news-autopilot.py --dry-run    # Preview without publishing
"""

import urllib.request
import xml.etree.ElementTree as ET
import subprocess
import json
import sys
import os
import re
import hashlib
import html
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── RSS Feeds (source, url, target_category) ───
FEEDS = [
    # General / World
    ('NPR', 'https://feeds.npr.org/1001/rss.xml', None),
    ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml', None),
    ('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml', 'business'),
    ('NYT World', 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml', None),
    ('NYT Business', 'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml', 'business'),
    ('CNBC Top', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'business'),
    ('MarketWatch', 'https://feeds.marketwatch.com/marketwatch/topstories/', 'business'),
    ('Yahoo Finance', 'https://finance.yahoo.com/news/rssindex', 'business'),
    ('Bloomberg', 'https://feeds.bloomberg.com/markets/news.rss', 'business'),
    # Tech / AI
    ('TechCrunch', 'https://techcrunch.com/feed/', 'tech'),
    ('Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index', 'tech'),
    ('The Verge', 'https://www.theverge.com/rss/index.xml', 'tech'),
    ('Hacker News', 'https://hnrss.org/frontpage?count=20', 'tech'),
    ('Wired', 'https://www.wired.com/feed/rss', 'tech'),
    # Science / Climate
    ('Science Daily', 'https://www.sciencedaily.com/rss/all.xml', 'science'),
    # Travel
    ('Skift', 'https://skift.com/feed/', 'travel'),
    # Gaming
    ('IGN', 'https://feeds.feedburner.com/ign/all', 'entertainment'),
    ('Kotaku', 'https://kotaku.com/rss', 'entertainment'),
    # Health
    ('NPR Health', 'https://feeds.npr.org/1128/rss.xml', 'health'),
    ('BBC Health', 'https://feeds.bbci.co.uk/news/health/rss.xml', 'health'),
    # Sports
    ('ESPN', 'https://www.espn.com/espn/rss/news', 'sports'),
    # Entertainment
    ('BBC Entertainment', 'https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml', 'entertainment'),
]

# ─── Category keywords ───
CATEGORY_KEYWORDS = {
    'business':  ['stock', 'market', 'economy', 'gdp', 'inflation', 'fed', 'rate', 'trade',
                   'tariff', 'bank', 'invest', 'dollar', 'debt', 'earning', 'revenue', 'profit',
                   'ipo', 'merger', 'acquisition', 'startup', 'crypto', 'bitcoin', 'oil', 'gold'],
    'politics':  ['trump', 'biden', 'congress', 'senate', 'election', 'vote', 'democrat',
                   'republican', 'white house', 'legislation', 'bill', 'supreme court', 'doj',
                   'executive order', 'impeach', 'government shutdown', 'policy'],
    'world':     ['war', 'conflict', 'nato', 'sanctions', 'nuclear', 'missile', 'china', 'russia',
                   'ukraine', 'iran', 'middle east', 'gaza', 'israel', 'summit', 'un ', 'eu '],
    'tech':      ['ai', 'artificial intelligence', 'openai', 'google', 'apple', 'meta', 'microsoft',
                   'nvidia', 'chip', 'semiconductor', 'robot', 'quantum', 'spacex', 'tesla'],
    'health':    ['fda', 'vaccine', 'covid', 'drug', 'health', 'hospital', 'medical', 'cancer',
                   'disease', 'mental health', 'diet', 'nutrition', 'exercise'],
    'science':   ['nasa', 'space', 'climate', 'earthquake', 'hurricane', 'research', 'study',
                   'discovery', 'species', 'ocean', 'environment'],
    'travel':    ['airline', 'flight', 'airport', 'tourism', 'visa', 'cruise', 'hotel'],
    'sports':    ['nba', 'nfl', 'mlb', 'fifa', 'olympic', 'championship', 'tournament', 'game'],
    'entertainment': ['movie', 'film', 'oscar', 'grammy', 'music', 'celebrity', 'netflix',
                       'disney', 'streaming', 'box office'],
}

# Skip UK-domestic news
UK_DOMESTIC = ['nhs', 'uk government', 'downing street', 'labour party', 'conservative party',
               'premier league', 'bbc weather', 'uk housing', 'ofsted', 'channel crossing']

# ─── Internal linking: keyword → gab.ae slug ───
INTERNAL_LINKS = {
    # Finance
    'mortgage': '/mortgage-calculator', 'inflation': '/fire-movement',
    'invest': '/capital-markets-wealth-guide-2026', 'stock': '/capital-markets-wealth-guide-2026',
    'retirement': '/fire-movement', 'budget': '/personal-finance-budgeting',
    'crypto': '/cryptocurrency-investing-guide', 'bitcoin': '/cryptocurrency-investing-guide',
    'real estate': '/real-estate-investing', 'housing': '/real-estate-investing',
    'tariff': '/capital-markets-wealth-guide-2026', 'trade war': '/capital-markets-wealth-guide-2026',
    'oil price': '/oil-price-impact-calculator', 'dividend': '/dividend-investing-guide',
    'etf': '/etf-investing-guide', 'interest rate': '/capital-markets-wealth-guide-2026',
    'startup': '/business-plan-startup-strategy', 'venture capital': '/venture-capital-fundraising',
    # Tech
    'ai': '/ai-autonomous-agents', 'cybersecurity': '/cybersecurity-privacy',
    'saas': '/micro-saas-bootstrapping', 'privacy': '/cybersecurity-privacy',
    # Health
    'vaccine': '/health-wellness-optimization', 'nutrition': '/nutrition-guide',
    'fitness': '/fitness-training-guide', 'mental health': '/health-wellness-optimization',
    # Travel
    'flight': '/flight-hacking-airline-routing', 'visa': '/visas-residency-citizenship',
    'nomad': '/digital-nomad-lifestyle', 'cost of living': '/cost-of-living-geo-arbitrage',
    # Lifestyle
    'freelanc': '/freelancing-consulting-business', 'remote work': '/remote-work-career-strategies',
    'social media': '/social-media-algorithms-growth', 'youtube': '/video-production-youtube-strategy',
}


def get_existing():
    """Get existing slugs, source URLs, and title keywords from D1."""
    slugs, urls, words = set(), set(), set()
    try:
        r = subprocess.run(
            ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote',
             '--command', "SELECT slug, source_url, title FROM news"],
            capture_output=True, text=True, cwd=BASE, timeout=30)
        for m in re.finditer(r'"slug":\s*"([^"]+)"', r.stdout):
            slugs.add(m.group(1))
        for m in re.finditer(r'"source_url":\s*"([^"]*)"', r.stdout):
            if m.group(1): urls.add(m.group(1).split('?')[0])
        for m in re.finditer(r'"title":\s*"([^"]+)"', r.stdout):
            words.update(re.findall(r'[a-z]{4,}', m.group(1).lower()))
    except Exception as e:
        print(f"  ⚠️ D1 query error: {e}", file=sys.stderr)
    return slugs, urls, words


def fetch_rss():
    """Fetch all RSS feeds."""
    stories = []
    for feed_entry in FEEDS:
        name, url = feed_entry[0], feed_entry[1]
        hint_cat = feed_entry[2] if len(feed_entry) > 2 else None
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })
            data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(data)
            
            items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
            for item in items[:8]:
                title = (item.findtext('title') or item.findtext('{http://www.w3.org/2005/Atom}title') or '').strip()
                link = (item.findtext('link') or '').strip()
                # Atom feeds use <link href="..."/> 
                if not link:
                    link_el = item.find('{http://www.w3.org/2005/Atom}link')
                    if link_el is not None:
                        link = link_el.get('href', '')
                desc = (item.findtext('description') or item.findtext('{http://www.w3.org/2005/Atom}summary') or item.findtext('{http://www.w3.org/2005/Atom}content') or '').strip()
                
                # Extract image from media:thumbnail or media:content
                image = ''
                for ns in ['http://search.yahoo.com/mrss/', 'media']:
                    for tag in [f'{{{ns}}}thumbnail', f'{{{ns}}}content']:
                        el = item.find(tag)
                        if el is not None:
                            image = el.get('url', '')
                            if image: break
                    if image: break
                
                # Also check enclosure
                if not image:
                    enc = item.find('enclosure')
                    if enc is not None and 'image' in (enc.get('type', '')):
                        image = enc.get('url', '')
                
                if title and link:
                    stories.append({
                        'source': name,
                        'title': title,
                        'link': link.split('?')[0],
                        'description': strip_html(desc)[:500],
                        'image': image,
                        'hint_category': hint_cat,
                    })
        except Exception as e:
            print(f"  ⚠️ Feed error {name}: {e}", file=sys.stderr)
    return stories


def strip_html(text):
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return text.strip()


def slugify(text):
    """Generate URL slug from text."""
    s = text.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s).strip('-')
    return s[:80]


def categorize(title, description, hint=None):
    """Assign category based on keyword matching, with optional feed hint."""
    text = (title + ' ' + description).lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score
    # Feed hint gets a boost
    if hint and hint in CATEGORY_KEYWORDS:
        scores[hint] = scores.get(hint, 0) + 3
    if scores:
        return max(scores, key=scores.get)
    return hint or 'world'


def extract_tags(title, description):
    """Extract relevant tags from title + description."""
    text = (title + ' ' + description).lower()
    tags = set()
    
    # Named entities / topics
    tag_patterns = [
        (r'\btrump\b', 'trump'), (r'\bbiden\b', 'biden'), (r'\bchina\b', 'china'),
        (r'\brussia\b', 'russia'), (r'\bukraine\b', 'ukraine'), (r'\biran\b', 'iran'),
        (r'\bnato\b', 'nato'), (r'\beu\b', 'eu'), (r'\bfed\b', 'federal-reserve'),
        (r'\bai\b', 'artificial-intelligence'), (r'\bnvidia\b', 'nvidia'),
        (r'\btesla\b', 'tesla'), (r'\bapple\b', 'apple'), (r'\bgoogle\b', 'google'),
        (r'\bbitcoin\b', 'bitcoin'), (r'\bcrypto', 'cryptocurrency'),
        (r'\btariff', 'tariffs'), (r'\binflation\b', 'inflation'),
        (r'\brecession\b', 'recession'), (r'\bclimate\b', 'climate'),
    ]
    for pattern, tag in tag_patterns:
        if re.search(pattern, text):
            tags.add(tag)
    
    # Add category as tag
    cat = categorize(title, description)
    tags.add(cat)
    
    return list(tags)[:8]


def find_internal_links(title, description):
    """Find relevant gab.ae pages to link to."""
    text = (title + ' ' + description).lower()
    links = []
    seen = set()
    for keyword, slug in INTERNAL_LINKS.items():
        if keyword in text and slug not in seen:
            links.append(slug)
            seen.add(slug)
            if len(links) >= 3:
                break
    return links


def fetch_article_content(url):
    """Fetch the full article page and extract readable text."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        data = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', errors='replace')
        
        # Extract paragraphs from article body
        paragraphs = []
        
        # Look for article content in <article> or common content divs
        article_match = re.search(r'<article[^>]*>(.*?)</article>', data, re.DOTALL)
        if article_match:
            content = article_match.group(1)
        else:
            # Fallback: look for main content area
            for selector in [r'class="[^"]*article-body[^"]*"', r'class="[^"]*story-body[^"]*"',
                           r'class="[^"]*entry-content[^"]*"', r'class="[^"]*post-content[^"]*"']:
                match = re.search(f'<div[^>]*{selector}[^>]*>(.*?)</div>', data, re.DOTALL)
                if match:
                    content = match.group(1)
                    break
            else:
                content = data
        
        # Extract <p> tags
        for p_match in re.finditer(r'<p[^>]*>(.*?)</p>', content, re.DOTALL):
            text = strip_html(p_match.group(1))
            # Filter: must be actual content (>40 chars, not navigation/ads)
            if len(text) > 40 and not any(skip in text.lower() for skip in 
                ['cookie', 'subscribe', 'sign up', 'advertisement', 'copyright', 'all rights reserved']):
                paragraphs.append(text)
        
        return paragraphs[:15]  # Max 15 paragraphs
    except Exception as e:
        print(f"    ⚠️ Fetch error: {e}", file=sys.stderr)
        return []


def build_article(story, paragraphs):
    """Build structured article JSON from RSS story + fetched content."""
    title = story['title']
    description = story['description']
    category = categorize(title, description, story.get('hint_category'))
    tags = extract_tags(title, description)
    internal_links = find_internal_links(title, description)
    
    # Build slug: category-keyword-keyword-YYYY
    slug_base = slugify(title)
    slug = f"{slug_base}-{datetime.now().strftime('%Y')}" if not slug_base.endswith(str(datetime.now().year)) else slug_base
    
    # Build sections from paragraphs
    sections = []
    
    if paragraphs:
        # Section 1: What Happened (first 3-4 paragraphs)
        what_happened = paragraphs[:min(4, len(paragraphs))]
        sections.append({
            'heading': 'What Happened',
            'paragraphs': what_happened,
        })
        
        # Section 2: Why It Matters (next 3-4 paragraphs)
        if len(paragraphs) > 4:
            why_matters = paragraphs[4:min(8, len(paragraphs))]
            sections.append({
                'heading': 'Why It Matters',
                'paragraphs': why_matters,
            })
        
        # Section 3: What Comes Next (remaining paragraphs)
        if len(paragraphs) > 8:
            whats_next = paragraphs[8:]
            sections.append({
                'heading': 'What Comes Next',
                'paragraphs': whats_next,
            })
    else:
        # Fallback: use RSS description
        sections.append({
            'heading': 'What Happened',
            'paragraphs': [description] if description else ['Breaking story — details emerging.'],
        })
    
    # Add internal links section if we have any
    if internal_links:
        link_paragraphs = []
        for link in internal_links:
            link_name = link.strip('/').replace('-', ' ').title()
            link_paragraphs.append(f'Related: <a href="https://gab.ae{link}">{link_name}</a>')
        sections.append({
            'heading': 'Related Resources',
            'paragraphs': link_paragraphs,
        })
    
    # Build lede (first paragraph, max 200 chars)
    lede = paragraphs[0][:200] if paragraphs else description[:200]
    
    # Meta description
    meta_desc = f"{lede[:155]}..." if len(lede) > 155 else lede
    
    article = {
        'slug': slug,
        'title': title,
        'description': meta_desc,
        'category': category,
        'image': story.get('image', ''),
        'imageAlt': title,
        'lede': lede,
        'sections': sections,
        'tags': tags,
        'sources': [{'name': story['source'], 'url': story['link']}],
        'faqs': [],  # Skip FAQs for speed
    }
    
    return article


def insert_article(article):
    """Insert article into D1 via wrangler."""
    import tempfile
    
    tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, dir='/tmp')
    json.dump(article, tf)
    tf.close()
    
    r = subprocess.run(
        ['python3', 'scripts/insert-news.py', tf.name],
        capture_output=True, text=True, cwd=BASE, timeout=30
    )
    os.unlink(tf.name)
    
    return '✅' in r.stdout, r.stdout.strip()


def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    count = 3
    if '--count' in args:
        idx = args.index('--count')
        if idx + 1 < len(args):
            count = int(args[idx + 1])
    
    print(f"📰 News Autopilot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Mode: {'DRY RUN' if dry_run else 'PUBLISH'}, Count: {count}")
    print()
    
    # 1. Get existing articles for dedup
    existing_slugs, existing_urls, existing_words = get_existing()
    print(f"📊 Existing articles: {len(existing_slugs)}")
    
    # 2. Fetch RSS
    stories = fetch_rss()
    print(f"📡 Fetched {len(stories)} stories from {len(FEEDS)} feeds")
    
    # 3. Filter candidates
    candidates = []
    seen = set()
    for s in stories:
        title_lower = s['title'].lower()
        
        # Skip UK domestic
        if any(kw in title_lower for kw in UK_DOMESTIC):
            continue
        
        # Skip if source URL already covered
        if s['link'] in existing_urls:
            continue
        
        # Skip if title has >50% word overlap with existing
        story_words = set(re.findall(r'[a-z]{4,}', title_lower))
        if story_words and existing_words:
            overlap = len(story_words & existing_words) / max(len(story_words), 1)
            if overlap > 0.5:
                continue
        
        # Skip duplicates within batch
        if title_lower in seen:
            continue
        seen.add(title_lower)
        
        candidates.append(s)
    
    print(f"✅ {len(candidates)} new candidates after dedup")
    
    # 4. Prioritize (finance/world first)
    def priority(s):
        t = s['title'].lower()
        score = 0
        for cat in ['business', 'world', 'politics', 'tech']:
            for kw in CATEGORY_KEYWORDS.get(cat, [])[:10]:
                if kw in t:
                    score += 2
                    break
        return score
    
    candidates.sort(key=priority, reverse=True)
    candidates = candidates[:count]
    
    if not candidates:
        print("❌ No new stories to publish")
        return
    
    # 5. Process each candidate
    published = 0
    for i, story in enumerate(candidates):
        print(f"\n{'─'*60}")
        print(f"📰 [{i+1}/{len(candidates)}] {story['title'][:80]}")
        print(f"   Source: {story['source']} | {story['link'][:60]}")
        
        # Fetch full article content
        print(f"   Fetching article content...")
        paragraphs = fetch_article_content(story['link'])
        print(f"   Got {len(paragraphs)} paragraphs")
        
        # Build structured article
        article = build_article(story, paragraphs)
        print(f"   Category: {article['category']} | Tags: {', '.join(article['tags'][:5])}")
        print(f"   Slug: {article['slug']}")
        print(f"   Sections: {len(article['sections'])}")
        
        if dry_run:
            print(f"   🏷️ DRY RUN — would publish")
            continue
        
        # Insert into D1
        success, output = insert_article(article)
        if success:
            print(f"   ✅ Published!")
            published += 1
        else:
            print(f"   ❌ Failed: {output[:100]}")
    
    print(f"\n{'═'*60}")
    print(f"📊 Published: {published}/{len(candidates)}")


if __name__ == '__main__':
    main()
