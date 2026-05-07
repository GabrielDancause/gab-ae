#!/usr/bin/env python3
"""
Download footage clips from a Google Drive folder, stitch them, strip audio.

Usage:
    python3 footage/stitch_and_upload.py --folder DRIVE_FOLDER_ID
    python3 footage/stitch_and_upload.py --folder DRIVE_FOLDER_ID --list
    python3 footage/stitch_and_upload.py --folder DRIVE_FOLDER_ID --output ~/Desktop/my_video.mp4

Output lands on ~/Desktop/stitched_output.mp4 by default.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR.parent / "shorts-uploader" / "credentials.json"
TOKEN_FILE = SCRIPT_DIR / "token.json"

VIDEO_MIME_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}


def get_credentials():
    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
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


def list_videos(drive_service, folder_id: str) -> list[dict]:
    videos = []
    page_token = None
    while True:
        resp = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
            pageSize=100,
            orderBy="name",
        ).execute()
        for f in resp.get("files", []):
            mime = f.get("mimeType", "")
            if mime in VIDEO_MIME_TYPES or mime.startswith("video/"):
                videos.append(f)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return videos


def download_video(drive_service, file_id: str, dest_path: str, label: str):
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            pct = int(status.progress() * 100)
            print(f"  [{label}] Downloading... {pct}%", end="\r")
    print()


def stitch(input_paths: list[str], output_path: str):
    concat_list = output_path + ".txt"
    with open(concat_list, "w") as f:
        for p in input_paths:
            f.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-an",           # strip audio
        "-c:v", "copy",  # no re-encode, fast
        output_path,
    ]

    print(f"\n  Stitching {len(input_paths)} clip(s)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(concat_list)

    if result.returncode != 0:
        print("  FFmpeg error:")
        print(result.stderr[-2000:])
        sys.exit(1)

    size_mb = Path(output_path).stat().st_size // 1_000_000
    print(f"  Done → {output_path} ({size_mb} MB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Google Drive folder ID")
    parser.add_argument("--output", default=str(Path.home() / "Desktop" / "stitched_output.mp4"))
    parser.add_argument("--list", action="store_true", help="List videos and exit")
    args = parser.parse_args()

    creds = get_credentials()
    drive_service = build("drive", "v3", credentials=creds)

    videos = list_videos(drive_service, args.folder)
    if not videos:
        print("No video files found in that Drive folder.")
        sys.exit(1)

    print(f"\nFound {len(videos)} video(s):")
    for v in videos:
        size_mb = int(v.get("size", 0)) // 1_000_000
        print(f"  {v['name']} ({size_mb} MB)")

    if args.list:
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        downloaded = []
        for i, video in enumerate(videos, 1):
            dest = os.path.join(tmp_dir, f"{i:02d}_{video['name']}")
            download_video(drive_service, video["id"], dest, f"{i}/{len(videos)}")
            downloaded.append(dest)

        stitch(downloaded, args.output)

    print(f"\n  Ready to upload manually: {args.output}")


if __name__ == "__main__":
    main()
