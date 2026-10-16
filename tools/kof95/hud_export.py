#!/usr/bin/env python3
"""KOF95 in-battle HUD graphics -> PNGs (RGBA, native size, the game's palettes), for the SF6 Mobile Replays viewer.

Everything comes from our emulator (emu/neogeo_sdl --capture: VRAMDUMP + PALDUMP + SNAPS), started from the vs state
/data/neogeo_dict/ngsdl_sta/kof95/vs_kyo.state (Kyo vs Joe, 2P fight), with life / power pokes for the states shown.
The VRAM dump is rendered here (fix layer from the S ROM, sprites from the C ROM) and the HUD parts are cut from it.

    python3 hud_export.py [OUTDIR]          (default /data/kof95_hud)

Neo Geo facts used: fix map at VRAM $7000 + col*32 + row (40 x 32 cells, rows 2-29 visible), word = palette<<12 | tile;
fix tile 32 bytes, byte columns (x4,5) (x6,7) (x0,1) (x2,3) at +$00 / +$08 / +$10 / +$18, low nibble = left pixel.
Sprites: SCB1 = 64 words per sprite (tile lsw, attr: palette<<8 | tile msb<<4 | auto-anim<<2 | flip), SCB3 = y / sticky /
height, SCB4 = x. Screen y = 496 - ypos (visible lines 16-239 already removed)."""
import json, os, struct, subprocess, sys
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rom
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
STA = '/data/neogeo_dict/ngsdl_sta/kof95'
W, H = 320, 224

def neo_regions(path=rom.NEO):
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    return reg

def words(path): d = open(path, 'rb').read(); return struct.unpack(f'>{len(d) // 2}H', d)

def rgb(w):
    """Neo Geo colour word -> 8-bit RGB (5 bits per gun incl. the shared dark bit, linear; the dark bit is ignored as
    MAME does)"""
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)

def run(tag, frames, workdir, state='vs_kyo', seq=None, seq2='', pokes=''):
    """one capture: VRAM + the active palette bank at each listed frame"""
    os.makedirs(workdir, exist_ok=True); last = max(frames) + 2
    o = os.path.join(workdir, tag)
    env = dict(os.environ, LOAD=os.path.join(STA, state + '.state'), SEQ=seq or f'{last}:-', SEQ2=seq2 or f'{last}:-',
               POKE=pokes, OUT=o, PALDUMP=','.join(map(str, frames)),
               VRAMDUMP=';'.join(f'{f}:{o}.v{f}' for f in frames))
    subprocess.run([NGSDL, rom.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    return {f: (words(f'{o}.v{f}'), words(f'{o}.pal{f}')) for f in frames}

class Gfx:
    def __init__(self):
        reg = neo_regions(); self.s, self.c = reg['S'], reg['C']; self.cache = {}

    def fix_tile(self, t):
        b = self.s[t * 32:t * 32 + 32]; px = [[0] * 8 for _ in range(8)]
        for y in range(8):
            for k, x0 in ((0x10, 0), (0x18, 2), (0x00, 4), (0x08, 6)):
                v = b[k + y]; px[y][x0] = v & 15; px[y][x0 + 1] = v >> 4
        return px

    def spr_tile(self, t):
        if t in self.cache: return self.cache[t]
        t %= len(self.c) // 128
        d = self.c[t * 128:(t + 1) * 128]; c1, c2 = d[0::2], d[1::2]; px = [[0] * 16 for _ in range(16)]
        for half, x0 in ((0, 8), (1, 0)):
            for y in range(16):
                o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
                for x in range(8):
                    px[y][x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
        self.cache[t] = px; return px

def sprites(v):
    """every sprite with its chain position: dicts i, x, y, h, shrink, tiles [(tile, attr)]"""
    out, x, y, h = [], 0, 0, 0
    for i in range(1, 381):
        s3, s4 = v[0x8200 + i], v[0x8400 + i]
        if s3 & 0x40: x += 16
        else: y, h, x = 496 - (s3 >> 7), s3 & 0x3F, s4 >> 7
        xs = x - 0x200 if x >= 0x1E0 else x
        tiles = [(v[i * 64 + 2 * r] | ((v[i * 64 + 2 * r + 1] >> 4) & 0xF) << 16, v[i * 64 + 2 * r + 1]) for r in range(min(h, 32))]
        out.append({'i': i, 'x': xs, 'y': y if y < 288 else y - 512, 'h': h, 'shrink': v[0x8000 + i], 'tiles': tiles})
    return out

def fix_cells(v):
    """{(col, row): (tile, palette)} of the visible fix layer (rows 2-29 -> screen y 0-223)"""
    out = {}
    for col in range(40):
        for row in range(2, 30):
            w = v[0x7000 + col * 32 + row]
            out[(col, row)] = (w & 0xFFF, w >> 12)
    return out

def put(img, idx, x, y, px, pal, flip=0, size=16):
    for yy in range(size):
        for xx in range(size):
            c = px[yy][xx]
            if not c: continue
            sx = x + (size - 1 - xx if flip & 1 else xx); sy = y + (size - 1 - yy if flip & 2 else yy)
            if 0 <= sx < img.width and 0 <= sy < img.height:
                img.putpixel((sx, sy), pal[c] + (255,))
                if idx is not None: idx[sy * img.width + sx] = (pal, c)

def render(g, v, palw, fix=True, spr=True, keep=None, fixkeep=None, backdrop=True):
    """the frame as the LSPC draws it (unshrunk sprites only, which is all the HUD uses); keep / fixkeep restrict to
    some sprite numbers / fix cells"""
    pal = [[rgb(palw[p * 16 + k]) for k in range(16)] for p in range(256)]
    img = Image.new('RGBA', (W, H), rgb(palw[0xFFF]) + (255,) if backdrop else (0, 0, 0, 0))
    if spr:
        for s in sprites(v):
            if keep is not None and s['i'] not in keep: continue
            for r, (t, a) in enumerate(s['tiles']):
                if not t and keep is None: continue
                put(img, None, s['x'], s['y'] + 16 * r, g.spr_tile(t), pal[a >> 8], a & 3)
    if fix:
        for (col, row), (t, p) in fix_cells(v).items():
            if fixkeep is not None and (col, row) not in fixkeep: continue
            put(img, None, col * 8, (row - 2) * 8, g.fix_tile(t), pal[p], 0, 8)
    return img

# ── the HUD, as fix-layer cell grids ([row][col] of tile numbers; screen x = col * 8, y = (row - 2) * 8) ───────────────
# Everything in KOF95's battle HUD except the two portraits is on the fix layer (8x8 S-ROM tiles, palettes 0-15):
# the sprites drawn under the POW gauges in a VRAM dump are the stage's water sparkles, not HUD.
def row_tiles(*rows): return [list(r) for r in rows]
LIFE = {   # (first col, first row): P1 = 12 cells + its inner cap (col 17), P2 = its inner cap (col 22) + 12 cells
    'p1': {'cell': (5, 4), 'full': row_tiles([0x808] * 12 + [0x82E], [0x818] * 12 + [0x83E]),
           'empty': row_tiles([0x800] * 12 + [0x828], [0x810] * 12 + [0x838])},
    'p2': {'cell': (22, 4), 'full': row_tiles([0x846] + [0x808] * 12, [0x856] + [0x818] * 12),
           'empty': row_tiles([0x840] + [0x800] * 12, [0x850] + [0x810] * 12)},
}
POW_FULL = row_tiles([0x84D] + [0x868] * 6 + [0x886], [0x85D] + [0x878] * 6 + [0x896])
POW_EMPTY = row_tiles([0x847] + [0x860] * 6 + [0x880], [0x857] + [0x870] * 6 + [0x890])
MAXIMUM = row_tiles(list(range(0x869, 0x870)) + [0x84F], list(range(0x879, 0x880)) + [0x85F])
POW_CELL = {'p1': (5, 27), 'p2': (27, 27)}
POW_LABEL = {'p1': ((2, 27), row_tiles([0x887, 0x888, 0x889], [0x897, 0x898, 0x899])),
             'p2': ((35, 27), row_tiles([0x88A, 0x88B, 0x88C], [0x89A, 0x89B, 0x89C]))}
WIN_LABEL = {'p1': ((2, 7), [[0x8A5, 0x8A6, 0x8A7]]), 'p2': ((35, 7), [[0x8B5, 0x8B6, 0x8B7]])}
BOXES = {'none': [0x8A8, 0x8A9, 0x8AA], 'right': [0x8AB, 0x8AC, 0x8AD], 'left': [0x8B8, 0x8B9, 0x8BA], 'both': [0x8BB, 0x8BC, 0x8BD]}
BOX_CELL = {'p1': (5, 7), 'p2': (32, 7)}
FRAME_CELL = {'p1': (2, 3), 'p2': (35, 3)}          # portrait frames, 3x3 cells, palette 7
CHALLENGER = {'p1': ((6, 3), 2), 'p2': ((24, 3), 3)}  # "CHALLENGER!" (11 cells), font tile = $300 + ASCII
NAME = {'p1': ((2, 6), 15, 2), 'p2': ((23, 6), 15, 3)}  # name strip, font tile = $B00 + ASCII
TIMER_CELL = (17, 3)                                   # 6 x 4 cells: TIME (pal 8) + box (pal 9)
DIGIT_CELL = {'tens': (18, 4), 'units': (20, 4)}

def digit_tiles(n):
    """timer glyph n (0-19: tens digits 0-9, then units digits 0-9): 2x3 cells, 8 glyphs per 3-row block of the S ROM"""
    t = 0xE00 + (n // 8) * 0x30 + 2 * (n % 8)
    return [[t + 0x10 * r, t + 0x10 * r + 1] for r in range(3)]

def grid_img(g, grid, palw, pn):
    """a cell grid ([row][col] tiles, one palette or a matching grid of palettes) -> RGBA, colour 0 transparent"""
    hgt, wid = len(grid), len(grid[0]); img = Image.new('RGBA', (wid * 8, hgt * 8), (0, 0, 0, 0))
    for r, row in enumerate(grid):
        for c, t in enumerate(row):
            if t is None: continue
            p = pn[r][c] if isinstance(pn, list) else pn
            put(img, None, c * 8, r * 8, g.fix_tile(t), [rgb(palw[p * 16 + k]) for k in range(16)], 0, 8)
    return img

def vram_grid(v, col, row, w, hgt):
    fc = fix_cells(v)
    return [[fc[(col + c, row + r)][0] for c in range(w)] for r in range(hgt)], \
           [[fc[(col + c, row + r)][1] for c in range(w)] for r in range(hgt)]

def check(v, col, row, grid, what):
    got = vram_grid(v, col, row, len(grid[0]), len(grid))[0]
    want = [[t for t in r] for r in grid]
    assert all(a == b or b is None for ra, rb in zip(got, want) for a, b in zip(ra, rb)), f'{what}: VRAM {got} != {want}'

def fill_px(img, full, empty):
    """columns of a rendered bar that show the full image where full and empty differ -> (count, side)"""
    cols = []
    for x in range(img.width):
        col = lambda im: [im.getpixel((x, y)) for y in range(img.height)]
        a, f, e = col(img), col(full), col(empty)
        if f == e: continue
        cols.append('F' if a == f else 'E' if a == e else '?')
    s = ''.join(cols); assert '?' not in s, s
    return s.count('F'), s

def main(out='/data/kof95_hud'):
    os.makedirs(out, exist_ok=True); work = '/data/tmp/kof95hud/export'; g = Gfx()
    files = []; img_rgb = lambda w: list(rgb(w))
    def save(im, name, what, x, y, **kw):
        im.save(os.path.join(out, name)); files.append(dict(file=name, what=what, w=im.width, h=im.height, x=x, y=y, **kw))

    # 1. base fight (both bars full, power 0) over 48 frames: the global blink of palettes 5 and 7
    base = run('base', list(range(1, 49)), work)
    pal = {f: base[f][1] for f in base}
    phase = {f: int(pal[f][5 * 16:6 * 16][1:] != pal[f][4 * 16:5 * 16][1:]) for f in pal}
    toggles = [f for f in range(2, 49) if phase[f] != phase[f - 1]]
    period = toggles[1] - toggles[0]
    assert all(b - a == period for a, b in zip(toggles, toggles[1:])), toggles
    F0 = next(f for f in range(30, 49) if phase[f] == 0); F1 = next(f for f in range(30, 49) if phase[f] == 1)
    P0, P1 = pal[F0], pal[F1]; v0 = base[F0][0]
    assert P0[:5 * 16] == P1[:5 * 16] and P0[8 * 16:16 * 16] == P1[8 * 16:16 * 16] and P0[6 * 16:7 * 16] == P1[6 * 16:7 * 16]

    # screenshot (our render of VRAM, 320x224 incl. the 8-px black fix columns at both edges) + HUD-only overlay
    shot = render(g, v0, P0); shot.convert('RGB').save(os.path.join(out, 'kof95_battle_320x224.png'))
    files.append(dict(file='kof95_battle_320x224.png', what='a KOF95 battle frame (Kyo vs Joe, 2P versus, stage 1), '
                      'rendered from VRAM + palette RAM of our emulator; columns 0-7 and 312-319 are the game\'s own black '
                      'fix-layer mask (the emulator crops them: its screenshot is 304 wide)', w=320, h=224, x=0, y=0))
    portraits = [s for s in sprites(v0) if s['y'] == 8 and s['h'] == 2 and s['x'] in (8, 24, 280, 296)]
    hud = render(g, v0, P0, keep={s['i'] for s in portraits},
                 fixkeep={k for k, (t, p) in fix_cells(v0).items() if t not in (0xF20, 0x37F) and k[1] < 29},
                 backdrop=False)
    save(hud, 'hud_overlay_320x224.png', 'every HUD element of that frame on a transparent 320x224 canvas (no CREDITS line)', 0, 0)

    # 2. life bars: full / empty (palette 4), low-life flash (palette 5, phase 1)
    for side, d in LIFE.items():
        col, row = d['cell']; x, y = col * 8, (row - 2) * 8
        check(v0, col, row, d['full'], f'life {side} full')
        full, empty = grid_img(g, d['full'], P0, 4), grid_img(g, d['empty'], P0, 4)
        save(full, f'life_{side}_full.png', f'{side.upper()} life bar, full (border + fill, palette 4)', x, y)
        save(empty, f'life_{side}_empty.png', f'{side.upper()} life bar, empty (border + the lost/empty checker, palette 4)', x, y)
        fl, el = grid_img(g, d['full'], P1, 5), grid_img(g, d['empty'], P1, 5)
        save(fl, f'life_{side}_full_lowflash.png', f'{side.upper()} life bar fill in the low-life flash (palette 5, blink phase 1)', x, y,
             anim={'frames': [f'life_{side}_full.png', f'life_{side}_full_lowflash.png'], 'ticks_each': period})
        if el.tobytes() != empty.tobytes():
            save(el, f'life_{side}_empty_lowflash.png', f'{side.upper()} empty part during the low-life flash', x, y)

    # drain both bars to 1 (P1 / P2 life +$120 poked, the displayed copy +$122 follows 2 per frame): fill per value
    fr = list(range(3, 112))
    env_pokes = '2:108221=01,108421=01'
    dr = run('drain', fr, work, pokes=env_pokes)
    o = os.path.join(work, 'drainram')
    env = dict(os.environ, LOAD=os.path.join(STA, 'vs_kyo.state'), SEQ='115:-', SEQ2='115:-', POKE=env_pokes, OUT=o,
               RAMDUMP=';'.join(f'{f}:108222:2;{f}:108422:2' for f in fr))
    subprocess.run([NGSDL, rom.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    life_tab = {'p1': {}, 'p2': {}}; low_at = {}
    for f in fr:
        v = dr[f][0]
        for side, base_addr in (('p1', 0x108222), ('p2', 0x108422)):
            L = int(open(f'{o}.ram{f}_{base_addr:06X}').read(), 16)
            col, row = LIFE[side]['cell']; tiles, pals = vram_grid(v, col, row, 13, 2)
            img = grid_img(g, tiles, P0, 4)
            n, s = fill_px(img, grid_img(g, LIFE[side]['full'], P0, 4), grid_img(g, LIFE[side]['empty'], P0, 4))
            life_tab[side][L] = n
            if pals[0][1] == 5: low_at.setdefault(side, L)
            assert (s == 'E' * (len(s) - n) + 'F' * n) if side == 'p1' else (s == 'F' * n + 'E' * (len(s) - n)), s
    for side in life_tab:
        for L, n in life_tab[side].items(): assert n == min(L // 2, 102), (side, L, n)
    empty_ok = dr[fr[-1]][0]
    for side, d in LIFE.items(): check(empty_ok, *d['cell'], d['empty'], f'life {side} empty')

    # 3. timer: frame (TIME + box without the digit cells and without the two life-bar caps), digits
    tg, tp = vram_grid(v0, *TIMER_CELL, 6, 4)
    for r in (1, 2): tg[r][0] = tg[r][5] = None
    for r in (1, 2, 3):
        for c in (1, 2, 3, 4): tg[r][c] = None
    save(grid_img(g, tg, P0, tp), 'timer_frame.png', 'timer box: TIME label (palette 8) and box (palette 9); the 32x24 '
         'hole at (8,8) is where the two digits go; rows 8-23 of columns 0-7 / 40-47 are the life bars\' inner caps', 136, 8)
    for kind, base_n in (('tens', 0), ('units', 10)):
        col, row = DIGIT_CELL[kind]
        for d in range(10):
            save(grid_img(g, digit_tiles(base_n + d), P0, 9), f'timer_{kind}_{d}.png',
                 f'timer {kind} digit {d} (opaque, includes the box background; tens and units glyphs differ slightly)', col * 8, (row - 2) * 8)
    check(v0, *DIGIT_CELL['tens'], digit_tiles(5), 'timer tens 5'); check(v0, *DIGIT_CELL['units'], digit_tiles(15), 'timer units 5')
    save(render(g, v0, P0, spr=False, backdrop=False, fixkeep={(c, r) for c in range(17, 23) for r in range(3, 7)}).crop((136, 8, 184, 40)),
         'timer_example_55.png', 'the whole timer as the game drew it (55), incl. the life-bar caps at its sides', 136, 8)

    # 4. side labels around the bars
    for side in ('p1', 'p2'):
        (col, row), pn = CHALLENGER[side]
        grid, pals = vram_grid(v0, col, row, 11, 1)
        save(grid_img(g, grid, P0, pn), f'challenger_{side}.png', f'"CHALLENGER!" over the {side.upper()} bar (2P versus; '
             f'font tile = $300 + ASCII, palette {pn})', col * 8, (row - 2) * 8)
        (col, row), w, pn = NAME[side]
        grid, pals = vram_grid(v0, col, row, w, 1)
        save(grid_img(g, grid, P0, pn), f'name_{side}_example.png', f'{side.upper()} name strip as drawn for this fight '
             f'({"KYO KUSANAGI" if side == "p1" else "JOE HIGASHI"}); text in the name font (tile $B00 + ASCII, palette {pn}), no plate behind it',
             col * 8, (row - 2) * 8)
        col, row = FRAME_CELL[side]; grid = vram_grid(v0, col, row, 3, 3)[0]
        a, b = grid_img(g, grid, P0, 7), grid_img(g, grid, P1, 7)
        save(a, f'portrait_frame_{side}.png', f'{side.upper()} portrait frame (palette 7; centre cell transparent)', col * 8, (row - 2) * 8)
        if a.tobytes() != b.tobytes():
            save(b, f'portrait_frame_{side}_phase1.png', 'portrait frame in blink phase 1', col * 8, (row - 2) * 8)
        (col, row), grid = WIN_LABEL[side]; check(v0, col, row, grid, 'WIN')
        for ph, P in ((0, P0), (1, P1)):
            save(grid_img(g, grid, P, 7), f'win_{side}_phase{ph}.png', f'{side.upper()} "WIN" label, blink phase {ph} (palette 7)',
                 col * 8, (row - 2) * 8, anim={'frames': [f'win_{side}_phase0.png', f'win_{side}_phase1.png'], 'ticks_each': period})
        col, row = BOX_CELL[side]
        for state, tiles in BOXES.items():
            for ph, P in ((0, P0), (1, P1)):
                save(grid_img(g, [tiles], P, 7), f'rounds_{side}_{state}_phase{ph}.png',
                     f'{side.upper()} round-win boxes, won: {state} (palette 7, blink phase {ph})', col * 8, (row - 2) * 8)
    check(v0, *BOX_CELL['p1'], [BOXES['none']], 'boxes p1'); check(v0, *BOX_CELL['p2'], [BOXES['none']], 'boxes p2')

    # portraits (sprites, character specific: examples of this fight)
    for side, xs in (('p1', (8, 24)), ('p2', (280, 296))):
        keep = {s['i'] for s in portraits if s['x'] in xs}
        im = render(g, v0, P0, fix=False, keep=keep, backdrop=False).crop((xs[0], 8, xs[0] + 32, 40))
        s0 = next(s for s in portraits if s['x'] == xs[0])
        save(im, f'portrait_{side}_example.png', f'{side.upper()} portrait as drawn in this fight ({"Kyo" if side == "p1" else "Joe"}): '
             f'2x2 C-ROM sprite tiles {[hex(t) for t, a in s0["tiles"]]}..., palette {s0["tiles"][0][1] >> 8:#x}, '
             f'{"h-flipped" if s0["tiles"][0][1] & 1 else "not flipped"}; under the fix frame', xs[0], 8)

    # 5. POW: labels, gauge full / empty, fill per power value, MAXIMUM (blink)
    for side in ('p1', 'p2'):
        (col, row), grid = POW_LABEL[side]; check(v0, col, row, grid, 'POW label')
        save(grid_img(g, grid, P0, 6), f'pow_label_{side}.png', f'{side.upper()} "POW" label (palette 6)', col * 8, (row - 2) * 8)
        check(v0, *POW_CELL[side], POW_EMPTY, 'pow empty')
    pf, pe = grid_img(g, POW_FULL, P0, 6), grid_img(g, POW_EMPTY, P0, 6)
    save(pf, 'pow_gauge_full.png', 'POW gauge, full (power 126; same tiles both sides, palette 6)', None, None,
         positions={'p1': [40, 200], 'p2': [216, 200]})
    save(pe, 'pow_gauge_empty.png', 'POW gauge, empty (power 0)', None, None, positions={'p1': [40, 200], 'p2': [216, 200]})
    fr = [11 + 2 * k for k in range(127)] + [300, 300 + period]
    pk = ';'.join(f'{10 + 2 * k}:108219={k:02X},108419={k:02X}' for k in range(127)) + ';290:108219=7F,108419=7F'
    sw = run('pow', fr, work, pokes=pk)
    pow_tab = {'p1': {}, 'p2': {}}
    for k in range(127):
        v = sw[11 + 2 * k][0]
        for side in ('p1', 'p2'):
            tiles = vram_grid(v, *POW_CELL[side], 8, 2)[0]
            n, s = fill_px(grid_img(g, tiles, P0, 6), pf, pe)
            assert (s == 'F' * n + 'E' * (len(s) - n)) if side == 'p1' else (s == 'E' * (len(s) - n) + 'F' * n), (side, k, s)
            pow_tab[side][k] = n
    assert pow_tab['p1'] == pow_tab['p2'], 'POW fill differs between the sides'
    assert all(n == max(0, k // 2 - 3) for k, n in pow_tab['p1'].items()), pow_tab['p1']
    for f in fr[-2:]:
        for side in ('p1', 'p2'): check(sw[f][0], *POW_CELL[side], MAXIMUM, 'MAXIMUM')
    for ph, P in ((0, P0), (1, P1)):
        save(grid_img(g, MAXIMUM, P, 7), f'pow_maximum_phase{ph}.png', f'"MAXIMUM" shown in place of the gauge at power 127 '
             f'(palette 7, blink phase {ph})', None, None, positions={'p1': [40, 200], 'p2': [216, 200]},
             anim={'frames': ['pow_maximum_phase0.png', 'pow_maximum_phase1.png'], 'ticks_each': period})

    # 6. fonts (for names / other text): both fonts, both side palettes
    for font, base_t in (('font_label', 0x300), ('font_name', 0xB00)):
        for pn in (2, 3):
            grid = [[base_t + 0x20 + r * 16 + c for c in range(16)] for r in range(4)]
            save(grid_img(g, grid, P0, pn), f'{font}_pal{pn}.png', f'{"label" if font == "font_label" else "name"} font, ASCII $20-$5F '
                 f'(16 per row, 8x8 each; tile ${base_t:X} + code), palette {pn} ({"P1 blue" if pn == 2 else "P2 red"})', None, None)

    pals = {'phase0': {str(p): [{'word': f'{w:04X}', 'rgb': list(rgb(w))} for w in P0[p * 16:p * 16 + 16]] for p in range(16)},
            'phase1_changes': {str(p): [{'word': f'{w:04X}', 'rgb': list(rgb(w))} for w in P1[p * 16:p * 16 + 16]] for p in (5, 7)}}
    def runs(tab):
        out, prev = [], None
        for k in sorted(tab):
            if tab[k] != prev: out.append([k, tab[k]]); prev = tab[k]
        return out
    meta = {
        'source': 'The King of Fighters \'95 (SNK 1995, /data/roms/kof95.neo) in our emulator (emu/neogeo_sdl --capture, Geolith), '
                  'state /data/neogeo_dict/ngsdl_sta/kof95/vs_kyo.state (2P versus, Kyo vs Joe); made by tools/kof95/hud_export.py',
        'screen': [320, 224], 'coords': 'x, y = top-left pixel in KOF95\'s 320x224 frame; null when the file is used at several places (see positions)',
        'colour': 'Neo Geo 16-bit colour -> 8-bit RGB: 5 bits per gun (4 + the shared LSB), linear (x * 255 / 31), dark bit ignored; colour 0 transparent',
        'blink': {'palettes': [5, 7], 'ticks_each_phase': period, 'note': 'global 2-phase blink of fix palettes 5 and 7, '
                  'always running; phase 0 = palette 5 equal to palette 4'},
        'life': {'max': 207, 'fill_px': 'min(floor(life / 2), 102) (0-102 px), measured for every odd value 1-205',
                 'fill_columns': {'p1': 'PNG x 0-101 (screen 40-141); n px = PNG x 102-n .. 101',
                                  'p2': 'PNG x 2-103 (screen 178-279); n px = PNG x 2 .. 1+n'},
                 'fill_anchor': {'p1': 'right (inner end, next to the timer); empties from the portrait side',
                                 'p2': 'left (inner end, next to the timer); empties from the portrait side'},
                 'draw': 'draw life_pX_empty, then life_pX_full clipped to the fill columns; only columns where full and empty differ count',
                 'damage': 'no separate damage colour: the shown life follows the real one at 2 units (1 px) per frame, the lost part is the empty checker',
                 'low_life': f'shown life below {min(low_at.values()) + 1 if low_at else "?"} -> the bar uses palette 5 (blinks to life_pX_full_lowflash every {period} frames)',
                 'measured': {s: runs(t) for s, t in life_tab.items()}},
        'pow': {'max': 127, 'fill_anchor': {'p1': 'left (next to POW)', 'p2': 'right (next to POW)'},
                'fill_px': 'max(0, floor(power / 2) - 3) (0-60 px), measured for every power 0-126 on both sides',
                'fill_columns': {'p1': 'PNG x 2-61 (screen 42-101); n px = PNG x 2 .. 1+n',
                                 'p2': 'PNG x 2-61 (screen 218-277); n px = PNG x 62-n .. 61'},
                'fill_px_by_power': runs(pow_tab['p1']),
                'max_state': 'power 127 replaces the gauge by MAXIMUM (palette 7 blink); no other gauge animation '
                             '(charging with A+B+C only fills the gauge)'},
        'timer': {'digits': 'tens digit = timer_tens_N.png at x 144, units = timer_units_N.png at x 160 (y 16); '
                            'glyph tiles $E00 + (n div 8) * $30 + 2 * (n mod 8), n = digit (tens) or 10 + digit (units)'},
        'rounds': 'P2 fills the box next to its WIN first (state "right"), measured in a saved fight; P1 assumed mirrored '
                  '("left" first) — not captured',
        'palettes': pals,
        'files': files,
    }
    json.dump(meta, open(os.path.join(out, 'hud.json'), 'w'), indent=1)
    write_readme(out, meta)
    print(len(files), 'files; blink period', period, 'low life below', low_at, 'phase frames', F0, F1)
    return meta

README = """# KOF95 battle HUD

The in-battle HUD of The King of Fighters '95 (SNK 1995) as PNGs: RGBA, colour 0 transparent, native pixel size, the
game's own palettes. Captured in our emulator (emu/neogeo_sdl --capture) from a 2P versus fight (Kyo vs Joe), rendered
from VRAM + palette RAM; every tile grid below is checked against the game's VRAM. Regenerate with
`python3 tools/kof95/hud_export.py` (repo NeoScanSDK). `hud.json` has everything here in machine form (+ all 16 fix
palettes as Neo Geo words and RGB, the measured fill tables).

Screen: 320x224. `x, y` = top-left of the PNG in that frame. KOF95 masks columns 0-7 and 312-319 with black fix tiles
(our emulator's screenshot is the 304-px middle).

## How it is built

- Everything except the two portraits is the **fix layer** (8x8 S-ROM tiles, palettes 0-15). The sprites under the POW
  gauges in a VRAM dump are the stage's water sparkles, not HUD.
- **Blink**: fix palettes 5 and 7 alternate between two sets every {period} frames, always (phase 0 / phase 1 files).
  Palette 7 = WIN labels, round boxes, MAXIMUM; palette 5 = the life bar at low life.
- **Life** (0-207): fill = min(floor(life / 2), 102) px. The bar fills from its inner end (next to the timer) and
  empties from the portrait side. Draw `life_pX_empty`, then `life_pX_full` over the fill columns: P1 PNG x 102-n..101,
  P2 PNG x 2..1+n (n = fill px; the other columns are the same in both images). No separate damage colour:
  the shown life follows the real one at 1 px per frame and the lost part is the empty checker.
  Below {low} the bar switches to palette 5 and blinks: phase 1 = `life_pX_full_lowflash` / `life_pX_empty_lowflash`.
- **POW** (0-127): fill = max(0, floor(power / 2) - 3) px (0-60), from the POW label side: P1 PNG x 2..1+n, P2 PNG
  x 62-n..61; the gauge tiles are the same for both sides. At 127 the gauge is replaced by MAXIMUM (palette 7 blink). Charging
  (A+B+C held) only fills the gauge, there is no other gauge animation.
- **Timer**: tens digit at (144, 16), units at (160, 16), 16x24 each, opaque (box background included). The tens and
  units glyph sets differ slightly; use each at its own place.

## Files

| File | What | Size | x, y |
|---|---|---|---|
{rows}

## Not extracted / limits

- 1P-vs-CPU HUD: only 2P versus was captured; row 3 shows "CHALLENGER!" there. What a 1P game shows instead is not captured.
- Names / portraits are per character: only Kyo (P1) and Joe (P2) as examples. Names are text in the name font
  (`font_name_*`: letters A-Z only, tile $B00 + ASCII); the portrait table in the ROM is not decoded.
- Round boxes: P2 fills the box next to its WIN first (seen in a saved fight). P1's order ("left" first) is assumed, not captured.
- Timer infinity / time-out displays, the CREDITS line, round-call / KO / win-screen texts: not exported.
- RGB conversion is the linear 5-bit one (dark bit ignored); the emulator's "resnet" output is a few levels different.
"""

def write_readme(out, meta):
    rows = []
    for f in meta['files']:
        pos = f'{f["x"]}, {f["y"]}' if f.get('x') is not None else \
            ('; '.join(f'{k}: {v[0]}, {v[1]}' for k, v in f['positions'].items()) if f.get('positions') else '-')
        anim = f' Animation: {" / ".join(f["anim"]["frames"])}, {f["anim"]["ticks_each"]} frames each.' if f.get('anim') else ''
        rows.append(f'| `{f["file"]}` | {f["what"]}.{anim} | {f["w"]}x{f["h"]} | {pos} |')
    open(os.path.join(out, 'README.md'), 'w').write(README.format(period=meta['blink']['ticks_each_phase'],
        low=meta['life']['low_life'].split(' -> ')[0].replace('shown life below ', 'a shown life of '), rows='\n'.join(rows)))

if __name__ == '__main__':
    main(*sys.argv[1:])
