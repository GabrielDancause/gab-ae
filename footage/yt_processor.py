#!/usr/bin/env python3
"""
yt_processor.py — YouTube processor for vault clips.

Polls D1 for yt_jobs WHERE status='queued', then for each job:
  1. Downloads clip from Internet Archive
  2. Applies ffmpeg: slow-mo (0.5x) + cinematic color grade
  3. Uploads to YouTube as a scheduled Short
  4. Updates D1 job to status='scheduled'

Runs on VPS. Cron every 5 min:
  */5 * * * * python3 /opt/gab/gab-adventures/footage/yt_processor.py >> /tmp/yt_processor.log 2>&1

YouTube token: /opt/gab/gab-adventures/footage/token_yt_gab.json
CF token:      /tmp/cf_token.txt
"""

import json, os, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── Config ────────────────────────────────────────────────────────────────────
CF_ACCOUNT_ID = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID      = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
TOKEN_FILE    = Path("/tmp/cf_token.txt")
YT_TOKEN_FILE = Path(__file__).parent / "token_yt_gab.json"
WORK_DIR      = Path("/tmp/yt_work")
LOG_FILE      = Path("/tmp/yt_processor.log")
MUSIC_DIR     = Path(__file__).parent / "music"
SATIE_TRACKS  = ["gymnopedie_no1.mp3", "gymnopedie_no2.mp3", "gymnopedie_no3.mp3", "gnossienne_no1.mp3"]

YT_CHANNEL    = "gab2"   # label only
YT_PRIVACY    = "private"  # start private, scheduler flips to public at publish time


# ── Helpers ───────────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def get_cf_token():
    permanent = Path("/opt/gab/cf_api_token.txt")
    if permanent.exists():
        return permanent.read_text().strip()
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""


def d1_query(sql, token):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = json.dumps({"sql": sql}).encode()
    req = urllib.request.Request(url, data=body,
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        if not result.get("success"):
            log(f"D1 error: {result.get('errors')}")
            return []
        return (result.get("result") or [{}])[0].get("results", [])
    except Exception as e:
        log(f"D1 exception: {e}")
        return []


def d1_exec(sql, token):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = json.dumps({"sql": sql}).encode()
    req = urllib.request.Request(url, data=body,
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        return result.get("success", False)
    except Exception as e:
        log(f"D1 exec exception: {e}")
        return False


def update_job(job_id, token, **fields):
    sets = ", ".join(f"{k}='{str(v).replace(chr(39), chr(39)*2)}'" for k, v in fields.items())
    sets += ", updated_at=datetime('now')"
    d1_exec(f"UPDATE yt_jobs SET {sets} WHERE id={job_id};", token)


def next_publish_time(token):
    """Return datetime for next available YouTube slot (1h after latest scheduled)."""
    rows = d1_query(
        "SELECT yt_scheduled_at FROM yt_jobs WHERE yt_scheduled_at IS NOT NULL ORDER BY yt_scheduled_at DESC LIMIT 1;",
        token
    )
    now = datetime.now(timezone.utc)
    if rows and rows[0].get("yt_scheduled_at"):
        try:
            last = datetime.fromisoformat(rows[0]["yt_scheduled_at"].replace("Z", "+00:00"))
            candidate = last + timedelta(hours=1)
            return candidate if candidate > now + timedelta(minutes=10) else now + timedelta(hours=1)
        except Exception:
            pass
    # Default: next full hour + 15 min
    return (now + timedelta(hours=1)).replace(minute=15, second=0, microsecond=0)


def ia_download_url(ia_url):
    """Convert embed/download IA URL to a direct download URL."""
    # embed: https://archive.org/embed/<id>/<file>?autoplay=1
    # download: https://archive.org/download/<id>/<file>
    url = ia_url.split("?")[0]
    return url.replace("/embed/", "/download/")


def download_from_ia(download_url, dest_path):
    """Download a file from IA to dest_path. Returns True on success."""
    log(f"  Downloading: {download_url}")
    req = urllib.request.Request(download_url, headers={"User-Agent": "gab-vault/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r, open(dest_path, "wb") as f:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        size_mb = dest_path.stat().st_size // 1024 // 1024
        log(f"  Downloaded: {size_mb}MB → {dest_path.name}")
        return True
    except Exception as e:
        log(f"  Download failed: {e}")
        return False


def get_duration(path):
    """Return duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def apply_effects(src, dst, music_track=None):
    """Apply slow-mo + color grade + Satie music (no original audio). Returns True on success."""
    src_dur = get_duration(src)
    out_dur = src_dur * 2.0  # 2x slow-mo
    fade_out_start = max(0.0, out_dur - 2.5)

    if music_track and music_track.exists():
        log(f"  ffmpeg: slow-mo + color grade + {music_track.name} (no original audio) → {dst.name}")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-stream_loop", "-1", "-i", str(music_track),
            "-t", str(out_dur),
            "-filter_complex",
            f"[0:v]setpts=2.0*PTS,"
            f"curves=r='0/0 0.5/0.52 1/0.96':g='0/0.02 0.5/0.54 1/0.98':b='0/0.06 0.5/0.52 1/0.88',"
            f"eq=contrast=1.1:saturation=1.7:brightness=0.02[v];"
            f"[1:a]volume=0.85,"
            f"afade=t=in:st=0:d=1.5,"
            f"afade=t=out:st={fade_out_start:.2f}:d=2.5[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(dst),
        ]
    else:
        log(f"  ffmpeg: slow-mo + color grade (no music) → {dst.name}")
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-vf",
            "setpts=2.0*PTS,"
            "curves=r='0/0 0.5/0.52 1/0.96':g='0/0.02 0.5/0.54 1/0.98':b='0/0.06 0.5/0.52 1/0.88',"
            "eq=contrast=1.1:saturation=1.7:brightness=0.02",
            "-an",  # no audio
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-movflags", "+faststart",
            str(dst),
        ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  ffmpeg error: {r.stderr[-600:]}")
        return False
    size_mb = dst.stat().st_size // 1024 // 1024
    log(f"  ffmpeg done: {size_mb}MB ({out_dur:.1f}s output)")
    return True


def get_yt_service():
    creds = Credentials.from_authorized_user_file(str(YT_TOKEN_FILE))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        YT_TOKEN_FILE.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_to_youtube(video_path, title, publish_at):
    """Upload video to YouTube, scheduled at publish_at (datetime). Returns video_id."""
    svc = get_yt_service()
    publish_str = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = {
        "snippet": {
            "title": title,
            "description": f"Shot in Paris, France.\n\n#shorts #paris #france #travel #pov",
            "tags": ["paris", "france", "travel", "shorts", "pov"],
            "categoryId": "19",  # Travel & Events
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_str,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=4*1024*1024)
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    log(f"  Uploading to YouTube (scheduled: {publish_str})...")
    while response is None:
        status, response = req.next_chunk()
        if status:
            log(f"  Upload progress: {int(status.progress() * 100)}%")
    video_id = response["id"]
    log(f"  YouTube video ID: {video_id}")
    return video_id


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    token = get_cf_token()
    if not token:
        log("ERROR: no CF token at /tmp/cf_token.txt")
        sys.exit(1)

    # Check for queued jobs
    jobs = d1_query("SELECT * FROM yt_jobs WHERE status='queued' ORDER BY id ASC LIMIT 5;", token)
    if not jobs:
        log("No queued YouTube jobs.")
        return

    log(f"Found {len(jobs)} queued job(s).")

    for job in jobs:
        job_id   = job["id"]
        slug     = job["video_slug"]
        ia_url   = job["ia_url"]
        log(f"\n{'='*50}")
        log(f"Job {job_id}: {slug}")

        src_path = WORK_DIR / f"{slug}_raw.mp4"
        out_path = WORK_DIR / f"{slug}_slowmo.mp4"

        try:
            # 1. Download from IA
            update_job(job_id, token, status="downloading", progress="Downloading from IA")
            dl_url = ia_download_url(ia_url)
            if not download_from_ia(dl_url, src_path):
                update_job(job_id, token, status="error", error="IA download failed")
                continue

            # 2. ffmpeg slow-mo + color grade + Satie
            music = MUSIC_DIR / SATIE_TRACKS[0]  # always Gymnopedie No. 1
            update_job(job_id, token, status="processing", progress=f"Applying slow-mo + {music.stem}")
            if not apply_effects(src_path, out_path, music_track=music):
                update_job(job_id, token, status="error", error="ffmpeg failed")
                src_path.unlink(missing_ok=True)
                continue

            src_path.unlink(missing_ok=True)

            # 3. Schedule time
            publish_at = next_publish_time(token)
            log(f"  Scheduled for: {publish_at.isoformat()}")

            # 4. Upload to YouTube
            update_job(job_id, token, status="uploading", progress="Uploading to YouTube")
            # Refresh CF token before long upload
            token = get_cf_token()

            # Pull title from videos table (LLM-set location), fall back to slug
            vid_rows = d1_query(f"SELECT title FROM videos WHERE slug='{slug}';", token)
            if vid_rows and vid_rows[0].get("title"):
                title = vid_rows[0]["title"][:60]
            else:
                title = slug.replace("-", " ").replace("_", " ").title()[:60]
            video_id = upload_to_youtube(out_path, title, publish_at)
            yt_url = f"https://www.youtube.com/watch?v={video_id}"

            out_path.unlink(missing_ok=True)

            # 5. Update D1
            scheduled_str = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            token = get_cf_token()
            update_job(job_id, token,
                       status="scheduled",
                       progress=f"Scheduled for {scheduled_str}",
                       yt_video_id=video_id,
                       yt_url=yt_url,
                       yt_scheduled_at=scheduled_str)
            log(f"  Done: {yt_url}")

        except Exception as e:
            log(f"  EXCEPTION: {e}")
            update_job(job_id, token, status="error", error=str(e)[:200])
            for p in [src_path, out_path]:
                p.unlink(missing_ok=True)

    log(f"\n{'='*50}")
    log("yt_processor done.")


if __name__ == "__main__":
    main()
