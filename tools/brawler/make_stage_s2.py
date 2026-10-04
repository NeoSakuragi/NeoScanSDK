#!/usr/bin/env python3
"""Placeholder brawler stage: Sengoku 2's round 1 castle, extracted from /data/roms/sengoku2.neo (prototype art only; the
final game gets its own). Two planes, both as Sengoku 2 shows them (block row 0 at screen y 0, 16 px tiles):

  front  map 0 block row 4 (blocks 18, 18, 6, 7; 18 is empty: 6, 7 = the castle courtyard, 640 px) followed by map 29 block row 4 (blocks 19, 20: the
         castle after the warp, 640 px) = 80 columns x 14 rows (1280 x 224 px), scrolls 1:1 with the camera
  back   map 1 block row 2 (blocks 12, 13, 12: sunset sky + burning field, 960 px), scrolls at camera >> 1 (Sengoku 2's
         parallax code 2). Only its top BACK_ROWS rows are kept: the front plane is opaque below y 80 (measured: its
         transparent pixels are all in rows 0-4, the deepest at y 65), so the back plane is a band that never reaches the
         floor. stage_depth[] = rows from the top of each front column that hold a transparent pixel: the runtime sizes
         each back sprite to what the front columns over it let through (0 = the front hides it, no sprite at all).

ROM format (decoded 2026-10-04, /data/neogeo_dict/sengoku2/tools/extract_maps.py): map table $402E8; a map = u8 width,
u8 height, u8 y0, then width*height block ids column-major; block $56A30 + id*640 = 20 x 16 tile words column-major;
tile word bits 0-13 index (C ROM tile $8000 + index, 0 = empty), bit 14 H flip, bit 15 V flip; palette byte per index at
$40582; palette n at $50040 + (n >> 5) * $402 + (n & 31) * 32 (the set the game keeps in palette RAM bank 1, never
changed during round 1: measured on 400 palette dumps).

Tiles are copied raw from Sengoku 2's C ROM and stored once: a tile that is a flipped copy of a stored one points to it
with the flip folded into the map word. They go into the free space of bm_c1/bm_c2.bin below the banner (1 ..
BANNER_BASE - 1). Palettes: STAGE_PAL + k, k in the order of Sengoku 2's palette numbers.

    python3 make_stage_s2.py OUTDIR      (after export_bm.py OUTDIR ...)  -> stage.h, stage.png, patched bm_c*.bin"""
import os, struct, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_banner import BANNER_BASE

ROM = '/data/roms/sengoku2.neo'
FRONT = [(0, 4), (29, 4)]                  # (map, block row): their blocks left to right
BACK = (1, 2)
ROWS = 14                                  # 224 px: rows 14-15 of a block are below the screen (empty in these blocks)
BACK_ROWS = 5                              # the back plane band: rows 0-4 (the front's transparency ends at y 65)
STAGE_PAL = 80                             # main.c: 0 text, 1 free, 2-15 fix portraits, 16-79 fighters (8 x MAX_PALS)

def load_rom():
    d = open(ROM, 'rb').read()
    off = [struct.unpack_from('<I', d, o)[0] for o in (4, 8, 12, 16, 20, 24)]
    p = bytearray(d[4096:4096 + off[0]]); p[0::2], p[1::2] = p[1::2], p[0::2]   # .neo P is little-endian words
    cbase = 4096 + sum(off[:5])
    return bytes(p), d[cbase:cbase + off[5]]

P, CROM = load_rom()
def u8(a): return P[a]
def u16(a): return struct.unpack_from('>H', P, a)[0]
def u32(a): return struct.unpack_from('>I', P, a)[0]

def map_row(m, row):
    """the blocks of a map's block row, left to right, without the empty ones (block 18: nothing in it)"""
    a = u32(0x402E8 + 4 * m); w, h = u8(a), u8(a + 1)
    blocks = [u8(a + 3 + c * h + row) for c in range(w)]
    return [b for b in blocks if any(u16(0x56A30 + b * 640 + 2 * k) & 0x3FFF for k in range(320))]

def tile_raw(t):                           # .neo C ROM: c1 / c2 bytes interleaved, 128 bytes a tile
    tt = CROM[t * 128:(t + 1) * 128]
    return tt[0::2], tt[1::2]

def tile_px(t):
    c1, c2 = tile_raw(t); px = np.zeros((16, 16), np.uint8)
    for half, x0 in ((0, 8), (1, 0)):
        for y in range(16):
            o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
            for x in range(8):
                px[y, x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
    return px

def palette(n):
    return [u16(0x50040 + (n >> 5) * 0x402 + (n & 31) * 32 + 2 * k) for k in range(16)]

def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)

def plane(blocks, rows):
    """column-major list of (rom tile index, flips SCB1-style: bit 0 H, bit 1 V, rom palette) per cell, None = empty"""
    cells = []
    for b in blocks:
        for c in range(20):
            for r in range(rows):
                w = u16(0x56A30 + b * 640 + c * 32 + r * 2); idx = w & 0x3FFF
                cells.append(None if not idx else (0x8000 + idx, (1 if w & 0x4000 else 0) | (2 if w & 0x8000 else 0), u8(0x40582 + idx)))
    return cells

def flip(px, f):
    if f & 1: px = px[:, ::-1]
    if f & 2: px = px[::-1]
    return px

def build(outdir):
    front_blocks = [b for m, r in FRONT for b in map_row(m, r)]
    back_blocks = map_row(*BACK)
    front, back = plane(front_blocks, ROWS), plane(back_blocks, BACK_ROWS)
    fcols, bcols = len(front_blocks) * 20, len(back_blocks) * 20
    pals = sorted({c[2] for c in front + back if c})
    assert len(pals) <= 16, pals
    stored, index, rom_of = [], {}, {}            # stored: raw tiles; index: pixel bytes -> our tile number
    def ours(t):                                  # rom tile -> (our tile number, flip to apply to the stored one)
        if t in rom_of: return rom_of[t]
        px = tile_px(t)
        for f in range(4):                        # t = flip(stored, f)  <=>  stored = flip(t, f)
            k = index.get(flip(px, f).tobytes())
            if k is not None: rom_of[t] = (k, f); return rom_of[t]
        stored.append(t); index[px.tobytes()] = len(stored); rom_of[t] = (len(stored), 0)
        return rom_of[t]
    def words(cells):
        out = []
        for c in cells:
            if c is None: out += [0, 0]; continue
            n, f = ours(c[0])
            out += [n, (STAGE_PAL + pals.index(c[2])) << 8 | (c[1] ^ f)]
        return out
    fw, bw = words(front), words(back)
    assert len(stored) < BANNER_BASE, f'{len(stored)} stage tiles, room for {BANNER_BASE - 1}'
    for name, k in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        for n, t in enumerate(stored): data[(n + 1) * 64:(n + 2) * 64] = tile_raw(t)[k]
        open(p, 'wb').write(bytes(data))
    # what the camera sees: front pixels per column, transparent rows from the top
    img = np.zeros((ROWS * 16, fcols * 16), np.uint8); pimg = np.zeros_like(img)
    for i, c in enumerate(front):
        if c is None: continue
        col, row = divmod(i, ROWS)
        img[row * 16:row * 16 + 16, col * 16:col * 16 + 16] = flip(tile_px(c[0]), c[1]); pimg[row * 16:row * 16 + 16, col * 16:col * 16 + 16] = pals.index(c[2])
    depth = []
    for col in range(fcols):
        t = np.where((img[:, col * 16:col * 16 + 16] == 0).any(1))[0]
        depth.append(0 if not len(t) else t.max() // 16 + 1)
    assert max(depth) <= BACK_ROWS, max(depth)
    pal_words = [w for n in pals for w in palette(n)]
    h = ['/* Generated by tools/brawler/make_stage_s2.py: Sengoku 2 round 1 (castle), a prototype placeholder. Do not edit. */',
         '#ifndef STAGE_H', '#define STAGE_H',
         f'#define STAGE_COLS {fcols}', f'#define STAGE_ROWS {ROWS}', f'#define STAGE_W {fcols * 16}',
         f'#define BACK_COLS {bcols}', f'#define BACK_ROWS {BACK_ROWS}',
         f'#define STAGE_PAL {STAGE_PAL}', f'#define STAGE_NPAL {len(pals)}   /* Sengoku 2 palettes {", ".join(map(str, pals))} */',
         'static const uint16_t stage_pal[STAGE_NPAL * 16] = {' + ', '.join(f'0x{v:04X}' for v in pal_words) + '};',
         '/* SCB1 words {tile, attribute} per cell, column-major */',
         'static const uint16_t stage_map[STAGE_COLS * STAGE_ROWS * 2] = {' + ', '.join(map(str, fw)) + '};',
         'static const uint16_t back_map[BACK_COLS * BACK_ROWS * 2] = {' + ', '.join(map(str, bw)) + '};',
         '/* rows from the top of each front column holding a transparent pixel: how much of the back plane shows there;',
         '   2 zeros past the end (main.c reads the 2 front columns over each back column without a bound test) */',
         'static const uint8_t stage_depth[STAGE_COLS + 2] = {' + ', '.join(map(str, depth + [0, 0])) + '};',
         '#endif']
    open(os.path.join(outdir, 'stage.h'), 'w').write('\n'.join(h) + '\n')
    # preview: the front with the back plane in its holes, each column as seen with the camera centred on it
    lut = np.array([[rgb(w) for w in palette(n)] for n in pals], np.uint8)
    out = lut[pimg, img]
    bimg = np.zeros((BACK_ROWS * 16, bcols * 16, 3), np.uint8)
    for i, c in enumerate(back):
        if c is None: continue
        col, row = divmod(i, BACK_ROWS)
        bimg[row * 16:row * 16 + 16, col * 16:col * 16 + 16] = lut[pals.index(c[2])][flip(tile_px(c[0]), c[1])]
    hole = img == 0
    for x in range(out.shape[1]):                 # back at half speed, the camera centred on x: back x = x - camera / 2
        cam = min(max(x - 160, 0), out.shape[1] - 320); bx = (x - cam // 2) % bimg.shape[1]
        rows_ = np.where(hole[:BACK_ROWS * 16, x])[0]
        out[rows_, x] = bimg[rows_, bx]
    Image.fromarray(out).save(os.path.join(outdir, 'stage.png'))
    print(f'stage: Sengoku 2 castle, front {fcols}x{ROWS} (blocks {front_blocks}), back {bcols}x{BACK_ROWS} (blocks {back_blocks}), '
          f'{len(stored)} unique tiles ({len(rom_of)} ROM tiles), palettes {pals} -> {STAGE_PAL}-{STAGE_PAL + len(pals) - 1}, '
          f'back band depth max {max(depth)} rows')

if __name__ == '__main__':
    build(sys.argv[1])
