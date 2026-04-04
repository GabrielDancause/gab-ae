#!/usr/bin/env python3
"""
Batch rework — regenerate tool pages via OpenRouter.
Reads slugs from D1, calls Gemini via OpenRouter, updates D1 in-place.
"""
import json, os, subprocess, urllib.request, time

OPENROUTER_KEY = os.popen("cd ~/Desktop/gab-ae && npx wrangler secret list 2>/dev/null").read()
# Read key from workspace
with open(os.path.expanduser("~/.openclaw/workspace/.openrouter-key")) as f:
    API_KEY = f.read().strip()

MODEL = "google/gemini-2.5-pro"
GAB_AE = os.path.expanduser("~/Desktop/gab-ae")

# Timer slugs to rebuild as interactive tools
TIMER_SLUGS = [
    "30-minute-timer", "40-minute-timer", "1-hour-timer",
]

# Other tool slugs
TOOL_SLUGS = [
    "word-randomizer",
    "ama-citation-generator",
    "histogram-maker",
]

ALL_SLUGS = TIMER_SLUGS + TOOL_SLUGS

CSS = """<style>
.seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #e2e8f0; }
.seed-page h1 { font-size: 1.75rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; line-height: 1.2; }
.seed-meta { font-size: 0.8rem; color: #64748b; margin-bottom: 2rem; }
.seed-section { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.seed-section h2 { font-size: 1.15rem; font-weight: 700; color: #818cf8; margin-bottom: 0.75rem; }
.seed-section h3 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem; }
.seed-section p { font-size: 0.95rem; line-height: 1.7; color: #94a3b8; margin-bottom: 0.5rem; }
.seed-section ul, .seed-section ol { padding-left: 1.25rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.8; }
.seed-explore { text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #64748b; }
.seed-explore a { color: #818cf8; text-decoration: underline; }
</style>"""

def call_llm(prompt, max_tokens=16384):
    data = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gab.ae",
            "X-Title": "gab.ae batch rework",
        },
    )
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]

def d1_exec(sql):
    cmd = ["npx", "wrangler", "d1", "execute", "gab-ae-prod", "--remote", "--command", sql]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=GAB_AE, timeout=30)
    return result.stdout

def build_timer_prompt(slug, keyword):
    # Extract duration from keyword
    return f"""Create a FULLY FUNCTIONAL {keyword.upper()} for gab.ae.

This must be a beautiful, working interactive countdown timer. Imagine the top 5 Google results for "{keyword}" — basic timers with ads. Beat them.

BUILD:
- Large animated time display (MM:SS or HH:MM:SS), at least 4rem font
- Circular progress ring (SVG) that depletes as time passes — accent color #818cf8
- Start / Pause / Reset buttons with clear states
- Audio alert when timer finishes (use Web Audio API oscillator — no external files)
- Visual flash/pulse animation when complete
- Fullscreen button
- Dark theme matching gab.ae (#0a0a0f background, #818cf8 accent)

BELOW THE TOOL, add:
- Brief section: "About the {keyword}" (2-3 sentences, what it's useful for)
- 3 FAQs specific to this timer duration

Return ONLY raw HTML. Include {CSS} for layout, then the tool UI inside <div class="seed-page">, then <script> at the end with ALL JavaScript.

Make it DELIGHTFUL. Smooth animations. Satisfying button feedback. This should feel premium."""

def build_tool_prompt(slug, keyword):
    return f"""Create a FULLY FUNCTIONAL INTERACTIVE TOOL for "{keyword}" on gab.ae.

Imagine the top 5 Google results for "{keyword}". They probably have thin content, ads, and poor UX. Build something better.

BUILD a working tool that:
- Does exactly what someone searching "{keyword}" wants
- Has instant, polished interaction (no page reloads)
- Includes a copy/export button for output
- Has customization options where relevant
- Dark theme: #0a0a0f background, #818cf8 accent, #e2e8f0 text
- Mobile-friendly

BELOW THE TOOL, add:
- Brief explanation section (what it does, tips)
- 3-5 FAQs about this topic

Return ONLY raw HTML. Include {CSS} for layout, then the tool UI inside <div class="seed-page">, then <script> at the end.

Make it DELIGHTFUL — smooth animations, satisfying interactions."""

def update_page(slug, html, keyword):
    # Escape single quotes for SQL
    html_escaped = html.replace("'", "''")
    title = keyword.title() + " | gab.ae"
    title_escaped = title.replace("'", "''")
    sql = f"UPDATE pages SET html = '{html_escaped}', quality = 'llm-gemini-pro', engine = 'llm-gemini-pro', page_type = 'interactive_tool', updated_at = datetime('now') WHERE slug = '{slug}'"
    d1_exec(sql)

def main():
    total = len(ALL_SLUGS)
    print(f"🔄 Batch rework: {total} pages")
    
    for i, slug in enumerate(ALL_SLUGS):
        keyword = slug.replace("-", " ")
        is_timer = slug in TIMER_SLUGS
        
        print(f"\n[{i+1}/{total}] {'⏱️' if is_timer else '🔧'} {slug}")
        
        try:
            prompt = build_timer_prompt(slug, keyword) if is_timer else build_tool_prompt(slug, keyword)
            html = call_llm(prompt)
            
            # Clean markdown fences
            html = html.strip()
            if html.startswith("```"):
                html = html.split("\n", 1)[1] if "\n" in html else html[3:]
            if html.endswith("```"):
                html = html.rsplit("```", 1)[0]
            html = html.strip()
            
            if len(html) < 500:
                print(f"  ❌ Too short ({len(html)} chars)")
                continue
            
            if "seed-page" not in html and "<div" in html:
                # Wrap in seed-page if missing
                html = f'<div class="seed-page">\n{html}\n</div>'
            
            update_page(slug, html, keyword)
            print(f"  ✅ Updated ({len(html)} chars)")
            
            # Small delay to avoid rate limiting
            time.sleep(2)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue
    
    print(f"\n🎉 Done! {total} pages processed.")

if __name__ == "__main__":
    main()
