#!/usr/bin/env python3
"""Draw the copper of a board window straight from pcbnew data (F.Cu red, B.Cu blue, pads, vias; listed nets in green).
Two steps (KiCad's Python has no PIL): AppRun python3.11 render_area.py dump board.kicad_pcb geo.json
                                       python3 render_area.py draw geo.json x0 y0 x1 y1 out.png [NET ...]"""
import sys, json
if sys.argv[1] == 'dump':
    import pcbnew
    b = pcbnew.LoadBoard(sys.argv[2]); g = {'tracks': [], 'vias': [], 'pads': []}
    for t in b.GetTracks():
        if t.GetClass() == 'PCB_VIA': g['vias'].append([t.GetPosition().x / 1e6, t.GetPosition().y / 1e6, t.GetWidth() / 1e6, t.GetNetname()])
        else: g['tracks'].append([t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6, t.GetWidth() / 1e6, t.GetLayerName(), t.GetNetname()])
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox(); g['pads'].append([bb.GetX() / 1e6, bb.GetY() / 1e6, (bb.GetX() + bb.GetWidth()) / 1e6, (bb.GetY() + bb.GetHeight()) / 1e6, p.GetNetname(), fp.GetReference() + ':' + p.GetNumber()])
    json.dump(g, open(sys.argv[3], 'w')); sys.exit()
from PIL import Image, ImageDraw
g = json.load(open(sys.argv[2])); x0, y0, x1, y1 = map(float, sys.argv[3:7]); out = sys.argv[7]; hl = set(sys.argv[8:]); S = 40.0
im = Image.new('RGB', (int((x1 - x0) * S), int((y1 - y0) * S)), 'white'); d = ImageDraw.Draw(im)
def P(x, y): return ((x - x0) * S, (y - y0) * S)
for layer, c in (('B.Cu', (110, 150, 230)), ('F.Cu', (225, 70, 70))):
    for ax, ay, bx, by, w, ln, n in g['tracks']:
        if ln == layer: d.line([P(ax, ay), P(bx, by)], fill=(0, 170, 0) if n in hl else c, width=max(1, int(w * S)))
for ax, ay, bx, by, n, ref in g['pads']:
    a, c2 = P(ax, ay), P(bx, by)
    if c2[0] < 0 or a[0] > im.size[0] or c2[1] < 0 or a[1] > im.size[1]: continue
    d.rectangle([a, c2], outline=(0, 140, 0) if n in hl else (120, 0, 0), fill=(255, 210, 90) if n in hl else None)
for x, y, w, n in g['vias']:
    (px, py), r = P(x, y), w / 2 * S
    d.ellipse([px - r, py - r, px + r, py + r], outline=(0, 0, 0), fill=(0, 170, 0) if n in hl else (200, 200, 200))
im.save(out); print(out, im.size)
