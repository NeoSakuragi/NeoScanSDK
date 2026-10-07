#!/usr/bin/env python3
"""Billy's super (SUPER 236 = anim 82, the brawler's fury) and 623 connecting in a real fight, in our emulator
(TODO #192): per frame P1's animation / step / x and P2's (the victim's) animation / step / x / height / damage taken /
+$1F, plus every write to P2's +$1C (the reaction's animation) and +$0A (its height) with the writing pc.

    python3 fury_dd.py [OUT.json]       (default /data/neogeo_dict/doubledr/fury192.json)

Pictures of the super (placed case, every frame 40-199): /data/tmp/dd95/fury192/snap_<frame>.png (fury192_proof.py).
From the vs state (P1 Billy, P2 Jimmy idle; P1 / P2 placed at x 150 / 210 but in super_wall): P1 walks in, then 236 + A+B with the powered flag poked (+$00 bit 0, as
specials_dd.py), or 623 + D. One emulator process per capture."""
import json, sys
import cap_dd as c, dd
P1, P2 = 0x10042A, 0x10052A
OUT = '/data/neogeo_dict/doubledr/fury192.json'
# P1 / P2 placed at x 150 / 210 (+$06 poked on the first frames: the vs state's 324 / 384 puts the super's last
# hits against the stage's right edge, ~600)
PLACE = '100430=00,100431=96,100530=00,100531=D2'
CASES = {
    'super': ('30:R,12:-,2:D,2:DR,3:Rab,150:-', True),
    'super_wall': ('30:R,12:-,2:D,2:DR,3:Rab,150:-', 'wall'),
    '623D': ('30:R,12:-,2:R,2:D,3:DRd,120:-', False),
    '623D_close': ('44:R,4:-,2:R,2:D,3:DRd,120:-', False),
}

SNAPS = '/data/tmp/dd95/fury192'                 # the super's pictures (placed case): snap_<frame>.png, every frame 40-200

def capture(seq, powered, snaps=None):
    pk = [f'{f}:' + ','.join((['10042A=81'] if powered else []) + ([PLACE] if powered != 'wall' and f < 3 else []))
          for f in range(1, 60)]
    pokes = ';'.join(p for p in pk if not p.endswith(':'))
    rows = c.run(seq, pokes=pokes, wlog=['100546', '100534', '100536', '10055C', '10055E'], snaps=snaps)
    out = []
    for r in rows:
        R = r['ram']; F = dd.fighter_fields(R, P1); G = dd.fighter_fields(R, P2)
        out.append(dict(f=r['f'], a1=F['anim'], s1=F['step'], x1=F['x'], y1=488 - F['y'], a2=G['anim'], s2=G['step'],
                        x2=G['x'], y2=488 - G['y'], dmg=c.u16(R, P2 + 0x26), f1f=R[P1 + 0x1F - 0x100000],
                        e0=R[P2 + 0xE0 - 0x100000], e1=R[P2 + 0xE1 - 0x100000], snd=r['snd']))
    return out, rows[0]['wlog']

def summary(rec, first_anim):
    s = next(i for i, q in enumerate(rec) if q['a1'] == first_anim)
    hits = []
    for i in range(s, len(rec)):
        if rec[i]['dmg'] > rec[i - 1]['dmg']:
            hits.append(dict(t=i - s, step=rec[i]['s1'], damage=rec[i]['dmg'] - rec[i - 1]['dmg'], p2_anim=rec[i]['a2'],
                             p2_y=rec[i]['y2']))
    p2 = []
    for q in rec[s:]:
        if not p2 or p2[-1][0] != q['a2']: p2.append([q['a2'], q['f'] - rec[s]['f'], q['y2']])
    return dict(start=s, hits=hits, p2_anims=p2, p2_peak=max(q['y2'] for q in rec[s:]))

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else OUT
    res = {}
    import os, shutil
    from PIL import Image
    for k, (seq, pw) in CASES.items():
        sn = ','.join(str(f) for f in range(40, 200)) if k == 'super' else None
        rec, wl = capture(seq, pw, sn)
        if sn:
            os.makedirs(SNAPS, exist_ok=True)
            for f in sn.split(','):
                p = f'/data/tmp/dd95/snap_{f}.ppm'
                if os.path.exists(p): Image.open(p).save(f'{SNAPS}/snap_{f}.png'); os.remove(p)
        sm = summary(rec, 82 if k.startswith('super') else 90)
        res[k] = dict(seq=seq, summary=sm, rows=rec, wlog=wl)
        print(k, json.dumps({x: y for x, y in sm.items() if x != 'p2_anims'}), sm['p2_anims'])
    json.dump(res, open(out, 'w'))
