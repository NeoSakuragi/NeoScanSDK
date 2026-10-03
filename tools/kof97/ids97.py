#!/usr/bin/env python3
"""KOF97: contact sheet of every character table's idle frame (slot of game state 0), to name the ids.
KOF98's layout (rom96.GAMES['kof97']). Grey until the palettes are found.
    python3 ids97.py OUT.png [palette-fn]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import numpy as np
from PIL import Image, ImageDraw
import rom96
from neogeo.sprite_decode import decode_tile

GREY = [(0, 0, 0, 0)] + [(16 * i, 16 * i, 16 * i, 255) for i in range(1, 16)]

def render(m, crom, cid, slot=0, step=0, pal_of=None):
    steps, mode = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
    fi = steps[step][1]
    W, H = 260, 240; ox, oy = 130, 220
    img = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    for p in rom96.frame_parts(m, cid, fi):
        sd = rom96.sdef(m, cid, p['sdef'])
        cols = sd['cols']
        if not cols: continue
        w, h = len(cols) * 16, len(cols[0]) * 16
        a = np.zeros((h, w), dtype=np.uint8)
        for c, col in enumerate(cols):
            for r, t in enumerate(col):
                if t is not None: a[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = decode_tile(crom, t)
        if p['hflip']: a = a[:, ::-1]
        if p['vflip']: a = a[::-1, :]
        x = ox - p['dx'] - w if p['hflip'] else ox + p['dx']
        y = oy - p['dy'] - h if p['vflip'] else oy + p['dy']
        pal = pal_of(cid, sd['pal']) if pal_of else GREY
        img.alpha_composite(Image.fromarray(np.array(pal, dtype=np.uint8)[a], 'RGBA'), (max(0, min(W - w, x)), max(0, min(H - h, y))))
    return img

def count_ids(m):
    n = 0
    while True:
        try:
            t = m.u32(m.g['anims'] + n * 4)
            if not 0x200000 <= t < 0x300000: break
            rom96.parse_anim(m, rom96.anim_addr(m, n, 0)); n += 1
        except Exception: break
    return n

if __name__ == '__main__':
    prom, crom = rom96.load(rom96.GAMES['kof97']['neo']); m = rom96.Mem(prom, 'kof97')
    n = count_ids(m); print(n, 'ids')
    cols = 8; sheet = Image.new('RGB', (cols * 164, ((n + cols - 1) // cols) * 154), 'white'); d = ImageDraw.Draw(sheet)
    for cid in range(n):
        try: im = render(m, crom, cid, rom96.state_slot(m, cid, 0)).convert('RGB').resize((160, 148))
        except Exception as e: im = Image.new('RGB', (160, 148), 'white'); ImageDraw.Draw(im).text((4, 70), str(e)[:28], fill='black')
        sheet.paste(im, ((cid % cols) * 164, (cid // cols) * 154)); d.text(((cid % cols) * 164 + 3, (cid // cols) * 154 + 2), f'id {cid}', fill='black')
    sheet.save(sys.argv[1])
