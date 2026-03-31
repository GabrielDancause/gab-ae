#!/usr/bin/env python3
"""
Fix the gab.ae Apex Guides → Pillar → Hub connection chain.

Problems found:
1. Pillar pages committed to git but never inserted into D1
2. Apex index page shows "Soon" for all 99 hubs (none linked as Live)
3. Hub breadcrumbs point to pillar slugs that don't match what's in D1
4. Hub items on apex page are plain text, not links

This script:
- Step 1: Insert missing pillar pages into D1
- Step 2: Update apex-guides.html to mark built hubs as "Live" with links
- Step 3: Fix breadcrumbs on hub pages to use correct pillar slugs
- Step 4: Re-insert updated hub pages into D1
"""

import os
import subprocess
import json
import re

REPO = os.path.expanduser("~/Desktop/gab-ae")
PILLAR_DIR = os.path.join(REPO, "pillar-pages")

# ── Mapping: hub slug → (correct parent pillar slug, parent pillar display name) ──
# Based on SONNET-ASSIGNMENT.md structure

PILLAR_MAP = {
    # Apex 01: Software, AI & Digital Infrastructure
    "software-ai-infrastructure-guide-2026": "Software, AI & Digital Infrastructure",
    # Apex 02: Capital Markets & Wealth Architecture
    "capital-markets-wealth-guide-2026": "Capital Markets & Wealth Architecture",
    # Apex 03: E-Commerce, Supply Chain & Physical Goods
    "ecommerce-supply-chain-guide-2026": "E-Commerce, Supply Chain & Physical Goods",
    # Apex 04: Real Estate, Hospitality & Physical Assets
    "real-estate-hospitality-guide-2026": "Real Estate, Hospitality & Physical Assets",
    # Apex 05: Education, Knowledge Commerce & Micro-SaaS
    "education-knowledge-commerce-guide-2026": "Education, Knowledge Commerce & Micro-SaaS",
    # Apex 06: Digital Media & The Creator Economy
    "digital-media-creator-economy-guide-2026": "Digital Media & The Creator Economy",
    # Apex 07: Global Mobility & Geo-Arbitrage
    "global-mobility-geo-arbitrage-guide-2026": "Global Mobility & Geo-Arbitrage",
    # Apex 08: Human Optimization, Health & Longevity
    "human-optimization-health-guide-2026": "Human Optimization, Health & Longevity",
    # Apex 09: Interpersonal Dynamics, Intimacy & Social Architecture
    "interpersonal-dynamics-intimacy-guide-2026": "Interpersonal Dynamics, Intimacy & Social Architecture",
    # Apex 10: Fine Arts, Design & Creative Expression
    "fine-arts-design-creative-guide-2026": "Fine Arts, Design & Creative Expression",
}

# Hub → which pillar it belongs under
HUB_TO_PILLAR = {
    # Apex 01
    "ai-autonomous-agents": "software-ai-infrastructure-guide-2026",
    "website-builders-architecture": "software-ai-infrastructure-guide-2026",
    "b2b-saas-business-software": "software-ai-infrastructure-guide-2026",
    "developer-tools-infrastructure": "software-ai-infrastructure-guide-2026",
    "cybersecurity-privacy": "software-ai-infrastructure-guide-2026",
    "consumer-tech-mobile-ecosystems": "software-ai-infrastructure-guide-2026",
    "legal-tech-business-formation": "software-ai-infrastructure-guide-2026",
    "remote-work-productivity": "software-ai-infrastructure-guide-2026",
    "digital-marketing-seo": "software-ai-infrastructure-guide-2026",
    "programmatic-seo-web-traffic": "software-ai-infrastructure-guide-2026",
    # Apex 02
    "capital-allocation-market-strategy": "capital-markets-wealth-guide-2026",
    "global-currencies-forex": "capital-markets-wealth-guide-2026",
    "fire-movement": "capital-markets-wealth-guide-2026",
    "alternative-investments": "capital-markets-wealth-guide-2026",
    "hard-assets-precious-metals": "capital-markets-wealth-guide-2026",
    "currency-hedging-macro-strategies": "capital-markets-wealth-guide-2026",
    "offshore-trusts-asset-protection": "capital-markets-wealth-guide-2026",
    "family-offices-generational-wealth": "capital-markets-wealth-guide-2026",
    "real-estate-investing": "capital-markets-wealth-guide-2026",
    "commercial-real-estate-syndication": "capital-markets-wealth-guide-2026",
    # Apex 03
    "ecommerce-platforms-marketplaces": "ecommerce-supply-chain-guide-2026",
    "supply-chain-logistics": "ecommerce-supply-chain-guide-2026",
    "affiliate-marketing-partner-commerce": "ecommerce-supply-chain-guide-2026",
    "crowdfunding-patronage-economics": "ecommerce-supply-chain-guide-2026",
    "land-banking-strategic-acquisition": "ecommerce-supply-chain-guide-2026",
    # Apex 04
    "property-management-hospitality": "real-estate-hospitality-guide-2026",
    "boutique-hotel-inn-management": "real-estate-hospitality-guide-2026",
    "short-term-rental-automation": "real-estate-hospitality-guide-2026",
    "hospitality-tech-booking-engines": "real-estate-hospitality-guide-2026",
    "real-estate-acquisition-tourism": "real-estate-hospitality-guide-2026",
    "retreat-centers-wellness-resorts": "real-estate-hospitality-guide-2026",
    "agritourism-rural-hospitality": "real-estate-hospitality-guide-2026",
    # Apex 05
    "e-learning-digital-courses": "education-knowledge-commerce-guide-2026",
    "digital-products-elearning-platforms": "education-knowledge-commerce-guide-2026",
    "membership-sites-subscription-models": "education-knowledge-commerce-guide-2026",
    "cohort-based-course-platforms": "education-knowledge-commerce-guide-2026",
    "micro-saas-bootstrapping": "education-knowledge-commerce-guide-2026",
    "paid-forums-community-architecture": "education-knowledge-commerce-guide-2026",
    # Apex 06
    "video-production-youtube-strategy": "digital-media-creator-economy-guide-2026",
    "podcasting-audio-engineering": "digital-media-creator-economy-guide-2026",
    "digital-journalism-newsletters": "digital-media-creator-economy-guide-2026",
    "live-streaming-architecture": "digital-media-creator-economy-guide-2026",
    "social-media-algorithms-growth": "digital-media-creator-economy-guide-2026",
    "email-marketing-automation": "digital-media-creator-economy-guide-2026",
    "community-building-masterminds": "digital-media-creator-economy-guide-2026",
    "creator-sponsorships-brand-deals": "digital-media-creator-economy-guide-2026",
    "content-automation-ai-generation": "digital-media-creator-economy-guide-2026",
    "copyright-ip-digital-licensing": "digital-media-creator-economy-guide-2026",
    "managing-agencies-outsourcing": "digital-media-creator-economy-guide-2026",
    "creator-economy-finance-tax": "digital-media-creator-economy-guide-2026",
    "media-asset-management": "digital-media-creator-economy-guide-2026",
    "web-analytics-data-attribution": "digital-media-creator-economy-guide-2026",
    "web-hosting-edge-computing": "digital-media-creator-economy-guide-2026",
    # Apex 07
    "flight-hacking-airline-routing": "global-mobility-geo-arbitrage-guide-2026",
    "global-accommodation-matrix": "global-mobility-geo-arbitrage-guide-2026",
    "ground-transport-overland-logistics": "global-mobility-geo-arbitrage-guide-2026",
    "travel-insurance-risk-management": "global-mobility-geo-arbitrage-guide-2026",
    "visas-residency-citizenship": "global-mobility-geo-arbitrage-guide-2026",
    "cost-of-living-geo-arbitrage": "global-mobility-geo-arbitrage-guide-2026",
    "remote-work-infrastructure": "global-mobility-geo-arbitrage-guide-2026",
    "expat-banking-international-finance": "global-mobility-geo-arbitrage-guide-2026",
    "global-travel-digital-nomadism": "global-mobility-geo-arbitrage-guide-2026",
    "culinary-gastronomy-tourism": "global-mobility-geo-arbitrage-guide-2026",
    "adventure-outdoor-expeditions": "global-mobility-geo-arbitrage-guide-2026",
    "wellness-medical-tourism": "global-mobility-geo-arbitrage-guide-2026",
    "sustainable-eco-tourism": "global-mobility-geo-arbitrage-guide-2026",
    "travel-credit-cards-rewards": "global-mobility-geo-arbitrage-guide-2026",
    "luggage-packing-optimization": "global-mobility-geo-arbitrage-guide-2026",
    "travel-photography-videography": "global-mobility-geo-arbitrage-guide-2026",
    "language-learning-cultural-integration": "global-mobility-geo-arbitrage-guide-2026",
    # Apex 08
    "health-longevity-biohacking": "human-optimization-health-guide-2026",
    "nootropics-cognitive-enhancers": "human-optimization-health-guide-2026",
    "habit-tracking-behavior-modification": "human-optimization-health-guide-2026",
    "cognitive-behavioral-frameworks": "human-optimization-health-guide-2026",
    "executive-coaching-peak-performance": "human-optimization-health-guide-2026",
    # Apex 09
    "relationship-coaching-communication": "interpersonal-dynamics-intimacy-guide-2026",
    "alternative-relationship-structures": "interpersonal-dynamics-intimacy-guide-2026",
    "intimacy-tech-sexual-wellness": "interpersonal-dynamics-intimacy-guide-2026",
    "family-dynamics-conscious-parenting": "interpersonal-dynamics-intimacy-guide-2026",
    # Apex 10
    "painting-pigment": "fine-arts-design-creative-guide-2026",
    "sculpture-3d-forms": "fine-arts-design-creative-guide-2026",
    "drawing-illustration": "fine-arts-design-creative-guide-2026",
    "fine-art-photography": "fine-arts-design-creative-guide-2026",
    "digital-painting-2d-animation": "fine-arts-design-creative-guide-2026",
    "3d-modeling-vfx": "fine-arts-design-creative-guide-2026",
    "generative-ai-synthetic-art": "fine-arts-design-creative-guide-2026",
    "ui-ux-web-aesthetics": "fine-arts-design-creative-guide-2026",
    "art-investing-global-market": "fine-arts-design-creative-guide-2026",
    "business-freelance-art": "fine-arts-design-creative-guide-2026",
    "digital-ownership-blockchain-art": "fine-arts-design-creative-guide-2026",
    "art-supplies-materials-directory": "fine-arts-design-creative-guide-2026",
    "graphic-brand-design": "fine-arts-design-creative-guide-2026",
    "architecture-spatial-design": "fine-arts-design-creative-guide-2026",
    "fashion-textile-design": "fine-arts-design-creative-guide-2026",
    "tattoo-body-art": "fine-arts-design-creative-guide-2026",
    "art-history-movements": "fine-arts-design-creative-guide-2026",
    "museums-galleries-exhibitions": "fine-arts-design-creative-guide-2026",
    "film-cinema-videography": "fine-arts-design-creative-guide-2026",
    "music-production-sound-design": "fine-arts-design-creative-guide-2026",
}

# Also map "bonus" hub pages that Sonnet built but aren't in the original 99
# These need to be mapped to a pillar too
BONUS_HUBS = {
    "affiliate-marketing-strategies": "digital-media-creator-economy-guide-2026",
    "ai-automation-business": "software-ai-infrastructure-guide-2026",
    "blockchain-cryptocurrency-investing": "capital-markets-wealth-guide-2026",
    "brand-building-strategy": "digital-media-creator-economy-guide-2026",
    "business-plan-startup-strategy": "education-knowledge-commerce-guide-2026",
    "content-creation-monetization": "digital-media-creator-economy-guide-2026",
    "copywriting-marketing-psychology": "digital-media-creator-economy-guide-2026",
    "cryptocurrency-investing-guide": "capital-markets-wealth-guide-2026",
    "cryptocurrency-trading-strategies": "capital-markets-wealth-guide-2026",
    "customer-retention-loyalty": "digital-media-creator-economy-guide-2026",
    "digital-nomad-lifestyle": "global-mobility-geo-arbitrage-guide-2026",
    "dropshipping-business-model": "ecommerce-supply-chain-guide-2026",
    "ecommerce-business-strategy": "ecommerce-supply-chain-guide-2026",
    "ecommerce-supply-chain": "ecommerce-supply-chain-guide-2026",
    "freelancing-consulting-business": "education-knowledge-commerce-guide-2026",
    "health-wellness-optimization": "human-optimization-health-guide-2026",
    "influencer-marketing-strategies": "digital-media-creator-economy-guide-2026",
    "lead-generation-conversion": "digital-media-creator-economy-guide-2026",
    "online-course-creation": "education-knowledge-commerce-guide-2026",
    "online-education-learning": "education-knowledge-commerce-guide-2026",
    "passive-income-strategies": "capital-markets-wealth-guide-2026",
    "personal-finance-budgeting": "capital-markets-wealth-guide-2026",
    "personal-productivity-systems": "software-ai-infrastructure-guide-2026",
    "remote-work-career-strategies": "software-ai-infrastructure-guide-2026",
    "saas-marketing-strategies": "software-ai-infrastructure-guide-2026",
    "social-media-automation": "digital-media-creator-economy-guide-2026",
    "travel-optimization-strategies": "global-mobility-geo-arbitrage-guide-2026",
    "venture-capital-fundraising": "capital-markets-wealth-guide-2026",
}

# Merge
ALL_HUBS = {**HUB_TO_PILLAR, **BONUS_HUBS}

# Built hub pages (files in pillar-pages/)
built_hubs = set()
for f in os.listdir(PILLAR_DIR):
    if f.endswith('.html'):
        slug = f[:-5]
        if slug not in ('apex-guides', 'best-apex-routers-2026'):
            built_hubs.add(slug)

print(f"Found {len(built_hubs)} built hub pages")

# ── Step 1: Insert missing pillar pages into D1 ──
print("\n=== STEP 1: Insert pillar pages into D1 ===")

# Map pillar file names (from git) to their expected -guide-2026 slugs
PILLAR_FILES = {
    "human-optimization-health": "human-optimization-health-guide-2026",
    "interpersonal-dynamics-intimacy": "interpersonal-dynamics-intimacy-guide-2026",
    "real-estate-hospitality": "real-estate-hospitality-guide-2026",
    "digital-media-creator-economy": "digital-media-creator-economy-guide-2026",
    "education-knowledge-commerce": "education-knowledge-commerce-guide-2026",
}

# Check which pillar HTML files exist
for file_base, target_slug in PILLAR_FILES.items():
    fpath = os.path.join(PILLAR_DIR, f"{file_base}.html")
    if os.path.exists(fpath):
        title = PILLAR_MAP.get(target_slug, file_base.replace('-', ' ').title())
        desc = f"Comprehensive guide to {title.lower()} — strategies, tools, and frameworks."
        print(f"  Inserting: {target_slug} (from {file_base}.html)")
        # Copy file with correct name if needed
        target_path = os.path.join(PILLAR_DIR, f"{target_slug}.html")
        if not os.path.exists(target_path):
            os.system(f"cp '{fpath}' '{target_path}'")
        cmd = f'cd {REPO} && python3 scripts/insert-html-page.py pillar-pages/{target_slug}.html --slug "{target_slug}" --title "{title} — Complete Guide 2026 | gab.ae" --description "{desc}" --category guide'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"    → {result.stdout.strip() or result.stderr.strip()}")
    else:
        print(f"  MISSING file: {fpath} (need to create {target_slug})")

# Also check the ones that need to be created from scratch
MISSING_PILLARS = []
for pillar_slug, pillar_name in PILLAR_MAP.items():
    fpath = os.path.join(PILLAR_DIR, f"{pillar_slug}.html")
    # Also check without -guide-2026
    base = pillar_slug.replace("-guide-2026", "")
    fpath2 = os.path.join(PILLAR_DIR, f"{base}.html")
    if not os.path.exists(fpath) and not os.path.exists(fpath2):
        MISSING_PILLARS.append((pillar_slug, pillar_name))
        print(f"  NEEDS CREATION: {pillar_slug} ({pillar_name})")

# ── Step 2: Fix hub breadcrumbs ──
print("\n=== STEP 2: Fix hub page breadcrumbs ===")

fixed_count = 0
for hub_slug in sorted(built_hubs):
    if hub_slug not in ALL_HUBS:
        print(f"  UNMAPPED: {hub_slug} — skipping (no pillar assignment)")
        continue
    
    pillar_slug = ALL_HUBS[hub_slug]
    pillar_name = PILLAR_MAP.get(pillar_slug, pillar_slug)
    
    fpath = os.path.join(PILLAR_DIR, f"{hub_slug}.html")
    with open(fpath, 'r') as f:
        html = f.read()
    
    # Find and replace the breadcrumb section
    # Pattern: <div class="breadcrumb">...<a href="/apex-guides">...</a>...<span>...</span>...<a href="/...">...</a>...<span>...</span>...
    bc_match = re.search(r'(<div[^>]*class="[^"]*breadcrumb[^"]*"[^>]*>)(.*?)(</div>)', html, re.DOTALL)
    if bc_match:
        new_bc = f'''
      <a href="/apex-guides">Apex Guides</a>
      <span>›</span>
      <a href="/{pillar_slug}">{pillar_name}</a>
      <span>›</span>
      <span style="color: #cbd5e1;">Current</span>
    '''
        new_html = html[:bc_match.start(2)] + new_bc + html[bc_match.end(2):]
        if new_html != html:
            with open(fpath, 'w') as f:
                f.write(new_html)
            fixed_count += 1
    else:
        print(f"  NO BREADCRUMB found in {hub_slug}")

print(f"  Fixed {fixed_count} breadcrumbs")

# ── Step 3: Update apex-guides.html — mark built hubs as Live with links ──
print("\n=== STEP 3: Update apex-guides.html ===")

apex_path = os.path.join(PILLAR_DIR, "apex-guides.html")
with open(apex_path, 'r') as f:
    apex_html = f.read()

# For each built hub, find its "Soon" entry and convert to "Live" with link
changes = 0

# Build a lookup of hub display names to slugs from SONNET-ASSIGNMENT
DISPLAY_TO_SLUG = {
    "AI & Autonomous Agents": "ai-autonomous-agents",
    "Website Builders & Architecture": "website-builders-architecture",
    "B2B SaaS & Business Software": "b2b-saas-business-software",
    "Developer Tools & Infrastructure": "developer-tools-infrastructure",
    "Cybersecurity & Privacy": "cybersecurity-privacy",
    "Consumer Tech & Mobile Ecosystems": "consumer-tech-mobile-ecosystems",
    "Legal Tech & Business Formation": "legal-tech-business-formation",
    "Remote Work & Productivity": "remote-work-productivity",
    "Digital Marketing & SEO": "digital-marketing-seo",
    "Programmatic SEO & Web Traffic Architecture": "programmatic-seo-web-traffic",
    "Capital Allocation & Market Strategy": "capital-allocation-market-strategy",
    "Global Currencies & Forex": "global-currencies-forex",
    "The FIRE Movement": "fire-movement",
    "Alternative Investments": "alternative-investments",
    "Hard Assets, Precious Metals & Vaulting": "hard-assets-precious-metals",
    "Currency Hedging & Macro Strategies": "currency-hedging-macro-strategies",
    "Offshore Trusts & Asset Protection": "offshore-trusts-asset-protection",
    "Family Offices & Generational Wealth": "family-offices-generational-wealth",
    "Real Estate Investing": "real-estate-investing",
    "Commercial Real Estate Syndication": "commercial-real-estate-syndication",
    "E-Commerce Platforms & Marketplaces": "ecommerce-platforms-marketplaces",
    "Supply Chain & Logistics": "supply-chain-logistics",
    "Affiliate Marketing & Partner Commerce": "affiliate-marketing-partner-commerce",
    "Crowdfunding & Patronage Economics": "crowdfunding-patronage-economics",
    "Land Banking & Strategic Acquisition": "land-banking-strategic-acquisition",
    "Property Management & Hospitality": "property-management-hospitality",
    "Boutique Hotel & Inn Management": "boutique-hotel-inn-management",
    "Short-Term Rental Automation": "short-term-rental-automation",
    "Hospitality Tech & Booking Engines": "hospitality-tech-booking-engines",
    "Real Estate Acquisition for Tourism": "real-estate-acquisition-tourism",
    "Retreat Centers & Wellness Resorts": "retreat-centers-wellness-resorts",
    "Agritourism & Rural Boutique Hospitality": "agritourism-rural-hospitality",
    "E-Learning & Digital Courses": "e-learning-digital-courses",
    "Digital Products & E-Learning Platforms": "digital-products-elearning-platforms",
    "Membership Sites & Subscription Models": "membership-sites-subscription-models",
    "Cohort-Based Course Platforms": "cohort-based-course-platforms",
    "Micro-SaaS Development & Bootstrapping": "micro-saas-bootstrapping",
    "Paid Forums & Private Community Architecture": "paid-forums-community-architecture",
    "Video Production & YouTube Strategy": "video-production-youtube-strategy",
    "Podcasting & Audio Engineering": "podcasting-audio-engineering",
    "Digital Journalism & Newsletter Publishing": "digital-journalism-newsletters",
    "Live Streaming Architecture": "live-streaming-architecture",
    "Social Media Algorithms & Growth": "social-media-algorithms-growth",
    "Email Marketing Automation": "email-marketing-automation",
    "Community Building & Paid Masterminds": "community-building-masterminds",
    "Creator Sponsorships & Brand Deals": "creator-sponsorships-brand-deals",
    "Content Automation & AI Generation": "content-automation-ai-generation",
    "Copyright, IP & Digital Licensing": "copyright-ip-digital-licensing",
    "Managing Agencies & Outsourcing": "managing-agencies-outsourcing",
    "Creator Economy Finance & Tax Strategy": "creator-economy-finance-tax",
    "Media Asset Management": "media-asset-management",
    "Web Analytics & Data Attribution": "web-analytics-data-attribution",
    "Web Hosting & Edge Computing": "web-hosting-edge-computing",
    "Flight Hacking & Airline Routing": "flight-hacking-airline-routing",
    "The Global Accommodation Matrix": "global-accommodation-matrix",
    "Ground Transport & Overland Logistics": "ground-transport-overland-logistics",
    "Travel Insurance & Risk Management": "travel-insurance-risk-management",
    "Visas, Residency & Citizenship": "visas-residency-citizenship",
    "Cost of Living & Geo-Arbitrage": "cost-of-living-geo-arbitrage",
    "Remote Work Infrastructure": "remote-work-infrastructure",
    "Expat Banking & International Finance": "expat-banking-international-finance",
    "Global Travel & Digital Nomadism": "global-travel-digital-nomadism",
    "Culinary & Gastronomy Tourism": "culinary-gastronomy-tourism",
    "Adventure & Outdoor Expeditions": "adventure-outdoor-expeditions",
    "Wellness & Medical Tourism": "wellness-medical-tourism",
    "Sustainable & Eco-Tourism": "sustainable-eco-tourism",
    "Travel Credit Cards & Rewards": "travel-credit-cards-rewards",
    "Luggage & Packing Optimization": "luggage-packing-optimization",
    "Travel Photography & Videography": "travel-photography-videography",
    "Language Learning & Cultural Integration": "language-learning-cultural-integration",
    "Health, Longevity & Biohacking": "health-longevity-biohacking",
    "Nootropics & Cognitive Enhancers": "nootropics-cognitive-enhancers",
    "Habit Tracking & Behavior Modification": "habit-tracking-behavior-modification",
    "Cognitive Behavioral Frameworks & Therapy Apps": "cognitive-behavioral-frameworks",
    "Executive Coaching & Peak Performance": "executive-coaching-peak-performance",
    "Relationship Coaching & Communication": "relationship-coaching-communication",
    "Alternative Relationship Structures & ENM": "alternative-relationship-structures",
    "Intimacy Tech & Sexual Wellness": "intimacy-tech-sexual-wellness",
    "Family Dynamics & Conscious Parenting": "family-dynamics-conscious-parenting",
    "Painting & Pigment": "painting-pigment",
    "Sculpture & 3D Forms": "sculpture-3d-forms",
    "Drawing & Illustration": "drawing-illustration",
    "Fine Art Photography": "fine-art-photography",
    "Digital Painting & 2D Animation": "digital-painting-2d-animation",
    "3D Modeling & VFX": "3d-modeling-vfx",
    "Generative AI & Synthetic Art": "generative-ai-synthetic-art",
    "UI/UX & Web Aesthetics": "ui-ux-web-aesthetics",
    "Art Investing & the Global Market": "art-investing-global-market",
    "The Business of Freelance Art": "business-freelance-art",
    "Digital Ownership & Blockchain Art": "digital-ownership-blockchain-art",
    "Art Supplies & Materials Directory": "art-supplies-materials-directory",
    "Graphic & Brand Design": "graphic-brand-design",
    "Architecture & Spatial Design": "architecture-spatial-design",
    "Fashion & Textile Design": "fashion-textile-design",
    "Tattoo & Body Art": "tattoo-body-art",
    "Art History & Movements": "art-history-movements",
    "Museums, Galleries & Exhibitions": "museums-galleries-exhibitions",
    "Film, Cinema & Videography": "film-cinema-videography",
    "Music Production & Sound Design": "music-production-sound-design",
}

for display_name, slug in DISPLAY_TO_SLUG.items():
    if slug in built_hubs:
        # Find the "Soon" entry for this hub and convert to "Live" with link
        # Pattern: <div class="hub-item"><span class="hub-status status-soon">Soon</span><span class="hub-name">Display Name</span></div>
        old_pattern = f'<span class="hub-status status-soon">Soon</span><span class="hub-name">{re.escape(display_name)}</span>'
        new_pattern = f'<span class="hub-status status-live">Live</span><a href="/{slug}" style="color:#cbd5e1;text-decoration:none;"><span class="hub-name">{display_name}</span></a>'
        
        if old_pattern in apex_html:
            apex_html = apex_html.replace(old_pattern, new_pattern)
            changes += 1

print(f"  Marked {changes} hubs as Live in apex-guides.html")

# Write updated apex page
with open(apex_path, 'w') as f:
    f.write(apex_html)

# ── Step 4: Re-insert all updated pages into D1 ──
print("\n=== STEP 4: Re-insert updated pages into D1 ===")

# Insert apex-guides
cmd = f'cd {REPO} && python3 scripts/insert-html-page.py pillar-pages/apex-guides.html --slug "apex-guides" --title "The Apex Guides — 10 Pillars, 100 Hubs | gab.ae" --description "10 pillar guides, 100 specialized hubs. A structured knowledge base covering every domain." --category guide'
result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
print(f"  apex-guides: {result.stdout.strip() or result.stderr.strip()}")

# Re-insert all hub pages with fixed breadcrumbs
reinserted = 0
for hub_slug in sorted(built_hubs):
    fpath = os.path.join(PILLAR_DIR, f"{hub_slug}.html")
    if not os.path.exists(fpath):
        continue
    # Get title from the page
    with open(fpath) as f:
        content = f.read()
    title_match = re.search(r'class="gradient-h1"[^>]*>([^<]+)', content)
    title = title_match.group(1).strip() if title_match else hub_slug.replace('-', ' ').title()
    
    cmd = f'cd {REPO} && python3 scripts/insert-html-page.py pillar-pages/{hub_slug}.html --slug "{hub_slug}" --title "{title} — The Complete Playbook | gab.ae" --description "Comprehensive guide to {title.lower()}." --category guide'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    reinserted += 1

print(f"  Re-inserted {reinserted} hub pages")

# ── Summary ──
print("\n=== SUMMARY ===")
print(f"Pillar pages that need creation (no HTML file exists):")
for slug, name in MISSING_PILLARS:
    print(f"  ❌ {slug} — {name}")
print(f"\nHub pages connected: {changes}")
print(f"Breadcrumbs fixed: {fixed_count}")
print(f"Pages re-inserted into D1: {reinserted}")
