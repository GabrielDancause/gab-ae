#!/usr/bin/env python3
"""
Seed the D1 `shorts` table with the Paris Slowmo Satie clips.
Usage: python3 footage/seed_shorts.py
Requires: thumbnails in /tmp/clip_thumbs/, wrangler in PATH.
"""

import base64, os, subprocess, tempfile, sys

THUMB_DIR = "/tmp/clip_thumbs"
DB = "gab-ae-prod"

# Clips in order (skipping 13 which is in _aside)
CLIPS = [
    ("01", "01_IMG_5821"), ("02", "02_IMG_5831"), ("03", "03_IMG_5842"),
    ("04", "04_IMG_5825"), ("05", "05_IMG_5827"), ("06", "06_IMG_5840"),
    ("07", "07_IMG_5829"), ("08", "08_IMG_5833"), ("09", "09_IMG_5799"),
    ("10", "10_IMG_5814"), ("11", "11_IMG_5804"), ("12", "12_IMG_5837"),
    # 13 is aside
    ("14", "14_IMG_5806"), ("15", "15_IMG_5816"), ("16", "16_IMG_5845"),
    ("17", "17_IMG_5835"), ("18", "18_IMG_5848"), ("19", "19_IMG_5850"),
    ("20", "20_IMG_5812"), ("21", "21_IMG_5809"), ("22", "22_IMG_5823"),
    ("23", "23_IMG_5819"), ("24", "24_IMG_5817"), ("25", "25_IMG_5801"),
]

def make_sql():
    lines = ["CREATE TABLE IF NOT EXISTS shorts (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, series TEXT, thumb_b64 TEXT, video_url TEXT, published_at TEXT DEFAULT (datetime('now')), status TEXT DEFAULT 'live');"]
    for num, fname in CLIPS:
        slug = f"paris-satie-{num}"
        title = f"Paris · {num}"
        series = "paris-satie"
        thumb_path = os.path.join(THUMB_DIR, f"{fname}.jpg")
        if not os.path.exists(thumb_path):
            print(f"  WARNING: thumb not found for {fname}, skipping", file=sys.stderr)
            continue
        with open(thumb_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        # Escape single quotes in b64 (shouldn't occur but be safe)
        b64 = b64.replace("'", "''")
        lines.append(
            f"INSERT OR REPLACE INTO shorts (slug, title, series, thumb_b64, status) "
            f"VALUES ('{slug}', '{title}', '{series}', '{b64}', 'live');"
        )
        print(f"  {slug} — {len(b64)//1024}KB b64")
    return "\n".join(lines)

def main():
    print("Building SQL...")
    sql = make_sql()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write(sql)
        sql_path = f.name
    print(f"SQL written to {sql_path} ({os.path.getsize(sql_path)//1024}KB)")
    print("Executing against D1 (remote)...")
    result = subprocess.run(
        ["npx", "wrangler", "d1", "execute", DB, "--remote", "--file", sql_path],
        capture_output=False,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    os.unlink(sql_path)
    if result.returncode != 0:
        print("ERROR: wrangler exited with code", result.returncode, file=sys.stderr)
        sys.exit(1)
    print("Done — 24 clips seeded.")

if __name__ == "__main__":
    main()
