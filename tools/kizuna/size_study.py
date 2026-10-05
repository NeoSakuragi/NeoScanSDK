#!/usr/bin/env python3
"""Kim's size problem, measured: the frames the brawler uses (every step of the export's moves and specials) under
three ways of showing him, against the brawler's sprite budget, plus a picture of each next to a KOF fighter.

    python3 size_study.py [BUILD_DIR] [OUT_DIR]   (default examples/brawler/build, /data/tmp/kizuna/out)

(a) full size: Kizuna's sprite definitions as they are (one hardware sprite per non-empty 16 px column of each part;
    tiles = the ROM tiles they use, mirrored by the parts' flip bits, so no copies);
(b) hardware shrink at Kizuna's own in-play zoom ($CC): the same sprites and tiles as (a), each drawn 13 px wide:
    the LSPC shrinks a sprite's pixels, not its count: a column is one sprite whatever its zoom;
(c) pre-scaled (the export, export_kz.py): Kizuna's renderer at $CC (LSPC pixel / line selection) baked into new tiles.
Sprites per frame = the brawler's line-guard count (fighter_t.ncols: all of a frame's columns, counted as one line),
the most on one scanline = columns that cover a common line. Budget per line (main.c line_guard): 96 - 21 (stage) -
16 (shadows) - 6 (sparks) = 53 for 8 fighters (2 players + 6 enemies)."""
import json, os, sys, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np, kz
from PIL import Image, ImageDraw

BUILD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'build')
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/kizuna/out'
BUDGET = 96 - 21 - 16 - 6

def full_cols(addr):
    """(a): columns, most on a line, ROM tiles of the step at full size"""
    s, _ = kz.parse_step(addr); cols = 0; lines = {}; tiles = set()
    for w, (dx, dy) in zip(s['defs'], s['offs']):
        d = kz.sdef(w)
        if not d: continue
        for col in d['cols']:
            rows = [r for r, c in enumerate(col) if c]
            if not rows: continue
            cols += 1
            for r in rows: tiles.add(col[r][0])
            for y in range(-dy + 16 * min(rows), -dy + 16 * (max(rows) + 1)): lines[y] = lines.get(y, 0) + 1
    return cols, max(lines.values(), default=0), tiles

def export_cols(fr):
    cols = sum(len(p['tiles']) for p in fr['parts']); lines = {}
    for p in fr['parts']:
        for col in p['tiles']:
            rows = [r for r, t in enumerate(col) if t]
            if not rows: continue
            for y in range(p['dy'] + 16 * min(rows), p['dy'] + 16 * (max(rows) + 1)): lines[y] = lines.get(y, 0) + 1
    return cols, max(lines.values(), default=0)

def render_export(ex, fi, tiles, pal_sets, set_=0):
    """an export frame drawn from its own tiles (facing left, as the brawler's ROM sprites)"""
    fr = ex['frames'][fi]; img = np.zeros((300, 300, 4), np.uint8)
    for p in fr['parts']:
        pal = pal_sets[set_][p.get('pal', 0)]
        for c, col in enumerate(p['tiles']):
            for r, t in enumerate(col):
                if not t: continue
                pen = kz_tile(tiles, t)
                if p.get('hflip'): pen = pen[:, ::-1]
                y, x = 260 + p['dy'] + 16 * r, 150 + p['dx'] + 16 * c
                for yy in range(16):
                    for xx in range(16):
                        if pen[yy, xx] and 0 <= y + yy < 300 and 0 <= x + xx < 300:
                            img[y + yy, x + xx] = kz.color(pal[pen[yy, xx]]) + (255,)
    return Image.fromarray(img, 'RGBA')

def kz_tile(region, code):
    b = np.frombuffer(region, np.uint8, 128, code * 128).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    return np.concatenate([pen[1], pen[0]], axis=1)

def load_export(name, game):
    d = os.path.join(BUILD, f'tmp_{game}_{name}')
    ex = json.load(open(os.path.join(d, 'kof95_export.json')))
    c1 = open(os.path.join(d, 'kof95_c1.bin'), 'rb').read(); c2 = open(os.path.join(d, 'kof95_c2.bin'), 'rb').read()
    reg = bytearray(len(c1) * 2); reg[0::2] = c1; reg[1::2] = c2
    return ex, bytes(reg)

def main():
    os.makedirs(OUT, exist_ok=True)
    ex, reg = load_export('kim', 'kizuna'); ch = ex['characters']['kim']
    used = sorted({int(f['record'], 16) for f in ch['frames']})
    A = [full_cols(a) for a in used]
    C = [export_cols(f) for f in ch['frames']]
    full_tiles = set().union(*[a[2] for a in A])
    res = {'frames': len(used),
           'full': {'cols_median': statistics.median(a[0] for a in A), 'cols_max': max(a[0] for a in A),
                    'line_max': max(a[1] for a in A), 'tiles': len(full_tiles), 'bytes': 128 * len(full_tiles)},
           'shrink_CC': {'cols_median': statistics.median(a[0] for a in A), 'cols_max': max(a[0] for a in A),
                         'line_max': max(a[1] for a in A), 'tiles': len(full_tiles), 'bytes': 128 * len(full_tiles),
                         'note': 'same sprites and tiles as full size; each column drawn 12-13 px wide'},
           'prescaled_CC': {'cols_median': statistics.median(c[0] for c in C), 'cols_max': max(c[0] for c in C),
                            'line_max': max(c[1] for c in C), 'tiles': ex['tiles'], 'bytes': 128 * ex['tiles']}}
    # KOF fighters of the roster for reference (their exports, as the brawler packs them)
    ref = {}
    for nm, g in (('terry', 'kof98'), ('kyo', 'kof98'), ('krauser', 'kof96'), ('hanzo', 'whp'), ('haohmaru', 'samsho4')):
        try:
            e, _ = load_export(nm, g); c = e['characters'][nm]
            cs = [export_cols(f) for f in c['frames']]
            ref[nm] = {'cols_median': statistics.median(x[0] for x in cs), 'cols_max': max(x[0] for x in cs), 'tiles': e['tiles']}
        except FileNotFoundError: pass
    res['roster_reference'] = ref
    res['budget_per_line'] = BUDGET
    for k in ('full', 'shrink_CC', 'prescaled_CC'):
        r = res[k]; r['eight_kims_median'] = 8 * r['cols_median']; r['eight_kims_worst'] = 8 * r['cols_max']
    json.dump(res, open(os.path.join(OUT, 'size_study.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1))
    # the picture: Terry (KOF98, the brawler's export) | Kim full size | Kim at Kizuna's zoom $CC (hardware shrink =
    # the pre-scaled export, pixel for pixel) - idle, each facing left as in the brawler, the floor line under them
    te, treg = load_export('terry', 'kof98'); tc = te['characters']['terry']
    terry = render_export(tc, tc['anims']['idle']['steps'][0]['frame'], treg, tc['block_palettes'])
    kim_c = render_export(ch, ch['anims']['idle']['steps'][0]['frame'], reg, ch['block_palettes'])
    a0 = ch['anims']['idle']['steps'][0]['kz_step']
    full = np.zeros((300, 300), np.uint16); kz.render_step_zoom(full, a0, 150, 260, 0xFF); full = full[:, ::-1]
    pal = [0] * 4096
    for k, p in enumerate(ch['modes']['palettes']): pal[int(p, 16) * 16:int(p, 16) * 16 + 16] = ch['block_palettes'][0][k]
    rgb = kz.colorize(full, pal); kim_a = Image.fromarray(np.dstack([rgb, np.where(full > 0, 255, 0).astype(np.uint8)]), 'RGBA')
    sheet = Image.new('RGB', (900, 330), 'white'); d = ImageDraw.Draw(sheet)
    for i, (im, lab) in enumerate(((terry, 'KOF98 Terry (brawler)'), (kim_a, 'Kim full size (a)'),
                                   (kim_c, 'Kim at $CC: (b) = (c) pixels'))):
        sheet.paste(im, (i * 300, 20), im); d.rectangle([i * 300, 0, i * 300 + 299, 329], outline='black')
        d.line([i * 300 + 10, 280, i * 300 + 290, 280], fill='black'); d.text((i * 300 + 6, 4), lab, fill='black')
    sheet.save(os.path.join(OUT, 'size_compare.png'))

if __name__ == '__main__':
    main()
