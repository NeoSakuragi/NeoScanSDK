#!/usr/bin/env python3
"""Play an input sequence on The Last Blade 2 from a vs state in our emulator's core and log P1 / P2 per frame:
move (+$74), animation (+$72), script offset (+$7C), frame (+$C6), x (+$80), height (+$88), state class (+$150).
    python3 play_lb2.py 'SEQ' [--p2 SEQ] [--state vs] [--frames N] [--snap DIR]
SEQ = 'frames:keys,...' (keys U D L R a b c d; '-' none), the inputs of P1 (facing right in vs.state: R = forward)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core_lb2 import LB2, STA

P1, P2 = 0x105E00, 0x106000

def row(g, b):
    r = lambda o, n=2: g.r(b + o, n); s = lambda o: g.rs(b + o, 2)
    return dict(move=r(0x74), anim=r(0x72), off=r(0x7C, 4), frame=r(0xC6), x=s(0x80), h=s(0x88), z=s(0x84),
                cls=r(0x150), tick=r(0xB6, 1), face=r(0x41, 1), life=r(0x17E), gt=g.r(0x108292))

def expand(seq):
    out = []
    for part in seq.split(','):
        n, k = part.split(':'); out += [k.replace('-', '')] * int(n)
    return out

_G = []
def core():
    if not _G: _G.append(LB2())
    return _G[0]

def play(seq, p2='', state='vs', frames=None, each=None, g=None, snaps=None):
    g = g or core()
    g.load_state(f'{STA}/{state}.state'); g.frame = 0
    a, b = expand(seq), expand(p2) if p2 else []
    n = frames or len(a)
    log = []
    for f in range(n):
        g.pad = [set(a[f] if f < len(a) else ''), set(b[f] if f < len(b) else '')]
        if snaps and f in snaps:
            g.screenshot(os.path.join(snaps[f])); log.append((row(g, P1), row(g, P2))); continue
        g.core.retro_run(); g.frame += 1
        log.append((row(g, P1), row(g, P2)))
        if each: each(g, f)
    return log, g

if __name__ == '__main__':
    av = sys.argv[1:]
    p2 = av[av.index('--p2') + 1] if '--p2' in av else ''
    st = av[av.index('--state') + 1] if '--state' in av else 'vs'
    log, g = play(av[0], p2, st)
    prev = None
    for f, (p, q) in enumerate(log):
        k = (p['move'], p['anim'], p['frame'], q['anim'])
        if k != prev:
            print(f, 'P1 move %3x anim %3x frame %4d x %4d h %4d cls %3x | P2 anim %3x frame %4d life %d' %
                  (p['move'], p['anim'], p['frame'], p['x'], p['h'], p['cls'], q['anim'], q['frame'], q['life']))
        prev = k
