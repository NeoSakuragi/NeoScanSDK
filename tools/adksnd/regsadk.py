#!/usr/bin/env python3
"""The ADK driver's songs as YM2610 writes (songadk.py) compared with a captureadk.py capture, tick by tick.

    python3 regsadk.py M1.bin 0xD0 CAP.txt            compare
    python3 regsadk.py M1.bin 0xD0 CAP.txt --show N   print the first N differing ticks

The driver plays the music in its main loop, not in the interrupt: the timer-A interrupt only counts ($0E1A,
$F832), and the main loop runs a music tick when the count has reached 2 ($0E56). A capture's writes are therefore
grouped by timer-A interrupt pairs after the command: group k = the writes after timer-A interrupt 2k - p and
before 2k + 2 - p, p = the count already standing when the command arrived (0, 1 or 2: the one that matches);
group 0 = the song start. Left out on both sides: the interrupt's $27 acknowledgements (value with bit 4 or 5 set:
timer flag resets); the 'W' command's $27 writes ($0F / $4F) are kept."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from songadk import Song

def capture(path, cmd):
    """-> ([(timer-A count since the command, port, reg, val)] from the command's read on, interrupt status bits per
    interrupt, preamble [(port, reg, val)] before the command)"""
    out = []; started = False; na = 0; kinds = []; fc = False; pre = []
    for line in open(path):
        p = line.split()
        if not p: continue
        if p[0] == 'c':
            if p[-1] == 'blocked': continue
            v = int(p[1], 16)
            if not started and fc and v == cmd: started = True; continue
            fc = v in (0xFB, 0xFC)
            continue
        if p[0] == 'i':
            if started:
                st = int(p[1], 16); kinds.append(st & 3)
                if st & 1: na += 1
            continue
        if p[0] in ('a', 'b'):
            r, v = int(p[1], 16), int(p[2], 16)
            if not started: pre.append((p[0], r, v)); continue
            if p[0] == 'a' and r == 0x27 and v & 0x30: continue
            out.append((na, p[0], r, v))
    return out, kinds, pre

def simulate(cap, model, nt, p):
    """walk the capture with the driver's own clock: the interrupt adds 1 to the count ($F832), a tick starts when
    the main loop finds it at 2 or more and clears it ($0E56), so a tick that outlasts two interrupts makes the next
    one start at once. Tick k takes the next len(model[k]) captured writes; it is identical when they are the
    model's and its first write falls after its start's interrupt (at most one interrupt later).
    Returns {tick: (captured writes, start interrupt, timing ok)}."""
    res = {}; i = 0; c = p; na_now = 0
    for k in range(nt):
        m = model.get(k, [])
        if k == 0: start = 0
        else:
            start = na_now if c >= 2 else na_now + 2 - c
            c = 0
        seg = cap[i:i + len(m)]; i += len(m)
        ok = all(x[0] >= start for x in seg) and (not seg or seg[0][0] <= start + 1)
        res[k] = ([x[1:] for x in seg], start, ok)
        end = seg[-1][0] if seg else start
        c = p + end if k == 0 else end - start               # interrupts counted while the tick ran
        na_now = max(start, end)
    return res, cap[i:]

def compare(data, cmd, path, show=0, quiet=False):
    cap, kinds, _ = capture(path, cmd)
    nA = sum(1 for k in kinds if k & 1)
    s = Song(data, cmd).run(nA // 2 + 2)
    model = s.by_tick()
    best = None
    for p in (0, 1, 2):
        r, rest = simulate(cap, model, nA // 2 + 2, p)
        good = [k for k in r if r[k][2] and r[k][0] == model.get(k, [])]
        if best is None or len(good) > best[0]: best = (len(good), p, r, rest)
    _, p, r, rest = best
    last = max((r[k][1] for k in r), default=0)
    ticks = [k for k in r if r[k][1] + 2 <= nA and k <= s.tick]     # ticks whose window the capture covers
    withw = [k for k in ticks if r[k][0] or model.get(k)]
    same = [k for k in withw if r[k][2] and r[k][0] == model.get(k, [])]
    ncap = sum(len(r[k][0]) for k in ticks)
    end = max((r[k][1] for k in ticks), default=0)
    extra = sum(1 for x in rest if x[0] < end)               # captured writes no model tick accounts for
    if not quiet:
        print(f'command ${cmd:02X}: {nA} timer-A interrupts, {len(ticks)} music ticks (count at the command {p}), '
              f'{ncap} captured writes; ticks with writes {len(withw)}, identical {len(same)}; unaccounted writes {extra}')
    bad = [k for k in withw if k not in same]
    for k in bad[:show]:
        print(f'tick {k} (start after interrupt {r[k][1]}, timing {"ok" if r[k][2] else "WRONG"}):\n  cap   ' +
              ' '.join(f'{q}{rr:02X}={v:02X}' for q, rr, v in r[k][0]) +
              '\n  model ' + ' '.join(f'{q}{rr:02X}={v:02X}' for q, rr, v in model.get(k, [])))
    return len(same), len(withw), ncap, p, extra, r, s

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    show = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == '--show' else 0
    compare(data, int(sys.argv[2], 16), sys.argv[3], show)
