#!/usr/bin/env python3
"""Chain Lab site files from a brawler build: the ROM, a BIOS archive with only SNK's MVS BIOS (region US: sp-u2.sp1,
its fix / sound / zoom ROMs; no UniBIOS), the game's layout (symbol addresses, fighter_t offsets: harness._layout) and
the fighters' move / route data (build/chainlab.json, export_bm.py).

    python3 make_site.py OUTDIR [GAME_DIR]      (GAME_DIR: examples/brawler, built)"""
import json, os, shutil, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness
out = sys.argv[1]; game = sys.argv[2] if len(sys.argv) > 2 else harness.GAME
os.makedirs(out, exist_ok=True)
shutil.copy(os.path.join(game, 'brawler.neo'), os.path.join(out, 'game.neo'))
with zipfile.ZipFile('/data/roms/neogeo.zip') as src, zipfile.ZipFile(os.path.join(out, 'neogeo.zip'), 'w', zipfile.ZIP_DEFLATED) as dst:
    for n in ('sp-u2.sp1', '000-lo.lo', 'sfix.sfix', 'sm1.sm1'): dst.writestr(n, src.read(n))
layout, fsize, states, syms = harness._layout(game)
want = ['lab', 'fighters', 'route_tab', 'bm_chars', 'mode', 'cam_x', 'projectiles']
json.dump({'fields': layout, 'fsize': fsize, 'states': states, 'syms': {k: syms[k] for k in want if k in syms},
           'version': open(os.path.join(game, 'VERSION')).read().strip()},
          open(os.path.join(out, 'layout.json'), 'w'))
shutil.copy(os.path.join(game, 'build', 'chainlab.json'), os.path.join(out, 'chainlab.json'))
for f in ('index.html', 'app.js', 'lab.js'): shutil.copy(os.path.join(HERE, f), os.path.join(out, f))
print('site data in', out)
