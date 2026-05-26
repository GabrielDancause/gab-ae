#!/usr/bin/env python3
"""
Create a YouTube Live broadcast and return the stream key.

Usage:
    python create_livestream.py
    python create_livestream.py --title "Toujours en Route" --description "24/7 live"

Creates a persistent live broadcast on Gab's Adventures channel.
Prints the stream key to use in stream_to_youtube.ps1.
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SECRETS_FILE = Path(__file__).parent / "client_secrets.json"
TOKEN_FILE   = Path(__file__).parent / "token_youtube.json"


def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def create_live(title: str, description: str):
    yt = build("youtube", "v3", credentials=get_credentials())

    # --- 1. Create the broadcast ---
    start = datetime.now(timezone.utc) + timedelta(seconds=30)
    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,
                "enableDvr": True,
                "latencyPreference": "normal",
                "recordFromStart": True,
                "startWithSlate": False,
            },
        },
    ).execute()

    broadcast_id  = broadcast["id"]
    broadcast_url = f"https://www.youtube.com/watch?v={broadcast_id}"
    print(f"Broadcast created: {broadcast_url}")

    # --- 2. Create the stream ingestion point ---
    stream = yt.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {
                "title": f"{title} -- ingest",
            },
            "cdn": {
                "frameRate":     "30fps",
                "ingestionType": "rtmp",
                "resolution":    "2160p",
            },
            "contentDetails": {
                "isReusable": True,
            },
        },
    ).execute()

    stream_id  = stream["id"]
    stream_key = stream["cdn"]["ingestionInfo"]["streamName"]
    rtmp_url   = stream["cdn"]["ingestionInfo"]["ingestionAddress"]

    print(f"Stream key:  {stream_key}")
    print(f"RTMP URL:    {rtmp_url}/{stream_key}")

    # --- 3. Bind broadcast to stream ---
    yt.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    print(f"\nAll set. Update stream_to_youtube.ps1:")
    print(f'  $StreamKey = "{stream_key}"')
    print(f"\nBroadcast will go live automatically when ffmpeg connects.")
    print(f"Watch it at: {broadcast_url}")

    return stream_key, broadcast_url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title",       default="Toujours en Route -- 24/7 Live")
    ap.add_argument("--description", default=(
        "24/7 live stream -- archival travel footage from around the world.\n"
        "Ambient music, no commentary.\n\n"
        "Gab's Adventures -- travel, walks, and life on the road.\n"
        "Subscribe: https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w"
    ))
    args = ap.parse_args()
    create_live(args.title, args.description)


if __name__ == "__main__":
    main()
