#!/usr/bin/env python3
"""Kizuna Encounter fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99 export
(layer 0 of docs/brawler_data_model.md, one code path), the way tools/samsho4 and tools/whp do (spec `kizuna:kim`).

    python3 export_kz.py OUTDIR [kim]          -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

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
Known limits: the effects his specials spawn (sparks, the Phoenix's flames) are not drawn; no D button
attacks in Kizuna (D = tag): the brawler's D normals use his strong kick (B+C, $6E); one jump height (hop = jump)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kz
import numpy as np

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = {'kim': 5}
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
    'win_a': ('anim', 0x80, 0, None),
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
    for s in kz.parse_anim(0x5000 | n):
        if s['boxes'] is not None: cur = s['boxes']
        elif not s['trailer'] & 0x10 and not s['nboxes']: cur = []
        out.append((s, cur))
    return out

STEP_BOXES = {}
def step_boxes(addr):
    if not STEP_BOXES:
        for n in range(1, kz.anim_count(5)):
            try:
                for s, b in boxes_in_force(n): STEP_BOXES[s['addr']] = b
            except Exception: pass
    return STEP_BOXES.get(addr, [])

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
        """the step at addr as brawler parts: drawn by Kizuna's renderer at zoom Z facing right, mirrored, re-tiled"""
        if addr in self.index: return self.index[addr]
        img = np.zeros((H, W), np.uint16)
        kz.render_step_zoom(img, addr, X0, Y0, Z)
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
        self.frames.append({'record': f'{addr:06X}', 'parts': parts, 'weapon': None})
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
    w = run('walk_fwd', 0x1); walk = (w[-1][2] - w[0][2]) / (len(w) - 1)
    wb = run('walk_back', 0x2); back = abs(wb[-1][2] - wb[0][2]) / (len(wb) - 1)
    ju = [f[0] for f in cap['jump_up']['frames'] if f[0][0] in (0x9, 0x81)]
    t0 = next(i for i, f in enumerate(ju) if f[3] > 0) - 1
    ys = [f[3] for f in ju[t0:]]
    n = ys.index(max(ys)); vy0 = 2 * max(ys) / n; g = vy0 / n
    fw = [f[0] for f in cap['jump_fwd']['frames'] if f[0][3] > 0]
    jdx = (fw[-1][2] - fw[0][2]) / (len(fw) - 1)
    return {'walk_fwd': walk * S, 'walk_back': back * S, 'jump_vy0': vy0 * S, 'gravity': g * S, 'jump_dx': jdx * S, 'prejump': t0 + 1}

def special(B, inp, cap):
    rec, hitrec, anims = SPECIALS[inp]; fr = cap[rec]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    e = next((i for i in range(s0, len(fr)) if fr[i][0][0] not in anims), len(fr))
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
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rboxes,
            'row_steps': rsteps, 'marks': [''] * n, 'projectiles': [], 'anims': anims,
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False], 'game_hits': game_hits}

VSTATE = {0xEF: (0x10C, 0xFA), 0xDE: (0x17A, 0xDE)}   # Hayate's victim animation -> (state, Kim's animation for it)
POSES = json.load(open(os.path.join(HERE, 'victim_poses_kz.json')))['poses']
KIM_POSE = {'grabbed': (0x24, 3), 'curled': (0x32, 2), 'inverted': (0x32, 2), 'horizontal': (0x32, 2),
            'falling': (0x32, 2), 'lying': (0x2B, 5)}    # Kim's own (feet-centred) frame for each posture he is thrown in

def vcentre(n, k):
    """Kim's frame of animation n step k drawn facing right at x 0: (centre x, height of its lowest pixel)"""
    img = np.zeros((H, W), np.uint16); kz.render_step(img, kz.parse_anim(0x5000 | n)[k]['addr'], X0, Y0)
    ys, xs = np.nonzero(img)
    return (xs.min() + xs.max()) / 2 - X0, Y0 - 1 - ys.max()

def throw(B, cap):
    """Kim's throw (6C, $6F) in export96's throw layout: per frame from the grab to the victim's landing, the thrower
    [frame, dx, dy, turned] and the victim [Kim's frame for the posture, x forward, height, same facing, in front, key]"""
    fr = cap['throw_fc']['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == 0x6F)
    e = next(i for i in range(s0, len(fr)) if fr[i][1][0] == 0xDE and fr[i][1][1] == 1) + 1
    x0 = fr[s0][0][2]
    timeline, rows, steps = [], [], []
    for i in range(s0, e):
        a, b = fr[i][0], fr[i][1]
        fi = B.frame(a[5])
        timeline.append([fi, sc(a[2] - x0), sc(a[3]), a[4]])
        if a[0] == 0x6F and (not steps or steps[-1][0] != a[5]): steps.append([a[5], 0])
        if a[0] == 0x6F: steps[-1][1] += 1
        st, kn = VSTATE[b[0]]
        key = f'{st:X}.{b[1]}'
        cx, bot = vcentre(kn, b[1])
        vn, vk = KIM_POSE[POSES[key][0]]
        vf = B.frame(kz.parse_anim(0x5000 | vn)[vk]['addr'])
        rows.append([vf, sc(b[2] - a[2] - cx), sc(b[3] + bot), 0, 0, key])
    anim = {'slot': 0x6F, 'mode': 'hold', 'steps': [step(B, ad, n, step_boxes(ad)) for ad, n in steps]}
    return {'slot': 0x6F, 'inputs': '6C / 4C (close)', 'table': [], 'hold': False, 'timeline': timeline,
            'victims': {'kim': rows}, 'impacts': [], 'anim': anim}

def rom_palette(n): return [kz.u16(0x70000 + 32 * n + 2 * i) for i in range(16)]

def export(names, outdir, only=None, extra=None):
    cap = json.load(open(CAPTURE))
    B = Builder(); out = {'game': 'kizuna', 'tile_base': TILE_BASE, 'characters': {}}
    for name in names:
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
        th = throw(B, cap)
        anims['throw_c'] = th.pop('anim')
        sps = [special(B, inp, cap) for inp in SPECIALS]
        sets = [[[0] + rom_palette(s + p - 16)[1:] for p in B.pals] for s in SETS]
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
