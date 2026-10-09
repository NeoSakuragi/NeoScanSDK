#!/usr/bin/env python3
"""The select screen's backdrop: KOF95's stage 2, the Esaka street in front of SNK's Neo Geo Land (the Japan team's
stage), rebuilt from SNK's own sprite words with its layers, scroll speeds and animations (no flattening, SNK's colours).

Source (extracted 2026-10-09 in our emulator, /data/neogeo_dict/kof95/stages/README.md): tools/stage2_columns.pkl =
every world column's VRAM words per layer (stage95.py collect), tools/stage2_palram.bin = the fight's palette RAM
(bank 1: SNK's palettes 176-239), the C ROM of /data/roms/kof95.neo.

Layers, back to front (main.c "the select screen's backdrop"):
- top (far skyline): only its world columns 32-39 have pixels that can show (through the main layer's gap at the top
  right); a sprite each, scroll 64 + 5/7 camera. Row 0 (screen y -16) never shows: dropped.
- lights: the 6 x 2 tile chain at far x 512, screen y 88, 4 images of 18 / 20 / 18 / 20 frames, each drawn every other
  frame (SNK's 30 Hz flicker).
- main (the Neo Geo Land facade, the karaoke building, the street): 48 columns, 1:1 with the camera.
- mid (the crowd): 48 columns from screen y 72, 1:1.
- front (rope barriers, barricades, grating): 60 columns from screen y 168, 10/7 camera, drawn over the fighters.
Each column keeps only its rows from its first to its last non-empty tile inside the screen (y 0-223) (first, n): a
sprite counts on a line only inside its height. Auto-animated words keep their bits (bit 2: 4 frames, bit 3: 8 frames;
KOF95's counter steps every 8 frames: REG_LSPCMODE $0700).

Tiles: appended after what bm_c1/bm_c2.bin hold (export_bm.py, make_stage_ra.py), stored once (a tile that is a flipped
copy of a stored one points to it with the flip folded into the word), every animated group copied whole and aligned;
a word carries its tile bits 16-19 (attribute bits 4-7). Palettes: SNK's in number order at LAND_PAL .. LAND_PAL +
LAND_NPAL - 1 = the top of the block below KOF's shared effects bank (fighter.h SFX_PAL 224); the select screen's actors
take theirs from 16 (main.c static assert).

    python3 make_stage_land.py OUTDIR   (after make_stage_ra.py OUTDIR) -> land.h, land.json (the Lab), land_cam*.png, patched bm_c*.bin"""
import json, os, pickle, struct, sys
import numpy as np
from PIL import Image

SRC = '/data/neogeo_dict/kof95/stages'
NEO = '/data/roms/kof95.neo'
SFX_PAL = 224                              # fighter.h: KOF's shared effects bank, the land's palettes end below it
LSPCMODE = 0x0700                          # KOF95's auto-animation: the counter steps every 8 frames (measured)
BACKDROP = 0x0000                          # KOF95 stage 2's backdrop ($401FFE): black
CAM_MAX = 448                              # the camera's range on the main layer (768 - 320)
LIGHTS_TIMES = (18, 20, 18, 20)            # each image's frames (the 76-frame cycle, README "Animation")
LAYERS = {                                 # name: (screen y of the sprite's row 0, first source row kept)
    'top': (0, 1), 'main': (0, 1), 'mid': (72, 0), 'front': (168, 0)}
TOP_COLS = range(32, 40)                   # the far layer's columns that can show (README: content at x 512-640)


def load_crom():
    d = open(NEO, 'rb').read()
    sz = struct.unpack('<6I', d[4:0x1C])
    return d[0x1000 + sum(sz[:5]):0x1000 + sum(sz)]


CROM = load_crom()


def tile_raw(t):                           # .neo C ROM: c1 / c2 bytes interleaved, 128 bytes a tile
    tt = CROM[t * 128:(t + 1) * 128]
    return tt[0::2], tt[1::2]


_px = {}
def tile_px(t):
    if t in _px: return _px[t]
    c1, c2 = tile_raw(t); px = np.zeros((16, 16), np.uint8)
    for half, x0 in ((0, 8), (1, 0)):
        for y in range(16):
            o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
            for x in range(8):
                px[y, x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
    _px[t] = px
    return px


def flip(px, f):
    if f & 1: px = px[:, ::-1]
    if f & 2: px = px[::-1]
    return px


def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def snk_tile(tw, aw): return tw | ((aw >> 4) & 0xF) << 16


def empty(tw, aw):                         # no pixels in any frame of it
    t = snk_tile(tw, aw)
    k = 8 if aw & 8 else 4 if aw & 4 else 1
    return not any(tile_px((t & ~(k - 1)) + i if k > 1 else t).any() for i in range(k))


def build(outdir):
    C = pickle.load(open(f'{SRC}/tools/stage2_columns.pkl', 'rb'))
    pw = np.frombuffer(open(f'{SRC}/tools/stage2_palram.bin', 'rb').read(), dtype='>u2').astype(np.int64)
    snkpal = lambda n: [int(w) for w in pw[4096 + n * 16:4096 + n * 16 + 16]]   # bank 1
    # ---- the layers' columns: (first, rows) of SNK's words, trimmed to the rows that show and hold pixels
    layers = {}
    for name, (y, r0) in LAYERS.items():
        cols = C['cols'][name]; ncols = max(cols) + 1
        out = []
        for c in range(ncols):
            if name == 'top' and c not in TOP_COLS: continue
            if c not in cols: out.append((0, [])); continue
            sy, h, dw = cols[c]
            assert ((sy + 16) & 511) - 16 == y - 16 * r0, (name, c, sy)
            rows = [(dw[2 * r], dw[2 * r + 1]) for r in range(r0, h) if y + 16 * (r - r0) < 224]
            keep = [r for r, (tw, aw) in enumerate(rows) if not empty(tw, aw)]
            out.append((keep[0], rows[keep[0]:keep[-1] + 1]) if keep else (0, []))
        layers[name] = out
    (ox, oy, oh), = C['objpos']
    assert (ox, oy, oh) == (512, 88, 2)
    lights = [None] * len(C['objs'])
    for dw, k in C['objs'].items():
        lights[k] = [[(dw[c * 2 * oh + 2 * r], dw[c * 2 * oh + 2 * r + 1]) for r in range(oh)] for c in range(6)]
    # ---- palettes: every one a kept word uses, in SNK's order
    words = [w for L in layers.values() for _, col in L for w in col] + [w for im in lights for col in im for w in col]
    pals = sorted({aw >> 8 for tw, aw in words if not empty(tw, aw)})
    npal = len(pals); LAND_PAL = SFX_PAL - npal
    # ---- the tile pool, after what the C ROM holds
    c1p = os.path.join(outdir, 'bm_c1.bin'); base0 = len(open(c1p, 'rb').read()) // 64
    free = [base0]
    slots = {}                                                  # our tile -> SNK tile
    index, ours_of, grp = {}, {}, {}
    def alloc(n):
        k = (free[0] + n - 1) & ~(n - 1)
        while (k & 0xFFFF) == 0: k += n                         # low 16 bits 0 = our empty tile word
        free[0] = k + n
        return k
    def ours(t):
        if t in ours_of: return ours_of[t]
        px = tile_px(t)
        for f in range(4):
            k = index.get(flip(px, f).tobytes())
            if k is not None: ours_of[t] = (k, f); return ours_of[t]
        k = alloc(1); slots[k] = t; index[px.tobytes()] = k; ours_of[t] = (k, 0)
        return ours_of[t]
    groups = {}                                                 # animated groups: SNK base -> 4 / 8
    for tw, aw in words:
        if aw & 12 and not empty(tw, aw):
            n = 8 if aw & 8 else 4; g = snk_tile(tw, aw) & ~(n - 1); groups[g] = max(groups.get(g, 0), n)
    for g, k in list(groups.items()):
        if k == 4 and groups.get(g & ~7) == 8: del groups[g]
    for g, k in sorted(groups.items(), key=lambda kv: (-kv[1], kv[0])):
        b = alloc(k)
        for j in range(k): slots[b + j] = g + j
        grp[g] = (b, k)
    def word(tw, aw):
        if empty(tw, aw): return [0, 0]
        t = snk_tile(tw, aw); pn = LAND_PAL + pals.index(aw >> 8)
        if aw & 12:
            k = 8 if aw & 8 else 4; g = t & ~7 if grp.get(t & ~7, (0, 0))[1] == 8 else t & ~3
            tn = grp[g][0] + (t & ~(k - 1)) - g; f = 0
        else:
            tn, f = ours(t)
        return [tn & 0xFFFF, pn << 8 | (tn >> 16) << 4 | (aw & 12) | ((aw & 3) ^ f)]
    # ---- land.h
    h = ['/* Generated by tools/brawler/make_stage_land.py: KOF95 stage 2 (Esaka, in front of SNK\'s Neo Geo Land), the',
         ' * select screen\'s backdrop, SNK\'s sprite words re-tiled into our C ROM. Do not edit. */',
         '#ifndef LAND_H', '#define LAND_H',
         f'#define LAND_PAL {LAND_PAL}', f'#define LAND_NPAL {npal}             /* SNK\'s palettes {pals[0]}-{pals[-1]} in order */',
         f'#define LAND_LSPCMODE 0x{LSPCMODE:04X}', f'#define LAND_BACKDROP 0x{BACKDROP:04X}', f'#define LAND_CAM_MAX {CAM_MAX}',
         f'#define LAND_W {CAM_MAX + 320}',
         '/* a layer: cols columns, column c = its words from w + off[c] (n[c] rows from screen y y + first[c] * 16, two words',
         ' * a row: SCB1 tile bits 0-15, attribute); x0 = the world x of its column 0 */',
         'typedef struct { const uint16_t *w, *off; const uint8_t *first, *n; uint8_t cols; int16_t y, x0; } land_layer_t;',
         'static const uint16_t land_pal[LAND_NPAL * 16] = {' + ', '.join(f'0x{v:04X}' for p in pals for v in snkpal(p)) + '};']
    tab = []
    for name, L in layers.items():
        y = LAYERS[name][0]
        w, off, first, n = [], [], [], []
        for f0, col in L:
            off.append(len(w)); first.append(f0); n.append(len(col))
            for tw, aw in col: w += word(tw, aw)
        h.append(f'static const uint16_t land_{name}_w[{len(w)}] = {{' + ', '.join(map(str, w)) + '};')
        h.append(f'static const uint16_t land_{name}_off[{len(off)}] = {{' + ', '.join(map(str, off)) + '};')
        h.append(f'static const uint8_t land_{name}_first[{len(first)}] = {{' + ', '.join(map(str, first)) + '};')
        h.append(f'static const uint8_t land_{name}_n[{len(n)}] = {{' + ', '.join(map(str, n)) + '};')
        x0 = TOP_COLS[0] * 16 if name == 'top' else 0
        h.append(f'#define LAND_{name.upper()}_COLS {len(L)}')
        h.append(f'static const land_layer_t land_{name} = {{ land_{name}_w, land_{name}_off, land_{name}_first, land_{name}_n, {len(L)}, {y}, {x0} }};')
        tab.append((name, len(L), sum(n)))
    lw = []
    for im in lights:
        for col in im:
            for tw, aw in col: lw += word(tw, aw)
    h += [f'#define LAND_LIGHTS_X {ox}            /* far-layer x, screen y, 6 columns x 2 rows, 4 images */',
          f'#define LAND_LIGHTS_Y {oy}', '#define LAND_LIGHTS_COLS 6', f'#define LAND_LIGHTS_ROWS {oh}', f'#define LAND_LIGHTS_N {len(lights)}',
          f'static const uint16_t land_lights[LAND_LIGHTS_N][LAND_LIGHTS_COLS * LAND_LIGHTS_ROWS * 2] = {{' +
          ', '.join('{' + ', '.join(map(str, lw[i * 24:(i + 1) * 24])) + '}' for i in range(len(lights))) + '};',
          'static const uint8_t land_lights_t[LAND_LIGHTS_N] = {' + ', '.join(map(str, LIGHTS_TIMES)) + '};   /* each image\'s frames */',
          '#endif']
    open(os.path.join(outdir, 'land.h'), 'w').write('\n'.join(h) + '\n')
    for name, k in (('bm_c1.bin', 0), ('bm_c2.bin', 1)):
        p = os.path.join(outdir, name); data = bytearray(open(p, 'rb').read())
        assert len(data) == base0 * 64
        data += bytes(free[0] * 64 - len(data))
        for t, st in slots.items(): data[t * 64:(t + 1) * 64] = tile_raw(st)[k]
        open(p, 'wb').write(bytes(data))
    # ---- previews from our words, our tiles (as stored), our palettes: the screen at cameras 0 / 224 / 448
    P = {LAND_PAL + i: np.array([rgb(v) for v in snkpal(p)], np.float64) for i, p in enumerate(pals)}
    def ourpx(t0, aw, cnt):
        t = t0 | ((aw >> 4) & 15) << 16
        if aw & 8: t = (t & ~7) | (cnt & 7)
        elif aw & 4: t = (t & ~3) | (cnt & 3)
        return flip(tile_px(slots[t]), aw & 3)
    def blit(img, x, y, t0, aw, alpha=1.0, cnt=0):
        if not t0 and not aw: return
        px = ourpx(t0, aw, cnt); lut = P[aw >> 8]
        for yy in range(16):
            for xx in range(16):
                X, Y = x + xx, y + yy
                if px[yy, xx] and 0 <= X < 320 and 0 <= Y < 224:
                    img[Y, X] = img[Y, X] * (1 - alpha) + lut[px[yy, xx]] * alpha
    def scroll(c): return 64 + (c * 731 >> 10), (c * 1463 + 512) >> 10
    def lay(name, img, sc):
        y = LAYERS[name][0]; L = layers[name]; x0 = TOP_COLS[0] * 16 if name == 'top' else 0
        for c, (f0, col) in enumerate(L):
            X = x0 + c * 16 - sc
            if X <= -16 or X >= 320: continue
            for r, (tw, aw) in enumerate(col):
                blit(img, X, y + 16 * (f0 + r), *word(tw, aw))
    for cam in (0, 224, CAM_MAX):
        img = np.zeros((224, 320, 3)); img[:] = rgb(BACKDROP)
        st, sf = scroll(cam)
        lay('top', img, st)
        for c in range(6):
            for r in range(oh): blit(img, ox + c * 16 - st, oy + 16 * r, *word(*lights[0][c][r]), alpha=0.5)
        lay('main', img, cam); lay('mid', img, cam); lay('front', img, sf)
        Image.fromarray(img.round().astype(np.uint8)).save(os.path.join(outdir, f'land_cam{cam:03d}.png'))
    # ---- land.json for the Lab's Select screen tab (chainlab/select_images.py -> selectrender.js): each layer as palette
    # indices (local palette * 16 + pen, 0 = transparent; little-endian uint16, base64) at auto-animation counter 0, its
    # world x / screen y, its columns' trims (the per-line count), the lights' first image, SNK's palette words
    import base64
    def idx_img(cols, x0, y, rows_max):
        W = len(cols) * 16; Hh = rows_max * 16; img = np.zeros((Hh, W), np.uint16)
        for c, (f0, col) in enumerate(cols):
            for r, (tw, aw) in enumerate(col):
                t0, a = word(tw, aw)
                if not t0 and not a: continue
                px = ourpx(t0, a, 0).astype(np.uint16); m = px != 0
                yy = 16 * (f0 + r); sub = img[yy:yy + 16, c * 16:c * 16 + 16]; sub[m] = ((a >> 8) - LAND_PAL) * 16 + px[m]
        return {'x0': x0, 'y': y, 'w': W, 'h': Hh, 'pix': base64.b64encode(img.astype('<u2').tobytes()).decode(),
                'cols': [[f0, len(col)] for f0, col in cols]}
    LJ = {'pals': [v for p in pals for v in snkpal(p)], 'w': CAM_MAX + 320, 'cam_max': CAM_MAX, 'backdrop': BACKDROP, 'layers': {}}
    for name in layers:
        y = LAYERS[name][0]; rmax = max(f0 + len(col) for f0, col in layers[name])
        LJ['layers'][name] = idx_img(layers[name], TOP_COLS[0] * 16 if name == 'top' else 0, y, rmax)
    LJ['layers']['lights'] = idx_img([(0, lights[0][c]) for c in range(6)], ox, oy, oh)
    json.dump(LJ, open(os.path.join(outdir, 'land.json'), 'w'))
    print(f'land: {npal} palettes ({LAND_PAL}-{LAND_PAL + npal - 1}), {len(slots)} tiles {base0}-{free[0] - 1} '
          f'(C ROM +{(free[0] - base0) * 128} bytes), ' + ', '.join(f'{n} {c} columns / {k} cells' for n, c, k in tab))


if __name__ == '__main__':
    build(sys.argv[1])
