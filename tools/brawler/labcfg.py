#!/usr/bin/env python3
"""The Character Lab's live fighter configs on the VPS (docs/character_lab.md "Character Lab"; the feedback service
tools/feedback/server.py, its /api/lab/ over ssh on localhost = authenticated by the ssh key, user "ssh").

The VPS is the source of truth while Bruno tunes a fighter in the web Assembly; every PUT is a revision kept for good
(LAB/config/<f>.history.jsonl). NO STAGING (Bruno 2026-10-10: "forget about staging, remove that step"): what the
Assembly saves IS the game. Every live send of a sheet queues a ship request (POST lab/ship/<f>); the WORKER ships it:

    labcfg.py ship-worker [--once] [--fighter F] [--quiet 60] [--poll 20] [--no-publish] [--commit]
        polls the queue; a fighter whose newest request is --quiet seconds old (no change since) is shipped once (his
        older requests: dropped, "superseded"): status building -> VERSION bumped, arb_compile.py F (his sheet -> game.json,
        build, bank_proof, every linked slot / knob / timing checked in our emulator) -> make publish-vps (the Player's
        game; --no-publish: built only) [-> git commit of game.json, VERSION, docs/brawler_gold.md: --commit] -> done
        "build 0.10.N" + what was left out. Refused / failed: VERSION and game.json as they were, the game rebuilt,
        status failed with the plain reason (the sheet's "In the game" line shows it). Nothing changed: done, no build.
        Run it on the desktop (the toolchain): `python3 tools/brawler/labcfg.py ship-worker --commit` in a terminal, or
        `--once` from a loop tick.
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
import argparse, base64, datetime, hashlib, json, os, shlex, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
HOST = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/lab/'


def api(path, body=None, method=None, headers=()):
    cmd = f'curl -s -S --max-time 30 {shlex.quote(BASE + path)}'
    for h in headers: cmd += ' -H ' + shlex.quote(h)
    if body is not None: cmd += f" -X {method or 'POST'} -H 'Content-Type: application/json' --data-binary @-"
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, cmd], input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if r.returncode: raise SystemExit('ssh/curl: ' + r.stderr.strip())
    out = json.loads(r.stdout)
    if isinstance(out, dict) and 'error' in out: raise SystemExit('server: ' + out['error'])
    return out


def head(r):
    rv = f"  (revert of rev {r['reverted_from']})" if r.get('reverted_from') else ''
    return (f"rev {r['version']:>4}  {r['hash'][:16]}  {r['size']:>7} B  {r['updated'][:16].replace('T', ' ')}  {r['by']:<12}"
            + (f"  {r['note']}" if r.get('note') else '') + rv)


def mark(i, status, note=''):
    return api('ship_done', {'id': i, 'status': status, 'note': note[:600]})['ship']


def ship_one(a, f, row):
    """one ship (the worker): VERSION bump, arb_compile.py F, publish, [commit] -> (status, note)"""
    game = a.game; vp = os.path.join(game, 'VERSION'); v0 = open(vp).read()
    p = v0.strip().split('.'); p[-1] = str(int(p[-1]) + 1); v1 = '.'.join(p)
    mark(row['id'], 'building', f'building {v1}')
    print(f'[ship #{row["id"]}] {f} rev {row["rev"]}: building {v1}', flush=True)
    open(vp, 'w').write(v1 + '\n')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'arb_compile.py'), f, '--game', game], capture_output=True, text=True)
    out = r.stdout + r.stderr
    os.makedirs(a.logs, exist_ok=True)
    log = os.path.join(a.logs, f'ship_{row["id"]}_{f}.log'); open(log, 'w').write(out)
    lines = out.splitlines()
    left = [x.strip()[2:] for x in lines[next((i for i, x in enumerate(lines) if x.startswith('REPORT ')), len(lines)):] if x.strip().startswith('- ')]
    changed = not any(x.startswith('game.json roster changes: none') for x in lines)
    if r.returncode or not changed:
        open(vp, 'w').write(v0)                          # (VERSION as it was; arb_compile restored game.json itself)
        if r.returncode:
            why = [x.strip() for x in lines if x.strip().startswith('- ') or x.startswith('REFUSED')] or lines[-6:]
            subprocess.run(['make', '-C', game, '-j2'], capture_output=True)   # (its rebuild had the bumped VERSION)
            return 'failed', 'not in the game: ' + ' '.join(why)[:560] + f' (log {log})'
        cur = v0.strip()
        return 'done', f'nothing changed: the game already plays this sheet (build {cur})' + ('; left out: ' + '; '.join(left) if left else '')
    note = f'build {v1}'
    if a.no_publish: note += ' (built, not published: --no-publish)'
    else:
        pr = subprocess.run(['make', '-C', game, 'publish-vps'], capture_output=True, text=True)
        if pr.returncode: return 'failed', f'built {v1} but the publish failed: ' + (pr.stderr or pr.stdout).strip()[-300:]
        note += ' published'
    if a.commit:
        paths = [os.path.relpath(x, REPO) for x in (os.path.join(game, 'game.json'), vp, os.path.join(REPO, 'docs', 'brawler_gold.md'))]
        subprocess.run(['git', '-C', REPO, 'add', '--'] + paths)
        c = subprocess.run(['git', '-C', REPO, 'commit', '-q', '-m', f'Brawler {v1}: {f} shipped from the Assembly (ship #{row["id"]}, live config rev {row["rev"]})', '--'] + paths,
                           capture_output=True, text=True)
        if not c.returncode: note += ', committed'
    if left: note += '; left out: ' + '; '.join(left)
    return 'done', note


def ship_worker(a):
    while True:
        rs = api('ship')['requests']
        pend = {}
        for r in rs:
            if r['status'] == 'pending' and (not a.fighter or r['fighter'] == a.fighter): pend.setdefault(r['fighter'], []).append(r)
        for f, rows in sorted(pend.items()):
            rows.sort(key=lambda r: r['id']); last = rows[-1]
            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last['at'].replace('Z', '+00:00'))).total_seconds()
            if age < a.quiet: continue                   # (still being edited: the next poll)
            for r in rows[:-1]: mark(r['id'], 'dropped', f'superseded by #{last["id"]}')
            try: st, note = ship_one(a, f, last)
            except Exception as e: st, note = 'failed', f'the worker stopped: {type(e).__name__}: {e}'
            mark(last['id'], st, note)
            print(f'[ship #{last["id"]}] {f}: {st}: {note}', flush=True)
        if a.once: return
        time.sleep(a.poll)


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
    p.add_argument('--quiet', type=int, default=60); p.add_argument('--poll', type=int, default=20)
    p.add_argument('--no-publish', action='store_true'); p.add_argument('--commit', action='store_true')
    p.add_argument('--game', default=os.path.join(REPO, 'examples', 'brawler')); p.add_argument('--logs', default='/data/tmp/ship')
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
        old = next((x for x in G['roster'] if x['name'] == a.fighter), None)
        if old is None: raise SystemExit(f'{a.fighter} is not in {gp} roster (add the entry first)')
        ch = [k for k in sorted(set(old) | set(cfg)) if old.get(k) != cfg.get(k)]
        print(head(r)); print('changed keys:', ', '.join(ch) or 'none')
        for k in ch: print(f'  {k}: {json.dumps(old.get(k), ensure_ascii=False)} -> {json.dumps(cfg.get(k), ensure_ascii=False)}')
        if ch and not a.dry_run:
            write_game(gp, a.fighter, cfg); print('written', os.path.relpath(gp, REPO) if gp.startswith(REPO + os.sep) else gp, f'(commit it: "{a.fighter}: Lab config rev {r["version"]}")')


if __name__ == '__main__':
    main()
