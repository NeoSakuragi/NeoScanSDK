#!/usr/bin/env python3
"""The fighters' ANIMATION DICTIONARIES (the Brawler Lab's anims.html?f=<fighter> and the review pages' move picker, tab
"All animations": a pick is stored as the piece "anim-<hex>"), one page and one JSON layout for every source game:

  kizuna  Kim: tools/kizuna/anim_dict.py (his Kizuna Encounter table, 313 animations at zoom $CC)
  kof96   KOF96 fighters (Krauser first, 2026-10-09): every animation of the fighter's table ($080000[id], 512 slots), one
          entry per distinct animation (slots that point at the same steps listed with it), rendered from the ROM at
          the brawler's scale (roster[].scale, 1 today) facing right
  kof98   KOF98 fighters (Robert, 2026-10-09): the same engine and the same builder through rom96.GAMES['kof98']: the
          table at bank 2 $200002[id], the fighter's own state -> slot map, palettes from bank 2 (colour set A)
  samsho2 SS2 fighters (Hanzo, 2026-10-10): every animation of his table, SS2's own move list (recogniser + action table),
          the specials decoded as programs (handlers_ss2), the throws (samsho2() below)

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
import json, os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
for p in (os.path.join(TOOLS, 'kof96'), os.path.join(TOOLS, 'kizuna'), os.path.join(TOOLS, 'neosdk')):
    if p not in sys.path: sys.path.insert(0, p)

DICTS = {'kim': 'kizuna', 'krauser': 'kof96', 'robert': 'kof98', 'iori': 'kof98', 'terry': 'kof98', 'ryo': 'kof98', 'ralf': 'kof98', 'yamazaki': 'kof98', 'billy': 'kof98', 'kyo': 'kof98', 'mai': 'kof98', 'yashiro': 'kof98', 'hanzo_ss2': 'samsho2'}   # the fighters with a dictionary and its source
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


# ============================================================================================ Samurai Shodown II
# SS2 fighters (Hanzo first, Character Lab 2026-10-10; tools/samsho2, study /data/neogeo_dict/samsho2/README.md): EVERY
# animation of the fighter's table ($220280[char] -> longs [anim], ss2.n_anims: Hanzo 648), rendered from the ROM by the
# decoder that equals SS2's VRAM (ss2.render_step: its layers in the $365E / $367E order, a step's bit 15 drawn turned),
# colour set A, facing right as SS2 draws P1. Ids = the animation number in hex (the sheets' $NN, the LAB special's).
# Per animation: steps (ticks + 1 frames each), the boxes in force (the $24 records: [type word: bit 15 attack]
# [left][width][top][height] x 4 px from the feet, facing right; the body list stays until a step brings another, the
# attack list is the step's own), the step sounds ($08 / $0C), the drawing offsets ($20) and events ($10), and the moves
# that play it, read from SS2's own tables: the recogniser ($6C9EA, commands_ss2) + the action table ($28310: class 0
# system actions, class 1 normals by button and stance / specials by command result, class 3 reactions, class 4 / 5 the
# throws and their victims), the specials decoded as programs (handlers_ss2.SPECIALS, SNK's names), the objects they
# spawn, the throws (handlers_ss2.throws, the Lab's too). Unarmed versions (the weapon lost: mode 1 tables, odd numbers)
# are named "(unarmed)".
SS2_CAST = {'hanzo_ss2': 2, 'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}       # roster name -> SS2 character
SS2_BTN = ['A', 'B', 'A+B', 'C', 'D', 'C+D']
SS2_SYSTEM = {1: 'walk forward', 2: 'walk back', 3: 'crouch', 4: 'crouch', 5: 'crouch', 6: 'jump up', 7: 'jump', 8: 'jump forward',
              9: 'jump back', 10: 'back dash', 11: 'forward dash', 12: 'guard', 13: 'crouching guard', 14: 'turn around',
              15: 'crouching turn', 16: 'roll', 18: 'landing', 43: 'taunt (A+C held)', 44: 'taunt (B+D held)',
              46: 'rage (POW full)', 54: 'duck (B+C)', 56: 'bow (4 1 2 3 6, unarmed)'}
SS2_REACT = {1: 'light reel', 2: 'heavy reel', 3: 'reel', 4: 'reel', 5: 'reel', 6: 'crouching reel', 7: 'crouching reel',
             8: 'crouching reel', 9: 'trip', 19: 'knockdown', 20: 'knockdown', 22: 'blown away', 23: 'blown away',
             27: 'knockdown flight', 28: 'knockdown flight', 33: 'caught by Mozu Otoshi', 34: 'caught by a grab special',
             36: 'caught by a rage move'}


def ss2_names(name, ch):
    """{animation: [what plays it]} and the special inputs / projectiles / throws, from SS2's tables"""
    import commands_ss2 as K, handlers_ss2 as HS, export_ss2 as XS
    moves, exported = {}, {}
    hname = {v: k for k, v in XS.CAST.items()}.get(ch)
    put = lambda d, a, v: d.setdefault(a, []).append(v) if v not in d.get(a, []) else None
    def acts(cls, n, label=None, mode=0):
        d = K.descriptor(ch, mode, cls, n)
        return [w & 0x3FF for _, h, w in (d['entries'] if d else []) if not w & 0x8000]
    for mode, suf in ((0, ''),):
        for b, btn in enumerate(SS2_BTN):              # class 1 actions 1-30: per button close / far, crouch, 3 jumps
            base = 1 + 5 * b
            for k, a in enumerate(acts(1, base, mode)[:2]): put(moves, a, ('close ' if k == 0 else 'far ') + btn + suf)
            for a in acts(1, base + 1, mode)[:2]: put(moves, a, 'crouch ' + btn + suf)
            for a in acts(1, base + 2, mode)[:1]: put(moves, a, 'jump ' + btn + suf)
            for a in acts(1, base + 3, mode)[:1]: put(moves, a, 'jump forward ' + btn + suf)
    for n, lab in SS2_SYSTEM.items():                 # (a list runs on into the next ones: its first animation only,
        for a in acts(0, n)[:1]: put(moves, a, lab)   # the unarmed one = it + 1, $276E8)
    for n in range(1, 40):
        for a in acts(3, n)[:1]: put(moves, a, f'reaction: {SS2_REACT.get(n, "class 3 action %d" % n)}')
    for a, lab in zip(acts(0, 30)[:3], ('run (start)', 'run', 'run (stop)')): put(moves, a, lab)
    put(moves, 0, 'idle'); put(moves, 2, 'rage idle'); put(moves, 82, 'super-deformed pose (6 4 6 4 6 4 2 + A: anim 82, the code sets it)')
    for a, v in list(moves.items()):                  # the unarmed versions: the A+1 rule ($276E8)
        if a % 2 == 0 and a + 1 not in moves: moves[a + 1] = [x + ' (unarmed)' for x in v]
    for mv, (a, f_, l_) in {**XS.MOVES, **XS.jump_moves(ch)}.items(): put(exported, a, mv)   # the game's export (its moves)
    if hname in XS.WIN: put(exported, XS.WIN[hname], 'win'); put(moves, XS.WIN[hname], 'round win')
    # specials: every version (its program's animations), the objects they spawn
    B = XS.Builder(ch)
    sps = HS.specials(B, ch, hname, versions=True) if hname in HS.SPECIALS else []
    for sp in sps:
        if sp['condition'] != 'version' and HS.SPECIALS[hname][sp['input']][1] > 1: continue   # (its versions name it)
        lab = sp['input'] + (' ' + sp['name'] if sp.get('name') else '')
        for st in sp['rom']['states']:
            a = sp['rom']['anims'][st]['ss2']; a = a[0] if isinstance(a, tuple) else a
            v = int(st.split(':')[0])
            if v != sp['rom']['vtable'].get('default', 0) and sp['rom']['vtable'].get('nvar'): continue
            put(moves, a, lab); put(exported, a, sp['input'])
        for ob in sp['rom']['objects']:
            ss = ob.get('ss2') or {}
            for a in [ss.get('anim')] + list(ss.get('anims') or []) + [ss.get('burst'), ss.get('end'), ss.get('floor')]:
                if isinstance(a, int): put(moves, a, f'{sp["input"]} (its projectile)' if ob['kind'] == 1 else f'{sp["input"]} (its effect)')
    # throws (class 4 / 5)
    names = {'throw_c': 'throw (forward + A, Slash throw B or A+B)', 'throw_d': 'throw (back + A, Kick throw D or C+D)',
             'throw_x': 'throw (on Earthquake, Earthquake throw: SS2 any throw on Earthquake or Kuroko)',
             'throw_air': 'throw (air, Kuutengeki air throw B or A+B)'}
    if hname in HS.THROWS:
        T = HS.throws(B, ch, hname, lab=True)
        if hname in HS.AIR_THROWS: T['throw_air'] = HS.throw_air(B, ch, hname, HS.AIR_THROWS[hname])
        for k, th in T.items():
            ss = th['ss2']
            for a in ([ss['anim']] if 'anim' in ss else []) + list(ss.get('anims') or []):
                put(moves, a, names.get(k, k)); put(exported, a, k)
            for r in next(iter(th['victims'].values())):
                if r[5] and r[5][0].isdigit():
                    a = int(r[5].split('.')[0])
                    if a not in (220, 222): put(moves, a, f'thrown ({names.get(k, k).split(", ")[-1].rstrip(")")}: the victim)')
    return moves, exported, sps


def samsho2(out, game, name):
    """an SS2 fighter's dictionary (DICTS[name] == 'samsho2'); the same JSON as kof96()"""
    sys.path.insert(0, os.path.join(TOOLS, 'samsho2'))
    import ss2, neo2
    KZ = kizuna_dict()
    G = json.load(open(os.path.join(game, 'game.json')))
    ros = next(r for r in G['roster'] if r['name'] == name)
    ch = SS2_CAST[name]
    pals = ss2.fighter_palettes(ch, 0)
    lut = np.zeros((4096, 4), np.uint8)
    for p in range(112):
        for k in range(16): lut[(32 + p) * 16 + k] = neo2.color(ss2.u16(0x216400 + 32 * p + 2 * k)) + (255,)
    for p in range(16):
        for k in range(16): lut[p * 16 + k] = neo2.color(ss2.u16(0x214000 + 32 * p + 2 * k)) + (255,)
    for p, pal in enumerate(pals):
        for k in range(16): lut[(16 + p) * 16 + k] = neo2.color(pal[k]) + (255,)
    lut[0::16] = 0
    W, H, X0, Y0 = 640, 480, 320, 360                 # the feet at (320, 344): SS2's screen line Y - 16
    rcache = {}
    def render(st):
        key = st['addr']
        if key in rcache: return rcache[key]
        img = np.zeros((H, W), np.uint16)
        ss2.render_step(img, st, X0, Y0, 1 if st['flags'] & 0x8000 else 0, (0, 0, 0, 0))
        ys, xs = np.nonzero(img & 15)
        if not len(ys): rcache[key] = None; return None
        t, b, l, r = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = img[t:b, l:r]
        rgba = lut[crop]
        used = {int(p) - 16 for p in np.unique(crop[(crop & 15) > 0] >> 4)}
        res = (np.ascontiguousarray(rgba), int(X0 - l), int(Y0 - 16 - t), used)
        rcache[key] = res
        return res
    sb = lambda v: v - 256 if v > 127 else v
    def box_px(w, l):
        left, wd, top, ht = sb(l >> 24) * 4, (l >> 16 & 255) * 4, sb(l >> 8 & 255) * 4, (l & 255) * 4
        return ['a' if w & 0x8000 else 'h', w, left, left + wd, -(top + ht), -top]
    moves, exported, sps = ss2_names(name, ch)
    react_anims = {a for a, v in moves.items() if any(x.startswith(('reaction', 'thrown')) for x in v)}
    btn_of = {}
    for a, v in moves.items():
        for x in v:
            m = re.match(r'^(close|far|crouch|jump(?: forward)?) (A\+B|C\+D|[ABCD])', x)
            if m: btn_of.setdefault(a, set()).add(m.group(2).replace('+', ''))
    n_an = ss2.n_anims(ch)
    seen = {}
    for a in range(n_an):
        try: ad = ss2.anim_addr(ch, a)
        except Exception: continue
        seen.setdefault(ad, []).append(a)
    anims, sheets, cur = [], [], None
    for k, (addr, slots) in enumerate(seen.items()):
        if k // PER_SHEET >= len(sheets): cur = KZ.Sheet(); sheets.append(cur)
        a0 = slots[0]
        e = {'id': f'{a0:X}', 'n': a0, 'sheet': k // PER_SHEET, 'slots': slots, 'addr': f'{addr:06X}', 'states': list(slots)}
        try: steps = ss2.parse_anim(ch, a0, 400)
        except Exception as x:
            e.update(status='broken', error=str(x)[:80], steps=[], frames=0, f=[], desc='broken (does not parse)', moves=[], exported=[])
            anims.append(e); continue
        st, body, used = [], [], set()
        for s in steps:
            b = [box_px(w, l) for w, l in s['boxes'] if not w & 0x8000]
            if b: body = b
            atk = [box_px(w, l) for w, l in s['boxes'] if w & 0x8000]
            try: rd = render(s)
            except Exception: rd = None
            d = -1
            if rd is not None: d = cur.add(rd[0], rd[1], rd[2]); used |= rd[3]
            snd = next((c[1] for c in s['cmds'] if c[0] in ('sound', 'sound_pan')), None)
            cm = '; '.join(f'move {c[1]:+d}, {-c[2]:+d} px (drawing offset)' if c[0] == 'move' else f'event ${c[1]:03X}'
                           for c in s['cmds'] if c[0] in ('move', 'event')) or None
            st.append({'a': f"{s['addr']:06X}", 'd': d, 't': s['ticks'] + 1, 'b': body + atk,
                       's': f'{snd:04X}' if snd is not None else None, 'm': cm, 'fr': s['addr']})
        fr = [i for i, s in enumerate(st) for _ in range(s['t'])]
        atk = any(b[0] == 'a' for s in st for b in s['b'])
        drawn = any(s['d'] >= 0 for s in st)
        mv = list(dict.fromkeys(x for s_ in slots for x in moves.get(s_, [])))
        exl = list(dict.fromkeys(x for s_ in slots for x in exported.get(s_, [])))
        if not drawn: kind = 'empty'
        elif not (used & set(range(8))) or any('(its projectile)' in x or '(its effect)' in x for x in mv) and not any(
                not ('(its projectile)' in x or '(its effect)' in x) for x in mv): kind = 'effect-only'
        elif atk: kind = 'attack'
        elif any(s_ in react_anims for s_ in slots): kind = 'reaction'
        elif any(x.startswith(('walk', 'jump', 'run', 'back dash', 'forward dash', 'roll', 'landing')) for x in mv): kind = 'movement'
        else: kind = 'pose'
        e.update(status='ok' if drawn else 'empty', steps=st, frames=sum(s['t'] for s in st), f=fr, end=steps[-1]['end'] or 'end',
                 attack=atk, body=any(b[0] == 'h' for s in st for b in s['b']), travel=0, rises=False, kind=kind, moves=mv,
                 move_keys=[], reactions=[], exported=exl, pals=sorted(used), sounds=sorted({s['s'] for s in st if s['s']}))
        fl = set()
        if atk:
            bs = set().union(*[btn_of.get(s_, set()) for s_ in slots])
            for b in bs:
                if b in ('A', 'B', 'AB'): fl.add('weapon')
                if b in ('A', 'B'): fl.add('light')
                if b in ('C', 'D'): fl.add('kick'); fl.add('light')
                if b in ('AB', 'CD'): fl.add('heavy')
            if any(re.match(r'^(j\.)?\d', x) for x in mv): fl.add('heavy')
            if 'heavy' in fl and 'light' in fl: fl -= {'light', 'heavy'}; fl.add('medium')
        if any(x.startswith('throw (') for x in mv): fl |= {'throw', 'heavy'}
        if any('(its projectile)' in x for x in mv): fl.add('projectile')
        e['suggest'] = sorted(fl)
        e['desc'] = KZ.desc(e) + (' (unarmed)' if mv and all('(unarmed)' in x for x in mv) else '')
        anims.append(e)
    names = []
    for k, sh in enumerate(sheets):
        fn = f'review/{name}_anims_{k}.png'
        names.append({'src': fn, 'cells': sh.save(os.path.join(out, fn))})
    data = {'fighter': name, 'display': (ros.get('display') or name.upper()), 'game': 'samsho2',
            'source': f"Samurai Shodown II (character {ch} {ss2.NAMES[ch]}, animation table $220280[{ch}] -> ${ss2.anim_table(ch):06X}: {n_an} entries, {len(anims)} distinct animations)",
            'drawn': 'drawn from the ROM at full size (SS2 shows its fighters 1:1 up close), facing right, colour set A',
            'zoom': None, 'scale': ros.get('scale', 1), 'fps': FPS, 'count': len(anims), 'sheets': names, 'anims': anims,
            'specials': [{'input': sp['input'], 'name': sp.get('name'), 'condition': sp['condition'],
                          'anims': [sp['rom']['anims'][s]['ss2'] if isinstance(sp['rom']['anims'][s]['ss2'], int) else sp['rom']['anims'][s]['ss2'][0]
                                    for s in sp['rom']['states']]} for sp in sps]}
    json.dump(data, open(os.path.join(out, 'review', f'{name}_anims.json'), 'w'), separators=(',', ':'))
    c = lambda f: sum(1 for a in anims if f(a))
    stats = {'animations': len(anims), 'rendered': c(lambda a: a['status'] == 'ok'), 'attack': c(lambda a: a.get('attack')),
             'used': c(lambda a: a.get('moves')), 'exported': c(lambda a: a.get('exported')), 'empty': c(lambda a: a['status'] == 'empty'),
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
        elif DICTS[n] == 'samsho2': res[n] = samsho2(out, game, n)
        else: res[n] = kof96(out, game, n)
    return res


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3:] or None)
