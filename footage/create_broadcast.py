#!/usr/bin/env python3
"""
Create a persistent YouTube live broadcast for Musique et scènes mondaines.
Run once on Mac. Saves RTMP URL to VPS at /opt/rtmp_url.txt.
"""

import os
import json
import subprocess
import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CREDENTIALS_FILE = "/Users/gab/Desktop/gab-ae/shorts-uploader/credentials.json"
TOKEN_FILE = "/Users/gab/Desktop/gab-ae/footage/live_token.json"
VPS = "root@138.201.21.95"
VPS_KEY = "/Users/gab/.ssh/id_ed25519"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
]


def get_youtube():
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
    return build("youtube", "v3", credentials=creds)


def main():
    print("Musique et scènes mondaines — Broadcast Setup")
    print("=" * 50)

    youtube = get_youtube()

    # Create a persistent stream key (reusable)
    stream = youtube.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {"title": "Musique et scènes mondaines — stream key"},
            "cdn": {
                "frameRate": "60fps",
                "ingestionType": "rtmp",
                "resolution": "1080p",
            },
            "contentDetails": {"isReusable": True},
        },
    ).execute()

    stream_id = stream["id"]
    rtmp_base = stream["cdn"]["ingestionInfo"]["ingestionAddress"]
    stream_key = stream["cdn"]["ingestionInfo"]["streamName"]
    rtmp_url = f"{rtmp_base}/{stream_key}"

    print(f"Stream key created: {stream_id}")

    # Schedule start in 2 minutes
    start_time = (datetime.datetime.utcnow() + datetime.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": "Musique et scènes mondaines",
                "description": (
                    "Scènes du quotidien — Paris et ailleurs.\n"
                    "Images captées au fil du temps, accompagnées de musique douce.\n\n"
                    "Diffusion continue 24h/24."
                ),
                "scheduledStartTime": start_time,
            },
            "status": {
                "privacyStatus": "unlisted",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,  # never auto-stop
                "latencyPreference": "normal",
                "enableDvr": False,
                "enableClosedCaptions": False,
            },
        },
    ).execute()

    broadcast_id = broadcast["id"]
    watch_url = f"https://www.youtube.com/watch?v={broadcast_id}"

    # Bind
    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    print(f"\nBroadcast created!")
    print(f"  Watch URL:    {watch_url}")
    print(f"  Broadcast ID: {broadcast_id}")
    print(f"  RTMP URL:     {rtmp_url[:80]}...")

    # Save info locally
    info = {
        "broadcast_id": broadcast_id,
        "watch_url": watch_url,
        "stream_id": stream_id,
        "rtmp_url": rtmp_url,
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    with open("/tmp/broadcast_info.json", "w") as f:
        json.dump(info, f, indent=2)
    print(f"\nSaved to /tmp/broadcast_info.json")

    # Push RTMP URL to VPS
    print("\nPushing RTMP URL to VPS...")
    subprocess.run([
        "ssh", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=no", VPS,
        f"echo '{rtmp_url}' > /opt/rtmp_url.txt && echo 'Saved.'"
    ], check=True)

    print(f"\nAll done. Watch URL:\n  {watch_url}")
    print("\nStart the VPS streamer:")
    print(f"  ssh -i {VPS_KEY} {VPS}")
    print("  systemctl start musique")


if __name__ == "__main__":
    main()
