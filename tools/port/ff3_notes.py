#!/usr/bin/env python3
"""A MAKOTO v3 song (Fatal Fury 3, KOF94) as notes with their full chip state, from the tools/makoto3 model:
the engine-neutral form ff3_to_kof98.py writes into KOF98's format.

    python3 ff3_notes.py M1.bin 0x2F          summary: notes per channel, loop points, what does not map 1:1

notes(data, cmd) -> {channel: [Note]}, loop {channel: (loop tick, length)}, tick rate (Hz).
A Note holds the music tick it keys on, the tick it keys off (None: a sample that plays to its end, or an FM note
that goes on into the next one: that one has legato=True, the chip's key was still on), and the chip
state at the key-on: FM = the 30 patch registers in write order ($30..$9C, $B0, $B4), carrier TL, F-number word,
pan; ADPCM-A = start, end, pan|level register; ADPCM-B = start, end, delta-N, volume, pan. Changes during a note
(FM vibrato / F-number, TL, ADPCM-B slur, volume, pan) are kept in Note.changes as (tick, kind, value)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'makoto3'))
from song import Song, tick_hz
from regs import patch_regs, CARRIERS

FM = ('FM1', 'FM2', 'FM3', 'FM4')

class Note:
    def __init__(self, tick, **state):
        self.tick, self.off, self.changes = tick, None, []
        self.__dict__.update(state)
    def __repr__(self):
        return f'Note({self.tick}-{self.off} ' + ' '.join(f'{k}={v}' for k, v in self.__dict__.items()
                                                           if k not in ('tick', 'off', 'changes', 'regs')) + ')'

def notes(data, cmd, ticks=None):
    s = Song(data, cmd)
    s.run(ticks=ticks or 20000)
    if ticks is None:                                        # one intro + one loop of every channel
        end = max((a + b for a, b, _ in s.loop_at.values()), default=s.tick) + 1
        s = Song(data, cmd); s.run(ticks=end)
    out = {n: [] for n in ('FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B')}
    st = {n: dict(regs=None, alg=0, tl=0, fnum=0, pan=0xC0, tls=[0] * 4, b4=0xC0) for n in FM}
    a_lvl = {f'A{i}': 0xDF for i in range(1, 7)}
    b_pan = 0xC0
    cur = {}                                                 # channel -> sounding Note
    for irq, tick, ch, kind, kw in s.out:
        if ch in FM:
            c = st[ch]
            if kind == 'patch':
                q = [s.m.d[kw['addr'] + i] for i in range(52)]
                vals = patch_regs(q, c['tls'], c['b4'])
                c['regs'], c['alg'] = vals, q[1] & 7; c['b4'] = vals[29]
                for r in range(4): c['tls'][r] = vals[4 + r]
            elif kind == 'tl':
                c['tl'] = kw['tl'] & 0x7F
                if ch in cur: cur[ch].changes.append((tick, 'tl', c['tl']))
            elif kind in ('fnum', 'vib'):
                c['fnum'] = kw['a4'] << 8 | kw['a0']
                if ch in cur: cur[ch].changes.append((tick, kind, c['fnum']))
            elif kind == 'pan':
                c['pan'] = kw['pan']; c['b4'] = c['b4'] & 0x3F | kw['pan']
                if ch in cur: cur[ch].changes.append((tick, 'pan', kw['pan']))
            elif kind == 'key':
                if kw['d']:
                    # a key-on while the key is on does not restart the envelope: the note goes on (legato)
                    legato = ch in cur and cur[ch].off is None
                    n = Note(tick, regs=list(c['regs']), alg=c['alg'], tl=c['tl'], fnum=c['fnum'], pan=c['pan'],
                             legato=legato)
                    out[ch].append(n); cur[ch] = n
                elif ch in cur and cur[ch].off is None: cur[ch].off = tick
            continue
        if ch.startswith('A'):
            if kind == 'alevel':
                a_lvl[ch] = kw['v']
                if ch in cur and cur[ch].off is None: cur[ch].changes.append((tick, 'alevel', kw['v']))
            elif kind == 'akey':
                if ch in cur and cur[ch].off is None: cur[ch].off = tick
                n = Note(tick, start=kw['start'], end=kw['end'], level=a_lvl[ch], loops=kw.get('loops', 0),
                         lstart=kw.get('lstart'), lend=kw.get('lend'))
                out[ch].append(n); cur[ch] = n
            elif kind == 'adump':
                if ch in cur and cur[ch].off is None: cur[ch].off = tick
        elif ch == 'B':
            if kind == 'bpan':
                b_pan = kw['pan']
                if ch in cur and cur[ch].off is None: cur[ch].changes.append((tick, 'bpan', b_pan))
            elif kind == 'bkey':
                if ch in cur and cur[ch].off is None: cur[ch].off = tick
                n = Note(tick, start=kw['start'], end=kw['end'], deltan=kw['deltan'], vol=kw['vol'], pan=b_pan,
                         loops=kw.get('loops', 0), lend=kw.get('lend'))
                out[ch].append(n); cur[ch] = n
            elif kind in ('bslur', 'bvol'):
                if ch in cur and cur[ch].off is None:
                    cur[ch].changes.append((tick, kind, kw.get('deltan'), kw['vol']))
            elif kind == 'boff':
                if ch in cur and cur[ch].off is None: cur[ch].off = tick
    # FF3 keys on before it writes the F-number and TL ($17A8 order): writes in the key-on's own tick are the note's
    # starting state, not changes
    field = {'tl': 'tl', 'fnum': 'fnum', 'vib': 'fnum', 'pan': 'pan', 'alevel': 'level', 'bpan': 'pan'}
    for lst in out.values():
        for n in lst:
            keep = []
            for c in n.changes:
                if c[0] == n.tick and c[1] in field: setattr(n, field[c[1]], c[2])
                elif c[0] == n.tick and c[1] in ('bslur', 'bvol'):
                    if c[2] is not None: n.deltan = c[2]
                    n.vol = c[3]
                else: keep.append(c)
            n.changes = keep
    loops = {n: (a, b) for n, (a, b, _) in s.loop_at.items()}
    return {k: v for k, v in out.items() if v}, loops, tick_hz(s.tempo), s

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    ns, loops, hz, s = notes(data, int(sys.argv[2], 16))
    print(f'song ${int(sys.argv[2], 16):02X}: {hz:.2f} ticks/s, {s.tick} ticks modelled')
    for ch, lst in ns.items():
        ch_kinds = {}
        for n in lst:
            for c in n.changes: ch_kinds[c[1]] = ch_kinds.get(c[1], 0) + 1
        extra = ''
        if ch in FM:
            patches = len({tuple(n.regs) for n in lst}); fn = len({n.fnum for n in lst})
            extra = f'{patches} patches, {fn} pitches'
        elif ch == 'B':
            extra = f"{len({(n.start, n.end) for n in lst})} samples, {len({(n.start, n.deltan) for n in lst})} sample/rate pairs, loops {sum(1 for n in lst if n.loops)}"
        else:
            extra = f"{len({(n.start, n.end) for n in lst})} samples, loops {sum(1 for n in lst if n.loops)}"
        print(f'  {ch:4s} {len(lst):5d} notes, loop {loops.get(ch)}, {extra}; changes in notes {ch_kinds}')
