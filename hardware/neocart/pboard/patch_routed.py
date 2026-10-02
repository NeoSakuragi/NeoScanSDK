#!/usr/bin/env python3
"""Before continuing the routing: add a copper keepout band along the board edge and delete tracks that already
violate the edge clearance, so the router redoes them inside the band. Run with AppRun python3.11."""
import os, math, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb')
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
b = pcbnew.LoadBoard(SRC)
b.GetDesignSettings().m_CopperEdgeClearance = FromMM(0.3)
edges = [(d.GetShape(), (mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))) for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
def dist_pt_seg(p, a, c):
    ax, ay = a; cx, cy = c; px, py = p; dx, dy = cx - ax, cy - ay; L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2)); return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
def dist_edge(p):
    best = 1e9
    for kind, a, c in edges:
        if kind == pcbnew.S_CIRCLE: best = min(best, abs(math.dist(p, a) - math.dist(a, c)))
        else: best = min(best, dist_pt_seg(p, a, c))
    return best
BB = b.GetBoardEdgesBoundingBox(); bx0, by0, bx1, by1 = mm(BB.GetX()), mm(BB.GetY()), mm(BB.GetX() + BB.GetWidth()), mm(BB.GetY() + BB.GetHeight())
def contains(x, y): return bx0 < x < bx1 and by0 < y < by1
removed = 0
for t in list(b.GetTracks()):
    if type(t).__name__ != 'PCB_TRACK': continue
    s, e = (mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y)); m = ((s[0] + e[0]) / 2, (s[1] + e[1]) / 2)
    if min(dist_edge(s), dist_edge(e), dist_edge(m)) < 0.3 + mm(t.GetWidth()) / 2 + 0.05: b.Remove(t); removed += 1
print('edge-violating tracks removed:', removed)
# keepout band: ring of rule areas 0.45 mm wide just inside the outline (rectangles along straight edges)
def band(x0, y0, x1, y1):
    k = pcbnew.ZONE(b); k.SetIsRuleArea(True); k.SetDoNotAllowTracks(True); k.SetDoNotAllowVias(True); k.SetDoNotAllowZoneFills(False)
    k.SetLayerSet(pcbnew.LSET.AllCuMask(4)); k.AddPolygon(pcbnew.VECTOR_VECTOR2I([P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)])); b.Add(k)
W = 0.45
for kind, a, c in edges:
    if kind == pcbnew.S_CIRCLE: continue
    (x0, y0), (x1, y1) = a, c
    if abs(y0 - y1) < 0.01:      # horizontal edge: band on the inside; decide side by testing a point
        y = y0
        for sgn in (1, -1):
            test = (min(x0, x1) + abs(x1 - x0) / 2, y + sgn * 1.0)
            if contains(*test) and dist_edge(test) > 0.9: band(min(x0, x1), min(y, y + sgn * W), max(x0, x1), max(y, y + sgn * W)); break
    elif abs(x0 - x1) < 0.01:
        x = x0
        for sgn in (1, -1):
            test = (x + sgn * 1.0, min(y0, y1) + abs(y1 - y0) / 2)
            if contains(*test) and dist_edge(test) > 0.9: band(min(x, x + sgn * W), min(y0, y1), max(x, x + sgn * W), max(y0, y1)); break
b.Save(SRC); print('saved with edge keepout band')
