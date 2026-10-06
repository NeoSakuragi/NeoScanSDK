#!/usr/bin/env python3
"""Brute force of a fighter's move continuations in Kizuna Encounter (our emulator, the 'vs' state): each special played
whiff (P2 far), on hit (P2 close) and on block (P2 close holding back), and during it every input (each button A-D
alone, with each stick direction, and each of the character's command motions + each button) pressed at several
moments; per run, the animations P1 plays from the move until it is back to neutral. The distinct outcomes and the
inputs / moments / situations that give them -> JSON; substates_kz.py's decoded model is checked against it.

    python3 brute_kz.py [--char NAME] [OUT.json] [moves...]   (default Kim: /data/neogeo_dict/kizuna/kim_brute.json)
    python3 brute_kz.py [--char NAME] --level2 OUT.json

Any fighter (setup(name), fighters_kz.CAST): its specials = one per special command of its list (group 2, not the
throw $22 / $23, not a follow-up entry: condition bits 2 / 3, not the tag-in strike: bit 6, not air-only: bit 5), the
first notation of each command (one handler per command: the strengths share it); the desperation moves with life 20;
the inputs = each button alone, with each stick direction and after each stick motion of its own command list (a
follow-up is a command list entry: nothing else can start one), a mash (the button 4 times) when its list has one.

Moments: the input's button lands t frames after the move's own button, t in TIMES (covering every part of the moves:
236C's three parts end by ~200 frames, the Phoenix's sequence by ~330)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_kz as cap, fighters_kz as FK, commands_kz

OUT = '/data/neogeo_dict/kizuna/kim_brute.json'
LOW = '108313=14,108315=14,108391=14'
MOVES = {'236C': ('3:D,3:DR,3:R,3:c,3:c,', None), '[2]8C': ('40:D,3:Uc,3:Uc,', None), '214B': ('3:D,3:DL,3:L,3:b,3:b,', None),
         '421A': ('3:L,3:D,3:DL,3:a,3:a,', LOW), '6246A': ('3:R,3:D,3:L,3:R,3:a,3:a,', LOW)}
MOTIONS = {'': '', '6': 'R', '4': 'L', '2': 'D', '8': 'U', '3': 'DR', '1': 'DL',
           '236': '3:D,3:DR,3:R,', '214': '3:D,3:DL,3:L,', '[2]8': '30:D,3:U,', '421': '3:L,3:D,3:DL,', '623': '3:R,3:D,3:DR,'}
TIMES = (12, 24, 36, 48, 60, 75, 90, 110, 130)
THREADS = 11
STATE = cap.VS
NEUTRAL = {0xA0, 0x1, 0x2, 0x3, 0x4, 0x7, 0xA3, 0x9, 0xA, 0xB, 0x81, 0x82, 0x0}
SITU = {'whiff': (560, ''), 'hit': (300, ''), 'block': (300, 'R')}
STARTS = {0x50, 0x46, 0x5A}                                 # a button of the motion seen first (far B / A / C)
NAME = 'kim'
LETTERS = ((1, 'U'), (2, 'D'), (4, 'L'), (8, 'R'))
def stick(v): return ''.join(k for b, k in LETTERS if v & b)

def setup(name):
    """another fighter's specials, motions and neutral animations (module doc)"""
    global NAME, STATE, TIMES
    NAME = name; STATE = FK.state(name)
    if name == 'kim': return
    ch = FK.CAST[name]
    TIMES = (12, 24, 36, 50, 70, 95, 130)
    NEUTRAL.clear(); NEUTRAL.update({FK.kim_anim(ch, a) for a in (0xA0, 0x1, 0x2, 0x3, 0x4, 0x7, 0xA3, 0x9, 0xA, 0xB, 0x81, 0x82)} | {0})
    STARTS.clear(); STARTS.update({FK.kim_anim(ch, a) for a in (0x50, 0x46, 0x5A)})
    MOVES.clear(); MOTIONS.clear(); MOTIONS.update({'': '', '6': 'R', '4': 'L', '2': 'D', '8': 'U', '3': 'DR', '1': 'DL'})
    seen = set()
    for c in commands_kz.commands(ch):
        st = c['steps']
        if len(st) > 1 and not st[0][0] & 0x40 and st[-1][0] & 0x40: continue
        if len(st) > 2 and st[1][0] & 0x0F in (1, 2) and st[1][2] == 0 and st[0][2] & 0xF0 and st[2][2] & 0xF0:   # a mash
            MOTIONS['mash'] = 'mash'
        else:
            mo = ''.join(f'{max(w, 1) + 10 if t & 0x0F == 0x0B else 3}:{stick(v) or "-"},' for t, w, v in reversed(st[1:]))
            if mo and c['command'] >= 0x22: MOTIONS[commands_kz.notation(st).rstrip('ABCD')] = (mo, stick(st[0][2]))
        if c['command'] < 0x24 or c['cond'] & 0x6C or c['command'] in seen: continue
        seen.add(c['command'])
        seq = ''.join(f'{max(w, 1) + 10 if t & 0x0F == 0x0B else 3}:{inp(v)},' for t, w, v in reversed(st)) + f'3:{inp(st[0][2])},'
        MOVES[c['notation']] = (seq, LOW if c['cond'] & 0x4400 else None)

def inp(v): return (stick(v) + ''.join(k for b, k in ((16, 'a'), (32, 'b'), (64, 'c'), (128, 'd')) if v & b)) or '-'

def press(motion, b):
    m = MOTIONS[motion]
    if m == 'mash': return f'3:{b},3:-,' * 4 + f'3:{b},'
    if isinstance(m, tuple): return m[0] + f'3:{m[1]}{b},'
    if ',' in m: return m + f'3:{m.split(",")[-2].split(":")[1]}{b},'      # the motion, its last direction + the button
    return f'3:{m}{b},'

def run1(move, situ, motion, b, t):
    seq0, pokes = MOVES[move]
    p2x, hold = SITU[situ]
    pre = '2:-,' + seq0
    btn_at = cap.nframes(pre)                                 # the move's button lands about here
    ins = press(motion, b) if b else ''
    lead = cap.nframes(ins) - 3 if ins else 0
    gap = max(1, t - 3 - lead) if ins else 1
    seq = pre + f'{gap}:-,' + ins + '200:-' if ins else pre + '300:-'
    n = cap.nframes(seq)
    seq2 = f'{n}:{hold}' if hold else ''
    pk = ';'.join(f'{f}:' + ','.join(([f'108424={p2x >> 8:02X},108425={p2x & 255:02X}'] if f < 6 else []) + ([pokes] if pokes else []))
                  for f in range(n) if f < 6 or pokes)
    an = []
    started = False
    for a in cap.p1_anims(seq, seq2, pokes=pk or None, load=STATE):
        a &= 0xFFF
        if not started:
            if a in NEUTRAL or a in STARTS: continue
            started = True
        if a in NEUTRAL: break
        if not an or an[-1] != a: an.append(a)
    return an

def run2(move, situ, first, motion, b, t):
    """a second input after a first that gave a continuation (first = (motion + button, time)): the chain's next part"""
    seq0, pokes = MOVES[move]
    p2x, hold = SITU[situ]
    pre = '2:-,' + seq0
    m1, t1 = first
    i1 = press(m1[:-1], m1[-1].lower()); l1 = cap.nframes(i1) - 3
    seq = pre + f'{max(1, t1 - 3 - l1)}:-,' + i1
    i2 = press(motion, b); l2 = cap.nframes(i2) - 3
    seq += f'{max(1, t - t1 - 3 - l2)}:-,' + i2 + '250:-'
    n = cap.nframes(seq)
    pk = ';'.join(f'{f}:' + ','.join(([f'108424={p2x >> 8:02X},108425={p2x & 255:02X}'] if f < 6 else []) + ([pokes] if pokes else []))
                  for f in range(n) if f < 6 or pokes)
    an, started = [], False
    for a in cap.p1_anims(seq, f'{n}:{hold}' if hold else '', pokes=pk or None, load=STATE):
        a &= 0xFFF
        if not started:
            if a in NEUTRAL or a in STARTS: continue
            started = True
        if a in NEUTRAL: break
        if not an or an[-1] != a: an.append(a)
    return an

_OTHER = {}
def others():
    """the animations of the fighter's normals, jumps and movement (its capture: every recipe but the commands and the
    reactions): a continuation that starts one is a cancel into a normal, not a follow-up"""
    if NAME not in _OTHER:
        cap_ = json.load(open(FK.path(NAME, 'capture')))
        _OTHER[NAME] = {f[0][0] for k, d in cap_.items() if not k.startswith(('cmd_', 'sw_', 'react_')) for f in d['frames']}
    return _OTHER[NAME]

def plains(out):
    """{situation: the move's own sequence there (no input)}"""
    return {s: k for k, v in out.items() for s, inp, t in v if not inp}

def followup(out, k):
    """sequence k (a brute-force outcome) continues the move: an animation none of its plain sequences plays, the first
    of them not a normal's (Kim: kept as it was, every outcome but the most common)"""
    if NAME == 'kim': return True
    pa = {int(a, 16) for p in plains(out).values() for a in p.split()}
    new = [int(a, 16) for a in k.split() if int(a, 16) not in pa]
    return bool(new) and new[0] not in others() - pa

def level2(path):
    """for every continuation found (a part the plain move does not play), every input again after it"""
    data = json.load(open(path))
    for move, out in list(data.items()):
        if move.endswith(' L2'): continue
        plain = max(out, key=lambda k: len(out[k]))
        firsts = {}
        for k, v in out.items():
            if k == plain: continue
            if len(v) > 100 or not any(inp for s, inp, t in v): continue   # what any input gives (a hit's own sequence, a capture cut short): not a follow-up
            if not followup(out, k): continue
            for s, inp, t in v:
                if not inp: continue
                if (k, s) not in firsts or t < firsts[(k, s)][1]: firsts[(k, s)] = (inp, t)
        res2 = {}
        for (k, s), (inp, t1) in firsts.items():
            jobs = [(m, b, t1 + dt) for m in MOTIONS for b in 'abcd' for dt in (12, 24, 36, 48, 60, 80)]
            with ThreadPoolExecutor(THREADS) as ex:
                rr = list(ex.map(lambda j: (j, run2(move, s, (inp, t1), *j)), jobs))
            for (m, b, t), an in rr:
                res2.setdefault(' '.join(f'{a:X}' for a in an), []).append([s, f'{inp}@{t1} then {m}{b.upper()}', t])
        data[move + ' L2'] = res2
        print(move, 'level 2:', {k: len(v) for k, v in res2.items()})
        json.dump(data, open(path, 'w'))

def main():
    av = sys.argv[1:]
    if '--char' in av: i = av.index('--char'); setup(av[i + 1]); del av[i:i + 2]
    if '--level2' in av: return level2(av[av.index('--level2') + 1])
    path = av[0] if av else FK.path(NAME, 'brute')
    moves = av[1:] or list(MOVES)
    data = json.load(open(path)) if os.path.exists(path) else {}
    for move in moves:
        jobs = [(s, '', '', 0) for s in SITU] + [(s, m, b, t) for s in SITU for m in MOTIONS for b in 'abcd' for t in TIMES]
        with ThreadPoolExecutor(THREADS) as ex:
            res = list(ex.map(lambda j: (j, run1(move, *j)), jobs))
        out = {}
        for (s, m, b, t), an in res:
            k = ' '.join(f'{a:X}' for a in an)
            out.setdefault(k, []).append([s, m + b.upper(), t])
        data[move] = out
        base = {s: next(' '.join(f'{a:X}' for a in an) for (s_, m, b, t), an in res if s_ == s and not b) for s in SITU}
        print(move, 'plain:', base)
        for k, v in sorted(out.items(), key=lambda kv: -len(kv[1])):
            if k in base.values() and len(v) > 40: print(f'  {k:30s} {len(v)} runs (the plain move)'); continue
            print(f'  {k:30s} {len(v)} runs, e.g.', v[:4])
        json.dump(data, open(path, 'w'))

if __name__ == '__main__':
    main()
