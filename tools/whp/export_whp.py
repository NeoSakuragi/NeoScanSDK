#!/usr/bin/env python3
"""World Heroes Perfect fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99 export
(layer 0 of docs/brawler_data_model.md, one code path), the way tools/samsho4/export_ss4.py does for Samurai Shodown IV.

    python3 export_whp.py OUTDIR [hanzo]          -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

Sources: the ROM through whp.py (the study, /data/neogeo_dict/whp/README.md: animations $5D52C, steps, sub-animations,
sprite defs $262800 (types 2 and 3), body boxes $242800, attack box sets [$200074], palettes $1000 + 32 n) and the
captures of capture_whp.py (our emulator: which animation each move plays, the poses the game picks by vertical speed,
the timing of the knockdown, the movement, the specials and their objects).
Conversions (each checked against the game in our emulator): a WHP step shows ticks + 1 frames, the brawler's rule too
(ticks kept); a capture run of n frames = a step of ticks n - 1; WHP sprites face right, the brawler's left: every def
is mirrored about the feet (columns reversed, cells H-flipped: baked into flipped copies of the tiles); one part per
palette of a def; boxes (top, height, x forward, width in px) -> KOF's centre / half extents (x forward negative,
y up negative); a step's attack box is live when its flags have $0800 (the game's +$60D6 bit 3), the box set is the
last command 8 of the animation; body boxes are the def's (box 0, the broad box, left out).
Colour sets: A = palette $10, B = $11 (the navy costume); the effect palettes (the projectile cycles $80 / $82 / $83,
its impact $9D / $9E / $9F / $3E) the same in both: 8 palettes, the brawler's MAX_PALS.
The fury (button D): the hero rising, super_rising() ('HERO 623AB'); its MAX version (down+D): the hero desperation
move, fury(hero=True) ('MAX HERO 623AB'); both from tools/whp/handlers_whp.py's model. Normals, specials (three strengths
each) and throws from the ROM's action tables: moves_whp.py (normal_anims, rom_special, throw_export). Known limits: no hop
(WHP has one jump height: hop_* = jump_*); no trip reaction in WHP (a sweep gives the standing heavy reaction):
trip = the knockdown's start."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import whp, neo_whp as neo
import moves_whp as MW, handlers_whp as H

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = {'hanzo': 0}
CAPTURE = '/data/neogeo_dict/whp/hanzo_capture.json'
SETS = [0x10, 0x11]                               # colour A, colour B (palette RAM image $1000 + 32 n)
# brawler move -> source:
#   ('anim', n, first, last)  Hanzou's animation n (relative), its ROM steps first..last (None: to the end)
#   ('sub', n)                sub-animation n (command 14: idle, walk, run)
#   ('cap', recipe, anim, [(def, max ticks | None)...])  the runs of those defs while P1 plays anim in the capture
#                             (the poses the game picks by vertical speed, the knockdown's timing)
# Animation numbers (the normals now from moves_whp; the rest from the captures, capture_whp.py): stand A/B/C/D far $40/$44/$4C/$50, close $58/$5C/$64/$68
# (P2 within reach), crouch $70/$71/$74/$75, jump straight up $80/$81/$84/$85, forward $88/$89/$8C/$8D; C+D $54
# (a turning kick), A+B $48; hit reactions on P1 (Hanzou) under Fuuma's attacks: A $A0 (no recoil frame), B $A1,
# C $A4, D $A5 (the big recoil), knocked down $BE, hit in the air $BF, lying + getting up $1C; jumps $10 / $11 / $12,
# landing $18; win poses: $26 (the headband), $00 (arms up).
MOVES = {
    'idle': ('sub', 0x20), 'walk_fwd': ('sub', 0x21), 'run': ('sub', 0x24),
    'prejump': ('anim', 0x10, 0, 1),
    'jump_up_rise': ('cap', 'jump_up', 0x10, 'rise'), 'jump_up_fall': ('cap', 'jump_up', 0x10, 'fall'),
    'jump_fwd_rise': ('cap', 'jump_fwd', 0x11, 'rise'), 'jump_fwd_fall': ('cap', 'jump_fwd', 0x11, 'fall'),
    'jump_back_rise': ('cap', 'jump_back', 0x12, 'rise'), 'jump_back_fall': ('cap', 'jump_back', 0x12, 'fall'),
    'land': ('anim', 0x18, 1, None),
    # the normals (atk_*, body_toss, cmd_fwd_*): every button in every stance read from the ROM's action tables
    # (moves_whp.normals: the ground table $349C0, the close reach, the run and air handlers' immediates), normal_anims()
    'hit_stand_light': ('anim', 0xA1, 0, None), 'hit_stand_heavy': ('anim', 0xA5, 0, None),
    'hit_air': ('cap', 'react_air', 0xBF, [(0x84E4, 7), (0x66C, None)]),
    # the knockdown ($BE, then $1C on the floor) split the way fighter.c plays it: rising (blowback), falling (flight),
    # the floor impact and the bounce (bounce), the bounce coming down (fall), lying (down), getting up (getup)
    'blowback': ('cap', 'react_knockdown', 0xBE, [(0x61C, 2), (0x66C, None)]),
    'blowback_n': ('cap', 'react_knockdown', 0xBE, [(0x61C, 2), (0x66C, None)]),
    'knockdown_flight': ('cap', 'react_knockdown', 0xBE, [(0x670, None)]),
    'knockdown_bounce': ('cap', 'react_knockdown', 0xBE, [(0x674, None), (0x678, 11)]),
    'knockdown_fall': ('cap', 'react_knockdown', 0xBE, [(0x678, 11)]),
    'down': ('cap', 'react_knockdown', 0x1C, [(0x674, 30)]),
    'getup': ('cap', 'react_knockdown', 0x1C, [(0x638, None), (0x63C, None), (0x640, None), (0x644, None), (0x648, None), (0x734, None)]),
    'trip': ('cap', 'react_knockdown', 0xBE, [(0x61C, 2), (0x66C, None), (0x670, None)]),
    'win_a': ('anim', 0x26, 0, None),
}
ALIAS = {'hop_up_rise': 'jump_up_rise', 'hop_up_fall': 'jump_up_fall', 'hop_fwd_rise': 'jump_fwd_rise',
         'hop_fwd_fall': 'jump_fwd_fall', 'hop_back_rise': 'jump_back_rise', 'hop_back_fall': 'jump_back_fall',
         'atk_c_hop': 'atk_c_jump', 'atk_d_hop': 'atk_d_jump', 'atk_c_hop_diag': 'atk_c_jump_diag',
         'atk_d_hop_diag': 'atk_d_jump_diag', 'atk_cd_hop': 'atk_cd_jump'}
# specials: every ground special of the fighter read from the ROM with its three strengths (Bruno 2026-10-06: "every
# special move has a low / mid / high variant"): moves_whp.specials (the punch list: A / B / A+B, the kick list: C / D /
# C+D) -> rom_special() (a program per row, the rows as the variant table) and koryuuha() for the 236P projectile (TODO
# #147). Hanzou: 236P Ninpou Koryuu Ha, 23536P a second projectile, 623P the rising Koryuu, 214K the flying spin kick,
# 236K the dashing slash, 258P / 258K a high jump (no attack box; its three entries are one animation). The captured
# specials (236C / 236D / 623A / 623B / 214C / 214D, whiffs of capture_whp) are retired: ROM_SPECIALS keeps their
# captures for the voice listing (voices.py whp_list: the input each capture belongs to)
ROM_SPECIALS = {'236P': ('236aw', [0x100]), '236K': ('236cw', [0x110]), '623P': ('623aw', [0x104, 0x19]),
                '214K': ('214cw', [0x108, 0x19])}
SPECIALS = {}
# projectiles: the pool object with a live box (+$44) of the 236 A / B capture: its flight defs (one cycle loops) and
# its impact; every third frame the game shows the empty def $000C (a flicker): the brawler keeps the previous def
PROJ_FLIGHT = set(range(0xC000, 0xC018, 4)); PROJ_END = set(range(0xC030, 0xC040, 4))
BASIC = {0x4, 0x5, 0x6, 0x7, 0x9, 0xA}

def flip_tile(t, hf, vf):
    """a 128-byte .neo C tile (2 halves of 16 rows x 4 bytes; bit 0 = the leftmost pixel of a half) flipped"""
    halves = [t[0:64], t[64:128]]
    if vf: halves = [b''.join(h[r * 4:r * 4 + 4] for r in range(15, -1, -1)) for h in halves]
    if hf: halves = [bytes(int(f'{v:08b}'[::-1], 2) for v in h) for h in halves[::-1]]
    return halves[0] + halves[1]

def box_kof(top, h, x, w):
    """WHP box (px: top above the feet, height, x forward facing right, width) -> KOF's [x, y, half w, half h] (centre
    from the feet, x forward negative, y up negative); a centre past a signed byte is pulled toward the body"""
    l, r = int(min(x, x + w)), int(max(x, x + w)); lo, hi = int(top - h), int(top)
    r = min(r, 254); l = min(l, 254 - r)
    hi = min(hi, 254); lo = min(lo, 254 - hi)
    return [-(l + r) // 2, -(lo + hi) // 2, max(1, (r - l) // 2), max(1, (hi - lo) // 2)]

def kof_boxes(defw, atk):
    d = {}
    for i, b in enumerate(atk or []): d[f'1{1 + i:X}'] = box_kof(*b)
    for i, b in enumerate(whp.hurt_boxes(defw) if defw is not None else []): d[f'3{1 + i:X}'] = box_kof(*b)
    return d

class Builder:
    def __init__(self):
        self.p, self.c = neo.load()
        self.tile_map, self.frames, self.index = {}, [], {}
        self.pals = [SETS[0]]                       # the parts' palettes, in the order met (index 0 = the body)
    def tile(self, code, hf, vf):
        if not code & 0xFFFFF: return 0
        k = (code, hf, vf)
        if k not in self.tile_map: self.tile_map[k] = TILE_BASE + len(self.tile_map)
        return self.tile_map[k]
    def frame(self, w):
        """a def as brawler parts (mirrored: WHP faces right, the brawler's ROM sprites left), one part per palette"""
        if w in self.index: return self.index[w]
        sd, cols = whp.def_cells(w)
        wpx = len(cols) * 16
        parts = []
        for pal in sorted({c[1] >> 8 for col in cols for c in col if c and c[0] & 0xFFFFF}):
            tcols = []
            for col in cols[::-1]:                          # mirrored: columns right to left, every cell h-flipped
                tcols.append([self.tile(c[0], (c[1] & 1) ^ 1, c[1] >> 1 & 1) if c and c[1] >> 8 == pal else 0 for c in col])
            lead = 0
            while not any(tcols[-1]): tcols.pop()             # empty columns cost hardware sprites: trimmed
            while not any(tcols[0]): tcols.pop(0); lead += 1
            if pal not in self.pals: self.pals.append(pal)
            parts.append({'dx': -((-sd['xoff']) >> 7) - wpx + 16 * lead,   # facing right: left = feet - x off (floor)
                          'dy': -(sd['yoff'] >> 7), 'hflip': 0, 'vflip': 0,
                          'pal': self.pals.index(pal), 'tiles': tcols})
        self.index[w] = len(self.frames)
        self.frames.append({'record': f'{w:04X}', 'parts': parts, 'weapon': None})
        return self.index[w]
    def frame_multi(self, layers):
        """several defs as one frame: [(def, px forward, px up)] (an object drawn with its parts: the Koryuu Ha's tail),
        the first drawn first"""
        if len(layers) == 1 and layers[0][1:] == (0, 0): return self.frame(layers[0][0])
        k = tuple(layers)
        if k in self.index: return self.index[k]
        parts = []
        for w, dx, dy in layers:
            for q in self.frames[self.frame(w)]['parts']: parts.append(dict(q, dx=q['dx'] - dx, dy=q['dy'] - dy))
        self.index[k] = len(self.frames)
        self.frames.append({'record': '+'.join(f'{w:04X}@{dx}' for w, dx, dy in layers), 'parts': parts, 'weapon': None})
        return self.index[k]

HOLD = 120                                        # a step held until something else ends it (WHP ticks 255 / 20+ on the
                                                  # air normals: until the landing): the brawler's long hold
def step(B, defw, ticks, atk=None, chain=False):
    fi = B.frame(defw)
    return {'frame': fi, 'ticks': min(ticks, HOLD), 'flags': (0x100 if atk else 0) | (0x4000 if atk and chain else 0), 'dx': 0,
            'boxes': kof_boxes(defw, atk), 'whp_def': defw}

def anim_steps(B, n, first, last, char=0):
    st = [s for s in whp.steps_of(char, n) if not s['ctrl']]
    st = st[first:None if last is None else last + 1]
    act = [bool(s['flags'] & 0x800) for s in st]
    out = []
    for i, s in enumerate(st):
        if s['defw'] is None: continue                    # a step drawn by a sub-animation (none in the moves used)
        atk = whp.attack_boxes(s['box']) if act[i] else None
        nxt = i + 1 < len(st) and act[i + 1] and st[i + 1]['box'] == s['box']
        out.append(step(B, s['defw'], s['ticks'], atk, nxt))
    return out

def runs(frames, anim):
    """[(def, n frames, active, box set, y list)] of P1 while it plays anim"""
    out = []
    for f in frames:
        p = f[0]
        if p[0] != anim: continue
        k = (p[4], p[6], p[7])
        if out and out[-1][0] == k: out[-1][1] += 1; out[-1][2].append(p[3])
        else: out.append([k, 1, [p[3]]])
    return [(k[0], n, k[1], k[2], ys) for k, n, ys in out]

def cap_steps(B, cap, rec, anim, sel):
    rs = runs(cap[rec]['frames'], anim)
    if sel in ('rise', 'fall'):                           # a jump: the runs before / after the apex
        ys = [y for r in rs for y in r[4]]; apex = ys.index(max(ys)); k = 0; out = []
        for r in rs:
            mid = k + len(r[4]) // 2; k += len(r[4])
            if r[0] == 0x6CC or (mid <= apex) != (sel == 'rise'): continue
            out.append(step(B, r[0], r[1] - 1))
        return out
    out, i = [], 0
    for w, cap_t in sel:                                  # the runs of these defs, in order (merged when split)
        while i < len(rs) and rs[i][0] != w: i += 1
        if i >= len(rs): raise ValueError(f'{rec}: def {w:04X} not found in anim {anim:X}')
        n = 0
        while i < len(rs) and rs[i][0] == w: n += rs[i][1]; i += 1
        t = n - 1 if cap_t is None else min(n - 1, cap_t)
        out.append(step(B, w, t))
    return out

def physics(cap):
    """px / frame from the captures: walk ($9), jump ($10: y per frame fitted to y = v t - g t^2 / 2), jump dx ($11)"""
    def run(k, a): return [f[0] for f in cap[k]['frames'] if f[0][0] == a]
    w = run('walk_fwd', 0x9); walk = (w[-1][2] - w[0][2]) / (len(w) - 1)
    wb = run('walk_back', 0xA); back = abs(wb[-1][2] - wb[0][2]) / (len(wb) - 1)
    jf = [f for f in run('jump_up', 0x10)]
    t0 = next(i for i, f in enumerate(jf) if f[3] > 0) - 1     # the frame before take-off
    ys = [f[3] for f in jf[t0:]]
    n = ys.index(max(ys))                              # frames to the apex
    vy0 = 2 * max(ys) / n; g = vy0 / n
    fw = [f for f in run('jump_fwd', 0x11) if f[3] > 0]
    jdx = (fw[-1][2] - fw[0][2]) / (len(fw) - 1)
    return {'walk_fwd': walk, 'walk_back': back, 'jump_vy0': vy0, 'gravity': g, 'jump_dx': jdx, 'prejump': t0 + 1}

def special(B, inp, cap):
    rec, anims = SPECIALS[inp]; fr = cap[rec]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    e = next((i for i in range(s0, len(fr)) if fr[i][0][0] not in anims), len(fr))
    x0 = fr[s0][0][2]
    script, rboxes, rsteps = [], [], []
    pj = None
    for i in range(s0, e):
        p = fr[i][0]
        a, k, x, y, w, flip, live, bset = p[:8]
        atk = whp.attack_boxes(bset) if live else None
        script.append([B.frame(w), x - x0, y, []])
        rboxes.append(kof_boxes(w, atk))
        nlive = i + 1 < e and fr[i + 1][0][6] and fr[i + 1][0][7] == bset
        rsteps.append([a, k, (0x100 if live else 0) | (0x4000 if live and nlive else 0), 0xFF])
        for o in fr[i][2]:                                # the projectile: the object with a live box
            ok, oa, ow, ox, oy, of, obox, olive = o
            if not olive and pj is None: continue
            if pj is None:
                pj = {'k': ok, 'spawn_row': i - s0, 'x0': ox, 'spawn_x': ox - x0, 'spawn_y': oy, 'rows': [], 'end': [],
                      'box': obox, 'last': None, 'xi': None}
            if ok != pj['k']: continue
            if ow == whp.BLANK: ow = pj['last']
            if ow in PROJ_FLIGHT and olive and not pj['end']:   # (its hit-stop frames: box off, left out)
                pj['last'] = ow
                ab = whp.attack_boxes(obox)
                pj['rows'].append((B.frame(ow), ox - pj['x0'], oy, [1] + box_kof(*ab[0]) if ab and olive else None, None, ow))
            elif ow in PROJ_END:                          # (x, height from the hit's: bpend_t, TODO #164)
                if pj['xi'] is None: pj['xi'] = ox; pj['yi'] = pj['rows'][-1][2] if pj['rows'] else oy
                pj['end'].append((B.frame(ow), ox - pj['xi'], oy - pj['yi']))
    if pj is not None and len(pj['end']) == 0:            # the impact comes after the move's last row: from the capture's
        for i in range(e, len(fr)):                       # later frames
            for o in fr[i][2]:
                if o[0] == pj['k'] and o[2] in PROJ_END:
                    if pj['xi'] is None: pj['xi'] = o[3]; pj['yi'] = pj['rows'][-1][2] if pj['rows'] else o[4]
                    pj['end'].append((B.frame(o[2]), o[3] - pj['xi'], o[4] - pj['yi']))
    pjs = []
    if pj is not None:
        rows = pj['rows']; defs = [r[5] for r in rows]
        per = next((p for p in range(1, len(defs) - 2) if defs[p:] == defs[:len(defs) - p] and defs[p - 1] != defs[p]), None)
        if per: rows = rows[:per]
        pjs.append({'kind': 1, 'rows': [r[:5] for r in rows], 'loop': 0 if per else None, 'end': pj['end'],
                    'spawn_row': pj['spawn_row'], 'spawn_x': pj['spawn_x'], 'spawn_y': pj['spawn_y'], 'child': None,
                    'hit_kind': 1, 'react': 'heavy', 'travel': rows[-1][1] if rows else 0, 'hits': {}, 'name': 'KORYUUHA'})
    n = len(script)
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': [''] * n, 'projectiles': pjs, 'anims': anims,
            'shape': [max(r[1] for r in script), max(r[2] for r in script), bool(pjs)],
            'game_hits': sum(1 for j in range(s0 + 1, e) if fr[j][1][0] != fr[j - 1][1][0] and fr[j - 1][1][0] in (4, 5))}

# The desperation move (tools/whp/handlers_whp.py: the command, the hooks, the model; README "Desperation move"):
# 6 5 4 2 6 + A+C with the life under half. $128 crouch, jump back to the screen bound, hang, dive (box $A2); a dive
# that lands a hit goes on to the ninja sequence (steps 13.. + $129: vanish, five strikes placed from the victim, the
# last with a mirrored clone), a whiff lands ($128 steps 10..11, $1B). Hero version (the gauge full: down+D, the MAX):
# $12A / $12B, one more rising strike. Played from the model (the ROM's steps + Hanzou's hooks, frame-identical to WHP,
# handlers_whp.py --check); the brawler has no fixed screen bound: the hang comes after EDGE_AFTER frames of flight
# (the reference geometry: the vs. state's round-start places), the hero DM's 56-frame freeze (fp+$4141) is WHP's own
# super flash (the brawler's engine rule stands in for it), WHP's one-frame white backdrop at each teleport and the hit
# sparks are left to the brawler. The victim is held where WHP held it (its floating reel FF, carry) until the last
# strike; the effects (the kanji, the smoke at the victim, the clone) as WHP drew them in the reference run.
DM_INPUT = '65426AC'
EDGE_AFTER = 8

def fury(B, hero=False, inp=None):
    import handlers_whp as H
    refs = json.load(open(H.REF))
    rec = 'dmh' if hero else 'dm'
    rel = 0x12A if hero else 0x128
    hit = refs[rec + '_hit']; fr = hit['frames']
    vic = lambda k: tuple(fr[min(k, len(fr) - 1)]['p2'])
    mw = H.play('hanzo', rel, edge_after=EDGE_AFTER)                                   # the dive whiffs
    mh = H.play('hanzo', rel, victim=vic, hit_frames=set(hit['hits'][:1]), edge_after=EDGE_AFTER)   # the dive connects
    land = next(k for k, r in enumerate(mw) if r['anim'] == rel and r['step'] == 10)    # the landing row (step 10)
    for k in range(land + 1):
        assert (mw[k]['defw'], mw[k]['x'], mw[k]['y']) == (mh[k]['defw'], mh[k]['x'], mh[k]['y']), k
    dive = [k for k in range(land) if mw[k]['live'] is not None]
    rows = mw[:land + 1] + mw[land + 1:] + mh[land + 1:]
    parts = [{'first': 0, 'end': land + 1, 'next': 1}, {'first': land + 1, 'end': len(mw), 'next': None},
             {'first': len(mw), 'end': len(rows), 'next': None}]
    links = [{'from': 0, 'to': 2, 'on': 'hit', 'input': None, 'window': [dive[0], land + 1], 'at': 'end'}]
    script, rboxes, rsteps, carry = [], [], [], []
    hk = [k for k in range(land + 1, len(mh)) if mh[k]['live'] is not None and (k == 0 or mh[k - 1]['live'] is None)]
    last = hk[-1] if hk else len(mh)                      # the last strike's first row: the victim is let go there
    for i, r in enumerate(rows):
        pi = 0 if i < parts[1]['first'] else 1 if i < parts[2]['first'] else 2
        k = i if pi < 2 else i - len(mw) + land + 1      # the frame in its own model run
        x0 = 0.0 if pi == 0 else rows[land]['x']
        objs = []
        if pi == 2 and k < len(fr):                       # WHP's effects that frame (priority: the clones, kanji, smoke)
            fx = sorted(fr[k]['fx'], key=lambda o: [0x7A, 0x71, 0x5A, 0x5D, 0x77].index(o[0]) if o[0] in (0x7A, 0x71, 0x5A, 0x5D, 0x77) else 9)
            for task, dw, ox, oy, of in fx:
                if dw == whp.BLANK or len(objs) == 2: continue
                objs.append([B.frame(dw), round(ox - x0), round(oy), 1 if of == 0 else 0])
        script.append([B.frame(r['defw']), round(r['x'] - x0), round(r['y']), objs])
        atk = whp.attack_boxes(r['live']) if r['live'] is not None else None
        rboxes.append(kof_boxes(r['defw'], atk))
        nxt = next((q for q in rows[i + 1:] if (q['anim'], q['step']) != (r['anim'], r['step'])), None)   # the next step
        same = atk is not None and nxt is not None and nxt['live'] == r['live']   # it goes on with this box: one hit
        rsteps.append([r['anim'], r['step'], (0x100 if atk else 0) | (0x4000 if same else 0), 0xFF])
        if pi == 2 and k < last and k < len(fr):          # held where WHP had it (x; WHP's held reel FF floats 9 px:
            vx, vy = fr[k]['p2']                          # the brawler's reel stays on the floor, a height would make
            carry.append((max(-32000, min(32000, round(vx - r['x']))), 0))   # it an air hit)
        else: carry.append(None)
    n = len(script)
    inp = inp or ('MAX ' if hero else '') + DM_INPUT
    return {'input': inp, 'condition': 'desperation', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': [''] * n, 'projectiles': [], 'anims': [rel, rel + 1, 0x1B],
            'shape': [max(r[1] for r in script[:land + 1]), max(r[2] for r in script[:land + 1]), False],
            'game_hits': len(hit['hits']), 'parts': parts, 'links': links, 'carry_src': carry,
            'whp': {'rel': rel, 'land_row': land, 'dive_rows': dive, 'edge_after': EDGE_AFTER}}

# The fury (button D, Bruno 2026-10-06: "Super Shoryuha"): the hero rising, Hanzou's 623 with the hero gauge full
# (handlers_whp: the punch list's command 5, R D DR, byte FC: A / B / A+B -> $104 / $105 / $106, hero $120 / $121 /
# $122). The A+B one, $122: the fastest rise (vy 10.5 px), the spin played twice, the most damage in WHP (47 + 6 x 2 of
# 192 at point blank). Played from the model (frame-identical to WHP, handlers_whp --check sr_hit / sr_whiff); WHP's
# 55-frame freeze at step 1 (effect $24: the flashing palette, the sparkles: WHP's super flash) is the brawler's super
# flash (engine rule): Hanzou holds step 1 through it as in WHP, so the uppercut comes when the flash ends. Two parts: the uppercut (steps 0-2) and the rise (step 3 to the landing, $18); a hit in the
# uppercut goes on to the rise at once (WHP $4C188: a contact while Hanzou stands still ends the step with the
# hit-stop). Hits open where WHP's did at point blank (sr_hit: the uppercut, then six in the spin: steps 7, 8, 10, 7,
# 8, 10); the live steps between them go on with the hit before (the 'same hit' $4000 flag). The ice dragon (task $20,
# command 9 $13) as WHP drew it in the whiff (every other frame). The victim: WHP's hits launch it and it rises with
# Hanzou, hit again on the way up ($AB / $BA, its own flight: no hold); the brawler's reactions: a launch at each hit
# (KOF's 286, juggleable), the last one knocks it down.
SR_INPUT = 'HERO 623AB'
GAME_JSON = os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')
R_KNOCKDOWN, R_LAUNCH = 2, 3                      # fighter.h R_* (export_bm: special_play react_src)
SR_REL = 0x122

def runs_of(frames, key):
    """[(key, first index, end index)] of consecutive frames with the same key"""
    out = []
    for i, f in enumerate(frames):
        k = key(f)
        if out and out[-1][0] == k: out[-1][2] = i + 1
        else: out.append([k, i, i + 1])
    return out

def super_rising(B):
    import handlers_whp as H
    refs = json.load(open(H.REF))
    hit, wref = refs['sr_hit'], refs['sr_whiff']
    mw = H.play('hanzo', SR_REL, first_ticks=True)
    n = len(wref['frames'])
    mw = mw[:n]                                           # (the model goes on standing; WHP's move ends with $18)
    for k, (r, c) in enumerate(zip(mw, wref['frames'])):  # the model is WHP's whiff
        assert [r['anim'], r['step'], r['defw']] == c['p1'][:3] and abs(r['x'] - c['p1'][3]) < 1.01 and abs(r['y'] - c['p1'][4]) < 1.01, k
    fxs = [c['fx'] for c in wref['frames']]
    # WHP's freeze: Hanzou held on step 1's first frame while everybody else stops. The brawler's super flash stands
    # in for it: held through the flash (game.json super_flash: from the fury's frame start for freeze frames; row r
    # plays on fury frame r + 1), then step 1's own frames
    sf = json.load(open(GAME_JSON))['super_flash']
    s1 = next(k for k, r in enumerate(mw) if r['step'] == 1)
    hold = max(0, sf['start'] + sf['freeze'] - 1 - s1)
    mw = mw[:s1] + [dict(mw[s1]) for _ in range(hold)] + mw[s1:]
    fxs = fxs[:s1] + [[] for _ in range(hold)] + fxs[s1:]
    up_end = next(k for k, r in enumerate(mw) if r['anim'] == SR_REL and r['step'] >= 3)   # the rise's first row
    up = [k for k in range(up_end) if mw[k]['live'] is not None]
    # WHP's hits by step run: the hit capture's runs = the whiff's (the uppercut's run shorter)
    hf = hit['frames']; hr = runs_of(hf, lambda f: (f['p1'][0], f['p1'][1]))
    wr = runs_of(mw, lambda r: (r['anim'], r['step']))
    assert [k for k, _, _ in hr] == [k for k, _, _ in wr][:len(hr)], 'hit / whiff runs differ'
    opens = {j for h in hit['hits'] for j, (_, a, b) in enumerate(hr) if a <= h + 1 < b}   # the runs where life dropped
    script, rboxes, rsteps, react = [], [], [], []
    for j, (key, a, b) in enumerate(wr):
        nxt_live = j + 1 < len(wr) and mw[wr[j + 1][1]]['live'] is not None
        for k in range(a, b):
            r = mw[k]
            objs = []
            for task, dw, ox, oy, of in fxs[k]:
                if dw == whp.BLANK or abs(ox - r['x']) > 120: continue   # (parked off screen: the flicker)
                objs.append([B.frame(dw), round(ox), round(oy), 1 if of == 0 else 0])
            script.append([B.frame(r['defw']), round(r['x']), round(r['y']), objs[:2]])
            atk = whp.attack_boxes(r['live']) if r['live'] is not None else None
            rboxes.append(kof_boxes(r['defw'], atk))
            same = atk is not None and nxt_live and j + 1 not in opens
            rsteps.append([r['anim'], r['step'], (0x100 if atk else 0) | (0x4000 if same else 0), 0xFF])
            react.append((R_KNOCKDOWN if j == max(opens) else R_LAUNCH) if j in opens and k == a else None)
    nrow = len(script)
    parts = [{'first': 0, 'end': up_end, 'next': 1}, {'first': up_end, 'end': nrow, 'next': None}]
    links = [{'from': 0, 'to': 1, 'on': 'hit', 'input': None, 'window': [up[0], up_end], 'at': 'now'}]
    return {'input': SR_INPUT, 'condition': 'hero', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': [''] * nrow, 'projectiles': [], 'anims': [SR_REL, 0x18],
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False],
            'game_hits': len(hit['hits']), 'parts': parts, 'links': links, 'react_src': react,
            'whp': {'rel': SR_REL, 'flash_hold': hold, 'uppercut_rows': up, 'rise_row': up_end, 'hit_runs': sorted(opens)}}

# The projectile (TODO #147): 236 + A / B / A+B, one special '236P' with the three presses as the variant table
# (vocabulary variant.table: the row game.json roster[].variant['236P'] picks, latched at the move's start; else the
# heaviest, A+B). Read from the ROM (handlers_whp.koryuuha: Hanzou's animations $100 / $101 / $102, the effect each
# spawns at its step with command 9, the object's routine: speed 3 / 5.25 / 7.5 px, its def cycle, its two trailing
# parts, its impact; the model is frame-identical to WHP, koryuuha_check). The program: the row's animation to its end;
# the object spawned as the step with command 9 is entered (bchar_t.pfx), the shout (command 4 $A0) likewise
# (bchar_t.pvox). The object: one entity whose frame is the main def with its parts at their place behind it (the
# parts end with it at its hit, as in WHP); WHP's empty def every third frame (its flicker) keeps the def before (the
# brawler's rule for WHP's flicker); rows until it is past any screen (the brawler's off-screen test ends it). Damage:
# one hit, WHP's the same for the three (10 of 192 [meas]): the brawler's special damage for each row.
KORYUUHA_REACH = 470                              # px: rows until the object is this far (off screen from any start)

def koryuuha(B):
    import handlers_whp as H
    presses = list(H.KORYUUHA)
    states, anims_d, objects, step_fx = [], {}, [], []
    models = [H.koryuuha(p, frames=300) for p in presses]
    for v, M in enumerate(models):
        k = f'{v}:{M["anim"]:X}'; states.append(k)
        st = anim_steps(B, M['anim'], 0, None)
        for i, e in enumerate(M['steps']):
            st[i]['voices'] = [int(a, 16) for c, a in e['cmds'] if c == 4]
        st[0]['ticks'] += 1                       # the start frame shows the first step (the brawler's clock counts
                                                  # it: fighter.c pan_advance ends prog_update; handlers_ss2's rule): else
                                                  # every later step, its sound and its spawn come a frame early (TODO #181)
        st[-1]['ticks'] -= 1                      # the held last step: the program sees its end a frame after it (the
                                                  # brawler's PF_END; export_ss2's rule): WHP's length, 47 / 46 / 47 frames
        anims_d[k] = {'mode': 'hold', 'steps': st}
        step_fx.append((v, M['spawn_step'], v))
        objects.append(koryuuha_object(B, M))
    P = {'anim': 1, 'resume': 10, 'br': 9, 'end': 15}; PC_END = 0
    prims = [[P['anim'], 0, (8 | 1 << 8), None], [P['resume'], 0, 0, 0], [P['br'], PC_END, -1, 0], [P['end'], 0, 0, 0]]
    default = len(presses) - 1
    # the script (Brawler Lab data, never played: prog_only) = the default row frame by frame
    M = models[default]; st = anims_d[states[default]]['steps']
    script, rb, rs = [], [], []
    for i, s_ in enumerate(st):
        for _ in range(s_['ticks'] + 1):
            script.append([s_['frame'], 0, 0, []]); rb.append(s_['boxes']); rs.append([M['anim'], i, s_['flags'], 0xFF])
    rom = {'states': states, 'anims': anims_d, 'prims': prims, 'objects': objects, 'openings': {}, 'step_fx': step_fx,
           'hit_kind': 1, 'last_hit': -1, 'apex': -1, 'length': len(script), 'voice_frames': False,
           'vtable': {'rows': [[8] for _ in presses], 'ncol': 1, 'nvar': len(presses), 'default': default, 'vanim': 1,
                      'vobj': 1, 'vdmg': 1, 'buttons': presses, 'strengths': [MW.STRENGTH[p] for p in presses],
                      'anims': [m_['anim'] for m_ in models],
                      'speeds': [m_['object']['vx'] for m_ in models], 'spawn_frames': [m_['spawn_frame'] for m_ in models],
                      'whp_damage': [10, 10, 10]}}
    pj = [dict(objects[default], spawn_row=M['spawn_frame'])]
    return {'input': '236P', 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rb, 'row_steps': rs,
            'marks': [''] * len(script), 'projectiles': pj, 'anims': [m_['anim'] for m_ in models],
            'shape': [0, 0, True], 'game_hits': 1, 'rom': rom}

def koryuuha_object(B, M, name='KORYUUHA'):
    """a projectile of handlers_whp.koryuuha's model (its flight rows with the trailing parts as one frame, its impact)"""
    o = M['object']; ab = whp.attack_boxes(o['box'])
    rows, last, lastp = [], None, [None] * len(o['parts'])
    for r in M['rows']:
        if r['x'] > KORYUUHA_REACH: break
        d = r['defw'] if r['defw'] != whp.BLANK else last; last = d
        layers = [(d, 0, 0)]
        for j, (pd, px) in enumerate(r['parts']):
            if pd is None: continue
            pd = pd if pd != whp.BLANK else lastp[j]; lastp[j] = pd
            if pd is not None: layers.append((pd, round(px - r['x']), 0))
        rows.append([B.frame_multi(layers), r['x'], r['y'], [1] + box_kof(*ab[0]), None])
    end = [[B.frame(e['defw']), e['dx'], 0] for e in M['impact'] if e['defw'] != whp.BLANK]
    return {'kind': 1, 'rows': rows, 'loop': None, 'end': end, 'react': 'heavy', 'hit_kind': 1,
            'spawn_row': M['spawn_frame'], 'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0,
            'travel': rows[-1][1], 'vx': o['vx'], 'name': name,
            'whp': {'effect': M['effect'], 'level': o['level'], 'box': o['box'], 'parts': [p['vx'] for p in o['parts']]}}

WAVE_ROUTINE = 0x4E934                            # the wave pair's frame routine (handlers_whp.wave_objects)
def wave_object(B, wo, eo, name):
    """a wave projectile (handlers_whp.wave_flight: x / y per frame, the Koryuu Ha's def cycle, WHP's empty def every
    third frame kept as the def before) with the Koryuu Ha's impact (eo: effect_object's)"""
    ab = whp.attack_boxes(wo['box']); rows, last = [], None
    for r in H.wave_flight(wo, 300):
        if r['x'] > KORYUUHA_REACH: break
        d = r['defw'] if r['defw'] != whp.BLANK else last; last = d
        rows.append([B.frame(d), r['x'], r['y'], [1] + box_kof(*ab[0]), None])
    per, defs, loop = eo['impact']
    end = [[B.frame(d), round(eo['hit_vx'] * (t + 1)), 0] for t, d in enumerate(x for x in defs for _ in range(per)) if d != whp.BLANK]
    return {'kind': 1, 'rows': rows, 'loop': None, 'end': end, 'react': 'heavy', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'travel': rows[-1][1], 'vx': wo['vx'], 'name': name,
            'whp': {'box': wo['box'], 'level': wo.get('level'), 'vy': wo['vy'], 'ay': wo['ay'], 'period': wo['period']}}

# ---- the normals: six buttons x every stance (moves_whp.normals) -----------------------------------------------------
def normal_anims(B, name):
    """{brawler move: anim} for every normal the ROM's action tables give the fighter (moves_whp.normals: button x
    stance; a stance whose animation is another's is that move) + the inventory rows. The steps are the ROM's
    (anim_steps); a ground normal that moves (the running ones: commands 28 / 29) gets each step's travel from the
    model (handlers_whp.play: x at the step's last frame), KOF's step dx (forward = negative)"""
    import handlers_whp as H
    row, char = H.ROWS[name], H.CHARS[name]
    anims, inv = {}, []
    for n in MW.normals(row, char):
        bn = MW.brawler_name(n)
        inv.append({k: v for k, v in n.items() if k != 'addr'} | {'addr': f'{n["addr"]:X}', 'brawler': bn})
        if bn is None: continue
        st = anim_steps(B, n['rel'], 0, None, char)
        if not n['stance'].startswith('jump'):
            try: mod = H.play(name, n['rel'], hooks=False, maxf=200)
            except Exception: mod = []
            if any(abs(r['x']) > 0.01 for r in mod):
                ends = {}
                for r in mod:
                    if r['anim'] == n['rel']: ends[r['step']] = r['x']
                drawn = [i for i, s_ in enumerate(s for s in whp.steps_of(char, n['rel']) if not s['ctrl']) if s_['defw'] is not None]
                prev = 0
                for j, i in enumerate(drawn):
                    if j >= len(st): break
                    x = ends.get(i, prev); st[j]['dx'] = -(round(x) - round(prev)); prev = x
        anims[bn] = {'slot': n['rel'], 'mode': 'hold', 'steps': st,
                     'whp': {'button': n['button'], 'strength': n['strength'], 'stance': n['stance'], 'rel': n['rel']}}
    return anims, inv

# ---- the specials: every command's three strengths as one program with a variant table --------------------------------
# A special = the fighter's command (moves_whp.specials) with its three rows (low / mid / high: A / B / A+B or C / D /
# C+D). Each row is played by the model (handlers_whp.play: the ROM's entries, velocity commands, landing / goto
# branches, the character's step hooks) and becomes its own sub-program: one animation (the model's step runs, each
# a step of ticks = run - 1, the last held) and its motion in segments of constant velocity / acceleration
# (P_SET vx / vy / g, then per frame P_MOVE + P_FALL: y += vy, vy -= g; WHP's y += vy + ay / 2, vy += ay is the same
# with vy set to vy + ay / 2 and g = -ay), its projectile spawned (P_SPAWN) on the frame its effect command spawns it.
# The rows are picked at the move's start (vocabulary variant.table, latched): column 0 = the row index, the program's
# head branches on it (P_SET cnt from the column, P_BR PC_CNTLE); column 1 = the damage (the brawler's special damage
# split over the row's hits). Frame-exact to the model by construction (prog_sim below plays the program the way
# fighter.c prog_update does and compares). The 623 commands start a frame earlier in WHP (handlers_whp.play
# first_ticks [meas]).
FIRST_TICKS = {'623P', '258P', '258K'}
NOTATION = {'26P': '236P', '24P': '214P', '26K': '236K', '24K': '214K'}   # the game's two-direction motions, KOF names
P_OP = {'anim': 1, 'set': 2, 'move': 4, 'fall': 6, 'dec': 8, 'br': 9, 'resume': 10, 'jmp': 12, 'spawn': 13, 'end': 15, 'add': 27}
P_REG = {'vx': 0, 'vy': 1, 'g': 2, 'cnt': 4}
PC_CNT, PC_ALWAYS, PC_CNTLE = 4, 7, 19
R_HEAVY_ = 1

def special_input(sp): return NOTATION.get(sp['input'], sp['input'])

def segments(mod, spawn_at):
    """the model's frames -> [(first, n, vx, ax, vy, g)] of constant accelerations (px), a new one at every frame in
    spawn_at"""
    xs = [r['x'] for r in mod]; ys = [r['y'] for r in mod]
    dx = [xs[0]] + [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    dy = [ys[0]] + [ys[i] - ys[i - 1] for i in range(1, len(ys))]
    out, k = [], 0
    while k < len(mod):
        vx, vy = dx[k], dy[k]
        nxt = k + 1 < len(mod) and k + 1 not in spawn_at
        g = dy[k] - dy[k + 1] if nxt else 0.0
        ax = dx[k + 1] - dx[k] if nxt else 0.0
        j = k + 1
        while j < len(mod) and j not in spawn_at and abs(dx[j] - (vx + (j - k) * ax)) < 1e-9 and abs(dy[j] - (vy - (j - k) * g)) < 1e-9: j += 1
        out.append((k, j - k, vx, ax, vy, g)); k = j
    return out

def fx16(v): return round(v * 65536)

def row_program(tag, segs, spawns, dmg_react):
    """one row's ops [(op, a, b, v)] with labels ('L', tag, i) at its segments: per segment its velocities and frame
    count, then per frame (from its resume point): the counter (over: the next segment, in the same frame), the motion,
    the frame's end; the row's last segment over: P_END"""
    ops = [('label', ('R', tag)), (P_OP['anim'], 0, dmg_react, None)]
    cur = {}
    y = 0.0
    for i, (k, n, vx, ax, vy, g) in enumerate(segs):
        ops.append(('label', ('L', tag, i)))
        for o in spawns.get(k, []): ops.append((P_OP['spawn'], o, 0, 0))
        moving = vx or ax
        falling = vy or g or y
        for r, val, need in (('vx', vx, moving), ('vy', vy, falling), ('g', g, falling)):   # the registers as the last
            if need and cur.get(r) != fx16(val):                                         # segment left them
                ops.append((P_OP['set'], P_REG[r], 0, fx16(val))); cur[r] = fx16(val)
        ops += [(P_OP['set'], P_REG['cnt'], 0, n), (P_OP['resume'], 0, 0, 0),
                (P_OP['dec'], 0, 0, 0), (P_OP['br'], PC_CNT | 0x80, ('L', tag, i + 1), 0)]
        if moving: ops += [(P_OP['move'], 0, 0, 0)] + ([(P_OP['add'], P_REG['vx'], 0, fx16(ax))] if ax else [])
        if falling: ops += [(P_OP['fall'], 0, 0, 0)]
        ops += [(P_OP['br'], PC_ALWAYS | 0x80, -1, 0)]
        if moving: cur['vx'] = fx16(vx + n * ax)
        if falling:
            cur['vy'] = fx16(vy - n * g)
            for _ in range(n): y = max(0.0, y + vy); vy -= g
    ops += [('label', ('L', tag, len(segs))), (P_OP['end'], 0, 0, 0)]
    return ops

def prog_sim(prims, var, vars_, vcols, nframes):
    """the program as fighter.c prog_update runs it (the ops used here): per frame (x, y) px"""
    x = y = vx = vy = g = 0; cnt = 0; pres = 0; out = []
    for f in range(nframes + 1):
        pc = pres; done = False
        for _ in range(96):
            op, a, b, v = prims[pc]; pc += 1
            if op & 0x80: op &= 0x7F; v = vars_[var * vcols + b]
            if op == P_OP['anim'] or op == P_OP['spawn']: continue
            if op == P_OP['set']:
                if a == 0: vx = v
                elif a == 1: vy = v
                elif a == 2: g = v
                else: cnt = v
            elif op == P_OP['move']: x += vx
            elif op == P_OP['add']: vx += v
            elif op == P_OP['fall']:
                v0 = vy; vy -= g; y += v0
                if y <= 0: y = 0
            elif op == P_OP['dec']: cnt -= 1
            elif op == P_OP['br']:
                c = a & 0x7F
                t = cnt < 0 if c == PC_CNT else True if c == PC_ALWAYS else cnt <= v if c == PC_CNTLE else False
                if t == bool(a >> 7):
                    if b < 0: break
                    pc = b
            elif op == P_OP['resume']: pres = pc
            elif op == P_OP['jmp']: pc = b
            elif op == P_OP['end']: done = True; break
        if done: return out
        out.append((x / 65536, y / 65536))
    return out

def not_exported(name, sp):
    """why a special is not exported (None: it is): a move without an attack box in any step and no projectile is not an
    attack; one whose step hook writes a screen-absolute x (handlers_whp.hook_paths: `movew #imm, +$02`) has no meaning
    on the brawler's stage (Hanzou's 258P / 258K: the vanishing jump to the screen's left / right / middle, $35FEA)"""
    char, row = H.CHARS[name], H.ROWS[name]
    for r in sp['rows']:
        E_ = [e for e in H.entries(char, r['rel']) if e['ctrl'] is None]
        if any(e['flags'] & 0x800 for e in E_): return None
        for e in E_:
            for c, a in e['cmds']:
                if c == 9:
                    try: H.effect_object(int(a, 16)); return None
                    except Exception: pass
    places = sorted({ac[3] for r in sp['rows'] for s in range(32) for _, acts in H.hook_paths(row, r['rel'], s)
                     for ac in acts if ac[0] == '?' and ac[3].endswith(',%a5@(2)')})
    return ('no attack box, no projectile' + (f'; its step hook puts it at fixed screen places ({", ".join(places)}: '
            'screen-absolute x, none on the brawler\'s stage)' if places else ''))

def rom_special(B, name, sp):
    """a ground special (moves_whp.specials entry) -> the export's special with its program and variant table"""
    import handlers_whp as H
    char = H.CHARS[name]; inp = special_input(sp)
    nv = len(sp['rows']); default = nv - 1
    models, progs, objects, states, anims_d, nh, pjs = [], [], [], [], {}, [], []
    for v, r in enumerate(sp['rows']):
        try: mod = H.play(name, r['rel'], first_ticks=inp in FIRST_TICKS, maxf=400)
        except (KeyError, ValueError): mod = H.play(name, r['rel'], first_ticks=inp in FIRST_TICKS, maxf=400, hooks=False)
        assert len(mod) < 400, (inp, r['button'], 'no end')
        models.append(mod)
        # the steps: the model's runs of (anim, step)
        rn = runs_of(mod, lambda q: (q['anim'], q['step'], q['defw']))
        st = []
        ents = {}
        for (a, s, d), i0, i1 in rn:
            if a not in ents: ents[a] = H.entries(char, a)
            e = ents[a][s]
            live = mod[i0]['live']
            st.append(dict(step(B, d, i1 - i0 - 1, whp.attack_boxes(live) if live is not None else None),
                           voices=[int(x, 16) for c, x in e['cmds'] if c == 4], whp=[a, s], live=live))
        for j, s_ in enumerate(st):                           # one hit per run of a box set (WHP: a box set stays one
            nxt = st[j + 1] if j + 1 < len(st) else None      # hit while it is live on consecutive steps)
            if s_['live'] is not None and nxt is not None and nxt['live'] == s_['live']: s_['flags'] |= 0x4000
        opens = [j for j, s_ in enumerate(st) if s_['live'] is not None and (j == 0 or st[j - 1]['live'] != s_['live'])]
        for j, s_ in enumerate(st):
            if s_['live'] is not None: s_['react'] = 2 if opens and j >= opens[-1] else R_HEAVY_   # the last hit knocks down
        for s_ in st: s_.pop('live')
        if len(st) > 1: st[0]['ticks'] += 1                   # the start frame shows the first step (fighter.c's clock
                                                              # counts it, handlers_ss2's rule; the program ends by its
                                                              # count): else every later step, its hit and its sound come
                                                              # a frame early (TODO #181)
        k = f'{v}:{r["rel"]:X}'; states.append(k); anims_d[k] = {'mode': 'hold', 'steps': st}
        nh.append(len(opens))
        # its projectile: an effect command whose routine is a Koryuu Ha-like object (handlers_whp.effect_object)
        spawns, objs = {}, []
        for i, q in enumerate(mod):
            for eff in q['spawns']:
                try: eo = H.effect_object(eff)
                except Exception: continue                    # (not a projectile: dust, flashes)
                if eo['routine'] == WAVE_ROUTINE:             # the wave pair (handlers_whp.wave_objects)
                    for wo in H.wave_objects(eff):
                        objs.append(wave_object(B, wo, eo, inp)); spawns.setdefault(i, []).append(len(objs) - 1)
                    continue
                M_ = H.koryuuha(r['button'], frames=300, rel=r['rel'])
                objs.append(koryuuha_object(B, M_, name=inp)); spawns.setdefault(i, []).append(len(objs) - 1)
        objects.append(objs)
        progs.append((segments(mod, set(spawns)), spawns))
    vobj = max(len(o) for o in objects)
    flat_objs = []
    for objs in objects: flat_objs += objs + [objs[-1]] * (vobj - len(objs)) if objs else []
    # the program: the head picks the row (column 0), then each row's own ops
    head = [(P_OP['set'] | 0x80, P_REG['cnt'], 0, 0)]
    for v in range(nv - 1): head.append((P_OP['br'], PC_CNTLE | 0x80, ('R', v), v))
    head.append((P_OP['jmp'], 0, ('R', nv - 1), 0))
    ops = list(head)
    for v, (segs, spawns) in enumerate(progs): ops += row_program(v, segs, spawns, 0 | R_HEAVY_ << 8)
    lab, prims = {}, []
    for o in ops:
        if o[0] == 'label': lab[o[1]] = len(prims)
        else: prims.append(o)
    def res(t): return lab[t] if isinstance(t, tuple) else t
    prims = [[op, a, res(b) if op in (P_OP['br'], P_OP['jmp']) else b, v] for op, a, b, v in prims]
    assert len(prims) < 255, (inp, len(prims))
    dmg = [max(1, 8 // max(1, n_)) for n_ in nh]
    vrows = [[v, dmg[v]] for v in range(nv)]
    # the check: the program frame by frame = the model (x, y)
    for v, mod in enumerate(models):
        sim = prog_sim([(p[0], p[1], p[2], p[3] if p[3] is not None else 0) for p in prims], v, [x for r_ in vrows for x in r_], 2, len(mod) + 2)
        assert len(sim) == len(mod), (inp, v, len(sim), len(mod))
        bad = [i for i, (q, (x, y)) in enumerate(zip(mod, sim)) if abs(q['x'] - x) > 0.01 or abs(max(0.0, q['y']) - y) > 0.01]
        assert not bad, (inp, v, bad[:3], [(mod[i]['x'], mod[i]['y'], sim[i]) for i in bad[:3]])
    # the script (Brawler Lab data, never played: prog_only) = the default row frame by frame
    mod = models[default]; st = anims_d[states[default]]['steps']
    script, rb, rs = [], [], []
    k = 0
    for i, s_ in enumerate(st):
        for _ in range(s_['ticks'] + 1):
            q = mod[min(k, len(mod) - 1)]; k += 1
            script.append([s_['frame'], round(q['x']), round(q['y']), []]); rb.append(s_['boxes']); rs.append([s_['whp'][0], s_['whp'][1], s_['flags'], 0xFF])
    pj = [dict(objects[default][0], spawn_row=next(i for i, q in enumerate(mod) if any(True for _ in q['spawns'])))] if objects[default] else []
    rom = {'states': states, 'anims': anims_d, 'prims': prims, 'objects': flat_objs, 'openings': {}, 'step_fx': [],
           'hit_kind': 1, 'last_hit': -1, 'apex': -1, 'length': len(script), 'voice_frames': False,
           'vtable': {'rows': vrows, 'ncol': 2, 'nvar': nv, 'default': default, 'vanim': 1, 'vobj': vobj, 'vdmg': 2,
                      'buttons': [r['button'] for r in sp['rows']], 'strengths': [r['strength'] for r in sp['rows']],
                      'anims': [r['rel'] for r in sp['rows']], 'hits': nh, 'frames': [len(m_) for m_ in models],
                      'travel': [round(m_[-1]['x']) for m_ in models], 'height': [round(max(q['y'] for q in m_)) for m_ in models],
                      'distinct': sp['distinct']}}
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rb, 'row_steps': rs,
            'marks': [''] * len(script), 'projectiles': pj, 'anims': [r['rel'] for r in sp['rows']],
            'shape': [max(r_[1] for r_ in script), max(r_[2] for r_ in script), bool(pj)], 'game_hits': nh[default], 'rom': rom}

# ---- the throws (moves_whp.throws / throw_model) -----------------------------------------------------------------------
# throw_c = the forward throw, throw_d = the back throw (fighter.c throw_start: the stick toward the facing -> BT_THROW_C).
# The thrower's rows: the model (its animation, x / height); the victim held: command 16's entries for the victim row
# of the fighter itself (the brawler's mirror match: its own defs, export96's rule) drawn feet-centred: the def's
# visual centre (forward) and its lowest row of cells are the place (Kizuna's rule, vcentre: KOF victims line up), its
# posture key 'throw anim.step' (victim_poses_whp.json, read by eye); after the release (command 18): the brawler's
# knockdown animations by the flight's place (rising: blowback, falling: knockdown_flight, the floor touch:
# knockdown_bounce, the bounce: knockdown_fall, lying: down), the flight's x / height from the model. Impacts: the
# thrower's step with +$60D5 bit 7 (the life drop [meas]) and the victim's landing. Control return (TODO #146 rule 8,
# throwrom's): the first thrower step start at or after the last impact, at the latest its move's end.
THROW_KEYS = {'forward': 'throw_c', 'back': 'throw_d'}
RET_AFTER_LAND = 3                                # = tools/kof96/throwrom.RET_AFTER_LAND

def def_box(w):
    """(centre x forward, lowest pixel height) px of a def drawn facing right at the object (cells)"""
    sd, cols = whp.def_cells(w)
    xs = [c for c, col in enumerate(cols) if any(col)]
    ys = [r for col in cols for r, cell in enumerate(col) if cell]
    left = -(sd['xoff'] >> 7); top = sd['yoff'] >> 7
    cx = left + 16 * (min(xs) + max(xs) + 1) / 2
    return cx, top - 16 * (max(ys) + 1)

def throw_export(B, name, t):
    import handlers_whp as H
    row, char = H.ROWS[name], H.CHARS[name]
    mod = MW.throw_model(name, t['rel'], row, char, turn=t['dir'] == 'back')
    fr = mod['frames']; rel = mod['release']; land = mod['land']; end = mod['end']
    last_t = None; timeline, rows, steps = [], [], []
    tframes = [f['t'] for f in fr if f['t'] is not None]
    for i, f in enumerate(fr):
        q = f['t'] or last_t; last_t = q
        fi = B.frame(q['defw'])
        timeline.append([fi, round(q['x']), round(q['y']), 0])
        if f['t'] is not None and (not steps or steps[-1][0] != (q['anim'], q['step'])): steps.append([(q['anim'], q['step']), q['defw'], 0])
        if f['t'] is not None: steps[-1][2] += 1
        v = f['v']
        if v['phase'] == 'held':
            cx, bot = def_box(v['defw'])
            vf = B.frame_multi([(v['defw'], -round(cx), -round(bot))])
            rows.append([vf, round(v['x'] - cx - q['x']), round(v['y'] + bot - q['y']), 0, 0, f'{t["rel"]:X}.{q["step"]}', None])
        else:
            if v['phase'] == 'down': role = 'down'
            elif land is None or i < land: role = 'blowback' if i == rel or v['y'] >= fr[i - 1]['v']['y'] else 'knockdown_flight'
            elif i == land or (v['y'] <= 0 and fr[i - 1]['v']['y'] <= 0): role = 'knockdown_bounce'
            else: role = 'knockdown_fall'
            rows.append([-1, round(v['x'] - q['x']), round(max(0.0, v['y']) - q['y']), int(t['dir'] == 'back'), 0, None, role])
    impacts = [i for i, f in enumerate(fr) if f['impact']]
    last = max(impacts + ([land + RET_AFTER_LAND] if land is not None else []))
    starts = [i for i in range(1, min(end, len(fr))) if fr[i]['t'] is not None and (fr[i]['t']['anim'], fr[i]['t']['step']) != (fr[i - 1]['t']['anim'], fr[i - 1]['t']['step'])]
    cand = [i for i in starts if i >= last]
    ret = min(cand[0], end) if cand else end
    down = mod['down']
    n = max(down + 1, ret)
    anim = {'slot': t['rel'], 'mode': 'hold', 'steps': [step(B, d, k - 1) for _, d, k in steps]}
    th = {'slot': t['rel'], 'inputs': f"{t['dir']} + {t['chord']} (close)", 'table': [], 'hold': False,
          'timeline': timeline[:n], 'victims': {name: rows[:n]}, 'impacts': impacts + ([land] if land is not None else []),
          'release': rel, 'land': land, 'down': down, 'end': end, 'ret': ret, 'rom': True,
          'sheet': {'whp': {'chord': t['chord'], 'dir': t['dir'], 'anim': f"${t['rel']:X}", 'count': t['count'],
                            'reach_set': t['reach_set'], 'victim_start': f"${mod['victim_start']:X}", 'table': mod['table'],
                            'release_anim': f"${mod['release_anim']:X}"},
                    'impacts': impacts, 'release': rel, 'land': land, 'down': down, 'end': end, 'ret': ret,
                    'ret_why': f'the first thrower step start at or after the last impact (frame {last}), at the latest its move\'s end ({end})'}}
    return th, anim

def drawn_steps(cid, a):
    """an animation's steps that draw a def of their own (the held poses' step numbering)"""
    return [s for s in whp.steps_of(cid, a) if not s['ctrl'] and s['defw'] is not None]

def export(names, outdir, only=None, extra=None):
    cap = json.load(open(CAPTURE))
    B = Builder(); out = {'game': 'whp', 'tile_base': TILE_BASE, 'characters': {}}
    for name in names:
        cid = CAST[name]
        anims = {}
        for mv, src in MOVES.items():
            if src[0] == 'anim': st = anim_steps(B, src[1], src[2], src[3]); slot = src[1]
            elif src[0] == 'sub': st = [step(B, w, t) for w, t in whp.sub_steps(src[1])[0]]; slot = 0x1000 + src[1]
            else: st = cap_steps(B, cap, src[1], src[2], src[3]); slot = src[2]
            anims[mv] = {'slot': slot, 'mode': 'loop' if src[0] == 'sub' else 'hold', 'steps': st}
        normals, inventory = normal_anims(B, name)
        anims.update(normals)
        throws = {}
        for t in MW.throws(H.ROWS[name], H.CHARS[name]):
            if t['dir'] not in THROW_KEYS: continue                 # (an air throw: the brawler has none)
            th, an = throw_export(B, name, t)
            throws[THROW_KEYS[t['dir']]] = th; anims[THROW_KEYS[t['dir']]] = an
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        if only is not None: anims = {k: v for k, v in anims.items() if k in only or k in throws}
        for mv, (a, k) in (extra or {}).get(name, {}).items():   # held poses (export96's extra): the roster's watch, the
            st = drawn_steps(cid, a); k = k if k >= 0 else len(st) - 1   # lab's pose candidates: (animation, step; -1 = its last)
            anims[mv] = {'slot': a, 'mode': 'hold', 'steps': [step(B, st[k]['defw'], st[k]['ticks'])]}
        sps, sp_inv = [], []
        for sp in MW.specials(H.ROWS[name], H.CHARS[name]):   # every ground special, its three strengths
            why = not_exported(name, sp)
            sp_inv.append({'input': special_input(sp), 'command': sp['command'], 'list': sp['list'], 'distinct': sp['distinct'],
                           'rows': [{k: (f'{v:X}' if k == 'addr' else v) for k, v in r.items()} for r in sp['rows']],
                           'hero': sp['hero'], 'exported': why is None, 'why': why})
            if why: continue
            sps.append(koryuuha(B) if special_input(sp) == '236P' else rom_special(B, name, sp))
        sps += [special(B, inp, cap) for inp in SPECIALS] + [super_rising(B), fury(B, hero=True, inp='MAX ' + SR_INPUT)]
        assert len(B.pals) <= 8, f'{len(B.pals)} palettes (MAX_PALS 8)'
        sets = [[[0] + whp.palette(p)[1:] for p in [s] + B.pals[1:]] for s in SETS]
        out['characters'][name] = {'id': cid, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0],
                                   'physics': physics(cap), 'throws': throws, 'specials': sps,
                                   'whp_normals': inventory, 'whp_specials': sp_inv,
                                   'modes': {'sets': ['colour A', 'colour B'], 'palettes': [f'{p:02X}' for p in B.pals]}}
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
    ex = export(sys.argv[2:] or ['hanzo'], sys.argv[1], extra={'hanzo': {'watch': (0x00, 0)}})
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'])
        print('  pals', ch['modes']['palettes'], 'max cols', max(sum(len(p['tiles']) for p in f['parts']) for f in ch['frames']))
        for mv, a in ch['anims'].items():
            print(f"  {mv:16s} {a['slot']:4X} " + ' '.join(f"{ch['frames'][s['frame']]['record']}/{s['ticks']}{'*' if s['flags'] & 0x100 else ''}" for s in a['steps']))
        for sp in ch['specials']:
            print('  ', sp['input'], len(sp['script']), 'rows, shape', [round(v) if not isinstance(v, bool) else v for v in sp['shape']], 'projectiles',
                  [(len(p['rows']), p['loop'], len(p['end']), p['spawn_row'], round(p['spawn_x']), round(p['spawn_y'])) for p in sp['projectiles']])
    print(ex['tiles'], 'tiles')
