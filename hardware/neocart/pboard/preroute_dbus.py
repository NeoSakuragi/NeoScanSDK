#!/usr/bin/env python3
"""Pre-route the 68K data bus D0-D15 (gold fingers J2, top layer) to U4's B pins as a planar staircase, locked, before
Freerouting. Fingers and U4 pins are in the same left-to-right order (design.py reverses U4's channels for that), so every
line goes straight up from its finger, runs horizontally at its own height, then straight up into its pin; the rightmost
line turns highest. Horizontal runs sit between the tab and the right shell-post keep-out (y 133.5-141): the keep-out ends
at y 133, and every U4 pin is left of it (x < 178.75), so no line meets the hole.
Usage: AppRun python3.11 preroute_dbus.py board.kicad_pcb"""
import sys, pcbnew
from pcbnew import VECTOR2I, FromMM
b = pcbnew.LoadBoard(sys.argv[1])
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
fp = {f.GetReference(): f for f in b.GetFootprints()}
def pad_of(ref, net):
    return next(p for p in fp[ref].Pads() if p.GetNetname() == net)
lines = []
for i in range(16):
    n = f'D{i}'; pf, pu = pad_of('J2', n), pad_of('U4', n)
    lines.append((mm(pf.GetPosition().x), n, pf, pu))
lines.sort()                                   # left to right: D15 ... D0
H_LOW, PITCH, W = 140.5, 0.35, 0.15            # leftmost line's horizontal run, spacing (0.15 track + 0.2 gap)
assert max(mm(pad_of('U4', f'D{i}').GetPosition().x) for i in range(16)) < 178.75, 'a U4 data pin sits over the hole keep-out'
order_u4 = [mm(pu.GetPosition().x) for _, _, _, pu in lines]
assert order_u4 == sorted(order_u4), 'U4 pin order does not match finger order: the staircase would cross'
n_tr = 0
for k, (xf, n, pf, pu) in enumerate(lines):
    h = H_LOW - k * PITCH
    assert h >= 133.5, 'staircase reaches the hole keep-out'
    yf = mm(pf.GetPosition().y); xt, yt = mm(pu.GetPosition().x), mm(pu.GetPosition().y)
    pts = [(xf, yf), (xf, h), (xt, h), (xt, yt)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6: continue
        t = pcbnew.PCB_TRACK(b); t.SetStart(P(x0, y0)); t.SetEnd(P(x1, y1)); t.SetWidth(FromMM(W)); t.SetLayer(pcbnew.F_Cu)
        t.SetNet(pf.GetNet()); t.SetLocked(True); b.Add(t); n_tr += 1
b.Save(sys.argv[1]); print(f'pre-routed D0-D15: {n_tr} locked segments, horizontals y {H_LOW - 15 * PITCH:.2f}-{H_LOW:.2f}')
