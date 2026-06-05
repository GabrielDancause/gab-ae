#!/usr/bin/env python3
"""
YouTube Live Stream Setup + FFmpeg Streamer
Streams SD card footage (action cam first, then drone) to YouTube unlisted.
"""

import os
import sys
import json
import subprocess
import datetime
import argparse

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CREDENTIALS_FILE = "/Users/gab/Desktop/gab-ae/shorts-uploader/credentials.json"
TOKEN_FILE = "/Users/gab/Desktop/gab-ae/footage/live_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/drive",
]

# Action cam (Untitled SD card) — streams first
ACTION_CAM_DIR = "/Volumes/Untitled/DCIM/100MEDIA"

# Drone (SD_Card) — streams second
DRONE_DIR = "/Volumes/SD_Card/DCIM/DJI_001"

# Filelist paths
FILELIST_PATH = "/tmp/stream_filelist.txt"


def get_youtube_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


def create_broadcast(youtube, title, privacy="unlisted"):
    now = datetime.datetime.utcnow()
    scheduled_start = (now + datetime.timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": title,
                "description": "Gab's Adventures — SD Card Footage Stream\nAction cam + drone footage from today.",
                "scheduledStartTime": scheduled_start,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "latencyPreference": "low",
                "enableDvr": False,
            },
        },
    ).execute()

    broadcast_id = broadcast["id"]
    broadcast_url = f"https://www.youtube.com/watch?v={broadcast_id}"
    print(f"\n✅ Broadcast created: {broadcast_url}")
    print(f"   ID: {broadcast_id}")
    return broadcast_id, broadcast_url


def create_stream(youtube):
    stream = youtube.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {
                "title": "Gab SD Card Stream",
            },
            "cdn": {
                "frameRate": "60fps",
                "ingestionType": "rtmp",
                "resolution": "1080p",
            },
            "contentDetails": {
                "isReusable": False,
            },
        },
    ).execute()

    stream_id = stream["id"]
    rtmp_url = stream["cdn"]["ingestionInfo"]["ingestionAddress"]
    stream_key = stream["cdn"]["ingestionInfo"]["streamName"]
    full_rtmp = f"{rtmp_url}/{stream_key}"

    print(f"\n✅ Stream created")
    print(f"   Stream ID: {stream_id}")
    print(f"   RTMP URL: {rtmp_url}")
    print(f"   Stream Key: {stream_key}")
    print(f"   Full RTMP: {full_rtmp}")
    return stream_id, full_rtmp, stream_key


def bind_broadcast(youtube, broadcast_id, stream_id):
    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()
    print(f"\n✅ Broadcast bound to stream")


def transition_broadcast(youtube, broadcast_id, status):
    youtube.liveBroadcasts().transition(
        broadcastStatus=status,
        id=broadcast_id,
        part="id,status",
    ).execute()
    print(f"\n✅ Broadcast transitioned to: {status}")


def make_filelist(action_cam_dir, drone_dir):
    lines = []

    # Action cam files first (sorted)
    ac_files = sorted(
        f for f in os.listdir(action_cam_dir) if f.upper().endswith(".MP4")
    )
    for fn in ac_files:
        path = os.path.join(action_cam_dir, fn)
        lines.append(f"file '{path}'")
    print(f"\n📹 Action cam files ({len(ac_files)}):")
    for fn in ac_files:
        print(f"   {fn}")

    # Drone files second (sorted)
    drone_files = sorted(
        f for f in os.listdir(drone_dir) if f.upper().endswith(".MP4")
    )
    for fn in drone_files:
        path = os.path.join(drone_dir, fn)
        lines.append(f"file '{path}'")
    print(f"\n🚁 Drone files ({len(drone_files)}):")
    for fn in drone_files[:5]:
        print(f"   {fn}")
    if len(drone_files) > 5:
        print(f"   ... and {len(drone_files) - 5} more")

    with open(FILELIST_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"\n✅ File list written to {FILELIST_PATH}")
    return FILELIST_PATH


def stream_to_youtube(filelist_path, rtmp_url):
    """Stream all footage to YouTube via FFmpeg at high quality 1080p60."""
    cmd = [
        "ffmpeg",
        "-re",                          # Read at native speed (real-time)
        "-f", "concat",                 # Concatenation demuxer
        "-safe", "0",
        "-i", filelist_path,
        # Video encoding — high quality 1080p60
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "9000k",
        "-maxrate", "9000k",
        "-bufsize", "18000k",
        "-pix_fmt", "yuv420p",
        "-g", "120",                    # Keyframe every 2s at 60fps
        "-s", "1920x1080",              # Downscale 4K → 1080p
        "-r", "60",                     # 60fps output
        # Audio encoding
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        # Output
        "-f", "flv",
        rtmp_url,
    ]

    print("\n🚀 Starting FFmpeg stream...")
    print("   Resolution: 1920x1080 @ 60fps")
    print("   Video bitrate: 9000 kbps")
    print("   Audio: AAC 192kbps 48kHz")
    print(f"   RTMP: {rtmp_url[:60]}...")
    print("\nPress Ctrl+C to stop the stream early.\n")

    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    except KeyboardInterrupt:
        print("\n⏹️  Stream interrupted by user")
        return 0


def stop_broadcast(youtube, broadcast_id):
    try:
        transition_broadcast(youtube, broadcast_id, "complete")
    except Exception as e:
        print(f"⚠️  Could not transition broadcast: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default=f"Gab's Adventures — Raw Footage {datetime.date.today()}")
    parser.add_argument("--stop-only", metavar="BROADCAST_ID", help="Just stop an existing broadcast")
    args = parser.parse_args()

    print("🎬 YouTube Live Stream — SD Card Footage")
    print("=" * 50)

    youtube = get_youtube_service()

    if args.stop_only:
        print(f"\nStopping broadcast: {args.stop_only}")
        stop_broadcast(youtube, args.stop_only)
        return

    # Create broadcast + stream
    title = args.title
    broadcast_id, broadcast_url = create_broadcast(youtube, title, privacy="unlisted")
    stream_id, full_rtmp, stream_key = create_stream(youtube)
    bind_broadcast(youtube, broadcast_id, stream_id)

    # Save info for cleanup
    info = {
        "broadcast_id": broadcast_id,
        "broadcast_url": broadcast_url,
        "stream_id": stream_id,
        "stream_key": stream_key,
        "full_rtmp": full_rtmp,
        "title": title,
    }
    info_path = "/tmp/live_stream_info.json"
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)
    print(f"\n💾 Stream info saved to {info_path}")
    print(f"\n🔗 Watch URL: {broadcast_url}")

    # Build file list
    filelist = make_filelist(ACTION_CAM_DIR, DRONE_DIR)

    # Wait for user to confirm
    print("\n" + "=" * 50)
    print("Ready to stream. YouTube will show the stream as LIVE once FFmpeg connects.")
    print(f"Stream URL: {broadcast_url}")
    input("\nPress ENTER to start streaming, or Ctrl+C to cancel...")

    # Stream
    result = stream_to_youtube(filelist, full_rtmp)

    # Stop broadcast when done
    print("\n📡 Footage done — ending broadcast...")
    stop_broadcast(youtube, broadcast_id)

    print(f"\n✅ Done! Stream ended.")
    print(f"   Watch replay at: {broadcast_url}")
    print(f"   Broadcast ID: {broadcast_id}")


if __name__ == "__main__":
    main()
