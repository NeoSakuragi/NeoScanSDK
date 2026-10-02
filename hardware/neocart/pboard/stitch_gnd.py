#!/usr/bin/env python3
"""Give every SMD GND pad its own via to the In1 ground plane (short track + via), avoiding existing copper.
Run: AppDir/AppRun python3.11 stitch_gnd.py [board.kicad_pcb]"""
import os, sys, math, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'neocart_pboard.kicad_pcb')
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
NETNAME = sys.argv[2] if len(sys.argv) > 2 else 'GND'
b = pcbnew.LoadBoard(SRC); gnd = b.GetNetsByName()[NETNAME].GetNetCode()
VIA_D, VIA_DRILL, TRK0, CLR = 0.6, 0.3, 0.3, 0.16
TRK = TRK0
# copper obstacles: (layer or None for all, x0,y0,x1,y1, netcode)
obs = []
for t in b.GetTracks():
    bb = t.GetBoundingBox(); obs.append((None if type(t).__name__ == 'PCB_VIA' else t.GetLayer(), mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetX() + bb.GetWidth()), mm(bb.GetY() + bb.GetHeight()), t.GetNetCode()))
for f in b.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox(); lay = None if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else (pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
        obs.append((lay, mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetX() + bb.GetWidth()), mm(bb.GetY() + bb.GetHeight()), p.GetNetCode()))
keep = [z for z in b.Zones() if z.GetIsRuleArea()]
BB = b.GetBoardEdgesBoundingBox(); bx0, by0, bx1, by1 = mm(BB.GetX()), mm(BB.GetY()), mm(BB.GetX() + BB.GetWidth()), mm(BB.GetY() + BB.GetHeight())
def free(x0, y0, x1, y1, layer, allow_net):
    for lay, ax, ay, bx, by, n in obs:
        if n == allow_net: continue
        if layer is not None and lay is not None and lay != layer: continue
        if not (x1 + CLR <= ax or bx + CLR <= x0 or y1 + CLR <= ay or by + CLR <= y0): return False
    return True
def in_keepout(x, y):
    for z in keep:
        if z.Outline().Contains(P(x, y)): return True
    return False
holes = ((94.75, 127.0), (184.75, 127.0))
added = skipped = 0
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode() != gnd or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH: continue
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        cx, cy = mm(p.GetPosition().x), mm(p.GetPosition().y)
        TRK = max(0.15, min(TRK0, mm(min(p.GetSize().x, p.GetSize().y))))   # stub no wider than the pad (0.2 on the QFN), never below the 0.15 mm minimum (USB-C shell pads report a 0.005 mm size)
        # an existing GND via close by: reuse it with a stub if the stub is free
        done = False
        near = sorted(((math.hypot((ax + bx) / 2 - cx, (ay + by) / 2 - cy), (ax + bx) / 2, (ay + by) / 2) for lay, ax, ay, bx, by, n in obs if lay is None and n == gnd), key=lambda q: q[0])
        for dist, vx, vy in near[:3]:
            if dist > 1.8: break
            tx0, ty0, tx1, ty1 = min(cx, vx) - TRK / 2, min(cy, vy) - TRK / 2, max(cx, vx) + TRK / 2, max(cy, vy) + TRK / 2
            if free(tx0, ty0, tx1, ty1, layer, gnd):
                t = pcbnew.PCB_TRACK(b); t.SetStart(P(cx, cy)); t.SetEnd(P(vx, vy)); t.SetWidth(FromMM(TRK)); t.SetLayer(layer); t.SetNetCode(gnd); b.Add(t)
                obs.append((layer, tx0, ty0, tx1, ty1, gnd)); added += 1; done = True; break
        if done: continue
        done = False
        for rad in (0.9, 1.2, 1.5, 1.9, 2.4, 3.0, 4.0, 5.0, 6.0, 6.3, 7.2, 8.0):
            for k in range(12):
                ang = 2 * math.pi * k / 12; vx, vy = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
                r = VIA_D / 2
                if vy > 145.0 or in_keepout(vx, vy) or any(math.dist((vx, vy), h) < 6.9 for h in holes): continue   # via must reach the plane (y < 144)
                if not (bx0 + 0.8 < vx < bx1 - 0.8 and by0 + 0.8 < vy < by1 - 0.8): continue
                if not free(vx - r, vy - r, vx + r, vy + r, None, gnd): continue
                tx0, ty0, tx1, ty1 = min(cx, vx) - TRK / 2, min(cy, vy) - TRK / 2, max(cx, vx) + TRK / 2, max(cy, vy) + TRK / 2
                if not free(tx0, ty0, tx1, ty1, layer, gnd): continue
                if not any(lay is None and n == gnd and abs((ax + bx) / 2 - vx) < 0.02 and abs((ay + by) / 2 - vy) < 0.02 for lay, ax, ay, bx, by, n in obs):   # a GND via is already there (the two finger faces share x): only the stub is new
                    v = pcbnew.PCB_VIA(b); v.SetPosition(P(vx, vy)); v.SetWidth(FromMM(VIA_D)); v.SetDrill(FromMM(VIA_DRILL)); v.SetNetCode(gnd); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)
                t = pcbnew.PCB_TRACK(b); t.SetStart(P(cx, cy)); t.SetEnd(P(vx, vy)); t.SetWidth(FromMM(TRK)); t.SetLayer(layer); t.SetNetCode(gnd); b.Add(t)
                obs.append((None, vx - r, vy - r, vx + r, vy + r, gnd)); obs.append((layer, tx0, ty0, tx1, ty1, gnd)); added += 1; done = True; break
            if done: break
        if not done: skipped += 1; print('no room for a', NETNAME, 'via at', f.GetReference(), p.GetNumber(), round(cx, 1), round(cy, 1))
b.Save(SRC); print(f'{NETNAME} vias added: {added}, pads without room: {skipped}')
