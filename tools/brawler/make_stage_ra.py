#!/usr/bin/env python3
"""Placeholder brawler stages: Robo Army's horizontal parts (areas 0, 1, 2's boss arena, 3, 4, 6's street), extracted
from /data/roms/roboarmy.neo (prototype art only; the final game gets its own). One plane each, as Robo Army shows it:
band row 0 at screen y 0, scrolling 1:1 with the camera (Robo Army has no parallax). The vertical parts (area 2's climb,
area 5): docs/brawler_stage_vertical.md.

ROM format (decoded 2026-10-04, /data/neogeo_dict/roboarmy/README.md + tools/extract_roboarmy.py): map data $531F2,
16-px columns of 16 tile words (32 bytes), a map id = 16 columns; tile word bits 0-12 C ROM tile, bit 13 H flip, bits
14-15 -> SCB1 auto-animation bits 2-3 (bit 14: 4 frames, bit 15: 8 frames); palette = byte $5C1F2 + tile; palette n at
$313F4 + n*32. Tile $3FF is Robo Army's blank (no pixels): our empty tile 0. Robo Army's tile 0 is a real tile. Rows
0-1 are blank in every stage (Robo Army's black backdrop, behind the HUD), rows 14-15 are below the screen: 12 rows
from screen y 32 (computed per stage).

Auto-animation (the LSPC replaces the low 2 / 3 bits of an animated tile's number by its counter): every group of 4 / 8
tiles an animated word names is copied whole to an aligned place, its words keep the flag. Robo Army's speed: REG_LSPCMODE
= $104016 << 8 = $0800 in every scene, written by the runtime with the stage (stage_t.lspcmode).

Tiles: one pool for all stages, stored once (a tile that is a flipped copy of a stored one points to it with the flip
folded into the map word): tiles 1 .. BANNER_BASE - 1 first, then after the fighters (the end of export_bm.py's
bm_c1/bm_c2.bin, which grow); each map word carries its tile bits 16-19 (attribute bits 4-7). Palettes: per stage,
STAGE_PAL + k in the order of Robo Army's palette numbers, loaded when the stage starts (one stage in use at a time).

    python3 make_stage_ra.py OUTDIR      (after export_bm.py OUTDIR ...)  -> stage.h, stage<n>.png, patched bm_c*.bin"""
import os, struct, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_banner import BANNER_BASE

ROM = '/data/roms/roboarmy.neo'
MAP, PTAB, PALS = 0x531F2, 0x5C1F2, 0x313F4
BLANK = 0x3FF
SCREEN_ROWS = 14                           # rows 0-13 = screen y 0-223 (Robo Army's horizontal scenes: scroll y 0)
STAGE_PAL = 80                             # main.c: 0 text, 1 free, 2-15 fix portraits, 16-79 fighters (8 x MAX_PALS)
LSPCMODE = 0x0800                          # Robo Army's auto-animation speed (8; $104016 = 8 in all 14 scenes, measured)
BACKDROP = 0x0000                          # Robo Army's backdrop (palette RAM $401FFE, measured in all 14 scenes): black
# The horizontal parts (/data/neogeo_dict/roboarmy/README.md; scene table $7624, area bases $6506): (Robo Army area, first
# map id, columns, floor top). An id = 16 columns.
# - area 2's street part is the boss arena after the climb (scene 5, ids $1F-$20; Robo Army's camera stays at ring x 192,
#   its left 12 columns are never shown there); area 5 is vertical only (docs/brawler_stage_vertical.md).
# - area 6: the street is the first 100 columns (ids $3B-$41, scene 12 = its last screen); after 12 blank columns the
#   data holds the final boss and ending screens, not a street.
# floor top: the screen y of the feet at Z = 0, measured on the art, the walkable band FLOOR_TOP .. FLOOR_TOP + 64 on the
# floor (Robo Army's own band: feet y 170-222 in every horizontal scene, measured): street solid from y 160 (area 0),
# road from 160 under a curb 156-159 (1), floor from 157-158 (3, 4 left, 6). Areas 2 (arena) and 4's right half: the
# floor below y 152 / 165 is water (Robo Army's walkers stand in that band too).
STAGES = [(0, 0x00, 160, 158), (1, 0x0A, 160, 158), (2, 0x1F, 32, 158), (3, 0x21, 160, 158), (4, 0x2B, 160, 158),
          (6, 0x3B, 100, 158)]
# The vertical parts (docs/brawler_stage_vertical.md, measured): descents played as transitions between stages (game.json
# stages[].transition, main.c "transition"): (Robo Army area, first map id, 256-px bands, camera y start, camera y end).
# A band = 2 map ids (32 columns); only columns 0-19 (320 px) are ever on screen. Area 2: bands 0-4 (ids $14-$1D), its
# camera from y ~40 to 960; area 5: bands 0-2 (ids $35-$3A), y ~40 to 528. Each transition shows only the descent's last
# part: the whole of both costs 1039 new tiles (133 KB), past the 16 MB C ROM size step (8 MB a chip, 436 tiles free in
# 0.0.44: neobuild pads to a power of two, so 32 MB); area 2 from y 600 to 880 (above the shaft's floor: the fallers
# drop out of the screen's bottom) and area 5 from y 240 to its end: 355 tiles (45 KB).
VSECTIONS = [(2, 0x14, 5, 600, 880), (5, 0x35, 3, 240, 528)]
VCOLS = 20

def vsect_cells(vs):
    """a descent's rows the camera shows, row-major: (cells[row][col], first row)"""
    area, i0, bands, y0, y1 = vs
    r0, r1 = y0 >> 4, (y1 + 223) >> 4
    assert r1 < bands * 16
    return [[rom_cell(i0 + 2 * (r >> 4), c, r & 15) for c in range(VCOLS)] for r in range(r0, r1 + 1)], r0

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

def word(c, r, id0=0): return u16(MAP + id0 * 512 + c * 32 + r * 2)

def flip(px, f):
    if f & 1: px = px[:, ::-1]
    if f & 2: px = px[::-1]
    return px

def rom_cell(id0, c, r):                   # Robo Army's own word, as its LSPC draws it: (tile, SCB1 attribute bits 0-3)
    w = word(c, r, id0); t = w & 0x1FFF
    return (None, 0) if t == BLANK else (t, (1 if w & 0x2000 else 0) | (w >> 14) << 2)

def stage_cells(st):
    """the stage's screen rows: (cells[col][row], first row); rows above the first row with a tile are backdrop"""
    area, i0, cols, _ = st
    cells = [[rom_cell(i0, c, r) for r in range(SCREEN_ROWS)] for c in range(cols)]
    r0 = min(r for col in cells for r, (t, a) in enumerate(col) if t is not None)
    return [col[r0:] for col in cells], r0

def render_rom(st, anim=0):
    """the stage as Robo Army's LSPC shows it (straight from its map words and palettes), auto-animation counter anim;
    None where nothing is drawn (backdrop)"""
    cells, r0 = stage_cells(st); rows = len(cells[0])
    img = np.zeros((SCREEN_ROWS * 16, len(cells) * 16, 3), np.int16); img[:] = -1
    for c, col in enumerate(cells):
        for r, (t, a) in enumerate(col):
            if t is None: continue
            pn = u8(PTAB + t)
            if a & 8: t = (t & ~7) | (anim & 7)
            elif a & 4: t = (t & ~3) | (anim & 3)
            px = flip(tile_px(t), a & 3); lut = np.array([rgb(w) for w in palette(pn)], np.int16)
            m = px != 0; y = (r0 + r) * 16; sub = img[y:y + 16, c * 16:c * 16 + 16]; sub[m] = lut[px[m]]
    return img

def build(outdir):
    c1p = os.path.join(outdir, 'bm_c1.bin'); hi0 = len(open(c1p, 'rb').read()) // 64   # the fighters' end (export_bm.py)
    # One tile pool for every stage (a tile shared by two stages is stored once): tiles 1 .. BANNER_BASE - 1 first, then
    # after the fighters. A map word carries its own tile bits 16-19 (attribute bits 4-7), so the pool may cross pages.
    slots = {}                                                  # our tile number -> Robo Army tile (raw copy)
    rom_of = {}                                                 # Robo Army tile -> (our tile, flip to apply); ('grp', g) -> base
    index = {}                                                  # pixels -> our tile number
    free = {'lo': 1, 'hi': hi0}
    def alloc(n):                                               # n consecutive tiles aligned on n (n = 1, 4 or 8)
        for reg, end in (('lo', BANNER_BASE), ('hi', 1 << 20)):
            k = (free[reg] + n - 1) & ~(n - 1)
            if reg == 'hi':
                while (k & 0xFFFF) == 0: k += n                 # low 16 bits 0 = our empty tile: never a stage tile
            if k + n <= end:
                free[reg] = k + n; return k
        raise SystemExit('C ROM: no room for stage tiles')
    def ours(t):
        if t in rom_of: return rom_of[t]
        px = tile_px(t)
        for f in range(4):                                      # t = flip(stored, f)  <=>  stored = flip(t, f)
            k = index.get(flip(px, f).tobytes())
            if k is not None: rom_of[t] = (k, f); return rom_of[t]
        k = alloc(1); slots[k] = t; index[px.tobytes()] = k; rom_of[t] = (k, 0)
        return rom_of[t]
    h = ['/* Generated by tools/brawler/make_stage_ra.py: Robo Army\'s horizontal parts, prototype placeholders. Do not edit. */',
         '#ifndef STAGE_H', '#define STAGE_H', f'#define STAGE_PAL {STAGE_PAL}',
         '/* a stage: SCB1 words {tile bits 0-15, attribute} per cell, column-major, rows from screen y y; palettes',
         ' * STAGE_PAL .. + npal - 1; floor_top = screen y of the feet at Z = 0; REG_LSPCMODE value (auto-animation speed) */',
         'typedef struct { const uint16_t *map, *pal; uint16_t cols; uint8_t rows, npal; int16_t y, floor_top; uint16_t backdrop, lspcmode; } stage_t;']
    def encode(cells, pals):
        """SCB1 word pairs of a list of cells (Robo Army tile, attribute); palettes STAGE_PAL + pals.index"""
        # animated groups (the LSPC replaces the low 2 / 3 bits): copied whole, aligned; 4-groups inside an 8-group share it
        groups = {}
        for t, a in cells:
            if t is not None and a & 12: n_ = 8 if a & 8 else 4; groups[t & ~(n_ - 1)] = max(groups.get(t & ~(n_ - 1), 0), n_)
        for g, k in list(groups.items()):
            if k == 4 and groups.get(g & ~7) == 8: del groups[g]
        for g, k in sorted(groups.items(), key=lambda kv: -kv[1]):
            if ('grp', g) in rom_of: assert rom_of[('grp', g)][1] >= k; continue
            base = alloc(8 if k == 8 else 4)
            for j in range(k): slots[base + j] = g + j; index.setdefault(tile_px(g + j).tobytes(), base + j)
            rom_of[('grp', g)] = (base, k)
        out = []
        for t, a in cells:
            if t is None: out += [0, 0]; continue
            pn = STAGE_PAL + pals.index(u8(PTAB + t))
            if a & 12:
                k = 8 if a & 8 else 4; g = t & ~7 if groups.get(t & ~7) == 8 else t & ~3
                tn = rom_of[('grp', g)][0] + (t & ~(k - 1)) - g; f = 0      # the group start (low bits: the counter's)
            else:
                tn, f = ours(t)
            out += [tn & 0xFFFF, pn << 8 | (tn >> 16) << 4 | (a ^ f)]
        return out
    table, info, maxpal, maxrows = [], [], 0, 0
    for n, st in enumerate(STAGES):
        area, i0, cols, floor = st
        cells, r0 = stage_cells(st); rows = len(cells[0])
        pals = sorted({u8(PTAB + t) for col in cells for t, a in col if t is not None})
        assert STAGE_PAL + len(pals) <= 250, pals                 # 250+: banner, shadows, debug, sparks (main.c)
        assert cols < 255 and floor + 64 <= 222
        out = encode([c for col in cells for c in col], pals)
        pal_words = [w for p in pals for w in palette(p)]
        h.append(f'/* stage {n}: Robo Army area {area}, ids ${i0:02X}-${i0 + (cols - 1) // 16:02X}, {cols} columns ({cols * 16} px), rows {r0}-{r0 + rows - 1}, '
                 f'palettes {", ".join(map(str, pals))} */')
        h.append(f'static const uint16_t stage{n}_pal[{len(pal_words)}] = {{' + ', '.join(f'0x{v:04X}' for v in pal_words) + '};')
        h.append(f'static const uint16_t stage{n}_map[{len(out)}] = {{' + ', '.join(map(str, out)) + '};')
        table.append(f'{{stage{n}_map, stage{n}_pal, {cols}, {rows}, {len(pals)}, {r0 * 16}, {floor}, 0x{BACKDROP:04X}, 0x{LSPCMODE:04X}}}')
        maxpal, maxrows = max(maxpal, len(pals)), max(maxrows, rows)
        info.append((n, area, cols * 16, rows, r0, len(pals), floor, out))
    n_stage_tiles = len(slots); vtab, vinfo = [], []
    for n, vs in enumerate(VSECTIONS):
        area, i0, bands, y0, y1 = vs
        cells, r0 = vsect_cells(vs); rows = len(cells)
        pals = sorted({u8(PTAB + t) for row in cells for t, a in row if t is not None})
        assert STAGE_PAL + len(pals) <= 250 and rows < 256, pals
        out = encode([c for row in cells for c in row], pals)
        pal_words = [w for p in pals for w in palette(p)]
        h.append(f'/* descent {n}: Robo Army area {area}, ids ${i0:02X}-${i0 + 2 * bands - 1:02X}, rows {r0}-{r0 + rows - 1} x {VCOLS} '
                 f'columns (row-major), camera {y0}-{y1}, palettes {", ".join(map(str, pals))} */')
        h.append(f'static const uint16_t vsect{n}_pal[{len(pal_words)}] = {{' + ', '.join(f'0x{v:04X}' for v in pal_words) + '};')
        h.append(f'static const uint16_t vsect{n}_map[{len(out)}] = {{' + ', '.join(map(str, out)) + '};')
        vtab.append(f'{{vsect{n}_map, vsect{n}_pal, {VCOLS}, {rows}, {len(pals)}, {y0 - r0 * 16}, {y1 - r0 * 16}, 0x{BACKDROP:04X}, 0x{LSPCMODE:04X}}}')
        vinfo.append((n, area, rows, r0, pals, out))
    # tiles into the C ROM image (grown past the fighters as needed)
    for name, k in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        data += bytes(max(0, free['hi'] * 64 - len(data)))
        for t, rt in slots.items(): data[t * 64:(t + 1) * 64] = tile_raw(rt)[k]
        open(p, 'wb').write(bytes(data))
    h += [f'#define STAGE_COUNT {len(STAGES)}', f'#define STAGE_MAXPAL {maxpal}', f'#define STAGE_MAXROWS {maxrows}',
          'static const stage_t stages[STAGE_COUNT] = {' + ', '.join(table) + '};',
          '/* the descents (transitions, main.c): the same stage_t, map row-major (rows x cols), y / floor_top = the camera\'s',
          ' * start / end y from the map\'s first row */',
          f'#define VSECT_COUNT {len(VSECTIONS)}', 'static const stage_t vsects[VSECT_COUNT] = {' + ', '.join(vtab) + '};', '#endif']
    open(os.path.join(outdir, 'stage.h'), 'w').write('\n'.join(h) + '\n')
    # previews: our words, our tiles (as stored in the image), our palettes
    for n, area, w, rows, r0, npal, floor, out in info:
        pals = sorted({u8(PTAB + t) for col in stage_cells(STAGES[n])[0] for t, a in col if t is not None})
        luts = [np.array([rgb(v) for v in palette(p)], np.uint8) for p in pals]
        img = np.zeros((SCREEN_ROWS * 16, w, 3), np.uint8)
        for i in range(0, len(out), 2):
            tn, aw = out[i] | ((out[i + 1] >> 4) & 15) << 16, out[i + 1]
            if not out[i]: continue
            c, r = divmod(i // 2, rows); px = flip(tile_px(slots[tn]), aw & 3); lut = luts[(aw >> 8) - STAGE_PAL]
            m = px != 0; y = (r0 + r) * 16; sub = img[y:y + 16, c * 16:c * 16 + 16]; sub[m] = lut[px[m]]
        Image.fromarray(img).save(os.path.join(outdir, f'stage{n}.png'))
    for n, area, rows, r0, pals, out in vinfo:
        luts = [np.array([rgb(v) for v in palette(p)], np.uint8) for p in pals]
        img = np.zeros((rows * 16, VCOLS * 16, 3), np.uint8)
        for i in range(0, len(out), 2):
            tn, aw = out[i] | ((out[i + 1] >> 4) & 15) << 16, out[i + 1]
            if not out[i]: continue
            r, c = divmod(i // 2, VCOLS); px = flip(tile_px(slots[tn]), aw & 3); lut = luts[(aw >> 8) - STAGE_PAL]
            m = px != 0; sub = img[r * 16:r * 16 + 16, c * 16:c * 16 + 16]; sub[m] = lut[px[m]]
        Image.fromarray(img).save(os.path.join(outdir, f'vsect{n}.png'))
        used = {out[i] | ((out[i + 1] >> 4) & 15) << 16 for i in range(0, len(out), 2) if out[i]}
        print(f'  descent {n}: area {area}, rows {r0}-{r0 + rows - 1}, {len(used)} tile numbers, {len(pals)} palettes')
    print(f'descents: {len(slots) - n_stage_tiles} new tiles ({(len(slots) - n_stage_tiles) * 128} bytes of C ROM)')
    lo = [t for t in slots if t < BANNER_BASE]; hi = [t for t in slots if t >= BANNER_BASE]
    print(f'stages: {len(STAGES)}, {len(slots)} tiles: {len(lo)} in 1-{free["lo"] - 1}, {len(hi)} in {hi0}-{free["hi"] - 1} '
          f'(C ROM {hi0 * 128} -> {free["hi"] * 128} bytes)')
    for n, area, w, rows, r0, npal, floor, out in info:
        used = {out[i] | ((out[i + 1] >> 4) & 15) << 16 for i in range(0, len(out), 2) if out[i]}
        print(f'  stage {n}: area {area}, {w} px, rows {r0}-{r0 + rows - 1}, {len(used)} tile numbers, {npal} palettes, floor {floor}')

if __name__ == '__main__':
    build(sys.argv[1])
