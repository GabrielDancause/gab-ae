#!/usr/bin/env python3
"""
clip_tagger.py — Tag video clips using vision AI (OpenRouter).

Extracts 4 frames from a clip, sends to vision model, stores results in D1.

Usage:
    python3 footage/clip_tagger.py --clip /path/to/clip.mp4
    python3 footage/clip_tagger.py --clip /path/to/clip.mp4 --dry-run   # print tags, don't save
    python3 footage/clip_tagger.py --folder /opt/broadcast               # tag all untagged clips
    python3 footage/clip_tagger.py --status                              # show tagging stats from D1
"""

import argparse, base64, json, os, subprocess, sys, tempfile, tomllib, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL         = "nvidia/nemotron-nano-12b-v2-vl:free"
CF_ACCOUNT_ID = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID      = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"

PROMPT = """You are analyzing frames from a short video clip. I will show you 4 frames sampled evenly across the clip.

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
- timelapse.possible: true if the shot is slow/stable enough that speeding it up would look great (drone pans, landscapes, cityscapes, slow walks)
- confidence: your overall confidence in these tags (0.0–1.0)"""


# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frames(clip_path, n=4):
    """Extract n frames evenly spaced from clip. Returns list of base64 JPEG strings."""
    # Get duration
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", clip_path],
        capture_output=True, text=True)
    duration = float(json.loads(r.stdout)["format"]["duration"])

    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = duration * (i + 1) / (n + 1)   # evenly spaced, skip start/end
            out = os.path.join(tmp, f"frame_{i}.jpg")
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(t), "-i", clip_path,
                "-vframes", "1", "-q:v", "3",
                "-vf", "scale=640:-1",   # resize to 640px wide for API efficiency
                out
            ], capture_output=True)
            if os.path.exists(out):
                with open(out, "rb") as f:
                    frames.append(base64.b64encode(f.read()).decode())
    return frames, duration


# ── OpenRouter call ───────────────────────────────────────────────────────────

def tag_clip(clip_path, dry_run=False):
    """Extract frames, call vision model, return parsed tags dict."""
    print(f"  Extracting frames from {Path(clip_path).name}...")
    frames, duration = extract_frames(clip_path)
    print(f"  {len(frames)} frames extracted ({duration:.1f}s clip)")

    # Build message with all frames
    content = [{"type": "text", "text": PROMPT}]
    for i, b64 in enumerate(frames):
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    print(f"  Sending to {MODEL}...")
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

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    tags = json.loads(raw)
    tags["duration_s"] = round(duration, 1)
    tags["clip"] = Path(clip_path).name
    return tags


# ── D1 ────────────────────────────────────────────────────────────────────────

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

def ensure_clips_table(token):
    d1_query("""
        CREATE TABLE IF NOT EXISTS clips (
            id           TEXT PRIMARY KEY,
            drive        TEXT,
            folder       TEXT,
            stream       TEXT,
            broadcast_ok INTEGER DEFAULT 1,
            tags         TEXT,
            scene_desc   TEXT,
            tagged_at    TEXT,
            created_at   TEXT
        )
    """, token)

def save_to_d1(clip_path, tags, drive, token):
    clip_id    = Path(clip_path).name
    folder     = Path(clip_path).parent.name
    stream     = tags.get("stream_suggestion", "horizontal")
    broadcast_ok = 1 if tags.get("broadcast_ok", True) else 0
    scene_desc = tags.get("scene_desc", "")
    tags_json  = json.dumps(tags)
    now        = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    d1_query("""
        INSERT OR REPLACE INTO clips
        (id, drive, folder, stream, broadcast_ok, tags, scene_desc, tagged_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, token, params=[clip_id, drive, folder, stream, broadcast_ok, tags_json, scene_desc, now, now])


# ── Status ────────────────────────────────────────────────────────────────────

def show_status(token):
    r = d1_query("SELECT COUNT(*) as n FROM clips", token)
    total = r["result"][0]["results"][0]["n"]
    r = d1_query("SELECT COUNT(*) as n FROM clips WHERE broadcast_ok = 0", token)
    private = r["result"][0]["results"][0]["n"]
    r = d1_query("SELECT COUNT(*) as n FROM clips WHERE json_extract(tags, '$.has_ali') = 1", token)
    ali = r["result"][0]["results"][0]["n"]
    r = d1_query("SELECT stream, COUNT(*) as n FROM clips GROUP BY stream", token)
    by_stream = {row["stream"]: row["n"] for row in r["result"][0]["results"]}

    print(f"\n  Total clips tagged : {total}")
    print(f"  Private (no broadcast): {private}")
    print(f"  Has Ali            : {ali}")
    print(f"  By stream          : {by_stream}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip",     help="Tag a single clip")
    parser.add_argument("--folder",   help="Tag all untagged clips in a folder")
    parser.add_argument("--drive",    default="unknown", help="Drive label (luke, padme, yoda...)")
    parser.add_argument("--dry-run",  action="store_true", help="Print tags, don't save to D1")
    parser.add_argument("--status",   action="store_true", help="Show tagging stats")
    args = parser.parse_args()

    token = None
    if not args.dry_run:
        token = get_cf_token()
        ensure_clips_table(token)

    if args.status:
        show_status(token)
        return

    if args.clip:
        clips = [args.clip]
    elif args.folder:
        clips = sorted(
            str(p) for p in Path(args.folder).glob("**/*.mp4")
            if "_wip" not in str(p)
        ) + sorted(
            str(p) for p in Path(args.folder).glob("**/*.MP4")
            if "_wip" not in str(p)
        )
        if not args.dry_run and token:
            # Filter already-tagged
            r = d1_query("SELECT id FROM clips", token)
            already = {row["id"] for row in r["result"][0]["results"]}
            before = len(clips)
            clips = [c for c in clips if Path(c).name not in already]
            print(f"  {before} clips found, {len(clips)} untagged")
    else:
        parser.print_help()
        sys.exit(1)

    for i, clip in enumerate(clips, 1):
        print(f"\n[{i}/{len(clips)}] {Path(clip).name}")
        try:
            tags = tag_clip(clip)

            # Pretty print
            print(f"\n  ┌─ Tags ──────────────────────────────")
            print(f"  │ scene     : {tags.get('scene_desc')}")
            print(f"  │ activity  : {tags.get('activity')}")
            print(f"  │ location  : {tags.get('location')}")
            print(f"  │ camera    : {tags.get('camera')}")
            print(f"  │ weather   : {tags.get('weather')}")
            print(f"  │ stream    : {tags.get('stream_suggestion')}")
            print(f"  │ broadcast : {'✓ yes' if tags.get('broadcast_ok') else '✗ NO — private'}")
            print(f"  │ has_ali   : {'YES' if tags.get('has_ali') else 'no'}")
            print(f"  │ children  : {'YES — private' if tags.get('has_children') else 'no'}")
            print(f"  │ nudity    : {'YES — private' if tags.get('has_nudity') else 'no'}")
            tl = tags.get("timelapse", {})
            if tl.get("possible"):
                print(f"  │ timelapse : ✓ {tl.get('from_s')}s–{tl.get('to_s')}s — {tl.get('reason')}")
            else:
                print(f"  │ timelapse : no — {tl.get('reason')}")
            print(f"  │ confidence: {tags.get('confidence')}")
            print(f"  └────────────────────────────────────")

            if args.dry_run:
                print("  [dry-run] not saved to D1")
            else:
                save_to_d1(clip, tags, args.drive, token)
                print("  ✓ saved to D1")

        except Exception as e:
            print(f"  ✗ error: {e}")

if __name__ == "__main__":
    main()
