# Field Note Sync

An offline field notebook for fictional weather and water monitoring stations. The browser keeps notes in an outbox. A small Python API appends them to SQLite, handles retries, and surfaces conflicts when a second recorder gets there first.

Built with AI assistance as a portfolio demo. The stations, readings, and observations are fictional.

## Run it

Use Python 3.10 or newer. The app uses the Python standard library and plain JavaScript.

```sh
python app.py
```

Open [127.0.0.1:8084](http://127.0.0.1:8084). A normal run creates `field-notes.sqlite3` beside `app.py`. Pass `--db /path/to/demo.sqlite3` for a separate dataset or `--port 8085` to try a separate browser session.

## Walk through a conflict

1. Select **Ridge station**, click **Work offline**, and save an observation to the outbox. Its row records the server revision it expects.
2. Click **Resume connection**, then **Simulate another writer**. That button sends a real API request from a second recorder and leaves the pending note alone.
3. Click **Sync outbox**. The server returns a conflict, keeps the successful write, and leaves your pending note available for review.
4. Read the saved history, click **Rebase notes**, and sync again. The client changes the expected revision and keeps the same event ID and note text.

After one online load, the service worker caches the app files. To try a real offline reload, wait for the app to load, take the browser offline, reload, and add a note. Reconnect before submitting. Run this on loopback so the browser treats it as a secure context for the service worker and `crypto.randomUUID()`.

## How it works

| Part | What it does |
| --- | --- |
| `static/sync.mjs` | Stores each pending note under its own `localStorage` key. Removes a note only after receiving an acknowledgment that matches its ID. |
| `static/sw.js` | Caches the application shell. API requests go to the server when the connection works. |
| `app.py` | Serves the frontend and validates JSON requests. |
| `store.py` |Uses an SQLite transaction to compare the expected revision and append the note atomically. |

The `events` table uses `event_id` as a primary key and makes `(stream, revision)` unique. Revisions are independent per station. `BEGIN IMMEDIATE` serializes the check and insert, so two writes that both expect the same revision cannot commit. Repeating a note ID with the same station and text returns the original event, even after newer events arrive. Repeating the ID with different text or a different station returns a conflict.

## API

`GET /api/streams/ridge-station/events` returns the latest revision and all saved events for the station. Use the same path with `POST` to append a note.

```json
{
  "event_id": "a91007d6-d8d2-48e2-bed4-077233604080",
  "expected_revision": 1,
  "note": "Checked the mount after a rain shower."
}
```

| Status | Behavior |
| --- | --- |
| `201` | A fresh note committed. |
| `200` | The same note committed earlier. The original event is returned. |
| `409` | `stale_revision` includes the latest revision. `id_conflict` indicates reuse of an ID for a different note. |
| `400` | Input failed validation. |

## Check the behavior

```sh
python -m unittest discover -s tests -v
node --test tests/sync.test.mjs
```

The Python tests make actual HTTP requests against a temporary SQLite database and include two concurrent writers. The JavaScript tests exercise the same outbox functions the browser uses, including a lost acknowledgment and a replay. Node 20 or newer is only needed for the JavaScript tests.

This demo binds to loopback and uses two fixed sample stations. The browser outbox is stored in one browser profile and applies no background sync. Clearing browser site data deletes its pending notes. A shared deployment would need authentication, pagination, and cross-device account handling.
