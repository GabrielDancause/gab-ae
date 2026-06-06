#!/usr/bin/env python3
"""
stream_watchdog.py — Monitors both loop streams via YouTube API.

Checks the actual YouTube streamStatus every 2 minutes.
If a stream shows 'inactive' or 'error' for 2 consecutive checks,
it restarts the corresponding systemd service on the server.

If the broadcast itself is gone (ended/deleted), creates a new one.

Run permanently:
    python3 footage/stream_watchdog.py

Or as a one-shot health check:
    python3 footage/stream_watchdog.py --check
"""

import argparse, json, os, subprocess, sys, time, datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE = "footage/live_token.json"
SERVER     = "root@138.201.21.95"
SCOPES     = ["https://www.googleapis.com/auth/youtube"]
CHECK_INTERVAL = 120   # seconds between checks
FAIL_THRESHOLD = 2     # consecutive bad checks before restart

STREAMS = {
    "landscape": {
        "service":     "musique",
        "rtmp_file":   "/opt/rtmp_url.txt",
        "sid_file":    "/opt/stream_id.txt",
        "bid_file":    "/opt/broadcast_id.txt",
        "title":       "Musique et scènes mondaines",
        "description": "Scènes du quotidien — Paris et ailleurs.\nDiffusion continue 24h/24.",
    },
    "vertical": {
        "service":     "musique_vertical",
        "rtmp_file":   "/opt/rtmp_url_vertical.txt",
        "sid_file":    "/opt/stream_id_vertical.txt",
        "bid_file":    "/opt/broadcast_id_vertical.txt",
        "title":       "Scènes verticales — Paris et ailleurs",
        "description": "Moments du quotidien filmés à la verticale.\nDiffusion continue 24h/24.",
    },
}


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_youtube():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def get_stream_status(yt, stream_id):
    """Returns (streamStatus, healthStatus) or ('gone', 'gone') if not found."""
    try:
        r = yt.liveStreams().list(part="status", id=stream_id).execute()
        if not r.get("items"):
            return "gone", "gone"
        s = r["items"][0]["status"]
        return s.get("streamStatus", "unknown"), s.get("healthStatus", {}).get("status", "unknown")
    except Exception as e:
        log(f"  API error checking stream {stream_id}: {e}")
        return "error", "error"


def get_broadcast_status(yt, broadcast_id):
    """Returns lifeCycleStatus or 'gone'."""
    try:
        r = yt.liveBroadcasts().list(part="status", id=broadcast_id).execute()
        if not r.get("items"):
            return "gone"
        return r["items"][0]["status"]["lifeCycleStatus"]
    except Exception as e:
        log(f"  API error checking broadcast {broadcast_id}: {e}")
        return "error"


def read_server_file(path):
    r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER, f"cat {path}"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def write_server_file(path, content):
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER,
                    f"echo '{content}' > {path}"], check=True)


def create_new_broadcast(yt, cfg):
    """Create a fresh broadcast + stream key, save to server. Returns (bid, sid, rtmp)."""
    log(f"  Creating new broadcast for {cfg['title']}...")
    stream = yt.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {"title": f"{cfg['title']} — key"},
            "cdn": {"frameRate": "60fps", "ingestionType": "rtmp", "resolution": "1080p"},
            "contentDetails": {"isReusable": True},
        }
    ).execute()
    rtmp = (stream["cdn"]["ingestionInfo"]["ingestionAddress"] + "/"
            + stream["cdn"]["ingestionInfo"]["streamName"])
    sid = stream["id"]

    start = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    b = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {"title": cfg["title"], "description": cfg["description"], "scheduledStartTime": start},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            "contentDetails": {"enableAutoStart": True, "enableAutoStop": False, "latencyPreference": "normal"},
        }
    ).execute()
    bid = b["id"]
    yt.liveBroadcasts().bind(part="id,contentDetails", id=bid, streamId=sid).execute()

    write_server_file(cfg["rtmp_file"], rtmp)
    write_server_file(cfg["sid_file"], sid)
    write_server_file(cfg["bid_file"], bid)
    log(f"  New broadcast: https://www.youtube.com/watch?v={bid}")
    return bid, sid, rtmp


def restart_service(service):
    log(f"  Restarting {service}...")
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER,
                    f"systemctl restart {service}"], check=True)
    log(f"  {service} restarted.")


def check_and_fix(yt, name, cfg, fail_counts):
    sid = read_server_file(cfg["sid_file"])
    bid = read_server_file(cfg["bid_file"])

    if not sid or not bid:
        log(f"[{name}] No stream/broadcast ID on file — creating new broadcast")
        bid, sid, _ = create_new_broadcast(yt, cfg)
        restart_service(cfg["service"])
        fail_counts[name] = 0
        return

    stream_status, health = get_stream_status(yt, sid)
    broadcast_status = get_broadcast_status(yt, bid)

    log(f"[{name}] stream={stream_status} health={health} broadcast={broadcast_status}")

    # Broadcast gone — need a new one
    if broadcast_status == "gone":
        log(f"[{name}] Broadcast gone — creating new one")
        bid, sid, _ = create_new_broadcast(yt, cfg)
        restart_service(cfg["service"])
        fail_counts[name] = 0
        return

    # Broadcast ended by YouTube — create new
    if broadcast_status in ("complete", "revoked"):
        log(f"[{name}] Broadcast ended ({broadcast_status}) — creating new one")
        bid, sid, _ = create_new_broadcast(yt, cfg)
        restart_service(cfg["service"])
        fail_counts[name] = 0
        return

    # Stream inactive/error — count failures
    if stream_status in ("inactive", "error", "gone", "unknown"):
        fail_counts[name] = fail_counts.get(name, 0) + 1
        log(f"[{name}] Bad status — fail count: {fail_counts[name]}/{FAIL_THRESHOLD}")
        if fail_counts[name] >= FAIL_THRESHOLD:
            log(f"[{name}] Threshold reached — restarting service")
            restart_service(cfg["service"])
            fail_counts[name] = 0
    else:
        # Active and healthy
        if fail_counts.get(name, 0) > 0:
            log(f"[{name}] Recovered ✓")
        fail_counts[name] = 0


def run_loop():
    log("=== Stream watchdog started ===")
    fail_counts = {}
    while True:
        try:
            yt = get_youtube()
            for name, cfg in STREAMS.items():
                check_and_fix(yt, name, cfg, fail_counts)
        except Exception as e:
            log(f"Watchdog error: {e}")
        time.sleep(CHECK_INTERVAL)


def run_check():
    """One-shot health check, exits with 0 if all good, 1 if any issues."""
    yt = get_youtube()
    all_good = True
    for name, cfg in STREAMS.items():
        sid = read_server_file(cfg["sid_file"])
        bid = read_server_file(cfg["bid_file"])
        stream_status, health = get_stream_status(yt, sid) if sid else ("no_id", "no_id")
        broadcast_status = get_broadcast_status(yt, bid) if bid else "no_id"
        status_icon = "✓" if stream_status == "active" else "✗"
        print(f"{status_icon} [{name}] stream={stream_status} health={health} broadcast={broadcast_status}")
        if stream_status != "active":
            all_good = False
    return 0 if all_good else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="One-shot check and exit")
    args = parser.parse_args()
    if args.check:
        sys.exit(run_check())
    else:
        run_loop()
