#!/usr/bin/env python3
"""Brawler voice-feedback service (VPS, docs/feedback.md). Stdlib only, 127.0.0.1:8920, unit brawler-feedback.

The player (Player 0.0.15+: nginx /brawler/feedback/, every call behind the Oros login: auth_request /jlpt-auth on the
Authorization: Bearer <Oros JWT> the player got from /oros/api/login; the request carries X-Public, and this service
checks the token again with Oros's /api/whoami, so it knows the user; no token = 401):
  POST /transcribe   the audio (body; X-Audio-Name = its file name): transcribed at once with OpenAI's API
                     (gpt-4o-mini-transcribe, whisper-1 on error; the game terms as the prompt) -> {"text", "model"}
  POST /upload       the bundle zip (X-Bundle = its id): unpacked into DATA/bundles/<id>/, a row in the tracker DB
                     (status new, user = the signed-in account); its audio transcribed in the background when the
                     player sent no transcript
  GET  /dlauth       nginx's auth_request for /brawler/download/ (the token, or a pre-0.0.15 player in the transition)
  GET  /mine         the user's notes, newest first, each with its status history and its files (the player's list)
  GET  /mine/file/<id>/<name>   a file of one of the user's notes (screen_marked.png, audio.m4a, reply_<n>.m4a ...)
  POST /reply        (Player 0.0.17) a reply to one of the user's notes, JSON {id, kind, text, raw_transcript?, tx_id?,
                     audio_b64?, audio_name?, device?, android?}: kind voice (its audio, transcribed by /transcribe
                     first and edited) | text | up (thumbs up: status verified) | down (thumbs down: status reopened,
                     with an optional text / voice); stored in the replies table with its origin, the status change
                     in status_history -> {"reply", "row"}. Every row of /mine, /api/list and /api/item carries its
                     thread ("replies", oldest first).
  GET  /mine/scenario/<id>/<sha>/<key>.state   (Player 0.0.22) a note's test state for build <sha> on system <key>
                     (mvs-mvs arcade, uni-aes console; tools/brawler/scenario.py); 404 = none for that build. /mine rows
                     carry "scenario" {title, do, expect}, "scenario_builds" ["<sha>/<key>"] and "timeline"
  POST /test         (Player 0.0.22) a test attempt: a zip with test.json {id, result up | down | abandoned, rom_sha,
                     game_version, system, seconds, reply_id?, note?} + the attempt's replay (bundle files) -> tests table,
                     DATA/attempts/<attempt id>/
  Notes sent before the login (no user) are claimed by the first account that calls from the same install id.
Signed in (nginx /brawler-lab/feedback-api/ behind the Oros login, the Brawler Lab's Feedback tab; or over ssh on
localhost: tools/feedback/fb.py, pull.py):
  GET  /api/list[?status=&category=]        the tracker rows, newest first
  GET  /api/item/<id>                        a row + its status history + the bundle's files
  GET  /api/file/<id>/<name>                 a bundle file (the audio, screen.png, the states, inputs.bin)
  GET  /api/rom/<sha256>                     the game build a note was played on (gzip, cached for good by the
                                             browser): DATA/roms/<sha>.neo.gz, archived from the builds dir when the
                                             note arrives, so publish_vps.sh's pruning never loses a build with feedback
  POST /api/status {id, status, release?, note?, duplicate_of?, by?}
  POST /api/set    {id, category?, fighters?, notes?, title?, todo?, fix?, rca?, by?}   title: the one-line headline I write at triage
                   (<= 70 chars, one line; every change goes to status_history as 'title: "..."'); todo: its TODO item(s)
  POST /api/status also takes commit (status fixed needs it: on the branch, not yet published)
  GET  /api/scenario/<id>                    its test recipe + the states per build; POST /api/scenario {id, recipe}
  POST /api/scenario_state {id, rom_sha, keys, version, state_sha256}   scenario.py, after the rsync of the states
  GET  /api/scenario/<id>/<sha>/<file>       a state / the proof clip; GET /api/attempt/<aid>/<name> a test attempt's replay
  POST /api/test {id, result, rom_sha?, game_version?, system?, note?}  a test attempt in the Lab (up / down set the status)
  GET  /api/select_layout                    the select screen layout Bruno saved in the Lab's Select screen tab (404: none)
  POST /api/select_layout {layout, game_version?}   saved as DATA/select_layout.json (the one before it kept in
                                             DATA/select_layout/<time>.json); tools/brawler/select_layout.py pulls it
                                             into game.json "select_layout" 
  POST /api/event {id, kind, at, text, ref, todo?, fix_commit?}         a timeline event (backfill_history.py; idempotent)
Lifecycle (docs/feedback.md): every row's timeline = found + status history + events + tests + replies, oldest first.
Cost: every transcription's usage as OpenAI returns it (tokens, or seconds for whisper-1) and its USD cost from
PRICES (prices.json next to this file: the price table with its source and date) go to the transcriptions table,
linked to its note (the player sends the tx_id it got back; cancelled notes' transcriptions stay unlinked but count
in the total). Notes from before the cost log: estimated from the audio's duration (source 'duration').
Tracker: DATA/feedback.db (SQLite; feedback + status_history + transcriptions + replies), copied daily to DATA/backups/ (kept 14), mirrored to
the desktop by pull.py. The OpenAI key is read from KEY_FILE at each call; never logged, never stored."""
import http.server, io, json, mimetypes, os, queue, re, secrets, socketserver, sqlite3, threading, time
import urllib.error, urllib.parse, urllib.request, uuid, zipfile

DATA = os.environ.get('FEEDBACK_DATA', '/data/brawler/feedback')
PORT = int(os.environ.get('FEEDBACK_PORT', '8920'))
PRICES = os.environ.get('FEEDBACK_PRICES', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prices.json'))
KEY_FILE = os.environ.get('FEEDBACK_OPENAI_KEY', '/data/oros/secrets/openai.key')
WHOAMI = os.environ.get('FEEDBACK_WHOAMI', 'http://127.0.0.1:8900/api/whoami')
INSTALL = re.compile(r'^[0-9a-f-]{8,40}$')
LEGACY_FLAG = os.path.join(DATA, 'legacy_open')   # exists = players < 0.0.15 may still send without the login (transition)


def old_player(v):
    try: return tuple(int(x) for x in v.split('.')) < (0, 0, 15)
    except ValueError: return False
MODELS = ('gpt-4o-mini-transcribe', 'whisper-1')         # the first that answers
PROMPT = ('Neo Geo brawler game feedback, in English or French. Terms: Terry, Geese, Ryo, Ryuko Ranbu, Kim, Phoenix, '
          'Hanzo, Billy, fury, MAX, grab, throw, hold hits, Chain Lab, brawler, hitbox, combo, special, desperation.')
STATUSES = ('new', 'read', 'in_progress', 'fixed', 'shipped', 'wont_do', 'duplicate', 'verified', 'reopened')   # fixed: on the
                                                         # branch (its commit), not yet in a published build
TEST_RESULTS = ('up', 'down', 'abandoned')               # a test attempt (Player 0.0.22 / the Lab): fixed / still broken / left
SCENARIOS = os.path.join(DATA, 'scenarios')              # <id>/<rom sha>/<key>.state (+ clip.gif, sheet.png, <key>_start.png)
ATTEMPTS = os.path.join(DATA, 'attempts')                # <attempt id>/ the replay of a test attempt (the bundle's files)
SFILE = re.compile(r'^[a-z0-9_-]{1,40}\.(state|png|gif|json)$')
SKEY = re.compile(r'^[a-z]{3}-[a-z]{3}$')               # the player's system: Native.systemType() + '-' + hw
REPLY_KINDS = ('voice', 'text', 'up', 'down')            # up = verified fixed, down = still broken (reopened)
MAX_REPLY = 12 << 20                                     # the JSON with the voice in base64 (MAX_AUDIO * 4 / 3)
CATEGORIES = ('', 'sound', 'graphics', 'gameplay', 'integration', 'scripting', 'other')
MAX_BODY = 32 << 20
MAX_AUDIO = 8 << 20
MAX_UNPACKED = 96 << 20
NAME = re.compile(r'^[a-z0-9_]{1,40}\.(state|bin|png|json|m4a|wav|mp3|ogg|txt)$')
ID = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{4}(-\d+)?$')
BUNDLES = os.path.join(DATA, 'bundles')
ROMS = os.path.join(DATA, 'roms')
BUILDS = os.environ.get('FEEDBACK_BUILDS', '/data/brawler/builds')
SHA = re.compile(r'^[0-9a-f]{64}$')
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
        CREATE INDEX IF NOT EXISTS status_history_id ON status_history(feedback_id);
        CREATE TABLE IF NOT EXISTS transcriptions (
            tx_id TEXT PRIMARY KEY, at TEXT, feedback_id TEXT DEFAULT '', model TEXT, audio_seconds REAL,
            input_text_tokens INTEGER, input_audio_tokens INTEGER, output_tokens INTEGER, usage_json TEXT,
            cost_usd REAL, cost_source TEXT, prices_checked TEXT, by TEXT);
        CREATE INDEX IF NOT EXISTS transcriptions_fb ON transcriptions(feedback_id);
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, feedback_id TEXT, at TEXT, user TEXT, kind TEXT, text TEXT DEFAULT '',
            raw_transcript TEXT DEFAULT '', audio_path TEXT DEFAULT '', status_from TEXT DEFAULT '', status_to TEXT DEFAULT '',
            apk_version TEXT, install_id TEXT, device TEXT, android TEXT, ip TEXT, user_agent TEXT);
        CREATE INDEX IF NOT EXISTS replies_fb ON replies(feedback_id);
        CREATE TABLE IF NOT EXISTS scenarios (
            feedback_id TEXT PRIMARY KEY, recipe TEXT, updated TEXT, by TEXT);
        CREATE TABLE IF NOT EXISTS scenario_states (
            feedback_id TEXT, rom_sha TEXT, key TEXT, version TEXT DEFAULT '', state_sha256 TEXT DEFAULT '', created TEXT, by TEXT,
            PRIMARY KEY (feedback_id, rom_sha, key));
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, feedback_id TEXT, at TEXT, user TEXT, source TEXT, result TEXT,
            rom_sha TEXT DEFAULT '', game_version TEXT DEFAULT '', system TEXT DEFAULT '', apk_version TEXT DEFAULT '',
            device TEXT DEFAULT '', reply_id INTEGER, attempt TEXT DEFAULT '', seconds REAL, note TEXT DEFAULT '', ip TEXT);
        CREATE INDEX IF NOT EXISTS tests_fb ON tests(feedback_id);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, feedback_id TEXT, at TEXT, by TEXT, kind TEXT, text TEXT DEFAULT '',
            ref TEXT DEFAULT '', UNIQUE (feedback_id, kind, ref));
        CREATE INDEX IF NOT EXISTS events_fb ON events(feedback_id);''')
        cols = {r[1] for r in c.execute('PRAGMA table_info(feedback)')}
        for col in ('user', 'install_id', 'marked', 'title', 'todo', 'fix_commit', 'fix', 'rca'):   # 0.0.15: the account, its install, a scribble;
                                                                      # title: my one-liner; todo: the TODO item(s); fix_commit;
                                                                      # fix / rca: the fix and its root cause, one or two plain sentences each
            if col not in cols: c.execute(f"ALTER TABLE feedback ADD COLUMN {col} TEXT DEFAULT ''")
        for col in ('ip', 'user_agent', 'android'):                   # who sent it from where (NULL = unknown)
            if col not in cols: c.execute(f"ALTER TABLE feedback ADD COLUMN {col} TEXT")
        tcols = {r[1] for r in c.execute('PRAGMA table_info(transcriptions)')}
        for col in ('user', 'install_id', 'ip', 'user_agent'):
            if col not in tcols: c.execute(f"ALTER TABLE transcriptions ADD COLUMN {col} TEXT")
        for r in c.execute("SELECT id FROM feedback WHERE install_id = ''").fetchall():
            try: inst = json.load(open(os.path.join(BUNDLES, r['id'], 'received.json'))).get('install', '')
            except Exception: inst = ''
            if inst: c.execute('UPDATE feedback SET install_id=? WHERE id=?', (inst, r['id']))


NGINX_LOGS = os.environ.get('FEEDBACK_NGINX_LOG', '/var/log/nginx/brawler.log')
LOGLINE = re.compile(r'^(\S+) (\S+) "(/brawler/feedback/(?:upload|transcribe))" 200 .*? install="([^"]*)" ua="([^"]*)"')


def backfill_origin():
    """notes and transcriptions from before the origin columns: their IP + user agent (+ install) from nginx's
    brawler log (log rotations included) by time (and install for a note); no match = left NULL"""
    import glob, gzip, datetime
    with db() as c:
        fb = c.execute("SELECT id, install_id, created FROM feedback WHERE ip IS NULL").fetchall()
        tx = c.execute("SELECT tx_id, at FROM transcriptions WHERE ip IS NULL AND by='player'").fetchall()
        miss = c.execute("SELECT id FROM feedback WHERE android IS NULL").fetchall()
    for r in miss:                                            # the device's Android version, from the bundle's meta.json
        try: a = json.load(open(os.path.join(BUNDLES, r['id'], 'meta.json'))).get('android')
        except Exception: a = None
        if a:
            with lock, db() as c: c.execute('UPDATE feedback SET android=? WHERE id=?', (a, r['id']))
    with lock, db() as c:                                     # a linked transcription's user = its note's
        c.execute("UPDATE transcriptions SET user=(SELECT NULLIF(f.user, '') FROM feedback f WHERE f.id=transcriptions.feedback_id) "
                  "WHERE user IS NULL AND feedback_id != ''")
    if not fb and not tx: return
    hits = {'/brawler/feedback/upload': [], '/brawler/feedback/transcribe': []}
    for p in glob.glob(NGINX_LOGS + '*'):
        try:
            with (gzip.open(p, 'rt', errors='replace') if p.endswith('.gz') else open(p, errors='replace')) as f:
                for line in f:
                    m = LOGLINE.match(line)
                    if m: hits[m[3]].append((datetime.datetime.fromisoformat(m[1]).timestamp(), m[2], m[4] if m[4] != '-' else None, m[5]))
        except OSError as e: log('backfill origin: cannot read', p, e)
    ts = lambda iso: datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp()
    n = 0
    for r in fb:
        try: t = ts(json.load(open(os.path.join(BUNDLES, r['id'], 'received.json')))['received'])
        except Exception: continue
        c_ = [h for h in hits['/brawler/feedback/upload'] if abs(h[0] - t) <= 120 and (not r['install_id'] or h[2] == r['install_id'])]
        if not c_: continue
        h = min(c_, key=lambda h: abs(h[0] - t))
        with lock, db() as c: c.execute('UPDATE feedback SET ip=?, user_agent=?, install_id=COALESCE(NULLIF(install_id, \'\'), ?) WHERE id=?', (h[1], h[3], h[2] or '', r['id']))
        n += 1
    k = 0
    for r in tx:
        try: t = ts(r['at'])
        except Exception: continue
        c_ = [h for h in hits['/brawler/feedback/transcribe'] if abs(h[0] - t) <= 15]
        if not c_: continue
        h = min(c_, key=lambda h: abs(h[0] - t))
        with lock, db() as c: c.execute('UPDATE transcriptions SET ip=?, user_agent=?, install_id=? WHERE tx_id=?', (h[1], h[3], h[2], r['tx_id']))
        k += 1
    log(f'backfill origin: {n} of {len(fb)} notes, {k} of {len(tx)} transcriptions matched in the nginx log')


def backup():
    """one copy a day in DATA/backups (SQLite's online backup), the last 14 kept"""
    d = os.path.join(DATA, 'backups'); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, time.strftime('feedback-%Y%m%d.db'))
    if os.path.exists(p): return
    src = db(); dst = sqlite3.connect(p + '.part'); src.backup(dst); dst.close(); src.close(); os.replace(p + '.part', p)
    for old in sorted(f for f in os.listdir(d) if f.startswith('feedback-'))[:-14]: os.remove(os.path.join(d, old))


def prices():
    return json.load(open(PRICES))


def audio_seconds(data=None, path=None):
    """the audio's duration (ffprobe), None when unknown"""
    import subprocess, tempfile
    tmp = None
    if path is None:
        tmp = tempfile.NamedTemporaryFile(suffix='.m4a', delete=False); tmp.write(data); tmp.close(); path = tmp.name
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True, timeout=20)
        return round(float(r.stdout.strip()), 2)
    except Exception: return None
    finally:
        if tmp: os.unlink(tmp.name)


def cost_of(model, usage, seconds):
    """-> (usd, source, prices_checked, text_in, audio_in, out)"""
    P = prices(); m = P['models'].get(model, {})
    usage = usage or {}
    if usage.get('type') == 'tokens':
        det = usage.get('input_token_details') or {}
        ti, ai, out = det.get('text_tokens', 0), det.get('audio_tokens', usage.get('input_tokens', 0)), usage.get('output_tokens', 0)
        usd = ti * m.get('text_input_per_1m', 0) / 1e6 + ai * m.get('audio_input_per_1m', 0) / 1e6 + out * m.get('output_per_1m', 0) / 1e6
        return usd, 'usage', P['checked'], ti, ai, out
    secs = usage.get('seconds') if usage.get('type') == 'duration' else seconds
    rate = m.get('per_minute', m.get('estimated_per_minute', 0))
    return (secs or 0) / 60 * rate, 'usage' if usage.get('type') == 'duration' else 'duration', P['checked'], None, None, None


def log_tx(model, usage, seconds, feedback_id='', by='player', at=None, source=None, who=None):
    """[who] = the caller of a player transcription: {user, install_id, ip, user_agent} ([H.who])"""
    usd, src, checked, ti, ai, out = cost_of(model, usage, seconds)
    tx = secrets.token_hex(8)
    w = who or {}
    with lock, db() as c:
        c.execute('INSERT INTO transcriptions (tx_id, at, feedback_id, model, audio_seconds, input_text_tokens, input_audio_tokens, output_tokens, '
                  'usage_json, cost_usd, cost_source, prices_checked, by, user, install_id, ip, user_agent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (tx, at or now(), feedback_id, model, seconds, ti, ai, out, json.dumps(usage) if usage else '', round(usd, 6), source or src,
                   checked, by, w.get('user'), w.get('install_id'), w.get('ip'), w.get('user_agent')))
    return tx, usd


def backfill():
    """notes with a voice and no transcription logged: the unlinked player transcription of the same duration (an
    older player sent no tx_id), else estimated from the audio's duration"""
    with db() as c:
        rows = c.execute("SELECT id, audio_path, transcript_model, created FROM feedback WHERE audio_path != '' AND raw_transcript != '' "
                         "AND id NOT IN (SELECT feedback_id FROM transcriptions)").fetchall()
    for r in rows:
        secs = audio_seconds(path=os.path.join(BUNDLES, r['id'], r['audio_path']))
        with lock, db() as c:
            t = c.execute("SELECT tx_id, cost_usd FROM transcriptions WHERE feedback_id='' AND by='player' AND ABS(audio_seconds - ?) < 0.05 "
                          "ORDER BY at LIMIT 1", (secs or -1,)).fetchone()
            if t: c.execute('UPDATE transcriptions SET feedback_id=? WHERE tx_id=?', (r['id'], t['tx_id']))
        if t: log('backfill cost', r['id'], 'linked', t['tx_id'], f"${t['cost_usd']:.5f}"); continue
        tx, usd = log_tx(r['transcript_model'] or MODELS[0], None, secs, r['id'], 'backfill', r['created'])
        log('backfill cost', r['id'], secs, 's', f'${usd:.5f}')


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
            return res.get('text', '').strip(), model, round(time.time() - t0, 2), res.get('usage')
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
    data = open(p, 'rb').read()
    text, model, dt, usage = openai_transcribe(row['audio_path'], data)
    log_tx(model, usage, audio_seconds(path=p), bid, 'server')
    with open(os.path.join(d, 'transcript.txt'), 'w') as f: f.write(text + '\n')
    write_json(os.path.join(d, 'transcript.json'), {'text': text, 'model': model, 'seconds': dt, 'done': now(), 'by': 'server'})
    with db() as c: c.execute('UPDATE feedback SET raw_transcript=?, transcript_model=?, updated=? WHERE id=?', (text, model, now(), bid))
    log('transcribed', bid, model, f'{time.time() - t0:.1f}s', len(text), 'chars')


def archive_rom(sha):
    """DATA/roms/<sha>.neo.gz from the published build with that sha256 (if it is still there)"""
    import gzip, hashlib, shutil
    if not SHA.match(sha or '') or os.path.exists(os.path.join(ROMS, sha + '.neo.gz')): return
    os.makedirs(ROMS, exist_ok=True)
    for f in sorted(os.listdir(BUILDS)):
        p = os.path.join(BUILDS, f)
        if not f.endswith('.neo') or os.path.islink(p): continue
        h = hashlib.sha256()
        with open(p, 'rb') as i:
            for b in iter(lambda: i.read(1 << 20), b''): h.update(b)
        if h.hexdigest() != sha: continue
        tmp = os.path.join(ROMS, sha + '.neo.gz.part')
        with open(p, 'rb') as i, gzip.open(tmp, 'wb', 6) as o: shutil.copyfileobj(i, o, 1 << 20)
        os.replace(tmp, os.path.join(ROMS, sha + '.neo.gz')); log('rom archived', f, sha[:12]); return
    log('rom NOT archived (not in the builds any more)', sha[:12])


def worker():
    while True:
        try: bid = jobs.get(timeout=3600)
        except queue.Empty: bid = None
        try:
            backup()
            if bid and bid.startswith('rom:'): archive_rom(bid[4:])
            elif bid: transcribe_bundle(bid)
        except Exception as e: log('worker', bid, 'error', e)


def account(headers):
    """who is asking: the Oros user behind the player's token (Authorization: Bearer) or the Lab's cookie, checked
    with Oros's /api/whoami (cached 5 min); None = nobody signed in (ssh on localhost: the caller's own "by")"""
    auth = headers.get('Authorization', '')
    key, hdr = (auth, {'Authorization': auth}) if auth.startswith('Bearer ') else (headers.get('Cookie', ''), {'Cookie': headers.get('Cookie', '')})
    if not key: return None
    hit = ACCOUNTS.get(key)
    if hit and hit[1] > time.time(): return hit[0]
    try:
        with urllib.request.urlopen(urllib.request.Request(WHOAMI, headers=hdr), timeout=5) as r:
            name = json.load(r).get('username') or None
    except Exception: name = None
    if name:
        if len(ACCOUNTS) > 1000: ACCOUNTS.clear()
        ACCOUNTS[key] = (name, time.time() + 300)
    return name


def claim(user, install):
    """notes sent from this install before the login (no user) become this account's"""
    if not user or not INSTALL.match(install or ''): return
    with lock, db() as c:
        n = c.execute("UPDATE feedback SET user=? WHERE user IN ('', 'legacy') AND install_id=?", (user, install)).rowcount
        c.execute("UPDATE transcriptions SET user=? WHERE (user IS NULL OR user='legacy') AND install_id=?", (user, install))
    if n: log('claimed', n, 'notes of install', install[:8], 'for', user)


def row_dict(r): return {k: r[k] for k in r.keys()}


def replies(c, fid):
    """a note's thread, oldest first"""
    return [row_dict(x) for x in c.execute('SELECT * FROM replies WHERE feedback_id=? ORDER BY id', (fid,))]


def scenario(c, fid):
    """the note's test scenario: {title, do, expect, ...} (the recipe, scenario.py) or None"""
    r = c.execute('SELECT recipe FROM scenarios WHERE feedback_id=?', (fid,)).fetchone()
    try: return json.loads(r['recipe']) if r else None
    except ValueError: return None


def scenario_builds(c, fid):
    """the builds a state exists for: ["<rom sha>/<key>", ...] (key = the player's system, e.g. mvs-mvs)"""
    return [f"{r['rom_sha']}/{r['key']}" for r in c.execute('SELECT rom_sha, key FROM scenario_states WHERE feedback_id=? ORDER BY created', (fid,))]


def tests(c, fid):
    return [row_dict(x) for x in c.execute('SELECT * FROM tests WHERE feedback_id=? ORDER BY id', (fid,))]


TEST_TEXT = {'up': '👍 fixed', 'down': '👎 still broken', 'abandoned': 'left without a verdict'}


def timeline(c, fid, public=False):
    """the note's whole life, oldest first: [{at, by, kind, text, ref}] from the note itself (found), its status
    history (triaged / in_progress / fixed / shipped / verified / reopened ...), the events (commits, releases,
    scenario states, backfills), the test attempts and the replies. public: the player's own view (no IPs)"""
    r = c.execute('SELECT * FROM feedback WHERE id=?', (fid,)).fetchone()
    if not r: return []
    out = [{'at': r['created'], 'by': r['user'] or '-', 'kind': 'found',
            'text': f"note sent ({'voice' if r['audio_path'] else 'text'}): game v{r['game_version']}, player {r['apk_version']}, "
                    f"{r['device'] or '?'}" + (f", Android {r['android']}" if r['android'] else '')}]
    for h in c.execute('SELECT * FROM status_history WHERE feedback_id=? ORDER BY at', (fid,)):
        if not h['from_status'] and h['to_status'] == 'new': continue          # = found
        f, t, note = h['from_status'], h['to_status'], h['note'] or ''
        if f == t:
            kind = 'triaged' if note.startswith('set ') or re.search(r'TODO #\d+', note) else 'note'
            text = note
        else:
            kind = t if t in ('in_progress', 'fixed', 'shipped', 'verified', 'reopened', 'wont_do', 'duplicate', 'read') else 'status'
            text = f'{f} → {t}' + (': ' + note if note else '')
            if t == 'shipped': text = f"{f} → shipped" + (': ' + note if note else '')
        out.append({'at': h['at'], 'by': h['by'], 'kind': kind, 'text': text})
    for e in c.execute('SELECT * FROM events WHERE feedback_id=? ORDER BY at', (fid,)):
        out.append({'at': e['at'], 'by': e['by'], 'kind': e['kind'], 'text': e['text'], 'ref': e['ref']})
    for t in c.execute('SELECT * FROM tests WHERE feedback_id=? ORDER BY id', (fid,)):
        out.append({'at': t['at'], 'by': t['user'], 'kind': 'test', 'ref': t['attempt'] or '',
                    'text': f"test from the {t['source']} on game v{t['game_version'] or '?'} ({(t['rom_sha'] or '?')[:12]}, {t['system'] or '?'})"
                            f": {TEST_TEXT.get(t['result'], t['result'])}" + (f", {t['seconds']:.0f} s" if t['seconds'] else '') +
                            (f", replay {t['attempt']}" if t['attempt'] else '') + (f": {t['note']}" if t['note'] else '')})
    for x in c.execute('SELECT * FROM replies WHERE feedback_id=? ORDER BY id', (fid,)):
        if x['status_to']: continue                                           # a thumbs up / down: in the status history
        out.append({'at': x['at'], 'by': x['user'], 'kind': 'reply', 'ref': x['audio_path'] or '',
                    'text': ('voice reply' if x['kind'] == 'voice' else 'reply') + (': ' + x['text'] if x['text'] else '')})
    out.sort(key=lambda e: e['at'] or '')
    return out


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
        if u.path == '/mine' or u.path.startswith('/mine/'): return self.mine(u.path.split('/')[2:])
        if u.path == '/dlauth': return self.dlauth()
        if not u.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        parts = u.path.split('/')[2:]
        with db() as c:
            if parts == ['list']:
                sql, args = ('SELECT f.*, (SELECT ROUND(SUM(cost_usd), 6) FROM transcriptions t WHERE t.feedback_id = f.id) AS cost_usd, '
                             '(SELECT GROUP_CONCAT(cost_source) FROM transcriptions t WHERE t.feedback_id = f.id) AS cost_source FROM feedback f'), []
                conds = []
                for k in ('status', 'category'):
                    if q.get(k): conds.append(f'{k}=?'); args.append(q[k][0])
                if conds: sql += ' WHERE ' + ' AND '.join(conds)
                rows = [row_dict(r) for r in c.execute(sql + ' ORDER BY created DESC', args)]
                for r in rows:
                    r['replies'] = replies(c, r['id']); r['scenario'] = scenario(c, r['id'])
                    r['scenario_builds'] = scenario_builds(c, r['id']); r['timeline'] = timeline(c, r['id'])
                tot = c.execute("SELECT COUNT(*) n, ROUND(SUM(cost_usd), 6) usd, ROUND(SUM(CASE WHEN feedback_id != '' THEN cost_usd ELSE 0 END), 6) linked, "
                                "ROUND(SUM(audio_seconds), 1) secs FROM transcriptions").fetchone()
                return self.reply(200, {'rows': rows, 'statuses': STATUSES, 'categories': CATEGORIES[1:], 'user': account(self.headers),
                                        'cost': {'transcriptions': tot['n'], 'usd': tot['usd'] or 0, 'usd_in_notes': tot['linked'] or 0,
                                                 'audio_seconds': tot['secs'] or 0, 'prices': prices()}})
            if len(parts) == 2 and parts[0] == 'item' and ID.match(parts[1]):
                r = c.execute('SELECT * FROM feedback WHERE id=?', (parts[1],)).fetchone()
                if not r: return self.reply(404, {'error': 'no such feedback'})
                hist = [row_dict(h) for h in c.execute('SELECT * FROM status_history WHERE feedback_id=? ORDER BY at', (parts[1],))]
                txs = [row_dict(t) for t in c.execute('SELECT * FROM transcriptions WHERE feedback_id=? ORDER BY at', (parts[1],))]
                d = os.path.join(BUNDLES, parts[1])
                return self.reply(200, {'row': row_dict(r), 'history': hist, 'transcriptions': txs, 'replies': replies(c, parts[1]),
                                        'files': sorted(os.listdir(d)) if os.path.isdir(d) else [], 'timeline': timeline(c, parts[1]),
                                        'tests': tests(c, parts[1]), 'scenario': scenario(c, parts[1]), 'scenario_builds': scenario_builds(c, parts[1])})
            if len(parts) == 2 and parts[0] == 'scenario' and ID.match(parts[1]):
                return self.reply(200, {'id': parts[1], 'recipe': scenario(c, parts[1]), 'states': [row_dict(x) for x in c.execute(
                    'SELECT * FROM scenario_states WHERE feedback_id=? ORDER BY created', (parts[1],))]})
        if parts == ['select_layout']:
            p = os.path.join(DATA, 'select_layout.json')
            return self.reply(200, body=open(p, 'rb').read()) if os.path.exists(p) else self.reply(404, {'error': 'no layout saved'})
        if len(parts) == 2 and parts[0] == 'rom' and SHA.match(parts[1]):
            p = os.path.join(ROMS, parts[1] + '.neo.gz')
            if not os.path.exists(p): return self.reply(404, {'error': 'build not archived'})
            n = os.path.getsize(p)
            self.send_response(200); self.send_header('Content-Type', 'application/octet-stream'); self.send_header('Content-Encoding', 'gzip')
            self.send_header('Cache-Control', 'private, max-age=31536000, immutable'); self.send_header('Content-Length', str(n)); self.end_headers()
            with open(p, 'rb') as f:
                for b in iter(lambda: f.read(1 << 20), b''): self.wfile.write(b)
            return
        if len(parts) == 4 and parts[0] == 'scenario' and ID.match(parts[1]) and SHA.match(parts[2]) and SFILE.match(parts[3]):
            p = os.path.join(SCENARIOS, parts[1], parts[2], parts[3])
            if os.path.exists(p): return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
        if len(parts) == 3 and parts[0] == 'attempt' and re.match(r'^[0-9a-z-]{8,40}$', parts[1]) and NAME.match(parts[2]):
            p = os.path.join(ATTEMPTS, parts[1], parts[2])
            if os.path.exists(p): return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
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
        commit = str(req.get('commit') or '').strip()
        if commit and not re.match(r'^[0-9a-f]{7,40}$', commit): return 'commit: a git sha (hex)'
        if st == 'fixed' and not commit: return 'fixed needs the commit (fb.py status ID fixed --commit SHA)'
        c.execute('UPDATE feedback SET status=?, release=?, duplicate_of=?, fix_commit=?, updated=? WHERE id=?',
                  (st, rel if st == 'shipped' else r['release'], dup if st == 'duplicate' else r['duplicate_of'],
                   commit or r['fix_commit'] or '', now(), r['id']))
        note = req.get('note', '')
        if commit: note = (note + '; ' if note else '') + 'commit ' + commit
        if st == 'shipped' and rel and f'in {rel}' not in note: note = (note + '; ' if note else '') + 'release ' + rel
        c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (r['id'], now(), r['status'], st, by, note))

    @staticmethod
    def set_fields(c, r, req, by):
        cat = req.get('category', r['category'])
        if cat not in CATEGORIES: return 'category: one of ' + ', '.join(CATEGORIES[1:])
        fighters = ','.join(f.strip().lower() for f in str(req.get('fighters', r['fighters'])).split(',') if f.strip())
        title = ' '.join(str(req.get('title', r['title']) or '').split())
        if len(title) > 70: return f'title: one line of at most 70 characters ({len(title)} given)'
        todo = ','.join(t.strip().lstrip('#') for t in str(req.get('todo', r['todo']) or '').split(',') if t.strip())
        if todo and not re.match(r'^\d+(,\d+)*$', todo): return 'todo: TODO item numbers, e.g. 166 or 163,173'
        fix = ' '.join(str(req.get('fix', r['fix']) or '').split()); rca = ' '.join(str(req.get('rca', r['rca']) or '').split())
        if len(fix) > 400 or len(rca) > 400: return 'fix / rca: one or two sentences (<= 400 characters)'
        c.execute('UPDATE feedback SET category=?, fighters=?, notes=?, title=?, todo=?, fix=?, rca=?, updated=? WHERE id=?',
                  (cat, fighters, req.get('notes', r['notes']), title, todo, fix, rca, now(), r['id']))
        changed = [f'{k}={v}' for k, v in (('category', cat), ('fighters', fighters)) if v != r[k]]
        if fix != (r['fix'] or ''): changed.append(f'fix: "{fix}"')
        if rca != (r['rca'] or ''): changed.append(f'root cause: "{rca}"')
        if todo != (r['todo'] or ''): changed.append('TODO #' + ', #'.join(todo.split(',')) if todo else 'TODO -')
        if 'notes' in req and req['notes'] != r['notes']: changed.append('notes')
        if title != (r['title'] or ''): changed.append(f'title: "{title}"')
        if changed: c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (r['id'], now(), r['status'], r['status'], by, 'set ' + ' '.join(changed)))

    @staticmethod
    def set_scenario(c, r, req, by):
        """the note's test recipe (scenario.py put): title, do, expect, setup, do_keys ..."""
        rec = req.get('recipe')
        if not isinstance(rec, dict) or not all(isinstance(rec.get(k), str) and rec.get(k) for k in ('title', 'do', 'expect')):
            return 'recipe: an object with title, do and expect'
        old = c.execute('SELECT recipe FROM scenarios WHERE feedback_id=?', (r['id'],)).fetchone()
        new = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        if old and old['recipe'] == new: return None
        c.execute('INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?)', (r['id'], new, now(), by))
        c.execute('INSERT INTO events (feedback_id, at, by, kind, text, ref) VALUES (?,?,?,?,?,?)',
                  (r['id'], now(), by, 'scenario', ('test recipe changed: ' if old else 'test recipe written: ') + rec['title'], now()))

    @staticmethod
    def add_state(c, r, req, by):
        """scenario.py upload: the states of build rom_sha are in DATA/scenarios/<id>/<sha>/ (rsync), one row per key"""
        sha, keys = req.get('rom_sha', ''), req.get('keys') or []
        if not SHA.match(sha) or not keys or not all(SKEY.match(k) for k in keys): return 'rom_sha + keys'
        d = os.path.join(SCENARIOS, r['id'], sha)
        missing = [k for k in keys if not os.path.exists(os.path.join(d, k + '.state'))]
        if missing: return 'not uploaded: ' + ', '.join(missing)
        shas = req.get('state_sha256') or {}
        for k in keys:
            c.execute('INSERT OR REPLACE INTO scenario_states VALUES (?,?,?,?,?,?,?)', (r['id'], sha, k, req.get('version', ''), shas.get(k, ''), now(), by))
        c.execute('INSERT OR REPLACE INTO events (feedback_id, at, by, kind, text, ref) VALUES (?,?,?,?,?,?)',
                  (r['id'], now(), by, 'scenario', f"test state generated on game v{req.get('version') or '?'} ({sha[:12]}): " + ', '.join(keys), sha))
        jobs.put('rom:' + sha)                               # the Lab's Test it loads that build: archived

    @staticmethod
    def add_event(c, r, req, by):
        """a timeline event (backfill_history.py: commits, releases); idempotent on (kind, ref)"""
        kind, at = str(req.get('kind') or ''), str(req.get('at') or now())
        if not re.match(r'^[a-z_]{2,20}$', kind) or not re.match(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$', at): return 'kind + at (UTC ISO)'
        c.execute('INSERT OR REPLACE INTO events (feedback_id, at, by, kind, text, ref) VALUES (?,?,?,?,?,?)',
                  (r['id'], at, by, kind, str(req.get('text') or '')[:500], str(req.get('ref') or '')[:80]))
        for k in ('todo', 'fix_commit'):
            if req.get(k) and not r[k]: c.execute(f'UPDATE feedback SET {k}=? WHERE id=?', (str(req[k])[:80], r['id']))

    @staticmethod
    def lab_test(c, r, req, by):
        """a test attempt from the Lab's Feedback tab: up / down also set verified / reopened"""
        res = req.get('result')
        if res not in TEST_RESULTS: return 'result: ' + ', '.join(TEST_RESULTS)
        c.execute('INSERT INTO tests (feedback_id, at, user, source, result, rom_sha, game_version, system, note, seconds) VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (r['id'], now(), by, 'lab', res, req.get('rom_sha', ''), req.get('game_version', ''), req.get('system', ''),
                   str(req.get('note') or '')[:2000], req.get('seconds')))
        to = {'up': 'verified', 'down': 'reopened'}.get(res)
        if to and to != r['status']:
            c.execute('UPDATE feedback SET status=?, updated=? WHERE id=?', (to, now(), r['id']))
            c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (r['id'], now(), r['status'], to, by,
                      ('thumbs up in the Lab: verified fixed' if res == 'up' else 'thumbs down in the Lab: still broken') + (': ' + req['note'] if req.get('note') else '')))

    def dlauth(self):
        """nginx auth_request for the builds (/brawler/download/): 204 = an Oros token or cookie; or, while
        LEGACY_FLAG exists, a player older than 0.0.15 (X-App-Version < 0.0.15; its 5 s poll of latest.json sends only
        X-Install-Id, no version and no token)"""
        if account(self.headers): return self.reply(204, body=b'')
        h = self.headers
        if os.path.exists(LEGACY_FLAG) and not h.get('Authorization') and (
                old_player(h.get('X-App-Version', '')) or (not h.get('X-App-Version') and INSTALL.match(h.get('X-Install-Id', '')))):
            return self.reply(204, body=b'')
        self.reply(401, {'error': 'sign in with your Oros account'})

    # ---- the player's own notes (signed in) ---------------------------------------------------------------------
    def player(self, legacy=False):
        """the signed-in account of a player call, or None (401 sent). Transition (until LEGACY_FLAG is removed):
        a player older than 0.0.15 (no login yet) may still upload and transcribe, logged as user 'legacy'"""
        user = account(self.headers)
        if not user and legacy and os.path.exists(LEGACY_FLAG) and old_player(self.headers.get('X-App-Version', '')):
            return 'legacy'
        if not user: self.reply(401, {'error': 'sign in with your Oros account'}); return None
        claim(user, self.headers.get('X-Install-Id', ''))
        return user

    def who(self, user):
        """who sent this and from where: the account (or 'legacy'), the install, the client's address as nginx saw
        it (X-Real-IP, set by the proxy over anything the client sent) and its user agent"""
        inst = self.headers.get('X-Install-Id', '')
        return {'user': user, 'install_id': inst if INSTALL.match(inst) else None,
                'ip': self.headers.get('X-Real-IP') or None, 'user_agent': self.headers.get('User-Agent') or None}

    def mine(self, parts):
        user = self.player()
        if not user: return
        with db() as c:
            if not parts or parts == ['']:
                rows = [row_dict(r) for r in c.execute('SELECT id, created, apk_version, game_version, title, final_text, raw_transcript, category, '
                        'fighters, status, release, duplicate_of, notes, updated, audio_path, marked, device, android, install_id, ip, fix, rca FROM feedback WHERE user=? ORDER BY created DESC', (user,))]
                for r in rows:
                    r['history'] = [row_dict(h) for h in c.execute('SELECT at, from_status, to_status, by, note FROM status_history '
                                                                   'WHERE feedback_id=? ORDER BY at', (r['id'],))]
                    d = os.path.join(BUNDLES, r['id'])
                    r['replies'] = [{k: x[k] for k in ('id', 'at', 'kind', 'text', 'audio_path', 'status_from', 'status_to', 'device', 'apk_version')}
                                    for x in replies(c, r['id'])]
                    r['screen'] = 'screen_marked.png' if os.path.exists(os.path.join(d, 'screen_marked.png')) else 'screen.png' if os.path.exists(os.path.join(d, 'screen.png')) else ''
                    sc = scenario(c, r['id'])                          # Player 0.0.22: TEST IT (older players ignore these)
                    r['scenario'] = {k: sc.get(k, '') for k in ('title', 'do', 'expect')} if sc else None
                    r['scenario_builds'] = scenario_builds(c, r['id']) if sc else []
                    r['timeline'] = [{k: e.get(k, '') for k in ('at', 'by', 'kind', 'text')} for e in timeline(c, r['id'], True)]
                return self.reply(200, {'user': user, 'rows': rows})
            if len(parts) == 4 and parts[0] == 'scenario' and ID.match(parts[1]) and SHA.match(parts[2]) and SFILE.match(parts[3]):
                if not c.execute('SELECT 1 FROM feedback WHERE id=? AND user=?', (parts[1], user)).fetchone(): return self.reply(404, {'error': 'not found'})
                p = os.path.join(SCENARIOS, parts[1], parts[2], parts[3])
                if not os.path.exists(p): return self.reply(404, {'error': 'no test state for this build'})
                return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
            if len(parts) == 3 and parts[0] == 'file' and ID.match(parts[1]) and NAME.match(parts[2]) and not parts[2].endswith('.state'):
                if c.execute('SELECT 1 FROM feedback WHERE id=? AND user=?', (parts[1], user)).fetchone():
                    p = os.path.join(BUNDLES, parts[1], parts[2])
                    if os.path.exists(p):
                        return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
        self.reply(404, {'error': 'not found'})

    # ---- POST ---------------------------------------------------------------------------------------------------
    def do_POST(self):
        if self.path == '/transcribe': return self.transcribe()
        if self.path == '/upload': return self.upload()
        if self.path == '/reply': return self.post_reply()
        if self.path == '/test': return self.post_test()
        if not self.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        if self.path == '/api/status': return self.change(self.set_status)
        if self.path == '/api/set': return self.change(self.set_fields)
        if self.path == '/api/scenario': return self.change(self.set_scenario)
        if self.path == '/api/scenario_state': return self.change(self.add_state)
        if self.path == '/api/event': return self.change(self.add_event)
        if self.path == '/api/test': return self.change(self.lab_test)
        if self.path == '/api/select_layout': return self.save_layout()
        self.reply(404, {'error': 'not found'})

    def save_layout(self):
        """the Lab's Select screen tab: {layout: {fighter: {x, y, z, facing, pose, slot}}, game_version?} (build_tables.py
        select_layout checks it fully when select_layout.py pulls it; here only its shape)"""
        b = self.body(1 << 16)
        try: req = json.loads(b or b'')
        except ValueError: return self.reply(400, {'error': 'json'})
        L = req.get('layout') if isinstance(req, dict) else None
        ok = isinstance(L, dict) and 0 < len(L) <= 64 and all(
            isinstance(k, str) and re.match(r'^[a-z0-9_]{1,24}$', k) and isinstance(v, dict) and set(v) == {'x', 'y', 'z', 'facing', 'pose', 'slot'}
            and all(isinstance(v[f], int) for f in ('x', 'y', 'z', 'slot')) and v['facing'] in ('left', 'right')
            and isinstance(v['pose'], list) and len(v['pose']) == 2 and all(isinstance(x, int) for x in v['pose']) for k, v in L.items())
        if not ok: return self.reply(400, {'error': 'layout: {fighter: {x, y, z, facing, pose, slot}}'})
        doc = {'layout': L, 'saved': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'by': account(self.headers) or 'ssh',
               'game_version': str(req.get('game_version', ''))[:20]}
        with lock:
            p = os.path.join(DATA, 'select_layout.json')
            if os.path.exists(p):
                h = os.path.join(DATA, 'select_layout'); os.makedirs(h, exist_ok=True)
                os.replace(p, os.path.join(h, time.strftime('%Y%m%d-%H%M%S', time.gmtime()) + '.json'))
            with open(p + '.tmp', 'w') as f: json.dump(doc, f, indent=1)
            os.replace(p + '.tmp', p)
        log('select layout saved by', doc['by'], len(L), 'fighters')
        self.reply(200, {'ok': True, 'saved': doc['saved'], 'by': doc['by']})

    def transcribe(self):
        user = self.player(legacy=True)
        if not user: return
        data = self.body(MAX_AUDIO)
        if data is None: return self.reply(413, {'error': 'size'})
        name = self.headers.get('X-Audio-Name', 'audio.m4a')
        if not NAME.match(name): name = 'audio.m4a'
        t0 = time.time()
        try: text, model, dt, usage = openai_transcribe(name, data)
        except RuntimeError as e: return self.reply(502, {'error': 'transcription unavailable'})
        tx, usd = log_tx(model, usage, audio_seconds(data=data), '', 'player', who=self.who(user))
        log('transcribe (player)', user, len(data), 'bytes', model, f'{time.time() - t0:.1f}s', len(text), 'chars', f'${usd:.5f}', json.dumps(usage))
        self.reply(200, {'text': text, 'model': model, 'seconds': dt, 'tx_id': tx})

    def upload(self):
        user = self.player(legacy=True)
        if not user: return
        who = self.who(user)
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
                      'audio_path, bundle_path, status, updated, transcript_model, user, install_id, marked, ip, user_agent, android) '
                      'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (bid, meta.get('created') or now(), meta.get('app_version', ''), meta.get('rom_version', ''), meta.get('rom_sha256', ''),
                       meta.get('device', ''), raw, meta.get('final_text', ''), audio, d, 'new', now(), meta.get('transcript_model', ''),
                       user, self.headers.get('X-Install-Id', '') if INSTALL.match(self.headers.get('X-Install-Id', '')) else '',
                       '1' if os.path.exists(os.path.join(d, 'screen_marked.png')) else '', who['ip'], who['user_agent'], meta.get('android')))
            c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (bid, now(), '', 'new', user, meta.get('kind', '')))
        tx = meta.get('transcribe_tx', '')
        if tx and re.match(r'^[0-9a-f]{16}$', tx):
            with lock, db() as c: c.execute("UPDATE transcriptions SET feedback_id=? WHERE tx_id=? AND feedback_id=''", (bid, tx))
        elif audio and raw:                                   # an older player sends no tx_id: its transcription is the
            secs = audio_seconds(path=os.path.join(d, audio))  # unlinked one of the same duration, else an estimate
            with lock, db() as c:
                t = c.execute("SELECT tx_id FROM transcriptions WHERE feedback_id='' AND by='player' AND ABS(audio_seconds - ?) < 0.05 "
                              "ORDER BY at DESC LIMIT 1", (secs or -1,)).fetchone()
                if t: c.execute('UPDATE transcriptions SET feedback_id=? WHERE tx_id=?', (bid, t['tx_id']))
            if not t: log_tx(meta.get('transcript_model') or MODELS[0], None, secs, bid, 'estimate')
        if audio and not raw: jobs.put(bid)
        jobs.put('rom:' + meta.get('rom_sha256', ''))
        log('bundle', bid, user, len(body), 'bytes', meta.get('device'), meta.get('app_version'), 'text' if meta.get('final_text') else 'no text')
        self.reply(200, {'id': bid})

    def post_reply(self):
        """a reply to one of the signed-in user's notes (no legacy access: Player 0.0.17+)"""
        import base64
        user = self.player()
        if not user: return
        b = self.body(MAX_REPLY)
        if b is None: return self.reply(413, {'error': 'size'})
        try: req = json.loads(b)
        except ValueError: return self.reply(400, {'error': 'json'})
        fid, kind = req.get('id', ''), req.get('kind', '')
        text = str(req.get('text') or '').strip()[:4000]
        if not ID.match(fid) or kind not in REPLY_KINDS: return self.reply(400, {'error': 'id + kind (' + ', '.join(REPLY_KINDS) + ')'})
        try: audio = base64.b64decode(req['audio_b64'], validate=True) if req.get('audio_b64') else b''
        except ValueError: return self.reply(400, {'error': 'audio_b64'})
        if len(audio) > MAX_AUDIO: return self.reply(413, {'error': 'size'})
        if kind == 'voice' and not audio: return self.reply(400, {'error': 'a voice reply needs its audio'})
        if kind == 'text' and not text: return self.reply(400, {'error': 'an empty reply'})
        ext = (req.get('audio_name') or 'a.m4a').rsplit('.', 1)[-1]
        if ext not in ('m4a', 'wav', 'mp3', 'ogg'): ext = 'm4a'
        w = self.who(user)
        with lock, db() as c:
            r = c.execute('SELECT * FROM feedback WHERE id=? AND user=?', (fid, user)).fetchone()
            if not r: return self.reply(404, {'error': 'no such note of yours'})
            to = {'up': 'verified', 'down': 'reopened'}.get(kind, '')
            cur = c.execute('INSERT INTO replies (feedback_id, at, user, kind, text, raw_transcript, status_from, status_to, apk_version, '
                            'install_id, device, android, ip, user_agent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (fid, now(), user, kind, text, str(req.get('raw_transcript') or '')[:4000], r['status'] if to else '', to,
                             self.headers.get('X-App-Version'), w['install_id'], str(req.get('device') or '')[:80] or None,
                             str(req.get('android') or '')[:40] or None, w['ip'], w['user_agent']))
            rid = cur.lastrowid
            if audio:
                name = f'reply_{rid}.{ext}'
                with open(os.path.join(BUNDLES, fid, name), 'wb') as f: f.write(audio)
                c.execute('UPDATE replies SET audio_path=? WHERE id=?', (name, rid))
            if to:
                c.execute('UPDATE feedback SET status=?, updated=? WHERE id=?', (to, now(), fid))
                c.execute('INSERT INTO status_history VALUES (?,?,?,?,?,?)', (fid, now(), r['status'], to, user,
                          ('thumbs up: verified fixed' if kind == 'up' else 'thumbs down: still broken') + (': ' + text if text else '')))
            else:
                c.execute('UPDATE feedback SET updated=? WHERE id=?', (now(), fid))
            tx = req.get('tx_id', '')
            if tx and re.match(r'^[0-9a-f]{16}$', tx):
                c.execute("UPDATE transcriptions SET feedback_id=? WHERE tx_id=? AND feedback_id=''", (fid, tx))
            out = {'reply': row_dict(c.execute('SELECT * FROM replies WHERE id=?', (rid,)).fetchone()),
                   'row': row_dict(c.execute('SELECT * FROM feedback WHERE id=?', (fid,)).fetchone())}
        log('reply', fid, rid, user, kind, (r['status'] + ' -> ' + to) if to else '', len(audio), 'bytes audio', len(text), 'chars')
        self.reply(200, out)

    def post_test(self):
        """Player 0.0.22: a test attempt of one of the user's notes, a zip: test.json {id, result (up / down / abandoned),
        rom_sha, game_version, system, seconds?, reply_id? (the thumbs reply it went with), note?, device?} + optionally
        the replay of the attempt (the feedback bundle's files: snap_*.state, inputs.bin, press.state, screen.png, meta.json),
        unpacked into DATA/attempts/<attempt id>/"""
        user = self.player()
        if not user: return
        body = self.body(MAX_BODY)
        if body is None: return self.reply(413, {'error': 'size'})
        try: z = zipfile.ZipFile(io.BytesIO(body)); infos = z.infolist(); t = json.loads(z.read('test.json'))
        except Exception: return self.reply(400, {'error': 'a zip with test.json'})
        if any(not NAME.match(i.filename) for i in infos) or sum(i.file_size for i in infos) > MAX_UNPACKED:
            return self.reply(400, {'error': 'unexpected content'})
        fid, res = t.get('id', ''), t.get('result')
        if not ID.match(fid) or res not in TEST_RESULTS: return self.reply(400, {'error': 'id + result (' + ', '.join(TEST_RESULTS) + ')'})
        w = self.who(user)
        aid = ''
        if any(i.filename != 'test.json' for i in infos):
            aid = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
            d = os.path.join(ATTEMPTS, aid); os.makedirs(d)
            for i in infos:
                with open(os.path.join(d, i.filename), 'wb') as f: f.write(z.read(i))
        with lock, db() as c:
            r = c.execute('SELECT * FROM feedback WHERE id=? AND user=?', (fid, user)).fetchone()
            if not r: return self.reply(404, {'error': 'no such note of yours'})
            rid = t.get('reply_id') if isinstance(t.get('reply_id'), int) else None
            secs = t.get('seconds') if isinstance(t.get('seconds'), (int, float)) else None
            cur = c.execute('INSERT INTO tests (feedback_id, at, user, source, result, rom_sha, game_version, system, apk_version, device, reply_id, '
                            'attempt, seconds, note, ip) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (fid, now(), user, 'player', res, str(t.get('rom_sha') or '')[:64], str(t.get('game_version') or '')[:20],
                             str(t.get('system') or '')[:10], self.headers.get('X-App-Version') or '', str(t.get('device') or '')[:80],
                             rid, aid, secs, str(t.get('note') or '')[:2000], w['ip']))
            out = row_dict(c.execute('SELECT * FROM tests WHERE id=?', (cur.lastrowid,)).fetchone())
        if aid: jobs.put('rom:' + str(t.get('rom_sha') or ''))
        log('test', fid, user, res, aid or 'no replay')
        self.reply(200, {'test': out})

    def log_message(self, fmt, *a): pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    os.makedirs(BUNDLES, exist_ok=True); os.makedirs(SCENARIOS, exist_ok=True); os.makedirs(ATTEMPTS, exist_ok=True); db_init(); backfill()
    try: backfill_origin()
    except Exception as e: log('backfill origin failed:', e)
    threading.Thread(target=worker, daemon=True).start()
    with db() as c:                                          # transcripts missed while down
        for r in c.execute("SELECT id FROM feedback WHERE audio_path != '' AND raw_transcript = ''"): jobs.put(r['id'])
        for r in c.execute("SELECT DISTINCT rom_sha FROM feedback"): jobs.put('rom:' + r['rom_sha'])
    log('listening on 127.0.0.1:%d, data %s' % (PORT, DATA))
    Server(('127.0.0.1', PORT), H).serve_forever()
