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
    elif h in (5, 12):
        o.vx = o.vy = 0
        if o.cnt == 0 and attr & 4:
            ev.append(('spawn', 14, b6, -vxw if o.right else vxw, -vyw))   # px forward, px up
            if h == 12: ev.append(('spawn2', 14, b6, -vxw if o.right else vxw, -vyw))
    else:
        raise NotImplementedError(f'step handler {h}')

def start(o, n):
    o.anim, o.step, o.cnt, o.f1f, o.hold = n, 0, 0, o.f1f & 0x20, False

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
        if o.air or not nx: return rec
        start(o, nx); rec['next'] = nx; return rec
    c0 = o.cnt; o.cnt += 1
    if c0 >= s['ticks']:
        if s['left']: o.cnt = 0; o.step += 1
        elif hdr[1] & 1: o.cnt = 0; o.step = 0
        elif hdr[1] & 2: o.hold = True; o.cnt = c0
        else:
            n = nx or (35 if o.air else 0); start(o, n); rec['next'] = n
    return rec

def play(ch, anim, limit=400, until=(0, 1, 2, 3), right=True):
    """the animation chain from anim, standing on the floor, until one of `until` (idle / walks) starts"""
    o = Obj(ch, anim, 0, FLOOR, right); out = []
    for _ in range(limit):
        if out and out[-1].get('next') in until: break
        out.append(frame(o))
    return out

if __name__ == '__main__':
    import sys
    ch, a = int(sys.argv[1]), int(sys.argv[2])
    for i, r in enumerate(play(ch, a)):
        print(i, r['anim'], r['step'], r['def_'], f"{r['x']:.2f}", f"{r['y']:.2f}", r['snd'] or '', r['ev'] or '', r.get('next', ''))
