# Mission: Z: Drive Footage -> Views, Engagement & Money

Started: 2026-05-23
Owner: Gab
Status: **LIVE** (stream running, uploads working)

---

## Goal

Maximize revenue, views, and engagement from the footage archive on the Z: drive (32 TB used, 9.5 TB free).

---

## What We Built (2026-05-23 / 24)

### 1. 24/7 Live Stream -- "Toujours en Route"
- **Channel:** Gab's Adventures (UCFUjYzVjRjweKhfs480xR4w)
- **Stream key:** `qmp5-ue0m-38gp-cc2y-7kjs`
- **Script:** `stream_to_youtube.ps1`
- Scans all 6,619 MP4 clips from `Z:\01- Media files` recursively
- Shuffles on every launch and every playlist completion
- MP4-only filter (avoids AVI/MOV codec mismatches in concat demuxer)
- Original audio stripped, background music looped on top
- Auto-reconnects on drop (10s delay), reshuffles on playlist end
- **Auto-starts on Windows login** via Registry:
  `HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run` -> `ToujoursEnRoute`
- Logs everything to `C:\gab-ae\stream.log`

### 2. Background Music Library
- **File:** `C:\gab-ae\music\background.mp3`
- 122 royalty-free tracks from YouTube Audio Library
- 3h47min, 312 MB, built with `build_music.ps1`
- Combined into one looping track with `ffmpeg concat`

### 3. YouTube Upload Pipeline
- **Script:** `upload_video.py`
- Python 3.12 installed, google-api-python-client set up
- OAuth token saved to `token_youtube.json` (one-time browser auth done)
- Auto-generates titles from filenames: `2024-03-22_A-Day-in-Bangkok.mp4` -> `A Day in Bangkok | Mar 2024`
- **Videos uploaded:**
  - https://www.youtube.com/watch?v=qVgBp2FHt98 -- Boracay, Philippines | Ambient (3:35)
  - https://www.youtube.com/watch?v=tJHLiEoMCIA -- Charlevoix, Quebec | Ambient (5:05, 4K)

### 4. Clip Encoder
- **Script:** `encode_clips.ps1`
- GPU-accelerated (h264_nvenc), strips audio, adds music, scales to 1080p
- Skips already-encoded files (safe to re-run)
- Three Bangkok/Thailand clips encoded to `C:\gab-ae\output\`

---

## Lessons Learned

### Audio
- **ALL published content:** original audio stripped, music replaced
- Rule: `-map "0:v:0" -map "1:a:0"` -- video from source, audio from music only
- No exceptions (privacy: no voices, no passwords, no background conversation)

### Quality: Upload vs Stream
Two very different targets:

| | Upload | Stream |
|---|---|---|
| Command | `-c:v copy` (zero re-encoding) | `-c:v h264_nvenc -rc cbr -b:v 15000k` |
| Resolution | Native (4K if source is 4K) | Native (4K if channel supports it) |
| Bitrate | Source bitrate (94 Mbps for 4K DJI) | 15 Mbps CBR (YouTube Live max for 4K/30) |
| File size | 3+ GB for 5 min | ~550 MB for 5 min |

- **Never downscale for uploads** -- YouTube processes and serves all resolutions
- **Raw 94 Mbps won't stream** -- upload connection can't sustain real-time, YouTube drops it
- **15 Mbps CBR at 4K = excellent stream health** -- confirmed working

### Stream Stability
- Problem: raw Z: drive has mixed codecs (AVI, MOV, MJPEG alongside H.264)
- Fix: MP4-only filter + `-err_detect ignore_err` + `-fflags +genpts+discardcorrupt`
- Real fix: pre-encode library to normalized files (next step)
- Software decode on input (no `-hwaccel cuda` on the concat input) -- avoids codec mismatch failures

### Titles
- Format: `Location | Music vibe` -- nothing else
- No assumptions about shot type (don't say "drone", "walking", etc.)
- Series concept: **Musique et Scenes Mondaines** -- ambient music over random archival footage

### Script Encoding
- Em dashes (`--`) in PowerShell strings cause corruption on Windows -- use `--` always

---

## File Map

```
C:\gab-ae\
  stream_to_youtube.ps1     -- 24/7 live stream (THE main script)
  upload_video.py           -- YouTube upload via Data API v3
  encode_clips.ps1          -- encode specific clips for upload
  build_music.ps1           -- build background.mp3 from Downloads/*.mp3
  music\
    background.mp3          -- 3h47min ambient music loop (gitignored)
  output\                   -- encoded clips ready for upload (gitignored)
  client_secrets.json       -- OAuth credentials (gitignored, never commit)
  token_youtube.json        -- OAuth token (gitignored, never commit)
  stream.log                -- live stream log (gitignored)
  stream_list.txt           -- concat playlist (gitignored)
```

---

## What's Next

### Immediate
- [ ] Build `normalize_library.ps1` -- pre-encode all 6,619 clips to `C:\gab-ae\normalized\`
  - Each clip: 4K where source is 4K, 1080p otherwise, 15 Mbps CBR H.264, no audio
  - Stream reads from `normalized\` -- pure passthrough, zero GPU at stream time, never drops
- [ ] Switch stream to pull from `normalized\` instead of raw Z: drive

### Daily Upload Pipeline
- [ ] Script to pick 3 clips per day, encode at full quality, upload automatically
- [ ] Playlist/series on YouTube: "Musique et Scenes Mondaines"

### Longer Term
- [ ] Google Drive sync -- pull gabrieldancause@gmail.com and gab@gab.ae footage to Z:
- [ ] Dedup strategy across Z: + Drive + Photos Takeout
- [ ] Internet Archive upload pipeline (already started -- continue)
- [ ] Shorts cutting pipeline -- vertical clips for TikTok/Reels/YouTube Shorts

---

## Key Assets

- **Gab's Adventures** -- 1,100 YouTube subs, adventure/travel, this is our main channel
- **Ali Imperiale** -- 127K YouTube, ~$15K/month (separate, don't break it)
- **Z: drive** -- 32 TB, 6,619 MP4 clips indexed, 2022-2025
- **Stream key** -- `qmp5-ue0m-38gp-cc2y-7kjs` (in scripts, not secret)
- **OAuth credentials** -- in `client_secrets.json` (gitignored)

---

## Context Docs

- `MEDIA_ARCHIVE_PLAN.md` -- full archiving and publishing plan
- `socials.md` -- all channels, brands, and social strategy
- `footage-pipeline.md` -- automated footage processor (VPS-based, not yet built)
