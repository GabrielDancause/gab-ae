#!/usr/bin/env python3
"""
One-shot: Download square DJI clip → center crop → AI title → YouTube unlisted.
Usage: python3 process_one.py <drive_file_id> <filename>
"""

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials

# ── Config ──────────────────────────────────────────────────────────────────
DRIVE_TOKEN    = '/opt/gab/footage/token.json'
YT_CREDS       = '/opt/gab/shorts-uploader/credentials.json'
YT_TOKEN       = '/opt/gab/shorts-uploader/token.json'
SHORTS_FOLDER  = '1NIMuljumdURuvWJa_c7YCPFY-wAIMb_f'
REFERENCE_PHOTO = '/opt/gab/footage/reference_photo.jpg'
ENV_FILE       = '/opt/gab/.env'
WORKDIR        = '/tmp/oneoff'
MUSIC_LIBRARY  = '/opt/gab/music/library.json'

OPENROUTER_MODELS = [
    "openrouter/free",           # OpenRouter's auto-router across all free vision models
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]

# ── Helpers ─────────────────────────────────────────────────────────────────
def load_env():
    env = {}
    if Path(ENV_FILE).exists():
        for line in Path(ENV_FILE).read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def drive_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds)

def yt_service():
    creds = Credentials.from_authorized_user_file(YT_TOKEN)
    return build('youtube', 'v3', credentials=creds)

def download_from_drive(svc, file_id, dest_path):
    print(f"  Downloading {file_id} → {dest_path}")
    request = svc.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request, chunksize=32*1024*1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"    {int(status.progress() * 100)}%", end='\r')
    print()

def get_duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
        capture_output=True, text=True
    )
    return float(json.loads(r.stdout).get('format', {}).get('duration', 0))

def extract_frames(video_path, timestamps, out_dir):
    frames = []
    for i, ts in enumerate(timestamps):
        p = os.path.join(out_dir, f'frame_{i:02d}.jpg')
        subprocess.run(
            ['ffmpeg', '-y', '-ss', str(ts), '-i', video_path,
             '-vframes', '1', '-q:v', '4', p],
            capture_output=True
        )
        if os.path.exists(p) and os.path.getsize(p) > 0:
            frames.append((ts, p))
    return frames

def img_b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()

def analyze_clip(video_path, env):
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=env['OPENROUTER_API_KEY'])

    duration = get_duration(video_path)
    timestamps = [duration / 5 * i for i in range(1, 5)]

    with tempfile.TemporaryDirectory() as tmp:
        frames = extract_frames(video_path, timestamps, tmp)
        if not frames:
            return None

        music_lib = json.loads(Path(MUSIC_LIBRARY).read_text()) if Path(MUSIC_LIBRARY).exists() else []
        music_list = '\n'.join(f'- {t["filename"]}: {t["description"]} (mood: {t["mood"]}, energy: {t["energy"]})' for t in music_lib)

        content = [{
            "type": "text",
            "text": f"""You are selecting the best moment from a travel/adventure video clip for a YouTube Short.
I show you 4 frames from a {int(duration)}s clip filmed with a DJI Action Cam 6 (square 3840x3840) in Paris, France.

CRITICAL RULE: end_time - start_time MUST be between 30 and 60 seconds. Never less than 30.
If the clip is shorter than 30s, use the full clip.

Available background music tracks (pick the one that best fits the mood of this clip):
{music_list}

Respond ONLY with valid JSON, no explanation:
{{
  "score": 1-10,
  "start_time": <float seconds>,
  "end_time": <float seconds — must be start_time + at least 30>,
  "music": "<filename from the list above that best fits this clip>",
  "title": "SEO-optimized YouTube Shorts title: specific, vivid, searchable. Use keywords people search (city name, activity, landmark). Max 60 chars, 1 emoji ok, NO hashtags.",
  "reason": "one sentence describing the best visual moment in the window",
  "has_ali": true or false,
  "tags": ["tag1","tag2"],
  "activity": "brief description of what is happening"
}}

Constraints: start_time >= 0, end_time <= {duration:.1f}, end_time - start_time >= 30
Scoring: 8-10=stunning/clear action/strong hook, 5-7=decent, 1-4=boring transition"""
        }]

        if Path(REFERENCE_PHOTO).exists():
            content.append({"type": "text", "text": "Reference photo of Ali:"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64(REFERENCE_PHOTO)}"}})

        for ts, p in frames:
            m, s = int(ts // 60), int(ts % 60)
            content.append({"type": "text", "text": f"Frame at {m}:{s:02d}:"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64(p)}"}})

        for model in OPENROUTER_MODELS:
            try:
                print(f"  Trying model: {model}")
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.2,
                )
                text = resp.choices[0].message.content.strip()
                # Extract JSON from markdown fences or surrounding prose
                import re
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    text = json_match.group(0)
                data = json.loads(text)
                data['start_time'] = max(0.0, min(float(data.get('start_time', 0)), duration))
                data['end_time']   = max(0.0, min(float(data.get('end_time', 60)), duration))
                window = data['end_time'] - data['start_time']
                if window < 30:
                    # AI returned a short window — extend to 30s centered on the suggested start
                    mid = (data['start_time'] + data['end_time']) / 2 if window > 0 else duration / 2
                    data['start_time'] = max(0.0, mid - 15)
                    data['end_time']   = min(duration, data['start_time'] + 30)
                    print(f"  Window too short ({window:.1f}s) — extended to {data['start_time']:.1f}s→{data['end_time']:.1f}s")
                print(f"  Score: {data.get('score')} | Music: {data.get('music')} | Title: {data.get('title')}")
                return data
            except Exception as e:
                print(f"  {model} failed: {e}")
                if "429" in str(e):
                    time.sleep(3)
                    continue
        return None

def get_dimensions(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams',
         '-select_streams', 'v:0', path],
        capture_output=True, text=True
    )
    stream = json.loads(r.stdout).get('streams', [{}])[0]
    return stream.get('width', 0), stream.get('height', 0)

def cut_short(input_path, output_path, start, end):
    duration = end - start
    if duration < 5:
        return False

    w, h = get_dimensions(input_path)
    is_square = abs(w - h) < 10
    print(f"  Dimensions: {w}x{h} → {'square → center crop' if is_square else '16:9 → blur background'}")

    if is_square:
        vf = 'crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920'
    else:
        vf = '[0:v]scale=1080:1920,boxblur=20:5[bg];[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2'

    cmd = ['ffmpeg', '-y', '-ss', str(start), '-i', input_path,
           '-t', str(duration), '-an']
    if is_square:
        cmd += ['-vf', vf]
    else:
        cmd += ['-filter_complex', vf]
    cmd += ['-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
            '-maxrate', '25M', '-bufsize', '50M', output_path]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg error:", result.stderr[-500:])
        return False
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  Short: {output_path} ({size_mb:.1f}MB, {duration:.0f}s)")
    return True

FONT_BOLD    = '/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf'
FONT_REGULAR = '/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf'

def write_caption(location, env):
    """Ask AI to write a short travel paragraph about the given location."""
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=env['OPENROUTER_API_KEY'])
    prompt = f"""Write a short travel description for a YouTube Short about {location}.
2-3 sentences max. Vivid, informative, enthusiastic. No hashtags. Plain text only."""
    for model in OPENROUTER_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e):
                time.sleep(3)
                continue
    return f"Exploring {location} — one of Paris's hidden gems."

def burn_text(video_path, location, paragraph, output_path):
    """Render location name + paragraph as a Pillow overlay at the top of the video."""
    # Get video dimensions
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams',
         '-select_streams', 'v:0', video_path],
        capture_output=True, text=True
    )
    stream = json.loads(r.stdout).get('streams', [{}])[0]
    W, H = stream.get('width', 1080), stream.get('height', 1920)

    # Build overlay image with Pillow
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    pad = 40
    text_w = W - pad * 2

    font_title = ImageFont.truetype(FONT_BOLD, 56)
    font_body  = ImageFont.truetype(FONT_REGULAR, 38)

    # Word-wrap the paragraph
    wrapped = textwrap.fill(paragraph, width=32)
    lines = [location, ''] + wrapped.split('\n')

    # Measure total text block height
    line_heights = []
    for i, line in enumerate(lines):
        font = font_title if i == 0 else font_body
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1] + (8 if i > 0 else 12))
    total_h = sum(line_heights) + pad * 2

    # Draw semi-transparent dark background
    draw.rectangle([(0, 0), (W, total_h)], fill=(0, 0, 0, 180))

    # Draw text
    y = pad
    for i, line in enumerate(lines):
        if not line:
            y += 10
            continue
        font = font_title if i == 0 else font_body
        color = (255, 255, 255, 255) if i == 0 else (220, 220, 220, 230)
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill=color)
        y += line_heights[i]

    # Save overlay as PNG, composite onto video with FFmpeg
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        overlay_path = tmp.name
    overlay.save(overlay_path)

    result = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', overlay_path,
        '-filter_complex', '[0:v][1:v]overlay=0:0',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
        '-maxrate', '25M', '-bufsize', '50M',
        '-c:a', 'copy',
        output_path
    ], capture_output=True, text=True)

    os.unlink(overlay_path)

    if result.returncode != 0:
        print("  Text burn error:", result.stderr[-300:])
        return False
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  With text: {size_mb:.1f}MB")
    return True

def mix_audio(video_path, music_filename, output_path):
    """Overlay music track onto silent video, looping/trimming to fit."""
    library = json.loads(Path(MUSIC_LIBRARY).read_text()) if Path(MUSIC_LIBRARY).exists() else []
    track = next((t for t in library if t['filename'] == music_filename), None)
    if not track:
        # Fallback to first track
        track = library[0] if library else None
    if not track:
        print("  No music track found — skipping audio")
        return False

    music_path = track['file']
    print(f"  Mixing: {track['filename']} ({track['mood']})")

    # Get video duration to know how long to loop music
    vid_dur = get_duration(video_path)

    result = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-stream_loop', '-1', '-i', music_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy',
        '-filter:a', 'volume=0.6',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(vid_dur),
        output_path
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print("  Audio mix error:", result.stderr[-300:])
        return False
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  With audio: {size_mb:.1f}MB")
    return True

def upload_to_drive(svc, file_path, title):
    meta = {'name': title, 'parents': [SHORTS_FOLDER]}
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True, chunksize=32*1024*1024)
    f = svc.files().create(body=meta, media_body=media, fields='id').execute()
    return f['id']

def upload_to_youtube(video_path, title, description=''):
    svc = yt_service()
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['shorts', 'paris', 'travel'],
            'categoryId': '19',  # Travel & Events
        },
        'status': {'privacyStatus': 'unlisted'},
    }
    media = MediaFileUpload(video_path, mimetype='video/mp4', resumable=True, chunksize=32*1024*1024)
    request = svc.videos().insert(part='snippet,status', body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload: {int(status.progress() * 100)}%", end='\r')
    print()
    return response['id']

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    file_id  = sys.argv[1] if len(sys.argv) > 1 else '1wD1w2Zfw6rLyKXU5lDuLCqmLsavOiHFE'
    filename = sys.argv[2] if len(sys.argv) > 2 else 'DJI_20260430154051_0294_D.MP4'
    location = sys.argv[3] if len(sys.argv) > 3 else None  # e.g. "Parc Martin Luther King, Paris 17e"

    env = load_env()
    os.makedirs(WORKDIR, exist_ok=True)

    raw_path    = os.path.join(WORKDIR, filename)
    short_path  = os.path.join(WORKDIR, 'short_'  + filename)
    audio_path  = os.path.join(WORKDIR, 'audio_'  + filename)
    final_path  = os.path.join(WORKDIR, 'final_'  + filename)

    # 1. Download
    print(f"\n[1/6] Downloading {filename}...")
    drive_svc = drive_service()
    if not os.path.exists(raw_path):
        download_from_drive(drive_svc, file_id, raw_path)
    else:
        print(f"  Already exists, skipping download")

    # 2. Analyze
    print(f"\n[2/6] Analyzing clip with AI...")
    ai = analyze_clip(raw_path, env)
    if not ai:
        print("  AI analysis failed, using defaults")
        ai = {'start_time': 0, 'end_time': 45, 'title': 'Paris adventure 🗼', 'score': 5,
              'activity': 'unknown', 'music': 'shipping_lanes.mp3'}

    title = ai.get('title', 'Paris short')
    music = ai.get('music', 'shipping_lanes.mp3')
    print(f"  Window: {ai['start_time']:.1f}s → {ai['end_time']:.1f}s")
    print(f"  Title:  {title}")
    print(f"  Music:  {music}")

    # 3. Cut short
    print(f"\n[3/6] Cutting short (center crop)...")
    ok = cut_short(raw_path, short_path, ai['start_time'], ai['end_time'])
    if not ok:
        print("  FFmpeg failed")
        sys.exit(1)

    # 4. Mix audio
    print(f"\n[4/6] Mixing music...")
    ok = mix_audio(short_path, music, audio_path)
    if not ok:
        print("  Audio mix failed — continuing without music")
        audio_path = short_path

    # 5. Burn text caption (only if location provided)
    print(f"\n[5/6] Burning caption...")
    if location:
        print(f"  Writing caption for: {location}")
        paragraph = write_caption(location, env)
        print(f"  Caption: {paragraph[:80]}...")
        ok = burn_text(audio_path, location, paragraph, final_path)
        if not ok:
            print("  Text burn failed — uploading without caption")
            final_path = audio_path
    else:
        print("  No location provided — skipping caption")
        final_path = audio_path

    # 6. Upload to YouTube
    print(f"\n[6/6] Uploading to YouTube...")
    yt_id = upload_to_youtube(final_path, title)
    yt_url = f"https://www.youtube.com/watch?v={yt_id}"

    print(f"\n✅ Done!")
    print(f"   Title:   {title}")
    print(f"   YouTube: {yt_url}")
    print(f"   Score:   {ai.get('score')}")
    print(f"   Reason:  {ai.get('reason')}")

if __name__ == '__main__':
    main()
