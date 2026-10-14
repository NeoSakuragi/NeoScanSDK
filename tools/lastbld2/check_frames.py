#!/usr/bin/env python3
"""Every exported frame of a fighter vs the ROM render (lb2.render_frame: the decoder that equals the game's VRAM, README
"Proof"): colour per pixel, colour set A. -> frames, frames identical, and a contact sheet of the first differing ones.
    python3 check_frames.py [EXPORT_DIR] [name]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'samsho2')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import numpy as np
import lb2 as L
from pal_pack import tile_pens

def export_render(ex, ch, fr, tiles, sets):
    img = {}
    for pt in fr['parts']:
        for ci, col in enumerate(pt['tiles']):
            for ri, t in enumerate(col):
                if not t: continue
                pens = tile_pens(tiles[t - ex['tile_base']])
                for r in range(16):
                    for c in range(16):
                        q = pens[(1 if c < 8 else 0) * 128 + r * 8 + c % 8]
                        if q: img[(pt['dx'] + 16 * ci + c, pt['dy'] + 16 * ri + r)] = sets[0][pt['pal']][q]
    return img

def rom_render(cid, fid, pal0):
    im = L.render_frame(cid, fid, np.zeros((512, 512), np.uint16), 256, 300)
    ys, xs = np.nonzero(im); out = {}
    for y, x in zip(ys, xs):
        v = int(im[y, x]); p, q = v >> 4, v & 15
        base = pal0 if cid < 24 else 6177           # (char 24, the common effects: word 4 = byte 0 + 6177)
        out[(int(x) - 256, int(y) - 300)] = L.u16(0xA9000 + 32 * (base + p) + 2 * q)
    return out

def main(d='/data/tmp/lastbld2/exp', name='moriya'):
    ex = json.load(open(os.path.join(d, 'kof95_export.json'))); ch = ex['characters'][name]
    c1 = open(os.path.join(d, 'kof95_c1.bin'), 'rb').read(); c2 = open(os.path.join(d, 'kof95_c2.bin'), 'rb').read()
    raw = bytearray(len(c1) * 2); raw[0::2] = c1; raw[1::2] = c2
    tiles = [bytes(raw[128 * k:128 * k + 128]) for k in range(ex['tile_base'], len(raw) // 128)]
    import export_lb2 as X
    same = 0; bad = []
    for i, fr in enumerate(ch['frames']):
        fid = fr['lb2']['frame']; cid = fr['lb2'].get('char', ch['id'])
        a = export_render(ex, ch, fr, tiles, ch['block_palettes']); b = rom_render(cid, fid, X.PAL0[ch['id']])
        if fr['lb2'].get('lnk'):                    # (T4: a normal's frame with its OBJ LNK trail, export_lb2.frame_lnk:
            lf, lx, ly = fr['lb2']['lnk']           # the trail's frame at (x, y), drawn over him)
            b.update({(x + lx, y + ly): v for (x, y), v in rom_render(cid, lf, X.PAL0[ch['id']]).items()})
        if a == b: same += 1
        else: bad.append((i, fid, len(a), len(b), sum(1 for k in a if b.get(k) != a[k])))
    print(name, len(ch['frames']), 'frames', same, 'identical', bad[:10])
    return len(ch['frames']), same

if __name__ == '__main__':
    main(*sys.argv[1:])
