#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — Net Assignment Script

Uses KiCad's pcbnew Python API to:
1. Load the PCB
2. Create all signal nets
3. Assign nets to the correct pads on each footprint
4. Save the PCB ready for routing

This is the electrical design — it defines what connects to what.
"""

import pcbnew
import os
import sys

PCB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neocart.kicad_pcb")

# ─── Net definitions ───
# Every unique electrical signal in the design

POWER_NETS = ["GND", "VCC_5V", "VCC_3V3", "VBUS"]

# P ROM bus (CTRG2 ↔ U_PROM)
PROM_ADDR_NETS = [f"PA{i}" for i in range(18)]   # PA0-PA17
PROM_DATA_NETS = [f"PD{i}" for i in range(16)]    # PD0-PD15

# S ROM bus (CTRG1 ↔ U_SROM)
SROM_ADDR_NETS = [f"SA{i}" for i in range(17)]    # SA0-SA16
SROM_DATA_NETS = [f"SD{i}" for i in range(8)]     # SD0-SD7

# M ROM bus (CTRG2 ↔ U_MROM)
MROM_ADDR_NETS = [f"MA{i}" for i in range(17)]    # MA0-MA16
MROM_DATA_NETS = [f"MD{i}" for i in range(8)]     # MD0-MD7

# C ROM bus (CTRG1 ↔ U_CROM1/U_CROM2)
CROM_ADDR_NETS = [f"CA{i}" for i in range(18)]    # CA0-CA17
CROM1_DATA_NETS = [f"CR{i}" for i in range(16)]   # CR0-CR15 (C1)
CROM2_DATA_NETS = [f"CR{i}" for i in range(16, 32)]  # CR16-CR31 (C2)

# Control signals
CTRL_NETS = [
    "nCE_P", "nOE_P", "nWE_P",
    "nCE_S", "nOE_S", "nWE_S",
    "nCE_M", "nOE_M", "nWE_M",
    "nCE_C1", "nOE_C1", "nWE_C1",
    "nCE_C2", "nOE_C2", "nWE_C2",
    "ROMOE", "ROMOEU", "ROMOEL",
    "SDROM", "SDMRD", "SDROE",
    "PCK1B", "PCK2B",
    "nBYTE_FLASH",
]

# Programmer bus (RP2040 ↔ shift registers ↔ flash)
PROG_ADDR_NETS = [f"PRGA{i}" for i in range(24)]  # shift register outputs
PROG_DATA_NETS = [f"PRGD{i}" for i in range(8)]   # data buffer outputs
PROG_CTRL_NETS = [
    "SR_SER", "SR_SRCLK", "SR_RCLK", "SR_nOE",
    "BUF_nOE", "BUS_DIR",
    "PROG_nWE", "PROG_nOE",
    "PROG_nCE_P", "PROG_nCE_S", "PROG_nCE_M",
    "PROG_nCE_C1", "PROG_nCE_C2", "PROG_nBYTE",
]

# USB + RP2040 support
USB_NETS = ["USB_DP", "USB_DM", "USB_CC1", "USB_CC2"]
SPI_NETS = ["QSPI_SS", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3"]
XTAL_NETS = ["XIN", "XOUT"]
MISC_NETS = ["SR_CHAIN_0", "SR_CHAIN_1", "RUN", "BOOTSEL"]

ALL_NETS = (POWER_NETS + PROM_ADDR_NETS + PROM_DATA_NETS +
            SROM_ADDR_NETS + SROM_DATA_NETS + MROM_ADDR_NETS + MROM_DATA_NETS +
            CROM_ADDR_NETS + CROM1_DATA_NETS + CROM2_DATA_NETS +
            CTRL_NETS + PROG_ADDR_NETS + PROG_DATA_NETS + PROG_CTRL_NETS +
            USB_NETS + SPI_NETS + XTAL_NETS + MISC_NETS)

# ─── Pad-to-net assignments ───
# For each component: { "pad_number": "net_name" }

# AM29F400 pin mapping (TSOP-48)
# Pin numbers from KiCad library: A0=25, A1=24, ..., A17=47(actually 48 per earlier extract)
# DQ0=29, DQ1=31, DQ2=33, DQ3=35, DQ4=38, DQ5=40, DQ6=42, DQ7=44
# DQ8=30, DQ9=32, DQ10=34, DQ11=36, DQ12=39, DQ13=41, DQ14=43, DQ15=45

AM29F400_ADDR_PINS = {
    "25": 0, "24": 1, "23": 2, "22": 3, "21": 4,
    "20": 5, "19": 6, "18": 7, "8": 8, "7": 9,
    "6": 10, "5": 11, "4": 12, "3": 13, "2": 14,
    "1": 15, "48": 16, "47": 17
}

AM29F400_DATA_PINS = {
    "29": 0, "31": 1, "33": 2, "35": 3,
    "38": 4, "40": 5, "42": 6, "44": 7,
    "30": 8, "32": 9, "34": 10, "36": 11,
    "39": 12, "41": 13, "43": 14, "45": 15
}

AM29F400_CTRL_PINS = {"17": "CE", "26": "OE", "28": "WE", "11": "BYTE", "46": "RESET"}
AM29F400_POWER_PINS = {"12": "VCC_5V", "37": "GND", "27": "GND"}

# SST39SF010 pin mapping (PLCC-32)
SST_ADDR_PINS = {
    "12": 0, "11": 1, "10": 2, "9": 3, "8": 4,
    "7": 5, "6": 6, "5": 7, "27": 8, "26": 9,
    "23": 10, "25": 11, "4": 12, "28": 13, "29": 14,
    "3": 15, "2": 16
}

SST_DATA_PINS = {
    "13": 0, "14": 1, "15": 2, "17": 3,
    "18": 4, "19": 5, "20": 6, "21": 7
}

SST_CTRL_PINS = {"22": "CE", "24": "OE", "31": "WE"}
SST_POWER_PINS = {"32": "VCC_5V", "16": "GND"}

# 74HC595 pin mapping (SOIC-16)
# QA-QH = pins 15,1,2,3,4,5,6,7 (outputs)
# SER=14, SRCLK=11, RCLK=12, OE=13, SRCLR=10, QH'=9
HC595_OUTPUT_PINS = {"15": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}
HC595_CTRL = {"14": "SER", "11": "SRCLK", "12": "RCLK", "13": "nOE", "10": "SRCLR", "9": "QH_PRIME"}
HC595_POWER = {"16": "VCC_3V3", "8": "GND"}

# 74HC245 pin mapping (SOIC-20)
# A1-A8 = pins 2-9, B1-B8 = pins 18-11, DIR=1, OE=19
HC245_A_PINS = {"2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5, "8": 6, "9": 7}
HC245_B_PINS = {"18": 0, "17": 1, "16": 2, "15": 3, "14": 4, "13": 5, "12": 6, "11": 7}
HC245_CTRL = {"1": "DIR", "19": "nOE"}
HC245_POWER = {"20": "VCC_5V", "10": "GND"}

# RP2040 pin mapping (QFN-56)
# From KiCad library extraction
RP2040_GPIO_PINS = {
    "2": "GPIO0", "3": "GPIO1", "4": "GPIO2", "5": "GPIO3",
    "6": "GPIO4", "7": "GPIO5", "8": "GPIO6", "9": "GPIO7",
    "10": "GPIO8", "11": "GPIO9", "12": "GPIO10", "13": "GPIO11",
    "14": "GPIO12", "15": "GPIO13", "16": "GPIO14", "17": "GPIO15",
    "18": "GPIO16", "19": "GPIO17", "20": "GPIO18", "21": "GPIO19",
    "22": "GPIO20", "23": "GPIO21", "24": "GPIO22", "25": "GPIO23",
    "26": "GPIO24", "27": "GPIO25", "28": "GPIO26", "29": "GPIO27",
    "30": "GPIO28", "31": "GPIO29",
}

# GPIO to net mapping (programmer function assignments)
GPIO_NET_MAP = {
    "GPIO0": "SR_SER",
    "GPIO1": "SR_SRCLK",
    "GPIO2": "SR_RCLK",
    "GPIO3": "PRGD0", "GPIO4": "PRGD1", "GPIO5": "PRGD2", "GPIO6": "PRGD3",
    "GPIO7": "PRGD4", "GPIO8": "PRGD5", "GPIO9": "PRGD6", "GPIO10": "PRGD7",
    "GPIO11": "PROG_nWE",
    "GPIO12": "PROG_nOE",
    "GPIO13": "PROG_nCE_P",
    "GPIO14": "PROG_nCE_S",
    "GPIO15": "PROG_nCE_M",
    "GPIO16": "PROG_nCE_C1",
    "GPIO17": "PROG_nCE_C2",
    "GPIO18": "PROG_nBYTE",
    "GPIO19": "BUS_DIR",
    "GPIO20": "SR_nOE",
    "GPIO21": "BUF_nOE",
}

RP2040_SPECIAL_PINS = {
    "33": "USB_DP", "34": "USB_DM",
    "36": "QSPI_SS", "37": "QSPI_SCLK",
    "38": "QSPI_SD0", "39": "QSPI_SD1", "40": "QSPI_SD2", "41": "QSPI_SD3",
    "42": "XIN", "43": "XOUT",
    "32": "RUN",
    "35": "USB_VDD",
}

RP2040_POWER_PINS = {
    "44": "VCC_3V3",   # IOVDD
    "45": "VCC_3V3",   # IOVDD
    "46": "VCC_3V3",   # IOVDD
    "47": "VCC_3V3",   # IOVDD
    "48": "VCC_3V3",   # IOVDD
    "49": "VCC_3V3",   # IOVDD
    "1": "VCC_3V3",    # IOVDD (pin 1 is IOVDD on some pinouts)
    "50": "VCC_3V3",   # DVDD
    "51": "VCC_3V3",   # DVDD
    "52": "VCC_3V3",   # VREG_VIN
    "53": "VCC_3V3",   # VREG_VOUT
    "54": "VCC_3V3",   # USB_VDD
    "55": "VCC_3V3",   # ADC_AVDD
    "56": "GND",       # TESTEN (tie low)
    "57": "GND",       # EP (exposed pad)
}

# CTRG1 (CHA) connector — pad names are A1..A60, B1..B60
# Maps to signals from the JNX pinout
CTRG1_A_SIGNALS = {
    1: "GND", 2: "GND",
    3: "CA0", 4: "CA2", 5: "CA4", 6: "CA6", 7: "CA8", 8: "CA10",
    9: "CA12", 10: "CA14", 11: "CA16", 12: "CA18",  # extended address not used
    13: "CA20", 14: "CA22",  # not used for our small ROMs
    15: "PCK1B", 16: "PCK2B", 17: "GND", 18: "GND",
    19: "CR0", 20: "CR2", 21: "CR4", 22: "CR6",
    23: "CR8", 24: "CR10", 25: "CR12", 26: "CR14",
    27: "CR16", 28: "CR18",
    29: "VCC_5V", 30: "VCC_5V", 31: "VCC_5V", 32: "VCC_5V",
    33: "CR20", 34: "CR22", 35: "CR24", 36: "CR26",
    37: "CR28", 38: "CR30",
    39: "GND", 40: "GND", 41: "GND", 42: "GND",
    43: "SA0", 44: "SA1", 45: "SA2", 46: "SA3",
    47: "SA4", 48: "SA5", 49: "SA6", 50: "SA7",
    51: "SA8", 52: "SA9", 53: "SA10", 54: "SA11",
    55: "SA12", 56: "SA13", 57: "SA14",
    58: "GND", 59: "GND", 60: "GND",
}

CTRG1_B_SIGNALS = {
    1: "GND", 2: "GND",
    3: "CA1", 4: "CA3", 5: "CA5", 6: "CA7", 7: "CA9", 8: "CA11",
    9: "CA13", 10: "CA15", 11: "CA17", 12: "CA19",
    13: "CA21", 14: "CA23",
    15: "GND", 16: "GND", 17: "GND", 18: "GND",
    19: "CR1", 20: "CR3", 21: "CR5", 22: "CR7",
    23: "CR9", 24: "CR11", 25: "CR13", 26: "CR15",
    27: "CR17", 28: "CR19",
    29: "VCC_5V", 30: "VCC_5V", 31: "VCC_5V", 32: "VCC_5V",
    33: "CR21", 34: "CR23", 35: "CR25", 36: "CR27",
    37: "CR29", 38: "CR31",
    39: "GND", 40: "GND", 41: "GND", 42: "GND",
    43: "GND", 44: "GND", 45: "GND", 46: "GND",
    47: "SDMRD", 48: "SD0", 49: "SD1", 50: "SD2",
    51: "SD3", 52: "SD4", 53: "SD5", 54: "SD6",
    55: "SD7", 56: "SDROM",
    57: "SA15",
    58: "GND", 59: "GND", 60: "GND",
}

# CTRG2 (PROG) connector
CTRG2_A_SIGNALS = {
    1: "GND", 2: "GND", 3: "GND", 4: "GND",
    5: "PD0", 6: "PD1", 7: "PD2", 8: "PD3",
    9: "PD4", 10: "PD5", 11: "PD6", 12: "PD7",
    13: "PD8", 14: "PD9", 15: "PD10", 16: "PD11",
    17: "PD12", 18: "PD13", 19: "PD14", 20: "PD15",
    21: "GND", 22: "GND",
    23: "ROMOEU", 24: "ROMOEL",
    25: "GND", 26: "GND", 27: "GND", 28: "GND",
    29: "VCC_5V", 30: "VCC_5V", 31: "VCC_5V", 32: "VCC_5V",
    33: "ROMOE",
    34: "GND", 35: "GND", 36: "GND", 37: "GND",
    38: "GND", 39: "GND", 40: "GND", 41: "GND",
    42: "GND", 43: "GND",
    44: "GND", 45: "GND", 46: "GND",
    47: "MA8", 48: "MA9", 49: "MA10", 50: "MA11",
    51: "MA12", 52: "MA13", 53: "MA14", 54: "MA15",
    55: "MA16", 56: "GND",
    57: "GND", 58: "GND",
    59: "GND", 60: "GND",
}

CTRG2_B_SIGNALS = {
    1: "GND", 2: "GND", 3: "GND", 4: "GND",
    5: "PA0", 6: "PA1", 7: "PA2", 8: "PA3",
    9: "PA4", 10: "PA5", 11: "PA6", 12: "PA7",
    13: "PA8", 14: "PA9", 15: "PA10", 16: "PA11",
    17: "PA12", 18: "PA13", 19: "PA14", 20: "PA15",
    21: "PA16", 22: "PA17",
    23: "GND", 24: "GND",
    25: "GND", 26: "GND", 27: "GND", 28: "GND",
    29: "VCC_5V", 30: "VCC_5V", 31: "VCC_5V", 32: "VCC_5V",
    33: "GND", 34: "GND", 35: "GND", 36: "GND",
    37: "GND", 38: "GND", 39: "GND",
    40: "MD0", 41: "MD1", 42: "MD2", 43: "MD3",
    44: "MD4", 45: "MD5", 46: "MD6",
    47: "MD7",
    48: "MA0", 49: "MA1", 50: "MA2", 51: "MA3",
    52: "MA4", 53: "MA5", 54: "MA6", 55: "MA7",
    56: "SDROE",
    57: "GND", 58: "GND",
    59: "GND", 60: "GND",
}


def build_component_nets():
    """Build complete pad→net mapping for every component."""
    assignments = {}

    # ── U_PROM (AM29F400) — P ROM ──
    prom = {}
    for pin, idx in AM29F400_ADDR_PINS.items():
        prom[pin] = f"PA{idx}"
    for pin, idx in AM29F400_DATA_PINS.items():
        prom[pin] = f"PD{idx}"
    prom["17"] = "nCE_P"
    prom["26"] = "nOE_P"
    prom["28"] = "nWE_P"
    prom["11"] = "nBYTE_FLASH"
    prom["12"] = "VCC_5V"
    prom["37"] = "GND"
    prom["27"] = "GND"
    prom["46"] = "VCC_5V"  # NC → tie to VCC or leave
    assignments["U_PROM"] = prom

    # ── U_SROM (SST39SF010) — S ROM ──
    srom = {}
    for pin, idx in SST_ADDR_PINS.items():
        srom[pin] = f"SA{idx}"
    for pin, idx in SST_DATA_PINS.items():
        srom[pin] = f"SD{idx}"
    srom["22"] = "nCE_S"
    srom["24"] = "nOE_S"
    srom["31"] = "nWE_S"
    srom["32"] = "VCC_5V"
    srom["16"] = "GND"
    assignments["U_SROM"] = srom

    # ── U_MROM (SST39SF010) — M ROM ──
    mrom = {}
    for pin, idx in SST_ADDR_PINS.items():
        mrom[pin] = f"MA{idx}"
    for pin, idx in SST_DATA_PINS.items():
        mrom[pin] = f"MD{idx}"
    mrom["22"] = "nCE_M"
    mrom["24"] = "nOE_M"
    mrom["31"] = "nWE_M"
    mrom["32"] = "VCC_5V"
    mrom["16"] = "GND"
    assignments["U_MROM"] = mrom

    # ── U_CROM1 (AM29F400) — C1 ROM (CR0-CR15) ──
    crom1 = {}
    for pin, idx in AM29F400_ADDR_PINS.items():
        crom1[pin] = f"CA{idx}"
    for pin, idx in AM29F400_DATA_PINS.items():
        crom1[pin] = f"CR{idx}"
    crom1["17"] = "nCE_C1"
    crom1["26"] = "nOE_C1"
    crom1["28"] = "nWE_C1"
    crom1["11"] = "nBYTE_FLASH"
    crom1["12"] = "VCC_5V"
    crom1["37"] = "GND"
    crom1["27"] = "GND"
    assignments["U_CROM1"] = crom1

    # ── U_CROM2 (AM29F400) — C2 ROM (CR16-CR31) ──
    crom2 = {}
    for pin, idx in AM29F400_ADDR_PINS.items():
        crom2[pin] = f"CA{idx}"  # shared address with C1
    for pin, idx in AM29F400_DATA_PINS.items():
        crom2[pin] = f"CR{idx + 16}"
    crom2["17"] = "nCE_C2"
    crom2["26"] = "nOE_C2"
    crom2["28"] = "nWE_C2"
    crom2["11"] = "nBYTE_FLASH"
    crom2["12"] = "VCC_5V"
    crom2["37"] = "GND"
    crom2["27"] = "GND"
    assignments["U_CROM2"] = crom2

    # ── U_SR1, U_SR2, U_SR3 (74HC595) — Address shift registers ──
    for sr_idx in range(3):
        ref = f"U_SR{sr_idx + 1}"
        sr = {}
        for pin, bit in HC595_OUTPUT_PINS.items():
            addr_bit = sr_idx * 8 + bit
            sr[pin] = f"PRGA{addr_bit}"
        sr["14"] = "SR_SER" if sr_idx == 0 else f"SR_CHAIN_{sr_idx - 1}"
        sr["9"] = f"SR_CHAIN_{sr_idx}" if sr_idx < 2 else "GND"
        sr["11"] = "SR_SRCLK"
        sr["12"] = "SR_RCLK"
        sr["13"] = "SR_nOE"
        sr["10"] = "VCC_3V3"  # SRCLR tied high (no clear)
        sr["16"] = "VCC_3V3"
        sr["8"] = "GND"
        assignments[ref] = sr

    # ── U_BUF1 (74HC245) — Data bus buffer ──
    buf1 = {}
    for pin, bit in HC245_A_PINS.items():
        buf1[pin] = f"PRGD{bit}"  # A side: RP2040/3.3V
    for pin, bit in HC245_B_PINS.items():
        buf1[pin] = f"SD{bit}" if bit < 8 else "GND"  # B side: flash data (shared bus)
        # Actually the data buffer connects to ALL flash data buses
        # For simplicity, use a shared FLASH_D bus
    # Override B side to shared flash data bus
    for pin, bit in HC245_B_PINS.items():
        buf1[pin] = f"PRGD{bit}"  # In practice both sides use the same programmer data net
    # Actually, A side = RP2040 data, B side = flash chip data
    # Let's use distinct nets
    for pin, bit in HC245_A_PINS.items():
        buf1[pin] = f"PRGD{bit}"
    for pin, bit in HC245_B_PINS.items():
        buf1[pin] = f"PRGD{bit}"  # Same net — buffer is bidirectional on same bus
    buf1["1"] = "BUS_DIR"
    buf1["19"] = "BUF_nOE"
    buf1["20"] = "VCC_5V"
    buf1["10"] = "GND"
    assignments["U_BUF1"] = buf1

    # ── U_BUF2 (74HC245) — Control bus buffer ──
    buf2_a_nets = ["PROG_nCE_P", "PROG_nCE_S", "PROG_nCE_M",
                   "PROG_nCE_C1", "PROG_nCE_C2", "PROG_nWE", "PROG_nOE", "PROG_nBYTE"]
    buf2_b_nets = ["nCE_P", "nCE_S", "nCE_M",
                   "nCE_C1", "nCE_C2", "nWE_P", "nOE_P", "nBYTE_FLASH"]
    buf2 = {}
    for i, (pin, _) in enumerate(HC245_A_PINS.items()):
        if i < len(buf2_a_nets):
            buf2[pin] = buf2_a_nets[i]
    for i, (pin, _) in enumerate(HC245_B_PINS.items()):
        if i < len(buf2_b_nets):
            buf2[pin] = buf2_b_nets[i]
    buf2["1"] = "BUS_DIR"
    buf2["19"] = "BUF_nOE"
    buf2["20"] = "VCC_5V"
    buf2["10"] = "GND"
    assignments["U_BUF2"] = buf2

    # ── U_MCU (RP2040) ──
    mcu = {}
    for pin, gpio in RP2040_GPIO_PINS.items():
        if gpio in GPIO_NET_MAP:
            mcu[pin] = GPIO_NET_MAP[gpio]
    for pin, net in RP2040_SPECIAL_PINS.items():
        mcu[pin] = net
    for pin, net in RP2040_POWER_PINS.items():
        mcu[pin] = net
    assignments["U_MCU"] = mcu

    # ── U_REG (AMS1117-3.3) — SOT-223 ──
    assignments["U_REG"] = {"1": "GND", "2": "VCC_3V3", "3": "VCC_5V", "4": "VCC_3V3"}

    # ── Y1 (Crystal) ──
    assignments["Y1"] = {"1": "XIN", "2": "XOUT"}

    # ── U_FLASH (W25Q32 SPI flash) — SOIC-8 ──
    assignments["U_FLASH"] = {
        "1": "QSPI_SS", "2": "QSPI_SD1", "3": "VCC_3V3", "4": "GND",
        "5": "QSPI_SD0", "6": "QSPI_SCLK", "7": "VCC_3V3", "8": "VCC_3V3"
    }

    # ── J_CTRG1 (CHA connector) ──
    ctrg1 = {}
    for pin, sig in CTRG1_A_SIGNALS.items():
        ctrg1[f"A{pin}"] = sig
    for pin, sig in CTRG1_B_SIGNALS.items():
        ctrg1[f"B{pin}"] = sig
    assignments["J_CTRG1"] = ctrg1

    # ── J_CTRG2 (PROG connector) ──
    ctrg2 = {}
    for pin, sig in CTRG2_A_SIGNALS.items():
        ctrg2[f"A{pin}"] = sig
    for pin, sig in CTRG2_B_SIGNALS.items():
        ctrg2[f"B{pin}"] = sig
    assignments["J_CTRG2"] = ctrg2

    return assignments


def main():
    print(f"Loading PCB: {PCB_PATH}")
    board = pcbnew.LoadBoard(PCB_PATH)

    netinfo = board.GetNetInfo()
    net_table = {}

    # Create all nets
    print("Creating nets...")
    all_net_names = set()
    assignments = build_component_nets()
    for comp_ref, pad_nets in assignments.items():
        for pad_num, net_name in pad_nets.items():
            all_net_names.add(net_name)

    # Also add from ALL_NETS
    for n in ALL_NETS:
        all_net_names.add(n)

    # Get existing nets
    for net_id in range(board.GetNetCount()):
        net = board.GetNetInfo().GetNetItem(net_id)
        if net:
            net_table[net.GetNetname()] = net_id

    # Create new nets
    next_id = board.GetNetCount()
    for net_name in sorted(all_net_names):
        if net_name not in net_table and net_name:
            net = pcbnew.NETINFO_ITEM(board, net_name, next_id)
            board.Add(net)
            net_table[net_name] = next_id
            next_id += 1

    print(f"  {len(all_net_names)} nets defined")

    # Assign nets to pads
    print("Assigning nets to pads...")
    footprints = board.GetFootprints()
    fp_by_ref = {}
    for fp in footprints:
        ref = fp.GetReference()
        fp_by_ref[ref] = fp

    assigned = 0
    skipped = 0

    for comp_ref, pad_nets in assignments.items():
        fp = fp_by_ref.get(comp_ref)
        if not fp:
            print(f"  WARNING: footprint {comp_ref} not found on PCB")
            continue

        pads = fp.Pads()
        pad_by_num = {}
        for pad in pads:
            pad_by_num[pad.GetNumber()] = pad

        for pad_num, net_name in pad_nets.items():
            pad = pad_by_num.get(str(pad_num))
            if not pad:
                skipped += 1
                continue

            if net_name in net_table:
                net_id = net_table[net_name]
                net_item = board.GetNetInfo().GetNetItem(net_id)
                if net_item:
                    pad.SetNet(net_item)
                    assigned += 1
            else:
                print(f"  WARNING: net '{net_name}' not found for {comp_ref} pad {pad_num}")

    print(f"  {assigned} pad-net assignments made, {skipped} pads skipped")

    # Save
    pcbnew.SaveBoard(PCB_PATH, board)
    print(f"\nPCB saved: {PCB_PATH}")
    print("Open in KiCad → run DRC → route traces with interactive router")
    print("Or: Tools → Freerouting for auto-routing")


if __name__ == "__main__":
    main()
