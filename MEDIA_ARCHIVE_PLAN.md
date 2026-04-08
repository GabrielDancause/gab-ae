# Media Archive & Membership Pipeline — Plan

Status: draft v1
Owner: Gab
Last updated: 2026-04-08

## Goal

Build a personal/family media archive that:

1. Pulls everything out of Google Photos via Takeout → Google Drive (one-time + periodic catch-up).
2. Treats Google Drive as the **single source of truth** going forward.
3. Publishes selected content to Internet Archive (lossless masters) and YouTube (unlisted, viewable backup).
4. Sells access to a curated subset via a Stripe-backed membership section on a website.
5. Delivers member access via emailed unlisted URLs (no account/login system in v1).

The DB question is deliberately deferred — covered in §9.

---

## 1. Phase 0 — Takeout out of Google Photos

**One-time bootstrap, then optional periodic refreshes.**

- Trigger Google Takeout from both accounts (mine + girlfriend's, since partner-shared content lives on her account even with auto-save on).
- Delivery target: **Google Drive**, not email. Splits into ~50 GB `.tgz` archives.
- Format: `.tgz` (smaller than zip, scriptable extraction).
- Frequency: one-shot for the historical bulk. Then enable Google's built-in "every 2 months for 1 year" scheduled export as a safety net. **No realtime/daily Takeout exists** — Google deliberately doesn't expose that. Browser automation is a TOS violation, not worth the account risk.
- Verify: spot-check that auto-saved partner-shared photos actually appear in my Takeout (the JSON sidecars tag them with `googlePhotosOrigin: partnerShared`).

**Output:** a `Takeout/` folder in Drive with ~N `.tgz` archives.

---

## 2. Phase 1 — Extract & reorganize into the source-of-truth folder structure

Once the Takeout files are sitting in Drive, run a worker (locally on the Mac Mini, or as a Cloudflare-triggered job pulling via Drive API) that:

1. Downloads each `.tgz`.
2. Extracts on a scratch volume.
3. Reads each photo/video's JSON sidecar to recover the real `photoTakenTime`, GPS, and partner-sharing flag (Takeout strips most EXIF and writes it to sidecar files instead).
4. Merges sidecar metadata back into the file with `exiftool` so the originals are self-describing.
5. Computes hashes (perceptual hash for images, sha256 + duration + first-frame hash for video).
6. Writes the file into the canonical folder structure below.
7. Records the file in a manifest (CSV or SQLite or D1 — see §9).

After this phase, the original `.tgz` archives can be moved to a `Takeout/_processed/` folder (or deleted once verified).

### 2.1 Canonical folder structure in Drive

This is the layout Drive will hold *after* the Takeout extraction. Date-first because that's how 95% of personal media browsing works.

```
/Archive/
├── _inbox/                        ← new files land here before classification
│   └── (camera dumps, unsorted phone backups, etc.)
│
├── _processed/                    ← Takeout tgz archives after extraction (or delete)
│
├── photos/
│   ├── 2014/
│   │   ├── 2014-06/
│   │   │   ├── 2014-06-12_birthday-marie/
│   │   │   │   ├── IMG_0001.jpg
│   │   │   │   ├── IMG_0002.jpg
│   │   │   │   └── _meta.json     ← perceptual hashes, source, dedup info
│   │   │   └── 2014-06-unsorted/  ← shots that don't belong to a named event
│   │   └── 2014-07/
│   ├── 2015/
│   ├── ...
│   └── 2026/
│
├── videos/
│   ├── 2014/
│   │   └── 2014-06/
│   │       ├── 2014-06-12_birthday-marie/
│   │       │   ├── VID_0001.mp4   ← original master (highest quality available)
│   │       │   └── _meta.json
│   │       └── 2014-06-unsorted/
│   ├── ...
│   └── 2026/
│
├── projects/                      ← stitched/edited deliverables, NOT raw
│   ├── 2025-summer-trip/
│   │   ├── master.mkv             ← lossless final cut
│   │   ├── proxy.mp4              ← h.264 viewable copy
│   │   ├── source-list.txt        ← which files from /videos/ went into this
│   │   └── _meta.json
│   └── 2026-q1-recap/
│
├── partner-shared/                ← optional: mirror of partner's contributions
│   │                                (only if we decide to keep them physically separated;
│   │                                otherwise they live alongside everything else and
│   │                                are tagged in _meta.json)
│   └── ...
│
└── _system/
    ├── manifest.sqlite            ← OR mirror of the D1 if we go that route
    ├── dedup-log.jsonl
    └── ingest-runs/
        └── 2026-04-08T14-22-00.log
```

### 2.2 Naming rules

- **Folders**: `YYYY-MM-DD_kebab-case-event-name`. Date-first sorts naturally. Event name optional but encouraged.
- **Files**: keep the original camera filename (`IMG_0001.jpg`, `DSC_4421.NEF`, `PXL_20240612_143022.mp4`). Don't rename — it breaks reverse-lookup against Photos and against the original device.
- **Year/month folders**: `YYYY/YYYY-MM/`. Yes, the year repeats in the path. It's worth it for grep-ability (`find /Archive/photos/2024-06 …`) and so each level sorts cleanly on its own.
- **The `_meta.json` per event folder** holds: source (gphotos_gab, gphotos_gf, gdrive_gab, camera_card), partner_shared bool, perceptual hashes for each file, and any human notes.

### 2.3 Why date-first and not event-first?

- 90% of "find a photo" queries are date-anchored ("summer 2022", "Marie's birthday last year").
- Events come and go, dates don't.
- Easy to merge new content from new sources — you just drop it in the right month.
- Compatible with how Photos itself organizes things, so the mental model carries over.

The tradeoff: you can't browse "all birthdays" in one folder. That's what the database is for (§9). Folders are for storage; queries are for browsing.

---

## 3. Phase 2 — Drive becomes the source of truth

After Phase 1 completes, the rules change:

- **New phone photos**: configure phones to back up to Drive directly (via Drive's mobile app or `rclone` from the phone), into `/Archive/_inbox/`. Stop relying on Google Photos as the canonical destination. Photos can still be a viewer, but it's no longer the master.
- **Camera card dumps**: copy to `/Archive/_inbox/` then run the same classifier worker that handles Takeout extracts.
- **Inbox triage**: a daily/weekly scheduled job moves files from `_inbox/` into the proper `photos/YYYY/YYYY-MM/` or `videos/YYYY/YYYY-MM/` folders based on EXIF capture date. Files with no usable date go to `/photos/_undated/` for manual review.
- **Google Photos** stays as a consumer endpoint that I push *to* (optional), not pull from. Avoids the deprecated Library API entirely.

---

## 4. Phase 3 — Stitching / editing

Out of scope for the automated pipeline. This is whatever I do in Premiere/Resolve/ffmpeg, with the rule that:

- Output goes to `/Archive/projects/<project-slug>/`.
- `master.<ext>` is the highest-quality export (ProRes, FFV1, or h.264 CRF 16, depending on use case).
- `proxy.mp4` is the viewable version (1080p h.264 + AAC, ~5 Mbps).
- `source-list.txt` records the input files from `/videos/` so I can trace what went in.

---

## 5. Phase 4 — Publishing to Internet Archive

For each `projects/<slug>/` that I want to preserve:

- Use the `internetarchive` Python CLI.
- Upload `master.<ext>` as the IA "original" — IA's deriver will auto-generate the streaming versions.
- Optionally include a `_rules.conf` with `CAT.lossy` to suppress lossy derivatives if I want to save IA's disk and limit casual streaming.
- Item identifier: `gab-<project-slug>-<short-random>` (random suffix makes it harder to guess).
- Metadata: minimal title/description, no descriptive tags that would make it discoverable in IA's own search.
- Item is technically public (IA has no real "unlisted") but the obscure URL is the access control. Threat model: "meh if it leaks."
- After upload completes, record the IA identifier and URL in the manifest/DB.

**Chunking rule**: each IA item stays under 500 GB and 500 files. For most projects this is one item; for huge multi-day shoots, split into `<slug>-pt1`, `<slug>-pt2`, etc.

---

## 6. Phase 5 — Publishing to YouTube (unlisted)

Parallel to IA, for each project:

- Upload `proxy.mp4` (not the master — YouTube re-encodes anyway, no point uploading 200 GB).
- YouTube Data API v3, `videos.insert`, `privacyStatus: "unlisted"`.
- Title = project slug, description = a date and one-line summary, no tags.
- Quota cost: 1,600 units per upload, default daily quota is 10,000 units → ~6 uploads/day. If this becomes a bottleneck, request a quota increase (free, takes ~1-2 weeks).
- Record the resulting YouTube video ID in the manifest/DB.

YouTube serves as: (a) a viewable second copy in case IA goes down, (b) the actual embed source for the member website (because YouTube's player + CDN is free and good).

---

## 7. Phase 6 — Stripe payment + email delivery

The simplest possible flow, no account system:

1. Member visits a public landing page (e.g. `gab.ae/members` or a dedicated subdomain) with a "Get access" button.
2. Button → Stripe Checkout (one-time payment or subscription, TBD).
3. Stripe webhook (`checkout.session.completed`) hits a Cloudflare Worker.
4. Worker generates a long random token (32+ chars), writes a row mapping `{token, email, tier, granted_at, expires_at?}` to D1 (or KV — see §9).
5. Worker calls Resend to email the member their personal access URL: `https://gab.ae/m/<token>`.
6. Done. No password, no account, no login form.

**Revocation**: delete the row. **Re-send**: look up by email, re-email the same token.

**Idempotency**: Stripe webhook handler uses the Stripe event ID as a unique key so duplicate deliveries don't create duplicate rows.

---

## 8. Phase 7 — The member-only section of the website

The "/m/<token>" route:

1. Worker validates the token against the DB.
2. If valid, it loads the member's tier and queries the list of assets they're allowed to see.
3. Renders a gallery page with embedded YouTube unlisted players + thumbnails.
4. Gallery is grouped by date (year → month), Google-Photos-style.
5. Frontend = Astro page with a React island for the grid (PhotoSwipe lightbox + a justified-layout grid library).
6. Page has `<meta name="robots" content="noindex,nofollow">` and the route is in `robots.txt` under `Disallow: /m/`. Threat model accepts that a determined member could share the link.

**v1 scope**: just the grid + YouTube embeds. No face recognition, no search, no tagging. Date-based browsing only.

**v2 maybe**: keyword search, faces, member-side favorites. Nothing here in v1.

---

## 9. The database question (deferred)

Three viable options, in order of complexity:

### Option A — No database, just files
- Use `_meta.json` files in each folder + a single `manifest.sqlite` in `/Archive/_system/`.
- Pros: zero infra, fully self-contained, can be `rclone`'d anywhere.
- Cons: hard to query from a website Worker without shipping the SQLite around. Bad fit for the membership site backend.
- Use case: works if the membership site is essentially static and rebuilt on each publish.

### Option B — Cloudflare D1 (recommended starting point)
- Already in use on `gab.ae`. One more table set, same Worker.
- Pros: native to the existing stack, free tier is generous, integrates with Stripe webhook + member auth.
- Cons: still relatively young; multi-tenant migration story (if I ever split gab.ae and aliimperiale.com) needs thought.
- Use case: this is almost certainly the right answer.

### Option C — Postgres (Supabase or Neon)
- Heavier, but more familiar tooling and better full-text search if I ever want it.
- Pros: scales further, mature ecosystem.
- Cons: another vendor, another bill, another thing to monitor.
- Use case: only if D1 actually starts to hurt at scale.

**Decision: start with Option B (D1).** Schema sketch (subject to change):

```sql
-- Canonical asset, identified by content
CREATE TABLE assets (
  id TEXT PRIMARY KEY,
  perceptual_hash TEXT,
  sha256 TEXT NOT NULL,
  media_type TEXT NOT NULL,        -- 'photo' | 'video'
  duration_s REAL,
  width INTEGER,
  height INTEGER,
  captured_at INTEGER,             -- unix seconds
  drive_path TEXT NOT NULL,        -- canonical location in /Archive/
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_assets_phash ON assets(perceptual_hash);
CREATE INDEX idx_assets_captured ON assets(captured_at);

-- Where this asset has been seen across sources
CREATE TABLE asset_sources (
  asset_id TEXT NOT NULL,
  source TEXT NOT NULL,            -- 'gphotos_gab' | 'gphotos_gf' | 'gdrive' | 'camera_card'
  source_id TEXT NOT NULL,
  partner_shared INTEGER NOT NULL DEFAULT 0,
  first_seen_at INTEGER NOT NULL,
  PRIMARY KEY (source, source_id)
);

-- Where this asset has been published
CREATE TABLE asset_publications (
  asset_id TEXT NOT NULL,
  destination TEXT NOT NULL,       -- 'internet_archive' | 'youtube' | 'r2_member'
  destination_id TEXT NOT NULL,
  destination_url TEXT,
  visibility TEXT,                 -- 'public' | 'unlisted' | 'members_only'
  published_at INTEGER NOT NULL,
  PRIMARY KEY (destination, destination_id)
);

-- Member tier access control
CREATE TABLE asset_access (
  asset_id TEXT NOT NULL,
  tier TEXT NOT NULL,              -- 'public' | 'tier_basic' | 'tier_premium'
  PRIMARY KEY (asset_id, tier)
);

-- Members
CREATE TABLE members (
  token TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  tier TEXT NOT NULL,
  stripe_customer_id TEXT,
  granted_at INTEGER NOT NULL,
  expires_at INTEGER,
  revoked_at INTEGER
);
CREATE INDEX idx_members_email ON members(email);

-- Stripe webhook idempotency
CREATE TABLE stripe_events (
  event_id TEXT PRIMARY KEY,
  processed_at INTEGER NOT NULL
);
```

---

## 10. Build order

Each step should be runnable and demoable on its own before moving to the next.

1. **Takeout export from both accounts → Drive.** Manual click. Verify partner-shared content shows up in mine.
2. **Folder structure created in Drive.** Empty skeleton (`/Archive/photos/`, `/Archive/videos/`, etc.).
3. **D1 schema deployed** to the existing gab.ae Cloudflare project.
4. **Tiny CLI script** that takes a folder path, hashes everything, inserts into D1. Test on a sample of 100 photos. Verify perceptual hash correctly collapses known duplicates.
5. **Takeout extractor**: download `.tgz` from Drive, extract, merge sidecar metadata back into files via `exiftool`, place files in canonical folders, register in D1.
6. **Drive scanner** for ongoing `_inbox/` ingestion. Cloudflare Cron trigger, runs hourly or daily.
7. **Bootstrap reconciliation**: list anything already on my IA account and YouTube channel, hash, backfill `asset_publications` so the publish step doesn't re-upload existing content.
8. **Publish pipeline**: given an asset (or project folder), push to IA + YouTube, write rows to `asset_publications`. Idempotent. Test on 5 assets.
9. **Stripe checkout + webhook + Resend email** for the membership flow. Test with a $1 test product end-to-end.
10. **Member gallery page** at `/m/<token>`. Read-only D1 query, justified-layout grid, PhotoSwipe lightbox, YouTube embeds. Date-grouped.
11. **Polish**: noindex headers, robots.txt, 404 handling for invalid/expired tokens, basic admin page to revoke a member.

---

## 11. Open questions / decisions still to make

- **One repo or two** for gab.ae vs aliimperiale.com? (Leaning two repos with a shared `media-pipeline` package.)
- **Membership pricing model**: one-time, recurring, or both?
- **Tier structure**: single tier or multiple? Affects `asset_access` complexity.
- **What's actually published vs. private?** Need an explicit conversation about which content (especially partner-shared) is okay to put on IA, on YouTube unlisted, on the members site.
- **R2 vs IA for member-gated media**: probably R2 with signed URLs for anything genuinely private, IA only for "meh if it leaks" content. Both can coexist via the `destination` column.
- **Deletion / right-to-be-forgotten flow**: how do I remove an asset from all destinations cleanly? Needs a `delete_from_all()` function that walks `asset_publications` and removes from each.
- **Backup of the manifest itself**: D1 should be exported nightly to R2 as a SQL dump. The whole archive is worthless if the index is lost.

---

## 12. Out of scope (for now)

- Face recognition / people tagging.
- Full-text search across descriptions.
- Mobile app.
- Multi-user collaborative editing (girlfriend uploading directly).
- Auto-generated highlight reels.
- Public, non-member portfolio site (separate project).

These are all reasonable v2 features but would each double the complexity of v1. Ship v1 first.
