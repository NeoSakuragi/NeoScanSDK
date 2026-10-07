#!/usr/bin/env python3
"""The head point of a fighter's select-screen pose (TODO #157): where the select cursor's arrow points, px from the
feet in the ROM sprites' orientation (facing LEFT; x < 0 = the way it faces, y < 0 = up).

Rule: the pose's frame drawn from its export (export_bm.py's per-fighter tmp dir: kof95_export.json + its C1 / C2), the
top of the head = the first row from the top with an opaque run of at least HEAD_RUN px (a weapon's tip, a staff, a
hand's fingers are thinner), x = the middle of the pixels of that run and of the runs under it that overlap it over
HEAD_ROWS rows. A pose where something wide rises above the head (a raised fist, Mai's fan) gives its point in data:
game.json roster[].watch.head [x, y], which wins.

    python3 head_point.py BUILD_DIR [OUT.png]     every roster fighter's point (build/roster.json), and a sheet"""
import json, os, sys
import numpy as np

HEAD_RUN, HEAD_ROWS = 8, 10

def tile(reg, code):
    """a C ROM tile (C1 / C2 interleaved bytes, 128 a tile) as 16 x 16 pens"""
    b = np.frombuffer(reg, np.uint8, 128, code * 128).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    return np.concatenate([pen[1], pen[0]], axis=1)

X0, Y0, SIZE = 160, 300, 320                   # the feet's place in the picture

def pens(ch, reg, fi, pal=None):
    """frame fi of an export (parts at dx / dy from the feet, as draw.s places them) -> pens[SIZE][SIZE]; pal: only the
    parts drawn with that palette (the body without its effects: SS2's rage pose, Kuroko's flame aura)"""
    img = np.zeros((SIZE, SIZE), np.uint8)
    for p in ch['frames'][fi]['parts']:
        if pal is not None and p.get('pal', 0) != pal: continue
        rows = len(p['tiles'][0]); top = -p['dy'] - rows * 16 if p['vflip'] else p['dy']
        for c, col in enumerate(p['tiles']):
            for r, t in enumerate(col):
                if not t: continue
                pen = tile(reg, t)
                if p['hflip']: pen = pen[:, ::-1]
                rr = r
                if p['vflip']: pen = pen[::-1]; rr = rows - 1 - r
                y, x = Y0 + top + 16 * rr, X0 + p['dx'] + 16 * c
                sub = img[y:y + 16, x:x + 16]; sub[pen > 0] = pen[pen > 0]
    return img

def runs(row):
    out, x, n = [], 0, len(row)
    while x < n:
        if row[x]:
            s = x
            while x < n and row[x]: x += 1
            out.append((s, x))
        else: x += 1
    return out

def head_of(img):
    m = img > 0
    for y in range(SIZE):
        w = [r for r in runs(m[y]) if r[1] - r[0] >= HEAD_RUN]
        if not w: continue
        s, e = max(w, key=lambda r: r[1] - r[0]); xs = []
        for yy in range(y, min(SIZE, y + HEAD_ROWS)):
            for r in runs(m[yy]):
                if r[1] > s and r[0] < e: xs += range(r[0], r[1])
        return int(round(float(np.mean(xs)))) - X0, y - Y0
    return 0, -100

def load(tmp, name):
    ex = json.load(open(os.path.join(tmp, 'kof95_export.json'))); ch = ex['characters'][name]
    c1 = open(os.path.join(tmp, 'kof95_c1.bin'), 'rb').read(); c2 = open(os.path.join(tmp, 'kof95_c2.bin'), 'rb').read()
    reg = bytearray(len(c1) * 2); reg[0::2] = c1; reg[1::2] = c2
    return ch, bytes(reg)

def head_point(ch, reg, override=None):
    """(x, y) of the head of the export's watch pose (its first step's frame); override: game.json's [x, y]"""
    if override: return tuple(override)
    if 'watch' not in ch['anims']: return 0, -100
    return head_of(pens(ch, reg, ch['anims']['watch']['steps'][0]['frame']))

if __name__ == '__main__':
    B = sys.argv[1]
    from PIL import Image, ImageDraw
    tiles = []
    for r in json.load(open(os.path.join(B, 'roster.json'))):
        g, n = r['bank'].split(':')
        ch, reg = load(os.path.join(B, f'tmp_{g}_{n}'), n)
        hx, hy = head_point(ch, reg, r.get('head')); print(r['name'], hx, hy, '(data)' if r.get('head') else '')
        if len(sys.argv) > 2:
            m = pens(ch, reg, ch['anims']['watch']['steps'][0]['frame'])
            im = Image.fromarray(np.where(m > 0, 0, 255).astype(np.uint8)).convert('RGB'); d = ImageDraw.Draw(im)
            x, y = X0 + hx, Y0 + hy; d.line([x - 8, y, x + 8, y], fill='red'); d.line([x, y - 8, x, y + 8], fill='red')
            d.text((4, 4), f"{r['name']} {hx},{hy}", fill='black'); tiles.append(im.crop((60, 140, 260, 310)))
    if tiles:
        sheet = Image.new('RGB', (200 * 6, 170 * ((len(tiles) + 5) // 6)), 'white')
        for i, t in enumerate(tiles): sheet.paste(t, ((i % 6) * 200, (i // 6) * 170))
        sheet.save(sys.argv[2])
