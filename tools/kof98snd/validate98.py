#!/usr/bin/env python3
"""Compare song98.py's model of a song with a MAME capture (ymtap.lua with IRQ=1), timer interrupt by timer interrupt.

    python3 validate98.py M1.bin CMD CAPTURE [--detail CH]

The capture's "i" lines number the timer-A interrupts; the model numbers its own from the song start. The offset
between the two is found by trying every value in a small window after the command and keeping the best (it is then
the same for every channel). Per channel: key-ons (count, exact-interrupt matches, pitch / sample / delta-N at the
key-on), key-offs, and the effect writes (F-number writes between key-ons = vibrato)."""
import sys, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import song98

FMKEY = {1: 'FM1', 2: 'FM2', 5: 'FM3', 6: 'FM4'}

def read_capture(path, cmd):
    """-> (events [(irq, ch, kind, dict)], irq at the command, total irqs)"""
    lines = open(path).read().split('\n')
    ev = []
    irq = 0; cmd_irq = None
    lat = {}                                   # (port, reg) -> last value
    for i, l in enumerate(lines):
        if not l: continue
        p = l.split()
        if p[0] == 'i': continue               # the ISR's status read (timer-A flag = bit 0)
        if p[0] == 'q':                        # $FD9B <- 1: a timer interrupt that runs the sequencer (2 = nested, dropped)
            if p[1] == '1': irq += 1
            continue
        if p[0] == 'f': continue
        if p[0] == 'c':
            if cmd_irq is None and int(p[1], 16) >> 8 == cmd: cmd_irq = irq
            continue
        port = p[0]; reg = int(p[1], 16); val = int(p[2], 16)
        lat[(port, reg)] = val
        if port == 'a' and reg == 0x28:
            ch = FMKEY.get(val & 7)
            if ch: ev.append((irq, ch, 'keyon' if val & 0xF0 else 'keyoff', {}))
        elif 0xA1 <= reg <= 0xA2:
            ch = ('FM%d' % (reg - 0xA0)) if port == 'a' else ('FM%d' % (reg - 0xA0 + 2))
            hi = lat.get((port, reg + 4), 0)
            ev.append((irq, ch, 'fnum', {'block': (hi >> 3) & 7, 'fnum': (hi & 7) << 8 | val}))
        elif 0x40 <= reg <= 0x4F and reg & 3:
            ch = ('FM%d' % (reg & 3)) if port == 'a' else ('FM%d' % ((reg & 3) + 2))
            ev.append((irq, ch, 'tlw', {'op': (reg - 0x40) >> 2, 'tl': val}))
        elif port == 'b' and reg == 0x00:
            for c in range(6):
                if val >> c & 1:
                    if val & 0x80: ev.append((irq, 'A%d' % (c + 1), 'adump', {}))
                    else:
                        st = lat.get(('b', 0x10 + c), 0) | lat.get(('b', 0x18 + c), 0) << 8
                        en = lat.get(('b', 0x20 + c), 0) | lat.get(('b', 0x28 + c), 0) << 8
                        lv = lat.get(('b', 0x08 + c), 0)
                        ev.append((irq, 'A%d' % (c + 1), 'akey', {'start': st, 'end': en, 'pan': lv & 0xC0, 'level': lv & 0x1F}))
        elif port == 'a' and reg == 0x10 and val & 0x80:
            dn = lat.get(('a', 0x19), 0) | lat.get(('a', 0x1A), 0) << 8
            st = lat.get(('a', 0x12), 0) | lat.get(('a', 0x13), 0) << 8
            en = lat.get(('a', 0x14), 0) | lat.get(('a', 0x15), 0) << 8
            ev.append((irq, 'B', 'bkey', {'deltan': dn, 'start': st, 'end': en, 'vol': lat.get(('a', 0x1B), 0)}))
        elif port == 'a' and reg == 0x11 and val == 0:
            nxt = next((x for x in lines[i + 1:i + 12] if x.startswith('a ') and x[:4] not in ('a 27', 'a 1C') and x != 'a 10 00'), '')  # preamble $11=0, $14=0 (skip a nested ISR's writes)
            if nxt != 'a 14 00': ev.append((irq, 'B', 'boff', {}))
        elif reg in (0xB5, 0xB6):
            ch = ('FM%d' % (reg - 0xB4)) if port == 'a' else ('FM%d' % (reg - 0xB4 + 2))
            ev.append((irq, ch, 'panw', {'pan': val & 0xC0}))
        elif port == 'a' and reg == 0x1B:
            ev.append((irq, 'B', 'bvolw', {'vol': val}))
        elif port == 'a' and reg == 0x1A:
            dn = lat.get(('a', 0x19), 0) | val << 8
            ev.append((irq, 'B', 'bdn', {'deltan': dn}))
    return ev, cmd_irq, irq

def model(data, cmd, irqs):
    s = song98.Song(data, cmd)
    s.run(irqs=irqs)
    return s

def sig(ch, kind, kw):
    """(class, comparable values) of one event, the same for the model and the capture"""
    if kind in ('fnum', 'vib'): return 'pitch', (kw['block'], kw['fnum'])
    if kind == 'tl': return 'tl', (kw['tl'],)
    if kind == 'tlw': return 'tl', (kw['tl'],)
    if kind == 'keyon': return 'key', ()
    if kind == 'keyoff': return 'off', ()
    if kind == 'akey': return 'key', (kw['start'], kw['end'], kw['pan'], kw['level'])
    if kind == 'adump': return 'off', ()
    if kind == 'bkey': return 'key', (kw['deltan'], kw['start'], kw['end'], kw['vol'])
    if kind == 'boff': return 'off', ()
    if kind in ('bpitch', 'bdn'): return 'bpitch', (kw['deltan'],)
    if kind in ('pan', 'panw'): return 'pan', (kw['pan'],)
    if kind in ('bvol', 'bvolw'): return 'bvol', (kw['vol'],)
    return None, None

CLASSES = ('key', 'off', 'pitch', 'tl', 'pan', 'bpitch', 'bvol')

def compare(data, cmd, path, detail=None, quiet=False):
    cap, cmd_irq, total = read_capture(path, cmd)
    if cmd_irq is None: raise SystemExit('command not in capture')
    s = model(data, cmd, total - cmd_irq + 4)
    sim = [(irq, ch, kind, kw) for irq, t, ch, kind, kw in s.out]
    # the model's ADPCM-A key-on also dumps the channel first ($0232): one extra "off" per key-on
    sim += [(irq, ch, 'adump', {}) for irq, ch, kind, kw in sim if kind == 'akey']
    simk = defaultdict(list); capk = defaultdict(list)
    for irq, ch, kind, kw in sim:
        if kind in ('keyon', 'akey', 'bkey'): simk[ch].append(irq)
    for irq, ch, kind, kw in cap:
        if kind in ('keyon', 'akey', 'bkey') and irq > cmd_irq: capk[ch].append(irq)
    best = None                                  # offset: maximise exact key-on matches over all channels
    for off in range(cmd_irq - 2, cmd_irq + 12):
        sc = sum(len(set(i + off for i in simk[ch]) & set(capk[ch])) for ch in simk)
        if best is None or sc > best[0]: best = (sc, off)
    off = best[1]
    first = off + 1
    S = defaultdict(lambda: defaultdict(list)); C = defaultdict(lambda: defaultdict(list))
    for irq, ch, kind, kw in sim:
        cl, v = sig(ch, kind, kw)
        if cl and irq + off < total: S[ch][cl].append((irq + off, v))
    for irq, ch, kind, kw in cap:
        cl, v = sig(ch, kind, kw)
        if cl and first <= irq < total: C[ch][cl].append((irq, v))
    # looping samples (sample table 7, loop count != 0): the driver's ADPCM end-flag handler ($0306) restarts the loop
    # region each time the sample ends; those key-ons follow the sample length, not the sequencer: class 'loop'
    for ch in list(S):
        lk = [(i, kw) for i, c, k, kw in sim if c == ch and k == 'akey']
        for i, kw in lk:
            if not kw.get('loops'): continue
            nxt = min([j for j, _ in lk if j > i] + [10 ** 9])
            rest = []
            for e in C[ch]['key']:
                if i + off < e[0] < nxt + off and e[1][0] == kw['lstart']: C[ch]['loop'].append(e)
                else: rest.append(e)
            C[ch]['key'] = rest
    res = {}
    for ch in song98.CHANNELS:
        if not s.sp[song98.CHANNELS.index(ch)]: continue
        r = {}
        if C[ch]['loop']:
            iv = [b[0] - a[0] for a, b in zip(C[ch]['loop'], C[ch]['loop'][1:])]
            r['loop'] = (0, len(C[ch]['loop']), 0, [], sorted(set(iv)))
        for cl in CLASSES:
            sm, cp = S[ch][cl], C[ch][cl]
            if not sm and not cp: continue
            cset = defaultdict(int)
            for e in cp: cset[e] += 1
            hit = 0; miss = []
            for e in sm:
                if cset[e]: cset[e] -= 1; hit += 1
                else: miss.append(e)
            extra = [e for e in cp if cset[e] > 0 and not cset.__setitem__(e, cset[e] - 1)]
            r[cl] = (len(sm), len(cp), hit, miss, extra)
        res[ch] = r
    if not quiet:
        print(f'song ${cmd:02X}: command at irq {cmd_irq}, model irq 0 = capture irq {off} (+{off - cmd_irq}), '
              f'{total - off} irqs = {s.tick} ticks compared; model/capture/matched (same irq, same values)')
        for ch, r in res.items():
            print(f'{ch:4s} ' + '  '.join(f'{cl} {a}/{b}/{h}' if cl != 'loop' else f'loop-replays {b} every {x} irqs'
                                          for cl, (a, b, h, _, x) in r.items()))
        if detail:
            for cl, (a, b, h, miss, extra) in res.get(detail, {}).items():
                print(detail, cl, 'model only', miss[:12]); print(detail, cl, 'capture only', extra[:12])
    return res, off, s, cap

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    det = sys.argv[sys.argv.index('--detail') + 1] if '--detail' in sys.argv else None
    compare(data, int(sys.argv[2], 16), sys.argv[3], det)
