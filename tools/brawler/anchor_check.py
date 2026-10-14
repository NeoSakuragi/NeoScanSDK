#!/usr/bin/env python3
"""The posture-anchor fallback measured on KOF's ground truth (T1, docs/brawler_throws_review.md; export_bm.VICTIM_ANCHORS):
every KOF98 / KOF96 thrower x victim pair of the build that has the victim's OWN list (export96 victims_all: KOF's per-
victim offsets = what the source really draws), per script row: where the brawler would put the victim's posture frame
with (a) the mirror rows as they are (no anchor), (b) the pixel-centre anchor (the victim frame's centre where the source
victim frame's centre was: fighter.c vrow, vanc), each against the truth. Centres computed two ways: 'old' = export_bm's
frame_centre before T1 (a flipped part kept in place, only its tiles flipped), 'draw' = as draw.s places it (a flipped
part mirrored about the origin: x0 = ox - dx - w).

    python3 anchor_check.py [BUILD_DIR]      -> stdout: mean / median / p90 |dx| + |dy| per method, per thrower"""
import json, os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import head_point as HP
B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'build')
VP = json.load(open(os.path.join(HERE, '..', 'kof96', 'victim_poses98.json'))) if os.path.exists(os.path.join(HERE, '..', 'kof96', 'victim_poses98.json')) else None


def centre(ld, f, mode):
    ch, reg = ld
    sx = sy = n = 0
    for p in ch['frames'][f]['parts']:
        rows = len(p['tiles'][0])
        for c_, col in enumerate(p['tiles']):
            for r_, t_ in enumerate(col):
                if not t_: continue
                pen = HP.tile(reg, t_)
                if mode == 'old':
                    top = -p['dy'] - rows * 16 if p['vflip'] else p['dy']; rr = r_
                    if p['hflip']: pen = pen[:, ::-1]
                    if p['vflip']: pen = pen[::-1]; rr = rows - 1 - r_
                    ys, xs = np.nonzero(pen); xs = xs + p['dx'] + 16 * c_; ys = ys + top + 16 * rr
                else:
                    ys, xs = np.nonzero(pen); xs = xs + p['dx'] + 16 * c_; ys = ys + p['dy'] + 16 * r_
                    if p['hflip']: xs = -xs - 1
                    if p['vflip']: ys = -ys - 1
                sx += float(xs.sum()); sy += float(ys.sum()); n += len(xs)
    return (sx / n, sy / n) if n else None


def main():
    import export_bm as E
    h = open(os.path.join(B, 'bm_chars.h')).read()
    pkeys = re.search(r'enum \{ VP_COUNT = \d+ \};\s*/\* victim postures: (.*?) \*/', h).group(1).split()
    c = open(os.path.join(B, 'bm_chars.c')).read()
    vposes = {m.group(1): [int(v, 0) for v in re.findall(r'0x[0-9A-Fa-f]+|\d+', m.group(2))]
              for m in re.finditer(r'static const uint16_t (\w+)_vposes\[VP_COUNT \+ 1\] = \{(.*?)\};', c, re.S)}
    roster = json.load(open(os.path.join(B, 'roster.json')))
    bank = {r['name']: r['bank'] for r in roster}
    LD, ex = {}, {}
    def ld(n):
        if n not in LD:
            g, nm = bank[n].split(':'); LD[n] = HP.load(os.path.join(B, f'tmp_{g}_{nm}'), nm)
        return LD[n]
    err = {k: [] for k in ('mirror', 'anchor_old', 'anchor_draw')}
    per = {}
    for r in roster:
        n = r['name']; g, nm = bank[n].split(':')
        if g not in ('kof98', 'kof96'): continue
        ch = ld(n)[0]
        for t, th in (ch.get('throws') or {}).items():
            if not th.get('victims_all') or nm not in th['victims']: continue
            mir = th['victims'][nm]
            for vn, rows in th['victims_all'].items():
                vr = next((x['name'] for x in roster if x['bank'] == f'{g}:{vn}'), None)
                if not vr or vr == n or vr not in vposes: continue
                for i, row in enumerate(rows):
                    vx, vy, same, key = row[1], row[2], row[3], row[5]
                    m = mir[min(i, len(mir) - 1)]
                    vf_m, vx_m, vy_m = m[0], m[1], m[2]
                    post = E.vocab(g, key)
                    if post not in pkeys or vf_m is None or vf_m < 0: continue
                    fv = vposes[vr][pkeys.index(post)]
                    if fv == 0xFFFF: continue
                    s = 1 if same & 1 else -1
                    e = abs(vx_m - vx) + abs(vy_m - vy); err['mirror'].append(e)
                    for mode in ('old', 'draw'):
                        a, mm = centre(ld(vr), fv, mode), centre(ld(n), vf_m, mode)
                        if not a or not mm: continue
                        px = vx_m + (s * (a[0] - mm[0]) if True else 0); py = vy_m + (a[1] - mm[1])
                        err['anchor_' + mode].append(abs(round(px) - vx) + abs(round(py) - vy))
                    per.setdefault(n, {k: [] for k in err})
                    for k in err:
                        if err[k]: per[n][k].append(err[k][-1])
    for k, v in err.items():
        v = np.array(v); print(f'{k:12s} rows {len(v):6d} mean {v.mean():6.1f} median {np.median(v):5.1f} p90 {np.percentile(v, 90):6.1f} max {v.max():6.1f}')
    for n, d in per.items():
        print(n, {k: round(float(np.mean(v)), 1) for k, v in d.items() if v})


if __name__ == '__main__':
    main()
