#!/usr/bin/env python3
"""The bonus stages' scenes (TODO T7, Bruno 2026-10-14: "the wooden prop from Art of Fighting 2 and the big tree also
from Art of Fighting 2 key training"): Art of Fighting 2's own sprite words, from the VRAM + palette RAM dumps of
tools/aof/bonus_rip.py (/data/neogeo_dict/aof/rip, taken in our emulator) and the C ROM of /data/roms/aof2.neo.

Two scenes, each a stage_t (stage.h's type: main.c draws it as a stage, the camera fixed) + its objects:
- tree  (Spirit Training): the forest (AOF2 sprites 11-31 at frame 500: 21 columns from screen x -6, the layer's rows
        that show), the big tree (sprites 49-59: 11 columns), the falling leaf (sprite 305.. at frame 800: tile $6DF0,
        palette 47), the punch mark on the bark (sprite 60, 5 x 1, frames 750 / 800).
- posts (Initiate Super Death Blow): the temple (sprites 1-20 at frame 510: 20 columns, screen x 0), the wooden post
        (sprites 21-24, 4 x 8 tiles: intact at 510, burnt by the super at 558 / 840 / 1116), its 6 splinter shapes
        (palette 59 chains at frames 558 / 1410).
Every word keeps AOF2's tile (bits 16-19 in the attribute's bits 4-7), flips and auto-animation bits; palettes are
renumbered BONUS_PAL + k per scene in AOF2's order (one scene loaded at a time: the stage's palette block, STAGE_PAL).
Tiles are appended after what bm_c1 / bm_c2.bin hold (after make_sparks.py), each AOF2 tile stored once (an
auto-animated group copied whole and aligned).

    python3 make_bonus.py OUTDIR    -> OUTDIR/bonus.h, bonus_<scene>.png (the scene as drawn from the build's tiles), patched bm_c*.bin"""
import os, struct, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'aof')); sys.path.insert(0, os.path.join(HERE, '..'))
from bonus_rip import sprites, OUT as RIP
from tile_encoder import encode_crom_tile

NEO = '/data/roms/aof2.neo'
STAGE_PAL = 80                             # make_stage_ra.py: the stage's palette block (main.c stage_pals)

SCENES = {                                 # backdrop: (dump, first sprite, last sprite), world x of AOF2's screen x 0
    'tree': {'bg': ('spirit_500', 11, 31), 'cam': 6, 'floor': 206},
    'posts': {'bg': ('posts_510', 1, 20), 'cam': 0, 'floor': 206},
}
OBJECTS = {                                # name: scene, [(dump, first sprite, last sprite)] = its images
    'tree': ('tree', [('spirit_500', 49, 59)]),
    'leaf': ('tree', [('spirit_800', 305, 305), ('spirit_850', 306, 306)]),
    'mark': ('tree', [('spirit_750', 60, 64), ('spirit_800', 60, 64)]),
    'fall': ('tree', [('spirit_top_740', 225, 237), ('spirit_top_770', 225, 239), ('spirit_top_810', 225, 243)]),
    'post': ('posts', [('posts_510', 21, 24), ('posts_558', 21, 24), ('posts_840', 21, 24), ('posts_1116', 21, 24)]),
    'piece': ('posts', [('posts_558', 264, 264), ('posts_558', 265, 265), ('posts_558', 268, 268), ('posts_558', 269, 270),
                        ('posts_1410', 277, 278), ('posts_1410', 281, 282)]),
}


def load_crom():
    d = open(NEO, 'rb').read()
    sz = struct.unpack('<6I', d[4:0x1C])
    return d[0x1000 + sum(sz[:5]):0x1000 + sum(sz)]


CROM = load_crom()


def tile_px(t):
    tt = CROM[t * 128:(t + 1) * 128]; c1, c2 = tt[0::2], tt[1::2]; px = np.zeros((16, 16), np.uint8)
    for half, x0 in ((0, 8), (1, 0)):
        for y in range(16):
            o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
            for x in range(8): px[y, x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
    return px


def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def group(aw):                             # auto-animation: the tile group size its attribute asks for
    return 8 if aw & 8 else 4 if aw & 4 else 1


def empty(t, aw):
    k = group(aw); b = t & ~(k - 1) if k > 1 else t
    return not any(tile_px(b + i).any() for i in range(k))


def dump(name):
    return open(f'{RIP}/{name}.vram', 'rb').read(), open(f'{RIP}/{name}.pal', 'rb').read()


def cols_of(name, lo, hi):
    """sprites lo..hi of a dump -> [(x, y, [(tile, attr)] rows as the screen shows them: a full-height (32) chain's rows
    wrapped and cut to screen y -16..239)]"""
    v, _ = dump(name)
    out = []
    for s in sprites(v):
        if not lo <= s['i'] <= hi: continue
        rows = s['tiles'][:s['h']]
        if s['h'] >= 32:                                   # a 512 px column: the rows that land on screen, from the top
            ys = [((s['y'] + 16 * r + 16) & 511) - 16 for r in range(32)]
            vis = sorted((y, r) for r, y in enumerate(ys) if -16 < y < 224)
            out.append((s['x'], vis[0][0], [rows[r] for _, r in vis]))
        else: out.append((s['x'], s['y'], rows))
    return out


def trim(cols):
    """an object's columns -> (x0, y0, w, h, [[(tile, attr)] per column]): empty rows / columns at the edges cut"""
    x0 = min(x for x, _, _ in cols); y0 = min(y for _, y, _ in cols)
    W = (max(x for x, _, _ in cols) - x0) // 16 + 1; H = max((y - y0) // 16 + len(r) for _, y, r in cols)
    grid = [[(0, 0)] * H for _ in range(W)]
    for x, y, rows in cols:
        for r, (t, a) in enumerate(rows):
            if not empty(t, a): grid[(x - x0) // 16][(y - y0) // 16 + r] = (t, a)
    used_r = [r for r in range(H) if any(grid[c][r][0] for c in range(W))]
    used_c = [c for c in range(W) if any(t for t, _ in grid[c])]
    r0, r1, c0, c1 = used_r[0], used_r[-1], used_c[0], used_c[-1]
    return x0 + 16 * c0, y0 + 16 * r0, c1 - c0 + 1, r1 - r0 + 1, [col[r0:r1 + 1] for col in grid[c0:c1 + 1]]


# ---- AOF2's own screens around a bonus game (notes 20261014-085447-5d29 "the classic screen from Art of Fighting 2
# showing the message 'Bonus Game!'", 20261014-085507-5d29 "the shouting in Japanese with the kanji written on the
# screen", Bruno 2026-10-14 "AOF2's ORIGINAL bonus select screen"): dumps of tools/aof/bonus_rip.py screens (AOF2's
# order and timing in its docstring). Sprites are copied as AOF2's chains (tiles, flips, palettes); AOF2's fix-layer
# texts (the select's title / TIME / messages, the title cards' kanji and names) are baked into sprite tiles of ours
# (2 x 2 fix tiles a tile, the pens of the fix palettes they use merged into palettes of 15 colours), so each screen
# is sprites + palettes only (our fix layer keeps its bottom line). Palettes: SCREEN_PAL + k per screen (one screen at a
# time, the stage's block). Sprite numbers from 1 in AOF2's order (bonus.h bscr_obj_t.spr; main.c hides 1..BSCR_SPRS
# when a screen ends: the stage, shadows and fighters write theirs again).
SCREEN_PAL = STAGE_PAL
INTRO = [f'intro_{f}' for f in range(2964, 2984)]        # tick 0 = AOF2's frame 2964 (black), the zoom 2966-2980
SEL_PICS = [(21, 34), (35, 48), (49, 59)]                # the pictures of slots 0-2 (AOF2's sprites)
SEL_FRAME, SEL_BACK, SEL_BOX = (60, 64), (1, 20), (65, 81)
MSGS = ['select_gen', 'select_0', 'select_1', 'select_2']  # the message box's text: general, then slot 0-2's
CARDS = {0: 'card_0', 2: 'card_2'}                        # the title cards ripped (slot: dump); build_tables BONUS_SLOTS
GREY = 0.55                                              # a slot without a game: its picture's palettes grey, darkened


def load_srom():
    d = open(NEO, 'rb').read(); sz = struct.unpack('<6I', d[4:0x1C])
    return d[0x1000 + sz[0]:0x1000 + sz[0] + sz[1]]


SROM = load_srom()


def fix_px(t):                                           # an S ROM tile -> 8 x 8 pens (make_hud.sdecode)
    b = SROM[t * 32:t * 32 + 32]; px = np.zeros((8, 8), np.uint8)
    for cl, cr, base in ((4, 5, 0), (6, 7, 8), (0, 1, 16), (2, 3, 24)):
        for y in range(8): px[y, cl], px[y, cr] = b[base + y] & 15, b[base + y] >> 4
    return px


def word_of(r, g, b):                                    # 5-bit r g b -> a Neo Geo colour word (rgb()'s inverse)
    return (r >> 1) << 8 | (r & 1) << 14 | (g >> 1) << 4 | (g & 1) << 13 | (b >> 1) | (b & 1) << 12


def grey(w):
    r, g, b = (((w >> 7) & 0x1E) | ((w >> 14) & 1)), (((w >> 3) & 0x1E) | ((w >> 13) & 1)), (((w << 1) & 0x1E) | ((w >> 12) & 1))
    y = min(31, round((0.30 * r + 0.59 * g + 0.11 * b) * GREY)); return word_of(y, y, y)


class Screen:
    """one screen's palettes (AOF2's sprite palettes copied, fix pens merged) and objects (chains of ours)"""
    def __init__(self, name, tile, newtile):
        self.name, self.tile, self.newtile = name, tile, newtile
        self.pals = []; self.keys = {}; self.fixsets = []; self.spr = 1; self.objs = []

    def pal(self, words, key):                           # an AOF2 palette (or its grey copy) -> its number here
        if key not in self.keys: self.keys[key] = len(self.pals); self.pals.append(list(words))
        return SCREEN_PAL + self.keys[key]

    def chains(self, dname, lo, hi, greyed=False):
        """AOF2's sprites lo..hi of a dump -> [(x, y, w, h, map words)] (a head and its sticky sprites = one chain)"""
        v, praw = dump(dname); pw = lambda n: [struct.unpack('>H', praw[(n * 16 + i) * 2:(n * 16 + i) * 2 + 2])[0] for i in range(16)]
        out = []
        for s in sprites(v):
            if not lo <= s['i'] <= hi: continue
            if not s['sticky']: out.append([s['x'], s['y'], 0, s['h'], []])
            col = []
            for t, aw in s['tiles'][:out[-1][3]]:
                nt = self.tile(t, aw)
                if not nt: col += [0, 0]; continue
                p = aw >> 8; words = pw(p)
                pn = self.pal([words[0]] + [grey(x) for x in words[1:]], ('g', dname, p)) if greyed else self.pal(words, ('p', dname, p))
                col += [nt & 0xFFFF, pn << 8 | ((nt >> 16) & 0xF) << 4 | (aw & 0xF)]
            out[-1][2] += 1; out[-1][4] += col
        return [tuple(o) for o in out]

    def fixbake(self, dname, rows, cells=None):
        """the fix layer's non-empty cells in rows (r0, r1) of a dump (or the given {(col, row): (tile, pal)}) -> one chain:
        x = first column * 8, y = r0 * 8 - 16, a tile per 2 x 2 cells, each tile's colours in a palette of merged pens"""
        v, praw = dump(dname); w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]
        fw = lambda n, i: struct.unpack('>H', praw[(n * 16 + i) * 2:(n * 16 + i) * 2 + 2])[0]
        if cells is None:
            cells = {}
            for c in range(1, 39):
                for r in range(rows[0], rows[1] + 1):
                    x = w(0x7000 + c * 32 + r)
                    if fix_px(x & 0xFFF).any(): cells[(c, r)] = (x & 0xFFF, x >> 12)
        assert cells, (dname, rows)
        c0 = min(c for c, _ in cells); c1 = max(c for c, _ in cells); r0 = rows[0]
        W, H = (c1 - c0) // 2 + 1, (rows[1] - r0) // 2 + 1
        img = np.zeros((H * 16, W * 16), np.int32) - 1    # colour words (-1: transparent)
        for (c, r), (t, p) in cells.items():
            px = fix_px(t); x, y = (c - c0) * 8, (r - r0) * 8
            for yy in range(8):
                for xx in range(8):
                    if px[yy, xx]: img[y + yy, x + xx] = fw(int(p), int(px[yy, xx]))
        m = []
        for cx in range(W):
            for ry in range(H):
                blk = img[ry * 16:ry * 16 + 16, cx * 16:cx * 16 + 16]
                cols = sorted(set(blk[blk >= 0].tolist()))
                if not cols: m += [0, 0]; continue
                assert len(cols) <= 15, (dname, rows, cx, ry, len(cols))
                k = next((i for i, s in enumerate(self.fixsets) if len(s | set(cols)) <= 15), None)
                if k is None: self.fixsets.append(set()); k = len(self.fixsets) - 1
                self.fixsets[k] |= set(cols)
                m.append((k, blk))                      # (resolved in close(): the set's final pen order)
                m.append(None)
        return [c0 * 8, r0 * 8 - 16, W, H, m]               # (fix row r = sprite y 8 r - 16: row 2 is the first line shown)

    def close(self, chains):                             # fix chains' pens resolved, the fix palettes appended
        base = len(self.pals)
        order = [sorted(s) for s in self.fixsets]
        for o in order: self.pals.append([0] + o + [0] * (15 - len(o)))
        for ch in chains:
            m = ch[4]
            for i in range(0, len(m), 2):
                if m[i + 1] is None:
                    k, blk = m[i]; pen = {c: j + 1 for j, c in enumerate(order[k])}
                    px = np.zeros((16, 16), np.uint8)
                    for yy in range(16):
                        for xx in range(16):
                            if blk[yy, xx] >= 0: px[yy, xx] = pen[int(blk[yy, xx])]
                    nt = self.newtile(px); m[i] = nt & 0xFFFF; m[i + 1] = (SCREEN_PAL + base + k) << 8 | ((nt >> 16) & 0xF) << 4
        self.fixsets = []
        assert SCREEN_PAL + len(self.pals) <= 240, (self.name, len(self.pals))

    def obj(self, ch, spr=None):                         # a chain -> a bscr_obj_t initializer on sprite spr (default: next)
        if spr is None: spr = self.spr; self.spr += ch[2]
        self.n_obj = getattr(self, 'n_obj', 0) + 1
        nm = f'bscr_{self.name}_m{self.n_obj}'
        self.objs.append(f'static const uint16_t {nm}[] = {{ {", ".join(f"0x{v:04X}" for v in ch[4])} }};')
        return f'{{ {{ {ch[0]}, {ch[1]}, {ch[2]}, {ch[3]}, {nm} }}, {spr} }}'

    def emit(self, h):
        h += self.objs
        h.append(f'static const uint16_t bscr_{self.name}_pal[] = {{ {", ".join(f"0x{v:04X}" for p in self.pals for v in p)} }};')
        h.append(f'#define BSCR_{self.name.upper()}_NPAL {len(self.pals)}')


def screens(h, tile, newtile, outdir):
    h += ['/* AOF2\'s own screens around a bonus game (make_bonus.py "screens"; main.c "bonus stages"): bscr_obj_t = a chain',
          ' * of sprites (bonus_obj_t) on its sprite number; palettes at BSCR_PAL + k, one screen at a time */',
          'typedef struct { bonus_obj_t o; uint16_t spr; } bscr_obj_t;',
          f'#define BSCR_PAL {SCREEN_PAL}']
    sprs = []
    # "BONUS GAME": AOF2's two chains, their zoom: x, y, h shrink, v shrink (-1: not shown) per tick
    s = Screen('intro', tile, newtile)
    ch = s.chains(INTRO[-1], 1, 15)
    objs = [s.obj(c) for c in ch]
    heads = [i for i in range(1, 16) if not any(sp['i'] == i and sp['sticky'] for sp in sprites(dump(INTRO[-1])[0]))]
    track = []
    for d in INTRO:
        v = dump(d)[0]; w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]; row = []
        for i in heads:
            s3, s2 = w(0x8200 + i), w(0x8000 + i)
            y = 496 - (s3 >> 7); y = y - 512 if y > 256 else y
            row.append((w(0x8400 + i) >> 7, y, s2 >> 8, s2 & 0xFF) if s3 & 0x3F else (0, 0, 0, -1))
        track.append(row)
    while len(track) > 1 and track[-1] == track[-2]: track.pop()
    s.emit(h); sprs.append(s.spr)
    h.append(f'#define BSCR_INTRO_N {len(objs)}')
    h.append(f'static const bscr_obj_t bscr_intro[BSCR_INTRO_N] = {{ {", ".join(objs)} }};')
    h.append(f'#define BSCR_ZOOM_N {len(track)}')
    h.append('static const int16_t bscr_zoom[BSCR_ZOOM_N][BSCR_INTRO_N][4] = { ' + ', '.join(
        '{ ' + ', '.join('{ %d, %d, %d, %d }' % r for r in row) + ' }' for row in track) + ' };   /* x, y, h shrink, v shrink (-1: off) */')
    # SELECT BONUS GAME: the grass, the 3 pictures (each also greyed), the cursor frame, the message box, then the fix texts
    s = Screen('sel', tile, newtile)
    back = [s.obj(c) for c in s.chains('select_0', *SEL_BACK)]
    pics, late = [], []
    for k, (a, b) in enumerate(SEL_PICS):
        nrm, gry = s.chains('select_0', a, b), s.chains('select_0', a, b, greyed=True)
        sp0 = s.spr; on = [s.obj(c) for c in nrm]; sp1 = s.spr; s.spr = sp0
        off = [s.obj(c) for c in gry]; assert s.spr == sp1
        late.append(f'static const bscr_obj_t bscr_pic{k}[] = {{ {", ".join(on)} }};')
        late.append(f'static const bscr_obj_t bscr_pic{k}g[] = {{ {", ".join(off)} }};')
        pics.append((len(on), k))
    fr = s.chains('select_0', *SEL_FRAME); assert len(fr) == 1
    frame = s.obj(fr[0])
    frame_x = []
    for d in MSGS[1:]:
        f2 = s.chains(d, *SEL_FRAME); frame_x.append(f2[0][0])
    box = [s.obj(c) for c in s.chains('select_0', *SEL_BOX)]
    fixc = [s.fixbake('select_gen', (4, 5)), s.fixbake('select_gen', (20, 20))]   # the title, TIME (its digit cut below)
    v = dump('select_gen')[0]; w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]
    tc = {(c, 20): (w(0x7000 + c * 32 + 20) & 0xFFF, w(0x7000 + c * 32 + 20) >> 12) for c in range(1, 39) if fix_px(w(0x7000 + c * 32 + 20) & 0xFFF).any()}
    dcol = max(c for c, _ in tc); dpal = tc[(dcol, 20)][1]; assert tc[(dcol, 20)][0] == 0x339, tc   # "TIME 9": '9' = $339 (columns 0 and 39: AOF2's edge masks, off screen)
    fixc[1] = s.fixbake('select_gen', (20, 20), {k: x for k, x in tc.items() if k[0] != dcol})
    digits = [s.fixbake('select_gen', (20, 20), {(dcol, 20): (0x330 + d, dpal)}) for d in range(10)]
    msgs = [s.fixbake(d, (23, 26)) for d in MSGS]
    s.close(fixc + digits + msgs)
    fixed = [s.obj(c) for c in fixc]
    sp = s.spr; dig = [s.obj(c, sp) for c in digits]; s.spr += 1
    msw = max(m[2] for m in msgs); sp = s.spr; ms = [s.obj(c, sp) for c in msgs]; s.spr += msw
    s.emit(h); sprs.append(s.spr)
    h += late
    h.append(f'#define BSCR_SEL_N {len(back) + len(box) + len(fixed)}')
    h.append(f'static const bscr_obj_t bscr_sel[BSCR_SEL_N] = {{ {", ".join(back + box + fixed)} }};   /* grass, box, title, TIME */')
    h.append('typedef struct { uint8_t n; const bscr_obj_t *on, *off; } bscr_pic_t;')
    h.append(f'static const bscr_pic_t bscr_pics[3] = {{ {", ".join(f"{{ {n}, bscr_pic{k}, bscr_pic{k}g }}" for n, k in pics)} }};   /* AOF2 slots 0-2: picture, greyed */')
    h.append(f'static const bscr_obj_t bscr_frame = {frame};   /* the cursor\'s frame (AOF2: on every other frame while picking) */')
    h.append(f'static const int16_t bscr_frame_x[3] = {{ {", ".join(map(str, frame_x))} }};')
    h.append(f'static const bscr_obj_t bscr_digit[10] = {{ {", ".join(dig)} }};   /* TIME\'s digit */')
    h.append(f'#define BSCR_MSG_W {msw}')
    h.append(f'static const bscr_obj_t bscr_msg[4] = {{ {", ".join(ms)} }};   /* the general message, slot 0-2\'s */')
    # the title cards (white; AOF2's fix layer: the kanji, the English name)
    cards = []
    for k in range(3):
        if k not in CARDS: cards.append('{ 0, 0, 0, 0, 0 }'); continue
        s = Screen(f'card{k}', tile, newtile)
        v = dump(CARDS[k])[0]; w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]
        rows = [r for r in range(29) if any(fix_px(w(0x7000 + c * 32 + r) & 0xFFF).any() for c in range(1, 39))]
        bands = []
        for r in rows:
            if bands and r == bands[-1][1] + 1: bands[-1][1] = r
            else: bands.append([r, r])
        bands = [s.fixbake(CARDS[k], tuple(b)) for b in bands]
        s.close(bands); objs = [s.obj(c) for c in bands]
        bd = struct.unpack('>H', dump(CARDS[k])[1][(255 * 16 + 15) * 2:(255 * 16 + 15) * 2 + 2])[0]
        s.emit(h); sprs.append(s.spr)
        h.append(f'static const bscr_obj_t bscr_card{k}[] = {{ {", ".join(objs)} }};')
        cards.append(f'{{ bscr_card{k}_pal, BSCR_CARD{k}_NPAL, 0x{bd:04X}, {len(objs)}, bscr_card{k} }}')
    h.append('typedef struct { const uint16_t *pal; uint8_t npal; uint16_t backdrop; uint8_t n; const bscr_obj_t *objs; } bscr_card_t;')
    h.append(f'static const bscr_card_t bscr_cards[3] = {{ {", ".join(cards)} }};   /* AOF2 slots 0-2 (n 0: none ripped) */')
    h.append(f'#define BSCR_SPRS {max(sprs)}   /* sprites 1..BSCR_SPRS - 1: the screens\' */')


FALL_MARK = 700                                        # spirit_top: the punch mark's first frame (main.c: the blow's tick)
FALL_REFS = ['spirit_top_740', 'spirit_top_770', 'spirit_top_810']   # = OBJECTS 'fall': each image's dump
def fall_seq():
    """the top grade's tree (note 20261014-133606-5d29): AOF2's tree chain (sprites 225..) in every spirit_top dump, as
    keyframes [tick from the mark, image (bonus_fall), dx, dy from the image's place in its dump, SCB2 vertical shrink]
    where something changes; main.c bn_gauge_flow plays it from the blow on a winning grade"""
    def chain(name):
        ss = [s for s in sprites(dump(name)[0]) if 225 <= s['i'] <= 260]
        v = dump(name)[0]; scb2 = v[(0x8000 + 225) * 2] << 8 | v[(0x8000 + 225) * 2 + 1]
        return (len(ss), ss[0]['x'], ss[0]['y'], scb2 & 0xFF) if ss else None
    refs = [chain(n) for n in FALL_REFS]
    out, last = [], None
    for f in range(FALL_MARK, 1000, 2):
        if not os.path.exists(f'{RIP}/spirit_top_{f}.vram'): continue
        c = chain(f'spirit_top_{f}')
        if not c: continue
        img = next(k for k, r in enumerate(refs) if r[0] == c[0])
        e = (img, c[1] - refs[img][1], c[2] - refs[img][2], c[3])
        if e != last: out.append((f - FALL_MARK,) + e); last = e
    return ['/* the top grade\'s falling tree: {tick from the blow, image (bonus_fall), dx, dy, vertical shrink} (make_bonus fall_seq) */',
            'typedef struct { uint16_t t; uint8_t img; int8_t dx, dy; uint8_t vs; } bonus_fall_t;',
            f'#define BONUS_N_FALLSEQ {len(out)}',
            f'#define BONUS_FALL_MAXW {max(r[0] for r in refs)}',
            'static const bonus_fall_t bonus_fall_seq[BONUS_N_FALLSEQ] = { ' + ', '.join(f'{{{t}, {i}, {dx}, {dy}, 0x{vs:02X}}}' for t, i, dx, dy, vs in out) + ' };']


def build(outdir):
    c1p, c2p = os.path.join(outdir, 'bm_c1.bin'), os.path.join(outdir, 'bm_c2.bin')
    c1, c2 = bytearray(open(c1p, 'rb').read()), bytearray(open(c2p, 'rb').read())
    remap = {}
    def tile(t, aw):                                       # AOF2 tile -> ours (a group copied whole, aligned)
        if empty(t, aw): return 0
        k = group(aw); b = t & ~(k - 1) if k > 1 else t
        if b not in remap:
            while k > 1 and (len(c1) // 64) % k: c1.extend(bytes(64)); c2.extend(bytes(64))
            remap[b] = len(c1) // 64
            for i in range(k):
                tt = CROM[(b + i) * 128:(b + i + 1) * 128]; c1.extend(tt[0::2]); c2.extend(tt[1::2])
        return remap[b] + (t - b)
    h = ['/* Generated by tools/brawler/make_bonus.py (Art of Fighting 2\'s bonus scenes, /data/neogeo_dict/aof/rip). Do not edit. */',
         '#ifndef BONUS_H', '#define BONUS_H', '#include "stage.h"',
         '/* an object: w x h tiles, column-major (tile low word, attribute: palette BONUS_PAL-relative already placed, tile bits 16-19,',
         ' * flips, auto-animation); x, y = its top left on AOF2\'s screen (world x = x + the scene\'s cam) */',
         'typedef struct { int16_t x, y; uint8_t w, h; const uint16_t *map; } bonus_obj_t;',
         'typedef struct { stage_t st; int16_t cam; } bonus_scene_t;']
    scenes, objs = [], {}
    for si, (sn, sc) in enumerate(SCENES.items()):
        d, lo, hi = sc['bg']
        bg = cols_of(d, lo, hi)
        x0 = bg[0][0]; y0 = min(y for _, y, _ in bg); nr = max((y - y0) // 16 + len(r) for _, y, r in bg)
        assert all(x == x0 + 16 * i for i, (x, _, _) in enumerate(bg)), 'backdrop columns not contiguous'
        assert x0 == -sc['cam'], (sn, x0)
        words = [w for _, _, r in bg for w in r]
        mine = [(o, ims) for o, (scn, ims) in OBJECTS.items() if scn == sn]
        ob = {o: [trim(cols_of(dn, a, b)) for dn, a, b in ims] for o, ims in mine}
        words += [w for o in ob.values() for im in o for col in im[4] for w in col]
        pal_raw = dump(d)[1]
        pals = sorted({aw >> 8 for t, aw in words if t and not empty(t, aw)})
        assert STAGE_PAL + len(pals) <= 240, pals
        pw = lambda n: [struct.unpack('>H', pal_raw[(n * 16 + i) * 2:(n * 16 + i) * 2 + 2])[0] for i in range(16)]
        def word(t, aw):
            nt = tile(t, aw)
            if not nt: return (0, 0)
            return (nt & 0xFFFF, ((STAGE_PAL + pals.index(aw >> 8)) << 8) | ((nt >> 16) & 0xF) << 4 | (aw & 0xF))
        m = []
        for x, y, rows in bg:
            col = [(0, 0)] * nr
            for r, (t, aw) in enumerate(rows): col[(y - y0) // 16 + r] = word(t, aw)
            m += [v for w in col for v in w]
        h.append(f'static const uint16_t bonus_{sn}_map[] = {{ {", ".join(f"0x{v:04X}" for v in m)} }};')
        h.append(f'static const uint16_t bonus_{sn}_pal[] = {{ {", ".join(f"0x{v:04X}" for n in pals for v in pw(n))} }};   /* AOF2 palettes {pals} */')
        scenes.append(f'{{ {{ bonus_{sn}_map, bonus_{sn}_pal, {len(bg)}, {nr}, {len(pals)}, {y0}, {sc["floor"]}, 0x{pw(255)[15]:04X}, 0, 0, 0xFF, 0, 0, 0 }}, {sc["cam"]} }}')
        h.append(f'#define BONUS_{sn.upper()} {si}')
        for o, ims in ob.items():
            names = []
            for k, (ox, oy, w, hh, grid) in enumerate(ims):
                h.append(f'static const uint16_t bonus_{o}{k}[] = {{ {", ".join(f"0x{v:04X}" for col in grid for tw in col for v in word(*tw))} }};')
                names.append(f'{{ {ox}, {oy}, {w}, {hh}, bonus_{o}{k} }}')
            h.append(f'#define BONUS_N_{o.upper()} {len(ims)}')
            h.append(f'static const bonus_obj_t bonus_{o}[BONUS_N_{o.upper()}] = {{ {", ".join(names)} }};')
            objs[o] = ims
        # the scene as the build draws it (a check picture)
        img = Image.new('RGB', (320, 224), (0, 0, 0)); P = img.load()
        def put(sx, sy, t, aw):
            if not t: return
            px = tile_px(t)
            if aw & 1: px = px[:, ::-1]
            if aw & 2: px = px[::-1]
            pl = pw(aw >> 8)
            for yy in range(16):
                for xx in range(16):
                    c = int(px[yy, xx]); X, Y = sx + xx, sy + yy
                    if c and 0 <= X < 320 and 0 <= Y < 224: P[X, Y] = rgb(pl[c])
        for x, y, rows in bg:
            for r, (t, aw) in enumerate(rows): put(x, y + 16 * r, t, aw)
        for o, ims in ob.items():
            ox, oy, w, hh, grid = ims[0]
            for c, col in enumerate(grid):
                for r, (t, aw) in enumerate(col): put(ox + 16 * c, oy + 16 * r, t, aw)
        img.save(os.path.join(outdir, f'bonus_{sn}.png'))
    h += fall_seq()
    h.append(f'#define BONUS_SCENES {len(scenes)}')
    h.append('static const bonus_scene_t bonus_scenes[BONUS_SCENES] = {\n    ' + ',\n    '.join(scenes) + '\n};')
    h.append(f'#define BONUS_MAXROWS {max(len(c) for o in objs.values() for im in o for c in im[4])}')
    synth = {}
    def newtile(px):                                       # a tile of ours (16 x 16 pens) -> its number (stored once)
        if not px.any(): return 0
        k = px.tobytes()
        if k not in synth:
            synth[k] = len(c1) // 64; a, b = encode_crom_tile(px); c1.extend(a); c2.extend(b)
        return synth[k]
    n0 = len(remap)
    screens(h, tile, newtile, outdir)
    print(f'bonus screens: {len(remap) - n0} AOF2 sprite tiles + {len(synth)} fix-layer tiles ({(len(remap) - n0 + len(synth)) * 128 // 1024} KB)')
    h.append('#endif')
    open(c1p, 'wb').write(bytes(c1)); open(c2p, 'wb').write(bytes(c2))
    open(os.path.join(outdir, 'bonus.h'), 'w').write('\n'.join(h) + '\n')
    print(f'bonus: {len(remap)} AOF2 tiles ({len(remap) * 128 // 1024} KB) appended, C ROM now {len(c1) // 64} tiles')


if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit(__doc__)
    build(sys.argv[1])
