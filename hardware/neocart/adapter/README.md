> **Warning (2026-09-23):** the v4 boards below were fabricated but cannot serve ROMs in real time — the 74HC165 shift-register address capture takes ~1 µs against the 68K's ~150 ns P-ROM window. They also have a mirrored FPGA header, wrong shell holes and no gold fingers. Written off; see `../README.md`.

# NeoCart PCB Adapters

KiCad PCB designs for PROG and CHA board adapters that connect an FPGA to the MVS cart slot.

## Current Designs

### PROG Board (v5 TQFP)
68K program bus adapter. Connects to CTRG2 (PROG connector).
- `prog_v5_tqfp.kicad_pcb` — unrouted
- `prog_v5_tqfp_routed.kicad_pcb` — autorouted

### PROG Breakout
Simpler breakout board for prototyping.
- `prog_breakout.kicad_pcb` — unrouted
- `prog_breakout_routed.kicad_pcb` — autorouted

### CHA Board (v5 TQFP)
Character/sound bus adapter. Connects to CTRG1 (CHA connector).
- `cha_v5_tqfp.kicad_pcb` — unrouted
- `cha_v5_tqfp_routed.kicad_pcb` — autorouted

## Production Files

- `gerbers_jlc_prog/` — PROG gerbers for JLCPCB
- `gerbers_jlc_cha/` — CHA gerbers for JLCPCB
- `jlcpcb_order/` — BOM + CPL for assembly
- `neocart_*_cpl_FINAL.csv` — Component placement (final)
- `neocart_*_pos.csv` — Pick and place
