#!/usr/bin/env python3
"""
One-shot repair: generate missing Meta glasses variants for folder
1oY_24nVrwlSJPM1CMCZgu2r8MSa7p3NA.

Generates: native (1440x1920, no crop) and 9x16 (centre-cropped).
Pillarbox is dropped from the pipeline; 16x9 was already uploaded.
"""

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

FOLDER_ID      = '1oY_24nVrwlSJPM1CMCZgu2r8MSa7p3NA'
FOLDER_NAME    = '2026-05-94 - phone glasses and action cam in Paris'
DRIVE_TOKEN    = '/opt/gab/footage/token.json'
MUSIC_LIBRARY  = '/opt/gab/music/library.json'
READY_LONG_DIR = '/opt/gab/footage/ready_long'
READY_LONG_Q   = '/opt/gab/footage/ready_long_queue.json'
WORKDIR        = '/tmp/long_repair'
META_PREFIXES  = ('video-', 'od_video-')
NORM_VF        = 'scale=1440:-2,pad=1440:1920:0:(1920-ih)/2:black'

VARIANTS = [
    ('native', 'scale=1440:1920'),
    ('9x16',   'crop=ih*9/16:ih:(iw-ih*9/16)/2:0'),
]

os.makedirs(WORKDIR, exist_ok=True)


def get_duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def download_file(svc, file_id, dest):
    from googleapiclient.http import MediaIoBaseDownload
    request = svc.files().get_media(fileId=file_id)
    with open(dest, 'wb') as fh:
        dl = MediaIoBaseDownload(fh, request, chunksize=64 * 1024 * 1024)
        done = False
        while not done:
            status, done = dl.next_chunk()
            if status:
                print(f"  {int(status.progress() * 100)}%", end='\r', flush=True)
    print()


def concat_clips(paths, dst):
    lst = dst + '.txt'
    with open(lst, 'w') as f:
        for p in paths:
            f.write(f"file '{p}'\n")
    r = subprocess.run(
        ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', lst,
         '-c', 'copy', dst],
        capture_output=True, text=True)
    Path(lst).unlink(missing_ok=True)
    return r.returncode == 0


def mix_satie(src, dst):
    library = json.loads(Path(MUSIC_LIBRARY).read_text())
    track = random.choice(library)
    music_path = track.get('path') or track.get('file')
    vid_dur = get_duration(src)
    music_dur = get_duration(music_path)
    max_offset = max(0, music_dur - vid_dur - 10)
    offset = random.uniform(0, max_offset) if max_offset > 0 else 0
    print(f"  Music: {track.get('filename', '?')} offset={offset:.0f}s")
    r = subprocess.run([
        'ffmpeg', '-y',
        '-i', src,
        '-ss', str(offset), '-stream_loop', '-1', '-i', music_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-filter:a', 'volume=0.5',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(vid_dur), dst,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Audio mix error: {r.stderr[-200:]}")
        return False
    gb = os.path.getsize(dst) / 1024**3
    print(f"  With audio: {gb:.2f} GB")
    return True


def main():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    svc = build('drive', 'v3', credentials=creds, cache_discovery=False)

    # List Meta glasses files
    print(f"Listing files in folder {FOLDER_ID}...", flush=True)
    results = svc.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields='files(id,name,size)',
        pageSize=200,
    ).execute()
    files = results.get('files', [])
    meta_files = [f for f in files if any(f['name'].startswith(p) for p in META_PREFIXES)]
    print(f"Found {len(meta_files)} Meta glasses clips", flush=True)

    if not meta_files:
        print("No Meta glasses files found — folder may have been moved?")
        sys.exit(1)

    # Download (skip if already present)
    raw_paths = []
    for f in sorted(meta_files, key=lambda x: x['name']):
        dst = os.path.join(WORKDIR, f['name'])
        if Path(dst).exists() and Path(dst).stat().st_size > 0:
            print(f"  Cached: {f['name']}", flush=True)
        else:
            size_mb = int(f.get('size', 0)) // 1024 // 1024
            print(f"  Downloading {f['name']} ({size_mb} MB)...", flush=True)
            download_file(svc, f['id'], dst)
        raw_paths.append(dst)

    # Normalize (skip if cached norm exists and is non-zero)
    print(f"\nNormalizing {len(raw_paths)} clips to 1440x1920...", flush=True)
    norm_paths = []
    for p in raw_paths:
        norm = p + '.norm.mp4'
        if Path(norm).exists() and Path(norm).stat().st_size > 0:
            print(f"  Cached norm: {Path(p).name}", flush=True)
            norm_paths.append(norm)
            continue
        r = subprocess.run([
            'ffmpeg', '-y', '-i', p,
            '-vf', NORM_VF,
            '-c:v', 'libx264', '-crf', '20', '-preset', 'ultrafast', '-an',
            norm,
        ], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  Normalized: {Path(p).name}", flush=True)
            norm_paths.append(norm)
        else:
            print(f"  Norm error {Path(p).name}: {r.stderr[-100:]}", flush=True)

    if not norm_paths:
        print("All normalizations failed.")
        sys.exit(1)
    print(f"  {len(norm_paths)}/{len(raw_paths)} normalized OK", flush=True)

    # Stitch
    stitched = os.path.join(WORKDIR, f'meta_stitched_{FOLDER_ID}.mp4')
    if Path(stitched).exists() and Path(stitched).stat().st_size > 0:
        print(f"\nCached stitch: {Path(stitched).name}", flush=True)
    else:
        print(f"\nStitching {len(norm_paths)} clips...", flush=True)
        if len(norm_paths) == 1:
            shutil.copy2(norm_paths[0], stitched)
        elif not concat_clips(norm_paths, stitched):
            print("Stitch failed.")
            sys.exit(1)

    dur = get_duration(stitched)
    print(f"  Stitched: {os.path.getsize(stitched)/1024**3:.2f} GB, {dur:.0f}s", flush=True)

    # Fan out to variants
    new_entries = []
    for variant_name, vf in VARIANTS:
        print(f"\n--- Variant: {variant_name} ---", flush=True)
        preview_dur = min(dur, 180)
        preview = os.path.join(WORKDIR, f'meta_{variant_name}_{FOLDER_ID}.mp4')
        print(f"  Applying filter, cutting to {preview_dur:.0f}s...", flush=True)
        r = subprocess.run([
            'ffmpeg', '-y', '-i', stitched,
            '-vf', vf, '-t', str(preview_dur),
            '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-an',
            preview,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  Preview error: {r.stderr[-300:]}", flush=True)
            continue
        print(f"  Preview: {os.path.getsize(preview)/1024**2:.0f} MB", flush=True)

        audio_out = os.path.join(READY_LONG_DIR, f'{FOLDER_ID}_meta_{variant_name}.mp4')
        print(f"  Mixing Satie...", flush=True)
        if not mix_satie(preview, audio_out):
            print("  Music mix failed.", flush=True)
            Path(preview).unlink(missing_ok=True)
            continue
        Path(preview).unlink(missing_ok=True)

        new_entries.append({
            'drive_folder_id': FOLDER_ID,
            'folder_name':     FOLDER_NAME,
            'location':        'phone glasses and action cam in Paris',
            'type':            f'meta_preview_{variant_name}',
            'title':           f'phone glasses and action cam in Paris POV — {variant_name} 👓',
            'description':     f'Meta glasses POV footage in phone glasses and action cam in Paris. Preview variant: {variant_name}. Pick your favourite format.',
            'local_file':      audio_out,
            'ts_processed':    __import__('datetime').datetime.utcnow().isoformat() + 'Z',
            'uploaded':        False,
        })
        print(f"  Saved: {audio_out}", flush=True)

    # Clean up stitch and norms
    Path(stitched).unlink(missing_ok=True)
    for p in norm_paths:
        Path(p).unlink(missing_ok=True)

    if not new_entries:
        print("\nNo variants produced.")
        sys.exit(1)

    # Append to queue
    q_path = Path(READY_LONG_Q)
    q = json.loads(q_path.read_text()) if q_path.exists() else []
    q.extend(new_entries)
    q_path.write_text(json.dumps(q, indent=2))
    print(f"\nQueued {len(new_entries)} variant(s). Total long-form queue: {len(q)}", flush=True)


if __name__ == '__main__':
    main()
