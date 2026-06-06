#!/usr/bin/env python3
"""
session_stream.py — One-shot ordered session broadcast.

Encodes all clips from a folder in chronological order (full duration,
no random cuts), streams them once back-to-back to a new YouTube Live
broadcast, then ends the stream automatically when the last clip finishes.

Usage:
    python3 footage/session_stream.py --base "/Volumes/obiwan/North Hatley" --title "North Hatley Bike Ride"
    python3 footage/session_stream.py --base "/path/to/folder" --title "My Session" --encode-only
    python3 footage/session_stream.py --base "/path/to/folder" --title "My Session" --out /tmp/session_clips

Options:
    --base DIR        Source footage folder (required)
    --title TEXT      YouTube broadcast title (required)
    --out DIR         Where to store encoded clips (default: /tmp/session_stream)
    --desc TEXT       YouTube description
    --parallel N      Parallel encoding workers (default: 4)
    --encode-only     Encode clips but don't create broadcast or stream
    --privacy         public / unlisted / private (default: unlisted)
"""

import argparse, os, glob, subprocess, json, datetime, signal, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CREDENTIALS_FILE = "/Users/gab/Desktop/gab-ae/shorts-uploader/credentials.json"
TOKEN_FILE       = "/Users/gab/Desktop/gab-ae/footage/live_token.json"
SERVER           = "root@138.201.21.95"
SERVER_CLIP_DIR  = "/tmp/session_stream_clips"
SERVER_PLAYLIST  = "/tmp/session_stream_playlist.txt"
MUSIC_DIR        = "/opt/music"
SCOPES           = ["https://www.googleapis.com/auth/youtube"]


# ── YouTube ───────────────────────────────────────────────────────────────────

def get_youtube():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def create_broadcast(title, description, privacy):
    yt = get_youtube()

    stream = yt.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {"title": f"{title} — stream key"},
            "cdn": {"frameRate": "60fps", "ingestionType": "rtmp", "resolution": "1080p"},
            "contentDetails": {"isReusable": False},
        }
    ).execute()
    rtmp_url = (stream["cdn"]["ingestionInfo"]["ingestionAddress"] + "/"
                + stream["cdn"]["ingestionInfo"]["streamName"])

    start = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": start,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,   # ends broadcast when stream stops
                "latencyPreference": "normal",
                "enableDvr": True,
            },
        }
    ).execute()

    yt.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast["id"],
        streamId=stream["id"],
    ).execute()

    return broadcast["id"], rtmp_url


def end_broadcast(broadcast_id):
    yt = get_youtube()
    try:
        yt.liveBroadcasts().transition(
            broadcastStatus="complete",
            id=broadcast_id,
            part="id,status"
        ).execute()
        print(f"[youtube] Broadcast {broadcast_id} ended.", flush=True)
    except Exception as e:
        print(f"[youtube] Could not end broadcast: {e}", flush=True)


# ── Encoding ──────────────────────────────────────────────────────────────────

def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, timeout=15)
    d = json.loads(r.stdout)
    dur = float(d["format"]["duration"])
    vs = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    return dur, int(vs.get("width", 0)), int(vs.get("height", 0))


def build_vf(w, h):
    if w == h:
        return "crop={}:{}:0:{},scale=1920:1080".format(
            w, int(w * 9 / 16), int((h - w * 9 / 16) / 2))
    elif w < h:
        new_w = int(h * 16 / 9)
        x_off = int((w - new_w) / 2)
        return "crop={}:{}:{}:0,scale=1920:1080".format(new_w, h, x_off)
    else:
        return "scale=1920:1080"


def encode_full(src, out):
    """Encode entire source file (no trimming)."""
    if os.path.exists(out):
        print(f"  skip (exists): {os.path.basename(src)}", flush=True)
        return True
    try:
        _, w, h = probe(src)
    except Exception as e:
        print(f"  probe failed {os.path.basename(src)}: {e}", flush=True)
        return False

    vf = build_vf(w, h)
    tmp = out + ".wip.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "videotoolbox",
        "-i", src,
        "-vf", vf,
        "-c:v", "h264_videotoolbox",
        "-b:v", "8000k", "-maxrate", "8000k", "-bufsize", "16000k",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", "60", "-g", "120", "-an",
        tmp,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        os.rename(tmp, out)
        print(f"  ✓ {os.path.basename(src)}", flush=True)
        return True
    if os.path.exists(tmp):
        os.unlink(tmp)
    print(f"  ✗ {os.path.basename(src)} FAILED", flush=True)
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="One-shot ordered session broadcast")
    parser.add_argument("--base",         required=True, help="Source footage folder")
    parser.add_argument("--title",        required=True, help="YouTube broadcast title")
    parser.add_argument("--out",          default="/tmp/session_stream", help="Temp dir for encoded clips — deleted after stream ends")
    parser.add_argument("--desc",         default="", help="YouTube description")
    parser.add_argument("--parallel",     type=int, default=4, help="Parallel encoding workers")
    parser.add_argument("--encode-only",  action="store_true", help="Encode but don't stream")
    parser.add_argument("--privacy",      default="unlisted", choices=["public","unlisted","private"])
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # Gather sources in chronological order
    sources = []
    for pat in ["*.MP4", "*.mp4", "*.MOV", "*.mov"]:
        sources += glob.glob(os.path.join(args.base, "**", pat), recursive=True)
    sources = sorted(set(s for s in sources if not s.upper().endswith(".LRF")))

    if not sources:
        print(f"No video files found in {args.base}")
        sys.exit(1)

    print(f"Found {len(sources)} source files in chronological order")

    # Encode all files in order
    print("Encoding...")
    encoded = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = {
            ex.submit(encode_full, src, os.path.join(args.out, f"{i:04d}_{os.path.basename(src)}")): (i, src)
            for i, src in enumerate(sources)
        }
        results = {}
        for fut in as_completed(futs):
            i, src = futs[fut]
            if fut.result():
                results[i] = os.path.join(args.out, f"{i:04d}_{os.path.basename(src)}")

    # Rebuild in order
    encoded = [results[i] for i in sorted(results)]
    print(f"\n{len(encoded)}/{len(sources)} clips encoded.")

    if not encoded:
        print("Nothing encoded, aborting.")
        sys.exit(1)

    if args.encode_only:
        print(f"--encode-only set. Clips in: {args.out}")
        return

    # Create YouTube broadcast
    print("\nCreating YouTube broadcast...")
    description = args.desc or f"Session recorded on {os.path.basename(args.base)}.\nPlaying back {len(encoded)} clips in chronological order."
    broadcast_id, rtmp_url = create_broadcast(args.title, description, args.privacy)
    watch_url = f"https://www.youtube.com/watch?v={broadcast_id}"
    print(f"  Watch URL: {watch_url}")

    # Push clips to server
    print(f"\nRsyncing {len(encoded)} clips to server...")
    subprocess.run([
        "rsync", "-av", "--delete", "--exclude", "*.wip.mp4",
        args.out + "/",
        f"{SERVER}:{SERVER_CLIP_DIR}/"
    ], check=True)

    # Write ordered playlist on server
    playlist_lines = "\n".join(f"file '{SERVER_CLIP_DIR}/{os.path.basename(p)}'" for p in encoded)
    subprocess.run([
        "ssh", "-o", "StrictHostKeyChecking=no", SERVER,
        f"printf '{playlist_lines}' > {SERVER_PLAYLIST} && echo 'Playlist written: $(wc -l < {SERVER_PLAYLIST}) entries'"
    ], check=True)

    # Stream — no -stream_loop, so it ends naturally
    print(f"\nStreaming to YouTube... ({len(encoded)} clips)")
    print(f"Watch: {watch_url}\n")

    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", SERVER,
        " ".join([
            "ffmpeg", "-y", "-re",
            "-f", "concat", "-safe", "0", "-i", SERVER_PLAYLIST,
            "-stream_loop", "-1", "-i", f"$(ls {MUSIC_DIR}/*.mp3 | shuf -n1)",
            "-filter_complex",
            '"[0:v]setpts=PTS-STARTPTS[vout];[1:a]volume=0.8,aformat=sample_rates=48000:channel_layouts=stereo[aout]"',
            "-map", '"[vout]"', "-map", '"[aout]"',
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-maxrate", "6800k", "-bufsize", "13600k",
            "-pix_fmt", "yuv420p", "-r", "60", "-g", "120",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-f", "flv", f'"{rtmp_url}"',
        ])
    ]

    proc = subprocess.Popen(cmd)

    def handle_sigint(sig, frame):
        print("\nInterrupted — ending broadcast...")
        proc.terminate()
        end_broadcast(broadcast_id)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    ret = proc.wait()
    print(f"\nStream finished (exit code {ret}).")
    print("Ending YouTube broadcast...")
    end_broadcast(broadcast_id)

    # Clean up temp files — no reason to keep them
    print("\nCleaning up temp files...")
    import shutil
    shutil.rmtree(args.out, ignore_errors=True)
    print(f"  ✓ Deleted local: {args.out}")
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER,
                    f"rm -rf {SERVER_CLIP_DIR} {SERVER_PLAYLIST}"], check=False)
    print(f"  ✓ Deleted server: {SERVER_CLIP_DIR}")

    print(f"\nDone. Replay available at:\n  {watch_url}")


if __name__ == "__main__":
    main()
