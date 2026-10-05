#!/usr/bin/env python3
"""Every exported WHP frame, drawn the brawler's way (parts, export tiles, facing right = mirrored back), against the
def it came from drawn by whp.render_def (the study's renderer: pixel-exact against WHP's VRAM, check_vram.py), as pen
indices (the export's palette index: (0x80 + index) * 16 + pen).

    python3 check_frames.py EXPORT_DIR"""
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import whp

def tile_pens(c1, c2, t):
    raw = bytearray(128); raw[0::2] = c1[t * 64:(t + 1) * 64]; raw[1::2] = c2[t * 64:(t + 1) * 64]
    b = np.frombuffer(bytes(raw), np.uint8).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    return np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint16)

def draw_export(fr, c1, c2, ox, oy, H=320, W=448):
    """the brawler facing right (draw.s: hflip ^ 1, x0 = 2 ox - x0 - w): pen-index image (tools/samsho4/check_frames.py)"""
    img = np.zeros((H, W), np.uint16)
    for p in fr['parts']:
        cols = len(p['tiles'])
        x0 = ox + p['dx']; x0 = 2 * ox - x0 - cols * 16
        for ci, col in enumerate(p['tiles']):
            for ri, t in enumerate(col):
                if not t: continue
                px = tile_pens(c1, c2, t)[:, ::-1]
                x = x0 + (cols - 1 - ci) * 16; y = oy + p['dy'] + ri * 16
                if not (0 <= x <= W - 16 and 0 <= y <= H - 16): continue
                sub = img[y:y + 16, x:x + 16]
                img[y:y + 16, x:x + 16] = np.where(px > 0, (0x80 + p['pal']) * 16 + px, sub)
    return img

def main(d):
    ex = json.load(open(os.path.join(d, 'kof95_export.json')))
    c1 = open(os.path.join(d, 'kof95_c1.bin'), 'rb').read(); c2 = open(os.path.join(d, 'kof95_c2.bin'), 'rb').read()
    ok = bad = 0
    for ch in ex['characters'].values():
        pals = [int(p, 16) for p in ch['modes']['palettes']]
        for fi, fr in enumerate(ch['frames']):
            w = int(fr['record'], 16)
            ref = np.zeros((1024, 640), np.uint16)
            whp.render_def(ref, w, (320 + 128) * 128, (352 - 560) * 128)
            pal = ref >> 4; pen = ref & 15
            idx = np.vectorize(lambda p: pals.index(p) if p in pals else 0x70)(pal) if ref.any() else pal
            ref = np.where(pen > 0, (0x80 + idx) * 16 + pen, 0).astype(np.uint16)
            got = draw_export(fr, c1, c2, 320, 560, 1024, 640)
            if (ref == got).all(): ok += 1
            else:
                bad += 1
                if bad <= 5: print('frame', fi, fr['record'], int((ref != got).sum()), 'pixels differ')
    print(ok, 'frames identical,', bad, 'differ')
    return ok, bad

if __name__ == '__main__':
    main(sys.argv[1])
