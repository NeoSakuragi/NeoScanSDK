# NeoCart programmer v1 — design notes (2026-10-01)

A USB host for MVS PROG boards: the board plays the console. It flashes and verifies the NeoCart PROG board v3
(JP1 on 1-2 PROGRAM), dumps any PROG board (ours or SNK's), and gives the PC raw bus access for bench tests.

Source of truth: `design.py` (netlist; imports the CTRG2 finger table from `../pboard/design.py`, so the two boards cannot disagree).
Simulation: `sim_system.py` joins this netlist to the PROG board netlist at the slot and runs the firmware's cycles
(9 checks: power-up isolation, VCC isolation, P1 identify, P program + read-back over P1 and all 7 P2 banks, V program
+ read-back through both sample buses, dump, wait-state inputs, jumper on PLAY = no writes). Mutation-tested: 6 planted
wiring bugs, all caught (3 by `design.check()`, 4 by the simulation).
Board: `gen_progr.py` → `../pboard/route_pboard.py` (ROUTE_DIR/ROUTE_NAME) → `../pboard/export_pboard.py` (EXPORT_DIR/EXPORT_NAME).
Firmware: `firmware/` (Pico SDK 2.1.1, `cmake -DPICO_NO_PICOTOOL=1`), PC tool `neocart.py` (images, flash, verify, dump, UF2).

## Circuit
| Block | Parts | Why |
|---|---|---|
| MCU | WeAct Studio RP2350B Core Board (~$4.21) on 2 × (2×15) 2.54 mm headers | RP2350B with Raspberry Pi's reference circuit, 16 MB flash, regulator, USB-C, BOOT/RESET, SWD all on the module (schematic + drawing: github.com/WeActStudio/WeActStudio.RP2350BCoreBoard). The bare QFN-80 version did not route cleanly on 2 layers (`out/design_v1_bare_rp2350.py`). |
| Internal bus | GPIO0-15 = MD0-15 | shared by the data transceivers and the latch inputs |
| Strobes | GPIO26-40 → SN74LVC16T245 (U7) → slot | direct and contiguous: PIO can run cycles at bus speed. GPIO23 (module KEY) and GPIO25 (module LED) are avoided and reused as button / busy LED |
| Slow lines | MD → 2 × 74LVC16374 (LCLK1/LCLK2) → 2 × SN74LVC16T245 (U8, U9) | A1-A19, ADPCM high bits, /RESET, 4 MHz, /SLOTCS |
| D0-D15 | 74LVC16245A at 3.3 V (U5) | our PROG board drives D at 3.3 V; a 5 V-referenced input wants 3.5 V. LVC inputs: 2.0 V high, 5.5 V tolerant |
| SDRAD/SDPAD | SN74LVC16T245 (U6), B side 5 V | PROGRAM writes into the PROG board's 74LVC8T245 B port need 3.5 V highs |
| Cart 5 V | module VBUS → TPS2553 (R_ILIM 33k → 0.79 A typ), enable + /FAULT on GPIO44/45, VCART/2 on GPIO46 (ADC6); our 3.3 V logic runs from the module's 3V3 pins | every 16T245 B port runs from VCART: an unpowered cart is never driven (TI VCC isolation) |
| Wait-state inputs | /ROMWAIT /PWAIT0 /PWAIT1 /PDTACK → 1k → GPIO16-19 | RP2350 GPIO0-39 are "Digital IO (FT)": 5.5 V tolerant with IOVDD at 3.3 V |

Slot: EDAC 345-120-520-201 (2 × 60, 2.54 mm pitch, 5.08 mm rows), not stocked by LCSC: buy it separately, hand-solder.
Pad "A<k>" touches cart finger A<k>. The cart's component side faces the top edge (silkscreen arrow). A cart inserted
backwards lands A<k> on B<61-k>: 5 V still meets 5 V and GND meets GND (checked in `design.check()`), and the current
limit plus the firmware's ID check catch the rest.

## Firmware rules (each is a simulation scenario)
1. MD0-15 are released before any transceiver turns toward the MCU (the first simulation run found this bus fight).
2. Power-up: strobes idle and latches loaded with every /OE high → VCART on → /FAULT checked → /OE_OUT low → /RESET released.
3. Jumper on PLAY: autoselect IDs come back as array data instead of 0x0001/0x227E — the PC tool reports it before erasing.

## Layers: 2
First attempt stalled at 133 unrouted: the auto-placer had packed passives against the RP2350's QFN-80 on all four sides, so its
0.4 mm pins could not fan out. A free ring around U1 (RING, 3 mm) fixed it. A 4-layer version was tried and dropped: its first
"good" result turned out to be a 2-layer export, the real 4-layer export did worse, and 2 layers keeps the board at $10.50 for 5.
Trap found on the way: pcbnew's board.Save() rewrites the .kicad_pro next to the board with KiCad's default net class (0.2 mm
clearance), so gen_progr.py writes the project rules AFTER saving the board.

## Cost
Live JLCPCB prices 2026-10-01: assembled parts $9.09/board at 5 boards (4 extended types: 16T245, 16245, 16374, TPS2553;
43 placements). Bought separately: WeAct RP2350B module ~$4.21, slot EDAC 345-120-520-201 ~$14-19 (DigiKey/Mouser),
2 × 2×15 female headers (or solder the module's own male headers straight in). Board 176 × 100 mm, 2 layers.

## Embedding the programmer on every PROG board instead (the comparison Bruno asked for)
| Per PCBA order of 2 carts | Separate programmer | Programmer on each cart |
|---|---|---|
| One-time | programmer order ≈ $85 + slot $12-19 | — |
| Extra parts per cart | — | ≈ $6.90 (RP2350B 1.28, W25Q32 1.50, crystal 0.62, inductor 0.28, USB-C 0.19, 2 × 16374 address latches 1.78, a tri-state buffer for FA16-21 0.69, buttons/LED/passives ~0.55) |
| Extra extended-part fees per order | — | 6 types × $3.09 ≈ $18.50 (RP2350B, W25Q32, crystal, inductor, USB-C, 27R) |
| Board | 2 layers $15.30 | 4 layers $39.40 (+$24.10; v1, the board that carried an RP2350, needed 4 layers) |
| Total extra per order | $0 | ≈ $56 |
v1 is the evidence: it had the RP2350B on the cart, needed 4 layers, 31 part types (22 extended), $40.97 parts per board.
Break-even: the separate programmer pays for itself after about two cart orders, then every order is ~$56 cheaper.
What the cart-borne programmer buys: reflash through a USB port without opening the shell. What it costs besides money:
an MCU wired to every flash pin on a live bus (it must stay high impedance during play), a USB hole in the shell, and no dump/bench
capability for SNK carts.

## Finish flow (as built 2026-10-01)
`gen_progr.py` (MOD_X, MOD_ROT env; variant n = module at x 110) → `../pboard/route_pboard.py 40 placed_*.kicad_pcb` (ROUTE_DIR/ROUTE_NAME)
→ best by DRC (routed_v1 = placed_n, 2 open) → `../pboard/route_one_net.py` for the rest (D5; /ROMOE after ripping the GND rail next to U7)
→ `POUR_YMAX=120.5 ../pboard/pour_pboard.py` (GND both layers, 275 stitching vias) → stitching vias into isolated ground fragments
(two U9 GND pins were connected only through an island) → `fix_silk.py` → DRC with `--refill-zones`: **0 errors, 0 unconnected**.
Backup: `/data/backup/progr_v1_module/`. Export: `EXPORT_DIR=hardware/neocart/progr EXPORT_NAME=neocart_progr BOARDS=2 ../pboard/export_pboard.py`
→ `out/neocart_progr_{jlcpcb.zip,bom.csv,cpl.csv}` (10 part types, 43 placements, stock checked).
Known cosmetic warnings: silkscreen over copper (3), 11 "footprint differs from library" (generated slot/module/test-point footprints).
Known compromise: D5 is a 64 mm detour with 4 vias (fine at the programmer's 1 µs cycles).

## JLCPCB (project "neocart_progr_jlcpcb" in Bruno's account, not ordered)
Detected 2 layers 100 × 176 mm; 5 PCBs $12.50. Economic, 2 assembled, placement confirmation. All 10 BOM lines matched (4 extended).
Placement preview checked: U5 pin 1 dot on the footprint mark, U4 pin 1 (VBUS) corner, LED "+" on the VCART pad; the 16T245/16374 pin-1 marks
sit in the same corner as U5 (model dots not zoomed before the browser extension dropped). Components for 2 boards $22.72 (JLCPCB BOM page);
estimated total ≈ $59 before shipping (setup + stencil $9.79, extended fees ~4 × $3.09, SMT + confirmation ~$1.77).

## Still unverified
- Firmware never ran on hardware; its bus sequences mirror `sim_system.py`, which passes.
- WeAct module pin map taken from WeAct's published pinout/drawing/schematic (GitHub HDK); verify the first module against it with a meter
  (3V3, VBUS, GND, GP0) before soldering it to the board.

## Later
- Programmer v2: both slots (CTRG2 + CTRG1), a second WeAct module for the CHA side (~99 lines), designed together with the NeoCart CHA board.
  Needs the CTRG1-CTRG2 slot spacing measured on Bruno's MVS. Sellable version: v2 + a polished PC tool (MAME-named dumps, CRC check, flash).
- Real-hardware bus tracing: a passthrough tap with an RP2350 (burst captures, ~1-2 frames) or the FPGA dev cart; for instruction traces today,
  log P-ROM fetches in `bus/shm_server.c` and executed instructions in Geolith.
