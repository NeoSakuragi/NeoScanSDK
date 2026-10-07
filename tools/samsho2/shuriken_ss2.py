#!/usr/bin/env python3
"""Hanzo's air special in Samurai Shodown II (TODO #211): 4 1 2 3 + A / B / A+B in a jump, the shuriken (command entries
9-11 -> results 48-50, descriptor list $36BF2; object type 5 $30396). Captured in our emulator (cap_ss2: P1 Hanzo,
state cap/p1_02.state, P2 Haohmaru 160 px away, both idle), per frame: Hanzo, Haohmaru, the shuriken object (the task
named 'TAMA'), whether its floor picture (def 3432, anim 269) is drawn, the sound commands.

    python3 shuriken_ss2.py [OUT.json]         (default /data/neogeo_dict/samsho2/moves/02_air.json)

Cases: up / fwd (the jump) x a / b / ab (the button), whiffs and hits (P2 poked to 330 px: the shuriken
meets him), whiffs with P2 poked to 560 (out of the shuriken's reach, and Hanzo's hop back stays within the
players' 401 px). The motion is entered DR one frame before the button: the recogniser takes one pattern step a frame (a
direction and the button in the same frame only match the direction step), [meas]."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_ss2 as C

STATE = '/data/neogeo_dict/samsho2/cap/p1_02.state'
P1, P2 = 0x105720, 0x104E20                    # the players' tasks in p1_02.state (cap_ss2.players)
FLOOR_DEF = 3432                               # anim 269's layer: the shuriken stuck in the floor
TAIL = 160
JUMP = {'up': 'U', 'fwd': 'UR'}

def seq(jump, b):
    return f'12:-,3:{JUMP[jump]},4:-,1:L,1:DL,1:D,1:DR,1:DR{b},{TAIL}:-'

CASES = {f'{j}_{b}': (seq(j, b), 560) for j in JUMP for b in ('a', 'b', 'ab')}   # (P2 out of reach;
                                                                                 # 401 px apart at most: he stays free)
CASES.update({f'hit_{j}_{b}': (seq(j, b), 330) for j in JUMP for b in ('a', 'b', 'ab')})

def obj(r, a):
    o = a - 0x100000
    return dict(cls=r[o + 0xE6], sub=r[o + 0xE7], a=C.u16(r, o + 0x66), st=r[o + 0x7C], f9=r[o + 0xF9], ee=r[o + 0xEE],
                x=C.s16(r, o + 0x4E), y=C.s16(r, o + 0x50), vx=C.s16(r, o + 0x52), vy=C.s16(r, o + 0x56), proj=r[o + 0x112])

def run_case(name, sq, p2x):
    d = f'/data/tmp/hz211/cap_{name}'
    pk = ';'.join(f'{k}:{P2 + 0x4E:X}={p2x >> 8:02X},{P2 + 0x4F:X}={p2x & 255:02X}' for k in (1, 2)) if p2x else None
    C.run(d, sq, load=STATE, vram=False, pokes=pk)
    snd = {}
    for line in open(f'{d}/snd.txt'):
        snd.setdefault(int(line[:5]), []).append(int(line[6:8], 16))
    rows = []
    for f in range(1, C.nframes(sq)):
        r = C.ram(d, f)
        if r is None: continue
        tama = [dict(a=C.u16(r, a + 0x66), st=r[a + 0x7C], x=C.s16(r, a + 0x4E), y=C.s16(r, a + 0x50), vx=C.s16(r, a + 0x52),
                     vy=C.s16(r, a + 0x56), ax=C.s16(r, a + 0xD0), ay=C.s16(r, a + 0xD2), rt=C.u32(r, a) & 0xFFFFFF)
                for a in range(0x2000, 0xA000, 0x20) if r[a + 4:a + 8] == b'TAMA']
        rows.append(dict(f=f, p1=obj(r, P1), p2=obj(r, P2), tama=tama,
                         floor_drawn=any(e['d'] == FLOOR_DEF for e in C.display_list(r)), snd=snd.get(f, [])))
    for f in os.listdir(d):
        if f.startswith('ram'): os.remove(os.path.join(d, f))
    return dict(name=name, seq=sq, p2x=p2x, rows=rows)

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/data/neogeo_dict/samsho2/moves/02_air.json'
    res = {n: run_case(n, s, x) for n, (s, x) in CASES.items()}
    json.dump(res, open(out, 'w'))
    for n, c in res.items():
        seqa = []
        for r in c['rows']:
            k = (r['p1']['cls'], r['p1']['sub'], r['p1']['a'])
            if not seqa or seqa[-1][0] != k: seqa.append([k, r['f']])
        hit = next((r['f'] for r in c['rows'] if r['p2']['cls'] == 3), None)
        fl = [r['f'] for r in c['rows'] if r['floor_drawn']]
        print(n, ' '.join(f'{a}@{f}' for (_, _, a), f in seqa[1:]), '| hit', hit, '| floor drawn', fl[:1], fl[-1:] if fl else '')
