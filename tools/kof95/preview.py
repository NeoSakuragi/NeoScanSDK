#!/usr/bin/env python3
"""Render animations from the EXPORTED data only (kof95_export.json + kof95_c1/c2.bin), exactly as the engine will:
each part = columns of 16x16 tiles placed at (origin.x + dx, origin.y + dy); a flipped part is mirrored around the origin
(hflip: x = origin.x - dx - width, vflip: y = origin.y - dy - height).
    python3 preview.py EXPORTDIR terry [move ...] -> EXPORTDIR/preview_terry.png"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
import rom  # noqa: F401  (puts the shared neosdk library on the path)
from neogeo.sprite_decode import decode_tile, decode_color

def load(d):
    ex = json.load(open(os.path.join(d, 'kof95_export.json')))
    c1, c2 = open(os.path.join(d, 'kof95_c1.bin'), 'rb').read(), open(os.path.join(d, 'kof95_c2.bin'), 'rb').read()
    region = bytearray(len(c1) * 2); region[0::2] = c1; region[1::2] = c2
    return ex, bytes(region)

def draw_frame(canvas, region, pal, frame, ox, oy, facing_left=False):
    for p in frame['parts']:
        cols = p['tiles']; w, h = len(cols) * 16, len(cols[0]) * 16
        img = np.zeros((h, w), dtype=np.uint8)
        for c, col in enumerate(cols):
            for r, t in enumerate(col):
                if t: img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = decode_tile(region, t)
        # a flipped part is mirrored around the character origin (offset and image), like turning around
        x0 = ox - p['dx'] - w if p['hflip'] else ox + p['dx']
        y0 = oy - p['dy'] - h if p['vflip'] else oy + p['dy']
        if p['hflip']: img = img[:, ::-1]
        if p['vflip']: img = img[::-1, :]
        if facing_left: img = img[:, ::-1]; x0 = 2 * ox - x0 - w
        for y in range(h):
            for x in range(w):
                ci = img[y, x]
                if ci and 0 <= x0 + x < canvas.width and 0 <= y0 + y < canvas.height:
                    canvas.putpixel((x0 + x, y0 + y), decode_color(pal[ci]))

if __name__ == '__main__':
    d, name = sys.argv[1], sys.argv[2]; ex, region = load(d); ch = ex['characters'][name]
    moves = sys.argv[3:] or list(ch['anims'])
    CW, CH = 160, 170
    W = 110 + CW * max(len(ch['anims'][m]['steps']) for m in moves)
    sheet = Image.new('RGB', (W, CH * len(moves)), (255, 255, 255)); dr = ImageDraw.Draw(sheet)
    for ri, m in enumerate(moves):
        a = ch['anims'][m]; y0 = ri * CH
        dr.line([(0, y0), (W, y0)], fill=(0, 0, 0)); dr.text((4, y0 + 4), f'{m}\n{a["mode"]}', fill=(0, 0, 0))
        for si, s in enumerate(a['steps']):
            ox, oy = 110 + si * CW + CW // 2, y0 + CH - 20
            draw_frame(sheet, region, ch['palette'], ch['frames'][s['frame']], ox, oy)
            dr.line([(ox - 5, oy), (ox + 5, oy)], fill=(255, 0, 0)); dr.line([(ox, oy - 5), (ox, oy + 5)], fill=(255, 0, 0))
            dr.text((110 + si * CW + 4, y0 + 4), f'{s["ticks"]}t f{s["frame"]}', fill=(0, 0, 160))
            for k, (bx, by, bw, bh) in s.get('boxes', {}).items():   # same axis as sprite dx; the ROM's sprites face left
                bx, by = (bx ^ 0x80) - 0x80, (by ^ 0x80) - 0x80
                atk = int(k, 16) >> 4 == 1
                dr.rectangle([ox + bx - bw, oy + by - bh, ox + bx + bw, oy + by + bh], outline=(220, 0, 0) if atk else (0, 0, 0), width=2 if atk else 1)
    out = os.path.join(d, f'preview_{name}.png'); sheet.save(out); print(out, sheet.size)
