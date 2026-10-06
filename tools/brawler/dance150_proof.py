#!/usr/bin/env python3
"""TODO #150 proof: a dance fury catching an airborne victim (fighter.c react "the dance's catch", DANCE_DROP) and a dead
body never hit again (fighter.c dead_body), harness.py on a `make AI_OFF=1` build (the enemies stand still).

    python3 dance150_proof.py [OUT_DIR] [FIGHTER ...]   (default /data/tmp/boss172/out, Robert 3 and Ryo 1)

Per fighter, P1 fires the fury (D, meter full) at an enemy 60 px ahead:
  ground     the victim standing (the baseline: the dance's hits on a ground victim)
  airborne   the note's case (feedback 20261006-160204-b3f3): 3 frames before the ground case's first hit the victim is
             put in a juggle at 40 px (test poke: S_KNOCKDOWN, rising 1 px a frame), alive. Pass: the first fury hit lands
             on it in the air, it stays in its reel (S_HITSTUN, vx 0) and drops to the floor within 30 frames (its hit-stops included; a catch's
             hold may place it at once), every
             later dance hit lands (as many hits as the ground case), only the finisher knocks it down
  group      the note's scene: the same airborne victim + a dead body in its KO flight put between P1 and it at the
             same moment (life -7, y 60: test poke) + one enemy standing behind. Pass: the dead body is never hit (no life lost, no
             hit-stop), falls and dies; the airborne one is caught as above
Out: dance150.json, dance150_<fighter>.png (contact sheets: airborne + group)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 2 or (len(sys.argv) > 1 and not sys.argv[1].isdigit()) else '/data/tmp/boss172/out'
FIGHTERS = [int(a) for a in sys.argv[1:] if a.isdigit()] or [3, 1]
os.makedirs(OUT, exist_ok=True)
BA_BLOWBACK, BA_KNOCKDOWN_FLIGHT = 24, 25
b = Brawler(); ST = b.states; st = ST.index

def setup(start, case):
    b.load(start)
    for i in range(2, 8): b.fset(i, 'state', st('OFF'))
    for i in (0, 2) + ((3, 4) if case == 'group' else ()):
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.fset(i, 'vx', 0); b.fset(i, 'vy', 0); b.intent(i)
    b.place(0, x=100, z=20); b.fset(0, 'facing', 1); b.fset(0, 'meter', 120)
    b.place(2, x=160, z=20); b.fset(2, 'facing', 0xFF)
    if case == 'group':
        b.place(3, x=140, z=62); b.fset(3, 'facing', 0xFF)    # the dead body: off the lane until its poke
        b.place(4, x=200, z=18); b.fset(4, 'facing', 0xFF)    # one standing behind

def airborne(i, y, vy, hp):
    b.fset(i, 'state', st('KNOCKDOWN')); b.fset(i, 'y', y); b.fset(i, 'vy', vy); b.fset(i, 'vx', 0.5); b.fset(i, 'hp', hp)
    b.fset(i, 'anim', BA_BLOWBACK); b.fset(i, 'step', 0); b.fset(i, 'kmode', 0); b.fset(i, 'state_t', 0)

def play(case, shots, poke_at=None):
    rows, poked, h0 = [], None, len(b.hits)
    for f in range(400):
        sp = ST[b.fget(0, 'state')] == 'SPECIAL'
        if case != 'ground' and f == poke_at:                 # 3 frames before the ground case's first hit
            airborne(2, 40, 1, 60); poked = f
            if case == 'group':                                # into the rush, in its KO flight, dead
                airborne(3, 60, 1.5, -7); b.place(3, x=(b.fget(0, 'x') + b.fget(2, 'x')) / 2, z=21)
        k = 'd' if f < 3 else ''
        if shots is not None and poked is not None and f - poked < 120 and (f - poked) % 8 == 0:
            p = os.path.join(OUT, f'_s{len(shots)}.png'); b.pad = [set(k), set()]; b._want_video = True; b.run(1, p1=k); b._want_video = False
            data, w, h, pitch = b._video
            Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(p)
            shots.append((p, f'{case} +{f - poked}: v {ST[b.fget(2, "state")][:5]} y{b.fget(2, "y"):.0f}' +
                          (f' dead {ST[b.fget(3, "state")][:5]} y{b.fget(3, "y"):.0f}' if case == 'group' else '')))
        else: b.run(1, p1=k)
        rows.append(dict(f=f, p1=(ST[b.fget(0, 'state')], b.fget(0, 'spec_id')),
                         v={i: (ST[b.fget(i, 'state')], round(b.fget(i, 'y'), 1), round(b.fget(i, 'vx'), 2), b.fget(i, 'hp'), b.fget(i, 'freeze'))
                            for i in ((2, 3, 4) if case == 'group' else (2,))}))
        if not sp and f > 60 and ST[b.fget(0, 'state')] != 'SPECIAL' and all(r['p1'][0] != 'SPECIAL' for r in rows[-30:]): break
    hits = [h for h in b.hits[h0:]]
    return rows, hits, poked

res = {}
for F in FIGHTERS:
    b.pick(F); start = b.save(); shots = []; out = {}
    for case in ('ground', 'airborne', 'group'):
        setup(start, case); b.hits.clear()
        rows, hits, poked = play(case, shots if case != 'ground' else None, out['ground']['hit_rows'][0] - 3 if case != 'ground' else None)
        vh = [(f - b.frame + len(rows) - 1, i, d, s) for f, i, d, s in hits]   # frame -> row index
        v2 = [h for h in vh if h[1] == 2]
        o = dict(poked=poked, hits_on_victim=len(v2), hit_rows=[h[0] for h in v2])
        if case != 'ground' and v2:
            h1 = v2[0][0]; after = rows[h1 + 1:h1 + 40]
            o['y_at_first_hit'] = rows[h1 - 1]['v'][2][1] if h1 > 0 else None
            o['state_after_first_hit'] = rows[h1]['v'][2][0]
            o['vx_after_first_hit'] = rows[h1]['v'][2][2]
            o['frames_to_floor'] = next((k for k, r in enumerate(rows[h1:]) if r['v'][2][1] == 0), None)
            fin = v2[-1][0]
            o['states_between'] = sorted(set(r['v'][2][0] for r in rows[h1:fin]))
            o['state_after_last_hit'] = rows[min(fin + 3, len(rows) - 1)]['v'][2][0]
        if case == 'group':
            d3 = [h for h in vh if h[1] == 3]
            o['dead_body_hits'] = len(d3)
            o['dead_body_states'] = list(dict.fromkeys(r['v'][3][0] for r in rows))
            o['dead_body_hp'] = [rows[poked]['v'][3][3], rows[-1]['v'][3][3]]
            o['standing_hits'] = len([h for h in vh if h[1] == 4])
        out[case] = o
    g = out['ground']['hits_on_victim']
    for case in ('airborne', 'group'):
        o = out[case]
        o['pass'] = bool(o['hits_on_victim'] == g and (o.get('y_at_first_hit') or 0) > 20 and o.get('state_after_first_hit') == 'HITSTUN'
                         and o.get('vx_after_first_hit') == 0 and o.get('frames_to_floor') is not None and o['frames_to_floor'] <= 30
                         and o.get('states_between') == ['HITSTUN'] and (case != 'group' or (o['dead_body_hits'] == 0 and 'DEAD' in o['dead_body_states']
                                                                                              and o['dead_body_hp'][0] == o['dead_body_hp'][1])))
    res[F] = out
    print(F, json.dumps(out))
    if shots:
        ims = [(Image.open(p), l) for p, l in shots]
        w, h = ims[0][0].size; cols = 5; nr = (len(ims) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * w, nr * (h + 14)), 'white'); d = ImageDraw.Draw(sheet)
        for i, (im, l) in enumerate(ims):
            x, y = (i % cols) * w, (i // cols) * (h + 14); sheet.paste(im, (x, y + 14)); d.rectangle([x, y + 14, x + w - 1, y + 13 + h], outline='black'); d.text((x + 2, y + 1), l, fill='black')
        sheet.save(f'{OUT}/dance150_{F}.png')
        for p, _ in shots: os.remove(p)
json.dump(res, open(f'{OUT}/dance150.json', 'w'), indent=1)
ok = all(res[F][c]['pass'] for F in res for c in ('airborne', 'group'))
print('ALL PASS' if ok else 'FAIL')
