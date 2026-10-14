#!/usr/bin/env python3
"""Contact sheet of every animation of a Final Fight fighter as the ROM draws it (ff.py): one row per animation
(address, frames with their ticks), boxes outlined (body grey, attack red).

    python3 sheet_ff.py NAME OUT.png [ANIM_HEX ...]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ff
from PIL import Image, ImageDraw

def render(fa, scale=1, boxes=True, mirror=False):
    """a frame record -> RGBA image 192 x 176, feet at (96, 150)"""
    f = ff.frame(fa); im = Image.new('RGBA', (192, 176), (255, 255, 255, 255)); px = im.load()
    for code, at, x, y in f['tiles']:
        pal = [ff.cps_rgb(w) for w in ff.palette(at & 31)]
        t = ff.tile_pixels(code); hf = at >> 5 & 1; vf = at >> 6 & 1
        for yy in range(16):
            for xx in range(16):
                p = t[15 - yy if vf else yy][15 - xx if hf else xx]
                if p == 15: continue
                X, Y = 96 + x + xx, 150 + y + yy
                if mirror: X = 191 - X
                if 0 <= X < 192 and 0 <= Y < 176: px[X, Y] = pal[p] + (255,)
    if boxes:
        d = ImageDraw.Draw(im)
        for kind, b in ff.boxes(f).items():
            cx, cy, hw, hh = b
            d.rectangle([96 + cx - hw, 150 - cy - hh, 96 + cx + hw, 150 - cy + hh], outline=(160, 160, 160) if kind == 'body' else (220, 0, 0))
    return im

def main():
    name, out = sys.argv[1], sys.argv[2]
    heads = [int(a, 16) for a in sys.argv[3:]] or ff.region_anims(name)
    rows = []
    for h in heads:
        ents, lp = ff.anim(h)
        rows.append((h, ents, lp))
    W = 120; cols = max(len(r[1]) for r in rows)
    sheet = Image.new('RGB', (110 + cols * W, len(rows) * 150), 'white'); d = ImageDraw.Draw(sheet)
    for i, (h, ents, lp) in enumerate(rows):
        d.text((4, i * 150 + 60), f'{h:05X}\n{len(ents)} fr' + (f'\nloop {lp}' if lp is not None else ''), fill='black')
        for k, (e, fa, t, at) in enumerate(ents):
            im = render(fa).crop((36, 20, 156, 166))
            sheet.paste(im, (110 + k * W, i * 150))
            d.text((112 + k * W, i * 150 + 2), f'{t}{"*" if at else ""} {fa:05X}', fill='blue')
    sheet.save(out)

if __name__ == '__main__': main()
