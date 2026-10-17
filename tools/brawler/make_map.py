#!/usr/bin/env python3
"""The campaign map (game.json "map"; main.c "the map"): Final Fight's between-rounds city map, from FF's ROM
(tools/ffight/map_ff.py: 32 x 13 scroll1 cells, palette 4 = grey / not visited, 3 = green / visited), as one sticky
chain of 16 px sprite columns on the Neo Geo.

- the picture: FF's map copy 0 (nothing visited), its place names wiped (map_ff.erase_labels: their pixels filled from
  their neighbours), FF's red route dots wiped the same way; the banner rows ("THE ATLANTIC OCEAN") cut off (cell rows
  0 .. ROWS - 1 kept); our names go on the fix layer in our font (main.c, game.json stages[].map name / label: the stops
  are the campaign's stages in play, build_tables.map_stops)
- the districts: FF's per-8x8-cell progress (the cells each round turns green, map_ff step k) + Up Town (never green in
  FF: its last round), named as FF names them (DISTRICTS below), coloured per 8 x 8 cell as FF does. A Neo Geo sprite
  tile picks its palette per 16 x 16 tile: a tile whose cells all belong to one stop (or none: the base) takes that
  stop's palette; a tile whose 8 x 8 cells straddle two districts (or a district and the base) gets a SPLIT palette
  (note 20261017-132507-e03d, Bruno: "the green fill is bleeding into the SLUM portion of the map": 0.10.160-164 gave
  such a tile wholly to the district of most of its cells): its pixels' pens renumbered so that each pen whose grey
  and green differ gets one slot per district in the tile (the pens alike in both share a slot), and main.c fills each
  slot from its district's current colours (map_split: [stop or 0xFF the base, FF pen]); split palettes are packed
  (tiles share one while their slots fit 15)
- palettes: MAP_PAL + 0 = the base (grey), MAP_PAL + 1 + k = stop k's (main.c writes FF's grey or green into it: lit =
  reached, the current stop blinking between the two), then the split palettes (MAP_PAL + 1 + MAP_NSTOPS + j); FF's
  CPS1 colours as Neo Geo words; FF's pen 15 (transparent) = our pen 0, FF pen p = our p + 1
Tiles appended to BUILD/rom_c1/c2.bin (identical ones once), BUILD/map.h, BUILD/map.png (+ map_lit.png: every stop lit).

    python3 make_map.py game.json BUILD_DIR"""
import json, os, sys
from collections import Counter
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, os.path.join(HERE, '..', 'ffight')); sys.path.insert(0, HERE)
from tile_encoder import encode_crom_tile
import map_ff as M
import ff

ROWS = 11                                    # FF's cell rows kept (rows 11-12: the ATLANTIC OCEAN banner)
COLS = 32
MAP_PAL = 240                                # main.c MAP_PAL (the drama portraits' palettes: never on screen with the map)
MAP_PAL_END = 248                            # main.c SF_RAYS_PAL: the map's palettes stay under it
MAX_STOPS = 6                                # gamedata.h GM_STOPS
DISTRICTS = ('SLUM', 'PARK', 'WEST SIDE', 'INDUSTRIAL AREA', 'BAY AREA', 'UP TOWN')   # FF's: step 1-5 (PARK = SUBWAY + PARK), Up Town


def district_cells():
    """cell (r, c) -> district name (or None)"""
    V = [M.variant(k) for k in range(6)]
    d = {}
    for k in range(1, 6):
        for r in range(ROWS):
            for c in range(COLS):
                if V[k][r][c][1] & 31 == 3 and V[k - 1][r][c][1] & 31 != 3: d[(r, c)] = DISTRICTS[k - 1]
    for r in range(0, 6):                    # Up Town: the land east of the West Side over Industrial / Bay (FF never
        for c in range(18, 31):              # lights it): its cells not in another district
            d.setdefault((r, c), 'UP TOWN')
    return d


def neo(w):
    r, g, b = ff.cps_rgb(w)
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    return ((r5 & 1) << 14) | ((g5 & 1) << 13) | ((b5 & 1) << 12) | ((r5 >> 1) << 8) | ((g5 >> 1) << 4) | (b5 >> 1)


def palette(p):
    w = M.pal1(p)                            # FF pens 0-14 -> ours 1-15; pen 0 transparent
    return [0x8000] + [neo(w[k]) for k in range(15)]


def pen_map():
    g0 = M.variant(0)
    pm = M.erase_labels(M.pens(g0))
    # the red route dots (pen 2): wiped as the names (filled from the neighbours)
    H, W = len(pm), len(pm[0])
    left = {(x, y) for y in range(H) for x in range(W) if pm[y][x] in M.PEN_STOP}
    while left:
        done = {}
        for x, y in left:
            c = Counter(pm[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                        if (dx or dy) and 0 <= y + dy < H and 0 <= x + dx < W and (x + dx, y + dy) not in left)
            if c: done[(x, y)] = c.most_common(1)[0][0]
        if not done: break
        for k, v in done.items(): pm[k[1]][k[0]] = v
        left -= set(done)
    a = np.array(pm[:ROWS * 8], np.uint8)
    out = np.where(a == 15, 0, a + 1).astype(np.uint8)          # FF pen 15 transparent -> ours 0
    return out


def build(game_json, bd):
    import build_tables
    G = build_tables.load(game_json); mp = G.get('map')
    stops = build_tables.map_stops(G) if mp else []
    assert len(stops) <= MAX_STOPS, f'map.stops: at most {MAX_STOPS}'
    for s in stops: assert s['district'] in DISTRICTS, f'map stop {s["name"]}: district {s["district"]!r} not one of {DISTRICTS}'
    px = pen_map(); H, W = px.shape
    oy = (16 - H % 16) % 16                                       # pad at the bottom: whole 16 px tiles
    px = np.vstack([px, np.zeros((oy, W), np.uint8)]); H = px.shape[0]
    nc, nr = W // 16, H // 16
    dc = district_cells(); dstop = {s['district']: k for k, s in enumerate(stops)}
    grey, lit = palette(4), palette(3)
    differ = {p for p in range(1, 16) if grey[p] != lit[p]}           # the pens a district's state changes
    c1p, c2p = os.path.join(bd, 'rom_c1.bin'), os.path.join(bd, 'rom_c2.bin')
    c1, c2 = bytearray(open(c1p, 'rb').read()), bytearray(open(c2p, 'rb').read())
    def cell_stop(r8, c8): return dstop.get(dc.get((r8, c8)), 0xFF)  # an 8 x 8 cell's stop (0xFF: the base)
    owner = np.full((H, W), 0xFF, np.uint8)                           # every pixel's stop
    for r8 in range(H // 8):
        for c8 in range(W // 8): owner[r8 * 8:r8 * 8 + 8, c8 * 8:c8 * 8 + 8] = cell_stop(r8, c8)
    splits = []                                                       # split palettes: [slot 1-15] = (stop | 0xFF, pen)
    base = len(c1) // 64; index = {}; words = []; tile_pal = []
    for c in range(nc):
        for r in range(nr):
            t = px[r * 16:r * 16 + 16, c * 16:c * 16 + 16]; o = owner[r * 16:r * 16 + 16, c * 16:c * 16 + 16]
            used = {int(x) for x in np.unique(o[t != 0])}
            if len(used) <= 1:
                pal = (next(iter(used)) + 1) % 0x100 if used else 0  # one stop k: 1 + k; the base (0xFF) or empty: 0
            else:                                                     # a split tile: (owner, pen) -> a slot
                need = sorted({(int(o[y, x]) if t[y, x] in differ else 0xFF, int(t[y, x]))
                               for y in range(16) for x in range(16) if t[y, x]})
                for j, sp in enumerate(splits):
                    if len(set(sp) | set(need)) <= 15: splits[j] = sorted(set(sp) | set(need)); pal = j; break
                else: splits.append(need); pal = len(splits) - 1
                pal = ('split', pal)
            tile_pal.append(pal)
            words += [None, None]                                     # (filled once the splits are packed)
    assert 1 + len(stops) + len(splits) <= MAP_PAL_END - MAP_PAL, f'map: {1 + len(stops)} + {len(splits)} split palettes > {MAP_PAL_END - MAP_PAL}'
    k = 0; ftiles = []                                                # ftiles: each tile as written (its pens)
    for c in range(nc):
        for r in range(nr):
            t = px[r * 16:r * 16 + 16, c * 16:c * 16 + 16].copy(); o = owner[r * 16:r * 16 + 16, c * 16:c * 16 + 16]
            pal = tile_pal[k]
            if isinstance(pal, tuple):                                # its pens renumbered to the split's slots
                sp = splits[pal[1]]; nt = np.zeros_like(t)
                for y in range(16):
                    for x in range(16):
                        if t[y, x]: nt[y, x] = sp.index((int(o[y, x]) if t[y, x] in differ else 0xFF, int(t[y, x]))) + 1
                t = nt; pn = 1 + len(stops) + pal[1]
            else: pn = pal
            tile_pal[k] = pn; ftiles.append(t)
            if not t.any(): words[2 * k:2 * k + 2] = [0, 0]; k += 1; continue
            key = t.tobytes()
            if key not in index:
                index[key] = base + len(index); x, y = encode_crom_tile(t); c1.extend(x); c2.extend(y)
            n = index[key]
            words[2 * k:2 * k + 2] = [n & 0xFFFF, ((MAP_PAL + pn) << 8) | (((n >> 16) & 0xF) << 4)]
            k += 1
    tile_stop = tile_pal
    open(c1p, 'wb').write(bytes(c1)); open(c2p, 'wb').write(bytes(c2))
    h = ['/* Generated by tools/brawler/make_map.py from Final Fight\'s city map (tools/ffight/map_ff.py) and game.json map. Do not edit. */',
         '#ifndef MAP_H', '#define MAP_H',
         f'#define MAP_COLS {nc}   /* sprites (16 px columns) */', f'#define MAP_ROWS {nr}   /* tiles a column */',
         f'#define MAP_W {W}', f'#define MAP_H_PX {ROWS * 8}   /* the picture\'s height (the last tile row padded) */',
         f'#define MAP_PAL {MAP_PAL}   /* + 0 the base (grey), + 1 + k stop k (main.c: grey / lit / blinking) */',
         f'#define MAP_NSTOPS {len(stops)}',
         f'#define MAP_TILES {len(index)}',
         f'#define MAP_NSPLIT {len(splits)}   /* split palettes (MAP_PAL + 1 + MAP_NSTOPS + j): tiles across two districts */',
         '/* a split palette\'s slots 1-15: [stop k (0xFF: the base, always grey; also a pen alike grey / green), FF pen + 1] */',
         f'static const uint8_t map_split[{max(1, len(splits))}][15][2] = {{ {", ".join("{ " + ", ".join(f"{{ {a}, {b} }}" for a, b in sp + [(0xFF, 0)] * (15 - len(sp))) + " }" for sp in splits) or "{ { 0 } }"} }};',
         '/* column-major SCB1 word pairs: tile low 16 bits, attribute (palette MAP_PAL + its stop, tile bits 16-19) */',
         f'static const uint16_t map_scb1[MAP_COLS * MAP_ROWS * 2] = {{ {", ".join(f"0x{v:04X}" for v in words)} }};',
         f'static const uint16_t map_grey[16] = {{ {", ".join(f"0x{v:04X}" for v in grey)} }};   /* FF\'s scroll1 palette 4 */',
         f'static const uint16_t map_lit[16] = {{ {", ".join(f"0x{v:04X}" for v in lit)} }};   /* FF\'s scroll1 palette 3 */',
         '#endif']
    open(os.path.join(bd, 'map.h'), 'w').write('\n'.join(h) + '\n')
    from PIL import Image
    def rgb(w):
        r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
        return (r * 255 // 31, g * 255 // 31, b * 255 // 31)
    def colour(pn, v, litset):                                      # the shown colour of pen v in map palette pn
        if pn == 0: return grey[v]
        if pn <= len(stops): return (lit if pn in litset else grey)[v]
        st, pen = splits[pn - 1 - len(stops)][v - 1]
        return (lit if st != 0xFF and st + 1 in litset else grey)[pen]
    for name, litset in (('map.png', set()), ('map_lit.png', set(range(1, len(stops) + 1)))):
        im = Image.new('RGB', (W, H), (0, 0, 0)); P = im.load(); k = 0
        for c in range(nc):
            for r in range(nr):
                pn = tile_stop[c * nr + r]; t = ftiles[c * nr + r]   # (the tiles as written: the split renumbering proven)
                for y in range(16):
                    for x in range(16):
                        v = t[y, x]
                        if v: P[c * 16 + x, r * 16 + y] = rgb(colour(pn, v, litset))
        im.save(os.path.join(bd, name))
    print(f'map: {W}x{ROWS * 8} px, {nc} x {nr} tiles, {sum(1 for k in range(0, len(words), 2) if words[k] or words[k + 1])} used, '
          f'{len(index)} unique from {base}, {len(splits)} split palette(s), stops {[s["name"] for s in stops]}')


if __name__ == '__main__':
    if len(sys.argv) != 3: sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
