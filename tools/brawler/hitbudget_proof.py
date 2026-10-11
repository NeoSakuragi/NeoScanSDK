#!/usr/bin/env python3
"""The projectile hit budget (docs/brawler_gold.md "Engine features", "Projectile hit budget"; note 20261011-134041-5d29:
"the Kaiser Wave can have maximum 10 hits before disappearing, but it can hit every character twice"): Krauser's Kaiser
Wave (the fury, D, and its MAX, down + D at low life) played in our emulator (harness.py, the Chain Lab's training: the
game's own path, no AI; scenario.py setup) in two layouts:
  crowd   six Ryos standing in its path (the lab's dummy + five copies in the free slots, scenario.py "extra"), their life
          kept up: every Ryo takes at most 2 hits, the wave vanishes (its end rows) on its 10th hit, the frame of it
  single  one Ryo: 2 hits, then the wave passes through him and flies on (no third hit, no end where he stands)
Per hit: frame, victim slot, its count so far, the damage, the wave's hits in all (fighter_t.vtot) and its x; the
wave's end (pend 1 = its end rows) or its flight off screen. Table + sheet (a frame on every hit and the wave's end) to
OUT (default /data/tmp/kaiser_hits).
    python3 hitbudget_proof.py [OUT]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H
import scenario as SC
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kaiser_hits'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
NPJ = 8
CASES = {
    'fury_crowd':  dict(keys='2:d', extra=[95, 120, 145, 170, 195], hp=None),
    'max_crowd':   dict(keys='2:Dd', extra=[95, 120, 145, 170, 195], hp=15),
    'fury_single': dict(keys='2:d', extra=[], hp=None),
    'max_single':  dict(keys='2:Dd', extra=[], hp=15),
}
PER, TOTAL = 2, 10                                         # game.json roster.krauser.proj_hits 641236C


def shot(b):
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def play(b, name, c):
    rec = {'setup': {'mode': 'lab', 'fighter': 'krauser', 'dummy': 'ryo', 'gap': 70, 'fury': 'full', 'drive': 'full',
                     'extra': c['extra'], **({'hp': c['hp']} if c['hp'] else {})}}
    SC.setup(b, rec)
    foes = [2] + [3 + k for k in range(len(c['extra']))]
    off = b.states.index('OFF'); proj = b.states.index('PROJ')
    b._want_video = True
    rows, pics, wave, end, seen = [], [], None, None, {}
    steps = [p.split(':') for p in c['keys'].split(',')]
    seq = [k for n, k in steps for _ in range(int(n))]
    for f in range(420):
        for i in foes:                                     # their life kept up (never beaten: each may take its hits)
            if b.fget(i, 'state') != off: b.fset(i, 'hp', 60)
        hp0 = {i: b.fget(i, 'hp') for i in foes}
        b.run(1, p1=seq[f] if f < len(seq) else '')
        if wave is None:                                   # the wave: the travelling entity that pierces (vper)
            wave = next((k for k in range(NPJ) if b.pget(k, 'state') == proj and b.pget(k, 'vper')), None)
            if wave is not None: born = f
        if wave is not None and end is None:
            st, pend = b.pget(wave, 'state'), b.pget(wave, 'pend')
            if st != proj or pend == 1: end = dict(f=f, how='end rows' if st == proj else 'gone', x=round(b.pget(wave, 'x'), 1),
                                                     vtot=b.pget(wave, 'vtot'))
        for i in foes:
            d = hp0[i] - b.fget(i, 'hp')
            if d > 0:
                seen[i] = seen.get(i, 0) + 1
                rows.append(dict(f=f, victim=i, nth=seen[i], dmg=d, state=b.states[b.fget(i, 'state')],
                                 wave_vtot=b.pget(wave, 'vtot') if wave is not None else None,
                                 wave_x=round(b.pget(wave, 'x'), 1) if wave is not None else None,
                                 victim_x=round(b.fget(i, 'x'), 1)))
                pics.append((f'{name} f{f} hit {len(rows)}: Ryo {i} #{seen[i]}', shot(b)))
        if end and end['f'] == f: pics.append((f'{name} f{f}: wave {end["how"]}', shot(b)))
        if end and f > end['f'] + 30: break
        if wave is not None and end is None and b.pget(wave, 'state') == off: break
    if end is None and wave is not None:
        end = dict(f=None, how='flying at the case end', x=round(b.pget(wave, 'x'), 1), vtot=b.pget(wave, 'vtot'))
    per = {i: seen.get(i, 0) for i in foes}
    if len(foes) > 1:                                      # crowd: <= 2 each, 10 in all, the wave ends on the 10th
        ok = (max(per.values()) <= PER and len(rows) == TOTAL and end is not None and end['how'] in ('end rows', 'gone')
              and end['f'] == rows[-1]['f'] and end['vtot'] == TOTAL)
    else:                                                  # single: 2 hits, then it flies on past him
        ok = len(rows) == PER and (end is None or end['how'] != 'end rows' or end['x'] > rows[-1]['victim_x'] + 40)
    return dict(ok=ok, wave_born=born if wave is not None else None, hits=rows, per_victim=per, end=end), pics


def sheet(pics, path):
    pics = pics[:30]
    if not pics: return
    w, h = pics[0][1].size; cols = 4; rws = (len(pics) + cols - 1) // cols
    S = Image.new('RGB', (cols * w, rws * (h + 16)), 'white'); d = ImageDraw.Draw(S)
    for n, (t, im) in enumerate(pics):
        x, y = (n % cols) * w, (n // cols) * (h + 16)
        S.paste(im, (x, y + 16)); d.rectangle([x, y + 16, x + w - 1, y + 16 + h - 1], outline='black'); d.text((x + 2, y + 2), t, fill='black')
    S.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    b = H.Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME); b.game = GAME
    res, allpics = {}, []
    for name, c in CASES.items():
        r, pics = play(b, name, c); res[name] = r; allpics += pics
        print(f"{name}: {'OK' if r['ok'] else 'FAIL'}  hits {len(r['hits'])} per victim {r['per_victim']} end {r['end']}", flush=True)
        for h in r['hits']: print(f"   f{h['f']:3} Ryo {h['victim']} #{h['nth']} dmg {h['dmg']} {h['state']:9} wave hits {h['wave_vtot']} wave x {h['wave_x']} victim x {h['victim_x']}")
    json.dump(res, open(os.path.join(OUT, 'hits.json'), 'w'), indent=1)
    with open(os.path.join(OUT, 'hits.tsv'), 'w') as fh:
        fh.write('case\tframe\tvictim\tnth\tdamage\tstate\twave_hits\twave_x\tvictim_x\n')
        for n, r in res.items():
            for h in r['hits']: fh.write(f"{n}\t{h['f']}\t{h['victim']}\t{h['nth']}\t{h['dmg']}\t{h['state']}\t{h['wave_vtot']}\t{h['wave_x']}\t{h['victim_x']}\n")
            fh.write(f"{n}\tEND\t{r['end']}\n")
    sheet([p for p in allpics if p[0].startswith('fury_crowd')], os.path.join(OUT, 'fury_crowd.png'))
    sheet([p for p in allpics if p[0].startswith('max_crowd')], os.path.join(OUT, 'max_crowd.png'))
    sheet([p for p in allpics if 'single' in p[0]], os.path.join(OUT, 'single.png'))
    print('ALL OK' if all(r['ok'] for r in res.values()) else 'FAIL: ' + ' '.join(n for n, r in res.items() if not r['ok']))
    sys.exit(0 if all(r['ok'] for r in res.values()) else 1)


if __name__ == '__main__':
    main()
