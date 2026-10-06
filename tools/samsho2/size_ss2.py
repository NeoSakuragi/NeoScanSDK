#!/usr/bin/env python3
"""Sizes vs the brawler: per fighter the animation count, steps, distinct sprite definitions ('frames') and C-ROM tiles,
idle height x width in px (anim 0 / Tam-Tam-less roster; ROM render), idle sprites per line and the peak sprites per line
over every step (each layer is one chain of `cols` sprites over its rows). -> /data/neogeo_dict/samsho2/sizes.json"""
import json, numpy as np
import ss2

def step_lines(st):
    lines = {}
    for w in st['layers']:
        sd = ss2.sprite_def(w & 0x7FFF); xo, yo = ss2.place(w & 0x7FFF)
        if sd['raw'] == 0: continue
        top = -yo
        for y in range(top, top + 16 * sd['rows']): lines[y] = lines.get(y, 0) + sd['cols']
    return max(lines.values()) if lines else 0

def fighter(c):
    n = ss2.n_anims(c); steps = 0; defs = set(); peak = (0, None)
    for a in range(n):
        try: anim = ss2.parse_anim(c, a)
        except Exception: continue
        for st in anim:
            steps += 1
            for w in st['layers']: defs.add(w & 0x7FFF)
            k = step_lines(st)
            if k > peak[0]: peak = (k, a)
    tiles = set()
    for d in defs:
        try: _, cells = ss2.sprite_cells(d)
        except Exception: continue
        for col in cells:
            for cell in col:
                if cell: tiles.add(cell[0] | (cell[1] >> 4 & 15) << 16)
    tiles.discard(0)
    idle = 4 if c == 10 else 0
    st = ss2.parse_anim(c, idle)[0]
    img = np.zeros((400, 400), np.uint16); ss2.render_step(img, st, 200, 380, 0, (0, 0, 0, 0))
    ys, xs = np.nonzero(img)
    return dict(char=c, name=ss2.NAMES[c] if c < 18 else str(c), anims=n, steps=steps, frames=len(defs), tiles=len(tiles),
                idle_h=int(ys.max() - ys.min() + 1), idle_w=int(xs.max() - xs.min() + 1), idle_layers=len(st['layers']),
                idle_sprites_line=step_lines(st), peak_sprites_line=peak[0], peak_anim=peak[1])

if __name__ == '__main__':
    out = [fighter(c) for c in range(19)]
    json.dump(out, open('/data/neogeo_dict/samsho2/sizes.json', 'w'), indent=1)
    for r in out: print(r)
