#!/usr/bin/env python3
"""Brawler HUD on the fix layer, patched into the S ROM after the ASCII font, and hud.h:

1. Life bar glyphs in the style of KOF94's (studied from its S ROM in a demo fight): one 8 px row, white outline,
   dark shadow line, a yellow-to-orange vertical gradient, rounded caps, 1 px steps; plus a red damage trail (KOF94 has
   none). Cells: left cap, middle, right cap; each with f px yellow from the left (0-8; caps 0-7: the cap's first
   column is the outline) and the rest empty (black) or trail (red). Tile = BAR_TILE + kind * 18 + rest * 9 + f.
   BAR_TILE_R + the same index = the glyph mirrored: a right-hand bar keeps its life at its outer (right) edge, so both
   bars empty from the middle of the screen toward the outside, as in a fighting game.
   Colours = fix palette 0 entries 6-15 (main.c TEXT_PAL keeps 0-5 for text).
2. Fighter portraits: each roster fighter's HUD portrait from its game (tools/brawler/portraits.py, PNGs in
   /data/neogeo_dict/portraits; KOF96's boss team: their member-select squares, <game>_<name>_square.png, portraits.py
   select96), its 28x28 face core (other KOF96: centred on the face, its tan band repainted: band96) in
   one shared 2 px frame = 32x32, 15 colours, 16 fix tiles
   (row-major) from PORTRAIT_TILE + i * 16; colours portrait_pal[i], loaded into fix palette 2 + HUD side when shown (main.c portrait()).

    python3 make_hud.py OUTDIR kof98:terry ...        (after font_encoder.py wrote OUTDIR/font.s1)  -> hud.h"""
import os, sys
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_stage import neo_colour

PORTRAITS = '/data/neogeo_dict/portraits/'
CROP = {'kof98': (2, 1), 'kof99': (2, 0), 'kof96': (6, 4), 'kof94': (2, 0), 'kof97': (2, 2)}      # top-left of the 28x28 face core per game
FACE_BG = (24, 40, 104)
KOF98_BG = (0, 0, 255)                     # the blue behind KOF98's HUD faces (their portrait palettes)
BAR_TILE, BAR_TILE_R, PORTRAIT_TILE = 0x80, 0xB6, 0x100   # BAR_TILE_R: the same glyphs mirrored (right-hand bars)
# palette 0, entries 6-15: bar gradient (rows 1-5), trail gradient, empty, outline shadow
BAR_PAL = {6: (255, 255, 200), 7: (255, 240, 96), 8: (255, 208, 40), 9: (255, 168, 24), 10: (232, 120, 16),
           11: (255, 96, 96), 12: (224, 32, 32), 13: (152, 16, 16), 14: (8, 8, 8), 15: (64, 64, 80)}
WHITE = 1                                   # TEXT_PAL[1]
YEL = [6, 7, 8, 9, 10]; RED = [11, 11, 12, 12, 13]; EMPTY = 14; SHADOW = 15

ARROW_TILE = 0x7F                            # a down arrow: white, a shadow outline (TEXT_PAL 1 / 15)
ARROW = [[{'.': 0, 'w': WHITE, 's': SHADOW}[ch] for ch in row] for row in (
    '..www...', '..www...', '..www...', 'wwwwwww.', '.wwwww..', '..www...', '...w....', '........')]

def stile(px):
    """8x8 colour indices -> 32-byte S ROM tile"""
    t = bytearray(32)
    for cl, cr, base in ((4, 5, 0), (6, 7, 8), (0, 1, 16), (2, 3, 24)):
        for y in range(8): t[base + y] = (px[y][cr] << 4) | px[y][cl]
    return bytes(t)

def bar_glyph(kind, f, rest):
    """kind 0 left cap, 1 middle, 2 right cap; f px yellow from the left; rest 0 empty, 1 trail"""
    px = [[0] * 8 for _ in range(8)]
    for x in range(8):
        cap_l, cap_r = kind == 0 and x == 0, kind == 2 and x == 7
        if cap_l or cap_r:                                      # rounded end: vertical outline, no corners
            for y in range(1, 6): px[y][x] = WHITE
            px[6][x] = SHADOW
            continue
        px[0][x] = WHITE; px[6][x] = WHITE; px[7][x] = SHADOW
        filled = (x - (1 if kind == 0 else 0)) < f
        for y in range(1, 6): px[y][x] = YEL[y - 1] if filled else (RED[y - 1] if rest else EMPTY)
    return px

def band96(src):
    """KOF96's HUD portrait: the face over a tan parallelogram (48x48). The band's colours = the indices right of the
    face (x >= 34, only band there); its pixels = the 4-connected region of those colours reached from there. -> the
    set of band pixels (they become background) and the 28x28 window: centred on the rest (the face), from its top"""
    px = src.load(); W, H = src.size
    cols = {px[x, y] for x in range(34, W) for y in range(H)} - {0}
    seen, todo = set(), [(x, y) for x in range(34, W) for y in range(H) if px[x, y] in cols]
    while todo:
        x, y = todo.pop()
        if (x, y) in seen or not (0 <= x < W and 0 <= y < H) or px[x, y] not in cols: continue
        seen.add((x, y)); todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    face = [(x, y) for x in range(W) for y in range(H) if px[x, y] and (x, y) not in seen]
    xs, ys = [p[0] for p in face], [p[1] for p in face]
    x0 = max(0, min(W - 28, (min(xs) + max(xs)) // 2 - 14)); y0 = max(0, min(H - 28, min(ys) - 1))
    return seen, (x0, y0)

def portrait(game, name):
    sq = f'{PORTRAITS}{game}_{name}_square.png'       # a select-screen square (portraits.py select96): 28x28 as is
    if os.path.exists(sq): return frame28(Image.open(sq).convert('RGBA'))
    src = Image.open(f'{PORTRAITS}{game}_{name}.png'); rgba = src.convert('RGBA'); idx = src.load()
    band, crop = band96(src) if game == 'kof96' else (set(), CROP[game])   # KOF96: its band repainted, face centred
    for y in range(src.height):
        for x in range(src.width):
            if (x, y) in band or (game == 'kof96' and idx[x, y] == 0):
                rgba.putpixel((x, y), KOF98_BG + (255,))           # KOF96: band + black field in KOF98's portrait blue
            elif idx[x, y] == 0: rgba.putpixel((x, y), FACE_BG + (255,))
    x0, y0 = crop
    return frame28(rgba.crop((x0, y0, x0 + 28, y0 + 28)))

def frame28(face):
    """28x28 face -> 32x32 in the shared frame, 15 colours"""
    out = Image.new('RGB', (32, 32)); d = ImageDraw.Draw(out)
    d.rectangle([0, 0, 31, 31], outline=(255, 255, 255)); d.rectangle([1, 1, 30, 30], outline=(0, 0, 0))
    out.paste(face.convert('RGB'), (2, 2))
    q = out.quantize(colors=15, method=Image.Quantize.MEDIANCUT)
    pal = (q.getpalette() or [])[:45]
    pal += [0] * (45 - len(pal))                                        # fewer than 15 colours: pad
    px = [[q.getpixel((x, y)) + 1 for x in range(32)] for y in range(32)]   # index 0 stays transparent
    return px, [tuple(pal[i * 3:i * 3 + 3]) for i in range(15)]

def build(outdir, specs):
    p = os.path.join(outdir, 'font.s1'); s = bytearray(open(p, 'rb').read())
    for kind in range(3):
        for rest in range(2):
            for f in range(9):
                o = (BAR_TILE + kind * 18 + rest * 9 + f) * 32; s[o:o + 32] = stile(bar_glyph(kind, f, rest))
                o = (BAR_TILE_R + kind * 18 + rest * 9 + f) * 32; s[o:o + 32] = stile([row[::-1] for row in bar_glyph(kind, f, rest)])
    o = ARROW_TILE * 32; s[o:o + 32] = stile(ARROW)  # the select screen's "1P" / "2P" arrow (ASCII $7F, unused)
    pals = []
    for i, spec in enumerate(specs):
        game, name = spec.split(':')
        px, pal = portrait(game, name)
        for r in range(4):
            for c in range(4):
                o = (PORTRAIT_TILE + i * 16 + r * 4 + c) * 32
                s[o:o + 32] = stile([row[c * 8:c * 8 + 8] for row in px[r * 8:r * 8 + 8]])
        pals.append([0x8000] + [neo_colour(*c) for c in pal])
    assert (PORTRAIT_TILE + len(specs) * 16) * 32 <= len(s), 'S ROM too small'
    open(p, 'wb').write(bytes(s))
    h = ['/* Generated by tools/brawler/make_hud.py. Do not edit. */', '#ifndef HUD_H', '#define HUD_H',
         f'#define BAR_TILE 0x{BAR_TILE:X}   /* + kind * 18 + rest * 9 + f: kind 0 left cap / 1 middle / 2 right cap */',
         f'#define BAR_TILE_R 0x{BAR_TILE_R:X}   /* the same glyphs mirrored: kind 0 = the right (outer) cap */',
         f'#define ARROW_TILE 0x{ARROW_TILE:X}   /* a down arrow (select screen) */',
         f'#define PORTRAIT_TILE 0x{PORTRAIT_TILE:X}   /* + fighter * 16 + row * 4 + col (32x32, colours portrait_pal[fighter] in fix palette 2 + side) */',
         'static const uint16_t bar_colours[10] = {' + ', '.join('0x%04X' % neo_colour(*BAR_PAL[k]) for k in range(6, 16)) + '};   /* palette 0, entries 6-15 */',
         f'static const uint16_t portrait_pal[{len(specs)}][16] = {{' + ', '.join('{' + ', '.join(f'0x{v:04X}' for v in pl) + '}' for pl in pals) + '};',
         '#endif']
    open(os.path.join(outdir, 'hud.h'), 'w').write('\n'.join(h) + '\n')
    print(f'hud: 54 bar glyphs at ${BAR_TILE:X} (+ mirrored at ${BAR_TILE_R:X}), {len(specs)} portraits at ${PORTRAIT_TILE:X}')

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2:])
