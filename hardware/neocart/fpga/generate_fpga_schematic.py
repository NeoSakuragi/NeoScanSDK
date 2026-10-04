#!/usr/bin/env python3
"""
NeoCart FPGA PROG Board -- KiCad 9 Schematic Generator
======================================================

FPGA-based Neo Geo MVS PROG board. Plugs into CTRG2 (PROG slot).
All ROMs emulated by ECP5 FPGA + 64MB SDRAM (2x 32MB).
RP2040 handles USB, SD card, and SPI loading into SDRAM.

Components:
  U1:  Lattice ECP5-25 (LFE5U-25F-6BG256I) -- BGA-256
  U2:  Winbond W9825G6KH-6 SDRAM #1 -- TSOP-54, 32MB
  U3:  Winbond W9825G6KH-6 SDRAM #2 -- TSOP-54, 32MB
  U4:  RP2040 -- QFN-56
  U5:  W25Q32 (RP2040 firmware) -- SOIC-8
  U6:  W25Q32 (FPGA bitstream) -- SOIC-8
  U7:  74LVC245 (D0-D7 level shift) -- SOIC-20
  U8:  74LVC245 (D8-D15 level shift) -- SOIC-20
  U9:  AMS1117-3.3 (5V -> 3.3V) -- SOT-223
  U10: AMS1117-1.1 (3.3V -> 1.1V) -- SOT-223

Connectors:
  J1/J2: MVS PROG edge connector (A/B sides, 60 pins each)
  J3:    USB-C receptacle (USB 2.0, 14-pin)
  J4:    microSD card slot
  J5:    2x50 inter-board connector to CHA board
  J6:    JTAG header (6-pin)
  J7:    UART header (3-pin)

Outputs: neocart_fpga_prog.kicad_sch
"""

import uuid
import os
import sys

# =============================================================================
# S-expression helpers (KiCad 9 schematic format, version 20231120)
# =============================================================================

def uid():
    """Generate a unique UUID for KiCad elements."""
    return str(uuid.uuid4())


def prop(name, value, x, y, angle=0, hide=False, size=1.27):
    """Generate a property S-expression."""
    hide_str = "\n\t\t\t\t(hide yes)" if hide else ""
    return (
        f'(property "{name}" "{value}"\n'
        f'\t\t\t(at {x} {y} {angle})\n'
        f'\t\t\t(effects\n'
        f'\t\t\t\t(font\n'
        f'\t\t\t\t\t(size {size} {size})\n'
        f'\t\t\t\t){hide_str}\n'
        f'\t\t\t)\n'
        f'\t\t)'
    )


def symbol_instance(lib_id, ref, value, x, y, angle=0, unit=1,
                     mirror="", pins=None, extra_props=None, footprint="",
                     datasheet=""):
    """Generate a symbol placement S-expression."""
    mirror_str = f" (mirror {mirror})" if mirror else ""
    pin_str = ""
    if pins:
        for pnum in pins:
            pin_str += f'\n\t\t(pin "{pnum}" (uuid "{uid()}"))'
    extra_str = ""
    if extra_props:
        for ep in extra_props:
            extra_str += f"\n\t\t{ep}"
    fp_prop = ""
    if footprint:
        fp_prop = f'\n\t\t{prop("Footprint", footprint, x + 2, y - 4, hide=True)}'
    ds_prop = ""
    if datasheet:
        ds_prop = f'\n\t\t{prop("Datasheet", datasheet, x + 2, y - 6, hide=True)}'
    return (
        f'(symbol\n'
        f'\t\t(lib_id "{lib_id}")\n'
        f'\t\t(at {x} {y} {angle})\n'
        f'\t\t(unit {unit}){mirror_str}\n'
        f'\t\t(exclude_from_sim no)\n'
        f'\t\t(in_bom yes)\n'
        f'\t\t(on_board yes)\n'
        f'\t\t(dnp no)\n'
        f'\t\t(uuid "{uid()}")\n'
        f'\t\t{prop("Reference", ref, x + 2, y + 2, hide=False)}\n'
        f'\t\t{prop("Value", value, x + 2, y - 2, hide=False)}'
        f'{fp_prop}{ds_prop}{extra_str}{pin_str}\n'
        f'\t)'
    )


def net_label(name, x, y, angle=0):
    """Generate a net label S-expression."""
    return (
        f'(label "{name}"\n'
        f'\t\t(at {x} {y} {angle})\n'
        f'\t\t(effects\n'
        f'\t\t\t(font\n'
        f'\t\t\t\t(size 1.27 1.27)\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{uid()}")\n'
        f'\t)'
    )


def global_label(name, x, y, angle=0, shape="bidirectional"):
    """Generate a global label S-expression."""
    return (
        f'(global_label "{name}"\n'
        f'\t\t(shape {shape})\n'
        f'\t\t(at {x} {y} {angle})\n'
        f'\t\t(effects\n'
        f'\t\t\t(font\n'
        f'\t\t\t\t(size 1.27 1.27)\n'
        f'\t\t\t)\n'
        f'\t\t\t(justify left)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{uid()}")\n'
        f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"\n'
        f'\t\t\t(at 0 0 0)\n'
        f'\t\t\t(effects\n'
        f'\t\t\t\t(font\n'
        f'\t\t\t\t\t(size 1.27 1.27)\n'
        f'\t\t\t\t)\n'
        f'\t\t\t\t(hide yes)\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t)'
    )


def wire(x1, y1, x2, y2):
    """Generate a wire S-expression."""
    return (
        f'(wire\n'
        f'\t\t(pts\n'
        f'\t\t\t(xy {x1} {y1}) (xy {x2} {y2})\n'
        f'\t\t)\n'
        f'\t\t(stroke\n'
        f'\t\t\t(width 0)\n'
        f'\t\t\t(type default)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{uid()}")\n'
        f'\t)'
    )


def no_connect(x, y):
    """Generate a no-connect flag."""
    return (
        f'(no_connect\n'
        f'\t\t(at {x} {y})\n'
        f'\t\t(uuid "{uid()}")\n'
        f'\t)'
    )


def power_flag(name, ref, x, y, angle=0):
    """Generate a power symbol instance."""
    return symbol_instance(f"power:{name}", ref, name, x, y, angle)


def text_note(text, x, y, size=2.54):
    """Generate a text annotation S-expression."""
    return (
        f'(text "{text}"\n'
        f'\t\t(exclude_from_sim no)\n'
        f'\t\t(at {x} {y} 0)\n'
        f'\t\t(effects\n'
        f'\t\t\t(font\n'
        f'\t\t\t\t(size {size} {size})\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(uuid "{uid()}")\n'
        f'\t)'
    )


def resistor(ref, value, x, y, angle=0, footprint="Resistor_SMD:R_0402_1005Metric"):
    """Place a resistor symbol."""
    return symbol_instance("Device:R", ref, value, x, y, angle,
                            footprint=footprint)


def capacitor(ref, value, x, y, angle=0, footprint="Capacitor_SMD:C_0402_1005Metric"):
    """Place a capacitor symbol."""
    return symbol_instance("Device:C", ref, value, x, y, angle,
                            footprint=footprint)


def led(ref, value, x, y, angle=0, footprint="LED_SMD:LED_0402_1005Metric"):
    """Place an LED symbol."""
    return symbol_instance("Device:LED", ref, value, x, y, angle,
                            footprint=footprint)


def button(ref, value, x, y, angle=0, footprint="Button_Switch_SMD:SW_SPST_SKQG"):
    """Place a tactile button symbol."""
    return symbol_instance("Switch:SW_Push", ref, value, x, y, angle,
                            footprint=footprint)


# =============================================================================
# CTRG2 (PROG) pinout -- from Neo Geo CTRG2 edge connector
# =============================================================================

CTRG2 = {
    1:  ("GND",     "GND"),
    2:  ("GND",     "GND"),
    3:  ("GND",     "GND"),
    4:  ("GND",     "GND"),
    5:  ("D0",      "A1"),
    6:  ("D1",      "A2"),
    7:  ("D2",      "A3"),
    8:  ("D3",      "A4"),
    9:  ("D4",      "A5"),
    10: ("D5",      "A6"),
    11: ("D6",      "A7"),
    12: ("D7",      "A8"),
    13: ("D8",      "A9"),
    14: ("D9",      "A10"),
    15: ("D10",     "A11"),
    16: ("D11",     "A12"),
    17: ("D12",     "A13"),
    18: ("D13",     "A14"),
    19: ("D14",     "A15"),
    20: ("D15",     "A16"),
    21: ("nRW",     "A17"),
    22: ("nAS",     "A18"),
    23: ("ROMOEU",  "A19"),
    24: ("ROMOEL",  "68KCLKB"),
    25: ("PORTOEU", "ROMWAIT"),
    26: ("PORTOEL", "PWAIT0"),
    27: ("PORTWEU", "PWAIT1"),
    28: ("PORTWEL", "PDTACK"),
    29: ("VCC",     "VCC"),
    30: ("VCC",     "VCC"),
    31: ("VCC",     "VCC"),
    32: ("VCC",     "VCC"),
    33: ("ROMOE",   "4MB"),
    34: ("NC",      "NC"),
    35: ("NC",      "RESET"),
    36: ("NC",      "NC"),
    37: ("NC",      "NC"),
    38: ("NC",      "NC"),
    39: ("NC",      "NC"),
    40: ("NC",      "SDPAD0"),
    41: ("NC",      "SDPAD1"),
    42: ("NC",      "SDPAD2"),
    43: ("SDPA8",   "SDPAD3"),
    44: ("SDPA9",   "SDPAD4"),
    45: ("SDPA10",  "SDPAD5"),
    46: ("SDPA11",  "SDPAD6"),
    47: ("SDRA8",   "SDPAD7"),
    48: ("SDRA9",   "SDRA0"),
    49: ("SDRA10",  "SDRA1"),
    50: ("SDRA11",  "SDRA2"),
    51: ("SDRA12",  "SDRA3"),
    52: ("SDRA13",  "SDRA4"),
    53: ("SDRA14",  "SDRA5"),
    54: ("SDRA15",  "SDRA6"),
    55: ("SDRA16",  "SDRA7"),
    56: ("SDRA17",  "SDROE"),
    57: ("SDRA18",  "SDRA19"),
    58: ("SDRA20",  "SDMRD"),
    59: ("GND",     "GND"),
    60: ("GND",     "GND"),
}

# =============================================================================
# Inter-board connector pin map (J5, 2x50 = 100 pins)
# =============================================================================

def interboard_pin_map():
    """Return dict of pin_number -> net_name for J5."""
    pins = {}
    # C ROM address CA0-CA23
    for i in range(24):
        pins[i + 1] = f"CA{i}"
    # C ROM data CR0-CR31
    for i in range(32):
        pins[i + 25] = f"CR{i}"
    # S ROM address SA0-SA15
    for i in range(16):
        pins[i + 57] = f"SA{i}"
    # S ROM data SD0-SD7
    for i in range(8):
        pins[i + 73] = f"SD{i}"
    # Control
    pins[81] = "SDMRD_CHA"
    pins[82] = "PCK1B"
    pins[83] = "PCK2B"
    # Power
    pins[84] = "VCC_3V3"
    pins[85] = "VCC_3V3"
    pins[86] = "VCC_3V3"
    pins[87] = "GND"
    pins[88] = "GND"
    pins[89] = "GND"
    pins[90] = "GND"
    # Spare GPIO
    for i in range(10):
        pins[i + 91] = f"SPARE_GPIO{i}"
    return pins


# =============================================================================
# Schematic generation -- each function returns a list of S-expression strings
# =============================================================================

def section_title_block():
    """Generate the schematic header with title block."""
    return (
        f'(kicad_sch\n'
        f'\t(version 20231120)\n'
        f'\t(generator "neocart_fpga_generator")\n'
        f'\t(generator_version "2.0")\n'
        f'\t(uuid "{uid()}")\n'
        f'\t(paper "A0")\n'
        f'\t(title_block\n'
        f'\t\t(title "NeoCart FPGA PROG Board")\n'
        f'\t\t(date "2026-04-25")\n'
        f'\t\t(rev "2.0")\n'
        f'\t\t(company "NeoScanSDK")\n'
        f'\t\t(comment 1 "FPGA-based Neo Geo MVS dev cart -- PROG board")\n'
        f'\t\t(comment 2 "ECP5-25 + 64MB SDRAM + RP2040 + USB-C + SD")\n'
        f'\t\t(comment 3 "Designed by Bruno Russo")\n'
        f'\t\t(comment 4 "neo.bruno.russo@gmail.com")\n'
        f'\t)\n'
        f'\t(lib_symbols\n'
        f'\t)\n'
    )


def section_fpga(elements, bx, by):
    """U1: Lattice ECP5-25 FPGA (LFE5U-25F-6BG256I)."""
    elements.append(text_note(
        "U1: Lattice ECP5-25F FPGA (LFE5U-25F-6BG256I) -- BGA-256, 197 IOs",
        bx - 30, by - 80, 2.5))

    elements.append(symbol_instance(
        "FPGA_Lattice:LFE5U-25F-xBG256", "U1", "LFE5U-25F-6BG256I",
        bx, by,
        footprint="Package_BGA:BGA-256_17.0x17.0mm_Layout16x16_P1.0mm",
        pins=[str(i) for i in range(1, 257)]
    ))

    # ---- FPGA power pins ----
    # VCC core (1.1V)
    for i in range(8):
        lx = bx - 50
        ly = by - 70 + i * 3
        elements.append(net_label("VCC_1V1", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # VCCIO (3.3V) -- all IO banks
    for i in range(8):
        lx = bx - 50
        ly = by - 44 + i * 3
        elements.append(net_label("VCC_3V3", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # VCCAUX (3.3V)
    for i in range(2):
        lx = bx - 50
        ly = by - 18 + i * 3
        elements.append(net_label("VCC_3V3", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # GND
    for i in range(8):
        lx = bx - 50
        ly = by - 8 + i * 3
        elements.append(net_label("GND", lx, ly, 0))
        elements.append(wire(lx, ly, lx + 5, ly))

    # ---- FPGA clock input ----
    elements.append(net_label("CLK_12M", bx - 50, by + 20, 0))
    elements.append(wire(bx - 50, by + 20, bx - 45, by + 20))

    # ---- FPGA config pins (directly to U6 W25Q32) ----
    cfg_y = by + 26
    for i, sig in enumerate(["CFG_MOSI", "CFG_MISO", "CFG_SCLK", "CFG_CSN",
                              "PROGRAMN", "INITN", "DONE"]):
        ly = cfg_y + i * 3
        elements.append(net_label(sig, bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # ---- FPGA -> SDRAM (right side of symbol) ----
    # Shared address A0-A12
    sdram_y = by - 70
    for i in range(13):
        ly = sdram_y + i * 2.54
        elements.append(net_label(f"SDRAM_A{i}", bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # Shared data DQ0-DQ15
    dq_y = sdram_y + 13 * 2.54 + 3
    for i in range(16):
        ly = dq_y + i * 2.54
        elements.append(net_label(f"SDRAM_DQ{i}", bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # Control: CLK, CKE, CSn[0], CSn[1], RASn, CASn, WEn, BA0, BA1, DQM0, DQM1
    ctrl_y = dq_y + 16 * 2.54 + 3
    sdram_ctrl_sigs = ["SDRAM_CLK", "SDRAM_CKE",
                       "SDRAM_CS0N", "SDRAM_CS1N",
                       "SDRAM_RASN", "SDRAM_CASN", "SDRAM_WEN",
                       "SDRAM_BA0", "SDRAM_BA1",
                       "SDRAM_DQM0", "SDRAM_DQM1"]
    for i, sig in enumerate(sdram_ctrl_sigs):
        ly = ctrl_y + i * 2.54
        elements.append(net_label(sig, bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # ---- FPGA -> PROG bus (bottom-left, after level shifters) ----
    # Address A1-A19 (via 470R series resistors from PROG connector)
    prog_addr_y = by + 52
    elements.append(text_note("PROG bus (via 470R input / 74LVC245 bidir)", bx - 30, prog_addr_y - 5, 1.5))
    for i in range(19):
        ly = prog_addr_y + i * 2.54
        elements.append(net_label(f"FPGA_PA{i + 1}", bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # Data D0-D15 (via 74LVC245)
    prog_data_y = prog_addr_y + 19 * 2.54 + 3
    for i in range(16):
        ly = prog_data_y + i * 2.54
        elements.append(net_label(f"FPGA_PD{i}", bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # Control signals (via 470R)
    prog_ctrl_y = prog_data_y + 16 * 2.54 + 3
    prog_ctrl_sigs = ["FPGA_ROMOE", "FPGA_ROMOEU", "FPGA_ROMOEL",
                      "FPGA_RW", "FPGA_SDROE"]
    for i, sig in enumerate(prog_ctrl_sigs):
        ly = prog_ctrl_y + i * 2.54
        elements.append(net_label(sig, bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # V ROM address (SDRA/SDPA) - via 470R
    vrom_y = prog_ctrl_y + 5 * 2.54 + 3
    for i in range(24):
        ly = vrom_y + i * 2.54
        elements.append(net_label(f"FPGA_VA{i}", bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # V ROM data (SDPAD0-7) - via 470R
    vrom_d_y = vrom_y + 24 * 2.54 + 3
    for i in range(8):
        ly = vrom_d_y + i * 2.54
        elements.append(net_label(f"FPGA_VD{i}", bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # 74LVC245 direction control
    dir_y = vrom_d_y + 8 * 2.54 + 3
    elements.append(net_label("FPGA_PDATA_DIR", bx - 50, dir_y, 0))
    elements.append(wire(bx - 50, dir_y, bx - 45, dir_y))
    elements.append(net_label("FPGA_PDATA_OEN", bx - 50, dir_y + 2.54, 0))
    elements.append(wire(bx - 50, dir_y + 2.54, bx - 45, dir_y + 2.54))

    # ---- FPGA -> CHA bus (via inter-board connector, bottom-right) ----
    cha_y = by + 52
    elements.append(text_note("CHA bus (via inter-board J5)", bx + 30, cha_y - 5, 1.5))

    # C ROM address CA0-CA23
    for i in range(24):
        ly = cha_y + i * 2.54
        elements.append(net_label(f"CA{i}", bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # C ROM data CR0-CR31
    cr_y = cha_y + 24 * 2.54 + 3
    for i in range(32):
        ly = cr_y + i * 2.54
        elements.append(net_label(f"CR{i}", bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # S ROM address SA0-SA15
    sa_y = cr_y + 32 * 2.54 + 3
    for i in range(16):
        ly = sa_y + i * 2.54
        elements.append(net_label(f"SA{i}", bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # S ROM data SD0-SD7
    sd_y = sa_y + 16 * 2.54 + 3
    for i in range(8):
        ly = sd_y + i * 2.54
        elements.append(net_label(f"SD{i}", bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # CHA control
    cha_ctrl_y = sd_y + 8 * 2.54 + 3
    for i, sig in enumerate(["SDMRD_CHA", "PCK1B", "PCK2B"]):
        ly = cha_ctrl_y + i * 2.54
        elements.append(net_label(sig, bx + 50, ly, 0))
        elements.append(wire(bx + 45, ly, bx + 50, ly))

    # ---- FPGA -> SPI slave (from RP2040) ----
    spi_y = dir_y + 2.54 * 4
    elements.append(text_note("SPI slave (from RP2040)", bx - 30, spi_y - 3, 1.5))
    spi_sigs = ["SPI_SCK", "SPI_MOSI", "SPI_MISO", "SPI_CSN", "SPI_IRQ"]
    for i, sig in enumerate(spi_sigs):
        ly = spi_y + i * 2.54
        elements.append(net_label(sig, bx - 50, ly, 0))
        elements.append(wire(bx - 50, ly, bx - 45, ly))

    # ---- FPGA status LEDs ----
    led_y = spi_y + 6 * 2.54
    elements.append(net_label("FPGA_LED_ACT", bx - 50, led_y, 0))
    elements.append(wire(bx - 50, led_y, bx - 45, led_y))


def section_sdram(elements, bx, by, unit_num, ref, cs_net):
    """U2/U3: Winbond W9825G6KH-6 SDRAM (TSOP-54, 32MB each)."""
    elements.append(text_note(
        f"{ref}: W9825G6KH-6 SDRAM (32MB, TSOP-54)",
        bx - 20, by - 55, 2.0))

    elements.append(symbol_instance(
        "Memory_RAM:W9825G6KH-6", ref, "W9825G6KH-6",
        bx, by,
        footprint="Package_SO:TSOP-II-54_22.2x10.16mm_P0.8mm",
        pins=[str(i) for i in range(1, 55)]
    ))

    # Address A0-A12 (shared bus)
    for i in range(13):
        ly = by - 45 + i * 2.54
        elements.append(net_label(f"SDRAM_A{i}", bx - 25, ly, 0))
        elements.append(wire(bx - 25, ly, bx - 20, ly))

    # Data DQ0-DQ15 (shared bus)
    for i in range(16):
        ly = by - 45 + (13 + i) * 2.54 + 3
        elements.append(net_label(f"SDRAM_DQ{i}", bx + 25, ly, 0))
        elements.append(wire(bx + 20, ly, bx + 25, ly))

    # Bank select BA0-BA1
    ba_y = by + 15
    elements.append(net_label("SDRAM_BA0", bx - 25, ba_y, 0))
    elements.append(wire(bx - 25, ba_y, bx - 20, ba_y))
    elements.append(net_label("SDRAM_BA1", bx - 25, ba_y + 2.54, 0))
    elements.append(wire(bx - 25, ba_y + 2.54, bx - 20, ba_y + 2.54))

    # Control
    ctrl_y = ba_y + 6
    ctrl_sigs = [
        ("SDRAM_CLK",  "CLK"),
        ("SDRAM_CKE",  "CKE"),
        (cs_net,       "CSn"),
        ("SDRAM_RASN", "RASn"),
        ("SDRAM_CASN", "CASn"),
        ("SDRAM_WEN",  "WEn"),
        ("SDRAM_DQM0", "LDQM"),
        ("SDRAM_DQM1", "UDQM"),
    ]
    for i, (net, _pin_name) in enumerate(ctrl_sigs):
        ly = ctrl_y + i * 2.54
        elements.append(net_label(net, bx - 25, ly, 0))
        elements.append(wire(bx - 25, ly, bx - 20, ly))

    # Power
    pwr_y = ctrl_y + len(ctrl_sigs) * 2.54 + 3
    elements.append(net_label("VCC_3V3", bx, by - 52, 0))
    elements.append(net_label("GND", bx, pwr_y, 0))

    # Decoupling caps (2x 100nF per SDRAM)
    cap_base = f"C_{ref}"
    elements.append(capacitor(f"{cap_base}_1", "100nF", bx + 30, by - 52, 0))
    elements.append(net_label("VCC_3V3", bx + 30, by - 57, 0))
    elements.append(net_label("GND", bx + 30, by - 47, 0))
    elements.append(capacitor(f"{cap_base}_2", "100nF", bx + 38, by - 52, 0))
    elements.append(net_label("VCC_3V3", bx + 38, by - 57, 0))
    elements.append(net_label("GND", bx + 38, by - 47, 0))


def section_rp2040(elements, bx, by):
    """U4: RP2040 microcontroller (QFN-56)."""
    elements.append(text_note(
        "U4: RP2040 -- USB-C, SD card, SPI master to FPGA",
        bx - 30, by - 65, 2.5))

    elements.append(symbol_instance(
        "MCU_RaspberryPi:RP2040", "U4", "RP2040",
        bx, by,
        footprint="Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
        pins=[str(i) for i in range(1, 57)]
    ))

    # ---- RP2040 GPIO assignments ----
    gpio_map = {
        # SPI master to FPGA
        "GPIO0":  "SPI_MISO",      # SPI RX (from FPGA)
        "GPIO1":  "SPI_CSN",       # SPI CS (active low)
        "GPIO2":  "SPI_SCK",       # SPI clock
        "GPIO3":  "SPI_MOSI",      # SPI TX (to FPGA)
        "GPIO4":  "SPI_IRQ",       # FPGA interrupt
        # SD card (SPI mode)
        "GPIO5":  "SD_MISO",
        "GPIO6":  "SD_CSN",
        "GPIO7":  "SD_SCK",
        "GPIO8":  "SD_MOSI",
        "GPIO9":  "SD_DET",        # Card detect
        # UART debug
        "GPIO10": "UART_TX",
        "GPIO11": "UART_RX",
        # FPGA control
        "GPIO12": "FPGA_PROGRAMN", # FPGA reconfig trigger
        "GPIO13": "FPGA_INITN",    # FPGA init status
        "GPIO14": "FPGA_DONE",     # FPGA config done
        # Status LEDs (accent control via RP2040 optionally)
        "GPIO15": "MCU_LED_SPARE",
        # Spare
        "GPIO16": "MCU_SPARE0",
        "GPIO17": "MCU_SPARE1",
        "GPIO18": "MCU_SPARE2",
        "GPIO19": "MCU_SPARE3",
        "GPIO20": "MCU_SPARE4",
        "GPIO21": "MCU_SPARE5",
        "GPIO22": "MCU_SPARE6",
        "GPIO23": "MCU_SPARE7",
        "GPIO24": "MCU_SPARE8",
        "GPIO25": "MCU_SPARE9",
        "GPIO26": "MCU_ADC0",
        "GPIO27": "MCU_ADC1",
        "GPIO28": "MCU_ADC2",
        "GPIO29": "MCU_ADC3",
    }

    for i, (gpio, net) in enumerate(gpio_map.items()):
        lx = bx + 35
        ly = by - 55 + i * 2.54
        elements.append(net_label(net, lx, ly, 0))
        elements.append(wire(lx - 5, ly, lx, ly))

    # USB D+/D-
    elements.append(net_label("USB_DP", bx - 35, by - 10, 180))
    elements.append(wire(bx - 35, by - 10, bx - 30, by - 10))
    elements.append(net_label("USB_DM", bx - 35, by - 7, 180))
    elements.append(wire(bx - 35, by - 7, bx - 30, by - 7))

    # QSPI flash interface (for RP2040 firmware, U5)
    qspi_y = by - 40
    qspi_sigs = ["QSPI_SCLK", "QSPI_SS", "QSPI_SD0", "QSPI_SD1",
                  "QSPI_SD2", "QSPI_SD3"]
    for i, sig in enumerate(qspi_sigs):
        ly = qspi_y + i * 2.54
        elements.append(net_label(sig, bx - 35, ly, 180))
        elements.append(wire(bx - 35, ly, bx - 30, ly))

    # Crystal pins
    elements.append(net_label("XIN", bx - 35, by + 20, 180))
    elements.append(wire(bx - 35, by + 20, bx - 30, by + 20))
    elements.append(net_label("XOUT", bx - 35, by + 23, 180))
    elements.append(wire(bx - 35, by + 23, bx - 30, by + 23))

    # RUN pin (active high, active low reset)
    elements.append(net_label("MCU_RUN", bx - 35, by + 28, 180))
    elements.append(wire(bx - 35, by + 28, bx - 30, by + 28))

    # Power pins
    # IOVDD (3.3V)
    for i in range(3):
        ly = by + 35 + i * 2.54
        elements.append(net_label("VCC_3V3", bx - 35, ly, 180))
        elements.append(wire(bx - 35, ly, bx - 30, ly))

    # DVDD (1.1V internal, decoupled)
    elements.append(net_label("VCC_1V1_MCU", bx - 35, by + 45, 180))
    elements.append(wire(bx - 35, by + 45, bx - 30, by + 45))

    # USB_VDD (3.3V for USB PHY)
    elements.append(net_label("VCC_3V3", bx - 35, by + 48, 180))
    elements.append(wire(bx - 35, by + 48, bx - 30, by + 48))

    # ADC_AVDD
    elements.append(net_label("VCC_3V3", bx - 35, by + 51, 180))
    elements.append(wire(bx - 35, by + 51, bx - 30, by + 51))

    # GND
    elements.append(net_label("GND", bx, by + 58, 0))

    # RP2040 decoupling
    for i in range(6):
        cx = bx + 50 + i * 8
        elements.append(capacitor(f"C_U4_{i + 1}", "100nF", cx, by + 60, 0))
        elements.append(net_label("VCC_3V3", cx, by + 55, 0))
        elements.append(net_label("GND", cx, by + 65, 0))

    # 1uF on USB_VDD
    elements.append(capacitor("C_U4_USB", "1uF", bx + 50, by + 72, 0,
                               footprint="Capacitor_SMD:C_0402_1005Metric"))
    elements.append(net_label("VCC_3V3", bx + 50, by + 67, 0))
    elements.append(net_label("GND", bx + 50, by + 77, 0))


def section_w25q32_rp2040(elements, bx, by):
    """U5: W25Q32 -- RP2040 firmware storage (QSPI)."""
    elements.append(text_note(
        "U5: W25Q32 -- RP2040 QSPI firmware flash",
        bx - 15, by - 25, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:W25Q32JVSS", "U5", "W25Q32_FW",
        bx, by,
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        pins=[str(i) for i in range(1, 9)]
    ))

    # Pin connections
    elements.append(net_label("QSPI_SS", bx - 18, by - 5, 0))
    elements.append(wire(bx - 18, by - 5, bx - 13, by - 5))

    elements.append(net_label("QSPI_SD0", bx - 18, by - 2, 0))
    elements.append(wire(bx - 18, by - 2, bx - 13, by - 2))

    elements.append(net_label("QSPI_SD1", bx - 18, by + 1, 0))
    elements.append(wire(bx - 18, by + 1, bx - 13, by + 1))

    elements.append(net_label("QSPI_SCLK", bx - 18, by + 4, 0))
    elements.append(wire(bx - 18, by + 4, bx - 13, by + 4))

    elements.append(net_label("QSPI_SD2", bx + 18, by - 5, 0))
    elements.append(wire(bx + 13, by - 5, bx + 18, by - 5))

    elements.append(net_label("QSPI_SD3", bx + 18, by - 2, 0))
    elements.append(wire(bx + 13, by - 2, bx + 18, by - 2))

    # Power
    elements.append(net_label("VCC_3V3", bx, by - 15, 0))
    elements.append(net_label("GND", bx, by + 15, 0))

    # Decoupling
    elements.append(capacitor("C_U5", "100nF", bx + 25, by - 15, 0))
    elements.append(net_label("VCC_3V3", bx + 25, by - 20, 0))
    elements.append(net_label("GND", bx + 25, by - 10, 0))


def section_w25q32_fpga(elements, bx, by):
    """U6: W25Q32 -- FPGA bitstream storage (SPI)."""
    elements.append(text_note(
        "U6: W25Q32 -- FPGA bitstream flash (ECP5 SPI config)",
        bx - 15, by - 25, 2.0))

    elements.append(symbol_instance(
        "Memory_Flash:W25Q32JVSS", "U6", "W25Q32_CFG",
        bx, by,
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        pins=[str(i) for i in range(1, 9)]
    ))

    # ECP5 SPI config: directly connected to FPGA config pins
    elements.append(net_label("CFG_CSN", bx - 18, by - 5, 0))
    elements.append(wire(bx - 18, by - 5, bx - 13, by - 5))

    elements.append(net_label("CFG_MOSI", bx - 18, by - 2, 0))
    elements.append(wire(bx - 18, by - 2, bx - 13, by - 2))

    elements.append(net_label("CFG_MISO", bx - 18, by + 1, 0))
    elements.append(wire(bx - 18, by + 1, bx - 13, by + 1))

    elements.append(net_label("CFG_SCLK", bx - 18, by + 4, 0))
    elements.append(wire(bx - 18, by + 4, bx - 13, by + 4))

    # WP and HOLD pulled high
    elements.append(net_label("VCC_3V3", bx + 18, by - 5, 0))
    elements.append(wire(bx + 13, by - 5, bx + 18, by - 5))
    elements.append(net_label("VCC_3V3", bx + 18, by - 2, 0))
    elements.append(wire(bx + 13, by - 2, bx + 18, by - 2))

    # Power
    elements.append(net_label("VCC_3V3", bx, by - 15, 0))
    elements.append(net_label("GND", bx, by + 15, 0))

    # Decoupling
    elements.append(capacitor("C_U6", "100nF", bx + 25, by - 15, 0))
    elements.append(net_label("VCC_3V3", bx + 25, by - 20, 0))
    elements.append(net_label("GND", bx + 25, by - 10, 0))


def section_74lvc245(elements, bx, by, ref, bus_label, bit_start, bit_end):
    """U7/U8: 74LVC245 bidirectional level shifter for PROG data bus.

    A-side: 5V from Neo Geo (PROG connector)
    B-side: 3.3V to FPGA
    """
    n_bits = bit_end - bit_start
    elements.append(text_note(
        f"{ref}: 74LVC245 -- D{bit_start}-D{bit_end - 1} level shift (5V <-> 3.3V)",
        bx - 20, by - 30, 2.0))

    elements.append(symbol_instance(
        "74xx:74LVC245", ref, "74LVC245",
        bx, by,
        footprint="Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm",
        pins=[str(i) for i in range(1, 21)]
    ))

    # A side (5V, from PROG connector)
    for i in range(n_bits):
        bit = bit_start + i
        ly = by - 12 + i * 2.54
        elements.append(net_label(f"PROG_D{bit}", bx - 20, ly, 0))
        elements.append(wire(bx - 20, ly, bx - 15, ly))

    # B side (3.3V, to FPGA)
    for i in range(n_bits):
        bit = bit_start + i
        ly = by - 12 + i * 2.54
        elements.append(net_label(f"FPGA_PD{bit}", bx + 20, ly, 0))
        elements.append(wire(bx + 15, ly, bx + 20, ly))

    # Direction control from FPGA
    elements.append(net_label("FPGA_PDATA_DIR", bx - 20, by + 12, 0))
    elements.append(wire(bx - 20, by + 12, bx - 15, by + 12))

    # Output enable from FPGA
    elements.append(net_label("FPGA_PDATA_OEN", bx - 20, by + 15, 0))
    elements.append(wire(bx - 20, by + 15, bx - 15, by + 15))

    # Power: A-side VCC = 5V (Neo Geo rail), B-side VCC = 3.3V
    elements.append(net_label("VCC_5V", bx - 5, by - 22, 0))
    elements.append(net_label("VCC_3V3", bx + 5, by - 22, 0))
    elements.append(net_label("GND", bx, by + 22, 0))

    # Decoupling
    elements.append(capacitor(f"C_{ref}_A", "100nF", bx - 10, by - 28, 0))
    elements.append(net_label("VCC_5V", bx - 10, by - 33, 0))
    elements.append(net_label("GND", bx - 10, by - 23, 0))
    elements.append(capacitor(f"C_{ref}_B", "100nF", bx + 10, by - 28, 0))
    elements.append(net_label("VCC_3V3", bx + 10, by - 33, 0))
    elements.append(net_label("GND", bx + 10, by - 23, 0))


def section_series_resistors(elements, bx, by):
    """470 ohm series resistors for 5V->3.3V input protection on PROG bus signals.

    All PROG bus INPUT signals (address, control) go through 470R between
    the edge connector and FPGA. The FPGA's internal ESD clamp handles the
    remaining voltage drop.
    """
    elements.append(text_note(
        "470R Series Resistors -- PROG bus 5V input protection",
        bx - 10, by - 20, 2.5))
    elements.append(text_note(
        "5V from Neo Geo -> 470R -> FPGA IO (3.3V bank, ESD clamp absorbs excess)",
        bx - 10, by - 14, 1.5))

    r_idx = 1

    # Address A1-A19 (19 resistors)
    elements.append(text_note("Address A1-A19", bx - 10, by - 5, 1.5))
    for i in range(19):
        col = i % 10
        row = i // 10
        rx = bx + col * 18
        ry = by + row * 12
        ref_name = f"R{r_idx}"
        elements.append(resistor(ref_name, "470R", rx, ry, 0))
        elements.append(net_label(f"CONN_A{i + 1}", rx - 8, ry, 180))
        elements.append(wire(rx - 8, ry, rx - 5, ry))
        elements.append(net_label(f"FPGA_PA{i + 1}", rx + 8, ry, 0))
        elements.append(wire(rx + 5, ry, rx + 8, ry))
        r_idx += 1

    # Control signals: ROMOE, ROMOEU, ROMOEL, RW, nAS, SDROE (6 resistors)
    ctrl_y = by + 30
    elements.append(text_note("Control signals", bx - 10, ctrl_y - 5, 1.5))
    ctrl_pairs = [
        ("CONN_ROMOE",  "FPGA_ROMOE"),
        ("CONN_ROMOEU", "FPGA_ROMOEU"),
        ("CONN_ROMOEL", "FPGA_ROMOEL"),
        ("CONN_RW",     "FPGA_RW"),
        ("CONN_nAS",    "FPGA_nAS"),
        ("CONN_SDROE",  "FPGA_SDROE"),
    ]
    for i, (in_net, out_net) in enumerate(ctrl_pairs):
        rx = bx + i * 18
        ry = ctrl_y
        ref_name = f"R{r_idx}"
        elements.append(resistor(ref_name, "470R", rx, ry, 0))
        elements.append(net_label(in_net, rx - 8, ry, 180))
        elements.append(wire(rx - 8, ry, rx - 5, ry))
        elements.append(net_label(out_net, rx + 8, ry, 0))
        elements.append(wire(rx + 5, ry, rx + 8, ry))
        r_idx += 1

    # V ROM address (SDRA/SDPA, 24 lines, 24 resistors)
    va_y = ctrl_y + 18
    elements.append(text_note("V ROM address (SDRA/SDPA)", bx - 10, va_y - 5, 1.5))
    for i in range(24):
        col = i % 10
        row = i // 10
        rx = bx + col * 18
        ry = va_y + row * 12
        ref_name = f"R{r_idx}"
        elements.append(resistor(ref_name, "470R", rx, ry, 0))
        elements.append(net_label(f"CONN_VA{i}", rx - 8, ry, 180))
        elements.append(wire(rx - 8, ry, rx - 5, ry))
        elements.append(net_label(f"FPGA_VA{i}", rx + 8, ry, 0))
        elements.append(wire(rx + 5, ry, rx + 8, ry))
        r_idx += 1

    # V ROM data (SDPAD0-7, 8 resistors)
    vd_y = va_y + 42
    elements.append(text_note("V ROM data (SDPAD0-7)", bx - 10, vd_y - 5, 1.5))
    for i in range(8):
        rx = bx + i * 18
        ry = vd_y
        ref_name = f"R{r_idx}"
        elements.append(resistor(ref_name, "470R", rx, ry, 0))
        elements.append(net_label(f"CONN_VD{i}", rx - 8, ry, 180))
        elements.append(wire(rx - 8, ry, rx - 5, ry))
        elements.append(net_label(f"FPGA_VD{i}", rx + 8, ry, 0))
        elements.append(wire(rx + 5, ry, rx + 8, ry))
        r_idx += 1

    # Additional control: 68KCLKB, ROMWAIT, RESET, 4MB, PDTACK, PORTOEU, etc.
    misc_y = vd_y + 18
    elements.append(text_note("Miscellaneous PROG bus inputs", bx - 10, misc_y - 5, 1.5))
    misc_pairs = [
        ("CONN_68KCLKB", "FPGA_68KCLKB"),
        ("CONN_ROMWAIT", "FPGA_ROMWAIT"),
        ("CONN_RESET",   "FPGA_RESET"),
        ("CONN_4MB",     "FPGA_4MB"),
        ("CONN_PDTACK",  "FPGA_PDTACK"),
        ("CONN_SDMRD",   "FPGA_SDMRD_PROG"),
    ]
    for i, (in_net, out_net) in enumerate(misc_pairs):
        rx = bx + i * 18
        ry = misc_y
        ref_name = f"R{r_idx}"
        elements.append(resistor(ref_name, "470R", rx, ry, 0))
        elements.append(net_label(in_net, rx - 8, ry, 180))
        elements.append(wire(rx - 8, ry, rx - 5, ry))
        elements.append(net_label(out_net, rx + 8, ry, 0))
        elements.append(wire(rx + 5, ry, rx + 8, ry))
        r_idx += 1

    return r_idx  # return next available resistor index


def section_prog_connector(elements, bx, by):
    """J1/J2: MVS PROG edge connector (CTRG2) -- 2x60 pins (gold fingers).

    J1 = A-side (bottom of PCB), J2 = B-side (top of PCB).
    Signals map to net labels matching CONN_* for protected inputs,
    PROG_D* for 74LVC245-buffered data, and direct power/GND.
    """
    elements.append(text_note(
        "J1/J2: MVS PROG Edge Connector (CTRG2) -- 2x60 gold fingers",
        bx - 10, by - 75, 2.5))

    # -- J1: A-side connector --
    elements.append(text_note("J1: CTRG2 Side A (bottom)", bx - 5, by - 65, 2.0))
    elements.append(symbol_instance(
        "Connector_Generic:Conn_01x60", "J1", "CTRG2_A",
        bx, by,
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x60_P2.54mm_Vertical",
        pins=[str(i) for i in range(1, 61)]
    ))

    # Map A-side signals
    for pin_num in sorted(CTRG2.keys()):
        sig_a, _sig_b = CTRG2[pin_num]
        ly = by - 60 + (pin_num - 1) * 2.54
        if sig_a == "GND":
            elements.append(net_label("GND", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        elif sig_a == "VCC":
            elements.append(net_label("VCC_5V", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        elif sig_a == "NC":
            elements.append(no_connect(bx - 13, ly))
        elif sig_a.startswith("D") and sig_a[1:].isdigit():
            # Data lines go through 74LVC245
            elements.append(net_label(f"PROG_{sig_a}", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        elif sig_a in ("nRW", "nAS"):
            elements.append(net_label(f"CONN_{sig_a}", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        elif sig_a in ("ROMOEU", "ROMOEL", "ROMOE"):
            elements.append(net_label(f"CONN_{sig_a}", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        elif sig_a.startswith("PORT"):
            elements.append(net_label(f"CONN_{sig_a}", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        elif sig_a.startswith("SDPA") or sig_a.startswith("SDRA"):
            # V ROM address on A-side
            elements.append(net_label(f"CONN_VA_{sig_a}", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))
        else:
            elements.append(net_label(f"CONN_{sig_a}", bx - 18, ly, 0))
            elements.append(wire(bx - 18, ly, bx - 13, ly))

    # -- J2: B-side connector --
    j2x = bx + 60
    elements.append(text_note("J2: CTRG2 Side B (top)", j2x - 5, by - 65, 2.0))
    elements.append(symbol_instance(
        "Connector_Generic:Conn_01x60", "J2", "CTRG2_B",
        j2x, by,
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x60_P2.54mm_Vertical",
        pins=[str(i) for i in range(1, 61)]
    ))

    for pin_num in sorted(CTRG2.keys()):
        _sig_a, sig_b = CTRG2[pin_num]
        ly = by - 60 + (pin_num - 1) * 2.54
        if sig_b == "GND":
            elements.append(net_label("GND", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        elif sig_b == "VCC":
            elements.append(net_label("VCC_5V", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        elif sig_b == "NC":
            elements.append(no_connect(j2x + 13, ly))
        elif sig_b.startswith("A") and sig_b[1:].isdigit():
            # 68k address
            addr_num = int(sig_b[1:])
            elements.append(net_label(f"CONN_A{addr_num}", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        elif sig_b.startswith("SDPAD"):
            # V ROM data
            dnum = int(sig_b[5:])
            elements.append(net_label(f"CONN_VD{dnum}", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        elif sig_b.startswith("SDRA") or sig_b.startswith("SDPA"):
            # V ROM / sound address
            elements.append(net_label(f"CONN_VA_{sig_b}", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        elif sig_b in ("SDROE", "SDMRD"):
            elements.append(net_label(f"CONN_{sig_b}", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        elif sig_b in ("RESET", "68KCLKB", "ROMWAIT", "4MB", "PDTACK",
                        "PWAIT0", "PWAIT1"):
            elements.append(net_label(f"CONN_{sig_b}", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))
        else:
            elements.append(net_label(f"CONN_{sig_b}", j2x + 18, ly, 0))
            elements.append(wire(j2x + 13, ly, j2x + 18, ly))


def section_usb_c(elements, bx, by):
    """J3: USB-C receptacle (USB 2.0, 14-pin)."""
    elements.append(text_note(
        "J3: USB-C Receptacle (USB 2.0) -- PC communication via RP2040",
        bx - 15, by - 30, 2.0))

    elements.append(symbol_instance(
        "Connector:USB_C_Receptacle_USB2.0_14P", "J3", "USB_C",
        bx, by,
        footprint="Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal"
    ))

    # USB data through series resistors
    elements.append(net_label("USB_DP_CONN", bx + 20, by - 8, 0))
    elements.append(wire(bx + 15, by - 8, bx + 20, by - 8))
    elements.append(net_label("USB_DM_CONN", bx + 20, by - 5, 0))
    elements.append(wire(bx + 15, by - 5, bx + 20, by - 5))

    # VBUS
    elements.append(net_label("VBUS", bx + 20, by - 14, 0))
    elements.append(wire(bx + 15, by - 14, bx + 20, by - 14))

    # CC1/CC2 with 5.1K pull-down (UFP/sink identification)
    elements.append(net_label("USB_CC1", bx + 20, by + 2, 0))
    elements.append(wire(bx + 15, by + 2, bx + 20, by + 2))
    elements.append(net_label("USB_CC2", bx + 20, by + 5, 0))
    elements.append(wire(bx + 15, by + 5, bx + 20, by + 5))

    # Shield / GND
    elements.append(net_label("GND", bx, by + 18, 0))

    # --- CC resistors (5.1K to GND for UFP identification) ---
    elements.append(resistor("R_CC1", "5.1K", bx + 35, by + 2, 0))
    elements.append(net_label("USB_CC1", bx + 27, by + 2, 0))
    elements.append(wire(bx + 27, by + 2, bx + 30, by + 2))
    elements.append(net_label("GND", bx + 43, by + 2, 0))
    elements.append(wire(bx + 40, by + 2, bx + 43, by + 2))

    elements.append(resistor("R_CC2", "5.1K", bx + 35, by + 5, 0))
    elements.append(net_label("USB_CC2", bx + 27, by + 5, 0))
    elements.append(wire(bx + 27, by + 5, bx + 30, by + 5))
    elements.append(net_label("GND", bx + 43, by + 5, 0))
    elements.append(wire(bx + 40, by + 5, bx + 43, by + 5))

    # --- USB series resistors (27 ohm) ---
    elements.append(text_note("27R USB series resistors", bx + 28, by - 15, 1.5))
    elements.append(resistor("R_USB_DP", "27R", bx + 35, by - 8, 0))
    elements.append(net_label("USB_DP_CONN", bx + 27, by - 8, 0))
    elements.append(wire(bx + 27, by - 8, bx + 30, by - 8))
    elements.append(net_label("USB_DP", bx + 43, by - 8, 0))
    elements.append(wire(bx + 40, by - 8, bx + 43, by - 8))

    elements.append(resistor("R_USB_DM", "27R", bx + 35, by - 5, 0))
    elements.append(net_label("USB_DM_CONN", bx + 27, by - 5, 0))
    elements.append(wire(bx + 27, by - 5, bx + 30, by - 5))
    elements.append(net_label("USB_DM", bx + 43, by - 5, 0))
    elements.append(wire(bx + 40, by - 5, bx + 43, by - 5))


def section_sd_card(elements, bx, by):
    """J4: microSD card slot (SPI mode)."""
    elements.append(text_note(
        "J4: microSD Card Slot (SPI mode via RP2040)",
        bx - 15, by - 25, 2.0))

    elements.append(symbol_instance(
        "Connector:Micro_SD_Card_Det", "J4", "microSD",
        bx, by,
        footprint="Connector_Card:microSD_HC_Molex_104031-0811"
    ))

    # SD card SPI signals
    sd_sigs = [
        ("SD_MISO",  "DAT0/MISO"),
        ("SD_MOSI",  "CMD/MOSI"),
        ("SD_SCK",   "CLK/SCK"),
        ("SD_CSN",   "DAT3/CS"),
    ]
    for i, (net, _desc) in enumerate(sd_sigs):
        ly = by - 8 + i * 3
        elements.append(net_label(net, bx - 20, ly, 0))
        elements.append(wire(bx - 20, ly, bx - 15, ly))

    # Card detect
    elements.append(net_label("SD_DET", bx - 20, by + 8, 0))
    elements.append(wire(bx - 20, by + 8, bx - 15, by + 8))

    # Power (3.3V)
    elements.append(net_label("VCC_3V3", bx, by - 18, 0))
    elements.append(net_label("GND", bx, by + 15, 0))

    # Decoupling
    elements.append(capacitor("C_SD", "100nF", bx + 20, by - 18, 0))
    elements.append(net_label("VCC_3V3", bx + 20, by - 23, 0))
    elements.append(net_label("GND", bx + 20, by - 13, 0))

    # 10K pull-ups on all SD SPI lines (required for SPI mode)
    for i, net in enumerate(["SD_MISO", "SD_MOSI", "SD_CSN"]):
        rx = bx + 30 + i * 10
        elements.append(resistor(f"R_SD_{i}", "10K", rx, by - 25, 90))
        elements.append(net_label(net, rx, by - 20, 0))
        elements.append(net_label("VCC_3V3", rx, by - 30, 0))


def section_interboard(elements, bx, by):
    """J5: 2x50 pin socket for inter-board connection to CHA board."""
    elements.append(text_note(
        "J5: Inter-board Connector (2x50 = 100 pins) -- to CHA board",
        bx - 10, by - 135, 2.5))

    elements.append(symbol_instance(
        "Connector_Generic:Conn_02x50_Odd_Even", "J5", "CHA_INTERBOARD",
        bx, by,
        footprint="Connector_PinSocket_2.54mm:PinSocket_2x50_P2.54mm_Vertical",
        pins=[str(i) for i in range(1, 101)]
    ))

    pin_map = interboard_pin_map()

    for pin_num in sorted(pin_map.keys()):
        net = pin_map[pin_num]
        # Odd pins on left, even on right
        if pin_num % 2 == 1:
            ly = by - 125 + ((pin_num - 1) // 2) * 2.54
            elements.append(net_label(net, bx - 22, ly, 0))
            elements.append(wire(bx - 22, ly, bx - 17, ly))
        else:
            ly = by - 125 + ((pin_num - 2) // 2) * 2.54
            elements.append(net_label(net, bx + 22, ly, 0))
            elements.append(wire(bx + 17, ly, bx + 22, ly))


def section_jtag(elements, bx, by):
    """J6: JTAG header (6-pin: TDI, TDO, TMS, TCK, GND, VCC)."""
    elements.append(text_note(
        "J6: JTAG Header -- ECP5 FPGA programming/debug",
        bx - 10, by - 18, 2.0))

    elements.append(symbol_instance(
        "Connector_Generic:Conn_02x03_Odd_Even", "J6", "JTAG",
        bx, by,
        footprint="Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical",
        pins=[str(i) for i in range(1, 7)]
    ))

    jtag_sigs = {
        1: "JTAG_TMS",
        2: "VCC_3V3",
        3: "JTAG_TCK",
        4: "GND",
        5: "JTAG_TDO",
        6: "JTAG_TDI",
    }
    for pin, net in jtag_sigs.items():
        if pin % 2 == 1:
            ly = by - 3 + ((pin - 1) // 2) * 2.54
            elements.append(net_label(net, bx - 15, ly, 0))
            elements.append(wire(bx - 15, ly, bx - 10, ly))
        else:
            ly = by - 3 + ((pin - 2) // 2) * 2.54
            elements.append(net_label(net, bx + 15, ly, 0))
            elements.append(wire(bx + 10, ly, bx + 15, ly))


def section_uart(elements, bx, by):
    """J7: UART header (3-pin: TX, RX, GND)."""
    elements.append(text_note(
        "J7: UART Header -- RP2040 debug serial",
        bx - 10, by - 15, 2.0))

    elements.append(symbol_instance(
        "Connector_Generic:Conn_01x03", "J7", "UART",
        bx, by,
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        pins=["1", "2", "3"]
    ))

    elements.append(net_label("UART_TX", bx - 15, by - 3, 0))
    elements.append(wire(bx - 15, by - 3, bx - 10, by - 3))
    elements.append(net_label("UART_RX", bx - 15, by, 0))
    elements.append(wire(bx - 15, by, bx - 10, by))
    elements.append(net_label("GND", bx - 15, by + 3, 0))
    elements.append(wire(bx - 15, by + 3, bx - 10, by + 3))


def section_power(elements, bx, by):
    """U9: AMS1117-3.3 and U10: AMS1117-1.1 power regulators."""
    # ---- U9: 5V -> 3.3V ----
    elements.append(text_note(
        "U9: AMS1117-3.3 -- 5V (Neo Geo) -> 3.3V (FPGA IO + SDRAM)",
        bx - 15, by - 25, 2.0))

    elements.append(symbol_instance(
        "Regulator_Linear:AMS1117-3.3", "U9", "AMS1117-3.3",
        bx, by,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2"
    ))

    elements.append(net_label("VCC_5V", bx - 20, by, 180))
    elements.append(wire(bx - 20, by, bx - 15, by))
    elements.append(net_label("VCC_3V3", bx + 20, by, 0))
    elements.append(wire(bx + 15, by, bx + 20, by))
    elements.append(net_label("GND", bx, by + 12, 0))

    # Input cap (10uF + 100nF)
    elements.append(capacitor("C_U9_IN1", "10uF", bx - 25, by - 15, 0,
                               footprint="Capacitor_SMD:C_0805_2012Metric"))
    elements.append(net_label("VCC_5V", bx - 25, by - 20, 0))
    elements.append(net_label("GND", bx - 25, by - 10, 0))
    elements.append(capacitor("C_U9_IN2", "100nF", bx - 17, by - 15, 0))
    elements.append(net_label("VCC_5V", bx - 17, by - 20, 0))
    elements.append(net_label("GND", bx - 17, by - 10, 0))

    # Output cap (10uF + 100nF)
    elements.append(capacitor("C_U9_OUT1", "10uF", bx + 20, by - 15, 0,
                               footprint="Capacitor_SMD:C_0805_2012Metric"))
    elements.append(net_label("VCC_3V3", bx + 20, by - 20, 0))
    elements.append(net_label("GND", bx + 20, by - 10, 0))
    elements.append(capacitor("C_U9_OUT2", "100nF", bx + 28, by - 15, 0))
    elements.append(net_label("VCC_3V3", bx + 28, by - 20, 0))
    elements.append(net_label("GND", bx + 28, by - 10, 0))

    # ---- U10: 3.3V -> 1.1V ----
    u10x = bx
    u10y = by + 50
    elements.append(text_note(
        "U10: AMS1117-1.1 -- 3.3V -> 1.1V (FPGA core)",
        u10x - 15, u10y - 25, 2.0))

    elements.append(symbol_instance(
        "Regulator_Linear:AMS1117-1.8", "U10", "AMS1117-1.1",
        u10x, u10y,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2"
    ))

    elements.append(net_label("VCC_3V3", u10x - 20, u10y, 180))
    elements.append(wire(u10x - 20, u10y, u10x - 15, u10y))
    elements.append(net_label("VCC_1V1", u10x + 20, u10y, 0))
    elements.append(wire(u10x + 15, u10y, u10x + 20, u10y))
    elements.append(net_label("GND", u10x, u10y + 12, 0))

    # Input cap
    elements.append(capacitor("C_U10_IN1", "10uF", u10x - 25, u10y - 15, 0,
                               footprint="Capacitor_SMD:C_0805_2012Metric"))
    elements.append(net_label("VCC_3V3", u10x - 25, u10y - 20, 0))
    elements.append(net_label("GND", u10x - 25, u10y - 10, 0))
    elements.append(capacitor("C_U10_IN2", "100nF", u10x - 17, u10y - 15, 0))
    elements.append(net_label("VCC_3V3", u10x - 17, u10y - 20, 0))
    elements.append(net_label("GND", u10x - 17, u10y - 10, 0))

    # Output cap
    elements.append(capacitor("C_U10_OUT1", "10uF", u10x + 20, u10y - 15, 0,
                               footprint="Capacitor_SMD:C_0805_2012Metric"))
    elements.append(net_label("VCC_1V1", u10x + 20, u10y - 20, 0))
    elements.append(net_label("GND", u10x + 20, u10y - 10, 0))
    elements.append(capacitor("C_U10_OUT2", "100nF", u10x + 28, u10y - 15, 0))
    elements.append(net_label("VCC_1V1", u10x + 28, u10y - 20, 0))
    elements.append(net_label("GND", u10x + 28, u10y - 10, 0))

    # Power flags
    elements.append(power_flag("PWR_FLAG", "#PWR01", bx - 35, by - 5, 0))
    elements.append(net_label("VCC_5V", bx - 35, by - 5, 0))
    elements.append(power_flag("PWR_FLAG", "#PWR02", bx + 35, by - 5, 0))
    elements.append(net_label("VCC_3V3", bx + 35, by - 5, 0))
    elements.append(power_flag("PWR_FLAG", "#PWR03", u10x + 35, u10y - 5, 0))
    elements.append(net_label("VCC_1V1", u10x + 35, u10y - 5, 0))
    elements.append(power_flag("GND", "#PWR04", bx, by + 18, 0))
    elements.append(net_label("GND", bx, by + 18, 0))


def section_crystal(elements, bx, by):
    """Y1: 12MHz crystal (3215 package) with load caps."""
    elements.append(text_note(
        "Y1: 12MHz Crystal -- RP2040 clock source",
        bx - 10, by - 20, 2.0))

    elements.append(symbol_instance(
        "Device:Crystal", "Y1", "12MHz",
        bx, by,
        footprint="Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm"
    ))

    elements.append(net_label("XIN", bx - 10, by, 180))
    elements.append(wire(bx - 10, by, bx - 5, by))
    elements.append(net_label("XOUT", bx + 10, by, 0))
    elements.append(wire(bx + 5, by, bx + 10, by))

    # Load caps (15pF to GND)
    elements.append(capacitor("C_Y1_1", "15pF", bx - 10, by + 10, 0))
    elements.append(net_label("XIN", bx - 10, by + 5, 0))
    elements.append(net_label("GND", bx - 10, by + 15, 0))

    elements.append(capacitor("C_Y1_2", "15pF", bx + 10, by + 10, 0))
    elements.append(net_label("XOUT", bx + 10, by + 5, 0))
    elements.append(net_label("GND", bx + 10, by + 15, 0))


def section_buttons(elements, bx, by):
    """SW1: BOOTSEL, SW2: RESET."""
    # SW1: BOOTSEL (holds QSPI_SS low during power-on for RP2040 UF2 mode)
    elements.append(text_note(
        "SW1: BOOTSEL -- hold during power-on for RP2040 USB boot mode",
        bx - 10, by - 15, 2.0))
    elements.append(button("SW1", "BOOTSEL", bx, by,
                            footprint="Button_Switch_SMD:SW_SPST_TL3342"))
    elements.append(net_label("QSPI_SS", bx - 10, by, 180))
    elements.append(wire(bx - 10, by, bx - 5, by))
    elements.append(net_label("GND", bx + 10, by, 0))
    elements.append(wire(bx + 5, by, bx + 10, by))

    # SW2: RESET (active low to FPGA PROGRAMN and RP2040 RUN)
    sw2y = by + 20
    elements.append(text_note(
        "SW2: RESET -- resets FPGA (PROGRAMN) and RP2040 (RUN)",
        bx - 10, sw2y - 10, 2.0))
    elements.append(button("SW2", "RESET", bx, sw2y,
                            footprint="Button_Switch_SMD:SW_SPST_TL3342"))
    elements.append(net_label("nRESET", bx - 10, sw2y, 180))
    elements.append(wire(bx - 10, sw2y, bx - 5, sw2y))
    elements.append(net_label("GND", bx + 10, sw2y, 0))
    elements.append(wire(bx + 5, sw2y, bx + 10, sw2y))

    # 10K pull-up on nRESET
    elements.append(resistor("R_RST", "10K", bx - 15, sw2y - 8, 90))
    elements.append(net_label("nRESET", bx - 15, sw2y - 3, 0))
    elements.append(net_label("VCC_3V3", bx - 15, sw2y - 13, 0))

    # Connect nRESET to FPGA PROGRAMN and RP2040 RUN
    elements.append(net_label("nRESET", bx + 25, sw2y - 3, 0))
    elements.append(net_label("PROGRAMN", bx + 25, sw2y, 0))
    elements.append(net_label("MCU_RUN", bx + 25, sw2y + 3, 0))
    elements.append(text_note("nRESET -> PROGRAMN + MCU_RUN", bx + 20, sw2y - 8, 1.2))

    # 100nF debounce cap
    elements.append(capacitor("C_RST", "100nF", bx - 8, sw2y - 8, 90))
    elements.append(net_label("nRESET", bx - 8, sw2y - 3, 0))
    elements.append(net_label("GND", bx - 8, sw2y - 13, 0))


def section_leds(elements, bx, by):
    """LED1: Power (green), LED2: FPGA DONE (blue), LED3: Activity (yellow)."""
    elements.append(text_note(
        "Status LEDs",
        bx - 5, by - 20, 2.0))

    # LED1: Power (green, on 3.3V rail)
    elements.append(led("LED1", "GREEN", bx, by,
                         footprint="LED_SMD:LED_0603_1608Metric"))
    elements.append(resistor("R_LED1", "1K", bx - 12, by, 0))
    elements.append(net_label("VCC_3V3", bx - 20, by, 180))
    elements.append(wire(bx - 20, by, bx - 17, by))
    elements.append(wire(bx - 7, by, bx - 5, by))
    elements.append(net_label("GND", bx + 8, by, 0))
    elements.append(wire(bx + 5, by, bx + 8, by))

    # LED2: FPGA DONE (blue, driven by FPGA DONE pin)
    led2y = by + 10
    elements.append(led("LED2", "BLUE", bx, led2y,
                         footprint="LED_SMD:LED_0603_1608Metric"))
    elements.append(resistor("R_LED2", "1K", bx - 12, led2y, 0))
    elements.append(net_label("DONE", bx - 20, led2y, 180))
    elements.append(wire(bx - 20, led2y, bx - 17, led2y))
    elements.append(wire(bx - 7, led2y, bx - 5, led2y))
    elements.append(net_label("GND", bx + 8, led2y, 0))
    elements.append(wire(bx + 5, led2y, bx + 8, led2y))

    # LED3: Activity (yellow, driven by FPGA GPIO)
    led3y = by + 20
    elements.append(led("LED3", "YELLOW", bx, led3y,
                         footprint="LED_SMD:LED_0603_1608Metric"))
    elements.append(resistor("R_LED3", "1K", bx - 12, led3y, 0))
    elements.append(net_label("FPGA_LED_ACT", bx - 20, led3y, 180))
    elements.append(wire(bx - 20, led3y, bx - 17, led3y))
    elements.append(wire(bx - 7, led3y, bx - 5, led3y))
    elements.append(net_label("GND", bx + 8, led3y, 0))
    elements.append(wire(bx + 5, led3y, bx + 8, led3y))


def section_fpga_decoupling(elements, bx, by):
    """FPGA decoupling capacitors -- 100nF per VCC/VCCIO/VCCAUX pair + bulk."""
    elements.append(text_note(
        "FPGA Decoupling -- 100nF x12 (per power pin pair) + 10uF bulk",
        bx - 10, by - 15, 2.0))

    # 12x 100nF for FPGA (8 VCC core + 8 VCCIO + 2 VCCAUX, shared in pairs)
    for i in range(12):
        col = i % 6
        row = i // 6
        cx = bx + col * 10
        cy = by + row * 12
        elements.append(capacitor(f"C_FPGA_{i + 1}", "100nF", cx, cy, 0))
        if i < 6:
            elements.append(net_label("VCC_1V1", cx, cy - 5, 0))
        else:
            elements.append(net_label("VCC_3V3", cx, cy - 5, 0))
        elements.append(net_label("GND", cx, cy + 5, 0))

    # Bulk caps
    elements.append(capacitor("C_FPGA_BULK1", "10uF", bx + 65, by,
                               footprint="Capacitor_SMD:C_0805_2012Metric"))
    elements.append(net_label("VCC_1V1", bx + 65, by - 5, 0))
    elements.append(net_label("GND", bx + 65, by + 5, 0))

    elements.append(capacitor("C_FPGA_BULK2", "10uF", bx + 75, by,
                               footprint="Capacitor_SMD:C_0805_2012Metric"))
    elements.append(net_label("VCC_3V3", bx + 75, by - 5, 0))
    elements.append(net_label("GND", bx + 75, by + 5, 0))


def section_notes(elements, bx, by):
    """Design notes and bus mapping documentation."""
    elements.append(text_note(
        "DESIGN NOTES -- NeoCart FPGA PROG Board rev 2.0", bx, by, 3.0))

    elements.append(text_note(
        "LEVEL SHIFTING STRATEGY:\\n"
        "  - All PROG bus INPUT signals (address, control): 470R series resistor\\n"
        "    between connector and FPGA. FPGA ESD clamp handles 5V->3.3V.\\n"
        "  - PROG bus BIDIRECTIONAL signals (D0-D15): 74LVC245 transceivers.\\n"
        "    A-side = 5V (Neo Geo), B-side = 3.3V (FPGA).\\n"
        "    Direction controlled by FPGA (FPGA_PDATA_DIR).\\n"
        "  - Inter-board signals (CHA bus): already 3.3V from CHA board.\\n"
        "  - Output signals: 3.3V from FPGA is valid TTL high for Neo Geo.\\n",
        bx, by + 10, 1.5))

    elements.append(text_note(
        "POWER DOMAINS:\\n"
        "  VCC_5V:  5V from Neo Geo PROG connector (pins 29-32 both sides)\\n"
        "  VCC_3V3: 3.3V from U9 AMS1117-3.3 (FPGA IO, SDRAM, RP2040)\\n"
        "  VCC_1V1: 1.1V from U10 AMS1117-1.1 (FPGA core)\\n"
        "  VBUS:    5V from USB-C (not used for board power, RP2040 detection only)\\n",
        bx, by + 32, 1.5))

    elements.append(text_note(
        "SDRAM MEMORY MAP:\\n"
        "  0x000000 - 0x1FFFFF   P ROM    (2MB max, 68k program)\\n"
        "  0x200000 - 0x9FFFFF   V ROMs   (8MB max, ADPCM samples)\\n"
        "  0xA00000 - 0x19FFFFF  C ROMs   (16MB max, sprite tiles interleaved)\\n"
        "  0x1A00000- 0x1A1FFFF  S ROM    (128KB, fix layer tiles)\\n"
        "  0x1A20000- 0x1A3FFFF  M ROM    (128KB, Z80 sound program)\\n"
        "  0x1A40000- 0x1FFFFFF  Snoop buffer (ring buffer for bus trace)\\n"
        "  Total: 2x 32MB SDRAM = 64MB, addressed as single linear space\\n"
        "  U2 covers lower 32MB (CS0), U3 covers upper 32MB (CS1)\\n",
        bx, by + 52, 1.5))

    elements.append(text_note(
        "PROG BUS (CTRG2) ACTIVE SIGNALS:\\n"
        "  68k address: A1-A19 (B-side pins 5-22, active during ROMOE)\\n"
        "  68k data: D0-D15 (A-side pins 5-20, BIDIRECTIONAL via 74LVC245)\\n"
        "  R/W (A21), ROMOE (A33), ROMOEU/L (A23-A24)\\n"
        "  V ROM addr: SDRA0-SDRA20, SDPA8-SDPA11\\n"
        "  V ROM data: SDPAD0-SDPAD7 (B-side pins 40-47)\\n"
        "  V ROM OE: SDROE (B56)\\n"
        "  Power: VCC on pins 29-32 (both sides), GND on 1-4 + 59-60\\n",
        bx, by + 78, 1.5))

    elements.append(text_note(
        "INTER-BOARD CONNECTOR (J5, 2x50):\\n"
        "  Pins 1-24:  C ROM address (CA0-CA23)\\n"
        "  Pins 25-56: C ROM data (CR0-CR31)\\n"
        "  Pins 57-72: S ROM address (SA0-SA15)\\n"
        "  Pins 73-80: S ROM data (SD0-SD7)\\n"
        "  Pins 81-83: Control (SDMRD, PCK1B, PCK2B)\\n"
        "  Pins 84-90: Power (VCC_3V3 x3, GND x4)\\n"
        "  Pins 91-100: Spare GPIO (SPARE_GPIO0-9)\\n",
        bx, by + 100, 1.5))


# =============================================================================
# Main schematic assembly
# =============================================================================

def generate_schematic():
    """Generate the complete KiCad 9 schematic for the FPGA PROG board."""
    elements = []

    # ---- Title and overview ----
    elements.append(text_note(
        "NeoCart FPGA PROG Board -- ECP5-25 + 64MB SDRAM + RP2040",
        20, 15, 3.5))
    elements.append(text_note(
        "FPGA-based Neo Geo MVS dev cart (PROG slot) -- all ROMs from SDRAM",
        20, 22, 2.0))

    # ====================================================================
    # Section 1: ECP5 FPGA (center of design, largest symbol)
    # ====================================================================
    section_fpga(elements, 200, 200)

    # ====================================================================
    # Section 2: SDRAM x2
    # ====================================================================
    section_sdram(elements, 420, 120, 1, "U2", "SDRAM_CS0N")
    section_sdram(elements, 420, 280, 2, "U3", "SDRAM_CS1N")

    # ====================================================================
    # Section 3: RP2040
    # ====================================================================
    section_rp2040(elements, 650, 200)

    # ====================================================================
    # Section 4: W25Q32 x2 (RP2040 firmware + FPGA bitstream)
    # ====================================================================
    section_w25q32_rp2040(elements, 800, 120)
    section_w25q32_fpga(elements, 800, 200)

    # ====================================================================
    # Section 5: 74LVC245 x2 (PROG data bus level shifting)
    # ====================================================================
    section_74lvc245(elements, 80, 500, "U7", "D0-D7", 0, 8)
    section_74lvc245(elements, 200, 500, "U8", "D8-D15", 8, 16)

    # ====================================================================
    # Section 6: 470R series resistors (PROG bus input protection)
    # ====================================================================
    section_series_resistors(elements, 80, 620)

    # ====================================================================
    # Section 7: PROG edge connector (J1/J2)
    # ====================================================================
    section_prog_connector(elements, 80, 900)

    # ====================================================================
    # Section 8: USB-C (J3)
    # ====================================================================
    section_usb_c(elements, 800, 320)

    # ====================================================================
    # Section 9: microSD (J4)
    # ====================================================================
    section_sd_card(elements, 800, 420)

    # ====================================================================
    # Section 10: Inter-board connector (J5)
    # ====================================================================
    section_interboard(elements, 500, 550)

    # ====================================================================
    # Section 11: JTAG header (J6)
    # ====================================================================
    section_jtag(elements, 650, 420)

    # ====================================================================
    # Section 12: UART header (J7)
    # ====================================================================
    section_uart(elements, 650, 470)

    # ====================================================================
    # Section 13: Power supply (U9, U10)
    # ====================================================================
    section_power(elements, 500, 420)

    # ====================================================================
    # Section 14: Crystal (Y1)
    # ====================================================================
    section_crystal(elements, 800, 480)

    # ====================================================================
    # Section 15: Buttons (SW1, SW2)
    # ====================================================================
    section_buttons(elements, 650, 520)

    # ====================================================================
    # Section 16: LEDs
    # ====================================================================
    section_leds(elements, 800, 540)

    # ====================================================================
    # Section 17: FPGA decoupling capacitors
    # ====================================================================
    section_fpga_decoupling(elements, 350, 400)

    # ====================================================================
    # Section 18: Design notes
    # ====================================================================
    section_notes(elements, 20, 1100)

    # ====================================================================
    # Assemble final schematic file
    # ====================================================================
    header = section_title_block()
    body = "\n\t".join(elements)
    footer = (
        f'\t(symbol_instances\n'
        f'\t)\n'
        f')\n'
    )

    return f"{header}\t{body}\n\t{footer}"


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_file = os.path.join(out_dir, "neocart_fpga_prog.kicad_sch")

    schematic = generate_schematic()

    with open(out_file, "w") as f:
        f.write(schematic)

    print(f"Generated: {out_file}")
    print()
    print("Component summary:")
    print("  U1:  LFE5U-25F-6BG256I (ECP5-25 FPGA, BGA-256)")
    print("  U2:  W9825G6KH-6 SDRAM #1 (32MB, TSOP-54)")
    print("  U3:  W9825G6KH-6 SDRAM #2 (32MB, TSOP-54)")
    print("  U4:  RP2040 (QFN-56)")
    print("  U5:  W25Q32 -- RP2040 firmware (SOIC-8)")
    print("  U6:  W25Q32 -- FPGA bitstream (SOIC-8)")
    print("  U7:  74LVC245 -- D0-D7 level shift (SOIC-20)")
    print("  U8:  74LVC245 -- D8-D15 level shift (SOIC-20)")
    print("  U9:  AMS1117-3.3 (SOT-223)")
    print("  U10: AMS1117-1.1 (SOT-223)")
    print("  J1:  CTRG2 A-side (60-pin edge)")
    print("  J2:  CTRG2 B-side (60-pin edge)")
    print("  J3:  USB-C receptacle")
    print("  J4:  microSD card slot")
    print("  J5:  Inter-board 2x50 (CHA board)")
    print("  J6:  JTAG 2x3 header")
    print("  J7:  UART 1x3 header")
    print("  Y1:  12MHz crystal")
    print("  SW1: BOOTSEL button")
    print("  SW2: RESET button")
    print("  LED1-3: Power/Done/Activity")
    print(f"  ~63x 470R series resistors (0402)")
    print(f"  ~20x 100nF decoupling caps (0402)")
    print(f"  6x 10uF bulk caps (0805)")
    print(f"  2x 15pF crystal load caps")
    print(f"  2x 27R USB series resistors")
    print(f"  2x 5.1K USB CC resistors")
    print()
    print("Open in KiCad 9 and run ERC to verify net connectivity.")


if __name__ == "__main__":
    main()
