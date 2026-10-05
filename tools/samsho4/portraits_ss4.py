#!/usr/bin/env python3
"""Haohmaru's portraits in Samurai Shodown IV, read from the screens that show them (VRAM + palette RAM dumped by our
emulator, emu/neogeo_sdl --capture VRAMDUMP / PALDUMP, during the boot of tools/samsho4 captures): every portrait is
made of sprites (the fix layer holds only text there). Per portrait: the sprite slots inside its rectangle, their
tiles and attributes (SCB1), the palettes they use, a PNG in its own colours (transparent where no sprite pixel),
a JSON with the raw data, all into /data/neogeo_dict/portraits/ (samsho4_haohmaru_<kind>.png / .json) and the
HUD-size square (28x28, the select face scaled) the brawler's make_hud.py takes as samsho4_haohmaru_square.png.

    python3 portraits_ss4.py DUMPDIR        (DUMPDIR: vram<f>.bin, pal<f>.bin of the boot capture, see PORTRAITS)

Found (2026-10-05): 'select' the character-select face (48x48, a 3x3 tile block in the 4x4 grid; frame 830 of the
boot), 'technique' the Slash / Bust choice art (the big upper body, ~112x160, P1's on the left; frame 990). Not found
in this pass: in-fight HUD faces (SS4's fight HUD has none: names only), win-quote / story / ending portraits (they
need a won match / the ending: not captured)."""
import json, os, sys, numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import neo

OUT = '/data/neogeo_dict/portraits'
# kind: (dump frame, screen rectangle x0, y0, x1, y1, where the game shows it)
# kind: (dump frame, search rectangle, the palettes of its cells (the rest of the screen's sprites in the rectangle:
# grid background, cursors, the SLASH caption), where the game shows it); the PNG is cropped to the portrait's pixels
PORTRAITS = {'select': (830, 160, 56, 240, 136, {79}, 'character select grid, the Haohmaru square'),
             'technique': (990, 0, 24, 176, 224, {128, 129}, 'CHOICE TECHNIQUE screen (Slash / Bust), P1 side: the fighter palettes $80 / $81')}

def slots_in(v, rect):
    """sprite slots (full-size chains) whose drawn rectangle overlaps rect -> [(slot, x, y, rows)]"""
    x0, y0, x1, y1 = rect; out = []; sx = sy = sh = 0
    for s in range(381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx += 16
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if not sh: continue
        top = (496 - sy) & 0x1FF; top = top - 512 if top > 300 else top
        rows = min(sh, 32)
        if sx < x1 and sx + 16 > x0 and top < y1 and top + rows * 16 > y0: out.append((s, sx, top, rows))
    return out

def main(d):
    os.makedirs(OUT, exist_ok=True)
    for kind, (f, x0, y0, x1, y1, keep, where) in PORTRAITS.items():
        v = list(neo.vram_words(f'{d}/vram{f}.bin')); pal = neo.pal_bank(f'{d}/pal{f}.bin', 1)
        sl = slots_in(v, (x0, y0, x1, y1))
        for s, *_ in sl:                                   # cells of other palettes: tile 0 (not drawn)
            for r in range(32):
                if v[s * 64 + 2 * r + 1] >> 8 not in keep: v[s * 64 + 2 * r] = 0; v[s * 64 + 2 * r + 1] &= 0xFF00
        sl = [t for t in sl if any(v[t[0] * 64 + 2 * r] for r in range(t[3]))]
        if not any(pal): pal = neo.pal_bank(f'{d}/pal{f}.bin', 0)
        a, _ = neo.render_vram(v, pal, {s for s, *_ in sl}, bg=(0, 0, 0))
        b, _ = neo.render_vram(v, pal, {s for s, *_ in sl}, bg=(255, 0, 255))
        rgba = np.dstack([a, np.where((a == b).all(axis=2), 255, 0).astype(np.uint8)])[y0:y1, x0:x1]
        ys, xs = np.nonzero(rgba[..., 3]); bx0, by0 = int(xs.min()), int(ys.min())
        rgba = rgba[by0:ys.max() + 1, bx0:xs.max() + 1]; x0 += bx0; y0 += by0; y1, x1 = y0 + rgba.shape[0], x0 + rgba.shape[1]
        Image.fromarray(rgba, 'RGBA').save(f'{OUT}/samsho4_haohmaru_{kind}.png')
        tiles = [{'slot': s, 'x': int(x - x0), 'y': int(y - y0),
                  'cells': [[v[s * 64 + 2 * r] | (v[s * 64 + 2 * r + 1] >> 4 & 0xF) << 16, v[s * 64 + 2 * r + 1]] for r in range(rows)]}
                 for s, x, y, rows in sl]
        pals = sorted({c[1] >> 8 for t in tiles for c in t['cells'] if c[0]})
        json.dump({'game': 'samsho4', 'name': 'haohmaru', 'kind': kind, 'where': where, 'frame': f, 'rect': [int(x0), int(y0), int(x1), int(y1)],
                   'size': [int(x1 - x0), int(y1 - y0)], 'sprites': tiles,
                   'palettes': {str(p): list(pal[p * 16:p * 16 + 16]) for p in pals}},
                  open(f'{OUT}/samsho4_haohmaru_{kind}.json', 'w'))
        print(kind, len(sl), 'sprites, palettes', pals, '->', f'{OUT}/samsho4_haohmaru_{kind}.png')
    sel = Image.open(f'{OUT}/samsho4_haohmaru_select.png').convert('RGBA')
    sq = sel.crop((8, 4, 44, 40)).resize((28, 28), Image.LANCZOS)          # the face, scaled to the HUD's 28x28 core
    bg = Image.new('RGBA', sq.size, (24, 40, 104, 255)); bg.alpha_composite(sq)
    bg.save(f'{OUT}/samsho4_haohmaru_square.png')

if __name__ == '__main__':
    main(sys.argv[1])
