#!/usr/bin/env python3
"""TODO #196 proof: the throw hitch (found by #194). At the thrower's control return (its script's row `ret`) fighter.c
paired_update returned before placing the victim: that frame the victim showed row ret's pose at row ret-1's place,
then jumped two rows' worth the frame after (one stall + one double step, ~6 px in Billy Lee's flight). Fixed: the
victim is placed on the control-return row too, then plays on alone (thrown_update) from there.
Our emulator only: the brawler through the Geolith harness on a `make AI_OFF=1` build (the test places the enemy; one
core per process), the source game's flight from the KOF98 capture (tools/kof96/capture/throws98/3.txt, Terry vs Yuri,
taken with our emulator).

    BRAWLER_CORE=<core> python3 throw196_proof.py OUT TAG [FIGHTERS]   per fighter (terry, geese, billy_lee) x forward /
        back + A: the walk-in grab, then the throw; per frame the thrower's state / row, the victim's row, place from the
        throw's origin (grab facing), height and frame; each frame's place vs the exported script's row the victim shows
        (tx + vx, ty + vy), and the largest per-frame step across the release vs the flight's own -> OUT/TAG.json
    python3 throw196_proof.py OUT kof98      KOF98 Terry's forward throw on Yuri: the victim's place per frame across
        Terry's control return (the game's flight has no hitch) -> OUT/kof98.json
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
KEYS = {'throw_c': 'Ra', 'throw_d': 'La'}
ENEMY = 2


def script_rows(name, key):
    """the exported throw's rows (build/bm_chars.c: {tframe, tx, ty, vpose, flags, vx, vy}) and its points"""
    c = open(os.path.join(GAME, 'build', 'bm_chars.c')).read()
    m = re.search(rf'static const bthrow_row_t {name}_{key}\[\] = \{{(.*?)\}};', c, re.S)
    rows = [tuple(int(x) for x in r.split(',')) for r in re.findall(r'\{([^{}]*)\}', m.group(1))]
    t = re.search(rf'static const bthrow_t {name}_throws\[BT_COUNT\] = \{{(.*?)\}};', c, re.S).group(1)
    ent = re.findall(r'\{([^{}]*)\}', t)[0 if key == 'throw_c' else 1].split(',')
    return rows, dict(nrows=int(ent[0]), speed=int(ent[1], 0), ret=int(ent[3], 0))


def case(b, name, key):
    st = b.states.index
    S = lambda i: b.states[b.fget(i, 'state')]
    names = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    b.pick(names.index(name), unlock=True)
    for i in range(8):
        if b.fget(i, 'ch') == 0 or (i == 1 and b.fget(i, 'state') == st('OFF')): continue
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.fset(i, 'frame_ovr', 0xFFFF); b.fset(i, 'held', 0); b.intent(i)
    x1 = 160 if key == 'throw_c' else 300
    b.place(0, x=x1, z=30); b.fset(0, 'facing', 1)
    b.place(ENEMY, x=x1 + 30, z=30); b.fset(ENEMY, 'facing', 0xFF)
    for j, i in enumerate((3, 4, 5)):
        if b.fget(i, 'ch'): b.place(i, x=900 + 40 * j, z=30)
    b.run(1)
    for f in range(60):
        b.run(1, p1='R')
        if S(0) == 'GRAB': break
    else: raise RuntimeError('no grab: ' + b.brief())
    x0 = b.fget(0, 'x'); rows = []
    for f in range(140):
        b.run(1, p1=KEYS[key] if f == 0 else '')
        rows.append(dict(f=f, p1=S(0), p1row=b.fget(0, 'srow') - 1, v=S(ENEMY), vrow=b.fget(ENEMY, 'srow') - 1,
                         vx=round(b.fget(ENEMY, 'x') - x0), vy=round(b.fget(ENEMY, 'y')), vframe=b.fget(ENEMY, 'shown_frame')))
        if f > 30 and rows[-1]['v'] in ('DOWN', 'GETUP', 'IDLE'): break
    srows, pts = script_rows(name, key)
    th = [r for r in rows if r['v'] == 'THROWN']
    ret_f = next((r['f'] for r in rows if r['f'] > 0 and r['p1'] != 'THROW'), None)
    bad = []
    for r in th:                                           # each frame: the place of the row the victim shows
        k = min(r['vrow'], len(srows) - 1); s = srows[k]
        want = (s[1] + s[5], max(0, s[2] + s[6]))
        if abs(want[0] - r['vx']) > 1 or abs(want[1] - r['vy']) > 1: bad.append(dict(f=r['f'], row=k, want=want, got=(r['vx'], r['vy'])))
    steps = [max(abs(b_['vx'] - a['vx']), abs(b_['vy'] - a['vy'])) for a, b_ in zip(th, th[1:])]
    sc = [max(abs(srows[i + 1][1] + srows[i + 1][5] - srows[i][1] - srows[i][5]),
              abs(max(0, srows[i + 1][2] + srows[i + 1][6]) - max(0, srows[i][2] + srows[i][6]))) for i in range(len(srows) - 1)]
    # across the release: the frames from 2 before to 2 after the control return, vs the script's own steps there
    win = [r for r in rows if ret_f is not None and ret_f - 2 <= r['f'] <= ret_f + 2]
    win_steps = [max(abs(b_['vx'] - a['vx']), abs(b_['vy'] - a['vy'])) for a, b_ in zip(win, win[1:])]
    k0 = pts['ret']
    own = max(sc[max(0, k0 - 3):k0 + 3]) if sc else 0
    stall = [r['f'] for a, r in zip(win, win[1:]) if (a['vx'], a['vy']) == (r['vx'], r['vy']) and a['vrow'] != r['vrow']
             and (srows[min(a['vrow'], len(srows) - 1)][1] + srows[min(a['vrow'], len(srows) - 1)][5],) !=
             (srows[min(r['vrow'], len(srows) - 1)][1] + srows[min(r['vrow'], len(srows) - 1)][5],)]
    out = dict(fighter=name, throw=key, ret_row=pts['ret'], control_return_frame=ret_f, frames_thrown=len(th),
               place_mismatches=len(bad), first_mismatches=bad[:4], release_window=[(r['f'], r['p1'], r['vrow'], r['vx'], r['vy'], r['vframe']) for r in win],
               release_steps=win_steps, script_steps_there=sc[max(0, k0 - 3):k0 + 3], stalls_at_release=stall)
    out['ok'] = len(th) > 20 and ret_f is not None and not bad and not stall and (max(win_steps) if win_steps else 0) <= own
    return out, rows


def kof98():
    """KOF98 Terry's forward throw on Yuri (the canonical capture): victim x / y per frame across Terry's return"""
    sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture')); import analyze as A
    p = os.path.join(HERE, '..', 'kof96', 'capture', 'throws98', '3.txt')
    r1, r2 = A.load(p, 1), A.load(p, 2)
    g0 = next(i for i in range(40, len(r2)) if A.state_of(r2[i][3]) >= 400)        # the victim's thrown state starts
    s0 = A.state_of(r1[g0][3]); x0 = A.x_of(r1[g0][3])
    ret = next(i for i in range(g0, len(r1)) if A.state_of(r1[i][3]) != s0)        # Terry's throw state ends
    win = []
    for i in range(ret - 4, ret + 5):
        w2 = r2[i][3]
        win.append(dict(f=i - g0, terry_state=A.state_of(r1[i][3]), victim_state=A.state_of(w2),
                        vx=round(A.x_of(w2) - x0, 2), vy=round(A.y_of(w2), 2)))
    steps = [round(max(abs(b['vx'] - a['vx']), abs(b['vy'] - a['vy'])), 2) for a, b in zip(win, win[1:])]
    return dict(control_return_frame=ret - g0, window=win, steps=steps)


def main():
    out, tag = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    if tag == 'kof98':
        r = kof98(); json.dump(r, open(os.path.join(out, 'kof98.json'), 'w'), indent=1); print(json.dumps(r)); return
    if tag.startswith('case:'):                            # one fighter per process (one core per process)
        _, t, name = tag.split(':')
        import harness as H
        b = H.Brawler(); res = {}
        for key in KEYS:
            res[key], rows = case(b, name, key)
            res[key]['rows'] = rows
        json.dump(res, open(os.path.join(out, f'{t}_{name}.json'), 'w'), indent=1); return
    names = sys.argv[3].split(',') if len(sys.argv) > 3 else ['terry', 'geese', 'billy_lee']
    res = {}
    for n in names:
        subprocess.run([sys.executable, __file__, out, f'case:{tag}:{n}'], check=True)
        res[n] = json.load(open(os.path.join(out, f'{tag}_{n}.json')))
        for key, r in res[n].items():
            print(tag, n, key, 'ok' if r['ok'] else 'HITCH', 'ret', r['ret_row'], 'mismatches', r['place_mismatches'],
                  'steps', r['release_steps'], 'script', r['script_steps_there'], 'stalls', r['stalls_at_release'], flush=True)
    res['all_ok'] = all(r['ok'] for n in names for r in res[n].values())
    json.dump(res, open(os.path.join(out, f'{tag}.json'), 'w'), indent=1)
    print(tag, 'ALL OK' if res['all_ok'] else 'FAIL')


if __name__ == '__main__':
    main()
