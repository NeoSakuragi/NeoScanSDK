#!/usr/bin/env python3
"""The MAX cancel (note 20261016-133443-e03d, game.json max_cancel: KOF's Dream Cancel): per fighter with a fury, in our
emulator (harness.py, the Lab: scenario.setup mode lab, the dummy Ryo standing 60 px ahead, the fury gauge full):
1. a 4-chunk drive bar (chunks 4, full): D = the fury; once one of its hits lands, down + D every other frame. Checks:
   the MAX starts (fighter_t.fmax), drive spent = max_cancel.cost chunks (on top of the fury's own), the freeze
   (main.c mc_t: max_cancel.freeze ticks, P1 and the dummy do not move, their state held), the stage hidden behind the
   backdrop (bd_on), MAX CANCEL in the big font (bt_s = big_text.max_cancel), then the MAX's own super flash (sf_who).
2. a 2-chunk bar (the fury leaves 1, short of the cost): the same presses, no cancel: the fury plays on to its end.
3. D alone (no down) after the fury's hit: no cancel.
Screenshots OUT/<fighter>.png (the freeze's middle). Out: OUT/maxcancel.json

    python3 maxcancel_proof.py OUT [FIGHTER ...]     (default every roster fighter with a fury)   exit 1 on a FAIL"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
G = os.path.join(HERE, '..', '..', 'examples', 'brawler')

def one(name, chunks, keys, shot=None):
    import harness as H, scenario as SC
    b = H.Brawler(game=G); b.game = G; S = b.syms
    SC.setup(b, {'setup': {'mode': 'lab', 'fighter': name, 'dummy': 'ryo' if name != 'ryo' else 'terry', 'gap': 60,
                           'chunks': chunks, 'drive': 'full', 'fury': 'full'}})
    MC = json.load(open(os.path.join(G, 'game.json')))['max_cancel']; chunk = json.load(open(os.path.join(G, 'game.json')))['meter']['chunk']
    st = lambda i=0: b.states[b.fget(i, 'state')]
    h0 = len(b.hits); b.run(1, p1='d'); b.run(1)
    r = {'fighter': name, 'chunks': chunks}
    if st() != 'SPECIAL' or b.fget(0, 'spec_id') != b.syms.get('BS_FURY', 6) and False: pass
    for k in range(400):
        if st() != 'SPECIAL': r['fury_end'] = k; break
        if b.fget(0, 'fmax'):                                      # the MAX started: the cancel
            r['cancel_at'] = k; break
        hit = any(h[1] != 0 for h in b.hits[h0:])
        dr = b.fget(0, 'drive')
        b.run(1, p1=keys if hit and k % 2 == 0 else '')
        if b.fget(0, 'fmax'): r['drive_before'] = dr
    if 'cancel_at' not in r: return r
    r['drive_after'] = b.fget(0, 'drive'); r['spent_chunks'] = (r['drive_before'] - r['drive_after']) / chunk
    mc = b.r(S['mc_t'], 1); r['mc_t'] = mc
    pos = [(b.fget(i, 'x'), b.fget(i, 'y'), b.fget(i, 'state'), b.fget(i, 'anim'), b.fget(i, 'step'), b.fget(i, 'srow')) for i in (0, 2)]
    use = (b.r(S['bt_s'], 4) - S['gbig']) // 10 if b.r(S['bt_n'], 1) else None
    held, bd = 0, 0
    for k in range(mc):
        b.run(1)
        if k == mc // 2 and shot: b.screenshot(shot)
        if [(b.fget(i, 'x'), b.fget(i, 'y'), b.fget(i, 'state'), b.fget(i, 'anim'), b.fget(i, 'step'), b.fget(i, 'srow')) for i in (0, 2)] == pos: held += 1
        bd += b.r(S['bd_on'], 1) != 0
    r.update(big_use=use, frozen_frames=held, backdrop_frames=bd, text_after=b.r(S['bt_n'], 1))
    sf = None
    for k in range(10):
        b.run(1)
        if b.r(S['sf_who'], 4): sf = k; break
    r['flash_after'] = sf
    # (held / bd: the screenshot runs a frame of its own: one frame of the freeze not counted)
    r['ok'] = (abs(r['spent_chunks'] - MC['cost']) < 0.01 and mc == MC['freeze'] and held >= mc - 2 and bd >= mc - 2
               and use == 7 and sf is not None)
    return r

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    if sys.argv[2:3] == ['--one']:
        name, chunks, keys, shot = sys.argv[3], int(sys.argv[4]), sys.argv[5], sys.argv[6] if len(sys.argv) > 6 else None
        print(json.dumps(one(name, chunks, keys, shot))); return
    g = json.load(open(os.path.join(G, 'game.json')))
    names = sys.argv[2:] or [r['name'] for r in g['roster'] if r.get('fury') and r['name'] != 'kuroko']
    res, fails = {}, 0
    for n in names:
        run = lambda c, k, s=None: json.loads(subprocess.run([sys.executable, os.path.abspath(__file__), out, '--one', n, str(c), k] + ([s] if s else []),
                                                         capture_output=True, text=True).stdout.strip().splitlines()[-1])
        a = run(4, 'Dd', os.path.join(out, f'{n}.png')); bb = run(2, 'Dd'); c = run(4, 'd')
        ok = bool(a.get('ok')) and 'cancel_at' not in bb and 'cancel_at' not in c
        fails += not ok; res[n] = {'cancel': a, 'short_of_drive': bb, 'D_alone': c, 'ok': ok}
        print(('OK  ' if ok else 'FAIL'), n, {k: a.get(k) for k in ('cancel_at', 'spent_chunks', 'mc_t', 'frozen_frames', 'backdrop_frames', 'big_use', 'flash_after')},
              '| 2 chunks:', 'no cancel' if 'cancel_at' not in bb else 'CANCELLED', '| D alone:', 'no cancel' if 'cancel_at' not in c else 'CANCELLED', flush=True)
    json.dump(res, open(os.path.join(out, 'maxcancel.json'), 'w'), indent=1)
    print('ALL OK' if not fails else f'{fails} FAIL'); sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
