#!/usr/bin/env python3
"""
Assign apex_slug and cluster to every tracked_page in the D1 database.
Reads all pages, classifies them, then batch-updates via wrangler d1 execute.
"""

import json
import subprocess
import sys
import os
import tempfile
import re
from collections import defaultdict

WRANGLER_DIR = os.path.expanduser("~/Desktop/gab-ae")
DB_NAME = "gab-ae-prod"
BATCH_SIZE = 500

# ── Domain → Default Apex ──────────────────────────────────────────────
DOMAIN_APEX = {
    'westmountfundamentals.com': 'capital-markets-wealth-guide-2026',
    'firemaths.info': 'capital-markets-wealth-guide-2026',
    'siliconbased.dev': 'software-ai-infrastructure-guide-2026',
    'fixitwithducttape.photonbuilder.com': 'software-ai-infrastructure-guide-2026',
    'migratingmammals.com': 'global-mobility-geo-arbitrage-guide-2026',
    'bodycount.photonbuilder.com': 'human-optimization-health-guide-2026',
    'sendnerds.photonbuilder.com': 'education-knowledge-commerce-guide-2026',
    'pleasestartplease.photonbuilder.com': 'ecommerce-supply-chain-guide-2026',
    'getthebag.photonbuilder.com': 'ecommerce-supply-chain-guide-2026',
    'thenookienook.com': 'interpersonal-dynamics-intimacy-guide-2026',
    'leeroyjenkins.quest': 'digital-media-creator-economy-guide-2026',
    'eeniemeenie.photonbuilder.com': 'digital-media-creator-economy-guide-2026',
    'justonemoment.photonbuilder.com': 'digital-media-creator-economy-guide-2026',
    'papyruspeople.photonbuilder.com': 'digital-media-creator-economy-guide-2026',
    '28grams.vip': 'fine-arts-design-creative-guide-2026',
    'photonbuilder.com': 'software-ai-infrastructure-guide-2026',
    'ijustwantto.live': 'real-estate-hospitality-guide-2026',
    'gab.ae': None,
}

# ── Cluster keyword rules per apex ─────────────────────────────────────
# Order matters: first match wins within an apex. More specific patterns first.
CLUSTER_RULES = {
    'capital-markets-wealth-guide-2026': [
        ('real-estate-finance', ['cap-rate', 'rental-yield', 'real-estate', 'housing', 'home-equity', 'rent-vs-buy', 'rental', 'renters-vs-homeowners']),
        ('intrinsic-value', ['intrinsic-value']),
        ('economic-prospect', ['economic-prospect']),
        ('dividend-investing', ['dividend', 'drip', 'payout', 'aristocrat', 'king']),
        ('etf-investing', ['etf', 'expense-ratio', 'index-fund', 'voo', 'spy', 'qqq', 'vanguard', 'schwab']),
        ('stock-analysis', ['stock', 'pe-ratio', 'beta', 'buyback', 'insider', 'earnings', 'market-cap', 'screener', 'eps', 'valuation', 'dcf', 'fair-value', 'price-target', 'price-to-book', 'free-cash-flow', 'revenue', 'institutional-ownership', 'short-squeeze', 'ipo', 'hedge-fund', 'value-investing', 'technical-analysis', 'balance-sheet', 'cash-flow', 'ceo-compensation', 'revenue-per-employee', 'volatility', '52-week']),
        ('portfolio-management', ['portfolio', 'rebalance', 'allocation', 'diversif', 'risk-tolerance', 'sharpe', 'asset-mix']),
        ('retirement-planning', ['retirement', '401k', 'ira', 'roth', 'fire', 'rrsp', 'tfsa', 'withdrawal', 'pension', 'annuit']),
        ('bonds-fixed-income', ['bond', 'treasury', 'yield-curve', 'fixed-income', 'coupon-rate']),
        ('crypto', ['crypto', 'bitcoin', 'blockchain', 'ethereum']),
        ('trading', ['trading', 'simulator', 'options', 'day-trading', 'short-selling', 'short-interest', 'margin', 'forex']),
        ('market-data', ['sp500', 's-p-500', 'market', 'recession', 'sector', 'concentration', 'correlation', 'historical-returns', 'benchmark', 'inflation']),
        ('personal-finance', ['budget', 'debt', 'savings', 'net-worth', 'credit-card', 'loan', 'mortgage', 'paycheck', 'tax', 'salary', 'income', 'compound', 'interest', 'amortiz', 'cost', 'calculator', 'money', 'financial', 'wealth', 'capital-gain', 'depreci', 'emergency-fund', 'fiduciary', 'broker', 'fee', 'robo-advisor', 'invest', 'brokerage', 'planner', 'cd-rate', 'what-is-a-cd']),
    ],
    'software-ai-infrastructure-guide-2026': [
        ('tech-reviews', ['best-', 'comparison', '-vs-', 'angular-vs', 'astro-vs', 'react-vs', 'vue-vs', 'next-vs']),
        ('reference', ['ascii', 'binary', 'unicode', 'table', 'chart']),
        ('timers-clocks', ['timer', 'countdown', 'minute-timer', 'hour-timer', 'second-timer', 'stopwatch']),
        ('productivity', ['planner', 'filofax', 'platinum-planner', 'digital-planner']),
        ('seo-analytics', ['seo', 'meta-tag', 'schema', 'og-tag', 'sitemap', 'analytics', 'structured-data']),
        ('security', ['security', 'password', 'privacy', 'vpn', 'hash', 'jwt', 'csp', 'oauth', 'encrypt', 'ssl', 'cors']),
        ('css-frontend', ['css', 'tailwind', 'bootstrap', 'flexbox', 'grid', 'color', 'gradient', 'shadow', 'border', 'font-size', 'responsive', 'animation', 'transition']),
        ('api-data', ['api', 'json', 'xml', 'yaml', 'csv', 'rest', 'graphql', 'webhook', 'endpoint']),
        ('devops-infra', ['docker', 'ci-cd', 'nginx', 'git', 'ssh', 'hosting', 'deploy', 'monitoring', 'kubernetes', 'terraform', 'aws', 'cloudflare']),
        ('web-performance', ['performance', 'benchmark', 'framework-size', 'bundle', 'lighthouse', 'lazy-load', 'cache']),
        ('developer-tools', ['tool', 'generator', 'formatter', 'minifier', 'encoder', 'decoder', 'converter', 'validator', 'tester', 'regex', 'uuid', 'base64', 'url-encode', 'diff', 'playground', 'snippet', 'lint', 'debug']),
    ],
    'global-mobility-geo-arbitrage-guide-2026': [
        ('visas-documents', ['visa', 'passport', 'schengen', 'residency', 'immigration', 'work-permit']),
        ('flight-travel', ['flight', 'airport', 'airline', 'cruise', 'hurricane', 'layover', 'baggage']),
        ('money-abroad', ['currency', 'travel-card', 'no-fx', 'exchange-rate', 'banking-abroad']),
        ('nomad-lifestyle', ['nomad', 'coworking', 'remote-work', 'cost-of-living', 'expat', 'digital-nomad']),
        ('travel-planning', ['packing', 'budget', 'checklist', 'countdown', 'insurance', 'timezone', 'itinerary', 'travel', 'destination', 'guide', 'trip', 'country']),
    ],
    'human-optimization-health-guide-2026': [
        ('medical-tools', ['a1c', 'gfr', 'bac', 'blood-pressure', 'blood-type', 'creatinine', 'ascvd', 'crcl', 'chronological-age']),
        ('dental-grooming', ['toothbrush', 'dental', 'electric-vs-manual']),
        ('research', ['e2-', 'genotype', 'therapeutic', 'integration-patterns']),
        ('body-metrics', ['bmi', 'body-fat', 'ffmi', 'ideal-weight', 'body-type', 'waist', 'height', 'weight-for', 'lean-mass', 'bmr', 'bra-size']),
        ('reproductive-health', ['pregnancy', 'ovulation', 'period', 'conception', 'ivf', 'hpv', 'vaccine', 'cervical', 'fertility', 'menstrual', 'birth-control', 'contracepti', 'trimester', 'due-date', 'implantation']),
        ('supplements', ['supplement', 'vitamin', 'peptide', 'creatine', 'nootropic']),
        ('sleep-recovery', ['sleep', 'mattress', 'insomnia', 'circadian']),
        ('nutrition', ['calorie', 'protein', 'meal', 'diet', 'fasting', 'tdee', 'macro', 'food', 'carb', 'keto', 'nutriti', 'fiber']),
        ('fitness', ['workout', 'exercise', 'hiit', 'running', 'gym', 'stretching', 'yoga', 'one-rep-max', 'vo2', 'push-up', 'squat', 'bench', 'deadlift', 'cardio', 'steps', 'walk', 'pace', 'marathon', 'rep', 'set', 'muscle', 'strength', 'training', 'fitness-tracker']),
    ],
    'real-estate-hospitality-guide-2026': [
        ('home-maintenance', ['maintenance', 'checklist', 'unclog', 'drain', 'inspection', 'inventory', 'cleaning']),
        ('energy-efficiency', ['energy', 'solar', 'electricity', 'btu', 'insulation', 'voltage']),
        ('moving', ['moving', 'apartment', 'first-apartment']),
        ('diy-materials', ['lumber', 'concrete', 'gravel', 'mulch', 'drywall', 'tile', 'board-foot', 'cubic-yard', 'stair', 'fence', 'deck', 'wallpaper', 'roof-pitch', 'paint', 'flooring', 'surface-area', 'sq-ft', 'square-foot', 'square-footage']),
        ('home-improvement', ['remodel', 'renovation', 'diy', 'contractor', 'floor', 'roof', 'plumb', 'electric', 'hvac', 'organiz', 'landscap', 'garden', 'lawn', 'plant', 'cabinet', 'kitchen-remodel', 'bathroom-remodel', 'deep-clean', 'pressure-wash', 'caulk', 'grout', 'standing-desk', 'furniture']),
        ('home-security', ['security-camera', 'security-system', 'smart-home', 'lock', 'alarm', 'doorbell', 'surveillance']),
        ('real-estate', ['real-estate', 'mortgage', 'home-buy', 'house-hunt', 'cap-rate', 'rental', 'rent-vs-buy', 'housing', 'property', 'apprais', 'closing-cost', 'down-payment', 'home-equity', 'home-value', 'home-inspection']),
        ('hospitality', ['hotel', 'airbnb', 'hosting', 'guest', 'check-in']),
    ],
    'education-knowledge-commerce-guide-2026': [
        ('math-calculators', ['calculator', 'fraction', 'percent', 'square-root', 'slope', 'derivative', 'integral', 'matrix', 'standard-deviation', 'algebra', 'equation', 'geometry', 'trigonometr', 'logarithm', 'exponent', 'factor', 'prime', 'ratio', 'proportion', 'mean', 'median', 'mode', 'probability', 'permutation', 'combination', 'quadratic', 'polynomial', 'lcm', 'gcf', 'gcd', 'decimal', 'binary-to', 'hex-to', 'roman-numeral', 'scientific-notation', 'significant-figure', 'average', 'area', 'volume', 'perimeter', 'circumference', 'pythagorean', 'midpoint', 'distance-formula']),
        ('academic-tools', ['gpa', 'grade', 'finals', 'sat', 'study', 'citation', 'essay', 'typing', 'flashcard', 'scholarship', 'college', 'university', 'course', 'exam', 'test-prep', 'act-score', 'class-rank']),
        ('reference', ['chart', 'multiplication', 'place-value', 'ti-84', 'periodic-table', 'conversion', 'unit', 'measurement']),
    ],
    'ecommerce-supply-chain-guide-2026': [
        ('career-tools', ['resume', 'interview', 'linkedin', 'freelance', 'salary', 'negotiation', 'job', 'career', 'networking', 'branding', 'internship', 'side-hustle']),
        ('automotive', ['car', 'vehicle', 'auto', 'tire', 'oil-change', 'obd2', 'dash-cam', 'fuel', 'motor-oil', 'wax', 'battery', 'ev-vs-gas', 'catalytic', 'mpg', 'gas', 'engine', 'tow', 'vin', 'odometer', 'mileage', 'horsepower', 'torque', 'brake', 'transmission']),
        ('business-tools', ['startup', 'business-plan', 'how-to-start', 'franchise', 'how-much-does-it-cost', 'profit-margin', 'break-even', 'roi']),
        ('product-reviews', ['best-', 'review', 'comparison', 'vs', 'top-', 'buying-guide']),
        ('ecommerce', ['shop', 'store', 'ecommerce', 'dropship', 'inventory', 'shipping', 'supply-chain', 'wholesale', 'retail', 'amazon', 'etsy']),
    ],
    'interpersonal-dynamics-intimacy-guide-2026': [
        ('contraception', ['birth-control', 'iud', 'implant', 'contraception', 'emergency-contraception', 'pill']),
        ('lubricant-guides', ['lube', 'lubricant']),
        ('fertility', ['fertility', 'ovulation']),
        ('dating', ['dating', 'date-night', 'date-ideas', 'first-date', 'honeymoon', 'tinder', 'hinge', 'bumble', 'pickup', 'flirt', 'attract']),
        ('sexual-health', ['sexual', 'std', 'sti', 'condom', 'sex-ed', 'orgasm', 'libido', 'erectile', 'kegel']),
        ('relationships', ['relationship', 'marriage', 'couples', 'love', 'breakup', 'divorce', 'communication', 'attachment', 'trust', 'jealous', 'boundary', 'toxic', 'narciss', 'gasligh', 'red-flag', 'green-flag', 'compatibility', 'consent']),
        ('intimacy', ['intimacy', 'romance', 'foreplay', 'sensual', 'position', 'fantasy', 'kink', 'bdsm', 'pleasure']),
    ],
    'digital-media-creator-economy-guide-2026': [
        ('board-games-social', ['board-game', 'charades', 'trivia', 'never-have-i-ever', 'would-you-rather', 'truth-or-dare', 'dice']),
        ('gaming-gear', ['headset', 'keyboard', 'mouse', 'monitor', 'chair', 'gaming-pc', 'streaming-setup', 'capture-card', 'microphone', 'webcam']),
        ('gaming-tools', ['game', 'fps', 'dpi', 'aim', 'tier-list', 'tracker', 'filler-list', 'valorant', 'fortnite', 'minecraft', 'pokemon', 'roblox', 'genshin', 'apex', 'league', 'overwatch', 'elden', 'souls', 'zelda', 'gta', 'anime', 'manga', 'naruto', 'one-piece', 'bleach', 'dragon-ball']),
        ('random-generators', ['random', 'coin-flip', 'wheel', 'team-generator', 'name-generator', 'number-generator', 'picker', 'spinner', 'lottery', 'raffle']),
        ('timers-clocks', ['timer', 'countdown', 'pomodoro', 'clock', 'stopwatch', 'world-clock', 'schedule', 'alarm', 'interval']),
        ('text-tools', ['font', 'text', 'character', 'word-count', 'binary', 'morse', 'lorem', 'markdown', 'glitch', 'unicode', 'ascii', 'emoji', 'symbol', 'zalgo', 'fancy-text', 'strikethrough', 'bold-text', 'italic-text', 'case-converter', 'letter']),
        ('productivity', ['meditation', 'focus', 'journal', 'habit', 'digital-detox', 'deep-work', 'goal', 'planner', 'to-do', 'checklist', 'note']),
    ],
    'fine-arts-design-creative-guide-2026': [
        ('beverages', ['coffee', 'cocktail', 'tea', 'caffeine', 'abv']),
        ('baking', ['bread', 'sourdough', 'yeast', 'dough', 'flour', 'baking']),
        ('kitchen-tools', ['knife', 'cutting-board', 'blender', 'scale', 'air-fryer', 'cast-iron', 'espresso', 'instant-pot', 'food-processor']),
        ('nutrition-tools', ['nutrition', 'calorie', 'protein-per-calorie', 'recipe-calorie']),
        ('cooking', ['cook', 'recipe', 'meal-prep', 'spice', 'oil', 'smoke-point', 'fermentation', 'smoking', 'sous-vide', 'food', 'grill', 'roast', 'fry', 'sauté', 'braise', 'stew', 'soup', 'sauce', 'marinade', 'cake', 'cookie', 'pastry', 'dessert', 'chocolate', 'candy', 'ice-cream', 'wine', 'beer', 'spirit', 'bartend', 'mixolog', 'ingredient', 'nutrition-fact', 'serving', 'portion', 'gram', 'ounce', 'cup', 'tablespoon', 'teaspoon', 'kitchen']),
        ('design', ['design', 'color-palette', 'typography', 'illustrat', 'photoshop', 'figma', 'canva', 'sketch', 'draw', 'paint', 'art', 'craft', 'calligraphy', 'lettering']),
        ('music', ['music', 'guitar', 'piano', 'drum', 'chord', 'scale', 'tuning', 'bpm', 'metronome', 'song', 'lyric', 'playlist']),
    ],
}

# ── Firemaths RE override keywords ─────────────────────────────────────
FIREMATHS_RE_KEYWORDS = [
    'cap-rate', 'cap-rates', 'rental-yield', 'real-estate', 'rent-vs-buy',
    'housing', 'home-equity', 'renters-vs-homeowners', 'house-hunt',
    'guide-real-estate', 'mortgage'
]


def run_wrangler_query(sql):
    """Run a SQL query against D1 and return results."""
    result = subprocess.run(
        ['npx', 'wrangler', 'd1', 'execute', DB_NAME, '--remote', '--json', '--command', sql],
        capture_output=True, text=True, cwd=WRANGLER_DIR
    )
    if result.returncode != 0:
        print(f"ERROR running query: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    return data[0]['results']


def run_wrangler_file(filepath):
    """Execute a SQL file against D1."""
    result = subprocess.run(
        ['npx', 'wrangler', 'd1', 'execute', DB_NAME, '--remote', '--file', filepath],
        capture_output=True, text=True, cwd=WRANGLER_DIR
    )
    if result.returncode != 0:
        print(f"ERROR executing file: {result.stderr}", file=sys.stderr)
        return False
    return True


def classify_page(domain, path, title):
    """Return (apex_slug, cluster) for a given page."""
    # Skip gab.ae
    if domain == 'gab.ae':
        return (None, None)

    # Get default apex from domain
    apex = DOMAIN_APEX.get(domain)
    if apex is None and domain != 'gab.ae':
        # Unknown domain — try to infer or skip
        print(f"  WARNING: Unknown domain '{domain}', skipping", file=sys.stderr)
        return (None, None)

    path_lower = (path or '').lower()
    title_lower = (title or '').lower()
    text = path_lower + ' ' + title_lower

    # Firemaths RE override: check if this firemaths page is about real estate
    if domain == 'firemaths.info':
        for kw in FIREMATHS_RE_KEYWORDS:
            if kw in path_lower:
                apex = 'real-estate-hospitality-guide-2026'
                break

    # bra-size pages → human-optimization (body-metrics), override domain default
    if 'bra-size' in path_lower:
        return ('human-optimization-health-guide-2026', 'body-metrics')

    # fertility/ovulation on bodycount → stays in human-optimization (reproductive-health)
    # fertility/ovulation on thenookienook → interpersonal-dynamics (fertility cluster)
    if domain == 'bodycount.photonbuilder.com' and ('fertility' in path_lower or 'ovulation' in path_lower):
        return ('human-optimization-health-guide-2026', 'reproductive-health')

    # Find cluster within the apex
    cluster = find_cluster(apex, text)

    return (apex, cluster)


def find_cluster(apex, text):
    """Match text against cluster rules for the given apex. Returns cluster name."""
    rules = CLUSTER_RULES.get(apex, [])
    for cluster_name, keywords in rules:
        for kw in keywords:
            if kw in text:
                return cluster_name
    return 'other'


def escape_sql_string(s):
    """Escape single quotes for SQL."""
    if s is None:
        return ''
    return s.replace("'", "''")


def main():
    print("=== SEO Hierarchy Assignment Script ===\n")

    # 1. Fetch all pages
    print("Fetching all tracked pages...")
    pages = run_wrangler_query("SELECT domain, path, title FROM tracked_pages ORDER BY domain, path;")
    print(f"  Found {len(pages)} pages\n")

    # 2. Classify each page
    print("Classifying pages...")
    assignments = []  # list of (apex, cluster, domain, path)
    skipped = 0
    apex_counts = defaultdict(int)
    cluster_counts = defaultdict(lambda: defaultdict(int))

    for page in pages:
        domain = page['domain']
        path = page['path']
        title = page['title']

        apex, cluster = classify_page(domain, path, title)
        if apex is None:
            skipped += 1
            continue

        assignments.append((apex, cluster, domain, path))
        apex_counts[apex] += 1
        cluster_counts[apex][cluster] += 1

    print(f"  Classified: {len(assignments)} pages")
    print(f"  Skipped: {skipped} pages (gab.ae or unknown domain)\n")

    # 3. Generate and execute batch SQL updates
    print("Generating batch SQL updates...")
    batch_num = 0
    total_executed = 0

    for i in range(0, len(assignments), BATCH_SIZE):
        batch = assignments[i:i + BATCH_SIZE]
        batch_num += 1

        # Build SQL file
        lines = []
        for apex, cluster, domain, path in batch:
            lines.append(
                f"UPDATE tracked_pages SET apex_slug='{escape_sql_string(apex)}', "
                f"cluster='{escape_sql_string(cluster)}' "
                f"WHERE domain='{escape_sql_string(domain)}' AND path='{escape_sql_string(path)}';"
            )

        sql_content = '\n'.join(lines)
        sql_file = os.path.join(WRANGLER_DIR, 'scripts', f'_batch_{batch_num}.sql')
        with open(sql_file, 'w') as f:
            f.write(sql_content)

        print(f"  Batch {batch_num}: {len(batch)} updates → {sql_file}")
        success = run_wrangler_file(sql_file)
        if success:
            total_executed += len(batch)
            print(f"    ✓ Executed successfully")
        else:
            print(f"    ✗ FAILED")

        # Clean up temp file
        os.remove(sql_file)

    print(f"\nTotal updates executed: {total_executed}\n")

    # 4. Print summary
    print("=" * 60)
    print("SUMMARY: Pages per Apex Guide")
    print("=" * 60)
    for apex in sorted(apex_counts.keys()):
        print(f"  {apex}: {apex_counts[apex]}")
    print(f"  {'TOTAL':}: {sum(apex_counts.values())}")

    print(f"\n{'=' * 60}")
    print("SUMMARY: Pages per Apex → Cluster")
    print("=" * 60)
    for apex in sorted(cluster_counts.keys()):
        print(f"\n  {apex}:")
        for cluster in sorted(cluster_counts[apex].keys(), key=lambda c: -cluster_counts[apex][c]):
            print(f"    {cluster}: {cluster_counts[apex][cluster]}")

    # 5. Verify with DB queries
    print(f"\n{'=' * 60}")
    print("VERIFICATION: Querying database...")
    print("=" * 60)

    print("\nPages per apex_slug:")
    rows = run_wrangler_query(
        "SELECT apex_slug, COUNT(*) as pages FROM tracked_pages "
        "WHERE apex_slug IS NOT NULL GROUP BY apex_slug ORDER BY pages DESC;"
    )
    for r in rows:
        print(f"  {r['apex_slug']}: {r['pages']}")

    print("\nPages per apex_slug → cluster:")
    rows = run_wrangler_query(
        "SELECT apex_slug, cluster, COUNT(*) as pages FROM tracked_pages "
        "WHERE apex_slug IS NOT NULL GROUP BY apex_slug, cluster ORDER BY apex_slug, pages DESC;"
    )
    current_apex = None
    for r in rows:
        if r['apex_slug'] != current_apex:
            current_apex = r['apex_slug']
            print(f"\n  {current_apex}:")
        print(f"    {r['cluster']}: {r['pages']}")

    print("\n✅ Done!")


if __name__ == '__main__':
    main()
