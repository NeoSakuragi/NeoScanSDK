#!/usr/bin/env python3
"""The MAX cancel (note 20261016-133443-e03d, game.json max_cancel: KOF's Dream Cancel), round 2 (Bruno: "if you trigger
a MAX fury from a regular fury and you have the means (meter AND life bar AND condition), then there is the MAX fury's
freeze, plus the black background with some text. That's it. No weird light-punch frame, no broken conditions"). Per
fighter with a fury, in our emulator (harness.py, the Lab: scenario.setup mode lab, the dummy Ryo 60 px ahead, the fury
gauge full, a full 5-chunk drive bar):
0. the reference: at low life (life <= meter.low %, the life bar blinking red) down + D from neutral = the MAX: the frame
   the fighter shows through its super flash (fighter_t.shown_frame, sf_who set).
1. low life: D = the fury; once one of its hits lands, down + D every other frame. Checks: the MAX starts (fmax), drive
   spent = meter.max_drive chunks, the fury gauge emptied (paid as the MAX, fighter.c max_ready); its own super flash
   follows (sf_who) and through it the stage is hidden (bd_on) behind max_cancel.backdrop (the backdrop colour in palette
   RAM), MAX CANCEL in the big font (bt_s = big_text.max_cancel), the fighter showing the reference's MAX frames (never a
   normal's: shown_frame equal frame for frame); the text gone after the flash.
2. normal life (the bar not red): the same presses, no cancel: the fury plays on to its end.
3. D alone (no down) after the fury's hit, at low life: no cancel.
Screenshots OUT/<fighter>.png (the cancel's flash, its middle), OUT/<fighter>_max.png (the plain MAX's, the same frame).
Out: OUT/maxcancel.json

    python3 maxcancel_proof.py OUT [FIGHTER ...]     (default every roster fighter with a fury)   exit 1 on a FAIL"""
import ctypes as C, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
G = os.path.join(HERE, '..', '..', 'examples', 'brawler')
GJ = json.load(open(os.path.join(G, 'game.json')))
M = GJ['meter']; MC = GJ['max_cancel']

def lab(name, low):
    import harness as H, scenario as SC
    b = H.Brawler(game=G); b.game = G
    SC.setup(b, {'setup': {'mode': 'lab', 'fighter': name, 'dummy': 'ryo' if name != 'ryo' else 'terry', 'gap': 60,
                           'chunks': M.get('max_chunks', 4), 'drive': 'full', 'fury': 'full',
                           'hp': 60 * M['low'] // 100 if low else 60}})   # (the lab's P1 keeps it: lab.p1_life; 60 = LIFE)
    return b

def flash(b, shot=None):
    """from now to the end of the super flash (at most 120 frames to its start): [(shown_frame, bd_on, big use, backdrop)]"""
    S = b.syms; rows = []
    pal = (C.c_uint16 * 8192).from_address(b.core.retro_get_memory_data(104))   # (palette RAM: the backdrop $401FFE)
    for k in range(200):
        b.run(1)
        if b.r(S['sf_who'], 4):
            use = (b.r(S['bt_s'], 4) - S['gbig']) // 10 if b.r(S['bt_n'], 1) else None
            rows.append((b.fget(0, 'shown_frame'), b.r(S['bd_on'], 1), use, pal[0xFFF]))
        elif rows: break
        if not rows and k > 120: break
    return rows, None

def ref_max(name, shot, key='Dd'):
    b = lab(name, True); pre = b.save(); b.run(1, p1=key); b.run(1)
    st = b.states[b.fget(0, 'state')]
    rows, n = flash(b)
    if shot and rows:                                            # (a second run to the flash's middle for its picture)
        b.load(pre); b.run(1, p1=key); b.run(1)
        for k in range(200):
            b.run(1)
            if b.r(b.syms['sf_who'], 4): break
        b.run(len(rows) // 2 - 1); b.screenshot(shot)
    return {'state': st, 'key': key, 'fmax': b.fget(0, 'fmax'), 'frames': [r[0] for r in rows]}

def one(name, low, keys, shot=None):
    b = lab(name, low); S = b.syms
    st = lambda i=0: b.states[b.fget(i, 'state')]
    h0 = len(b.hits); b.run(1, p1='d'); b.run(1)
    r = {'fighter': name, 'low': low, 'keys': keys}
    def go(b, stop_at_cancel=True):
        for k in range(400):
            if st() != 'SPECIAL': return k, None, None
            hit = any(h[1] != 0 for h in b.hits[h0:])
            dr, fg = b.fget(0, 'drive'), b.fget(0, 'fgauge')
            b.run(1, p1=keys if hit and k % 2 == 0 else '')
            if b.fget(0, 'fmax'): return k, dr, fg
        return None, None, None
    k, dr, fg = go(b)
    if dr is None: r['fury_end'] = k; return r
    r.update(cancel_at=k, spent_chunks=(dr - b.fget(0, 'drive')) / M['chunk'], gauge_before=fg, gauge_after=b.fget(0, 'fgauge'))
    pre = b.save()
    rows, _ = flash(b)
    r['flash'] = {'frames': [x[0] for x in rows], 'bd_on': sum(1 for x in rows if x[1]), 'big_use': sorted({x[2] for x in rows}, key=str),
                  'backdrop': sorted({x[3] for x in rows}), 'n': len(rows)}
    b.run(2); r['text_after'] = b.r(S['bt_n'], 1)
    if shot and rows:
        b.load(pre)
        for k in range(200):
            b.run(1)
            if b.r(S['sf_who'], 4): break
        b.run(len(rows) // 2 - 1); b.screenshot(shot)
    return r

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    if sys.argv[2:3] == ['--one']:
        name, low, keys, shot = sys.argv[3], sys.argv[4] == '1', sys.argv[5], sys.argv[6] if len(sys.argv) > 6 else None
        print(json.dumps(one(name, low, keys, shot) if not keys.startswith('REF') else ref_max(name, shot, keys[3:] or 'Dd'))); return
    names = sys.argv[2:] or [r['name'] for r in GJ['roster'] if r.get('fury') and r['name'] != 'kuroko']
    import build_tables; big = list(build_tables.BIG_USES).index('max_cancel')   # (gbig's order: main.c BIG_*)
    bd = int(MC.get('backdrop', '0x0000'), 16)
    res, fails = {}, 0
    for n in names:
        run = lambda low, k, s=None: json.loads(subprocess.run([sys.executable, os.path.abspath(__file__), out, '--one', n, '1' if low else '0', k] + ([s] if s else []),
                                                               capture_output=True, text=True).stdout.strip().splitlines()[-1])
        ref = run(True, 'REF', os.path.join(out, f'{n}_max.png'))
        rr = next(r for r in GJ['roster'] if r['name'] == n)
        if not ref.get('fmax') and 'down+D' in str((rr.get('form') or {}).get('trigger')) and not rr.get('max'):
            ref = run(True, 'REFd', os.path.join(out, f'{n}_max.png'))   # (down + D from neutral is his form change and
                                                                 # he has no MAX of his own: his MAX = his fury, fury_buy)
            ref['fmax'] = 1
        a = run(True, 'Dd', os.path.join(out, f'{n}.png')); bb = run(False, 'Dd'); c = run(True, 'd')
        fl = a.get('flash') or {}
        checks = {
            'MAX from neutral at low life (the reference)': bool(ref.get('fmax')) and bool(ref.get('frames')),
            'cancelled at low life': 'cancel_at' in a,
            f'paid as the MAX: {M["max_drive"]} chunks, gauge emptied': abs(a.get('spent_chunks', -1) - M['max_drive']) < 0.01 and a.get('gauge_after') == 0,
            'its own super flash': fl.get('n', 0) > 0,
            "the MAX's frames through the flash (= the plain MAX's)": fl.get('frames') == ref.get('frames'),
            'stage hidden, backdrop max_cancel.backdrop': fl.get('bd_on') == fl.get('n') and fl.get('backdrop') == [bd],
            'MAX CANCEL in the big font through the flash': fl.get('big_use') == [big],
            'the text gone after the flash': a.get('text_after') == 0,
            'normal life: no cancel': 'cancel_at' not in bb,
            'D alone: no cancel': 'cancel_at' not in c}
        ok = all(checks.values())
        fails += not ok; res[n] = {'reference_max': ref, 'cancel': a, 'normal_life': bb, 'D_alone': c, 'checks': checks, 'ok': ok}
        print(('OK  ' if ok else 'FAIL'), n, {k: a.get(k) for k in ('cancel_at', 'spent_chunks')}, 'flash', fl.get('n'), 'frames',
              (fl.get('frames') or [])[:3], 'ref', (ref.get('frames') or [])[:3], [k for k, v in checks.items() if not v] or '', flush=True)
    json.dump(res, open(os.path.join(out, 'maxcancel.json'), 'w'), indent=1)
    print('ALL OK' if not fails else f'{fails} FAIL'); sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
