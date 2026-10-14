#!/usr/bin/env python3
"""Garou HUD faces for the brawler (make_hud.portrait: <game>_<name>_square.png, 28x28 as is), cut from the fighter's
own idle frame (ROM render mirrored to face left, colour set A), the way portraits_lb2.py does Moriya's: the 28 x 28
window on the head, the background of the brawler's other faces behind it.
    python3 portraits_garou.py [rock]   -> /data/neogeo_dict/portraits/garou_<name>_square.png"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from PIL import Image
import garou as G, export_garou as X

OUT = '/data/neogeo_dict/portraits'
FACE_BG = (32, 48, 96)
HEAD = {'rock': (0, 1, 0)}                       # name -> (idle step, px below the top row, px left of the hair's middle)

def square(name):
    ch = X.CAST[name]; k, dy, dx = HEAD[name]
    im = G.render_step(ch, G.step(ch, 0, k), np.zeros((256, 256), np.uint16), 128, 220, hflip=1)
    ys, xs = np.nonzero(im)
    top = ys.min(); row = xs[ys < top + 20]
    cx = int((row.min() + row.max()) // 2)
    x0, y0 = cx - 14 + dx, top + dy - 2
    base = X.PAL_BASE + ch * X.PAL_CHAR
    rgb = np.zeros((28, 28, 3), np.uint8); rgb[:] = FACE_BG
    for y in range(28):
        for x in range(28):
            v = int(im[y0 + y, x0 + x])
            if v: rgb[y, x] = G.color(G.u16(base + 32 * ((v >> 4) - X.OWN_SLOTS[0]) + 2 * (v & 15)))
    p = os.path.join(OUT, f'garou_{name}_square.png')
    Image.fromarray(rgb).save(p); return p

if __name__ == '__main__':
    for n in sys.argv[1:] or ['rock']: print(square(n))
