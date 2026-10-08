#!/usr/bin/env python3
"""Revamp phase 1A proof: the chain core (fighter.c "chain core", routes.py chain_tree, game.json "chain"), in the Chain
Lab's training mode (labdrive: P1 = the fighter, a dummy that never attacks unless this script drives it), our emulator's
core (harness). Test-only pokes: the fighters' positions, the dummy's life (set full before a chain), the dummy's intent
for the presses that hit P1, a copy of the dummy as a second enemy (scenario.py's `extra`), and in the juggle-cap test the
juggled dummy's height held (y, vy) so the jabs keep reaching it.

    python3 chain_proof.py OUT_DIR [SECTION ...]     -> OUT_DIR/chain1a.json + sheets (sheet_*.png)

Sections (all by default):
  roster     every roster fighter: mashed A at close range = its archetype's links (fast 5, balanced 4, heavy 3), each
             link's damage and hit-stop = the tree's (routes.py chain_tree), the chain total = the archetype's
  whiff      a whiff restarts the chain at link 1 (from neutral, and a link that whiffs mid-chain); being hit restarts it
  window     link 1 hits, the press D frames after its recovery: link 2 up to the window (game.json chain.window), link 1
             after
  buffer     a press in the hit-stop is latched (the next link on the first frame after it); a press k frames before a
             whiffing link ends restarts link 1 at once for k <= chain.buffer, not beyond; a press k frames before link
             1's hit: link 2 after the hit-stop for k <= chain.buffer, nothing beyond
  finishers  Terry / Kim / Krauser: the last link with the stick neutral / forward / up / down / back = the tree's
             finisher (its move, the victim's reaction); back = the back throw (P1 untouchable through it, the victim
             thrown behind, a second enemy behind knocked down by the body, no chain after it); the fallbacks:
             Haohmaru (no throw) back = neutral, a tree without up / down links: up / down = neutral
  juggle     at most chain.juggle_cap air hits, then untouchable until it lands, hittable again once it stands; a downed
             fighter (its knockdown touched the floor) is never hit
  hitstop    the scale per link (roster) + a special's hit (the engine's 7)
  stun       an enemy's hit stun (light / heavy) and a player's (stun_player) + its untouchable window (guard_player):
             a second enemy cannot hit it meanwhile, the one that hit it can; after it, anyone"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import routes as RT, export_bm
from labdrive import Lab
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
SECTIONS = sys.argv[2:] or ['roster', 'whiff', 'window', 'buffer', 'finishers', 'juggle', 'hitstop', 'stun']
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json'))); CH = G['chain']
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
MOVES = export_bm.MOVES
names = [r['name'] for r in G['roster']]
L = Lab(); b = L.b; ST = b.states
INV_FURY = 0xFF

def throws_built():
    src = open(os.path.join(GAME, 'build', 'bm_chars.c')).read(); out = {}
    for n in names:
        m = re.search(r'static const bthrow_t %s_throws\[BT_COUNT\] = \{\{(.*?)\}, \{(.*?)\}\};' % n, src)
        ts = []
        for g in (m.group(1), m.group(2)) if m else ():
            f = [x.strip() for x in g.split(',')]
            nrows = int(f[0], 0); rows = f[2]; rel = int(f[4], 0); stun = int(f[12], 0) if len(f) > 12 else 0
            end = None
            if nrows and rows != '0':
                rm = re.search(r'static const bthrow_row_t %s\[[^]]*\] = \{(.*?)\};' % rows, src, re.S)
                last = re.findall(r'\{([^{}]*)\}', rm.group(1))[nrows - 1].split(',')
                end = int(last[1], 0) + int(last[5], 0)            # tx + vx of the last row (< 0: behind the thrower)
            ts.append({'nrows': nrows, 'rel': rel, 'stun': stun, 'end_dx': end})
        out[n] = ts
    return out
THROWS = throws_built()
def back_throw(n):
    """fighter.c cthrow_pick: (throw index, mirrored) or None"""
    first = None
    for t in (1, 0):
        th = THROWS[n][t]
        if not th['nrows'] or th['stun']: continue
        if first is None: first = t
        if th['end_dx'] is not None and th['end_dx'] < 0: return t, False
    return (first, True) if first is not None else None
def st(i=0): return ST[b.fget(i, 'state')]
def mv(i=0): return MOVES[b.fget(i, 'anim')]
def run(n=1, k=''): b.run(n, p1=k)
def tree_of(fi): return CL['fighters'][fi]['tree']
def blob_of(fi, tree=None): return RT.encode(tree or tree_of(fi), CL['ba'], set(CL['fighters'][fi]['has']))
def nodes_of(fi, tree=None):
    """node index -> the node dict, as encode() numbers them (the same memo walk)"""
    tree = tree or tree_of(fi); blob = blob_of(fi, tree)
    out = {}
    def nd_bytes(i): o = 16 + i * 24; return blob[o:o + 24]
    def walk(i, nd):
        if i in out: return
        out[i] = nd
        nb = nd_bytes(i)
        for k, ch in (nd.get('links') or {}).items():
            j = nb[8 + RT.INPUTS.index(k)]
            if j: walk(j, ch)
    root = blob[4]
    walk(root, {'links': tree['links']})
    return out
def start(fi, dummy=None, tree=None):
    L.start(fi, (1 if fi == 0 else 0) if dummy is None else dummy, list(tree) if tree is not None else None); run(30)
def settle():
    for _ in range(600):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'chain_t') and not b.fget(0, 'freeze'): break
        run(1)
    else: raise RuntimeError('never idle: ' + b.brief((0, 2)))
def setpos(dist, dz=0, hp=60):
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30 + dz); b.fset(0, 'facing', 1); b.fset(2, 'facing', -1 & 0xFF)
    b.fset(2, 'hp', hp); run(2)
def shot(name): p = os.path.join(OUT, name + '.png'); b.screenshot(p); return p

def mash(N, last='', gap=6, limit=320, dist=30, after=None, setp=True):
    """A pressed every `gap` frames (2 frames held) until link N (the finisher) starts, `last` held from the moment
    link N-1 plays (the finisher's stick); then no input until P1 is idle again. -> (links [{node, move, state, hits
    [(damage, P1 freeze)], t}], damage dealt). after(t, links): called every frame (pokes, pictures)"""
    if setp: setpos(dist)
    h0 = b.fget(2, 'hp'); links = []; t = 0; prev_node = None; prev_state = None; done_t = None
    while t < limit:
        k = ''
        if len(links) < N:
            k = (last if len(links) == N - 1 else '') + ('a' if t % gap < 2 else '')
        hp0 = b.fget(2, 'hp'); run(1, k); t += 1
        s_, nd = st(0), b.fget(0, 'node')
        if (s_ == 'ATTACK' and (prev_state != 'ATTACK' or nd != prev_node)) or (s_ == 'THROW' and prev_state != 'THROW'):
            links.append({'node': nd if s_ == 'ATTACK' else None, 'move': mv(0) if s_ == 'ATTACK' else 'throw', 'state': s_, 'hits': [], 't': t})
        hp1 = b.fget(2, 'hp')
        if hp1 < hp0 and links: links[-1]['hits'].append((hp0 - hp1, b.fget(0, 'freeze')))
        if after and after(t, links): break
        prev_state, prev_node = s_, nd
        if len(links) >= N and s_ in ('IDLE', 'WALK') and not b.fget(0, 'freeze'):
            if done_t is None: done_t = t
            if t - done_t > 2: break
        if len(links) < N and t > 40 and s_ in ('IDLE', 'WALK') and not b.fget(0, 'chain_t') and not b.fget(0, 'freeze'): break   # the chain broke
    return links, h0 - b.fget(2, 'hp')

res = {}
def save(): json.dump(res, open(os.path.join(OUT, 'chain1a.json'), 'w'), indent=1)
def text_sheet(name, lines):
    W = 1400; H = 16 * len(lines) + 20
    im = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(im)
    for i, l in enumerate(lines): d.text((8, 8 + 16 * i), l, fill='black')
    im.save(os.path.join(OUT, f'sheet_{name}.png'))

# ---- roster: length, damage, hit-stop ------------------------------------------------------------------------------
if 'roster' in SECTIONS or 'hitstop' in SECTIONS:
    R = res['roster'] = {}; lines = ['ROSTER: mashed A at close range (dummy Ryo; Terry for Ryo): links played, damage per link, hit-stop per link']
    for fi, n in enumerate(names):
        t = tree_of(fi); c = t['chain']; N = c['length']
        start(fi)
        best = None
        for dist in (30, 40, 22, 50, 60, 16):
            settle(); hp0 = b.fget(2, 'hp'); links, _ = mash(N, dist=dist)
            dmg = [sum(h[0] for h in l['hits']) for l in links]
            score = (len([l for l in links if l['hits']]), dmg == c['damage'])
            if best is None or score > best[0]: best = (score, dist, links, sum(dmg))
            if score == (N, True): break
        _, dist, links, total = best
        dmg = [sum(h[0] for h in l['hits']) for l in links]; hs = [l['hits'][0][1] if l['hits'] else None for l in links]
        ok = len(links) == N and all(l['hits'] for l in links) and dmg == c['damage'] and total == c['total'] and hs == c['hitstop']
        R[n] = {'archetype': c['archetype'], 'want_links': N, 'links': [l['move'] for l in links], 'dist': dist, 'damage': dmg,
                'want_damage': c['damage'], 'total': total, 'want_total': c['total'], 'hitstop': hs, 'want_hitstop': c['hitstop'], 'ok': ok}
        line = f"{n:11s} {c['archetype']:8s} {len(links)}/{N} links {' > '.join(l['move'] for l in links)} | dmg {dmg} = {total} (want {c['total']}) | hit-stop {hs} {'ok' if ok else 'FAIL'}"
        print(line, flush=True); lines.append(line)
    text_sheet('roster', lines); save()

# ---- whiff / being hit restarts -----------------------------------------------------------------------------------
if 'whiff' in SECTIONS:
    fi = 0; start(fi); nodes = nodes_of(fi); root = CL['fighters'][fi]['tree']
    link1 = None
    out = res['whiff'] = {}
    settle(); setpos(160); seen = []
    for rep in range(3):                                      # far: every press is link 1
        run(2, 'a')
        for _ in range(60):
            if st(0) == 'ATTACK': break
            run(1)
        seen.append(b.fget(0, 'node'))
        for _ in range(80):
            if st(0) == 'IDLE': break
            run(1)
        run(8)
    link1 = seen[0]
    out['from_neutral'] = {'nodes': seen, 'ok': len(set(seen)) == 1}
    settle(); setpos(30); run(2, 'a')                         # link 1 hits, the dummy taken away, link 2 whiffs
    for _ in range(40):
        if b.fget(0, 'landed'): break
        run(1)
    while b.fget(0, 'freeze'): run(1)
    cam = b.r(b.syms['cam_x'], 2)
    run(2, 'a'); n2 = b.fget(0, 'node'); b.place(2, x=cam + 290); run(1)
    for _ in range(80):
        if st(0) == 'IDLE': break
        run(1)
    land2 = b.fget(0, 'landed'); run(4); run(2, 'a'); run(1); n3 = b.fget(0, 'node')
    out['mid_chain_whiff'] = {'link2': n2, 'link2_landed': land2, 'next': n3, 'link1': link1, 'ok': n2 != link1 and not land2 and n3 == link1}
    settle(); setpos(30); run(2, 'a')                         # link 1 hits, then the dummy hits P1: back to link 1
    for _ in range(40):
        if b.fget(0, 'landed'): break
        run(1)
    for _ in range(80):                                       # P1 idle with its window open, the dummy out of its stun
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK'): break
        run(1)
    ct = b.fget(0, 'chain_t'); b.place(2, x=b.fget(0, 'x') + 26); hit = False
    for k in range(20):
        b.intent(2, press=1 if k < 2 else 0, face=-1); run(1)
        if st(0) == 'HITSTUN': hit = True; break
    ct2 = b.fget(0, 'chain_t')
    for _ in range(80):
        if st(0) == 'IDLE': break
        run(1)
    setpos(30); run(2, 'a'); run(1); n4 = b.fget(0, 'node')
    out['being_hit'] = {'window_before': ct, 'hit': hit, 'window_after_hit': ct2, 'next': n4, 'link1': link1, 'ok': hit and ct > 0 and ct2 == 0 and n4 == link1}
    for k, v in out.items(): print('whiff', k, v, flush=True)
    text_sheet('whiff', ['WHIFF / BEING HIT: the chain restarts at link 1'] + [f'{k}: {v}' for k, v in out.items()]); save()

# ---- the window after the recovery (game frames: E = link 1's end, the press read on the frame its next move starts) --
if 'window' in SECTIONS:
    fi = 0; start(fi); out = res['window'] = {'want': CH['window'], 'by_delay': {}}
    for D in (2, 10, 20, 30, 33, 34, 35, 36, 37, 40, 50):
        settle(); setpos(30); run(2, 'a'); n1 = None
        for _ in range(40):
            if st(0) == 'ATTACK' and n1 is None: n1 = b.fget(0, 'node')
            if b.fget(0, 'landed'): break
            run(1)
        E = None
        for t in range(120):
            run(1, 'a' if E is not None and t - E == D - 1 else '')
            if E is None and st(0) == 'IDLE': E = t
            if E is not None and st(0) == 'ATTACK': break
        g = t - E
        n2 = b.fget(0, 'node')
        out['by_delay'][D] = {'frames_after_end': g, 'next_node': n2, 'advanced': n2 != n1}
        print('window', D, out['by_delay'][D], flush=True)
    adv = [v['frames_after_end'] for v in out['by_delay'].values() if v['advanced']]
    out['last_advancing'] = max(adv) if adv else None
    out['ok'] = out['last_advancing'] == CH['window'] and all(v['advanced'] == (v['frames_after_end'] <= CH['window']) for v in out['by_delay'].values())
    text_sheet('window', [f"WINDOW: link 1 hit; a press read g frames after its end (want: link 2 up to {CH['window']}, link 1 after)"] +
               [f"g {v['frames_after_end']:3d}: next node {v['next_node']} {'LINK 2' if v['advanced'] else 'link 1'}" for D, v in out['by_delay'].items()] +
               [f"last advancing {out['last_advancing']}  {'ok' if out['ok'] else 'FAIL'}"]); save()

# ---- latch + buffer (ages in game frames: from the frame the game took the press, hit-stop frames not counted) --------
if 'buffer' in SECTIONS:
    out = res['buffer'] = {}
    fi = 0; start(fi)
    lat = out['latch'] = []
    for at in ('first', 'middle', 'last'):                    # one press inside link 1's hit-stop
        settle(); setpos(30); run(2, 'a')
        for _ in range(40):
            if b.fget(0, 'freeze'): break
            run(1)
        fz = b.fget(0, 'freeze'); wait = {'first': 0, 'middle': fz // 2 - 1, 'last': fz - 2}[at]
        run(wait); n1 = b.fget(0, 'node'); run(1, 'a')
        k = 0; reg_fz = None; reg_k = None; free_at = None; start_at = None
        while k < 40:
            if reg_fz is None and b.fget(0, 'buffered'): reg_fz = b.fget(0, 'freeze'); reg_k = k
            if free_at is None and not b.fget(0, 'freeze'): free_at = k
            if b.fget(0, 'node') != n1: start_at = k; break
            run(1); k += 1
        lat.append({'press_in_hitstop': at, 'taken_at': reg_k, 'freeze_left_then': reg_fz, 'last_frozen_tick': free_at, 'next_link_at': start_at,
                    'ok': reg_fz is not None and free_at is not None and reg_k <= free_at and start_at == free_at + 1})
    # whiff: a press taken `age` frames before a whiffing link 1 ends restarts link 1 at once when age <= buffer
    wb = out['whiff_buffer'] = {'by_k': {}}
    for k in range(1, 12):
        settle(); setpos(160); run(1, 'a')
        for _ in range(10):
            if st(0) == 'ATTACK': break
            run(1)
        reg = None; E = None; t = 0; prev_t = b.fget(0, 'state_t'); restarted = None
        while t < 80:
            run(1, 'a' if t == k else ''); t += 1
            if reg is None and b.fget(0, 'buffered'): reg = t
            stt = b.fget(0, 'state_t')
            if st(0) == 'IDLE': E = t; restarted = False; break
            if st(0) == 'ATTACK' and stt < prev_t: E = t; restarted = True; break
            prev_t = stt
        wb['by_k'][k] = {'age_at_end': E - reg if reg is not None and E is not None else None, 'restarted': restarted}
    wb['ok'] = all(v['restarted'] == (v['age_at_end'] <= CH['buffer']) for v in wb['by_k'].values() if v['age_at_end'] is not None)
    # before a hit: Krauser's link 1 (a slow close C), a press taken before it hits: link 2 after the hit-stop when its
    # age at that first free frame is <= buffer
    fk = names.index('krauser'); start(fk)
    pb = out['prehit_buffer'] = {'fighter': 'krauser', 'by_k': {}}
    for k in range(1, 10):
        settle(); setpos(30); run(1, 'a')
        for _ in range(10):
            if st(0) == 'ATTACK': break
            run(1)
        n1 = b.fget(0, 'node'); reg = hit = fire = None; t = 0
        while t < 80:
            run(1, 'a' if t == k else ''); t += 1
            if reg is None and b.fget(0, 'buffered'): reg = t
            if hit is None and b.fget(0, 'landed'): hit = t
            if b.fget(0, 'node') != n1 and st(0) == 'ATTACK': fire = t; break
            if st(0) == 'IDLE': break
        age = hit - reg + 1 if hit is not None and reg is not None and reg <= hit else None
        pb['by_k'][k] = {'age_at_first_free_frame': age, 'next_link': fire is not None}
    pb['ok'] = all(v['next_link'] == (v['age_at_first_free_frame'] <= CH['buffer']) for v in pb['by_k'].values() if v['age_at_first_free_frame'] is not None)
    out['ok'] = all(x['ok'] for x in lat) and wb['ok'] and pb['ok']
    for k, v in out.items(): print('buffer', k, v, flush=True)
    text_sheet('buffer', ['LATCH + BUFFER (ages in game frames, hit-stop frames not counted)'] + [f'latch {x}' for x in lat] +
               [f"whiff: press {k} f in, age at the link's end {v['age_at_end']}: {'RESTART link 1' if v['restarted'] else 'idle'}" for k, v in wb['by_k'].items()] +
               [f"pre-hit krauser: press {k} f in, age at the first free frame {v['age_at_first_free_frame']}: {'LINK 2' if v['next_link'] else 'none'}" for k, v in pb['by_k'].items()] +
               [f"buffer {CH['buffer']}: {'ok' if out['ok'] else 'FAIL'}"]); save()

# ---- finishers by direction ------------------------------------------------------------------------------------------
DIRS = {'neutral': '', 'forward': 'R', 'up': 'U', 'down': 'D', 'back': 'L'}
KEY = {'neutral': 'A', 'forward': 'fA', 'up': 'uA', 'down': 'dA', 'back': 'bA'}
def finisher_case(fi, d, tree=None, extra_behind=False, shots=None, far_victim=False):
    c = (tree or tree_of(fi)).get('chain') or tree_of(fi)['chain']; N = c['length']
    settle()
    if extra_behind:                                          # a second enemy behind P1 (a copy of the dummy)
        base = b.base; src = base + 2 * b.fsize; dst = base + 3 * b.fsize
        for o in range(b.fsize): b.w(dst + o, 1, b.r(src + o, 1))
        b.fset(3, 'idx', 3)
    setpos(30)
    if extra_behind:
        b.place(3, x=b.fget(0, 'x') + extra_behind, z=30); b.fset(3, 'facing', 1); b.fset(3, 'state', ST.index('IDLE')); run(1)
    x0 = b.fget(0, 'x'); v0 = b.fget(2, 'x') - x0
    obs = {'inv': [], 'ymax': 0, 'states': set(), 'ex': set(), 'fin_t': None, 'moved': False}
    def after(t, links):
        if far_victim and len(links) == N - 1 and links[-1]['hits'] and not obs['moved']:   # out of the throw's reach
            b.place(2, x=b.fget(0, 'x') + 140); obs['moved'] = True
        if len(links) >= N:
            if obs['fin_t'] is None: obs['fin_t'] = t
            if st(0) == 'THROW':
                obs['inv'].append(b.fget(0, 'inv'))
                if 'x_throw' not in obs: obs['x_throw'] = b.fget(0, 'x')
            obs['ymax'] = max(obs['ymax'], b.fget(2, 'y')); obs['states'].add(st(2))
            if extra_behind: obs['ex'].add(st(3))
            if shots is not None and t - obs['fin_t'] in (2, 10, 22): shots.append((t, d, shot(f'fin_{names[fi]}_{d}_{t - obs["fin_t"]}')))
    links, dmg = mash(N, last=DIRS[d], after=after, setp=False)
    if len(links) < N: return {'ok': False, 'why': f'chain broke at link {len(links)}', 'links': [l['move'] for l in links]}
    fin = links[N - 1]
    for _ in range(120):                                      # the victim's flight / throw played out
        if st(2) in ('IDLE', 'WALK', 'DOWN', 'GETUP'): break
        run(1); obs['ymax'] = max(obs['ymax'], b.fget(2, 'y')); obs['states'].add(st(2))
        if extra_behind: obs['ex'].add(st(3))
    vside = b.fget(2, 'x') - obs.get('x_throw', b.fget(0, 'x'))
    want = (tree or tree_of(fi))['links']['A']
    for _ in range(N - 2): want = want['links']['A']
    wnode = want['links'].get(KEY[d]) or want['links']['A']
    r = {'want': wnode.get('move') + (' (throw)' if wnode.get('throw') else '') + ' ' + wnode.get('effect', ''), 'played': fin['move'],
         'state': fin['state'], 'victim_states': sorted(obs['states']), 'victim_max_y': round(obs['ymax'], 1), 'damage': dmg,
         'victim_side_before': round(v0), 'victim_side_after': round(vside), 'chain_t_after': b.fget(0, 'chain_t')}
    bt = back_throw(names[fi]) if d == 'back' else None
    if d == 'back' and wnode.get('throw') and not far_victim and bt is None:   # (only a stun strike: Cheng-Fu)
        r['note'] = 'no usable throw (a stun strike only): the neutral finisher'
        r['ok'] = fin['state'] == 'ATTACK' and fin['move'] == wnode['move']
        return r
    if d == 'back' and wnode.get('throw') and not far_victim:
        th = THROWS[names[fi]][bt[0]]; r['throw'] = ('D' if bt[0] else 'C') + (' mirrored' if bt[1] else ''); r['thrown_body_phase'] = th['rel'] != 0xFFFF
        inv = obs['inv']
        r.update({'inv_through_throw': bool(inv) and all(v == INV_FURY for v in inv), 'throw_frames': len(inv), 'behind': (vside > 0) != (v0 > 0)})
        if extra_behind: r['second_enemy_states'] = sorted(obs['ex'])
        r['ok'] = fin['state'] == 'THROW' and r['inv_through_throw'] and r['behind'] and r['chain_t_after'] == 0 and \
            (not extra_behind or not r['thrown_body_phase'] or 'KNOCKDOWN' in obs['ex'])
    else:
        eff = wnode.get('effect')
        okv = {'launch': obs['ymax'] > 40, 'knockdown': 'KNOCKDOWN' in obs['states'], 'blowback': 'KNOCKDOWN' in obs['states'],
               'trip': 'KNOCKDOWN' in obs['states'], 'slam': 'KNOCKDOWN' in obs['states']}.get(eff, True)
        r['ok'] = fin['state'] == 'ATTACK' and fin['move'] == wnode['move'] and okv
    return r
if 'finishers' in SECTIONS:
    out = res['finishers'] = {}; lines = ['FINISHERS by the stick on the last link (P1 faces right: forward = R, back = L)']
    allshots = []
    for n in ([x for x in names if os.environ['FIN_ALL'] == '1' or x in os.environ['FIN_ALL'].split(',')] if os.environ.get('FIN_ALL') else ('terry', 'kim', 'krauser')):   # FIN_ALL=1: the whole roster
        fi = names.index(n); start(fi); out[n] = {}
        for d in DIRS:
            sh = []
            xb = False
            if d == 'back':                                      # where the thrown body comes down: a throw measured first,
                land = []                                        # the second enemy then stands there
                bt = back_throw(n); rel = THROWS[n][bt[0]]['rel'] if bt else 0xFFFF
                def track(t, links, land=land):             # the victim's x in its thrown-body rows (from the release
                    if st(2) == 'THROWN' and b.fget(2, 'srow') > rel: land.append((b.fget(2, 'y'), b.fget(2, 'x') - land_x0[0]))   # row on)
                settle(); setpos(30); land_x0 = [b.fget(0, 'x')]
                mash(tree_of(fi)['chain']['length'], last='L', after=track, setp=False)
                low = [x for y, x in land if y < 48]            # (where its body flies low enough to meet a standing one)
                xb = int(low[min(len(low) - 1, 6)]) if low else int(land[-1][1]) if land else -60
            out[n][d] = finisher_case(fi, d, extra_behind=xb, shots=sh if n in ('terry', 'kim', 'krauser') else None)
            allshots += [x for x in sh if len(x) == 3]
            line = f"{n:8s} {d:8s} want {out[n][d].get('want')} played {out[n][d].get('played')} victim {out[n][d].get('victim_states')} max y {out[n][d].get('victim_max_y')} dmg {out[n][d].get('damage')}" + \
                (f" inv {out[n][d].get('inv_through_throw')} ({out[n][d].get('throw_frames')} f) behind {out[n][d].get('behind')} 2nd enemy {out[n][d].get('second_enemy_states')}" if d == 'back' else '') + \
                f" chain_t after {out[n][d].get('chain_t_after')} {'ok' if out[n][d]['ok'] else 'FAIL'}"
            print(line, flush=True); lines.append(line)
    # fallbacks: the victim out of the back throw's reach (poked 140 px away after link N-1's hit) = the neutral
    # finisher; a tree without the up / down finishers: up / down = the neutral
    start(0)
    out['terry_back_out_of_reach'] = r = finisher_case(0, 'back', far_victim=True)
    nt = tree_of(0)['links']['A']
    for _ in range(tree_of(0)['chain']['length'] - 2): nt = nt['links']['A']
    r['ok'] = r.get('played') == nt['links']['A']['move'] and r.get('state') == 'ATTACK'
    lines.append(f"terry back, victim out of reach -> {r.get('played')} (neutral {nt['links']['A']['move']}) {'ok' if r['ok'] else 'FAIL'}")
    t2 = json.loads(json.dumps(tree_of(0))); nd = t2['links']['A']
    for _ in range(t2['chain']['length'] - 2): nd = nd['links']['A']
    del nd['links']['uA']; del nd['links']['dA']
    start(0, tree=blob_of(0, t2))
    for d in ('up', 'down'):
        r = out['terry_no_' + d] = finisher_case(0, d, tree=t2)
        r['ok'] = r.get('played') == nd['links']['A']['move']
        lines.append(f"terry tree without {d}: {d} -> {r.get('played')} (neutral {nd['links']['A']['move']}) {'ok' if r['ok'] else 'FAIL'}")
    print('\n'.join(lines[-3:]), flush=True)
    text_sheet('finishers', lines); save()
    if allshots:                                              # pictures: each finisher 2 / 10 / 22 frames in
        ims = [(lab, Image.open(p)) for _, lab, p in allshots]; w, h = ims[0][1].size; cols = 6
        S = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); dr = ImageDraw.Draw(S)
        for i, ((_, lab, p), (_, im)) in enumerate(zip(allshots, ims)):
            x, y = i % cols * w, i // cols * (h + 14); S.paste(im, (x, y + 14)); dr.text((x + 3, y + 1), os.path.basename(p)[4:-4], fill='black')
        S.save(os.path.join(OUT, 'sheet_finishers_pics.png'))
        for _, _, p in allshots: os.remove(p)

# ---- juggle cap + downed untouchable --------------------------------------------------------------------------------
if 'juggle' in SECTIONS:
    out = res['juggle'] = {}
    fi = 0; start(fi); N = tree_of(fi)['chain']['length']
    settle(); launched = []
    def lch(t, l):
        if len(l) >= N and st(2) == 'KNOCKDOWN' and b.fget(2, 'y') > 20: launched.append(t); return True
    mash(N, last='U', after=lch, limit=200)
    launched = launched[0] if launched else None
    air = []; hp = b.fget(2, 'hp'); hold_y = 40.0; jn = []
    for t in range(160):                                      # the victim held in the air in front of P1 (test poke), A mashed
        if st(2) == 'KNOCKDOWN':
            b.fset(2, 'y', hold_y); b.fset(2, 'vy', 0); b.place(2, x=b.fget(0, 'x') + 34, z=30)
        run(1, 'a' if t % 8 < 2 else '')
        h2 = b.fget(2, 'hp')
        if h2 < hp: air.append(t)
        hp = h2; jn.append(b.fget(2, 'jug_n'))
    out['held_air'] = {'launched': launched is not None, 'air_hits': len(air), 'cap': CH['juggle_cap'], 'jug_n_max': max(jn),
                       'ok': launched is not None and len(air) == CH['juggle_cap']}
    for _ in range(400):                                      # let it fall: downed, untouchable; it stands: hittable again
        if st(2) in ('IDLE', 'WALK'): break
        run(1)
    settle(); setpos(30); hp = b.fget(2, 'hp'); run(2, 'a')
    for _ in range(40):
        if b.fget(2, 'hp') < hp: break
        run(1)
    out['after_landing'] = {'hit_again': b.fget(2, 'hp') < hp, 'jug_n': b.fget(2, 'jug_n'), 'ok': b.fget(2, 'hp') < hp and b.fget(2, 'jug_n') == 0}
    # natural juggle (no pokes): the up finisher, then A mashed at the falling victim
    settle(); launched2 = []
    def lch2(t, l):
        if len(l) >= N and st(2) == 'KNOCKDOWN' and b.fget(2, 'y') > 0: launched2.append(t); return True
    mash(N, last='U', after=lch2, limit=200); air2 = 0
    for t in range(200):
        y = b.fget(2, 'y'); h0 = b.fget(2, 'hp'); run(1, 'a' if t % 6 < 2 else '')
        if b.fget(2, 'hp') < h0 and y > 0: air2 += 1
        if st(2) in ('DOWN', 'GETUP', 'IDLE'): break
    out['natural'] = {'air_hits_after_launch': air2, 'ok': air2 <= CH['juggle_cap']}
    # downed: the neutral finisher, then A mashed at it on the floor (the bounce's hop included): no hit until it stands
    settle(); kf = []
    def flo(t, l):
        if b.fget(2, 'kfloor'): kf.append(t); return True
    mash(N, after=flo, limit=300)
    for _ in range(200):                                      # (no input) until its knockdown touches the floor
        if b.fget(2, 'kfloor') or st(2) in ('DOWN', 'IDLE'): break
        run(1)
    hp = b.fget(2, 'hp'); dh = 0; fl = []
    for t in range(200):
        if st(2) in ('IDLE', 'WALK', 'GETUP'): break
        if st(2) in ('KNOCKDOWN', 'DOWN'): b.place(0, x=b.fget(2, 'x') - 30, z=b.fget(2, 'z')); b.fset(0, 'facing', 1)
        fl.append((st(2), round(b.fget(2, 'y'), 1)))
        run(1, 'a' if t % 6 < 2 else '')
        if b.fget(2, 'hp') < hp: dh += 1
        hp = b.fget(2, 'hp')
    out['downed'] = {'floor_touched': bool(kf) or bool(fl), 'hop_frames': sum(1 for s, y in fl if s == 'KNOCKDOWN' and y > 0),
                     'hits_while_down': dh, 'ok': dh == 0 and bool(fl)}
    for k, v in out.items(): print('juggle', k, v, flush=True)
    text_sheet('juggle', ['JUGGLE CAP / DOWNED'] + [f'{k}: {v}' for k, v in out.items()]); save()

# ---- a special's hit-stop -----------------------------------------------------------------------------------------
if 'hitstop' in SECTIONS:
    out = res['hitstop'] = {'chains': {n: (v['hitstop'], v['want_hitstop']) for n, v in res.get('roster', {}).items()}}
    fi = 0; start(fi); out['special'] = {}
    for slot, keys in (('C', 'c'), ('down+C', 'Dc'), ('forward+C', 'Rc')):   # each hit's victim freeze (a projectile does
        settle(); setpos(50); run(2, keys); fz = None; hp = b.fget(2, 'hp')   # not freeze its thrower)
        for _ in range(120):
            run(1)
            if b.fget(2, 'hp') < hp: fz = b.fget(2, 'freeze'); break
        out['special'][slot] = fz
    out['special']['ok'] = all(v in (7, None) for v in out['special'].values()) and any(v == 7 for v in out['special'].values())
    out['special']['ok'] = out['special']['ok']
    out['ok'] = out['special']['ok'] and all(a == w for a, w in out['chains'].values())
    print('hitstop special', out['special'], flush=True); save()

# ---- stun: enemy light / heavy, player + its guard ------------------------------------------------------------------
if 'stun' in SECTIONS:
    out = res['stun'] = {}
    fi = 0; start(fi)
    def stun_len(i):
        while b.fget(i, 'freeze'): run(1)
        n = 0
        while st(i) == 'HITSTUN' and n < 200: run(1); n += 1
        return n
    nodes = nodes_of(fi); t = tree_of(fi)
    settle(); setpos(30); run(2, 'a')
    for _ in range(40):
        if st(2) == 'HITSTUN': break
        run(1)
    out['enemy_light'] = {'frames': stun_len(2), 'want': CH['stun_light']}
    # a strong link (link 3, close C): its reel is the heavy one
    settle(); obs = {'hp': 0, 'n': 0, 'last': None, 'reel': None}
    def cnt(t, links):
        hp = b.fget(2, 'hp')
        fz = b.fget(2, 'freeze')
        if obs['hp'] is not None and fz > obs['hp']: obs['last'] = t; obs['n'] = 0; obs['reel'] = MOVES[b.fget(2, 'anim')]
        obs['hp'] = fz
        if obs['last'] is not None and not b.fget(2, 'freeze') and st(2) == 'HITSTUN': obs['n'] += 1
    mash(3, after=cnt)                                       # links 1-3 (Terry's link 3: close C, a heavy reel)
    for _ in range(80):
        if st(2) != 'HITSTUN': break
        run(1); cnt(0, None)
    n, heavy = obs['n'], obs['reel']
    out['enemy_heavy'] = {'frames': n, 'want': CH['stun_heavy'], 'reel': heavy, 'note': 'counted from the last hit of the chain (Terry close C: a heavy reel)'}
    out['enemy_light']['ok'] = abs(out['enemy_light']['frames'] - CH['stun_light']) <= 1
    out['enemy_heavy']['ok'] = heavy == 'hit_stand_heavy' and abs(out['enemy_heavy']['frames'] - CH['stun_heavy']) <= 1
    # the player: hit by the dummy; a second enemy (a copy, slot 3) presses into its guard; the dummy itself can
    settle(); setpos(26)
    base = b.base; src = base + 2 * b.fsize; dst = base + 3 * b.fsize
    for o in range(b.fsize): b.w(dst + o, 1, b.r(src + o, 1))
    b.fset(3, 'idx', 3); b.place(3, x=b.fget(0, 'x') - 26, z=30); b.fset(3, 'facing', 1); run(1)
    b.intent(2, press=1, face=-1); run(1)
    for _ in range(30):
        if st(0) == 'HITSTUN': break
        run(1)
    g0 = b.fget(0, 'guard'); gb = b.fget(0, 'guard_by')
    # the second enemy attacks at once (inside the guard)
    hits3 = []; frames = 0; stunf = 0
    for k in range(60):
        b.intent(3, press=1 if k in (0, 1) else 0, face=1); b.intent(2)
        hp0 = b.fget(0, 'hp'); run(1); frames += 1
        if st(0) == 'HITSTUN' and not b.fget(0, 'freeze'): stunf += 1
        if st(3) == 'ATTACK' and b.fget(3, 'landed'): hits3.append(k)
        if k > 2 and st(3) == 'IDLE' and st(0) != 'HITSTUN': break
    out['player'] = {'stun_frames': stunf, 'want_stun': CH['stun_player'], 'guard_at_hit': g0, 'want_guard': CH['guard_player'],
                     'second_enemy_hit_in_guard': bool(hits3)}
    for _ in range(60): run(1)
    settle(); setpos(26); b.place(3, x=b.fget(0, 'x') - 26, z=30); b.fset(3, 'facing', 1); b.fset(3, 'state', ST.index('IDLE')); run(1)
    hit_after = False
    for k in range(40):                                       # outside any guard: the second enemy hits
        b.intent(3, press=1 if k in (0, 1) else 0, face=1); run(1)
        if st(0) == 'HITSTUN': hit_after = True; break
    out['player']['second_enemy_hit_outside_guard'] = hit_after
    for _ in range(60): run(1)
    settle(); setpos(26); b.fset(3, 'state', ST.index('OFF')); run(1)   # the same attacker during its own guard: it reaches
    b.intent(2, press=1, face=-1); run(1)
    for _ in range(30):
        if st(0) == 'HITSTUN': break
        run(1)
    while b.fget(0, 'freeze'): run(1)
    run(3); gl = b.fget(0, 'guard'); b.intent(2, press=1, face=-1); hit_same = False
    for k in range(30):
        f0 = b.fget(0, 'freeze'); run(1)
        if b.fget(0, 'freeze') > f0: hit_same = True; break
    out['player']['same_attacker_in_guard'] = {'guard_left': gl, 'hit': hit_same}
    out['player']['ok'] = abs(stunf - CH['stun_player']) <= 1 and g0 >= CH['guard_player'] - 1 and not hits3 and hit_after and hit_same
    out['ok'] = all(v['ok'] for v in out.values() if isinstance(v, dict))
    for k, v in out.items(): print('stun', k, v, flush=True)
    text_sheet('stun', ['HIT STUN / PLAYER GUARD'] + [f'{k}: {v}' for k, v in out.items()]); save()

summary = {}
for k, v in res.items():
    if k == 'roster': summary[k] = all(x['ok'] for x in v.values())
    elif k == 'finishers': summary[k] = all(x['ok'] for n, x in v.items() if isinstance(x, dict) and 'ok' in x) and \
        all(y['ok'] for n, x in v.items() if isinstance(x, dict) and 'ok' not in x for y in x.values())
    elif k in ('whiff', 'juggle'): summary[k] = all(x['ok'] for x in v.values())
    else: summary[k] = v.get('ok')
res['summary'] = summary; save()
print('SUMMARY', summary)
print('ALL OK' if all(summary.values()) else 'FAILURES: ' + ' '.join(k for k, v in summary.items() if not v))
