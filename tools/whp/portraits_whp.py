#!/usr/bin/env python3
"""Hanzou's portraits in World Heroes Perfect, read from the screens that show them (VRAM + palette RAM dumped by our
emulator, emu/neogeo_sdl --capture VRAMDUMP / PALDUMP, during one boot): every portrait is made of sprites. Per portrait:
the sprite slots inside its rectangle with a cell in its palettes, a PNG in its own colours (transparent where no sprite
pixel), a JSON with the raw data (tiles, attributes, palettes), all into /data/neogeo_dict/portraits/ (whp_hanzo_<kind>
.png / .json), and the HUD-size square (28x28, the fight HUD face) make_hud.py takes as whp_hanzo_square.png.

    python3 portraits_whp.py [DUMPDIR]          (default /data/tmp/whp/portraits: the boot capture is made there)

Found (2026-10-05): 'select' the character-select face (the grid, drawn in his fighter palette $10; boot frame 1300),
'vs' the big art shown after the pick (his upper body with the kunai, P1's left side; frame 1400), 'hud' the fight HUD
face (20 x 20, top left, palette $10; frame 1700). The square is the select face scaled to 28 x 28."""
import json, os, sys, subprocess, numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import neo_whp as neo

OUT = '/data/neogeo_dict/portraits'
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
# kind: (dump frame, search rectangle x0, y0, x1, y1, its palettes (None: every palette but the excluded ones), excluded
# palettes (the grid's frame, the 1P cursor, the VS letters...), where the game shows it)
PORTRAITS = {'select': (1300, 120, 50, 176, 100, {0x10}, set(), "character select grid, Hanzou's face (his fighter palette $10)"),
             'vs': (1400, 0, 40, 150, 224, {0x60, 0x62}, set(), 'after the pick: his big art over the select screen, P1 side (palettes $60, $62)'),
             'hud': (1700, 0, 0, 60, 40, {0x10}, set(), 'fight HUD, P1 face (top left, palette $10)')}

def rle(lane):
    runs = []
    for x in lane:
        if runs and runs[-1][1] == x: runs[-1][0] += 1
        else: runs.append([1, x])
    return ','.join(f'{n}:{x}' for n, x in runs)

def boot(d):
    """coins 600 / 650, starts 720 / 760, P1's A at 901 (ends the how-to-play demo: the select screen is up at 1300),
    A on both sides every 20 frames from 1301 (P1 = Hanzou, P2 = Fuuma: the cursors' defaults)"""
    n = 2400; p1, p2 = ['-'] * n, ['-'] * n
    for f in range(600, 606): p1[f] = 'o'
    for f in range(650, 656): p2[f] = 'o'
    for f in range(720, 726): p1[f] = 's'
    for f in range(760, 766): p2[f] = 's'
    for f in range(901, 904): p1[f] = 'a'                 # skips the how-to-play demo: the select screen
    for f in range(1301, 1500):
        if f % 20 < 3: p1[f] = p2[f] = 'a'
    fr = sorted({v[0] for v in PORTRAITS.values()})
    os.makedirs(d, exist_ok=True)
    env = dict(os.environ, SEQ=rle(p1), SEQ2=rle(p2), OUT=f'{d}/boot.txt',
               VRAMDUMP=';'.join(f'{f}:{d}/vram{f}.bin' for f in fr), PALDUMP=';'.join(f'{f}:{d}/pal{f}.bin' for f in fr),
               SNAPS=','.join(map(str, fr)), SNAPDIR=d)
    subprocess.run([NGSDL, neo.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)

def main(d):
    if not os.path.exists(f'{d}/vram{PORTRAITS["hud"][0]}.bin'): boot(d)
    os.makedirs(OUT, exist_ok=True)
    for kind, (f, x0, y0, x1, y1, keep, drop, where) in PORTRAITS.items():
        v = list(neo.vram_words(f'{d}/vram{f}.bin'))
        pal = neo.pal_bank(f'{d}/pal{f}.bin', 1)
        if not any(pal[16:]): pal = neo.pal_bank(f'{d}/pal{f}.bin', 0)
        sl = []
        for s, sx, top, sh, s2 in neo.chains(v):
            if not sh: continue
            top = top - 512 if top > 300 else top
            if sx < x1 and sx + 16 > x0 and top < y1 and top + min(sh, 32) * 16 > y0: sl.append((s, sx, top, min(sh, 32)))
        for s, *_ in sl:                                   # cells of other palettes: tile 0 (not drawn)
            for r in range(32):
                p = v[s * 64 + 2 * r + 1] >> 8
                if (keep is not None and p not in keep) or p in drop: v[s * 64 + 2 * r] = 0; v[s * 64 + 2 * r + 1] &= 0xFF00
        sl = [t for t in sl if any(v[t[0] * 64 + 2 * r] for r in range(t[3]))]
        img, _ = neo.vram_index(v, slots={s for s, *_ in sl})
        img = img[y0:y1, x0:x1]
        rgb = neo.colorize(img, pal)
        rgba = np.dstack([rgb, np.where(img > 0, 255, 0).astype(np.uint8)])
        ys, xs = np.nonzero(img); bx0, by0 = int(xs.min()), int(ys.min())
        rgba = rgba[by0:ys.max() + 1, bx0:xs.max() + 1]; X0, Y0 = x0 + bx0, y0 + by0
        Image.fromarray(rgba, 'RGBA').save(f'{OUT}/whp_hanzo_{kind}.png')
        tiles = [{'slot': s, 'x': int(x - X0), 'y': int(y - Y0),
                  'cells': [[v[s * 64 + 2 * r] | (v[s * 64 + 2 * r + 1] >> 4 & 0xF) << 16, v[s * 64 + 2 * r + 1]] for r in range(rows)]}
                 for s, x, y, rows in sl]
        pals = sorted({c[1] >> 8 for t in tiles for c in t['cells'] if c[0]})
        json.dump({'game': 'whp', 'name': 'hanzo', 'kind': kind, 'where': where, 'frame': f,
                   'rect': [X0, Y0, X0 + rgba.shape[1], Y0 + rgba.shape[0]], 'size': [rgba.shape[1], rgba.shape[0]],
                   'sprites': tiles, 'palettes': {str(p): list(pal[p * 16:p * 16 + 16]) for p in pals}},
                  open(f'{OUT}/whp_hanzo_{kind}.json', 'w'))
        print(kind, len(sl), 'sprites, palettes', [hex(p) for p in pals], rgba.shape[1], 'x', rgba.shape[0], '->', f'{OUT}/whp_hanzo_{kind}.png')
    hud = Image.open(f'{OUT}/whp_hanzo_select.png').convert('RGBA')
    w, h = hud.size; c = min(w, h)
    sq = hud.crop(((w - c) // 2, (h - c) // 2, (w - c) // 2 + c, (h - c) // 2 + c)).resize((28, 28), Image.LANCZOS)
    bg = Image.new('RGBA', sq.size, (24, 40, 104, 255)); bg.alpha_composite(sq)
    bg.save(f'{OUT}/whp_hanzo_square.png')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/whp/portraits')
