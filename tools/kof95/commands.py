#!/usr/bin/env python3
"""KOF95 special-move input commands, decoded from the ROM (recogniser at $B2C0, found 2026-10-02).

Per character, 8 command ids at the start of its 128-byte record ($7AEF2 + id*128; the physics fields are at +$24),
copied to object +$E8..+$EF; 0 = unused. Slot k of that list sets
bit k of the player's command byte ($10D7C0 for P1) when its motion is recognised; the character's move dispatcher
then runs entry k of its move table (pointer list at $77DE, indexed by character).
Command id -> motion pattern: pointer table $7A6B0 + (id-1)*4. A pattern is a list of 4-byte steps ending with $FF:
  [type][input][mask][frames]
  input: low nibble = stick (1 up, 2 down, 4 back, 8 forward; the game mirrors left/right for a fighter facing
         left), high nibble = buttons (A $10, B $20, C $40, D $80)
  mask : bits that may be anything (the step compares input & (~mask | input) with input)
  type : bit 0 = hold (charge): the input must be held `frames` frames; otherwise `frames` is the time allowed to
         reach the next step (0 = default). Bit 7 on the button step: all listed buttons together.
Condition per command id: byte table $B388 + (id-1) selects a check routine (jump table $B4A0): airborne-only, mash,
super (power gauge full or life <= 64), etc. (RULES; names from reading the routines, the flag-based ones are guesses).
    python3 commands.py [name ...]"""
import struct, sys
import rom

TABLE_IDS, TABLE_PATTERNS, TABLE_RULES = 0x7AEF2, 0x7A6B0, 0xB388   # ids: 128-byte character record, +0
STICK = {0: '5', 1: '8', 2: '2', 4: '4', 8: '6', 5: '7', 9: '9', 6: '1', 10: '3'}   # numpad, facing right
BUTTONS = [(0x10, 'A'), (0x20, 'B'), (0x40, 'C'), (0x80, 'D')]

def command_ids(prom, cid):
    return list(prom[TABLE_IDS + cid * 128:TABLE_IDS + cid * 128 + 8])

def pattern(prom, cmd):
    a = struct.unpack_from('>I', prom, TABLE_PATTERNS + (cmd - 1) * 4)[0]; steps = []
    while prom[a] != 0xFF and len(steps) < 24:
        steps.append(tuple(prom[a:a + 4])); a += 4
    return steps

RULES = {0: 'ground', 1: 'normal', 2: 'airborne', 3: 'timer', 4: 'in the air', 6: 'mash', 7: 'flagged',
         8: 'always', 9: 'super (full gauge or life <= 64)', 10: 'always', 11: 'super, ground', 12: 'super, opponent check'}

def notation(steps):
    """numpad motion, e.g. '236P', '[2]35f 8P' (hold down 35 frames, then up), '21416BC'. The recogniser folds C onto A
    and D onto B unless the button step has type bit 7, so A in a pattern means 'P' (A or C), B means 'K' (B or D)."""
    out = []
    for typ, inp, mask, frames in steps:
        stick, btn = inp & 15, inp >> 4
        if btn:
            if typ & 0x80: out.append(''.join(n for b, n in BUTTONS if inp & b))
            else: out.append(('P' if inp & 0x10 else '') + ('K' if inp & 0x20 else ''))
        elif typ & 1:
            out.append(f'[{STICK.get(stick, "?")}]{frames}f ')
        else:
            out.append(STICK.get(stick, '?'))
    return ''.join(out)

def cast_commands(prom):
    res = {}
    for cid, name in enumerate(rom.CAST):
        res[name] = [{'slot': k, 'command': c, 'rule': prom[TABLE_RULES + c - 1], 'condition': RULES.get(prom[TABLE_RULES + c - 1], '?'),
                      'pattern': [list(s) for s in pattern(prom, c)], 'input': notation(pattern(prom, c))}
                     for k, c in enumerate(command_ids(prom, cid)) if c]
    return res

if __name__ == '__main__':
    prom, _ = rom.load(); cmds = cast_commands(prom)
    for name in sys.argv[1:] or rom.CAST:
        print(f'{name:12}', '  '.join(f"{c['slot']}:{c['input']}" + ('' if c['rule'] in (1, 8, 10) else f"({c['condition']})") for c in cmds[name]))
