#!/usr/bin/env python3
"""
One-shot repair: generate clickbait AI titles for the 14 pending Paris shorts
that currently have the placeholder title 'phone glasses and action cam in Paris 🎬'.
"""

import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path

from openai import OpenAI

ENV_FILE    = '/opt/gab/.env'
READY_Q     = '/opt/gab/footage/ready_queue.json'
LOCATION    = 'Paris'
MODELS      = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]


def load_env():
    env = {}
    for line in Path(ENV_FILE).read_text().splitlines():
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def sample_frames(video_path, n=3):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
        capture_output=True, text=True)
    try:
        dur = float(r.stdout.strip())
    except ValueError:
        return []
    frames = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        r = subprocess.run(
            ['ffmpeg', '-ss', str(t), '-i', video_path, '-frames:v', '1',
             '-f', 'image2', '-vcodec', 'mjpeg', 'pipe:1'],
            capture_output=True)
        if r.returncode == 0 and r.stdout:
            frames.append(base64.b64encode(r.stdout).decode())
    return frames


def generate_title(video_path, api_key):
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=api_key)
    frames = sample_frames(video_path)
    if not frames:
        return f"You won't believe this in {LOCATION} 😱", f"Shot in {LOCATION}."

    prompt = (f"You're writing a YouTube Shorts title for a travel clip shot in {LOCATION}.\n"
              f"I show you {len(frames)} frames from the clip.\n"
              f"Rules: reaction/curiosity-gap style (POV: / Nobody told me / Wait... WHAT / "
              f"This is WILD / You won't believe), max 80 chars, 1 emoji, CAPS on 1 key word.\n"
              f"NEVER invent specific events, people, or stories that may not have happened. "
              f"Describe only what is visually present or use a generic reaction hook.\n"
              f"No hashtags. Also write one punchy sentence for the description.\n"
              f'Respond ONLY with JSON: {{"title":"...","description":"..."}}')

    content = [{"type": "text", "text": prompt}]
    for i, b64 in enumerate(frames):
        content += [{"type": "text", "text": f"Frame {i+1}:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]

    for model in MODELS:
        for attempt in range(3):
            try:
                label = f"{model}" + (f" attempt {attempt+1}" if attempt else "")
                print(f"    [{label}]", end=' ', flush=True)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.7,
                )
                text = resp.choices[0].message.content.strip()
                m = re.search(r'\{[\s\S]*\}', text)
                if not m:
                    raise ValueError("no JSON")
                data = json.loads(m.group(0))
                print(f"→ {data['title']}")
                return data['title'], data.get('description', f'Shot in {LOCATION}.')
            except Exception as e:
                print(f"failed: {str(e)[:60]}")
                time.sleep(8)

    return f"You won't believe this in {LOCATION} 😱", f"Shot in {LOCATION}."


def main():
    env = load_env()
    api_key = env.get('OPENROUTER_API_KEY', '')
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not found in .env")
        return

    q = json.loads(Path(READY_Q).read_text())
    updated = 0
    for e in q:
        if e.get('uploaded'):
            continue
        lf = e.get('local_file', '')
        if not Path(lf).exists():
            continue
        print(f"\n{Path(lf).name}")
        title, desc = generate_title(lf, api_key)
        e['title'] = title
        e['description'] = f'{desc}\n\n#shorts #paris #travel #pov'
        updated += 1

    Path(READY_Q).write_text(json.dumps(q, indent=2))
    print(f"\nUpdated {updated} shorts titles.")


if __name__ == '__main__':
    main()
