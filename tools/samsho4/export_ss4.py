#!/usr/bin/env python3
"""Samurai Shodown IV fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99 export
(layer 0 of docs/brawler_data_model.md, one code path).

    python3 export_ss4.py OUTDIR [haohmaru]          -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

Sources: the ROM through ss4.py (the study, /data/neogeo_dict/samsho4/README.md: animations $1C14, steps with up to 3
sprite layers, sprite definitions in bank 0, palettes $1298 -> $C0000, 6-byte boxes) and the captures of capture_ss4.py
(our emulator: which animation each move plays, the timing, the movement, the specials and their objects).

One fighter = both of SS4's modes ("spirits", byte $108324: 0 Slash, 1 Bust). Measured: the two share every normal
(same animation numbers), they differ in colours and in some specials. So the export holds
  - 4 colour sets: Slash A, Slash B, Bust A, Bust B ($1298[char*4 + mode*2 + colour], 32 palettes each);
  - every special of both: Slash's as SS4's inputs ('236C'), Bust's own ones prefixed 'BUST ' (like KOF98's 'EX ').
Conversions (each checked against the game in our emulator, see the comments): SS4 shows a step for its ticks frames,
the brawler (KOF's rule) ticks + 1, so ticks - 1; SS4 sprites face right, the brawler's left: every layer is mirrored
about the feet; per-cell flips of SS4's sprite formats (the brawler flips whole parts) are baked into flipped copies of
the tiles; boxes [type][strength][x1][x2][y1][y2] (x4 px, x forward, y up) -> KOF's centre / half extents (x forward
negative, y up negative); a box with a non-zero second byte is an attack (measured: far C hits on the step whose boxes
have it, not on the earlier step with a type $80 box), types 0-15 and $80-$8F with byte 1 = 0 are hurt boxes,
a step whose box word has bit 4 keeps the previous step's boxes. Layer 1 is the sword (rendered alone: the katana in
every move checked): each frame records which part it is ('weapon') and each step its place ('weapon': x, y, w, h in
the brawler's orientation), for a later disarm.
Known limits: 3 frames of 421 (the flame, 21-22 sprites wide) pass the brawler's 20-sprite block (clipped); effect cells
in palettes outside the fighter's 32 are drawn with palette 0; throws (SS4's are not decoded): none."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss4, neo

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = {'haohmaru': 0}
CAPTURE = '/data/neogeo_dict/samsho4/haohmaru_capture.json'
SETS = [(0, 0), (0, 1), (1, 0), (1, 1)]           # (mode, colour): Slash A, Slash B, Bust A, Bust B
# brawler move -> (animation, first step, last step (None: to the end), 'loop' | 'hold'). Animation numbers from the
# captures (capture_ss4.py): stand A/B/C close 160/162/164, far 161/163/165; D 172 (both distances in the captures;
# 173 is the far D the game plays at mid range, 236D's leading frame), crouch A-D 167/169/171/174, jump A-D 182/183/184/
# 189 straight up, 185/186/187/189 diagonal; C+D 672 (the two-handed slash); hit reactions read on P2 (Haohmaru too):
# light 198 (close A), heavy 208 (C), air 216 (crouch C on a jump), trip 224 (3D sweep), KO flight 256, down 101,
# getup 105; win 140 (the sheathing pose after 138). SS4 has no hop: a tapped jump is the regular one (hop_* = jump_*).
# Its jump has no prejump animation (the first rising step is already 12 px up): prejump = the jump's first step.
MOVES = {
    'idle': (0, 0, None, 'loop'), 'walk_fwd': (12, 0, None, 'loop'), 'run': (53, 0, None, 'loop'),
    'prejump': (16, 0, 0, 'hold'), 'jump_up_rise': (16, 1, None, 'hold'), 'jump_up_fall': (18, 0, None, 'hold'),
    'jump_fwd_rise': (20, 1, None, 'hold'), 'jump_fwd_fall': (22, 0, None, 'hold'),
    'jump_back_rise': (24, 1, None, 'hold'), 'jump_back_fall': (26, 0, None, 'hold'), 'land': (28, 0, None, 'hold'),
    'atk_a_close': (160, 0, None, 'hold'), 'atk_a_far': (161, 0, None, 'hold'),
    'atk_b_close': (162, 0, None, 'hold'), 'atk_b_far': (163, 0, None, 'hold'),
    'atk_c_close': (164, 0, None, 'hold'), 'atk_c_far': (165, 0, None, 'hold'),
    'atk_d_close': (172, 0, None, 'hold'), 'atk_d_far': (173, 0, None, 'hold'),
    'atk_a_crouch': (167, 0, None, 'hold'), 'atk_b_crouch': (169, 0, None, 'hold'),
    'atk_c_crouch': (171, 0, None, 'hold'), 'atk_d_crouch': (174, 0, None, 'hold'),
    'atk_c_jump': (184, 0, None, 'hold'), 'atk_d_jump': (189, 0, None, 'hold'),
    'atk_c_jump_diag': (187, 0, None, 'hold'), 'atk_d_jump_diag': (189, 0, None, 'hold'),
    'atk_cd_jump': (187, 0, None, 'hold'), 'body_toss': (672, 0, None, 'hold'),
    'hit_stand_light': (198, 0, None, 'hold'), 'hit_stand_heavy': (208, 0, None, 'hold'), 'hit_air': (216, 0, None, 'hold'),
    # the KO / knockdown fall 256 (12 steps) split the way fighter.c plays a knockdown: rising (blowback), falling
    # (flight), on the floor (bounce: head-first steps 5-8), the roll over (fall), then lying (down)
    'blowback': (256, 0, 2, 'hold'), 'blowback_n': (256, 0, 2, 'hold'), 'knockdown_flight': (256, 3, 4, 'hold'),
    'knockdown_bounce': (256, 5, 8, 'hold'), 'knockdown_fall': (256, 9, 11, 'hold'), 'down': (101, 0, None, 'hold'),
    'getup': (105, 0, None, 'hold'), 'trip': (224, 0, 3, 'hold'), 'win_a': (140, 0, None, 'hold'),
}
ALIAS = {'hop_up_rise': 'jump_up_rise', 'hop_up_fall': 'jump_up_fall', 'hop_fwd_rise': 'jump_fwd_rise',
         'hop_fwd_fall': 'jump_fwd_fall', 'hop_back_rise': 'jump_back_rise', 'hop_back_fall': 'jump_back_fall',
         'atk_c_hop': 'atk_c_jump', 'atk_d_hop': 'atk_d_jump', 'atk_c_hop_diag': 'atk_c_jump_diag',
         'atk_d_hop_diag': 'atk_d_jump_diag', 'atk_cd_hop': 'atk_cd_jump'}
# specials: input -> (capture recipe, the animations the move plays (its script starts at the first))
SPECIALS = {**{f'{m}{b.upper()}': (f'{m}{b}', anims[i]) for m, anims in (
                 ('236', ([432], [433], [434])), ('623', ([407, 410, 413], [408, 411, 414], [409, 412, 415])),
                 ('421', ([429], [430], [431]))) for i, b in enumerate('abc')},
            'ABC': ('ABC', [735]), 'BC': ('BC', [193]), 'AB': ('AB', [380]),
            'BUST 236D': ('BUST 236d', [417]), 'BUST 623D': ('BUST 623d', [340]), 'BUST 421C': ('BUST 421c', [418])}
# pool objects that are projectiles (they hit; the brawler's bproj_t): kind 1 travels (Senpuu Retsu Zan's tornado:
# anim 437 its launch, 360 the flight (8 px a frame, 6 steps looped), 361 the hit), kind 3 stays where it was born
# (Bust 236D's flame wave, anim 448, born 48 px ahead). Other objects (KOGETSU: Kogetsu Zan's crescent) are effects.
PROJECTILES = {'SENPUDAN': {'kind': 1, 'flight': [435, 436, 437, 438, 439, 360], 'loop_anim': (438, 439, 360), 'end_anims': [361]},
               'SENPU-HA': {'kind': 3, 'flight': [448], 'loop_anim': None, 'end_anims': []}}   # A / B / C: launch 435-437, flight 438 / 439 / 360
BASIC = {0, 2, 4, 6, 8, 12, 14}
WHIFF = 900                                       # = capture_ss4.WHIFF: P2's x in a whiff capture

def flip_tile(t, hf, vf):
    """a 128-byte .neo C tile (2 halves of 16 rows x 4 bytes; bit 0 = the leftmost pixel of a half) flipped"""
    halves = [t[0:64], t[64:128]]
    if vf: halves = [b''.join(h[r * 4:r * 4 + 4] for r in range(15, -1, -1)) for h in halves]
    if hf: halves = [bytes(int(f'{v:08b}'[::-1], 2) for v in h) for h in halves[::-1]]
    return halves[0] + halves[1]

def box_kof(b):
    """SS4 box -> (key kind, [x, y, w, h]) in KOF's convention (centre from the feet, x forward negative, y up negative,
    half extents); a centre past a signed byte is pulled toward the body (tips kept up to 254 px)"""
    t, s, x1, x2, y1, y2 = b
    x1, x2 = (v - 256 if v > 127 else v for v in (x1, x2)); y1, y2 = (v - 256 if v > 127 else v for v in (y1, y2))
    l, r = min(x1, x2) * 4, max(x1, x2) * 4; lo, hi = min(y1, y2) * 4, max(y1, y2) * 4
    r = min(r, 254); l = min(l, 254 - r)              # far tips (C's blade, Kogetsu Zan's rise): the box grows
    hi = min(hi, 254); lo = min(lo, 254 - hi)          # toward the body / the feet so its centre fits a signed byte
    return ('1' if s else '3'), [-(l + r) // 2, -(lo + hi) // 2, max(1, (r - l) // 2), max(1, (hi - lo) // 2)]

def is_hurt(b): return b[1] == 0 and (b[0] & 0x7F) < 16 and b[0] != 0x80

class Builder:
    def __init__(self):
        self.p, self.c = neo.load()
        self.tile_map, self.frames, self.index = {}, [], {}
    def tile(self, code, hf, vf):
        if not code: return 0
        k = (code, hf, vf)
        if k not in self.tile_map: self.tile_map[k] = TILE_BASE + len(self.tile_map)
        return self.tile_map[k]
    def frame(self, st):
        """a step's layers as brawler parts (mirrored: SS4 faces right, the brawler's ROM sprites left)"""
        fl = st['flags']; order = [0, 1, 2] if not (st['misc'] >> 5 & 4) else [1, 2, 0]
        key = (tuple(st['layers']), fl & 0xF0, tuple(order))
        if key in self.index: return self.index[key]
        flips = [(fl >> 7 & 1, fl >> 6 & 1), (fl >> 5 & 1, fl >> 4 & 1), (fl >> 5 & 1, fl >> 4 & 1)]
        parts, weapon = [], None
        for li in order:
            if li >= len(st['layers']): continue
            w, xo, yo = st['layers'][li]
            sd, cols = ss4.layer_cells(w, flips[li][0], flips[li][1], 0)
            if sd is None or not cols: continue
            wpx, rows = len(cols) * 16, len(cols[0])
            pal = None; tcols = []
            for col in cols[::-1]:                          # mirrored: columns right to left, every cell h-flipped
                tc = []
                for cell in col:
                    if cell is None or not (cell[0] | (cell[1] >> 4 & 0xF) << 16): tc.append(0); continue
                    tile, at = cell
                    p = (at >> 8) - 0x80
                    if pal is None: pal = p
                    assert p == pal, f'sprite {w:04X}: two palettes in one layer'
                    tc.append(self.tile(tile | (at >> 4 & 0xF) << 16, (at & 1) ^ 1, at >> 1 & 1))
                tcols.append(tc)
            if pal is None: continue
            while not any(tcols[-1]): tcols.pop()             # empty columns cost hardware sprites: trimmed
            lead = 0
            while not any(tcols[0]): tcols.pop(0); lead += 1
            x_left = -xo - wpx + 16 * lead
            if not 0 <= pal < 32: pal = 0                    # effect sprites outside the fighter's 32 palettes
            if li == 1: weapon = len(parts)
            parts.append({'dx': x_left, 'dy': -yo, 'hflip': 0, 'vflip': 0, 'pal': pal, 'tiles': tcols})
        self.index[key] = len(self.frames)
        self.frames.append({'record': ' '.join(f'{w:04X}' for w, x, y in st['layers']), 'parts': parts, 'weapon': weapon,
                            'ss4': {'layers': st['layers'], 'flags': fl, 'misc': st['misc']}})
        return self.index[key]

def step_boxes(steps):
    """per step its live boxes (bit 4 of the box word: the previous step's)"""
    out, prev = [], []
    for st in steps:
        if st['boxes'] is not None: cur = list(st['boxes'])
        elif st['boxword'] & 0x10: cur = prev
        else: cur = []
        out.append(cur); prev = cur
    return out

def kof_boxes(bl):
    d, nh, na = {}, 0, 0
    for b in bl:
        if b[1]:
            k, v = box_kof(b); d[f'1{1 + na:X}'] = v; na += 1
        elif is_hurt(b):
            k, v = box_kof(b); d[f'3{1 + nh:X}'] = v; nh += 1
    return d

def anim_steps(B, anim, first, last, dxs=None):
    steps = ss4.steps_of(0, anim); bx = step_boxes(steps)
    sel = range(first, len(steps) if last is None else last + 1)
    act = [any(b[1] for b in bx[i]) for i in range(len(steps))]
    out = []
    for i in sel:
        st = steps[i]; fl = (0x100 if act[i] else 0) | (0x4000 if act[i] and i + 1 < len(steps) and act[i + 1] else 0)
        fi = B.frame(st); fr = B.frames[fi]
        wp = fr['parts'][fr['weapon']] if fr['weapon'] is not None else None
        out.append({'frame': fi, 'ticks': max(0, st['ticks'] - 1), 'flags': fl, 'dx': -(dxs or {}).get(i, 0),
                    'boxes': kof_boxes(bx[i]), 'ss4_ticks': st['ticks'],
                    'weapon': [wp['dx'], wp['dy'], len(wp['tiles']) * 16, len(wp['tiles'][0]) * 16] if wp else None})
    return out

def physics(cap):
    """px / frame from the captures: walk (anim 12), jump (16/18: y per frame fitted to y = v t - g t^2 / 2), jump dx"""
    def run(k, anim): return [f[0] for f in cap[k]['frames'] if f[0][0] == anim]
    w = run('walk_fwd', 12); walk = (w[-1][2] - w[0][2]) / (len(w) - 1)
    ys = [f[0][3] for f in cap['jump_up']['frames'] if f[0][0] in (16, 18)]
    n = ys.index(max(ys)) + 1                         # frames to the apex (y counted from the frame before take-off)
    vy0 = 2 * max(ys) / n; g = vy0 / n
    jf = [f[0] for f in cap['jump_fwd']['frames'] if f[0][0] in (20, 22)]
    jdx = (jf[-1][2] - jf[0][2]) / (len(jf) - 1)
    return {'walk_fwd': walk, 'walk_back': walk * 0.75, 'jump_vy0': vy0, 'gravity': g, 'jump_dx': jdx, 'prejump': 2}

def special(B, inp, cap):
    rec, anims = SPECIALS[inp]; fr = cap[rec]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    e = next((i for i in range(s0, len(fr)) if fr[i][0][0] in BASIC), len(fr))
    x0 = fr[s0][0][2]
    script, rboxes, rsteps, projs, live = [], [], [], {}, {}
    for i in range(s0, e):
        a, k, x, y = fr[i][0]
        steps = ss4.steps_of(0, a); bx = step_boxes(steps)
        act = [any(b[1] for b in q) for q in bx]
        fi = B.frame(steps[k])
        objs = []
        for nm, oa, ok, ox, oy, ofl in fr[i][2]:
            ofi = B.frame(ss4.steps_of(0, oa)[ok])
            if nm in PROJECTILES:
                pj = projs.setdefault(nm, {'name': nm, 'spawn_row': i - s0, 'spawn_x': ox - x0, 'spawn_y': oy, 'rows': [],
                                           'end': [], 'x0': ox, **PROJECTILES[nm]})
                obx = step_boxes(ss4.steps_of(0, oa))[ok]
                atk = next((box_kof(b)[1] for b in obx if b[1]), None)
                own = next((box_kof(b)[1] for b in obx if not b[1]), None)
                if oa in pj['flight']: pj['rows'].append((ofi, ox - pj['x0'], oy, [1] + atk if atk else None, own, oa))
                elif oa in pj['end_anims']:
                    pj.setdefault('xi', ox); pj['end'].append((ofi, ox - pj['xi'], oy))
            else:
                objs.append([ofi, ox - x, oy, 1])
        script.append([fi, x - x0, y, objs])
        rboxes.append(kof_boxes(bx[k]))
        rsteps.append([a, k, (0x100 if act[k] else 0) | (0x4000 if act[k] and k + 1 < len(act) and act[k + 1] else 0), 0xFF])
    pjs = []
    for nm, pj in projs.items():
        rows = pj['rows']
        if pj['loop_anim'] is not None:                  # one cycle of the looping flight animation
            li = next(j for j, r in enumerate(rows) if r[5] in pj['loop_anim'])
            n = len(ss4.steps_of(0, rows[li][5])); rows = rows[:li + n]; loop = li
        else: loop = None
        pjs.append({'kind': pj['kind'], 'rows': [r[:5] for r in rows], 'loop': loop, 'end': pj['end'],
                    'spawn_row': pj['spawn_row'], 'spawn_x': pj['spawn_x'], 'spawn_y': pj['spawn_y'], 'child': None,
                    'hit_kind': 1, 'react': 'knockdown', 'travel': rows[-1][1] if rows else 0,
                    'hits': {} if pj['kind'] == 1 else {'120': {'hits': 1}}, 'name': nm})
    n = len(script)
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': [''] * n, 'projectiles': pjs, 'anims': anims,
            'shape': [max(r[1] for r in script), max(r[2] for r in script), bool(pjs)],
            # hits on P2 in the capture; -1 (not measured, check_specials' '-') for a whiff capture (P2 out of reach,
            # capture_ss4.WHIFF): 0 would read as KOF's 'whiffs on a close standing opponent' (a counter / hold)
            'game_hits': -1 if cap[rec]['recipe'][1] >= WHIFF else
                         sum(1 for j in range(s0 + 1, e) if fr[j][1][0] != fr[j - 1][1][0] and fr[j - 1][1][0] in (0, 2))}

def export(names, outdir, only=None, extra=None):
    cap = json.load(open(CAPTURE))
    B = Builder(); out = {'game': 'samsho4', 'tile_base': TILE_BASE, 'characters': {}}
    for name in names:
        cid = CAST[name]
        anims = {}
        for mv, (a, f, l, mode) in MOVES.items():
            anims[mv] = {'slot': a, 'mode': mode, 'steps': anim_steps(B, a, f, l)}
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        if only is not None: anims = {k: v for k, v in anims.items() if k in only}
        for mv, (a, k) in (extra or {}).get(name, {}).items():   # held poses (export96's extra): the roster's watch, the
            st = ss4.steps_of(cid, a); k = k if k >= 0 else len(st) - 1   # lab's pose candidates: (SS4 animation, step; -1 = its last)
            anims[mv] = {'slot': a, 'mode': 'hold', 'steps': anim_steps(B, a, k, k)}
        sps = [special(B, inp, cap) for inp in SPECIALS]
        sets = [[[0] + p[1:] for p in ss4.fighter_palettes(cid, md, co)] for md, co in SETS]
        out['characters'][name] = {'id': cid, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0],
                                   'physics': physics(cap), 'throws': {}, 'specials': sps,
                                   'modes': {'sets': ['slash A', 'slash B', 'bust A', 'bust B'],
                                             'bust_specials': [s for s in SPECIALS if s.startswith('BUST ')]}}
    out['tiles'] = len(B.tile_map)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * (TILE_BASE + len(B.tile_map)))
    for (code, hf, vf), ours in B.tile_map.items():
        region[ours * 128:(ours + 1) * 128] = flip_tile(B.c[(code * 128) % len(B.c):(code * 128) % len(B.c) + 128], hf, vf)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    ex = export(sys.argv[2:] or ['haohmaru'], sys.argv[1], extra={'haohmaru': {'watch': (140, -1)}})
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'])
        print('  pals used', sorted({p['pal'] for f in ch['frames'] for p in f['parts']}),
              'max cols', max(sum(len(p['tiles']) for p in f['parts']) for f in ch['frames']))
        for sp in ch['specials']:
            print('  ', sp['input'], len(sp['script']), 'rows, shape', sp['shape'], 'projectiles',
                  [(p['name'], len(p['rows']), p['loop'], len(p['end']), p['spawn_row']) for p in sp['projectiles']])
    print(ex['tiles'], 'tiles')
