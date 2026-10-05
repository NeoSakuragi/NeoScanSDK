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
Known limits: the desperation moves (WHP's hero gauge, a full gauge needed) and throws are not captured; no hop
(WHP has one jump height: hop_* = jump_*); no trip reaction in WHP (a sweep gives the standing heavy reaction):
trip = the knockdown's start."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import whp, neo_whp as neo

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = {'hanzo': 0}
CAPTURE = '/data/neogeo_dict/whp/hanzo_capture.json'
SETS = [0x10, 0x11]                               # colour A, colour B (palette RAM image $1000 + 32 n)
# brawler move -> source:
#   ('anim', n, first, last)  Hanzou's animation n (relative), its ROM steps first..last (None: to the end)
#   ('sub', n)                sub-animation n (command 14: idle, walk, run)
#   ('cap', recipe, anim, [(def, max ticks | None)...])  the runs of those defs while P1 plays anim in the capture
#                             (the poses the game picks by vertical speed, the knockdown's timing)
# Animation numbers from the captures (capture_whp.py): stand A/B/C/D far $40/$44/$4C/$50, close $58/$5C/$64/$68
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
    'atk_a_close': ('anim', 0x58, 0, None), 'atk_a_far': ('anim', 0x40, 0, None),
    'atk_b_close': ('anim', 0x5C, 0, None), 'atk_b_far': ('anim', 0x44, 0, None),
    'atk_c_close': ('anim', 0x64, 0, None), 'atk_c_far': ('anim', 0x4C, 0, None),
    'atk_d_close': ('anim', 0x68, 0, None), 'atk_d_far': ('anim', 0x50, 0, None),
    'atk_a_crouch': ('anim', 0x70, 0, None), 'atk_b_crouch': ('anim', 0x71, 0, None),
    'atk_c_crouch': ('anim', 0x74, 0, None), 'atk_d_crouch': ('anim', 0x75, 0, None),
    'atk_c_jump': ('anim', 0x84, 0, None), 'atk_d_jump': ('anim', 0x85, 0, None),
    'atk_c_jump_diag': ('anim', 0x8C, 0, None), 'atk_d_jump_diag': ('anim', 0x8D, 0, None),
    'atk_cd_jump': ('anim', 0x8D, 0, None), 'body_toss': ('anim', 0x54, 0, None),
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
# specials: input -> (whiff capture, the animations the move plays). Hanzou in WHP: 236 A / B Ninpou Koryuu Ha (the
# projectile, $100 / $101), 236 C / D the dashing slash ($110 / $111, 116 px forward), 623 A / B the rising Koryuu
# ($104 / $105, 51 / 80 px up, a hit on every step), 214 C / D the flying kick ($108 / $109, 61 px forward, 23 up,
# a spin of four steps that hits on every other one); the landing ($19) is part of the move
SPECIALS = {'236A': ('236aw', [0x100]), '236B': ('236bw', [0x101]), '236C': ('236cw', [0x110]), '236D': ('236dw', [0x111]),
            '623A': ('623aw', [0x104, 0x19]), '623B': ('623bw', [0x105, 0x19]),
            '214C': ('214cw', [0x108, 0x19]), '214D': ('214dw', [0x109, 0x19])}
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

HOLD = 120                                        # a step held until something else ends it (WHP ticks 255 / 20+ on the
                                                  # air normals: until the landing): the brawler's long hold
def step(B, defw, ticks, atk=None, chain=False):
    fi = B.frame(defw)
    return {'frame': fi, 'ticks': min(ticks, HOLD), 'flags': (0x100 if atk else 0) | (0x4000 if atk and chain else 0), 'dx': 0,
            'boxes': kof_boxes(defw, atk), 'whp_def': defw}

def anim_steps(B, n, first, last):
    st = [s for s in whp.steps_of(0, n) if not s['ctrl']]
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
            elif ow in PROJ_END:
                if pj['xi'] is None: pj['xi'] = ox
                pj['end'].append((B.frame(ow), ox - pj['xi'], oy))
    if pj is not None and len(pj['end']) == 0:            # the impact comes after the move's last row: from the capture's
        for i in range(e, len(fr)):                       # later frames
            for o in fr[i][2]:
                if o[0] == pj['k'] and o[2] in PROJ_END:
                    if pj['xi'] is None: pj['xi'] = o[3]
                    pj['end'].append((B.frame(o[2]), o[3] - pj['xi'], o[4]))
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
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        w = (extra or {}).get(name, {}).get('watch')
        if w:                                            # roster watch pose: (animation, step; -1 = its last)
            st = [s for s in whp.steps_of(cid, w[0]) if not s['ctrl'] and s['defw'] is not None]
            k = w[1] if w[1] >= 0 else len(st) - 1
            anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': [step(B, st[k]['defw'], st[k]['ticks'])]}
        if only is not None: anims = {k: v for k, v in anims.items() if k in only}
        sps = [special(B, inp, cap) for inp in SPECIALS]
        sets = [[[0] + whp.palette(p)[1:] for p in [s] + B.pals[1:]] for s in SETS]
        out['characters'][name] = {'id': cid, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0],
                                   'physics': physics(cap), 'throws': {}, 'specials': sps,
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
