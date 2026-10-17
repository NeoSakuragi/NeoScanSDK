#!/usr/bin/env python3
"""Notes 20261017-133338-e03d / 20261017-133543-e03d (Robert, 0.10.164), in our emulator, before / after:

  1. a special cancelled out of a ground normal that hops (his ff + A Blitz = KOF98's forward + A, Kouryuu Koukyaku
     Geri) starts from the floor (fighter.c start_special: out of S_ATTACK, y = 0), not in the air at the hop's height;
  2. his down + C fireball (EX 236C, Ryuugeki Ken) knocks its victim back AWAY from him on the regular fireball arc
     (game.json proj_react knockdown), not the high launch the way it faced (back past Robert).

    robert1017_proof.py OUT [--before GAME_DIR]      GAME_DIR: an older build's examples/brawler (its brawler.neo + build/)
Each note runs its scenarios.json recipe (scenario.setup, the game's own lab path), logs P1 / the dummy per frame and
writes OUT/<note>_<label>.png (16 frames) + OUT/report.json. Run each build in its own process (the core is global)."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
NOTES = ['20261017-133338-e03d', '20261017-133543-e03d']


def one(game, label, out):
    import harness as H, scenario as S
    from PIL import Image, ImageDraw
    rec_all = S.recipes(); res = {}
    b = H.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); b.game = game
    for rid in NOTES:
        rec = rec_all[rid]; S.setup(b, rec)
        log, pics, t0 = [], [], b.frame
        def each(b):
            p, d = b.fighter(0), b.fighter(2)
            log.append(dict(t=b.frame - t0, p1=p['state'], p1y=round(p['y'], 1), p1x=round(p['x'], 1), anim=p['anim'],
                            spec=p['spec_ix'], dum=d['state'], dx=round(d['x'], 1), dy=round(d['y'], 1), face=d['facing']))
            if (b.frame - t0) % 3 == 0:
                data, w, h, pitch = b._video
                pics.append((b.frame - t0, Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')))
        b._want_video = True
        for part in [q for q in rec['do_keys'].split(',') if q]:
            n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''), each=each)
        b.run(int(rec.get('proof', 90)), each=each)
        b._want_video = False
        r = {}
        if rid == NOTES[0]:                                  # the special's first frame: P1's height
            st = [e for e in log if e['p1'] == 'SPECIAL']
            hop = [e['p1y'] for e in log if e['p1'] == 'ATTACK']
            r = dict(hop_max=max(hop or [0]), special_y0=st[0]['p1y'] if st else None, special_t=st[0]['t'] if st else None)
            keyt = st[0]['t'] if st else 30
        else:                                                # the dummy's flight after the fireball's hit
            kd = [e for e in log if e['dum'] == 'KNOCKDOWN']
            if kd:
                x0, p1x = kd[0]['dx'], kd[0]['p1x']
                r = dict(hit_t=kd[0]['t'], apex=max(e['dy'] for e in kd), travel=round(kd[-1]['dx'] - x0, 1),
                         away=(kd[-1]['dx'] - x0) * (x0 - p1x) > 0)
                keyt = kd[0]['t']
            else: keyt = 60
        res[rid] = r
        pick = [p for p in pics if keyt - 24 <= p[0]][:16]
        w, h = pick[0][1].size
        sh = Image.new('RGB', (w * 4, (h + 14) * 4), 'white'); dr = ImageDraw.Draw(sh)
        for i, (f, im) in enumerate(pick):
            e = log[f - 1] if f >= 1 else log[0]
            x, y = i % 4 * w, i // 4 * (h + 14); sh.paste(im, (x, y + 14))
            dr.text((x + 3, y + 1), f'{label} +{f}  P1 {e["p1"]} y{e["p1y"]:.0f}  dummy {e["dum"]} y{e["dy"]:.0f}', fill='black')
        sh.save(os.path.join(out, f'{rid}_{label}.png'))
        json.dump(log, open(os.path.join(out, f'{rid}_{label}.log.json'), 'w'))
    print(json.dumps({label: res}))


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
    ok = rep['after'][NOTES[0]].get('special_y0') == 0 and rep['after'][NOTES[1]].get('away') and rep['after'][NOTES[1]].get('apex', 999) < rep.get('before', {}).get(NOTES[1], {}).get('apex', 999) and rep['after'][NOTES[1]]['apex'] < 100
    print('ALL OK' if ok else 'FAIL')


if __name__ == '__main__':
    main()
