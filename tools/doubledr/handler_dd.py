#!/usr/bin/env python3
"""Capture one special's handler path (our emulator's WLOG: every 68000 write to the watched words with its pc):
Billy's 236 + A and + D from his vs state. Double Dragon has no per-move handler code: the path is the generic
recogniser ($2428C -> $24362 -> $244A6 writes the animation the button's column names), the step loader
($20B1A), the velocity setter ($20D48: header vx / vy at the first moving step), and the hit code ($258EC-$25DB4:
category / level -> damage, pushback, gauge). (+$DE-$E1 are not watched: the renderer uses them as scratch
for each group's offsets, $8660, every frame.) -> /data/neogeo_dict/doubledr/handler_path_billy_236.txt"""
import cap_dd as c, specials_dd as sp, commands_dd as cm
from fighters_dd import STATE
W = {'100446': 'P1 +$1C animation', '10042C': 'P1 +$02 step attr (bits 4-5 = level)', '100438': 'P1 +$0E vx (16.16)',
     '100550': 'P2 +$26 damage taken',
     '100628': 'P2 +$FE this hit', '10055A': 'P2 +$30 knock vx', '100510': 'P1 +$E6 gauge'}
LABEL = {0x244A6: 'recogniser: anim = entry column[button] ($244A6)', 0x20B52: 'step loader: attr ($20B52)',
         0x20D5E: 'velocity: header vx ($20D5E)', 0x20D36: 'velocity: cleared (step without bit 2)',
         0x20D8C: 'friction: v -= v >> shift ($20D8C)', 0x2592C: 'hit: category = header b1 & $60 ($2592C)',
         0x25D46: 'hit: damage = table x guts ($25D46)', 0x25D4A: 'hit: damage taken += ($25D4A)',
         0x25AC8: 'hit: knock velocity from $2664A[cat][level] ($25AC8)', 0x25DAC: 'hit: attacker gauge ($25DAC)'}
if __name__ == '__main__':
    e = cm.entries(0)[2]                      # 236 + A/B/C/D -> anims 83-86
    out = []
    for b in 'ad':
        seq = '30:R,12:-,' + sp.inputs(e, b) + ',90:-'
        rows = c.run(seq, load=STATE.format(0), ram=False, wlog=list(W))
        out.append(f'== Billy {cm.notation(e)} button {b.upper()} (input {seq})')
        last = {}
        for l in rows[0]['wlog']:
            f, wv, pc = l.split()[:3]; a, v = wv.split('='); v = v.split('/')[0]; pc = int(pc[3:], 16)
            if int(f) < 40 or last.get(a) == v: continue
            last[a] = v
            out.append(f'{int(f):4d} {W[a]:38s} = {v}  pc={pc:06X} {LABEL.get(pc, "")}')
    open('/data/neogeo_dict/doubledr/handler_path_billy_236.txt', 'w').write('\n'.join(out) + '\n')
    print('\n'.join(out))
