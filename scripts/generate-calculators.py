#!/usr/bin/env python3
"""
Generate calculator page configs by batching keywords into Sonnet sub-agent calls.
Outputs SQL files for D1 import.

Usage: python3 scripts/generate-calculators.py --limit 10 --dry-run
       python3 scripts/generate-calculators.py --limit 10
"""

import json
import subprocess
import sys
import re
import os
import argparse

GAB_AE = os.path.expanduser("~/Desktop/gab-ae")

# Keywords to skip (branded, nonsensical, not buildable as calculators)
SKIP_PATTERNS = [
    r"\bomni calculator\b",       # branded
    r"\bcalculator soup\b",       # branded site
    r"\bschedule 1\b",            # game-specific
    r"\bthe forge\b",             # game-specific
    r"\bdiddy\b",                 # meme
    r"\bchipotle\b",             # branded
    r"\bsnow day\b",             # novelty, can't actually calculate
    r"\bchick.fil.a\b",          # branded
    r"\bmcdonalds\b",            # branded
    r"\bdesmos\b",               # branded
    r"\bsymbolab\b",             # branded
    r"\btrading post calculator\b",  # game
    r"\bblooket\b",              # game
    r"\bgrow a garden\b",        # roblox game
    r"\bapush\b",                # too niche (AP US History)
]


def should_skip(keyword):
    kw = keyword.lower()
    for p in SKIP_PATTERNS:
        if re.search(p, kw):
            return True
    return False


def query_d1(sql):
    """Run SQL on D1 and return results."""
    result = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "gab-ae-prod", "--remote", "--command", sql, "--json"],
        capture_output=True, text=True, cwd=GAB_AE
    )
    if result.returncode != 0:
        print(f"D1 error: {result.stderr}", file=sys.stderr)
        return []
    try:
        data = json.loads(result.stdout)
        return data[0].get('results', [])
    except (json.JSONDecodeError, IndexError, KeyError):
        return []


def generate_config_prompt(keywords_batch):
    """Build a prompt for Sonnet to generate calculator configs."""
    kw_list = "\n".join([
        f"{i+1}. **{kw['keyword']}** (slug: {kw['target_slug']}, volume: {kw['volume']}, KD: {kw['kd']})"
        for i, kw in enumerate(keywords_batch)
    ])
    
    return f"""Generate calculator page configurations for these keywords. Return ONLY a JSON array, no markdown fences, no explanation.

Keywords:
{kw_list}

For each keyword, generate an object with this EXACT structure:
{{
  "slug": "the-slug",
  "title": "SEO Title | gab.ae",
  "description": "Meta description targeting the keyword, 150-160 chars",
  "config": {{
    "inputs": [
      {{
        "id": "inputId",
        "label": "Human Label",
        "type": "number",
        "prefix": "$",
        "suffix": "%",
        "default": 0,
        "min": 0,
        "max": 100,
        "step": 0.01
      }}
    ],
    "outputs": [
      {{
        "id": "outputId",
        "label": "Output Label",
        "format": "currency"
      }}
    ],
    "formula": "var outputId = inputA * inputB / 100",
    "verdicts": [
      {{"max": 50, "label": "Low", "color": "yellow"}},
      {{"max": 100, "label": "High", "color": "green"}}
    ],
    "verdictOutput": "outputId"
  }},
  "content": [
    {{
      "heading": "How to Calculate X",
      "body": "<p>Educational content...</p><p>More detail...</p>"
    }},
    {{
      "heading": "Understanding Y",
      "body": "<p>More content...</p>"
    }}
  ],
  "faqs": [
    {{"q": "Question?", "a": "Answer."}},
    {{"q": "Question?", "a": "Answer."}},
    {{"q": "Question?", "a": "Answer."}}
  ],
  "schema": {{
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "Calculator Name",
    "url": "https://gab.ae/the-slug",
    "description": "Same as meta description",
    "applicationCategory": "FinanceApplication",
    "operatingSystem": "All",
    "offers": {{"@type": "Offer", "price": "0", "priceCurrency": "USD"}}
  }}
}}

RULES:
- formula uses `var` declarations: `var result = input1 * input2`
- formula must reference input IDs and output IDs exactly
- All output IDs must be assigned in the formula
- Input type is always "number" or "preset" (preset has "options" array)
- Output format: "currency", "percent", "number", "integer", "text"
- Verdicts are optional (include when there's a meaningful quality scale)
- verdictOutput must match one of the INPUT ids (what the user controls) not output ids
- Content sections: 2-3 sections, educational, naturally uses the target keyword
- FAQs: 3-5 questions people actually search for
- Schema applicationCategory: FinanceApplication, HealthApplication, EducationalApplication, UtilityApplication as appropriate
- Be accurate with formulas — these are real calculators people will use
- Title format: "Name Calculator | gab.ae" or "Free Name Calculator | gab.ae"

Return ONLY the JSON array. No ```json fences. No text before or after."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10, help='Number of keywords to process')
    parser.add_argument('--batch-size', type=int, default=5, help='Keywords per Sonnet call')
    parser.add_argument('--dry-run', action='store_true', help='Just show what would be built')
    parser.add_argument('--min-volume', type=int, default=1000, help='Minimum search volume')
    parser.add_argument('--max-kd', type=int, default=50, help='Maximum keyword difficulty')
    args = parser.parse_args()
    
    # Query top keywords
    sql = f"""SELECT keyword, volume, kd, priority_score, target_slug 
              FROM keywords 
              WHERE status='new' AND engine='calculator' 
                AND volume >= {args.min_volume} AND kd <= {args.max_kd}
              ORDER BY priority_score DESC 
              LIMIT {args.limit + 20}"""
    
    rows = query_d1(sql)
    
    # Filter out skip patterns
    filtered = [r for r in rows if not should_skip(r['keyword'])][:args.limit]
    
    print(f"Selected {len(filtered)} keywords to build:\n")
    for kw in filtered:
        print(f"  {kw['priority_score']:>8.0f}  {kw['keyword']} (vol:{kw['volume']}, KD:{kw['kd']}) → /{kw['target_slug']}")
    
    if args.dry_run:
        print("\n[dry run — no configs generated]")
        return
    
    # Process in batches
    all_configs = []
    for i in range(0, len(filtered), args.batch_size):
        batch = filtered[i:i + args.batch_size]
        print(f"\n--- Batch {i // args.batch_size + 1} ({len(batch)} keywords) ---")
        
        prompt = generate_config_prompt(batch)
        
        # Write prompt to temp file for the sub-agent
        prompt_file = os.path.join(GAB_AE, f".tmp-prompt-{i}.txt")
        with open(prompt_file, 'w') as f:
            f.write(prompt)
        
        print(f"  Prompt written to {prompt_file}")
        print(f"  Keywords: {', '.join(kw['keyword'] for kw in batch)}")
    
    # Write the combined prompt for manual/automated execution
    all_prompts_file = os.path.join(GAB_AE, "generate-batch.txt")
    with open(all_prompts_file, 'w') as f:
        for i in range(0, len(filtered), args.batch_size):
            batch = filtered[i:i + args.batch_size]
            f.write(f"=== BATCH {i // args.batch_size + 1} ===\n")
            f.write(generate_config_prompt(batch))
            f.write("\n\n")
    
    print(f"\nAll prompts written to {all_prompts_file}")
    print(f"Run these through Sonnet, then use insert-configs.py to load results into D1")


if __name__ == '__main__':
    main()
