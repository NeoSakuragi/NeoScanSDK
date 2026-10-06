#!/usr/bin/env python3
"""Haohmaru's and Genjuro's HUD faces for the brawler (make_hud.py takes /data/neogeo_dict/portraits/<game>_<bank>_square.png,
28x28): Samurai Shodown II's fight HUD has names only, so the face is the fighter's square on the player select grid
(boot.py's boot, frame 830 of the study: /data/tmp/samsho2/sel2/snap_830.ppm, our emulator's screenshot, 304 px wide;
re-made with --boot), the 28x28 inside its white border.
    python3 portraits_ss2.py [--boot]      -> samsho2_haohmaru_square.png, samsho2_genjuro_square.png"""
import os, sys
from PIL import Image
OUT = '/data/neogeo_dict/portraits'
SNAP = '/data/tmp/samsho2/sel2/snap_830.ppm'
CELLS = {'haohmaru': (103, 170), 'genjuro': (155, 135)}   # the face's top left on the grid (bottom row 3rd, top row 5th)

if __name__ == '__main__':
    if '--boot' in sys.argv:
        import boot
        boot.boot(840, snaps='830', out='/data/tmp/samsho2/sel2/b.txt')
    im = Image.open(SNAP).convert('RGBA')
    for n, (x, y) in CELLS.items():
        im.crop((x, y, x + 28, y + 28)).save(os.path.join(OUT, f'samsho2_{n}_square.png'))
        print(n, os.path.join(OUT, f'samsho2_{n}_square.png'))
