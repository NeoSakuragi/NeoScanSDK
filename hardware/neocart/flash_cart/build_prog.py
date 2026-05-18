#!/usr/bin/env python3
"""Build complete PROG board from scratch: outline, gold fingers, P-ROM header, routing."""
import pcbnew

def pad_x(n): return round(214.68 - (n-1)*2.54, 2)
def mm(x,y): return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))

PCB = '/home/bruno/CLProjects/NeoScanSDK/hardware/neocart/flash_cart/mvs_blank_prog.kicad_pcb'
board = pcbnew.BOARD()

# ══════ Board outline ══════
outline = [
    (52.75,23.75),(88.75,23.75),(88.75,26.25),(100.75,26.25),(100.75,23.75),
    (178.75,23.75),(178.75,26.25),(190.75,26.25),(190.75,23.75),(226.75,23.75),
    (226.75,138.75),(217.05,138.75),(217.05,157.75),(62.45,157.75),
    (62.45,138.75),(52.75,138.75),
]
for i in range(len(outline)):
    p1, p2 = outline[i], outline[(i+1)%len(outline)]
    s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(mm(p1[0],p1[1])); s.SetEnd(mm(p2[0],p2[1]))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(pcbnew.FromMM(0.1)); board.Add(s)
for cx,cy in [(94.75,127),(184.75,127)]:
    c = pcbnew.PCB_SHAPE(board); c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetCenter(mm(cx,cy)); c.SetEnd(mm(cx+5,cy))
    c.SetLayer(pcbnew.Edge_Cuts); c.SetWidth(pcbnew.FromMM(0.1)); board.Add(c)

# ══════ Pinouts ══════
A_SIDE = {1:"GND",2:"GND",3:"GND",4:"GND",5:"D0",6:"D1",7:"D2",8:"D3",9:"D4",10:"D5",11:"D6",12:"D7",13:"D8",14:"D9",15:"D10",16:"D11",17:"D12",18:"D13",19:"D14",20:"D15",21:"R/W",22:"AS",23:"ROMOEU",24:"ROMOEL",25:"PORTOEU",26:"PORTOEL",27:"PORTWEU",28:"PORTWEL",29:"VCC",30:"VCC",31:"VCC",32:"VCC",33:"PORTADRS",34:"NC",35:"NC",36:"NC",37:"NC",38:"NC",39:"NC",40:"NC",41:"NC",42:"SLOTCS",43:"SDPA8",44:"SDPA9",45:"SDPA10",46:"SDPA11",47:"SDPMPX",48:"SDPOE",49:"SDRA8",50:"SDRA9",51:"SDRA20",52:"SDRA21",53:"SDRA22",54:"SDRA23",55:"SDRMPX",56:"SDROE",57:"GND",58:"GND",59:"GND",60:"GND"}
B_SIDE = {1:"GND",2:"GND",3:"GND",4:"GND",5:"A1",6:"A2",7:"A3",8:"A4",9:"A5",10:"A6",11:"A7",12:"A8",13:"A9",14:"A10",15:"A11",16:"A12",17:"A13",18:"A14",19:"A15",20:"A16",21:"A17",22:"A18",23:"A19",24:"68KCLKB",25:"ROMWAIT",26:"PWAIT0",27:"PWAIT1",28:"PDTACK",29:"VCC",30:"VCC",31:"VCC",32:"VCC",33:"ROMOE",34:"4MB",35:"RESET",36:"NC",37:"NC",38:"NC",39:"NC",40:"NC",41:"SDPAD0",42:"SDPAD1",43:"SDPAD2",44:"SDPAD3",45:"SDPAD4",46:"SDPAD5",47:"SDPAD6",48:"SDPAD7",49:"SDRAD0",50:"SDRAD1",51:"SDRAD2",52:"SDRAD3",53:"SDRAD4",54:"SDRAD5",55:"SDRAD6",56:"SDRAD7",57:"GND",58:"GND",59:"GND",60:"GND"}

# P-ROM header pin assignment (sorted by gold finger position)
col_L = [("GND",1,"B"),("A1",5,"B"),("A2",6,"B"),("A3",7,"B"),("A4",8,"B"),("A5",9,"B"),("A6",10,"B"),("A7",11,"B"),("A8",12,"B"),("A9",13,"B"),("A10",14,"B"),("A11",15,"B"),("A12",16,"B"),("A13",17,"B"),("A14",18,"B"),("A15",19,"B"),("A16",20,"B"),("A17",21,"B"),("A18",22,"B"),("A19",23,"B")]
col_R = [("VCC",29,"A"),("D0",5,"A"),("D1",6,"A"),("D2",7,"A"),("D3",8,"A"),("D4",9,"A"),("D5",10,"A"),("D6",11,"A"),("D7",12,"A"),("D8",13,"A"),("D9",14,"A"),("D10",15,"A"),("D11",16,"A"),("D12",17,"A"),("D13",18,"A"),("D14",19,"A"),("D15",20,"A"),("ROMOEU",23,"A"),("ROMOEL",24,"A"),("ROMOE",33,"B")]

# Collect all net names used by P-ROM
prom_nets = set()
for sig,_,_ in col_L + col_R: prom_nets.add(sig)

# Create nets
all_net_names = set()
for s in A_SIDE.values(): all_net_names.add(s)
for s in B_SIDE.values(): all_net_names.add(s)
all_net_names.discard("NC")

for name in all_net_names:
    board.Add(pcbnew.NETINFO_ITEM(board, name))
nets = {}
for n in board.GetNetInfo().NetsByName():
    nets[str(n)] = board.GetNetInfo().GetNetItem(str(n))

# ══════ Layer sets ══════
fcu_mask = pcbnew.LSET(); fcu_mask.AddLayer(pcbnew.F_Cu); fcu_mask.AddLayer(pcbnew.F_Mask)
bcu_mask = pcbnew.LSET(); bcu_mask.AddLayer(pcbnew.B_Cu); bcu_mask.AddLayer(pcbnew.B_Mask)
all_cu = pcbnew.LSET()
all_cu.AddLayer(pcbnew.F_Cu); all_cu.AddLayer(pcbnew.B_Cu)
all_cu.AddLayer(pcbnew.F_Mask); all_cu.AddLayer(pcbnew.B_Mask)

GF_Y = 154.4

# ══════ Gold finger pads with nets ══════
for n in range(1, 61):
    for side, pinout, lset, layer in [("A", A_SIDE, fcu_mask, pcbnew.F_Cu), ("B", B_SIDE, bcu_mask, pcbnew.B_Cu)]:
        sig = pinout[n]
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(f"{side}{n}"); fp.SetValue(sig)
        fp.SetPosition(mm(pad_x(n), GF_Y)); fp.SetLayer(layer)
        fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.5), pcbnew.FromMM(10)))
        pad.SetPosition(mm(pad_x(n), GF_Y)); pad.SetLayerSet(lset); pad.SetNumber("1")
        if sig != "NC" and sig in nets: pad.SetNet(nets[sig])
        fp.Add(pad); board.Add(fp)

# ══════ Gold finger silk labels ══════
LS, LT = 1.17, 0.15
for n in range(1, 61):
    for side, pinout, layer, mir in [("A", A_SIDE, pcbnew.F_SilkS, False), ("B", B_SIDE, pcbnew.B_SilkS, True)]:
        t = pcbnew.PCB_TEXT(board); t.SetText(pinout[n])
        t.SetPosition(mm(pad_x(n), 144.5)); t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(LS), pcbnew.FromMM(LS)))
        t.SetTextThickness(pcbnew.FromMM(LT))
        t.SetTextAngle(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
        if mir: t.SetMirrored(True)
        board.Add(t)

# ══════ Title texts ══════
for text, x, y, sz, layer, mir in [
    ("NEOCART BLANK PROG",139.75,55,3.0,pcbnew.F_SilkS,False),
    ("NeoScanSDK — MVS CTRG2",139.75,62,1.5,pcbnew.F_SilkS,False),
    ("A-SIDE",139.75,75,1.5,pcbnew.F_SilkS,False),
    ("B-SIDE",139.75,75,1.5,pcbnew.B_SilkS,True),
    ("CTRG2 (PROG)",139.75,136,1.8,pcbnew.F_SilkS,False),
]:
    t = pcbnew.PCB_TEXT(board); t.SetText(text); t.SetLayer(layer)
    t.SetPosition(mm(x,y))
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(sz), pcbnew.FromMM(sz)))
    t.SetTextThickness(pcbnew.FromMM(sz*0.1))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    if mir: t.SetMirrored(True)
    board.Add(t)

# ══════ P-ROM header ══════
HDR_X, HDR_Y = 220.0, 32.0
PITCH, ROW_SP = 2.54, 2.54

fp = pcbnew.FOOTPRINT(board)
fp.SetReference("J_PROM"); fp.SetValue("P-ROM 2x20")
fp.SetPosition(mm(HDR_X, HDR_Y)); fp.SetLayer(pcbnew.F_Cu)
fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
for i in range(20):
    for ci, col in enumerate([col_L, col_R]):
        sig = col[i][0]
        x, y = HDR_X + ci*ROW_SP, HDR_Y + i*PITCH
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_OVAL); pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.7), pcbnew.FromMM(1.7)))
        pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
        pad.SetPosition(mm(x, y)); pad.SetLayerSet(all_cu)
        pad.SetNumber(str(i*2+ci+1))
        if sig in nets: pad.SetNet(nets[sig])
        fp.Add(pad)
board.Add(fp)

# Header silk
for layer, mir in [(pcbnew.F_SilkS, False), (pcbnew.B_SilkS, True)]:
    for i in range(20):
        for ci, col in enumerate([col_L, col_R]):
            t = pcbnew.PCB_TEXT(board); t.SetText(col[i][0])
            t.SetPosition(mm(HDR_X + ci*ROW_SP + (-2 if ci==0 else 2), HDR_Y + i*PITCH))
            t.SetLayer(layer)
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(LS), pcbnew.FromMM(LS)))
            t.SetTextThickness(pcbnew.FromMM(LT))
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT if ci==0 else pcbnew.GR_TEXT_H_ALIGN_LEFT)
            if mir: t.SetMirrored(True)
            board.Add(t)
    t = pcbnew.PCB_TEXT(board); t.SetText("P-ROM"); t.SetLayer(layer)
    t.SetPosition(mm(HDR_X+ROW_SP/2, HDR_Y-4.5))
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(2.5), pcbnew.FromMM(2.5)))
    t.SetTextThickness(pcbnew.FromMM(0.25))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    if mir: t.SetMirrored(True)
    board.Add(t)
    bl,br,bt,bb = HDR_X-1.5, HDR_X+ROW_SP+1.5, HDR_Y-1.5, HDR_Y+19*PITCH+1.5
    for x1,y1,x2,y2 in [(bl,bt,br,bt),(br,bt,br,bb),(br,bb,bl,bb),(bl,bb,bl,bt)]:
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(mm(x1,y1)); s.SetEnd(mm(x2,y2))
        s.SetLayer(layer); s.SetWidth(pcbnew.FromMM(0.15)); board.Add(s)

# ══════ Routing ══════
TW = pcbnew.FromMM(0.25)
TW_PWR = pcbnew.FromMM(0.4)
SP = 0.5

def track(x1,y1,x2,y2, layer, sig, w=TW):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(mm(x1,y1)); t.SetEnd(mm(x2,y2)); t.SetLayer(layer); t.SetWidth(w)
    if sig in nets: t.SetNet(nets[sig]); board.Add(t)

def add_via(x,y,sig):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(mm(x,y)); v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
    if sig in nets: v.SetNet(nets[sig]); board.Add(v)

nt, nv = 0, 0

# Right column → A-side gold fingers on F.Cu (except ROMOE which is B-side)
for row in range(20):
    sig, gf_pin, side = col_R[row]
    hx, hy = HDR_X + ROW_SP, HDR_Y + row*PITCH
    gf_x = pad_x(gf_pin)
    w = TW_PWR if sig in ("VCC","GND") else TW
    jy = 100 + row * SP

    if side == "A":
        track(hx, hy, gf_x, jy, pcbnew.F_Cu, sig, w)
        track(gf_x, jy, gf_x, GF_Y, pcbnew.F_Cu, sig, w)
        nt += 2
    else:  # B-side (ROMOE)
        track(hx, hy, gf_x, jy, pcbnew.F_Cu, sig, w)
        add_via(gf_x, jy, sig)
        track(gf_x, jy, gf_x, GF_Y, pcbnew.B_Cu, sig, w)
        nt += 2; nv += 1

# Left column → B-side gold fingers on B.Cu
for row in range(20):
    sig, gf_pin, side = col_L[row]
    hx, hy = HDR_X, HDR_Y + row*PITCH
    gf_x = pad_x(gf_pin)
    w = TW_PWR if sig in ("VCC","GND") else TW
    jy = 100 + row * SP

    via_x = hx - 1.5
    add_via(via_x, hy, sig)
    track(via_x, hy, gf_x, jy, pcbnew.B_Cu, sig, w)
    track(gf_x, jy, gf_x, GF_Y, pcbnew.B_Cu, sig, w)
    nt += 2; nv += 1

pcbnew.SaveBoard(PCB, board)
print(f"Complete rebuild: 121 footprints, {nt} tracks, {nv} vias")
