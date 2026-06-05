# GAB.AE Pipeline — Current State (2026-06-05)

---

## 🔴 LIVE NOW — Musique et scènes mondaines (24/7 YouTube Live)

**Stream:** https://www.youtube.com/watch?v=u4y1ZSt3V5Q  
**Server:** Hetzner dedicated — `root@138.201.21.95` (password: `EqsSQX%_2TQ65q`)  
**Service:** `systemctl status musique` — runs forever, auto-restarts on crash/reboot

### Architecture

```
Mac (hardware encode)          Hetzner server (broadcast only)
─────────────────────          ────────────────────────────────
footage/batch_encode.py        /opt/musique_streamer.py
  VideoToolbox H.264             - loops /opt/broadcast/*.mp4
  1920x1080 @ 60fps @ 8Mbps      - ambient music from /opt/music/
  crop square/portrait → 16:9    - libx264 ultrafast re-stamp (setpts)
  rsync → /opt/broadcast/        - RTMP → YouTube Live
                                 - inotifywait: picks up new clips live
```

### Server paths
| Path | Content |
|------|---------|
| `/opt/broadcast/` | Live clip library (~147 clips, ~4.4 GB) |
| `/opt/music/` | Ambient MP3 tracks |
| `/opt/rtmp_url.txt` | Current YouTube RTMP URL (write here to change stream) |
| `/opt/musique_streamer.py` | Streamer script (auto-deployed via git) |
| `/opt/musique_streamer.log` | Live logs: `tail -f /opt/musique_streamer.log` |
| `/etc/systemd/system/musique.service` | systemd unit |

### Key ffmpeg flags learned the hard way
- **`-re`** — CRITICAL. Read input at realtime. Without it ffmpeg sends at ~10x speed and YouTube drops after ~35s.
- **`setpts=PTS-STARTPTS`** — Normalize timestamps. Without it, concat loop causes timestamp burst at boundary → "faster than realtime" error.
- **`libx264 ultrafast`** on server (not copy) — needed to regenerate clean timestamps.
- **`-g 120`** at 60fps — keyframe every 2s (YouTube requirement).
- **Normal latency** (not low latency) — required for full quality selector.

### Clip pickup (seamless)
The server watches `/opt/broadcast/` with `inotifywait`. When new clips arrive via rsync, ffmpeg is gracefully killed, the playlist rebuilds, and streaming resumes within ~3s. YouTube's buffer absorbs the gap.

---

## Broadcast scripts (local: footage/)

| Script | Purpose |
|--------|---------|
| `batch_encode.py` | Encode clips from any footage folder, rsync to server |
| `musique_streamer.py` | 24/7 streamer (deployed to `/opt/`) |
| `create_broadcast.py` | Create YouTube Live broadcast, write RTMP URL to server |

### batch_encode.py — usage

```bash
# Encode all clips from default folder, push to server
python3 footage/batch_encode.py

# Encode with prefix (prevents filename collisions when mixing batches)
python3 footage/batch_encode.py --prefix nh --base "/Volumes/obiwan/North Hatley"

# Encode locally only — stage before a special broadcast
python3 footage/batch_encode.py --prefix nh --no-push --out /tmp/nh_clips

# All options
python3 footage/batch_encode.py \
  --prefix SLUG       # output: {prefix}_{idx:04d}_{n}.mp4
  --base   DIR        # source footage folder
  --out    DIR        # local output folder (default: /tmp/broadcast_batch)
  --clips  N          # clips per source file (default: 2)
  --min    N          # min clip duration secs (default: 8)
  --max    N          # max clip duration secs (default: 25)
  --parallel N        # parallel encode workers (default: 6)
  --no-push           # skip rsync + service restart
```

### Special broadcast pattern (e.g. themed 15-min segment)
```bash
# 1. Encode themed clips locally
python3 footage/batch_encode.py --prefix nh --base "/path/to/footage" --no-push --out /tmp/nh_clips

# 2. Stash full library, swap in themed clips
ssh root@138.201.21.95 "mv /opt/broadcast /opt/broadcast_full && mkdir /opt/broadcast"
rsync -av /tmp/nh_clips/ root@138.201.21.95:/opt/broadcast/
ssh root@138.201.21.95 "systemctl restart musique"

# 3. After the segment, restore
ssh root@138.201.21.95 "rm -rf /opt/broadcast && mv /opt/broadcast_full /opt/broadcast"
ssh root@138.201.21.95 "systemctl restart musique"
```

---

## Vault pipeline (Drive → IA → D1 → gab.ae/vault)

### Phase 1 — `footage/backup_to_ia.py`
- Streams from `gab-drive:_Todo/` → Internet Archive (rclone remote-to-remote)
- Zero VPS disk usage. Creates D1 entry `status='backed_up'`.
- Drive state machine: `_Todo` → `_Doing` → `_Done`

### Phase 2 — `footage/process_from_ia.py`
- Queries D1 for `status='backed_up'`
- Fetches IA-generated thumbnail JPEGs (no full video download)
- LLM tags via OpenRouter (nvidia/nemotron-nano-12b-v2-vl:free)
- Updates D1 to `status='vault'` with title, tags, thumb_b64

### Vault sessions
| Session | IA Item | D1 |
|---------|---------|-----|
| 2026-04-28 - Seine | gab-raw-seine-2026-04-28 | ✓ |
| 2026-05-03 - Action cam Paris | gab-raw-action-cam-paris-may3 | ✓ |
| 2026-04-30 - Square action cam 6 | gab-raw-action-cam-apr30 | ✓ |
| 2026-05-01 - Square action cam 6 | gab-raw-action-cam-may1-sq | ✓ partial |
| 2026-05-09 Action cam, Paris | gab-raw-action-cam-paris-may9 | ✓ |
| 2026-05-10 - Phone, Paris | gab-raw-2026-05-10-phone-paris-france | ✓ |

**D1 videos table: ~108 rows total**

---

## Servers

| Server | IP | Role |
|--------|----|------|
| Hetzner dedicated | `138.201.21.95` | 24/7 broadcast, yt_processor |
| ~~Old VPS~~ | ~~178.105.50.213~~ | DEAD |

**SSH:** `ssh root@138.201.21.95`  
**Password:** `EqsSQX%_2TQ65q`  
**Permanent CF token:** `/opt/gab/cf_api_token.txt`  
**YouTube token:** `/opt/gab/gab-adventures/footage/token_yt_gab.json`

---

## Cloudflare

- Account ID: `f8a9c8de1fcedb10d25b24325a6f8727`
- D1 DB ID: `4e23e386-b430-4ffc-bf84-246a4e7bcdd1` (gab-ae-prod)
- Worker deployed — all routes live on gab.ae

---

## YouTube Pipeline (Shorts)

**`footage/yt_processor.py`** — cron every 5 min on server  
- Polls D1 `yt_jobs` WHERE `status='queued'`
- Downloads clip from IA, applies 2x slow-mo + cinematic color grade + Gymnopedie No. 1
- Uploads as scheduled Short
- Token needs full `youtube` scope to edit titles post-upload (TODO)

**Vault Review Page** (`/vault/review/<series>`) — "Schedule on YouTube" button active

---

## Key Files (local: /Users/gab/Desktop/gab-ae)

| File | Purpose |
|------|---------|
| `footage/batch_encode.py` | Mac → encode clips → rsync to server |
| `footage/musique_streamer.py` | 24/7 server broadcast script |
| `footage/create_broadcast.py` | Create YouTube Live + write RTMP URL |
| `footage/backup_to_ia.py` | Phase 1: Drive→IA stream, seed D1 |
| `footage/process_from_ia.py` | Phase 2: IA thumbnails → LLM tag → D1 vault |
| `footage/yt_processor.py` | YouTube: download IA → ffmpeg → upload Shorts |
| `footage/reseed_d1.py` | Re-seed D1 for sessions that failed |
| `src/worker.js` | CF Worker: vault, review, status, YouTube queue API |
| `schema.sql` | D1 schema |

---

## Pending / Next Steps

1. **Encode 2026-06-03 folders 1-7** — encode all footage and push to server
2. **--prefix convention** — use descriptive prefixes when mixing sources (e.g. `nh` for North Hatley, `sq` for square action cam, `ph` for phone)
3. **YouTube token full scope** — re-auth with `youtube` scope to enable title editing post-upload
4. **HEIC thumbnails** — currently skipped. Would need download + sips convert.
5. **Reseed action-cam-may1-sq clips 38–79** — token expired mid-run
