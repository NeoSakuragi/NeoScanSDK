#!/usr/bin/env python3
"""Hit marks on screen at once (fighter.c hit_spark, HMARK_MAX; Bruno 2026-10-11: limit the sprites SS2's blood splashes
take, against CPU slowdown): Haohmaru's data as P1 in the first stage fight, every enemy of the wave kept in front of him (kept alive), A mashed for 900
frames; per frame the projectile entities alive (with only A pressed: his hit marks) -> max / frames over the cap, before
vs after (one process per build); a screenshot of the busiest frame of each.
    python3 hitmark_cap_proof.py BEFORE_GAME_DIR AFTER_GAME_DIR [OUT]   (dirs with brawler.neo + build/; default OUT /data/tmp/hmark)"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
OUT = sys.argv[3] if len(sys.argv) > 3 else '/data/tmp/hmark'
CAP = 2

def child(tag, game):
    import harness
    b = harness.Brawler(rom=os.path.join(game, 'brawler.neo'), game=game, tick_sync=True)      # (each build's own symbols)
    GAME = game
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    b.to_fight(cache=False)                                  # a stage fight: its wave's enemies, all kept in front of P1,
    b.fset(0, 'ch', b.syms['bm_chars'] + bcs.index('BC_HAOHMARU') * b.syms['sizeof_bchar'])   # P1 = Haohmaru's data
    off = b.states.index('OFF')
    src = next(i for i in range(1, 8) if b.fget(i, 'state') != off and i != 0)       # wave 1 has one enemy: three copies
    blob = bytes(b.r(b.base + src * b.fsize + k, 1) for k in range(b.fsize))         # of him in free slots (a crowd: one
    for i in [i for i in range(2, 8) if b.fget(i, 'state') == off][:3]:               # A hits them all at once, a mark each)
        for k, v in enumerate(blob): b.w(b.base + i * b.fsize + k, 1, v)
    hist, best, lag, lag_mark = [], -1, 0, 0
    tk = b.r(b.syms['hud_tick'], 2)
    for t in range(900):
        x, z = b.fget(0, 'x'), b.fget(0, 'z'); b.fset(0, 'facing', 1); b.fset(0, 'hp', 60)
        for k, i in enumerate(range(2, 8)):
            if b.fget(i, 'state') != off: b.place(i, x=x + 40, z=z); b.fset(i, 'hp', 60)
        b.run(1, p1='a' if t % 6 < 2 else '')
        n = sum(1 for i in range(8) if b.pget(i, 'state') != off)            # (NPJ = 8)
        hist.append(n)
        t2 = b.r(b.syms['hud_tick'], 2)
        if t2 == tk: lag += 1; lag_mark += n > 0                # a lag frame: the game did not finish a tick
        tk = t2
        if n > best: best = n; b.screenshot(os.path.join(OUT, f'{tag}_busiest.png'))
    r = {'max': max(hist), 'over': sum(1 for n in hist if n > CAP), 'any': sum(1 for n in hist if n), 'hits': len(b.hits), 'lag': lag, 'lag_with_marks': lag_mark}
    json.dump(r, open(os.path.join(OUT, f'_{tag}.json'), 'w'))

if len(sys.argv) > 4: child(sys.argv[4], {'before': sys.argv[1], 'after': sys.argv[2]}[sys.argv[4]]); sys.exit(0)
os.makedirs(OUT, exist_ok=True)
for tag in ('before', 'after'): subprocess.run([sys.executable, __file__, sys.argv[1], sys.argv[2], OUT, tag], check=True)
R = {t: json.load(open(os.path.join(OUT, f'_{t}.json'))) for t in ('before', 'after')}
for t in R: print(f"{t}: hit marks alive max {R[t]['max']}, frames with more than {CAP}: {R[t]['over']}, frames with any: {R[t]['any']}, hits {R[t]['hits']}, lag frames {R[t]['lag']} ({R[t]['lag_with_marks']} with marks)")
ok = R['after']['max'] <= CAP and R['after']['any'] > 0 and R['after']['hits'] == R['before']['hits']
print('ALL OK' if ok else 'FAIL'); sys.exit(0 if ok else 1)
