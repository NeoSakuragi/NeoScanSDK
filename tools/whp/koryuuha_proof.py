#!/usr/bin/env python3
"""TODO #147 proof: Hanzou's Ninpou Koryuu Ha (236 + A / B / A+B) read from WHP's code (handlers_whp.koryuuha) against
WHP in our emulator, and as the brawler plays each row of its variant table.

    python3 koryuuha_proof.py OUT_DIR [GAME_DIR]        (a normal build: the Chain Lab training, Hanzou vs the dummy)

1. The model vs WHP (handlers_whp.koryuuha_check), per press: the move's frames, the spawn frame, every flight frame
   of the object and its two parts (x, y, def), the life drop, the impact (def, drift) -> model_vs_whp in summary.
2. The brawler: the slot D special ('236P') with the brawler's rule (game.json roster[].variant, latched at the start:
   fighter_t.var), then every row (var poked on the special's first frame, before its program's first run: srow 0):
   per frame the projectile entity (x from Hanzou's start, height, frame), its spawn frame from the special's first
   frame, its speed, the move's frames; far (a whiff: the object flies off screen) and near (the dummy 150 px ahead:
   one hit, the end rows). Pass: spawn frame, speed, move length = WHP's, one hit.
3. Sheets per row: WHP (left, our emulator's screen) | brawler (right), every 3rd frame from the spawn:
   OUT_DIR/koryuuha_<press>.png; OUT_DIR/summary.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import handlers_whp as H, cap_whp as cap, capture_whp as C
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/var147/out'
EVERY = 3

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

def whp_snaps(press, frames, d):
    """WHP's screen on these frames of the hit recipe (koryuuha_capture's)"""
    b = {'A': 'a', 'B': 'b', 'AB': 'ab'}[press]
    seq = C.m('D DR R'.split(), b) + '150:-'; n = cap.nframes(seq); p2x = 400
    pk = ';'.join(f'{f}:100102={p2x * 128 >> 8 & 255:02X},100103={p2x * 128 & 255:02X}' for f in range(n))
    os.makedirs(d, exist_ok=True)
    cap.run(seq, '', pokes=pk, extra={'SNAPS': ','.join(map(str, frames)), 'SNAPDIR': d}, n=max(frames) + 2)
    return [Image.open(f'{d}/snap_{f}.ppm').convert('RGB') if os.path.exists(f'{d}/snap_{f}.ppm') else Image.new('RGB', (320, 224)) for f in frames]

def brawler_play(b, idx, var, dist, shots=None):
    lab_req(b, 1, idx['hanzo'], idx['terry']); b.run(40)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    camx = b.r(b.syms['cam_x'], 2)
    b.place(0, x=camx + 40, z=30); b.place(dm, x=camx + 40 + dist, z=30); b.fset(0, 'facing', 1); b.run(3)
    while b.states[b.fget(0, 'state')] != 'IDLE': b.run(1)
    x0 = b.fget(0, 'x'); h0 = len(b.hits); hp0 = b.fget(dm, 'hp')
    start = None; rule = None; srow0 = None; rows = []; cells = []; end = None
    for f in range(220):
        b.run(1, p1='c' if f < 3 else '')
        st = b.states[b.fget(0, 'state')]
        if st == 'SPECIAL' and start is None:
            start = f; rule = b.fget(0, 'var'); srow0 = b.fget(0, 'srow')
            if var is not None: b.fset(0, 'var', var)
        if start is None: continue
        if end is None and st != 'SPECIAL': end = f - start
        pj = None
        for i in range(8):
            if b.states[b.pget(i, 'state')] == 'PROJ':
                pj = {'x': round(b.pget(i, 'x') - x0, 3), 'y': round(b.pget(i, 'y'), 3), 'frame': b.pget(i, 'frame_ovr'),
                      'pend': b.pget(i, 'pend'), 'prow': b.pget(i, 'prow')}
        rows.append({'f': f - start, 'state': st, 'srow': b.fget(0, 'srow'), 'pj': pj, 'dummy_hp': b.fget(dm, 'hp')})
        if shots is not None and pj is None and rows and any(r['pj'] for r in rows[:-1]) and end is not None: break
        if shots is not None and (f - start) in shots:
            p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).convert('RGB'))
    hits = [(h[0], h[1], h[2]) for h in b.hits[h0:] if h[1] == dm]
    spawn = next((r['f'] for r in rows if r['pj']), None)
    fl = [r['pj']['x'] for r in rows if r['pj'] and not r['pj']['pend']]
    return {'rule_row': rule, 'played_row': var if var is not None else rule, 'srow_at_poke': srow0, 'move_frames': end,
            'spawn_frame': spawn, 'first_x': fl[0] if fl else None, 'speed': round((fl[-1] - fl[0]) / (len(fl) - 1), 4) if len(fl) > 1 else None,
            'flight_frames': len(fl), 'height': rows[spawn]['pj']['y'] if spawn is not None else None,
            'hits': len(hits), 'life_lost': hp0 - min(r['dummy_hp'] for r in rows), 'end_rows': sum(1 for r in rows if r['pj'] and r['pj']['pend'] == 1),
            'rows': rows}, cells

def main():
    import harness
    os.makedirs(OUT, exist_ok=True)
    game = sys.argv[2] if len(sys.argv) > 2 else harness.GAME
    G = json.load(open(os.path.join(game, 'game.json'))); names = [r['name'] for r in G['roster']]
    idx = {n: i for i, n in enumerate(names)}
    hz = next(r for r in G['roster'] if r['name'] == 'hanzo')
    res = {'slot_D': hz['specials']['D'], 'variant_rule': (hz.get('variant') or {}).get('236P', 'default (the heaviest, A+B)'),
           'model_vs_whp': {}, 'brawler': {}, 'pass': True}
    b = harness.Brawler(game=game)
    for _ in range(400): b.core.retro_run()
    # the brawler's rule: slot D played as is
    r, _ = brawler_play(b, idx, None, 400)
    res['brawler']['rule'] = {k: v for k, v in r.items() if k != 'rows'}
    print('rule: row', r['rule_row'], {k: r[k] for k in ('spawn_frame', 'speed', 'move_frames')}, flush=True)
    for v, press in enumerate(H.KORYUUHA):
        chk = H.koryuuha_check(press, True); res['model_vs_whp'][press] = chk
        M = H.koryuuha(press)
        far, _ = brawler_play(b, idx, v, 400)
        near, _ = brawler_play(b, idx, v, 150)
        shots = list(range(M['spawn_frame'], M['spawn_frame'] + 60, EVERY))
        _, cells = brawler_play(b, idx, v, 400, shots=shots)
        ok = (far['spawn_frame'] == chk['spawn_frame'] and abs(far['speed'] - M['object']['vx']) < 0.01 and far['move_frames'] == chk['move_frames']
              and near['hits'] == 1 and chk['mismatches'] == 0 and chk['impact_ok'])
        res['pass'] &= ok
        res['brawler'][press] = {'ok': ok, 'whp': {'spawn_frame': chk['spawn_frame'], 'speed': M['object']['vx'], 'move_frames': chk['move_frames'],
                                                   'hits': 1, 'life_drop_of_192': chk['life_drop'], 'height': M['object']['dy'],
                                                   'first_x': M['rows'][0]['x'], 'box_set': M['object']['box'], 'level': M['object']['level'],
                                                   'parts_vx': [p['vx'] for p in M['object']['parts']]},
                                 'far': {k: v_ for k, v_ in far.items() if k != 'rows'}, 'near': {k: v_ for k, v_ in near.items() if k != 'rows'}}
        print(press, 'ok' if ok else 'DIFF', res['brawler'][press]['whp'], {k: far[k] for k in ('spawn_frame', 'speed', 'move_frames', 'first_x', 'height')},
              'near hits', near['hits'], flush=True)
        # the sheet: WHP's frames from its spawn (capture frame = the move's first frame + spawn + k)
        rows = H.koryuuha_capture(press, True)
        s0 = next(i for i, q in enumerate(rows) if q['anim'] == M['anim'])
        wf = [rows[s0]['f'] + k + 2 for k in shots]           # (its screen shows a RAM dump's frame 2 frames later [meas])
        wcells = whp_snaps(press, wf, os.path.join('/data/tmp/var147', f'snap_{press}'))
        n = max(len(cells), len(wcells)); W, Hh = 320, 224
        sheet = Image.new('RGB', (2 * W, (Hh + 14) * n), 'white'); d = ImageDraw.Draw(sheet)
        for j in range(n):
            if j < len(wcells): sheet.paste(wcells[j].resize((W, Hh)), (0, j * (Hh + 14) + 14))
            if j < len(cells): sheet.paste(cells[j].resize((W, Hh)), (W, j * (Hh + 14) + 14))
            d.text((4, j * (Hh + 14) + 1), f'236{press}: move frame {shots[j]}  WHP (left) | brawler row {press} (right)', fill='black')
        sheet.save(os.path.join(OUT, f'koryuuha_{press}.png'))
    # the colours: every frame the rows draw uses the same palettes (one def cycle for the three presses)
    json.dump(res, open(os.path.join(OUT, 'summary.json'), 'w'), indent=1)
    print('PASS' if res['pass'] else 'FAIL', os.path.join(OUT, 'summary.json'))

if __name__ == '__main__':
    main()
