#!/usr/bin/env python3
"""
backup_manager.py — Track and upload source folders to multiple destinations.

Usage:
    python3 footage/backup_manager.py --status
    python3 footage/backup_manager.py --backup all [--destination ia|youtube|all]
    python3 footage/backup_manager.py --backup "2026-06-04 - North Hatley en bike"
    python3 footage/backup_manager.py --scan-sidecars /Volumes/obiwan   # rebuild manifest from .backup files
    python3 footage/backup_manager.py --verify                          # check checksums + completeness
    python3 footage/backup_manager.py --dry-run --backup all            # preview without uploading
"""

import argparse, configparser, hashlib, json, os, re, subprocess, sys, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_FILE = Path(__file__).parent / "backup_manifest.json"
SIDECAR_NAME  = ".backup"
IA_ACCESS     = os.environ.get("IA_ACCESS", "Ot0FVHkLiDTD4WDE")
IA_SECRET     = os.environ.get("IA_SECRET", "caXpcbAZF8nfBX1D")

# Only skip OS/filesystem junk — never skip actual content files
SKIP_PATTERNS = {
    "._",                        # macOS metadata forks (invisible, not real files)
    ".DS_Store",                 # macOS folder settings
    "Thumbs.db",                 # Windows thumbnail cache
    "$RECYCLE.BIN",              # Windows recycle bin
    "System Volume Information", # Windows system folder
    ".Spotlight-V100",           # macOS Spotlight index
    ".Trashes",                  # macOS trash
    ".fseventsd",                # macOS filesystem events
    SIDECAR_NAME,                # our own .backup file
    ".LRF",                      # DJI low-res proxy — IA rejects these, originals are the MP4s
    ".lrf",
}

# Configured source locations — add more drives here over time
SOURCES = [
    {
        "root": "/Volumes/obiwan",
        "label": "obiwan",
        "scan_depth": 1,   # each subfolder = one session
        "skip_dirs": {"broadcast_ready", "broadcast_ready_vertical",
                      "$RECYCLE.BIN", "System Volume Information"},
        # Folders whose name contains these strings get a custom label
        "label_overrides": [
            ("ali", "ali-imperiale"),
        ],
    },
    {
        "root": "/Volumes/Untitled/DCIM/100MSDCF",
        "label": "sony-card",
        "scan_depth": 0,   # the folder itself is the session
    },
]


# ── Checksums ─────────────────────────────────────────────────────────────────

def md5(path, chunk=8 * 1024 * 1024):
    """Compute MD5 of a file, reading in chunks."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


# ── Sidecar (.backup) ─────────────────────────────────────────────────────────

def read_sidecar(folder):
    """Read .backup file → dict of {section: {key: value}}."""
    p = Path(folder) / SIDECAR_NAME
    if not p.exists():
        return {}
    cfg = configparser.ConfigParser(allow_no_value=True)
    cfg.optionxform = str   # preserve case
    content = "[_root]\n" + p.read_text()
    cfg.read_string(content)
    return {section: dict(cfg[section]) for section in cfg.sections()}

def write_sidecar(folder, data):
    """Write .backup file from dict of {section: {key: value}}."""
    p = Path(folder) / SIDECAR_NAME
    lines = []
    root = data.get("_root", {})
    for k, v in root.items():
        lines.append(f"{k:<16}{v}")
    for section, kv in data.items():
        if section == "_root":
            continue
        lines.append(f"\n[{section}]")
        for k, v in kv.items():
            lines.append(f"{k:<16}{v}")
    p.write_text("\n".join(lines) + "\n")

def update_sidecar(folder, section, updates):
    """Merge updates into one section of the .backup file."""
    data = read_sidecar(folder)
    data.setdefault("_root", {})
    data["_root"]["source"] = str(folder)
    parts = Path(folder).parts
    data["_root"].setdefault("drive", parts[2] if len(parts) > 2 else parts[0])
    data.setdefault(section, {})
    data[section].update(updates)
    write_sidecar(folder, data)

def write_checksum_section(folder, checksums):
    """Write/update the [checksums] section in .backup."""
    data = read_sidecar(folder)
    data.setdefault("_root", {})
    data["_root"]["source"] = str(folder)
    # Store as "filename  md5:abc123"
    data["checksums"] = {rel: f"md5:{chk}" for rel, chk in checksums.items()}
    write_sidecar(folder, data)


# ── Manifest ──────────────────────────────────────────────────────────────────

def load_manifest():
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {"sessions": {}, "version": 1}

def save_manifest(m):
    with open(MANIFEST_FILE, "w") as f:
        json.dump(m, f, indent=2)

def session_key(folder_path):
    p = Path(folder_path)
    return f"{p.parent.name}/{p.name}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]

def label_for(src, folder_name):
    """Return label, applying overrides if folder name matches."""
    for pattern, override_label in src.get("label_overrides", []):
        if pattern.lower() in folder_name.lower():
            return override_label
    return src["label"]

def ia_id_for(label, folder_name):
    return f"gab-raw-{label}-{slugify(folder_name)}"

def ia_remote(ia_id):
    return f":internetarchive,access_key_id={IA_ACCESS},secret_access_key={IA_SECRET}:{ia_id}"

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def should_skip(path):
    s = str(path)
    name = Path(path).name
    return name.startswith("._") or name in SKIP_PATTERNS or any(pat in s for pat in SKIP_PATTERNS)

def scan_files(folder):
    """Return list of (rel_path, abs_path, size_bytes) for all files."""
    results = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not should_skip(Path(root) / d))
        for fname in sorted(files):
            abs_path = Path(root) / fname
            if should_skip(abs_path):
                continue
            rel = str(abs_path.relative_to(folder))
            try:
                results.append((rel, str(abs_path), abs_path.stat().st_size))
            except OSError:
                pass
    return results

def total_gb(files):
    return round(sum(sz for _, _, sz in files) / 1024**3, 2)


# ── IA upload ─────────────────────────────────────────────────────────────────

def upload_file_ia(abs_path, rel_path, ia_id, title, folder_name, size_bytes=0):
    dest = f"{ia_remote(ia_id)}/{urllib.parse.quote(rel_path)}"
    # Timeout: allow at least 60s + 1s per MB, minimum 120s, max 6h
    timeout_s = max(120, min(21600, 60 + size_bytes // (1024 * 1024)))
    cmd = [
        "rclone", "copyto", abs_path, dest,
        "--progress",
        "--stats-one-line",
        "--stats", "5s",
        "--header-upload", f"x-archive-meta-title:{title}",
        "--header-upload", f"x-archive-meta-description:Raw backup of {folder_name} by Gab Dancause",
        "--header-upload", "x-archive-meta-mediatype:movies",
        "--header-upload", f"x-archive-meta-subject:gab;raw;backup;{slugify(folder_name)}",
        "--header-upload", "x-archive-meta-creator:Gab Dancause",
        "--header-upload", "x-archive-meta-noindex:true",
        "--header-upload", "x-archive-meta-access-control:private",
    ]
    try:
        r = subprocess.run(cmd, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"    ✗ TIMEOUT after {timeout_s//60}min: {rel_path}")
        return False
    if r.returncode != 0:
        print(f"    ✗ FAILED: {rel_path}")
        return False
    return True

def backup_ia(folder_path, label, manifest, dry_run=False):
    folder_path = str(folder_path)
    folder_name = Path(folder_path).name
    key         = session_key(folder_path)
    ia_id       = ia_id_for(label, folder_name)
    title       = f"Raw backup — {folder_name}"

    if key not in manifest["sessions"]:
        manifest["sessions"][key] = {
            "folder": folder_path, "label": label,
            "ia_id": ia_id, "status": "pending",
            "files": {}, "created_at": now(),
        }
    session = manifest["sessions"][key]

    all_files = scan_files(folder_path)
    already   = session.get("files", {})
    pending   = [(r, a, s) for r, a, s in all_files
                 if already.get(r, {}).get("status") != "uploaded"]

    print(f"\n[IA] {folder_name}")
    print(f"     item  : {ia_id}")
    print(f"     url   : https://archive.org/details/{ia_id}")
    print(f"     files : {len(all_files)} total · {len(already)} done · {len(pending)} pending · {total_gb(all_files)} GB")

    if not pending:
        print("     ✓ Already complete")
        session["status"] = "complete"
        _finalize_sidecar(folder_path, ia_id, all_files, already, "complete")
        save_manifest(manifest)
        return

    if dry_run:
        print(f"     [dry-run] would upload {len(pending)} files")
        for rel, _, sz in pending[:5]:
            print(f"       {rel}  ({sz//1024//1024 or sz//1024} {'MB' if sz>1024*1024 else 'KB'})")
        if len(pending) > 5:
            print(f"       … and {len(pending)-5} more")
        return

    ok = fail = 0
    checksums = {rel: chk for rel, info in already.items()
                 if (chk := info.get("md5"))}   # carry over existing checksums

    for i, (rel, abs_p, sz) in enumerate(pending, 1):
        mb = sz // 1024 // 1024
        sz_str = f"{mb} MB" if mb else f"{sz//1024} KB"
        print(f"  [{i}/{len(pending)}] {rel} ({sz_str})", flush=True)

        # Compute checksum before upload
        print(f"    checksumming…", end="\r", flush=True)
        file_md5 = md5(abs_p)
        print(f"    md5: {file_md5[:16]}…  uploading…", end="\r", flush=True)

        if upload_file_ia(abs_p, rel, ia_id, title, folder_name, size_bytes=sz):
            session["files"][rel] = {
                "status": "uploaded", "size": sz,
                "md5": file_md5, "uploaded_at": now(),
            }
            checksums[rel] = file_md5
            ok += 1
            print(f"    ✓ md5:{file_md5[:16]}…")
        else:
            session["files"][rel] = {"status": "failed", "size": sz, "md5": file_md5}
            fail += 1

        save_manifest(manifest)   # crash-safe: save after every file

    status = "complete" if fail == 0 else "partial"
    session["status"] = status
    session["last_run"] = now()
    save_manifest(manifest)

    _finalize_sidecar(folder_path, ia_id, all_files, session["files"], status, checksums)
    print(f"\n  {'✓' if fail==0 else '⚠'} {ok} uploaded · {fail} failed")
    print(f"  https://archive.org/details/{ia_id}")

def _finalize_sidecar(folder_path, ia_id, all_files, files_dict, status, checksums=None):
    n_up = sum(1 for f in files_dict.values() if f.get("status") == "uploaded")
    update_sidecar(folder_path, "ia", {
        "item":    ia_id,
        "url":     f"https://archive.org/details/{ia_id}",
        "files":   f"{n_up} / {len(all_files)}",
        "size_gb": str(total_gb(all_files)),
        "status":  status,
        "date":    now(),
    })
    if checksums:
        # Write checksums section to sidecar
        data = read_sidecar(folder_path)
        data["checksums"] = {rel: f"md5:{chk}" for rel, chk in sorted(checksums.items())}
        write_sidecar(folder_path, data)


# ── Status report ─────────────────────────────────────────────────────────────

def status_report(manifest):
    COL = 44
    print()
    print(f"  {'FOLDER':<{COL}} {'IA':<20} {'YOUTUBE':<14} {'HETZNER'}")
    print("  " + "─" * 92)

    for key, s in sorted(manifest["sessions"].items()):
        folder = s["folder"]
        name   = Path(folder).name
        sc     = read_sidecar(folder) if Path(folder).exists() else {}
        exists = "⚠ drive offline" if not Path(folder).exists() else ""

        ia_str = _dest_str(sc.get("ia", {}), s)
        yt_str = _dest_str(sc.get("youtube", {}))
        hz_str = _dest_str(sc.get("hetzner", {}))
        suffix = f"  {exists}" if exists else ""

        print(f"  {name:<{COL}} {ia_str:<20} {yt_str:<14} {hz_str}{suffix}")

    untracked = discover_untracked(manifest)
    if untracked:
        print()
        print(f"  {'NOT YET TRACKED'}")
        print("  " + "─" * 92)
        for label, fpath in untracked:
            name = Path(fpath).name
            sc   = read_sidecar(fpath) if Path(fpath).exists() else {}
            ia_str = _dest_str(sc.get("ia", {}))
            yt_str = _dest_str(sc.get("youtube", {}))
            hz_str = _dest_str(sc.get("hetzner", {}))
            note = "  ← has .backup, not in manifest" if any([sc.get("ia"), sc.get("youtube"), sc.get("hetzner")]) else ""
            print(f"  {name:<{COL}} {ia_str:<20} {yt_str:<14} {hz_str}{note}")
    print()

def _dest_str(sc_section, session=None):
    if not sc_section:
        if session:
            st = session.get("status", "")
            n  = sum(1 for f in session.get("files", {}).values() if f.get("status") == "uploaded")
            if st == "complete": return f"✓ {n}f"
            if st == "partial":  return f"⚠ {n}f partial"
        return "✗"
    status = sc_section.get("status", "")
    files  = sc_section.get("files", "")
    if status == "complete": return f"✓ {files}f" if files else "✓"
    if status == "partial":  return f"⚠ {files}"
    return "?"


# ── Verify (checksums) ────────────────────────────────────────────────────────

def verify(manifest):
    """Re-compute MD5s on disk and compare against manifest."""
    print()
    any_issues = False
    for key, s in sorted(manifest["sessions"].items()):
        folder = s["folder"]
        name   = Path(folder).name
        if not Path(folder).exists():
            print(f"  ⚠  {name}  — drive offline, cannot verify")
            continue

        files = s.get("files", {})
        uploaded = {rel: info for rel, info in files.items()
                    if info.get("status") == "uploaded" and info.get("md5")}

        if not uploaded:
            print(f"  —  {name}  — no checksums recorded yet")
            continue

        print(f"  Verifying {name} ({len(uploaded)} files)…")
        ok = bad = missing = 0
        for rel, info in sorted(uploaded.items()):
            abs_p = Path(folder) / rel
            if not abs_p.exists():
                print(f"    ✗ missing on disk: {rel}")
                missing += 1
                continue
            expected = info["md5"]
            actual   = md5(str(abs_p))
            if actual == expected:
                ok += 1
            else:
                print(f"    ✗ CHECKSUM MISMATCH: {rel}")
                print(f"      expected: {expected}")
                print(f"      actual:   {actual}")
                bad += 1
                any_issues = True

        status = "✓" if bad == 0 and missing == 0 else "✗"
        print(f"  {status}  {name}: {ok} OK · {bad} corrupted · {missing} missing on disk")

    if not any_issues:
        print("\n  All checksums match ✓")
    print()


# ── Scan sidecars (recovery) ──────────────────────────────────────────────────

def scan_sidecars(root, manifest):
    """Walk a drive and rebuild manifest entries from .backup sidecar files."""
    found = 0
    for dirpath, dirs, files in os.walk(root):
        if SIDECAR_NAME in files:
            sc  = read_sidecar(dirpath)
            key = session_key(dirpath)
            if key not in manifest["sessions"]:
                ia_sec = sc.get("ia", {})
                manifest["sessions"][key] = {
                    "folder":   dirpath,
                    "label":    "recovered",
                    "ia_id":    ia_sec.get("item", ""),
                    "status":   ia_sec.get("status", "unknown"),
                    "files":    {},
                    "created_at": now(),
                    "recovered_from_sidecar": True,
                }
                print(f"  recovered: {dirpath}  →  {ia_sec.get('item', '(no ia)')}")
                found += 1
    save_manifest(manifest)
    print(f"\n  {found} new session(s) recovered → {MANIFEST_FILE}")


# ── Discover untracked ────────────────────────────────────────────────────────

def discover_untracked(manifest):
    tracked = {s["folder"] for s in manifest["sessions"].values()}
    untracked = []
    for src in SOURCES:
        root = Path(src["root"])
        if not root.exists():
            continue
        if src.get("scan_depth", 1) == 0:
            if str(root) not in tracked:
                lbl = label_for(src, root.name)
                untracked.append((lbl, str(root)))
        else:
            for child in sorted(root.iterdir()):
                if not child.is_dir(): continue
                if child.name in src.get("skip_dirs", set()): continue
                if should_skip(child): continue
                if str(child) not in tracked:
                    lbl = label_for(src, child.name)
                    untracked.append((lbl, str(child)))
    return untracked


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backup source folders to multiple destinations")
    parser.add_argument("--status",        action="store_true", help="Show backup status matrix")
    parser.add_argument("--backup",        metavar="FOLDER",    help="Folder name to back up, or 'all'")
    parser.add_argument("--destination",   default="ia",        choices=["ia", "youtube", "all"])
    parser.add_argument("--dry-run",       action="store_true", help="Preview without uploading")
    parser.add_argument("--verify",        action="store_true", help="Re-check MD5 checksums on disk")
    parser.add_argument("--scan-sidecars", metavar="PATH",      help="Rebuild manifest from .backup files on a drive")
    args = parser.parse_args()

    manifest = load_manifest()

    if args.scan_sidecars:
        scan_sidecars(args.scan_sidecars, manifest)
        return

    if args.verify:
        verify(manifest)
        return

    if args.status or not args.backup:
        status_report(manifest)
        return

    # Resolve target folders
    targets = []
    if args.backup == "all":
        for label, fpath in discover_untracked(manifest):
            targets.append((label, fpath))
        for key, s in manifest["sessions"].items():
            if s.get("status") in ("partial", "pending"):
                targets.append((s["label"], s["folder"]))
    else:
        query = args.backup.strip("/").lower()
        for src in SOURCES:
            root = Path(src["root"])
            if not root.exists(): continue
            candidates = [root] if src.get("scan_depth", 1) == 0 else sorted(root.iterdir())
            for child in candidates:
                if child.is_dir() and query in child.name.lower():
                    targets.append((label_for(src, child.name), str(child)))
                    break
        if not targets:
            p = Path(args.backup)
            if p.exists():
                targets.append(("manual", str(p)))
            else:
                print(f"Folder not found: {args.backup}")
                sys.exit(1)

    for label, fpath in targets:
        if args.destination in ("ia", "all"):
            backup_ia(fpath, label, manifest, dry_run=args.dry_run)
        if args.destination in ("youtube", "all"):
            print(f"\n[YouTube] {Path(fpath).name} — not yet implemented")

if __name__ == "__main__":
    main()
