#!/usr/bin/env python3
"""Billy Lee's HUD face for the brawler (make_hud.py takes /data/neogeo_dict/portraits/<game>_<bank>_square.png, 28x28):
Double Dragon's fight HUD has names only (no face), so the face is his square on the player select grid (boot.py's
boot, frame 880: P1's cursor on Billy; the emulator's screenshot, 304 px wide: x - 8 = the grid cell at screen x 128-157,
y 112-139, inside its white border). The transformed form has no face of its own in the game: the same square.
    python3 portraits_dd.py      -> doubledr_billy_square.png, doubledr_billy_super_square.png"""
import os
from PIL import Image
import boot
OUT = '/data/neogeo_dict/portraits'

if __name__ == '__main__':
    boot.boot(900, snaps='880')
    im = Image.open('/data/tmp/dd95/snap_880.ppm').convert('RGBA')
    face = im.crop((122, 112, 150, 140))
    for bank in ('billy', 'billy_super'): face.save(os.path.join(OUT, f'doubledr_{bank}_square.png'))
