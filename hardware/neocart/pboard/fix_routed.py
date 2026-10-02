#!/usr/bin/env python3
"""Post-route fixes on neocart_pboard_routed.kicad_pcb (re-runnable): board via/drill minimums match the netclass, tracks hugging the
tab-step edge are pushed inward, and a GND pin the stitcher could not reach gets a via at the first free spot. Run with AppRun python3.11."""
import os, sys, math, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb')
b = pcbnew.LoadBoard(SRC); ds = b.GetDesignSettings()
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
ds.m_ViasMinSize = FromMM(0.45); ds.m_MinThroughDrill = FromMM(0.3)
# 1. tracks within 0.35 mm of the horizontal tab-step edges (y = 138.75, outside the tab x-range): move them up to y = 138.2
moved = 0
for t in b.GetTracks():
    if t.GetClass() != 'PCB_TRACK': continue
    for get, set_ in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
        p = get(); x, y = mm(p.x), mm(p.y)
        if (x < 62.45 or x > 217.05) and 138.75 - 0.35 - mm(t.GetWidth()) / 2 < y <= 138.75:
            set_(P(x, 138.75 - 0.35 - mm(t.GetWidth()) / 2 - 0.05)); moved += 1
print('edge-hugging track ends moved:', moved)
# 1b. the P3V3 diagonal at the left tab step: its junction goes to x = 59.83 so the run along y 138.2 clears R26 and the edge
bent = 0
for t in b.GetTracks():
    if t.GetClass() != 'PCB_TRACK' or t.GetNetname() != 'P3V3': continue
    for get, set_ in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
        p = get()
        if abs(mm(p.x) - 61.92) < 0.3 and abs(mm(p.y) - 138.22) < 0.3: set_(P(59.83, 138.2)); bent += 1
print('junction moved on', bent, 'segment ends')
# 2. GND via for a pad without one: search a free spot around the pad
gnd = b.GetNetsByName()['GND'].GetNetCode()
def items_near(x, y, r):
    out = []
    for t in b.GetTracks():
        if t.GetNetCode() == gnd: continue
        if t.GetClass() == 'PCB_VIA': d = math.dist((x, y), (mm(t.GetPosition().x), mm(t.GetPosition().y))) - mm(t.GetWidth()) / 2
        else:
            a, c = t.GetStart(), t.GetEnd(); ax, ay, cx, cy = mm(a.x), mm(a.y), mm(c.x), mm(c.y)
            L2 = (cx - ax) ** 2 + (cy - ay) ** 2; u = 0 if L2 == 0 else max(0, min(1, ((x - ax) * (cx - ax) + (y - ay) * (cy - ay)) / L2))
            d = math.dist((x, y), (ax + u * (cx - ax), ay + u * (cy - ay))) - mm(t.GetWidth()) / 2
        if d < r: out.append(d)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == gnd: continue
            bb = p.GetBoundingBox(); px = min(max(x, mm(bb.GetLeft())), mm(bb.GetRight())); py = min(max(y, mm(bb.GetTop())), mm(bb.GetBottom()))
            d = math.dist((x, y), (px, py))
            if d < r: out.append(d)
    return out
VIA_D, VIA_DRILL, TRK, CLR = 0.5, 0.25, 0.15, 0.16
added = 0
for ref, pn in (('U30', '62'),):
    fp = b.FindFootprintByReference(ref); pad = next(p for p in fp.Pads() if p.GetNumber() == pn)
    bb = pad.GetBoundingBox()
    if any(t.GetNetCode() == gnd and bb.Contains(t.GetStart() if t.GetClass() == 'PCB_TRACK' else t.GetPosition()) for t in b.GetTracks()): print(ref, pn, 'already has copper'); continue
    px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y); done = False
    for rad in [0.6 + 0.1 * i for i in range(20)]:
        for k in range(24):
            ang = 2 * math.pi * k / 24; vx, vy = px + rad * math.cos(ang), py + rad * math.sin(ang)
            if items_near(vx, vy, VIA_D / 2 + CLR): continue
            # the stub from the pad centre to the via must be free too (sampled)
            if any(items_near(px + (vx - px) * s, py + (vy - py) * s, TRK / 2 + CLR) for s in (0.3, 0.5, 0.7, 0.85)): continue
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(vx, vy)); v.SetWidth(FromMM(VIA_D)); v.SetDrill(FromMM(VIA_DRILL)); v.SetNetCode(gnd); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)
            t = pcbnew.PCB_TRACK(b); t.SetStart(P(px, py)); t.SetEnd(P(vx, vy)); t.SetWidth(FromMM(TRK)); t.SetLayer(pad.GetLayer()); t.SetNetCode(gnd); b.Add(t)
            print(ref, pn, 'GND via at', round(vx, 2), round(vy, 2), 'radius', round(rad, 1)); added += 1; done = True; break
        if done: break
    if not done: print(ref, pn, 'NO free spot for a via')
b.Save(SRC); print('saved', SRC, 'vias added', added)
