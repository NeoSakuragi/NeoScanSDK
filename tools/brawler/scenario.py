#!/usr/bin/env python3
"""Test scenarios for the feedback notes ("verify an issue", docs/feedback.md "Scenarios"): per note a JSON recipe kept
with the note in the tracker (tools/feedback/server.py, table scenarios) that the deterministic harness (harness.py, the
repo's Geolith core) turns into a SAVE STATE on a given build: the NeoScan Player (0.0.22+) and the Lab's Feedback tab
load it under a banner "Do: ... / Expect: ...", and his 👍 / 👎 closes or reopens the note.

    scenario.py show ID                         the note's recipe (tracker) and its states per build
    scenario.py put ID [FILE]                   recipe from FILE (default: tools/brawler/scenarios.json[ID]) to the tracker
    scenario.py gen ID [--rom R] [--upload]     state(s) on build R (default examples/brawler/brawler.neo) for both player
                                                systems (mvs-mvs = arcade, uni-aes = console) + the proof clip of "do"
                                                -> /data/feedback/scenarios/<id>/<sha12>/; --upload: to the tracker
    scenario.py verify ID [--rom R]             gen twice in fresh processes (byte-identical states) + the state loaded in a
                                                third fresh core, the do inputs replayed: the same end state as gen's
    scenario.py publish [--rom R] [--dry]       every note in shipped / reopened / fixed with a recipe: gen + upload on the
                                                CURRENT build (the publish routine runs it after publish_vps.sh)
    scenario.py backfill [--only ID,...]        every recipe of scenarios.json: put + gen + upload

A recipe (scenarios.json, keyed by note id):
  title       the test's one-line headline (the banner's first line)
  do / expect what to do / what should happen, as the player reads them
  setup       mode "lab" (default): the Chain Lab (main.c lab_start, the lab mailbox: the game's own path, no AI, P1's
                  life refilled, the dummy stands and gets up); fighter / dummy = game.json roster names;
                  gap = the dummy's distance in front of P1 (px, default the lab's 80); extra = [dx, ...] more standing
                  dummies (copies of the dummy, dx from P1; they stay down once beaten);
              mode "stage": campaign stage `stage` from wave `wave` (lab req 4: P1 alone, the enemies' AI on);
              meter (0..120, "full"), hp (P1's life), lives (P1's), face (+1 / -1), pre = "frames:keys,..." inputs played
              before the save (e.g. walking into the grab: the state then starts mid-hold)
  do_keys     the "do" as inputs ("frames:keys,..." with the harness keys U D L R a b c d), for the proof clip
  proof       frames to keep running after do_keys (default 90)
Every poke used is listed here: fighter_t.x / z / facing / hp / meter (harness offsets from fighter.h), lives[0], and the
lab mailbox (fighter.h lab_t). The state is the frame after the setup; the player loads it paused."""
import argparse, hashlib, json, os, shlex, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
GAME = os.path.join(REPO, 'examples', 'brawler')
RECIPES = os.path.join(HERE, 'scenarios.json')
OUT = '/data/feedback/scenarios'
HOST = 'root@195.201.91.211'
REMOTE = '/data/brawler/feedback/scenarios'
# the player's two systems (player.c environ_cb: region us; the card only on AES; console = UniBIOS in AES mode: the
# APK's neogeo.zip has no neo-epo.bin) -> the state key the player asks for: Native.systemType() + "-" + hw
SYSTEMS = {'mvs-mvs': dict(geolith_system_type='mvs', geolith_unibios_hw='mvs', geolith_memcard='off', geolith_region='us'),
           'uni-aes': dict(geolith_system_type='uni', geolith_unibios_hw='aes', geolith_memcard='on', geolith_region='us')}
BOOT = 400                                  # power on -> the BIOS hands over to the game (labdrive.py)
LAB_REQ, LAB_FIGHTER, LAB_DUMMY_, LAB_ACTIVE, LAB_WAVE = 4, 5, 6, 8, 13   # fighter.h lab_t offsets


def sha256(b): return hashlib.sha256(b).hexdigest()


def snapshot(rom):
    """the game sources + build symbols that belong to this ROM (the harness reads fighter_t's layout from fighter.h and the
    addresses from build/rom.elf: the working tree moves on after a publish, and a state poked with another build's
    offsets is wrong): /data/feedback/scenarios/_builds/<sha12>/ = examples/brawler + sdk at the release commit (the
    "Brawler <VERSION>:" commit) + the repo's build/rom.elf and headers, taken once, while the repo's brawler.neo IS
    this ROM (scenario.py publish runs right after publish_vps.sh, so it is)"""
    sha = sha_file(rom); d = os.path.join(OUT, '_builds', sha[:12]); game = os.path.join(d, 'examples', 'brawler')
    if os.path.exists(os.path.join(game, 'build', 'rom.elf')): return game
    if sha_file(os.path.join(GAME, 'brawler.neo')) != sha:
        raise RuntimeError(f'no build snapshot for ROM {sha[:12]}: run scenario.py while examples/brawler/brawler.neo is that build')
    ver = open(os.path.join(GAME, 'VERSION')).read().strip()
    log = subprocess.run(['git', '-C', REPO, 'log', '--format=%H %s', '--', 'examples/brawler/VERSION'], capture_output=True, text=True).stdout
    commit = next((l.split()[0] for l in log.splitlines() if l.split(' ', 1)[1].startswith(f'Brawler {ver}')), None)
    if not commit: raise RuntimeError(f'no "Brawler {ver}" commit')
    os.makedirs(d + '.part', exist_ok=True)
    subprocess.run(f'git -C {shlex.quote(REPO)} archive {commit} examples/brawler sdk | tar -x -C {shlex.quote(d + ".part")}', shell=True, check=True)
    b = os.path.join(d + '.part', 'examples', 'brawler', 'build'); os.makedirs(b, exist_ok=True)
    for f in os.listdir(os.path.join(GAME, 'build')):
        if f == 'rom.elf' or f.endswith('.h'): subprocess.run(['cp', '-p', os.path.join(GAME, 'build', f), b], check=True)
    json.dump({'rom_sha256': sha, 'version': ver, 'commit': commit}, open(os.path.join(d + '.part', 'build.json'), 'w'))
    os.replace(d + '.part', d)
    return game
def sha_file(p): return sha256(open(p, 'rb').read())
def recipes(): return json.load(open(RECIPES)) if os.path.exists(RECIPES) else {}
def roster(game):
    return [r if isinstance(r, str) else r.get('name') for r in json.load(open(os.path.join(game, 'game.json')))['roster']]


# ---- the generator (one core per process: run as `scenario.py _gen`) ---------------------------------------------------
def setup(b, rec):
    """power on -> the scenario's first frame (see the recipe format above)"""
    s = rec.get('setup', {}); names = roster(b.game)
    lab = b.syms['lab']; poke = lambda off, data: [b.w(lab + off + i, 1, v) for i, v in enumerate(data)]
    b.core.retro_reset(); b.frame = 0
    for _ in range(BOOT): b.core.retro_run()
    b.frame = BOOT
    fi = names.index(s.get('fighter', 'terry'))
    if s.get('mode', 'lab') == 'lab':
        poke(0, b'LAB1'); poke(LAB_FIGHTER, [fi, names.index(s.get('dummy', 'ryo'))]); poke(LAB_REQ, [1])
        want = lambda: b.r(lab + LAB_ACTIVE, 1) == 1
    else:
        poke(0, b'LAB1'); poke(LAB_FIGHTER, [fi, int(s.get('stage', 0))]); poke(LAB_WAVE, [int(s.get('wave', 0))]); poke(LAB_REQ, [4])
        want = lambda: b.r(lab + LAB_REQ, 1) == 0 and b.r(b.syms['mode'], 1) == 1
    for _ in range(3000):
        b.core.retro_run(); b.frame += 1
        if want(): break
    else: raise RuntimeError('the game never took the lab request')
    b.run(2)
    cam = b.r(b.syms['cam_x'], 2); cam = cam - 65536 if cam > 32767 else cam
    if s.get('mode', 'lab') == 'lab':
        x0 = b.fget(0, 'x')
        if 'x' in s: x0 = cam + s['x']; b.fset(0, 'x', x0)
        face = s.get('face', 1); b.fset(0, 'facing', face & 0xFF)
        if 'gap' in s or 'x' in s or face != 1:
            b.fset(2, 'x', x0 + face * s.get('gap', 80)); b.fset(2, 'facing', -face & 0xFF)
        z = b.fget(0, 'z')
        for k, dx in enumerate(s.get('extra', [])):           # copies of the dummy (same palette), standing at dx
            i = 3 + k; base = b.base
            src = base + 2 * b.fsize; dst = base + i * b.fsize
            for o in range(b.fsize): b.w(dst + o, 1, b.r(src + o, 1))
            b.fset(i, 'idx', i); b.fset(i, 'x', x0 + dx); b.fset(i, 'z', z); b.fset(i, 'facing', (1 if dx < 0 else -1) & 0xFF)
    if 'meter' in s: b.fset(0, 'meter', 120 if s['meter'] == 'full' else int(s['meter']))
    if 'hp' in s: b.fset(0, 'hp', int(s['hp']))
    if 'lives' in s: b.w(b.syms['lives'], 1, int(s['lives']))
    b.run(1)
    if s.get('pre'): b.seq(s['pre'])


def gen_child(rid, key, rom, out, rec_json):
    sys.path.insert(0, HERE)
    import harness as H
    H.OPTIONS.update(SYSTEMS[key])
    from PIL import Image, ImageDraw
    rec = json.loads(rec_json)
    game = snapshot(rom)
    b = H.Brawler(rom=rom, game=game); b.game = game
    setup(b, rec)
    state = b.save()
    b.load(state)
    assert b.save() == state, 'a state saved right after its own load differs'
    open(os.path.join(out, key + '.state'), 'wb').write(state)
    frames = []
    def grab(b):
        if (b.frame - t0) % 2 == 0 or not frames:
            data, w, h, pitch = b._video
            frames.append((b.frame - t0, Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')))
    t0 = b.frame; b._want_video = True
    b.run(1, each=grab)                                    # the state's first frame, no keys (the banner's picture)
    frames[0][1].save(os.path.join(out, key + '_start.png'))
    for part in [p for p in (rec.get('do_keys') or '').split(',') if p]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''), each=grab)
    b.run(int(rec.get('proof', 90)), each=grab)
    b._want_video = False
    end = b.save()
    if key == 'mvs-mvs':
        g = frames[::max(1, len(frames) // 300)]                # at most ~300 pictures (a long wait is sped up)
        g[0][1].save(os.path.join(out, 'clip.gif'), save_all=True, append_images=[f for _, f in g[1:]],
                     duration=33 * max(1, len(frames) // 300), loop=0)
        pick = frames[::max(1, len(frames) // 16)][:16]
        w, h = pick[0][1].size
        sh = Image.new('RGB', (w * 4, (h + 14) * ((len(pick) + 3) // 4)), 'white'); d = ImageDraw.Draw(sh)
        for i, (f, im) in enumerate(pick):
            x, y = i % 4 * w, i // 4 * (h + 14); sh.paste(im, (x, y + 14)); d.text((x + 3, y + 1), f'frame +{f}', fill='black')
        sh.save(os.path.join(out, 'sheet.png'))
    info = {'key': key, 'state_sha256': sha256(state), 'size': len(state), 'end_sha256': sha256(end), 'frames': b.frame - t0,
            'hits': [h for h in b.hits if h[0] >= t0], 'end': b.brief((0, 2, 3, 4))}
    json.dump(info, open(os.path.join(out, key + '.json'), 'w'), indent=1)
    print(json.dumps(info))


def check_child(rid, key, rom, state_path, rec_json):
    """a fresh core: load the state, replay do_keys + proof, print the end state's sha256 (= gen's when deterministic)"""
    sys.path.insert(0, HERE)
    import harness as H
    H.OPTIONS.update(SYSTEMS[key])
    rec = json.loads(rec_json)
    b = H.Brawler(rom=rom, game=snapshot(rom))
    for _ in range(437): b.core.retro_run()               # this core has run frames before the load (as the player has)
    b.load(open(state_path, 'rb').read())
    b.run(1)
    for part in [p for p in (rec.get('do_keys') or '').split(',') if p]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''))
    b.run(int(rec.get('proof', 90)))
    print(sha256(b.save()))


# ---- the tracker (over ssh, as fb.py) ------------------------------------------------------------------------------------
def api(path, body=None):
    sys.path.insert(0, os.path.join(REPO, 'tools', 'feedback'))
    import fb
    return fb.api(path, body)


def get_recipe(rid):
    r = recipes().get(rid)
    if r is None:
        try: r = api('scenario/' + rid).get('recipe')
        except Exception: r = None
    if not r: sys.exit(f'scenario.py: no recipe for {rid} (scenarios.json or the tracker)')
    return r


def gen(rid, rom, rec=None, keys=tuple(SYSTEMS)):
    rec = rec or get_recipe(rid)
    sha = sha_file(rom); snapshot(rom)                     # once, before the children
    out = os.path.join(OUT, rid, sha[:12]); os.makedirs(out, exist_ok=True)
    res = {}
    for key in keys:
        r = subprocess.run([sys.executable, __file__, '_gen', rid, key, rom, out, json.dumps(rec)], capture_output=True, text=True)
        if r.returncode: raise RuntimeError(f'{rid} {key}: generation failed\n' + r.stderr[-3000:])
        res[key] = json.loads(r.stdout.strip().splitlines()[-1])
    json.dump({'id': rid, 'rom_sha256': sha, 'rom': rom, 'recipe': rec, 'states': res}, open(os.path.join(out, 'scenario.json'), 'w'), indent=1)
    return out, sha, res


def upload(rid, out, sha, res, version):
    """the states + the proof (clip, sheet, start pictures) to DATA/scenarios/<id>/<sha>/ and the event in the tracker"""
    rdir = f'{REMOTE}/{rid}/{sha}'
    subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, f'mkdir -p {shlex.quote(rdir)}'], check=True)
    files = [os.path.join(out, f) for f in sorted(os.listdir(out)) if f.endswith(('.state', '.png', '.gif', '.json'))]
    subprocess.run(['rsync', '-q'] + files + [f'{HOST}:{rdir}/'], check=True)
    return api('scenario_state', {'id': rid, 'rom_sha': sha, 'version': version, 'keys': sorted(res), 'by': 'scenario.py',
                                  'state_sha256': {k: v['state_sha256'] for k, v in res.items()}})


def version_of(rom):
    return json.load(open(os.path.join(os.path.dirname(os.path.dirname(snapshot(rom))), 'build.json')))['version']


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '_gen': return gen_child(*sys.argv[2:7])
    if len(sys.argv) > 1 and sys.argv[1] == '_check': return check_child(*sys.argv[2:7])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('show'); p.add_argument('id')
    p = sub.add_parser('put'); p.add_argument('id'); p.add_argument('file', nargs='?')
    for n in ('gen', 'verify'):
        p = sub.add_parser(n); p.add_argument('id'); p.add_argument('--rom', default=os.path.join(GAME, 'brawler.neo'))
        p.add_argument('--upload', action='store_true')
    p = sub.add_parser('publish'); p.add_argument('--rom', default=os.path.join(GAME, 'brawler.neo')); p.add_argument('--dry', action='store_true')
    p = sub.add_parser('backfill'); p.add_argument('--only', default=''); p.add_argument('--rom', default=os.path.join(GAME, 'brawler.neo'))
    p.add_argument('--no-upload', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'show':
        print(json.dumps(api('scenario/' + a.id), indent=1, ensure_ascii=False))
    elif a.cmd == 'put':
        rec = json.load(open(a.file)) if a.file else get_recipe(a.id)
        print(api('scenario', {'id': a.id, 'recipe': rec, 'by': 'scenario.py'})['ok'])
    elif a.cmd == 'gen':
        out, sha, res = gen(a.id, a.rom)
        for k, v in res.items(): print(k, v['state_sha256'][:16], v['size'], 'bytes; end', v['end'])
        print('proof:', out)
        if a.upload: print(upload(a.id, out, sha, res, version_of(a.rom)))
    elif a.cmd == 'verify':
        rec = get_recipe(a.id)
        out, sha, r1 = gen(a.id, a.rom, rec)
        _, _, r2 = gen(a.id, a.rom, rec)
        ok = True
        for k in SYSTEMS:
            same = r1[k]['state_sha256'] == r2[k]['state_sha256'] and r1[k]['end_sha256'] == r2[k]['end_sha256']
            c = subprocess.run([sys.executable, __file__, '_check', a.id, k, a.rom, os.path.join(out, k + '.state'), json.dumps(rec)],
                               capture_output=True, text=True)
            fresh = c.stdout.strip().splitlines()[-1] if c.returncode == 0 else 'error ' + c.stderr[-500:]
            print(f"{k}: two generations {'identical' if same else 'DIFFER'}; loaded in a fresh core, do + proof -> end state "
                  f"{'identical' if fresh == r1[k]['end_sha256'] else 'DIFFERENT (' + fresh[:16] + ')'}")
            ok &= same and fresh == r1[k]['end_sha256']
        print('proof:', out); sys.exit(0 if ok else 1)
    elif a.cmd in ('publish', 'backfill'):
        ver = version_of(a.rom)
        if a.cmd == 'publish':
            rows = api('list')['rows']
            ids = [r['id'] for r in rows if r['status'] in ('shipped', 'reopened', 'fixed')]
            have = {i for i in ids if api('scenario/' + i).get('recipe')}
            todo = [i for i in ids if i in have]
            print(f'{len(todo)} of {len(ids)} shipped / reopened / fixed notes have a recipe; build {ver} {sha_file(a.rom)[:12]}')
        else:
            R = recipes(); todo = [i for i in R if not a.only or i in a.only.split(',')]
        for rid in todo:
            if a.cmd == 'publish' and a.dry: print('would generate', rid); continue
            rec = recipes().get(rid) if a.cmd == 'backfill' else api('scenario/' + rid)['recipe']
            if a.cmd == 'backfill' and not a.no_upload: api('scenario', {'id': rid, 'recipe': rec, 'by': 'scenario.py backfill'})
            try:
                out, sha, res = gen(rid, a.rom, rec)
                if not getattr(a, 'no_upload', False): upload(rid, out, sha, res, ver)
                print(rid, 'ok', ' | '.join(f"{k} {v['state_sha256'][:12]}" for k, v in res.items()), '|', res['mvs-mvs']['end'])
            except Exception as e: print(rid, 'FAILED', e)


if __name__ == '__main__':
    main()
