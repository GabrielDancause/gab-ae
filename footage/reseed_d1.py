#!/usr/bin/env python3
"""
Re-seed D1 videos table for sessions where D1 seeding failed during batch.
Uses IA-generated thumbnails and OpenRouter LLM tagging.
Runs locally using the CF OAuth token (wrangler must be logged in).

Usage:
    python3 footage/reseed_d1.py
    python3 footage/reseed_d1.py --sessions action-cam-paris-may3 action-cam-apr30
    python3 footage/reseed_d1.py --dry-run
"""

import argparse, base64, io, json, os, sys, time, urllib.request, urllib.parse
import requests
import internetarchive as ia
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Config ──────────────────────────────────────────────────────────────────
CF_ACCOUNT_ID = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID      = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
IA_ACCESS     = "xmKajI71PPwfRuAb"
IA_SECRET     = "PuQEQQLZYb1k5e3J"
OR_MODEL      = "nvidia/nemotron-nano-12b-v2-vl:free"
OR_KEY        = os.environ.get("OPENROUTER_API_KEY", "")

# Sessions that need re-seeding (add more as needed)
SESSIONS = [
    {
        "name": "2026-05-03 - Action cam Paris",
        "series":    "action-cam-paris-may3",
        "vault_ia_id": "gab-raw-action-cam-paris-may3",
        "context":   "Paris, France, May 2026",
    },
    {
        "name": "2026-04-30 - Square action cam 6 footage",
        "series":    "action-cam-apr30",
        "vault_ia_id": "gab-raw-action-cam-apr30",
        "context":   "Paris, France, April 2026",
    },
    {
        "name": "2026-05-01 - Square action cam 6 footage",
        "series":    "action-cam-may1-sq",
        "vault_ia_id": "gab-raw-action-cam-may1-sq",
        "context":   "Paris, France, May 2026",
    },
    {
        "name": "2026-03-02 - Gab phone",
        "series":    "gab-phone-mar2",
        "vault_ia_id": "gab-raw-phone-mar2",
        "context":   "Paris, France, March 2026",
    },
    {
        "name": "2026-05-10 - Phone, Paris, France",
        "series":    "2026-05-10-phone-paris-france",
        "vault_ia_id": "gab-raw-2026-05-10-phone-paris-france",
        "context":   "Paris, France, May 2026",
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────
def get_cf_token():
    """Read the wrangler OAuth token from disk, refreshing if expired."""
    import tomllib, pathlib, datetime
    p = pathlib.Path.home() / "Library/Preferences/.wrangler/config/default.toml"
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    exp = cfg.get("expiration_time", "")
    try:
        exp_dt = datetime.datetime.fromisoformat(exp.replace("Z", "+00:00"))
        now    = datetime.datetime.now(datetime.timezone.utc)
        if (exp_dt - now).total_seconds() < 120:
            print("  Token expiring soon — refreshing via CF OAuth...")
            cfg = _refresh_cf_token(cfg, p)
    except Exception:
        pass
    return cfg["oauth_token"]


def _refresh_cf_token(cfg, config_path):
    """Refresh the wrangler OAuth token using the refresh_token."""
    import tomllib, pathlib
    refresh_token = cfg.get("refresh_token", "")
    if not refresh_token:
        raise ValueError("No refresh_token in wrangler config")
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": "54d11594-84e4-41aa-b438-e81b8fa78ee7",
    }).encode()
    req = urllib.request.Request(
        "https://dash.cloudflare.com/oauth2/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    if "access_token" not in result:
        raise ValueError(f"Refresh failed: {result}")
    import datetime
    exp = (datetime.datetime.now(datetime.timezone.utc) +
           datetime.timedelta(seconds=result.get("expires_in", 3600))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    cfg = dict(cfg)
    cfg["oauth_token"]      = result["access_token"]
    cfg["expiration_time"]  = exp
    if "refresh_token" in result:
        cfg["refresh_token"] = result["refresh_token"]
    # Write back
    lines = [f'oauth_token = "{cfg["oauth_token"]}"',
             f'expiration_time = "{exp}"',
             f'refresh_token = "{cfg["refresh_token"]}"']
    if "scopes" in cfg:
        scopes = json.dumps(cfg["scopes"])
        lines.append(f"scopes = {scopes}")
    config_path.write_text("\n".join(lines) + "\n")
    print(f"  Token refreshed, expires: {exp}")
    return cfg


def d1_query(sql, token, dry_run=False):
    if dry_run:
        preview = sql[:120].replace('\n', ' ')
        print(f"  [DRY RUN] SQL: {preview}...")
        return True
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = json.dumps({"sql": sql, "params": []}).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        if not result.get("success"):
            print(f"  D1 error: {result.get('errors')}")
            return False
        return True
    except Exception as e:
        print(f"  D1 exception: {e}")
        return False


VIDEO_FORMATS = {"MPEG4", "h.264", "QuickTime", "AVI", "Matroska"}
PHOTO_FORMATS = {"HEIF", "JPEG", "PNG"}
VIDEO_EXTS    = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
PHOTO_EXTS    = {".heic", ".heif", ".jpg", ".jpeg", ".png"}

def ia_list_media_files(vault_ia_id):
    """Return list of (filename, size, media_type) for all media in an IA item."""
    s = ia.get_session({"s3": {"access": IA_ACCESS, "secret": IA_SECRET}})
    item = s.get_item(vault_ia_id)
    files = []
    for f in item.get_files():
        # Skip IA-generated derivatives (.thumbs, _meta.xml, etc.)
        if ".thumbs" in f.name or f.name.endswith(("_meta.xml", "_files.xml", ".sqlite", ".torrent")):
            continue
        ext = ("." + f.name.rsplit(".", 1)[-1]).lower() if "." in f.name else ""
        if f.format in VIDEO_FORMATS or ext in VIDEO_EXTS:
            files.append((f.name, f.size, "video"))
        elif f.format in PHOTO_FORMATS or ext in PHOTO_EXTS:
            files.append((f.name, f.size, "photo"))
    return sorted(files, key=lambda x: x[0])

def ia_list_video_files(vault_ia_id):
    """Return list of (filename, size) for video files in an IA item."""
    return [(n, s) for n, s, t in ia_list_media_files(vault_ia_id) if t == "video"]


def resize_thumb(raw_bytes, max_size=400):
    """Resize a JPEG thumbnail to at most max_size px in each dimension."""
    if not HAS_PIL or not raw_bytes:
        return raw_bytes
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.thumbnail((max_size, max_size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=72)
        return buf.getvalue()
    except Exception:
        return raw_bytes


def ia_get_thumb(vault_ia_id, filename):
    """Download the IA-generated thumbnail for a clip (first frame)."""
    stem = filename.rsplit(".", 1)[0]
    # Try _000001.jpg (1st second), fall back to _000030.jpg (30s)
    for ts in ["_000001.jpg", "_000030.jpg", "_000060.jpg"]:
        thumb_name = f"{vault_ia_id}.thumbs/{stem}{ts}"
        url = f"https://archive.org/download/{vault_ia_id}/{urllib.parse.quote(thumb_name)}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200 and len(r.content) > 1000:
                return resize_thumb(r.content)
        except Exception:
            pass
    return None


def tag_clip_from_thumb(thumb_bytes, context, dry_run=False):
    """Call OpenRouter with a single thumbnail image for metadata tagging."""
    if dry_run:
        return {"location": context, "time_of_day": "day", "mood": "urban",
                "tags": ["Paris", "France", "travel", "urban", "outdoor"]}
    b64 = base64.b64encode(thumb_bytes).decode()
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": f"""Single frame from a video clip filmed in {context}.
Return ONLY valid JSON (no markdown):
{{
  "tags": ["tag1","tag2",...15+ specific tags],
  "location": "specific place if identifiable, else '{context}'",
  "time_of_day": "night/day/golden hour/dusk/etc",
  "mood": "short mood phrase",
  "subjects": ["subjects visible"],
  "activity": "what is happening",
  "weather": "conditions",
  "camera_motion": "static/panning/walking/etc",
  "description": "1-2 sentence description"
}}"""}
    ]
    payload = json.dumps({
        "model": OR_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 600, "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://gab.ae"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        raw = result["choices"][0]["message"].get("content", "").strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  LLM error: {e}")
        return {}


def seed_clip(slug, title, series, thumb_bytes, embed_url, status, meta, token, dry_run=False):
    """Insert a single clip into D1."""
    thumb_b64 = base64.b64encode(thumb_bytes).decode().replace("'", "''") if thumb_bytes else ""
    tags_json = json.dumps(meta or {}).replace("'", "''")
    title_s   = str(title).replace("'", "''")
    series_s  = str(series).replace("'", "''")
    embed_s   = str(embed_url).replace("'", "''")

    sql = (
        f"INSERT OR REPLACE INTO videos (slug, title, series, thumb_b64, video_url, status, tags) "
        f"VALUES ('{slug}', '{title_s}', '{series_s}', '{thumb_b64}', '{embed_s}', '{status}', '{tags_json}');"
    )
    return d1_query(sql, token, dry_run=dry_run)


def update_pipeline_state(pipeline_json, token, dry_run=False):
    """Push pipeline state JSON to D1 pipeline_state table."""
    val = json.dumps(pipeline_json).replace("'", "''")
    sql = f"INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) VALUES ('current', '{val}', datetime('now'));"
    return d1_query(sql, token, dry_run=dry_run)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Re-seed D1 for sessions that failed")
    parser.add_argument("--sessions", nargs="*", help="Series slugs to reseed (default: all in SESSIONS list)")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM tagging, use placeholder titles")
    args = parser.parse_args()

    token = get_cf_token()
    print(f"Using CF OAuth token: {token[:20]}...")

    sessions = SESSIONS
    if args.sessions:
        sessions = [s for s in SESSIONS if s["series"] in args.sessions]
        if not sessions:
            print(f"No matching sessions for: {args.sessions}")
            sys.exit(1)

    total_seeded = 0
    total_failed = 0

    for sess in sessions:
        print(f"\n{'='*60}")
        print(f"Session: {sess['name']}")
        print(f"  vault_ia_id: {sess['vault_ia_id']}")
        print(f"  series:      {sess['series']}")

        print(f"  Listing IA files...")
        all_files = ia_list_media_files(sess["vault_ia_id"])
        print(f"  Found {len(all_files)} file(s): {sum(1 for _,_,t in all_files if t=='video')} video, {sum(1 for _,_,t in all_files if t=='photo')} photo")

        if not all_files:
            print("  No files found — skipping")
            continue

        for i, (fname, size_bytes, media_type) in enumerate(all_files, 1):
            slug = f"{sess['series']}-raw-{i:02d}"
            size_mb = int(size_bytes or 0) // 1024 // 1024
            is_photo = media_type == "photo"

            if is_photo:
                url = f"https://archive.org/download/{sess['vault_ia_id']}/{urllib.parse.quote(fname)}"
            else:
                url = f"https://archive.org/embed/{sess['vault_ia_id']}/{urllib.parse.quote(fname)}?autoplay=1"

            print(f"\n  [{i}/{len(all_files)}] {fname} ({size_mb}MB) [{media_type}]")
            print(f"    slug: {slug}")

            # Get thumbnail
            print(f"    Fetching IA thumbnail...")
            thumb = ia_get_thumb(sess["vault_ia_id"], fname)
            if thumb:
                print(f"    thumb: {len(thumb)//1024}KB")
            else:
                print(f"    thumb: NOT FOUND (will skip thumbnail)")

            # LLM tagging
            base_meta = {"media_type": media_type, "location": sess["context"], "tags": ["Paris", "France", "travel"]}
            if args.skip_llm or not thumb:
                meta = base_meta
                title = f"{sess['series']} — {i:02d}"
            else:
                print(f"    LLM tagging...")
                meta = tag_clip_from_thumb(thumb, sess["context"], dry_run=args.dry_run)
                meta["media_type"] = media_type
                title = meta.get("location", f"{sess['series']} — {i:02d}")[:60]
                if meta:
                    print(f"    → {meta.get('location','?')} · {meta.get('time_of_day','?')} · {meta.get('mood','?')}")

            print(f"    Seeding D1...")
            ok = seed_clip(slug, title, sess["series"], thumb, url, "vault", meta, token, dry_run=args.dry_run)
            print(f"    D1: {'OK' if ok else 'FAILED'}")
            if ok:
                total_seeded += 1
            else:
                total_failed += 1

            if not args.dry_run:
                time.sleep(0.3)  # Rate limit guard

    print(f"\n{'='*60}")
    print(f"Done: {total_seeded} seeded, {total_failed} failed")

    # Update pipeline_state in D1
    import pathlib
    state_file = pathlib.Path("/tmp/pipeline_state.json")  # from VPS - not available locally
    # Just push a note that reseed ran
    if not args.dry_run and total_seeded > 0:
        print("\nNote: pipeline_state D1 table not updated (run sync_pipeline_state.py separately)")


if __name__ == "__main__":
    main()
