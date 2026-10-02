#!/bin/bash
# P board v3 (one shared sample flash): from the chosen Freerouting result to the final board. Run from the NeoGeo repo root.
# Chosen 2026-10-01: placement w3e (U2 x 97, flash row y 50, data bus pre-routed by preroute_dbus.py, finger corridors free).
set -eu
B=hardware/neocart/pboard; K=AppDir/AppRun; S=$B/out
cp $S/routed_w3e.kicad_pcb $B/neocart_pboard_routed.kicad_pcb
cp $S/placed_w3e.kicad_pcb $B/neocart_pboard.kicad_pcb
cp $B/neocart_pboard.kicad_pro $B/neocart_pboard_routed.kicad_pro
$K python3.11 $B/pour_pboard.py $B/neocart_pboard_routed.kicad_pcb          # GND pours both layers above the tab + 6 mm stitching
$K python3.11 $B/fix_silk.py $B/neocart_pboard_routed.kicad_pcb            # IC references on a free side, title in the top area
$K kicad-cli pcb drc --format json --severity-all --refill-zones --save-board -o $S/drc_routed.json $B/neocart_pboard_routed.kicad_pcb >/dev/null 2>&1
python3 -c "import json; d=json.load(open('$S/drc_routed.json')); v=d['violations']; print('DRC errors', sum(x['severity']=='error' for x in v), '| unconnected', len(d['unconnected_items']))"
