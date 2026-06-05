# GAB.AE Pipeline — Current State (2026-05-10, updated ~17:30 UTC)

## What We Built This Session

### 1. New Backup Architecture (Drive → IA → D1)

**Phase 1 — `footage/backup_to_ia.py`** (runs locally or on VPS)
- Streams directly from `gab-drive:_Todo/` → Internet Archive via rclone remote-to-remote
- Zero VPS disk usage — no download needed
- Creates D1 entry with `status='backed_up'` for each media file
- Drive state machine: `_Todo` → `_Doing` → `_Done`
- On startup: recovers stuck `_Doing` folders back to `_Todo`

**Phase 2 — `footage/process_from_ia.py`** (runs on VPS)
- Queries D1 for `status='backed_up'` entries (or `--reprocess` for vault entries with no thumb)
- Fetches IA-generated thumbnail JPEGs (no full video download)
- LLM tags via OpenRouter (nvidia/nemotron-nano-12b-v2-vl:free)
- Updates D1 to `status='vault'` with title, tags, thumb_b64
- HEICs skipped (IA doesn't generate thumbs for them)

**`footage/reseed_d1.py`** (updated)
- Now handles QuickTime, HEIF, and MPEG4 formats
- Updated to support `media_type: video/photo` in tags
- Added `2026-05-10-phone-paris-france` to SESSIONS list

### 2. YouTube Pipeline (one-button schedule)

**`footage/yt_processor.py`** (runs on VPS, cron every 5 min)
- Polls D1 `yt_jobs` WHERE `status='queued'`
- Downloads clip from IA
- ffmpeg: 2x slow-mo + cinematic color grade + Gymnopedie No. 1 (no original audio)
  - `setpts=2.0*PTS` + curves color grade + `eq=contrast=1.05:saturation=1.1`
  - Music: `/opt/gab/gab-adventures/footage/music/gymnopedie_no1.mp3`
  - Fade in 1.5s, fade out 2.5s
- Uploads to YouTube as scheduled Short (private → scheduled publish)
- Updates D1 `yt_jobs` with `status='scheduled'`, `yt_video_id`, `yt_url`, `yt_scheduled_at`

**Vault Review Page** (`/vault/review/<series>`)
- "Schedule on YouTube" button now active
- Shows job status on button (Queued / Processing / Scheduled / Error) when clip already has a job
- Refreshes status on page load

**`/vault/status`** — YouTube Queue section at bottom, auto-refreshes every 10s

**D1 `yt_jobs` table** (new):
```sql
id, video_slug, series, ia_url, effects, status, progress, yt_video_id, yt_url, yt_scheduled_at, error, created_at, updated_at
```

### 3. Previously Built (sessions)

| Session | IA Item | D1 | Notes |
|---|---|---|---|
| 2026-04-28 - Seine | gab-raw-seine-2026-04-28 | ✓ | 4 clips |
| 2026-05-03 - Action cam Paris | gab-raw-action-cam-paris-may3 | ✓ | 3 clips |
| 2026-04-30 - Square action cam 6 | gab-raw-action-cam-apr30 | ✓ | 8 clips |
| 2026-05-01 - Square action cam 6 | gab-raw-action-cam-may1-sq | ✓ | 37/79 clips seeded (token expired mid-run) |
| 2026-05-09 Action cam, Paris | gab-raw-action-cam-paris-may9 | ✓ | 10 portrait clips |
| 2026-05-10 - Phone, Paris | gab-raw-2026-05-10-phone-paris-france | ✓ | 11 videos + 4 HEICs, videos tagged |

**D1 videos table: ~108 rows total** (as of this session)

---

## VPS State

- **SSH:** `ssh root@178.105.50.213`
- **Scripts:** `/opt/gab/gab-adventures/footage/`
- **Cron jobs:**
  - `*/5 * * * *` — `yt_processor.py` (YouTube upload queue)
  - `*/45 * * * *` — CF token refresh (local Mac → VPS `/tmp/cf_token.txt`)
- **No batch currently running** — VPS is idle
- **Disk:** ~95 GB free

---

## Cloudflare

- Account ID: `f8a9c8de1fcedb10d25b24325a6f8727`
- D1 DB ID: `4e23e386-b430-4ffc-bf84-246a4e7bcdd1` (gab-ae-prod)
- Worker deployed — all routes live on gab.ae
- YouTube token on VPS: `/opt/gab/gab-adventures/footage/token_yt_gab.json`

---

## Pending / Next Steps

1. **Reseed action-cam-may1-sq clips 38–79** — token expired mid-run last time. Run:
   ```
   npx wrangler d1 list --remote   # force token refresh
   python3 footage/reseed_d1.py --sessions action-cam-may1-sq
   ```

2. **Queue up more folders to backup** — put into `gab-drive:_Todo/`, run `backup_to_ia.py` locally or on VPS. Candidates in Drive root:
   - `2026-05-10 - Action cam, Paris, France`
   - `2026-05-10 - Action cam, Old Wall, Paris, France`
   - `2026-04-27 - DJI Gab` (140 GB — needs `backup_to_ia.py`, too big for old pipeline)
   - `2026-05-01 - Action cam not squared` (115 GB — same)

3. **Process backed_up videos** — after backup, run on VPS:
   ```
   python3 /opt/gab/gab-adventures/footage/process_from_ia.py
   ```

4. **HEIC thumbnails** — currently skipped (IA doesn't auto-generate). Would need download + ffmpeg/sips convert. Low priority.

5. **gab-phone-mar2** — 0 files on IA (IA upload failed during old batch). Folder is in `gab-drive:_Done/`. Move back to `_Todo/` and run `backup_to_ia.py` to properly back it up.

---

## Key Files (local: /Users/gab/Desktop/gab-ae)

| File | Purpose |
|---|---|
| `footage/backup_to_ia.py` | Phase 1: Drive→IA stream, seed D1 as `backed_up` |
| `footage/process_from_ia.py` | Phase 2: IA thumbnails → LLM tag → D1 `vault` |
| `footage/yt_processor.py` | YouTube: download IA → ffmpeg slow-mo+Satie → upload |
| `footage/reseed_d1.py` | Re-seed D1 for sessions that failed (updated: handles QuickTime/HEIF) |
| `footage/batch_process.py` | Old combined pipeline (Drive→VPS→IA→D1), still works for small sessions |
| `footage/process_session.py` | Single session processor (called by batch_process.py) |
| `footage/refresh_vps_token.sh` | Push fresh CF OAuth token to VPS |
| `src/worker.js` | CF Worker: vault, review, status, YouTube queue API |
| `schema.sql` | D1 schema (includes `yt_jobs` table) |
