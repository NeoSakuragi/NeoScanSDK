#!/usr/bin/env python3
"""T6 (2026-10-14): Moriya's dragon punch follow-up in The Last Blade 2, measured in our emulator (play_lb2: the repo's
Geolith core, vs.state). Ittou Shingetsu (623A, move $92) then 623B (row $7A): the transition table maps row $7A from
Shingetsu's state class 78 to move $B2, Ittou Sougetsu [code: $A0000[$7A * 256 + 78 - 1]]; Shingetsu sets class 78 in
Speed / EX only (Power: none, so no Sougetsu) [code: its $92 command, per style]. Measured here, per style (+$17A) and
per press time (the B press of 623B ending k frames after Shingetsu starts): the frame Sougetsu starts, on hit (P2 at +60)
and on whiff (P2 kept 250 px away).

    python3 sougetsu_lb2_proof.py [OUT.json]   (default /data/tmp/lb2_t456/sougetsu_lb2.json)
    python3 sougetsu_lb2_proof.py game DIR     LB2 (Speed, P2 at +60): 623A, 623B pressed during it, every 3rd frame
    python3 sougetsu_lb2_proof.py brawler DIR  the brawler (his pack build): C next to Ryo, C again, every 3rd frame
    python3 sougetsu_lb2_proof.py sheet DIR    -> DIR/sougetsu.png (one core per process: game / brawler apart)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import play_lb2 as PL

def main(out='/data/tmp/lb2_t456/sougetsu_lb2.json'):
    g = PL.core(); res = {}
    for style, sname in ((0, 'Power'), (1, 'Speed'), (3, 'EX')):
        for gap, keep in ((60, False), (250, True)):
            rows = []
            for d in range(0, 40, 2):
                g.load_state(f'{PL.STA}/vs.state'); g.frame = 0
                g.w(PL.P1 + 0x17A, 1, style)
                keys = PL.expand('2:-,3:R,3:D,3:DR,3:a,' + (f'{d}:-,' if d else '') + '3:R,3:D,3:DR,3:b,100:-')
                s92 = sb2 = bend = None; hits = []
                for f, k in enumerate(keys):
                    g.pad = [set(k), set()]
                    if keep or f < 12: g.w(PL.P2 + 0x80, 2, (g.r(PL.P1 + 0x80) + gap) & 0xFFFF)
                    l0 = g.r(PL.P2 + 0x17E)
                    g.core.retro_run(); g.frame += 1
                    m = g.r(PL.P1 + 0x74)
                    if m == 0x92 and s92 is None: s92 = f
                    if m == 0xB2 and sb2 is None: sb2 = f
                    if 'b' in k: bend = f
                    if s92 is not None and g.r(PL.P2 + 0x17E) < l0: hits.append(f - s92)
                rows.append({'b_press_end': bend - s92, 'sougetsu_from': None if sb2 is None else sb2 - s92, 'hits': hits,
                             'class': 78 if style else 0})
            key = f'{sname} {"hit" if not keep else "whiff"}'
            res[key] = rows
            print(key, [(r['b_press_end'], r['sougetsu_from']) for r in rows], flush=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, 'w'), indent=0)
    ok = (all(r['sougetsu_from'] is None for k, v in res.items() if not k.startswith(('Speed hit', 'EX hit')) for r in v)
          and any(r['sougetsu_from'] for r in res['Speed hit']) and any(r['sougetsu_from'] for r in res['EX hit']))
    print('LB2: Sougetsu only in Speed / EX and only after Shingetsu hit:', ok)

STEP, N = 3, 24

def game(out):
    os.makedirs(out, exist_ok=True)
    g = PL.core(); g.load_state(f'{PL.STA}/vs.state'); g.frame = 0; g.w(PL.P1 + 0x17A, 1, 1)
    keys = PL.expand('2:-,3:R,3:D,3:DR,3:a,8:-,3:R,3:D,3:DR,3:b,120:-'); start = None; k = 0
    for f, kk in enumerate(keys):
        g.pad = [set(kk), set()]
        if f < 12: g.w(PL.P2 + 0x80, 2, (g.r(PL.P1 + 0x80) + 60) & 0xFFFF)
        if start is None and g.r(PL.P1 + 0x74) == 0x92: start = f
        if start is not None and (f - start) % STEP == 0 and k < N: g.screenshot(f'{out}/game_{k:02d}.png'); k += 1
        else: g.core.retro_run(); g.frame += 1

def brawler(out):
    sys.path.insert(0, os.path.join(HERE, '..', 'brawler', 'chainlab')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
    import harness
    from labdrive import Lab
    game_dir = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')); harness.GAME = game_dir
    L = Lab(rom='/data/tmp/lb2_t456/shell_moriya.neo', game=game_dir, build='build_shell'); b = L.b   # (lab_pack.py apply: shell + pack)
    G = json.load(open(os.path.join(game_dir, 'game.json'))); names = [r['name'] for r in G['roster']]
    os.makedirs(out, exist_ok=True)
    L.start(len(names), names.index('ryo')); b.run(30)
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 90
    b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.place(2, x=x0 + 40, z=30); b.fset(2, 'facing', 0xFF); b.run(1)
    start = None; k = 0
    for i in range(200):
        if start is None and b.states[b.fget(0, 'state')] == 'SPECIAL': start = i
        if start is not None and (i - start) % STEP == 0 and k < N: b.screenshot(f'{out}/brawler_{k:02d}.png'); k += 1
        else: b.run(1, p1='c' if i < 2 or (10 <= i < 12) else '')

def sheet(out):
    from PIL import Image, ImageDraw
    rows = []
    for side, lab in (('game', 'LB2 (Speed)'), ('brawler', 'brawler')):
        ims = [Image.open(p).convert('RGB').crop((0, 30, 240, 224)) for k in range(N) if os.path.exists(p := f'{out}/{side}_{k:02d}.png')]
        w, h = ims[0].size; per = 12
        for r0 in range(0, len(ims), per):
            row = Image.new('RGB', (110 + per * (w // 2 + 2), h // 2 + 2), 'white')
            ImageDraw.Draw(row).text((4, 4), f'{lab}\nframes {r0 * STEP}-{(r0 + per - 1) * STEP}\nevery {STEP}', fill='black')
            for k, im in enumerate(ims[r0:r0 + per]): row.paste(im.resize((w // 2, h // 2)), (110 + k * (w // 2 + 2), 1))
            rows.append(row)
    W = max(r.size[0] for r in rows); H = sum(r.size[1] + 4 for r in rows)
    sh = Image.new('RGB', (W, H), 'white'); y = 0
    for r in rows: sh.paste(r, (0, y)); y += r.size[1] + 4
    sh.save(f'{out}/sougetsu.png'); print(f'{out}/sougetsu.png', sh.size)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] in ('game', 'brawler', 'sheet'): {'game': game, 'brawler': brawler, 'sheet': sheet}[a[0]](a[1] if len(a) > 1 else '/data/tmp/lb2_t456/sougetsu')
    else: main(*a)
