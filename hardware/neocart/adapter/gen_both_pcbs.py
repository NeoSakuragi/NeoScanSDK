#!/usr/bin/env python3
"""
Generate BOTH MVS adapter PCBs — v4 (full MVS pinout, sound ROM support)

PROG adapter (CTRG2):
- J1 = FPGA U2 socket (2x32, PROG+sound signals)
- J3 = FPGA U1 socket (2x32, CHA signals passthrough)
- J2 = inter-board connector to CHA (male 2x40)
- J4 = microSD card slot (SPI mode)
- U1-U2: 74LVC245 level shifters for P-ROM data (PD0-15)
- U3:    74LVC245 level shifter for sound data (SDPAD0-7)
- U4-U6: 74HC165 shift registers for 68k address + control
- U7-U10: 74HC165 shift registers for sound ROM address
- CTRG2: gold fingers (60x2)

CHA adapter (CTRG1):
- J2 = inter-board connector from PROG (female 2x40)
- U1-U3: 74HC165 shift registers (C-ROM address P0-P23)
- U4-U5: 74HC165 shift registers (S-ROM address SDA0-SDA15)
- CTRG1: gold fingers (60x2)
"""
import pcbnew
import os

MM = pcbnew.FromMM
FP_LIB = '/usr/share/kicad/footprints'
OUT_DIR = '/home/bruno/CLProjects/NeoScanSDK/hardware/neocart/adapter'

def load_fp(lib_name, fp_name):
    return pcbnew.FootprintLoad(os.path.join(FP_LIB, f'{lib_name}.pretty'), fp_name)

def make_board_outline(board, pts):
    for i in range(len(pts)-1):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(MM(pts[i][0]), MM(pts[i][1])))
        seg.SetEnd(pcbnew.VECTOR2I(MM(pts[i+1][0]), MM(pts[i+1][1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(MM(0.1))
        board.Add(seg)

def make_board_circle(board, cx, cy, r):
    circle = pcbnew.PCB_SHAPE(board)
    circle.SetShape(pcbnew.SHAPE_T_CIRCLE)
    circle.SetCenter(pcbnew.VECTOR2I(MM(cx), MM(cy)))
    circle.SetEnd(pcbnew.VECTOR2I(MM(cx + r), MM(cy)))
    circle.SetLayer(pcbnew.Edge_Cuts)
    circle.SetWidth(MM(0.1))
    board.Add(circle)

def make_board(outline_pts, circles=None):
    board = pcbnew.BOARD()
    make_board_outline(board, outline_pts)
    if circles:
        for cx, cy, r in circles:
            make_board_circle(board, cx, cy, r)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = MM(0.2)
    ds.m_ViasMinSize = MM(0.6)
    ds.m_ViasMinDrill = MM(0.3)
    return board

def add_nets(board, names):
    nets = {}
    for i, name in enumerate(names, 1):
        net = pcbnew.NETINFO_ITEM(board, name, i)
        board.Add(net)
        nets[name] = net
    return nets

def place(board, fp, ref, value, x, y, angle=0, text_size=None, ref_offset=None, ref_layer=None, ref_angle=None):
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    if angle: fp.SetOrientationDegrees(angle)
    if text_size:
        for item in [fp.Reference(), fp.Value()]:
            item.SetTextSize(pcbnew.VECTOR2I(MM(text_size), MM(text_size)))
            item.SetTextThickness(MM(text_size * 0.15))
    if ref_offset:
        dx, dy = ref_offset
        fp.Reference().SetPosition(pcbnew.VECTOR2I(MM(x + dx), MM(y + dy)))
    if ref_layer is not None:
        fp.Reference().SetLayer(ref_layer)
    if ref_angle is not None:
        fp.Reference().SetTextAngleDegrees(ref_angle)
    board.Add(fp)
    return fp

def move_fp_text(fp, ref_x, ref_y):
    fp.Reference().SetPosition(pcbnew.VECTOR2I(MM(ref_x), MM(ref_y)))

def assign(fp, pad, nets, net):
    if net not in nets: return
    for p in fp.Pads():
        if p.GetNumber() == str(pad):
            p.SetNet(nets[net]); return

def gold_fingers(board, count, pitch=2.54, pw=1.5, ph=10.0):
    fp = pcbnew.FOOTPRINT(board)
    for i in range(count):
        xo = MM(i * pitch)
        for side, layer in [('A', pcbnew.F_Cu), ('B', pcbnew.B_Cu)]:
            pad = pcbnew.PAD(fp)
            pad.SetNumber(f"{side}{i+1}")
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(MM(pw), MM(ph)))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            ls = pcbnew.LSET(); ls.AddLayer(layer)
            pad.SetLayerSet(ls)
            pad.SetPosition(pcbnew.VECTOR2I(xo, MM(ph/2)))
            fp.Add(pad)
    return fp

def gnd_fill(board, nets, w, h):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(False); z.SetLayer(pcbnew.B_Cu); z.SetNet(nets['GND'])
    ol = z.Outline(); ol.NewOutline()
    ol.Append(MM(0),MM(0)); ol.Append(MM(w),MM(0))
    ol.Append(MM(w),MM(h)); ol.Append(MM(0),MM(h))
    z.SetMinThickness(MM(0.2)); board.Add(z)

def check_overlaps(board, name, holes=None, cutouts=None):
    fps = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith("CTRG"): continue
        bb = fp.GetBoundingBox(False)  # exclude text from bbox
        fps.append((ref, pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    # Include silkscreen text objects
    ti = 0
    for drawing in board.GetDrawings():
        if hasattr(drawing, 'GetText') and drawing.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bb = drawing.GetBoundingBox()
            txt = drawing.GetText()[:12]
            fps.append((f"TXT:{txt}", pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                        pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
            ti += 1
    if holes:
        for i, (cx, cy, r) in enumerate(holes):
            fps.append((f"HOLE{i+1}", cx-r-3, cy-r-3, cx+r+3, cy+r+3))
    if cutouts:
        for i, (x1, y1, x2, y2) in enumerate(cutouts):
            fps.append((f"CUTOUT{i+1}", x1, y1, x2, y2))
    count = 0
    for i in range(len(fps)):
        for j in range(i+1, len(fps)):
            a, b = fps[i], fps[j]
            if a[0].startswith("CUTOUT") and b[0].startswith("CUTOUT"): continue
            if a[0].startswith("HOLE") and b[0].startswith("HOLE"): continue
            if a[0].startswith("HOLE") and b[0].startswith("CUTOUT"): continue
            if a[0].startswith("CUTOUT") and b[0].startswith("HOLE"): continue
            if a[0].startswith("TXT:") and b[0].startswith("TXT:"): continue  # text-vs-text OK
            ox = min(a[3],b[3]) - max(a[1],b[1])
            oy = min(a[4],b[4]) - max(a[2],b[2])
            both_r = a[0].startswith('R') and b[0].startswith('R')
            thresh = 1.5 if both_r else 0.5  # lenient for adjacent 0402, strict for everything else
            if ox > thresh and oy > thresh:
                print(f"  OVERLAP: {a[0]} vs {b[0]} ({ox:.1f}x{oy:.1f}mm)")
                count += 1
    # Also check footprint ref/value text vs component bodies
    texts = []
    for fp in board.GetFootprints():
        for item in [fp.Reference(), fp.Value()]:
            if item.IsVisible():
                bb = item.GetBoundingBox()
                texts.append((f"{fp.GetReference()}:{item.GetText()[:10]}",
                    pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    for tname, tl, tt, tr, tb in texts:
        for cname, cl, ct, cr, cb in fps:
            if cname.startswith("HOLE") or cname.startswith("CUTOUT"): continue
            if tname.startswith(cname): continue  # skip self
            # Adjacent resistor labels touching resistor bodies is normal for 0402
            if tname.split(':')[0].startswith('R') and cname.startswith('R'): continue
            ox = min(tr, cr) - max(tl, cl)
            oy = min(tb, cb) - max(tt, ct)
            if ox > 0.5 and oy > 0.5:
                print(f"  OVERLAP: text '{tname}' vs {cname} ({ox:.1f}x{oy:.1f}mm)")
                count += 1
    if count == 0: print(f"  No overlaps")
    return count

def add_text(board, text, x, y, size=3.0, thickness=0.3, angle=0, layer=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    lyr = layer if layer is not None else pcbnew.F_SilkS
    t.SetLayer(lyr)
    if lyr == pcbnew.B_SilkS:
        t.SetMirrored(True)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(thickness))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    if angle:
        t.SetTextAngleDegrees(angle)
    board.Add(t)

def add_gf_labels(board, net_map_a, net_map_b, gf_start_x, pitch, count, y_label=121):
    sz, th = 1.0, 0.12
    for i in range(count):
        x = gf_start_x + i * pitch
        pin = i + 1
        a_net = net_map_a.get(pin, '')
        b_net = net_map_b.get(pin, '')
        if a_net and b_net and a_net == b_net:
            add_text(board, a_net, x, y_label, size=sz, thickness=th, angle=90, layer=pcbnew.F_SilkS)
            add_text(board, a_net, x, y_label, size=sz, thickness=th, angle=90, layer=pcbnew.B_SilkS)
        else:
            if a_net:
                add_text(board, a_net, x, y_label, size=sz, thickness=th, angle=90, layer=pcbnew.F_SilkS)
            if b_net:
                add_text(board, b_net, x, y_label, size=sz, thickness=th, angle=90, layer=pcbnew.B_SilkS)

# ═══════════════════════════════════════════════════════════════
# BOARD OUTLINES (from neogeo-diag-mvs-prog/cha)
# Y=0 at top, Y=134 at bottom (gold fingers)
# ═══════════════════════════════════════════════════════════════
PROG_OUTLINE = [
    (0, 0), (36, 0), (36, 2.5), (48, 2.5), (48, 0),
    (126, 0), (126, 2.5), (138, 2.5), (138, 0), (174, 0),
    (174, 115), (164.3, 115), (164.3, 134),
    (9.7, 134), (9.7, 115), (0, 115), (0, 0),
]
CHA_OUTLINE = [
    (0, 0), (5.451, 0), (5.451, 2.5), (17.451, 2.5), (17.451, 0),
    (156.451, 0), (156.451, 2.5), (168.451, 2.5), (168.451, 0),
    (173.9, 0), (173.9, 115), (164.251, 115), (164.251, 134),
    (9.651, 134), (9.651, 115), (0, 115), (0, 0),
]
PROG_CIRCLES = [(10, 98, 5.0), (164, 98, 5.0)]
CHA_CIRCLES  = [(10, 98, 5.0), (164, 98, 5.0)]
PROG_CUTOUTS = [
    (36, -1, 48, 3.5), (126, -1, 138, 3.5),
    (-1, 115, 9.7, 135), (164.3, 115, 175, 135),
    (-1, -1, 175, 0), (-1, 134, 175, 135),
]
CHA_CUTOUTS = [
    (5.451, -1, 17.451, 3.5), (156.451, -1, 168.451, 3.5),
    (-1, 115, 9.651, 135), (164.251, 115, 175, 135),
    (-1, -1, 175, 0), (-1, 134, 175, 135),
]

BOARD_W, BOARD_H = 174.0, 134.0
GF_COUNT = 60
GF_TOTAL_W = (GF_COUNT - 1) * 2.54
GF_X_START = (BOARD_W - GF_TOTAL_W) / 2
GF_X = lambda pin: GF_X_START + (pin - 1) * 2.54
SOCKET_SPACING = 61.0

# ═══════════════════════════════════════════════════════════════
# REAL MVS PINOUTS — from MAME / neogeo-diag-mvs / Jamma Nation X
# Format: { pin: (A_side_signal, B_side_signal) }
# ═══════════════════════════════════════════════════════════════

CTRG2 = {
    1:('GND','GND'), 2:('GND','GND'), 3:('GND','GND'), 4:('GND','GND'),
    5:('D0','A1'), 6:('D1','A2'), 7:('D2','A3'), 8:('D3','A4'),
    9:('D4','A5'), 10:('D5','A6'), 11:('D6','A7'), 12:('D7','A8'),
    13:('D8','A9'), 14:('D9','A10'), 15:('D10','A11'), 16:('D11','A12'),
    17:('D12','A13'), 18:('D13','A14'), 19:('D14','A15'), 20:('D15','A16'),
    21:('nRW','A17'), 22:('nAS','A18'), 23:('ROMOEU','A19'),
    24:('ROMOEL','68KCLK'), 25:('PORTOEU','ROMWAIT'), 26:('PORTOEL','PWAIT0'),
    27:('PORTWEU','PWAIT1'), 28:('PORTWEL','PDTACK'),
    29:('VCC','VCC'), 30:('VCC','VCC'), 31:('VCC','VCC'), 32:('VCC','VCC'),
    33:('ROMOE','4MB'), 34:('NC','NC'), 35:('NC','RESET'),
    36:('NC','NC'), 37:('NC','NC'), 38:('NC','NC'), 39:('NC','NC'),
    40:('NC','SDPAD0'), 41:('NC','SDPAD1'), 42:('NC','SDPAD2'),
    43:('SDPA8','SDPAD3'), 44:('SDPA9','SDPAD4'), 45:('SDPA10','SDPAD5'),
    46:('SDPA11','SDPAD6'), 47:('SDRA8','SDPAD7'),
    48:('SDRA9','SDRA0'), 49:('SDRA10','SDRA1'), 50:('SDRA11','SDRA2'),
    51:('SDRA12','SDRA3'), 52:('SDRA13','SDRA4'), 53:('SDRA14','SDRA5'),
    54:('SDRA15','SDRA6'), 55:('SDRA16','SDRA7'),
    56:('SDRA17','SDROE'), 57:('SDRA18','SDRA19'), 58:('SDRA20','SDMRD'),
    59:('GND','GND'), 60:('GND','GND'),
}

CTRG1 = {
    1:('GND','GND'), 2:('GND','GND'),
    3:('P0','P1'), 4:('P2','P3'), 5:('P4','P5'), 6:('P6','P7'),
    7:('P8','P9'), 8:('P10','P11'), 9:('P12','P13'), 10:('P14','P15'),
    11:('P16','P17'), 12:('P18','P19'), 13:('P20','P21'), 14:('P22','P23'),
    15:('PCK1B','24M'), 16:('PCK2B','12M'), 17:('2H1','8M'), 18:('CA4','RESET'),
    19:('CR0','CR1'), 20:('CR2','CR3'), 21:('CR4','CR5'), 22:('CR6','CR7'),
    23:('CR8','CR9'), 24:('CR10','CR11'), 25:('CR12','CR13'), 26:('CR14','CR15'),
    27:('CR16','CR17'), 28:('CR18','CR19'),
    29:('VCC','VCC'), 30:('VCC','VCC'), 31:('VCC','VCC'), 32:('VCC','VCC'),
    33:('CR20','CR21'), 34:('CR22','CR23'), 35:('CR24','CR25'),
    36:('CR26','CR27'), 37:('CR28','CR29'), 38:('CR30','CR31'),
    39:('NC','FIX0'), 40:('NC','FIX1'), 41:('NC','FIX2'),
    42:('SYSTEMB','FIX3'), 43:('SDA0','FIX4'), 44:('SDA1','FIX5'),
    45:('SDA2','FIX6'), 46:('SDA3','FIX7'),
    47:('SDA4','SDMRD'), 48:('SDA5','SDD0'), 49:('SDA6','SDD1'),
    50:('SDA7','SDD2'), 51:('SDA8','SDD3'), 52:('SDA9','SDD4'),
    53:('SDA10','SDD5'), 54:('SDA11','SDD6'), 55:('SDA12','SDD7'),
    56:('SDA13','SDROM'), 57:('SDA14','SDA15'),
    58:('GND','GND'), 59:('GND','GND'), 60:('GND','GND'),
}


# ══════════════════════════════════════════════════════════════
# PROG ADAPTER
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("PROG ADAPTER v4 — full MVS pinout + sound ROM")
print("=" * 60)

prog = make_board(PROG_OUTLINE, PROG_CIRCLES)

# Internal net names (MVS canonical where possible, _R = resistor-protected)
prog_net_names = ['GND', 'VCC_5V', 'VCC_3V3']
# 68k data bus
prog_net_names += [f'D{i}' for i in range(16)] + [f'FD{i}' for i in range(16)]
# 68k address bus
prog_net_names += [f'A{i}' for i in range(1,20)] + [f'A{i}_R' for i in range(1,20)]
# 68k control
prog_net_names += ['nRW','nAS','ROMOEU','ROMOEL','ROMOE','68KCLK','RESET',
                   'nRW_R','nAS_R','ROMOEU_R','ROMOEL_R','ROMOE_R','68KCLK_R','RESET_R',
                   'PORTOEU','PORTOEL','PORTWEU','PORTWEL',
                   'ROMWAIT','PDTACK','4MB']
# Sound ROM data
prog_net_names += [f'SDPAD{i}' for i in range(8)] + [f'FSD{i}' for i in range(8)]
# Sound ROM address
prog_net_names += [f'SDRA{i}' for i in range(21)] + [f'SDRA{i}_R' for i in range(21)]
prog_net_names += [f'SDPA{i}' for i in range(8,12)] + [f'SDPA{i}_R' for i in range(8,12)]
prog_net_names += ['SDRA19','SDRA19_R']  # separate pin position
prog_net_names += ['SDMRD','SDROE','SDMRD_R','SDROE_R']
# Shift register control
prog_net_names += ['BUS_DIR','BUF_OE','SER_P','CLK_P','LOAD_P','SR1_OUT','SR2_OUT',
                   'SER_SD','CLK_SD','LOAD_SD','SSR1_OUT','SSR2_OUT','SSR3_OUT',
                   'SD_BUF_OE']
# microSD
prog_net_names += ['SD_CS','SD_CLK','SD_MOSI','SD_MISO']
# CHA passthrough
prog_net_names += [f'CR{i}' for i in range(32)] + [f'SDD{i}' for i in range(8)]
prog_net_names += [f'FIX{i}' for i in range(8)]
prog_net_names += [f'P{i}' for i in range(24)]
prog_net_names += ['SER_C','CLK_C','LOAD_C','SER_S','CLK_S','LOAD_S']
prog_net_names += ['PCK1B','PCK2B','CLK24M','CLK12M','CLK8M','SIG_2H1','CHA_CA4',
                   'SYSTEMB','SDROM','SDMRD_CHA','RESET_CHA']
# deduplicate
prog_net_names = list(dict.fromkeys(prog_net_names))
prog_nets = add_nets(prog, prog_net_names)

# ── CTRG2 Gold Fingers ──
gf = gold_fingers(prog, GF_COUNT)
place(prog, gf, "CTRG2", "MVS_PROG", GF_X_START, 124)
move_fp_text(gf, 40, 118)

# Map MVS signal names → internal net names for CTRG2
CTRG2_NET = {
    'GND':'GND', 'VCC':'VCC_5V', 'NC':None,
    'D0':'D0','D1':'D1','D2':'D2','D3':'D3','D4':'D4','D5':'D5','D6':'D6','D7':'D7',
    'D8':'D8','D9':'D9','D10':'D10','D11':'D11','D12':'D12','D13':'D13','D14':'D14','D15':'D15',
    'A1':'A1','A2':'A2','A3':'A3','A4':'A4','A5':'A5','A6':'A6','A7':'A7','A8':'A8',
    'A9':'A9','A10':'A10','A11':'A11','A12':'A12','A13':'A13','A14':'A14','A15':'A15',
    'A16':'A16','A17':'A17','A18':'A18','A19':'A19',
    'nRW':'nRW','nAS':'nAS','ROMOEU':'ROMOEU','ROMOEL':'ROMOEL','ROMOE':'ROMOE',
    '68KCLK':'68KCLK','RESET':'RESET',
    'PORTOEU':'PORTOEU','PORTOEL':'PORTOEL','PORTWEU':'PORTWEU','PORTWEL':'PORTWEL',
    'ROMWAIT':'ROMWAIT','PWAIT0':'GND','PWAIT1':'GND','PDTACK':'PDTACK','4MB':'4MB',
    'SDPAD0':'SDPAD0','SDPAD1':'SDPAD1','SDPAD2':'SDPAD2','SDPAD3':'SDPAD3',
    'SDPAD4':'SDPAD4','SDPAD5':'SDPAD5','SDPAD6':'SDPAD6','SDPAD7':'SDPAD7',
    'SDRA0':'SDRA0','SDRA1':'SDRA1','SDRA2':'SDRA2','SDRA3':'SDRA3',
    'SDRA4':'SDRA4','SDRA5':'SDRA5','SDRA6':'SDRA6','SDRA7':'SDRA7',
    'SDRA8':'SDRA8','SDRA9':'SDRA9','SDRA10':'SDRA10','SDRA11':'SDRA11',
    'SDRA12':'SDRA12','SDRA13':'SDRA13','SDRA14':'SDRA14','SDRA15':'SDRA15',
    'SDRA16':'SDRA16','SDRA17':'SDRA17','SDRA18':'SDRA18','SDRA19':'SDRA19','SDRA20':'SDRA20',
    'SDPA8':'SDPA8','SDPA9':'SDPA9','SDPA10':'SDPA10','SDPA11':'SDPA11',
    'SDMRD':'SDMRD','SDROE':'SDROE',
}

for pin, (a_sig, b_sig) in CTRG2.items():
    a_net = CTRG2_NET.get(a_sig)
    b_net = CTRG2_NET.get(b_sig)
    if a_net: assign(gf, f"A{pin}", prog_nets, a_net)
    if b_net: assign(gf, f"B{pin}", prog_nets, b_net)

# ── J1: FPGA U2 socket (centered left) ──
j1 = place(prog, load_fp('Connector_PinSocket_2.54mm','PinSocket_2x32_P2.54mm_Vertical'),
           "J1", "FPGA_U2", 57, 7)
for p in [1,2,3,4]: assign(j1, p, prog_nets, 'VCC_3V3')
for i in range(16): assign(j1, i+5, prog_nets, f'FD{i}')
for i in range(8): assign(j1, i+21, prog_nets, f'FSD{i}')
assign(j1,29,prog_nets,'SER_P'); assign(j1,30,prog_nets,'CLK_P')
assign(j1,31,prog_nets,'LOAD_P'); assign(j1,32,prog_nets,'ROMOE_R')
assign(j1,33,prog_nets,'SDROE_R'); assign(j1,34,prog_nets,'BUS_DIR')
assign(j1,35,prog_nets,'BUF_OE')
assign(j1,36,prog_nets,'SD_CS'); assign(j1,37,prog_nets,'SD_CLK')
assign(j1,38,prog_nets,'SD_MOSI'); assign(j1,39,prog_nets,'SD_MISO')
assign(j1,40,prog_nets,'SER_SD'); assign(j1,41,prog_nets,'CLK_SD')
assign(j1,42,prog_nets,'LOAD_SD'); assign(j1,43,prog_nets,'SD_BUF_OE')
assign(j1,44,prog_nets,'nAS_R'); assign(j1,45,prog_nets,'68KCLK_R')
assign(j1,46,prog_nets,'RESET_R'); assign(j1,47,prog_nets,'SDMRD_R')
assign(j1,48,prog_nets,'PDTACK'); assign(j1,49,prog_nets,'ROMWAIT')
assign(j1,50,prog_nets,'4MB')
for p in [59,61,63]: assign(j1, p, prog_nets, 'VCC_5V')  # VIN (odd)
for p in [60,62,64]: assign(j1, p, prog_nets, 'GND')   # GVN (even)

# ── J3: FPGA U1 socket (centered right, J1+61mm) ──
j3 = place(prog, load_fp('Connector_PinSocket_2.54mm','PinSocket_2x32_P2.54mm_Vertical'),
           "J3", "FPGA_U1", 57 + SOCKET_SPACING, 7)
for p in [1,2]: assign(j3, p, prog_nets, 'VCC_3V3')
for p in [3,4]: assign(j3, p, prog_nets, 'GND')
for i in range(32):
    if i+5 <= 64: assign(j3, i+5, prog_nets, f'CR{i}')
for i in range(8): assign(j3, i+37, prog_nets, f'SDD{i}')
assign(j3,45,prog_nets,'SER_C'); assign(j3,46,prog_nets,'CLK_C')
assign(j3,47,prog_nets,'LOAD_C'); assign(j3,48,prog_nets,'SER_S')
assign(j3,49,prog_nets,'CLK_S'); assign(j3,50,prog_nets,'LOAD_S')
assign(j3,51,prog_nets,'PCK1B'); assign(j3,52,prog_nets,'PCK2B')
assign(j3,53,prog_nets,'SDMRD_CHA')
for p in [59,61,63]: assign(j3, p, prog_nets, 'VCC_5V')  # VIN (odd)
for p in [60,62,64]: assign(j3, p, prog_nets, 'GND')   # GVN (even)

# ── J2: Inter-board connector (male 2x40, centered between J1 and J3) ──
j2 = place(prog, load_fp('Connector_PinHeader_2.54mm','PinHeader_2x40_P2.54mm_Vertical'),
           "J2", "TO_CHA", 87, 7)
for p in [1,2]: assign(j2, p, prog_nets, 'VCC_3V3')
for p in [3,4]: assign(j2, p, prog_nets, 'VCC_5V')
for p in [5,6,7,8]: assign(j2, p, prog_nets, 'GND')
for i in range(32): assign(j2, i+9, prog_nets, f'CR{i}')
for i in range(8): assign(j2, i+41, prog_nets, f'SDD{i}')
for i in range(8): assign(j2, i+49, prog_nets, f'FIX{i}')
assign(j2,57,prog_nets,'SER_C'); assign(j2,58,prog_nets,'CLK_C')
assign(j2,59,prog_nets,'LOAD_C'); assign(j2,60,prog_nets,'SER_S')
assign(j2,61,prog_nets,'CLK_S'); assign(j2,62,prog_nets,'LOAD_S')
assign(j2,63,prog_nets,'PCK1B'); assign(j2,64,prog_nets,'PCK2B')
assign(j2,65,prog_nets,'CLK24M'); assign(j2,66,prog_nets,'CLK12M')
assign(j2,67,prog_nets,'CLK8M'); assign(j2,68,prog_nets,'SIG_2H1')
assign(j2,69,prog_nets,'CHA_CA4'); assign(j2,70,prog_nets,'SYSTEMB')
assign(j2,71,prog_nets,'SDMRD_CHA'); assign(j2,72,prog_nets,'SDROM')
assign(j2,73,prog_nets,'RESET_CHA')
for p in [74,75,76,77,78,79,80]: assign(j2, p, prog_nets, 'GND')

# ── J4: microSD card slot ──
j4 = place(prog, load_fp('Connector_Card','microSD_HC_Molex_47219-2001'),
           "J4", "microSD", 15, 10)
sd_map = {'1':'SD_CS','2':'SD_MOSI','3':'GND','4':'VCC_3V3','5':'SD_CLK','6':'GND','7':'SD_MISO'}
for pin, net in sd_map.items(): assign(j4, pin, prog_nets, net)
for pad in j4.Pads():
    if pad.GetNumber() == '9': pad.SetNet(prog_nets['GND'])

# ── U1, U2: 74LVC245 — P-ROM data level shifters ──
# Left zone (x=20-50, left of J1)
for ref, y, d_off in [('U1', 42, 0), ('U2', 65, 8)]:
    u = place(prog, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'), ref, '74LVC245', 38, y)
    assign(u,1,prog_nets,'BUS_DIR')
    for i in range(8): assign(u, i+2, prog_nets, f'D{i+d_off}')
    assign(u,10,prog_nets,'GND'); assign(u,20,prog_nets,'VCC_5V')
    assign(u,19,prog_nets,'BUF_OE')
    for i in range(8): assign(u, 18-i, prog_nets, f'FD{i+d_off}')

# ── U3: 74LVC245 — Sound data level shifter (SDPAD0-7) ──
# Right zone near SDPAD gold fingers (pins B40-B47, x≈111-129mm)
u3 = place(prog, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'), 'U3', '74LVC245', 140, 50)
assign(u3,1,prog_nets,'GND')  # DIR tied low = B→A for read, but sound is output...
# For sound ROM output: FPGA side (A) → MVS side (B)
# DIR=HIGH means A→B
assign(u3,1,prog_nets,'VCC_5V')  # DIR=HIGH: FPGA→MVS
for i in range(8): assign(u3, i+2, prog_nets, f'FSD{i}')
assign(u3,10,prog_nets,'GND'); assign(u3,20,prog_nets,'VCC_5V')
assign(u3,19,prog_nets,'SD_BUF_OE')
for i in range(8): assign(u3, 18-i, prog_nets, f'SDPAD{i}')

# ── U4-U6: 74HC165 — 68k address + control shift registers ──
# Left zone, between J1 and J3, near address gold fingers
sr_prog = [
    ('U4', 22, 38, [('A1_R','7'),('A2_R','6'),('A3_R','5'),('A4_R','4'),('A5_R','3'),('A6_R','13'),('A7_R','12'),('A8_R','11')], 'GND', 'SR1_OUT'),
    ('U5', 22, 55, [('A9_R','7'),('A10_R','6'),('A11_R','5'),('A12_R','4'),('A13_R','3'),('A14_R','13'),('A15_R','12'),('A16_R','11')], 'SR1_OUT', 'SR2_OUT'),
    ('U6', 22, 72, [('A17_R','7'),('A18_R','6'),('A19_R','5'),('nRW_R','4'),('nAS_R','3'),('ROMOEU_R','13'),('ROMOEL_R','12'),('ROMOE_R','11')], 'SR2_OUT', 'SER_P'),
]
for ref, x, y, pins, si, so in sr_prog:
    u = place(prog, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y)
    assign(u,1,prog_nets,'LOAD_P'); assign(u,2,prog_nets,'CLK_P')
    for net, pin in pins: assign(u, pin, prog_nets, net)
    assign(u,8,prog_nets,'GND'); assign(u,16,prog_nets,'VCC_5V')
    assign(u,14,prog_nets,'GND'); assign(u,10,prog_nets,si); assign(u,9,prog_nets,so)

# ── U7-U10: 74HC165 — Sound ROM address shift registers ──
# Right zone near sound gold fingers (pins 43-58, x≈119-157mm)
sr_sound = [
    ('U7', 155, 30, [('SDRA0_R','7'),('SDRA1_R','6'),('SDRA2_R','5'),('SDRA3_R','4'),('SDRA4_R','3'),('SDRA5_R','13'),('SDRA6_R','12'),('SDRA7_R','11')], 'GND', 'SSR1_OUT'),
    ('U8', 155, 47, [('SDRA8_R','7'),('SDRA9_R','6'),('SDRA10_R','5'),('SDRA11_R','4'),('SDRA12_R','3'),('SDRA13_R','13'),('SDRA14_R','12'),('SDRA15_R','11')], 'SSR1_OUT', 'SSR2_OUT'),
    ('U9', 155, 64, [('SDRA16_R','7'),('SDRA17_R','6'),('SDRA18_R','5'),('SDRA19_R','4'),('SDRA20_R','3'),('SDPA8_R','13'),('SDPA9_R','12'),('SDPA10_R','11')], 'SSR2_OUT', 'SSR3_OUT'),
    ('U10', 155, 81, [('SDPA11_R','7'),('SDMRD_R','6'),('SDROE_R','5'),('GND','4'),('GND','3'),('GND','13'),('GND','12'),('GND','11')], 'SSR3_OUT', 'SER_SD'),
]
for ref, x, y, pins, si, so in sr_sound:
    u = place(prog, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y)
    assign(u,1,prog_nets,'LOAD_SD'); assign(u,2,prog_nets,'CLK_SD')
    for net, pin in pins: assign(u, pin, prog_nets, net)
    assign(u,8,prog_nets,'GND'); assign(u,16,prog_nets,'VCC_5V')
    assign(u,14,prog_nets,'GND'); assign(u,10,prog_nets,si); assign(u,9,prog_nets,so)

# ── Resistors ──
# 470Ω between gold finger pad and shift register / FPGA input
# Placed in rows near gold fingers, aligned with each pin's X position
prog_resistors = []
ri = 1

# Group 1: 68k address (B-side pins 5-23 → A1-A19)
for i in range(19):
    prog_resistors.append((f'R{ri}', GF_X(i+5), f'A{i+1}', f'A{i+1}_R'))
    ri += 1

# Group 2: 68k control (A-side pins 21-24, 33)
for pin, sig in [(21,'nRW'),(22,'nAS'),(23,'ROMOEU'),(24,'ROMOEL'),(33,'ROMOE')]:
    prog_resistors.append((f'R{ri}', GF_X(pin), sig, f'{sig}_R'))
    ri += 1

# Group 3: Direct signals (need resistor for 5V→3.3V protection)
for pin, sig in [(24,'68KCLK'),(35,'RESET')]:
    prog_resistors.append((f'R{ri}', GF_X(pin), sig, f'{sig}_R'))
    ri += 1

# Group 4: Sound ROM address (B48-B55: SDRA0-7, A47-A58: SDRA8-20, B57: SDRA19, A43-A46: SDPA8-11)
for i in range(8):
    prog_resistors.append((f'R{ri}', GF_X(48+i), f'SDRA{i}', f'SDRA{i}_R'))
    ri += 1
for i in range(8,18):
    prog_resistors.append((f'R{ri}', GF_X(47+i-8), f'SDRA{i}', f'SDRA{i}_R'))
    ri += 1
prog_resistors.append((f'R{ri}', GF_X(57), 'SDRA18', 'SDRA18_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(57), 'SDRA19', 'SDRA19_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(58), 'SDRA20', 'SDRA20_R')); ri += 1
for i in range(4):
    prog_resistors.append((f'R{ri}', GF_X(43+i), f'SDPA{i+8}', f'SDPA{i+8}_R'))
    ri += 1

# Group 5: Sound control
prog_resistors.append((f'R{ri}', GF_X(58), 'SDMRD', 'SDMRD_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(56), 'SDROE', 'SDROE_R')); ri += 1

print(f"  {ri-1} resistors on PROG")

# Place resistors with conflict-free stagger (no two at same x AND y)
# Place resistors with conflict-free stagger, avoiding J2 and holes
# J2 at x=145: bbox ~x=140-150. Hole2 at x=164 r=5: x=156-172.
# Resistors that would land in x=138-172 get redistributed to x=96-135 (open zone)
# Exclusion zones for resistor placement:
# J2 at x=145 (bbox ~140-150), HOLE1 at x=10 (bbox 4-16), HOLE2 at x=164 (bbox 158-170)
def rx_is_excluded(rx):
    if 82 <= rx <= 94: return True     # J2 (now centered at x=87)
    if rx <= 18: return True            # HOLE1
    if rx >= 156: return True           # HOLE2
    return False

# Fix exclusions first, then sort by x, then alternate rows
# Sorting by x ensures close-x resistors get different rows
fixed = []
for ref, rx, n1, n2 in prog_resistors:
    if rx_is_excluded(rx):
        if rx < 87: rx = 79
        elif rx < 95: rx = 96
        elif rx > 150: rx = 100 + (rx - 150) * 2  # push to open zone x=100-115
        else: rx = 20
    fixed.append((ref, rx, n1, n2))
fixed.sort(key=lambda r: r[1])
for i, (ref, rx, n1, n2) in enumerate(fixed):
    ry = 98 + (i % 4) * 4  # 4 rows: 98, 102, 106, 110
    r = place(prog, load_fp('Resistor_SMD','R_0402_1005Metric'), ref, '470R', rx, ry, angle=90, text_size=0.8, ref_offset=(-2.0, 0), ref_angle=90)
    assign(r,1,prog_nets,n1); assign(r,2,prog_nets,n2)

# ── Caps ──
cap_defs = [
    ('C1','100nF','VCC_5V','GND', 30, 42), ('C2','100nF','VCC_5V','GND', 30, 65),
    ('C3','100nF','VCC_5V','GND', 15, 38), ('C4','100nF','VCC_5V','GND', 15, 55),
    ('C5','100nF','VCC_5V','GND', 15, 72),
    ('C6','100nF','VCC_5V','GND', 148, 30), ('C7','100nF','VCC_5V','GND', 148, 47),
    ('C8','100nF','VCC_5V','GND', 148, 64), ('C9','100nF','VCC_5V','GND', 148, 81),
    ('C10','100nF','VCC_3V3','GND', 133, 50),
    ('C11','10uF','VCC_5V','GND', 8, 110),
]
for ref, val, np, nm, cx, cy in cap_defs:
    fn = 'C_0805_2012Metric' if '10u' in val else 'C_0402_1005Metric'
    c = place(prog, load_fp('Capacitor_SMD', fn), ref, val, cx, cy, text_size=0.5)
    assign(c,1,prog_nets,np); assign(c,2,prog_nets,nm)

# Silkscreen
add_text(prog, "NEOCART PROG v4", 160, 10, size=1.8, thickness=0.2)
add_text(prog, "NeoScanSDK", 160, 14, size=1.0, thickness=0.1)

# Gold finger labels from CTRG2 dict
prog_a_labels, prog_b_labels = {}, {}
for pin, (a_sig, b_sig) in CTRG2.items():
    if a_sig not in ('NC',): prog_a_labels[pin] = a_sig
    if b_sig not in ('NC',): prog_b_labels[pin] = b_sig
add_gf_labels(prog, prog_a_labels, prog_b_labels, GF_X_START, 2.54, GF_COUNT)

# Critical constraint: J1-J3 spacing must be exactly 61mm for QMTech FPGA
j1_x = pcbnew.ToMM(j1.GetPosition().x)
j3_x = pcbnew.ToMM(j3.GetPosition().x)
spacing = j3_x - j1_x
assert abs(spacing - SOCKET_SPACING) < 0.1, f"FATAL: J1-J3 spacing is {spacing:.1f}mm, must be {SOCKET_SPACING}mm!"
print(f"  J1-J3 spacing: {spacing:.1f}mm (OK)")

gnd_fill(prog, prog_nets, BOARD_W, BOARD_H)
prog_path = os.path.join(OUT_DIR, 'prog_adapter.kicad_pcb')
pcbnew.SaveBoard(prog_path, prog)
print(f"  {len(prog.GetFootprints())} footprints, {prog.GetNetCount()} nets")

# ══════════════════════════════════════════════════════════════
# CHA ADAPTER
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("CHA ADAPTER v4 — full MVS pinout")
print("=" * 60)

cha = make_board(CHA_OUTLINE, CHA_CIRCLES)

cha_net_names = ['GND','VCC_5V','VCC_3V3']
cha_net_names += [f'CR{i}' for i in range(32)] + [f'SDD{i}' for i in range(8)]
cha_net_names += [f'FIX{i}' for i in range(8)]
cha_net_names += [f'P{i}' for i in range(24)] + [f'P{i}_R' for i in range(24)]
cha_net_names += [f'SDA{i}' for i in range(16)] + [f'SDA{i}_R' for i in range(16)]
cha_net_names += ['PCK1B','PCK2B','CLK24M','CLK12M','CLK8M','SIG_2H1','CHA_CA4',
                  'SYSTEMB','SDROM','SDMRD_CHA','RESET_CHA']
cha_net_names += ['SER_C','CLK_C','LOAD_C','SER_S','CLK_S','LOAD_S',
                  'CSR1_OUT','CSR2_OUT','SSR1_OUT']
cha_net_names = list(dict.fromkeys(cha_net_names))
cha_nets = add_nets(cha, cha_net_names)

# ── CTRG1 Gold Fingers ──
gf_c = gold_fingers(cha, GF_COUNT)
place(cha, gf_c, "CTRG1", "MVS_CHA", GF_X_START, 124)
move_fp_text(gf_c, 40, 118)

CTRG1_NET = {
    'GND':'GND', 'VCC':'VCC_5V', 'NC':None,
    'CR0':'CR0','CR1':'CR1','CR2':'CR2','CR3':'CR3','CR4':'CR4','CR5':'CR5',
    'CR6':'CR6','CR7':'CR7','CR8':'CR8','CR9':'CR9','CR10':'CR10','CR11':'CR11',
    'CR12':'CR12','CR13':'CR13','CR14':'CR14','CR15':'CR15','CR16':'CR16','CR17':'CR17',
    'CR18':'CR18','CR19':'CR19','CR20':'CR20','CR21':'CR21','CR22':'CR22','CR23':'CR23',
    'CR24':'CR24','CR25':'CR25','CR26':'CR26','CR27':'CR27','CR28':'CR28','CR29':'CR29',
    'CR30':'CR30','CR31':'CR31',
    'P0':'P0','P1':'P1','P2':'P2','P3':'P3','P4':'P4','P5':'P5','P6':'P6','P7':'P7',
    'P8':'P8','P9':'P9','P10':'P10','P11':'P11','P12':'P12','P13':'P13',
    'P14':'P14','P15':'P15','P16':'P16','P17':'P17','P18':'P18','P19':'P19',
    'P20':'P20','P21':'P21','P22':'P22','P23':'P23',
    'SDA0':'SDA0','SDA1':'SDA1','SDA2':'SDA2','SDA3':'SDA3','SDA4':'SDA4',
    'SDA5':'SDA5','SDA6':'SDA6','SDA7':'SDA7','SDA8':'SDA8','SDA9':'SDA9',
    'SDA10':'SDA10','SDA11':'SDA11','SDA12':'SDA12','SDA13':'SDA13','SDA14':'SDA14','SDA15':'SDA15',
    'SDD0':'SDD0','SDD1':'SDD1','SDD2':'SDD2','SDD3':'SDD3',
    'SDD4':'SDD4','SDD5':'SDD5','SDD6':'SDD6','SDD7':'SDD7',
    'FIX0':'FIX0','FIX1':'FIX1','FIX2':'FIX2','FIX3':'FIX3',
    'FIX4':'FIX4','FIX5':'FIX5','FIX6':'FIX6','FIX7':'FIX7',
    'PCK1B':'PCK1B','PCK2B':'PCK2B','24M':'CLK24M','12M':'CLK12M','8M':'CLK8M',
    '2H1':'SIG_2H1','CA4':'CHA_CA4','SYSTEMB':'SYSTEMB',
    'SDMRD':'SDMRD_CHA','SDROM':'SDROM','RESET':'RESET_CHA',
}

for pin, (a_sig, b_sig) in CTRG1.items():
    a_net = CTRG1_NET.get(a_sig)
    b_net = CTRG1_NET.get(b_sig)
    if a_net: assign(gf_c, f"A{pin}", cha_nets, a_net)
    if b_net: assign(gf_c, f"B{pin}", cha_nets, b_net)

# ── J2: Inter-board from PROG (female 2x40, left edge) ──
j2c = place(cha, load_fp('Connector_PinHeader_2.54mm','PinHeader_2x40_P2.54mm_Vertical'),
            "J2", "FROM_PROG", 87, 7)
for p in [1,2]: assign(j2c,p,cha_nets,'VCC_3V3')
for p in [3,4]: assign(j2c,p,cha_nets,'VCC_5V')
for p in [5,6,7,8]: assign(j2c,p,cha_nets,'GND')
for i in range(32): assign(j2c,i+9,cha_nets,f'CR{i}')
for i in range(8): assign(j2c,i+41,cha_nets,f'SDD{i}')
for i in range(8): assign(j2c,i+49,cha_nets,f'FIX{i}')
assign(j2c,57,cha_nets,'SER_C'); assign(j2c,58,cha_nets,'CLK_C')
assign(j2c,59,cha_nets,'LOAD_C'); assign(j2c,60,cha_nets,'SER_S')
assign(j2c,61,cha_nets,'CLK_S'); assign(j2c,62,cha_nets,'LOAD_S')
assign(j2c,63,cha_nets,'PCK1B'); assign(j2c,64,cha_nets,'PCK2B')
assign(j2c,65,cha_nets,'CLK24M'); assign(j2c,66,cha_nets,'CLK12M')
assign(j2c,67,cha_nets,'CLK8M'); assign(j2c,68,cha_nets,'SIG_2H1')
assign(j2c,69,cha_nets,'CHA_CA4'); assign(j2c,70,cha_nets,'SYSTEMB')
assign(j2c,71,cha_nets,'SDMRD_CHA'); assign(j2c,72,cha_nets,'SDROM')
assign(j2c,73,cha_nets,'RESET_CHA')
for p in [74,75,76,77,78,79,80]: assign(j2c,p,cha_nets,'GND')

# ── U1-U3: 74HC165 — C-ROM address (P0-P23) shift registers ──
# Placed left zone near P-address gold fingers (pins 3-14)
sr_crom = [
    ('U1', 55, 35, [('P0_R','7'),('P2_R','6'),('P4_R','5'),('P6_R','4'),('P8_R','3'),('P10_R','13'),('P12_R','12'),('P14_R','11')], 'GND', 'CSR1_OUT'),
    ('U2', 55, 55, [('P16_R','7'),('P18_R','6'),('P20_R','5'),('P22_R','4'),('P1_R','3'),('P3_R','13'),('P5_R','12'),('P7_R','11')], 'CSR1_OUT', 'CSR2_OUT'),
    ('U3', 55, 75, [('P9_R','7'),('P11_R','6'),('P13_R','5'),('P15_R','4'),('P17_R','3'),('P19_R','13'),('P21_R','12'),('P23_R','11')], 'CSR2_OUT', 'SER_C'),
]
for ref, x, y, pins, si, so in sr_crom:
    u = place(cha, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y)
    assign(u,1,cha_nets,'LOAD_C'); assign(u,2,cha_nets,'CLK_C')
    for net, pin in pins: assign(u, pin, cha_nets, net)
    assign(u,8,cha_nets,'GND'); assign(u,16,cha_nets,'VCC_5V')
    assign(u,14,cha_nets,'GND'); assign(u,10,cha_nets,si); assign(u,9,cha_nets,so)

# ── U4-U5: 74HC165 — S-ROM address (SDA0-SDA15) shift registers ──
# Right zone near SDA gold fingers (pins 43-57)
sr_srom = [
    ('U4', 120, 35, [('SDA0_R','7'),('SDA1_R','6'),('SDA2_R','5'),('SDA3_R','4'),('SDA4_R','3'),('SDA5_R','13'),('SDA6_R','12'),('SDA7_R','11')], 'GND', 'SSR1_OUT'),
    ('U5', 120, 55, [('SDA8_R','7'),('SDA9_R','6'),('SDA10_R','5'),('SDA11_R','4'),('SDA12_R','3'),('SDA13_R','13'),('SDA14_R','12'),('SDA15_R','11')], 'SSR1_OUT', 'SER_S'),
]
for ref, x, y, pins, si, so in sr_srom:
    u = place(cha, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y)
    assign(u,1,cha_nets,'LOAD_S'); assign(u,2,cha_nets,'CLK_S')
    for net, pin in pins: assign(u, pin, cha_nets, net)
    assign(u,8,cha_nets,'GND'); assign(u,16,cha_nets,'VCC_5V')
    assign(u,14,cha_nets,'GND'); assign(u,10,cha_nets,si); assign(u,9,cha_nets,so)

# ── CHA Resistors ──
cha_resistors = []
ri = 1

# C-ROM address: P0-P23 on pins A3-A14 (even) and B3-B14 (odd)
for i in range(12):
    pin = i + 3
    cha_resistors.append((f'R{ri}', GF_X(pin), f'P{i*2}', f'P{i*2}_R'))
    ri += 1
for i in range(12):
    pin = i + 3
    cha_resistors.append((f'R{ri}', GF_X(pin), f'P{i*2+1}', f'P{i*2+1}_R'))
    ri += 1

# S-ROM address: SDA0-SDA14 on A43-A57, SDA15 on B57
for i in range(15):
    cha_resistors.append((f'R{ri}', GF_X(43+i), f'SDA{i}', f'SDA{i}_R'))
    ri += 1
cha_resistors.append((f'R{ri}', GF_X(57), 'SDA15', 'SDA15_R'))
ri += 1

print(f"  {ri-1} resistors on CHA")

# Exclusion: J2 (x=34-46), HOLE1 (x=2-18), HOLE2 (x=156-172)
def cha_rx_excluded(rx):
    if 82 <= rx <= 94: return True   # J2 (centered at x=87)
    if rx <= 19: return True          # HOLE1
    if rx >= 155: return True         # HOLE2
    return False

overflow_resistors_c = []
normal_resistors_c = []
for ref, rx, n1, n2 in cha_resistors:
    if cha_rx_excluded(rx):
        overflow_resistors_c.append((ref, rx, n1, n2))
    else:
        normal_resistors_c.append((ref, rx, n1, n2))

all_cha_r = list(normal_resistors_c)
if overflow_resistors_c:
    n = len(overflow_resistors_c)
    spread_start, spread_end = 50.0, 78.0
    spacing = (spread_end - spread_start) / max(n - 1, 1)
    for i, (ref, _, n1, n2) in enumerate(overflow_resistors_c):
        all_cha_r.append((ref, spread_start + i * spacing, n1, n2))

all_cha_r.sort(key=lambda r: r[1])
for i, (ref, rx, n1, n2) in enumerate(all_cha_r):
    ry = 100 + (i % 3) * 5
    r = place(cha, load_fp('Resistor_SMD','R_0402_1005Metric'), ref, '470R', rx, ry, angle=90, text_size=0.8, ref_offset=(-2.0, 0), ref_angle=90)
    assign(r,1,cha_nets,n1); assign(r,2,cha_nets,n2)

# ── CHA Caps ──
for ref, val, np, nm, cx, cy in [
    ('C1','100nF','VCC_5V','GND',48,30), ('C2','100nF','VCC_5V','GND',48,50),
    ('C3','100nF','VCC_5V','GND',48,70), ('C4','100nF','VCC_5V','GND',113,30),
    ('C5','100nF','VCC_5V','GND',113,50), ('C6','10uF','VCC_5V','GND',15,110)]:
    fn = 'C_0805_2012Metric' if '10u' in val else 'C_0402_1005Metric'
    c = place(cha, load_fp('Capacitor_SMD',fn), ref, val, cx, cy, text_size=0.5)
    assign(c,1,cha_nets,np); assign(c,2,cha_nets,nm)

add_text(cha, "NEOCART CHA-256 v4", 155, 10, size=1.8, thickness=0.2)
add_text(cha, "NeoScanSDK", 155, 14, size=1.0, thickness=0.1)

# Gold finger labels from CTRG1 dict
cha_a_labels, cha_b_labels = {}, {}
for pin, (a_sig, b_sig) in CTRG1.items():
    if a_sig not in ('NC',): cha_a_labels[pin] = a_sig
    if b_sig not in ('NC',): cha_b_labels[pin] = b_sig
add_gf_labels(cha, cha_a_labels, cha_b_labels, GF_X_START, 2.54, GF_COUNT)

gnd_fill(cha, cha_nets, BOARD_W, BOARD_H)
cha_path = os.path.join(OUT_DIR, 'cha_adapter.kicad_pcb')
pcbnew.SaveBoard(cha_path, cha)
print(f"  {len(cha.GetFootprints())} footprints, {cha.GetNetCount()} nets")

# Critical constraint: J2 must be aligned between both boards
prog_j2_x = pcbnew.ToMM(j2.GetPosition().x)
cha_j2_x = pcbnew.ToMM(j2c.GetPosition().x)
assert abs(prog_j2_x - cha_j2_x) < 0.1, f"FATAL: J2 x misaligned! PROG={prog_j2_x:.1f} CHA={cha_j2_x:.1f}"
# Through-hole connectors mate from opposite sides — same position, same orientation
prog_j2_angle = j2.GetOrientationDegrees()
cha_j2_angle = j2c.GetOrientationDegrees()
assert abs(prog_j2_angle - cha_j2_angle) < 0.1, f"FATAL: J2 angle mismatch! PROG={prog_j2_angle}° CHA={cha_j2_angle}°"
# Verify pin 1 and pin 2 exact positions match
for pin_num in ['1', '2']:
    pp = cp = None
    for pad in j2.Pads():
        if pad.GetNumber() == pin_num:
            pp = (pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y))
    for pad in j2c.Pads():
        if pad.GetNumber() == pin_num:
            cp = (pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y))
    assert abs(pp[0] - cp[0]) < 0.1 and abs(pp[1] - cp[1]) < 0.1, \
        f"FATAL: Pin {pin_num} mismatch! PROG={pp} CHA={cp}"
    print(f"  Pin {pin_num}: PROG=({pp[0]:.1f},{pp[1]:.1f}) CHA=({cp[0]:.1f},{cp[1]:.1f}) (OK)")

# ── Gate: only render if BOTH boards pass ──
prog_issues = check_overlaps(prog, "PROG", PROG_CIRCLES, PROG_CUTOUTS)
cha_issues = check_overlaps(cha, "CHA", CHA_CIRCLES, CHA_CUTOUTS)
total_issues = prog_issues + cha_issues

if total_issues > 0:
    print(f"\n*** {total_issues} OVERLAP(S) FOUND — FIX BEFORE RENDERING ***")
    print("Skipping renders.")
else:
    print("\nAll checks passed. Rendering 4 views at 4K...")
    views = []
    for name in ['prog_adapter', 'cha_adapter']:
        pcb = os.path.join(OUT_DIR, f'{name}.kicad_pcb')
        for side in ['top', 'bottom']:
            png = os.path.join(OUT_DIR, f'{name}_{side}.png')
            os.system(f'kicad-cli pcb render "{pcb}" -o "{png}" --side {side} --width 1920 --height 1440 2>/dev/null')
            views.append(png)
            print(f"  {name}_{side}.png")

    # Composite into single image: 2x2 grid
    from PIL import Image, ImageDraw, ImageFont
    labels = ['PROG Top', 'PROG Bottom', 'CHA Top', 'CHA Bottom']
    imgs = [Image.open(v) for v in views]
    w, h = imgs[0].size
    composite = Image.new('RGB', (w * 2, h * 2), (30, 30, 30))
    for i, (img, label) in enumerate(zip(imgs, labels)):
        col, row = i % 2, i // 2
        composite.paste(img, (col * w, row * h))
        draw = ImageDraw.Draw(composite)
        draw.text((col * w + 10, row * h + 10), label, fill=(255, 255, 255))
    comp_path = os.path.join(OUT_DIR, 'neocart_views.png')
    composite.save(comp_path)
    print(f"  Composite: neocart_views.png ({w*2}x{h*2})")

    # Superimposed views: PROG+CHA top, PROG+CHA bottom
    prog_top, prog_bot, cha_top, cha_bot = imgs
    for side, pa, ca in [('top', prog_top, cha_top), ('bottom', prog_bot, cha_bot)]:
        blended = Image.blend(pa.convert('RGBA'), ca.convert('RGBA'), 0.5)
        draw = ImageDraw.Draw(blended)
        draw.text((10, 10), f"PROG+CHA {side} (superimposed)", fill=(255, 255, 0))
        blended.save(os.path.join(OUT_DIR, f'neocart_overlay_{side}.png'))
        print(f"  neocart_overlay_{side}.png")

    # Also make a 2x3 composite: 4 views + 2 overlays
    comp6 = Image.new('RGB', (w * 2, h * 3), (30, 30, 30))
    all_imgs = imgs + [Image.open(os.path.join(OUT_DIR, f'neocart_overlay_{s}.png')).convert('RGB') for s in ['top','bottom']]
    all_labels = ['PROG Top', 'PROG Bottom', 'CHA Top', 'CHA Bottom', 'Overlay Top', 'Overlay Bottom']
    for i, (img, label) in enumerate(zip(all_imgs, all_labels)):
        col, row = i % 2, i // 2
        comp6.paste(img, (col * w, row * h))
        draw = ImageDraw.Draw(comp6)
        draw.text((col * w + 10, row * h + 10), label, fill=(255, 255, 255))
    comp6.save(os.path.join(OUT_DIR, 'neocart_views.png'))
    print(f"  Updated neocart_views.png ({w*2}x{h*3}) with overlays")
    print("Done!")
