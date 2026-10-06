#!/usr/bin/env python3
"""Samurai Shodown II command lists (the recogniser $317BC / $31800, read in the 68000 code):
  list         long $6C9EA[char] -> up to 32 entries of 8 bytes:
               [long pattern][b4 flags][b5 result][b6 weapon mode: 0 armed, 1 unarmed, $FF any][b7 type]
  pattern      4-byte steps [mask][value][word frames], ended by a step whose mask is 0. A step matches when
               (input & mask) == value; input = stick (low nibble: 1 U, 2 D, 4 back, 8 forward) | buttons (A $10,
               B $20, C $40, D $80); frames = the window from the previous step (b4 bit 0: the first step must be
               HELD for `frames` = charge)
  b4           bit 0 charge, bit 1 needs no projectile of this player on screen (+$112)
  b7 type      handler $318F4[type]: 1 ground special (class 1 action b5, +$F7), 13 ground special needing +$F0 = 32,
               2 air special, 3 ground special when behind / facing the opponent's back ($31B1C), 9 / 10 / 12 the same
               (via $31B1C), 11 / 15 when the opponent's +$AB is set ($31B08), 5 / 6 / 8 cancels (table $6CA32),
               0 / 7 / 16 / 17 class 0 system actions (17: opponent within $6C8CA = 125 px: the throw;
               16: not Mizuki, sets +$C4)
  result       class 1 descriptor b5 of the action table $28310 (char*2 + weapon mode, class) -> anim(s)
    python3 commands_ss2.py [CHAR]      print the lists (default all 15 + Mizuki / Kuroko)"""
import sys, json
import ss2
from ss2 import u8, u16, u32

TYPES = {0: 'system', 1: 'ground', 2: 'air', 3: 'behind', 5: 'cancel', 6: 'cancel', 7: 'system', 8: 'cancel',
         9: 'behind', 10: 'behind', 11: 'opp_state', 12: 'behind', 13: 'ground_stand', 14: 'behind_stand',
         15: 'opp_state_stand', 16: 'system', 17: 'throw'}
DIR = {0: 'n', 1: 'U', 2: 'D', 4: 'B', 8: 'F', 5: 'UB', 9: 'UF', 6: 'DB', 10: 'DF'}
NUM = {0: '5', 1: '8', 2: '2', 4: '4', 8: '6', 5: '7', 9: '9', 6: '1', 10: '3'}

def steps_of(p):
    out = []
    for _ in range(32):
        out.append((u8(p), u8(p + 1), u16(p + 2))); p += 4
        if u8(p) == 0: break
    return out

def btn(v): return ''.join(n for k, n in ((0x10, 'A'), (0x20, 'B'), (0x40, 'C'), (0x80, 'D')) if v & k)

def notation(steps):
    """numpad notation: directions in order, '+' buttons; a button step's 'not' mask in brackets"""
    s = []
    for m, v, fr in steps:
        t = ''
        if m & 15: t += NUM.get(v & 15, '?')
        if m & 0xF0:
            b = btn(v & 0xF0); excl = btn(m & 0xF0 & ~v)
            t += ('+' if t else '') + b + (f'(not {excl})' if excl else '')
        s.append(t)
    return ' '.join(s)

def command_list(char):
    lst = u32(0x6C9EA + 4 * char); out = []
    for i in range(32):
        a = lst + 8 * i; p = u32(a)
        if p == 0: break
        st = steps_of(p)
        out.append(dict(i=i, pattern=hex(p), flags=u8(a + 4), result=u8(a + 5), mode=u8(a + 6), type=u8(a + 7),
                        kind=TYPES.get(u8(a + 7), '?'), steps=st, notation=notation(st),
                        charge=bool(u8(a + 4) & 1), one_projectile=bool(u8(a + 4) & 2)))
    return out

_starts = {}
def list_starts(char, mode, cls):
    """every entry-list start of one class table (the lists have no terminator: a list ends where another starts)"""
    key = (char, mode, cls)
    if key not in _starts:
        t = u32(0x28310 + 4 * ((char * 2 + mode) * 8 + cls)); st = set()
        if t:
            for sub in range(64):
                L = u32(t + 8 * sub) & 0xFFFFFF
                if 0x20000 <= L < 0x80000: st.add(L)
        _starts[key] = sorted(st)
    return _starts[key]

def descriptor(char, mode, cls, sub):
    """action descriptor ($27958): 8 bytes at long $28310[(char*2 + mode)*8 + cls] + 8 sub:
    [flags byte][24-bit list of 6-byte entries: (flag byte, 24-bit handler, word)][b4 b5 b6 b7]; an entry word is an
    animation (bits 0-9; bit 14: bits 10-13 = a voice index -> +$117) or, bit 15 set, a parameter for the handler
    (+$DE); the handler steps through the list with +$F9"""
    t = u32(0x28310 + 4 * ((char * 2 + mode) * 8 + cls))
    if not t: return None
    d = t + 8 * sub; L = u32(d); a = L & 0xFFFFFF
    nxt = [x for x in list_starts(char, mode, cls) if x > a]
    end = min(nxt[0] if nxt else a + 48, a + 6 * 24)
    ents = []
    while a < end:
        h = u32(a); w = u16(a + 4)
        if not 0x1000 <= h & 0xFFFFFF < 0x80000: break
        ents.append((h >> 24, h & 0xFFFFFF, w)); a += 6
    return dict(flags=L >> 24, list=hex(L & 0xFFFFFF), b=[u8(d + 4 + k) for k in range(4)], entries=ents)

def anims_of(d):
    return [w & 0x3FF for _, _, w in (d['entries'] if d else []) if not w & 0x8000]

def to_seq(steps, hold=3, charge_hold=None, facing_right=True):
    """an input lane for neogeo_sdl (SEQ): each direction step held `hold` frames (a charge step its frames + 4);
    buttons pressed with their step"""
    out = []
    F, B = ('R', 'L') if facing_right else ('L', 'R')
    for k, (m, v, fr) in enumerate(steps):
        d = v & 15 if m & 15 else 0
        s = ('U' if d & 1 else '') + ('D' if d & 2 else '') + (B if d & 4 else '') + (F if d & 8 else '')
        s += ''.join(n for k2, n in ((0x10, 'a'), (0x20, 'b'), (0x40, 'c'), (0x80, 'd')) if v & k2 and m & 0xF0)
        n = (fr + 4 if charge_hold is None else charge_hold) if (k == 0 and fr and steps is not None and charge_hold != 0
                                                                 and _charge.get(id(steps))) else hold
        out.append(f'{n}:{s or "-"}')
    return ','.join(out)
_charge = {}

if __name__ == '__main__':
    chars = [int(sys.argv[1])] if len(sys.argv) > 1 else [c for c in range(18) if c != 10]
    for c in chars:
        print(f'== {c} {ss2.NAMES[c]}')
        for e in command_list(c):
            d = descriptor(c, 0 if e['mode'] in (0, 0xFF) else 1, 0 if e['kind'] in ('system', 'throw') else 1, e['result'])
            anims = anims_of(d)
            print(f"  {e['i']:2d} {e['kind']:12s} f{e['flags']:02x} m{e['mode']:02x} -> {e['result']:3d} anims {anims}  {e['notation']}"
                  f"  [{' '.join(str(s[2]) for s in e['steps'])}]")
