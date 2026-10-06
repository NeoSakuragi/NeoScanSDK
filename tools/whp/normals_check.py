#!/usr/bin/env python3
"""Every normal of the six-button decode (moves_whp.normals: button x stance) played by WHP in our emulator: the
animation the game picks = the one the ROM's tables give, and its frames = the ROM's steps (a step shows ticks + 1
frames; an air normal until its held step, the landing ends it).

    python3 normals_check.py OUT.json [--capture CAP.json]

Recipes from the vs. state (P1 Hanzou at 200 facing right, P2 pinned): far = P2 at 330, close = P2 at 250 (50 px:
inside every close reach, 58-88 px), forward / back = the stick held (P2 far: no throw, the strong chords' throw
needs the close range), crouch = down held, jump = up (diagonal: up-forward) then the button 12 frames later, run =
forward twice then the button (low: with down)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_whp as cap, moves_whp as MW, handlers_whp as H, whp

BTN = {'A': 'a', 'B': 'b', 'AB': 'ab', 'C': 'c', 'D': 'd', 'CD': 'cd'}
FAR, CLOSE = 330, 250
def recipe(stance, b):
    k = BTN[b]
    return {'far': (FAR, f'2:-,3:{k},70:-'), 'close': (CLOSE, f'2:-,3:{k},70:-'),
            'far_fwd': (FAR, f'2:-,4:R,3:R{k},8:R,70:-'), 'far_back': (FAR, f'2:-,4:L,3:L{k},8:L,70:-'),
            'close_fwd': (CLOSE, f'2:-,4:R,3:R{k},8:R,70:-'), 'close_back': (CLOSE, f'2:-,4:L,3:L{k},8:L,70:-'),
            'crouch': (FAR, f'2:-,8:D,3:D{k},40:D,30:-'), 'jump_up': (FAR, f'2:-,3:U,12:-,3:{k},70:-'),
            'jump_diag': (None, f'2:-,40:-,3:UR,10:-,3:{k},70:-'),
            'run': (None, f'2:-,40:-,3:R,3:-,12:R,3:R{k},8:R,60:-'), 'run_low': (None, f'2:-,40:-,3:R,3:-,12:R,3:DR{k},8:DR,60:-')}[stance]

def capture_one(n):
    p2x, seq = recipe(n['stance'], n['button'])
    if p2x is None: seq2 = '2:-,40:R'                    # P2 walks away first (capture_whp.AWAY): room ahead
    else: seq2 = ''
    nfr = cap.nframes(seq)
    pk = ';'.join(f'{f}:100102={p2x * 128 >> 8 & 255:02X},100103={p2x * 128 & 255:02X}' for f in range(nfr)) if p2x else None
    rows = cap.run(seq, seq2, pokes=pk, span=0x200)
    out = []
    for r in rows:
        o = cap.obj(r, 0)
        out.append([o['anim'] - o['base'], o['step'], o['defw'], r['anim'][0x10C], (o['y'] - r['floor']) / 128])   # + P2's life, P1's height
    return f"{n['button']}:{n['stance']}", out

def expected(rel):
    """the ROM's frames of an animation: [(step, def)] each shown ticks + 1 frames, to its end or its held step"""
    out = []
    for i, s in enumerate(s for s in whp.steps_of(0, rel) if not s['ctrl']):
        out += [(i, s['defw'])] * (min(s['ticks'], 30) + 1)
        if s['ticks'] >= 30: break                       # a held step (air normals: until the landing)
    return out

def check(capd):
    """per normal: the animation WHP played = the decode's (a close strong chord with a direction: the throw, $315B0
    before the normal), its frames = the ROM's up to the first contact (P2's life drops: the hit-stop follows) or the
    landing (an air normal)"""
    res = {}
    thr = {(t['chord'], t['dir']): t['rel'] for t in MW.throws(1, 0)}
    for n in MW.normals(1, 0):
        k = f"{n['button']}:{n['stance']}"; fr = capd[k]
        want = n['rel']
        if n['stance'] in ('close_fwd', 'close_back') and (n['button'], n['stance'][6:].replace('fwd', 'forward')) in thr:
            want = thr[(n['button'], n['stance'][6:].replace('fwd', 'forward'))]
        played = next((f[0] for f in fr if 0x40 <= f[0] < 0x90 or 0xD0 <= f[0] < 0xE0), None)
        same_anim = played is not None and whp.anim_addr(0, played) == whp.anim_addr(0, want)
        s0 = next((i for i, f in enumerate(fr) if f[0] == played), None)
        exp = expected(played) if played is not None else []
        cut = len(exp)
        if s0 is not None:
            for i in range(1, len(exp)):
                if s0 + i >= len(fr): cut = i; break
                if fr[s0 + i][3] < fr[s0 + i - 1][3]: cut = min(cut, i + 1); break            # the contact: compared up to it
                if n['stance'].startswith('jump') and fr[s0 + i][4] <= 0 < fr[s0 + i - 1][4]: cut = min(cut, i); break   # landed
        exp = exp[:cut]
        got = [(f[1], f[2]) for f in fr[s0:s0 + len(exp)]] if s0 is not None else []
        bad = [i for i, (a, b_) in enumerate(zip(exp, got)) if a != b_]
        res[k] = {'button': n['button'], 'strength': n['strength'], 'stance': n['stance'], 'decoded': f"${want:X}",
                  'game': f'${played:X}' if played is not None else None, 'same_animation': same_anim,
                  'frames_compared': len(exp), 'frames_identical': len(got) - len(bad), 'cut': 'contact / landing' if cut < len(expected(played or 0x40)) else None,
                  'first_bad': [[i, exp[i], got[i]] for i in bad[:2]], 'brawler': MW.brawler_name(n), 'same_as': n['same_as']}
    return res

if __name__ == '__main__':
    capf = sys.argv[sys.argv.index('--capture') + 1] if '--capture' in sys.argv else '/data/tmp/whp6/normals_cap.json'
    if '--capture' in sys.argv or not os.path.exists(capf):
        with ThreadPoolExecutor(8) as ex: capd = dict(ex.map(capture_one, MW.normals(1, 0)))
        json.dump(capd, open(capf, 'w'))
    res = check(json.load(open(capf)))
    json.dump(res, open(sys.argv[1], 'w'), indent=1)
    for k, v in res.items():
        print(f"{k:14s} decoded {v['decoded']} game {v['game']} same {v['same_animation']} frames {v['frames_identical']}/{v['frames_compared']} {v['cut'] or ''} {v['first_bad'] or ''}")
