"""
db.py -- SQLite database for the gab-ae pipeline.

Stored on the NAS (Z:\\gab-ae.db) so both the encoding computer and
the streaming computer share the same state.

Tables:
  sessions -- one row per shooting session, tracks both pipelines + YouTube
"""

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(r"Z:\gab-ae.db")

# VOD pipeline statuses
VOD_PENDING   = 'pending'
VOD_STITCHING = 'stitching'
VOD_MIXING    = 'mixing'
VOD_ENCODED   = 'encoded'    # file ready, not yet uploaded
VOD_UPLOADED  = 'uploaded'
VOD_ERROR     = 'error'

# Stream pipeline statuses
STREAM_PENDING  = 'pending'
STREAM_ENCODING = 'encoding'
STREAM_READY    = 'ready'
STREAM_ERROR    = 'error'


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              TEXT PRIMARY KEY,
                folder          TEXT,
                folder_name     TEXT,
                location        TEXT,
                date            TEXT,
                date_label      TEXT,
                file_count      INTEGER,
                total_bytes     INTEGER,
                files           TEXT,       -- JSON array

                vod_status      TEXT NOT NULL DEFAULT 'pending',
                vod_file        TEXT,       -- path to finished VOD mp4
                vod_error       TEXT,
                vod_ts_done     TEXT,

                stream_status   TEXT NOT NULL DEFAULT 'pending',
                stream_folder   TEXT,       -- path to Z:\\gab-ae-sessions\\<name>
                stream_error    TEXT,
                stream_ts_done  TEXT,

                youtube_url     TEXT,
                youtube_id      TEXT,
                youtube_ts      TEXT,       -- when uploaded

                ts_found        TEXT        -- when first scanned
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vod_status    ON sessions(vod_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stream_status ON sessions(stream_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date          ON sessions(date)")


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


# ── Session getters ────────────────────────────────────────────────────────────

def get_session(sid):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()


def get_sessions(vod_status=None, stream_status=None, order_by='date'):
    sql = "SELECT * FROM sessions WHERE 1=1"
    params = []
    if vod_status:
        if isinstance(vod_status, (list, tuple)):
            sql += f" AND vod_status IN ({','.join('?'*len(vod_status))})"
            params += list(vod_status)
        else:
            sql += " AND vod_status=?"; params.append(vod_status)
    if stream_status:
        if isinstance(stream_status, (list, tuple)):
            sql += f" AND stream_status IN ({','.join('?'*len(stream_status))})"
            params += list(stream_status)
        else:
            sql += " AND stream_status=?"; params.append(stream_status)
    sql += f" ORDER BY {order_by}"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def upsert_session(sid, **fields):
    """Insert or update a session row with the given fields."""
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
        if existing:
            sets = ', '.join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE sessions SET {sets} WHERE id=?",
                         list(fields.values()) + [sid])
        else:
            fields['id'] = sid
            cols = ', '.join(fields.keys())
            vals = ', '.join('?' * len(fields))
            conn.execute(f"INSERT INTO sessions ({cols}) VALUES ({vals})",
                         list(fields.values()))


# ── VOD helpers ───────────────────────────────────────────────────────────────

def vod_set_status(sid, status, error=None, vod_file=None):
    fields = {'vod_status': status}
    if error is not None:   fields['vod_error'] = error
    if vod_file is not None: fields['vod_file'] = vod_file
    if status in (VOD_ENCODED, VOD_UPLOADED): fields['vod_ts_done'] = ts()
    upsert_session(sid, **fields)


def vod_set_uploaded(sid, youtube_url, youtube_id):
    upsert_session(sid,
        vod_status=VOD_UPLOADED,
        youtube_url=youtube_url,
        youtube_id=youtube_id,
        youtube_ts=ts(),
        vod_ts_done=ts(),
    )


# ── Stream helpers ─────────────────────────────────────────────────────────────

def stream_set_status(sid, status, stream_folder=None, error=None):
    fields = {'stream_status': status}
    if stream_folder is not None: fields['stream_folder'] = stream_folder
    if error is not None:         fields['stream_error'] = error
    if status == STREAM_READY:    fields['stream_ts_done'] = ts()
    upsert_session(sid, **fields)


# ── Files list ────────────────────────────────────────────────────────────────

def get_files(sid):
    row = get_session(sid)
    if not row or not row['files']:
        return []
    return json.loads(row['files'])
