#!/usr/bin/env python3
"""TODO #74 / #140: the follow-up specials read from the ROM (handlers98 FOLLOW_CHECKS: Iori's 214A Aoi Hana and 623D
Kototsuki In (a hit-confirm into Aoi Hana), Kyo's 236C Dokugami (two more parts) in KOF98, K''s 236C Ein Trigger, 623C
Crow Bites and 623A (a check, no follow-up) in KOF99), proven two ways. ONLY=<fighter[ input]> runs those moves.

A. brute force in our emulator (the game) against the decoded program's model (handlers98.run_model, the press read
   FOLLOW_LAG frames after its button): every press frame of each follow-up input before, inside and after its window
   (and the second press of Iori's third part), plus every other button / direction at a frame inside the window (the
   ones the game refuses must change nothing); per run the game's states + frames against the model's (compare: 0
   frame mismatches, the same state sequence).
B. the brawler (harness, an AI_OFF=1 build) against the model: every chain (no press, each link, both links for
   Iori), facing right and left, whiff and a standing dummy 48 px ahead: the frames it shows per program frame (its
   hit-stop dropped) against the model's ROM frames, and its x mirrored between the facings.

    python3 followups_proof.py GAME_DIR [OUT]          (default OUT /data/tmp/fu74/out; OUT/proof.json)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import rom96, handlers98 as H, romspecials98 as K
import romspecials_check as RC
from harness import Brawler

GAME = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler')
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/fu74/out'
ARROW = {'n': '', 'f': 'R', 'b': 'L', 'd': 'D', 'u': 'U'}
# the game's inputs tried inside a window (facing right): each motion / stick + each button, [(offset, frames, keys)]
MOT = {'236': [(-4, 2, 'D'), (-2, 2, 'DR'), (0, 3, 'R')], '214': [(-4, 2, 'D'), (-2, 2, 'DL'), (0, 3, 'L')],
       '623': [(-4, 2, 'R'), (-2, 2, 'D'), (0, 3, 'DR')], '421': [(-4, 2, 'L'), (-2, 2, 'D'), (0, 3, 'DL')],
       '63214': [(-8, 2, 'R'), (-6, 2, 'DR'), (-4, 2, 'D'), (-2, 2, 'DL'), (0, 3, 'L')],
       '41236': [(-8, 2, 'L'), (-6, 2, 'DL'), (-4, 2, 'D'), (-2, 2, 'DR'), (0, 3, 'R')],
       'n': [(0, 3, '')], 'f': [(-2, 2, 'R'), (0, 6, 'R')], 'b': [(-2, 2, 'L'), (0, 6, 'L')], 'd': [(-2, 2, 'D'), (0, 6, 'D')],
       'u': [(-2, 2, 'U'), (0, 6, 'U')]}
# the game's rule per link (handlers98 FOLLOW_CHECKS), on (motion, button): which tries are that link
RULE = {('iori', 'again'): lambda mo, b: mo in ('214', '63214') and b in 'ac',            # 214 + A / C (+$1AD bit 6)
        ('kyo', 'again'): lambda mo, b: mo in ('214', '63214') and b in 'ac',              # '6 2 4' + A / C (214: the 6
                                                                                            # of 236C's own input still
                                                                                            # in the recogniser's window)
        ('kyo', 'fA'): lambda mo, b: mo == 'f' and b in 'ac',                             # forward + A / C ($1ED30)
        ('k_dash', 'fA'): lambda mo, b: mo == 'f' and b == 'b',                           # forward + B
        ('k_dash', 'fAB'): lambda mo, b: mo == 'f' and b == 'd'}                          # forward + D
# (a motion's last stick is held 3 frames: gone when the handler reads the press FOLLOW_LAG frames later)
# (fighter, game, cid, input, slot, [(the presses before, link, its press frames swept)], [(presses before, a frame
# inside the window)] for the tries)
MOVES = [('iori', 'kof98', 27, '214A', 'ufD', [([], 'again', range(3, 32)), ([('again', 5)], 'again', range(11, 34))],
          [([], 10)]),
         ('iori', 'kof98', 27, '623D', 'uD', [([], 'again', range(16, 46)), ([('again', 30)], 'again', range(46, 92, 2)),
                                                ([('again', 30), ('again', 70)], 'again', range(80, 116, 2))], [([], 32)], 'close'),
         ('kyo', 'kof98', 0, '236C', 'ufD', [([], 'again', range(6, 34)), ([('again', 10)], 'fA', range(14, 50))],
          [([], 10), ([('again', 10)], 30)]),
         ('k_dash', 'kof99', 0, '236C', 'D', [([], 'fA', range(4, 26)), ([], 'fAB', range(4, 26))], [([], 14)]),
         ('k_dash', 'kof99', 0, '623C', 'dD', [([], 'fA', range(10, 56, 3)), ([], 'fAB', range(10, 56, 3))], [([], 30)]),
         ('k_dash', 'kof99', 0, '623A', 'dfD', [([], 'fA', range(10, 56, 3)), ([], 'fAB', range(10, 56, 3))], [([], 30)])]
ONLY = os.environ.get('ONLY')                            # 'kyo', 'iori 623D', ...: those moves only

def seq(states):
    return [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]

def kof_vs_model(game, cid, inp, follow, branch='whiff'):
    res, g, model, objs, prog = K.compare(cid, inp, branch, False, quiet=True, game=game, follow=follow)
    n = res['frames_game']
    return {'ok': res['by']['frame'] == 0 and seq([r['state'] for r in g[:n]]) == seq([r[1] for r in model[:n]]) and len(model) - 1 == n,
            'kof': seq([r['state'] for r in g[:n]]), 'model': seq([r[1] for r in model[:len(model) - 1]]), 'frames': n,
            'mismatch': res['by']}

def moves():
    return [mv for mv in MOVES if not ONLY or ONLY in f'{mv[0]} {mv[3]}']

def part_a():
    out = []
    for name, game, cid, inp, slot, sweeps, mids, *br in moves():
        br = br[0] if br else 'whiff'                      # Iori 623D: a hit-confirm (its hit-stop latch), on hit
        links = RC.prog_links(game, cid, inp)
        ev = lambda l: RC.FOLLOW_KOF[(name, l)]
        pre_ = lambda pre: [(t, ev(l), 1 << links.index(l)) for l, t in pre]
        for pre, l, rng in sweeps:                         # every press frame of each link (after the presses before)
            for t in rng:
                r = kof_vs_model(game, cid, inp, pre_(pre) + [(t, ev(l), 1 << links.index(l))], br)
                out.append(dict(r, move=f'{name} {inp}', press='+'.join(f'{a}@{b}' for a, b in pre + [(l, t)]))); print(out[-1], flush=True)
        for pre, mid in mids:                              # every motion / stick + button inside the window: the game's
            for mo, evs in MOT.items():                    # own rule says which are a follow-up
                for btn in 'abcd':
                    e = [(o, n, k + (btn if o == 0 else '')) for o, n, k in evs]
                    mk = sum(1 << links.index(l) for (f_, l), rule in RULE.items() if f_ == name and l in links and rule(mo, btn))
                    r = kof_vs_model(game, cid, inp, pre_(pre) + [(mid, e, mk)], br)
                    out.append(dict(r, move=f'{name} {inp}', press='+'.join(f'{a}@{b}' for a, b in pre) + f' {mo}{btn}@{mid}', link=mk))
                    print(out[-1], flush=True)
    return out

CHAINS = {('iori', '214A'): [[], [('again', 9)], [('again', 23)], [('again', 9), ('again', 17)], [('again', 9), ('again', 31)]],
          ('iori', '623D'): [[], [('again', 'hit')], [('again', 'hit'), ('again', 52)], [('again', 'hit'), ('again', 52), ('again', 66)]],
          ('kyo', '236C'): [[], [('again', 10)], [('again', 10), ('fA', 30)], [('again', 25), ('fA', 40)]],
          ('k_dash', '236C'): [[], [('fA', 12)], [('fAB', 20)], [('fA', 26)]],
          ('k_dash', '623C'): [[], [('fA', 20)], [('fAB', 26)], [('fAB', 40)]],
          ('k_dash', '623A'): [[], [('fA', 20)], [('fAB', 26)]]}

def part_b():
    frames = json.load(open(os.path.join(GAME, 'build', 'bm_frames.json')))
    roster = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    meter = json.load(open(os.path.join(GAME, 'game.json')))['meter']['max']
    b = Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME)
    out = []
    for name, game, cid, inp, slot, sweeps, mids, *_ in moves():
        m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
        h, bt = H.handler_of(cid, inp, False, game); prog = H.decode(m, h, bt, cid=cid)
        bits = prog['links']
        rec = lambda bf: int(frames[name][bf].split(':')[1]) if bf < len(frames[name]) and frames[name][bf] else -1
        bh = None
        if any(p == 'hit' for ch in CHAINS[(name, inp)] for l, p in ch):   # a hit-stop latch (Iori 623D): pressed at the
            br = RC.brawler_run(b, roster.index(name), slot, 48, os.path.join(OUT, 'shots_b'), meter=meter)   # hit's frame
            bh = next(i for i in range(1, len(br)) if br[i]['hp2'] < br[i - 1]['hp2'])
        for chain in CHAINS[(name, inp)]:
            chain = [(l, bh if p == 'hit' else p) for l, p in chain]
            pr = {}
            for l, p in chain: pr[p] = pr.get(p, 0) | 1 << bits.index(l)
            pads = [(None if p == bh and bh is not None else p,) + ((RC.ROLES[slot].split(':')[1], 0) if l == 'again' else RC.FOLLOW_PAD[l])
                    for l, p in chain]
            runs = {}
            for branch, gap in (('whiff', None), ('close', 48)):
                model, _ = H.run_model(m, cid, prog, presses=pr, hits={bh} if branch == 'close' and bh is not None else ())
                model = model[:-1]                          # its last row: the frame the program ended
                for facing in (1, -1):
                    shots = os.path.join(OUT, 'shots_b'); os.makedirs(shots, exist_ok=True)
                    br = RC.brawler_run(b, roster.index(name), slot, gap, shots, meter=meter, follow=pads, facing=facing)
                    n = min(len(br), len(model))
                    near = lambda i: range(max(0, i - 1), min(n, i + 2))
                    bad = sum(1 for i in range(n) if all(rec(br[i]['frame']) != model[j][2] for j in near(i)))
                    runs[(branch, facing)] = br
                    r = {'move': f'{name} {inp}', 'chain': '+'.join(f'{l}@{p}' for l, p in chain) or 'none', 'branch': branch,
                         'facing': facing, 'model_frames': len(model), 'brawler_frames': len(br), 'frame_mismatch': bad,
                         'model_states': seq([r_[1] for r_ in model]), 'ok': bad == 0 and 0 <= len(br) - len(model) <= 1}
                    # (a hit: romspecials_check's run also keeps the frame after the move, the victim still falling)
                    if facing < 0:                          # mirrored: the same frames, x the other way
                        a, c = runs[(branch, 1)], br
                        r['mirror_frames_equal'] = [q['frame'] for q in a] == [q['frame'] for q in c]
                        r['mirror_max_dx'] = max((abs(p_['x'] - q['x']) for p_, q in zip(a, c)), default=0)
                        r['ok'] &= r['mirror_frames_equal']
                    out.append(r); print(r, flush=True)
    return out

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    a = part_a() if os.environ.get('PART', 'ab') != 'b' else []
    bb = part_b() if os.environ.get('PART', 'ab') != 'a' else []
    res = {'a_runs': len(a), 'a_ok': sum(r['ok'] for r in a), 'b_runs': len(bb), 'b_ok': sum(r['ok'] for r in bb),
           'a': a, 'b': bb}
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print(f"A (game vs model): {res['a_ok']} / {res['a_runs']} ok; B (brawler vs model, both facings): {res['b_ok']} / {res['b_runs']} ok")
