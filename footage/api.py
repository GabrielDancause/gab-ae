#!/usr/bin/env python3
"""
Footage library API — runs on VPS alongside the pipeline.
Serves library data from library.db for the gab.ae/library page.

Run: uvicorn footage.api:app --host 0.0.0.0 --port 8765
"""

import json
import sqlite3
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

DB_FILE = Path(__file__).parent / "library.db"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/library")
def library():
    conn = get_conn()

    sessions = conn.execute("""
        SELECT
            s.id, s.device, s.started_at, s.ended_at, s.clip_count,
            s.total_duration_seconds, s.has_ali, s.activity, s.time_of_day,
            s.processed_at,
            COUNT(c.id) as tagged_clips,
            SUM(CASE WHEN c.short_drive_id IS NOT NULL THEN 1 ELSE 0 END) as shorts_count
        FROM sessions s
        LEFT JOIN clips c ON c.session_id = s.id
        GROUP BY s.id
        ORDER BY s.started_at DESC
    """).fetchall()

    result = []
    for s in sessions:
        s = dict(s)

        clips = conn.execute("""
            SELECT
                id, filename, device, recorded_at, duration_seconds,
                has_ali, ai_tags, short_drive_id, short_score, short_reason,
                short_start_seconds, short_end_seconds, drive_file_id, youtube_url
            FROM clips
            WHERE session_id = ?
            ORDER BY recorded_at
        """, (s["id"],)).fetchall()

        s["clips"] = []
        for c in clips:
            c = dict(c)
            c["ai_tags"] = json.loads(c["ai_tags"]) if c.get("ai_tags") else []
            s["clips"].append(c)

        result.append(s)

    conn.close()
    return {"sessions": result}


@app.get("/library/stats")
def stats():
    conn = get_conn()
    total_clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    processed = conn.execute("SELECT COUNT(*) FROM sessions WHERE processed_at IS NOT NULL").fetchone()[0]
    total_shorts = conn.execute("SELECT COUNT(*) FROM clips WHERE short_drive_id IS NOT NULL").fetchone()[0]
    has_ali = conn.execute("SELECT COUNT(*) FROM clips WHERE has_ali = 1").fetchone()[0]
    conn.close()
    return {
        "total_clips": total_clips,
        "total_sessions": total_sessions,
        "processed_sessions": processed,
        "total_shorts": total_shorts,
        "clips_with_ali": has_ali,
    }
