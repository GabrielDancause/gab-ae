"""
db_stream_done.py -- called by preencode_all_sessions.ps1 after a session encodes.

Usage:
  python db_stream_done.py <folder_name> <stream_folder_path>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def main():
    if len(sys.argv) < 3:
        print("Usage: db_stream_done.py <folder_name> <stream_folder_path>")
        sys.exit(1)

    folder_name  = sys.argv[1]
    stream_folder = sys.argv[2]

    if not db.DB_PATH.exists():
        print(f"DB not found at {db.DB_PATH} — skipping")
        sys.exit(0)

    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE folder_name=?", (folder_name,)
        ).fetchone()

    if not row:
        print(f"Session not in DB: {folder_name} — skipping")
        sys.exit(0)

    with db.get_conn() as conn:
        current = conn.execute(
            "SELECT stream_status FROM sessions WHERE id=?", (row['id'],)
        ).fetchone()

    if current and current['stream_status'] == db.STREAM_READY:
        print(f"already ready")
        sys.exit(0)

    db.stream_set_status(row['id'], db.STREAM_READY, stream_folder=stream_folder)
    print(f"DB: {folder_name} → stream_status=ready")


if __name__ == '__main__':
    main()
