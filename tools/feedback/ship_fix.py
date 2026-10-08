#!/usr/bin/env python3
"""Ship voice-note fixes in ONE step (Bruno 2026-10-08: "fix, and immediately build the verification scenario BEFORE
shipping"): every note must already have its recipe in tools/brawler/scenarios.json; this checks them (lint), generates
the test states on the build being published, then marks each note fixed (commit) and shipped (release) together.

    ship_fix.py --release 0.8.8 --commit SHA --note-ID "what changed" ... ID [ID ...]
    ship_fix.py --release 0.8.8 --commit SHA ID ...          (the fix note given per id with --note ID=text)

Run it right after `make -C examples/brawler publish-vps` (the states are made on examples/brawler/brawler.neo)."""
import argparse, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.join(HERE, '..', '..')
ap = argparse.ArgumentParser()
ap.add_argument('--release', required=True); ap.add_argument('--commit', required=True)
ap.add_argument('--note', action='append', default=[], help='ID=what changed (one per note)')
ap.add_argument('ids', nargs='+')
a = ap.parse_args()
notes = dict(n.split('=', 1) for n in a.note)
rec = json.load(open(os.path.join(REPO, 'tools', 'brawler', 'scenarios.json')))
missing = [i for i in a.ids if i not in rec]
if missing: sys.exit(f'no recipe in scenarios.json for: {" ".join(missing)} (write it first)')
fb = [sys.executable, os.path.join(HERE, 'fb.py')]; sc = [sys.executable, os.path.join(REPO, 'tools', 'brawler', 'scenario.py')]
subprocess.run(sc + ['backfill', '--only', ','.join(a.ids)], check=True)          # put + test states on this build + upload
for i in a.ids:
    subprocess.run(fb + ['status', i, 'fixed', '--commit', a.commit] + (['--note', notes[i]] if i in notes else []), check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(fb + ['status', i, 'shipped', '--release', a.release], check=True, stdout=subprocess.DEVNULL)
subprocess.run(sc + ['publish'], check=True, stdout=subprocess.DEVNULL)           # every other shipped note's states too
print(f'shipped in {a.release} with tests: {" ".join(a.ids)}')
