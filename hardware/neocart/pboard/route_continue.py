#!/usr/bin/env python3
"""Continue routing from the current routed board (keeps existing tracks): DSN with wires -> freerouting -> SES -> save.
Run: AppDir/AppRun python3.11 hardware/neocart/pboard/route_continue.py [max_passes]
"""
import sys, os, subprocess, glob, time
import pcbnew
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb')
DSN = os.path.join(HERE, 'out', 'neocart_pboard_cont.dsn'); SES = os.path.join(HERE, 'out', 'neocart_pboard_cont.ses')
JAR = glob.glob(os.path.expanduser('~/.local/share/kicad/10.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-*.jar'))[0]
passes = sys.argv[1] if len(sys.argv) > 1 else '10'
board = pcbnew.LoadBoard(SRC)
assert pcbnew.ExportSpecctraDSN(board, DSN); print('DSN', os.path.getsize(DSN) // 1024, 'KB (with existing wiring)')
t = time.time()
r = subprocess.run(['java', '-Xmx6g', '-Djava.awt.headless=true', '-jar', JAR, '-de', DSN, '-do', SES, '-mp', passes, '-us', 'global', '-oit', '2'], capture_output=True, text=True, timeout=4 * 3600)
print('freerouting rc', r.returncode, f'{time.time() - t:.0f}s'); print('\n'.join((r.stdout + r.stderr).strip().splitlines()[-14:]))
assert os.path.exists(SES) and os.path.getsize(SES) > 1000
board = pcbnew.LoadBoard(SRC); assert pcbnew.ImportSpecctraSES(board, SES); board.Save(SRC); print('saved', SRC)
