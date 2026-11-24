import sqlite3
from contextlib import closing
from datetime import datetime, timezone


STREAMS = {
    'creek-gauge': 'Creek gauge',
    'ridge-station': 'Ridge station',
}


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def setup(path):
    with closing(connect(path)) as db, db:
        db.execute('PRAGMA journal_mode = WAL')
        db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                stream TEXT NOT NULL,
                revision INTEGER NOT NULL,
                note TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                UNIQUE (stream, revision)
            )
        ''')
        db.executemany('INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)', [
            ('8568538b-9a57-4934-b102-deecfad51e3b', 'creek-gauge', 1,
             'Staff gauge at 42 cm. Light leaf debris near the downstream post.', '2026-09-18T09:20:00Z'),
            ('19a91134-e364-41b6-a103-e091497eaed7', 'ridge-station', 1,
             'Weather shield seated correctly. Battery indicator reads 83%.', '2026-09-18T09:05:00Z'),
        ])


def list_events(path, stream):
    with closing(connect(path)) as db:
        rows = db.execute('SELECT * FROM events WHERE stream = ? ORDER BY revision', (stream,))
        events = [dict(row) for row in rows]
    return {'stream': stream, 'revision': events[-1]['revision'] if events else 0, 'events': events}


def append(path, stream, event_id, expected_revision, note):
    with closing(connect(path)) as db, db:
        # Reserve the write lock before checking the revision.
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT * FROM events WHERE event_id = ?', (event_id,)).fetchone()
        if prior:
            if prior['stream'] == stream and prior['note'] == note:
                return 200, {'event': dict(prior), 'replayed': True}
            return 409, {'code': 'id_conflict', 'error': 'That event ID already belongs to a different note.'}

        current = db.execute(
            'SELECT COALESCE(MAX(revision), 0) FROM events WHERE stream = ?', (stream,)
        ).fetchone()[0]
        if expected_revision != current:
            return 409, {
                'code': 'stale_revision', 'revision': current,
                'error': 'This station has newer notes. Review before syncing again.',
            }

        saved = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        event = {'event_id': event_id, 'stream': stream, 'revision': current + 1, 'note': note, 'saved_at': saved}
        db.execute('INSERT INTO events VALUES (:event_id, :stream, :revision, :note, :saved_at)', event)
        return 201, {'event': event, 'replayed': False}
