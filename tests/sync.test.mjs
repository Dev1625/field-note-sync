import assert from 'node:assert/strict';
import { test } from 'node:test';
import { pending, queueNote, rebase, upload } from '../static/sync.mjs';

function browserStorage() {
  const values = new Map();
  return {
    get length() { return values.size; },
    key(i) { return [...values.keys()][i]; },
    getItem(key) { return values.get(key); },
    setItem(key, value) { values.set(key, value); },
    removeItem(key) { values.delete(key); },
  };
}

test('queuing counts only earlier notes for the same stream', () => {
  const store = browserStorage();
  queueNote(store, 'ridge', 'One', 4, 'a', 1);
  queueNote(store, 'creek', 'Two', 8, 'b', 2);
  queueNote(store, 'ridge', 'Three', 4, 'c', 3);
  assert.deepEqual(pending(store).map(note => note.expected_revision), [4, 8, 5]);
  rebase(store, 'ridge', 7);
  assert.deepEqual(pending(store).map(note => note.expected_revision), [7, 8, 8]);
  assert.deepEqual(pending(store).map(note => note.event_id), ['a', 'b', 'c']);
});

test('network error preserves the ID and one acknowledged replay removes it', async () => {
  const store = browserStorage();
  queueNote(store, 'ridge', 'Saw loose casing', 3, 'original-id', 2);
  const failed = await upload(store, pending(store), () => { throw new Error('lost acknowledgment'); });
  assert.equal(failed.synced, 0);
  assert.equal(pending(store)[0].event_id, 'original-id');
  const reply = await upload(store, pending(store), entry => ({ status: 200, data: { event: entry } }));
  assert.equal(reply.synced, 1);
  assert.equal(pending(store).length, 0);
});

test('a stale stream pauses while an independent stream can continue', async () => {
  const store = browserStorage();
  queueNote(store, 'ridge', 'First', 2, 'a', 1);
  queueNote(store, 'ridge', 'Second', 2, 'b', 2);
  queueNote(store, 'creek', 'Third', 2, 'c', 3);
  const requested = [];
  const result = await upload(store, pending(store), entry => {
    requested.push(entry.event_id);
    if (entry.stream === 'ridge') return { status: 409, data: { code: 'stale_revision', revision: 5 } };
    return { status: 201, data: { event: entry } };
  });
  assert.deepEqual(requested, ['a', 'c']);
  assert.equal(result.conflicts.get('ridge'), 5);
  assert.deepEqual(pending(store).map(entry => entry.event_id), ['a', 'b']);
});
