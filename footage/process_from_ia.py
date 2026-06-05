#!/usr/bin/env python3
"""
process_from_ia.py — Phase 2: Tag & thumbnail backed_up D1 entries using IA thumbnails.

Queries D1 for status='backed_up', fetches IA-generated thumbnails (no full video download),
sends to LLM for tagging, updates D1 to status='vault'.

Runs on the VPS. Uses /tmp/cf_token.txt for CF auth.

Usage:
    python3 process_from_ia.py
    python3 process_from_ia.py --series 2026-05-10-phone-paris-france
    python3 process_from_ia.py --dry-run
"""

import argparse, base64, io, json, os, sys, time, urllib.request, urllib.parse
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
CF_ACCOUNT_ID = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID      = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
TOKEN_FILE    = Path("/tmp/cf_token.txt")
OR_KEY        = os.environ.get("OPENROUTER_API_KEY", "")
OR_MODEL      = "nvidia/nemotron-nano-12b-v2-vl:free"


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_cf_token():
    permanent = Path("/opt/gab/cf_api_token.txt")
    if permanent.exists():
        return permanent.read_text().strip()
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""


def d1_query(sql, token, dry_run=False):
    if dry_run:
        print(f"  [DRY RUN] {sql[:120].replace(chr(10),' ')}...")
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = json.dumps({"sql": sql}).encode()
    req = urllib.request.Request(url, data=body,
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        if not result.get("success"):
            print(f"  D1 error: {result.get('errors')}")
            return []
        return (result.get("result") or [{}])[0].get("results", [])
    except Exception as e:
        print(f"  D1 exception: {e}")
        return []


def d1_exec(sql, token, dry_run=False):
    if dry_run:
        print(f"  [DRY RUN] {sql[:120].replace(chr(10),' ')}...")
        return True
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = json.dumps({"sql": sql}).encode()
    req = urllib.request.Request(url, data=body,
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        return result.get("success", False)
    except Exception as e:
        print(f"  D1 exception: {e}")
        return False


def resize_jpeg(raw_bytes, max_px=300):
    """Resize JPEG to max_px on longest side, return JPEG bytes."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw_bytes))
        img.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except Exception:
        return raw_bytes


def ia_fetch_thumb(vault_ia_id, filename):
    """Fetch IA auto-generated thumbnail for a file. Returns JPEG bytes or None."""
    stem = filename.rsplit(".", 1)[0]
    # IA names thumbnails as STEM_NNNNNN.jpg — try 1s, 5s, 30s marks
    for ts in ["_000001.jpg", "_000005.jpg", "_000030.jpg"]:
        thumb_name = f"{vault_ia_id}.thumbs/{stem}{ts}"
        url = f"https://archive.org/download/{vault_ia_id}/{urllib.parse.quote(thumb_name)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gab-vault/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) > 2000:  # real image, not error page
                return resize_jpeg(data)
        except Exception:
            pass
    return None


def llm_tag(thumb_bytes, context, dry_run=False):
    """Send thumbnail to OpenRouter, return metadata dict."""
    if dry_run:
        return {"location": context, "time_of_day": "day", "mood": "urban",
                "tags": ["Paris", "France", "travel"]}
    b64 = base64.b64encode(thumb_bytes).decode()
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": f"""Single frame from a video clip filmed in {context}.
Return ONLY valid JSON (no markdown, no trailing commas):
{{
  "tags": ["tag1","tag2",...],
  "location": "specific place if identifiable, else '{context}'",
  "time_of_day": "night/day/golden hour/dusk",
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
        headers={"Authorization": f"Bearer {OR_KEY}",
                 "Content-Type": "application/json",
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


def update_d1_entry(slug, title, thumb_bytes, meta, token, dry_run=False):
    """Update D1 row: set title, thumb_b64, tags, status=vault."""
    thumb_b64 = base64.b64encode(thumb_bytes).decode().replace("'", "''") if thumb_bytes else ""
    tags_json  = json.dumps(meta).replace("'", "''") if meta else "{}"
    title_s    = str(title).replace("'", "''")
    slug_s     = str(slug).replace("'", "''")
    sql = (
        f"UPDATE videos SET "
        f"title='{title_s}', thumb_b64='{thumb_b64}', tags='{tags_json}', status='vault' "
        f"WHERE slug='{slug_s}';"
    )
    return d1_exec(sql, token, dry_run=dry_run)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Phase 2: Tag backed_up entries from IA thumbnails")
    parser.add_argument("--series", help="Only process this series slug")
    parser.add_argument("--reprocess", action="store_true",
                        help="Also pick up vault entries with no thumbnail")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = get_cf_token()
    if not token:
        print("ERROR: no CF token at /tmp/cf_token.txt")
        sys.exit(1)
    print(f"CF token: {token[:16]}...")

    # Fetch entries to process
    if args.reprocess:
        where = "(status='backed_up' OR (status='vault' AND (thumb_b64='' OR thumb_b64 IS NULL)))"
    else:
        where = "status='backed_up'"
    if args.series:
        where += f" AND series='{args.series}'"
    rows = d1_query(f"SELECT slug, title, series, video_url, tags FROM videos WHERE {where} ORDER BY slug;",
                    token)
    if not rows:
        print("No entries found to process.")
        return

    print(f"Found {len(rows)} backed_up entry/entries to process.")

    done = 0
    failed = 0

    for row in rows:
        slug     = row["slug"]
        series   = row["series"]
        video_url = row["video_url"]
        try:
            existing_tags = json.loads(row.get("tags") or "{}")
        except Exception:
            existing_tags = {}

        media_type = existing_tags.get("media_type", "video")
        is_photo   = media_type == "photo"

        # Derive vault_ia_id from video_url
        # embed URL: https://archive.org/embed/<id>/<file>
        # download URL: https://archive.org/download/<id>/<file>
        try:
            parts = video_url.split("/")
            ia_idx = parts.index("archive.org") + 1
            url_type = parts[ia_idx]  # 'embed' or 'download'
            vault_ia_id = parts[ia_idx + 1]
            filename = urllib.parse.unquote(parts[ia_idx + 2].split("?")[0])
        except Exception as e:
            print(f"  [{slug}] can't parse URL: {e}")
            failed += 1
            continue

        context = existing_tags.get("location", series.replace("-", " "))
        print(f"\n[{slug}] {filename} [{media_type}]")

        # Skip IA-generated derivative files that got accidentally seeded
        if ".thumbs" in filename or filename.endswith(("_meta.xml", "_files.xml", ".sqlite")):
            print(f"  IA derivative — skipping")
            failed += 1
            continue

        if is_photo:
            print(f"  photo — IA doesn't auto-thumb HEICs, skipping for now")
            failed += 1
            continue

        # Fetch IA thumbnail
        print(f"  fetching IA thumb...")
        thumb = ia_fetch_thumb(vault_ia_id, filename)
        if not thumb:
            print(f"  no thumb yet (IA may still be processing) — skipping")
            failed += 1
            continue
        print(f"  thumb: {len(thumb)//1024}KB")

        # LLM tag
        print(f"  tagging...")
        meta = llm_tag(thumb, context, dry_run=args.dry_run)
        if meta:
            meta["media_type"] = media_type
            title = meta.get("location", slug)[:60]
            print(f"  → {meta.get('location','?')} · {meta.get('time_of_day','?')} · {meta.get('mood','?')}")
        else:
            meta  = existing_tags
            title = slug

        # Update D1
        ok = update_d1_entry(slug, title, thumb, meta, token, dry_run=args.dry_run)
        print(f"  D1 update: {'OK' if ok else 'FAILED'}")
        if ok:
            done += 1
        else:
            failed += 1
            token = get_cf_token()  # refresh on 401

        if not args.dry_run:
            time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"Done: {done} processed, {failed} skipped/failed")


if __name__ == "__main__":
    main()
