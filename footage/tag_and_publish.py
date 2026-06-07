#!/usr/bin/env python3
"""
tag_and_publish.py — Full pipeline: raw clip → encode → AI tag → YouTube → homepage.

Usage:
    python3 footage/tag_and_publish.py --clip /path/to/raw.MP4
    python3 footage/tag_and_publish.py --clip /path/to/raw.MP4 --dry-run   # no upload, no D1
    python3 footage/tag_and_publish.py --clip /path/to/raw.MP4 --start 30  # encode from 30s
"""

import argparse, base64, json, os, random, re, subprocess, sys, tempfile, tomllib, urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
MODEL           = "nvidia/nemotron-nano-12b-v2-vl:free"
CF_ACCOUNT_ID   = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID        = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
CREDENTIALS_FILE = "/Users/gab/Desktop/gab-ae/shorts-uploader/credentials.json"
TOKEN_FILE       = "/Users/gab/Desktop/gab-ae/footage/live_token.json"

CLIP_DURATION = 15   # seconds to encode

VISION_PROMPT = """You are analyzing frames from a short video clip. I will show you 4 frames sampled evenly across the clip.

Answer the following in valid JSON — nothing else, no markdown:

{
  "has_ali": false,
  "has_nudity": false,
  "has_children": false,
  "broadcast_ok": true,
  "activity": "describe main activity in 2-3 words",
  "location": "describe location briefly",
  "camera": "drone / iphone / gopro / unknown",
  "weather": "sunny / cloudy / night / indoor / unknown",
  "scene_desc": "one sentence describing what is happening",
  "timelapse": {
    "possible": false,
    "from_s": null,
    "to_s": null,
    "reason": "why or why not"
  },
  "stream_suggestion": "horizontal / vertical / ali / private",
  "confidence": 0.0
}

Rules:
- has_nudity: true if any nudity or partial nudity is visible
- has_children: true if anyone who appears to be under 18 is visible
- has_ali: true ONLY if you are confident a specific recurring person (dark hair, appears to be the main subject in multiple frames) is present — be conservative, default false
- broadcast_ok: false if has_nudity OR has_children, otherwise true
- stream_suggestion: "private" if not broadcast_ok, "ali" if has_ali, "vertical" if footage is portrait/vertical orientation, otherwise "horizontal"
- timelapse.possible: true if the shot is slow/stable enough that speeding it up would look great
- confidence: your overall confidence in these tags (0.0–1.0)"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg): print(msg, flush=True)

def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]

def get_cf_token():
    p = Path.home() / "Library/Preferences/.wrangler/config/default.toml"
    with open(p, "rb") as f:
        return tomllib.load(f)["oauth_token"]

def d1_query(sql, token, params=None):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = {"sql": sql}
    if params:
        body["params"] = params
    req = urllib.request.Request(url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    if not result.get("success"):
        raise Exception(f"D1 error: {result.get('errors')}")
    return result


# ── Step 1: Probe raw clip ────────────────────────────────────────────────────

def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True)
    d = json.loads(r.stdout)
    vs = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    fmt = d["format"]
    return {
        "duration": float(fmt["duration"]),
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
    }


# ── Step 2: Encode 15s clip ───────────────────────────────────────────────────

def encode_clip(src, out_path, start_s, duration=CLIP_DURATION):
    """Encode a clip with VideoToolbox H.264. Returns output path."""
    info = probe(src)
    w, h = info["width"], info["height"]
    is_vertical = h > w

    if is_vertical:
        vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    else:
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s),
        "-i", src,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "h264_videotoolbox",
        "-b:v", "8000k",
        "-r", "60",
        "-an",           # strip audio
        "-movflags", "+faststart",
        out_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"ffmpeg encode failed:\n{r.stderr[-500:]}")
    return out_path


# ── Step 3: Extract frames for tagging ───────────────────────────────────────

def extract_frames(clip_path, n=4):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", clip_path],
        capture_output=True, text=True)
    duration = float(json.loads(r.stdout)["format"]["duration"])

    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = duration * (i + 1) / (n + 1)
            out = os.path.join(tmp, f"frame_{i}.jpg")
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(t), "-i", clip_path,
                "-vframes", "1", "-q:v", "3", "-vf", "scale=640:-1", out
            ], capture_output=True)
            if os.path.exists(out):
                with open(out, "rb") as f:
                    frames.append(base64.b64encode(f.read()).decode())
    return frames, duration


# ── Step 4: AI tag ────────────────────────────────────────────────────────────

def tag_clip(clip_path):
    log("  Extracting frames for tagging...")
    frames, duration = extract_frames(clip_path)
    log(f"  {len(frames)} frames extracted ({duration:.1f}s clip)")

    content = [{"type": "text", "text": VISION_PROMPT}]
    for b64 in frames:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    log(f"  Sending to {MODEL}...")
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 512,
        "temperature": 0.1,
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gab.ae",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())

    raw = resp["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    tags = json.loads(raw)
    tags["duration_s"] = round(duration, 1)
    return tags


# ── Step 5: Extract thumbnail ─────────────────────────────────────────────────

def extract_thumbnail(clip_path):
    """Extract middle frame as base64 JPEG (640px wide)."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", clip_path],
        capture_output=True, text=True)
    duration = float(json.loads(r.stdout)["format"]["duration"])
    t = duration / 2

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "thumb.jpg")
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(t), "-i", clip_path,
            "-vframes", "1", "-q:v", "2", "-vf", "scale=640:-1", out
        ], capture_output=True)
        if os.path.exists(out):
            with open(out, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return ""


# ── Step 6: YouTube upload ────────────────────────────────────────────────────

def upload_youtube(clip_path, title, description, tags_list):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    yt = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags_list,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(clip_path, chunksize=10*1024*1024, resumable=True)
    req_obj = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req_obj.next_chunk()
        if status:
            print(f"  uploading... {int(status.progress()*100)}%", end="\r", flush=True)

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    log(f"\n  ✓ YouTube: {url}")
    return video_id, url


# ── Step 7: Save to D1 shorts ─────────────────────────────────────────────────

def save_to_shorts(slug, title, yt_url, thumb_b64, tags, token):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tags_json = json.dumps(tags)
    d1_query("""
        INSERT OR REPLACE INTO shorts (slug, title, series, thumb_b64, video_url, published_at, status, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, token, params=[slug, title, "raw-footage", thumb_b64, yt_url, now, "live", tags_json])
    log(f"  ✓ D1 shorts: {slug} → live on homepage")


# ── Shared publish logic (tag → check → upload → D1) ─────────────────────────

def run_publish(encoded_path, source_name, drive, dry_run):
    """Tag an encoded clip and publish it if broadcast_ok. Returns True if published."""
    # Tag
    log("\n── Tagging ──")
    tags = tag_clip(encoded_path)

    log(f"\n  ┌─ Tags ──────────────────────────────")
    log(f"  │ scene     : {tags.get('scene_desc')}")
    log(f"  │ activity  : {tags.get('activity')}")
    log(f"  │ location  : {tags.get('location')}")
    log(f"  │ camera    : {tags.get('camera')}")
    log(f"  │ weather   : {tags.get('weather')}")
    log(f"  │ stream    : {tags.get('stream_suggestion')}")
    log(f"  │ broadcast : {'✓ yes' if tags.get('broadcast_ok') else '✗ NO — will not publish'}")
    log(f"  │ has_ali   : {'YES' if tags.get('has_ali') else 'no'}")
    log(f"  │ timelapse : {'✓ possible' if tags.get('timelapse', {}).get('possible') else 'no'}")
    log(f"  │ confidence: {tags.get('confidence')}")
    log(f"  └────────────────────────────────────")

    if not tags.get("broadcast_ok", True):
        log("  ✗ broadcast_ok = false — skipping publish")
        return False

    if dry_run:
        log("  [dry-run] stopping here — no upload, no D1")
        return False

    # Build slug + title
    activity = tags.get("activity", "clip").replace(" ", "-")
    location = tags.get("location", "").split(",")[0].strip().replace(" ", "-").lower()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug_raw = f"{activity}-{location}-{date_str}" if location else f"{activity}-{date_str}"
    slug = slugify(slug_raw)

    # Make slug unique if already exists in D1
    token = get_cf_token()
    r = d1_query("SELECT COUNT(*) as n FROM shorts WHERE slug = ?", token, params=[slug])
    if r["result"][0]["results"][0]["n"] > 0:
        slug = slug[:50] + f"-{int(datetime.now().timestamp()) % 10000}"

    title = tags.get("scene_desc", "").rstrip(".") or f"{tags.get('activity', 'Clip')} — {date_str}"
    if len(title) > 100:
        title = title[:97] + "..."

    description = (
        f"{tags.get('scene_desc', '')}\n\n"
        f"Activity: {tags.get('activity', '')}\n"
        f"Location: {tags.get('location', '')}\n"
        f"Camera: {tags.get('camera', '')}\n\n"
        f"gab.ae"
    )
    yt_tags = ["gab", tags.get("activity", ""), tags.get("location", ""),
               tags.get("camera", ""), tags.get("weather", ""), "footage"]
    yt_tags = [t for t in yt_tags if t]

    log(f"\n── Publishing ──")
    log(f"  slug  : {slug}")
    log(f"  title : {title}")

    log("  Extracting thumbnail...")
    thumb_b64 = extract_thumbnail(encoded_path)
    log(f"  ✓ Thumbnail: {len(thumb_b64)//1024}KB base64")

    log("  Uploading to YouTube...")
    yt_id, yt_url = upload_youtube(encoded_path, title, description, yt_tags)

    log("  Saving to D1...")
    tags["clip_source"] = source_name
    tags["drive"] = drive
    save_to_shorts(slug, title, yt_url, thumb_b64, tags, token)

    log(f"\n{'='*50}")
    log(f"  ✓ Live on gab.ae homepage!")
    log(f"  YouTube : {yt_url}")
    log(f"  Page    : https://gab.ae")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip",            required=True, help="Path to clip (raw or already-encoded)")
    parser.add_argument("--start",           type=float, default=None, help="Start offset in seconds (random if omitted, ignored if --already-encoded)")
    parser.add_argument("--already-encoded", action="store_true", help="Skip encode step — clip is already a broadcast-ready 15s file")
    parser.add_argument("--dry-run",         action="store_true", help="Tag only, no upload, no D1")
    parser.add_argument("--drive",           default="unknown", help="Drive label")
    args = parser.parse_args()

    clip = args.clip
    if not os.path.exists(clip):
        log(f"✗ File not found: {clip}")
        sys.exit(1)

    log(f"\n=== tag_and_publish ===")
    log(f"Source: {Path(clip).name}")

    if args.already_encoded:
        log("  (already-encoded — skipping encode step)")
        run_publish(clip, Path(clip).name, args.drive, args.dry_run)
        return

    # Probe source
    info = probe(clip)
    log(f"  {info['width']}x{info['height']} · {info['duration']:.0f}s")

    # Pick start time (avoid first/last 5%)
    margin = max(5, info["duration"] * 0.05)
    max_start = max(0, info["duration"] - CLIP_DURATION - margin)
    start_s = args.start if args.start is not None else random.uniform(margin, max_start)
    log(f"  Encoding {CLIP_DURATION}s clip starting at {start_s:.1f}s...")

    with tempfile.TemporaryDirectory() as tmp:
        encoded = os.path.join(tmp, f"clip_{int(start_s)}.mp4")
        encode_clip(clip, encoded, start_s)
        size_mb = os.path.getsize(encoded) / 1024 / 1024
        log(f"  ✓ Encoded: {size_mb:.1f} MB")
        run_publish(encoded, Path(clip).name, args.drive, args.dry_run)


if __name__ == "__main__":
    main()
