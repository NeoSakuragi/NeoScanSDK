#!/usr/bin/env python3
"""anim_sheet.py OUT.png ANIM [ANIM...] [--zoom Z] [--boxes]: every step of Kim's animations (hex numbers), one row
per animation, colour A, the step's boxes in force drawn (hurt grey, attack black) with --boxes"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, kz
from PIL import Image, ImageDraw
def rompal(n): return [kz.u16(0x70000 + 32 * n + 2 * i) for i in range(16)]
PAL = [0] * 4096
PAL[16 * 16:17 * 16] = rompal(0x88); PAL[17 * 16:18 * 16] = rompal(0x89); PAL[18 * 16:19 * 16] = rompal(0x8A)

def cell(a, z, boxes, W=200, H=260):
    img = np.zeros((H, W), np.uint16)
    kz.render_step_zoom(img, a, W // 2, H - 20, z)
    rgb = kz.colorize(img, PAL); rgb[img == 0] = 255
    im = Image.fromarray(rgb); d = ImageDraw.Draw(im)
    s = (z + 1) / 256
    for b in boxes or []:
        x0, x1, y0, y1 = W // 2 + b[2] * 4 * s, W // 2 + b[3] * 4 * s, H - 20 - b[5] * 4 * s, H - 20 - b[4] * 4 * s
        d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], outline=(0, 0, 0) if b[0] >= 0x10 else (150, 150, 150))
    d.line([W // 2 - 4, H - 20, W // 2 + 4, H - 20], fill=(255, 0, 0))
    return im

if __name__ == '__main__':
    a = sys.argv[1:]; out = a.pop(0)
    z = 0xFF; boxes = '--boxes' in a
    if '--zoom' in a: i = a.index('--zoom'); z = int(a[i + 1], 0); del a[i:i + 2]
    a = [x for x in a if x != '--boxes']
    rows = []
    for n in a:
        st = kz.parse_anim(0x5000 | int(n, 16)); cur = []
        cells = []
        for s in st:
            if s['boxes'] is not None: cur = s['boxes']
            elif not s['trailer'] & 0x10 and not s['nboxes']: cur = []
            im = cell(s['addr'], z, cur if boxes else None)
            ImageDraw.Draw(im).text((4, 4), f"{n} s{len(cells)} t{s['ticks']}", fill=(0, 0, 0))
            cells.append(im)
        rows.append(cells)
    W, H = 200, 260; nc = max(len(r) for r in rows)
    sheet = Image.new('RGB', (W * min(nc, 12), H * sum((len(r) + 11) // 12 for r in rows)), 'white')
    y = 0
    for r in rows:
        for i, im in enumerate(r): sheet.paste(im, ((i % 12) * W, y + (i // 12) * H))
        y += H * ((len(r) + 11) // 12)
    sheet.save(out)
