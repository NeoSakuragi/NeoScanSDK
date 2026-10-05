#!/usr/bin/env python3
"""Kizuna Encounter's command lists (the COMND task, $2C2F6; list per character long[$604D0 + 4 char]):
entries [pattern pointer l][condition w][command w] up to a pointer outside P1. The command word is written to the
fighter's +$20 by the COMND task and picked up by the character's state code. A pattern is 4-byte steps, newest
first: [type][0][window][value]; type bit 5 = the oldest step (the end of the list), bit 6 = the button step;
low nibble: 2 / 3 stick (within `window` frames), 4 bits included, 5 byte equal (stick + buttons), $B charge (held
`window` frames, flag $A0). Values: bits 0-3 up / down / left / right (right = forward when facing right), 4-7 A-D.
    python3 commands_kz.py [char]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kz

def pattern(p):
    out = []
    for i in range(16):
        e = kz.P[p + 4 * i:p + 4 * i + 4]
        if e[2:4] == b'\xff\xff' and e[0] == 0: break
        out.append((e[0], e[2], e[3]))
        if e[0] & 0x20: break
    return out

NUM = {0: '5', 1: '8', 2: '2', 4: '4', 8: '6', 5: '7', 9: '9', 6: '1', 10: '3'}
BTN = {16: 'A', 32: 'B', 64: 'C', 128: 'D'}
def notation(steps):
    s = ''
    for typ, win, val in reversed(steps):
        d = NUM.get(val & 15, '?'); b = ''.join(v for k, v in BTN.items() if val & k)
        if typ & 0x0F == 0x0B: s += f'[{d}]'
        elif typ & 0x40 or b: s += ('' if d == '5' else d) + b
        else: s += d
    return s

def commands(ch):
    a = kz.u32(0x604D0 + 4 * ch); out = []
    while True:
        p = kz.u32(a)
        if not 0x10000 <= p < 0x100000: break
        st = pattern(p)
        out.append({'entry': a, 'pattern': p, 'cond': kz.u16(a + 4), 'command': kz.u16(a + 6), 'steps': st, 'notation': notation(st)})
        a += 8
    return out

if __name__ == '__main__':
    for c in commands(int(sys.argv[1]) if len(sys.argv) > 1 else 5):
        print(f"{c['entry']:06X} {c['pattern']:06X} cond {c['cond']:04X} cmd {c['command']:02X} {c['notation']:10s}",
              ' '.join(f'{t:02X}/{w:02X}/{v:02X}' for t, w, v in c['steps']))
