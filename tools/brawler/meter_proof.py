#!/usr/bin/env python3
"""Revamp phase 2 proof: the meter (fighter.c "the meter", game.json "meter"; Bruno 2026-10-08, docs/brawler_feel.md 8h),
in the Chain Lab's training (labdrive: P1 = the fighter, a dummy that only attacks when this script drives it), our
emulator's core (harness). Test-only pokes: positions, P1's meter and life (lab.p1_life = 1: its life left to the game),
the dummy's intent for the hit that puts P1 in a hit stun.

    python3 meter_proof.py OUT_DIR [FIGHTER ...]       -> OUT_DIR/meter2.json, hud_*.png, breaker_*.png, red_*.png

Per fighter (default Terry, Kim, Krauser, Haohmaru, Billy Lee):
  gain        from 0: the meter per frame for 400 frames (a point every meter.refill frames)
  special     full meter, C: SPECIAL, meter - special; meter short (special - 10: a refill point never closes the gap before the press), life full: SPECIAL, life - life_special,
              meter kept; meter short, life <= life_special: nothing
  breaker     P1 hit (a hit stun), C: SPECIAL with meter - breaker, brk on and the palette white on the blink's frames
              (ovl per frame) to its end; meter short (breaker - 10): SPECIAL, life - life_breaker; meter short and life
              <= life_breaker: no breaker (P1 stays in the hit stun)
  fury        meter full, D: the fury, meter 0; meter fury - 10: nothing
  max         meter full, down+D at full life: the fury (not the MAX); life at the red line (low % of 60) and under:
              the MAX (its spec_ix, fmax 1), at the line + 1: the fury; the red state's overlay per frame (OVL_RED 4 of
              16 frames) and none above it
  hud         (Terry) screenshots with 0, 1, 2, 3 stocks, and the red state (MAX mark shown)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from labdrive import Lab, PACK_STAT_OFF
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json'))); M = G['meter']
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
names = [r['name'] for r in G['roster']]
only = sys.argv[2:] or ['terry', 'kim', 'krauser', 'haohmaru', 'billy_lee']
L = Lab(); b = L.b; ST = b.states
BS_FURY = 6
LOW = 60 * M['low'] // 100                                   # the red line (life <= it)

def st(i=0): return ST[b.fget(i, 'state')]
def run(n, k=''): b.run(n, p1=k)
def free_life(on): b.w(L.lab + PACK_STAT_OFF + 1, 1, 1 if on else 0)
def settle(meter=None, hp=60):
    free_life(False)
    for _ in range(1500):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'shot') and not b.fget(0, 'brk'): break
        run(1)
    else: raise RuntimeError('P1 never idle: ' + b.brief((0, 2)))
    free_life(True); b.fset(0, 'hp', hp)
    if meter is not None: b.fset(0, 'meter', meter); b.fset(0, 'meter_t', 0)
def setpos(dist):
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30); b.fset(0, 'facing', 1); run(2)
def snap(): return dict(state=st(0), meter=b.fget(0, 'meter'), hp=b.fget(0, 'hp'), spec_id=b.fget(0, 'spec_id'),
                        spec_ix=b.fget(0, 'spec_ix'), brk=b.fget(0, 'brk'), ovl=b.fget(0, 'ovl'), fmax=b.fget(0, 'fmax'))
def press(keys, n=8):
    """keys on the first frame; the first frame P1 is in SPECIAL (or after n frames) -> its snapshot"""
    run(1, keys)
    for _ in range(n):
        if st(0) == 'SPECIAL': break
        run(1)
    return snap()
def hit_p1(meter, hp_after):
    """the dummy hits P1 (in a hit stun when this returns), P1's meter and life then set -> True when it took"""
    for dist in (26, 32, 20, 38):
        settle(meter); setpos(dist); b.intent(2, press=1, face=-1); run(1)
        for _ in range(40):
            if st(0) == 'HITSTUN': break
            run(1)
        else: continue
        while b.fget(0, 'freeze'): run(1)
        b.fset(0, 'meter', meter); b.fset(0, 'meter_t', 0); b.fset(0, 'hp', hp_after)
        return True
    return False
def sheet(paths, out, label):
    ims = [Image.open(p) for p, _ in paths]
    if not ims: return
    w, h = ims[0].size; cols = min(6, len(ims))
    S = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(S)
    for n, (im, (p, t)) in enumerate(zip(ims, paths)):
        x, y = (n % cols) * w, (n // cols) * (h + 14); S.paste(im, (x, y + 14)); d.text((x + 2, y + 1), label(t), fill='black')
        os.remove(p)
    S.save(out)

res = {}
for name in only:
    ci = names.index(name); F = CL['fighters'][ci]; R = G['roster'][ci]
    pool = [p['input'] for p in F['pool']]
    L.start(ci, 1 if ci == 0 else 0); run(30)
    r = res[name] = {}
    # ---- gain -----------------------------------------------------------------------------------------------------------
    settle(0); tr = []
    for _ in range(400): run(1); tr.append(b.fget(0, 'meter'))
    r['gain'] = {'meter_after': [tr[k] for k in (3, 7, 99, 199, 399)], 'trace_every_4': tr[3::4][:12],
                 'ok': tr[-1] == 400 // M['refill'] and tr[M['refill'] - 1] == 1 and tr[M['refill'] - 2] == 0}
    # ---- special: meter, life, neither ---------------------------------------------------------------------------------
    sp = r['special'] = {}
    settle(M['max']); setpos(80); s = press('c'); sp['meter'] = s
    sp['meter']['ok'] = s['state'] == 'SPECIAL' and s['meter'] == M['max'] - M['special'] and s['hp'] == 60
    settle(M['special'] - 10); setpos(80); s = press('c'); sp['life'] = s
    sp['life']['ok'] = s['state'] == 'SPECIAL' and s['meter'] < M['special'] and s['hp'] == 60 - M['life_special']
    settle(M['special'] - 10, hp=M['life_special']); setpos(80); s = press('c'); sp['neither'] = s
    sp['neither']['ok'] = s['state'] != 'SPECIAL' and s['hp'] == M['life_special']
    # ---- breaker: meter (blink), life, neither -----------------------------------------------------------------------------
    bk = r['breaker'] = {}
    for case, meter, hp in (('meter', M['max'], 40), ('life', M['breaker'] - 10, 40), ('neither', M['breaker'] - 10, M['life_breaker'])):
        if not hit_p1(meter, hp): bk[case] = {'ok': False, 'why': 'the dummy never hit P1'}; continue
        s0 = st(0); s = press('c', 2); e = dict(s, before=s0)
        if case == 'meter':
            ov, shots = [], []
            for k in range(400):
                if st(0) != 'SPECIAL': break
                ov.append(b.fget(0, 'ovl'))
                if name == 'terry' and k < 24:
                    p = os.path.join(OUT, f'_b{k}.png'); b.screenshot(p); shots.append((p, (k, b.fget(0, 'ovl'))))
                else: run(1)
            if shots: sheet(shots, os.path.join(OUT, 'breaker_blink_terry.png'), lambda t: f'frame {t[0]} ovl {t[1]}')
            run(2); e['ovl_frames'] = ''.join('W' if v == 1 else '.' for v in ov); e['after'] = snap()
            e['ok'] = s0 == 'HITSTUN' and s['state'] == 'SPECIAL' and s['meter'] == M['max'] - M['breaker'] and s['brk'] > 0 and \
                'W' * M['blink'] in e['ovl_frames'] and '.' * M['blink'] in e['ovl_frames'] and \
                e['after']['brk'] == 0 and e['after']['ovl'] == 0 and s['hp'] == hp
        elif case == 'life':
            e['ok'] = s0 == 'HITSTUN' and s['state'] == 'SPECIAL' and s['meter'] < M['breaker'] and s['hp'] == hp - M['life_breaker'] and s['brk'] > 0
        else:
            e['ok'] = s0 == 'HITSTUN' and s['state'] != 'SPECIAL' and s['hp'] == hp
        bk[case] = e
    # ---- fury / MAX ------------------------------------------------------------------------------------------------------
    fury = R.get('fury'); fu = r['fury'] = {}
    if fury and fury in pool:
        fix = pool.index(fury)
        mx = R.get('max') if R.get('max') in pool else 'MAX ' + fury if 'MAX ' + fury in pool else fury
        mix = pool.index(mx); form = R.get('form')
        settle(M['max']); setpos(60); s = press('d'); fu['full'] = dict(s, ok=s['state'] == 'SPECIAL' and s['spec_id'] == BS_FURY and s['spec_ix'] == fix and s['meter'] == M['max'] - M['fury'])
        settle(M['fury'] - 10); setpos(60); s = press('d', 20); fu['short'] = dict(s, ok=s['state'] != 'SPECIAL')
        if form and form['trigger'] == 'down+D full meter':
            fu['max'] = {'note': 'down+D = its form link (no MAX)', 'ok': True}
        else:
            mm = fu['max'] = {}
            for case, hp in (('full_life', 60), ('line+1', LOW + 1), ('line', LOW), ('low', 5)):
                settle(M['max'], hp=hp); setpos(60)
                ov = []
                for _ in range(32): ov.append(b.fget(0, 'ovl')); run(1)
                if name == 'terry' and case == 'low':
                    for k in range(16):
                        if b.fget(0, 'ovl') == 2 and (b.r(b.syms['hud_tick'], 2) & 8) == 0: break
                        run(1)
                    b.screenshot(os.path.join(OUT, 'red_state_terry.png'))
                b.fset(0, 'meter', M['max']); s = press('Dd')
                want_max = hp <= LOW
                mm[case] = dict(s, hp_set=hp, red_frames=''.join('R' if v == 2 else '.' for v in ov),
                                ok=s['state'] == 'SPECIAL' and s['spec_id'] == BS_FURY and
                                   s['spec_ix'] == (mix if want_max else fix) and s['fmax'] == (1 if want_max else 0) and
                                   s['meter'] == M['max'] - (M['max_fury'] if want_max else M['fury']) and
                                   (('R' * 4 in ''.join('R' if v == 2 else '.' for v in ov)) == want_max))
            settle(M['max_fury'] - 10, hp=5); setpos(60); s = press('Dd', 20); mm['low_short'] = dict(s, ok=s['state'] != 'SPECIAL')
        fu['ok'] = all(v.get('ok') for v in fu.values() if isinstance(v, dict) and 'ok' in v) and \
            all(v['ok'] for v in fu.get('max', {}).values() if isinstance(v, dict))
    # ---- HUD (Terry): 0..3 stocks, the red state --------------------------------------------------------------------------
    if name == 'terry':
        for k in range(4):
            settle(min(M['max'], k * M['stock'] + (M['stock'] // 2 if k < 3 else 0))); setpos(120); run(3)
            b.screenshot(os.path.join(OUT, f'hud_{k}_stocks.png'))
    oks = {'gain': r['gain']['ok'], 'special': all(v['ok'] for v in sp.values()), 'breaker': all(v['ok'] for v in bk.values()),
           'fury': fu.get('ok', True)}
    r['ok'] = oks
    print(name, ' '.join(f'{k}={"ok" if v else "FAIL"}' for k, v in oks.items()), flush=True)
    free_life(False)
json.dump(res, open(os.path.join(OUT, 'meter2.json'), 'w'), indent=1)
print('ALL OK' if all(all(v['ok'].values()) for v in res.values()) else 'FAILURES')
