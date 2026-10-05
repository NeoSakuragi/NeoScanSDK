#!/usr/bin/env python3
"""Hanzou (World Heroes Perfect, tools/whp/export_whp.py) in the brawler, proved in the harness (tools/brawler/
harness.py, the game's ROM on the Geolith core), picked on the select screen (the real path: cursor walked to his slot).
Made from tools/samsho4/haohmaru_proof.py (same steps; the reference is WHP's def renderer).

    python3 hanzo_proof.py [OUTDIR]          (default /data/tmp/hanzo/out)

1. Every move, both facings: in the Chain Lab training (lab req 1: P1 = Hanzou against a standing dummy) each step of
   each of his BA_* animations is shown through the game's renderer (fighter_t.frame_ovr), the screen cropped around him
   -> moves_right.png / moves_left.png (one row per move, the steps left to right); and every one of those frames is
   compared with WHP's own rendering of the def it came from (whp.render_def, pixel-exact against WHP's VRAM: check_vram.py
   6274 / 6275 frames): the brawler's sprites read back from VRAM (SCB1-4 of P1's block, the brawler's C ROM tiles) as
   pen indices, palettes mapped back to the export's, mirrored when he faces left, aligned on the first opaque pixel.
2. The specials (D, forward+D, down+D, up+D) played with the pad against the dummy: hits taken by the dummy, projectile
   entities in flight, a strip of each -> specials.png."""
import json, os, re, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import whp
from harness import Brawler
from PIL import Image, ImageDraw
import ctypes as C

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/hanzo/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
HAO = 'hanzo'

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

def tiles_of(rom):
    d = open(rom, 'rb').read(); import struct
    sizes = struct.unpack('<6I', d[4:0x1C]); off = 0x1000 + sum(sizes[:5])
    return d[off:off + sizes[5]]

def pens(crom, code):
    b = np.frombuffer(crom, np.uint8, 128, code * 128).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    return np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint16)

def block_image(b, vram, crom, used):
    """P1's sprite block from VRAM -> pen-index image (the export's palette numbering: (0x80 + its palette) * 16 + pen)"""
    spr, n, pb = b.fget(0, 'spr'), b.fget(0, 'ncols'), b.fget(0, 'palbase')
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
            if not 0 <= p < len(used): continue
            y, x = (top + r * 16 + 16) & 0x1FF, (sx + 96) & 0x1FF    # shifted: a block across the 512 px wrap stays whole
            sub = img[y:y + 16, x:x + 16]
            img[y:y + 16, x:x + 16] = np.where(t > 0, (0x80 + used[p]) * 16 + t, sub)
    return img

def ref_image(w, pals):
    """WHP's drawing of def w (whp.render_def, facing right) in the export's palette numbering"""
    ref = np.zeros((640, 640), np.uint16)
    whp.render_def(ref, w, (320 + 128) * 128, (352 - 560) * 128)
    idx = np.vectorize(lambda p: pals.index(p) if p in pals else 0x70)(ref >> 4) if ref.any() else ref
    return np.where(ref & 15, (0x80 + idx) * 16 + (ref & 15), 0).astype(np.uint16)

def crop_nz(img):
    ys, xs = np.nonzero(img)
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else img[:0, :0]

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler()
    ex = json.load(open(os.path.join(GAME, 'build', f'tmp_whp_{HAO}', 'kof95_export.json')))['characters'][HAO]
    pals = [int(p, 16) for p in ex['modes']['palettes']]
    used = sorted({p.get('pal', 0) for fr in ex['frames'] for p in fr['parts']})
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    moves = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', hdr).group(1).replace('BA_', '').lower().split(', ')
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_' + HAO.upper())
    from export_bm import MOVES
    crom = tiles_of(b.rom)
    b.core.retro_get_memory_data.restype = C.c_void_p
    vram = (C.c_uint16 * 65536).from_address(b.core.retro_get_memory_data(101))
    b.pick(k)                                         # power on, coin, START, the cursor to his slot, A, the fight
    print('picked', b.char_of(0), 'BC index', k)
    lab_req(b, 1, k, 0); b.run(60)
    assert b.char_of(0) == k, 'P1 is not Hanzou in the lab'
    # 1. every move, both facings
    anims = {m: ex['anims'][m] for m in moves if m in ex['anims']}
    same = diff = 0; worst = []
    for facing in (1, -1):
        rows = []
        for m in moves:
            a = anims.get(m) or ex['anims']['idle']
            cells = []
            for st in a['steps']:
                fi = st['frame']
                for _ in range(2):
                    b.fset(0, 'facing', facing & 0xFF); b.fset(0, 'frame_ovr', fi); b.fset(0, 'shown_frame', 0xFFFF); b.run(1)
                b.fset(0, 'frame_ovr', fi); b.fset(0, 'facing', facing & 0xFF)
                p = os.path.join(OUT, '_shot.png'); b.screenshot(p)
                x = int(b.fget(0, 'x')) - b.r(b.syms['cam_x'], 2); im = Image.open(p)
                cells.append(im.crop((x - 120, 0, x + 120, im.height)))
                got = crop_nz(block_image(b, vram, crom, used))
                ref = ref_image(int(ex['frames'][fi]['record'], 16), pals)
                ref = crop_nz(ref if facing > 0 else ref[:, ::-1])
                if got.shape == ref.shape and (got == ref).all(): same += 1
                else: diff += 1; worst.append((m, facing, fi, got.shape, ref.shape))
            rows.append((m, cells))
        W = 240 * max(len(c) for _, c in rows) + 120; H = 230
        sheet = Image.new('RGB', (W, H * len(rows)), 'white'); d = ImageDraw.Draw(sheet)
        for i, (m, cells) in enumerate(rows):
            d.text((4, i * H + 4), m, fill='black')
            for j, c in enumerate(cells): sheet.paste(c.resize((240, 230)), (120 + j * 240, i * H))
        sheet.save(os.path.join(OUT, f'moves_{"right" if facing > 0 else "left"}.png'))
    print(f'frames vs WHP: {same} identical, {diff} differ', worst[:6])
    b.fset(0, 'frame_ovr', 0xFFFF)
    # 2. specials with the pad: D, forward+D, down+D (stick down = toward the screen), up+D
    res = {}
    strips = []
    for name, keys, dist in (('D', 'd', 150), ('fwd+D', 'Rd', 150), ('down+D', 'Dd', 50), ('up+D', 'Ud', 90)):
        lab_req(b, 1, k, 0); b.run(40)
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        b.place(0, x=b.fget(dm, 'x') - dist, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
        h0 = len(b.hits); cells = []; proj = 0; vst = []
        for f in range(110):
            b.run(1, p1=keys if f < 4 else '')
            proj = max(proj, sum(1 for i in range(4) if b.pget(i, 'state') == b.states.index('PROJ')))
            st_ = b.states[b.fget(dm, 'state')]
            if not vst or vst[-1] != st_: vst.append(st_)
            if f % 6 == 0:
                p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).resize((160, 112)))
        res[name] = {'hits': b.hits[h0:], 'projectiles_seen': proj, 'dummy_states': vst}
        strips.append((name, cells))
        print(name, 'hits on the dummy', [(h[1], h[2], h[3]) for h in b.hits[h0:]], 'projectile entities', proj, 'dummy', vst)
    W = 160 * max(len(c) for _, c in strips) + 80
    sheet = Image.new('RGB', (W, 112 * len(strips)), 'white'); d = ImageDraw.Draw(sheet)
    for i, (nm, cells) in enumerate(strips):
        d.text((4, i * 112 + 4), nm, fill='black')
        for j, c in enumerate(cells): sheet.paste(c, (80 + j * 160, i * 112))
    sheet.save(os.path.join(OUT, 'specials.png'))
    json.dump({'frames_same': same, 'frames_differ': diff, 'differ': worst, 'specials': res}, open(os.path.join(OUT, 'proof.json'), 'w'), default=str)

if __name__ == '__main__':
    main()
