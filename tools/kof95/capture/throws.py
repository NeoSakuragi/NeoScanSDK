#!/usr/bin/env python3
"""Throw capture for any KOF95 character, run in MAME from save state 'a' (Terry vs Terry).
P1 Terry's health is set to 1 and P2 knocks him out; while the next round loads, the incoming fighter's id
(the P1 team record at $10A840) is set to the requested character, so the game initialises that character for real.
P1 then tries forward+C and forward+D on the ground and forward+C / forward+D in the air against P2 Terry.

For each throw that connects it records:
  thrower  - P1's animation slot (the slot whose step frames match what P1 showed) and frame records
  victim   - per frame: P2's pose as a slot of P2's (Terry's) table, its position relative to P1 (in P1-facing x),
             until P2 is free again (lying down / back to neutral)
    python3 capture/throws.py ID [ID ...]   -> capture/throws/<id>.json + summary"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
import analyze as A, rom, export
from neogeo.sprite_decode import r32
from timeline import seqs

ROUND = 1100                                     # first frame of the new round with the swapped character in control
GAP = 240                                       # frames per try; fighters are put back 60 px apart at mid-stage first
TRIES = [  # (name, events relative to the try's start)
    ('ground_c', 'p1 0 60 R; p1 20 3 Rc'),
    ('ground_d', 'p1 0 60 R; p1 20 3 Rd'),
    ('air_c', 'p1 0 8 UR; p2 2 8 U; p1 12 4 URc; p1 16 30 R'),
    ('air_c_back', 'p1 0 8 UR; p2 2 8 U; p1 12 4 ULc; p1 16 30 L'),
    ('air_c_meet', 'p1 0 8 UR; p2 0 8 UL; p1 10 4 URc; p1 14 30 R'),
    ('air_d', 'p1 0 8 UR; p2 2 8 U; p1 12 4 URd; p1 16 30 R'),
    ('air_d_back', 'p1 0 8 UR; p2 2 8 U; p1 12 4 ULd; p1 16 30 L'),
    ('air_d_meet', 'p1 0 8 UR; p2 0 8 UL; p1 10 4 URd; p1 14 30 R'),
]
TOTAL = ROUND + GAP * len(TRIES) + 60
P1X, P2X = 0x190, 0x1CC                         # 400 and 460
GRABBED = set(range(180, 240)) | {37, 38}       # P2 game states seen while being thrown (Terry capture)

def run(cid):
    out = os.path.join(HERE, 'throws', f'{cid}.txt'); os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = 'p2 20 45 L; p2 70 3 c; ' + '; '.join(
        ' '.join([w, str(int(s) + ROUND + GAP * t), n, i])
        for t, (_, ev) in enumerate(TRIES) for w, s, n, i in (e.split() for e in ev.split(';')))
    s1, s2 = seqs(spec, TOTAL)
    # P1 health 1 + P1 team record ($10A840: +3..+5 = member ids) set to the character: after P2's hit the game
    # loads that fighter for the next round with everything (graphics, moves, throws) of its own
    poke = (f'2:108220=0,108221=1,108222=0,108223=1,10824C=0,10824D=1,10A843={cid:02X},10A844={cid:02X},10A845={cid:02X};' +
            ';'.join(f'{ROUND + GAP * t - 2}:108118={P1X >> 8:02X},108119={P1X & 255:02X},108318={P2X >> 8:02X},108319={P2X & 255:02X}'
                     for t in range(len(TRIES))))
    env = dict(os.environ, SEQ=s1, SEQ2=s2, POKE=poke, OUT=out)
    subprocess.run(['mame', 'kof95', '-rompath', '/home/bruno/Downloads', '-state', 'a', '-video', 'none', '-sound', 'none',
                    '-nothrottle', '-skip_gameinfo', '-noplugin', 'cart_bridge', '-autoboot_script', os.path.join(HERE, 'record.lua')],
                   env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    return out

def slot_of_sequence(prom, cid, recs):
    """the slot whose step frame records best cover the recorded sequence (in order)"""
    st = r32(prom, 0x080000 + cid * 4); best = (0, None)
    for s in range(102, 256):
        try: steps, _ = export.parse_anim(prom, r32(prom, st + s * 4))
        except Exception: continue
        fr = [f for _, f, _, _ in steps]
        if not fr or fr[0] != recs[0]: continue
        score = sum(1 for a, b in zip(fr, recs) if a == b)
        if score > best[0]: best = (score, s)
    return best[1]

def analyze(cid, path):
    prom, _ = rom.load(); sd = {r32(prom, 0x080080 + i * 4): i for i in range(30)}
    terry = A.slot_index(prom, 15)
    r1, r2 = A.load(path, 1), A.load(path, 2)
    assert sd.get((r1[ROUND][3][0x3C // 2] << 16) | r1[ROUND][3][0x3E // 2]) == cid, 'character swap failed'
    found, k = [], ROUND
    while k < len(r2):
        if A.state_of(r2[k][3]) in GRABBED and A.state_of(r1[k][3]) not in (0, 1, 2):
            start = k
            # the throw is over when the victim is down or free again, or when the thrower has been neutral for 30
            # frames (some throws end with the victim in a state of its own); 240 frames at most
            # hold throws (Goro, Choi, Rugal) loop the victim through the grab states 192/176/178 while the thrower
            # is back to neutral: the script ends where that loop starts again
            idle, left_grab, hold = 0, False, False
            while k < len(r2) and k - start < 240 and A.state_of(r2[k][3]) not in (0, 45, 47) and idle < 30:
                s2, s1 = A.state_of(r2[k][3]), A.state_of(r1[k][3])
                if s2 != 192 and k > start: left_grab = True
                if left_grab and s2 == 192 and A.state_of(r2[k - 1][3]) != 192 and s1 != 144: hold = True; break
                idle = idle + 1 if s1 in (0, 1, 2) else 0
                k += 1
            p1 = [w for _, _, _, w in r1[start - 2:k]]
            p1_states = sorted({A.state_of(w) for w in p1})
            recs = []
            for w in p1:
                f = A.frame_of(w)
                if not recs or recs[-1] != f: recs.append(f)
            # thrower's own animation starts where P1 left its pre-throw pose: find the slot from the first new record
            slot = None
            for i in range(len(recs)):
                slot = slot_of_sequence(prom, cid, recs[i:])
                if slot: break
            vic = []
            face0 = 1 if A.facing_of(r1[start][3]) else -1; x0 = A.x_of(r1[start][3])
            for (_, _, _, w1), (_, _, _, w2) in zip(r1[start:k], r2[start:k]):
                face = 1 if A.facing_of(w1) else -1
                f2 = A.frame_of(w2)
                # per frame: thrower frame record + x shift since the grab (in its starting facing); victim pose as
                # 'slot.step' of the victim's own table, its offset from the thrower (thrower-facing x, y up) and
                # whether it faces the same way as the thrower
                # victim pose = its game state (the game drives the victim by state; the victim's own state->slot
                # table gives the animation, so the same numbers work for any victim) + the step reached in that
                # animation (+$74 = byte offset of the current 6-byte step); frame record kept for checking
                vic.append({'tframe': f'{A.frame_of(w1):06X}', 'tdx': round((A.x_of(w1) - x0) * face0, 2), 'ty': round(A.y_of(w1), 2),
                            'state': A.state_of(w2), 'step': w2[0x74 // 2] // 6, 'record': f'{f2:06X}',
                            'pose': terry.get(f2, [f'{f2:06X}'])[0].split('(')[0],
                            'dx': round((A.x_of(w2) - A.x_of(w1)) * face, 2), 'dy': round(A.y_of(w2) - A.y_of(w1), 2),
                            'same_facing': A.facing_of(w1) == A.facing_of(w2)})
            kind = TRIES[min(len(TRIES) - 1, max(0, (r1[start][0] - ROUND) // GAP))][0]
            found.append({'try': kind, 'hold_loop': hold, 'p1_states': p1_states, 'thrower_slot': slot, 'p1_air': any(A.y_of(w) > 0 for w in p1[:4]),
                          'victim': vic})
        k += 1
    return found

if __name__ == '__main__':
    reuse = sys.argv[1] == '--reuse'                # re-analyse existing captures without running MAME
    for cid in map(int, sys.argv[2:] if reuse else sys.argv[1:]):
        path = os.path.join(HERE, 'throws', f'{cid}.txt') if reuse else run(cid)
        try: res = analyze(cid, path)
        except AssertionError as e: print(cid, e); continue
        json.dump(res, open(os.path.join(HERE, 'throws', f'{cid}.json'), 'w'), indent=1)
        print(cid, [(t['try'], t['thrower_slot'], t['p1_states'], 'air' if t['p1_air'] else 'ground', len(t['victim'])) for t in res])
