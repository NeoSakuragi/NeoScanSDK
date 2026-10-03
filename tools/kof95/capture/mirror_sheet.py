#!/usr/bin/env python3
"""Visual throw check sheets from mirror_check.py runs: per character, 4 moments of the throw (grab +2, +22, +42, +70
frames) as [MAME screenshot | same frame drawn from the recorded data], victim (P2) in the mirror palette.
    python3 capture/mirror_sheet.py OUT.png ID [ID ...]"""
import os, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import analyze as A, rom, export
from mirror_check import ROUND, SHOTS, GRAB
from PIL import Image, ImageDraw, ImageOps
from neogeo.sprite_decode import r32, r16, decode_tile, decode_color
import numpy as np

prom, crom = rom.load()

def palette(owner, slot, mirror):
    if 16 <= slot < 112: a = 0x1D9000 + owner * 0x400 + (0x200 if mirror else 0) + ((slot - 16) % 16) * 32
    else: a = 0x1D7000 + slot * 32
    return [0] + [r16(prom, a + 2 * i) for i in range(1, 16)]

def draw_object(cid, rec, face_right, mirror):
    """RGBA image of one object's frame, origin (feet) at (200, 250); sprites face left in ROM, mirrored to face right"""
    img = Image.new('RGBA', (400, 300)); px = img.load(); sdt = r32(prom, 0x080080 + cid * 4); pos = rec
    for _ in range(8):
        dx, dy, word = export.rs16(prom, pos), export.rs16(prom, pos + 2), r16(prom, pos + 4)
        sd = export.read_sprite_def(prom, sdt, word & 0x1FF)
        pal = palette(cid, prom[r32(prom, sdt + (word & 0x1FF) * 4) + 2], mirror)
        cols = export.sdef_columns(sd); w, h = len(cols) * 16, len(cols[0]) * 16; t = np.zeros((h, w), np.uint8)
        for c, col in enumerate(cols):
            for r, tile in enumerate(col):
                if tile is not None: t[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = decode_tile(crom, tile)
        hf, vf = (word >> 14) & 1, (word >> 15) & 1
        x0 = -dx - w if hf else dx; y0 = -dy - h if vf else dy
        if hf: t = t[:, ::-1]
        if vf: t = t[::-1, :]
        for y in range(h):
            for x in range(w):
                v = t[y, x]
                if v and 0 <= 200 + x0 + x < 400 and 0 <= 250 + y0 + y < 300: px[200 + x0 + x, 250 + y0 + y] = decode_color(pal[v]) + (255,)
        if not (word >> 13) & 1: break
        pos += 6
    return ImageOps.mirror(img) if face_right else img          # mirrored around x = 200, the origin

def pairs(cid):
    out = os.path.join(HERE, 'mirror', f'{cid}.txt'); shots = sorted(glob.glob(os.path.join(HERE, 'mirror', f'{cid}_shots', 'kof95', '*.png')))
    r1, r2 = A.load(out, 1), A.load(out, 2)
    grab = [n for n, _, _, w in r2[ROUND:] if A.state_of(w) in GRAB]
    if not grab or not shots: return []
    res = []
    for off in (2, 22, 42, 70):
        want = grab[0] + off
        k = min(range(len(SHOTS)), key=lambda i: abs(SHOTS[i] - want))
        if k >= len(shots): continue
        n = SHOTS[k]; shot = Image.open(shots[k]).convert('RGB')
        w1, w2 = r1[n - 1][3], r2[n - 1][3]; x1, x2 = A.x_of(w1), A.x_of(w2)
        rec = Image.new('RGB', shot.size, 'white'); cx = shot.width // 2 - int((x2 - x1) // 2)
        for w, x, m in ((w2, x2, True), (w1, x1, False)):
            im = draw_object(cid, A.frame_of(w), A.facing_of(w) == 1, m)
            rec.paste(im, (int(cx + (x - x1)) - 200, int(shot.height - 24 - A.y_of(w)) - 250), im)
        ImageDraw.Draw(rec).text((4, 4), f'+{n - grab[0]}f  victim st {A.state_of(w2)}', fill='black')
        res.append((shot, rec))
    return res

if __name__ == '__main__':
    out = sys.argv[1]; ids = list(map(int, sys.argv[2:]))
    rows = []
    for cid in ids:
        ps = pairs(cid)
        if not ps: continue
        W, H = ps[0][0].size
        row = Image.new('RGB', ((2 * W + 10) * len(ps) + 90, H), 'white'); d = ImageDraw.Draw(row)
        d.text((4, 4), rom.CAST[cid], fill='black')
        for i, (s, r) in enumerate(ps):
            x = 90 + i * (2 * W + 10)
            row.paste(s, (x, 0)); row.paste(r, (x + W + 2, 0))
        rows.append(row)
    S = Image.new('RGB', (max(r.width for r in rows), sum(r.height + 4 for r in rows)), 'black'); y = 0
    for r in rows: S.paste(r, (0, y)); y += r.height + 4
    S.save(out); print(out, S.size)
