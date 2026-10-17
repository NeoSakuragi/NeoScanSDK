#!/usr/bin/env python3
"""Bruno's notes of 2026-10-17 on 0.10.167, in our emulator (harness.py, the repo's Geolith core), before / after:

  20261017-141432-e03d (reopened) / 20261017-150524-e03d  Haggar's chain mashed: the frames each link plays before the
        next (roster[].chain.keep gone: back to 0.10.166's 15-frame links on hit)
  20261017-141149-e03d (reopened)  run + A: the victim's ejection (launch vx / vy, apex, distance to its landing) = the
        forward finisher's (jab, jab, forward + A); Haggar's frames in the attack (the +4 recovery kept)
  20261017-131927-e03d (reopened) / 20261017-150757-e03d  the stage-clear map (cheat DOWN + A + D): STAGE n CLEAR /
        ALL CLEAR in the big font, nothing under the map (lit pixels of the foot rows)

    notes1017c_proof.py OUT [--before GAME_DIR]     GAME_DIR: an older build's examples/brawler (brawler.neo + build/)
Writes OUT/sheet.png (one contact sheet, before / after) and OUT/report.json; ALL OK / FAIL on the after build."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
N_CHAIN, N_BLITZ, N_CLEAR = '20261017-141432-e03d', '20261017-141149-e03d', '20261017-131927-e03d'


def pic(b):
    from PIL import Image
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def play(b, keys, each):
    for part in [q for q in keys.split(',') if q]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''), each=each)


def eject(b, rec, keys, label, pics, title):
    """the dummy's flight from the hit that knocks it down: launch speed, apex, distance; P1's attack frames"""
    import scenario as S
    S.setup(b, rec); log = []; shot = {}
    def each(b):
        p, d = b.fighter(0), b.fighter(2); log.append((p['state'], d['state'], d['freeze'], d['x'], d['y'], d['vx'], d['vy'], p['node']))
        if d['state'] == 'KNOCKDOWN' and d['y'] > shot.get('y', -1): shot.update(y=d['y'], im=pic(b))
    b._want_video = True; play(b, keys, each); b._want_video = False
    att = sum(1 for s, *_ in log if s == 'ATTACK')
    k0 = next((i for i, (_, ds, fz, *_r) in enumerate(log) if ds == 'KNOCKDOWN' and fz == 0), None)
    k1 = next(i for i, r in enumerate(log) if r[1] == 'KNOCKDOWN')   # the knocking hit: P1's node then
    if k0 is None: return {'hit': False, 'attack_frames': att}
    _, _, _, x0, _, vx, vy, _ = log[k0]
    fl = log[k0:]
    air = fl[:next((i for i, r in enumerate(fl) if i > 1 and r[4] <= 0), len(fl))]   # the flight: launch to landing
    track = [(round(r[3] - x0, 2), round(r[4], 2)) for r in air]
    if shot: pics.append((f'{label} {title}: apex y{shot["y"]:.0f}', shot['im']))
    return {'hit': True, 'attack_frames': att, 'node': log[k1][7], 'vx': round(abs(vx), 2), 'vy': round(vy, 2), 'away': (vx > 0) - (vx < 0),
            'apex': round(max(r[4] for r in fl), 1), 'frames': len(air), 'distance': abs(track[-1][0]), 'track': track}


def chain(b, R):
    import scenario as S
    S.setup(b, R[N_CHAIN]); log = []
    play(b, R[N_CHAIN]['do_keys'], lambda b: log.append((b.fighter(0)['state'], b.fighter(0)['node'])))
    runs = []
    for i, (s, nd) in enumerate(log):
        if s != 'ATTACK': continue
        if runs and runs[-1][0] == nd and runs[-1][2] == i - 1: runs[-1][1] += 1; runs[-1][2] = i
        else: runs.append([nd, 1, i])
    return [r[1] for r in runs]


def clear(b, label, pics, stage):
    import scenario as S, harness as H
    S.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': stage, 'wave': 1}})
    keys = H.stage_clear_keys(b.game) if hasattr(H, 'stage_clear_keys') else 'Dad'
    b.run(20); t = 0
    while b.r(b.syms['phase'], 1) < 3 and t < 400: b.run(1, p1=keys); t += 1
    b._want_video = True; seen = None; r = {'map': False}
    for k in range(900):
        b.run(1)
        if b.r(b.syms['map_on'], 1):
            if seen is None: seen = k
            if k - seen == 90:
                im = pic(b); px = im.load(); r['map'] = True; W, Hh = im.size
                im.save(os.path.join(b.out, f'clear{stage + 1}_{b.label}.png'))
                # the foot rows: under the map (game.json map.y + its 88 px + 8: the fix rows NEXT ... used)
                g = json.load(open(os.path.join(b.game, 'game.json')))['map']; y0 = g["y"] + 88 + 8
                import ctypes as C                       # the foot rows on the fix layer (VRAM $7000 + col x 32 + row):
                vr = (C.c_uint16 * 0x7800).from_address(b.core.retro_get_memory_data(3))   # tiles other than the blank
                row0 = g['y'] // 8; foot = [row0 + 88 // 8 + k + 2 for k in (1, 2)]   # (FIX_print's row + 2 in VRAM)
                r['foot_tiles'] = sum(1 for rw in foot for c in range(1, 39) if vr[0x7000 + c * 32 + rw] & 0xFFF not in (0, 32))
                pics.append((f'{label} stage {stage + 1} clear map +90', im)); break
    b._want_video = False
    return r


def one(game, label, out):
    import harness as H, scenario as S
    b = H.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); b.game = game; b.out = out; b.label = label
    R = S.recipes(); pics = []
    rep = {'chain': chain(b, R),
           'run_a': eject(b, R[N_BLITZ], R[N_BLITZ]['do_keys'], label, pics, 'run+A'),
           'fwd_fin': eject(b, {'setup': dict(R[N_BLITZ]['setup'], gap=40)}, '2:a,4:-,2:a,4:-,2:a,4:-,2:Ra,4:-,2:Ra,4:-,2:Ra,90:-', label, pics, 'jab jab fwd+A'),
           'clear1': clear(b, label, pics, 0), 'clear3': clear(b, label, pics, 2)}
    import pickle
    pickle.dump(pics, open(os.path.join(out, f'pics_{label}.pkl'), 'wb'))
    print(json.dumps({label: rep}))


def main():
    a = sys.argv[1:]
    if a and a[0] == '_one': return one(*a[1:4])
    out = a[0]; os.makedirs(out, exist_ok=True)
    runs = [('after', os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))]
    if '--before' in a: runs.insert(0, ('before', a[a.index('--before') + 1]))
    rep = {}
    for label, game in runs:
        r = subprocess.run([sys.executable, __file__, '_one', game, label, out], capture_output=True, text=True)
        if r.returncode: sys.exit(r.stderr[-3000:])
        rep.update(json.loads(r.stdout.strip().splitlines()[-1]))
    import pickle
    from PIL import Image, ImageDraw
    pics = [p for label, _ in runs for p in pickle.load(open(os.path.join(out, f'pics_{label}.pkl'), 'rb'))]
    w, h = pics[0][1].size; cols = 4
    sh = Image.new('RGB', (w * cols, (h + 14) * ((len(pics) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sh)
    for i, (t, im) in enumerate(pics):
        x, y = i % cols * w, i // cols * (h + 14); sh.paste(im, (x, y + 14)); d.text((x + 3, y + 1), t, fill='black')
    sh.save(os.path.join(out, 'sheet.png'))
    json.dump(rep, open(os.path.join(out, 'report.json'), 'w'), indent=1)
    print(json.dumps(rep, indent=1))
    A, B = rep['after'], rep.get('before')
    ra, ff = A['run_a'], A['fwd_fin']
    ok = {
        'chain back to 15-frame links': A['chain'][:2] == [15, 15],
        'run+A ejects as the forward finisher': ra['hit'] and ff['hit'] and all(ra[k] == ff[k] for k in ('vx', 'vy', 'away', 'apex', 'frames', 'track')),
        'run+A +4 recovery kept': not B or A['run_a']['attack_frames'] == B['run_a']['attack_frames'],
        'forward finisher measured (not the Blitz)': ff['node'] != ra['node'],
        'clear maps shown, nothing under them': all(A[k]['map'] and A[k]['foot_tiles'] == 0 for k in ('clear1', 'clear3')),
    }
    for k, v in ok.items(): print(('ok   ' if v else 'FAIL ') + k)
    print('ALL OK' if all(ok.values()) else 'FAIL')


if __name__ == '__main__':
    main()
