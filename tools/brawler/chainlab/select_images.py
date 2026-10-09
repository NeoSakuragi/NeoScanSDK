#!/usr/bin/env python3
"""Brawler Lab, Select screen tab data (make_site.py -> select.json): everything the page needs to draw the game's
select screen pixel for pixel (selectrender.js) while Bruno places the fighters.

  poses     per selectable fighter: its select pose from the ROM build (build/bm_chars.c: the 'watch' animation's
            frame, its parts, tiles, column trims; build/bm_c1 / c2) and, from the Characters tab's export of every pose
            candidate (char_images.pose_candidates, `ix`), the other frames it could hold; each as palette indices
            (pal * 16 + pen, 0 transparent) in the ROM sprites' orientation (facing LEFT; the page mirrors x -> 2 ox - 1 - x
            for facing right, as draw.s fighter_place does), clipped to the select block's SEL_COLS sprites, its sprite
            columns (top from the feet, rows: the trims draw.s writes to SCB3, what the LSPC counts per line) and the
            head point (head_point.py: where the cursor's arrow points)
  fix       the fix layer as the game left it on the select screen (our emulator, harness.py: fresh power-on, a coin,
            START), the cursor's arrow, "1P" and the name row taken out (the page draws them for the layout's cursor),
            the S ROM tiles it uses + ASCII, the fix palettes, the backdrop colour
  lut       Geolith's resnet palette LUT (geo_lspc_palgen_resnet, the option harness.py / web_core.c / neogeo_sdl set):
            6-bit channel (5 bits << 1 | the dark bit) -> 8 bits
  layout    the build's layout (build_tables.select_layout: game.json select_layout, else the first layout)
  land      the select screen's backdrop, KOF95's Neo Geo Land (make_stage_land.py -> build/land.json): its layers as
            palette indices at their world x / screen y, their columns' trims, SNK's palette words, the street's width
  stick     game.json select.stick: 'positions' (the cursor graph from the places) or 'order' (left / right = the list)
  graph     the build's cursor graph {fighter: {right, left, up, down}} (build_tables.select_stick; the page computes
            its own from the layout being edited, selectrender.js stick)

    python3 select_images.py GAME_DIR OUT.json     (standalone: the ROM poses only, no candidates)"""
import base64, json, os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
from move_images import Rom, _nums
import head_point as HP

# geo_lspc.c geo_lspc_palgen_resnet, lut_normal (compiled from the function itself, 2026-10-07): index = (5-bit << 1) | dark
LUT = [0, 0, 7, 7, 15, 14, 22, 22, 30, 30, 38, 37, 45, 44, 54, 53, 63, 62, 72, 71, 79, 78, 87, 85, 95, 93, 102, 101, 110, 108,
       122, 120, 133, 131, 145, 143, 153, 151, 160, 158, 168, 166, 176, 173, 183, 181, 192, 189, 201, 198, 210, 207, 217, 214,
       225, 222, 233, 230, 240, 237, 248, 244, 255, 251]


def trims_of(dx, dy, hf, vf, cols):
    """a part's column trims as export_bm.py writes them: per column (top px from the feet, rows shown; 0 rows = empty)"""
    rows = len(cols[0]); ptop = -dy - rows * 16 if vf else dy; out = []
    for col in cols:
        nz = [r for r, t in enumerate(col) if t]
        if not nz: out.append((0, 0)); continue
        ns = nz[-1] - nz[0] + 1
        out.append((ptop + 16 * (rows - nz[0] - ns if vf else nz[0]), ns))
    return out


def left_frame(parts, tile):
    """parts [(dx, dy, hflip, vflip, pal, tile columns, trims or None)] -> the frame facing LEFT as draw.s draws it:
    {w, h, ox, oy (the feet in the picture), pix (base64 of h * w palette indices), cols [[top, rows, left x] per sprite],
    ncols} (a frame wider than the select block's SEL_COLS sprites is clipped by draw.s: select_data leaves it out)"""
    placed, cols_out, ncols = [], [], 0
    for dx, dy, hf, vf, pal, cols, trims in parts:
        ncols += len(cols)
        rows = len(cols[0]); w, h = len(cols) * 16, rows * 16
        x0 = -dx - w if hf else dx                 # each column's left x from the feet, facing left (the street's clip)
        cols_out += [list(t) + [x0 + (w - 16 * (c + 1) if hf else 16 * c)] for c, t in enumerate(trims or trims_of(dx, dy, hf, vf, cols))]
        img = np.zeros((h, w), np.uint8)
        for c, col in enumerate(cols):
            for r, t in enumerate(col):
                if t: img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = tile(t)
        if hf: img = img[:, ::-1]
        if vf: img = img[::-1, :]
        placed.append((-dx - w if hf else dx, -dy - h if vf else dy, img, pal))
    if not placed: return None
    minx = min(p[0] for p in placed); miny = min(p[1] for p in placed)
    maxx = max(p[0] + p[2].shape[1] for p in placed); maxy = max(p[1] + p[2].shape[0] for p in placed)
    out = np.zeros((maxy - miny, maxx - minx), np.uint8)
    for x0, y0, img, pal in placed:
        m = img > 0
        sub = out[y0 - miny:y0 - miny + img.shape[0], x0 - minx:x0 - minx + img.shape[1]]
        sub[m] = (pal * 16 + img[m]).astype(np.uint8)
    return {'w': int(out.shape[1]), 'h': int(out.shape[0]), 'ox': int(-minx), 'oy': int(-miny),
            'pix': base64.b64encode(out.tobytes()).decode(), 'cols': cols_out, 'ncols': ncols}


def rom_parts(rom, name, fi, tile_hi):
    """frame fi of a fighter in the ROM build: its parts with their tiles (tile_hi applied) and the trims export_bm wrote"""
    out = []
    for dx, dy, cols, rows, hf, vf, pal, tarr in re.findall(r'\{(-?\d+), (-?\d+), (\d+), (\d+), (\d), (\d), (\d+), (\w+)\}', rom.arr(f'{name}_f{fi}') or ''):
        dx, dy, cols, rows, hf, vf, pal = map(int, (dx, dy, cols, rows, hf, vf, pal))
        w = _nums(rom.arr(tarr))
        tiles = [[(tile_hi << 16) | t if t else 0 for t in w[c * rows:(c + 1) * rows]] for c in range(cols)]
        tr = []
        for c in range(cols):
            t, top = w[cols * rows + 3 * c], w[cols * rows + 3 * c + 1]
            tr.append((top - 65536 if top > 32767 else top, t & 63) if t else (0, 0))
        out.append((dx, dy, hf, vf, pal, tiles, tr))
    return out


def fix_capture(game, b=None):
    """the select screen's fix layer in our emulator: {map: 40 x 28 words (column-major, visible rows: VRAM $7000 + col * 32 + row + 2),
    pals: fix palettes 0-15 (words), backdrop (word), tiles: {tile: base64 of 64 pens}}"""
    import ctypes as C
    from harness import Brawler
    b = b or Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)   # (one per process: a caller's own)
    b.core.retro_reset(); b.seq('600:-,4:o,100:-'); b.seq('4:s,120:-')
    n = b.core.retro_get_memory_size(3)
    vram = (C.c_uint16 * (n // 2)).from_address(b.core.retro_get_memory_data(3))
    pal = (C.c_uint16 * 8192).from_address(b.core.retro_get_memory_data(104))
    fmap = [vram[0x7000 + c * 32 + r + 2] for c in range(40) for r in range(28)]   # visible rows 0-27 (map rows 2-29)
    arrow = int(re.search(r'#define ARROW_TILE (0x[0-9A-Fa-f]+)', open(os.path.join(game, 'build', 'hud.h')).read()).group(1), 16)
    for c in range(40):                          # the name row (select_name) and the cursor's "1P" + arrow: the page's
        fmap[c * 28 + 2] = 0x20                  # (select_name fills it with spaces; P1 only: P2 is not in on a fresh select screen)
        for r in range(1, 28):
            if fmap[c * 28 + r] & 0xFFF == arrow:
                fmap[c * 28 + r] = 0
                for cc in (c, c + 1):
                    if cc < 40: fmap[cc * 28 + r - 1] = 0
    rom = open(os.path.join(game, 'brawler.neo'), 'rb').read()
    psz, ssz = (int.from_bytes(rom[o:o + 4], 'little') for o in (4, 8))
    srom = rom[4096 + psz:4096 + psz + ssz]
    def ftile(t):                                # S ROM tile: 32 bytes, columns 4-5, 6-7, 0-1, 2-3 of 8 rows; low nibble left
        d = srom[t * 32:t * 32 + 32]; px = bytearray(64)
        for g, x in ((0, 4), (1, 6), (2, 0), (3, 2)):
            for y in range(8):
                v = d[g * 8 + y]; px[y * 8 + x] = v & 15; px[y * 8 + x + 1] = v >> 4
        return base64.b64encode(bytes(px)).decode()
    used = sorted({w & 0xFFF for w in fmap} | set(range(0x20, 0x80)))
    return {'map': fmap, 'pals': [pal[i] for i in range(256)], 'backdrop': pal[4095], 'arrow': arrow,
            'tiles': {t: ftile(t) for t in used}}


def select_data(game, cand=None, b=None):
    """-> select.json's dict; cand: char_images.pose_candidates' index (the other poses), None = the ROM poses only;
    b: the process's harness.Brawler when it has one"""
    import build_tables
    build = os.path.join(game, 'build'); rom = Rom(build)
    G = json.load(open(os.path.join(game, 'game.json')))
    L = build_tables.select_layout(G)
    src = open(os.path.join(game, 'main.c')).read()
    sel_cols = int(re.search(r'#define SEL_COLS (\d+)', src).group(1)); floor = int(re.search(r'#define SELECT_FLOOR (\d+)', src).group(1))
    na = int(re.search(r'#define NA (\d+)', src).group(1))
    heads = re.search(r'bm_head\[BC_COUNT\]\[2\] = \{(.*?)\};', rom.src).group(1)
    heads = [list(map(int, h)) for h in re.findall(r'\{(-?\d+), (-?\d+)\}', heads)]
    names = [r['name'] for r in G['roster']]
    disp = {m.group(2): m.group(1) for m in re.finditer(r'\{"([^"\n]*)", \d+, \d+, (\w+)_pals, ', rom.src)}
    fighters = {}
    for n in L:
        r = G['roster'][names.index(n)]
        npal, nsets = rom.chars[n]; th = rom.tile_hi[n]
        steps = re.findall(r'\{(\d+), (\d+), (\d+), \{', rom.arr(f'{n}_watch'))
        fi = int(steps[-1][0])
        cur = left_frame(rom_parts(rom, n, fi, th), rom.tile)
        assert cur['ncols'] <= sel_cols, f'{n}: its select pose is {cur["ncols"]} sprites wide, the block {sel_cols}'
        cur.update(pose=build_tables.watch_of(G, r)[0], head=heads[names.index(n)], pals=_nums(rom.arr(f'{n}_pals'))[:npal * 16], rom=True)
        poses, wide = [cur], []
        cur['alias'] = [cur['pose']]
        for t in ((cand or {}).get(n) or {}).get('ix', []):    # a frame each (alias: every [state, step] that shows it)
            if cur['pose'] in t['poses'] or all(t['frame'][k] == cur[k] for k in ('w', 'h', 'ox', 'oy', 'pix')):
                cur['alias'] += [p for p in t['poses'] if p not in cur['alias']]; continue   # the ROM's own frame stands for it
            if t['frame']['ncols'] > sel_cols or t['head'] is None: wide += t['poses']; continue   # draw.s would clip it /
                                                # head_point.py can't find its head (the export would stop): not offered
            poses.append(dict(t['frame'], pose=t['poses'][0], alias=t['poses'], head=t['head'], pals=cand[n]['pals'], rom=False))
        u = r.get('unlock', 'always')
        fighters[n] = {'name': disp.get(n, n.upper()), 'locked': u != 'always', 'poses': poses, 'wide': wide}
    stick = G.get('select', {}).get('stick', 'positions')   # the cursor graph (TODO #187): the build's (game_tables.c sel_stick)
    graph = build_tables.select_stick(L, build_tables.bm_heads(build, G), stick)
    return {'layout': L, 'stick': stick, 'graph': graph, 'roster': names, 'fighters': fighters, 'lut': LUT, 'floor': floor, 'sel_cols': sel_cols, 'na': na, 'line_max': 96,
            'fix': fix_capture(game, b), 'version': open(os.path.join(game, 'VERSION')).read().strip(),
            'land': json.load(open(os.path.join(build, 'land.json')))}


if __name__ == '__main__':
    d = select_data(sys.argv[1])
    json.dump(d, open(sys.argv[2], 'w'))
    for n, f in d['fighters'].items(): print(n, f['name'], len(f['poses']), 'poses', f['poses'][0]['w'], 'x', f['poses'][0]['h'], 'cols', f['poses'][0]['ncols'])
