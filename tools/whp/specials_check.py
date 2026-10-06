#!/usr/bin/env python3
"""Every ground special's three strength rows (moves_whp.specials) played by WHP in our emulator (P2 walked away first:
a whiff) against the model the export plays (handlers_whp.play): anim, step, def, x, y frame by frame from the move's
first frame until Hanzou is back in neutral.

    python3 specials_check.py OUT.json [--capture CAP.json]     (--capture: capture again into CAP.json)"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_whp as cap, capture_whp as C, moves_whp as MW, handlers_whp as H, export_whp as E

DIRS = {'N': '-', 'U': 'U', 'D': 'D', 'L': 'L', 'R': 'R', 'DR': 'DR', 'DL': 'DL', 'UR': 'UR', 'UL': 'UL'}
BTN = {'A': 'a', 'B': 'b', 'AB': 'ab', 'C': 'c', 'D': 'd', 'CD': 'cd'}

def recipe(sp, row):
    dirs = [DIRS[H.DIRS[d]] for d, _ in sp['motion']]
    seq = C.m(dirs, BTN[row['button']]) + '160:-'
    return C.away(seq), C.AWAY

def capture_one(args):
    sp, row = args
    seq, seq2 = recipe(sp, row)
    rows = cap.run(seq, seq2, span=0x200)
    out = []
    for r in rows:
        o = cap.obj(r, 0)
        out.append([o['anim'] - o['base'], o['step'], o['defw'], o['x'] / 128 + r['cam'], (o['y'] - r['floor']) / 128])
    return f"{E.special_input(sp)}:{row['button']}", out

def wave_check(sp, row, frames=60):
    """the wave pair (handlers_whp.wave_objects / wave_flight) vs WHP's two pool objects (routine $4E934), whiff: per
    object x / y / def per frame from its spawn until it leaves or 60 frames"""
    seq, seq2 = recipe(sp, row)
    rows = cap.run(seq, seq2, span=0x3000)
    eff = next(int(a, 16) for e in H.entries(0, row['rel']) if e['ctrl'] is None for c, a in e['cmds'] if c == 9)
    objs = H.wave_objects(eff); U = cap.u16
    s0 = next(i for i, r in enumerate(rows) if cap.obj(r, 0)['anim'] - cap.obj(r, 0)['base'] == row['rel'])
    x0 = cap.obj(rows[s0], 0)['x'] / 128 + rows[s0]['cam']
    seen = {}
    for i, r in enumerate(rows):
        o = r['obj']
        for a in range(0x200, 0x3000, 0x80):
            if (U(o, a + 4) << 16 | U(o, a + 6)) != objs[0]['routine'] or not o[a + 0x28]: continue
            seen.setdefault(a, []).append((i, U(o, a + 2) / 128 + r['cam'] - x0, (U(o, a) - r['floor']) / 128, U(o, a + 8)))
    out = []
    for a, tr in sorted(seen.items()):
        t0 = tr[0][0]
        m = min(objs, key=lambda ob: abs((ob['dy'] + ob['vy']) - tr[0][2]))
        mod = H.wave_flight(m, frames)
        bad = [[k, [round(x, 2), round(y, 2), d], [round(mod[k]['x'], 2), round(mod[k]['y'], 2), mod[k]['defw']]]
               for k, (i, x, y, d) in enumerate(tr[:frames]) if i - t0 == k and (abs(x - mod[k]['x']) > 1.01 or abs(y - mod[k]['y']) > 1.01 or d != mod[k]['defw'])]
        out.append({'slot': f'{a:X}', 'spawn_frame': t0 - s0, 'frames': min(len(tr), frames), 'mismatches': len(bad), 'first_bad': bad[:3],
                    'vy0': m['vy'], 'ay': m['ay'], 'vx': m['vx']})
    return out

def check(capd):
    res = {}
    for sp in MW.specials(H.ROWS['hanzo'], H.CHARS['hanzo']):
        inp = E.special_input(sp)
        for row in sp['rows']:
            k = f"{inp}:{row['button']}"; fr = capd[k]
            s0 = next((i for i, f in enumerate(fr) if f[0] == row['rel']), None)
            if s0 is None: res[k] = {'error': 'the move never started'}; continue
            mod = H.play('hanzo', row['rel'], first_ticks=inp in E.FIRST_TICKS, maxf=400)
            x0 = fr[s0][3]; bad = []; bound = None
            for i, q in enumerate(mod):
                if s0 + i >= len(fr): bad.append([i, 'capture ended']); break
                c = fr[s0 + i]
                # WHP's screen bound (P1 walked to the edge by the whiff's set-up, or the screen's width): the capture's
                # x stops while the model moves on; from there x is not compared (the brawler has no fixed screen)
                if bound is None and i and abs(c[3] - fr[s0 + i - 1][3]) < 0.01 and abs(q['x'] - mod[i - 1]['x']) > 0.01: bound = i
                ok = [q['anim'], q['step'], q['defw']] == c[:3] and (bound is not None or abs(q['x'] - (c[3] - x0)) < 1.01) and abs(q['y'] - c[4]) < 1.01
                if not ok: bad.append([i, [hex(q['anim']), q['step'], hex(q['defw']), round(q['x'], 2), round(q['y'], 2)],
                                       [hex(c[0]), c[1], hex(c[2]), round(c[3] - x0, 2), round(c[4], 2)]])
            after = fr[s0 + len(mod)][0] if s0 + len(mod) < len(fr) else None
            res[k] = {'strength': row['strength'], 'anim': f"${row['rel']:X}", 'frames': len(mod), 'identical': len(mod) - len(bad),
                      'x_from_bound': bound, 'first_bad': bad[:3], 'next_anim': after, 'travel': round(mod[-1]['x']),
                      'height': round(max(q['y'] for q in mod))}
    return res

if __name__ == '__main__':
    capf = sys.argv[sys.argv.index('--capture') + 1] if '--capture' in sys.argv else '/data/tmp/whp6/specials_cap.json'
    if '--capture' in sys.argv or not os.path.exists(capf):
        jobs = [(sp, row) for sp in MW.specials(H.ROWS['hanzo'], H.CHARS['hanzo']) for row in sp['rows']]
        with ThreadPoolExecutor(8) as ex: capd = dict(ex.map(capture_one, jobs))
        json.dump(capd, open(capf, 'w'))
    res = check(json.load(open(capf)))
    # the projectiles of every row (handlers_whp.koryuuha's object model vs WHP's pool object, P2 pinned at 400: hit)
    for sp in MW.specials(H.ROWS['hanzo'], H.CHARS['hanzo']):
        inp = E.special_input(sp)
        if inp == '23536P':
            for row in sp['rows']: res[f'{inp}:{row["button"]}']['projectile'] = wave_check(sp, row)
            continue
        if inp not in ('236P',): continue
        mot = ' '.join(DIRS[H.DIRS[d]] for d, _ in sp['motion'])
        def one(row): return row['button'], H.koryuuha_check(row['button'], True, rel=row['rel'], motion=mot)
        with ThreadPoolExecutor(3) as ex:
            for b, r in ex.map(one, sp['rows']): res[f'{inp}:{b}']['projectile'] = r
    json.dump(res, open(sys.argv[1], 'w'), indent=1)
    for k, v in res.items():
        if 'projectile' in v: p = v['projectile']; print(k, 'projectile: flight', p['flight_frames'], 'frames, mismatches', p['mismatches'], 'spawn', p['spawn_frame'], '/', p['model_spawn_frame'], 'hit at', p['hit_frame'], 'impact', p['impact_ok'], 'vx', p['vx'])
    for k, v in res.items(): print(k, v.get('strength'), v.get('anim'), f"{v.get('identical')} / {v.get('frames')}", 'travel', v.get('travel'), 'height', v.get('height'), v.get('first_bad', v.get('error')))
