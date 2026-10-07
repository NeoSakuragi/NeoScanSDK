#!/usr/bin/env python3
"""Kizuna Encounter fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99 export
(layer 0 of docs/brawler_data_model.md, one code path), the way tools/samsho4 and tools/whp do (spec `kizuna:kim`).

    python3 export_kz.py OUTDIR [kim]          -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin
    python3 export_kz.py OUTDIR NAME           any fighter of fighters_kz.CAST (spec `kizuna:NAME`)

Any fighter (setup(name), one code path): Kim's tables below moved to its animations through the state map
(fighters_kz.kim_anim: the same states, other animation numbers), its own colour sets ($1438 / $1458[char]), its
captures (fighters_kz.path), its specials from plan_kz.py (the multipart ones as FOLLOW entries made from its brute
force); its down+A in the air = its air special (plan 'air') or else its j.B. Kim keeps his hand-written tables.

Sources: the ROM through kz.py (the study /data/neogeo_dict/kizuna/README.md: animations $80000[char], steps,
13 sprite-definition formats, boxes, palettes $70000 + 32 n) and the captures of capture_kz.py (our emulator: which
animation each move plays, the jumps' and knockdown's timing, the specials as played, Kim's travel).

**Size**: every frame is drawn the way Kizuna draws it with its camera zoomed out to its widest in play (shrink Z =
$CC: the fighters 208 px or more apart), kz.render_step_zoom = the LSPC's own horizontal pixel pattern and L0 vertical
line table, pixel-identical to Kizuna's VRAM at that zoom (check_frames.py), then cut into new 16x16 tiles: fewer
columns (sprites per line) and fewer tiles than full size; every distance (offsets, boxes, travel, speeds) scaled by
S = (Z + 1) / 256 = 0.80 with it.
Conversions: Kizuna steps show `ticks` frames, the brawler's ticks + 1 (ticks - 1 kept); Kizuna draws facing right,
the brawler's ROM sprites face left: the shrunk image is mirrored about the feet (the brawler's own facing-right flip
gives back Kizuna's image exactly); one part per palette and per run of non-empty columns; tiles deduplicated (exact);
boxes [type][b1][x left][x right][y bottom][y top] x 4 px (forward / up positive) -> KOF's centre / half extents
(x forward negative, y up negative); a step's attack box is live when its boxes in force (a step's trailer bit 4 keeps
the previous step's) include a type >= $10.
Colour sets: A = ROM palettes $88 + k, B = $1C0 + k (code $13B2: tables $1438 / $1458 by character, bit 7 of the pick
byte = colour B), k = the slot - 16 (Kim's sprites use slots 16, 17).
Throw (throw_c = Kizuna's 6C / 4C, $6F, its only throw; throw_d falls back to it): the capture throw_fc (P2 Hayate
not pinned after the grab): the thrower's step per frame, the victim's place (object dx + the visual centre of Kim's
own frame for that victim state, scaled) and state step as a posture key 'state.step' (victim_poses_kz.json: the
victim states $10C (Hayate's $EF, Kim's $FA) and $17A ($DE), postures read by eye from Kim's frames), until the victim
lands; Kim's own frames for those postures are his reaction frames (feet-centred, so KOF victims and he line up).
Not exported: A+B (dodge $20) and C+D (taunt $21): the brawler has no slot for them (A+B is the special chord).
Effects (TODO #144): his own effect objects are drawn: the Phoenix's flames as FOLLOW 'objects' (each place's PHOELX
halves one frame, two places a row) and every other one (the Hienzan pillar, 214B / 236A's ADH EFFE, 421A's
afterimages, the Phoenix's further feathers) as pinned effects (effects()); kim_effects_check.py proves it against
Kizuna's screen. Known limits: Kizuna's generic hit sparks / marks are not drawn (the brawler plays its own); no D button
attacks in Kizuna (D = tag): the brawler's D normals use his strong kick (B+C, $6E); one jump height (hop = jump)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kz, fighters_kz as FK
import numpy as np

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = FK.CAST
CH, NAME = 5, 'kim'
CAPTURE = '/data/neogeo_dict/kizuna/kim_capture.json'
Z = 0xCC                                          # Kizuna's widest in-play zoom ($10966A, measured: zoom_probe.py)
S = (Z + 1) / 256
SETS = [0x88, 0x1C0]                              # colour A / B: ROM palette of slot 16 (+ k for slot 16 + k)
W, H, X0, Y0 = 640, 640, 320, 520                 # render canvas, the feet at (X0, Y0)

def sc(v): return int(round(v * S))

# brawler move -> source: ('anim', n, first, last) Kim's animation n, its ROM steps first..last (None: to the end);
# ('cap', recipe, anims, 'rise' | 'fall') the steps P1 shows before / after the apex of a jump capture
MOVES = {
    'idle': ('anim', 0xA0, 0, None), 'walk_fwd': ('anim', 0x1, 0, None), 'run': ('anim', 0x3, 1, 2),
    'prejump': ('anim', 0x9, 0, 0),
    'jump_up_rise': ('cap', 'jump_up', (0x9, 0x81), 'rise'), 'jump_up_fall': ('cap', 'jump_up', (0x9, 0x81), 'fall'),
    'jump_fwd_rise': ('cap', 'jump_fwd', (0xA, 0x81), 'rise'), 'jump_fwd_fall': ('cap', 'jump_fwd', (0xA, 0x81), 'fall'),
    'jump_back_rise': ('cap', 'jump_back', (0xB, 0x81), 'rise'), 'jump_back_fall': ('cap', 'jump_back', (0xB, 0x81), 'fall'),
    'land': ('anim', 0x82, 0, None),
    'atk_a_close': ('anim', 0x48, 0, None), 'atk_a_far': ('anim', 0x46, 0, None),
    'atk_b_close': ('anim', 0x52, 0, None), 'atk_b_far': ('anim', 0x50, 0, None),
    'atk_c_close': ('anim', 0x5B, 0, None), 'atk_c_far': ('anim', 0x5A, 0, None),
    'atk_d_close': ('anim', 0x6E, 0, None), 'atk_d_far': ('anim', 0x6E, 0, None),
    'atk_a_crouch': ('anim', 0x4B, 0, None), 'atk_b_crouch': ('anim', 0x55, 0, None),
    'atk_c_crouch': ('anim', 0x5E, 0, None), 'atk_d_crouch': ('anim', 0x5F, 0, None),
    # air: A = j.C ($60), down+A = the air dive j.2B ($8F: Kizuna's command $26, 2B in a jump), up+A = j.A ($4E)
    'atk_c_jump': ('anim', 0x60, 0, None), 'atk_d_jump': ('anim', 0x8F, 0, None),
    'atk_c_jump_diag': ('anim', 0x60, 0, None), 'atk_d_jump_diag': ('anim', 0x8F, 0, None),
    'atk_cd_jump': ('anim', 0x4E, 0, None), 'body_toss': ('anim', 0x5C, 0, None),
    'cmd_fwd_a': ('anim', 0x49, 0, None), 'cmd_fwd_b': ('anim', 0x53, 0, None),
    'cmd_df_c': ('anim', 0x4D, 0, None), 'cmd_df_d': ('anim', 0x57, 0, None),     # 3A, 3B (3C = atk_d_crouch)
    'hit_stand_light': ('anim', 0x22, 0, None), 'hit_stand_heavy': ('anim', 0x24, 0, None),
    'hit_air': ('anim', 0x32, 1, 2),
    # the knockdown ($32: hit off the feet, flying, the floor, lying) split the way fighter.c plays it
    'blowback': ('anim', 0x32, 0, 1), 'blowback_n': ('anim', 0x32, 0, 1), 'knockdown_flight': ('anim', 0x32, 2, 2),
    'knockdown_bounce': ('anim', 0x32, 3, 4), 'knockdown_fall': ('anim', 0x32, 4, 4), 'down': ('anim', 0x2B, 5, 5),
    'getup': ('anim', 0x1B, 0, None), 'trip': ('anim', 0x2C, 0, 2),
    # the round win (TODO #184): $37 (a hand to his brow), what Kizuna plays after a KO (tools/brawler/wins184.py; $80 was
    # not it); its voice $1CCA is sent 53 frames in (the 'win' capture, voices_kz)
    'win': ('anim', 0x37, 0, None),
}
ALIAS = {'hop_up_rise': 'jump_up_rise', 'hop_up_fall': 'jump_up_fall', 'hop_fwd_rise': 'jump_fwd_rise',
         'hop_fwd_fall': 'jump_fwd_fall', 'hop_back_rise': 'jump_back_rise', 'hop_back_fall': 'jump_back_fall',
         'atk_c_hop': 'atk_c_jump', 'atk_d_hop': 'atk_d_jump', 'atk_c_hop_diag': 'atk_c_jump_diag',
         'atk_d_hop_diag': 'atk_d_jump_diag', 'atk_cd_hop': 'atk_cd_jump'}
LOOP = {'idle', 'walk_fwd', 'run'}
# specials: input (Kizuna's command list, $604D0[5]) -> (whiff capture: P2 walked away, the hit capture, animations).
# 421A and 6246A need life <= 96 (cond $0400 / $4000: Kim's desperation moves), 236A is the tag-in strike (cond bit 6,
# forced in the capture)
SPECIALS = {'236C': ('sw_236C', 'cmd_236C_near', [0x97, 0x8E, 0x99]), '214B': ('sw_214B', 'cmd_214B_near', [0x93]),
            '[2]8C': ('sw_[2]8C', 'cmd_[2]8C_near', [0x9B, 0x9C, 0x9E]),
            '421A': ('sw_421A_low', 'cmd_421A_low_near', [0x100, 0x101]),
            '6246A': ('sw_6246A_low', 'cmd_6246A_low_near', [0x85, 0x86]),
            '236A': ('sw_236A', 'cmd_236A_near', [0x126])}

def encode_tile(pen):
    """16x16 pens -> 128 bytes of .neo C data (the inverse of kz.tile)"""
    out = bytearray(128)
    for half, x0 in ((1, 0), (0, 8)):                  # bytes 64-127: pixels 0-7, 0-63: pixels 8-15
        for r in range(16):
            for k, pl in enumerate((0, 2, 1, 3)):       # byte k of a row: plane 0, 2, 1, 3
                v = 0
                for b in range(8):
                    if pen[r, x0 + b] >> pl & 1: v |= 1 << b
                out[half * 64 + r * 4 + k] = v
    return bytes(out)

def attack(b):
    """an attack box: type >= $10 but $27 (a push box: idle, walks) and $33 (skipped by the hit test, $20A4A)"""
    return b[0] >= 0x10 and b[0] not in (0x27, 0x33)

def box_kof(b):
    """Kizuna box [type][b1][x left][x right][y bottom][y top] (x 4 px) -> KOF's [x, y, half w, half h], scaled"""
    l, r = sorted((b[2] * 4 * S, b[3] * 4 * S)); lo, hi = sorted((b[4] * 4 * S, b[5] * 4 * S))
    l, r, lo, hi = int(round(l)), int(round(r)), int(round(lo)), int(round(hi))
    r = min(r, 254); l = min(l, 254 - r) if l > 0 else max(l, -254)
    hi = min(hi, 254); lo = min(lo, 254 - hi)
    return [-(l + r) // 2, -(lo + hi) // 2, max(1, (r - l) // 2), max(1, (hi - lo) // 2)]

def kof_boxes(boxes):
    d = {}; na = nh = 0
    for b in boxes or []:
        if attack(b): na += 1; d[f'1{na:X}'] = box_kof(b)
        elif b[0] < 0x10: nh += 1; d[f'3{nh:X}'] = box_kof(b)
    return d

def boxes_in_force(n):
    """per ROM step of animation n: the boxes in force (a step's trailer bit 4 keeps the previous step's)"""
    out, cur = [], []
    for s in kz.parse_anim(CH << 12 | n):
        if s['boxes'] is not None: cur = s['boxes']
        elif not s['trailer'] & 0x10 and not s['nboxes']: cur = []
        out.append((s, cur))
    return out

STEP_BOXES = {}                                      # per character: step address -> boxes in force
def step_boxes(addr):
    if CH not in STEP_BOXES:
        sb_ = STEP_BOXES[CH] = {}
        for n in range(1 if CH == 5 else 0, kz.anim_count(CH)):
            try:
                for s, b in boxes_in_force(n): sb_[s['addr']] = b
            except Exception: pass
    return STEP_BOXES[CH].get(addr, [])

class Builder:
    def __init__(self):
        self.tiles, self.tile_map, self.frames, self.index = [], {}, [], {}
        self.pals = [16]                                # palette slots in the order met (index 0 = the body)
    def tile(self, pen):
        if not pen.any(): return 0
        b = encode_tile(pen)
        if b not in self.tile_map: self.tile_map[b] = TILE_BASE + len(self.tiles); self.tiles.append(b)
        return self.tile_map[b]
    def frame(self, addr):
        """the step at addr as brawler parts: drawn by Kizuna's renderer at zoom Z facing right, mirrored, re-tiled;
        addr a tuple: those steps drawn at one place, one frame (objects Kizuna draws together: the Phoenix's PHOELX
        halves, a step each, 508A + 508C and 508B + 508D at the same x / y)"""
        if addr in self.index: return self.index[addr]
        img = np.zeros((H, W), np.uint16)
        for a in (addr if isinstance(addr, tuple) else (addr,)): kz.render_step_zoom(img, a, X0, Y0, Z)
        img = img[:, ::-1]                              # mirrored: feet column X0 -> W - X0 (offset u -> -u - 1)
        fx = W - X0
        parts = []
        for pal in sorted({int(p) for p in np.unique(img >> 4) if p} | set()):
            m = (img >> 4) == pal
            if not (m & ((img & 15) > 0)).any(): continue
            ys, xs = np.nonzero(m)
            top, left = ys.min(), xs.min()
            ncol = (xs.max() - left) // 16 + 1; nrow = (ys.max() - top) // 16 + 1
            cols = []
            for c in range(ncol):
                col = []
                for r in range(nrow):
                    blk = img[top + 16 * r:top + 16 * r + 16, left + 16 * c:left + 16 * c + 16]
                    mk = m[top + 16 * r:top + 16 * r + 16, left + 16 * c:left + 16 * c + 16]
                    pen = np.where(mk, blk & 15, 0).astype(np.uint8)
                    pen = np.pad(pen, ((0, 16 - pen.shape[0]), (0, 16 - pen.shape[1])))
                    col.append(self.tile(pen))
                cols.append(col)
            if pal not in self.pals: self.pals.append(pal)
            run = []                                    # one part per run of non-empty columns
            for c in range(ncol + 1):
                if c < ncol and any(cols[c]): run.append(c); continue
                if run:
                    tc = [cols[k] for k in run]
                    while not any(t[-1] for t in tc): tc = [t[:-1] for t in tc]
                    lead = 0
                    while not any(t[0] for t in tc): tc = [t[1:] for t in tc]; lead += 1
                    parts.append({'dx': int(left + 16 * run[0] - fx), 'dy': int(top + 16 * lead - Y0), 'hflip': 0,
                                  'vflip': 0, 'pal': self.pals.index(pal), 'tiles': tc})
                    run = []
        self.index[addr] = len(self.frames)
        self.frames.append({'record': '+'.join(f'{a:06X}' for a in (addr if isinstance(addr, tuple) else (addr,))), 'parts': parts, 'weapon': None})
        return self.index[addr]

HOLD = 120
def step(B, addr, ticks, boxes, chain=False, dx=0):
    atk = any(attack(b) for b in boxes or [])
    return {'frame': B.frame(addr), 'ticks': max(0, min(ticks - 1, HOLD)), 'flags': (0x100 if atk else 0) | (0x4000 if atk and chain else 0),
            'dx': dx, 'boxes': kof_boxes(boxes), 'kz_step': addr}

def anim_steps(B, n, first, last, cap=None):
    st = boxes_in_force(n)[first:None if last is None else last + 1]
    travel = step_travel(cap, n) if cap else {}
    out = []
    for i, (s, bx) in enumerate(st):
        nxt = i + 1 < len(st) and any(attack(b) for b in st[i + 1][1]) and st[i + 1][1] == bx
        out.append(step(B, s['addr'], s['ticks'], bx, nxt, -sc(travel.get(s['addr'], 0))))
    return out

CAP_OF = {0x53: 'fwd_b', 0x5C: 'fwd_c', 0x49: 'fwd_a', 0x52: 'close_b'}   # walks / runs move by physics
def step_travel(cap, n):
    """forward px Kim moves during each step of animation n in its capture (velocity commands): per step address"""
    rec = CAP_OF.get(n)
    if not rec or rec not in cap: return {}
    fr = [f[0] for f in cap[rec]['frames']]
    out, prev = {}, None
    for i, p in enumerate(fr):
        if p[0] != n: continue
        if i + 1 < len(fr): out[p[5]] = out.get(p[5], 0) + (fr[i + 1][2] - p[2])
    return out

def cap_steps(B, cap, rec, anims, sel):
    fr = [f[0] for f in cap[rec]['frames'] if f[0][0] in anims]
    runs = []
    for p in fr:
        if runs and runs[-1][0] == p[5]: runs[-1][1] += 1; runs[-1][2].append(p[3])
        else: runs.append([p[5], 1, [p[3]]])
    ys = [y for r in runs for y in r[2]]; apex = ys.index(max(ys)); k = 0; out = []
    for addr, nfr, yl in runs:
        mid = k + len(yl) // 2; k += len(yl)
        if max(yl) <= 0 and k <= len(runs[0][2]): continue        # the prejump (on the floor)
        if (mid <= apex) != (sel == 'rise'): continue
        out.append(step(B, addr, nfr, step_boxes(addr)))
    return out

def physics(cap):
    def run(k, a): return [f[0] for f in cap[k]['frames'] if f[0][0] == a]
    w = run('walk_fwd', FK.kim_anim(CH, 0x1)); walk = (w[-1][2] - w[0][2]) / (len(w) - 1)
    wb = run('walk_back', FK.kim_anim(CH, 0x2)); back = abs(wb[-1][2] - wb[0][2]) / (len(wb) - 1)
    ju = [f[0] for f in cap['jump_up']['frames'] if f[0][0] in (FK.kim_anim(CH, 0x9), FK.kim_anim(CH, 0x81))]
    t0 = next(i for i, f in enumerate(ju) if f[3] > 0) - 1
    ys = [f[3] for f in ju[t0:]]
    n = ys.index(max(ys)); vy0 = 2 * max(ys) / n; g = vy0 / n
    fw = [f[0] for f in cap['jump_fwd']['frames'] if f[0][3] > 0]
    jdx = (fw[-1][2] - fw[0][2]) / (len(fw) - 1)
    return {'walk_fwd': walk * S, 'walk_back': back * S, 'jump_vy0': vy0 * S, 'gravity': g * S, 'jump_dx': jdx * S, 'prejump': t0 + 1}

def part_rows(fr, anims, hitcap):
    """a capture's frames a special (or a part of a multipart move) plays: (first, end, the frames kept as script rows:
    a connect capture's hit-stop frames removed)"""
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    e = next((i for i in range(s0, len(fr)) if fr[i][0][0] not in anims), len(fr))
    return s0, e, [i for i in range(s0, e) if not (hitcap and frozen(fr, i))]

def special_sounds(inp, cap, fc):
    """[(script row, sound word)]: the sounds Kizuna sent while special inp played, at the script row of the frame each
    was sent in (the rows special / multipart export; words as voices_kz.words_of reads them: prefix << 8 | code)"""
    import voices_kz
    parts = [(fc[r]['frames'], an, r.endswith('_h')) for r, an, _ in FOLLOW[inp]['parts']] if inp in FOLLOW else \
            [(cap[SPECIALS[inp][0]]['frames'], SPECIALS[inp][2], False)]
    out, base = [], 0
    for fr, anims, hitcap in parts:
        s0, e, rows = part_rows(fr, anims, hitcap)
        for f, w in voices_kz.words_of(fr):
            if s0 <= f < e: out.append((base + sum(1 for i in rows if i < f), w))
        base += len(rows)
    return out

def projectile_run(fr, s0):
    """[(capture frame, object row)] of the special's projectile: the first object of the fighter's own (its animation
    table, a task name) with a live attack box in a step, from the frame it appears while its slot stays alive"""
    lives = {}
    for i in range(s0, len(fr)):
        for o in fr[i][2]:
            if o[1] >> 12 == CH and not o[7].startswith('\0'): lives.setdefault(o[0], []).append((i, o))
    for slot, seen in sorted(lives.items(), key=lambda kv: kv[1][0][0]):
        if not any(attack(b) for i, o in seen for b in step_boxes(o[6])): continue
        run = [seen[0]]
        for i, o in seen[1:]:
            if i != run[-1][0] + 1: break                # the slot freed (a later object in it is another)
            run.append((i, o))
        return run
    return None

def projectile(B, fr, s0, x0, hf):
    """the special's projectile (export96.projectile_entry's layout; projectile_run): rows [frame, x from its spawn point
    (forward +), its height (px above the floor), its attack box [1, x, y, w, h] or None, None]; spawned at script row spawn_row, spawn_x / spawn_y
    from the script's origin; kind 1 (travelling: its hit ends it), hits = the near capture's life drops while one of its
    objects lived"""
    run = projectile_run(fr, s0)
    if not run: return None
    i0, o0 = run[0]; sx, sy = o0[3], o0[4]
    rows = []
    for i, o in run:
        ab = next((b for b in step_boxes(o[6]) if attack(b)), None)
        rows.append([B.frame(o[6]), sc(o[3] - sx), sc(o[4]), [1] + box_kof(ab) if ab else None, None])
    hits = sum(1 for j in range(1, len(hf)) if hf[j][1][6] < hf[j - 1][1][6] and any(q[1] >> 12 == CH and not q[7].startswith('\0') for q in hf[j][2]))
    return {'table': 0, 'state': o0[1] & 0xFFF, 'kind': 1, 'hit_kind': 1, 'spawn_row': i0 - s0, 'spawn_x': sc(sx - x0),
            'spawn_y': sc(sy), 'loop': None, 'death': None, 'life': len(rows), 'travel': max(abs(r[1]) for r in rows),
            'vx': rows[1][1] - rows[0][1] if len(rows) > 1 else 0, 'rows': rows, 'end': [], 'react': 'knockdown',
            'child': None, 'hits': {'near': {'hits': hits}}}

def effects(B, fr, rows, first, x0, skip=()):
    """Kim's own effect objects in a special's (or a part's) script rows (TODO #144, spawn.pinned_effect): every run of
    a task slot alive with an animation of his table and no attack box in its steps (those are projectile()'s), e.g.
    the Hienzan pillar '503 EFFE' ($509F, $5084: palette 27, blue) -> an effect entity of the special (export_bm
    played_projectiles; bproj_t follow 1 | 2 | 4: pinned to Kim, its rows run with his script rows, frozen with his
    hit-stop, ended when the special leaves them), spawned at the script row it first shows (first + k), each row its
    step drawn as a frame at its place from Kim's (forward / up px at zoom Z, the same rounding as the script's).
    Kizuna's pillar is Kim's: it stops with his hit-stop, moves with him and dies when his rising part 9B ends [meas]."""
    seen = {}
    for k, i in enumerate(rows):
        p = fr[i][0]
        for o in fr[i][2]:
            if o[1] >> 12 != CH or o[7].startswith('\0') or any(attack(b) for b in step_boxes(o[6])) or (i, o[0]) in skip: continue
            seen.setdefault(o[0], []).append((k, o, p))
    out = []
    for slot, ev in sorted(seen.items(), key=lambda kv: kv[1][0][0]):
        runs = [[ev[0]]]
        for e in ev[1:]:
            if e[0] == runs[-1][-1][0] + 1: runs[-1].append(e)
            else: runs.append([e])                       # the slot freed and taken again: another object
        for run in runs:
            rws = []
            for k, o, p in run:
                assert o[5] == p[4], (inp_of(fr), 'an effect facing away from Kim')
                rws.append([B.frame(o[6]), sc(o[3] - x0) - sc(p[2] - x0), sc(o[4]) - max(0, sc(p[3])), None, None])
            out.append({'effect': True, 'table': 0, 'state': run[0][1][1] & 0xFFF, 'kind': 0, 'hit_kind': 1, 'follow': 7,
                        'spawn_row': first + run[0][0], 'spawn_x': 0, 'spawn_y': 0, 'loop': None, 'death': None,
                        'life': len(rws), 'travel': 0, 'vx': 0, 'rows': rws, 'end': [], 'react': 'knockdown',
                        'child': None, 'hits': {}, 'name': run[0][1][7]})
    return out
def inp_of(fr): return f'P1 anim {fr[0][0][0]:X}'

def special(B, inp, cap):
    rec, hitrec, anims = SPECIALS[inp]; fr = cap[rec]['frames']
    s0, e, _ = part_rows(fr, anims, False)
    x0 = fr[s0][0][2]
    script, rboxes, rsteps = [], [], []
    for i in range(s0, e):
        p = fr[i][0]
        a, k, x, y, addr = p[0], p[1], p[2], p[3], p[5]
        bx = step_boxes(addr)
        script.append([B.frame(addr), sc(x - x0), sc(y), []])
        rboxes.append(kof_boxes(bx))
        live = any(attack(b) for b in bx)
        nb = step_boxes(fr[i + 1][0][5]) if i + 1 < e else []
        rsteps.append([a, k, (0x100 if live else 0) | (0x4000 if live and nb == bx else 0), 0xFF])
    hf = cap[hitrec]['frames']
    game_hits = sum(1 for j in range(1, len(hf)) if hf[j][1][6] < hf[j - 1][1][6])
    n = len(script)
    pj = projectile(B, fr, s0, x0, hf)
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': [''] * n, 'projectiles': ([pj] if pj else []) + effects(B, fr, range(s0, e), 0, x0), 'anims': anims,
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False], 'game_hits': game_hits}

# Multipart moves: the logic decoded from the 68000 code (substates_kz.py, README "Move sub-states"), cross-checked by
# brute force in our emulator (brute_kz.py), the frames from captures (followups_kz.py: whiff and connect, P2 free after
# the move starts). A follow-up command is accepted only inside the move's window (+$10C bit 3, opened by the handler):
#   236C  97 + 8E the 3-hit rush, then 99; 236C again while 8E plays (hit, whiff or block): 98 instead of 99 when 8E
#         ends; again while 98 plays: 9A; 98 / 9A end in 99. Nothing after 9A.
#   [2]8C 9B rising, then 9C 9E; once airborne a landed hit opens the window: 2C before 9B ends -> 9D, the dive (9E).
#   421A  100 the lunge; a hit that caught: at once 101 (the whiff ends after 100).
#   6246A 85 the rush; a hit that caught: at once 86 (rush hits, the launch, the flight in the Phoenix flames $508C /
#         $508D), 88 the dive among flame feathers $5068 / $506B (random places in Kizuna: the captured ones), 89.
#         'backdrop': from the launch (86's step event at the hit, $3AC5C) to 88 Kizuna hides the stage and its backdrop
#         ($401FFE, routine $1FC46) alternates $27E6 / $27E4 = $7DFF / $4700 every frame ($27E1 = $80: bit 0 of the
#         counter picks; cleared as 88 starts, $3ACDE); measured in our emulator: white first, 87 frames.
# A part = (capture, Kim's animations in it); links (export_bm.special_parts): 'again' = the A+B input that started the
# move; down+C -> down+A (A is the brawler's attack button). Connect parts (hit captures): Kizuna's hit-stop frames
# removed (Kim and the victim both still: the brawler freezes on its own hits), the victim held where Kizuna had it
# (carry: the desperation moves drive their victim by script, +$1AF phases) until the part ends.
FOLLOW = {
    '236C': {'parts': [('236C_w', (0x97, 0x8E), 1), ('236C_w', (0x99,), None), ('236C2_w', (0x98,), 1), ('236C3_w', (0x9A,), 1)],
             'links': [(0, 2, 'input', 'again', 0x8E, 'end'), (2, 3, 'input', 'again', 0x98, 'end')]},
    '[2]8C': {'parts': [('28C_w', (0x9B,), 1), ('28C_w', (0x9C, 0x9E), None), ('28C2_h', (0x9D, 0x9E), None)],
              'links': [(0, 2, 'hit+input', 'dA', (0x9B, 2), 'end')]},
    '421A': {'parts': [('421A_w', (0x100,), None), ('421A_h', (0x101,), None)],
             'links': [(0, 1, 'hit', None, 0x100, 'now')], 'carry': 1},
    '6246A': {'parts': [('6246A_w', (0x85,), None), ('6246A_h', (0x86, 0x88, 0x89), None)],
              'links': [(0, 1, 'hit', None, 0x85, 'now')], 'carry': 1, 'objects': 1, 'damage': '6246A_h',
              'backdrop': {'part': 1, 'to': 0x88, 'colours': (0x7DFF, 0x4700)}},
}
FOLLOWUPS = '/data/neogeo_dict/kizuna/kim_followups.json'
LIFE_KZ, LIFE_BRAWLER = 192, 60                        # full life: Kizuna (+$113), the brawler (fighter.c f->hp)
def game_damage(F, fc):
    """{'damage': the move's damage as Kizuna dealt it (its hit capture's life drop: a desperation move takes it at once),
    in the brawler's life} for a FOLLOW entry with 'damage' (export_bm special_rows splits it over the hits), else {}"""
    if not F.get('damage'): return {}
    fr = fc[F['damage']]['frames']
    return {'damage': int(round((fr[0][1][6] - min(f[1][6] for f in fr)) * LIFE_BRAWLER / LIFE_KZ))}
R_HEAVY, R_KNOCKDOWN, R_LAUNCH = 1, 2, 3               # fighter.h R_*
def react_of(a):
    """the victim's Kizuna animation -> the brawler's reaction: hit off the feet / launched / knocked down, else a reel"""
    return R_LAUNCH if a in (0x32, 0x33, 0x9B) else R_KNOCKDOWN if a in (0x2B, 0x2C) else R_HEAVY

def frozen(fr, i):
    """a hit-stop frame: Kim still (step, place, tick count) while the victim is still or just hit"""
    if i == 0: return False
    p, q, p0, q0 = fr[i][0], fr[i][1], fr[i - 1][0], fr[i - 1][1]
    still = [p[k] for k in (0, 1, 2, 3, 10)] == [p0[k] for k in (0, 1, 2, 3, 10)]
    vstill = [q[k] for k in (0, 1, 10)] == [q0[k] for k in (0, 1, 10)] or (q[1] == 0 and q[10] == 0 and q[0] != q0[0])
    return still and vstill

def hit_reactions(fc):
    """(Kim's anim, step) -> the reaction of the victim it hit, from every hit capture (a new reaction animation or its
    step 0 again starts on a hit; Kim's step on the frame before is the impact)"""
    out = {}
    for k, v in fc.items():
        if not k.endswith('_h'): continue
        fr = v['frames']
        for j in range(1, len(fr)):
            q, q0 = fr[j][1], fr[j - 1][1]
            if q[0] != q0[0] or (q[1] == 0 and q0[1] != 0 and q[10] == 0 and q0[0] == q[0]):
                if q[0] in (0, 0x1B, 0x1D, 0x01, 0x02): continue      # standing / getting up / walking: no hit
                p = fr[j - 1][0]; out.setdefault((p[0], p[1]), react_of(q[0]))
    return out

def multipart(B, inp, fc):
    """a multipart move as one script of parts (export_bm.special_parts): rows, boxes, steps, victim places, objects"""
    F = FOLLOW[inp]; react = hit_reactions(fc)
    script, rboxes, rsteps, carry, rsrc, parts, links, spans = [], [], [], [], [], [], [], []
    chained = {}                                         # rows whose box became a held victim's: their same-hit flag
    marks, grows, backdrop, effs = [], [], None, []
    for pi, (rec, anims, nxt) in enumerate(F['parts']):
        fr = fc[rec]['frames']
        hitcap = rec.endswith('_h')
        s0, e, rows = part_rows(fr, anims, hitcap)
        x0 = fr[s0][0][2] if pi == 0 else fr[s0 - 1][0][2]   # part 0: from its start; a follow-up: from where Kim is
        first = len(script); spans.append([])
        drawn = set()                                    # (6246A: its flames' first two places are script objects,
        for i in rows:
            p, q = fr[i][0], fr[i][1]
            bx = step_boxes(p[5])
            objs = []
            if F.get('objects'):                         # Kim's own objects (the flames), alive; the ones at one place
                grp = {}                                 # (x, y, flip) are one frame; the first two places by task slot
                for o in sorted(fr[i][2]):
                    if o[1] >> 12 == CH and not o[7].startswith('\0'): grp.setdefault((o[3], o[4], o[5]), []).append(o[6])
                for (ox, oy, of), st in list(grp.items())[:2]:
                    drawn |= {(i, o[0]) for o in fr[i][2] if (o[3], o[4], o[5]) == (ox, oy, of)}
                    objs.append([B.frame(tuple(sorted(st)) if len(st) > 1 else st[0]), sc(ox - x0), sc(oy), 1 if of == p[4] else 0])
            script.append([B.frame(p[5]), sc(p[2] - x0), sc(p[3]), objs])
            rboxes.append(kof_boxes(bx))
            spans[-1].append((p[0], p[1]))
            rsrc.append(react.get((p[0], p[1])))
            carry.append((max(-32000, min(32000, sc(q[2] - p[2]))), max(0, min(255, sc(q[3])))) if F.get('carry') == pi and hitcap else None)
        effs += effects(B, fr, rows, first, x0, drawn)  # the others (the third PHOELX W feather on) pinned effects)
        for j in range(first, len(script)):
            nb = rboxes[j + 1] if j + 1 < len(script) else {}
            live = any(k_[0] == '1' for k_ in rboxes[j])
            rsteps.append([spans[-1][j - first][0], spans[-1][j - first][1], (0x100 if live else 0) | (0x4000 if live and nb == rboxes[j] else 0), 0xFF])
        marks += [''] * (len(script) - first)
        if hitcap:                                       # the connect part hits where Kizuna's victim was hit: the row
            grows += range(first, len(script))           # before each new reaction (export_bm special_rows 'h')
            for j in range(s0 + 1, e):
                q, q0 = fr[j][1], fr[j - 1][1]
                if q[0] != q0[0] and q[0] not in (0, 0x1B, 0x1D, 1, 2) or (q[0] == q0[0] and q[1] == 0 and q0[1] != 0 and q[10] == 0):
                    k = max((t for t, i in enumerate(rows) if i < j), default=None)
                    if k is None: continue
                    marks[first + k] += 'h'
                    cv = carry[first + k]
                    if cv:                               # the held victim was hit here: the row's box covers it
                        t = first + k                    # (the Phoenix's foot-up kicks at 86 steps 55 / 58: the
                        vb = [max(-120, min(120, -cv[0])), max(-120, min(120, -(cv[1] - script[t][2] + 40))), 24, 48]   # victim 90-200 px above Kim's box)
                        ab = next((v for k_, v in sorted(rboxes[t].items()) if k_[0] == '1'), None)
                        if ab:                           # Kim's box there: its union with the victim's, the row's
                            l = min(ab[0] - ab[2], vb[0] - vb[2]); r_ = max(ab[0] + ab[2], vb[0] + vb[2])   # same-hit
                            b_ = min(ab[1] - ab[3], vb[1] - vb[3]); t_ = max(ab[1] + ab[3], vb[1] + vb[3])   # flag kept
                            vb = [(l + r_) // 2, max(-120, (b_ + t_) // 2), min(120, (r_ - l + 1) // 2), min(120, (t_ - b_ + 1) // 2)]
                            chained[t] = rsteps[t][2] & 0x4000
                            if t > first: chained[t - 1] = rsteps[t - 1][2] & 0x4000
                            rboxes[t] = {**{k_: v for k_, v in rboxes[t].items() if k_[0] != '1'}, '1F': vb}
                        else:                            # an object's hit (101's last: the RUSH object): a box
                            for t in (first + k, first + k + 1):     # on the held victim, 2 rows
                                if t < len(script): rboxes[t] = dict(rboxes[t], **{'1F': vb if t == first + k else
                                    [vb[0], max(-120, min(120, -(cv[1] - script[t][2] + 40))), 24, 48]})
            if F.get('carry') == pi:                     # a carried part hits only where Kizuna's did (its victim is
                j = first                                # held by script): a run of attack rows without a game hit
                while j < len(script):                   # loses its box (6246A's 86 steps 61 / 64: no hit there)
                    if not any(k_[0] == '1' for k_ in rboxes[j]): j += 1; continue
                    e_ = j
                    while e_ < len(script) and any(k_[0] == '1' for k_ in rboxes[e_]): e_ += 1
                    if not any('h' in marks[t] for t in range(j, e_)):
                        for t in range(j, e_): rboxes[t] = {k_: v for k_, v in rboxes[t].items() if k_[0] != '1'}
                    j = e_
        for j in range(first, len(script)):
            nb = rboxes[j + 1] if j + 1 < len(script) else {}
            live = any(k_[0] == '1' for k_ in rboxes[j])
            rsteps[j][2] = (0x100 if live else 0) | (0x4000 if live and (nb == rboxes[j] or chained.get(j)) else 0)
        bd = F.get('backdrop')
        if bd and bd['part'] == pi:                      # the screen effect: from the hit that launches (its life drop:
            drop = next(j for j in range(s0 + 1, e) if fr[j][1][6] < fr[j - 1][1][6])   # the same step event) to
            to = next(j for j in range(s0, e) if fr[j][0][0] == bd['to'])              # the part's anim bd['to']
            sel = [first + k for k, i in enumerate(rows) if drop <= i < to]
            backdrop = {'rows': [sel[0], sel[-1] + 1], 'colours': list(bd['colours'])}
        parts.append({'first': first, 'end': len(script), 'next': nxt})
    for a, b, on, key, win, at in F['links']:
        an, st0 = win if isinstance(win, tuple) else (win, 0)
        rows = [parts[a]['first'] + k for k, (n, s) in enumerate(spans[a]) if n == an and s >= st0]
        links.append({'from': a, 'to': b, 'on': on, 'input': key, 'window': [rows[0], rows[-1] + 1], 'at': at})
    n = len(script)
    p0 = script[:parts[0]['end']]
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': marks, 'game_rows': grows, 'projectiles': effs, 'anims': [a for _, an, _ in F['parts'] for a in an],
            'shape': [max(r[1] for r in p0), max(r[2] for r in p0), False], 'game_hits': sum(1 for r in rsrc if r), **game_damage(F, fc),
            'parts': parts, 'links': links, 'carry_src': carry, 'react_src': rsrc, **({'backdrop': backdrop} if backdrop else {})}

# ---- the air special (TODO #200, vocabulary `air special`: game.json roster[].air_special, down+A in a jump) --------
# Kim's j.2B is a special of Kizuna's (command $26, group 2, handler $3A79E), not an air normal: read from the 68000 code
# [code] and measured in our emulator [meas] (followups_kz.py j2B_w / j2B_apex_w / j2B_up_w whiff, j2B_h / j2B2_h hit):
#   $3A79E: state $19D (anim 8F); 8F step 0's command 9 sets the velocity (6, -6) px / frame = a 45-degree dive
#     forward and down from wherever the jump is (rising or falling, vertical jump too), no gravity, the jump's own
#     speed dropped [meas: x +6 / y -6 every frame from 8F's first frame to the floor]. Step 1 (ticks 0) waits with the
#     staff's attack box live; a hit (trailer bit 15 = a new hit) moves the animation on: steps 2-21, the blue effect
#     (part 2) at his feet and a new hit every 4 steps (6, 10, 14, 18) while he keeps diving [meas: 4 hits, 22 = a reel].
#     The whiff shows no effect: step 1 until the floor.
#   $3A7C2 each frame: a hit landed (+$106 bit 0) -> the follow-up window opens (+$10C bit 3), earlier presses dropped;
#     the floor ($29432) -> $3A84A. $3A802 (after the hit): the floor -> $3A84A; 64 px up or more and 2B accepted again
#     -> state $1A0 (anim 92: the second dive kick, velocity (6, -6) again, one hit that knocks down: 2C) -> $3A84A.
#   $3A84A: on the floor: state $19F (anim 91, the landing, 14 frames) then neutral ($377E4) [meas: 8F shown 2 frames on
#     the floor first].
# Played by a program (export_bm rom 'prims', fighter.c prog_update), no recorded rows: the anims are ROM steps, the
# motion the velocity (scaled by S), the hits the steps' boxes; 2B again = down+A again (A is the attack button).
AIR = {'j.2B': {'dive': 0x8F, 'land': 0x91, 'again': 0x92, 'again_from': 64, 'vel': (6.0, -6.0),
                'whiff': 'j2B_w', 'hit': 'j2B_h', 'hit2': 'j2B2_h'}}
P = {'anim': 1, 'set': 2, 'move': 4, 'fall': 6, 'br': 9, 'resume': 10, 'resume_at': 11, 'end': 15, 'check': 17, 'part': 18,
     'hitclr': 22}   # bm_chars.h P_*
PC = {'end': 0, 'land': 2, 'hit': 5, 'always': 7, 'link': 10, 'hitany': 11, 'low': 16}                                    # PC_*
REG = {'vx': 0, 'vy': 1, 'g': 2}
SPECIAL_DAMAGE = 8                                   # export_bm.SPECIAL_DAMAGE

def rom_steps(B, n, first, last, new_hit=True):
    """ROM steps first..last of Kim's animation n as a program's steps (export_bm rom_c: flags $100 attack box live,
    $4000 the next step goes on with this hit): a step opens a new hit where Kizuna's does (its trailer bit 15) or where
    a live box follows a dead one; new_hit False: the first steps continue a hit already landed (no box until the next
    opening: the brawler's program starts a new animation there)"""
    st = boxes_in_force(n)[first:last + 1]
    live = [any(attack(b) for b in bx) for _, bx in st]
    if not new_hit:
        k = next((i for i, (s, _) in enumerate(st) if s['trailer'] & 0x8000), len(st))
        live[:k] = [False] * k
    out = []
    for i, (s, bx) in enumerate(st):
        nxt = st[i + 1][0] if i + 1 < len(st) else None
        cont = i + 1 < len(st) and live[i] and live[i + 1] and not nxt['trailer'] & 0x8000 and \
            not (nxt['nboxes'] and not nxt['trailer'] & 0x10)   # (TODO #136: a step with its own attack box list hits
                                                                 # anew: the Phoenix's 86.43 -> 86.44, 32 then 9B [meas:
                                                                 # 6246A_h]; the only such pair in Kim's programs)
        d = step(B, s['addr'], s['ticks'] + (i == 0), bx if live[i] else [b for b in bx if not attack(b)])   # (the
        d['flags'] = (0x100 if live[i] else 0) | (0x4000 if cont else 0)   # program's P_ANIM frame counts one of
                                                                             # its first step's: Kizuna shows it ticks)
        at = [v for k, v in d['boxes'].items() if k[0] == '1']
        if len(at) > 1:                                  # (TODO #136) several attack boxes: Kizuna tests each ($209C6),
            l = min(b[0] - b[2] for b in at); r = max(b[0] + b[2] for b in at)   # the brawler's step has one: their
            t = min(b[1] - b[3] for b in at); bt = max(b[1] + b[3] for b in at)  # union [meas: the Phoenix's 86.55,
            d['boxes'] = {**{k: v for k, v in d['boxes'].items() if k[0] != '1'},   # 37 / 48: 48 reaches its victim]
                          '11': [(l + r) // 2, (t + bt) // 2, (r - l + 1) // 2, (bt - t + 1) // 2]}
        out.append(d)
    return out

def air_special(B, inp, fc):
    """the air special inp (AIR) as a special read from the ROM: its anims, its program, the follow-up link, the Brawler
    Lab's script (the whiff as the program plays it)"""
    A = AIR[inp]
    last = lambda n: len(kz.parse_anim(CH << 12 | n)) - 1
    hits = [i for i, s in enumerate(kz.parse_anim(CH << 12 | A['dive'])) if s['trailer'] & 0x8000]
    again = kz.parse_anim(CH << 12 | A['again'])
    a_hit = next(i for i, s in enumerate(again) if s['trailer'] & 0x8000)
    anims = {'dive': {'mode': 'hold', 'steps': rom_steps(B, A['dive'], 0, hits[0])},
             'dive_hit': {'mode': 'hold', 'steps': rom_steps(B, A['dive'], hits[0] + 1, last(A['dive']), new_hit=False)},
             'again': {'mode': 'hold', 'steps': rom_steps(B, A['again'], 0, a_hit)},
             'land': {'mode': 'hold', 'steps': rom_steps(B, A['land'], 0, last(A['land']))}}
    states = list(anims)
    # damage: SPECIAL_DAMAGE over the dive's hits as Kizuna dealt them (j2B_h: 4 hits), the second kick by Kizuna's ratio
    def drops(rec):
        fr = fc[rec]['frames']; return [fr[j - 1][1][6] - fr[j][1][6] for j in range(1, len(fr)) if fr[j][1][6] < fr[j - 1][1][6]]
    d1, d2 = drops(A['hit']), drops(A['hit2'])
    each = max(1, round(SPECIAL_DAMAGE / len(d1)))
    dmg2 = max(1, round(d2[-1] * SPECIAL_DAMAGE / sum(d1)))
    def first_react(rec, anim):                      # the victim's reaction to the first hit of anim
        fr = fc[rec]['frames']
        j = next(j for j in range(1, len(fr)) if fr[j][1][6] < fr[j - 1][1][6] and fr[j - 1][0][0] == anim)
        return react_of(fr[j][1][0])
    r1, r2 = first_react(A['hit'], A['dive']), first_react(A['hit2'], A['again'])
    vx, vy = (round(v * S * 65536) for v in A['vel'])
    low = sc(A['again_from'])
    L = {}
    # frame order as Kizuna's [meas]: the dive moves from its first frame; the frame after a hit's hit-stop shows step 2
    # in place (the handler's hit path, then on); the second kick and the landing start the frame after their test
    ops = [('set', REG['g'], 0), ('set', REG['vx'], vx), ('set', REG['vy'], vy),
           ('anim', 0, each | r1 << 8), ('resume',),
           ('br', PC['hit'], 'HIT'), ('move',), ('fall',), ('br', PC['land'], 'LAND0'), ('br', PC['always'], None),
           'HIT', ('anim', 1, each | r1 << 8), ('part',), ('check', 1), ('hitclr',),  # the window opens: the presses of
           ('resume_at', 'DIVE'), ('br', PC['always'], None),                       # its hit-stop count, earlier ones not
           'DIVE', ('check', 1), ('br', PC['hitany'], 'STILL'),                     # (each later hit's hit-stop: then a
           ('move',), ('fall',), ('br', PC['land'], 'LAND0'),                        # frame in place, as the first's)
           ('br', PC['low'], None, low), ('br', PC['link'], 'AGAIN', 1), ('br', PC['always'], None),
           'STILL', ('hitclr',), ('br', PC['low'], None, low), ('br', PC['link'], 'AGAIN', 1), ('br', PC['always'], None),
           'AGAIN', ('anim', 2, dmg2 | r2 << 8), ('set', REG['vx'], vx), ('set', REG['vy'], vy),
           ('resume_at', 'KICK'), ('br', PC['always'], None),
           'KICK', ('move',), ('fall',), ('br', PC['land'], 'LAND0'), ('br', PC['always'], None),
           'LAND0', ('resume_at', 'LAND0B'), ('br', PC['always'], None),            # [meas] 8F 2 frames on the floor
           'LAND0B', ('resume_at', 'LAND1'), ('br', PC['always'], None),
           'LAND1', ('anim', 3, 0), ('resume',), ('br', PC['end'], 'END'), ('br', PC['always'], None),
           'END', ('end',)]
    k = 0
    for o in ops:
        if isinstance(o, str): L[o] = k
        else: k += 1
    prims = []
    for o in ops:
        if isinstance(o, str): continue
        c = o[0]
        if c == 'set': prims.append([P['set'], o[1], 0, o[2]])
        elif c == 'anim': prims.append([P['anim'], o[1], o[2], None])      # (hit effect: export_bm move_fx)
        elif c == 'check': prims.append([P['check'], o[1], 0, 0])
        elif c == 'br': prims.append([P['br'], o[1] | 0x80, -1 if o[2] is None else L[o[2]], o[3] if len(o) > 3 else 0])
        elif c == 'resume_at': prims.append([P['resume_at'], 0, L[o[1]], 0])
        else: prims.append([P[c], 0, 0, 0])
    # the Lab's script: the whiff as Kizuna plays it from the dive's first frame (rows = frames)
    fr = fc[A['whiff']]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == A['dive'])
    e = next(i for i in range(s0, len(fr)) if fr[i][0][0] not in (A['dive'], A['land']))
    x0 = fr[s0 - 1][0][2]
    script, rb, rs = [], [], []
    for i in range(s0, e):
        p = fr[i][0]; bx = step_boxes(p[5])
        script.append([B.frame(p[5]), sc(p[2] - x0), sc(p[3]), []]); rb.append(kof_boxes(bx))
        rs.append([p[0], p[1], 0x100 if any(attack(b) for b in bx) else 0, 0xFF])
    rom = {'states': states, 'anims': anims, 'prims': prims, 'objects': [], 'openings': {}, 'hit_kind': 1,
           'last_hit': -1, 'apex': -1, 'length': len(script), 'voice_frames': True, 'now': True, 'sharepush': True,
           'parts': [{'states': ['dive', 'dive_hit']}, {'states': ['again']}],
           'follow_links': [{'from': 0, 'to': 1, 'input': 'dA'}], 'links': ['dA']}
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'air': True, 'script': script, 'row_boxes': rb,
            'row_steps': rs, 'marks': [''] * len(script), 'projectiles': [], 'anims': [A['dive'], A['land'], A['again']],
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False], 'game_hits': len(d1), 'rom': rom}

def air_sounds(inp, fc):
    """[(frame of the program, sound word)]: what Kizuna sent while the air special's whiff played (from its first frame)"""
    import voices_kz
    A = AIR[inp]; fr = fc[A['whiff']]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == A['dive'])
    e = next(i for i in range(s0, len(fr)) if fr[i][0][0] not in (A['dive'], A['land']))
    return [(f - s0, w) for f, w in voices_kz.words_of(fr) if s0 <= f < e]

# ---- the ground specials as programs (TODO #133-#138: no recorded rows; Kizuna's handlers read from the 68000 code) --
# A Kizuna special = its handler's sub-states (substates_kz.py) + the animations they set; an animation's steps carry
# their own motion (kz.CMD_NAMES, the step loader $139EA -> handlers $14082[cmd]) [code], and the measured order of a
# frame [meas, our emulator, kim_capture.json / kim_followups.json]: the handler's tests (on the state of the frame
# before), then the animation's clock (a step entered runs its command: 1 stop = every velocity and acceleration 0,
# 5 / 6 stop + move [dx w][dy w] px, 9 [vx w][vy w], 10 [vx][ax][vy], 11 [vx][vy][ay], 12 [vx][ax][vy][ay], 13 [ax],
# 14 [ay], 15 [ax][ay]; velocities 1/256 px a frame, accelerations 1/4096 px a frame^2: 214B's ax $FF00 = -1/16 [meas:
# 106 px over its 11 moving frames], [2]8C's fall ay $F000 = -1 [meas: 3 3 5 5 7 7 ...]), then the move: x += vx + ax / 2,
# vx += ax (the same for y: 9C falls 2.5, 3.5, 4.5 ...). A step shows max(1, ticks) frames.
# The brawler plays it as a program (export_bm 'prims', fighter.c prog_update): each animation a block that runs its
# frames by a counter from its P_ANIM (KzProg.block: the steps' frame offsets are static, the hit-stop freezes the
# program and the animation alike), its steps' commands as register writes on their first frame (vx / vy hold
# v + a / 2, g = -ay: P_MOVE then P_ADD ax, P_FALL), the handler's tests as branches at the frame's start.
P = {**P, 'mul': 3, 'nudge': 7, 'dec': 8, 'jmp': 12, 'spawn': 13, 'adv': 16, 'evclr': 19, 'hitoff': 26, 'add': 27,
     'vphase': 32, 'screen': 33}                     # bm_chars.h P_* (more of them)
PC = {**PC, 'cnt': 4, 'event': 1, 'cntle': 19, 'thigh': 22}
VA = {'snap': 1, 'freeze': 2, 'thaw': 4, 'mirror': 8, 'unmirror': 16}   # bm_chars.h VA_* (P_VPHASE)
REG.update(h=5, cnt=4)

def step_motion(s):
    """a ROM step's command as motion [code]: {vx, vy (px / frame), ax, ay (px / frame^2), nudge (dx, dy px)}, the
    registers it writes only"""
    c, a = s['cmd'], s['args']
    w = lambda i: kz.sw(int.from_bytes(a[2 * i:2 * i + 2], 'big'))
    m = {}
    if c in (1, 3, 4, 5, 6, 7, 8): m.update(vx=0.0, vy=0.0, ax=0.0, ay=0.0)
    if c in (5, 6): m['nudge'] = (w(0), w(1))
    if c in (7, 8): m['nudge'] = (kz.sb(a[0]), kz.sb(a[1]))
    if c == 9: m.update(vx=w(0) / 256, vy=w(1) / 256)
    if c == 10: m.update(vx=w(0) / 256, ax=w(1) / 4096, vy=w(2) / 256)
    if c == 11: m.update(vx=w(0) / 256, vy=w(1) / 256, ay=w(2) / 4096)
    if c == 12: m.update(vx=w(0) / 256, ax=w(1) / 4096, vy=w(2) / 256, ay=w(3) / 4096)
    if c == 13: m['ax'] = w(0) / 4096
    if c == 14: m['ay'] = w(0) / 4096
    if c == 15: m.update(ax=w(0) / 4096, ay=w(1) / 4096)
    return m

def fx16(v): return int(round(v * 65536))
MERGE = {'ax': 0.0, 'ay': 0.0, 'y': 0.0, 'vx': None, 'vy': None}   # a block entered from several paths: velocities written

# ---- Kizuna's hit reactions (TODO #136, vocabulary reaction.source_motion), read from the 68000 code [code] and
# checked against the captures [meas: kim136_proof.py]:
#   the hit ($2D4F2): the victim's +$132 = the type byte of the attack box that hit ($2E740: the collision's +$7E);
#   request $0400 | byte[$5FBEE + 4 (type - 16) + situation] (situation 0 standing, 1 crouching (+$10F bit 6), 2 in the
#   air (+$10F bit 7), 3 in the air with its life copy +$190 < 0) -> +$20; the victim's group-4 handler for it
#   (long[long[long[$5FCE2 + 8 char] + 16] + 4 request]) sets one state (`movew #state,%d0`, $293E6 / $293DC):
#   its reaction animation (word[long[$69118 + 4 char] + 2 state]); that animation's step commands move the body
#   (the physics $2B644: x += vx, y += vy, v += a each frame; vx < 0 = backward, away from the attacker): a reel slides
#   (cmd 10: vx, ax) while it plays, a flight (cmd 11: vx, vy, ay) to a 0-tick step that waits for the floor, a stop
#   (cmd 3) whose ticks are the landing's pause, then a 0-tick bounce (cmd 11) and the lying step.
#   Timing [meas: 214B_h, 28C_h, 421A_h, 6246A_h]: the victim stands still through the hit-stop and the first frame after
#   it, then moves; on the floor it pauses the stop's ticks - 1 frames and the bounce moves on the next one.
#   The reaction animations are the victim's own, their motions the same for every Kizuna fighter (Gozu's / Mezu's
#   launches differ by 1 px a frame): the brawler takes Hayate's (char 0, the captures' victim) for every victim.
SR_VICTIM = 0
SR_TABLE, SR_GROUP = 0x5FBEE, 4

def sr_anim(btype, air):
    """the reaction animation an attack box of type btype gives a standing / airborne victim (Hayate) [code]"""
    idx = kz.u8(SR_TABLE + (btype - 16) * 4 + (2 if air else 0))
    T = kz.u32(kz.u32(0x5FCE2 + 8 * SR_VICTIM) + 4 * SR_GROUP)
    h = kz.u32(T + 4 * idx) & 0xFFFFFF
    for a in range(h, h + 0x40, 2):                      # the handler: jsr, jsr, bset ..., movew #state,%d0, jsr $293E6
        if kz.u16(a) == 0x303C and kz.u16(a + 4) == 0x4EB9 and kz.u32(a + 6) in (0x293E6, 0x293DC):
            st = kz.u16(a + 2)
            return kz.u16(kz.u32(0x69118 + 4 * SR_VICTIM) + 2 * st) & 0xFFF
    raise ValueError(f'reaction handler ${h:X} (type {btype}): no state')

def sr_motion(n):
    """reaction animation n (Hayate's) as a source reaction: {anim, r (the brawler's posture R_*, | 8 hittable in its
    flight), vx, ax (away from the
    attacker, px / frame, the KzProg convention: vx holds v + a / 2), vy, ay (up), n (frames a reel slides), land (the
    landing's pause frames; -1: none, the brawler's own landing), bvx, bvy, bay (the bounce)} in Kizuna px"""
    st = kz.parse_anim(SR_VICTIM << 12 | n)
    k = next((i for i, s in enumerate(st) if step_motion(s).get('vx') or step_motion(s).get('vy')), None)
    out = {'anim': n, 'vx': 0.0, 'ax': 0.0, 'vy': 0.0, 'ay': 0.0, 'n': 0, 'land': -1, 'bvx': 0.0, 'bvy': 0.0, 'bay': 0.0}
    if k is None: out['r'] = R_HEAVY; return out
    m = step_motion(st[k])
    out.update(vx=-(m['vx'] + m.get('ax', 0.0) / 2), ax=-m.get('ax', 0.0), vy=m.get('vy', 0.0) + m.get('ay', 0.0) / 2, ay=m.get('ay', 0.0))
    if not out['vy']:                                    # a reel: it slides while its animation plays
        out['r'] = R_HEAVY; out['n'] = sum(max(1, s['ticks']) for s in st[k:]); return out
    out['r'] = react_of(n) if n in (0x32, 0x33, 0x9B, 0x2B, 0x2C) else R_KNOCKDOWN
    w = next((i for i in range(k + 1, len(st)) if st[i]['ticks'] == 0 and not step_motion(st[i])), None)   # the wait for the floor
    cur, live = [], []                                   # hittable in its flight (R_* | 8): its steps there carry boxes
    for s_ in st:                                        # (Kizuna's juggle rule: 32 / 33 / 9B / the air hits do,
        if s_['boxes'] is not None: cur = s_['boxes']    # 2B / 2C / 8A-8C / 9E none) [code: the box test $209C6]
        elif not s_['trailer'] & 0x10 and not s_['nboxes']: cur = []
        live.append(bool(cur))
    if any(live[k:(w if w is not None else len(st)) + 1]): out['r'] |= 8
    if w is not None and w + 2 < len(st) and st[w + 1]['cmd'] in (1, 3) and st[w + 2]['cmd'] == 11:
        b = step_motion(st[w + 2])
        out.update(land=max(0, st[w + 1]['ticks'] - 1), bvx=-b['vx'], bvy=b['vy'] + b['ay'] / 2, bay=b['ay'])
    return out

SREACT = []                                              # the source reactions met, in order (export: 'sreacts')
def sr_index(btype, air):
    """the index (1-based) of the reaction an attack box type gives (standing / airborne) in SREACT"""
    m = sr_motion(sr_anim(btype, air))
    if m not in SREACT: SREACT.append(m)
    return SREACT.index(m) + 1

def sr_pair(boxes):
    """a step's attack box -> the packed source reactions standing | airborne << 4 (fighter.c: bstep_t.hy under
    SF_SREACT); the first attack box in force (Kizuna's two-box steps: [2]8C's 9B.6 types 49 / 41 hit as 49 -> 32,
    the Phoenix's 86.55 37 / 48 both 33 [meas: 46 of 48 measured hits as decoded with the last box, 48 with the first])"""
    at = [b for b in boxes or [] if attack(b)]
    if not at: return 0
    t = at[0][0]
    return sr_index(t, False) | sr_index(t, True) << 4

class KzProg:
    """one special's program: its animations (rom_steps, each step's reaction and voices), its objects (effects) and
    its ops, written as blocks (one per animation the handler sets) joined by labels"""
    def __init__(self, B, react, voices):
        self.B, self.react, self.voices = B, react, voices
        self.anims, self.states, self.ops, self.objects = {}, [], [], []
        self.entry = {}                                  # block label -> its first frame (static entries only)
        self.labels = 0

    def anim(self, key, n):
        if key not in self.anims:
            last = len(kz.parse_anim(CH << 12 | n)) - 1
            steps = rom_steps(self.B, n, 0, last)
            bif = boxes_in_force(n)
            for k, s in enumerate(steps):                # the victim's reaction to a hit window (TODO #136): Kizuna's
                if s['flags'] & 0x100 and (k == 0 or not steps[k - 1]['flags'] & 0x4000):   # reaction code for the
                    s['react'] = sr_pair(bif[k][1])      # box that opens it (sr_pair: SF_SREACT, its own slide / flight)
                if any(b[0] == 5 for b in bif[k][1]): s['push'] = 1   # its push box (type 5, the body box Kizuna's
                                                         # push reads [meas: kim136]; bstep_t flag 4 under SF_SREACT)
                vs = self.voices.get((n, k))
                if vs: s['voices'] = vs
            if kz.parse_anim(CH << 12 | n)[-1]['end'] == 'loop':   # a looping animation (the Phoenix's dive 88): its
                one = [dict(s_) for s_ in steps]          # steps again and again, unrolled (240 frames, held after): only
                one[0]['ticks'] -= 1                      # the first pass has rom_steps' one more tick on step 0 [meas:
                while sum(s_['ticks'] + 1 for s_ in steps) < 240:   # 6246A_h 88.0 / 88.1 five frames each]
                    steps += [dict(s_) for s_ in one]
            self.anims[key] = {'mode': 'hold', 'steps': steps, 'n': n}
            self.states.append(key)
        return self.states.index(key)

    def L(self):
        self.labels += 1; return f'_{self.labels}'

    def emit(self, *ops): self.ops += ops

    def block(self, label, key, n, b, ends=None, branches=(), extras=(), enter=(), spawns=None, state=None,
              extra_end=0, at=None, extras_from=0, step_ops=None):
        """animation n as one block from label: P_ANIM (b = damage | reaction << 8), the enter ops, then frame by
        frame: branches [(op tuple)...] (the handler's tests), the clock (a step's command on its first frame, spawns
        {step: object index}), the move, extras (per-frame ops: follow-up checks; a function of the program when they
        hold labels; from the segment of step extras_from on). ends: the label its last frame
        goes on to (None: it holds until a branch leaves). state: the motion in force at entry {ax, ay, y (None:
        not static)}; returns the state at its end. at: the block's first frame (static entries: effects pinned to
        the program's frames). step_ops {step: [ops]}: run on that step's first frame (the handler's acts on a step
        event: its phase writes, the screen effect)"""
        st = dict(state or {'ax': 0.0, 'ay': 0.0, 'y': 0.0, 'vx': 0.0, 'vy': 0.0})
        if at is not None: self.entry[label] = at
        steps = kz.parse_anim(CH << 12 | n)
        dur = [max(1, s['ticks']) for s in steps]
        t0 = [sum(dur[:k]) for k in range(len(steps))]
        D = sum(dur) + extra_end
        spawns = spawns or {}
        ix = self.anim(key, n)
        self.emit(label, ('anim', ix, b))
        if label == 'START': self.emit(('set', REG['vx'], 0), ('set', REG['vy'], 0), ('set', REG['g'], 0))   # (his walk's speed dropped)
        self.emit(*enter)
        # the events: the steps whose command changes the motion in force (a stop when still writes nothing), and the
        # step after each attack step: Kizuna's hit ends the step it lands in (after the hit-stop the next step
        # shows, its ticks from 0 [meas: 236C_h 8E.1 t3 hit on its 2nd frame -> 8E.2], j.2B's 'a hit moves 8F on')
        live = [bool(s_['flags'] & 0x100) for s_ in self.anims[key]['steps']]
        evs = []
        for k, s_ in enumerate(steps):
            m = step_motion(s_); ops = []
            ax0, ay0 = st['ax'], st['ay']
            ax, ay = m.get('ax', ax0), m.get('ay', ay0)
            if 'vx' in m and (st['vx'] != m['vx'] or ax != ax0): ops.append(('set', REG['vx'], fx16((m['vx'] + ax / 2) * S)))
            elif 'vx' not in m and ax != ax0: ops.append(('add', REG['vx'], fx16((ax - ax0) / 2 * S)))
            if 'vy' in m and (st['vy'] != m['vy'] or ay != ay0): ops.append(('set', REG['vy'], fx16((m['vy'] + ay / 2) * S)))
            elif 'vy' not in m and ay != ay0: ops.append(('add', REG['vy'], fx16((ay - ay0) / 2 * S)))
            if ay != ay0: ops.append(('set', REG['g'], fx16(-ay * S)))
            st['ax'], st['ay'] = ax, ay
            if 'vx' in m: st['vx'] = m['vx']
            if 'vy' in m: st['vy'] = m['vy']
            if ax: st['vx'] = None                       # (no longer static)
            if ay: st['vy'] = None
            if 'nudge' in m:
                dx, dy = m['nudge']
                if dx: ops.append(('nudge', sc(dx), 0))
                if dy:
                    if st['y'] is not None: st['y'] = max(0.0, st['y'] + dy); ops.append(('set', REG['h'], fx16(st['y'] * S)))
                    else: ops.append(('nudge', 0, sc(dy)))
            if st['vy'] is None or st['vy']: st['y'] = None   # (the height is no longer static)
            for o in spawns.get(k, ()): ops.append(('spawn', o))
            ops += (step_ops or {}).get(k, ())             # the handler's acts on that step's event (TODO #136: victim phases, the screen)
            if k == 0 or ops or k == extras_from or live[k - 1]: evs.append((k, ops, st['ax']))
        ground = st['y'] == 0.0 and all(not (set(step_motion(s_)) & {'vy', 'ay'}) and not step_motion(s_).get('nudge', (0, 0))[1]
                                         for s_ in steps)   # (no P_FALL: on the floor all along)
        bodies, pend = {}, []
        def body(ax, on):                                # one frame: the handler's tests, the move, the extras
            if (ax, on) in bodies: return [('jmp', bodies[(ax, on)])]
            bodies[(ax, on)] = bl = self.L()             # (its first use: the ops follow on)
            return [bl, *branches, ('move',), *([('add', REG['vx'], fx16(ax * S))] if ax else []), *([] if ground else [('fall',)]),
                    *((extras(self) if callable(extras) else extras) if on else ()), ('yield',)]
        # the clock: P_DEC every frame of the block, the frame an event runs once more (its ops fall into the next
        # segment's stub): in segment i at frame t cnt = -(t + i + 1); segment i's stub tests the next event's frame
        # (PC_CNTLE), the event's ops then run and resume at the next stub. A hit in a segment ending on an attack
        # step (Kizuna: the step ends, the next one shows after the hit-stop with its full ticks): the clock and the
        # animation run on (P_DEC, P_ADV) to that step's last tick, so the frame's own advance enters the next step,
        # whose event runs now
        self.emit(('set', REG['cnt'], 0))
        Es = [None] + [self.L() for _ in evs[1:]]
        for i, (k, ops, ax) in enumerate(evs):
            last = i + 1 == len(evs)
            if i: self.emit(Es[i])
            self.emit(*ops)
            on = k >= extras_from
            if last and not ends:
                if (ax, on) in bodies: self.emit(('resume_at', bodies[(ax, on)]), ('jmp', bodies[(ax, on)]))
                else: bd = body(ax, on); self.emit(('resume_at', bd[0]), *bd)
                continue
            stub = self.L()
            nxt, T = (Es[i + 1], t0[evs[i + 1][0]]) if not last else (ends, D)
            th = -(T + i + 1)
            kl = (evs[i + 1][0] if not last else len(steps)) - 1    # the segment's last step
            H = self.L() if live[kl] else None
            self.emit(('resume_at', stub), stub, *([('br', PC['hitany'], 1, H)] if H else []), ('dec',),
                      ('br', PC['cntle'], 1, nxt, th), *body(ax, on))
            if H:
                Lp = self.L()
                self.emit(H, ('hitclr',), ('dec',), Lp, ('br', PC['cntle'], 1, nxt, th), ('adv',), ('dec',), ('jmp', Lp))
        return st

    def prims(self):
        """the ops as bprim_t rows [op, a, b, v] (labels resolved; v None = export_bm's hit effect)"""
        at, k = {}, 0
        for o in self.ops:
            if isinstance(o, str): at[o] = k
            else: k += 1
        out = []
        for o in self.ops:
            if isinstance(o, str): continue
            c = o[0]
            if c == 'anim': out.append([P['anim'], o[1], o[2], None])
            elif c == 'set': out.append([P['set'], o[1], 0, o[2]])
            elif c == 'add': out.append([P['add'], o[1], 0, o[2]])
            elif c == 'nudge': out.append([P['nudge'], 0, o[1], o[2]])
            elif c == 'check': out.append([P['check'], o[1], 1 if len(o) > 2 else 0, 0])
            elif c == 'br': out.append([P['br'], o[1] | o[2] << 7, -1 if o[3] is None else at[o[3]], o[4] if len(o) > 4 else 0])
            elif c == 'yield': out.append([P['br'], PC['always'] | 0x80, -1, 0])
            elif c in ('resume_at', 'jmp'): out.append([P[c], 0, at[o[1]], 0])
            elif c == 'spawn': out.append([P['spawn'], o[1], 0, 0])
            elif c in ('vphase', 'screen'): out.append([P[c], o[1], 0, 0])
            else: out.append([P[c], 0, 0, 0])
        assert len(out) < 0x7FFF, len(out)
        return out

def step_voices(fcs):
    """{(Kim's anim, step): [sound words]} sent as that step showed (a word goes out the frame after its step's first
    one: voices_kz.words_of), from the move's captures; export_bm keeps his voices (voices.json), the rest is silent"""
    import voices_kz
    out = {}
    for fr in fcs:
        for f, w in voices_kz.words_of(fr):
            p = fr[max(0, f - 1)][0]
            ws = out.setdefault((p[0], p[1]), [])
            kind = lambda x: 1 if x >> 8 == 0x1C and x & 0xFF >= 0xB0 else 2 if x >> 8 == 0x1A else 0
            if w not in ws and not (kind(w) and any(kind(x) == kind(w) for x in ws)): ws.append(w)   # (one voice a
    return out                                           # step: Kizuna's alternate yells, the first kept)

# The moves [code: substates_kz.py, the handlers below]; 'caps' = the captures their voices / effects / reactions come
# from (whiff first). Kizuna's 'animation ended' test sees the end the frame after its last step's frames
# [meas: 9B -> 9C, 97 -> 8E]; a move whose handler went back to neutral ($377E4) plays its animation to the end there
# (214B: 93's last step one frame more [meas]).
PROG_MOVES = ('214B', '236A', '236C', '[2]8C', '421A', '6246A')
CEILING = 384                                        # $109678 in the vs captures' stage (Kizuna px, up): the Phoenix's
                                                     # victim is frozen at Kim once above it ($3AC92) [meas: 6246A_h]

def first_steps(fr, rows, objs, anims):
    """{(Kim's animation, step): [object index]}: the step each effect object first shows on (its spawn op goes there:
    the object's row 0 shows on the frame it is spawned)"""
    out = {}
    for j, o in enumerate(objs):
        p = fr[rows[o['spawn_row']]][0]
        if p[0] in anims: out.setdefault((p[0], p[1]), []).append(j)
    return out

def merged_effect(B, fr, rows, x0, name):
    """the objects called name drawn at one place each frame (the Phoenix's four PHOELX halves, $3AD22: one place,
    Kim's) as one pinned effect whose frames are their steps together (the multipart export's way)"""
    rws, first = [], None
    for k, i in enumerate(rows):
        p = fr[i][0]
        st = sorted(o[6] for o in fr[i][2] if o[1] >> 12 == CH and o[7] == name)
        if not st:
            if first is not None: break
            continue
        if first is None: first = k
        o = next(o for o in fr[i][2] if o[1] >> 12 == CH and o[7] == name)
        rws.append([B.frame(tuple(st) if len(st) > 1 else st[0]), sc(o[3] - x0) - sc(p[2] - x0), sc(o[4]) - max(0, sc(p[3])), None, None])
    return {'effect': True, 'table': 0, 'state': 0, 'kind': 0, 'hit_kind': 1, 'follow': 7, 'spawn_row': first, 'spawn_x': 0,
            'spawn_y': 0, 'loop': None, 'death': None, 'life': len(rws), 'travel': 0, 'vx': 0, 'rows': rws, 'end': [],
            'react': 'knockdown', 'child': None, 'hits': {}, 'name': name}
def prog_special(B, inp, cap, fc, rec):
    """special inp as a program (TODO #133-#138): rec = its recorded export (special / multipart: the Brawler Lab's
    rows); -> rec with 'rom'"""
    E_ = (cap | fc)
    react = hit_reactions(fc)
    if inp in ('214B', '236A'):
        # $3A872 (command $27, 214B; 236A = the same command with +$105 bit 6, the tag-in strike: state 432, anim 126):
        # state 417 / 432, bsr $3B032 spawns the 'ADH EFFE' task (state 419 / 434: the effect), then waits while
        # still (vx 0) for the step-2 slide (cmd 10: vx 10, ax -1/16), then for vx 0 again (step 6 stops it) -> neutral
        # ($377E4), where the animation plays on to its end (93 / 126 hold the last step) [meas: one frame more]
        n = 0x93 if inp == '214B' else 0x126
        caps = [cap[SPECIALS[inp][0]]['frames']] + ([fc['214B_h']['frames']] if inp == '214B' else [])
        K = KzProg(B, react, step_voices(caps))
        fr = caps[0]; s0, e, rows = part_rows(fr, [n], False)
        K.objects = effects(B, fr, rows, 0, fr[s0][0][2])
        for o in K.objects: o['spawn_row'] = 0
        K.block('START', 'a', n, SPECIAL_DAMAGE // max(1, rec['game_hits'] or 1) | R_KNOCKDOWN << 8, ends='END',
                spawns={0: list(range(len(K.objects)))}, extra_end=1, at=0)
        parts, links, flinks = [], [], []
    elif inp == '236C':
        # $3A650 (command $25): state 400 (anim 97); $3A68A: 97 ended -> on the ground state 429 (8E, the 3-hit rush),
        # the request cleared, the window opened (+$10C bit 3) -> $3A6D6: 8E ended -> 236C again came: state 402
        # (98), cleared -> $3A720: 98 ended -> again: state 403 (9A) -> $3A76A: 9A ended -> 99; no request: 99
        # (state 420, the window closed) -> neutral. The brawler: 'again' = its own direction + C (P_CHECK each
        # frame of 8E / 98, its hit-stop's presses included: Kizuna's command scan runs in the hit-stop too)
        caps = [fc[r]['frames'] for r in ('236C_w', '236C2_w', '236C3_w', '236C_h', '236C2_h', '236C3_h')]
        K = KzProg(B, react, step_voices(caps))
        hits = lambda n: sum(1 for s in kz.parse_anim(CH << 12 | n) if s['trailer'] & 0x8000)
        d = lambda n: max(1, SPECIAL_DAMAGE // max(1, hits(n)))
        chk = (('check', 1),)                            # (a press in a hit-stop counts: fighter_t.spend keeps it)
        st = K.block('START', '97', 0x97, 0, ends='R1', at=0)
        st = K.block('R1', '8E', 0x8E, d(0x8E) | R_HEAVY << 8, ends='J1', enter=(('part',),), extras=chk, state=st)
        K.emit('J1', ('br', PC['link'], 1, 'C2', 1), ('jmp', 'END99'))
        st2 = K.block('C2', '98', 0x98, d(0x98) | R_HEAVY << 8, ends='J2', enter=(('part',),), extras=chk, state=st)
        K.emit('J2', ('br', PC['link'], 1, 'C3', 1), ('jmp', 'END99'))
        K.block('C3', '9A', 0x9A, d(0x9A) | R_KNOCKDOWN << 8, ends='END99', state=st2)
        K.block('END99', '99', 0x99, 0, ends='END', state=dict(MERGE), extra_end=1)
        parts = [{'states': ['97', '8E']}, {'states': ['98']}, {'states': ['9A']}]
        flinks = [{'from': 0, 'to': 1, 'input': 'again'}, {'from': 1, 'to': 2, 'input': 'again'}]; links = ['again']
    elif inp == '[2]8C':
        # $3A904 (command $28): state 421 (9B, the rising staff), the request cleared; $3A93E: waits until airborne;
        # $3A966: 9B ended -> 9C (the fall); a hit landed first -> the window opens ($3A994): at 9B's end 2C came ->
        # 9D (the dive) else 9C; $3A9D4: on the floor -> 9E (state 424) -> neutral. The brawler: 2C = down+A, read
        # each frame once airborne (9B step 2 on) after a hit; the pillar '503 EFFE' with 9B, its second with 9D
        caps = [fc[r]['frames'] for r in ('28C_w', '28C_h', '28C2_h', '28C2_w')]
        K = KzProg(B, react, step_voices(caps))
        fr = caps[0]; s0, e, rows = part_rows(fr, [0x9B], False)
        K.objects = effects(B, fr, rows, 0, fr[s0][0][2])
        fr2 = fc['28C2_h']['frames']; s2 = next(i for i, f in enumerate(fr2) if f[0][0] == 0x9D)
        e2 = next(i for i in range(s2, len(fr2)) if fr2[i][0][0] not in (0x9D, 0x9E))
        dive_fx = effects(B, fr2, [i for i in range(s2, e2) if not frozen(fr2, i)], 0, fr2[s2 - 1][0][2])
        D9B = sum(max(1, s['ticks']) for s in kz.parse_anim(CH << 12 | 0x9B))
        for o in K.objects: o['spawn_row'] = 0
        for o in dive_fx: o['spawn_row'] = D9B
        K.objects += dive_fx
        nh = sum(1 for s in kz.parse_anim(CH << 12 | 0x9B) if s['trailer'] & 0x8000)
        each = max(1, SPECIAL_DAMAGE // max(1, nh))
        def chk(K_):                                     # the window: a hit landed (PC_HIT), then the press; from
            g = K_.L(); return [('br', PC['hit'], 0, g), ('check', 1), g]   # 9B step 2 (airborne: $3A93E)
        st = K.block('START', '9B', 0x9B, each | R_HEAVY << 8, ends='J', enter=(('part',),), extras=chk, extras_from=2,
                     at=0, spawns={0: list(range(len(K.objects) - len(dive_fx)))})
        K.emit('J', ('br', PC['link'], 1, 'DIVE', 1), ('jmp', 'FALL'))
        K.block('FALL', '9C', 0x9C, 0, branches=(('br', PC['land'], 1, 'LAND'),), state=st)
        K.block('DIVE', '9D', 0x9D, SPECIAL_DAMAGE | R_KNOCKDOWN << 8, branches=(('br', PC['land'], 1, 'LAND'),), state=st,
                spawns={0: list(range(len(K.objects) - len(dive_fx), len(K.objects)))}, at=D9B)
        K.block('LAND', '9E', 0x9E, 0, ends='END', state=dict(MERGE), extra_end=1)
        parts = [{'states': ['9B']}, {'states': ['9C', '9E']}, {'states': ['9D']}]
        flinks = [{'from': 0, 'to': 2, 'input': 'dA'}]; links = ['dA']
    elif inp == '421A':
        # $3AEE0 (command $2A): state $90 (anim 100), $3AF14 waits for the lunge (100.3's cmd 10: vx 8, ax -3/16);
        # $3AF3A each frame: 100 ended -> neutral (the whiff); a hit that caught -> at once state $91 (101) and the victim
        # snapped onto Kim's place and frozen ($1AF bit 6 + $1AE bit 0: $2CD06 -> its +$106 bit 3, $2CE56 its x / y =
        # Kim's), the relief call (+$180 = 2: the tag partner jumps in, task RELIEFP1 at $101B00, and lands the last two
        # hits [meas: 421A_h, WLOG on the victim's life: pc $2B56A from the partner's $345DA / $34646] -- the brawler has
        # no partner: Kim's own three hits); $3AFB0: his next hit landed (+$129 bit 2) -> the victim thawed ($1AF bit 7),
        # its reaction plays on; $3AFD4 / $3AFF8: 101 to its end -> neutral
        caps = [fc[r]['frames'] for r in ('421A_w', '421A_h')]
        K = KzProg(B, react, step_voices(caps))
        fr = caps[0]; s0, e, rows = part_rows(fr, [0x100], False)
        K.objects = effects(B, fr, rows, 0, fr[s0][0][2])
        sp0 = first_steps(fr, rows, K.objects, (0x100,))
        each = max(1, SPECIAL_DAMAGE // 3)              # (Kim's three hits: 100.3, 101.3, 101.7)
        # (the end: the handler's 'ended' test the frame after the held last step, then the neutral routine plays that
        # step's ticks again and sees the end once more [meas: 100.6 1 tick shown 3 frames, 101.11 6 ticks 13, 85.10
        # 4 ticks 9]: last = 1 + its ticks)
        last = lambda n: 1 + kz.parse_anim(CH << 12 | n)[-1]['ticks']
        K.block('START', '100', 0x100, each | R_HEAVY << 8, ends='END', branches=(('br', PC['hit'], 1, 'CATCH'),),
                spawns={k: v for (a, k), v in sp0.items()}, extra_end=last(0x100), at=0)
        def thaw(K_):                                    # (each frame of 101: his next hit thaws the victim)
            g = K_.L(); return [('br', PC['hit'], 0, g), ('vphase', VA['thaw']), g]
        stop = (('set', REG['vx'], 0), ('set', REG['vy'], 0), ('set', REG['g'], 0))   # (the new state: Kim's velocity 0 [meas:
                                                                                        # 421A_h / 6246A_h, +$34 at 101.0 / 86.0])
        K.block('CATCH', '101', 0x101, each | R_HEAVY << 8, ends='END', enter=stop + (('vphase', VA['snap'] | VA['freeze']), ('hitoff',)),
                extras=thaw, extra_end=last(0x101))
        parts, links, flinks = [], [], []
    elif inp == '6246A':
        # $3ABA6 (command $29): state $194 (85, the rush: 85.0's cmd 10 vx 5); $3ABD0: 85 ended -> neutral; a hit that
        # caught -> at once $195 (86) and the victim snapped onto Kim and mirrored ($1AF bit 4 + $1AE bit 0: its +$107
        # bit 2, $37A20: its velocity = -Kim's, so it moves away as he steps back [meas: 6246A_h, symmetric about the
        # snap point]); $3AC22: 86's first event (the 0-tick step 42, its handler the frame after: 43) -> unmirrored
        # ($1AF bit 5); $3AC46: the next (54, at 55) -> the screen effect on ($27E4 = $47007DFF, $27E1 = $80) and the
        # four PHOELX flames on Kim; $3AC7C each frame: 86 ended -> $3ACCE, else the victim above the ceiling ($109678)
        # -> snapped onto Kim and frozen ($1AF bit 6); $3ACCE: state $197 (88, the dive: 86.69's cmd 9, vy -12), the
        # screen effect off, the PHOELX W feathers (random places: the captured ones); $3ACF4: landed -> the victim
        # thawed ($1AF bit 7), state $198 (89) -> neutral (89 to its end)
        caps = [fc[r]['frames'] for r in ('6246A_w', '6246A_h')]
        K = KzProg(B, react, step_voices(caps))
        fr = caps[1]; s0, e, rows = part_rows(fr, [0x85, 0x86, 0x88, 0x89], True)
        x0 = fr[s0][0][2]
        flames = merged_effect(B, fr, rows, x0, 'PHOELX')
        rest = effects(B, fr, rows, 0, x0, skip={(i, o[0]) for i in rows for o in fr[i][2] if o[7] == 'PHOELX'})
        K.objects = [flames] + rest
        sp_ = first_steps(fr, rows, K.objects, (0x86, 0x88))
        dmg = game_damage(FOLLOW['6246A'], fc).get('damage', SPECIAL_DAMAGE)   # Kizuna's (6246A_h's life drop) over its
        nh = max(1, sum(1 for j in range(s0 + 1, e) if (fr[j][1][0] != fr[j - 1][1][0] and fr[j][1][0] not in (0, 0x1B, 0x1D, 1, 2))
                        or (fr[j][1][0] == fr[j - 1][1][0] and fr[j][1][1] == 0 and fr[j - 1][1][1] != 0 and fr[j][1][10] == 0)))
                                                         # hits (each new reaction: 12, the rush, 86's ten, the second 33), the rush's the rest
        each = max(1, dmg // nh)
        last = lambda n: 1 + kz.parse_anim(CH << 12 | n)[-1]['ticks']   # (as 421A's: the handler's end, then neutral's)
        st = K.block('START', '85', 0x85, max(1, dmg - each * (nh - 1)) | R_HEAVY << 8, ends='END',
                     branches=(('br', PC['hit'], 1, 'CATCH'),), extra_end=last(0x85), at=0)
        def ceiling(K_):                                 # (each frame from 86.55: the victim above the ceiling)
            g = K_.L(); return [('br', PC['thigh'], 0, g, sc(CEILING)), ('vphase', VA['snap'] | VA['freeze']), g]
        stop = (('set', REG['vx'], 0), ('set', REG['vy'], 0), ('set', REG['g'], 0))
        st = K.block('CATCH', '86', 0x86, each | R_HEAVY << 8, ends='DIVE', enter=stop + (('vphase', VA['snap'] | VA['mirror']),),
                     step_ops={43: [('vphase', VA['unmirror'])], 55: [('screen', 1)]}, extras=ceiling, extras_from=55,
                     spawns={k: v for (a, k), v in sp_.items() if a == 0x86})
        K.block('DIVE', '88', 0x88, 0, enter=(('screen', 0),), branches=(('br', PC['land'], 1, 'LAND'),),
                spawns={k: v for (a, k), v in sp_.items() if a == 0x88}, state=st)
        K.block('LAND', '89', 0x89, 0, enter=(('vphase', VA['thaw']),), ends='END', state=dict(MERGE), extra_end=1)
        parts, links, flinks = [], [], []
    K.emit('END', ('end',))
    rom = {'states': K.states, 'anims': {k: {'mode': a['mode'], 'steps': a['steps'], 'kz_anim': a['n']} for k, a in K.anims.items()},
           'prims': K.prims(), 'objects': K.objects, 'openings': {}, 'hit_kind': 1, 'last_hit': -1, 'apex': -1,
           'length': len(rec['script']), 'now': True, 'sreact': True, 'sharepush': True}   # (TODO #136: Kizuna's
                                                     # bodies share the push, $2B644's +$0C bit 6 path: SF_SHARE)
    if parts: rom.update(parts=parts, follow_links=flinks, links=links)
    # as down+D (the rising reversal, export_bm rom_inv): invincible to its last hit or its apex on the whiff path (the
    # recorded rows of its first parts: the same frames as the program's)
    wp = rec['parts'][0 if FOLLOW.get(inp, {}).get('carry') is not None else 1]['end'] if rec.get('parts') else len(rec['script'])
    live = [i for i in range(wp) if any(k_[0] == '1' for k_ in rec['row_boxes'][i])]
    rom['last_hit'] = live[-1] if live else -1
    peak = max(range(wp), key=lambda i: rec['script'][i][2])
    rom['apex'] = peak if rec['script'][peak][2] > 0 else -1
    out = {**rec, 'parts': [], 'links': [], 'rom': rom}   # (its follow-ups: the program's, rom parts / follow_links)
    out.pop('carry_src', None)                           # (TODO #136: no recorded victim places: the victim's own reaction)
    if out.get('backdrop'): out['backdrop'] = {'rows': [0xFFFF, 1], 'colours': out['backdrop']['colours']}   # (P_SCREEN)
    return out

VSTATE = {0xEF: (0x10C, 0xFA), 0xDE: (0x17A, 0xDE)}   # Hayate's victim animation -> (state, Kim's animation for it)
def vstate(a):
    """the victim's (Hayate's) animation -> (its state: the first one Hayate plays it in, the thrower's animation there)"""
    st = FK.smap(0).index(a)
    return st, FK.smap(CH)[st]
POSES = json.load(open(os.path.join(HERE, 'victim_poses_kz.json')))['poses']
KIM_POSE = {'grabbed': (0x24, 3), 'curled': (0x32, 2), 'inverted': (0x32, 2), 'horizontal': (0x32, 2),
            'falling': (0x32, 2), 'lying': (0x2B, 5)}    # Kim's own (feet-centred) frame for each posture he is thrown in

def vcentre(n, k):
    """Kim's frame of animation n step k drawn facing right at x 0: (centre x, height of its lowest pixel)"""
    img = np.zeros((H, W), np.uint16); kz.render_step(img, kz.parse_anim(CH << 12 | n)[k]['addr'], X0, Y0)
    ys, xs = np.nonzero(img)
    return (xs.min() + xs.max()) / 2 - X0, Y0 - 1 - ys.max()

def throw(B, cap):
    """Kim's throw (6C, $6F) in export96's throw layout: per frame from the grab to the victim's landing, the thrower
    [frame, dx, dy, turned] and the victim [Kim's frame for the posture, x forward, height, same facing, in front, key]"""
    fr = cap['throw_fc']['frames']; TH = FK.kim_anim(CH, 0x6F)
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == TH)
    e = next((i for i in range(s0, len(fr)) if fr[i][1][0] == 0xDE and fr[i][1][1] == 1), None)
    if e is None:                                    # the victim does not end lying: up to its first neutral frame
        e = next((i for i in range(s0 + 1, len(fr)) if fr[i][1][0] in (0, 0x1B) and fr[i][0][0] != TH), len(fr) - 1)
    e += 1
    x0 = fr[s0][0][2]
    timeline, rows, steps = [], [], []
    for i in range(s0, e):
        a, b = fr[i][0], fr[i][1]
        fi = B.frame(a[5])
        timeline.append([fi, sc(a[2] - x0), sc(a[3]), a[4]])
        if a[0] == TH and (not steps or steps[-1][0] != a[5]): steps.append([a[5], 0])
        if a[0] == TH: steps[-1][1] += 1
        st, kn = vstate(b[0])
        key = f'{st:X}.{b[1]}'
        nst = len(kz.parse_anim(CH << 12 | kn))
        cx, bot = vcentre(kn, min(b[1], nst - 1))
        # the posture: the frame of it read by eye for Kim's throw (victim_poses_kz.json), else the thrower's own frame
        # of the victim's state and step (every fighter has its frame for that state: what Kizuna draws for him there)
        vn, vk = (FK.kim_anim(CH, KIM_POSE[POSES[key][0]][0]), KIM_POSE[POSES[key][0]][1]) if key in POSES else (kn, min(b[1], nst - 1))
        vf = B.frame(kz.parse_anim(CH << 12 | vn)[vk]['addr'])
        rows.append([vf, sc(b[2] - a[2] - cx), sc(b[3] + bot), 0, 0, key])
    anim = {'slot': TH, 'mode': 'hold', 'steps': [step(B, ad, n, step_boxes(ad)) for ad, n in steps]}
    return {'slot': TH, 'inputs': '6C / 4C (close)', 'table': [], 'hold': False, 'timeline': timeline,
            'victims': {NAME: rows}, 'impacts': [], 'anim': anim}

def rom_palette(n): return [kz.u16(0x70000 + 32 * n + 2 * i) for i in range(16)]

KIM = {}
def setup(name):
    """fighter name's tables (module doc): Kim's as written, another's moved to its animations + its plan_kz specials"""
    global CH, NAME, CAPTURE, FOLLOWUPS, SETS, MOVES, SPECIALS, FOLLOW, CAP_OF
    if not KIM: KIM.update(CAPTURE=CAPTURE, FOLLOWUPS=FOLLOWUPS, SETS=SETS, MOVES=MOVES, SPECIALS=SPECIALS, FOLLOW=FOLLOW, CAP_OF=CAP_OF)
    NAME, CH = name, FK.CAST[name]
    if name == 'kim':
        CAPTURE, FOLLOWUPS, SETS, MOVES, SPECIALS, FOLLOW, CAP_OF = (KIM[k] for k in ('CAPTURE', 'FOLLOWUPS', 'SETS', 'MOVES', 'SPECIALS', 'FOLLOW', 'CAP_OF'))
        return
    CAPTURE, FOLLOWUPS = FK.path(name, 'capture'), FK.path(name, 'followups')
    SETS = [kz.u16(0x1438 + 2 * CH), kz.u16(0x1458 + 2 * CH)]
    plan = json.load(open(FK.path(name, 'follow')))
    ka = lambda n: FK.kim_anim(CH, n)
    air = plan['air']['anim'] if plan.get('air') else ka(0x58)          # its air special, else j.B
    def clamp(n, first, last):                       # Kim's step ranges cut to the fighter's own animation
        k = len(kz.parse_anim(CH << 12 | n)) - 1
        return min(first, k), None if last is None else max(min(last, k), min(first, k))
    MOVES = {}
    for mv, src in KIM['MOVES'].items():
        if src[0] == 'anim':
            n = air if src[1] == 0x8F else ka(src[1]); MOVES[mv] = ('anim', n, *clamp(n, src[2], src[3]))
        else: MOVES[mv] = ('cap', src[1], tuple(ka(a) for a in src[2]), src[3])
    CAP_OF = {ka(k): v for k, v in KIM['CAP_OF'].items()}
    SPECIALS = {k: (v[0], v[1], v[2]) for k, v in plan['specials'].items()}
    FOLLOW = {}
    for k, F in plan['follow'].items():
        FOLLOW[k] = {**F, 'parts': [(r, tuple(a), n) for r, a, n in F['parts']],
                     'links': [tuple(l) for l in F['links']]}

def export(names, outdir, only=None, extra=None):
    B = Builder(); out = {'game': 'kizuna', 'tile_base': TILE_BASE, 'characters': {}}
    for name in names:
        setup(name); SREACT.clear()
        cap = json.load(open(CAPTURE))
        cid = CAST[name]
        anims = {}
        for mv, src in MOVES.items():
            if src[0] == 'anim': st = anim_steps(B, src[1], src[2], src[3], cap); slot = src[1]
            else: st = cap_steps(B, cap, src[1], src[2], src[3]); slot = src[2][0]
            anims[mv] = {'slot': slot, 'mode': 'loop' if mv in LOOP else 'hold', 'steps': st}
        for mv, src in ALIAS.items(): anims[mv] = anims[src]
        w = (extra or {}).get(name, {}).get('watch')
        if w:                                            # roster watch pose: (animation, step; -1 = its last)
            st = boxes_in_force(w[0]); k = w[1] if w[1] >= 0 else len(st) - 1
            anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': [step(B, st[k][0]['addr'], st[k][0]['ticks'], [])]}
        if only is not None: anims = {k: v for k, v in anims.items() if k in only}
        for mv, (a, f, l) in ((extra or {}).get(name, {}).get('anims') or {}).items():   # whole animations by request (export_bm FLASH_POSES: the flash pose, TODO #145): {move: (anim, first, last)}
            anims[mv] = {'slot': a, 'mode': 'hold', 'steps': anim_steps(B, a, f, l)}
        th = throw(B, cap)
        anims['throw_c'] = th.pop('anim')
        fc = json.load(open(FOLLOWUPS))
        def thrown(inp):                                 # a move whose only branch is the hit (the thrower's recovery
            F = FOLLOW[inp]                              # when its projectile hits, Hayate's 236C) plays as one part
            if F.get('carry') or any(l[2] != 'hit' for l in F['links']): return False     # with its projectile
            fr = cap[SPECIALS[inp][0]]['frames']
            return projectile_run(fr, part_rows(fr, SPECIALS[inp][2], False)[0]) is not None
        sps = [multipart(B, inp, fc) if inp in FOLLOW and not thrown(inp) else special(B, inp, cap) for inp in SPECIALS]
        sps += [air_special(B, inp, fc) for inp in (AIR if name == 'kim' else ())]   # (TODO #200: Kim's j.2B)
        if name == 'kim':                                # (TODO #133-#138: his specials played by their programs)
            sps = [prog_special(B, sp['input'], cap, fc, sp) if sp['input'] in PROG_MOVES else sp for sp in sps]
        sets = [[[0] + rom_palette(s_ + p - 16)[1:] for p in B.pals] for s_ in SETS]
        out['characters'][name] = {'id': cid, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0],
                                   'physics': physics(cap), 'throws': {'throw_c': th}, 'specials': sps,
                                   'sreacts': [{**r, **{k: r[k] * S for k in ('vx', 'ax', 'vy', 'ay', 'bvx', 'bvy', 'bay')}} for r in SREACT],
                                   'modes': {'sets': ['colour A', 'colour B'], 'palettes': [f'{p:02X}' for p in B.pals],
                                             'zoom': Z}}
    out['tiles'] = len(B.tiles)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * TILE_BASE) + b''.join(B.tiles)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    ex = export(sys.argv[2:] or ['kim'], sys.argv[1], extra={'kim': {'watch': (0x37, 0)}})
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'])
        print('  pals', ch['modes']['palettes'], 'max cols', max(sum(len(p['tiles']) for p in f['parts']) for f in ch['frames']))
        for mv, a in ch['anims'].items():
            print(f"  {mv:16s} {a['slot']:4X} " + ' '.join(f"{ch['frames'][s['frame']]['record']}/{s['ticks']}{'*' if s['flags'] & 0x100 else ''}{'>' + str(s['dx']) if s['dx'] else ''}" for s in a['steps']))
        for sp in ch['specials']:
            print('  ', sp['input'], len(sp['script']), 'rows, shape', sp['shape'], 'game hits', sp['game_hits'])
    print(ex['tiles'], 'tiles')
