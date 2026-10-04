#!/usr/bin/env python3
"""
MVS Dev Cart Adapter Board

Connects a QMTech Wukong FPGA board to the MVS PROG slot.
- 40-pin header (from Wukong J12) → level shifters → MVS gold fingers
- Clean, well-spaced layout inspired by the KOF96 PROG board

This board is SIMPLE:
  - No FPGA (that's on the Wukong)
  - No SDRAM (that's on the Wukong)
  - No USB (that's on the Wukong)
  - Just: pin header + 2x 74LVC245 + series resistors + gold fingers

The board shape uses the proven MVS cart outline from the neogeo-diag project.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from pcb_engine import Board, Package

# ─── Board: MVS cart dimensions ───
# 174mm x 134mm, gold fingers at bottom, proven outline
board = Board(174, 134, layers=2)

# ─── Components ───

# 40-pin header — connects to Wukong J12 via ribbon cable
hdr = board.place("J1", Package.pin_header_2x20("HDR_2x20"), x=87, y=25,
                  value="TO_WUKONG")

# 74LVC245 #1 — level shifter for data bus D0-D7
u1 = board.place("U1", Package.soic20w("SOIC-20W"), x=65, y=60,
                 value="74LVC245", lcsc="C5949")

# 74LVC245 #2 — level shifter for data bus D8-D15
u2 = board.place("U2", Package.soic20w("SOIC-20W"), x=110, y=60,
                 value="74LVC245", lcsc="C5949")

# Series resistors — address bus (PA0-PA17) — 5V protection
# Spread evenly across the board, like KOF96's resistor row
for i in range(18):
    x = 20 + i * 7.5
    board.place(f"RA{i}", Package.smd_resistor("R_0402"), x=x, y=85,
                value="470", lcsc="C25117")

# Control signal resistors (ROMOE, ROMOEU, ROMOEL, nRW)
for i, name in enumerate(["ROMOE", "ROMOEU", "ROMOEL", "nRW"]):
    board.place(f"RC{i}", Package.smd_resistor("R_0402"), x=20 + i * 10, y=92,
                value="470", lcsc="C25117")

# Decoupling caps — one per 245
board.place("C1", Package.smd_cap("C_0402"), x=60, y=52, value="100nF", lcsc="C1525")
board.place("C2", Package.smd_cap("C_0402"), x=105, y=52, value="100nF", lcsc="C1525")

# Bulk cap near power entry
board.place("C3", Package.smd_cap("C_0402"), x=87, y=18, value="10uF", lcsc="C15850")

# MVS PROG edge connector — gold fingers at the bottom
# 60 pins, 2.54mm pitch, A-side and B-side
j2 = board.place("J2", Package.gold_fingers("CTRG2_A", 60, 2.54), x=87, y=127,
                  value="CTRG2_A")
j3 = board.place("J3", Package.gold_fingers("CTRG2_B", 60, 2.54), x=87, y=127,
                  value="CTRG2_B")

print(f"Components placed: {len(board.components)}")

# ─── Net connections ───

# Power
board.connect("VCC_5V", "J1", "1")   # Pin 1 = 3.3V from Wukong
board.connect("GND", "J1", "2")      # Pin 2 = GND
board.connect("VCC_5V", "U1", "20")
board.connect("VCC_5V", "U2", "20")
board.connect("GND", "U1", "10")
board.connect("GND", "U2", "10")
board.connect("VCC_5V", "C1", "1")
board.connect("GND", "C1", "2")
board.connect("VCC_5V", "C2", "1")
board.connect("GND", "C2", "2")
board.connect("VCC_5V", "C3", "1")
board.connect("GND", "C3", "2")

# Connector power/ground
for p in ["A1", "A2", "A3", "A4", "A59", "A60"]:
    board.connect("GND", "J2", p)
for p in ["B1", "B2", "B3", "B4", "B59", "B60"]:
    board.connect("GND", "J3", p)
for p in ["A29", "A30", "A31", "A32"]:
    board.connect("VCC_5V", "J2", p)
for p in ["B29", "B30", "B31", "B32"]:
    board.connect("VCC_5V", "J3", p)

# BUS_DIR — directly from Wukong header pin to 245 DIR pins
board.connect("BUS_DIR", "J1", "3")
board.connect("BUS_DIR", "U1", "1")
board.connect("BUS_DIR", "U2", "1")

# OE — active low, tie to GND (always enabled)
board.connect("GND", "U1", "19")
board.connect("GND", "U2", "19")

# Data bus D0-D7: CTRG2 A5-A12 → 245 U1 A-side → 245 U1 B-side → header
for i in range(8):
    bus_net = f"PD{i}"
    fpga_net = f"FD{i}"
    # Connector → 245 A-side (5V)
    board.connect(bus_net, "J2", f"A{5+i}")
    board.connect(bus_net, "U1", str(2+i))
    # 245 B-side → header (3.3V to Wukong)
    board.connect(fpga_net, "U1", str(18-i))
    board.connect(fpga_net, "J1", str(4+i))  # header pins 4-11

# Data bus D8-D15: CTRG2 A13-A20 → 245 U2
for i in range(8):
    bus_net = f"PD{8+i}"
    fpga_net = f"FD{8+i}"
    board.connect(bus_net, "J2", f"A{13+i}")
    board.connect(bus_net, "U2", str(2+i))
    board.connect(fpga_net, "U2", str(18-i))
    board.connect(fpga_net, "J1", str(12+i))  # header pins 12-19

# Address bus PA0-PA17: CTRG2 B5-B22 → series resistors → header
for i in range(18):
    bus_net = f"PA{i}"
    board.connect(bus_net, "J3", f"B{5+i}")
    board.connect(bus_net, f"RA{i}", "1")
    board.connect(bus_net, f"RA{i}", "2")  # same net both sides (inline)
    board.connect(bus_net, "J1", str(20+i))  # header pins 20-37

# Control signals: through series resistors → header
ctrl_map = [
    ("ROMOE", "A33", "RC0", "38"),
    ("ROMOEU", "A23", "RC1", "39"),
    ("ROMOEL", "A24", "RC2", "40"),
]
for net, conn_pin, res_ref, hdr_pin in ctrl_map:
    board.connect(net, "J2", conn_pin)
    board.connect(net, res_ref, "1")
    board.connect(net, res_ref, "2")
    board.connect(net, "J1", hdr_pin)

# nRW — directly to header (no resistor needed, it's a read signal)
board.connect("nRW", "J2", "A21")
board.connect("nRW", "RC3", "1")
board.connect("nRW", "RC3", "2")

# ─── Stats ───
stats = board.stats()
print(f"\nBoard: {stats['board_size']}, {stats['layers']} layers")
print(f"Components: {stats['components']}")
print(f"Nets: {stats['nets']}")
print(f"Pads assigned: {stats['assigned_pads']}/{stats['total_pads']}")
print(f"Orphans: {stats['orphan_pads']}")

# ─── Route ───
print("\nRouting...")
routed, failed = board.route(power_nets={"GND", "VCC_5V"})
print(f"Routed: {routed}, Failed: {failed}")
print(f"Traces: {len(board.traces)}, Vias: {len(board.vias)}")

# ─── DRC ───
violations = board.check_drc()
orphan_violations = [v for v in violations if v.type == "orphan_pad"]
other_violations = [v for v in violations if v.type != "orphan_pad"]
print(f"\nDRC: {len(other_violations)} violations, {len(orphan_violations)} unused connector pins")

# ─── Render ───
output_dir = "/home/bruno/CLProjects/NeoGeo/tools/pcb_engine/output"
os.makedirs(output_dir, exist_ok=True)
board.render(os.path.join(output_dir, "mvs_adapter_top.png"), dpi=200)
print(f"\nRendered: mvs_adapter_top.png")

# ─── Export ───
board.export_gerbers(os.path.join(output_dir, "mvs_gerbers"))
board.export_bom(os.path.join(output_dir, "mvs_bom.csv"))
print(f"Gerbers: {output_dir}/mvs_gerbers/")
print(f"BOM: {output_dir}/mvs_bom.csv")

print("\n✓ MVS adapter board complete")
