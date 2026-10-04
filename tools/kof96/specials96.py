#!/usr/bin/env python3
"""KOF96 specials from the captures (capture/specials96.py, our emulator): one entry per distinct move.

A try counts when P1 enters a special state (117..255: past the normals, before the reactions) and that first special
state is new for the character; tries that fall back to a simpler command's move (e.g. 23623 giving 623) or to a
normal are dropped. Script: one row per video frame from the first special state until P1 is back in idle/crouch and
its projectiles are gone (objects born during the move; one frozen on a step past that step's ticks has ended, the
pool keeps finished projectiles allocated; max 240 frames, never past the next try): [P1 frame index, x from start (P1 faces right), height, objects], objects = P1-owned pool objects on
the character's own animation table (projectiles, flames; KOF96 keeps them in the fighter's table) as
[frame index, x from P1's start, height, same facing]. Objects on the shared effect table (id 29: super flash, sparks)
are not drawn. 'steps' per row: [P1 state, P1 animation raw index (+$74 / 6), P2 state, P2 life (+$138), P1's live
attack box (+$90: type x y w h), P1's hit-stop counter (+$124 high byte, counts down to 0 while frozen, $FF = none;
measured in KOF96/98/99 on hits: the counter starts on the row P2's life drops), P2's height, P2's x from P1's start (forward +)]. A super is recognised by its flash (KOF96: table 29, state 58) or, in KOF98, by the power stock it spends
(P1 +$15E; tries start from a state with 3 stocks)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
import analyze as A, rom96, commands96
sys.path.insert(0, os.path.join(HERE, 'capture')); import emu

HELPERS_MAX = 0x101600
FLASH = {'kof96': ('29', '58'), 'kof98': ('38', '34')}          # the shared super flash (table, state)
END = {0, 23}

NUMPAD = {'': '5', 'R': '6', 'L': '4', 'U': '8', 'D': '2', 'UR': '9', 'UL': '7', 'DR': '3', 'DL': '1'}

def notation(events, air=False):
    """numpad notation (facing right) of the input actually performed (capture/specials96.motion): '236A', charge
    as '[4]6A', button presses inside the motion where they are, neutral frames dropped"""
    out, prev = [], None
    for k, (t, n, keys) in enumerate(events):
        if air and k == 0 and keys == 'U': continue          # the jump of an air try
        st = ''.join(c for c in keys if c in 'UDLR'); bt = ''.join(c.upper() for c in keys if c in 'abcd')
        st = ''.join(sorted(st, key='UDLR'.index))
        if not st and not bt: prev = None; continue
        d = NUMPAD.get(st, st)
        if n >= 30: out.append(f'[{d}]'); prev = d; continue
        if st and d != prev: out.append(d)
        prev = d if st else prev
        if bt: out.append(bt)
    return ''.join(out)

def frame_index(m, cid, rec):
    return (rec - rom96.frame_record(m, cid, 0)) // 6

def load(m, cid, tags=('', '_max', '_sdm', '_close', '_ex')):
    """all capture files of the fighter (main, MAX-mode supers, close range), first occurrence of each move kept"""
    d = os.path.join(HERE, 'capture', {'kof96': 'specials', 'kof98': 'specials98'}.get(m.game, 'specials_' + m.game))
    out, seen, first_of = [], set(), {}
    for tag in tags:
        path = os.path.join(d, f'{cid}{tag}.txt')
        if not os.path.exists(path): continue
        out += load_file(m, cid, path, json.load(open(os.path.join(d, f'{cid}{tag}.json'))), seen, tag, first_of)
    return out

def load_file(m, cid, path, T, seen, tag, first_of):
    """first_of: first state -> the move kept for it; a close-range try of a move already kept is attached to it as
    'close' (its hit version: P2 in reach, the hit-confirmed continuation states happen)"""
    lines = open(path).read().split('\n')
    r1 = A.load(path, 1); r2 = A.load(path, 2)
    out = []
    for tr in T:
        s = tr['start']; win = tr.get('gap', 220) - 4             # frames of this try (longer for MAX/counter tries)
        if s + win >= len(r1): continue
        lo = 117 if m.game == 'kof96' else 128            # KOF98's normals run past 116 (hop attacks 120-123)
        g0 = next((i for i in range(s, s + 200) if lo <= A.state_of(r1[i][3]) < 256), None)
        if g0 is None: continue
        # a move = the special states it goes through (first 6, until neutral): KOF99's SDMs start in their DM's state
        path_ = []
        for i in range(g0, min(len(r1), g0 + 300, s + win)):
            st_ = A.state_of(r1[i][3])
            if i > g0 + 2 and st_ in END: break
            if lo <= st_ < 256 and (not path_ or path_[-1] != st_): path_.append(st_)
        # main / close passes: one move per first state (a hit and a whiff of one move differ later on); the MAX /
        # counter, SDM and EX passes: kept when their state path is new (KOF99's counter-mode SDMs start in the DM's state)
        first = A.state_of(r1[g0][3]); key = tuple(path_)
        attach = None
        if tag in ('', '_close'):
            if first in seen:
                attach = first_of.get(first) if tag == '_close' else None
                if attach is None or 'close' in attach or (attach['cmd'], attach['button']) != (tr['cmd'], tr['button']): continue
        elif key in seen: continue
        seen.add(first); seen.add(key)
        w0 = r1[g0][3]; x0 = A.x_of(w0); f0 = 1 if A.facing_of(w0) else -1
        rows, states, psteps, super_ = [], [], [], False
        def bases(i):
            o = lines[i - 1].split()[-1]
            return set() if o == '-' else {x.split(':')[0] for x in o.split(';')}
        old_objs = bases(s - 1)                           # alive before the try: not this move's
        since, ended = {}, set()                          # an object frozen on one step past its ticks has ended
        for i in range(g0, min(len(r1), g0 + 300, s + win)):
            w = r1[i][3]; st = A.state_of(w)
            objs = []
            o = lines[i - 1].split()[-1]
            for x in ([] if o == '-' else o.split(';')):
                base, tid, ost, steps, rec, ox, oy, of = x.split(':')
                if (tid, ost) == FLASH.get(m.game): super_ = True
                if base in old_objs or base in ended: continue
                key = (ost, steps, rec, ox, oy)
                if base not in since or since[base][0] != key: since[base] = (key, i)
                elif tid == str(cid):
                    st_ = rom96.parse_anim(m, rom96.anim_addr(m, cid, rom96.state_slot(m, cid, int(ost))))[0] if int(ost) < 512 else []
                    k = int(steps) - 1
                    ticks = st_[k][0] if 0 <= k < len(st_) else 0
                    if i - since[base][1] > max(ticks, 1) + 1: ended.add(base); continue
                base, tid, rec = int(base, 16), int(tid), int(rec, 16)
                if tid != cid or base < HELPERS_MAX: continue
                objs.append([frame_index(m, cid, rec), round((int(ox) - x0) * f0), int(oy), int(int(of) == A.facing_of(w))])
            if i > g0 + 2 and st in END and not objs: break           # P1 back to neutral and its projectiles gone
            if not states or states[-1][1] != st: states.append([i - g0, st])
            rows.append([frame_index(m, cid, A.frame_of(w)), round((A.x_of(w) - x0) * f0), round(A.y_of(w)), objs])
            v = r2[i][3]                                  # P1's animation step (state, raw index = +$74 / 6), P2's
            psteps.append([st, w[0x74 // 2] // 6, A.state_of(v), v[0x138 // 2],   # state + life, P1's live attack box
                           [w[0x90 // 2] >> 8, w[0x90 // 2] & 255, w[0x92 // 2] >> 8, w[0x92 // 2] & 255, w[0x94 // 2] >> 8],
                           w[0x124 // 2] >> 8, round(A.y_of(v)), round((A.x_of(v) - x0) * f0),   # (+$90: type, x, y,
                           [w[0x1B8 // 2] >> 8, w[0x1BA // 2] >> 8]])  # w, h), P1's hit-stop (+$124, $FF none), P2's
                                                       # height, P2's x, KOF98 hit effect: kind (+$1B8: the victim's hit
                                                       # sounds, table $1E208) and burn (+$1BA: 2 orange, 1 purple)
        if m.game != 'kof96':                              # KOF98/99: a super spends a power stock (P1 +$15E)
            so = emu.GAMES[m.game]['stock']                # byte offset of the stock count in the P1 object
            stock = lambda i: (r1[i][3][so // 2] >> 8) if so % 2 == 0 else (r1[i][3][so // 2] & 0xFF)
            super_ = stock(min(len(r1) - 1, s + 200)) < stock(s)
        e = {'state': first, 'cmd': tr['cmd'], 'button': tr['button'], 'range': 'close' if tag == '_close' else 'far',
                    'input': ('EX ' if tag == '_ex' else '') + (('Counter ' if m.game == 'kof99' else 'MAX ') if tr.get('max') else '') + ('SDM ' if tr.get('sdm') else '') + ('air ' if tr.get('air') else '') + notation(
                        [e for e in tr['events'] if not (tr.get('max') and e[2] == 'abc')], tr.get('air')),
                    'condition': 'super' if super_ else 'normal', 'states': states, 'rows': rows, 'steps': psteps}
        if attach is not None: attach['close'] = e
        else: out.append(e); first_of.setdefault(first, e)
    return out

if __name__ == '__main__':
    prom, _ = rom96.load(); m = rom96.Mem(prom)
    for cid in map(int, sys.argv[1:] or ['3']):
        for sp in load(m, cid):
            print(cid, sp['input'], sp['condition'], sp['state'], [s[1] for s in sp['states']][:6], len(sp['rows']),
                  max((len(r[3]) for r in sp['rows']), default=0), 'objs')
