# NeoCart Flash Cart — Design Spec

## Decision: CPLD + NOR Flash, JLCPCB assembled

### Architecture
```
MVS bus (5V) ←→ 74LVC245 level shifters ←→ NOR flash (3.3V)
                                              ↑
                                         XC9536XL CPLD
                                    (address decode + bank switch)
```
Data goes direct from NOR flash to MVS bus through level shifters.
CPLD only handles chip selects and bank registers — never touches data.

### Board Outline
Locked reference: `hardware/neocart/reference/neogeo-diag-mvs-prog/` and `neogeo-diag-mvs-cha/`
- Board: 174mm × 134mm
- Mounting holes: (94.75, 127.0) and (184.75, 127.0), radius 5.0mm
- Gold fingers: 60 pins per side, 2.54mm pitch
- Notches: left (88.75-100.75, 23.75-26.25), right (178.75-190.75, 23.75-26.25)
- Step-down at Y=138.75 for gold finger area

### Prototype Config (danmaku game, 5 chips)

**PROG board (CTRG2):**
| Ref | Part | JLCPCB # | Function | Size |
|-----|------|----------|----------|------|
| U1 | XC9536XL-10VQG44C | C124132 | CPLD — address decode + bank switch | VQFP-44 |
| U2 | S29GL064N90TFI040 | C117907 | P-ROM (68K code + LUTs) | 8MB TSOP-48 |
| U3 | S29GL064N90TFI040 | C117907 | V-ROM (ADPCM samples) | 8MB TSOP-48 |
| U4 | SN74LVC16245ADGGR | C7824 | 16-bit level shifter (P data bus) | TSSOP-48 |
| U5 | 74LVC245 (MDD) | C53552926 | 8-bit level shifter (V data bus) | TSSOP-20 |
| U6 | 74HC374 | — | Bank register latch | SOIC-20 |
| U7 | 74HC138 | C5602 | Address decoder | SOIC-16 |
| U8 | AMS1117-3.3 | C6186 | 3.3V LDO (BASIC) | SOT-223 |
| P2 | 6× pads | — | Programming port (VCC,GND,CLK,MOSI,MISO,CS) | Exposed copper |
| | Passives | BASIC | Decoupling caps, pull-ups | 0402/0603 |

**CHA board (CTRG1):**
| Ref | Part | JLCPCB # | Function | Size |
|-----|------|----------|----------|------|
| U1 | XC9536XL-10VQG44C | C124132 | CPLD — address decode + bank switch | VQFP-44 |
| U2 | S29GL064N90TFI040 | C117907 | C1 ROM (sprite even bytes) | 8MB TSOP-48 |
| U3 | S29GL064N90TFI040 | C117907 | C2 ROM (sprite odd bytes) | 8MB TSOP-48 |
| U4 | S29GL064N90TFI040 | C117907 | S-ROM + M-ROM (shared) | 8MB TSOP-48 |
| U5 | 74LVC245 (MDD) | C53552926 | 8-bit level shifter (S data) | TSSOP-20 |
| U6 | 74LVC245 (MDD) | C53552926 | 8-bit level shifter (M data) | TSSOP-20 |
| U7 | 74HC574 | — | Bank register latch (C-ROM) | SOIC-20 |
| U8 | 74HC574 | — | Bank register latch (V via CHA) | SOIC-20 |
| U9 | 74HC138 | C5602 | Address decoder | SOIC-16 |
| U10 | AMS1117-3.3 | C6186 | 3.3V LDO (BASIC) | SOT-223 |
| P2 | 6× pads | — | Programming port | Exposed copper |
| | Passives | BASIC | Decoupling caps, pull-ups | 0402/0603 |

### Max Config (KOF 2003 class, 13 chips)
Same boards but populated with:
- PROG: 2× P-ROM + 2× V-ROM = 4 flash chips
- CHA: 4× C1 + 4× C2 + 1× S/M = 9 flash chips
- Extra bank bits from CPLD for larger address space

### Cost Summary (5 prototype carts, JLCPCB fully assembled)

| Item | Cost |
|------|------|
| PCBs (10 boards, HASL prototype) | $70 |
| Setup fee (×2 designs) | $16 |
| Components (all) | $118 |
| Extended surcharges (~10 unique) | $30 |
| Assembly (pick & place) | $5 |
| **Total (5 carts)** | **~$290** |
| **Per cart** | **~$58** |
| Shells (AliExpress, separate) | ~$50 for 5 |

Production run (1000 carts + gold fingers): ~$72/cart → $72,000
At $199 retail: ~$127K profit before dev costs and taxes.

### Programming
6-pad SPI port (P2) on each board.
Programming jig: RP2040 dev board ($4) + pogo pin adapter + 3D printed alignment frame.
Sequence: JTAG to CPLD, then bit-bang NOR flash write protocol through CPLD.

### Verification Assertions (built into generator script)
```python
assert hole_positions_match(NEOGEO_DIAG_MVS_REF), "Mounting holes"
assert board_outline_matches(NEOGEO_DIAG_MVS_REF), "Board outline"
assert gold_finger_no_solder_mask(), "Mask clearance on fingers"
assert pin1_nets_correct(CPLD, FLASH, SHIFTERS), "Pin 1 orientation"
assert all_power_on_power_nets(), "No power on signal nets"
assert all_components_inside_boundary(), "Component placement"
assert ctrg_pinout_matches(MAME_REFERENCE), "Edge connector pinout"
```

### What We Need to Start
1. CTRG2 (PROG) complete pinout — from neogeo-diag-mvs-prog reference
2. CTRG1 (CHA) complete pinout — from neogeo-diag-mvs-cha reference  
3. XC9536XL Verilog — address decode + bank switch logic
4. NOR flash datasheet — S29GL064N timing + pin assignments
5. Level shifter wiring — which bus lines need shifting
6. Schematic capture — KiCad or programmatic
7. PCB layout — programmatic with assertion checks
8. JLCPCB BOM + CPL files — for assembly order

### Reference Designs
- `hardware/neocart/reference/neogeo-diag-mvs-prog/` — PROG board outline, gold fingers, holes
- `hardware/neocart/reference/neogeo-diag-mvs-cha/` — CHA board outline, gold fingers, holes
- PixelHeart NeoDriftOut teardown — validates CPLD+NOR+LDO+shifter architecture
- VTXCart (github.com/xvortex/VTXCart) — CPLD Verilog for Neo Geo banking
