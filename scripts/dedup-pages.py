#!/usr/bin/env python3
"""
gab.ae page deduplication.
Reads all pages from D1, identifies duplicates by semantic concept,
picks the cleanest canonical slug, outputs SQL to delete dupes.

Run with --dry-run (default) or --execute to actually delete.
"""
import json, re, sys, subprocess
from collections import defaultdict
from pathlib import Path

DRY_RUN = '--execute' not in sys.argv

# Load all pages
print("Fetching all pages from D1...")
result = subprocess.run(
    ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote',
     '--command', 'SELECT slug, category, config FROM pages', '--json'],
    capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
)
data = json.loads(result.stdout)
rows = data[0]['results'] if isinstance(data, list) else data['results']
print(f"Loaded {len(rows)} pages\n")


def normalize_concept(slug):
    """Reduce a slug to its core concept for grouping."""
    s = slug
    
    # 1. Strip SEO/quality prefixes
    for p in ['free-', 'best-', 'most-accurate-', 'online-', 'accurate-', 'simple-',
              'my-', 'new-', 'smart-', 'advanced-', 'basic-', 'ideal-', 'healthy-',
              'medical-', 'figure-', 'find-my-', 'use-a-', 'i-']:
        if s.startswith(p): s = s[len(p):]
    
    s = s.replace('-calculator', '').replace('-calc', '')
    
    # 2. how-to / what-is / calculate patterns → strip entirely
    s = re.sub(r'^how-(?:to|do-you|do-i)-calculate-(?:my-|your-|the-|a-)?', '', s)
    s = re.sub(r'^calculate-(?:my-)?', '', s)
    s = re.sub(r'^what-is-(?:my-|this-|a-)?', '', s)
    s = re.sub(r'^whats-(?:my-)?', '', s)
    
    # 3. Brand/authority prefixes → strip
    brands = (
        'dave-ramsey|bankrate|forbes|dollartimes|brett-whissel|marketbeat|mr-cooper|'
        'adp|barchart|cboe|kelley-blue-book|aarp|cdc|nhs|nih|nhlbi|webmd|mayo-clinic|'
        'harvard|hers|google|bodybuildingcom|bodybuilding|myfitnesspal|nasm|omni|merck|'
        'gym-geek|pro-physique|iifym|mia-aesthetics|wegovy|losertown|eric-roberts|'
        'katy-hearn|warrior-babe|legion|mind-pump|gains-by-brains|pet-alliance|ti-84'
    )
    s = re.sub(r'^(?:' + brands + r')-', '', s)
    
    # 4. Restaurant/food brands → all become "restaurant-food-type"
    restaurants = (
        'chipotle|chiptole|chipolte|starbucks|mcdonalds|subway|taco-bell|dunkin|'
        'panera|panda-express|panda|chick-fil-a|burger-king|wendys|pizza-hut|'
        'popeyes|dominos|kfc|in-n-out|in-and-out|whataburger|five-guys|5-guys|'
        'dairy-queen|cava|qdoba|moes|potbelly|sheetz|wawa|texas-roadhouse|chilis|'
        'tropical-smoothie|sweetgreen|jimmy-johns|salata|bibibop|7-brew|blaze-pizza|'
        'ihop|dutch-bros|canes|hills|purina|pet-alliance'
    )
    if re.match(r'^(?:' + restaurants + r')-', s):
        # Extract what they're calculating (calorie, macro, nutrition)
        remainder = re.sub(r'^(?:' + restaurants + r')-', '', s)
        # Normalize sub-variants: bowl-calorie, burrito-calorie, drink-calorie → calorie
        remainder = re.sub(r'^(?:bowl-|burrito-|sandwich-|sub-|drink-|coffee-|pizza-|food-|plate-)', '', remainder)
        s = 'restaurant-' + remainder if remainder else 'restaurant-calorie'
    
    # 5. Stock tickers → all become "stock-type"
    tickers = (
        'schd|voo|spy|jepi|jepq|agnc|apple|coca-cola|verizon|shell|vym|msty|tsly|'
        'ulty|qqq|qqqi|realty-income|spyi|cd|o'
    )
    if re.match(r'^(?:' + tickers + r')-', s):
        remainder = re.sub(r'^(?:' + tickers + r')-', '', s)
        s = 'stock-' + remainder if remainder else 'stock-dividend'
    
    # 6. State/country prefixes
    for loc in ['california-', 'florida-', 'texas-', 'india-', 'uk-', 'gbp-', 'yen-', 'japan-']:
        if s.startswith(loc): s = s[len(loc):]
    
    # 7. Military prefixes
    for mil in ['army-', 'navy-', 'air-force-', 'usmc-', 'us-navy-', 'naval-', 'military-']:
        if s.startswith(mil): s = s[len(mil):]
    
    # 8. Demographic suffixes (gender/age/group)
    demos = (
        r'-(?:women|woman|female|females|male|men|man|kids|kid|child|children|childrens|'
        r'childs|teens|teen|teenager|adults|adult|seniors|senior|boys|boy|girls|girl|'
        r'infant|newborn|toddler|baby|preterm|adolescent|older-woman|pediatric|'
        r'pediatrics|peds|geriatric|hers|womens|mens|cat|cats|dog|dogs|puppy|kitten|'
        r'feline|canine)$'
    )
    s = re.sub(demos, '', s)
    
    # -for-X goal suffixes
    s = re.sub(
        r'-for-(?:women|men|kids|teens|athletes|seniors?|female|males?|'
        r'weight-loss|muscle-gain|cutting|bulking|fat-loss|runners|weight-gain|'
        r'losing-weight|building-muscle|food|recipes|body-recomp|body-recomposition|'
        r'cats?|dogs?|puppies|kittens|senior-women|women-over-\d+|men-and-age|'
        r'weight-loss-surgery|weight-loss-and-muscle-gain|fat-loss-and-muscle-gain)$', '', s)
    s = re.sub(r'-to-(?:lose|gain|build|maintain)-\w+$', '', s)
    
    # 9. Platform/format suffixes
    for f in ['-excel', '-app', '-software', '-template', '-spreadsheet', 
              '-formula', '-equation', '-online', '-free', '-net']:
        s = s.replace(f, '')
    
    # 10. Unit/locale variants
    for u in ['-kg', '-lbs', '-cm', '-metric', '-inches-and-pounds', '-kg-and-cm',
              '-cm-and-kg', '-in-kg', '-in-kg-and-feet', '-usa', '-india', '-uk', '-nhs']:
        s = s.replace(u, '')
    
    # 11. Feature/modifier variants
    for f in ['-with-age', '-with-body-fat', '-with-measurements', '-with-muscle-mass',
              '-with-waist', '-by-age', '-by-age-and-gender', '-by-date', '-by-breed',
              '-by-weight', '-with-age-and-gender', '-by-stock', '-by-ticker',
              '-with-drip', '-with-dividend-reinvestment', '-with-company-match',
              '-with-inflation', '-with-balloon-payment', '-and-gender',
              '-height-and-weight', '-using-height-and-weight']:
        s = s.replace(f, '')
    
    # 12. Redundant trailing modifiers
    for m in ['-chart', '-index', '-percentage', '-percentile', '-scale', '-visual',
              '-rate', '-daily', '-monthly', '-quarterly', '-annual', '-weekly',
              '-simple', '-compound', '-reverse', '-score']:
        if s.endswith(m): s = s[:len(s)-len(m)]
    
    # 13. Known synonyms
    synonyms = {
        'bmi-body-fat': 'bmi',
        'bmi-calorie': 'bmi',
        'bmi-calorie-deficit': 'bmi',
        'bmi-cdc': 'bmi',
        'bmi-walking': 'bmi',
        'bmi-weight': 'bmi',
        'bmi-weight-loss': 'bmi',
        'bmi-ideal-weight': 'bmi',
        'bmi-to-weight': 'bmi',
        'bmi-pregnancy': 'bmi',
        'bmi-age': 'bmi',
        'bmi-for': 'bmi',
        'bmi-older': 'bmi',
        'body-bmi': 'bmi',
        'weight-bmi': 'bmi',
        'height-weight-bmi': 'bmi',
        'bmis': 'bmi',
        'calorie-burn': 'calorie-burn',
        'calorie-burned': 'calorie-burn',
        'calorie-burner': 'calorie-burn',
        'calorie-burning': 'calorie-burn',
        'calories-burned-heart-rate': 'calorie-burn',
        'calorie-defecit': 'calorie-deficit',
        'calorie-deficiet': 'calorie-deficit',
        'calorie-defict': 'calorie-deficit',
        'deficit-calorie': 'calorie-deficit',
        'calorie-cut': 'calorie-deficit',
        'calorie-cutting': 'calorie-deficit',
        'calorie-loss': 'calorie-deficit',
        'calorie-maintenance': 'calorie-maintenance',
        'calorie-maintain': 'calorie-maintenance',
        'maintain-calorie': 'calorie-maintenance',
        'maintence-calorie': 'calorie-maintenance',
        'maintenence-calorie': 'calorie-maintenance',
        'calorie-need': 'calorie-intake',
        'calorie-needs': 'calorie-intake',
        'calorie-per-day': 'calorie-intake',
        'calorie-requirement': 'calorie-intake',
        'calorie-consumption': 'calorie-intake',
        'calorie-goal': 'calorie-intake',
        'recommended-calorie-intake': 'calorie-intake',
        'calorie-macro': 'macro',
        'macro-calorie': 'macro',
        'macro-nutrient': 'macro',
        'macro-nutrients': 'macro',
        'macro-diet': 'macro',
        'macro-food': 'macro',
        'macro-recipe': 'macro',
        'macro-split': 'macro',
        'macro-ratio': 'macro',
        'macro-to-calorie': 'macro',
        'calorie-and-macro': 'macro',
        'calorie-and-protein': 'protein',
        'calorie-protein': 'protein',
        'protein-macro': 'protein',
        'protein-and-calorie': 'protein',
        'calorie-to-protein-ratio': 'protein',
        'body-fat-percent': 'body-fat',
        'body-fat-loss': 'body-fat',
        'body-fat-goal': 'body-fat',
        'percent-body-fat': 'body-fat',
        'skinfold-body-fat': 'body-fat',
        'caliper-body-fat': 'body-fat',
        'body-fat-caliper': 'body-fat',
        'lean-body-mass-with-body-fat': 'body-fat',
        'ymca-body-fat': 'body-fat',
        'body-fat-for': 'body-fat',
        'bmr-and-tdee': 'tdee',
        'bmr-tdee': 'tdee',
        'tdee-calorie': 'tdee',
        'tdee-calorie-deficit': 'tdee',
        'bmr-calorie': 'bmr',
        'basal-calorie': 'bmr',
        'base-calorie': 'bmr',
        'resting-calorie': 'bmr',
        'resting-calorie-burn': 'bmr',
        'body-calorie': 'calorie',
        'daily-calorie-burn': 'calorie-burn',
        'daily-calorie': 'calorie-intake',
        'daily-calorie-intake': 'calorie-intake',
        'daily-calorie-needs': 'calorie-intake',
        'daily-calorie-expenditure': 'calorie-intake',
        'calorie-step': 'step-calorie',
        'steps-to-calorie': 'step-calorie',
        'step-to-calorie': 'step-calorie',
        'calorie-count': 'calorie',
        'calorie-counter': 'calorie',
        'calorie-food': 'food-calorie',
        'calorie-in-food': 'food-calorie',
        'food-calorie': 'food-calorie',
        'ingredient-calorie': 'food-calorie',
        'nutrition-calorie': 'food-calorie',
        'calorie-meal': 'meal-calorie',
        'meal-calorie': 'meal-calorie',
        'calorie-exercise': 'exercise-calorie',
        'exercise-calorie': 'exercise-calorie',
        'exercise-calorie-burn': 'calorie-burn',
        'calorie-surplus': 'calorie-surplus',
        'gain-weight-calorie': 'calorie-surplus',
        'weight-gain-calorie': 'calorie-surplus',
        'calorie-weight-gain': 'calorie-surplus',
        'bulk-calorie': 'calorie-surplus',
        'bulking-calorie': 'calorie-surplus',
        'muscle-building-calorie': 'calorie-surplus',
        'muscle-gain-calorie': 'calorie-surplus',
        'calorie-bulk': 'calorie-surplus',
        'lose-weight-calorie': 'calorie-deficit',
        'weight-loss-calorie': 'calorie-deficit',
        'calorie-weight-loss': 'calorie-deficit',
        'fat-loss-calorie': 'calorie-deficit',
        'cutting-calorie': 'calorie-deficit',
        'cut-calorie': 'calorie-deficit',
        'daily-calorie-deficit-weight-loss': 'calorie-deficit',
        'calorie-deficit-weight-loss': 'calorie-deficit',
        'calorie-deficit-diet': 'calorie-deficit',
        'recomp-calorie': 'body-recomp-calorie',
        'body-recomp-calorie': 'body-recomp-calorie',
        'body-recomposition-calorie': 'body-recomp-calorie',
        'recomp-macro': 'body-recomp-macro',
        'body-recomp-macro': 'body-recomp-macro',
        'body-recomposition-macro': 'body-recomp-macro',
        'lean-bulk-calorie': 'calorie-surplus',
        'lean-bulk-macro': 'bulking-macro',
        'bulking-macro': 'bulking-macro',
        'cutting-macro': 'cutting-macro',
        'fat-loss-macro': 'cutting-macro',
        'weight-loss-macro': 'cutting-macro',
        'keto-macro': 'keto-macro',
        'ketogains-macro': 'keto-macro',
        'low-carb-macro': 'keto-macro',
        'carnivore-macro': 'carnivore-macro',
        'carnivore-diet-macro': 'carnivore-macro',
        'carnivore-calorie': 'carnivore-macro',
        'calorie-cycling': 'calorie-cycling',
        'zig-zag-calorie': 'calorie-cycling',
        'restaurant-nutrition': 'restaurant-calorie',
        'restaurant-bowl-calorie': 'restaurant-calorie',
        'restaurant-bowl-macro': 'restaurant-macro',
        'child-growth': 'growth-chart',
        'baby-growth': 'growth-chart',
        'baby-growth-chart': 'growth-chart',
        'baby-growth-curve': 'growth-chart',
        'boy-growth-chart': 'growth-chart',
        'boys-growth-chart': 'growth-chart',
        'girl-growth-chart': 'growth-chart',
        'girls-growth-chart': 'growth-chart',
        'infant-growth-chart': 'growth-chart',
        'infant-growth': 'growth-chart',
        'kids-growth': 'growth-chart',
        'kids-growth-chart': 'growth-chart',
        'child-growth-chart': 'growth-chart',
        'child-growth': 'growth-chart',
        'newborn-growth-chart': 'growth-chart',
        'toddler-growth-chart': 'growth-chart',
        'preterm-growth-chart': 'growth-chart',
        'fenton-growth': 'growth-chart',
        'fenton-growth-chart': 'growth-chart',
        'who-growth': 'growth-chart',
        'who-growth-chart': 'growth-chart',
        'growth-curve': 'growth-chart',
        'growth': 'growth-chart',
        'baby-growth-percentile': 'growth-chart',
        'who-growth-percentile': 'growth-chart',
        'growth-chart-percentile': 'growth-chart',
        'growth-percentile': 'growth-chart',
        'stock-dividend-reinvestment': 'stock-dividend',
        'stock-dividend-yield': 'stock-dividend',
        'stock-dividend-growth': 'stock-dividend',
        'stock-growth': 'stock-dividend',
        'dividend-reinvestment': 'dividend',
        'dividend-compound': 'dividend',
        'dividend-compound-interest': 'dividend',
        'dividend-drip': 'dividend',
        'drip-dividend': 'dividend',
        'dividend-income': 'dividend',
        'dividend-investing': 'dividend',
        'dividend-investment': 'dividend',
        'dividend-payment': 'dividend',
        'dividend-payout': 'dividend',
        'dividend-portfolio': 'dividend',
        'dividend-return': 'dividend',
        'dividend-snowball': 'dividend',
        'dividend-stock': 'dividend',
        'dividend-stocks': 'dividend',
        'dividend-etf': 'dividend',
        'dividend-discount-model': 'dividend',
        'investment-dividend': 'dividend',
        'compound-dividend': 'dividend',
        'compounding-dividend': 'dividend',
        'compound-interest-dividend': 'dividend',
        'savings-account-dividend': 'dividend',
        'certificate-dividend': 'dividend',
        'reit-dividend': 'dividend',
        'etf-dividend': 'dividend',
        'annual-dividend': 'dividend',
        'dividend-tax': 'dividend',
        'dividend-tax-rate': 'dividend',
        'dividend-yield': 'dividend',
        'sp-500-return': 'sp-500',
        'sp-500-returns': 'sp-500',
        'sp-500-index': 'sp-500',
        'sp-500-index-fund': 'sp-500',
        'sp-500-investment': 'sp-500',
        'sp-500-compound-interest': 'sp-500',
        'sp-500-historical-returns': 'sp-500',
        's-and-p-500-investment': 'sp-500',
        's-and-p-500': 'sp-500',
        's-p-500': 'sp-500',
        'sp-growth': 'sp-500',
        'index-fund': 'sp-500',
        'vanguard-sp-500': 'sp-500',
        '1000-invested-in-sp-500': 'sp-500',
        '10000-invested-in-sp-500': 'sp-500',
        'investment-sp-500': 'sp-500',
        'compound-interest': 'compound-interest',
        'compounding-interest': 'compound-interest',
        'compounded-growth': 'compound-interest',
        'compounding-growth': 'compound-interest',
        'compound-growth': 'compound-interest',
        'compound-growth-rate': 'compound-interest',
        'compound-annual-growth': 'compound-interest',
        'compound-annual-growth-rate': 'compound-interest',
        'compound-annual-growth-rate-formula': 'compound-interest',
        'interest-growth': 'compound-interest',
        'roi-rental-property': 'rental-roi',
        'roi-rental': 'rental-roi',
        'rental-property-roi': 'rental-roi',
        'rental-roi': 'rental-roi',
        'roi-rental-property-with-a-mortgage': 'rental-roi',
        'roi-on-rental-property': 'rental-roi',
        'roi-on-investment-property': 'rental-roi',
        'roi-real-estate': 'rental-roi',
        'rental-property-roi-excel': 'rental-roi',
        'roi-for-rental-property': 'rental-roi',
        'roi-in-real-estate': 'rental-roi',
        'roi-on-a-rental-property': 'rental-roi',
        'ebitda-from-income-statement': 'ebitda',
        'ebitda-margin': 'ebitda',
        'ebitda-multiple': 'ebitda',
        'adjusted-ebitda': 'ebitda',
        'ebitda-business-valuation': 'ebitda',
        'book-value-per-share': 'book-value',
        'book-value-of-equity': 'book-value',
        'net-book-value': 'book-value',
        'depreciation-on-equipment': 'depreciation',
        'depreciation-on-fixed-assets': 'depreciation',
        'depreciation-expense': 'depreciation',
        'depreciation-recapture': 'depreciation',
        'annual-depreciation': 'depreciation',
        'accumulated-depreciation': 'depreciation',
        'tax-depreciation': 'depreciation',
        'retained-earnings-from-balance-sheet': 'retained-earnings',
        'retained-earnings-on-a-balance-sheet': 'retained-earnings',
        'retained-earnings-on-balance-sheet': 'retained-earnings',
        'revenue-growth': 'revenue',
        'revenue-growth-rate': 'revenue',
        'sales-revenue': 'revenue',
        'total-revenue': 'revenue',
        'gross-revenue': 'revenue',
        'net-revenue': 'revenue',
        'total-sales-revenue': 'revenue',
        'net-sales-revenue': 'revenue',
        'average-revenue': 'revenue',
        'sales-revenue-accounting': 'revenue',
        'projected-revenue': 'revenue',
        'sales-revenue-from-balance-sheet': 'revenue',
        'revenue-from-balance-sheet': 'revenue',
        'revenue-in-accounting': 'revenue',
        'incremental-revenue': 'revenue',
        'recurring-revenue': 'revenue',
        'annual-recurring-revenue': 'revenue',
        'tax-revenue': 'revenue',
        'net-revenue-retention': 'revenue',
        'deferred-revenue': 'revenue',
        'roi-in-excel': 'roi',
        'roi-in-digital-marketing': 'marketing-roi',
        'roi-for-a-project': 'roi',
        'roi-saas': 'roi',
        'social-media-roi': 'marketing-roi',
        'digital-marketing-roi': 'marketing-roi',
        'online-marketing-roi': 'marketing-roi',
        'ppc-roi': 'marketing-roi',
        'ecommerce-roi': 'marketing-roi',
        'marketing-automation-roi': 'marketing-roi',
        'seo-roi': 'seo-roi',
        'seo-roi-excel': 'seo-roi',
        'enterprise-seo-roi': 'seo-roi',
        'heart-rate-zone-2': 'heart-rate-zone',
        'zone-2-heart-rate': 'heart-rate-zone',
        'zone-2-cardio-heart-rate': 'heart-rate-zone',
        'zone-heart-rate': 'heart-rate-zone',
        'zone-two-heart-rate': 'heart-rate-zone',
        'heart-rate-zones-by-age': 'heart-rate-zone',
        'heart-rate-training-zone': 'heart-rate-zone',
        'heart-rate-training-zones': 'heart-rate-zone',
        'target-heart-rate': 'heart-rate-zone',
        'target-heart-rate-zone': 'heart-rate-zone',
        'training-heart-rate': 'heart-rate-zone',
        'exercise-heart-rate': 'heart-rate-zone',
        'karvonen-heart-rate': 'heart-rate-zone',
        'fat-burn-heart-rate': 'heart-rate-zone',
        'fat-burning-heart-rate': 'heart-rate-zone',
        'fat-burning-heart-rate-zone': 'heart-rate-zone',
        'cardio-heart-rate': 'heart-rate-zone',
        'threshold-heart-rate': 'heart-rate-zone',
        'heart-rate-reserve': 'heart-rate-zone',
        'resting-heart-rate': 'heart-rate',
        'max-heart-rate': 'heart-rate',
        'maximum-heart-rate': 'heart-rate',
        'heart-rate-calorie': 'heart-rate',
        'blood-pressure-average': 'blood-pressure',
        'blood-pressure-by-age': 'blood-pressure',
        'blood-pressure-life-expectancy': 'blood-pressure',
        'blood-pressure-map': 'blood-pressure',
        'blood-pressure-mean': 'blood-pressure',
        'map-blood-pressure': 'blood-pressure',
        'mean-blood-pressure': 'blood-pressure',
        'average-blood-pressure': 'blood-pressure',
        '401k-growth': '401k',
        '401k-with-company-match': '401k',
        '401k-company-match': '401k',
        '401-k-growth': '401k',
        'company-match': '401k',
        '403b-growth': '403b',
        '529-growth': '529',
        '529-plan-growth': '529',
        'roth-ira-growth': 'roth-ira',
        'roth-growth': 'roth-ira',
        'ira-growth': 'ira',
        'tsp-growth': 'tsp',
        'hsa-growth': 'hsa-growth',
        'etf-growth': 'etf-growth',
        'etf-expense-ratio': 'etf-growth',
        'investment-growth': 'investment',
        'growth-of-investment': 'investment',
        'investment-portfolio': 'investment',
        'growth-investment': 'investment',
        'growth-of-money': 'investment',
        'financial-growth': 'investment',
        'asset-growth': 'investment',
        'future-growth': 'investment',
        'money-growth': 'investment',
        'wealth-growth': 'investment',
        'net-worth-growth': 'investment',
        'portfolio-growth': 'portfolio',
        'portfolio-allocation': 'portfolio',
        'portfolio-weight': 'portfolio',
        'portfolio-beta': 'portfolio',
        'beta-of-a-portfolio': 'portfolio',
        'retirement-growth': 'retirement',
        'retirement-withdrawal': 'retirement',
        'retirement-savings-growth': 'retirement',
        'retirement-portfolio': 'retirement',
        'retirement-account-growth': 'retirement',
        'savings-growth': 'savings',
        'savings-account-growth': 'savings',
        'high-yield-savings-account': 'savings',
        'account-growth': 'savings',
        'salary-growth': 'salary',
        'income-growth': 'salary',
        'auto-loan': 'car-loan',
        'auto-loan-payment': 'car-loan',
        'auto-payment': 'car-loan',
        'car-finance': 'car-loan',
        'car-loan-payment': 'car-loan',
        'car': 'car-loan',
        'auto-depreciation': 'car-depreciation',
        'car-depreciation-tax': 'car-depreciation',
        'home-mortgage': 'mortgage',
        'house-payment': 'mortgage',
        'mortgage-loan': 'mortgage',
        'mortgage-payment': 'mortgage',
        'mortgage-payoff': 'mortgage',
        'mortgage-rate': 'mortgage',
        'simple-mortgage': 'mortgage',
        'mortage': 'mortgage',
        'the-mortgage-company': 'mortgage',
        'mortgage-company-llc': 'mortgage',
        'heloc-payment': 'heloc',
        'heloc-vs-home-equity-loan': 'heloc',
        'home-equity-line-of-credit-rates': 'heloc',
        'home-equity-loan': 'home-equity',
        'home-equity-payment': 'home-equity',
        'home-equity-loan-interest-rate': 'home-equity',
        'home-equity-conversion-mortgage': 'home-equity',
        'cash-out-refinance-vs-home-equity-loan': 'home-equity',
        'pay-off-home-equity-loan-early': 'home-equity',
        'equity-house': 'home-equity',
        'equity-line-credit': 'home-equity',
        'gift-of-equity': 'home-equity',
        'lease-equity': 'home-equity',
        'negative-equity-auto-loan': 'home-equity',
        'home-loan': 'mortgage',
        'loan-amortization': 'loan',
        'loan-payment': 'loan',
        'loan-payoff': 'loan',
        'walking-calorie': 'walking-calorie',
        'walk-calorie': 'walking-calorie',
        'calorie-walking': 'walking-calorie',
        'walking-calorie-burn': 'walking-calorie',
        'calorie-burn-walking': 'walking-calorie',
        'running-calorie': 'running-calorie',
        'run-calorie': 'running-calorie',
        'calorie-running': 'running-calorie',
        'run-calorie-burn': 'running-calorie',
        'running-calorie-burn': 'running-calorie',
        'calorie-burn-running': 'running-calorie',
        'jogging-calorie': 'running-calorie',
        'treadmill-calorie': 'treadmill-calorie',
        'treadmill-calorie-burn': 'treadmill-calorie',
        'calorie-treadmill': 'treadmill-calorie',
        'calorie-burn-treadmill': 'treadmill-calorie',
        'treadmill-walking-calorie': 'treadmill-calorie',
        'treadmill-incline-calorie': 'treadmill-calorie',
        'incline-treadmill-calorie': 'treadmill-calorie',
        'incline-calorie': 'treadmill-calorie',
        'incline-walk-calorie': 'treadmill-calorie',
        'incline-walking-calorie': 'treadmill-calorie',
        'biking-calorie': 'cycling-calorie',
        'bike-calorie': 'cycling-calorie',
        'bike-ride-calorie': 'cycling-calorie',
        'bicycle-calorie': 'cycling-calorie',
        'bicycling-calorie': 'cycling-calorie',
        'cycling-calorie': 'cycling-calorie',
        'exercise-bike-calorie': 'cycling-calorie',
        'stationary-bike-calorie': 'cycling-calorie',
        'calorie-biking': 'cycling-calorie',
        'swimming-calorie': 'swimming-calorie',
        'swim-calorie': 'swimming-calorie',
        'rowing-calorie': 'rowing-calorie',
        'rowing-machine-calorie': 'rowing-calorie',
        'hiking-calorie': 'hiking-calorie',
        'hike-calorie': 'hiking-calorie',
        'backpacking-calorie': 'hiking-calorie',
        'stairmaster-calorie': 'stairmaster-calorie',
        'stair-master-calorie': 'stairmaster-calorie',
        'elliptical-calorie': 'elliptical-calorie',
        'jump-rope-calorie': 'jump-rope-calorie',
        'yoga-calorie-burn': 'yoga-calorie',
        'yoga-calorie-burner': 'yoga-calorie',
        'weight-lifting-calorie': 'weightlifting-calorie',
        'weightlifting-calorie': 'weightlifting-calorie',
        'workout-calorie': 'exercise-calorie',
        'cardio-calorie': 'exercise-calorie',
        'activity-calorie': 'exercise-calorie',
        'push-up-calorie': 'exercise-calorie',
        'ruck-calorie': 'rucking-calorie',
        'rucking-calorie': 'rucking-calorie',
        'goruck-calorie': 'rucking-calorie',
        'sauna-calorie': 'sauna-calorie',
        'dog-calorie-by-breed': 'dog-calorie',
        'dog-calorie-by-weight': 'dog-calorie',
        'dog-calorie-needs': 'dog-calorie',
        'dog-food-calorie': 'dog-calorie',
        'senior-dog-calorie': 'dog-calorie',
        'vet-calorie': 'dog-calorie',
        'veterinary-calorie': 'dog-calorie',
        'pet-calorie': 'dog-calorie',
        'cat-food-calorie': 'cat-calorie',
        'cat-calorie': 'cat-calorie',
        'feline-calorie': 'cat-calorie',
        'kitten-calorie': 'cat-calorie',
        'canine-calorie': 'dog-calorie',
        'puppy-calorie': 'dog-calorie',
        'purina-calorie-dog': 'dog-calorie',
        'ffmi': 'ffmi',
        'one-rep-max': '1rm',
        '1-rep-max': '1rm',
        'ideal-body-weight': 'ideal-weight',
        'ideal-running-weight': 'ideal-weight',
        'dog-ideal-weight': 'dog-ideal-weight',
        'weight-loss': 'weight-loss',
        'weight-loss-bmi': 'weight-loss',
        'weight-calorie': 'calorie',
        'desmos-graphing': 'graphing',
        'desmos-scientific': 'scientific',
        'desmos': 'graphing',
        'google': 'online',
        'calculator-soup': 'online',
        'calculator-math': 'online',
        'calculator-app': 'online',
        'options-contract': 'options',
        'options-price': 'options',
        'options-pricing': 'options',
        'options-return': 'options',
        'options-spread': 'options',
        'options-strategy': 'options',
        'options-trading': 'options',
        'options-trading-tax': 'options',
        'options-value': 'options',
        'options-call': 'options',
        'options-premium': 'options',
        'options-trade': 'options',
        'options-probability': 'options',
        'long-options': 'options',
        'put-options': 'options',
        'call-options': 'options',
        'stock-options': 'options',
        'stock-options-profit': 'options',
        'percent': 'percentage',
        'percent-change': 'percentage',
        'percent-decrease': 'percentage',
        'percent-difference': 'percentage',
        'percent-error': 'percentage',
        'percent-growth': 'percentage',
        'percent-increase': 'percentage',
        'percent-off': 'percentage',
        'percentage-change': 'percentage',
        'percentage-decrease': 'percentage',
        'percentage-growth': 'percentage',
        'percentage-of-growth': 'percentage',
        'percentage-increase': 'percentage',
        'company-valuation': 'company-valuation',
        'how-much-is-my-company-worth': 'company-valuation',
        'private-company-valuation': 'company-valuation',
        'company-value': 'company-valuation',
        'saas-company-valuation': 'company-valuation',
        'how-to-value-a-company': 'company-valuation',
        'depreciation-schedule': 'depreciation',
        'double-declining-depreciation': 'depreciation',
        'macrs-depreciation': 'depreciation',
        'straight-line-depreciation': 'depreciation',
        'furniture-depreciation': 'depreciation',
        'equipment-depreciation': 'depreciation',
        'roof-depreciation': 'depreciation',
        'rv-depreciation': 'depreciation',
        'manufactured-home-depreciation': 'depreciation',
        'the-formula-to-compute-annual-straight-line-depreciation-is': 'depreciation',
        'balance-sheet': 'balance-sheet',
        'accounts-payable-on-balance-sheet': 'balance-sheet',
        'capex-from-balance-sheet': 'balance-sheet',
        'common-stock-on-a-balance-sheet': 'balance-sheet',
        'common-stock-on-balance-sheet': 'balance-sheet',
        'current-ratio-from-balance-sheet': 'balance-sheet',
        'dividends-from-balance-sheet': 'balance-sheet',
        'net-income-from-balance-sheet': 'balance-sheet',
        'working-capital-from-balance-sheet': 'balance-sheet',
        'amortization-biweekly': 'amortization',
        'amortization-balloon': 'amortization',
        'amortization-for-land-contract': 'amortization',
        'amortization-schedule-with-balloon-payment': 'amortization',
        'amortization-schedule-excel': 'amortization',
        'amortization-expense': 'amortization',
        'arm-amortization': 'amortization',
        'reverse-mortgage-amortization': 'reverse-mortgage',
        'boat-loan-amortization-schedule': 'boat-loan',
    }
    
    s = re.sub(r'-+', '-', s).strip('-')
    if s in synonyms:
        s = synonyms[s]
    return s if s else slug


def pick_canonical(pages):
    """Pick the best canonical slug from a group."""
    junk_starts = [
        'how-to-', 'what-is-', 'whats-', 'calculate-', 'how-do-you-', 'how-do-i-',
        'best-', 'most-accurate-', 'free-', 'online-', 'my-', 'accurate-', 'use-a-',
        'find-my-', 'figure-', 'i-',
    ]
    brand_starts = [
        'dave-ramsey-', 'bankrate-', 'forbes-', 'dollartimes-', 'brett-whissel-',
        'marketbeat-', 'mr-cooper-', 'adp-', 'barchart-', 'cboe-', 'kelley-blue-book-',
        'aarp-', 'cdc-', 'nhs-', 'nih-', 'nhlbi-', 'webmd-', 'mayo-clinic-',
        'harvard-', 'hers-', 'google-', 'bodybuildingcom-', 'bodybuilding-',
        'myfitnesspal-', 'nasm-', 'omni-', 'merck-', 'gym-geek-', 'eric-roberts-',
        'pro-physique-', 'iifym-', 'mia-aesthetics-', 'wegovy-', 'losertown-',
        'katy-hearn-', 'warrior-babe-', 'legion-', 'mind-pump-', 'gains-by-brains-',
        'pet-alliance-', 'ti-84-',
        # restaurants
        'chipotle-', 'starbucks-', 'mcdonalds-', 'subway-', 'taco-bell-',
        'dunkin-', 'panera-', 'panda-', 'chick-fil-a-', 'burger-king-',
        'wendys-', 'pizza-hut-', 'popeyes-', 'dominos-', 'kfc-', 'in-n-out-',
        'whataburger-', 'five-guys-', '5-guys-', 'dairy-queen-', 'cava-',
        'qdoba-', 'moes-', 'sheetz-', 'wawa-', 'texas-roadhouse-', 'chilis-',
        'tropical-smoothie-', 'sweetgreen-', 'jimmy-johns-', 'salata-',
        'bibibop-', '7-brew-', 'blaze-pizza-', 'ihop-', 'dutch-bros-', 'canes-',
        'potbelly-', 'hills-', 'purina-',
        # tickers
        'schd-', 'voo-', 'spy-', 'jepi-', 'jepq-', 'agnc-', 'apple-',
        'coca-cola-', 'verizon-', 'shell-', 'vym-', 'msty-', 'tsly-', 'ulty-',
        'qqq-', 'qqqi-', 'realty-income-', 'spyi-',
        # states
        'california-', 'florida-', 'texas-',
        # military
        'army-', 'navy-', 'air-force-', 'usmc-', 'us-navy-', 'naval-', 'military-',
    ]
    
    def score(p):
        slug = p['slug']
        config = json.loads(p['config'])
        n_outputs = len(config.get('outputs', []))
        
        has_junk = any(slug.startswith(x) for x in junk_starts)
        has_brand = any(slug.startswith(x) for x in brand_starts)
        is_clean = not (has_junk or has_brand)
        ends_calc = slug.endswith('-calculator')
        
        return (
            -int(is_clean and ends_calc),
            -int(is_clean),
            -int(ends_calc),
            len(slug),
            -n_outputs,
        )
    return sorted(pages, key=score)[0]


# Preferred canonical overrides: concept → preferred slug
CANONICAL_OVERRIDES = {
    'calorie-deficit': 'calorie-deficit-calculator',
    'mortgage': 'mortgage-calculator',
    'compound-interest': 'compound-interest-calculator',
    'treadmill-calorie': 'treadmill-calorie-calculator',
    'percentage': 'percentage-calculator',
    'calorie-intake': 'calorie-intake-calculator',
    'calorie-surplus': 'calorie-surplus-calculator',
    'home-equity': 'home-equity-loan-calculator',
    'restaurant-calorie': 'food-calorie-calculator',
    'restaurant-macro': 'meal-macro-calculator',
    'stock-dividend': 'stock-dividend-calculator',
    'growth-chart': 'growth-chart-calculator',
    'rental-roi': 'rental-property-roi-calculator',
    'heart-rate-zone': 'heart-rate-zone-calculator',
    'sp-500': 'sp-500-calculator',
    'dog-calorie': 'dog-calorie-calculator',
    'cat-calorie': 'cat-calorie-calculator',
    'walking-calorie': 'walking-calorie-calculator',
    'running-calorie': 'running-calorie-calculator',
    'cycling-calorie': 'cycling-calorie-calculator',
    'swimming-calorie': 'swimming-calorie-calculator',
    'exercise-calorie': 'exercise-calorie-calculator',
    'revenue': 'revenue-calculator',
    'balance-sheet': 'balance-sheet-calculator',
    'company-valuation': 'company-valuation-calculator',
    '401k': '401k-calculator',
    'roth-ira': 'roth-ira-calculator',
    'car-loan': 'car-loan-calculator',
    'marketing-roi': 'marketing-roi-calculator',
    'options': 'options-calculator',
    'amortization': 'amortization-calculator',
}

# Group by concept
concepts = defaultdict(list)
for row in rows:
    c = normalize_concept(row['slug'])
    concepts[c].append(row)

# Build keep/delete
keep = []
delete = []
all_slugs = {row['slug'] for row in rows}
for concept, pages in concepts.items():
    # Check for override first
    override_slug = CANONICAL_OVERRIDES.get(concept)
    if override_slug and override_slug in all_slugs:
        canonical_slug = override_slug
    else:
        canonical_slug = pick_canonical(pages)['slug']
    keep.append(canonical_slug)
    for p in pages:
        if p['slug'] != canonical_slug:
            delete.append({
                'slug': p['slug'],
                'canonical': canonical_slug,
                'concept': concept,
            })

delete.sort(key=lambda x: (x['concept'], x['slug']))

print(f"=== DEDUP RESULTS ===")
print(f"Total pages:     {len(rows)}")
print(f"Unique concepts: {len(concepts)}")
print(f"Keep:            {len(keep)}")
print(f"Delete:          {len(delete)}")
print()

concept_counts = defaultdict(int)
for d in delete:
    concept_counts[d['concept']] += 1

print("Top 25 cleanups (concept → canonical):")
for concept, count in sorted(concept_counts.items(), key=lambda x: -x[1])[:25]:
    canonical = [d['canonical'] for d in delete if d['concept'] == concept][0]
    print(f"  {concept:40s} delete {count:3d} → keep {canonical}")

# Category breakdown
keep_set = set(keep)
keep_cats = defaultdict(int)
delete_cats = defaultdict(int)
for row in rows:
    (keep_cats if row['slug'] in keep_set else delete_cats)[row['category']] += 1

print(f"\nBy category:")
for cat in sorted(set(list(keep_cats) + list(delete_cats))):
    k, d = keep_cats.get(cat, 0), delete_cats.get(cat, 0)
    print(f"  {cat:20s} {k:4d} keep / {d:3d} delete")

# Save
output = {
    'stats': {'total': len(rows), 'keep': len(keep), 'delete': len(delete)},
    'keep': sorted(keep),
    'delete': delete,
}
with open('/tmp/gab-ae-delete-list.json', 'w') as f:
    json.dump(output, f, indent=2)

# Generate SQL
slugs_to_delete = [d['slug'] for d in delete]
# Batch into chunks of 50 for SQL
chunks = [slugs_to_delete[i:i+50] for i in range(0, len(slugs_to_delete), 50)]
with open('/tmp/gab-ae-delete.sql', 'w') as f:
    for chunk in chunks:
        quoted = ",".join("'" + s + "'" for s in chunk)
        f.write("DELETE FROM pages WHERE slug IN (" + quoted + ");\n")

print(f"\nSQL written to /tmp/gab-ae-delete.sql ({len(chunks)} statements)")
print(f"\nTo execute: pass --execute flag")

if not DRY_RUN:
    import subprocess
    print("\n🔥 EXECUTING DELETES...")
    for i, chunk in enumerate(chunks):
        quoted = ','.join(f"'{s}'" for s in chunk)
        sql = f"DELETE FROM pages WHERE slug IN ({quoted})"
        result = subprocess.run(
            ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote', '--command', sql],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )
        print(f"  Batch {i+1}/{len(chunks)}: deleted {len(chunk)} pages")
    print(f"\n✅ Done! Deleted {len(slugs_to_delete)} duplicate pages.")
