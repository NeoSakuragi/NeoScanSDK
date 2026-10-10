#!/usr/bin/env python3
"""Samurai Shodown II fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99 export
(layer 0 of docs/brawler_data_model.md, one code path), the way tools/samsho4, tools/kizuna and tools/doubledr do.

    python3 export_ss2.py OUTDIR [haohmaru genjuro]   -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

Everything comes from the ROM (study /data/neogeo_dict/samsho2/README.md, decoder ss2.py: the game's VRAM pixel for
pixel); captures (moves/CC.json) only name the animations of the basic actions and check the models (handlers_ss2.py):
- frames: a step's sprite definitions (up to 4 layers, the $365E / $367E order, later on top) at full size (1:1: SS2
  shows its fighters unscaled up close), the step's $20 command (a drawing offset while the step shows: the world x
  does not move, measured: Haohmaru's landing anim 3) in the part offsets; SS2's art faces right, the brawler's left:
  every layer mirrored about the feet, per-cell flips baked into flipped tile copies (the brawler flips whole parts);
  one part per run of columns sharing a palette. Feet = the object's y (the sprite top = Y - 16 - y offset, $3368).
- boxes: the $24 records as the collision code reads them ($BA0A / $B92C): [type word: bit 15 = attack (+$26),
  else body (+$3A)][left][width][top][height] x 4 px from the feet, facing right; the attack list is cleared every
  frame ($345E) and set by the steps that carry attack records, the body list stays until a step brings another.
  -> KOF keys: '31' the body union (hurt), '11' the attack union, centre / half extents, x forward negative.
- palettes: the fighter's 8 ($FD10, colour sets A / B: fighter_palettes), the effects' fixed palettes ($216400:
  32-143) and the HUD's ($214000: 0-15) by the palette byte of each cell.
- physics: the velocity table long $6A500[table] ($46BAE: [vx][vy] 8.8 px / frame): walk 0, jumps 2 / 4, gravity 5.
- specials: handlers_ss2.py (the action handlers decoded into brawler programs, variant table A / B / A+B)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import ss2, neo2 as N

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17, 'hanzo': 2}
COLOURS = 2                                       # colour sets per fighter in $FD10 (P1 / the second player's)
FEET = 16                                         # the feet's screen line = Y - 16 ($3368: top = Y - 16 - y offset)

def u8(a): return N.u8(a)
def sb(v): return v - 256 if v > 127 else v

# brawler move -> (SS2 animation, first step, last step (None: to the end)). Animations of the actions (the action
# table $28310, class 0 / 1 / 3: commands_ss2.descriptor), named by the captures (moves.md): idle 0, walk 4 (back 6),
# run 66, jumps up 22 / 26, forward 28 / 32, back 34 / 38 (rise / fall; no prejump: the first frame is airborne),
# landing 178; normals close / far / crouch / jump: A 230 / 232 / 236 / 238, B 250 / 252 / 254 / 258, C 302 / 304 /
# 306 / 310, D 322 / 324 / 326 / 330, A+B 276 / 278 / 280 / 284 (the heavy slash: body_toss, the brawler's C+D),
# C+D 348 / 350 / 352 / 356; reactions (class 3, read on P2 in the captures): reel 110 (light) / 106 (heavy), the
# crouching reel 120 (trip), the knockdown flight 220 (2 steps) and its landing / lying 222, the get-up 138 (from
# its kneeling step 1). 140 (the sheathing pose) is not the round win: WIN below.
MOVES = {
    'idle': (0, 0, None), 'walk_fwd': (4, 0, None), 'run': (66, 0, None),
    'prejump': (22, 0, 0), 'jump_up_rise': (22, 0, None), 'jump_up_fall': (26, 0, None),
    'jump_fwd_rise': (28, 0, None), 'jump_fwd_fall': (32, 0, None),
    'jump_back_rise': (34, 0, None), 'jump_back_fall': (38, 0, None), 'land': (178, 0, None),
    'atk_a_close': (230, 0, None), 'atk_a_far': (232, 0, None), 'atk_b_close': (250, 0, None), 'atk_b_far': (252, 0, None),
    'atk_c_close': (302, 0, None), 'atk_c_far': (304, 0, None), 'atk_d_close': (322, 0, None), 'atk_d_far': (324, 0, None),
    'atk_a_crouch': (236, 0, None), 'atk_b_crouch': (254, 0, None), 'atk_c_crouch': (306, 0, None), 'atk_d_crouch': (326, 0, None),
    'atk_c_jump': (310, 0, None), 'atk_d_jump': (330, 0, None), 'atk_c_jump_diag': (310, 0, None), 'atk_d_jump_diag': (330, 0, None),
    'atk_cd_jump': (284, 0, None), 'body_toss': (278, 0, None),
    'hit_stand_light': (110, 0, None), 'hit_stand_heavy': (106, 0, None), 'hit_air': (220, 0, 0),
    'blowback': (220, 0, 0), 'blowback_n': (220, 0, 0), 'knockdown_flight': (220, 1, 1), 'knockdown_bounce': (222, 0, 0),
    'knockdown_fall': (222, 0, 0), 'down': (222, 1, 1), 'getup': (138, 1, None), 'trip': (120, 0, None),
}
# the round win (TODO #184): the animation SS2 plays for the winner, read in our emulator (tools/brawler/wins184.py: P1
# lands a slash, the clock runs out with P1 ahead; P1's +$66 after it): Haohmaru 200 (facing the camera, the sword on his shoulder;
# its step 2 sends his voice $1A98), Genjuro 198 (his back turned; step 11 $1CD8), Kuroko 198, Hanzo 198 (TODO #193:
# 0 -> 230 (his slash) -> 2 -> 198, /data/tmp/hanzo193/win/wins184.json)
WIN = {'haohmaru': 200, 'genjuro': 198, 'kuroko': 198, 'hanzo': 198}
def jump_moves(ch):
    """the jumps' animations from the fighter's own class 0 actions [code] ($28310: 6 up, 8 forward, 9 back; a list =
    the rise animation, parameter entries, the fall animation, then the same again for the other weapon mode): rise =
    its first animation, fall = the last one before the list repeats its first handler. Haohmaru: 28 / 32 forward, 34 /
    38 back; Genjuro and Kuroko jump forward / back with 22 / 26 like up (Genjuro's 28-38 are other things: his cards'
    frames, empty steps). 2026-10-07 (feedback 20261007-004728-5d29: the fixed table drew Genjuro's diagonal jumps as
    his hanafuda card and empty frames)"""
    import commands_ss2 as K
    out = {}
    for key, sub in (('jump_up', 6), ('jump_fwd', 8), ('jump_back', 9)):
        ents = K.descriptor(ch, 0, 0, sub)['entries']
        half = next((i for i in range(1, len(ents)) if ents[i][1] == ents[0][1]), len(ents))
        an = [w & 0x3FF for _, _, w in ents[:half] if not w & 0x8000]
        out[key + '_rise'] = (an[0], 0, None); out[key + '_fall'] = (an[-1], 0, None)
    return out

LOOP = {'idle', 'walk_fwd', 'run'}
ALIAS = {'hop_up_rise': 'jump_up_rise', 'hop_up_fall': 'jump_up_fall', 'hop_fwd_rise': 'jump_fwd_rise',
         'hop_fwd_fall': 'jump_fwd_fall', 'hop_back_rise': 'jump_back_rise', 'hop_back_fall': 'jump_back_fall',
         'atk_c_hop': 'atk_c_jump', 'atk_d_hop': 'atk_d_jump', 'atk_c_hop_diag': 'atk_c_jump_diag',
         'atk_d_hop_diag': 'atk_d_jump_diag', 'atk_cd_hop': 'atk_cd_jump'}

def flip_tile(t, hf, vf):
    """a 128-byte .neo C tile (2 halves of 16 rows x 4 bytes; bit 0 = the leftmost pixel of a half) flipped"""
    halves = [t[0:64], t[64:128]]
    if vf: halves = [b''.join(h[r * 4:r * 4 + 4] for r in range(15, -1, -1)) for h in halves]
    if hf: halves = [bytes(int(f'{v:08b}'[::-1], 2) for v in h) for h in halves[::-1]]
    return halves[0] + halves[1]

# palettes past the effect table: palette RAM of a fight (Kuroko's ghost, palette 250: not in $216400's table, where
# 178 / 183 are and match the RAM) [meas: /data/neogeo_dict/samsho2/cap/p1_17.state, both frames 10 and 50]
RAM_PALS = {250: [0x0000, 0x7FFF, 0x2060, 0x7FD9, 0x6FA5, 0x0D61, 0x0830, 0x20FC, 0x00C6, 0x0082, 0x4FD0, 0x2C70, 0x30FD,
                  0x7AAA, 0x7777, 0x0000]}

def fixed_palette(p):
    """a palette the game loads once: 32-143 the effects ($FBD4: $216400; the table goes on past 143: 178 / 183 match the
    RAM), 0-15 the HUD ($214000)"""
    if p in RAM_PALS: return RAM_PALS[p]
    base = 0x216400 + 32 * (p - 32) if p >= 32 else 0x214000 + 32 * p
    return [N.u16(base + 2 * k) for k in range(16)]

class Builder:
    """frames as brawler parts; palettes by absolute SS2 palette number (keys), 16-23 = the fighter's colour set"""
    def __init__(self, ch):
        self.ch = ch; self.c = N.load()[1]
        self.tile_map, self.tiles, self.frames, self.index, self.pals = {}, [], [], {}, []
    def tile(self, code, hf, vf):
        k = (code, hf, vf)
        if k not in self.tile_map:
            raw = self.c[(code * 128) % len(self.c):(code * 128) % len(self.c) + 128]
            if not any(raw): return 0
            self.tile_map[k] = TILE_BASE + len(self.tiles); self.tiles.append(flip_tile(raw, hf, vf))
        return self.tile_map[k]
    def pal(self, p):
        if p not in self.pals: self.pals.append(p)
        return self.pals.index(p)
    def frame(self, st, extra=(), mirror=None):
        """a step (ss2.parse_step) as a frame; extra: more steps drawn with it (objects pinned to the body), each
        (step, dx, dy, facing flip) in SS2's facing-right screen offsets; mirror: the step drawn turned (its flags
        bit 15, SS2 draws the object mirrored about its feet: the throws' thrower, TODO #148 feedback; anim_steps).
        None (the default): the step's own bit 15, for every animation [code: $35E8 tst.w +$74, bpl; eori #1 on the
        display entry's flip +$1C]; the boxes are not turned (the collision reads the object's facing +$7F)"""
        if mirror is None: mirror = bool(st['flags'] & 0x8000)
        mv = next(((c[1], c[2]) for c in st['cmds'] if c[0] == 'move'), (0, 0))
        key = (tuple(st['layers']), st['flags'] & 0x4000, mv,
               tuple((tuple(s['layers']), s['flags'] & 0x4000, dx, dy, fl) for s, dx, dy, fl in extra)) + ((('mirror',) if mirror else ()))
        if key in self.index: return self.index[key]
        parts = []
        for s, ox, oy, fl in [(st, -mv[0] if mirror else mv[0], mv[1], 1 if mirror else 0)] + [(s, dx + next(((c[1]) for c in s['cmds'] if c[0] == 'move'), 0),
                                                         dy + next(((c[2]) for c in s['cmds'] if c[0] == 'move'), 0), fl) for s, dx, dy, fl in extra]:
            nl = len(s['layers'])
            for li in ss2.ORDER[bool(s['flags'] & 0x4000)][nl - 1]:
                parts += self.layer(s['layers'][li], ox, oy, fl, li)
        self.index[key] = len(self.frames)
        self.frames.append({'record': ' '.join(f'{w:04X}' for w in st['layers']), 'parts': parts, 'weapon': None,
                            'ss2': {'layers': st['layers'], 'flags': st['flags'], 'move': list(mv),
                                    'extra': [[s['layers'], s['flags'], dx, dy, fl] for s, dx, dy, fl in extra]}})
        return self.index[key]
    def layer(self, w, ox, oy, facing, li=0):
        """one sprite definition drawn at (ox, oy) from the object (SS2 screen offsets, facing right) -> brawler parts
        (facing left: mirrored about the feet). facing 1: the definition drawn facing left in SS2 (an object turned).
        li: its place in the step's layer list (the second one flickers: flicker_key)"""
        flip = facing ^ (w >> 15)
        sd = ss2.sprite_def(w & 0x7FFF); xo, yo = ss2.place(w & 0x7FFF)
        _, cells = ss2.sprite_cells(w & 0x7FFF)
        wpx = sd['cols'] * 16
        left = (-xo if not flip else -wpx + xo) + ox  # SS2 screen x of the definition's left edge from the object
        top = -yo - FEET + FEET + oy                  # from the feet: top = (Y - 16 - yo) - (Y - 16)
        vis = cells[::-1] if flip else cells          # SS2's columns left to right on screen
        bcols = vis[::-1]                             # mirrored: right to left becomes left to right
        bleft = -(left + wpx)                         # the mirrored left edge
        cols = []                                     # (x, top, palette, {row: tile})
        for ci, col in enumerate(bcols):
            byp, byc = {}, {}
            for r, cell in enumerate(col):
                if cell is None: continue
                t, at = cell
                at ^= flip                            # the handler toggles the flip bit of a turned layer
                code = t | (at >> 4 & 0xF) << 16
                if not code: continue
                tn = self.tile(code, (at & 1) ^ 1, at >> 1 & 1)   # mirrored: every cell flipped once more
                if tn: byp.setdefault(at >> 8, {})[r] = tn; byc.setdefault(at >> 8, set()).add(code)
            for p, rows in byp.items():
                if li == 1: p = flicker_key(self.ch, p, byc[p])
                cols.append((bleft + 16 * ci, top, p, [rows.get(r, 0) for r in range(len(col))]))
        parts = []
        for x, tp, p, t in cols:                      # adjacent columns with the same palette and top: one part
            while t and not t[-1]: t = t[:-1]
            lead = 0
            while t and not t[0]: t = t[1:]; lead += 1
            if not t: continue
            q = parts[-1] if parts else None
            if q and q['_p'] == p and q['_top'] == tp + 16 * lead and q['_x'] + 16 * len(q['tiles']) == x:
                q['tiles'].append(t); continue
            parts.append({'_p': p, '_top': tp + 16 * lead, '_x': x, 'tiles': [t]})
        out = []
        for q in parts:
            n = max(len(t) for t in q['tiles'])
            out.append({'dx': q['_x'], 'dy': q['_top'], 'hflip': 0, 'vflip': 0, 'pal': self.pal(q['_p']),
                        'tiles': [t + [0] * (n - len(t)) for t in q['tiles']]})
        return out

def box_list(st, prev_body):
    """(body records, attack records) live on a step: the attack list is the step's own, the body list the last given"""
    body = [l for w, l in st['boxes'] if not w & 0x8000]
    atk = [l for w, l in st['boxes'] if w & 0x8000]
    return (body if body else prev_body), atk

def kof_box(recs):
    """union of SS2 records ([left][width][top][height] x 4 px, facing right) as KOF's (cx, cy, hw, hh), x forward -"""
    l = min(sb(r >> 24) * 4 for r in recs); r_ = max(sb(r >> 24) * 4 + (r >> 16 & 255) * 4 for r in recs)
    t = min(sb(r >> 8 & 255) * 4 for r in recs); b = max(sb(r >> 8 & 255) * 4 + (r & 255) * 4 for r in recs)
    cx, cy = -(l + r_) // 2, (t + b) // 2
    return [max(-128, min(127, cx)), max(-128, min(127, cy)), min(255, max(1, (r_ - l + 1) // 2)), min(255, max(1, (b - t + 1) // 2))]

def kof_boxes(body, atk):
    out = {}
    if body: out['31'] = kof_box(body)
    if atk: out['11'] = kof_box(atk)
    return out

def first_body(ch, a):
    """the body boxes in force when animation a starts: its first step's, else the first its steps bring"""
    for s in ss2.parse_anim(ch, a, 400):
        b = [l for w, l in s['boxes'] if not w & 0x8000]
        if b: return b
    return []

def anim_steps(B, ch, a, first=0, last=None, mirror=True):
    """animation a's steps first..last as brawler steps; mirror: a step whose flags have bit 15 is drawn turned (SS2's
    display list shows those steps h-flipped with the object's facing unchanged: Haohmaru's / Genjuro's throws 274 /
    346, measured on moves/00.json, 12.json close_throw_*); every animation honours it (2026-10-07: Genjuro's 208 / 270,
    Kuroko's 55 ...): mirror=False only to draw a step unturned on purpose"""
    st = ss2.parse_anim(ch, a, 400)
    body = first_body(ch, a); rows = []
    for i, s in enumerate(st):
        body, atk = box_list(s, body)
        rows.append((s, body, atk))
    sel = rows[first:None if last is None else last + 1]
    out = []
    for i, (s, body, atk) in enumerate(sel):
        nxt = sel[i + 1] if i + 1 < len(sel) else None
        fl = (0x100 if atk else 0) | (0x4000 if atk and nxt is not None and nxt[2] else 0)
        out.append({'frame': B.frame(s, mirror=mirror and bool(s['flags'] & 0x8000)), 'ticks': s['ticks'], 'flags': fl, 'dx': 0, 'boxes': kof_boxes(body, atk),
                    'ss2': [a, first + i]})
    return out

def vtab(ch, i, var=0):
    """$46BAE's table: [vx][vy] (8.8 px / frame, vx forward, vy down) of entry i of the fighter's table"""
    base = N.u32(0x6A500 + 4 * ch)
    return N.s16(base + 4 * i), N.s16(base + 4 * i + 2)

def physics(ch):
    walk = vtab(ch, 0)[0] / 256; back = -vtab(ch, 1)[0] / 256
    vy0 = -vtab(ch, 4)[1] / 256; g = vtab(ch, 5)[1] / 256; jdx = vtab(ch, 2)[0] / 256
    return {'walk_fwd': walk, 'walk_back': back, 'jump_vy0': vy0, 'gravity': g, 'jump_dx': jdx, 'prejump': 2}

# ---- the second layer's flicker (TODO #193) ----------------------------------------------------------------------------
# The display code adds the object's +$82 to the palette of a step's second layer ($35C6 / $3656: the layer list's
# entries 0 / 1 / 2 get +$81 / +$82 / +$83) and $25D3E sets +$82 every frame to the player's colour block (0, P2 8) + bit 0
# of the frame counter $1089F9 [code]: that layer is drawn with palette p and p + 1 on alternate frames. Measured in our
# emulator (Hanzo's fight state, /data/tmp/hanzo193/pal): his sword (the idle's second layer, palette 19) is 20 every
# other frame in VRAM, and P2 Haohmaru's second layer 27 / 28 the same (the study's "one layer one palette off" for
# Hanzo / Sieger / Nicotine: their stages do not switch SCB3 banks, so every frame was compared; the others' captures
# skipped every other frame). Palette 19 / 20 differ in pens 8-10 (the blade's greys): a glint. The brawler: such a
# part gets the palette key FLK + p, its colours p, and every other frame p + 1 (bchar_t.flk, fighter.c flicker); a part
# whose pens are the same in p and p + 1 keeps p (no flicker to show).
FLK = 1000

def key_colours(ch, s, p):
    """the 16 colours of SS2 palette key p in colour set s (FLK + p: palette p's, the flicker's base)"""
    p %= FLK
    return ss2.fighter_palettes(ch, s)[p - 16] if 16 <= p < 24 else fixed_palette(p)

def flicker_key(ch, p, tiles):
    """the key of a second-layer part drawn with palette p (tiles: its C tile codes): FLK + p when palette p + 1 shows
    any of its pens in another colour in some colour set, else p"""
    pens = set()
    for t in tiles: pens.update(int(q) for q in N.tile(t).flatten() if q)
    assert p + 1 < 24 or p >= 32, (ch, p)
    same = all(key_colours(ch, s, p)[q] == key_colours(ch, s, p + 1)[q] for s in range(COLOURS) for q in pens)
    return p if same else FLK + p

def flicker(B, ch, sets):
    """bchar_t.flk: [{'index': brawler palette, 'key': SS2 palette, 'sets': the other frame's colours per colour set}]
    (pens another palette was folded into keep their colours: pack_palettes never folds into a flicker palette)"""
    out = []
    for i, k in enumerate(B.pals):
        if k < FLK: continue
        out.append({'index': i, 'key': k - FLK, 'sets': [[0] + key_colours(ch, s, k - FLK + 1)[1:] for s in range(COLOURS)]})
    return out

def colours(B, ch):
    """the colour sets: per set every palette key of the frames (16 colours, pen 0 transparent); a packed palette
    (pack_palettes) with the pens it took from the palettes folded into it"""
    sets = []
    for s in range(COLOURS):
        body = ss2.fighter_palettes(ch, s)
        row = []
        for p in B.pals:
            c = [0] + key_colours(ch, s, p)[1:]
            for q, col in getattr(B, 'packed', {}).get(p, {}).items(): c[q] = col[s]
            row.append(c)
        sets.append(row)
    return sets

# ---- the palette budget (TODO #176 follow-up) --------------------------------------------------------------------------
# The brawler reserves MAX_PALS palettes per fighter (fighter.h: 16 + slot * 8). SS2 draws Kuroko's moves with 10: his
# colour set (16) and 9 of the game's fixed effect palettes, most of them using a few pens. pack_palettes folds the
# smallest into others until 8 remain, with the exact colours: a pen of the folded palette whose colour (in every colour
# set) the host already has maps to that pen, any other goes to a pen the host leaves unused; the folded palette's tiles
# are copied with their pens renumbered (a pen = the 4 bitplanes of a pixel: .neo bytes bp0 bp2 bp1 bp3). Nothing at
# run time: every frame shows the colours SS2 shows (proof: pack_check).
MAX_PALS = 8
# the pen codec of a 128-byte .neo C tile (tile_pens: pixel by pixel, 32 groups of 4 bytes x 8 pixels holding pen bits
# 0, 2, 1, 3: neo2.tile; tile_recolour: pens renumbered) is the brawler export's palette packer's (TODO #201), which folds
# every other game's fighters the same way
sys.path.append(os.path.join(HERE, '..', 'brawler'))
from pal_pack import tile_pens, tile_recolour

def pack_palettes(B, ch, limit=MAX_PALS):
    """fold palettes until B.pals has at most `limit` (see above): -> [(host key, folded key, pen map)]"""
    B.packed = getattr(B, 'packed', {})
    def pens_of():
        use = {}
        for fr in B.frames:
            for pt in fr['parts']:
                u = use.setdefault(pt['pal'], set())
                for col in pt['tiles']:
                    for t in col:
                        if t: u.update(q for q in tile_pens(B.tiles[t - TILE_BASE]) if q)
        return use
    done = []
    while len(B.pals) > limit:
        use = pens_of(); cols = colours(B, ch)
        colour = lambda i, q: tuple(cols[s][i][q] for s in range(COLOURS))
        best = None
        for a in range(len(B.pals)):
            for b in range(1, len(B.pals)):
                if a == b: continue
                ka_, kb_ = B.pals[a], B.pals[b]
                if ka_ >= FLK: continue               # a flicker palette hosts nothing (its pens change every frame)
                if kb_ >= FLK and ka_ != kb_ - FLK: continue   # one folds only into its own base: that flicker dropped
                taken = {q: colour(a, q) for q in use.get(a, ())}
                m = {}; ok = True
                for q in sorted(use.get(b, ())):
                    c = colour(b, q)
                    same = next((r for r, cr in taken.items() if cr == c), None)
                    if same is not None: m[q] = same; continue
                    if q not in taken: m[q] = q; taken[q] = c; continue
                    free = next((r for r in range(1, 16) if r not in taken), None)
                    if free is None: ok = False; break
                    m[q] = free; taken[free] = c
                if not ok: continue
                moved = sum(1 for q, r in m.items() if q != r)
                cost = (kb_ >= FLK, moved, len(taken), -b)   # a flicker dropped only when nothing else folds
                if best is None or cost < best[0]: best = (cost, a, b, m, taken)
        assert best, f'{ch}: no palette folds into another ({[B.pals[i] for i in range(len(B.pals))]})'
        _, a, b, m, taken = best
        ka, kb = B.pals[a], B.pals[b]
        B.packed.setdefault(ka, {})
        for q, r in m.items(): B.packed[ka][r] = colour(b, q)
        cache = {}
        for fr in B.frames:
            for pt in fr['parts']:
                if pt['pal'] != b: continue
                if any(q != r for q, r in m.items()):
                    def re(t):
                        if not t: return 0
                        if t not in cache:
                            cache[t] = TILE_BASE + len(B.tiles); B.tiles.append(tile_recolour(B.tiles[t - TILE_BASE], m))
                        return cache[t]
                    pt['tiles'] = [[re(t) for t in col] for col in pt['tiles']]
                pt['pal'] = a
        for fr in B.frames:
            for pt in fr['parts']:
                if pt['pal'] > b: pt['pal'] -= 1
        del B.pals[b]
        done.append((ka, kb, m))
    return done

def render_frame(B, sets, fr, s=0):
    """a frame's parts as {(x, y): colour} (colour set s; later parts on top)"""
    img = {}
    for pt in fr['parts']:
        for ci, col in enumerate(pt['tiles']):
            for ri, t in enumerate(col):
                if not t: continue
                pens = tile_pens(B.tiles[t - TILE_BASE])
                for r in range(16):
                    for c in range(16):
                        q = pens[(1 if c < 8 else 0) * 128 + r * 8 + c % 8]
                        if q: img[(pt['dx'] + 16 * ci + c, pt['dy'] + 16 * ri + r)] = sets[s][pt['pal']][q]
    return img

def pack_check(name):
    """every frame of a fighter's export with its palettes packed vs unpacked, pixel colours in every colour set ->
    (frames, frames identical)"""
    import handlers_ss2 as H
    res = []
    for lim in (99, MAX_PALS):
        ch = CAST[name]; B = Builder(ch)
        for mv, (a, f, l) in {**MOVES, **jump_moves(ch)}.items(): anim_steps(B, ch, a, f, l)
        H.specials(B, ch, name); H.throws(B, ch, name)
        pack_palettes(B, ch, lim); res.append((B, colours(B, ch)))
    (B0, s0), (B1, s1) = res
    assert len(B0.frames) == len(B1.frames)
    for (code, hf, vf), t in B0.tile_map.items():     # the pen decoder = neo2's (the study's, = SS2's VRAM)
        assert sorted(tile_pens(B0.tiles[t - TILE_BASE])) == sorted(N.tile(code).flatten().tolist()), code
    same = sum(all(render_frame(B0, s0, f0, s) == render_frame(B1, s1, f1, s) for s in range(COLOURS))
               for f0, f1 in zip(B0.frames, B1.frames))
    return len(B0.frames), same, len(B0.pals), len(B1.pals)

RAGE_POW = 32                                     # +$F0 when the rage is full (the flash pose: anim 140, TODO #189)

def rage_palette(B, ch, a, sets):
    """the colours SS2 shows anim a (the rage-full animation 140) in [code + meas, TODO #191]: the display code ($35C6)
    adds the object's +$81 to the palette of a step's first layer ($3656: layer slots 0 / 1 / 2 -> +$81 / +$82 / +$83,
    the fourth none) and $25D3E sets +$81 = $25D72[+$F0] every frame: 2 at a full POW (1 from 10, 2 from 20), +$82 /
    +$83 stay 0 (measured: ragepal_ss2.py, +$81 = 2 through the whole animation, palette RAM 16-23 = the colour set,
    unchanged). So the body (the first layer: palette 16 in every step of anim 140, Haohmaru / Genjuro / Kuroko) shows
    the colour set's palette 16 + 2 (Haohmaru / Genjuro: the clothes red, Kuroko: the robe dark red).
    -> {'key': SS2 palette, 'index': its palette in this export, 'sets': per colour set its 16 colours as the pose
    shows them} (the pens another palette was folded into keep their colours: pack_palettes), or None"""
    add = N.u8(0x25D72 + RAGE_POW)
    first, other = set(), set()
    for s in ss2.parse_anim(ch, a, 400):
        for li, w in enumerate(s['layers']):
            _, cells = ss2.sprite_cells(w & 0x7FFF)
            ps = {cell[1] >> 8 for col in cells for cell in col if cell is not None and cell[0]}
            (first if li == 0 else other).update(ps)
    if not add or not first: return None
    assert len(first) == 1 and not first & other, (ch, a, first, other)   # one body palette, drawn by the first layer only
    p = first.pop()
    assert 16 <= p and p + add < 24, (ch, p, add)
    i = B.pals.index(p); packed = getattr(B, 'packed', {}).get(p, {})
    rows = []
    for s in range(COLOURS):
        q = ss2.fighter_palettes(ch, s)[p + add - 16]
        rows.append([0] + [sets[s][i][k] if k in packed else q[k] for k in range(1, 16)])
    return {'key': p, 'index': i, 'sets': rows}

def export(names, outdir, only=None, extra=None, lab=None):
    """lab: {name: [(hex id, animation)]} the Character Lab's slot (export_bm LAB): that fighter also gets every special
    version as its own special (handlers_ss2.specials versions), his Lab throws (the big victim's, the air throw) and
    the LAB special (every animation of his dictionary)"""
    import handlers_ss2 as H
    out = {'game': 'samsho2', 'tile_base': TILE_BASE, 'characters': {}}
    allt, tmap = [], {}
    for name in names:
        ch = CAST[name]; B = Builder(ch); B.tiles = allt; B.tile_map = tmap
        anims = {}
        for mv, (a, f, l) in {**MOVES, **jump_moves(ch)}.items():
            anims[mv] = {'slot': a, 'mode': 'loop' if mv in LOOP else 'hold', 'steps': anim_steps(B, ch, a, f, l)}
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        if name in WIN: anims['win'] = {'slot': WIN[name], 'mode': 'hold', 'steps': anim_steps(B, ch, WIN[name])}
        w = (extra or {}).get(name, {}).get('watch')
        if w:
            st = ss2.parse_anim(ch, w[0], 400); k = w[1] if w[1] >= 0 else len(st) - 1
            anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': anim_steps(B, ch, w[0], k, k)}
        for mv, hx in ((extra or {}).get(name, {}).get('moves') or {}).items():   # the roster's moves "$XX" (2026-10-10: the
            a = int(str(hx).lstrip('$'), 16)                  # Assembly's picks shipped by arb_compile, a spare move name
            anims[mv] = {'slot': a, 'mode': 'hold', 'steps': anim_steps(B, ch, a)}   # on any SS2 animation, KOF's export96 slots)
        if only is not None: anims = {k: v for k, v in anims.items() if k in only or k == 'watch'}
        for mv, (a, f, l) in ((extra or {}).get(name, {}).get('anims') or {}).items():   # whole animations by request (export_bm FLASH_POSES: the flash pose, TODO #145): {move: (anim, first, last)}
            anims[mv] = {'slot': a, 'mode': 'hold', 'steps': anim_steps(B, ch, a, f, l)}
        L = (lab or {}).get(name)
        sps = H.specials(B, ch, name, versions=L is not None)
        throws = H.throws(B, ch, name, lab=L is not None)
        if L is not None:
            e, bad = H.lab_special(B, ch, L); sps.append(e)
            if bad: print(f'{name}: LAB special: {len(bad)} animations left out:', bad[:8])
        for t, th in throws.items(): anims[t] = th.pop('anim')
        packed = pack_palettes(B, ch)
        sets = colours(B, ch)
        rage = rage_palette(B, ch, anims['flash']['slot'], sets) if 'flash' in anims and anims['flash']['slot'] == 140 else None
        out['characters'][name] = {'id': ch, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0], 'physics': physics(ch),
                                   'throws': throws, 'specials': sps,
                                   'modes': {'sets': ['A', 'B'], 'palettes': [str(p) + ''.join(f'+{kb}' for ka, kb, _ in packed if ka == p) for p in B.pals]},
                                   'ss2_packed': [[ka, kb, {str(q): r for q, r in m.items()}] for ka, kb, m in packed]}
        if rage: out['characters'][name]['flash_pal'] = rage      # the rage palette of the flash pose (TODO #191)
        flk = flicker(B, ch, sets)
        if flk: out['characters'][name]['flicker'] = flk          # the second layer's flicker palette (TODO #193)
    out['tiles'] = len(allt)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * TILE_BASE) + b''.join(allt)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    names = sys.argv[2:] or ['haohmaru', 'genjuro', 'kuroko']
    ex = export(names, sys.argv[1], extra={n: {'watch': (140, -1)} for n in names})
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'], 'palettes', ch['modes']['palettes'])
        print('  max cols', max(sum(len(p['tiles']) for p in f['parts']) for f in ch['frames']),
              'max rows', max(len(p['tiles'][0]) for f in ch['frames'] for p in f['parts']))
        for sp in ch['specials']:
            print('  ', sp['input'], sp['condition'], len(sp['rom']['prims']), 'ops', (sp['rom'].get('vtable') or {}).get('nvar'), 'variants')
    print(ex['tiles'], 'tiles')
