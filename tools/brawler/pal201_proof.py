#!/usr/bin/env python3
"""TODO #201 proofs (the fighter export's palette packer, pal_pack.py: KOF98 Rugal's 11 palettes folded into the 8 the
game loads, the exact colours).

    python3 pal201_proof.py counts BASE NEW [OUT]     every roster fighter: palettes its frames use, slots before
                                                      (TODO #198's identical-colour merge) / after (pal_pack); -> OUT/counts.json
    python3 pal201_proof.py pixels BASE NEW [OUT]     every exported frame of every fighter drawn from the game's own data
                                                      (build/bm_chars.c parts + palettes, bm_c1 / c2 tiles), every colour
                                                      set, BASE vs NEW: the same colour on every pixel (a part's slot past
                                                      MAX_PALS drawn with its own table entry, as the data says); NEW: every
                                                      part's slot < MAX_PALS; -> OUT/pixels.json
    python3 pal201_proof.py measure [OUT]             KOF98 in our emulator: palette RAM with P1 = Rugal in colour sets A-D
                                                      (the team record's set bytes poked with the swap, as specials96.prep
                                                      loads a fighter) and in the EX state c36x; -> OUT/kof98_rugal_palram.json
    python3 pal201_proof.py kof BASE NEW [OUT]        Rugal's frames that used slots 8-10 (BASE): every pixel of the NEW
                                                      build's data against KOF98's colour (the export's pens + palette
                                                      byte, KOF98's palette RAM from `measure`), every colour set;
                                                      -> OUT/kof.json, OUT/kof_<frame>.png
    python3 pal201_proof.py game BASE_GAME [OUT]      in the game (harness.py on examples/brawler's build, an enemy 50 px in
                                                      front: the effects play on the hit): Rugal in each colour set (A-D at the select) plays
                                                      the fury (D, 23624C) and its MAX (down+D) (624A, the other move whose
                                                      export lists slot-8 frames, never shows them as the brawler plays
                                                      it: covered by `pixels` / `kof`): on each
                                                      frame showing one of the frames that had a part past slot 7, the
                                                      parts' slots < 8 and palette RAM (his palbase + slot) = the build's
                                                      palettes (which `kof` proves = KOF98's colours); the same on
                                                      BASE_GAME (a game dir: build/ + brawler.neo of the build before:
                                                      slots 8+ = the next fighter's palettes); screenshots before | this
                                                      build -> OUT/game_base.json, OUT/game_new.json, OUT/game_sheet.png

BASE / NEW = build directories (examples/brawler/build of the build before / of this one). Default OUT /data/tmp/pal201/out."""
import json, os, re, struct, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import head_point as HP
import pal_pack as PP

OUT = '/data/tmp/pal201/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
MAX_PALS = 8
CANVAS, CX, CY = 1024, 512, 700                          # a frame's picture: the feet at (CX, CY)

# ---- the game's data -------------------------------------------------------------------------------------------------
class Data:
    """a build's fighters as the ROM holds them: per fighter its frames (parts: dx, dy, cols, rows, hflip, vflip, slot,
    tile numbers) and palettes [set][slot][16]"""
    def __init__(self, build):
        s = open(os.path.join(build, 'bm_chars.c')).read()
        c1 = open(os.path.join(build, 'bm_c1.bin'), 'rb').read(); c2 = open(os.path.join(build, 'bm_c2.bin'), 'rb').read()
        self.reg = bytearray(len(c1) * 2); self.reg[0::2] = c1; self.reg[1::2] = c2
        self.chars = {}
        for a, b, name in re.findall(r'\{"[^"]+", (\d+), (\d+), (\w+)_pals, \w+_frames', s):
            npal, nsets = int(a), int(b)
            pals = [int(v, 16) for v in re.search(r'static const uint16_t %s_pals\[\] = \{(.*?)\};' % name, s).group(1).split(', ')]
            pals = [[pals[(st * npal + k) * 16:(st * npal + k + 1) * 16] for k in range(npal)] for st in range(nsets)]
            hi = int(re.search(r'%s_specials, (\d+), \d+, %s_routes' % (name, name), s).group(1))
            parts_src = dict(re.findall(r'static const uint16_t (%s_f\d+_p\d+)\[\] = \{(.*?)\};' % name, s))
            nfr = len(re.findall(r'\{\d+, \d+, %s_f\d+\}' % name, re.search(r'static const bframe_t %s_frames\[\] = \{(.*?)\};' % name, s).group(1)))
            frames = []
            body_of = dict(re.findall(r'static const bpart_t %s_f(\d+)\[\] = \{(.*?)\};' % name, s))
            for fi in range(nfr):
                parts = []
                for dx, dy, cols, rows, hf, vf, slot, arr in re.findall(r'\{(-?\d+), (-?\d+), (\d+), (\d+), (\d), (\d), (\d+), (\w+)\}', body_of.get(str(fi), '')):
                    cols, rows = int(cols), int(rows)
                    flat = [int(v) for v in parts_src[arr].split(', ')][:cols * rows]
                    t = [[(v | hi << 16) if v else 0 for v in flat[c * rows:(c + 1) * rows]] for c in range(cols)]
                    parts.append({'dx': int(dx), 'dy': int(dy), 'hflip': int(hf), 'vflip': int(vf), 'pal': int(slot), 'tiles': t})
                frames.append({'parts': parts})
            self.chars[name] = {'npal': npal, 'nsets': nsets, 'pals': pals, 'frames': frames}

def draw(ch, reg, fi, cache):
    """frame fi -> (pens, slots) as int16 pictures (pen 0 = nothing), parts drawn in order (a later one on top); the
    head_point.pens placement (= draw.s)"""
    pen = np.zeros((CANVAS, CANVAS), np.int16); slot = np.zeros((CANVAS, CANVAS), np.int16)
    for p in ch['frames'][fi]['parts']:
        rows = len(p['tiles'][0]); top = -p['dy'] - rows * 16 if p['vflip'] else p['dy']
        for c, col in enumerate(p['tiles']):
            for r, t in enumerate(col):
                if not t: continue
                if t not in cache: cache[t] = HP.tile(reg, t)
                tp = cache[t]
                if p['hflip']: tp = tp[:, ::-1]
                rr = r
                if p['vflip']: tp = tp[::-1]; rr = rows - 1 - r
                y, x = CY + top + 16 * rr, CX + p['dx'] + 16 * c
                assert 0 <= y <= CANVAS - 16 and 0 <= x <= CANVAS - 16, (fi, x, y)
                m = tp > 0
                pen[y:y + 16, x:x + 16][m] = tp[m]; slot[y:y + 16, x:x + 16][m] = p['pal']
    return pen, slot

def colours(pals, pen, slot):
    """the picture's colours (-1 = transparent) from palettes [slot][16]"""
    lut = np.array([row for row in pals], np.int32)          # [slot][16]
    out = lut[slot, pen]; out[pen == 0] = -1
    return out

# ---- counts / pixels -------------------------------------------------------------------------------------------------
def export_counts(build):
    """per fighter (roster name) its export's palettes used and identical-colour slots, from build/tmp_* (the exports
    as export_bm read them: NEW's are the packed ones) and bm_chars.c's npal"""
    roster = {r['bank']: r['name'] for r in json.load(open(os.path.join(build, 'roster.json')))}
    s = open(os.path.join(build, 'bm_chars.c')).read()
    npal = {n: int(a) for a, n in re.findall(r'\{"[^"]+", (\d+), \d+, (\w+)_pals', s)}
    out = {}
    for spec, name in roster.items():
        game, bank = spec.split(':'); tmp = os.path.join(build, f'tmp_{game}_{bank}')
        ch = json.load(open(os.path.join(tmp, 'kof95_export.json')))['characters'][bank]
        used = sorted({p.get('pal', 0) for fr in ch['frames'] for p in fr['parts']})
        out[name] = {'bank': spec, 'used': len(used), 'slots': len(PP.slots(used, ch['block_palettes'])), 'npal': npal[name]}
    return out

def counts(base, new, out):
    b, n = export_counts(base), export_counts(new)
    rows = [{'fighter': k, 'bank': b[k]['bank'], 'palettes_used': b[k]['used'], 'before': b[k]['npal'], 'after': n[k]['npal'],
             'over_before': b[k]['npal'] > MAX_PALS, 'over_after': n[k]['npal'] > MAX_PALS} for k in b]
    print(f'{"fighter":12s} {"bank":22s} used before after')
    for r in rows: print(f'{r["fighter"]:12s} {r["bank"]:22s} {r["palettes_used"]:4d} {r["before"]:6d} {r["after"]:5d}' + ('  <- over' if r['over_after'] else ''))
    print('over 8 after:', [r['fighter'] for r in rows if r['over_after']] or 'none')
    json.dump(rows, open(os.path.join(out, 'counts.json'), 'w'), indent=1)

def pixels(base, new, out):
    B, N = Data(base), Data(new)
    res, bad = {}, []
    for name in B.chars:
        cb, cn = B.chars[name], N.chars[name]
        assert len(cb['frames']) == len(cn['frames']), name
        same = 0; over = 0; px = 0; cacheb, cachen = {}, {}
        for fi in range(len(cb['frames'])):
            pb, sb = draw(cb, B.reg, fi, cacheb); pn, sn = draw(cn, N.reg, fi, cachen)
            if any(p['pal'] >= MAX_PALS for p in cn['frames'][fi]['parts']): over += 1
            ok = True
            for st in range(cb['nsets']):
                a, c = colours(cb['pals'][st], pb, sb), colours(cn['pals'][st], pn, sn)
                if not np.array_equal(a, c): ok = False
            px += int((pb > 0).sum())
            if ok: same += 1
            else: bad.append((name, fi))
        res[name] = {'frames': len(cb['frames']), 'identical': same, 'sets': cb['nsets'], 'frames_past_slot7_new': over,
                     'pixels': px, 'slots_before': cb['npal'], 'slots_after': cn['npal']}
        print(f'{name:12s} frames {len(cb["frames"]):4d} identical {same:4d} (x{cb["nsets"]} sets, {px} px), slots {cb["npal"]} -> {cn["npal"]}, parts past slot 7: {over}', flush=True)
    total = sum(r['frames'] for r in res.values()); ok = sum(r['identical'] for r in res.values())
    print(f'all: {ok} / {total} frames identical in every colour set; mismatches {bad[:20]}')
    json.dump({'fighters': res, 'frames': total, 'identical': ok, 'mismatch': bad}, open(os.path.join(out, 'pixels.json'), 'w'), indent=1)

# ---- KOF98 -------------------------------------------------------------------------------------------------------------
RUGAL = 36

def measure(out):
    import emu, specials96 as S
    g = emu.GAMES['kof98']; L = g['load_frames']; res = {}
    d = os.path.join(out, 'kof98'); os.makedirs(d, exist_ok=True)
    def pal_of(path):
        w = open(path, 'rb').read()
        for bk in (0, 1):
            pal = struct.unpack('>4096H', w[bk * 8192:(bk + 1) * 8192])
            if any(pal[16 * 16 + 1:16 * 16 + 16]): return {b: list(pal[b * 16:b * 16 + 16]) for b in range(16, 64)}
    for s in range(4):                                   # team record +4..6: the members' colour sets (A-D)
        p = os.path.join(d, f'set{s}.pal')
        pk = emu.swap_pokes('kof98', RUGAL) + ',' + ','.join(f'{g["team"] + 4 + k:X}={s:02X}' for k in range(3))
        s1, s2 = S.seqs('p2 20 60 L; p2 85 3 c', L + 200)
        emu.run('kof98', '/dev/null', s1, s2, [f'2:{pk}'], extra={'PALDUMP': f'{L + 150}:{p}', 'SNAPS': str(L + 150), 'SNAPDIR': d})
        res[f'set{s}'] = pal_of(p)
    p = os.path.join(d, 'c36x.pal')                      # the EX state (Omega Rugal: KOF98 EX = another character)
    emu.run('kof98', os.path.join(d, 'c36x.txt'), '30:-', '', start='c36x', extra={'PALDUMP': f'20:{p}'})
    res['ex'] = pal_of(p)
    # the fury played (Gigantic Pressure 23624C, P2 close: the pillar on the hit): palette RAM every 4th frame, the
    # effect palettes held as loaded (no palette animation)
    import rom96, romspecials98 as K
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98'); tr = K.try_for(m, RUGAL, '23624C'); S0 = K.START
    s1, s2 = S.seqs('; '.join(f'p1 {S0 + off} {n} {keys}' for off, n, keys in tr['events'] if keys), S0 + 200)
    x1h, x1l, x2h, x2l = K.PLACE['close']; fr = list(range(S0, S0 + 200, 4)); gp = os.path.join(d, 'gp.txt')
    emu.run('kof98', gp, s1, s2, [f'{S0 - 2}:108118={x1h},108119={x1l},108318={x2h},108319={x2l}'], reload=f'c{RUGAL}',
            reload_frames=[S0 - 4], extra={'PALDUMP': ','.join(map(str, fr))}, snaps=fr[9:41:4], snapdir=d)
    held = []
    for f in fr:
        w = struct.unpack('>4096H', open(f'{gp}.pal{f}', 'rb').read()[:8192])
        held.append(all(list(w[b * 16:b * 16 + 16]) == res['set0'][b] for b in range(32, 48)))
    res['gp_effects_held'] = all(held)
    print('KOF98 Gigantic Pressure: effect palettes 32-47 as loaded on all', len(fr), 'frames sampled:', all(held))
    from PIL import Image
    ims = [Image.open(os.path.join(d, f'snap_{f}.ppm')).convert('RGB') for f in fr[9:41:4]]
    sh = Image.new('RGB', (ims[0].width * 4, ims[0].height * 2))
    for i, im in enumerate(ims): sh.paste(im, ((i % 4) * im.width, (i // 4) * im.height))
    sh.save(os.path.join(out, 'kof98_gp_sheet.png'))
    json.dump(res, open(os.path.join(out, 'kof98_rugal_palram.json'), 'w'))
    for k, v in res.items():
        if isinstance(v, dict): print(k, 'palette 16:', ' '.join(f'{c:04X}' for c in v[16]))

def ex_frames(ch):
    """frames only an 'EX ...' special shows (KOF98 EX Rugal = Omega Rugal; export_bm NO_EX: never played)"""
    def ints(o):
        if isinstance(o, dict):
            for v in o.values(): yield from ints(v)
        elif isinstance(o, list):
            for v in o: yield from ints(v)
        elif isinstance(o, int): yield o
    ex, reg = set(), set()
    for sp in ch['specials']:
        fr = {x for k in ('script', 'rom', 'projectiles') if k in sp for x in ints(sp[k]) if 0 <= x < len(ch['frames'])}
        (ex if sp['input'].startswith('EX ') else reg).update(fr)
    for a in ch['anims'].values(): reg.update(s['frame'] for s in a['steps'])
    return ex - reg

def kof(base, new, out, name='rugal', bank='kof98_rugal'):
    pr = json.load(open(os.path.join(out, 'kof98_rugal_palram.json')))
    B, N = Data(base), Data(new)
    ex0 = json.load(open(os.path.join(base, f'tmp_{bank}', 'kof95_export.json')))['characters'][name]
    reg0 = PP.load_region(os.path.join(base, f'tmp_{bank}'))
    pbytes = ex0['palette_bytes']
    cb, cn = B.chars[name], N.chars[name]
    exf = ex_frames(ex0)
    want = [fi for fi, fr in enumerate(cb['frames']) if any(p['pal'] >= MAX_PALS for p in fr['parts'])]
    res, cache0, cachen = [], {}, {}
    from PIL import Image
    for fi in want:
        # KOF98's picture: the export's own tiles and pens (BASE tmp export), each part in its palette byte's colours
        pk, bk =draw({'frames': [{'parts': [dict(p, pal=pbytes[p.get('pal', 0)]) for p in ex0['frames'][fi]['parts']]}]}, reg0, 0, cache0)
        pn, sn = draw(cn, N.reg, fi, cachen)
        is_ex = fi in exf
        sets = ['ex'] if is_ex else [f'set{s}' for s in range(4)]
        r = {'frame': fi, 'omega_ex': is_ex, 'kof_bytes': sorted({pbytes[p.get('pal', 0)] for p in ex0['frames'][fi]['parts']}),
             'slots_before': sorted({p['pal'] for p in cb['frames'][fi]['parts']}), 'slots_after': sorted({p['pal'] for p in cn['frames'][fi]['parts']}),
             'pixels': int((pk > 0).sum()), 'sets': {}}
        for k, sk in enumerate(sets):
            lut = np.zeros((64, 16), np.int32)
            for b, v in pr[sk].items(): lut[int(b)] = v
            kc = lut[bk, pk]; kc[pk == 0] = -1
            st = k if not is_ex else 0
            nc = colours(cn['pals'][st], pn, sn)
            r['sets'][sk] = int((kc != nc).sum())
            if k == 0 and not is_ex and fi in want[:40:4]:
                def img(c):
                    a = np.where(c[..., None] >= 0, np.stack([((c >> 8) & 15) << 4 | ((c >> 14) & 1) << 3, ((c >> 4) & 15) << 4 | ((c >> 13) & 1) << 3,
                                                               (c & 15) << 4 | ((c >> 12) & 1) << 3], -1), 255).astype(np.uint8)
                    ys, xs = np.nonzero(pk); return Image.fromarray(a[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
                a, b = img(kc), img(nc); im = Image.new('RGB', (a.width * 2 + 8, a.height), 'white')
                im.paste(a, (0, 0)); im.paste(b, (a.width + 8, 0)); im.save(os.path.join(out, f'kof_{fi}.png'))
        r['ok'] = all(v == 0 for v in r['sets'].values())
        res.append(r)
    reg_ = [r for r in res if not r['omega_ex']]; om = [r for r in res if r['omega_ex']]
    print(f'Rugal frames that used slots 8+: {len(res)} ({len(reg_)} of his own moves, {len(om)} only in Omega Rugal\'s EX moves)')
    print(f'  his moves: {sum(r["ok"] for r in reg_)} / {len(reg_)} colour-exact vs KOF98 in all 4 colour sets '
          f'({sum(r["pixels"] for r in reg_)} px each)')
    print(f'  Omega EX frames vs KOF98 EX palette RAM: {sum(r["ok"] for r in om)} / {len(om)} exact '
          f'(bytes {sorted({b for r in om for b in r["kof_bytes"]})}: the export reads them from Rugal\'s tables)')
    json.dump(res, open(os.path.join(out, 'kof.json'), 'w'), indent=1)

# ---- in the game -------------------------------------------------------------------------------------------------------
MOVES = [('fury_23624C', 'd', 0), ('MAX_23624C', 'Dd', 0)]

def game_run(gdir, tag, out):
    """one build in its own process (one core a process): per colour set and move the frames Rugal and his objects show"""
    from harness import Brawler
    roster = [r['name'] for r in json.load(open(os.path.join(gdir, 'game.json')))['roster']]
    frames = json.load(open(os.path.join(gdir, 'build', 'bm_frames.json')))['rugal']
    D = Data(os.path.join(gdir, 'build'))
    ch = D.chars['rugal']
    b = Brawler(rom=os.path.join(gdir, "brawler.neo"), game=gdir)
    import ctypes as C
    b.core.retro_get_memory_data.restype = C.c_void_p
    def palram():
        w = (C.c_uint16 * 8192).from_address(b.core.retro_get_memory_data(104)); return [w[k] for k in range(8192)]
    res = []
    for st, button in enumerate('abcd'):
        for label, keys, _ in MOVES:
            b.pick(roster.index('rugal'), button=button, unlock=True); b.run(10)
            for i in range(1, 8): b.place(i, x=1000, z=0)
            b.place(0, x=60, z=30); b.fset(0, 'facing', 1); b.place(2, x=110, z=30); b.fset(2, 'facing', 0xFF)
            b.run(2)
            w = 0
            while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
            b.place(0, x=60, z=30); b.place(2, x=110, z=30); b.fset(0, 'meter', 300); b.fset(2, 'hp', 60)
            assert b.fget(0, 'set') == st, (b.fget(0, 'set'), st)
            pb = b.fget(0, 'palbase'); seen = []; shot = None
            for f in range(200):
                b.run(1, p1=keys if f < 4 else '')
                shown = []
                if b.fget(0, 'frame_ovr') != 0xFFFF: shown.append(b.fget(0, 'frame_ovr'))
                own = b.syms['fighters']
                for i in range(8):
                    if b.pget(i, 'state') < len(b.states) and b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'owner') == own \
                            and b.pget(i, 'frame_ovr') != 0xFFFF: shown.append(b.pget(i, 'frame_ovr'))
                hit =[fi for fi in shown if fi in OLD_SLOT8]
                if not hit: continue
                ram = palram()
                for fi in hit:
                    slots = sorted({p['pal'] for p in ch['frames'][fi]['parts']})
                    loaded = all(ram[(pb + s) * 16 + k] == ch['pals'][st][s][k] for s in slots for k in range(1, 16)) if all(s < MAX_PALS for s in slots) else False
                    seen.append({'f': f, 'frame': fi, 'slots': slots, 'palram_ok': loaded,
                                 'palram': {s: ram[(pb + s) * 16:(pb + s) * 16 + 16] for s in slots}})
                if shot is None and len(seen) >= 6:
                    shot = os.path.join(out, 'shots', f'game_{tag}_{label}_set{st}.png'); b.screenshot(shot)
            res.append({'set': st, 'move': label, 'frames_seen': sorted({s['frame'] for s in seen}), 'checks': len(seen),
                        'all_ok': bool(seen) and all(s['palram_ok'] for s in seen), 'shot': shot, 'seen': seen})
            print(tag, label, 'set', st, 'frames', sorted({s['frame'] for s in seen}), 'ok', res[-1]['all_ok'], flush=True)
    json.dump(res, open(os.path.join(out, f'game_{tag}.json'), 'w'))

OLD_SLOT8 = set()

def game(base_game, out):
    os.makedirs(os.path.join(out, 'shots'), exist_ok=True)
    for tag, gdir in (("base", base_game), ("new", GAME)):
        subprocess.run([sys.executable, os.path.abspath(__file__), '_game', gdir, tag, out], check=True)
    from PIL import Image, ImageDraw
    nb = json.load(open(os.path.join(out, 'game_base.json'))); nn = json.load(open(os.path.join(out, 'game_new.json')))
    rows = [(a, c) for a, c in zip(nb, nn) if a['shot'] and c['shot']]
    W, H = 320, 224
    im = Image.new('RGB', (2 * W + 12, len(rows) * (H + 16) + 20), 'white'); d = ImageDraw.Draw(im)
    d.text((4, 4), 'Rugal, his moves past palette slot 7: the build before (slots 8+ = the next fighter\'s colours) | this build', fill='black')
    for k, (a, c) in enumerate(rows):
        y = 20 + k * (H + 16)
        d.text((4, y), f'{a["move"]} set {a["set"]}: before', fill='black'); d.text((W + 12, y), f'this build: palette RAM = data {c["all_ok"]}', fill='black')
        im.paste(Image.open(a['shot']).convert('RGB'), (0, y + 12)); im.paste(Image.open(c['shot']).convert('RGB'), (W + 12, y + 12))
    im.save(os.path.join(out, 'game_sheet.png'))
    print('this build:', sum(r['all_ok'] for r in nn), '/', len(nn), 'moves x sets: slots < 8 and palette RAM = the data on every frame shown;',
          'before:', sum(r['all_ok'] for r in nb), '/', len(nb))

def old_slot8(base):
    """Rugal's frames that had a part past slot 7 in BASE (from its bm_chars.c)"""
    B = Data(base)
    return {fi for fi, fr in enumerate(B.chars['rugal']['frames']) if any(p['pal'] >= MAX_PALS for p in fr['parts'])}

if __name__ == '__main__':
    a = sys.argv[1:]
    cmd = a[0]
    if cmd == '_game':
        OLD_SLOT8.update(json.load(open(os.path.join(a[3], 'old_slot8.json'))))
        game_run(a[1], a[2], a[3]); sys.exit()
    if cmd == 'counts': out = a[3] if len(a) > 3 else OUT; os.makedirs(out, exist_ok=True); counts(a[1], a[2], out)
    elif cmd == 'pixels': out = a[3] if len(a) > 3 else OUT; os.makedirs(out, exist_ok=True); pixels(a[1], a[2], out)
    elif cmd == 'measure': out = a[1] if len(a) > 1 else OUT; os.makedirs(out, exist_ok=True); measure(out)
    elif cmd == 'kof': out = a[3] if len(a) > 3 else OUT; os.makedirs(out, exist_ok=True); kof(a[1], a[2], out)
    elif cmd == 'game':
        out = a[2] if len(a) > 2 else OUT; os.makedirs(out, exist_ok=True)
        base_build = os.path.join(a[1], "build")
        json.dump(sorted(old_slot8(base_build)), open(os.path.join(out, 'old_slot8.json'), 'w'))
        game(a[1], out)
    else: print(__doc__)
