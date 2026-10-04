#!/usr/bin/env python3
"""
route_fpga.py — Assign nets to pads on the FPGA PROG PCB and auto-route with Freerouting.

Steps:
  1. Load the PCB with pcbnew.LoadBoard()
  2. Create all necessary nets
  3. Assign nets to pads on each footprint
  4. Export DSN for Freerouting (stripping GND/VCC_3V3 power nets)
  5. Run Freerouting auto-router
  6. Import .ses results back
  7. Save and render with kicad-cli
"""

import os
import sys
import subprocess
import pcbnew

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FPGA_DIR   = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/fpga"
PROD_DIR   = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production"
PCB_PATH   = os.path.join(FPGA_DIR, "neocart_fpga_prog.kicad_pcb")
DSN_PATH   = os.path.join(FPGA_DIR, "neocart_fpga_prog.dsn")
SES_PATH   = os.path.join(FPGA_DIR, "neocart_fpga_prog.ses")

JAVA_BIN   = "/usr/lib/jvm/java-21-openjdk-amd64/bin/java"
FREEROUTER = "/tmp/freerouting/freerouting-2.1.0.jar"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_fp(board, ref):
    """Find a footprint by reference. Returns None if not found."""
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            return fp
    return None

def pad_map(fp):
    """Return dict mapping pad_number -> list of PAD objects."""
    result = {}
    for pad in fp.Pads():
        num = pad.GetNumber()
        result.setdefault(num, []).append(pad)
    return result

def assign_net_to_pad(fp, pad_num, net_code, net_name=""):
    """Assign a net to all pads with the given number on a footprint."""
    count = 0
    for pad in fp.Pads():
        if pad.GetNumber() == pad_num:
            pad.SetNetCode(net_code)
            count += 1
    if count == 0:
        print(f"    WARNING: pad {pad_num} not found on {fp.GetReference()}")
    return count

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
# NET CREATION
# ===========================================================================
def create_all_nets(board):
    """Create every net the board needs. Returns dict name -> net_code."""
    net_names = []

    # Power nets (already exist as 1=GND, 2=VCC_3V3, but we add more)
    net_names += ["VCC_5V", "VCC_1V1"]

    # -----------------------------------------------------------------------
    # 68k PROG bus signals (5V side, on edge connectors)
    # -----------------------------------------------------------------------
    net_names += [f"PD{i}" for i in range(16)]     # PD0-PD15 data
    net_names += [f"PA{i}" for i in range(18)]     # PA0-PA17 address
    net_names += ["nRW", "ROMOEU", "ROMOEL", "ROMOE"]

    # M/V ROM bus signals
    net_names += [f"MA{i}" for i in range(17)]     # MA0-MA16
    net_names += [f"MD{i}" for i in range(8)]      # MD0-MD7
    net_names += ["SDROE"]

    # -----------------------------------------------------------------------
    # FPGA-side data bus (3.3V, after level shifters)
    # -----------------------------------------------------------------------
    net_names += [f"FPGA_PD{i}" for i in range(16)]

    # -----------------------------------------------------------------------
    # SDRAM signals
    # -----------------------------------------------------------------------
    net_names += [f"SDRAM_A{i}" for i in range(13)]    # A0-A12
    net_names += ["SDRAM_BA0", "SDRAM_BA1"]
    net_names += [f"SDRAM_DQ{i}" for i in range(16)]   # DQ0-DQ15
    net_names += ["SDRAM_CKE", "SDRAM_CLK",
                  "SDRAM_CS0N", "SDRAM_CS1N",
                  "SDRAM_RASN", "SDRAM_CASN", "SDRAM_WEN",
                  "SDRAM_DQM0", "SDRAM_DQM1"]

    # -----------------------------------------------------------------------
    # RP2040 signals
    # -----------------------------------------------------------------------
    net_names += [f"RP_GPIO{i}" for i in range(30)]
    net_names += ["RP_USB_DP", "RP_USB_DM", "RP_DVDD", "RP_RUN", "RP_XIN", "RP_XOUT"]
    net_names += ["RP_QSPI_CS", "RP_QSPI_CLK",
                  "RP_QSPI_D0", "RP_QSPI_D1", "RP_QSPI_D2", "RP_QSPI_D3"]
    net_names += ["RP_SWD_CLK", "RP_SWD_IO"]

    # -----------------------------------------------------------------------
    # SPI Flash signals
    # -----------------------------------------------------------------------
    net_names += ["FLASH_RP_CS", "FLASH_RP_CLK", "FLASH_RP_DI", "FLASH_RP_DO",
                  "FLASH_RP_WP", "FLASH_RP_HOLD"]
    net_names += ["FLASH_FPGA_CS", "FLASH_FPGA_CLK", "FLASH_FPGA_DI", "FLASH_FPGA_DO",
                  "FLASH_FPGA_WP", "FLASH_FPGA_HOLD"]

    # -----------------------------------------------------------------------
    # Inter-board signals
    # -----------------------------------------------------------------------
    net_names += [f"INTER_{i}" for i in range(1, 101)]

    # -----------------------------------------------------------------------
    # Level shifter control
    # -----------------------------------------------------------------------
    net_names += ["XCVR_DIR", "XCVR_OE"]

    # -----------------------------------------------------------------------
    # USB-C
    # -----------------------------------------------------------------------
    net_names += ["USB_DP", "USB_DM", "USB_VBUS", "USB_CC1", "USB_CC2"]

    # -----------------------------------------------------------------------
    # microSD
    # -----------------------------------------------------------------------
    net_names += ["SD_CMD", "SD_CLK", "SD_D0", "SD_D1", "SD_D2", "SD_D3",
                  "SD_CD", "SD_VDD"]

    # -----------------------------------------------------------------------
    # JTAG
    # -----------------------------------------------------------------------
    net_names += ["JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO"]

    # -----------------------------------------------------------------------
    # UART
    # -----------------------------------------------------------------------
    net_names += ["UART_TX", "UART_RX"]

    # -----------------------------------------------------------------------
    # Crystal
    # -----------------------------------------------------------------------
    net_names += ["XIN", "XOUT"]

    # -----------------------------------------------------------------------
    # LEDs
    # -----------------------------------------------------------------------
    net_names += ["LED_PWR", "LED_ACT", "LED_USR"]

    # -----------------------------------------------------------------------
    # Buttons
    # -----------------------------------------------------------------------
    net_names += ["nBOOTSEL", "nRESET"]

    # Deduplicate and remove existing nets
    existing = {"", "GND", "VCC_3V3"}
    net_names = [n for n in net_names if n not in existing]
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for n in net_names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    net_names = unique

    print(f"  Creating {len(net_names)} new nets...")

    # Create net objects. Start IDs after existing (0=unconnected, 1=GND, 2=VCC_3V3)
    net_map = {}
    # First, record existing nets
    net_map["GND"] = 1
    net_map["VCC_3V3"] = 2

    next_id = 3
    for name in net_names:
        ni = pcbnew.NETINFO_ITEM(board, name, next_id)
        board.Add(ni)
        net_map[name] = next_id
        next_id += 1

    print(f"  Total nets: {next_id} (IDs 0-{next_id-1})")
    return net_map


# ===========================================================================
# PAD-TO-NET ASSIGNMENT
# ===========================================================================
def assign_all_nets(board, nm):
    """Assign nets to pads on every footprint."""

    # -------------------------------------------------------------------
    # J2: A-side (CTRG2) edge connector — 60 pads
    # -------------------------------------------------------------------
    print("\n  Assigning J2 (A-side edge connector)...")
    j2 = find_fp(board, "J2")
    if j2:
        j2_map = {
            # GND pads
            "1": "GND", "2": "GND", "3": "GND", "4": "GND",
            "58": "GND", "59": "GND", "60": "GND",
            # PD0-PD15 on pads 5-20
            "5": "PD0", "6": "PD1", "7": "PD2", "8": "PD3",
            "9": "PD4", "10": "PD5", "11": "PD6", "12": "PD7",
            "13": "PD8", "14": "PD9", "15": "PD10", "16": "PD11",
            "17": "PD12", "18": "PD13", "19": "PD14", "20": "PD15",
            # Control
            "21": "nRW",
            "23": "ROMOEU", "24": "ROMOEL",
            "33": "ROMOE",
            # Power
            "29": "VCC_5V", "30": "VCC_5V", "31": "VCC_5V", "32": "VCC_5V",
            # M/V ROM address and control
            "47": "MA8", "48": "MA9", "49": "MA10", "50": "MA11",
            "51": "MA12", "52": "MA13", "53": "MA14", "54": "MA15",
            "55": "MA16", "56": "SDROE",
        }
        for pad_num, net_name in j2_map.items():
            if net_name in nm:
                assign_net_to_pad(j2, pad_num, nm[net_name], net_name)
        print(f"    Assigned {len(j2_map)} pads on J2")
    else:
        print("    WARNING: J2 not found!")

    # -------------------------------------------------------------------
    # J1: B-side (CTRG2) edge connector — 60 pads
    # -------------------------------------------------------------------
    print("  Assigning J1 (B-side edge connector)...")
    j1 = find_fp(board, "J1")
    if j1:
        j1_map = {
            # GND pads
            "1": "GND", "2": "GND", "3": "GND", "4": "GND",
            "58": "GND", "59": "GND", "60": "GND",
            # PA0-PA15 on pads 5-20
            "5": "PA0", "6": "PA1", "7": "PA2", "8": "PA3",
            "9": "PA4", "10": "PA5", "11": "PA6", "12": "PA7",
            "13": "PA8", "14": "PA9", "15": "PA10", "16": "PA11",
            "17": "PA12", "18": "PA13", "19": "PA14", "20": "PA15",
            # Address extension
            "21": "PA16", "22": "PA17",
            # Power
            "29": "VCC_5V", "30": "VCC_5V", "31": "VCC_5V", "32": "VCC_5V",
            # MD0-MD7 on pads 40-47
            "40": "MD0", "41": "MD1", "42": "MD2", "43": "MD3",
            "44": "MD4", "45": "MD5", "46": "MD6", "47": "MD7",
            # MA0-MA7 on pads 48-55
            "48": "MA0", "49": "MA1", "50": "MA2", "51": "MA3",
            "52": "MA4", "53": "MA5", "54": "MA6", "55": "MA7",
            "56": "SDROE",
        }
        for pad_num, net_name in j1_map.items():
            if net_name in nm:
                assign_net_to_pad(j1, pad_num, nm[net_name], net_name)
        print(f"    Assigned {len(j1_map)} pads on J1")
    else:
        print("    WARNING: J1 not found!")

    # -------------------------------------------------------------------
    # U2, U3: SDRAM (TSOP-54)
    # -------------------------------------------------------------------
    sdram_pin_map = {
        # Power — VCC pins
        "1": "VCC_3V3", "2": "VCC_3V3", "7": "VCC_3V3", "24": "VCC_3V3",
        "31": "VCC_3V3", "42": "VCC_3V3", "48": "VCC_3V3", "54": "VCC_3V3",
        # Ground — VSS pins
        "27": "GND", "28": "GND", "43": "GND", "49": "GND",
        # Data
        "3": "SDRAM_DQ0", "4": "SDRAM_DQ1", "5": "SDRAM_DQ2", "6": "SDRAM_DQ3",
        "38": "SDRAM_DQ4", "39": "SDRAM_DQ5", "40": "SDRAM_DQ6", "41": "SDRAM_DQ7",
        "44": "SDRAM_DQ8", "45": "SDRAM_DQ9", "46": "SDRAM_DQ10", "47": "SDRAM_DQ11",
        "50": "SDRAM_DQ12", "51": "SDRAM_DQ13", "52": "SDRAM_DQ14", "53": "SDRAM_DQ15",
        # DQM
        "8": "SDRAM_DQM0", "34": "SDRAM_DQM1",
        # Control
        "9": "SDRAM_WEN", "10": "SDRAM_CASN", "11": "SDRAM_RASN",
        # Bank address
        "13": "SDRAM_BA0", "14": "SDRAM_BA1",
        # Address
        "15": "SDRAM_A10", "16": "SDRAM_A0",
        "17": "SDRAM_A1", "18": "SDRAM_A2", "19": "SDRAM_A3", "20": "SDRAM_A4",
        "21": "SDRAM_A5", "22": "SDRAM_A6", "23": "SDRAM_A7",
        "25": "SDRAM_A8", "26": "SDRAM_A9",
        "29": "SDRAM_A11", "30": "SDRAM_A12",
        # Clock
        "32": "SDRAM_CLK", "33": "SDRAM_CKE",
        # NC/unused pins: 35, 36, 37 (depending on package)
    }

    for ref, cs_net in [("U2", "SDRAM_CS0N"), ("U3", "SDRAM_CS1N")]:
        print(f"  Assigning {ref} (SDRAM)...")
        fp = find_fp(board, ref)
        if fp:
            for pad_num, net_name in sdram_pin_map.items():
                if net_name in nm:
                    assign_net_to_pad(fp, pad_num, nm[net_name], net_name)
            # CS# pin (pin 12) is unique per chip
            assign_net_to_pad(fp, "12", nm[cs_net], cs_net)
            print(f"    Assigned SDRAM pads on {ref} (CS={cs_net})")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # U7, U8: 74LVC245 level shifters (SOIC-20)
    # -------------------------------------------------------------------
    for ref, bit_offset in [("U7", 0), ("U8", 8)]:
        print(f"  Assigning {ref} (74LVC245 D{bit_offset}-D{bit_offset+7})...")
        fp = find_fp(board, ref)
        if fp:
            # Pin 1: DIR, Pin 19: OE#
            assign_net_to_pad(fp, "1", nm["XCVR_DIR"])
            assign_net_to_pad(fp, "19", nm["XCVR_OE"])
            # Pin 20: VCC (5V side), Pin 10: GND
            assign_net_to_pad(fp, "20", nm["VCC_5V"])
            assign_net_to_pad(fp, "10", nm["GND"])
            # A-side (5V): pins 2-9 = PD[offset+0..offset+7]
            for i in range(8):
                assign_net_to_pad(fp, str(2 + i), nm[f"PD{bit_offset + i}"])
            # B-side (3.3V): pins 18-11 = FPGA_PD[offset+0..offset+7]
            for i in range(8):
                assign_net_to_pad(fp, str(18 - i), nm[f"FPGA_PD{bit_offset + i}"])
            print(f"    Assigned 20 pads on {ref}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # U4: RP2040 (QFN-56)
    # RP2040 pinout (from datasheet):
    #   1=IOVDD, 2=GPIO0, 3=GPIO1, 4=GPIO2, 5=GPIO3, 6=GPIO4, 7=GPIO5,
    #   8=GPIO6, 9=GPIO7, 10=IOVDD, 11=GPIO8, 12=GPIO9, 13=GPIO10,
    #   14=GPIO11, 15=GPIO12, 16=GPIO13, 17=GPIO14, 18=GPIO15,
    #   19=TESTEN(GND), 20=XIN, 21=XOUT, 22=IOVDD, 23=DVDD,
    #   24=SWCLK, 25=SWD, 26=RUN, 27=GPIO16, 28=GPIO17,
    #   29=GPIO18, 30=GPIO19, 31=GPIO20, 32=GPIO21,
    #   33=IOVDD, 34=GPIO22, 35=GPIO23, 36=GPIO24, 37=GPIO25,
    #   38=GPIO26, 39=GPIO27, 40=GPIO28, 41=GPIO29,
    #   42=IOVDD, 43=ADC_AVDD, 44=VREG_VIN, 45=VREG_VOUT,
    #   46=USB_DM, 47=USB_DP, 48=IOVDD,
    #   49=QSPI_SD3, 50=QSPI_SCLK, 51=QSPI_SD0,
    #   52=QSPI_SD2, 53=QSPI_SD1, 54=QSPI_SS,
    #   55=IOVDD, 56=DVDD,
    #   57=GND_PAD (exposed pad)
    # -------------------------------------------------------------------
    print("  Assigning U4 (RP2040)...")
    u4 = find_fp(board, "U4")
    if u4:
        rp_map = {
            # IOVDD pins -> VCC_3V3
            "1": "VCC_3V3", "10": "VCC_3V3", "22": "VCC_3V3",
            "33": "VCC_3V3", "42": "VCC_3V3", "48": "VCC_3V3", "55": "VCC_3V3",
            # DVDD
            "23": "RP_DVDD", "56": "RP_DVDD",
            # GPIO0-GPIO29
            "2": "RP_GPIO0", "3": "RP_GPIO1", "4": "RP_GPIO2", "5": "RP_GPIO3",
            "6": "RP_GPIO4", "7": "RP_GPIO5", "8": "RP_GPIO6", "9": "RP_GPIO7",
            "11": "RP_GPIO8", "12": "RP_GPIO9", "13": "RP_GPIO10", "14": "RP_GPIO11",
            "15": "RP_GPIO12", "16": "RP_GPIO13", "17": "RP_GPIO14", "18": "RP_GPIO15",
            "27": "RP_GPIO16", "28": "RP_GPIO17", "29": "RP_GPIO18", "30": "RP_GPIO19",
            "31": "RP_GPIO20", "32": "RP_GPIO21", "34": "RP_GPIO22", "35": "RP_GPIO23",
            "36": "RP_GPIO24", "37": "RP_GPIO25", "38": "RP_GPIO26", "39": "RP_GPIO27",
            "40": "RP_GPIO28", "41": "RP_GPIO29",
            # Special
            "19": "GND",          # TESTEN -> GND
            "20": "RP_XIN",
            "21": "RP_XOUT",
            "24": "RP_SWD_CLK",
            "25": "RP_SWD_IO",
            "26": "RP_RUN",
            "43": "VCC_3V3",      # ADC_AVDD
            "44": "VCC_3V3",      # VREG_VIN
            "45": "RP_DVDD",      # VREG_VOUT -> 1.1V core
            "46": "RP_USB_DM",
            "47": "RP_USB_DP",
            # QSPI
            "49": "RP_QSPI_D3", "50": "RP_QSPI_CLK", "51": "RP_QSPI_D0",
            "52": "RP_QSPI_D2", "53": "RP_QSPI_D1", "54": "RP_QSPI_CS",
            # Exposed pad
            "57": "GND",
        }
        for pad_num, net_name in rp_map.items():
            if net_name in nm:
                assign_net_to_pad(u4, pad_num, nm[net_name], net_name)
        # Also assign the unnamed thermal pads (empty string pad number) to GND
        for pad in u4.Pads():
            if pad.GetNumber() == "":
                pad.SetNetCode(nm["GND"])
        print(f"    Assigned RP2040 pads")
    else:
        print("    WARNING: U4 not found!")

    # -------------------------------------------------------------------
    # U5: W25Q32 SPI Flash for RP2040
    # SOIC-8: 1=CS#, 2=DO, 3=WP#, 4=GND, 5=DI, 6=CLK, 7=HOLD#, 8=VCC
    # -------------------------------------------------------------------
    print("  Assigning U5 (RP2040 Flash)...")
    u5 = find_fp(board, "U5")
    if u5:
        u5_map = {
            "1": "FLASH_RP_CS", "2": "FLASH_RP_DO", "3": "FLASH_RP_WP",
            "4": "GND", "5": "FLASH_RP_DI", "6": "FLASH_RP_CLK",
            "7": "FLASH_RP_HOLD", "8": "VCC_3V3",
        }
        for pad_num, net_name in u5_map.items():
            assign_net_to_pad(u5, pad_num, nm[net_name], net_name)
        # Connect RP2040 QSPI to flash
        # RP_QSPI_CS->FLASH_RP_CS, RP_QSPI_CLK->FLASH_RP_CLK,
        # RP_QSPI_D0->FLASH_RP_DI, RP_QSPI_D1->FLASH_RP_DO
        print("    Assigned U5 Flash pads")
    else:
        print("    WARNING: U5 not found!")

    # -------------------------------------------------------------------
    # U6: W25Q32 SPI Flash for FPGA configuration
    # SOIC-8: same pinout
    # -------------------------------------------------------------------
    print("  Assigning U6 (FPGA Config Flash)...")
    u6 = find_fp(board, "U6")
    if u6:
        u6_map = {
            "1": "FLASH_FPGA_CS", "2": "FLASH_FPGA_DO", "3": "FLASH_FPGA_WP",
            "4": "GND", "5": "FLASH_FPGA_DI", "6": "FLASH_FPGA_CLK",
            "7": "FLASH_FPGA_HOLD", "8": "VCC_3V3",
        }
        for pad_num, net_name in u6_map.items():
            assign_net_to_pad(u6, pad_num, nm[net_name], net_name)
        print("    Assigned U6 Flash pads")
    else:
        print("    WARNING: U6 not found!")

    # -------------------------------------------------------------------
    # U9: AMS1117-3.3 voltage regulator (SOT-223)
    # Pin 1=GND, Pin 2=VOUT(3V3), Pin 3=VIN(5V), Pin 4(tab)=VOUT(3V3)
    # -------------------------------------------------------------------
    print("  Assigning U9 (3.3V regulator)...")
    u9 = find_fp(board, "U9")
    if u9:
        assign_net_to_pad(u9, "1", nm["GND"])
        assign_net_to_pad(u9, "2", nm["VCC_3V3"])
        assign_net_to_pad(u9, "3", nm["VCC_5V"])
        print("    Assigned U9 pads")
    else:
        print("    WARNING: U9 not found!")

    # -------------------------------------------------------------------
    # U10: AMS1117-1.1 voltage regulator (SOT-223)
    # Pin 1=GND, Pin 2=VOUT(1V1), Pin 3=VIN(3V3), Pin 4(tab)=VOUT(1V1)
    # -------------------------------------------------------------------
    print("  Assigning U10 (1.1V regulator)...")
    u10 = find_fp(board, "U10")
    if u10:
        assign_net_to_pad(u10, "1", nm["GND"])
        assign_net_to_pad(u10, "2", nm["VCC_1V1"])
        assign_net_to_pad(u10, "3", nm["VCC_3V3"])
        print("    Assigned U10 pads")
    else:
        print("    WARNING: U10 not found!")

    # -------------------------------------------------------------------
    # J5A, J5B: Inter-board pin headers (2x25 = 50 pads each)
    # -------------------------------------------------------------------
    for ref, offset in [("J5A", 0), ("J5B", 50)]:
        print(f"  Assigning {ref} (inter-board)...")
        fp = find_fp(board, ref)
        if fp:
            for i in range(1, 51):
                net_name = f"INTER_{offset + i}"
                if net_name in nm:
                    assign_net_to_pad(fp, str(i), nm[net_name], net_name)
            print(f"    Assigned 50 pads on {ref}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # J3: USB-C connector
    # GCT USB4085 pin mapping:
    #   A1=GND, A4=VBUS, A5=CC1, A6=D+, A7=D-, A8=SBU1,
    #   A9=VBUS, A12=GND
    #   B1=GND, B4=VBUS, B5=CC2, B6=D+, B7=D-, B8=SBU2,
    #   B9=VBUS, B12=GND
    #   S1=shield=GND (4 pads)
    # -------------------------------------------------------------------
    print("  Assigning J3 (USB-C)...")
    j3 = find_fp(board, "J3")
    if j3:
        j3_map = {
            "A1": "GND", "A4": "USB_VBUS", "A5": "USB_CC1",
            "A6": "USB_DP", "A7": "USB_DM",
            "A9": "USB_VBUS", "A12": "GND",
            "B1": "GND", "B4": "USB_VBUS", "B5": "USB_CC2",
            "B6": "USB_DP", "B7": "USB_DM",
            "B9": "USB_VBUS", "B12": "GND",
            "S1": "GND",  # shield pads (multiple pads share this number)
        }
        for pad_num, net_name in j3_map.items():
            if net_name in nm:
                assign_net_to_pad(j3, pad_num, nm[net_name], net_name)
        print("    Assigned USB-C pads")
    else:
        print("    WARNING: J3 not found!")

    # -------------------------------------------------------------------
    # J4: microSD connector
    # Molex 47219-2001 pin mapping:
    #   1=CD/DAT3, 2=CMD, 3=VSS, 4=VDD, 5=CLK, 6=VSS, 7=DAT0, 8=DAT1, 9=DAT2
    #   Shell pads (9 duplicates) = GND
    # -------------------------------------------------------------------
    print("  Assigning J4 (microSD)...")
    j4 = find_fp(board, "J4")
    if j4:
        j4_map = {
            "1": "SD_D3", "2": "SD_CMD", "3": "GND", "4": "VCC_3V3",
            "5": "SD_CLK", "6": "GND", "7": "SD_D0", "8": "SD_D1",
        }
        for pad_num, net_name in j4_map.items():
            if net_name in nm:
                assign_net_to_pad(j4, pad_num, nm[net_name], net_name)
        # pad 9 is shell/GND (multiple pads share this number)
        assign_net_to_pad(j4, "9", nm["GND"])
        print("    Assigned microSD pads")
    else:
        print("    WARNING: J4 not found!")

    # -------------------------------------------------------------------
    # J6: JTAG header (2x3)
    # 1=TCK, 2=GND, 3=TDO, 4=VCC_3V3, 5=TMS, 6=TDI
    # -------------------------------------------------------------------
    print("  Assigning J6 (JTAG)...")
    j6 = find_fp(board, "J6")
    if j6:
        j6_map = {
            "1": "JTAG_TCK", "2": "GND", "3": "JTAG_TDO",
            "4": "VCC_3V3", "5": "JTAG_TMS", "6": "JTAG_TDI",
        }
        for pad_num, net_name in j6_map.items():
            if net_name in nm:
                assign_net_to_pad(j6, pad_num, nm[net_name], net_name)
        print("    Assigned JTAG pads")
    else:
        print("    WARNING: J6 not found!")

    # -------------------------------------------------------------------
    # J7: UART header (1x3)
    # 1=TX, 2=RX, 3=GND
    # -------------------------------------------------------------------
    print("  Assigning J7 (UART)...")
    j7 = find_fp(board, "J7")
    if j7:
        j7_map = {"1": "UART_TX", "2": "UART_RX", "3": "GND"}
        for pad_num, net_name in j7_map.items():
            if net_name in nm:
                assign_net_to_pad(j7, pad_num, nm[net_name], net_name)
        print("    Assigned UART pads")
    else:
        print("    WARNING: J7 not found!")

    # -------------------------------------------------------------------
    # Y1: 12MHz Crystal
    # Pad 1=XIN, Pad 2=XOUT
    # -------------------------------------------------------------------
    print("  Assigning Y1 (crystal)...")
    y1 = find_fp(board, "Y1")
    if y1:
        assign_net_to_pad(y1, "1", nm["XIN"])
        assign_net_to_pad(y1, "2", nm["XOUT"])
        print("    Assigned crystal pads")
    else:
        print("    WARNING: Y1 not found!")

    # -------------------------------------------------------------------
    # SW1, SW2: Buttons
    # SW_SPST: 1=one side (input), 2=other side (GND)
    # -------------------------------------------------------------------
    print("  Assigning SW1 (BOOTSEL), SW2 (RESET)...")
    for ref, net in [("SW1", "nBOOTSEL"), ("SW2", "nRESET")]:
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[net])
            assign_net_to_pad(fp, "2", nm["GND"])
            print(f"    Assigned {ref}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # LEDs: LED1=PWR, LED2=ACT, LED3=USR
    # Pad 1=anode (to resistor), Pad 2=cathode (to GND via resistor)
    # LED anode gets the LED net, cathode gets GND
    # -------------------------------------------------------------------
    print("  Assigning LEDs...")
    for ref, net in [("LED1", "LED_PWR"), ("LED2", "LED_ACT"), ("LED3", "LED_USR")]:
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[net])    # anode
            assign_net_to_pad(fp, "2", nm["GND"])   # cathode
            print(f"    Assigned {ref}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # LED resistors: R11-R13
    # Pad 1 = VCC_3V3 (power), Pad 2 = LED_xxx (to LED anode)
    # -------------------------------------------------------------------
    print("  Assigning LED resistors R11-R13...")
    for ref, led_net in [("R11", "LED_PWR"), ("R12", "LED_ACT"), ("R13", "LED_USR")]:
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm["VCC_3V3"])
            assign_net_to_pad(fp, "2", nm[led_net])
            print(f"    Assigned {ref}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # USB resistors: R14-R17
    # R14: CC1 pull-down (5.1K) — pad1=USB_CC1, pad2=GND
    # R15: CC2 pull-down (5.1K) — pad1=USB_CC2, pad2=GND
    # R16: D+ series (27R) — pad1=USB_DP, pad2=RP_USB_DP
    # R17: D- series (27R) — pad1=USB_DM, pad2=RP_USB_DM
    # -------------------------------------------------------------------
    print("  Assigning USB resistors R14-R17...")
    usb_r_map = {
        "R14": ("USB_CC1", "GND"),
        "R15": ("USB_CC2", "GND"),
        "R16": ("USB_DP", "RP_USB_DP"),
        "R17": ("USB_DM", "RP_USB_DM"),
    }
    for ref, (net1, net2) in usb_r_map.items():
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[net1])
            assign_net_to_pad(fp, "2", nm[net2])
            print(f"    Assigned {ref}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # Series resistors R1-R10: data bus protection between edge conn & FPGA
    # These sit between FPGA_PD signals and the bus transceiver outputs.
    # For routing purposes, connect them to meaningful signal nets.
    # R1-R5: FPGA control/address signals, R6-R10: more of the same
    # Let's assign:
    #   R1: pad1=PA0, pad2=RP_GPIO0 (address passthrough to RP2040 monitoring)
    #   ... etc. For now, generic signal net assignment:
    # -------------------------------------------------------------------
    print("  Assigning series resistors R1-R10...")
    series_r = {
        "R1":  ("PA0",  "RP_GPIO8"),
        "R2":  ("PA1",  "RP_GPIO9"),
        "R3":  ("PA2",  "RP_GPIO10"),
        "R4":  ("PA3",  "RP_GPIO11"),
        "R5":  ("PA4",  "RP_GPIO12"),
        "R6":  ("PA5",  "RP_GPIO13"),
        "R7":  ("PA6",  "RP_GPIO14"),
        "R8":  ("PA7",  "RP_GPIO15"),
        "R9":  ("nRW",  "RP_GPIO16"),
        "R10": ("ROMOE","RP_GPIO17"),
    }
    for ref, (net1, net2) in series_r.items():
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[net1])
            assign_net_to_pad(fp, "2", nm[net2])
            print(f"    Assigned {ref}: {net1} <-> {net2}")
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # Decoupling caps: C1-C21 (0402, 100nF)
    # Each: pad1 = power net, pad2 = GND
    # Group by proximity to IC
    # -------------------------------------------------------------------
    print("  Assigning decoupling caps C1-C21...")
    # C1-C8: near FPGA (VCC_3V3)
    # C9-C11: near U2 SDRAM (VCC_3V3)
    # C12-C14: near U3 SDRAM (VCC_3V3)
    # C15-C17: near RP2040 (VCC_3V3)
    # C18-C19: near bus transceivers (VCC_5V)
    # C20: near U5 flash (VCC_3V3)
    # C21: near U6 flash (VCC_3V3)
    decap_nets = {
        "C1": "VCC_3V3", "C2": "VCC_3V3", "C3": "VCC_3V3", "C4": "VCC_3V3",
        "C5": "VCC_3V3", "C6": "VCC_3V3", "C7": "VCC_3V3", "C8": "VCC_3V3",
        "C9": "VCC_3V3", "C10": "VCC_3V3", "C11": "VCC_3V3",
        "C12": "VCC_3V3", "C13": "VCC_3V3", "C14": "VCC_3V3",
        "C15": "VCC_3V3", "C16": "VCC_3V3", "C17": "VCC_3V3",
        "C18": "VCC_5V", "C19": "VCC_5V",
        "C20": "VCC_3V3", "C21": "VCC_3V3",
    }
    for ref, pwr_net in decap_nets.items():
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[pwr_net])
            assign_net_to_pad(fp, "2", nm["GND"])
        else:
            print(f"    WARNING: {ref} not found!")
    print(f"    Assigned {len(decap_nets)} decoupling caps")

    # -------------------------------------------------------------------
    # Bulk caps: C22-C24 (0805, 10uF)
    # C22: near U9 input (VCC_5V / GND)
    # C23: near U10 input (VCC_3V3 / GND)
    # C24: between regulators output (VCC_3V3 / GND)
    # -------------------------------------------------------------------
    print("  Assigning bulk caps C22-C24...")
    bulk_map = {"C22": "VCC_5V", "C23": "VCC_3V3", "C24": "VCC_3V3"}
    for ref, pwr_net in bulk_map.items():
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[pwr_net])
            assign_net_to_pad(fp, "2", nm["GND"])
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # Crystal load caps: C25, C26
    # C25: pad1=XIN, pad2=GND
    # C26: pad1=XOUT, pad2=GND
    # -------------------------------------------------------------------
    print("  Assigning crystal load caps C25-C26...")
    for ref, xnet in [("C25", "XIN"), ("C26", "XOUT")]:
        fp = find_fp(board, ref)
        if fp:
            assign_net_to_pad(fp, "1", nm[xnet])
            assign_net_to_pad(fp, "2", nm["GND"])
        else:
            print(f"    WARNING: {ref} not found!")

    # -------------------------------------------------------------------
    # U1: ECP5 FPGA (BGA-256) — leave unassigned per instructions
    # The FPGA pin assignment is flexible and will be done during routing.
    # -------------------------------------------------------------------
    print("  U1 (ECP5 FPGA): Skipping pad assignment (flexible pin mapping)")


# ===========================================================================
# POWER NET STRIPPING FOR DSN EXPORT
# ===========================================================================
POWER_NETS = {"GND", "VCC_3V3"}

def strip_power_from_dsn(dsn_path):
    """
    Read the DSN file and remove all references to power nets.
    This prevents Freerouting from hanging on high-fanout nets.
    Power delivery is handled by copper pour planes on In1.Cu and In2.Cu.
    """
    print(f"  Stripping power nets from DSN: {POWER_NETS}")
    with open(dsn_path, "r") as f:
        content = f.read()

    # Replace net references in pin assignments
    # In Specctra DSN, net names appear in (net <name>) entries
    for net_name in POWER_NETS:
        # Remove net declarations and references
        # The DSN format uses quoted or unquoted net names
        # Replace pin->net bindings for power nets with empty net
        import re
        # Replace (net "GND") or (net GND) with (net "")
        content = re.sub(
            rf'\(net\s+"{re.escape(net_name)}"\)',
            '(net "")',
            content
        )
        content = re.sub(
            rf'\(net\s+{re.escape(net_name)}\b(?!")\)',
            '(net "")',
            content
        )

    with open(dsn_path, "w") as f:
        f.write(content)
    print("  Power nets stripped from DSN")


def restore_power_nets(board, nm):
    """
    After Freerouting, re-assign power nets to all pads that had them.
    """
    print("  Restoring power net assignments...")
    # We need to re-run the assignment for power pads
    # Walk all footprints and re-assign based on our known mapping
    # This is simpler than tracking state — just re-assign all power pads

    # Helper: assign power to specific pad numbers on a footprint
    def set_power(ref, pad_net_map):
        fp = find_fp(board, ref)
        if not fp:
            return
        for pad_num, net_name in pad_net_map.items():
            if net_name in POWER_NETS and net_name in nm:
                assign_net_to_pad(fp, pad_num, nm[net_name])

    # Edge connectors
    set_power("J2", {"1": "GND", "2": "GND", "3": "GND", "4": "GND",
                      "58": "GND", "59": "GND", "60": "GND"})
    set_power("J1", {"1": "GND", "2": "GND", "3": "GND", "4": "GND",
                      "58": "GND", "59": "GND", "60": "GND"})

    # SDRAM
    for ref in ["U2", "U3"]:
        set_power(ref, {"1": "VCC_3V3", "2": "VCC_3V3", "7": "VCC_3V3",
                        "24": "VCC_3V3", "27": "GND", "28": "GND",
                        "31": "VCC_3V3", "42": "VCC_3V3", "43": "GND",
                        "48": "VCC_3V3", "49": "GND", "54": "VCC_3V3"})

    # RP2040
    set_power("U4", {"1": "VCC_3V3", "10": "VCC_3V3", "19": "GND",
                      "22": "VCC_3V3", "33": "VCC_3V3", "42": "VCC_3V3",
                      "43": "VCC_3V3", "44": "VCC_3V3", "48": "VCC_3V3",
                      "55": "VCC_3V3", "57": "GND"})
    # RP2040 unnamed thermal pads
    u4 = find_fp(board, "U4")
    if u4:
        for pad in u4.Pads():
            if pad.GetNumber() == "":
                pad.SetNetCode(nm["GND"])

    # Bus transceivers
    for ref in ["U7", "U8"]:
        set_power(ref, {"10": "GND"})

    # Flash
    set_power("U5", {"4": "GND", "8": "VCC_3V3"})
    set_power("U6", {"4": "GND", "8": "VCC_3V3"})

    # Regulators
    set_power("U9", {"1": "GND", "2": "VCC_3V3"})
    set_power("U10", {"1": "GND", "3": "VCC_3V3"})

    # USB-C
    set_power("J3", {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND"})

    # microSD
    set_power("J4", {"3": "GND", "4": "VCC_3V3", "6": "GND", "9": "GND"})

    # JTAG, UART
    set_power("J6", {"2": "GND", "4": "VCC_3V3"})
    set_power("J7", {"3": "GND"})

    # Buttons
    for ref in ["SW1", "SW2"]:
        set_power(ref, {"2": "GND"})

    # LEDs
    for ref in ["LED1", "LED2", "LED3"]:
        set_power(ref, {"2": "GND"})

    # Resistors
    for ref in ["R11", "R12", "R13"]:
        set_power(ref, {"1": "VCC_3V3"})
    for ref in ["R14", "R15"]:
        set_power(ref, {"2": "GND"})

    # All decoupling/bulk caps
    for i in range(1, 27):
        ref = f"C{i}"
        set_power(ref, {"2": "GND"})
    # Caps with VCC_3V3 on pad 1
    for ref in ["C1","C2","C3","C4","C5","C6","C7","C8",
                "C9","C10","C11","C12","C13","C14",
                "C15","C16","C17","C20","C21","C23","C24"]:
        set_power(ref, {"1": "VCC_3V3"})

    print("  Power nets restored")


# ===========================================================================
# DISCONNECT POWER NETS BEFORE DSN EXPORT
# ===========================================================================
def disconnect_power_pads(board, nm):
    """Set all GND and VCC_3V3 pads to net 0 (unconnected) before DSN export."""
    print("  Disconnecting power pads for DSN export...")
    count = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_info = pad.GetNet()
            if net_info is None:
                continue
            net_name = net_info.GetNetname()
            if net_name in POWER_NETS:
                pad.SetNetCode(0)
                count += 1
    print(f"  Disconnected {count} power pads")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    os.makedirs(PROD_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Load PCB
    # ------------------------------------------------------------------
    print("=" * 70)
    print("STEP 1: Loading PCB")
    print("=" * 70)
    board = pcbnew.LoadBoard(PCB_PATH)
    fps = list(board.GetFootprints())
    print(f"  Loaded {len(fps)} footprints")
    print(f"  Existing net count: {board.GetNetCount()}")

    # ------------------------------------------------------------------
    # Step 2: Create nets
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 2: Creating nets")
    print("=" * 70)
    nm = create_all_nets(board)

    # ------------------------------------------------------------------
    # Step 3: Assign nets to pads
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 3: Assigning nets to pads")
    print("=" * 70)
    assign_all_nets(board, nm)

    # ------------------------------------------------------------------
    # Step 3.5: Save intermediate result
    # ------------------------------------------------------------------
    print("\n  Saving PCB with net assignments...")
    pcbnew.SaveBoard(PCB_PATH, board)
    print(f"  Saved: {PCB_PATH}")

    # ------------------------------------------------------------------
    # Step 4: Export DSN (stripping power nets)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 4: Exporting DSN for Freerouting")
    print("=" * 70)

    # Disconnect power pads before export
    disconnect_power_pads(board, nm)

    # Save temporary PCB for DSN export
    tmp_pcb = PCB_PATH + ".tmp_for_dsn.kicad_pcb"
    pcbnew.SaveBoard(tmp_pcb, board)

    # Export DSN
    print(f"  Exporting DSN to {DSN_PATH}...")
    ok = pcbnew.ExportSpecctraDSN(board, DSN_PATH)
    if not ok:
        # Try the single-argument form
        print("  Two-arg form failed, trying single-arg...")
        ok = pcbnew.ExportSpecctraDSN(DSN_PATH)
    print(f"  ExportSpecctraDSN returned: {ok}")

    if not os.path.exists(DSN_PATH):
        print("  ERROR: DSN file was not created!")
        # Restore power and save anyway
        restore_power_nets(board, nm)
        pcbnew.SaveBoard(PCB_PATH, board)
        return

    dsn_size = os.path.getsize(DSN_PATH)
    print(f"  DSN file size: {dsn_size} bytes")

    # Additional stripping of power nets from DSN text
    strip_power_from_dsn(DSN_PATH)

    # Clean up temp file
    if os.path.exists(tmp_pcb):
        os.remove(tmp_pcb)

    # ------------------------------------------------------------------
    # Step 5: Run Freerouting
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 5: Running Freerouting auto-router")
    print("=" * 70)

    # Remove old .ses if it exists
    if os.path.exists(SES_PATH):
        os.remove(SES_PATH)

    cmd = [
        JAVA_BIN,
        "-Djava.awt.headless=true",
        "-Xmx2g",
        "-jar", FREEROUTER,
        "-de", DSN_PATH,
        "-do", SES_PATH,
        "-mp", "3",
    ]
    print(f"  Command: {' '.join(cmd)}")
    print(f"  Timeout: 10 minutes")
    print(f"  NOTE: For this complex 4-layer BGA board, Freerouting may need")
    print(f"        30+ minutes to converge. You can also open the DSN file in")
    print(f"        Freerouting GUI for interactive routing.")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        print(f"  Freerouting exit code: {result.returncode}")
        if result.stdout:
            # Print last 30 lines of stdout
            lines = result.stdout.strip().split("\n")
            print(f"  stdout ({len(lines)} lines, showing last 30):")
            for line in lines[-30:]:
                print(f"    {line}")
        if result.stderr:
            lines = result.stderr.strip().split("\n")
            print(f"  stderr ({len(lines)} lines, showing last 10):")
            for line in lines[-10:]:
                print(f"    {line}")
    except subprocess.TimeoutExpired:
        print("  WARNING: Freerouting timed out after 10 minutes")
        print("  The auto-router was actively routing but needs more time.")
        print("  To complete routing, run manually:")
        print(f"    {' '.join(cmd)}")
        print(f"  Or open the DSN in Freerouting GUI for interactive control.")
    except Exception as e:
        print(f"  ERROR: Freerouting failed: {e}")

    # ------------------------------------------------------------------
    # Step 6: Import SES results
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 6: Importing routing results")
    print("=" * 70)

    # Reload the board with full net assignments for import
    board = pcbnew.LoadBoard(PCB_PATH)
    # Re-create net map from board
    nm_reload = {}
    for i in range(board.GetNetCount()):
        net = board.FindNet(i)
        if net:
            nm_reload[net.GetNetname()] = i

    if os.path.exists(SES_PATH):
        ses_size = os.path.getsize(SES_PATH)
        print(f"  SES file found: {SES_PATH} ({ses_size} bytes)")
        ok = pcbnew.ImportSpecctraSES(board, SES_PATH)
        if not ok:
            print("  Two-arg form failed, trying single-arg...")
            ok = pcbnew.ImportSpecctraSES(SES_PATH)
        print(f"  ImportSpecctraSES returned: {ok}")
    else:
        print("  No SES file found — Freerouting did not produce output")
        print("  The PCB has net assignments but no routes")

    # Ensure power nets are restored
    restore_power_nets(board, nm_reload)

    # ------------------------------------------------------------------
    # Step 7: Save and render
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 7: Saving and rendering final board")
    print("=" * 70)

    pcbnew.SaveBoard(PCB_PATH, board)
    print(f"  Saved: {PCB_PATH}")

    # Count assigned nets
    assigned = 0
    total_pads = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            total_pads += 1
            if pad.GetNet().GetNetname() != "":
                assigned += 1
    print(f"\n  Net assignment summary: {assigned}/{total_pads} pads have nets")

    # Render
    render_board(PCB_PATH,
                 os.path.join(PROD_DIR, "neocart_fpga_prog_routed_top.png"), "top")
    render_board(PCB_PATH,
                 os.path.join(PROD_DIR, "neocart_fpga_prog_routed_bottom.png"), "bottom")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"  PCB: {PCB_PATH}")
    print(f"  DSN: {DSN_PATH}")
    if os.path.exists(SES_PATH):
        print(f"  SES: {SES_PATH}")


if __name__ == "__main__":
    main()
