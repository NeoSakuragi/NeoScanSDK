#!/usr/bin/env python3
"""Proof of the brawler's projectiles against the games: every roster fighter's D projectile (export_bm.pick_specials,
bspec_t.proj) played in the brawler (harness.py, `make AI_OFF=1` build, the fighter picked on the select screen; the
enemies' intents written by the test) next to the game's measurements of the same move (tools/kof96/projectiles96.py:
our emulator, P2 held off the ground / standing 60, 120, 200 px ahead).

    python3 check_projectiles.py [game:name ...]        (default: the roster of examples/brawler/game.json)

Per projectile, brawler / game:
  spawn      frame of the special's script it appears on (row 0 = the special's first frame)
  speed      px per frame once it flies
  free       nobody in reach: its life (frames), travel (px from its spawn point), the screen x it died at (x - camera:
             off screen at >= 384, the games' own test) or 'end' (its animation ended)
  owner hit  its thrower is punched (enemy 3 behind it, A) once it flies: still alive / its travel when it died
  60/120/200 enemy 2 standing that far ahead: hits, frame of the first (script rows), its travel at the hit, and what
             it did after the hit (end: a travelling one plays its end in place; spent: an eruption plays on)
  clash      an enemy with a projectile throws it from 250 px at the same time: both end, nobody hit"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export_bm, export96, projectiles96
from harness import Brawler

X0, Z0 = 150, 32                                 # thrower's place
FAR = (1000, 0)                                  # the others: out of the way (other end of the stage, back line)

def chars_from_makefile():                       # the roster of examples/brawler/game.json (bm_chars order)
    import build_tables
    return build_tables.chars(build_tables.load(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))

def picked(specs):
    """game:name -> (special input, its game projectile definitions) of the D role"""
    out, games = {}, {}
    for s in specs: g, n = s.split(':'); games.setdefault(g, []).append(n)
    for g, names in games.items():
        ex = export96.export(names, '/tmp/check_projectiles', g, only={'idle', 'specials'})
        cast = {'kof98': export96.CAST98, 'kof99': export96.CAST99}.get(g, export96.CAST)
        for n in names:
            sp = export_bm.pick_specials(ex['characters'][n], n)[0]
            if sp is not None and export_bm.real_projectile(sp):
                out[f'{g}:{n}'] = (sp['input'], projectiles96.definitions(g, cast.index(n))[sp['input']])
    return out

def mine(b, i):
    """projectile entity i is an independent projectile in flight (S_PROJ with a definition)"""
    return b.pget(i, 'state') == b.states.index('PROJ') and b.pget(i, 'pdef') != 0

def is_child(b, i):
    """entity i plays a trail (a bproj_t that is some projectile's child: its definition has no kind)"""
    if not hasattr(b, 'trails'):                  # the trails' bproj_t symbols (export_bm: <name>_pj<k>_<j>c)
        b.trails = {a for n, a in b.syms.items() if re.search(r'_pj\d+_\d+c$', n)}
    return mine(b, i) and b.pget(i, 'pdef') in b.trails

def trial(b, k, dist=None, owner_hit=False, clash=None, frames=200, spawn_row=None):
    """fighter k (bm_chars index, picked on the select screen) throws its D special; dist: enemy 2 standing that far
    ahead; owner_hit: enemy 3 punches the thrower once its projectile flies; clash: enemy slot that throws its own D
    from 250 px at the same time"""
    b.pick(k)
    for i in range(2, 8): b.place(i, *FAR)
    b.place(0, X0, Z0); b.fset(0, 'facing', 1)
    if dist is not None: b.place(2, X0 + dist, Z0)
    if clash is not None: b.place(clash, X0 + 250, Z0); b.fset(clash, 'facing', -1)
    b.run(20)                                     # the camera settles
    b.hits = []
    if clash is not None: b.intent(clash, press=16, face=-1)   # IN_SP: its A+B special (TODO #71)
    b.run(1, p1='ab')                     # A+B together: the special at once
    if clash is not None: b.intent(clash)
    r = {'spawn': None, 'xs': [], 'end': None, 'sx': None, 'outlived': False, 'hit': None, 'after': None, 'owner': None,
         'others': set(), 'trail': 0, 'trail_x': []}
    t0 = slot = None; hp2 = b.fget(2, 'hp'); punched = None
    for t in range(frames):
        st = b.states[b.fget(0, 'state')]
        if t0 is None and st == 'SPECIAL': t0 = b.frame + 1      # the frame the script's row 0 shows
        if slot is None:
            for i in range(4):
                if mine(b, i) and not is_child(b, i) and b.pget(i, 'owner') == b.base: slot = i; r['spawn'] = b.frame - t0
        for i in range(4):
            if i != slot and mine(b, i) and not is_child(b, i): r['others'].add(i)
            if is_child(b, i) and b.pget(i, 'state_t') == 0 and r['xs'] and r['end'] is None:   # a trail born this frame
                r['trail'] += 1; r['trail_x'].append(round(b.pget(i, 'x') - b.pget(slot, 'x'), 1))
        if slot is not None and r['end'] is None:
            if slot is not None and mine(b, slot) and is_child(b, slot): slot = None; continue
            if not mine(b, slot) or b.pget(slot, 'pend') == 1:
                r['end'] = 'end' if mine(b, slot) else 'gone'
                if not r['xs']: r['xs'].append(b.pget(slot, 'x'))
                cam = b.r(b.syms['cam_x'], 2); r['sx'] = round(r['xs'][-1] - cam, 1)
                if r['owner'] == 'hit': r['owner'] = round(r['xs'][-1] - r['xs'][0], 1)
            else:
                r['xs'].append(b.pget(slot, 'x'))
                if st != 'SPECIAL': r['outlived'] = True
                if owner_hit and punched is None and len(r['xs']) == 2:
                    punched = b.frame; b.place(3, X0 - 40, Z0); b.fset(3, 'facing', 1); b.intent(3, press=1, face=1)
                elif punched is not None and b.frame == punched + 1: b.intent(3)
                if owner_hit and st in ('HITSTUN', 'KNOCKDOWN') and r['owner'] is None: r['owner'] = 'hit'
        hp = b.fget(2, 'hp')
        if hp < hp2 and r['hit'] is None and (slot is not None or (t0 is not None and spawn_row is not None and b.frame - t0 >= spawn_row)):
            r['hit'] = (b.frame - t0, round(r['xs'][-1] - r['xs'][0], 1) if r['xs'] else 0.0)   # (a projectile without end
            if slot is None: r['after'] = 'gone'          # rows goes on the frame it hits: Iori's, as in KOF98)
        if r['hit'] is not None and r['after'] is None and slot is not None:
            r['after'] = 'end' if mine(b, slot) and b.pget(slot, 'pend') == 1 else 'spent' if mine(b, slot) and b.pget(slot, 'pend') == 2 else 'gone' if not mine(b, slot) else None
        hp2 = hp
        b.run(1)
    r['hits'] = sum(1 for fr, v, hp, vs in b.hits if v == 2 and hp > 0)
    r['p1_hits'] = sum(1 for fr, v, hp, vs in b.hits if v == 0 and hp > 0)
    return r

def main(args):
    specs = [a for a in args if not a.startswith('--')] or chars_from_makefile()
    roster = chars_from_makefile()
    P = picked(specs)
    b = Brawler()
    shooters = [roster.index(s) for s in P]
    print('fighter input | spawn b/g | speed b/g | free: life b/g, travel b/g, died at sx b/g | outlives its special | '
          'owner hit | ' + ' | '.join(f'{d}: hits b/g, frame b/g, travel b/g, after' for d in projectiles96.DISTS) + ' | clash')
    for spec, (inp, gs_) in P.items():
        g = gs_[0]
        k = roster.index(spec)
        free = trial(b, k)
        xs = free['xs']; v = round(xs[-1] - xs[-2], 2) if len(xs) > 1 else 0
        gs = 'end' if g['death'] == 'anim' else g['death_sx']
        gv = round(g['rows'][-1][3] - g['rows'][-2][3], 2) if len(g['rows']) > 1 else 0   # its motion, not +$50
        line = (f'{spec.split(":")[1]} {inp} | {free["spawn"]}/{g["spawn_row"]} | {v}/{gv} | {len(xs)}/{g["life"]}, '
                f'{round(xs[-1] - xs[0], 1)}/{g["travel"]}, {free["sx"] if free["end"] == "gone" and g["death"] != "anim" else free["end"]}/{gs} | '
                f'{"yes" if free["outlived"] else "no"}')
        if g['child']:
            c = g['child']; nb = sum(1 for x in c['births'] if x < g['life'])
            line += f' | trail {free["trail"]}/{nb} at dx {sorted(set(free["trail_x"]))}/{c["dx"]}'
        if len(gs_) > 1: line += f' | +{len(gs_) - 1} more: spawn rows {[q["spawn_row"] for q in gs_]}'
        oh = trial(b, k, owner_hit=True)
        line += f' | {"thrower hit, " if oh["owner"] is not None else "not hit, "}' + (f'flew on to {oh["owner"]} px' if isinstance(oh['owner'], float) else str(oh['owner']))
        for d in projectiles96.DISTS:
            r = trial(b, k, d, spawn_row=g['spawn_row']); gh = g['hits'].get(d, {})
            gn = sum(q['hits'].get(d, {}).get('hits') or 0 for q in gs_)   # every projectile of the move
            line += (f' | {r["hits"]}/{gn}, {r["hit"][0] if r["hit"] else "-"}/{gh.get("frame", "-")}, '
                     f'{r["hit"][1] if r["hit"] else "-"}/{gh.get("x", "-")}, {r["after"] or "-"}')
        # clash: an enemy whose fighter has a projectile (its D), on the screen's other side
        enemy = next((i for i in range(2, 8) if b.char_of(i) in shooters and b.char_of(i) != k), None)
        if enemy is not None:
            c = trial(b, k, clash=enemy)
            line += f' | vs {roster[b.char_of(enemy)].split(":")[1]}: mine {c["end"]}, theirs {"ended" if c["others"] else "-"}, fighters hit {c["p1_hits"] + c["hits"]}'
        print(line, flush=True)

if __name__ == '__main__':
    main(sys.argv[1:])
