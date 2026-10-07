#!/usr/bin/env python3
"""Double Dragon (Technos 1995): the object frame update as a model, read in the 68000 code (/data/tmp/dd95/p1.dis),
so a fighter's moves can be played from the ROM's data alone (the brawler export, tools/doubledr/export_dd.py).

Per frame ($2048A, one object):
  1. the step loader ($20B1A): animation table $2C0000[char], step = 8 bytes [left][attr][def w][ticks][sound][box w]
  2. the step handler of the animation header's byte 0 (table $20C2E):
       0 $20D2E  attr bit 2 clear: v = 0; else the header velocity once per animation (+$1F bit 0), then unless attr
                 bit 3 the friction v -= v >> (b6 & 15) on vx AND vy (shift 0: stop)
       1 $20E58  attr bit 3: v = 0; attr bit 2: the friction only; else the header velocity every frame
       2 $20FA4  attr bit 2: v = 0 (and the once-flag cleared); else once: airborne (+$01 bit 7) + the header velocity;
                 airborne: vy += g, g = (b6 & $F0) << 8 (16.16, down), negated on attr bit 3; vx -= vx >> (b6 & 15)
       3 $211B4  handler 2's gravity and friction only (no velocity set)
       4 $211B8  attr bit 2 clear or not the step's last frame: v = 0; its last frame: v = the header words as whole
                 px (a one-frame step: $FB-like)
       5 $21202  v = 0; on the first frame of a step with attr bit 2: spawn an effect object (character 14, animation
                 b6, at x + header vx, y + header vy px; Super Billy's 236 ring)
      11 $21944  the transformation: at a step's first frame attr bit 4 -> palette slot - 2, attr bit 5 -> the
                 character + 1 (transform_dd.py); then handler 1's motion
      12 $219E0  v = 0; on the first frame of a step with attr bit 2: two effect objects (character 14, animation b6,
                 the second with palette $83 at step 4; Super Billy's 41236 rings)
      21 $22A6C  handler 2, then on the first frame (+$20 = 0) of a step WITHOUT attr bit 2: an afterimage (TODO #212,
                 Cheng-Fu's super 623 rise): an object (character 14, animation 86 = one step of 15 frames, palette base
                 96) with the fighter's palette (+$03), definition (+$04), place (+$06 / +$0A) and facing copied: the
                 fighter's picture of that frame left where it stands for 15 frames (measured: the trail of copies)
      22 $22B08  handler 0; +$1F bit 6 (its hit landed) in steps 0-1 and the victim free: the CATCH (Cheng-Fu's super 623
                 landing strike, anim 96): the victim stands in its animation 122 (one step: the held pose, def 2676
                 for Billy), on the floor, +$F3 bit 5; the attacker placed 48 px from it (x = victim x -/+ 48) and
                 animation 97 (the rush on the held victim) from step 0
      23 $22B9E  attr bit 3: v = 0, else the header velocity every frame ($20E6C: handler 1 without its friction
                 test); then on the first frame of a step WITH attr bit 2 the afterimage of handler 21 (Cheng-Fu's
                 super 236 rush)
      28 $23012  the DOWN ATTACK's leap (TODO #218: every fighter's anim 124, 8 / 2 + a button while the opponent lies
                 dizzy): attr bit 2: v = 0 (and the once-flag cleared); else once: airborne, vx = |x - the opponent's x|
                 (whole px) << 10 = the distance / 64 px a frame toward it (the fighter turned to face it), vy = the header
                 vy; then every frame vy += g ((b6 & $F0) << 8, down) and an afterimage (handler 21's object) on the
                 frames the object's own counter +$3B has its low 2 bits 0 (every 4th frame: model phase = the 2nd
                 airborne frame, as measured in chain218_dd); the opponent no longer dizzy (+$F3 bit 2 clear): the fall
                 (anim 35) at once; landed -> the header's next (125: the stomp). Its flight = 64 frames whatever the
                 distance (vy 14 / 13 px up, g 0.4375 / 0.40625): it lands on the opponent
      34 $2371A  v = 0; attr bit 2: +$F7 bit 4 = the COUNTER stance (Cheng-Fu's 421, anims 126-129): an attack that
                 overlaps his body record of type $40 hits nothing ($258AA: both +$1F bit 6, +$2E 22 / 20, sound $D1)
                 and the next frame here: the victim takes the throw victim's animation 113 + level (row 14), damage
                 table $237EE by level ($2000 / $2400 / $2800 / $3200), he goes to the header's next animation at
                 step 1 (the throw); unmatched it plays on (the whiff: 126 > 130 > 134)
     (velocities: header vx 8.8 in the art's facing (left: negative = forward), vy 8.8 up; world y grows downward)
  3. x += vx, y += vy; on the ground below y 488 -> airborne; airborne at y >= 489 -> landed: y = 488, vy = 0 and the
     header's next animation (11 / 12 when next is 0, 11, 12, 79 or 80) at once ($2065E)
  4. the step clock ($206CA): a step shows ticks + 1 frames (its sound byte sent on its first frame); after the last
     step: header flag bit 0 loop, bit 1 hold (until landed when airborne, then next), else next (0 = idle, 35 when
     airborne). A new animation clears +$1F but bit 5 and starts at step 0 the next frame.
-> play(): one record per frame [anim, step, def, x px forward, y px up, vx, vy, sound, events]."""
import dd

FLOOR = 488 << 16

class Obj:
    def __init__(self, ch, anim, x=0, y=FLOOR, right=True):
        self.ch, self.anim, self.step, self.cnt = ch, anim, 0, 0
        self.x, self.y, self.vx, self.vy = x << 16, y, 0, 0
        self.right = right                                   # facing right (the art faces left: +$01 bit 5 clear)
        self.f1f = 0; self.air = y < FLOOR; self.hold = False
        self.home = 58; self.n28 = 0                         # handler 28: the opponent's distance (px), airborne frames

def fwd(o, hv): return -(hv << 8) if o.right else hv << 8     # header vx (8.8, art facing) -> world 16.16

def handler(o, h, hdr, s, ev):
    attr = s['attr']; vxw = int.from_bytes(hdr[2:4], 'big', signed=True); vyw = int.from_bytes(hdr[4:6], 'big', signed=True)
    b6 = hdr[6]
    def fric(both):
        k = b6 & 15
        if both or k:                                        # handler 0/1: shift 0 = stop; handler 2: only when set
            o.vx -= o.vx >> k
            if both: o.vy -= o.vy >> k
    if h == 0:
        if not attr & 4: o.vx = o.vy = 0; return
        if not o.f1f & 1:
            o.f1f |= 1
            if vxw: o.vx = fwd(o, vxw)
            if vyw: o.vy = -(vyw << 8)
        if not attr & 8: fric(True)
    elif h in (1, 11):
        if h == 11 and o.cnt == 0:                           # $21944: the step's first frame, then handler 1's motion
            if attr & 0x10: ev.append(('palette', -2))
            if attr & 0x20: ev.append(('form', 1))
        if attr & 8: o.vx = o.vy = 0; return
        if attr & 4: fric(True); return
        o.vx = fwd(o, vxw); o.vy = -(vyw << 8)
    elif h in (2, 3):
        if h == 2:
            if attr & 4: o.vx = o.vy = 0; o.f1f &= ~1; return
            if not o.f1f & 1:
                o.f1f |= 1; o.air = True; o.vx = fwd(o, vxw); o.vy = -(vyw << 8)
        if o.air:
            g = (b6 & 0xF0) << 8
            o.vy += -g if attr & 8 else g
        if b6 & 15: o.vx -= o.vx >> (b6 & 15)
    elif h == 4:
        if not attr & 4 or o.cnt < s['ticks']: o.vx = o.vy = 0; return
        o.vx = (-(vxw << 16) if o.right else vxw << 16); o.vy = vyw << 16
    elif h in (21, 22, 23, 34):
        if h == 21: handler(o, 2, hdr, s, ev)
        elif h == 22: handler(o, 0, hdr, s, ev)              # (the catch needs a hit: never in the model)
        elif h == 23:
            if attr & 8: o.vx = o.vy = 0
            else: o.vx = fwd(o, vxw); o.vy = -(vyw << 8)
        else: o.vx = o.vy = 0                                # (the counter needs an attacker: never in the model)
        if o.cnt == 0 and ((h == 21 and not attr & 4) or (h == 23 and attr & 4)):
            ev.append(('ghost', s['def_'], o.x / 65536, (FLOOR - o.y) / 65536))   # the place before this frame's move
    elif h == 28:                                            # $23012: the down attack's homing leap (TODO #218)
        if attr & 4: o.vx = o.vy = 0; o.f1f &= ~1; return
        if not o.f1f & 1:
            o.f1f |= 1; o.air = True; o.n28 = 0
            v = o.home << 10; o.vx = -v if not o.right else v; o.vy = -(vyw << 8)
        o.vy += (b6 & 0xF0) << 8
        if o.n28 & 3 == 1: ev.append(('ghost', s['def_'], o.x / 65536, (FLOOR - o.y) / 65536))
        o.n28 += 1
    elif h in (5, 12):
        o.vx = o.vy = 0
        if o.cnt == 0 and attr & 4:
            ev.append(('spawn', 14, b6, -vxw if o.right else vxw, -vyw))   # px forward, px up
            if h == 12: ev.append(('spawn2', 14, b6, -vxw if o.right else vxw, -vyw))
    else:
        raise NotImplementedError(f'step handler {h}')

def start(o, n):
    o.anim, o.step, o.cnt, o.f1f, o.hold = n, 0, 0, o.f1f & 0x20, False
    if n == 13 and not o.air:                                # (the crouch out of a special: see frame's hold rule)
        o.step = 1; o.cnt = dd.steps(o.ch, 13)[1][1]['ticks']; o.hold = True

def landing_anim(nx): return 11 if nx in (0, 11, 12, 79, 80) else nx

def frame(o, stop=None):
    """one frame -> record; stop(o): the animations the caller does not follow (returns True to end)"""
    hdr, st = dd.steps(o.ch, o.anim); s = st[o.step]; ev = []
    handler(o, hdr[0], hdr, s, ev)
    o.x += o.vx; o.y += o.vy
    if not o.air and o.y < FLOOR: o.air = True
    landed = False
    if o.air and o.y >= FLOOR + 0x10000:
        o.y = FLOOR; o.vy = 0; o.air = False; landed = True
    rec = dict(anim=o.anim, step=o.step, def_=s['def_'], x=o.x / 65536, y=(FLOOR - o.y) / 65536, vx=o.vx / 65536,
               vy=-o.vy / 65536, snd=s['b5'] if o.cnt == 0 and not o.hold and s['b5'] else 0, ev=ev, box=s['w6'],
               attr=s['attr'], landed=landed)
    nx = hdr[7]
    if landed:
        start(o, landing_anim(nx)); rec['next'] = o.anim; return rec
    if o.hold:
        if o.air: return rec
        if not nx and o.anim == 13:                          # the crouch (13, a hold, steps accepting commands) after a
            start(o, 0); rec['next'] = 0; return rec         # special: with the stick neutral the control code stands
                                                             # the fighter up at once: its step 1 a frame, then idle
                                                             # (measured, compare_dd --far: Cheng-Fu's 623 > 102 > 13 > 0)
        if not nx: return rec
        start(o, nx); rec['next'] = nx; return rec
    c0 = o.cnt; o.cnt += 1
    if c0 >= s['ticks']:
        if s['left']: o.cnt = 0; o.step += 1
        elif hdr[1] & 1: o.cnt = 0; o.step = 0
        elif hdr[1] & 2: o.hold = True; o.cnt = c0
        else:
            n = nx or (35 if o.air else 0); start(o, n); rec['next'] = n
    return rec

def play(ch, anim, limit=400, until=(0, 1, 2, 3), right=True, home=58):
    """the animation chain from anim, standing on the floor, until one of `until` (idle / walks) starts (home: handler
    28's opponent distance, px)"""
    o = Obj(ch, anim, 0, FLOOR, right); o.home = home; out = []
    for _ in range(limit):
        if out and out[-1].get('next') in until: break
        out.append(frame(o))
    return out

if __name__ == '__main__':
    import sys
    ch, a = int(sys.argv[1]), int(sys.argv[2])
    for i, r in enumerate(play(ch, a)):
        print(i, r['anim'], r['step'], r['def_'], f"{r['x']:.2f}", f"{r['y']:.2f}", r['snd'] or '', r['ev'] or '', r.get('next', ''))
