#!/usr/bin/env python3
"""
build_tqfp_prog.py — Build a KiCad 9 PCB for Neo Geo MVS PROG board
using an ECP5 FPGA in TQFP-144 package with optimized component placement.

Clones board outline + edge connectors from neogeo-diag-mvs-prog reference board,
places all components, creates nets, assigns pads, adds power zones, and exports DSN.
"""

import os
import sys
import subprocess
import warnings

warnings.filterwarnings("ignore")

import pcbnew

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REFERENCE_PCB = "/tmp/neogeo-diag-mvs-prog/hardware/neogeo-diag-mvs-prog.kicad_pcb"
OUTPUT_DIR = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/fpga"
PRODUCTION_DIR = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production"
OUTPUT_PCB = os.path.join(OUTPUT_DIR, "neocart_tqfp_prog.kicad_pcb")
DSN_PATH = os.path.join(OUTPUT_DIR, "neocart_tqfp_prog.dsn")

# Footprint libraries
LIB_QFP = "/usr/share/kicad/footprints/Package_QFP.pretty"
LIB_SO = "/usr/share/kicad/footprints/Package_SO.pretty"
LIB_QFN = "/usr/share/kicad/footprints/Package_DFN_QFN.pretty"
LIB_TO_SOT = "/usr/share/kicad/footprints/Package_TO_SOT_SMD.pretty"
LIB_CAP = "/usr/share/kicad/footprints/Capacitor_SMD.pretty"
LIB_RES = "/usr/share/kicad/footprints/Resistor_SMD.pretty"
LIB_LED = "/usr/share/kicad/footprints/LED_SMD.pretty"
LIB_CRYSTAL = "/usr/share/kicad/footprints/Crystal.pretty"
LIB_USB = "/usr/share/kicad/footprints/Connector_USB.pretty"
LIB_PIN = "/usr/share/kicad/footprints/Connector_PinHeader_2.54mm.pretty"
LIB_SW = "/usr/share/kicad/footprints/Button_Switch_SMD.pretty"


def mm_pos(x_mm, y_mm):
    """Return a VECTOR2I from mm coordinates."""
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


def load_fp(lib_path, fp_name):
    """Load a footprint from a library, returning None on failure."""
    try:
        fp = pcbnew.FootprintLoad(lib_path, fp_name)
        if fp is None:
            print(f"  WARNING: FootprintLoad returned None for {fp_name} in {lib_path}")
        return fp
    except Exception as e:
        print(f"  WARNING: Could not load {fp_name} from {lib_path}: {e}")
        return None


def place_fp(board, ref, lib_path, fp_name, x, y, angle_deg=0):
    """Load, place and add a footprint to the board. Returns the footprint or None."""
    fp = load_fp(lib_path, fp_name)
    if fp is None:
        return None
    fp.SetReference(ref)
    fp.SetPosition(mm_pos(x, y))
    if angle_deg != 0:
        fp.SetOrientationDegrees(angle_deg)
    board.Add(fp)
    print(f"  Placed {ref}: {fp_name} at ({x}, {y}) angle={angle_deg}")
    return fp


def create_net(board, name, net_dict):
    """Create a net on the board and register it in our dict."""
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    net_dict[name] = ni.GetNetCode()
    return ni.GetNetCode()


def assign_pad_net(fp, pad_number, net_name, net_dict):
    """Assign a net to a specific pad on a footprint by pad number (string)."""
    if fp is None:
        return
    pad_str = str(pad_number)
    for pad in fp.Pads():
        if pad.GetNumber() == pad_str:
            if net_name in net_dict:
                pad.SetNetCode(net_dict[net_name])
            return
    # Pad not found — silently skip


def strip_pad_net(fp, pad_number):
    """Strip net assignment from a pad (set netcode to 0)."""
    if fp is None:
        return
    pad_str = str(pad_number)
    for pad in fp.Pads():
        if pad.GetNumber() == pad_str:
            pad.SetNetCode(0)
            return


def main():
    print("=" * 70)
    print("NeoCart TQFP PROG Board Builder")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 1. Load reference board and create new board
    # -----------------------------------------------------------------------
    print("\n[1] Loading reference board...")
    ref_board = pcbnew.LoadBoard(REFERENCE_PCB)
    board = pcbnew.CreateEmptyBoard()

    # -----------------------------------------------------------------------
    # 2. Layer setup — 4 layers
    # -----------------------------------------------------------------------
    print("[2] Setting up 4-layer stackup...")
    board.SetCopperLayerCount(4)

    # -----------------------------------------------------------------------
    # 3. Clone board outline (Edge_Cuts) from reference
    # -----------------------------------------------------------------------
    print("[3] Cloning board outline (Edge_Cuts)...")
    ec_count = 0
    for drawing in ref_board.GetDrawings():
        if drawing.GetLayer() == pcbnew.Edge_Cuts:
            dup = drawing.Duplicate()
            board.Add(dup)
            ec_count += 1
    print(f"  Cloned {ec_count} Edge_Cuts drawings")

    # -----------------------------------------------------------------------
    # 4. Clone edge connectors J1 and J2
    # -----------------------------------------------------------------------
    print("[4] Cloning edge connectors J1, J2...")
    edge_fps = {}
    for fp in ref_board.GetFootprints():
        ref = fp.GetReference()
        if ref in ("J1", "J2"):
            dup = fp.Duplicate()
            # Clear all pad nets from cloned footprint (they reference the old board's nets)
            for pad in dup.Pads():
                pad.SetNetCode(0)
            board.Add(dup)
            edge_fps[ref] = dup
            pad_count = sum(1 for _ in dup.Pads())
            print(f"  Cloned {ref} ({pad_count} pads, nets cleared)")

    # -----------------------------------------------------------------------
    # 5. Place components
    # -----------------------------------------------------------------------
    print("\n[5] Placing components...")
    fps = {}  # ref -> footprint

    # --- Center: FPGA ---
    fps["U1"] = place_fp(board, "U1", LIB_QFP,
                         "TQFP-144_20x20mm_P0.5mm", 140, 80)

    # --- Top: SDRAM (4x 32MB = 128MB) ---
    fps["U2"] = place_fp(board, "U2", LIB_SO,
                         "TSOP-II-54_22.2x10.16mm_P0.8mm", 110, 48)
    fps["U2b"] = place_fp(board, "U2b", LIB_SO,
                          "TSOP-II-54_22.2x10.16mm_P0.8mm", 110, 62)
    fps["U3"] = place_fp(board, "U3", LIB_SO,
                         "TSOP-II-54_22.2x10.16mm_P0.8mm", 170, 48)
    fps["U3b"] = place_fp(board, "U3b", LIB_SO,
                          "TSOP-II-54_22.2x10.16mm_P0.8mm", 170, 62)

    # --- Below FPGA: Level shifters (swapped to match connector pin order) ---
    fps["U7"] = place_fp(board, "U7", LIB_SO,
                         "SOIC-20W_7.5x12.8mm_P1.27mm", 160, 110)
    fps["U8"] = place_fp(board, "U8", LIB_SO,
                         "SOIC-20W_7.5x12.8mm_P1.27mm", 120, 110)

    # --- Left: RP2040 section (spread out, room to breathe) ---
    fps["U4"] = place_fp(board, "U4", LIB_QFN,
                         "QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm", 80, 80)
    fps["U5"] = place_fp(board, "U5", LIB_SO,
                         "SOIC-8_3.9x4.9mm_P1.27mm", 65, 70)
    fps["Y1"] = place_fp(board, "Y1", LIB_CRYSTAL,
                         "Crystal_SMD_3215-2Pin_3.2x1.5mm", 80, 95)
    fps["J3"] = place_fp(board, "J3", LIB_USB,
                         "USB_C_Receptacle_GCT_USB4085", 55, 110, angle_deg=270)

    # --- Right: FPGA config flash (close to FPGA JTAG/config pins) ---
    fps["U6"] = place_fp(board, "U6", LIB_SO,
                         "SOIC-8_3.9x4.9mm_P1.27mm", 200, 80)

    # --- Bottom-right: Power regulators (away from signal area) ---
    fps["U9"] = place_fp(board, "U9", LIB_TO_SOT,
                         "SOT-223-3_TabPin2", 200, 105)
    fps["U10"] = place_fp(board, "U10", LIB_TO_SOT,
                          "SOT-223-3_TabPin2", 200, 120)

    # --- Top-left: Debug (spread out) ---
    fps["J6"] = place_fp(board, "J6", LIB_PIN,
                         "PinHeader_2x03_P2.54mm_Vertical", 70, 35)
    fps["J7"] = place_fp(board, "J7", LIB_PIN,
                         "PinHeader_1x03_P2.54mm_Vertical", 58, 35)

    fps["LED1"] = place_fp(board, "LED1", LIB_LED,
                           "LED_0805_2012Metric", 82, 35)
    fps["LED2"] = place_fp(board, "LED2", LIB_LED,
                           "LED_0805_2012Metric", 88, 35)
    # LED3 removed — pin used for SDRAM_CS3N

    # Tactile switches — try PTS645 first, fall back
    sw_candidates = [
        "SW_SPST_PTS645Sx43SMTR92",
        "SW_SPST_PTS810",
        "SW_SPST_TL3342",
        "SW_SPST_B3U-1000P",
    ]
    sw_fp_name = None
    for cand in sw_candidates:
        test = load_fp(LIB_SW, cand)
        if test is not None:
            sw_fp_name = cand
            break
    if sw_fp_name:
        fps["SW1"] = place_fp(board, "SW1", LIB_SW, sw_fp_name, 90, 35)
        fps["SW2"] = place_fp(board, "SW2", LIB_SW, sw_fp_name, 100, 35)
    else:
        print("  WARNING: No suitable tactile switch footprint found")

    # --- Decoupling caps ---
    print("\n  Placing decoupling capacitors...")

    # FPGA corners — 100nF 0402
    cap_0402 = "C_0402_1005Metric"
    fpga_caps = [(130, 70), (150, 70), (130, 90), (150, 90)]
    for i, (cx, cy) in enumerate(fpga_caps):
        fps[f"C_FPGA{i+1}"] = place_fp(board, f"C{i+1}", LIB_CAP, cap_0402, cx, cy)

    # SDRAM caps — 100nF 0402 (one per chip, 4 chips)
    sdram_caps = [(105, 44), (115, 44), (165, 44), (175, 44), (105, 66), (115, 66), (165, 66), (175, 66)]
    for i, (cx, cy) in enumerate(sdram_caps):
        fps[f"C_SDRAM{i+1}"] = place_fp(board, f"C{i+5}", LIB_CAP, cap_0402, cx, cy)

    # RP2040 caps — 100nF 0402
    rp_caps = [(70, 45), (80, 45)]
    for i, (cx, cy) in enumerate(rp_caps):
        fps[f"C_RP{i+1}"] = place_fp(board, f"C{i+9}", LIB_CAP, cap_0402, cx, cy)

    # 74LVC245 caps
    fps["C_LV1"] = place_fp(board, "C11", LIB_CAP, cap_0402, 115, 105)
    fps["C_LV2"] = place_fp(board, "C12", LIB_CAP, cap_0402, 165, 105)

    # Regulator caps
    fps["C_REG1"] = place_fp(board, "C13", LIB_CAP, cap_0402, 195, 100)
    fps["C_REG2"] = place_fp(board, "C14", LIB_CAP, cap_0402, 195, 115)

    # USB cap
    fps["C_USB"] = place_fp(board, "C15", LIB_CAP, cap_0402, 60, 105)

    # FPGA config flash cap
    fps["C_FLASH"] = place_fp(board, "C16", LIB_CAP, cap_0402, 205, 45)

    # Bulk caps near regulators — 10uF 0805
    cap_0805 = "C_0805_2012Metric"
    bulk_caps = [(205, 100), (205, 115), (205, 125)]
    for i, (cx, cy) in enumerate(bulk_caps):
        fps[f"C_BULK{i+1}"] = place_fp(board, f"C{i+17}", LIB_CAP, cap_0805, cx, cy)

    # Crystal load caps — 15pF 0402
    fps["C_XL1"] = place_fp(board, "C20", LIB_CAP, cap_0402, 75, 98)
    fps["C_XL2"] = place_fp(board, "C21", LIB_CAP, cap_0402, 85, 98)

    # --- Series resistors near gold fingers ---
    print("\n  Placing series resistors...")
    r_0402 = "R_0402_1005Metric"
    for i in range(10):
        rx = 100 + i * 10
        fps[f"R_SER{i+1}"] = place_fp(board, f"R{i+1}", LIB_RES, r_0402, rx, 125)

    # USB resistors
    fps["R_USB1"] = place_fp(board, "R11", LIB_RES, r_0402, 60, 100)
    fps["R_USB2"] = place_fp(board, "R12", LIB_RES, r_0402, 60, 103)
    fps["R_CC1"] = place_fp(board, "R13", LIB_RES, r_0402, 50, 115)
    fps["R_CC2"] = place_fp(board, "R14", LIB_RES, r_0402, 50, 118)

    # LED resistors
    fps["R_LED1"] = place_fp(board, "R15", LIB_RES, r_0402, 82, 38)
    fps["R_LED2"] = place_fp(board, "R16", LIB_RES, r_0402, 88, 38)

    # -----------------------------------------------------------------------
    # 6. Create nets
    # -----------------------------------------------------------------------
    print("\n[6] Creating nets...")
    net_dict = {}

    # Power nets
    for name in ["GND", "VCC_5V", "VCC_3V3", "VCC_1V1"]:
        create_net(board, name, net_dict)

    # Program data bus (connector side)
    for i in range(16):
        create_net(board, f"PD{i}", net_dict)

    # FPGA-side data bus
    for i in range(16):
        create_net(board, f"FPGA_PD{i}", net_dict)

    # Program address bus (connector side)
    for i in range(18):
        create_net(board, f"PA{i}", net_dict)

    # M1 address bus
    for i in range(17):
        create_net(board, f"MA{i}", net_dict)

    # M1 data bus
    for i in range(8):
        create_net(board, f"MD{i}", net_dict)

    # Control signals
    for name in ["nRW", "ROMOEU", "ROMOEL", "ROMOE", "SDROE"]:
        create_net(board, name, net_dict)

    # SDRAM nets
    for name in ["SDRAM_CLK", "SDRAM_CKE", "SDRAM_CS0N", "SDRAM_CS1N",
                  "SDRAM_CS2N", "SDRAM_CS3N",
                  "SDRAM_RASN", "SDRAM_CASN", "SDRAM_WEN",
                  "SDRAM_DQMH", "SDRAM_DQML"]:
        create_net(board, name, net_dict)
    for i in range(16):
        create_net(board, f"SDRAM_DQ{i}", net_dict)
    for i in range(13):
        create_net(board, f"SDRAM_A{i}", net_dict)
    for i in range(2):
        create_net(board, f"SDRAM_BA{i}", net_dict)

    # RP2040 SPI nets
    for name in ["SPI_MOSI", "SPI_MISO", "SPI_SCK", "SPI_CS"]:
        create_net(board, name, net_dict)

    # RP2040 QSPI nets
    for name in ["QSPI_SCK", "QSPI_CS", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3"]:
        create_net(board, name, net_dict)

    # USB nets
    for name in ["USB_DP", "USB_DM", "USB_CC1", "USB_CC2", "USB_VBUS"]:
        create_net(board, name, net_dict)

    # Crystal
    for name in ["XTAL_IN", "XTAL_OUT"]:
        create_net(board, name, net_dict)

    # JTAG
    for name in ["JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO"]:
        create_net(board, name, net_dict)

    # UART
    for name in ["UART_TX", "UART_RX"]:
        create_net(board, name, net_dict)

    # LED nets
    for i in range(1, 4):
        create_net(board, f"LED{i}_NET", net_dict)

    # FPGA config SPI
    for name in ["CFG_SCK", "CFG_CS", "CFG_MOSI", "CFG_MISO"]:
        create_net(board, name, net_dict)

    # 74LVC245 direction/enable
    for name in ["LV_DIR_LO", "LV_DIR_HI", "LV_OE_LO", "LV_OE_HI"]:
        create_net(board, name, net_dict)

    print(f"  Created {len(net_dict)} nets")

    # -----------------------------------------------------------------------
    # 7. Assign nets to pads
    # -----------------------------------------------------------------------
    print("\n[7] Assigning nets to pads...")

    # --- Edge connector J2 (A-side, 60 pins) ---
    j2 = edge_fps.get("J2")
    if j2:
        # Pins 1-4: GND
        for p in range(1, 5):
            assign_pad_net(j2, p, "GND", net_dict)
        # Pins 5-20: PD0-PD15
        for i in range(16):
            assign_pad_net(j2, 5 + i, f"PD{i}", net_dict)
        # Pin 21: nRW
        assign_pad_net(j2, 21, "nRW", net_dict)
        # Pins 23-24: ROMOEU/ROMOEL
        assign_pad_net(j2, 23, "ROMOEU", net_dict)
        assign_pad_net(j2, 24, "ROMOEL", net_dict)
        # Pins 29-32: VCC_5V
        for p in range(29, 33):
            assign_pad_net(j2, p, "VCC_5V", net_dict)
        # Pin 33: ROMOE
        assign_pad_net(j2, 33, "ROMOE", net_dict)
        # Pins 47-55: MA8-MA16
        for i in range(9):
            assign_pad_net(j2, 47 + i, f"MA{8 + i}", net_dict)
        # Pin 56: SDROE
        assign_pad_net(j2, 56, "SDROE", net_dict)
        # Pins 58-60: GND
        for p in range(58, 61):
            assign_pad_net(j2, p, "GND", net_dict)
        print("  J2 (A-side) nets assigned")

    # --- Edge connector J1 (B-side, 60 pins) ---
    j1 = edge_fps.get("J1")
    if j1:
        # Pins 1-4: GND
        for p in range(1, 5):
            assign_pad_net(j1, p, "GND", net_dict)
        # Pins 5-22: PA0-PA17
        for i in range(18):
            assign_pad_net(j1, 5 + i, f"PA{i}", net_dict)
        # Pins 29-32: VCC_5V
        for p in range(29, 33):
            assign_pad_net(j1, p, "VCC_5V", net_dict)
        # Pins 40-47: MD0-MD7
        for i in range(8):
            assign_pad_net(j1, 40 + i, f"MD{i}", net_dict)
        # Pins 48-55: MA0-MA7
        for i in range(8):
            assign_pad_net(j1, 48 + i, f"MA{i}", net_dict)
        # Pins 58-60: GND
        for p in range(58, 61):
            assign_pad_net(j1, p, "GND", net_dict)
        print("  J1 (B-side) nets assigned")

    # --- SDRAM U2 (IS42S16400J TSOP-54, CS0) ---
    # Standard IS42S16400J pinout for TSOP-II-54
    u2 = fps.get("U2")
    if u2:
        # VDD pins: 3, 17, 30, 43
        for p in [3, 17, 30, 43]:
            assign_pad_net(u2, p, "VCC_3V3", net_dict)
        # VSS pins: 4, 16, 31, 42
        for p in [4, 16, 31, 42]:
            assign_pad_net(u2, p, "GND", net_dict)
        # DQ0-DQ15: pins 20-27 (DQ0-7), 33-40 (DQ8-15)
        for i in range(8):
            assign_pad_net(u2, 20 + i, f"SDRAM_DQ{i}", net_dict)
        for i in range(8):
            assign_pad_net(u2, 33 + i, f"SDRAM_DQ{8 + i}", net_dict)
        # Address A0-A12: pins 44-54, wrapping
        addr_pins_u2 = [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 1, 2]
        for i, pin in enumerate(addr_pins_u2):
            assign_pad_net(u2, pin, f"SDRAM_A{i}", net_dict)
        # BA0, BA1: pins 5, 6
        assign_pad_net(u2, 5, "SDRAM_BA0", net_dict)
        assign_pad_net(u2, 6, "SDRAM_BA1", net_dict)
        # Control: CS=12, RAS=7, CAS=8, WE=9, CKE=10, CLK=11
        assign_pad_net(u2, 12, "SDRAM_CS0N", net_dict)
        assign_pad_net(u2, 7, "SDRAM_RASN", net_dict)
        assign_pad_net(u2, 8, "SDRAM_CASN", net_dict)
        assign_pad_net(u2, 9, "SDRAM_WEN", net_dict)
        assign_pad_net(u2, 10, "SDRAM_CKE", net_dict)
        assign_pad_net(u2, 11, "SDRAM_CLK", net_dict)
        # DQM: DQML=18, DQMH=32
        assign_pad_net(u2, 18, "SDRAM_DQML", net_dict)
        assign_pad_net(u2, 32, "SDRAM_DQMH", net_dict)
        print("  U2 (SDRAM CS0) nets assigned")

    # --- SDRAM U3 (same, CS1) ---
    u3 = fps.get("U3")
    if u3:
        for p in [3, 17, 30, 43]:
            assign_pad_net(u3, p, "VCC_3V3", net_dict)
        for p in [4, 16, 31, 42]:
            assign_pad_net(u3, p, "GND", net_dict)
        for i in range(8):
            assign_pad_net(u3, 20 + i, f"SDRAM_DQ{i}", net_dict)
        for i in range(8):
            assign_pad_net(u3, 33 + i, f"SDRAM_DQ{8 + i}", net_dict)
        addr_pins_u3 = [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 1, 2]
        for i, pin in enumerate(addr_pins_u3):
            assign_pad_net(u3, pin, f"SDRAM_A{i}", net_dict)
        assign_pad_net(u3, 5, "SDRAM_BA0", net_dict)
        assign_pad_net(u3, 6, "SDRAM_BA1", net_dict)
        assign_pad_net(u3, 12, "SDRAM_CS1N", net_dict)  # CS1 instead of CS0
        assign_pad_net(u3, 7, "SDRAM_RASN", net_dict)
        assign_pad_net(u3, 8, "SDRAM_CASN", net_dict)
        assign_pad_net(u3, 9, "SDRAM_WEN", net_dict)
        assign_pad_net(u3, 10, "SDRAM_CKE", net_dict)
        assign_pad_net(u3, 11, "SDRAM_CLK", net_dict)
        assign_pad_net(u3, 18, "SDRAM_DQML", net_dict)
        assign_pad_net(u3, 32, "SDRAM_DQMH", net_dict)
        print("  U3 (SDRAM CS1) nets assigned")

    # --- SDRAM U2b (CS2) ---
    u2b = fps.get("U2b")
    if u2b:
        for p in [3, 17, 30, 43]:
            assign_pad_net(u2b, p, "VCC_3V3", net_dict)
        for p in [4, 16, 31, 42]:
            assign_pad_net(u2b, p, "GND", net_dict)
        for i in range(8):
            assign_pad_net(u2b, 20 + i, f"SDRAM_DQ{i}", net_dict)
        for i in range(8):
            assign_pad_net(u2b, 33 + i, f"SDRAM_DQ{8 + i}", net_dict)
        addr_pins = [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 1, 2]
        for i, pin in enumerate(addr_pins):
            assign_pad_net(u2b, pin, f"SDRAM_A{i}", net_dict)
        assign_pad_net(u2b, 5, "SDRAM_BA0", net_dict)
        assign_pad_net(u2b, 6, "SDRAM_BA1", net_dict)
        assign_pad_net(u2b, 12, "SDRAM_CS2N", net_dict)
        assign_pad_net(u2b, 7, "SDRAM_RASN", net_dict)
        assign_pad_net(u2b, 8, "SDRAM_CASN", net_dict)
        assign_pad_net(u2b, 9, "SDRAM_WEN", net_dict)
        assign_pad_net(u2b, 10, "SDRAM_CKE", net_dict)
        assign_pad_net(u2b, 11, "SDRAM_CLK", net_dict)
        assign_pad_net(u2b, 18, "SDRAM_DQML", net_dict)
        assign_pad_net(u2b, 32, "SDRAM_DQMH", net_dict)
        print("  U2b (SDRAM CS2) nets assigned")

    # --- SDRAM U3b (CS3) ---
    u3b = fps.get("U3b")
    if u3b:
        for p in [3, 17, 30, 43]:
            assign_pad_net(u3b, p, "VCC_3V3", net_dict)
        for p in [4, 16, 31, 42]:
            assign_pad_net(u3b, p, "GND", net_dict)
        for i in range(8):
            assign_pad_net(u3b, 20 + i, f"SDRAM_DQ{i}", net_dict)
        for i in range(8):
            assign_pad_net(u3b, 33 + i, f"SDRAM_DQ{8 + i}", net_dict)
        addr_pins = [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 1, 2]
        for i, pin in enumerate(addr_pins):
            assign_pad_net(u3b, pin, f"SDRAM_A{i}", net_dict)
        assign_pad_net(u3b, 5, "SDRAM_BA0", net_dict)
        assign_pad_net(u3b, 6, "SDRAM_BA1", net_dict)
        assign_pad_net(u3b, 12, "SDRAM_CS3N", net_dict)
        assign_pad_net(u3b, 7, "SDRAM_RASN", net_dict)
        assign_pad_net(u3b, 8, "SDRAM_CASN", net_dict)
        assign_pad_net(u3b, 9, "SDRAM_WEN", net_dict)
        assign_pad_net(u3b, 10, "SDRAM_CKE", net_dict)
        assign_pad_net(u3b, 11, "SDRAM_CLK", net_dict)
        assign_pad_net(u3b, 18, "SDRAM_DQML", net_dict)
        assign_pad_net(u3b, 32, "SDRAM_DQMH", net_dict)
        print("  U3b (SDRAM CS3) nets assigned")

    # --- FPGA U1 (TQFP-144) pin assignments ---
    # Optimized: top pins → SDRAM, bottom pins → PROG bus, left → RP2040, right → config
    u1 = fps.get("U1")
    if u1:
        # Bottom side (pins 1-36): PROG bus signals + RP2040 SPI
        # FPGA_PD0-PD15 (connect to 74LVC245 B-side)
        for i in range(16):
            assign_pad_net(u1, 1 + i, f"FPGA_PD{i}", net_dict)
        # PA0-PA17 (directly from FPGA to series resistors to connector)
        for i in range(18):
            assign_pad_net(u1, 17 + i, f"PA{i}", net_dict)
        # Control signals
        assign_pad_net(u1, 35, "ROMOE", net_dict)
        assign_pad_net(u1, 36, "BUS_DIR", net_dict)

        # Top side (pins 37-72): SDRAM
        for i in range(16):
            assign_pad_net(u1, 37 + i, f"SDRAM_DQ{i}", net_dict)
        for i in range(13):
            assign_pad_net(u1, 53 + i, f"SDRAM_A{i}", net_dict)
        assign_pad_net(u1, 66, "SDRAM_BA0", net_dict)
        assign_pad_net(u1, 67, "SDRAM_BA1", net_dict)
        assign_pad_net(u1, 68, "SDRAM_RASN", net_dict)
        assign_pad_net(u1, 69, "SDRAM_CASN", net_dict)
        assign_pad_net(u1, 70, "SDRAM_WEN", net_dict)
        assign_pad_net(u1, 71, "SDRAM_CLK", net_dict)
        assign_pad_net(u1, 72, "SDRAM_CKE", net_dict)

        # Right side (pins 73-108): SDRAM CS + config + V ROM
        assign_pad_net(u1, 73, "SDRAM_CS0N", net_dict)
        assign_pad_net(u1, 74, "SDRAM_CS1N", net_dict)
        assign_pad_net(u1, 75, "SDRAM_CS2N", net_dict)
        assign_pad_net(u1, 76, "SDRAM_CS3N", net_dict)
        assign_pad_net(u1, 77, "SDRAM_DQML", net_dict)
        assign_pad_net(u1, 78, "SDRAM_DQMH", net_dict)
        # V ROM data
        for i in range(8):
            assign_pad_net(u1, 79 + i, f"VD{i}", net_dict)
        assign_pad_net(u1, 87, "SDROE", net_dict)
        assign_pad_net(u1, 88, "ROMOEU", net_dict)
        assign_pad_net(u1, 89, "ROMOEL", net_dict)
        assign_pad_net(u1, 90, "nRW", net_dict)
        # M ROM address (directly from FPGA)
        for i in range(8):
            assign_pad_net(u1, 91 + i, f"MA{8+i}", net_dict)
        # LEDs
        assign_pad_net(u1, 99, "LED1_NET", net_dict)
        assign_pad_net(u1, 100, "LED2_NET", net_dict)

        # Left side (pins 109-144): RP2040 SPI + config
        assign_pad_net(u1, 109, "SPI_MOSI", net_dict)
        assign_pad_net(u1, 110, "SPI_MISO", net_dict)
        assign_pad_net(u1, 111, "SPI_SCK", net_dict)
        assign_pad_net(u1, 112, "SPI_CS", net_dict)
        assign_pad_net(u1, 113, "SPI_IRQ", net_dict)
        assign_pad_net(u1, 114, "nRESET", net_dict)
        # FPGA config SPI (directly to U6 config flash)
        assign_pad_net(u1, 115, "CFG_MOSI", net_dict)
        assign_pad_net(u1, 116, "CFG_MISO", net_dict)
        assign_pad_net(u1, 117, "CFG_SCK", net_dict)
        assign_pad_net(u1, 118, "CFG_CS", net_dict)
        # JTAG
        assign_pad_net(u1, 119, "JTAG_TDI", net_dict)
        assign_pad_net(u1, 120, "JTAG_TDO", net_dict)
        assign_pad_net(u1, 121, "JTAG_TMS", net_dict)
        assign_pad_net(u1, 122, "JTAG_TCK", net_dict)
        # M ROM data + address low
        for i in range(8):
            assign_pad_net(u1, 123 + i, f"MD{i}", net_dict)
        for i in range(8):
            assign_pad_net(u1, 131 + i, f"MA{i}", net_dict)
        # Crystal
        assign_pad_net(u1, 139, "XTAL_IN", net_dict)
        assign_pad_net(u1, 140, "XTAL_OUT", net_dict)
        # QSPI to RP2040 flash (directly through)
        assign_pad_net(u1, 141, "QSPI_CS", net_dict)
        assign_pad_net(u1, 142, "QSPI_SCK", net_dict)
        assign_pad_net(u1, 143, "QSPI_SD0", net_dict)
        assign_pad_net(u1, 144, "QSPI_SD1", net_dict)

        print("  U1 (FPGA TQFP-144) nets assigned — 108 pins mapped")

    # --- 74LVC245 U7 (D0-D7) ---
    # SOIC-20: pin 1=DIR, pin 20=VCC, pin 10=GND, pin 19=OE
    # A-side: pins 2-9, B-side: pins 18-11
    u7 = fps.get("U7")
    if u7:
        assign_pad_net(u7, 1, "LV_DIR_LO", net_dict)
        assign_pad_net(u7, 19, "LV_OE_LO", net_dict)
        assign_pad_net(u7, 20, "VCC_3V3", net_dict)
        assign_pad_net(u7, 10, "GND", net_dict)
        for i in range(8):
            assign_pad_net(u7, 2 + i, f"PD{i}", net_dict)       # A side
            assign_pad_net(u7, 18 - i, f"FPGA_PD{i}", net_dict)  # B side
        print("  U7 (74LVC245 D0-D7) nets assigned")

    # --- 74LVC245 U8 (D8-D15) ---
    u8 = fps.get("U8")
    if u8:
        assign_pad_net(u8, 1, "LV_DIR_HI", net_dict)
        assign_pad_net(u8, 19, "LV_OE_HI", net_dict)
        assign_pad_net(u8, 20, "VCC_3V3", net_dict)
        assign_pad_net(u8, 10, "GND", net_dict)
        for i in range(8):
            assign_pad_net(u8, 2 + i, f"PD{8 + i}", net_dict)
            assign_pad_net(u8, 18 - i, f"FPGA_PD{8 + i}", net_dict)
        print("  U8 (74LVC245 D8-D15) nets assigned")

    # --- RP2040 U4 ---
    u4 = fps.get("U4")
    if u4:
        # Power: multiple VDD/GND pins on QFN-56
        # RP2040 pinout: IOVDD=1,10,22,33,42,49; DVDD=23,50; USB_VDD=48
        # GND=57(EP)
        for p in [1, 10, 22, 33, 42, 49]:
            assign_pad_net(u4, p, "VCC_3V3", net_dict)
        for p in [23, 50]:
            assign_pad_net(u4, p, "VCC_1V1", net_dict)
        assign_pad_net(u4, 48, "VCC_3V3", net_dict)  # USB_VDD
        assign_pad_net(u4, 57, "GND", net_dict)       # Exposed pad
        # GPIO0-3: SPI to FPGA (pins 2,3,4,5)
        assign_pad_net(u4, 2, "SPI_MOSI", net_dict)   # GPIO0
        assign_pad_net(u4, 3, "SPI_MISO", net_dict)   # GPIO1
        assign_pad_net(u4, 4, "SPI_SCK", net_dict)    # GPIO2
        assign_pad_net(u4, 5, "SPI_CS", net_dict)     # GPIO3
        # USB: GPIO pins 46,47
        assign_pad_net(u4, 46, "USB_DP", net_dict)
        assign_pad_net(u4, 47, "USB_DM", net_dict)
        # QSPI: pins 51-56
        assign_pad_net(u4, 51, "QSPI_SD0", net_dict)
        assign_pad_net(u4, 52, "QSPI_SD1", net_dict)
        assign_pad_net(u4, 53, "QSPI_SCK", net_dict)
        assign_pad_net(u4, 54, "QSPI_SD2", net_dict)
        assign_pad_net(u4, 55, "QSPI_SD3", net_dict)
        assign_pad_net(u4, 56, "QSPI_CS", net_dict)
        # Crystal: pins 20,21
        assign_pad_net(u4, 20, "XTAL_IN", net_dict)
        assign_pad_net(u4, 21, "XTAL_OUT", net_dict)
        print("  U4 (RP2040) nets assigned")

    # --- W25Q32 U5 (RP2040 firmware flash) ---
    # SOIC-8: 1=CS, 2=DO, 3=WP, 4=GND, 5=DI, 6=CLK, 7=HOLD, 8=VCC
    u5 = fps.get("U5")
    if u5:
        assign_pad_net(u5, 1, "QSPI_CS", net_dict)
        assign_pad_net(u5, 2, "QSPI_SD1", net_dict)
        assign_pad_net(u5, 3, "QSPI_SD2", net_dict)
        assign_pad_net(u5, 4, "GND", net_dict)
        assign_pad_net(u5, 5, "QSPI_SD0", net_dict)
        assign_pad_net(u5, 6, "QSPI_SCK", net_dict)
        assign_pad_net(u5, 7, "QSPI_SD3", net_dict)
        assign_pad_net(u5, 8, "VCC_3V3", net_dict)
        print("  U5 (W25Q32 RP2040 flash) nets assigned")

    # --- W25Q32 U6 (FPGA config flash) ---
    u6 = fps.get("U6")
    if u6:
        assign_pad_net(u6, 1, "CFG_CS", net_dict)
        assign_pad_net(u6, 2, "CFG_MISO", net_dict)
        assign_pad_net(u6, 4, "GND", net_dict)
        assign_pad_net(u6, 5, "CFG_MOSI", net_dict)
        assign_pad_net(u6, 6, "CFG_SCK", net_dict)
        assign_pad_net(u6, 8, "VCC_3V3", net_dict)
        print("  U6 (W25Q32 FPGA config) nets assigned")

    # --- AMS1117-3.3 U9 ---
    # SOT-223-3: pin 1=GND/ADJ, pin 2=VOUT (tab), pin 3=VIN
    u9 = fps.get("U9")
    if u9:
        assign_pad_net(u9, 1, "GND", net_dict)
        assign_pad_net(u9, 2, "VCC_3V3", net_dict)
        assign_pad_net(u9, 3, "VCC_5V", net_dict)
        print("  U9 (AMS1117-3.3) nets assigned")

    # --- AMS1117-1.1 U10 ---
    u10 = fps.get("U10")
    if u10:
        assign_pad_net(u10, 1, "GND", net_dict)
        assign_pad_net(u10, 2, "VCC_1V1", net_dict)
        assign_pad_net(u10, 3, "VCC_3V3", net_dict)
        print("  U10 (AMS1117-1.1) nets assigned")

    # --- Crystal Y1 ---
    y1 = fps.get("Y1")
    if y1:
        assign_pad_net(y1, 1, "XTAL_IN", net_dict)
        assign_pad_net(y1, 2, "XTAL_OUT", net_dict)
        print("  Y1 (crystal) nets assigned")

    # --- JTAG J6 ---
    j6 = fps.get("J6")
    if j6:
        assign_pad_net(j6, 1, "JTAG_TCK", net_dict)
        assign_pad_net(j6, 2, "GND", net_dict)
        assign_pad_net(j6, 3, "JTAG_TDI", net_dict)
        assign_pad_net(j6, 4, "JTAG_TMS", net_dict)
        assign_pad_net(j6, 5, "JTAG_TDO", net_dict)
        assign_pad_net(j6, 6, "VCC_3V3", net_dict)
        print("  J6 (JTAG) nets assigned")

    # --- UART J7 ---
    j7 = fps.get("J7")
    if j7:
        assign_pad_net(j7, 1, "UART_TX", net_dict)
        assign_pad_net(j7, 2, "UART_RX", net_dict)
        assign_pad_net(j7, 3, "GND", net_dict)
        print("  J7 (UART) nets assigned")

    # --- USB connector J3 ---
    j3 = fps.get("J3")
    if j3:
        # GCT USB4085 pinout: A1=GND, A4=VBUS, A5=CC1, A6=D+, A7=D-
        # B1=GND, B4=VBUS, B5=CC2, B6=D+, B7=D-
        # Shield=GND
        # Pad names vary — assign by iterating known pad names
        usb_net_map = {
            "A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND",
            "A4": "USB_VBUS", "B4": "USB_VBUS", "A9": "USB_VBUS", "B9": "USB_VBUS",
            "A5": "USB_CC1", "B5": "USB_CC2",
            "A6": "USB_DP", "B6": "USB_DP",
            "A7": "USB_DM", "B7": "USB_DM",
            "S1": "GND", "S2": "GND", "S3": "GND", "S4": "GND",
        }
        for pad in j3.Pads():
            pn = pad.GetNumber()
            if pn in usb_net_map and usb_net_map[pn] in net_dict:
                pad.SetNetCode(net_dict[usb_net_map[pn]])
        print("  J3 (USB-C) nets assigned")

    # --- Decoupling caps: VCC_3V3 + GND ---
    # All 0402 100nF caps get VCC_3V3 on pad 1, GND on pad 2
    cap_refs_100nf = [
        "C_FPGA1", "C_FPGA2", "C_FPGA3", "C_FPGA4",
        "C_SDRAM1", "C_SDRAM2", "C_SDRAM3", "C_SDRAM4",
        "C_RP1", "C_RP2",
        "C_LV1", "C_LV2",
        "C_REG1", "C_REG2",
        "C_USB", "C_FLASH",
    ]
    for cref in cap_refs_100nf:
        cfp = fps.get(cref)
        if cfp:
            assign_pad_net(cfp, 1, "VCC_3V3", net_dict)
            assign_pad_net(cfp, 2, "GND", net_dict)

    # Bulk caps: same
    for cref in ["C_BULK1", "C_BULK2", "C_BULK3"]:
        cfp = fps.get(cref)
        if cfp:
            assign_pad_net(cfp, 1, "VCC_3V3", net_dict)
            assign_pad_net(cfp, 2, "GND", net_dict)

    # Crystal load caps: XTAL pins
    cxl1 = fps.get("C_XL1")
    if cxl1:
        assign_pad_net(cxl1, 1, "XTAL_IN", net_dict)
        assign_pad_net(cxl1, 2, "GND", net_dict)
    cxl2 = fps.get("C_XL2")
    if cxl2:
        assign_pad_net(cxl2, 1, "XTAL_OUT", net_dict)
        assign_pad_net(cxl2, 2, "GND", net_dict)

    # --- USB resistors: 27R on D+/D-, 5.1K CC ---
    r_usb1 = fps.get("R_USB1")
    if r_usb1:
        assign_pad_net(r_usb1, 1, "USB_DP", net_dict)
        assign_pad_net(r_usb1, 2, "USB_DP", net_dict)
    r_usb2 = fps.get("R_USB2")
    if r_usb2:
        assign_pad_net(r_usb2, 1, "USB_DM", net_dict)
        assign_pad_net(r_usb2, 2, "USB_DM", net_dict)
    r_cc1 = fps.get("R_CC1")
    if r_cc1:
        assign_pad_net(r_cc1, 1, "USB_CC1", net_dict)
        assign_pad_net(r_cc1, 2, "GND", net_dict)
    r_cc2 = fps.get("R_CC2")
    if r_cc2:
        assign_pad_net(r_cc2, 1, "USB_CC2", net_dict)
        assign_pad_net(r_cc2, 2, "GND", net_dict)

    # --- LED resistors ---
    for i in range(1, 4):
        rfp = fps.get(f"R_LED{i}")
        if rfp:
            assign_pad_net(rfp, 1, f"LED{i}_NET", net_dict)
            assign_pad_net(rfp, 2, "VCC_3V3", net_dict)

    # --- LEDs ---
    for i in range(1, 4):
        lfp = fps.get(f"LED{i}")
        if lfp:
            assign_pad_net(lfp, 1, f"LED{i}_NET", net_dict)
            assign_pad_net(lfp, 2, "GND", net_dict)

    print("  Passive component nets assigned")

    # -----------------------------------------------------------------------
    # 8. Strip GND and VCC_3V3 pads before DSN export (handled by copper pour)
    # -----------------------------------------------------------------------
    print("\n[8] Stripping GND and VCC_3V3 pad net assignments for copper pour...")
    strip_nets = {"GND", "VCC_3V3"}
    strip_count = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_name = pad.GetNet().GetNetname()
            if net_name in strip_nets:
                pad.SetNetCode(0)
                strip_count += 1
    print(f"  Stripped {strip_count} pads")

    # -----------------------------------------------------------------------
    # 9. Add power zones (GND on In1.Cu, VCC_3V3 on In2.Cu)
    # -----------------------------------------------------------------------
    print("\n[9] Adding power zones...")

    # Board area: roughly X=53-227, Y=24-139 (gold fingers at ~150, avoid 20mm from bottom)
    zone_x1, zone_y1 = 53, 24
    zone_x2, zone_y2 = 227, 130  # 20mm above gold fingers at 150

    def add_zone(layer, net_name):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        if net_name in net_dict:
            z.SetNetCode(net_dict[net_name])
        outline = z.Outline()
        outline.NewOutline()
        outline.Append(pcbnew.FromMM(zone_x1), pcbnew.FromMM(zone_y1))
        outline.Append(pcbnew.FromMM(zone_x2), pcbnew.FromMM(zone_y1))
        outline.Append(pcbnew.FromMM(zone_x2), pcbnew.FromMM(zone_y2))
        outline.Append(pcbnew.FromMM(zone_x1), pcbnew.FromMM(zone_y2))
        board.Add(z)
        print(f"  Added {net_name} zone on layer {layer}")

    add_zone(pcbnew.In1_Cu, "GND")
    add_zone(pcbnew.In2_Cu, "VCC_3V3")

    # -----------------------------------------------------------------------
    # 10. Save PCB
    # -----------------------------------------------------------------------
    print(f"\n[10] Saving PCB to {OUTPUT_PCB}...")
    board.Save(OUTPUT_PCB)
    print("  PCB saved successfully")

    # -----------------------------------------------------------------------
    # 11. Export DSN
    # -----------------------------------------------------------------------
    print(f"\n[11] Exporting Specctra DSN to {DSN_PATH}...")
    try:
        result = pcbnew.ExportSpecctraDSN(board, DSN_PATH)
        if result:
            print("  DSN export successful")
        else:
            print("  DSN export returned False (check file)")
    except Exception as e:
        print(f"  DSN export error: {e}")

    # -----------------------------------------------------------------------
    # 12. Render images
    # -----------------------------------------------------------------------
    print("\n[12] Rendering board images...")
    os.makedirs(PRODUCTION_DIR, exist_ok=True)

    top_png = os.path.join(PRODUCTION_DIR, "neocart_tqfp_top.png")
    persp_png = os.path.join(PRODUCTION_DIR, "neocart_tqfp_perspective.png")

    # Top view
    cmd_top = [
        "kicad-cli", "pcb", "render",
        "--output", top_png,
        "--side", "top",
        "--width", "2000",
        "--height", "1500",
        "--quality", "user",
        OUTPUT_PCB,
    ]
    print(f"  Rendering top view...")
    r = subprocess.run(cmd_top, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  Top view saved to {top_png}")
    else:
        print(f"  Top render failed: {r.stderr.strip()}")

    # Perspective view
    cmd_persp = [
        "kicad-cli", "pcb", "render",
        "--output", persp_png,
        "--perspective",
        "--side", "top",
        "--width", "2000",
        "--height", "1500",
        "--quality", "user",
        "--rotate", "30,0,20",
        OUTPUT_PCB,
    ]
    print(f"  Rendering perspective view...")
    r = subprocess.run(cmd_persp, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  Perspective view saved to {persp_png}")
    else:
        print(f"  Perspective render failed: {r.stderr.strip()}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("BUILD COMPLETE")
    print("=" * 70)
    fp_count = len(list(board.GetFootprints()))
    print(f"  Footprints placed: {fp_count}")
    print(f"  Nets created: {len(net_dict)}")
    print(f"  PCB: {OUTPUT_PCB}")
    print(f"  DSN: {DSN_PATH}")
    print(f"  Top render: {top_png}")
    print(f"  Perspective render: {persp_png}")


if __name__ == "__main__":
    main()
