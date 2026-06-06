#!/usr/bin/env python3
"""
publish_clip.py — Upload one clip to YouTube + IA, seed D1, return URLs.

Usage:
    python3 footage/publish_clip.py --file "/path/to/clip.MOV" --slug my-slug
    python3 footage/publish_clip.py --file "/path/to/clip.MOV"  # auto-slug from date
"""

import argparse, json, os, re, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CREDENTIALS_FILE = "/Users/gab/Desktop/gab-ae/shorts-uploader/credentials.json"
TOKEN_FILE       = "/Users/gab/Desktop/gab-ae/footage/live_token.json"
CF_ACCOUNT_ID    = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID         = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
IA_ACCESS        = os.environ.get("IA_ACCESS", "Ot0FVHkLiDTD4WDE")
IA_SECRET        = os.environ.get("IA_SECRET", "caXpcbAZF8nfBX1D")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg): print(msg, flush=True)

def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]

def get_youtube():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f: f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def get_cf_token():
    import tomllib
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


# ── Probe ─────────────────────────────────────────────────────────────────────

def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", path],
        capture_output=True, text=True)
    d = json.loads(r.stdout)
    vs = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    fmt = d["format"]
    creation_time = None
    for obj in d["streams"] + [fmt]:
        ct = obj.get("tags", {}).get("creation_time")
        if ct:
            creation_time = ct
            break
    return {
        "duration": float(fmt["duration"]),
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "codec": vs.get("codec_name", ""),
        "bitrate_kbps": int(fmt.get("bit_rate", 0)) // 1000,
        "size_mb": int(fmt.get("size", 0)) // 1024 // 1024,
        "fps": vs.get("r_frame_rate", ""),
        "creation_time": creation_time,
    }


def build_metadata(info, slug, filepath):
    """Generate title + description from probe data."""
    ct = info.get("creation_time", "")
    try:
        dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        date_str = dt.strftime("%B %d, %Y")
        time_str = dt.strftime("%H:%M")
    except Exception:
        date_str = "2026"
        time_str = ""

    w, h = info["width"], info["height"]
    orientation = "vertical" if h > w else "horizontal"
    dur_min = int(info["duration"] // 60)
    dur_sec = int(info["duration"] % 60)
    dur_str = f"{dur_min}m{dur_sec:02d}s" if dur_min else f"{dur_sec}s"

    title = f"{date_str} — iPhone {orientation} clip"
    description = (
        f"Filmed on {date_str}{' at ' + time_str if time_str else ''}.\n"
        f"{w}×{h} · {dur_str} · {info['codec'].upper()} · {info['bitrate_kbps']} kbps\n\n"
        f"Original footage by Gab Dancause.\n"
        f"gab.ae"
    )
    return title, description


# ── YouTube upload ────────────────────────────────────────────────────────────

def upload_youtube(filepath, title, description):
    log(f"\n[YouTube] Uploading: {os.path.basename(filepath)}")
    yt = get_youtube()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["gab", "iphone", "vertical", "footage", "paris"],
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(filepath, chunksize=10*1024*1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  uploading... {pct}%", end="\r", flush=True)

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    log(f"  ✓ YouTube: {url}")
    return video_id, url


# ── IA upload ─────────────────────────────────────────────────────────────────

def upload_ia(filepath, ia_id, title, description):
    log(f"\n[IA] Uploading to: {ia_id}")
    filename = os.path.basename(filepath)
    ia_path = f":internetarchive,access_key_id={IA_ACCESS},secret_access_key={IA_SECRET}:{ia_id}"
    cmd = [
        "rclone", "copyto", filepath, f"{ia_path}/{filename}",
        "--progress",
        "--header-upload", f"x-archive-meta-title:{title}",
        "--header-upload", f"x-archive-meta-description:{description}",
        "--header-upload", "x-archive-meta-mediatype:movies",
        "--header-upload", "x-archive-meta-subject:gab;vertical;iphone;footage",
        "--header-upload", "x-archive-meta-creator:Gab Dancause",
        "--header-upload", "x-archive-meta-licenseurl:http://creativecommons.org/licenses/by/4.0/",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"IA upload failed: {r.stderr[-300:]}")

    download_url = f"https://archive.org/download/{ia_id}/{urllib.parse.quote(filename)}"
    page_url     = f"https://archive.org/details/{ia_id}"
    log(f"  ✓ IA: {page_url}")
    return download_url, page_url


# ── D1 seed ───────────────────────────────────────────────────────────────────

def seed_d1(slug, title, yt_id, ia_download_url, ia_page_url, info, token):
    log(f"\n[D1] Seeding: {slug}")
    tags = json.dumps({
        "media_type": "video",
        "orientation": "vertical" if info["height"] > info["width"] else "horizontal",
        "width": info["width"],
        "height": info["height"],
        "duration_s": int(info["duration"]),
        "codec": info["codec"],
        "source": "iphone",
        "yt_id": yt_id,
        "ia_download": ia_download_url,
        "ia_page": ia_page_url,
    }).replace("'", "''")
    title_s = title.replace("'", "''")
    yt_url  = f"https://www.youtube.com/watch?v={yt_id}".replace("'", "''")
    sql = (
        f"INSERT OR REPLACE INTO videos "
        f"(slug, title, series, thumb_b64, video_url, status, tags) VALUES "
        f"('{slug}', '{title_s}', 'iphone-clips', '', '{yt_url}', 'vault', '{tags}');"
    )
    d1_exec(sql, token)
    log(f"  ✓ D1 entry created")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",  required=True, help="Path to source video file")
    parser.add_argument("--slug",  default="",    help="URL slug (auto-generated if omitted)")
    args = parser.parse_args()

    filepath = args.file
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    log(f"=== publish_clip ===")
    log(f"File: {filepath}")

    # Probe
    log("\n[probe] Reading metadata...")
    info = probe(filepath)
    log(f"  {info['width']}x{info['height']} · {info['duration']:.0f}s · {info['codec']} · {info['bitrate_kbps']} kbps")

    # Slug
    ct = info.get("creation_time", "")
    try:
        dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        date_slug = dt.strftime("%Y-%m-%d")
    except Exception:
        date_slug = "2026"
    slug   = args.slug or slugify(f"iphone-vertical-{date_slug}")
    ia_id  = f"gab-footage-{slug}"
    log(f"  slug: {slug}")
    log(f"  ia_id: {ia_id}")

    title, description = build_metadata(info, slug, filepath)
    log(f"  title: {title}")

    # Upload to YouTube
    yt_id, yt_url = upload_youtube(filepath, title, description)

    # Upload to IA
    ia_download_url, ia_page_url = upload_ia(filepath, ia_id, title, description)

    # Seed D1
    token = get_cf_token()
    seed_d1(slug, title, yt_id, ia_download_url, ia_page_url, info, token)

    # Summary
    log(f"\n{'='*50}")
    log(f"Done!")
    log(f"  YouTube:  {yt_url}")
    log(f"  IA:       {ia_page_url}")
    log(f"  Page:     https://gab.ae/footage/{slug}")
    log(f"  slug:     {slug}")

    # Save for next step (building the page)
    with open("/tmp/published_clip.json", "w") as f:
        json.dump({"slug": slug, "yt_id": yt_id, "ia_download": ia_download_url,
                   "ia_page": ia_page_url, "title": title, "info": info}, f, indent=2)
    log(f"  Saved to /tmp/published_clip.json")


if __name__ == "__main__":
    main()
