#!/usr/bin/env python3
"""
Session streamer — runs on VPS forever.
Streams each DJI session as its own unlisted YouTube broadcast, chronologically.
-c:v copy = zero re-encode. Music underneath, looping.
Loops forever: checks for new sessions every 5 min, musique fallback covers gaps.
State: /opt/session_state.json
"""

import os, sys, json, glob, subprocess, datetime, time, random, re, signal

FOOTAGE_DIR  = "/opt/footage_1080p"
MUSIC_DIR    = "/opt/music"
STATE_FILE   = "/opt/session_state.json"
TOKEN_FILE   = "/opt/yt_token.json"
PLAYLIST_TMP = "/tmp/session_playlist.txt"
POLL_INTERVAL = 300   # seconds between checks when no new sessions
MIN_CLIPS     = 3     # don't stream a session until at least this many clips are ready


# ── YouTube auth ─────────────────────────────────────────────────────────────

def get_youtube():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


# ── Session grouping ─────────────────────────────────────────────────────────

def find_sessions():
    """Return dict: {date_str: [sorted clip paths]}"""
    clips = sorted(glob.glob(os.path.join(FOOTAGE_DIR, "*.mp4")))
    sessions = {}
    for clip in clips:
        name = os.path.basename(clip)
        m = re.search(r'DJI_(\d{8})', name)
        date = m.group(1) if m else "unknown"
        sessions.setdefault(date, []).append(clip)
    return sessions


# ── State ────────────────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"done": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── YouTube broadcast ────────────────────────────────────────────────────────

def create_broadcast(youtube, date_str, clip_count):
    try:
        d = datetime.datetime.strptime(date_str, "%Y%m%d")
        label = d.strftime("%-d %B %Y")
    except Exception:
        label = date_str

    start_time = (datetime.datetime.utcnow() + datetime.timedelta(seconds=35)).strftime("%Y-%m-%dT%H:%M:%SZ")

    stream = youtube.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {"title": f"Scènes — {label}"},
            "cdn": {"frameRate": "30fps", "ingestionType": "rtmp", "resolution": "1080p"},
            "contentDetails": {"isReusable": False},
        },
    ).execute()

    stream_id = stream["id"]
    rtmp_url  = (stream["cdn"]["ingestionInfo"]["ingestionAddress"] + "/" +
                 stream["cdn"]["ingestionInfo"]["streamName"])

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": f"Musique et scènes mondaines — {label}",
                "description": (
                    f"Session du {label}.\n"
                    f"{clip_count} séquences, diffusion intégrale.\n\n"
                    "Images captées au fil du temps, accompagnées de musique douce."
                ),
                "scheduledStartTime": start_time,
            },
            "status": {
                "privacyStatus": "unlisted",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop":  True,
                "latencyPreference": "low",
                "enableDvr": False,
                "enableClosedCaptions": False,
            },
        },
    ).execute()

    broadcast_id = broadcast["id"]
    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    return broadcast_id, rtmp_url


# ── Stream one session ────────────────────────────────────────────────────────

def pick_music():
    tracks = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
    return random.choice(tracks) if tracks else None


def stream_session(clips, rtmp_url):
    music = pick_music()
    if not music:
        print("  ERROR: no music in", MUSIC_DIR, flush=True)
        return False

    with open(PLAYLIST_TMP, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")

    print(f"  {len(clips)} clips | music: {os.path.basename(music)}", flush=True)

    cmd = [
        "ffmpeg", "-y",
        "-re",
        "-f", "concat", "-safe", "0", "-i", PLAYLIST_TMP,
        "-stream_loop", "-1", "-i", music,
        "-filter_complex", "[1:a]volume=0.8,aformat=sample_rates=48000:channel_layouts=stereo[aout]",
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-shortest",
        "-f", "flv", rtmp_url,
    ]

    proc = subprocess.run(cmd, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        err = proc.stderr.decode()[-600:]
        print(f"  ffmpeg error:\n{err}", flush=True)
        return False
    return True


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print("=== Session Streamer (continuous) ===", flush=True)
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    youtube = get_youtube()
    state   = load_state()

    while True:
        sessions = find_sessions()
        pending  = {d: clips for d, clips in sorted(sessions.items())
                    if d not in state["done"] and len(clips) >= MIN_CLIPS}

        if not pending:
            print(f"No new sessions ready. Sleeping {POLL_INTERVAL}s...", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        for date_str, clips in pending.items():
            print(f"\n── Session {date_str} ({len(clips)} clips) ──", flush=True)

            # Retry broadcast creation with backoff
            broadcast_id, rtmp_url = None, None
            for attempt in range(5):
                try:
                    broadcast_id, rtmp_url = create_broadcast(youtube, date_str, len(clips))
                    break
                except Exception as e:
                    wait = 30 * (attempt + 1)
                    print(f"  Broadcast attempt {attempt+1} failed: {e} — retrying in {wait}s", flush=True)
                    time.sleep(wait)
            if not broadcast_id:
                print(f"  Giving up on {date_str} this cycle", flush=True)
                time.sleep(120)
                continue

            watch_url = f"https://www.youtube.com/watch?v={broadcast_id}"
            print(f"  {watch_url}", flush=True)
            print(f"  Waiting 35s for YouTube...", flush=True)
            time.sleep(35)

            ok = stream_session(clips, rtmp_url)

            if ok:
                state["done"][date_str] = {
                    "broadcast_id": broadcast_id,
                    "watch_url":    watch_url,
                    "clips":        len(clips),
                    "streamed_at":  datetime.datetime.utcnow().isoformat(),
                }
                save_state(state)
                print(f"  Done → {watch_url}", flush=True)
            else:
                print(f"  Failed — will retry next cycle", flush=True)

            # Short gap between sessions so musique kicks in briefly
            print("  Pausing 60s before next session...", flush=True)
            time.sleep(60)

        # Re-check immediately after a successful pass (more sessions may have arrived)


if __name__ == "__main__":
    main()
