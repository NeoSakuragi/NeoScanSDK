#!/usr/bin/env python3
"""Kuroko's flag boomerang (6 3 2 1 4 + A, command result 50) measured in our emulator (TODO #176 follow-up): per frame
Kuroko, his opponent and the flag (object type 27, $4C274) with the fields its routines use. Situations: P2 out of the
flag's reach (a whiff), P2 in the out leg (hit going out), P2 put in the return leg once the flag hovers (hit coming
back). -> /data/tmp/kuroko176/ss2/<case>.json (+ ram dumps for the sheets)
    python3 boomerang_ss2.py [case ...]           cases: whiff out back p42 p46 (the last two: the parodies 1 2 6 BC
                                                  and 2 1 4 1 6 BC, P2 at the vs state's 157 px)
Rows: f, p1 / p2 (x, animation, step, class / action), flag (its fields) and segs, dl (the display list), slow ($8AC9).
Every case also takes a screenshot every 2nd frame (snap_<n>.ppm, the n-th listed frame: SNAPS) for the proof sheets.

The flag's code [code] (/data/tmp/samsho2/p1.dis):
  Kuroko  descriptor $5955E (class 1 result 50): anim 15 ($59576: velocities 0, the end -> next); anim 17 ($59582: spawn
          object type 27, its +$DC = the opponent, sound $E8, +$D4 = 0, next at once); $595A2 (param): waits for +$D4
          (the flag's catch signal) -> next; anim 24 ($595B0: the end -> neutral).
  flag    type 27 init $4C274: Kuroko's table, anim 19, vx = word $6BB26 (8 px a frame, forward), the hover count +$D6 =
          word $6BB28 (16), placed 99 px ahead of him and 32 up; two effect objects 40 ($4E72E: anim 23, the pole
          segments) placed 48 / 96 px behind the flag every frame, never nearer him than 64 px ($4EC50).
          $4C2F8 out:   its own clash test ($C670); |x + vx - his x| >= 220 -> x = his x + 220, vx 0 -> hover
          $4C358 hover: its clash test; +$D6 - 1 < 0 -> vx = -8 px (back to him) -> return
          $4C398 back:  (no clash test) |x + vx - his x| <= 104 -> x = his x + 104, vx 0, his +$D4 = -1 (the catch), +$D6
                        = 1 -> caught; it passes the place of its hit (+$DA) -> +$D5 = -1
          $4C410 caught: +$D6 - 1 < 0 -> gone ($4C730)
          every phase: Kuroko out of this action (+$E6 != $0132) -> gone at once
  its hit on a fighter (the objects' loop $C5C4, any object with +$102 clear: the animation clock clears it on every new
  step): $31478[27] = $4C47E (a hit) / $31618[27] = $4C45A (guarded: +$DA = 100 + (|dx| - 100) / 2), its clash
  $316E8[27] = $4C440 (+$DA = |dx|); each then: vx 0, the hover again ($4C358) with the count it has left."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_ss2 as C

STATE = '/data/neogeo_dict/samsho2/cap/p1_17.state'
OUT = '/data/tmp/kuroko176/ss2'
LEAD = 12
SEQ = f'{LEAD}:-,3:R,3:DR,3:D,3:DL,3:L,3:La'
N = 150
P2_OBJ = 0x105960                    # P2 (Haohmaru) in p1_17.state (cap_ss2.players)

def find_objs(r, owner):
    """the flag (type 27) and its pole segments (effect objects whose owner is the flag): tasks of $120 bytes from $102000"""
    flag, segs = None, []
    for o in range(0x2000, 0xA000, 0x20):
        if r[o + 4:o + 10] == b'PLAYER': continue
        if C.u32(r, o + 0xCC) == owner and r[o + 0xF6] == 27 and C.u16(r, o + 0x64) == 17 and C.u32(r, o) >> 24 == 0:
            if C.u32(r, o) in range(0x4C274, 0x4C442): flag = o
    if flag is not None:
        for o in range(0x2000, 0xA000, 0x20):
            if C.u32(r, o + 0xCC) == 0x100000 + flag and C.u16(r, o + 0x66) == 23 and C.u16(r, o + 0x64) == 17: segs.append(o)
    return flag, segs

def row(r, o):
    return dict(x=C.s16(r, o + 0x4E), y=C.s16(r, o + 0x50), vx=C.s16(r, o + 0x52), a=C.u16(r, o + 0x66),
                st=C.u32(r, o + 0x6C), tick=r[o + 0x7D], stn=r[o + 0x7C], face=r[o + 0x7F], r102=r[o + 0x102],
                d4=r[o + 0xD4], d5=r[o + 0xD5], d6=C.s16(r, o + 0xD6), da=C.s16(r, o + 0xDA), rt=C.u32(r, o))

def pl(r, o):
    return dict(x=C.s16(r, o + 0x4E), y=C.s16(r, o + 0x50), a=C.u16(r, o + 0x66), st=C.u32(r, o + 0x6C),
                cls=r[o + 0xE6], sub=r[o + 0xE7], life=r[o + 0x8C] if False else None, stn=r[o + 0x7C])

def parody_seq(result):
    import capture_cmds as CC, commands_ss2 as K
    e = next(e for e in K.command_list(17) if e['result'] == result)
    return f'{LEAD}:-,' + CC.seq_for(e)

CASES = {
    # P2 far: his world x poked out of reach each frame (Kuroko 240 -> the flag's reach 460 + its box)
    'whiff': dict(p2x=[(f, 560) for f in range(1, 40)]),
    'out': dict(p2x=[]),                                     # the vs state's 157 px: the flag hits going out
    # P2 out of reach while it flies out and hovers, then put 147 px from Kuroko once it heads back
    'back': dict(p2x=[(f, 560) for f in range(1, 76)] + [(f, 390) for f in range(76, 80)]),
    'p42': dict(p2x=[], seq=lambda: parody_seq(42)),         # 1 2 6 BC: the energy ball (palettes 38 / 39)
    'p46': dict(p2x=[], seq=lambda: parody_seq(46)),         # 2 1 4 1 6 BC: the smoke dud (palette 178)
}
SNAPS = list(range(2, N, 2))

def poke_x(a, f, x): return f'{f}:{a + 0x4E:X}={x >> 8 & 255:02X},{a + 0x4F:X}={x & 255:02X}'

def capture(case):
    c = CASES[case]; out = f'{OUT}/{case}'
    pokes = ';'.join(poke_x(P2_OBJ, f, x) for f, x in c['p2x'])
    seq = c['seq']() if 'seq' in c else SEQ
    C.run(out, seq + f',{N - C.nframes(seq)}:-', load=STATE, vram=False, pal_every=0, pokes=pokes or None, frames=range(1, N),
          snaps=SNAPS)
    rows = []
    for f in range(1, N):
        r = C.ram(out, f)
        if r is None: continue
        a1, a2 = C.players(r)
        fl, segs = find_objs(r, a1)
        if fl is not None and r[fl + 0xD4] == 0xFF: fl, segs = None, []   # gone ($4C434: +$D4 = -1, then deleted)
        rows.append(dict(f=f, p1=pl(r, a1 - 0x100000), p2=pl(r, a2 - 0x100000), flag=row(r, fl) if fl is not None else None,
                         segs=[row(r, s) for s in segs], dl=C.display_list(r),
                         slow=r[0xAC9]))                 # $8AC9: a hit's slow motion (frames left; $8AD3 alternates)
    json.dump(rows, open(f'{out}.json', 'w'))
    return rows

def show(rows):
    for q in rows:
        p1, p2, fl = q['p1'], q['p2'], q['flag']
        if p1['cls'] != 1 and not fl: continue
        s = f"{q['f']:3d} P1 {p1['cls']}/{p1['sub']} a{p1['a']} x{p1['x']}  P2 {p2['cls']}/{p2['sub']} a{p2['a']} x{p2['x']}"
        if fl: s += f"  FLAG x{fl['x']} (+{fl['x'] - p1['x']}) y{fl['y']} vx{fl['vx']} a{fl['a']}.{fl['stn']} r102={fl['r102']:02X} d4={fl['d4']} d5={fl['d5']:02X} d6={fl['d6']} da={fl['da']} rt={fl['rt']:X} segs {[g['x'] - p1['x'] for g in q['segs']]}"
        print(s)

if __name__ == '__main__':
    for case in sys.argv[1:] or list(CASES):
        print('==', case); show(capture(case))
