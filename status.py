"""
status.py -- unified pipeline status for both computers.

Usage:
  python status.py              -- summary
  python status.py --vod        -- VOD pipeline detail
  python status.py --stream     -- stream pipeline detail
  python status.py --ready      -- sessions ready to upload (VOD done, not uploaded)
  python status.py --both       -- sessions ready on BOTH pipelines
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024: return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def summary():
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

        print(f"\n  {'PIPELINE':<20}  {'STATUS':<12}  {'COUNT':>6}")
        print('  ' + '-' * 44)

        for label, col, statuses in [
            ('VOD',    'vod_status',    [db.VOD_PENDING, db.VOD_STITCHING, db.VOD_MIXING,
                                         db.VOD_ENCODED, db.VOD_UPLOADED, db.VOD_ERROR]),
            ('Stream', 'stream_status', [db.STREAM_PENDING, db.STREAM_ENCODING,
                                         db.STREAM_READY,   db.STREAM_ERROR]),
        ]:
            for st in statuses:
                n = conn.execute(f"SELECT COUNT(*) FROM sessions WHERE {col}=?", (st,)).fetchone()[0]
                if n:
                    print(f"  {label:<20}  {st:<12}  {n:>6}")

        # Ready to upload
        n_ready = conn.execute("""
            SELECT COUNT(*) FROM sessions
            WHERE vod_status=? AND youtube_url IS NULL
        """, (db.VOD_ENCODED,)).fetchone()[0]

        # Both pipelines done
        n_both = conn.execute("""
            SELECT COUNT(*) FROM sessions
            WHERE vod_status=? AND stream_status=? AND youtube_url IS NULL
        """, (db.VOD_ENCODED, db.STREAM_READY)).fetchone()[0]

        print()
        print(f"  Total sessions      : {total}")
        print(f"  Ready to upload     : {n_ready}  (VOD encoded, not yet on YouTube)")
        print(f"  Both pipelines done : {n_both}  (VOD + stream ready, not yet uploaded)")

        # Recently completed VOD
        recent = conn.execute("""
            SELECT location, date, vod_file, youtube_url
            FROM sessions WHERE vod_status IN (?,?)
            ORDER BY vod_ts_done DESC LIMIT 5
        """, (db.VOD_ENCODED, db.VOD_UPLOADED)).fetchall()
        if recent:
            print(f"\n  Recently finished VOD:")
            for r in recent:
                url = r['youtube_url'] or '(not uploaded)'
                print(f"    {r['location'][:35]:<35}  {r['date']}  {url}")

        # Errors
        errors = conn.execute("""
            SELECT location, date, vod_error FROM sessions WHERE vod_status=?
        """, (db.VOD_ERROR,)).fetchall()
        if errors:
            print(f"\n  VOD errors ({len(errors)}):")
            for e in errors:
                print(f"    X {e['location'][:35]:<35}  {e['date']}  {(e['vod_error'] or '')[:60]}")
        print()


def detail_vod():
    rows = db.get_sessions(vod_status=[db.VOD_PENDING, db.VOD_STITCHING, db.VOD_MIXING])
    rows = sorted(rows, key=lambda r: r['date'])
    print(f"\n  VOD pending ({len(rows)} sessions):")
    for r in rows[:20]:
        print(f"    {r['location'][:35]:<35}  {r['date_label']:<25}  {r['file_count']:>3} clips  {human_size(r['total_bytes'])}")
    if len(rows) > 20:
        print(f"    ... and {len(rows)-20} more")
    print()


def detail_stream():
    ready   = db.get_sessions(stream_status=db.STREAM_READY)
    pending = db.get_sessions(stream_status=db.STREAM_PENDING)
    print(f"\n  Stream ready ({len(ready)}):")
    for r in ready:
        print(f"    + {r['location'][:35]:<35}  {r['date']}  {r['stream_folder']}")
    print(f"\n  Stream pending: {len(pending)} sessions")
    print()


def ready_to_upload():
    rows = db.get_sessions(vod_status=db.VOD_ENCODED)
    rows = [r for r in rows if not r['youtube_url']]
    print(f"\n  Ready to upload ({len(rows)} sessions):")
    for r in rows:
        size = Path(r['vod_file']).stat().st_size if r['vod_file'] and Path(r['vod_file']).exists() else 0
        print(f"    {r['location'][:35]:<35}  {r['date']}  {human_size(size)}")
    print()


def both_ready():
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM sessions
            WHERE vod_status=? AND stream_status=?
            ORDER BY date
        """, (db.VOD_ENCODED, db.STREAM_READY)).fetchall()
    print(f"\n  Both pipelines ready, not uploaded ({len(rows)}):")
    for r in rows:
        print(f"    {r['location'][:35]:<35}  {r['date']}  {r['stream_folder']}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vod',    action='store_true')
    ap.add_argument('--stream', action='store_true')
    ap.add_argument('--ready',  action='store_true', help='VOD encoded, not uploaded')
    ap.add_argument('--both',   action='store_true', help='Both pipelines done')
    args = ap.parse_args()

    if not db.DB_PATH.exists():
        print(f"Database not found: {db.DB_PATH}")
        print("Run migrate.py first, or make sure Z: is mapped.")
        sys.exit(1)

    summary()
    if args.vod:    detail_vod()
    if args.stream: detail_stream()
    if args.ready:  ready_to_upload()
    if args.both:   both_ready()


if __name__ == '__main__':
    main()
