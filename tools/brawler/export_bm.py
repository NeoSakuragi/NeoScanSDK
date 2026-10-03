#!/usr/bin/env python3
"""Brawler fighter data: a beat 'em up subset of each fighter's animations from the KOF dictionaries
(tools/kof96/export96.py, any of KOF96/98/99), written as const 68000 tables + the C1/C2 tiles they use.

    python3 export_bm.py OUTDIR kof98:terry kof98:kyo ...        -> bm_chars.c/.h, bm_c1.bin, bm_c2.bin

Per fighter: frames (parts: dx, dy, columns, rows, flips, palette index, tile columns), animations (steps: frame, ticks,
one hurt box = union of KOF's hurt boxes, the attack box when the step has one), every colour set (16-colour palettes,
one per palette index), physics (16.16 px/frame). Boxes are KOF's: centre offset from the feet (y < 0 = up) and half
extents, in the sprites' own orientation (ROM sprites face LEFT: mirror x when the fighter faces right).
Tile numbers start at TILE_BASE (1-1023 hold the stage, make_stage.py)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export96

# the brawler's animation set (KOF move names); MOVES order = the BA_* enum
MOVES = ['idle', 'walk_fwd', 'run', 'prejump', 'jump_up_rise', 'jump_up_fall', 'jump_fwd_rise', 'jump_fwd_fall', 'land',
         'atk_a_close', 'atk_a_far', 'atk_b_close', 'atk_b_far', 'atk_c_close', 'atk_c_far', 'atk_d_close', 'atk_d_far',
         'atk_d_crouch', 'atk_c_jump', 'atk_d_jump', 'body_toss', 'hit_stand_light', 'hit_stand_heavy', 'hit_air',
         'blowback', 'knockdown_flight', 'knockdown_bounce', 'knockdown_fall', 'down', 'getup', 'trip', 'win_a', 'atk_c_crouch']
TILE_BASE = 1024                               # our first fighter tile; 1-1023 hold the stage (make_stage.py), 0 empty
SRC_BASE = export96.TILE_BASE                  # export96 numbers its tiles from here

def sb(v): return v - 256 if v > 127 else v

REACH = 96                                     # px: every normal reaches at least this far forward (beat 'em up)

def boxes(bx, reach=0):
    """KOF step boxes -> (hurt union, attack) as (x, y, w, h) or None; reach: minimum forward reach of the attack box"""
    # KOF box key: the first hex digit is the type, 3 = hurt ('31'-'33', in every animation), 1 = attack ('11', '1B'-'1E',
    # only in attack animations; KOF96/98/99 census 2026-10-03). The second digit is not a slot: close A's attack box
    # is '1C', close C's / close D's '1D' (the old low-2-bits rule read '1D' as a hurt box: no C / D normal ever hit).
    # KOF99 '1B' = armor (it absorbs hits; only Maxima's C / D normals and C+D carry it): not an attack. KOF99 itself,
    # measured in our emulator: Maxima's close C hits twice (life 101 -> 90 at frames 132 and 150), not three times.
    hurt = [v for k, v in bx.items() if int(k, 16) >> 4 in (3, 4)]   # KOF94/95 hurt: 3x and 4x
    atk = [v for k, v in bx.items() if int(k, 16) >> 4 == 1 and k.upper() != '1B']
    def norm(b): return sb(b[0]), sb(b[1]), b[2], b[3]
    h = None
    if hurt:
        l = min(sb(b[0]) - b[2] for b in hurt); r = max(sb(b[0]) + b[2] for b in hurt)
        t = min(sb(b[1]) - b[3] for b in hurt); bt = max(sb(b[1]) + b[3] for b in hurt)
        h = ((l + r) // 2, (t + bt) // 2, (r - l + 1) // 2, (bt - t + 1) // 2)
    a = None
    if atk:
        # Beat 'em up reach: the attack covers everything from the body line (x = 0) to its tip, so far normals still
        # land point blank inside a combo. Forward = negative x (ROM sprites face left); the vertical extent is kept.
        # Normals also reach at least `reach` px forward, the same for every hit of a route: KOF's boxes are made for one
        # opponent in front, so an enemy standing behind it was only reached by the longer hits and dropped out.
        x, y, w, hh = norm(atk[0])
        left, right = min(x - w, -reach), x + w
        if left < 0: right = max(right, 0)
        a = ((left + right) // 2, y, (right - left + 1) // 2, hh)
    return h, a

THROWS = ['throw_c', 'throw_d']                         # BT_* order: ground throws, close, forward+C / forward+D in KOF

def build(specs, outdir):
    """one export per game (the whole roster of that game at once, so every fighter has the frames of every victim
    posture its teammates' throws use); tiles renumbered into one space"""
    os.makedirs(outdir, exist_ok=True)
    games = {}
    for spec in specs:
        game, name = spec.split(':'); games.setdefault(game, []).append(name)
    chars, c1, c2 = [], bytearray(), bytearray()
    tile_next = TILE_BASE
    for game, names in games.items():
        tmp = os.path.join(outdir, 'tmp_' + game)
        if game == 'kof94':                             # KOF95's engine: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'kof94')); import export94
            ex = export94.export(names, tmp, only=set(MOVES))
        else: ex = export96.export(names, tmp, game, only=set(MOVES) | set(THROWS) | {'specials'})
        a = open(os.path.join(tmp, 'kof95_c1.bin'), 'rb').read(); b = open(os.path.join(tmp, 'kof95_c2.bin'), 'rb').read()
        n = ex['tiles']
        assert n < 0x10000, f'{game}: {n} tiles in one block (a block must fit one 64K tile page after its blank tile)'
        if tile_next >> 16 != (tile_next + n - 1) >> 16:    # keep a block inside one 64K page: its fighters' tile numbers
            gap = ((tile_next >> 16) + 1 << 16) - tile_next  # then share bits 16-19 (bchar_t.tile_hi -> SCB1 attribute)
            c1 += bytes(gap * 64); c2 += bytes(gap * 64); tile_next += gap
        if tile_next & 0xFFFF == 0:                     # tile 0 = empty, and with tile_hi it means page start: blank
            c1 += bytes(64); c2 += bytes(64); tile_next += 1
        c1 += a[SRC_BASE * 64:(SRC_BASE + n) * 64]; c2 += b[SRC_BASE * 64:(SRC_BASE + n) * 64]
        off = tile_next - SRC_BASE; tile_next += n
        chars += [(game, name, ex['characters'][name], off) for name in names]
    assert tile_next <= 0x100000, f'{tile_next} tiles: past the 20-bit tile number'
    pad = bytearray(TILE_BASE * 64)
    open(os.path.join(outdir, 'bm_c1.bin'), 'wb').write(bytes(pad + c1))
    open(os.path.join(outdir, 'bm_c2.bin'), 'wb').write(bytes(pad + c2))
    write_c(chars, outdir)
    return chars, tile_next

# Specials by role (Bruno 2026-10-03): D = a projectile, forward+D = a move travelling forward (Terry's Burn Knuckle),
# down+D = a rising invincible reversal (dragon punch, Rising Tackle...). Picked from each fighter's captured ground
# specials by what its body does (tools/kof96/specials96.py scripts: per row frame, x forward, height, objects):
# projectile = objects while the body stays put (x <= 45, height <= 10; a capture often ends before the object flies,
# so its travel is no criterion), rush = body forward >= 60 px staying low (height <= 30; scored travel - 2 x height: Terry's Burn
# Knuckle, not his Crack Shoot), rise = height >= 25, scored
# height - travel / 2. Big versions (C / D) first. ROLE_OVERRIDE: KOF input notation per fighter and role.
ROLE_OVERRIDE = {'mai': {'rise': '623D'},       # Mai: [2]8A is a wall-jump dive, not a reversal
                 'terry': {'up': '214D'},        # Crack Shoot
                 'kyo': {'up': 'EX 624D'}}       # EX Kyo's triple kick
ROLES = ('proj', 'rush', 'rise', 'up')

def special_shape(sp):
    sc = sp['script']
    return max(r[1] for r in sc), max(r[2] for r in sc), any(r[3] for r in sc)

def pick_specials(ch, name=None):
    """[projectile, rush, rise, up] (None where the fighter has no such move). The big versions first (C / D: Bruno
    2026-10-03, the long Burn Knuckle, the high dragon punch); up+D = the best special of a move not used yet (one move
    = its input motion with the punch or kick pair: 214A / 214C is one move, 214B / 214D another)."""
    c = [sp for sp in ch.get('specials', []) if sp['condition'] == 'normal' and not sp['input'].startswith('air')]
    auto = [sp for sp in c if not sp['input'].split()[0] in ('EX', 'MAX', 'Counter')]   # supers / EX: by override only
    big = lambda sp: sp['input'][-1:] in ('C', 'D')
    move = lambda sp: (sp['input'].rstrip('ABCD'), sp['input'][-1:] in ('A', 'C'))
    out = []
    for role in ROLES:
        want = ROLE_OVERRIDE.get(name, {}).get(role)
        pick = next((sp for sp in c if sp['input'] == want), None) if want else None
        if pick is None:
            c_all, c = c, [sp for sp in auto if sp not in out]
            if role == 'proj': cand = [(0, sp) for sp in c if special_shape(sp)[2] and special_shape(sp)[0] <= 45 and special_shape(sp)[1] <= 10]
            elif role == 'rush': cand = [(special_shape(sp)[0] - 2 * special_shape(sp)[1], sp) for sp in c if special_shape(sp)[0] >= 60 and special_shape(sp)[1] <= 30]
            elif role == 'rise': cand = [(special_shape(sp)[1] - special_shape(sp)[0] / 2, sp) for sp in c if special_shape(sp)[1] >= 25]
            else:
                used = {move(sp) for sp in out if sp}
                cand = [(0, sp) for sp in c if move(sp) not in used]
            cand.sort(key=lambda t: (not big(t[1]), -t[0]))
            pick = cand[0][1] if cand else None
            c = c_all
        out.append(pick)
    return out

# Throw impacts (Bruno 2026-10-03): the moment a throw's blow lands (Terry's punch, Ralf's headbutt), else the moment the
# victim touches the ground. From the victim's KOF states in the captured script (KOF96-99 numbering): a strike = the
# victim entering a hit reaction (416-418, 426, 427) or a launch (283) straight from being held (424, 425, 432, 433) or
# from the previous blow (multi-hit throws: one impact per blow); no strike = the first ground touch after it was in the
# air (height back to 0, or state 309, the floor bounce).
HELD = {424, 425, 432, 433}
STRIKE = {416, 417, 418, 426, 427}

def throw_impacts(rows, game):
    if game not in ('kof96', 'kof97', 'kof98', 'kof99'): return []
    st = lambda r: int(r[5].split('.')[0]) if r[5] else -1
    out = []; prev = None
    for i, r in enumerate(rows):
        s = st(r)
        if prev is not None and s != prev and prev in HELD | STRIKE and (s in STRIKE or (s == 283 and prev in HELD)):
            out.append(i)
        prev = s
    if out: return out
    air = False
    for i, r in enumerate(rows):
        if r[2] >= 16: air = True
        if air and (r[2] <= 0 or st(r) == 309): return [i]
    return []

def frame_box(fr):
    """bounding box of a frame's sprites, as a KOF box (centre from the origin, half extents, sprite orientation)"""
    xs, ys = [], []
    for p in fr['parts']:
        w, h = len(p['tiles']) * 16, len(p['tiles'][0]) * 16
        x0 = -p['dx'] - w if p['hflip'] else p['dx']; y0 = -p['dy'] - h if p['vflip'] else p['dy']
        xs += [x0, x0 + w]; ys += [y0, y0 + h]
    if not xs: return None
    cl = lambda v: max(-128, min(127, v))
    return (cl((min(xs) + max(xs)) // 2), cl((min(ys) + max(ys)) // 2), min(255, (max(xs) - min(xs)) // 2), min(255, (max(ys) - min(ys)) // 2))

VICTIM_POSES = {g: json.load(open(os.path.join(HERE, '..', 'kof96', f'victim_poses{g[3:]}.json')))['poses']
                for g in ('kof96', 'kof98', 'kof99')}

FAMILY = {'grabbed': 'standing', 'hunched': 'standing', 'hit_reel': 'standing', 'bent_back': 'standing', 'standing': 'standing',
          'launched': 'air', 'horizontal': 'air', 'curled': 'air',
          'falling': 'head_down', 'inverted': 'head_down', 'inverted_diagonal': 'head_down', 'lying': 'floor'}

FALLBACK_MOVE = {'standing': 'hit_stand_heavy', 'air': 'blowback', 'head_down': 'knockdown_fall', 'floor': 'down'}

def vocab(game, key):
    """a victim 'state.step' of a game -> its portable posture name 'posture:angle' (tools/kof96/victim_poses*.json):
    state numbers differ between games (KOF99 re-uses 432 for a launched pose, a grabbed one in KOF98), postures don't"""
    p = VICTIM_POSES[game].get(key)
    return f'{p[0]}:{p[1]}' if p else None

def poses(chars):
    """victim postures (portable names) used by any throw, and each fighter's frame for them, taken from the throws of
    its own game that have it as the victim. A posture it has no frame for takes its frame for the same posture at the
    nearest angle, else the nearest angle of the same family (FAMILY), else the family's brawler animation
    (FALLBACK_MOVE: heavy hit, blowback, knockdown fall, down)."""
    keys = sorted({vocab(g, r[5]) for g, _, ch, _ in chars for t in ch.get('throws', {}).values()
                   for rows in t['victims'].values() for r in rows if r[0] >= 0 and vocab(g, r[5])})
    table = {}
    for gv, n, chv, _ in chars:
        m = {}
        for g, _, ch, _ in chars:
            if g != gv: continue
            for t in ch.get('throws', {}).values():
                for r in t['victims'].get(n, []):
                    v = vocab(g, r[5])
                    if r[0] >= 0 and v: m.setdefault(v, r[0])
        row = []
        for k in keys:
            if k in m: row.append(m[k]); continue
            post, ang = k.rsplit(':', 1)
            near = [(abs(int(a) - int(ang)), f) for v, f in m.items() for p_, a in [v.rsplit(':', 1)] if p_ == post] or \
                   [(abs(int(a) - int(ang)), f) for v, f in m.items() for p_, a in [v.rsplit(':', 1)]
                    if FAMILY.get(p_) == FAMILY.get(post)]
            if not near:                                 # nothing in its throws: the family's brawler animation
                a = chv['anims'].get(FALLBACK_MOVE[FAMILY.get(post, 'standing')])
                near = [(0, a['steps'][-1]['frame'])] if a else []
            row.append(min(near)[1] if near else -1)
        table[n] = row
    return keys, table

def write_c(chars, outdir):
    pkeys, ptable = poses(chars)
    h = ['/* Generated by tools/brawler/export_bm.py from the KOF dictionaries. Do not edit. */',
         '#ifndef BM_CHARS_H\n#define BM_CHARS_H\n#include <stdint.h>\n',
         'typedef struct { int16_t dx, dy; uint8_t cols, rows, hflip, vflip, pal; const uint16_t *tiles; } bpart_t;   /* tiles: cols*rows column-major, 0 = empty; pal: palette index of the fighter */',
         'typedef struct { uint8_t nparts, ncols; const bpart_t *parts; } bframe_t;   /* ncols: hardware sprites the frame uses */',
         'typedef struct { int8_t x, y; uint8_t w, h; } bbox_t;                       /* centre from the feet (y<0 up), half extents; sprite faces left */',
         'typedef struct { uint16_t frame; uint8_t ticks, flags; bbox_t hurt, atk; int8_t dx, pad; } bstep_t;   /* flags: 1 = attack box, 2 = hurt box, 4 = opens a new hit (multi-hit normals); dx: px the fighter moves forward as the step starts (KOF\'s $FB move) */',
         'typedef struct { uint8_t nsteps, hold; const bstep_t *steps; } banim_t;     /* hold: stop on the last step */',
         'typedef struct { int32_t walk, jump_vy0, gravity, jump_dx; } bphys_t;     /* 16.16 px per frame */',
         'typedef struct { uint16_t tframe; int16_t tx, ty; uint8_t vpose, flags; int16_t vx, vy; } bthrow_row_t;   /* one video frame: thrower frame + offset from its start (forward +, up +); victim posture (0xFF: none) + offset from the thrower; flags 1 = victim faces the thrower\'s way, 2 = victim drawn in front, 4 = impact (the blow lands / the victim hits the floor) */',
         'typedef struct { uint16_t nrows; const bthrow_row_t *rows; } bthrow_t;',
         'typedef struct { uint16_t frame; int16_t x, y; uint8_t same, pad; bbox_t box; } bsobj_t;   /* special\'s object (projectile): frame (0xFFFF = none), offset from the fighter\'s start, faces the fighter\'s way, sprite bounds as its attack box */',
         'typedef struct { uint16_t frame; int16_t x, y; bbox_t atk; uint8_t hit, pad; bsobj_t obj[2]; } bspec_row_t;   /* one video frame of a special: fighter frame + offset from its start (forward +, up +), body attack box when hit */',
         'typedef struct { uint16_t nrows, inv_rows; const bspec_row_t *rows; } bspec_t;   /* inv_rows: invincible for its first rows */',
         'typedef struct { const char *name; uint8_t npal, nsets; const uint16_t *pals; const bframe_t *frames; const banim_t *anims; bphys_t phys; const bthrow_t *throws; const uint16_t *vposes; const bspec_t *specials; uint8_t tile_hi; } bchar_t;   /* pals: nsets * npal * 16 colours; throws: BT_COUNT (nrows 0 = none); vposes: VP_COUNT frames (0xFFFF = none); specials: BS_COUNT (D projectile, forward+D rush, down+D rising reversal, up+D another; nrows 0 = none); tile_hi: tile number bits 16-19 of all its tiles */\n',
         'enum { ' + ', '.join(f'BA_{m.upper()}' for m in MOVES) + ', BA_COUNT };',
         'enum { ' + ', '.join(f'BC_{n.upper()}' for _, n, _, _ in chars) + ', BC_COUNT };',
         'enum { ' + ', '.join(f'BT_{t.upper()}' for t in THROWS) + ', BT_COUNT };',
         'enum { BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_COUNT };',
         f'enum {{ VP_COUNT = {len(pkeys)} }};   /* victim postures: ' + ' '.join(pkeys) + ' */',
         'extern const bchar_t bm_chars[BC_COUNT];\n#endif']
    c = ['/* Generated by tools/brawler/export_bm.py. Do not edit. */\n#include "bm_chars.h"\n']
    fx = lambda v: str(int(round(v * 65536)))
    def bb(b): return '{0, 0, 0, 0}' if b is None else f'{{{b[0]}, {b[1]}, {b[2]}, {b[3]}}}'
    used = {}                                            # palettes the exported frames use, renumbered 0..k-1
    for game, n, ch, off in chars:
        used[n] = sorted({p.get('pal', 0) for fr in ch['frames'] for p in fr['parts']}) or [0]
        sets = ch['block_palettes']
        c.append(f'static const uint16_t {n}_pals[] = {{' + ', '.join(f'0x{v:04X}' for st in sets for k in used[n] for v in st[k]) + '};')
        for fi, fr in enumerate(ch['frames']):
            for pi, p in enumerate(fr['parts']):
                assert len(p['tiles'][0]) <= 32, f'{n} frame {fi}: {len(p["tiles"][0])} rows (SCB3 height and draw.s stop at 32)'
                flat = [(t + off) & 0xFFFF if t else 0 for col in p['tiles'] for t in col]   # low 16 bits; tile_hi has 16-19
                c.append(f'static const uint16_t {n}_f{fi}_p{pi}[] = {{' + ', '.join(map(str, flat)) + '};')
            c.append(f'static const bpart_t {n}_f{fi}[] = {{' + ', '.join(
                f'{{{p["dx"]}, {p["dy"]}, {len(p["tiles"])}, {len(p["tiles"][0])}, {p["hflip"]}, {p["vflip"]}, {used[n].index(p.get("pal", 0))}, {n}_f{fi}_p{pi}}}'
                for pi, p in enumerate(fr['parts'])) + '};' if fr['parts'] else f'static const bpart_t {n}_f{fi}[1];')
        c.append(f'static const bframe_t {n}_frames[] = {{' + ', '.join(
            f'{{{len(fr["parts"])}, {sum(len(p["tiles"]) for p in fr["parts"])}, {n}_f{fi}}}' for fi, fr in enumerate(ch['frames'])) + '};')
        for m in MOVES:
            a = ch['anims'].get(m) or ch['anims']['idle']
            steps, live, prev_act, prev_chain = [], None, False, False
            for s in a['steps']:
                hb, ab = boxes(s['boxes'], REACH)
                # KOF step flags: $0100 = attack active (the last attack box stays live on every active step, a box command
                # only comes when it changes), $4000 = the next active step continues this hit. An active step after an
                # inactive one, or after one without $4000, opens a new hit: Terry / Chang close C, Yamazaki close D hit
                # twice (KOF98 measured: 52 of 54 normals match the rule; Billy's staff close D hits twice, rule says once)
                fl = s.get('flags', 0); act = bool(fl & 0x100)
                if ab: live = ab
                elif act: ab = live
                new = ab is not None and not (prev_act and prev_chain)
                prev_act, prev_chain = ab is not None, bool(fl & 0x4000)
                fwd = -s.get('dx', 0); assert -128 <= fwd <= 127, (n, m, fwd)   # KOF x: negative = forward
                steps.append(f'{{{s["frame"]}, {s["ticks"]}, {(1 if ab else 0) | (2 if hb else 0) | (4 if new else 0)}, {bb(hb)}, {bb(ab)}, {fwd}, 0}}')
            c.append(f'static const bstep_t {n}_{m}[] = {{' + ', '.join(steps) + '};')
        for t in THROWS:
            th = ch.get('throws', {}).get(t)
            if not th: continue
            rows = th['victims'].get(n) or next(iter(th['victims'].values()))   # offsets of the mirror match (see README)
            out = []; imp = set(throw_impacts(rows, game))
            for i, (tf, tx, ty) in enumerate(th['timeline']):
                vf, vx, vy, same, front, key = rows[min(i, len(rows) - 1)]
                v = vocab(game, key)
                vp = pkeys.index(v) if vf >= 0 and v in pkeys else 255
                out.append(f'{{{tf if tf >= 0 else 0}, {tx}, {ty}, {vp}, {same | front << 1 | (4 if i in imp else 0)}, {vx}, {vy}}}')
            c.append(f'static const bthrow_row_t {n}_{t}[] = {{' + ', '.join(out) + '};')
        c.append(f'static const bthrow_t {n}_throws[BT_COUNT] = {{' + ', '.join(
            f'{{{len(ch["throws"][t]["timeline"])}, {n}_{t}}}' if t in ch.get('throws', {}) else '{0, 0}' for t in THROWS) + '};')
        sps = pick_specials(ch, n)
        for k, sp in enumerate(sps):
            if sp is None: continue
            out = []
            for f, x, hgt, objs in sp['script']:
                hb, ab = boxes(sp['frame_boxes'].get(f, sp['frame_boxes'].get(str(f), {})))
                ob = []
                for of, ox, oh, same in objs[:2]:
                    b = frame_box(ch['frames'][of]) or (0, 0, 0, 0)
                    ob.append(f'{{{of}, {ox}, {oh}, {same}, 0, {bb(b)}}}')
                ob += ['{0xFFFF, 0, 0, 0, 0, {0, 0, 0, 0}}'] * (2 - len(ob))
                out.append(f'{{{f}, {x}, {hgt}, {bb(ab)}, {1 if ab else 0}, 0, {{{", ".join(ob)}}}}}')
            c.append(f'static const bspec_row_t {n}_sp{k}[] = {{' + ', '.join(out) + '};')
        def inv_rows(sp, k):                             # the rising reversal: invincible through its last hit row
            if ROLES[k] != 'rise': return 0                     # or its apex
            hits = [i for i, r in enumerate(sp['script']) if boxes(sp['frame_boxes'].get(r[0], {}))[1]]
            peak = max(range(len(sp['script'])), key=lambda i: sp['script'][i][2])   # a rising move: to its apex
            return max(hits[-1] + 1 if hits else 0, peak + 1 if sp['script'][peak][2] > 0 else 0) or len(sp['script'])
        c.append(f'static const bspec_t {n}_specials[BS_COUNT] = {{' + ', '.join(
            f'{{{len(sp["script"])}, {inv_rows(sp, k)}, {n}_sp{k}}}' if sp else '{0, 0, 0}' for k, sp in enumerate(sps)) + '};')
        c.append(f'static const uint16_t {n}_vposes[VP_COUNT + 1] = {{' + ', '.join(str(v if v >= 0 else 0xFFFF) for v in ptable[n]) + ', 0xFFFF};')
        c.append(f'static const banim_t {n}_anims[BA_COUNT] = {{' + ', '.join(
            f'{{{len((ch["anims"].get(m) or ch["anims"]["idle"])["steps"])}, {1 if (ch["anims"].get(m) or ch["anims"]["idle"])["mode"] == "hold" else 0}, {n}_{m}}}' for m in MOVES) + '};')
    c.append('const bchar_t bm_chars[BC_COUNT] = {')
    for game, n, ch, off in chars:
        p = ch['physics']; sets = ch['block_palettes']
        c.append(f'  {{"{n.upper()}", {len(used[n])}, {len(sets)}, {n}_pals, {n}_frames, {n}_anims, {{{fx(p["walk_fwd"])}, {fx(p["jump_vy0"])}, {fx(p["gravity"])}, {fx(p["jump_dx"])}}}, {n}_throws, {n}_vposes, {n}_specials, {(off + SRC_BASE) >> 16}}},')
    c.append('};')
    open(os.path.join(outdir, 'bm_chars.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(outdir, 'bm_chars.c'), 'w').write('\n'.join(c) + '\n')

if __name__ == '__main__':
    outdir = sys.argv[1]; specs = sys.argv[2:] or ['kof98:terry']
    chars, tiles = build(specs, outdir)
    for game, n, ch, off in chars:
        print(f'{game}:{n}: specials ' + ', '.join(f'{k} {sp["input"] if sp else "-"}' for k, sp in zip(('D', 'fwd+D', 'down+D', 'up+D'), pick_specials(ch, n))) + ';', end=' ')
        print(f'{len(ch["frames"])} frames, {len([m for m in MOVES if m in ch["anims"]])}/{len(MOVES)} moves, '
              f'{len(ch["block_palettes"])} colour sets, max cols '
              f'{max(sum(len(p["tiles"]) for p in f["parts"]) for f in ch["frames"])}')
    print('tiles', tiles - TILE_BASE, f'({(tiles - TILE_BASE) * 128 // 1024} KB)')
