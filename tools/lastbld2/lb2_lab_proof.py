#!/usr/bin/env python3
"""LB2 Moriya through the Character Lab (2026-10-12), the SS2 fighters' proof (tools/samsho2/ss2_lab_proof.py) for The Last
Blade 2: every decoded piece of his pack (arb_pieces/<f>_ids.json: each S- special version, each T- throw) fired from a
slot override of the TRY blob (encoded by the pages' own chainlab/lab.js encodeTry) in the SHELL with his PACK applied
(lab_pack.py apply: the bytes the Player and the web core load), in our emulator (tools/brawler/harness.py, the Geolith
core; never MAME), against a training dummy:

  a ground special on C (sp_c), the rage move on D (fury); the throws in the hold's slots (grab_fwd: LE_THROW | k,
  k = export_bm LE_THROWS: 0 T-001, 1 T-002: Samidare both)
  measured: the move started (P1 in the special / the throw), the dummy's hits and damage, his travel / top height

    python3 tools/lastbld2/lb2_lab_proof.py FIGHTER [GAME_DIR] [--neo SHELL+PACK.neo] [--out DIR]
        -> OUT/<f>_lab_proof.json (default --neo /data/tmp/lb2lab/shell_<f>.neo, --out /data/tmp/lb2lab)
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab

LAB_JS = os.path.join(BR, 'chainlab', 'lab.js')
LE_SPEC, LE_THROW = 0x1000, 0x2000

# per fighter: (input, slot, key, dummy distance px (a tuple: the first that lands its hit), x offset from the camera,
# {measure: minimum}) for every S- piece. The teleports (Taitou Hogetsu: anims $B3 / $AF / $B0 carry no attack record) and
# Izayoi Gekka's whiff (its hits are the connect branch's, not imported) want the move to start only
CASES = {
    'moriya': [('236A', 'sp_c', 'c', (60, 80, 40), 70, {'hits': 1}), ('236B', 'sp_c', 'c', (80, 100, 60), 70, {'hits': 1}),
               ('623A', 'sp_c', 'c', (40, 60, 20), 70, {'hits': 1}), ('623B', 'sp_c', 'c', (60, 80, 40, 100), 70, {'hits': 1}),
               ('214A', 'sp_c', 'c', (60, 80, 40), 70, {'hits': 1}), ('214B', 'sp_c', 'c', (60, 80, 40), 70, {'hits': 1}),
               ('214C', 'sp_c', 'c', (60, 80, 40), 70, {'hits': 1}),
               ('412A', 'sp_c', 'c', 80, 100, {}), ('412B', 'sp_c', 'c', 80, 70, {}), ('412C', 'sp_c', 'c', 80, 70, {}),
               ('22A', 'sp_c', 'c', (80, 120, 60), 70, {'hits': 1}), ('22B', 'sp_c', 'c', (80, 120, 60), 70, {'hits': 1}),
               ('64123AB', 'fury', 'd', (60, 80, 40), 70, {}), ('641236B', 'fury', 'd', (120, 160, 80), 40, {'hits': 1})],
}


def encode(cfg):
    js = ("const CL=require(%r);const c=JSON.parse(process.argv[1]);"
          "process.stdout.write(Buffer.from(CL.encodeTry(c)).toString('hex'))") % LAB_JS
    return bytes.fromhex(subprocess.run(['node', '-e', js, json.dumps(cfg)], capture_output=True, text=True, check=True).stdout)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter')
    ap.add_argument('game', nargs='?', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--neo'); ap.add_argument('--build', default='build_shell'); ap.add_argument('--out', default='/data/tmp/lb2lab')
    a = ap.parse_args(); game = os.path.abspath(a.game); harness.GAME = game; f = a.fighter
    L = Lab(rom=a.neo or f'/data/tmp/lb2lab/shell_{f}.neo', game=game, build=a.build); b = L.b; ST = b.states
    G = json.load(open(os.path.join(game, 'game.json')))
    names = [r['name'] for r in G['roster']]
    fid = len(names)                                        # the shell's slot (the last index): him with his pack
    CLJ = json.load(open(os.path.join(game, f'build_pack_{f}', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CLJ['fighters'] if x['name'] == 'slot')['pool']]
    reg = json.load(open(os.path.join(BR, 'arb_pieces', f'{f}_ids.json')))
    lf = b.syms['lab_fields']

    def send(cfg):
        blob = encode(dict(cfg, fighter=fid))
        L.poke(lf['tblob'], blob); L.poke(lf['lstat'], [0]); L.poke(lf['tnow'], [1]); L.poke(0, b'LAB1'); L.poke(5, [fid]); L.poke(7, [6])
        b.run(3)
        return b.r(L.lab + lf['lstat'], 1)
    bases = {}
    def base(dummy):
        if dummy not in bases:
            L.start(fid, names.index(dummy)); b.run(30); bases[dummy] = b.save()
        return bases[dummy]
    rows, ok = [], True

    def trial(pid, slot, entry, keys, dx, dummy='ryo', frames=300, grab=False, x0off=70):
        b.load(base(dummy))
        st = send({'slots': {slot: [entry]}} if slot else {})
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + x0off
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + dx, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max')); b.run(2)
        hp = b.fget(2, 'hp'); hits = dmg = 0; seen = set(); started = False; x_0 = b.fget(0, 'x'); ytop = 0; nspec = 0
        if grab:                                            # walk into it: the hold
            for i in range(40):
                b.run(1, p1='R')
                if ST[b.fget(0, 'state')] == 'GRAB': break
            if ST[b.fget(0, 'state')] != 'GRAB': return dict(piece=pid, slot=slot, started=False, hits=0, damage=0, why='no hold')
        for i in range(frames):
            b.run(1, p1=keys if i < 2 else '')
            s = ST[b.fget(0, 'state')]; seen.add(s)
            if s in ('SPECIAL', 'THROW'): started = True
            if s == 'SPECIAL': nspec += 1; ytop = max(ytop, b.fget(0, 'y'))
            h = b.fget(2, 'hp')
            if h < hp: hits += 1; dmg += hp - h
            hp = h
            if h < 30: b.fset(2, 'hp', b.fget(2, 'hp_max')); hp = b.fget(2, 'hp')
        return dict(piece=pid, slot=slot, entry=hex(entry), lstat=st, started=started, hits=hits, damage=dmg,
                    states=sorted(seen), travel=round(b.fget(0, 'x') - x_0), top=round(ytop), frames=nspec)

    def case(r, want):
        nonlocal ok
        good = r.get('started') and all((r.get(k) or 0) >= v for k, v in want.items())
        r['result'] = 'PASS' if good else 'FAIL'; r['want'] = want; ok &= bool(good); rows.append(r)
        print(f"{r['piece']:6} {reg['pieces'].get(r['piece'], {}).get('input', '')[:24]:24} {r['slot']:9} started {r['started']!s:5} "
              f"hits {r['hits']:2} dmg {r['damage']:3} travel {r.get('travel')} top {r.get('top')} frames {r.get('frames')}  {r['result']}", flush=True)

    S = {p['input']: i for i, p in reg['pieces'].items() if p['kind'] == 'special'}
    assert {c[0] for c in CASES[f]} <= set(S) and all('>' in i for i in set(S) - {c[0] for c in CASES[f]}), \
        ('every S- piece has a case (the follow-up pieces "236A>BD": followups_lb2_proof.py)', set(S) ^ {c[0] for c in CASES[f]})
    only = os.environ.get('ONLY')                      # (ONLY=input,input: those pieces alone, no throws)
    for inp, slot, key, dx, x0off, want in CASES[f]:
        if only and inp not in only.split(','): continue
        for d in (dx if isinstance(dx, tuple) else (dx,)):     # (a long leap: the first gap it lands its hit at)
            r = trial(S[inp], slot, LE_SPEC | pool.index(inp), key, d, x0off=x0off); r['gap'] = d
            if r['hits'] >= want.get('hits', 0): break
        case(r, want)
    T = {p['move']: i for i, p in reg['pieces'].items() if p['kind'] == 'throw'}
    for mv, k in (() if only else (('throw_c', 0), ('throw_d', 1))):   # (T-001 / T-002: Samidare on both throw slots)
        case(trial(T[mv], 'grab_fwd', LE_THROW | k, 'Ra', 30, grab=True), {'hits': 1})
    os.makedirs(a.out, exist_ok=True)
    json.dump(rows, open(os.path.join(a.out, f'{f}_lab_proof.json'), 'w'), indent=1)
    print(f"{f}: {sum(r['result'] == 'PASS' for r in rows)} / {len(rows)} PASS")
    sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
