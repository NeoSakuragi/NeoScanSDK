#!/usr/bin/env python3
"""Route the P board v2 (2 layers) with Freerouting, several variants in parallel, keep the best.
DSN export -> N freerouting jobs (different update strategies / pass counts) -> SES import per variant ->
count unrouted nets and vias -> save the winner as neocart_pboard_routed.kicad_pcb.
Run: AppDir/AppRun python3.11 hardware/neocart/pboard/route_pboard.py [max_passes]
"""
import sys, os, subprocess, glob, time, json, re
import pcbnew
HERE = os.path.abspath(os.environ.get('ROUTE_DIR', os.path.dirname(os.path.abspath(__file__))))   # ROUTE_DIR/ROUTE_NAME: the programmer board uses the same driver
NAME = os.environ.get('ROUTE_NAME', 'neocart_pboard')
OUTD = os.path.join(HERE, 'out')
SRC = os.path.join(HERE, NAME + '.kicad_pcb')
DSN = os.path.join(OUTD, NAME + '.dsn')
OUT = os.path.join(HERE, NAME + '_routed.kicad_pcb')
JAR = glob.glob(os.path.expanduser('~/.local/share/kicad/10.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-*.jar'))[0]
passes = sys.argv[1] if len(sys.argv) > 1 else '40'
# variants: placement files (one Freerouting job each). Default: the single placed board with two optimiser settings.
BOARDS = sys.argv[2:] or [SRC]
VARIANTS = [(b, 'greedy', '10') for b in BOARDS] if len(BOARDS) > 1 else [(SRC, 'greedy', '10'), (SRC, 'global', '5')]

t0 = time.time(); procs = []
for i, (src, us, oit) in enumerate(VARIANTS):
    DSN = os.path.join(OUTD, f'route_v{i}.dsn')
    assert pcbnew.ExportSpecctraDSN(pcbnew.LoadBoard(src), DSN) and os.path.getsize(DSN) > 10000, 'DSN export failed'
    ses = os.path.join(OUTD, f'route_v{i}.ses'); log = open(os.path.join(OUTD, f'route_v{i}.log'), 'w')
    if os.path.exists(ses): os.remove(ses)
    cmd = ['nice', '-n', '10', 'java', '-Xmx3g', '-Djava.awt.headless=true', '-jar', JAR, '-de', DSN, '-do', ses, '-mp', passes, '-us', us, '-oit', oit, '-mt', '2']
    procs.append((i, src, us, oit, ses, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)))
for i, src, us, oit, ses, p in procs:
    p.wait(); print(f'variant {i} ({us}, oit {oit}) finished rc {p.returncode} after {time.time() - t0:.0f}s', flush=True)

results = []
for i, src, us, oit, ses, p in procs:
    if not os.path.exists(ses) or os.path.getsize(ses) < 1000: print('variant', i, 'no SES'); continue
    b = pcbnew.LoadBoard(src)
    if not pcbnew.ImportSpecctraSES(b, ses): print('variant', i, 'SES import failed'); continue
    path = os.path.join(OUTD, f'routed_v{i}.kicad_pcb'); b.Save(path)
    import shutil; shutil.copy(os.path.join(HERE, NAME + '.kicad_pro'), path.replace('.kicad_pcb', '.kicad_pro'))
    if os.path.exists(os.path.join(HERE, NAME + '.kicad_dru')): shutil.copy(os.path.join(HERE, NAME + '.kicad_dru'), path.replace('.kicad_pcb', '.kicad_dru'))   # custom DRC rules travel with the board
    drcj = path.replace('.kicad_pcb', '_drc.json')
    subprocess.run([os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'AppDir', 'AppRun'), 'kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', drcj, path], capture_output=True)
    dj = json.load(open(drcj)); drc_open = len(dj.get('unconnected_items', [])); drc_err = sum(1 for x in dj.get('violations', []) if x['severity'] == 'error')
    vias = sum(1 for t in b.GetTracks() if t.GetClass() == 'PCB_VIA')
    length = sum(t.GetLength() for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK') / 1e6
    logtxt = open(os.path.join(OUTD, f'route_v{i}.log')).read()
    m = re.findall(r'\((\d+) unrouted\)', logtxt); unrouted = int(m[-1]) if m else -1
    results.append(dict(variant=i, placed=os.path.basename(src), strategy=us, oit=oit, unrouted=unrouted, drc_open=drc_open, drc_errors=drc_err, vias=vias, length_mm=round(length), board=path))
    print(results[-1], flush=True)
results.sort(key=lambda r: (r['drc_errors'], r['drc_open'], r['vias'], r['length_mm']))
json.dump(results, open(os.path.join(OUTD, 'route_variants.json'), 'w'), indent=1)
best = results[0]
pcbnew.LoadBoard(best['board']).Save(OUT)
import shutil; shutil.copy(os.path.join(HERE, NAME + '.kicad_pro'), OUT.replace('.kicad_pcb', '.kicad_pro'))
if os.path.exists(os.path.join(HERE, NAME + '.kicad_dru')): shutil.copy(os.path.join(HERE, NAME + '.kicad_dru'), OUT.replace('.kicad_pcb', '.kicad_dru'))
print('BEST', best, '->', OUT)
