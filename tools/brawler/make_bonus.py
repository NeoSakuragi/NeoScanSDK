#!/usr/bin/env python3
"""The bonus stages' scenes (TODO T7, Bruno 2026-10-14: "the wooden prop from Art of Fighting 2 and the big tree also
from Art of Fighting 2 key training"): Art of Fighting 2's own sprite words, from the VRAM + palette RAM dumps of
tools/aof/bonus_rip.py (/data/neogeo_dict/aof/rip, taken in our emulator) and the C ROM of /data/roms/aof2.neo.

Two scenes, each a stage_t (stage.h's type: main.c draws it as a stage, the camera fixed) + its objects:
- tree  (Spirit Training): the forest (AOF2 sprites 11-31 at frame 500: 21 columns from screen x -6, the layer's rows
        that show), the big tree (sprites 49-59: 11 columns), the falling leaf (sprite 305.. at frame 800: tile $6DF0,
        palette 47), the punch mark on the bark (sprite 60, 5 x 1, frames 750 / 800).
- posts (Initiate Super Death Blow): the temple (sprites 1-20 at frame 510: 20 columns, screen x 0), the wooden post
        (sprites 21-24, 4 x 8 tiles: intact at 510, burnt by the super at 558 / 840 / 1116), its 6 splinter shapes
        (palette 59 chains at frames 558 / 1410).
Every word keeps AOF2's tile (bits 16-19 in the attribute's bits 4-7), flips and auto-animation bits; palettes are
renumbered BONUS_PAL + k per scene in AOF2's order (one scene loaded at a time: the stage's palette block, STAGE_PAL).
Tiles are appended after what bm_c1 / bm_c2.bin hold (after make_sparks.py), each AOF2 tile stored once (an
auto-animated group copied whole and aligned).

    python3 make_bonus.py OUTDIR    -> OUTDIR/bonus.h, bonus_<scene>.png (the scene as drawn from the build's tiles), patched bm_c*.bin"""
import os, struct, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'aof'))
from bonus_rip import sprites, OUT as RIP

NEO = '/data/roms/aof2.neo'
STAGE_PAL = 80                             # make_stage_ra.py: the stage's palette block (main.c stage_pals)

SCENES = {                                 # backdrop: (dump, first sprite, last sprite), world x of AOF2's screen x 0
    'tree': {'bg': ('spirit_500', 11, 31), 'cam': 6, 'floor': 206},
    'posts': {'bg': ('posts_510', 1, 20), 'cam': 0, 'floor': 206},
}
OBJECTS = {                                # name: scene, [(dump, first sprite, last sprite)] = its images
    'tree': ('tree', [('spirit_500', 49, 59)]),
    'leaf': ('tree', [('spirit_800', 305, 305), ('spirit_850', 306, 306)]),
    'mark': ('tree', [('spirit_750', 60, 64), ('spirit_800', 60, 64)]),
    'post': ('posts', [('posts_510', 21, 24), ('posts_558', 21, 24), ('posts_840', 21, 24), ('posts_1116', 21, 24)]),
    'piece': ('posts', [('posts_558', 264, 264), ('posts_558', 265, 265), ('posts_558', 268, 268), ('posts_558', 269, 270),
                        ('posts_1410', 277, 278), ('posts_1410', 281, 282)]),
}


def load_crom():
    d = open(NEO, 'rb').read()
    sz = struct.unpack('<6I', d[4:0x1C])
    return d[0x1000 + sum(sz[:5]):0x1000 + sum(sz)]


CROM = load_crom()


def tile_px(t):
    tt = CROM[t * 128:(t + 1) * 128]; c1, c2 = tt[0::2], tt[1::2]; px = np.zeros((16, 16), np.uint8)
    for half, x0 in ((0, 8), (1, 0)):
        for y in range(16):
            o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
            for x in range(8): px[y, x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
    return px


def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def group(aw):                             # auto-animation: the tile group size its attribute asks for
    return 8 if aw & 8 else 4 if aw & 4 else 1


def empty(t, aw):
    k = group(aw); b = t & ~(k - 1) if k > 1 else t
    return not any(tile_px(b + i).any() for i in range(k))


def dump(name):
    return open(f'{RIP}/{name}.vram', 'rb').read(), open(f'{RIP}/{name}.pal', 'rb').read()


def cols_of(name, lo, hi):
    """sprites lo..hi of a dump -> [(x, y, [(tile, attr)] rows as the screen shows them: a full-height (32) chain's rows
    wrapped and cut to screen y -16..239)]"""
    v, _ = dump(name)
    out = []
    for s in sprites(v):
        if not lo <= s['i'] <= hi: continue
        rows = s['tiles'][:s['h']]
        if s['h'] >= 32:                                   # a 512 px column: the rows that land on screen, from the top
            ys = [((s['y'] + 16 * r + 16) & 511) - 16 for r in range(32)]
            vis = sorted((y, r) for r, y in enumerate(ys) if -16 < y < 224)
            out.append((s['x'], vis[0][0], [rows[r] for _, r in vis]))
        else: out.append((s['x'], s['y'], rows))
    return out


def trim(cols):
    """an object's columns -> (x0, y0, w, h, [[(tile, attr)] per column]): empty rows / columns at the edges cut"""
    x0 = min(x for x, _, _ in cols); y0 = min(y for _, y, _ in cols)
    W = (max(x for x, _, _ in cols) - x0) // 16 + 1; H = max((y - y0) // 16 + len(r) for _, y, r in cols)
    grid = [[(0, 0)] * H for _ in range(W)]
    for x, y, rows in cols:
        for r, (t, a) in enumerate(rows):
            if not empty(t, a): grid[(x - x0) // 16][(y - y0) // 16 + r] = (t, a)
    used_r = [r for r in range(H) if any(grid[c][r][0] for c in range(W))]
    used_c = [c for c in range(W) if any(t for t, _ in grid[c])]
    r0, r1, c0, c1 = used_r[0], used_r[-1], used_c[0], used_c[-1]
    return x0 + 16 * c0, y0 + 16 * r0, c1 - c0 + 1, r1 - r0 + 1, [col[r0:r1 + 1] for col in grid[c0:c1 + 1]]


def build(outdir):
    c1p, c2p = os.path.join(outdir, 'bm_c1.bin'), os.path.join(outdir, 'bm_c2.bin')
    c1, c2 = bytearray(open(c1p, 'rb').read()), bytearray(open(c2p, 'rb').read())
    remap = {}
    def tile(t, aw):                                       # AOF2 tile -> ours (a group copied whole, aligned)
        if empty(t, aw): return 0
        k = group(aw); b = t & ~(k - 1) if k > 1 else t
        if b not in remap:
            while k > 1 and (len(c1) // 64) % k: c1.extend(bytes(64)); c2.extend(bytes(64))
            remap[b] = len(c1) // 64
            for i in range(k):
                tt = CROM[(b + i) * 128:(b + i + 1) * 128]; c1.extend(tt[0::2]); c2.extend(tt[1::2])
        return remap[b] + (t - b)
    h = ['/* Generated by tools/brawler/make_bonus.py (Art of Fighting 2\'s bonus scenes, /data/neogeo_dict/aof/rip). Do not edit. */',
         '#ifndef BONUS_H', '#define BONUS_H', '#include "stage.h"',
         '/* an object: w x h tiles, column-major (tile low word, attribute: palette BONUS_PAL-relative already placed, tile bits 16-19,',
         ' * flips, auto-animation); x, y = its top left on AOF2\'s screen (world x = x + the scene\'s cam) */',
         'typedef struct { int16_t x, y; uint8_t w, h; const uint16_t *map; } bonus_obj_t;',
         'typedef struct { stage_t st; int16_t cam; } bonus_scene_t;']
    scenes, objs = [], {}
    for si, (sn, sc) in enumerate(SCENES.items()):
        d, lo, hi = sc['bg']
        bg = cols_of(d, lo, hi)
        x0 = bg[0][0]; y0 = min(y for _, y, _ in bg); nr = max((y - y0) // 16 + len(r) for _, y, r in bg)
        assert all(x == x0 + 16 * i for i, (x, _, _) in enumerate(bg)), 'backdrop columns not contiguous'
        assert x0 == -sc['cam'], (sn, x0)
        words = [w for _, _, r in bg for w in r]
        mine = [(o, ims) for o, (scn, ims) in OBJECTS.items() if scn == sn]
        ob = {o: [trim(cols_of(dn, a, b)) for dn, a, b in ims] for o, ims in mine}
        words += [w for o in ob.values() for im in o for col in im[4] for w in col]
        pal_raw = dump(d)[1]
        pals = sorted({aw >> 8 for t, aw in words if t and not empty(t, aw)})
        assert STAGE_PAL + len(pals) <= 240, pals
        pw = lambda n: [struct.unpack('>H', pal_raw[(n * 16 + i) * 2:(n * 16 + i) * 2 + 2])[0] for i in range(16)]
        def word(t, aw):
            nt = tile(t, aw)
            if not nt: return (0, 0)
            return (nt & 0xFFFF, ((STAGE_PAL + pals.index(aw >> 8)) << 8) | ((nt >> 16) & 0xF) << 4 | (aw & 0xF))
        m = []
        for x, y, rows in bg:
            col = [(0, 0)] * nr
            for r, (t, aw) in enumerate(rows): col[(y - y0) // 16 + r] = word(t, aw)
            m += [v for w in col for v in w]
        h.append(f'static const uint16_t bonus_{sn}_map[] = {{ {", ".join(f"0x{v:04X}" for v in m)} }};')
        h.append(f'static const uint16_t bonus_{sn}_pal[] = {{ {", ".join(f"0x{v:04X}" for n in pals for v in pw(n))} }};   /* AOF2 palettes {pals} */')
        scenes.append(f'{{ {{ bonus_{sn}_map, bonus_{sn}_pal, {len(bg)}, {nr}, {len(pals)}, {y0}, {sc["floor"]}, 0x{pw(255)[15]:04X}, 0, 0, 0xFF, 0, 0, 0 }}, {sc["cam"]} }}')
        h.append(f'#define BONUS_{sn.upper()} {si}')
        for o, ims in ob.items():
            names = []
            for k, (ox, oy, w, hh, grid) in enumerate(ims):
                h.append(f'static const uint16_t bonus_{o}{k}[] = {{ {", ".join(f"0x{v:04X}" for col in grid for tw in col for v in word(*tw))} }};')
                names.append(f'{{ {ox}, {oy}, {w}, {hh}, bonus_{o}{k} }}')
            h.append(f'#define BONUS_N_{o.upper()} {len(ims)}')
            h.append(f'static const bonus_obj_t bonus_{o}[BONUS_N_{o.upper()}] = {{ {", ".join(names)} }};')
            objs[o] = ims
        # the scene as the build draws it (a check picture)
        img = Image.new('RGB', (320, 224), (0, 0, 0)); P = img.load()
        def put(sx, sy, t, aw):
            if not t: return
            px = tile_px(t)
            if aw & 1: px = px[:, ::-1]
            if aw & 2: px = px[::-1]
            pl = pw(aw >> 8)
            for yy in range(16):
                for xx in range(16):
                    c = int(px[yy, xx]); X, Y = sx + xx, sy + yy
                    if c and 0 <= X < 320 and 0 <= Y < 224: P[X, Y] = rgb(pl[c])
        for x, y, rows in bg:
            for r, (t, aw) in enumerate(rows): put(x, y + 16 * r, t, aw)
        for o, ims in ob.items():
            ox, oy, w, hh, grid = ims[0]
            for c, col in enumerate(grid):
                for r, (t, aw) in enumerate(col): put(ox + 16 * c, oy + 16 * r, t, aw)
        img.save(os.path.join(outdir, f'bonus_{sn}.png'))
    h.append(f'#define BONUS_SCENES {len(scenes)}')
    h.append('static const bonus_scene_t bonus_scenes[BONUS_SCENES] = {\n    ' + ',\n    '.join(scenes) + '\n};')
    h.append(f'#define BONUS_MAXROWS {max(len(c) for o in objs.values() for im in o for c in im[4])}')
    h.append('#endif')
    open(c1p, 'wb').write(bytes(c1)); open(c2p, 'wb').write(bytes(c2))
    open(os.path.join(outdir, 'bonus.h'), 'w').write('\n'.join(h) + '\n')
    print(f'bonus: {len(remap)} AOF2 tiles ({len(remap) * 128 // 1024} KB) appended, C ROM now {len(c1) // 64} tiles')


if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit(__doc__)
    build(sys.argv[1])
