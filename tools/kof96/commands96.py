#!/usr/bin/env python3
"""KOF96 special-move inputs, decoded from the command recogniser ($11C76, per player: P1 $11C42, P2 $11C4E).

Each frame the player's 60-byte input history is shifted (newest last); a byte = stick (bits 0-3: up, down, left,
right) | buttons (bits 4-7: A, B, C, D). Command lists: $71B9E + id * 8 = [list facing left, list facing right]
(chosen by the two fighters' x, so forward/back are already resolved); a list = pattern pointers ended by a negative
long. Pattern: [n steps][window frames][hold:16] + n steps [type*4][value] (oldest first), checked newest first: the last step must
match the newest history byte, the earlier ones are searched backwards within `window` frames in total. A match sets the
command's bit pair in the player's flag block and stores the buttons pressed in its result byte, which the
character's move code reads (e.g. & $50 = A or C, & $A0 = B or D). A pattern with n < 0 is disabled.

Step types ($11D3E for the newest step, $11D72 for the others):
  0 byte equal          1 any bit shared        2 buttons equal       3 charge: byte equal held >= hold frames
  4 charge: any bit held >= hold frames         5 stick equal         6 stick bits, no buttons
  7 buttons, no stick   8 stick bits and button bits                  9 stick equal and a button bit
KOF98 adds (handlers $174C6/$174E6, newest step $17648/$1766E):
  10 stick equal, no button                     11 a button bit while the stick has none of the value's stick bits"""
import json, os, sys
import rom96

TABLE = 0x71B9E
STICK = {0: 'n', 1: 'u', 2: 'd', 4: 'l', 8: 'r', 5: 'ul', 9: 'ur', 6: 'dl', 10: 'dr'}
BUTTONS = 'ABCD'

def lists(m, cid, ex=0):
    """[list facing left, list facing right]. KOF98 (recogniser $1720E, same pattern format): table $B14A2, two
    entries per fighter, (id*2 + ex)*8 with ex = 1 for the EX version of the character"""
    if m.game == 'kof98': a = 0xB14A2 + (cid * 2 + ex) * 8
    elif m.game == 'kof99': a = 0xBA866 + cid * 8           # selected at $11B04 by object +$184; no EX lists
    else: a = TABLE + cid * 8
    return [m.u32(a), m.u32(a + 4)]

def patterns(m, lst):
    out, a = [], lst
    while True:
        p = m.u32(a); a += 4
        if p & 0x80000000 or p == 0: break
        n = m.u8(p)
        if n & 0x80: out.append(None); continue
        win, hold = m.u8(p + 1), m.u16(p + 2)
        out.append({'addr': hex(p), 'window': win, 'hold': hold,
                    'steps': [(m.u8(p + 4 + 2 * i) >> 2, m.u8(p + 5 + 2 * i)) for i in range(n)]})   # type byte = 4 * type (long table offset)
    return out

def stick_name(v, facing_right):
    """numpad notation relative to the fighter's facing: 6 = forward"""
    fwd, back = (8, 4) if facing_right else (4, 8)
    v &= 15
    if v == 0: return '5'
    num = {0: 5, fwd: 6, back: 4, 1: 8, 2: 2, 1 | fwd: 9, 1 | back: 7, 2 | fwd: 3, 2 | back: 1}
    return str(num.get(v, f'?{v:X}'))

def btn_name(v):
    b = ''.join(BUTTONS[i] for i in range(4) if v >> (4 + i) & 1)
    return {'AC': 'P', 'BD': 'K'}.get(b, b)

def step_text(t, v, hold, facing_right):
    st, bt = stick_name(v, facing_right), btn_name(v)
    if t == 0: return st + bt if bt else st
    if t == 1: return f'any({st if v & 15 else ""}{bt})'
    if t == 2: return bt                                  # '' = no button held
    if t in (3, 4): return f'[{st}{bt}]{hold}'          # charge: hold for `hold` frames
    if t == 5: return st
    if t == 6: return st
    if t == 7: return bt
    if t == 8: return st + bt
    if t == 9: return st + bt
    if t == 10: return st                                   # KOF98: stick exactly, no button
    if t == 11: return bt                                   # KOF98: button, stick off the value's directions
    return f'?{t}:{v:02X}'

def notation(p, facing_right=True):
    """charge steps (a latched held state, checked first by the game) are written first, as they are performed"""
    order = [s for s in p['steps'] if s[0] in (3, 4)] + [s for s in p['steps'] if s[0] not in (3, 4)]
    return ' '.join(x for x in (step_text(t, v, p['hold'], facing_right) for t, v in order) if x)

def decode_all(m, cast):
    out = {}
    for cid, name in enumerate(cast):
        L = patterns(m, lists(m, cid)[1])                    # facing right
        out[name] = [None if p is None else dict(p, notation=notation(p)) for p in L]
    return out

if __name__ == '__main__':
    from export96 import CAST
    prom, _ = rom96.load(); m = rom96.Mem(prom)
    d = decode_all(m, CAST)
    json.dump(d, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'commands96.json'), 'w'), indent=1)
    for name in (sys.argv[1:] or CAST):
        print(name, [(k, p['notation'] if p else None, p['window'] if p else None) for k, p in enumerate(d[name])])
