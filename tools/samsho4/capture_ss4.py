#!/usr/bin/env python3
"""Haohmaru's moves and specials played by Samurai Shodown IV in our emulator (emu/neogeo_sdl --capture), one capture
per recipe from the 'vs' states (Slash: cap/vs.state, Bust: cap/vs_bust.state; P1 Haohmaru at x 240 facing right,
P2 Haohmaru pinned at x P2X). Per frame: P1 [anim, step, x, y], P2 [anim, step, x, y], the P1-side pool objects
(named objects with an animation, $103C00-$107FFF: SENPUDAN = Senpuu Retsu Zan's tornado) [name, anim, step, x, y].

    python3 capture_ss4.py [OUT.json]        (default /data/neogeo_dict/samsho4/haohmaru_capture.json)

Recipes: SEQ strings (U D L R a b c d, 3-frame presses), the state, P2's x. Measured facts these captures gave
(2026-10-05): a step shows for its ROM ticks frames (KOF96-99: ticks + 1); Slash and Bust share every normal
(the same animation numbers); the mode is byte $108324 (P1) / $108325 (P2), 0 Slash 1 Bust; the colour word $10832C
(P1) = the $1298 palette index ($80 Slash A, $A0 Slash B, $C0 Bust A, $E0 Bust B)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap, ss4

BUST = '/data/neogeo_dict/samsho4/cap/vs_bust.state'
OUT = '/data/neogeo_dict/samsho4/haohmaru_capture.json'
FAR, NEAR = 600, 280
# name: (state, P2 x, P1 seq, P2 seq, pool objects)
RECIPES = {
    'idle': ('slash', FAR, '2:-,90:-', ''),
    'walk_fwd': ('slash', FAR, '2:-,70:R,10:-', ''),
    'walk_back': ('slash', FAR, '2:-,70:L,10:-', ''),
    'run': ('slash', FAR, '2:-,3:R,3:-,50:R,40:-', ''),
    'jump_up': ('slash', FAR, '2:-,3:U,70:-', ''),
    'jump_fwd': ('slash', FAR, '2:-,3:UR,70:-', ''),
    'jump_back': ('slash', FAR, '2:-,3:UL,70:-', ''),
    'crouch': ('slash', FAR, '2:-,30:D,20:-', ''),
    'far_a': ('slash', FAR, '2:-,3:a,60:-', ''), 'far_b': ('slash', FAR, '2:-,3:b,60:-', ''),
    'far_c': ('slash', FAR, '2:-,3:c,100:-', ''), 'far_d': ('slash', FAR, '2:-,3:d,70:-', ''),
    'close_a': ('slash', NEAR, '2:-,3:a,60:-', ''), 'close_b': ('slash', NEAR, '2:-,3:b,60:-', ''),
    'close_c': ('slash', NEAR, '2:-,3:c,100:-', ''), 'close_d': ('slash', NEAR, '2:-,3:d,70:-', ''),
    'crouch_a': ('slash', FAR, '2:-,3:Da,60:-', ''), 'crouch_b': ('slash', FAR, '2:-,3:Db,60:-', ''),
    'crouch_c': ('slash', FAR, '2:-,3:Dc,100:-', ''), 'crouch_d': ('slash', FAR, '2:-,3:Dd,70:-', ''),
    'sweep': ('slash', NEAR + 20, '2:-,3:DRd,150:-', ''),
    'cd': ('slash', FAR, '2:-,3:cd,90:-', ''),
    'jump_a': ('slash', FAR, '2:-,3:U,12:-,3:a,70:-', ''), 'jump_b': ('slash', FAR, '2:-,3:U,12:-,3:b,70:-', ''),
    'jump_c': ('slash', FAR, '2:-,3:U,12:-,3:c,70:-', ''), 'jump_d': ('slash', FAR, '2:-,3:U,12:-,3:d,70:-', ''),
    'jump_fwd_c': ('slash', FAR, '2:-,3:UR,8:-,3:c,70:-', ''), 'jump_fwd_d': ('slash', FAR, '2:-,3:UR,8:-,3:d,70:-', ''),
    # the opponent's reactions (P2 is Haohmaru too): hit by a close A / far C / crouch C in the air / the sweep
    'react_light': ('slash', NEAR + 10, '2:-,3:a,80:-', ''),
    'react_heavy': ('slash', NEAR + 10, '2:-,3:c,120:-', ''),
    'react_air': ('slash', NEAR + 10, '2:-,17:-,3:Dc,120:-', '2:-,3:U,140:-'),
    'react_trip': ('slash', NEAR + 20, '2:-,3:DRd,200:-', ''),
    # specials: Slash (A / B / C versions of 236, 623, 421), both modes' A+B+C, B+C+D, B+C; Bust's own
    **{f'{mo}{b}': ('slash', 400, f'2:-,{",".join(f"3:{d}" for d in dirs[:-1])},3:{dirs[-1]}{b},3:{b},150:-', '')
       for mo, dirs in (('236', ('D', 'DR', 'R')), ('623', ('R', 'D', 'DR')), ('421', ('L', 'D', 'DL'))) for b in 'abc'},
    'ABC': ('slash', 400, '2:-,3:abc,150:-', ''), 'BCD': ('slash', 400, '2:-,3:bcd,150:-', ''),
    'BC': ('slash', 400, '2:-,3:bc,100:-', ''), 'AB': ('slash', 400, '2:-,3:ab,100:-', ''),
    'BUST 236d': ('bust', 400, '2:-,3:D,3:DR,3:Rd,3:d,150:-', ''),
    'BUST 623d': ('bust', 400, '2:-,3:R,3:D,3:DRd,3:d,150:-', ''),
    'BUST 421c': ('bust', 400, '2:-,3:L,3:D,3:DLc,3:c,150:-', ''),
}
SPECIAL = lambda k: k[0].isdigit() or k.isupper() or k.startswith('BUST')

def step_of(o):
    s = cap.summary(o); return s['anim'], ss4.step_index(0, s['anim'], s['step']), s['x'], s['y']

def capture(name):
    mode, p2x, seq, seq2 = RECIPES[name]
    n = cap.nframes(seq)
    pk = ';'.join(f'{f}:103A2E={p2x >> 8:02X},103A2F={p2x & 255:02X}' for f in range(n))
    pool = SPECIAL(name)
    rows = cap.run(seq, seq2, pool=pool, pokes=pk, load=cap.VS if mode == 'slash' else BUST)
    out = []
    for r in rows:
        objs = []
        if pool:
            p = r['pool']
            for k in range(0x3C, 0x80):
                o = p[k * 0x100:(k + 1) * 0x100]; nm = o[0x10:0x18]
                if not cap.u32(o, 0x4E) or not all(32 <= c < 127 for c in nm) or o[0x1E] != 0: continue
                if nm.decode().strip() in ('', 'LifeDisp', 'PAL ACT', 'BACKSCRN', 'Back Dir', 'SeDmgStp'): continue
                a, st, x, y = step_of(o)
                if st is None: continue
                objs.append([nm.decode().strip(), a, st, x, y, o[0x0F] & 2])
        out.append([list(step_of(r['p1'])), list(step_of(r['p2'])), objs])
    return out

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else OUT
    data = {}
    for k in RECIPES:
        data[k] = {'recipe': RECIPES[k], 'frames': capture(k)}
        anims = []
        for f in data[k]['frames']:
            if f[0][0] not in anims: anims.append(f[0][0])
        print(k, anims, {o[0] for f in data[k]['frames'] for o in f[2]} or '')
    json.dump(data, open(path, 'w'))
