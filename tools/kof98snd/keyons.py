#!/usr/bin/env python3
"""Key-on events per channel from a ymtap.lua capture: FM (port A $28, slots on), ADPCM-A (port B $00, bit 7 clear),
ADPCM-B (port A $10 = $80 start), SSG (port A $08-$0A level going from 0 to non-zero).
    python3 keyons.py TAP.txt [from_frame] -> {channel: [frames]}"""
import sys
from collections import defaultdict
FM = {1: 'FM1', 2: 'FM2', 5: 'FM3', 6: 'FM4'}          # YM2610 key-on channel codes of the 4 FM voices

def keyons(path, start=0):
    ev, f = defaultdict(list), 0
    lvl = [0, 0, 0]
    for l in open(path):
        p = l.split()
        if p[0] == 'f': f = int(p[1]); continue
        if p[0] == 'c' or f < start: continue
        reg, val = int(p[1], 16), int(p[2], 16)
        if p[0] == 'a':
            if reg == 0x28 and val & 0xF0 and (val & 7) in FM: ev[FM[val & 7]].append(f)
            elif reg == 0x10 and val & 0x80: ev['ADPCM-B'].append(f)
            elif 0x08 <= reg <= 0x0A:
                k = reg - 8
                if (val & 0x1F) and not lvl[k]: ev['SSG' + 'ABC'[k]].append(f)
                lvl[k] = val & 0x1F
        elif p[0] == 'b' and reg == 0x00 and not val & 0x80:
            for ch in range(6):
                if val >> ch & 1: ev[f'ADPCM-A{ch + 1}'].append(f)
    return ev

if __name__ == '__main__':
    ev = keyons(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    for ch in sorted(ev): print(ch, len(ev[ch]), ev[ch][:16])
