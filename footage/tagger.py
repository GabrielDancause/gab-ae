#!/usr/bin/env python3
"""
AI tagging module — analyzes individual raw clips via OpenRouter.

tag_clip(): scores a single clip, picks best short window (start/end time),
            returns scene metadata (has_ali, tags, activity, time_of_day).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from openai import OpenAI


FRAMES_PER_CLIP = 4
REQUEST_DELAY_SEC = 5

# Free vision models, tried in order on 429
MODELS = [
    "google/gemini-2.5-flash-preview:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "qwen/qwen-2-vl-7b-instruct:free",
]

CLIP_PROMPT = """\
You are selecting the best moment from a travel/adventure video clip for a social media short \
(YouTube Shorts, TikTok, Instagram Reels).

I first show you a reference photo of Ali.
Then I show you {n} frames sampled from a {duration_str} clip, each labeled with its timestamp.

The clip has NO AUDIO — visual impact is everything.
Pick the most compelling continuous window to use as a short.

Respond ONLY with valid JSON — no explanation, no markdown:
{{
  "score": 1-10,
  "start_time": <float, seconds>,
  "end_time": <float, seconds>,
  "reason": "one sentence",
  "has_ali": true or false,
  "tags": ["tag1", "tag2"],
  "activity": "brief description of what is happening",
  "time_of_day": "day, night, or golden_hour"
}}

Scoring guide:
  8-10 = stunning view, clear action, strong visual hook — post immediately
  5-7  = decent but not remarkable
  1-4  = nothing interesting (camera adjusting, walking transition, lens cap, etc.)

Rules:
- end_time - start_time must be between 15 and 90 seconds
- start_time >= 0, end_time <= {duration_sec:.1f}
- has_ali = true only if the person in the reference photo is clearly visible
- tags: describe the scene (location, landmarks, weather, mood, shot type). Max 10 tags.\
"""


def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return key


def get_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return 0.0
    return float(json.loads(result.stdout).get("format", {}).get("duration", 0))


def extract_frames_at(video_path: str, timestamps: list[float], out_dir: str) -> list[tuple[float, str]]:
    frames = []
    for i, ts in enumerate(timestamps):
        path = os.path.join(out_dir, f"frame_{i:02d}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path, "-vframes", "1", "-q:v", "4", path],
            capture_output=True,
        )
        if os.path.exists(path) and os.path.getsize(path) > 0:
            frames.append((ts, path))
    return frames


def img_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def tag_clip(clip_path: str, reference_photo_path: str) -> dict:
    """
    Analyze a single raw clip via OpenRouter.
    Returns: {score, start_time, end_time, reason, has_ali, tags, activity, time_of_day}
    """
    default = {
        "score": 0, "start_time": 0.0, "end_time": 0.0, "reason": "tagging failed",
        "has_ali": None, "tags": [], "activity": "", "time_of_day": "",
    }

    duration = get_duration(clip_path)
    if duration < 5:
        default["reason"] = "clip too short"
        return default

    interval = duration / (FRAMES_PER_CLIP + 1)
    timestamps = [interval * (i + 1) for i in range(FRAMES_PER_CLIP)]
    duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"

    prompt = CLIP_PROMPT.format(
        n=FRAMES_PER_CLIP,
        duration_str=duration_str,
        duration_sec=duration,
    )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=load_api_key(),
    )

    with tempfile.TemporaryDirectory() as tmp:
        frames = extract_frames_at(clip_path, timestamps, tmp)
        if not frames:
            default["reason"] = "frame extraction failed"
            return default

        # Build message content: prompt + reference photo + labeled frames
        content = [{"type": "text", "text": prompt}]
        content.append({"type": "text", "text": "Reference photo of Ali:"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_to_b64(reference_photo_path)}"},
        })
        for ts, path in frames:
            m, s = int(ts // 60), int(ts % 60)
            content.append({"type": "text", "text": f"Frame at {m}:{s:02d}:"})
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_to_b64(path)}"},
            })

        for model in MODELS:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.1,
                )
                text = response.choices[0].message.content.strip()
                text = text.strip("```json").strip("```").strip()
                data = json.loads(text)

                data["start_time"] = max(0.0, min(float(data.get("start_time", 0)), duration))
                data["end_time"] = max(0.0, min(float(data.get("end_time", duration)), duration))
                if data["end_time"] <= data["start_time"]:
                    data["end_time"] = min(data["start_time"] + 60, duration)

                return data

            except Exception as e:
                msg = str(e)
                if "429" in msg:
                    print(f"  {model} 429 — trying next model...")
                    time.sleep(2)
                    continue
                default["reason"] = f"{model}: {msg}"
                return default

        default["reason"] = "all models rate limited"
        return default
