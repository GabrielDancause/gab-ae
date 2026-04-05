#!/usr/bin/env python3
"""
Import Ahrefs keyword exports into the D1 keywords table.

Usage: python3 scripts/import-keywords.py path/to/keywords.csv [--dry-run]

Handles both CSV (comma) and TSV (tab, UTF-16 from Ahrefs export).
Expected columns: Keyword, Volume, KD, CPC, Traffic potential, Parent topic
Deduplicates by keyword, keeps highest volume version.
Auto-classifies engine type (calculator, interactive_tool, etc.) and category.

Output: Generates SQL INSERT statements and runs them against gab-ae-prod D1.
"""

import csv
import os
import re
import json
import sys
from pathlib import Path

# Paths
RAW_DIR = Path(os.path.expanduser("~/Desktop/photonbuilder/data/seo/ahrefs/raw"))
ALL_KW_DIR = Path(os.path.expanduser("~/Desktop"))
OUTPUT_SQL = Path(os.path.expanduser("~/Desktop/gab-ae/import-keywords.sql"))

# All keywords keyed by lowercase keyword text
keywords = {}

# ── Engine classification rules ──
ENGINE_PATTERNS = {
    "calculator": [
        r"\bcalculator\b", r"\bcalc\b", r"\bcalculate\b", r"\bcompute\b",
    ],
    "converter": [
        r"\bto\b.*\b(converter|conversion)\b", r"\bconvert\b",
        r"\b(km|miles|kg|lbs|celsius|fahrenheit|cups|ml|inches|cm|feet|meters)\s+to\s+",
    ],
    "timer": [
        r"\btimer\b", r"\bcountdown\b", r"\bstopwatch\b",
        r"\b\d+\s*(minute|min|second|sec|hour|hr)\s*timer\b",
    ],
    "chart": [
        r"\bchart\b", r"\btable\b", r"\bperiodic\b",
        r"\bmultiplication\b", r"\bascii\b",
    ],
    "generator": [
        r"\bgenerator\b", r"\bmaker\b", r"\brandom\b", r"\bcreator\b",
    ],
    "checker": [
        r"\bchecker\b", r"\bvalidator\b", r"\btester\b", r"\bverifier\b",
    ],
    "knowledge": [
        r"\bwhat is\b", r"\bwhat are\b", r"\bhow to\b", r"\bwhy do\b",
        r"\bmeaning of\b", r"\bdefinition\b", r"\blist of\b",
    ],
}

# ── Allowed categories (15 total — NO "general" fallback) ──
VALID_CATEGORIES = [
    "finance", "math", "health", "education", "lifestyle", "gaming",
    "construction", "productivity", "science", "food", "tools", "shipping",
    "tech", "auto", "sports",
]

# ── Category classification rules ──
# Order matters: more specific patterns first to avoid mis-classification.
CATEGORY_PATTERNS = {
    "gaming": [
        r"\bgame\b", r"\bgaming\b", r"\btier\s*list\b", r"\bwiki\b",
        r"\bminecraft\b", r"\bfortnite\b", r"\broblox\b", r"\bpokemon\b",
        r"\bpalworld\b", r"\bblox\s*fruit\b", r"\bwordle\b", r"\bdunk\b",
        r"\bedpi\b", r"\bbottleneck\b", r"\bpoint\s*buy\b", r"\bfantasy\s*trade\b",
        r"\bdynasty\s*trade\b", r"\bgrow\s*a\s*garden\b", r"\bthe\s*forge\b",
        r"\bcp\s*calculator\b",  # Combat Power (Pokemon)
    ],
    "food": [
        r"\bchipotle\b", r"\bstarbucks\b", r"\brecipe\b.*\bcalorie\b",
        r"\bfood\b.*\bcalorie\b", r"\bcooking\b", r"\brecipe\b", r"\bkitchen\b",
        r"\bnutrition\b.*\bcalculator\b",
    ],
    "construction": [
        r"\basphalt\b", r"\bboard\s*foot\b", r"\bconcrete\b", r"\bconstruction\b",
        r"\bcubic\s*(feet|yard|ft|yd)\b", r"\bgravel\b", r"\bmulch\b",
        r"\broof\b.*\bpitch\b", r"\bsoil\b", r"\bstair\b", r"\bgear\s*ratio\b",
        r"\blumber\b", r"\bdrywall\b", r"\binsulation\b", r"\bfencing\b",
        r"\bpaint\b.*\bcalc\b", r"\btile\b.*\bcalc\b", r"\bflooring\b",
    ],
    "shipping": [
        r"\bshipping\b", r"\bfreight\b", r"\busps\b", r"\bups\b.*\bship\b",
        r"\bfedex\b", r"\bebay\b.*\bship\b", r"\bmail\b.*\bzip\b",
        r"\bpostage\b", r"\bdelivery\b.*\bcost\b",
    ],
    "auto": [
        r"\btire\b", r"\bcar\b.*\b(mpg|mileage|fuel)\b", r"\bvehicle\b",
        r"\bautomotive\b", r"\bengine\b.*\b(hp|horsepower|cc)\b",
        r"\btowing\b", r"\bgas\s*mileage\b",
    ],
    "productivity": [
        r"\btimesheet\b", r"\btime\s*card\b", r"\btime\s*clock\b",
        r"\bwork\s*hours\b", r"\bhours?\s*calculator\b", r"\btime\s*sheet\b",
        r"\btime\s*duration\b", r"\btime\s*and\s*a\s*half\b",
        r"\btime\s*calculator\b", r"\bovertime\b",
    ],
    "finance": [
        r"\bmortgage\b", r"\bloan\b", r"\btax\b", r"\binterest\b", r"\binvest\b",
        r"\bstock\b", r"\betf\b", r"\bdividend\b", r"\b401k\b", r"\brrsp\b",
        r"\bbudget\b", r"\bsalary\b", r"\btip\b", r"\bgratuity\b", r"\bcredit\b",
        r"\bdebt\b", r"\bsaving\b", r"\bcompound\b", r"\binflation\b", r"\bequity\b",
        r"\bappreci\b", r"\bmoat\b", r"\breturn\b", r"\bbalance.sheet\b",
        r"\brevenue\b", r"\bprofit\b", r"\bcurrency\b", r"\bcrypto\b", r"\bbitcoin\b",
        r"\bpaycheck\b", r"\bpayroll\b", r"\bpaypal\b", r"\bfee\b.*\bcalc\b",
        r"\brefinance\b", r"\bretirement\b", r"\bsocial\s*security\b",
        r"\brmd\b", r"\bcap\s*rate\b", r"\bheloc\b", r"\bamortiz\b",
        r"\bannuity\b", r"\bfire\b.*\bcalc\b", r"\bincome\b", r"\bpay\b.*\bcalc\b",
        r"\bcar\s*payment\b", r"\bhouse\s*payment\b", r"\bmonthly\s*payment\b",
        r"\bmarkup\b", r"\bmargin\b", r"\bdiscount\b", r"\bcpm\b",
        r"\bsip\b.*\bcalc\b", r"\birr\b", r"\bnpv\b", r"\broth\b", r"\bira\b",
        r"\binsurance\b", r"\bschedule\s*1\b", r"\bdepreciation\b",
        r"\bcost\s*of\s*living\b", r"\brent\b.*\bcalc\b", r"\bprorated\b",
    ],
    "health": [
        r"\bbmi\b", r"\bcalorie\b", r"\bweight\b.*\b(loss|calc|gain)\b",
        r"\bheight\b.*\bcalc\b", r"\bbody\s*(fat|mass)\b",
        r"\bpeptide\b", r"\bfitness\b", r"\bexercise\b", r"\bpregnancy\b",
        r"\bovulation\b", r"\bhealth\b", r"\bdiet\b",
        r"\bmacro\b.*\bcalc\b", r"\bprotein\b.*\bcalc\b", r"\bsleep\b",
        r"\btdee\b", r"\bvo2\b", r"\brep\s*max\b", r"\b1rm\b",
        r"\bacft\b", r"\bffmi\b", r"\bheart\s*rate\b",
        r"\bdue\s*date\b", r"\bconception\b", r"\bivf\b", r"\bperiod\b",
        r"\bbac\b.*\bcalc\b", r"\betg\b", r"\babv\b",
        r"\bcreatinine\b", r"\bcrcl\b", r"\ba1c\b", r"\bcalcium\b",
        r"\bpuppy\b.*\bweight\b", r"\blife\s*expectancy\b",
        r"\bpace\b.*\bcalc\b", r"\bsteps\b.*\bmiles\b",
    ],
    "education": [
        r"\bgrade\b", r"\bgpa\b", r"\bexam\b", r"\bfinal\b.*\bgrade\b",
        r"\bstudy\b", r"\bcollege\b", r"\buniversity\b", r"\bschool\b",
        r"\bspelling\b", r"\bgrammar\b", r"\bvocabulary\b", r"\bquiz\b",
        r"\bsat\b.*\bscore\b", r"\bap\b.*\bscore\b", r"\bsemester\b",
    ],
    "math": [
        r"\bmath\b", r"\bmultiplication\b", r"\bcalculus\b",
        r"\balgebra\b", r"\bgeometry\b", r"\btrigonometry\b",
        r"\bfraction\b", r"\bdecimal\b", r"\bpercentage?\b", r"\bpercent\b",
        r"\bequation\b", r"\bmatrix\b", r"\beigen\b", r"\brref\b",
        r"\bslope\b", r"\bderivative\b", r"\bintegral\b", r"\bantiderivative\b",
        r"\blimit\b.*\bcalc\b", r"\blog\b.*\bcalc\b",
        r"\bsquare\s*root\b", r"\bsq\s*ft\b", r"\bsquare\s*foot\b",
        r"\bsurface\s*area\b", r"\bvolume\b.*\bcalc\b", r"\bcircle\b",
        r"\btriangle\b", r"\bcylinder\b", r"\bpythagorean\b",
        r"\bmidpoint\b", r"\bmedian\b", r"\bmean\b.*\bcalc\b",
        r"\bstandard\s*deviation\b", r"\bvariance\b", r"\bz.score\b",
        r"\bp.value\b", r"\bgcf\b", r"\blcm\b", r"\bfactor\b",
        r"\bratio\b", r"\bproportion\b", r"\bsimplif\b",
        r"\bgraphing\b", r"\bscientific\s*calculator\b", r"\bdesmos\b",
        r"\bdistance\b.*\bcalc\b", r"\bconversion\b.*\bcalc\b",
        r"\brounding\b", r"\bremainder\b", r"\bdivision\b",
        r"\bsignificant\s*figures\b", r"\bscientific\s*notation\b",
        r"\bcosine\b", r"\bsine\b", r"\bhypotenuse\b",
        r"\bcross\s*product\b", r"\bdensity\b", r"\bhalf.life\b",
    ],
    "science": [
        r"\bphysics\b", r"\bchemistry\b", r"\bbiology\b", r"\bscien\b",
        r"\bmolecul\b", r"\batom\b", r"\bperiodic\s*table\b",
        r"\blight\b.*\bspeed\b", r"\bgravity\b",
        r"\bdilution\b", r"\bmolarity\b", r"\bheat\s*index\b",
        r"\bwind\s*chill\b", r"\bformula\b",
    ],
    "lifestyle": [
        r"\bage\b.*\bcalc\b", r"\bdate\b.*\bcalc\b", r"\btime\s*zone\b",
        r"\bbirthday\b", r"\bday\s*calculator\b", r"\bdays\s*calculator\b",
        r"\bdog\s*age\b", r"\bdog\s*years\b", r"\bfemale\s*delusion\b",
        r"\bgematria\b", r"\bbirth\s*chart\b", r"\bmoon\s*sign\b",
        r"\brising\s*sign\b", r"\bsaturn\s*return\b", r"\blove\b.*\bcalc\b",
        r"\bsnow\s*day\b", r"\bpool\b.*\bvolume\b", r"\bbra\s*size\b",
        r"\bchronological\b", r"\bastrology\b", r"\bhoroscope\b",
        r"\btravel\b", r"\bnomad\b", r"\bvisa\b", r"\bflight\b",
    ],
    "tech": [
        r"\bjson\b", r"\bhtml\b", r"\bcss\b", r"\bregex\b", r"\bcode\b",
        r"\bprogramming\b", r"\bapi\b", r"\bgithub\b", r"\bpython\b",
        r"\bjavascript\b", r"\blinux\b", r"\bchmod\b", r"\bcron\b",
        r"\bip\b.*\baddress\b", r"\bsubnet\b", r"\bpassword\b", r"\bhash\b",
        r"\bencrypt\b", r"\bbase64\b", r"\bflexbox\b", r"\bgrid\b",
        r"\bgpu\b", r"\bbenchmark\b", r"\bohm\b", r"\bwire\s*size\b",
    ],
    "sports": [
        r"\bsport\b", r"\bfootball\b", r"\bbasketball\b", r"\bbaseball\b",
        r"\bsoccer\b", r"\btennis\b", r"\bgolf\b",
        r"\bnfl\b", r"\bnba\b", r"\bmlb\b", r"\bfifa\b",
        r"\bpace\b.*\b(run|mile|km)\b",
    ],
    "tools": [
        r"\bcalculator\s*(app|online|google|soup)\b",
        r"\bomni\s*calculator\b", r"\bti.84\b",
        r"\bonline\s*calculator\b", r"\bgoogle\s*calculator\b",
    ],
}

# ── Blacklist patterns ──
BLACKLIST_PATTERNS = [
    r"\bporn\b", r"\bxxx\b", r"\bsex\b(?!\s*ed)", r"\bnude\b", r"\badult\s*friend\b",
    r"\bonlyfans\b", r"\bchaturbate\b", r"\bxvideos\b", r"\bpornhub\b",
    r"\bfacebook\b", r"\byoutube\b", r"\binstagram\b", r"\btiktok\b",
    r"\bnetflix\b", r"\bspotify\b", r"\bamazon\b(?!\s*stock)", r"\bgmail\b",
    r"\blogin\b", r"\bsign\s*in\b", r"\bsign\s*up\b", r"\bdownload\b",
    r"\bfree\s*movie\b", r"\bstream\b(?!\s*line)", r"\btorrent\b",
]


def classify_engine(kw):
    """Determine which engine would build this keyword."""
    kw_lower = kw.lower()
    for engine, patterns in ENGINE_PATTERNS.items():
        for p in patterns:
            if re.search(p, kw_lower):
                return engine
    return None


def classify_category(kw):
    """Determine category for this keyword. Never returns 'general'."""
    kw_lower = kw.lower()
    for cat, patterns in CATEGORY_PATTERNS.items():
        for p in patterns:
            if re.search(p, kw_lower):
                return cat
    # Fallback: use broad heuristics instead of "general"
    if any(w in kw_lower for w in ["money", "pay", "cost", "price", "fee", "earn"]):
        return "finance"
    if any(w in kw_lower for w in ["health", "medical", "body", "heart", "blood"]):
        return "health"
    if any(w in kw_lower for w in ["number", "calculate", "formula", "equation"]):
        return "math"
    # Last resort: "lifestyle" as the broadest non-"general" bucket
    return "lifestyle"


def is_blacklisted(kw):
    """Check if keyword should be blacklisted."""
    kw_lower = kw.lower()
    for p in BLACKLIST_PATTERNS:
        if re.search(p, kw_lower):
            return True
    return False


def keyword_to_slug(kw):
    """Convert keyword to URL slug."""
    slug = kw.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:80]


def parse_csv_file(filepath):
    """Parse a standard Ahrefs CSV (comma-separated, UTF-8 or UTF-16)."""
    results = []
    try:
        # Detect encoding
        with open(filepath, 'rb') as f:
            raw = f.read(4)
        
        if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            # UTF-16, treat as TSV
            return parse_tsv_utf16(filepath)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                kw = row.get('Keyword', '').strip()
                if not kw:
                    continue
                try:
                    volume = int(row.get('Volume', '0').replace(',', ''))
                except (ValueError, TypeError):
                    volume = 0
                try:
                    kd = int(row.get('Difficulty', '0'))
                except (ValueError, TypeError):
                    kd = 0
                try:
                    cpc = float(row.get('CPC', '0'))
                except (ValueError, TypeError):
                    cpc = 0.0
                try:
                    tp = int(row.get('Traffic potential', '0').replace(',', ''))
                except (ValueError, TypeError):
                    tp = 0
                parent = row.get('Parent Keyword', '')
                
                results.append({
                    'keyword': kw,
                    'volume': volume,
                    'kd': kd,
                    'cpc': cpc,
                    'traffic_potential': tp,
                    'parent_topic': parent,
                })
    except Exception as e:
        print(f"  Error parsing {filepath.name}: {e}", file=sys.stderr)
    return results


def parse_tsv_utf16(filepath):
    """Parse Ahrefs TSV exports (UTF-16 LE with BOM, tab-separated, quoted)."""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-16') as f:
            content = f.read()
        
        lines = content.strip().split('\n')
        if not lines:
            return results
        
        # Parse header
        header_line = lines[0]
        headers = [h.strip().strip('"') for h in header_line.split('\t')]
        
        for line in lines[1:]:
            fields = [f.strip().strip('"') for f in line.split('\t')]
            if len(fields) < 5:
                continue
            
            row = dict(zip(headers, fields))
            kw = row.get('Keyword', '').strip()
            if not kw:
                continue
            
            try:
                volume = int(row.get('Volume', '0').replace(',', ''))
            except (ValueError, TypeError):
                volume = 0
            try:
                kd = int(row.get('Difficulty', '0'))
            except (ValueError, TypeError):
                kd = 0
            try:
                cpc = float(row.get('CPC', '0'))
            except (ValueError, TypeError):
                cpc = 0.0
            try:
                tp = int(row.get('Traffic potential', '0').replace(',', ''))
            except (ValueError, TypeError):
                tp = 0
            parent = row.get('Parent Keyword', '')
            
            results.append({
                'keyword': kw,
                'volume': volume,
                'kd': kd,
                'cpc': cpc,
                'traffic_potential': tp,
                'parent_topic': parent,
            })
    except Exception as e:
        print(f"  Error parsing {filepath.name}: {e}", file=sys.stderr)
    return results


def main():
    print("=== Ahrefs Keyword Import ===\n")
    
    # 1. Parse all raw CSV files
    csv_files = sorted(RAW_DIR.glob("*.csv"))
    print(f"Found {len(csv_files)} CSV files in {RAW_DIR}")
    
    for f in csv_files:
        rows = parse_csv_file(f)
        for row in rows:
            key = row['keyword'].lower().strip()
            if key in keywords:
                # Keep the one with higher volume
                if row['volume'] > keywords[key]['volume']:
                    keywords[key] = row
            else:
                keywords[key] = row
    
    print(f"After raw CSVs: {len(keywords)} unique keywords")
    
    # 2. Parse all-keywords TSV files
    all_kw_files = sorted(ALL_KW_DIR.glob("google_us_all-keywords_*.csv"))
    print(f"\nFound {len(all_kw_files)} all-keywords files")
    
    for f in all_kw_files:
        rows = parse_tsv_utf16(f)
        print(f"  {f.name}: {len(rows)} rows")
        for row in rows:
            key = row['keyword'].lower().strip()
            if key in keywords:
                if row['volume'] > keywords[key]['volume']:
                    keywords[key] = row
            else:
                keywords[key] = row
    
    print(f"\nTotal unique keywords: {len(keywords)}")
    
    # 3. Classify all keywords
    stats = {
        'total': len(keywords),
        'blacklisted': 0,
        'engines': {},
        'categories': {},
    }
    
    classified = []
    for key, kw in keywords.items():
        keyword_text = kw['keyword']
        
        # Check blacklist
        if is_blacklisted(keyword_text):
            status = 'blacklist'
            skip_reason = 'auto_blacklist'
            stats['blacklisted'] += 1
        else:
            status = 'new'
            skip_reason = None
        
        engine = classify_engine(keyword_text)
        category = classify_category(keyword_text)
        slug = keyword_to_slug(keyword_text)
        priority = kw['volume'] / (kw['kd'] + 1)
        
        if engine:
            stats['engines'][engine] = stats['engines'].get(engine, 0) + 1
        stats['categories'][category] = stats['categories'].get(category, 0) + 1
        
        classified.append({
            **kw,
            'engine': engine,
            'category': category,
            'target_slug': slug,
            'status': status,
            'skip_reason': skip_reason,
            'priority_score': round(priority, 2),
            'classified_by': 'auto',
            'source': 'ahrefs_us_2026-03',
        })
    
    # 4. Print stats
    print(f"\n=== Classification Stats ===")
    print(f"Blacklisted: {stats['blacklisted']}")
    print(f"\nBy engine:")
    for eng, count in sorted(stats['engines'].items(), key=lambda x: -x[1]):
        print(f"  {eng}: {count}")
    print(f"  unclassified: {len(keywords) - sum(stats['engines'].values())}")
    print(f"\nBy category:")
    for cat, count in sorted(stats['categories'].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    
    # 5. Generate SQL
    print(f"\nGenerating SQL...")
    
    # D1 has a 10MB SQL file limit, so we batch
    BATCH_SIZE = 50
    batches = []
    current_batch = []
    
    for kw in classified:
        # Escape single quotes for SQL
        def sq(s):
            if s is None:
                return 'NULL'
            return "'" + str(s).replace("'", "''") + "'"
        
        values = f"({sq(kw['keyword'])}, {kw['volume']}, {kw['kd']}, {kw['cpc']}, {kw['traffic_potential']}, {sq(kw['parent_topic'])}, {sq(kw['engine'])}, {sq(kw['category'])}, {sq(kw['target_slug'])}, {sq(kw['status'])}, {sq(kw['skip_reason'])}, {kw['priority_score']}, {sq(kw['classified_by'])}, datetime('now'), {sq(kw['source'])}, datetime('now'))"
        current_batch.append(values)
        
        if len(current_batch) >= BATCH_SIZE:
            batches.append(current_batch)
            current_batch = []
    
    if current_batch:
        batches.append(current_batch)
    
    # Write SQL files (D1 has limits, split if needed)
    file_num = 0
    rows_per_file = 10000
    current_rows = 0
    
    sql_files = []
    current_sql = []
    
    for batch in batches:
        stmt = "INSERT OR IGNORE INTO keywords (keyword, volume, kd, cpc, traffic_potential, parent_topic, engine, category, target_slug, status, skip_reason, priority_score, classified_by, classified_at, source, created_at) VALUES\n"
        stmt += ",\n".join(batch) + ";"
        current_sql.append(stmt)
        current_rows += len(batch)
        
        if current_rows >= rows_per_file:
            file_num += 1
            outpath = OUTPUT_SQL.parent / f"import-keywords-{file_num:02d}.sql"
            with open(outpath, 'w') as f:
                f.write("\n\n".join(current_sql))
            sql_files.append(outpath)
            print(f"  Wrote {outpath.name} ({current_rows} rows)")
            current_sql = []
            current_rows = 0
    
    if current_sql:
        file_num += 1
        outpath = OUTPUT_SQL.parent / f"import-keywords-{file_num:02d}.sql"
        with open(outpath, 'w') as f:
            f.write("\n\n".join(current_sql))
        sql_files.append(outpath)
        print(f"  Wrote {outpath.name} ({current_rows} rows)")
    
    print(f"\n=== Done ===")
    print(f"Generated {len(sql_files)} SQL files")
    print(f"Total keywords: {len(classified)}")
    
    # Print top 20 by priority score
    top = sorted(classified, key=lambda x: -x['priority_score'])[:20]
    print(f"\nTop 20 keywords by priority (volume/KD):")
    for kw in top:
        eng = kw['engine'] or '?'
        print(f"  {kw['priority_score']:>10.0f}  [{eng:12s}] {kw['keyword']} (vol:{kw['volume']}, KD:{kw['kd']})")


if __name__ == '__main__':
    main()
