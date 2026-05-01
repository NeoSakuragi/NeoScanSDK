#!/usr/bin/env python3
"""
NeoCart PROG Breakout Board — MVS PROG slot debug/dev adapter
Gold fingers → labeled headers + address LED display + activity LEDs + buttons
"""
import pcbnew, os

MM = pcbnew.FromMM
FP_LIB = '/usr/share/kicad/footprints'
OUT_DIR = '/home/bruno/CLProjects/NeoScanSDK/hardware/neocart/adapter'

def load_fp(lib, name):
    return pcbnew.FootprintLoad(os.path.join(FP_LIB, f'{lib}.pretty'), name)

def make_board(pts, circles=None):
    board = pcbnew.BOARD()
    for i in range(len(pts)-1):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(MM(pts[i][0]), MM(pts[i][1])))
        seg.SetEnd(pcbnew.VECTOR2I(MM(pts[i+1][0]), MM(pts[i+1][1])))
        seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(MM(0.1))
        board.Add(seg)
    if circles:
        for cx, cy, r in circles:
            c = pcbnew.PCB_SHAPE(board)
            c.SetShape(pcbnew.SHAPE_T_CIRCLE)
            c.SetCenter(pcbnew.VECTOR2I(MM(cx), MM(cy)))
            c.SetEnd(pcbnew.VECTOR2I(MM(cx+r), MM(cy)))
            c.SetLayer(pcbnew.Edge_Cuts); c.SetWidth(MM(0.1))
            board.Add(c)
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
        board.Add(net); nets[name] = net
    return nets

def place(board, fp, ref, value, x, y, angle=0, text_size=None, ref_layer=None):
    fp.SetReference(ref); fp.SetValue(value)
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    if angle: fp.SetOrientationDegrees(angle)
    if text_size:
        for item in [fp.Reference(), fp.Value()]:
            item.SetTextSize(pcbnew.VECTOR2I(MM(text_size), MM(text_size)))
            item.SetTextThickness(MM(text_size * 0.15))
    if ref_layer is not None:
        fp.Reference().SetLayer(ref_layer)
    board.Add(fp); return fp

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

def add_text(board, text, x, y, size=1.5, thickness=0.15, angle=0, layer=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    lyr = layer if layer is not None else pcbnew.F_SilkS
    t.SetLayer(lyr)
    if lyr == pcbnew.B_SilkS: t.SetMirrored(True)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(thickness))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    if angle: t.SetTextAngleDegrees(angle)
    board.Add(t)

# ═══════════════════════════════════════════════
# BOARD OUTLINE (same as PROG)
# ═══════════════════════════════════════════════
OUTLINE = [
    (0, 0), (36, 0), (36, 2.5), (48, 2.5), (48, 0),
    (126, 0), (126, 2.5), (138, 2.5), (138, 0), (174, 0),
    (174, 115), (164.3, 115), (164.3, 134),
    (9.7, 134), (9.7, 115), (0, 115), (0, 0),
]
CIRCLES = [(10, 98, 5.0), (164, 98, 5.0)]

GF_COUNT = 60
GF_TOTAL_W = (GF_COUNT - 1) * 2.54
GF_X_START = (174.0 - GF_TOTAL_W) / 2

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

print("PROG Breakout Board Generator")

board = make_board(OUTLINE, CIRCLES)

# ── All nets ──
net_names = ['GND', 'VCC', 'VCC_3V3']
net_names += [f'A{i}' for i in range(1, 20)]
net_names += [f'D{i}' for i in range(16)]
net_names += ['nRW','nAS','ROMOEU','ROMOEL','ROMOE','68KCLK','RESET',
              'PDTACK','ROMWAIT','4MB',
              'PORTOEU','PORTOEL','PORTWEU','PORTWEL']
net_names += [f'SDRA{i}' for i in range(21)]
net_names += [f'SDPA{i}' for i in range(8,12)]
net_names += [f'SDPAD{i}' for i in range(8)]
net_names += ['SDROE','SDMRD']
# Latch outputs for LEDs
net_names += [f'LA{i}' for i in range(1, 20)]
net_names += ['LATCH_EN']
net_names = list(dict.fromkeys(net_names))
nets = add_nets(board, net_names)

# ── Gold Fingers ──
gf = gold_fingers(board, GF_COUNT)
place(board, gf, "CTRG2", "MVS_PROG", GF_X_START, 124)

CTRG2_NET = {
    'GND':'GND','VCC':'VCC','NC':None,
    **{f'D{i}':f'D{i}' for i in range(16)},
    **{f'A{i}':f'A{i}' for i in range(1,20)},
    'nRW':'nRW','nAS':'nAS','ROMOEU':'ROMOEU','ROMOEL':'ROMOEL','ROMOE':'ROMOE',
    '68KCLK':'68KCLK','RESET':'RESET',
    'PORTOEU':'PORTOEU','PORTOEL':'PORTOEL','PORTWEU':'PORTWEU','PORTWEL':'PORTWEL',
    'ROMWAIT':'ROMWAIT','PWAIT0':'GND','PWAIT1':'GND','PDTACK':'PDTACK','4MB':'4MB',
    **{f'SDPAD{i}':f'SDPAD{i}' for i in range(8)},
    **{f'SDRA{i}':f'SDRA{i}' for i in range(21)},
    **{f'SDPA{i}':f'SDPA{i}' for i in range(8,12)},
    'SDMRD':'SDMRD','SDROE':'SDROE',
}
for pin, (a_sig, b_sig) in CTRG2.items():
    a_net = CTRG2_NET.get(a_sig)
    b_net = CTRG2_NET.get(b_sig)
    if a_net: assign(gf, f"A{pin}", nets, a_net)
    if b_net: assign(gf, f"B{pin}", nets, b_net)

# ════════════════════════════════════════════
# HEADERS — bus breakout
# ════════════════════════════════════════════

# J1: P-ROM Address + Data (2×20, left side)
j1 = place(board, load_fp('Connector_PinSocket_2.54mm','PinSocket_2x20_P2.54mm_Vertical'),
           "J1", "P-ROM_BUS", 15, 5, text_size=0.8)
j1_pins = [
    (1,'GND'),(2,'VCC'),
    (3,'A1'),(4,'D0'),(5,'A2'),(6,'D1'),(7,'A3'),(8,'D2'),(9,'A4'),(10,'D3'),
    (11,'A5'),(12,'D4'),(13,'A6'),(14,'D5'),(15,'A7'),(16,'D6'),(17,'A8'),(18,'D7'),
    (19,'A9'),(20,'D8'),(21,'A10'),(22,'D9'),(23,'A11'),(24,'D10'),
    (25,'A12'),(26,'D11'),(27,'A13'),(28,'D12'),(29,'A14'),(30,'D13'),
    (31,'A15'),(32,'D14'),(33,'A16'),(34,'D15'),
    (35,'A17'),(36,'VCC_3V3'),(37,'A18'),(38,'GND'),(39,'A19'),(40,'GND'),
]
for pin, net in j1_pins:
    assign(j1, pin, nets, net)

# J2: P-ROM Control (2×8, center-left)
j2 = place(board, load_fp('Connector_PinSocket_2.54mm','PinSocket_2x08_P2.54mm_Vertical'),
           "J2", "P-ROM_CTRL", 60, 10, text_size=0.8)
j2_pins = [
    (1,'nRW'),(2,'nAS'),(3,'ROMOEU'),(4,'ROMOEL'),
    (5,'ROMOE'),(6,'68KCLK'),(7,'PDTACK'),(8,'ROMWAIT'),
    (9,'4MB'),(10,'RESET'),(11,'PORTOEU'),(12,'PORTOEL'),
    (13,'PORTWEU'),(14,'PORTWEL'),(15,'GND'),(16,'GND'),
]
for pin, net in j2_pins:
    assign(j2, pin, nets, net)

# J3: V-ROM (2×20, right side)
j3 = place(board, load_fp('Connector_PinSocket_2.54mm','PinSocket_2x20_P2.54mm_Vertical'),
           "J3", "V-ROM_BUS", 110, 5, text_size=0.8)
j3_pins = [
    (1,'GND'),(2,'VCC'),
    (3,'SDRA0'),(4,'SDRA1'),(5,'SDRA2'),(6,'SDRA3'),
    (7,'SDRA4'),(8,'SDRA5'),(9,'SDRA6'),(10,'SDRA7'),
    (11,'SDRA8'),(12,'SDRA9'),(13,'SDRA10'),(14,'SDRA11'),
    (15,'SDRA12'),(16,'SDRA13'),(17,'SDRA14'),(18,'SDRA15'),
    (19,'SDRA16'),(20,'SDRA17'),(21,'SDRA18'),(22,'SDRA19'),
    (23,'SDRA20'),(24,'SDPA8'),(25,'SDPA9'),(26,'SDPA10'),
    (27,'SDPA11'),(28,'SDPAD0'),(29,'SDPAD1'),(30,'SDPAD2'),
    (31,'SDPAD3'),(32,'SDPAD4'),(33,'SDPAD5'),(34,'SDPAD6'),
    (35,'SDPAD7'),(36,'SDROE'),(37,'SDMRD'),(38,'GND'),
    (39,'VCC_3V3'),(40,'GND'),
]
for pin, net in j3_pins:
    assign(j3, pin, nets, net)

# J4: Power (1×6)
j4 = place(board, load_fp('Connector_PinSocket_2.54mm','PinSocket_1x06_P2.54mm_Vertical'),
           "J4", "POWER", 85, 5, text_size=0.8)
for pin, net in [(1,'VCC'),(2,'VCC'),(3,'VCC_3V3'),(4,'VCC_3V3'),(5,'GND'),(6,'GND')]:
    assign(j4, pin, nets, net)

# ════════════════════════════════════════════
# HEADER PIN LABELS
# ════════════════════════════════════════════
def add_header_labels(board, hx, hy, pins, col_offset=6.5):
    """Add signal name labels next to header pins. pins = [(pin_num, name), ...]"""
    for pin, name in pins:
        if name in ('GND','VCC','VCC_3V3'): continue
        row = (pin - 1) // 2
        is_right = (pin % 2 == 0)
        y = hy + row * 2.54
        if is_right:
            x = hx + col_offset
        else:
            x = hx - col_offset
        just = pcbnew.GR_TEXT_H_ALIGN_LEFT if is_right else pcbnew.GR_TEXT_H_ALIGN_RIGHT
        t = pcbnew.PCB_TEXT(board)
        t.SetText(name)
        t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(MM(0.7), MM(0.7)))
        t.SetTextThickness(MM(0.08))
        t.SetHorizJustify(just)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        board.Add(t)

add_header_labels(board, 15, 5, j1_pins)
add_header_labels(board, 60, 10, j2_pins)
add_header_labels(board, 110, 5, j3_pins)

# J4 power labels (1×6, single column)
for pin, name in [(1,'5V'),(2,'5V'),(3,'3V3'),(4,'3V3'),(5,'GND'),(6,'GND')]:
    y = 5 + (pin-1) * 2.54
    add_text(board, name, 85 + 5, y, size=0.7, thickness=0.08)

# ════════════════════════════════════════════
# 74HC573 LATCHES — address display
# ════════════════════════════════════════════
# U1: A1-A8 → LA1-LA8
u1 = place(board, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'),
           'U1', '74HC573', 35, 68, text_size=0.6)
assign(u1, 1, nets, 'GND')       # OE (low = outputs enabled)
assign(u1, 11, nets, 'LATCH_EN') # LE
assign(u1, 10, nets, 'GND')
assign(u1, 20, nets, 'VCC')
for i in range(8):
    assign(u1, i+2, nets, f'A{i+1}')   # D0-D7 = A1-A8
    assign(u1, 19-i, nets, f'LA{i+1}') # Q0-Q7 = LA1-LA8

# U2: A9-A16 → LA9-LA16
u2 = place(board, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'),
           'U2', '74HC573', 75, 68, text_size=0.6)
assign(u2, 1, nets, 'GND')
assign(u2, 11, nets, 'LATCH_EN')
assign(u2, 10, nets, 'GND')
assign(u2, 20, nets, 'VCC')
for i in range(8):
    assign(u2, i+2, nets, f'A{i+9}')
    assign(u2, 19-i, nets, f'LA{i+9}')

# U3: A17-A19 → LA17-LA19 (5 inputs unused, tied to GND)
u3 = place(board, load_fp('Package_SO','SOIC-20W_7.5x12.8mm_P1.27mm'),
           'U3', '74HC573', 115, 68, text_size=0.6)
assign(u3, 1, nets, 'GND')
assign(u3, 11, nets, 'LATCH_EN')
assign(u3, 10, nets, 'GND')
assign(u3, 20, nets, 'VCC')
assign(u3, 2, nets, 'A17'); assign(u3, 19, nets, 'LA17')
assign(u3, 3, nets, 'A18'); assign(u3, 18, nets, 'LA18')
assign(u3, 4, nets, 'A19'); assign(u3, 17, nets, 'LA19')
for p in [5,6,7,8,9]:
    assign(u3, p, nets, 'GND')

# ════════════════════════════════════════════
# LEDs — address display + activity
# ════════════════════════════════════════════
LED_Y = 56
LED_X_START = 18
LED_SPACING = 7.0

# 19 address LEDs (from latch outputs)
ri = 1
for i in range(19):
    x = LED_X_START + i * LED_SPACING
    led = place(board, load_fp('LED_SMD','LED_0805_2012Metric'),
                f'D{i+1}', 'LED', x, LED_Y, text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(led, 1, nets, f'LA{i+1}')
    assign(led, 2, nets, f'RLED{i+1}')
    # Add net for LED resistor cathode side
    if f'RLED{i+1}' not in nets:
        n = pcbnew.NETINFO_ITEM(board, f'RLED{i+1}', board.GetNetCount())
        board.Add(n); nets[f'RLED{i+1}'] = n
        assign(led, 2, nets, f'RLED{i+1}')

    r = place(board, load_fp('Resistor_SMD','R_0402_1005Metric'),
              f'R{ri}', '1K', x, LED_Y + 4, angle=90, text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(r, 1, nets, f'RLED{i+1}')
    assign(r, 2, nets, 'GND')
    ri += 1
    # Label below LED
    add_text(board, f'A{i+1}', x, LED_Y - 3, size=0.8, thickness=0.1)

# Activity LEDs (direct from bus, no latch)
activity = [
    ('nAS', 'BUS', 150, LED_Y),
    ('ROMOEU', 'PROM', 157, LED_Y),
    ('SDROE', 'VROM', 164, LED_Y),
]
for sig, label, x, y in activity:
    led = place(board, load_fp('LED_SMD','LED_0805_2012Metric'),
                f'D{20+activity.index((sig,label,x,y))}', 'LED', x, y,
                text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(led, 1, nets, sig)
    rnet = f'RACT_{sig}'
    n = pcbnew.NETINFO_ITEM(board, rnet, board.GetNetCount())
    board.Add(n); nets[rnet] = n
    assign(led, 2, nets, rnet)
    r = place(board, load_fp('Resistor_SMD','R_0402_1005Metric'),
              f'R{ri}', '1K', x, y + 4, angle=90, text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(r, 1, nets, rnet)
    assign(r, 2, nets, 'GND')
    ri += 1
    add_text(board, label, x, y - 3, size=0.8, thickness=0.1)

# Power LED
pled = place(board, load_fp('LED_SMD','LED_0805_2012Metric'),
             'D23', 'PWR', 87, 40, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(pled, 1, nets, 'VCC')
pnet = 'RPWR'
n = pcbnew.NETINFO_ITEM(board, pnet, board.GetNetCount()); board.Add(n); nets[pnet] = n
assign(pled, 2, nets, pnet)
rpwr = place(board, load_fp('Resistor_SMD','R_0402_1005Metric'),
             f'R{ri}', '1K', 87, 44, angle=90, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(rpwr, 1, nets, pnet)
assign(rpwr, 2, nets, 'GND')
ri += 1
add_text(board, 'PWR', 87, 37, size=0.8, thickness=0.1)

# ════════════════════════════════════════════
# BUTTONS
# ════════════════════════════════════════════
# SW1: Freeze — press = LE goes LOW = latch holds
sw1 = place(board, load_fp('Button_Switch_THT','SW_PUSH_1P1T_6x3.5mm_H4.3_APEM_MJTP1243'),
            'SW1', 'FREEZE', 145, 68, text_size=0.6)
assign(sw1, 1, nets, 'LATCH_EN')
assign(sw1, 2, nets, 'GND')

# Pull-up for LATCH_EN (normally HIGH = transparent)
r_pu = place(board, load_fp('Resistor_SMD','R_0402_1005Metric'),
             f'R{ri}', '10K', 140, 65, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(r_pu, 1, nets, 'VCC')
assign(r_pu, 2, nets, 'LATCH_EN')
ri += 1

# SW2: Reset
sw2 = place(board, load_fp('Button_Switch_THT','SW_PUSH_1P1T_6x3.5mm_H4.3_APEM_MJTP1243'),
            'SW2', 'RESET', 145, 80, text_size=0.6)
assign(sw2, 1, nets, 'RESET')
assign(sw2, 2, nets, 'GND')

# ════════════════════════════════════════════
# LDO + POWER
# ════════════════════════════════════════════
ldo = place(board, load_fp('Package_TO_SOT_SMD','SOT-223-3_TabPin2'),
            'U4', 'AMS1117-3.3', 155, 40, text_size=0.6)
assign(ldo, 1, nets, 'GND')
assign(ldo, 2, nets, 'VCC_3V3')
assign(ldo, 3, nets, 'VCC')

# LDO caps
c1 = place(board, load_fp('Capacitor_SMD','C_0805_2012Metric'),
           'C1', '10uF', 148, 35, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(c1, 1, nets, 'VCC'); assign(c1, 2, nets, 'GND')
c2 = place(board, load_fp('Capacitor_SMD','C_0805_2012Metric'),
           'C2', '10uF', 148, 45, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(c2, 1, nets, 'VCC_3V3'); assign(c2, 2, nets, 'GND')

# Latch decoupling
for ref, x in [('C3', 28), ('C4', 68), ('C5', 108)]:
    c = place(board, load_fp('Capacitor_SMD','C_0402_1005Metric'),
              ref, '100nF', x, 62, text_size=0.4, ref_layer=pcbnew.F_Fab)
    assign(c, 1, nets, 'VCC'); assign(c, 2, nets, 'GND')

# ════════════════════════════════════════════
# PULL-UPS / PULL-DOWNS for bus safety
# ════════════════════════════════════════════
# PDTACK pull-down (active = acknowledge bus cycle)
r_pd = place(board, load_fp('Resistor_SMD','R_0402_1005Metric'),
             f'R{ri}', '1K', 70, 30, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(r_pd, 1, nets, 'PDTACK'); assign(r_pd, 2, nets, 'GND')
ri += 1
add_text(board, 'PDTACK\nPULL-DN', 70, 26, size=0.6, thickness=0.08)

# ROMWAIT pull-up (inactive = no wait states)
r_rw = place(board, load_fp('Resistor_SMD','R_0402_1005Metric'),
             f'R{ri}', '10K', 77, 30, text_size=0.4, ref_layer=pcbnew.F_Fab)
assign(r_rw, 1, nets, 'VCC'); assign(r_rw, 2, nets, 'ROMWAIT')
ri += 1

# ════════════════════════════════════════════
# SILKSCREEN
# ════════════════════════════════════════════
add_text(board, 'NEOCART PROG BREAKOUT', 87, 84, size=2.0, thickness=0.25)
add_text(board, 'NeoScanSDK', 87, 88, size=1.0, thickness=0.1)
add_text(board, 'ADDRESS BUS', 87, LED_Y - 7, size=1.2, thickness=0.12)
add_text(board, 'ACTIVE', 157, LED_Y - 7, size=0.8, thickness=0.1)
add_text(board, '5V LOGIC — USE PROTECTION FOR 3.3V DEVICES', 87, 95,
         size=1.0, thickness=0.12)

# Gold finger labels
for pin, (a_sig, b_sig) in CTRG2.items():
    x = GF_X_START + (pin-1) * 2.54
    if a_sig != 'NC':
        add_text(board, a_sig, x, 121, size=0.8, thickness=0.1, angle=90, layer=pcbnew.F_SilkS)
    if b_sig != 'NC':
        add_text(board, b_sig, x, 121, size=0.8, thickness=0.1, angle=90, layer=pcbnew.B_SilkS)

# ════════════════════════════════════════════
# GND ZONES
# ════════════════════════════════════════════
for layer in [pcbnew.F_Cu, pcbnew.B_Cu]:
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(False); z.SetLayer(layer); z.SetNet(nets['GND'])
    ol = z.Outline(); ol.NewOutline()
    ol.Append(MM(0),MM(0)); ol.Append(MM(174),MM(0))
    ol.Append(MM(174),MM(134)); ol.Append(MM(0),MM(134))
    z.SetMinThickness(MM(0.2)); z.SetThermalReliefSpokeWidth(MM(0.5))
    board.Add(z)

# ════════════════════════════════════════════
# SAVE + VERIFY + RENDER
# ════════════════════════════════════════════
pcb_path = os.path.join(OUT_DIR, 'prog_breakout.kicad_pcb')
pcbnew.SaveBoard(pcb_path, board)
fp_count = len(board.GetFootprints())
net_count = board.GetNetCount()
print(f"  {fp_count} footprints, {net_count} nets")
print(f"  {ri-1} resistors, 23 LEDs, 3 latches, 2 buttons")
print(f"  Saved: {pcb_path}")

# Export DSN for routing
pcbnew.ExportSpecctraDSN(board, os.path.join(OUT_DIR, 'prog_breakout.dsn'))
print("  Exported prog_breakout.dsn")

# Render
print("  Rendering...")
from PIL import Image, ImageDraw
views, labels = [], []
for side in ['top', 'bottom']:
    png = os.path.join(OUT_DIR, f'prog_breakout_{side}.png')
    os.system(f'kicad-cli pcb render "{pcb_path}" -o "{png}" --side {side} --width 1920 --height 1440 2>/dev/null')
    views.append(png); labels.append(f'BREAKOUT {side}')
imgs = [Image.open(v) for v in views]
w, h = imgs[0].size
comp = Image.new('RGB', (w*2, h), (30,30,30))
for i, (img, lbl) in enumerate(zip(imgs, labels)):
    comp.paste(img, (i*w, 0))
    ImageDraw.Draw(comp).text((i*w+10, 10), lbl, fill=(255,255,0))
comp.save(os.path.join(OUT_DIR, 'prog_breakout_views.png'))
print("  Saved prog_breakout_views.png")
print("Done!")
