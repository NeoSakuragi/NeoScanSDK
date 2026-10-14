#!/usr/bin/env python3
"""Final Fight measured in its own game (FBNeo libretro, /data/emu/harness/lr.py; study harness /data/study/ffight/scripts
lab.py): each scenario = an input script from a study state (P1 vs Bred), every frame P1's and the enemy's object
(animation entry +$20, frame record +$24, x +6, y +$A (screen-vertical incl. the depth), height +$C, ground y +$E,
facing +$2E, hp +$18, hit-stop +$17, state +3). Tells which ROM animation the game plays for each action (export_ff
MOVES), the motion (walk / jump / special / throw victim path) and gives the FF side of the proof sheets.

    python3 rec_ff.py NAME [SCENARIO ...] [--png]   -> /data/tmp/ffight/rec/NAME_SCENARIO.json (+ png/NAME_SCENARIO/NNN.png)

Buttons: B = attack, A = jump (RetroPad -> CPS1 1 / 2), RIGHT = forward (P1 faces right in the states)."""
import json, os, sys
sys.path.insert(0, '/data/study/ffight/scripts')
from lab import Lab, objrow, P
from ffl import rb, rw, rl, sw, w16
OUT = '/data/tmp/ffight/rec'
SND = {}                                                # the sound ring's last write index seen

def row(r, a):
    d = objrow(r, a); d['frame'] = rl(r, a + 0x24); d['h'] = sw(rw(r, a + 0xc)); return d

F = ('RIGHT',); BK = ('LEFT',)
def tap(btn, n=1, gap=0): return [(btn, n), ((), gap)] if gap else [(btn, n)]
def seq_chain(k, last=()):
    s = []
    for i in range(k):
        s += [(('B',) + (last if i == k - 1 else ()), 1), ((), 9 if i < k - 1 else 70)]
    return s
# scenarios: (state, dx to the enemy (None: as saved), enemy hp, input script or a callable(lab) -> frames)
SCEN = {
    'idle':    (None, 200, [((), 60)]),
    'walk':    (None, 200, [(F, 60)]),
    'walkup':  (None, 200, [(('UP',), 40), (('DOWN',), 40)]),
    'jumpn':   (None, 200, [(('A',), 1), ((), 70)]),
    'jumpf':   (None, 200, [(('A', 'RIGHT'), 1), (F, 70)]),
    'jatk_n':  (None, 200, [(('A',), 1), ((), 14), (('B',), 1), ((), 60)]),
    'jatk_f':  (None, 200, [(('A', 'RIGHT'), 1), (F, 14), (('B', 'RIGHT'), 1), (F, 60)]),
    'jatk_d':  (None, 200, [(('A',), 1), ((), 22), (('B', 'DOWN'), 1), (('DOWN',), 50)]),
    'jatk_fd': (None, 200, [(('A', 'RIGHT'), 1), (F, 22), (('B', 'DOWN'), 1), (('DOWN',), 50)]),     # (note 20261014-084234)
    'special': (None, 200, [(('A', 'B'), 1), ((), 90)]),
    'special_hit': (30, 200, [(('A', 'B'), 1), ((), 90)]),    # (the spin connecting: its hit sound, for the fury's pieces)
    'whiff':   (None, 200, [(('B',), 1), ((), 40)]),
}
def chain_scen(name, links, back=False):
    """mash: B every other frame (a fresh press as early as the game takes it); the last link's press with LEFT (back)
    once links - 1 hits have landed (Bred's hp dropped links - 1 times)"""
    def run(L, n=160):
        hits = 0; hp = None
        for f in range(n):
            e = L.log[-1]['E'] if L.log else None
            if e is not None:
                if hp is not None and e['hp'] < hp: hits += 1
                hp = e['hp']
            btn = ('B',) if f % 2 == 0 else ()
            if btn and back and hits >= links - 1: btn = ('LEFT', 'B')
            if hits >= links: btn = ()
            L.step(*btn)
    return (30, 200, run)
LINKS = {'guy': 5, 'cody': 4, 'haggar': 3}

def grab_script(act):
    """walk into Bred (RIGHT) until the hold (P1 state 2), then the action"""
    def run(L, n=260):
        grabbed = None
        for f in range(n):
            p = L.log[-1]['P'] if L.log else None
            if p and grabbed is None and p['st'] == 2: grabbed = f
            btn = ('RIGHT',) if grabbed is None else ()
            if grabbed is not None:
                k = f - grabbed
                if act == 'knees' and k in (6, 26, 46): btn = ('B',)
                if act == 'fwd' and k == 6: btn = ('RIGHT', 'B')
                if act == 'back' and 2 <= k <= 8: btn = ('LEFT', 'B') if k == 6 else ('LEFT',)
                if act == 'jump' and k == 6: btn = ('A',)
                if act == 'jumpB' and k == 6: btn = ('A',)
                if act == 'jumpB' and k in range(12, 40) and k % 3 == 0: btn = ('B',)
                if act in ('jumpBf', 'jumpBb'):          # (the piledriver with the stick held: note 20261014-084718)
                    d = ('RIGHT',) if act == 'jumpBf' else ('LEFT',)
                    btn = d + (('A',) if k == 6 else ('B',) if k in range(12, 40) and k % 3 == 0 else ())
            L.step(*btn)
    return run

def scenarios(name):
    s = dict(SCEN)
    s['chain'] = chain_scen(name, LINKS[name]); s['chain_back'] = chain_scen(name, LINKS[name], True)
    for a in ('knees', 'fwd', 'back', 'jump', 'jumpB', 'jumpBf', 'jumpBb'): s['grab_' + a] = (60, 200, grab_script(a))
    s['hit'] = ('bredhit', 200, [((), 120)])
    return s

def record(name, scen, png=None):
    st, ehp, script = scenarios(name)[scen]
    dx = st if isinstance(st, int) else (None if st is None else 30)
    state = name + '_bred'
    L = Lab(name, state, dx=dx if dx is not None else 200, ehp=ehp); SND.clear()
    if png:                                             # every frame's picture: png/<name>_<scen>/<frame>.png
        d = os.path.join(png, f'{name}_{scen}'); os.makedirs(d, exist_ok=True); step0 = L.step
        L.step = lambda *b: step0(*b, png=os.path.join(d, '%03d.png' % L.f))
    if callable(script): script(L)
    else: L.run(script)
    rows = []
    r0 = None
    for d in L.log: rows.append(d)
    out = {'fighter': name, 'scenario': scen, 'rows': [dict(f=d['f'], inp=d['inp'], P=d['P'], E=d.get('E')) for d in rows]}
    return out

def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('name'); ap.add_argument('scen', nargs='*'); ap.add_argument('--png', action='store_true'); a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    import lab as LB
    LB.objrow_orig = LB.objrow
    def objrow2(r, ad):
        d = LB.objrow_orig(r, ad); d['frame'] = rl(r, ad + 0x24); d['h'] = sw(rw(r, ad + 0xc))
        d['cam'] = rw(r, 0xFF1284); d['camy'] = rw(r, 0xFF8416)   # the scroll the sprites are drawn against ($168CC: a5 = $FF8000)
        if ad == P:                                     # the sound queue ($984: ring of 64 words at a5+388, write index
            w = rw(r, 0xFF801A); last = SND.get('w', w); out = []   # a5+26; each word's low byte = the command sent to
            while last != w:                            # the sound CPU's latch $800180, $F9: + the high byte to $800188)
                out.append(rw(r, 0xFF8184 + last)); last = (last + 2) & 0x7F
            SND['w'] = w; d['snd'] = out
        return d
    LB.objrow = objrow2
    for s in a.scen or list(scenarios(a.name)):
        o = record(a.name, s, os.path.join(OUT, 'png') if a.png else None)
        json.dump(o, open(os.path.join(OUT, f'{a.name}_{s}.json'), 'w'))
        P_ = [x['P'] for x in o['rows']]
        seq = []
        for p in P_:
            k = '%05X' % p['anim']
            if not seq or seq[-1][0] != k: seq.append([k, 1])
            else: seq[-1][1] += 1
        print(s, ' '.join(f'{k}x{n}' for k, n in seq[:30]))

if __name__ == '__main__': main()
