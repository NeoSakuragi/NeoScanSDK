#!/usr/bin/env python3
"""Brawler revamp phase 4 (docs/brawler_revamp_plan.md, docs/brawler_feel.md 7 / 8 / 8b / 8h): each fighter's piece
catalogue, an appeal score per piece, and my chain proposal, read from a built game (build/bm_chars.c, bm_spec.c,
chainlab.json; game.json). Generic: every roster fighter goes through the same code.

PIECES (candidates for a chain link): the ground normals (close / far / crouch A B C D), the command normals, the
body toss, the jump normals (tagged air, never proposed as a ground link), each chain-able special's first hit (the
fighter's six C slots: the specials a chain link cancels into; rows up to the end of the first hit's recovery) and
the back throw (the throw whose victim ends behind, the chain core's rule).

TAGS, all from the data:
  limb      punch / kick / slash by the source button (KOF, Kizuna: A C punch, B D kick; SS2 / SS4: A B C slash, D kick)
  height    high / mid / low: the attack box's centre on the fighter's own standing hurt box (idle): above 2/3 of its
            height high, below 1/3 low (or a box touching the floor band, bottom within 12 px of the feet), else mid
  reaction  the victim's reaction the brawler gives the move (its routes file / default tree: knockdown, launch,
            trip = sweep, blowback = push, slam; none = a plain reel); the chain core's finishers set their own
  reach     px from the feet to the attack box's front edge, the step's forward travel included (the farthest live frame)
  startup / active / recovery   the 1C segments (retime.py): frames before the first live attack box, the live
            frames, the frames after the last (all windows summed)
  damage    the brawler's default for its weight / effect (routes.default_damage), a special its first hit's
  speed     startup class: snappy (<= 4 f before contact), quick (<= 7), slow (> 7)

APPEAL (0-100) = 20 x (drawings + evenness + travel + contact + joins), each part 0..1:
  drawings  distinct drawings shown: (n - 1) / 8, capped at 1 (9 drawings or more = full)
  evenness  no drawing held far longer than the rest: r = longest hold / median hold (frames);
            1 when r <= 2, 0 when r >= 6, linear between
  travel    pose travel: silhouette pixels that change from one drawing to the next (feet-aligned, the step's
            forward travel applied), summed over the move, over the fighter's idle silhouette area; / 6, capped at 1
  contact   a clear contact frame: 0.35 the first live frame shows a new drawing (not the one before it), up to 0.35
            for that drawing snapping forward (its front edge past the previous drawing's, 24 px = full), 0.3 an effect
            on it (a part drawn from the shared effects palettes: a smear / flash) or a voice on the move
  joins     clean joins with idle: the silhouette overlap (intersection / union) of the first drawing and of the last
            drawing with the idle pose (a jump normal: the jump's fall pose), averaged; 0.25 -> 0, 0.75 -> 1, linear
  (constants set once on the whole roster's 587 pieces, 2026-10-08: medians 6 drawings, hold ratio 2, travel 3.5x,
  overlap 0.5; appeal 10th / 50th / 90th percentile 46 / 63 / 80)
The chain proposal's flow uses one more number, the join between two pieces: the overlap of a link's contact
drawing (where the next press cancels it) with the next link's first drawing.

    python3 tools/brawler/pieces.py GAME_DIR FIGHTER...      the catalogue and the proposal as text
    python3 tools/brawler/pieces.py GAME_DIR --json FIGHTER   the same as JSON"""
import itertools, json, os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from move_images import Rom, _nums
import routes as R, retime as RT

NORMALS = ['atk_a_close', 'atk_a_far', 'atk_a_crouch', 'atk_b_close', 'atk_b_far', 'atk_b_crouch',
           'atk_c_close', 'atk_c_far', 'atk_c_crouch', 'atk_d_close', 'atk_d_far', 'atk_d_crouch',
           'atk_ab_close', 'atk_ab_far', 'atk_ab_crouch', 'atk_cd_close', 'atk_cd_crouch']
COMMANDS = ['cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d', 'cmd_fwd_c', 'cmd_fwd_cd', 'body_toss']
AIR = ['atk_a_jump', 'atk_b_jump', 'atk_c_jump', 'atk_d_jump', 'atk_cd_jump']
SLOTS = ['D', 'fD', 'dD', 'uD', 'dfD', 'ufD']
SLOT_NAME = {'D': 'C', 'fD': 'forward + C', 'dD': 'down + C', 'uD': 'up + C', 'dfD': 'down-forward + C', 'ufD': 'up-forward + C'}
LIMBS = {'kof': {'a': 'punch', 'b': 'kick', 'c': 'punch', 'd': 'kick', 'ab': 'punch', 'cd': 'kick'},
         'samsho': {'a': 'slash', 'b': 'slash', 'c': 'slash', 'd': 'kick', 'ab': 'slash', 'cd': 'kick'},
         'whp': {'a': 'punch', 'b': 'kick', 'c': 'punch', 'd': 'kick', 'ab': 'punch', 'cd': 'kick'}}
GAME_LIMBS = {'kof94': 'kof', 'kof96': 'kof', 'kof98': 'kof', 'kof99': 'kof', 'kizuna': 'kof', 'doubledr': 'kof',
              'samsho2': 'samsho', 'samsho4': 'samsho', 'whp': 'whp'}
EFFECT_TAG = {'none': 'reel', 'knockdown': 'knockdown', 'launch': 'launcher', 'trip': 'sweep', 'blowback': 'push', 'slam': 'slam'}
PURPOSE = {'chain': 'damage: the plain string', 'neutral': 'damage: knocks down', 'forward': 'reposition: pushes the victim away',
           'up': 'juggle: launches for air hits', 'down': 'knockdown: sweep', 'down_slam': 'juggle: slams, the victim bounces',
           'back': 'escape: invincible throw behind'}
FPS = 59.18                                       # the Neo Geo's frame rate (the clips play at it)


# ---- C tables ---------------------------------------------------------------------------------------------------------
def c_body(src, name):
    m = re.search(r'(?:static )?const \w+ %s\[[^\]]*\] = \{(.*?)\};' % re.escape(name), src, re.S)
    return m.group(1) if m else None


def top_items(s):
    """the top-level {...} items of an initialiser body -> their inner texts"""
    out, d, st = [], 0, 0
    for i, ch in enumerate(s):
        if ch == '{':
            if d == 0: st = i + 1
            d += 1
        elif ch == '}':
            d -= 1
            if d == 0: out.append(s[st:i])
    return out


def fields(s):
    """an item's comma-separated fields at brace depth 0"""
    out, d, cur = [], 0, ''
    for ch in s:
        if ch == '{': d += 1
        elif ch == '}': d -= 1
        if ch == ',' and d == 0: out.append(cur.strip()); cur = ''
        else: cur += ch
    if cur.strip(): out.append(cur.strip())
    return out


STEP = re.compile(r'\{(\d+), (\d+), (\d+), \{(-?\d+), (-?\d+), (\d+), (\d+)\}, \{(-?\d+), (-?\d+), (\d+), (\d+)\}, (-?\d+), (\d+)\}')


def steps_of(src, arr):
    b = c_body(src, arr)
    if b is None: return None
    return [{'frame': int(m[0]), 'ticks': int(m[1]), 'flags': int(m[2]), 'hurt': tuple(map(int, m[3:7])),
             'atk': tuple(map(int, m[7:11])), 'dx': int(m[11]), 'hy': int(m[12])} for m in STEP.findall(b)]


# ---- one fighter's data ---------------------------------------------------------------------------------------------
class Fighter:
    def __init__(self, game, name, rom=None, lab=None, G=None):
        self.game, self.name = game, name
        build = os.path.join(game, 'build')
        self.rom = rom or Rom(build)
        self.src = self.rom.src
        self.spec_src = open(os.path.join(build, 'bm_spec.c')).read()
        lab = lab or json.load(open(os.path.join(build, 'chainlab.json')))
        self.lab = next(f for f in lab['fighters'] if f['name'] == name)
        G = G or json.load(open(os.path.join(game, 'game.json')))
        self.G = G
        self.ros = next(r for r in G['roster'] if r['name'] == name)
        self.src_game = self.lab['game']
        self.limbs = LIMBS[GAME_LIMBS.get(self.src_game, 'kof')]
        ch = self.rom.chars[name]
        self.npal, self.nsets, self.tile_hi = ch[0], ch[1], self.rom.tile_hi[name]
        self.pals = _nums(self.rom.arr(f'{name}_pals'))[:self.npal * self.nsets * 16]
        self._ix = {}
        idle = steps_of(self.src, f'{name}_idle')
        self.idle_frame = idle[0]['frame']
        self.body = idle[0]['hurt']                   # the standing hurt box: (x, y, w, h), y < 0 up, half extents
        self.body_h = -(self.body[1] - self.body[3])  # its top above the feet
        self.idle_mask = self.mask(self.idle_frame)
        self.idle_area = max(1, int(self.idle_mask[0].sum()))
        jf = steps_of(self.src, f'{name}_jump_up_fall')
        self.air_mask = self.mask(jf[0]['frame'])[0] if jf else self.idle_mask[0]
        base = R.load(name, os.path.join(HERE, '..', '..', self.ros['routes']) if self.ros.get('routes', 'default') != 'default' else None)
        self.effects = {}                              # a move's reaction in its routes file / the default tree
        for _, nd in R._ground_pieces(base):
            e = nd.get('effect', 'none')
            if e != 'none' or nd['move'] not in self.effects: self.effects[nd['move']] = e
        self.has = set(self.lab['has'])
        self.ba = lab['ba']

    # ---- drawings ----
    def index(self, fi):
        if fi not in self._ix: self._ix[fi] = self.rom.frame_index(self.name, fi, self.tile_hi)
        return self._ix[fi]

    def mask(self, fi, dx=0, size=(360, 720), feet=(270, 240)):
        """frame fi's silhouette on a fixed canvas, feet at `feet` (row, col), dx px forward -> (bool array, front col)"""
        r = self.index(fi)
        out = np.zeros(size, bool)
        if r is None: return out, None
        ix, ox, oy = r
        y0, x0 = feet[0] - oy, feet[1] - ox + dx
        h, w = ix.shape
        ys, xs = slice(max(0, y0), min(size[0], y0 + h)), slice(max(0, x0), min(size[1], x0 + w))
        if ys.stop > ys.start and xs.stop > xs.start:
            out[ys, xs] = ix[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0] > 0
        cols = np.where(out.any(0))[0]
        return out, (int(cols.max()) - feet[1] if len(cols) else None)

    def has_effect_part(self, fi):
        parts = re.findall(r'\{(-?\d+), (-?\d+), (\d+), (\d+), (\d), (\d), (\d+), (\w+)\}', self.rom.arr(f'{self.name}_f{fi}') or '')
        return any(int(p[6]) & 0x80 for p in parts)

    # ---- specials (ROM programs played alone: retime.Prog over the exported bspec_t) ----
    def special(self, k):
        """pool special k -> per frame [{'frame', 'x', 'y', 'live', 'atk', 'step'}] at 1x (its whiff), or None"""
        b = c_body(self.spec_src, f'{self.name}_specials')
        sp = fields(top_items(b)[k]); sp += ['0'] * (30 - len(sp))   # trailing zero fields are left out
        prog_n, an_n = sp[6], sp[7]
        if prog_n == '0' or an_n == '0':                     # a captured script: its rows are its frames
            rows = top_items(c_body(self.spec_src, sp[4]) or '')
            out = []
            for r in rows:
                f = fields(r); atk = tuple(map(int, fields(f[3].strip('{}'))))
                out.append({'frame': int(f[0]), 'x': int(f[1]), 'y': int(f[2]), 'live': bool(int(f[4]) & 1), 'atk': atk})
            return out
        prims = [tuple(int(v) for v in fields(it)) for it in top_items(c_body(self.spec_src, prog_n))]
        anims = []
        for it in top_items(c_body(self.spec_src, an_n)):
            n, hold, arr = fields(it)
            st = steps_of(self.spec_src, arr)
            anims.append({'hold': bool(int(hold)), 'steps': [dict(s, dx=-s['dx'], flags=(0x80 if s['flags'] & 8 else 0) | (0x2000 if s['flags'] & 32 else 0), bflags=s['flags']) for s in st]})
        acts = [[bool(s['bflags'] & 1) for s in a['steps']] for a in anims]
        vars_n, nvar, vdef, vanim, vcols = sp[19], int(sp[20]), int(sp[21]), int(sp[22]), int(sp[24])
        vals = [int(v) for v in fields(c_body(self.spec_src, vars_n))] if vars_n != '0' else None
        pg = RT.Prog(prims, anims, acts, vals, vdef if nvar else 0, vcols, vanim, nvar)
        out = []
        for r in pg.run():
            s = anims[r['j']]['steps'][r['i']]
            out.append({'frame': s['frame'], 'x': r['x'] >> 16, 'y': r['y'] >> 16, 'live': r['act'], 'atk': s['atk']})
        return out


# ---- pieces --------------------------------------------------------------------------------------------------------
def label_of(move):
    m = re.match(r'atk_([a-d]{1,2})_(close|far|crouch|jump)$', move)
    if m: return {'close': 'close', 'far': 'far', 'crouch': 'crouch', 'jump': 'jump'}[m.group(2)] + ' ' + m.group(1).upper()
    m = re.match(r'cmd_(fwd|df)_([a-d]{1,2})$', move)
    if m: return ('forward + ' if m.group(1) == 'fwd' else 'down-forward + ') + m.group(2).upper()
    return {'body_toss': 'body toss'}.get(move, move)


def button_of(move):
    m = re.search(r'_([a-d]{1,2})(?:_|$)', move.replace('atk_', '_').replace('cmd_fwd', '').replace('cmd_df', ''))
    return m.group(1) if m else None


def height_of(F, boxes):
    """the attack box (facing left: x, y centre from the feet, w, h half extents) on the standing body"""
    if not boxes: return None
    x, y, w, h = max(boxes, key=lambda b: b[2] * b[3])
    cy, bot = -y, -(y + h)                            # px above the feet
    H = F.body_h or 90
    if cy > H * 2 / 3: return 'high'
    if cy < H / 3 or bot <= 12: return 'low'
    return 'mid'


def frames_normal(F, steps):
    """a brawler move frame by frame at 1x (fighter.c anim_tick: routes.play_steps) -> per frame dict"""
    sf = [(s['ticks'], bool(s['flags'] & 1), bool(s['flags'] & 4)) for s in steps]
    shown = R.play_steps(sf)
    out, x, last = [], 0, -1
    for k in shown:
        s = steps[k]
        if k != last: x += s['dx']; last = k                    # the step's travel as it starts
        out.append({'frame': s['frame'], 'x': x, 'y': s['hy'], 'live': bool(s['flags'] & 1), 'atk': s['atk'], 'opens': bool(s['flags'] & 4) and k != (out and shown[len(out) - 1])})
    return out


def holds(frames):
    """drawings in order with their hold (frames shown in a row)"""
    out = []
    for fr in frames:
        if out and out[-1][0] == fr['frame']: out[-1][1] += 1
        else: out.append([fr['frame'], 1])
    return out


def front(F, fr):
    x, y, w, h = fr['atk']
    return -x + w + fr['x']                           # sprite faces left: forward = -x; the travel so far


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum()) / u if u else 0.0


def appeal(F, frames, contact, air=False):
    """frames (per frame: frame, x, live...), contact = index of the first live frame -> (score, parts, notes)"""
    hl = holds(frames)
    seq = [h[0] for h in hl]
    distinct = len({F.index(fi)[0].tobytes() if F.index(fi) is not None else fi for fi in set(seq)})
    p_draw = min(1.0, (distinct - 1) / 8)
    hs = sorted(h[1] for h in hl)
    med = hs[len(hs) // 2] if len(hs) % 2 else (hs[len(hs) // 2 - 1] + hs[len(hs) // 2]) / 2
    r = max(hs) / med if med else 1
    p_even = max(0.0, min(1.0, 1 - (r - 2) / 4))
    # pose travel: changed pixels between consecutive drawings (in place: the travel applied)
    xs = {}
    for fr in frames: xs.setdefault(fr['frame'], fr['x'])
    order = []
    for fr in frames:
        if not order or order[-1] != (fr['frame'], fr['x']): order.append((fr['frame'], fr['x']))
    ch = 0
    for (a, ax), (b, bx) in zip(order, order[1:]):
        ch += (F.mask(a, ax)[0] ^ F.mask(b, bx)[0]).sum()
    trav = ch / F.idle_area
    p_trav = min(1.0, trav / 6)
    # contact frame
    pc, why = 0.0, []
    if contact is not None:
        cf = frames[contact]['frame']
        prev = frames[contact - 1]['frame'] if contact else None
        if prev is None or prev != cf: pc += 0.35; why.append('new drawing on contact')
        fc = F.mask(cf, 0)[1]; fp = F.mask(prev, 0)[1] if prev is not None else None
        if fc is not None and fp is not None and fc > fp:
            pc += 0.35 * min(1.0, (fc - fp) / 24); why.append(f'snaps {fc - fp} px forward')
        if F.has_effect_part(cf) or frames_have_voice(F, frames): pc += 0.3; why.append('effect / voice')
    p_cont = pc
    # joins with idle
    home = F.air_mask if air else F.idle_mask[0]
    j0 = iou(F.mask(seq[0])[0], home); j1 = iou(F.mask(seq[-1])[0], home)
    p_join = max(0.0, min(1.0, ((j0 + j1) / 2 - 0.25) / 0.5))
    parts = {k: round(float(v), 2) for k, v in (('drawings', p_draw), ('evenness', p_even), ('travel', p_trav), ('contact', p_cont), ('joins', p_join))}
    raw = {'drawings': distinct, 'longest_hold': int(max(hs)), 'median_hold': float(med), 'travel': round(float(trav), 2), 'contact': why,
           'join_start': round(j0, 2), 'join_end': round(j1, 2)}
    return int(round(20 * sum(parts.values()))), parts, raw


def frames_have_voice(F, frames):
    return bool(frames and frames[0].get('voice'))


def segs_of(frames):
    return RT.segments([f['live'] for f in frames])


def normal_piece(F, move):
    st = steps_of(F.src, f'{F.name}_{move}')
    if not st: return None
    fr = frames_normal(F, st)
    sg = segs_of(fr)
    if not sg: return None
    v = (F.lab['voices'].get('map') or {}).get(move)
    if v: fr[0]['voice'] = True
    contact = sg[0]
    live = [f for f in fr if f['live']]
    reach = max(front(F, f) for f in live)
    eff = F.effects.get(move, 'none')
    w = 'strong' if (button_of(move) or 'a') in ('c', 'd', 'cd', 'ab') or move == 'body_toss' else 'light'
    dmg = R.default_damage({'effect': eff, 'weight': w})
    kind = 'air' if move in AIR else 'command' if move in COMMANDS else 'normal'
    height = 'air' if kind == 'air' else 'low' if move.endswith('_crouch') and height_of(F, [f['atk'] for f in live]) != 'high' else height_of(F, [f['atk'] for f in live])
    btn = button_of(move)
    sc, parts, raw = appeal(F, fr, contact, kind == 'air')
    return {'id': move, 'kind': kind, 'move': move, 'label': label_of(move), 'button': (btn or '').upper(),
            'limb': F.limbs.get(btn, 'body') if move != 'body_toss' else 'body', 'height': height, 'weight': w,
            'reaction': EFFECT_TAG[eff], 'effect': eff, 'reach': int(reach), 'segs': sg,
            'startup': sg[0], 'active': sum(sg[1::2]), 'recovery': sum(sg[2::2]), 'hits': len(sg) // 2,
            'damage': dmg[0], 'push': dmg[1], 'voice': bool(v), 'appeal': sc, 'parts': parts, 'raw': raw, 'frames': fr,
            'check': {'frames': len(fr), 'data_total': F.lab['moves'].get(move, {}).get('total'), 'data_segs': F.lab['segs']['moves'].get(move)}}


def special_piece(F, slot):
    inp = F.ros['specials'].get(slot)
    if not inp: return None
    pool = F.lab['pool']
    k = next((i for i, p in enumerate(pool) if p['input'] == inp), None)
    if k is None: return None
    fr = F.special(k)
    if not fr: return None
    sg_all = segs_of(fr)
    data = (F.lab['segs'].get('specials') or [None] * (k + 1))[k]
    if not sg_all: return None
    cut = sum(sg_all[:3])                             # the first hit: startup, its window, the recovery after it
    first = fr[:cut]
    sg = sg_all[:3]
    live = [f for f in first if f['live']]
    reach = max(-f['atk'][0] + f['atk'][2] + f['x'] for f in live) if live else 0
    p = pool[k]
    dmg = next((h[1] for h in p['hits'] if h[1]), 0) or 8
    sc, parts, raw = appeal(F, first, sg[0])
    sid = 'sp-' + re.sub(r'[^a-z0-9]+', '-', inp.lower()).strip('-')
    return {'id': sid, 'kind': 'special', 'special': inp, 'slot': slot, 'label': f'{inp} (on {SLOT_NAME[slot]}), first hit',
            'button': 'C', 'limb': 'special', 'height': height_of(F, [f['atk'] for f in live]), 'weight': 'strong',
            'reaction': 'special', 'effect': 'none', 'reach': int(reach), 'segs': sg, 'startup': sg[0], 'active': sg[1],
            'recovery': sg[2], 'hits': len(sg_all) // 2, 'damage': dmg, 'push': 0, 'voice': False, 'appeal': sc,
            'parts': parts, 'raw': raw, 'frames': first,
            'check': {'frames': len(first), 'whole': len(fr), 'segs_all': sg_all, 'data_segs': data}}


def throw_piece(F):
    """the back throw (the chain core's rule, fighter.c chain_throw): throw D, then C, whose victim ends behind; none:
    its throw played mirrored (the thrower turned away)"""
    best = None
    for key in ('throw_d', 'throw_c'):
        b = c_body(F.src, f'{F.name}_throws')
        th = top_items(b)[0 if key == 'throw_c' else 1]
        f = fields(th)
        if f[2] == '0' or f[0] == '0': continue
        if len(f) > 12 and int(f[12]): continue                       # a stun strike is no throw
        rows = [tuple(map(int, fields(r))) for r in top_items(c_body(F.src, f[2]))]
        nrows, speed, ret, rel, land = int(f[0]), int(f[1], 0), int(f[3]), int(f[4]), int(f[5])
        end = rows[land if land < len(rows) else -1]
        behind = end[5] < 0                                            # offsets stay in the grab facing
        if behind or best is None: best = (key, rows, speed, ret, behind)
        if behind: break
    if best is None: return None
    key, rows, speed, ret, behind = best
    vposes = _nums(c_body(F.src, f'{F.name}_vposes') or '')
    fr, acc, flight = [], 0, None
    while True:
        i = acc >> 8
        if i >= len(rows): break
        tframe, tx, ty, vpose, fl, vx, vy = rows[i]
        vic = None
        if vpose != 0xFF:
            if fl & 32:                                               # a BA_* animation it plays (its flight), from its row
                if flight is None or flight[0] != vpose:
                    st = steps_of(F.src, f"{F.name}_{F.ba[vpose]}") if vpose < len(F.ba) else None
                    flight = (vpose, [st[k]['frame'] for k in R.play_steps([(s['ticks'], False, False) for s in st])] if st else [], len(fr))
                seq = flight[1]
                vf = seq[min(len(fr) - flight[2], len(seq) - 1)] if seq else None
            else: vf = vposes[vpose] if vpose < len(vposes) and vposes[vpose] != 0xFFFF else None
            if vf is not None: vic = {'frame': vf, 'x': vx, 'y': vy, 'mirror': not fl & 1, 'front': bool(fl & 2)}
        fr.append({'frame': tframe, 'x': tx, 'y': ty, 'live': bool(fl & 4), 'atk': (0, 0, 0, 0), 'turned': bool(fl & 8), 'victim': vic, 'row': i})
        acc += speed
    if not behind:
        for f in fr: f['turned'] = not f['turned']
    imp = next((i for i, f in enumerate(fr) if f['live']), None)
    sc, parts, raw = appeal(F, fr, imp)
    return {'id': 'throw-back', 'kind': 'throw', 'throw': key, 'label': f"back throw ({'throw ' + key[-1].upper()}{'' if behind else ', played mirrored'})",
            'button': 'A', 'limb': 'throw', 'height': 'mid', 'weight': 'strong', 'reaction': 'thrown behind', 'effect': 'knockdown',
            'reach': 96, 'segs': [], 'startup': 0, 'active': 0, 'recovery': 0, 'hits': 1, 'damage': 0, 'push': 0, 'voice': False,
            'appeal': sc, 'parts': parts, 'raw': raw, 'frames': fr, 'mirrored': not behind,
            'check': {'frames': len(fr), 'rows': len(rows), 'speed': speed}}


def catalogue(F):
    out = []
    for m in NORMALS + COMMANDS + AIR:
        if m in F.has:
            p = normal_piece(F, m)
            if p: out.append(p)
    for s in SLOTS:
        p = special_piece(F, s)
        if p and all(q['id'] != p['id'] for q in out): out.append(p)
    t = throw_piece(F)
    if t: out.append(t)
    return out


# ---- the proposal --------------------------------------------------------------------------------------------------
def join(F, a, b):
    """a link's contact drawing (the next press cancels it there) -> the next link's first drawing: silhouette overlap"""
    ca = a['frames'][a['startup']]['frame'] if a['segs'] else a['frames'][-1]['frame']
    return iou(F.mask(ca)[0], F.mask(b['frames'][0]['frame'])[0])


HW = 16                                               # the dummy victim's half width (px): a standing hurt box


def spacing(seq):
    """the victim in reach: it starts 8 px inside link 1's reach, slides back by each link's push, the attacker's travel
    to the contact frame closes in; -> margins per link (px; < 0: that link whiffs)"""
    d = seq[0]['reach'] + HW - 8
    out = []
    for i, p in enumerate(seq):
        out.append(p['reach'] + HW - d)
        trav = p['frames'][min(p['startup'], len(p['frames']) - 1)]['x']
        d = max(2 * HW, d + p['push'] - trav)
    return out


def rank_pieces(F, cat, arch):
    """my ranking of the catalogue (the page's order): appeal, then a snappy first hit for fast / balanced fighters,
    ground pieces before air / specials / the throw"""
    pen = {'normal': 0, 'command': 0, 'special': 15, 'air': 25, 'throw': 10}
    return sorted(cat, key=lambda p: -(p['appeal'] - pen[p['kind']] - (0 if arch == 'heavy' else max(0, p['startup'] - 6))))


def propose(F, cat):
    arch = F.ros['archetype']
    N = F.G['chain']['lengths'][arch]
    ground = [p for p in cat if p['kind'] in ('normal', 'command')]
    reel = [p for p in ground if p['effect'] == 'none' and p['move'] != 'body_toss']   # builders: plain reels (the toss is a finisher)
    lights = [p for p in reel if p['weight'] == 'light']
    best_start = min((p['startup'] for p in (lights or reel)), default=0)
    def score(seq):
        m = spacing(seq)
        if min(m) < 0: return None
        s = sum(p['appeal'] for p in seq) / len(seq)
        jn = [join(F, a, b) for a, b in zip(seq, seq[1:])]
        s += 25 * (sum(jn) / len(jn) if jn else 1)
        w = [p['weight'] == 'strong' for p in seq]
        s -= 12 * sum(1 for a, b in zip(w, w[1:]) if a and not b)          # rising intensity: never strong -> light
        lv = sum(1 for a, b in zip(seq, seq[1:]) if a['limb'] != b['limb'])
        hv = len({p['height'] for p in seq})
        s += 4 * min(lv, 2) + 3 * min(hv, 3)                                 # height / limb variety
        if arch == 'heavy':
            s += 6 * sum(w)                                                   # the heavy: fewer, stronger hits
        else:
            s -= 3 * max(0, seq[0]['startup'] - best_start)                   # snappy first hit (feel 1)
            if arch == 'fast': s -= 1.0 * sum(p['startup'] for p in seq[1:]) / len(seq)
        return s, m, jn
    best = None
    pool = sorted(reel, key=lambda p: -p['appeal'])[:12]
    for seq in itertools.permutations(pool, N - 1):
        if arch != 'heavy' and seq[0]['weight'] != 'light' and lights: continue
        r = score(list(seq))
        if r and (best is None or r[0] > best[0]): best = (r[0], list(seq), r[1], r[2])
    if best is None:                                  # nothing keeps the victim in reach: the best appeal, flagged
        seq = pool[:N - 1]; best = (0, seq, spacing(seq), [join(F, a, b) for a, b in zip(seq, seq[1:])])
    _, builders, margins, joins = best
    used = {p['id'] for p in builders}
    last = builders[-1]

    def pick(cands, why):
        """finisher candidates -> ranked [(piece, margin, join, score)]: reach after the builders, appeal, join"""
        out = []
        for p in cands:
            if p['id'] in used: continue
            m = spacing(builders + [p])[-1]
            j = join(F, last, p)
            out.append((p, m, j, p['appeal'] + 25 * j - (40 if m < 0 else 0)))
        out.sort(key=lambda t: -t[3])
        return [{'id': p['id'], 'margin': int(m), 'join': round(j, 2), 'score': round(sc, 1), 'why': why} for p, m, j, sc in out[:4]]
    strong = [p for p in ground if p['weight'] == 'strong']
    fins = {}
    fins['neutral'] = pick([p for p in strong if p['effect'] in ('none', 'knockdown') and p['move'] != 'body_toss'] or strong, 'a strong hit that reads as an ender')
    fins['forward'] = pick([p for p in ground if p['effect'] == 'blowback' or p['move'].startswith('cmd_fwd') or p['move'] == 'body_toss'
                            or (p['weight'] == 'strong' and max(f['x'] for f in p['frames']) > 8)] or strong, 'a push: forward travel or a blowback')
    fins['up'] = pick([p for p in strong if p['effect'] == 'launch' or p['height'] == 'high'] or strong, 'a launcher: a rising, high strong hit')
    if (F.ros.get('finishers') or {}).get('down', 'sweep') == 'slam' or arch == 'heavy':
        fins['down'] = pick([p for p in strong if p['height'] != 'low' and p['move'].endswith(('_close', '_far'))] or strong, 'a slam: a strong close hit downward')
        down_kind = 'down_slam'
    else:
        fins['down'] = pick([p for p in ground if p['height'] == 'low' and (p['weight'] == 'strong' or p['effect'] == 'trip')] or strong, 'a sweep: a low strong kick')
        down_kind = 'down'
    # one piece per finisher where possible: each slot in turn takes its best candidate no earlier slot took (none
    # left in its own list: its best, shared, as the chain core allows: Krauser's up and down are both far D today)
    taken = set()
    for k in ('neutral', 'forward', 'up', 'down'):
        c = fins[k]
        if not c: continue
        ix = next((i for i, x in enumerate(c) if x['id'] not in taken), 0)
        c.insert(0, c.pop(ix)); taken.add(c[0]['id'])
    thr = next((p for p in cat if p['kind'] == 'throw'), None)
    chain = {'archetype': arch, 'length': N, 'links': [p['id'] for p in builders], 'margins': [int(m) for m in margins],
             'joins': [round(float(j), 2) for j in joins], 'purpose': PURPOSE['chain'],
             'current': F.lab['tree'].get('chain', {})}
    fin = {k: {'pick': v[0]['id'] if v else None, 'alternatives': v, 'purpose': PURPOSE[down_kind if k == 'down' else k]} for k, v in fins.items()}
    fin['back'] = {'pick': thr['id'] if thr else None, 'alternatives': [], 'purpose': PURPOSE['back']}
    return {'archetype': arch, 'chain': chain, 'finishers': fin, 'down_kind': 'slam' if down_kind == 'down_slam' else 'sweep'}


def review(game, name, rom=None, lab=None, G=None):
    F = Fighter(game, name, rom, lab, G)
    cat = catalogue(F)
    prop = propose(F, cat)
    ranked = rank_pieces(F, cat, F.ros['archetype'])
    return F, ranked, prop


def text(F, cat, prop):
    out = [f"{F.name} ({F.src_game}), archetype {prop['archetype']}, {len(cat)} pieces"]
    for p in cat:
        out.append(f"  {p['appeal']:3d}  {p['id']:14s} {p['label'][:34]:34s} {p['limb']:7s} {str(p['height']):5s} {p['reaction']:9s} "
                   f"reach {p['reach']:4d}  {p['startup']:3d}/{p['active']:3d}/{p['recovery']:3d}  dmg {p['damage']:2d}  {p['parts']}")
    c = prop['chain']
    out.append(f"  chain: {' > '.join(c['links'])}  margins {c['margins']} joins {c['joins']}")
    for k, v in prop['finishers'].items():
        out.append(f"  {k:8s} {v['pick']}  ({v['purpose']})  alt: {[a['id'] for a in v['alternatives'][1:]]}")
    return '\n'.join(out)


if __name__ == '__main__':
    game = sys.argv[1]; args = sys.argv[2:]
    js = '--json' in args; args = [a for a in args if a != '--json']
    for n in args:
        F, cat, prop = review(game, n)
        if js: print(json.dumps({'pieces': [{k: v for k, v in p.items() if k != 'frames'} for p in cat], 'proposal': prop}, indent=1))
        else: print(text(F, cat, prop))
