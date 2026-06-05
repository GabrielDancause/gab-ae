#!/usr/bin/env python3
"""
backup_to_ia.py — Phase 1: Stream Drive folders → Internet Archive (no local disk)

Flow per session (Drive state machine):
  _Todo/<folder>  →  _Doing/<folder>  →  rclone Drive→IA stream  →  D1 seed (backed_up)  →  _Done/<folder>

Stuck _Doing folders are moved back to _Todo on startup for retry.

Usage:
    python3 footage/backup_to_ia.py              # process all in _Todo
    python3 footage/backup_to_ia.py --dry-run    # print what would happen, no transfers
"""

import argparse, json, re, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
CF_ACCOUNT_ID = "f8a9c8de1fcedb10d25b24325a6f8727"
CF_DB_ID      = "4e23e386-b430-4ffc-bf84-246a4e7bcdd1"
IA_ACCESS     = "Ot0FVHkLiDTD4WDE"
IA_SECRET     = "caXpcbAZF8nfBX1D"
IA_ENDPOINT   = "s3.us.archive.org"

DRIVE_TODO    = "gab-drive:_Todo"
DRIVE_DOING   = "gab-drive:_Doing"
DRIVE_DONE    = "gab-drive:_Done"

VIDEO_EXTS    = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".hevc", ".insv", ".lrv"}
PHOTO_EXTS    = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".insp", ".dng", ".tiff", ".tif"}

STATE_FILE    = Path("/tmp/backup_state.json")
LOG_FILE      = Path("/tmp/backup_to_ia.log")


# ── Helpers ───────────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]


def run(cmd, dry_run=False, **kwargs):
    log(f"  $ {' '.join(str(c) for c in cmd)}")
    if dry_run:
        return type("R", (), {"returncode": 0})()
    return subprocess.run(cmd, **kwargs)


def get_cf_token():
    # Permanent API token (long-lived, no expiry) — takes priority
    permanent = Path("/opt/gab/cf_api_token.txt")
    if permanent.exists():
        return permanent.read_text().strip()
    # VPS fallback: hourly OAuth token pushed by Mac cron
    vps_token_file = Path("/tmp/cf_token.txt")
    if vps_token_file.exists():
        return vps_token_file.read_text().strip()
    # Mac mode: read from wrangler TOML, auto-refresh if expiring
    import tomllib, pathlib, datetime as dt
    p = pathlib.Path.home() / "Library/Preferences/.wrangler/config/default.toml"
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    exp = cfg.get("expiration_time", "")
    try:
        exp_dt = dt.datetime.fromisoformat(exp.replace("Z", "+00:00"))
        if (exp_dt - dt.datetime.now(dt.timezone.utc)).total_seconds() < 120:
            log("  Token expiring soon — refreshing...")
            subprocess.run(["npx", "wrangler", "d1", "list", "--remote"],
                           capture_output=True)
            with open(p, "rb") as f:
                cfg = tomllib.load(f)
    except Exception:
        pass
    return cfg["oauth_token"]


def d1_query(sql, token, dry_run=False):
    if dry_run:
        log(f"  [DRY RUN] {sql[:100]}...")
        return True
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
    body = json.dumps({"sql": sql}).encode()
    req = urllib.request.Request(url, data=body,
          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        if not result.get("success"):
            log(f"  D1 error: {result.get('errors')}")
            return False
        return True
    except Exception as e:
        log(f"  D1 exception: {e}")
        return False


def list_drive_folders(drive_path):
    r = subprocess.run(["rclone", "lsd", drive_path, "--max-depth", "1"],
                       capture_output=True, text=True)
    folders = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 4)
        if len(parts) >= 5:
            folders.append(parts[4])
    return sorted(folders, reverse=True)  # most recent first


def list_drive_files(drive_path):
    """Return list of (path, size_bytes) for all files in a Drive folder (recursive)."""
    r = subprocess.run(["rclone", "lsjson", drive_path, "--no-modtime", "--recursive"],
                       capture_output=True, text=True)
    try:
        return [(f["Path"], f.get("Size", 0)) for f in json.loads(r.stdout)
                if not f.get("IsDir")]
    except Exception:
        return []


def folder_size_gb(drive_path):
    r = subprocess.run(["rclone", "size", drive_path, "--json"],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("bytes", 0) / 1024**3
    except Exception:
        return 0


def write_state(sessions):
    state = {"updated": now_iso(), "sessions": sessions}
    STATE_FILE.write_text(json.dumps(state, indent=2))


def seed_backed_up(slug, fname, series, vault_ia_id, media_type, token, dry_run=False):
    """Insert a backed_up (no thumbnail, no tags) entry into D1."""
    ext = ("." + fname.rsplit(".", 1)[-1]).lower() if "." in fname else ""
    if media_type == "photo":
        url = f"https://archive.org/download/{vault_ia_id}/{urllib.parse.quote(fname)}"
    else:
        url = f"https://archive.org/embed/{vault_ia_id}/{urllib.parse.quote(fname)}?autoplay=1"
    tags = json.dumps({"media_type": media_type, "backed_up": True, "producer": "gab-productions"}).replace("'", "''")
    title = fname.replace("'", "''")
    series_s = series.replace("'", "''")
    url_s = url.replace("'", "''")
    sql = (
        f"INSERT OR REPLACE INTO videos (slug, title, series, thumb_b64, video_url, status, tags) "
        f"VALUES ('{slug}', '{title}', '{series_s}', '', '{url_s}', 'backed_up', '{tags}');"
    )
    return d1_query(sql, token, dry_run=dry_run)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Phase 1: Stream Drive → IA, seed D1 as backed_up")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Check quota flag — skip run until next UTC day
    quota_flag = Path("/tmp/backup_quota_hit.flag")
    if quota_flag.exists():
        flag_time = quota_flag.read_text().strip()
        try:
            import datetime as dt
            flag_dt = dt.datetime.fromisoformat(flag_time.replace("Z", "+00:00"))
            if flag_dt.date() >= dt.datetime.now(dt.timezone.utc).date():
                log("Quota hit today — skipping until tomorrow. Remove /tmp/backup_quota_hit.flag to force.")
                return
        except Exception:
            pass
        quota_flag.unlink(missing_ok=True)  # new day, clear flag

    log("backup_to_ia starting")

    # Recover stuck _Doing folders → _Todo
    stuck = list_drive_folders(DRIVE_DOING)
    for folder in stuck:
        log(f"  Recovering stuck: {folder} → _Todo/")
        run(["rclone", "moveto", f"{DRIVE_DOING}/{folder}", f"{DRIVE_TODO}/{folder}"], dry_run=args.dry_run)

    todo = list_drive_folders(DRIVE_TODO)
    if not todo:
        log("Nothing in _Todo/ — done.")
        return

    log(f"Found {len(todo)} folder(s): {todo}")

    token = get_cf_token()
    log(f"CF token: {token[:16]}...")

    sessions_state = []
    for folder_name in todo:
        slug        = slugify(folder_name)
        vault_ia_id = f"gab-raw-{slug}"
        size_gb     = folder_size_gb(f"{DRIVE_TODO}/{folder_name}")
        sessions_state.append({
            "name": folder_name, "series": slug, "vault_ia_id": vault_ia_id,
            "size_gb": round(size_gb, 1), "status": "queued",
        })
    write_state(sessions_state)

    for st in sessions_state:
        folder_name = st["name"]
        slug        = st["series"]
        vault_ia_id = st["vault_ia_id"]

        log(f"\n{'='*60}")
        log(f"Backing up: {folder_name}  ({st['size_gb']:.1f} GB)")
        log(f"  IA item: {vault_ia_id}")

        # List files before moving so we know what to seed
        files = list_drive_files(f"{DRIVE_TODO}/{folder_name}")
        media_files = []
        for fname, size in files:
            ext = ("." + fname.rsplit(".", 1)[-1]).lower() if "." in fname else ""
            if ext in VIDEO_EXTS:
                media_files.append((fname, size, "video"))
            elif ext in PHOTO_EXTS:
                media_files.append((fname, size, "photo"))
        log(f"  {len(media_files)} media files ({sum(1 for _,_,t in media_files if t=='video')} video, {sum(1 for _,_,t in media_files if t=='photo')} photo)")

        # _Todo → _Doing
        r = run(["rclone", "moveto", f"{DRIVE_TODO}/{folder_name}", f"{DRIVE_DOING}/{folder_name}"],
                dry_run=args.dry_run)
        if not args.dry_run and r.returncode != 0:
            log("  ERROR: could not move to _Doing/ — skipping")
            continue

        # Stream Drive → IA (rclone remote-to-remote, no local disk)
        st["status"] = "uploading"
        write_state(sessions_state)
        log(f"  Streaming Drive → IA (no local disk)...")

        ia_path = f":internetarchive,access_key_id={IA_ACCESS},secret_access_key={IA_SECRET}:{vault_ia_id}"
        upload_cmd = [
            "rclone", "copy",
            f"{DRIVE_DOING}/{folder_name}",
            ia_path,
            "--transfers=1",
            "--tpslimit=2",
            "--drive-pacer-min-sleep=200ms",
            "--drive-pacer-burst=2",
            "--retries=1",
            "--progress",
        ]

        # Set IA item metadata on first upload via header
        upload_cmd += [
            '--header-upload', 'x-archive-meta-mediatype:movies',
            '--header-upload', 'x-archive-meta-subject:gab;personal;vault;private',
            '--header-upload', 'x-archive-meta-access-control:private',
            '--header-upload', f'x-archive-meta-title:{folder_name}',
            '--header-upload', 'x-archive-meta-noindex:true',
            '--header-upload', 'x-archive-meta-creator:Gab Dancause',
            '--header-upload', 'x-archive-meta-producer:Gab Productions',
        ]

        r = run(upload_cmd, dry_run=args.dry_run, capture_output=True, text=True)
        if not args.dry_run and r.returncode != 0:
            stderr = (r.stderr or "") + (r.stdout or "")
            if "downloadQuotaExceeded" in stderr or "quotaExceeded" in stderr:
                log("  QUOTA EXCEEDED — Google Drive daily limit hit. Stopping for today.")
                log("  All remaining folders will be retried on next run after quota resets.")
                st["status"] = "quota"
                run(["rclone", "moveto", f"{DRIVE_DOING}/{folder_name}", f"{DRIVE_TODO}/{folder_name}"],
                    dry_run=args.dry_run)
                write_state(sessions_state)
                # Touch a flag file so cron skips until midnight
                Path("/tmp/backup_quota_hit.flag").write_text(now_iso())
                break  # stop processing remaining folders
            log("  ERROR: upload failed — moving back to _Todo/")
            st["status"] = "error"
            run(["rclone", "moveto", f"{DRIVE_DOING}/{folder_name}", f"{DRIVE_TODO}/{folder_name}"],
                dry_run=args.dry_run)
            write_state(sessions_state)
            continue

        log(f"  Upload complete.")

        # Refresh token after long upload
        token = get_cf_token()

        # Seed D1 — one entry per media file, status=backed_up
        st["status"] = "seeding"
        write_state(sessions_state)
        seeded = 0
        failed = 0
        for i, (fname, size, media_type) in enumerate(media_files, 1):
            file_slug = f"{slug}-{i:03d}"
            log(f"  [{i}/{len(media_files)}] {fname} ({size//1024//1024}MB) [{media_type}]")
            ok = seed_backed_up(file_slug, fname, slug, vault_ia_id, media_type, token, dry_run=args.dry_run)
            time.sleep(0.3)  # avoid D1 overload
            if ok:
                seeded += 1
            else:
                failed += 1
                token = get_cf_token()  # refresh on failure

        log(f"  D1: {seeded} seeded, {failed} failed")

        # _Doing → _Done
        run(["rclone", "moveto", f"{DRIVE_DOING}/{folder_name}", f"{DRIVE_DONE}/{folder_name}"],
            dry_run=args.dry_run)

        st["status"] = "backed_up"
        write_state(sessions_state)
        log(f"  Done — {folder_name} backed up to IA. Process later with process_from_ia.py")

    log(f"\n{'='*60}")
    log("backup_to_ia complete.")


if __name__ == "__main__":
    main()
