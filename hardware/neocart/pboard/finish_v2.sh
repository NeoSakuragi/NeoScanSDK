#!/bin/bash
# P board v2: from the chosen Freerouting result to the final routed board. Run from the NeoGeo repo root.
# Every step below was needed for the 2026-10-01 result (routing variant "q": U2 x 78, U3 x 118, flash row y 48).
set -eu
B=hardware/neocart/pboard; K=AppDir/AppRun; S=$B/out
cp $S/routed_q.kicad_pcb $B/neocart_pboard_routed.kicad_pcb
cp $B/neocart_pboard.kicad_pro $B/neocart_pboard_routed.kicad_pro
# 1. Freerouting joined U6's GND pins 34 and 39 with a bar just below the chip that walls in SDRAD7 (pin 37): the pours do that job.
$K python3.11 $B/rip_box.py $B/neocart_pboard_routed.kicad_pcb GND 73.2,117.5,76.0,119.2
# 2. SDRAD7: U6 pin 37 to its via 2.7 mm below.
$K python3.11 $B/route_one_net.py SDRAD7 $B/neocart_pboard_routed.kicad_pcb --pad U6:37
# 3. GND pours on both layers above the tab + stitching vias (6 mm grid, clear of every hole).
$K python3.11 $B/pour_pboard.py $B/neocart_pboard_routed.kicad_pcb
# 4. U6 pin 39 (GND) lost the bar and sits between two signal traces: stub + via into the bottom pour.
$K python3.11 $B/route_one_net.py GND $B/neocart_pboard_routed.kicad_pcb --pad U6:39
# 5. Silkscreen: IC references on a free side, title in the empty top area.
$K python3.11 $B/fix_silk.py $B/neocart_pboard_routed.kicad_pcb
# 6. Refill and DRC.
$K kicad-cli pcb drc --format json --severity-all --refill-zones --save-board -o $S/drc_routed.json $B/neocart_pboard_routed.kicad_pcb >/dev/null 2>&1
python3 -c "import json; d=json.load(open('$S/drc_routed.json')); v=d['violations']; print('DRC errors', sum(x['severity']=='error' for x in v), 'warnings', sum(x['severity']=='warning' for x in v), 'unconnected', len(d['unconnected_items']))"
