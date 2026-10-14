#!/usr/bin/env python3
"""Throw tie / ejection audit (T1, docs/brawler_throws_review.md): reads the per-frame cases throws_audit.py ran (OUT/<case>.json:
thrower + victim place, facing, shown frame per frame, our emulator) and draws both fighters' frames from their exports
(build/tmp_<game>_<name>: the pixels the game shows) to measure what the eye sees:

  gap   held frames (the script holds the pair: S_THROW + S_THROWN, or a hold): the smallest distance between the
        thrower's opaque pixels and the victim's (0 = they touch / overlap). A tied throw keeps gap 0 (a hand on the
        body); gap > TIE_PX = visibly apart ("not tying the victim")
  jump  the victim's largest one-frame move of its origin (px) and of its pixel centre (a posture swap that jumps)
  arc   after the release: the victim's path (x, y per frame), its top, its landing frame and x, frames below the floor,
        frames the victim is outside the screen

    python3 throw_tie.py OUT CASE [CASE ...]      -> OUT/tie_<case>.json + OUT/tie_<case>.png (line-art proof sheet)
    python3 throw_tie.py OUT --all                every OUT/*.json case -> OUT/tie_summary.json + a table on stdout

Proof sheet (e-ink: black on white): one tile per sampled frame, thrower drawn as a black outline, victim filled grey,
the gap's two nearest pixels joined by a line labelled with the px; under them the ejection arc (victim origin per
frame, dots) with the floor line."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import head_point as HP
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
BUILD = os.environ.get('THROWS_REF') or os.path.join(GAME, 'build')
TIE_PX = 6                                                   # px apart: visibly not tied
HELD_T = ('THROW', 'GRAB', 'SPECIAL')
HELD_V = ('THROWN', 'GRABBED')
_CH = {}


def bank(name):
    if not _CH:
        for r in json.load(open(os.path.join(BUILD, 'roster.json'))):
            g, n = r['bank'].split(':'); _CH[r['name']] = (os.path.join(BUILD, f'tmp_{g}_{n}'), n)
    return _CH[name]


_LD, _MASK = {}, {}
def mask(name, fi):
    """fighter name's frame fi: (ys, xs) of its opaque pixels, px from the feet, facing left"""
    k = (name, fi)
    if k not in _MASK:
        if name not in _LD: _LD[name] = HP.load(*bank(name))
        ch, reg = _LD[name]
        if fi is None or fi < 0 or fi >= len(ch['frames']): _MASK[k] = (np.zeros(0, int), np.zeros(0, int))
        else:                                                # (as export_bm.frame_centre: no canvas, nothing clipped)
            Y, X = [], []
            for p in ch['frames'][fi]['parts']:
                for c_, col in enumerate(p['tiles']):
                    for r_, t_ in enumerate(col):
                        if not t_: continue
                        ys, xs = np.nonzero(HP.tile(reg, t_))   # (draw.s: a flipped part is the whole part mirrored
                        xs = xs + p['dx'] + 16 * c_; ys = ys + p['dy'] + 16 * r_   # about the origin, its dx / dy
                        if p['hflip']: xs = -xs - 1                  # negated: x0 = ox - dx - w)
                        if p['vflip']: ys = -ys - 1
                        Y.append(ys); X.append(xs)
            _MASK[k] = (np.concatenate(Y) if Y else np.zeros(0, int), np.concatenate(X) if X else np.zeros(0, int))
    return _MASK[k]


def world(name, s):
    """a snapshot's fighter as world pixels (x right, y up)"""
    ys, xs = mask(name, s['shown_frame'])
    if s['facing'] > 0: xs = -xs                             # (ROM frames face left)
    return s['x'] + xs, s['y'] - ys


def gap(a, b):
    """the smallest distance between two pixel sets (0: they touch), and the two nearest points"""
    ax, ay = a; bx, by = b
    if not len(ax) or not len(bx): return None, None
    A = np.stack([ax, ay], 1)[::3]; B = np.stack([bx, by], 1)[::3]   # (every third pixel: within 2 px)
    d = np.abs(A[:, None, :] - B[None, :, :]).max(2)         # (chessboard distance)
    i = np.unravel_index(np.argmin(d), d.shape)
    return float(max(0, d[i] - 2)), (A[i[0]].tolist(), B[i[1]].tolist())


_D = {}
def src_rows(tn, key):
    """the source's own pair per script row (the mirror match: what the source game draws): [(tframe, tx, ty, flags, vf,
    vx, vy)], vf = the source victim's frame in the thrower's own export (export json throws[key].victims[its name])"""
    if not _D:
        import throws_audit as TA
        _D['d'] = TA.data()[0]
    th = (_D['d'].get(tn) or {}).get(key)
    if not th: return None
    if tn not in _LD: _LD[tn] = HP.load(*bank(tn))
    ex = (_LD[tn][0].get('throws') or {}).get(key)
    if not ex or not ex.get('victims'): return None
    vic = ex['victims'].get(bank(tn)[1]) or next(iter(ex['victims'].values()))
    return [(r[0], r[1], r[2], r[4], vic[min(i, len(vic) - 1)][0], r[5], r[6]) for i, r in enumerate(th['rows'])]


def src_gap(tn, R, i):
    """the source's gap at row i (both fighters the thrower's own export: the mirror match), None: no victim frame"""
    tf, tx, ty, fl, vf, vx, vy = R[min(i, len(R) - 1)]
    if vf is None or vf < 0 or fl & 32: return None
    T = dict(x=tx, y=ty, facing=-1 if fl & 8 else 1, shown_frame=tf)
    V = dict(x=tx + vx, y=ty + vy, facing=1 if fl & 1 else -1, shown_frame=vf)
    return gap(world(tn, T), world(tn, V))[0]


def tie(out, spec):
    res = json.load(open(os.path.join(out, spec.replace(':', '_') + '.json')))
    tn, vn, ft = res['thrower'], res['victim'], res['floor_top']
    rp = os.path.join(out, 'rep_' + spec.replace(':', '_') + '.json')
    rep = json.load(open(rp)) if os.path.exists(rp) else {}
    rel = rep.get('rel', 0xFFFF)                                 # (a victim list / hold: none)
    R = src_rows(res['thrower'], rep['throw']) if rep.get('throw', '').startswith('throw') else None
    F = []
    for r in res['rows']:
        T, V = r['t'], r['v']
        held = (V['state'] == 'GRABBED' or V['state'] == 'THROWN' and V['srow'] - 1 < rel or   # (in the hands: before the
                V['state'] == 'HITSTUN' and T['state'] == 'SPECIAL' and T['vlist'] and not T['vlist'] & 0x80)   # release row)
        wt, wv = world(tn, T), world(vn, V)
        g, pts = gap(wt, wv) if held else (None, None)
        c = (float(np.mean(wv[0])), float(np.mean(wv[1]))) if len(wv[0]) else (V['x'], V['y'])
        sg = src_gap(tn, R, V['srow'] - 1) if held and R and V['state'] == 'THROWN' else None
        F.append(dict(f=r['f'], sgap=sg, row=V['srow'] - 1, cam=r['cam'], ts=T['state'], vs=V['state'], held=held, gap=g, pts=pts, vx=V['x'], vy=V['y'],
                      tx=T['x'], vc=c, vfr=V['shown_frame'], tfr=T['shown_frame'], vface=V['facing'], tface=T['facing']))
    H = [f for f in F if f['held'] and f['gap'] is not None]
    rel = next((i for i, f in enumerate(F) if f['f'] >= 0 and not f['held'] and f['vs'] in ('THROWN', 'KNOCKDOWN')), None)
    st = [f for f in F if f['f'] >= 0]
    J = [(round(abs(b['vx'] - a['vx']) + abs(b['vy'] - a['vy']), 1), round(abs(b['vc'][0] - a['vc'][0]) + abs(b['vc'][1] - a['vc'][1]), 1), b['f'], a['vs'], b['vs'], a['vfr'], b['vfr'])
         for a, b in zip(st, st[1:]) if a['vs'] in HELD_V + ('KNOCKDOWN',) and b['vs'] in HELD_V + ('KNOCKDOWN', 'DOWN')]
    jo = max((j[0] for j in J), default=0); jc = max((j[1] for j in J), default=0)
    jumps = sorted(J, reverse=True, key=lambda j: max(j[0], j[1]))[:4]
    arc = [f for f in F[rel:]] if rel is not None else []
    land = next((f for f in arc if f['vs'] in ('DOWN', 'KNOCKDOWN') and f['vy'] <= 0.5 and f is not arc[0]), None)
    off = [f['f'] for f in F if f['f'] >= 0 and (f['vx'] - f['cam'] < -8 or f['vx'] - f['cam'] > 312)]
    # the free flight (not held, airborne): the engine's or the script's; its per-frame vertical steps
    fl = [f for f in arc if f['vs'] in ('THROWN', 'KNOCKDOWN')]
    dvy = [round(b['vy'] - a['vy'], 1) for a, b in zip(fl, fl[1:])]
    accel = [round(b - a, 2) for a, b in zip(dvy, dvy[1:])]
    s = dict(case=spec, thrower=tn, victim=vn, held_frames=len(H),
             gap_max=max((f['gap'] for f in H), default=None), gap_bad=sum(f['gap'] > TIE_PX for f in H),
             gap_excess=sum(f['sgap'] is not None and f['gap'] > f['sgap'] + TIE_PX for f in H),
             excess_max=max((f['gap'] - f['sgap'] for f in H if f['sgap'] is not None), default=None),
             src_gap_max=max((f['sgap'] for f in H if f['sgap'] is not None), default=None),
             gap_first_bad=next((f['f'] for f in H if f['gap'] > TIE_PX), None),
             jump_origin=round(jo, 1), jump_centre=round(jc, 1), jumps=jumps,
             release_f=F[rel]['f'] if rel is not None else None,
             arc_top=round(max((f['vy'] for f in arc), default=0), 1),
             land_f=land['f'] if land else None, land_dx=round((land['vx'] - F[rel]['vx']) * (1 if F[rel]['tface'] > 0 else -1), 1) if land and rel is not None else None,
             below_floor=sum(f['vy'] < -0.5 for f in F if f['vs'] in ('KNOCKDOWN', 'DOWN')),
             offscreen=len(off), accel_changes=sum(abs(b - a) > 0.6 for a, b in zip(accel, accel[1:])),
             end_v=F[-1]['vs'], end_t=F[-1]['ts'])
    json.dump(dict(summary=s, frames=F), open(os.path.join(out, 'tie_' + spec.replace(':', '_') + '.json'), 'w'))
    sheet(out, spec, F, ft, tn, vn, s)
    return s


def sheet(out, spec, F, ft, tn, vn, s):
    from PIL import Image, ImageDraw
    st = [f for f in F if f['f'] >= 0]
    H = [f for f in st if f['held']]
    bad = [f for f in H if f['gap'] is not None and f['gap'] > TIE_PX]
    rest = [f for f in st if not f['held']]
    hand = [x for a, b in zip(st, st[1:]) if a['vs'] == 'THROWN' and b['vs'] != 'THROWN' for x in (a, b)]   # (the hand-off)
    pick = (H[::max(1, len(H) // 5)][:5] + bad[:2] + hand[:2] + rest[::max(1, len(rest) // 3)][:3])
    pick = sorted({f['f']: f for f in pick}.values(), key=lambda f: f['f'])[:12]
    W, Hh = 200, 240
    tiles = []
    for f in pick:
        im = Image.new('L', (W, Hh), 255); px = im.load()
        ox = (f['tx'] + f['vx']) / 2 - W / 2; oy = 225                 # (world -> tile: the pair's middle, floor at 225)
        r = next(r for r in json.load(open(os.path.join(out, spec.replace(':', '_') + '.json')))['rows'] if r['f'] == f['f'])
        for nm, sn, fill in ((vn, r['v'], 150), (tn, r['t'], None)):
            xs, ys = world(nm, sn)
            P = set(zip((xs - ox).astype(int).tolist(), (oy - ys).astype(int).tolist()))
            for (x, y) in P:
                if not (0 <= x < W and 0 <= y < Hh): continue
                if fill is not None: px[x, y] = fill
                elif any((x + dx, y + dy) not in P for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))): px[x, y] = 0
        g = ImageDraw.Draw(im)
        g.line((0, oy, W, oy), fill=0)
        if f['pts']:
            (ax, ay), (bx, by) = f['pts']
            g.line((ax - ox, oy - ay, bx - ox, oy - by), fill=0, width=1)
        lab = f"f{f['f']} {f['vs'][:6]}" + (f" gap {f['gap']:.0f}" if f['gap'] is not None else '') + (' APART' if f['gap'] is not None and f['gap'] > TIE_PX else '')
        g.rectangle((0, 0, W, 11), fill=255); g.text((2, 0), lab, fill=0); g.rectangle((0, 0, W - 1, Hh - 1), outline=0)
        tiles.append(im)
    # the ejection arc: the victim's origin per frame (world, from the throw's start), floor line
    A = Image.new('L', (W * 4, Hh), 255); g = ImageDraw.Draw(A)
    xs = [f['vx'] for f in st] + [f['tx'] for f in st]; x0 = min(xs) - 10; sc = min(1.0, (W * 4 - 20) / max(1, max(xs) - x0))
    g.line((0, 225, W * 4, 225), fill=0)
    for f in st:
        x, y = 10 + (f['vx'] - x0) * sc, 225 - f['vy'] * sc
        g.ellipse((x - 1, y - 1, x + 1, y + 1), fill=0 if f['held'] else 120)
        tx = 10 + (f['tx'] - x0) * sc; g.point((tx, 227), fill=0)
    g.text((2, 0), f"{spec}: victim {vn} origin per frame (black held, grey free), thrower x under the floor line | "
                   f"gap max {s['gap_max']} bad {s['gap_bad']}/{s['held_frames']}  top {s['arc_top']}  land dx {s['land_dx']}  "
                   f"below floor {s['below_floor']}  offscreen {s['offscreen']}", fill=0)
    g.rectangle((0, 0, W * 4 - 1, Hh - 1), outline=0)
    n = len(tiles); rows = (n + 3) // 4
    S = Image.new('L', (W * 4, Hh * rows + Hh), 255)
    for i, t in enumerate(tiles): S.paste(t, ((i % 4) * W, (i // 4) * Hh))
    S.paste(A, (0, Hh * rows))
    S.save(os.path.join(out, 'tie_' + spec.replace(':', '_') + '.png'))


def main():
    out = sys.argv[1]
    if sys.argv[2] == '--all':
        specs = sorted(f[:-5].replace('_', ':', 1) for f in os.listdir(out)
                       if f.endswith('.json') and not f.startswith(('rep_', 'tie_', 'summary', 'compare', 'static', 'src98')))
        # (case files are <thrower>_<action>[_scene[_slot]].json: names with '_' are restored from the case list)
        cases = json.load(open(os.path.join(out, 'cases.json'))) if os.path.exists(os.path.join(out, 'cases.json')) else specs
    else: cases = sys.argv[2:]
    allr = {}
    for c in cases:
        try: allr[c] = tie(out, c)
        except FileNotFoundError: continue
        s = allr[c]
        print(f"{c:22s} {s['victim']:6s} held {s['held_frames']:3d} gapmax {s['gap_max']!s:5s} bad {s['gap_bad']:3d} excess {s['gap_excess']:3d} ({s['excess_max']!s:5s}, src {s['src_gap_max']!s:5s}) "
              f"jump {s['jump_origin']:5.1f}/{s['jump_centre']:5.1f} top {s['arc_top']:6.1f} land {s['land_dx']!s:6s} "
              f"below {s['below_floor']:2d} off {s['offscreen']:2d} acc {s['accel_changes']:2d} end {s['end_v']}/{s['end_t']}", flush=True)
    p = os.path.join(out, 'tie_summary.json'); old = json.load(open(p)) if os.path.exists(p) else {}
    old.update(allr); json.dump(old, open(p, 'w'), indent=1)


if __name__ == '__main__':
    main()
