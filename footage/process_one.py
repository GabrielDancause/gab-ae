#!/usr/bin/env python3
"""
One-shot: Download square DJI clip → center crop → AI title → YouTube unlisted.
Usage: python3 process_one.py <drive_file_id> <filename> [--slowmo] [--channel gab]
  --slowmo       Use full clip slowed 2× (for 60fps panning/travel gesture shots)
  --channel gab  Upload to GAB adventures channel (default: Ali Imperiale channel)
"""

import base64
import io
import json
import random
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
YT_TOKEN       = '/opt/gab/shorts-uploader/token.json'        # Ali Imperiale channel
YT_TOKEN_GAB   = '/opt/gab/gab-adventures/token.json'         # GAB adventures channel
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

def yt_service(channel='ali'):
    token = YT_TOKEN_GAB if channel == 'gab' else YT_TOKEN
    creds = Credentials.from_authorized_user_file(token)
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

def get_fps(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams',
         '-select_streams', 'v:0', path],
        capture_output=True, text=True
    )
    s = json.loads(r.stdout).get('streams', [{}])[0]
    num, den = s.get('r_frame_rate', '0/1').split('/')
    return float(num) / float(den) if float(den) else 0

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

def analyze_clip(video_path, env, slowmo=False, has_ali=None, question_style='creator'):
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

        ali_hint = ''
        if has_ali is True:
            ali_hint = '\nIMPORTANT: A woman named Ali IS confirmed in this clip. Lead the title with her action (e.g. "Ali Cycling in Paris", "Ali Exploring Montmartre").'
        elif has_ali is False:
            ali_hint = '\nIMPORTANT: Ali is NOT in this clip. Title should focus entirely on the scene, action, or subject visible.'

        if question_style == 'clickbait':
            title_instruction = f"""
The TITLE must be a clickbait-style hook — emotional, surprising, urgent. Makes the viewer NEED to watch.
It does NOT need to be a question. Use CAPS on 1-2 key words for emphasis. Focus on intrigue, FOMO, surprise.
Be specific to what you actually see. Do NOT invent things not in the frame.

The CAPS word must amplify the hook — pick something that creates surprise or FOMO about what's visible.
NEVER capitalize a word that describes a mood you invented (e.g. SILENCE, BEAUTY, MAGIC) — only cap something that makes the specific scene more dramatic.

Good examples (clickbait with CAPS emphasis):
- "NOBODY told me Paris looked like this 😱"
- "This spot in Paris BROKE me 🥹"
- "I almost MISSED this 😮"
- "This is WHY I keep coming back to Paris 🔥"
- "WAIT... is this really Paris? 🤯"
- "The side of Paris NOBODY shows you 👀"
- "I can't believe I FILMED this 😭"
- "POV: stumbling onto something MAGICAL in Paris ✨"

Bad CAPS (invented mood, not scene-specific): "Parisian SILENCE", "Pure BEAUTY", "Total PEACE"

Rules: max 60 chars — 1-2 words in CAPS — 1 emoji ok — NO hashtags — NEVER invent what's in the frame.{ali_hint}"""
        elif question_style == 'trivia':
            title_instruction = f"""
The TITLE must be a trivia question with a real, knowable answer based ONLY on what you can clearly see in the frames.
WARNING: Only ask about landmarks or places you can identify with near-certainty from the visuals. If unsure, ask a general question instead.
NEVER invent or assume specific names — a wrong fact is worse than a vague question.

Good examples (trivia-style, only when clearly visible):
- "Which famous cemetery is this in Paris? 🏛️"
- "Can you name this Paris bridge? 🌉"
- "Which arrondissement is this? 🗺️"

Rules: must end with ? — only ask facts visible in frame — max 60 chars — 1 emoji ok — NO hashtags.{ali_hint}"""
        elif question_style == 'audience':
            title_instruction = f"""
The TITLE must be a curious question directed at the audience — make them want to answer in the comments.
Ask about what they see: location, landmark, activity, what happens next.
Be specific to what you actually see in the frames.

Good examples (audience-directed):
- "Where in Paris do you think this is? 🗺️"
- "Can you name this Paris landmark? 🗼"
- "What do you think is happening here? 👀"
- "Which arrondissement is this? 🤔"
- "Have you ever been to this spot? ✨"
- "Spot the hidden detail in this shot 👇"

Rules: must end with ? — max 60 chars — 1 emoji ok — NO hashtags — NEVER invent place names.{ali_hint}"""
        else:  # creator (default)
            title_instruction = f"""
The TITLE must be a curious question directed at the viewer, from the creator's point of view (first person).
Frame it as if the person who filmed this is asking YOU (the viewer) to guess something about their experience.
Be specific to what you actually see in the frames.

Good examples (first-person POV, directed at viewer):
- "Can you guess where I was? 🗺️"
- "Do you know this Paris spot? 👀"
- "Would you have stopped here? ✨"
- "Can you name this neighborhood? 🗼"
- "Have you ever been here? 🌿"
- "Do you recognize where I filmed this? 🎬"
- "Can you spot what caught my eye? 👇"

Rules: must end with ? — first-person or second-person framing — max 60 chars — 1 emoji ok — NO hashtags — NEVER invent place names.{ali_hint}"""

        if slowmo:
            slowed_dur = duration * 2
            clip_desc = f"""You are titling a slow-motion travel short for YouTube.
I show you frames from a {duration:.1f}s clip filmed at 60fps with a DJI Action Cam 6 (square 3840x3840) in Paris, France.
This clip will be slowed down 2× and become {slowed_dur:.0f}s — smooth, cinematic slow-motion.

Available background music tracks:
{music_list}

Respond ONLY with valid JSON, no explanation:
{{
  "score": 1-10,
  "music": "<filename that best fits — pick something cinematic/ambient for slow-mo>",
  "title": {title_instruction},
  "reason": "one sentence on why this is a great slow-mo shot",
  "has_ali": true or false,
  "tags": ["tag1","tag2"],
  "activity": "brief description of the specific subject and action"
}}

Scoring: 8-10=stunning panning/gesture with great background, 5-7=decent, 1-4=nothing interesting"""
        else:
            clip_desc = f"""You are selecting the best moment from a travel/adventure video clip for a YouTube Short.
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
  "title": {title_instruction},
  "reason": "one sentence describing the best visual moment in the window",
  "has_ali": true or false,
  "tags": ["tag1","tag2"],
  "activity": "brief description of what is happening"
}}

Constraints: start_time >= 0, end_time <= {duration:.1f}, end_time - start_time >= 30
Scoring: 8-10=stunning/clear action/strong hook, 5-7=decent, 1-4=boring transition"""

        content = [{"type": "text", "text": clip_desc}]

        if Path(REFERENCE_PHOTO).exists():
            content.append({"type": "text", "text": "Reference photo of Ali:"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64(REFERENCE_PHOTO)}"}})

        for ts, p in frames:
            m, s = int(ts // 60), int(ts % 60)
            content.append({"type": "text", "text": f"Frame at {m}:{s:02d}:"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64(p)}"}})

        import re
        for model in OPENROUTER_MODELS:
            max_retries = 4 if model == 'openrouter/free' else 2
            for attempt in range(max_retries):
                try:
                    print(f"  Trying model: {model}" + (f" (attempt {attempt+1})" if attempt else ""))
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": content}],
                        temperature=0.2,
                    )
                    text = resp.choices[0].message.content.strip()
                    json_match = re.search(r'\{[\s\S]*\}', text)
                    if not json_match:
                        raise ValueError("no JSON in response")
                    data = json.loads(json_match.group(0))
                    if slowmo:
                        data['start_time'] = 0.0
                        data['end_time']   = duration
                    else:
                        data['start_time'] = max(0.0, min(float(data.get('start_time', 0)), duration))
                        data['end_time']   = max(0.0, min(float(data.get('end_time', 60)), duration))
                        window = data['end_time'] - data['start_time']
                        if window < 30:
                            mid = (data['start_time'] + data['end_time']) / 2 if window > 0 else duration / 2
                            data['start_time'] = max(0.0, mid - 15)
                            data['end_time']   = min(duration, data['start_time'] + 30)
                            print(f"  Window too short ({window:.1f}s) — extended to {data['start_time']:.1f}s→{data['end_time']:.1f}s")
                    print(f"  Score: {data.get('score')} | Music: {data.get('music')} | Title: {data.get('title')}")
                    return data
                except Exception as e:
                    err = str(e)
                    is_rate_limit = "429" in err
                    delay = 12 if is_rate_limit else 8
                    print(f"  {model} failed (attempt {attempt+1}): {err[:120]}")
                    if attempt + 1 < max_retries:
                        print(f"  Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        break  # try next model
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

def cut_short_slowmo(input_path, output_path):
    """Slow down 60fps clip 2× via setpts=2.0*PTS, then center crop to 1080x1920."""
    duration = get_duration(input_path)
    if duration < 2:
        return False

    w, h = get_dimensions(input_path)
    is_square = abs(w - h) < 10
    slowed = duration * 2
    print(f"  Dimensions: {w}x{h} @ 60fps → {slowed:.0f}s at 50% speed {'(center crop)' if is_square else '(blur bg)'}")

    if is_square:
        vf = 'setpts=2.0*PTS,crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920'
        cmd = ['ffmpeg', '-y', '-i', input_path, '-an',
               '-vf', vf, '-r', '30',
               '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
               '-maxrate', '25M', '-bufsize', '50M', output_path]
    else:
        fc = '[0:v]setpts=2.0*PTS,scale=1080:1920,boxblur=20:5[bg];[0:v]setpts=2.0*PTS,scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2'
        cmd = ['ffmpeg', '-y', '-i', input_path, '-an',
               '-filter_complex', fc, '-r', '30',
               '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
               '-maxrate', '25M', '-bufsize', '50M', output_path]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg error:", result.stderr[-500:])
        return False
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  Slow-mo: {output_path} ({size_mb:.1f}MB, {slowed:.0f}s)")
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

    # Pick a random start offset (leave at least vid_dur + 10s before end)
    music_dur = get_duration(music_path)
    max_offset = max(0, music_dur - vid_dur - 10)
    offset = random.uniform(0, max_offset) if max_offset > 0 else 0

    result = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-ss', str(offset), '-stream_loop', '-1', '-i', music_path,
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

def build_description(ai_data, music_filename):
    """Build YouTube description with tags and music attribution."""
    parts = []
    activity = ai_data.get('activity', '')
    if activity:
        parts.append(activity)
    tags = ai_data.get('tags', [])
    if tags:
        parts.append(' '.join(f'#{t.replace(" ", "")}' for t in tags))
    # Music attribution
    library = json.loads(Path(MUSIC_LIBRARY).read_text()) if Path(MUSIC_LIBRARY).exists() else []
    track = next((t for t in library if t['filename'] == music_filename), None)
    if track and track.get('attribution'):
        parts.append(track['attribution'])
    return '\n\n'.join(parts)

def upload_to_youtube(video_path, title, description='', channel='ali'):
    svc = yt_service(channel)
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['shorts', 'paris', 'travel', 'france'],
            'categoryId': '19',  # Travel & Events
        },
        'status': {'privacyStatus': 'public'},
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
    args     = sys.argv[1:]
    slowmo   = '--slowmo' in args
    slowmo_forced = slowmo  # user explicitly passed --slowmo
    args     = [a for a in args if a != '--slowmo']
    # --question clickbait|creator|audience|trivia  (default: clickbait)
    question_style = 'clickbait'
    if '--question' in args:
        idx = args.index('--question')
        question_style = args[idx + 1] if idx + 1 < len(args) else 'creator'
        args = args[:idx] + args[idx+2:]
    # --has-ali yes/no  → skip interactive prompt (for autopilot)
    has_ali_override = None
    if '--has-ali' in args:
        idx = args.index('--has-ali')
        val = args[idx + 1].lower() if idx + 1 < len(args) else ''
        has_ali_override = val in ('yes', 'true', '1')
        args = args[:idx] + args[idx+2:]
    channel  = 'gab' if '--channel' in args and args[args.index('--channel') + 1] == 'gab' else 'ali'
    if '--channel' in args:
        idx  = args.index('--channel')
        args = args[:idx] + args[idx+2:]
    file_id  = args[0] if len(args) > 0 else '1wD1w2Zfw6rLyKXU5lDuLCqmLsavOiHFE'
    filename = args[1] if len(args) > 1 else 'DJI_20260430154051_0294_D.MP4'
    location = args[2] if len(args) > 2 else None

    env = load_env()
    os.makedirs(WORKDIR, exist_ok=True)

    raw_path    = os.path.join(WORKDIR, filename)
    short_path  = os.path.join(WORKDIR, 'short_'  + filename)
    audio_path  = os.path.join(WORKDIR, 'audio_'  + filename)
    final_path  = os.path.join(WORKDIR, 'final_'  + filename)

    # 1. Download
    print(f"\n[1/6] Downloading {filename}{'  [SLOW-MO MODE]' if slowmo else ''}...")
    drive_svc = drive_service()
    if not os.path.exists(raw_path):
        download_from_drive(drive_svc, file_id, raw_path)
    else:
        print(f"  Already exists, skipping download")

    # 1b. Auto-detect slowmo: 60fps + short clip → 2× slowdown
    if not slowmo_forced:
        fps  = get_fps(raw_path)
        dur  = get_duration(raw_path)
        if fps >= 50 and dur <= 20:
            slowmo = True
            print(f"  Auto-slowmo: {fps:.0f}fps, {dur:.1f}s → will slow 2× to {dur*2:.0f}s")
        else:
            print(f"  Mode: regular speed ({fps:.0f}fps, {dur:.1f}s)")

    # 1c. Ali check — extract mid-frame, ask user if Ali is in the shot
    has_ali = has_ali_override
    check_frame = os.path.join(WORKDIR, 'check_ali_' + filename + '.jpg')
    dur_check = get_duration(raw_path)
    subprocess.run(
        ['ffmpeg', '-y', '-ss', str(dur_check / 2), '-i', raw_path,
         '-vframes', '1', '-q:v', '2', check_frame],
        capture_output=True
    )
    if has_ali is None and os.path.exists(check_frame):
        print(f"\n  Preview frame saved → {check_frame}")
        print(f"  Is Ali in this clip? [yes/no/skip]: ", end='', flush=True)
        try:
            ans = input().strip().lower()
            if ans in ('yes', 'y'):
                has_ali = True
            elif ans in ('no', 'n'):
                has_ali = False
            # 'skip' or anything else → leave as None (let AI decide)
        except EOFError:
            pass  # non-interactive / piped — let AI decide

    if has_ali is True:
        print(f"  ✓ Ali confirmed — title will feature her name/presence")
    elif has_ali is False:
        print(f"  ✓ No Ali — title will focus on scene/action")
    else:
        print(f"  ? Ali presence unknown — AI will guess from reference photo")

    # 2. Analyze
    print(f"\n[2/6] Analyzing clip with AI...")
    ai = analyze_clip(raw_path, env, slowmo=slowmo, has_ali=has_ali, question_style=question_style)
    if not ai:
        print("  AI analysis failed, using defaults")
        dur = get_duration(raw_path)
        ai = {'start_time': 0, 'end_time': dur, 'title': 'Paris slow-motion 🎬' if slowmo else 'Paris adventure 🗼',
              'score': 5, 'activity': 'unknown', 'music': 'shipping_lanes.mp3'}

    title = ai.get('title', 'Paris short')
    music = ai.get('music', 'shipping_lanes.mp3')
    if not slowmo:
        print(f"  Window: {ai['start_time']:.1f}s → {ai['end_time']:.1f}s")
    print(f"  Title:  {title}")
    print(f"  Music:  {music}")

    # 3. Cut short (or slow-mo)
    if slowmo:
        print(f"\n[3/6] Applying 2× slow-motion + center crop...")
        ok = cut_short_slowmo(raw_path, short_path)
    else:
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
    ch_label = 'GAB adventures' if channel == 'gab' else 'Ali Imperiale'
    description = build_description(ai, music)
    print(f"\n[6/6] Uploading to YouTube ({ch_label})...")
    print(f"  Description: {description[:80]}..." if description else "  No description")
    yt_id = upload_to_youtube(final_path, title, description=description, channel=channel)
    yt_url = f"https://www.youtube.com/watch?v={yt_id}"

    print(f"\n✅ Done!")
    print(f"   Channel: {ch_label}")
    print(f"   Title:   {title}")
    print(f"   YouTube: {yt_url}")
    print(f"   Score:   {ai.get('score')}")
    print(f"   Reason:  {ai.get('reason')}")

if __name__ == '__main__':
    main()
