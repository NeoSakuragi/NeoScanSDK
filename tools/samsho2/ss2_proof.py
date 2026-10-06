#!/usr/bin/env python3
"""Haohmaru and Genjuro (Samurai Shodown II, tools/samsho2/export_ss2.py) in the brawler, proved in the harness
(tools/brawler/harness.py: the game's ROM on the Geolith core), each picked on the select screen (the real path).

    python3 ss2_proof.py [OUTDIR] [haohmaru genjuro]        (default /data/tmp/ss2/out)

1. Frame check vs SS2, both facings: every exported frame of the fighter shown through the game's renderer
   (fighter_t.frame_ovr in the Chain Lab training, lab req 1) and read back from VRAM (P1's sprite block, the brawler's C
   ROM tiles, pen indices with the palettes mapped back to SS2's numbers), against ss2.render_step of the step it came
   from (the study's renderer = SS2's VRAM pixel for pixel), mirrored when he faces left; a contact sheet of his moves
   per facing -> frames_<name>.json, moves_<name>_right.png / _left.png.
2. Specials sheets SS2 vs brawler: each slot (C + the stick) and the fury (D) played with the pad against the standing
   dummy 120 px away: the brawler's frames every 4th, under them SS2's frames of the same command (its capture
   moves/CC.json: the display list rendered by the decoder); hits on the dummy, projectile entities -> specials_<name>.png,
   specials_<name>.json.
3. #148's acceptance (Haohmaru): the fury is SS2's weapon-flipping technique (bchar_t.fury = the WFT); the 623 crescent
   stays with him (its entity's place minus his, every frame it lives, = its rows: pinned); he throws (walk-in grab,
   forward+A: the dummy thrown) -> acceptance.json."""
import json, os, re, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import ss2, neo2 as N
from harness import Brawler
from PIL import Image, ImageDraw
import ctypes as C

OUT = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith('/') else '/data/tmp/ss2/out'
NAMES = [a for a in sys.argv[1:] if not a.startswith('/')] or ['haohmaru', 'genjuro', 'kuroko']
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
CHAR = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}
CAPS = '/data/neogeo_dict/samsho2/moves'

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

def tiles_of(rom):
    import struct
    d = open(rom, 'rb').read(); sizes = struct.unpack('<6I', d[4:0x1C]); off = 0x1000 + sum(sizes[:5])
    return d[off:off + sizes[5]]

_pc = {}
def pens(crom, code):
    if code in _pc: return _pc[code]
    b = np.frombuffer(crom, np.uint8, 128, code * 128).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    _pc[code] = np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint16); return _pc[code]

def block_image(b, vram, crom, palmap, who=0, proj=False):
    """a sprite block from VRAM -> pen-index image with SS2's palette numbers (palmap: block palette -> SS2 palette)"""
    get = b.pget if proj else b.fget
    spr, n, pb = get(who, 'spr'), get(who, 'ncols'), get(who, 'palbase')
    img = np.zeros((544, 544), np.uint16); sx = sy = sh = 0
    for s in range(spr, spr + n):
        scb3 = vram[0x8200 + s]
        if scb3 & 0x40: sx += 16
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, vram[0x8400 + s] >> 7
        top = (496 - sy) & 0x1FF
        for r in range(min(sh, 32)):
            code = vram[s * 64 + 2 * r]; at = vram[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if not code: continue
            t = pens(crom, code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            p = (at >> 8) - pb
            if not 0 <= p < len(palmap): continue
            y, x = (top + r * 16 + 16) & 0x1FF, (sx + 96) & 0x1FF
            sub = img[y:y + 16, x:x + 16]
            img[y:y + 16, x:x + 16] = np.where(t > 0, palmap[p] * 16 + t, sub)
    return img

def unwrap(img):
    """the block read back from VRAM lives on the 512-line circle (a frame reaching above the screen wraps): rolled so
    the longest empty run of lines is at the bottom"""
    occ = img.any(axis=1)[:512]
    if occ.all() or not occ.any(): return img
    best = (0, 0); run = 0
    for i in range(1024):
        if not occ[i % 512]:
            run += 1
            if run > best[0]: best = (run, i % 512)
        else: run = 0
    return np.roll(img[:512], -(best[1] + 1), axis=0)

def crop_nz(img):
    ys, xs = np.nonzero(img)
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else img[:0, :0]

def ref_frame(ch, fr):
    """SS2's own drawing of the step a frame came from (ss2.render_step: the game's VRAM), its $20 offset applied"""
    s = fr['ss2']; img = np.zeros((1024, 1024), np.uint16)
    mx, my = s['move']; X, Y = 512 + mx, 700 + my
    order = ss2.ORDER[bool(s['flags'] & 0x4000)][len(s['layers']) - 1]
    for li in order:                                  # render_step's drawing without the screen's 512-line wrap
        w = s['layers'][li]; flip = w >> 15
        sd = ss2.sprite_def(w & 0x7FFF); xo, yo = ss2.place(w & 0x7FFF); _, cells = ss2.sprite_cells(w & 0x7FFF)
        left = X - xo if not flip else X - sd['cols'] * 16 + xo
        ss2.blit(img, cells, left, Y - 16 - yo, flip, 0)
    if s['flags'] & 0x8000: img = img[:, ::-1]        # the step drawn turned (flags bit 15: SS2's $35E8 eori #1 on the
    return img                                        # entry's flip), about its feet: the export's frame(mirror)

def colour_img(img, ch):
    return Image.fromarray(ss2.colorize(img, ss2.fighter_palettes(ch, 0)))

def ss2_strip(ch, cap, every=4, n=None, W=160, H=112):
    """SS2's frames of a capture: P1's display entries (palette add < 8: P2 adds 8; shadows / HUD (priority 18 / 34 / 66) left
    out) rendered by the decoder, from the frame its action starts"""
    rows = cap['rows']; s0 = next(i for i, r in enumerate(rows) if r['p1']['cls'] == 1 or r['p1']['cls'] == 4)
    e0 = next((i for i in range(s0, len(rows)) if rows[i]['p1']['cls'] == 0), len(rows))
    cells = []
    for i in range(s0, min(len(rows), e0 + 4, s0 + (n or 999) * every), every):
        img = np.zeros((224, 320), np.uint16)
        for d, x, y, flip, pal, prio in rows[i]['dl']:
            if pal >= 8 or prio in (18, 34, 66): continue
            try:
                sd, left, top = ss2.layer_box(d, x, y, flip); _, cells_ = ss2.sprite_cells(d & 0x7FFF)
                tmp = np.zeros_like(img); ss2.blit(tmp, cells_, left, top, flip, pal)
                m = tmp > 0; img[m] = tmp[m]
            except Exception: pass
        cells.append(colour_img(img, ch).resize((W, H)))
    return cells

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler()
    crom = tiles_of(b.rom)
    vram = (C.c_uint16 * 65536).from_address(b.core.retro_get_memory_data(3))   # RETRO_MEMORY_VIDEO_RAM
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    moves = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', hdr).group(1).replace('BA_', '').lower().split(', ')
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    roster = {r['name']: r for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']}
    acc = {}
    for name in NAMES:
        ch = CHAR[name]; k = bcs.index('BC_' + name.upper())
        ex = json.load(open(os.path.join(GAME, 'build', f'tmp_samsho2_{name}', 'kof95_export.json')))['characters'][name]
        used = sorted({p.get('pal', 0) for fr in ex['frames'] for p in fr['parts']})
        palmap = [int(ex['modes']['palettes'][u]) for u in used]
        b.pick(k)
        lab_req(b, 1, k, 0); b.run(60)
        assert b.char_of(0) == k, f'P1 is not {name} in the lab'
        # 1. every frame, both facings; the moves' sheets
        res = {'same': 0, 'differ': 0, 'differ_list': []}
        inmove = {}
        for m in moves:
            if m in ex['anims']:
                for st in ex['anims'][m]['steps']: inmove.setdefault(st['frame'], m)
        for facing in (1, -1):
            cells = {}
            for fi, fr in enumerate(ex['frames']):
                for _ in range(2):
                    b.fset(0, 'facing', facing & 0xFF); b.fset(0, 'frame_ovr', fi); b.fset(0, 'shown_frame', 0xFFFF); b.run(1)
                got = crop_nz(unwrap(block_image(b, vram, crom, palmap)))
                ref = ref_frame(ch, fr); ref = crop_nz(ref if facing > 0 else ref[:, ::-1])
                if got.shape == ref.shape and (got == ref).all(): res['same'] += 1
                else:
                    res['differ'] += 1
                    res['differ_list'].append({'frame': fi, 'facing': facing, 'record': fr['record'], 'got': got.shape, 'ref': ref.shape,
                                               'cols': sum(len(p['tiles']) for p in fr['parts']),
                                               'px': int((got != ref).sum()) if got.shape == ref.shape else None})
                if fi in inmove and len(cells.setdefault(inmove[fi], [])) < 14:
                    cells[inmove[fi]].append(colour_img(got, ch) if got.size else Image.new('RGB', (8, 8), 'white'))
            rows = [(m, cells[m]) for m in moves if m in cells]
            W, H = 140, 150
            sheet = Image.new('RGB', (W * max(len(c) for _, c in rows) + 130, H * len(rows)), 'white'); d = ImageDraw.Draw(sheet)
            for i, (m, cs) in enumerate(rows):
                d.text((4, i * H + 4), m, fill='black')
                for j, c in enumerate(cs):
                    c = c.copy(); c.thumbnail((W, H)); sheet.paste(c, (130 + j * W, i * H + H - c.height))
            sheet.save(os.path.join(OUT, f'moves_{name}_{"right" if facing > 0 else "left"}.png'))
        b.fset(0, 'frame_ovr', 0xFFFF)
        json.dump(res, open(os.path.join(OUT, f'frames_{name}.json'), 'w'), indent=1)
        print(name, f'frames vs SS2 (both facings): {res["same"]} identical, {res["differ"]} differ', res['differ_list'][:4], flush=True)
        # 2. the specials with the pad vs SS2's captures
        import handlers_ss2 as HS
        caps = {m['entry']['result']: m for m in json.load(open(f'{CAPS}/{ch:02d}.json')) if m['entry']}
        rage = {m['entry']['result']: m for m in json.load(open(f'{CAPS}/{ch:02d}_rage.json')) if m['entry']}
        r = roster[name]; slots = [('C', '', 'D'), ('fwd+C', 'R', 'fD'), ('down+C', 'D', 'dD'), ('up+C', 'U', 'uD'),
                                   ('df+C', 'DR', 'dfD'), ('uf+C', 'UR', 'ufD')]
        plays = [(lab, st + 'c', r['specials'].get(key)) for lab, st, key in slots if r['specials'].get(key)] + [('D (fury)', 'd', r['fury'])]
        if 'MAX ' + r['fury'] in HS.SPECIALS[name]: plays.append(('down+D (MAX)', 'Dd', 'MAX ' + r['fury']))
        sres, strips = {}, []
        for lab, keys, inp in plays:
            lab_req(b, 1, k, 0); b.run(40)
            dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
            b.place(0, x=b.fget(dm, 'x') - 120, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
            h0 = len(b.hits); cells = []; proj = 0
            for f in range(120):
                b.run(1, p1=keys if f < 4 else '')
                proj = max(proj, sum(1 for i in range(4) if b.pget(i, 'state') == b.states.index('PROJ')))
                if f % 4 == 0 and len(cells) < 26:
                    p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).resize((160, 112)))
            fn, nv, results = HS.SPECIALS[name][inp]
            cap = (rage if inp == 'WFT' or 'RAGE' in inp else caps).get(results[-1])
            sres[inp] = {'slot': lab, 'hits': [(h[1], h[2], h[3]) for h in b.hits[h0:]], 'projectiles_seen': proj}
            strips.append((f'{lab} {inp} brawler', cells))
            if cap: strips.append((f'{inp} SS2 ({"ABC"[nv - 1] if nv > 1 else ""})', ss2_strip(ch, cap, n=26)))
            print(name, lab, inp, 'hits', sres[inp]['hits'], 'projectiles', proj, flush=True)
        Wc = 160 * max(len(c) for _, c in strips) + 150
        sheet = Image.new('RGB', (Wc, 112 * len(strips)), 'white'); d = ImageDraw.Draw(sheet)
        for i, (nm, cs) in enumerate(strips):
            d.text((4, i * 112 + 4), nm, fill='black')
            for j, c in enumerate(cs): sheet.paste(c, (150 + j * 160, i * 112))
        sheet.save(os.path.join(OUT, f'specials_{name}.png'))
        json.dump(sres, open(os.path.join(OUT, f'specials_{name}.json'), 'w'), indent=1, default=str)
        # 3. the acceptance list (TODO #148), Haohmaru
        if name == 'haohmaru':
            a = {}
            bc = b.syms['bm_chars'] + k * b.syms['sizeof_bchar']
            a['fury_is_wft'] = r['fury'] == 'WFT' and ex['specials'][[sp['input'] for sp in ex['specials']].index('WFT')]['anims'] == [333]
            # the crescent pinned: during down+C (623S) every frame its entity's place minus his
            lab_req(b, 1, k, 0); b.run(40)
            dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
            b.place(0, x=b.fget(dm, 'x') - 200, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
            track = []
            for f in range(60):
                b.run(1, p1='Dc' if f < 4 else '')
                for i in range(4):
                    if b.pget(i, 'state') == b.states.index('PROJ'):
                        track.append((f, round(b.pget(i, 'x') - b.fget(0, 'x'), 2), round(b.pget(i, 'y') - b.fget(0, 'y'), 2), round(b.fget(0, 'y'), 1)))
            a['crescent'] = {'frames': len(track), 'offsets': sorted({(t[1], t[2]) for t in track}), 'his_heights': sorted({t[3] for t in track})[-3:]}
            # the throw: walk into the dummy, then forward+A
            lab_req(b, 1, k, 0); b.run(40)
            dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
            b.place(0, x=b.fget(dm, 'x') - 40, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(2)
            seq = []
            for f in range(140):
                b.run(1, p1='R' if f < 12 else ('Ra' if 16 <= f < 20 else ''))
                st_ = (b.states[b.fget(0, 'state')], b.states[b.fget(dm, 'state')])
                if not seq or seq[-1][1] != st_: seq.append((f, st_))
            a['throw'] = seq
            acc[name] = a
            print('acceptance', json.dumps(a)[:600], flush=True)
    json.dump(acc, open(os.path.join(OUT, 'acceptance.json'), 'w'), indent=1, default=str)

if __name__ == '__main__':
    main()
