#!/usr/bin/env python3
"""TODO #204 (feedback 20261007-125822-b3f3, 0.1.9: "Billy Kane cannot be hit anymore ... Everything whiffs and I cannot
grab him"): Super Billy's two hold hits took Billy Kane's last 6 life points (GRAB_DAMAGE 3 each) while the hold went
on; no third hit came, the hold timed out (GRAB_TIME) and release() put him back on his feet with 0 life: every hit test
(hittable, the hold crowd, grabbable) skips a fighter without life, so he walked and attacked untouchable for good.
Fixed: a hold hit that takes the last life ends the hold like the finisher (the victim knocked down: S_DOWN -> S_DEAD).

    BRAWLER_CORE=<core> python3 hold204_proof.py GAME_DIR OUT TAG [FIGHTERS]   one build (one core per process)
        a: Bruno's case on stage 1 wave 5 (lab req 4, the game's own spawns): P1 Super Billy, every enemy but Billy Kane
           (fighter 6) taken off, Billy Kane's life 6; P1 walks into him (the grab), A, A (two hold hits), then nothing
           until the hold would time out; then A presses and walks into him: his states, life and the hits he takes
        b: every roster fighter (or FIGHTERS, comma separated) as P1 on Billy Kane with 3 life: one hold hit takes it
        c: the hold with life to spare (40): two hits then the escape, three hits (the finisher); then A hits him
    -> OUT/TAG.json + OUT/TAG_a.png (the case's pictures)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FOE = 6                                                    # Billy Kane in stage 1 wave 5 (spawn 4: fighter 6)


def stage_at(b, scen, fighter):
    scen.setup(b, {'setup': {'mode': 'stage', 'fighter': fighter, 'stage': 0, 'wave': 4, 'wait': 240}})
    for i in range(2, 8):
        if i != FOE: b.fset(i, 'state', b.states.index('OFF'))
    return b.save()


def grab_in(b, hp):
    """Billy Kane with `hp` life, P1 40 px to his left on his lane facing him; walk right into him until the grab"""
    b.fset(FOE, 'hp', hp); b.fset(FOE, 'inv', 0)
    b.place(0, x=b.fget(FOE, 'x') - 40, z=b.fget(FOE, 'z')); b.fset(0, 'facing', 1)
    for f in range(150):
        b.run(1, p1='R')
        if b.states[b.fget(0, 'state')] == 'GRAB': return f
    return None


def hold_hits(b, n, log):
    for k in range(n):
        b.run(2, p1='a')
        for _ in range(40):
            b.run(1); log.append(row(b))
            if b.states[b.fget(0, 'state')] != 'GRAB' or not b.fget(0, 'srow'): break


def row(b):
    return dict(f=b.frame, p1=b.states[b.fget(0, 'state')], foe=b.states[b.fget(FOE, 'state')], hp=b.fget(FOE, 'hp'),
                inv=b.fget(FOE, 'inv'), held=b.fget(FOE, 'held'))


def main(game, out, tag, only=None):
    import harness as H, scenario as scen
    from PIL import Image, ImageDraw
    H.OPTIONS.update(scen.SYSTEMS['mvs-mvs'])
    b = H.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); b.game = game
    names = scen.roster(game)
    res = {}
    # (a) Bruno's case
    start = stage_at(b, scen, 'billy_super'); b.load(start)
    g = grab_in(b, 6); log = []; pics = []
    def pic(label):
        b._want_video = True; b.run(1); b._want_video = False
        data, w, h, pitch = b._video
        pics.append((label, Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')))
    hold_hits(b, 2, log)
    pic(f'after 2 hold hits: Billy {log[-1]["foe"]} life {b.fget(FOE, "hp")}')
    for f in range(130):
        b.run(1); log.append(row(b))
        if f in (20, 60, 129): pic(f'+{f}: Billy {log[-1]["foe"]} life {log[-1]["hp"]}')
    after = len(b.hits)
    for k in range(6):                                     # A presses and walks into him (a grab), from his left
        b.place(0, x=b.fget(FOE, 'x') - 36, z=b.fget(FOE, 'z')); b.fset(0, 'facing', 1)
        b.run(3, p1='a'); b.run(25)
        b.place(0, x=b.fget(FOE, 'x') - 40, z=b.fget(FOE, 'z')); b.fset(0, 'facing', 1)
        b.run(30, p1='R'); log.append(row(b))
    pic(f'then: Billy {b.states[b.fget(FOE, "state")]} life {b.fget(FOE, "hp")}')
    took = [h for h in b.hits[after:] if h[1] == FOE]
    grabbed = any(r['foe'] in ('GRABBED', 'THROWN') for r in log[-6:]) or any(r['p1'] == 'GRAB' for r in log[-6:])
    seq = []
    for r in log:
        if not seq or seq[-1][1] != r['foe']: seq.append((r['f'], r['foe'], r['hp']))
    res['a'] = dict(grab_after=g, states=seq, dead=any(r['foe'] == 'DEAD' for r in log),
                    standing_without_life=any(r['foe'] in ('IDLE', 'WALK', 'ATTACK') and r['hp'] <= 0 for r in log),
                    hits_taken_after=len(took), ok=any(r['foe'] == 'DEAD' for r in log) and not any(r['foe'] in ('IDLE', 'WALK', 'ATTACK') and r['hp'] <= 0 for r in log))
    print(tag, 'a', json.dumps(res['a']), flush=True)
    w, h = pics[0][1].size
    sh = Image.new('RGB', (w * len(pics), h + 30), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), f'{tag}: Super Billy vs Billy Kane (stage 1 wave 5, life 6): two hold hits, then the hold left to time out; '
                   f'then A presses and walks into him: {len(took)} hits on him, ok={res["a"]["ok"]}', fill='black')
    for k, (lab, im) in enumerate(pics):
        sh.paste(im, (k * w, 30)); d.text((k * w + 4, 16), lab, fill='black')
    sh.save(os.path.join(out, f'{tag}_a.png'))
    # (b) every fighter's hold hit taking the last life
    res['b'] = {}
    for name in (only.split(',') if only else names):
        b.load(stage_at(b, scen, name))
        g = grab_in(b, 3); log = []
        if g is None: res['b'][name] = dict(ok=None, why='no grab'); print(tag, 'b', name, 'no grab', flush=True); continue
        hold_hits(b, 1, log)
        for f in range(200): b.run(1); log.append(row(b))
        dead = any(r['foe'] == 'DEAD' for r in log)
        bad = any(r['foe'] in ('IDLE', 'WALK', 'ATTACK') and r['hp'] <= 0 for r in log)
        res['b'][name] = dict(ok=dead and not bad, dead=dead, standing_without_life=bad,
                              states=[s for i, s in enumerate(r['foe'] for r in log) if i == 0 or s != log[i - 1]['foe']])
        print(tag, 'b', name, res['b'][name], flush=True)
    # (c) the hold with life to spare is unchanged: two hits then the escape (standing, life left, hittable); three hits
    # = the finisher (down, up again)
    res['c'] = {}
    for n in (2, 3):
        b.load(start); grab_in(b, 40); log = []
        hold_hits(b, n, log)
        for f in range(160): b.run(1); log.append(row(b))
        after = len(b.hits)
        for k in range(3):
            b.place(0, x=b.fget(FOE, 'x') - 36, z=b.fget(FOE, 'z')); b.fset(0, 'facing', 1); b.fset(FOE, 'inv', 0)
            b.run(3, p1='a'); b.run(40)
        seq = [s for i, s in enumerate(r['foe'] for r in log) if i == 0 or s != log[i - 1]['foe']]
        hp = b.fget(FOE, 'hp'); took = len([h for h in b.hits[after:] if h[1] == FOE])
        res['c'][f'{n}_hits'] = dict(states=seq, life_after_hold=log[-1]['hp'], hits_taken_after=took,
                                     ok=log[-1]['hp'] > 0 and 'DEAD' not in seq and took > 0 and
                                        (('KNOCKDOWN' in seq) if n == 3 else ('KNOCKDOWN' not in seq)))
        print(tag, 'c', n, res['c'][f'{n}_hits'], flush=True)
    res['all_ok'] = res['a']['ok'] and all(v['ok'] for v in res['b'].values() if v['ok'] is not None) and \
        all(v['ok'] for v in res['c'].values())
    json.dump(res, open(os.path.join(out, f'{tag}.json'), 'w'), indent=1)
    print(tag, 'ALL OK' if res['all_ok'] else 'FAIL')


if __name__ == '__main__':
    main(*sys.argv[1:5])
