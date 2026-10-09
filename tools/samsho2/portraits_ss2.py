#!/usr/bin/env python3
"""Haohmaru's and Genjuro's HUD faces for the brawler (make_hud.py takes /data/neogeo_dict/portraits/<game>_<bank>_square.png,
28x28): Samurai Shodown II's fight HUD has names only, so the face is the fighter's square on the player select grid
(boot.py's boot, frame 830 of the study: /data/tmp/samsho2/sel2/snap_830.ppm, our emulator's screenshot, 304 px wide;
re-made with --boot), the 28x28 inside its white border. Kuroko (the hidden referee) has no square: his face is the top of
his idle frame (anim 0 step 0, colour set A) drawn by the decoder, 28x28 from the top of his hood.
    python3 portraits_ss2.py [--boot]      -> samsho2_haohmaru_square.png, samsho2_genjuro_square.png, samsho2_hanzo_square.png,
                                              samsho2_kuroko_square.png"""
import os, sys
from PIL import Image
OUT = '/data/neogeo_dict/portraits'
SNAP = '/data/tmp/samsho2/sel2/snap_830.ppm'
CELLS = {'haohmaru': (121, 135), 'genjuro': (155, 135),   # the face's top left on the grid (top row 4th, top row 5th,
         'hanzo': (189, 137)}                              # top row 6th: inside its white border at 187 / 135, TODO #193)
# Haohmaru was (103, 170) until 2026-10-09: the bottom row's 3rd square, Jubei Yagyu's (note 20261009-122317-5d29);
# his own square is the top row's 4th, inside its white border at 119 / 133, next to Genjuro's

if __name__ == '__main__':
    if '--boot' in sys.argv:
        import boot
        boot.boot(840, snaps='830', out='/data/tmp/samsho2/sel2/b.txt')
    im = Image.open(SNAP).convert('RGBA')
    for n, (x, y) in CELLS.items():
        im.crop((x, y, x + 28, y + 28)).save(os.path.join(OUT, f'samsho2_{n}_square.png'))
        print(n, os.path.join(OUT, f'samsho2_{n}_square.png'))
    import numpy as np, ss2
    img = np.zeros((256, 256), np.uint16); ss2.render_step(img, ss2.parse_anim(17, 0)[0], 128, 240, 0, (0, 0, 0, 0))
    ys, xs = np.nonzero(img); top = ys.min(); cx = int(np.median(xs[ys < top + 24]))
    rgb = Image.fromarray(ss2.colorize(img, ss2.fighter_palettes(17, 0), bg=(40, 40, 72)))
    rgb.crop((cx - 14, top - 2, cx + 14, top + 26)).save(os.path.join(OUT, 'samsho2_kuroko_square.png'))
    print('kuroko', os.path.join(OUT, 'samsho2_kuroko_square.png'))
