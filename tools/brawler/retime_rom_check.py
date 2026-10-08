#!/usr/bin/env python3
"""Retiming from the ROM's own table (build_tables.py gretime_rom, game.json roster[].retime): every entry of
build/retime.json played in the brawler (Chain Lab training, the dummy out of reach, rt_tab left 0) and its segments
measured frame by frame = its targets (retime_proof.py's checks: events in order, each segment's first source frame
shown, the place on every settled frame = the source's at that frame)

    python3 retime_rom_check.py OUT.json [GAME_DIR]   (a build with retime entries)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness, retime_proof as P

ROLE_KEYS = {'D': 'c', 'fD': 'Rc', 'dD': 'Dc', 'uD': 'Uc', 'dfD': 'DRc', 'ufD': 'URc'}

def main(out, game=harness.GAME):
    G = json.load(open(os.path.join(game, 'game.json'))); names = [r['name'] for r in G['roster']]
    lab = json.load(open(os.path.join(game, 'build', 'chainlab.json'))); ba = lab['ba']
    F = {f['name']: f for f in lab['fighters']}
    ents = json.load(open(os.path.join(game, 'build', 'retime.json')))
    b = harness.Brawler(game=game, tick_sync=True); res = []
    for e in ents:
        r = G['roster'][names.index(e['fighter'])]
        special = e['move'] not in ba
        if special:
            role = next((k for k, v in r['specials'].items() if v == e['move']), None)
            if role is None: print('skip (not on a role):', e['fighter'], e['move']); continue
            keys = ROLE_KEYS[role]
        else: keys = 'a'                                   # (a normal: the A route's first node; others skipped)
        start = P.training(b, names, e['fighter'])
        b.load(start); src = None
        tr = P.play(b, start, keys, None, [])               # the ROM's table (rt_tab 0)
        fr, af = P.move_frames(tr, special)
        if not special and ba[fr[0]['anim']] != e['move']: print('skip (not the A route\'s first node):', e['fighter'], e['move']); continue
        steps = None if special else F[e['fighter']]['moves'][e['move']]['steps']
        seg = P.RT.segments(P.active(fr, special, steps))
        ok = seg == e['targets'] and len(fr) == sum(e['targets'])
        print('OK ' if ok else 'BAD', e['fighter'], e['move'], 'segments', e['segments'], '-> played', seg, 'target', e['targets'], flush=True)
        res.append({'entry': e, 'played': seg, 'ok': ok})
    json.dump(res, open(out, 'w'), indent=1)
    print('all ok:', all(x['ok'] for x in res), len(res))

if __name__ == '__main__':
    main(sys.argv[1], *(sys.argv[2:3]))
