#!/usr/bin/env python3
"""
seed_session_d1.py — Seed D1 with IA-backed session files (no YouTube).

Usage:
    python3 footage/seed_session_d1.py
"""

import json, os, subprocess, tomllib, urllib.request, urllib.parse
from pathlib import Path

CF_ACCOUNT_ID = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID      = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
IA_ID         = "gab-raw-meta-glasses-2026-05-29"
SERIES        = "meta-glasses-2026-05-29"

FILES = [
    {"name": "video-31830_singular_display.MOV", "duration_s": 1,   "media_type": "video"},
    {"name": "video-31835_singular_display.MOV", "duration_s": 10,  "media_type": "video"},
    {"name": "video-31842_singular_display.MOV", "duration_s": 85,  "media_type": "video"},
    {"name": "video-31848_singular_display.MOV", "duration_s": 65,  "media_type": "video"},
    {"name": "video-31855_singular_display.MOV", "duration_s": 180, "media_type": "video"},
    {"name": "video-31862_singular_display.MOV", "duration_s": 180, "media_type": "video"},
    {"name": "video-31867_singular_display.MOV", "duration_s": 180, "media_type": "video"},
    {"name": "video-31872_singular_display.MOV", "duration_s": 160, "media_type": "video"},
    {"name": "video-31877_singular_display.MOV", "duration_s": 180, "media_type": "video"},
    {"name": "video-31974_singular_display.MOV", "duration_s": 3,   "media_type": "video"},
    {"name": "video-31979_singular_display.MOV", "duration_s": 25,  "media_type": "video"},
    {"name": "video-31984_singular_display.MOV", "duration_s": 33,  "media_type": "video"},
    {"name": "video-31989_singular_display.MOV", "duration_s": 54,  "media_type": "video"},
    {"name": "od_photo-31775_singular_display_fullPicture.HEIC", "duration_s": 0, "media_type": "photo"},
    {"name": "photo-31827_singular_display_fullPicture.HEIC",    "duration_s": 0, "media_type": "photo"},
    {"name": "photo-31890_singular_display_fullPicture.HEIC",    "duration_s": 0, "media_type": "photo"},
    {"name": "photo-31962_singular_display_fullPicture.HEIC",    "duration_s": 0, "media_type": "photo"},
    {"name": "photo-31968_singular_display_fullPicture.HEIC",    "duration_s": 0, "media_type": "photo"},
]

def get_cf_token():
    p = Path.home() / "Library/Preferences/.wrangler/config/default.toml"
    with open(p, "rb") as f:
        return tomllib.load(f)["oauth_token"]

def d1_exec(sql, token):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    req = urllib.request.Request(url, data=json.dumps({"sql": sql}).encode(),
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    if not result.get("success"):
        raise Exception(f"D1 error: {result.get('errors')}")
    return result

def main():
    token = get_cf_token()
    print(f"Seeding {len(FILES)} entries into D1 (series={SERIES})")

    for f in FILES:
        fname   = f["name"]
        slug    = f"session-{SERIES}-{fname.replace('_', '-').replace('.', '-').lower()}"[:80]
        ia_down = f"https://archive.org/download/{IA_ID}/{urllib.parse.quote(fname)}"
        ia_page = f"https://archive.org/details/{IA_ID}"
        tags = json.dumps({
            "media_type":  f["media_type"],
            "source":      "meta-glasses",
            "duration_s":  f["duration_s"],
            "ia_download": ia_down,
            "ia_page":     ia_page,
            "filename":    fname,
            "noindex":     True,
        }).replace("'", "''")
        title_s = fname.replace("'", "''")
        sql = (
            f"INSERT OR REPLACE INTO videos "
            f"(slug, title, series, thumb_b64, video_url, status, tags) VALUES "
            f"('{slug}', '{title_s}', '{SERIES}', '', '', 'backed_up', '{tags}');"
        )
        d1_exec(sql, token)
        print(f"  ✓ {fname}")

    print(f"\nDone! Session page: https://gab.ae/footage/session/{SERIES}")

if __name__ == "__main__":
    main()
