#!/usr/bin/env python3
"""Chain routes: each fighter's chain-combo tree (Chain Lab, 2026-10-05).

A routes file (tools/brawler/routes/<fighter>.json, written by hand or by the Chain Lab page) is a tree of hits:

    {"fighter": "terry",
     "links": {"A": NODE, "B": NODE, "dB": NODE},            # the links from neutral (where a route starts)
     "entries": {"dash": NODE, "nospecial": NODE, "hold": NODE, "air_a": NODE, "air_b": NODE, "air_cd": NODE}}   # optional
    NODE = {"move": "atk_a_close",                           # one of the fighter's moves (MOVE_NAMES), or
            "special": "dD",                                 # a special (D, fD, dD, uD): a route ender, D inputs only
            "weight": "light" | "strong",                    # the victim's hit animation and hit stun (effect none)
            "effect": "none" | "knockdown" | "launch" | "trip" | "blowback",
            "keep": true,                                    # optional: keep the full animation on hit (it plays to its
                                                             # end, then the buffered input takes its link); left out (the
                                                             # default since 2026-10-05): on hit the next link starts as soon
                                                             # as its input comes, after the hit-stop
            "speed": 1.25,                                   # optional: playback speed, x KOF's timing (0.25-4; 1 left out),
                                                             # 8.8 fixed point in the game (rnode_t.speed)
            "damage": 3, "push": 3,                          # optional (advanced): default from weight / effect
            "links": {"A": NODE, "dfA": NODE, "D": NODE, ...}}
    inputs (INPUTS, the game's RI_* order): A B, dA dB (down), fA fB (forward), dfA dfB (down-forward), AB (A+B together),
    D fD dD uD (the specials). A link's input falls back in the game: down-forward -> forward -> down -> plain.

A fighter without a routes file gets default_tree(): the brawler's single table before the Chain Lab (fighter.c's
old COMBO), byte for byte the same behaviour. encode() turns a tree into the blob fighter.h describes (rt_head_t +
rnode_t[]), identical subtrees shared; the Chain Lab page has the same encoder in JavaScript (tools/brawler/chainlab/,
checked against this one by chainlab/check_encode.py)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTES_DIR = os.path.join(HERE, 'routes')
INPUTS = ['A', 'B', 'dA', 'dB', 'fA', 'fB', 'dfA', 'dfB', 'AB', 'D', 'fD', 'dD', 'uD']     # fighter.h RI_*
NORMAL_INPUTS, SPECIAL_INPUTS = INPUTS[:9], INPUTS[9:]
SPECIALS = ['D', 'fD', 'dD', 'uD']                                                       # BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D
MOVE_NAMES = ['atk_a_close', 'atk_a_far', 'atk_a_crouch', 'atk_b_close', 'atk_b_far', 'atk_b_crouch',
              'atk_c_close', 'atk_c_far', 'atk_c_crouch', 'atk_d_close', 'atk_d_far', 'atk_d_crouch', 'body_toss',
              'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d']                          # ground moves a route may play
AIR_MOVES = {'air_a': 'atk_c_jump', 'air_b': 'atk_d_jump', 'air_cd': 'atk_cd_jump'}     # the jump picks the animation
ENTRIES = ['dash', 'nospecial', 'hold', 'air_a', 'air_b', 'air_cd']
WEIGHTS = ['light', 'strong']
EFFECTS = ['none', 'knockdown', 'launch', 'trip', 'blowback']                            # fighter.h RE_*
RF_SPECIAL, RF_AIR, RF_KEEP = 1, 2, 4
NODE_SIZE, HEAD_SIZE, RI_N, MAX_NODES = 22, 16, 13, 128
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
    """fighter.c's COMBO before the Chain Lab, as a tree (shared nodes repeated; encode() shares them again)"""
    def n(move, dmg, w, eff, push, **links):
        return {'move': move, 'weight': w, 'effect': eff, 'damage': dmg, 'push': push,
                'links': {**links, **{k: {'special': k} for k in SPECIALS}}}   # any D: the special its input picks
    toss = lambda: n('body_toss', 10, 'strong', 'knockdown', 0)
    sweep = lambda: n('atk_d_crouch', 7, 'strong', 'trip', 0)
    fin = lambda: {'fA': toss(), 'dB': sweep()}                                        # finishers inside any window
    a5 = toss()
    a4 = n('atk_d_close', 6, 'strong', 'none', 4, A=a5, **fin())
    a3 = n('atk_c_close', 6, 'strong', 'none', 4, A=a4, **fin())
    aab = n('atk_d_far', 9, 'strong', 'launch', 0)
    a2 = n('atk_a_far', 3, 'light', 'none', 3, A=a3, B=aab, **fin())
    ab = n('atk_d_close', 6, 'strong', 'none', 6, **fin())
    a1 = n('atk_a_far', 3, 'light', 'none', 3, A=a2, B=ab, **fin())
    bb = n('atk_d_close', 8, 'strong', 'knockdown', 0)
    ba = n('atk_c_far', 5, 'strong', 'none', 5, B=sweep(), **fin())
    b1 = n('atk_b_close', 4, 'light', 'none', 3, A=ba, B=bb, **fin())
    air = lambda m, dmg, w, eff, push: {'move': m, 'weight': w, 'effect': eff, 'damage': dmg, 'push': push, 'links': {}}
    return {'fighter': None, 'links': {'A': a1, 'B': b1, 'dB': sweep()},
            'entries': {'dash': toss(), 'nospecial': toss(), 'hold': toss(),
                        'air_a': air('atk_c_jump', 6, 'strong', 'none', 4), 'air_b': air('atk_d_jump', 8, 'strong', 'knockdown', 0),
                        'air_cd': air('atk_cd_jump', 10, 'strong', 'knockdown', 0)}}


def load(name, path=None):
    """the fighter's tree: its routes file (game.json roster[].routes; entries it leaves out: the default's), else
    (path None) the default tree"""
    p = path
    d = default_tree()
    if p is None: return dict(d, fighter=name)
    t = json.load(open(p))
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
            assert k in INPUTS, f'{where}: unknown input {k}'
            if k in SPECIAL_INPUTS: assert 'special' in ch, f'{where} {k}: a D input leads to a special'
            else: assert 'move' in ch, f'{where} {k}: an A / B input leads to a move'
            nxt[INPUTS.index(k)] = node(ch, f'{where} {k}')
        if 'special' in nd:
            assert nd['special'] in SPECIALS, f'{where}: unknown special {nd["special"]}'
            assert not nd.get('links'), f'{where}: a special ends the route (no links)'
            anim, flags = SPECIALS.index(nd['special']), RF_SPECIAL
        elif nd.get('move') is None: anim, flags = 0, 0                                # the root
        else:
            m = nd['move']
            assert m in moves, f'{where}: unknown move {m}'
            assert air or m in MOVE_NAMES, f'{where}: {m} is not a ground move'
            assert has is None or m in has, f'{where}: the fighter has no {m}'
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
    ent = [node(dict((tree.get('entries') or {}).get(k) or d[k], move=AIR_MOVES[k]) if k in AIR_MOVES else (tree.get('entries') or {}).get(k) or d[k],
                k, air=k in AIR_MOVES) for k in ENTRIES]
    assert len(nodes) <= MAX_NODES, f'{len(nodes)} nodes (at most {MAX_NODES})'
    head = b'RT' + bytes([2, len(nodes), root] + ent + [0] * 5)
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
