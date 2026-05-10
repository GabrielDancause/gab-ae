# GAB.AE Pipeline — Current State (2026-05-10, updated ~13:00 UTC)

## What We Built

### 1. Footage Pipeline (VPS → Internet Archive → gab.ae/vault)
- `footage/process_session.py` — core pipeline: ffmpeg grade → IA upload → D1 seed
- `footage/batch_process.py` — batch runner: loops sessions, downloads from Drive, processes, moves to `_Done/` in Drive, deletes local
- `footage/find_best_clips.py` — scores clips by sharpness (Laplacian variance), extracts best 5s clips
- `footage/reseed_d1.py` — LOCAL re-seeder: uses IA thumbnails + LLM to seed D1 for sessions that failed D1 during batch
- Pipeline writes state to `/tmp/pipeline_state.json` AND to D1 `pipeline_state` table (key='current') via CF REST API

### 2. Vault (`/vault`)
- Password-protected (cookie `vk=<VAULT_KEY>`, env var `VAULT_KEY` in worker, default `gabvault2026`)
- Shows all videos from D1 `videos` table with series filter pills (client-side JS)
- `/vault/status` — dashboard reading from D1 `pipeline_state` table, auto-refreshes every 10s
- Noindex meta on both vault pages, robots.txt `Disallow: /vault`

### 3. gab.ae Worker
- Cron: Nookie Nook article gen re-enabled, gab.ae news gen disabled (pivoted to footage)
- Shorts homepage at `/` (grid of shorts)
- Videos page at `/videos`
- Approve-video API at `/api/approve-video` (POST with `{slug}`)
- Thumbnails served at `/vthumb/:slug`

---

## VPS

- **SSH:** `ssh root@178.105.50.213`

### Currently Running (as of 2026-05-10 ~13:00 UTC)
- `batch_process.py` running in background (`/tmp/batch_process.log`)
- Session 6 of 9: `2026-05-01 - Square action cam 6 footage` (36 GB, 79 clips) — IA upload ~75% done, then ~2h LLM tagging phase
- Session 7 (`2026-03-02 - Gab phone`, 10 GB) — queued, will start after session 6

### Batch Session Status
| Session | Size | Status | D1 |
|---|---|---|---|
| 2026-04-28 - Seine | 18 GB | done | ✓ seeded (4 clips) |
| 2026-05-09 - Phone, Paris | 1.4 GB | done (no video clips) | n/a |
| 2026-05-09 Action cam, Paris | 20 GB | done (10 clips, all portrait) | ✓ seeded (from prev run) |
| 2026-05-03 - Action cam Paris | 22 GB | done (3 clips) | ✓ reseeded locally |
| 2026-04-30 - Square action cam 6 | 29 GB | done (21 clips; only 8 uploaded to IA due to connection error) | ✓ reseeded locally (8 clips) |
| 2026-05-01 - Square action cam 6 | 36 GB | **processing** (IA upload in progress) | pending reseed |
| 2026-03-02 - Gab phone | 10 GB | queued | pending reseed |
| 2026-04-27 - DJI Gab | 140 GB | skipped (need 150 GB free) | — |
| 2026-05-01 - Action cam wide | 115 GB | skipped (need 125 GB free) | — |

### Key Paths on VPS
- Pipeline scripts: `/opt/gab/gab-adventures/footage/`
- Footage download dir: `/opt/gab/footage/`
- State file: `/tmp/pipeline_state.json`
- Logs: `/tmp/batch_process.log`, `/tmp/process_session_*.log`
- CF token file: `/tmp/cf_token.txt` (refreshed every 45 min by local Mac cron)

---

## Cloudflare

- Account ID: `f8a9c8de1fcedb10d25b24325a6f8727`
- D1 DB ID: `4e23e386-b430-4ffc-bf84-246a4e7bcdd1` (gab-ae-prod)
- Worker deployed, all routes live on gab.ae
- **D1 videos: 29 rows** (sessions 1-5 seeded; sessions 6-7 pending reseed after batch completes)

## Internet Archive

- IA S3 access: `xmKajI71PPwfRuAb` / secret: `PuQEQQLZYb1k5e3J`
- Raw private backups: `gab-raw-*` items (access=private, noindex=true)
- Public long-form: `gab-*` items (status='processed' in D1, not yet 'live')

---

## CF API Token Situation

- **wrangler OAuth token** — lives at `~/Library/Preferences/.wrangler/config/default.toml`, expires hourly
- **Auto-refresh cron** — runs every 45 min on local Mac: `/tmp/refresh_vps_token.sh`; pushes fresh token to VPS `/tmp/cf_token.txt`
- **batch_process.py patched** — now reads token from `/tmp/cf_token.txt` at each session start (not just at startup)
- **reseed_d1.py** — reads wrangler toml directly and auto-refreshes; use this after batch completes

---

## Pending Tasks

### After Batch Completes (sessions 6 + 7 done)
1. **Reseed D1 for sessions 6 and 7:**
   ```
   cd /Users/gab/Desktop/gab-ae
   python3 footage/reseed_d1.py --sessions action-cam-may1-sq gab-phone-mar2
   ```
2. **Update pipeline_state in D1** — run reseed_d1.py or push manually via:
   ```python
   # In Python, after reading /tmp/pipeline_state.json from VPS
   d1_query(f"INSERT OR REPLACE INTO pipeline_state ...", token)
   ```
3. **Re-upload apr30 missing 13 clips** — `gab-raw-action-cam-apr30` only has 8/21 clips due to connection error. Re-download from `gab-drive:_Done/2026-04-30 - Square action cam 6 footage` and re-run `ia upload`.

### Nice to Have
4. **Approve videos** — flip status from 'vault' → 'live' for best clips via `/api/approve-video`
5. **Large sessions** — DJI Apr27 (140 GB) + Action cam wide May1 (115 GB) need VPS disk expansion
6. **drive_to_ia.py** — direct Drive→IA streaming for 20TB archive (discussed, not built)

---

## Key Files (local: /Users/gab/Desktop/gab-ae)

- `src/worker.js` — main CF worker (vault, videos, cron, routing)
- `src/templates/site-layout.js` — layout shell (supports `extraHead` param)
- `footage/process_session.py` — single session pipeline
- `footage/batch_process.py` — batch runner (patched: reads CF token from /tmp/cf_token.txt per-session)
- `footage/find_best_clips.py` — clip scorer
- `footage/reseed_d1.py` — LOCAL D1 re-seeder (run after batch to fix failed D1 seeds)
- `schema.sql` — D1 schema (includes `pipeline_state` table)
- `wrangler.toml` — CF worker config
