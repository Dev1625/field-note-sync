import { pending, queueNote, rebase, upload } from './sync.mjs';

const get = (id) => document.getElementById(id);
const station = get('station');
const field = get('note');
const conflicts = new Map();
let paused = false;
let busy = false;

function snapshot(stream) {
  return JSON.parse(localStorage.getItem('field-note:cache:' + stream)) || { revision: 0, events: [] };
}

async function request(stream, entry) {
  const url = `/api/streams/${stream}/events`;
  const options = entry ? {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  } : {};
  const response = await fetch(url, options);
  return { status: response.status, data: await response.json() };
}

async function refresh(stream) {
  const { status, data } = await request(stream);
  if (status !== 200) throw new Error('Could not refresh the station history.');
  localStorage.setItem('field-note:cache:' + stream, JSON.stringify(data));
  return data.revision;
}

function connected() {
  return navigator.onLine && !paused;
}

function message(text) {
  get('message').textContent = text;
}

function drawList(container, entries, label, empty) {
  const items = entries.map(entry => {
    const li = document.createElement('li');
    const note = document.createElement('p');
    const meta = document.createElement('small');
    note.textContent = entry.note;
    meta.className = 'entry-meta';
    meta.textContent = label(entry);
    li.append(note, meta);
    return li;
  });
  if (!items.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = empty;
    items.push(li);
  }
  container.replaceChildren(...items);
}

function render() {
  const stream = station.value;
  const history = snapshot(stream);
  const queue = pending(localStorage, stream);
  const live = connected();
  const conflict = conflicts.get(stream);
  get('connection').textContent = paused ? 'Offline practice mode' : live ? 'Online' : 'Device offline';
  get('offline').textContent = paused ? 'Resume connection' : 'Work offline';
  get('offline').disabled = busy;
  get('simulate').disabled = !live || busy;
  get('sync').disabled = !live || busy || queue.length === 0 || conflict !== undefined;
  get('queue').disabled = busy;
  get('rebase').disabled = busy;
  get('revision').textContent = `Station revision ${history.revision}${live ? '' : ' · cached'}`;
  get('pending-count').textContent = queue.length;
  get('conflict').hidden = conflict === undefined;
  if (conflict !== undefined) {
    get('conflict-text').textContent = `Server revision ${conflict} is newer than the first pending note expected. Review the saved entries below before rebasing.`;
  }
  drawList(get('outbox'), queue, entry => `Waiting to sync · expects revision ${entry.expected_revision}`, 'Nothing queued.');
  drawList(get('saved'), [...history.events].reverse(), entry => `Revision ${entry.revision}`, 'No saved history on this device.');
}

get('note-form').addEventListener('submit', event => {
  event.preventDefault();
  const note = field.value.trim();
  if (!note || busy) return;
  const stream = station.value;
  queueNote(localStorage, stream, note, snapshot(stream).revision, crypto.randomUUID(), performance.timeOrigin + performance.now());
  field.value = '';
  message('Saved on this device. Sync the outbox when you are online.');
  render();
});

get('sync').addEventListener('click', async () => {
  const stream = station.value;
  busy = true;
  message('Syncing notes…');
  render();
  try {
    const result = await upload(localStorage, pending(localStorage, stream), entry => request(entry.stream, entry));
    for (const [key, revision] of result.conflicts) conflicts.set(key, revision);
    const outcome = result.stopped || (result.conflicts.size ? 'Sync paused for a revision conflict.' : `${result.synced} synced.`);
    message(outcome);
    try {
      await refresh(stream);
    } catch {
      message(`${outcome} History will refresh when the server returns.`);
    }
  } finally {
    busy = false;
    render();
  }
});

get('rebase').addEventListener('click', () => {
  const stream = station.value;
  if (!conflicts.has(stream)) return;
  rebase(localStorage, stream, Math.max(conflicts.get(stream), snapshot(stream).revision));
  conflicts.delete(stream);
  message('Pending notes now follow the latest server history. Sync the outbox again.');
  render();
});

get('offline').addEventListener('click', () => {
  paused = !paused;
  message(paused ? 'New notes will stay on this device.' : 'Connection resumed. You can sync pending notes.');
  render();
});

get('simulate').addEventListener('click', async () => {
  const stream = station.value;
  busy = true;
  render();
  try {
    const revision = await refresh(stream);
    const result = await request(stream, {
      event_id: crypto.randomUUID(), expected_revision: revision,
      note: 'Second recorder: Checked the mounting bracket and logged a fresh reading.',
    });
    if (result.status !== 201) throw new Error('Another writer changed the station first. Try again.');
    await refresh(stream);
    message('A second writer added a note to this station. The outbox still has its original expectations.');
  } catch (error) {
    message(error.message);
  } finally {
    busy = false;
    render();
  }
});

async function loadHistory() {
  render();
  if (!connected()) return;
  try { await refresh(station.value); } catch { message('Server unavailable. You can still save to the outbox.'); }
  render();
}

station.addEventListener('change', loadHistory);
window.addEventListener('online', loadHistory);
window.addEventListener('offline', render);
window.addEventListener('storage', render);
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
loadHistory();
