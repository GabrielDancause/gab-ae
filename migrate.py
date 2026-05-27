"""
migrate.py -- one-time migration from sessions_state.json to Z:\\gab-ae.db

Run once:
  python migrate.py

Safe to re-run (INSERT OR IGNORE skips existing rows).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

STATE_FILE   = Path(r"C:\gab-ae\sessions_state.json")
SESSIONS_DIR = Path(r"Z:\gab-ae-sessions")

VOD_STATUS_MAP = {
    'pending':   db.VOD_PENDING,
    'stitching': db.VOD_PENDING,    # reset — will restart cleanly
    'mixing':    db.VOD_PENDING,    # reset — will restart cleanly
    'uploading': db.VOD_ENCODED,    # treat as encoded, not uploaded
    'encoded':   db.VOD_ENCODED,
    'done':      db.VOD_UPLOADED,
    'error':     db.VOD_ERROR,
}

def main():
    if not STATE_FILE.exists():
        print(f"State file not found: {STATE_FILE}")
        sys.exit(1)

    print(f"Initialising database at {db.DB_PATH} ...")
    db.init_db()

    state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
    sessions = state.get('sessions', {})
    print(f"Migrating {len(sessions)} sessions ...")

    inserted = updated = skipped = 0

    with db.get_conn() as conn:
        for sid, s in sessions.items():
            existing = conn.execute(
                "SELECT id FROM sessions WHERE id=?", (sid,)
            ).fetchone()

            vod_status = VOD_STATUS_MAP.get(s.get('status', 'pending'), db.VOD_PENDING)
            vod_file   = s.get('output_file') if vod_status in (db.VOD_ENCODED, db.VOD_UPLOADED) else None
            vod_error  = s.get('error')       if vod_status == db.VOD_ERROR else None

            # Check stream readiness from filesystem
            folder_name = s.get('folder_name', '')
            stream_folder = SESSIONS_DIR / folder_name
            playlist = stream_folder / 'playlist.txt'
            if playlist.exists() and playlist.stat().st_size > 0:
                stream_status = db.STREAM_READY
                stream_folder_path = str(stream_folder)
                stream_ts = s.get('ts_done')
            else:
                stream_status = db.STREAM_PENDING
                stream_folder_path = None
                stream_ts = None

            youtube_url = s.get('youtube_url')
            youtube_id  = None
            if youtube_url and 'v=' in youtube_url:
                youtube_id = youtube_url.split('v=')[-1]

            row = (
                sid,
                s.get('folder'),
                folder_name,
                s.get('location'),
                s.get('date'),
                s.get('date_label'),
                s.get('file_count'),
                s.get('total_bytes'),
                json.dumps(s.get('files', [])),
                vod_status,
                vod_file,
                vod_error,
                s.get('ts_done') if vod_status in (db.VOD_ENCODED, db.VOD_UPLOADED) else None,
                stream_status,
                stream_folder_path,
                None,   # stream_error
                stream_ts,
                youtube_url,
                youtube_id,
                s.get('ts_done') if vod_status == db.VOD_UPLOADED else None,
                s.get('ts_found'),
            )

            if existing:
                conn.execute("""
                    UPDATE sessions SET
                        folder=?, folder_name=?, location=?, date=?, date_label=?,
                        file_count=?, total_bytes=?, files=?,
                        vod_status=?, vod_file=?, vod_error=?, vod_ts_done=?,
                        stream_status=?, stream_folder=?, stream_error=?, stream_ts_done=?,
                        youtube_url=?, youtube_id=?, youtube_ts=?, ts_found=?
                    WHERE id=?
                """, row[1:] + (sid,))
                updated += 1
            else:
                conn.execute("""
                    INSERT INTO sessions (
                        id, folder, folder_name, location, date, date_label,
                        file_count, total_bytes, files,
                        vod_status, vod_file, vod_error, vod_ts_done,
                        stream_status, stream_folder, stream_error, stream_ts_done,
                        youtube_url, youtube_id, youtube_ts, ts_found
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, row)
                inserted += 1

    print(f"Done: {inserted} inserted, {updated} updated, {skipped} skipped")

    # Summary
    with db.get_conn() as conn:
        for label, col, val in [
            ('VOD pending',   'vod_status',    db.VOD_PENDING),
            ('VOD encoded',   'vod_status',    db.VOD_ENCODED),
            ('VOD uploaded',  'vod_status',    db.VOD_UPLOADED),
            ('VOD error',     'vod_status',    db.VOD_ERROR),
            ('Stream ready',  'stream_status', db.STREAM_READY),
            ('Stream pending','stream_status', db.STREAM_PENDING),
        ]:
            n = conn.execute(f"SELECT COUNT(*) FROM sessions WHERE {col}=?", (val,)).fetchone()[0]
            print(f"  {label:<18}: {n}")


if __name__ == '__main__':
    main()
