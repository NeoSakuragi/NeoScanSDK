#!/usr/bin/env python3
"""Fatal Fury 3 songs as YM2610 register writes: song_ff3.py's chip events turned into the writes the driver makes
($1A8C, $2BC3, $14B5, $0359, $077D, $083E; docs/ff3_sound_driver.md "Output stage"), and a register-level comparison
with a capture.py capture, interrupt by interrupt.

    python3 regs_ff3.py M1.bin 0x23 CAP.txt          compare the model's writes with the capture
    python3 regs_ff3.py M1.bin 0x23 CAP.txt --show N  print the first N differing interrupts

writes(): [(irq, port, reg, val)], irq = timer interrupt since the command (0 = the command itself, in the main loop),
port 'a' / 'b'. capture(): the same from a capture, plus the interrupt kinds ('A' / 'B') to drive the model."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from song_ff3 import Song, CHANNELS, M1

FM = {'FM1': ('a', 1, 1), 'FM2': ('a', 2, 2), 'FM3': ('b', 1, 5), 'FM4': ('b', 2, 6)}   # port, reg offset, $28 code
CARRIERS = [8, 8, 8, 8, 0x0A, 0x0E, 0x0E, 0x0F]          # $2C8D by algorithm: bit 0 S1, 1 S2, 2 S3, 3 S4
TL_ORDER = [(0, 0x40), (1, 0x48), (2, 0x44), (3, 0x4C)]   # $2BC3: bit -> TL register (S1 $40, S3 $44, S2 $48, S4 $4C)
SLOT = [0, 2, 1, 3]                                       # register slot (S1, S3, S2, S4) -> patch operator index

def patch_regs(q, tl_shadow, b4):
    """$18A4: the 52-byte patch -> the 28 operator registers in write order ($30..$9C, 4 slots each), $B0, $B4.
    Carrier TLs (by the algorithm) keep the shadow's value."""
    rr = lambda v, n: (v >> n | v << (8 - n)) & 0xFF      # RRCA n times
    dt = lambda v: (-v) & 0xFF | 4 if v >= 4 else v        # $1A27: DT -1..-3 stored as $FF..$FD -> 5..7
    car = CARRIERS[q[1] & 7]
    am = q[0x33]
    out = []
    for r in range(4): o = SLOT[r]; out.append(rr(dt(q[2 + o]), 4) | q[6 + o])                 # DT/MUL
    for r in range(4): o = SLOT[r]; out.append(tl_shadow[r] if car >> o & 1 else q[0x0A + o])   # TL
    for r in range(4): o = SLOT[r]; out.append(rr(q[0x0E + o], 2) | q[0x12 + o])               # KS/AR
    for r in range(4): o = SLOT[r]; out.append((0x80 if am >> o & 1 else 0) | q[0x16 + o])     # AM/DR
    for r in range(4): o = SLOT[r]; out.append(q[0x1A + o])                                    # SR
    for r in range(4): o = SLOT[r]; out.append(rr(q[0x1E + o], 4) | q[0x22 + o])               # SL/RR
    for r in range(4): o = SLOT[r]; out.append(q[0x26 + o])                                    # SSG-EG
    out.append((q[0] << 3 | q[0] >> 5 | q[1]) & 0xFF)                                        # $B0 FB/ALG (RLCA x3)
    out.append(b4 & 0xC0 | q[0x32])                                                          # $B4
    return out

def start_writes(s, cmd):
    """$111B for song cmd: ADPCM-B reset, FM keys off ($0B2E), timer B, ADPCM-A master volume, timer flags (a fade in
    progress would skip the master volume: no song starts during one)"""
    d = s.m.d; i = cmd - 0x20
    base = M1.BANKS[d[0x2E00 + i]]
    ptr = d[0x3A70 + 2 * i] | d[0x3A71 + 2 * i] << 8
    rd = lambda a: d[a] if a < 0x8000 else d[base + a - 0x8000]
    return [('a', 0x10, 1), ('a', 0x10, 0), ('a', 0x28, 1), ('a', 0x28, 2), ('a', 0x28, 5), ('a', 0x28, 6),
            ('a', 0x26, rd(ptr + 0x17)), ('b', 0x01, rd(ptr + 0x19)), ('a', 0x27, 0x2F)]

def writes(s):
    """the model's events -> register writes"""
    out = []
    alg = {n: 0 for n in FM}; b4 = {n: 0xC0 for n in FM}
    tls = {n: [0] * 4 for n in FM}                          # TL shadow per register slot ($40, $44, $48, $4C)
    w = lambda irq, p, r, v: out.append((irq, p, r, v & 0xFF))
    for irq, tick, ch, kind, kw in s.out:
        if kind == 'start':
            for p, r, v in start_writes(s, kw['cmd']): w(irq, p, r, v)
            for n in FM: b4[n] = b4[n] & 0x3F | 0xC0
            continue
        if ch in FM:
            p, o, code = FM[ch]
            if kind == 'patch':
                q = [s.m.d[kw['addr'] + i] for i in range(52)]
                vals = patch_regs(q, tls[ch], b4[ch])
                alg[ch] = q[1] & 7
                for i in range(28):
                    g, r = divmod(i, 4)
                    w(irq, p, 0x30 + 0x10 * g + 4 * r + o, vals[i])
                    if g == 1: tls[ch][r] = vals[i]
                w(irq, p, 0xB0 + o, vals[28]); b4[ch] = vals[29]; w(irq, p, 0xB4 + o, vals[29])
            elif kind == 'tl':
                for bit, reg in TL_ORDER:
                    if CARRIERS[alg[ch]] >> bit & 1:
                        tls[ch][(reg - 0x40) >> 2] = kw['tl'] & 0x7F; w(irq, p, reg + o, kw['tl'] & 0x7F)
            elif kind == 'key': w(irq, 'a', 0x28, code | kw['d'])
            elif kind in ('fnum', 'vib'): w(irq, p, 0xA4 + o, kw['a4']); w(irq, p, 0xA0 + o, kw['a0'])
            elif kind == 'pan': b4[ch] = b4[ch] & 0x3F | kw['pan']; w(irq, p, 0xB4 + o, b4[ch])
        if kind == 'lfo': w(irq, 'a', 0x22, kw['v'])
        elif kind == 'tempo': w(irq, 'a', 0x26, kw['tb'])
        elif kind == 'timerA': w(irq, 'a', 0x25, kw['r25']); w(irq, 'a', 0x24, kw['r24'])
        elif kind == 'reg': w(irq, 'a', kw['r'], kw['v'])
        elif kind == 'stop':                                 # $29F3
            for c in (1, 2, 5, 6): w(irq, 'a', 0x28, c)
            w(irq, 'a', 0x10, 1); w(irq, 'a', 0x10, 0); w(irq, 'b', 0x00, 0x87); w(irq, 'b', 0x01, 0x3F)
        if ch.startswith('A'):
            c = int(ch[1]) - 1; bit = 1 << c
            if kind == 'akey':
                st, en = kw['start'], (kw['lend'] if kw['loops'] else kw['end'])
                w(irq, 'b', 0x00, 0x80 | bit); w(irq, 'a', 0x1C, bit); w(irq, 'a', 0x1C, 0)
                w(irq, 'b', 0x10 + c, st); w(irq, 'b', 0x18 + c, st >> 8)
                w(irq, 'b', 0x20 + c, en); w(irq, 'b', 0x28 + c, en >> 8)
                w(irq, 'b', 0x00, bit)
            elif kind == 'alevel': w(irq, 'b', 0x08 + c, kw['v'])
            elif kind == 'adump': w(irq, 'b', 0x00, 0x80 | bit); w(irq, 'a', 0x1C, bit); w(irq, 'a', 0x1C, 0)
        elif ch == 'B':
            if kind == 'bkey':                               # $077D
                dn = kw['deltan']
                seq = [(0x11, 0), (0x14, 0), (0x15, 0), (0x10, 1), (0x1C, 0x80), (0x1C, 0), (0x10, 0),
                       (0x19, dn), (0x1A, dn >> 8), (0x12, kw['start']), (0x13, kw['start'] >> 8),
                       (0x14, kw['end']), (0x15, kw['end'] >> 8)]
                if kw['loops']: seq += [(0x12, kw['start']), (0x13, kw['start'] >> 8), (0x14, kw['lend']), (0x15, kw['lend'] >> 8)]
                seq += [(0x1B, kw['vol']), (0x10, 0x80)]
                for r, v in seq: w(irq, 'a', r, v)
            elif kind == 'bslur':                            # $083E
                w(irq, 'a', 0x1B, kw['vol']); w(irq, 'a', 0x19, kw['deltan']); w(irq, 'a', 0x1A, kw['deltan'] >> 8)
            elif kind == 'boff': w(irq, 'a', 0x11, 0)
            elif kind == 'bvol': w(irq, 'a', 0x1B, kw['vol'])
            elif kind == 'bpan': w(irq, 'a', 0x11, kw['pan'])
    return out

SKIP = {('a', 0x27), ('a', 0x1C)}
# timer flag resets ($27, every interrupt) and the ADPCM end-flag resets ($1C: also written by the interrupt handler's
# end-of-sample poll, $0870 / $03F3, driven by the chip's status) are left out on both sides, and so is ADPCM-B $10 = 0
# (the poll writes it when a B sample ends); none of them changes the sound

def capture(path, cmd):
    """-> (writes [(irq, port, reg, val)] from the command on, interrupt kinds ['A' / 'B', ...], preamble
    [(port, reg, val)] before the command). irq counts the interrupt handler's status reads ("i") after the command."""
    pre, out, kinds = [], [], []
    irq = 0; started = False
    for l in open(path):
        p = l.split()
        if not p or p[0] == 'f': continue
        if p[0] == 's' or (p[0] == 'c' and len(p) == 2):
            if not started and int(p[1], 16) == cmd and p[0] == 'c': started = True
            continue
        if p[0] == 'c': continue
        if p[0] == 'i':
            if started: irq += 1; kinds.append('B' if int(p[1], 16) & 2 else 'A')
            continue
        port, reg, val = p[0], int(p[1], 16), int(p[2], 16)
        if started: out.append((irq, port, reg, val))
        else: pre.append((port, reg, val))
    return out, kinds, pre

def keep(p, r, v): return (p, r) not in SKIP and (p, r, v) != ('a', 0x10, 0)

def replays(ws):
    """split one interrupt's writes into (music, replays): a looping sample's next pass, started by the interrupt
    handler's end-of-sample poll ($03F3 ADPCM-A, $0870 ADPCM-B), is the address group + key-on without the key-on
    preamble (ADPCM-A: no dump b $00 = $80|bit before it; ADPCM-B: no $1B volume before $10 = $80).
    replays: [(chan, start, end)]"""
    music, rep = [], []
    i = 0
    while i < len(ws):
        g = ws[i:i + 5]
        if len(g) == 5 and g[0][0] == 'b' and 0x10 <= g[0][1] <= 0x15:
            c = g[0][1] - 0x10
            if [(p, r) for p, r, v in g] == [('b', 0x10 + c), ('b', 0x18 + c), ('b', 0x20 + c), ('b', 0x28 + c), ('b', 0)] \
                    and g[4][2] == 1 << c and not (music and music[-1] == ('b', 0, 0x80 | 1 << c)):
                rep.append((f'A{c + 1}', g[0][2] | g[1][2] << 8, g[2][2] | g[3][2] << 8)); i += 5; continue
        if len(g) == 5 and [(p, r) for p, r, v in g] == [('a', 0x12), ('a', 0x13), ('a', 0x14), ('a', 0x15), ('a', 0x10)] \
                and g[4][2] == 0x80 and not (music and music[-1][:2] == ('a', 0x15)):
            rep.append(('B', g[0][2] | g[1][2] << 8, g[2][2] | g[3][2] << 8)); i += 5; continue
        music.append(ws[i]); i += 1
    return music, rep

def compare(data, cmd, path, show=0, quiet=False):
    """-> (identical interrupts, interrupts with writes, model, replay stats). The capture's last interrupt is left
    out (the capture stops inside it)."""
    cap, kinds, _ = capture(path, cmd)
    n = len(kinds) - 1
    s = Song(data, cmd).run(irqs=n, seq=kinds)
    mod = writes(s)
    a, b = {}, {}
    for q, p, r, v in cap:
        if q <= n and keep(p, r, v): a.setdefault(q, []).append((p, r, v))
    for q, p, r, v in mod:
        if q <= n and keep(p, r, v): b.setdefault(q, []).append((p, r, v))
    # replays: each must be the loop region or the tail of the looping sample last keyed on that channel
    loops = {}; rep_ok = rep_bad = 0
    ev = sorted((irq, ch, kw) for irq, t, ch, kind, kw in s.out if kind in ('akey', 'bkey'))
    for q in sorted(a):
        a[q], rep = replays(a[q])
        for ch, st, en in rep:
            k = [kw for irq, c, kw in ev if c == ch and irq < q]
            kw = k[-1] if k else {}
            ok = kw.get('loops') and ((st, en) == (kw['lstart'], kw['lend']) or (st, en) == (kw['lend'] + 1, kw['end']))
            rep_ok += bool(ok); rep_bad += not ok
            if not ok and not quiet: print(f'unexpected replay irq {q} {ch} {st:04X}-{en:04X}')
        if not a[q]: del a[q]
    ticks = sorted(set(a) | set(b))
    same = sum(1 for q in ticks if a.get(q) == b.get(q))
    na = sum(len(v) for v in a.values()); nb = sum(len(v) for v in b.values())
    if not quiet:
        print(f'song ${cmd:02X}: {n} interrupts ({kinds[:n].count("B")} timer B, {s.tick} music ticks), {na} captured '
              f'writes, {nb} model writes; interrupts with writes {len(ticks)}, identical {same}; loop replays '
              f'{rep_ok} as predicted, {rep_bad} not')
    shown = 0
    for q in ticks:
        if a.get(q) == b.get(q) or shown >= show: continue
        shown += 1
        fa = ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in a.get(q, []))
        fb = ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in b.get(q, []))
        print(f'-- irq {q} ({kinds[q - 1] if q else "cmd"})\n  cap   {fa}\n  model {fb}')
    return same, len(ticks), s, (rep_ok, rep_bad)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    show = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == '--show' else 0
    compare(data, int(sys.argv[2], 16), sys.argv[3], show)
