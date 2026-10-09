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
            "sound": "heavy",                                # optional: its hits sound as a heavy normal's (RF_HEAVY_SFX), or
            "sound": ["11", "13"],                           # its hits' own sound commands in order (hex; Kim's picks on the
                                                             # Lab sounds page, 2026-10-09), per move in the fighter's ROM
                                                             # data (hit_sounds -> export_bm bm_hsnd, fighter.c own_sound);
                                                             # a hit past the list sounds by the engine's rule
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
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTES_DIR = os.path.join(HERE, 'routes')
NORMAL_INPUTS = ['A', 'B', 'dA', 'cA', 'fA', 'bA', 'dfA']                               # fighter.h RI_A .. RI_DFA
SPECIAL_INPUTS = ['AB', 'fAB', 'dAB', 'uAB', 'dfAB', 'ufAB']                             # RI_S .. RI_UFS
INPUTS = NORMAL_INPUTS + ['uA', None] + SPECIAL_INPUTS                                  # fighter.h RI_* (slot 7: up+A, revamp 1A,
                                                                                         # the chain's up finisher; slot 8 unused)
RI_THEN = 8                                                                              # fighter.h RI_THEN: a node's 'then' (Kim
                                                                                         # gold: a finisher of several moves played
                                                                                         # back to back, rnode_t.next[RI_THEN])
SPECIALS = ['D', 'fD', 'dD', 'uD', 'dfD', 'ufD']                                         # BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_DF_D, BS_UF_D
SLOT_OF = dict(zip(SPECIAL_INPUTS, SPECIALS))                                            # a C input -> the slot it plays
MOVE_NAMES = ['atk_a_close', 'atk_a_far', 'atk_a_crouch', 'atk_b_close', 'atk_b_far', 'atk_b_crouch',
              'atk_c_close', 'atk_c_far', 'atk_c_crouch', 'atk_d_close', 'atk_d_far', 'atk_d_crouch', 'body_toss',
              'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d',                          # ground moves a route may play
              # World Heroes Perfect's six buttons (tools/whp/moves_whp.py; docs/brawler_data_model.md): the strong
              # punch A+B / strong kick C+D, forward + C / C+D, the running normals
              'atk_ab_close', 'atk_ab_far', 'atk_ab_crouch', 'atk_cd_close', 'atk_cd_crouch', 'cmd_fwd_c', 'cmd_fwd_cd',
              'atk_a_run', 'atk_b_run', 'atk_ab_run', 'atk_c_run', 'atk_d_run', 'atk_cd_run',
              'atk_a_run_low', 'atk_b_run_low', 'atk_ab_run_low', 'atk_c_run_low', 'atk_d_run_low', 'atk_cd_run_low']
AIR_MOVES = {'air_a': 'atk_c_jump', 'air_b': 'atk_d_jump', 'air_cd': 'atk_cd_jump'}     # the jump picks the animation
AIR_MOVE_NAMES = list(AIR_MOVES.values()) + ['atk_a_jump', 'atk_b_jump', 'atk_ab_jump']  # an air node's moves (B links, air
                                                 # links); the jump picks the vertical / diagonal one (fighter.c start_node)
ENTRIES = ['dash', 'nospecial', 'hold', 'air_a', 'air_b', 'air_cd']
WEIGHTS = ['light', 'strong']
EFFECTS = ['none', 'knockdown', 'launch', 'trip', 'blowback', 'slam']                    # fighter.h RE_* (slam: revamp 1A)
RF_SPECIAL, RF_AIR, RF_KEEP, RF_THROW, RF_HEAVY_SFX = 1, 2, 4, 8, 16   # (RF_HEAVY_SFX, Kim queue 2026-10-09: "sound": "heavy", its hits sound as a heavy normal's)
ARCHETYPES = ['fast', 'balanced', 'heavy']                                               # rt_head_t.arch - 1 (revamp 1A)
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
    if e != 'none': return {'knockdown': 8, 'launch': 9, 'trip': 7, 'blowback': 10, 'slam': 9}[e], 0
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
HIT_FIELDS = ('move', 'special', 'weight', 'effect', 'keep', 'speed', 'damage', 'push', 'throw', 'hitstop', 'sound')   # (throw, hitstop: a chain tree's nodes)


def hit_of(nd):
    """a node's hit as the game plays it (defaults applied): what decides whether two routes' steps are the same hit"""
    if 'special' in nd: return {'special': nd['special'], 'speed': speed_fx(nd)}
    dd, dp = default_damage(nd)
    return {'move': nd.get('move'), 'weight': nd.get('weight', 'light'), 'effect': nd.get('effect', 'none'),
            'keep': bool(nd.get('keep')), 'speed': speed_fx(nd), 'damage': nd.get('damage', dd), 'push': nd.get('push', dp),
            'sound': nd.get('sound')}


def sound_codes(nd):
    """a node's per-hit sound list ("sound": [hex codes]) as ints, else None ("heavy" or none: the flag / the rule)"""
    v = nd.get('sound')
    if not isinstance(v, list): return None
    out = [int(str(c).lstrip('$'), 16) for c in v]
    assert out and len(out) <= 8 and all(0 < c < 0x100 for c in out), f'{nd.get("move")}: sound {v}: 1-8 hex codes $01-$FF'
    return out


def hit_sounds(tree):
    """{move: [codes]}: the per-hit sound lists of a tree's nodes (links, 'then' chains, entries); a move given two
    different lists is refused (the game keys them by move: export_bm bm_hsnd)"""
    out = {}
    def walk(nd):
        c = sound_codes(nd) if 'move' in nd else None
        if c is not None:
            assert out.setdefault(nd['move'], c) == c, f'{nd["move"]}: two sound lists {out[nd["move"]]} / {c}'
        for ch in (nd.get('links') or {}).values(): walk(ch)
        if nd.get('then'): walk(nd['then'])
    walk({'links': tree.get('links') or {}})
    for e in (tree.get('entries') or {}).values():
        if e: walk(e)
    return out


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
            elif 'special' in ch:                                            # a special on a stick+A link: the chain's
                assert not air, f'{where} {k}: no special in the air'        # special finisher (revamp gold), played free
                                                                             # by fighter.c route_go (node_special)
            else: assert 'move' in ch, f'{where} {k}: an A / B input leads to a move (a back throw: "throw" + its shown move)'
            assert not (air and k == 'B'), f'{where}: no jump-cancel in the air'
            assert not (where == 'root' and (k == 'B' or k in SPECIAL_INPUTS)), f'root {k}: a route starts with an A'
            nxt[INPUTS.index(k)] = node(ch, f'{where} {k}', air or k == 'B')   # B: a jump-cancel, its node in the air
        if nd.get('then'):                                                   # (Kim gold) the move played as this one
            assert 'move' in nd and 'move' in nd['then'], f'{where}: then: moves only'   # ends, whatever happened
            nxt[RI_THEN] = node(nd['then'], f'{where} then', air)
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
            anim, flags = moves.index(m), (RF_AIR if air else 0) | (RF_KEEP if nd.get('keep') else 0) | (RF_HEAVY_SFX if nd.get('sound') == 'heavy' else 0)
            if nd.get('throw'):                                                         # the chain's back throw (revamp 1A)
                assert not air and not nd.get('links'), f'{where}: a throw ends a ground chain'
                flags |= RF_THROW
        w, e = nd.get('weight', 'light'), nd.get('effect', 'none')
        assert w in WEIGHTS and e in EFFECTS, f'{where}: weight {w} / effect {e}'
        dd, dp = default_damage(nd)
        dmg, push = nd.get('damage', dd), nd.get('push', dp)
        assert 0 <= dmg <= 255 and -128 <= push <= 127, where
        sp = speed_fx(nd)
        hs = nd.get('hitstop', 0)                                                       # 0 = the engine's HITSTOP
        assert 0 <= hs <= 60, f'{where}: hitstop {hs}'
        nodes[i] = bytes([anim, flags, WEIGHTS.index(w), EFFECTS.index(e), dmg, push & 0xFF, sp >> 8, sp & 0xFF] + nxt + [hs])
        return i
    root = node({'links': tree.get('links', {})}, 'root')
    d = default_tree()['entries']
    ent = [node((tree.get('entries') or {}).get(k) or d[k], k, air=k in AIR_MOVES) for k in ENTRIES]   # an air entry: its own
                                                         # move (air_a's default air C; any of the three)
    assert len(nodes) <= MAX_NODES, f'{len(nodes)} nodes (at most {MAX_NODES})'
    arch = ARCHETYPES.index(tree['archetype']) + 1 if tree.get('archetype') else 0
    head = b'RT' + bytes([TREE_VERSION, len(nodes), root] + ent + [arch, tree.get('chain_links', 0)] + [0] * 3)
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



# ---- the chain core's default chains (revamp 1A, docs/brawler_feel.md 8h; docs/brawler_data_model.md "Chains") ---------
# Every roster fighter plays ONE standard chain built from its existing pieces (its routes file or the default tree):
# length by archetype, damage scaled to the archetype's total, hit-stop on one scale, finishers by direction. The
# generator, chain_tree(), in order:
#  1. pieces: the base tree's ground move nodes (breadth first from the root, B / jump-cancel and special nodes left out);
#     the main line = the plain-A path from the root's A or close-A link with the most no-effect pieces (A on a tie).
#  2. builders (links 1 .. N-1): the main line's no-effect pieces, the first N-1 (fast / balanced: from the jab) or the
#     last N-1 (heavy: the strong end); short of them, the other no-effect pieces breadth first, then the last again.
#  3. finishers (link N, by the stick): neutral = the line's first knockdown / blowback / trip piece after the builders,
#     else the tree's first, else close D / far C (knockdown); the launcher = the tree's first launch piece, else far D,
#     else the neutral's move, put where finishers.launcher says (up default; forward or neutral); forward = the launcher
#     there, else the tree's first blowback piece, else the body toss (blowback); down = finishers.down: "sweep" the
#     tree's trip piece, else crouch D (trip), "slam" a strong close normal (close D, close C, close C+D, far C) with the
#     slam effect, null none; back = the fighter's back throw (RF_THROW, shown as the neutral's move). Every finisher may
#     be named instead (finishers.neutral / forward / up / down = a move). A missing one falls back to neutral (the game).
#  4. damage: the pieces' own damage (their weight's default) as weights, scaled to the archetype's total for the whole
#     chain (largest remainder, each at least 1); every finisher deals the neutral's share. The jump-cancel, dash, C
#     without a special and air entries keep their own damage times the fighter's `damage` scale (it no longer applies
#     to normals in the game); the hold's finisher its own.
#  5. hit-stop: link k of N = lo + (hi - lo) (k - 1) / (N - 1) rounded (6, 8, 10, 12 for 4 links), every finisher hi; the
#     other nodes by class: light lo, strong (lo + hi) / 2, an effect hi.
#  6. links: each builder A -> the next (the stick ignored: the fallback), B -> the base tree's jump-cancel (the default's
#     air C, then A air C+D), the six C inputs -> the slots' specials; the last builder's A / fA / uA / dA / bA -> the
#     finishers. The root: A -> link 1 (any stick, close or far).


def _ground_pieces(tree):
    """the tree's ground move nodes, breadth first from the root: (inputs from the root, node)"""
    out, q = [], [([k], nd) for k, nd in (tree.get('links') or {}).items()]
    while q:
        p, nd = q.pop(0)
        if 'move' not in nd or p[-1] == 'B' or p[-1] in SPECIAL_INPUTS: continue
        out.append((p, nd))
        q += [(p + [k], c) for k, c in (nd.get('links') or {}).items()]
    return out


def _b_node(tree):
    """the tree's first jump-cancel node (a B link), breadth first"""
    q = list((tree.get('links') or {}).values())
    while q:
        nd = q.pop(0)
        if 'B' in (nd.get('links') or {}): return nd['links']['B']
        q += [c for k, c in (nd.get('links') or {}).items() if k != 'B' and 'move' in c]
    return None


def _dmg(nd): return hit_of(nd)['damage']


def _scale(weights, total):
    """integers proportional to weights summing to total (largest remainder), each at least 1"""
    tw = sum(weights); raw = [w * total / tw for w in weights]; out = [max(1, int(x)) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: (-round(raw[i] - int(raw[i]), 6), -i))   # (ties: the later link)
    k = 0
    while sum(out) < total: out[order[k % len(out)]] += 1; k += 1
    while sum(out) > total: i = max(range(len(out)), key=lambda i: out[i]); out[i] -= 1
    return out


STRONG_BUTTONS = ('c', 'd', 'ab', 'cd')


def piece_weight(m):
    """a move's hit weight when no tree gives it one (pieces.py's rule): strong for C / D / A+B / C+D and the body toss"""
    b = re.match(r'(?:atk|cmd)_(?:fwd_|df_)?([a-d]+)', m)
    return 'strong' if m == 'body_toss' or (b and b.group(1) in STRONG_BUTTONS) else 'light'


def _main_line(base, ok):
    """the chain generator's main line: the plain-A path from the root's A or close-A link with the most no-effect pieces"""
    noeff = lambda nd: nd.get('effect', 'none') == 'none'
    lines = []
    for k in ('A', 'cA'):
        nd = (base.get('links') or {}).get(k); line = []
        while nd and 'move' in nd and ok(nd['move']):
            line.append(nd); nd = (nd.get('links') or {}).get('A')
        if line: lines.append(line)
    return max(lines, key=lambda l: sum(map(noeff, l))) if lines else []


def chain_base(base, has):
    """per move the node a link named by the chain tool takes (game.json roster[].chain.links; build/chainlab.json
    fighters[].chain_base, the Lab assembles chains with the same table): the main line's node of that move, else the
    base tree's first ground node playing it (breadth first), so a named link is the piece the generator would take;
    its weight, speed, push and damage (the damage = its weight in the chain's damage scaling)"""
    ok = lambda m: m in has
    out = {}
    for nd in _main_line(base, ok) + [nd for _, nd in _ground_pieces(base)]:
        if ok(nd['move']) and nd['move'] not in out:
            out[nd['move']] = {k: nd[k] for k in ('move', 'weight', 'effect', 'speed', 'push', 'damage', 'sound') if k in nd}
    return out


def chain_piece(m, table, has, name):
    """a named link (chain_base's table): that node with no effect, else the move with piece_weight"""
    assert m in MOVE_NAMES and m in has, f'{name}: chain.links: {m}: not a ground move the fighter has'
    out = dict(table[m]) if m in table else {'move': m, 'weight': piece_weight(m)}
    out['effect'] = 'none'
    return out


def _then(nd):
    out = [nd]
    while out[-1].get('then'): out.append(out[-1]['then'])
    return out


def chain_tree(name, base, cfg, has):
    """the chain the game plays (see above): base = the fighter's tree (load()), cfg = build_tables.chain_cfg's entry
    {archetype, length, total, hitstop [lo, hi], finishers {launcher, down, neutral?, forward?, up?, down_move?}, damage},
    has = the moves it has. Returns a tree for encode() (with 'archetype', 'chain_links' and a 'chain' summary)"""
    if not cfg: return base
    N, total, (lo, hi) = cfg['length'], cfg['total'], cfg['hitstop']
    fin = cfg.get('finishers') or {}
    mul = cfg.get('damage', 1)
    ok = lambda m: m in has
    pieces = [(p, nd) for p, nd in _ground_pieces(base) if ok(nd['move'])]
    clean = lambda nd: {k: nd[k] for k in ('move', 'weight', 'effect', 'speed', 'push', 'damage', 'sound') if k in nd}
    noeff = lambda nd: nd.get('effect', 'none') == 'none'
    main = _main_line(base, ok)
    pool = [nd for nd in main if noeff(nd)]
    if cfg['archetype'] == 'heavy': pool = pool[-(N - 1):] if len(pool) > N - 1 else pool
    builders = [clean(nd) for nd in pool[:N - 1]]
    if cfg.get('links') is not None:                                # (revamp 5, the chain tool) game.json roster[].chain.links
        assert len(cfg['links']) == N - 1, f"{name}: chain.links: {len(cfg['links'])} links, the {cfg['archetype']} chain has {N - 1} before its finisher"
        builders = [chain_piece(m, chain_base(base, has), has, name) for m in cfg['links']]
    used = {b['move'] for b in builders}
    for _, nd in pieces:
        if len(builders) >= N - 1: break
        if noeff(nd) and nd['move'] not in used: builders.append(clean(nd)); used.add(nd['move'])
    while len(builders) < N - 1: builders.append(dict(builders[-1]) if builders else {'move': 'atk_a_far', 'weight': 'light', 'effect': 'none'})
    for b in builders: b['effect'] = 'none'

    allp = [nd for _, nd in pieces]
    def first(pred, src, avoid=()):
        return next((clean(nd) for nd in src if pred(nd) and nd['move'] not in avoid), None)
    tool = chain_base(base, has) if cfg.get('links') is not None else None   # a chain tool's chain: its finishers too
    sp_in = {i: s for s, i in (cfg.get('specials') or {}).items() if i}      # a special input -> its slot (D .. ufD)
    def spec_slot(m):                                                        # a finisher named as a special (its input or
        return m if m in SPECIALS else sp_in.get(m)                          # its slot) -> the slot, else None
    def named(m, eff, w='strong'):                                  # take the piece its links would (chain_base)
        if isinstance(m, list):                                     # (Kim gold) several moves played back to back: the
            assert m, f'{name}: an empty finisher list'               # head and its 'then' chain, the effect on the last
            nd = named(m[-1], eff, w)
            for x in reversed(m[:-1]): nd = dict(named(x, 'none', w), then=nd)
            return nd
        sl = spec_slot(m)
        if sl: return {'special': sl, 'effect': eff, 'weight': w}           # a special played as the finisher (free, like
                                                                             # the built-in ones: fighter.c route_go)
        assert m in has, f'{name}: chain finisher {m}: the fighter has no such move'
        if tool is not None and m in tool: return dict(tool[m], effect=eff)
        return {'move': m, 'weight': w, 'effect': eff}
    def last(nd):                                                   # the last move of a 'then' chain
        while nd.get('then'): nd = nd['then']
        return nd
    def cand(ms, eff, avoid=()):                                    # the first of these moves it has (not in avoid)
        return next((named(m, eff) for m in ms if ok(m) and m not in avoid), None)
    by = lambda e: (lambda nd: nd.get('effect') == e)
    where = fin.get('launcher', 'up')
    assert where in ('up', 'forward', 'neutral', None), f'{name}: finishers.launcher {where}'
    # neutral: the line's next piece after the builders (no effect or a knockdown: made a knockdown), else the tree's
    # first knockdown / blowback / trip piece (the line's after the builders first), else a strong normal
    nxt_line = main[main.index(pool[min(len(pool), N - 1) - 1]) + 1:] if pool and cfg['archetype'] != 'heavy' else \
        main[main.index(pool[-1]) + 1:] if pool else main
    nl = nxt_line[0] if nxt_line else None
    if fin.get('neutral'): neutral = named(fin['neutral'], 'knockdown')
    elif nl is not None and nl.get('effect', 'none') in ('none', 'knockdown'): neutral = dict(clean(nl), effect='knockdown')
    else:
        neutral = next((r for src in (nxt_line, allp) for e in ('knockdown', 'blowback', 'trip') for r in [first(by(e), src)] if r), None) or \
            cand(('atk_d_close', 'atk_c_far', 'atk_c_close', 'atk_b_far'), 'knockdown') or dict(builders[-1], effect='knockdown')
    # the launcher: named, else the tree's first launch piece, else far D / down-forward C / D, far C (not the neutral's
    # move when another exists), else the neutral's move
    lname = fin.get(where) if where in ('up', 'forward') else None
    launch = named(lname, 'launch') if lname else \
        first(by('launch'), allp, (neutral['move'],)) or cand(('atk_d_far', 'cmd_df_c', 'cmd_df_d', 'atk_c_far'), 'launch', (neutral['move'],)) or \
        first(by('launch'), allp) or dict(neutral, effect='launch')
    launch['effect'] = 'launch'
    if where == 'neutral': neutral = launch
    # forward: the launcher there, else a push: the tree's first blowback piece, else the body toss, forward + A / B, far
    # C / B (blowback), never the neutral's move when another exists
    if where == 'forward': forward = launch
    elif fin.get('forward'): forward = named(fin['forward'], 'blowback')
    else:
        forward = first(by('blowback'), allp, (neutral['move'],)) or \
            cand(('body_toss', 'cmd_fwd_a', 'cmd_fwd_b', 'atk_c_far', 'atk_b_far'), 'blowback', (neutral['move'],)) or dict(neutral, effect='blowback')
        forward['effect'] = 'blowback'
    up = launch if where == 'up' else (named(fin['up'], 'knockdown') if fin.get('up') else None)
    # down: a sweep (the tree's trip piece, else crouch D) or a slam (a strong close normal the chain does not play yet)
    dk = fin.get('down', 'sweep')
    assert dk in ('sweep', 'slam', None), f'{name}: finishers.down {dk}'
    usedm = {x['move'] for x in builders} | {neutral['move'], forward['move']}
    if fin.get('down_move'): down = named(fin['down_move'], 'trip' if dk == 'sweep' else 'slam')
    elif dk == 'sweep': down = first(by('trip'), allp) or cand(('atk_d_crouch', 'atk_c_crouch'), 'trip')
    elif dk == 'slam':
        sl = ('atk_d_close', 'atk_c_close', 'atk_cd_close', 'atk_c_far', 'atk_d_far')
        down = cand(sl, 'slam', usedm) or cand(sl, 'slam')
    else: down = None
    if down: last(down)['effect'] = 'trip' if dk == 'sweep' else 'slam'

    dm = _scale([_dmg(b) for b in builders] + [_dmg(neutral)], total)
    hs = [lo + ((hi - lo) * k * 2 + (N - 1)) // (2 * (N - 1)) for k in range(N)] if N > 1 else [hi]
    if cfg.get('hitstops') is not None:                             # (revamp 5) game.json roster[].chain.hitstop: per link, the finisher last
        hs = list(cfg['hitstops'])
        assert len(hs) == N and all(isinstance(v, int) and 1 <= v <= 60 for v in hs), f'{name}: chain.hitstop {hs}: {N} values, 1-60 frames'
    for k, b in enumerate(builders): b['damage'] = dm[k]; b['hitstop'] = hs[k]
    finals = {'A': neutral, 'fA': forward, 'uA': up, 'dA': down}
    for k, f in list(finals.items()):
        if f is None: del finals[k]; continue
        finals[k] = dict(f, damage=dm[-1], hitstop=hs[-1])
        finals[k].setdefault('weight', 'strong')
        if f.get('then'):                                           # (Kim gold) a finisher of several moves: its damage
            seq = [finals[k]]                                       # shared by them (the first ones floor, the last the rest)
            while seq[-1].get('then'): seq[-1]['then'] = dict(seq[-1]['then']); seq.append(seq[-1]['then'])
            for j, x in enumerate(seq):
                x['damage'] = dm[-1] // len(seq) if j < len(seq) - 1 else dm[-1] - dm[-1] // len(seq) * (len(seq) - 1)
                x['hitstop'] = hs[-1]; x.setdefault('weight', 'strong')
    finals['bA'] = {'move': neutral['move'], 'throw': 'back', 'weight': 'strong', 'effect': 'knockdown', 'damage': 0, 'hitstop': hs[-1]}
    spl = lambda: {k: {'special': SLOT_OF[k]} for k in SPECIAL_INPUTS}
    def cls(nd, scale):                                              # an entry / jump-cancel: its own damage x the scale,
        nd = json.loads(json.dumps(nd))                              # hit-stop by class
        def walk(x):
            if 'move' in x:
                if scale: x['damage'] = min(255, _dmg(x) * mul)
                x['hitstop'] = hi if x.get('effect', 'none') != 'none' else (lo + hi) // 2 if x.get('weight') == 'strong' else lo
            for c in (x.get('links') or {}).values(): walk(c)
        walk(nd); return nd
    for f in finals.values():
        while f is not None:                                       # (each move of a 'then' chain: the C cancels)
            if 'throw' not in f and 'special' not in f: f['links'] = spl()
            f = f.get('then')   # (a special finisher ends the route: no links)
    nxt = finals
    for k in range(N - 2, -1, -1):
        nd = dict(builders[k], links={**({'A': nxt} if k < N - 2 else nxt), **spl()})   # (no B link: the jump-cancel is
                                                                     # gone, Bruno 2026-10-08: three air attacks only, the chain
                                                                     # always starts on the ground at link 1)
        nxt = nd
    ent = base.get('entries') or {}
    entries = {k: cls(v, k != 'hold') for k, v in ent.items()}
    air = cfg.get('air')                                            # the three air attacks (Bruno 2026-10-08; gamedata.h gjump_t):
    if air:                                                         # air_a = straight jump + A, air_cd = forward jump + A (both
        for k, m, w, e in (('air_a', air['straight'], 'strong', 'knockdown'),   # knock down), air_b = down + A in either
                           ('air_cd', air['forward'], 'strong', 'knockdown'),   # jump (a flinch; fighter.c holds it active
                           ('air_b', air['down'], 'light', 'none')):            # to the landing)
            assert m in AIR_MOVE_NAMES, f'{name}: air {k}: {m} is not an air move ({" ".join(AIR_MOVE_NAMES)})'
            entries[k] = cls({'move': m, 'weight': w, 'effect': e}, True)
    summary = {'archetype': cfg['archetype'], 'length': N, 'total': total,
               'links': [b['move'] for b in builders], 'damage': dm, 'hitstop': hs,
               'finishers': {{'A': 'neutral', 'fA': 'forward', 'uA': 'up', 'dA': 'down', 'bA': 'back'}[k]:
                             ('throw' if 'throw' in f else ('special ' + f['special'] if 'special' in f else ' > '.join(x['move'] for x in _then(f))) + ' (' + _then(f)[-1]['effect'] + ')') for k, f in finals.items()}}
    return {'fighter': name, 'links': {'A': nxt}, 'entries': entries, 'archetype': cfg['archetype'], 'chain_links': N, 'chain': summary}

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
