#!/usr/bin/env python3
"""
generate_shorts.py — gab.ae to Facebook Reels pipeline

Fetches today's tech + business articles from gab.ae, pulls b-roll from
Pexels, assembles a 30-second 9:16 vertical video with text overlays using
FFmpeg + Pillow. Outputs MP4s to shorts/output/.

Usage:
    python3 shorts/generate_shorts.py
    python3 shorts/generate_shorts.py --limit 3       # generate first 3 only
    python3 shorts/generate_shorts.py --dry-run        # fetch + print, no video
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# ─── Config ──────────────────────────────────────────────────────────────────

PEXELS_API_KEY  = "kJHI1050W5rs7GVlAlIFrIVQvTCl6N1ikhtqMoyYLgh8VW0URGvbxCXL"
SHORTS_FEED_URL = "https://gab.ae/api/shorts-feed"
OUTPUT_DIR      = Path(__file__).parent / "output"

# 9:16 vertical (Instagram / Facebook Reels)
W, H = 1080, 1920

# Fonts
FONT_DIR  = Path("/System/Library/Fonts/Supplemental")
FONT_BOLD = str(FONT_DIR / "Arial Bold.ttf")
FONT_REG  = str(FONT_DIR / "Arial.ttf")
FONT_BLK  = str(FONT_DIR / "Arial Black.ttf")

# Category accent colors matching gab.ae
CAT_COLORS = {
    "tech":        "#8a4020",
    "business":    "#1a5c30",
    "us":          "#c8102e",
    "world":       "#1a5c8a",
    "politics":    "#3a2060",
    "health":      "#8a2020",
    "science":     "#2a1e5e",
    "climate":     "#1a5c30",
    "sports":      "#1a3a5c",
    "travel":      "#1a4a6a",
    "entertainment": "#8a6020",
}

# Pexels search terms per category
CAT_PEXELS = {
    "tech":     "technology digital innovation",
    "business": "financial market business",
    "us":       "american cityscape",
    "world":    "global international city",
    "politics": "government capitol politics",
    "health":   "healthcare medical wellness",
    "science":  "science laboratory research",
    "climate":  "nature environment climate",
    "sports":   "sports athletic competition",
    "travel":   "travel destination landscape",
    "entertainment": "entertainment media performance",
}

# ─── Colour helpers ───────────────────────────────────────────────────────────

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def hex_to_rgba(h, alpha=255):
    return (*hex_to_rgb(h), alpha)

# ─── Text helpers ─────────────────────────────────────────────────────────────

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def wrap_lines(text, font, max_width, draw):
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        w = draw.textlength(test, font=font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_text_block(draw, lines, font, x, y, color, line_spacing=1.25):
    """Draw a list of lines left-aligned at (x, y), return final y."""
    size = font.size if hasattr(font, "size") else 40
    for line in lines:
        draw.text((x, y), line, font=font, fill=color)
        y += int(size * line_spacing)
    return y

def draw_centered_text(draw, text, font, y, color, img_width):
    w = draw.textlength(text, font=font)
    draw.text(((img_width - w) // 2, y), text, font=font, fill=color)

# ─── Slide generators ─────────────────────────────────────────────────────────
# Each returns a PIL Image (RGBA 1080×1920).

SCRIM = (0, 0, 0, 178)   # black @ ~70% for text readability

def _base_slide():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Semi-transparent scrim over full frame
    draw.rectangle([0, 0, W, H], fill=SCRIM)
    return img, draw

def slide_headline(title, category):
    img, draw = _base_slide()
    accent = hex_to_rgba(CAT_COLORS.get(category, "#c8102e"))

    # Category badge
    badge_font = load_font(FONT_BOLD, 38)
    badge_text = category.upper()
    badge_w = int(draw.textlength(badge_text, font=badge_font)) + 40
    draw.rounded_rectangle([80, 200, 80 + badge_w, 260], radius=6, fill=accent)
    draw.text((100, 208), badge_text, font=badge_font, fill=(255, 255, 255, 255))

    # Headline
    h_font = load_font(FONT_BLK, 82)
    lines = wrap_lines(title, h_font, W - 160, draw)
    draw_text_block(draw, lines, h_font, 80, 310, (255, 255, 255, 255), line_spacing=1.2)

    # "Read more at gab.ae" hint at bottom
    hint_font = load_font(FONT_REG, 34)
    draw.text((80, H - 160), "gab.ae", font=hint_font, fill=(255, 255, 255, 140))

    return img

def slide_lede(lede):
    img, draw = _base_slide()

    label_font = load_font(FONT_BOLD, 32)
    draw.text((80, 200), "WHAT HAPPENED", font=label_font, fill=(255, 255, 255, 120))

    # Horizontal rule
    draw.rectangle([80, 250, W - 80, 254], fill=(255, 255, 255, 60))

    lede_font = load_font(FONT_REG, 58)
    lines = wrap_lines(lede, lede_font, W - 160, draw)
    draw_text_block(draw, lines, lede_font, 80, 290, (255, 255, 255, 240), line_spacing=1.35)

    return img

def slide_key_stat(key_stat):
    img, draw = _base_slide()

    # Big number, centered
    val_font  = load_font(FONT_BLK, 200)
    lbl_font  = load_font(FONT_BOLD, 52)

    value = key_stat.get("value", "")
    label = key_stat.get("label", "")

    draw_centered_text(draw, value, val_font, 600, (255, 255, 255, 255), W)
    draw_centered_text(draw, label.upper(), lbl_font, 830, (255, 255, 255, 180), W)

    return img

def slide_takeaways(takeaways):
    img, draw = _base_slide()

    label_font = load_font(FONT_BOLD, 32)
    draw.text((80, 200), "AT A GLANCE", font=label_font, fill=(255, 255, 255, 120))
    draw.rectangle([80, 250, W - 80, 254], fill=(255, 255, 255, 60))

    item_font = load_font(FONT_REG, 54)
    y = 290
    for item in (takeaways or [])[:3]:
        draw.text((80, y), "→", font=item_font, fill=(255, 255, 255, 200))
        lines = wrap_lines(item, item_font, W - 200, draw)
        y = draw_text_block(draw, lines, item_font, 160, y, (255, 255, 255, 240), line_spacing=1.3)
        y += 40

    return img

def slide_pull_quote(pull_quote, category):
    img, draw = _base_slide()
    accent = hex_to_rgba(CAT_COLORS.get(category, "#c8102e"))

    # Left accent bar
    draw.rectangle([60, 200, 72, 700], fill=accent)

    q_font    = load_font(FONT_REG, 60)
    attr_font = load_font(FONT_BOLD, 36)

    lines = wrap_lines(f'"{pull_quote}"', q_font, W - 200, draw)
    draw_text_block(draw, lines, q_font, 100, 220, (255, 255, 255, 240), line_spacing=1.35)

    # Branding
    draw.rectangle([80, H - 220, W - 80, H - 216], fill=(255, 255, 255, 40))
    draw.text((80, H - 200), "gab.ae", font=attr_font, fill=(255, 255, 255, 200))
    draw.text((80, H - 150), "Finance & Tech News", font=load_font(FONT_REG, 30),
              fill=(255, 255, 255, 120))

    return img

# ─── Pexels ───────────────────────────────────────────────────────────────────

def fetch_pexels_video(query, fallback_query="technology news"):
    headers = {"Authorization": PEXELS_API_KEY}
    for q in [query, fallback_query]:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": q, "orientation": "portrait", "size": "medium", "per_page": 5},
                timeout=10,
            )
            r.raise_for_status()
            videos = r.json().get("videos", [])
            if videos:
                # Pick the HD file (or best available)
                for video in videos:
                    files = sorted(
                        video.get("video_files", []),
                        key=lambda f: f.get("width", 0),
                        reverse=True,
                    )
                    for f in files:
                        if f.get("file_type") == "video/mp4":
                            return f["link"]
        except Exception as e:
            print(f"  Pexels error for '{q}': {e}")
    return None

def download_file(url, dest):
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(chunk_size=65536):
            fh.write(chunk)

# ─── FFmpeg assembly ──────────────────────────────────────────────────────────

# Slide timing (seconds): [start, end]
SLIDE_TIMES = [
    (0,  5),   # headline
    (5,  12),  # lede
    (12, 20),  # key stat
    (20, 26),  # takeaways
    (26, 30),  # pull quote
]

MUSIC_DIR = Path(__file__).parent / "music"

def find_music():
    """Return path to the first MP3/M4A found in shorts/music/, or None."""
    if not MUSIC_DIR.exists():
        return None
    for ext in ("*.mp3", "*.m4a", "*.aac", "*.wav"):
        matches = sorted(MUSIC_DIR.glob(ext))
        if matches:
            return matches[0]
    return None

def assemble_video(broll_path, slide_paths, output_path, music_path=None):
    """
    Compose b-roll + 5 timed PNG overlays into a 30s 9:16 MP4.
    Each overlay is full-frame RGBA; FFmpeg uses alpha for blending.
    If music_path is provided, it is mixed in at low volume with fade in/out.
    """
    inputs = ["-stream_loop", "-1", "-i", str(broll_path)]

    # Music is input 1 (if present); slides shift to 2+
    music_idx = None
    if music_path:
        inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_idx = 1

    slide_offset = 2 if music_path else 1
    for p in slide_paths:
        inputs += ["-i", str(p)]

    # Build filter_complex
    filter_parts = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,format=rgba[bg]"
    ]

    prev = "bg"
    for idx, (start, end) in enumerate(SLIDE_TIMES):
        inp  = idx + slide_offset
        curr = f"v{idx}"
        filter_parts.append(
            f"[{prev}][{inp}:v]overlay=0:0:enable='between(t,{start},{end})'[{curr}]"
        )
        prev = curr

    # Audio: fade in 1s, fade out last 2s, keep volume subtle
    if music_idx is not None:
        filter_parts.append(
            f"[{music_idx}:a]volume=0.18,afade=t=in:st=0:d=1,afade=t=out:st=28:d=2[aout]"
        )

    filter_complex = ";\n".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev}]",
    ]

    if music_idx is not None:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]

    cmd += [
        "-t", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("  FFmpeg stderr:", result.stderr[-800:])
        raise RuntimeError(f"FFmpeg failed (code {result.returncode})")

# ─── Main pipeline ────────────────────────────────────────────────────────────

def generate_short(article, tmpdir, music_path=None):
    slug     = article["slug"]
    title    = article["title"]
    lede     = article.get("lede") or title
    takeaways = article.get("takeaways") or []
    key_stat = article.get("key_stat")
    pull_quote = article.get("pull_quote") or lede
    category = article.get("category", "tech")
    tags     = article.get("tags", [])

    output_path = OUTPUT_DIR / f"{slug}.mp4"
    if output_path.exists():
        print(f"  ↩  Skipping {slug} (already exists)")
        return str(output_path)

    print(f"  📰 {title[:60]}")

    # 1. Pexels b-roll
    pexels_query = CAT_PEXELS.get(category, "news technology")
    if tags:
        pexels_query = " ".join(tags[1:3]) + " " + pexels_query
    print(f"  🎬 Pexels: '{pexels_query}'")
    video_url = fetch_pexels_video(pexels_query, CAT_PEXELS.get(category, "technology"))
    if not video_url:
        print(f"  ⚠  No b-roll found, skipping {slug}")
        return None

    broll_path = Path(tmpdir) / f"{slug}_broll.mp4"
    download_file(video_url, broll_path)
    print(f"  ✅ B-roll downloaded")

    # 2. Generate overlay slides
    slides_data = [
        ("headline",  slide_headline(title, category)),
        ("lede",      slide_lede(lede)),
        ("stat",      slide_key_stat(key_stat) if key_stat else slide_lede(takeaways[0] if takeaways else lede)),
        ("takeaways", slide_takeaways(takeaways)),
        ("quote",     slide_pull_quote(pull_quote, category)),
    ]

    slide_paths = []
    for name, img in slides_data:
        p = Path(tmpdir) / f"{slug}_{name}.png"
        img.save(p, "PNG")
        slide_paths.append(p)

    # 3. Assemble
    print(f"  🎞  Assembling video…")
    assemble_video(broll_path, slide_paths, output_path, music_path=music_path)
    print(f"  ✅ Saved → {output_path}")
    return str(output_path)

def main():
    parser = argparse.ArgumentParser(description="Generate gab.ae news shorts")
    parser.add_argument("--limit",    type=int, default=15, help="Max articles to process")
    parser.add_argument("--dry-run",  action="store_true",  help="Fetch and print, no video")
    parser.add_argument("--feed",     default=SHORTS_FEED_URL, help="Override feed URL")
    parser.add_argument("--music",    default=None, help="Path to background music file (MP3/M4A)")
    parser.add_argument("--no-music", action="store_true",  help="Skip background music even if found")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve music track
    music_path = None
    if not args.no_music:
        if args.music:
            music_path = Path(args.music)
        else:
            music_path = find_music()
        if music_path:
            print(f"🎵 Music: {music_path.name}")
        else:
            print("🔇 No music found — drop an MP3 into shorts/music/ to add background audio")
            print("   Free tracks (no attribution): pixabay.com/music  |  freepd.com\n")

    print(f"Fetching shorts feed: {args.feed}")
    try:
        resp = requests.get(args.feed, timeout=15)
        resp.raise_for_status()
        articles = resp.json()
    except Exception as e:
        print(f"Error fetching feed: {e}")
        sys.exit(1)

    if not articles:
        print("No articles returned (might be early in the day — try again after more content is published).")
        sys.exit(0)

    articles = articles[: args.limit]
    print(f"Found {len(articles)} article(s)\n")

    if args.dry_run:
        for a in articles:
            print(f"  [{a['category']}] {a['title']}")
        return

    with tempfile.TemporaryDirectory(prefix="gab_shorts_") as tmpdir:
        results = []
        for i, article in enumerate(articles, 1):
            print(f"[{i}/{len(articles)}] {article['slug']}")
            try:
                out = generate_short(article, tmpdir, music_path=music_path)
                if out:
                    results.append(out)
            except Exception as e:
                print(f"  ❌ Error: {e}")
            print()

    print(f"\nDone. {len(results)}/{len(articles)} video(s) generated in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
