# SONNET ASSIGNMENT: Build 99 Hub Pages for gab.ae

## Overview
You are building 99 hub pages for gab.ae. Each page lives under one of 10 "Apex" pillar guides. One hub page has already been built as a template: **Flight Hacking & Airline Routing**. You must match its quality, structure, and design system exactly.

## Architecture
- **gab.ae** runs on Cloudflare Worker + D1
- Pages are stored as HTML body content only in the D1 `pages` table
- No `<html>`, `<head>`, or `<body>` tags — the Worker wraps content in a shared layout (nav, footer, dark theme)
- Insert pages using: `python3 scripts/insert-html-page.py <html-file> --slug <slug> --title <title> --description <desc> --category guide`
- Repo: `~/Desktop/gab-ae`
- Save HTML files to: `~/Desktop/gab-ae/pillar-pages/<slug>.html`

## The Template: Flight Hacking & Airline Routing
**File:** `~/Desktop/gab-ae/pillar-pages/flight-hacking-airline-routing.html`
**Live:** https://gab.ae/flight-hacking-airline-routing

### What Makes It Good (copy these patterns):

1. **Breadcrumb navigation** at top: `Apex Guides → [Parent Pillar] → [This Hub]`
   - Links to `/apex-guides` and the parent pillar's slug

2. **Updated badge** with date and emoji

3. **Gradient H1** with subtitle

4. **Sticky sidebar TOC** with anchor links to each section

5. **8-10 major sections** with deep content (~4,000-5,000 words total)

6. **Multiple content types mixed together:**
   - Prose paragraphs (informative, opinionated, no fluff)
   - Data tables with color-coded values
   - Callout boxes (blue for insights, yellow for warnings, green for pro tips)
   - Card grids (for tools, comparisons, resources)
   - Tactic/technique cards with tags (savings %, risk level, difficulty)
   - Interactive calculator or tool (JavaScript at bottom of file)

7. **Alliance/comparison section** — every hub should have some kind of structured comparison (products, services, strategies, programs)

8. **FAQ section** at bottom: 6-8 questions targeting real search queries people would Google

9. **CTA cards** linking to other gab.ae pages where relevant

### Design System (MANDATORY — use these exact values):
```
Background: #0a0a0f (handled by layout)
Card bg: #12121a
Border: rgba(255,255,255,0.08)
Accent: #818cf8
Accent hover: #6366f1
Text main: #e2e8f0
Text muted: #94a3b8
Text dimmed: #64748b
Success: #4ade80 / #10b981
Warning: #fbbf24 / #f59e0b
Danger: #f87171 / #ef4444
Info: #22d3ee / #06b6d4
Border radius: 14-16px for cards
Font: system-ui stack
```

### CSS Rules:
- All CSS in a `<style>` tag at the top of the HTML
- NO `:root` variables (conflicts with layout) — use direct color values
- All class names should be prefixed or unique to avoid collision
- Mobile responsive (1024px and 768px breakpoints)
- Inline styles only for one-off elements

### JavaScript Rules:
- If the page has an interactive tool/calculator, put the `<script>` at the very end
- Use vanilla JS only (no frameworks)
- All functions must be globally scoped (no modules)

## Quality Standards
- **4,000-5,000 words** per hub page
- **Opinionated** — strong recommendations, not wishy-washy "it depends"
- **Real data** — actual numbers, statistics, prices, percentages. Research if needed.
- **No fluff** — every paragraph must teach something or provide a tool
- **Interactive element** — every page should have at least one calculator, quiz, comparison tool, or interactive widget
- **Internal links** — link to other gab.ae pages where relevant (existing tools, other hubs, apex guides)
- **SEO-ready** — FAQ section targets real search queries, title includes year

## The 99 Hub Pages to Build

### Under Apex 01: Software, AI & Digital Infrastructure (`/software-ai-infrastructure-guide-2026`)
1. ai-autonomous-agents — AI & Autonomous Agents
2. website-builders-architecture — Website Builders & Architecture
3. b2b-saas-business-software — B2B SaaS & Business Software
4. developer-tools-infrastructure — Developer Tools & Infrastructure
5. cybersecurity-privacy — Cybersecurity & Privacy
6. consumer-tech-mobile-ecosystems — Consumer Tech & Mobile Ecosystems
7. legal-tech-business-formation — Legal Tech & Business Formation
8. remote-work-productivity — Remote Work & Productivity
9. digital-marketing-seo — Digital Marketing & SEO
10. programmatic-seo-web-traffic — Programmatic SEO & Web Traffic Architecture

### Under Apex 02: Capital Markets & Wealth Architecture (`/capital-markets-wealth-guide-2026`)
11. capital-allocation-market-strategy — Capital Allocation & Market Strategy
12. global-currencies-forex — Global Currencies & Forex
13. fire-movement — The FIRE Movement (Financial Independence, Retire Early)
14. alternative-investments — Alternative Investments
15. hard-assets-precious-metals — Hard Assets, Precious Metals & Vaulting
16. currency-hedging-macro-strategies — Currency Hedging & Macro Strategies
17. offshore-trusts-asset-protection — Offshore Trusts & Asset Protection Structuring
18. family-offices-generational-wealth — Family Offices & Generational Wealth Planning
19. real-estate-investing — Real Estate Investing
20. commercial-real-estate-syndication — Commercial Real Estate Syndication

### Under Apex 03: E-Commerce, Supply Chain & Physical Goods (`/ecommerce-supply-chain-guide-2026`)
21. ecommerce-platforms-marketplaces — E-Commerce Platforms & Marketplaces
22. supply-chain-logistics — Supply Chain & Logistics
23. affiliate-marketing-partner-commerce — Affiliate Marketing & Partner Commerce
24. crowdfunding-patronage-economics — Crowdfunding & Patronage Economics
25. land-banking-strategic-acquisition — Land Banking & Strategic Acquisition

### Under Apex 04: Real Estate, Hospitality & Physical Assets (`/real-estate-hospitality-guide-2026`)
26. property-management-hospitality — Property Management & Hospitality
27. boutique-hotel-inn-management — Boutique Hotel & Inn Management
28. short-term-rental-automation — Short-Term Rental Automation
29. hospitality-tech-booking-engines — Hospitality Tech & Booking Engines
30. real-estate-acquisition-tourism — Real Estate Acquisition for Tourism
31. retreat-centers-wellness-resorts — Retreat Centers & Wellness Resorts
32. agritourism-rural-hospitality — Agritourism & Rural Boutique Hospitality

### Under Apex 05: Education, Knowledge Commerce & Micro-SaaS (`/education-knowledge-commerce-guide-2026`)
33. e-learning-digital-courses — E-Learning & Digital Courses
34. digital-products-elearning-platforms — Digital Products & E-Learning Platforms
35. membership-sites-subscription-models — Membership Sites & Subscription Models
36. cohort-based-course-platforms — Cohort-Based Course Platforms & Frameworks
37. micro-saas-bootstrapping — Micro-SaaS Development & Bootstrapping
38. paid-forums-community-architecture — Paid Forums & Private Community Architecture

### Under Apex 06: Digital Media & The Creator Economy (`/digital-media-creator-economy-guide-2026`)
39. video-production-youtube-strategy — Video Production & YouTube Strategy
40. podcasting-audio-engineering — Podcasting & Audio Engineering
41. digital-journalism-newsletters — Digital Journalism & Newsletter Publishing
42. live-streaming-architecture — Live Streaming Architecture
43. social-media-algorithms-growth — Social Media Algorithms & Growth
44. email-marketing-automation — Email Marketing Automation
45. community-building-masterminds — Community Building & Paid Masterminds
46. creator-sponsorships-brand-deals — Creator Sponsorships & Brand Deals
47. content-automation-ai-generation — Content Automation & AI Generation Tools
48. copyright-ip-digital-licensing — Copyright, IP & Digital Licensing
49. managing-agencies-outsourcing — Managing Agencies & Outsourcing Networks
50. creator-economy-finance-tax — Creator Economy Finance & Tax Strategy
51. media-asset-management — Media Asset Management (MAM)
52. web-analytics-data-attribution — Web Analytics & Data Attribution
53. web-hosting-edge-computing — Web Hosting & Edge Computing

### Under Apex 07: Global Mobility & Geo-Arbitrage (`/global-mobility-geo-arbitrage-guide-2026`)
(#1 — flight-hacking-airline-routing — ALREADY BUILT)
54. global-accommodation-matrix — The Global Accommodation Matrix
55. ground-transport-overland-logistics — Ground Transport & Overland Logistics
56. travel-insurance-risk-management — Travel Insurance & Risk Management
57. visas-residency-citizenship — Visas, Residency & Citizenship
58. cost-of-living-geo-arbitrage — Cost of Living & Geo-Arbitrage
59. remote-work-infrastructure — Remote Work Infrastructure
60. expat-banking-international-finance — Expat Banking & International Finance
61. global-travel-digital-nomadism — Global Travel & Digital Nomadism
62. culinary-gastronomy-tourism — Culinary & Gastronomy Tourism
63. adventure-outdoor-expeditions — Adventure & Outdoor Expeditions
64. wellness-medical-tourism — Wellness & Medical Tourism
65. sustainable-eco-tourism — Sustainable & Eco-Tourism
66. travel-credit-cards-rewards — Travel Credit Cards & Rewards Programs
67. luggage-packing-optimization — Luggage & Packing Optimization
68. travel-photography-videography — Travel Photography & Videography
69. language-learning-cultural-integration — Language Learning & Cultural Integration

### Under Apex 08: Human Optimization, Health & Longevity (`/human-optimization-health-guide-2026`)
70. health-longevity-biohacking — Health, Longevity & Biohacking
71. nootropics-cognitive-enhancers — Nootropics & Cognitive Enhancers
72. habit-tracking-behavior-modification — Habit Tracking & Behavior Modification Tech
73. cognitive-behavioral-frameworks — Cognitive Behavioral Frameworks & Therapy Apps
74. executive-coaching-peak-performance — Executive Coaching & Peak Performance Leadership

### Under Apex 09: Interpersonal Dynamics, Intimacy & Social Architecture (`/interpersonal-dynamics-intimacy-guide-2026`)
75. relationship-coaching-communication — Relationship Coaching & Communication Frameworks
76. alternative-relationship-structures — Alternative Relationship Structures & Ethical Non-Monogamy
77. intimacy-tech-sexual-wellness — Intimacy Tech & Sexual Wellness E-Commerce
78. family-dynamics-conscious-parenting — Family Dynamics & Conscious Parenting

### Under Apex 10: Fine Arts, Design & Creative Expression (`/fine-arts-design-creative-guide-2026`)
79. painting-pigment — Painting & Pigment
80. sculpture-3d-forms — Sculpture & 3D Forms
81. drawing-illustration — Drawing & Illustration
82. fine-art-photography — Fine Art Photography
83. digital-painting-2d-animation — Digital Painting & 2D Animation
84. 3d-modeling-vfx — 3D Modeling & VFX
85. generative-ai-synthetic-art — Generative AI & Synthetic Art
86. ui-ux-web-aesthetics — UI/UX & Web Aesthetics
87. art-investing-global-market — Art Investing & the Global Market
88. business-freelance-art — The Business of Freelance Art
89. digital-ownership-blockchain-art — Digital Ownership & Blockchain Art
90. art-supplies-materials-directory — Art Supplies & Materials Directory
91. graphic-brand-design — Graphic & Brand Design
92. architecture-spatial-design — Architecture & Spatial Design
93. fashion-textile-design — Fashion & Textile Design
94. tattoo-body-art — Tattoo & Body Art
95. art-history-movements — Art History & Movements
96. museums-galleries-exhibitions — Museums, Galleries & Exhibitions
97. film-cinema-videography — Film, Cinema & Videography
98. music-production-sound-design — Music Production & Sound Design

## Workflow
1. Read the template file: `~/Desktop/gab-ae/pillar-pages/flight-hacking-airline-routing.html`
2. For each hub page:
   a. Research the topic (use web search for real data, prices, statistics)
   b. Create the HTML file at `~/Desktop/gab-ae/pillar-pages/<slug>.html`
   c. Insert into D1: `python3 scripts/insert-html-page.py pillar-pages/<slug>.html --slug "<slug>" --title "<Title> | gab.ae" --description "<desc>" --category guide`
   d. Verify it loads: `curl -s -o /dev/null -w "%{http_code}" https://gab.ae/<slug>`
3. Work in batches of 10. After each batch, report what's live.
4. Do NOT ask for confirmation — just build and report.

## Naming Convention
- Slug: kebab-case, no year suffix (e.g., `ai-autonomous-agents`)
- Title: `[Hub Name] — The Complete Playbook | gab.ae`
- Description: 1-2 sentences, keyword-rich
- Category: always `guide`
- File: `pillar-pages/<slug>.html`

## Internal Linking
Link to these existing gab.ae pages where relevant:
- `/apex-guides` — The hub index
- `/api-cost-calculator`
- `/best-free-databases-2026`
- `/best-free-analytics-tools-2026`
- `/best-free-startup-tools-2026`
- `/flight-hacking-airline-routing` — The template page
- `/ecommerce-supply-chain-guide-2026`
- Other hub pages as they get built (cross-link between related hubs)

## What NOT to Do
- Don't use `:root` CSS variables
- Don't use `<html>`, `<head>`, or `<body>` tags
- Don't create thin content (under 3,000 words)
- Don't skip the interactive element (calculator/tool/quiz)
- Don't skip the FAQ section
- Don't use generic stock phrases — be specific and opinionated
- Don't hallucinate statistics — if you can't find real data, say "industry estimates suggest" rather than inventing precise numbers

## Priority Order
Start with high-search-volume pages first:
1. Batch 1 (HIGH priority): #13 fire-movement, #71 nootropics-cognitive-enhancers, #37 micro-saas-bootstrapping, #57 visas-residency-citizenship, #58 cost-of-living-geo-arbitrage, #39 video-production-youtube-strategy, #28 short-term-rental-automation, #5 cybersecurity-privacy, #1 ai-autonomous-agents, #9 digital-marketing-seo
2. Batch 2: #43 social-media-algorithms-growth, #44 email-marketing-automation, #19 real-estate-investing, #40 podcasting-audio-engineering, #70 health-longevity-biohacking, #66 travel-credit-cards-rewards, #2 website-builders-architecture, #85 generative-ai-synthetic-art, #21 ecommerce-platforms-marketplaces, #8 remote-work-productivity
3. Remaining: work through the rest in any order

Now go build. Start with Batch 1. Report after every 10 pages.
