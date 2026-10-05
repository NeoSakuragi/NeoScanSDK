#!/usr/bin/env python3
"""SNK Sound Driver songs (KOF98, Kizuna Encounter: games98.py) as YM2610 register writes: the song98.py model's chip events turned into the writes the driver makes
($2003, $2447, $130C, $035D, $0825; docs/kof98_sound_driver.md "Output stage"), and a register-level comparison with a
capture (ymtap.lua in MAME, capture98.py in our emulator).

    python3 regs98.py M1.bin 0x23 CAP.txt          compare model writes with the capture, sequencer tick by tick
    python3 regs98.py M1.bin 0x23 CAP.txt --show N  print the first N differing ticks

writes(): [(irq, port, reg, val)], irq = sequencer interrupt (1 = the first after the command), port 'a' / 'b'.
capture(): the same from a capture, plus the timer interrupt (real time) each write happened at."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from song98 import Song, CHANNELS

FM = {'FM1': ('a', 1, 1), 'FM2': ('a', 2, 2), 'FM3': ('b', 1, 5), 'FM4': ('b', 2, 6)}   # port, reg offset, $28 code
CARRIERS = [8, 8, 8, 8, 0x0C, 0x0E, 0x0E, 0x0F]          # $26EF by algorithm; bit i = operator i in register order
# (S1, S3, S2, S4: bit 0 S1, 1 S3, 2 S2, 3 S4)

def cmd_of(field):
    """a capture's command field: MAME's ymtap.lua logs the 68000's word ($2300), capture98.py the Z80's byte ($23)"""
    v = int(field, 16)
    return v >> 8 if len(field) > 2 else v

def writes(s):
    """the model's events -> register writes; first the driver's song start (games98 'start': KOF98 ADPCM-B stop,
    FM keys off, ADPCM-A 1-3 dump; Kizuna ADPCM-B stop, FM keys off)"""
    out = [(0, p, r, v) for p, r, v in s.g['start']]
    alg = {n: 0 for n in FM}; b4 = {n: 0xC0 for n in FM}    # pan shadow: both sides
    tls = {n: [0] * 4 for n in FM}                          # TL shadow ($F8C9 / $F950 + $10 + 4*op)
    a_on = set()                                            # Ver 0.1: ADPCM-A channels keyed and not dumped
    w = lambda irq, p, r, v: out.append((irq, p, r, v & 0xFF))
    for irq, tick, ch, kind, kw in s.out:
        if ch in FM:
            p, o, code = FM[ch]
            if kind == 'patch':
                d = [s.m.rd(kw['addr'] + i) for i in range(30)]
                alg[ch] = d[28] & 7
                for i in range(4):                     # $1350: the new algorithm's carriers keep the shadow's TL
                    if not CARRIERS[alg[ch]] >> i & 1: tls[ch][i] = d[4 + i]
                for g in range(7):
                    for i in range(4):
                        w(irq, p, 0x30 + 0x10 * g + 4 * i + o, tls[ch][i] if g == 1 else d[4 * g + i])
                w(irq, p, 0xB0 + o, d[28])
                b4[ch] = b4[ch] & 0xC0 | d[29] & 0x3F; w(irq, p, 0xB4 + o, b4[ch])
            elif kind == 'tl':
                for i in range(4):
                    if CARRIERS[alg[ch]] >> i & 1: tls[ch][i] = kw['tl']; w(irq, p, 0x40 + 4 * i + o, kw['tl'])
            elif kind == 'modtl':
                for i in range(4):
                    if not CARRIERS[alg[ch]] >> i & 1: tls[ch][i] = kw['tl']; w(irq, p, 0x40 + 4 * i + o, kw['tl'])
            elif kind in ('fnum', 'vib'):
                w(irq, p, 0xA4 + o, kw.get('hi', kw['block'] << 3 | kw['fnum'] >> 8)); w(irq, p, 0xA0 + o, kw['fnum'])
            elif kind == 'keyon': w(irq, 'a', 0x28, 0xF0 | code)
            elif kind == 'keyoff': w(irq, 'a', 0x28, code)
            elif kind == 'pan': b4[ch] = b4[ch] & 0x3F | kw['pan']; w(irq, p, 0xB4 + o, b4[ch])
            elif kind == 'ams_pms': b4[ch] = b4[ch] & 0xC0 | kw['p'] & 0x3F; w(irq, p, 0xB4 + o, b4[ch])
            elif kind == 'lfo': w(irq, 'a', 0x22, kw['reg22'])
            elif kind == 'optl':                       # Ver 0.0 operator level effect ($18B5)
                op = (0x40, 0x44, 0x48, 0x4C).index(kw['reg']); tls[ch][op] = kw['tl']; w(irq, p, kw['reg'] + o, kw['tl'])
            continue
        if kind == 'bogus_fnum':                       # the FM pitch path run on an ADPCM channel ($05, any ADPCM)
            w(irq, 'b', kw['reg_hi'], kw['word'] >> 8); w(irq, 'b', kw['reg_lo'], kw['word']); continue
        if kind == 'bogus_key': w(irq, 'a', 0x28, kw['reg28']); continue
        if ch.startswith('A'):
            c = int(ch[1]) - 1; bit = 1 << c
            if kind == 'akey':
                if s.g.get('a_dump_first') and ch in a_on: w(irq, 'b', 0x00, 0x80 | bit)   # Ver 0.1: a note on a
                a_on.add(ch)                                     # sounding channel dumps it before the level
                w(irq, 'b', 0x08 + c, kw['pan'] | kw['level'] & 0x1F)
                if 'rec_level' in kw: w(irq, 'b', 0x08 + c, kw['rec_level'])   # Ver 0.0, 11-byte records ($0277)
                w(irq, 'b', 0x00, 0x80 | bit); w(irq, 'a', 0x1C, bit); w(irq, 'a', 0x1C, 0)
                w(irq, 'b', 0x10 + c, kw['start']); w(irq, 'b', 0x18 + c, kw['start'] >> 8)
                w(irq, 'b', 0x20 + c, kw['end']); w(irq, 'b', 0x28 + c, kw['end'] >> 8)
                w(irq, 'b', 0x00, bit)
            elif kind == 'alevel': w(irq, 'b', 0x08 + c, kw['pan'] | kw['level'])
            elif kind == 'adump' and (ch in a_on or not s.g.get('a_dump_first')):   # Ver 0.1: only a sounding one
                w(irq, 'b', 0x00, 0x80 | bit); w(irq, 'a', 0x1C, bit); w(irq, 'a', 0x1C, 0); a_on.discard(ch)
            continue
        if ch == 'B':
            if kind == 'bkey':
                for r, v in ((0x11, 0), (0x14, 0), (0x15, 0), (0x10, 1), (0x1C, 0x80), (0x1C, 0), (0x10, 0),
                             (0x19, kw['deltan']), (0x1A, kw['deltan'] >> 8), (0x12, kw['start'] or 0),
                             (0x13, (kw['start'] or 0) >> 8), (0x14, kw['end'] or 0), (0x15, (kw['end'] or 0) >> 8),
                             (0x1B, kw['vol']), (0x10, 0x80), (0x11, kw['pan'])):
                    w(irq, 'a', r, v)
            elif kind == 'boff': w(irq, 'a', 0x11, 0)
            elif kind == 'bstop': w(irq, 'a', 0x10, 1); w(irq, 'a', 0x10, 0)
            elif kind == 'bvol': w(irq, 'a', 0x1B, kw['vol'])
            elif kind == 'bpitch': w(irq, 'a', 0x19, kw['deltan']); w(irq, 'a', 0x1A, kw['deltan'] >> 8)
    return out

MUSIC_SKIP = {('a', 0x1C), ('a', 0x27), ('a', 0x24), ('a', 0x25), ('a', 0x26), ('a', 0x07), ('a', 0x08), ('a', 0x09), ('a', 0x0A)}
# timer control / SSG: not written by the music path; $1C (ADPCM end-flag reset) and ADPCM-B $10 = 0 are also written by
# the interrupt handler's end-of-sample poll (driven by the chip's status, every interrupt after a sample ends): compare()
# leaves them out on both sides (neither changes the sound)

def capture(path, cmd):
    """-> (writes [(seq_irq, timer_irq, port, reg, val)] from the command on, preamble [(port, reg, val)] before it).
    seq_irq counts the interrupts that ran the sequencer (q 1), timer_irq every timer-A interrupt (i, bit 0)."""
    pre, out = [], []
    seq = tim = 0; started = False
    for l in open(path):
        p = l.split()
        if not p: continue
        if p[0] == 'i':
            if started and int(p[1], 16) & 1: tim += 1
            continue
        if p[0] == 'q':
            if started and p[1] == '1': seq += 1
            continue
        if p[0] in ('f', 's'): continue
        if p[0] == 'c':
            if not started and p[-1] != 'blocked' and cmd_of(p[1]) == cmd: started = True
            continue
        port, reg, val = p[0], int(p[1], 16), int(p[2], 16)
        if started: out.append((seq, tim, port, reg, val))
        else: pre.append((port, reg, val))
    return out, pre

def compare(data, cmd, path, show=0):
    cap, _ = capture(path, cmd)
    n = cap[-1][0]
    s = Song(data, cmd).run(irqs=n)
    mod = writes(s)
    by = lambda ws: {}
    a, b = {}, {}
    for q, t, p, r, v in cap:
        if (p, r) not in MUSIC_SKIP and (p, r, v) != ('a', 0x10, 0): a.setdefault(q, []).append((p, r, v))
    for q, p, r, v in mod:
        if q <= n and (p, r) not in MUSIC_SKIP and (p, r, v) != ('a', 0x10, 0): b.setdefault(q, []).append((p, r, v))
    ticks = sorted(set(a) | set(b))
    same = sum(1 for q in ticks if a.get(q) == b.get(q))
    same_set = sum(1 for q in ticks if sorted(a.get(q, [])) == sorted(b.get(q, [])))
    na = sum(len(v) for v in a.values()); nb = sum(len(v) for v in b.values())
    print(f'song ${cmd:02X}: {n} sequencer interrupts, {na} captured writes, {nb} model writes; interrupts with '
          f'writes {len(ticks)}: identical in order {same}, identical as a set {same_set}')
    shown = 0
    for q in ticks:
        if a.get(q) == b.get(q) or shown >= show: continue
        shown += 1
        fa = ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in a.get(q, []))
        fb = ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in b.get(q, []))
        print(f'-- irq {q}\n  cap   {fa}\n  model {fb}')
    return same, len(ticks)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    show = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == '--show' else 0
    compare(data, int(sys.argv[2], 16), sys.argv[3], show)
