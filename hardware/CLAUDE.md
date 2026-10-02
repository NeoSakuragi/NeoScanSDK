# Hardware — NeoCart

Goal (2026-10-01): a two-board MVS flash cartridge for homebrews (PROG on CTRG2, CHA on CTRG1), ROMs in 3.3 V NOR flash behind LVC level shifters, written through the gold fingers by a separate programmer board (`neocart/progr/`) that also dumps and bench-tests carts. The FPGA + RAM cart (NeoSD / Darksoft topology, QMTech XC7A100T) is the later dev-cart track. Current state, decisions and the pre-order checklist: `neocart/README.md` (2026-10-01).

## Rules that cost real money to learn
- **Never a shift register on a live bus.** v4's 74HC165 address chains take ~1 µs per capture; the 68K wants P-ROM data in ~150 ns. Every live signal goes straight through a level shifter to an FPGA or memory pin. Serial paths only on programming/loading paths.
- **The FPGA is not the memory.** BRAM is 607 KB, DDR3 through MIG is too slow for P-ROM. Memory chips on the bus, FPGA on the 3.3 V side as tap + bank/CE driver + in-system flash programmer.
- **Pin budget first.** CTRG2 = 84 signals, CTRG1 = 99, QMTech = 108 IOs. Count before drawing anything.
- **Orientation-proofing** (v4's header came back mirrored): the QMTech's female headers are on its underside. Place them from the manual's drawing (84.1 × 67.1 mm, rows 61 mm apart, 4.1 mm from the edge, pins 1/2 left in top view) with an explicit mirror transform and a pin-1 assertion; overlay a bottom-view render on the manual's underside photo; 1:1 paper print with the real core laid on it before every order. Headers are hand-soldered, never in the CPL.
- **Every part by LCSC number from a live search** (`neocart/adapter/jlcpcb_search.py`), footprints via easyeda2kicad so JLCPCB's placement orientation matches; check the placement preview part by part before confirming. 5 V flash is no longer sourceable; design for 3.3 V NOR + SN74LVC16245.
- **Nothing on or near the tab.** The shell neck and the slot housing sit around the tab step (y 138.75 on the diag outline). The diag cart keeps every component ≥ 24 mm above that step; our gate refuses any body below y 125. Bruno caught the first P board with a chip row 4 mm from the fingers (2026-09-26).
- **Boards are generated, never hand-placed.** Follow the 15-step process (requirements → verified pinouts → signal classes → nets → zones → placement → overlap gate → constraint assertions → renders inspected before showing → DSN/Freerouting/SES → DRC → gerbers). Never call a board "verified" unless every pin was checked against a datasheet; never show a render with detectable overlaps.

- **Simulate the boards together before routing.** `neocart/progr/sim_system.py` runs the programmer's firmware cycles against the PROG board netlist; its first run found a bus fight. Plant a few wiring faults to prove the checks bite.
- **Pull fine-pitch MCUs onto modules** when a cheap 2-layer board is the goal: the bare RP2350B QFN-80 never routed cleanly; the WeAct module version did.

## Tooling
- KiCad 10.0.3 AppImage extracted at `NeoGeo/AppDir` (no system KiCad any more). `AppDir/AppRun kicad-cli …`; `AppDir/AppRun python3.11 gen.py` for pcbnew scripts (import fails outside AppRun). Footprints: `AppDir/usr/share/kicad/footprints`. Update: `AppDir/usr/bin/kicad-appimage-update.sh`.
- Freerouting 2.2.0: `~/.local/share/kicad/10.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-2.2.0.jar`, `java -Djava.awt.headless=true -jar … -de in.dsn -do out.ses -mp 10`.
- Traps (2026-10-01, details in `neocart/README.md`): pcbnew `Save()` rewrites the `.kicad_pro` (write rules after saving); Freerouting ignores edge clearance (edge bands); ground islands show only as zone↔zone in DRC (check with a fragment graph); `pkill -f` matches its own shell.
- JLCPCB quotes: the assembly-terms checkbox needs Bruno's OK per quote; a session refresh can silently reset the quote page; stop before "Save to cart".
- Scanner: HP M479 on the LAN, `scanimage -d 'escl:https://192.168.68.100:443' --mode Color --resolution 600 --format=png`; flatbeds are sharp only within ~1 mm of the glass, so photograph chip markings.
- FPGA toolchain: Vivado is not installed and does not fit the disk (48–60 GB). openXC7 (yosys + nextpnr-xilinx, Artix-7 with BRAM/IO) is the planned route.

## Structure
| Directory | What |
|-----------|------|
| `neocart/README.md` | Status, constraints, sourcing, decisions (start here) |
| `neocart/adapter/` | v4 PROG/CHA adapters (fabricated, unusable for real-time serving), v5 generators, JLCPCB order files, parts search |
| `neocart/pboard/` | PROG board v3 (current): netlist, sim, generator, routing/export drivers shared with `progr/` |
| `neocart/progr/` | Programmer v1 (WeAct RP2350B + MVS slot): netlist, system sim, generator, firmware, PC tool `neocart.py` |
| `neocart/flash_cart/` | Blank MVS PROG/CHA boards on the diag-cart outline, P-ROM breakout (last work, 2026-05-18) |
| `neocart/reference/` | jwestfall69 neogeo-diag-mvs-prog / -cha: the proven outlines, gold fingers, holes |
| `neocart/datasheets/` | QMTech core + daughter manuals/schematics, ECP5 pinout |
| `neocart/fpga/` | Shelved ECP5-25F design (RTL never synthesised, targets a different board) |
| `neocart/firmware/`, `neocart/flash_cart.py` | RP2040 flash-programmer firmware + PC tool (reusable for the loader) |
| `neocart/sim/` | Verilog cart testbench + SHM bus server glue |

## Physical layout
MVS cart shell: screw side = PROG board (CTRG2), flat side = CHA board (CTRG1). Edge connectors 2×60, 2.54 mm pitch, 1.6 mm card. Slot part: EDAC 345-120-520-201. Shell cavity height for a QMTech stack (~15 mm above PROG) is unmeasured.
