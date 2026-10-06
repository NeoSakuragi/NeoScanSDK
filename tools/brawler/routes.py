#!/usr/bin/env python3
"""Chain routes: each fighter's chain-combo tree (Chain Lab, 2026-10-05).

A routes file (tools/brawler/routes/<fighter>.json, written by hand or by the Chain Lab page) is a tree of hits:

    {"fighter": "terry",
     "links": {"A": NODE, "cA": NODE, "dA": NODE},           # the links from neutral (where a route starts)
     "entries": {"dash": NODE, "nospecial": NODE, "hold": NODE, "air_a": NODE, "air_b": NODE, "air_cd": NODE}}   # optional
    NODE = {"move": "atk_a_close",                           # one of the fighter's moves (MOVE_NAMES; an air node:
                                                             # AIR_MOVE_NAMES), or
            "special": "dD",                                 # a special slot (D, fD, dD, uD, dfD, ufD: the C slots, named
                                                             # by their old D inputs): a route ender, C inputs only
            "weight": "light" | "strong",                    # the victim's hit animation and hit stun (effect none)
            "effect": "none" | "knockdown" | "launch" | "trip" | "blowback",
            "keep": true,                                    # optional: keep the full animation on hit (it plays to its
                                                             # end, then the buffered input takes its link); left out (the
                                                             # default since 2026-10-05): on hit the next link starts as soon
                                                             # as its input comes, after the hit-stop
            "speed": 1.25,                                   # optional: playback speed, x KOF's timing (0.25-4; 1 left out),
                                                             # 8.8 fixed point in the game (rnode_t.speed)
            "damage": 3, "push": 3,                          # optional (advanced): default from weight / effect
            "links": {"A": NODE, "dfA": NODE, "AB": NODE, ...}}
    inputs (TODO #71, tree version 4: A is the only attack button; INPUTS = the game's RI_* order): A, B, dA (down), cA
    (close: an opponent within CLOSE_X, KOF's close normals), fA (forward), bA (back), dfA (down-forward); AB fAB dAB
    uAB dfAB ufAB (button C + the stick since 2026-10-06, the old A+B names kept: the specials, slots D fD dD uD dfD ufD). An A falls back in the game: down-forward -> forward ->
    down -> back -> close -> plain; a diagonal C: its link, else down's / up's, else plain C's. B is a jump-cancel
    (on hit, like every link): its node is an air move (atk_c_jump / atk_d_jump / atk_cd_jump), played by the first A in
    that jump (the stick picks the jump's direction), and an air node's A links chain in the same jump (an air
    sub-route). A route never starts with B (B from neutral is the jump) nor with C (the slot's special).

A fighter without a routes file gets default_tree(): the brawler's single table before the Chain Lab (fighter.c's
old COMBO), byte for byte the same behaviour. encode() turns a tree into the blob fighter.h describes (rt_head_t +
rnode_t[]), identical subtrees shared; the Chain Lab page has the same encoder in JavaScript (tools/brawler/chainlab/,
checked against this one by chainlab/check_encode.py)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTES_DIR = os.path.join(HERE, 'routes')
NORMAL_INPUTS = ['A', 'B', 'dA', 'cA', 'fA', 'bA', 'dfA']                               # fighter.h RI_A .. RI_DFA
SPECIAL_INPUTS = ['AB', 'fAB', 'dAB', 'uAB', 'dfAB', 'ufAB']                             # RI_S .. RI_UFS
INPUTS = NORMAL_INPUTS + [None, None] + SPECIAL_INPUTS                                  # fighter.h RI_* (slots 7, 8 unused)
SPECIALS = ['D', 'fD', 'dD', 'uD', 'dfD', 'ufD']                                         # BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_DF_D, BS_UF_D
SLOT_OF = dict(zip(SPECIAL_INPUTS, SPECIALS))                                            # a C input -> the slot it plays
MOVE_NAMES = ['atk_a_close', 'atk_a_far', 'atk_a_crouch', 'atk_b_close', 'atk_b_far', 'atk_b_crouch',
              'atk_c_close', 'atk_c_far', 'atk_c_crouch', 'atk_d_close', 'atk_d_far', 'atk_d_crouch', 'body_toss',
              'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d']                          # ground moves a route may play
AIR_MOVES = {'air_a': 'atk_c_jump', 'air_b': 'atk_d_jump', 'air_cd': 'atk_cd_jump'}     # the jump picks the animation
AIR_MOVE_NAMES = list(AIR_MOVES.values())                                                # an air node's moves (B links, air links)
ENTRIES = ['dash', 'nospecial', 'hold', 'air_a', 'air_b', 'air_cd']
WEIGHTS = ['light', 'strong']
EFFECTS = ['none', 'knockdown', 'launch', 'trip', 'blowback']                            # fighter.h RE_*
RF_SPECIAL, RF_AIR, RF_KEEP = 1, 2, 4
NODE_SIZE, HEAD_SIZE, RI_N, MAX_NODES = 24, 16, 15, 128                                  # tree version 4 (TREE_VERSION)
TREE_VERSION = 4
SPEED_MIN, SPEED_MAX = 0x40, 0x400


def speed_fx(nd):
    """a node's speed as the game's 8.8 (round half up: the page's Math.round)"""
    v = int(float(nd.get('speed', 1)) * 256 + 0.5)
    assert SPEED_MIN <= v <= SPEED_MAX, f'speed {nd.get("speed")} outside 0.25-4'
    return v


def default_damage(node):
    e = node.get('effect', 'none')
    if e != 'none': return {'knockdown': 8, 'launch': 9, 'trip': 7, 'blowback': 10}[e], 0
    return (6, 4) if node.get('weight') == 'strong' else (3, 3)


def default_tree():
    """every fighter without a routes file (TODO #71, one attack button): far A, far A, close C, close D, C+D (knockdown);
    close A: close B, far C, crouch D (trip); down+A: the sweep; forward+A = body toss (knockdown) and down+A = sweep inside
    any window; far A, far A, down-forward+A = far D (launch); B after a far A that hit = a jump-cancel (air C, then A:
    air C+D); every C = the special its input picks, cancelling a normal that hit. Air: A air C (A again on hit: air
    C+D), down+A air D, up+A air C+D. (Shared nodes repeated; encode() shares them again.)"""
    def n(move, dmg, w, eff, push, **links):
        return {'move': move, 'weight': w, 'effect': eff, 'damage': dmg, 'push': push,
                'links': {**links, **{k: {'special': SLOT_OF[k]} for k in SPECIAL_INPUTS}}}   # any C: the special its input picks
    air = lambda m, dmg, w, eff, push, **links: dict({'move': m, 'weight': w, 'effect': eff, 'damage': dmg, 'push': push}, **({'links': links} if links else {}))
    aircd = lambda: air('atk_cd_jump', 10, 'strong', 'knockdown', 0)
    airc = lambda: air('atk_c_jump', 6, 'strong', 'none', 4, A=aircd())                  # an air route: C, then C+D on hit
    toss = lambda: n('body_toss', 10, 'strong', 'knockdown', 0)
    sweep = lambda: n('atk_d_crouch', 7, 'strong', 'trip', 0)
    fin = lambda: {'fA': toss(), 'dA': sweep()}                                        # finishers inside any window
    a4 = n('atk_d_close', 6, 'strong', 'none', 4, A=toss(), **fin())
    a3 = n('atk_c_close', 6, 'strong', 'none', 4, A=a4, **fin())
    a2 = n('atk_a_far', 3, 'light', 'none', 3, A=a3, dfA=n('atk_d_far', 9, 'strong', 'launch', 0), B=airc(), **fin())
    a1 = n('atk_a_far', 3, 'light', 'none', 3, A=a2, B=airc(), **fin())
    c2 = n('atk_c_far', 5, 'strong', 'none', 5, A=sweep(), **fin())
    c1 = n('atk_b_close', 4, 'light', 'none', 3, A=c2, **fin())
    return {'fighter': None, 'links': {'A': a1, 'cA': c1, 'dA': sweep()},
            'entries': {'dash': toss(), 'nospecial': toss(), 'hold': toss(),
                        'air_a': airc(), 'air_b': air('atk_d_jump', 8, 'strong', 'knockdown', 0), 'air_cd': aircd()}}


def strip_specials(nd):
    """a tree without its special links (D inputs): the route ends where the special was"""
    out = {k: v for k, v in nd.items() if k != 'links'}
    links = {k: strip_specials(v) for k, v in (nd.get('links') or {}).items() if k not in SPECIAL_INPUTS}
    if links: out['links'] = links
    return out


ENEMY_PRESETS = ['jabs', 'no_specials']


def enemy_preset(name, own):
    """an enemy's named reduced move list (game.json enemies[].moves), from its fighter's own tree `own`:
    jabs         A, A, strong close C (three hits on A, close or far, no jump-cancel, no specials): a minion that only punches
    no_specials  its own tree without the special links (its routes, no special cancels)"""
    assert name in ENEMY_PRESETS, f'no enemy move preset {name} ({", ".join(ENEMY_PRESETS)})'
    if name == 'no_specials': return dict(strip_specials(own), entries={k: strip_specials(v) for k, v in (own.get('entries') or {}).items()})
    c = {'move': 'atk_c_close', 'weight': 'strong', 'effect': 'none'}
    a2 = {'move': 'atk_a_far', 'weight': 'light', 'effect': 'none', 'links': {'A': c}}
    a1 = {'move': 'atk_a_close', 'weight': 'light', 'effect': 'none', 'links': {'A': a2}}
    return {'fighter': own.get('fighter'), 'links': {'A': a1, 'cA': a1}}           # from any range


# ---- routes as the source (Bruno 2026-10-06): a routes file is a LIST OF ROUTES, each edited on its own ---------------
# {"fighter": ..., "routes": [[STEP, STEP, ...], ...], "entries": {...}}, STEP = {"input": "A", "move": ... | "special": ...,
# "weight", "effect", "keep"?, "speed"?, "damage"?, "push"?}. The build merges them into the game's tree (rnode_t, as
# before): routes that start with the same inputs AND the same hits there share those nodes (a trunk); two routes with
# the same inputs up to a step but a different hit there cannot both be in the game (it picks the next hit by input
# alone): a conflict, reported (which routes, which step, what differs) and the build refused.
HIT_FIELDS = ('move', 'special', 'weight', 'effect', 'keep', 'speed', 'damage', 'push')


def hit_of(nd):
    """a node's hit as the game plays it (defaults applied): what decides whether two routes' steps are the same hit"""
    if 'special' in nd: return {'special': nd['special'], 'speed': speed_fx(nd)}
    dd, dp = default_damage(nd)
    return {'move': nd.get('move'), 'weight': nd.get('weight', 'light'), 'effect': nd.get('effect', 'none'),
            'keep': bool(nd.get('keep')), 'speed': speed_fx(nd), 'damage': nd.get('damage', dd), 'push': nd.get('push', dp)}


def tree_to_routes(tree):
    """a tree (the old routes file / the ROM's shape) -> its routes, root to leaf, in link order"""
    out = []
    def walk(links, path):
        for k, ch in (links or {}).items():
            step = dict({f: ch[f] for f in HIT_FIELDS if f in ch}, input=k)
            if ch.get('links'): walk(ch['links'], path + [step])
            else: out.append([dict(x) for x in path + [step]])   # each route its own steps
    walk(tree.get('links'), [])
    return out


def merge_routes(routes):
    """routes -> (tree {'links': ...}, conflicts [{routes: (i, j) 1-based, step (1-based), input path, differs}]);
    a conflicting step is left out of the tree (the first route's hit stays)"""
    root = {'links': {}}; owner = {}; conflicts = []
    for ri, r in enumerate(routes):
        nd = root
        for si, st in enumerate(r):
            k = st['input']
            assert k in INPUTS and k is not None, f'route {ri + 1} step {si + 1}: unknown input {k}'
            assert si or k not in ('B',) + tuple(SPECIAL_INPUTS), f'route {ri + 1}: a route starts with an A (B from neutral jumps, C is the special)'
            hit = {f: st[f] for f in HIT_FIELDS if f in st}
            ch = (nd.get('links') or {}).get(k)
            if ch is None:
                assert 'special' not in nd, f'route {ri + 1} step {si + 1}: a special ends its route'
                ch = dict(hit); nd.setdefault('links', {})[k] = ch; owner[id(ch)] = ri
            elif hit_of(ch) != hit_of(hit):
                a, b = hit_of(ch), hit_of(hit)
                conflicts.append({'routes': (owner[id(ch)] + 1, ri + 1), 'step': si + 1, 'inputs': [x['input'] for x in r[:si + 1]],
                                  'differs': {f: (a.get(f), b.get(f)) for f in set(a) | set(b) if a.get(f) != b.get(f)}})
                break
            nd = ch
    return root, conflicts


def default_routes():
    """the default tree (the brawler's table before the Chain Lab) as routes"""
    return tree_to_routes(default_tree())


def load(name, path=None):
    """the fighter's tree: its routes file (game.json roster[].routes; entries it leaves out: the default's), else
    (path None) the default tree. A file with "routes" (the list form) is merged (merge_routes; a conflict is an
    error naming the routes and the step); the older tree form ("links") still loads as it is."""
    p = path
    d = default_tree()
    if p is None: return dict(d, fighter=name)
    t = json.load(open(p))
    if 'routes' in t:
        tree, conflicts = merge_routes(t['routes'])
        assert not conflicts, f'{p}: ' + '; '.join(f"routes {c['routes'][0]} and {c['routes'][1]} differ at step {c['step']} " \
            f"({' '.join(c['inputs'])}): " + ', '.join(f'{f} {x} / {y}' for f, (x, y) in c['differs'].items()) for c in conflicts)
        t = dict({k: v for k, v in t.items() if k != 'routes'}, links=tree['links'])
    t['entries'] = {**d['entries'], **t.get('entries', {})}
    t['fighter'] = name
    return t


def encode(tree, moves, has=None, specials_have=None):
    """tree -> bytes (fighter.h rt_head_t + rnode_t[]); moves: the BA_* order (export_bm.MOVES); has: the moves this
    fighter has (a route may not play a move it lacks: it would show its idle); specials_have: which BS_* exist (a
    missing one plays the nearest, fighter.c special_pick)"""
    nodes = [bytes(NODE_SIZE)]
    memo = {}
    def node(nd, where, air=False):
        key = json.dumps([nd, air], sort_keys=True)
        if key in memo: return memo[key]
        i = len(nodes); nodes.append(None); memo[key] = i
        nxt = [0] * RI_N
        for k, ch in (nd.get('links') or {}).items():
            assert k in INPUTS and k is not None, f'{where}: unknown input {k}'
            if k in SPECIAL_INPUTS:
                assert 'special' in ch, f'{where} {k}: a C input leads to a special'
                assert not air, f'{where} {k}: no special in the air'
            else: assert 'move' in ch, f'{where} {k}: an A / B input leads to a move'
            assert not (air and k == 'B'), f'{where}: no jump-cancel in the air'
            assert not (where == 'root' and (k == 'B' or k in SPECIAL_INPUTS)), f'root {k}: a route starts with an A'
            nxt[INPUTS.index(k)] = node(ch, f'{where} {k}', air or k == 'B')   # B: a jump-cancel, its node in the air
        if 'special' in nd:
            assert nd['special'] in SPECIALS, f'{where}: unknown special {nd["special"]}'
            assert not nd.get('links'), f'{where}: a special ends the route (no links)'
            anim, flags = SPECIALS.index(nd['special']), RF_SPECIAL
        elif nd.get('move') is None: anim, flags = 0, 0                                # the root
        else:
            m = nd['move']
            assert m in moves, f'{where}: unknown move {m}'
            assert m in (AIR_MOVE_NAMES if air else MOVE_NAMES), f'{where}: {m} is not an {"air" if air else "ground"} move'
            assert has is None or air or m in has, f'{where}: the fighter has no {m}'
            anim, flags = moves.index(m), (RF_AIR if air else 0) | (RF_KEEP if nd.get('keep') else 0)
        w, e = nd.get('weight', 'light'), nd.get('effect', 'none')
        assert w in WEIGHTS and e in EFFECTS, f'{where}: weight {w} / effect {e}'
        dd, dp = default_damage(nd)
        dmg, push = nd.get('damage', dd), nd.get('push', dp)
        assert 0 <= dmg <= 255 and -128 <= push <= 127, where
        sp = speed_fx(nd)
        nodes[i] = bytes([anim, flags, WEIGHTS.index(w), EFFECTS.index(e), dmg, push & 0xFF, sp >> 8, sp & 0xFF] + nxt + [0])
        return i
    root = node({'links': tree.get('links', {})}, 'root')
    d = default_tree()['entries']
    ent = [node((tree.get('entries') or {}).get(k) or d[k], k, air=k in AIR_MOVES) for k in ENTRIES]   # an air entry: its own
                                                         # move (air_a's default air C; any of the three)
    assert len(nodes) <= MAX_NODES, f'{len(nodes)} nodes (at most {MAX_NODES})'
    head = b'RT' + bytes([TREE_VERSION, len(nodes), root] + ent + [0] * 5)
    assert len(head) == HEAD_SIZE
    return head + b''.join(nodes)


def step_flags(steps):
    """per step (ticks, active, opens a hit): active = KOF's $0100 once an attack box was loaded (export_bm's rule); a
    new hit = an active step after an inactive one or after one without $4000 (bstep_t flags 1 / 4)"""
    live = False; out = []; prev_act = prev_chain = False
    for s in steps:
        fl = s.get('flags', 0)
        if any(k[0] == '1' and k.upper() != '1B' for k in s.get('boxes', {})): live = True
        a = bool(fl & 0x100) and live
        out.append((s['ticks'], a, a and not (prev_act and prev_chain)))
        prev_act, prev_chain = a, bool(fl & 0x4000)
    return out


def play_steps(sf, speed=0x100):
    """the steps shown frame by frame as fighter.c anim_tick plays them (KOF's ticks + 1 frames a step at 0x100, the time
    carried, an active step never skipped); the list ends before the frame the move is over"""
    shown = [0]; step = 0; acc = 0
    while True:
        acc += speed; done = False
        while True:
            d = (sf[step][0] + 1) << 8
            if acc < d: break
            if step + 1 < len(sf): acc -= d; step += 1
            else: done = True; break
            if sf[step][1]:                                  # an active step is never skipped
                d = (sf[step][0] + 1) << 8
                if acc >= d: acc = d - 1
                break
        if done: return shown
        shown.append(step)


def frame_data(steps, speed=0x100):
    """a move as the brawler plays it at this speed -> startup (frame of the first active, 1 = the press frame), active
    (first to last active frame), recovery, total, hits, travel (px forward), per-frame list ('-' inactive, 'x'
    active), steps [(ticks, active, opens a hit)] (the page recomputes them at a node's speed)"""
    sf = step_flags(steps); shown = play_steps(sf, speed)
    fr = [sf[k][1] for k in shown]
    first = next((i for i, a in enumerate(fr) if a), None)
    last = max((i for i, a in enumerate(fr) if a), default=None)
    hits = len({k for k in shown if sf[k][2]})
    return {'startup': first + 1 if first is not None else 0, 'active': last - first + 1 if first is not None else 0,
            'recovery': len(fr) - 1 - last if first is not None else len(fr), 'total': len(fr), 'hits': hits,
            'travel': -sum(s.get('dx', 0) for s in steps), 'frames': ''.join('x' if a else '-' for a in fr),
            'steps': [[t, int(a), int(n)] for t, a, n in sf]}


if __name__ == '__main__':
    # python3 routes.py FIGHTER                     its tree's node count and size
    # python3 routes.py encode TREE.json OUT.bin    a tree file (the Chain Lab's export) -> the blob the game reads
    import sys
    sys.path.insert(0, HERE); import export_bm
    if sys.argv[1] == 'encode':
        t = json.load(open(sys.argv[2])); t = t.get('tree', t)
        open(sys.argv[3], 'wb').write(encode(t, export_bm.MOVES)); sys.exit(0)
    t = load(sys.argv[1]); b = encode(t, export_bm.MOVES)
    print(sys.argv[1], b[3], 'nodes', len(b), 'bytes')
