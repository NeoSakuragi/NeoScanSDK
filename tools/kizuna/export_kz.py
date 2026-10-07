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
        setup(name)
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
        sets = [[[0] + rom_palette(s_ + p - 16)[1:] for p in B.pals] for s_ in SETS]
        out['characters'][name] = {'id': cid, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0],
                                   'physics': physics(cap), 'throws': {'throw_c': th}, 'specials': sps,
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
