#!/usr/bin/env python3
"""The Last Blade 2 HUD faces for the brawler (make_hud.portrait: <game>_<name>_square.png, 28x28 as is): LB2's fight HUD
has no face (names only) and its select grid's squares are 40 x 16 strips, so the face is cut from the fighter's own idle
frame (ROM render, colour set A: the way SS2's Kuroko got his, portraits_ss2.py): the 28 x 28 window on the head (the
topmost rows of the body layer, centred on them), the background of the brawler's other faces behind it.
    python3 portraits_lb2.py [moriya]   -> /data/neogeo_dict/portraits/lastbld2_<name>_square.png"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image
import lb2 as L, export_lb2 as X

OUT = '/data/neogeo_dict/portraits'
FACE_BG = (32, 48, 96)                            # (make_hud.FACE_BG's blue field behind the face)
HEAD = {'moriya': (0, 2, -5)}                     # name -> (frame id, px below the top row, px left of the hair's middle)

def square(name):
    ch = X.CAST[name]; fid, dy, dx = HEAD[name]
    im = L.render_frame(ch, fid, np.zeros((256, 256), np.uint16), 128, 200)
    ys, xs = np.nonzero(im)
    top = ys.min(); row = xs[ys < top + 20]
    cx = int((row.min() + row.max()) // 2)
    x0, y0 = cx - 14 + dx, top + dy - 4
    rgb = np.zeros((28, 28, 3), np.uint8); rgb[:] = FACE_BG
    for y in range(28):
        for x in range(28):
            v = int(im[y0 + y, x0 + x])
            if v: rgb[y, x] = L.color(L.u16(0xA9000 + 32 * (X.PAL0[ch] + (v >> 4)) + 2 * (v & 15)))
    p = os.path.join(OUT, f'lastbld2_{name}_square.png')
    Image.fromarray(rgb).save(p); return p

if __name__ == '__main__':
    for n in sys.argv[1:] or ['moriya']: print(square(n))
