#!/usr/bin/env python3
"""Final Fight's Guy, Cody and Haggar in the export96 layout: the brawler's export_bm.py reads them like a KOF export (layer
0 of docs/brawler_data_model.md, one code path), the way tools/lastbld2 (export_lb2) does.

    python3 export_ff.py OUTDIR [guy cody haggar]   -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

From the ROM (ff.py: program, graphics, palettes, animations, frames, boxes) and FF's own play measured in FBNeo
(rec_ff.py -> throws_ff.json: which animation each action plays, the throws' victim paths):
- frames: a frame record's 16x16 tiles (CPS1 4bpp -> Neo Geo C tiles, pen 15 transparent -> pen 0, pens 0-14 -> 1-15),
  MIRRORED: FF's art faces right, the brawler's left; columns of tiles with the same top = one part. Full size (1 CPS1
  px = 1 Neo Geo px; FF's pixels are 384 / 320 narrower on a TV).
- steps: one per animation entry (its frame, ticks = t - 1: the export96 rule); attack steps flag $100, an attack
  continued by the next step one hit ($4000: FF hits once per move).
- boxes: body (b4) -> '31', attack (b5, bit 7 = a ground-only grab box: not an attack) -> '11', centre / half extents,
  x forward negative / y up negative (KOF's).
- palettes: the fighter's own (Guy 0, Cody 1, Haggar 2 of the sprite palettes $C0000) + any effect palette a frame
  names, CPS1 colour -> Neo Geo colour word. Colour set B = A (FF has one colour per character).
- physics: walk / jump from the study (ffight_framedata.json) and the jump's 16.16 heights [meas]: vy0 6.0, gravity
  0.28125 ($4800), 7 crouch frames; forward jump dx 108 / 101 / 82 px over 42 frames.
- the special (attack + jump): one program from its animation and its measured motion (Guy / Cody hop: vy0 6 / 7,
  gravity 0.33203125 ($5500); Haggar's lariat stays on the ground).
- throws: throws_ff.json (throws_ff.py from FF's play: the thrower's frames, the victim's path and posture per frame)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ff
import handlers_ff as H

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = ff.CAST
EFFECT_PALS = (28, 31)                            # the shared effect palettes some frames name (the special's flash)

def W(*a): return a
# brawler move -> FF animation: an address, or (address, first entry, end entry) for a part of one; LOOP = played as a loop
MOVES = {
    'guy': {'idle': 0xF6B4, 'walk_fwd': 0xF7C4, 'run': 0xF7C4, 'prejump': (0xFBBE, 0, 1), 'land': (0xFBBE, 0, 1),
            'jump_up_rise': 0xFAB4, 'jump_up_fall': 0xFAB4, 'jump_fwd_rise': (0xFAEC, 0, 1), 'jump_fwd_fall': (0xFAEC, 1, None),
            'jump_back_rise': (0xFAEC, 0, 1), 'jump_back_fall': (0xFAEC, 1, None),
            'atk_a_far': 0x10258, 'atk_a_close': 0x10258, 'atk_b_far': 0x102FC, 'atk_b_close': 0x103B8,
            'atk_c_close': 0xFCE2, 'atk_c_far': 0xFCE2, 'atk_d_close': 0x10686, 'atk_d_far': 0x10686,
            'atk_c_jump': 0xFEFA, 'atk_d_jump': 0xFE16, 'atk_c_jump_diag': 0xFE16, 'atk_d_jump_diag': 0xFE16, 'atk_a_jump': 0xFC3A, 'atk_a_jump_diag': 0xFC3A,
            'hit_stand_light': 0x106CE, 'hit_stand_heavy': 0x106DA, 'hit_air': 0x1093E, 'blowback': 0x1093E, 'blowback_n': 0x1093E,
            'knockdown_flight': 0x1093E, 'knockdown_bounce': 0x1093E, 'knockdown_fall': 0x1093E, 'trip': 0x1093E,
            'down': 0x10946, 'getup': 0x10772, 'win': 0xF6B4, 'grab': 0x10636},
    'cody': {'idle': 0x111B6, 'walk_fwd': 0x112BA, 'run': 0x112BA, 'prejump': (0x11828, 0, 1), 'land': (0x11828, 0, 1),
             'jump_up_rise': (0x1163A, 0, 1), 'jump_up_fall': (0x1163A, 1, None), 'jump_fwd_rise': (0x116B4, 0, 2),
             'jump_fwd_fall': (0x116B4, 2, None), 'jump_back_rise': (0x116B4, 0, 2), 'jump_back_fall': (0x116B4, 2, None),
             'atk_a_far': 0x120E4, 'atk_a_close': 0x120E4, 'atk_b_far': 0x12188, 'atk_b_close': 0x12188,
             'atk_c_close': 0x12240, 'atk_c_far': 0x12240, 'atk_d_close': 0x1197A, 'atk_d_far': 0x1197A,
             'atk_c_jump': 0x11E16, 'atk_d_jump': 0x11D1A, 'atk_c_jump_diag': 0x11D1A, 'atk_d_jump_diag': 0x11D1A, 'atk_a_jump': 0x11C4A, 'atk_a_jump_diag': 0x11C4A,
             'hit_stand_light': 0x12412, 'hit_stand_heavy': 0x12412, 'hit_air': 0x12382, 'blowback': 0x12382, 'blowback_n': 0x12382,
             'knockdown_flight': 0x12382, 'knockdown_bounce': 0x12382, 'knockdown_fall': 0x12382, 'trip': 0x12382,
             'down': 0x1238A, 'getup': 0x124B2, 'win': 0x111B6, 'grab': 0x11870},
    'haggar': {'idle': 0x12CFC, 'walk_fwd': 0x12DE0, 'run': 0x12DE0, 'prejump': (0x133FC, 0, 1), 'land': (0x133FC, 0, 1),
               'jump_up_rise': (0x13348, 0, 1), 'jump_up_fall': (0x13348, 1, None), 'jump_fwd_rise': (0x133D4, 0, 1),
               'jump_fwd_fall': (0x133D4, 1, None), 'jump_back_rise': (0x133D4, 0, 1), 'jump_back_fall': (0x133D4, 1, None),
               'atk_a_far': 0x1397C, 'atk_a_close': 0x1397C, 'atk_b_far': 0x13A94, 'atk_b_close': 0x13A94,
               'atk_c_close': 0x13A94, 'atk_c_far': 0x13A94, 'atk_d_close': 0x14938, 'atk_d_far': 0x14938,
               'atk_c_jump': 0x13558, 'atk_d_jump': 0x13558, 'atk_c_jump_diag': 0x13558, 'atk_d_jump_diag': 0x13558, 'atk_a_jump': 0x134B0, 'atk_a_jump_diag': 0x134B0,
               'hit_stand_light': 0x13F6C, 'hit_stand_heavy': 0x13F78, 'hit_air': 0x13EBE, 'blowback': 0x13EBE, 'blowback_n': 0x13EBE,
               'knockdown_flight': 0x13EBE, 'knockdown_bounce': 0x13EBE, 'knockdown_fall': 0x13EBE, 'trip': 0x13EBE,
               'down': 0x13EC6, 'getup': 0x1401A, 'win': 0x12CFC, 'grab': 0x143C8,
               'hold_walk': 0x14434},   # (the walk in the hold: rec_ff.py grab_walk*, only Haggar's; Guy / Cody stand still)
}
LOOP = {'idle', 'walk_fwd', 'run', 'win', 'hold_walk'}
# atk_a_jump = FF's down-attack (attack + down in a jump), the same animation in a neutral and a forward jump (rec_ff.py
# jatk_d / jatk_fd 2026-10-14: Guy $FC3A, Cody $11C4A, Haggar $134B0 from either): atk_a_jump_diag names it for the
# forward / back jump (the brawler's air down + A plays its _diag twin there; without one export_bm fell back to the
# jump's own attack: note 20261014-084234-5d29, "the dive is missing in a forward jump")
# jump attacks: FF keeps the attack frame to the landing (its entry's ticks run out first: the game holds it) [meas]
WALK = {'guy': 2.10, 'cody': 1.95, 'haggar': 1.85}                # px a frame [meas, study]
DEPTH = {'guy': 1.0, 'cody': 0.797, 'haggar': 0.699}
FJUMP = {'guy': 108, 'cody': 101, 'haggar': 82}                   # forward jump travel px over its 42 air frames [meas]
# the walk: its 12 entries all say 1 tick, but FF holds each for about 3 frames (its walk code steps the animation on its own
# clock, not the entry's ticks): one 12-entry cycle = 39 / 44 / 34 frames (rec_ff.py walk 2026-10-14: 3.24 / 3.67 / 2.84
# frames an entry; note 20261014-084140: Haggar's walk played 12 frames a cycle, 2.8x too fast) [meas]
WALK_CYCLE = {'guy': 39, 'cody': 44, 'haggar': 34}
CYCLED = ('walk_fwd', 'run', 'hold_walk')
# the hold walk ($14434, Haggar, note 20261014-171133-5d29; rec_ff.py grab_walkf / walkb / walkud / walkdiag 2026-10-14): 12
# entries of 1 tick on the walk's clock, 34 frames a cycle while it moves along x (= his walk's cadence), ~47 moving in depth
# alone; backward along x it plays the entries in reverse, the facing kept (no turn); the thrower moves at his walk's speed
# (1.85 px a frame x, 0.70 depth) and the victim keeps its held pose ($23CC0) 42 px ahead, carried with him; the hold's
# timer runs on (released 124 frames after the grab, walking or not); a direction + attack throws (up + attack the
# backdrop), attack alone the headbutt; jump + attack the piledriver [meas]

def cycle_ticks(steps, frames):
    """spread `frames` over the steps (Bresenham: the measured cadence's 3s and 4s) -> each step's ticks (= frames - 1)"""
    n = len(steps)
    for i, s in enumerate(steps): s['ticks'] = (i + 1) * frames // n - i * frames // n - 1
    return steps

def neo_colour(w):
    import importlib.util
    r, g, b = ff.cps_rgb(w)
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    return ((r5 & 1) << 14) | ((r5 >> 1) << 8) | ((g5 & 1) << 13) | ((g5 >> 1) << 4) | ((b5 & 1) << 12) | (b5 >> 1)

def neo_tile(code, hf, vf):
    """CPS1 tile `code` -> a 128-byte Neo Geo C tile (combined c1 / c2 bytes: per row [bp0 bp2 bp1 bp3], the right half
    first, bit 0 = the leftmost pixel), mirrored when hf, pens + 1 (15 = transparent -> 0)"""
    px = ff.tile_pixels(code)
    if vf: px = px[::-1]
    if hf: px = [r[::-1] for r in px]
    out = bytearray(128)
    for half, x0 in enumerate((8, 0)):
        for y in range(16):
            bp = [0, 0, 0, 0]
            for x in range(8):
                p = px[y][x0 + x]; p = 0 if p == 15 else p + 1
                for k in range(4):
                    if p >> k & 1: bp[k] |= 1 << x
            o = half * 64 + y * 4
            out[o:o + 4] = bytes((bp[0], bp[2], bp[1], bp[3]))
    return bytes(out)

class Builder:
    """frames as brawler parts (mirrored: facing left); palettes keyed by FF palette number"""
    def __init__(self, name):
        self.name = name
        self.tile_map, self.tiles, self.frames, self.index, self.pals = {}, [], [], {}, []
    def tile(self, code, hf, vf):
        k = (code, hf, vf)
        if k not in self.tile_map:
            t = neo_tile(code, hf, vf)
            if not any(t): return 0
            self.tile_map[k] = TILE_BASE + len(self.tiles); self.tiles.append(t)
        return self.tile_map[k]
    def pal(self, p):
        if p not in self.pals: self.pals.append(p)
        return self.pals.index(p)
    def frame(self, fa):
        if fa in self.index: return self.index[fa]
        f = ff.frame(fa)
        cols = {}                                       # (palette, x) -> {y: tile}
        for code, at, x, y in f['tiles']:
            hf = 1 ^ (at >> 5 & 1); vf = at >> 6 & 1     # mirrored: every tile flips once more
            nx = -(x + 16)
            t = self.tile(code, hf, vf)
            if t: cols.setdefault((at & 31, nx), {})[y] = t
        parts = []
        for (p, x), ys in sorted(cols.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            top, bot = min(ys), max(ys)
            col = [ys.get(y, 0) for y in range(top, bot + 16, 16)]
            q = parts[-1] if parts else None
            if q and q['_p'] == p and q['_top'] == top and q['_x'] + 16 * len(q['tiles']) == x and len(q['tiles'][0]) == len(col):
                q['tiles'].append(col); continue
            parts.append({'_p': p, '_top': top, '_x': x, 'tiles': [col]})
        out = []
        for q in parts:
            n = max(len(t) for t in q['tiles'])
            out.append({'dx': q['_x'], 'dy': q['_top'], 'hflip': 0, 'vflip': 0, 'pal': self.pal(q['_p']),
                        'tiles': [t + [0] * (n - len(t)) for t in q['tiles']]})
        self.index[fa] = len(self.frames)
        self.frames.append({'record': f'{self.name}:{fa:05X}', 'parts': out, 'weapon': None, 'ff': {'frame': fa}})
        return self.index[fa]

def kof_boxes(fa, name):
    f = ff.frame(fa); b = ff.boxes(f, name); out = {}
    def k(v):
        cx, cy, hw, hh = v
        return [max(-128, min(127, -cx)), max(-128, min(127, -cy)), min(255, max(1, hw)), min(255, max(1, hh))]
    if 'body' in b: out['31'] = k(b['body'])
    if 'atk' in b and not f['atk'] & 0x80: out['11'] = k(b['atk'])
    return out

def entries(spec):
    a, lo, hi = (spec, 0, None) if isinstance(spec, int) else spec
    ents, lp = ff.anim(a)
    return ents[lo:hi], a

def anim_steps(B, name, spec):
    ents, a = entries(spec)
    steps = []
    for e, fa, t, at in ents:
        bx = kof_boxes(fa, name)
        steps.append({'frame': B.frame(fa), 'ticks': max(0, t - 1), 'flags': 0x100 if '11' in bx else 0, 'dx': 0,
                      'boxes': bx, 'ff': [e, fa, t, at]})
    for i, s in enumerate(steps):                   # one hit per move: an attack step continued by the next attack step
        if s['flags'] & 0x100 and i + 1 < len(steps) and steps[i + 1]['flags'] & 0x100: s['flags'] |= 0x4000
    return steps

def physics(name):
    return {'walk_fwd': WALK[name], 'walk_back': WALK[name], 'jump_vy0': 6.0, 'gravity': 0.28125,
            'jump_dx': FJUMP[name] / 42, 'prejump': 7, 'depth': DEPTH[name]}

def colours(B):
    row = [[0] + [neo_colour(w) for w in ff.palette(p)[:15]] for p in B.pals]
    return [row, [list(r) for r in row]]

# ---- throws: throws_ff.json (throws_ff.py) ----
THROWS_JSON = os.path.join(HERE, 'throws_ff.json')
def throws(B, name):
    if not os.path.exists(THROWS_JSON): return {}
    T = json.load(open(THROWS_JSON)).get(name, {})
    out = {}
    for key, t in T.items():
        tl = [[B.frame(fa), tx, ty, turned] for fa, tx, ty, turned in t['timeline']]
        vrows = [[B.frame(r[0]) if r[0] is not None else -1] + r[1:] for r in t['victim']]
        steps = []
        for fa, tx, ty, turned in t['timeline']:
            f = B.frame(fa)
            if steps and steps[-1]['frame'] == f: steps[-1]['ticks'] += 1
            else: steps.append({'frame': f, 'ticks': 0, 'flags': 0, 'dx': 0, 'boxes': kof_boxes(fa, name)})
        out[key] = {'slot': t['anim'], 'inputs': t['inputs'], 'table': [], 'hold': False, 'rom': True, 'timeline': tl,
                    'victims': {name: vrows}, 'impacts': t['impacts'], 'release': t['release'], 'land': t['land'],
                    'ret': t['ret'], 'anim': {'slot': t['anim'], 'mode': 'hold', 'steps': steps}, 'turned': False,
                    'grab_frame': None, 'name': t['name'], 'ff': {'anim': t['anim'], 'damage': t.get('damage')}}
    return out

def export(names, outdir, only=None, extra=None, lab=None):
    out = {'game': 'ffight', 'tile_base': TILE_BASE, 'characters': {}}
    allt, tmap = [], {}
    for name in names:
        B = Builder(name); B.tiles = allt; B.tile_map = tmap
        B.pal(ff.PAL[name])
        anims = {}
        for mv, spec in MOVES[name].items():
            if only is not None and mv not in only and mv not in ('watch', 'grab'): continue
            st = anim_steps(B, name, spec)
            if mv in CYCLED: cycle_ticks(st, WALK_CYCLE[name])
            anims[mv] = {'slot': entries(spec)[1], 'mode': 'loop' if mv in LOOP else 'hold', 'steps': st}
        w = (extra or {}).get(name, {}).get('watch')
        if w: anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': anim_steps(B, name, w[0])[w[1]:][:1]}
        th = throws(B, name)
        for t, x in th.items(): anims[t] = x.pop('anim')
        sps = [H.special(sys.modules[__name__], B, name)] + H.pieces(sys.modules[__name__], B, name)   # (+ its fury pieces)
        sets = colours(B)
        out['characters'][name] = {'id': CAST[name], 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0], 'physics': physics(name),
                                   'throws': th, 'specials': sps, 'hit_sparks': [],
                                   'modes': {'sets': ['A', 'B'], 'palettes': [str(p) for p in B.pals]}}
    out['tiles'] = len(allt)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * TILE_BASE) + b''.join(allt)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    names = sys.argv[2:] or list(CAST)
    ex = export(names, sys.argv[1])
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', 'palettes', ch['modes']['palettes'],
              'special', ch['specials'][0]['rom']['length'], 'frames', ch['specials'][0]['game_hits'], 'hits', 'throws', list(ch['throws']))
    print(ex['tiles'], 'tiles', ex['tiles'] * 128 // 1024, 'KB')
