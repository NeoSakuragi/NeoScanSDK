#!/usr/bin/env python3
"""Per-victim throw scripts: every KOF96 throw, frame by frame, for any of the 29 victims.

Thrower: its timeline as captured (capture/throws/<id>_<try>.txt, victim Yuri): state and step counter +$80, so
its frame is step +$80 - 1 of its own animation for that state (shared state map).
Victim, list phase: the throw list the capture shows driving Yuri (victim side $1AF72 or thrower side $1B008,
throwtables96.py), taken for the other victim: list = base + victim id * size, entry at the thrower's step +$80 - 1
gives the victim's state and offset. The victim's frame is the current step of its own animation for that state.
Victim, before the list (approach of hold throws) and after the release (flight, landing): as captured on Yuri, the
flight shifted so it starts where this victim was released.
Choi's hold uses no list: as captured, with each victim's own frames for its states.
Validated: every captured list reproduces Yuri's state and offset frame for frame up to the release (62 throws).

Timeline row: [thrower frame index, x from start, height, turned (1: faces away from its facing at the grab)].
Victim row: [victim frame index or None, victim x from thrower, victim height from thrower, victim faces the thrower's
      grab facing (1/0), victim drawn in front (1/0), 'state.step' = key into victim_poses96.json (posture + angle)].
Every x is in the thrower's facing at the grab. The game's freezes are cut (build), 'impacts' = rows before them."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
import analyze as A, rom96, throwtables96 as T

SPAN = 300
VICTIMS = {'kof96': 8, 'kof98': 8, 'kof99': 3}             # P2 in each game's 'vs' state, the captured victim
TDIR = {'kof96': 'throws', 'kof98': 'throws98'}
KEYS = {'ground_c': 'throw_c', 'ground_d': 'throw_d', 'air_c': 'air_throw'}
INPUTS = {'ground_c': 'forward+C (close)', 'ground_d': 'forward+D (close)', 'air_c': 'forward+C in the air (close)'}
LANDED = {0, 66, 24}

def anim_steps(m, cid, state, mp, cache={}):
    k = (m.game, cid, state)
    if k not in cache:
        slot = mp[state] if mp is not None else rom96.state_slot(m, cid, state)
        try: cache[k] = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
        except Exception: cache[k] = ([], 'end')
    return cache[k]

def frame_by_step(m, cid, state, step, mp):
    steps, _ = anim_steps(m, cid, state, mp)
    return steps[min(max(0, step - 1), len(steps) - 1)][1] if steps else None

def frame_by_time(m, cid, state, t, mp):
    """(frame index, step) of `cid`'s animation for `state`, t frames after entering it (loop/hold)"""
    steps, mode = anim_steps(m, cid, state, mp)
    if not steps: return None, 0
    total = sum(s[0] for s in steps)
    if mode == 'loop' and total: t %= total
    for k, s in enumerate(steps):
        if t < s[0]: return s[1], k
        t -= s[0]
    return steps[-1][1], len(steps) - 1

def build(m, mp, cid, found, victims):
    """found: the tables.json entries of one try. {victim id: rows}"""
    VICTIM = VICTIMS[m.game]
    cap = found[0]['capture']; start = found[0]['round']; d = os.path.join(HERE, 'capture', TDIR.get(m.game, 'throws_' + m.game))
    r1, r2 = A.load(os.path.join(d, cap), 1), A.load(os.path.join(d, cap), 2)
    lists = [(x['side'], int(x['base'], 16), x['size']) for x in found if 'base' in x]
    ylists = {(s, b + VICTIM * z): T.entries(m, b, z, VICTIM) for s, b, z in lists}
    end = min(len(r1), len(r2), start + SPAN)
    # the grab window: first frame Yuri is in a throw pose .. Yuri back on the ground in a landed state
    g0 = next((i for i in range(start, end) if A.state_of(r2[i][3]) >= 400), None)
    if g0 is None: return {}
    g1 = g0
    landed = LANDED if m.game == 'kof96' else {0, 72, 24}     # KOF98/99 get-up = 72
    while g1 < end and not (g1 > g0 + 5 and A.state_of(r2[g1][3]) in landed): g1 += 1
    # which list drives each frame (as validated on Yuri)
    phase, released = [], False
    for i in range(g0, g1):
        w1, w2 = r1[i][3], r2[i][3]; drv = None
        if not released:
            for (side, addr), e in ylists.items():
                h = w2 if side == 'victim' else w1
                if ((h[0xC2 // 2] << 16) | h[0xC4 // 2]) != addr: continue
                x = e[min(max(0, w1[0x80 // 2] - 1), len(e) - 1)]
                f = 1 if A.facing_of(w1) else -1
                if x['state'] == A.state_of(w2) and abs((A.x_of(w2) - A.x_of(w1)) * f - x['dx']) <= 1 and abs(A.y_of(w2) - A.y_of(w1) - x['dy']) <= 1:
                    drv = (side, addr - VICTIM * [z for s, b, z in lists if b + VICTIM * z == addr][0], x['flags'] & 64); break
        if drv is None and any(p != 'approach' for p in phase): released = True
        phase.append('flight' if released else drv if drv else 'approach')
    w0 = r1[g0][3]; f0 = 1 if A.facing_of(w0) else -1; x0 = A.x_of(w0)
    # the game's freezes (Bruno 2026-10-04: impact freezes baked into the throws): KOF98 shows a step for its ROM ticks
    # + 1 frames (checked on Terry, Ralf, Kyo); frames past that where nothing moves (thrower x, height, step; victim
    # state, x, height) are a freeze (Ryo's forward+C: 20 frames on step 10; not P1's +$124 hit-stop, unset in throws).
    # Dropped; the frame before a freeze is an impact. The anim's last step (a hold) is never cut.
    drop, impacts, run_key, run_n = set(), [], None, 0
    for i in range(g0, g1):
        w1, w2 = r1[i][3], r2[i][3]; key = (A.state_of(w1), w1[0x80 // 2])
        run_n = run_n + 1 if key == run_key else 1; run_key = key
        steps_ = anim_steps(m, cid, key[0], mp)[0]
        if i == g0 or not steps_ or not 1 <= key[1] < len(steps_) or run_n <= steps_[key[1] - 1][0] + 1: continue
        p1, p2 = r1[i - 1][3], r2[i - 1][3]
        if (A.x_of(w1), A.y_of(w1), A.state_of(w2), A.x_of(w2), A.y_of(w2)) == (A.x_of(p1), A.y_of(p1), A.state_of(p2), A.x_of(p2), A.y_of(p2)):
            if i - 1 not in drop: impacts.append(i - 1)
            drop.add(i)
    kept = [i for i in range(g0, g1) if i not in drop]
    # facing: everything is measured in the thrower's facing at the grab (f0); a thrower that turns around during the
    # throw (Terry's reverse throw) gets the row flag 'turned' (it is drawn mirrored, its places do not flip)
    timeline = []
    for i in kept:
        w1 = r1[i][3]
        timeline.append((frame_by_step(m, cid, A.state_of(w1), w1[0x80 // 2], mp), round((A.x_of(w1) - x0) * f0), round(A.y_of(w1)),
                         int((1 if A.facing_of(w1) else -1) != f0)))
    out = {}
    for v in victims:
        rows, cur, shift, last = [], None, None, None
        for k, i in enumerate(range(g0, g1)):
            w1, w2 = r1[i][3], r2[i][3]; f = 1 if A.facing_of(w1) else -1; ph = phase[k]
            if isinstance(ph, tuple):
                side, base, flag = ph; size = [z for s, b, z in lists if b == base][0]
                e = T.entries(m, base, size, v); x = e[min(max(0, w1[0x80 // 2] - 1), len(e) - 1)]
                # facing: KOF96 keeps the victim facing the thrower (all 3825 list frames captured: opposite facing);
                # KOF98's entry bit 'turn' = victim faces the thrower's way
                state, dx, dy, same, front = x['state'], x['dx'], x['dy'], x.get('turn', 0), x['front']
                ydx, ydy = round((A.x_of(w2) - A.x_of(w1)) * f), round(A.y_of(w2) - A.y_of(w1))
                last = (dx - ydx, dy - ydy)
            else:
                state = A.state_of(w2); dx = round((A.x_of(w2) - A.x_of(w1)) * f); dy = round(A.y_of(w2) - A.y_of(w1))
                same = int(A.facing_of(w1) == A.facing_of(w2)); front = 0
                if ph == 'flight' and last: dx, dy = dx + last[0], dy + last[1]
            if f != f0: dx, same = -dx, 1 - same                # into the grab's facing
            if i in drop: continue
            kk = len(rows)                                   # time in kept frames: the game froze the victim too
            if cur is None or cur[0] != state: cur = (state, kk)
            vf, step = frame_by_time(m, v, state, kk - cur[1], mp)
            rows.append([vf, dx, dy, same, front, f'{state}.{step}'])     # key into victim_poses96.json
        out[v] = rows
    return {'timeline': timeline, 'victims': out, 'thrower_state': A.state_of(r1[g0][3]),
            'impacts': [kept.index(i) for i in impacts],
            'lists': [{'side': s, 'base': hex(b), 'size': z} for s, b, z in lists]}

def hold(m, mp, cid, info, victims, cap='20_ground_c.txt', start=1400):
    """Choi: hold throw outside the list routines, replayed as captured"""
    p = os.path.join(HERE, 'capture', 'throws', cap)
    r1, r2 = A.load(p, 1), A.load(p, 2)
    g0 = next(i for i in range(start, len(r2)) if A.state_of(r2[i][3]) >= 400)
    g1 = min(len(r2), g0 + 120)
    w0 = r1[g0][3]; f0 = 1 if A.facing_of(w0) else -1; x0 = A.x_of(w0)
    timeline = [(frame_by_step(m, cid, A.state_of(r1[i][3]), r1[i][3][0x80 // 2], mp), round((A.x_of(r1[i][3]) - x0) * f0),
                 round(A.y_of(r1[i][3])), int((1 if A.facing_of(r1[i][3]) else -1) != f0)) for i in range(g0, g1)]
    out = {}
    for v in victims:
        rows, cur = [], None
        for k, i in enumerate(range(g0, g1)):
            w1, w2 = r1[i][3], r2[i][3]; f = 1 if A.facing_of(w1) else -1; state = A.state_of(w2)
            if cur is None or cur[0] != state: cur = (state, k)
            vf, step = frame_by_time(m, v, state, k - cur[1], mp)
            rows.append([vf, round((A.x_of(w2) - A.x_of(w1)) * f0), round(A.y_of(w2) - A.y_of(w1)),
                         int((1 if A.facing_of(w2) else -1) == f0), 0, f'{state}.{step}'])
        out[v] = rows
    return {'timeline': timeline, 'victims': out, 'thrower_state': A.state_of(r1[g0][3]), 'lists': [], 'hold': True}

def all_throws(m, mp, victims):
    """{thrower id: {key: built}} from capture/throws/tables.json"""
    tabs = json.load(open(os.path.join(HERE, 'capture', TDIR.get(m.game, 'throws_' + m.game), 'tables.json')))
    res = {}
    for k, L in tabs.items():
        cid = int(k); res[cid] = {}
        if L and L[0].get('hold'):
            res[cid]['throw_c'] = dict(hold(m, mp, cid, L[0], victims), inputs=INPUTS['ground_c']); continue
        for tr, key in KEYS.items():
            found = [x for x in L if x.get('try') == tr]
            if not found: continue
            b = build(m, mp, cid, found, victims)
            if b: res[cid][key] = dict(b, inputs=INPUTS[tr])
    return res

if __name__ == '__main__':
    prom, _ = rom96.load(); m = rom96.Mem(prom); mp = rom96.shared_map(m)
    res = all_throws(m, mp, [0, 3, 8])
    for cid, d in sorted(res.items()):
        print(cid, {k: (len(v['timeline']), v['thrower_state'], v['victims'][0][:2]) for k, v in d.items()})
