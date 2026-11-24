const prefix = 'field-note:pending:';

export function pending(storage, stream) {
  return Array.from({ length: storage.length }, (_, i) => storage.key(i))
    .filter(key => key?.startsWith(prefix))
    .map(key => JSON.parse(storage.getItem(key)))
    .filter(entry => entry && (!stream || entry.stream === stream))
    .sort((a, b) => a.created - b.created || a.event_id.localeCompare(b.event_id));
}

export function queueNote(storage, stream, note, revision, id, created) {
  const entry = {
    stream, note, event_id: id, created,
    expected_revision: revision + pending(storage, stream).length,
  };
  storage.setItem(prefix + id, JSON.stringify(entry));
  return entry;
}

export function rebase(storage, stream, latest) {
  pending(storage, stream).forEach((entry, i) => {
    storage.setItem(prefix + entry.event_id, JSON.stringify({ ...entry, expected_revision: latest + i }));
  });
}

export async function upload(storage, entries, send) {
  const conflicts = new Map();
  let synced = 0;
  let stopped = '';
  for (const entry of entries) {
    if (conflicts.has(entry.stream)) continue;
    let result;
    try {
      result = await send(entry);
    } catch {
      stopped = 'Connection interrupted. Pending notes are still on this device.';
      break;
    }
    const { status, data } = result;
    if ((status === 200 || status === 201) && data.event?.event_id === entry.event_id) {
      storage.removeItem(prefix + entry.event_id);
      synced += 1;
    } else if (status === 409 && data.code === 'stale_revision') {
      conflicts.set(entry.stream, data.revision);
    } else {
      stopped = data.error || 'The server did not confirm this note. It is still on this device.';
      break;
    }
  }
  return { synced, conflicts, stopped };
}
