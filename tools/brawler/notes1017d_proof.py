#!/usr/bin/env python3
"""Note 20261017-141149-e03d reopened on 0.10.170 (Bruno: "when the opponent is launched in the air there's a different
behaviour, and the air behaviour lets me juggle more and more: apply the same behaviour when the enemy is grounded
versus when the enemy is in the air"), in our emulator (harness.py, the repo's Geolith core), before / after:

  ground   Haggar's run + A (the ff Blitz, routes/haggar.json entries.dash) on a standing Ryo: launch vx / vy, the track
  air      the same run + A on Ryo held airborne (S_KNOCKDOWN at AIR_Y px, a juggle) until it lands: the same launch
           and the same track from where it is (RF_AIR_SAME), not the engine's air hit (vy 5, vx 1.5)
  fwd_air  his forward finisher (jab, jab, forward + A) on Ryo held airborne: the same (finishers.air.forward)
  loop     run + A pressed again and again on the juggled Ryo: its air hits, the frame it lands (the loop ends)

    notes1017d_proof.py OUT [--before GAME_DIR]     GAME_DIR: an older build's examples/brawler (brawler.neo + build/)
Writes OUT/sheet.png (one contact sheet, before / after) and OUT/report.json; ALL OK / FAIL on the after build."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
NOTE, AIR_Y = '20261017-141149-e03d', 24
RUN_A = '4:R,4:-,20:R,2:Ra,60:-'
FWD = '2:a,4:-,2:a,4:-,2:a,4:-,2:Ra,4:-,2:Ra,4:-,2:Ra,90:-'
LOOPS = [('4:R,4:-,12:R,2:Ra,30:-', 10), ('2:R,2:-,6:R,2:Ra,4:R', 25), ('1:R,1:-,4:R,2:Ra,8:R', 25),   # the chase after the
         ('2:Ra,4:R', 50), ('2:R,2:-,10:R,2:Ra,2:R', 25), ('3:R,3:-,8:R,2:Ra,16:-', 20)]               # first run + A: run +
                                                                    # A again and again, several rhythms (some with jabs)
CHAIN_LOOPS = [('2:a,4:-,2:a,4:-,2:Ra,6:R', 12), ('2:Ra,4:R', 60), ('2:a,6:-,2:a,6:-,2:Ra,10:R,4:R,4:-,8:R,2:Ra,6:R', 8)]
                                                                    # jab, jab, forward + A (the forward finisher) on the
                                                                    # juggled Ryo close by, again and again, with run + A


def pic(b):
    from PIL import Image
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def flight(b, rec, keys, air, label, pics, title, frames=0, nth=1, air_y=AIR_Y):
    """Ryo's flight from the hit that knocks it down (held at AIR_Y until P1's nth hit when air): launch vx / vy, the
    track (dx, y - y0) to its landing; every later hit in the air (the loop) and the frame it lies (nth: the hit
    measured, the chain's finisher is its third)"""
    import scenario as S
    S.setup(b, rec); log = []; st = {'held': air, 'hp': None, 'pic': None, 'n': 0}
    KD = b.states.index('KNOCKDOWN')
    def each(b):
        d = b.fighter(2)
        if st['hp'] is None: st['hp'] = d['hp']
        if d['hp'] < st['hp']: st['n'] += 1; st['hp'] = d['hp']
        if st['held'] and st['n'] >= nth: st['held'] = False          # its hit: from here the engine's own flight
        if st['held']:
            for f, v in (('state', KD), ('y', air_y), ('vy', 0), ('vx', 0), ('kfloor', 0), ('kmode', 0), ('jug_n', 0)): b.fset(2, f, v)
            d = b.fighter(2)
        log.append((d['state'], d['freeze'], d['x'], d['y'], d['vx'], d['vy'], d['hp'], d['kfloor'], d['jug_n']))
        if st['pic'] is None and st['n'] >= nth and len(log) > 1 and log[-2][6] > d['hp']: st['pic'] = len(log) + 12
        if st['pic'] == len(log): pics.append((f'{label} {title}: hit + 12', pic(b)))
    b._want_video = True
    for part in [q for q in keys.split(',') if q]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''), each=each)
    if frames: b.run(frames, each=each)
    b._want_video = False
    hits = [i for i in range(1, len(log)) if log[i][6] < log[i - 1][6]]
    if not hits: return {'hit': False}
    if len(hits) < nth: return {'hit': False}
    k0 = next((i for i in range(hits[nth - 1], len(log)) if log[i][0] == 'KNOCKDOWN' and log[i][1] == 0), None)
    _, _, x0, y0, vx, vy, *_ = log[k0]
    fl = log[k0:]
    n = next((i for i, r in enumerate(fl) if i > 1 and (r[3] <= 0 or r[0] != 'KNOCKDOWN')), len(fl))
    track = [(round(abs(r[2] - x0), 2), round(r[3] - y0, 2)) for r in fl[:n]]
    lands = next((i for i in range(hits[0], len(log)) if log[i][7]), None)
    return {'hit': True, 'y0': round(y0, 1), 'vx': round(abs(vx), 2), 'vy': round(vy, 2), 'frames': n,
            'rise': round(max(t[1] for t in track), 1), 'distance': track[-1][0], 'track': track,
            'hits': len(hits), 'air_hits': sum(1 for i in hits if log[i - 1][3] > 0 and (lands is None or i <= lands)),
            'jug_n': max(r[8] for r in log),                       # (air_hits: the juggle, its hits before it first lands)
            'lands_after': None if lands is None else lands - hits[0], 'log_frames': len(log)}


def one(game, label, out):
    import harness as H, scenario as S
    b = H.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    R = S.recipes()[NOTE]; pics = []
    near = {'setup': dict(R['setup'], gap=40)}
    rep = {'ground': flight(b, R, RUN_A, False, label, pics, 'run+A grounded'),
           'air': flight(b, R, RUN_A, True, label, pics, 'run+A airborne'),
           'fwd_ground': flight(b, near, FWD, False, label, pics, 'jab jab fwd+A grounded', nth=3),
           'fwd_air': flight(b, near, FWD, True, label, pics, 'jab jab fwd+A airborne', nth=3),
           **{f'loop{i}_{h}': flight(b, R, RUN_A + ',' + ','.join([p] * n), True, label, pics if i == 0 and h == 64 else [],
                                     f'run+A loop from {h} px', 120, air_y=h)
              for h in (24, 64) for i, (p, n) in enumerate(LOOPS)},   # (64 px: a high juggle, as from his throw's launch)
           **{f'loopc{i}_{h}': flight(b, near, ','.join([p] * n), True, label, [], f'chain loop from {h} px', 120, air_y=h)
              for h in (24, 64) for i, (p, n) in enumerate(CHAIN_LOOPS)}}
    for k in rep: rep[k].pop('log_frames', None)
    import pickle
    pickle.dump(pics, open(os.path.join(out, f'pics_{label}.pkl'), 'wb'))
    print(json.dumps({label: rep}))


def plot(rep, w, h):
    """the tracks (dx, y - y0) of grounded / airborne hits, one panel per build"""
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (w, h), 'white'); d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w - 1, h - 1), outline='black')
    ox, oy, s = 8, h // 2 + 10, 1.0
    d.line((ox, oy, w - 8, oy), fill='black'); d.text((ox, 4), 'track from the hit: dx, y - y0 (px)', fill='black')
    styles = {'ground': (0, 'solid'), 'air': (3, 'dots'), 'fwd_ground': (0, 'solid'), 'fwd_air': (3, 'dots')}
    for k, (r, sty) in styles.items():
        t = rep[k].get('track') or []
        pts = [(ox + x * s, oy - y * s * 2) for x, y in t]
        if sty == 'solid' and len(pts) > 1: d.line(pts, fill='black', width=1)
        else:
            for x, y in pts: d.ellipse((x - 2, y - 2, x + 2, y + 2), outline='black')
    d.text((ox, h - 26), 'line: grounded  circles: airborne', fill='black')
    return im


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
    pics = []
    for label, _ in runs:
        p = pickle.load(open(os.path.join(out, f'pics_{label}.pkl'), 'rb'))
        w, h = p[0][1].size
        pics += p + [(f'{label}: tracks', plot(rep[label], w, h))]
    w, h = pics[0][1].size; cols = 6
    sh = Image.new('RGB', (w * cols, (h + 14) * ((len(pics) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sh)
    for i, (t, im) in enumerate(pics):
        x, y = i % cols * w, i // cols * (h + 14); sh.paste(im, (x, y + 14)); d.text((x + 3, y + 1), t, fill='black')
    sh.save(os.path.join(out, 'sheet.png'))
    json.dump(rep, open(os.path.join(out, 'report.json'), 'w'), indent=1)
    show = {L: {k: {f: v for f, v in r.items() if f != 'track'} for k, r in R.items()} for L, R in rep.items()}
    print(json.dumps(show, indent=1))
    A, B = rep['after'], rep.get('before')
    g, ai, fg, fa = A['ground'], A['air'], A['fwd_ground'], A['fwd_air']
    loops = lambda R: [R[k] for k in sorted(R) if k.startswith('loop')]
    print('air hits per loop: ' + '  '.join(f"{L} {[r.get('air_hits') for r in loops(R)]}" for L, R in rep.items()))
    same = lambda p, q: p['hit'] and q['hit'] and p['vx'] == q['vx'] and p['vy'] == q['vy'] and q['track'][:len(p['track'])] == p['track']
    ok = {
        'run+A airborne = grounded (vx, vy, track from where it is)': same(g, ai) and ai['y0'] > 0,
        'forward finisher airborne = grounded': same(fg, fa) and fa['y0'] > 0,
        'run+A = forward finisher (grounded)': same(g, fg),
        'run+A loops on a juggled Ryo end (it lands, juggle cap kept)': all(lp['hit'] and lp['lands_after'] is not None and
            lp['jug_n'] <= 5 for lp in loops(A)),
        'no loop juggles more than before': not B or all(a['air_hits'] <= b['air_hits'] for a, b in zip(loops(A), loops(B))),
    }
    for k, v in ok.items(): print(('ok   ' if v else 'FAIL ') + k)
    print('ALL OK' if all(ok.values()) else 'FAIL')


if __name__ == '__main__':
    main()
