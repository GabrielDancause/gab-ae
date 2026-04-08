#!/usr/bin/env python3
"""
Upload YouTube Shorts from a Google Drive folder.

Expects a Drive folder with two subfolders:
  01-todo  — videos waiting to be uploaded
  02-done  — videos are moved here after successful upload

Usage:
    python upload_shorts.py              # upload next video (default)
    python upload_shorts.py --count 3    # upload next 3 videos
    python upload_shorts.py --list       # list todo/done videos

Setup: see README_SETUP.md in this folder.

YouTube API quota: each upload costs ~1,600 units. Default daily limit is
10,000 units, so 6 uploads/day uses 9,600 units — very close to the limit.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ── Config ────────────────────────────────────────────────────────────────────

# Parent folder containing 01-todo and 02-done
PARENT_FOLDER_ID = "1SujQQeplJmOq_tRMUul0N7xz6_Nn-yjM"

SCOPES = [
    "https://www.googleapis.com/auth/drive",          # need write to move files
    "https://www.googleapis.com/auth/youtube.upload",
]

SCRIPT_DIR = Path(__file__).parent
TOKEN_FILE = SCRIPT_DIR / "token.json"
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"

VIDEO_MIME_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_credentials():
    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
        print("Download it from Google Cloud Console > APIs & Services > Credentials.")
        sys.exit(1)

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return creds


# ── Google Drive ──────────────────────────────────────────────────────────────

def find_subfolder(drive_service, parent_id: str, name: str) -> str | None:
    """Find a subfolder by name inside parent_id. Returns folder ID or None."""
    resp = drive_service.files().list(
        q=f"'{parent_id}' in parents and name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
        pageSize=5,
    ).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def list_videos_in_folder(drive_service, folder_id: str) -> list[dict]:
    """Return all video files in folder_id, ordered by name."""
    videos = []
    page_token = None

    while True:
        resp = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size, parents)",
            pageToken=page_token,
            pageSize=100,
            orderBy="name",
        ).execute()

        for f in resp.get("files", []):
            if f.get("mimeType") in VIDEO_MIME_TYPES or f.get("mimeType", "").startswith("video/"):
                videos.append(f)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return videos


def move_file_to_folder(drive_service, file_id: str, from_folder_id: str, to_folder_id: str):
    """Move a file from one Drive folder to another."""
    drive_service.files().update(
        fileId=file_id,
        addParents=to_folder_id,
        removeParents=from_folder_id,
        fields="id, parents",
    ).execute()


def download_video(drive_service, file_id: str, dest_path: str):
    """Download a Drive file to dest_path with progress."""
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            pct = int(status.progress() * 100)
            print(f"  Downloading... {pct}%", end="\r")
    print()


# ── YouTube ───────────────────────────────────────────────────────────────────

def upload_to_youtube(youtube_service, video_path: str, title: str) -> str:
    """Upload video as a Short. Returns the YouTube video ID."""
    clean_title = Path(title).stem
    # Strip leading number prefix like "302 - " or "DONE-"
    clean_title = re.sub(r"^\d+\s*[-–—]\s*", "", clean_title)
    clean_title = re.sub(r"^DONE[-\s]*", "", clean_title, flags=re.IGNORECASE)
    clean_title = clean_title.strip()[:100]

    body = {
        "snippet": {
            "title": clean_title,
            "description": "#Shorts",
            "tags": ["Shorts"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    request = youtube_service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Uploading...  {pct}%", end="\r")

    print()
    return response["id"]


# ── Commands ──────────────────────────────────────────────────────────────────

def resolve_folders(drive_service):
    """Find 01-todo and 02-done folder IDs. Exits if not found."""
    todo_id = find_subfolder(drive_service, PARENT_FOLDER_ID, "01-todo")
    done_id = find_subfolder(drive_service, PARENT_FOLDER_ID, "02-done")

    if not todo_id:
        print("ERROR: Could not find '01-todo' subfolder in the Drive folder.")
        sys.exit(1)
    if not done_id:
        print("ERROR: Could not find '02-done' subfolder in the Drive folder.")
        sys.exit(1)

    return todo_id, done_id


def cmd_list(drive_service):
    todo_id, done_id = resolve_folders(drive_service)

    todo_videos = list_videos_in_folder(drive_service, todo_id)
    done_videos = list_videos_in_folder(drive_service, done_id)

    print(f"\n  To upload : {len(todo_videos)}")
    print(f"  Done      : {len(done_videos)}\n")

    if todo_videos:
        print("Pending (01-todo):")
        for v in todo_videos[:20]:
            size_mb = int(v.get("size", 0)) // 1_000_000
            print(f"  {v['name']} ({size_mb} MB)")
        if len(todo_videos) > 20:
            print(f"  ... and {len(todo_videos) - 20} more")

    if done_videos:
        print("\nDone (02-done):")
        for v in done_videos[:10]:
            print(f"  {v['name']}")
        if len(done_videos) > 10:
            print(f"  ... and {len(done_videos) - 10} more")


def cmd_upload(drive_service, youtube_service, count: int):
    todo_id, done_id = resolve_folders(drive_service)
    pending = list_videos_in_folder(drive_service, todo_id)

    if not pending:
        print("Nothing to upload — 01-todo is empty.")
        return

    to_upload = pending[:count]
    print(f"Uploading {len(to_upload)} of {len(pending)} pending video(s)...\n")

    for i, video in enumerate(to_upload, 1):
        name = video["name"]
        size_mb = int(video.get("size", 0)) // 1_000_000
        print(f"[{i}/{len(to_upload)}] {name} ({size_mb} MB)")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            print(f"  Downloading from Drive...")
            download_video(drive_service, video["id"], tmp_path)

            print(f"  Uploading to YouTube...")
            yt_id = upload_to_youtube(youtube_service, tmp_path, name)

            # Move from 01-todo → 02-done
            print(f"  Moving to 02-done...")
            move_file_to_folder(drive_service, video["id"], todo_id, done_id)

            print(f"  Done! https://youtu.be/{yt_id}\n")

        except HttpError as e:
            print(f"  ERROR: {e}")
            if "quotaExceeded" in str(e):
                print("  YouTube API quota exceeded. Try again tomorrow.")
                break
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if i < len(to_upload):
            time.sleep(3)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload Shorts from Google Drive to YouTube")
    parser.add_argument("--count", type=int, default=1,
                        help="Number of videos to upload (default: 1)")
    parser.add_argument("--list", action="store_true",
                        help="List todo/done videos")
    args = parser.parse_args()

    creds = get_credentials()
    drive_service = build("drive", "v3", credentials=creds)
    youtube_service = build("youtube", "v3", credentials=creds)

    if args.list:
        cmd_list(drive_service)
    else:
        cmd_upload(drive_service, youtube_service, args.count)


if __name__ == "__main__":
    main()
