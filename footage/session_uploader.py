#!/usr/bin/env python3
"""
Session Uploader — runs on VPS.
Concatenates all MP4s from a session folder, strips audio, adds music, uploads unlisted to YouTube.

Usage:
  python3 session_uploader.py --session /opt/footage/1
  python3 session_uploader.py --all            # process all sessions not yet uploaded
  python3 session_uploader.py --list           # list sessions and their status
"""

import os
import sys
import json
import glob
import random
import argparse
import subprocess
import datetime
import tempfile

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN_FILE = "/opt/yt_token.json"
FOOTAGE_DIR = "/opt/footage"
MUSIC_DIR = "/opt/music"
STATE_FILE = "/opt/session_upload_state.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def get_youtube():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("Token invalid and cannot refresh. Re-run auth on Mac.")
    return build("youtube", "v3", credentials=creds)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def find_sessions():
    """Find all session folders under FOOTAGE_DIR that contain MP4s."""
    sessions = []
    for root, dirs, files in os.walk(FOOTAGE_DIR):
        mp4s = [f for f in files if f.upper().endswith(".MP4")]
        if mp4s:
            sessions.append(root)
    return sorted(set(sessions))


def find_mp4s(session_dir):
    mp4s = []
    for pat in ["*.MP4", "*.mp4", "*.MOV", "*.mov"]:
        mp4s.extend(glob.glob(os.path.join(session_dir, "**", pat), recursive=True))
    return sorted(mp4s)


def pick_music():
    tracks = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
    if not tracks:
        return None
    return random.choice(tracks)


def session_label(session_dir):
    """Human-readable label from path, e.g. /opt/footage/1/DCIM/DJI_001 -> session-1"""
    rel = os.path.relpath(session_dir, FOOTAGE_DIR)
    parts = rel.split(os.sep)
    return parts[0] if parts else rel


def concat_and_process(mp4s, output_path, music_path):
    """Concatenate all MP4s, strip original audio, add music track, output to file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fl:
        for mp4 in mp4s:
            fl.write(f"file '{mp4}'\n")
        filelist = fl.name

    music_args = []
    audio_filter = "anullsrc=r=48000:cl=stereo[aout]"
    audio_map = ["-map", "0:v", "-map", "[aout]"]

    if music_path:
        music_args = ["-stream_loop", "-1", "-i", music_path]
        audio_filter = "[1:a]volume=0.7,aformat=sample_rates=48000:channel_layouts=stereo[aout]"
        audio_map = ["-map", "0:v", "-map", "[aout]"]

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", filelist,
    ] + music_args + [
        "-filter_complex", audio_filter,
    ] + audio_map + [
        # Video — fast copy if possible, else re-encode to h264
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        # Audio
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-ac", "2",
        # Trim to YouTube max (12h = 43200s), avoids issues with very long sessions
        "-t", "43200",
        output_path,
    ]

    print(f"  Processing {len(mp4s)} clips -> {output_path}")
    print(f"  Music: {os.path.basename(music_path) if music_path else 'none (silent)'}")

    proc = subprocess.run(cmd, stderr=subprocess.PIPE)
    os.unlink(filelist)

    if proc.returncode != 0:
        print(f"  ffmpeg error:\n{proc.stderr.decode()[-2000:]}")
        return False
    return True


def upload_to_youtube(youtube, video_path, title, description=""):
    print(f"  Uploading: {title}")
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "19",  # Travel & Events
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=10 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.resumable_progress / status.total_size * 100)
            print(f"  Upload: {pct}%", end="\r")

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n  Uploaded: {url}")
    return video_id, url


def process_session(session_dir, youtube, state, force=False):
    label = session_label(session_dir)

    if label in state and not force:
        print(f"[SKIP] {label} already uploaded: {state[label]['url']}")
        return

    mp4s = find_mp4s(session_dir)
    if not mp4s:
        print(f"[SKIP] {label} — no MP4s found")
        return

    print(f"\n[SESSION] {label} — {len(mp4s)} clips")

    music = pick_music()
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    title = f"Scènes mondaines — {label} ({now})"

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        output_path = tf.name

    try:
        ok = concat_and_process(mp4s, output_path, music)
        if not ok:
            print(f"  [ERROR] Processing failed for {label}")
            return

        size_gb = os.path.getsize(output_path) / 1024**3
        print(f"  Output: {size_gb:.2f} GB")

        video_id, url = upload_to_youtube(youtube, output_path, title)

        state[label] = {
            "session_dir": session_dir,
            "video_id": video_id,
            "url": url,
            "clips": len(mp4s),
            "uploaded_at": datetime.datetime.now().isoformat(),
            "music": os.path.basename(music) if music else None,
        }
        save_state(state)
        print(f"  [DONE] {url}")

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", help="Process a specific session folder")
    parser.add_argument("--all", action="store_true", help="Process all unuploaded sessions")
    parser.add_argument("--list", action="store_true", help="List sessions and status")
    parser.add_argument("--force", action="store_true", help="Re-upload even if already done")
    args = parser.parse_args()

    state = load_state()

    if args.list:
        sessions = find_sessions()
        print(f"Found {len(sessions)} session(s):\n")
        for s in sessions:
            label = session_label(s)
            mp4s = find_mp4s(s)
            if label in state:
                print(f"  ✓ {label} ({len(mp4s)} clips) → {state[label]['url']}")
            else:
                print(f"  ○ {label} ({len(mp4s)} clips) — not uploaded")
        return

    youtube = get_youtube()

    if args.session:
        process_session(args.session, youtube, state, force=args.force)
    elif args.all:
        sessions = find_sessions()
        print(f"Processing {len(sessions)} session(s)...")
        for s in sessions:
            process_session(s, youtube, state, force=args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
