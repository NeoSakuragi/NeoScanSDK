#!/usr/bin/env python3
"""The Character Lab's live fighter configs on the VPS (docs/character_lab.md "Character Lab"; the feedback service
tools/feedback/server.py, its /api/lab/ over ssh on localhost = authenticated by the ssh key, user "ssh").

The VPS is the source of truth while Bruno tunes a fighter in the web Assembly; every PUT is a revision kept for good
(LAB/config/<f>.history.jsonl). NO STAGING (Bruno 2026-10-10: "forget about staging, remove that step"): what the
Assembly saves goes to the Player's Character lab at once; the GAME (the Player's brawler, the VPS download) changes
only when Bruno presses the sheet's "Ship to the game" (2026-10-12): a ship request (POST lab/ship/<f>) that THE SHIP
SERVICE ships with no agent (docs/character_lab.md "Ship service"):

    labcfg.py ship-worker [--once] [--fighter F] [--conf /data/brawler-ship/ship.json] [--logs DIR]
        brawler-ship.service (systemd --user), run from the ship checkout (conf "repo": a detached git worktree nobody
        edits; every host path in the conf, tools/brawler/ship.example.json). Each request, one at a time (a fighter's
        older pending ones: dropped, superseded), stopping at the first failure ("<step>: <reason>", the checkout reset,
        the VPS untouched before the checks pass): reset + git pull --ff-only origin brawler, VERSION +1, arb_compile.py F
        (his sheet -> game.json, built, every linked slot checked; "nothing changed" ends here, no new version), levels.py
        merge (a request with "levels": the Factory's Levels draft -> game.json stage names / backgrounds / songs),
        rm build/*.o + make -C sdk + make -jN, bank_proof ALL OK, regress.py --bleed-only True / True, git commit
        (game.json, VERSION, docs/brawler_gold.md), make publish-vps, scenario.py publish, labpub.py all --if-changed,
        push origin HEAD:brawler -> done "shipped 0.10.N". One log per request: <logs>/<id>.log.
    labcfg.py ship-pending                          the requests waiting: id, fighter, revision, who, when
    labcfg.py ship FIGHTER [--rev N] [--note ...]   queue one from here (as a live send does)
    labcfg.py ship-done ID [--dropped] [--note "0.0.120, commit abc123"]   close a request by hand

    labcfg.py list                                  every fighter's live config: revision, hash, when, by whom
    labcfg.py show FIGHTER [--rev N] [--blob]       the config's JSON (the roster entry form); --blob: the RAM-loads bytes as hex
    labcfg.py history FIGHTER                       every revision, oldest first
    labcfg.py revert FIGHTER REV [--note "..."]     a NEW revision with revision REV's blob + JSON (nothing is deleted)
    labcfg.py export FIGHTER [--rev N] [--dry-run] [--game examples/brawler]
                                                    the JSON written as the fighter's roster entry in game.json (key by key:
                                                    unchanged keys keep their text, arb_compile.write_game)
    labcfg.py put FIGHTER --blob FILE [--json FILE] [--note "..."] [--if-match HASH]
                                                    a revision from the desktop; --json defaults to the repo's roster entry

The blob is opaque here (its byte format: chainlab/lab.js liveBlob = the TRY blob + an optional chain override); its
hash = sha256 of the bytes, what the player polls. A revision sent by a Lab page ("Send to Player") has the JSON
{name, lab_try: {page, try, chain}} (what the page played): `show` prints it, `export` refuses it (ship it with
arb_compile.py / chain_save.py)."""
import argparse, base64, datetime, hashlib, json, os, re, shlex, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
HOST = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/lab/'


def api(path, body=None, method=None, headers=()):
    cmd = f'curl -s -S --max-time 30 {shlex.quote(BASE + path)}'
    for h in headers: cmd += ' -H ' + shlex.quote(h)
    if body is not None: cmd += f" -X {method or 'POST'} -H 'Content-Type: application/json' --data-binary @-"
    r = subprocess.run((['ssh', '-o', 'BatchMode=yes', HOST, cmd] if HOST else ['sh', '-c', cmd]), input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if r.returncode: raise SystemExit('ssh/curl: ' + r.stderr.strip())
    out = json.loads(r.stdout)
    if isinstance(out, dict) and 'error' in out: raise SystemExit('server: ' + out['error'])
    return out


def head(r):
    rv = f"  (revert of rev {r['reverted_from']})" if r.get('reverted_from') else ''
    return (f"rev {r['version']:>4}  {r['hash'][:16]}  {r['size']:>7} B  {r['updated'][:16].replace('T', ' ')}  {r['by']:<12}"
            + (f"  {r['note']}" if r.get('note') else '') + rv)


def mark(i, status, note='', **kw):
    return api('ship_done', dict({'id': i, 'status': status, 'note': note[:600]}, **{k: v for k, v in kw.items() if v}))['ship']


def api_raw(path, data):
    """POST raw bytes (a ship log) to the feedback service, as api() does JSON"""
    cmd = f"curl -s -S --max-time 60 -X POST -H 'Content-Type: text/plain' --data-binary @- {shlex.quote(BASE + path)}"
    r = subprocess.run((['ssh', '-o', 'BatchMode=yes', HOST, cmd] if HOST else ['sh', '-c', cmd]), input=data, capture_output=True)
    return r.returncode == 0


FOOTER = ('\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n'
          'Claude-Session: https://claude.ai/code/session_01XhxN754ESQrKXnzjnRdvPt\n')
# the Factory's Build tab shows a ship as these phases (each step of ship_one belongs to one)
PHASE = {'reset': 'pull', 'git pull': 'pull', 'arb_compile': 'compile', 'levels': 'compile', 'make sdk': 'build', 'make': 'build', 'bank_proof': 'checks',
         'regress bleed': 'checks', 'commit': 'publish', 'publish-vps': 'publish', 'scenario publish': 'publish', 'labpub': 'Lab packs', 'push': 'push'}
STATE = {'state': 'idle'}                                # what the heartbeat says (ship_one updates it)


def ship_conf(path):
    """the ship service's host config (JSON, outside the repo; tools/brawler/ship.example.json): repo (the ship checkout),
    logs, jobs, nice, poll, lab_host (the feedback service over ssh; "" = curl on this host: the VPS itself), env (added
    to every step: BRAWLER_CORE, PATH ...). Nothing in it is a secret: ssh / gh use the user's own keys."""
    c = {'repo': REPO, 'logs': '/data/brawler-ship/logs', 'jobs': 4, 'nice': 10, 'poll': 30, 'lab_host': HOST, 'env': {}}
    if path and os.path.exists(path): c.update(json.load(open(path)))
    return c


class Fail(Exception): pass


def ship_one(c, fighters, row):
    """one ship, in the ship checkout c['repo'] (nobody edits it) -> (status, note, version, changes). fighters: the sheets
    compiled (one or several: ONE version); none = a rebuild of the game as pushed (an engine merge). Stops at the first
    failure ("<step>: <reason>"; the checkout reset, nothing reaches the VPS before the checks pass). Every step's output:
    <logs>/<id>.log, uploaded to the feedback service after each step (the Factory's Build tab reads it there)"""
    repo = c['repo']; game = os.path.join(repo, 'examples', 'brawler'); bl = os.path.join(repo, 'tools', 'brawler')
    vp = os.path.join(game, 'VERSION'); env = dict(os.environ, **c['env']); nice = ['nice', '-n', str(c['nice'])]
    os.makedirs(c['logs'], exist_ok=True)
    lp = os.path.join(c['logs'], f'{row["id"]}.log')
    logf = open(lp, 'w')
    st = {'v': None}
    up = lambda: (logf.flush(), api_raw(f'ship_log/{row["id"]}', open(lp, 'rb').read()))

    def run(step, cmd, cwd=repo, ok=None, timeout=3600):
        ph = PHASE.get(step, step)
        STATE.update(state='building', id=row['id'], step=ph, version=st['v'])
        mark(row['id'], 'building', f'building {st["v"] or "?"}: {step}', step=ph, version=st['v'])
        print(f'[ship #{row["id"]}] {row["fighter"]}: {step}', flush=True)
        logf.write(f'\n==== {step}: {" ".join(cmd)}\n'); up()
        t0 = time.time()
        try: r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired: raise Fail(f'{step}: timed out after {timeout} s')
        out = r.stdout + r.stderr
        logf.write(out + f'\n==== {step}: exit {r.returncode} in {time.time() - t0:.0f} s\n'); up()
        if r.returncode or (ok and not ok(out)):
            last = [x.strip() for x in out.splitlines() if x.strip()]
            why = last[-1:] if 'Traceback' in out else ([x for x in last if x.startswith(('REFUSED', '- ', 'FAIL', 'error', 'fatal', 'bleed:'))] or last[-2:])
            raise Fail(f'{step}: ' + ' '.join(why)[:400])
        return out

    g = lambda *x: ['git', '-C', repo] + list(x)
    py = lambda name, *x: nice + [sys.executable, os.path.join(bl, name)] + list(x)
    start = None; changes = []; left = []
    try:
        run('reset', g('reset', '-q', '--hard', 'HEAD'))
        run('git pull', g('fetch', '-q', 'origin', 'brawler'))
        run('git pull', g('merge', '-q', '--ff-only', 'FETCH_HEAD'))
        start = run('git pull', g('rev-parse', 'HEAD')).strip()
        v0 = open(vp).read().strip(); p = v0.split('.'); p[-1] = str(int(p[-1]) + 1); st['v'] = v1 = '.'.join(p)
        open(vp, 'w').write(v1 + '\n')                   # (first: arb_compile's build and gold section carry it)
        for f in fighters:
            out = run('arb_compile', py('arb_compile.py', f, '--game', game))
            lines = out.splitlines()
            left += [f + ': ' + x.strip()[2:] for x in lines[next((i for i, x in enumerate(lines) if x.startswith('REPORT ')), len(lines)):] if x.strip().startswith('- ')]
            changes += [f + ': ' + x.split(':', 1)[1].strip() for x in lines if x.startswith('game.json roster changes:') and not x.startswith('game.json roster changes: none')]
        if row.get('levels'):                            # the Factory's Levels draft (lab/levels), as it is now
            dp = os.path.join(c['logs'], f'{row["id"]}_levels.json')
            json.dump(api('levels').get('draft') or {}, open(dp, 'w'))
            out = run('levels', py('levels.py', 'merge', game, dp))
            changes += [x for x in out.splitlines() if x.startswith('levels: stage ')]
        if (fighters or row.get('levels')) and not changes:
            run('reset', g('reset', '-q', '--hard', 'HEAD'))
            logf.write('\nnothing changed\n'); up(); logf.close()
            return 'done', f'nothing changed: the game already plays this sheet ({v0})', None, []
        if not fighters and not row.get('levels'): changes = ['rebuild: no data change (the engine as pushed)']
        bd = os.path.join(game, 'build')
        for x in os.listdir(bd):
            if x.endswith('.o'): os.remove(os.path.join(bd, x))
        run('make sdk', nice + ['make', '-C', 'sdk'])
        run('make', nice + ['make', f'-j{c["jobs"]}'], cwd=game)
        run('bank_proof', py('bank_proof.py', game), ok=lambda o: 'ALL OK' in o)
        run('regress bleed', py('regress.py', game, os.path.join(c['logs'], f'{row["id"]}_regress.json'), '--bleed-only'),
            ok=lambda o: re.search(r'bleed: .*: True frame-exact: True', o))
        paths = ['examples/brawler/game.json', 'examples/brawler/VERSION', 'docs/brawler_gold.md']
        what = (', '.join(fighters) + ' shipped from the Assembly' + (f' (rev {row["rev"]})' if row.get('rev') else '')) if fighters else 'rebuild (no data change)'
        if row.get('levels'): what = (what + ' + ' if fighters else '') + f'levels shipped from the Factory (draft rev {row["levels"]})'
        run('commit', g('add', '--', *paths))                # (before the publish: scenario.py publish finds the build
        run('commit', g('commit', '-q', '-m', f'Brawler {v1}: {what}' + FOOTER, '--', *paths))
        run('publish-vps', ['make', '-C', game, 'publish-vps'])   # by its "Brawler 0.10.N" commit)
        run('scenario publish', py('scenario.py', 'publish'))
        run('labpub', py('labpub.py', 'all', '--if-changed'))
        run('push', g('push', '-q', 'origin', 'HEAD:brawler'))
    except Fail as e:
        logf.write(f'\nFAILED: {e}\n'); up(); logf.close()
        subprocess.run(g('reset', '-q', '--hard', start or 'HEAD'))   # (the checkout as pulled; a local commit dropped)
        if st['v']: subprocess.run(nice + ['make', f'-j{c["jobs"]}'], cwd=game, env=env, capture_output=True)   # (build/ as
        # the pulled game.json: arb_compile reads what the build plays as "now", a stale build hides the sheet's change)
        return 'failed', f'{e} (the whole log: the Factory\'s Build tab)', st['v'], changes
    logf.write(f'\nshipped {v1}\n'); up(); logf.close()
    return 'done', f'shipped {v1}' + ('; left out: ' + '; '.join(left) if left else ''), v1, changes


def levels_report(c):
    """the Factory's Levels: the songs' 20 s previews (only those not cached yet, played by the ship checkout's ROM in our
    emulator) to the VPS, then what the game plays now (levels.py state) to the feedback service. Never fails a ship"""
    game = os.path.join(c['repo'], 'examples', 'brawler'); lv = os.path.join(c['repo'], 'tools', 'brawler', 'levels.py')
    env = dict(os.environ, **c['env'])
    try:
        r = subprocess.run(['nice', '-n', str(c['nice']), sys.executable, lv, 'previews', game, c.get('previews', '/data/brawler-ship/previews')]
                           + (['--host', HOST, '--dest', c.get('previews_dest', '/data/brawler-factory/songs')] if HOST else []),
                           capture_output=True, text=True, env=env, timeout=1800)
        if r.returncode: print('levels previews failed:', (r.stderr or r.stdout).strip()[-300:], flush=True)
        st = subprocess.run([sys.executable, lv, 'state', game], capture_output=True, text=True, check=True).stdout
        api('levels_game', json.loads(st))
    except (SystemExit, Exception) as e: print('levels report failed:', e, flush=True)


def beat_loop(poll):
    """the heartbeat (the Factory's "Build daemon: online"): every 30 s, what the service is doing"""
    import socket, threading
    def loop():
        while True:
            try: api('ship_beat', dict(STATE, host=socket.gethostname(), pid=os.getpid()))
            except (SystemExit, Exception) as e: print('heartbeat failed:', e, flush=True)
            time.sleep(30)
    threading.Thread(target=loop, daemon=True).start()


def ship_worker(a):
    """THE SHIP SERVICE (brawler-ship.service, docs/character_lab.md "Ship service"): every poll s, the pending requests
    (the Assembly's "Ship to the game", the Factory's "Ship pending changes" / "Rebuild & ship current"), one at a time,
    oldest first; a one-fighter request is dropped when a newer pending one covers that fighter"""
    global HOST
    c = ship_conf(a.conf); HOST = c['lab_host']
    if a.logs: c['logs'] = a.logs
    me = os.path.abspath(__file__); mt = os.path.getmtime(me)
    print(f'ship service: repo {c["repo"]}, logs {c["logs"]}, lab {HOST or "local"}, poll {c["poll"]} s', flush=True)
    if not a.once: beat_loop(c['poll']); levels_report(c)
    fs_of = lambda r: r.get('fighters') if 'fighters' in r else [r['fighter']]
    while True:
        try: rs = api('ship')['requests']
        except (SystemExit, Exception) as e: print('queue unreachable:', e, flush=True); rs = []
        pend = sorted((r for r in rs if r['status'] == 'pending' and (not a.fighter or a.fighter in fs_of(r))), key=lambda r: r['id'])
        for r in pend:
            later = next((x for x in pend if x['id'] > r['id'] and 'fighters' not in r and r['fighter'] in fs_of(x)), None)
            if later: mark(r['id'], 'dropped', f'superseded by #{later["id"]}'); continue
            t0 = time.time()
            try: stt, note, ver, ch = ship_one(c, fs_of(r), r)
            except Exception as e: stt, note, ver, ch = 'failed', f'the ship service stopped: {type(e).__name__}: {e}', None, []
            STATE.clear(); STATE['state'] = 'idle'
            mark(r['id'], stt, note, version=ver, changes=ch)
            if stt == 'done' and ver: levels_report(c)
            print(f'[ship #{r["id"]}] {r["fighter"]}: {stt}: {note} ({time.time() - t0:.0f} s)', flush=True)
            if os.path.getmtime(me) != mt:               # (a pull changed this file: run the new one)
                print('labcfg.py changed: restarting', flush=True); os.execv(sys.executable, [sys.executable] + sys.argv)
            break                                        # (the queue read again: requests made meanwhile, drops)
        if a.once and not pend: return
        if not pend: time.sleep(c['poll'])


def record(f, rev):
    return api(f'config/{f}/rev/{rev}') if rev else api(f'config/{f}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('list')
    p = sp.add_parser('show'); p.add_argument('fighter'); p.add_argument('--rev', type=int); p.add_argument('--blob', action='store_true')
    p = sp.add_parser('history'); p.add_argument('fighter')
    p = sp.add_parser('revert'); p.add_argument('fighter'); p.add_argument('rev', type=int); p.add_argument('--note', default='')
    p = sp.add_parser('export'); p.add_argument('fighter'); p.add_argument('--rev', type=int); p.add_argument('--dry-run', action='store_true')
    p.add_argument('--game', default=os.path.join(REPO, 'examples', 'brawler'))
    p = sp.add_parser('put'); p.add_argument('fighter'); p.add_argument('--blob', required=True); p.add_argument('--json')
    p.add_argument('--note', default=''); p.add_argument('--if-match')
    p.add_argument('--game', default=os.path.join(REPO, 'examples', 'brawler'))
    sp.add_parser('ship-pending')
    p = sp.add_parser('ship'); p.add_argument('fighter'); p.add_argument('--rev', type=int); p.add_argument('--note', default='')
    p = sp.add_parser('ship-done'); p.add_argument('id', type=int); p.add_argument('--dropped', action='store_true'); p.add_argument('--note', default='')
    p = sp.add_parser('ship-worker'); p.add_argument('--once', action='store_true'); p.add_argument('--fighter')
    p.add_argument('--conf', default=os.environ.get('BRAWLER_SHIP_CONF', '/data/brawler-ship/ship.json')); p.add_argument('--logs')
    a = ap.parse_args()

    if a.cmd == 'ship-worker': return ship_worker(a)

    if a.cmd == 'ship-pending':
        rs = api('ship?status=pending')['requests']
        if not rs: print('no pending ship requests')
        for r in rs:
            print(f"#{r['id']:<4} {r['fighter']:<12} rev {r['rev']:<4} {r['hash'][:16]}  {r['at'][:16].replace('T', ' ')}  {r['by']}"
                  + (f"  {r['note']}" if r.get('note') else ''))
        if rs: print('the worker ships them: labcfg.py ship-worker')
    elif a.cmd == 'ship':
        print(api(f'ship/{a.fighter}', {k: v for k, v in (('rev', a.rev), ('note', a.note)) if v})['ship'])
    elif a.cmd == 'ship-done':
        print(api('ship_done', {'id': a.id, 'status': 'dropped' if a.dropped else 'done', 'note': a.note})['ship'])
    elif a.cmd == 'list':
        cs = api('config')['configs']
        if not cs: print('no live configs yet')
        for r in cs: print(f"{r['fighter']:<12} " + head(r))
    elif a.cmd == 'history':
        for r in api(f'config/{a.fighter}/history')['revisions']: print(head(r))
    elif a.cmd == 'show':
        r = record(a.fighter, a.rev)
        print(head(r)); print(json.dumps(r['json'], indent=1, ensure_ascii=False))
        if a.blob: print(base64.b64decode(r['blob']).hex(' ', 2))
    elif a.cmd == 'revert':
        print('now', head(api(f'config/{a.fighter}/revert', {'rev': a.rev, **({'note': a.note} if a.note else {})})))
    elif a.cmd == 'put':
        blob = open(a.blob, 'rb').read()
        if a.json: cfg = json.load(open(a.json))
        else:
            G = json.load(open(os.path.join(a.game, 'game.json')))
            cfg = next((r for r in G['roster'] if r['name'] == a.fighter), None)
            if cfg is None: raise SystemExit(f'{a.fighter} is not in game.json roster: give --json')
        r = api(f'config/{a.fighter}', {'blob': base64.b64encode(blob).decode(), 'json': cfg, 'hash': hashlib.sha256(blob).hexdigest(),
                                        'note': a.note}, 'PUT', [f'If-Match: "{a.if_match}"'] if a.if_match else [])
        print(('new ' if r['changed'] else 'unchanged, still ') + head(r))
    elif a.cmd == 'export':
        sys.path.insert(0, HERE)
        from arb_compile import write_game
        r = record(a.fighter, a.rev)
        if 'lab_try' in r['json']:                       # a web page's Send to Player: what it played, not a roster entry
            print(head(r)); print(json.dumps(r['json']['lab_try'], indent=1, ensure_ascii=False))
            raise SystemExit('this revision was sent by a Lab page (Send to Player): its JSON is the page\'s try, not a roster '
                             'entry. Ship a sheet with arb_compile.py, a chain with chain_save.py (its entry is above).')
        cfg = dict(r['json']); cfg.setdefault('name', a.fighter)
        if cfg['name'] != a.fighter: raise SystemExit(f"the config's name is {cfg['name']!r}, not {a.fighter!r}")
        gp = os.path.join(a.game, 'game.json'); G = json.load(open(gp))
        old = next((x for x in (G['roster'] + [y for y in (G.get('roster_benched') or {}).get('fighters', []) if y.get('lab')]) if x['name'] == a.fighter), None)
        if old is None: raise SystemExit(f'{a.fighter} is not in {gp} roster (add the entry first)')
        ch = [k for k in sorted(set(old) | set(cfg)) if old.get(k) != cfg.get(k)]
        print(head(r)); print('changed keys:', ', '.join(ch) or 'none')
        for k in ch: print(f'  {k}: {json.dumps(old.get(k), ensure_ascii=False)} -> {json.dumps(cfg.get(k), ensure_ascii=False)}')
        if ch and not a.dry_run:
            write_game(gp, a.fighter, cfg); print('written', os.path.relpath(gp, REPO) if gp.startswith(REPO + os.sep) else gp, f'(commit it: "{a.fighter}: Lab config rev {r["version"]}")')


if __name__ == '__main__':
    main()
