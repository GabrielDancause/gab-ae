# GAB.AE Pipeline — Current State (2026-06-07)

---

## 🔴 LIVE NOW — Musique et scènes mondaines (24/7 YouTube Live)

### Landscape loop (horizontal)
**Stream:** https://www.youtube.com/watch?v=u4y1ZSt3V5Q
**Clips on server:** 511 MP4s in `/opt/broadcast/`
**Service:** `systemctl status musique`

### Vertical loop (9:16)
**Clips on server:** 195 MP4s in `/opt/broadcast_vertical/`
**Service:** `systemctl status musique_vertical`

### Watchdog
**Service:** `systemctl status stream_watchdog`
Checks YouTube API every 2 min, restarts service if stream goes inactive, recreates broadcast if ended.

### Server
**Hetzner dedicated:** `root@138.201.21.95`
**Password:** `EqsSQX%_2TQ65q`

---

## Architecture

```
Mac (hardware encode)               Hetzner server (broadcast)
─────────────────────               ──────────────────────────
footage/batch_encode.py             /opt/musique_streamer.py
  VideoToolbox H.264                  - loops /opt/broadcast/*.mp4
  1920x1080 @ 60fps @ 8Mbps           - weighted playlist (new clips play more)
  crop/scale per orientation          - ambient music from /opt/music/
  rsync → /opt/broadcast/             - libx264 ultrafast + setpts
                                      - RTMP → YouTube Live
footage/encode_and_push.sh            - inotifywait: picks up new clips live
  continuous small-batch encode
  15s clips → push → restart        /opt/musique_streamer_vertical.py
  repeat forever                      - same but scale=1080:1920
```

### Playlist weighting (new clips play more often)
| Age | Times in playlist |
|-----|-------------------|
| < 1 hour | 8× |
| < 6 hours | 5× |
| < 24 hours | 3× |
| < 3 days | 2× |
| Older | 1× |

---

## Server paths
| Path | Content |
|------|---------|
| `/opt/broadcast/` | Landscape clip library (511 clips) |
| `/opt/broadcast_vertical/` | Vertical clip library (195 clips) |
| `/opt/music/` | Ambient MP3 tracks |
| `/opt/rtmp_url.txt` | Landscape YouTube RTMP URL |
| `/opt/rtmp_url_vertical.txt` | Vertical YouTube RTMP URL |
| `/opt/musique_streamer.py` | Landscape streamer |
| `/opt/musique_streamer_vertical.py` | Vertical streamer |
| `/opt/stream_watchdog.py` | Health checker + auto-restart |
| `/opt/live_token.json` | YouTube OAuth token |

---

## Key ffmpeg lessons (learned the hard way)
- **`-re`** — CRITICAL. Read input at realtime. Without it ffmpeg sends at ~10x speed → YouTube drops after ~35s.
- **`setpts=PTS-STARTPTS`** — Normalize timestamps on concat. Without it: timestamp burst → "faster than realtime".
- **`libx264 ultrafast`** on server (not copy) — regenerates clean timestamps.
- **`-g 120`** at 60fps — keyframe every 2s (YouTube requirement).
- **`-maxrate 6800k -bufsize 13600k`** — keep bitrate in check (YouTube recommends ≤6800k).
- **`-stream_loop -1`** goes BEFORE `-i` (input option, not output).
- **Normal latency** (not low latency) — required for full quality selector.

---

## Encoding — local Mac scripts

### batch_encode.py
```bash
# Encode clips from a drive, push to server
python3 footage/batch_encode.py --base /Volumes/luke --prefix luke --clips 3 --min 12 --max 15

# Vertical
python3 footage/batch_encode.py --base /Volumes/yoda --prefix yoda-v --clips 3 --min 12 --max 15 --vertical

# Local only (no push)
python3 footage/batch_encode.py --base /Volumes/padme --prefix padme --no-push --out /tmp/clips
```

### encode_and_push.sh
Continuous loop: encode small batches (15s clips) from all mounted drives → push → restart → repeat.
```bash
caffeinate -i bash footage/encode_and_push.sh
```
Sources: `/Volumes/luke`, `/Volumes/padme`, `/Volumes/yoda`

---

## Session stream (one-shot ordered broadcast)

Successfully streamed the North Hatley bike ride DJI session end-to-end:
- **66 clips** encoded and rsynced to server
- YouTube broadcast created with `enableAutoStop: true`
- Streamed in chronological order, recorded to YouTube
- URL: https://www.youtube.com/watch?v=7NIQOITbMlU (unlisted)

Script: `footage/session_stream.py`

---

## Footage backup system

### backup_manager.py
Tracks source folders → Internet Archive. One IA item per folder. Crash-safe (saves after every file).
```bash
python3 footage/backup_manager.py --status               # full matrix
python3 footage/backup_manager.py --backup all           # upload everything pending
python3 footage/backup_manager.py --backup "folder name" # one folder
python3 footage/backup_manager.py --verify               # re-check MD5 checksums
python3 footage/backup_manager.py --scan-sidecars /Volumes/drive  # recover from .backup files
```

### .backup sidecar file
Written to every backed-up folder. Survives drive moves, machine changes, manifest loss.
```
source          /Volumes/obiwan/2026-06-03 - Multiple exports
drive           obiwan

[ia]
item            gab-raw-obiwan-2026-06-03-multiple-exports
url             https://archive.org/details/...
files           621 / 621
status          complete
date            2026-06-07T...

[checksums]
1/DCIM/DJI_001/DJI_20260530142155_0001_D.MP4   md5:a3f8c2d1...
```

### Backup status
| Folder | IA | Notes |
|--------|-----|-------|
| obiwan/2026-06-03 - Multiple exports | ✓ complete | DJI + iPhone |
| obiwan/2026-06-04 - North Hatley en bike | ⚠ partial | DJI, in progress |
| obiwan/2026-06-05 - export from iPhone | ⚠ 18/956 | meta-glasses done |
| obiwan/2026-06-06 - Ali new video | ✓ complete | Sony card |

### IA organization
- One item per source folder
- `noindex:true` + `access-control:private` — hidden from IA search
- Item naming: `gab-raw-{label}-{folder-slug}`
- Ali's folders: label `ali-imperiale` auto-applied
- LRF proxy files: skipped (IA rejects them)
- Everything else backed up (no content filtering)

### Session management page
**Meta glasses session:** https://gab.ae/footage/session/meta-glasses-2026-05-29
Unlisted, `X-Robots-Tag: noindex`, shows all 18 files with IA download links.

---

## Public footage pages

**Published clip:** https://gab.ae/footage/iphone-vertical-2026-05-29
- YouTube embed + IA download button
- Audio stripped (muted upload)
- Route: `/footage/[slug]` in worker.js

---

## Cloudflare

- Account ID: `f8a9c8de1fcedb10d25b24325a6f8727`
- D1 DB ID: `4e23e386-b430-4ffc-bf84-246a4e7bcdd1` (gab-ae-prod)
- Worker deployed — all routes live on gab.ae

---

## Key local files

| File | Purpose |
|------|---------|
| `footage/batch_encode.py` | Encode clips from footage drives → server |
| `footage/encode_and_push.sh` | Continuous small-batch encode + push loop |
| `footage/musique_streamer.py` | Landscape 24/7 streamer (deployed to server) |
| `footage/musique_streamer_vertical.py` | Vertical 24/7 streamer (deployed to server) |
| `footage/stream_watchdog.py` | YouTube health checker (deployed to server) |
| `footage/session_stream.py` | One-shot ordered session broadcast |
| `footage/publish_clip.py` | Upload one clip to YouTube + IA + seed D1 |
| `footage/backup_manager.py` | IA backup tracker with checksums + sidecars |
| `footage/backup_manifest.json` | Local backup manifest (layer 2 of 3) |
| `footage/seed_session_d1.py` | Seed D1 for a backed-up session |
| `src/worker.js` | CF Worker: all gab.ae routes |
| `PIPELINE_STATE.md` | This file |

---

## Pending / Next Steps

1. **Resume IA backup** — `python3 footage/backup_manager.py --backup all` (obiwan must be mounted)
2. **Verify backed-up folders** — `--verify` once obiwan is mounted
3. **Add more drives to SOURCES** in backup_manager.py (luke, padme, yoda, + 17 others)
4. **encode_and_push.sh** — keep running to grow the loop library
5. **YouTube token full scope** — re-auth to enable title editing post-upload
