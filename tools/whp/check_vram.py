#!/usr/bin/env python3
"""whp.render_def (the ROM-only renderer the export is checked against) vs World Heroes Perfect's own rendering: every
frame of the capture recipes (capture_whp.RECIPES, our emulator with VRAMDUMP), P1's display object ($100000: def +$08,
position, flip) rendered from the ROM against P1's sprites in the VRAM dump (pen indices: palette * 16 + pen; P1's slots
= those with a cell in its palettes; the game writes its sprites to slots 100-199 and 200-299 on alternate frames, the
bank written this frame holds this frame's object [meas]; a lag frame breaks the alternation, so a frame is identical
when one of the two banks is; the position the game draws is the object's position of this frame or, in fast vertical
moves (the jumps), the previous frame's: the physics runs after the sprites are queued [meas]; likewise a def, a flip
(the spins of 623 / 214) or a hit flash can show one frame late: a frame counts as identical when the drawing matches
this frame's object, the previous one's, or one of them with the other's def).

    python3 check_vram.py [recipe ...]          (default: every recipe; prints the totals, a line per differing frame)"""
import os, sys, shutil, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import neo_whp as neo, whp, cap_whp as cap, capture_whp

def vram_img(v, pals, bank):
    lo, hi = 100 + 100 * bank, 200 + 100 * bank
    sl = {s for s, x, top, sh, s2 in neo.chains(v) if lo <= s < hi and sh and
          any(v[s * 64 + 2 * r] and v[s * 64 + 2 * r + 1] >> 8 in pals for r in range(min(sh, 32)))}
    img, sk = neo.vram_index(v, slots=sl)
    return np.where(np.isin(img >> 4, list(pals)), img, 0)

def render(o):
    """P1's display object as the game draws it: def, position, flip, its own offsets when +$21 bit 0 is clear, the
    palette override +$20 (the hit flash: every cell in that palette, $C23E)"""
    a = np.zeros((224, 320), np.uint16)
    whp.render_def(a, o['defw'], o['x'], o['y'], hflip=o['flags'] >> 7 & 1, pal_add=o['add'] >> 8,
                   offs=None if o['flags'] & 1 else o['offs'])
    if o['pal']: a = np.where(a > 0, (o['pal'] << 4) | (a & 15), 0).astype(np.uint16)
    return a

def check(name):
    p2x, seq, seq2 = capture_whp.RECIPES[name]
    n = max(cap.nframes(seq), cap.nframes(seq2) if seq2 else 0)
    pk = ';'.join(f'{f}:100102={p2x * 128 >> 8 & 255:02X},100103={p2x * 128 & 255:02X}' for f in range(n)) if p2x else None
    d = f'/data/tmp/whp/vram_{name}'
    rows = cap.run(seq, seq2, pokes=pk, keep=d, vram=True)
    res = []; prev = None
    for r in rows:
        o = cap.obj(r, 0)
        v = neo.vram_words(r['vram'])
        cands = [o] if prev is None else [o, prev, dict(prev, defw=o['defw']), dict(o, defw=prev['defw'])]
        best = None
        for c in cands:
            a = render(c)
            ps = {int(p) for p in np.unique(a[a > 0] >> 4)} or {0x10}
            diff = min(int((a != vram_img(v, ps, bank)).sum()) for bank in (0, 1))
            if best is None or diff < best: best = diff
        res.append((r['f'], o['defw'], best, int((render(o) > 0).sum())))
        prev = o
    shutil.rmtree(d, ignore_errors=True)
    return res

if __name__ == '__main__':
    names = sys.argv[1:] or list(capture_whp.RECIPES)
    tot = same = 0; defs = set()
    for nm in names:
        res = check(nm)
        ok = sum(1 for x in res if x[2] == 0); tot += len(res); same += ok; defs |= {x[1] for x in res}
        print(f'{nm}: {ok} / {len(res)} frames identical', '' if ok == len(res) else [(f, f'{w:04X}', d) for f, w, d, n in res if d][:4])
    print(f'total {same} / {tot} frames identical ({len(defs)} defs)')
