#!/usr/bin/env python3
"""Title banner "BRAWLER '27", drawn the way 90s Neo Geo logos were: heavy slanted capitals, a hot vertical gradient
(white-yellow to red), a bright top edge, a thick black outline and a dark drop shadow; "'27" smaller in a cold gradient.
One 16-colour palette (0 = transparent), cut into 16x16 tiles: identical tiles stored once, written into the free
low tiles of bm_c1/bm_c2.bin from BANNER_BASE (after the stage, below the fighters); map + palette in banner.h.

    python3 make_banner.py OUTDIR            (after export_bm.py and make_stage.py)  -> banner.h, banner.png"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from tile_encoder import encode_crom_tile
from export_bm import TILE_BASE
from make_stage import neo_colour

FONT = '/usr/share/fonts/truetype/noto/NotoSans-CondensedBlack.ttf'
BANNER_BASE = 1536                         # stage tiles are 1..1535 (make_stage_ra.py: its pool fills them, the rest goes after the fighters); fighters start at TILE_BASE
SHADOW_BASE = 1664                         # ground shadow: 2 tiles, a 30x9 ellipse in colour 1
CORNER_BASE = 1666                         # debug box corners: 4 tiles (top left, top right, bottom left, bottom right)
SHEAR = 0.32                               # extra slant (x shift per row)
PAL = [(0, 0, 0),                          # 0 transparent
       (8, 8, 16),                         # 1 outline
       (72, 16, 24),                       # 2 drop shadow
       (255, 255, 224), (255, 240, 96), (255, 200, 40), (255, 150, 24), (240, 96, 16), (200, 40, 16),   # 3-8 hot gradient
       (255, 255, 255),                    # 9 top edge highlight
       (224, 248, 255), (120, 200, 255), (48, 120, 240), (24, 56, 168),                                  # 10-13 cold gradient
       (150, 150, 170), (0, 0, 0)]         # 14 thin underline, 15 unused

def glyphs(text, size):
    font = ImageFont.truetype(FONT, size)
    l, t, r, b = font.getbbox(text)
    im = Image.new('L', (r - l + 8, b - t + 8), 0)
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=font, fill=255)
    m = np.array(im) > 128
    h, w = m.shape
    out = np.zeros((h, w + int(SHEAR * h) + 2), bool)          # slant: the top moves right
    for y in range(h):
        dx = int(round(SHEAR * (h - 1 - y)))
        out[y, dx:dx + w] = m[y]
    return out

def paint(canvas, mask, x0, y0, gradient):
    h, w = mask.shape
    big = np.array(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0   # 2 px outline
    region = canvas[y0:y0 + h, x0:x0 + w]
    shadow = np.zeros_like(big); shadow[4:, 4:] = big[:-4, :-4]
    region[shadow & (region == 0)] = 2
    region[big] = 1
    rows = np.nonzero(mask.any(axis=1))[0]; top, bot = rows[0], rows[-1]
    for y in range(h):
        k = (y - top) * len(gradient) // max(1, bot - top + 1)
        region[y][mask[y]] = gradient[min(len(gradient) - 1, max(0, k))]
    edge = mask & ~np.vstack([np.zeros((2, w), bool), mask[:-2]])                                         # top 2 px
    region[edge] = 9 if gradient[0] == 3 else 10

def draw():
    big, small = glyphs('BRAWLER', 47), glyphs("'27", 33)
    W = 16 * ((big.shape[1] + small.shape[1] + 16 + 15) // 16)
    H = 16 * ((big.shape[0] + 16 + 15) // 16)
    canvas = np.zeros((H, W), np.uint8)
    paint(canvas, big, 4, 4, [3, 4, 5, 6, 7, 8])
    paint(canvas, small, 4 + big.shape[1] + 2, 4 + big.shape[0] - small.shape[0], [10, 11, 12, 13])
    y = 4 + big.shape[0] + 6
    canvas[y, 8:W - 8][canvas[y, 8:W - 8] == 0] = 14                                                     # speed line
    return canvas

def build(outdir):
    px = draw(); H, W = px.shape; cols, rows = W // 16, H // 16
    tiles, index, tmap = [], {}, []
    for c in range(cols):
        for r in range(rows):
            t = px[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16]
            if not t.any(): tmap.append(0); continue
            key = t.tobytes()
            if key not in index: index[key] = BANNER_BASE + len(tiles); tiles.append(t)
            tmap.append(index[key])
    assert BANNER_BASE + len(tiles) <= SHADOW_BASE, 'banner tiles run into the shadow tiles'
    for name, plane in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        for k, t in enumerate(tiles):
            o = (BANNER_BASE + k) * 64; data[o:o + 64] = encode_crom_tile(t)[plane]
        open(p, 'wb').write(bytes(data))
    sh = np.zeros((16, 32), np.uint8)                                       # ground shadow ellipse
    for y in range(16):
        for x in range(32):
            if ((x - 15.5) / 15.0) ** 2 + ((y - 7.5) / 4.6) ** 2 <= 1: sh[y, x] = 1
    for name, plane in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        for k in range(2):
            o = (SHADOW_BASE + k) * 64; data[o:o + 64] = encode_crom_tile(sh[:, k * 16:(k + 1) * 16])[plane]
        open(p, 'wb').write(bytes(data))
    corners = []                                                             # 8x8 brackets, 2 px, black edge
    for cx, cy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        t = np.zeros((16, 16), np.uint8)
        x0, y0 = (8 if cx else 0), (8 if cy else 0)
        for i in range(8):
            for j in range(2):
                hx = x0 + i; hy = y0 + (7 - j if cy else j)                  # horizontal arm along the box edge
                vx = x0 + (7 - j if cx else j); vy = y0 + i                  # vertical arm
                t[hy, hx] = 1; t[vy, vx] = 1
        edge = np.zeros_like(t)
        for y in range(16):
            for x in range(16):
                if not t[y, x] and any(0 <= y + dy < 16 and 0 <= x + dx < 16 and t[y + dy, x + dx] == 1
                                       for dy in (-1, 0, 1) for dx in (-1, 0, 1)): edge[y, x] = 2
        corners.append(t + edge)
    for name, plane in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        for k, t in enumerate(corners):
            o = (CORNER_BASE + k) * 64; data[o:o + 64] = encode_crom_tile(t)[plane]
        open(p, 'wb').write(bytes(data))
    pal = [0x8000] + [neo_colour(*c) for c in PAL[1:]]
    h = ['/* Generated by tools/brawler/make_banner.py. Do not edit. */', '#ifndef BANNER_H', '#define BANNER_H',
         f'#define BANNER_COLS {cols}', f'#define BANNER_ROWS {rows}', f'#define SHADOW_TILE {SHADOW_BASE}   /* 2 tiles: ground shadow, colour 1 */', f'#define CORNER_TILE {CORNER_BASE}   /* 4 tiles: box corners TL TR BL BR, colour 1 + black edge 2 */',
         'static const uint16_t banner_pal[16] = {' + ', '.join(f'0x{v:04X}' for v in pal) + '};',
         'static const uint16_t banner_map[BANNER_COLS * BANNER_ROWS] = {' + ', '.join(map(str, tmap)) + '};   /* column-major, 0 = empty */',
         '#endif']
    open(os.path.join(outdir, 'banner.h'), 'w').write('\n'.join(h) + '\n')
    im = Image.fromarray(px, 'P'); im.putpalette([v for c in PAL for v in c]); im.save(os.path.join(outdir, 'banner.png'))
    print(f'banner: {W}x{H} px, {cols}x{rows} tiles, {len(tiles)} unique')

if __name__ == '__main__':
    build(sys.argv[1])
