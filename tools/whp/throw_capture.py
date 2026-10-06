#!/usr/bin/env python3
"""WHP's throws in our emulator (the check of moves_whp's throw model): from the vs. state, P2 pinned 40 px in front
for the first frames, P1 holds forward / back and presses A+B -> per frame both fighters (anim relative, step, x / y px
world, def, flip, row, life).

    python3 throw_capture.py OUT.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_whp as cap
FLOOR = 0x4800

def fighter(r, k):
    o = cap.obj(r, k); a = r['anim'][k * 0x100:(k + 1) * 0x100]
    return dict(anim=o['anim'] - o['base'], step=o['step'], x=o['x'] / 128 + r['cam'], y=(o['y'] - r['floor']) / 128, defw=o['defw'],
                flip=o['flags'] >> 7 & 1, row=a[4], life=a[0x0C], base=o['base'])

RECIPES = {'fwd': 'R', 'back': 'L'}
def capture(name, chord='ab'):
    d = RECIPES[name]
    seq = f'2:-,6:{d},3:{d}{chord},3:{d},200:-'
    pk = ';'.join(f'{f}:100102={240 * 128 >> 8 & 255:02X},100103={240 * 128 & 255:02X}' for f in range(8))
    rows = cap.run(seq, '', pokes=pk, span=0x300)
    return [[fighter(r, 0), fighter(r, 1)] for r in rows]

if __name__ == '__main__':
    out = {k: capture(k) for k in RECIPES}
    json.dump(out, open(sys.argv[1], 'w'))
    for k, fr in out.items():
        an = []
        for p1, p2 in fr:
            if (p1['anim'], p2['anim']) not in an: an.append((p1['anim'], p2['anim']))
        print(k, [(hex(a), hex(b)) for a, b in an][:20], 'p2 row', fr[0][1]['row'], 'base', hex(fr[0][1]['base']))
