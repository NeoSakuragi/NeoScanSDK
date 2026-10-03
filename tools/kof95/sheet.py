"""Contact sheet: one row per state, every frame with its duration and the origin cross. python3 sheet.py terry 0 18"""
import sys, json
import numpy as np
from PIL import Image, ImageDraw
import rom
from neogeo.sprite_decode import r32, read_palette
from neogeo.animation import parse_animation, follow_fragment_chain
from neogeo.renderer import render_frame
name, s0, s1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
cid = rom.CHARS[name]
prom, crom = rom.load()
cfg = json.load(open(rom.os.path.join(rom.HERE, '..', 'neosdk', 'games', 'kof95.json')))
pal = cfg['characters'][cid]['palettes']
body = read_palette(prom, int(pal['v0_body'], 16)); acc = read_palette(prom, int(pal['v1_acc'], 16))
st = r32(prom, 0x080000 + cid * 4); sd = r32(prom, 0x080080 + cid * 4)
CW, CH, S = 150, 150, 1
rows = []
for s in range(s0, s1 + 1):
    fr = parse_animation(prom, r32(prom, st + s * 4))
    rows.append((s, fr))
W = 60 + CW * max(len(f) for _, f in rows); H = CH * len(rows)
sheet = Image.new('RGB', (W, H), (255, 255, 255)); dr = ImageDraw.Draw(sheet)
for ri, (s, fr) in enumerate(rows):
    y0 = ri * CH; dr.line([(0, y0), (W, y0)], fill=(0, 0, 0)); dr.text((4, y0 + 4), f's{s}', fill=(0, 0, 0))
    for fi, (dur, frag, flags) in enumerate(fr):
        parts = follow_fragment_chain(prom, frag, sd)
        x0 = 60 + fi * CW
        if parts:
            r = render_frame(crom, parts, body, acc, scale=S, return_origin=True)
            if r and r[0] is not None:
                img, ox, oy = r; im = Image.fromarray(img, 'RGBA')
                px, py = x0 + CW // 2 - ox, y0 + CH - 20 - oy
                sheet.paste(im, (px, py), im)
                cx, cy = x0 + CW // 2, y0 + CH - 20
                dr.line([(cx - 6, cy), (cx + 6, cy)], fill=(255, 0, 0)); dr.line([(cx, cy - 6), (cx, cy + 6)], fill=(255, 0, 0))
        dr.text((x0 + 4, y0 + 4), f'{dur}t', fill=(0, 0, 160))
sheet.save(f'out_{name}_{s0}_{s1}.png'); print('saved', sheet.size)
