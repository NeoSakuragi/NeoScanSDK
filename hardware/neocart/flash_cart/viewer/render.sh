#!/bin/bash
# Renders 4 PCB views into viewer/ for the live HTML page
# Usage: ./render.sh [path-to-kicad_pcb]

PCB="${1:-../mvs_blank_prog.kicad_pcb}"
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="/tmp/svgconv"

[ -f "$VENV/bin/python3" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" install -q cairosvg; }

# Front copper + mask
kicad-cli pcb export svg --output "$DIR/_f_cu.svg" \
  --layers "F.Cu,F.Mask,Edge.Cuts" \
  --page-size-mode 2 --exclude-drawing-sheet "$PCB" 2>/dev/null

# Back copper + mask (mirrored)
kicad-cli pcb export svg --output "$DIR/_b_cu.svg" \
  --layers "B.Cu,B.Mask,Edge.Cuts" \
  --mirror --page-size-mode 2 --exclude-drawing-sheet "$PCB" 2>/dev/null

# Front copper + silk
kicad-cli pcb export svg --output "$DIR/_f_silk.svg" \
  --layers "F.Cu,F.Mask,F.SilkS,Edge.Cuts" \
  --page-size-mode 2 --exclude-drawing-sheet "$PCB" 2>/dev/null

# Back copper + silk (mirrored)
kicad-cli pcb export svg --output "$DIR/_b_silk.svg" \
  --layers "B.Cu,B.Mask,B.SilkS,Edge.Cuts" \
  --mirror --page-size-mode 2 --exclude-drawing-sheet "$PCB" 2>/dev/null

# Convert to PNG
"$VENV/bin/python3" -c "
import cairosvg, sys, os
d = '$DIR'
pairs = [
    ('_f_cu.svg',   'front_cu.png'),
    ('_b_cu.svg',   'back_cu.png'),
    ('_f_silk.svg', 'front_silk.png'),
    ('_b_silk.svg', 'back_silk.png'),
]
for svg, png in pairs:
    src = os.path.join(d, svg)
    dst = os.path.join(d, png)
    if os.path.exists(src):
        cairosvg.svg2png(url=src, write_to=dst, output_width=2400, background_color='#1a1a2e')
for svg, _ in pairs:
    p = os.path.join(d, svg)
    if os.path.exists(p): os.remove(p)
print('4 views rendered')
"
