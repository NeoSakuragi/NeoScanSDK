#!/usr/bin/env python3
"""The Character Lab's live fighter configs on the VPS (docs/feedback.md "Character Lab"; the feedback service
tools/feedback/server.py, its /api/lab/ over ssh on localhost = authenticated by the ssh key, user "ssh").

The VPS is the source of truth while Bruno tunes a fighter in the web Assembly pages (arbitrage / workshop / the Chain
Lab); every PUT is a revision kept for good (LAB/config/<f>.history.jsonl). The Lab config is a STAGING area (Bruno
2026-10-10): editing it never changes the real game or git. His "Ship to game" (POST lab/ship/<f>) only queues a request;
here `ship-pending` lists them, the export -> game.json -> arb_compile -> build -> publish is run by hand (`export` brings
the config into examples/brawler/game.json, the fighter's roster entry, so git keeps its history), then `ship-done`.

    labcfg.py ship-pending                          the "Ship to game" requests waiting: id, fighter, revision, who, when
    labcfg.py ship FIGHTER [--rev N] [--note ...]   queue one from here (as the Lab's button does)
    labcfg.py ship-done ID [--dropped] [--note "0.0.120, commit abc123"]   close a request once shipped (or dropped)

    labcfg.py list                                  every fighter's live config: revision, hash, when, by whom
    labcfg.py show FIGHTER [--rev N] [--blob]       the config's JSON (the roster entry form); --blob: the RAM-loads bytes as hex
    labcfg.py history FIGHTER                       every revision, oldest first
    labcfg.py revert FIGHTER REV [--note "..."]     a NEW revision with revision REV's blob + JSON (nothing is deleted)
    labcfg.py export FIGHTER [--rev N] [--dry-run] [--game examples/brawler]
                                                    the JSON written as the fighter's roster entry in game.json (key by key:
                                                    unchanged keys keep their text, arb_compile.write_game)
    labcfg.py put FIGHTER --blob FILE [--json FILE] [--note "..."] [--if-match HASH]
                                                    a revision from the desktop; --json defaults to the repo's roster entry

The blob is opaque here (its byte format: the RAM-loads spec); its hash = sha256 of the bytes, what the player polls."""
import argparse, base64, hashlib, json, os, shlex, subprocess, sys

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
    a = ap.parse_args()

    if a.cmd == 'ship-pending':
        rs = api('ship?status=pending')['requests']
        if not rs: print('no pending ship requests')
        for r in rs:
            print(f"#{r['id']:<4} {r['fighter']:<12} rev {r['rev']:<4} {r['hash'][:16]}  {r['at'][:16].replace('T', ' ')}  {r['by']}"
                  + (f"  {r['note']}" if r.get('note') else ''))
        if rs: print('ship each: labcfg.py export F --rev N, build + check, publish, commit, then labcfg.py ship-done ID --note "<release>"')
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
