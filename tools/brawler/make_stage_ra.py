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
import functools, os, struct, sys
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

def palette(n, area=None):
    """palette n as Robo Army's palette RAM holds it in that area: the global table ($313F4), then the area's load lists
    on top (area_lists), a cycled palette at its cycle's first step (cycles); area None: the table alone"""
    p = [u16(PALS + n * 32 + 2 * k) for k in range(16)]
    if area is None: return p
    for l in area_lists(area): p = plist(l).get(n, p)
    for ps, seq in cycles():
        if n in ps: p = plist(seq[0][0])[n]
    return p

# Palette lists (TODO #159, read from Robo Army's code 2026-10-06): pointer table $30000[i] -> 16-word records, word 0 =
# the palette number (bit 15 ends the list), copied into palette RAM by $6002 (list index $10402C). Robo Army's area
# load ($756A) sets them over the global table: area 0 list 27; any other area a (7 = 1) lists a - 1, a + 8 (area 6:
# a + 7), 8. Area 1's palettes 32 / 33 (the animated sky block, columns 36-38 / 57-59) and area 4's 179 / 180 come from
# them; measured in our emulator (Robo Army scene 2 walked to x 688, palette RAM) and in every capture of
# /data/neogeo_dict/roboarmy/ver: every palette a stage uses equals this rule, except the cycled ones below.
PLISTS = 0x30000
@functools.lru_cache(None)
def plist(i):
    a = struct.unpack_from('>I', P, PLISTS + 4 * i)[0]; out = {}
    while not u16(a) & 0x8000:
        out[u16(a)] = [u16(a + 2 * k) for k in range(16)]; a += 32
    return out
def area_lists(area):
    if area == 0: return [27]
    a = 1 if area == 7 else area
    return [a - 1, a + 7 if area == 6 else a + 8, 8]
# Palette cycles ($6568, every frame): cycle id $10407A (set by the area scripts, $85D6) -> $65CE[id - 1] -> a list of
# (palette list, frames) words ending $FFFF, played in a loop: 1 = lists 18 / 19 x 10 frames (palette 196, area 1's
# columns 0-7 and 132-139), 2 = 20 / 21 x 12 (222), 3 = 22 / 23 / 24 x 16 (240, area 6). Robo Army runs a cycle while
# its art is on screen (its script starts / stops it); the brawler cycles it all the time (stage_t.cyc, main.c
# stage_cycle): the same picture wherever it is seen.
CYCLES = 0x65CE
@functools.lru_cache(None)
def cycles():
    """[(palette numbers, [(list, frames)])] for each of Robo Army's palette cycles"""
    out = []
    for k in range(3):
        a = struct.unpack_from('>I', P, CYCLES + 4 * k)[0]; seq = []
        while u16(a) != 0xFFFF: seq.append((u16(a), u16(a + 2))); a += 4
        out.append((set().union(*[plist(l) for l, _ in seq]), seq))
    return out

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
    """the stage as Robo Army's LSPC shows it (straight from its map words and its area's palettes, cycles at their first
    step), auto-animation counter anim; None where nothing is drawn (backdrop)"""
    cells, r0 = stage_cells(st); rows = len(cells[0])
    img = np.zeros((SCREEN_ROWS * 16, len(cells) * 16, 3), np.int16); img[:] = -1
    for c, col in enumerate(cells):
        for r, (t, a) in enumerate(col):
            if t is None: continue
            pn = u8(PTAB + t)
            if a & 8: t = (t & ~7) | (anim & 7)
            elif a & 4: t = (t & ~3) | (anim & 3)
            px = flip(tile_px(t), a & 3); lut = np.array([rgb(w) for w in palette(pn, st[0])], np.int16)
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
         'typedef struct { const uint16_t *map, *pal; uint16_t cols; uint8_t rows, npal; int16_t y, floor_top; uint16_t backdrop, lspcmode; const uint16_t *cyc; uint8_t cyc_pal, cyc_n, cyc_ticks, cyc_pad; } stage_t;   /* cyc: a palette cycle (Robo Army $6568): palette STAGE_PAL + cyc_pal steps through cyc_n palettes of cyc, cyc_ticks frames each (cyc_pal 0xFF: none) */']
    table, info, maxpal, maxrows = [], [], 0, 0
    for n, st in enumerate(STAGES):
        area, i0, cols, floor = st
        cells, r0 = stage_cells(st); rows = len(cells[0])
        pals = sorted({u8(PTAB + t) for col in cells for t, a in col if t is not None})
        assert STAGE_PAL + len(pals) <= 250, pals                 # 250+: banner, shadows, debug, sparks (main.c)
        assert cols < 255 and floor + 64 <= 222
        # animated groups (the LSPC replaces the low 2 / 3 bits): copied whole, aligned; 4-groups inside an 8-group share it
        groups = {}
        for col in cells:
            for t, a in col:
                if t is not None and a & 12: n_ = 8 if a & 8 else 4; groups[t & ~(n_ - 1)] = max(groups.get(t & ~(n_ - 1), 0), n_)
        for g, k in list(groups.items()):
            if k == 4 and groups.get(g & ~7) == 8: del groups[g]
        for g, k in sorted(groups.items(), key=lambda kv: -kv[1]):
            if ('grp', g) in rom_of: assert rom_of[('grp', g)][1] >= k; continue
            base = alloc(8 if k == 8 else 4)
            for j in range(k): slots[base + j] = g + j; index.setdefault(tile_px(g + j).tobytes(), base + j)
            rom_of[('grp', g)] = (base, k)
        out = []
        for col in cells:
            for t, a in col:
                if t is None: out += [0, 0]; continue
                pn = STAGE_PAL + pals.index(u8(PTAB + t))
                if a & 12:
                    k = 8 if a & 8 else 4; g = t & ~7 if groups.get(t & ~7) == 8 else t & ~3
                    tn = rom_of[('grp', g)][0] + (t & ~(k - 1)) - g; f = 0      # the group start (low bits: the counter's)
                else:
                    tn, f = ours(t)
                out += [tn & 0xFFFF, pn << 8 | (tn >> 16) << 4 | (a ^ f)]
        pal_words = [w for p in pals for w in palette(p, area)]
        cyc = [(p, seq) for ps, seq in cycles() for p in pals if p in ps]   # a cycled palette: its steps, the first
        assert len(cyc) <= 1, cyc                                           # loaded with the others
        cyc_words, cyc_info = [], '0, 0xFF, 0, 0'
        if cyc:
            p, seq = cyc[0]; k = pals.index(p); steps = [plist(l)[p] for l, _ in seq]
            assert len({t for _, t in seq}) == 1
            cyc_words = [w for st_ in steps for w in st_]
            h.append(f'static const uint16_t stage{n}_cyc[{len(cyc_words)}] = {{' + ', '.join(f'0x{v:04X}' for v in cyc_words) + '};')
            cyc_info = f'stage{n}_cyc, {k}, {len(steps)}, {seq[0][1]}'
        h.append(f'/* stage {n}: Robo Army area {area}, ids ${i0:02X}-${i0 + (cols - 1) // 16:02X}, {cols} columns ({cols * 16} px), rows {r0}-{r0 + rows - 1}, '
                 f'palettes {", ".join(map(str, pals))} */')
        h.append(f'static const uint16_t stage{n}_pal[{len(pal_words)}] = {{' + ', '.join(f'0x{v:04X}' for v in pal_words) + '};')
        h.append(f'static const uint16_t stage{n}_map[{len(out)}] = {{' + ', '.join(map(str, out)) + '};')
        table.append(f'{{stage{n}_map, stage{n}_pal, {cols}, {rows}, {len(pals)}, {r0 * 16}, {floor}, 0x{BACKDROP:04X}, 0x{LSPCMODE:04X}, {cyc_info}}}')
        maxpal, maxrows = max(maxpal, len(pals)), max(maxrows, rows)
        info.append((n, area, cols * 16, rows, r0, len(pals), floor, out))
    # tiles into the C ROM image (grown past the fighters as needed)
    for name, k in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        data += bytes(max(0, free['hi'] * 64 - len(data)))
        for t, rt in slots.items(): data[t * 64:(t + 1) * 64] = tile_raw(rt)[k]
        open(p, 'wb').write(bytes(data))
    h += [f'#define STAGE_COUNT {len(STAGES)}', f'#define STAGE_MAXPAL {maxpal}', f'#define STAGE_MAXROWS {maxrows}',
          'static const stage_t stages[STAGE_COUNT] = {' + ', '.join(table) + '};', '#endif']
    open(os.path.join(outdir, 'stage.h'), 'w').write('\n'.join(h) + '\n')
    # previews: our words, our tiles (as stored in the image), our palettes
    for n, area, w, rows, r0, npal, floor, out in info:
        pals = sorted({u8(PTAB + t) for col in stage_cells(STAGES[n])[0] for t, a in col if t is not None})
        luts = [np.array([rgb(v) for v in palette(p, area)], np.uint8) for p in pals]
        img = np.zeros((SCREEN_ROWS * 16, w, 3), np.uint8)
        for i in range(0, len(out), 2):
            tn, aw = out[i] | ((out[i + 1] >> 4) & 15) << 16, out[i + 1]
            if not out[i]: continue
            c, r = divmod(i // 2, rows); px = flip(tile_px(slots[tn]), aw & 3); lut = luts[(aw >> 8) - STAGE_PAL]
            m = px != 0; y = (r0 + r) * 16; sub = img[y:y + 16, c * 16:c * 16 + 16]; sub[m] = lut[px[m]]
        Image.fromarray(img).save(os.path.join(outdir, f'stage{n}.png'))
    lo = [t for t in slots if t < BANNER_BASE]; hi = [t for t in slots if t >= BANNER_BASE]
    print(f'stages: {len(STAGES)}, {len(slots)} tiles: {len(lo)} in 1-{free["lo"] - 1}, {len(hi)} in {hi0}-{free["hi"] - 1} '
          f'(C ROM {hi0 * 128} -> {free["hi"] * 128} bytes)')
    for n, area, w, rows, r0, npal, floor, out in info:
        used = {out[i] | ((out[i + 1] >> 4) & 15) << 16 for i in range(0, len(out), 2) if out[i]}
        print(f'  stage {n}: area {area}, {w} px, rows {r0}-{r0 + rows - 1}, {len(used)} tile numbers, {npal} palettes, floor {floor}')

if __name__ == '__main__':
    build(sys.argv[1])
