#!/usr/bin/env python3
"""Notes on 0.10.171, in our emulator (harness.py, the repo's Geolith core), before / after:

  20261017-173520-e03d (Haggar: "only one finisher, the regular one: no up / forward / down finisher; the neutral
      finisher pushes the opponent away and not much in the air; the same for run + A; less juggle"):
      fin_<stick>  jab, jab, then A with the stick neutral / up / forward / down / down-forward on a standing Ryo: the
                   finisher node + animation played, Ryo's launch (vx, vy), rise, air frames, distance
      fin_air      the neutral finisher on Ryo held airborne (the same flight from where it is: finishers.air.neutral)
      run / run_air run + A (the ff Blitz) on a standing / an airborne Ryo
      loops        run + A / the chain pressed again and again on a juggled Ryo: its air hits before it lands
  20261017-173728-e03d ("five frames of recovery to the finisher and to the blitz"): Haggar's ATTACK frames for the
      finisher and for run + A (hit), before / after
  20261017-174059-e03d (stage 2's water floor): stage 2's boss (Krauser) on its new background, and stage 2's end of
      scroll (the camera at the boss lock): no water

    notes1017e_proof.py OUT [--before GAME_DIR]     GAME_DIR: an older build's examples/brawler (brawler.neo + build/)
Writes OUT/sheet.png (one contact sheet) and OUT/report.json; ALL OK / FAIL on the after build."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import notes1017d_proof as D
NOTE_FIN, NOTE_REC, NOTE_STAGE = '20261017-173520-e03d', '20261017-173728-e03d', '20261017-174059-e03d'
STICKS = {'neutral': '', 'up': 'U', 'forward': 'R', 'down': 'D', 'downfwd': 'DR'}
CHAIN = '2:a,10:-,2:a,12:-,2:{}a,90:-'
RUN_A = D.RUN_A


def attack_frames(b, rec, keys, nth):
    """P1's ATTACK frames for the move whose hit is the nth on Ryo (from its first frame to the frame it leaves ATTACK /
    the node changes) and the node / animation it played"""
    import scenario as S
    S.setup(b, rec); log = []; st = {'hp': None, 'n': 0}
    def each(b):
        p, d = b.fighter(0), b.fighter(2)
        if st['hp'] is None: st['hp'] = d['hp']
        if d['hp'] < st['hp']: st['n'] += 1; st['hp'] = d['hp']
        log.append((p['state'], p['node'], p['anim'], st['n']))
    for part in [q for q in keys.split(',') if q]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''), each=each)
    i = next((i for i, r in enumerate(log) if r[3] >= nth), None)
    if i is None: return {'hit': False}
    node = log[i][1]
    s = i
    while s > 0 and log[s - 1][0] == 'ATTACK' and log[s - 1][1] == node: s -= 1
    e = i
    while e < len(log) and log[e][0] == 'ATTACK' and log[e][1] == node: e += 1
    return {'hit': True, 'node': node, 'anim': log[i][2], 'frames': e - s}


def stage_pics(b, label, pics):
    import scenario as S
    out = {}
    rec = {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': 1, 'wave': 4, 'wait': 420}}
    S.setup(b, rec); b._want_video = True; b.run(30); b._want_video = False
    boss = b.fighter(2)
    pics.append((f'{label} stage 2 boss (fighter 2 x {boss["x"]:.0f})', D.pic(b)))
    out['boss_x'] = round(boss['x'])
    for cam in (1200, 1568):
        rec = {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': 1, 'wave': 3, 'cam': cam}}
        S.setup(b, rec); b._want_video = True; b.run(2); b._want_video = False
        pics.append((f'{label} stage 2 cam {cam}', D.pic(b)))
    return out


def one(game, label, out):
    import harness as H, scenario as S
    b = H.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    R = S.recipes()['20261017-141149-e03d']; pics = []
    near = {'setup': dict(R['setup'], gap=40)}
    rep = {f'fin_{k}': D.flight(b, near, CHAIN.format(v), False, label, pics if k in ('neutral', 'forward') else [], f'jab jab {k}+A', nth=3)
           for k, v in STICKS.items()}
    for k, v in STICKS.items():
        rep[f'fin_{k}'].update({f'atk_{f}': x for f, x in attack_frames(b, near, CHAIN.format(v), 3).items()})
    rep['fin_air'] = D.flight(b, near, CHAIN.format(''), True, label, pics, 'jab jab A airborne', nth=3)
    rep['run'] = D.flight(b, R, RUN_A, False, label, pics, 'run+A grounded')
    rep['run'].update({f'atk_{f}': x for f, x in attack_frames(b, R, RUN_A, 1).items()})
    rep['run_air'] = D.flight(b, R, RUN_A, True, label, pics, 'run+A airborne')
    for h in (24, 64):
        for i, (p, n) in enumerate(D.LOOPS):
            rep[f'loop{i}_{h}'] = D.flight(b, R, RUN_A + ',' + ','.join([p] * n), True, label, [], f'loop {h}', 120, air_y=h)
        for i, (p, n) in enumerate(D.CHAIN_LOOPS):
            rep[f'loopc{i}_{h}'] = D.flight(b, near, ','.join([p] * n), True, label, [], f'chain loop {h}', 120, air_y=h)
    rep['stage'] = stage_pics(b, label, pics)
    for k in rep: rep[k].pop('log_frames', None)
    import pickle
    pickle.dump(pics, open(os.path.join(out, f'pics_{label}.pkl'), 'wb'))
    print(json.dumps({label: rep}))


def main():
    a = sys.argv[1:]
    if a and a[0] == '_one': return one(*a[1:4])
    out = a[0]; os.makedirs(out, exist_ok=True)
    runs = [('after', os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))]
    if '--before' in a: runs.insert(0, ('before', a[a.index('--before') + 1]))
    rep = {}
    for label, game in runs:
        r = subprocess.run([sys.executable, __file__, '_one', game, label, out], capture_output=True, text=True)
        if r.returncode: sys.exit(r.stderr[-3000:])
        rep.update(json.loads(r.stdout.strip().splitlines()[-1]))
    import pickle
    from PIL import Image, ImageDraw
    pics = []
    for label, _ in runs: pics += pickle.load(open(os.path.join(out, f'pics_{label}.pkl'), 'rb'))
    w, h = pics[0][1].size; cols = 5
    sh = Image.new('RGB', (w * cols, (h + 14) * ((len(pics) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sh)
    for i, (t, im) in enumerate(pics):
        x, y = i % cols * w, i // cols * (h + 14); sh.paste(im, (x, y + 14)); d.text((x + 3, y + 1), t, fill='black')
    sh.save(os.path.join(out, 'sheet.png'))
    for L, (t, im) in [(L, p) for L in ('after',) for p in pickle.load(open(os.path.join(out, f'pics_{L}.pkl'), 'rb')) if 'boss' in p[0]]:
        im.save(os.path.join(out, 'stage2_krauser.png'))
    json.dump(rep, open(os.path.join(out, 'report.json'), 'w'), indent=1)
    keys = ('hit', 'y0', 'vx', 'vy', 'frames', 'rise', 'distance', 'air_hits', 'jug_n', 'atk_node', 'atk_anim', 'atk_frames')
    for L, R in rep.items():
        print(L)
        for k, r in R.items():
            if k.startswith('loop'): continue
            print(f'  {k:12} ' + '  '.join(f'{f} {r[f]}' for f in keys if f in r) if k != 'stage' else f'  stage {r}')
    loops = lambda R: [R[k] for k in sorted(R) if k.startswith('loop')]
    print('air hits per loop: ' + '  '.join(f"{L} {[r.get('air_hits') for r in loops(R)]}" for L, R in rep.items()))
    A, B = rep['after'], rep.get('before')
    same = lambda p, q: p['hit'] and q['hit'] and p['vx'] == q['vx'] and p['vy'] == q['vy'] and q['track'][:len(p['track'])] == p['track']
    fin = A['fin_neutral']
    ok = {
        'every stick plays the neutral finisher (same node, same flight)': all(A[f'fin_{k}'].get('atk_node') == fin['atk_node'] and same(fin, A[f'fin_{k}']) for k in STICKS),
        'the finisher pushes away low (vx 4.5, vy 3)': fin['vx'] == 4.5 and fin['vy'] == 3.0,
        'run + A the same launch as the finisher': same(fin, A['run']),
        'airborne victims the same flight (finisher, run + A)': same(fin, A['fin_air']) and same(A['run'], A['run_air']) and A['fin_air']['y0'] > 0,
        'run + A loops on a juggled Ryo end (it lands, cap kept)': all(lp['hit'] and lp['lands_after'] is not None and lp['jug_n'] <= 5 for lp in loops(A)),
    }
    if B:
        ok['finisher + 5 recovery frames'] = fin['atk_frames'] == B['fin_neutral']['atk_frames'] + 5
        ok['run + A + 5 recovery frames'] = A['run']['atk_frames'] == B['run']['atk_frames'] + 5
        ok['lower than before (finisher, run + A)'] = fin['rise'] < B['fin_neutral']['rise'] and A['run']['rise'] < B['run']['rise']
        ok['no loop juggles more than before'] = all(a['air_hits'] <= b['air_hits'] for a, b in zip(loops(A), loops(B)))
    for k, v in ok.items(): print(('ok   ' if v else 'FAIL ') + k)
    print('ALL OK' if all(ok.values()) else 'FAIL')


if __name__ == '__main__':
    main()
