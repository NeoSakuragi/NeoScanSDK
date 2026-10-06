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
CAST = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}
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
# its kneeling step 1), win 140 (the sheathing pose).
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
    'knockdown_fall': (222, 0, 0), 'down': (222, 1, 1), 'getup': (138, 1, None), 'trip': (120, 0, None), 'win_a': (140, 0, None),
}
# per fighter: Kuroko's jumps forward / back rise with 22 and fall with 26 (class 0 action 9: 22, 30, 26; the one-step
# 28 / 32 / 34 / 38 of the others are placeholders in his table)
MOVES_OF = {'kuroko': {'jump_fwd_rise': (22, 0, None), 'jump_fwd_fall': (26, 0, None),
                       'jump_back_rise': (22, 0, None), 'jump_back_fall': (26, 0, None)}}
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
    def frame(self, st, extra=(), mirror=0):
        """a step (ss2.parse_step) as a frame; extra: more steps drawn with it (objects pinned to the body), each
        (step, dx, dy, facing flip) in SS2's facing-right screen offsets; mirror: the step drawn turned (its flags
        bit 15, SS2 draws the object mirrored about its feet: the throws' thrower, TODO #148 feedback; anim_steps)"""
        mv = next(((c[1], c[2]) for c in st['cmds'] if c[0] == 'move'), (0, 0))
        key = (tuple(st['layers']), st['flags'] & 0x4000, mv,
               tuple((tuple(s['layers']), s['flags'] & 0x4000, dx, dy, fl) for s, dx, dy, fl in extra)) + ((('mirror',) if mirror else ()))
        if key in self.index: return self.index[key]
        parts = []
        for s, ox, oy, fl in [(st, -mv[0] if mirror else mv[0], mv[1], 1 if mirror else 0)] + [(s, dx + next(((c[1]) for c in s['cmds'] if c[0] == 'move'), 0),
                                                         dy + next(((c[2]) for c in s['cmds'] if c[0] == 'move'), 0), fl) for s, dx, dy, fl in extra]:
            nl = len(s['layers'])
            for li in ss2.ORDER[bool(s['flags'] & 0x4000)][nl - 1]:
                parts += self.layer(s['layers'][li], ox, oy, fl)
        self.index[key] = len(self.frames)
        self.frames.append({'record': ' '.join(f'{w:04X}' for w in st['layers']), 'parts': parts, 'weapon': None,
                            'ss2': {'layers': st['layers'], 'flags': st['flags'], 'move': list(mv),
                                    'extra': [[s['layers'], s['flags'], dx, dy, fl] for s, dx, dy, fl in extra]}})
        return self.index[key]
    def layer(self, w, ox, oy, facing):
        """one sprite definition drawn at (ox, oy) from the object (SS2 screen offsets, facing right) -> brawler parts
        (facing left: mirrored about the feet). facing 1: the definition drawn facing left in SS2 (an object turned)"""
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
            byp = {}
            for r, cell in enumerate(col):
                if cell is None: continue
                t, at = cell
                at ^= flip                            # the handler toggles the flip bit of a turned layer
                code = t | (at >> 4 & 0xF) << 16
                if not code: continue
                tn = self.tile(code, (at & 1) ^ 1, at >> 1 & 1)   # mirrored: every cell flipped once more
                if tn: byp.setdefault(at >> 8, {})[r] = tn
            for p, rows in byp.items():
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

def anim_steps(B, ch, a, first=0, last=None, mirror=False):
    """animation a's steps first..last as brawler steps; mirror: a step whose flags have bit 15 is drawn turned (SS2's
    display list shows those steps h-flipped with the object's facing unchanged: Haohmaru's / Genjuro's throws 274 /
    346, measured on moves/00.json, 12.json close_throw_*; only the throws pass it so far)"""
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

def colours(B, ch):
    """the colour sets: per set every palette key of the frames (16 colours, pen 0 transparent)"""
    sets = []
    for s in range(COLOURS):
        body = ss2.fighter_palettes(ch, s)
        sets.append([[0] + (body[p - 16] if 16 <= p < 24 else fixed_palette(p))[1:] for p in B.pals])
    return sets

def export(names, outdir, only=None, extra=None):
    import handlers_ss2 as H
    out = {'game': 'samsho2', 'tile_base': TILE_BASE, 'characters': {}}
    allt, tmap = [], {}
    for name in names:
        ch = CAST[name]; B = Builder(ch); B.tiles = allt; B.tile_map = tmap
        anims = {}
        for mv, (a, f, l) in {**MOVES, **MOVES_OF.get(name, {})}.items():
            anims[mv] = {'slot': a, 'mode': 'loop' if mv in LOOP else 'hold', 'steps': anim_steps(B, ch, a, f, l)}
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        w = (extra or {}).get(name, {}).get('watch')
        if w:
            st = ss2.parse_anim(ch, w[0], 400); k = w[1] if w[1] >= 0 else len(st) - 1
            anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': anim_steps(B, ch, w[0], k, k)}
        if only is not None: anims = {k: v for k, v in anims.items() if k in only or k == 'watch'}
        sps = H.specials(B, ch, name)
        throws = H.throws(B, ch, name)
        for t, th in throws.items(): anims[t] = th.pop('anim')
        sets = colours(B, ch)
        out['characters'][name] = {'id': ch, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0], 'physics': physics(ch),
                                   'throws': throws, 'specials': sps,
                                   'modes': {'sets': ['A', 'B'], 'palettes': [str(p) for p in B.pals]}}
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
