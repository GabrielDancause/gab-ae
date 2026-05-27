#!/usr/bin/env python3
"""
ensure_broadcast.py -- called by stream_to_youtube.ps1 before every connect.
Checks if the current broadcast is still alive. If YouTube ended it, creates a new one.
Prints the stream key to stdout (one line). That's it.

Usage: python ensure_broadcast.py
Output: qdbm-aa2m-8e5c-qq1j-814g
"""

import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES       = ["https://www.googleapis.com/auth/youtube"]
SECRETS_FILE = Path(__file__).parent / "client_secrets.json"
TOKEN_FILE   = Path(__file__).parent / "token_youtube.json"

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--state-file", default=str(Path(__file__).parent / "broadcast_state.json"))
_args, _ = _ap.parse_known_args()
STATE_FILE = Path(_args.state_file)

DEAD_STATES  = {"complete", "revoked", "completeStarting"}


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


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def create_broadcast(yt):
    start = datetime.now(timezone.utc) + timedelta(seconds=30)
    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": "Toujours en Route -- 24/7 Live",
                "description": (
                    "24/7 live stream -- archival travel footage from around the world.\n"
                    "Ambient music, no commentary.\n\n"
                    "Gab's Adventures -- travel, walks, and life on the road.\n"
                    "Subscribe: https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w"
                ),
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

    broadcast_id = broadcast["id"]

    stream = yt.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {"title": "Toujours en Route -- ingest"},
            "cdn": {
                "frameRate":     "30fps",
                "ingestionType": "rtmp",
                "resolution":    "1080p",
            },
            "contentDetails": {"isReusable": True},
        },
    ).execute()

    stream_id  = stream["id"]
    stream_key = stream["cdn"]["ingestionInfo"]["streamName"]

    yt.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    print(f"New broadcast: https://www.youtube.com/watch?v={broadcast_id}", file=sys.stderr)
    return broadcast_id, stream_id, stream_key


def main():
    creds = get_credentials()
    yt    = build("youtube", "v3", credentials=creds)
    state = load_state()

    broadcast_id = state.get("broadcast_id")
    stream_key   = state.get("stream_key")
    need_new     = True

    # Check if existing broadcast is still usable
    if broadcast_id and stream_key:
        try:
            resp   = yt.liveBroadcasts().list(part="status", id=broadcast_id).execute()
            items  = resp.get("items", [])
            if items:
                status = items[0]["status"]["lifeCycleStatus"]
                print(f"Broadcast {broadcast_id}: {status}", file=sys.stderr)
                need_new = status in DEAD_STATES
            # No items = broadcast deleted
        except HttpError as e:
            print(f"Error checking broadcast: {e}", file=sys.stderr)

    if need_new:
        print("Creating new broadcast...", file=sys.stderr)
        broadcast_id, stream_id, stream_key = create_broadcast(yt)
        save_state({
            "broadcast_id": broadcast_id,
            "stream_id":    stream_id,
            "stream_key":   stream_key,
        })
    else:
        print("Reusing existing broadcast.", file=sys.stderr)

    # Print ONLY the stream key to stdout -- PS captures this
    print(stream_key)


if __name__ == "__main__":
    main()
