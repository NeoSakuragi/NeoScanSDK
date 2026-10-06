#!/usr/bin/env python3
"""A song of Technos' SDC_NGSS driver (Double Dragon, Super Dodge Ball: tools/ngss) as notes with their full chip
state: the engine-neutral form port98.py writes into KOF98's format, read from the register writes of song_ngss.py's
model (register-identical to the real driver, every pass) through snk_notes.from_writes.

    python3 ngss_notes.py M1.bin 0xE3          summary: notes per channel, loop points, changes inside notes

notes(data, cmd) -> {channel: [Note]}, loops {channel: (loop tick, length)}, tick rate (Hz), the Song.
Ticks: every channel of a song runs the same tempo (all DD songs: one $E0 per channel, the same value), so the music
tick is the channels' common tick (tick 1 = the song's first events, pass 4 after the command at tempo $49 ...).
Normalised: FM TL writes keep their 7 register bits (the driver's level stage can leave bit 7 set: TL - B mod 256,
$0BA5; the chip ignores it). SSG channels are not notes (KOF98's songs have no SSG music path): reported, left out."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'ngss'))
import snk_notes
from song_ngss import Song, loop_passes, PASS_HZ, NAMES

PORT_NAMES = {'FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B'}

def tl7(ws):
    return [(q, p, r, v & 0x7F if 0x40 <= r <= 0x4F else v) for q, p, r, v in ws]

def run(data, cmd, passes=1):
    """the model to the intro + `passes` loops of every looping channel (or the end) -> (Song, {pass: tick}, loops)"""
    n, _ = loop_passes(data, cmd)
    loops = Song(data, cmd).run(n + 1).loop_ticks()
    end_t = max((a + passes * b for a, b in loops.values()), default=1 << 30)
    s = Song(data, cmd); first = s.e['streams'][0][0]; tick = {}
    while (s.drv.npass < 4 or s.active()) and s.drv.ticks[first] <= end_t:
        s.drv.pass_(); tick[s.drv.npass] = s.drv.ticks[first]
    return s, tick, loops

def ticks_writes(data, cmd, ticks):
    """the model's writes (TL to 7 bits) up to the end of music tick `ticks` and a pass -> tick function"""
    s = Song(data, cmd); first = s.e['streams'][0][0]; tick = {}
    while s.drv.ticks[first] <= ticks and (s.active() or s.drv.npass < 4):
        s.drv.pass_(); tick[s.drv.npass] = s.drv.ticks[first]
    ws = [w for w in tl7(s.writes) if tick.get(w[0], 0) <= ticks]
    return ws, lambda q: tick.get(q, 0)

def notes(data, cmd, passes=1):
    s, tick, loops = run(data, cmd, passes)
    out = snk_notes.from_writes(tl7(s.writes), tick)
    tempo = s.tempo()
    used = {NAMES[b] for b, _ in s.e['streams']}
    s.ssg = sorted(used - PORT_NAMES)
    return ({k: v for k, v in out.items() if k in PORT_NAMES}, {k: v for k, v in loops.items() if k in PORT_NAMES},
            PASS_HZ * tempo / 256, s)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read(); cmd = int(sys.argv[2], 16)
    ns, loops, hz, s = notes(data, cmd)
    print(f'song ${cmd:02X}: {hz:.2f} ticks/s (tempo ${s.tempo():02X}), {s.drv.npass} passes; SSG channels left out: {s.ssg}')
    for ch, lst in ns.items():
        kinds = {}
        for n in lst:
            for c in n.changes: kinds[c[1]] = kinds.get(c[1], 0) + 1
        extra = (f"{len({tuple(n.regs) for n in lst})} patches, {len({n.fnum for n in lst})} pitches, {sum(n.legato for n in lst)} legato, "
                 f"{sum(len(set(n.car_tls)) > 1 for n in lst)} with unequal carrier TLs") if ch.startswith('FM') else \
                f"{len({(n.start, n.end) for n in lst})} samples"
        print(f'  {ch:4s} {len(lst):5d} notes, loop {loops.get(ch)}, {extra}; changes in notes {kinds}')
