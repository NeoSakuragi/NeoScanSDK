# NeoCart FPGA — Handoff Package

## What this is
FPGA-based Neo Geo MVS dev cart. Two boards that stack together
and plug into an MVS motherboard. Loads ROM data from USB,
serves it to the Neo Geo in real-time, captures bus activity
for debugging.

## What's done

### Proven board outlines ✅
Both board outlines cloned from manufactured, tested open-source MVS carts:
- PROG: from github.com/jwestfall69/neogeo-diag-mvs-prog
- CHA: from github.com/jwestfall69/neogeo-diag-mvs-cha
Board shape, gold fingers, notches, mounting holes — all verified to fit MVS slots.

### Component placement ✅
All components placed on both PCBs using pcbnew:
- `fpga/neocart_fpga_prog.kicad_pcb` — PROG board (10 ICs, 7 connectors, ~60 passives)
- `fpga/neocart_fpga_cha.kicad_pcb` — CHA board (pin headers + resistors)

### Schematic ✅
- `fpga/neocart_fpga_prog.kicad_sch` — 390 nets, all connections defined
- Every component pin mapped to a named net via net labels

### Verilog RTL ✅
- `fpga/rtl/neocart_top.v` — top-level module
- `fpga/rtl/prog_bus.v` — P ROM + V ROM bus interface
- `fpga/rtl/cha_bus.v` — C ROM + S ROM + M ROM bus interface
- `fpga/rtl/sdram_ctrl.v` — multi-port SDRAM controller
- `fpga/rtl/spi_slave.v` — SPI interface to RP2040
- `fpga/rtl/bus_snooper.v` — 68k bus transaction capture
- `fpga/rtl/clk_pll.v` — 12MHz → 100MHz PLL

### BOM with LCSC part numbers ✅
- `production/fpga_bom_prog.csv`
- `production/fpga_bom_cha.csv`

### 3D renders ✅
- `production/neocart_fpga_prog_top.png`
- `production/neocart_fpga_cha_top.png`

## What needs to be done to order

### 1. Create ECP5-25F-BG256 KiCad symbol (~2 hours)
KiCad doesn't ship with a symbol for the LFE5U-25F in BGA-256 package.
Need to create one from the Lattice pinout CSV:
  https://www.latticesemi.com/products/fpgaandcpld/ecp5

Use ecppll or the ECP5-Utils repo to generate:
  https://github.com/ECP5-PCIe/ECP5-Utils

The symbol needs 256 pins mapped to the correct BGA ball names (A1-P16).

### 2. Link schematic to PCB ("Update PCB from Schematic")
Open `neocart_fpga_prog.kicad_sch` in KiCad.
Fix any remaining symbol references.
Open the PCB, run Tools → Update PCB from Schematic.
This assigns nets to pads — the critical step for routing.

### 3. FPGA pin assignment
Assign FPGA I/O signals to specific BGA balls. Consider:
- Put SDRAM on one I/O bank (short, matched-length traces)
- Put PROG bus on adjacent banks
- Put CHA bus (inter-board connector) on opposite banks
- Keep SPI + config pins on their dedicated bank

Create constraints file: `fpga/constraints/neocart.lpf`

### 4. Route traces
With nets assigned, either:
- Route interactively in KiCad (Tools → Route Tracks, press X)
- Export DSN (File → Export → Specctra DSN), run Freerouting
- Send to a PCB freelancer ($200-400)

BGA fanout is the hardest part — the inner balls of the FPGA need
via fanout to escape to the outer routing layers.

### 5. DRC → Gerbers → Order
Run DRC (Inspect → Design Rules Check).
Fix violations.
Export gerbers (File → Plot).
Upload to JLCPCB/PCBWay.

## Architecture reference

```
PROG board (brain):
  ECP5-25 FPGA (BGA-256) ─── 2x W9825G6KH SDRAM (64MB)
       │
       ├── PROG bus (68k addr/data, V ROM) ─── edge connector
       ├── CHA bus (via pin headers) ─── to CHA board
       ├── SPI slave ←── RP2040 (USB-C, loads ROMs)
       └── bus snooper → RP2040 → USB → PC (debug trace)

CHA board (passive):
  Edge connector ─── 470Ω resistors ─── pin headers ─── to PROG board
```

## Inter-board connection
- 2x 2x25 pin headers (100 pins total)
- 8mm M2 brass standoffs through mounting holes
- Pin mapping in schematic (J5A/J5B)

## Key specs
- Board dimensions: 174mm × 134mm (both boards identical)
- Edge connector: 60 pins per side, 2.54mm pitch
- FPGA: Lattice LFE5U-25F-6BG256I (LCSC: C5272996)
- SDRAM: 2x Winbond W9825G6KH-6, 32MB each (LCSC: C62246)
- Power: 5V from Neo Geo → 3.3V (AMS1117-3.3) → 1.1V (AMS1117-1.1)
- Level shifting: 470Ω series resistors on 5V inputs, 74LVC245 on data bus
- USB: via RP2040, CDC serial protocol
- No SD card — USB-only injection
