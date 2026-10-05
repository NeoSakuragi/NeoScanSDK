#!/usr/bin/env python3
"""Boot Kizuna Encounter into a 2P fight (boot.py's default inputs: the select times out) with P1 = Kim (5) first and
Rosa (4) as his partner, P2 = Hayate (0) + Eagle (1): the team record $1088EC (P1 first, P2 first, P1 second, P2
second; filled by the select) poked after the select, then save the 'vs' state.
    python3 mkvs.py FRAMES [SAVE_FRAME|-] [SNAPS|-] [P1FIRST P1SECOND P2FIRST P2SECOND] [NAME]"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot
a = sys.argv[1:]
N = int(a[0]); save = int(a[1]) if len(a) > 1 and a[1] != '-' else None
snaps = a[2] if len(a) > 2 and a[2] != '-' else None
t = [int(x) for x in a[3:7]] if len(a) > 6 else [5, 4, 0, 1]
name = a[7] if len(a) > 7 else 'vs'
poke = ';'.join(f'{f}:1088EC={t[0]:02X},1088ED={t[2]:02X},1088EE={t[1]:02X},1088EF={t[3]:02X}' for f in range(2000, 2150))
p1, p2 = ['-'] * N, ['-'] * N                      # boot.py's default lanes, the 'a' presses stopped at 2300
for f in range(600, 606): p1[f] = 'o'
for f in range(650, 656): p2[f] = 'o'
for f in range(720, 726): p1[f] = 's'
for f in range(760, 766): p2[f] = 's'
for f in range(801, min(N, 2300)):
    if f % 20 < 3: p1[f] = p2[f] = 'a'
boot.boot(N, save=save, snaps=snaps, extra={'POKE': poke}, name=name, p1=p1, p2=p2)
