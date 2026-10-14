#!/usr/bin/env python3
"""The brawler's BIG bitmap font (Bruno 2026-10-14: "I want a BIG bitmap font, for big messages on the screen. I like the
one from SAVAGE REIGN"): Savage Reign's round-call letters, completed to a full set in their own construction.

What Savage Reign has (SNK 1995, /data/roms/savagere.neo, measured in OUR emulator, emu/neogeo_sdl --capture, VRAM +
palette RAM dumps; tools/brawler/bigfont_proof.py `rip` redoes it):
  * the round call "ROUND n" = one sprite per letter, 16 x 48 px (3 tiles), palette $BD (palette RAM bank 1), sprites
    238-245, x 112 + 16 k, y 63; the letters are only R O U N D and the digits 1-4 (ROUND 1-4; ROUND 4 adds the small
    "-FINAL-" strip under it, its own 16 px row), C ROM tiles (+ $1D000):
      R 9ED 9EE 9EF   O 9F0 9F1 9F2   U 9F3 9F1 9F4   N 9F5 9F6 9F7   D 9F8 9F1 9F9   (O U D share their middle tile)
      1 9FA 9FB 9FC   2 9FD 9FE 9FF | A01 A02 A03   3 9FD A04 A05 | A01 A06 A07   4 A0D A0E A0F | A11 A12 A13
      -FINAL- A08 A09 A0A A0B A0C A10 A14 (one row, under ROUND 4)
  * "FIGHT!" = ONE picture (no letters): 8 sprites x 4 tiles (128 x 64 px), $1D9C2-$1D9E1 column-major, palette $BC
    (the same colours as $BD but pen 13)
  * no K.O. / TIME OVER / WINNER picture: the KO is a white flash; YOU WIN / YOU LOSE / DEMONSTRATION are 16 x 16 fix
    layer fonts (2 x 2 S ROM tiles a letter: $502 + 4 k palette 3, $755 + 4 k palette 6, full A-Z), not big letters
So the big set is not an alphabet: 5 letters + 4 digits. The rest (A-Z, 0, 5-9, ! . - ' : ?) is built here in Savage
Reign's construction, read off those 9 glyphs: 13 px of fill between a 2 px outline on the left / top / bottom and 1 px
on the right (16 px a glyph), stems 5 px wide with 3 px between them, bars 5 rows (top 0-4, bottom 36-40 of the 41 fill
rows), the middle bar about rows 16-23, every top-right and bottom-left corner cut at 45 degrees over 4 px (D: top-right
and bottom-right), and the colours by row: pen 12 (red) at the top and the bottom through 11 10 9 8 7 6 5 to pen 4
(white) in the middle (GRAD), a lighter left edge (EDGE), the top edge a 5-9 highlight run (TOP), the bottom-left cut
pens 10 / 7 / 8, pens 2 / 3 on the outline right of the top-right cut. render() re-draws Savage Reign's own 5 letters
from their masks at 96-98 % of their pixels (bigfont_proof.py); the brawler keeps their original pixels and draws only
the missing glyphs with it. Digits 2-4 are 17 px (their stray column 0 line and 2 blank columns dropped), so 2 sprites.

Output (after staff_roll.py; examples/brawler/Makefile): every glyph's columns cut into 16 x 16 tiles (blank = tile 0,
identical ones once) appended to BUILD/rom_c1/c2.bin; BUILD/bigfont.h: per ASCII $20-$5F the advance, the sprite
columns, the first column; the columns' SCB1 words (3 tiles each); the palette (Savage Reign's $BD); BUILD/bigfont.png
(the set as built). main.c "big text" draws a message with a sprite per glyph column.

    python3 make_bigfont.py BUILD_DIR            -> bigfont.h, rom_c1/c2.bin + the font's tiles, bigfont.png
    python3 make_bigfont.py sheet OUT.png        the contact sheet: Savage Reign's originals + the full set (x3)
    python3 make_bigfont.py dump DIR             the rip: DIR/glyphs.json (tiles, palette, which glyph is SR's), DIR/*.png"""
import json, os, struct, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
from tile_encoder import encode_crom_tile

ROM = '/data/roms/savagere.neo'
SR_PAL = [0x0000, 0x0000, 0x0630, 0x0A60, 0x7FFF, 0x7FF8, 0x6FF0, 0x4FD0, 0x6FA0, 0x6F80, 0x6F60, 0x4F40, 0x4F00, 0x00E8,
          0x0000, 0x0000]                    # Savage Reign's palette $BD (bank 1) on ROUND 1, frame 2420 of bigfont_proof.py's run
T0 = 0x1D000
SR_GLYPHS = {                                # columns of 3 tiles (+ T0); crop = the glyph's pixel columns kept
    'R': ([[0x9ED, 0x9EE, 0x9EF]], None), 'O': ([[0x9F0, 0x9F1, 0x9F2]], None), 'U': ([[0x9F3, 0x9F1, 0x9F4]], None),
    'N': ([[0x9F5, 0x9F6, 0x9F7]], None), 'D': ([[0x9F8, 0x9F1, 0x9F9]], None),
    '1': ([[0x9FA, 0x9FB, 0x9FC]], (4, 16)),
    '2': ([[0x9FD, 0x9FE, 0x9FF], [0xA01, 0xA02, 0xA03]], (3, 20)),
    '3': ([[0x9FD, 0xA04, 0xA05], [0xA01, 0xA06, 0xA07]], (3, 20)),
    '4': ([[0xA0D, 0xA0E, 0xA0F], [0xA11, 0xA12, 0xA13]], (3, 20)),
}
SR_FINAL = [0xA08, 0xA09, 0xA0A, 0xA0B, 0xA0C, 0xA10, 0xA14]           # "-FINAL-" (one row of 7 tiles)
SR_FIGHT = [[0x9C2 + c * 4 + r for r in range(4)] for c in range(8)]   # "FIGHT!" (8 columns of 4 tiles, palette $BC)
SPACE = 8                                    # a space's advance (px)
FIRST, NCH = 0x20, 64                        # ASCII $20-$5F

# --- the construction (see the module doc): design grid x 0..w-1 = glyph column x + 2, y 0..40 = glyph row y + 4 ----
GRAD = [12] * 11 + [11, 10, 9, 8, 7, 6, 5, 5, 5] + [4] * 8 + [5] * 4 + [6, 7, 8, 9, 10, 11] + [12] * 10
EDGE = [5] * 6 + [6] * 9 + [5] * 3 + [4] * 13 + [5] * 3 + [6] * 9 + [7, 8, 8, 8, 8]
TOP = [5, 5, 6, 6, 7, 7, 7, 8, 9]
_L, _R, _T, _B = (0, 0, 4, 40), (8, 0, 12, 40), (0, 0, 12, 4), (0, 36, 12, 40)
DESIGN = {                                   # r: fill rectangles (x0, y0, x1, y1), cut: holes, ch: the corners cut, k: the cut's size, w: width
    'A': dict(r=[_T, _L, _R, (0, 17, 12, 23)]),
    'B': dict(r=[_T, _L, _R, _B, (0, 17, 11, 22)], cut=[(11, 18, 12, 21)], ch='tr br'),
    'C': dict(r=[_T, _L, _B, (8, 0, 12, 11), (8, 30, 12, 40)]),
    'E': dict(r=[_T, _L, _B, (0, 17, 10, 23)]),
    'F': dict(r=[_T, _L, (0, 17, 10, 23)]),
    'G': dict(r=[_T, _L, _B, (8, 0, 12, 10), (8, 20, 12, 40), (6, 20, 12, 25)]),
    'H': dict(r=[_L, _R, (0, 17, 12, 23)]),
    'I': dict(r=[(0, 0, 4, 40)], w=5),
    'J': dict(r=[_R, _B, (0, 27, 4, 40)]),
    'K': dict(r=[_L, (0, 17, 8, 23), (8, 0, 12, 13), (6, 9, 10, 19), (6, 21, 10, 31), (8, 27, 12, 40)]),
    'L': dict(r=[_L, _B]),
    'M': dict(r=[(0, 0, 20, 4), (0, 0, 4, 40), (8, 0, 12, 32), (16, 0, 20, 40)], w=21),
    'P': dict(r=[_T, _L, (8, 0, 12, 25), (0, 20, 12, 25)], ch='tr br bl'),
    'Q': dict(r=[_T, _L, _R, _B, (6, 29, 9, 33)], cut=[(10, 36, 12, 40)]),
    'S': dict(r=[_T, (0, 0, 4, 23), (0, 17, 12, 23), (8, 17, 12, 40), _B, (8, 0, 12, 9), (0, 31, 4, 40)]),
    'T': dict(r=[_T, (4, 0, 8, 40)]),
    'V': dict(r=[(0, 0, 4, 30), (8, 0, 12, 30), (2, 26, 10, 40)], ch='tr bl br', k=6),
    'W': dict(r=[(0, 0, 4, 40), (8, 8, 12, 40), (16, 0, 20, 40), (0, 36, 20, 40)], w=21),
    'X': dict(r=[(0, 0, 4, 14), (8, 0, 12, 14), (2, 12, 10, 28), (0, 26, 4, 40), (8, 26, 12, 40)], cut=[(5, 0, 7, 11), (5, 30, 7, 40)]),
    'Y': dict(r=[(0, 0, 4, 22), (8, 0, 12, 22), (0, 17, 12, 23), (4, 17, 8, 40)]),
    'Z': dict(r=[_T, (8, 0, 12, 12), (4, 10, 12, 20), (0, 18, 8, 30), (0, 28, 4, 40), _B]),
    '0': dict(r=[_T, _L, _R, _B]),
    '5': dict(r=[_T, (0, 0, 4, 23), (0, 17, 12, 23), (8, 17, 12, 40), _B]),
    '6': dict(r=[_T, _L, (0, 17, 12, 23), (8, 17, 12, 40), _B]),
    '7': dict(r=[_T, (8, 0, 12, 40)]),
    '8': dict(r=[_T, _L, _R, _B, (0, 17, 12, 22)], cut=[(11, 18, 12, 21), (0, 18, 1, 21)], ch='tr bl br'),
    '9': dict(r=[_T, (0, 0, 4, 23), (0, 17, 12, 23), _R, _B]),
    '!': dict(r=[(0, 0, 4, 29), (0, 34, 4, 40)], w=5),
    '.': dict(r=[(0, 34, 4, 40)], w=5, k=3),
    '-': dict(r=[(0, 17, 8, 23)], w=9, k=3),
    "'": dict(r=[(0, 0, 4, 10)], w=5, k=3),
    ':': dict(r=[(0, 12, 4, 18), (0, 30, 4, 36)], w=5, k=3),
    '?': dict(r=[_T, (8, 0, 12, 22), (4, 17, 12, 22), (4, 17, 8, 29), (4, 34, 8, 40)]),
}
CHARS = ' ' + ''.join(sorted(set(SR_GLYPHS) | set(DESIGN)))     # what the font draws (build_tables.py checks the texts)

_crom = None


def crom():
    global _crom
    if _crom is None:
        d = open(ROM, 'rb').read(); sz = struct.unpack('<6I', d[4:0x1C])
        _crom = d[0x1000 + sum(sz[:5]):0x1000 + sum(sz)]
    return _crom


def tile_px(t):
    tt = crom()[t * 128:(t + 1) * 128]; c1, c2 = tt[0::2], tt[1::2]; px = np.zeros((16, 16), np.uint8)
    for half, x0 in ((0, 8), (1, 0)):
        for y in range(16):
            o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
            for x in range(8): px[y, x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
    return px


def sr_picture(cols):
    a = np.zeros((len(cols[0]) * 16, 16 * len(cols)), np.uint8)
    for c, col in enumerate(cols):
        for r, t in enumerate(col): a[r * 16:r * 16 + 16, c * 16:c * 16 + 16] = tile_px(T0 + t)
    return a


def render(m):
    """a fill mask (bool [48, w]) -> pens, the construction's colours (module doc)"""
    H, W = m.shape
    f = np.zeros((H + 6, W + 6), bool); f[3:-3, 3:-3] = m
    out = np.zeros((H, W), np.uint8)
    for y in range(H):
        for x in range(W):
            Y, X = y + 3, x + 3
            if f[Y, X]:
                if not f[Y - 1, X] and y <= 5:                 # the top edge: a highlight run
                    k = 0
                    while k < x and f[Y, X - k - 1] and not f[Y - 1, X - k - 1]: k += 1
                    p = TOP[min(k, 8)]
                elif not f[Y, X - 1]: p = EDGE[y]
                elif not f[Y + 1, X] and y > 40: p = 7
                elif y > 36 and not f[Y + 1, X - 1]: p = 10
                else: p = GRAD[y]
                out[y, x] = p
            elif f[Y - 2:Y + 3, X - 1:X + 3].any():            # the outline: 2 px left / up / down, 1 right
                out[y, x] = 3 if f[Y, X - 1] and 5 <= y <= 6 else 2 if f[Y, X - 1] and y == 7 else 1
    return out


def chamfer(m, kinds, k):
    """cut the convex corners of the kinds ('tr', 'bl', 'br', 'tl') at 45 degrees: a pixel goes when its run to the
    corner's two sides is shorter than k"""
    H, W = m.shape
    up, dn, lf, rt = (np.zeros(m.shape, int) for _ in range(4))
    for y in range(H):
        for x in range(W):
            if m[y, x]:
                up[y, x] = up[y - 1, x] + 1 if y and m[y - 1, x] else 0
                lf[y, x] = lf[y, x - 1] + 1 if x and m[y, x - 1] else 0
    for y in range(H - 1, -1, -1):
        for x in range(W - 1, -1, -1):
            if m[y, x]:
                dn[y, x] = dn[y + 1, x] + 1 if y < H - 1 and m[y + 1, x] else 0
                rt[y, x] = rt[y, x + 1] + 1 if x < W - 1 and m[y, x + 1] else 0
    o = m.copy()
    for a, (p, q) in (('tr', (up, rt)), ('bl', (dn, lf)), ('br', (dn, rt)), ('tl', (up, lf))):
        if a in kinds: o &= ~((p + q < k) & m)
    return o


def design_mask(c):
    d = DESIGN[c]; w = d.get('w', 13)
    m = np.zeros((41, w), bool)
    for x0, y0, x1, y1 in d['r']: m[y0:y1 + 1, x0:x1 + 1] = True
    for x0, y0, x1, y1 in d.get('cut', []): m[y0:y1 + 1, x0:x1 + 1] = False
    m = chamfer(m, d.get('ch', 'tr bl').split(), d.get('k', 4))
    g = np.zeros((48, w + 3), bool); g[4:45, 2:2 + w] = m
    return g


def glyph(c):
    """-> (pens [48, w], 'sr' | 'built')"""
    if c in SR_GLYPHS:
        cols, crop = SR_GLYPHS[c]; a = sr_picture(cols)
        return (a[:, crop[0]:crop[1]] if crop else a), 'sr'
    return render(design_mask(c)), 'built'


def font():
    return {c: glyph(c) for c in CHARS if c != ' '}


def build(bd):
    c1p, c2p = os.path.join(bd, 'rom_c1.bin'), os.path.join(bd, 'rom_c2.bin')
    c1, c2 = bytearray(open(c1p, 'rb').read()), bytearray(open(c2p, 'rb').read())
    assert not any(c1[:64]) and not any(c2[:64]), 'C ROM tile 0 is not empty'
    base = len(c1) // 64; index = {}; cols = []; adv = [0] * NCH; ncol = [0] * NCH; col0 = [0] * NCH
    F = font()
    for c, (a, _) in sorted(F.items()):
        i = ord(c) - FIRST; w = a.shape[1]; n = (w + 15) // 16
        adv[i], ncol[i], col0[i] = w, n, len(cols)
        p = np.zeros((48, n * 16), np.uint8); p[:, :w] = a
        for k in range(n):
            col = []
            for r in range(3):
                px = p[r * 16:r * 16 + 16, k * 16:k * 16 + 16]
                if not px.any(): col.append(0); continue
                key = px.tobytes()
                if key not in index:
                    index[key] = base + len(index); x, y = encode_crom_tile(px); c1.extend(x); c2.extend(y)
                col.append(index[key])
            cols.append(col)
    adv[0] = SPACE
    assert len(cols) < 256
    open(c1p, 'wb').write(bytes(c1)); open(c2p, 'wb').write(bytes(c2))
    words = [v for col in cols for t in col for v in (t & 0xFFFF, ((t >> 16) & 0xF) << 4)]
    h = ['/* Generated by tools/brawler/make_bigfont.py (Savage Reign\'s round-call letters, completed in their construction). Do not edit. */',
         '#ifndef BIGFONT_H', '#define BIGFONT_H',
         f'#define BIGF_FIRST 0x{FIRST:02X}   /* ASCII of the first entry; BIGF_N entries */', f'#define BIGF_N {NCH}',
         '#define BIGF_ROWS 3   /* tiles a column: 48 px (glyph rows 0-1 and 47 blank) */',
         f'#define BIGF_COLS {len(cols)}',
         f'static const uint8_t bigf_adv[BIGF_N] = {{ {", ".join(map(str, adv))} }};   /* advance px (0: no glyph) */',
         f'static const uint8_t bigf_ncol[BIGF_N] = {{ {", ".join(map(str, ncol))} }};   /* sprites (16 px columns) */',
         f'static const uint8_t bigf_col0[BIGF_N] = {{ {", ".join(map(str, col0))} }};   /* its first column in bigf_map */',
         '/* the columns\' SCB1 words: tile low 16 bits, attribute (tile bits 16-19 << 4; main.c adds the palette) */',
         f'static const uint16_t bigf_map[BIGF_COLS * BIGF_ROWS * 2] = {{ {", ".join(f"0x{v:04X}" for v in words)} }};',
         f'static const uint16_t bigf_pal[16] = {{ {", ".join(f"0x{v:04X}" for v in SR_PAL)} }};   /* Savage Reign\'s palette $BD */',
         '#endif']
    open(os.path.join(bd, 'bigfont.h'), 'w').write('\n'.join(h) + '\n')
    sheet(os.path.join(bd, 'bigfont.png'), scale=1)
    nsr = sum(1 for v in F.values() if v[1] == 'sr')
    print(f'big font: {len(F)} glyphs ({nsr} Savage Reign\'s, {len(F) - nsr} built), {len(cols)} columns, {len(index)} tiles '
          f'from {base} ({len(index) * 128 / 1024:.1f} KB), C ROM {len(c1) * 2 / 1048576:.2f} MB')


def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def picture(a, bg=(96, 96, 120)):
    from PIL import Image
    im = Image.new('RGB', (a.shape[1], a.shape[0]), bg); P = im.load(); pl = [rgb(c) for c in SR_PAL]
    for y, x in zip(*np.nonzero(a)): P[int(x), int(y)] = pl[a[y, x]]
    return im


def sheet(out, scale=3):
    """the contact sheet: Savage Reign's big pictures as they are in its C ROM (top), the brawler's set (Savage Reign's
    glyphs white labels, built ones cyan)"""
    from PIL import Image, ImageDraw
    bg = (96, 96, 120)
    s = Image.new('RGB', (476, 64 + 14 + 2 * 66 + 4), bg); d = ImageDraw.Draw(s)
    x = 2
    for k in 'ROUND1234':
        cols, _ = SR_GLYPHS[k]; s.paste(picture(sr_picture(cols), bg), (x, 0)); x += 16 * len(cols) + 2
    fin = sr_picture([[t] for t in SR_FINAL]); fin = np.concatenate([fin[:, i * 16:i * 16 + 16] for i in range(7)], 1)
    s.paste(picture(fin, bg), (x, 16)); x += 114
    s.paste(picture(sr_picture(SR_FIGHT), bg), (x, 0))
    d.text((2, 64), 'Savage Reign: ROUND letters + digits, -FINAL-, FIGHT! (one picture)', fill=(255, 255, 0))
    F = font(); x, y = 2, 80
    for c in CHARS[1:]:
        a, src = F[c]
        if x + a.shape[1] > s.width - 2: x = 2; y += 66
        s.paste(picture(a, bg), (x, y)); d.text((x + 3, y + 48), c, fill=(255, 255, 255) if src == 'sr' else (0, 255, 255))
        x += a.shape[1] + 1
    if scale > 1: s = s.resize((s.width * scale, s.height * scale), Image.NEAREST)
    s.save(out)


def dump(out):
    """the rip: Savage Reign's tiles + palette + each glyph's pixels and source -> out/glyphs.json, out/<code>.png"""
    os.makedirs(out, exist_ok=True)
    F = font(); meta = {'rom': ROM, 'palette_BD': [f'0x{v:04X}' for v in SR_PAL],
                        'sr_tiles': {k: [[f'0x{T0 + t:05X}' for t in col] for col in v[0]] for k, v in SR_GLYPHS.items()},
                        'sr_final': [f'0x{T0 + t:05X}' for t in SR_FINAL], 'sr_fight': [[f'0x{T0 + t:05X}' for t in col] for col in SR_FIGHT],
                        'glyphs': {}}
    for c, (a, src) in F.items():
        picture(a).save(os.path.join(out, f'{ord(c):02X}.png'))
        meta['glyphs'][c] = {'source': src, 'width': int(a.shape[1]), 'png': f'{ord(c):02X}.png'}
    picture(sr_picture(SR_FIGHT)).save(os.path.join(out, 'sr_fight.png'))
    json.dump(meta, open(os.path.join(out, 'glyphs.json'), 'w'), indent=1)
    sheet(os.path.join(out, 'sheet.png'))
    print(out, len(F), 'glyphs')


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == 'sheet': sheet(a[1])
    elif len(a) == 2 and a[0] == 'dump': dump(a[1])
    elif len(a) == 1: build(a[0])
    else: sys.exit(__doc__)
