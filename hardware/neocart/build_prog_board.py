#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — PROG Board Builder

Copies the EXACT board outline and edge connector footprints from the
proven neogeo-diag-mvs-prog project, then places our flash chips and
RP2040 programmer on top.

Board: PROG side only (P ROM + V1 + V2 + RP2040)
Pair with donor CHA board for C/S/M ROMs.

Uses pcbnew API to clone the proven geometry.
"""

import pcbnew
import os
import shutil

SOURCE_PCB = "/tmp/neogeo-diag-mvs-prog/hardware/neogeo-diag-mvs-prog.kicad_pcb"
SOURCE_LIB = "/tmp/neogeo-diag-mvs-prog/hardware/library/neogeo-diag/neogeo-diag.pretty"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PCB = os.path.join(OUT_DIR, "neocart_prog.kicad_pcb")

# Copy the footprint library so KiCad can find it
dst_lib = os.path.join(OUT_DIR, "footprints", "neogeo-diag.pretty")
if not os.path.exists(dst_lib):
    shutil.copytree(SOURCE_LIB, dst_lib)
    print(f"Copied connector library to {dst_lib}")

# ─── Step 1: Clone the source board (outline + connectors) ───
print("Loading source board...")
src = pcbnew.LoadBoard(SOURCE_PCB)

# Create a fresh board with the same outline
print("Creating new board with proven outline...")
board = pcbnew.NewBoard(OUT_PCB)
board.SetCopperLayerCount(4)

# Copy edge cuts (board outline)
for dwg in src.GetDrawings():
    if dwg.GetLayer() == pcbnew.Edge_Cuts:
        new_line = dwg.Duplicate()
        board.Add(new_line)
print("  Board outline copied")

# Copy edge connector footprints (J1 = B-side, J2 = A-side)
for fp in src.GetFootprints():
    ref = fp.GetReference()
    if ref in ("J1", "J2"):
        new_fp = fp.Duplicate()
        board.Add(new_fp)
        print(f"  Connector {ref} copied ({fp.GetPadCount()} pads)")

# ─── Step 2: Define all nets ───
print("\nCreating nets...")

# Power
power_nets = ["GND", "VCC_5V", "VCC_3V3", "VBUS"]

# P ROM signals (from CTRG2 PROG connector)
prom_nets = [f"PA{i}" for i in range(19)] + [f"PD{i}" for i in range(16)]
prom_ctrl = ["nCE_P", "nOE_P", "nWE_P", "ROMOE", "ROMOEU", "ROMOEL"]

# V ROM signals
vrom_nets = ([f"VA{i}" for i in range(18)] +
             [f"VD{i}" for i in range(16)] +  # V1 data
             ["nCE_V1", "nOE_V1", "nWE_V1",
              "nCE_V2", "nOE_V2", "nWE_V2"])

# Programmer signals
prog_nets = (["SR_SER", "SR_SRCLK", "SR_RCLK", "SR_nOE",
              "BUF_nOE", "BUS_DIR", "PROG_nWE", "PROG_nOE",
              "PROG_nCE_P", "PROG_nCE_V1", "PROG_nCE_V2", "PROG_nBYTE"] +
             [f"PRGD{i}" for i in range(8)] +
             [f"PRGA{i}" for i in range(24)] +
             ["SR_CHAIN_0", "SR_CHAIN_1"])

# USB/MCU
mcu_nets = ["USB_DP", "USB_DM", "QSPI_SS", "QSPI_SCLK",
            "QSPI_SD0", "QSPI_SD1", "XIN", "XOUT", "RUN", "nBYTE_FLASH"]

all_nets = power_nets + prom_nets + prom_ctrl + vrom_nets + prog_nets + mcu_nets

net_id = 1
for name in all_nets:
    net = pcbnew.NETINFO_ITEM(board, name, net_id)
    board.Add(net)
    net_id += 1
print(f"  {len(all_nets)} nets created")

# ─── Step 3: Place components ───
print("\nPlacing components...")

KICAD_FP = "/usr/share/kicad/footprints"
MM = pcbnew.FromMM

def place_footprint(board, lib_path, fp_name, ref, value, x_mm, y_mm, angle=0):
    """Load a footprint from library and place it on the board."""
    fp_file = os.path.join(lib_path, fp_name + ".kicad_mod")
    if not os.path.exists(fp_file):
        print(f"  WARNING: {fp_file} not found")
        return None

    fp = pcbnew.FootprintLoad(lib_path, fp_name)
    if not fp:
        print(f"  WARNING: could not load {fp_name}")
        return None

    fp.SetPosition(pcbnew.VECTOR2I(MM(x_mm), MM(y_mm)))
    fp.SetReference(ref)
    fp.SetValue(value)
    if angle:
        fp.SetOrientationDegrees(angle)
    board.Add(fp)
    print(f"  {ref:12s} ({value}) at ({x_mm:.1f}, {y_mm:.1f})")
    return fp

# Board area: X=52.75-226.75, Y=23.75-138.75 (main body)
# Finger area: Y=138.75-157.75
# Components go in main body area

# Flash chips — upper area, close to connector
place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "TSOP-I-48_18.4x12mm_P0.5mm", "U_PROM", "AM29F400_P",
    140, 70)

place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "TSOP-I-48_18.4x12mm_P0.5mm", "U_V1", "AM29F400_V1",
    100, 70)

place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "TSOP-I-48_18.4x12mm_P0.5mm", "U_V2", "AM29F400_V2",
    180, 70)

# Shift registers — middle
place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "SOIC-16_3.9x9.9mm_P1.27mm", "U_SR1", "74HC595",
    80, 95)

place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "SOIC-16_3.9x9.9mm_P1.27mm", "U_SR2", "74HC595",
    100, 95)

place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "SOIC-16_3.9x9.9mm_P1.27mm", "U_SR3", "74HC595",
    120, 95)

# Bus buffers
place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "SOIC-20W_7.5x12.8mm_P1.27mm", "U_BUF1", "74HC245_DATA",
    150, 95)

place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "SOIC-20W_7.5x12.8mm_P1.27mm", "U_BUF2", "74HC245_CTRL",
    180, 95)

# RP2040 + support — lower area
place_footprint(board, f"{KICAD_FP}/Package_DFN_QFN.pretty",
    "QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm", "U_MCU", "RP2040",
    100, 55)

place_footprint(board, f"{KICAD_FP}/Package_SO.pretty",
    "SOIC-8_3.9x4.9mm_P1.27mm", "U_FLASH", "W25Q32",
    120, 48)

place_footprint(board, f"{KICAD_FP}/Crystal.pretty",
    "Crystal_SMD_3215-2Pin_3.2x1.5mm", "Y1", "12MHz",
    112, 48)

# LDO regulator
place_footprint(board, f"{KICAD_FP}/Package_TO_SOT_SMD.pretty",
    "SOT-223-3_TabPin2", "U_REG", "AMS1117-3.3",
    200, 50)

# USB-C — on the right edge of the board
place_footprint(board, f"{KICAD_FP}/Connector_USB.pretty",
    "USB_C_Receptacle_GCT_USB4085", "J_USB", "USB_C",
    222, 80, 90)

# Decoupling caps
cap_positions = [
    (130, 60), (150, 60), (170, 60),  # near flash chips
    (90, 88), (110, 88), (130, 88),   # near shift registers
    (160, 88), (190, 88),             # near buffers
    (108, 60), (95, 48),              # near MCU
    (195, 55), (205, 55),             # near regulator
    (215, 75),                        # near USB
]
for i, (cx, cy) in enumerate(cap_positions):
    place_footprint(board, f"{KICAD_FP}/Capacitor_SMD.pretty",
        "C_0402_1005Metric", f"C{i+1}", "100nF",
        cx, cy)

# Bulk caps near regulator
place_footprint(board, f"{KICAD_FP}/Capacitor_SMD.pretty",
    "C_0805_2012Metric", "C14", "10uF", 192, 45)
place_footprint(board, f"{KICAD_FP}/Capacitor_SMD.pretty",
    "C_0805_2012Metric", "C15", "10uF", 208, 45)

# Crystal load caps
place_footprint(board, f"{KICAD_FP}/Capacitor_SMD.pretty",
    "C_0402_1005Metric", "C16", "15pF", 109, 52)
place_footprint(board, f"{KICAD_FP}/Capacitor_SMD.pretty",
    "C_0402_1005Metric", "C17", "15pF", 115, 52)

# USB resistors
place_footprint(board, f"{KICAD_FP}/Resistor_SMD.pretty",
    "R_0402_1005Metric", "R1", "27R", 215, 70)
place_footprint(board, f"{KICAD_FP}/Resistor_SMD.pretty",
    "R_0402_1005Metric", "R2", "27R", 215, 73)
# CC resistors
place_footprint(board, f"{KICAD_FP}/Resistor_SMD.pretty",
    "R_0402_1005Metric", "R3", "5.1K", 215, 85)
place_footprint(board, f"{KICAD_FP}/Resistor_SMD.pretty",
    "R_0402_1005Metric", "R4", "5.1K", 215, 88)
# Pull-ups
place_footprint(board, f"{KICAD_FP}/Resistor_SMD.pretty",
    "R_0402_1005Metric", "R5", "10K", 80, 105)
place_footprint(board, f"{KICAD_FP}/Resistor_SMD.pretty",
    "R_0402_1005Metric", "R6", "10K", 85, 105)

# Diodes for CE bus-OR
for i in range(3):
    place_footprint(board, f"{KICAD_FP}/Package_TO_SOT_SMD.pretty",
        "SOT-23", f"D{i+1}", "BAT54S",
        75 + i * 12, 115)

# ─── Step 4: Add power planes ───
print("\nAdding power planes...")

bbox = board.GetBoardEdgesBoundingBox()
bx1 = bbox.GetLeft() + MM(2)
by1 = bbox.GetTop() + MM(2)
bx2 = bbox.GetRight() - MM(2)
by2 = bbox.GetBottom() - MM(20)  # stop before finger area

gnd_net = board.GetNetInfo().GetNetItem("GND")
vcc_net = board.GetNetInfo().GetNetItem("VCC_5V")

for net_item, layer, name in [
    (gnd_net, pcbnew.In1_Cu, "GND"),
    (vcc_net, pcbnew.In2_Cu, "VCC_5V"),
]:
    if net_item:
        zone = pcbnew.ZONE(board)
        zone.SetNet(net_item)
        zone.SetLayer(layer)
        outline = zone.Outline()
        outline.NewOutline()
        outline.Append(int(bx1), int(by1))
        outline.Append(int(bx2), int(by1))
        outline.Append(int(bx2), int(by2))
        outline.Append(int(bx1), int(by2))
        zone.SetMinThickness(MM(0.2))
        zone.SetThermalReliefGap(MM(0.5))
        zone.SetThermalReliefSpokeWidth(MM(0.5))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        board.Add(zone)
        print(f"  {name} plane on {pcbnew.LayerName(layer)}")

# ─── Step 5: Save and render ───
pcbnew.SaveBoard(OUT_PCB, board)
print(f"\nSaved: {OUT_PCB}")

import subprocess
subprocess.run([
    'kicad-cli', 'pcb', 'render', OUT_PCB,
    '-o', os.path.join(OUT_DIR, 'production', 'neocart_prog_top.png'),
    '--side', 'top', '--width', '1920', '--height', '1080',
    '--quality', 'high', '--background', 'opaque', '--floor'
], capture_output=True)
subprocess.run([
    'kicad-cli', 'pcb', 'render', OUT_PCB,
    '-o', os.path.join(OUT_DIR, 'production', 'neocart_prog_perspective.png'),
    '--side', 'front', '--width', '1920', '--height', '1080',
    '--quality', 'high', '--background', 'opaque', '--perspective',
    '--rotate', '30,0,15', '--floor'
], capture_output=True)
print("Renders exported")
