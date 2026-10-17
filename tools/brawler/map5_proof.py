#!/usr/bin/env python3
"""The campaign map's five notes of 2026-10-17 (0.10.164), in our emulator (harness.py), one contact sheet:

  20261017-114940-e03d  stage start: the map 2 s on a BLACK stage (map.start_ticks), then the fade-in, twice as long
                        (stage_intro.fade 64), then the walk-in
  20261017-132838-e03d  stage clear: the win pose first, STAGE CLEAR + the map map.clear_at (2 s) later
  20261017-131927-e03d  the clear's map: the stage JUST CLEARED blinks (was the next one)
  20261017-132400-e03d  the map at every stage clear (stages 1, 2 and the last: ALL CLEAR!, then the ending), here
                        reached with the stage-clear cheat (P1 holds down + A + B + C + D)
  20261017-132507-e03d  no green in SLUM: make_map.py's split palettes (zoom, before = BEFORE_ROM if given)

    map5_proof.py [OUT] [--before ROM]     sheet OUT/map5_sheet.png, zoom OUT/map5_zoom.png, OUT/map5.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H
import scenario as S
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else '/data/tmp/ffmap5/out'
BEFORE = sys.argv[sys.argv.index('--before') + 1] if '--before' in sys.argv else None
ROM = os.path.join(S.GAME, 'brawler.neo')
os.makedirs(OUT, exist_ok=True)


def pic(b):
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def brawler(rom):
    game = S.snapshot(rom); b = H.Brawler(rom=rom, game=game); b.game = game; b._want_video = True; return b


def u8(b, n): return b.r(b.syms[n], 1)


def start_run(b, cells, log):
    """select Terry, A: the stage start, every 30 ticks from the map's opening to the walk-in"""
    S.setup(b, {'setup': {'mode': 'select', 'cursor': 'terry'}})
    b.seq('3:a')
    t = 0
    while not u8(b, 'map_on') and t < 600: b.run(1); t += 1
    m0 = b.frame; rows = []
    for k in range(260):
        b.run(1)
        r = {'t': b.frame - m0, 'map_on': u8(b, 'map_on'), 'in_ph': u8(b, 'in_ph'), 'backdrop': None}
        rows.append(r)
        if r['t'] in (10, 60, 115, 125, 150, 185, 200):
            lab = {10: 'map on black', 60: 'map on black 1 s', 115: 'map, 1.9 s', 125: 'fade 1/8', 150: 'fade 1/2',
                   185: 'fade done', 200: 'walk-in'}[r['t']]
            cells.append((f'START +{r["t"]}: {lab}', pic(b)))
    close = next(r['t'] for r in rows if not r['map_on'])
    walk = next((r['t'] for r in rows if r['in_ph'] == 2), None)
    log['start'] = {'map_ticks': close, 'walk_in_at': walk}


def clear_run(b, stage, cells, log, picks, zoom=None):
    """campaign stage `stage` from its second wave, the stage-clear cheat held, then the clear's sequence"""
    S.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': stage, 'wave': 1}})
    b.run(20)
    t = 0
    while u8(b, 'phase') < 3 and t < 400: b.run(1, p1='Dabcd'); t += 1      # PH_END = 3 (main.c enum)
    c0 = b.frame; rows = []; got = {}
    for k in range(1500):
        b.run(1)
        tt = b.frame - c0
        r = {'t': tt, 'phase': u8(b, 'phase'), 'map_on': u8(b, 'map_on'), 'mode': u8(b, 'mode'), 'bt_n': u8(b, 'bt_n'),
             'dr_on': u8(b, 'dr_on')}
        rows.append(r)
        if tt in picks:
            im = pic(b); cells.append((f'STAGE {stage + 1} CLEAR +{tt}: {picks[tt]}', im)); got[tt] = im
        if zoom is not None and r['map_on'] and len(zoom) < 14 and tt % 3 == 0: zoom.append(pic(b))
        if r['mode'] != 1 and tt > 600: break
    mo = next((r['t'] for r in rows if r['map_on']), None)
    mc = next((r['t'] for r in rows if mo and r['t'] > mo and not r['map_on']), None)
    dr = next((r['t'] for r in rows if r['dr_on']), None)
    nxt = next((r for r in rows if r['mode'] != 1), None)
    log[f'clear_{stage + 1}'] = {'map_open_at': mo, 'map_close_at': mc, 'win_drama_at': dr,
                                 'next_screen': nxt and {'t': nxt['t'], 'mode': nxt['mode']}}


def sheet(cells, path, cols=4):
    w, h = cells[0][1].size
    sh = Image.new('RGB', (w * cols, (h + 14) * ((len(cells) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sh)
    for i, (lab, im) in enumerate(cells):
        x, y = i % cols * w, i // cols * (h + 14); sh.paste(im, (x, y + 14)); d.text((x + 3, y + 1), lab, fill='black')
    sh.save(path)


def slum_zoom(frames, ref_lit):
    """the frame where POLICE shows green (its blink's lit phase): the map's left part, x4"""
    best = max(frames, key=lambda im: sum(1 for x in range(100, 200, 2) for y in range(90, 130, 2)
                                          if (lambda p: p[1] > p[0] + 40 and p[1] > p[2] + 40)(im.getpixel((x, y)))))
    return best.crop((32, 84, 192, 148)).resize((640, 256), Image.NEAREST)


def main():
    log = {}; cells = []
    b = brawler(ROM)
    start_run(b, cells, log)
    clear_run(b, 0, cells, log, {40: 'win pose, no text', 125: 'STAGE CLEAR + map', 131: '6 ticks on (blink)',
                                  400: 'map closing', 520: 'after the map'})
    zoom_after = []
    clear_run(b, 1, cells, log, {125: 'POLICE blinking', 131: 'blink'}, zoom_after)
    clear_run(b, 2, cells, log, {125: 'GEESE TOWER, ALL CLEAR!', 470: 'the ending'})
    sheet(cells, os.path.join(OUT, 'map5_sheet.png'))
    za = slum_zoom(zoom_after, None)
    if BEFORE:                                          # (one core a process: 0.10.164's run in a child)
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), '--zoom-before', BEFORE, os.path.join(OUT, 'zoom_before.png')], check=True)
        zbi = Image.open(os.path.join(OUT, 'zoom_before.png'))
        z = Image.new('RGB', (640, 256 * 2 + 28), 'white'); d = ImageDraw.Draw(z)
        d.text((4, 1), 'BEFORE (0.10.164): SLUM grey, POLICE green - x4', fill='black'); z.paste(zbi, (0, 13))
        d.text((4, 270), 'AFTER: SLUM grey, POLICE green - x4', fill='black'); z.paste(za, (0, 283))
        z.save(os.path.join(OUT, 'map5_zoom.png'))
    json.dump(log, open(os.path.join(OUT, 'map5.json'), 'w'), indent=1)
    print(json.dumps(log, indent=1))


if __name__ == '__main__':
    if '--zoom-before' in sys.argv:                     # 0.10.164: stage 1's clear map = SLUM grey, POLICE blinking
        i = sys.argv.index('--zoom-before'); zb = []
        clear_run(brawler(sys.argv[i + 1]), 0, [], {}, {}, zb); slum_zoom(zb, None).save(sys.argv[i + 2])
    else: main()
