#!/usr/bin/env python3
"""Escape vias for a power net on fine-pitch parts: every SMD pad of NET whose pad is narrower than 0.4 mm gets a short straight stub
outward from the package plus a via, so Freerouting never has to fan the power pins out across their neighbours' exits on the top
layer (the 0.25 mm P3V3 diagonals were what boxed in FA/SDPAD/P2 pins in runs 6-7). The via is plain copper on F..B; the router
connects it to the rest of the net from the inner layers. Run: AppDir/AppRun python3.11 stitch_escape.py NET [board.kicad_pcb]"""
import os, sys, math, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__)); NET = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'neocart_pboard.kicad_pcb')
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
b = pcbnew.LoadBoard(SRC); nc = b.GetNetsByName()[NET].GetNetCode()
VIA_D, VIA_DRILL, CLR = 0.5, 0.3, 0.16
obs = []
for t in b.GetTracks():
    bb = t.GetBoundingBox(); obs.append((None if type(t).__name__ == 'PCB_VIA' else t.GetLayer(), mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetX() + bb.GetWidth()), mm(bb.GetY() + bb.GetHeight()), t.GetNetCode()))
for f in b.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox(); lay = None if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else (pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
        obs.append((lay, mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetX() + bb.GetWidth()), mm(bb.GetY() + bb.GetHeight()), p.GetNetCode()))
keep = [z for z in b.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]
def free(x0, y0, x1, y1, layer, allow_net):
    for lay, ax, ay, bx, by, n in obs:
        if n == allow_net: continue
        if layer is not None and lay is not None and lay != layer: continue
        if not (x1 + CLR <= ax or bx + CLR <= x0 or y1 + CLR <= ay or by + CLR <= y0): return False
    return True
def in_keepout(x, y): return any(z.Outline().Contains(P(x, y)) for z in keep)
added = skipped = 0
for f in b.GetFootprints():
    cx0, cy0 = mm(f.GetPosition().x), mm(f.GetPosition().y)
    for p in f.Pads():
        if p.GetNetCode() != nc or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH: continue
        w, h = mm(p.GetSize().x), mm(p.GetSize().y)
        if min(w, h) >= 0.4: continue                       # only fine-pitch pads need an escape
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        cx, cy = mm(p.GetPosition().x), mm(p.GetPosition().y)
        # outward = along the pad's long axis, away from the package centre
        if h > w: dx, dy = 0.0, (1.0 if cy > cy0 else -1.0)
        else: dx, dy = (1.0 if cx > cx0 else -1.0), 0.0
        trk = max(0.15, min(0.25, min(w, h))); done = False
        for rad in (max(h, w) / 2 + 0.55, max(h, w) / 2 + 0.75, max(h, w) / 2 + 1.0, max(h, w) / 2 + 1.3):
            vx, vy = cx + dx * rad, cy + dy * rad; r = VIA_D / 2
            if in_keepout(vx, vy) or not free(vx - r, vy - r, vx + r, vy + r, None, nc): continue
            tx0, ty0, tx1, ty1 = min(cx, vx) - trk / 2, min(cy, vy) - trk / 2, max(cx, vx) + trk / 2, max(cy, vy) + trk / 2
            if not free(tx0, ty0, tx1, ty1, layer, nc): continue
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(vx, vy)); v.SetWidth(FromMM(VIA_D)); v.SetDrill(FromMM(VIA_DRILL)); v.SetNetCode(nc); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)
            t = pcbnew.PCB_TRACK(b); t.SetStart(P(cx, cy)); t.SetEnd(P(vx, vy)); t.SetWidth(FromMM(trk)); t.SetLayer(layer); t.SetNetCode(nc); b.Add(t)
            obs.append((None, vx - r, vy - r, vx + r, vy + r, nc)); obs.append((layer, tx0, ty0, tx1, ty1, nc)); added += 1; done = True; break
        if not done: skipped += 1; print('no room for an escape via at', f.GetReference(), p.GetNumber(), round(cx, 1), round(cy, 1))
b.Save(SRC); print(f'{NET} escape vias added: {added}, pads without room: {skipped}')
