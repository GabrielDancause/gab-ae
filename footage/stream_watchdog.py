#!/usr/bin/env python3
"""
stream_watchdog.py — runs ON the server.
Checks YouTube API every 2 min. If a stream is inactive 2 checks in a row,
restarts the service. If broadcast is gone, creates a new one and restarts.
"""

import json, os, subprocess, sys, time, datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE = "/opt/live_token.json"
SCOPES     = ["https://www.googleapis.com/auth/youtube"]
CHECK_INTERVAL = 120
FAIL_THRESHOLD = 2

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


def read_file(path):
    try:
        return open(path).read().strip()
    except Exception:
        return ""


def write_file(path, content):
    with open(path, "w") as f:
        f.write(content + "\n")


def get_stream_status(yt, stream_id):
    try:
        r = yt.liveStreams().list(part="status", id=stream_id).execute()
        if not r.get("items"):
            return "gone", "gone"
        s = r["items"][0]["status"]
        return s.get("streamStatus", "unknown"), s.get("healthStatus", {}).get("status", "unknown")
    except Exception as e:
        log(f"  API error: {e}")
        return "error", "error"


def get_broadcast_status(yt, broadcast_id):
    try:
        r = yt.liveBroadcasts().list(part="status", id=broadcast_id).execute()
        if not r.get("items"):
            return "gone"
        return r["items"][0]["status"]["lifeCycleStatus"]
    except Exception as e:
        log(f"  API error: {e}")
        return "error"


def create_new_broadcast(yt, cfg):
    log(f"  Creating new broadcast for '{cfg['title']}'...")
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

    write_file(cfg["rtmp_file"], rtmp)
    write_file(cfg["sid_file"], sid)
    write_file(cfg["bid_file"], bid)
    log(f"  New broadcast: https://www.youtube.com/watch?v={bid}")
    return bid, sid


def restart_service(service):
    log(f"  Restarting {service}...")
    subprocess.run(["systemctl", "restart", service], check=True)
    log(f"  {service} restarted.")


def check_and_fix(yt, name, cfg, fail_counts):
    sid = read_file(cfg["sid_file"])
    bid = read_file(cfg["bid_file"])

    if not sid or not bid:
        log(f"[{name}] No IDs on file — creating broadcast")
        create_new_broadcast(yt, cfg)
        restart_service(cfg["service"])
        fail_counts[name] = 0
        return

    stream_status, health = get_stream_status(yt, sid)
    broadcast_status = get_broadcast_status(yt, bid)
    log(f"[{name}] stream={stream_status} health={health} broadcast={broadcast_status}")

    if broadcast_status in ("gone", "complete", "revoked"):
        log(f"[{name}] Broadcast {broadcast_status} — creating new one")
        create_new_broadcast(yt, cfg)
        restart_service(cfg["service"])
        fail_counts[name] = 0
        return

    if stream_status in ("inactive", "error", "gone", "unknown"):
        fail_counts[name] = fail_counts.get(name, 0) + 1
        log(f"[{name}] Bad status — fail count {fail_counts[name]}/{FAIL_THRESHOLD}")
        if fail_counts[name] >= FAIL_THRESHOLD:
            log(f"[{name}] Restarting service")
            restart_service(cfg["service"])
            fail_counts[name] = 0
    else:
        if fail_counts.get(name, 0) > 0:
            log(f"[{name}] Recovered ✓")
        fail_counts[name] = 0


def main():
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


if __name__ == "__main__":
    main()
