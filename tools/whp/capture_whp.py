#!/usr/bin/env python3
"""Hanzou's moves played by World Heroes Perfect in our emulator (emu/neogeo_sdl --capture), one capture per recipe
from the 'vs' state (cap/vs.state: P1 Hanzou at x 200 facing right, P2 Fuuma; P2's x pinned per recipe unless None).
Per frame: P1 [anim (relative to its base), step, x, y, def, flip, active, box id, life],
P2 the same, the pool objects other than the fighters [k, anim, def, x, y, flip, box id, live]
(x / y in px: world x = object word / 128 + the camera x $108232, y up from the floor line 144 = 0; active = step flag byte +$60D6 bit 3;
box id = +$60F8 (fighters) / +$40 (pool objects, live = +$44); life = record +$0C).

    python3 capture_whp.py [OUT.json] [names...]      (default /data/neogeo_dict/whp/hanzo_capture.json)

Reactions are Hanzou's own (P1) under P2 Fuuma's attacks (the two share the animation numbering, base + n)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_whp as cap

OUT = '/data/neogeo_dict/whp/hanzo_capture.json'
FLOOR = 0x4800                                   # y word of a fighter standing on the floor [meas]
FAR, NEAR = 330, 250
def m(dirs, b):                                   # a motion: 3 frames per direction, the button with the last, held 3
    return '2:-,' + ','.join(f'3:{d}' for d in dirs[:-1]) + f',3:{dirs[-1]}{b},3:{b},'
# AWAY: P2 walks back for 40 frames (P1 waits), then stands: the two are ~230 px apart, the widest the camera allows
# (pinning P2 farther pushes P1 back every frame: a moving move would not move), and nothing pins anyone
AWAY = '2:-,40:R'
def away(seq): return '2:-,40:-,' + seq[4:]
RECIPES = {
    'idle': (FAR, '2:-,120:-', ''),
    'walk_fwd': (None, away('2:-,50:R,10:-'), AWAY), 'walk_back': (FAR, '2:-,60:L,10:-', ''),
    'run': (None, away('2:-,3:R,3:-,30:R,30:-'), AWAY), 'backdash': (FAR, '2:-,3:L,3:-,3:L,50:-', ''),
    'crouch': (FAR, '2:-,40:D,30:-', ''),
    'jump_up': (FAR, '2:-,3:U,70:-', ''), 'jump_fwd': (None, away('2:-,3:UR,70:-'), AWAY), 'jump_back': (FAR, '2:-,3:UL,70:-', ''),
    **{f'far_{b}': (FAR, f'2:-,3:{b},70:-', '') for b in 'abcd'},
    **{f'close_{b}': (NEAR, f'2:-,3:{b},70:-', '') for b in 'abcd'},
    **{f'crouch_{b}': (FAR, f'2:-,8:D,3:D{b},40:D,30:-', '') for b in 'abcd'},
    **{f'jump_{b}': (FAR, f'2:-,3:U,12:-,3:{b},70:-', '') for b in 'abcd'},
    **{f'jump_fwd_{b}': (None, away(f'2:-,3:UR,10:-,3:{b},70:-'), AWAY) for b in 'abcd'},
    'ab': (FAR, '2:-,3:ab,90:-', ''), 'cd': (FAR, '2:-,3:cd,90:-', ''),
    # Hanzou hit by P2 (Fuuma, facing left: forward = L)
    'react_a': (NEAR, '2:-,80:-', '2:-,3:a,75:-'), 'react_b': (NEAR, '2:-,80:-', '2:-,3:b,75:-'),
    'react_c': (NEAR, '2:-,90:-', '2:-,3:c,85:-'), 'react_d': (NEAR, '2:-,90:-', '2:-,3:d,85:-'),
    'react_knockdown': (240, '2:-,220:-', '2:-,3:L,3:D,3:DLa,3:a,205:-'),
    'react_air': (NEAR, '2:-,3:U,150:-', '2:-,4:-,3:L,3:D,3:DLa,3:a,132:-'),
    'react_sweep': (NEAR, '2:-,150:-', '2:-,8:D,3:DLd,60:D,79:-'),
    # specials (P2 at 260: in reach of the dashes; 400: the projectile flies)
    **{f'236{b}': (400 if b in 'ab' else 260, m('D DR R'.split(), b) + '100:-', '') for b in 'abcd'},
    **{f'623{b}': (240, m('R D DR'.split(), b) + '100:-', '') for b in 'abcd'},
    **{f'214{b}': (260, m('D DL L'.split(), b) + '110:-', '') for b in 'abcd'},
}
# whiffs: P2 walks away first (AWAY); the projectile still reaches P2 (its impact animation)
WHIFF = {f'{k}w': (None, away(RECIPES[k][1]), AWAY) for k in ('236a', '236b', '236c', '236d', '623a', '623b', '214c', '214d')}
RECIPES.update(WHIFF)

def fighter(r, k):
    o = cap.obj(r, k); a = r['anim'][k * 0x100:(k + 1) * 0x100]
    return [o['anim'] - o['base'], o['step'], o['x'] / 128 + r['cam'], (o['y'] - FLOOR) / 128, o['defw'], o['flags'] >> 7 & 1,
            a[0xD6] >> 3 & 1, cap.u16(a, 0xF8), a[0x0C]]

def capture(name):
    p2x, seq, seq2 = RECIPES[name]
    n = max(cap.nframes(seq), cap.nframes(seq2) if seq2 else 0)
    pk = ';'.join(f'{f}:100102={p2x * 128 >> 8 & 255:02X},100103={p2x * 128 & 255:02X}' for f in range(n)) if p2x else None
    rows = cap.run(seq, seq2, pokes=pk, span=0x3000)
    base = {k for k in range(2, 48) if cap.u32(rows[0]['obj'], k * 0x100 + 8)}   # stage objects alive at the start
    out = []
    for r in rows:
        objs = []
        for k in range(2, 48):
            o = r['obj'][k * 0x100:(k + 1) * 0x100]
            ob = cap.obj(r, k)
            if not o[0x44] and (k in base or not ob['defw'] or ob['defw'] == 0x000C): continue   # stage / free / blank
            objs.append([k, ob['anim'], ob['defw'], ob['x'] / 128 + r['cam'], (ob['y'] - FLOOR) / 128, ob['flags'] >> 7 & 1,
                         cap.u16(o, 0x40), o[0x44]])
        out.append([fighter(r, 0), fighter(r, 1), objs])
    return out

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else OUT
    names = sys.argv[2:] or list(RECIPES)
    data = json.load(open(path)) if os.path.exists(path) and sys.argv[2:] else {}
    for k in names:
        fr = capture(k)
        data[k] = {'recipe': RECIPES[k], 'frames': fr}
        anims = []
        for f in fr:
            if f[0][0] not in anims: anims.append(f[0][0])
        print(k, [hex(a) for a in anims], 'P2', sorted({hex(f[1][0]) for f in fr}), 'objs', len({o[0] for f in fr for o in f[2]}))
    json.dump(data, open(path, 'w'))
