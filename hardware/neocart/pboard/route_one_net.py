#!/usr/bin/env python3
"""Maze-route ONE net that Freerouting left unrouted: grid Dijkstra over F.Cu / In2.Cu / B.Cu with obstacles from every other net
(tracks, vias, pads, hole keepouts), 45-degree moves, vias where all layers are free. Usage: AppRun python3.11 route_one_net.py NET [board]"""
import os, sys, math, heapq, pcbnew
from pcbnew import VECTOR2I, FromMM
HERE = os.path.dirname(os.path.abspath(__file__))
_skip = {i + 1 for i, a in enumerate(sys.argv) if a in ('--pad', '--from', '--to')}
args = [a for i, a in enumerate(sys.argv) if i > 0 and not a.startswith('--') and i not in _skip]; NET = args[0]; SRC = args[1] if len(args) > 1 else os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb')
START_PAD = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--pad'), None)
NOVIA = '--novia' in sys.argv
FROM = next((tuple(map(float, sys.argv[i + 1].split(','))) for i, a in enumerate(sys.argv) if a == '--from'), None)
TO = next((tuple(map(float, sys.argv[i + 1].split(','))) for i, a in enumerate(sys.argv) if a == '--to'), None)
POINT = '--point' in sys.argv
args = [a for a in args if ',' not in a]
b = pcbnew.LoadBoard(SRC); net = b.GetNetsByName()[NET]; nc = net.GetNetCode()
def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
TRK, VIA_D, VIA_DRILL, CLR, STEP = float(os.environ.get('ROUTE_TRK', 0.15)), 0.5, 0.3, float(os.environ.get('ROUTE_CLR', 0.15)), float(os.environ.get('ROUTE_STEP', 0.1))   # 0.4/0.2 via fits at the tip of a 0.5 mm pitch pad (JLCPCB min 0.25/0.15)
LAYERS = [n for n in ('F.Cu', 'In2.Cu', 'B.Cu') if b.IsLayerEnabled(b.GetLayerID(n)) and b.GetLayerType(b.GetLayerID(n)) != pcbnew.LT_POWER]; LID = {n: b.GetLayerID(n) for n in LAYERS}   # never route through a plane layer
allpads = [(fp, p) for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == nc]
PLANE = any((not z.GetIsRuleArea()) and z.GetNetCode() == nc for z in b.Zones())
if FROM and TO:
    pads = []; others = []; owncu = [t for t in b.GetTracks() if t.GetNetCode() == nc]; pts = [FROM, TO]
    START_PAD = None
elif START_PAD:
    r0, n0 = START_PAD.split(':'); pads = [next((fp, p) for fp, p in allpads if fp.GetReference() == r0 and p.GetNumber() == n0)]
    others = [(fp, p) for fp, p in allpads if (fp, p) != pads[0]]
    owncu = [t for t in b.GetTracks() if t.GetNetCode() == nc]
    # window: around the start pad, wide enough to reach the nearest own copper or pad
    tgt = [(mm(t.GetPosition().x), mm(t.GetPosition().y)) for t in owncu] + [(mm(p.GetPosition().x), mm(p.GetPosition().y)) for _, p in others]
    sx, sy = mm(pads[0][1].GetPosition().x), mm(pads[0][1].GetPosition().y)
    near = sorted(tgt, key=lambda q: math.dist(q, (sx, sy)))[:3] if tgt else []
    pts = [(sx, sy)] + near + ([TO] if TO else [])
else:
    assert len(allpads) == 2, [(fp.GetReference(), p.GetNumber()) for fp, p in allpads]
    pads = allpads; others = []; owncu = []; pts = [(mm(p.GetPosition().x), mm(p.GetPosition().y)) for _, p in pads]
PADW = 25 if not (START_PAD or FROM) else 8
X0, X1 = min(x for x, _ in pts) - PADW, max(x for x, _ in pts) + (16 if not (START_PAD or FROM) else 8); Y0, Y1 = min(y for _, y in pts) - (30 if not (START_PAD or FROM) else 8), max(y for _, y in pts) + (6 if not (START_PAD or FROM) else 8)
NX, NY = int((X1 - X0) / STEP) + 1, int((Y1 - Y0) / STEP) + 1
def cell(x, y): return int(round((x - X0) / STEP)), int(round((y - Y0) / STEP))
obst = {n: bytearray(NX * NY) for n in LAYERS}      # 1 = a 0.15 mm track centred here would violate clearance
viabad = bytearray(NX * NY)                          # 1 = a via centred here would violate clearance on some layer
def paint_disc(arr, cx, cy, r):
    i0, i1 = max(0, int((cx - r - X0) / STEP)), min(NX - 1, int((cx + r - X0) / STEP) + 1)
    j0, j1 = max(0, int((cy - r - Y0) / STEP)), min(NY - 1, int((cy + r - Y0) / STEP) + 1)
    r2 = r * r
    for j in range(j0, j1 + 1):
        dy = Y0 + j * STEP - cy
        for i in range(i0, i1 + 1):
            dx = X0 + i * STEP - cx
            if dx * dx + dy * dy <= r2: arr[j * NX + i] = 1
def paint_seg(arr, ax, ay, cx, cy, r):
    n = max(1, int(math.dist((ax, ay), (cx, cy)) / (STEP / 2)))
    for k in range(n + 1):
        t = k / n; paint_disc(arr, ax + (cx - ax) * t, ay + (cy - ay) * t, r)
def paint_rect(arr, x0, y0, x1, y1, r):
    i0, i1 = max(0, int((x0 - r - X0) / STEP)), min(NX - 1, int((x1 + r - X0) / STEP) + 1)
    j0, j1 = max(0, int((y0 - r - Y0) / STEP)), min(NY - 1, int((y1 + r - Y0) / STEP) + 1)
    for j in range(j0, j1 + 1):
        y = Y0 + j * STEP; dy = max(y0 - y, 0, y - y1)
        for i in range(i0, i1 + 1):
            x = X0 + i * STEP; dx = max(x0 - x, 0, x - x1)
            if dx * dx + dy * dy <= r * r: arr[j * NX + i] = 1
def inwin(x, y, r): return X0 - r <= x <= X1 + r and Y0 - r <= y <= Y1 + r
RT, RV = TRK / 2 + CLR + 0.01, VIA_D / 2 + CLR
for t in b.GetTracks():
    if t.GetNetCode() == nc: continue
    if t.GetClass() == 'PCB_VIA':
        x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
        if not inwin(x, y, 2): continue
        for n in LAYERS: paint_disc(obst[n], x, y, mm(t.GetWidth()) / 2 + RT)
        paint_disc(viabad, x, y, mm(t.GetWidth()) / 2 + RV)
    else:
        s, e = t.GetStart(), t.GetEnd(); ax, ay, cx, cy = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        # a long track crossing the window has both ends outside it: test the segment's bounding box, not its ends (this bug shorted FA2 into VA_DQ7 once)
        if max(ax, cx) < X0 - 2 or min(ax, cx) > X1 + 2 or max(ay, cy) < Y0 - 2 or min(ay, cy) > Y1 + 2: continue
        ln = b.GetLayerName(t.GetLayer())
        if ln in obst: paint_seg(obst[ln], ax, ay, cx, cy, mm(t.GetWidth()) / 2 + RT)
        paint_seg(viabad, ax, ay, cx, cy, mm(t.GetWidth()) / 2 + RV)
for fp in b.GetFootprints():
    for p in fp.Pads():
        bb = p.GetBoundingBox(); x0, y0, x1, y1 = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
        if not inwin((x0 + x1) / 2, (y0 + y1) / 2, 3): continue
        if p.GetNetCode() == nc: continue
        th = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
        HR = 0.25 + 0.01   # board hole-to-copper clearance for plated / unplated holes
        for n in LAYERS:
            if th or p.IsOnLayer(LID[n]): paint_rect(obst[n], x0, y0, x1, y1, max(RT, TRK / 2 + HR) if th else RT)
        paint_rect(viabad, x0, y0, x1, y1, max(RV, VIA_D / 2 + HR) if th else RV)
for z in b.Zones():
    if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
        bb = z.GetBoundingBox(); x0, y0, x1, y1 = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
        if not (x1 < X0 or x0 > X1 or y1 < Y0 or y0 > Y1):
            for n in LAYERS: paint_rect(obst[n], x0, y0, x1, y1, 0.1)
            paint_rect(viabad, x0, y0, x1, y1, 0.1)
# vias must also keep the plane's clearance from In1 GND copper: fine by construction (the fill retreats). Board edge: keep 0.35 mm.
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.S_SEGMENT:
        s, e = d.GetStart(), d.GetEnd()
        for n in LAYERS: paint_seg(obst[n], mm(s.x), mm(s.y), mm(e.x), mm(e.y), 0.35 + TRK / 2)
        paint_seg(viabad, mm(s.x), mm(s.y), mm(e.x), mm(e.y), 0.35 + VIA_D / 2)
# start / goal cells: inside the two pads, on the layers those pads live on
def pad_cells(p):
    bb = p.GetBoundingBox(); x0, y0, x1, y1 = mm(bb.GetLeft()) + TRK / 2, mm(bb.GetTop()) + TRK / 2, mm(bb.GetRight()) - TRK / 2, mm(bb.GetBottom()) - TRK / 2
    out = []
    for n in LAYERS:
        if not p.IsOnLayer(LID[n]): continue
        i0, j0 = cell(x0, y0); i1, j1 = cell(x1, y1)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1): out.append((n, i, j))
    return out
# the net's own pads are never obstacles (their neighbours' dilation may have painted into them)
for _, p in allpads:
    bb = p.GetBoundingBox(); x0, y0, x1, y1 = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
    if not inwin((x0 + x1) / 2, (y0 + y1) / 2, 1): continue
    for n in LAYERS:
        if not p.IsOnLayer(LID[n]): continue
        i0, j0 = cell(x0 + TRK / 2, y0 + TRK / 2); i1, j1 = cell(x1 - TRK / 2, y1 - TRK / 2)
        for j in range(max(0, j0), min(NY - 1, j1) + 1):
            for i in range(max(0, i0), min(NX - 1, i1) + 1): obst[n][j * NX + i] = 0
def copper_cells_near(pt, r=0.6):
    out = set()
    for t in owncu:
        if t.GetClass() == 'PCB_VIA':
            x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
            if math.dist((x, y), pt) < r:
                for n in LAYERS: out.add((n,) + cell(x, y))
        else:
            ln = b.GetLayerName(t.GetLayer()); s_, e_ = t.GetStart(), t.GetEnd()
            if ln not in LAYERS: continue
            k = max(1, int(math.dist((mm(s_.x), mm(s_.y)), (mm(e_.x), mm(e_.y))) / STEP))
            for q in range(k + 1):
                x, y = mm(s_.x) + (mm(e_.x) - mm(s_.x)) * q / k, mm(s_.y) + (mm(e_.y) - mm(s_.y)) * q / k
                if math.dist((x, y), pt) < r: out.add((ln,) + cell(x, y))
    for fp, p in allpads:
        x, y = mm(p.GetPosition().x), mm(p.GetPosition().y)
        if math.dist((x, y), pt) < r + 0.5: out |= set(pad_cells(p))
    return out
def point_cells(pt, r=0.35):
    out = set(); i0, j0 = cell(pt[0], pt[1]); k = int(r / STEP) + 1
    for n in LAYERS:
        for j in range(j0 - k, j0 + k + 1):
            for i in range(i0 - k, i0 + k + 1):
                if 0 <= i < NX and 0 <= j < NY and math.hypot((i - i0) * STEP, (j - j0) * STEP) <= r and not obst[n][j * NX + i]: out.add((n, i, j))
    return out
if FROM and TO:
    starts = list(copper_cells_near(FROM)); goals = point_cells(TO) if POINT else copper_cells_near(TO)
    for c in starts: obst[c[0]][c[2] * NX + c[1]] = 0
    for c in goals: obst[c[0]][c[2] * NX + c[1]] = 0
    assert starts and goals, ('no own copper near', FROM, TO, len(starts), len(goals))
else: starts = pad_cells(pads[0][1])
if FROM and TO: pass
elif START_PAD and TO and POINT: goals = point_cells(TO)
elif START_PAD:
    goals = set()
    for _, p in others:
        if inwin(mm(p.GetPosition().x), mm(p.GetPosition().y), 0): goals |= set(pad_cells(p))
    for t in owncu:
        if t.GetClass() == 'PCB_VIA':
            x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
            if inwin(x, y, 0):
                for n in LAYERS: goals.add((n,) + cell(x, y))
        else:
            ln = b.GetLayerName(t.GetLayer()); s_, e_ = t.GetStart(), t.GetEnd()
            if ln in LAYERS and inwin(mm(s_.x), mm(s_.y), 0):
                k = max(1, int(math.dist((mm(s_.x), mm(s_.y)), (mm(e_.x), mm(e_.y))) / STEP))
                for q in range(k + 1): goals.add((ln,) + cell(mm(s_.x) + (mm(e_.x) - mm(s_.x)) * q / k, mm(s_.y) + (mm(e_.y) - mm(s_.y)) * q / k))
else:
    goals = set(pad_cells(pads[1][1]))
print(NET, 'from', (pads[0][0].GetReference() + ' ' + pads[0][1].GetNumber()) if pads else FROM, 'to', TO if FROM else (pads[1][0].GetReference() + ' ' + pads[1][1].GetNumber()) if not (START_PAD or FROM) else 'own copper / other pads' + (' (plane: any via)' if PLANE else ''), '| grid', NX, 'x', NY, '| start cells', len(starts), 'goal cells', len(goals))
# Dijkstra
INF = 1e18; dist = {}; prev = {}; pq = []
for s in starts: dist[s] = 0; heapq.heappush(pq, (0, s))
MOVES = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
VIA_COST = 40 if not NOVIA else 10 ** 9; found = None; vias_here = False
while pq:
    d, u = heapq.heappop(pq)
    if d > dist.get(u, INF): continue
    if u in goals: found = u; break
    n, i, j = u
    for di, dj, c in MOVES:
        ii, jj = i + di, j + dj
        if not (0 <= ii < NX and 0 <= jj < NY): continue
        v = (n, ii, jj)
        if obst[n][jj * NX + ii] and v not in goals: continue
        if d + c < dist.get(v, INF): dist[v] = d + c; prev[v] = u; heapq.heappush(pq, (d + c, v))
    if 0 <= i < NX and 0 <= j < NY and not viabad[j * NX + i] and not NOVIA:
        if PLANE and START_PAD and not (TO and POINT): found = u; vias_here = True; break
        for n2 in LAYERS:
            if n2 == n: continue
            v = (n2, i, j)
            if obst[n2][j * NX + i]: continue
            if d + VIA_COST < dist.get(v, INF): dist[v] = d + VIA_COST; prev[v] = u; heapq.heappush(pq, (d + VIA_COST, v))
if not found:
    import collections
    reach = collections.Counter(n for (n, i, j) in dist); ext = {}
    for (n, i, j) in dist: e = ext.setdefault(n, [1e9, -1e9, 1e9, -1e9]); e[0] = min(e[0], i); e[1] = max(e[1], i); e[2] = min(e[2], j); e[3] = max(e[3], j)
    print('reachable cells from the start per layer', dict(reach)); print('extent (mm)', {n: (round(X0 + e[0] * STEP, 1), round(X0 + e[1] * STEP, 1), round(Y0 + e[2] * STEP, 1), round(Y0 + e[3] * STEP, 1)) for n, e in ext.items()})
    sys.exit('NO PATH')
path = [found]
while path[-1] in prev: path.append(prev[path[-1]])
path.reverse()
# compress into straight runs per layer, emit tracks + vias
def xy(c): return (X0 + c[1] * STEP, Y0 + c[2] * STEP)
segs = []; vias = []; run = [path[0]]
for a, c in zip(path, path[1:]):
    if a[0] != c[0]: 
        segs.append((a[0], run)); vias.append(xy(a)); run = [c]; continue
    run.append(c)
segs.append((run[0][0], run))
def simplify(cells):
    pts = [xy(c) for c in cells]
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = out[-1], pts[k], pts[k + 1]
        if abs((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)) > 1e-9: out.append(pts[k])
    out.append(pts[-1]); return out
ntr = 0
if len(path) < 2 and not vias_here:
    print('routed', NET, ': nothing to add, the pad already touches its copper'); sys.exit(0)
if vias_here: vias.append(xy(found))
existing_vias = {(round(mm(t.GetPosition().x), 2), round(mm(t.GetPosition().y), 2)) for t in b.GetTracks() if t.GetClass() == 'PCB_VIA'}
for layer, cells in segs:
    pts = simplify(cells)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6: continue          # Freerouting cannot normalise zero-length wires
        t = pcbnew.PCB_TRACK(b); t.SetStart(P(x0, y0)); t.SetEnd(P(x1, y1)); t.SetWidth(FromMM(TRK)); t.SetLayer(LID[layer]); t.SetNetCode(nc); b.Add(t); ntr += 1
nvia = 0
for (x, y) in vias:
    if (round(x, 2), round(y, 2)) in existing_vias: continue              # never stack a via on an existing one
    v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(FromMM(VIA_D)); v.SetDrill(FromMM(VIA_DRILL)); v.SetNetCode(nc); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v); nvia += 1
# snap the two ends exactly onto the pad centres with a final stub
for (fp, p), end in ([(pads[0], path[0])] if pads else []) + ([(pads[1], path[-1])] if not (START_PAD or FROM) else []):
    x, y = xy(end); px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
    if math.dist((x, y), (px, py)) > 0.02:
        t = pcbnew.PCB_TRACK(b); t.SetStart(P(x, y)); t.SetEnd(P(px, py)); t.SetWidth(FromMM(TRK)); t.SetLayer(LID[end[0]]); t.SetNetCode(nc); b.Add(t); ntr += 1
ds = b.GetDesignSettings(); ds.m_ViasMinSize = min(ds.m_ViasMinSize, FromMM(VIA_D)); ds.m_MinThroughDrill = min(ds.m_MinThroughDrill, FromMM(VIA_DRILL))
b.Save(SRC)
print('routed', NET, ':', ntr, 'segments,', nvia, 'vias, layers', [l for l, _ in segs], 'length', round(dist[found] * STEP, 1), 'mm-ish; saved', SRC)
