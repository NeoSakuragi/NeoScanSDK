> **Superseded 2026-09-23.** This ECP5-25F custom-board plan is shelved; the cart is now built around the QMTech XC7A100T core board with NOR flash on the bus. See `README.md` in this folder. Kept for the RTL, BOM research and connector footprints.

# NeoCart FPGA Dev Cart — Complete Handoff Package

## What is this?
An FPGA-based Neo Geo MVS dev cart that plugs into an MVS motherboard
and serves ROM data from SDRAM, loaded via USB. Supports bus snooping
for live debugging.

## What's DONE and verified

### 1. Architecture ✅
- ECP5-25F FPGA (TQFP-144, 98 user IOs)
- 4x W9825G6KH-6 SDRAM = 128MB (covers entire Neo Geo library)
- RP2040 MCU for USB + SPI data loading
- 2x 74LVC245 level shifters (5V Neo Geo ↔ 3.3V FPGA)
- Dual LDO power (3.3V + 1.1V)
- USB-C for programming
- JTAG for FPGA debug
- Phase 1: PROG board only (pair with donor CHA board)

### 2. Board outline ✅ (VERIFIED — from manufactured board)
Cloned from github.com/jwestfall69/neogeo-diag-mvs-prog
- 174mm × 134mm, 4-layer
- Gold fingers: 60 pins, 2.54mm pitch, 1.5mm × 10mm pads
- Alignment notches, mounting holes — exact match to MVS slot
- Edge connector footprints included in project

### 3. Verilog RTL ✅ (6 modules, synthesizable)
Location: `fpga/rtl/`
- `neocart_top.v` — top-level
- `prog_bus.v` — P ROM + V ROM serving
- `cha_bus.v` — C/S/M ROM serving (for Phase 2 CHA board)
- `sdram_ctrl.v` — multi-port SDRAM controller
- `spi_slave.v` — SPI interface from RP2040
- `bus_snooper.v` — 68k bus transaction capture
- `clk_pll.v` — 12MHz → 100MHz PLL

### 4. BOM ✅ (all LCSC part numbers verified in stock)
| Ref | Part | LCSC | Price |
|-----|------|------|-------|
| U1 | LFE5U-25F-6TG144C | C2682019 | ~$12 |
| U2-U5 | W9825G6KH-6 (×4) | C62246 | $4.64 ea |
| U6 | RP2040 | C2040 | $0.69 |
| U7-U8 | W25Q32JVSSIQ (×2) | C571986 | $0.50 ea |
| U9-U10 | 74LVC245AD (×2) | C5949 | $0.15 ea |
| U11 | AMS1117-3.3 | C6186 | $0.10 |
| U12 | AMS1117-1.1 | C6187 | $0.10 |
| J1 | USB-C GCT USB4085 | C168688 | $0.30 |
| Y1 | 12MHz crystal | C9002 | $0.15 |
| - | Passives (caps/res) | various | ~$2 |
| **Total** | | | **~$35** |

### 5. Proven connector pinout ✅ (from manufactured boards)
CTRG2 PROG connector: `footprints/neogeo-diag.pretty/`
- `neogeo-mvs-prog-a-side-edge.kicad_mod` (60 pads, A-side)
- `neogeo-mvs-prog-b-side-edge.kicad_mod` (60 pads, B-side)

### 6. KiCad project files (component placement done)
- `fpga/neocart_tqfp_prog.kicad_pcb` — PCB with all components placed
- `fpga/neocart_fpga_prog.kicad_sch` — schematic (reference only)
- `fpga/build_tqfp_prog.py` — Python script to regenerate PCB

### 7. Firmware (flash cart version, compiles to .uf2)
- `firmware/` — RP2040 firmware with DUMP/SCAN/VERIFY commands
- `flash_cart.py` — Python PC-side tool
- Needs adaptation for FPGA version (SPI loader instead of flash programmer)

## What NEEDS to be done by a human with the ECP5 datasheet

### 1. FPGA pin assignment (CRITICAL)
The ECP5-25F TQFP-144 has:
- ~98 user IO pins across 7 IO banks
- ~34 dedicated pins (VCC, GND, VCCIO, JTAG, config)
- 12 unused/NC pins

**You MUST consult Lattice FPGA-DS-02012, Table 10-4** to get the real
pin-to-function mapping. Then assign signals to IO pins respecting:
- IO bank voltage grouping (all pins in a bank share VCCIO)
- SDRAM on one bank (matched-length traces)
- PROG bus on adjacent bank
- Config pins (PROGRAMN, INITN, DONE, CCLK, SPI) are dedicated — don't assign IO
- JTAG pins (TMS, TCK, TDI, TDO) are dedicated
- VCC (1.1V core) and VCCIO (3.3V per bank) pins must go to power planes

### 2. SDRAM pin mapping (verify against W9825G6KH-6 datasheet)
The build script uses IS42S16400J pin numbering for TSOP-54.
**Verify against the actual W9825G6KH-6 TSOP-54 pinout** — they're
similar but not guaranteed identical.

### 3. CTRG2 connector mapping (verify against Neo Geo documentation)
The PROG connector pinout was taken from jamma-nation-x.com and
cross-referenced with the neogeo-diag-mvs-prog project. The key
signals (A1-A19, D0-D15, ROMOE) should be correct but verify.

### 4. Route the PCB
With correct pin assignments, routing a TQFP-144 on a 4-layer board
is straightforward. Use KiCad's interactive router or Freerouting.

### 5. Generate production files
Export gerbers, BOM CSV, and CPL from KiCad. Order from JLCPCB/PCBWay.

## How to find a freelancer
Search Upwork/Fiverr for "ECP5 PCB design" or "FPGA PCB layout KiCad".
Send them:
1. This document
2. The KiCad project folder (`hardware/neocart/fpga/`)
3. The Verilog (`fpga/rtl/`) so they understand signal requirements
4. Budget: $300-500, timeline: 3-5 days

## Inter-board connection (for Phase 2 CHA board)
- 2×50 pin headers (2.54mm pitch)
- 8mm M2 standoffs between boards
- Measured from Bruno's MVS motherboard

## File structure
```
hardware/neocart/
├── fpga/
│   ├── rtl/                    — Verilog source (6 modules)
│   ├── firmware/               — RP2040 firmware (C, compiles)
│   ├── neocart_tqfp_prog.kicad_pcb  — PCB (components placed)
│   ├── neocart_fpga_prog.kicad_sch  — schematic (reference)
│   ├── build_tqfp_prog.py     — PCB generator script
│   └── FPGA_DESIGN.md         — architecture spec
├── footprints/                 — MVS connector footprints (proven)
├── production/                 — renders, BOMs, gerbers
├── flash_cart.py               — Python flasher tool
└── BOM.md                      — component list
```
