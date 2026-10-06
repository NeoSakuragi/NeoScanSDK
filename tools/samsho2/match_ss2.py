#!/usr/bin/env python3
"""ROM render vs the game's VRAM: every display-list entry of frame f-1 (RAM) drawn by the ROM decoder (ss2.py)
against the VRAM of frame f, pixel for pixel (pen index = palette * 16 + pen) on the full-size sprites.
    python3 match_ss2.py CAPDIR [first last]   -> per-frame counts + a summary"""
import sys, glob, re, collections, numpy as np
import ss2, neo2 as N, cap_ss2 as C

def render_entries(ents, only=None):
    img = np.zeros((224, 320), np.uint16); own = np.full((224, 320), -1, np.int32)
    for k, e in enumerate(ents):          # list order = ascending priority = increasing sprite slots ($32D4): later on top
        if only and not only(e): continue
        d = e['d']
        if e['zoom']: continue
        try:
            sd, left, top = ss2.layer_box(d, e['x'], e['y'], e['flip'])
            _, cells = ss2.sprite_cells(d & 0x7FFF)
        except Exception as ex:
            print('  def', hex(d), ex); continue
        tmp = np.zeros_like(img)
        ss2.blit(tmp, cells, left, top, e['flip'], e['pal'])
        m = tmp > 0; img[m] = tmp[m]; own[m] = k
    return img, own

def match(cap, f, only=None):
    r = C.ram(cap, f - 1); v = N.words(f'{cap}/vram{f}.bin')
    ents = C.display_list(r)
    img, own = render_entries(ents, only)
    vi, who, sk = N.vram_index(v)
    m = (img > 0) & (who >= 81) & (who <= 320)    # the display list's slots ($31F0 copies SCB3 of 81-320); the
                                                  # stage's own sprites (foreground rocks, bushes) live outside
    eq = (vi[m] == img[m]); bad = collections.Counter()
    match.pen_eq = int(((vi[m] & 15) == (img[m] & 15)).sum())   # shapes / pens only (palette ignored)
    for k in np.unique(own[m][~eq]): bad[hex(ents[k]['d'])] += int(((own == k) & m & (vi != img)).sum())
    return int(m.sum()), int(eq.sum()), bad, ents

if __name__ == '__main__':
    cap = sys.argv[1]
    fs = sorted(int(re.findall(r'vram(\d+)', p)[0]) for p in glob.glob(f'{cap}/vram*.bin'))
    if len(sys.argv) > 3: fs = [f for f in fs if int(sys.argv[2]) <= f <= int(sys.argv[3])]
    tot = totq = exact = 0; allbad = collections.Counter(); defs = set()
    for f in fs:
        if C.ram(cap, f - 1) is None: continue
        if not any(N.words(f'{cap}/vram{f}.bin')[0x8251:0x8251 + 240]): continue   # SCB3 of slots 81-320 blank: the dump
                                                                                     # caught the buffer between banks
        n, q, bad, ents = match(cap, f)
        defs.update(e['d'] & 0x7FFF for e in ents)
        tot += n; totq += q; exact += n == q; allbad.update(bad)
        if n != q: print(f, n, q, dict(bad))
    print(f'frames {len(fs)}  exact {exact}  pixels {totq}/{tot}  defs {len(defs)}  worst {allbad.most_common(8)}')
