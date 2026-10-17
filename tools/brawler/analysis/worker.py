#!/usr/bin/env python3
"""The replay analysis worker (VPS unit brawler-analysis, deploy_vps.sh): token-free statistics of every recorded play
session, no Claude and no desktop involved. Stdlib only + the Geolith core (harness.py through analyze.py).

Every POLL seconds: the sessions in the feedback service's index (FEEDBACK_DB, read only) that are FINISHED (no new
chunk for GAP seconds) and not yet analysed by this ANALYZER version with all their chunks are replayed, newest first,
ONE AT A TIME, each in its own process (analyze.py: the core is a process global), with the pack of their build
(ANALYSIS/builds/<VERSION>/pack.json, matched by the ROM's SHA-256) and the ROM from the feedback archive
(/data/brawler/feedback/roms/<sha>.neo.gz, unpacked once into CACHE on the storage box) or the builds dir. Results:
ANALYSIS/results/<session>.json.gz (the whole analysis: events, screens, segments, summary) + one row per session in
ANALYSIS/stats.db (runs: status ok | error | nopack | norom | empty | running, the drift check, the summary and the
segments as JSON), then ANALYSIS/aggregates.json (per player and per build, aggregate()). A re-run request =
the file ANALYSIS/rerun/<session> (the admin page's button, server.py POST api/stats/rerun). Idempotent and resumable:
a crash or a restart re-runs the session that was running; nothing is analysed twice for the same chunks + ANALYZER.

    python3 worker.py                 the loop (the unit)
    python3 worker.py --once [ID]     one pass (or that session) and exit
    python3 worker.py --aggregate     only rewrite aggregates.json"""
import argparse, gzip, hashlib, json, os, shutil, sqlite3, statistics, subprocess, sys, time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from analyze import ANALYZER, FPS, SLOT_ROLE

ANALYSIS = os.environ.get('ANALYSIS', '/data/brawler/analysis')
FEEDBACK_DB = os.environ.get('FEEDBACK_DB', '/data/brawler/feedback/feedback.db')
SESSIONS = os.environ.get('SESSIONS', '/mnt/storagebox/brawler-sessions')
ROMS = os.environ.get('ROMS', '/data/brawler/feedback/roms')
BUILDS = os.environ.get('BUILDS', '/data/brawler/builds')
CACHE = os.environ.get('CACHE', '/mnt/storagebox/brawler-analysis/roms')
BIOS = os.environ.get('BIOS', os.path.join(ANALYSIS, 'bios'))
GAP = int(os.environ.get('GAP', '600'))               # a session with no chunk for this long is finished
POLL = int(os.environ.get('POLL', '60'))
TIMEOUT = int(os.environ.get('TIMEOUT', '7200'))      # one session's replay at most
DB = os.path.join(ANALYSIS, 'stats.db'); RESULTS = os.path.join(ANALYSIS, 'results'); RERUN = os.path.join(ANALYSIS, 'rerun')
PROGRESS = os.path.join(ANALYSIS, 'progress.json'); AGG = os.path.join(ANALYSIS, 'aggregates.json')


def log(*a): print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


def db():
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS runs (session TEXT PRIMARY KEY, status TEXT, analyzer INTEGER, chunks INTEGER,
        rom_sha TEXT, rom_version TEXT, user TEXT, install_id TEXT, device TEXT, first_at REAL, last_at REAL, frames INTEGER,
        started REAL, finished REAL, wall_s REAL, cpu_s REAL, checked INTEGER, mismatches TEXT, gaps TEXT, error TEXT,
        summary TEXT, segments TEXT)''')
    return c


def feedback_sessions():
    c = sqlite3.connect('file:%s?mode=ro' % FEEDBACK_DB, uri=True, timeout=30); c.row_factory = sqlite3.Row
    try: return [dict(r) for r in c.execute('SELECT id, user, install_id, first_at, last_at, chunks, frames, rom_sha, rom_version, device FROM sessions')]
    finally: c.close()


def packs():
    out = {}
    for v in os.listdir(os.path.join(ANALYSIS, 'builds')) if os.path.isdir(os.path.join(ANALYSIS, 'builds')) else []:
        p = os.path.join(ANALYSIS, 'builds', v, 'pack.json')
        if not os.path.exists(p): continue                  # (being sent)
        try: out[json.load(open(p))['rom_sha256']] = p
        except Exception as e: log('pack', p, 'unreadable:', e)
    return out


def rom_for(sha, version):
    """the build's ROM as a plain .neo (the core loads a path): the cache, else unpacked from the feedback archive, else
    the published builds dir (sha checked); None = nowhere"""
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, sha + '.neo')
    if os.path.exists(out): return out
    src = os.path.join(ROMS, sha + '.neo.gz')
    if os.path.exists(src):
        with gzip.open(src, 'rb') as f, open(out + '.part', 'wb') as g: shutil.copyfileobj(f, g, 1 << 20)
    else:
        b = os.path.join(BUILDS, 'brawler-%s.neo' % version)
        if not os.path.exists(b): return None
        shutil.copyfile(b, out + '.part')
    h = hashlib.sha256()
    with open(out + '.part', 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''): h.update(blk)
    if h.hexdigest() != sha: os.unlink(out + '.part'); return None
    os.replace(out + '.part', out); return out


def wanted(s, run, now, reruns):
    if s['id'] in reruns: return True
    if not s['last_at'] or now - s['last_at'] < GAP: return False          # still being recorded
    if run is None: return True
    if run['status'] == 'running': return True                              # a crash / restart in the middle
    if run['status'] in ('nopack', 'norom'): return run['status'] != status_of(s)   # retry once its pack / ROM exists
    if run['analyzer'] != ANALYZER: return True
    return run['chunks'] != s['chunks'] and run['status'] != 'error'


_packs = {}
def status_of(s):
    if s['rom_sha'] not in _packs: return 'nopack'
    return 'norom' if not (os.path.exists(os.path.join(CACHE, s['rom_sha'] + '.neo')) or os.path.exists(os.path.join(ROMS, s['rom_sha'] + '.neo.gz'))
                           or os.path.exists(os.path.join(BUILDS, 'brawler-%s.neo' % s['rom_version']))) else 'ok'


def run_one(s):
    sid = s['id']; t0 = time.time()
    base = {k: s.get(k) for k in ('chunks', 'rom_sha', 'rom_version', 'user', 'install_id', 'device', 'first_at', 'last_at', 'frames')}
    def save(**kw):
        row = dict(base, session=sid, analyzer=ANALYZER, **kw)
        with db() as c:
            c.execute('INSERT OR REPLACE INTO runs (%s) VALUES (%s)' % (','.join(row), ','.join('?' * len(row))), list(row.values()))
    d = os.path.join(SESSIONS, sid)
    if not os.path.exists(os.path.join(d, 'meta.json')) or not any(f.endswith('.state.gz') for f in os.listdir(d)):
        return save(status='empty', finished=time.time(), error='no meta.json or no keyframe')
    pk = _packs.get(s['rom_sha'])
    if not pk: return save(status='nopack', finished=time.time(), error='no analysis pack for build %s' % s['rom_version'])
    rom = rom_for(s['rom_sha'], s['rom_version'])
    if not rom: return save(status='norom', finished=time.time(), error='ROM %s not archived' % s['rom_sha'][:12])
    save(status='running', started=t0)
    os.makedirs(RESULTS, exist_ok=True); out = os.path.join(RESULTS, sid + '.json.gz')
    log('analyse', sid, s['user'], s['rom_version'], s['chunks'], 'chunks')
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, 'analyze.py'), d, pk, rom, '--bios', BIOS, '--out', out,
                            '--progress', PROGRESS], capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return save(status='error', started=t0, finished=time.time(), wall_s=round(time.time() - t0, 1), error='timeout %d s' % TIMEOUT)
    if p.returncode != 0:
        log('  failed:', p.stderr.strip()[-400:])
        return save(status='error', started=t0, finished=time.time(), wall_s=round(time.time() - t0, 1), error=p.stderr.strip()[-1500:])
    r = json.load(gzip.open(out))
    save(status='ok', started=t0, finished=time.time(), wall_s=r['wall_s'], cpu_s=r['cpu_s'], checked=r['checked'],
         mismatches=json.dumps(r['mismatches']), gaps=json.dumps(r['gaps']), summary=json.dumps(r['summary']),
         segments=json.dumps([{k: v for k, v in g.items()} for g in r['segments']]), chunks=r['chunks'])
    log('  ok', r['wall_s'], 's,', r['checked'], 'checked,', len(r['mismatches']), 'mismatches')


def seg_key(g): return 'S%d %s' % (g['stage'], 'BONUS' if g['kind'] == 'bonus' else 'BOSS' if g['kind'] == 'boss' else 'W%d' % g['wave'])
def seg_rank(k):
    st, w = k.split(' '); return (int(st[1:]), 2 if w == 'BONUS' else 1 if w == 'BOSS' else 0, int(w[1:]) if w.startswith('W') else 0)


def aggregate():
    """per player (lower-case user) and per build: sessions, play / fight time, deaths, continues, the furthest point,
    per segment (S<stage> W<wave> / BOSS / BONUS): the median duration, deaths, lives lost, damage taken, plays;
    death hotspots, the moves used (fighter: role input) most first, the slots never used, the drop-off (where the
    sessions ended)"""
    with db() as c: rows = [dict(r) for r in c.execute("SELECT * FROM runs WHERE status='ok'")]
    pk = {}
    for sha, p in _packs.items():
        try: pk[sha] = json.load(open(p))
        except Exception: pass
    def group(rs):
        g = {'sessions': len(rs), 'play_s': 0, 'fight_s': 0, 'deaths': 0, 'continues': 0, 'gameovers': 0, 'specials': 0,
             'furies': 0, 'dmg_taken': 0, 'dmg_dealt': 0, 'fighters': Counter(), 'furthest': None, 'segments': {},
             'moves': Counter(), 'dropoff': Counter(), 'ends': Counter(), 'users': Counter(), 'builds': Counter(),
             'fight_sessions': 0, 'mismatch_sessions': 0}
        segd = defaultdict(lambda: {'n': 0, 'secs': [], 'deaths': 0, 'dmg_taken': 0, 'won': 0})
        slots = defaultdict(set)
        for r in rs:
            sm = json.loads(r['summary'] or '{}'); segs = json.loads(r['segments'] or '[]')
            g['play_s'] += sm.get('seconds', 0); g['fight_s'] += sm.get('fight_s', 0)
            for k in ('deaths', 'continues', 'gameovers', 'specials', 'furies', 'dmg_taken', 'dmg_dealt'): g[k] += sm.get(k, 0) or 0
            g['users'][(r['user'] or '?').lower()] += 1; g['builds'][r['rom_version']] += 1
            if json.loads(r['mismatches'] or '[]'): g['mismatch_sessions'] += 1
            for f in sm.get('fighters', []): g['fighters'][f] += 1
            fu = sm.get('furthest')
            if fu:
                k = seg_key(fu); g['fight_sessions'] += 1
                if g['furthest'] is None or seg_rank(k) > seg_rank(g['furthest']): g['furthest'] = k
            if segs: g['dropoff'][seg_key(segs[-1])] += 1
            g['ends'][sm.get('end', '?')] += 1
            p = pk.get(r['rom_sha'])
            for s in segs:
                k = seg_key(s); d = segd[k]; d['n'] += 1; d['secs'].append(s['seconds'])
                if s.get('won'): d['won'] += 1
                for pl in s['players'].values():
                    d['deaths'] += pl['deaths']; d['dmg_taken'] += pl['dmg_taken']
                    if s['kind'] != 'bonus':
                        for m, n in pl['specials'].items(): g['moves'][(pl['fighter'] or '?') + ': ' + m] += n
                    if p and pl['fighter']:
                        for f in p['fighters']:
                            if f['name'] == pl['fighter']:
                                for slot, inp in (f.get('specials') or {}).items():
                                    if SLOT_ROLE.get(slot) and inp: slots[f['name']].add(SLOT_ROLE[slot] + ' ' + inp)
                                slots[f['name']].add('fury (D)')
        for k in sorted(segd, key=seg_rank):
            d = segd[k]
            g['segments'][k] = {'n': d['n'], 'median_s': round(statistics.median(d['secs']), 1), 'min_s': min(d['secs']),
                                'max_s': max(d['secs']), 'deaths': d['deaths'], 'deaths_per_play': round(d['deaths'] / d['n'], 2),
                                'dmg_taken': d['dmg_taken'], 'won': d['won'], 'ended_here': g['dropoff'].get(k, 0)}
        used = set(g['moves'])
        fury_used = {u.split(': ')[0] for u in used if u.split(': ', 1)[1].startswith(('fury', 'MAX'))}
        g['unused'] = sorted('%s: %s' % (f, m) for f, ms in slots.items() for m in ms
                             if (f not in fury_used if m == 'fury (D)' else '%s: %s' % (f, m) not in used))
        g['hotspots'] = sorted(([k, v['deaths']] for k, v in g['segments'].items() if v['deaths']), key=lambda x: -x[1])[:8]
        g['moves'] = g['moves'].most_common(); g['dropoff'] = sorted(g['dropoff'].items(), key=lambda x: -x[1])
        for k in ('fighters', 'ends', 'users', 'builds'): g[k] = dict(g[k].most_common())
        g['play_s'] = round(g['play_s'], 1); g['fight_s'] = round(g['fight_s'], 1)
        return g
    by_u = defaultdict(list); by_b = defaultdict(list)
    for r in rows: by_u[(r['user'] or '?').lower()].append(r); by_b[r['rom_version'] or '?'].append(r)
    agg = {'analyzer': ANALYZER, 'at': time.time(), 'all': group(rows),
           'players': {u: group(rs) for u, rs in sorted(by_u.items())},
           'builds': {b: group(rs) for b, rs in sorted(by_b.items(), key=lambda x: [int(n) if n.isdigit() else 0 for n in x[0].split('.')])}}
    tmp = AGG + '.part'; json.dump(agg, open(tmp, 'w'), separators=(',', ':')); os.replace(tmp, AGG)


def one_pass(only=None):
    global _packs
    _packs = packs(); now = time.time()
    os.makedirs(RERUN, exist_ok=True)
    reruns = set(os.listdir(RERUN))
    with db() as c: runs = {r['session']: dict(r) for r in c.execute('SELECT * FROM runs')}
    todo = [s for s in sorted(feedback_sessions(), key=lambda s: -(s['last_at'] or 0))
            if (s['id'] == only if only else wanted(s, runs.get(s['id']), now, reruns))]
    todo.sort(key=lambda s: s['id'] not in reruns)          # requests first
    did = 0
    for s in todo[:1] if not only else todo:                 # one session, then re-read the index (new ones first)
        try: os.unlink(os.path.join(RERUN, s['id']))
        except FileNotFoundError: pass
        run_one(s); did += 1
    for f in reruns - {s['id'] for s in feedback_sessions()}:
        os.unlink(os.path.join(RERUN, f))                    # a request for no session
    if did: aggregate()
    try: os.unlink(PROGRESS)
    except FileNotFoundError: pass
    return did, len(todo)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--once', nargs='?', const='', default=None); ap.add_argument('--aggregate', action='store_true')
    a = ap.parse_args()
    os.makedirs(ANALYSIS, exist_ok=True); db().close()
    if a.aggregate:
        global _packs
        _packs = packs(); aggregate(); return
    if a.once is not None:
        while True:
            did, left = one_pass(a.once or None)
            if a.once or not did: break
        return
    log('brawler-analysis: analyzer', ANALYZER, 'gap', GAP, 's, data', ANALYSIS)
    if not os.path.exists(AGG): _packs.update(packs()); aggregate()
    while True:
        try: did, left = one_pass()
        except Exception as e: log('pass failed:', repr(e)); did, left = 0, 0
        if not did or left <= 1: time.sleep(POLL)


if __name__ == '__main__':
    main()
