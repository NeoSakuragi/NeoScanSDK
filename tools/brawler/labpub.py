#!/usr/bin/env python3
"""Publish the Character Lab's shell build and character packs to the VPS catalogue (docs/character_lab.md "Character Lab").

The file goes to /data/brawler/lab/incoming/ by scp, then the feedback service (over ssh on localhost: /api/lab/publish)
checks its sha256 and moves it into place: shell/<version><ext>, packs/<f>/<version>.pack, faces/<f>.png. The player's
Character lab sees it in GET /brawler/lab/catalogue on its next poll and downloads it from /brawler/lab/dl/ (Range).

    labpub.py all [--if-changed] [--only f,g] [--dry-run] [--no-build]
                     THE ONE COMMAND (make lab-publish): builds the shell and the full pack of every fighter that has a
                     dictionary and a piece library (animdict.DICTS + arb_pieces/<f>.json), then publishes what changed:
                     the shell when its bytes differ from the catalogue's, a pack when its DATA (lab_pack.py data_sha:
                     its regions, format, needs, page data) differs from the newest of his the shell can load.
                     --if-changed (deploy_vps.sh): nothing at all unless the pack format or a fighter's inputs changed
                     since the last run (packs/stamps.json): an engine change alone publishes nothing
    labpub.py list                                                      the catalogue (last shell, each fighter's last pack)
    labpub.py publish-shell FILE [--engine E] [--version V]            (format / features from the shell's anchor)
    labpub.py publish-pack FIGHTER FILE [--engine E] [--version V] [--display "Kim"] [--face PNG | --no-face]
                     (format / needs / data_sha from the pack's sidecar .json); the face defaults to the game's own HUD
                     portrait (make_hud.portrait, x4)
    labpub.py publish-face FIGHTER [PNG]
    labpub.py remove-shell VERSION      labpub.py remove-pack FIGHTER VERSION      labpub.py remove-face FIGHTER

Compatibility is the PACK FORMAT (docs/character_lab.md "The pack format"): a pack loads into a shell of its format whose
features cover its needs. --engine is the legacy string the Players before 0.0.33 compare (a pack built against that
very shell; default: computed / the sidecar's). --version defaults to the UTC time (YYYYMMDD-HHMMSS). A version is
published once; the newest published is the one served."""
import argparse, glob, hashlib, json, os, shlex, subprocess, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
HOST = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/lab/'
INCOMING = '/data/brawler/lab/incoming/'
PORTRAITS = '/data/neogeo_dict/portraits/'


def api(path, body=None):
    cmd = f'curl -s -S --max-time 60 {shlex.quote(BASE + path)}'
    if body is not None: cmd += " -X POST -H 'Content-Type: application/json' --data-binary @-"
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, cmd], input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if r.returncode: raise SystemExit('ssh/curl: ' + r.stderr.strip())
    out = json.loads(r.stdout)
    if isinstance(out, dict) and 'error' in out: raise SystemExit('server: ' + out['error'])
    return out


def upload(path, req):
    """scp into incoming/ under a fresh name, then /api/lab/publish; the upload is removed if the publish fails"""
    ext = os.path.splitext(path)[1].lower()
    src = uuid.uuid4().hex[:12] + ext
    subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, 'mkdir -p ' + INCOMING], check=True)
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', path, f'{HOST}:{INCOMING}{src}'], check=True)
    req = dict(req, src=src, sha256=hashlib.sha256(open(path, 'rb').read()).hexdigest())
    try: return api('publish', req)['published']
    except SystemExit:
        subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, 'rm -f ' + shlex.quote(INCOMING + src)]); raise


def default_face(f):
    G = json.load(open(os.path.join(REPO, 'examples', 'brawler', 'game.json')))
    bench = G.get('roster_benched') or []
    bench = list(bench.values()) if isinstance(bench, dict) else bench
    r = next((r for r in G['roster'] + bench if isinstance(r, dict) and r.get('name') == f), None)
    if not r: return None
    return hud_face(r['bank'])

def hud_face(bank):
    """the fighter's face exactly as the game's HUD draws it (Bruno 2026-10-10: the Player's faces = the HUD's, for
    consistency): make_hud.portrait's 32x32 indexed pixels + its 15 colours (index i = colour i - 1, 0 unused), x4 nearest"""
    import tempfile
    from PIL import Image
    import make_hud
    game, name = bank.split(':')
    px, pal = make_hud.portrait(game, name)
    im = Image.new('RGB', (32, 32))
    for y, row in enumerate(px):
        for x, i in enumerate(row): im.putpixel((x, y), tuple(pal[i - 1]) if 1 <= i <= len(pal) else (0, 0, 0))
    out = os.path.join(tempfile.mkdtemp(), name + '.png'); im.resize((128, 128), Image.NEAREST).save(out)
    return out


def show(cat):
    s = cat['shell']
    print('shell:', f"{s['version']}  format {s.get('format') or '-'} ({len(s.get('features') or [])} features)  engine {s['engine']}  "
          f"{s['size']} B  {s['sha256'][:16]}  {s['url']}" if s else 'none')
    for p in cat['packs']:
        best = newest_compatible(p, s)
        print(f"pack  {p['fighter']:<12} {p['version']:<16} format {p.get('format') or '-'}  {len(p.get('needs') or [])} needs  "
              f"{p['size']:>9} B  {p['sha256'][:16]}  face {'yes' if p['face'] else 'no'}  ({p['versions']} published; "
              + (f"the shell loads {best['version']})" if best else f"NONE the shell loads: {why_not(p, s)})"))
    if not cat['packs']: print('no packs')


def why_not(p, s):
    """why a catalogue pack entry does not load into the catalogue shell (None: it does): lab_pack.compat"""
    import lab_pack
    if not s: return 'no shell'
    return lab_pack.compat(p.get('format'), p.get('needs') or [], s.get('format'), s.get('features') or [])


def newest_compatible(p, s):
    """his newest published version the shell can load (the catalogue's `all`, newest first), or None"""
    for v in p.get('all') or [p]:
        if s and not why_not(v, s): return v
    return None


# ---- THE ONE COMMAND ----------------------------------------------------------------------------------------------------
GAME = os.path.join(REPO, 'examples', 'brawler')
STAMPS = os.path.join(GAME, 'packs', 'stamps.json')


def lab_fighters():
    """every roster fighter with a dictionary (animdict.DICTS) and a piece library (arb_pieces/<f>.json)"""
    import animdict
    G = json.load(open(os.path.join(GAME, 'game.json')))
    names = [r['name'] for r in G['roster']]
    return [f for f in names if f in animdict.DICTS and os.path.exists(os.path.join(HERE, 'arb_pieces', f + '.json'))]


def inputs_hash(f):
    """what a fighter's pack is made from, besides the engine: the pack format, his roster entry, his piece library and
    ids, his route file, his voices, and the exporters (an exporter change may change his data)"""
    import lab_pack
    G = json.load(open(os.path.join(GAME, 'game.json')))
    r = next(x for x in G['roster'] if x['name'] == f)
    h = hashlib.sha256(json.dumps({'format': lab_pack.FORMAT, 'abi': lab_pack.FORMATS[lab_pack.FORMAT], 'roster': r,
                                   'chain': G.get('chain')}, sort_keys=True).encode())
    game = r['bank'].split(':')[0]
    files = [os.path.join(HERE, 'arb_pieces', f + '.json'), os.path.join(HERE, 'arb_pieces', f + '_ids.json'),
             os.path.join(HERE, 'routes', f + '.json'), os.path.join(HERE, 'voices.json'), os.path.join(HERE, 'export_bm.py'),
             os.path.join(HERE, 'knobs.py'), os.path.join(HERE, 'build_tables.py'), os.path.join(HERE, 'routes.py')]
    files += sorted(glob.glob(os.path.join(REPO, 'tools', {'kof98': 'kof96', 'kof99': 'kof96', 'kizuna': 'kizuna'}.get(game, game), '*.py')))
    for p in files:
        if os.path.exists(p): h.update(p.encode() + open(p, 'rb').read())
    return h.hexdigest()[:16]


def make(*args):
    print('make', ' '.join(args), flush=True)
    r = subprocess.run(['make', '-C', GAME, '-j2', *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode: print(r.stdout[-4000:]); raise SystemExit(f'make {" ".join(args)} failed')
    for l in r.stdout.split('\n'):
        if l.startswith(('pack ', '  .labslot', 'lab_pack', 'NEO:')): print('  ' + l.strip())


def cmd_all(a):
    import lab_pack
    fighters = lab_fighters()
    if a.only: fighters = [f for f in fighters if f in a.only.split(',')]
    stamps = json.load(open(STAMPS)) if os.path.exists(STAMPS) else {}
    want = {f: inputs_hash(f) for f in fighters}
    cat = api('catalogue'); sh = cat.get('shell')
    if a.if_changed:
        fmt_changed = not sh or sh.get('format') != lab_pack.FORMAT or stamps.get('format') != [lab_pack.FORMAT, lab_pack.FORMATS[lab_pack.FORMAT]]
        changed = [f for f in fighters if stamps.get(f) != want[f]]
        if not fmt_changed and not changed:
            print(f'labpub all --if-changed: the pack format ({lab_pack.FORMAT}) and every fighter\'s inputs are as last published: nothing to do')
            return
        if not fmt_changed: fighters = changed
        print('labpub all: ' + ('the pack format changed' if fmt_changed else 'changed: ' + ', '.join(changed)))
    print(f'labpub all: the shell + {len(fighters)} packs ({", ".join(fighters)})', flush=True)
    if not a.no_build:
        make('LAB_SHELL=1')
        for f in fighters: make(f'LAB_PACK={f}', 'STRICT=1')
    shell = os.path.join(GAME, 'lab-shell.neo')
    sfmt, sid, feats, sregs, sdoc = lab_pack.shell_anchor(shell)
    ssha = hashlib.sha256(open(shell, 'rb').read()).hexdigest()
    d, sizes, layout = lab_pack.neo(shell)
    engine = lab_pack.legacy_engine(d, layout, lab_pack.regions('build_shell')[0])
    snew = {'format': sfmt, 'features': feats}
    todo = []
    if not sh or sh['sha256'] != ssha: todo.append(('shell', None, shell))
    for f in fighters:
        pk = os.path.join(GAME, 'packs', f + '.pack'); side = json.load(open(os.path.join(GAME, 'packs', f + '.json')))
        if side.get('built_with', {}).get('shell_sha256') != ssha: raise SystemExit(f'{f}: packs/{f}.pack was not built against lab-shell.neo (run without --no-build)')
        why = lab_pack.compat(side['ngpk']['format'], side['ngpk']['needs'].split(), sfmt, feats)
        if why: raise SystemExit(f'{f}: the shell cannot load his pack: {why}')
        p = next((x for x in cat['packs'] if x['fighter'] == f), None)
        best = newest_compatible(p, snew) if p else None
        if best and best.get('data_sha') == side['data_sha']: print(f'  {f}: unchanged (his pack {best["version"]}, data {side["data_sha"][:12]})'); continue
        todo.append(('pack', f, pk))
    if not todo: print('labpub all: nothing changed')
    for kind, f, path in todo:
        print(f'  publish {kind} {f or ""} {path}' + (' (dry run)' if a.dry_run else ''), flush=True)
        if a.dry_run: continue
        stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
        if kind == 'shell':
            print('    published', upload(path, {'kind': 'shell', 'version': stamp, 'engine': engine, 'format': sfmt, 'features': feats}))
        else:
            side = json.load(open(os.path.splitext(path)[0] + '.json'))
            print('    published', upload(path, {'kind': 'pack', 'fighter': f, 'version': stamp, 'engine': side['engine'], 'display': side['display'].title(),
                                               'format': side['ngpk']['format'], 'needs': side['ngpk']['needs'], 'data_sha': side['data_sha']}))
            face = default_face(f)
            if face: upload(face, {'kind': 'face', 'fighter': f})
        time.sleep(1.1)                                  # (versions are the UTC second)
    if not a.dry_run:
        stamps.update(want); stamps['format'] = [lab_pack.FORMAT, lab_pack.FORMATS[lab_pack.FORMAT]]
        os.makedirs(os.path.dirname(STAMPS), exist_ok=True); json.dump(stamps, open(STAMPS, 'w'), indent=1)
    show(api('catalogue'))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('list')
    p = sp.add_parser('all'); p.add_argument('--if-changed', action='store_true'); p.add_argument('--only')
    p.add_argument('--dry-run', action='store_true'); p.add_argument('--no-build', action='store_true')
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    p = sp.add_parser('publish-shell'); p.add_argument('file'); p.add_argument('--engine'); p.add_argument('--version', default=stamp)
    p = sp.add_parser('publish-pack'); p.add_argument('fighter'); p.add_argument('file'); p.add_argument('--engine')
    p.add_argument('--version', default=stamp); p.add_argument('--display'); p.add_argument('--face'); p.add_argument('--no-face', action='store_true')
    p = sp.add_parser('publish-face'); p.add_argument('fighter'); p.add_argument('png', nargs='?')
    p = sp.add_parser('remove-shell'); p.add_argument('version')
    p = sp.add_parser('remove-pack'); p.add_argument('fighter'); p.add_argument('version')
    p = sp.add_parser('remove-face'); p.add_argument('fighter')
    a = ap.parse_args()

    if a.cmd == 'list': return show(api('catalogue'))
    if a.cmd == 'all': return cmd_all(a)
    import lab_pack
    if a.cmd == 'publish-shell':
        sfmt, sid, feats, sregs, sdoc = lab_pack.shell_anchor(a.file)
        d, sizes, layout = lab_pack.neo(a.file)
        eng = a.engine or lab_pack.legacy_engine(d, layout, [{'rom': r, 'offset': o, 'size': z} for r, o, z in sregs.values()])
        print('published', upload(a.file, {'kind': 'shell', 'version': a.version, 'engine': eng, 'format': sfmt, 'features': feats}))
    elif a.cmd == 'publish-pack':
        disp = a.display or a.fighter.replace('_', ' ').title()
        side = json.load(open(os.path.splitext(a.file)[0] + '.json'))
        print('published', upload(a.file, {'kind': 'pack', 'fighter': a.fighter, 'version': a.version, 'engine': a.engine or side['engine'],
                                           'display': disp, 'format': side['ngpk']['format'], 'needs': side['ngpk']['needs'],
                                           'data_sha': side['data_sha']}))
        face = None if a.no_face else (a.face or default_face(a.fighter))
        if face: print('face', upload(face, {'kind': 'face', 'fighter': a.fighter})['url'], 'from', face)
        elif not a.no_face: print('no HUD portrait found for', a.fighter, '(publish-face FIGHTER PNG)')
    elif a.cmd == 'publish-face':
        face = a.png or default_face(a.fighter)
        if not face: raise SystemExit('no HUD portrait found for ' + a.fighter)
        print('face', upload(face, {'kind': 'face', 'fighter': a.fighter})['url'], 'from', face)
    elif a.cmd == 'remove-shell': api('unpublish', {'kind': 'shell', 'version': a.version}); print('removed shell', a.version)
    elif a.cmd == 'remove-pack': api('unpublish', {'kind': 'pack', 'fighter': a.fighter, 'version': a.version}); print('removed pack', a.fighter, a.version)
    elif a.cmd == 'remove-face': api('unpublish', {'kind': 'face', 'fighter': a.fighter}); print('removed face', a.fighter)
    show(api('catalogue'))


if __name__ == '__main__':
    main()
