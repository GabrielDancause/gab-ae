#!/usr/bin/env python3
"""
Daily backup of catalog.db to Google Drive.
Keeps last 7 backups, deletes older ones automatically.

Usage: python3 backup_catalog.py
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DRIVE_TOKEN   = '/opt/gab/footage/token.json'
CATALOG_DB    = '/opt/gab/footage/catalog.db'
BACKUP_FOLDER = 'catalog-backups'   # folder name in Drive root
KEEP_BACKUPS  = 7


def get_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds)


def get_or_create_folder(svc, name):
    """Find or create a folder in Drive root."""
    results = svc.files().list(
        q="name='{}' and mimeType='application/vnd.google-apps.folder' and trashed=false".format(name),
        fields="files(id, name)"
    ).execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    folder = svc.files().create(
        body={'name': name, 'mimeType': 'application/vnd.google-apps.folder'},
        fields='id'
    ).execute()
    return folder['id']


def main():
    if not Path(CATALOG_DB).exists():
        print("catalog.db not found — nothing to back up")
        sys.exit(1)

    svc = get_service()

    # Get or create backup folder
    folder_id = get_or_create_folder(svc, BACKUP_FOLDER)

    # Upload with datestamp
    stamp     = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')
    filename  = 'catalog_{}.db'.format(stamp)
    size_mb   = os.path.getsize(CATALOG_DB) / 1024 / 1024

    print("Uploading {} ({:.1f} MB) to Drive/{}/...".format(filename, size_mb, BACKUP_FOLDER))

    media = MediaFileUpload(CATALOG_DB, mimetype='application/octet-stream', resumable=True)
    file  = svc.files().create(
        body={'name': filename, 'parents': [folder_id]},
        media_body=media,
        fields='id'
    ).execute()

    print("Uploaded: {} (id={})".format(filename, file['id']))

    # Rotate — delete backups older than KEEP_BACKUPS
    backups = svc.files().list(
        q="'{}' in parents and name contains 'catalog_' and trashed=false".format(folder_id),
        fields="files(id, name, createdTime)",
        orderBy="createdTime desc"
    ).execute().get('files', [])

    to_delete = backups[KEEP_BACKUPS:]
    for old in to_delete:
        svc.files().delete(fileId=old['id']).execute()
        print("Deleted old backup: {}".format(old['name']))

    print("Done. {} backups kept.".format(min(len(backups), KEEP_BACKUPS)))


if __name__ == '__main__':
    main()
