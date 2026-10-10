#!/usr/bin/env python3
"""Publish the Character Lab's shell build and character packs to the VPS catalogue (docs/character_lab.md "Character Lab").

The file goes to /data/brawler/lab/incoming/ by scp, then the feedback service (over ssh on localhost: /api/lab/publish)
checks its sha256 and moves it into place: shell/<version><ext>, packs/<f>/<version>.pack, faces/<f>.png. The player's
Character lab sees it in GET /brawler/lab/catalogue on its next poll and downloads it from /brawler/lab/dl/ (Range).

    labpub.py list                                                      the catalogue (last shell, each fighter's last pack)
    labpub.py publish-shell FILE --engine E [--version V]
    labpub.py publish-pack FIGHTER FILE --engine E [--version V] [--display "Kim"] [--face PNG | --no-face]
                     the face defaults to the game's own HUD portrait (make_hud.portrait, x4)
    labpub.py publish-face FIGHTER [PNG]
    labpub.py remove-shell VERSION      labpub.py remove-pack FIGHTER VERSION      labpub.py remove-face FIGHTER

--engine: the engine version the file is built for (a pack loads only into a shell of the same engine); --version
defaults to the UTC time (YYYYMMDD-HHMMSS). A version is published once; the newest published is the one served."""
import argparse, hashlib, json, os, shlex, subprocess, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
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
    print('shell:', f"{s['version']}  engine {s['engine']}  {s['size']} B  {s['sha256'][:16]}  {s['url']}" if s else 'none')
    for p in cat['packs']:
        print(f"pack  {p['fighter']:<12} {p['version']:<16} engine {p['engine']:<10} {p['size']:>9} B  {p['sha256'][:16]}  "
              f"{p['url']}  face {'yes' if p['face'] else 'no'}  ({p['versions']} published)")
    if not cat['packs']: print('no packs')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('list')
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    p = sp.add_parser('publish-shell'); p.add_argument('file'); p.add_argument('--engine', required=True); p.add_argument('--version', default=stamp)
    p = sp.add_parser('publish-pack'); p.add_argument('fighter'); p.add_argument('file'); p.add_argument('--engine', required=True)
    p.add_argument('--version', default=stamp); p.add_argument('--display'); p.add_argument('--face'); p.add_argument('--no-face', action='store_true')
    p = sp.add_parser('publish-face'); p.add_argument('fighter'); p.add_argument('png', nargs='?')
    p = sp.add_parser('remove-shell'); p.add_argument('version')
    p = sp.add_parser('remove-pack'); p.add_argument('fighter'); p.add_argument('version')
    p = sp.add_parser('remove-face'); p.add_argument('fighter')
    a = ap.parse_args()

    if a.cmd == 'list': return show(api('catalogue'))
    if a.cmd == 'publish-shell':
        print('published', upload(a.file, {'kind': 'shell', 'version': a.version, 'engine': a.engine}))
    elif a.cmd == 'publish-pack':
        disp = a.display or a.fighter.replace('_', ' ').title()
        print('published', upload(a.file, {'kind': 'pack', 'fighter': a.fighter, 'version': a.version, 'engine': a.engine, 'display': disp}))
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
