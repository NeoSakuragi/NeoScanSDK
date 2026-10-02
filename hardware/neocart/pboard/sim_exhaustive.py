#!/usr/bin/env python3
"""Exhaustive driver enumeration on the design.py netlist: every combination of the MVS strobes, R/W, PROG_MODE and the MCU's
enable lines is settled and every net with more than one driver is reported. Run: python3 sim_exhaustive.py"""
import itertools, sys, os, json, time, importlib.util, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
# import the simulator module without running its scenarios: exec the file up to the scenario section
src = open(os.path.join(HERE, 'sim_pboard.py')).read().split("s = Sim(); idle(s)")[0]
ns = {'__file__': os.path.join(HERE, 'sim_pboard.py'), '__name__': 'simcore'}
with contextlib.redirect_stdout(io.StringIO()): exec(compile(src, 'sim_pboard.py', 'exec'), ns)
Sim, idle, Z, d = ns['Sim'], ns['idle'], ns['Z'], ns['d']
MVS_LINES = ['RW', 'nROMOE', 'nPORTOEL', 'nPORTOEU', 'nPORTWEL', 'nPORTADRS', 'nSDROE', 'nSDPOE']
MCU_LINES = ['nP_OE', 'nP_WE', 'nVA_OE', 'nVA_WE', 'nVB_OE', 'nVB_WE']
def reachable(v):
    """states the MVS can actually produce: read strobes only while R/W is high, the write strobe only while it is low"""
    if v['RW'] == 0 and (v['nROMOE'] == 0 or v['nPORTOEL'] == 0 or v['nPORTOEU'] == 0): return False
    if v['RW'] == 1 and v['nPORTWEL'] == 0: return False
    return True
findings = {}; n = 0; t0 = time.time()
for prog in (0, 1):
    mcu_combos = list(itertools.product((0, 1), repeat=len(MCU_LINES))) if prog else [None]
    for mvs in itertools.product((0, 1), repeat=len(MVS_LINES)):
        v = dict(zip(MVS_LINES, mvs))
        for mcu in mcu_combos:
            s = Sim(); idle(s)
            s.drive('PROG_MODE', 'jumper', prog)
            s.mvs(**v, nROMOEL=v['nROMOE'], nROMOEU=v['nROMOE'])
            for i in range(16): s.drive(f'D{i}', 'MVS', (i & 1) if v['RW'] == 0 else Z)
            for i in range(8): s.drive(f'SDRAD{i}', 'MVS', Z); 
            if mcu:
                for name, val in zip(MCU_LINES, mcu): s.drive(name, 'MCU', val)
            try:
                s.settle()
            except AssertionError as e:
                key = ('EXC', str(e)[:80]); findings.setdefault(key, []).append((prog, v, mcu)); n += 1; continue
            for net, srcs in s.strong.items():
                drivers = [k for k in srcs if k != 'power']
                if len(drivers) > 1:
                    key = (net, tuple(sorted(drivers))); findings.setdefault(key, []).append((prog, v, mcu))
            n += 1
print(f'{n} states settled in {time.time() - t0:.0f} s')
if not findings: print('NO net ever has more than one driver: no bus contention in any strobe combination')
report = []
for key, states in findings.items():
    reach = [st for st in states if reachable(st[1])]
    line = f'{key}: {len(states)} states, {len(reach)} physically reachable; example {states[0]}'
    print(line); report.append({'net': key[0], 'drivers': list(key[1]) if isinstance(key[1], tuple) else key[1], 'states': len(states), 'reachable': len(reach), 'example': str(states[0])})
json.dump({'states': n, 'findings': report}, open(os.path.join(HERE, 'out', 'sim_exhaustive.json'), 'w'), indent=1)
sys.exit(1 if any(r['reachable'] for r in report) else 0)
