#!/usr/bin/env python3
"""Chain Lab move pictures: each route move's impact frame(s), drawn from the brawler's own tables (build/bm_chars.c:
frames, parts, tile numbers, colour set 0; build/bm_c1.bin / bm_c2.bin: the C ROM), the way draw.s places the parts,
facing right (P1's start). One picture per hit the move opens (bstep_t flags & 4: an active step after an inactive one,
the game's hit-window rule), so a 2-hit move shows 2.

    move_images(GAME_DIR, OUT_DIR, fighters, moves) -> {fighter: {move: [{x, y, w, h, step}]}}; OUT_DIR/moves/<fighter>.png"""
import os, re
import numpy as np
from PIL import Image


def _nums(s): return [int(v, 0) for v in re.findall(r'-?(?:0x[0-9A-Fa-f]+|\d+)', s)]


def _colour(w):                                   # Neo Geo colour word -> 8-bit RGB (neogeo.sprite_decode.decode_color)
    r = ((w >> 14) & 1) | (((w >> 8) & 0xF) << 1); g = ((w >> 13) & 1) | (((w >> 4) & 0xF) << 1); b = ((w >> 12) & 1) | ((w & 0xF) << 1)
    r, g, b = (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2)
    if w >> 15: r, g, b = max(0, r - 4), max(0, g - 4), max(0, b - 4)
    return r, g, b


class Rom:
    def __init__(self, build):
        self.src = open(os.path.join(build, 'bm_chars.c')).read()
        c1 = np.frombuffer(open(os.path.join(build, 'bm_c1.bin'), 'rb').read(), np.uint8)
        c2 = np.frombuffer(open(os.path.join(build, 'bm_c2.bin'), 'rb').read(), np.uint8)
        self.c = np.empty(len(c1) * 2, np.uint8); self.c[0::2] = c1; self.c[1::2] = c2
        self.chars = {m.group(1).lower(): _nums(m.group(2)) for m in re.finditer(r'\{"(\w+)", ([^\n]*?)\},\n', self.src)}

    def arr(self, name):
        m = re.search(r'static const \w+ %s\[[^\]]*\] = \{(.*?)\};' % re.escape(name), self.src)
        return m.group(1) if m else None

    def tile(self, t):                            # 16x16 palette indices; bitplanes [bp0, bp2, bp1, bp3], right half first
        o = t * 128
        if o + 128 > len(self.c): return np.zeros((16, 16), np.uint8)
        d = self.c[o:o + 128].reshape(2, 16, 4)       # [half (0x00: x 8-15, 0x40: x 0-7)][row][bp0 bp2 bp1 bp3]
        out = np.zeros((16, 16), np.uint8)
        for half, xb in ((1, 0), (0, 8)):
            bp = d[half].astype(np.uint16)
            for x in range(8):
                bit = 1 << x
                v = ((bp[:, 0] & bit) > 0) * 1 + ((bp[:, 2] & bit) > 0) * 2 + ((bp[:, 1] & bit) > 0) * 4 + ((bp[:, 3] & bit) > 0) * 8
                out[:, xb + x] = v
        return out

    def frame(self, name, fi, tile_hi, pals):
        """-> RGBA image of frame fi, its feet origin (ox, oy), facing right"""
        parts = re.findall(r'\{(-?\d+), (-?\d+), (\d+), (\d+), (\d), (\d), (\d+), (\w+)\}', self.arr(f'{name}_f{fi}') or '')
        placed = []
        for dx, dy, cols, rows, hf, vf, pal, tarr in parts:
            dx, dy, cols, rows, hf, vf, pal = map(int, (dx, dy, cols, rows, hf, vf, pal))
            tiles = _nums(self.arr(tarr)); img = np.zeros((rows * 16, cols * 16), np.uint8)
            for c in range(cols):
                for r in range(rows):
                    t = tiles[c * rows + r]
                    if t: img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = self.tile((tile_hi << 16) | t)
            w, h = cols * 16, rows * 16
            x0 = -dx - w if hf else dx; y0 = -dy - h if vf else dy
            if hf: img = img[:, ::-1]
            if vf: img = img[::-1, :]
            placed.append((x0, y0, img, pal))
        if not placed: return None
        minx = min(p[0] for p in placed); miny = min(p[1] for p in placed)
        maxx = max(p[0] + p[2].shape[1] for p in placed); maxy = max(p[1] + p[2].shape[0] for p in placed)
        rgba = np.zeros((maxy - miny, maxx - minx, 4), np.uint8)
        for x0, y0, img, pal in placed:
            m = img > 0
            lut = np.array([(0, 0, 0, 0)] + [(*_colour(pals[pal * 16 + k]), 255) for k in range(1, 16)], np.uint8)
            sub = rgba[y0 - miny:y0 - miny + img.shape[0], x0 - minx:x0 - minx + img.shape[1]]
            sub[m] = lut[img[m]]
        rgba = rgba[:, ::-1]                       # ROM sprites face left: P1 faces right
        return rgba, maxx - 1, -miny               # origin x mirrored: 0 -> width-1-(0-minx)


def move_images(game, out, fighters, moves, scale=2):
    rom = Rom(os.path.join(game, 'build'))
    os.makedirs(os.path.join(out, 'moves'), exist_ok=True)
    index = {}
    for name in fighters:
        ch = rom.chars[name]
        npal, tile_hi = ch[0], ch[-3]
        pals = _nums(rom.arr(f'{name}_pals'))[:npal * 16]          # colour set 0
        shots = []
        for m in moves:
            st = rom.arr(f'{name}_{m}')
            if st is None: continue
            steps = re.findall(r'\{(\d+), (\d+), (\d+), \{', st)
            hits = [(k, int(f)) for k, (f, t, fl) in enumerate(steps) if int(fl) & 4]
            for k, fi in hits:
                r = rom.frame(name, fi, tile_hi, pals)
                if r: shots.append((m, k, *r))
        if not shots: continue
        # one sheet per fighter: every picture on a common feet line, so they compare at the same scale
        up = max(s[4] for s in shots); down = max(s[2].shape[0] - s[4] for s in shots)
        H = up + down; x = 0; cells = []
        for m, k, img, ox, oy in shots:
            cells.append((m, k, x, img, oy)); x += img.shape[1] + 2
        sheet = np.zeros((H, x, 4), np.uint8)
        idx = {}
        for m, k, x0, img, oy in cells:
            y0 = up - oy
            sheet[y0:y0 + img.shape[0], x0:x0 + img.shape[1]] = img
            idx.setdefault(m, []).append({'x': x0 * scale, 'y': 0, 'w': img.shape[1] * scale, 'h': H * scale, 'step': k})
        im = Image.fromarray(sheet, 'RGBA')
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(os.path.join(out, 'moves', f'{name}.png'), optimize=True)
        index[name] = {'sheet': f'moves/{name}.png', 'w': im.width, 'h': im.height, 'moves': idx}
    return index


if __name__ == '__main__':
    import sys, json
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    import routes
    game, out = sys.argv[1], sys.argv[2]
    names = [f['name'] for f in json.load(open(os.path.join(game, 'build', 'chainlab.json')))['fighters']]
    ix = move_images(game, out, names, routes.MOVE_NAMES)
    for n, v in ix.items(): print(n, v['w'], 'x', v['h'], sum(len(x) for x in v['moves'].values()), 'pictures')
