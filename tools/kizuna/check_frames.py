#!/usr/bin/env python3
"""Two checks of the export's frames (export_kz.py: Kizuna's renderer at its widest zoom $CC, re-tiled):

1. kz.render_step_zoom vs Kizuna itself: Kim plays a string of moves in our emulator (emu/neogeo_sdl --capture, the
   vs state; P1 put at x 320, P2 held at 640: the camera sits at $CC with Kim inside the screen); every frame at zoom $CC, the step P1 showed (the step of
   the frame before: the game draws one frame late) is rendered from the ROM and compared with VRAM (kz.vram_index_shrink:
   the LSPC's shrink, every sprite) restricted to Kim's palettes (16, 17), both cropped to their opaque pixels.
2. every exported frame drawn from the export's own tiles (mirrored back to facing right) vs kz.render_step_zoom.

    python3 check_frames.py [EXPORT_DIR]      (default examples/brawler/build/tmp_kizuna_kim)"""
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import kz, cap_kz, export_kz

EXP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'build', 'tmp_kizuna_kim')
MOVES = ('2:-,70:-,' + ','.join(f'{s},40:-' for s in ['3:a', '3:b', '3:c', '3:bc', '6:R,3:Rb', '6:R,3:Rc', '6:D,3:Da,20:D',
         '6:D,3:Db,20:D', '6:D,3:Dc,20:D', '3:D,3:DR,3:R,3:c,3:c', '3:D,3:DL,3:L,3:b,3:b', '40:D,3:Uc,3:Uc',
         '3:U,12:-,3:a', '3:U,12:-,3:c', '3:UR,60:-', '3:UL,60:-', '3:ab', '3:cd']) + ',60:-')

def crop(img):
    ys, xs = np.nonzero(img)
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else img[:0, :0]

def check_vram(d='/data/tmp/kizuna/check'):
    n = cap_kz.nframes(MOVES)
    pk = '1:108224=01,108225=40;' + ';'.join(f'{f}:108424=02,108425=80' for f in range(n))   # P1 x 320 once, P2 640
    rows = cap_kz.run(MOVES, '', vram=True, keep=d, pokes=pk)
    same = diff = skipped = 0; bad = []
    for i in range(1, len(rows)):
        r = rows[i]; z = r['cam'][0x2A]
        if z != export_kz.Z: skipped += 1; continue
        o = cap_kz.obj(rows[i - 1], 0x108200)
        v = kz.vram_words(r['vram'])
        vi = kz.vram_index_shrink(v)
        vi = np.where(((vi >> 4) == 16) | ((vi >> 4) == 17), vi, 0)
        ref = np.zeros((640, 640), np.uint16); kz.render_step_zoom(ref, o['ptr'], 320, 520, z)
        a, b = crop(vi), crop(ref)
        if a.shape == b.shape and (a == b).all(): same += 1
        else: diff += 1; bad.append((r['f'], hex(o['anim']), o['step'], a.shape, b.shape))
    return same, diff, skipped, bad

def check_export():
    ex = json.load(open(os.path.join(EXP, 'kof95_export.json')))['characters']['kim']
    c1 = open(os.path.join(EXP, 'kof95_c1.bin'), 'rb').read(); c2 = open(os.path.join(EXP, 'kof95_c2.bin'), 'rb').read()
    reg = bytearray(len(c1) * 2); reg[0::2] = c1; reg[1::2] = c2; reg = bytes(reg)
    pals = [int(p, 16) for p in ex['modes']['palettes']]
    same = diff = 0; bad = []
    for fi, fr in enumerate(ex['frames']):
        img = np.zeros((640, 640), np.uint16)
        for p in fr['parts']:
            for c, col in enumerate(p['tiles']):
                for r, t in enumerate(col):
                    if not t: continue
                    b = np.frombuffer(reg, np.uint8, 128, t * 128).reshape(2, 16, 4)
                    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
                    pen = (bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3)
                    pen = np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint16)
                    y, x = 520 + p['dy'] + 16 * r, 320 + p['dx'] + 16 * c
                    img[y:y + 16, x:x + 16] = np.where(pen > 0, pals[p['pal']] << 4 | pen, img[y:y + 16, x:x + 16])
        ref = np.zeros((640, 640), np.uint16); [kz.render_step_zoom(ref, int(a, 16), 320, 520, export_kz.Z) for a in fr['record'].split('+')]
        a, b = crop(img[:, ::-1]), crop(ref)
        if a.shape == b.shape and (a == b).all(): same += 1
        else: diff += 1; bad.append((fi, fr['record']))
    return same, diff, bad

if __name__ == '__main__':
    s, d, k, bad = check_vram()
    print(f'1. ROM render at $CC vs Kizuna VRAM: {s} identical, {d} differ ({k} frames at another zoom skipped)', bad[:8])
    s2, d2, bad2 = check_export()
    print(f'2. exported frames vs the ROM render: {s2} identical, {d2} differ', bad2[:8])
    json.dump({'vram_same': s, 'vram_differ': d, 'vram_bad': bad, 'export_same': s2, 'export_differ': d2},
              open('/data/tmp/kizuna/out/check_frames.json', 'w'), default=str)
