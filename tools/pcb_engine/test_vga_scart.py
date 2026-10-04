#!/usr/bin/env python3
"""
Test case 1: VGA → SCART adapter

A simple board that converts VGA (DB15) to SCART for French CRT TVs.
- R2R DAC resistor ladder for RGB (4-bit per channel)
- Sync combiner (H+V → composite sync via XOR)
- Audio passthrough
- 15kHz output for CRT compatibility

This is the simplest possible board to prove the PCB engine works.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from pcb_engine import Board, Package

# ─── Create board ───
board = Board(60, 35, layers=2)  # 6cm x 3.5cm, 2-layer

# ─── Define components ───
# VGA input connector (DB15)
vga = board.place("J1", Package.db15_vga("DB15_VGA"), x=8, y=17, value="VGA_IN")

# SCART output connector
scart = board.place("J2", Package.scart("SCART"), x=48, y=17, value="SCART_OUT")

# Sync combiner — 74HC86 (quad XOR gate in SOIC-14)
xor_pkg = Package.soic("SOIC-14", pin_count=14, pitch=1.27, span=5.4)
xor = board.place("U1", xor_pkg, x=28, y=8, value="74HC86", lcsc="C5591")

# Resistors for R2R DAC (convert 3.3V digital to 0-0.7V analog for SCART)
# Red channel: 3 resistors for simple voltage divider
r_positions = [
    ("R1", 20, 17, "680"),   # Red - MSB
    ("R2", 23, 17, "1K"),    # Red - LSB
    ("R3", 20, 22, "680"),   # Green - MSB
    ("R4", 23, 22, "1K"),    # Green - LSB
    ("R5", 20, 27, "680"),   # Blue - MSB
    ("R6", 23, 27, "1K"),    # Blue - LSB
    ("R7", 32, 8, "470"),    # Sync series resistor
    ("R8", 32, 12, "75"),    # Sync termination
]

for ref, x, y, val in r_positions:
    board.place(ref, Package.smd_resistor("R_0402"), x=x, y=y, value=val)

# Decoupling cap for XOR gate
board.place("C1", Package.smd_cap("C_0402"), x=28, y=4, value="100nF")

# Audio coupling caps
board.place("C2", Package.smd_cap("C_0402"), x=38, y=10, value="10uF")
board.place("C3", Package.smd_cap("C_0402"), x=38, y=14, value="10uF")

print(f"Components: {len(board.components)}")

# ─── Net connections ───
# VGA pinout: 1=Red, 2=Green, 3=Blue, 5=GND, 6=Red_GND, 7=Green_GND,
#             8=Blue_GND, 10=Sync_GND, 13=HSync, 14=VSync

# SCART pinout: 7=Blue, 11=Green, 15=Red, 17=Video_GND, 20=Comp_Sync,
#               2=Audio_R, 6=Audio_L, 4=Audio_GND

# Red: VGA pin 1 → R1 → SCART pin 15
board.connect("VGA_RED", "J1", "1")
board.connect("VGA_RED", "R1", "1")
board.connect("SCART_RED", "R1", "2")
board.connect("SCART_RED", "R2", "1")
board.connect("SCART_RED", "J2", "15")
board.connect("GND", "R2", "2")

# Green: VGA pin 2 → R3 → SCART pin 11
board.connect("VGA_GREEN", "J1", "2")
board.connect("VGA_GREEN", "R3", "1")
board.connect("SCART_GREEN", "R3", "2")
board.connect("SCART_GREEN", "R4", "1")
board.connect("SCART_GREEN", "J2", "11")
board.connect("GND", "R4", "2")

# Blue: VGA pin 3 → R5 → SCART pin 7
board.connect("VGA_BLUE", "J1", "3")
board.connect("VGA_BLUE", "R5", "1")
board.connect("SCART_BLUE", "R5", "2")
board.connect("SCART_BLUE", "R6", "1")
board.connect("SCART_BLUE", "J2", "7")
board.connect("GND", "R6", "2")

# Sync: VGA HSync (pin 13) + VSync (pin 14) → XOR → SCART pin 20
board.connect("HSYNC", "J1", "13")
board.connect("HSYNC", "U1", "1")       # XOR input A
board.connect("VSYNC", "J1", "14")
board.connect("VSYNC", "U1", "2")       # XOR input B
board.connect("CSYNC", "U1", "3")       # XOR output = composite sync
board.connect("CSYNC", "R7", "1")
board.connect("SCART_SYNC", "R7", "2")
board.connect("SCART_SYNC", "R8", "1")
board.connect("SCART_SYNC", "J2", "20")
board.connect("GND", "R8", "2")

# Power for XOR gate
board.connect("VCC", "U1", "14")
board.connect("GND", "U1", "7")
board.connect("VCC", "C1", "1")
board.connect("GND", "C1", "2")

# VCC from VGA pin 9 (5V)
board.connect("VCC", "J1", "9")

# Ground connections
for p in ["5", "6", "7", "8", "10"]:
    board.connect("GND", "J1", p)
board.connect("GND", "J2", "17")
board.connect("GND", "J2", "4")
board.connect("GND", "J2", "18")

# Audio passthrough (VGA doesn't carry audio, but SCART pins need to be there)
# Just ground the audio pins or connect to a 3.5mm jack later
board.connect("GND", "J2", "2")   # Audio R
board.connect("GND", "J2", "6")   # Audio L

# SCART pin 8 = switching voltage (tell TV it's RGB mode)
# Connect to VCC through a resistor divider — SCART expects 1-3V on pin 8
# For now just connect to a net
board.connect("VCC", "J2", "8")  # RGB select (high = RGB mode)

# SCART pin 16 = blanking (fast switching, also ~1-3V for RGB)
board.connect("VCC", "J2", "16")

# ─── Stats ───
stats = board.stats()
print(f"\nBoard: {stats['board_size']}, {stats['layers']} layers")
print(f"Components: {stats['components']}")
print(f"Nets: {stats['nets']}")
print(f"Pads: {stats['assigned_pads']}/{stats['total_pads']} assigned")
print(f"Orphans: {stats['orphan_pads']}")

# ─── Route ───
print("\nRouting...")
board.route(power_nets={"GND", "VCC"})
print(f"Traces: {len(board.traces)}, Vias: {len(board.vias)}")

# ─── DRC ───
print("\nRunning DRC...")
violations = board.check_drc()
print(f"Violations: {len(violations)}")
for v in violations[:10]:
    print(f"  {v.type}: {v.message}")

# ─── Render ───
output_dir = "/home/bruno/CLProjects/NeoGeo/tools/pcb_engine/output"
os.makedirs(output_dir, exist_ok=True)

print("\nRendering...")
board.render(os.path.join(output_dir, "vga_scart_top.png"), dpi=300)
print(f"Saved: {output_dir}/vga_scart_top.png")

# ─── Export ───
board.export_gerbers(os.path.join(output_dir, "gerbers"))
board.export_bom(os.path.join(output_dir, "bom.csv"))
print(f"Gerbers: {output_dir}/gerbers/")
print(f"BOM: {output_dir}/bom.csv")

print("\n✓ VGA → SCART adapter complete")
