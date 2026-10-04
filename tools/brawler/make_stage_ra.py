#!/usr/bin/env python3
"""Placeholder brawler stage: Robo Army's area 0 (the horizontal street), extracted from /data/roms/roboarmy.neo
(prototype art only; the final game gets its own). One plane, as Robo Army shows it: 160 columns (2560 px, ids $00-$09),
band row 0 at screen y 0, scrolls 1:1 with the camera (Robo Army has no parallax).

ROM format (decoded 2026-10-04, /data/neogeo_dict/roboarmy/README.md + tools/extract_roboarmy.py): map data $531F2,
16-px columns of 16 tile words (32 bytes), area 0 = the first 160 columns; tile word bits 0-12 C ROM tile, bit 13 H flip,
bits 14-15 -> SCB1 auto-animation bits 2-3 (bit 14: 4 frames, bit 15: 8 frames); palette = byte $5C1F2 + tile; palette n
at $313F4 + n*32. Tile $3FF is Robo Army's blank (no pixels): our empty tile 0. Robo Army's tile 0 is a real tile (one
cell of the street uses it). Rows 0-1 are blank over the whole street (Robo Army shows its black backdrop there, behind
the HUD), rows 14-15 are below the screen: STAGE_ROWS = 12 rows from screen y STAGE_Y = 32.

Auto-animation (the LSPC replaces the low 2 / 3 bits of an animated tile's number by its counter): every group of 4 / 8
tiles an animated word names is copied whole to an aligned place, its words keep the flag. Robo Army's speed: REG_LSPCMODE
= $104016 << 8 = $0800 in every scene (table $7616), written by the runtime with the stage (STAGE_LSPCMODE).

Other tiles are copied raw and stored once: a tile that is a flipped copy of a stored one points to it with the flip
folded into the map word. They go into bm_c1/bm_c2.bin at 1 .. BANNER_BASE - 1. Palettes: STAGE_PAL + k, k in the order
of Robo Army's palette numbers.

    python3 make_stage_ra.py OUTDIR      (after export_bm.py OUTDIR ...)  -> stage.h, stage.png, patched bm_c*.bin"""
import os, struct, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_banner import BANNER_BASE

ROM = '/data/roms/roboarmy.neo'
MAP, PTAB, PALS = 0x531F2, 0x5C1F2, 0x313F4
COLS = 160                                 # area 0: ids $00-$09 (area 1 starts at id $0A, $6506)
ROW0, ROWS = 2, 12                         # rows 2-13: screen y 32-223
BLANK = 0x3FF
STAGE_PAL = 80                             # main.c: 0 text, 1 free, 2-15 fix portraits, 16-79 fighters (8 x MAX_PALS)
LSPCMODE = 0x0800                          # Robo Army's auto-animation speed (8)
BACKDROP = 0x0000                          # Robo Army's backdrop in area 0 (palette RAM $401FFE, measured): black

def load_rom():
    d = open(ROM, 'rb').read()
    off = [struct.unpack_from('<I', d, o)[0] for o in (4, 8, 12, 16, 20, 24)]
    p = bytearray(d[4096:4096 + off[0]]); p[0::2], p[1::2] = p[1::2], p[0::2]   # .neo P is little-endian words
    cbase = 4096 + sum(off[:5])
    return bytes(p), d[cbase:cbase + off[5]]

P, CROM = load_rom()
def u8(a): return P[a]
def u16(a): return struct.unpack_from('>H', P, a)[0]

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

def palette(n): return [u16(PALS + n * 32 + 2 * k) for k in range(16)]

def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)

def word(c, r): return u16(MAP + c * 32 + r * 2)

def flip(px, f):
    if f & 1: px = px[:, ::-1]
    if f & 2: px = px[::-1]
    return px

def render(words_of, tile_of, pal_of, anim=0, bg=(0, 0, 0)):
    """the plane, COLS x ROWS cells, with the auto-animation counter at anim (the LSPC's tile substitution)"""
    img = np.zeros((ROWS * 16, COLS * 16, 3), np.uint8); img[:] = bg
    for c in range(COLS):
        for r in range(ROWS):
            t, a = words_of(c, r)
            if t is None: continue
            if a & 8: t = (t & ~7) | (anim & 7)
            elif a & 4: t = (t & ~3) | (anim & 3)
            px = flip(tile_of(t), a & 3); lut = pal_of(a, t)
            m = px != 0; sub = img[r * 16:r * 16 + 16, c * 16:c * 16 + 16]; sub[m] = lut[px[m]]
    return img

def rom_cell(c, r):                        # Robo Army's own word, as its LSPC draws it: (tile, SCB1 attribute bits 0-3)
    w = word(c, ROW0 + r); t = w & 0x1FFF
    return (None, 0) if t == BLANK else (t, (1 if w & 0x2000 else 0) | (w >> 14) << 2)

def build(outdir):
    for c in range(COLS):                  # what the cut leaves out is blank / off screen
        assert all(word(c, r) & 0x1FFF == BLANK for r in range(ROW0)), c
    cells = [[rom_cell(c, r) for r in range(ROWS)] for c in range(COLS)]
    pals = sorted({u8(PTAB + t) for col in cells for t, a in col if t is not None})
    assert len(pals) <= 250 - STAGE_PAL, pals                   # 250+: banner, shadows, debug, sparks (main.c)
    # animated groups first, aligned: 8-tile groups, then 4-tile groups not inside one
    groups = {}
    for col in cells:
        for t, a in col:
            if t is None or not a & 12: continue
            n = 8 if a & 8 else 4; groups[t & ~(n - 1)] = n
    for g, n in list(groups.items()):
        if n == 4 and groups.get(g & ~7) == 8: del groups[g]
    slots = {}                                                  # our tile number -> Robo Army tile (raw copy)
    rom_of = {}                                                 # Robo Army tile -> (our tile, flip to apply)
    index = {}                                                  # pixels -> our tile number
    nxt = 8
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        nxt = (nxt + n - 1) & ~(n - 1)
        for k in range(n):
            slots[nxt + k] = g + k
            index.setdefault(tile_px(g + k).tobytes(), nxt + k)
        rom_of[('grp', g)] = nxt; nxt += n
    free = (k for k in range(1, 1 << 16) if k not in slots)
    def ours(t):
        if t in rom_of: return rom_of[t]
        px = tile_px(t)
        for f in range(4):                                      # t = flip(stored, f)  <=>  stored = flip(t, f)
            k = index.get(flip(px, f).tobytes())
            if k is not None: rom_of[t] = (k, f); return rom_of[t]
        k = next(free); slots[k] = t; index[px.tobytes()] = k; rom_of[t] = (k, 0)
        return rom_of[t]
    out = []
    for col in cells:
        for t, a in col:
            if t is None: out += [0, 0]; continue
            pn = STAGE_PAL + pals.index(u8(PTAB + t))
            if a & 12:
                n = 8 if a & 8 else 4; g = t & ~7 if (t & ~7) in groups and groups[t & ~7] == 8 else t & ~3
                base = rom_of[('grp', g)] + (t & ~(n - 1)) - g      # the group start (low bits: the counter's)
                out += [base, pn << 8 | a]
            else:
                k, f = ours(t); out += [k, pn << 8 | (a ^ f)]
    top = max(slots)
    assert top < BANNER_BASE, f'stage tiles up to {top}, room for {BANNER_BASE - 1}'
    for name, k in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        for n, t in slots.items(): data[n * 64:(n + 1) * 64] = tile_raw(t)[k]
        open(p, 'wb').write(bytes(data))
    pal_words = [w for n in pals for w in palette(n)]
    h = ['/* Generated by tools/brawler/make_stage_ra.py: Robo Army area 0 (the street), a prototype placeholder. Do not edit. */',
         '#ifndef STAGE_H', '#define STAGE_H',
         f'#define STAGE_COLS {COLS}', f'#define STAGE_ROWS {ROWS}', f'#define STAGE_Y {ROW0 * 16}   /* screen y of the top row */',
         f'#define STAGE_W {COLS * 16}',
         f'#define STAGE_PAL {STAGE_PAL}', f'#define STAGE_NPAL {len(pals)}   /* Robo Army palettes {", ".join(map(str, pals))} */',
         f'#define STAGE_BACKDROP 0x{BACKDROP:04X}   /* Robo Army\'s backdrop there (black) */',
         f'#define STAGE_LSPCMODE 0x{LSPCMODE:04X}   /* REG_LSPCMODE: auto-animation speed {LSPCMODE >> 8}, as Robo Army */',
         'static const uint16_t stage_pal[STAGE_NPAL * 16] = {' + ', '.join(f'0x{v:04X}' for v in pal_words) + '};',
         '/* SCB1 words {tile, attribute} per cell, column-major */',
         'static const uint16_t stage_map[STAGE_COLS * STAGE_ROWS * 2] = {' + ', '.join(map(str, out)) + '};',
         '#endif']
    open(os.path.join(outdir, 'stage.h'), 'w').write('\n'.join(h) + '\n')
    luts = {n: np.array([rgb(w) for w in palette(n)], np.uint8) for n in pals}
    mw = {}
    for i in range(COLS * ROWS):
        tw, aw = out[2 * i], out[2 * i + 1]; c, r = divmod(i, ROWS); mw[c, r] = (tw or None, aw)
    # preview: our map with our tiles, palette from the word
    img = np.zeros((ROWS * 16, COLS * 16, 3), np.uint8)
    for (c, r), (t, a) in mw.items():
        if t is None: continue
        px = flip(tile_px(slots[t]), a & 3); lut = luts[pals[(a >> 8) - STAGE_PAL]]
        m = px != 0; sub = img[r * 16:r * 16 + 16, c * 16:c * 16 + 16]; sub[m] = lut[px[m]]
    Image.fromarray(img).save(os.path.join(outdir, 'stage.png'))
    print(f'stage: Robo Army area 0, {COLS}x{ROWS} at y {ROW0 * 16}, {len(slots)} tiles up to {top} '
          f'({len([t for t in rom_of if not isinstance(t, tuple)])} static ROM tiles, anim groups {sorted(groups.items())}), '
          f'palettes {pals} -> {STAGE_PAL}-{STAGE_PAL + len(pals) - 1}')

if __name__ == '__main__':
    build(sys.argv[1])
