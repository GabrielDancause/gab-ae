#!/usr/bin/env python3
"""Add tool cross-links to news articles in D1."""
import json, subprocess, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UPDATES = [
    {
        "slug": "tier-lists-dominate-internet-culture-ranking-everything",
        "section": 3, "para": 1,
        "text": 'Free online tier list makers have made the format accessible to anyone with a browser. No design skills required — just add items, drag them into tiers, and export. Try our <a href="https://eeniemeenie.photonbuilder.com/tier-list-maker" target="_blank">free tier list maker</a> to create and share your own rankings in seconds.'
    },
    {
        "slug": "ancient-geometry-modern-ai-pythagorean-theorem-construction",
        "section": 3, "para": 1,
        "text": 'Educators note that it remains one of the first formulas students learn that has immediate, tangible applications. Understanding a² + b² = c² is the gateway to trigonometry, vector mathematics, and the spatial reasoning that underpins engineering, physics, and computer graphics. Use our <a href="https://sendnerds.photonbuilder.com/pythagorean-theorem-calculator" target="_blank">Pythagorean theorem calculator</a> to solve any right triangle instantly.'
    },
    {
        "slug": "rti-framework-schools-struggling-readers-2026-data",
        "section": 2, "para": 1,
        "text": 'Schools that struggle with RTI implementation almost always cite scheduling as the primary obstacle. When intervention time competes with specials (art, music, PE), student access becomes inconsistent. The most successful programs treat intervention time as non-negotiable — as sacred as math or reading block. Our <a href="https://sendnerds.photonbuilder.com/rti-scheduler" target="_blank">free RTI scheduler</a> helps educators organize intervention groups across time slots without conflicts.'
    },
    {
        "slug": "schd-etf-dividend-growth-2026-income-investors",
        "section": 2, "para": 1,
        "text": "Reddit's r/dividends and r/FIRE communities feature near-daily SCHD discussion threads. The ETF's combination of reasonable current yield, strong growth trajectory, and rock-bottom 0.06% expense ratio makes it a mathematical favorite for long-term income planning. See the <a href=\"https://westmountfundamentals.com/schd-dividend\" target=\"_blank\">complete SCHD dividend history</a> with interactive income calculator."
    },
    {
        "slug": "unicode-combining-characters-glitch-text-security-concerns",
        "section": 3, "para": 1,
        "text": 'The Unicode Consortium itself has acknowledged the tension, noting in technical reports that the standard "cannot prevent all forms of visual spoofing" and that platform-level defenses are the appropriate response, not modifications to the standard. Try our <a href="https://papyruspeople.photonbuilder.com/glitch-text-generator" target="_blank">glitch text generator</a> to create your own zalgo text effects safely.'
    },
    {
        "slug": "ev-torque-converters-obsolete-transmission-industry-adapts",
        "section": 3, "para": 1,
        "text": "Hybrid vehicles also maintain torque converters in many configurations, particularly Toyota's planetary gear system and most plug-in hybrids. The component's decline will be gradual rather than sudden, following the slow retirement of existing ICE vehicles rather than the pace of new EV sales. For a deep dive, see our <a href=\"https://pleasestartplease.photonbuilder.com/torque-converter\" target=\"_blank\">complete torque converter guide</a> with symptom checker and replacement costs."
    }
]

for u in UPDATES:
    slug = u["slug"]
    # Fetch current sections
    result = subprocess.run(
        ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote', '--json',
         '--command', f"SELECT sections FROM news WHERE slug = '{slug}'"],
        capture_output=True, text=True, cwd=BASE
    )
    
    import re
    m = re.search(r'\[.*\]', result.stdout, re.DOTALL)
    if not m:
        print(f"  SKIP {slug}: no data")
        continue
    
    data = json.loads(m.group())
    sections = None
    for item in data:
        if 'results' in item and item['results']:
            sections = json.loads(item['results'][0]['sections'])
            break
    
    if not sections:
        print(f"  SKIP {slug}: no sections")
        continue
    
    # Update the paragraph
    sections[u["section"]]["paragraphs"][u["para"]] = u["text"]
    
    # Write back
    new_sections = json.dumps(sections).replace("'", "''")
    sql = f"UPDATE news SET sections = '{new_sections}' WHERE slug = '{slug}'"
    
    result = subprocess.run(
        ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote', '--command', sql],
        capture_output=True, text=True, cwd=BASE
    )
    
    if 'error' in result.stderr.lower():
        print(f"  ERROR {slug}: {result.stderr[-200:]}")
    else:
        print(f"  ✅ {slug}")

print("\nDone!")
