#!/usr/bin/env python3
"""Garou's numbers for Rock, measured in our emulator (cap_garou): per move the frames (the ROM timeline), the frame it
first hits, the hit-stop (the frames the attacker stays on one step beyond the ROM timeline when it connects), the
damage (the victim's life +$8E, 120 full), the victim's reaction animation; walk / run / jump physics from the velocity
registers.

    python3 numbers_garou.py   -> /data/neogeo_dict/garou/rock_numbers.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cap_garou import Garou, STA, VS
from check_timeline import seq
import export_garou as X

OUT = '/data/neogeo_dict/garou/rock_numbers.json'
LIFE2 = 0x10058E
# move -> (state, script); the close normals from close.state, the far ones from vs.state (160 px: far A / B reach)
CASES = {'far A': ('close', seq('A')), 'far B': ('close', seq('B')), 'close C': ('close', seq('C')), 'close D': ('close', seq('D')),
         'crouch A': ('close', seq('2A')), 'crouch B': ('close', seq('2B')), 'crouch C': ('close', seq('2C')),
         'crouch D': ('close', seq('2D')), 'far C': ('vs', '12:R,4:c'), 'far D': ('vs', '12:R,4:d'),
         '6A': ('close', seq('6A')), '6B': ('close', seq('6B')),
         '236A': ('close', seq('236A')), '236C': ('close', seq('236C')), '28A': ('close', '45:D,4:Ua'),
         '28C': ('close', '45:D,4:Uc'), '214A': ('close', seq('214A')), '214C': ('close', seq('214C')),
         '214B': ('vs', seq('214B')), '214D': ('vs', seq('214D')),
         '236236A': ('close', seq('236236A')), '236236C': ('close', seq('236236C')),
         '236236B': ('vs', seq('236236B')), '236236D': ('vs', seq('236236D')),
         'throw': ('close', '12:R,4:Rc')}
NEUTRAL = {0, 1, 2, 3, 4, 6, 7}

def measure(g, st, s, poke):
    g.load(open(f'{STA}/{st}.state', 'rb').read())
    if poke: g.w(0x1004BE, 1, 0x80)
    life0 = g.r(LIFE2, 1); rows = g.play('1:,' + s + ',200:')
    i0 = next((i for i, r in enumerate(rows) if r['P1']['anim'] not in NEUTRAL), None)
    if i0 is None: return None
    rows = rows[i0:]
    hits, prev = [], life0
    for i, r in enumerate(rows):
        lf = r['P2']['raw'][0x8E]
        if lf < prev: hits.append({'frame': i, 'damage': prev - lf, 'react': f"{r['P2']['anim']:X}"})
        prev = lf
    # hit-stop: from the first hit frame, the frames P1 stays on one (anim, step, tick) beyond the timeline's own
    stop = None
    if hits:
        h = hits[0]['frame']; k = h
        same = lambda a, b: (a['anim'], a['step'], a['tick']) == (b['anim'], b['step'], b['tick'])
        while k + 1 < len(rows) and same(rows[k + 1]['P1'], rows[h]['P1']): k += 1
        stop = k - h
    anims = list(dict.fromkeys(r['P1']['anim'] for r in rows if r['P1']['anim'] not in NEUTRAL))
    return {'anims': [f'{a:X}' for a in anims], 'rom_frames': sum(len(X.timeline(1, a)) for a in anims[:1]),
            'hits': hits, 'damage': life0 - rows[-1]['P2']['raw'][0x8E], 'hitstop': stop}

def physics(g):
    out = {}
    g.load(open(VS, 'rb').read()); r = g.play('40:R'); out['walk_fwd_vx'] = r[-1]['P1']['vx']
    g.load(open(VS, 'rb').read()); r = g.play('40:L'); out['walk_back_vx'] = r[-1]['P1']['vx']
    g.load(open(VS, 'rb').read()); r = g.play('3:R,3:,30:R'); out['run_vx'] = r[-1]['P1']['vx']
    g.load(open(VS, 'rb').read()); r = g.play('3:U,60:')
    out['jump'] = [[round(x['P1']['h'], 3), round(x['P1']['vh'], 4), x['P1']['anim']] for x in r if x['P1']['h'] > 0 or x['P1']['anim'] == 8]
    g.load(open(VS, 'rb').read()); r = g.play('3:UR,60:')
    out['jump_fwd_vx'] = max(x['P1']['vx'] for x in r)
    out['jump_frames'] = sum(1 for x in r if x['P1']['h'] > 0)
    return out

def main():
    g = Garou(); res = {'physics': physics(g), 'moves': {}}
    print('physics', {k: v for k, v in res['physics'].items() if k != 'jump'})
    for k, (st, s) in CASES.items():
        m = measure(g, st, s, k.startswith('236236'))
        res['moves'][k] = m
        print(f'{k:10s}', m and {kk: m[kk] for kk in ('anims', 'damage', 'hitstop')}, m and [(h['frame'], h['damage'], h['react']) for h in m['hits']])
    json.dump(res, open(OUT, 'w'), indent=1)

if __name__ == '__main__': main()
