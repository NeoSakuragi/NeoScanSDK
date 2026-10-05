#!/usr/bin/env python3
"""Kizuna Encounter's move sub-state logic decoded from the 68000 code: every special's handler as a graph of sub-states
(the README's "Move sub-states"), for any character.

    python3 substates_kz.py [char] [--json OUT]     (default Kim, 5)

The model [code]: a fighter is a task whose long +$00 is the routine it runs next frame (a coroutine: each sub-state ends
`movel #next,%a4@` + rts). A command the COMND scan accepts (commands_kz.py, $2D948) is written to +$20 as group << 8 |
command; its handler = long[T + 4 command] & $FFFFFF, T = long[B + 4 group], B = long[$5FCE2 + 8 char + (4 in the air)]
($2E660; group 2 = the specials). A handler's routines use a small vocabulary of calls and flags (VOCAB): $293E6 / $293DC
set the state +$22 (its animation: word[long[$69118 + 4 char] + 2 state]), $13816 ticks the animation (Z clear = it
ended), +$106 bit 0 = a hit of this move landed, +$107 bit 3 = a follow-up command was accepted (the COMND scan accepts
command entries with condition bit 3 only while +$10C bit 3, the move's window, is set and +$1EB = this move's
command), +$10C bit 3 opened / closed by the move, $29432 / $29470 the landing test, the victim (a3) driven by its
+$1AF bits 4-7 (scripted phases; the desperation moves go on only when the hit caught: the fighter's +$12B bit 5), $12FFA spawns a task (its routine `lea pc@(R),%a0`, its
name the two longs written at +$10 / +$14).

The walker follows every path through each routine (branches both ways) and reports per path: the conditions met and the
actions (state set -> animation, next routine, window, spawns, victim phases, end = back to the neutral routine $377E4 /
$37914). A part = a state's animation; its trigger = the conditions on the path that sets it (ANIM_END: when the
current part ends; HIT: on a landed hit, at once if ANIM_END is not also required; FOLLOWUP: the window's command)."""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kz, commands_kz

PBIN = '/data/tmp/kizuna/p.bin'
NEUTRAL = {0x377E4: 'neutral (stand)', 0x37914: 'neutral'}
VOCAB = {   # (mnemonic, operands) -> the atom it tests or does
    'jsr 0x13816': 'ANIM_END', 'jsr 0x29432': 'LANDED', 'jsr 0x29470': 'LANDED',
    'btst #0,%a4@(262)': 'HIT_LANDED', 'btst #3,%a4@(263)': 'FOLLOWUP', 'btst #5,%a4@(299)': 'HIT_CAUGHT',
    'btst #0,%a4@(265)': 'ON_GROUND', 'tstw %a4@(40)': 'AIRBORNE', 'bclr #1,%a4@(14)': 'STEP_EVENT',
    'btst #1,%a4@(14)': 'STEP_EVENT', 'btst #2,%a4@(297)': 'VICTIM_DOWN', 'tstl %a4@(52)': 'MOVING',
}
ACTS = {'bset #3,%a4@(268)': 'WINDOW_OPEN', 'bclr #3,%a4@(268)': 'WINDOW_CLOSE', 'bclr #3,%a4@(263)': 'FOLLOWUP_CLEAR',
        'addqb #1,%a4@(359)': 'FOLLOWUP_COUNT+1', 'bset #4,%a4@(14)': 'FLAG_E4'}

_dis = {}
def dis(a, b):
    """{addr: (mnemonic, operands, next addr)} for [a, b)"""
    if not os.path.exists(PBIN): os.makedirs(os.path.dirname(PBIN), exist_ok=True); open(PBIN, 'wb').write(kz.P)
    key = (a, b)
    if key in _dis: return _dis[key]
    out = subprocess.run(['m68k-linux-gnu-objdump', '-D', '-b', 'binary', '-m', 'm68k:68000', f'--start-address={a}',
                          f'--stop-address={b}', PBIN], capture_output=True, text=True).stdout
    ins, prev = {}, None
    for l in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\t[0-9a-f ]+\t(\S+)\s*(.*)', l)
        if not m: continue
        ad = int(m.group(1), 16)
        ins[ad] = [m.group(2), m.group(3).strip(), None]
        if prev is not None: ins[prev][2] = ad
        prev = ad
    _dis[key] = ins
    return ins

def state_anim(ch, s): return kz.u16(kz.u32(0x69118 + 4 * ch) + 2 * s) & 0xFFF

def handlers(ch, group=2, air=False):
    B = kz.u32(0x5FCE2 + 8 * ch + (4 if air else 0)); T = kz.u32(B + 4 * group)
    out = {}
    for c in range(0x20, 0x40):
        r = kz.u32(T + 4 * c) & 0xFFFFFF
        if r and r != 0x37DFC: out[c] = r
    return out

def paths(ins, start):
    """every path through a routine: (conditions [(atom, value)], actions [...]) until rts / a jump away"""
    res = []
    def walk(a, conds, acts, last, depth):
        while a in ins and depth < 200:
            mn, op, nx = ins[a]; depth += 1
            key = f'{mn} {op}'
            if mn == 'rts': res.append((conds, acts)); return
            if key in VOCAB: last = VOCAB[key]
            elif mn.startswith('btst') or mn.startswith('tst') or mn.startswith('cmp'): last = key
            if key in ACTS: acts = acts + [ACTS[key]]
            m = re.match(r'#(-?\d+),%d0', op)
            if mn == 'movew' and m: d0 = int(m.group(1)) & 0xFFFF; acts = acts + [('d0', d0)]
            m = re.match(r'%pc@\(0x([0-9a-f]+),%d0:w\),%d0', op)
            if mn == 'movew' and m:                      # a state picked at random from a table (421A: 16 words)
                tb = int(m.group(1), 16); ws = []
                while len(ws) < 16 and kz.u16(tb + 2 * len(ws)) < 0x200: ws.append(kz.u16(tb + 2 * len(ws)))   # up to the code after it
                acts = acts + [('d0', sorted(set(ws)))]
            if mn == 'jsr' and op in ('0x293e6', '0x293dc'):
                d0 = next((x[1] for x in reversed(acts) if isinstance(x, tuple) and x[0] == 'd0'), None)
                acts = acts + [('STATE', d0)]
            m = re.match(r'#(\d+),%a4@$', op)
            if mn == 'movel' and m: acts = acts + [('NEXT', int(m.group(1)))]
            m = re.match(r'#(\d),%a3@\(431\)', op)
            if mn == 'bset' and m: acts = acts + [('VICTIM_PHASE', int(m.group(1)))]
            m = re.match(r'%pc@\(0x([0-9a-f]+)\),%a0', op)
            if mn == 'lea' and m: acts = acts + [('SPAWN', int(m.group(1), 16))]
            if mn == 'bsrw' and op.startswith('0x'):
                acts = acts + [('CALL', int(op, 16))]
            if mn in ('bras', 'braw'): a = int(op, 16); continue
            if re.match(r'b(eq|ne|le|gt|lt|ge|cc|cs|mi|pl|hi|ls)[sw]?$', mn) and op.startswith('0x'):
                cc = mn[1:3]
                t = int(op, 16)
                # taken / not taken with the condition's value: Z (eq) or not, y <= 0 (le) ...
                walk(t, conds + [(last, cc)], acts, last, depth)
                inv = {'eq': 'ne', 'ne': 'eq', 'le': 'gt', 'gt': 'le', 'lt': 'ge', 'ge': 'lt', 'cc': 'cs', 'cs': 'cc', 'mi': 'pl', 'pl': 'mi', 'hi': 'ls', 'ls': 'hi'}[cc]
                conds = conds + [(last, inv)]
            a = nx
        res.append((conds, acts))
    walk(start, [], [], None, 0)
    return res

def meaning(atom, cc):
    """a branch condition in words"""
    t = {'ANIM_END': ('the animation ended', 'ne'), 'LANDED': ('on the floor', 'ne'), 'HIT_LANDED': ('a hit landed', 'ne'),
         'FOLLOWUP': ('the follow-up command came', 'ne'), 'HIT_CAUGHT': ('the hit caught (+$12B bit 5)', 'ne'),
         'ON_GROUND': ('on the ground (+$109 bit 0)', 'ne'), 'STEP_EVENT': ('the step event flag (+$0E bit 1)', 'ne'),
         'VICTIM_DOWN': ('+$129 bit 2', 'ne'), 'MOVING': ('moving (vx != 0)', 'ne')}
    if atom == 'AIRBORNE': return 'in the air (y > 0)' if cc == 'gt' else 'on the floor (y <= 0)'
    if atom in t: return t[atom][0] if cc == t[atom][1] else 'not ' + t[atom][0]
    return f'{atom} {cc}'

def decode(ch, cmd, entry, limit=40):
    """the sub-state graph of one handler: {routine: [{'if': [...], 'do': [...], 'next': routine}]}"""
    graph, todo, seen = {}, [entry], set()
    while todo and len(seen) < limit:
        r = todo.pop(0)
        if r in seen or r in NEUTRAL: continue
        seen.add(r)
        ins = dis(r, r + 0x200)
        out = []
        for conds, acts in paths(ins, r):
            do, nxt = [], None
            for x in acts:
                if isinstance(x, tuple) and x[0] == 'STATE' and x[1] is not None:
                    for st in (x[1] if isinstance(x[1], list) else [x[1]]): do.append(f'state {st} (anim {state_anim(ch, st):X})')
                elif isinstance(x, tuple) and x[0] == 'NEXT': nxt = x[1]
                elif isinstance(x, tuple) and x[0] == 'VICTIM_PHASE': do.append(f'victim phase bit {x[1]}')
                elif isinstance(x, tuple) and x[0] == 'SPAWN': do.append(f'spawn task {x[1]:X}')
                elif isinstance(x, str): do.append(x)
            ifs = [meaning(a, c) for a, c in conds if a]
            if nxt and nxt not in NEUTRAL and nxt not in seen: todo.append(nxt)
            out.append({'if': ifs, 'do': do, 'next': (NEUTRAL.get(nxt) or f'{nxt:X}') if nxt else 'same'})
        graph[f'{r:X}'] = out
    return graph

def parts_of(graph):
    """the move's parts and what starts each: [(anim, trigger words)]"""
    out = []
    for r, ps in graph.items():
        for p in ps:
            for d in p['do']:
                if d.startswith('state'):
                    out.append((d, r, p['if']))
    return out

def needs(graph):
    """per animation the decoded model sets: (needs the follow-up command, needs a landed hit, needs it to catch);
    an animation set on several paths needs what all of them need"""
    out = {}
    for r, ps in graph.items():
        for p in ps:
            for d in p['do']:
                m = re.match(r'state \d+ \(anim ([0-9A-F]+)\)', d)
                if not m: continue
                a = int(m.group(1), 16)
                n = ('the follow-up command came' in p['if'], 'a hit landed' in p['if'], 'the hit caught (+$12B bit 5)' in p['if'])
                out[a] = tuple(x and y for x, y in zip(out[a], n)) if a in out else n
    return out

def check(ch, brute_path, moves):
    """the decoded model vs the brute force (brute_kz.py): every animation either finds, the inputs and situations of
    each follow-up / hit-only part; -> (agreements, disagreements)"""
    br = json.load(open(brute_path))
    cmds = commands_kz.commands(ch)
    hs = handlers(ch)
    ok, bad = [], []
    for name, cmd in moves.items():
        g = decode(ch, cmd, hs[cmd]); nd = needs(g)
        first = {state_anim(ch, int(re.match(r'state (\d+)', d).group(1))) for p in g[f'{hs[cmd]:X}'] for d in p['do'] if d.startswith('state')}
        runs = []                                    # (animations, situation, the input that gave them)
        l1 = {int(x, 16) for seq in br.get(name, {}) for x in seq.split()}
        for key in (name, name + ' L2'):
            for seq, v in br.get(key, {}).items():
                an = [int(x, 16) for x in seq.split()]
                if not an or an[0] not in first: continue
                if key == name: runs += [(an, s, inp) for s, inp, t in v]
                else: runs += [([a for a in an if a not in l1], s, inp.split(' then ')[-1]) for s, inp, t in v]   # a second
                                                     # input's part: the ones the first level never saw
        seen = {a for an, s, i in runs for a in an}
        follow = sorted({c['notation'] for c in cmds if c['command'] == cmd and c['cond'] & 8})
        for a, (fu, hit, caught) in sorted(nd.items()):
            rs = [(s, i) for an, s, i in runs if a in an]
            if a not in seen: bad.append(f'{name}: anim {a:X} decoded, never seen by the brute force'); continue
            sits = sorted({s for s, i in rs})
            if fu:
                ins = sorted({i.split(' then ')[-1] for s, i in rs})
                (ok if set(ins) <= set(follow) else bad).append(f'{name}: {a:X} after the follow-up {follow} (window command): brute inputs {ins}, situations {sits}')
            elif hit:
                (ok if set(sits) <= ({'hit'} if caught else {'hit', 'block'}) else bad).append(
                    f'{name}: {a:X} only on a hit{" that caught" if caught else ""}: brute situations {sits}')
            else: ok.append(f'{name}: {a:X} decoded and seen ({sits})')
        for a in sorted(seen - set(nd)):
            bad.append(f'{name}: anim {a:X} seen by the brute force, not set by the decoded handler')
    return ok, bad

if __name__ == '__main__' and '--check' in sys.argv:
    ok, bad = check(5, sys.argv[sys.argv.index('--check') + 1], {'236C': 0x25, '[2]8C': 0x28, '214B': 0x27, '421A': 0x2A, '6246A': 0x29})
    for l in ok: print('agree   ', l)
    for l in bad: print('DISAGREE', l)
    sys.exit(0)

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    ch = int(args[0]) if args else 5
    jo = sys.argv[sys.argv.index('--json') + 1] if '--json' in sys.argv else None
    cmds = {c['command']: c['notation'] for c in commands_kz.commands(ch)}
    res = {}
    for cmd, r in handlers(ch).items():
        if cmd not in cmds: continue
        g = decode(ch, cmd, r)
        res[f'{cmd:02X} {cmds[cmd]}'] = {'entry': f'{r:X}', 'graph': g}
        print(f'== command {cmd:02X} {cmds[cmd]} handler {r:X}')
        for rt, ps in g.items():
            for p in ps:
                if not p['do'] and p['next'] == 'same': continue
                print(f'  {rt}: if {" and ".join(p["if"]) or "always"}: {", ".join(p["do"]) or "-"} -> {p["next"]}')
    if jo: json.dump(res, open(jo, 'w'), indent=1)
