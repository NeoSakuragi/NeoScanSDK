#!/usr/bin/env python3
"""Every exported SS4 frame, drawn the brawler's way (parts, export tiles, facing right = mirrored), against the SS4
step it came from drawn by ss4.render_step (the study's renderer, 444 / 454 frames pixel-exact against VRAM), as
pen indices (palette * 16 + pen).

    python3 check_frames.py EXPORT_DIR

2026-10-05, Haohmaru (/data/neogeo_dict/samsho4/haohmaru_export): 309 / 310 frames identical; the other (the tornado's
hit, sprite $7CA4) has an effect cell in a palette outside the fighter's 32 (exported as palette 0: 13 pixels).
(ss4.render_step had dropped layers with a negative y offset: fixed in this copy.)"""
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss4, neo

def tile_pens(c1, c2, t):
    raw = bytearray(128); raw[0::2] = c1[t * 64:(t + 1) * 64]; raw[1::2] = c2[t * 64:(t + 1) * 64]
    b = np.frombuffer(bytes(raw), np.uint8).reshape(2, 16, 4)          # neo.tile's decode (not its cache)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    return np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint16)

def draw_export(fr, c1, c2, ox, oy, H=320, W=448):
    """the brawler facing right (draw.s: hflip ^ 1, x0 = 2 ox - x0 - w): pen-index image"""
    img = np.zeros((H, W), np.uint16)
    for p in fr['parts']:
        cols, rows = len(p['tiles']), len(p['tiles'][0])
        x0 = ox + p['dx']; x0 = 2 * ox - x0 - cols * 16
        for ci, col in enumerate(p['tiles']):
            for ri, t in enumerate(col):
                if not t: continue
                px = tile_pens(c1, c2, t)[:, ::-1]                 # facing right: every tile flipped
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
        for fi, fr in enumerate(ch['frames']):
            st = fr['ss4']
            ref = np.zeros((1024, 640), np.uint16)
            ss4.render_step(ref, st, 320, 560)
            got = draw_export(fr, c1, c2, 320, 560, 1024, 640)
            if (ref == got).all(): ok += 1
            else:
                bad += 1
                if bad <= 5: print('frame', fi, fr['record'], int((ref != got).sum()), 'pixels differ')
    print(ok, 'frames identical,', bad, 'differ')

if __name__ == '__main__':
    main(sys.argv[1])
