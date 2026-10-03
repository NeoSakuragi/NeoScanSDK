#!/usr/bin/env python3
"""KOF94: contact sheet of every character table's idle frame (slot 0), to name the ids. Reuses the KOF95 parsers
(same table layout: animations $080000 + id*4, sprite definitions $080080 + id*4); palettes at $71000 + id*$400.
    python3 ids94.py OUT.png"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95'))
import numpy as np
from PIL import Image, ImageDraw
import rom, export
from neogeo.sprite_decode import decode_tile, decode_color, r32, r16, rs16
from neogeo.animation import read_sprite_def

NEO = '/data/roms/kof94.neo'
PAL_ROM = 0x6F000            # palette n at $6F000 + n*32 (+2: colour 0 is a tag), loader $330E / $336A
PAL_TABLE = 0x33D2           # word per (id, colour set): first palette number; a fighter owns 14 palettes

def palette_base(prom, cid, cset=0): return r16(prom, PAL_TABLE + (cid * 2 + cset) * 2)

def sdef_columns(sdef):
    """columns of KOF tile codes (None = empty), top row first; KOF94: 16-bit masks, MSB = top row"""
    code, cols = sdef['base_tile'], []
    for bm in sdef['bitmasks'][:sdef['cols']]:
        col = []
        for t in range(sdef['tiles_per_col']):
            if (bm >> (15 - t)) & 1: col.append(code); code += 1
            else: col.append(None)
        cols.append(col)
    return cols

def frame_parts(prom, rec, sd):
    """KOF95's frame chain; KOF94's sprite definitions always use 16-bit column bitmasks (KOF95: 8-bit when rows <= 8)"""
    parts, pos = [], rec
    for _ in range(8):
        dx, dy, word = rs16(prom, pos), rs16(prom, pos + 2), r16(prom, pos + 4)
        sdef = read_sprite_def(prom, sd, word & 0x1FF, bitmask_mode='word')
        if sdef is None: raise ValueError(f'frame {rec:06X}: sprite definition {word & 0x1FF} unreadable')
        parts.append({'dx': dx, 'dy': dy, 'hflip': (word >> 14) & 1, 'vflip': (word >> 15) & 1, 'columns': sdef_columns(sdef),
                      'pal': sdef['pal_sub']})
        if not (word >> 13) & 1: break
        pos += 6
    return parts

def render(prom, crom, cid, slot=0, step=0, scale=1):
    st, sd = r32(prom, 0x080000 + cid * 4), r32(prom, 0x080080 + cid * 4)
    steps, mode = export.parse_anim(prom, r32(prom, st + slot * 4))
    rec = steps[step][1]
    parts = frame_parts(prom, rec, sd)
    base = PAL_ROM + palette_base(prom, min(cid, 25)) * 32
    pals = [[(0, 0, 0, 0)] + [decode_color(r16(prom, base + 32 * k + 2 * i)) + (255,) for i in range(1, 16)] for k in range(16)]
    W, H = 220, 200; ox, oy = 110, 180
    img = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    for p in parts:
        cols = p['columns']; w, h = len(cols) * 16, len(cols[0]) * 16
        a = np.zeros((h, w), dtype=np.uint8)
        for c, col in enumerate(cols):
            for r, t in enumerate(col):
                if t is not None: a[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = decode_tile(crom, t)
        if p['hflip']: a = a[:, ::-1]
        if p['vflip']: a = a[::-1, :]
        x = ox - p['dx'] - w if p['hflip'] else ox + p['dx']
        y = oy - p['dy'] - h if p['vflip'] else oy + p['dy']
        rgba = np.array(pals[(p['pal'] - 1) & 15], dtype=np.uint8)[a]   # sdef byte 2 high nibble 1 = the owner's first palette (KOF95: $10 = body)
        im = Image.fromarray(rgba, 'RGBA'); img.alpha_composite(im, (max(0, min(W - w, x)), max(0, min(H - h, y))))
    return img

if __name__ == '__main__':
    prom, crom = rom.load(NEO)
    sheet = Image.new('RGB', (6 * 224, 5 * 214), 'white'); d = ImageDraw.Draw(sheet)
    for cid in range(30):
        try: im = render(prom, crom, cid)
        except Exception as e: im = Image.new('RGBA', (220, 200), (255, 255, 255, 255)); ImageDraw.Draw(im).text((5, 90), str(e)[:40], fill='black')
        sheet.paste(im.convert('RGB'), ((cid % 6) * 224, (cid // 6) * 214)); d.text(((cid % 6) * 224 + 4, (cid // 6) * 214 + 2), f'id {cid}', fill='black')
    sheet.save(sys.argv[1])
