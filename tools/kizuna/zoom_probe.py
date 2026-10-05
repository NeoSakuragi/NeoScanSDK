#!/usr/bin/env python3
"""The camera's shrink ($10966A, 0-255; $FF = full size) against the fighters' distance: P2 walks away, then back."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cap_kz as c
rows = c.run('2:-,140:L,200:-,100:R', '2:-,200:L,40:-,200:R')
seen = {}
for r in rows:
    p1 = c.obj(r, 0x108200); p2 = c.obj(r, 0x108400)
    z = r['cam'][0x2A]; d = abs(p2['x'] - p1['x'])
    seen.setdefault(z, []).append(d)
for z in sorted(seen): print(f'zoom {z:3d} ({(z + 1) / 256:.3f})  distance {min(seen[z])}-{max(seen[z])} px  frames {len(seen[z])}')
