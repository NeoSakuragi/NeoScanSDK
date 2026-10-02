#!/usr/bin/env python3
"""Before Freerouting: route the nets it keeps leaving unrouted with the maze router while the board is still empty (only pads,
GND stitches and keepouts exist), pad by pad into the net's own copper. Freerouting keeps pre-existing wires and routes around them.
Usage: python3 preroute_hard_nets.py [board] [NET ...]   (defaults: neocart_pboard.kicad_pcb and the list below)"""
import os, sys, subprocess, importlib.util, time
HERE = os.path.dirname(os.path.abspath(__file__)); K = os.path.join(HERE, '..', '..', '..', 'AppDir', 'AppRun')
args = sys.argv[1:]; board = args[0] if args and args[0].endswith('.kicad_pcb') else os.path.join(HERE, 'neocart_pboard.kicad_pcb')
nets = [a for a in args if not a.endswith('.kicad_pcb')] or ['FA2', 'FA4', 'FA5', 'SDPAD2', 'SDPAD4', 'nP_OE', 'P2', 'VBUS']
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
t0 = time.time(); ok = bad = 0
for net in nets:
    pads = [f'{r}:{pn}' for r, pn in d.NETS[net] if r.startswith('U')] + [f'{r}:{pn}' for r, pn in d.NETS[net] if not r.startswith('U')]
    res = []
    for pad in pads[1:]:
        out = subprocess.run([K, 'python3.11', os.path.join(HERE, 'route_one_net.py'), net, board, '--pad', pad], capture_output=True, text=True)
        line = [l for l in (out.stdout + out.stderr).splitlines() if l.startswith('routed') or 'NO PATH' in l]
        good = bool(line) and line[-1].startswith('routed'); ok += good; bad += not good; res.append(f"{pad}:{'ok' if good else 'FAIL'}")
    print(f'{net}: ' + ' '.join(res))
print(f'pre-routed {ok} pad connections, {bad} failed, {time.time() - t0:.0f} s')
sys.exit(1 if bad else 0)
