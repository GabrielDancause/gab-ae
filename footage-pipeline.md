# Footage Processing Pipeline

Auto-processes DJI Action 6 footage from Google Drive — strips audio, detects Ali, sorts clips to the right channel.

---

## Goal

Plug SD card → upload to Drive → everything else is automated on a VPS. No manual editing, no laptop required.

---

## Architecture

```
DJI Action 6 SD card
        ↓
  Google Drive  inbox/raw/
        ↓
  VPS watches Drive for new files
        ↓
  FFmpeg extracts 1 frame every 5s
        ↓
  Gemini Flash vision (OpenRouter free)
  "Is Ali Imperiale visible in this frame?"
        ↓
  FFmpeg strips original audio
  + overlays background music
        ↓
  Sorted output back to Google Drive:
    olives-travel/     ← Ali visible
    gabs-adventures/   ← Gab only
```

---

## Stack

| Component | Tool | Notes |
|-----------|------|-------|
| Storage | Google Drive | `inbox/raw/` → `inbox/processed/` |
| Video processing | FFmpeg | Pre-installed on Ubuntu, handles 4K |
| AI detection | `google/gemini-2.0-flash-exp:free` via OpenRouter | Vision model, free tier |
| Server | Hetzner CX22 | €4/month, Ubuntu 24.04, 2 vCPU / 4GB RAM |
| Language | Python | Google Drive SDK + OpenRouter API |
| Background music | TBD | Drop an mp3 on the VPS, FFmpeg loops it |

---

## Processing Logic

### Ali detection
- Extract 1 frame every 5 seconds from clip
- Send each frame to Gemini Flash with a reference photo of Ali
- If **any frame** returns Ali visible → `olives-travel/`
- If **no frames** contain Ali → `gabs-adventures/`
- Use a reference photo of Ali in the prompt for accuracy (10,000+ available)

### Audio
- Strip original audio entirely (conversations may contain private info)
- Replace with looping background music via FFmpeg
- No trimming needed — replace everything, every time

### Clip size / disk management
- Process **one clip at a time**: download → process → upload → delete
- At any moment: max 2 clips on disk (input + output)
- DJI Action 6 4K clips are typically 4-8GB each — well within VPS disk limits

---

## Folder Structure (Google Drive)

```
footage/
  inbox/
    raw/          ← dump SD card here, pipeline picks up automatically
    processed/    ← moved here after processing (original, audio stripped)
  olives-travel/  ← Ali visible, ready to review/publish
  gabs-adventures/ ← Gab only, ready to review/publish
```

---

## VPS Setup (Hetzner CX22)

Steps when ready to execute:
1. Create Hetzner account → spin up CX22, Ubuntu 24.04
2. Add SSH key
3. Run setup script:
   - Install FFmpeg, Python 3, pip packages
   - Install Google Drive SDK (`google-api-python-client`)
   - Set up OpenRouter API key env var
   - Set up Google Drive service account credentials
4. Drop background music mp3 on VPS
5. Deploy pipeline script as a systemd service (runs continuously, watches Drive)
6. Test with one short clip

Estimated cost: **€4/month** (same VPS will also host the gab.ae shorts pipeline)

---

## TODOs

- [ ] Create Hetzner account and spin up CX22
- [ ] Create Google Drive service account + share `footage/` folder with it
- [ ] Get OpenRouter API key
- [ ] Write pipeline script (`footage_pipeline.py`)
- [ ] Write FFmpeg audio replacement + frame extraction commands
- [ ] Choose / source background music track
- [ ] Pick reference photo of Ali for vision prompt
- [ ] Test end-to-end with one DJI clip
- [ ] Set up systemd service for continuous watching
- [ ] (Later) Auto-assemble daily montage from sorted clips

---

## Notes

- Paris footage (3 days, 4K) is likely 50GB+ — process clip by clip, never load all at once
- Some clips will have both Gab and Ali — default to `olives-travel/` (bigger audience, urgent to build)
- Vlogs already uploaded directly to YouTube are excluded — only process raw unedited footage
- This same VPS will run the gab.ae shorts pipeline (see `shorts/PHASE2-PUBLISHING.md`)
