# NeoCart FPGA — Complete Build Plan

## The Goal
A custom MVS PROG board that plugs into a Neo Geo MVS motherboard.
An FPGA reads ROM requests from the 68k bus and serves data from SDRAM.
ROMs are loaded via USB from a PC.
Pair with existing donor CHA board for sprites/sound.

## What the board does
1. Neo Geo puts an address on the bus
2. FPGA reads the address through series resistors (5V→3.3V)
3. FPGA looks up the data in SDRAM
4. FPGA sends data back through 74LVC245 level shifters (3.3V→5V)
5. Neo Geo reads the data

## Components (19 types, ~77 parts total)

| Ref | Part | Package | Pins | Function |
|-----|------|---------|------|----------|
| U1 | ECP5-25F | TQFP-144 | 144 | FPGA — the brain |
| U2 | W9825G6KH | TSOP-54 | 54 | SDRAM #1 (32MB) |
| U3 | W9825G6KH | TSOP-54 | 54 | SDRAM #2 (32MB) |
| U4 | 74LVC245 | SOIC-20 | 20 | Level shifter D0-D7 |
| U5 | 74LVC245 | SOIC-20 | 20 | Level shifter D8-D15 |
| U6 | RP2040 | QFN-56 | 56 | MCU — USB + SPI master |
| U7 | W25Q32 | SOIC-8 | 8 | RP2040 firmware flash |
| U8 | W25Q32 | SOIC-8 | 8 | FPGA config flash |
| U9 | AMS1117-3.3 | SOT-223 | 4 | 5V→3.3V regulator |
| U10 | AMS1117-1.1 | SOT-223 | 4 | 3.3V→1.1V regulator |
| J1 | USB-C | SMD-16 | 16 | PC connection |
| J2 | JTAG | 2x3 header | 6 | FPGA debug |
| Y1 | 12MHz | SMD 3215 | 2 | RP2040 clock |
| LED1-2 | LED | 0805 | 2 each | Status |
| SW1-2 | Button | SMD | 2 each | BOOTSEL + RESET |
| RA0-RA17 | 470Ω | 0402 | 2 each | Address bus protection |
| RC0-RC3 | 470Ω | 0402 | 2 each | Control signal protection |
| RL1-2 | 1KΩ | 0402 | 2 each | LED current limit |
| C1-C16 | 100nF | 0402 | 2 each | Decoupling |
| CB0-2 | 10µF | 0805 | 2 each | Bulk decoupling |
| CX1-2 | 15pF | 0402 | 2 each | Crystal load |
| CTRG2 | MVS connector | Gold fingers | 120 (60×2) | MVS slot |

**Total pads: ~760**
**Every pad must have a net. Zero orphans.**

## Execution Steps

### Step 1: Circuit Definition (pin-by-pin)
For each component, list every pin and what net it connects to.
Sources:
- FPGA: prjtrellis database (verified)
- SDRAM: W9825G6KH datasheet Rev A04 page 4 (verified)
- 74LVC245: standard pinout (verified)
- RP2040: RP2040 datasheet
- CTRG2: JNX pinout + neogeo-diag project (verified)
- All others: standard datasheets

Gate: total assigned pads == total pads. Zero orphans.

### Step 2: Netlist Validation
- Every net has 2+ pads
- No pin on two nets
- Every IC power pin → power net
- Every IC ground pin → GND
- Signal direction makes sense

Gate: automated validation passes.

### Step 3: Component Placement
- Board: 174mm × 134mm (proven MVS outline)
- SDRAM top, FPGA center, level shifters bottom, RP2040 left, power right
- No overlaps
- Decoupling caps touching their IC

Gate: zero overlaps confirmed programmatically.

### Step 4: Routing
- Route all signal nets
- Before placing each trace segment: check cell is free on that layer
- After routing: scan entire grid for shorts

Gate: zero shorts. All nets routed.

### Step 5: DRC
- Clearance check
- Connectivity check
- Board edge check

Gate: zero violations.

### Step 6: Export + Render
- Gerbers
- BOM
- PNG render
- Host on LAN

Gate: files generated, image looks correct.
