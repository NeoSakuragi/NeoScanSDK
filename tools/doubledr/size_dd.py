#!/usr/bin/env python3
"""Sprite sizes of every Double Dragon fighter at full size (zoom 0, the camera's close range) vs the brawler:
idle height / width (opaque pixels), the sprites (16-px columns) of the idle frame, the most columns any scanline
of any frame of any animation needs (the per-line cost), and the C ROM tiles the fighter's definitions use.
    python3 size_dd.py -> /data/neogeo_dict/doubledr/sizes.json"""
import json, numpy as np, dd
from fighters_dd import CHARS

def def_lines(w):
    d = dd.sdef(w)
    if not d: return {}, 0
    per = {}
    for c in d['cols']:
        rows = [r for r, (code, at) in enumerate(c['tiles']) if not ((code == 0xFF) and not (at >> 4 & 15))]
        if not rows: continue
        for y in range(c['yo'] + 16 * min(rows), c['yo'] + 16 * (max(rows) + 1)): per[y] = per.get(y, 0) + 1
    return per, len(d['cols'])

def opaque_box(w):
    pw = [0x7FFF] * 4096
    img = dd.draw_def(w, pw, palette=1, size=(400, 400), origin=(200, 330))
    ys, xs = np.nonzero(img[..., 3])
    return (int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)) if len(ys) else (0, 0)

out = {}
for ch in sorted(CHARS):
    defs = set(); peak = 0; peak_at = None
    for n in range(dd.anim_count(ch)):
        try: h, st = dd.steps(ch, n)
        except Exception: continue
        for s in st:
            if s['def_'] in defs: continue
            defs.add(s['def_']); per, nc = def_lines(s['def_'])
            m = max(per.values()) if per else 0
            if m > peak: peak, peak_at = m, (n, hex(s['def_']))
    idle = dd.steps(ch, 0)[1][0]['def_']
    tiles = set()
    for w in defs:
        d = dd.sdef(w)
        for c in d['cols'] if d else []:
            for code, at in c['tiles']: tiles.add(code | (at >> 4 & 15) << 16)
    hgt, wid = opaque_box(idle)
    out[CHARS[ch]] = dict(ch=ch, idle_height=hgt, idle_width=wid, idle_columns=len(dd.sdef(idle)['cols']),
                          peak_line_sprites=peak, peak_at=peak_at, frames=len(defs), tiles=len(tiles))
    print(CHARS[ch], out[CHARS[ch]])
json.dump(out, open('/data/neogeo_dict/doubledr/sizes.json', 'w'), indent=1)
