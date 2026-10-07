#!/usr/bin/env python3
"""Kim's moves against Kizuna's SCREEN, every effect object included (TODO #144: the Hienzan pillar was missing because
the captures read half of the task pool and dropped reused slots; kim_proof compared Kim's body only).

    python3 kim_effects_check.py [--scan] [EXPORT_DIR] [OUT]
        (default examples/brawler/build/tmp_kizuna_kim, /data/tmp/kim144/out; --scan re-plays Kizuna, else the
         scan cached in /data/neogeo_dict/kizuna/kim_screen.json)

1. Screen scan (our emulator, every recipe of capture_kz.py and followups_kz.py, VRAM per frame): every sprite tile on
   Kizuna's screen is attributed to what drew it, from the step each object showed (the step of the frame before: the
   game draws one frame late) and its sprite definitions' tile codes: Kim (P1's body), P2, any task of the whole pool
   $100000-$107FFF (cap_kz.new_objects or alive at the start: stage, partners, shadows). Tiles nobody's step explains
   and that were not on the screen at the start are listed as UNEXPLAINED (something drawn outside the step system).
   Per recipe: Kim's own objects (an animation of his table, char 5) that put tiles on the screen, with their steps
   and frames.
2. Against the export: every special (export_kz SPECIALS / FOLLOW: the recipe and animations each part came from) must
   draw, among its projectiles / pinned effects / script objects, every step of Kim's objects Kizuna drew during those
   frames; a normal (export_kz MOVES) must have none drawn (the export gives normals no objects). Kim's reactions
   (react_*) and other recipes are listed (the KO's flying staff BUKI is a reaction, not a move).
   Kizuna's generic hit effects (char 14 tasks: HIT SPRK, HIT MARK, RUSH ONE / TWO) are the engine's hit sparks:
   the brawler plays its own (KOF98's), listed apart.
-> OUT/effects_check.json, printed summary, 'all ok' when nothing is missing and nothing is unexplained."""
import json, os, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import kz, cap_kz as cap, capture_kz, followups_kz, export_kz

av = [a for a in sys.argv[1:] if not a.startswith('--')]
EXP = av[0] if av else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'build', 'tmp_kizuna_kim')
OUT = av[1] if len(av) > 1 else '/data/tmp/kim144/out'
SCAN = '/data/neogeo_dict/kizuna/kim_screen.json'
TMP = '/data/tmp/kim144/vram'
STAGE_PAL = 80          # palettes 80+ = the stage and HUD: their tiles scroll in drawn by the stage's own code (no
                        # step); every tile a step explains (fighters, partners, effects, shadows) is below [meas: the
                        # scan's object_palettes, checked in main]
CH = 5
_tiles = {}

def step_tiles(addr):
    """the tile codes the step at addr draws (all its parts)"""
    if addr in _tiles: return _tiles[addr]
    out = set()
    try:
        f, t, parts, defs, xy, attr, q = kz.step_at(addr)
        for w in defs:
            d = kz.sdef(w)
            if not d: continue
            out |= {c[0] for col in d['cols'] for c in col if c and c[0]}
    except Exception: pass
    _tiles[addr] = frozenset(out); return _tiles[addr]

_gen = set()
def generic_tiles():
    """tile codes of every step of Kizuna's generic effect animations (char 14: HIT SPRK, HIT MARK, RUSH ONE / TWO)"""
    if not _gen:
        for n in range(1, kz.anim_count(14)):
            try: st = kz.parse_anim(14 << 12 | n) or []
            except Exception: continue
            for x in st: _gen.update(step_tiles(x['addr']))
    return _gen

_ct = {}
def char_tiles(ch):
    """tile codes of every step of every animation of character ch"""
    if ch not in _ct:
        t = set()
        for n in range(1, kz.anim_count(ch)):
            try: st = kz.parse_anim(ch << 12 | n) or []
            except Exception: continue
            for x in st: t.update(step_tiles(x['addr']))
        _ct[ch] = t
    return _ct[ch]
def p2ch(r, sw): return cap.obj(r, 0x108200 if sw else 0x108400)['anim'] >> 12

def screen_tiles(v):
    """tile codes on the visible screen (320 x 224) from VRAM (sticky chains, shrink ignored: a column's left edge)"""
    out = {}; sx = sy = sh = 0
    for s in range(381):
        scb3 = v[0x8200 + s]; scb2 = v[0x8000 + s]
        if scb3 & 0x40: sx = (sx + (scb2 >> 8 & 15) + 1) & 0x1FF
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if not sh: continue
        x = sx if sx < 0x1F0 else sx - 0x200
        if not -16 < x < 320: continue
        top = (496 - sy) & 0x1FF
        if top >= 0x100: top -= 0x200
        vs = scb2 & 0xFF
        for r in range(min(sh, 32)):
            y = top + (r * 16 * (vs + 1) >> 8)
            if not -16 < y < 224: continue
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if code: out[code] = at >> 8
    return out

def owners(r, sw):
    """{key: step pointer} of everything that may draw: P1 / P2 (Kim is P2 in a swapped recipe) and every pool task"""
    a, b = (0x108400, 0x108200) if sw else (0x108200, 0x108400)
    out = {'kim': cap.obj(r, a)['ptr'], 'p2': cap.obj(r, b)['ptr']}
    for k in range(cap.POOL >> 8):
        o = r['pool'][k * 0x100:(k + 1) * 0x100]
        p = cap.u32(o, 0x94)
        if p: out[('obj', k, cap.u16(o, 0x40), o[0x10:0x18].decode('latin1'))] = p
    return out

def scan_recipe(mod, name):
    sw = mod is capture_kz and name in capture_kz.SWAP
    shutil.rmtree(TMP, ignore_errors=True); os.makedirs(TMP)
    rows = mod.capture(name, raw=True, vram=True, keep=TMP)
    base = set(screen_tiles(kz.vram_words(rows[0]['vram'])))
    prev = owners(rows[0], sw)
    kim_objs, unexpl, fpals, generic, victim = {}, {}, set(), {}, {}
    for i in range(1, len(rows)):
        cur = owners(rows[i], sw)
        v = kz.vram_words(rows[i]['vram'])
        on = screen_tiles(v)
        expl = {}                                        # owner -> tiles of its steps (this frame's and the one before)
        for key in set(cur) | set(prev):
            t = set()
            for p in {cur.get(key), prev.get(key)} - {None}: t |= step_tiles(p)
            expl[key] = t
        body = expl.get('kim', set()) | expl.get('p2', set())
        for code, pal in on.items():
            if code in body: continue
            ks = [k for k, t in expl.items() if k not in ('kim', 'p2') and code in t]
            kk = [k for k in ks if (k[2] >> 12) == CH]
            if kk:
                for k in kk:
                    e = kim_objs.setdefault(f'{k[2]:04X}', {'frames': [], 'steps': set(), 'slot': k[1], 'names': set()})
                    e['names'].add(k[3].strip(chr(0)).strip())
                    if not e['frames'] or e['frames'][-1] != i: e['frames'].append(i)
                    for p in {cur.get(k), prev.get(k)} - {None}:
                        if code in step_tiles(p): e['steps'].add(p)
            if kk: fpals.add(pal)                       # (Kim's objects' palettes: below the stage's)
            if not ks and code not in base and pal < STAGE_PAL and code in char_tiles(p2ch(rows[i], sw)):
                vt = victim.setdefault(pal, set()); vt.add(i)   # P2's own frames drawn by code (a victim palette effect:
                continue                                         # 421A's freeze, the Phoenix's victim; one frame each)
            if not ks and code not in base and pal < STAGE_PAL and code in generic_tiles():
                g = generic.setdefault(pal, set()); g.add(code)  # a char 14 hit effect drawn on a frame its task's
                continue                                         # pointer did not show (spawned / freed that frame)
            if not ks and code not in base and pal < STAGE_PAL:
                u = unexpl.setdefault(pal, {'tiles': set(), 'frames': set()}); u['tiles'].add(code); u['frames'].add(i)
        prev = cur
    shutil.rmtree(TMP, ignore_errors=True)
    return {'kim_objects': {k: {'frames': v['frames'], 'steps': sorted(v['steps']), 'slot': v['slot'], 'names': sorted(v['names'])} for k, v in kim_objs.items()},
            'object_palettes': sorted(fpals), 'generic_hit_tiles': {str(p): len(g) for p, g in generic.items()},
            'victim_by_code': {str(p): sorted(f) for p, f in victim.items()},
            'unexplained': {str(p): {'tiles': len(u['tiles']), 'frames': sorted(u['frames'])} for p, u in unexpl.items()}}

def scan(only=None):
    out = json.load(open(SCAN)) if only and os.path.exists(SCAN) else {}
    for mod in (capture_kz, followups_kz):
        for name in mod.RECIPES:
            key = ('cap ' if mod is capture_kz else 'fol ') + name
            if only and key not in only: continue
            out[key] = scan_recipe(mod, name)
            ko = out[key]['kim_objects']
            print(f'{key:28s} kim objects', {k: (len(v['frames']), [hex(s) for s in v['steps']]) for k, v in ko.items()},
                  '| unexplained', {p: u['tiles'] for p, u in out[key]['unexplained'].items()}, flush=True)
    json.dump(out, open(SCAN, 'w'))
    return out

def exported_steps(sp):
    """the Kizuna step addresses a special of the export draws as objects: projectiles / pinned effects, script objects"""
    recs = set()
    fr = lambda f: {int(a, 16) for a in FRAMES[f]['record'].split('+')}
    for pj in sp.get('projectiles', []):
        for r in pj['rows'] + pj.get('end', []): recs |= fr(r[0])
    for r in sp['script']:
        for o in r[3]: recs |= fr(o[0])
    return recs

def drawn_in(s, rec, anims, capf):
    """Kim's object steps the screen scan saw drawn while P1 played anims in recipe rec (frames i: VRAM i shows i - 1)"""
    fr = capf[rec]['frames']
    idx = {i + 1 for i, f in enumerate(fr) if f[0][0] in anims} | {i for i, f in enumerate(fr) if f[0][0] in anims}
    out = {}
    for k, v in s[rec if rec.startswith(('cap ', 'fol ')) else rec]['kim_objects'].items():
        fs = [f for f in v['frames'] if f in idx]
        if fs: out[k] = {'frames': len(fs), 'steps': v['steps']}
    return out

def main():
    global FRAMES
    s = scan() if '--scan' in sys.argv or not os.path.exists(SCAN) else json.load(open(SCAN))
    air = {('fol ' + A[k]) for A in export_kz.AIR.values() for k in ('whiff', 'hit', 'hit2')}   # (TODO #200: j.2B's
    if air - set(s): s = scan(sorted(air - set(s)))                                            # captures, scanned once)
    ex = json.load(open(os.path.join(EXP, 'kof95_export.json')))['characters']['kim']
    FRAMES = ex['frames']
    capj = json.load(open(export_kz.CAPTURE)); folj = json.load(open(export_kz.FOLLOWUPS))
    caps = {('cap ' + k): v for k, v in capj.items()} | {('fol ' + k): v for k, v in folj.items()}
    res = {'specials': {}, 'normals': {}, 'other': {}, 'unexplained': {}}
    ok = True
    for sp in ex['specials']:
        inp = sp['input']
        if inp in export_kz.AIR:                         # the air special (TODO #200): its whiff and hit captures
            A = export_kz.AIR[inp]; srcs = [('fol ' + A[k], (A['dive'], A['land'], A['again'])) for k in ('whiff', 'hit', 'hit2')]
        elif inp in export_kz.FOLLOW:
            srcs = [('fol ' + rec, anims) for rec, anims, _ in export_kz.FOLLOW[inp]['parts']]
        else:
            rec, _, anims = export_kz.SPECIALS[inp]; srcs = [('cap ' + rec, tuple(anims))]
        want = {}
        for rec, anims in srcs:
            for k, v in drawn_in(s, rec, anims, caps).items():
                w = want.setdefault(k, {'frames': 0, 'steps': set()}); w['frames'] += v['frames']; w['steps'] |= set(v['steps'])
        have = exported_steps(sp)
        miss = {k: sorted(hex(a) for a in v['steps'] - have) for k, v in want.items() if v['steps'] - have}
        res['specials'][inp] = {'kizuna_objects': {k: {'frames': v['frames'], 'steps': sorted(hex(a) for a in v['steps'])} for k, v in want.items()},
                                'missing': miss, 'ok': not miss}
        ok &= not miss
        print(f'special {inp:6s} kizuna draws {sorted(want)} | missing {miss or "none"}')
    for mv, src in export_kz.MOVES.items():                # normals and movement: no objects in the export
        rec = 'cap ' + (export_kz.CAP_OF.get(src[1], mv) if src[0] == 'anim' else src[1])
        if rec not in s: continue
        anims = (src[1],) if src[0] == 'anim' else tuple(src[2])
        d = drawn_in(s, rec, anims, caps)
        res['normals'][mv] = {'kizuna_objects': d, 'ok': not d}
        ok &= not d
        if d: print(f'normal {mv}: Kizuna draws {sorted(d)}: MISSING')
    used = {('fol ' + r) for F in export_kz.FOLLOW.values() for r, _, _ in F['parts']} | {('cap ' + v[0]) for v in export_kz.SPECIALS.values()} | air
    for k, v in s.items():
        if v['kim_objects'] and k not in used: res['other'][k] = sorted(v['kim_objects'])
        if v['unexplained']: res['unexplained'][k] = v['unexplained']
    op = sorted({p for v in s.values() for p in v['object_palettes']})
    res['object_palettes'] = op
    print('palettes of the tiles steps explain:', op, '(stage / HUD from', STAGE_PAL, ')')
    ok &= max(op) < STAGE_PAL
    print('other recipes drawing Kim objects (not an exported move part):', res['other'])
    print('unexplained tiles:', {k: {p: u['tiles'] for p, u in v.items()} for k, v in res['unexplained'].items()} or 'none')
    ok &= not res['unexplained']
    res['all_ok'] = ok
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, 'effects_check.json'), 'w'), indent=1, default=sorted)
    print('all ok' if ok else 'FAILURES')

if __name__ == '__main__':
    main()
