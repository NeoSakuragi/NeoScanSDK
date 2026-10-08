#!/usr/bin/env python3
"""Double Dragon (Technos 1995): the normal throws, read in the 68000 code (TODO #194), as the brawler's paired scripts.

    python3 throw_dd.py check [OUT.json]   the scripts against the game (captures in our emulator), every form /
                                           button / direction -> /data/neogeo_dict/doubledr/throw194.json

The command [code] (/data/tmp/dd95/p1.dis): a button press ($2033E: d0 = A 0 .. D 3, + $8000 when the stick holds left
or right, either way) goes through $2380E; with the stick bit and the opponent throwable ($23876-$238FA: not in a hit
reaction 50-80 but 76, both on the ground or both airborne) $239F0 measures the gap between the two first box records
(edge to edge, x: d3, y: d2) and, when the opponent's record is a body box (type bit 6), $23A76 reads the THROW TABLE
$23C2A + 48 x character, four words per button (A..D) per field:
   +$00 range (gap < range; bit 15: also in the air, the gap y < 32 then)   +$08 the thrower's animation (0 = none;
   bit 15: the victim is first placed by +$18 / +$20)   +$10 the VICTIM's animation, in its own character's table (bit 15:
   the stick picks the direction: not holding toward the facing side turns the thrower around = the back throw, and the
   victim then faces the thrower's way; clear: face to face)   +$18 -> victim +$3E (the placement row, below)
   +$20 -> thrower +$3E   +$28 -> thrower +$FA = the throw's damage (word, of 26624).
Billy (0) and the transformed Billy (1): A none; B / C / D = ranges 10 / 8 / 6 px, thrower animations 110 / 111 / 112
(the same four definitions, steps 10 / 8|7|6 / 8|7|6 / 12 frames, his voice $1F / $20 / $21 on step 2, $CC on step 3),
victim animations 113 / 114 / 115 (bit 15: forward or back by the stick), placement row 0, damage $1000 / $1200 / $1400
(transformed $1200 / $1400 / $1600).
The victim [code] (every character's 113-115 have the same header: handler 13, flags $82, vx -5 / -6 / -7, vy 0 / 2 / 4,
gravity 0.375, next 71; steps: 3 thrown poses of 2 frames, then the flight pose twice): handler 13 ($21AF0) each frame
copies the THROWER's step (+$1E) to the victim, clears its tick counter and places it at the thrower + the row's
offset (table $21B76 + 16 x victim +$3E + 4 x step: [dx w][dy w]; x negated when the victim faces right, y up): row 0 =
(40, 0) (56, 40) (-16, 56) (-56, 64): the victim, facing the thrower's way, is pulled behind him (the thrower's frames
are drawn turned), swung over his head and dropped in front. Its step 3 lasts one frame, so on the thrower's step 3 the
victim's own clock reaches step 4 (attr bit 2): the RELEASE ($21AF8): +$F3 bit 4 cleared, the damage ($21E50, from the
thrower's +$FA), then handler 2's flight from $20FD6: the header velocity once (vx forward in the victim's facing), then
vy -= 0.375 before each move; landed (height < -1) -> animation 71 (the bounce, handler 2), 73 lying, 75 the get-up.
Measured [meas] (cap_dd, vs state, P1 Billy walks into Jimmy, forward / back + B / C / D): every row's victim step,
place and height = the script's; damage on the release's frame + 1. Not modelled: DD's global 17-frame pause with the
dragon effect (sound $D6) after the forward throw's release and at the thrower's end (absent from the back throw), as
TODO #192 for the super.

Brawler (#146 standard throw): throw_c = forward + A = DD's forward C throw (animation 111 / victim 114), throw_d = back
+ A = DD's back C throw (the thrower turned: row flag 8, offsets mirrored, the victim facing him). Rows: the thrower's
steps with DD's start-frame clock (the first step shows its ticks, the others ticks + 1: the recogniser starts the
animation in the frame the clock runs); impacts = the release (DD's damage frame) and the landing; control return =
the thrower's animation end (35 rows, DD's own: he acts again while the victim still flies); release = the damage row,
land = the floor touch; after it the victim plays the brawler's knockdown bounce (DD's 71 heights) then lies (73).
The hold (the brawler's walk-in grab, before forward / back + A): DD has none; its throw starts with the victim pulled
behind the turned thrower, so the hold is that first picture mirrored (bthrow_t.gframe = step 0 unturned, the victim in
front facing him: SS2's rule, TODO #188 a); forward + A then plays DD's throw from its first row."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dd, model_dd as M

TABLE, PLACE = 0x23C2A, 0x21B76
GRAVITY = 0.375                                   # (b6 & $F0) << 8 of the victim header ($6000 / 65536)
BUTTONS = 'ABCD'
OUT = '/data/neogeo_dict/doubledr/throw194.json'
VICTIM_REF = 0                                    # the victim animations' character for the poses / flight (every
                                                  # character's 113-115 share the header; Billy's frames name the poses)

def table(ch):
    """the throw table entry of a character: per button {range, air, thrower, placed, victim, by_stick, vrow, t3e, damage}"""
    a = TABLE + 48 * ch; out = {}
    for k, b in enumerate(BUTTONS):
        w = [dd.u16(a + f + 2 * k) for f in range(0, 48, 8)]
        if not w[1]: continue
        out[b] = {'range': w[0] & 0x7FFF, 'air': bool(w[0] & 0x8000), 'thrower': w[1] & 0x7FFF, 'placed': bool(w[1] & 0x8000),
                  'victim': w[2] & 0x7FFF, 'by_stick': bool(w[2] & 0x8000), 'vrow': w[3] & 0x7FFF, 't3e': w[4], 'damage': w[5]}
    return out

def place_row(vrow, step):
    """the victim's offset on the thrower's step (handler 13, $21B26): (dx, dy) px, dx toward the victim's back side
    (negated when it faces right: x = thrower x - dx x facing), dy up; None = not placed (a zero long)"""
    a = PLACE + 16 * vrow + 4 * step
    if not dd.u32(a): return None
    return dd.s16(a), dd.s16(a + 2)

def script(ch, button='C', back=False, vch=VICTIM_REF):
    """the throw as frames of the grab facing (+1 = the thrower's facing when the button was pressed): per row the
    thrower's (animation, step), and the victim's (animation, step, def, x forward of the thrower, height, faces the grab
    facing); events: release / impact / land. Read from the code above, the victim's flight from its header."""
    e = table(ch)[button]
    _, tst = dd.steps(ch, e['thrower'])
    vhdr, vst = dd.steps(vch, e['victim'])        # (the victim's own table: 113's vx is -5 or -3 by character)
    F = -1 if back else 1                         # the thrower's facing after the stick test, in grab terms
    V = F                                         # by_stick: the victim faces the thrower's way
    tl = []
    for i, s in enumerate(tst): tl += [i] * (s['ticks'] + (0 if i == 0 else 1))   # DD's start-frame clock
    rows = []; vstep = 0; x = y = 0.0; vx = vy = 0.0; rel = land = None; free = False
    vxh = -int.from_bytes(vhdr[2:4], 'big', signed=True) / 256; vyh = int.from_bytes(vhdr[4:6], 'big', signed=True) / 256
    T = lambda i: tl[min(i, len(tl) - 1)]
    i = 0
    while True:
        ev = []; a = e['victim']
        if not free and vst[vstep]['attr'] & 4 and rows:   # its clock reached the release step last frame: released now
            free = True; rel = i; ev += ['release', 'impact']; vx, vy = vxh * V, vyh
        if not free:
            vstep = T(i)                          # the thrower's step, the row's offset (x forward of the thrower in
            p = place_row(e['vrow'], vstep)       # grab terms: -dx x the victim's facing)
            if p: x, y = -p[0] * V, p[1]
        else:
            vy -= GRAVITY; x += vx; y += vy       # (the release frame moves too: vy0 - g, measured)
            if y <= -1: y = 0; land = i; ev += ['land', 'impact']; a, vstep = 71, 0
        rows.append(dict(t=[e['thrower'], T(i)], v=[a, vstep, dd.steps(vch, a)[1][vstep]['def_']], x=x, y=y, ev=ev))
        i += 1
        if land is not None: break
        if not free and vst[vstep]['ticks'] == 0 and vstep + 1 < len(vst):
            vstep += 1                            # a one-frame step: its own clock shows the next step at this place
            if vst[vstep]['attr'] & 4:
                rows.append(dict(t=[e['thrower'], T(i)], v=[a, vstep, vst[vstep]['def_']], x=x, y=y, ev=[])); i += 1
        assert i < 400
    # after the landing: DD's 71 (the bounce, handler 2 from the floor) then 73 (lying), the model's heights
    o = M.Obj(vch, 71); bounce = []
    for _ in range(200):
        r = M.frame(o)
        if r['anim'] != 71 or r['landed']: break
        bounce.append(r['y'])
    lie = sum(s['ticks'] + 1 for s in dd.steps(vch, 73)[1])
    return dict(button=button, back=back, entry=e, timeline=tl, rows=rows, release=rel, land=land, ret=len(tl),
                bounce=bounce, lie=lie, face=V)

# ---- the brawler's paired script (export_dd: characters[].throws) ------------------------------------------------------
# victim poses (export_bm.VICTIM_POSES['doubledr'], victim_poses_dd.json): keys 'anim.step' of the victim animations
THROWS = {'throw_c': ('C', False), 'throw_d': ('C', True)}     # forward + A / back + A: DD's C throw, forward / back

def brawler_throw(B, ch, key, mirror_frame, scale=1.0):
    """a throw for export_dd: B the frame builder (thrower frames 'body'), mirror_frame(def) -> the frame of that
    definition mirrored (the hold pose). Victim rows [frame of Billy's own pose (poses()), x, y, same, front, key, role]"""
    button, back = THROWS[key]
    s = script(ch, button, back)
    _, tst = dd.steps(ch, s['entry']['thrower'])
    th_steps = [{'frame': B.frame(((t['def_'], 0, 0, 'body'),)), 'ticks': t['ticks'], 'flags': 0, 'dx': 0, 'boxes': {}, 'dd': [s['entry']['thrower'], i]}
                for i, t in enumerate(tst)]
    timeline = [[th_steps[k]['frame'], 0, 0, 1 if back else 0] for k in s['timeline']]
    _, vst = dd.steps(ch, s['entry']['victim'])   # its own frames as the victim of this throw (a mirror match: the
    vframe = lambda k: B.frame(((vst[k]['def_'], 0, 0, 'body'),))   # brawler's poses() names them for this fighter)
    same = 1 if s['face'] == 1 else 0
    rows, impacts = [], []
    for i, r in enumerate(s['rows']):
        a, k, _ = r['v']
        if 'impact' in r['ev']: impacts.append(i)
        if r['ev'] and 'land' in r['ev']: role = 'knockdown_bounce'
        else: role = None
        rows.append([vframe(k), round(r['x'] * scale), round(r['y'] * scale), same, 0, f'{a}.{k}', role])
    x_land = rows[-1][1]
    for h in s['bounce']:
        rows.append([-1, x_land, round(h * scale), same, 0, '71.0', 'knockdown_bounce'])
    rows += [[-1, x_land, 0, same, 0, '73.0', 'down'] for _ in range(s['lie'])]
    anim = {'slot': s['entry']['thrower'], 'mode': 'hold', 'steps': th_steps}
    g0 = mirror_frame(tst[0]['def_']) if key == 'throw_c' else None
    return {'slot': s['entry']['thrower'], 'inputs': ('back' if back else 'forward') + ' + A (DD: close, left / right + ' + button + ')',
            'table': [], 'hold': False, 'rom': True, 'timeline': timeline, 'victims': {}, 'victim_rows': rows,
            'impacts': sorted(set(impacts)), 'release': s['release'], 'land': s['land'], 'ret': s['ret'], 'anim': anim,
            'dd': {'thrower': s['entry']['thrower'], 'victim': s['entry']['victim'], 'button': button, 'back': back,
                   'damage': s['entry']['damage']},
            'grab_frame': g0}

# ---- Cheng-Fu's throw (TODO #212): the stun strike ------------------------------------------------------------------------
# His table row (character 10): B / C / D ranges 12 / 10 / 8, thrower 110 for every button (10 steps, 87 frames: the
# palm to the chest, his voice $3F on step 2, the dust blown off his fingers), victim 121 face to face (bit 15 clear),
# damage 0. $23A76's special case for a victim animation 121 ($23B74): the victim is NOT held (+$F3 bit 4 cleared; bits 2
# and 1 set), placed t3e = 48 px in front of the thrower, and its +$FE = the vrow field = 96 / 128 / 160 (B / C / D).
# 121 (every character's, handler 0): 52 frames stunned holding its chest (Billy's 984), then it staggers back bent
# (878-880, header vx 4.5 px with friction: 31 px), next 76 = the DIZZY animation (6 steps looping), which counts +$FE
# down one a frame and stands the victim up at 0: open to any hit meanwhile. Measured (cap_dd, Cheng-Fu C vs Jimmy):
# 121 from the press frame for 87 frames, x +31, 76 for 129 frames (+$FE 128 -> 0), no damage at any point.
# Brawler: throw_c (and back + A: DD has no back throw for him, by_stick clear) = the C row: the victim rows = 121 from
# the thrower's place (48 px + the stagger), postures '121.k' (victim_poses_dd.json); then bthrow_t.stun = 128 frames:
# fighter.c victim_end leaves the victim standing in its heavy reel, hittable (fighter_t.dizzy), no throw damage.
STUN_ANIM = 121

def is_stun(ch): return table(ch).get('C', {}).get('victim') == STUN_ANIM

def stun_script(ch, button='C', vch=VICTIM_REF):
    e = table(ch)[button]
    _, tst = dd.steps(ch, e['thrower'])
    tl = []
    for i, st_ in enumerate(tst): tl += [i] * (st_['ticks'] + (0 if i == 0 else 1))   # DD's start-frame clock
    rec = M.play(vch, STUN_ANIM, until=(0, 1, 2, 3, 76))
    rows = [dict(t=[e['thrower'], tl[min(i, len(tl) - 1)]], v=[STUN_ANIM, r['step'], r['def_']], x=e['t3e'] - r['x'], y=0.0, ev=[])
            for i, r in enumerate(rec)]
    return dict(button=button, back=False, entry=e, timeline=tl, rows=rows, release=None, land=None, ret=len(tl),
                stun=e['vrow'], face=-1)

def brawler_stun(B, ch, scale=1.0):
    """Cheng-Fu's stun strike as the brawler's paired script (export_dd: characters[].throws['throw_c'])"""
    s = stun_script(ch)
    _, tst = dd.steps(ch, s['entry']['thrower'])
    th_steps = [{'frame': B.frame(((t['def_'], 0, 0, 'body'),)), 'ticks': t['ticks'], 'flags': 0, 'dx': 0, 'boxes': {}, 'dd': [s['entry']['thrower'], i]}
                for i, t in enumerate(tst)]
    timeline = [[th_steps[k]['frame'], 0, 0, 0] for k in s['timeline']]
    _, vst = dd.steps(ch, STUN_ANIM)                  # (his own pictures as the victim: a mirror match)
    rows = [[B.frame(((vst[r['v'][1]]['def_'], 0, 0, 'body'),)), round(r['x'] * scale), 0, 0, 0, f"{STUN_ANIM}.{r['v'][1]}", None] for r in s['rows']]
    return {'slot': s['entry']['thrower'], 'inputs': 'forward / back + A (DD: close, left / right + C: the stun strike)',
            'table': [], 'hold': False, 'rom': True, 'timeline': timeline, 'victims': {}, 'victim_rows': rows,
            'impacts': [], 'release': None, 'land': None, 'ret': s['ret'], 'stun': s['stun'],
            'anim': {'slot': s['entry']['thrower'], 'mode': 'hold', 'steps': th_steps},
            'dd': {'thrower': s['entry']['thrower'], 'victim': STUN_ANIM, 'button': 'C', 'back': False, 'damage': s['entry']['damage']},
            'grab_frame': None}

def victim_pose_rows(B, ch):
    """the fighter's own pictures of every victim posture DD's throws use (victim_poses_dd.json keys): rows of a pseudo
    throw 'victim_poses' (export_bm.poses takes a fighter's posture frames from the throws that have it as the victim:
    Cheng-Fu's own throw holds only the stun postures, Billy's throws need his frames of 113-115)"""
    keys = json.load(open(os.path.join(HERE, 'victim_poses_dd.json')))['poses']
    rows = []
    for k in sorted(keys, key=lambda k: tuple(map(int, k.split('.')))):
        a, i = map(int, k.split('.'))
        rows.append([B.frame(((dd.steps(ch, a)[1][i]['def_'], 0, 0, 'body'),)), 0, 0, 0, 0, k, None])
    return rows

# ---- check: the scripts against the game ---------------------------------------------------------------------------------
P1, P2 = 0x10042A, 0x10052A
WALL = 576                                       # the vs stage's right edge for a body (x of the victim held there)
STATES = {0: None, 1: '/data/neogeo_dict/doubledr/cap/p1_01.state'}

def capture(ch, button, back):
    """P1 (Billy, or transformed from p1_01.state) walks into P2 and presses left / right + the button: per frame P1's
    animation / step / x / facing, P2's animation / step / definition / x / height (16.16) / facing / damage"""
    import cap_dd as c
    seq = f'70:R,3:{"L" if back else "R"}{button.lower()},140:-'
    rows = c.run(seq, load=STATES[ch] or c.VS)
    out = []
    for r in rows:
        R = r['ram']; F = dd.fighter_fields(R, P1); G = dd.fighter_fields(R, P2)
        s32 = lambda a: (lambda v: v - (1 << 32) if v & 0x80000000 else v)(c.u32(R, a))
        out.append(dict(f=r['f'], a1=F['anim'], s1=F['step'], t1=R[P1 + 0x20 - 0x100000], x1=s32(P1 + 6) / 65536, d1=F['dir'], c1=F['ch'],
                        a2=G['anim'], s2=G['step'], def2=G['def_'], x2=s32(P2 + 6) / 65536, y2=(s32(P1 + 10) - s32(P2 + 10)) / 65536,
                        d2=G['dir'], dmg=c.u16(R, P2 + 0x26), snd=r['snd']))
    return out

def compare(ch, button, back):
    """the script's rows vs the capture's from the throw's first frame, DD's pause frames (nothing moves, the thrower's
    tick counter held) dropped: per row the victim's (anim, step, def), x from the thrower in grab terms, height"""
    s = script(ch, button, back, vch=2); cap = capture(ch, button, back)   # (P2 = Jimmy, character 2)
    t0 = next(i for i, q in enumerate(cap) if q['a1'] == s['entry']['thrower'])
    F0 = -1 if cap[t0 - 1]['d1'] & 0x20 else 1   # the facing at the press (bit 5 = facing left)
    import math
    tx = math.floor(cap[t0]['x1'])
    seq, prev = [], None
    for q in cap[t0:]:
        k = (q['a1'], q['s1'], q['t1'], q['a2'], q['s2'], round(q['x2'], 3), round(q['y2'], 3))
        if k == prev: continue                    # (a frozen frame of the dragon pause)
        prev = k; seq.append(q)
    bad, first, n, wall = 0, None, 0, 0; dmg_row = None
    for i, r in enumerate(s['rows']):
        if i >= len(seq): break
        q = seq[i]; n += 1
        if dmg_row is None and q['dmg'] > cap[t0 - 1]['dmg']: dmg_row = i
        want = (r['v'][0], r['v'][1], round(r['x'], 2), round(r['y'], 2))
        got = (q['a2'], q['s2'], (math.floor(q['x2']) - tx) * F0, round(q['y2'], 2))   # (whole px: DD places by the words)
        if (want[0], want[1]) != (got[0], got[1]) or abs(math.floor(want[2]) - got[2]) > 0 or abs(want[3] - got[3]) > 0.5:
            if q['x2'] >= WALL and (want[0], want[1]) == (got[0], got[1]) and abs(want[3] - got[3]) <= 0.5:
                wall += 1; continue               # DD's stage edge holds the victim (x only)
            bad += 1; first = first or (i, want, got)
    land_cap = next((i for i, q in enumerate(seq) if q['a2'] == 71), None)
    th_end = next((i for i, q in enumerate(seq) if q['a1'] != s['entry']['thrower']), None)
    return dict(ch=ch, button=button, back=back, rows=n, mismatches=bad, first=first, at_stage_edge=wall, release=s['release'],
                damage_row=dmg_row, damage=cap[-1]['dmg'] - cap[t0 - 1]['dmg'], land=s['land'], land_dd=land_cap,
                ret=s['ret'], thrower_end_dd=th_end, victim_faces_grab=s['face'], dd_victim_dir=cap[t0]['d2'],
                dd_thrower_dir=cap[t0]['d1'])

if __name__ == '__main__':
    if sys.argv[1:2] == ['check']:
        out = sys.argv[2] if len(sys.argv) > 2 else OUT
        res = {'tables': {ch: table(ch) for ch in (0, 1)}, 'checks': []}
        for ch in (0, 1):
            for b in 'BCD':
                for back in (False, True):
                    r = compare(ch, b, back); res['checks'].append(r); print(json.dumps(r))
        json.dump(res, open(out, 'w'), indent=1)
    else:
        for ch in (0, 1): print(ch, table(ch))
        s = script(0, 'C')
        for i, r in enumerate(s['rows']): print(i, r)
