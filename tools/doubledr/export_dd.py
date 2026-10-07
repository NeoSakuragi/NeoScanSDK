#!/usr/bin/env python3
"""Double Dragon (Technos 1995) fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99
export (layer 0 of docs/brawler_data_model.md, one code path), the way tools/kizuna and tools/whp do.

    python3 export_dd.py OUTDIR [billy billy_super]   -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

Banks: `doubledr:billy` = Billy Lee (character 0), `doubledr:billy_super` = the transformed Billy (character 1: own
animations, sprites, commands, damage rows; reached through the form link, docs/brawler_move_vocabulary.md "form").
Everything comes from the ROM (study /data/neogeo_dict/doubledr/README.md, decoder dd.py, the frame model model_dd.py,
which equals the game frame for frame: compare_dd.py); captures are proofs only, nothing is recorded:
- frames: the sprite definitions at full size (1:1: DD shows its fighters unscaled at close range), each definition
  group a part (columns 16 px apart, rows padded), per-tile H / V flips baked into tile copies, exact dedupe; group 0
  takes the fighter's colour set, later groups their own palette (effects drawn with the body: the 623 arc, the
  transformation's dragons, palette 128). The art faces left like KOF's ROM sprites; feet = the anchor + FEET px.
- boxes: [type][x][y][half w][half h] from the feet, x forward negative (KOF's convention); type bit 6 the body (hurt,
  union), bit 7 an attack (union: the transformation's two boxes, behind and in front, become one).
- normals / reactions / jumps: the animations the game plays for them (captured once to name them: tools/doubledr
  idmoves in the README), steps at DD's ticks (shown ticks + 1 frames, as the brawler), the travel of a step from the
  model (bstep_t.dx), a new hit where an attack step follows a step without one or another box set.
- specials: one move per command entry with its four buttons as the VARIANT TABLE (vocabulary `variant`): one program
  (bprim_t ops generated from the animation chain + the step handlers, model_dd) and one parameter row per button
  (velocities, step counts, the button's animations / objects, damage); the brawler plays the row its rule picks
  (bspec_t.vdef, latched at the move's start). Supers (one animation for every button): no table.
- the transformation (Billy's anim 81): the form link's transition (FORM), its program ends with P_FORM at the step
  that changes the character (attr bit 5), its steps have no hurt box; from the step that switches the palette (attr
  bit 4) its frames take the transformed colours (palette key 'form').
- palettes: palette RAM of the vs states (the ROM's palette source is not decoded): Billy A slot 18 (P1), B 34 (P2 in a
  mirror match); the transformed form A 16, B 32 (both preloaded by the game); effects their own slots.
- voices: tools/brawler/voices.py 'doubledr' (step sound bytes + the NGSS model's samples)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import dd, model_dd as M

TILE_BASE = 256                                   # = export96.TILE_BASE
CAST = {'billy': 0, 'billy_super': 1}
FEET = -4                                         # the anchor's row + 3 is the soles' last row (idle): part dy = yo + FEET
STATES = {'vs': '/data/neogeo_dict/doubledr/cap/vs.state', 'bb': '/data/neogeo_dict/doubledr/cap/bb.state',
          't': '/data/neogeo_dict/doubledr/cap/p1_01.state'}
BODY = {0: (18, 34), 1: (16, 32)}                 # colour sets A / B: palette slots (P1 / P2)
FORM_PAL = {0: (16, 32)}                          # the transformation's colours (key 'form')
PALRAM = '/data/neogeo_dict/doubledr/palram.json'

def palram():
    """palette RAM (4096 words) of the vs states, merged (a slot empty in one taken from the next): cached"""
    if os.path.exists(PALRAM): return json.load(open(PALRAM))
    import cap_dd as c
    out = [0] * 4096
    for st in STATES.values():
        pw = dd.vram_words(c.run('3:-', load=st, vram=True, ram=False)[0]['pal'])[:4096]
        for s in range(256):
            if not any(out[16 * s:16 * s + 16]): out[16 * s:16 * s + 16] = pw[16 * s:16 * s + 16]
    json.dump(out, open(PALRAM, 'w')); return out

def encode_tile(pen):
    """16x16 pens -> 128 bytes of .neo C data"""
    out = bytearray(128)
    for half, x0 in ((1, 0), (0, 8)):
        for r in range(16):
            for k, pl in enumerate((0, 2, 1, 3)):
                v = 0
                for b in range(8):
                    if pen[r, x0 + b] >> pl & 1: v |= 1 << b
                out[half * 64 + r * 4 + k] = v
    return bytes(out)

class Builder:
    """frames as brawler parts; layers = ((def, ox, oy, group-0 palette key), ...): key 'body' (the colour set's body),
    'form' (the transformed body of the set), an int slot (fixed), None (the tiles' own palettes)"""
    def __init__(self, ch):
        self.ch = ch; self.tiles, self.tile_map, self.frames, self.index = [], {}, [], {}
        self.pals = ['body']; self.autoanim = 0
    def tile(self, code, attr):
        pen = dd.tile(code | (attr >> 4 & 15) << 16)
        if attr & 1: pen = pen[:, ::-1]
        if attr & 2: pen = pen[::-1]
        if attr & 0xC: self.autoanim += 1
        if not pen.any(): return 0
        b = encode_tile(np.ascontiguousarray(pen))
        if b not in self.tile_map: self.tile_map[b] = TILE_BASE + len(self.tiles); self.tiles.append(b)
        return self.tile_map[b]
    def pal(self, key):
        if key not in self.pals: self.pals.append(key)
        return self.pals.index(key)
    def frame(self, layers):
        if isinstance(layers, int): layers = ((layers, 0, 0, 'body'),)
        if layers in self.index: return self.index[layers]
        cols = []                                         # (x, top, palette key, [tile numbers per row])
        for w, ox, oy, key in layers:
            d = dd.sdef(w)
            for c in d['cols'] if d else []:
                byk = {}
                for r, (code, at) in enumerate(c['tiles']):
                    k = key if c['group'] == 0 and key is not None else at >> 8
                    byk.setdefault(k, {})[r] = self.tile(code, at)
                for k, rows in byk.items():
                    if any(rows.values()):
                        cols.append((ox + c['xo'], oy + c['yo'], k, [rows.get(r, 0) for r in range(c['rows'])]))
        parts = []
        for x, top, k, t in cols:                         # columns side by side, same top and palette: one part
            while t and not t[-1]: t = t[:-1]
            lead = 0
            while t and not t[0]: t = t[1:]; lead += 1
            if not t: continue
            p = parts[-1] if parts else None
            if p and p['_k'] == k and p['_top'] == top + 16 * lead and p['_x'] + 16 * len(p['tiles']) == x:
                p['tiles'].append(t); continue
            parts.append({'_k': k, '_top': top + 16 * lead, '_x': x, 'tiles': [t]})
        out = []
        for p in parts:
            n = max(len(t) for t in p['tiles'])
            assert n <= 32, (layers, n)
            out.append({'dx': p['_x'], 'dy': p['_top'] + FEET, 'hflip': 0, 'vflip': 0, 'pal': self.pal(p['_k']),
                        'tiles': [t + [0] * (n - len(t)) for t in p['tiles']]})
        self.index[layers] = len(self.frames)
        self.frames.append({'record': '+'.join(f'{w}' for w, *_ in layers), 'parts': out, 'weapon': None,
                            'layers': [list(l) for l in layers]})   # (billy_proof.py: DD's drawing of the same)
        return self.index[layers]

def dd_boxes(w6):
    """the step's box records up to the end marker (a record whose type's low byte is $FF: the list walk $207C8)"""
    out = []
    for b in dd.boxes(w6):
        if b['type'] & 0xFF == 0xFF: break
        out.append(b)
    return out

def openings(ch, a):
    """per step of animation a: True where a new hit can open ($258EC: a hit sets +$1F bit 6 and nothing hits again
    until it is cleared: at the animation's start, and, in an animation with header flag bit 4 (+$1F bit 3), on entering
    a step one of whose box records has type bit 5 ($207B8): a run of attack steps is one hit, the 214 kicks and the
    super's punches hit again at each such step)"""
    hdr, st = dd.steps(ch, a); allowed = True; out = []
    for i, s in enumerate(st):
        bx = dd_boxes(s['w6'])
        if i and hdr[1] & 0x10 and any(b['type'] & 0x20 for b in bx): allowed = True
        atk = any(b['type'] & 0x80 for b in bx)
        out.append(atk and allowed)
        if atk: allowed = False
    return out

def kof_boxes(w6):
    """DD box set -> KOF keys: '31' the body union (type bit 6), '11' the attack union (bit 7)"""
    def union(bs):
        l = min(b['x'] - b['hw'] for b in bs); r = max(b['x'] + b['hw'] for b in bs)
        t = min(b['y'] - b['hh'] for b in bs); bt = max(b['y'] + b['hh'] for b in bs)
        return [max(-128, min(127, (l + r) // 2)), max(-128, min(127, (t + bt) // 2)), min(255, (r - l + 1) // 2), min(255, (bt - t + 1) // 2)]
    bx = dd_boxes(w6); out = {}
    hurt = [b for b in bx if b['type'] & 0x40]; atk = [b for b in bx if b['type'] & 0x80]
    if hurt: out['31'] = union(hurt)
    if atk: out['11'] = union(atk)
    return out

def attacks(w6): return any(b['type'] & 0x80 for b in dd_boxes(w6))

def step_travel(ch, a):
    """px forward the model moves during each step of animation a (played alone, on the floor)"""
    out, prev = {}, 0.0
    for r in M.play(ch, a, limit=200, until=()):
        if r['anim'] != a: break
        out[r['step']] = out.get(r['step'], 0.0) + r['x'] - prev; prev = r['x']
    return out

def anim_steps(B, ch, a, first=0, last=None, key='body', moving=True):
    hdr, st = dd.steps(ch, a)
    st = st[first:None if last is None else last + 1]
    tr = step_travel(ch, a) if moving else {}
    op = openings(ch, a)[first:None if last is None else last + 1]
    out, acc = [], 0.0
    for i, s in enumerate(st):
        atk = attacks(s['w6']); nx = st[i + 1] if i + 1 < len(st) else None
        chain = atk and nx is not None and attacks(nx['w6']) and not op[i + 1]   # the next attack step continues this hit
        acc += tr.get(first + i, 0.0); dx = int(round(acc)); acc -= dx
        out.append({'frame': B.frame(((s['def_'], 0, 0, key),)), 'ticks': s['ticks'], 'flags': (0x100 if atk else 0) | (0x4000 if chain else 0),
                    'dx': -dx, 'boxes': kof_boxes(s['w6']), 'dd': [a, first + i]})
    return out

# brawler move -> (DD animation, first step, last step); both forms number their animations alike (README): idle 0,
# walk 1, jumps 5 / 7 / 9, landing 11, close A-D 15 17 19 21, far 16 18 20 22, crouch 23-26, jump up 27-30, jump forward
# 31-34, reactions 50-75 (captured: idmoves, sheet react.png)
MOVES = {'idle': (0,), 'walk_fwd': (1,), 'run': (1,), 'land': (11,),
         'atk_a_close': (15,), 'atk_a_far': (16,), 'atk_b_close': (17,), 'atk_b_far': (18,), 'atk_c_close': (19,), 'atk_c_far': (20,),
         'atk_d_close': (21,), 'atk_d_far': (22,), 'atk_a_crouch': (23,), 'atk_b_crouch': (24,), 'atk_c_crouch': (25,),
         'atk_d_crouch': (26,), 'atk_c_jump': (29,), 'atk_d_jump': (30,), 'atk_c_jump_diag': (33,), 'atk_d_jump_diag': (34,),
         'atk_cd_jump': (28,), 'body_toss': (22,),
         'hit_stand_light': (50,), 'hit_stand_heavy': (52,), 'hit_air': (62,), 'blowback': (67, 0, 1), 'blowback_n': (67, 0, 1),
         'knockdown_flight': (66, 0, 0), 'knockdown_bounce': (71,), 'knockdown_fall': (67, 1, 1), 'down': (73,), 'getup': (75,),
         'trip': (69,), 'win_a': (100,)}
LOOP = {'idle', 'walk_fwd', 'run'}
ALIAS = {'hop_up_rise': 'jump_up_rise', 'hop_up_fall': 'jump_up_fall', 'hop_fwd_rise': 'jump_fwd_rise',
         'hop_fwd_fall': 'jump_fwd_fall', 'hop_back_rise': 'jump_back_rise', 'hop_back_fall': 'jump_back_fall',
         'atk_c_hop': 'atk_c_jump', 'atk_d_hop': 'atk_d_jump', 'atk_c_hop_diag': 'atk_c_jump_diag',
         'atk_d_hop_diag': 'atk_d_jump_diag', 'atk_cd_hop': 'atk_cd_jump'}
JUMPS = {'jump_up': 5, 'jump_fwd': 7, 'jump_back': 9}

def jump_steps(B, ch, a):
    """(prejump steps, rise steps, fall steps) of a jump animation from the model: on the ground before take-off, then
    split at the apex (a step whose middle frame is before it rises)"""
    rec = M.play(ch, a, limit=200, until=(0, 11, 12))
    _, st = dd.steps(ch, a)
    frames = {}
    for i, r in enumerate(rec):
        if r['anim'] == a: frames.setdefault(r['step'], []).append((i, r['y']))
    apex = max(range(len(rec)), key=lambda i: rec[i]['y'])
    pre, rise, fall = [], [], []
    for k, fs in sorted(frames.items()):
        s = st[k]; stp = {'frame': B.frame(((s['def_'], 0, 0, 'body'),)), 'ticks': max(0, len(fs) - 1), 'flags': 0, 'dx': 0,
                          'boxes': kof_boxes(s['w6']), 'dd': [a, k]}
        if max(y for _, y in fs) <= 0: pre.append(stp)
        elif fs[len(fs) // 2][0] <= apex: rise.append(stp)
        else: fall.append(stp)
    return pre, rise, fall

def physics(ch):
    h1 = dd.steps(ch, 1)[0]; h7 = dd.steps(ch, 7)[0]; h5 = dd.steps(ch, 5)[0]
    walk = -int.from_bytes(h1[2:4], 'big', signed=True) / 256
    vy0 = int.from_bytes(h5[4:6], 'big', signed=True) / 256
    g = ((h5[6] & 0xF0) << 8) / 65536
    jdx = -int.from_bytes(h7[2:4], 'big', signed=True) / 256
    rec = M.play(ch, 5, limit=200, until=(0, 11, 12))
    pre = next(i for i, r in enumerate(rec) if r['y'] > 0)
    return {'walk_fwd': walk, 'walk_back': walk, 'jump_vy0': vy0, 'gravity': g, 'jump_dx': jdx, 'prejump': pre}

# ---- specials: the program (bprim_t) from the animation chain -------------------------------------------------------
P = {'anim': 1, 'set': 2, 'mul': 3, 'move': 4, 'fricmove': 5, 'fall': 6, 'nudge': 7, 'dec': 8, 'br': 9, 'resume': 10,
     'resume_at': 11, 'jmp': 12, 'spawn': 13, 'fxoff': 14, 'end': 15, 'add': 27, 'form': 28}       # bm_chars.h P_*
REG = {'vx': 0, 'vy': 1, 'g': 2, 'fric': 3, 'cnt': 4}
PC = {'end': 0, 'land': 2, 'cnt': 4, 'always': 7}
R_HEAVY, R_KNOCKDOWN, R_LAUNCH = 1, 2, 3
SPECIAL_DAMAGE = 8                                 # export_bm.SPECIAL_DAMAGE (a special's damage, the default row)
DAMAGE = 0x266AA

def hdr_v(hdr):
    vx = int.from_bytes(hdr[2:4], 'big', signed=True); vy = int.from_bytes(hdr[4:6], 'big', signed=True)
    return -(vx << 8), vy << 8                     # 16.16, forward +, up +

def mode_of(h, s, prev_attr, first_set):
    """(mode, sets velocity on its first frame) of a step under handler h (model_dd)"""
    a = s['attr']
    if h == 0:
        if not a & 4: return 'stop', False
        return ('keep' if a & 8 else 'fric'), not first_set
    if h in (1, 11):
        return ('stop' if a & 8 else 'fric' if a & 4 else 'const'), False
    if h == 2:
        if a & 4: return 'stop', False
        return ('airup' if a & 8 else 'air'), (prev_attr is None or prev_attr & 4)
    if h == 3: return ('airup' if a & 8 else 'air'), False
    if h in (5, 12): return 'stop', False
    raise NotImplementedError(f'handler {h} in a special')

def chain(ch, a0, stop=(0, 1, 2, 3)):
    """the animations a special plays: its first, each one's next (end, or a landing for airborne ones)"""
    out, todo = [], [a0]
    while todo:
        a = todo.pop(0)
        if a in out or a in stop: continue
        out.append(a)
        hdr, st = dd.steps(ch, a); nx = hdr[7]
        if hdr[0] in (2, 3): todo.append(M.landing_anim(nx))
        if nx: todo.append(nx)
    return out

def program(ch, a0, objs_of=None):
    """ops of the special starting with animation a0: [(op name, operands...)] with labels; anims (DD numbers, the
    states), spawns [(object animation, second object?, dx, dy)]"""
    states = chain(ch, a0)
    ops = [('set', 'g', 0), ('set', 'vx', 0), ('set', 'vy', 0)]
    spawns = []
    switch = set()                                 # anims entered from a land / an end: their switch blocks
    for j, a in enumerate(states):
        hdr, st = dd.steps(ch, a); h = hdr[0]; nx = hdr[7]
        V, W = hdr_v(hdr); s_ = hdr[6] & 15; g = (hdr[6] & 0xF0) << 8
        k = 0 if s_ == 0 else 0x10000 - (0x10000 >> s_)
        land = ('SW', M.landing_anim(nx)) if h in (2, 3) else None
        if land and land[1] not in (0, 1, 2, 3): switch.add(land[1])
        elif land: land = 'END'
        endt = ('SW', nx) if nx and nx not in (0, 1, 2, 3) else 'END'
        if endt != 'END': switch.add(nx)
        ops.append(('label', ('B', a)))             # an animation started by the previous one's end or a landing
        ops.append(('anim', j))                     # ($20836) shows its first step in that frame (the switch blocks
        segs = []                                   # below) and counts its ticks from the next: played again here
        set_done = False; prev = None
        for i, s in enumerate(st):
            mode, vset = mode_of(h, s, prev, set_done)
            if h == 2 and s['attr'] & 4: set_done = False
            entry = []
            if vset:                                # (handler 0 writes only the non-zero header words: a 0 keeps
                set_done = True                     # the velocity it came with, Super Billy's 214 landing slides)
                entry += [('set', 'vx', V)] if V or h != 0 else []
                entry += [('set', 'vy', W)] if W or h != 0 else []
            if h in (5, 12) and s['attr'] & 4:
                entry.append(('spawn', len(spawns))); spawns.append((hdr[6], h == 12, -int.from_bytes(hdr[2:4], 'big', signed=True), -int.from_bytes(hdr[4:6], 'big', signed=True)))
            if h == 11 and s['attr'] & 0x20: entry.append(('form',))
            fr = s['ticks'] + 1
            if segs and not entry and segs[-1][0] == mode: segs[-1][1] += fr
            else: segs.append([mode, fr, entry])
            prev = s['attr']
        hold = bool(hdr[1] & 2); loop = bool(hdr[1] & 1)
        assert not loop, (ch, a, 'a looping animation in a special')
        for q, (mode, n, entry) in enumerate(segs):
            last = q == len(segs) - 1
            ops += entry
            if mode == 'stop' and not any(e[0] == 'set' for e in entry): ops += [('set', 'vx', 0), ('set', 'vy', 0)]
            if ('form',) in entry: break
            until_land = last and hold and mode in ('air', 'airup')
            if last and hold and not until_land: n += 1           # a grounded hold: one more frame, then its next
            if not until_land: ops.append(('set', 'cnt', n - 1 if last else n))
            ops.append(('resume',))
            if not until_land and not last: ops += [('dec',), ('br', 'cnt', 1, ('S', a, q + 1))]
            if mode == 'keep': ops += [('move',)] + ([('fall',)] if W else [])
            elif mode == 'fric':
                ops += [('mul', 'vx', k)] + ([('mul', 'vy', k)] if W or h in (1, 11) else []) + [('move',)] + ([('fall',)] if W else [])
            elif mode == 'const': ops += [('set', 'vx', V), ('set', 'vy', W), ('move',)] + ([('fall',)] if W else [])
            elif mode in ('air', 'airup'):
                ops += [('add', 'vy', g if mode == 'airup' else -g)] + ([('mul', 'vx', k)] if s_ else []) + [('move',), ('fall',), ('br', 'land', 1, land)]
            if not until_land and last: ops += [('dec',), ('br', 'cnt', 1, endt)]   # its last frame: the next now
            ops.append(('br', 'always', 1, 'yield'))
            ops.append(('label', ('S', a, q + 1)))
    for a in sorted(switch):                       # the next animation starts this frame, its frames from the next
        ops += [('label', ('SW', a)), ('anim', states.index(a)), ('resume_at', ('B', a)), ('br', 'always', 1, 'yield')]
    ops.append(('label', 'END')); ops.append(('end',))
    return ops, states, spawns

def assemble(ops):
    """labels -> op indices; -> [(name, operands...)]"""
    lab, out = {}, []
    for o in ops:
        if o[0] == 'label': lab[o[1]] = len(out)
        else: out.append(o)
    res = []
    for o in out:
        if o[0] == 'br': res.append(('br', o[1], o[2], -1 if o[3] == 'yield' else lab[o[3]]))
        elif o[0] in ('jmp', 'resume_at'): res.append((o[0], lab[o[1]]))
        else: res.append(o)
    return res

def encode(o):
    """(op, a, b, v) of one assembled op (values: ints, 16.16 / 0.16 / counts)"""
    n = o[0]
    if n == 'anim': return (P['anim'], o[1], 0, 0)
    if n in ('set', 'mul', 'add'): return (P[n], REG[o[1]], 0, o[2])
    if n == 'br': return (P['br'], PC[o[1]] | (0x80 if o[2] else 0), o[3], 0)
    if n in ('jmp', 'resume_at'): return (P[n], 0, o[1], 0)
    if n == 'spawn': return (P['spawn'], o[1], 0, 0)
    return (P[n], 0, 0, 0)

def hit_runs(ch, states):
    """per state: the hits it opens (openings) with the damage row of each ([category, level] of the step)"""
    out = {}
    for a in states:
        hdr, st = dd.steps(ch, a)
        op = openings(ch, a); hs = []
        for i, o in enumerate(op):                  # the level: the highest of the run of attack steps it opens (the
            if not o: continue                      # step at contact decides in DD: 623's hit lands on its level step)
            j, lv = i, 0
            while j < len(st) and attacks(st[j]['w6']) and (j == i or not op[j]):
                lv = max(lv, (st[j]['attr'] & 0x30) >> 4); j += 1
            hs.append(((hdr[1] & 0x60) >> 5, lv))
        out[a] = hs
    return out

def rom_steps(B, ch, a, key_of=None):
    hdr, st = dd.steps(ch, a); out = []; op = openings(ch, a)
    key = 'body'
    for i, s in enumerate(st):
        if key_of: key = key_of(i, s, key)
        nx = st[i + 1] if i + 1 < len(st) else None
        atk = attacks(s['w6'])
        chain_ = atk and nx is not None and attacks(nx['w6']) and not op[i + 1]
        out.append({'frame': B.frame(((s['def_'], 0, 0, key),)), 'ticks': s['ticks'],
                    'flags': (0x100 if atk else 0) | (0x4000 if chain_ else 0), 'dx': 0, 'boxes': kof_boxes(s['w6']), 'dd': [a, i]})
    return out

def projectile(B, spawn, var):
    """a spawned effect object (character 14, handler 1: its header velocity every frame, looping) as a travelling
    projectile: one loop of its animation (rows from the thrower's place at the spawn: spawn offset + flight), its
    attack box, its end = character 14's animation 53 (the burst) in place. The 41236 pair (the second object with
    palette $83 at step 4) drawn as one object"""
    an, pair, dx0, dy0 = spawn
    hdr, st = dd.steps(14, an)
    vx = -int.from_bytes(hdr[2:4], 'big', signed=True) / 256
    rows = []; x = float(dx0); fr = 0
    seq = [(i, s) for i, s in enumerate(st) for _ in range(s['ticks'] + 1)]
    for t, (i, s) in enumerate(seq):
        x += vx
        layers = ((s['def_'], 0, 0, None),)
        if pair:
            j, s2 = seq[(t + sum(q['ticks'] + 1 for q in st[:4])) % len(seq)]
            layers += ((s2['def_'], 0, 0, 0x83),)
        bx = kof_boxes(s['w6'])
        a = bx.get('11')
        rows.append([B.frame(layers), round(x, 3), dy0, [1] + a if a else None, a])
    _, es = dd.steps(14, 53)
    end = [[B.frame(((s['def_'], 0, 0, None),)), 0, 0] for s in es for _ in range(s['ticks'] + 1)]   # at the hit's height (bpend_t y: from it, TODO #164)
    return {'table': 0, 'state': an, 'kind': 1, 'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'loop': 0,
            'death': None, 'life': len(rows), 'travel': 300, 'vx': vx, 'rows': rows, 'end': end, 'react': 'knockdown',
            'child': None, 'hits': {}, 'sig': 0}

def special(B, ch, inp, anims, knock, default=None, form=False):
    """a command entry (anims: its animation per button; one = a super) as a special with its variant table"""
    nv = len(anims); default = nv - 1 if default is None else default
    progs = [program(ch, a) for a in anims]
    asm = [assemble(o) for o, _, _ in progs]
    assert all(len(x) == len(asm[0]) for x in asm), (ch, inp, [len(x) for x in asm])
    enc = [[encode(o) for o in x] for x in asm]
    cols, prims = [], []
    for pos in range(len(enc[0])):
        ops_ = [e[pos] for e in enc]
        assert all(o[:3] == ops_[0][:3] for o in ops_) or ops_[0][0] == P['br'], (ch, inp, pos, ops_)
        assert all(o[:3] == ops_[0][:3] for o in ops_), (ch, inp, pos, ops_)
        if len({o[3] for o in ops_}) > 1:
            cols.append([o[3] for o in ops_]); o = ops_[default]
            prims.append((o[0] | 0x80, o[1], len(cols) - 1, o[3]))
        else: prims.append(ops_[default])
    hits = [hit_runs(ch, st) for _, st, _ in progs]
    dmg_dd = [sum(dd.u16(DAMAGE + 64 * ch + 8 * c + 2 * l) for st in h.values() for c, l in st) for h in hits]
    nh = [sum(len(v) for v in h.values()) for h in hits]
    if nv > 1:                                     # the damage column: the default row deals a special's damage,
        per = [max(1, round(SPECIAL_DAMAGE * dmg_dd[v] / max(1, dmg_dd[default]) / max(1, nh[v]))) for v in range(nv)]   # the others DD's ratio
        cols.append(per); vdmg = len(cols)
    else: vdmg = 0
    # states: every row's (they share no list), objects likewise
    key_of = None
    if form:
        def key_of(i, s, key): return 'form' if s['attr'] & 0x10 or key == 'form' else 'body'
    states, anims_d, objects = [], {}, []
    for v, (_, st, sp_) in enumerate(progs):
        for a in st:
            k = f'{v}:{a}'; states.append(k)
            anims_d[k] = {'mode': 'hold' if dd.steps(ch, a)[0][1] & 2 else 'loop' if dd.steps(ch, a)[0][1] & 1 else 'once',
                          'steps': rom_steps(B, ch, a, key_of)}
            hits_last = [x for x in st if hits[v][x]]
            # the knockdown belongs to the move's LAST hit only (TODO #186): from the last step that opens a hit in the
            # last animation with hits; every earlier hit reels (R_HEAVY). 0.0.92 gave the whole last animation the
            # knockdown, so the super's (anim 82, 5 hits) first hit already launched the victim and the rest whiffed.
            # DD itself (captured in our emulator, /data/tmp/b188/out/c186_dd_capture.json): hits 1-2 reel (anims
            # 56 / 57), hits 3-5 hold the victim in its knockdown pose 69 carried 10-13 px off the floor with Billy's
            # dash, the fall (71) after the 5th; the brawler keeps hits 3-4 as reels on the floor (no low carry)
            op = openings(ch, a); lastop = max((i for i, o in enumerate(op) if o), default=None)
            for i, s in enumerate(anims_d[k]['steps']):
                if s['flags'] & 0x100:
                    s['react'] = R_KNOCKDOWN if knock and hits_last and a == hits_last[-1] and lastop is not None and i >= lastop else R_HEAVY
        objects += [projectile(B, s, v) for s in sp_]
    nstate = len(progs[0][1]); nobj = len(progs[0][2])
    # the dmg / reaction operand of P_ANIM (rows without a table: SPECIAL_DAMAGE split over its hits)
    each = max(1, SPECIAL_DAMAGE // max(1, nh[default]))
    st0 = progs[default][1]
    prims = [(p[0], p[1], each | ((R_KNOCKDOWN if knock and [x for x in st0 if hits[default][x]] and st0[p[1]] == [x for x in st0 if hits[default][x]][-1] else R_HEAVY) << 8), None)
             if p[0] == P['anim'] else p for p in prims]
    # the script (Brawler Lab data, the fallback) = the default row as the model plays it
    rec = M.play(ch, anims[default], limit=400)
    script, rb, rs = [], [], []
    for r in rec:
        s = dd.steps(ch, r['anim'])[1][r['step']]
        script.append([B.frame(((s['def_'], 0, 0, 'body'),)), int(round(r['x'])), int(round(r['y'])), []])
        rb.append(kof_boxes(s['w6'])); rs.append([r['anim'], r['step'], 0x100 if attacks(s['w6']) else 0, 0xFF])
    opens = []; prev = None
    for i, r in enumerate(rec):
        if (r['anim'], r['step']) != prev and openings(ch, r['anim'])[r['step']]: opens.append(i)
        prev = (r['anim'], r['step'])
    apex = max(range(len(rec)), key=lambda i: rec[i]['y'])
    pj = [dict(objects[default * nobj], spawn_row=next((i for i, r in enumerate(rec) if any(e[0] == 'spawn' for e in r['ev'])), 0))] if nobj else []
    rom = {'states': states, 'anims': anims_d, 'prims': [list(p) for p in prims], 'objects': objects, 'openings': {},
           'hit_kind': 1, 'last_hit': opens[-1] if opens else -1, 'apex': apex if rec[apex]['y'] > 0 else -1,
           'length': len(rec), 'voice_frames': True,
           'vtable': {'rows': [list(r) for r in zip(*cols)] if cols else [], 'ncol': len(cols), 'nvar': nv if nv > 1 else 0,
                      'default': default, 'vanim': nstate, 'vobj': nobj, 'vdmg': vdmg,
                      'buttons': 'ABCD'[:nv], 'anims': anims, 'hits': nh, 'dd_damage': dmg_dd}}
    return {'input': inp, 'condition': 'form' if form else 'super' if nv == 1 else 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rb, 'row_steps': rs,
            'marks': [''] * len(script), 'projectiles': pj, 'anims': anims,
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False], 'game_hits': len(opens),
            'rom': rom, 'model_events': [[i, e] for i, r in enumerate(rec) for e in r['ev']]}

# command entries (commands_dd.py) per form: input -> (animation per button A..D, knocks down): the victim's
# reaction measured in the specials capture (specials.json p2_anims: 66-70 = a knockdown, 50-61 standing reels)
SPECIALS = {0: {'623': ([87, 88, 89, 90], True), '236': ([83, 84, 85, 86], True), '214': ([91, 92, 93, 94], False),
                'SUPER 236': ([82], True), 'FORM': ([81], True)},
            1: {'623': ([91, 92, 93, 94], True), '41236': ([87, 88, 89, 90], True), '236': ([83, 84, 85, 86], True),
                '214': ([95, 96, 97, 98], True)}}

def export(names, outdir, only=None, extra=None):
    pr = palram()
    out = {'game': 'doubledr', 'tile_base': TILE_BASE, 'characters': {}}
    allt = []
    for name in names:
        ch = CAST[name]; B = Builder(ch)
        scale = (extra or {}).get(name, {}).get('scale', 1)    # game.json roster[].scale (Bruno 2026-10-06: full
        assert scale == 1, f'{name}: scale {scale}: only 1 is exported so far'   # size, 115 px; another scale: the
                                                       # definitions through the LSPC shrink tables first, as export_kz)
        B.tiles = allt; B.tile_map = {bytes(t): TILE_BASE + i for i, t in enumerate(allt)}
        anims = {}
        for mv, src in MOVES.items():
            st = anim_steps(B, ch, src[0], *(src[1:] if len(src) > 1 else ()))
            anims[mv] = {'slot': src[0], 'mode': 'loop' if mv in LOOP else 'hold', 'steps': st}
        for j, a in JUMPS.items():
            pre, rise, fall = jump_steps(B, ch, a)
            if j == 'jump_up': anims['prejump'] = {'slot': a, 'mode': 'hold', 'steps': pre}
            anims[j + '_rise'] = {'slot': a, 'mode': 'hold', 'steps': rise}
            anims[j + '_fall'] = {'slot': a, 'mode': 'hold', 'steps': fall}
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        w = (extra or {}).get(name, {}).get('watch')
        if w:
            st = dd.steps(ch, w[0])[1]; k = w[1] if w[1] >= 0 else len(st) - 1
            anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': [{'frame': B.frame(st[k]['def_']), 'ticks': 0, 'flags': 0, 'dx': 0, 'boxes': {}}]}
        if only is not None: anims = {k: v for k, v in anims.items() if k in only}
        for mv, (a, f, l) in ((extra or {}).get(name, {}).get('anims') or {}).items():   # whole animations by request (export_bm FLASH_POSES: the flash pose, TODO #145): {move: (anim, first, last)}
            anims[mv] = {'slot': a, 'mode': 'hold', 'steps': anim_steps(B, ch, a, f, l, moving=False)}
        sps = [special(B, ch, inp, an, kn, form=inp == 'FORM') for inp, (an, kn) in SPECIALS[ch].items()]
        def colours(key, s):
            slot = BODY[ch][s] if key == 'body' else FORM_PAL[ch][s] if key == 'form' else key
            return [0] + pr[16 * slot + 1:16 * slot + 16]
        sets = [[colours(k, s) for k in B.pals] for s in range(2)]
        assert all(any(c) for st_ in sets for c in st_), (name, 'an empty palette', B.pals)
        out['characters'][name] = {'id': ch, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0], 'physics': physics(ch),
                                   'throws': {}, 'specials': sps,
                                   'modes': {'sets': ['P1', 'P2'], 'palettes': [str(k) for k in B.pals], 'autoanim_tiles': B.autoanim}}
    out['tiles'] = len(allt)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * TILE_BASE) + b''.join(allt)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    ex = export(sys.argv[2:] or ['billy', 'billy_super'], sys.argv[1], extra={'billy': {'watch': (0, 0)}, 'billy_super': {'watch': (0, 0)}})
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'], 'pals', ch['modes'])
        print('  max cols', max(sum(len(p['tiles']) for p in f['parts']) for f in ch['frames']))
        for sp in ch['specials']:
            r = sp['rom']; v = r['vtable']
            print('  ', sp['input'], len(sp['script']), 'rows,', len(r['prims']), 'ops,', v['nvar'], 'rows x', v['ncol'], 'cols', v['rows'], 'hits', v['hits'], 'dd', v['dd_damage'])
    print(ex['tiles'], 'tiles')
