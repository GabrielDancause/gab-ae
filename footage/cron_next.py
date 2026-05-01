#!/usr/bin/env python3
"""
Pop the next clip from queue.json and run it through process_one.py.
Outputs: RESULT: <title> | <youtube_url>
Called by the Claude Code scheduled task.
"""

import json
import subprocess
import sys
from pathlib import Path

QUEUE_FILE = '/opt/gab/footage/queue.json'
DONE_FILE  = '/opt/gab/footage/processed.json'
SCRIPT     = '/opt/gab/footage/process_one.py'

def load_json(path, default):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default

def main():
    queue     = load_json(QUEUE_FILE, [])
    done_list = load_json(DONE_FILE, [])
    done_ids  = {e['id'] for e in done_list}

    clip = next((c for c in queue if c['id'] not in done_ids), None)
    if not clip:
        print("QUEUE_EMPTY: no more clips to process")
        sys.exit(0)

    print(f">> Next: {clip['name']} ({clip['id']})", flush=True)

    result = subprocess.run(
        ['python3', SCRIPT, clip['id'], clip['name'], '--channel', 'gab'],
        capture_output=True, text=True,
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    title, yt_url = '', ''
    for line in result.stdout.splitlines():
        if 'Title:' in line:
            title = line.split('Title:')[-1].strip()
        if 'YouTube:' in line:
            yt_url = line.split('YouTube:')[-1].strip()

    done_list.append({'id': clip['id'], 'name': clip['name'],
                      'title': title, 'youtube_url': yt_url})
    Path(DONE_FILE).write_text(json.dumps(done_list, indent=2))

    remaining = len(queue) - len(done_list)
    print(f"\nRESULT: {title} | {yt_url}")
    print(f"REMAINING: {remaining} clips left in queue")

if __name__ == '__main__':
    main()
