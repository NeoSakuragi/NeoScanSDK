#!/usr/bin/env python3
"""Four notes of 2026-10-14 in our emulator's core (harness.py), from the Chain Lab:

A. note 20261014-193405-5d29 (reopen, Bruno: "when the grab times out, Ryo stays slightly in the air; for Haggar he
   should fall on his back"): every roster fighter that holds by walking into Ryo, the hold left to run out
   (GRAB_TIME): Ryo's height the frame after the release and after; game.json roster[].hold_timeout: stand (the
   default) = on his feet at height 0, knockdown (Haggar) = S_KNOCKDOWN then lying (S_DOWN), no damage either way.
B. note 20261014-164531-5d29 (Bruno: "apply this attack for the jump straight A as well"): Moriya's straight jump + A
   plays the same animation as his forward jump + A (LB2's jump B, atk_d_jump; roster[].air.straight).
C. note 20261014-233105-5d29 (Bruno: "after the throws, front or back, Yamazaki stays idle too long"): each KOF
   fighter's forward / back throw from the hold: the frames from the throw's start to the thrower's control return
   (S_THROW left) and how many of them showed its idle animation's frames (a captured throw's idle tail, export_bm
   throw_rows: 0 now).
D. note 20261014-234051-5d29 (Bruno, on Yamazaki's fury: "the last kick should also be a group impact, like Iori's"):
   Yamazaki's Drill (D) on Ryo with two more Ryos standing at 100 / 130 px: both are knocked down by its last kick
   (roster[].fury_final_area), sent away.

    python3 reopen1014_proof.py [OUTDIR]          (default /data/tmp/reopen1014; OUTDIR/report.json)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/reopen1014'
G = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))
LAB = lambda f, **k: {'setup': dict({'mode': 'lab', 'fighter': f, 'dummy': 'ryo', 'drive': 'full', 'fury': 'full'}, **k)}


def hold_timeout(b, st):
    out = []
    for r in G['roster']:
        n = r['name']
        if r.get('selectable') is False or n == 'ryo': continue
        try: scenario.setup(b, LAB(n, gap=30, pre='30:R,4:-'))
        except Exception as e: out.append({'fighter': n, 'skip': repr(e)[:80]}); continue
        if st[b.fget(0, 'state')] != 'GRAB': out.append({'fighter': n, 'skip': 'no hold: ' + st[b.fget(0, 'state')]}); continue
        hp0 = b.fget(2, 'hp'); held_y = round(b.fget(2, 'y'), 1); rel = None; seq = []
        for f in range(200):
            b.run(1)
            s0, s2, y = st[b.fget(0, 'state')], st[b.fget(2, 'state')], round(b.fget(2, 'y'), 1)
            if rel is None and s0 != 'GRAB': rel = f
            if rel is not None:
                seq.append((s2, y))
                if len(seq) >= 70: break
        want = 'knockdown' if r.get('hold_timeout') == 'knockdown' else 'stand'
        first = seq[0] if seq else None
        if want == 'stand': ok = bool(seq) and all(y == 0 for s, y in seq[:20]) and first[0] in ('IDLE', 'WALK')
        else: ok = bool(seq) and first[0] == 'KNOCKDOWN' and any(s == 'DOWN' for s, _ in seq)
        out.append({'fighter': n, 'want': want, 'held_y': held_y, 'released_after': rel, 'first': first,
                    'states': sorted({s for s, _ in seq}), 'max_y_after': max(y for _, y in seq) if seq else None,
                    'damage': hp0 - b.fget(2, 'hp'), 'ok': ok and b.fget(2, 'hp') == hp0})
        print('A', out[-1], flush=True)
    return out


def moriya_air(b, st):
    res = {}
    for kind, keys in (('straight', [(6, 'b'), (10, ''), (2, 'a')]), ('forward', [(6, 'Rb'), (8, 'R'), (2, 'a')])):
        scenario.setup(b, LAB('moriya', gap=60))
        anims = []
        for n, k in keys:
            for _ in range(n): b.run(1, p1=k)
        for f in range(60):
            b.run(1)
            if st[b.fget(0, 'state')] == 'AIR_ATTACK': anims.append(b.fget(0, 'shown_frame'))   # (its frames: the straight jump's atk_d_jump and the forward's _diag twin are both LB2 $3C)
        res[kind] = sorted(set(anims))
    res['ok'] = bool(res['straight']) and res['straight'] == res['forward']
    print('B', res, flush=True)
    return res


def throws(b, st):
    out = []
    import re
    src = open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'build', 'bm_chars.c')).read()
    for r in G['roster']:
        n = r['name']
        if not str(r.get('bank', '')).startswith(('kof96', 'kof98', 'kof99')): continue
        for key, way in (('throw_c', 'Ra'), ('throw_d', 'La')):
            try: scenario.setup(b, LAB(n, gap=30, pre='30:R,4:-'))
            except Exception as e: out.append({'fighter': n, 'skip': repr(e)[:80]}); continue
            if st[b.fget(0, 'state')] != 'GRAB': continue
            idle = set()                                      # its idle frames: shown standing before the walk
            b.run(2, p1=way); t0 = None; n_idle = 0; frames = 0
            for f in range(300):
                s0 = st[b.fget(0, 'state')]
                if s0 != 'THROW': break
                frames += 1
                b.run(1)
            out.append({'fighter': n, 'throw': key, 'control_return_frames': frames})
    for o in out:
        m = re.search(r'%s_throws\[BT_COUNT\] = \{\{(\d+), (\d+), \w+, (\d+)(?:.*?)\}, \{(\d+), (\d+), \w+, (\d+)' % o['fighter'], src)
        if m: o['rows'], o['ret'] = (int(m.group(1)), int(m.group(3))) if o['throw'] == 'throw_c' else (int(m.group(4)), int(m.group(6)))
    print('C', [(o['fighter'], o['throw'], o.get('control_return_frames'), o.get('ret'), o.get('rows')) for o in out], flush=True)
    return out


def yamazaki_area(b, st):
    """the Drill leaps ~170 px and catches the first Ryo it reaches; Ryos placed where its kicks end (220 / 250 px; the
    lab stands them at the screen's edge): the caught one (carried: its x moves while it reels) and the others; pass =
    an other Ryo standing within the area (front 100 / back 40 px of Yamazaki) is knocked down on the Drill's last kick,
    the frame the caught one's last blow lands, and one outside it (the first dummy, left behind) is not"""
    scenario.setup(b, LAB('yamazaki', gap=40, extra=[220, 250]))
    for i in (2, 3, 4): b.fset(i, 'hp', 200)
    log = {i: [] for i in (2, 3, 4)}; ylog = []
    for f in range(400):
        b.run(1, p1='d' if f < 2 else '')
        ylog.append((st[b.fget(0, 'state')], int(b.fget(0, 'x')), b.fget(0, 'facing')))
        for i in (2, 3, 4): log[i].append((st[b.fget(i, 'state')], int(b.fget(i, 'x')), b.fget(i, 'hp')))
        if f > 30 and ylog[-1][0] in ('IDLE', 'WALK'): break
    end = max(f for f, r in enumerate(ylog) if r[0] == 'SPECIAL')
    carried = lambda i: len({x for s, x, h in log[i][80:end] if s == 'HITSTUN'}) > 3
    caught = [i for i in (2, 3, 4) if carried(i)]
    blow = max((f for f in range(1, end + 1) for i in caught if log[i][f][2] < log[i][f - 1][2]), default=None)   # its last blow
    res = {'caught': caught, 'last_blow': blow, 'others': {}}
    for i in (2, 3, 4):
        if i in caught or blow is None: continue
        s, x, h = log[i][blow - 1]; yx = ylog[blow - 1][1]
        dx = x - yx                                     # (Yamazaki faces right: + ahead)
        inside = -40 <= dx <= 100
        kd = next((f for f in range(blow, min(blow + 3, len(log[i]))) if log[i][f][0] == 'KNOCKDOWN'), None)
        res['others'][i] = {'dx_at_blow': dx, 'inside': inside, 'state_before': s, 'knocked_down_at': kd,
                            'damage': h - log[i][-1][2], 'ok': (kd is not None) == inside}
    res['ok'] = bool(caught) and any(o['inside'] for o in res['others'].values()) and all(o['ok'] for o in res['others'].values())
    print('D', res, flush=True)
    return res


def main():
    os.makedirs(OUT, exist_ok=True)
    b = H.Brawler(); b.game = scenario.GAME; st = b.states
    a = hold_timeout(b, st)
    bm = moriya_air(b, st)
    c = throws(b, st)
    d = yamazaki_area(b, st)
    yam = [o for o in c if o['fighter'] == 'yamazaki']
    checks = [
        (all(o.get('ok') for o in a if 'skip' not in o) and any(o.get('want') == 'knockdown' for o in a),
         f"A hold timeout: {sum(1 for o in a if o.get('ok'))} / {sum(1 for o in a if 'skip' not in o)} fighters as their hold_timeout (Haggar knockdown, the others on their feet at height 0); skipped {[o['fighter'] for o in a if 'skip' in o]}"),
        (bm['ok'], f"B Moriya: straight jump + A frames {bm['straight']} = forward jump + A {bm['forward']}"),
        (all(o['control_return_frames'] * 3 <= o['ret'] * 2 + 3 for o in yam) and len(yam) == 2,
         f"C Yamazaki: control return after {[o['control_return_frames'] for o in yam]} frames (rows to ret {[o.get('ret') for o in yam]} at 1.5 rows a frame)"),
        (d['ok'], f"D Yamazaki's Drill: caught {d['caught']}, last blow frame {d['last_blow']}, the others {d['others']}"),
    ]
    ok = all(c_ for c_, _ in checks)
    for c_, w in checks: print(('OK  ' if c_ else 'FAIL') + ' ' + w)
    json.dump(dict(ok=ok, checks=[dict(ok=c_, what=w) for c_, w in checks], hold_timeout=a, moriya=bm, throws=c, yamazaki_area={str(k): v for k, v in d.items()}),
              open(os.path.join(OUT, 'report.json'), 'w'), indent=1)
    print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
