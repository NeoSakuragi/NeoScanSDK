#!/usr/bin/env python3
"""Garou: Mark of the Wolves fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99
export (layer 0 of docs/brawler_data_model.md, one code path), the way tools/lastbld2 (export_lb2) does.

    python3 export_garou.py OUTDIR [rock]   -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

From the ROM (study /data/neogeo_dict/garou/README.md; decoder garou.py):
- frames: a step's sprite definition ($200100 tables, formats 0 / 1 / 3 / 7-10) at the step's offsets (+$54 / +$56).
  Garou's art faces RIGHT (P1 unflipped); the brawler's faces LEFT: every frame is mirrored (columns reversed, each
  tile's copy flipped, x = xoff - width from the feet). Boxes are already authored facing left (x negative = forward:
  the debug box drawer $3B30 negates them for an unflipped object).
- steps: the animation player $11C9E: a step shows (duration & $FF) + 1 frames; flag $20 loops to step 0, $10 ends
  (the last step's count then ends the animation). Runs of the same frame and boxes collapse into export96 steps
  (ticks = frames - 1).
- boxes: the step's 5-byte records [type][y1][y2][x1][x2] x 4 px from the feet (y up); flags $08 = the boxes stay as
  they were. Type 1-15 = body (hurt), $20+ = attack ($10-$1F: other uses, not taken) -> KOF keys '31' / '11'.
- palettes: a definition's byte 0 = its palette slot (P1 base 0, P2 + 16); the fighter's 16 slots ($60-$6F) are the
  ROM blocks $CF500 + char * $A00 + colour set * $200 (32 bytes each; [meas] palette RAM = these blocks, Rock set A
  $CFF00, Terry's as P2 $CF500).
- physics [meas]: walk / jump from the object's velocity registers in our emulator (cap_garou), the values the move
  code loads.
- specials, throws: handlers_garou.py."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import garou as G

TILE_BASE = 256
CAST = {'rock': 1}
PAL_BASE = 0xCF500; PAL_CHAR = 0xA00; PAL_SET = 0x200
OWN_SLOTS = range(0x60, 0x70)                    # the fighter's 16 palette slots (P1)
COLOURS = 2                                      # colour sets exported (A, B: the second player's)

# brawler move -> Garou animation (Rock; [meas] cap_garou from vs.state / close.state: the animation the input starts)
MOVES = {
    'idle': 0x00, 'walk_fwd': 0x02, 'walk_back': 0x03, 'run': 0x18, 'prejump': 0x08,
    'jump_up_rise': 0x0B, 'jump_up_fall': 0x0C, 'jump_fwd_rise': 0x0D, 'jump_fwd_fall': 0x0E,
    'jump_back_rise': 0x0F, 'jump_back_fall': 0x10, 'land': 0x09,
    'atk_a_close': 0x23, 'atk_a_far': 0x23, 'atk_b_close': 0x24, 'atk_b_far': 0x24,
    'atk_c_close': 0x21, 'atk_c_far': 0x25, 'atk_d_close': 0x22, 'atk_d_far': 0x26,
    'atk_a_crouch': 0x27, 'atk_b_crouch': 0x28, 'atk_c_crouch': 0x29, 'atk_d_crouch': 0x2A,
    'atk_a_jump': 0x2B, 'atk_b_jump': 0x2C, 'atk_c_jump': 0x2D, 'atk_d_jump': 0x2E,
    'atk_a_jump_diag': 0x2B, 'atk_b_jump_diag': 0x2C, 'atk_c_jump_diag': 0x2D, 'atk_d_jump_diag': 0x2E,
    'cmd_fwd_a': 0x1F, 'cmd_fwd_b': 0x20,
    'body_toss': 0x22,                            # the routes' dash / no-special entries: his close D (the heaviest
                                                  # standing kick, 10 damage [meas]; Garou has no body-toss move)
    'hit_stand_light': 0x196, 'hit_stand_heavy': 0x199, 'hit_air': 0x1C1, 'blowback': 0x1B9, 'blowback_n': 0x1B9,
    'knockdown_flight': 0x1C1, 'knockdown_bounce': 0x1EE, 'knockdown_fall': 0x1EE, 'down': 0x1FB, 'getup': 0x17E,
    'trip': 0x19B,
}
LOOP = {'idle', 'walk_fwd', 'run', 'walk_back'}

def flip_tile(t, hf, vf):
    sys.path.insert(0, os.path.join(HERE, '..', 'samsho2'))
    import export_ss2 as X
    return X.flip_tile(t, hf, vf)

class Builder:
    """frames as brawler parts (mirrored to face left); palettes by Garou slot (definition byte 0)"""
    def __init__(self, ch):
        self.ch = ch; self.c = G.load()[1]
        self.tile_map, self.tiles, self.frames, self.index, self.pals = {}, [], [], {}, []
    def tile(self, code, hf):
        k = (code, hf)
        if k not in self.tile_map:
            o = (code * 128) % len(self.c); raw = self.c[o:o + 128]
            if not any(raw): return 0
            self.tile_map[k] = TILE_BASE + len(self.tiles); self.tiles.append(flip_tile(raw, hf, 0))
        return self.tile_map[k]
    def pal(self, p):
        if p not in self.pals: self.pals.append(p)
        return self.pals.index(p)
    def frame(self, fid, xy=None, ch=None, flip=0):
        """a step's frame (sprite definition fid at the step's offsets xy = (xoff, yoff)) mirrored; flip = the step's
        own H flip (flag $80 of +$6A: drawn the other way, i.e. NOT mirrored here)"""
        ch = self.ch if ch is None else ch
        key = (ch, fid, xy, flip)
        if key in self.index: return self.index[key]
        sd = G.sprite_def(ch, fid); cells = G.sprite_cells(sd)
        xo, yo = xy
        W = sd['cols'] * 16
        mirror = not flip
        x0 = (xo - W) if mirror else -xo
        vis = cells[::-1] if mirror else cells
        cols = []
        for ci, col in enumerate(vis):
            rows = {r: self.tile(t, int(mirror)) for r, t in enumerate(col) if t}
            rows = {r: t for r, t in rows.items() if t}
            if rows: cols.append((x0 + 16 * ci, yo, [rows.get(r, 0) for r in range(len(col))]))
        parts = []
        for x, tp, t in cols:
            while t and not t[-1]: t = t[:-1]
            lead = 0
            while t and not t[0]: t = t[1:]; lead += 1
            if not t: continue
            q = parts[-1] if parts else None
            if q and q['_top'] == tp + 16 * lead and q['_x'] + 16 * len(q['tiles']) == x:
                q['tiles'].append(t); continue
            parts.append({'_top': tp + 16 * lead, '_x': x, 'tiles': [t]})
        out = []
        pk = self.pal(sd['paladd'])
        for q in parts:
            n = max(len(t) for t in q['tiles'])
            out.append({'dx': q['_x'], 'dy': q['_top'], 'hflip': 0, 'vflip': 0, 'pal': pk,
                        'tiles': [t + [0] * (n - len(t)) for t in q['tiles']]})
        self.index[key] = len(self.frames)
        self.frames.append({'record': f'{ch}:{fid}', 'parts': out, 'weapon': None,
                            'garou': {'fid': fid, 'char': ch, 'xy': list(xy), 'flip': flip}})
        return self.index[key]
    def step_frame(self, ch, st):
        xo, yo = st['l'] >> 16, st['l'] & 0xFFFF
        xo -= 0x10000 if xo & 0x8000 else 0; yo -= 0x10000 if yo & 0x8000 else 0
        return self.frame(st['fid'], (xo, yo), ch, st['f6a'] >> 7 & 1)

# ---- boxes ----
def kof_box(recs):
    """records (type, y1, y2, x1, x2) (y up, x forward negative) -> KOF (cx, cy, hw, hh): y down"""
    l = min(r[3] for r in recs); r_ = max(r[4] for r in recs)
    t = min(-r[1] for r in recs); b = max(-r[2] for r in recs)
    cx, cy = (l + r_) // 2, (t + b) // 2
    return [max(-128, min(127, cx)), max(-128, min(127, cy)), min(255, max(1, (r_ - l) // 2)), min(255, max(1, (b - t) // 2))]

def is_body(t): return 1 <= t < 0x10
def is_attack(t): return t >= 0x20

def kof_boxes(boxes):
    body = [v for v in boxes if is_body(v[0])]
    atk = [v for v in boxes if is_attack(v[0])]
    out = {}
    if body: out['31'] = kof_box(body)
    if atk: out['11'] = kof_box(atk)
    return out

# ---- an animation as the game plays it (the player $11C9E) ----
def timeline(ch, a, loop=False, limit=600):
    """[{'anim', 'step', 'st', 'boxes'}] per frame: each step (dur & $FF) + 1 frames; the end flag ($10) ends; the
    loop flag ($20) restarts (loop=True: one cycle)"""
    rows, boxes = [], []
    k = 0
    while len(rows) < limit:
        st = G.step(ch, a, k)
        if not st['f76'] & 0x08: boxes = st['boxes']
        n = (st['dur'] & 0xFF) + 1
        for _ in range(n): rows.append({'anim': a, 'step': k, 'st': st, 'boxes': boxes})
        if st['f6a'] & 0x10: break
        if st['f6a'] & 0x20:
            if loop: break
            k = 0; continue
        k += 1
    return rows

def collapse(B, ch, rows, cuts=()):
    steps = []
    for k, r in enumerate(rows):
        bx = kof_boxes(r['boxes'])
        fr = B.step_frame(ch, r['st'])
        key = (fr, json.dumps(bx, sort_keys=True))
        if steps and steps[-1]['_key'] == key and k not in cuts: steps[-1]['ticks'] += 1; continue
        steps.append({'_key': key, 'frame': fr, 'ticks': 0, 'flags': 0x100 if '11' in bx else 0, 'dx': 0, 'boxes': bx,
                      'garou': [r['anim'], r['step']], '_atk': [v for v in r['boxes'] if is_attack(v[0])]})
    for i, s in enumerate(steps):                     # an attack continued by the next step (the same records): one hit
        n = steps[i + 1] if i + 1 < len(steps) else None
        if s['_atk'] and n is not None and n['_atk'] == s['_atk']: s['flags'] |= 0x4000
    for s in steps: s.pop('_key'); s.pop('_atk')
    return steps

def anim_steps(B, ch, a, loop=False):
    return collapse(B, ch, timeline(ch, a, loop=loop))

# [meas] (numbers_garou.py, cap_garou from vs.state, P1 Rock: the velocity registers): walk forward 3.0 px a frame
# (+$34 = $30000), back 2.3125, run 5.5; the jump (stick held: anim 8 for 2 frames, then $B / $D / $F): the first air
# frame rises 9.96875, gravity 0.5546875 ($8E00, +$48) a frame (jump_vy0 = the first frame's rise, as LB2's), forward /
# back vx 2.6875. (A tapped stick = Garou's hop, anims $11 / $12: the rise is cut to 2.125 after 6 frames and the
# gravity drops to 0.390625: not imported, the brawler's hop plays the jump's numbers.)
PHYS = {1: {'walk_fwd': 3.0, 'walk_back': 2.3125, 'jump_vy0': 9.96875, 'gravity': 0.5546875, 'jump_dx': 2.6875, 'prejump': 2}}
def physics(ch): return dict(PHYS[ch])

def colours(B, ch):
    """per colour set the 16-colour palettes of every slot B uses (the fighter's own slots $60-$6F from his ROM blocks)"""
    sets = []
    for s in range(COLOURS):
        row = []
        for k in B.pals:
            if k in OWN_SLOTS: a = PAL_BASE + ch * PAL_CHAR + s * PAL_SET + 32 * (k - OWN_SLOTS[0])
            else: raise ValueError(f'palette slot {k:#x} outside the fighter\'s own')
            row.append([0] + [G.u16(a + 2 * q) for q in range(1, 16)])
        sets.append(row)
    return sets

def export(names, outdir, only=None, extra=None, lab=None):
    import handlers_garou as H
    out = {'game': 'garou', 'tile_base': TILE_BASE, 'characters': {}}
    allt, tmap = [], {}
    for name in names:
        ch = CAST[name]; B = Builder(ch); B.tiles = allt; B.tile_map = tmap
        anims = {}
        for mv, a in MOVES.items():
            if only is not None and mv not in only and mv != 'watch': continue
            anims[mv] = {'slot': a, 'mode': 'loop' if mv in LOOP else 'hold', 'steps': anim_steps(B, ch, a, loop=mv in LOOP)}
        w = (extra or {}).get(name, {}).get('watch')
        if w: anims['watch'] = {'slot': w[0] or 0, 'mode': 'hold', 'steps': anim_steps(B, ch, w[0] or 0)[w[1]:][:1]}
        anims.update(H.win_anims(B, ch, name))
        sps = H.specials(B, ch, name)
        throws = H.throws(B, ch, name)
        for t, th in throws.items(): anims[t] = th.pop('anim')
        sets = colours(B, ch)
        out['characters'][name] = {'id': ch, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0], 'physics': physics(ch),
                                   'throws': throws, 'specials': sps, 'hit_sparks': [],
                                   'modes': {'sets': ['A', 'B'], 'palettes': [str(p) for p in B.pals]}}
    out['tiles'] = len(allt)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * TILE_BASE) + b''.join(allt)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    names = sys.argv[2:] or ['rock']
    ex = export(names, sys.argv[1])
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'], 'palettes', ch['modes']['palettes'])
        for sp in ch['specials']:
            print('  ', sp['input'], len(sp['rom']['prims']), 'ops', sp['rom']['length'], 'frames', sp.get('name'))
    print(ex['tiles'], 'tiles')
