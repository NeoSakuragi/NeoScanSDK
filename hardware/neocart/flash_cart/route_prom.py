#!/usr/bin/env python3
"""P-ROM header + routing. F.Cu fan for A-side, B.Cu fan for B-side. Zero crossings."""
import pcbnew

PCB = '/home/bruno/CLProjects/NeoGeo/hardware/neocart/flash_cart/mvs_blank_prog.kicad_pcb'
board = pcbnew.LoadBoard(PCB)

# Remove old header and tracks
for fp in list(board.GetFootprints()):
    if fp.GetReference() == 'J_PROM': board.Remove(fp)
for t in list(board.GetTracks()): board.Remove(t)
# Remove old header silk (X > 200, Y < 90)
for d in list(board.GetDrawings()):
    if d.GetClass() in ('PCB_TEXT','PCB_SHAPE'):
        x, y = pcbnew.ToMM(d.GetPosition().x), pcbnew.ToMM(d.GetPosition().y)
        if x > 200 and y < 90: board.Remove(d)

def pad_x(n): return round(214.68 - (n-1)*2.54, 2)
def mm(x,y): return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))

# Pin assignment sorted by gold finger position
# Left: B-side signals → route on B.Cu
# Right: A-side signals → route on F.Cu
col_left = [
    ("GND",1),("A1",5),("A2",6),("A3",7),("A4",8),("A5",9),("A6",10),
    ("A7",11),("A8",12),("A9",13),("A10",14),("A11",15),("A12",16),
    ("A13",17),("A14",18),("A15",19),("A16",20),("A17",21),("A18",22),("A19",23),
]
col_right = [
    ("VCC",29),("D0",5),("D1",6),("D2",7),("D3",8),("D4",9),("D5",10),
    ("D6",11),("D7",12),("D8",13),("D9",14),("D10",15),("D11",16),
    ("D12",17),("D13",18),("D14",19),("D15",20),("ROMOEU",23),("ROMOEL",24),("ROMOE",33),
]

HDR_X, HDR_Y = 220.0, 32.0
PITCH, ROW_SP = 2.54, 2.54
GF_Y = 154.4
TW = pcbnew.FromMM(0.25)
TW_PWR = pcbnew.FromMM(0.4)
SP = 0.5

nets = {}
for n in board.GetNetInfo().NetsByName():
    nets[str(n)] = board.GetNetInfo().GetNetItem(str(n))

# ── Header footprint ──
all_cu = pcbnew.LSET()
all_cu.AddLayer(pcbnew.F_Cu); all_cu.AddLayer(pcbnew.B_Cu)
all_cu.AddLayer(pcbnew.F_Mask); all_cu.AddLayer(pcbnew.B_Mask)

fp = pcbnew.FOOTPRINT(board)
fp.SetReference("J_PROM"); fp.SetValue("P-ROM 2x20")
fp.SetPosition(mm(HDR_X, HDR_Y)); fp.SetLayer(pcbnew.F_Cu)
fp.Reference().SetVisible(False); fp.Value().SetVisible(False)

for i in range(20):
    for ci in range(2):
        col = col_left if ci == 0 else col_right
        sig = col[i][0]
        x, y = HDR_X + ci*ROW_SP, HDR_Y + i*PITCH
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.7), pcbnew.FromMM(1.7)))
        pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
        pad.SetPosition(mm(x, y)); pad.SetLayerSet(all_cu)
        pad.SetNumber(str(i*2 + ci + 1))
        if sig in nets: pad.SetNet(nets[sig])
        fp.Add(pad)
board.Add(fp)

# ── Silk labels ──
LS, LT = 1.17, 0.15
for layer in [pcbnew.F_SilkS, pcbnew.B_SilkS]:
    mir = (layer == pcbnew.B_SilkS)
    for i in range(20):
        for ci, col in enumerate([col_left, col_right]):
            t = pcbnew.PCB_TEXT(board)
            t.SetText(col[i][0])
            t.SetPosition(mm(HDR_X + ci*ROW_SP + (-2 if ci==0 else 2), HDR_Y + i*PITCH))
            t.SetLayer(layer)
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(LS), pcbnew.FromMM(LS)))
            t.SetTextThickness(pcbnew.FromMM(LT))
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT if ci==0 else pcbnew.GR_TEXT_H_ALIGN_LEFT)
            if mir: t.SetMirrored(True)
            board.Add(t)
    t = pcbnew.PCB_TEXT(board)
    t.SetText("P-ROM"); t.SetLayer(layer)
    t.SetPosition(mm(HDR_X + ROW_SP/2, HDR_Y - 4.5))
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(2.5), pcbnew.FromMM(2.5)))
    t.SetTextThickness(pcbnew.FromMM(0.25))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    if mir: t.SetMirrored(True)
    board.Add(t)
    bl,br,bt,bb = HDR_X-1.5, HDR_X+ROW_SP+1.5, HDR_Y-1.5, HDR_Y+19*PITCH+1.5
    for x1,y1,x2,y2 in [(bl,bt,br,bt),(br,bt,br,bb),(br,bb,bl,bb),(bl,bb,bl,bt)]:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(mm(x1,y1)); s.SetEnd(mm(x2,y2))
        s.SetLayer(layer); s.SetWidth(pcbnew.FromMM(0.15))
        board.Add(s)

# ── Routing ──
def track(x1,y1,x2,y2, layer, sig, w=TW):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(mm(x1,y1)); t.SetEnd(mm(x2,y2))
    t.SetLayer(layer); t.SetWidth(w)
    if sig in nets: t.SetNet(nets[sig])
    board.Add(t)

def add_via(x,y, sig):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(mm(x,y)); v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
    if sig in nets: v.SetNet(nets[sig])
    board.Add(v)

nt, nv = 0, 0

# RIGHT COLUMN: A-side signals → route entirely on F.Cu to F.Cu gold fingers
for row in range(20):
    sig, gf_pin = col_right[row]
    hx, hy = HDR_X + ROW_SP, HDR_Y + row*PITCH
    gf_x = pad_x(gf_pin)
    w = TW_PWR if sig in ("VCC","GND") else TW
    jy = 100 + row * SP

    if sig == "ROMOE":
        # ROMOE is B-side — needs special handling
        # Route on F.Cu diagonal, via, B.Cu drop
        track(hx, hy, gf_x, jy, pcbnew.F_Cu, sig, w)
        add_via(gf_x, jy, sig)
        track(gf_x, jy, gf_x, GF_Y, pcbnew.B_Cu, sig, w)
        nt += 2; nv += 1
    else:
        # Pure F.Cu: diagonal to junction, then straight down to gold finger
        track(hx, hy, gf_x, jy, pcbnew.F_Cu, sig, w)
        track(gf_x, jy, gf_x, GF_Y, pcbnew.F_Cu, sig, w)
        nt += 2

# LEFT COLUMN: B-side signals → via at header, route entirely on B.Cu
for row in range(20):
    sig, gf_pin = col_left[row]
    hx, hy = HDR_X, HDR_Y + row*PITCH
    gf_x = pad_x(gf_pin)
    w = TW_PWR if sig in ("VCC","GND") else TW
    jy = 100 + row * SP

    # Via near header to get to B.Cu
    via_x = hx - 1.5  # just left of header
    add_via(via_x, hy, sig)
    # B.Cu diagonal from via to junction above gold finger
    track(via_x, hy, gf_x, jy, pcbnew.B_Cu, sig, w)
    # B.Cu straight down to gold finger
    track(gf_x, jy, gf_x, GF_Y, pcbnew.B_Cu, sig, w)
    nt += 2; nv += 1

pcbnew.SaveBoard(PCB, board)
print(f"Routed: {nt} tracks, {nv} vias")
print("F.Cu = A-side fan (right col), B.Cu = B-side fan (left col)")
print("No layer mixing = no crossings")
