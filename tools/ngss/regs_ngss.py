#!/usr/bin/env python3
"""The SDC_NGSS model's YM2610 writes (song_ngss.py) compared with a capture_ngss.py capture, main-loop pass by pass.

    python3 regs_ngss.py M1.bin 0xE2 CAP.txt            compare
    python3 regs_ngss.py M1.bin 0xE2 CAP.txt --show N   print the first N differing passes

A capture is cut at its interrupt markers ("a 27 2A": the interrupt handler's only YM2610 write, $0236): pass k = the
writes after the k-th marker that follows the command's read ("c XX"). The command is taken by the first pass that
starts after the NMI; when the NMI lands between a marker and that pass's ring check ($00F1) the command is taken one
pass earlier: both alignments are tried, the better one is reported. The markers themselves are left out of the
comparison, and so is nothing else."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from song_ngss import Song

def capture(path, cmd):
    """-> (writes [(pass, port, reg, val)] from the command on, number of passes, preamble [(port, reg, val)])"""
    out, pre = [], []; started = False; k = 0
    for line in open(path):
        p = line.split()
        if not p or p[0] in ('f', 's', 'i'): continue
        if p[0] == 'c':
            if not started and p[-1] != 'blocked' and int(p[1], 16) == cmd: started = True
            continue
        r, v = int(p[1], 16), int(p[2], 16)
        if p[0] == 'a' and r == 0x27 and v == 0x2A:
            if started: k += 1
            continue
        if started: out.append((k, p[0], r, v))
        else: pre.append((p[0], r, v))
    return out, k, pre

def compare(data, cmd, path, show=0, quiet=False):
    """-> (identical passes, passes with writes, model Song, offset). The capture's last pass is left out (the
    capture stops inside it)."""
    cap, n, _ = capture(path, cmd)
    s = Song(data, cmd).run(n)
    best = None
    for off in (0, 1):                                       # model pass q = capture pass q - off
        a, b = {}, {}
        for q, p, r, v in cap:
            if q < n: a.setdefault(q, []).append((p, r, v))
        for q, p, r, v in s.writes:
            q2 = q - off
            if q2 < n: b.setdefault(q2, []).append((p, r, v))
        ks = sorted(set(a) | set(b))
        same = sum(1 for q in ks if a.get(q) == b.get(q))
        if best is None or same > best[0]: best = (same, len(ks), a, b, ks, off)
    same, total, a, b, ks, off = best
    if not quiet:
        na = sum(len(v) for v in a.values()); nb = sum(len(v) for v in b.values())
        print(f'sound ${cmd:02X}: {n} passes, {na} captured writes, {nb} model writes; passes with writes {total}, '
              f'identical {same} ({100 * same / max(1, total):.2f} %), command taken at capture pass {1 - off}')
    shown = 0
    for q in ks:
        if a.get(q) == b.get(q) or shown >= show: continue
        shown += 1
        print(f'-- pass {q}\n  cap   ' + ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in a.get(q, [])) +
              '\n  model ' + ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in b.get(q, [])))
    return same, total, s, off

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    show = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == '--show' else 0
    compare(data, int(sys.argv[2], 16), sys.argv[3], show)

def script(path):
    """a capture with any number of commands -> (writes [(pass, port, reg, val)], commands [(pass, cmd)], passes):
    pass = interrupt markers counted from the first command; a command read after marker k is pushed before pass
    k + 1 (the NMI's ring write, taken by that pass's $16D4)"""
    out, cmds = [], []; started = False; k = 0
    for line in open(path):
        p = line.split()
        if not p or p[0] in ('f', 's', 'i'): continue
        if p[0] == 'c':
            if p[-1] == 'blocked': continue
            if not started and len(cmds) == 0 and k == 0: started = True
            if started: cmds.append((k + 1, int(p[1], 16)))
            continue
        r, v = int(p[1], 16), int(p[2], 16)
        if p[0] == 'a' and r == 0x27 and v == 0x2A:
            if started: k += 1
            continue
        if started: out.append((k, p[0], r, v))
    return out, cmds, k

def compare_script(data, path, show=0, first=None):
    """every pass of a multi-command capture against the model fed the same commands at the same passes. first =
    the first command of the run (earlier ones, e.g. the boot's, are skipped by starting at it)"""
    from song_ngss import Driver
    out, cmds, n = script(path)
    if first is not None:
        i = next(j for j, (q, c) in enumerate(cmds) if c == first)
        q0 = cmds[i][0] - 1
        cmds = [(q - q0, c) for q, c in cmds[i:]]; out = [(q - q0, p, r, v) for q, p, r, v in out if q > q0]; n -= q0
    d = Driver(data); j = 0
    for q in range(1, n):
        while j < len(cmds) and cmds[j][0] <= q: d.push(cmds[j][1]); j += 1
        d.pass_()
    a, b = {}, {}
    for q, p, r, v in out:
        if 0 < q < n: a.setdefault(q, []).append((p, r, v))
    for q, p, r, v in d.writes:
        if q < n: b.setdefault(q, []).append((p, r, v))
    ks = sorted(set(a) | set(b)); same = sum(1 for q in ks if a.get(q) == b.get(q))
    print(f'{path}: {len(cmds)} commands, {n} passes, passes with writes {len(ks)}, identical {same}')
    shown = 0
    for q in ks:
        if a.get(q) == b.get(q) or shown >= show: continue
        shown += 1
        near = [f'{c:02X}@{p}' for p, c in cmds if q - 400 < p <= q]
        print(f'-- pass {q} (commands {near[-3:]})\n  cap   ' + ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in a.get(q, [])) +
              '\n  model ' + ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in b.get(q, [])))
    return same, len(ks)
