#!/usr/bin/env python3
"""Proof of Haohmaru's launcher finisher (voice note 20261011-132230-5d29, Bruno: "for the launcher finisher, use the far
B motion from Haohmaru", then reopened: "use the down + A+B animation instead"): last hit + up = his SS2 crouching A+B
(anim 280 = $118, the brawler's spare name atk_cd_crouch; game.json finishers.up, compiled from the Assembly answer
fin_up by arb_compile.py), the finisher that launches (finishers.launcher = "up").

    python3 launcher_proof.py [OUT.json]

The Chain Lab (harness.py, the repo's core; scenario.py's lab setup) against Ryo 40 px away: A, A, then up + A (the
chain's third press with up); per frame P1's state / move, the dummy's state / height / life. Checks: the third press
plays finishers.up (as the finisher: after the chain's two), it hits, the dummy leaves the floor (launched: height > 0)
and lands. Then the chain's middle press (atk_b_far as a link, no up) for comparison: it does not launch."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness as H, scenario as SC, export_bm

M = export_bm.MOVES
HAO = next(r for r in json.load(open(H.GAME if H.GAME.endswith('.json') else os.path.join(H.GAME, 'game.json')))['roster']
           if r['name'] == 'haohmaru')
UP = HAO['finishers']['up']                               # the launcher's move (atk_cd_crouch = SS2 crouching A+B $118)
D = 2                                                     # the lab's dummy: the first enemy slot (main.c lab_start)
def run(b, keys):
    SC.setup(b, {'setup': {'mode': 'lab', 'fighter': 'haohmaru', 'dummy': 'ryo', 'gap': 40}})
    log, t = [], 0
    for part in keys.split(','):
        n, k = part.split(':')
        for _ in range(int(n)):
            b.run(1, p1='' if k == '-' else k)
            a = b.fget(0, 'anim')
            log.append({'t': t, 'p1': b.states[b.fget(0, 'state')], 'move': M[a] if a < len(M) else a,
                        'node': b.fget(0, 'node'), 'dummy': b.states[b.fget(D, 'state')], 'y': round(b.fget(D, 'y'), 1),
                        'hp': b.fget(D, 'hp')})
            t += 1
    return log

def main():
    b = H.Brawler(); b.game = H.GAME
    fin = run(b, '2:a,10:-,2:a,10:-,2:Ua,180:-')
    link = run(b, '2:a,10:-,2:a,90:-')
    t3 = 24                                               # the third press
    third = [r for r in fin if r['t'] >= t3]
    n2 = next(r['node'] for r in fin if r['t'] == t3 - 1)  # the second press's node (still playing at the third press)
    moves = [r['move'] for r in third if r['p1'] == 'ATTACK' and r['node'] != n2]
    hp0 = next(r['hp'] for r in fin if r['t'] == t3 - 1)
    res = {'finishers_up': UP, 'anim': HAO['moves'].get(UP), 'third_press_move': moves[0] if moves else None,
           'hit': any(r['hp'] < hp0 for r in third),
           'max_height': max(r['y'] for r in third), 'dummy_states': list(dict.fromkeys(r['dummy'] for r in third)),
           'landed': any(r['y'] == 0 for r in third[[r['y'] for r in third].index(max(r['y'] for r in third)):]),
           'link_far_b_max_height': max(r['y'] for r in link if r['t'] >= 12)}
    res['ok'] = res['third_press_move'] == UP and res['hit'] and res['max_height'] > 0 and res['landed'] and \
        res['link_far_b_max_height'] == 0
    print(json.dumps(res))
    if len(sys.argv) > 1: json.dump({'result': res, 'finisher': fin, 'link': link}, open(sys.argv[1], 'w'))
    print('OK' if res['ok'] else 'FAIL')
    sys.exit(0 if res['ok'] else 1)

if __name__ == '__main__':
    main()
