#!/usr/bin/env python3
"""A fighter's specials as export_kz takes them (Kim's are written by hand in export_kz: SPECIALS / FOLLOW), made from its
captures: capture_kz (the command list played: sw_ whiff, cmd_ near), followups_kz (each brute-forced special whiff /
hit / every continuation found), substates_kz (the handlers: a victim driven by script = carried).

    python3 plan_kz.py NAME          -> fighters_kz.path(NAME, 'follow'): {'specials', 'follow', 'air', 'report'}

specials: every special command of its list (group 2 handlers but the throw $22 / $23; one per notation: the strengths
are moves of their own; not the follow-up entries, condition bits 2 / 3; not air-only, bit 5) -> [whiff capture, near
capture, its animations]; the desperation moves (life <= 96) from their _low captures, the tag-in strike (bit 6) with
the tag-in pokes (capture_kz TAGIN).
follow: the multipart ones (followups_kz module doc: the parts / links rule) -> export_kz FOLLOW entries.
air: its air special (an air-only command, bit 5) -> its first animation (the brawler's down+A in the air, Kim's j.2B).
report: per move the decoded parts vs the captured ones."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fighters_kz as FK, commands_kz

def seq(fr, neutral, starts):
    """P1's animations from the move's start to neutral (brute_kz's rule) and the frame count of each run"""
    an, started = [], False
    for f in fr:
        a = f[0][0]
        if not started:
            if a in neutral or a in starts: continue
            started = True
        if a in neutral: break
        if an and an[-1][0] == a: an[-1][1] += 1
        else: an.append([a, 1])
    return an

STICK = {'6': 'f', '3': 'df', '2': 'd', '9': 'uf', '8': 'u', '1': 'f', '4': 'f', '7': 'u', '5': ''}
def brawler_key(notation, own):
    """a follow-up input -> export_bm link input: the move's own command again = 'again', else the stick at its motion's
    end + A (the brawler's attack button: Kizuna's A-D are one button there)"""
    if own: return 'again'
    m = notation.rstrip('ABCD')
    if m in ('', 'mash'): return 'A'
    d = m.replace('[', '').replace(']', '')[-1]
    return STICK.get(d, '') + 'A'

def plan_move(name, mv, fc, recipes, neutral, starts, cmd, graph):
    """FOLLOW entry of move mv (or None: one part) + a report line"""
    S = []                                               # (rec, [anims], kind, inputs, situs)
    for rec in [f'{mv}_w', f'{mv}_h'] + sorted(r for r in fc if r.startswith(f'{mv}_c')):
        if rec not in fc: continue
        sq = seq(fc[rec]['frames'], neutral, starts)
        kind = 'w' if rec.endswith('_w') and '_c' not in rec[len(mv):] else 'h' if rec == f'{mv}_h' else 'c'
        r = recipes.get(rec)
        S.append((rec, sq, kind, r[4] if r and len(r) > 4 else [], r[5] if r and len(r) > 5 else []))
    W = next(s for s in S if s[2] == 'w'); H = next((s for s in S if s[2] == 'h'), None)
    an = lambda s: [a for a, n in s[1]]
    rep = {'whiff': [f'{a:X}' for a in an(W)], 'hit': [f'{a:X}' for a in an(H)] if H else None,
           'continuations': [{'rec': s[0], 'anims': [f'{a:X}' for a in an(s)], 'inputs': s[3], 'found_in': s[4]} for s in S if s[2] == 'c']}
    conts = [s for s in S if s[2] == 'c' and an(s) not in (an(W), an(H) if H else None)]
    rep['not_reproduced'] = [s[0] for s in S if s[2] == 'c' and s not in conts]
    if not conts and (H is None or an(H) == an(W)): return None, rep
    order = [W] + ([H] if H and an(H) != an(W) else []) + conts
    nodes = {}                                           # prefix tuple -> part index; parts in creation order
    parts, nexts, links, made = [], [], [], []
    for s in order:
        a = an(s)
        cuts = sorted({i for o in order if o is not s for i in range(1, len(a))
                       if an(o)[:i] == a[:i] and (len(an(o)) == i or an(o)[i] != a[i])})
        bounds = [0] + cuts + [len(a)]
        prev = None; ninp = 0
        for j in range(len(bounds) - 1):
            key = tuple(a[:bounds[j + 1]])
            if key not in nodes:
                nodes[key] = len(parts); parts.append([s[0], a[bounds[j]:bounds[j + 1]]]); nexts.append(None); made.append(s[0])
            p = nodes[key]
            if prev is not None and nexts[prev] != p:
                link = next((l for l in links if l[0] == prev and l[1] == p), None)
                if link is None and nexts[prev] is None and (s[2] == 'w' or made[prev] == s[0]):
                    nexts[prev] = p                          # the sequence's own way on: the part's next
                elif link is not None:
                    ninp += link[2] != 'hit'                 # an input link this sequence also took
                else:
                    pa = parts[prev]; last = pa[1][-1]
                    # 'now' when this sequence plays the part's last animation shorter than the part's own capture
                    own = next(n for x, n in seq(fc[pa[0]]['frames'], neutral, starts)[::-1] if x == last)
                    here = s[1][bounds[j] - 1][1]
                    at = 'now' if here < own else 'end'
                    if s[2] == 'h' or not s[3]: links.append([prev, p, 'hit', None, last, at])
                    else:
                        inp = s[3][min(ninp, len(s[3]) - 1)][0]
                        own_cmd = any(c['command'] == cmd and c['notation'] == inp for c in commands_kz.commands(FK.CAST[name]))
                        on = 'input' if 'whiff' in s[4] else 'hit+input'   # contact (hit or block) needed
                        links.append([prev, p, on, brawler_key(inp, own_cmd), last, at, inp])
                        ninp += 1
            prev = p
    victim = any('victim phase' in d for ps in graph.values() for p in ps for d in p['do']) if graph else False
    hitparts = [i for i, (rec, a) in enumerate(parts) if rec.endswith('_h')]
    F = {'parts': [[rec, a, nexts[i]] for i, (rec, a) in enumerate(parts)], 'links': [l[:6] for l in links],
         'inputs': [l[6] if len(l) > 6 else None for l in links]}
    if victim and hitparts: F['carry'] = hitparts[0]; F['damage'] = parts[hitparts[0]][0]
    if any(o[1] >> 12 == FK.CAST[name] and not o[7].startswith('\0') for s in order for f in fc[s[0]]['frames'] for o in f[2]):
        F['objects'] = 1
    return F, rep

def write(name):
    import brute_kz, followups_kz, substates_kz
    brute_kz.setup(name); followups_kz.setup(name)
    ch = FK.CAST[name]
    cap = json.load(open(FK.path(name, 'capture')))
    fc = json.load(open(FK.path(name, 'followups')))
    sub = json.load(open(FK.path(name, 'substates'))) if os.path.exists(FK.path(name, 'substates')) else {}
    neutral, starts = brute_kz.NEUTRAL, brute_kz.STARTS
    cmds = commands_kz.commands(ch)
    out = {'specials': {}, 'follow': {}, 'air': None, 'report': {}}
    for c in cmds:
        n = c['notation']
        if c['command'] < 0x24 or c['cond'] & 0x0C or n in out['specials']: continue
        if c['cond'] & 0x20:                             # air only
            if out['air'] is None and f'cmd_{n}_air' in cap:
                s = seq(cap[f'cmd_{n}_air']['frames'], neutral | {FK.kim_anim(ch, a) for a in (0x9, 0xA, 0xB, 0x81)}, starts)
                if s: out['air'] = {'input': n, 'anim': s[0][0]}
            continue
        low = '_low' if f'sw_{n}_low' in cap and c['cond'] & 0x4400 else ''
        sw, near = f'sw_{n}{low}', f'cmd_{n}{low}_near'
        if sw not in cap: continue
        s = seq(cap[sw]['frames'], neutral, starts)
        if not s: out['report'][n] = 'plays nothing'; continue
        out['specials'][n] = [sw, near, [a for a, k in s]]
    for mv in brute_kz.MOVES:
        cmd = next(c['command'] for c in cmds if c['notation'] == mv)
        g = next((v['graph'] for k, v in sub.items() if int(k.split()[0], 16) == cmd), None)
        F, rep = plan_move(name, mv, fc, followups_kz.RECIPES, neutral, starts, cmd, g)
        out['report'][mv] = rep
        if F: out['follow'][mv] = F
    json.dump(out, open(FK.path(name, 'follow'), 'w'), indent=1)
    return out

if __name__ == '__main__':
    o = write(sys.argv[1])
    print('specials', {k: [f'{a:X}' for a in v[2]] for k, v in o['specials'].items()})
    print('air', o['air'])
    for k, F in o['follow'].items(): print(k, F)
