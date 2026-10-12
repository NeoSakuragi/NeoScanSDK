#!/usr/bin/env python3
"""model_lb2 vs The Last Blade 2 in our emulator: each case = an input from vs.state that starts a move; the game's P1
per frame (animation, frame id, x, height) from the frame its move starts, against the model's play of that move.
    python3 check_model.py [case ...]        -> per case: frames compared, frames equal (anim, frame, x, h within 0.01)"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_lb2 as M, play_lb2 as PL

# name -> (P1 input from vs.state (P1 Moriya faces right, P2 160 px ahead), pokes before it, style state)
QCF = '3:D,3:DR,3:R'; DP = '3:R,3:D,3:DR'; QCB = '3:D,3:DL,3:L'; RQ = '3:L,3:DL,3:D'
CASES = {
    'stand_A': ('2:-,3:a,120:-', None), 'stand_B': ('2:-,3:b,120:-', None), 'stand_C': ('2:-,3:c,120:-', None),
    'crouch_A': ('2:-,3:D,3:Da,120:D', None), 'jump_up': ('2:-,3:U,120:-', None), 'jump_fwd': ('2:-,3:UR,120:-', None),
    '236A': ('2:-,%s,3:a,150:-' % QCF, None), '236B': ('2:-,%s,3:b,150:-' % QCF, None),
    '623A': ('2:-,%s,3:a,150:-' % DP, None), '623B': ('2:-,%s,3:b,150:-' % DP, None),
    '214A': ('2:-,%s,3:a,150:-' % QCB, None), '214B': ('2:-,%s,3:b,150:-' % QCB, None), '214C': ('2:-,%s,3:c,150:-' % QCB, None),
    '64123AB': ('2:-,3:R,3:L,3:DL,3:D,3:DR,3:ab,200:-', [(PL.P1 + 0x17D, 1, 64)]),
    '641236B': ('2:-,3:R,3:L,3:DL,3:D,3:DR,3:R,3:b,200:-', [(PL.P1 + 0x17D, 1, 64), (PL.P1 + 0x17E, 2, 60)]),
    '412A': ('2:-,%s,3:a,150:-' % RQ, None), '412B': ('2:-,%s,3:b,150:-' % RQ, None), '412C': ('2:-,%s,3:c,150:-' % RQ, None),
}

FAR = 300                                           # P2's distance during a case (0: left where it is)
BASIC = set(range(9))                                # idle, walks, crouch: the input's way to the move

def game_rows(seq, pokes=None, state='vs'):
    def each(g, f):
        if f == 0 and pokes:
            for a, n, v in pokes: g.w(a, n, v)
        if FAR: g.w(PL.P2 + 0x80, 2, (g.r(PL.P1 + 0x80) + FAR) & 0xFFFF)   # P2 kept FAR px ahead: a whiff
    log, g = PL.play(seq, state=state, each=each)
    return log

def compare(name, verbose=False):
    seq, pokes = CASES[name][:2]
    log = game_rows(seq, pokes)
    log = [log[0]] + [log[k] for k in range(1, len(log)) if log[k][0]['gt'] != log[k - 1][0]['gt']]   # lag frames out
    p1 = [p for p, q in log]
    # the move: the first frame P1's move changes from the idle's
    start = next(i for i in range(1, len(p1)) if p1[i]['anim'] not in BASIC)
    mv = p1[start]['move']
    rows, ev = M.play_move(1, mv, n=len(p1) - start, opp_dx=0)       # (the near versions: the descriptor's distance ops read the game's own distance, not the poked x)
    p2hit = sorted({q['anim'] for p, q in log[start:]} - {0})
    x0, h0 = p1[start - 1]['x'], 0
    face = 1                                            # P1 faces right in vs.state: forward = +x
    eq = 0; first_bad = None
    n = min(len(rows), len(p1) - start)
    warps = [e[0] for e in ev if e[1] == 'warp']
    for k in range(n):
        g = p1[start + k]; m = rows[k]
        if k in warps: x0 = g['x'] - int(m['x'])           # a teleport: the place is the opponent's (rebased)
        gx = (g['x'] - x0) * face
        ok = g['anim'] == m['anim'] and g['frame'] == m['frame'] and abs(gx - int(m['x'])) <= 1 and abs(g['h'] - int(m['h'])) <= 1
        eq += ok
        if not ok and first_bad is None: first_bad = k
        if verbose:
            print(k, 'game', hex(g['anim']), g['frame'], gx, g['h'], '| model', hex(m['anim']), m['frame'], round(m['x'], 1), round(m['h'], 1), '' if ok else '  <<')
    return dict(name=name, move=mv, frames=n, equal=eq, first_bad=first_bad, p2_anims=p2hit)

if __name__ == '__main__':
    names = [a for a in sys.argv[1:] if not a.startswith('-')] or list(CASES)
    for nm in names:
        r = compare(nm, verbose='-v' in sys.argv)
        print(r)
