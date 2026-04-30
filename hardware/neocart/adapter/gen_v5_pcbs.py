#!/usr/bin/env python3
"""
NeoCart v5 — Integrated FPGA PCB Generator
PROG board: ECP5-45K BGA-256 + SDRAM + shift registers + level shifters
CHA board: passive shift registers, connected via J2 sandwich

4-layer stackup: F.Cu (signals) / In1.Cu (GND) / In2.Cu (VCC) / B.Cu (signals)
"""
import pcbnew
import os, json, re, csv

MM = pcbnew.FromMM
FP_LIB = '/usr/share/kicad/footprints'
OUT_DIR = '/home/bruno/CLProjects/NeoScanSDK/hardware/neocart/adapter'

# ═══════════════════════════════════════════════════════════════
# HELPERS (reused from v4, with improvements)
# ═══════════════════════════════════════════════════════════════

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

def make_board(outline_pts, circles=None, layers=4):
    board = pcbnew.BOARD()
    make_board_outline(board, outline_pts)
    if circles:
        for cx, cy, r in circles:
            make_board_circle(board, cx, cy, r)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(layers)
    ds.m_TrackMinWidth = MM(0.15)  # tighter for BGA fanout
    ds.m_ViasMinSize = MM(0.4)
    ds.m_ViasMinDrill = MM(0.2)
    return board

def add_nets(board, names):
    nets = {}
    for i, name in enumerate(names, 1):
        net = pcbnew.NETINFO_ITEM(board, name, i)
        board.Add(net)
        nets[name] = net
    return nets

def place(board, fp, ref, value, x, y, angle=0, text_size=None, ref_layer=None):
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    if angle: fp.SetOrientationDegrees(angle)
    if text_size:
        for item in [fp.Reference(), fp.Value()]:
            item.SetTextSize(pcbnew.VECTOR2I(MM(text_size), MM(text_size)))
            item.SetTextThickness(MM(text_size * 0.15))
    if ref_layer is not None:
        fp.Reference().SetLayer(ref_layer)
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

def check_overlaps(board, name, holes=None, cutouts=None):
    fps = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith("CTRG"): continue
        bb = fp.GetBoundingBox(False)
        fps.append((ref, pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    # Include silkscreen text
    for drawing in board.GetDrawings():
        if hasattr(drawing, 'GetText') and drawing.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bb = drawing.GetBoundingBox()
            txt = drawing.GetText()[:12]
            fps.append((f"TXT:{txt}", pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                        pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
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
            if a[0].startswith("TXT:") and b[0].startswith("TXT:"): continue
            both_r = a[0].startswith('R') and b[0].startswith('R')
            thresh = 1.5 if both_r else 0.5
            if a[0].startswith('R') and b[0].startswith('R') and a[0].split(':')[0] != b[0]:
                continue  # R label vs R body OK
            ox = min(a[3],b[3]) - max(a[1],b[1])
            oy = min(a[4],b[4]) - max(a[2],b[2])
            if ox > thresh and oy > thresh:
                print(f"  OVERLAP: {a[0]} vs {b[0]} ({ox:.1f}x{oy:.1f}mm)")
                count += 1
    # Text vs component check
    texts = []
    for fp in board.GetFootprints():
        for item in [fp.Reference(), fp.Value()]:
            if item.IsVisible() and item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                bb = item.GetBoundingBox()
                texts.append((f"{fp.GetReference()}:{item.GetText()[:10]}",
                    pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    for tname, tl, tt, tr, tb in texts:
        for cname, cl, ct, cr, cb in fps:
            if cname.startswith("HOLE") or cname.startswith("CUTOUT"): continue
            if tname.startswith(cname): continue
            if tname.split(':')[0].startswith('R') and cname.startswith('R'): continue
            ox = min(tr, cr) - max(tl, cl)
            oy = min(tb, cb) - max(tt, ct)
            if ox > 0.5 and oy > 0.5:
                print(f"  OVERLAP: text '{tname}' vs {cname} ({ox:.1f}x{oy:.1f}mm)")
                count += 1
    if count == 0: print(f"  No overlaps")
    return count

# ═══════════════════════════════════════════════════════════════
# BOARD OUTLINES (same as v4)
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

# ═══════════════════════════════════════════════════════════════
# REAL MVS PINOUTS (verified from MAME/neogeo-diag)
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

# Load FPGA pin assignments
with open(os.path.join(OUT_DIR, 'fpga_pin_assignments.json')) as f:
    FPGA_PINS = json.load(f)  # signal -> (ball, bank)

print("NeoCart v5 Generator")
print(f"  FPGA pins: {len(FPGA_PINS)} assigned")
print(f"  CTRG2: {len(CTRG2)} pin pairs")
print(f"  CTRG1: {len(CTRG1)} pin pairs")

# ══════════════════════════════════════════════════════════════
# PROG BOARD v5 — 4-layer, BGA FPGA + SDRAM
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PROG BOARD v5 — ECP5-45K BGA-256 + SDRAM")
print("=" * 60)

prog = make_board(PROG_OUTLINE, PROG_CIRCLES, layers=4)

# ── Define all nets ──
prog_net_names = ['GND', 'VCC_5V', 'VCC_3V3', 'VCC_1V1']
# 68k data + sound data (through level shifters)
prog_net_names += [f'D{i}' for i in range(16)] + [f'FD{i}' for i in range(16)]
prog_net_names += [f'SDPAD{i}' for i in range(8)] + [f'FSD{i}' for i in range(8)]
# 68k address (through shift registers)
prog_net_names += [f'A{i}' for i in range(1,20)] + [f'A{i}_R' for i in range(1,20)]
# Control signals
prog_net_names += ['nRW','nAS','ROMOEU','ROMOEL','ROMOE','68KCLK','RESET',
                   'nRW_R','nAS_R','ROMOEU_R','ROMOEL_R','ROMOE_R','68KCLK_R','RESET_R',
                   'PORTOEU','PORTOEL','PORTWEU','PORTWEL',
                   'ROMWAIT','PDTACK','4MB']
# Sound ROM address
prog_net_names += [f'SDRA{i}' for i in range(21)] + [f'SDRA{i}_R' for i in range(21)]
prog_net_names += [f'SDPA{i}' for i in range(8,12)] + [f'SDPA{i}_R' for i in range(8,12)]
prog_net_names += ['SDRA19','SDRA19_R','SDMRD','SDROE','SDMRD_R','SDROE_R']
# Shift register control
prog_net_names += ['BUS_DIR','BUF_OE','SER_P','CLK_P','LOAD_P','SR1_OUT','SR2_OUT',
                   'SER_SD','CLK_SD','LOAD_SD','SSR1_OUT','SSR2_OUT','SSR3_OUT','SD_BUF_OE']
# FPGA direct control
prog_net_names += ['ROMOE_DIR','SDROE_DIR','SDMRD_DIR','nAS_DIR','CLK68K_DIR','RESET_DIR',
                   'PDTACK_OUT','ROMWAIT_OUT','FLAG_4MB_OUT']
# SD card
prog_net_names += ['SD_CS','SD_CLK','SD_MOSI','SD_MISO']
# SDRAM
prog_net_names += [f'SDRAM_D{i}' for i in range(16)]
prog_net_names += [f'SDRAM_A{i}' for i in range(13)]
prog_net_names += ['SDRAM_BA0','SDRAM_BA1','SDRAM_CLK','SDRAM_CKE','SDRAM_CS',
                   'SDRAM_RAS','SDRAM_CAS','SDRAM_WE','SDRAM_DQM']
# SPI Flash
prog_net_names += ['FLASH_CS','FLASH_CLK','FLASH_MOSI','FLASH_MISO']
# JTAG
prog_net_names += ['JTAG_TMS','JTAG_TCK','JTAG_TDI','JTAG_TDO']
# LED
prog_net_names += ['LED1']
# CHA passthrough (J2)
prog_net_names += [f'CR{i}' for i in range(32)] + [f'SDD{i}' for i in range(8)]
prog_net_names += [f'FIX{i}' for i in range(8)]
prog_net_names += ['SER_C','CLK_C','LOAD_C','SER_S','CLK_S','LOAD_S']
prog_net_names += ['PCK1B','PCK2B','CLK24M','CLK12M','CLK8M','SIG_2H1','CHA_CA4',
                   'SYSTEMB','SDROM','SDMRD_CHA','RESET_CHA']
# Clock
prog_net_names += ['CLK_50M']
prog_net_names = list(dict.fromkeys(prog_net_names))
prog_nets = add_nets(prog, prog_net_names)

# ── CTRG2 Gold Fingers (same as v4) ──
gf = gold_fingers(prog, GF_COUNT)
place(prog, gf, "CTRG2", "MVS_PROG", GF_X_START, 124)
move_fp_text(gf, 40, 118)

CTRG2_NET = {
    'GND':'GND', 'VCC':'VCC_5V', 'NC':None,
    **{f'D{i}':f'D{i}' for i in range(16)},
    **{f'A{i}':f'A{i}' for i in range(1,20)},
    'nRW':'nRW','nAS':'nAS','ROMOEU':'ROMOEU','ROMOEL':'ROMOEL','ROMOE':'ROMOE',
    '68KCLK':'68KCLK','RESET':'RESET',
    'PORTOEU':'PORTOEU','PORTOEL':'PORTOEL','PORTWEU':'PORTWEU','PORTWEL':'PORTWEL',
    'ROMWAIT':'ROMWAIT','PWAIT0':'GND','PWAIT1':'GND','PDTACK':'PDTACK','4MB':'4MB',
    **{f'SDPAD{i}':f'SDPAD{i}' for i in range(8)},
    **{f'SDRA{i}':f'SDRA{i}' for i in range(21)},
    'SDRA19':'SDRA19',
    **{f'SDPA{i}':f'SDPA{i}' for i in range(8,12)},
    'SDMRD':'SDMRD','SDROE':'SDROE',
}
for pin, (a_sig, b_sig) in CTRG2.items():
    a_net = CTRG2_NET.get(a_sig)
    b_net = CTRG2_NET.get(b_sig)
    if a_net: assign(gf, f"A{pin}", prog_nets, a_net)
    if b_net: assign(gf, f"B{pin}", prog_nets, b_net)

# ════════════════════════════════════════════
# COMPONENT PLACEMENT — Zone-based layout
# ════════════════════════════════════════════
# Board center: 87mm. Gold fingers at bottom (y=124).
# Zone A (center, y=20-55): FPGA BGA-256 (14x14mm)
# Zone B (right of FPGA, y=20-55): SDRAM TSOP-54
# Zone C (left of FPGA, y=20-55): SPI Flash, Crystal, LDOs, JTAG
# Zone D (left, y=60-90): 74LVC245 level shifters + 74HC165 address SRs
# Zone E (right, y=60-90): 74HC165 sound SRs
# Zone F (center, y=5-15): J2 inter-board, microSD
# Zone G (y=100-115): resistors near gold fingers

# ── U1: FPGA ECP5-45K BGA-256 ──
fpga = place(prog, load_fp('Package_BGA',
    'BGA-256_14.0x14.0mm_Layout16x16_P0.8mm_Ball0.45mm_Pad0.32mm_NSMD'),
    "U1", "LFE5U-45F", 87, 40, text_size=1.0)

# Assign all FPGA pins from the pin assignment map
for signal, (ball, bank) in FPGA_PINS.items():
    if signal in prog_nets:
        assign(fpga, ball, prog_nets, signal)
    else:
        print(f"  WARN: FPGA signal '{signal}' not in prog_nets")

# ── U2: SDRAM W9825G6KH TSOP-54 ──
sdram = place(prog, load_fp('Package_SO', 'TSOP-II-54_22.2x10.16mm_P0.8mm'),
    "U2", "W9825G6KH", 87, 70, text_size=0.8)
# SDRAM pin assignments (W9825G6KH-6 TSOP-54 datasheet)
sdram_pins = {
    '2':'SDRAM_D0', '4':'SDRAM_D1', '5':'SDRAM_D2', '7':'SDRAM_D3',
    '8':'SDRAM_D4', '10':'SDRAM_D5', '11':'SDRAM_D6', '13':'SDRAM_D7',
    '42':'SDRAM_D8', '44':'SDRAM_D9', '45':'SDRAM_D10', '47':'SDRAM_D11',
    '48':'SDRAM_D12', '50':'SDRAM_D13', '51':'SDRAM_D14', '53':'SDRAM_D15',
    '23':'SDRAM_A0', '24':'SDRAM_A1', '25':'SDRAM_A2', '26':'SDRAM_A3',
    '29':'SDRAM_A4', '30':'SDRAM_A5', '31':'SDRAM_A6', '32':'SDRAM_A7',
    '33':'SDRAM_A8', '34':'SDRAM_A9', '22':'SDRAM_A10', '35':'SDRAM_A11',
    '36':'SDRAM_A12',
    '20':'SDRAM_BA0', '21':'SDRAM_BA1',
    '38':'SDRAM_CLK', '37':'SDRAM_CKE', '19':'SDRAM_CS',
    '18':'SDRAM_RAS', '17':'SDRAM_CAS', '16':'SDRAM_WE',
    '15':'SDRAM_DQM',
    '1':'VCC_3V3', '14':'VCC_3V3', '27':'VCC_3V3', '28':'VCC_3V3',
    '40':'VCC_3V3', '41':'VCC_3V3', '54':'VCC_3V3',
    '3':'GND', '6':'GND', '9':'GND', '12':'GND', '39':'GND',
    '43':'GND', '46':'GND', '49':'GND', '52':'GND',
}
for pin, net in sdram_pins.items():
    assign(sdram, pin, prog_nets, net)

# ── U3: SPI Flash W25Q32 SOIC-8 ──
spiflash = place(prog, load_fp('Package_SO', 'SOIC-8_3.9x4.9mm_P1.27mm'),
    "U3", "W25Q32", 45, 30, text_size=0.8)
flash_pins = {'1':'FLASH_CS','2':'FLASH_MISO','3':'VCC_3V3','4':'GND',
              '5':'FLASH_MOSI','6':'FLASH_CLK','7':'VCC_3V3','8':'VCC_3V3'}
for pin, net in flash_pins.items():
    assign(spiflash, pin, prog_nets, net)

# ── U11: 3.3V LDO (AMS1117-3.3, SOT-223) ──
ldo33 = place(prog, load_fp('Package_TO_SOT_SMD', 'SOT-223-3_TabPin2'),
    "U11", "AMS1117-3.3", 45, 15, text_size=0.8)
assign(ldo33, '1', prog_nets, 'GND')
assign(ldo33, '2', prog_nets, 'VCC_3V3')  # output + tab
assign(ldo33, '3', prog_nets, 'VCC_5V')   # input

# ── U12: 1.1V LDO (AMS1117-1.2, SOT-223) ──
ldo11 = place(prog, load_fp('Package_TO_SOT_SMD', 'SOT-223-3_TabPin2'),
    "U12", "AMS1117-1.2", 45, 55, text_size=0.8)
assign(ldo11, '1', prog_nets, 'GND')
assign(ldo11, '2', prog_nets, 'VCC_1V1')  # output + tab
assign(ldo11, '3', prog_nets, 'VCC_3V3')  # input

# ── Y1: 50MHz Crystal (3225 package) ──
crystal = place(prog, load_fp('Crystal', 'Crystal_SMD_3225-4Pin_3.2x2.5mm'),
    "Y1", "50MHz", 55, 25, text_size=0.6)
assign(crystal, '1', prog_nets, 'CLK_50M')
assign(crystal, '3', prog_nets, 'GND')

# ── J2: Inter-board connector (2x40 male, centered) ──
j2 = place(prog, load_fp('Connector_PinHeader_2.54mm','PinHeader_2x40_P2.54mm_Vertical'),
    "J2", "TO_CHA", 25, 7)
# J2 pin assignments (same as v4)
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

# ── J3: microSD card slot ──
j3 = place(prog, load_fp('Connector_Card','microSD_HC_Molex_47219-2001'),
    "J3", "microSD", 160, 12, text_size=0.6)
sd_map = {'1':'SD_CS','2':'SD_MOSI','3':'GND','4':'VCC_3V3','5':'SD_CLK','6':'GND','7':'SD_MISO'}
for pin, net in sd_map.items(): assign(j3, pin, prog_nets, net)
for pad in j3.Pads():
    if pad.GetNumber() == '9': pad.SetNet(prog_nets['GND'])

# ── J4: JTAG header (2x3, 2.54mm) ──
jtag = place(prog, load_fp('Connector_PinHeader_2.54mm','PinHeader_2x03_P2.54mm_Vertical'),
    "J4", "JTAG", 15, 80, text_size=0.6)
assign(jtag, '1', prog_nets, 'VCC_3V3')
assign(jtag, '2', prog_nets, 'JTAG_TMS')
assign(jtag, '3', prog_nets, 'JTAG_TCK')
assign(jtag, '4', prog_nets, 'JTAG_TDO')
assign(jtag, '5', prog_nets, 'JTAG_TDI')
assign(jtag, '6', prog_nets, 'GND')

# ── Level Shifters (74LVC245) — Zone D, left side ──
for ref, y, d_off, dir_net in [('U4', 65, 0, 'BUS_DIR'), ('U5', 80, 8, 'BUS_DIR')]:
    u = place(prog, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'), ref, '74LVC245', 35, y, text_size=0.6)
    assign(u,1,prog_nets,dir_net)
    for i in range(8): assign(u, i+2, prog_nets, f'D{i+d_off}')
    assign(u,10,prog_nets,'GND'); assign(u,20,prog_nets,'VCC_5V')
    assign(u,19,prog_nets,'BUF_OE')
    for i in range(8): assign(u, 18-i, prog_nets, f'FD{i+d_off}')

# U6: Sound data level shifter
u6 = place(prog, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'), 'U6', '74LVC245', 160, 50, text_size=0.6)
assign(u6,1,prog_nets,'VCC_5V')  # DIR=HIGH: FPGA→MVS
for i in range(8): assign(u6, i+2, prog_nets, f'FSD{i}')
assign(u6,10,prog_nets,'GND'); assign(u6,20,prog_nets,'VCC_5V')
assign(u6,19,prog_nets,'SD_BUF_OE')
for i in range(8): assign(u6, 18-i, prog_nets, f'SDPAD{i}')

# ── Shift Registers (74HC165) — PROG address chain ──
sr_prog = [
    ('U7', 60, 65, [('A1_R','7'),('A2_R','6'),('A3_R','5'),('A4_R','4'),('A5_R','3'),('A6_R','13'),('A7_R','12'),('A8_R','11')], 'GND', 'SR1_OUT'),
    ('U8', 60, 80, [('A9_R','7'),('A10_R','6'),('A11_R','5'),('A12_R','4'),('A13_R','3'),('A14_R','13'),('A15_R','12'),('A16_R','11')], 'SR1_OUT', 'SR2_OUT'),
    ('U9', 60, 93, [('A17_R','7'),('A18_R','6'),('A19_R','5'),('nRW_R','4'),('nAS_R','3'),('ROMOEU_R','13'),('ROMOEL_R','12'),('ROMOE_R','11')], 'SR2_OUT', 'SER_P'),
]
for ref, x, y, pins, si, so in sr_prog:
    u = place(prog, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y, text_size=0.5)
    assign(u,1,prog_nets,'LOAD_P'); assign(u,2,prog_nets,'CLK_P')
    for net, pin in pins: assign(u, pin, prog_nets, net)
    assign(u,8,prog_nets,'GND'); assign(u,16,prog_nets,'VCC_5V')
    assign(u,14,prog_nets,'GND'); assign(u,10,prog_nets,si); assign(u,9,prog_nets,so)

# ── Shift Registers — Sound address chain (Zone E, right side) ──
sr_sound = [
    ('U13', 145, 35, [('SDRA0_R','7'),('SDRA1_R','6'),('SDRA2_R','5'),('SDRA3_R','4'),('SDRA4_R','3'),('SDRA5_R','13'),('SDRA6_R','12'),('SDRA7_R','11')], 'GND', 'SSR1_OUT'),
    ('U14', 145, 52, [('SDRA8_R','7'),('SDRA9_R','6'),('SDRA10_R','5'),('SDRA11_R','4'),('SDRA12_R','3'),('SDRA13_R','13'),('SDRA14_R','12'),('SDRA15_R','11')], 'SSR1_OUT', 'SSR2_OUT'),
    ('U15', 145, 69, [('SDRA16_R','7'),('SDRA17_R','6'),('SDRA18_R','5'),('SDRA19_R','4'),('SDRA20_R','3'),('SDPA8_R','13'),('SDPA9_R','12'),('SDPA10_R','11')], 'SSR2_OUT', 'SSR3_OUT'),
    ('U16', 145, 86, [('SDPA11_R','7'),('SDMRD_R','6'),('SDROE_R','5'),('GND','4'),('GND','3'),('GND','13'),('GND','12'),('GND','11')], 'SSR3_OUT', 'SER_SD'),
]
for ref, x, y, pins, si, so in sr_sound:
    u = place(prog, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y, text_size=0.5)
    assign(u,1,prog_nets,'LOAD_SD'); assign(u,2,prog_nets,'CLK_SD')
    for net, pin in pins: assign(u, pin, prog_nets, net)
    assign(u,8,prog_nets,'GND'); assign(u,16,prog_nets,'VCC_5V')
    assign(u,14,prog_nets,'GND'); assign(u,10,prog_nets,si); assign(u,9,prog_nets,so)

# ── Resistors (Zone G, y=100-115, near gold fingers) ──
prog_resistors = []
ri = 1
# 68k address
for i in range(19):
    prog_resistors.append((f'R{ri}', GF_X(i+5), f'A{i+1}', f'A{i+1}_R')); ri += 1
# Control
for pin, sig in [(21,'nRW'),(22,'nAS'),(23,'ROMOEU'),(24,'ROMOEL'),(33,'ROMOE')]:
    prog_resistors.append((f'R{ri}', GF_X(pin), sig, f'{sig}_R')); ri += 1
# Direct
for pin, sig in [(24,'68KCLK'),(35,'RESET')]:
    prog_resistors.append((f'R{ri}', GF_X(pin), sig, f'{sig}_R')); ri += 1
# Sound address
for i in range(8):
    prog_resistors.append((f'R{ri}', GF_X(48+i), f'SDRA{i}', f'SDRA{i}_R')); ri += 1
for i in range(8,18):
    prog_resistors.append((f'R{ri}', GF_X(47+i-8), f'SDRA{i}', f'SDRA{i}_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(57), 'SDRA18', 'SDRA18_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(57), 'SDRA19', 'SDRA19_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(58), 'SDRA20', 'SDRA20_R')); ri += 1
for i in range(4):
    prog_resistors.append((f'R{ri}', GF_X(43+i), f'SDPA{i+8}', f'SDPA{i+8}_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(58), 'SDMRD', 'SDMRD_R')); ri += 1
prog_resistors.append((f'R{ri}', GF_X(56), 'SDROE', 'SDROE_R')); ri += 1
print(f"  {ri-1} resistors on PROG")

# Exclusion zones for resistors
def rx_excluded(rx):
    if 18 <= rx <= 33: return True   # J2 at x=25 + HOLE1
    if rx >= 156: return True          # HOLE2
    return False

# Sort by x, alternate 4 rows
fixed_r = []
for ref, rx, n1, n2 in prog_resistors:
    if rx_excluded(rx):
        if rx < 87: rx = 79
        elif rx < 95: rx = 96
        elif rx > 150: rx = 100 + (rx - 150) * 2
        else: rx = 20
    fixed_r.append((ref, rx, n1, n2))
fixed_r.sort(key=lambda r: r[1])
for i, (ref, rx, n1, n2) in enumerate(fixed_r):
    ry = 100 + (i % 4) * 4
    r = place(prog, load_fp('Resistor_SMD','R_0402_1005Metric'), ref, '470R', rx, ry,
              angle=90, text_size=0.5, ref_layer=pcbnew.F_Fab)
    assign(r,1,prog_nets,n1); assign(r,2,prog_nets,n2)

# ── Capacitors ──
# FPGA decoupling (many caps needed for BGA)
cap_defs = [
    # FPGA VCC_1V1 decoupling (around FPGA at 87,40, body 14x14mm = 80-94 x 33-47)
    ('C1','100nF','VCC_1V1','GND', 77, 30), ('C2','100nF','VCC_1V1','GND', 97, 30),
    ('C3','100nF','VCC_1V1','GND', 77, 50), ('C4','100nF','VCC_1V1','GND', 97, 50),
    # FPGA VCC_3V3 decoupling
    ('C5','100nF','VCC_3V3','GND', 73, 35), ('C6','100nF','VCC_3V3','GND', 101, 35),
    ('C7','100nF','VCC_3V3','GND', 73, 45), ('C8','100nF','VCC_3V3','GND', 101, 45),
    # SDRAM decoupling (SDRAM at 130,40, body 22x10mm = 119-141 x 35-45)
    ('C9','100nF','VCC_3V3','GND', 73, 68), ('C10','100nF','VCC_3V3','GND', 101, 68),
    ('C11','100nF','VCC_3V3','GND', 73, 78), ('C12','100nF','VCC_3V3','GND', 101, 78),
    # SPI Flash
    ('C13','100nF','VCC_3V3','GND', 40, 35),
    # Level shifter decoupling
    ('C14','100nF','VCC_5V','GND', 42, 65), ('C15','100nF','VCC_5V','GND', 42, 80),
    ('C16','100nF','VCC_5V','GND', 153, 50),
    # SR decoupling
    ('C17','100nF','VCC_5V','GND', 53, 65), ('C18','100nF','VCC_5V','GND', 53, 80),
    ('C19','100nF','VCC_5V','GND', 53, 95),
    ('C20','100nF','VCC_5V','GND', 138, 35), ('C21','100nF','VCC_5V','GND', 138, 52),
    ('C22','100nF','VCC_5V','GND', 138, 69), ('C23','100nF','VCC_5V','GND', 138, 86),
    # LDO input/output
    ('C24','10uF','VCC_5V','GND', 8, 110),   # LDO 3.3V input
    ('C25','10uF','VCC_3V3','GND', 38, 15),   # LDO 3.3V output
    ('C26','10uF','VCC_3V3','GND', 38, 30),   # LDO 1.1V input
    ('C27','10uF','VCC_1V1','GND', 38, 50),   # LDO 1.1V output
    # Bulk
    ('C28','10uF','VCC_5V','GND', 165, 110),
]
for ref, val, np, nm, cx, cy in cap_defs:
    fn = 'C_0805_2012Metric' if '10u' in val else 'C_0402_1005Metric'
    c = place(prog, load_fp('Capacitor_SMD', fn), ref, val, cx, cy, text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(c,1,prog_nets,np); assign(c,2,prog_nets,nm)

# ── LED (indicator) ──
led = place(prog, load_fp('LED_SMD','LED_0402_1005Metric'), 'D1', 'LED', 15, 70, text_size=0.4)
assign(led, '1', prog_nets, 'LED1')
assign(led, '2', prog_nets, 'GND')
# LED resistor
rled = place(prog, load_fp('Resistor_SMD','R_0402_1005Metric'), 'R54', '1K', 15, 65,
             text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(rled, '1', prog_nets, 'LED1')
assign(rled, '2', prog_nets, 'VCC_3V3')

# ── Silkscreen ──
add_text(prog, "NEOCART v5", 130, 58, size=1.8, thickness=0.2)
add_text(prog, "NeoScanSDK", 130, 62, size=1.0, thickness=0.1)

# Gold finger labels
prog_a_labels, prog_b_labels = {}, {}
for pin, (a_sig, b_sig) in CTRG2.items():
    if a_sig not in ('NC',): prog_a_labels[pin] = a_sig
    if b_sig not in ('NC',): prog_b_labels[pin] = b_sig
add_gf_labels(prog, prog_a_labels, prog_b_labels, GF_X_START, 2.54, GF_COUNT)

# ── GND zones on signal layers ──
for layer in [pcbnew.F_Cu, pcbnew.B_Cu]:
    z = pcbnew.ZONE(prog)
    z.SetIsRuleArea(False); z.SetLayer(layer); z.SetNet(prog_nets['GND'])
    ol = z.Outline(); ol.NewOutline()
    ol.Append(MM(0),MM(0)); ol.Append(MM(174),MM(0))
    ol.Append(MM(174),MM(134)); ol.Append(MM(0),MM(134))
    z.SetMinThickness(MM(0.2)); z.SetThermalReliefSpokeWidth(MM(0.5))
    prog.Add(z)

# ── Inner layer power planes ──
# In1.Cu = GND plane
z_gnd_inner = pcbnew.ZONE(prog)
z_gnd_inner.SetIsRuleArea(False); z_gnd_inner.SetLayer(pcbnew.In1_Cu); z_gnd_inner.SetNet(prog_nets['GND'])
ol = z_gnd_inner.Outline(); ol.NewOutline()
ol.Append(MM(0),MM(0)); ol.Append(MM(174),MM(0)); ol.Append(MM(174),MM(134)); ol.Append(MM(0),MM(134))
z_gnd_inner.SetMinThickness(MM(0.2)); prog.Add(z_gnd_inner)

# In2.Cu = VCC_3V3 plane
z_vcc_inner = pcbnew.ZONE(prog)
z_vcc_inner.SetIsRuleArea(False); z_vcc_inner.SetLayer(pcbnew.In2_Cu); z_vcc_inner.SetNet(prog_nets['VCC_3V3'])
ol = z_vcc_inner.Outline(); ol.NewOutline()
ol.Append(MM(0),MM(0)); ol.Append(MM(174),MM(0)); ol.Append(MM(174),MM(134)); ol.Append(MM(0),MM(134))
z_vcc_inner.SetMinThickness(MM(0.2)); prog.Add(z_vcc_inner)

# Save PROG
prog_path = os.path.join(OUT_DIR, 'prog_v5.kicad_pcb')
pcbnew.SaveBoard(prog_path, prog)
print(f"  {len(prog.GetFootprints())} footprints, {prog.GetNetCount()} nets")
print(f"  Saved: {prog_path}")

# ══════════════════════════════════════════════════════════════
# CHA BOARD v5 — passive shift registers (same as v4 but simpler)
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("CHA BOARD v5 — passive shift registers")
print("=" * 60)

cha = make_board(CHA_OUTLINE, CHA_CIRCLES, layers=2)  # CHA stays 2-layer

cha_net_names = ['GND','VCC_5V','VCC_3V3']
cha_net_names += [f'CR{i}' for i in range(32)] + [f'SDD{i}' for i in range(8)]
cha_net_names += [f'FIX{i}' for i in range(8)]
cha_net_names += [f'P{i}' for i in range(24)] + [f'P{i}_R' for i in range(24)]
cha_net_names += [f'SDA{i}' for i in range(16)] + [f'SDA{i}_R' for i in range(16)]
cha_net_names += ['PCK1B','PCK2B','CLK24M','CLK12M','CLK8M','SIG_2H1','CHA_CA4',
                  'SYSTEMB','SDROM','SDMRD_CHA','RESET_CHA']
cha_net_names += ['SER_C','CLK_C','LOAD_C','SER_S','CLK_S','LOAD_S','CSR1_OUT','CSR2_OUT','SSR1_OUT']
cha_net_names = list(dict.fromkeys(cha_net_names))
cha_nets = add_nets(cha, cha_net_names)

# Gold fingers
gf_c = gold_fingers(cha, GF_COUNT)
place(cha, gf_c, "CTRG1", "MVS_CHA", GF_X_START, 124)
move_fp_text(gf_c, 40, 118)

CTRG1_NET = {
    'GND':'GND', 'VCC':'VCC_5V', 'NC':None,
    **{f'CR{i}':f'CR{i}' for i in range(32)},
    **{f'P{i}':f'P{i}' for i in range(24)},
    **{f'SDA{i}':f'SDA{i}' for i in range(16)},
    **{f'SDD{i}':f'SDD{i}' for i in range(8)},
    **{f'FIX{i}':f'FIX{i}' for i in range(8)},
    'PCK1B':'PCK1B','PCK2B':'PCK2B','24M':'CLK24M','12M':'CLK12M','8M':'CLK8M',
    '2H1':'SIG_2H1','CA4':'CHA_CA4','SYSTEMB':'SYSTEMB',
    'SDMRD':'SDMRD_CHA','SDROM':'SDROM','RESET':'RESET_CHA',
}
for pin, (a_sig, b_sig) in CTRG1.items():
    a_net = CTRG1_NET.get(a_sig)
    b_net = CTRG1_NET.get(b_sig)
    if a_net: assign(gf_c, f"A{pin}", cha_nets, a_net)
    if b_net: assign(gf_c, f"B{pin}", cha_nets, b_net)

# J2: Inter-board from PROG (female socket, centered)
j2c = place(cha, load_fp('Connector_PinHeader_2.54mm','PinHeader_2x40_P2.54mm_Vertical'),
            "J2", "FROM_PROG", 25, 7)
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

# C-ROM address shift registers
for ref, x, y, pins, si, so in [
    ('U1',55,35,[('P0_R','7'),('P2_R','6'),('P4_R','5'),('P6_R','4'),('P8_R','3'),('P10_R','13'),('P12_R','12'),('P14_R','11')],'GND','CSR1_OUT'),
    ('U2',55,55,[('P16_R','7'),('P18_R','6'),('P20_R','5'),('P22_R','4'),('P1_R','3'),('P3_R','13'),('P5_R','12'),('P7_R','11')],'CSR1_OUT','CSR2_OUT'),
    ('U3',55,75,[('P9_R','7'),('P11_R','6'),('P13_R','5'),('P15_R','4'),('P17_R','3'),('P19_R','13'),('P21_R','12'),('P23_R','11')],'CSR2_OUT','SER_C'),
]:
    u = place(cha, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y, text_size=0.5)
    assign(u,1,cha_nets,'LOAD_C'); assign(u,2,cha_nets,'CLK_C')
    for net, pin in pins: assign(u, pin, cha_nets, net)
    assign(u,8,cha_nets,'GND'); assign(u,16,cha_nets,'VCC_5V')
    assign(u,14,cha_nets,'GND'); assign(u,10,cha_nets,si); assign(u,9,cha_nets,so)

# S-ROM address shift registers
for ref, x, y, pins, si, so in [
    ('U4',120,35,[('SDA0_R','7'),('SDA1_R','6'),('SDA2_R','5'),('SDA3_R','4'),('SDA4_R','3'),('SDA5_R','13'),('SDA6_R','12'),('SDA7_R','11')],'GND','SSR1_OUT'),
    ('U5',120,55,[('SDA8_R','7'),('SDA9_R','6'),('SDA10_R','5'),('SDA11_R','4'),('SDA12_R','3'),('SDA13_R','13'),('SDA14_R','12'),('SDA15_R','11')],'SSR1_OUT','SER_S'),
]:
    u = place(cha, load_fp('Package_SO','SOIC-16_3.9x9.9mm_P1.27mm'), ref, '74HC165', x, y, text_size=0.5)
    assign(u,1,cha_nets,'LOAD_S'); assign(u,2,cha_nets,'CLK_S')
    for net, pin in pins: assign(u, pin, cha_nets, net)
    assign(u,8,cha_nets,'GND'); assign(u,16,cha_nets,'VCC_5V')
    assign(u,14,cha_nets,'GND'); assign(u,10,cha_nets,si); assign(u,9,cha_nets,so)

# CHA Resistors
cha_resistors = []
ri = 1
for i in range(12):
    cha_resistors.append((f'R{ri}', GF_X(i+3), f'P{i*2}', f'P{i*2}_R')); ri += 1
for i in range(12):
    cha_resistors.append((f'R{ri}', GF_X(i+3), f'P{i*2+1}', f'P{i*2+1}_R')); ri += 1
for i in range(15):
    cha_resistors.append((f'R{ri}', GF_X(43+i), f'SDA{i}', f'SDA{i}_R')); ri += 1
cha_resistors.append((f'R{ri}', GF_X(57), 'SDA15', 'SDA15_R')); ri += 1
print(f"  {ri-1} resistors on CHA")

def cha_rx_excluded(rx):
    if rx <= 33: return True          # J2 at x=25 + HOLE1 zone
    if rx >= 156: return True          # HOLE2
    return False

all_cha_r = []
for ref, rx, n1, n2 in cha_resistors:
    if cha_rx_excluded(rx):
        if rx < 87: rx = 35  # push right of J2+HOLE1 zone
        else: rx = 150
    all_cha_r.append((ref, rx, n1, n2))
all_cha_r.sort(key=lambda r: r[1])
for i, (ref, rx, n1, n2) in enumerate(all_cha_r):
    ry = 100 + (i % 4) * 4
    r = place(cha, load_fp('Resistor_SMD','R_0402_1005Metric'), ref, '470R', rx, ry,
              angle=90, text_size=0.5, ref_layer=pcbnew.F_Fab)
    assign(r,1,cha_nets,n1); assign(r,2,cha_nets,n2)

# CHA Caps
for ref, val, np, nm, cx, cy in [
    ('C1','100nF','VCC_5V','GND',48,30), ('C2','100nF','VCC_5V','GND',48,50),
    ('C3','100nF','VCC_5V','GND',48,70), ('C4','100nF','VCC_5V','GND',113,30),
    ('C5','100nF','VCC_5V','GND',113,50), ('C6','10uF','VCC_5V','GND',15,110)]:
    fn = 'C_0805_2012Metric' if '10u' in val else 'C_0402_1005Metric'
    c = place(cha, load_fp('Capacitor_SMD',fn), ref, val, cx, cy, text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(c,1,cha_nets,np); assign(c,2,cha_nets,nm)

add_text(cha, "NEOCART CHA v5", 87, 10, size=1.8, thickness=0.2)
add_text(cha, "NeoScanSDK", 87, 14, size=1.0, thickness=0.1)

cha_a_labels, cha_b_labels = {}, {}
for pin, (a_sig, b_sig) in CTRG1.items():
    if a_sig not in ('NC',): cha_a_labels[pin] = a_sig
    if b_sig not in ('NC',): cha_b_labels[pin] = b_sig
add_gf_labels(cha, cha_a_labels, cha_b_labels, GF_X_START, 2.54, GF_COUNT)

# CHA GND zones
for layer in [pcbnew.F_Cu, pcbnew.B_Cu]:
    z = pcbnew.ZONE(cha)
    z.SetIsRuleArea(False); z.SetLayer(layer); z.SetNet(cha_nets['GND'])
    ol = z.Outline(); ol.NewOutline()
    ol.Append(MM(0),MM(0)); ol.Append(MM(174),MM(0)); ol.Append(MM(174),MM(134)); ol.Append(MM(0),MM(134))
    z.SetMinThickness(MM(0.2)); z.SetThermalReliefSpokeWidth(MM(0.5))
    cha.Add(z)

cha_path = os.path.join(OUT_DIR, 'cha_v5.kicad_pcb')
pcbnew.SaveBoard(cha_path, cha)
print(f"  {len(cha.GetFootprints())} footprints, {cha.GetNetCount()} nets")

# ══════════════════════════════════════════════════════════════
# VERIFICATION GATES
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("VERIFICATION")
print("=" * 60)

# J2 alignment
prog_j2_x = pcbnew.ToMM(j2.GetPosition().x)
cha_j2_x = pcbnew.ToMM(j2c.GetPosition().x)
assert abs(prog_j2_x - cha_j2_x) < 0.1, f"FATAL: J2 misaligned! PROG={prog_j2_x} CHA={cha_j2_x}"
print(f"  J2 alignment: x={prog_j2_x:.1f}mm (OK)")

# Pin 1 match
for pin_num in ['1', '2']:
    pp = cp = None
    for pad in j2.Pads():
        if pad.GetNumber() == pin_num: pp = (pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y))
    for pad in j2c.Pads():
        if pad.GetNumber() == pin_num: cp = (pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y))
    assert abs(pp[0] - cp[0]) < 0.1 and abs(pp[1] - cp[1]) < 0.1, f"FATAL: Pin {pin_num} mismatch!"
    print(f"  Pin {pin_num}: PROG=({pp[0]:.1f},{pp[1]:.1f}) CHA=({cp[0]:.1f},{cp[1]:.1f}) (OK)")

# IC power check
HC165 = {'8':'GND','16':'VCC_5V','14':'GND'}
LVC245 = {'10':'GND','20':'VCC_5V'}
ic_errors = 0
for board_name, board_obj in [('PROG', prog), ('CHA', cha)]:
    for fp in board_obj.GetFootprints():
        ref, val = fp.GetReference(), fp.GetValue()
        power = HC165 if '165' in val else LVC245 if '245' in val else None
        if not power: continue
        for pin, expected in power.items():
            actual = next((p.GetNetname() for p in fp.Pads() if p.GetNumber() == pin), '')
            if expected not in actual:
                print(f"  ERROR: {board_name} {ref} pin {pin}: expected {expected}, got '{actual}'")
                ic_errors += 1
print(f"  IC power check: {ic_errors} errors")

# Overlap gates
print()
prog_issues = check_overlaps(prog, "PROG", PROG_CIRCLES, PROG_CUTOUTS)
cha_issues = check_overlaps(cha, "CHA", CHA_CIRCLES, CHA_CUTOUTS)
total_issues = prog_issues + cha_issues

if total_issues > 0:
    print(f"\n*** {total_issues} OVERLAP(S) — FIX BEFORE RENDERING ***")
    print("Skipping renders.")
else:
    print("\nAll checks passed. Rendering...")
    from PIL import Image, ImageDraw
    views, labels = [], []
    for name, pcb_path in [('prog_v5', prog_path), ('cha_v5', cha_path)]:
        for side in ['top', 'bottom']:
            png = os.path.join(OUT_DIR, f'{name}_{side}.png')
            os.system(f'kicad-cli pcb render "{pcb_path}" -o "{png}" --side {side} --width 1920 --height 1440 2>/dev/null')
            views.append(png)
            labels.append(f"{name.upper()} {side}")
    imgs = [Image.open(v) for v in views]
    w, h = imgs[0].size
    comp = Image.new('RGB', (w*2, h*2), (30,30,30))
    for i, (img, lbl) in enumerate(zip(imgs, labels)):
        col, row = i%2, i//2
        comp.paste(img, (col*w, row*h))
        ImageDraw.Draw(comp).text((col*w+10, row*h+10), lbl, fill=(255,255,0))
    comp.save(os.path.join(OUT_DIR, 'neocart_v5_views.png'))
    print("  Saved neocart_v5_views.png")
    print("Done!")
