# Social Media & Pipeline Master

---

## Quick Reference — All Links (as of 2026-04-28)

### Ali Imperiale
- YouTube (main): https://www.youtube.com/channel/aliimperiale
- YouTube Shorts: https://www.youtube.com/channel/UCvwhZDstIfchS8T-x7I0Jgw
- Facebook: https://www.facebook.com/people/Ali-Imperiale/61581368111171/
- Instagram: https://www.instagram.com/aliimperiale/
- TikTok: https://www.tiktok.com/@aliimperiale
- Patreon: https://www.patreon.com/cw/aliimperiale
- Website: https://aliimperiale.com/

### Travel with Ali Imperiale
- YouTube: https://www.youtube.com/channel/UCJp1lMTzYzd_UMtN6mTE0ZA

### The Nookie Nook
- Website: https://thenookienook.com
- YouTube: https://www.youtube.com/@TheNookieNook
- Instagram: https://www.instagram.com/thenookienook/

### La Casita Hedonista
- YouTube: https://www.youtube.com/@casitahedonista
- Facebook (old): https://www.facebook.com/mexicojunglecamping/?locale=fr_CA

### GAB News
- Website: https://gab.ae

### Gab's Adventures
- YouTube: https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w
- Instagram: https://www.instagram.com/gabrieldancause
- X / Twitter: https://x.com/Gabdancause
- TikTok: https://www.tiktok.com/@gabrieldancause

---

# VPS & AUTOMATION PIPELINE

*Everything that was running locally needs to move here. One Hetzner CX22 (€4/month) runs both pipelines.*

---

## VPS — Hetzner CX22

**Status: not yet created.**

| Spec | Value |
|------|-------|
| Provider | Hetzner |
| Plan | CX43 — €12.49/month |
| OS | Ubuntu 24.04 |
| RAM / vCPU | 16GB / 8 |
| Stack | Python 3, FFmpeg, Google Drive SDK, SQLite |

### Setup steps (when ready)
1. Create Hetzner account → spin up CX22, Ubuntu 24.04
2. Add SSH key
3. Install: FFmpeg, Python 3, pip packages, `google-api-python-client`
4. Set env vars: OpenRouter API key, Google Drive service account credentials, Pexels API key, Hootsuite API key
5. Deploy both pipeline scripts as systemd services
6. Test end-to-end with one clip / one article

---

## Pipeline 1 — Footage Processor ⚡ Priority — footage waiting to be processed

Auto-processes footage from Google Drive — strips audio, detects Ali, sorts clips, builds a searchable library database.

**⚠️ Paris footage (3 days, 4K, ~50GB+) is waiting.**

### Architecture

```
YOU: dump everything (DJI + Meta glasses + phone) into one folder
        ↓
  Google Drive  footage/inbox/raw/
        ↓
  VPS watcher detects new files
        ↓
  Detect device from filename pattern
  Group into sessions (clips within 2h = same session)
        ↓
  For each session:
    Download all clips in session
    FFmpeg stitch in order + strip audio
    Upload stitched output to Drive
    Move originals → footage/inbox/processed/
    Delete local files
        ↓
  Log everything to SQLite database (clips + sessions table)
```

### Session logic
- Clips within 2 hours of each other from the same device = one session
- Session named after start time (e.g. `2026-04-26_2009`)
- Crossing midnight is fine — 23:00–00:45 = one session, not two days
- Devices never mixed in same stitch: DJI stitched separately, Meta separately, phone separately

### Device detection (from filename)
- DJI Action: `dji_mimo_YYYYMMDD_HHMMSS_*`
- Meta glasses: TBD — filename pattern pending
- Phone: `IMG_*.MOV` / `VID_*.mp4`

### Google Drive folder structure

```
footage/
  inbox/
    raw/              ← dump everything here (all devices, mixed)
    processed/        ← originals moved here after processing
  sessions/
    dji/
      2026-04-26_2009/ ← stitched output per session
    meta/
      2026-04-26_2009/
    phone/
      2026-04-26_2009/
```

### SQLite database (footage library)
Lives on VPS, backed up to Drive daily. Every processed clip and session gets a row.

**clips table:** id, filename, device, recorded_at, session_id, duration, resolution, file_size, drive_raw_path, drive_processed_path, has_ali, location, processed_at

**sessions table:** id, device, started_at, ended_at, clip_count, drive_stitched_path, published_to (JSON), notes

Use cases: find all Paris clips with Ali, export unpublished clips for Patreon, build stock footage catalogue.

### Setup TODOs
- [ ] Create Hetzner account and spin up CX22
- [ ] Create Google Drive service account + share `footage/` folder with it
- [ ] Get OpenRouter API key
- [ ] Write `footage_pipeline.py`
- [ ] Choose background music track
- [ ] Pick reference photo of Ali for vision prompt
- [ ] Test end-to-end with one DJI clip
- [ ] Set up systemd service for continuous watching

---

## Pipeline 2 — GAB News Shorts

Generates 30-second 9:16 MP4s from gab.ae articles and publishes to all platforms daily.

### Phase 1 — Video generation (done, runs locally)

- `shorts/generate_shorts.py` — full pipeline:
  - Fetches articles from `https://gab.ae/api/shorts-feed` (tech + business, last 24h, D1 database)
  - B-roll: Pexels Video API (portrait, searched by tags + category)
  - Text overlays: Pillow (5 timed slides: headline → lede → key stat → takeaways → pull quote)
  - Audio: `shorts/music/background.mp3` (looped, 18% vol, fade in/out)
  - Assembly: FFmpeg
  - Output: `shorts/output/{slug}.mp4`
- Pexels API key: `kJHI1050W5rs7GVlAlIFrIVQvTCl6N1ikhtqMoyYLgh8VW0URGvbxCXL`
- Swap music anytime: `yt-dlp -x --audio-format mp3 -o "shorts/music/background.%(ext)s" "YOUTUBE_URL"`

```bash
python3 shorts/generate_shorts.py           # generate up to 15 videos
python3 shorts/generate_shorts.py --limit 3 # test with 3
python3 shorts/generate_shorts.py --dry-run # print articles, no video
python3 shorts/generate_shorts.py --no-music
```

**Pending:** `npx wrangler deploy` — was blocked by Cloudflare 10500 outage, needs retry.

### Phase 2 — Publishing (to build: `shorts/publish_shorts.py`)

**Technology:** Hootsuite API (user has key) — one API covers all platforms. Fallback: native APIs.

**Publishing schedule:**

| Platform | Posts/day | Times |
|----------|-----------|-------|
| Facebook | 15 | Every ~90 min from 7:00 |
| Twitter/X | 15 | Every ~90 min from 7:00 |
| TikTok | 6 | 7:00 10:00 13:00 16:00 19:00 22:00 |
| YouTube Shorts | 6 | 7:00 10:00 13:00 16:00 19:00 22:00 |
| Instagram | 1 | 12:00 |

**Hashtags:** `#Finance #Tech #News #SaaS #AINews #Investing #StockMarket #TechNews #StartupNews #gab` + article category tags

**What the script does:**
1. Load MP4s from `shorts/output/` (today's, by mtime)
2. Rank/select per platform based on schedule
3. Upload video + metadata (title, description, hashtags) via Hootsuite API
4. Space posts evenly across the day
5. Log to `shorts/publish_log.json`

**Daily cron on VPS:**
```bash
python3 shorts/generate_shorts.py && python3 shorts/publish_shorts.py
```

---

# HUMANS

*Personal brands — content driven by real people and real life.*

---

## Ali Imperiale

> ⚠️ YouTube is **one strike away from termination**. Strategy: funnel her audience to backup channels so any can become the main overnight. YouTube drives Patreon — it stays the priority while it lasts.

| Platform | Link | Notes |
|----------|------|-------|
| YouTube | [@aliimperiale](https://www.youtube.com/channel/aliimperiale) — 127K | **At risk — one strike away from termination** |
| YouTube Shorts | [Ali Imperiale Shorts](https://www.youtube.com/channel/UCvwhZDstIfchS8T-x7I0Jgw) | Dedicated Shorts channel — backup under her umbrella |
| Facebook | [Ali Imperiale](https://www.facebook.com/people/Ali-Imperiale/61581368111171/) — 34K | ~$2K/month — distant second driver for Patreon |
| Instagram | [@aliimperiale](https://www.instagram.com/aliimperiale/) | She's active, low subs, low value being created |
| TikTok | [@aliimperiale](https://www.tiktok.com/@aliimperiale) | Slowly growing |
| Patreon | [patreon.com/cw/aliimperiale](https://www.patreon.com/cw/aliimperiale) | ~$10K/month — YouTube is main driver |
| Website | [aliimperiale.com](https://aliimperiale.com/) | Hosted on GitHub Pages, repo on Desktop |

**Revenue breakdown:** ~$15K/month total — Patreon $10K, Facebook $2K, rest $3K. YouTube is the primary Patreon driver; Facebook is a distant second.

### Audience Migration Strategy — Emergency Email List

**Concept:** Replace every link in every YouTube video description with a single Kit form URL. At ~1:00 in every video, Ali delivers this script:

> "Hey guys, real quick — I need a small favor from you. This channel might not be here forever. Because of the nature of the topics I cover, one day a word, a link, a video could get me a strike and the whole channel disappears overnight. I've already spread my wings — I've got backup channels on YouTube and accounts on other platforms — but none of that matters if I can't find you again.
>
> So I created something simple. There's a link in the description — it's a form, you just enter your email. That's it. You'll get one automatic email with all my links — YouTube, Instagram, Facebook, everything. And if the worst happens and I lose this channel, I'll send you one single email to tell you where to find me.
>
> This is not a mailing list. I'm not going to email you every week. I'm not going to sell you anything. If I ever start a real newsletter, I'll ask you properly. This is just my way of staying connected to you, my friends, in case of emergency.
>
> The link is in the description. Takes 10 seconds. Means the world to me."

**Mechanics:**
- **Form:** Kit (ConvertKit) signup form — email only, no friction
- **Auto-email on signup:** One email, styled like a linktree — all her channels and platforms
- **Emergency email:** If @aliimperiale is terminated, send one email pointing to backup channels
- **Promise kept:** No newsletter, no weekly emails — unless she explicitly asks permission later

**Why it works:** "Not a mailing list" removes the #1 objection. Single CTA across all videos. The signup email lives in their inbox forever as a reference — better than a pinned comment.

---

## Travel with Ali Imperiale

Repurposed footage from Gab's Adventures that features Ali — biking, walking, travel. Already has 899 legit subscribers under [@olivetrvl](https://www.youtube.com/@olivetrvl). Rebrand it rather than starting from zero.

**Branding:** "Travel with Ali Imperiale" — leverages her name, acts as audience capture net if @aliimperiale goes down.

| Platform | Link | Notes |
|----------|------|-------|
| YouTube | [Travel with Ali Imperiale](https://www.youtube.com/channel/UCJp1lMTzYzd_UMtN6mTE0ZA) — 899 | Rebranded from @olivetrvl |
| Instagram | TBD | Reels from same footage |
| TikTok | TBD | Short clips |

---

## Gab's Adventures *(Gab à l'aventure)*

Adventure vlogs — bike, walk, travel, etc. A lot of the footage also features Ali.

| Platform | Link | Notes |
|----------|------|-------|
| YouTube | [Gab's Adventures](https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w) — 1,100 | Adventure vlogs, French |
| Instagram | [@gabrieldancause](https://www.instagram.com/gabrieldancause) | |
| X / Twitter | [@Gabdancause](https://x.com/Gabdancause) | |
| TikTok | [@gabrieldancause](https://www.tiktok.com/@gabrieldancause) | |

### Gab's Other YouTube Channels

| Channel | Handle | Subscribers | Notes |
|---------|--------|-------------|-------|
| More Gab | [@moregab](https://www.youtube.com/@moregab) | 1,230 | |
| Gab's Podcast | [@gabspodcast](https://www.youtube.com/@gabspodcast) | 1,150 | Currently active |
| Gab & Ali (español, Gab solo) | [@gabenespanol](https://www.youtube.com/@gabenespanol) | 1,030 | |
| Gab lab | [@gabdancause](https://www.youtube.com/@gabdancause) | 621 | |
| Paradigme 2 | [@paradigme2220](https://www.youtube.com/@paradigme2220) | 212 | |
| Gab Cafe Podcast | [@gabcafepodcast](https://www.youtube.com/@gabcafepodcast) | 132 | |

---

# BRANDS / PROGRAMMATIC

*Property and concept-driven — content is systematic, AI-assisted, or brand-first.*

---

## The Nookie Nook *(by Ali Imperiale)*

Sex education news site. Leverages Ali's brand. Same engine as gab.ae.

**Branding:** "by Ali Imperiale" is the hook — her name gives it instant credibility and cross-audience reach.

| Platform | Link | Notes |
|----------|------|-------|
| Website | [thenookienook.com](https://thenookienook.com) | News site, same engine as gab.ae |
| YouTube | [@TheNookieNook](https://www.youtube.com/@TheNookieNook) | Starting to get views |
| Instagram | [@thenookienook](https://www.instagram.com/thenookienook/) | Active |

---

## La Casita Hedonista *(by Ali Imperiale)*

Property in Mexico. Previously operated as jungle camping ([old Facebook](https://www.facebook.com/mexicojunglecamping/?locale=fr_CA)), now pivoting to a hedonist concept under Ali's brand.

**Branding:** "by Ali Imperiale" ties it to her audience and Patreon ecosystem. Position: sensual, adult, lifestyle — distinct from The Nookie Nook (news) but same brand family.

| Platform | Link | Notes |
|----------|------|-------|
| YouTube | [@casitahedonista](https://www.youtube.com/@casitahedonista) | New dedicated channel — live |
| Facebook (old) | [Mexico Jungle Camping](https://www.facebook.com/mexicojunglecamping/?locale=fr_CA) | Old brand — pivot or replace |
| Instagram | TBD | New account for hedonist rebrand |

---

## GAB News

AI-powered news engine, publishes articles every 5 minutes. Auto-generates news Shorts — pipeline built, needs to move to VPS.

| Platform | Notes |
|----------|-------|
| Website | [gab.ae](https://gab.ae) — has traffic |
| YouTube | TBD — create channel for auto-published Shorts |
| TikTok | TBD |
| Instagram | TBD |
| Facebook | TBD |

---

# UNPLANNED

*Exist but no strategy yet.*

---

## Gab & Ali (Collab) — Dormant

| Platform | Handle | Subscribers | Notes |
|----------|--------|-------------|-------|
| YouTube (FR) | [@gabalienfrancais](https://www.youtube.com/@gabalienfrancais) | 96 | No plan |
| YouTube (ES) | [@gabyaliespanol](https://www.youtube.com/@gabyaliespanol) | 54 | No plan |

## Other / Niche

| Channel | Handle | Subscribers | Notes |
|---------|--------|-------------|-------|
| Auberge de Nos Aïeux | [@aubergedenosaieux2264](https://www.youtube.com/@aubergedenosaieux2264) | 14 | Property/hospitality |
| Getting Stuff Done | [@gettingdone](https://www.youtube.com/@gettingdone) | 0 | Not yet launched |

---

## TODOs

### VPS & Pipeline — in order
- [ ] **Spin up Hetzner CX22** — create account, Ubuntu 24.04, add SSH key, install FFmpeg + Python stack
- [ ] **Create Google Drive service account** — share `footage/` folder with it for pipeline access
- [ ] **Get OpenRouter API key** — for Gemini Flash vision (Ali detection in footage)
- [ ] **Choose background music track** — drop mp3 on VPS for footage audio replacement
- [ ] **Build & deploy `footage_pipeline.py`** — write pipeline, pick Ali reference photo, test with one DJI clip, set up systemd service
- [ ] **Deploy `npx wrangler deploy`** — `/api/shorts-feed` endpoint was blocked by Cloudflare outage, retry
- [ ] **Move GAB News Shorts pipeline to VPS** — migrate `shorts/generate_shorts.py`, set up daily cron
- [ ] **Build `shorts/publish_shorts.py`** — Hootsuite API, publishes per platform schedule, logs to `shorts/publish_log.json`

### Socials — Quick fixes
- [ ] **The Nookie Nook Instagram bio link** — remove the `www` from the website link in the [@thenookienook](https://www.instagram.com/thenookienook/) bio
- [ ] **The Nookie Nook YouTube profile picture** — change to Ali's photo at [@TheNookieNook](https://www.youtube.com/@TheNookieNook)
- [ ] **Create social accounts for GAB News** — YouTube, TikTok, Instagram, Facebook for the news Shorts pipeline

### Strategy
- [ ] **Ali — Kit form setup** — create Kit signup form (email only), write linktree-style auto-email (all channels + Patreon), replace all YouTube description links with form URL
- [ ] **Ali — add email CTA to videos** — record and add the 1-min emergency email script to every new video
- [ ] **The Nookie Nook — Shorts pipeline** — decide if it gets its own feed (same engine as gab.ae), or shares the GAB News pipeline
- [ ] **Rebrand @olivetrvl → Travel with Ali Imperiale** — rename channel, update description, link from @aliimperiale; create matching Instagram and TikTok; start clipping Ali footage from Gab's Adventures
- [ ] **La Casita Hedonista** — define brand, create socials, decide what to do with old Mexico Jungle Camping Facebook
- [ ] **Cross-channel section** — Add a "Find me everywhere" section at the bottom of every YouTube channel's About page
- [ ] **Ads to Ali's audience** — Run ads targeting Ali's existing fans to push toward backup channels
- [ ] **Gab's Patreon** — Create a Patreon for Gab's Adventures

---

## Summary

| Property | Category | Key Asset | Risk |
|----------|----------|-----------|------|
| Ali Imperiale | Human | 127K YouTube (~$15K/mo total) | YouTube one strike from death |
| Travel with Ali Imperiale | Human | 899 subs + existing footage | Needs rebrand |
| Gab's Adventures | Human | Adventure YouTube + socials | Low growth |
| The Nookie Nook | Brand | Growing YouTube + Instagram | Early stage |
| La Casita Hedonista | Brand | Mexico property + Ali's brand + @gabandali (1,140) | Needs rebrand |
| GAB News | Programmatic | Traffic + auto-Shorts pipeline | Pipeline needs to move to VPS |
| Gab & Ali collab | Unplanned | ~150 subs | No strategy |
