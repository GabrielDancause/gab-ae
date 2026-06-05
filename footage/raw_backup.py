#!/usr/bin/env python3
"""
raw_backup.py — Upload a folder of raw footage to a private Internet Archive item.

Files are uploaded as-is (no transcoding, no re-encoding). The IA item is set to
private + noindex so it won't appear in search or be publicly accessible.
You can flip it to public later via the IA web interface or `ia metadata`.

Usage:
  python3 footage/raw_backup.py "/path/to/folder" --ia-id my-raw-backup-2026-05
  python3 footage/raw_backup.py "/path/to/folder" --ia-id my-raw-backup-2026-05 --title "Paris — Raw Footage May 2026"
  python3 footage/raw_backup.py "/path/to/folder" --ia-id my-id --exts .mp4 .mov .MOV .MP4 .dng .jpg
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_EXTS = {'.mov', '.mp4', '.MP4', '.MOV', '.MTS', '.m2ts', '.avi', '.mkv'}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder',              help='Folder of raw footage to back up')
    parser.add_argument('--ia-id',  required=True,
                        help='Internet Archive item identifier (must be unique, lowercase, hyphens ok)')
    parser.add_argument('--title',  default=None,
                        help='Title for the IA item (default: folder name)')
    parser.add_argument('--exts',   nargs='+', default=None,
                        help=f'File extensions to include (default: {" ".join(sorted(DEFAULT_EXTS))})')
    parser.add_argument('--public', action='store_true',
                        help='Make the IA item public instead of private')
    args = parser.parse_args()

    src_dir = Path(args.folder).expanduser().resolve()
    if not src_dir.is_dir():
        print(f"ERROR: not a folder: {src_dir}")
        sys.exit(1)

    exts = set(args.exts) if args.exts else DEFAULT_EXTS
    files = sorted([f for f in src_dir.iterdir()
                    if f.suffix in exts and not f.name.startswith('.')])

    if not files:
        print(f"No matching files found in {src_dir}")
        sys.exit(1)

    ia_id    = args.ia_id
    ia_title = args.title or src_dir.name
    total_gb = sum(f.stat().st_size for f in files) / 1024 ** 3

    log(f"Found {len(files)} file(s)  ({total_gb:.1f} GB)")
    log(f"IA item:  {ia_id}")
    log(f"Title:    {ia_title}")
    log(f"Access:   {'public' if args.public else 'private (noindex)'}")
    log("Uploading...")

    ia_cmd = [
        'ia', 'upload', ia_id, *[str(f) for f in files],
        '--metadata=mediatype:movies',
        f'--metadata=title:{ia_title}',
    ]
    if not args.public:
        ia_cmd += ['--metadata=access:private', '--metadata=noindex:true']

    result = subprocess.run(ia_cmd, cwd=str(src_dir))
    if result.returncode != 0:
        log("ERROR: ia upload failed")
        sys.exit(1)

    log(f"\n✓ Done — https://archive.org/details/{ia_id}")
    if not args.public:
        log("  (private — only visible when logged into your IA account)")


if __name__ == '__main__':
    main()
