#!/usr/bin/env python3
"""Revamp 1A: the default chains' finishers MEASURED (routes.py chain_tree step 3b). The generator picks each finisher
from the fighter's pieces by their data (effect, move names); some of them never reach the victim where the chain leaves
it (a piece that passes through, a short box, a multi-hit pushed out of reach). This tool plays every roster fighter's
chain in the Chain Lab's training (our emulator's core, harness / labdrive) with each finisher direction and, for a
finisher that does not hit, tries the candidates below in order (a lab tree with that one move changed) and keeps the
first that hits: written as the fighter's game.json `finishers` override (neutral / forward / up / down_move) with
--write. Test-only pokes: the fighters' positions and the dummy's life.

    python3 chain_reach.py OUT.json [--write] [FIGHTER ...]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import routes as RT, export_bm
from labdrive import Lab

args = [a for a in sys.argv[1:] if not a.startswith('--')]
OUT, ONLY = args[0], args[1:]
WRITE = '--write' in sys.argv
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
GJ = os.path.join(GAME, 'game.json')
G = json.load(open(GJ))
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
MOVES = export_bm.MOVES
names = [r['name'] for r in G['roster']]
DIRS = {'neutral': ('', 'A'), 'forward': ('R', 'fA'), 'up': ('U', 'uA'), 'down': ('D', 'dA')}
CANDS = {'neutral': ['atk_d_close', 'atk_c_far', 'atk_d_far', 'atk_c_close', 'body_toss', 'cmd_fwd_a', 'cmd_fwd_b', 'atk_cd_close', 'atk_b_far'],
         'forward': ['body_toss', 'cmd_fwd_a', 'cmd_fwd_b', 'atk_c_far', 'atk_d_far', 'atk_d_close', 'atk_b_far'],
         'up': ['atk_d_far', 'cmd_df_c', 'cmd_df_d', 'atk_c_far', 'atk_c_close', 'atk_d_close'],
         'down': ['atk_d_crouch', 'atk_c_crouch', 'cmd_df_c', 'cmd_df_d', 'atk_d_close', 'atk_c_close', 'atk_c_far', 'atk_d_far']}
KEYNAME = {'neutral': 'neutral', 'forward': 'forward', 'up': 'up', 'down': 'down_move'}
L = Lab(); b = L.b; ST = b.states
def st(i=0): return ST[b.fget(i, 'state')]
def run(n=1, k=''): b.run(n, p1=k)

def last_builder(tree):
    nd = tree['links']['A']
    for _ in range(tree['chain']['length'] - 2): nd = nd['links']['A']
    return nd

def play(fi, d, tree):
    """the chain mashed, `d`'s stick on the last link -> (the finisher's move, damage it dealt)"""
    L.start(fi, 0 if fi else 1, list(RT.encode(tree, CL['ba'], set(CL['fighters'][fi]['has'])))); run(30)
    N = tree['chain']['length']; cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
    b.place(0, x=x0, z=30); b.place(2, x=x0 + 30, z=30); b.fset(0, 'facing', 1); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', 60); run(2)
    links = 0; prev = None; fin_dmg = 0; fin = None
    for t in range(260):
        k = (DIRS[d][0] if links == N - 1 else '') + ('a' if t % 6 < 2 and links < N else '')
        hp = b.fget(2, 'hp'); run(1, k)
        nd = b.fget(0, 'node')
        if st(0) == 'ATTACK' and nd != prev: links += 1
        if links == N and fin is None: fin = MOVES[b.fget(0, 'anim')]
        if links == N and b.fget(2, 'hp') < hp: fin_dmg += hp - b.fget(2, 'hp')
        prev = nd if st(0) == 'ATTACK' else None
        if links >= N and st(0) == 'IDLE' and t > 30: break
    return fin, fin_dmg

res = {}; changed = {}
for fi, n in enumerate(names):
    if ONLY and n not in ONLY: continue
    tree = CL['fighters'][fi]['tree']; has = set(CL['fighters'][fi]['has']); res[n] = {}
    lb = last_builder(tree)
    for d, (_, key) in DIRS.items():
        if key not in lb['links']: continue
        fin, dmg = play(fi, d, tree)
        r = res[n][d] = {'move': lb['links'][key]['move'], 'played': fin, 'damage': dmg, 'hits': dmg > 0}
        if dmg > 0: continue
        used = {lb['links'][k]['move'] for k in ('A', 'fA', 'uA', 'dA') if k in lb['links']} | set(tree['chain']['links'])   # (the
                                                         # chain's other moves last: a finisher of its own first)
        for c in [m for m in CANDS[d] if m in has and m not in used] + [m for m in CANDS[d] if m in has and m in used and m != r['move']]:
            t2 = json.loads(json.dumps(tree)); nd = last_builder(t2)
            nd['links'][key]['move'] = c
            if key == 'A' and 'bA' in nd['links']: nd['links']['bA']['move'] = c
            f2, d2 = play(fi, d, t2)
            r.setdefault('tried', []).append((c, d2))
            if d2 > 0:
                r['pick'] = c; changed.setdefault(n, {})[KEYNAME[d]] = c; break
        print(n, d, r, flush=True)
json.dump({'results': res, 'overrides': changed}, open(OUT, 'w'), indent=1)
print('overrides', changed)
if WRITE and changed:                                     # into game.json's roster[].finishers (its own line, as written)
    lines = open(GJ).read().split('\n'); cur = None
    for i, l in enumerate(lines):
        if l.startswith('   "name": '): cur = json.loads(l.split(': ', 1)[1].rstrip(','))
        if l.startswith('   "finishers": ') and cur in changed:
            fin = json.loads(l.split(': ', 1)[1].rstrip(','))
            fin.update(changed[cur]); lines[i] = '   "finishers": ' + json.dumps(fin) + ','
    open(GJ, 'w').write('\n'.join(lines))
    print('game.json written')
