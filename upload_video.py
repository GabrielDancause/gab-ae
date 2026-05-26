#!/usr/bin/env python3
"""
Upload a video file to YouTube.

Usage:
    python upload_video.py --file output/2024-03-22_A-Day-in-Bangkok.mp4
    python upload_video.py --file output/clip.mp4 --title "Custom Title" --unlisted

Setup (one-time):
    1. Go to https://console.cloud.google.com/
    2. Create project -> Enable "YouTube Data API v3"
    3. APIs & Services -> Credentials -> Create OAuth 2.0 Client ID (Desktop App)
    4. Download JSON -> save as client_secrets.json in this folder
    5. First run opens a browser for authorization -> saves token.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SECRETS_FILE = Path(__file__).parent / "client_secrets.json"
TOKEN_FILE = Path(__file__).parent / "token_youtube.json"

CHANNEL_ID = "UCFUjYzVjRjweKhfs480xR4w"  # Gab's Adventures


def title_from_filename(path: Path) -> str:
    name = path.stem
    # "2024-03-22_A-Day-in-Bangkok" -> "A Day in Bangkok | March 2024"
    parts = name.split("_", 1)
    if len(parts) == 2 and re.match(r"\d{4}-\d{2}-\d{2}", parts[0]):
        date_str = parts[0]
        label = parts[1].replace("-", " ").title()
        year, month, _ = date_str.split("-")
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        month_name = months[int(month) - 1]
        return f"{label} | {month_name} {year}"
    return name.replace("-", " ").replace("_", " ").title()


def description_from_title(title: str) -> str:
    return (
        f"{title}\n\n"
        "Gab's Adventures — travel, walks, and life on the road.\n"
        "No commentary, just the footage with ambient music.\n\n"
        "Subscribe for more: https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w\n\n"
        "#travel #slowtv #adventure #walkingtour"
    )


def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRETS_FILE.exists():
                print(f"ERROR: {SECRETS_FILE} not found.")
                print("See setup instructions at the top of this file.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def upload(file_path: Path, title: str, description: str, privacy: str):
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["travel", "slowtv", "walkingvlog", "adventure", "gabsadventures"],
            "categoryId": "19",  # Travel & Events
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(file_path), chunksize=50 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"Uploading: {file_path.name}")
    print(f"Title: {title}")
    print(f"Privacy: {privacy}")
    print()

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  {pct}%", end="\r")

    video_id = response["id"]
    print(f"Done: https://www.youtube.com/watch?v={video_id}")
    return video_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Path to video file")
    ap.add_argument("--title", default=None, help="Override title")
    ap.add_argument("--description", default=None, help="Override description")
    ap.add_argument("--unlisted", action="store_true", help="Upload as unlisted (default: public)")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    title = args.title or title_from_filename(path)
    description = args.description or description_from_title(title)
    privacy = "unlisted" if args.unlisted else "public"

    upload(path, title, description, privacy)


if __name__ == "__main__":
    main()
