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
ROLES (docs/feedback.md "Roles and the two apps"): the Oros account's tags, from /api/whoami (brawler_role): brawler_admin
= everything; brawler_tester = upload / transcribe / reply / his own /mine (no decisions, no test states), me, his allowed
build (share/); anything else = 403 on every player call. Admin only: /dlauth (the dev builds), /test, /review, the Lab
(lab/ and api/lab/), the signed-in API (api/, also behind nginx's brawler-admin gate).
  GET  /me           {user, role, build, app {version, code, url, size, sha256}} (the Brawler app: its role + its update)
  GET  /share/latest.json, /share/build/brawler-<V>.neo   the account's allowed build (the Brawler app's RomFetch)
  GET  /app/brawler-<name>-<code>.apk?t=<ticket>          the Brawler APK (the app's self-update / browser; ticket from /me)
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
= user 'ssh', labcfg.py / labpub.py). Reads and writes: a brawler admin (Oros tag brawler_admin; 403 otherwise).
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
  POST lab/ship/<f> {rev?, note?}   the Assembly's "Ship to the game" button (2026-10-12): queues {id, fighter, rev, hash,
                                     by, at, note, status pending} in LAB/ship.json; the ship service (labcfg.py ship-worker,
                                     brawler-ship.service; docs/character_lab.md "Ship service") takes it within 30 s (a
                                     fighter's older pending ones: dropped, superseded): pull, arb_compile, VERSION +1,
                                     build, checks, publish, commit + push
  GET  lab/ship[?status=...][&fighter=f]  the queue; POST lab/ship_done {id, status building | done | failed | dropped,
                                     note?} (the worker; the sheet's "In the game" line reads it)
  POST lab/publish {kind shell|pack|face, fighter?, version, engine, src, sha256, display?, format?, features? (shell),
                    needs? + data_sha? (pack)}   labpub.py (the file in LAB/incoming)
  POST lab/unpublish {kind, fighter?, version?}
  Files: LAB/config/<f>.json (live) + <f>.history.jsonl (append-only, every revision in full); LAB/shell/<version><ext>,
  LAB/packs/<f>/<version>.pack (+ <version>.json sidecars), LAB/faces/<f>.png; served by nginx /brawler/lab/dl/ (Range).
Cloud saves (Player 0.0.39, docs/feedback.md "Cloud saves"): the emulator's backup data per Oros account and per game
(any .neo game, keyed by the ROM's name: "brawler"), so a save follows the account to another Player. The signed-in user
only (role admin or tester), never another account's; DATA/saves/<user>/<game>/state.json {rev, last, updated, deleted,
size, saved_at} + r<rev>.json (each revision in full; the last SAVE_KEEP kept as backups). nginx /brawler/feedback/saves/.
  GET    saves/<game>   {rev, updated, files {nv|srm|mcr|brm: base64}, size, saved_at}; ETag "<rev>"; 404 {rev 0,
                        deleted (ms) | null} = none (deleted = a Reset game save from some Player)
  PUT    saves/<game>   {base_rev, updated (ms, when the save changed on the device), files}; If-Match "<rev>" (else
                        base_rev) = the revision the device last synced (0 = none); another current revision -> 409 {rev,
                        updated, deleted} (the Player: newest wins; the older one is sent with ?backup=1: stored as a
                        backup revision, the current one unchanged) -> {rev, updated, current}; files <= MAX_SAVE bytes
  DELETE saves/<game>   the current save goes (its revision file stays as a backup), state deleted = now -> {rev 0, deleted}
Settings (app 0.0.44, docs/feedback.md "Sign-up and the player admin"): GET / PUT settings {settings {language, ...},
updated (ms)}: the signed-in account's app settings, newest wins (DATA/settings/<user>.json).
Player admin (the Factory's Players tab, brawler admins; the accounts themselves are Oros's /api/brawler/...):
  GET  /api/players                          every account's play data + who is LIVE + this side's audit (admin_audit)
  POST /api/players/reset_save {user, game?} the account's cloud save(s) deleted (audited)
  GET  /api/sessions?user=X                  one player's sessions
Nightly (Oros tag brawler_nightly): share/latest.json and me give the newest published build, not the assignment.
Session recording (Player 0.0.41, keyframes 0.0.43, 2 s chunks 0.0.44; docs/feedback.md "Session recording"): POST sessions/chunk = a ~2 s
chunk of the play session (pads + the state's SHA-256; a keyframe chunk, every ~30 s, the state too), files on the storage box SESSIONS/<session>/, the index in the sessions / session_chunks
tables; the Lab reads them through /api/sessions, /api/session/<id>[/inputs | /state/<seq>] (sessions_api).
Lifecycle (docs/feedback.md): every row's timeline = found + status history + events + tests + replies, oldest first.
Cost: every transcription's usage as OpenAI returns it (tokens, or seconds for whisper-1) and its USD cost from
PRICES (prices.json next to this file: the price table with its source and date) go to the transcriptions table,
linked to its note (the player sends the tx_id it got back; cancelled notes' transcriptions stay unlinked but count
in the total). Notes from before the cost log: estimated from the audio's duration (source 'duration').
Tracker: DATA/feedback.db (SQLite; feedback + status_history + transcriptions + replies), copied daily to DATA/backups/ (kept 14), mirrored to
the desktop by pull.py. The OpenAI key is read from KEY_FILE at each call; never logged, never stored."""
import base64, hashlib, hmac, http.server, io, json, mimetypes, os, queue, re, secrets, socketserver, sqlite3, threading, time
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
        CREATE INDEX IF NOT EXISTS review_history_id ON review_history(review_id);
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, user TEXT, install_id TEXT, started TEXT, first_at REAL, last_at REAL, chunks INTEGER DEFAULT 0,
            frames INTEGER DEFAULT 0, bytes INTEGER DEFAULT 0, rom_sha TEXT, rom_version TEXT, rom_build TEXT, system TEXT,
            memcard TEXT, app TEXT, app_version TEXT, device TEXT, android TEXT, ip TEXT, paused INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS sessions_last ON sessions(last_at);
        CREATE TABLE IF NOT EXISTS session_chunks (
            session TEXT, seq INTEGER, start_frame INTEGER, frames INTEGER, state INTEGER, state_size INTEGER,
            state_sha TEXT, bytes INTEGER, at REAL, paused INTEGER, inputs BLOB, PRIMARY KEY (session, seq));
        CREATE INDEX IF NOT EXISTS session_keys ON session_chunks(session, state, seq);
        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER, by TEXT, action TEXT, target TEXT, detail TEXT DEFAULT '');''')
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
    dirs = [d for d in (BUILDS, os.path.join(DATA, 'share', 'builds')) if os.path.isdir(d)]   # (the testers' assigned builds too)
    for p in [os.path.join(d, f) for d in dirs for f in sorted(os.listdir(d))]:
        f = os.path.basename(p)
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
    with Oros's /api/whoami (cached 1 min); None = nobody signed in (ssh on localhost: the caller's own "by")"""
    return account_role(headers)[0]


def brawler_role(tags):
    """THE BRAWLER ROLES (docs/feedback.md "Roles and the two apps"): the Oros account's tags (oros-server user-tags
    --name=X --add=brawler_admin | brawler_tester): 'admin' = everything (Lab, Factory, Chain Lab, dev builds, decisions,
    the test queue); 'tester' = his own feedback + his allowed build; 'none' = an Oros account with no brawler access"""
    tags = set(tags or [])
    return 'admin' if 'brawler_admin' in tags else 'tester' if 'brawler_tester' in tags else 'none'


def account_role(headers):
    """(user, brawler role 'admin' | 'tester' | 'none') behind the token / cookie; (None, None) = nobody signed in"""
    return account_full(headers)[:2]


def account_full(headers):
    """(user, brawler role, Oros tags) behind the token / cookie, checked with /api/whoami (cached 1 min; a revoked
    token, an Oros "sign out everywhere", = 401 there = nobody); (None, None, []) = nobody signed in"""
    auth = headers.get('Authorization', '')
    key, hdr = (auth, {'Authorization': auth}) if auth.startswith('Bearer ') else (headers.get('Cookie', ''), {'Cookie': headers.get('Cookie', '')})
    if not key: return None, None, []
    hit = ACCOUNTS.get(key)
    if hit and hit[3] > time.time(): return hit[0], hit[1], hit[2]
    try:
        with urllib.request.urlopen(urllib.request.Request(WHOAMI, headers=hdr), timeout=5) as r:
            j = json.load(r); name, tags = j.get('username') or None, list(j.get('tags') or [])
            role = brawler_role(tags)
    except Exception: name, role, tags = None, None, []
    if name:
        if len(ACCOUNTS) > 1000: ACCOUNTS.clear()
        ACCOUNTS[key] = (name, role, tags, time.time() + 60)
    return name, (role if name else None), (tags if name else [])


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
    cur = lab_current(f) or {'version': 0, 'hash': ''}   # (no live config yet: the ship compiles his sheet's answers anyway)
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
        if req['status'] == 'building':
            if row['status'] != 'building': row['started_at'] = now()
            row.update(status='building', result=str(req.get('note') or '')[:600])
            if req.get('step'): row.update(step=str(req['step'])[:40], step_at=now())
        else: row.update(status=req['status'], closed_at=now(), closed_by=by, result=str(req.get('note') or '')[:600])
        for k in ('version', 'changes'):                 # (the Factory's Build tab: the version built, the game.json diff lines)
            if req.get(k): row[k] = req[k] if k == 'version' else [str(x)[:300] for x in req[k][:40]]
        lab_ship_save(rows)
    log('lab ship', row['id'], row['status'], 'by', by)
    return row, None


def lab_ship_batch(req, by):
    """the Factory's "Ship pending changes" / "Rebuild & ship current": ONE request (one version) for several fighters
    ({fighters: [f...]}) or none ({rebuild: true}: no data change, the engine as pushed); revs = each fighter's live rev"""
    fs = req.get('fighters') or []
    if not isinstance(fs, list) or not all(isinstance(x, str) and FIGHTER.match(x) for x in fs): return None, 'fighters: a list of fighter names'
    secs = {}                                            # the Factory's draft sections asked for ({levels: true, game: true}): their revisions
    for n in SECTIONS:
        if not req.get(n): continue
        secs[n] = (section_load(n).get('draft') or {}).get('rev')
        if not secs[n]: return None, 'no %s draft to ship' % n
    if not fs and not secs and not req.get('rebuild'): return None, 'no fighter to ship (give fighters, a section (%s): true, or rebuild: true)' % ', '.join(SECTIONS)
    revs = {f: (lab_current(f) or {'version': 0})['version'] for f in fs}
    with lab_lock:
        rows = lab_ships()
        row = {'id': max([x['id'] for x in rows] or [0]) + 1, 'fighter': '+'.join(fs + list(secs)) or 'rebuild', 'fighters': fs, 'revs': revs,
               'kind': 'batch' if fs or secs else 'rebuild', 'rev': 0, 'hash': '', 'by': by, 'at': now(), 'note': str(req.get('note') or '')[:300], 'status': 'pending'}
        row.update(secs)                                 # (row[section] = the draft revision shipped)
        rows.append(row); lab_ship_save(rows)
    log('lab ship batch', row['id'], row['fighter'], 'by', by)
    return row, None


# THE FACTORY'S DRAFT SECTIONS (Levels, Game: one mechanism): a section = a part of game.json the Factory edits as a
# draft. LAB/<name>.json = {draft: {rev, <its fields>, by, at}, game: <the ship service's report of the game>}; every
# draft revision kept (<name>.json.history.jsonl). Each section: a shape check here (its clean function), its real
# check against the game by the ship service (tools/brawler/labcfg.py SECTIONS: <tool> merge -> game.json).
LEVEL_NAME = re.compile(r'^[A-Z0-9 .!-]{1,12}$')               # (tools/brawler/levels.py NAME)
SONG_NAME = re.compile(r'^[A-Z0-9_]{1,32}$')
KNOB_ID = re.compile(r'^[a-z_]+(\.[a-z0-9_*]+){0,4}$')         # (tools/brawler/gamecfg.py: a game.json path)


def levels_clean(req):
    """the Levels draft {stages: [{name, background, music}...]}"""
    st = req.get('stages')
    if not isinstance(st, list) or not 1 <= len(st) <= 32: return None, 'stages: a list of {name, background, music}'
    clean = []
    for i, x in enumerate(st):
        if not isinstance(x, dict) or not isinstance(x.get('name'), str) or not LEVEL_NAME.match(x['name']):
            return None, 'stage %d: name: 1-12 characters A-Z 0-9 space . ! -' % (i + 1)
        if not isinstance(x.get('background'), int) or not isinstance(x.get('music'), str) or not SONG_NAME.match(x['music']):
            return None, 'stage %d: background (a number) and music (a song name)' % (i + 1)
        clean.append({'name': x['name'], 'background': x['background'], 'music': x['music']})
    out = {'stages': clean}
    it = req.get('intro')                                        # the stage intro (note 20261014-192343-5d29; levels.py
    if it is not None:                                           # intro_merge checks it against the game)
        IK = {'fade': int, 'title': str, 'title_at': int, 'title_hold': int, 'walk_at': int, 'side': str, 'from': int, 'gait': str, 'wave_delay': int}
        if not isinstance(it, dict) or any(k not in IK or not isinstance(v, IK[k]) or isinstance(v, bool) or (isinstance(v, int) and not 0 <= v <= 1000)
                                           or (isinstance(v, str) and len(v) > 40) for k, v in it.items()):
            return None, 'intro: {fade, title, title_at, title_hold, walk_at, side, from, gait, wave_delay}'
        out['intro'] = dict(it)
    b = req.get('bonus')                                         # the bonus stages (TODO T7; levels.py bonus_view /
    if b is None: return out, None                               # bonus_merge check it against the game)
    num = lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 99
    if not isinstance(b, dict) or not isinstance(b.get('after'), list) or not all(num(s) for s in b['after']) or \
       not num(b.get('pick_seconds')) or not isinstance(b.get('fury_lock'), bool) or not isinstance(b.get('games'), list) or len(b['games']) > 3:
        return None, 'bonus: {after, pick_seconds, fury_lock, games}'
    games = []
    for g in b['games']:
        if not isinstance(g, dict) or not isinstance(g.get('name'), str) or not re.match(r'^[A-Z0-9 .!-]{1,18}$', g['name']) or \
           not isinstance(g.get('music'), str) or not SONG_NAME.match(g['music']) or not num(g.get('seconds')) or \
           not all(num(g[k]) for k in ('count', 'top', 'hp') if k in g):
            return None, 'bonus game: {name (1-18 A-Z 0-9 space . ! -), music, seconds, count + hp | top}'
        games.append({k: g[k] for k in ('id', 'kind', 'scene', 'name', 'music', 'seconds', 'count', 'hp', 'top') if k in g})
    return {**out, 'bonus': {'after': b['after'], 'pick_seconds': b['pick_seconds'], 'fury_lock': b['fury_lock'], 'games': games}}, None


def game_clean(req):
    """the Game draft {values: {knob id: a number, a word / line, or a story's 4-5 sentences}} (only what differs from
    the game; ranges checked by gamecfg.py merge)"""
    v = req.get('values')
    if not isinstance(v, dict) or len(v) > 200: return None, 'values: {knob id: value}'
    ok = lambda x: (isinstance(x, (int, float)) and not isinstance(x, bool)) or (isinstance(x, str) and len(x) <= 200)
    for k, x in v.items():
        if not KNOB_ID.match(k): return None, '%s: not a knob id' % k[:60]
        if not (ok(x) or (isinstance(x, list) and len(x) <= 5 and all(isinstance(s, str) and len(s) <= 200 for s in x))): return None, '%s: bad value' % k
    return {'values': v}, None


def roster_clean(req):
    """the Roster & select draft {selectable: {fighter: true | false} (only what differs from the game), layout?:
    {fighter: {x, y, z, facing, pose, slot}} (the select layout editor's), unlocks?: {starters, rungs: [[fighter]]} (the unlock
    ladder)}; the real checks: tools/brawler/roster.py merge"""
    s = req.get('selectable') or {}
    if not isinstance(s, dict) or len(s) > 64 or not all(FIGHTER.match(k) and isinstance(v, bool) for k, v in s.items()):
        return None, 'selectable: {fighter: true | false}'
    out = {'selectable': s}
    L = req.get('layout')
    if L is not None:
        num = lambda x: isinstance(x, int) and not isinstance(x, bool) and -1024 <= x <= 1024
        if not isinstance(L, dict) or len(L) > 64: return None, 'layout: {fighter: {x, y, z, facing, pose, slot}}'
        for k, v in L.items():
            if not FIGHTER.match(k) or not isinstance(v, dict) or set(v) != {'x', 'y', 'z', 'facing', 'pose', 'slot'} or \
               not all(num(v[f]) for f in ('x', 'y', 'z', 'slot')) or v['facing'] not in ('left', 'right') or \
               not (isinstance(v['pose'], list) and len(v['pose']) == 2 and all(num(p) for p in v['pose'])):
                return None, 'layout %s: {x, y, z, facing, pose, slot}' % k[:40]
        out['layout'] = L
    U = req.get('unlocks')                                  # the unlock ladder (game.json unlocks; Bruno 2026-10-15)
    if U is not None:
        names = lambda x: isinstance(x, list) and len(x) <= 32 and all(isinstance(n, str) and FIGHTER.match(n) for n in x)
        if not isinstance(U, dict) or set(U) != {'starters', 'rungs'} or not names(U['starters']) or not U['starters'] or \
           not (isinstance(U['rungs'], list) and len(U['rungs']) <= 16 and all(names(r) and 1 <= len(r) <= 6 for r in U['rungs'])):
            return None, 'unlocks: {starters: [fighter] (at least one), rungs: [[fighter] (1-6 a rung)]}'
        al = U['starters'] + [f for r in U['rungs'] for f in r]
        if len(set(al)) != len(al): return None, 'unlocks: a fighter twice'
        out['unlocks'] = U
    return out, None


THROW_ROW = re.compile(r'^[a-z0-9_]{1,40}-(fwd|back|holdb|run)$')     # (tools/brawler/throwcfg.py ROW_ID)


def throws_clean(req):
    """the Throws draft {throws: {<fighter>-<fwd | back | holdb | run>: {impacts: [{frame, damage?, spark?, sound?, shake?}]
    (1-3), held?, launch: {frame, dir, size?}}}} (only the throws that differ from the game); the real checks against
    the game (build_tables throw_events + the throw's length): tools/brawler/throwcfg.py merge"""
    T = req.get('throws')
    if not isinstance(T, dict) or len(T) > 96: return None, 'throws: {fighter-throw: events}'
    fr = lambda x: isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 400
    out = {}
    for k, e in T.items():
        if not isinstance(k, str) or not THROW_ROW.match(k): return None, '%s: not a throw (fighter-fwd | back | holdb | run)' % str(k)[:60]
        if not isinstance(e, dict) or not set(e) <= {'impacts', 'held', 'launch'}: return None, '%s: {impacts, held?, launch}' % k
        I = e.get('impacts')
        if not isinstance(I, list) or not 1 <= len(I) <= 3: return None, '%s: 1-3 impacts' % k
        imps = []
        for x in I:
            if not isinstance(x, dict) or not set(x) <= {'frame', 'damage', 'spark', 'sound', 'shake'} or not fr(x.get('frame')) or \
               not (isinstance(x.get('damage', 0), int) and not isinstance(x.get('damage', 0), bool) and 0 <= x.get('damage', 0) <= 100) or \
               not all(isinstance(x.get(f, True), bool) for f in ('spark', 'sound', 'shake')):
                return None, '%s: an impact {frame 1-400, damage 0-100 %%?, spark? sound? shake?: true | false}' % k
            imps.append(dict(x))
        L = e.get('launch')
        if not isinstance(L, dict) or not set(L) <= {'frame', 'dir', 'size'} or not fr(L.get('frame')) or L.get('dir') not in ('up', 'away', 'none') or \
           L.get('size', 'medium') not in ('small', 'medium', 'big'):
            return None, '%s: launch {frame 1-400, dir up | away | none, size? small | medium | big}' % k
        if 'held' in e and e['held'] is not None and not fr(e['held']): return None, '%s: held: a frame 1-400' % k
        out[k] = {'impacts': imps, 'launch': dict(L), **({'held': e['held']} if e.get('held') is not None else {})}
    return {'throws': out}, None


SECTIONS = {'levels': levels_clean, 'game': game_clean, 'roster': roster_clean, 'throws': throws_clean}


# THE BRAWLER APP (docs/feedback.md "Roles and the two apps"): the regular app (android flavor "brawler") plays the
# build its Oros account is allowed: the Factory's "players" section (lab/players: {assign: {name: VERSION}}, saved live,
# never shipped), served by GET share/latest.json = the newest published build up to it (a tester with none assigned:
# nothing; an admin with none assigned: the newest). The assigned builds are kept in SHARE/builds/ (hard links of
# /data/brawler/builds/brawler-<V>.neo, which publish_vps.sh prunes to the last 3). The accounts = the Oros users tagged
# brawler_admin / brawler_tester, read from the Oros DB (read only). Its own APK: SHARE/app/brawler-<name>-<code>.apk
# (tools/brawler/publish_app.sh), offered by GET me as a link with a ticket (HMAC with SHARE/secret, 24 h, the user in
# it): GET app/<file>?t=<ticket>. Since app 0.0.42 the app downloads it itself (size + sha256 from me) and installs it
# (PlayerUpdate.kt); the same link is its fallback in the phone's browser.
SHARE = os.path.join(DATA, 'share')
SHARE_SECRET = os.path.join(SHARE, 'secret')
SHARE_BUILDS = os.path.join(SHARE, 'builds')
SHARE_APP = os.path.join(SHARE, 'app')
SHARE_SEEN = os.path.join(SHARE, 'seen.json')               # {name: {at, rom, app, device}}: the Players tab's "on 0.10.80"
OROS_DB = os.environ.get('FEEDBACK_OROS_DB', '/data/oros/oros.db')
TICKET_S = 24 * 3600
BUILD_FILE = re.compile(r'^brawler-(\d+\.\d+\.\d+)\.neo$')
APP_FILE = re.compile(r'^brawler-(\d+\.\d+\.\d+)-(\d+)\.apk$')
share_lock = threading.Lock()
share_sha = {}                                              # path -> (size, mtime, sha256)


def brawler_tags():
    """{Oros username: [tags]} of every account with a brawler tag (the Oros DB, read only); {} on error"""
    try:
        c = sqlite3.connect('file:%s?mode=ro' % OROS_DB, uri=True, timeout=5)
        try: rows = c.execute("SELECT username, COALESCE(tags, '') FROM users WHERE tags LIKE '%brawler_%'").fetchall()
        finally: c.close()
    except sqlite3.Error as e: log('oros accounts:', e); return {}
    return {n: [x for x in t.split(',') if x] for n, t in rows}


def brawler_accounts():
    """{Oros username: 'admin' | 'tester'} of every account with a brawler role (the Oros DB, read only); {} on error"""
    out = {n: brawler_role(t) for n, t in brawler_tags().items()}
    return {n: r for n, r in out.items() if r != 'none'}


def share_secret():
    with share_lock:
        if not os.path.exists(SHARE_SECRET):
            os.makedirs(SHARE, exist_ok=True)
            fd = os.open(SHARE_SECRET, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, secrets.token_hex(32).encode()); os.close(fd)
        return open(SHARE_SECRET, 'rb').read().strip()


def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def app_ticket(user, f):
    """a download link's ticket for APK file f: base64url {sub, f, exp}.hmac (24 h)"""
    p = b64u(json.dumps({'sub': user, 'f': f, 'exp': int(time.time()) + TICKET_S}).encode())
    return p + '.' + b64u(hmac.new(share_secret(), ('app.' + p).encode(), 'sha256').digest())


def app_ticket_ok(t, f):
    """the user a valid ticket for file f was made for (signature, expiry, still a brawler account), else None"""
    try:
        p, sig = t.split('.')
        if not hmac.compare_digest(sig, b64u(hmac.new(share_secret(), ('app.' + p).encode(), 'sha256').digest())): return None
        j = json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4)))
    except Exception: return None
    return j['sub'] if j.get('exp', 0) > time.time() and j.get('f') == f and j.get('sub') in brawler_accounts() else None


def app_latest():
    """(versionName, versionCode, file) of the newest Brawler APK in SHARE/app, or None"""
    best = None
    for n in os.listdir(SHARE_APP) if os.path.isdir(SHARE_APP) else []:
        m = APP_FILE.match(n)
        if m and (best is None or int(m.group(2)) > best[1]): best = (m.group(1), int(m.group(2)), n)
    return best


def share_builds():
    """{VERSION: path} of every build an account can be given: the published ones + the kept (assigned) ones"""
    out = {}
    for d in (BUILDS, SHARE_BUILDS):
        for n in os.listdir(d) if os.path.isdir(d) else []:
            m = BUILD_FILE.match(n)
            if m and not os.path.islink(os.path.join(d, n)): out.setdefault(m.group(1), os.path.join(d, n))
    return out


def published_newest():
    """the newest build `make publish-vps` uploaded (BUILDS), or None"""
    vs = [m.group(1) for n in (os.listdir(BUILDS) if os.path.isdir(BUILDS) else []) for m in [BUILD_FILE.match(n)]
          if m and not os.path.islink(os.path.join(BUILDS, n))]
    return max(vs, key=vkey) if vs else None


def share_build_for(name, role='tester', nightly=False):
    """(VERSION, path) the account plays in the Brawler app: the newest build up to its assignment; nothing assigned =
    (None, None) for a tester, the newest build for an admin. NIGHTLY (Oros tag brawler_nightly, Bruno 2026-10-16:
    "bleeding edge"): the newest published build, whatever the assignment"""
    have = share_builds()
    if nightly:
        v = published_newest()
        if v and v in have: return v, have[v]
    a = (section_load('players').get('draft') or {}).get('assign') or {}
    want = vkey((a.get(name) or a.get('*')) if role == 'tester' else a.get(name))   # (Bruno 2026-10-15: every tester gets the
                                                                    # same build, '*'; 2026-10-16: a tester's own row overrides it)
    if not want and role == 'admin' and have: want = max(vkey(v) for v in have)
    if not want: return None, None
    ok = sorted((v for v in have if vkey(v) <= want), key=vkey)
    return (ok[-1], have[ok[-1]]) if ok else (None, None)


def share_pin(versions):
    """keep the assigned builds (a hard link in SHARE/builds, a copy across file systems); drop the others there"""
    import shutil
    os.makedirs(SHARE_BUILDS, exist_ok=True)
    for v in versions:
        dst = os.path.join(SHARE_BUILDS, 'brawler-%s.neo' % v); src = os.path.join(BUILDS, 'brawler-%s.neo' % v)
        if os.path.exists(dst) or not os.path.exists(src): continue
        try: os.link(src, dst)
        except OSError: shutil.copyfile(src, dst)
    for n in os.listdir(SHARE_BUILDS):
        m = BUILD_FILE.match(n)
        if m and m.group(1) not in versions: os.remove(os.path.join(SHARE_BUILDS, n))


def sha_of(p):
    st = os.stat(p); hit = share_sha.get(p)
    if hit and hit[:2] == (st.st_size, st.st_mtime): return hit[2]
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    share_sha[p] = (st.st_size, st.st_mtime, h.hexdigest()); return h.hexdigest()


def players_clean(req):
    """the Players draft {assign: {"*": the testers' build, admin account: VERSION}}: every VERSION a build there is"""
    a = req.get('assign')
    accs = brawler_accounts(); have = share_builds()
    if not isinstance(a, dict) or not all((k == '*' or k in accs) and (v == '' or v in have) for k, v in a.items()):
        return None, 'assign: {"*" (every tester) or an admin account: a published VERSION or ""}'
    return {'assign': {k: v for k, v in a.items() if v}}, None


def players_state():
    """the Players tab: the draft + every account (its build now, last seen) + the builds to pick from (newest first)"""
    d = section_load('players')
    try: seen = json.load(open(SHARE_SEEN))
    except (OSError, ValueError): seen = {}
    bt = brawler_tags(); ba = {n: brawler_role(t) for n, t in bt.items()}; ba = {n: r for n, r in ba.items() if r != 'none'}
    accs = [{'name': n, 'role': ba[n], 'nightly': 'brawler_nightly' in bt[n], 'gets': share_build_for(n, ba[n], 'brawler_nightly' in bt[n])[0],
             'seen': seen.get(n)} for n in sorted(ba, key=str.lower)]
    return dict(d, accounts=accs, builds=sorted(share_builds(), key=vkey, reverse=True))


def section_file(n): return os.path.join(LAB, n + '.json')


def section_load(n):
    try: return json.load(open(section_file(n)))
    except (OSError, ValueError): return {}


def section_put(n, req, by, game=False):
    """the page's draft (a new revision, its shape checked by SECTIONS[n]), or the ship service's report of the game
    (<tool> state: what the build plays)"""
    p = section_file(n)
    with lab_lock:
        d = section_load(n)
        if game:
            if not isinstance(req, dict): return None, 'game: the section tool\'s state'
            d['game'] = dict(req, at=now())
        else:
            clean, err = (players_clean if n == 'players' else SECTIONS[n])(req)
            if err: return None, err
            d['draft'] = dict(clean, rev=((d.get('draft') or {}).get('rev') or 0) + 1, by=by, at=now())
            with open(p + '.history.jsonl', 'a') as hf: hf.write(json.dumps(d['draft'], ensure_ascii=False) + '\n')
        os.makedirs(LAB, exist_ok=True)
        with open(p + '.part', 'w') as o: json.dump(d, o, indent=1, ensure_ascii=False)
        os.replace(p + '.part', p)
    log('lab', n, 'game' if game else 'draft rev %d' % d['draft']['rev'], 'by', by)
    return d, None


SHIP_BEAT = os.path.join(LAB, 'ship_beat.json')               # the ship service's heartbeat (every 30 s)
SHIP_LOGS = os.path.join(LAB, 'ship_logs')                    # <id>.log: each request's log, uploaded by the service as it runs
MAX_SHIP_LOG = 8 << 20


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


# ---- cloud saves (Player 0.0.39) ------------------------------------------------------------------------------------
SAVES = os.path.join(DATA, 'saves')
SAVE_GAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')    # the ROM's name without .neo
SAVE_EXT = ('nv', 'srm', 'mcr', 'brm')                         # player.c flushSaves: MVS backup RAM, cart RAM, AES card, CD RAM
MAX_SAVE = 1 << 20                                             # the decoded files together (the MVS .nv is 64 KB)
SAVE_KEEP = 8                                                  # revision files kept (the current one + backups)
save_lock = threading.Lock()


def save_dir(user, game):
    u = user if re.match(r'^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$', user) else 'u-' + hashlib.sha256(user.encode()).hexdigest()[:24]
    return os.path.join(SAVES, u, game)


def save_state(d):
    try: return json.load(open(os.path.join(d, 'state.json')))
    except (OSError, ValueError): return {'rev': 0, 'last': 0, 'updated': 0, 'deleted': None}


def save_put(d, files, updated, base, backup=False):
    """(state, None) stored; (state, 'conflict') when the current revision is not base. backup: stored as a backup
    revision whatever the current one is (the current one unchanged)"""
    with save_lock:
        st = save_state(d)
        if not backup and int(base) != int(st.get('rev') or 0): return st, 'conflict'
        os.makedirs(d, exist_ok=True)
        rev = int(st.get('last') or st.get('rev') or 0) + 1
        size = sum(len(base64.b64decode(v)) for v in files.values())
        rec = {'rev': rev, 'updated': int(updated), 'files': files, 'size': size, 'saved_at': now(), 'backup': backup}
        write_json(os.path.join(d, 'r%d.json' % rev), rec)
        st['last'] = rev
        if not backup: st.update(rev=rev, updated=int(updated), size=size, saved_at=rec['saved_at'], deleted=None)
        write_json(os.path.join(d, 'state.json'), st)
        revs = sorted(int(n[1:-5]) for n in os.listdir(d) if re.match(r'^r\d+\.json$', n))
        for r in revs[:-SAVE_KEEP]:
            if r != st.get('rev'): os.remove(os.path.join(d, 'r%d.json' % r))
        return st, None


def save_get(d):
    st = save_state(d)
    if not st.get('rev'): return st, None
    try: return st, json.load(open(os.path.join(d, 'r%d.json' % st['rev'])))
    except (OSError, ValueError): return st, None


def save_delete(d):
    with save_lock:
        st = save_state(d)
        if not os.path.isdir(d): return st
        st.update(rev=0, deleted=int(time.time() * 1000))
        write_json(os.path.join(d, 'state.json'), st)
        return st


SETTINGS = os.path.join(DATA, 'settings')                     # <user>.json: the app's settings per account (0.0.44)


def settings_file(user):
    return os.path.join(SETTINGS, os.path.basename(os.path.dirname(save_dir(user, 'x'))) + '.json')


def admin_audit(by, action, target, detail=''):
    """the feedback side of the player admin's audit log (the Oros side: brawler_audit); the Players tab merges both"""
    with lock, db() as c:
        c.execute('INSERT INTO admin_audit (at, by, action, target, detail) VALUES (?,?,?,?,?)', (int(time.time()), by, action, target, detail))
    log('admin', by, action, target, detail)


def admin_players():
    """the Factory's Players tab (GET api/players, brawler admins): every account's play data, by Oros username:
    sessions (count, play seconds, first / last, the live one), devices, app versions, IPs (sessions, notes, replies,
    transcriptions), notes (all, open), last seen (share/latest.json), cloud saves, the app settings' language; + who
    is LIVE now (a chunk in the last LIVE_S seconds) and this side's audit log. The accounts themselves are Oros's
    (/oros/api/brawler/players)"""
    t = time.time(); out = {}
    def u(n): return out.setdefault(n, {'sessions': 0, 'seconds': 0.0, 'first': None, 'last': None, 'live': None, 'devices': [], 'apps': [],
                                         'ips': [], 'notes': 0, 'open': 0, 'seen': None, 'saves': [], 'language': ''})
    def add(lst, v):
        if v and v not in lst: lst.append(v)
    live = []
    with db() as c:
        for r in c.execute('SELECT user, COUNT(*) n, SUM(frames) f, MIN(first_at) a, MAX(last_at) b FROM sessions GROUP BY user'):
            d = u(r['user']); d.update(sessions=r['n'], seconds=round((r['f'] or 0) / FPS), first=r['a'], last=r['b'])
        for r in c.execute('SELECT * FROM sessions ORDER BY last_at DESC'):
            d = u(r['user']); add(d['devices'], r['device']); add(d['apps'], r['app_version']); add(d['ips'], r['ip'])
            if r['last_at'] and t - r['last_at'] < LIVE_S:
                live.append(session_row(r, t))
                if not d['live']: d['live'] = r['id']
        for r in c.execute("SELECT user, COUNT(*) n, SUM(CASE WHEN status IN ('new', 'read', 'in_progress', 'reopened') THEN 1 ELSE 0 END) o FROM feedback GROUP BY user"):
            if r['user']: u(r['user']).update(notes=r['n'], open=r['o'] or 0)
        for tbl in ('feedback', 'replies', 'transcriptions'):
            for r in c.execute(f'SELECT DISTINCT user, ip FROM {tbl} WHERE ip IS NOT NULL AND user IS NOT NULL'):
                if r['user'] and r['user'] != 'legacy': add(u(r['user'])['ips'], r['ip'])
            for r in c.execute(f"SELECT DISTINCT user, device FROM {tbl} WHERE device IS NOT NULL AND device != ''") if tbl != 'transcriptions' else []:
                if r['user'] and r['user'] != 'legacy': add(u(r['user'])['devices'], r['device'])
        aud = [row_dict(r) for r in c.execute('SELECT at, by, action, target, detail FROM admin_audit ORDER BY id DESC LIMIT 300')]
    try: seen = json.load(open(SHARE_SEEN))
    except (OSError, ValueError): seen = {}
    for n, s in seen.items():
        d = u(n); d['seen'] = s; add(d['apps'], s.get('app')); add(d['devices'], s.get('device'))
    for n in os.listdir(SAVES) if os.path.isdir(SAVES) else []:
        for g in os.listdir(os.path.join(SAVES, n)):
            st = save_state(os.path.join(SAVES, n, g))
            if st.get('rev'): u(n)['saves'].append({'game': g, 'size': st.get('size') or 0, 'rev': st['rev'], 'saved_at': st.get('saved_at')})
    for f in os.listdir(SETTINGS) if os.path.isdir(SETTINGS) else []:
        if f.endswith('.json'):
            try: u(f[:-5])['language'] = str((json.load(open(os.path.join(SETTINGS, f))).get('settings') or {}).get('language') or '')
            except (OSError, ValueError): pass
    return {'players': out, 'live': live, 'live_s': LIVE_S, 'now': t, 'audit': aud}


# ---- session recording (Player 0.0.41) ----------------------------------------------------------------------------
# docs/feedback.md "Session recording": the Player sends its play session in ~5 s chunks (Session.kt): the pads of its
# frames (NSIN v1) + the SHA-256 of the state at the chunk's start; a KEYFRAME chunk (every ~30 s since Player 0.0.43;
# every chunk from 0.0.41 / 0.0.42) carries that state too (gzip). Files on the storage box (the VPS root disk is near
# full): SESSIONS/<session>/meta.json + <seq>.nsin + <seq>.sha256 + <seq>.state.gz (keyframes); the index (state = 1: a
# keyframe) (+ the pads, zlib'd: ~200 bytes a chunk) in the
# tracker DB (sessions, session_chunks). Kept for good for now.
SESSIONS = os.environ.get('FEEDBACK_SESSIONS', '/mnt/storagebox/brawler-sessions')
SESSIONS_MOUNT = os.environ.get('FEEDBACK_SESSIONS_MOUNT', '/mnt/storagebox')   # must be mounted ('' = no check: proofs)
SESSION_ID = re.compile(r'^[0-9a-f]{8}-\d{8}-\d{6}$')                          # <install 8 hex>-<UTC start yyyymmdd-hhmmss>
MAX_CHUNK = 1 << 20                                                            # the POST (a chunk is ~35 KB)
MAX_CHUNK_FRAMES = 1200
MAX_STATE = 2 << 20                                                            # the state unpacked (Geolith v3: ~220 KB)
LIVE_S = 15                                                                    # a chunk this recent = the session is LIVE
FPS = 59.185606


def parse_chunk(b):
    """the POST body (Session.kt): "NSCK", u32 1, u32 n + JSON meta, u32 n + inputs (NSIN v1), u32 n + gzip'd state
    (n 0 = none) -> (meta, inputs, state_gz, state_raw); ValueError when anything is off"""
    import struct, zlib
    if len(b) < 12 or b[:4] != b'NSCK' or struct.unpack_from('<I', b, 4)[0] != 1: raise ValueError('not a chunk (NSCK v1)')
    o = 8; parts = []
    for _ in range(3):
        if o + 4 > len(b): raise ValueError('truncated')
        n = struct.unpack_from('<I', b, o)[0]; o += 4
        if o + n > len(b): raise ValueError('truncated')
        parts.append(b[o:o + n]); o += n
    if o != len(b): raise ValueError('trailing bytes')
    meta, inputs, gz = json.loads(parts[0]), parts[1], parts[2]
    if not isinstance(meta, dict) or not SESSION_ID.match(str(meta.get('session', ''))): raise ValueError('session id')
    seq, start, frames = meta.get('seq'), meta.get('start_frame'), meta.get('frames')
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (seq, start, frames)): raise ValueError('seq / start_frame / frames')
    if not (0 <= seq < 10 ** 7 and start >= 0 and 1 <= frames <= MAX_CHUNK_FRAMES): raise ValueError('seq / start_frame / frames out of range')
    if len(inputs) != 24 + 4 * frames or inputs[:4] != b'NSIN' or struct.unpack_from('<IQQ', inputs, 4) != (1, start, start + frames):
        raise ValueError('inputs: not NSIN v1 for these frames')
    if not SHA.match(str(meta.get('rom_sha256', ''))): raise ValueError('rom_sha256')
    if not SKEY.match(str(meta.get('system', ''))): raise ValueError('system')
    raw = b''
    if gz:
        try: d = zlib.decompressobj(16 + zlib.MAX_WBITS); raw = d.decompress(gz, MAX_STATE + 1)
        except zlib.error: raise ValueError('state: not gzip')
        if len(raw) > MAX_STATE or not d.eof: raise ValueError('state: too big or truncated')
        if len(raw) != meta.get('state_size') or hashlib.sha256(raw).hexdigest() != meta.get('state_sha256'): raise ValueError('state: size / sha256')
    elif meta.get('state_sha256') is not None and not SHA.match(str(meta['state_sha256'])): raise ValueError('state_sha256')
    return meta, inputs, gz, raw


def write_atomic(path, data):
    tmp = path + '.part'
    with open(tmp, 'wb') as f: f.write(data)
    os.replace(tmp, path)


def session_row(r, t=None):
    d = row_dict(r); t = t or time.time()
    d['seconds'] = round((d.get('frames') or 0) / FPS, 1)
    d['live'] = bool(d.get('last_at') and t - d['last_at'] < LIVE_S)
    d['last_ago'] = round(t - (d.get('last_at') or t), 1)
    return d


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
        """the signed-in API (/brawler-lab/feedback-api/, nginx: brawler admins only) or ssh on localhost (no token, no cookie)"""
        if self.headers.get('X-Public'): self.reply(404, {'error': 'not found'}); return False
        if self.headers.get('Authorization') or self.headers.get('Cookie'):
            if account_role(self.headers)[1] != 'admin': self.reply(403, {'error': 'for brawler admins only'}); return False
        return True

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path in ('/', '/health'): return self.reply(200, {'ok': True})
        if u.path == '/mine' or u.path.startswith('/mine/'): return self.mine(u.path.split('/')[2:])
        if u.path == '/dlauth': return self.dlauth()
        if u.path == '/me': return self.me()
        if u.path.startswith('/saves/'): return self.saves('GET')
        if u.path == '/settings': return self.settings('GET')
        if u.path.startswith('/share/'): return self.share_get(u.path.split('/')[2:])
        if u.path.startswith('/app/'): return self.app_get(u.path.split('/')[2], q)
        lab = self.lab_route()
        if lab is not None: return self.lab_get(lab)
        if not u.path.startswith('/api/') or not self.api_ok(): return self.reply(404, {'error': 'not found'})
        parts = u.path.split('/')[2:]
        if parts and parts[0] in ('sessions', 'session'): return self.sessions_api(parts, q)
        if parts == ['players']: return self.reply(200, admin_players())
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
                accs = brawler_accounts()
                for r in rows: r['tester'] = accs.get(r.get('user')) == 'tester'     # a tester's note (fb.py: "Wael [tester]")
                if q.get('user'): rows = [r for r in rows if (r.get('user') or '').lower() == q['user'][0].lower()]
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
        """nginx auth_request for the dev builds (/brawler/download/): 204 = a brawler admin's token or cookie (a tester
        or an untagged account: 403); or, while
        LEGACY_FLAG exists, a player older than 0.0.15 (X-App-Version < 0.0.15; its 5 s poll of latest.json sends only
        X-Install-Id, no version and no token)"""
        u, role = account_role(self.headers)
        if u and role == 'admin': return self.reply(204, body=b'')
        if u: return self.reply(403, {'error': 'for brawler admins only'})
        h = self.headers
        if os.path.exists(LEGACY_FLAG) and not h.get('Authorization') and (
                old_player(h.get('X-App-Version', '')) or (not h.get('X-App-Version') and INSTALL.match(h.get('X-Install-Id', '')))):
            return self.reply(204, body=b'')
        self.reply(401, {'error': 'sign in with your Oros account'})

    # ---- the Brawler app (nginx /brawler/feedback/me, share/, app/; X-Public; "THE BRAWLER APP" above) -----------------
    def me(self):
        """GET me: {user, role admin | tester, build (the VERSION the Brawler app plays), app {version, code, url, size,
        sha256} (the newest Brawler APK, its link with a 24 h ticket; the app downloads and checks it, PlayerUpdate.kt)}; 401 no sign-in, 403 an Oros account without a brawler role"""
        user, role, tags = account_full(self.headers)
        if not user: return self.reply(401, {'error': 'sign in with your Oros account'})
        if role == 'none': return self.reply(403, {'error': 'this account has no access to the brawler: ask Bruno', 'user': user, 'role': 'none'})
        a = app_latest()
        f = os.path.join(SHARE_APP, a[2]) if a else None
        app = {'version': a[0], 'code': a[1], 'url': 'app/%s?t=%s' % (a[2], app_ticket(user, a[2])),
               'size': os.path.getsize(f), 'sha256': sha_of(f)} if a else None
        self.reply(200, {'user': user, 'role': role, 'nightly': 'brawler_nightly' in tags, 'build': share_build_for(user, role, 'brawler_nightly' in tags)[0], 'app': app})

    def app_get(self, f, q):
        """GET app/<file>?t=<ticket>: the Brawler APK, for the phone's browser (no token there: the ticket from GET me)"""
        m = APP_FILE.match(f or '')
        p = os.path.join(SHARE_APP, f) if m else None
        user = app_ticket_ok((q.get('t') or [''])[0], f) if m else None
        if not user or not os.path.isfile(p): return self.reply(404, {'error': 'this link has expired: open the app again for a new one'})
        n = os.path.getsize(p)
        self.send_response(200); self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', 'attachment; filename="%s"' % f); self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(n)); self.end_headers()
        with open(p, 'rb') as fh:
            for b in iter(lambda: fh.read(1 << 20), b''): self.wfile.write(b)
        log('app', f, 'to', user)

    def share_get(self, parts):
        """the Brawler app's builds: GET share/latest.json: the account's build {version, build, file, size, sha256}
        (RomFetch's latest.json); GET share/build/brawler-<V>.neo: that build only (another version = 404)"""
        user, role, tags = account_full(self.headers)
        if not user: return self.reply(401, {'error': 'sign in with your Oros account'})
        if role not in ('admin', 'tester'): return self.reply(403, {'error': 'this account has no access to the brawler: ask Bruno'})
        v, path = share_build_for(user, role, 'brawler_nightly' in tags)
        if parts == ['latest.json']:
            h = self.headers
            with share_lock:
                try: seen = json.load(open(SHARE_SEEN))
                except (OSError, ValueError): seen = {}
                seen[user] = {'at': now(), 'rom': h.get('X-Rom-Version', ''), 'app': h.get('X-App-Version', ''), 'device': h.get('X-Device', '')[:60]}
                os.makedirs(SHARE, exist_ok=True)
                with open(SHARE_SEEN + '.part', 'w') as o: json.dump(seen, o)
                os.replace(SHARE_SEEN + '.part', SHARE_SEEN)
            if not v: return self.reply(404, {'error': 'no build assigned to ' + user})
            return self.reply(200, {'version': v, 'build': int(os.path.getmtime(path)), 'file': 'build/brawler-%s.neo' % v,
                                    'size': os.path.getsize(path), 'sha256': sha_of(path)})
        if len(parts) == 2 and parts[0] == 'build' and v and parts[1] == 'brawler-%s.neo' % v:
            n = os.path.getsize(path)
            self.send_response(200); self.send_header('Content-Type', 'application/octet-stream'); self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(n)); self.end_headers()
            with open(path, 'rb') as f:
                for b in iter(lambda: f.read(1 << 20), b''): self.wfile.write(b)
            log('share build', v, 'to', user)
            return
        self.reply(404, {'error': 'not found'})

    # ---- the player's own notes (signed in) ---------------------------------------------------------------------
    def player(self, legacy=False):
        """the signed-in account of a player call, or None (401 sent). Transition (until LEGACY_FLAG is removed):
        a player older than 0.0.15 (no login yet) may still upload and transcribe, logged as user 'legacy'"""
        user = account(self.headers)
        if not user and legacy and os.path.exists(LEGACY_FLAG) and old_player(self.headers.get('X-App-Version', '')):
            return 'legacy'
        if not user: self.reply(401, {'error': 'sign in with your Oros account'}); return None
        if account_role(self.headers)[1] not in ('admin', 'tester'):
            self.reply(403, {'error': 'this account has no access to the brawler: ask Bruno'}); return None
        claim(user, self.headers.get('X-Install-Id', ''))
        return user

    def admin_player(self):
        """player() for the admin-only player calls (the test queue, the decisions): a tester gets 403"""
        user = self.player()
        if user and account_role(self.headers)[1] != 'admin':
            self.reply(403, {'error': 'for brawler admins only'}); return None
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
        admin = account_role(self.headers)[1] == 'admin'
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
                revs = [review_dict(c, x, True) for x in c.execute("SELECT * FROM reviews WHERE audience IN ('', ?) ORDER BY id DESC", (user,)).fetchall()] if admin else []
                return self.reply(200, {'user': user, 'role': 'admin' if admin else 'tester', 'rows': rows, 'reviews': revs})   # reviews: the decisions (admins)
            if len(parts) == 3 and parts[0] == 'review' and parts[1].isdigit() and RFILE.match(parts[2]) and admin:
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
        """reads and writes: a brawler admin only (a tester or an untagged account: 403). No token / cookie at all and
        not through the public proxy = ssh on localhost (labcfg.py, labpub.py): user 'ssh'"""
        user, role = account_role(self.headers)
        if not user:
            h = self.headers
            if h.get('X-Public') or h.get('Authorization') or h.get('Cookie'):
                self.reply(401, {'error': 'sign in with your Oros account'}); return None
            user, role = 'ssh', 'admin'
        if role != 'admin': self.reply(403, {'error': 'for brawler admins only'}); return None
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
            try: beat = json.load(open(SHIP_BEAT))
            except (OSError, ValueError): beat = None
            return self.reply(200, {'requests': [x for x in lab_ships() if (not st or x['status'] == st) and (not fi or x['fighter'] == fi or fi in (x.get('fighters') or []))],
                                    'daemon': beat, 'now': now()})
        if parts == ['players']: return self.reply(200, players_state())          # the Factory's Players tab (brawler accounts)
        if len(parts) == 1 and parts[0] in SECTIONS: return self.reply(200, section_load(parts[0]))   # a Factory draft section + the game's
        if len(parts) == 2 and parts[0] == 'ship_log' and parts[1].isdigit():
            p = os.path.join(SHIP_LOGS, parts[1] + '.log')
            if not os.path.exists(p): return self.reply(404, {'error': 'no log for request ' + parts[1]})
            return self.reply(200, body=open(p, 'rb').read(), ctype='text/plain; charset=utf-8')
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
        if parts == ['players']:                             # the Players tab's Save: live at once (no ship)
            req = self.json_body(1 << 14)
            if req is None: return
            d, err = section_put('players', req, user)
            if err: return self.reply(400, {'error': err})
            share_pin(set(d['draft']['assign'].values()))
            return self.reply(200, players_state())
        sec = parts[0][:-5] if len(parts) == 1 and parts[0].endswith('_game') else parts[0] if len(parts) == 1 else None
        if sec in SECTIONS:                                  # a Factory draft section (levels, game) / the ship service's game report
            req = self.json_body(1 << 16)
            if req is None: return
            d, err = section_put(sec, req, user, parts[0] != sec)
            return self.reply(400, {'error': err}) if err else self.reply(200, d)
        if parts == ['ship_batch']:
            req = self.json_body(1 << 14)
            if req is None: return
            row, err = lab_ship_batch(req, user)
            return self.reply(400, {'error': err}) if err else self.reply(200, {'ship': row})
        if parts == ['ship_beat']:                           # the ship service: {host, state idle | building, id?, step?, pid?}
            req = self.json_body(1 << 12)
            if req is None: return
            beat = dict({k: req[k] for k in ('host', 'state', 'id', 'step', 'pid', 'version') if k in req}, at=now(), by=user)
            os.makedirs(LAB, exist_ok=True)
            with open(SHIP_BEAT + '.part', 'w') as o: json.dump(beat, o)
            os.replace(SHIP_BEAT + '.part', SHIP_BEAT)
            return self.reply(200, {'ok': True})
        if len(parts) == 2 and parts[0] == 'ship_log' and parts[1].isdigit():   # the service: the request's whole log so far
            b = self.body(MAX_SHIP_LOG)
            if b is None: return self.reply(413, {'error': 'a log of 1 B to %d B' % MAX_SHIP_LOG})
            os.makedirs(SHIP_LOGS, exist_ok=True)
            p = os.path.join(SHIP_LOGS, parts[1] + '.log')
            with open(p + '.part', 'wb') as o: o.write(b)
            os.replace(p + '.part', p)
            return self.reply(200, {'ok': True, 'size': len(b)})
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

    # ---- cloud saves (Player 0.0.39) ----------------------------------------------------------------------------
    def saves(self, method):
        u = urllib.parse.urlparse(self.path); parts = u.path.split('/')[2:]
        if len(parts) != 1 or not SAVE_GAME.match(parts[0]): return self.reply(404, {'error': 'not found'})
        user = self.player()
        if not user: return
        game = parts[0]; d = save_dir(user, game)
        if method == 'GET':
            st, rec = save_get(d)
            if not rec: return self.reply(404, {'error': 'no save', 'rev': 0, 'deleted': st.get('deleted')})
            b = (json.dumps({k: rec[k] for k in ('rev', 'updated', 'files', 'size', 'saved_at')}) + '\n').encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
            self.send_header('ETag', '"%d"' % rec['rev']); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
            return
        if method == 'DELETE':
            st = save_delete(d); log('save delete', user, game)
            return self.reply(200, {'rev': 0, 'deleted': st.get('deleted')})
        raw = self.body(MAX_SAVE * 2)
        if raw is None: return self.reply(413, {'error': 'empty or too big'})
        try:
            req = json.loads(raw); files = req['files']; updated = int(req.get('updated') or time.time() * 1000)
            if not isinstance(files, dict) or not files or any(k not in SAVE_EXT for k in files): raise ValueError('files')
            if sum(len(base64.b64decode(v, validate=True)) for v in files.values()) > MAX_SAVE: return self.reply(413, {'error': 'too big'})
            im = self.headers.get('If-Match', '').strip().strip('"')
            base = int(im) if im.isdigit() else int(req.get('base_rev') or 0)
        except (ValueError, KeyError, TypeError) as e: return self.reply(400, {'error': 'bad save: %s' % e})
        backup = urllib.parse.parse_qs(u.query).get('backup') == ['1']
        st, err = save_put(d, files, updated, base, backup)
        if err: return self.reply(409, {'error': 'another save is current', 'rev': st.get('rev') or 0, 'updated': st.get('updated') or 0,
                                        'deleted': st.get('deleted')})
        log('save', user, game, 'rev', st['last'], 'backup' if backup else 'current', st.get('size'))
        self.reply(200, {'rev': st['last'], 'updated': updated, 'current': not backup})

    def settings(self, method):
        """GET / PUT settings (app 0.0.44): the signed-in account's app settings {settings {language, scanlines, ...},
        updated (ms)}, restored after a sign-in on any device. PUT {settings, updated}: newest wins (an older one = 409
        with the stored one)"""
        user = self.player()
        if not user: return
        p = settings_file(user)
        try: cur = json.load(open(p))
        except (OSError, ValueError): cur = None
        if method == 'GET':
            return self.reply(200, cur) if cur else self.reply(404, {'error': 'no settings saved', 'updated': 0})
        raw = self.body(8192)
        if raw is None: return self.reply(413, {'error': 'empty or too big'})
        try:
            req = json.loads(raw); st = req['settings']; upd = int(req.get('updated') or time.time() * 1000)
            if not (isinstance(st, dict) and len(st) <= 40 and all(re.match(r'^[a-z][a-z0-9_]{0,31}$', k) and (
                    isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 64)) for k, v in st.items())): raise ValueError('settings')
        except (ValueError, KeyError, TypeError) as e: return self.reply(400, {'error': 'bad settings: %s' % e})
        if cur and int(cur.get('updated') or 0) > upd: return self.reply(409, cur)
        rec = {'settings': st, 'updated': upd, 'saved_at': now()}
        os.makedirs(os.path.dirname(p), exist_ok=True); write_json(p, rec)
        log('settings', user, st.get('language', ''))
        self.reply(200, rec)

    def reset_save(self):
        """POST api/players/reset_save {user, game?} (the Factory's Players tab, a brawler admin): the account's cloud
        save(s) deleted as the Player's Reset game save does (the revision files stay as backups); audited"""
        req = self.json_body(4096)
        if req is None: return
        user = str(req.get('user') or ''); game = str(req.get('game') or '')
        base = os.path.dirname(save_dir(user, 'x')) if user else ''
        if not user or not os.path.isdir(base): return self.reply(404, {'error': 'no cloud save for ' + user})
        games = [game] if game else sorted(n for n in os.listdir(base) if SAVE_GAME.match(n))
        done = []
        for g in games:
            if SAVE_GAME.match(g) and save_state(os.path.join(base, g)).get('rev'): save_delete(os.path.join(base, g)); done.append(g)
        admin_audit(account(self.headers) or 'ssh', 'reset_save', user, ', '.join(done) or 'nothing to reset')
        self.reply(200, dict(admin_players(), reset=done))

    def do_DELETE(self):
        if self.path.startswith('/saves/'): return self.saves('DELETE')
        self.reply(404, {'error': 'not found'})

    def do_PUT(self):
        if self.path.startswith('/saves/'): return self.saves('PUT')
        if self.path == '/settings': return self.settings('PUT')
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
        if self.path == '/sessions/chunk': return self.session_chunk()
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
        if self.path == '/api/players/reset_save': return self.reset_save()
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
        """Player 0.0.24: his answer to a decision put to him (the token only, a brawler admin), with an optional note:
        text and / or voice (transcribed by /transcribe first, like a reply)"""
        import base64
        user = self.admin_player()
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
        unpacked into DATA/attempts/<attempt id>/; a tester tests his own notes too (2026-10-15)"""
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

    # ---- session recording (Player 0.0.41) -------------------------------------------------------------------------
    def session_chunk(self):
        """POST sessions/chunk (the Player, signed in: a brawler admin or tester): one ~5 s chunk of his play session"""
        import zlib
        user = self.player()
        if not user: return
        body = self.body(MAX_CHUNK)
        if body is None: return self.reply(413, {'error': 'empty or too big'})
        try: meta, inputs, gz, raw = parse_chunk(body)
        except (ValueError, KeyError, TypeError) as e:
            log('session chunk refused:', user, e); return self.reply(400, {'error': 'bad chunk: %s' % e})
        if SESSIONS_MOUNT and not os.path.ismount(SESSIONS_MOUNT):
            log('session chunk: the storage box is not mounted'); return self.reply(503, {'error': 'storage unavailable'})
        sid, seq = meta['session'], meta['seq']; w = self.who(user); t = time.time()
        with lock, db() as c:
            r = c.execute('SELECT user FROM sessions WHERE id=?', (sid,)).fetchone()
            if r and r['user'] != user: return self.reply(403, {'error': "another account's session"})
            new = not r
            if new:
                st = meta.get('started')
                c.execute('INSERT INTO sessions (id, user, install_id, started, first_at, last_at, rom_sha, rom_version, rom_build, system, memcard, app, '
                          'app_version, device, android, ip) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (sid, user, w['install_id'] or '',
                           time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(st / 1000)) if isinstance(st, (int, float)) and st > 0 else now(),
                           t, t, meta['rom_sha256'], str(meta.get('rom_version') or '')[:20], str(meta.get('rom_build') or '')[:20], meta['system'],
                           str(meta.get('memcard') or '')[:4], str(meta.get('app') or '')[:10], str(meta.get('app_version') or '')[:20],
                           str(meta.get('device') or '')[:80], str(meta.get('android') or '')[:40], w['ip'] or ''))
        d = os.path.join(SESSIONS, sid)
        try:
            os.makedirs(d, exist_ok=True)
            if new or not os.path.exists(os.path.join(d, 'meta.json')): write_json(os.path.join(d, 'meta.json'), dict(meta, user=user, received=now()))
            write_atomic(os.path.join(d, '%06d.nsin' % seq), inputs)
            if meta.get('state_sha256'): write_atomic(os.path.join(d, '%06d.sha256' % seq), meta['state_sha256'].encode())   # (the Node replay's drift check)
            if gz: write_atomic(os.path.join(d, '%06d.state.gz' % seq), gz)
        except OSError as e:
            log('session chunk: write failed', sid, seq, e); return self.reply(503, {'error': 'storage write failed'})
        with lock, db() as c:
            old = c.execute('SELECT frames, bytes FROM session_chunks WHERE session=? AND seq=?', (sid, seq)).fetchone()   # a retry: replaced
            c.execute('INSERT OR REPLACE INTO session_chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                      (sid, seq, meta['start_frame'], meta['frames'], 1 if gz else 0, meta.get('state_size') if isinstance(meta.get('state_size'), int) else len(raw),
                       meta.get('state_sha256') or '',
                       len(body), t, 1 if meta.get('paused') else 0, zlib.compress(inputs[24:], 9)))
            c.execute('UPDATE sessions SET last_at=?, chunks=chunks+?, frames=frames+?, bytes=bytes+?, paused=? WHERE id=?',
                      (t, 0 if old else 1, meta['frames'] - (old['frames'] if old else 0), len(body) - (old['bytes'] if old else 0),
                       1 if meta.get('paused') else 0, sid))
        if new:
            jobs.put('rom:' + meta['rom_sha256'])                     # the Lab's player loads that build: archived
            log('session', sid, 'starts:', user, meta.get('rom_version'), meta['system'], meta.get('device'), meta.get('app_version'))
        self.reply(200, {'ok': True, 'session': sid, 'seq': seq})

    def sessions_api(self, parts, q):
        """the Lab's Sessions tab (feedback-api/, brawler admins): every player's sessions
          GET sessions[?limit=N]                    newest first, + the storage totals and the MB per hour
          GET session/<id>[?after=SEQ]              its row + its chunks (seq > after; state 1 = a keyframe) + its keyframes' seqs
          GET session/<id>/inputs[?from=SEQ]        the pads of its chunks from SEQ on: per chunk u32 seq + NSIN v1
          GET session/<id>/state/<seq>              that chunk's start state (gzip; Content-Encoding gzip)"""
        import struct, zlib
        t = time.time()
        num = lambda k, dflt: int(q[k][0]) if q.get(k) and q[k][0].lstrip('-').isdigit() else dflt
        with db() as c:
            if parts == ['sessions']:
                uq = (q.get('user') or [''])[0]                       # ?user=: one player's (the Factory's Players tab links here)
                rows = [session_row(r, t) for r in (c.execute('SELECT * FROM sessions WHERE user=? ORDER BY last_at DESC LIMIT ?', (uq, num('limit', 300))) if uq else
                                                    c.execute('SELECT * FROM sessions ORDER BY last_at DESC LIMIT ?', (num('limit', 300),)))]
                tot = c.execute('SELECT COUNT(*) n, COALESCE(SUM(bytes), 0) b, COALESCE(SUM(frames), 0) f FROM session_chunks').fetchone()
                hours = tot['f'] / FPS / 3600
                return self.reply(200, {'sessions': rows, 'now': t, 'live_s': LIVE_S, 'fps': FPS,
                                        'storage': {'chunks': tot['n'], 'bytes': tot['b'], 'hours': round(hours, 3),
                                                    'mb_per_hour': round(tot['b'] / 1e6 / hours, 1) if hours else None}})
            if len(parts) < 2 or parts[0] != 'session' or not SESSION_ID.match(parts[1]): return self.reply(404, {'error': 'not found'})
            r = c.execute('SELECT * FROM sessions WHERE id=?', (parts[1],)).fetchone()
            if not r: return self.reply(404, {'error': 'no such session'})
            if len(parts) == 2:
                ch = [row_dict(x) for x in c.execute('SELECT seq, start_frame, frames, state, state_size, state_sha, bytes, at, paused '
                                                     'FROM session_chunks WHERE session=? AND seq>? ORDER BY seq', (parts[1], num('after', -1)))]
                keys = [x[0] for x in c.execute('SELECT seq FROM session_chunks WHERE session=? AND state=1 ORDER BY seq', (parts[1],))]
                return self.reply(200, {'session': session_row(r, t), 'chunks': ch, 'keys': keys, 'now': t})
            if len(parts) == 3 and parts[2] == 'inputs':
                out = io.BytesIO()
                for x in c.execute('SELECT seq, start_frame, frames, inputs FROM session_chunks WHERE session=? AND seq>=? ORDER BY seq', (parts[1], num('from', 0))):
                    out.write(struct.pack('<I4sIQQ', x['seq'], b'NSIN', 1, x['start_frame'], x['start_frame'] + x['frames'])); out.write(zlib.decompress(x['inputs']))
                return self.reply(200, body=out.getvalue(), ctype='application/octet-stream')
        if len(parts) == 4 and parts[2] == 'state' and parts[3].isdigit():
            p = os.path.join(SESSIONS, parts[1], '%06d.state.gz' % int(parts[3]))
            if not os.path.exists(p): return self.reply(404, {'error': 'no state for that chunk'})
            b = open(p, 'rb').read()
            self.send_response(200); self.send_header('Content-Type', 'application/octet-stream'); self.send_header('Content-Encoding', 'gzip')
            self.send_header('Cache-Control', 'private, max-age=31536000, immutable'); self.send_header('Content-Length', str(len(b))); self.end_headers()
            self.wfile.write(b); return
        self.reply(404, {'error': 'not found'})

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
        for r in c.execute("SELECT DISTINCT rom_sha FROM feedback"): jobs.put('rom:' + (r['rom_sha'] or ''))   # (a row without one: NULL)
    log('listening on 127.0.0.1:%d, data %s' % (PORT, DATA))
    Server(('127.0.0.1', PORT), H).serve_forever()
