#!/usr/bin/env python3
"""KOF96 throw tables (decoded 2026-10-02). Victim placement routine $1AF72 (thrower x/y copied to the victim, then the
entry for the thrower's step count +$80 - 1 from the victim's list +$C2; table base passed to $1A980 by the throw's code;
list = base + victim id * size). Entry: [dx][dy][word], dx/dy = 6-bit magnitude * 4, bit 6 = negative, bit 7 of dx =
which fighter is drawn in front ($129D6 / $12A10); word bits 0-8 = victim state (shared state map), bits 9-15 = flags
(bit 0 hit effect, bit 1 spawn, bit 2 screen; $40 = release). Lists live in bank 1.
Second mode, $1B008: the THROWER holds the list (its own +$C2, indexed by its own +$80) and is placed relative to the
victim while setting the victim's state (Mai's vault onto the shoulders, Kim's jump). The entry means the same thing
(victim offset from thrower), so one decoder serves both; 'side' says which object carries the list.
Stage edge, $1B134: if the victim would leave the stage, the thrower is moved so the list's widest offset fits x 32..736."""
import rom96

LIST_BANK = {'kof96': 1, 'kof98': 0, 'kof99': 0}   # KOF98 ($25372/$253E6) and KOF99 ($20302, SMA bank $A21A = 0) read bank 0

def entries(m, base, size, victim):
    """KOF98 adds bit 7 of dy = the victim's facing bit (+$31 bit 0, 'turn')"""
    a = base + victim * size; out = []; B = LIST_BANK[m.game]
    dec = lambda b: -((b & 0x3F) * 4) if b & 0x40 else (b & 0x3F) * 4
    for k in range(size // 4):
        dx, dy, w = m.u8(a + 4 * k, B), m.u8(a + 4 * k + 1, B), m.u16(a + 4 * k + 2, B)
        e = {'state': w & 0x1FF, 'dx': -dec(dx), 'dy': dec(dy), 'flags': w >> 9, 'front': dx >> 7}
        if m.game != 'kof96': e['turn'] = dy >> 7
        out.append(e)
    return out

def validate(m, path, lists, victim=8, start=None, end=None):
    """replay one throw against its capture. lists = [(side, base, size)] recorded for that throw; a frame where the
    victim is in a throw pose counts when the list its holder carries that frame (victim +$C2, or thrower +$C2 for the
    thrower side) gives the victim's state and offset for the thrower's step +$80 - 1"""
    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kof95', 'capture')); import analyze as A
    r1, r2 = A.load(path, 1), A.load(path, 2)
    L = {(side, base + victim * size): entries(m, base, size, victim) for side, base, size in lists}
    tot = ok = 0; bad = []
    for i in range(start, min(end, len(r1), len(r2))):
        w1, w2 = r1[i][3], r2[i][3]
        cand = [(k, e) for k, e in L.items()
                if ((w2 if k[0] == 'victim' else w1)[0xC2 // 2] << 16 | (w2 if k[0] == 'victim' else w1)[0xC4 // 2]) == k[1]
                and A.state_of(w2) in {x['state'] for x in e}]
        if not cand: continue
        f = 1 if A.facing_of(w1) else -1
        dx, dy = round((A.x_of(w2) - A.x_of(w1)) * f), round(A.y_of(w2) - A.y_of(w1))
        good = False
        for k, e in cand:
            x = e[min(max(0, w1[0x80 // 2] - 1), len(e) - 1)]
            good |= x['state'] == A.state_of(w2) and abs(dx - x['dx']) <= 1 and abs(dy - x['dy']) <= 1
        tot += 1; ok += good
        if not good and len(bad) < 4: bad.append((i - start, A.state_of(w2), dx, dy, [k[0] for k, _ in cand]))
    return tot, ok, bad
