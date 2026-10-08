#!/usr/bin/env python3
"""Revamp phase 4b: how far the piece score agrees with Bruno's reviews (docs/brawler_review/<fighter>.md: each piece's
Keep / Drop), before and after a scorer change. A piece is predicted Keep when its score is >= T (T = 60, the same for
both; the roster's median appeal was 63), and each side is also shown at its own best T. Also: his named roles
(starter, intermediate, crumple, hold hit, dash attack) against the pieces the scorer marks with them.

    python3 tools/brawler/review_agree.py GAME_DIR BEFORE_PIECES_PY [FIGHTER ...]   (default: the reviewed three)
BEFORE_PIECES_PY: the old pieces.py (git show <rev>:tools/brawler/pieces.py > file); its 'appeal' is the old score."""
import importlib.util, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import pieces as NEW

ROLE_WORDS = [('starter', 'starter'), ('intermediate', 'intermediate'), ('crumpling', 'crumple'), ('grabbing', 'hold'), ('fwd fwd', 'dash')]


def answers(name):
    out, roles = {}, {}
    for line in open(os.path.join(HERE, '..', '..', 'docs', 'brawler_review', name + '.md')):
        m = re.match(r'- (\S+): (Keep|Drop|None)(?: — "(.*)")?', line)
        if not m or m.group(1) in out: continue
        out[m.group(1)] = m.group(2)
        note = (m.group(3) or '').lower()
        for w, r in ROLE_WORDS:
            if w in note and 'not ' + w not in note and not note.startswith('starter is missing'): roles.setdefault(m.group(1), set()).add(r)
    return out, roles


def agree(vals, ans, T):
    return sum(1 for k, v in vals.items() if k in ans and ans[k] in ('Keep', 'Drop') and (v >= T) == (ans[k] == 'Keep'))


def main():
    game, before = sys.argv[1], sys.argv[2]
    names = sys.argv[3:] or ['terry', 'kim', 'krauser']
    spec = importlib.util.spec_from_file_location('pieces_before', before); OLD = importlib.util.module_from_spec(spec)
    sys.modules['pieces_before'] = OLD; spec.loader.exec_module(OLD); OLD.HERE = HERE      # its paths: this tree's
    T = 60
    rows, tot = [], [0, 0, 0, 0, 0]
    print('| fighter | answered Keep / Drop | before (appeal >= 60) | after (score >= 60) | before, best T | after, best T | his roles marked |')
    print('|---|---|---|---|---|---|---|')
    for n in names:
        ans, roles = answers(n)
        o = {p['id']: p['appeal'] for p in OLD.catalogue(OLD.Fighter(game, n))}
        cat = NEW.catalogue(NEW.Fighter(game, n)); nw = {p['id']: p['score'] for p in cat}
        k = sum(1 for p in o if ans.get(p) in ('Keep', 'Drop'))
        bo = max((agree(o, ans, t), t) for t in range(30, 95)); bn = max((agree(nw, ans, t), t) for t in range(30, 95))
        by = {p['id']: p for p in cat}; roles = {k: v for k, v in roles.items() if k in by}
        rm = sum(1 for pid, rs in roles.items() for r in rs if pid in by and r in by[pid]['roles'])
        rt = sum(len(rs) for rs in roles.values())
        miss = [f'{pid} {r}' for pid, rs in roles.items() for r in rs if not (pid in by and r in by[pid]['roles'])]
        if miss: print(f'<!-- {n}: his roles not marked: {", ".join(miss)} -->')
        a0, a1 = agree(o, ans, T), agree(nw, ans, T)
        print(f'| {n} | {k} | {a0} | {a1} | {bo[0]} (T {bo[1]}) | {bn[0]} (T {bn[1]}) | {rm} / {rt} |')
        for i, v in enumerate((k, a0, a1, rm, rt)): tot[i] += v
    print(f'| all | {tot[0]} | {tot[1]} | {tot[2]} | | | {tot[3]} / {tot[4]} |')
    for n in names:                                    # the disagreements, for the record
        ans, _ = answers(n)
        cat = NEW.catalogue(NEW.Fighter(game, n))
        bad = [f"{p['id']} {ans[p['id']]} {p['score']}" for p in cat if ans.get(p['id']) in ('Keep', 'Drop') and (p['score'] >= T) != (ans[p['id']] == 'Keep')]
        print(f'{n}: after, disagreeing: {", ".join(bad) or "none"}')


if __name__ == '__main__':
    main()
