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
                     carry "scenario" {title, do, expect}, "scenario_builds" ["<sha>/<key>"] and "timeline"; (0.0.23) every
                     row of /mine and /api/list carries "to_test" + "tested_on" (queue_info: the test queue's rule)
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
Decisions (reviews, Player 0.0.24; docs/feedback.md "Decisions"): a visual choice put to Bruno (before / after of a fix, a
pick between options, one picture to ship or not), stored in the reviews table + review_history, its images in
DATA/reviews/<id>/. kind before_after (answers "Ship AFTER" / "Stay with BEFORE" / "Needs work"), pick (the options given,
else the image labels), single ("Ship it" / "Needs work"); status open -> answered (a new answer replaces the last one,
the history keeps every one); each linked note gets "decision" events in its timeline.
  POST /api/review {title, question, kind, images: [{label, name, b64}], options?, todo?, notes?, audience?, by?}   fb.py review add
  GET  /api/reviews[?status=open|answered]  GET /api/review/<id>  GET /api/review/<id>/file/<name>
  POST /api/review_answer {id, answer, text?, source?, by?}   the Lab's Decisions filter (the signed-in user); over ssh
                                                (fb.py review answer) an answer he gave elsewhere: source artifact | chat
  POST /api/review_delete {id}                  the row, its history, its files and its events on the linked notes
  GET  /mine -> "reviews": the decisions put to the signed-in user (audience = the user, or '' = every account)
  GET  /mine/review/<id>/<name>                 an image or an answer's voice
  POST /review {id, answer, text, raw_transcript?, tx_id?, audio_b64?, audio_name?, device?, android?}   the player's answer
Character Lab (docs/character_lab.md "Character Lab"; 2026-10-10): the live config of each fighter + the catalogue of the Lab shell
and the character packs, in LAB (/data/brawler/lab). The same handlers answer /lab/... (the player: nginx /brawler/lab/,
X-Public, the Oros token) and /api/lab/... (the web pages: /brawler-lab/feedback-api/lab/, the Oros cookie; ssh on localhost
= user 'ssh', labcfg.py / labpub.py). Reads: any signed-in account; writes: Oros role admin (403 otherwise).
  GET  lab/me                        {user, role}: who the pages are (Send to Player and Revert need the role admin)
  GET  lab/config                    every fighter's live config head {fighter, version, hash, updated, by, size, note}
  GET  lab/config/<f>                the live config {fighter, version, hash, updated, by, size, note, blob (base64, opaque),
                                     json}; ETag "v<version>-<hash16>"
  GET  lab/config/<f>/hash           {hash, version, updated}: the 2-3 s poll; ETag "<hash>", If-None-Match -> 304
  PUT  lab/config/<f>                {blob, json, hash?, note?} (POST too); hash = sha256 of the blob bytes (checked when
                                     given); If-Match "<hash>" -> 412 when the live one differs; an unchanged blob + json = no
                                     new revision -> {head..., changed}
  GET  lab/config/<f>/history        every revision's head; GET lab/config/<f>/rev/<n> one revision in full
  POST lab/config/<f>/revert {rev, note?}   a new revision with revision <rev>'s blob + json (reverted_from)
  GET  lab/catalogue                 {shell: {version, url, sha256, engine, size, published, format, features}, packs:
                                     [{fighter, display, face, version, url, sha256, engine, size, published, versions, format,
                                     needs, data_sha, all: [every version of his, newest first: version, url, sha256, size,
                                     engine, format, needs, data_sha, published]}]}; ETag, If-None-Match -> 304. THE PACK
                                     FORMAT (docs/character_lab.md): a pack loads into a shell of its format whose features
                                     cover its needs (the Player / the pages pick his newest such pack from `all`)
  POST lab/ship/<f> {rev?, note?}   NO STAGING (Bruno 2026-10-10: "forget about staging, remove that step"): what the
                                     Assembly saves IS the game. Every live send of a sheet queues {id, fighter, rev, hash, by,
                                     at, note, status pending} in LAB/ship.json; the desktop's worker (labcfg.py ship-worker)
                                     ships a fighter once his newest request is 60 s old (the older ones: dropped, superseded):
                                     arb_compile -> build -> checks -> VERSION bump -> publish
  GET  lab/ship[?status=...][&fighter=f]  the queue; POST lab/ship_done {id, status building | done | failed | dropped,
                                     note?} (the worker; the sheet's "In the game" line reads it)
  POST lab/publish {kind shell|pack|face, fighter?, version, engine, src, sha256, display?, format?, features? (shell),
                    needs? + data_sha? (pack)}   labpub.py (the file in LAB/incoming)
  POST lab/unpublish {kind, fighter?, version?}
  Files: LAB/config/<f>.json (live) + <f>.history.jsonl (append-only, every revision in full); LAB/shell/<version><ext>,
  LAB/packs/<f>/<version>.pack (+ <version>.json sidecars), LAB/faces/<f>.png; served by nginx /brawler/lab/dl/ (Range).
Lifecycle (docs/feedback.md): every row's timeline = found + status history + events + tests + replies, oldest first.
Cost: every transcription's usage as OpenAI returns it (tokens, or seconds for whisper-1) and its USD cost from
PRICES (prices.json next to this file: the price table with its source and date) go to the transcriptions table,
linked to its note (the player sends the tx_id it got back; cancelled notes' transcriptions stay unlinked but count
in the total). Notes from before the cost log: estimated from the audio's duration (source 'duration').
Tracker: DATA/feedback.db (SQLite; feedback + status_history + transcriptions + replies), copied daily to DATA/backups/ (kept 14), mirrored to
the desktop by pull.py. The OpenAI key is read from KEY_FILE at each call; never logged, never stored."""
import base64, hashlib, http.server, io, json, mimetypes, os, queue, re, secrets, socketserver, sqlite3, threading, time
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
REVIEWS = os.path.join(DATA, 'reviews')                  # <review id>/ its images + the voices of its answers
REVIEW_KINDS = ('before_after', 'pick', 'single')       # the card's layout only: the buttons are always the decision's own
VAGUE = {'keep', 'change', 'yes', 'no', 'ok', 'okay', 'ship it', 'ship after', 'stay with before', 'needs work', 'approve', 'reject',
         'accept', 'good', 'bad', 'fine', 'other', 'neither', 'both', 'before', 'after', 'a', 'b', 'c', 'option a', 'option b'}
IMG = re.compile(r'^[a-z0-9_-]{1,60}\.(png|jpg|jpeg|gif|webp)$')
RFILE = re.compile(r'^([a-z0-9_-]{1,60}\.(png|jpg|jpeg|gif|webp)|answer_\d+\.(m4a|wav|mp3|ogg))$')
MAX_REVIEW = 48 << 20                                    # the create call: every image in base64
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
        CREATE INDEX IF NOT EXISTS events_fb ON events(feedback_id);
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, updated TEXT, by TEXT, audience TEXT DEFAULT '',
            title TEXT, question TEXT, kind TEXT, images TEXT, options TEXT, todo TEXT DEFAULT '', notes TEXT DEFAULT '',
            status TEXT DEFAULT 'open', answer TEXT DEFAULT '', answer_text TEXT DEFAULT '', answer_raw TEXT DEFAULT '',
            answer_audio TEXT DEFAULT '', answered_at TEXT DEFAULT '', answered_by TEXT DEFAULT '', answer_source TEXT DEFAULT '',
            answer_origin TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS review_history (
            review_id INTEGER, at TEXT, by TEXT, kind TEXT, text TEXT DEFAULT '', audio TEXT DEFAULT '');
        CREATE INDEX IF NOT EXISTS review_history_id ON review_history(review_id);''')
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
    return account_role(headers)[0]


def account_role(headers):
    """(user, role) behind the token / cookie (role: Oros's, 'admin' or 'viewer'); (None, None) = nobody signed in"""
    auth = headers.get('Authorization', '')
    key, hdr = (auth, {'Authorization': auth}) if auth.startswith('Bearer ') else (headers.get('Cookie', ''), {'Cookie': headers.get('Cookie', '')})
    if not key: return None, None
    hit = ACCOUNTS.get(key)
    if hit and hit[2] > time.time(): return hit[0], hit[1]
    try:
        with urllib.request.urlopen(urllib.request.Request(WHOAMI, headers=hdr), timeout=5) as r:
            j = json.load(r); name, role = j.get('username') or None, j.get('role') or ''
    except Exception: name, role = None, None
    if name:
        if len(ACCOUNTS) > 1000: ACCOUNTS.clear()
        ACCOUNTS[key] = (name, role, time.time() + 300)
    return name, (role if name else None)


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


def vkey(v):
    """a version as a sortable tuple ('0.0.86' -> (0, 0, 86)); None when it is not one"""
    try: return tuple(int(x) for x in str(v).split('.')) if v else None
    except ValueError: return None


def queue_info(c, r):
    """the test queue rule (docs/feedback.md "The test queue"): a note waits for a test (to_test) while its status is
    shipped (with a release) and no verdict (a 👍 / 👎 test attempt, player or Lab) was given on that release or a later
    build: tested_on = the build of the last verdict. A verdict takes it out (👍 verified, 👎 reopened: it stays in Open);
    it comes back only when a later ship has a release > tested_on. An abandoned attempt is no verdict: it stays queued.
    The player adds "release <= the build he runs"."""
    t = c.execute("SELECT game_version FROM tests WHERE feedback_id=? AND result IN ('up', 'down') ORDER BY id DESC LIMIT 1", (r['id'],)).fetchone()
    tested = t['game_version'] if t else ''
    rel, tv = vkey(r['release']), vkey(tested)
    return {'tested_on': tested, 'to_test': bool(r['status'] == 'shipped' and rel and (tv is None or rel > tv))}


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


def check_review(question, imgs, opts):
    """Bruno's clarity rules for a decision (docs/feedback.md "Decisions"): -> the broken rule, or None"""
    q = ' '.join(question.split())
    if not q.endswith('?') or q.count('?') != 1 or re.search(r'[.!;]\s', q) or len(q) > 200:
        return 'question: ONE question, one sentence ending in "?" (<= 200 characters); the context goes into each button\'s effect'
    for i in imgs:
        lab = ' '.join(str(i.get('label') or '').split())
        if len(lab.split()) < 2 or len(lab) > 120:
            return f'image label "{lab}": say what it is, e.g. "BEFORE: 0.0.88, system font" (two words at least, <= 120)'
    if not isinstance(opts, list) or not 2 <= len(opts) <= 5: return 'options: 2 to 5 buttons, each LABEL=EFFECT'
    seen = set()
    for o in opts:
        if not isinstance(o, dict): return 'options: {label, effect}'
        lab = ' '.join(str(o.get('label') or '').split()); eff = ' '.join(str(o.get('effect') or '').split())
        bare = re.sub(r'[^a-z ]', '', lab.lower()).strip()
        if bare in VAGUE or len(lab.split()) < 2 or len(lab) > 70:
            return f'button "{lab}": name its exact outcome in game terms ("Ship Kizuna\'s font", "Keep the old font"), never Keep / Change / Yes / No alone (2 words at least, <= 70)'
        if not eff or len(eff) > 160: return f'button "{lab}": its effect = one line saying what changes in the game if he picks it (<= 160)'
        if lab.lower() in seen: return f'button "{lab}" twice'
        seen.add(lab.lower())
    return None


def review_dict(c, r, public=False):
    """a decision with its images, options, history; public: the player's view (no IPs)"""
    d = row_dict(r)
    for k in ('images', 'options'):
        try: d[k] = json.loads(d[k] or '[]')
        except ValueError: d[k] = []
    d['history'] = [row_dict(h) for h in c.execute('SELECT at, by, kind, text, audio FROM review_history WHERE review_id=? ORDER BY rowid', (r['id'],))]
    if public: d.pop('answer_origin', None)
    return d


def review_event(c, rv, by, text, ref):
    """a "decision" event on every note the decision is linked to (their timelines)"""
    for fid in [x for x in (rv['notes'] or '').split(',') if x]:
        if c.execute('SELECT 1 FROM feedback WHERE id=?', (fid,)).fetchone():
            c.execute('INSERT OR REPLACE INTO events (feedback_id, at, by, kind, text, ref) VALUES (?,?,?,?,?,?)',
                      (fid, now(), by, 'decision', text[:500], ref[:80]))


def answer_review(c, rid, user, answer, text, raw='', audio=b'', ext='m4a', source='player', origin=None):
    """-> (review dict, None) or (None, error); the caller holds the lock"""
    r = c.execute('SELECT * FROM reviews WHERE id=?', (rid,)).fetchone()
    if not r: return None, 'no such decision'
    labels = [o['label'] for o in json.loads(r['options'] or '[]')]
    if answer not in labels: return None, 'answer: one of ' + ' / '.join(labels)
    if answer.lower().startswith('needs work') and not text: return None, 'this answer needs your note: say or type what to change'
    at = now(); name = ''
    if audio:
        k = c.execute('SELECT COUNT(*) FROM review_history WHERE review_id=? AND audio != \'\'', (rid,)).fetchone()[0] + 1
        name = f'answer_{k}.{ext}'
        os.makedirs(os.path.join(REVIEWS, str(rid)), exist_ok=True)
        with open(os.path.join(REVIEWS, str(rid), name), 'wb') as f: f.write(audio)
    c.execute('UPDATE reviews SET status=?, answer=?, answer_text=?, answer_raw=?, answer_audio=?, answered_at=?, answered_by=?, answer_source=?, '
              'answer_origin=?, updated=? WHERE id=?', ('answered', answer, text, raw, name, at, user, source, json.dumps(origin or {}), at, rid))
    prev = f' (was: {r["answer"]})' if r['answer'] else ''
    c.execute('INSERT INTO review_history VALUES (?,?,?,?,?,?)', (rid, at, user, 'answered', f'{answer}{prev}' + (f': {text}' if text else ''), name))
    review_event(c, r, user, f'decision #{rid} "{r["title"]}" answered from the {source}: {answer}' + (f': {text}' if text else ''), f'review{rid}:{at}')
    return review_dict(c, c.execute('SELECT * FROM reviews WHERE id=?', (rid,)).fetchone()), None


# ---- Brawler Character Lab (docs/character_lab.md "Character Lab"): live config per fighter + the shell / pack catalogue ----
LAB = os.environ.get('FEEDBACK_LAB', '/data/brawler/lab')   # shell/ packs/<f>/ faces/ (nginx /brawler/lab/dl/), config/, incoming/
LAB_CFG = os.path.join(LAB, 'config')                       # <f>.json = the live config, <f>.history.jsonl = every revision
LAB_IN = os.path.join(LAB, 'incoming')                      # labpub.py's uploads, moved into place by /api/lab/publish
LAB_DL = '/brawler/lab/dl/'                                 # the download URLs (nginx alias, Range, behind the Oros login)
FIGHTER = re.compile(r'^[a-z0-9_]{1,24}$')
LVER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$')
LEXT = re.compile(r'^\.[a-z0-9]{1,8}$')
MAX_CFG = 4 << 20                                           # the PUT: the JSON + the blob in base64
lab_lock = threading.Lock()


def lab_current(f):
    p = os.path.join(LAB_CFG, f + '.json')
    return json.load(open(p)) if os.path.exists(p) else None


def lab_history(f):
    p = os.path.join(LAB_CFG, f + '.history.jsonl')
    if not os.path.exists(p): return []
    return [json.loads(l) for l in open(p) if l.strip()]


def lab_head(rec, extra=()):
    """a revision without its payload (blob, json)"""
    return {k: rec.get(k) for k in ('fighter', 'version', 'hash', 'updated', 'by', 'size', 'note', 'reverted_from') + tuple(extra) if k in rec}


def lab_store(f, blob, cfg, by, note='', reverted_from=None, expect=None):
    """a new revision when the blob or the JSON changed: appended to the history (fsync'd), then the live file
    replaced atomically -> (record, changed, error)"""
    h = hashlib.sha256(blob).hexdigest()
    with lab_lock:
        cur = lab_current(f)
        if expect is not None and (cur['hash'] if cur else '') != expect:
            return cur, False, 'precondition'
        if cur and cur['hash'] == h and cur['json'] == cfg and reverted_from is None: return cur, False, None
        rec = {'fighter': f, 'version': (cur['version'] if cur else 0) + 1, 'hash': h, 'updated': now(), 'by': by,
               'size': len(blob), 'note': note[:300], 'blob': base64.b64encode(blob).decode(), 'json': cfg}
        if reverted_from is not None: rec['reverted_from'] = reverted_from
        os.makedirs(LAB_CFG, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n'
        with open(os.path.join(LAB_CFG, f + '.history.jsonl'), 'a') as hf:
            hf.write(line); hf.flush(); os.fsync(hf.fileno())
        tmp = os.path.join(LAB_CFG, f + '.json.part')
        with open(tmp, 'w') as o: json.dump(rec, o, ensure_ascii=False)
        os.replace(tmp, os.path.join(LAB_CFG, f + '.json'))
    log('lab config', f, 'rev', rec['version'], rec['hash'][:12], len(blob), 'bytes by', by, ('revert to %d' % reverted_from) if reverted_from else '')
    return rec, True, None


def lab_ships():
    p = os.path.join(LAB, 'ship.json')
    return json.load(open(p)) if os.path.exists(p) else []


def lab_ship_save(rows):
    p = os.path.join(LAB, 'ship.json'); os.makedirs(LAB, exist_ok=True)
    with open(p + '.part', 'w') as o: json.dump(rows, o, indent=1, ensure_ascii=False)
    os.replace(p + '.part', p)


def lab_ship(f, req, by):
    """a ship request (no staging since 2026-10-10: every live send of a sheet queues one): {fighter, rev (default the
    live one), hash, by, at, note} queued as pending; the desktop's worker (labcfg.py ship-worker) ships the fighter's
    newest once it is 60 s old (arb_compile -> build -> checks -> VERSION bump -> publish) and marks it"""
    cur = lab_current(f)
    if not cur: return None, 'no config for ' + f
    rev = req.get('rev') or cur['version']
    r = cur if rev == cur['version'] else next((x for x in lab_history(f) if x['version'] == rev), None)
    if not r: return None, 'no revision %s of %s' % (rev, f)
    with lab_lock:
        rows = lab_ships()
        row = {'id': max([x['id'] for x in rows] or [0]) + 1, 'fighter': f, 'rev': r['version'], 'hash': r['hash'], 'by': by,
               'at': now(), 'note': str(req.get('note') or '')[:300], 'status': 'pending'}
        rows.append(row); lab_ship_save(rows)
    log('lab ship request', row['id'], f, 'rev', row['rev'], 'by', by)
    return row, None


def lab_ship_mark(req, by):
    """the desktop's answer to a ship request: {id, status building | done | failed | dropped, note?} (building: the
    worker took it; done: the release in the note; failed: the plain reason, the game untouched)"""
    if req.get('status') not in ('building', 'done', 'failed', 'dropped'): return None, 'status: building | done | failed | dropped'
    with lab_lock:
        rows = lab_ships()
        row = next((x for x in rows if x['id'] == req.get('id')), None)
        if not row: return None, 'no ship request %s' % req.get('id')
        if req['status'] == 'building': row.update(status='building', started_at=now(), result=str(req.get('note') or '')[:600])
        else: row.update(status=req['status'], closed_at=now(), closed_by=by, result=str(req.get('note') or '')[:600])
        lab_ship_save(rows)
    log('lab ship', row['id'], row['status'], 'by', by)
    return row, None


def lab_items(kind, f=None):
    """the published shells (kind 'shell') or a fighter's packs: their sidecar JSONs, oldest first"""
    d = os.path.join(LAB, 'shell') if kind == 'shell' else os.path.join(LAB, 'packs', f)
    if not os.path.isdir(d): return []
    out = []
    for n in os.listdir(d):
        if n.endswith('.json'):
            try: out.append(json.load(open(os.path.join(d, n))))
            except ValueError: pass
    return sorted(out, key=lambda x: x.get('published', ''))


def lab_catalogue():
    """{shell, packs}: the last published shell and each fighter's last published pack (the newest 'published' wins,
    so a rollback = publishing the old file again under a new version)"""
    sh = lab_items('shell')
    shell = {k: sh[-1].get(k) for k in ('version', 'url', 'sha256', 'engine', 'size', 'published', 'format', 'features')} if sh else None
    packs = []
    pd = os.path.join(LAB, 'packs')
    for f in sorted(os.listdir(pd)) if os.path.isdir(pd) else []:
        it = lab_items('pack', f) if FIGHTER.match(f) else []
        if not it: continue
        x = it[-1]
        face = os.path.join(LAB, 'faces', f + '.png')
        keys = ('version', 'url', 'sha256', 'size', 'engine', 'format', 'needs', 'data_sha', 'published')
        packs.append({'fighter': f, 'display': x.get('display') or f, 'face': LAB_DL + 'faces/' + f + '.png' if os.path.exists(face) else None,
                      'version': x['version'], 'url': x['url'], 'sha256': x['sha256'], 'engine': x['engine'], 'size': x['size'],
                      'published': x.get('published'), 'versions': len(it), 'format': x.get('format'), 'needs': x.get('needs'),
                      'data_sha': x.get('data_sha'), 'all': [{k: y.get(k) for k in keys} for y in reversed(it)]})
    return {'shell': shell, 'packs': packs}


def lab_publish(req, by):
    """labpub.py: {kind shell|pack|face, fighter?, version, engine, src (a file name in LAB/incoming), sha256, display?}
    -> the file moved to shell/<version><ext> | packs/<f>/<version>.pack | faces/<f>.png, its sidecar <version>.json"""
    kind, f, ver, src = req.get('kind'), str(req.get('fighter') or ''), str(req.get('version') or ''), str(req.get('src') or '')
    if kind not in ('shell', 'pack', 'face'): return None, 'kind: shell | pack | face'
    if kind != 'shell' and not FIGHTER.match(f): return None, 'fighter'
    if not re.match(r'^[A-Za-z0-9._-]{1,80}$', src) or src.startswith('.'): return None, 'src'
    sp = os.path.join(LAB_IN, src)
    if not os.path.isfile(sp): return None, 'no such upload: ' + src
    data_sha = hashlib.sha256(open(sp, 'rb').read()).hexdigest()
    if req.get('sha256') != data_sha: return None, 'sha256 mismatch (upload %s)' % data_sha
    if kind == 'face':
        d = os.path.join(LAB, 'faces'); os.makedirs(d, exist_ok=True)
        os.replace(sp, os.path.join(d, f + '.png'))
        return {'kind': 'face', 'fighter': f, 'url': LAB_DL + 'faces/' + f + '.png', 'sha256': data_sha}, None
    eng = str(req.get('engine') or '')
    if not LVER.match(ver): return None, 'version: letters, digits, . _ - (32 at most)'
    if not LVER.match(eng): return None, 'engine: the engine version the file is built for'
    if kind == 'shell':
        ext = os.path.splitext(src)[1].lower() or '.bin'
        if not LEXT.match(ext): return None, 'extension'
        d, name, url = os.path.join(LAB, 'shell'), ver + ext, LAB_DL + 'shell/' + ver + ext
    else:
        d, name, url = os.path.join(LAB, 'packs', f), ver + '.pack', LAB_DL + 'packs/' + f + '/' + ver + '.pack'
    with lab_lock:
        os.makedirs(d, exist_ok=True)
        if os.path.exists(os.path.join(d, ver + '.json')): return None, 'version %s already published' % ver
        meta = {'kind': kind, 'version': ver, 'engine': eng, 'sha256': data_sha, 'size': os.path.getsize(sp), 'url': url,
                'file': name, 'published': now(), 'by': by}
        fmt = req.get('format')                         # the pack format (docs/character_lab.md): its number, the shell's
        if isinstance(fmt, int) and 0 < fmt < 1000: meta['format'] = fmt   # features / the pack's needs (tokens)
        toks = lambda v: [str(t)[:64] for t in (v.split() if isinstance(v, str) else v or [])][:2000]
        if kind == 'shell' and req.get('features') is not None: meta['features'] = toks(req['features'])
        if kind == 'pack':
            meta['fighter'] = f; meta['display'] = str(req.get('display') or f)[:40]
            if req.get('needs') is not None: meta['needs'] = toks(req['needs'])
            if re.match(r'^[0-9a-f]{64}$', str(req.get('data_sha') or '')): meta['data_sha'] = req['data_sha']
        os.replace(sp, os.path.join(d, name))
        with open(os.path.join(d, ver + '.json'), 'w') as o: json.dump(meta, o, indent=1, ensure_ascii=False)
    log('lab publish', kind, f, ver, 'engine', eng, meta['size'], 'bytes by', by)
    return meta, None


def lab_unpublish(req):
    """{kind shell|pack|face, fighter?, version?}: the file and its sidecar removed"""
    kind, f, ver = req.get('kind'), str(req.get('fighter') or ''), str(req.get('version') or '')
    if kind not in ('shell', 'pack', 'face') or (kind != 'shell' and not FIGHTER.match(f)): return 'kind / fighter'
    if kind == 'face':
        p = os.path.join(LAB, 'faces', f + '.png')
        if not os.path.exists(p): return 'no face for ' + f
        os.remove(p); return None
    if not LVER.match(ver): return 'version'
    d = os.path.join(LAB, 'shell') if kind == 'shell' else os.path.join(LAB, 'packs', f)
    side = os.path.join(d, ver + '.json')
    if not os.path.exists(side): return 'not published: %s %s' % (kind, ver)
    with lab_lock:
        meta = json.load(open(side))
        if os.path.exists(os.path.join(d, meta['file'])): os.remove(os.path.join(d, meta['file']))
        os.remove(side)
        if kind == 'pack' and not os.listdir(d): os.rmdir(d)
    log('lab unpublish', kind, f, ver)
    return None


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
        lab = self.lab_route()
        if lab is not None: return self.lab_get(lab)
        if not u.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        parts = u.path.split('/')[2:]
        if len(parts) == 2 and parts[0] == 'decisions' and re.match(r'^[a-z0-9_-]{1,40}$', parts[1]):
            p = os.path.join(DATA, 'decisions', parts[1] + '.json')
            return self.reply(200, json.load(open(p)) if os.path.exists(p) else {})
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
                    r.update(queue_info(c, r))
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
            if parts == ['reviews']:
                st = (q.get('status') or [''])[0]
                rs = c.execute('SELECT * FROM reviews' + (' WHERE status=?' if st else '') + ' ORDER BY id DESC', (st,) if st else ())
                return self.reply(200, {'reviews': [review_dict(c, r) for r in rs.fetchall()], 'kinds': REVIEW_KINDS})
            if len(parts) == 2 and parts[0] == 'review' and parts[1].isdigit():
                r = c.execute('SELECT * FROM reviews WHERE id=?', (int(parts[1]),)).fetchone()
                return self.reply(200, {'review': review_dict(c, r)}) if r else self.reply(404, {'error': 'no such decision'})
        if len(parts) == 4 and parts[0] == 'review' and parts[1].isdigit() and parts[2] == 'file' and RFILE.match(parts[3]):
            p = os.path.join(REVIEWS, parts[1], parts[3])
            if os.path.exists(p): return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
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
                    r.update(queue_info(c, r))                       # Player 0.0.23: the test queue's rule
                revs = [review_dict(c, x, True) for x in c.execute("SELECT * FROM reviews WHERE audience IN ('', ?) ORDER BY id DESC", (user,)).fetchall()]
                return self.reply(200, {'user': user, 'rows': rows, 'reviews': revs})   # reviews: Player 0.0.24's Decisions
            if len(parts) == 3 and parts[0] == 'review' and parts[1].isdigit() and RFILE.match(parts[2]):
                if c.execute("SELECT 1 FROM reviews WHERE id=? AND audience IN ('', ?)", (int(parts[1]), user)).fetchone():
                    p = os.path.join(REVIEWS, parts[1], parts[2])
                    if os.path.exists(p): return self.reply(200, body=open(p, 'rb').read(), ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
                return self.reply(404, {'error': 'not found'})
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

    # ---- Character Lab (docs/character_lab.md "Character Lab") ------------------------------------------------------------
    def lab_route(self):
        """the Lab's path parts after /lab/ (the player: nginx /brawler/lab/, X-Public) or /api/lab/ (the web pages:
        /brawler-lab/feedback-api/lab/, the Oros cookie; or ssh on localhost); None = not a Lab path"""
        p = urllib.parse.urlparse(self.path).path
        if p.startswith('/lab/'): return p.split('/')[2:]
        if p.startswith('/api/lab/') and not self.headers.get('X-Public'): return p.split('/')[3:]
        return None

    def lab_user(self, write=False):
        """any signed-in Oros account reads; writes need the Oros role admin. No token / cookie at all and not through
        the public proxy = ssh on localhost (labcfg.py, labpub.py): user 'ssh'"""
        user, role = account_role(self.headers)
        if not user:
            h = self.headers
            if h.get('X-Public') or h.get('Authorization') or h.get('Cookie'):
                self.reply(401, {'error': 'sign in with your Oros account'}); return None
            user, role = 'ssh', 'admin'
        if write and role != 'admin':
            self.reply(403, {'error': 'Lab writes need an Oros admin account'}); return None
        return user

    def etag_reply(self, tag, obj):
        """200 with ETag "<tag>", or 304 (no body) when If-None-Match names it"""
        inm = self.headers.get('If-None-Match', '')
        if inm and (inm.strip() == '*' or any(t.strip().removeprefix('W/').strip('"') == tag for t in inm.split(','))):
            self.send_response(304); self.send_header('ETag', '"%s"' % tag); self.send_header('Cache-Control', 'no-cache')
            self.end_headers(); return
        b = (json.dumps(obj, ensure_ascii=False) + '\n').encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('ETag', '"%s"' % tag)
        self.send_header('Cache-Control', 'no-cache'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def lab_get(self, parts):
        user = self.lab_user()
        if not user: return
        if parts == ['me']:                                  # the pages: Send to Player / Revert need the role admin
            return self.reply(200, {'user': user, 'role': 'admin' if user == 'ssh' else account_role(self.headers)[1]})
        if parts == ['catalogue']:
            cat = lab_catalogue()
            return self.etag_reply(hashlib.sha256(json.dumps(cat, sort_keys=True).encode()).hexdigest()[:32], cat)
        if parts == ['ship']:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            st, fi = (q.get('status') or [''])[0], (q.get('fighter') or [''])[0]
            return self.reply(200, {'requests': [x for x in lab_ships() if (not st or x['status'] == st) and (not fi or x['fighter'] == fi)]})
        if parts == ['config']:
            fs = sorted(n[:-5] for n in os.listdir(LAB_CFG) if n.endswith('.json')) if os.path.isdir(LAB_CFG) else []
            return self.reply(200, {'configs': [lab_head(lab_current(f)) for f in fs if FIGHTER.match(f)]})
        if len(parts) >= 2 and parts[0] == 'config' and FIGHTER.match(parts[1]):
            f, rest = parts[1], parts[2:]
            if rest == ['history']: return self.reply(200, {'fighter': f, 'revisions': [lab_head(r) for r in lab_history(f)]})
            if len(rest) == 2 and rest[0] == 'rev' and rest[1].isdigit():
                r = next((r for r in lab_history(f) if r['version'] == int(rest[1])), None)
                return self.reply(200, r) if r else self.reply(404, {'error': 'no revision %s of %s' % (rest[1], f)})
            cur = lab_current(f)
            if rest in ([], ['hash']) and not cur: return self.reply(404, {'error': 'no config for ' + f})
            if rest == []: return self.etag_reply('v%d-%s' % (cur['version'], cur['hash'][:16]), cur)
            if rest == ['hash']: return self.etag_reply(cur['hash'], {'hash': cur['hash'], 'version': cur['version'], 'updated': cur['updated']})
        self.reply(404, {'error': 'not found'})

    def lab_write(self, parts):
        user = self.lab_user(True)
        if not user: return
        if parts in (['publish'], ['unpublish']):
            req = self.json_body(1 << 16)
            if req is None: return
            if parts == ['publish']:
                meta, err = lab_publish(req, user)
                return self.reply(400, {'error': err}) if err else self.reply(200, {'published': meta, 'catalogue': lab_catalogue()})
            err = lab_unpublish(req)
            return self.reply(400, {'error': err}) if err else self.reply(200, {'ok': True, 'catalogue': lab_catalogue()})
        if (len(parts) == 2 and parts[0] == 'ship' and FIGHTER.match(parts[1])) or parts == ['ship_done']:
            req = self.json_body(1 << 12) if int(self.headers.get('Content-Length') or 0) else {}
            if req is None: return
            row, err = lab_ship(parts[1], req, user) if parts[0] == 'ship' else lab_ship_mark(req, user)
            return self.reply(400, {'error': err}) if err else self.reply(200, {'ship': row})
        if len(parts) >= 2 and parts[0] == 'config' and FIGHTER.match(parts[1]):
            f, rest = parts[1], parts[2:]
            if rest == ['revert']:
                req = self.json_body(1 << 12)
                if req is None: return
                r = next((r for r in lab_history(f) if r['version'] == req.get('rev')), None)
                if not r: return self.reply(404, {'error': 'no revision %s of %s' % (req.get('rev'), f)})
                rec, _, _ = lab_store(f, base64.b64decode(r['blob']), r['json'], user, str(req.get('note') or 'revert to rev %d' % r['version']),
                                      reverted_from=r['version'])
                return self.reply(200, dict(lab_head(rec), changed=True))
            if rest == []:
                b = self.body(MAX_CFG)
                if b is None: return self.reply(413, {'error': 'size: a JSON body of at most %d bytes' % MAX_CFG})
                try: req = json.loads(b)
                except ValueError: return self.reply(400, {'error': 'json'})
                if not isinstance(req, dict) or not isinstance(req.get('blob'), str) or not isinstance(req.get('json'), dict):
                    return self.reply(400, {'error': 'body: {blob: base64 of the RAM loads, json: {the config it was encoded from}, hash?, note?}'})
                try: blob = base64.b64decode(req['blob'], validate=True)
                except ValueError: return self.reply(400, {'error': 'blob: not base64'})
                if req.get('hash') and req['hash'] != hashlib.sha256(blob).hexdigest():
                    return self.reply(400, {'error': 'hash: not the sha256 of the blob (%s)' % hashlib.sha256(blob).hexdigest()})
                im = self.headers.get('If-Match', '').strip().strip('"') or None
                rec, changed, err = lab_store(f, blob, req['json'], user, str(req.get('note') or ''), expect=im)
                if err: return self.reply(412, {'error': 'the config changed meanwhile (If-Match)', 'current': lab_head(rec) if rec else None})
                return self.reply(200, dict(lab_head(rec), changed=changed))
        self.reply(404, {'error': 'not found'})

    def do_PUT(self):
        parts = self.lab_route()
        if parts is None: return self.reply(404, {'error': 'not found'})
        self.lab_write(parts)

    # ---- POST ---------------------------------------------------------------------------------------------------
    def do_POST(self):
        if self.path == '/transcribe': return self.transcribe()
        if self.path == '/upload': return self.upload()
        if self.path == '/reply': return self.post_reply()
        if self.path == '/test': return self.post_test()
        if self.path == '/review': return self.post_review_answer()
        lab = self.lab_route()
        if lab is not None: return self.lab_write(lab)
        if not self.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        if self.path == '/api/status': return self.change(self.set_status)
        if self.path == '/api/set': return self.change(self.set_fields)
        if self.path == '/api/scenario': return self.change(self.set_scenario)
        if self.path == '/api/scenario_state': return self.change(self.add_state)
        if self.path == '/api/event': return self.change(self.add_event)
        if self.path == '/api/test': return self.change(self.lab_test)
        if self.path == '/api/select_layout': return self.save_layout()
        if self.path == '/api/review': return self.create_review()
        if self.path == '/api/review_answer': return self.lab_review_answer()
        if self.path == '/api/review_delete': return self.delete_review()
        if self.path == '/api/transcribe': return self.lab_transcribe()
        if self.path == '/api/decision': return self.save_decision()
        self.reply(404, {'error': 'not found'})

    def lab_transcribe(self):
        """the Lab's microphone button on any note field (behind the Oros login, nginx auth_request): the raw audio body
        (X-Audio-Name: audio.webm / .m4a / .ogg / .wav / .mp3) -> {text}; logged like the player's"""
        data = self.body(MAX_AUDIO)
        if data is None: return self.reply(413, {'error': 'size'})
        name = self.headers.get('X-Audio-Name', 'audio.webm')
        if not re.match(r'^[a-z0-9_]{1,40}\.(webm|m4a|ogg|wav|mp3)$', name): name = 'audio.webm'
        t0 = time.time()
        try: text, model, dt, usage = openai_transcribe(name, data)
        except RuntimeError: return self.reply(502, {'error': 'transcription unavailable'})
        tx, usd = log_tx(model, usage, audio_seconds(data=data), '', 'lab', who={'user': 'lab', 'install_id': None,
                         'ip': self.headers.get('X-Real-IP') or None, 'user_agent': self.headers.get('User-Agent') or None})
        log('transcribe (lab)', len(data), 'bytes', model, f'{time.time() - t0:.1f}s', len(text), 'chars', f'${usd:.5f}')
        self.reply(200, {'text': text, 'model': model, 'seconds': dt, 'tx_id': tx})

    def save_decision(self):
        """the Lab's Decisions page: {set, id, choice?, label?, note?, question?, pieces?, flags?, knobs?} merged into DATA/decisions/<set>.json"""
        req = self.json_body(1 << 16)
        if req is None: return
        st, qid = str(req.get('set') or ''), str(req.get('id') or '')
        if not re.match(r'^[a-z0-9_-]{1,40}$', st) or not re.match(r'^[A-Za-z0-9_-]{1,40}$', qid): return self.reply(400, {'error': 'set / id'})
        d = os.path.join(DATA, 'decisions'); os.makedirs(d, exist_ok=True)
        p = os.path.join(d, st + '.json')
        with lock:
            cur = json.load(open(p)) if os.path.exists(p) else {}
            a = cur.get(qid, {})
            for k in ('choice', 'label', 'note', 'question'):
                if k in req: a[k] = req[k]
            ps = req.get('pieces')                     # an option's moves as Bruno edited them (review.js picker; a dictionary
            if isinstance(ps, list) and len(ps) <= 16 and all(isinstance(x, str) and re.match(r'^[A-Za-z0-9_.-]{1,40}$', x) for x in ps): a['pieces'] = ps
            elif ps is None and 'pieces' in req: a.pop('pieces', None)          # animation is "anim-6E")
            kn = req.get('knobs')                      # piece knobs (the Assembly, tools/brawler/knobs.py): {S- id: {knob id:
            if isinstance(kn, dict) and len(kn) <= 16 and all(   # value}}, shape only (arb_compile / the game check values)
                    isinstance(p, str) and re.match(r'^[ST]-\d{3,5}$', p) and isinstance(v, dict) and len(v) <= 8 and all(
                        isinstance(k, str) and re.match(r'^[a-z0-9_]{1,24}$', k) and isinstance(x, (int, float)) and not isinstance(x, bool)
                        and abs(x) < 1e6 for k, x in v.items()) for p, v in kn.items()):
                if kn: a['knobs'] = kn
                else: a.pop('knobs', None)
            elif kn is None and 'knobs' in req: a.pop('knobs', None)
            fl = req.get('flags')                      # an animation's flags (anims.html / the picker: weight, limb, ...)
            if isinstance(fl, list) and len(fl) <= 32 and all(isinstance(x, str) and re.match(r'^[a-z0-9_.-]{1,24}$', x) for x in fl): a['flags'] = fl
            elif fl is None and 'flags' in req: a.pop('flags', None)
            a['at'] = now(); cur[qid] = a
            tmp = p + '.part'; json.dump(cur, open(tmp, 'w'), indent=1, ensure_ascii=False); os.replace(tmp, p)
        self.reply(200, {'ok': True, 'answer': a})

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

    def json_body(self, limit):
        b = self.body(limit)
        if b is None: self.reply(413, {'error': 'size'}); return None
        try: req = json.loads(b)
        except ValueError: self.reply(400, {'error': 'json'}); return None
        if not isinstance(req, dict): self.reply(400, {'error': 'json object'}); return None
        return req

    def create_review(self):
        """a decision (fb.py review add): its images written to DATA/reviews/<id>/, the options fixed by its kind"""
        import base64
        req = self.json_body(MAX_REVIEW)
        if req is None: return
        by = account(self.headers) or req.get('by') or 'ssh'
        title = ' '.join(str(req.get('title') or '').split()); question = str(req.get('question') or '').strip()
        kind = req.get('kind'); imgs = req.get('images') or []
        if not title or len(title) > 90 or not question: return self.reply(400, {'error': 'title (<= 90) + question'})
        if kind not in REVIEW_KINDS: return self.reply(400, {'error': 'kind: ' + ', '.join(REVIEW_KINDS)})
        if not isinstance(imgs, list) or not imgs or len(imgs) > 40: return self.reply(400, {'error': 'images: 1 to 40'})
        names = [str(i.get('name') or '') for i in imgs]
        if any(not IMG.match(n) for n in names) or len(set(names)) != len(names): return self.reply(400, {'error': 'image names: distinct, [a-z0-9_-].png'})
        try: data = [base64.b64decode(i['b64'], validate=True) for i in imgs]
        except Exception: return self.reply(400, {'error': 'images: b64'})
        opts = req.get('options')
        err = check_review(question, imgs, opts)
        if err: return self.reply(400, {'error': err})
        opts = [{'label': ' '.join(str(o['label']).split()), 'effect': ' '.join(str(o['effect']).split())} for o in opts]
        todo = ','.join(t.strip().lstrip('#') for t in str(req.get('todo') or '').split(',') if t.strip())
        if todo and not re.match(r'^\d+(,\d+)*$', todo): return self.reply(400, {'error': 'todo: item numbers'})
        notes = ','.join(n.strip() for n in str(req.get('notes') or '').split(',') if n.strip())
        if notes and not all(ID.match(n) for n in notes.split(',')): return self.reply(400, {'error': 'notes: feedback ids'})
        audience = str(req.get('audience') or '').strip()
        if audience and not re.match(r'^[A-Za-z0-9_.@-]{1,40}$', audience): return self.reply(400, {'error': 'audience: an Oros username'})
        meta = [{'label': ' '.join(str(i['label']).split()), 'file': n} for i, n in zip(imgs, names)]
        with lock, db() as c:
            cur = c.execute('INSERT INTO reviews (created, updated, by, audience, title, question, kind, images, options, todo, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                            (now(), now(), by, audience, title, question, kind, json.dumps(meta, ensure_ascii=False), json.dumps(opts, ensure_ascii=False), todo, notes))
            rid = cur.lastrowid
            d = os.path.join(REVIEWS, str(rid)); os.makedirs(d, exist_ok=True)
            for n, b in zip(names, data):
                with open(os.path.join(d, n), 'wb') as f: f.write(b)
            c.execute('INSERT INTO review_history VALUES (?,?,?,?,?,?)', (rid, now(), by, 'created', f'{kind}, {len(meta)} images, for {audience or "every account"}', ''))
            r = c.execute('SELECT * FROM reviews WHERE id=?', (rid,)).fetchone()
            review_event(c, r, by, f'decision #{rid} asked: "{title}"', f'review{rid}:created')
            out = review_dict(c, r)
        log('review', rid, 'created by', by, kind, len(meta), 'images')
        self.reply(200, {'review': out})

    def lab_review_answer(self):
        req = self.json_body(1 << 16)
        if req is None: return
        by = account(self.headers) or req.get('by') or 'ssh'
        with lock, db() as c:
            src = req.get('source') if req.get('source') in ('lab', 'artifact', 'chat') else 'lab'   # fb.py review answer: where he answered
            out, err = answer_review(c, int(req.get('id') or 0), by, str(req.get('answer') or ''), str(req.get('text') or '').strip()[:4000], source=src)
        if err: return self.reply(400 if 'answer' in err else 404, {'error': err})
        log('review', out['id'], 'answered from the', out['answer_source'], 'by', by, out['answer'])
        self.reply(200, {'review': out})

    def delete_review(self):
        import shutil
        req = self.json_body(1 << 16)
        if req is None: return
        rid = int(req.get('id') or 0)
        with lock, db() as c:
            if not c.execute('SELECT 1 FROM reviews WHERE id=?', (rid,)).fetchone(): return self.reply(404, {'error': 'no such decision'})
            c.execute('DELETE FROM reviews WHERE id=?', (rid,)); c.execute('DELETE FROM review_history WHERE review_id=?', (rid,))
            c.execute("DELETE FROM events WHERE kind='decision' AND ref LIKE ?", (f'review{rid}:%',))
        shutil.rmtree(os.path.join(REVIEWS, str(rid)), ignore_errors=True)
        log('review', rid, 'deleted by', account(self.headers) or req.get('by') or 'ssh')
        self.reply(200, {'deleted': rid})

    def post_review_answer(self):
        """Player 0.0.24: his answer to a decision put to him (the token only), with an optional note: text and / or voice
        (transcribed by /transcribe first, like a reply)"""
        import base64
        user = self.player()
        if not user: return
        req = self.json_body(MAX_REPLY)
        if req is None: return
        try: rid = int(req.get('id') or 0)
        except (TypeError, ValueError): rid = 0
        try: audio = base64.b64decode(req['audio_b64'], validate=True) if req.get('audio_b64') else b''
        except ValueError: return self.reply(400, {'error': 'audio_b64'})
        if len(audio) > MAX_AUDIO: return self.reply(413, {'error': 'size'})
        ext = (req.get('audio_name') or 'a.m4a').rsplit('.', 1)[-1]
        if ext not in ('m4a', 'wav', 'mp3', 'ogg'): ext = 'm4a'
        w = self.who(user)
        origin = {'apk_version': self.headers.get('X-App-Version'), 'install_id': w['install_id'], 'device': str(req.get('device') or '')[:80],
                  'android': str(req.get('android') or '')[:40], 'ip': w['ip'], 'user_agent': w['user_agent']}
        with lock, db() as c:
            if not c.execute("SELECT 1 FROM reviews WHERE id=? AND audience IN ('', ?)", (rid, user)).fetchone():
                return self.reply(404, {'error': 'no such decision for you'})
            out, err = answer_review(c, rid, user, str(req.get('answer') or ''), str(req.get('text') or '').strip()[:4000],
                                     str(req.get('raw_transcript') or '')[:4000], audio, ext, 'player', origin)
            if err: return self.reply(400, {'error': err})
            tx = req.get('tx_id', '')
            if tx and re.match(r'^[0-9a-f]{16}$', tx): c.execute("UPDATE transcriptions SET feedback_id=? WHERE tx_id=? AND feedback_id=''", (f'review{rid}', tx))
        out.pop('answer_origin', None)
        log('review', rid, 'answered by', user, out['answer'], len(audio), 'bytes audio')
        self.reply(200, {'review': out})

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
    os.makedirs(BUNDLES, exist_ok=True); os.makedirs(SCENARIOS, exist_ok=True); os.makedirs(ATTEMPTS, exist_ok=True); os.makedirs(REVIEWS, exist_ok=True); db_init(); backfill()
    try: backfill_origin()
    except Exception as e: log('backfill origin failed:', e)
    threading.Thread(target=worker, daemon=True).start()
    with db() as c:                                          # transcripts missed while down
        for r in c.execute("SELECT id FROM feedback WHERE audio_path != '' AND raw_transcript = ''"): jobs.put(r['id'])
        for r in c.execute("SELECT DISTINCT rom_sha FROM feedback"): jobs.put('rom:' + r['rom_sha'])
    log('listening on 127.0.0.1:%d, data %s' % (PORT, DATA))
    Server(('127.0.0.1', PORT), H).serve_forever()
