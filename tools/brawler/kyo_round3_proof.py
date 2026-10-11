#!/usr/bin/env python3
"""Kyo round 3 proofs (Bruno's notes 20261011-205823 / 205309 / 210011-5d29, game 0.10.61), harness.py on the build in
GAME_DIR, our emulator only (one core, this process).

    python3 kyo_round3_proof.py fire GAME_DIR [OUT]   Kyo's C (623C) and down,down + A (623A) from idle, nobody near: per
                                                      frame his world x / height and every live projectile entity's
                                                      (the fires, KOF98 states 245 / 246), a screenshot every 2 frames
                                                      (OUT/<move>_NNN.png + OUT/<move>.png sheet); each fire must stay
                                                      where it was born (world x / height constant over its life) while
                                                      he rises, as KOF98 keeps them (OUT/kof98_trace.json, measured by
                                                      tools/kof96/capture/romspecials98.trace: fire 1 at his place, fire
                                                      2 at his place and height when born) -> OUT/fire.json
    python3 kyo_round3_proof.py fury GAME_DIR         down + D with ONE drive chunk, low life, the gauge full (the MAX's
                                                      cost not met, the fury's met) and with the gauge full at normal life
                                                      (not the red state): the fury must play, paying the fury's chunk;
                                                      with two chunks in the red state the MAX still plays; a KOF (kyo),
                                                      an SS2 (haohmaru) and a Double Dragon (cheng_fu) fighter
(note 20261011-205823-5d29, the chain's far A starter: arb_compile.py's own slot check, a1 PASS)
Exit status 1 on a FAIL."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw

OUT = '/data/tmp/kyo_fire'
FURY_FIGHTERS = ('kyo', 'haohmaru', 'cheng_fu')

def sheet(cells, path, title, cols=8, W=160, H=112):
    im = Image.new('RGB', (cols * (W + 4) + 4, 20 + ((len(cells) + cols - 1) // cols) * (H + 14)), 'white')
    d = ImageDraw.Draw(im); d.text((4, 4), title, fill='black')
    for i, (lab, p) in enumerate(cells):
        x = 4 + (i % cols) * (W + 4); y = 20 + (i // cols) * (H + 14)
        im.paste(Image.open(p).convert('RGB').resize((W, H)), (x, y + 12)); d.text((x, y), lab, fill='black')
        d.rectangle([x, y + 12, x + W - 1, y + 12 + H - 1], outline='black')
    im.save(path)

_B = []
def start(game, name):
    from harness import Brawler
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    if not _B: _B.append(Brawler(rom=os.path.join(game, 'brawler.neo'), game=game))   # (one core a process)
    b = _B[0]
    b.pick(roster.index(name), unlock=True); b.run(10)
    st = b.states
    for i in range(1, 8): b.fset(i, 'state', st.index('OFF'))
    b.place(0, x=b.r(b.syms['cam_x'], 2) + 100, z=30); b.fset(0, 'facing', 1)
    w = 0
    while st[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
    return b, roster

# ---- note 20261011-205309-5d29: the dragon's fires stay where they were born -------------------------------------------
MOVES = {'623C': ('C', ['4:c']), '623A': ('down,down + A', ['3:D', '3:', '3:D', '2:Da'])}

def fire(game, out):
    os.makedirs(out, exist_ok=True)
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))['kyo']
    b, roster = start(game, 'kyo'); s0 = b.save(); st = b.states; res = {}; ok = True
    for mv, (label, keys) in MOVES.items():
        b.load(s0); b.fset(0, 'drive', 480)
        script = [k for part in keys for k in [part.split(':')[1]] * int(part.split(':')[0])]
        rows, cells, born = [], [], {}
        for f in range(110):
            k = script[f] if f < len(script) else ''
            if f % 2 == 0 and 8 <= f < 8 + 2 * 40:
                p = os.path.join(out, f'{mv}_{f:03d}.png'); b.pad = [set(k), set()]; b.screenshot(p); cells.append((f'{mv} f{f}', p))
            else: b.run(1, p1=k)
            objs = []
            for j in range(8):
                if st[b.pget(j, 'state')] != 'PROJ': continue
                fo = b.pget(j, 'frame_ovr')
                objs.append({'slot': j, 'x': round(b.pget(j, 'x'), 2), 'h': round(b.pget(j, 'y'), 2), 'frame': frames[fo] if fo < len(frames) else fo})
            rows.append({'f': f, 'state': st[b.fget(0, 'state')], 'x': round(b.fget(0, 'x'), 2), 'h': round(b.fget(0, 'y'), 2), 'objs': objs})
        lives = []                                           # each fire's life: consecutive frames of one slot
        for r in rows:
            for o in r['objs']:
                lv = next((l for l in lives if l['slot'] == o['slot'] and l['last'] == r['f'] - 1), None)
                if lv is None:
                    lv = {'slot': o['slot'], 'first': r['f'], 'last': r['f'], 'kyo_at_birth': (r['x'], r['h']), 'pos': []}; lives.append(lv)
                lv['last'] = r['f']; lv['pos'].append((o['x'], o['h']))
        for lv in lives:
            xs = {p[0] for p in lv['pos']}; hs = {p[1] for p in lv['pos']}
            kyo_moved = [r for r in rows if lv['first'] <= r['f'] <= lv['last'] and (r['x'], r['h']) != lv['kyo_at_birth']]
            lv['frames'] = len(lv['pos']); lv['born_at'] = lv['pos'][0]
            lv['stays'] = len(xs) == 1 and len(hs) == 1
            lv['kyo_moved_frames'] = len(kyo_moved)
            lv['offset_at_birth'] = (round(lv['pos'][0][0] - lv['kyo_at_birth'][0], 2), round(lv['pos'][0][1] - lv['kyo_at_birth'][1], 2))
            del lv['pos']
        good = len(lives) == 2 and all(l['stays'] for l in lives) and any(l['kyo_moved_frames'] for l in lives) and \
            all(abs(l['offset_at_birth'][0]) <= 2 and abs(l['offset_at_birth'][1]) <= 2 for l in lives)
        ok &= good
        res[mv] = {'label': label, 'ok': good, 'fires': lives, 'rows': rows}
        sheet(cells, os.path.join(out, f'{mv}.png'), f'Kyo {mv} ({label}), every 2 frames: the fires stay where they were born')
        print(mv, 'OK' if good else 'FAIL', json.dumps(lives), flush=True)
    kt = os.path.join(out, 'kof98_trace.json')
    if os.path.exists(kt):                                   # KOF98 (romspecials98.trace, our emulator): per frame
        k = json.load(open(kt)); res['kof98'] = {}           # (f, Kyo x, Kyo h, [(state, x, h)])
        for mv, tr in k.items():
            pos = {}
            for f, x, h, objs in tr:
                for s_, ox, oh in objs: pos.setdefault(s_, set()).add((ox, oh))
            res['kof98'][mv] = {str(s_): sorted(v) for s_, v in pos.items()}
            print('kof98', mv, res['kof98'][mv])
    json.dump(res, open(os.path.join(out, 'fire.json'), 'w'), indent=1)
    print('fire:', 'OK' if ok else 'FAIL')
    return ok

# ---- note 20261011-210011-5d29: down + D falls back on the fury -----------------------------------------------------
def fury(game):
    g = json.load(open(os.path.join(game, 'game.json'))); M = g['meter']; ch = M['chunk']; ok = True
    cases = [('1 chunk, low life, gauge full', 1 * ch, True, 'fury'),
             ('2 chunks, normal life, gauge full', 2 * ch, False, 'fury'),
             ('2 chunks, low life, gauge full (MAX ready)', 2 * ch, True, 'max'),
             ('0 chunks, low life, gauge full', 0, True, None)]
    for name in FURY_FIGHTERS:
        b, roster = start(game, name); s0 = b.save(); st = b.states
        for label, drive, low, want in cases:
            b.load(s0)
            full = b.fget(0, 'hp_max') or 60
            b.fset(0, 'hp', max(1, full * M['low'] // 100) if low else full); b.fset(0, 'drive', drive); b.fset(0, 'fgauge', M['fury_max'])
            b.run(2)
            got, paid = None, 0
            for f in range(30):
                d0 = b.fget(0, 'drive')
                b.run(1, p1='Dd' if f < 3 else '')
                if st[b.fget(0, 'state')] == 'SPECIAL':
                    got = 'max' if b.fget(0, 'fmax') else 'fury'; paid = d0 - b.fget(0, 'drive'); break
            exp_paid = {'fury': M['fury_drive'] * ch, 'max': M['max_drive'] * ch, None: 0}[want]
            good = got == want and abs(paid - exp_paid) <= 1   # (the frame's refill point)
            ok &= good
            print(f'{name:9s} {label:45s} -> {got or "nothing":7s} drive paid {paid:4d} (want {want or "nothing"}, {exp_paid})',
                  'OK' if good else 'FAIL', flush=True)
    print('fury:', 'OK' if ok else 'FAIL')
    return ok

if __name__ == '__main__':
    cmd, game = sys.argv[1], os.path.abspath(sys.argv[2])
    out = sys.argv[3] if len(sys.argv) > 3 else OUT
    ok = {'fire': lambda: fire(game, out), 'fury': lambda: fury(game)}[cmd]()
    sys.exit(0 if ok else 1)
