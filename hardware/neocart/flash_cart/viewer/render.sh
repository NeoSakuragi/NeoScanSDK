#!/bin/bash
# Renders PROG + CHA board views for the live HTML viewer
# Usage: ./render.sh

DIR="$(cd "$(dirname "$0")" && pwd)"
FLASH="$(dirname "$DIR")"
VENV="/tmp/svgconv"

[ -f "$VENV/bin/python3" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" install -q cairosvg; }

PROG="$FLASH/mvs_blank_prog.kicad_pcb"
CHA="$FLASH/mvs_blank_cha.kicad_pcb"

# PROG front (A-side)
kicad-cli pcb export svg --output "$DIR/_prog_front.svg" \
  --layers "F.Cu,F.Mask,F.SilkS,Edge.Cuts" \
  --page-size-mode 2 --exclude-drawing-sheet "$PROG" 2>/dev/null

# PROG back (B-side) — no mirror, so labels read correctly
kicad-cli pcb export svg --output "$DIR/_prog_back.svg" \
  --layers "B.Cu,B.Mask,B.SilkS,Edge.Cuts" \
  --page-size-mode 2 --exclude-drawing-sheet "$PROG" 2>/dev/null

# CHA front (A-side)
[ -f "$CHA" ] && kicad-cli pcb export svg --output "$DIR/_cha_front.svg" \
  --layers "F.Cu,F.Mask,F.SilkS,Edge.Cuts" \
  --page-size-mode 2 --exclude-drawing-sheet "$CHA" 2>/dev/null

# CHA back (B-side) — no mirror
[ -f "$CHA" ] && kicad-cli pcb export svg --output "$DIR/_cha_back.svg" \
  --layers "B.Cu,B.Mask,B.SilkS,Edge.Cuts" \
  --page-size-mode 2 --exclude-drawing-sheet "$CHA" 2>/dev/null

# Convert to PNG
"$VENV/bin/python3" -c "
import cairosvg, os
d = '$DIR'
for name in ['prog_front', 'prog_back', 'cha_front', 'cha_back']:
    src = os.path.join(d, '_' + name + '.svg')
    dst = os.path.join(d, name + '.png')
    if os.path.exists(src):
        cairosvg.svg2png(url=src, write_to=dst, output_width=2400, background_color='#1a1a2e')
        os.remove(src)
print('Views rendered')
"
