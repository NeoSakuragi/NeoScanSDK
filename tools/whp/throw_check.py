#!/usr/bin/env python3
"""moves_whp.throw_model vs WHP (throw_capture.py's capture: Hanzou throws Fuuma, forward and back): the thrower
(anim, step, def, x, y) frame by frame, the held victim (x, y: command 16's placement), the flight after the release.

    python3 throw_check.py CAPTURE.json [OUT.json]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves_whp as M, handlers_whp as H

H.ROWS.setdefault('fuuma', 6); H.CHARS.setdefault('fuuma', 5)   # P2 of the vs. state (+$6004 = 7, base $900)

def check(cap):
    out = {}
    for k, rel in (('fwd', 0xD1), ('back', 0xD3)):
        mod = M.throw_model('hanzo', rel, H.ROWS['fuuma'], H.CHARS['fuuma'], 'fuuma', turn=k == 'back')
        fr = cap[k]; s0 = next(i for i, f in enumerate(fr) if f[0]['anim'] == rel)
        x0 = fr[s0][0]['x']; bad_t, bad_held, flight = [], [], []
        n = 0
        for i, mf in enumerate(mod['frames']):
            if s0 + i >= len(fr): break
            p, v = fr[s0 + i]; n += 1
            a = mf['t']
            if a is not None:
                ok = (a['anim'], a['step'], a['defw']) == (p['anim'], p['step'], p['defw']) and abs(a['x'] - (p['x'] - x0)) < 1.01 and abs(a['y'] - p['y']) < 1.01
                if not ok: bad_t.append([i, [a['anim'], a['step'], a['defw'], round(a['x'], 2), round(a['y'], 2)], [p['anim'], p['step'], p['defw'], round(p['x'] - x0, 2), p['y']]])
            q = mf['v']; e = (round(q['x'] - (v['x'] - x0), 2), round(q['y'] - v['y'], 2))
            if q['phase'] == 'held':
                if abs(e[0]) > 1.01 or abs(e[1]) > 1.01: bad_held.append([i, e])
            else: flight.append(max(abs(e[0]), abs(e[1])))
        imp = [i for i, f in enumerate(mod['frames']) if f['impact']]
        drop = next((i for i in range(1, n) if fr[s0 + i][1]['life'] < fr[s0 + i - 1][1]['life']), None)
        out[k] = {'frames': n, 'thrower_bad': len(bad_t), 'thrower_first_bad': bad_t[:3], 'held_frames': mod['release'],
                  'held_bad': len(bad_held), 'held_first_bad': bad_held[:3], 'flight_frames': len(flight),
                  'flight_max_err_px': max(flight) if flight else None, 'impacts_model': imp, 'life_drop_frame': drop,
                  'release': mod['release'], 'land': mod['land'], 'down': mod['down'], 'end': mod['end']}
    return out

if __name__ == '__main__':
    res = check(json.load(open(sys.argv[1])))
    for k, v in res.items(): print(k, json.dumps(v))
    if len(sys.argv) > 2: json.dump(res, open(sys.argv[2], 'w'), indent=1)
