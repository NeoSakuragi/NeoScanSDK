#!/usr/bin/env python3
"""NeoCart blank MVS test boards (PROG / CTRG2 and CHA / CTRG1).

Run with the KiCad AppImage python:  AppDir/AppRun python3.11 hardware/neocart/blank/gen_blank.py [prog|cha|all]

What it builds: the manufactured jwestfall69 diag-cart outline (locked numeric template, asserted equal to the
reference board), the diag cart's own gold-finger and test-point footprints (copied from the reference board,
so the geometry is the proven one), one net per connector pin, one trace finger -> test point per pin,
silkscreen labels on both faces (A side on front, B side on back mirrored), no components.

Every check that failed on the v4 boards is an assertion here. The script refuses to write a board that fails.
"""
import sys, os, json, math
import pcbnew
from pcbnew import VECTOR2I, FromMM

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
REF = {
    'prog': os.path.join(ROOT, 'reference/neogeo-diag-mvs-prog/hardware/neogeo-diag-mvs-prog.kicad_pcb'),
    'cha':  os.path.join(ROOT, 'reference/neogeo-diag-mvs-cha/hardware/atf1502as-plcc44-board/neogeo-diag-mvs-cha-atf1502as-plcc44.kicad_pcb'),
}
VERSION = 'v1 2026-09-24'

# ---------------------------------------------------------------------------------------------------------------
# Pinouts. Primary source: pad nets of the manufactured diag boards. Cross-checked against the diag boards' own
# silkscreen labels and the jamma-nation-x pinout. Differences are deliberate and listed in ALIASES.
# ---------------------------------------------------------------------------------------------------------------
def _seq(prefix, lo, hi, start_pin):
    return {start_pin + i: f'{prefix}{n}' for i, n in enumerate(range(lo, hi + 1))}

PROG_A = {**{p: 'GND' for p in (1, 2, 3, 4, 57, 58, 59, 60)}, **_seq('D', 0, 15, 5),
          21: 'R_W', 22: 'AS', 23: 'ROMOEU', 24: 'ROMOEL', 25: 'PORTOEU', 26: 'PORTOEL', 27: 'PORTWEU', 28: 'PORTWEL',
          **{p: 'VCC' for p in (29, 30, 31, 32)}, 33: 'PORTADRS', **{p: f'NC{p}A' for p in range(34, 42)}, 42: 'SYSTEMB',
          43: 'SDPA8', 44: 'SDPA9', 45: 'SDPA10', 46: 'SDPA11', 47: 'SDPMPX', 48: 'SDPOE',
          49: 'SDRA8', 50: 'SDRA9', 51: 'SDRA20', 52: 'SDRA21', 53: 'SDRA22', 54: 'SDRA23', 55: 'SDRMPX', 56: 'SDROE'}
PROG_B = {**{p: 'GND' for p in (1, 2, 3, 4, 57, 58, 59, 60)}, **_seq('A', 1, 19, 5), 24: '68KCLKB',
          25: 'ROMWAIT', 26: 'PWAIT0', 27: 'PWAIT1', 28: 'PDTACK', **{p: 'VCC' for p in (29, 30, 31, 32)},
          33: 'ROMOE', 34: '4MB', 35: 'RESET', **{p: f'NC{p}B' for p in range(36, 41)},
          **_seq('SDPAD', 0, 7, 41), **_seq('SDRAD', 0, 7, 49)}
CHA_A = {**{p: 'GND' for p in (1, 2, 59, 60)}, **{3 + i: f'P{2 * i}' for i in range(12)}, 15: 'PCK1B', 16: 'PCK2B',
         17: '2H1', 18: 'CA4', **{19 + i: f'CR{2 * i}' for i in range(10)}, **{p: 'VCC' for p in (29, 30, 31, 32)},
         **{33 + i: f'CR{20 + 2 * i}' for i in range(6)}, **{p: f'NC{p}A' for p in (39, 40, 41)}, 42: 'SYSTEMB',
         **_seq('SDA', 0, 15, 43)}
CHA_B = {**{p: 'GND' for p in (1, 2, 59, 60)}, **{3 + i: f'P{2 * i + 1}' for i in range(12)}, 15: '24M', 16: '12M',
         17: '8M', 18: 'RESET', **{19 + i: f'CR{2 * i + 1}' for i in range(10)}, **{p: 'VCC' for p in (29, 30, 31, 32)},
         **{33 + i: f'CR{21 + 2 * i}' for i in range(6)}, **_seq('FIX', 0, 7, 39), 47: 'SDRD0', 48: 'SDRD1',
         49: 'SDROM', 50: 'SDMRD', **_seq('SDD', 0, 7, 51)}
# our name -> name on the diag board (pad net or silkscreen), when they differ
ALIASES = {'R_W': 'R{slash}W', 'SYSTEMB': 'SLOTCS', '2H1': 'SA3', 'SDRD1': 'SRDR1', '68KCLKB': '68KCLB',
           'ROMWAIT': 'VCC', 'PWAIT0': 'VCC', 'PWAIT1': 'VCC', 'PDTACK': 'VCC',   # diag board ties these to VCC
           **{f'FIX{i}': f'FIXD{i}' for i in range(8)}}
DISPLAY = {'R_W': 'R/W'}

BOARDS = {
    'prog': dict(title='NEOCART BLANK PROG  CTRG2', fingers={'A': 'J2', 'B': 'J1'}, tps={'A': 'J4', 'B': 'J3'},
                 pins={'A': PROG_A, 'B': PROG_B}),
    'cha':  dict(title='NEOCART BLANK CHA   CTRG1', fingers={'A': 'J1', 'B': 'J4'}, tps={'A': 'J2', 'B': 'J3'},
                 pins={'A': CHA_A, 'B': CHA_B}),
}

def mm(v): return round(v / 1e6, 3)
def P(x, y): return VECTOR2I(FromMM(x), FromMM(y))

def edge_items(board):
    out = set()
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts: continue
        s, e = d.GetStart(), d.GetEnd()
        kind = {pcbnew.S_SEGMENT: 'seg', pcbnew.S_CIRCLE: 'circle', pcbnew.S_ARC: 'arc'}.get(d.GetShape(), '?')
        a, b = (mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))
        if kind == 'seg' and b < a: a, b = b, a          # direction-independent
        out.add((kind, a, b))
    return out

def build(kind):
    cfg = BOARDS[kind]
    ref = pcbnew.LoadBoard(REF[kind])
    ref_edges = edge_items(ref)
    report = {'board': kind, 'checks': [], 'pins': {}, 'aliases': {}}
    def check(name, ok, detail=''):
        report['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
        if not ok: raise SystemExit(f'CHECK FAILED [{kind}] {name}: {detail}')

    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_MinClearance = FromMM(0.2)
    ds.m_TrackMinWidth = FromMM(0.2)
    ds.m_MinSilkTextHeight = FromMM(0.7); ds.m_MinSilkTextThickness = FromMM(0.12)

    # -- outline: numeric template = the reference edge items, re-created as fresh shapes -------------------------
    for kind_, a, b in sorted(ref_edges):
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.S_SEGMENT if kind_ == 'seg' else pcbnew.S_CIRCLE)
        sh.SetStart(P(*a)); sh.SetEnd(P(*b)); sh.SetLayer(pcbnew.Edge_Cuts); sh.SetWidth(FromMM(0.1))
        board.Add(sh)
    check('outline equals manufactured reference', edge_items(board) == ref_edges,
          f'{len(ref_edges)} edge items, {len(ref_edges & edge_items(board))} identical')
    bb = board.GetBoardEdgesBoundingBox()
    check('outline size 174 x 134 mm', abs(mm(bb.GetWidth()) - 174.1) < 0.2 and abs(mm(bb.GetHeight()) - 134.1) < 0.2,
          f'{mm(bb.GetWidth())} x {mm(bb.GetHeight())} mm')
    holes = sorted((a, round(math.dist(a, b), 2)) for k, a, b in ref_edges if k == 'circle')
    check('two 10 mm shell-post holes', len(holes) == 2 and all(r == 5.0 for _, r in holes), str(holes))

    # -- nets ------------------------------------------------------------------------------------------------------
    nets = {}
    def net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name); board.Add(ni); nets[name] = ni
        return nets[name]

    # -- footprints copied from the reference board (proven pads), nets re-assigned from our table -----------------
    ref_fps = {f.GetReference(): f for f in ref.GetFootprints()}
    fps = {}
    for role, refname in list(cfg['fingers'].items()) + list(cfg['tps'].items()):
        src = ref_fps[refname]
        fp = pcbnew.FOOTPRINT(src)            # copy constructor: identical geometry
        board.Add(fp)
        fp.SetPosition(src.GetPosition()); fp.SetOrientation(src.GetOrientation())
        fps[refname] = fp
        check(f'{refname} placed at reference position', fp.GetPosition() == src.GetPosition() and fp.GetLayer() == src.GetLayer(),
              f'({mm(fp.GetPosition().x)}, {mm(fp.GetPosition().y)}) rot {fp.GetOrientationDegrees()} layer {board.GetLayerName(fp.GetLayer())}')
        fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
        try: fp.Models().clear()
        except Exception: pass

    pad_pos = {}   # (side, pin) -> (x, y) of the finger pad ; tp_pos: (side, pin) -> (x, y, layer-set)
    tp_pos = {}
    for side in 'AB':
        fpF, fpT = fps[cfg['fingers'][side]], fps[cfg['tps'][side]]
        pins = cfg['pins'][side]
        check(f'side {side} finger footprint has 60 pads', len(list(fpF.Pads())) == 60, str(len(list(fpF.Pads()))))
        for pad in fpF.Pads():
            n = int(pad.GetNumber()); pad.SetNet(net(pins[n])); pad_pos[(side, n)] = (mm(pad.GetPosition().x), mm(pad.GetPosition().y))
        for pad in fpT.Pads():
            n = int(pad.GetNumber()); pad.SetNet(net(pins[n])); tp_pos[(side, n)] = (mm(pad.GetPosition().x), mm(pad.GetPosition().y))
        # every pin 1..60 has a net; every non-power pin has a test point
        missing_tp = [n for n in range(1, 61) if pins[n] not in ('GND', 'VCC') and (side, n) not in tp_pos]
        check(f'side {side}: every signal pin has a test point', not missing_tp, f'missing {missing_tp}')
        # the reference pad nets agree with our table, up to the documented aliases
        ref_pins = {int(p.GetNumber()): str(p.GetNetname()) for p in ref_fps[cfg['fingers'][side]].Pads()}
        bad = []
        for n in range(1, 61):
            ours, theirs = pins[n], ref_pins[n]
            if ours != theirs and ALIASES.get(ours) != theirs: bad.append((n, ours, theirs))
            if ours != theirs: report['aliases'][f'{side}{n}'] = {'ours': ours, 'diag_board': theirs}
        check(f'side {side}: pinout agrees with the manufactured diag board (up to listed aliases)', not bad, str(bad))
        report['pins'][side] = {n: {'net': pins[n], 'x': pad_pos[(side, n)][0], 'tp': (side, n) in tp_pos} for n in range(1, 61)}

    # -- traces: finger pad -> its test point, dog-leg around the other side's through-hole pad when in the way -----
    all_tp = [(s, n, x, y) for (s, n), (x, y) in tp_pos.items()]
    W = FromMM(0.25)
    def track(layer, netname, pts):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board); t.SetStart(P(x1, y1)); t.SetEnd(P(x2, y2)); t.SetWidth(W)
            t.SetLayer(layer); t.SetNet(net(netname)); board.Add(t)
    n_tracks = 0
    for side in 'AB':
        layer = pcbnew.F_Cu if fps[cfg['fingers'][side]].GetLayer() == pcbnew.F_Cu else pcbnew.B_Cu
        for n in range(1, 61):
            if (side, n) not in tp_pos: continue
            (fx, fy), (tx, ty) = pad_pos[(side, n)], tp_pos[(side, n)]
            # obstacles: any other test-point pad within 1.0 mm in x between the finger and the target
            obst = [(y) for (s, m, x, y) in all_tp if (s, m) != (side, n) and abs(x - fx) < 1.0 and ty < y < fy]
            if not obst:
                pts = [(fx, fy), (tx, ty)]
            else:
                oy = max(obst)                       # nearest to the finger (largest y); assert only one
                check(f'{side}{n}: at most one obstacle on the way to its test point', len(obst) == 1, str(obst))
                dx = -1.29
                pts = [(fx, fy), (fx, oy + 2.8), (fx + dx, oy + 1.51), (fx + dx, ty + 1.29), (tx, ty)]
                # the dog-leg column must itself be clear of pads
                clash = [(s, m) for (s, m, x, y) in all_tp if abs(x - (fx + dx)) < 0.98 and ty - 0.5 < y < fy]
                check(f'{side}{n}: dog-leg column clear', not clash, str(clash))
            track(layer, cfg['pins'][side][n], pts); n_tracks += len(pts) - 1
    report['tracks'] = n_tracks

    # -- power stitching: GND pours on both copper layers, VCC rail per layer, through-hole test points join sides ----
    fy_top = min(y for (_, y) in pad_pos.values()) - 5.0                 # top edge of the gold fingers
    zone_bottom = fy_top - 1.35                                          # pour stops 1.35 mm above the fingers
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board); z.SetLayer(layer); z.SetNet(net('GND'))
        z.SetLocalClearance(FromMM(0.3)); z.SetMinThickness(FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(FromMM(0.4)); z.SetThermalReliefSpokeWidth(FromMM(0.4))
        x0, y0, x1 = mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetX()) + mm(bb.GetWidth())
        pts = [P(x0, y0), P(x1, y0), P(x1, zone_bottom), P(x0, zone_bottom)]
        z.AddPolygon(pcbnew.VECTOR_VECTOR2I(pts)); board.Add(z)
    for side in 'AB':
        layer = pcbnew.F_Cu if fps[cfg['fingers'][side]].GetLayer() == pcbnew.F_Cu else pcbnew.B_Cu
        pins = cfg['pins'][side]
        gnd = [n for n in range(1, 61) if pins[n] == 'GND']; vcc = [n for n in range(1, 61) if pins[n] == 'VCC']
        for n in gnd + vcc:
            x, y = pad_pos[(side, n)]
            track(layer, pins[n], [(x, y), (x, zone_bottom - 0.6 if pins[n] == 'GND' else fy_top - 0.9)])   # stub up into the pour / to the rail
        xs = [pad_pos[(side, n)][0] for n in vcc]
        track(layer, 'VCC', [(min(xs), fy_top - 0.9), (max(xs), fy_top - 0.9)])                              # VCC rail
    for n in range(1, 61):                                               # join A and B side power test points (through-hole)
        if (('A', n) in tp_pos and ('B', n) in tp_pos and cfg['pins']['A'][n] in ('GND', 'VCC') and cfg['pins']['A'][n] == cfg['pins']['B'][n]):
            (ax, ay), (bx, by) = tp_pos[('A', n)], tp_pos[('B', n)]
            track(pcbnew.F_Cu, cfg['pins']['A'][n], [(ax, ay), (bx, by)])
    # zones are filled by `kicad-cli pcb drc --refill-zones --save-board` (ZONE_FILLER segfaults in standalone python)

    # -- silkscreen. Rows are physical, so the naming follows the rows on BOTH faces: the upper test-point row is
    #    the B side (labels above it), the lower row is the A side (labels below it, in the band above the fingers).
    #    Power pins carry one label (same name on both sides). B labels that would run into a shell-post hole join
    #    the band, side by side with the A label of that column. Back-face copies are mirrored.
    label_bboxes = {'A': [], 'B': []}
    def text(s, x, y, layer, size=0.8, angle=90, mirror=False, halign=pcbnew.GR_TEXT_H_ALIGN_LEFT, thick=0.15, width=None):
        if mirror and angle == 90 and halign == pcbnew.GR_TEXT_H_ALIGN_LEFT:
            halign = pcbnew.GR_TEXT_H_ALIGN_RIGHT   # mirrored 90-degree text grows the other way (probed)
        t = pcbnew.PCB_TEXT(board); t.SetText(s); t.SetPosition(P(x, y)); t.SetLayer(layer)
        t.SetTextSize(VECTOR2I(FromMM(width or size), FromMM(size))); t.SetTextThickness(FromMM(thick))
        t.SetTextAngleDegrees(angle); t.SetMirrored(mirror); t.SetHorizJustify(halign)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER); board.Add(t); return t
    def vlabel(s, x, y, layer, mirror, down, size, width, thick):
        """vertical label anchored at (x, y) running UP (towards smaller y) or DOWN; direction probed per justification."""
        if down: hal = pcbnew.GR_TEXT_H_ALIGN_LEFT if mirror else pcbnew.GR_TEXT_H_ALIGN_RIGHT
        else:    hal = pcbnew.GR_TEXT_H_ALIGN_RIGHT if mirror else pcbnew.GR_TEXT_H_ALIGN_LEFT
        t = pcbnew.PCB_TEXT(board); t.SetText(s); t.SetPosition(P(x, y)); t.SetLayer(layer)
        t.SetTextSize(VECTOR2I(FromMM(width), FromMM(size))); t.SetTextThickness(FromMM(thick))
        t.SetTextAngleDegrees(90); t.SetMirrored(mirror); t.SetHorizJustify(hal); t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        board.Add(t); return t
    tp_row_top = min(y for (_, _, _, y) in all_tp)                         # B signal row
    a_sig_row = max(y for (s_, n, x, y) in all_tp if s_ == 'A' and cfg['pins']['A'][n] not in ('GND', 'VCC'))
    fy_top = min(y for (_, y) in pad_pos.values()) - 5.0                     # top edge of the gold fingers
    above_y = tp_row_top - 1.35                                               # B labels start here, run upward
    band_y = a_sig_row + 0.85 + 0.25                                          # A labels start here, run downward
    hole_c = [(a, 5.0) for k, a, b in ref_edges if k == 'circle']
    def hits_hole(tb):
        for (hx, hy), r in hole_c:
            x0, y0, x1, y1 = mm(tb.GetX()), mm(tb.GetY()), mm(tb.GetX() + tb.GetWidth()), mm(tb.GetY() + tb.GetHeight())
            cx, cy = min(max(hx, x0), x1), min(max(hy, y0), y1)
            if math.dist((cx, cy), (hx, hy)) < r + 0.3: return True
        return False
    for layer, mirror in ((pcbnew.F_SilkS, False), (pcbnew.B_SilkS, True)):
        key = 'A' if not mirror else 'B'       # bookkeeping per face
        for n in range(1, 61):
            col = []                            # labels that end up in the band for this column
            nameB = cfg['pins']['B'][n]; nameA = cfg['pins']['A'][n]
            if ('B', n) in tp_pos:
                disp = DISPLAY.get(nameB, nameB); x = tp_pos[('B', n)][0]
                t = vlabel(disp, x, above_y, layer, mirror, down=False, size=0.8, width=0.8, thick=0.15)
                if hits_hole(t.GetBoundingBox()):
                    # under a shell-post hole: same place, condensed face (0.7 tall x 0.55 wide) so it ends before the hole
                    board.Remove(t)
                    t = vlabel(disp, x, above_y, layer, mirror, down=False, size=0.7, width=0.55, thick=0.12)
                    if not mirror: report.setdefault('labels_condensed', []).append(f'B{n} {disp}')
                    check(f'condensed label B{n} "{disp}" clears the shell-post hole', not hits_hole(t.GetBoundingBox()))
                label_bboxes[key].append((f'B{n}', disp, t.GetBoundingBox()))
            if ('A', n) in tp_pos and nameA not in ('GND', 'VCC'):
                col.append(DISPLAY.get(nameA, nameA))
            elif ('A', n) in tp_pos and ('B', n) not in tp_pos:
                col.append(DISPLAY.get(nameA, nameA))         # power test point that exists on the A row only
            x = tp_pos[('A', n)][0] if ('A', n) in tp_pos else (tp_pos[('B', n)][0] if ('B', n) in tp_pos else None)
            if not col: continue
            two = len(col) == 2
            for i, disp in enumerate(col):
                width = 0.55 if two else (0.52 if len(disp) >= 8 else 0.6)
                dx = (-0.64 if i == 0 else 0.64) if two else 0.0
                t = vlabel(disp, x + dx, band_y, layer, mirror, down=True, size=0.7, width=width, thick=0.12)
                label_bboxes[key].append((f'A{n}' if not (two and i == 0) else f'B{n}', disp, t.GetBoundingBox()))
        # a few reference pin numbers in free columns (no test point there)
        for n in [m for m in range(1, 61) if ('A', m) not in tp_pos and ('B', m) not in tp_pos]:   # columns with no test point
            side = 'B' if mirror else 'A'
            vlabel(f'{side}{n}', pad_pos[(side, n)][0], fy_top - 0.4, layer, mirror, down=False, size=0.8, width=0.8, thick=0.15)
    # titles + legend
    cx = mm(bb.GetX()) + mm(bb.GetWidth()) / 2; top = mm(bb.GetY())
    text(f'{cfg["title"]}   {VERSION}', cx, top + 6, pcbnew.F_SilkS, size=2.0, angle=0, halign=pcbnew.GR_TEXT_H_ALIGN_CENTER, thick=0.3)
    text('A SIDE (component side)', cx, top + 9.5, pcbnew.F_SilkS, size=1.2, angle=0, halign=pcbnew.GR_TEXT_H_ALIGN_CENTER, thick=0.2)
    text(f'{cfg["title"]}   {VERSION}   B SIDE', cx, top + 6, pcbnew.B_SilkS, size=2.0, angle=0, mirror=True, halign=pcbnew.GR_TEXT_H_ALIGN_CENTER, thick=0.3)
    text('neogeo-diag-mvs outline (jwestfall69)  --  no components  --  every CTRG pin on a 1.0 mm test point', cx, top + 12.5, pcbnew.F_SilkS, size=1.0, angle=0, halign=pcbnew.GR_TEXT_H_ALIGN_CENTER, thick=0.15)
    legend = 'TEST POINTS:  upper row = B side, named above   |   lower row = A side, named below   |   same on both faces'
    for layer, mirror in ((pcbnew.F_SilkS, False), (pcbnew.B_SilkS, True)):
        text(legend, cx, tp_row_top - 19.5, layer, size=1.0, angle=0, mirror=mirror, halign=pcbnew.GR_TEXT_H_ALIGN_CENTER, thick=0.15)

    # -- geometric checks on labels: no label touches a pad, no label touches another label -------------------------
    pads_bb = [p.GetBoundingBox() for f in board.GetFootprints() for p in f.Pads()]
    def overlaps(a, b): return a.Intersects(b)
    for sideK, items in label_bboxes.items():
        for n, disp, tb in items:
            hit = [mm(pb.GetX()) for pb in pads_bb if overlaps(tb, pb)]
            check(f'label {sideK}{n} "{disp}" clear of pads', not hit, str(hit[:3]))
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                check(f'labels {items[i][1]} / {items[j][1]} do not overlap', not overlaps(items[i][2], items[j][2]))
    check('every label sits inside the board outline', all(bb.Contains(tb) for items in label_bboxes.values() for _, _, tb in items))
    check('B-side labels are mirrored, A-side are not', all(t.IsMirrored() == (t.GetLayer() == pcbnew.B_SilkS) for t in board.GetDrawings() if isinstance(t, pcbnew.PCB_TEXT)))

    # -- every signal pad has copper on it (the authoritative unconnected check is DRC after zone refill) -----------
    touching = set()
    for t in board.GetTracks():
        touching.add((mm(t.GetStart().x), mm(t.GetStart().y))); touching.add((mm(t.GetEnd().x), mm(t.GetEnd().y)))
    untouched = [(s_, n) for (s_, n), xy in list(pad_pos.items()) + list(tp_pos.items()) if xy not in touching]
    check('every finger pad and test point has a track on it', not untouched, str(untouched[:6]))
    check('zones present on both copper layers', len(board.Zones()) == 2 and all(z.Outline().OutlineCount() == 1 for z in board.Zones()))

    libdir = os.path.join(HERE, 'neocart_blank.pretty'); os.makedirs(libdir, exist_ok=True)
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    for fp in board.GetFootprints():
        name = fp.GetFPID().GetLibItemName().wx_str() if hasattr(fp.GetFPID().GetLibItemName(), 'wx_str') else str(fp.GetFPID().GetLibItemName())
        fp.SetFPID(pcbnew.LIB_ID('neocart_blank', name))
        io.FootprintSave(libdir, fp)
    open(os.path.join(HERE, 'fp-lib-table'), 'w').write('(fp_lib_table\n  (version 7)\n  (lib (name "neocart_blank")(type "KiCad")(uri "${KIPRJMOD}/neocart_blank.pretty")(options "")(descr "proven MVS edge + test-point footprints, copied from jwestfall69 neogeo-diag"))\n)\n')
    pro = os.path.join(HERE, f'neocart_blank_{kind}.kicad_pro')
    if not os.path.exists(pro):
        json.dump({'meta': {'filename': os.path.basename(pro), 'version': 1}, 'board': {'design_settings': {}}}, open(pro, 'w'), indent=1)
    out = os.path.join(HERE, f'neocart_blank_{kind}.kicad_pcb')
    board.Save(out)
    report['file'] = out; report['nets'] = len(nets)
    json.dump(report, open(os.path.join(HERE, 'out', f'report_{kind}.json'), 'w'), indent=1)
    print(f'[{kind}] OK  {len(report["checks"])} checks passed, {n_tracks} track segments, {len(nets)} nets -> {out}')
    return report

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    for k in (['prog', 'cha'] if which == 'all' else [which]):
        build(k)
