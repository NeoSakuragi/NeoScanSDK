#!/usr/bin/env python3
"""
build_fpga_pcbs.py — Generate KiCad PCB files for the FPGA-based Neo Geo MVS dev cart.

Creates two boards:
  1. neocart_fpga_prog.kicad_pcb — PROG board (4-layer, FPGA + RP2040 + SDRAM)
  2. neocart_fpga_cha.kicad_pcb  — CHA board (2-layer, passive breakout)

Requires: KiCad 9 with pcbnew Python API, kicad-cli for rendering.
"""

import os
import sys
import subprocess
import pcbnew

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FPGA_DIR = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/fpga"
PROD_DIR = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production"

PROG_PCB_PATH = os.path.join(FPGA_DIR, "neocart_fpga_prog.kicad_pcb")
CHA_PCB_PATH  = os.path.join(FPGA_DIR, "neocart_fpga_cha.kicad_pcb")

PROG_SRC = "/tmp/neogeo-diag-mvs-prog/hardware/neogeo-diag-mvs-prog.kicad_pcb"
CHA_SRC  = "/tmp/neogeo-diag-mvs-cha/hardware/neo-zmc-board/neogeo-diag-mvs-cha-neo-zmc-board.kicad_pcb"

KICAD_FP = "/usr/share/kicad/footprints"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mm(val):
    """Convert mm to KiCad internal units."""
    return pcbnew.FromMM(val)

def pos(x_mm, y_mm):
    """Create a VECTOR2I position from mm coordinates."""
    return pcbnew.VECTOR2I(int(mm(x_mm)), int(mm(y_mm)))

def load_fp(lib_name, fp_name):
    """Load a footprint from the KiCad library. Returns None on failure."""
    lib_path = os.path.join(KICAD_FP, lib_name + ".pretty")
    try:
        fp = pcbnew.FootprintLoad(lib_path, fp_name)
        if fp is None:
            print(f"  WARNING: FootprintLoad returned None for {lib_name}/{fp_name}")
        return fp
    except Exception as e:
        print(f"  WARNING: Could not load {lib_name}/{fp_name}: {e}")
        return None

def place_fp(board, lib_name, fp_name, ref, value, x_mm, y_mm, angle_deg=0):
    """Load, configure, and place a footprint on the board."""
    fp = load_fp(lib_name, fp_name)
    if fp is None:
        return None
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(pos(x_mm, y_mm))
    if angle_deg != 0:
        fp.SetOrientationDegrees(angle_deg)
    board.Add(fp)
    print(f"  Placed {ref} ({value}) — {fp_name} at ({x_mm}, {y_mm})")
    return fp

def clone_edge_cuts(src_board, dst_board):
    """Clone all Edge_Cuts drawings from src to dst."""
    count = 0
    for dwg in src_board.GetDrawings():
        if dwg.GetLayer() == pcbnew.Edge_Cuts:
            dup = dwg.Duplicate()
            dst_board.Add(dup)
            count += 1
    print(f"  Cloned {count} Edge_Cuts drawings")
    return count

def clone_footprint(src_board, ref, dst_board, new_ref=None):
    """Clone a footprint by reference from src to dst board."""
    for fp in src_board.GetFootprints():
        if fp.GetReference() == ref:
            dup = fp.Duplicate()
            fp2 = pcbnew.Cast_to_FOOTPRINT(dup)
            if new_ref:
                fp2.SetReference(new_ref)
            dst_board.Add(fp2)
            print(f"  Cloned edge connector {ref}" + (f" as {new_ref}" if new_ref else ""))
            return fp2
    print(f"  WARNING: Footprint {ref} not found in source board")
    return None

def add_zone(board, net_name, net_code, layer, x1, y1, x2, y2):
    """Add a rectangular copper zone to the board."""
    ni = pcbnew.NETINFO_ITEM(board, net_name, net_code)
    board.Add(ni)

    zone = pcbnew.ZONE(board)
    zone.SetNet(ni)
    zone.SetLayer(layer)
    zone.SetIsFilled(False)

    zone.AppendCorner(pos(x1, y1), -1)
    zone.AppendCorner(pos(x2, y1), -1)
    zone.AppendCorner(pos(x2, y2), -1)
    zone.AppendCorner(pos(x1, y2), -1)

    board.Add(zone)
    print(f"  Added zone: {net_name} on layer {board.GetLayerName(layer)}, "
          f"({x1},{y1})-({x2},{y2}) mm")
    return zone

def render_board(pcb_path, output_png, side="top"):
    """Render a PCB to PNG using kicad-cli."""
    cmd = [
        "kicad-cli", "pcb", "render",
        pcb_path,
        "-o", output_png,
        "--side", side,
        "--width", "1920",
        "--height", "1080",
        "--quality", "high",
        "--background", "opaque",
        "--floor",
    ]
    print(f"  Rendering {side} view -> {output_png}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"  WARNING: kicad-cli returned {result.returncode}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
        else:
            print(f"  Render OK: {output_png}")
    except Exception as e:
        print(f"  WARNING: Render failed: {e}")


# ===========================================================================
#  PROG BOARD
# ===========================================================================
def build_prog_board():
    print("=" * 70)
    print("BUILDING PROG BOARD")
    print("=" * 70)

    # Load source board for cloning
    print("\nLoading source board for edge cuts and connectors...")
    src = pcbnew.LoadBoard(PROG_SRC)

    # Create new board
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    print(f"  4-layer board: F.Cu, In1.Cu, In2.Cu, B.Cu")

    # --- Clone board outline ---
    print("\nCloning board outline (Edge_Cuts)...")
    clone_edge_cuts(src, board)

    # --- Clone edge connectors ---
    print("\nCloning edge connectors...")
    clone_footprint(src, "J1", board)  # B-side edge
    clone_footprint(src, "J2", board)  # A-side edge

    # --- Place ICs ---
    print("\nPlacing ICs...")
    place_fp(board, "Package_BGA",
             "BGA-256_17.0x17.0mm_Layout16x16_P1.0mm_Ball0.5mm_Pad0.4mm_NSMD",
             "U1", "ECP5-25F BGA256", 140, 75)

    place_fp(board, "Package_SO",
             "TSOP-II-54_22.2x10.16mm_P0.8mm",
             "U2", "IS42S16160J SDRAM", 140, 55)

    place_fp(board, "Package_SO",
             "TSOP-II-54_22.2x10.16mm_P0.8mm",
             "U3", "IS42S16160J SDRAM", 140, 95)

    place_fp(board, "Package_DFN_QFN",
             "QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm",
             "U4", "RP2040", 85, 55)

    place_fp(board, "Package_SO",
             "SOIC-8_3.9x4.9mm_P1.27mm",
             "U5", "W25Q32JVS RP2040-Flash", 75, 55)

    place_fp(board, "Package_SO",
             "SOIC-8_3.9x4.9mm_P1.27mm",
             "U6", "W25Q32JVS FPGA-Config", 165, 55)

    place_fp(board, "Package_SO",
             "SOIC-20W_7.5x12.8mm_P1.27mm",
             "U7", "74LVC245A Bus-Xcvr", 100, 115)

    place_fp(board, "Package_SO",
             "SOIC-20W_7.5x12.8mm_P1.27mm",
             "U8", "74LVC245A Bus-Xcvr", 125, 115)

    place_fp(board, "Package_TO_SOT_SMD",
             "SOT-223-3_TabPin2",
             "U9", "AMS1117-3.3", 200, 40)

    place_fp(board, "Package_TO_SOT_SMD",
             "SOT-223-3_TabPin2",
             "U10", "AMS1117-1.1", 200, 55)

    # --- Connectors ---
    print("\nPlacing connectors...")
    place_fp(board, "Connector_USB",
             "USB_C_Receptacle_GCT_USB4085",
             "J3", "USB-C", 222, 75, angle_deg=90)

    place_fp(board, "Connector_Card",
             "microSD_HC_Molex_47219-2001",
             "J4", "microSD", 210, 100)

    # Inter-board 2x50: two 2x25 headers side by side
    place_fp(board, "Connector_PinHeader_2.54mm",
             "PinHeader_2x25_P2.54mm_Vertical",
             "J5A", "InterBoard-A 2x25", 125, 35)
    place_fp(board, "Connector_PinHeader_2.54mm",
             "PinHeader_2x25_P2.54mm_Vertical",
             "J5B", "InterBoard-B 2x25", 155, 35)

    place_fp(board, "Connector_PinHeader_2.54mm",
             "PinHeader_2x03_P2.54mm_Vertical",
             "J6", "JTAG", 70, 40)

    place_fp(board, "Connector_PinHeader_2.54mm",
             "PinHeader_1x03_P2.54mm_Vertical",
             "J7", "UART", 60, 40)

    # --- Crystal ---
    print("\nPlacing crystal...")
    place_fp(board, "Crystal",
             "Crystal_SMD_3215-2Pin_3.2x1.5mm",
             "Y1", "12MHz", 95, 55)

    # --- Buttons ---
    print("\nPlacing buttons...")
    place_fp(board, "Button_Switch_SMD",
             "SW_SPST_PTS645Sx43SMTR92",
             "SW1", "BOOTSEL", 75, 45)

    place_fp(board, "Button_Switch_SMD",
             "SW_SPST_PTS645Sx43SMTR92",
             "SW2", "RESET", 85, 45)

    # --- LEDs ---
    print("\nPlacing LEDs...")
    place_fp(board, "LED_SMD", "LED_0805_2012Metric",
             "LED1", "PWR Green", 70, 32)
    place_fp(board, "LED_SMD", "LED_0805_2012Metric",
             "LED2", "ACT Yellow", 75, 32)
    place_fp(board, "LED_SMD", "LED_0805_2012Metric",
             "LED3", "USR Red", 80, 32)

    # --- Decoupling capacitors (0402, 100nF) near ICs ---
    print("\nPlacing decoupling capacitors (0402 100nF)...")
    decap_positions = [
        # Near U1 (FPGA) — 8 caps around the BGA
        ("C1",  133, 68),  ("C2",  147, 68),
        ("C3",  133, 82),  ("C4",  147, 82),
        ("C5",  130, 75),  ("C6",  150, 75),
        ("C7",  140, 67),  ("C8",  140, 83),
        # Near U2 (SDRAM top) — 3 caps
        ("C9",  130, 50),  ("C10", 150, 50),  ("C11", 140, 48),
        # Near U3 (SDRAM bottom) — 3 caps
        ("C12", 130, 100), ("C13", 150, 100), ("C14", 140, 102),
        # Near U4 (RP2040) — 3 caps
        ("C15", 80, 50),   ("C16", 90, 50),   ("C17", 85, 60),
        # Near U7, U8 (bus transceivers) — 2 caps
        ("C18", 95, 110),  ("C19", 120, 110),
        # Near U5, U6 (flash) — 2 caps
        ("C20", 70, 52),   ("C21", 160, 52),
    ]
    for ref, x, y in decap_positions:
        place_fp(board, "Capacitor_SMD", "C_0402_1005Metric",
                 ref, "100nF", x, y)

    # --- Bulk capacitors (0805, 10uF) near regulators ---
    print("\nPlacing bulk capacitors (0805 10uF)...")
    place_fp(board, "Capacitor_SMD", "C_0805_2012Metric",
             "C22", "10uF", 195, 40)   # Near U9
    place_fp(board, "Capacitor_SMD", "C_0805_2012Metric",
             "C23", "10uF", 195, 55)   # Near U10
    place_fp(board, "Capacitor_SMD", "C_0805_2012Metric",
             "C24", "10uF", 205, 47)   # Between regulators output

    # --- Crystal load capacitors ---
    print("\nPlacing crystal load caps...")
    place_fp(board, "Capacitor_SMD", "C_0402_1005Metric",
             "C25", "22pF", 92, 57)
    place_fp(board, "Capacitor_SMD", "C_0402_1005Metric",
             "C26", "22pF", 98, 57)

    # --- Series resistors (0402) between edge connector and FPGA ---
    print("\nPlacing series resistors (0402)...")
    resistor_positions = [
        # Row near bus transceivers — data bus protection
        ("R1",  100, 125), ("R2",  104, 125), ("R3",  108, 125),
        ("R4",  112, 125), ("R5",  116, 125),
        ("R6",  125, 125), ("R7",  129, 125), ("R8",  133, 125),
        ("R9",  137, 125), ("R10", 141, 125),
    ]
    for ref, x, y in resistor_positions:
        place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
                 ref, "33R", x, y)

    # --- LED resistors ---
    print("\nPlacing LED resistors...")
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R11", "1K", 70, 35)
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R12", "1K", 75, 35)
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R13", "1K", 80, 35)

    # --- USB resistors (CC pull-downs, D+/D- series) ---
    print("\nPlacing USB resistors...")
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R14", "5.1K CC1", 218, 70)
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R15", "5.1K CC2", 218, 73)
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R16", "27R D+", 218, 76)
    place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
             "R17", "27R D-", 218, 79)

    # --- Power zones on inner layers ---
    print("\nAdding power zones...")
    # Zone bounds: board area minus 20mm before finger area
    # Board roughly x: 50-225, y: 25-150, fingers start at ~131
    add_zone(board, "GND",     1, pcbnew.In1_Cu,  55, 28, 220, 130)
    add_zone(board, "VCC_3V3", 2, pcbnew.In2_Cu,  55, 28, 220, 130)

    # --- Save ---
    print(f"\nSaving PROG board to {PROG_PCB_PATH}...")
    pcbnew.SaveBoard(PROG_PCB_PATH, board)
    print("  PROG board saved successfully.")

    return board


# ===========================================================================
#  CHA BOARD
# ===========================================================================
def build_cha_board():
    print("\n" + "=" * 70)
    print("BUILDING CHA BOARD")
    print("=" * 70)

    # Load source board for cloning
    print("\nLoading source board for edge cuts and connectors...")
    src = pcbnew.LoadBoard(CHA_SRC)

    # Create new board
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    print(f"  2-layer board: F.Cu, B.Cu")

    # --- Clone board outline ---
    print("\nCloning board outline (Edge_Cuts)...")
    clone_edge_cuts(src, board)

    # --- Clone edge connectors ---
    print("\nCloning edge connectors...")
    clone_footprint(src, "J1", board)  # A-side edge
    clone_footprint(src, "J4", board)  # B-side edge

    # --- Inter-board connector (2x50 = two 2x25 male pin headers) ---
    print("\nPlacing inter-board connectors...")
    place_fp(board, "Connector_PinHeader_2.54mm",
             "PinHeader_2x25_P2.54mm_Vertical",
             "J2", "InterBoard-A 2x25", 125, 35)
    place_fp(board, "Connector_PinHeader_2.54mm",
             "PinHeader_2x25_P2.54mm_Vertical",
             "J3", "InterBoard-B 2x25", 155, 35)

    # --- Series resistors (0402, 470 ohm) ---
    # Place 20 representative resistors in rows between edge connector and
    # inter-board header area
    print("\nPlacing series resistors (0402 470R) — 20 representative...")
    resistor_y_rows = [70, 74, 78, 82]  # 4 rows
    resistor_x_start = 90
    resistor_x_step = 6
    r_idx = 1
    for row_idx, y in enumerate(resistor_y_rows):
        count_in_row = 5
        for col in range(count_in_row):
            x = resistor_x_start + col * resistor_x_step
            ref = f"R{r_idx}"
            place_fp(board, "Resistor_SMD", "R_0402_1005Metric",
                     ref, "470R", x, y)
            r_idx += 1

    # --- Decoupling caps near inter-board connector ---
    print("\nPlacing decoupling caps near inter-board connector...")
    cap_positions = [
        ("C1", 120, 45),
        ("C2", 135, 45),
        ("C3", 150, 45),
        ("C4", 160, 45),
        ("C5", 140, 30),
    ]
    for ref, x, y in cap_positions:
        place_fp(board, "Capacitor_SMD", "C_0402_1005Metric",
                 ref, "100nF", x, y)

    # --- Save ---
    print(f"\nSaving CHA board to {CHA_PCB_PATH}...")
    pcbnew.SaveBoard(CHA_PCB_PATH, board)
    print("  CHA board saved successfully.")

    return board


# ===========================================================================
#  MAIN
# ===========================================================================
def main():
    os.makedirs(FPGA_DIR, exist_ok=True)
    os.makedirs(PROD_DIR, exist_ok=True)

    # Build both boards
    build_prog_board()
    build_cha_board()

    # Render both boards
    print("\n" + "=" * 70)
    print("RENDERING BOARDS")
    print("=" * 70)

    render_board(PROG_PCB_PATH,
                 os.path.join(PROD_DIR, "neocart_fpga_prog_top.png"), "top")
    render_board(PROG_PCB_PATH,
                 os.path.join(PROD_DIR, "neocart_fpga_prog_perspective.png"), "front")
    render_board(CHA_PCB_PATH,
                 os.path.join(PROD_DIR, "neocart_fpga_cha_top.png"), "top")
    render_board(CHA_PCB_PATH,
                 os.path.join(PROD_DIR, "neocart_fpga_cha_perspective.png"), "front")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"\nPROG board: {PROG_PCB_PATH}")
    print(f"CHA board:  {CHA_PCB_PATH}")
    print(f"Renders in: {PROD_DIR}/")


if __name__ == "__main__":
    main()
