#!/bin/bash
# After routing: DRC (zone refill + save), renders, JLCPCB files, results page. Run from the NeoGeo repo root.
set -u
cd "$(dirname "$0")/../../.." || exit 1
B=hardware/neocart/pboard; K=AppDir/AppRun
$K kicad-cli pcb drc --format json --severity-all --refill-zones --save-board -o $B/out/drc_routed.json $B/neocart_pboard_routed.kicad_pcb 2>&1 | grep -v -E 'Debug|Warning:|Font' | tail -1
python3 - <<'PY'
import json, collections, re
d=json.load(open('hardware/neocart/pboard/out/drc_routed.json')); v=d.get('violations',[]); u=d.get('unconnected_items',[])
print('DRC violations', len(v), collections.Counter((x['type'],x['severity']) for x in v).most_common(10)); print('unconnected', len(u))
errs=[x for x in v if x['severity']=='error']
for x in errs[:8]: print('  ERR', x['type'], '|', x['description'][:70], '|', [(i.get('description','')[:60]) for i in x.get('items',[])][:2])
nets=collections.Counter()
for x in u:
    m=[re.search(r'\[([^\]]+)\]', i.get('description','')) for i in x.get('items',[])]
    nets[re.sub(r'\d+$','#', next((mm.group(1) for mm in m if mm),'?'))]+=1
print('unconnected by net prefix', nets.most_common(12))
PY
for side in top bottom; do $K kicad-cli pcb render --side $side --width 2400 --height 1800 --background opaque --quality high --zoom 1.05 -o $B/out/pboard_routed_${side}.png $B/neocart_pboard_routed.kicad_pcb 2>&1 | grep -v -E 'Debug|Warning:|Font|Success|Rendering|Reload|Loading' | tail -1; done
$K kicad-cli pcb export svg --layers F.Cu,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet -o $B/out/routed_fcu.svg $B/neocart_pboard_routed.kicad_pcb 2>&1 | tail -0
$K kicad-cli pcb export svg --layers B.Cu,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet --mirror -o $B/out/routed_bcu.svg $B/neocart_pboard_routed.kicad_pcb 2>&1 | tail -0
$K python3.11 $B/export_pboard.py 2>&1 | grep -v -E 'Debug|Warning|Font' | tail -3
python3 $B/make_pboard_page.py
ls -la $B/out/pboard_routed_*.png $B/out/neocart_pboard_jlcpcb.zip $B/out/results.html | awk '{print $5,$9}'
