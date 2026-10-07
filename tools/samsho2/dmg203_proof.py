#!/usr/bin/env python3
"""TODO #203 proof: damage per hit in the brawler, SS2 fighters (Haohmaru, Genjuro, Kuroko, Hanzo SS2) vs KOF fighters
(Terry, Kyo), all on the same training dummy (roster 1, Ryo) in the Chain Lab's training mode (labdrive), our emulator's
core (harness). Per fighter and move class: the hits the dummy took (life lost each, from the harness's hit log).

    python3 dmg203_proof.py OUT.json [FIGHTER ...]
    python3 dmg203_proof.py --table BEFORE.json AFTER.json OUT.txt     the before / after table (total, hits)

Classes: chain (A from far, A every 12 frames), close (cA chain), sweep (down+A), toss (forward+A), launch (far A, far
A, down-forward+A), each C slot (special), D (fury), down+D (MAX fury), throw (walk in, forward+A / back+A)."""
import json, os, sys
if sys.argv[1] == '--table':
    B_, A_ = (json.load(open(x)) for x in sys.argv[2:4]); lines = []
    for name in A_:
        lines.append(name + ('  (KOF98, damage 1)' if name in ('terry', 'kyo') else '  (SS2, game.json damage 3)'))
        for k in A_[name]:
            b, a = B_[name][k], A_[name][k]
            lines.append(f'  {k:18s} before {b["total"]:3d} {str(b["hits"]):28s} after {a["total"]:3d} {a["hits"]}')
    open(sys.argv[4], 'w').write('\n'.join(lines) + '\n'); print('\n'.join(lines)); sys.exit(0)
HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, B); sys.path.insert(0, os.path.join(B, 'chainlab'))
from labdrive import Lab

OUT = sys.argv[1]
GAME = os.path.join(B, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json')))
names = [r['name'] for r in G['roster']]
only = sys.argv[2:] or ['terry', 'kyo', 'haohmaru', 'genjuro', 'kuroko', 'hanzo_ss2']
DUMMY = names.index('ryo')
L = Lab(); b = L.b; ST = b.states


def st(i=0): return ST[b.fget(i, 'state')]
def run(n, k=''): b.run(n, p1=k)


def settle():
    for _ in range(1500):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'shot') and not b.fget(0, 'flash') and not b.fget(0, 'chain_t'): break
        run(1)
    b.fset(2, 'hp', 60); run(1)


def setpos(dist):
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30); b.fset(0, 'facing', 1); run(2)


def measure(dist, script, n_after=200, walk=False):
    settle(); setpos(dist); b.hits.clear()
    if walk:
        for _ in range(60):
            if st(0) == 'GRAB': break
            run(1, 'R')
        if st(0) != 'GRAB': return {'hits': [], 'total': 0, 'note': 'no grab (' + st(0) + ')'}
        run(4)
    for part in script.split(','):
        n, k = part.split(':')
        for _ in range(int(n)):
            run(1, k)
            if b.fget(2, 'hp') < 10: b.fset(2, 'hp', 60)      # (never a KO: the dummy refilled, the log keeps the hits)
    for _ in range(n_after):
        run(1)
        if b.fget(2, 'hp') < 10: b.fset(2, 'hp', 60)
    hits = [h[2] for h in b.hits if h[1] == 2 and h[2] > 0]
    return {'hits': hits, 'total': sum(hits)}


CHAIN = ','.join(['3:a,9:-'] * 7)
TESTS = [('chain A (far)', 70, CHAIN), ('chain cA (close)', 26, CHAIN), ('sweep dA', 40, '3:Da'), ('toss fA', 40, '3:Ra'),
         ('launch A,A,dfA', 70, '3:a,9:-,3:a,9:-,3:DRa'),
         ('C', 60, '3:c'), ('fC', 60, '3:Rc'), ('dC', 60, '3:Dc'), ('uC', 60, '3:Uc'), ('dfC', 60, '3:DRc'), ('ufC', 60, '3:URc'),
         ('fury D', 60, '3:d'), ('MAX down+D', 60, '3:Dd')]
if __name__ == '__main__':
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for name in only:
        ci = names.index(name); L.start(ci, DUMMY); run(30); r = res[name] = {}
        for label, dist, script in TESTS:
            r[label] = measure(dist, script, 700 if label.startswith(('fury', 'MAX')) else 200)
        r['throw f'] = measure(4, '3:Ra', 250, walk=True)
        r['throw b'] = measure(4, '3:La', 250, walk=True)
        print(name, {k: (v['total'], v['hits']) for k, v in r.items()}, flush=True)
        json.dump(res, open(OUT, 'w'), indent=1)
