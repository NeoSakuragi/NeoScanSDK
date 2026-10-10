#!/usr/bin/env python3
"""SS2 Hanzo through the Character Lab (2026-10-10): every decoded piece of his pack (arb_pieces/hanzo_ss2_ids.json: the
S- specials, every button version, and the T- throws) fired from a slot override of the TRY blob (encoded by the pages'
own chainlab/lab.js encodeTry) in the SHELL with his PACK applied (lab_pack.py apply: the bytes the Player and the web
core load), in our emulator (tools/brawler/harness.py, the Geolith core; never MAME), against a training dummy:

  a ground special on C (sp_c), an air one on C in a jump (air_sp_c), the rage move on D (fury); the throws in the hold's
  slots (grab_fwd: LE_THROW | k, k = export_bm LE_THROWS: 0 slash T-001, 1 kick T-002, 4 the extra paired throw =
  SS2's Earthquake throw T-003; the air throw T-004 has no slot: the engine plays three paired throws)
  measured: the move started (P1 in the special / the throw, its program's own animation), the dummy's hits and damage,
  the warps (Kage Bunshin: the camera's left + 80 / + 240; Utsusemi: on the dummy)

    python3 tools/samsho2/hanzo_lab_proof.py [GAME_DIR] [--neo SHELL+PACK.neo] [--out DIR]   -> OUT/hanzo_lab_proof.json
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab

LAB_JS = os.path.join(BR, 'chainlab', 'lab.js')
LE_SPEC, LE_THROW = 0x1000, 0x2000


def encode(cfg):
    js = ("const CL=require(%r);const c=JSON.parse(process.argv[1]);"
          "process.stdout.write(Buffer.from(CL.encodeTry(c)).toString('hex'))") % LAB_JS
    return bytes.fromhex(subprocess.run(['node', '-e', js, json.dumps(cfg)], capture_output=True, text=True, check=True).stdout)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('game', nargs='?', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--neo', default='/data/tmp/hanzo_ss2/shell_hanzo.neo')
    ap.add_argument('--build', default='build_shell')
    ap.add_argument('--out', default='/data/tmp/hanzo_ss2')
    a = ap.parse_args(); game = os.path.abspath(a.game); harness.GAME = game
    L = Lab(rom=a.neo, game=game, build=a.build); b = L.b; ST = b.states
    G = json.load(open(os.path.join(game, 'game.json')))
    names = [r['name'] for r in G['roster']]
    fid = len(names)                                        # the shell's slot (the last index): Hanzo with his pack
    CLJ = json.load(open(os.path.join(game, 'build_pack_hanzo_ss2', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CLJ['fighters'] if x['name'] == 'slot')['pool']]
    reg = json.load(open(os.path.join(BR, 'arb_pieces', 'hanzo_ss2_ids.json')))
    lf = b.syms['lab_fields']
    def send(cfg, dummy):
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

    def trial(pid, slot, entry, keys, dx, dummy='ryo', frames=260, jump=False, grab=False, x0off=70):
        b.load(base(dummy))
        st = send({'slots': {slot: [entry]}} if slot else {}, dummy)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + x0off
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + dx, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max')); b.run(2)
        hp0 = hp = b.fget(2, 'hp'); hits = dmg = 0; seen = set(); xs = []; started = False; x_0 = b.fget(0, 'x'); ytop = 0; nspec = 0
        if grab:                                            # walk into it: the hold
            for i in range(40):
                b.run(1, p1='R')
                if ST[b.fget(0, 'state')] == 'GRAB': break
            if ST[b.fget(0, 'state')] != 'GRAB': return dict(piece=pid, slot=slot, result='FAIL', why='no hold'), False
        if jump:
            b.run(6, p1='U'); b.run(4)
        for i in range(frames):
            b.run(1, p1=keys if i < 2 else '')
            s = ST[b.fget(0, 'state')]; seen.add(s)
            if s in ('SPECIAL', 'THROW'): started = True
            if s == 'SPECIAL': xs.append(round(b.fget(0, 'x') - b.r(b.syms['cam_x'], 2))); nspec += 1; ytop = max(ytop, b.fget(0, 'y'))
            h = b.fget(2, 'hp')
            if h < hp: hits += 1; dmg += hp - h
            hp = h
            if h < 30: b.fset(2, 'hp', b.fget(2, 'hp_max')); hp = b.fget(2, 'hp')
        return dict(piece=pid, slot=slot, entry=hex(entry) if entry is not None else None, lstat=st, started=started,
                    hits=hits, damage=dmg, states=sorted(seen), travel=round(b.fget(0, 'x') - x_0), top=round(ytop), frames=nspec,
                    screen_x=[xs[0], xs[len(xs) // 2], xs[-1]] if xs else None), True

    def case(r, want):
        nonlocal ok
        good = r.get('started') and all((r.get(k) or 0) >= v if isinstance(v, int) else v(r) for k, v in want.items())
        r['result'] = 'PASS' if good else 'FAIL'; ok &= bool(good); rows.append(r)
        print(f"{r['piece']:6} {reg['pieces'].get(r['piece'], {}).get('input', ''):12} {r['slot'] or '-':9} started {r['started']!s:5} hits {r['hits']:2} "
              f"dmg {r['damage']:3} travel {r.get('travel')} top {r.get('top')} frames {r.get('frames')} x {r.get('screen_x')}  {r['result']}", flush=True)

    S = {p['input']: i for i, p in reg['pieces'].items()}
    sp = lambda inp: LE_SPEC | pool.index(inp)
    for inp in ('6321A', '6321B', '6321AB'):
        r, _ = trial(S[inp], 'sp_c', sp(inp), 'c', 130); case(r, {'hits': 1})
    for inp in ('623C', '623D', '623CD'):
        r, _ = trial(S[inp], 'sp_c', sp(inp), 'c', 40, x0off=220); case(r, {'hits': 1})   # (room behind him: its leaps go back)
    r, _ = trial(S['WFT'], 'fury', sp('WFT'), 'd', 110); case(r, {'hits': 1})
    for inp in ('j.4123A', 'j.4123B', 'j.4123AB'):
        r, _ = trial(S[inp], 'air_sp_c', sp(inp), 'c', 110, jump=True); case(r, {'hits': 1})
    r, _ = trial(S['641236A'], 'sp_c', sp('641236A'), 'c', 140)   # (screen x after the warp: 80, facing right)
    case(r, {'w': lambda r: r['screen_x'] and abs(r['screen_x'][1] - 80) <= 2})
    r, _ = trial(S['641236B'], 'sp_c', sp('641236B'), 'c', 140)
    case(r, {'w': lambda r: r['screen_x'] and abs(r['screen_x'][1] - 240) <= 2})
    r, _ = trial(S['63214BCD'], 'sp_c', sp('63214BCD'), 'c', 140); case(r, {'hits': 1})
    r, _ = trial(S['6464642BCD'], 'sp_c', sp('6464642BCD'), 'c', 140); case(r, {})
    for inp in ('run 623C', 'run 623D', 'run 623CD'):                 # (the run's leap: backward travel, same catch)
        r, _ = trial(S[inp], 'sp_c', sp(inp), 'c', 40, x0off=220); case(r, {'hits': 1, 'back': lambda r: r['travel'] < -10})

    T = {p['move']: i for i, p in reg['pieces'].items() if p['kind'] == 'throw'}
    for mv, k in (('throw_c', 0), ('throw_d', 1), ('throw_x', 4)):   # (T-003, SS2's Earthquake throw: his extra paired
        r, _ = trial(T[mv], 'grab_fwd', LE_THROW | k, 'Ra', 30, grab=True); case(r, {'hits': 1})   # throw; T-004: no slot)
    os.makedirs(a.out, exist_ok=True)
    json.dump(rows, open(os.path.join(a.out, 'hanzo_lab_proof.json'), 'w'), indent=1)
    print(f"{sum(r['result'] == 'PASS' for r in rows)} / {len(rows)} PASS")
    sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
