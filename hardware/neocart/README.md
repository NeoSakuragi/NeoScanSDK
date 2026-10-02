# NeoCart — status 2026-10-01

Single entry point for the cartridge hardware. The 2026-09-23 status further down is kept as history.

## Plan (decided)
- **NeoCart = a platform for homebrews.** Protected commercial games (KOF2000-class: SMA, PVC, PCM2 encryption) are out of scope for now.
- **Flash carts are how games ship; a separate programmer writes them.** The FPGA + RAM cart (NeoSD/Darksoft style) stays a later **dev-cart** track
  (instant reload, bus tracing, breakpoints), not the production cart.
- **Programming is NOT embedded on the cart** (comparison in `progr/DESIGN.md`): ~+$56 per 2-cart order (MCU parts, 6 extended-part fees,
  4 layers), an MCU wired to every flash pin on the live bus, no dump/bench capability. The separate programmer is paid once and doubles as a
  dumper / bench tool, and may be sold later.

## Boards
| Board | Folder | State |
|---|---|---|
| **PROG board v3** (CTRG2) | `pboard/` | Routed, DRC 0/0, Gerbers/BOM/CPL exported. 174 × 134 mm, 2 layers, HASL fingers. P = S29GL064N (8 MB, P1 at MB 7, P2 bank n at MB n, 3-bit latch at $2FFFF0); V = ONE S29GL128P shared by ADPCM-A and ADPCM-B (LVC16374 capture registers as a tri-state mux, break-before-make on /SDPOE). JP1: 1-2 PROGRAM / 2-3 PLAY. Logic sim `sim_pboard.py` 14/14. JLCPCB project "neocart_pboard_jlcpcb": 5 PCBs + 2 assembled = **$94.90** before shipping (real quote). **Not ordered.** |
| **Programmer v1** | `progr/` | Routed, DRC 0/0, exported. 176 × 100 mm, 2 layers. WeAct RP2350B core board on headers + MVS slot (EDAC 345-120-520-201) + 4 × SN74LVC16T245, 74LVC16245A (D bus at 3.3 V), 2 × 74LVC16374 latches, TPS2553 cart switch. Netlist imports the CTRG2 table from `pboard/`; `sim_system.py` runs the firmware cycles against the PROG board netlist (9/9, 6 planted faults caught). Firmware `progr/firmware` (Pico SDK, UF2 in `progr/out`), PC tool `progr/neocart.py`. JLCPCB project "neocart_progr_jlcpcb": 5 PCBs + 2 assembled ≈ **$59** before shipping (built from JLCPCB's own BOM prices; final page not read). Plus module ~$4 and slot ~$14-19 bought separately. **Not ordered.** |
| CHA board | — | Not designed. Reference: KOF96 CHA256 (NEO-273 address latch, NEO-ZMC, 8 × 4 MB C, AT27C010 S1/M1). Will be designed together with programmer v2 (two slots, second WeAct module). |

## Before ordering
1. **Logic-analyzer capture** of /SDROE (A56), /SDPOE (A48), SDRMPX (A55), SDPMPX (A47) on Bruno's MVS with KOF96 playing music: the v3 PROG
   board's one unproven assumption (neogeodev wiki: the two strobes fall together, /SDPOE 250 ns, /SDROE 1.5 µs). Tool: any FX2 "24MHz 8CH"
   USB analyzer (CY7C68013A, sigrok/PulseView), ~€16; the Kingst LA1010 (€72) adds nothing needed here. A probe map (where the four lines run on
   the KOF96 PROG board) is still to be made from the scans.
2. **1:1 paper print** of the PROG board in a real shell (fit).
3. Order both boards in ONE JLCPCB order (one wait, one shipment).
Bring-up order: programmer first, validated by dumping Bruno's own SNK carts against MAME CRCs; then the PROG board, debugged with it.

## Reference hardware
`/data/scans/kof96/` (README + photos): 600 dpi scans and phone photos of KOF96 PROGBK1 and CHA256. PROGBK1 confirms our PROG outline
(holes 90.0 mm apart, 103.7 mm below the top edge) and SNK's own shared-V scheme (SNK PCM 9311 chip, V1-V3 = F32-W1/F32-W2/F16-W3,
P1 = F08-Q1, SP2 = F16-Q2, 74LS74A bank latch). Page: claude.ai/artifact/TCAhpmasqBDWVmgKT9YoJ3.

## Tooling traps found 2026-10-01 (see also ../CLAUDE.md)
- `pcbnew` `board.Save()` rewrites the `.kicad_pro` next to the board with KiCad's default net class (0.2 mm): write project rules AFTER saving.
- Freerouting ignores copper-to-edge clearance: add 0.45 mm no-track bands inside every edge before routing.
- A fine-pitch QFN needs a free ring (≥ 2-3 mm) or the autorouter boxes its pins in; a chip module removes the problem.
- Pre-route straight links (latch → shifter) as locked tracks, and gate them against every pad: one pass shorted through decoupling caps.
- KiCad's DRC reports a disconnected ground island only as "zone ↔ zone" at the zone origin; find it with a fragment graph
  (vias, pads, tracks joining filled-polygon fragments). One such island left two GND pins of a level shifter floating.
- `pkill -f <pattern>` matches its own shell: use `pgrep -f "patter[n]"` + kill by PID.
- Shared drivers: `pboard/route_pboard.py` (ROUTE_DIR/ROUTE_NAME), `export_pboard.py` (EXPORT_DIR/EXPORT_NAME), `price_bom.py` (PRICE_DIR),
  `pour_pboard.py` (POUR_YMAX) serve both boards.

# History: status 2026-09-23

Restarted after a four-month gap. This file is the single entry point; the per-track docs below are older and partly superseded.

## What exists
| Track | State |
|---|---|
| v4 PROG + CHA adapters (`adapter/`, JLCPCB order W202604300512O366, 2026-04-30) | On the bench. Header mirrored, holes don't match the shell, no gold fingers, and a design flaw: 74HC165 shift-register address capture (~1 µs) can never meet the 68K's ~150 ns P-ROM window. **Written off.** |
| QMTech XC7A100T core + DB_FPGA_with_RP2040 daughter (ordered 2026-04-28) | Owned, never programmed. No Verilog exists for it (`fpga/rtl` targets the ECP5 board). |
| ECP5-25F custom board (`fpga/`, `HANDOFF_FINAL.md`) | Shelved: superseded by the QMTech route. |
| Flash cart spec (`FLASH_CART_DESIGN.md`, `FLASH_CART_RESEARCH.md`) | Architecture and BOM only; nothing built. 5 V parts in it are no longer sourceable. |
| Blank MVS boards + P-ROM breakout (`flash_cart/`, last commit 2026-05-18) | Routing unfinished; unknown whether the blank PROG board was ever ordered. |

## Target (Bruno, 2026-09-23)
Two PCBs, install the QMTech, drop into donor shells: a playable cart with connectivity (USB, microSD) and debug (bus snooping, breakpoints). Assessment: correct topology, identical to NeoSD / Darksoft, with one correction — the FPGA maps, programs and watches the buses; the ROM data lives in memory chips on the bus.

## Constraints
**Pin budget** (from `adapter/gen_both_pcbs.py` net lists, derived from the diag carts and jamma-nation-x):

| | Signals |
|---|---|
| CTRG2 (PROG): D0–15, A1–19, control incl. ROMWAIT/PWAIT/PDTACK, ADPCM buses | 84 |
| CTRG1 (CHA): CR0–31, P0–23, SDA0–15, SDD0–7, FIX0–7, clocks/ctrl | 99 |
| Total | 183 |
| QMTech IOs on its two headers | 108 |

One QMTech cannot even tap both boards. Options: one QMTech per board (216 IOs, +€74, recommended) or QMTech on PROG only with the CHA as a flash board programmed over a slow serial link (no graphics-bus snooping).

**Timing** (neogeodev wiki): 68K user RAM is 100 ns parts, 166 ns window at 12 MHz → P-ROM ≈ 150 ns. C-ROM address latched by PCK1B (low 55 ns, high 610 ns, 1.5 MHz) → ≈ 600 ns per fetch. XC7A100T BRAM = 607 KB; DDR3 via MIG is too slow for P. Hence NOR flash (S29GL064N, 90 ns) or SRAM for P directly on the bus behind SN74LVC16245 shifters; the FPGA taps the 3.3 V side, drives bank bits and chip enables, programs the flash in-system through the CFI command set, and, for breakpoints, can disable the flash output and drive an instruction onto the data bus (ROMWAIT/PWAIT only configure fixed wait states; they cannot stall the 68K).

**QMTech physical facts** (manual, `datasheets/`): 84.1 × 67.1 mm; two 2×32 female headers on the underside, rows 61 mm apart, 4.1 mm from the edge, pins 1/2 at the left end in top view; U4 = banks 34/35 (1–2 VCCO, 59–64 VIN), U2 = banks 13/14/15 (1–2 3V3, 59–64 VIN); own 5 V DC jack; 6-pin JTAG; N25Q64A config flash. The RP2040 daughter plugs into the same female headers, so it cannot share the core with the cart adapter: the adapter carries its own microSD slot and USB-serial chip; the FPGA is programmed over JTAG into the config flash.

**Sourcing, JLCPCB API 2026-09-23:**

| Part | Role | Price | Stock |
|---|---|---|---|
| S29GL064N90TFI040, 8 MB, 3.3 V, 90 ns | every ROM | $4.65 | 108 |
| IS62WV51216BLL-55TLI, 1 MB SRAM, 55 ns | instant-reload P-ROM option | $12.02 | 4023 |
| IS61WV102416BLL-10TLI, 2 MB SRAM, 10 ns | same, bigger | $27.94 | 2178 |
| SN74LVC16245ADGGR, 16-bit shifter | bus interface | $1.57 | 429 |
| SST39SF040 (5 V, 512 KB) | 5 V option | $5.60 | 60 |
| MX29F800 (5 V, 1 MB) | 5 V option | $7.28 | 1 |
| AM29F800 / AM29F040 | 5 V option | none | 0 |
| RP2040 | loader MCU if wanted | $0.99 | 74k |

5 V flash is gone: the design is 3.3 V NOR + LVC shifters.

**Unknown:** shell cavity height with the CHA board present versus the ~15 mm QMTech stack. Needs a caliper measurement, or a shell-less first version.

## Toolchain
- KiCad 10.0.3 AppImage at `NeoGeo/AppDir`: `AppDir/AppRun kicad-cli …`, `AppDir/AppRun python3.11 gen.py` (pcbnew). Footprints `AppDir/usr/share/kicad/footprints`. Latest upstream 10.0.6.
- Freerouting 2.2.0 jar under `~/.local/share/kicad/10.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/`, Java 25.
- Vivado: not installed, needs 48–60 GB, machine has 45 GB free on /data. Plan: openXC7 (yosys + nextpnr-xilinx, Artix-7 with BRAM/IO, active as of 2026-09-19).
- Parts: `adapter/jlcpcb_search.py <keyword>`; bring parts into KiCad by LCSC number with easyeda2kicad.

## Orientation-proofing (why v4 came back mirrored, and the fix)
1. Header geometry and pin map from the QMTech manual and schematic, placed by the generator with an explicit "core seen from below = mirror X" transform and a pin-1 assertion.
2. Bottom-view render overlaid on the manual's underside photo, inspected before ordering.
3. 1:1 paper print, real core laid on it headers-down, rows and DC jack must land on the silkscreen.
4. A row swap is recoverable in the constraints file (both rows carry the same power at the same ends); a 180° rotation is not, and steps 1–3 exist to catch it.
5. Headers hand-soldered (never in the CPL); SMD parts via easyeda2kicad footprints; JLCPCB placement preview checked part by part.

## Step 1 — blank test boards (2026-09-24, generated, not ordered)
`blank/gen_blank.py` builds `blank/neocart_blank_prog.kicad_pcb` and `blank/neocart_blank_cha.kicad_pcb` on the diag-cart outlines with the diag cart's own finger and test-point footprints, every CTRG pin on a named 1.0 mm test point (upper row = B side, named above; lower row = A side, named below; both faces; hole-blocked names condensed, never moved to the other row's band). Assertions in the generator + KiCad DRC 0/0. JLCPCB zips, renders and reports in `blank/out/`; results page: https://claude.ai/artifact/Jyikm6sDgNqs9VTHfuWEmX. Order options that v4 missed: gold fingers YES + 30° bevel, ENIG.

## Step 2 — P board v1 (2026-09-25, designed and routed, DRC clean, not ordered)
`pboard/`: `design.py` (netlist, 185 parts, self-checked against the datasheet-verified library), `DESIGN.md` (architecture), `gen_pboard.py`
(zone placement + gates, 4-layer), `route_pboard.py` (Freerouting), `export_pboard.py` (JLCPCB files), `sim_pboard.py` (logic simulation of
reads, bank writes, ADPCM reads and programming mode), `firmware/` (RP2350B programmer, Pico SDK) and `pboard_flash.py` (.neo → chip images,
flash/verify over USB). Sourcing and datasheets in `pboard/sourcing_raw.json` and `pboard/datasheets/`.

Verified in software (details in `pboard/DESIGN.md`): the logic simulation (23 scenarios) and the SHM emulator harness (`pboard/harness/`,
KOF96 runs 90 s through the board's chip map, frame 900 identical to the reference). The harness proves image layout, bank map and byte
order only; the ADPCM multiplexing is checked against the neogeodev protocol text by the simulation and finally by the KOF96 CHA board.

Routing status 2026-09-26: 4 layers (F / In1 GND plane / In2 P3V3 plane / B), all parts ≥ 13.75 mm above the tab step, 0.3 mm via drills, KiCad DRC 0 errors, 0 unconnected, JLCPCB zip + BOM + CPL in
`pboard/out/`. It took five Freerouting runs; the fixes that mattered are in `pboard/DESIGN.md` under "Routing". `pboard/fix_routed.py`
(post-route fixes), `pboard/rip_net.py` and `pboard/route_one_net.py` (maze router for a net Freerouting leaves) are part of the flow.

## Open decisions
1. One QMTech per board, or QMTech on PROG only.
2. Measure the shell cavity, or accept a shell-less first version.
3. openXC7 first, or free 60 GB for Vivado.

Next step once decided: signal map + pin budget document, then the board generator.

## Market notes (2026-09-23)
AES+ delayed to 2027-09-16 (€199.99, new ASICs, AES carts only, MVS incompatible). Eagle Software NeoGeoSDK documents the same NOR + programmer cart, no PCB files. NeoSD MVS: 768 MB flash, two Lattice XP2, Cortex-M4; Darksoft: Cyclone IV + DDR; both reflash games over minutes.
