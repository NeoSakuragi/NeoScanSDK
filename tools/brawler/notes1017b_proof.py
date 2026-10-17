#!/usr/bin/env python3
"""The nine notes of 2026-10-17 on 0.10.165 (Haggar's balance, one special at a time, the map's black, the cheat's keys),
in our emulator (harness.py, the repo's Geolith core), before / after:

  haggar  (scenarios.json recipes, the Chain Lab: Haggar vs a standing Ryo)
    20261017-141149-e03d  run + A (the ff Blitz, the dash entry atk_c_close): the victim's knockdown apex (throw_launch.up
                          big -> medium) and the frames Haggar stays in it (+ 4: roster[].blitz_hit)
    20261017-141432-e03d  the chain mashed: the frames each link plays before the next (cut at the hit -> to its end:
                          roster[].chain.keep)
    20261017-141535-e03d  the fury: its pieces and hits (jab, jab, finisher x 3 -> x 2)
    20261017-141652-e03d  the jab's reach: the farthest gap (px, Ryo in front) it still hits (8 px less: roster[].box_trim)
    20261017-141826-e03d  the jab behind him: the farthest Ryo behind it still hits (16 px less: roster[].box_trim)
  ai      20261017-141933-e03d  stage waves with P1 kept alive (passive / walking): frames with two regular enemies in a special
                          at once (ai.rules.one_special: none), specials started
  map     20261017-114940-e03d  the stage start's map: lit pixels of the stage under it (the cycled neon pillar), from
                          the map's 4th frame (its first 3: the select screen's sprites leaving, every screen switch's)
          20261017-131927-e03d / 20261017-132400-e03d  the stage-clear cheat on DOWN + A + D (cheats.stage_clear_keys):
                          held 3 s in stage 1 -> PH_END, the win pose, the clear's map, the next screen

    notes1017b_proof.py OUT [--before GAME_DIR]     GAME_DIR: an older build's examples/brawler (brawler.neo + build/)
Writes OUT/<group>_<label>.png (one contact sheet per group) and OUT/report.json; ALL OK / FAIL on the after build."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
N_BLITZ, N_CHAIN, N_FURY, N_REACH, N_BACK = ('20261017-141149-e03d', '20261017-141432-e03d', '20261017-141535-e03d',
                                             '20261017-141652-e03d', '20261017-141826-e03d')
N_AI, N_MAP, N_CHEAT, N_CHEAT2 = '20261017-141933-e03d', '20261017-114940-e03d', '20261017-131927-e03d', '20261017-132400-e03d'


def pic(b):
    from PIL import Image
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def sheet(pics, path, cols=4):
    from PIL import Image, ImageDraw
    w, h = pics[0][1].size
    sh = Image.new('RGB', (w * cols, (h + 14) * ((len(pics) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sh)
    for i, (t, im) in enumerate(pics):
        x, y = i % cols * w, i // cols * (h + 14); sh.paste(im, (x, y + 14)); d.text((x + 3, y + 1), t, fill='black')
    sh.save(path)


def play(b, rec, each, extra=0):
    for part in [q for q in rec['do_keys'].split(',') if q]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''), each=each)
    b.run(int(rec.get('proof', 90)) + extra, each=each)


def haggar(b, label, out):
    import scenario as S
    R = S.recipes(); res = {}; pics = []
    # 1. run + A: the victim's apex, Haggar's frames in the attack
    S.setup(b, R[N_BLITZ]); t0 = b.frame; log = []; shots = {}
    def each(b):
        p, d = b.fighter(0), b.fighter(2); log.append((b.frame - t0, p['state'], p['anim'], d['state'], d['y']))
        if d['state'] == 'KNOCKDOWN' and (not shots or d['y'] > shots.get('y', -1)): shots.update(y=d['y'], im=pic(b), t=b.frame - t0)
    b._want_video = True; play(b, R[N_BLITZ], each); b._want_video = False
    att = [t for t, s, a, ds, dy in log if s == 'ATTACK']
    kd = [dy for t, s, a, ds, dy in log if ds == 'KNOCKDOWN']
    res['blitz'] = {'apex': round(max(kd or [0]), 1), 'attack_frames': len(att), 'hit': bool(kd)}
    if shots: pics.append((f'{label} run+A apex y{shots["y"]:.0f} (+{shots["t"]})', shots['im']))
    # 2. the chain mashed: each link's frames
    S.setup(b, R[N_CHAIN]); t0 = b.frame; log = []
    b._want_video = True; snap = []
    def each(b):
        p = b.fighter(0); log.append((b.frame - t0, p['state'], p['node'], p['anim']))
        if p['state'] == 'ATTACK' and (len(log) < 2 or log[-2][2] != p['node']): snap.append((f'{label} chain node {p["node"]} anim {p["anim"]} +{b.frame - t0}', pic(b)))
    play(b, R[N_CHAIN], each); b._want_video = False
    runs = []
    for t, s, nd, an in log:
        if s != 'ATTACK': continue
        if runs and runs[-1][0] == nd and runs[-1][2] == t - 1: runs[-1][1] += 1; runs[-1][2] = t
        else: runs.append([nd, 1, t, an])
    res['chain'] = {'links': [{'node': r[0], 'anim': r[3], 'frames': r[1]} for r in runs]}
    pics += snap[:3]
    # 3. the fury: its pieces and hits
    S.setup(b, R[N_FURY]); t0 = b.frame; nh0 = len(b.hits); pieces = []; last = None
    def each(b):
        nonlocal last
        p = b.fighter(0)
        k = (p['state'], p['spec_ix'])
        if p['state'] == 'SPECIAL' and k != last: pieces.append(p['spec_ix'])
        last = k
    play(b, R[N_FURY], each, 200)
    fh = [h for h in b.hits[nh0:] if h[1] == 2]
    res['fury'] = {'pieces': pieces, 'hits': len(fh), 'damage': sum(h[2] for h in fh)}
    # 4 / 5. the jab's reach in front and behind: the farthest gap it hits
    S.setup(b, {'setup': R[N_REACH]['setup']}); base = b.save(); x0 = b.fget(0, 'x')
    def jab_hits(dx):
        b.load(base); b.fset(2, 'x', x0 + dx); b.fset(2, 'facing', (-1 if dx > 0 else 1) & 0xFF); b.run(1)
        n0 = len(b.hits); b.run(2, p1='a'); b.run(30)
        return any(h[1] == 2 for h in b.hits[n0:])
    front = [g for g in range(60, 121, 2) if jab_hits(g)]
    back = [g for g in range(2, 61, 2) if jab_hits(-g)]
    res['reach'] = {'front_max': max(front) if front else None, 'behind_max': max(back) if back else None}
    sheet(pics, os.path.join(out, f'haggar_{label}.png'))
    return res


def ai(b, label, out):
    import scenario as S
    res = {'runs': []}; pics = []
    # the waves where 0.10.166 had two regular enemies in a special at once (a scan of every wave, P1 passive / walking
    # left and right every 2 s, 3000 frames: stage 2 waves 2-4, stage 3 wave 3)
    for st, wv, walk in ((1, 1, 1), (1, 2, 0), (1, 3, 1), (2, 2, 1)):
        S.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': st, 'wave': wv}})
        both = 0; started = 0; prev = {}; best = None
        for t in range(3000):
            if t % 30 == 0: b.fset(0, 'hp', b.fget(0, 'hp_max'))      # P1 kept alive
            b.run(1, p1=('L' if (t // 120) % 2 else 'R') if walk else '')
            boss = b.r(b.syms['phase'], 1) == 2
            sp = [i for i in range(2, 8) if not (boss and i == 2) and b.fighter(i)['state'] == 'SPECIAL']
            for i in range(2, 8):
                s = b.fighter(i)['state']
                if s == 'SPECIAL' and prev.get(i) != 'SPECIAL' and not (boss and i == 2): started += 1
                prev[i] = s
            if len(sp) >= 2:
                both += 1
                if best is None: b._want_video = True; b.run(1); b._want_video = False; best = pic(b)
        res['runs'].append({'stage': st + 1, 'wave': wv + 1, 'walk': walk, 'specials_started': started, 'frames_two_at_once': both})
        if best: pics.append((f'{label} stage {st + 1} wave {wv + 1}: two specials at once', best))
    res['frames_two_at_once'] = sum(r['frames_two_at_once'] for r in res['runs'])
    res['specials_started'] = sum(r['specials_started'] for r in res['runs'])
    if pics: sheet(pics[:8], os.path.join(out, f'ai_{label}.png'))
    return res


def maps(b, label, out):
    import scenario as S, harness as H
    res = {}; pics = []
    S.setup(b, {'setup': {'mode': 'select', 'cursor': 'terry'}})
    lit = []; b._want_video = True
    def each(b):
        if b.r(b.syms['map_on'], 1) and b.r(b.syms['in_ph'], 1) == 1:
            im = pic(b); px = im.load()
            n = sum(1 for y in range(0, 200) for x in range(0, 28) if sum(px[x, y]) > 24)
            lit.append(n)
            if len(lit) in (20, 90): pics.append((f'{label} stage start map +{len(lit)}: {n} lit px left strip', im))
    b.run(30, each=each); b.run(3, p1='a', each=each); b.run(420, each=each); b._want_video = False
    res['start_map'] = {'frames': len(lit), 'max_lit_left_strip': max(lit[3:] or [0]),   # (its first 3 frames: the select
                        'switch_frames_lit': lit[:3]}                  # screen's sprites still leaving, as every screen switch)
    for keys, full in (('Dad', 0), ('Dabcd', 0), ('Dad', 1)):     # (full: drive + fury full, the D press plays his MAX)
        S.setup(b, {'setup': dict({'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 1}, **({'drive': 'full', 'fury': 'full'} if full else {}))})
        b.run(20); t = 0; hold = json.load(open(os.path.join(b.game, 'game.json')))['cheats']['stage_clear_hold']
        while b.r(b.syms['phase'], 1) < 3 and t < hold + 30: b.run(1, p1=keys); t += 1
        r = {'end_after': t if b.r(b.syms['phase'], 1) >= 3 else None}
        if r['end_after'] is not None:
            seen = False; b._want_video = True; shot = 0
            for k in range(900):
                b.run(1)
                m = b.r(b.syms['map_on'], 1)
                if m and not seen: seen = True; r['map_at'] = k
                if m and keys == 'Dad' and shot < 2 and (k - r['map_at']) in (10, 60): pics.append((f'{label} cheat {keys}: clear map +{k}', pic(b))); shot += 1
                if seen and not m: r['map_closed_at'] = k; break
            b._want_video = False
            r['map'] = seen; m0 = b.r(b.syms['mode'], 1)
            for k in range(1200):                                # the next screen (stage 1: the bonus)
                if b.r(b.syms['mode'], 1) != m0 or b.r(b.syms['bonus_on'], 1): break
                b.run(1)
            r['next'] = {'after': k, 'mode': b.r(b.syms['mode'], 1), 'bonus_on': b.r(b.syms['bonus_on'], 1)}
        res['cheat_' + keys + ('_full' if full else '')] = r
    sheet(pics, os.path.join(out, f'map_{label}.png'))
    return res


def one(game, label, out):
    import harness as H
    b = H.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); b.game = game
    rep = {'haggar': haggar(b, label, out), 'ai': ai(b, label, out), 'map': maps(b, label, out)}
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
    json.dump(rep, open(os.path.join(out, 'report.json'), 'w'), indent=1)
    print(json.dumps(rep, indent=1))
    A, B = rep['after'], rep.get('before')
    ok = {
        'blitz lower': A['haggar']['blitz']['hit'] and (not B or A['haggar']['blitz']['apex'] < B['haggar']['blitz']['apex']),
        'blitz +4 frames': not B or A['haggar']['blitz']['attack_frames'] == B['haggar']['blitz']['attack_frames'] + 4,
        'fury 2 groups': A['haggar']['fury']['hits'] == 14,
        'jab reach -8': not B or (A['haggar']['reach']['front_max'] or 0) == (B['haggar']['reach']['front_max'] or 0) - 8,
        'jab behind -16': not B or (A['haggar']['reach']['behind_max'] or 0) <= (B['haggar']['reach']['behind_max'] or 0) - 16,
        'one special': A['ai']['frames_two_at_once'] == 0 and A['ai']['specials_started'] > 0,
        'map black': A['map']['start_map']['max_lit_left_strip'] < 10,
        'cheat DOWN+A+D': all(A['map'][k].get('end_after') is not None and A['map'][k].get('map') and A['map'][k]['next']['bonus_on']
                              for k in ('cheat_Dad', 'cheat_Dad_full')),
        'chain to the end': not B or all(a['frames'] > b_['frames'] for a, b_ in zip(A['haggar']['chain']['links'][:2], B['haggar']['chain']['links'][:2])),
    }
    for k, v in ok.items(): print(('ok   ' if v else 'FAIL ') + k)
    print('ALL OK' if all(ok.values()) else 'FAIL')


if __name__ == '__main__':
    main()
