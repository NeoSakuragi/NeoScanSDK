#!/usr/bin/env python3
"""NeoCart P board v2 - PCB generator (2 layers). Run: AppDir/AppRun python3.11 hardware/neocart/pboard/gen_pboard.py

Outline + gold fingers come from the checked blank PROG board (itself equal to the manufactured diag board).
Parts and nets come from design.py. Bus chips sit in one row directly above the finger pins they serve, glue logic
in a second row, flash above; every IC tries the four rotations and keeps the legal one with the shortest
connections. Overlap, containment, hole, shell-neck and orientation gates must pass before the board is written.
"""
import sys, os, json, math, importlib.util
import pcbnew
from pcbnew import VECTOR2I, FromMM

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
APP = os.path.abspath(os.path.join(ROOT, '..', '..', 'AppDir'))
STD_FP = os.path.join(APP, 'usr/share/kicad/footprints')
LIB_FP = os.path.join(HERE, 'lib/pboard.pretty')
BLANK = os.path.join(ROOT, 'blank/neocart_blank_prog.kicad_pcb')
OUT = os.environ.get('PBOARD_OUT', os.path.join(HERE, 'neocart_pboard.kicad_pcb'))
FLASH_Y = float(os.environ.get('FLASH_Y', '76'))
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); design = importlib.util.module_from_spec(spec); spec.loader.exec_module(design)
assert not design.check(), 'design.py check failed'

def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
report = {'checks': []}
def check(name, ok, detail=''):
    report['checks'].append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:200]})
    if not ok: raise SystemExit(f'CHECK FAILED: {name}: {detail}')

# ---------------------------------------------------------------------------------------------------------------
# Placement (mm, diag outline coordinates; y grows downward; fingers at y 150.65, tab step 138.75, no body below
# y 125, shell-post holes (94.75,127) (184.75,127) r 6). Finger x: ADPCM-A 75-93, ADPCM-B 95-113, strobes 128-164,
# D0..D15 = 204.5..166.4 (A face), A1..A19 = 204.5..158.8 (B face). Rotation None = pick the best of 0/90/180/270.
# ---------------------------------------------------------------------------------------------------------------
ROW1, ROW2 = 114.0, 100.5
PLACE = {
    # row 1, directly above the fingers they serve (board x 52.7-226.8, tab 62.45-217.05)
    # rot 180 on the registers and the 8T245s puts their finger-side row (D inputs / B port) at the bottom, bit 0 on the right
    'U7': (60.8, ROW1, 180), 'U6': (74.6, ROW1, 180), 'U10': (87.2, ROW1, 180),          # ADPCM-A: high reg, low reg, data (spreading them routed worse, iteration 7)
    'U11': (102.0, ROW1, 180), 'U8': (116.6, ROW1, 180), 'U9': (132.4, ROW1, 180),        # ADPCM-B: data, low reg, high reg, 1.5-2 mm apart (SDPAD0-7 feed all three)
    'U19': (141.0, 90.0, None),                                                             # 3.3 V LDO above the glue row, out of the bus row
    'U13': (148.6, ROW1, None), 'U15': (154.6, ROW1, None), 'U16': (160.6, ROW1, None),   # P-side glue over the strobes
    'U4': (172.0, ROW1, 0), 'U5': (200.0, ROW1, 180),                                        # 68K data / address: every U4 pin left of the hole keep-out (x < 178.75), U5 right of it
    # row 2: remaining glue
    'U14': (84.0, ROW2, None), 'U18': (100.0, ROW2, None), 'U12': (150.0, ROW2, None), 'U17': (161.0, ROW2, None),
    'JP1': (138.0, ROW2, 90),
    # row 3: flash
    'U2': (float(os.environ.get('U2_X', '97')), FLASH_Y, None),     # v3: one sample flash shared by both buses, between the two register groups
    'U1': (203.05, 101.99, 90),                                       # P flash right above U5/U4: short 68K paths (first found by the auto-placer, kept on purpose)
}

def load_fp(name):
    if name in ('R0603', 'C0603', 'C0805'):
        lib, fpn = {'R0603': ('Resistor_SMD.pretty', 'R_0603_1608Metric'), 'C0603': ('Capacitor_SMD.pretty', 'C_0603_1608Metric'), 'C0805': ('Capacitor_SMD.pretty', 'C_0805_2012Metric')}[name]
        return pcbnew.FootprintLoad(os.path.join(STD_FP, lib), fpn)
    if name == 'TP_PTH_1.0':
        fp = pcbnew.FOOTPRINT(board); fp.SetFPID(pcbnew.LIB_ID('pboard', 'TP_PTH_1.0'))
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH); pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(VECTOR2I(FromMM(1.7), FromMM(1.7))); pad.SetDrillSize(VECTOR2I(FromMM(1.0), FromMM(1.0))); pad.SetLayerSet(pcbnew.PAD.PTHMask())
        fp.Add(pad)
        return fp
    return pcbnew.FootprintLoad(LIB_FP, name)

# ---------------------------------------------------------------------------------------------------------------
blank = pcbnew.LoadBoard(BLANK)
board = pcbnew.BOARD()
n_edges = 0
for d in blank.GetDrawings():
    if d.GetLayer() != pcbnew.Edge_Cuts: continue
    sh = pcbnew.PCB_SHAPE(board); sh.SetShape(d.GetShape()); sh.SetStart(d.GetStart()); sh.SetEnd(d.GetEnd()); sh.SetLayer(pcbnew.Edge_Cuts); sh.SetWidth(FromMM(0.1)); board.Add(sh); n_edges += 1
check('outline copied from the blank board', n_edges == 18, n_edges)
for src in blank.GetFootprints():
    if src.GetReference() in ('J1', 'J2'):
        fp = pcbnew.FOOTPRINT(src); board.Add(fp); fp.SetPosition(src.GetPosition()); fp.SetOrientation(src.GetOrientation())
ds = board.GetDesignSettings(); ds.SetCopperLayerCount(2)
ds.m_MinClearance = FromMM(0.15); ds.m_TrackMinWidth = FromMM(0.15); ds.m_ViasMinSize = FromMM(0.45); ds.m_MinThroughDrill = FromMM(0.3)
ds.m_MinSilkTextHeight = FromMM(0.7); ds.m_MinSilkTextThickness = FromMM(0.12)
nc = None
for getter in (lambda: ds.m_NetSettings.GetDefaultNetclass(), lambda: ds.m_NetSettings.m_DefaultNetClass):
    try: nc = getter(); break
    except Exception: pass
if nc:
    nc.SetClearance(FromMM(0.15)); nc.SetTrackWidth(FromMM(0.15)); nc.SetViaDiameter(FromMM(0.5)); nc.SetViaDrill(FromMM(0.3))   # 0.3 mm drill = JLCPCB's free via class
bb = board.GetBoardEdgesBoundingBox(); BX0, BY0, BX1, BY1 = mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetX() + bb.GetWidth()), mm(bb.GetY() + bb.GetHeight())
check('blank outline present', abs((BX1 - BX0) - 174.1) < 0.2 and abs((BY1 - BY0) - 134.1) < 0.2, f'{BX1-BX0:.1f}x{BY1-BY0:.1f}')

nets = {}
def net(name):
    if name not in nets:
        ni = pcbnew.NETINFO_ITEM(board, name); board.Add(ni); nets[name] = ni
    return nets[name]
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
for ref, table in (('J2', design.CTRG2_A), ('J1', design.CTRG2_B)):
    for pad in fps[ref].Pads():
        n = table[int(pad.GetNumber())]
        if not n.startswith('NC_'): pad.SetNet(net(n))

placed = {}
POWER = {'GND', 'P3V3', 'VCC5'}
def add_part(ref, x, y, rot):
    pt = design.PARTS[ref]; fp = load_fp(pt['footprint'])
    fp.SetReference(ref); fp.SetValue(pt['value'] or ''); board.Add(fp)
    fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(rot or 0)
    fp.Reference().SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8))); fp.Reference().SetTextThickness(FromMM(0.12)); fp.Value().SetVisible(False)
    padnums = {p.GetNumber(): p for p in fp.Pads()}
    for netname, lst in design.NETS.items():
        for r, pn in lst:
            if r != ref: continue
            check(f'{ref} pad {pn} exists', pn in padnums, f'footprint {pt["footprint"]} pads {sorted(padnums)[:8]}...')
            if not netname.startswith('NC_'): padnums[pn].SetNet(net(netname))
    placed[ref] = fp; return fp
for fp in board.GetFootprints():
    if fp.GetReference() in ('J1', 'J2'): placed[fp.GetReference()] = fp

def body_box(fp):
    b = fp.GetBoundingBox(False, False)
    return (mm(b.GetX()), mm(b.GetY()), mm(b.GetX() + b.GetWidth()), mm(b.GetY() + b.GetHeight()))
def overlap(a, b, gap):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])
HOLES = ((94.75, 127.0), (184.75, 127.0))
BUS_ROW = ('U4', 'U5', 'U6', 'U7', 'U8', 'U9', 'U10', 'U11')
NOTCHES = ((88.75, 100.75), (178.75, 190.75))
def legal(bx, ref, skip=()):
    tab = 62.45 < bx[0] and bx[2] < 217.05
    if ref not in ('J1', 'J2') and bx[3] > 125.0: return False      # shell neck / slot housing keep-out
    if not (bx[0] >= BX0 + 0.6 and bx[2] <= BX1 - 0.6 and bx[1] >= BY0 + 0.6 and bx[3] <= (144.0 if tab else 138.75 - 0.6)): return False
    for hx, hy in HOLES:
        cx, cy = min(max(hx, bx[0]), bx[2]), min(max(hy, bx[1]), bx[3])
        if math.dist((cx, cy), (hx, hy)) < 6.0: return False
    for nx0, nx1 in NOTCHES:
        if overlap(bx, (nx0, 23.75, nx1, 26.25), 0.5): return False
    if ref[0] in 'RCT':                                              # finger corridors: nothing between a bus chip's finger-side pins and the fingers
        for r2 in BUS_ROW:
            if r2 in placed:
                cb = body_box(placed[r2])
                if overlap(bx, (cb[0] - 0.5, cb[3], cb[2] + 0.5, 138.75), 0.3): return False
    for r2, fp2 in placed.items():
        if r2 == ref or r2 in skip: continue
        gap = 0.3 if (ref[0] in 'RCT' and r2[0] in 'RCT') else 0.6
        if overlap(bx, body_box(fp2), gap): return False
    return True

def pad_xy(p): return (mm(p.GetPosition().x), mm(p.GetPosition().y))
def wirelength(fp):
    """sum over signal pads of the distance to the nearest same-net pad on another placed part"""
    tot = 0.0
    for pad in fp.Pads():
        n = pad.GetNetname()
        if not n or n in POWER: continue
        best = None
        for r2, fp2 in placed.items():
            if fp2 is fp: continue
            for p2 in fp2.Pads():
                if p2.GetNetname() == n:
                    dd = math.dist(pad_xy(pad), pad_xy(p2)); best = dd if best is None or dd < best else best
        if best is not None: tot += best
    return tot
# ICs: add at their spots, then pick rotations (two passes so every chip sees its neighbours' final orientation)
for ref, (x, y, rot) in PLACE.items(): add_part(ref, x, y, rot)
for _pass in range(2):
    for ref, (x, y, rot) in PLACE.items():
        if rot is not None: continue
        fp = placed[ref]; best = None
        for r in (0, 90, 180, 270):
            fp.SetOrientationDegrees(r)
            if not legal(body_box(fp), ref): continue
            wl = wirelength(fp)
            if best is None or wl < best[0]: best = (wl, r)
        check(f'{ref} has a legal rotation at {x},{y}', best, best)
        fp.SetOrientationDegrees(best[1])

def pad_pos(ref, pn):
    p = next(p for p in placed[ref].Pads() if p.GetNumber() == str(pn)); return pad_xy(p)
def anchor_for(ref):
    """a passive/test point goes next to its owner's supply pin, else an IC pad on its signal net, else above a finger pad"""
    owner = design.OWNER.get(ref)
    mynets = [n for n, lst in design.NETS.items() if any(r == ref for r, _ in lst)]
    if owner and owner in placed:
        rail = next((n for n in mynets if n in ('P3V3', 'VCC5')), None)
        cands = [(r, pn) for r, pn in design.NETS.get(rail, []) if r == owner]
        if cands: return pad_pos(*cands[0])
        return pad_xy(placed[owner])
    sig = [n for n in mynets if n not in POWER]
    for n in sig:
        for r, pn in design.NETS[n]:
            if r in placed and r.startswith(('U', 'JP')): return pad_pos(r, pn)
    for n in sig:
        for r, pn in design.NETS[n]:
            if r in ('J1', 'J2'):
                x, _ = pad_pos(r, pn); return (x, 123.0)
    x, y = pad_xy(placed['U19']); return (x, y - 9.0)          # power test points: next to the regulator
def auto_place(ref, ax, ay):
    fp = add_part(ref, ax, ay, 0)
    for rad in [x * 0.5 for x in range(2, 90)]:
        for k in range(24):
            ang = 2 * math.pi * k / 24
            for rot in (0, 90):
                fp.SetPosition(P(ax + rad * math.cos(ang), ay + rad * math.sin(ang))); fp.SetOrientationDegrees(rot)
                if legal(body_box(fp), ref): return True
    return False
unplaced = [ref for ref in design.PARTS if ref not in placed and not auto_place(ref, *anchor_for(ref))]
check('every passive and test point found a legal spot', not unplaced, unplaced)

# orientation gate: bus chips have their finger-side pins on the row facing the fingers
_finger_nets = {n for n, lst in design.NETS.items() if any(r in ('J1', 'J2') for r, _ in lst) and n not in POWER}
for ref in ('U4', 'U5', 'U6', 'U7', 'U8', 'U9', 'U10', 'U11'):
    fp = placed[ref]; cy = fp.GetPosition().y
    fy = [mm(p.GetPosition().y) for p in fp.Pads() if p.GetNetname() in _finger_nets]
    rows = sorted({round(mm(p.GetPosition().y), 1) for p in fp.Pads()})
    check(f'{ref} has horizontal pin rows', len(rows) == 2, rows)
    check(f'{ref} every finger pin is on the bottom row', fy and min(fy) > mm(cy), (min(fy), mm(cy)))

for ref in ('U4', 'U5'):
    xs = [mm(p.GetPosition().x) for p in placed[ref].Pads()]
    check(f'{ref} pins clear of the right hole keep-out column (178.75-190.75)', max(xs) < 178.75 or min(xs) > 190.75, (min(xs), max(xs)))
# geometric gates
boxes = {ref: body_box(fp) for ref, fp in placed.items()}
bad = []
refs = list(boxes)
for i in range(len(refs)):
    for j in range(i + 1, len(refs)):
        a, b = refs[i], refs[j]
        if {a, b} == {'J1', 'J2'}: continue
        gap = 0.3 if (a[0] in 'RCT' and b[0] in 'RCT') else 0.5
        if overlap(boxes[a], boxes[b], gap): bad.append((a, b))
check('no two parts overlap (0.5 mm ICs, 0.3 mm passives)', not bad, bad[:10])
for ref, bx in boxes.items():
    inside = bx[0] >= BX0 + 0.5 and bx[2] <= BX1 - 0.5 and bx[1] >= BY0 + 0.5 and bx[3] <= (157.75 - 0.5 if 62.45 < bx[0] and bx[2] < 217.05 else 138.75 - 0.5)
    check(f'{ref} inside the outline', inside, bx)
    if ref not in ('J1', 'J2'):
        check(f'{ref} clear of the shell neck and slot housing (no body below y 125)', bx[3] <= 125.0, bx)
        for hx, hy in HOLES:
            cx, cy = min(max(hx, bx[0]), bx[2]), min(max(hy, bx[1]), bx[3])
            check(f'{ref} clear of the shell-post hole', math.dist((cx, cy), (hx, hy)) >= 6.0, bx)
        for nx0, nx1 in NOTCHES:
            check(f'{ref} clear of the shell notch', not overlap(bx, (nx0, 23.75, nx1, 26.25), 0.5), bx)

# rule areas: no tracks or vias around the shell-post holes, a 0.45 mm band inside every straight outline edge
for hx, hy in HOLES:
    k = pcbnew.ZONE(board); k.SetIsRuleArea(True); k.SetDoNotAllowTracks(True); k.SetDoNotAllowVias(True); k.SetDoNotAllowZoneFills(True)
    k.SetDoNotAllowPads(False); k.SetDoNotAllowFootprints(False); k.SetLayerSet(pcbnew.LSET.AllCuMask(2))
    k.AddPolygon(pcbnew.VECTOR_VECTOR2I([P(hx + 6.0 * math.cos(2 * math.pi * i / 24), hy + 6.0 * math.sin(2 * math.pi * i / 24)) for i in range(24)])); board.Add(k)
def _band(x0, y0, x1, y1):
    k = pcbnew.ZONE(board); k.SetIsRuleArea(True); k.SetDoNotAllowTracks(True); k.SetDoNotAllowVias(True); k.SetDoNotAllowZoneFills(False)
    k.SetLayerSet(pcbnew.LSET.AllCuMask(2)); k.AddPolygon(pcbnew.VECTOR_VECTOR2I([P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)])); board.Add(k)
_edges = [((mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))) for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.S_SEGMENT]
def _dist_edge(pt):
    best = 1e9
    for a, c in _edges:
        ax, ay = a; cx, cy = c; dx, dy = cx - ax, cy - ay; L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0, min(1, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / L2)); best = min(best, math.hypot(pt[0] - (ax + t * dx), pt[1] - (ay + t * dy)))
    return best
def _inside(pt):
    x, y = pt
    if not ((BX0 < x < BX1 and BY0 < y < 138.75) or (62.45 < x < 217.05 and 138.75 <= y < 157.75)): return False
    return not any(nx0 < x < nx1 and y < 26.25 for nx0, nx1 in NOTCHES)
for (x0, y0), (x1, y1) in _edges:
    W = 0.45
    if abs(y0 - y1) < 0.01:
        for sgn in (1, -1):
            test = ((x0 + x1) / 2, y0 + sgn * 1.0)
            if _inside(test) and _dist_edge(test) > 0.9: _band(min(x0, x1), min(y0, y0 + sgn * W), max(x0, x1), max(y0, y0 + sgn * W)); break
    elif abs(x0 - x1) < 0.01:
        for sgn in (1, -1):
            test = (x0 + sgn * 1.0, (y0 + y1) / 2)
            if _inside(test) and _dist_edge(test) > 0.9: _band(min(x0, x0 + sgn * W), min(y0, y1), max(x0, x0 + sgn * W), max(y0, y1)); break
ds.m_CopperEdgeClearance = FromMM(0.3)
try:
    ns = ds.m_NetSettings
    pw = pcbnew.NETCLASS('power'); pw.SetTrackWidth(FromMM(0.3)); pw.SetClearance(FromMM(0.15)); pw.SetViaDiameter(FromMM(0.5)); pw.SetViaDrill(FromMM(0.3))
    ns.SetNetclass('power', pw)
    for n in ('P3V3', 'VCC5', 'GND'): ns.SetNetclassPatternAssignment(n, 'power')
except Exception as e:
    print('power netclass not set:', e)
# silkscreen: IC references above their bodies, jumper legend
for ref, fp in placed.items():
    if ref[0] in 'RCT': fp.Reference().SetVisible(False)
    elif ref not in ('J1', 'J2'):
        bx = body_box(fp); fp.Reference().SetPosition(P((bx[0] + bx[2]) / 2, bx[1] - 1.0)); fp.Reference().SetTextAngleDegrees(0)
        fp.Reference().SetTextSize(VECTOR2I(FromMM(0.9), FromMM(0.9))); fp.Reference().SetTextThickness(FromMM(0.15))
jb = body_box(placed['JP1'])
for i, txt in enumerate(('JP1: 1-2 PROGRAM', '2-3 PLAY')):
    t = pcbnew.PCB_TEXT(board); t.SetText(txt); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(P(jb[0] - 11.0, jb[1] + 3.0 + i * 1.6))
    t.SetTextSize(VECTOR2I(FromMM(1.0), FromMM(1.0))); t.SetTextThickness(FromMM(0.15)); board.Add(t)
t = pcbnew.PCB_TEXT(board); t.SetText('NeoCart PROG v3  2026-10-01'); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(P(140.0, 40.0))
t.SetTextSize(VECTOR2I(FromMM(1.5), FromMM(1.5))); t.SetTextThickness(FromMM(0.25)); board.Add(t)
open(os.path.join(HERE, 'fp-lib-table'), 'w').write('(fp_lib_table\n  (version 7)\n  (lib (name "pboard")(type "KiCad")(uri "${KIPRJMOD}/lib/pboard.pretty")(options "")(descr ""))\n  (lib (name "Resistor_SMD")(type "KiCad")(uri "' + STD_FP + '/Resistor_SMD.pretty")(options "")(descr ""))\n  (lib (name "Capacitor_SMD")(type "KiCad")(uri "' + STD_FP + '/Capacitor_SMD.pretty")(options "")(descr ""))\n)\n')
for fn in ('neocart_pboard', 'neocart_pboard_routed', *[os.path.splitext(os.path.basename(OUT))[0]]):
    pro = os.path.join(HERE, fn + '.kicad_pro')
    json.dump({'meta': {'filename': fn + '.kicad_pro', 'version': 1}, 'board': {'design_settings': {'rules': {'min_clearance': 0.127, 'min_track_width': 0.127, 'min_via_diameter': 0.45, 'min_through_hole_diameter': 0.3, 'min_via_annular_width': 0.1, 'min_copper_edge_clearance': 0.3, 'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.25, 'min_silk_clearance': 0.0, 'min_text_height': 0.7, 'min_text_thickness': 0.12}}},
               'net_settings': {'classes': [
                   {'name': 'Default', 'clearance': 0.15, 'track_width': 0.15, 'via_diameter': 0.5, 'via_drill': 0.3, 'microvia_diameter': 0.3, 'microvia_drill': 0.1, 'diff_pair_gap': 0.25, 'diff_pair_width': 0.2, 'diff_pair_via_gap': 0.25, 'wire_width': 6, 'bus_width': 12, 'line_style': 0, 'schematic_color': 'rgba(0, 0, 0, 0.000)', 'pcb_color': 'rgba(0, 0, 0, 0.000)', 'priority': 2147483647},
                   {'name': 'power', 'clearance': 0.15, 'track_width': 0.3, 'via_diameter': 0.5, 'via_drill': 0.3, 'microvia_diameter': 0.3, 'microvia_drill': 0.1, 'diff_pair_gap': 0.25, 'diff_pair_width': 0.2, 'diff_pair_via_gap': 0.25, 'wire_width': 6, 'bus_width': 12, 'line_style': 0, 'schematic_color': 'rgba(0, 0, 0, 0.000)', 'pcb_color': 'rgba(0, 0, 0, 0.000)', 'priority': 0}],
                   'meta': {'version': 4}, 'net_colors': None,
                   'netclass_patterns': [{'netclass': 'power', 'pattern': 'P3V3'}, {'netclass': 'power', 'pattern': 'VCC5'}, {'netclass': 'power', 'pattern': 'GND'}]}},
              open(pro, 'w'), indent=1)
    open(os.path.join(HERE, fn + '.kicad_dru'), 'w').write('(version 1)\n')

board.Save(OUT)
report['placement'] = {ref: [round(mm(fp.GetPosition().x), 2), round(mm(fp.GetPosition().y), 2), int(fp.GetOrientationDegrees())] for ref, fp in placed.items()}
json.dump(report, open(os.path.join(HERE, 'out_report.json'), 'w'), indent=1)
print(f'OK {len(placed)} parts placed, {len(nets)} nets, {len(report["checks"])} checks passed -> {OUT}')
