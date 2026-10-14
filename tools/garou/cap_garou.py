#!/usr/bin/env python3
"""Garou in our emulator's core (tools/lastbld2/core_lb2: the repo's Geolith build frame by frame from Python, the
68000 write tap) and the per-frame fighter rows the study reads.

    from cap_garou import Garou, VS
    g = Garou(); g.load_state(VS)               # round 1, P1 Rock (x $F0) vs P2 Terry (x $190), both idle
    rows = g.play('6:a,40:')                     # [{'P1': {...}, 'P2': {...}}] per frame (keys U D L R a b c d)

Fighter tasks [meas]: P1 'FIGHTER1' $100400, P2 'FIGHTER2' $100500 ($100 bytes each, name at +$18):
+$10 character, +$20 x (16.16), +$24 ground y, +$28 height (16.16, up negative), +$34 vx, +$3C v height, +$54 / +$56
the step's sprite offsets, +$58 facing, +$5E the step word (frame id), +$60 the requested animation, +$62 / +$64 its record,
+$66 the step, +$6A step flags, +$6F ticks left, +$76 the sprite data pointer, +$7A [box count][box list pointer]."""
import os, sys, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lastbld2'))
if not os.environ.get('BRAWLER_CORE'):
    for c in (os.path.join(HERE, '..', '..', 'geolith', 'libretro', 'geolith_libretro.so'),
              '/home/bruno/CLProjects/NeoGeo/geolith/libretro/geolith_libretro.so'):
        if os.path.exists(c): os.environ['BRAWLER_CORE'] = c; break
from core_lb2 import LB2

NEO = '/data/roms/garou.neo'
STA = '/data/neogeo_dict/garou/cap'
VS = STA + '/vs.state'
TASK = {'P1': 0x100400, 'P2': 0x100500}

class Garou(LB2):
    def __init__(self): super().__init__(NEO)

    def obj(self, base):
        r = lambda o, n=2: self.r(base + o, n)
        rs = lambda o, n=2: self.rs(base + o, n)
        return {'ch': r(0x10), 'x': rs(0x20, 4) / 65536, 'y': rs(0x24, 4) / 65536, 'h': rs(0x28, 4) / 65536,
                'vx': rs(0x34, 4) / 65536, 'vh': rs(0x3C, 4) / 65536, 'anim': r(0x60), 'rec': r(0x64), 'step': r(0x66, 1),
                'fid': r(0x5E) & 0x7FF, 'f6a': r(0x6A, 1), 'tick': r(0x6F, 1), 'face': r(0x58, 1),
                'nbox': r(0x7A, 1), 'boxp': r(0x7B, 4) & 0xFFFFFF, 'raw': bytes(self.ram[base - 0x100000:base - 0x100000 + 0x100])}

    def rows_now(self):
        return {k: self.obj(v) for k, v in TASK.items()}

    def play(self, s, p2='', each=None):
        """an input script 'N:keys,...' -> one row per frame (after the frame ran)"""
        out = []
        for part in s.split(','):
            if not part: continue
            n, k = part.split(':')
            for _ in range(int(n)):
                self.pad = [set(k), set(p2)]; self.core.retro_run(); self.frame += 1
                row = self.rows_now()
                if each: each(self, row)
                out.append(row)
        self.pad = [set(), set()]
        return out
