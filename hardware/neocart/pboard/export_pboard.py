#!/usr/bin/env python3
"""JLCPCB production files for the P board: gerbers+drill zip, BOM (LCSC) and CPL, from the routed board.
Run: AppDir/AppRun python3.11 hardware/neocart/pboard/export_pboard.py
"""
import os, sys, csv, json, subprocess, importlib.util, zipfile
import pcbnew
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
HERE = os.path.abspath(os.environ.get('EXPORT_DIR', os.path.dirname(os.path.abspath(__file__))))   # EXPORT_DIR/EXPORT_NAME: the programmer board uses the same exporter
NAME = os.environ.get('EXPORT_NAME', 'neocart_pboard')
KI = os.path.join(ROOT, 'AppDir', 'AppRun')
SRC = os.path.join(HERE, NAME + '_routed.kicad_pcb')
OUT = os.path.join(HERE, 'out'); G = os.path.join(OUT, 'gerbers'); os.makedirs(G, exist_ok=True)
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); design = importlib.util.module_from_spec(spec); spec.loader.exec_module(design)
def mm(v): return v / 1e6

board = pcbnew.LoadBoard(SRC)
# --- live stock check at JLCPCB: refuse to write a BOM with a part that is no longer orderable ----------------------
import time
from collections import Counter
need = Counter(pt['lcsc'] for r, pt in design.PARTS.items() if pt['lcsc'] and not r.startswith('JP'))   # parts without an LCSC number (fingers, slot) are never in the BOM
url = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
short = []
for code, n in need.items():
    body = json.dumps({"keyword": code, "pageSize": 5, "pageNum": 1})
    out = subprocess.run(['curl', '-s', '-m', '30', '-X', 'POST', url, '-H', 'Content-Type: application/json', '-H', 'User-Agent: Mozilla/5.0', '-d', body], capture_output=True, text=True).stdout
    lst = ((json.loads(out or '{}').get('data') or {}).get('componentPageInfo') or {}).get('list') or []
    p = next((x for x in lst if x.get('componentCode') == code), None)
    boards = int(os.environ.get('BOARDS', '5'))
    if not p or not p.get('isBuyComponent') or (p.get('stockCount') or 0) < n * boards: short.append((code, n * boards, p.get('stockCount') if p else 'not found'))
    time.sleep(0.2)
if short:
    for code, want, have in short: print(f'STOCK PROBLEM {code}: need {want}, JLCPCB has {have}')
    sys.exit('BOM not written: fix the parts above or set BOARDS=<n> lower')
print(f'stock check passed for {len(need)} parts x {os.environ.get("BOARDS", "5")} boards')
# --- BOM + CPL (JLCPCB format). Test points, headers hand-soldered by Bruno: not in the BOM. ------------------------
bom = {}; cpl = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith(('TP', 'MH')): continue
    pt = design.PARTS.get(ref)
    if not pt or not pt['lcsc']: continue
    if ref.startswith('JP'): continue                       # headers: hand soldered
    key = pt['lcsc']
    bom.setdefault(key, {'Comment': pt['value'], 'Designator': [], 'Footprint': pt['footprint'], 'LCSC Part #': key})
    bom[key]['Designator'].append(ref)
    # CPL position = centre of the pad bounding box (JLCPCB's convention), not the footprint origin
    xs = [mm(p.GetPosition().x) for p in fp.Pads()]; ys = [mm(p.GetPosition().y) for p in fp.Pads()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2; rot = fp.GetOrientationDegrees()
    cpl.append({'Designator': ref, 'Mid X': f'{cx:.3f}mm', 'Mid Y': f'{-cy:.3f}mm', 'Layer': 'Top' if fp.GetLayer() == pcbnew.F_Cu else 'Bottom', 'Rotation': f'{rot:.1f}'})
with open(os.path.join(OUT, NAME + '_bom.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for k, r in bom.items(): w.writerow([r['Comment'], ','.join(r['Designator']), r['Footprint'], r['LCSC Part #']])
with open(os.path.join(OUT, NAME + '_cpl.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation']); w.writeheader(); w.writerows(cpl)
print(f'BOM: {len(bom)} distinct parts, {sum(len(r["Designator"]) for r in bom.values())} placements')
# --- gerbers + drill -------------------------------------------------------------------------------------------------
for f in os.listdir(G): os.remove(os.path.join(G, f))
subprocess.run([KI, 'kicad-cli', 'pcb', 'export', 'gerbers', '--layers', 'F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts',
                '--subtract-soldermask', '--no-x2', '--no-netlist', '-o', G + '/', SRC], check=True, capture_output=True)
subprocess.run([KI, 'kicad-cli', 'pcb', 'export', 'drill', '--format', 'excellon', '--excellon-zeros-format', 'decimal', '--drill-origin', 'absolute', '--generate-map', '--map-format', 'gerberx2', '-o', G + '/', SRC], check=True, capture_output=True)
zp = os.path.join(OUT, NAME + '_jlcpcb.zip')
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(G)):
        if f.endswith(('.gbr', '.gtl', '.gbl', '.gts', '.gbs', '.gto', '.gbo', '.gtp', '.gbp', '.gm1', '.g1', '.g2', '.drl', '.gbrjob')): z.write(os.path.join(G, f), f)
print('zip', zp, os.path.getsize(zp) // 1024, 'KB', len(os.listdir(G)), 'files')
