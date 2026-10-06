#!/usr/bin/env python3
"""Brawler Lab Characters tab pictures, rendered at build time (make_site.py):

  pose_candidates  every frame a fighter could hold on the select screen: the first and the last frame of each of its
                   intros / win poses / lose pose / walk-in (KOF98 / KOF99 states 336-354, KOF96 202-239: CANDIDATES),
                   exported with the same code as the game's own 'watch' pose (export96 extra moves), in colour set 0
  colour_sets      the select pose in every colour set (the ROM's frame and palettes)
  special_images   per special of the fighter's pool (export_bm.special_info): the frame where it hits (first and last
                   hit when they differ) or throws its projectile, and the projectile's first frame

Sheets are 1x RGBA PNGs (the page scales them 2x, pixelated), every picture of a sheet on a common feet line.

    python3 char_images.py GAME_DIR OUT_DIR       (writes OUT_DIR/chars/*.png, prints the index)"""
import json, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof96'))
sys.path += [os.path.join(HERE, '..', '..', d) for d in ('samsho4', 'whp', 'kizuna', 'doubledr')]
from move_images import Rom, place, colours

CANDIDATES = {'kof96': range(202, 240), 'kof98': range(336, 355), 'kof99': range(336, 355),
              'samsho4': [*range(119, 127), *range(129, 150)], 'whp': [0, 1, *range(32, 64)],   # SS4: intros, taunts, win poses (140 the sheathing; 127 / 128 only the sword: left out); WHP: $00 / $26 win + intro, $22 back view, the poses around them
              'kizuna': [0x21, *range(0x34, 0x3A), 0x80, 0xA0],   # Kizuna (Kim's numbering): the taunt $21, $34-$39 ($37 the ROM's select pose), win $80, idle $A0
              'doubledr': [0, *range(99, 110)]}   # Double Dragon: idle 0, the win poses (Billy 100, the transformed 99), the one-frame poses 101-109


def sheet(pics, path, gap=4):
    """pics [(key, rgba, ox, oy)] -> one PNG, every picture on a common feet line; -> {key: [x, w]}, height"""
    up = max(p[3] for p in pics); down = max(p[1].shape[0] - p[3] for p in pics)
    W = sum(p[1].shape[1] + gap for p in pics); out = np.zeros((up + down, W, 4), np.uint8); x = 0; idx = {}
    for key, img, ox, oy in pics:
        out[up - oy:up - oy + img.shape[0], x:x + img.shape[1]] = img
        idx[key] = [x, img.shape[1]]; x += img.shape[1] + gap
    Image.fromarray(out, 'RGBA').save(path, optimize=True)
    return idx, up + down


def _states(game, name, states):
    """the candidate states this fighter has: {state: number of steps} (export96's own state -> animation lookup; SS4 /
    WHP: the animation numbers themselves, their exporters' own step lists)"""
    if game == 'samsho4':
        import export_ss4, ss4
        return {a: n for a in states if (n := len(ss4.steps_of(export_ss4.CAST[name], a)))}
    if game == 'whp':
        import export_whp
        return {a: n for a in states if (n := len(export_whp.drawn_steps(export_whp.CAST[name], a)))}
    if game == 'kizuna':
        import export_kz
        export_kz.setup(name)
        return {a: n for a in states if (n := len(export_kz.boxes_in_force(a)))}
    if game == 'doubledr':
        import dd
        dd.load()
        return {a: n for a in states if (n := len(dd.steps(__import__('export_dd').CAST[name], a)[1]))}
    import export96, rom96
    prom, crom = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    k98 = game in ('kof97', 'kof98', 'kof99')
    cast = {'kof97': export96.CAST97, 'kof98': export96.CAST98, 'kof99': export96.CAST99}.get(game, export96.CAST)
    mp = None if k98 else rom96.shared_map(m)
    cid = cast.index(name); have = {}
    for st in states:
        try:
            slot = rom96.state_slot(m, cid, st) if k98 else mp[st]
            steps, mode = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
            if steps: have[st] = len(steps)
        except Exception: continue
    return have


def _c_data(tile_base, tiles):
    """an exporter's tiles (128 bytes each, numbered from tile_base) -> the interleaved C data Rom.tile reads"""
    return np.frombuffer(bytes(128 * tile_base) + b''.join(tiles), np.uint8).copy()


def _held_kz(name, want):
    """Kizuna: each wanted (animation, step) as export_kz's roster watch pose is built (its Builder, zoomed frames),
    colour A -> ({anims: {key: {steps: [{frame}]}}, frames, block_palettes: [set 0]}, C data)"""
    import export_kz as E
    E.setup(name); B = E.Builder(); anims = {}
    for key, (a, k) in want.items():
        st = E.boxes_in_force(a); k = k if k >= 0 else len(st) - 1
        anims[key] = {'steps': [{'frame': B.frame(st[k][0]['addr'])}]}
    sets = [[[0] + E.rom_palette(E.SETS[0] + p - 16)[1:] for p in B.pals]]
    return {'anims': anims, 'frames': B.frames, 'block_palettes': sets}, _c_data(E.TILE_BASE, B.tiles)


def _held_dd(name, want):
    """Double Dragon: each wanted (animation, step) as export_dd's roster watch pose is built, colour set A"""
    import export_dd as E, dd
    dd.load(); ch = E.CAST[name]; B = E.Builder(ch); pr = E.palram(); anims = {}
    for key, (a, k) in want.items():
        st = dd.steps(ch, a)[1]; k = k if k >= 0 else len(st) - 1
        anims[key] = {'steps': [{'frame': B.frame(st[k]['def_'])}]}
    slot = lambda key: E.BODY[ch][0] if key == 'body' else E.FORM_PAL[ch][0] if key == 'form' else key
    sets = [[[0] + pr[16 * slot(key) + 1:16 * slot(key) + 16] for key in B.pals]]
    return {'anims': anims, 'frames': B.frames, 'block_palettes': sets}, _c_data(E.TILE_BASE, B.tiles)


HELD = {'kizuna': _held_kz, 'doubledr': _held_dd}


def pose_candidates(roster, out, tmp):
    """roster: game.json's roster -> {fighter: {sheet, h, tiles: [{x, w, poses: [[state, step]...]}], current: tile}}"""
    import export96, export_ss4, export_whp
    os.makedirs(os.path.join(out, 'chars'), exist_ok=True)
    index = {}
    for r in roster:
        game, name = r['bank'].split(':'); rn = r['name']             # bank fighter (the exporter's), roster name (doubledr:billy = billy_lee)
        if game not in CANDIDATES: continue                       # no candidate list for this bank: no pose picker
        have = _states(game, name, CANDIDATES[game])
        cur = (r['watch']['frame'], r['watch']['step'])
        want = {}
        for st, n in have.items():
            want[f's{st}_0'] = (st, 0); want[f's{st}_-1'] = (st, -1)
        if cur[0] in have: want[f's{cur[0]}_{cur[1]}'] = cur        # a held step that is neither first nor last
        if game in HELD: ch, cr = HELD[game](name, want)               # Kizuna / DD: their exporters' builders directly
        else:
            if game == 'samsho4': ex = export_ss4.export([name], os.path.join(tmp, name), only=set(), extra={name: want})
            elif game == 'whp': ex = export_whp.export([name], os.path.join(tmp, name), only=set(), extra={name: want})
            else: ex = export96.export([name], os.path.join(tmp, name), game, only=set(), extra={name: want})
            ch = ex['characters'][name]
            c1 = np.frombuffer(open(os.path.join(tmp, name, 'kof95_c1.bin'), 'rb').read(), np.uint8)
            c2 = np.frombuffer(open(os.path.join(tmp, name, 'kof95_c2.bin'), 'rb').read(), np.uint8)
            cr = np.empty(len(c1) * 2, np.uint8); cr[0::2] = c1; cr[1::2] = c2
        rom = Rom.__new__(Rom); rom.c = cr                           # its tile decoder over the export's own C data
        pals = [w for p in ch['block_palettes'][0] for w in p]
        tiles, by_frame, pics = [], {}, []
        for key, (st, step) in sorted(want.items(), key=lambda kv: (kv[1][0], kv[1][1] if kv[1][1] >= 0 else 999)):
            a = ch['anims'].get(key)
            if not a: continue
            fi = a['steps'][0]['frame']
            fr = ch['frames'][fi]
            # the same state, last step given as its index: -1 when it is the last (game.json's own notation)
            pose = [st, -1 if step == have[st] - 1 else step]
            if fi in by_frame:
                if pose not in tiles[by_frame[fi]]['poses']: tiles[by_frame[fi]]['poses'].append(pose)
                continue
            res = place([(p['dx'], p['dy'], p['hflip'], p['vflip'], p.get('pal', 0), p['tiles']) for p in fr['parts']], rom.tile)
            if res is None: continue
            by_frame[fi] = len(tiles); tiles.append({'poses': [pose], 'frame': fr.get('record')})
            pics.append((len(tiles) - 1, colours(res[0], pals), res[1], res[2]))
        idx, H = sheet(pics, os.path.join(out, 'chars', f'pose_{rn}.png'))
        for k, t in enumerate(tiles): t['x'], t['w'] = idx[k]
        norm = [cur[0], -1 if cur[0] in have and cur[1] in (-1, have[cur[0]] - 1) else cur[1]]
        curk = next((k for k, t in enumerate(tiles) if norm in t['poses']), None)
        index[rn] = {'sheet': f'chars/pose_{rn}.png', 'h': H, 'tiles': tiles, 'current': curk, 'states': have}
    return index


def colour_sets(game_dir, out, names):
    """the ROM's select pose ('watch', its last step) in every colour set -> {fighter: {sheet, h, sets: [[x, w]...]}}"""
    rom = Rom(os.path.join(game_dir, 'build')); index = {}
    for name in names:
        ch = rom.chars[name]; npal, nsets, tile_hi = ch[0], ch[1], rom.tile_hi[name]
        pals = [int(v) for v in __import__('move_images')._nums(rom.arr(f'{name}_pals'))]
        steps = __import__('re').findall(r'\{(\d+), (\d+), (\d+), \{', rom.arr(f'{name}_watch'))
        r = rom.frame_index(name, int(steps[-1][0]), tile_hi)
        pics = [(s, colours(r[0], pals[s * npal * 16:(s + 1) * npal * 16]), r[1], r[2]) for s in range(nsets)]
        idx, H = sheet(pics, os.path.join(out, 'chars', f'sets_{name}.png'))
        index[name] = {'sheet': f'chars/sets_{name}.png', 'h': H, 'sets': [idx[s] for s in range(nsets)]}
    return index


def special_images(game_dir, out, fighters):
    """fighters: chainlab.json's fighters (with 'pool') -> {fighter: {sheet, h, specials: [[[x, w], ...] per special]}}"""
    rom = Rom(os.path.join(game_dir, 'build')); index = {}
    for f in fighters:
        name = f['name']; ch = rom.chars[name]; npal, tile_hi = ch[0], rom.tile_hi[name]
        pals = [int(v) for v in __import__('move_images')._nums(rom.arr(f'{name}_pals'))][:npal * 16]
        pics, per = [], []
        for k, sp in enumerate(f['pool']):
            frames = [sp['pose']]
            if sp['hits'] and sp['hits'][-1][2] != sp['pose']: frames.append(sp['hits'][-1][2])
            if sp['proj']: frames.append(sp['proj']['frame'])
            keys = []
            for j, fi in enumerate(frames):
                r = rom.frame(name, fi, tile_hi, pals)
                if r: pics.append(((k, j), *r)); keys.append((k, j))
            per.append(keys)
        if not pics: continue
        idx, H = sheet(pics, os.path.join(out, 'chars', f'spec_{name}.png'))
        index[name] = {'sheet': f'chars/spec_{name}.png', 'h': H, 'specials': [[idx[q] for q in keys] for keys in per]}
    return index


if __name__ == '__main__':
    game, out = sys.argv[1], sys.argv[2]
    G = json.load(open(os.path.join(game, 'game.json')))
    lab = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    os.makedirs(os.path.join(out, 'chars'), exist_ok=True)
    pc = pose_candidates(G['roster'], out, os.path.join(out, 'tmp_poses'))
    for n, v in pc.items(): print(n, len(v['tiles']), 'pose tiles, current', v['current'], v['tiles'][v['current']]['poses'] if v['current'] is not None else None)
    print(json.dumps({n: v['sets'] for n, v in colour_sets(game, out, [r['name'] for r in G['roster']]).items()})[:200])
    print(json.dumps({n: len(v['specials']) for n, v in special_images(game, out, lab['fighters']).items()}))
