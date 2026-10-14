#!/usr/bin/env python3
"""T4 (2026-10-14): Moriya's normals and their slash trails, The Last Blade 2 vs the brawler, side by side.

LB2 [code]: a normal's animation script spawns its trail as a LINKED FRAME object ($AE, OBJ LNK: a frame record of his
own, pinned to him for the script step it starts in; model_lb2 events 'spawn' $AE); the slashes A / B / crouching A / B /
jumping A / forward B carry them, the kicks (C, D, crouching C / D, jumping B / C) none. In the brawler (export_lb2
anim_steps) the trail is drawn as part of his frame for those steps (a composite frame: body + trail, the trail's layers
in front, at the object's offset), no engine change.

    python3 normals_fx_lb2.py list                 the normals' trail spawns from the scripts (model_lb2)
    python3 normals_fx_lb2.py game OUT             LB2 in our emulator (vs.state, P2 kept away): every frame from the move's
                                                   start (one core per process)
    python3 normals_fx_lb2.py brawler OUT          the brawler (his pack build, our emulator): each normal as the TRY
                                                   chain's A press (LE_MOVE | BA_*), every frame
    python3 normals_fx_lb2.py sheet OUT            -> OUT/normals_fx.png (rows: LB2, brawler; every 2nd frame)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# (brawler move, LB2 input from vs.state, its LB2 animation)
MOVES = [('atk_a_far', '3:a', 0x31, 'stand A'), ('atk_b_far', '3:b', 0x34, 'stand B'), ('body_toss', '3:R,3:Rb', 0x91, 'forward B'),
         ('atk_a_crouch', '3:D,3:Da', 0x37, 'crouch A'), ('atk_b_crouch', '3:D,3:Db', 0x38, 'crouch B'),
         ('atk_c_far', '3:c', 0x35, 'stand C (kick)')]
N, STEP = 24, 2
SHELL = '/data/tmp/lb2_t456/shell_moriya.neo'   # lab_pack.py apply examples/brawler/lab-shell.neo packs/moriya.pack SHELL

def lst():
    import export_lb2 as X, handlers_lb2 as H
    for a in sorted(set(X.MOVES.values())):
        rows, ev = X.timeline(1, a)
        sp = [(e[0], H.spawn_info(e[2], e[3])) for e in ev if e[1] == 'spawn']
        lk = [(k, f"{i['word'] & 0xFFF:X}", i['fwd'], i['up']) for k, i in sp if i['kind'] == 'lnk']
        if lk: print(f'anim ${a:02X}', [m for m, v in X.MOVES.items() if v == a], 'trails (row, frame, fwd, up):', lk)

def game(out):
    import play_lb2 as PL
    os.makedirs(out, exist_ok=True)
    g = PL.core()
    for mv, seq, a, _ in MOVES:
        g.load_state(f'{PL.STA}/vs.state'); g.frame = 0
        keys = PL.expand('2:-,' + seq + ',60:-'); start = None; k = 0
        for f, kk in enumerate(keys):
            g.pad = [set(kk), set()]
            g.w(PL.P2 + 0x80, 2, (g.r(PL.P1 + 0x80) + 250) & 0xFFFF)
            if start is None and g.r(PL.P1 + 0x72) == a: start = f
            if start is not None and k < N:
                g.screenshot(f'{out}/game_{mv}_{k:02d}.png'); k += 1
            else: g.core.retro_run(); g.frame += 1

def brawler(out):
    sys.path.insert(0, os.path.join(HERE, '..', 'brawler', 'chainlab')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
    import harness
    from labdrive import Lab
    import lb2_lab_proof as LP
    game = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')); harness.GAME = game
    L = Lab(rom=SHELL, game=game, build='build_shell'); b = L.b   # (the Lab shell + his pack: what the Lab plays)
    G = json.load(open(os.path.join(game, 'game.json'))); fid = len(G['roster'])
    hdr = open(os.path.join(game, 'build_pack_moriya', 'bm_chars.h')).read()
    ba = hdr[hdr.index('enum { BA_IDLE'):].split('}')[0].split('{')[1].replace(' ', '').split(',')
    lf = b.syms['lab_fields']
    names = [r['name'] for r in G['roster']]
    L.start(fid, names.index('ryo')); b.run(30); base = b.save()
    os.makedirs(out, exist_ok=True)
    for mv, _, a, _ in MOVES:
        b.load(base)
        blob = LP.encode({'chain': {'entries': [0x4000 | ba.index('BA_' + mv.upper())] * 4}, 'fighter': fid})   # (the TRY
                                                       # chain record: LE_MOVE | m = his move m as the chain's A press)
        L.poke(lf['tblob'], blob); L.poke(lf['lstat'], [0]); L.poke(lf['tnow'], [1]); L.poke(0, b'LAB1'); L.poke(5, [fid]); L.poke(7, [6])
        b.run(3)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 90
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + 250, z=30); b.fset(2, 'facing', 0xFF); b.run(2)
        started = None; k = 0
        for i in range(120):
            if started is None and b.states[b.fget(0, 'state')] == 'ATTACK':
                started = i
            if started is not None and k < N:
                b.screenshot(f'{out}/brawler_{mv}_{k:02d}.png'); k += 1
            else: b.run(1, p1='a' if i < 2 else '')

def sheet(out):
    from PIL import Image, ImageDraw
    rows = []
    for mv, _, a, name in MOVES:
        for side in ('game', 'brawler'):
            ims = [Image.open(p).convert('RGB').crop((0, 60, 200, 224)) for k in range(0, N, STEP)
                   if os.path.exists(p := f'{out}/{side}_{mv}_{k:02d}.png')]
            if not ims: continue
            w, h = ims[0].size
            row = Image.new('RGB', (130 + len(ims) * (w // 2 + 2), h // 2 + 2), 'white')
            d = ImageDraw.Draw(row); d.text((4, 4), f'{name}\n${a:02X} {mv}\n{"LB2" if side == "game" else "brawler"}', fill='black')
            for k, im in enumerate(ims): row.paste(im.resize((w // 2, h // 2)), (130 + k * (w // 2 + 2), 1))
            rows.append(row)
    W = max(r.size[0] for r in rows); H = sum(r.size[1] + 4 for r in rows)
    sh = Image.new('RGB', (W, H), 'white'); y = 0
    for r in rows: sh.paste(r, (0, y)); y += r.size[1] + 4
    sh.save(f'{out}/normals_fx.png'); print(f'{out}/normals_fx.png', sh.size)

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'list': lst()
    else: {'game': game, 'brawler': brawler, 'sheet': sheet}[cmd](sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/lb2_t456/normals')
