#!/usr/bin/env python3
"""The decoder vs the game's VRAM: a capture in our emulator (emu/neogeo_sdl --capture from vs_sdl.state: P1 Moriya's
normals and specials, P2 kept far), every frame P1's frame id (+$C6), place (+$80 - the camera $10E572, feet line 200 -
height) and facing (+$41) rendered from the ROM (lb2.render_frame) against the VRAM of the same frame, pen index
(palette x 16 + pen). -> frames, frames whose every ROM pixel equals the VRAM, pixels equal / total.
    python3 proof_lb2.py [OUT]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import lb2 as L, cap_lb2 as C

SEQ = ('4:-,3:a,40:-,3:b,50:-,3:c,40:-,3:D,3:Da,30:D,10:-,3:Lb,50:-,3:Rc,50:-,'
       '3:D,3:DR,3:R,3:a,60:-,3:R,3:D,3:DR,3:a,70:-,3:D,3:DL,3:L,3:b,70:-,3:L,3:DL,3:D,3:c,70:-,3:U,60:-')
CAM = 0x10E572

def run(out='/data/tmp/lastbld2/proof'):
    n = C.nframes(SEQ)
    pokes = None
    C.run(out, SEQ, f'{n}:-', pal_every=0)
    res = dict(frames=0, exact=0, exact_or_covered=0, px=0, eq=0, covered=0, skipped=0, stale=0)
    for f in range(2, n):
        r = C.ram(out, f)
        if r is None or not os.path.exists(f'{out}/vram{f}.bin'): continue
        o = C.obj(r, C.P1)
        v = L.words(f'{out}/vram{f}.bin')
        img, who, sk = L.vram_index(v)
        if sk: res['skipped'] += 1; continue                # the camera zoomed out (shrunk sprites): not compared
        cam = C.s16(r, CAM - 0x100000)
        rom = L.render_frame(1, o['frame'], np.zeros((224, 320), np.uint16), o['x'] - cam, 200 - o['h'], hflip=o['facing'],
                             palbase=o['pal'])
        m = rom > 0
        same = m & (img == rom)
        eq = int(same.sum()); tot = int(m.sum())
        if eq < tot // 2: res['stale'] += 1; continue        # the VRAM of a lag frame (the game's sprite upload skipped)
        mine = set(np.unique(who[same]).tolist())
        over = m & ~same & (who >= 0) & ~np.isin(who, list(mine))   # drawn over by another object's slots (P2, effects)
        res['frames'] += 1; res['px'] += tot; res['eq'] += eq; res['exact'] += eq == tot
        res['exact_or_covered'] += eq + int(over.sum()) == tot; res['covered'] += int(over.sum())
    print(res)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'))
    return res

if __name__ == '__main__':
    run(*sys.argv[1:])
