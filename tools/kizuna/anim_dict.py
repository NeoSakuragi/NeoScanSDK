#!/usr/bin/env python3
"""Kim's ANIMATION DICTIONARY: every animation of his table in Kizuna Encounter (char 5, $80000[5], 313 animations),
rendered from the ROM the way the brawler shows him (kz.render_step_zoom at Kizuna's widest in-play zoom $CC = 0.80,
export_kz.Z), for the Brawler Lab's dictionary page (tools/brawler/chainlab/anims.html?f=kim) and the review pages'
move picker ("All animations" tab: a pick is stored as the piece "anim-6E").

    python3 tools/kizuna/anim_dict.py OUT [GAME_DIR]      -> OUT/review/kim_anims.json + OUT/review/kim_anims_<k>.png

Per animation: index (hex), its steps (drawing, ticks, boxes in force, sound word, step command), frames (sum of the
ticks: a step shows `ticks` game frames, README), end (loop / hold), attack boxes or not, the moves of kim_moves.json
that play it, whether the brawler exports it (the build's Kizuna export: its frames' step addresses, its specials'
animations and effect objects), a short description (attack / movement / reaction / pose / effect-only, from its boxes,
palettes and step commands), the flags I suggest (weight, limb, weapon, launcher, knockdown, throw: from the moves that
use it and the staff inside its attack boxes). Animations that do not parse or draw nothing are listed as such.
Drawings: deduplicated (exact pixels) per sheet; one sheet per 16 animations so the page loads only what it shows.
Boxes in px at the zoom: [kind, type, x left, x right, y bottom, y top], x forward / y up from the feet; kind h body
(type < $10), a attack (>= $10 but $27 / $33), p push ($27), x other ($33)."""
import hashlib, json, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kz, export_kz as EK

CH = 5
NAME = 'kim'
MOVES_JSON = '/data/neogeo_dict/kizuna/kim_moves.json'
Z, S = EK.Z, EK.S
W, H, X0, Y0 = 640, 640, 320, 520
PER_SHEET = 16
SHEET_W = 1024
BODY_PAL, STAFF_PAL = 16, 17
FPS = 59.18
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
# reaction animations (README "Reactions"; the export's hit / knockdown / getup slots add their own)
REACT = {0x22, 0x24, 0x27, 0x2A, 0x32, 0x2B, 0x2C, 0x1B, 0xF0, 0xFE, 0xB0, 0xD8}


def pal_rgba(p):
    """absolute palette p (Kim: 16 body, 17 staff / hair, others for effects) -> 16 RGBA colours of colour set A"""
    n = EK.SETS[0] + p - 16
    if n < 0: return [(128, 128, 128, 255)] * 16
    return [(0, 0, 0, 0)] + [kz.color(kz.u16(0x70000 + 32 * n + 2 * i)) + (255,) for i in range(1, 16)]


def box_kind(t):
    if t < 0x10: return 'h'
    if t == 0x27: return 'p'
    if t == 0x33: return 'x'
    return 'a'


def box_px(b):
    l, r = sorted((round(b[2] * 4 * S), round(b[3] * 4 * S)))
    lo, hi = sorted((round(b[4] * 4 * S), round(b[5] * 4 * S)))
    return [box_kind(b[0]), b[0], l, r, lo, hi]


def cmd_text(s):
    c, a = s['cmd'], s['args']
    if not c: return None
    w = lambda k: kz.sw(a[k] << 8 | a[k + 1])
    nm = kz.CMD_NAMES.get(c, f'cmd {c}')
    if c in (5, 6): return f'move {w(0) * S:+.0f}, {w(2) * S:+.0f} px'
    if c == 9: return f'velocity {w(0) / 256 * S:+.2f}, {w(2) / 256 * S:+.2f} px/f'
    if c in (3, 4, 17, 18): return f'spawn ${a[2] << 8 | a[3]:04X} at {kz.sb(a[0]) * 2}, {kz.sb(a[1]) * 2}'
    if c in (7, 8): return f'move {kz.sb(a[0]) * 2 * S:+.0f}, {kz.sb(a[1]) * 2 * S:+.0f} px + spawn ${a[4] << 8 | a[5]:04X}'
    if c == 1: return 'stop'
    return nm + ' ' + ' '.join(str(w(k)) for k in range(0, len(a), 2))


def travel(steps):
    """horizontal travel (px at the zoom) by the steps' own commands (move / velocity / acceleration; the game's code
    adds more on some moves: jumps, specials), and whether a command lifts him (vy > 0)"""
    x = vx = ax = 0.0; up = False
    for s in steps:
        c, a = s['cmd'], s['args']
        w = lambda k: kz.sw(a[k] << 8 | a[k + 1])
        if c == 1: vx = ax = 0.0
        elif c in (5, 6): x += w(0); vx = ax = 0.0
        elif c in (7, 8): x += kz.sb(a[0]) * 2; vx = ax = 0.0
        elif c == 9: vx = w(0) / 256; up |= w(2) > 0
        elif c == 10: vx, ax = w(0) / 256, w(2) / 4096; up |= w(4) > 0
        elif c == 11: vx = w(0) / 256; up |= w(2) > 0
        elif c == 12: vx, ax = w(0) / 256, w(2) / 4096; up |= w(4) > 0
        elif c in (13, 15): ax = w(0) / 4096
        for _ in range(s['ticks']): x += vx; vx += ax
    return round(x * S), up


class Sheet:
    def __init__(self):
        self.imgs, self.cells, self.seen = [], [], {}

    def add(self, rgba, ox, oy):
        k = hashlib.md5(rgba.tobytes() + bytes(str((rgba.shape, ox, oy)), 'ascii')).digest()
        if k not in self.seen: self.seen[k] = len(self.imgs); self.imgs.append((rgba, ox, oy))
        return self.seen[k]

    def save(self, path):
        x = y = rowh = 0; place = []
        for im, ox, oy in self.imgs:
            h, w = im.shape[:2]
            if x + w > SHEET_W: x = 0; y += rowh + 1; rowh = 0
            place.append([x, y, w, h, ox, oy]); x += w + 1; rowh = max(rowh, h)
        sh = np.zeros((max(1, y + rowh), max(1, max((p[0] + p[2] for p in place), default=1)), 4), np.uint8)
        for (im, _, _), (px, py, w, h, _, _) in zip(self.imgs, place): sh[py:py + h, px:px + w] = im
        flat = sh.reshape(-1, 4); flat = np.where(flat[:, 3:] > 0, flat, 0)
        cols, inv = np.unique(flat, axis=0, return_inverse=True)
        if len(cols) <= 256:                             # exact palette image, index 0 = transparent
            im = Image.fromarray(inv.reshape(sh.shape[:2]).astype(np.uint8), 'P')
            im.putpalette([int(v) for c in cols for v in c[:3]])
            t = [int(i) for i, c in enumerate(cols) if c[3] == 0]
            im.save(path, optimize=True, transparency=t[0] if t else None)
        else: Image.fromarray(sh, 'RGBA').save(path, optimize=True)
        return place


_render = {}
def render(addr):
    """the step at addr drawn by Kizuna's renderer at zoom Z facing right -> (rgba crop, ox, oy, staff mask, pals) or
    None when it draws nothing; ox / oy = the feet point inside the crop"""
    if addr in _render: return _render[addr]
    img = np.zeros((H, W), np.uint16)
    kz.render_step_zoom(img, addr, X0, Y0, Z)
    ys, xs = np.nonzero(img & 15)
    if not len(ys): _render[addr] = None; return None
    t, b, l, r = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = img[t:b, l:r]
    lut = np.zeros((4096, 4), np.uint8)
    pals = sorted({int(p) for p in np.unique(crop[(crop & 15) > 0] >> 4)})
    for p in pals: lut[p * 16:p * 16 + 16] = pal_rgba(p)
    rgba = lut[crop]; rgba[(crop & 15) == 0] = 0
    out = (rgba, int(X0 - l), int(Y0 - t), crop, pals)
    _render[addr] = out
    return out


def staff_in_attack(rd, boxes):
    """pixels of the staff's palette (17) inside the step's attack boxes"""
    if rd is None: return 0
    _, ox, oy, crop, _ = rd
    n = 0
    for k, t, l, r, lo, hi in boxes:
        if k != 'a': continue
        x0, x1 = max(0, ox + l), max(0, min(crop.shape[1], ox + r))
        y0, y1 = max(0, oy - hi), max(0, min(crop.shape[0], oy - lo))
        if x1 > x0 and y1 > y0: n += int(((crop[y0:y1, x0:x1] >> 4) == STAFF_PAL).sum())
    return n


def exported(game):
    """anim n -> brawler names that use it, from the build's Kizuna export (examples/brawler/build/tmp_kizuna_kim)"""
    p = os.path.join(game, 'build', 'tmp_kizuna_kim', 'kof95_export.json')
    if not os.path.exists(p): print('no export at', p, '(exported = none)'); return {}
    c = json.load(open(p))['characters'][NAME]
    owner = {}                                       # step address -> animation n
    for n in range(1, kz.anim_count(CH)):
        try:
            for s in kz.parse_anim(CH << 12 | n): owner.setdefault(s['addr'], n)
        except Exception: pass
    out = {}
    put = lambda n, nm: out.setdefault(n, []).append(nm) if nm not in out.get(n, []) else None
    for mv, a in c['anims'].items():
        for st in a['steps']:
            for r in c['frames'][st['frame']]['record'].split('+'):
                n = owner.get(int(r, 16))
                if n is not None: put(n, mv)
    for sp in c['specials']:
        for n in sp['anims']: put(n, sp['input'])
        for pj in sp.get('projectiles') or []:
            if 'state' in pj: put(pj['state'], sp['input'] + ' effect')
    return out


def build(out, game=None):
    game = game or os.path.join(REPO, 'examples', 'brawler')
    M = json.load(open(MOVES_JSON))
    os.makedirs(os.path.join(out, 'review'), exist_ok=True)
    count = kz.anim_count(CH)                        # word T = 314: animations 1..313
    used, react_used = {}, {}
    for k, m in M['moves'].items():
        for i, a in enumerate(m['anims']):
            used.setdefault(int(a, 16), []).append({'key': k, 'input': m.get('input') or k, 'first': i == 0,
                                                    'hits': [h['p2_anim'] for h in m.get('hits') or []]})
    for k, r in M['reactions'].items():
        for a in r['anims']: react_used.setdefault(int(a, 16), []).append(k)
    EXP = exported(game)
    anims, sheets, cur = [], [], None
    for n in range(1, count):
        k = (n - 1) // PER_SHEET
        if k >= len(sheets): cur = Sheet(); sheets.append(cur)
        e = {'id': f'{n:X}', 'n': n, 'sheet': k}
        try:
            steps = kz.parse_anim(CH << 12 | n)
        except Exception as ex:
            e.update(status='broken', error=str(ex)[:80], steps=[], frames=0, desc='broken (does not parse)')
            anims.append(e); continue
        if steps is None:
            e.update(status='empty', steps=[], frames=0, desc='empty (no entry)'); anims.append(e); continue
        st, cur_boxes, pals, staff = [], [], set(), 0
        for s in steps:
            if s['boxes'] is not None: cur_boxes = [box_px(b) for b in s['boxes']]
            elif not s['trailer'] & 0x10 and not s['nboxes']: cur_boxes = []
            rd = render(s['addr'])
            d = -1
            if rd is not None: d = cur.add(rd[0], rd[1], rd[2]); pals |= set(rd[4])
            staff += staff_in_attack(rd, cur_boxes)
            st.append({'a': f"{s['addr']:06X}", 'd': d, 't': s['ticks'], 'b': cur_boxes,
                       's': f"{s['sound']:04X}" if s['sound'] is not None else None, 'm': cmd_text(s)})
        frames = sum(s['t'] for s in st)
        # the clip: one entry per game frame = the step it shows (ticks expanded); an animation of 0-tick steps only
        # (a still: one held step) shows each step once
        fr = [i for i, s in enumerate(st) for _ in range(s['t'])] or list(range(len(st)))
        atk = any(b[0] == 'a' for s in st for b in s['b'])
        hurt = any(b[0] == 'h' for s in st for b in s['b'])
        drawn = any(s['d'] >= 0 for s in st)
        dx, up = travel(steps)
        mv = used.get(n, [])
        ex = EXP.get(n, [])
        if not drawn: kind = 'empty'
        elif BODY_PAL not in pals and STAFF_PAL not in pals: kind = 'effect-only'
        elif atk: kind = 'attack'
        elif n in REACT or n in react_used or any(x.startswith(('hit_', 'blowback', 'knockdown', 'down', 'getup', 'trip')) for x in ex): kind = 'reaction'
        elif abs(dx) >= 16 or up: kind = 'movement'
        else: kind = 'pose'
        e.update(status='ok' if drawn else 'empty', steps=st, frames=frames, f=fr, end=steps[-1]['end'], attack=atk, body=hurt,
                 travel=dx, rises=up, kind=kind, moves=list(dict.fromkeys(u['input'] for u in mv if not u['key'].startswith('sw_'))), move_keys=[u['key'] for u in mv],
                 reactions=react_used.get(n, []), exported=ex, pals=sorted(pals),
                 sounds=sorted({s['s'] for s in st if s['s']}), staff_px=staff)
        e['suggest'] = suggest(e, mv)
        e['desc'] = desc(e)
        anims.append(e)
    names = []
    for k, sh in enumerate(sheets):
        fn = f'review/{NAME}_anims_{k}.png'
        place = sh.save(os.path.join(out, fn))
        names.append({'src': fn, 'cells': place})
    data = {'fighter': NAME, 'display': 'KIM', 'game': 'kizuna', 'source': 'Kizuna Encounter, char 5, animation table $80000[5]',
            'zoom': f'{Z:02X}', 'scale': round(S, 4), 'fps': FPS, 'count': len(anims), 'sheets': names, 'anims': anims}
    json.dump(data, open(os.path.join(out, 'review', f'{NAME}_anims.json'), 'w'), separators=(',', ':'))
    c = lambda f: sum(1 for a in anims if f(a))
    stats = {'animations': len(anims), 'rendered': c(lambda a: a['status'] == 'ok'), 'attack': c(lambda a: a.get('attack')),
             'used': c(lambda a: a.get('moves')), 'not_exported': c(lambda a: a['status'] == 'ok' and not a.get('exported')),
             'exported': c(lambda a: a.get('exported')), 'empty': c(lambda a: a['status'] == 'empty'), 'broken': c(lambda a: a['status'] == 'broken'),
             'drawings': sum(len(s.imgs) for s in sheets)}
    print('kim anim dict:', stats)
    return stats


def suggest(e, mv):
    """my guess at Bruno's flags (anims.html FLAGS): from the moves that play it (Kizuna's buttons: A / B light, C heavy,
    A / C the staff ("punch"), B kick; specials heavy), the victim reactions they caused, the staff in its attack boxes"""
    f = set()
    if not e['attack'] and not any(u['key'].startswith('throw') for u in mv): return []
    for u in mv:
        k, inp = u['key'], u['input']
        if k.startswith('throw'): f |= {'throw', 'heavy'}; continue
        sp = k.startswith(('cmd_', 'sw_'))
        btn = ''.join(ch for ch in inp.split(' ')[0] if ch in 'ABCD')
        if sp: btn = btn[-1:] if btn else ''
        if sp or btn in ('C', 'BC'): f.add('heavy')
        elif btn in ('A', 'B'): f.add('light')
        if btn in ('A', 'C'): f.add('punch')
        if btn in ('B', 'BC'): f.add('kick')
        for r in u['hits']:
            if r == 0x32: f.add('launcher')
            if r in (0x2B, 0x2C): f.add('knockdown')
    if e['attack'] and e['staff_px'] >= 40: f |= {'weapon', 'stick'}
    if 'heavy' in f and 'light' in f: f -= {'light', 'heavy'}; f.add('medium')     # played by light and heavy moves alike
    return sorted(f)


def desc(e):
    if e['status'] != 'ok': return e['status']
    t = {'attack': 'attack', 'movement': 'movement', 'reaction': 'reaction', 'pose': 'pose', 'effect-only': 'effect only', 'empty': 'empty'}[e['kind']]
    bits = [t]
    if e['travel']: bits.append(f"travels {e['travel']:+d} px")
    if e['rises']: bits.append('rises')
    if not e['frames']: bits.append('a still (0-tick step%s)' % ('s' if len(e['steps']) > 1 else ''))
    else: bits.append('loops' if e['end'] == 'loop' else 'holds its last step' if e['end'] == 'hold' else 'ends')
    return ', '.join(bits)


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
