#!/usr/bin/env python3
"""export_garou.timeline (the animation player $11C9E read from the ROM) vs Garou in our emulator: for each input the
frames (step's frame id per frame) of every animation the move plays, from the frame it starts.

    python3 check_timeline.py            -> per move: frames compared / equal, the first difference"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import garou as G, export_garou as X
from cap_garou import Garou, VS, STA

D = {'1': 'DL', '2': 'D', '3': 'DR', '4': 'L', '5': '', '6': 'R', '7': 'UL', '8': 'U', '9': 'UR'}
def seq(m):
    """'236A' -> each direction 3 frames, then the button 4 frames with the last direction"""
    dirs = [c for c in m if c.isdigit()]; btn = ''.join(c.lower() for c in m if c.isalpha())
    return ','.join(f'3:{D[d]}' for d in dirs) + f',4:{D[dirs[-1]] if dirs else ""}{btn}'

CASES = [('vs', '5A'), ('vs', '5B'), ('vs', '5C'), ('vs', '5D'), ('vs', '2A'), ('vs', '2B'), ('vs', '2C'), ('vs', '2D'),
         ('close', '5C'), ('close', '5D'), ('close', '6A'), ('close', '6B'), ('vs', '236A'), ('vs', '214A'),
         ('vs', '236B'), ('vs', '214B'), ('vs', '236C'), ('vs', '214C'), ('vs', '236D'), ('vs', '214D')]

def runs(rows, who='P1'):
    """[(anim, [fid per frame])] in play order"""
    out = []
    for r in rows:
        o = r[who]
        if not out or out[-1][0] != o['anim'] or o['step'] < out[-1][2]:
            out.append([o['anim'], [], o['step']])
        out[-1][1].append(o['fid']); out[-1][2] = o['step']
    return [(a, f) for a, f, _ in out]

def main():
    g = Garou(); res = {}
    states = {'vs': open(VS, 'rb').read(), 'close': open(STA + '/close.state', 'rb').read()}
    for st, m in CASES:
        g.load(states[st])
        rows = g.play('1:,' + seq(m.lstrip('5')) + ',100:')
        tot = eq = 0; bad = None
        for a, fids in runs(rows):
            if a in (0, 1, 2, 3, 4, 6, 7): continue
            tl = X.timeline(1, a)
            exp = [r['st']['fid'] for r in tl]
            n = min(len(exp), len(fids))
            for k in range(n):
                tot += 1; eq += exp[k] == fids[k]
                if exp[k] != fids[k] and bad is None: bad = (hex(a), k, exp[k], fids[k])
            if len(fids) < len(exp) and bad is None and a not in (0x66,): pass
        res[f'{st}:{m}'] = {'frames': tot, 'equal': eq, 'first_diff': bad,
                            'anims': [f'{a:x}:{len(f)}/{len(X.timeline(1, a))}' for a, f in runs(rows) if a not in (0, 1, 2, 3, 4, 6, 7)]}
        print(f'{st}:{m}', res[f'{st}:{m}'])
    return res

if __name__ == '__main__': main()
