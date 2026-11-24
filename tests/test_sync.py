import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app import make_server


class SyncTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        server = make_server(Path(tmp.name) / 'test.sqlite3', 0)
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.shutdown)
        self.url = f'http://127.0.0.1:{server.server_port}'

    def api(self, stream='ridge-station', body=None):
        path = self.url + f'/api/streams/{stream}/events'
        request = Request(path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def event(self, revision=1, note='Retightened the sensor bracket.'):
        return {'event_id': str(uuid4()), 'expected_revision': revision, 'note': note}

    def test_serves_ui_and_module(self):
        with urlopen(self.url + '/', timeout=3) as response:
            self.assertIn(b'Station notebook', response.read())
        with urlopen(self.url + '/sync.mjs', timeout=3) as response:
            self.assertEqual(response.headers.get_content_type(), 'text/javascript')

    def test_retry_returns_original_event_after_another_write(self):
        first = self.event()
        status, created = self.api(body=first)
        self.assertEqual(status, 201)
        self.assertEqual(self.api(body=self.event(2, 'Photographed the sensor mount.'))[0], 201)
        status, reply = self.api(body=first)
        self.assertEqual(status, 200)
        self.assertTrue(reply['replayed'])
        self.assertEqual(reply['event'], created['event'])
        self.assertEqual(self.api()[1]['revision'], 3)

    def test_reused_id_cannot_change_note_or_station(self):
        first = self.event()
        self.assertEqual(self.api(body=first)[0], 201)
        status, reply = self.api(body={**first, 'note': 'Changed content.'})
        self.assertEqual((status, reply['code']), (409, 'id_conflict'))
        self.assertEqual(self.api('creek-gauge', first)[1]['code'], 'id_conflict')
        self.assertEqual(self.api('creek-gauge')[1]['revision'], 1)

    def test_stale_write_can_be_rebased_without_affecting_other_stream(self):
        self.assertEqual(self.api(body=self.event())[0], 201)
        next_event = self.event(1, 'Checked cable housing.')
        status, conflict = self.api(body=next_event)
        self.assertEqual((status, conflict['code'], conflict['revision']), (409, 'stale_revision', 2))
        self.assertEqual(self.api('creek-gauge', self.event())[0], 201)
        self.assertEqual(self.api(body={**next_event, 'expected_revision': conflict['revision']})[0], 201)
        self.assertEqual([row['revision'] for row in self.api()[1]['events']], [1, 2, 3])

    def test_parallel_writers_cannot_commit_same_revision(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            replies = list(workers.map(lambda event: self.api(body=event), [self.event(), self.event()]))
        self.assertEqual(sorted(status for status, _ in replies), [201, 409])
        self.assertEqual(self.api()[1]['revision'], 2)

    def test_rejects_invalid_note_shape(self):
        self.assertEqual(self.api(body={**self.event(), 'expected_revision': True})[0], 400)
        self.assertEqual(self.api(body={**self.event(), 'note': '   '})[0], 400)
        self.assertEqual(self.api(body=['bad shape'])[0], 400)
        self.assertEqual(self.api()[1]['revision'], 1)


if __name__ == '__main__':
    unittest.main()
