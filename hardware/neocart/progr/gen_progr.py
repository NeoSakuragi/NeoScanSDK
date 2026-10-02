#!/usr/bin/env python3
"""NeoCart programmer v1 - PCB generator (2 layers). Run: AppDir/AppRun python3.11 hardware/neocart/progr/gen_progr.py

176 x 76 mm board. The MVS slot (EDAC 345-120) runs along the top edge; the cart stands in it with its component side
toward the top edge (row A = the -y row), pin 1 at the LEFT end (seen from the component side, pin 1 is on the right:
standing at the top edge looking down the board, right = -x). Bus chips sit in one row under the slot pins they serve,
cart pins on the row facing the slot; latches behind them; the RP2350B and its reference circuit at the bottom centre,
USB-C on the bottom edge. Placement, orientation and overlap gates must pass before the board is written.
"""
import sys, os, json, math, importlib.util
import pcbnew
from pcbnew import VECTOR2I, FromMM

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, '..', '..', '..', 'AppDir'))
STD_FP = os.path.join(APP, 'usr/share/kicad/footprints')
LIB_FP = os.path.join(HERE, 'lib/progr.pretty')
OUT = os.environ.get('PROGR_OUT', os.path.join(HERE, 'neocart_progr.kicad_pcb'))
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); design = importlib.util.module_from_spec(spec); spec.loader.exec_module(design)
assert not design.check(), 'design.py check failed'

def mm(v): return v / 1e6
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))
report = {'checks': []}
def check(name, ok, detail=''):
    report['checks'].append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:200]})
    if not ok: raise SystemExit(f'CHECK FAILED: {name}: {detail}')

BX0, BY0, BW, BH = 20.0, 20.0, 176.0, 100.0
BX1, BY1 = BX0 + BW, BY0 + BH
SLOT_CX, SLOT_CY = BX0 + BW / 2, BY0 + 11.0                    # slot centre; rows at -/+ 2.54
PITCH, ROWS = 2.54, 5.08
def slot_x(k): return SLOT_CX + (k - 30.5) * PITCH           # pin k (1..60), pin 1 at the left
SLOT_BODY = (SLOT_CX - 79.5, SLOT_CY - 7.62, SLOT_CX + 79.5, SLOT_CY + 7.62)   # EDAC drawing: 159 mm x 0.600"
ROW1, ROW2 = BY0 + 30.0, BY0 + 43.0
PLACE = {
    'U5': (55.0, ROW1, None), 'U8': (71.5, ROW1, None),       # D0-D15 (A5-A20) and A1-A16 (B5-B20) share x 43-81
    'U7': (96.0, ROW1, None),                                 # strobes A21-A33, B24, B33
    'U9': (120.0, ROW1, None),                                # A17-A19, ADPCM high bits A43-A54, /RESET, 4 MHz, /SLOTCS
    'U6': (154.0, ROW1, None),                                # SDPAD B41-48, SDRAD B49-56
    'U10': (71.5, ROW2, None), 'U11': (120.0, ROW2, None),
    'U1': (float(os.environ.get('MOD_X', '96')), BY0 + 73.0, int(os.environ.get('MOD_ROT', '180'))),   # WeAct module; rot 180: GP0-24 (MD bus) faces the latches
    'U4': (150.0, BY0 + 62.0, None),                          # cart 5 V switch
    'LED1': (160.0, BY1 - 5.0, 0),
}
BUS = ('U5', 'U6', 'U7', 'U8', 'U9')
HOLES = [(BX0 + 4.0, BY0 + 22.0), (BX1 - 4.0, BY0 + 22.0), (BX0 + 4.0, BY1 - 4.0), (BX1 - 4.0, BY1 - 4.0)]

board = pcbnew.BOARD()
for (x0, y0), (x1, y1) in (((BX0, BY0), (BX1, BY0)), ((BX1, BY0), (BX1, BY1)), ((BX1, BY1), (BX0, BY1)), ((BX0, BY1), (BX0, BY0))):
    sh = pcbnew.PCB_SHAPE(board); sh.SetShape(pcbnew.SHAPE_T_SEGMENT); sh.SetStart(P(x0, y0)); sh.SetEnd(P(x1, y1)); sh.SetLayer(pcbnew.Edge_Cuts); sh.SetWidth(FromMM(0.1)); board.Add(sh)
LAYERS = int(os.environ.get('LAYERS', '2'))          # 2 routes once the QFN escape ring exists (DESIGN.md); 4 = In1 GND + In2 3.3 V planes
ds = board.GetDesignSettings(); ds.SetCopperLayerCount(LAYERS)
board.SetEnabledLayers(board.GetEnabledLayers())
ds.m_MinClearance = FromMM(0.15); ds.m_TrackMinWidth = FromMM(0.15); ds.m_ViasMinSize = FromMM(0.45); ds.m_MinThroughDrill = FromMM(0.3)
ds.m_CopperEdgeClearance = FromMM(0.3)

def slot_fp():
    fp = pcbnew.FOOTPRINT(board); fp.SetFPID(pcbnew.LIB_ID('progr', 'MVS_SLOT_EDAC_345-120'))
    for side, dy in (('A', -ROWS / 2), ('B', ROWS / 2)):
        for k in range(1, 61):
            pad = pcbnew.PAD(fp); pad.SetNumber(f'{side}{k}'); pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT if (side, k) == ('A', 1) else pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(VECTOR2I(FromMM(1.7), FromMM(1.7))); pad.SetDrillSize(VECTOR2I(FromMM(1.1), FromMM(1.1))); pad.SetLayerSet(pcbnew.PAD.PTHMask())
            fp.Add(pad); pad.SetFPRelativePosition(P((k - 30.5) * PITCH, dy))
    x0, y0, x1, y1 = [v - c for v, c in zip(SLOT_BODY, (SLOT_CX, SLOT_CY, SLOT_CX, SLOT_CY))]
    for layer in (pcbnew.F_SilkS, pcbnew.F_CrtYd):
        r = pcbnew.PCB_SHAPE(fp); r.SetShape(pcbnew.SHAPE_T_RECT); r.SetStart(P(x0, y0)); r.SetEnd(P(x1, y1)); r.SetLayer(layer); r.SetWidth(FromMM(0.12)); fp.Add(r)
    return fp
MOD_W, MOD_H = 41.402, 41.148                                 # WeAct drawing 尺寸图.pdf; pads 1.57 mm from the left/top edges, 38.10 mm outer row to outer row
MOD_ROWY = {'TO': 1.57, 'TI': 1.57 + 2.54, 'BI': 1.57 + 38.10 - 2.54, 'BO': 1.57 + 38.10}
def module_fp():
    fp = pcbnew.FOOTPRINT(board); fp.SetFPID(pcbnew.LIB_ID('progr', 'WEACT_RP2350B_CORE'))
    for pad_name, sig in design.MODULE_PADS.items():
        row, k = pad_name[:2], int(pad_name[2:])
        pad = pcbnew.PAD(fp); pad.SetNumber(pad_name); pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT if sig == 'GND' else pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(VECTOR2I(FromMM(1.7), FromMM(1.7))); pad.SetDrillSize(VECTOR2I(FromMM(1.0), FromMM(1.0))); pad.SetLayerSet(pcbnew.PAD.PTHMask())
        fp.Add(pad); pad.SetFPRelativePosition(P(1.57 + (k - 1) * 2.54 - MOD_W / 2, MOD_ROWY[row] - MOD_H / 2))
    for layer in (pcbnew.F_SilkS, pcbnew.F_CrtYd):
        r = pcbnew.PCB_SHAPE(fp); r.SetShape(pcbnew.SHAPE_T_RECT); r.SetStart(P(-MOD_W / 2, -MOD_H / 2)); r.SetEnd(P(MOD_W / 2, MOD_H / 2)); r.SetLayer(layer); r.SetWidth(FromMM(0.12)); fp.Add(r)
    for txt, (x, y) in (('USB-C', (-MOD_W / 2 + 4.0, 0.0)), ('WeAct RP2350B (components up)', (0.0, -4.0)), ('GP0-24', (0.0, MOD_ROWY['BI'] - MOD_H / 2 - 3.0)), ('GP25-47', (0.0, MOD_ROWY['TI'] - MOD_H / 2 + 3.0))):
        t = pcbnew.PCB_TEXT(fp); t.SetText(txt); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(P(x, y)); t.SetTextSize(VECTOR2I(FromMM(1.2), FromMM(1.2))); t.SetTextThickness(FromMM(0.18)); fp.Add(t)
    return fp
def load_fp(name):
    if name in ('R0603', 'C0603', 'C0805'):
        lib, fpn = {'R0603': ('Resistor_SMD.pretty', 'R_0603_1608Metric'), 'C0603': ('Capacitor_SMD.pretty', 'C_0603_1608Metric'), 'C0805': ('Capacitor_SMD.pretty', 'C_0805_2012Metric')}[name]
        return pcbnew.FootprintLoad(os.path.join(STD_FP, lib), fpn)
    if name == 'MVS_SLOT_EDAC_345-120': return slot_fp()
    if name == 'WEACT_RP2350B_CORE': return module_fp()
    if name in ('TP_PTH_1.0', 'MH_M3'):
        fp = pcbnew.FOOTPRINT(board); fp.SetFPID(pcbnew.LIB_ID('progr', name))
        pad = pcbnew.PAD(fp); pad.SetNumber('1' if name == 'TP_PTH_1.0' else '')
        if name == 'TP_PTH_1.0':
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH); pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE); pad.SetSize(VECTOR2I(FromMM(1.7), FromMM(1.7)))
            pad.SetDrillSize(VECTOR2I(FromMM(1.0), FromMM(1.0))); pad.SetLayerSet(pcbnew.PAD.PTHMask())
        else:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH); pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE); pad.SetSize(VECTOR2I(FromMM(3.2), FromMM(3.2)))
            pad.SetDrillSize(VECTOR2I(FromMM(3.2), FromMM(3.2))); pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
        fp.Add(pad); return fp
    return pcbnew.FootprintLoad(LIB_FP, name)

nets = {}
def net(name):
    if name not in nets:
        ni = pcbnew.NETINFO_ITEM(board, name); board.Add(ni); nets[name] = ni
    return nets[name]
placed = {}
POWER = {'GND', 'P3V3', 'VCART', 'VBUS'}
def add_part(ref, x, y, rot):
    pt = design.PARTS[ref]; fp = load_fp(pt['footprint'])
    fp.SetReference(ref); fp.SetValue(pt['value'] or ''); board.Add(fp)
    fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(rot or 0)
    fp.Reference().SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8))); fp.Reference().SetTextThickness(FromMM(0.12)); fp.Value().SetVisible(False)
    padnums = {p.GetNumber(): p for p in fp.Pads()}
    for netname, lst in design.NETS.items():
        for r, pn in lst:
            if r != ref: continue
            check(f'{ref} pad {pn} exists', pn in padnums, f'footprint {pt["footprint"]}')
            if not netname.startswith('NC_'): padnums[pn].SetNet(net(netname))
    placed[ref] = fp; return fp

def body_box(fp):
    b = fp.GetBoundingBox(False, False)
    return (mm(b.GetX()), mm(b.GetY()), mm(b.GetX() + b.GetWidth()), mm(b.GetY() + b.GetHeight()))
def overlap(a, b, gap):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])
def legal(bx, ref):
    if not (bx[0] >= BX0 + 0.6 and bx[2] <= BX1 - 0.6 and bx[1] >= BY0 + 0.6 and bx[3] <= BY1 - 0.6): return False
    if ref != 'J1' and overlap(bx, SLOT_BODY, 1.0): return False          # nothing under the slot housing
    for hx, hy in HOLES:
        cx, cy = min(max(hx, bx[0]), bx[2]), min(max(hy, bx[1]), bx[3])
        if math.dist((cx, cy), (hx, hy)) < 3.5: return False
    if ref[0] in 'RCT' or ref.startswith('LED'):                       # corridors: nothing between a bus chip and the slot
        for r2 in BUS:
            if r2 in placed:
                cb = body_box(placed[r2])
                if overlap(bx, (cb[0] - 0.5, SLOT_BODY[3], cb[2] + 0.5, cb[1]), 0.3): return False
        for lat, xc in (('U10', 'U8'), ('U11', 'U9')):               # ... nor between a latch and its level shifter (pre-routed straight links)
            if lat in placed and xc in placed:
                lb, xb = body_box(placed[lat]), body_box(placed[xc])
                if overlap(bx, (min(lb[0], xb[0]) - 0.5, xb[3], max(lb[2], xb[2]) + 0.5, lb[1]), 0.3): return False
    for r2, fp2 in placed.items():
        if r2 == ref: continue
        small = (ref[0] in 'RCTL' and r2[0] in 'RCTL')
        if overlap(bx, body_box(fp2), 0.3 if small else 0.6): return False
    return True
def pad_xy(p): return (mm(p.GetPosition().x), mm(p.GetPosition().y))
def wirelength(fp):
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

slot = add_part('J1', SLOT_CX, SLOT_CY, 0)
a1 = next(p for p in slot.Pads() if p.GetNumber() == 'A1'); b1 = next(p for p in slot.Pads() if p.GetNumber() == 'B1')
check('slot pad A1 at the left end of the -y row', pad_xy(a1)[0] < SLOT_CX and pad_xy(a1)[1] < SLOT_CY, pad_xy(a1))
check('slot pad B1 opposite A1', abs(pad_xy(b1)[0] - pad_xy(a1)[0]) < 0.01 and abs(pad_xy(b1)[1] - pad_xy(a1)[1] - ROWS) < 0.01)
check('slot pitch 2.54 / row spacing 5.08 (EDAC 345-120-520-201)', abs(slot_x(60) - slot_x(1) - 59 * 2.54) < 0.01)
for ref, (x, y, rot) in PLACE.items(): add_part(ref, x, y, rot)
# module orientation gates (the v4 adapter came back mirrored: check, never assume)
def mpad(name): return pad_xy(next(p for p in placed['U1'].Pads() if p.GetNumber() == name))
check('module: GP0-24 rows face the latch row (above GP25-47)', mpad('BI3')[1] < mpad('TI4')[1], (mpad('BI3'), mpad('TI4')))
check('module: inner rows between the outer rows', mpad('BO1')[1] < mpad('BI1')[1] < mpad('TI1')[1] < mpad('TO1')[1] if PLACE['U1'][2] == 180 else True)
check('module: outer-to-outer row distance 38.10 mm', abs(abs(mpad('TO1')[1] - mpad('BO1')[1]) - 38.10) < 0.01)
check('module: pad 1 rows run 15 x 2.54 mm', abs(abs(mpad('TO15')[0] - mpad('TO1')[0]) - 14 * 2.54) < 0.01)
cart_nets = {n for n in design.CART.values() if n not in POWER and not n.startswith('NC_')}
def facing_slot(fp):
    ys = [mm(p.GetPosition().y) for p in fp.Pads() if p.GetNetname() in cart_nets]
    return ys and max(ys) < mm(fp.GetPosition().y)
for _pass in range(2):
    for ref, (x, y, rot) in PLACE.items():
        if rot is not None: continue
        fp = placed[ref]; best = None
        for r in (0, 90, 180, 270):
            fp.SetOrientationDegrees(r)
            if not legal(body_box(fp), ref): continue
            if ref in BUS and not facing_slot(fp): continue
            wl = wirelength(fp)
            if best is None or wl < best[0]: best = (wl, r)
        check(f'{ref} has a legal rotation at {x},{y}', best, ref)
        fp.SetOrientationDegrees(best[1])
for ref in BUS:
    check(f'{ref}: every cart pin on the row facing the slot', facing_slot(placed[ref]))
for i, (hx, hy) in enumerate(HOLES, 1): add_part(f'MH{i}', hx, hy, 0)

def pad_pos(ref, pn):
    return pad_xy(next(p for p in placed[ref].Pads() if p.GetNumber() == str(pn)))
def anchor_for(ref):
    owner = design.OWNER.get(ref)
    mynets = [n for n, lst in design.NETS.items() if any(r == ref for r, _ in lst)]
    sig = [n for n in mynets if n not in POWER]
    for n in sig:                                               # a signal pin of an IC first (crystal caps, ILIM, divider ...)
        for r, pn in design.NETS[n]:
            if r in placed and r[0] in 'UYLJ' and r != 'J1': return pad_pos(r, pn)
    if owner and owner in placed:
        rail = next((n for n in mynets if n in POWER and n != 'GND'), None)
        cands = [(r, pn) for r, pn in design.NETS.get(rail, []) if r == owner]
        if cands: return pad_pos(*cands[0])
        return pad_xy(placed[owner])
    for n in sig:
        for r, pn in design.NETS[n]:
            if r in placed: return pad_pos(r, pn)
    return pad_xy(placed['U4'])
def auto_place(ref, ax, ay):
    fp = add_part(ref, ax, ay, 0)
    for rad in [x * 0.5 for x in range(2, 120)]:
        for k in range(24):
            ang = 2 * math.pi * k / 24
            for rot in (0, 90):
                fp.SetPosition(P(ax + rad * math.cos(ang), ay + rad * math.sin(ang))); fp.SetOrientationDegrees(rot)
                if legal(body_box(fp), ref): return True
    return False
order = sorted([r for r in design.PARTS if r not in placed], key=lambda r: (not r.startswith('C'), r))
unplaced = [ref for ref in order if not auto_place(ref, *anchor_for(ref))]
check('every passive and test point found a legal spot', not unplaced, unplaced)

boxes = {ref: body_box(fp) for ref, fp in placed.items()}
bad = [(a, b) for i, a in enumerate(boxes) for b in list(boxes)[i + 1:]
       if overlap(boxes[a], boxes[b], 0.25 if (a[0] in 'RCTLM' and b[0] in 'RCTLM') else 0.5)]
check('no two parts overlap', not bad, bad[:10])
for ref, bx in boxes.items():
    check(f'{ref} inside the outline', bx[0] >= BX0 + 0.5 and bx[2] <= BX1 - 0.5 and bx[1] >= BY0 + 0.5 and bx[3] <= BY1 - 0.5, bx)
    if ref != 'J1': check(f'{ref} not under the slot housing', not overlap(bx, SLOT_BODY, 0.5), bx)

# pre-route: every latch output faces its level-shifter input at the same x (U10->U8, U11->U9): one locked vertical
# F.Cu track each, so the router never has to find (or block) these 32 short links
n_pre = 0
for lat, xc in (('U10', 'U8'), ('U11', 'U9')):
    for q in placed[lat].Pads():
        n = q.GetNetname()
        if not n.startswith('L_'): continue
        a = next(p for p in placed[xc].Pads() if p.GetNetname() == n)
        (qx, qy), (ax, ay) = pad_xy(q), pad_xy(a)
        check(f'{n}: latch pin under its shifter pin', abs(qx - ax) < 0.01, (qx, ax))
        t = pcbnew.PCB_TRACK(board); t.SetStart(P(qx, qy)); t.SetEnd(P(ax, ay)); t.SetWidth(FromMM(0.15)); t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net(n)); t.SetLocked(True); board.Add(t); n_pre += 1
check('32 latch links pre-routed', n_pre == 32, n_pre)
# the links must not touch any other copper: pad of another net within track half-width + clearance of a link
for t in [t for t in board.GetTracks() if t.IsLocked()]:
    x, y0, y1 = mm(t.GetStart().x), min(mm(t.GetStart().y), mm(t.GetEnd().y)), max(mm(t.GetStart().y), mm(t.GetEnd().y))
    for ref, fp in placed.items():
        for p in fp.Pads():
            if p.GetNetname() == t.GetNetname(): continue
            b2 = p.GetBoundingBox(); px0, py0, px1, py1 = mm(b2.GetX()), mm(b2.GetY()), mm(b2.GetX() + b2.GetWidth()), mm(b2.GetY() + b2.GetHeight())
            check(f'{t.GetNetname()} link clear of {ref} pad {p.GetNumber()}', not (px0 - 0.23 < x < px1 + 0.23 and py0 - 0.23 < y1 and y0 < py1 + 0.23), (ref, p.GetNumber()))
# rule areas: Freerouting ignores copper-to-edge clearance, so a 0.45 mm no-track/no-via band runs inside every edge
for x0, y0, x1, y1 in ((BX0, BY0, BX1, BY0 + 0.45), (BX0, BY1 - 0.45, BX1, BY1), (BX0, BY0, BX0 + 0.45, BY1), (BX1 - 0.45, BY0, BX1, BY1)):
    k = pcbnew.ZONE(board); k.SetIsRuleArea(True); k.SetDoNotAllowTracks(True); k.SetDoNotAllowVias(True); k.SetDoNotAllowZoneFills(False)
    k.SetDoNotAllowPads(False); k.SetDoNotAllowFootprints(False); k.SetLayerSet(pcbnew.LSET.AllCuMask(2))
    k.AddPolygon(pcbnew.VECTOR_VECTOR2I([P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)])); board.Add(k)
# silkscreen
for ref, fp in placed.items():
    if ref[0] in 'RCTM': fp.Reference().SetVisible(False)
    elif ref != 'J1':
        bx = body_box(fp); fp.Reference().SetPosition(P((bx[0] + bx[2]) / 2, bx[1] - 1.0)); fp.Reference().SetTextAngleDegrees(0)
def silk(txt, x, y, size=1.0):
    t = pcbnew.PCB_TEXT(board); t.SetText(txt); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(P(x, y))
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(0.15 if size < 1.4 else 0.25)); board.Add(t)
silk('A1', slot_x(1) - 0.2, SLOT_CY - 5.2, 0.9); silk('B1', slot_x(1) - 0.2, SLOT_CY + 5.2, 0.9)
silk('A60', slot_x(60), SLOT_CY - 5.2, 0.9); silk('B60', slot_x(60), SLOT_CY + 5.2, 0.9)
silk('CART COMPONENT SIDE FACES THIS EDGE  ^', SLOT_CX, BY0 + 1.6, 1.0)
silk('NeoCart programmer v1  2026-10-01', 160.0, BY1 - 18.0, 1.4)
open(os.path.join(HERE, 'fp-lib-table'), 'w').write('(fp_lib_table\n  (version 7)\n  (lib (name "progr")(type "KiCad")(uri "${KIPRJMOD}/lib/progr.pretty")(options "")(descr ""))\n  (lib (name "Resistor_SMD")(type "KiCad")(uri "' + STD_FP + '/Resistor_SMD.pretty")(options "")(descr ""))\n  (lib (name "Capacitor_SMD")(type "KiCad")(uri "' + STD_FP + '/Capacitor_SMD.pretty")(options "")(descr ""))\n)\n')
if LAYERS == 4:
    for layer, n in ((pcbnew.In1_Cu, 'GND'), (pcbnew.In2_Cu, 'P3V3')):
        board.SetLayerType(layer, pcbnew.LT_POWER)
        z = pcbnew.ZONE(board); z.SetLayer(layer); z.SetNet(net(n)); z.SetLocalClearance(FromMM(0.25)); z.SetMinThickness(FromMM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.AddPolygon(pcbnew.VECTOR_VECTOR2I([P(BX0 + 0.5, BY0 + 0.5), P(BX1 - 0.5, BY0 + 0.5), P(BX1 - 0.5, BY1 - 0.5), P(BX0 + 0.5, BY1 - 0.5)])); board.Add(z)
    # planes are filled after routing (finish step); filling here segfaults pcbnew intermittently
board.Save(OUT)
# project files AFTER the board: pcbnew's Save rewrites the .kicad_pro with default net classes (0.2 mm clearance)
PRO = {'meta': {'version': 1}, 'board': {'design_settings': {'rules': {'min_clearance': 0.127, 'min_track_width': 0.127, 'min_via_diameter': 0.45, 'min_through_hole_diameter': 0.3, 'min_via_annular_width': 0.1, 'min_copper_edge_clearance': 0.3, 'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.25, 'min_silk_clearance': 0.0, 'min_text_height': 0.7, 'min_text_thickness': 0.12}}},
       'net_settings': {'classes': [
           {'name': 'Default', 'clearance': 0.15, 'track_width': 0.15, 'via_diameter': 0.5, 'via_drill': 0.3, 'microvia_diameter': 0.3, 'microvia_drill': 0.1, 'diff_pair_gap': 0.25, 'diff_pair_width': 0.2, 'diff_pair_via_gap': 0.25, 'wire_width': 6, 'bus_width': 12, 'line_style': 0, 'schematic_color': 'rgba(0, 0, 0, 0.000)', 'pcb_color': 'rgba(0, 0, 0, 0.000)', 'priority': 2147483647},
           {'name': 'power', 'clearance': 0.15, 'track_width': 0.4, 'via_diameter': 0.6, 'via_drill': 0.3, 'microvia_diameter': 0.3, 'microvia_drill': 0.1, 'diff_pair_gap': 0.25, 'diff_pair_width': 0.2, 'diff_pair_via_gap': 0.25, 'wire_width': 6, 'bus_width': 12, 'line_style': 0, 'schematic_color': 'rgba(0, 0, 0, 0.000)', 'pcb_color': 'rgba(0, 0, 0, 0.000)', 'priority': 0}],
           'meta': {'version': 4}, 'net_colors': None,
           'netclass_patterns': [{'netclass': 'power', 'pattern': p} for p in ('P3V3', 'VCART', 'VBUS', 'GND')]}}
for fn in {'neocart_progr', 'neocart_progr_routed', os.path.splitext(os.path.basename(OUT))[0]}:
    PRO['meta']['filename'] = fn + '.kicad_pro'
    json.dump(PRO, open(os.path.join(HERE, fn + '.kicad_pro'), 'w'), indent=1)
    open(os.path.join(HERE, fn + '.kicad_dru'), 'w').write('(version 1)\n')
report['placement'] = {ref: [round(mm(fp.GetPosition().x), 2), round(mm(fp.GetPosition().y), 2), int(fp.GetOrientationDegrees())] for ref, fp in placed.items()}
json.dump(report, open(os.path.join(HERE, 'out_report.json'), 'w'), indent=1)
print(f'OK {len(placed)} parts placed, {len(nets)} nets, {len(report["checks"])} checks passed -> {OUT}')
