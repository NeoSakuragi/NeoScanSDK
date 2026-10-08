#!/usr/bin/env python3
"""Revamp phase 2: the damage tiers (game.json "tiers", fighter.c "damage tiers"), measured in our emulator's core (harness,
the Chain Lab's training: P1 = the fighter, a dummy that never attacks).

Per roster fighter, per move: its six C slots' specials (each distinct special once), its fury (D) and its MAX (down+D in
the red state; a fighter without a MAX of its own plays its fury as the MAX): P1 fires it at the dummy standing DISTS px
ahead (full meter), the dummy's life lost from the press until P1 stood 90 frames out of the move (its objects
included) is summed (its life put back high every frame, so it never dies; the lab's refill of an idle dummy to 60
counted from 60); the move's total = the best of the distances (its full connect); 0 = it never hits (a counter, a
dodge, a follow-up's opener: no tier). Air specials on A (free dives), the down attack and follow-up presses are not
measured (a follow-up's part deals the same scaled damage).

    python3 damage_tiers.py OUT.json [--raw] [FIGHTER ...]
--raw: the build's tier table switched off (RAM dtier_off = 1: every scale 1), the moves' source damage; written
to tools/brawler/damage_raw.json by `--raw --save`, which build_tables.py turns into the per-move scales."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from labdrive import Lab, PACK_STAT_OFF

args = [a for a in sys.argv[1:] if not a.startswith('--')]
OUT, only = args[0], args[1:]
RAW, SAVE = '--raw' in sys.argv, '--save' in sys.argv
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json'))); M = G['meter']
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
SLOT_DIR = {'D': '', 'fD': 'R', 'dD': 'D', 'uD': 'U', 'dfD': 'DR', 'ufD': 'UR'}
HIGH = 2000
DISTS = (24, 40, 70, 110, 160, 200)                           # px from P1 to the dummy: the best is the full connect
L = Lab(); b = L.b; ST = b.states
NEW = 'dtier_off' in b.syms                                   # a phase-2 build (the tier table, P1's life knob)

def st(i=0): return ST[b.fget(i, 'state')]
def settle():
    for _ in range(1500):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'shot'): return
        b.run(1)
    raise RuntimeError('P1 never idle: ' + b.brief((0, 2)))

def fire(keys, dist, low):
    settle()
    if NEW:
        b.w(L.lab + PACK_STAT_OFF + 1, 1, 1)                     # lab.p1_life: P1's life left to the game
        b.fset(0, 'hp', 10 if low else 60)
    b.fset(0, 'meter', M['max']); b.fset(0, 'meter_t', 0)
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 60
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30); b.fset(0, 'facing', 1); b.fset(2, 'hp', HIGH); b.run(2)
    b.fset(2, 'hp', HIGH)
    total, started, out, sid, six = 0, None, 0, None, None
    for f in range(1500):
        b.run(1, p1=keys if f < 2 else '')
        hp = b.fget(2, 'hp')
        total += (60 - hp) if hp <= 60 else (HIGH - hp)     # (the lab refills an idle dummy to 60 before combat)
        b.fset(2, 'hp', HIGH)
        if st(0) == 'SPECIAL':
            if started is None: started = f; sid, six = b.fget(0, 'spec_id'), b.fget(0, 'spec_ix')
            out = 0
        elif started is not None:
            out += 1
            if out >= 90 and not b.fget(0, 'shot'): break
        elif f > 40: break
    if NEW: b.w(L.lab + PACK_STAT_OFF + 1, 1, 0); b.fset(0, 'hp', 60)
    return total, started is not None, sid, six

def measure(keys, low=False):
    best, got = 0, None
    for d in DISTS:
        t, ok, sid, six = fire(keys, d, low)
        if ok: got = (sid, six)
        best = max(best, t)
    return best, got

if NEW and RAW: b.w(b.syms['dtier_off'], 1, 1)              # (written again after each start: RAM is the game's)
res = {}
names = [r['name'] for r in G['roster']]
for ci, name in enumerate(names):
    if only and name not in only: continue
    R = G['roster'][ci]; F = CL['fighters'][ci]
    pool = [p['input'] for p in F['pool']]
    L.start(ci, 1 if ci == 0 else 0); b.run(30)
    if NEW and RAW: b.w(b.syms['dtier_off'], 1, 1)
    r = res[name] = {'archetype': R.get('archetype'), 'specials': {}, 'fury': None, 'max': None}
    seen = set()
    for slot, dk in SLOT_DIR.items():
        kof = R['specials'].get(slot)
        if not kof or kof in seen: continue
        seen.add(kof)
        t, got = measure(dk + 'c')
        r['specials'][kof] = {'slot': slot, 'damage': t, 'ix': pool.index(kof) if kof in pool else None, 'played': got}
    if R.get('fury'):
        t, got = measure('d'); r['fury'] = {'input': R['fury'], 'damage': t, 'played': got}
        form = R.get('form')
        if not (form and form['trigger'] == 'down+D full meter'):
            t, got = measure('Dd', low=True)
            mx = R.get('max') if R.get('max') in pool else 'MAX ' + R['fury'] if 'MAX ' + R['fury'] in pool else R['fury']
            r['max'] = {'input': mx, 'damage': t, 'played': got}
    print(name, json.dumps(r), flush=True)
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
json.dump(res, open(OUT, 'w'), indent=1)
if SAVE: json.dump(res, open(os.path.join(HERE, 'damage_raw.json'), 'w'), indent=1)
