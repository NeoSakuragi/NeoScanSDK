#!/usr/bin/env python3
"""Brawler voice-feedback service (VPS, docs/feedback.md). Stdlib only, 127.0.0.1:8920, unit brawler-feedback.

Public (nginx: exact locations, POST only, size + rate capped; the request carries X-Public):
  POST /transcribe   the audio (body; X-Audio-Name = its file name): transcribed at once with OpenAI's API
                     (gpt-4o-mini-transcribe, whisper-1 on error; the game terms as the prompt) -> {"text", "model"}
  POST /upload       the bundle zip (X-Bundle = its id): unpacked into DATA/bundles/<id>/, a row in the tracker DB
                     (status new); its audio transcribed in the background when the player sent no transcript
Signed in (nginx /brawler-lab/feedback-api/ behind the Oros login, the Brawler Lab's Feedback tab; or over ssh on
localhost: tools/feedback/fb.py, pull.py):
  GET  /api/list[?status=&category=]        the tracker rows, newest first
  GET  /api/item/<id>                        a row + its status history + the bundle's files
  GET  /api/file/<id>/<name>                 a bundle file (the audio, screen.png)
  POST /api/status {id, status, release?, note?, duplicate_of?, by?}
  POST /api/set    {id, category?, fighters?, notes?, by?}
Tracker: DATA/feedback.db (SQLite; feedback + status_history), copied daily to DATA/backups/ (kept 14), mirrored to
the desktop by pull.py. The OpenAI key is read from KEY_FILE at each call; never logged, never stored."""
import http.server, io, json, mimetypes, os, queue, re, secrets, socketserver, sqlite3, threading, time
import urllib.error, urllib.parse, urllib.request, uuid, zipfile

DATA = os.environ.get('FEEDBACK_DATA', '/data/brawler/feedback')
PORT = int(os.environ.get('FEEDBACK_PORT', '8920'))
KEY_FILE = os.environ.get('FEEDBACK_OPENAI_KEY', '/data/oros/secrets/openai.key')
WHOAMI = os.environ.get('FEEDBACK_WHOAMI', 'http://127.0.0.1:8900/api/whoami')
MODELS = ('gpt-4o-mini-transcribe', 'whisper-1')         # the first that answers
PROMPT = ('Neo Geo brawler game feedback, in English or French. Terms: Terry, Geese, Ryo, Ryuko Ranbu, Kim, Phoenix, '
          'Hanzo, Billy, fury, MAX, grab, throw, hold hits, Chain Lab, brawler, hitbox, combo, special, desperation.')
STATUSES = ('new', 'read', 'in_progress', 'shipped', 'wont_do', 'duplicate')
CATEGORIES = ('', 'sound', 'graphics', 'gameplay', 'integration', 'scripting', 'other')
MAX_BODY = 32 << 20
MAX_AUDIO = 8 << 20
MAX_UNPACKED = 96 << 20
NAME = re.compile(r'^[a-z0-9_]{1,40}\.(state|bin|png|json|m4a|wav|mp3|ogg|txt)$')
ID = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{4}(-\d+)?$')
BUNDLES = os.path.join(DATA, 'bundles')
DB = os.path.join(DATA, 'feedback.db')
lock = threading.Lock()
jobs = queue.Queue()
ACCOUNTS = {}


def log(*a): print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)
def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row
    return c


def db_init():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY, created TEXT, apk_version TEXT, game_version TEXT, rom_sha TEXT, device TEXT,
            raw_transcript TEXT DEFAULT '', final_text TEXT DEFAULT '', audio_path TEXT DEFAULT '', bundle_path TEXT,
            status TEXT DEFAULT 'new', release TEXT DEFAULT '', notes TEXT DEFAULT '', updated TEXT,
            category TEXT DEFAULT '', fighters TEXT DEFAULT '', duplicate_of TEXT DEFAULT '', transcript_model TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS status_history (
            feedback_id TEXT, at TEXT, from_status TEXT, to_status TEXT, by TEXT, note TEXT);
        CREATE INDEX IF NOT EXISTS status_history_id ON status_history(feedback_id);''')


def backup():
    """one copy a day in DATA/backups (SQLite's online backup), the last 14 kept"""
    d = os.path.join(DATA, 'backups'); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, time.strftime('feedback-%Y%m%d.db'))
    if os.path.exists(p): return
    src = db(); dst = sqlite3.connect(p + '.part'); src.backup(dst); dst.close(); src.close(); os.replace(p + '.part', p)
    for old in sorted(f for f in os.listdir(d) if f.startswith('feedback-'))[:-14]: os.remove(os.path.join(d, old))


def write_json(path, obj):
    with open(path + '.part', 'w') as f: json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(path + '.part', path)


def multipart(fields, fname, fdata):
    b = uuid.uuid4().hex; out = io.BytesIO()
    for k, v in fields.items(): out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.write(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
              f'Content-Type: application/octet-stream\r\n\r\n'.encode())
    out.write(fdata); out.write(f'\r\n--{b}--\r\n'.encode())
    return out.getvalue(), 'multipart/form-data; boundary=' + b


def openai_transcribe(name, data):
    """-> (text, model, seconds); raises RuntimeError with the last error"""
    t0 = time.time(); err = None
    for model in MODELS:
        body, ctype = multipart({'model': model, 'prompt': PROMPT, 'response_format': 'json'}, name, data)
        with open(KEY_FILE) as f: auth = 'Bearer ' + f.read().strip()   # at each call: a rotated key needs no restart
        req = urllib.request.Request('https://api.openai.com/v1/audio/transcriptions', data=body, method='POST',
                                     headers={'Authorization': auth, 'Content-Type': ctype})
        del auth
        try:
            with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
            return res.get('text', '').strip(), model, round(time.time() - t0, 2)
        except urllib.error.HTTPError as e: err = f'{model}: HTTP {e.code} {e.read()[:200]!r}'
        except Exception as e: err = f'{model}: {e}'
        log('transcribe', name, err)
    raise RuntimeError(err or '?')


def transcribe_bundle(bid):
    """background: a bundle that came without a transcript (offline at the time, or the box failed)"""
    d = os.path.join(BUNDLES, bid)
    with db() as c: row = c.execute('SELECT audio_path, raw_transcript FROM feedback WHERE id=?', (bid,)).fetchone()
    if not row or not row['audio_path'] or row['raw_transcript']: return
    p = os.path.join(d, row['audio_path'])
    if not os.path.exists(p): return
    t0 = time.time()
    text, model, dt = openai_transcribe(row['audio_path'], open(p, 'rb').read())
    with open(os.path.join(d, 'transcript.txt'), 'w') as f: f.write(text + '\n')
    write_json(os.path.join(d, 'transcript.json'), {'text': text, 'model': model, 'seconds': dt, 'done': now(), 'by': 'server'})
    with db() as c: c.execute('UPDATE feedback SET raw_transcript=?, transcript_model=?, updated=? WHERE id=?', (text, model, now(), bid))
    log('transcribed', bid, model, f'{time.time() - t0:.1f}s', len(text), 'chars')


def worker():
    while True:
        try: bid = jobs.get(timeout=3600)
        except queue.Empty: bid = None
        try:
            backup()
            if bid: transcribe_bundle(bid)
        except Exception as e: log('worker', bid, 'error', e)


def account(headers):
    """who is asking: the Oros user behind the Lab's cookie, else the caller's own "by" (ssh = root on the box)"""
    cookie = headers.get('Cookie', '')
    if not cookie: return None
    hit = ACCOUNTS.get(cookie)
    if hit and hit[1] > time.time(): return hit[0]
    try:
        with urllib.request.urlopen(urllib.request.Request(WHOAMI, headers={'Cookie': cookie}), timeout=5) as r:
            name = json.load(r).get('username') or None
    except Exception: name = None
    if name: ACCOUNTS[cookie] = (name, time.time() + 300)
    return name


def row_dict(r): return {k: r[k] for k in r.keys()}


class H(http.server.BaseHTTPRequestHandler):
    def reply(self, code, obj=None, body=None, ctype='application/json'):
        b = body if body is not None else (json.dumps(obj, ensure_ascii=False) + '\n').encode()
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def body(self, limit):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > limit: return None
        return self.rfile.read(n)

    # ---- signed-in API --------------------------------------------------------------------------------------------
    def api_ok(self):
        if self.headers.get('X-Public'): self.reply(404, {'error': 'not found'}); return False
        return True

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path in ('/', '/health'): return self.reply(200, {'ok': True})
        if not u.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        parts = u.path.split('/')[2:]
        with db() as c:
            if parts == ['list']:
                sql, args = 'SELECT * FROM feedback', []
                conds = []
                for k in ('status', 'category'):
                    if q.get(k): conds.append(f'{k}=?'); args.append(q[k][0])
                if conds: sql += ' WHERE ' + ' AND '.join(conds)
                rows = [row_dict(r) for r in c.execute(sql + ' ORDER BY created DESC', args)]
                return self.reply(200, {'rows': rows, 'statuses': STATUSES, 'categories': CATEGORIES[1:], 'user': account(self.headers)})
            if len(parts) == 2 and parts[0] == 'item' and ID.match(parts[1]):
                r = c.execute('SELECT * FROM feedback WHERE id=?', (parts[1],)).fetchone()
                if not r: return self.reply(404, {'error': 'no such feedback'})
                hist = [row_dict(h) for h in c.execute('SELECT * FROM status_history WHERE feedback_id=? ORDER BY at', (parts[1],))]
                d = os.path.join(BUNDLES, parts[1])
                return self.reply(200, {'row': row_dict(r), 'history': hist, 'files': sorted(os.listdir(d)) if os.path.isdir(d) else []})
        if len(parts) == 3 and parts[0] == 'file' and ID.match(parts[1]) and NAME.match(parts[2]):
            p = os.path.join(BUNDLES, parts[1], parts[2])
            if os.path.exists(p):
                return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
        self.reply(404, {'error': 'not found'})

    def change(self, fn):
        b = self.body(1 << 16)
        try: req = json.loads(b or b'')
        except ValueError: return self.reply(400, {'error': 'json'})
        bid = req.get('id', '')
        by = account(self.headers) or req.get('by') or 'ssh'
        with lock, db() as c:
            r = c.execute('SELECT * FROM feedback WHERE id=?', (bid,)).fetchone()
            if not r: return self.reply(404, {'error': 'no such feedback: ' + bid})
            err = fn(c, r, req, by)
            if err: return self.reply(400, {'error': err})
            out = row_dict(c.execute('SELECT * FROM feedback WHERE id=?', (bid,)).fetchone())
        self.reply(200, {'row': out})

    @staticmethod
    def set_status(c, r, req, by):
        st = req.get('status')
        if st not in STATUSES: return 'status: one of ' + ', '.join(STATUSES)
        rel = req.get('release', r['release'] or '')
        if st == 'shipped' and not rel: return 'shipped needs a release (the brawler version, e.g. 0.0.71)'
        dup = req.get('duplicate_of', '')
        if st == 'duplicate' and not c.execute('SELECT 1 FROM feedback WHERE id=?', (dup,)).fetchone():
            return 'duplicate needs duplicate_of = an existing feedback id'
        c.execute('UPDATE feedback SET status=?, release=?, duplicate_of=?, updated=? WHERE id=?',
                  (st, rel if st == 'shipped' else r['release'], dup if st == 'duplicate' else r['duplicate_of'], now(), r['id']))
        c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (r['id'], now(), r['status'], st, by, req.get('note', '')))

    @staticmethod
    def set_fields(c, r, req, by):
        cat = req.get('category', r['category'])
        if cat not in CATEGORIES: return 'category: one of ' + ', '.join(CATEGORIES[1:])
        fighters = ','.join(f.strip().lower() for f in str(req.get('fighters', r['fighters'])).split(',') if f.strip())
        c.execute('UPDATE feedback SET category=?, fighters=?, notes=?, updated=? WHERE id=?',
                  (cat, fighters, req.get('notes', r['notes']), now(), r['id']))
        changed = [f'{k}={v}' for k, v in (('category', cat), ('fighters', fighters)) if v != r[k]]
        if 'notes' in req and req['notes'] != r['notes']: changed.append('notes')
        if changed: c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (r['id'], now(), r['status'], r['status'], by, 'set ' + ' '.join(changed)))

    # ---- POST ---------------------------------------------------------------------------------------------------
    def do_POST(self):
        if self.path == '/transcribe': return self.transcribe()
        if self.path == '/upload': return self.upload()
        if not self.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        if self.path == '/api/status': return self.change(self.set_status)
        if self.path == '/api/set': return self.change(self.set_fields)
        self.reply(404, {'error': 'not found'})

    def transcribe(self):
        data = self.body(MAX_AUDIO)
        if data is None: return self.reply(413, {'error': 'size'})
        name = self.headers.get('X-Audio-Name', 'audio.m4a')
        if not NAME.match(name): name = 'audio.m4a'
        t0 = time.time()
        try: text, model, dt = openai_transcribe(name, data)
        except RuntimeError as e: return self.reply(502, {'error': 'transcription unavailable'})
        log('transcribe (player)', len(data), 'bytes', model, f'{time.time() - t0:.1f}s', len(text), 'chars')
        self.reply(200, {'text': text, 'model': model, 'seconds': dt})

    def upload(self):
        body = self.body(MAX_BODY)
        if body is None: return self.reply(413, {'error': 'size'})
        try: z = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile: return self.reply(400, {'error': 'not a zip'})
        infos = z.infolist()
        if not infos or any(not NAME.match(i.filename) for i in infos) or sum(i.file_size for i in infos) > MAX_UNPACKED:
            return self.reply(400, {'error': 'unexpected content'})
        want = self.headers.get('X-Bundle', '')
        bid = want if ID.match(want) else time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2)
        with lock:
            base = bid; k = 1
            while os.path.exists(os.path.join(BUNDLES, bid)): bid = f'{base}-{k}'; k += 1
            os.makedirs(os.path.join(BUNDLES, bid))
        d = os.path.join(BUNDLES, bid)
        for i in infos:
            with open(os.path.join(d, i.filename), 'wb') as f: f.write(z.read(i))
        try: meta = json.load(open(os.path.join(d, 'meta.json')))
        except Exception: meta = {}
        write_json(os.path.join(d, 'received.json'), {'received': now(), 'bytes': len(body),
                   'install': self.headers.get('X-Install-Id', ''), 'device': self.headers.get('X-Device', '')})
        audio = meta.get('audio', '') if meta.get('audio') and os.path.exists(os.path.join(d, meta.get('audio', ''))) else ''
        raw = meta.get('raw_transcript', '') or ''
        if raw:
            with open(os.path.join(d, 'transcript.txt'), 'w') as f: f.write(raw + '\n')
        with lock, db() as c:
            c.execute('INSERT INTO feedback (id, created, apk_version, game_version, rom_sha, device, raw_transcript, final_text, '
                      'audio_path, bundle_path, status, updated, transcript_model) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (bid, meta.get('created') or now(), meta.get('app_version', ''), meta.get('rom_version', ''), meta.get('rom_sha256', ''),
                       meta.get('device', ''), raw, meta.get('final_text', ''), audio, d, 'new', now(), meta.get('transcript_model', '')))
            c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (bid, now(), '', 'new', 'player', meta.get('kind', '')))
        if audio and not raw: jobs.put(bid)
        log('bundle', bid, len(body), 'bytes', meta.get('device'), meta.get('app_version'), 'text' if meta.get('final_text') else 'no text')
        self.reply(200, {'id': bid})

    def log_message(self, fmt, *a): pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    os.makedirs(BUNDLES, exist_ok=True); db_init()
    threading.Thread(target=worker, daemon=True).start()
    with db() as c:                                          # transcripts missed while down
        for r in c.execute("SELECT id FROM feedback WHERE audio_path != '' AND raw_transcript = ''"): jobs.put(r['id'])
    log('listening on 127.0.0.1:%d, data %s' % (PORT, DATA))
    Server(('127.0.0.1', PORT), H).serve_forever()
