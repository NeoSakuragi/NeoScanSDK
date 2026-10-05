#!/usr/bin/env python3
"""TODO #74: the follow-up specials read from the ROM (handlers98 FOLLOW_CHECKS: Iori's 214A Aoi Hana in KOF98, K''s
236C Ein Trigger and 623C Crow Bites in KOF99), proven two ways.

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
# (fighter, game, cid, input, slot, the link inputs' game events, the press frames swept, a frame inside the window)
MOVES = [('iori', 'kof98', 27, '214A', 'ufD', {'again': RC.FOLLOW_KOF[('iori', 'again')]}, range(3, 32), 10),
         ('k_dash', 'kof99', 0, '236C', 'D', {'fA': RC.FOLLOW_KOF[('k_dash', 'fA')], 'fAB': RC.FOLLOW_KOF[('k_dash', 'fAB')]}, range(4, 26), 14),
         ('k_dash', 'kof99', 0, '623C', 'dD', {'fA': RC.FOLLOW_KOF[('k_dash', 'fA')], 'fAB': RC.FOLLOW_KOF[('k_dash', 'fAB')]}, range(10, 56, 3), 30)]

def seq(states):
    return [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]

def kof_vs_model(game, cid, inp, follow):
    res, g, model, objs, prog = K.compare(cid, inp, 'whiff', False, quiet=True, game=game, follow=follow)
    n = res['frames_game']
    return {'ok': res['by']['frame'] == 0 and seq([r['state'] for r in g[:n]]) == seq([r[1] for r in model[:n]]) and len(model) - 1 == n,
            'kof': seq([r['state'] for r in g[:n]]), 'model': seq([r[1] for r in model[:len(model) - 1]]), 'frames': n,
            'mismatch': res['by']}

def part_a():
    out = []
    for name, game, cid, inp, slot, links, sweep, mid in MOVES:
        bits = H.FOLLOW_INPUTS['latch' if game == 'kof98' else 'fwdBD']
        for l, ev in links.items():                      # every press frame of each link
            for t in sweep:
                r = kof_vs_model(game, cid, inp, [(t, ev, 1 << bits.index(l))])
                out.append(dict(r, move=f'{name} {inp}', press=f'{l}@{t}')); print(out[-1], flush=True)
        if name == 'iori':                               # the third part: a second press after one at 5
            for t in range(11, 34):
                r = kof_vs_model(game, cid, inp, [(5, links['again'], 1), (t, links['again'], 1)])
                out.append(dict(r, move=f'{name} {inp}', press=f'again@5+again@{t}')); print(out[-1], flush=True)
        # every other button / direction inside the window: the game's own rule says which are a follow-up
        if name == 'iori':                                # 214 / 236 / back / nothing + each button: 214 + A or C
            tries = [(f'{mot}+{btn}', evs, 1 if mot == '214' and btn in 'ac' else 0) for btn in 'abcd' for mot, evs in
                     (('214', [(-4, 2, 'D'), (-2, 2, 'DL'), (0, 3, 'L' + btn)]), ('236', [(-4, 2, 'D'), (-2, 2, 'DR'), (0, 3, 'R' + btn)]),
                      ('b', [(-2, 2, 'L'), (0, 3, 'L' + btn)]), ('n', [(0, 3, btn)]))]
        else:                                             # each stick + each button: forward + B (link 0) or D (link 1)
            tries = [(f'{d}+{btn}', [(-2, 2, ARROW[d]), (0, 6, ARROW[d] + btn)] if d != 'n' else [(0, 6, btn)],
                      ((1 if btn == 'b' else 2 if btn == 'd' else 0) if d == 'f' else 0)) for d in 'nfbdu' for btn in 'abcd']
        for tag, evs, mk in tries:
            r = kof_vs_model(game, cid, inp, [(mid, evs, mk)])
            out.append(dict(r, move=f'{name} {inp}', press=f'{tag}@{mid}', link=mk)); print(out[-1], flush=True)
    return out

CHAINS = {('iori', '214A'): [[], [('again', 9)], [('again', 23)], [('again', 9), ('again', 17)], [('again', 9), ('again', 31)]],
          ('k_dash', '236C'): [[], [('fA', 12)], [('fAB', 20)], [('fA', 26)]],
          ('k_dash', '623C'): [[], [('fA', 20)], [('fAB', 26)], [('fAB', 40)]]}

def part_b():
    frames = json.load(open(os.path.join(GAME, 'build', 'bm_frames.json')))
    roster = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    meter = json.load(open(os.path.join(GAME, 'game.json')))['meter']['max']
    b = Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME)
    out = []
    for name, game, cid, inp, slot, links, sweep, mid in MOVES:
        m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
        h, bt = H.handler_of(cid, inp, False, game); prog = H.decode(m, h, bt)
        bits = H.FOLLOW_INPUTS['latch' if game == 'kof98' else 'fwdBD']
        rec = lambda bf: int(frames[name][bf].split(':')[1]) if bf < len(frames[name]) and frames[name][bf] else -1
        for chain in CHAINS[(name, inp)]:
            pr = {}
            for l, p in chain: pr[p] = pr.get(p, 0) | 1 << bits.index(l)
            model, _ = H.run_model(m, cid, prog, presses=pr)
            model = model[:-1]                              # its last row: the frame the program ended
            pads = [(p,) + ((RC.ROLES[slot].split(':')[1], 0) if l == 'again' else RC.FOLLOW_PAD[l]) for l, p in chain]
            runs = {}
            for branch, gap in (('whiff', None), ('close', 48)):
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
