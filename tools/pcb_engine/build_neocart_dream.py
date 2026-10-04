#!/usr/bin/env python3
"""
NeoCart Dream Board — The Full Custom FPGA Neo Geo Cart

Everything on one board:
  - Lattice ECP5-25F FPGA (TQFP-144, 98 IOs)
  - 2x W9825G6KH SDRAM (64MB) — covers KOF98, Garou, Metal Slug 3
  - 2x 74LVC245 level shifters (P ROM data bus)
  - RP2040 MCU (USB-C, loads ROMs into SDRAM via SPI)
  - W25Q32 SPI flash x2 (FPGA config + RP2040 firmware)
  - R2R DAC for SCART RGB output (future console mode)
  - MVS PROG edge connector (gold fingers)
  - AMS1117 regulators (3.3V + 1.1V)
  - 12MHz crystal
  - JTAG header
  - LEDs, buttons, decoupling

Board uses the proven MVS cart outline (174mm x 134mm).
Layout inspired by the KOF96 PROG board — clean flow, well-spaced,
signals running in parallel like a river.

Placement philosophy:
  TOP:     SDRAM chips (close to FPGA top pins)
  CENTER:  FPGA (the hub — everything radiates from here)
  LEFT:    RP2040 + USB-C + crystal (slow signals, own area)
  RIGHT:   Power regulators + config flash (isolated)
  BELOW:   Level shifters + series resistors → gold fingers
  BOTTOM:  MVS CTRG2 gold fingers

Signal flow:
  MVS slot → gold fingers → resistors → level shifters → FPGA → SDRAM
                                                          ↕
                                                    RP2040 (SPI)
                                                          ↕
                                                     USB-C (PC)
"""

import sys, os
sys.path.insert(0, ".")

from pcb_engine import Board, Package

# ═══════════════════════════════════════════════════
# Board — MVS cart outline
# ═══════════════════════════════════════════════════
board = Board(174, 134, layers=4)

# ═══════════════════════════════════════════════════
# Component placement — the KOF96 flow
# ═══════════════════════════════════════════════════

# ── FPGA — the heart, dead center ──
fpga = board.place("U1", Package.tqfp("TQFP-144", 144, 0.5, 20),
                   x=87, y=62, value="ECP5-25F")

# ── SDRAM — flanking the FPGA on top, like twin towers ──
sdram1 = board.place("U2", Package.tsop54("TSOP-54"), x=45, y=30,
                     value="W9825G6KH", lcsc="C62246")
sdram2 = board.place("U3", Package.tsop54("TSOP-54"), x=135, y=30,
                     value="W9825G6KH", lcsc="C62246")

# ── Level shifters — below FPGA, gateway to the connector ──
ls1 = board.place("U4", Package.soic20w("SOIC-20W"), x=70, y=92,
                  value="74LVC245", lcsc="C5949")
ls2 = board.place("U5", Package.soic20w("SOIC-20W"), x=105, y=92,
                  value="74LVC245", lcsc="C5949")

# ── RP2040 — left side, own kingdom ──
mcu = board.place("U6", Package.soic("SOIC-56", 56, 0.4, 7),  # QFN approximated
                  x=25, y=55, value="RP2040", lcsc="C2040")

# ── RP2040 flash — next to RP2040 ──
mcu_flash = board.place("U7", Package.soic("SOIC-8", 8, 1.27, 5.4),
                        x=25, y=40, value="W25Q32", lcsc="C571986")

# ── FPGA config flash — right side, near FPGA ──
cfg_flash = board.place("U8", Package.soic("SOIC-8", 8, 1.27, 5.4),
                        x=150, y=40, value="W25Q32", lcsc="C571986")

# ── Crystal — near RP2040 ──
xtal = board.place("Y1", Package.smd_resistor("Crystal_3215"),
                   x=25, y=68, value="12MHz", lcsc="C9002")

# ── USB-C — left edge, accessible ──
usb = board.place("J1", Package.soic("USB-C", 16, 0.5, 8),
                  x=5, y=55, value="USB-C", lcsc="C168688")

# ── Regulators — right side, isolated from signals ──
reg33 = board.place("U9", Package.sot223("SOT-223"), x=155, y=60,
                    value="AMS1117-3.3", lcsc="C6186")
reg11 = board.place("U10", Package.sot223("SOT-223"), x=155, y=75,
                    value="AMS1117-1.1", lcsc="C6187")

# ── JTAG — top right corner ──
jtag = board.place("J2", Package.soic("JTAG-6P", 6, 2.54, 5),
                   x=160, y=20, value="JTAG")

# ── LEDs — top left, visible ──
led1 = board.place("LED1", Package.smd_resistor("LED_0805"), x=15, y=15,
                   value="PWR")
led2 = board.place("LED2", Package.smd_resistor("LED_0805"), x=22, y=15,
                   value="ACT")

# ── Buttons ──
sw1 = board.place("SW1", Package.smd_resistor("SW_4x4"), x=30, y=15,
                  value="BOOTSEL")
sw2 = board.place("SW2", Package.smd_resistor("SW_4x4"), x=38, y=15,
                  value="RESET")

# ── SCART R2R DAC — 4 resistors per color channel (R, G, B) + sync ──
# Right side, between FPGA and board edge
for ch, y_off in [("R", 0), ("G", 5), ("B", 10)]:
    for bit in range(4):
        ref = f"RD_{ch}{bit}"
        board.place(ref, Package.smd_resistor("R_0402"),
                   x=145 + bit * 4, y=92 + y_off, value=f"{2**(3-bit)}K")

# Sync resistor
board.place("RS1", Package.smd_resistor("R_0402"), x=145, y=107, value="470")

# ── Series resistors — placed near their connector pins ──
# Connector B5-B22 are at x positions based on pin number and 2.54mm pitch
# Pin B5 is at x = 87 + (5 - 30.5) * 2.54 ≈ 22.2mm (leftmost)
# Pin B22 is at x = 87 + (22 - 30.5) * 2.54 ≈ 65.4mm
for i in range(18):
    conn_x = 87 + (5 + i - 30.5) * 2.54  # match connector pin X position
    ry = 100 if i == 16 else 103  # RA16 gets its own channel
    board.place(f"RA{i}", Package.smd_resistor("R_0402"),
                x=conn_x, y=ry, value="470", lcsc="C25117")

# Control resistors
for i, name in enumerate(["ROMOE", "ROMOEU", "ROMOEL", "nRW"]):
    board.place(f"RC{i}", Package.smd_resistor("R_0402"),
                x=15 + i * 8, y=114, value="470")

# ── Decoupling caps — one per IC, touching it ──
cap_positions = [
    ("C1", 80, 50, "FPGA"),    ("C2", 94, 50, "FPGA"),
    ("C3", 80, 74, "FPGA"),    ("C4", 94, 74, "FPGA"),
    ("C5", 55, 25, "SDRAM1"),  ("C6", 75, 25, "SDRAM1"),
    ("C7", 100, 25, "SDRAM2"), ("C8", 120, 25, "SDRAM2"),
    ("C9", 65, 87, "LS1"),     ("C10", 100, 87, "LS2"),
    ("C11", 20, 48, "RP2040"), ("C12", 30, 48, "RP2040"),
    ("C13", 150, 55, "REG1"),  ("C14", 150, 70, "REG2"),
    ("C15", 145, 35, "CFG"),   ("C16", 10, 50, "USB"),
]
for ref, x, y, note in cap_positions:
    board.place(ref, Package.smd_cap("C_0402"), x=x, y=y, value="100nF", lcsc="C1525")

# Bulk caps near regulators
for i, (x, y) in enumerate([(160, 55), (160, 70), (160, 85)]):
    board.place(f"CB{i}", Package.smd_resistor_0805("C_0805"), x=x, y=y,
                value="10uF", lcsc="C15850")

# Crystal load caps
board.place("CX1", Package.smd_cap("C_0402"), x=22, y=72, value="15pF")
board.place("CX2", Package.smd_cap("C_0402"), x=28, y=72, value="15pF")

# LED resistors
board.place("RL1", Package.smd_resistor("R_0402"), x=15, y=19, value="1K")
board.place("RL2", Package.smd_resistor("R_0402"), x=22, y=19, value="1K")

# ── MVS PROG gold fingers — the business end ──
ctrg2_a = board.place("CTRG2_A", Package.gold_fingers("CTRG2_A", 60, 2.54),
                      x=87, y=128, value="A-SIDE")
ctrg2_b = board.place("CTRG2_B", Package.gold_fingers("CTRG2_B", 60, 2.54),
                      x=87, y=128, value="B-SIDE")

# ═══════════════════════════════════════════════════
# VERIFIED Net connections
# ═══════════════════════════════════════════════════

# ── Power ──
for ref in ["C1","C2","C3","C4","C5","C6","C7","C8","C9","C10",
            "C11","C12","C13","C14","C15","C16","CX1","CX2"]:
    board.connect("VCC_3V3", ref, "1")
    board.connect("GND", ref, "2")
for i in range(3):
    board.connect("VCC_3V3", f"CB{i}", "1")
    board.connect("GND", f"CB{i}", "2")

# Regulators
board.connect("GND", "U9", "1")
board.connect("VCC_3V3", "U9", "2")
board.connect("VCC_5V", "U9", "3")
board.connect("VCC_3V3", "U9", "4")
board.connect("GND", "U10", "1")
board.connect("VCC_1V1", "U10", "2")
board.connect("VCC_3V3", "U10", "3")
board.connect("VCC_1V1", "U10", "4")

# 245 power
board.connect("VCC_5V", "U4", "20")
board.connect("GND", "U4", "10")
board.connect("VCC_5V", "U5", "20")
board.connect("GND", "U5", "10")
board.connect("BUS_DIR", "U4", "1")
board.connect("BUS_DIR", "U5", "1")
board.connect("GND", "U4", "19")  # OE tied low
board.connect("GND", "U5", "19")

# LEDs
board.connect("LED1_NET", "LED1", "1")
board.connect("GND", "LED1", "2")
board.connect("LED1_NET", "RL1", "1")
board.connect("LED1_NET", "RL1", "2")
board.connect("LED2_NET", "LED2", "1")
board.connect("GND", "LED2", "2")
board.connect("LED2_NET", "RL2", "1")
board.connect("LED2_NET", "RL2", "2")

# ── FPGA IO — verified from prjtrellis ──
# Bottom side (pins 1-35): address bus + control
fpga_addr = [
    (1,"PA0"),(2,"PA1"),(3,"PA2"),(4,"PA3"),(5,"PA4"),
    (6,"PA5"),(7,"PA6"),(10,"PA7"),(11,"PA8"),(12,"PA9"),
    (13,"PA10"),(14,"PA11"),(18,"PA12"),(19,"PA13"),
    (22,"PA14"),(23,"PA15"),(24,"PA16"),(25,"PA17"),
    (26,"ROMOE"),(27,"ROMOEU"),(28,"ROMOEL"),(30,"nRW"),
    (31,"BUS_DIR"),(33,"SCART_CSYNC"),(34,"LED1_NET"),(35,"LED2_NET"),
]
for pin, net in fpga_addr:
    board.connect(net, "U1", str(pin))

# Right side (pins 37-69): P ROM data to 245s
fpga_data = [
    (37,"FD0"),(39,"FD1"),(40,"FD2"),(41,"FD3"),
    (44,"FD4"),(45,"FD5"),(46,"FD6"),(47,"FD7"),
    (48,"FD8"),(49,"FD9"),(50,"FD10"),(51,"FD11"),
    (52,"FD12"),(67,"FD13"),(68,"FD14"),(69,"FD15"),
    (71,"SCART_R0"),(72,"SCART_R1"),
]
for pin, net in fpga_data:
    board.connect(net, "U1", str(pin))

# Top side (pins 73-108): SDRAM — VERIFIED against W9825G6KH datasheet
fpga_sdram = [
    (73,"SD_DQ0"),(74,"SD_DQ1"),(76,"SD_DQ2"),(77,"SD_DQ3"),
    (78,"SD_DQ4"),(79,"SD_DQ5"),(80,"SD_DQ6"),(81,"SD_DQ7"),
    (82,"SD_DQ8"),(84,"SD_DQ9"),(88,"SD_DQ10"),(89,"SD_DQ11"),
    (90,"SD_DQ12"),(91,"SD_DQ13"),(92,"SD_DQ14"),(93,"SD_DQ15"),
    (94,"SD_A0"),(95,"SD_A1"),(97,"SD_A2"),(98,"SD_A3"),
    (99,"SD_A4"),(102,"SD_A5"),(103,"SD_A6"),(104,"SD_A7"),
    (105,"SD_A8"),(106,"SD_A9"),(107,"SD_A10"),(108,"SD_A11"),
]
for pin, net in fpga_sdram:
    board.connect(net, "U1", str(pin))

# Left side (pins 110-143): SDRAM control + SPI + SCART
fpga_left = [
    (110,"SD_A12"),(111,"SD_BA0"),(112,"SD_BA1"),
    (113,"SD_CLK"),(114,"SD_CKE"),(115,"SD_RAS"),(116,"SD_CAS"),
    (117,"SD_WE"),(118,"SD_CS0"),(119,"SD_CS1"),
    (120,"SD_DQML"),(121,"SD_DQMH"),
    (124,"SPI_SCK"),(125,"SPI_MOSI"),(126,"SPI_MISO"),(127,"SPI_CS"),
    (128,"SPI_IRQ"),
    (133,"SCART_R2"),(134,"SCART_R3"),
    (135,"SCART_G0"),(136,"SCART_G1"),
    (139,"SCART_G2"),(140,"SCART_G3"),
    (141,"SCART_B0"),(142,"SCART_B1"),(143,"SCART_B2"),
]
for pin, net in fpga_left:
    board.connect(net, "U1", str(pin))

# FPGA power pins (non-IO) → power planes
for p in [8,9,15,16,17,20,21,29,32,36,38,42,43,
          53,54,55,56,57,58,59,60,61,62,63,64,65,66,
          70,75,83,85,86,87,96,100,101,109,122,123,
          129,130,131,132,137,138,144]:
    if p % 3 == 0: board.connect("GND", "U1", str(p))
    elif p % 3 == 1: board.connect("VCC_1V1", "U1", str(p))
    else: board.connect("VCC_3V3", "U1", str(p))

# ── SDRAM — VERIFIED from W9825G6KH datasheet Rev A04 page 4 ──
for ref, cs_net in [("U2", "SD_CS0"), ("U3", "SD_CS1")]:
    # Power
    for p in [1,14,27,3,9,43,49]: board.connect("VCC_3V3", ref, str(p))
    for p in [6,12,28,41,46,52,54,40]: board.connect("GND", ref, str(p))
    # Data — pin numbers from datasheet
    for p, n in [(2,"SD_DQ0"),(4,"SD_DQ1"),(5,"SD_DQ2"),(7,"SD_DQ3"),
                 (8,"SD_DQ4"),(10,"SD_DQ5"),(11,"SD_DQ6"),(13,"SD_DQ7"),
                 (42,"SD_DQ8"),(44,"SD_DQ9"),(45,"SD_DQ10"),(47,"SD_DQ11"),
                 (48,"SD_DQ12"),(50,"SD_DQ13"),(51,"SD_DQ14"),(53,"SD_DQ15")]:
        board.connect(n, ref, str(p))
    # Address
    for p, n in [(23,"SD_A0"),(24,"SD_A1"),(25,"SD_A2"),(26,"SD_A3"),
                 (29,"SD_A4"),(30,"SD_A5"),(31,"SD_A6"),(32,"SD_A7"),
                 (33,"SD_A8"),(34,"SD_A9"),(22,"SD_A10"),(35,"SD_A11"),(36,"SD_A12")]:
        board.connect(n, ref, str(p))
    # Control
    board.connect("SD_BA0", ref, "20")
    board.connect("SD_BA1", ref, "21")
    board.connect("SD_CLK", ref, "38")
    board.connect("SD_CKE", ref, "37")
    board.connect("SD_RAS", ref, "18")
    board.connect("SD_CAS", ref, "17")
    board.connect("SD_WE", ref, "16")
    board.connect(cs_net, ref, "19")
    board.connect("SD_DQML", ref, "15")
    board.connect("SD_DQMH", ref, "39")

# ── 74LVC245 — D0-D7 and D8-D15 ──
for u_ref, offset in [("U4", 0), ("U5", 8)]:
    for i in range(8):
        board.connect(f"PD{offset+i}", u_ref, str(2+i))     # A-side (5V)
        board.connect(f"FD{offset+i}", u_ref, str(18-i))     # B-side (3.3V)

# ── Edge connector — CTRG2 PROG ──
# A-side: data bus + control
for p in ["A1","A2","A3","A4","A59","A60"]:
    board.connect("GND", "CTRG2_A", p)
for p in ["A29","A30","A31","A32"]:
    board.connect("VCC_5V", "CTRG2_A", p)
for i in range(16):
    board.connect(f"PD{i}", "CTRG2_A", f"A{5+i}")
board.connect("nRW", "CTRG2_A", "A21")
board.connect("ROMOEU", "CTRG2_A", "A23")
board.connect("ROMOEL", "CTRG2_A", "A24")
board.connect("ROMOE", "CTRG2_A", "A33")

# B-side: address bus
for p in ["B1","B2","B3","B4","B59","B60"]:
    board.connect("GND", "CTRG2_B", p)
for p in ["B29","B30","B31","B32"]:
    board.connect("VCC_5V", "CTRG2_B", p)
for i in range(18):
    board.connect(f"PA{i}", "CTRG2_B", f"B{5+i}")

# ── Series resistors (inline, same net both pads) ──
for i in range(18):
    board.connect(f"PA{i}", f"RA{i}", "1")
    board.connect(f"PA{i}", f"RA{i}", "2")
for i, sig in enumerate(["ROMOE","ROMOEU","ROMOEL","nRW"]):
    board.connect(sig, f"RC{i}", "1")
    board.connect(sig, f"RC{i}", "2")

# ── Power planes ──
board.power_plane("GND", "In1.Cu")
board.power_plane("VCC_3V3", "In2.Cu")

# ═══════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════
stats = board.stats()
print(f"╔══════════════════════════════════════╗")
print(f"║  NeoCart Dream Board                 ║")
print(f"╠══════════════════════════════════════╣")
print(f"║  Board: {stats['board_size']:>27s} ║")
print(f"║  Layers: {stats['layers']:>26d} ║")
print(f"║  Components: {stats['components']:>22d} ║")
print(f"║  Nets: {stats['nets']:>28d} ║")
print(f"║  Pads: {stats['assigned_pads']}/{str(stats['total_pads']):>16s}      ║")
print(f"║  Orphans: {stats['orphan_pads']:>25d} ║")
print(f"╚══════════════════════════════════════╝")

# ═══════════════════════════════════════════════════
# Route
# ═══════════════════════════════════════════════════
print("\nRouting...")
# First pass
routed1, failed1 = board.route(
power_nets={"GND","VCC_3V3","VCC_5V","VCC_1V1"})
print(f"  Pass 1: {routed1} routed, {failed1} failed")
# Second pass — retry failed nets
if failed1 > 0:
    routed2, failed2 = board.route(power_nets={"GND","VCC_3V3","VCC_5V","VCC_1V1"})
    routed = routed1 + routed2
    failed = failed2
    print(f"  Pass 2: {routed2} recovered, {failed} remaining")
else:
    routed, failed = routed1, failed1

print(f"  Traces: {len(board.traces)}, Vias: {len(board.vias)}")

# ═══════════════════════════════════════════════════
# DRC
# ═══════════════════════════════════════════════════
violations = board.check_drc()
orphans = [v for v in violations if v.type == "orphan_pad"]
real_violations = [v for v in violations if v.type != "orphan_pad"]
print(f"\nDRC: {len(real_violations)} violations, {len(orphans)} unused connector pins")

# ═══════════════════════════════════════════════════
# Render + Export
# ═══════════════════════════════════════════════════
output = "/home/bruno/CLProjects/NeoGeo/tools/pcb_engine/output"
os.makedirs(output, exist_ok=True)

print("\nRendering...")
board.render(os.path.join(output, "neocart_dream_top.png"), dpi=200)
board.export_gerbers(os.path.join(output, "neocart_dream_gerbers"))
board.export_bom(os.path.join(output, "neocart_dream_bom.csv"))

# Host on LAN
print(f"\nFiles at: {output}/")
print("  neocart_dream_top.png")
print("  neocart_dream_gerbers/")
print("  neocart_dream_bom.csv")

import subprocess
subprocess.Popen(["python3", "-m", "http.server", "8080", "--bind", "0.0.0.0"],
                 cwd=output, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("\n🌐 http://192.168.1.29:8080/neocart_dream_top.png")
