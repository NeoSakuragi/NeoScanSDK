#!/usr/bin/env python3
"""A song of SNK's own Sound Driver line (KOF96's Ver 0.1, Kizuna, KOF97, ...: tools/kof98snd/games98.py) as notes with
their full chip state: the same engine-neutral form as ff3_notes.py (MAKOTO v3 songs), read here from the YM2610
register writes of the song98.py / regs98.py model (validated register-exact against the real driver), so whatever the
driver's own opcodes did, a note is what the chip received.

    python3 snk_notes.py M1.bin 0x2D          summary: notes per channel, loop points, changes inside notes

notes(data, cmd) -> {channel: [Note]}, loops {channel: (loop tick, length)}, tick rate (Hz), the Song.
FM: a key-on starts a Note with the 28 operator registers (register order $30..$9C), $B0, $B4, the carrier TL and the
F-number word as they stand at the end of the key-on's interrupt; an F-number change while the key is held (a tie into
another pitch: the SNK drivers do not key on again) starts a legato Note; other register changes while the key is held
are kept in Note.changes (tick, kind, value) when they change the value. ADPCM-A / ADPCM-B: as ff3_notes.py."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'kof98snd'))
import song98, regs98
from ff3_notes import Note, FM

CARRIERS = regs98.CARRIERS
FMCH = {1: ('a', 1, 'FM1'), 2: ('a', 2, 'FM2'), 5: ('b', 1, 'FM3'), 6: ('b', 2, 'FM4')}
BYNAME = {v[2]: (v[0], v[1]) for v in FMCH.values()}

def notes(data, cmd, passes=1):
    s = song98.Song(data, cmd).run(ticks=20000)
    end = max((a + passes * b for a, b, _ in s.loop_at.values()), default=s.tick) + 1
    s = song98.Song(data, cmd).run(ticks=end)
    tick = {}
    for irq, t, *_ in s.out: tick.setdefault(irq, t)
    out = from_writes(regs98.writes(s), tick)
    loops = {n: (a, b) for n, (a, b, _) in s.loop_at.items()}
    return out, loops, 166.83 * s.tempo / 208, s

def from_writes(ws, tick):
    """register writes [(irq, port, reg, val)] + {irq: music tick} -> {channel: [Note]} (also the SDC_NGSS source,
    ngss_notes.py)"""
    R = {'a': [0] * 256, 'b': [0] * 256}
    out = {n: [] for n in ('FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B')}
    cur = {}; key = {n: False for n in FM}
    by_irq = {}
    for irq, p, r, v in ws: by_irq.setdefault(irq, []).append((p, r, v))
    last_t = 0
    def fm_state(n):
        p, o = BYNAME[n]
        regs = [R[p][base + 4 * k + o] for base in range(0x30, 0xA0, 0x10) for k in range(4)]
        alg = R[p][0xB0 + o] & 7
        car = [regs[4 + k] for k in range(4) if CARRIERS[alg] >> k & 1]
        patch = [0 if 4 <= i < 8 and CARRIERS[alg] >> (i - 4) & 1 else x for i, x in enumerate(regs)]
        # (the carriers' TL is the note's velocity, not part of the patch: KOF98's patch load keeps it, $1350)
        return dict(regs=patch + [R[p][0xB0 + o], R[p][0xB4 + o]], alg=alg, tl=car[0], car_tls=car,
                    fnum=R[p][0xA4 + o] << 8 | R[p][0xA0 + o], pan=R[p][0xB4 + o] & 0xC0)
    for irq in sorted(by_irq):
        t = tick.get(irq, last_t); last_t = t
        before = {n: fm_state(n) for n in FM}
        keyed = set(); a_on = []; a_off = []; b_on = b_off = False
        for p, r, v in by_irq[irq]:
            R[p][r] = v
            if p == 'a' and r == 0x28 and (v & 7) in FMCH:
                n = FMCH[v & 7][2]
                if v & 0xF0:
                    if not key[n]: keyed.add(n)
                    key[n] = True
                else:
                    if key[n] and n in cur: cur[n].off = t
                    key[n] = False; keyed.discard(n)
            elif p == 'b' and r == 0x00:
                for c in range(6):
                    if v >> c & 1: (a_off if v & 0x80 else a_on).append(c)
            elif p == 'a' and r == 0x10:
                if v & 0x80: b_on = True
                elif v & 1: b_off = True
            elif p == 'a' and r == 0x11 and v == 0: b_off = True     # pan L/R off: the drivers' ADPCM-B key-off
        for n in FM:
            st = fm_state(n)
            if n in keyed:
                nt = Note(t, legato=False, **{k: v for k, v in st.items()})
                out[n].append(nt); cur[n] = nt
            elif key[n] and n in cur:
                old = before[n]
                if st['fnum'] != old['fnum']:                     # a tie into another pitch
                    cur[n].off = None
                    nt = Note(t, legato=True, **{k: v for k, v in st.items()})
                    out[n].append(nt); cur[n] = nt
                else:
                    if st['car_tls'] != old['car_tls']: cur[n].changes.append((t, 'tl', st['tl']))
                    if st['pan'] != old['pan']: cur[n].changes.append((t, 'pan', st['pan']))
                    if st['regs'][:28] != old['regs'][:28] and [x for i, x in enumerate(st['regs'][:28]) if not 4 <= i < 8] != \
                            [x for i, x in enumerate(old['regs'][:28]) if not 4 <= i < 8]:
                        cur[n].changes.append((t, 'patch', None))
        for c in a_off:
            n = f'A{c + 1}'
            if n in cur and cur[n].off is None and c not in a_on: cur[n].off = t
        for c in a_on:
            n = f'A{c + 1}'
            if n in cur and cur[n].off is None: cur[n].off = t
            nt = Note(t, start=R['b'][0x10 + c] | R['b'][0x18 + c] << 8, end=R['b'][0x20 + c] | R['b'][0x28 + c] << 8,
                      level=R['b'][0x08 + c], loops=0, lstart=None, lend=None)
            out[n].append(nt); cur[n] = nt
        bst = dict(start=R['a'][0x12] | R['a'][0x13] << 8, end=R['a'][0x14] | R['a'][0x15] << 8,
                   deltan=R['a'][0x19] | R['a'][0x1A] << 8, vol=R['a'][0x1B], pan=R['a'][0x11] & 0xC0)
        if b_on:
            if 'B' in cur and cur['B'].off is None: cur['B'].off = t
            nt = Note(t, loops=1 if R['a'][0x10] & 0x10 else 0, lend=None, **bst)
            out['B'].append(nt); cur['B'] = nt
        elif b_off:
            if 'B' in cur and cur['B'].off is None: cur['B'].off = t
        elif 'B' in cur and cur['B'].off is None:
            n = cur['B']; last = n.changes[-1] if n.changes else (0, '', n.deltan, n.vol)
            if (bst['deltan'], bst['vol']) != (last[2], last[3]) and any(r in (0x19, 0x1A, 0x1B) for p, r, v in by_irq[irq] if p == 'a'):
                n.changes.append((t, 'bslur', bst['deltan'], bst['vol']))
        for n in [f'A{c + 1}' for c in range(6)]:              # level changes while a sample plays
            c = int(n[1]) - 1
            if n in cur and cur[n].off is None and c not in a_on and any(p == 'b' and r == 0x08 + c for p, r, v in by_irq[irq]):
                if R['b'][0x08 + c] != (cur[n].changes[-1][2] if cur[n].changes else cur[n].level):
                    cur[n].changes.append((t, 'alevel', R['b'][0x08 + c]))
    return {k: v for k, v in out.items() if v}

def summary(ns, loops, hz, s):
    print(f'song ${s.cmd:02X}: {hz:.2f} ticks/s (tempo {s.tempo}), {s.tick} ticks modelled')
    for ch, lst in ns.items():
        kinds = {}
        for n in lst:
            for c in n.changes: kinds[c[1]] = kinds.get(c[1], 0) + 1
        extra = ''
        if ch in FM:
            extra = (f"{len({tuple(n.regs) for n in lst})} patches, {len({n.fnum for n in lst})} pitches, "
                     f"{sum(n.legato for n in lst)} legato, {sum(len(set(n.car_tls)) > 1 for n in lst)} with unequal carrier TLs")
        else: extra = f"{len({(n.start, n.end) for n in lst})} samples"
        print(f'  {ch:4s} {len(lst):5d} notes, loop {loops.get(ch)}, {extra}; changes in notes {kinds}')

if __name__ == '__main__':
    summary(*notes(open(sys.argv[1], 'rb').read(), int(sys.argv[2], 16)))
