#!/usr/bin/env python3
"""Ground pours on F.Cu and B.Cu of the routed P board (above the tab step only: nothing between the gold fingers),
then zone fill. Run: AppDir/AppRun python3.11 hardware/neocart/pboard/pour_pboard.py [board]"""
import os, sys, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb')
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
b = pcbnew.LoadBoard(SRC)
_pts = [q for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for q in (d.GetStart(), d.GetEnd())]
X0, Y0, X1 = min(q.x for q in _pts) / 1e6, min(q.y for q in _pts) / 1e6, max(q.x for q in _pts) / 1e6
TAB_STEP = float(os.environ.get('POUR_YMAX', '138.75'))   # pours stop 0.5 mm above this y (P board: the tab step; programmer: its bottom edge + 0.5)
gnd = b.GetNetsByName()['GND']
have = {z.GetLayer() for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == 'GND'}   # idempotent: reuse existing pours
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    if layer in have: continue
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(gnd)
    z.SetLocalClearance(FromMM(0.25)); z.SetMinThickness(FromMM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD pads solid, through-hole pads (test points, jumper) thermal
    z.SetThermalReliefGap(FromMM(0.3)); z.SetThermalReliefSpokeWidth(FromMM(0.3))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.AddPolygon(pcbnew.VECTOR_VECTOR2I([P(X0, Y0), P(X1, Y0), P(X1, TAB_STEP - 0.5), P(X0, TAB_STEP - 0.5)]))
    b.Add(z)
filler = pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
# stitching vias: every 4 mm where a via (and its clearance) sits fully inside the filled copper of BOTH layers
import math
zf = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == 'GND' and z.GetLayer() == pcbnew.F_Cu][0]
zb = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == 'GND' and z.GetLayer() == pcbnew.B_Cu][0]
pf, pb = zf.GetFilledPolysList(pcbnew.F_Cu), zb.GetFilledPolysList(pcbnew.B_Cu)
R = 0.25 + 0.2          # via radius (0.5 mm via) + margin inside the fill
GRID = 6.0
holes = [(t.GetPosition().x / 1e6, t.GetPosition().y / 1e6) for t in b.GetTracks() if t.GetClass() == 'PCB_VIA'] + \
        [(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6) for f in b.GetFootprints() for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
added = 0; y = Y0 + 2.0
while y < TAB_STEP - 1.5:
    x = X0 + 2.0
    while x < X1 - 2.0:
        ring = [(x + R * math.cos(a * math.pi / 4), y + R * math.sin(a * math.pi / 4)) for a in range(8)] + [(x, y)]
        if all(pf.Contains(P(px, py)) and pb.Contains(P(px, py)) for px, py in ring) and all(math.hypot(x - hx, y - hy) > 1.2 for hx, hy in holes):
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(FromMM(0.5)); v.SetDrill(FromMM(0.3)); v.SetNet(gnd); b.Add(v); added += 1
        x += GRID
    y += GRID
filler.Fill(b.Zones())
print('stitching vias', added)
b.Save(SRC)
print('poured GND on F.Cu and B.Cu above y', TAB_STEP - 0.5, '->', SRC)
