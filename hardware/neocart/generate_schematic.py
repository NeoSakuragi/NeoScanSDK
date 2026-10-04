#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — KiCad 9 Schematic Generator

Architecture:
  - 5V flash chips connected directly to Neo Geo edge connector
  - RP2040 programs flash via USB (3.3V domain)
  - 74HC595 shift registers for address bus during programming
  - 74HC245 for data bus level shifting during programming
  - Diode-OR on control signals (CE/OE/WE) for bus sharing
  - AMS1117-3.3 LDO for 3.3V rail (from USB VBUS or Neo Geo 5V)

Flash chips:
  P ROM  — AM29F400 (512KB, 16-bit, TSOP-48) — 68k program
  S ROM  — SST39SF010 (128KB, 8-bit, PLCC-32) — fix layer tiles
  M ROM  — SST39SF010 (128KB, 8-bit, PLCC-32) — Z80 sound program
  C1 ROM — AM29F400 (512KB, 16-bit, TSOP-48) — sprite data even
  C2 ROM — AM29F400 (512KB, 16-bit, TSOP-48) — sprite data odd
"""

import uuid
import json
import os

def uid():
    return str(uuid.uuid4())

# ─── Schematic S-expression helpers ───

def prop(name, value, x, y, angle=0, hide=False, size=1.27):
    hide_str = "\n\t\t\t\t(hide yes)" if hide else ""
    return f'''(property "{name}" "{value}"
\t\t\t(at {x} {y} {angle})
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size {size} {size})
\t\t\t\t){hide_str}
\t\t\t)
\t\t)'''

def symbol_instance(lib_id, ref, value, x, y, angle=0, unit=1, mirror="", pins=None, extra_props=None):
    mirror_str = f" (mirror {mirror})" if mirror else ""
    pin_str = ""
    if pins:
        for pnum in pins:
            pin_str += f'\n\t\t(pin "{pnum}" (uuid "{uid()}"))'
    extra_str = ""
    if extra_props:
        for ep in extra_props:
            extra_str += f"\n\t\t{ep}"
    return f'''(symbol
\t\t(lib_id "{lib_id}")
\t\t(at {x} {y} {angle})
\t\t(unit {unit}){mirror_str}
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "{uid()}")
\t\t{prop("Reference", ref, x+2, y+2, hide=False)}
\t\t{prop("Value", value, x+2, y-2, hide=False)}{extra_str}{pin_str}
\t)'''

def net_label(name, x, y, angle=0):
    return f'''(label "{name}"
\t\t(at {x} {y} {angle})
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t)
\t\t(uuid "{uid()}")
\t)'''

def global_label(name, x, y, angle=0, shape="bidirectional"):
    return f'''(global_label "{name}"
\t\t(shape {shape})
\t\t(at {x} {y} {angle})
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(justify left)
\t\t)
\t\t(uuid "{uid()}")
\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"
\t\t\t(at 0 0 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
\t)'''

def wire(x1, y1, x2, y2):
    return f'''(wire
\t\t(pts
\t\t\t(xy {x1} {y1}) (xy {x2} {y2})
\t\t)
\t\t(stroke
\t\t\t(width 0)
\t\t\t(type default)
\t\t)
\t\t(uuid "{uid()}")
\t)'''

def power_symbol(name, ref, x, y, angle=0, lib="power"):
    return symbol_instance(f"{lib}:{name}", ref, name, x, y, angle)

def text_note(text, x, y, size=2.54):
    return f'''(text "{text}"
\t\t(exclude_from_sim no)
\t\t(at {x} {y} 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size {size} {size})
\t\t\t)
\t\t)
\t\t(uuid "{uid()}")
\t)'''

# ─── Pin maps for components in KiCad library ───

AM29F400_PINS = {
    "A0": "25", "A1": "24", "A2": "23", "A3": "22", "A4": "21",
    "A5": "20", "A6": "19", "A7": "18", "A8": "8", "A9": "7",
    "A10": "6", "A11": "5", "A12": "4", "A13": "3", "A14": "2",
    "A15": "1", "A16": "48", "A17": "47",
    "DQ0": "29", "DQ1": "31", "DQ2": "33", "DQ3": "35",
    "DQ4": "38", "DQ5": "40", "DQ6": "42", "DQ7": "44",
    "DQ8": "30", "DQ9": "32", "DQ10": "34", "DQ11": "36",
    "DQ12": "39", "DQ13": "41", "DQ14": "43", "DQ15": "45",
    "CE": "17", "OE": "26", "WE": "28", "BYTE": "11",
    "RESET": "47", "VCC": "12", "VSS1": "37", "VSS2": "27", "NC": "46"
}

SST39SF010_PINS = {
    "A0": "12", "A1": "11", "A2": "10", "A3": "9", "A4": "8",
    "A5": "7", "A6": "6", "A7": "5", "A8": "27", "A9": "26",
    "A10": "23", "A11": "25", "A12": "4", "A13": "28", "A14": "29",
    "A15": "3", "A16": "2",
    "DQ0": "13", "DQ1": "14", "DQ2": "15", "DQ3": "17",
    "DQ4": "18", "DQ5": "19", "DQ6": "20", "DQ7": "21",
    "CE": "22", "OE": "24", "WE": "31",
    "VCC": "32", "GND": "16"
}

# ─── CTRG1 (CHA) pinout — from Jamma Nation X ───
# Side A = bottom, Side B = top
CTRG1 = {
    # Pin: (SideA_signal, SideB_signal)
    1: ("GND", "GND"), 2: ("GND", "GND"),
    3: ("P0", "P1"), 4: ("P2", "P3"), 5: ("P4", "P5"),
    6: ("P6", "P7"), 7: ("P8", "P9"), 8: ("P10", "P11"),
    9: ("P12", "P13"), 10: ("P14", "P15"), 11: ("P16", "P17"),
    12: ("P18", "P19"), 13: ("P20", "P21"), 14: ("P22", "P23"),
    15: ("PCK1B", "24M"), 16: ("PCK2B", "12M"),
    17: ("2H1", "8M"), 18: ("CA4", "RESET"),
    19: ("CR0", "CR1"), 20: ("CR2", "CR3"),
    21: ("CR4", "CR5"), 22: ("CR6", "CR7"),
    23: ("CR8", "CR9"), 24: ("CR10", "CR11"),
    25: ("CR12", "CR13"), 26: ("CR14", "CR15"),
    27: ("CR16", "CR17"), 28: ("CR18", "CR19"),
    29: ("VCC", "VCC"), 30: ("VCC", "VCC"),
    31: ("VCC", "VCC"), 32: ("VCC", "VCC"),
    33: ("CR20", "CR21"), 34: ("CR22", "CR23"),
    35: ("CR24", "CR25"), 36: ("CR26", "CR27"),
    37: ("CR28", "CR29"), 38: ("CR30", "CR31"),
    39: ("NC", "FIX00"), 40: ("NC", "FIX01"),
    41: ("NC", "FIX02"), 42: ("SYSTEMB", "FIX03"),
    43: ("SDA0", "FIX04"), 44: ("SDA1", "FIX05"),
    45: ("SDA2", "FIX06"), 46: ("SDA3", "FIX07"),
    47: ("SDA4", "SDMRD"), 48: ("SDA5", "SDD0"),
    49: ("SDA6", "SDD1"), 50: ("SDA7", "SDD2"),
    51: ("SDA8", "SDD3"), 52: ("SDA9", "SDD4"),
    53: ("SDA10", "SDD5"), 54: ("SDA11", "SDD6"),
    55: ("SDA12", "SDD7"), 56: ("SDA13", "SDROM"),
    57: ("SDA14", "SDA15"),
    58: ("GND", "GND"), 59: ("GND", "GND"), 60: ("GND", "GND"),
}

# ─── CTRG2 (PROG) pinout ───
CTRG2 = {
    1: ("GND", "GND"), 2: ("GND", "GND"),
    3: ("GND", "GND"), 4: ("GND", "GND"),
    5: ("D0", "A1"), 6: ("D1", "A2"), 7: ("D2", "A3"),
    8: ("D3", "A4"), 9: ("D4", "A5"), 10: ("D5", "A6"),
    11: ("D6", "A7"), 12: ("D7", "A8"), 13: ("D8", "A9"),
    14: ("D9", "A10"), 15: ("D10", "A11"), 16: ("D11", "A12"),
    17: ("D12", "A13"), 18: ("D13", "A14"), 19: ("D14", "A15"),
    20: ("D15", "A16"),
    21: ("nRW", "A17"), 22: ("nAS", "A18"),
    23: ("ROMOEU", "A19"), 24: ("ROMOEL", "68KCLKB"),
    25: ("PORTOEU", "ROMWAIT"), 26: ("PORTOEL", "PWAIT0"),
    27: ("PORTWEU", "PWAIT1"), 28: ("PORTWEL", "PDTACK"),
    29: ("VCC", "VCC"), 30: ("VCC", "VCC"),
    31: ("VCC", "VCC"), 32: ("VCC", "VCC"),
    33: ("ROMOE", "4MB"),
    34: ("NC", "NC"), 35: ("NC", "RESET"),
    36: ("NC", "NC"), 37: ("NC", "NC"),
    38: ("NC", "NC"), 39: ("NC", "NC"),
    40: ("NC", "SDPAD0"), 41: ("NC", "SDPAD1"),
    42: ("NC", "SDPAD2"), 43: ("SDPA8", "SDPAD3"),
    44: ("SDPA9", "SDPAD4"), 45: ("SDPA10", "SDPAD5"),
    46: ("SDPA11", "SDPAD6"), 47: ("SDRA8", "SDPAD7"),
    48: ("SDRA9", "SDRA0"), 49: ("SDRA10", "SDRA1"),
    50: ("SDRA11", "SDRA2"), 51: ("SDRA12", "SDRA3"),
    52: ("SDRA13", "SDRA4"), 53: ("SDRA14", "SDRA5"),
    54: ("SDRA15", "SDRA6"), 55: ("SDRA16", "SDRA7"),
    56: ("SDRA17", "SDROE"),
    57: ("SDRA18", "SDRA19"),
    58: ("SDRA20", "SDMRD"),
    59: ("GND", "GND"), 60: ("GND", "GND"),
}


def generate_connector_symbol(name, pinout, desc):
    """Generate a custom KiCad symbol for an MVS edge connector."""
    pins_a = []
    pins_b = []

    for pin_num in sorted(pinout.keys()):
        sig_a, sig_b = pinout[pin_num]
        phys_a = f"A{pin_num}"
        phys_b = f"B{pin_num}"
        pins_a.append((phys_a, sig_a, pin_num * 2 - 1))
        pins_b.append((phys_b, sig_b, pin_num * 2))

    return name, pins_a, pins_b


def generate_schematic():
    """Generate the complete KiCad schematic file."""

    elements = []

    # ─── Section headers as text notes ───
    elements.append(text_note("═══ NEO GEO MVS FLASH CART ═══", 20, 10, 3.0))
    elements.append(text_note("5 flash ROMs + RP2040 USB programmer", 20, 16, 2.0))

    # ════════════════════════════════════════════
    # SECTION 1: P ROM (Program ROM)
    # ════════════════════════════════════════════
    px, py = 80, 60
    elements.append(text_note("── P ROM (68k Program) ──", px-20, py-40, 2.0))

    ref = "U_PROM"
    elements.append(symbol_instance(
        "Memory_Flash:AM29F400Bx-xxEx", ref, "AM29F400_P",
        px, py, pins=list(AM29F400_PINS.values())
    ))

    # P ROM address labels (from CTRG2 68k bus)
    for i in range(18):
        lx = px - 20
        ly = py - 33 + i * 2.54
        elements.append(net_label(f"P_A{i}", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # P ROM data labels (D0-D15 from CTRG2)
    for i in range(16):
        lx = px + 20
        ly = py - 33 + i * 2.54
        elements.append(net_label(f"P_D{i}", lx, ly, 0))
        elements.append(wire(lx - 5, ly, lx, ly))

    # P ROM control labels
    elements.append(net_label("nCE_P", px - 20, py + 15, 0))
    elements.append(net_label("nOE_P", px - 20, py + 18, 0))
    elements.append(net_label("nWE_P", px - 20, py + 21, 0))
    elements.append(net_label("VCC_5V", px, py - 40, 0))
    elements.append(net_label("GND", px, py + 40, 0))

    # ════════════════════════════════════════════
    # SECTION 2: S ROM (Fix Layer)
    # ════════════════════════════════════════════
    sx, sy = 200, 60
    elements.append(text_note("── S ROM (Fix Layer Tiles) ──", sx-20, sy-40, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:SST39SF010", "U_SROM", "SST39SF010_S",
        sx, sy, pins=list(SST39SF010_PINS.values())
    ))

    # S ROM address labels (SDA0-SDA15 from CTRG1)
    for i in range(17):
        lx = sx - 20
        ly = sy - 33 + i * 2.54
        elements.append(net_label(f"SDA{i}", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # S ROM data labels (SDD0-SDD7 from CTRG1)
    for i in range(8):
        lx = sx + 20
        ly = sy - 20 + i * 2.54
        elements.append(net_label(f"SDD{i}", lx, ly, 0))
        elements.append(wire(lx - 5, ly, lx, ly))

    # S ROM control
    elements.append(net_label("nCE_S", sx - 20, sy + 15, 0))
    elements.append(net_label("nOE_S", sx - 20, sy + 18, 0))
    elements.append(net_label("nWE_S", sx - 20, sy + 21, 0))

    # ════════════════════════════════════════════
    # SECTION 3: M ROM (Z80 Sound Program)
    # ════════════════════════════════════════════
    mx, my = 320, 60
    elements.append(text_note("── M ROM (Z80 Sound Program) ──", mx-20, my-40, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:SST39SF010", "U_MROM", "SST39SF010_M",
        mx, my, pins=list(SST39SF010_PINS.values())
    ))

    for i in range(17):
        lx = mx - 20
        ly = my - 33 + i * 2.54
        elements.append(net_label(f"MA{i}", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    for i in range(8):
        lx = mx + 20
        ly = my - 20 + i * 2.54
        elements.append(net_label(f"MD{i}", lx, ly, 0))
        elements.append(wire(lx - 5, ly, lx, ly))

    elements.append(net_label("nCE_M", mx - 20, my + 15, 0))
    elements.append(net_label("nOE_M", mx - 20, my + 18, 0))
    elements.append(net_label("nWE_M", mx - 20, my + 21, 0))

    # ════════════════════════════════════════════
    # SECTION 4: C1 ROM (Sprite Data - Lower 16 bits)
    # ════════════════════════════════════════════
    c1x, c1y = 80, 180
    elements.append(text_note("── C1 ROM (Sprites CR0-CR15) ──", c1x-20, c1y-40, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:AM29F400Bx-xxEx", "U_CROM1", "AM29F400_C1",
        c1x, c1y, pins=list(AM29F400_PINS.values())
    ))

    # C ROM address (P0-P23 from CTRG1, directly as sprite tile address)
    for i in range(18):
        lx = c1x - 20
        ly = c1y - 33 + i * 2.54
        elements.append(net_label(f"CA{i}", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # C1 data (CR0-CR15)
    for i in range(16):
        lx = c1x + 20
        ly = c1y - 33 + i * 2.54
        elements.append(net_label(f"CR{i}", lx, ly, 0))
        elements.append(wire(lx - 5, ly, lx, ly))

    elements.append(net_label("nCE_C1", c1x - 20, c1y + 15, 0))
    elements.append(net_label("nOE_C1", c1x - 20, c1y + 18, 0))
    elements.append(net_label("nWE_C1", c1x - 20, c1y + 21, 0))

    # ════════════════════════════════════════════
    # SECTION 5: C2 ROM (Sprite Data - Upper 16 bits)
    # ════════════════════════════════════════════
    c2x, c2y = 200, 180
    elements.append(text_note("── C2 ROM (Sprites CR16-CR31) ──", c2x-20, c2y-40, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:AM29F400Bx-xxEx", "U_CROM2", "AM29F400_C2",
        c2x, c2y, pins=list(AM29F400_PINS.values())
    ))

    for i in range(18):
        lx = c2x - 20
        ly = c2y - 33 + i * 2.54
        elements.append(net_label(f"CA{i}", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    for i in range(16):
        lx = c2x + 20
        ly = c2y - 33 + i * 2.54
        elements.append(net_label(f"CR{i+16}", lx, ly, 0))
        elements.append(wire(lx - 5, ly, lx, ly))

    elements.append(net_label("nCE_C2", c2x - 20, c2y + 15, 0))
    elements.append(net_label("nOE_C2", c2x - 20, c2y + 18, 0))
    elements.append(net_label("nWE_C2", c2x - 20, c2y + 21, 0))

    # ════════════════════════════════════════════
    # SECTION 6: RP2040 Programmer
    # ════════════════════════════════════════════
    ux, uy = 320, 200
    elements.append(text_note("── RP2040 USB PROGRAMMER ──", ux-20, uy-50, 2.0))

    elements.append(symbol_instance(
        "MCU_RaspberryPi:RP2040", "U_MCU", "RP2040",
        ux, uy, pins=[str(i) for i in range(1, 57)]
    ))

    # GPIO assignments for programming:
    gpio_map = {
        "GPIO0": "SR_SER",      # Shift register serial data
        "GPIO1": "SR_SRCLK",    # Shift register clock
        "GPIO2": "SR_RCLK",     # Shift register latch
        "GPIO3": "PROG_D0",     # Programming data bus
        "GPIO4": "PROG_D1",
        "GPIO5": "PROG_D2",
        "GPIO6": "PROG_D3",
        "GPIO7": "PROG_D4",
        "GPIO8": "PROG_D5",
        "GPIO9": "PROG_D6",
        "GPIO10": "PROG_D7",
        "GPIO11": "PROG_nWE",   # Flash write enable
        "GPIO12": "PROG_nOE",   # Flash output enable
        "GPIO13": "PROG_nCE_P", # P ROM chip enable
        "GPIO14": "PROG_nCE_S", # S ROM chip enable
        "GPIO15": "PROG_nCE_M", # M ROM chip enable
        "GPIO16": "PROG_nCE_C1",# C1 ROM chip enable
        "GPIO17": "PROG_nCE_C2",# C2 ROM chip enable
        "GPIO18": "PROG_nBYTE", # 16-bit flash byte mode
        "GPIO19": "BUS_DIR",    # Bus transceiver direction
        "GPIO20": "SR_nOE",     # Shift register output enable
        "GPIO21": "BUF_nOE",    # Data buffer output enable
    }

    for i, (gpio, net) in enumerate(gpio_map.items()):
        lx = ux + 30
        ly = uy - 40 + i * 2.54
        elements.append(net_label(net, lx, ly, 0))

    # USB signals
    elements.append(net_label("USB_DP", ux - 30, uy - 10, 180))
    elements.append(net_label("USB_DM", ux - 30, uy - 7, 180))

    # SPI flash for RP2040 firmware
    elements.append(net_label("QSPI_SS", ux - 30, uy + 5, 180))
    elements.append(net_label("QSPI_SCLK", ux - 30, uy + 8, 180))
    elements.append(net_label("QSPI_SD0", ux - 30, uy + 11, 180))
    elements.append(net_label("QSPI_SD1", ux - 30, uy + 14, 180))

    # ════════════════════════════════════════════
    # SECTION 7: USB-C Connector
    # ════════════════════════════════════════════
    jx, jy = 430, 60
    elements.append(text_note("── USB-C (Programming Interface) ──", jx-20, jy-20, 2.0))

    elements.append(symbol_instance(
        "Connector:USB_C_Receptacle_USB2.0_14P", "J_USB", "USB_C",
        jx, jy
    ))

    elements.append(net_label("USB_DP", jx + 20, jy - 5, 0))
    elements.append(net_label("USB_DM", jx + 20, jy - 2, 0))
    elements.append(net_label("VBUS", jx + 20, jy - 10, 0))
    elements.append(net_label("GND", jx + 20, jy + 10, 0))

    # ════════════════════════════════════════════
    # SECTION 8: SPI Flash (RP2040 firmware storage)
    # ════════════════════════════════════════════
    fx, fy = 430, 140
    elements.append(text_note("── W25Q32 (RP2040 Firmware) ──", fx-20, fy-20, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:W25Q32JVSS", "U_FLASH", "W25Q32",
        fx, fy
    ))

    elements.append(net_label("QSPI_SS", fx - 15, fy - 5, 0))
    elements.append(net_label("QSPI_SCLK", fx - 15, fy, 0))
    elements.append(net_label("QSPI_SD0", fx - 15, fy + 5, 0))
    elements.append(net_label("QSPI_SD1", fx - 15, fy + 10, 0))
    elements.append(net_label("VCC_3V3", fx, fy - 15, 0))
    elements.append(net_label("GND", fx, fy + 15, 0))

    # ════════════════════════════════════════════
    # SECTION 9: 74HC595 Shift Registers (Address Bus for Programming)
    # ════════════════════════════════════════════
    srx, sry = 80, 320
    elements.append(text_note("── 74HC595 x3 — Address Bus (24 bits from 3 GPIO) ──", srx-20, sry-25, 2.0))

    for sr_idx in range(3):
        sx_off = sr_idx * 60
        ref_name = f"U_SR{sr_idx+1}"
        elements.append(symbol_instance(
            "74xx:74HC595", ref_name, "74HC595",
            srx + sx_off, sry,
            pins=[str(i) for i in range(1, 17)]
        ))

        # Output labels (address bits)
        for bit in range(8):
            addr_bit = sr_idx * 8 + bit
            lx = srx + sx_off + 15
            ly = sry - 10 + bit * 2.54
            elements.append(net_label(f"PROG_A{addr_bit}", lx, ly, 0))

        # Chain: QH' of each SR connects to SER of next
        if sr_idx < 2:
            elements.append(net_label(f"SR_CHAIN_{sr_idx}", srx + sx_off + 15, sry + 12, 0))
            elements.append(net_label(f"SR_CHAIN_{sr_idx}", srx + sx_off + 60 - 15, sry - 15, 180))

        # Shared control signals
        elements.append(net_label("SR_SRCLK", srx + sx_off - 15, sry - 5, 180))
        elements.append(net_label("SR_RCLK", srx + sx_off - 15, sry, 180))
        elements.append(net_label("SR_nOE", srx + sx_off - 15, sry + 5, 180))
        elements.append(net_label("VCC_3V3", srx + sx_off, sry - 20, 0))
        elements.append(net_label("GND", srx + sx_off, sry + 20, 0))

    # First SR gets serial data from RP2040
    elements.append(net_label("SR_SER", srx - 15, sry - 15, 180))

    # ════════════════════════════════════════════
    # SECTION 10: 74HC245 Data Buffer (Level Shifting for Programming)
    # ════════════════════════════════════════════
    bx, by = 320, 320
    elements.append(text_note("── 74HC245 x2 — Data + Control Bus Buffer ──", bx-20, by-25, 2.0))

    # Data buffer (PROG_D0-D7 from RP2040 ↔ flash data bus)
    elements.append(symbol_instance(
        "74xx:74HC245", "U_BUF1", "74HC245",
        bx, by, pins=[str(i) for i in range(1, 21)]
    ))

    for i in range(8):
        # A side: RP2040 (3.3V)
        elements.append(net_label(f"PROG_D{i}", bx - 15, by - 10 + i * 2.54, 180))
        # B side: Flash chips (5V)
        elements.append(net_label(f"FLASH_D{i}", bx + 15, by - 10 + i * 2.54, 0))

    elements.append(net_label("BUS_DIR", bx - 15, by + 12, 180))
    elements.append(net_label("BUF_nOE", bx - 15, by + 15, 180))
    elements.append(net_label("VCC_5V", bx, by - 18, 0))
    elements.append(net_label("GND", bx, by + 18, 0))

    # Control buffer (CE/OE/WE from RP2040 to flash)
    elements.append(symbol_instance(
        "74xx:74HC245", "U_BUF2", "74HC245",
        bx + 80, by, pins=[str(i) for i in range(1, 21)]
    ))

    ctrl_nets = ["PROG_nCE_P", "PROG_nCE_S", "PROG_nCE_M",
                 "PROG_nCE_C1", "PROG_nCE_C2", "PROG_nWE", "PROG_nOE", "PROG_nBYTE"]
    flash_ctrl = ["nCE_P", "nCE_S", "nCE_M", "nCE_C1", "nCE_C2",
                  "nWE_FLASH", "nOE_FLASH", "nBYTE_FLASH"]

    for i, (prog_net, flash_net) in enumerate(zip(ctrl_nets, flash_ctrl)):
        elements.append(net_label(prog_net, bx + 80 - 15, by - 10 + i * 2.54, 180))
        elements.append(net_label(flash_net, bx + 80 + 15, by - 10 + i * 2.54, 0))

    elements.append(net_label("BUS_DIR", bx + 80 - 15, by + 12, 180))
    elements.append(net_label("BUF_nOE", bx + 80 - 15, by + 15, 180))

    # ════════════════════════════════════════════
    # SECTION 11: Power Supply
    # ════════════════════════════════════════════
    rx, ry = 430, 250
    elements.append(text_note("── POWER: AMS1117-3.3 LDO ──", rx-20, ry-25, 2.0))

    elements.append(symbol_instance(
        "Regulator_Linear:AMS1117CD-3.3", "U_REG", "AMS1117-3.3",
        rx, ry
    ))

    elements.append(net_label("VCC_5V", rx - 15, ry, 180))
    elements.append(net_label("VCC_3V3", rx + 15, ry, 0))
    elements.append(net_label("GND", rx, ry + 10, 0))

    elements.append(text_note("VBUS from USB or 5V from Neo Geo\\n(Schottky diodes for OR)", rx-20, ry+15, 1.5))

    # ════════════════════════════════════════════
    # SECTION 12: 12MHz Crystal for RP2040
    # ════════════════════════════════════════════
    yx, yy = 430, 200
    elements.append(symbol_instance(
        "Device:Crystal", "Y1", "12MHz",
        yx, yy
    ))
    elements.append(net_label("XIN", yx - 8, yy, 180))
    elements.append(net_label("XOUT", yx + 8, yy, 0))

    # ════════════════════════════════════════════
    # SECTION 13: Decoupling Capacitors
    # ════════════════════════════════════════════
    cx, cy = 20, 420
    elements.append(text_note("── DECOUPLING: 100nF per IC, 10uF on power rails ──", cx, cy, 2.0))

    cap_refs = [
        ("C_P", "100nF", "P ROM"), ("C_S", "100nF", "S ROM"),
        ("C_M", "100nF", "M ROM"), ("C_C1", "100nF", "C1 ROM"),
        ("C_C2", "100nF", "C2 ROM"), ("C_MCU1", "100nF", "RP2040"),
        ("C_MCU2", "100nF", "RP2040"), ("C_FLASH", "100nF", "W25Q32"),
        ("C_SR1", "100nF", "SR1"), ("C_SR2", "100nF", "SR2"),
        ("C_SR3", "100nF", "SR3"), ("C_BUF1", "100nF", "BUF1"),
        ("C_BUF2", "100nF", "BUF2"), ("C_REG_IN", "10uF", "LDO in"),
        ("C_REG_OUT", "10uF", "LDO out"), ("C_USB", "10uF", "USB VBUS"),
    ]

    for i, (ref_name, val, note) in enumerate(cap_refs):
        col = i % 8
        row = i // 8
        elements.append(symbol_instance(
            "Device:C", ref_name, val,
            cx + 30 + col * 30, cy + 15 + row * 25
        ))

    # ════════════════════════════════════════════
    # SECTION 14: Connection notes (bus mapping documentation)
    # ════════════════════════════════════════════
    nx, ny = 20, 500
    elements.append(text_note(
        "═══ BUS MAPPING NOTES ═══\\n"
        "CTRG2 A1-A19 → P_A0-P_A18 (P ROM address, directly wired)\\n"
        "CTRG2 D0-D15 → P_D0-P_D15 (P ROM data, directly wired)\\n"
        "CTRG2 ROMOE → nOE_P (directly wired to P ROM ~OE)\\n"
        "CTRG2 ROMOEU → nCE_P via diode-OR with PROG_nCE_P\\n"
        "\\n"
        "CTRG1 SDA0-SDA15 → S ROM A0-A15 (directly wired)\\n"
        "CTRG1 SDD0-SDD7 → S ROM DQ0-DQ7 (directly wired)\\n"
        "CTRG1 SDROM → nCE_S via diode-OR with PROG_nCE_S\\n"
        "CTRG1 SDMRD → nOE_S (directly wired)\\n"
        "\\n"
        "CTRG2 SDRA0-SDRA16 → M ROM A0-A16 (Z80 sound address)\\n"
        "CTRG2 SDPAD0-SDPAD7 → M ROM DQ0-DQ7 (Z80 sound data)\\n"
        "CTRG2 SDROE → nOE_M (directly wired)\\n"
        "\\n"
        "CTRG1 P0-P17 → C ROM A0-A17 (sprite tile address)\\n"
        "CTRG1 CR0-CR15 → C1 ROM DQ0-DQ15\\n"
        "CTRG1 CR16-CR31 → C2 ROM DQ0-DQ15\\n"
        "CTRG1 PCK1B → C1 ~CE, PCK2B → C2 ~CE (active-low pixel clocks)\\n"
        "\\n"
        "PROGRAMMING MODE (USB connected, cart not in Neo Geo):\\n"
        "  RP2040 → 74HC595 → PROG_A0-A23 → Flash address pins\\n"
        "  RP2040 → 74HC245 → FLASH_D0-D7 → Flash data pins (byte mode)\\n"
        "  RP2040 → 74HC245 → nCE/nWE/nOE → Flash control pins\\n"
        "  74HC595 OE pulled HIGH by default (disabled during play)\\n"
        "  74HC245 OE pulled HIGH by default (disabled during play)\\n",
        nx, ny, 1.5
    ))

    # ════════════════════════════════════════════
    # Assemble the complete schematic file
    # ════════════════════════════════════════════

    body = "\n\t".join(elements)

    schematic = f"""(kicad_sch
\t(version 20231120)
\t(generator "neocart_generator")
\t(generator_version "1.0")
\t(uuid "{uid()}")
\t(paper "A1")
\t(title_block
\t\t(title "Neo Geo MVS Flash Cart")
\t\t(date "2026-04-25")
\t\t(rev "1.0")
\t\t(company "NeoScanSDK")
\t\t(comment 1 "5x Flash ROM + RP2040 USB Programmer")
\t\t(comment 2 "P/S/M/C1/C2 — hello world dev cart")
\t)
\t(lib_symbols
\t)
\t{body}
\t(symbol_instances
\t)
)"""

    return schematic


def generate_project():
    """Generate KiCad project file."""
    return json.dumps({
        "meta": {
            "filename": "neocart.kicad_pro",
            "version": 2
        },
        "schematic": {
            "drawing": {},
            "meta": {"version": 1}
        },
        "boards": [],
        "text_variables": {}
    }, indent=2)


def generate_pcb_outline():
    """Generate PCB file with board outline for MVS cart dimensions."""
    # MVS cart approximate dimensions: 140mm x 110mm
    # Edge connectors at the bottom edge
    # CTRG1 on one side, CTRG2 on the other
    # Finger pitch: 1.27mm

    board_w = 140.0
    board_h = 110.0
    finger_pitch = 1.27
    finger_w = 0.8
    finger_h = 6.0

    # Number of pins per connector side
    n_pins = 60

    elements = []

    # Board outline
    ox, oy = 100, 100  # origin offset
    corners = [
        (ox, oy),
        (ox + board_w, oy),
        (ox + board_w, oy + board_h),
        (ox, oy + board_h),
    ]

    for i in range(4):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % 4]
        elements.append(f"""(gr_line
\t\t(start {x1} {y1}) (end {x2} {y2})
\t\t(stroke (width 0.05) (type default))
\t\t(layer "Edge.Cuts")
\t\t(uuid "{uid()}")
\t)""")

    # Beveled edge for card insertion (bottom edge, chamfer corners)
    # Add mounting holes
    for mx, my in [(ox + 5, oy + 5), (ox + board_w - 5, oy + 5),
                   (ox + 5, oy + board_h - 5), (ox + board_w - 5, oy + board_h - 5)]:
        elements.append(f"""(footprint "MountingHole:MountingHole_3.2mm_M3"
\t\t(layer "F.Cu")
\t\t(uuid "{uid()}")
\t\t(at {mx} {my})
\t\t(property "Reference" "MH" (at 0 -3 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))
\t\t(property "Value" "MountingHole" (at 0 3 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))
\t)""")

    body = "\n\t".join(elements)

    pcb = f"""(kicad_pcb
\t(version 20240108)
\t(generator "neocart_generator")
\t(generator_version "1.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(title_block
\t\t(title "Neo Geo MVS Flash Cart")
\t\t(date "2026-04-25")
\t\t(rev "1.0")
\t)
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(32 "B.Adhes" user "B.Adhesive")
\t\t(33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user "B.Silkscreen")
\t\t(37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user "B.Mask")
\t\t(39 "F.Mask" user "F.Mask")
\t\t(40 "Dwgs.User" user "User.Drawings")
\t\t(41 "Cmts.User" user "User.Comments")
\t\t(44 "Edge.Cuts" user)
\t\t(45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard")
\t\t(47 "F.CrtYd" user "F.Courtyard")
\t\t(48 "B.Fab" user "B.Fabrication")
\t\t(49 "F.Fab" user "F.Fabrication")
\t)
\t(setup
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(pcbplotparams
\t\t\t(layerselection 0x00010fc_ffffffff)
\t\t\t(plot_on_all_layers_selection 0x0000000_00000000)
\t\t\t(disableapertmacros no)
\t\t\t(usegerberextensions no)
\t\t\t(usegerberattributes yes)
\t\t\t(usegerberadvancedattributes yes)
\t\t\t(creategerberjobfile yes)
\t\t\t(dashed_line_dash_ratio 12.000000)
\t\t\t(dashed_line_gap_ratio 3.000000)
\t\t\t(svgprecision 4)
\t\t\t(plotframeref no)
\t\t\t(viasonmask no)
\t\t\t(mode 1)
\t\t\t(useauxorigin no)
\t\t\t(hpglpennumber 1)
\t\t\t(hpglpenspeed 20)
\t\t\t(hpglpendiameter 15.000000)
\t\t\t(pdf_front_fp_property_popups yes)
\t\t\t(pdf_back_fp_property_popups yes)
\t\t\t(pdf_metadata yes)
\t\t\t(outputformat 1)
\t\t\t(mirror no)
\t\t\t(drillshape 1)
\t\t\t(scaleselection 1)
\t\t\t(outputdirectory "")
\t\t)
\t)
\t(net 0 "")
\t(net 1 "GND")
\t(net 2 "VCC_5V")
\t(net 3 "VCC_3V3")
\t{body}
)"""

    return pcb


def generate_bom():
    """Generate BOM with LCSC part numbers for JLCPCB assembly."""
    bom = """# Neo Geo MVS Flash Cart — Bill of Materials
# For JLCPCB PCBA Assembly
# Rev 1.0 — 2026-04-25

## Flash ROM Chips

| Ref     | Value           | Package   | Qty | Description                        | LCSC (check availability) |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| U_PROM  | AM29F400BB      | TSOP-48   | 1   | P ROM — 4Mbit 16-bit flash (5V)   | C2682159 or equivalent    |
| U_SROM  | SST39SF010A     | PLCC-32   | 1   | S ROM — 1Mbit 8-bit flash (5V)    | C191340 or equivalent     |
| U_MROM  | SST39SF010A     | PLCC-32   | 1   | M ROM — 1Mbit 8-bit flash (5V)    | C191340 or equivalent     |
| U_CROM1 | AM29F400BB      | TSOP-48   | 1   | C1 ROM — sprite data lower 16-bit | C2682159 or equivalent    |
| U_CROM2 | AM29F400BB      | TSOP-48   | 1   | C2 ROM — sprite data upper 16-bit | C2682159 or equivalent    |

## Microcontroller & Support

| Ref     | Value           | Package   | Qty | Description                        | LCSC                      |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| U_MCU   | RP2040          | QFN-56    | 1   | USB programmer MCU                 | C2040                     |
| U_FLASH | W25Q32JVSSIQ    | SOIC-8    | 1   | RP2040 firmware SPI flash (4MB)    | C571986                   |
| Y1      | 12MHz           | 3215      | 1   | Crystal for RP2040                 | C9002                     |
| U_REG   | AMS1117-3.3     | SOT-223   | 1   | 3.3V LDO regulator                | C6186                     |

## Bus Interface

| Ref     | Value           | Package   | Qty | Description                        | LCSC                      |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| U_SR1-3 | 74HC595D        | SOIC-16   | 3   | Shift register (address bus)       | C5947                     |
| U_BUF1  | 74HC245D        | SOIC-20   | 1   | Data bus buffer/level shifter      | C5949                     |
| U_BUF2  | 74HC245D        | SOIC-20   | 1   | Control bus buffer/level shifter   | C5949                     |

## Connectors

| Ref     | Value           | Package   | Qty | Description                        | LCSC                      |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| J_USB   | USB-C 2.0       | SMD       | 1   | USB Type-C receptacle (USB 2.0)    | C168688                   |

## Passive Components

| Ref          | Value  | Package | Qty | Description                    | LCSC   |
|--------------|--------|---------|-----|--------------------------------|--------|
| C1-C13       | 100nF  | 0402    | 13  | Decoupling caps (1 per IC)     | C1525  |
| C14-C16      | 10uF   | 0805    | 3   | Bulk caps (LDO in/out, USB)   | C15850 |
| C17-C18      | 15pF   | 0402    | 2   | Crystal load caps              | C1548  |
| R1           | 1K     | 0402    | 1   | USB boot pull-up (GPIO for bootsel) | C11702 |
| R2-R3        | 27R    | 0402    | 2   | USB series resistors           | C25100 |
| R4-R5        | 5.1K   | 0402    | 2   | USB-C CC resistors (UFP/sink)  | C25905 |
| R6-R7        | 10K    | 0402    | 2   | Pull-ups (SR_nOE, BUF_nOE)    | C25744 |
| D1-D5        | BAT54S | SOT-23  | 5   | Schottky diodes (CE bus OR)    | C82544 |
| D6           | BAT54S | SOT-23  | 1   | Power OR (VBUS / Neo Geo 5V)  | C82544 |

## JLCPCB PCB Specifications

- Layers: 2
- Dimensions: ~140mm x 110mm
- Thickness: 1.6mm
- Surface finish: ENIG (gold fingers required)
- Gold fingers: Yes — beveled, 30° chamfer
- Gold finger length: 6mm
- Min trace width: 0.2mm
- Min via: 0.3mm drill / 0.6mm annular

## Estimated Cost per Board (JLCPCB, qty 5)

- PCB fabrication (ENIG + gold fingers): ~$15-25
- SMT assembly (all components): ~$30-50
- Components: ~$15-25
- Total per assembled board: ~$60-100
"""
    return bom


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    # Generate KiCad project
    with open(os.path.join(out_dir, "neocart.kicad_pro"), "w") as f:
        f.write(generate_project())
    print("Created neocart.kicad_pro")

    # Generate schematic
    with open(os.path.join(out_dir, "neocart.kicad_sch"), "w") as f:
        f.write(generate_schematic())
    print("Created neocart.kicad_sch")

    # Generate PCB outline
    with open(os.path.join(out_dir, "neocart.kicad_pcb"), "w") as f:
        f.write(generate_pcb_outline())
    print("Created neocart.kicad_pcb")

    # Generate BOM
    with open(os.path.join(out_dir, "BOM.md"), "w") as f:
        f.write(generate_bom())
    print("Created BOM.md")

    print("\nDone! Open neocart.kicad_pro in KiCad 9.")
    print("The schematic uses net labels for all connections.")
    print("Run ERC (Electrical Rules Check) to verify connectivity.")


if __name__ == "__main__":
    main()
