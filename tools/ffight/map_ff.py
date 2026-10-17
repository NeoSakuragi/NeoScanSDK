#!/usr/bin/env python3
"""Final Fight's between-rounds city map, straight from the ROM (no emulator needed).

How the game draws it (68000 code, ffight World 900112):
- block copier $1BB8: block id -> table $66F3E (word offsets) -> [type.w][dst.l][rows-1.w][cols-1.w][attr.w][src.l];
  type 2 ($1C0E) copies rows x cols cells of [code - $4400][attr] words into the scroll1 (8x8) tilemap, row by row.
- the map = blocks 4..10: 32 x 13 cells (256 x 104 px) at $908888 (scroll1 column 17, row 2), sources
  $CB860 + k * $680 (k = 0..6), one per progress step; blocks 11..17 = the same sources on the second scroll1
  page ($90A8C8, rows 34+). On the round-clear screen the game flips scroll1 between the two pages every 6 frames:
  the previous progress and the new one blink (the "moving" route is that blink, not an object).
- cells: tile codes $46B0-$487F (the map is one 16-tile-wide picture in the graphics ROM) + a few route tiles;
  attr = palette (bits 0-4) only. Captured districts = the same tiles in palette 3 (green / cyan labels) instead of
  palette 4 (grey). Scroll1 palettes: ROM $C2800 + 32 * p (copied to palette RAM page 1).
- the place names (SLUM, SUBWAY, PARK, WEST SIDE, UP TOWN, INDUSTRIAL AREA, BAY AREA) are pixels inside those
  map tiles (baked), not text; "THE ATLANTIC OCEAN" (rows 15-16) and "ROUND n CLEAR!" are text drawn separately
  from font tiles.
Usage: map_ff.py OUT_DIR   -> PNGs + map_ff.json (cells, palettes, tile list)
"""
import json, os, struct, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ff

BLOCKS = 0x66F3E
PAL1 = 0xC2800
COLS, ROWS = 32, 13

def block(i):
    P = ff.load()[0]
    a = BLOCKS + struct.unpack('>H', P[BLOCKS + 2 * i:BLOCKS + 2 * i + 2])[0]
    t, dst, r, c, attr, src = struct.unpack('>HIHHHI', P[a:a + 16])
    return dict(id=i, type=t, dst=dst, rows=r + 1, cols=c + 1, attr=attr, src=src)

def cells(src, rows=ROWS, cols=COLS):
    P = ff.load()[0]; out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            o = src + 4 * (r * cols + c); code, attr = struct.unpack('>HH', P[o:o + 4])
            row.append((code + 0x4400, attr))
        out.append(row)
    return out

def pal1(p): return [ff.u16(PAL1 + 32 * p + 2 * k) for k in range(16)]
def rgb(p): return [ff.cps_rgb(w) for w in pal1(p)]

def px8(code, half):
    G = ff.load()[1]; o = (code & 0x7FFF) * 64; out = []
    for y in range(8):
        b = G[o + 8 * y + 4 * half:o + 8 * y + 4 * half + 4]
        out.append([sum(((b[k] >> (7 - x)) & 1) << k for k in range(4)) for x in range(8)])
    return out

def pens(grid, col0=17):
    """pen-index image (0..15) of a cell grid; scroll1 picks the tile half by tilemap column parity"""
    h, w = len(grid), len(grid[0]); out = [[15] * (8 * w) for _ in range(8 * h)]
    for r, row in enumerate(grid):
        for c, (code, attr) in enumerate(row):
            t = px8(code, (col0 + c) & 1)
            for y in range(8):
                for x in range(8):
                    yy = 7 - y if attr & 0x40 else y; xx = 7 - x if attr & 0x20 else x
                    out[8 * r + y][8 * c + x] = t[yy][xx]
    return out

def render(grid, pal_of=None, col0=17, bg=None):
    """RGBA image; pal_of(r, c, attr) -> palette number (default: the cell's own)"""
    h, w = len(grid), len(grid[0]); im = Image.new('RGBA', (8 * w, 8 * h), bg or (0, 0, 0, 0)); px = im.load()
    pm = pens(grid, col0)
    for r, row in enumerate(grid):
        for c, (code, attr) in enumerate(row):
            pal = rgb(pal_of(r, c, attr) if pal_of else attr & 0x1F)
            for y in range(8):
                for x in range(8):
                    v = pm[8 * r + y][8 * c + x]
                    if v != 15: px[8 * c + x, 8 * r + y] = pal[v] + (255,)
    return im

def on_white(im, scale=1):
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
    bg = bg.convert('RGB'); return bg.resize((im.size[0] * scale, im.size[1] * scale), Image.NEAREST) if scale > 1 else bg

# the map's parts by pen (the same in palettes 3 and 4): read off the pen images of the map
PEN_LABEL = (0, 12, 13)        # the place names: outline 0, fill 12 / 13 (13 also the park statue, a few dots)
PEN_ROUTE = (10, 11)           # the subway line (grey in palette 4, purple in palette 3)
PEN_STOP = (2,)                # the red dots (route ends: slum, west side, bay area)
# the names' boxes in map pixels (x0, y0, x1, y1), from the pen 0 / 12 clusters
LABELS = {'WEST SIDE': (86, 9, 145, 21), 'SUBWAY': (42, 29, 104, 67), 'SLUM': (31, 33, 70, 45), 'UP TOWN': (147, 34, 204, 46),
          'PARK': (97, 46, 124, 57), 'INDUSTRIAL AREA': (143, 50, 210, 71), 'BAY AREA': (208, 62, 251, 83)}
BANNER_ROWS = (11, 12)         # "THE ATLANTIC OCEAN": the block's last two cell rows
DISTRICTS = ['SLUM', 'SUBWAY + PARK', 'WEST SIDE', 'INDUSTRIAL AREA', 'BAY AREA']   # what variant k + 1 adds

def variant(k): return cells(0xCB860 + k * 0x680)

def label_mask(pm):
    m = [[False] * len(pm[0]) for _ in pm]
    for x0, y0, x1, y1 in LABELS.values():
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if pm[y][x] in PEN_LABEL: m[y][x] = True
        for y in range(y0, y1 + 1):              # their olive drop shadow (pen 14) next to them
            for x in range(x0, x1 + 1):
                if pm[y][x] == 14 and any(pm[y + dy][x + dx] in PEN_LABEL for dy in (-2, -1, 0) for dx in (-2, -1, 0)
                                          if 0 <= y + dy < len(pm) and 0 <= x + dx < len(pm[0])): m[y][x] = True
    return m

def erase_labels(pm):
    """the names' pixels filled from their neighbours (the most common non-name pen around, grown inward)"""
    from collections import Counter
    pm = [r[:] for r in pm]; todo = label_mask(pm); H, W = len(pm), len(pm[0])
    left = {(x, y) for y in range(H) for x in range(W) if todo[y][x]}
    while left:
        done = {}
        for x, y in left:
            c = Counter()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if (dx or dy) and 0 <= y + dy < H and 0 <= x + dx < W and (x + dx, y + dy) not in left:
                        v = pm[y + dy][x + dx]; c[v] += 0.2 if v == 14 else 1   # (road outlines: not smeared)
            if c: done[(x, y)] = c.most_common(1)[0][0]
        if not done: break
        for (x, y), v in done.items(): pm[y][x] = v
        left -= set(done)
    return pm

def pen_image(grid, pm, keep=None, drop=None):
    """RGBA of a pen map with the cells' palettes; keep / drop: pen sets"""
    H, W = len(pm), len(pm[0]); im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); px = im.load()
    for y in range(H):
        for x in range(W):
            v = pm[y][x]
            if v == 15 or (keep is not None and v not in keep) or (drop is not None and v in drop): continue
            px[x, y] = rgb(grid[y // 8][x // 8][1] & 0x1F)[v] + (255,)
    return im

def neo_stats(pm, ox=0, oy=0):
    """the picture as Neo Geo 16x16 sprite tiles from map pixel (-ox, -oy): columns, rows, tiles used, unique"""
    H, W = len(pm), len(pm[0]); used, uniq = 0, set()
    for by in range(-oy, H, 16):
        for bx in range(-ox, W, 16):
            blk = tuple(pm[y][x] if 0 <= y < H and 0 <= x < W else 15 for y in range(by, by + 16) for x in range(bx, bx + 16))
            if any(v != 15 for v in blk): used += 1; uniq.add(blk)
    return dict(cols=-(-(W + ox) // 16), rows=-(-(H + oy) // 16), tiles=used, unique=len(uniq))

if __name__ == '__main__':
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    blocks = [block(i) for i in range(18)]
    variants = [variant(k) for k in range(7)]
    info = {'blocks': blocks, 'palettes': {p: ['%04x' % w for w in pal1(p)] for p in (3, 4, 8)}, 'variants': []}
    for k, g in enumerate(variants):
        on_white(render(g)).save(f'{out}/variant{k}.png')
        info['variants'].append({'src': '%X' % (0xCB860 + k * 0x680),
                                 'green_cells': sum(1 for row in g for _, a in row if a & 0x1F == 3),
                                 'codes': sorted({'%04X' % c for row in g for c, _ in row})})
    # parts (variant 0 = nothing visited; variant 5 = all five districts green)
    g0, g5 = variants[0], variants[5]; pm = pens(g0)
    on_white(pen_image(g0, erase_labels(pm))).save(f'{out}/part_base_nolabels.png')
    lm = label_mask(pm); lab = Image.new('RGBA', (len(pm[0]), len(pm)), (0, 0, 0, 0))
    full5 = render(g5)
    for y in range(len(pm)):
        for x in range(len(pm[0])):
            if lm[y][x]: lab.putpixel((x, y), full5.getpixel((x, y)))
    on_white(lab).save(f'{out}/part_labels.png')
    pm5 = [r if y < 8 * BANNER_ROWS[0] else [15] * len(r) for y, r in enumerate(pens(g5))]
    on_white(pen_image(g5, pm5, keep=PEN_ROUTE + PEN_STOP)).save(f'{out}/part_route.png')
    ban = [[c if r in BANNER_ROWS else (0x4420, 4) for c in row] for r, row in enumerate(g0)]
    on_white(render(ban)).save(f'{out}/part_banner.png')
    for k in range(1, 6):                       # the cells each step turns green
        prev, cur = variants[k - 1], variants[k]
        g = [[(c, 3 if (a & 31) == 3 and (p[1] & 31) != 3 else 4) for (c, a), p in zip(r1, r0)] for r1, r0 in zip(cur, prev)]
        im = render(g, pal_of=lambda r, c, a: a); bg = Image.new('RGBA', im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
        bg.convert('RGB').save(f'{out}/step{k}.png')
    info['neo'] = {f'{ox},{oy}': neo_stats(pm, ox, oy) for ox in (0, 8) for oy in (0, 8)}
    info['labels'] = LABELS; info['districts'] = DISTRICTS
    json.dump(info, open(f'{out}/map_ff.json', 'w'), indent=1)
    print(json.dumps(info['neo']))
