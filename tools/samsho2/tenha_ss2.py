#!/usr/bin/env python3
"""Haohmaru's Tenha Fuujinzan (3 4 1 2 3 4 2 1 + B+C, result 53) in Samurai Shodown II, measured in our emulator (note
20261011-112545-5d29: "10 to 12 hits where the opponent gets hit but STAYS STANDING, the launcher only at the very end").

P1 Haohmaru (cap/p1_00.state), P2 poked 56 px ahead (capture_cmds' close rule); every frame: P2's life (+$BB), its hit-stop
counter (+$FB), its class 3 action / animation (the reaction), Haohmaru's animation, and the wind (object type 47: tasks
of $120 bytes from $102000, +$F6 = 47, +$CC = its fighter): its animation, step (+$7C) and hit flag (+$102). A hit = the frame the wind's +$102 is set: its step then.

    python3 tenha_ss2.py [OUT]        -> OUT/tenha_ss2.json (default /data/tmp/samsho2): hits [frame, wind step, P2
                                         action, anim, +$FB], handlers_ss2.TENHA_HITS = {his step: the wind's}"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cap2 as C2, capture_cmds as K, commands_ss2 as CM

P1, P2 = 0x105060, 0x1053C0                     # the players in cap/p1_00.state (cap_ss2.players)
BASE, SIZE = 0x102000, 0x8000

def run():
    e = next(x for x in CM.command_list(0) if x['result'] == 53)
    st = f'{K.STA}/p1_00.state'
    seq = f'{K.LEAD}:-,' + K.seq_for(e) + ',260:-'
    n = C2.nframes(seq)
    r1 = C2.run(seq, ranges=((BASE, SIZE),), load=st, frames=[1])[1][BASE]
    x = C2.s16(r1, P1 - BASE + 0x4E) + 56
    rows = C2.run(seq, ranges=((BASE, SIZE),), load=st, frames=range(1, n),
                  pokes=f'1:{P2 + 0x4E:X}={x >> 8 & 255:02X},{P2 + 0x4F:X}={x & 255:02X}')
    import ss2
    STEP = {s['addr']: (a, k) for a in (336, 264, 265, 3) for k, s in enumerate(ss2.parse_anim(0, a, 400))}
    out = []
    for f in sorted(rows):
        r = rows[f][BASE]; p2 = P2 - BASE
        wind = next(((C2.u16(r, o + 0x66), r[o + 0x7C], r[o + 0x102]) for o in range(0, SIZE - 0x120, 0x20)
                     if r[o + 0xF6] == 47 and C2.u32(r, o + 0xCC) == P1), None)
        out.append(dict(f=f, life=r[p2 + 0xBB], fb=r[p2 + 0xFB], cls=r[p2 + 0xE6], act=r[p2 + 0xE7], anim=C2.u16(r, p2 + 0x66),
                        p1anim=C2.u16(r, P1 - BASE + 0x66), p1step=STEP.get(C2.u32(r, P1 - BASE + 0x6C)), wind=wind))
    return out

def hits(rows):
    """the wind's hits [frame, wind step, P2 action, P2 anim] = the frames its +$102 is set (the object loop's "it hit"
    flag, $C5C4; the animation clock clears it on each new step) on a step with an attack record, P2's reaction 3 frames
    on; and the launch [frame, Haohmaru's animation, P2 action, P2 anim]: the first frame P2 is in class 3 action 73"""
    import ss2
    atk = {k for k, s in enumerate(ss2.parse_anim(0, 337, 400)) if any(w & 0x8000 for w, l in s['boxes'])}
    res = []
    for i in range(1, len(rows) - 3):
        w, w0 = rows[i]['wind'], rows[i - 1]['wind']
        if not w or not w[2] or w[1] not in atk or (w0 and w0[2] and w0[1] == w[1]): continue
        res.append([rows[i]['f'], w[1], rows[i + 3]['act'], rows[i + 3]['anim'], rows[i]['p1step']])
    la = next((r for r in rows if r['cls'] == 3 and r['act'] == 73), None)
    return res, la and [la['f'], la['p1anim'], la['act'], la['anim']]

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/samsho2'
    rows = run(); H, L = hits(rows)
    reel = [h[1] for h in H if h[2] == 4]
    res = {'hits': H, 'launch': L, 'count': len(H), 'reel_steps': reel, 'frames': rows}
    os.makedirs(out, exist_ok=True); json.dump(res, open(os.path.join(out, 'tenha_ss2.json'), 'w'))
    for h in H: print('wind hit frame %d  step %d  P2 class 3 action %d anim %d  Haohmaru (anim, step) %s' % tuple(h))
    print('launch frame %d  Haohmaru anim %d  P2 class 3 action %d anim %d' % tuple(L))
    print(len(H), 'wind hits; P2 reels after', len(reel), '(steps', reel, '); the launch follows the last one (step %d)' % H[-1][1])
