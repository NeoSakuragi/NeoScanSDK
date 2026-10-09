#!/usr/bin/env python3
"""The fighters' ANIMATION DICTIONARIES (the Brawler Lab's anims.html?f=<fighter> and the review pages' move picker, tab
"All animations": a pick is stored as the piece "anim-<hex>"), one page and one JSON layout for every source game:

  kizuna  Kim: tools/kizuna/anim_dict.py (his Kizuna Encounter table, 313 animations at zoom $CC)
  kof96   KOF96 fighters (Krauser first, 2026-10-09): every animation of the fighter's table ($080000[id], 512 slots), one
          entry per distinct animation (slots that point at the same steps listed with it), rendered from the ROM at
          the brawler's scale (roster[].scale, 1 today) facing right
  kof98   KOF98 fighters (Robert, 2026-10-09): the same engine and the same builder through rom96.GAMES['kof98']: the
          table at bank 2 $200002[id], the fighter's own state -> slot map, palettes from bank 2 (colour set A)

    python3 tools/brawler/animdict.py OUT [GAME_DIR] [FIGHTER ...]   -> OUT/review/<fighter>_anims.json + sheets

KOF96 per animation (tools/kof96/README.md, rom96.py): its steps ([ticks][byte][frame index:16][flags:16], each shown
ticks + 1 game frames), the boxes in force ($FD: slot 0 the attack box, live on a step with flag $0100 once loaded; 1-3
the body boxes, kept until replaced), the sound it asks for ($FC 00 <index:16>: the sound mapper's index, voices.py), the
step commands ($FB x move, $FA an effect object), the game states that select it (the shared state -> slot map), the
moves that play it (normals named by state, the specials captured in our emulator, the throws), whether the brawler
exports it (the build's KOF96 export: its moves', specials', projectiles' and throws' slots), a short description, and
the flags I suggest from the data (KOF's buttons: A / B light, C / D heavy; A / C punch, B / D kick; a special's
projectile, a knockdown its capture shows on the victim, a throw).
Boxes in px: [kind, type, x left, x right, y bottom, y top], x forward / y up from the feet; kind a attack, h body."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
for p in (os.path.join(TOOLS, 'kof96'), os.path.join(TOOLS, 'kizuna'), os.path.join(TOOLS, 'neosdk')):
    if p not in sys.path: sys.path.insert(0, p)

DICTS = {'kim': 'kizuna', 'krauser': 'kof96', 'robert': 'kof98'}   # the fighters with a dictionary and its source
FPS = 59.18
PER_SHEET = 16

# KOF96 move names (the Lab's own words; KOF96 commands from the ROM's recogniser, names checked against SNK's move
# lists: snk.fandom.com "Wolfgang Krauser/Move List", 2026-10-09). Inputs as the brawler writes them.
NAMES = {'krauser': {'214A': 'Blitz Ball', '214B': 'Blitz Ball', '214C': 'Blitz Ball', '214D': 'Blitz Ball',
                     '236B': 'Leg Tomahawk', '236D': 'Leg Tomahawk', '623B': 'Kaiser Kick', '623D': 'Kaiser Kick',
                     '41236B': 'Kaiser Duel Sobat', '41236D': 'Kaiser Duel Sobat', '641236A': 'Kaiser Wave',
                     '641236C': 'Kaiser Wave', 'MAX 641236C': 'Kaiser Wave MAX'},
         # KOF98 Robert (the recogniser's inputs; names from snk.fandom.com "Robert Garcia/Move List", 2026-10-09:
         # 623K Ryuu Zanshou in KOF97-98, half circle back + K Hien Senpuu Kyaku, close half circle forward + K
         # Ryuuren Gen'ei Kyaku, f b f + K Gen'ei Kyaku, the supers Ryuuko Ranbu and Haoh Shoukou Ken; 236236 K left
         # unnamed: the wiki's list has no KOF98 entry for it)
         'robert': {**{f'{p}236{b}': 'Ryuugeki Ken' for p in ('', 'EX ') for b in 'AC'},
                    **{f'623{b}': 'Ryuuga' for b in 'AC'}, **{f'623{b}': 'Ryuu Zanshou' for b in 'BD'},
                    **{f'{p}624{b}': 'Hien Senpuu Kyaku' for p in ('', 'EX ') for b in 'BD'},
                    **{f'air 214{b}': 'Hien Ryuujin Kyaku' for b in 'BD'}, '426B': "Ryuuren Gen'ei Kyaku",
                    **{f'EX 646{b}': "Gen'ei Kyaku" for b in 'BD'},
                    **{f'{p}23624{b}': 'Ryuuko Ranbu' + (' MAX' if p else '') for p in ('', 'MAX ') for b in 'AC'},
                    **{f'{p}6426{b}': 'Haoh Shoukou Ken' + (' MAX' if p else '') for p in ('', 'MAX ') for b in 'AC'},
                    **{f'{p}236236{b}': '236236 K super' + (' MAX' if p else '') for p in ('', 'MAX ') for b in 'BD'}}}
# command normals and throws by name (the same source)
MOVE_NAMES = {'robert': {'cmd_fwd_a': 'forward A (Kouryuu Koukyaku Geri)', 'cmd_fwd_b': 'forward B (Ryuu Hanshu)',
                         'throw_c': 'throw (forward + C, Ryuuchou Kyaku)', 'throw_d': 'throw (forward + D, Kubikiri Nage)'}}
# animations no capture reaches, named from their drawings (slot -> note; SNK Wiki for the names: Kaiser Suplex =
# the leaping German suplex on a close opponent, 632146 A / C; Kaiser Inferno = cartwheels and a belly flop, a super
# left unused in KOF96 (its command 2363214 is in the recogniser's list), used in KOF98 UM)
NOTES = {'krauser': {153: 'a copy of Kaiser Wave A (151): the MAX version\'s slot?', 154: 'a copy of Kaiser Wave C (152): the MAX version\'s slot?',
                     155: 'Kaiser Wave: the wave', 156: 'Kaiser Wave: the wave\'s impact', 157: 'Kaiser Wave: the wave', 158: 'Kaiser Wave: the wave\'s impact',
                     163: 'Kaiser Inferno (unused KOF96 super): a cartwheel', 164: 'Kaiser Inferno: a cartwheel', 165: 'Kaiser Inferno: the start',
                     166: 'Kaiser Inferno: the dive', 167: 'Kaiser Inferno: a cartwheel', 168: 'Kaiser Inferno: a cartwheel', 169: 'Kaiser Inferno: a cartwheel',
                     170: 'Kaiser Inferno: the start', 171: 'Kaiser Inferno: the dive', 172: 'Kaiser Inferno: the belly flop, getting up',
                     173: 'Kaiser Inferno: the belly flop, getting up', 178: 'Kaiser Suplex (632146 A / C): the grab', 179: 'Kaiser Suplex: the jump and the suplex (the jumping command grab)',
                     180: 'Kaiser Suplex?: a tumble', 181: 'Kaiser Suplex?: one pose (its whiff?)'}}
WAVES = {'krauser': {'Kaiser Wave'}, 'robert': {'Haoh Shoukou Ken'}}                    # projectile supers whose wave the export plays from the handler
NORMAL = {'close': 'close', 'far': 'far', 'crouch': 'crouch', 'jump': 'jump', 'jump_diag': 'jump (diagonal)'}


def normal_name(k, name=None):
    """'atk_c_close' -> 'close C'; other state names: '_' -> ' '"""
    if k in MOVE_NAMES.get(name, {}): return MOVE_NAMES[name][k]
    if k.startswith('cmd_fwd_'): return 'forward ' + k[-1].upper()
    if k.startswith('atk_'):
        _, b, *w = k.split('_'); w = '_'.join(w)
        return f"{NORMAL.get(w, w)} {b.upper()}" if b != 'cd' else 'jump C+D'
    return {'body_toss': 'C+D (body toss)', 'throw_c': 'throw (forward + C)', 'throw_d': 'throw (forward + D)'}.get(k, k.replace('_', ' '))


def kof96(out, game, name):
    """a KOF96 or KOF98 fighter (DICTS[name]): the same engine, rom96.GAMES says what moved"""
    import rom96, export96
    src = DICTS[name]; k98 = src != 'kof96'
    from neogeo.sprite_decode import decode_tile, decode_color
    KZ = kizuna_dict()                                       # Kim's builder: its sheet packer and descriptions
    G = json.load(open(os.path.join(game, 'game.json')))
    ros = next(r for r in G['roster'] if r['name'] == name)
    scale = ros.get('scale', 1)
    prom, crom = rom96.load(rom96.GAMES[src]['neo']); m = rom96.Mem(prom, src)
    cid = (export96.CAST98 if k98 else export96.CAST).index(name)
    smap = [rom96.state_slot(m, cid, st) for st in range(512)] if k98 else rom96.shared_map(m)
    by_state = {s: k for k, s in (export96.MOVES98 if k98 else export96.MOVES).items()}
    for k, v in export96.CMD_NORMALS.get(src, {}).get(name, {}).items():   # KOF98 command normals (a hop: every state)
        for st in [v[0]] + [r[0] for r in (v[2] if len(v) > 2 else [])]: by_state.setdefault(st, k)
    rgba = lambda p: [(0, 0, 0, 0)] + [decode_color(c) + (255,) for c in p[1:]]
    if k98:                                                  # palette byte b -> key b - 16 (0 the body palette, 16+ the
        def pal_of(b):                                       # effects; colour set A); KOF's shared bank: its own palette
            if 16 <= b < 48: return b - 16, export96.palettes98(m, cid, [b])[0][0]
            return b, export96.pal_rom98(m, b)
        rgba_pal = {}
    else:
        rgba_pal = [rgba(p) for p in export96.palettes(m, cid)[0]]   # the block's 16 palettes (colour set A)
    base = m.u32(m.g['anims'] + cid * 4)

    # ---- what plays each slot: states (shared map), specials captured, throws; the brawler's export ----
    states = {}
    for st, sl in enumerate(smap): states.setdefault(sl, []).append(st)
    exp_p = os.path.join(game, 'build', f'tmp_{src}_{name}', 'kof95_export.json')
    ex = json.load(open(exp_p))['characters'][name] if os.path.exists(exp_p) else None
    if ex is None: print('no export at', exp_p, '(exported = none)')
    moves, exported, knock, proj_slots, throws_proj = {}, {}, set(), set(), set()
    put = lambda d, sl, v: d.setdefault(sl, []).append(v) if v not in d.get(sl, []) else None
    for sl, sts in states.items():
        for st in sts:
            k = by_state.get(st)
            if k and not k.startswith(('blowback_n',)): put(moves, sl, normal_name(k, name))
    sp_names = NAMES.get(name, {})
    if ex:
        for k, a in ex['anims'].items():
            if k == 'watch': continue
            if 'parts' in a:
                for sl, _, _ in a['parts']: put(exported, sl, k)
            elif 'slot' in a: put(exported, a['slot'], k)
        for sp in ex['specials']:
            lab = sp['input'] + (' ' + sp_names[sp['input']] if sp['input'] in sp_names else '')
            for st, d, sl in sp['states']:
                if st == 0: continue
                put(moves, sl, lab); put(exported, sl, sp['input'])
                if any(len(r) > 5 and r[5] is not None and 280 <= r[5] < 400 for r in sp['row_steps']): knock.add(sl)
            for pj in sp.get('projectiles') or []:
                sl = smap[pj['state']]; put(moves, sl, lab + ' (its projectile)'); put(exported, sl, sp['input'] + ' effect'); proj_slots.add(sl)
        for k, t in ex['throws'].items(): put(moves, t['slot'], normal_name(k, name)); put(exported, t['slot'], k)
    if ex:                                                   # a move's other version knocks down too (a whiff capture
        kn = {sp_names.get(sp['input']) for sp in ex['specials'] for st, d, sl in sp['states'] if sl in knock} - {None}   # never shows it)
        pj = ({sp_names.get(sp['input']) for sp in ex['specials'] if sp.get('projectiles')} | WAVES.get(name, set())) - {None}
        for sp in ex['specials']:
            for st, d, sl in sp['states']:
                if st and sp_names.get(sp['input']) in kn: knock.add(sl)
                if st and sp_names.get(sp['input']) in pj: throws_proj.add(sl)
    btn_of = {}                                              # slot -> the buttons of the moves that play it
    for sl, sts in states.items():
        for st in sts:
            k = by_state.get(st, '')
            if k.startswith('atk_') or k == 'body_toss': btn_of.setdefault(sl, set()).add(k.split('_')[1].upper() if k.startswith('atk_') else 'CD')
            elif k.startswith('cmd_fwd_'): btn_of.setdefault(sl, set()).add(k[-1].upper())     # KOF98 command normals
    if ex:
        for sp in ex['specials']:
            for st, d, sl in sp['states']:
                if st: btn_of.setdefault(sl, set()).add(('SUPER' if sp.get('condition') == 'super' else '') + (sp.get('button') or sp.get('input', '?')[-1:]))

    # ---- one animation: parse (with $FC sounds, $FA spawns), render each frame facing right ----
    def parse(addr):
        steps, hurt, atk, dx, snd, cmds = [], {}, None, 0, None, []
        for i in range(300):
            a = addr + 6 * i
            b0, b1 = m.u8(a), m.u8(a + 1)
            if b0 == 0xFF: return steps, 'loop'
            if b0 == 0xFE: return steps, 'hold'
            if b0 >= 0x80:
                if b0 == 0xFB: v = m.s16(a + 2); dx += v; cmds.append(f'move {-v * scale:+.0f} px')
                elif b0 == 0xFC: snd = m.u16(a + 2)
                elif b0 == 0xFA: cmds.append(f'effect ${b1:02X} at {m.s16(a + 2)}, {m.s16(a + 4)}')
                elif b0 == 0xFD:
                    slot, t = b1 & 3, b1 >> 2
                    bx = [m.u8(a + 2), m.u8(a + 3), m.u8(a + 4), m.u8(a + 5)]
                    if slot == 0: atk = (0x10 | t if t < 16 else 0x100 | t, bx)
                    else: hurt[slot] = (0x30 + slot, bx)
                continue
            fl = m.u16(a + 4)
            bxs = list(hurt.values()) + ([atk] if atk and fl & 0x100 else [])
            steps.append({'t': b0, 'fi': m.u16(a + 2), 'fl': fl, 'boxes': bxs, 'snd': snd, 'cmd': '; '.join(cmds) or None, 'a': a, 'dx': dx})
            snd, cmds, dx = None, [], 0
        raise ValueError('no terminator')

    sb = lambda v: v - 256 if v > 127 else v
    def box_px(key, b):
        x, y, w, h = sb(b[0]), sb(b[1]), b[2], b[3]
        r = lambda v: round(v * scale)
        return ['a' if key >> 4 == 1 or key >= 0x100 else 'h', key, r(-x - w), r(-x + w), r(-y - h), r(-y + h)]

    rcache = {}
    def render(fi):
        """frame record fi -> (rgba crop facing right, ox, oy = the feet inside it, palettes used) or None"""
        if fi in rcache: return rcache[fi]
        placed, used = [], set()
        for p in rom96.frame_parts(m, cid, fi):
            sd = rom96.sdef(m, cid, p['sdef'])
            if not sd['cols']: continue
            cols = sd['cols']; w, h = len(cols) * 16, len(cols[0]) * 16
            img = np.zeros((h, w), np.uint8)
            for c, col in enumerate(cols):
                for rr, t in enumerate(col):
                    if t is not None: img[rr * 16:(rr + 1) * 16, c * 16:(c + 1) * 16] = decode_tile(crom, t)
            x0 = -p['dx'] - w if p['hflip'] else p['dx']
            y0 = -p['dy'] - h if p['vflip'] else p['dy']
            if p['hflip']: img = img[:, ::-1]
            if p['vflip']: img = img[::-1, :]
            if k98:
                pal, p_ = pal_of(sd['pal'])
                if pal not in rgba_pal: rgba_pal[pal] = rgba(p_)
            else: pal = (sd['pal'] - 16) % 16 if 16 <= sd['pal'] < 112 else 0
            placed.append((x0, y0, img, pal)); used.add(pal)
        if not placed: rcache[fi] = None; return None
        mnx = min(x for x, _, _, _ in placed); mny = min(y for _, y, _, _ in placed)
        mxx = max(x + i.shape[1] for x, _, i, _ in placed); mxy = max(y + i.shape[0] for _, y, i, _ in placed)
        out = np.zeros((mxy - mny, mxx - mnx, 4), np.uint8)
        for x, y, img, pal in placed:
            lut = np.array(rgba_pal[pal], np.uint8)
            msk = img > 0
            out[y - mny:y - mny + img.shape[0], x - mnx:x - mnx + img.shape[1]][msk] = lut[img[msk]]
        ys, xs = np.nonzero(out[:, :, 3])
        if not len(ys): rcache[fi] = None; return None
        t, b, l, r = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = out[t:b, l:r][:, ::-1]                          # the ROM draws him facing left: mirrored, facing right
        ox, oy = int(r + mnx), int(-(mny + t))                # the feet (x 0, y 0) inside the mirrored crop
        if scale != 1:
            from PIL import Image
            im = Image.fromarray(np.ascontiguousarray(crop), 'RGBA')
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.NEAREST)
            crop = np.asarray(im); ox, oy = round(ox * scale), round(oy * scale)
        res = (np.ascontiguousarray(crop), ox, oy, used)
        rcache[fi] = res
        return res

    # ---- every distinct animation of the table ----
    seen = {}
    for sl in range(512):
        seen.setdefault(m.u32(base + sl * 4), []).append(sl)
    nosteps = [a for a in seen if m.u8(a) in (0xFE, 0xFF)]    # KOF98: unused slots each point at their own bare terminator
    for a in nosteps: del seen[a]                            # (no steps: not animations, left out)
    anims, sheets, cur = [], [], None
    for k, (addr, slots) in enumerate(seen.items()):
        if k // PER_SHEET >= len(sheets): cur = KZ.Sheet(); sheets.append(cur)
        sl = slots[0]
        e = {'id': f'{sl:X}', 'n': sl, 'sheet': k // PER_SHEET, 'slots': slots, 'addr': f'{addr:06X}',
             'states': sorted(st for s in slots for st in states.get(s, []))}
        try: steps, end = parse(addr)
        except Exception as x:
            e.update(status='broken', error=str(x)[:80], steps=[], frames=0, f=[], desc='broken (does not parse)', moves=[], exported=[])
            anims.append(e); continue
        st, used, travel = [], set(), 0
        sts = e['states']
        for s in steps:
            rd = render(s['fi'])
            d = -1
            if rd is not None: d = cur.add(rd[0], rd[1], rd[2]); used |= rd[3]
            st.append({'a': f"{s['a']:06X}", 'd': d, 't': s['t'] + 1, 'b': [box_px(kk, b) for kk, b in s['boxes']],
                       's': f"{s['snd']:04X}" if s['snd'] is not None else None, 'm': s['cmd'], 'fr': s['fi']})
            travel += -s['dx']
        if sts and all(26 <= x <= 36 for x in sts):            # guard: its slot-0 box is not an attack
            for s_ in st: s_['b'] = [['x'] + b[1:] if b[0] == 'a' else b for b in s_['b']]
        fr = [i for i, s in enumerate(st) for _ in range(s['t'])]
        atk = any(b[0] == 'a' for s in st for b in s['b'])
        drawn = any(s['d'] >= 0 for s in st)
        mv = [x for s in slots for x in moves.get(s, [])] + [NOTES.get(name, {})[s] for s in slots if s in NOTES.get(name, {})]
        exl = [x for s in slots for x in exported.get(s, [])]
        if not drawn: kind = 'empty'
        elif any(s in proj_slots for s in slots) or 0 not in used: kind = 'effect-only'
        elif atk: kind = 'attack'
        elif any(256 <= x < 400 for x in sts) or any(x in (66,) for x in sts): kind = 'reaction'
        elif abs(travel) >= 16 or any(x in range(1, 21) or x in range(48, 54) for x in sts): kind = 'movement'
        else: kind = 'pose'
        e.update(status='ok' if drawn else 'empty', steps=st, frames=sum(s['t'] for s in st), f=fr, end=end, attack=atk,
                 body=any(b[0] == 'h' for s in st for b in s['b']), travel=round(travel * scale), rises=False, kind=kind,
                 moves=list(dict.fromkeys(mv)), move_keys=[], reactions=[], exported=list(dict.fromkeys(exl)), pals=sorted(used),
                 sounds=sorted({s['s'] for s in st if s['s']}))
        e['suggest'] = suggest(e, slots, btn_of, knock, proj_slots | throws_proj)
        e['desc'] = KZ.desc(e) + (f", states {', '.join(map(str, sts[:6]))}{' …' if len(sts) > 6 else ''}" if sts else ', no game state selects it')
        anims.append(e)
    names = []
    for k, sh in enumerate(sheets):
        fn = f'review/{name}_anims_{k}.png'
        names.append({'src': fn, 'cells': sh.save(os.path.join(out, fn))})
    data = {'fighter': name, 'display': (ros.get('display') or name.upper()), 'game': src,
            'source': f"{src.upper()} (id {cid}, animation table ${base:06X}{' in bank 2' if k98 else ''}: 512 slots, {len(anims)} distinct animations{f', {len(nosteps)} unused slots without steps left out' if nosteps else ''})",
            'drawn': f"drawn from the ROM at the brawler's scale (×{scale}), facing right", 'zoom': None, 'scale': scale,
            'fps': FPS, 'count': len(anims), 'sheets': names, 'anims': anims}
    json.dump(data, open(os.path.join(out, 'review', f'{name}_anims.json'), 'w'), separators=(',', ':'))
    c = lambda f: sum(1 for a in anims if f(a))
    stats = {'animations': len(anims), 'rendered': c(lambda a: a['status'] == 'ok'), 'attack': c(lambda a: a.get('attack')),
             'used': c(lambda a: a.get('moves')), 'not_exported': c(lambda a: a['status'] == 'ok' and not a.get('exported')),
             'exported': c(lambda a: a.get('exported')), 'empty': c(lambda a: a['status'] == 'empty'),
             'broken': c(lambda a: a['status'] == 'broken'), 'drawings': sum(len(s.imgs) for s in sheets)}
    print(name, 'anim dict:', stats)
    return stats


def suggest(e, slots, btn_of, knock, proj_slots):
    """my guess at Bruno's flags (anims_core.js FLAGS) from KOF's buttons: A / B light, C / D heavy (a super heavy),
    A / C punch, B / D kick; C+D heavy kick; a projectile special's object, a knockdown the capture saw, a throw"""
    f = set()
    if any(s in proj_slots for s in slots): f.add('projectile')
    if any('throw' in x or 'Suplex' in x for x in e['moves']): f |= {'throw', 'heavy'}
    if not e['attack'] and not f: return []
    bs = set().union(*[btn_of.get(s, set()) for s in slots])
    if 'throw' in f and not e['attack']: bs = set()
    for b in bs:
        sup = b.startswith('SUPER'); b = b.replace('SUPER', '')
        if sup or b in ('C', 'D', 'CD'): f.add('heavy')
        elif b in ('A', 'B'): f.add('light')
        if b in ('A', 'C'): f.add('punch')
        if b in ('B', 'D', 'CD'): f.add('kick')
    if any(s in knock for s in slots): f.add('knockdown')
    if any(x in ('crouch D', 'C+D (body toss)') for x in e['moves']): f.add('knockdown')
    if 'heavy' in f and 'light' in f: f -= {'light', 'heavy'}; f.add('medium')
    return sorted(f)


def kizuna_dict():
    """tools/kizuna/anim_dict.py (Kim's builder), loaded under its own name"""
    if 'kz_anim_dict' not in sys.modules:
        import importlib.util
        sp = importlib.util.spec_from_file_location('kz_anim_dict', os.path.join(TOOLS, 'kizuna', 'anim_dict.py'))
        mod = importlib.util.module_from_spec(sp); sys.modules['kz_anim_dict'] = mod; sp.loader.exec_module(mod)
    return sys.modules['kz_anim_dict']


def build(out, game=None, names=None):
    game = game or os.path.join(REPO, 'examples', 'brawler')
    os.makedirs(os.path.join(out, 'review'), exist_ok=True)
    res = {}
    for n in names or DICTS:
        if DICTS[n] == 'kizuna': res[n] = kizuna_dict().build(out, game)
        else: res[n] = kof96(out, game, n)
    return res


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3:] or None)
