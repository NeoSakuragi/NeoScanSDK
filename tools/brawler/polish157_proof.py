#!/usr/bin/env python3
"""TODO #157 / #159 / #167 proofs in our emulator (harness.py, the repo's Geolith core).

    python3 polish157_proof.py select GAME OUT TAG    every select slot with P1's cursor on it: crops of frames n / n+1
                                                      around the slot's head (OUT/TAG_select.png) + the whole screen
    python3 polish157_proof.py bg GAME OUT TAG SX...  campaign stage 2 (Robo Army area 1) with the camera at x SX:
                                                      OUT/TAG_bg_SX.png (P1 kept off the block's columns)
    python3 polish157_proof.py hud GAME OUT TAG       the title and a fight's bottom line (OUT/TAG_hud_*.png)"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from PIL import Image, ImageDraw

def boot(game):
    from harness import Brawler
    return Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)

def shot(b, path):
    b.screenshot(path); return Image.open(path)

FULL = os.environ.get('FULL')
def select(b, out, tag):
    b.core.retro_reset(); b.seq('600:-,4:o,100:-'); b.unlock_all(); b.seq('4:s,120:-')
    slots = b.sel_slots(); sc = [b.r(b.syms['slot_ch'] + i, 1) for i in range(b.nslot)]
    names = [r['name'] for r in __import__('json').load(open(os.path.join(b.game_dir, 'game.json')))['roster']]
    cells = []
    for s in range(b.nslot):
        k = sc[s]; b.sel_goto(k); b.run(8)
        a = shot(b, os.path.join(out, f'{tag}_sel_full.png'))
        bb = shot(b, os.path.join(out, f'{tag}_sel_full_n1.png'))
        a.save(os.path.join(out, f'{tag}_select_screen_{names[k]}.png')) if FULL else None
        x = slots[s][0] - 8                              # screenshot x = screen x - 8 (8 px overscan cropped)
        for im, lab in ((a, 'n'), (bb, 'n+1')):
            c = im.crop((x - 48, 0, x + 48, 150)).resize((192, 300), Image.NEAREST)
            d = ImageDraw.Draw(c); d.rectangle([0, 0, 191, 299], outline='black')
            d.text((3, 288), f'{names[k]} {lab}', fill='yellow'); cells.append(c)
    cols = 8
    sheet = Image.new('RGB', (192 * cols, 300 * ((len(cells) + cols - 1) // cols)), 'white')
    for i, c in enumerate(cells): sheet.paste(c, ((i % cols) * 192, (i // cols) * 300))
    sheet.save(os.path.join(out, f'{tag}_select.png'))
    os.remove(os.path.join(out, f'{tag}_sel_full.png')); os.remove(os.path.join(out, f'{tag}_sel_full_n1.png'))

def stage(b, camp):
    import scenario as S
    lab = b.syms['lab']; poke = lambda off, data: [b.w(lab + off + i, 1, v) for i, v in enumerate(data)]
    b.core.retro_reset()
    for _ in range(S.BOOT): b.core.retro_run()
    poke(0, b'LAB1'); poke(S.LAB_FIGHTER, [0, camp]); poke(S.LAB_WAVE, [0]); poke(S.LAB_REQ, [4])
    for _ in range(3000):
        b.core.retro_run()
        if b.r(lab + S.LAB_REQ, 1) == 0 and b.r(b.syms['mode'], 1) == 1: break
    b.run(2)

def bg(b, out, tag, sxs):
    stage(b, 1)
    for sx in sxs:
        for f in range(400):
            cam = b.r(b.syms['cam_x'], 2)
            if cam == sx: break
            b.w(b.syms['lock_x'], 2, 4000)
            b.fset(0, 'x', sx + 160); b.fset(0, 'hp', 100)
            for i in range(2, 8): b.fset(i, 'x', sx + 900)
            b.run(1)
        b.fset(0, 'x', sx + 160)
        for i in range(2, 8): b.fset(i, 'x', sx + 900)
        b.run(1); shot(b, os.path.join(out, f'{tag}_bg_{sx}.png'))
        for k in range(1, 32):                           # the next frames: every auto-animation phase (LSPC counter)
            shot(b, os.path.join(out, f'{tag}_bg_{sx}_f{k}.png'))
        print(tag, 'camera', b.r(b.syms['cam_x'], 2))

def hud(b, out, tag):
    b.core.retro_reset(); b.seq('700:-'); shot(b, os.path.join(out, f'{tag}_hud_title.png'))
    stage(b, 0); b.run(30); shot(b, os.path.join(out, f'{tag}_hud_fight.png'))

if __name__ == '__main__':
    mode, game, out, tag = sys.argv[1:5]; os.makedirs(out, exist_ok=True)
    b = boot(game); b.game_dir = game
    if mode == 'select': select(b, out, tag)
    elif mode == 'bg': bg(b, out, tag, [int(v) for v in sys.argv[5:]])
    elif mode == 'hud': hud(b, out, tag)
