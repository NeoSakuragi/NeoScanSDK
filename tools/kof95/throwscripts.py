#!/usr/bin/env python3
"""Per-victim throw scripts: every KOF95 throw, frame by frame, for any of the 26 victims.

Thrower: its timeline as captured in MAME (capture/throws/<id>.txt, victim Terry) - frame record, movement, animation step
counter (+$82), event flag (+$7D bit 0), hit-stop (+$7B), state. It does not depend on the victim.
Victim, table phase: the throw's ROM table (throwtables.py) for that victim, replayed with the game's rules (entry at the
thrower's step, look-ahead on flagged steps, frozen during hit-stop); no screen clamp (that is the game's camera, a
beat 'em up has its own). The victim's frame is the current step of its own animation for the table's state.
Victim, before the table (approach of hold throws) and after the release (flight, landing): as captured, the flight
shifted so it starts where this victim was released.
Validated: mirror matches of all 26 throwers and Heidern on 6 victims reproduce the game frame for frame (throwtables.py).

Row: [thrower frame record, thrower x from start (thrower-facing), thrower height, victim frame record, victim x from
      thrower, victim height from thrower, victim faces the thrower's way (1/0), victim drawn in front (1/0),
      posture, angle, 'state.step']"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, 'capture'))
import analyze as A, export, throwtables as T
from neogeo.sprite_decode import r32

ROUND = 1100
GRAB = {176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199,
        200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 223, 224,
        225, 226, 227, 246, 247, 254, 255}
LANDED = {0, 45, 47}
POSES = json.load(open(os.path.join(HERE, 'victim_poses.json')))['poses']

def windows(cid):
    """grab windows in capture/throws/<id>.txt: {'throw': (start, end), 'air_throw': ...}, first of each kind"""
    path = os.path.join(HERE, 'capture', 'throws', f'{cid}.txt')
    r1, r2 = A.load(path, 1), A.load(path, 2)
    out, i = {}, ROUND
    while i < len(r2):
        if A.state_of(r2[i][3]) in GRAB:
            g = i; released = False
            while i < len(r2) and i - g < 300:
                s = A.state_of(r2[i][3])
                if s not in GRAB: released = True
                if released and s in LANDED: break
                i += 1
            kind = 'air_throw' if A.y_of(r1[g][3]) > 0 else 'throw'
            out.setdefault(kind, (g, i))
        i += 1
    return out, r1, r2

def state_frame(prom, cid, state, t):
    """frame record of `cid`'s animation for game state `state`, t frames after entering it (ticks; loop/hold)"""
    addr = r32(prom, r32(prom, 0x080000 + cid * 4) + export.state_slot(prom, cid, state) * 4)
    steps, mode = export.parse_anim(prom, addr)
    if not steps: return None
    total = sum(s[0] for s in steps)
    if mode == 'loop' and total: t %= total
    for ticks, rec, _, _ in steps:
        if t < ticks: return rec
        t -= ticks
    return steps[-1][1]

def build(prom, cid, kind, fmt, tabs, victims):
    """{victim id: rows} for one throw of character `cid`"""
    wins, r1, r2 = windows(cid)
    if kind not in wins: return {}
    g0, g1 = wins[kind]
    terry = [T.victim_rows(prom, t, 15, fmt=fmt) for t in tabs]
    states15 = {c['state'] for l in terry if l for c in l}
    # phases from the captured (Terry) run: approach frames, table frames (until the release frame), flight frames
    T.predict.phases = []; phase = []; prev = None; released = False; started = False
    for i in range(g0, g1):
        w1, w2 = r1[i][3], r2[i][3]
        if released or (started and A.state_of(w2) not in states15): phase.append('flight'); continue
        pr = T.predict(terry, w1, w2, prev, None)
        if not started:
            ok = pr and pr[0] == A.state_of(w2) and abs(pr[1] - A.x_of(w2)) <= 1 and abs(pr[2] - A.y_of(w2)) <= 1
            if not ok: phase.append('approach'); continue
            started = True
        phase.append('table'); released = T.predict.last_end
        prev = (A.state_of(w2), A.x_of(w2), A.y_of(w2))
    w0 = r1[g0][3]; f0 = 1 if A.facing_of(w0) else -1; x0 = A.x_of(w0)
    out = {}
    for v in victims:
        lists = [T.victim_rows(prom, t, v, fmt=fmt) for t in tabs]
        T.predict.phases = []; prev = None; rows = []; shift = None; last_table = None; cur = None
        for k, i in enumerate(range(g0, g1)):
            w1, w2 = r1[i][3], r2[i][3]; f = 1 if A.facing_of(w1) else -1
            tx, ty = round((A.x_of(w1) - x0) * f0, 2), round(A.y_of(w1), 2)
            if phase[k] == 'table':
                pr = T.predict(lists, w1, w2, prev, None)
                b1 = bytes(x for q in w1 for x in (q >> 8, q & 255))
                e_front = 0
                if pr is None: break
                state, vx, vy = pr; prev = pr
                dx, dy = round((vx - A.x_of(w1)) * f, 2), round(vy - A.y_of(w1), 2)
                same = 1
                last_table = (dx, dy, A.x_of(r2[i][3]) - A.x_of(w1), A.y_of(r2[i][3]) - A.y_of(w1), f)
                for l in lists:
                    for e in l or []:
                        if e['state'] == state: e_front = e['front']; break
            else:
                state = A.state_of(w2); dx = round((A.x_of(w2) - A.x_of(w1)) * f, 2); dy = round(A.y_of(w2) - A.y_of(w1), 2)
                same = int(A.facing_of(w1) == A.facing_of(w2)); e_front = 0
                if phase[k] == 'flight' and last_table:
                    if shift is None: shift = (last_table[0] - last_table[2] * last_table[4], last_table[1] - last_table[3])
                    dx, dy = round(dx + shift[0], 2), round(dy + shift[1], 2)
            if cur is None or cur[0] != state: cur = (state, k)
            if phase[k] == 'table':
                rec = state_frame(prom, v, state, k - cur[1]); key = f'{state}.0'
            else:
                step = w2[0x74 // 2] // 6
                rec = export.frame_at(prom, r32(prom, r32(prom, 0x080000 + v * 4) + export.state_slot(prom, v, state) * 4), step)
                key = f'{state}.{step}'
            posture, angle = POSES.get(key, POSES.get(f'{state}.0', ['?', None]))
            rows.append([f'{A.frame_of(w1):06X}', tx, ty, f'{rec:06X}' if rec else None, dx, dy, same, e_front, posture, angle, key])
        out[v] = rows
    return out
