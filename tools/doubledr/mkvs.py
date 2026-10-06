#!/usr/bin/env python3
"""Make a vs state with chosen select-screen cursor moves (Double Dragon): P1 / P2 move the cursor with the given
directions first, then press A until the fight. -> /data/neogeo_dict/doubledr/cap/<name>.state (frame 1150)
    python3 mkvs.py NAME P1MOVES P2MOVES     (moves like 'DD' or 'RD', '-' = none)"""
import sys, boot

def make(name, m1='', m2='', n=1400, save=1300, snaps=None, extra=None, t0=900):
    p1 = ['-'] * n; p2 = ['-'] * n
    for f in range(600, 606): p1[f] = 'o'
    for f in range(650, 656): p2[f] = 'o'
    for f in range(720, 726): p1[f] = 's'
    for f in range(760, 766): p2[f] = 's'
    for lane, moves in ((p1, m1), (p2, m2)):
        for i, d in enumerate(moves.strip('-')):
            for f in range(t0 + 12 * i, t0 + 4 + 12 * i): lane[f] = d
    for f in range(801, 804): p1[f] = 'a'                       # skips the how-to-play screen
    for f in range(t0 + 100, t0 + 260):                         # pick + whatever follows (mode select)
        if f % 20 < 3: p1[f] = p2[f] = 'a'
    boot.boot(n, save=save, snaps=snaps, p1=p1, p2=p2, name=name, extra=extra)

if __name__ == '__main__':
    make(sys.argv[1], sys.argv[2], sys.argv[3])
