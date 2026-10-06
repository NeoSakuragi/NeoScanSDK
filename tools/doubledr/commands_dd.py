#!/usr/bin/env python3
"""Double Dragon command lists (decoded from the recogniser $2428C / $24362; table $24506 + word[$24506 + 2 char]).
Entry = 32 bytes, list ends with $FFFF:
  +0 flags: bit 0 air entry (the fighter must be airborne, +$01 bit 7) else ground only; bit 1 = mash entry (count
     presses of the button in the last 64 frames >= the byte at +2 + button); bit 2 = needs a multi-button press;
     bit 3 = only when the opponent is not in animations $47-$4A while flagged +$F3 bit 2
  +1 button mask (bits 4-7 = A B C D, newly pressed this frame, +$1A)
  +2 .. +$17 the direction pattern, newest first: [window][value] pairs, 0 word ends it, walked over the stick
     history (+$40 newest, 64 frames). window bit 7 clear: the stick must EQUAL value within the next (window & $7F)
     frames; window bit 7 set = a CHARGE step: the direction bit (value 0 = neutral) must be present on
     (window & $7F) + 1 frames, with at most 11 non-matching frames over the whole pattern [code $243CE-$24478,
     meas: Marian [2]8 needs 33 frames of down]. Stick bits 1 up 2 down 4 back
     8 forward (left / right swapped by the code when the fighter faces left).
  +$18 four words = the animation for A / B / C / D (the variant!), negative = a resource-checked id ($2380E).
The FIRST matching entry wins; the button pressed picks the column (D > C > B > A when several)."""
import sys, json, dd

DIRS = {0: 'n', 1: 'U', 2: 'D', 4: 'B', 8: 'F', 5: 'UB', 9: 'UF', 6: 'DB', 10: 'DF'}
NUM = {0: '5', 1: '8', 2: '2', 4: '4', 8: '6', 5: '7', 9: '9', 6: '1', 10: '3'}
TABLE = 0x24506

def entries(ch):
    a = TABLE + dd.u16(TABLE + 2 * ch); out = []
    while dd.u16(a) != 0xFFFF:
        b = dd.P[dd.off(a):dd.off(a) + 32]
        pat = []
        for i in range(2, 24, 2):
            if b[i] == 0 and b[i + 1] == 0: break
            pat.append((b[i] & 0x7F, bool(b[i] & 0x80), b[i + 1]))
        anims = [int.from_bytes(b[24 + 2 * k:26 + 2 * k], 'big', signed=True) for k in range(4)]
        out.append(dict(addr=a, flags=b[0], buttons=b[1], pattern=pat, anims=anims, raw=b.hex()))
        a += 32
    return out

def notation(e):
    if e['flags'] & 2:
        return 'mash ' + '/'.join('ABCD'[k] for k in range(4) if e['buttons'] >> (4 + k) & 1)
    seq = []
    for w, cont, v in reversed(e['pattern']):
        s = NUM.get(v, f'?{v:X}') if not cont else (f'[{NUM.get(v, "?") if v else "5"}]' if w else NUM.get(v, '?'))
        seq.append(s)
    btn = ''.join('ABCD'[k] for k in range(4) if e['buttons'] >> (4 + k) & 1)
    return ('j.' if e['flags'] & 1 else '') + ''.join(seq) + '+' + btn

if __name__ == '__main__':
    ch = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    for e in entries(ch):
        print(f"{e['addr']:06X} f{e['flags']:02X} b{e['buttons']:02X} {notation(e):16s} anims {e['anims']}  pat {e['pattern']}")
