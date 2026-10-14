#!/usr/bin/env python3
"""Hurt voice proof (note 20261014-170634-5d29, game.json hit_sounds.hurt_voice): a chain, a launcher and a KO in the
Chain Lab, every sound command the 68000 sends logged per frame (REG_SOUND $320000): the voices (prefix $1C / $1B the
player's, $1E / $17 the enemy's, + code) and the effects ($1A + code: the impact sounds), with the victim's state, height
and life at that frame. A hurt voice = the victim's VK_HIT code (build/snd/voices.h is the code map; the dummy's codes
are told by their prefix).

    python3 hurtvoice_proof.py OUT.json [ROM]"""
import ctypes as C, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario

CASES = [   # name, scenario setup (scenario.py), keys, the victim's fighter index
    ('chain', {'mode': 'lab', 'fighter': 'terry', 'dummy': 'ryo', 'gap': 60}, '3:a,9:-,3:a,9:-,3:a,9:-,3:b,9:-,3:b,9:-,3:c,120:-', 2),
    ('launcher', {'mode': 'lab', 'fighter': 'kyo', 'dummy': 'ryo', 'gap': 50, 'drive': 'full', 'fury': 'full'}, '2:Dc,14:-,2:Dc,150:-', 2),
    ('ko', {'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 4, 'wait': 240, 'alone': True, 'foe': 6, 'foe_hp': 6, 'gap': 40},
     '3:a,9:-,3:a,9:-,3:c,240:-', 6),                     # a minion's death (its KO voice at S_DEAD)
]
VPFX = {0x1C: 'P1 voice', 0x1B: 'P1 voice2', 0x1E: 'enemy voice', 0x17: 'enemy voice2', 0x1A: 'sfx'}

def main(out, rom=None):
    b = H.Brawler(rom=rom, options=scenario.SYSTEMS['mvs-mvs']) if rom else H.Brawler(options=scenario.SYSTEMS['mvs-mvs'])
    b.game = H.GAME
    raw = []
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): raw.append((b.frame, v & 0xFF if s == 1 else v >> 8))
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt)
    res = {}
    for name, st, keys, vi in CASES:
        b.core.retro_neoscan_m68k_write_tap(C.cast(None, type(WT)))
        scenario.setup(b, {'setup': st})
        del raw[:]; f0 = b.frame; rows = []
        b.core.retro_neoscan_m68k_write_tap(WT)
        def each(bb):
            rows.append((bb.frame - f0, bb.states[bb.fget(vi, 'state')], round(bb.fget(vi, 'y'), 1), bb.fget(vi, 'hp')))
        for part in keys.split(','):
            n, k = part.split(':'); b.run(int(n), k.replace('-', ''), '', each)
        b.core.retro_neoscan_m68k_write_tap(C.cast(None, type(WT)))
        ev, i = [], 0
        while i + 1 < len(raw):                            # prefix + code pairs (snd_cmd: the bytes go one per frame)
            f, p = raw[i]
            if p in VPFX: ev.append({'frame': f - f0, 'kind': VPFX[p], 'code': '%02X' % raw[i + 1][1]}); i += 2
            else: ev.append({'frame': f - f0, 'kind': 'cmd', 'code': '%02X' % p}); i += 1
        st_at = {r[0]: r for r in rows}
        for e in ev:
            r = st_at.get(e['frame']) or st_at.get(e['frame'] - 1)
            if r: e['victim'] = {'state': r[1], 'y': r[2], 'hp': r[3]}
        hits = [{'frame': f - f0, 'victim': v, 'lost': d, 'state': s} for f, v, d, s in b.hits if f > f0 and v == vi]
        b.hits.clear() if hasattr(b.hits, 'clear') else None
        res[name] = {'keys': keys, 'events': ev, 'hits': hits, 'raw': [(f - f0, '%02X' % v) for f, v in raw], 'victim_track': rows,
                     'enemy_voices': [e for e in ev if e['kind'].startswith('enemy')],
                     'impacts': [e for e in ev if e['kind'] == 'sfx']}
        print(f"{name}: {len(hits)} hits, {len(res[name]['impacts'])} effect sounds, enemy voices at",
              [(e['frame'], e['code'], e.get('victim', {}).get('state')) for e in res[name]['enemy_voices']])
    json.dump(res, open(out, 'w'), indent=1)

if __name__ == '__main__': main(*sys.argv[1:])
