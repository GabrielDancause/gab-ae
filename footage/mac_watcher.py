#!/usr/bin/env python3
"""
mac_watcher.py — watches ~/Downloads/_Pipeline/ for new footage folders.

Flow:
  1. Detect stable folder (no file changes in 2 min)
  2. Move to _processing/
  3. Run mac_process_long.py on it
  4. Move to _done/ on success, back to root on failure

launchd keeps this running permanently at login.
Log: ~/Library/Logs/gab-footage-watcher.log

Manual test:
  python3 -m footage.mac_watcher --once    # one scan then exit
  python3 -m footage.mac_watcher           # run forever (launchd mode)
"""

import subprocess
import sys
import time
from pathlib import Path

PIPELINE_DIR   = Path.home() / 'Downloads' / '_Pipeline'
PROCESSING_DIR = PIPELINE_DIR / '_processing'
DONE_DIR       = PIPELINE_DIR / '_done'
POLL_SECS      = 60      # how often to scan
STABLE_SECS    = 120     # folder must be unchanged this long before claiming


def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def folder_is_stable(path):
    """True if no file in folder has been modified in the last STABLE_SECS seconds."""
    newest = 0
    for p in path.rglob('*'):
        try:
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest > 0 and (time.time() - newest) > STABLE_SECS


def scan_once():
    """Scan PIPELINE_DIR for one claimable folder. Returns True if something was processed."""
    for entry in sorted(PIPELINE_DIR.iterdir()):
        if entry.name.startswith('_') or not entry.is_dir():
            continue

        if not folder_is_stable(entry):
            log(f"Waiting: {entry.name} (still copying...)")
            continue

        # Claim it
        target = PROCESSING_DIR / entry.name
        try:
            entry.rename(target)
        except Exception as e:
            log(f"Could not claim {entry.name}: {e}")
            continue

        log(f"Claimed: {entry.name} → _processing/")

        try:
            result = subprocess.run(
                [sys.executable, '-m', 'footage.mac_process_long', str(target)],
                cwd=str(Path.home() / 'Desktop' / 'gab-ae'),
                timeout=86400,   # 24h max per folder
            )
            if result.returncode == 0:
                dest = DONE_DIR / entry.name
                target.rename(dest)
                log(f"Done: {entry.name} → _done/")
            else:
                target.rename(PIPELINE_DIR / entry.name)
                log(f"Failed (exit {result.returncode}): {entry.name} — returned to queue")
        except subprocess.TimeoutExpired:
            log(f"Timeout: {entry.name} — returned to queue")
            target.rename(PIPELINE_DIR / entry.name)
        except Exception as e:
            log(f"Error processing {entry.name}: {e} — returned to queue")
            try:
                target.rename(PIPELINE_DIR / entry.name)
            except Exception:
                pass

        return True  # processed one, re-scan immediately

    return False  # nothing to do


def main():
    once = '--once' in sys.argv

    PROCESSING_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)

    # On startup: return any stuck _processing folders to queue
    for stuck in PROCESSING_DIR.iterdir():
        if stuck.is_dir():
            log(f"Recovering stuck folder: {stuck.name}")
            stuck.rename(PIPELINE_DIR / stuck.name)

    log(f"Watcher started. Scanning {PIPELINE_DIR} every {POLL_SECS}s")

    if once:
        scan_once()
        return

    while True:
        try:
            found = scan_once()
            if not found:
                time.sleep(POLL_SECS)
        except KeyboardInterrupt:
            log("Watcher stopped.")
            break
        except Exception as e:
            log(f"Unexpected error: {e}")
            time.sleep(POLL_SECS)


if __name__ == '__main__':
    main()
