#!/usr/bin/env python3
"""Chain Lab driven from the desktop core (tools/brawler/harness.py): the same mailbox the page writes (fighter.h lab_t),
SNK's MVS BIOS (region US) as in the page, so a route played here and in the browser can be compared frame by frame.

    python3 labdrive.py OUT.json [ROUTE_JSON]    -> boots, Terry vs the dummy, plays SCRIPT, writes the trace
The trace: per frame P1 / dummy state, anim, step, x, hp and the lab events (frame, kind, node, how, val)."""
import json, os, sys, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness
harness.OPTIONS.update({'geolith_system_type': 'mvs', 'geolith_region': 'us'})   # = web_core.c
from harness import Brawler

LAB_MAGIC, EV_OFF, EV_N, EV_SIZE, BUF_OFF = 0, 16, 64, 6, 16 + 64 * 6
PACK_STAT_OFF, PACK_OFF = BUF_OFF + 16 + 128 * 24, BUF_OFF + 16 + 128 * 24 + 2   # fighter.h lab_t: pack_stat, pack (a data pack)
KINDS = ['START', 'HIT', 'END', 'SPECIAL', 'CHAINWIN']
# the scripted route: Terry's "AABA command" (A, A, B, forward+A), each press 2 frames, then the dummy recovers
SCRIPT = '2:a,9:-,2:a,9:-,2:b,12:-,2:Ra,90:-'
BOOT_FRAMES = 400                     # power on -> the MVS BIOS hands over to the game (attract)

class Lab:
    def __init__(self, rom=None, game=None):
        game = game or harness.GAME                     # the build whose symbols and fighter_t layout apply
        self.b = Brawler(rom=rom or os.path.join(game, 'brawler.neo'), game=game)
        self.lab = self.b.syms['lab']
    def poke(self, off, data):
        for i, v in enumerate(data): self.b.w(self.lab + off + i, 1, v)
    def start(self, fighter=0, dummy=1, tree=None):
        self.b.core.retro_reset(); self.b.frame = 0
        for _ in range(BOOT_FRAMES): self.b.core.retro_run()   # (RAM is not the game's yet: no hit log)
        self.b.frame = BOOT_FRAMES
        if tree is not None:
            self.poke(BUF_OFF, tree); self.poke(5, [fighter]); self.poke(7, [1])
        self.poke(0, b'LAB1'); self.poke(5, [fighter, dummy]); self.poke(4, [1])
        for k in range(3000):                                     # the game reads it on its next tick (after the BIOS's boot)
            self.b.core.retro_run(); self.b.frame += 1
            if self.b.r(self.lab + 8, 1) == 1: break
        else: raise RuntimeError('training not active')
        self.started = self.b.frame
        self.b.run(2)
    def events(self):
        n = self.b.r(self.lab + 9, 1); out = []
        for k in range(min(n, EV_N)):
            i = (n - min(n, EV_N) + k) & (EV_N - 1); a = self.lab + EV_OFF + i * EV_SIZE
            out.append((self.b.r(a, 2), KINDS[self.b.r(a + 2, 1)], self.b.r(a + 3, 1), self.b.r(a + 4, 1), self.b.r(a + 5, 1)))
        return out
    def snap(self):
        b = self.b; st = b.states
        return [(st[b.fget(i, 'state')], b.fget(i, 'anim'), b.fget(i, 'step'), round(b.fget(i, 'x'), 3), b.fget(i, 'hp')) for i in (0, 2)]
    def play(self, script):
        tr = []
        for part in script.split(','):
            n, k = part.split(':')
            for _ in range(int(n)):
                self.b.run(1, p1=k); tr.append([self.b.r(self.lab + 10, 2)] + self.snap())
        return tr

if __name__ == '__main__':
    out = sys.argv[1]
    tree = list(open(sys.argv[2], 'rb').read()) if len(sys.argv) > 2 else None
    L = Lab()
    L.start(0, 1, tree)
    tr = L.play(SCRIPT)
    ev = L.events()
    json.dump({'script': SCRIPT, 'trace': tr, 'events': ev, 'combo': [L.b.r(L.lab + 12, 1), L.b.r(L.lab + 14, 2)]}, open(out, 'w'))
    for e in ev: print(e)
    print('combo hits / damage:', L.b.r(L.lab + 12, 1), L.b.r(L.lab + 14, 2))
    L.b.screenshot(out.replace('.json', '.png'))
