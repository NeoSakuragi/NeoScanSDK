#!/usr/bin/env python3
"""TODO #158 on Bruno's own inputs: feedback 20261006-161617-b3f3 (the select screen, Mr. Big and Billy Lee blinking)
was recorded from power-on (window frame 0), so its pads replay on any build: the player's core settings
(tools/feedback/pull.py Core), the bundle's pads frame by frame from power-on to his press. Per frame: the worst
scanline's sprite count as the LSPC drew it (the probe core of budget_proof.py, retro_get_memory_data(106)) and the
game's guard_hidden (main.c, the actors the budget hid); the last two frames' pictures side by side.

    BRAWLER_CORE=<probe core> python3 budget_bundle.py GAME_DIR OUT TAG      (one core per process)"""
import ctypes as C, json, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'feedback'))
BUNDLE = '/data/feedback/20261006-161617-b3f3'

def main(game, out, tag):
    import pull
    pull.CORE = os.environ['BRAWLER_CORE']
    meta = json.load(open(os.path.join(BUNDLE, 'meta.json')))
    raw = open(os.path.join(BUNDLE, 'inputs.bin'), 'rb').read()
    _, _, W, P = struct.unpack_from('<4sIQQ', raw)
    assert W == 0, 'the bundle does not start at power-on'
    pads = [struct.unpack_from('<HH', raw, 24 + 4 * i) for i in range(P - W)]
    syms = {}
    for l in subprocess.run(['m68k-linux-gnu-nm', os.path.join(game, 'build', 'rom.elf')], capture_output=True, text=True).stdout.split('\n'):
        p = l.split()
        if len(p) == 3: syms[p[2]] = int(p[0], 16)
    core = pull.Core(os.path.join(game, 'brawler.neo'), meta['system_type'], meta['hw'], meta.get('memcard', 'on'))
    core.core.retro_get_memory_data.restype = C.c_void_p
    ram = (C.c_uint8 * 65536).from_address(core.core.retro_get_memory_data(2))
    stat = (C.c_uint16 * (264 * 34)).from_address(core.core.retro_get_memory_data(106))
    rows, pics = [], []
    for i, (p0, p1) in enumerate(pads):
        img = core.frame(p0, p1, video=i >= len(pads) - 2)
        mode = ram[syms['mode'] - 0x100000]
        rows.append(dict(f=i, mode=mode, worst=max(stat[l * 34] for l in range(16, 240)), guard_hidden=ram[syms['guard_hidden'] - 0x100000]))
        if img is not None: pics.append((i, img))
    sel = [r for r in rows if r['mode'] == 0 and r['f'] > 700]
    res = dict(frames=len(rows), select_frames=len(sel), worst_line=max(r['worst'] for r in sel),
               frames_guard_hidden=sum(1 for r in sel if r['guard_hidden']), hidden_per_frame=sorted({r['guard_hidden'] for r in sel}))
    json.dump(dict(summary=res, rows=rows), open(os.path.join(out, f'bundle158_{tag}.json'), 'w'))
    from PIL import Image, ImageDraw
    w, h = pics[0][1].size
    sh = Image.new('RGB', (2 * w, h + 30), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), f'{tag}: Bruno\'s inputs (feedback 20261006-161617-b3f3) replayed from power-on: frames {pics[0][0]} / {pics[1][0]}', fill='black')
    d.text((4, 15), f'select screen frames {res["select_frames"]}: worst line {res["worst_line"]}, guard hid an actor on {res["frames_guard_hidden"]}', fill='black')
    for k, (f, im) in enumerate(pics): sh.paste(im, (k * w, 30))
    sh.save(os.path.join(out, f'bundle158_{tag}.png'))
    print(tag, res)

if __name__ == '__main__':
    main(*sys.argv[1:4])
