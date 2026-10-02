#!/usr/bin/env python3
"""Silkscreen tidy-up on the routed board: every IC reference goes to the first side of its body (above, below,
left, right) where it touches no pad and no other silkscreen text; the board title goes to the free top area.
Usage: AppRun python3.11 fix_silk.py [board]"""
import os, sys, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb')
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
b = pcbnew.LoadBoard(SRC)
def box(item, grow=0.2):
    bb = item.GetBoundingBox(); return (mm(bb.GetX()) - grow, mm(bb.GetY()) - grow, mm(bb.GetX() + bb.GetWidth()) + grow, mm(bb.GetY() + bb.GetHeight()) + grow)
def hit(a, c): return not (a[2] <= c[0] or c[2] <= a[0] or a[3] <= c[1] or c[3] <= a[1])
pads = [box(p, 0.15) for f in b.GetFootprints() for p in f.Pads()]
silk_shapes = [box(g, 0.1) for f in b.GetFootprints() for g in f.GraphicalItems() if g.GetLayer() == pcbnew.F_SilkS]
texts = []
for d in b.GetDrawings():
    if isinstance(d, pcbnew.PCB_TEXT) and d.GetText().startswith('NeoCart PROG'):
        d.SetText('NeoCart PROG v3  2026-10-01'); d.SetPosition(P(170.0, 30.0))
    if isinstance(d, pcbnew.PCB_TEXT): texts.append(box(d))
moved = 0
for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    ref = f.GetReference()
    if not ref.startswith(('U', 'JP')) or not f.Reference().IsVisible(): continue
    body = f.GetBoundingBox(False, False); x0, y0, x1, y1 = mm(body.GetX()), mm(body.GetY()), mm(body.GetX() + body.GetWidth()), mm(body.GetY() + body.GetHeight())
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for (px, py, ang) in ((cx, y0 - 1.0, 0), (cx, y1 + 1.0, 0), (x0 - 1.0, cy, 90), (x1 + 1.0, cy, 90), (cx, y0 - 2.2, 0), (cx, y1 + 2.2, 0)):
        t = f.Reference(); t.SetTextAngleDegrees(ang); t.SetPosition(P(px, py)); bb = box(t, 0.1)
        own = box(f, -0.01)
        if not any(hit(bb, p) for p in pads) and not any(hit(bb, s) for s in silk_shapes) and not any(hit(bb, s) for s in texts):
            texts.append(bb); moved += 1; break
    else:
        print('no free spot for', ref)
b.Save(SRC); print('references placed:', moved)
