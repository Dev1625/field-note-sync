import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from store import STREAMS, append, list_events, setup


ROOT = Path(__file__).parent
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/sync.mjs': ('sync.mjs', 'text/javascript; charset=utf-8'),
    '/sw.js': ('sw.js', 'text/javascript; charset=utf-8'),
}
EVENT_PATHS = {f'/api/streams/{key}/events': key for key in STREAMS}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        if content_type.startswith('application/json'):
            self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, data):
        self.send(status, json.dumps(data).encode(), 'application/json; charset=utf-8')

    def local_request(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host', '') not in hosts:
            self.json(403, {'error': 'Use the loopback address printed when the demo starts.'})
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path in ASSETS:
            name, content_type = ASSETS[path]
            self.send(200, (ROOT / 'static' / name).read_bytes(), content_type)
        elif path in EVENT_PATHS:
            self.json(200, list_events(self.server.db_path, EVENT_PATHS[path]))
        else:
            self.json(404, {'error': 'Not found.'})

    def do_POST(self):
        if not self.local_request():
            return
        stream = EVENT_PATHS.get(urlsplit(self.path).path)
        if stream is None:
            self.json(404, {'error': 'Station not found.'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.json(415, {'error': 'Send an application/json body.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 1 <= length <= 8192:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError()
            event_id = str(UUID(data.get('event_id', '')))
            revision = data.get('expected_revision')
            note = data.get('note')
            if type(revision) is not int or revision < 0 or not isinstance(note, str):
                raise ValueError()
            note = note.strip()
            if not 1 <= len(note) <= 500:
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            self.json(400, {'error': 'Use a UUID, a nonnegative expected revision, and a 1 to 500 character note.'})
            return
        try:
            status, response = append(self.server.db_path, stream, event_id, revision, note)
        except sqlite3.OperationalError:
            self.json(503, {'error': 'The database is temporarily unavailable. Keep the note and retry.'})
            return
        self.json(status, response)


def make_server(path, port):
    setup(path)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = path
    return server


def main():
    parser = argparse.ArgumentParser(description='Run the local field notes demo')
    parser.add_argument('--db', type=Path, default=ROOT / 'field-notes.sqlite3')
    parser.add_argument('--port', type=int, default=8084)
    args = parser.parse_args()
    with make_server(args.db, args.port) as server:
        print(f'Field Note Sync at http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
