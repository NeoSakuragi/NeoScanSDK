#!/usr/bin/env python3
"""Piece knobs in our emulator (harness.py, the desktop Geolith core; never MAME): the TRY blob's knob rows (encoded by
chainlab/lab.js encodeTry + knobRows under Node: the pages' own encoder) in a Lab build, measured on the projectile.

    python3 tools/brawler/knobs_proof.py [GAME_DIR] [--build build_lab_robert] [--rom lab-robert.neo] [--out DIR]

Robert's S-012 Haoh Shoukou Ken C (default 7 px/frame, 1 hit) and S-013 MAX 6426A (16 px/frame, 5 hits):
  default      S-012 on forward + C, no knob: 7 / 1
  knobbed      speed 12, hits 3 on forward + C: 12 / 3
  three slots  the same piece on C, forward + C, down + C at 9 / 12 / 15 (Bruno: "a decoded speed of 6, then the SAME
               piece on 3 slots at 9, 12 and 15"): each measured on its own input
  back         the same slots, no knob ("Back to default"): 7 / 1
  max          S-013 on down + D while S-012 is knobbed: its hits and 16 px the same as with no knob at all
  clamp        a value past the catalogue's bound (speed 100 px/frame raw) is clamped to the build's max (21)
  unknown      a knob row the catalogue lacks (a P_SET the piece never runs) is refused: lstat 0x80 | 9
-> OUT/knobs_proof.json, PASS / FAIL per case."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'chainlab')); sys.path.insert(0, HERE)
import harness
from labdrive import Lab
import knobs

LAB_JS = os.path.join(HERE, 'chainlab', 'lab.js')


def encode(cfg):
    """the TRY blob of cfg ({fighter, slots, queue, knobs: [{slot, spec, knob def, value} | raw rows]}) by lab.js"""
    js = ("const CL=require(%r);const c=JSON.parse(process.argv[1]);"
          "c.knobs=(c.knobs||[]).flatMap(k=>k.def?CL.knobRows(k.def,k.value).map(r=>Object.assign({slot:k.slot,spec:k.spec},r)):[k]);"
          "process.stdout.write(Buffer.from(CL.encodeTry(c)).toString('hex'))") % LAB_JS
    return bytes.fromhex(subprocess.run(['node', '-e', js, json.dumps(cfg)], capture_output=True, text=True, check=True).stdout)


def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('game', nargs='?', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--build', default='build_lab_robert'); ap.add_argument('--rom', default='lab-robert.neo')
    ap.add_argument('--out', default='/data/tmp/knobs')
    ap.add_argument('--as', dest='as_', default='robert', help='the roster name Robert plays as (a shell: "slot", with --rom a shell + his pack applied)')
    a = ap.parse_args(); game = os.path.abspath(a.game)
    harness.GAME = game
    L = Lab(rom=os.path.join(game, a.rom), game=game, build=a.build); b = L.b; ST = b.states
    G = json.load(open(os.path.join(game, 'game.json')))
    names = [r['name'] for r in G['roster']]
    CLJ = json.load(open(os.path.join(game, a.build, 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CLJ['fighters'] if x['name'] == a.as_)['pool']]
    cat, reg = knobs.library('robert')
    kd = lambda pid, kid: next(k for k in cat[pid] if k['id'] == kid)
    spec = lambda pid: pool.index(reg['pieces'][pid]['input'])
    fid = len(names) if a.as_ == 'slot' else names.index(a.as_); LE_SPEC = 0x1000   # (the shell's slot: the last index)
    L.start(fid, names.index('ryo')); b.run(30)
    lf = b.syms['lab_fields']
    cur = {'cfg': None}
    def send(cfg):
        cur['cfg'] = cfg
        blob = encode(dict(cfg, fighter=fid))
        L.poke(lf['tblob'], blob); L.poke(lf['lstat'], [0]); L.poke(lf['tnow'], [1]); L.poke(0, b'LAB1'); L.poke(5, [fid]); L.poke(7, [6])
        b.run(3)
        return b.r(L.lab + lf['lstat'], 1), len(blob)
    base = b.save()
    def shoot(keys, frames=200):
        """P1 facing right 60 px from the camera's left, the dummy 200 px ahead (life refilled): keys pressed 2 frames;
        -> the projectile's px per frame (its moving frames' mode), its hits on the dummy"""
        b.load(base)
        if cur['cfg'] is not None: send(cur['cfg'])
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 60
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + 200, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max')); b.run(2)   # (the training
                                                         # refills the dummy to its hp_max: never above, or that reads as a hit)
        hp = b.fget(2, 'hp'); hits = 0; seen = {}; alive = False
        for i in range(frames):
            b.run(1, p1=keys if i < 2 else '')
            for k in range(4):
                if ST[b.pget(k, 'state')] == 'PROJ' and b.pget(k, 'pdef') and b.pget(k, 'pend') == 0:
                    x = b.pget(k, 'x'); fr = b.pget(k, 'freeze')
                    if k in seen and not fr and x != seen[k]: seen.setdefault('d', []).append(round(abs(x - seen[k]), 3))
                    seen[k] = x; alive = True
            h = b.fget(2, 'hp')
            if h < hp: hits += 1
            hp = h; b.fset(2, 'hp', b.fget(2, 'hp_max')) if h < 40 else None; hp = b.fget(2, 'hp')
        d = seen.get('d', [])
        mode = max(set(d), key=d.count) if d else None
        return {'speed': mode, 'hits': hits, 'moving_frames': len(d)}
    rep, ok = {}, True
    def case(name, got, want):
        nonlocal ok
        good = all(got.get(k) == v for k, v in want.items())
        ok &= good; rep[name] = dict(got, want=want, result='PASS' if good else 'FAIL')
        print(f'{name:28} {"PASS" if good else "FAIL"}  got {got}  want {want}', flush=True)
    s12, s13 = spec('S-012'), spec('S-013')
    st, n = send({'slots': {'sp_fc': [LE_SPEC | s12]}}); rep['blob_v1'] = {'lstat': st, 'bytes': n}
    case('default forward+C', shoot('Rc'), {'speed': 7, 'hits': 1})
    st, n = send({'slots': {'sp_fc': [LE_SPEC | s12]}, 'knobs': [
        {'slot': 'sp_fc', 'spec': s12, 'def': kd('S-012', 'speed'), 'value': 12}, {'slot': 'sp_fc', 'spec': s12, 'def': kd('S-012', 'hits'), 'value': 3}]})
    rep['blob_v2'] = {'lstat': st, 'bytes': n}
    case('speed 12 hits 3 forward+C', shoot('Rc'), {'speed': 12, 'hits': 3})
    three = {'sp_c': 9, 'sp_fc': 12, 'sp_dc': 15}
    st, _ = send({'slots': {k: [LE_SPEC | s12] for k in three}, 'knobs': [
        {'slot': k, 'spec': s12, 'def': kd('S-012', 'speed'), 'value': v} for k, v in three.items()]})
    for k, v in three.items(): case(f'three slots {k} = {v}', shoot({'sp_c': 'c', 'sp_fc': 'Rc', 'sp_dc': 'Dc'}[k]), {'speed': v, 'hits': 1})
    send({'slots': {k: [LE_SPEC | s12] for k in three}})
    for k in three: case(f'back to default {k}', shoot({'sp_c': 'c', 'sp_fc': 'Rc', 'sp_dc': 'Dc'}[k]), {'speed': 7, 'hits': 1})
    send({'slots': {'sp_fc': [LE_SPEC | s12], 'max': [LE_SPEC | s13]}})
    mx = shoot('Dd', 200); rep['max_no_knob'] = mx
    print('MAX with no knob at all:', mx, '(hp drops counted on the dummy over the whole move)')
    send({'slots': {'sp_fc': [LE_SPEC | s12], 'max': [LE_SPEC | s13]}, 'knobs': [
        {'slot': 'sp_fc', 'spec': s12, 'def': kd('S-012', 'speed'), 'value': 12}, {'slot': 'sp_fc', 'spec': s12, 'def': kd('S-012', 'hits'), 'value': 3}]})
    case('MAX unchanged (S-012 knobbed)', shoot('Dd', 200), {'speed': 16, 'hits': mx['hits']})
    case('  and S-012 still knobbed', shoot('Rc'), {'speed': 12, 'hits': 3})
    raw = knobs.knob_rows(kd('S-012', 'speed'), 100)[0]
    send({'slots': {'sp_fc': [LE_SPEC | s12]}, 'knobs': [dict(raw, slot='sp_fc', spec=s12)]})
    case('clamp 100 -> 21', shoot('Rc'), {'speed': 21})
    st, _ = send({'slots': {'sp_fc': [LE_SPEC | s12]}, 'knobs': [{'slot': 'sp_fc', 'spec': s12, 'kind': 1, 'a': 0, 'match': 123456, 'val': 5}]})
    case('unknown knob refused', {'lstat': st}, {'lstat': 0x80 | 9})
    os.makedirs(a.out, exist_ok=True)
    json.dump(rep, open(os.path.join(a.out, f'knobs_proof_{a.as_}.json'), 'w'), indent=1)
    print('ALL PASS' if ok else 'SOME FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
