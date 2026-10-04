# NeoCart FPGA — Design Specification

## Overview
Single FPGA-based Neo Geo MVS dev cart. Replaces all ROM chips with
FPGA + SDRAM. Loads games from SD card or USB. Supports bus snooping
for live debugging.

## Architecture

```
┌─── PROG BOARD (main board) ──────────────────────────┐
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  ECP5    │──│  SDRAM   │  │  RP2040  │──USB-C    │
│  │  FPGA    │  │  32MB    │  │          │──SD Card  │
│  │          │  └──────────┘  └────┬─────┘           │
│  │          │◄════ SPI 40MHz ════►│                  │
│  │          │                                        │
│  │  P ROM   │  serves 68k bus (A1-A19, D0-D15)      │
│  │  V ROM   │  serves YM2610 (V1-V4 audio samples)  │
│  │  snooper │  captures all bus transactions         │
│  │          │                                        │
│  │          │◄══ FFC 50-pin ═══════════════╗        │
│  └────┬─────┘                               ║        │
│       │                                     ║        │
│  ═════╧═════════════════════════            ║        │
│     CTRG2 gold fingers (PROG)              ║        │
└──────────────────────────────────────────────╫────────┘
                                               ║
┌─── CHA BOARD (passive breakout) ─────────────╫────────┐
│                                               ║        │
│  FFC connector ◄══════════════════════════════╝        │
│  routes CHA signals to FPGA:                           │
│    C ROM addr (P0-P23), data (CR0-CR31)                │
│    S ROM addr (SDA0-15), data (SDD0-7)                 │
│    M ROM addr/data (Z80 bus)                           │
│    Clocks (PCK1B, PCK2B, 24M, 12M, 8M)                │
│                                                        │
│  ══════════════════════════════════════════            │
│     CTRG1 gold fingers (CHA)                          │
└────────────────────────────────────────────────────────┘
```

## FPGA Internal Architecture (Verilog)

```
                    FPGA
  ┌─────────────────────────────────────────┐
  │                                         │
  │  ┌───────────┐     ┌───────────────┐   │
  │  │ PROG bus  │     │ SDRAM         │   │
  │  │ interface │────→│ controller    │   │
  │  │ (68k+V)  │     │               │   │
  │  └───────────┘     │ 4 ports:      │   │
  │                     │  - PROG read  │   │
  │  ┌───────────┐     │  - CHA read   │   │
  │  │ CHA bus   │────→│  - snoop write│   │
  │  │ interface │     │  - SPI load   │   │
  │  │ (C/S/M)  │     └───────────────┘   │
  │  └───────────┘                         │
  │                     ┌───────────────┐   │
  │  ┌───────────┐     │ bus snooper   │   │
  │  │ SPI slave │     │ FIFO → RP2040 │   │
  │  │ (RP2040)  │     └───────────────┘   │
  │  └───────────┘                         │
  └─────────────────────────────────────────┘
```

## Pin Budget (ECP5-25 BGA-256, 197 IOs)

### PROG bus (CTRG2) — directly on PROG board
  - A1-A19:     19 pins  (68k address)
  - D0-D15:     16 pins  (68k data, directly accessible by 68k bidirectional)
  - ROMOE:       1 pin   (P ROM output enable)
  - ROMOEU/L:    2 pins  (byte enables)
  - R/W:         1 pin   (read/write)
  - SDPA/SDRA:  21 pins  (V ROM / Z80 sound address)
  - SDPAD:       8 pins  (V ROM / sound data)
  - SDROE:       1 pin   (V ROM output enable)
  - Subtotal:   69 pins

### CHA bus (CTRG1) — via FFC cable
  - P0-P23:     24 pins  (C ROM address from LSPC)
  - CR0-CR31:   32 pins  (C ROM data)
  - SDA0-SDA15: 16 pins  (S ROM address)
  - SDD0-SDD7:   8 pins  (S ROM data)
  - SDMRD:       1 pin   (S ROM read)
  - PCK1B/2B:    2 pins  (pixel clocks)
  - Subtotal:   83 pins

### SDRAM interface
  - A0-A12:     13 pins  (SDRAM address)
  - DQ0-DQ15:   16 pins  (SDRAM data)
  - BA0-BA1:     2 pins  (bank select)
  - CAS/RAS/WE:  3 pins  (control)
  - CKE/CS/CLK:  3 pins
  - DQM0-1:      2 pins  (byte masks)
  - Subtotal:   39 pins

### RP2040 interface
  - SPI (MOSI/MISO/SCK/CS): 4 pins
  - IRQ:         1 pin   (snoop data ready)
  - FPGA_DONE:   1 pin   (config status)
  - Subtotal:    6 pins

### Total: 197 pins — fits ECP5-25 BGA-256 exactly

## SDRAM Memory Map

```
0x000000 - 0x1FFFFF   P ROM    (2MB max)
0x200000 - 0x9FFFFF   V ROMs   (8MB max, V1+V2+V3+V4)
0xA00000 - 0x19FFFFF  C ROMs   (16MB max, C1-C8 interleaved)
0x1A00000- 0x1A1FFFF  S ROM    (128KB)
0x1A20000- 0x1A3FFFF  M ROM    (128KB)
0x1A40000- 0x1FFFFFF  Snoop buffer (ring buffer for bus trace)
```

Total: 32MB SDRAM covers everything up to KOF-class games.

## Verilog Module Hierarchy

```
neocart_top.v
├── prog_bus.v          — CTRG2 bus interface (68k + V ROM)
├── cha_bus.v           — CTRG1 bus interface (C/S/M ROM)
├── sdram_ctrl.v        — multi-port SDRAM controller
├── spi_slave.v         — SPI interface to RP2040
├── bus_snooper.v       — captures bus transactions to FIFO
└── clk_pll.v           — PLL: 12MHz input → 100MHz SDRAM clock
```

## Bill of Materials (estimated)

| Ref    | Part              | Package  | ~Cost | Notes                    |
|--------|-------------------|----------|-------|--------------------------|
| U_FPGA | LFE5U-25F-6BG256C | BGA-256  | $8    | Lattice ECP5-25          |
| U_SDRAM| IS42S16320D-7TL   | TSOP-54  | $3    | 32MB SDRAM               |
| U_MCU  | RP2040            | QFN-56   | $0.70 | USB + SD + SPI master    |
| U_FLASH| W25Q32            | SOIC-8   | $0.50 | RP2040 firmware          |
| U_CFG  | W25Q32            | SOIC-8   | $0.50 | FPGA bitstream storage   |
| J_USB  | USB-C receptacle  | SMD      | $0.30 | Programming/debug        |
| J_SD   | microSD slot      | SMD      | $0.50 | Game storage             |
| J_FFC  | 50-pin FFC conn   | SMD      | $0.30 | Board-to-board link      |
| U_REG  | AMS1117-3.3       | SOT-223  | $0.10 | 3.3V for FPGA+SDRAM     |
| U_REG2 | AMS1117-1.1       | SOT-223  | $0.10 | 1.1V for FPGA core      |
| Y1     | 12MHz crystal     | 3215     | $0.15 | → PLL → 100MHz SDRAM    |
| misc   | caps, resistors   | 0402     | $2    | Decoupling, pull-ups     |
|        |                   |          |       |                          |
| **Total per PROG board** |  |        | **~$16** |                      |
| **CHA board (passive)**  |  |        | **~$5**  | PCB + FFC connector  |
