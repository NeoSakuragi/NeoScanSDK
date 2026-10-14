#!/usr/bin/env python3
"""Final Fight's HUD faces (P1's life bar portrait, 14 x 14 px inside its white frame) from FF's own screen in FBNeo
(study states /data/study/ffight/<name>_g.state), doubled to the brawler's 28 x 28 select / HUD square
(make_hud.portrait reads <game>_<name>_square.png).

    python3 portraits_ff.py   -> /data/neogeo_dict/portraits/ffight_<name>_square.png (+ _hud.png, the 14 x 14 face)"""
import os, sys
sys.path.insert(0, '/data/study/ffight/scripts')
from ffl import core, ld
from PIL import Image
OUT = '/data/neogeo_dict/portraits'

def face(img):
    """the white frame's inside: the first white column / row from the top-left corner"""
    px = img.load(); W, H = img.size
    white = lambda x, y: px[x, y][0] > 200 and px[x, y][1] > 200 and px[x, y][2] > 200
    pts = [(x, y) for y in range(0, 40) for x in range(0, 40) if white(x, y)]
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    x1 = max(p[0] for p in pts if p[1] == y0); y1 = max(p[1] for p in pts if p[0] == x0)
    return img.crop((x0 + 1, y0 + 1, x1, y1))

def main():
    c = core(); tmp = '/tmp/_ffhud.png'
    for n in ('guy', 'cody', 'haggar'):
        ld(c, n + '_g'); c.run(2); c.png(tmp)
        f = face(Image.open(tmp).convert('RGB'))
        f.save(os.path.join(OUT, f'ffight_{n}_hud.png'))
        sq = Image.new('RGB', (28, 28), f.getpixel((0, 0)))             # 2x (whole pixels), on its own backdrop
        sq.paste(f.resize((f.width * 2, f.height * 2), Image.NEAREST), ((28 - 2 * f.width) // 2, (28 - 2 * f.height) // 2))
        sq.save(os.path.join(OUT, f'ffight_{n}_square.png'))
        print(n, f.size)

if __name__ == '__main__': main()
