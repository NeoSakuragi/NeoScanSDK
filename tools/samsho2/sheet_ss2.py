#!/usr/bin/env python3
"""Contact sheets rendered from the ROM decoder (ss2.py): one row per animation, one cell per step (ticks under it),
the fighter's colour set A from the ROM palette table ($FD10).
    python3 sheet_ss2.py CHAR ANIM[,ANIM...] OUT.png [--labels 'a:label,...']"""
import sys, numpy as np
from PIL import Image, ImageDraw
import ss2

def anim_cells(char, anim, W=200, H=200, foot=186, colour=0):
    steps = ss2.parse_anim(char, anim)
    pals = ss2.fighter_palettes(min(char, 17), colour)
    cells = []
    for st in steps:
        img = np.zeros((H, W), np.uint16)
        try: ss2.render_step(img, st, W // 2 - 20, foot, 0, (0, 0, 0, 0))
        except Exception as e: pass
        cells.append((Image.fromarray(ss2.colorize(img, pals)), st))
    return cells

def sheet(char, anims, out, labels=None, W=200, H=200, maxcols=12):
    rows = []
    for a in anims:
        cells = anim_cells(char, a, W, H)
        for k in range(0, max(len(cells), 1), maxcols): rows.append((a, k, cells[k:k + maxcols]))
    img = Image.new('RGB', (W * maxcols + 120, (H + 14) * len(rows)), 'white'); d = ImageDraw.Draw(img)
    for r, (a, k, cells) in enumerate(rows):
        y = r * (H + 14)
        d.text((4, y + 4), f'{ss2.NAMES[char] if char < 18 else char}\nanim {a}' + (f'\n{labels.get(a, "")}' if labels else '') +
               (f'\n(steps {k}+)' if k else ''), fill='black')
        for c, (im, st) in enumerate(cells):
            img.paste(im, (120 + c * W, y)); d.rectangle([120 + c * W, y, 120 + (c + 1) * W - 1, y + H - 1], outline='black')
            snd = [x for x in st['cmds'] if x[0].startswith('sound')]
            d.text((124 + c * W, y + H + 1), f"t{st['ticks']}" + (f" s{snd[0][1]:03x}" if snd else '') + (f" {st['end']}" if st['end'] else ''), fill='black')
    img.save(out); return out

if __name__ == '__main__':
    char = int(sys.argv[1]); anims = [int(x) for x in sys.argv[2].split(',')]
    labels = None
    if '--labels' in sys.argv:
        labels = {int(k): v for k, v in (x.split(':', 1) for x in sys.argv[sys.argv.index('--labels') + 1].split(','))}
    print(sheet(char, anims, sys.argv[3], labels))
