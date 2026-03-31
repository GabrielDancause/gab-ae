#!/usr/bin/env python3
"""
Fix gab.ae connection chain: insert pillar pages, update apex index, fix breadcrumbs.
"""
import os, re, subprocess

REPO = os.path.expanduser("~/Desktop/gab-ae")
PILLAR_DIR = os.path.join(REPO, "pillar-pages")

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO)
    return (r.stdout + r.stderr).strip()

# ═══════════════════════════════════════════
# STEP 1: Insert all 9 pillar pages into D1
# ═══════════════════════════════════════════
print("=== STEP 1: Insert 9 pillar pages into D1 ===")

PILLAR_FILES = {
    # file basename → (target slug in D1, title, description)
    "software-ai-infrastructure": (
        "software-ai-infrastructure-guide-2026",
        "Software, AI & Digital Infrastructure — Complete Guide 2026 | gab.ae",
        "The code layer — cloud, AI/ML, DevOps, cybersecurity, and the infrastructure that runs the modern internet."
    ),
    "capital-markets-wealth": (
        "capital-markets-wealth-guide-2026",
        "Capital Markets & Wealth Architecture — Complete Guide 2026 | gab.ae",
        "Markets, investing, crypto, FIRE, and the architecture of generational wealth."
    ),
    # ecommerce-supply-chain-guide-2026 already exists in D1
    "real-estate-hospitality": (
        "real-estate-hospitality-guide-2026",
        "Real Estate, Hospitality & Physical Assets — Complete Guide 2026 | gab.ae",
        "Property, hotels, short-term rentals, and the business of physical spaces."
    ),
    "education-knowledge-commerce": (
        "education-knowledge-commerce-guide-2026",
        "Education, Knowledge Commerce & Micro-SaaS — Complete Guide 2026 | gab.ae",
        "Courses, digital products, micro-SaaS, and the creator-to-educator pipeline."
    ),
    "digital-media-creator-economy": (
        "digital-media-creator-economy-guide-2026",
        "Digital Media & The Creator Economy — Complete Guide 2026 | gab.ae",
        "Video, podcasts, newsletters, brand deals, and building a media empire."
    ),
    "global-mobility-geo-arbitrage": (
        "global-mobility-geo-arbitrage-guide-2026",
        "Global Mobility & Geo-Arbitrage — Complete Guide 2026 | gab.ae",
        "Digital nomad visas, flight hacking, cost-of-living arbitrage, and expat infrastructure."
    ),
    "human-optimization-health": (
        "human-optimization-health-guide-2026",
        "Human Optimization, Health & Longevity — Complete Guide 2026 | gab.ae",
        "Sleep, nutrition, fitness, biohacking, nootropics, and extending healthspan."
    ),
    "interpersonal-dynamics-intimacy": (
        "interpersonal-dynamics-intimacy-guide-2026",
        "Interpersonal Dynamics, Intimacy & Social Architecture — Complete Guide 2026 | gab.ae",
        "Relationships, communication, intimacy, family dynamics, and social capital."
    ),
    "fine-arts-design-creative": (
        "fine-arts-design-creative-guide-2026",
        "Fine Arts, Design & Creative Expression — Complete Guide 2026 | gab.ae",
        "Painting, sculpture, digital art, AI-generated art, design, and the business of creativity."
    ),
}

for file_base, (slug, title, desc) in PILLAR_FILES.items():
    src = os.path.join(PILLAR_DIR, f"{file_base}.html")
    # Need to copy/symlink to the slug-named file for insert script
    dst = os.path.join(PILLAR_DIR, f"{slug}.html")
    if os.path.exists(src):
        # Copy with correct name
        if not os.path.exists(dst):
            os.system(f"cp '{src}' '{dst}'")
        # Also strip any :root CSS variables (conflicts with layout)
        with open(dst) as f:
            content = f.read()
        if ':root' in content:
            # Remove :root blocks
            content = re.sub(r':root\s*\{[^}]*\}', '', content)
            with open(dst, 'w') as f:
                f.write(content)
            print(f"  Stripped :root from {slug}")
        
        result = run(f'python3 scripts/insert-html-page.py pillar-pages/{slug}.html --slug "{slug}" --title "{title}" --description "{desc}" --category guide')
        print(f"  {slug}: {result}")
    else:
        print(f"  ❌ MISSING: {src}")

# ═══════════════════════════════════════════
# STEP 2: Fix hub breadcrumbs that point to wrong pillar slugs
# ═══════════════════════════════════════════
print("\n=== STEP 2: Fix hub breadcrumbs ===")

# Correct pillar slug for each hub
HUB_TO_PILLAR = {
    # Apex 01
    "ai-autonomous-agents": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    "ai-automation-business": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    "cybersecurity-privacy": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    "digital-marketing-seo": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    "personal-productivity-systems": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    "remote-work-career-strategies": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    "saas-marketing-strategies": ("software-ai-infrastructure-guide-2026", "Software, AI & Digital Infrastructure"),
    # Apex 02
    "fire-movement": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "real-estate-investing": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "blockchain-cryptocurrency-investing": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "cryptocurrency-investing-guide": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "cryptocurrency-trading-strategies": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "passive-income-strategies": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "personal-finance-budgeting": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    "venture-capital-fundraising": ("capital-markets-wealth-guide-2026", "Capital Markets & Wealth Architecture"),
    # Apex 03
    "dropshipping-business-model": ("ecommerce-supply-chain-guide-2026", "E-Commerce, Supply Chain & Physical Goods"),
    "ecommerce-business-strategy": ("ecommerce-supply-chain-guide-2026", "E-Commerce, Supply Chain & Physical Goods"),
    "ecommerce-supply-chain": ("ecommerce-supply-chain-guide-2026", "E-Commerce, Supply Chain & Physical Goods"),
    # Apex 04
    "short-term-rental-automation": ("real-estate-hospitality-guide-2026", "Real Estate, Hospitality & Physical Assets"),
    # Apex 05
    "micro-saas-bootstrapping": ("education-knowledge-commerce-guide-2026", "Education, Knowledge Commerce & Micro-SaaS"),
    "business-plan-startup-strategy": ("education-knowledge-commerce-guide-2026", "Education, Knowledge Commerce & Micro-SaaS"),
    "freelancing-consulting-business": ("education-knowledge-commerce-guide-2026", "Education, Knowledge Commerce & Micro-SaaS"),
    "online-course-creation": ("education-knowledge-commerce-guide-2026", "Education, Knowledge Commerce & Micro-SaaS"),
    "online-education-learning": ("education-knowledge-commerce-guide-2026", "Education, Knowledge Commerce & Micro-SaaS"),
    # Apex 06
    "social-media-algorithms-growth": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "video-production-youtube-strategy": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "email-marketing-automation": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "affiliate-marketing-strategies": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "brand-building-strategy": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "content-creation-monetization": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "copywriting-marketing-psychology": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "customer-retention-loyalty": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "influencer-marketing-strategies": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "lead-generation-conversion": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    "social-media-automation": ("digital-media-creator-economy-guide-2026", "Digital Media & The Creator Economy"),
    # Apex 07
    "flight-hacking-airline-routing": ("global-mobility-geo-arbitrage-guide-2026", "Global Mobility & Geo-Arbitrage"),
    "cost-of-living-geo-arbitrage": ("global-mobility-geo-arbitrage-guide-2026", "Global Mobility & Geo-Arbitrage"),
    "visas-residency-citizenship": ("global-mobility-geo-arbitrage-guide-2026", "Global Mobility & Geo-Arbitrage"),
    "digital-nomad-lifestyle": ("global-mobility-geo-arbitrage-guide-2026", "Global Mobility & Geo-Arbitrage"),
    "travel-optimization-strategies": ("global-mobility-geo-arbitrage-guide-2026", "Global Mobility & Geo-Arbitrage"),
    # Apex 08
    "nootropics-cognitive-enhancers": ("human-optimization-health-guide-2026", "Human Optimization, Health & Longevity"),
    "health-wellness-optimization": ("human-optimization-health-guide-2026", "Human Optimization, Health & Longevity"),
}

fixed = 0
for hub_slug, (pillar_slug, pillar_name) in sorted(HUB_TO_PILLAR.items()):
    fpath = os.path.join(PILLAR_DIR, f"{hub_slug}.html")
    if not os.path.exists(fpath):
        continue
    with open(fpath) as f:
        html = f.read()
    
    # Find breadcrumb div content
    bc = re.search(r'(class="[^"]*breadcrumb[^"]*"[^>]*>)(.*?)(</div>)', html, re.DOTALL)
    if not bc:
        continue
    
    old_bc = bc.group(2)
    correct_bc = f'''
      <a href="/apex-guides">Apex Guides</a>
      <span>›</span>
      <a href="/{pillar_slug}">{pillar_name}</a>
      <span>›</span>
      <span style="color: #cbd5e1;">Current</span>
    '''
    
    # Check if breadcrumb already points to the right pillar
    if pillar_slug in old_bc:
        continue  # already correct
    
    new_html = html[:bc.start(2)] + correct_bc + html[bc.end(2):]
    with open(fpath, 'w') as f:
        f.write(new_html)
    fixed += 1
    print(f"  Fixed: {hub_slug} → /{pillar_slug}")

print(f"  Total fixed: {fixed}")

# ═══════════════════════════════════════════
# STEP 3: Update apex-guides.html — Soon→Live for built hubs
# ═══════════════════════════════════════════
print("\n=== STEP 3: Update apex-guides.html ===")

apex_path = os.path.join(PILLAR_DIR, "apex-guides.html")
with open(apex_path) as f:
    apex = f.read()

# Map display names to slugs
DISPLAY_SLUG = {
    "AI & Autonomous Agents": "ai-autonomous-agents",
    "Cybersecurity & Privacy": "cybersecurity-privacy",
    "Digital Marketing & SEO": "digital-marketing-seo",
    "The FIRE Movement": "fire-movement",
    "Real Estate Investing": "real-estate-investing",
    "Short-Term Rental Automation": "short-term-rental-automation",
    "Micro-SaaS Development & Bootstrapping": "micro-saas-bootstrapping",
    "Video Production & YouTube Strategy": "video-production-youtube-strategy",
    "Social Media Algorithms & Growth": "social-media-algorithms-growth",
    "Email Marketing Automation": "email-marketing-automation",
    "Flight Hacking & Airline Routing": "flight-hacking-airline-routing",
    "Visas, Residency & Citizenship": "visas-residency-citizenship",
    "Cost of Living & Geo-Arbitrage": "cost-of-living-geo-arbitrage",
    "Nootropics & Cognitive Enhancers": "nootropics-cognitive-enhancers",
}

# Get all built hub slugs
built_hubs = set()
for f in os.listdir(PILLAR_DIR):
    if f.endswith('.html'):
        s = f[:-5]
        if s not in ('apex-guides', 'best-apex-routers-2026') and '-guide-2026' not in s:
            built_hubs.add(s)

changes = 0
# For each hub item in the apex page, check if it's built
# Pattern: <div class="hub-item"><span class="hub-status status-soon">Soon</span><span class="hub-name">NAME</span></div>
def replace_hub(match):
    global changes
    name = match.group(1)
    # Check if this hub exists as a built page
    slug = DISPLAY_SLUG.get(name)
    if not slug:
        # Try to find by checking built files
        for s in built_hubs:
            # Rough match
            if s.replace('-', ' ').lower() in name.lower() or name.lower().replace('&', 'and').replace(' ', '-').replace(',', '').lower().startswith(s[:10]):
                slug = s
                break
    
    if slug and slug in built_hubs:
        changes += 1
        return f'<div class="hub-item"><span class="hub-status status-live">Live</span><a href="/{slug}" style="color:#cbd5e1;text-decoration:none;"><span class="hub-name">{name}</span></a></div>'
    return match.group(0)

apex = re.sub(
    r'<div class="hub-item"><span class="hub-status status-soon">Soon</span><span class="hub-name">([^<]+)</span></div>',
    replace_hub,
    apex
)

with open(apex_path, 'w') as f:
    f.write(apex)
print(f"  Marked {changes} hubs as Live")

# ═══════════════════════════════════════════
# STEP 4: Re-insert updated apex + hub pages into D1
# ═══════════════════════════════════════════
print("\n=== STEP 4: Re-insert into D1 ===")

# Apex page
result = run('python3 scripts/insert-html-page.py pillar-pages/apex-guides.html --slug "apex-guides" --title "The Apex Guides — 10 Pillars, 100 Hubs | gab.ae" --description "10 pillar guides, 100 specialized hubs." --category guide')
print(f"  apex-guides: {result}")

# Re-insert all hub pages that had breadcrumb fixes
for hub_slug, _ in sorted(HUB_TO_PILLAR.items()):
    fpath = os.path.join(PILLAR_DIR, f"{hub_slug}.html")
    if not os.path.exists(fpath):
        continue
    with open(fpath) as f:
        content = f.read()
    title_m = re.search(r'class="gradient-h1"[^>]*>([^<]+)', content)
    title = title_m.group(1).strip() if title_m else hub_slug.replace('-', ' ').title()
    result = run(f'python3 scripts/insert-html-page.py pillar-pages/{hub_slug}.html --slug "{hub_slug}" --title "{title} | gab.ae" --description "Comprehensive guide." --category guide')
    print(f"  {hub_slug}: {result}")

print("\n✅ Done! Verify:")
print("  https://gab.ae/apex-guides")
print("  https://gab.ae/social-media-algorithms-growth (breadcrumb)")
print("  https://gab.ae/digital-media-creator-economy-guide-2026 (pillar page)")
