#!/usr/bin/env python3
"""RELEASE GATE (2026-10-16, the FPGA / MVS crash): no word / long access at an odd address, ever. A real 68000 takes an
ADDRESS ERROR there (UniBIOS: its ADDRESS ERROR screen; SNK's MVS BIOS: garbage, then a reset, ~24 s after power-on in
the first attract demo of 0.10.152: route nodes read from byte arrays at odd addresses). Our stock Geolith core ignores
it, so nothing else in the test suite can see it.

    python3 odd_access_proof.py [--rom examples/brawler/brawler.neo] [--build build] [--out /data/tmp/odd_access]
           [--attract 8100] [--max 20000] [--stage 1]

Runs fpga_playthrough.py on the address-error core (aerr_core.sh, rebuilt when stale; odd accesses logged, mode 1)
for BOTH BIOS setups at once (mvs-mvs: SNK MVS BIOS; uni-aes: UniBIOS as an AES): power on, the attract demo (3 loops
at 8100 frames), coin, START, the select, a short campaign (the bot plays until stage --stage is done or --max frames).
ALL OK = on both: zero odd-address accesses, the play reached, no fault past the BIOS's boot (PC outside ROM / RAM /
BIOS, a long stay in the BIOS, ticks stalled). Otherwise each odd access is listed as (address, read / write, PPC) with
the symbol the address falls in (build/rom.elf), and the run's logs stay in OUT/<sys>/run.json. ~1 min."""
import argparse, bisect, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))

ap = argparse.ArgumentParser()
ap.add_argument('--rom', default=os.path.join(GAME, 'brawler.neo')); ap.add_argument('--game', default=GAME)
ap.add_argument('--build', default='build'); ap.add_argument('--out', default='/data/tmp/odd_access')
ap.add_argument('--attract', type=int, default=8100); ap.add_argument('--max', type=int, default=20000)
ap.add_argument('--stage', type=int, default=1)
a = ap.parse_args()

import harness
harness.aerr_core()
env = dict(os.environ, BRAWLER_AERR='1'); env.pop('BRAWLER_CORE', None)
procs = {}
for sys_ in ('mvs-mvs', 'uni-aes'):
    out = os.path.join(a.out, sys_); os.makedirs(out, exist_ok=True)
    procs[sys_] = subprocess.Popen([sys.executable, os.path.join(HERE, 'fpga_playthrough.py'), '--rom', a.rom, '--game', a.game,
                                    '--build', a.build, '--sys', sys_, '--out', out, '--attract', str(a.attract),
                                    '--max', str(a.max), '--stop-after-stage', str(a.stage), '--aerr', '1'],
                                   env=env, stdout=open(os.path.join(out, 'log.txt'), 'w'), stderr=subprocess.STDOUT)

syms = []                                                # (addr, name) of the ELF's symbols, for the report
try:
    for ln in subprocess.run(['m68k-linux-gnu-nm', '-n', os.path.join(a.game, a.build, 'rom.elf')], capture_output=True,
                             text=True).stdout.splitlines():
        f = ln.split()
        if len(f) == 3 and f[1] in 'tTdDbBrR': syms.append((int(f[0], 16), f[2]))
except FileNotFoundError: pass
addrs = [s[0] for s in syms]
def sym(x):
    i = bisect.bisect_right(addrs, x) - 1
    return f'{syms[i][1]}+{x - syms[i][0]:#x}' if i >= 0 else '?'

bad = False
for sys_, p in procs.items():
    rc = p.wait(); out = os.path.join(a.out, sys_)
    if rc: print(f'{sys_}: fpga_playthrough failed (rc {rc}): {out}/log.txt'); bad = True; continue
    r = json.load(open(os.path.join(out, 'run.json')))
    n = r.get('odd_access_count')
    play = any(k[0] == 1 for k, f in r['screens'])
    faults = [f for f in r['faults'] if f[0] >= 600 and 'odd-address' not in f[1]]   # (the BIOS's boot: ticks stall)
    ok = n == 0 and play and not faults
    bad |= not ok
    print(f'{sys_}: {"OK" if ok else "FAIL"}: {r["frames"]} frames, odd accesses {n}, play reached {play}, faults {faults[:5]}')
    for x in r.get('odd_access', [])[:40]:
        print(f'    {"read " if x[1] else "write"} {x[0]:#08x} ({sym(x[0])}) by PPC {x[3]:#08x} ({sym(x[3])})')
print('ALL OK' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
