#!/usr/bin/env python3
"""WHP's six buttons in the brawler (moves_whp.py, export_whp.py): the proof, in our emulator only.

    python3 six_button_proof.py OUTDIR       (a built examples/brawler; BRAWLER_CORE = the Geolith core)

1. inventory.json / inventory.html: every WHP normal by button x stance (the ROM's action tables), the brawler move it is
   exported as, before (export_whp at de1e462) and after; the game check (normals_check.json: the animation WHP plays
   = the decode, its frames = the ROM's) and every special's three strength rows (specials_check.json).
2. normals_right.png / normals_left.png: each newly exported normal (and the corrected air C+D), every step shown by the
   game's renderer (frame_ovr in the Chain Lab training, P1 = Hanzou) next to WHP's own drawing of the def it came
   from (whp.render_def, = WHP's VRAM), both facings; the frame check: the brawler's sprites read back from VRAM vs
   WHP's drawing, pixel for pixel (hanzo_proof.py's method).
3. routes.json: each new move placed in a route (a one-node tree per move: the root A link, the air ones as the jump's
   air_a entry) and played with the pad in the training: the animation P1 plays = the move (BA_*), its hit on the
   dummy; the Chain Lab's data (build/chainlab.json: Hanzou's 'has' and the route cards) and its move pictures
   (chainlab/move_images.py -> moves/hanzo.png).
4. throws.png / throws.json: Hanzou's forward / back throw (A+B close in WHP; the brawler's walk-in grab + forward /
   back + A): WHP's frames (throw_capture.py: Hanzou throws Fuuma) above, the brawler's below (Hanzou throws Hanzou),
   every 4th frame from the throw's first; the model vs WHP (throw_check.py) and the brawler's rows / damage."""
import json, os, re, sys, subprocess, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler', 'chainlab'))
import whp, moves_whp as MW
from PIL import Image, ImageDraw
import ctypes as C
import hanzo_proof as HP

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
NAME = 'hanzo'
# export_whp.MOVES at de1e462 (0.0.84): the normals the brawler had
BEFORE = {'atk_a_close': 0x58, 'atk_a_far': 0x40, 'atk_b_close': 0x5C, 'atk_b_far': 0x44, 'atk_c_close': 0x64, 'atk_c_far': 0x4C,
          'atk_d_close': 0x68, 'atk_d_far': 0x50, 'atk_a_crouch': 0x70, 'atk_b_crouch': 0x71, 'atk_c_crouch': 0x74,
          'atk_d_crouch': 0x75, 'atk_c_jump': 0x84, 'atk_d_jump': 0x85, 'atk_c_jump_diag': 0x8C, 'atk_d_jump_diag': 0x8D,
          'atk_cd_jump': 0x8D, 'body_toss': 0x54}

def inventory():
    ex = json.load(open(os.path.join(GAME, 'build', f'tmp_whp_{NAME}', 'kof95_export.json')))['characters'][NAME]
    nc = json.load(open(os.path.join(OUT, 'normals_check.json')))
    sc = json.load(open(os.path.join(OUT, 'specials_check.json')))
    rows = []
    for n in ex['whp_normals']:
        k = f"{n['button']}:{n['stance']}"; bn = n['brawler']
        before = next((m for m, a in BEFORE.items() if a == n['rel'] and (bn is None or m == bn)), None) if n['same_as'] is None else None
        if bn is None: status = f"= {n['same_as']}"
        elif before is None: status = 'ADDED'
        else: status = 'kept'
        if bn == 'atk_cd_jump': status = 'FIXED (was $8D: the diagonal D)'
        g = nc.get(k, {})
        rows.append({'button': n['button'], 'strength': n['strength'], 'stance': n['stance'], 'whp_anim': f"${n['rel']:X}",
                     'close_px': n.get('close_px'), 'brawler_before': before, 'brawler_after': bn, 'status': status,
                     'whp_plays': g.get('game'), 'same_animation': g.get('same_animation'),
                     'frames': f"{g.get('frames_identical')}/{g.get('frames_compared')}"})
    sp = []
    for s in ex['whp_specials']:
        for r in s['rows']:
            c = sc.get(f"{s['input']}:{r['button']}", {})
            sp.append({'input': s['input'], 'button': r['button'], 'strength': r['strength'], 'whp_anim': f"${r['rel']:X}",
                       'exported': s['exported'], 'why': s['why'], 'distinct_rows': s['distinct'],
                       'model_vs_whp': f"{c.get('identical')}/{c.get('frames')}", 'x_bound_from': c.get('x_from_bound'),
                       'travel': c.get('travel'), 'height': c.get('height'),
                       'projectile': (f"{sum(o['frames'] - o['mismatches'] for o in c['projectile'])}/{sum(o['frames'] for o in c['projectile'])} frames ({len(c['projectile'])} objects)"
                                      if isinstance(c.get('projectile'), list) else
                                      f"{c['projectile']['flight_frames'] - c['projectile']['mismatches']}/{c['projectile']['flight_frames']} frames" if c.get('projectile') else None)})
    json.dump({'normals': rows, 'specials': sp}, open(os.path.join(OUT, 'inventory.json'), 'w'), indent=1)
    def table(rs, cols):
        h = '<tr>' + ''.join(f'<th>{c}</th>' for c in cols) + '</tr>'
        return '<table>' + h + ''.join('<tr>' + ''.join(f'<td>{"" if r[c] is None else r[c]}</td>' for c in cols) + '</tr>' for r in rs) + '</table>'
    html = ('<!doctype html><meta charset="utf-8"><title>Hanzo six buttons</title><style>body{font:13px sans-serif;background:#fff;color:#000}'
            'table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #000;padding:2px 6px}</style>'
            '<h2>Hanzo: WHP normals by button x stance (the ROM\'s tables) vs the brawler, before / after</h2>'
            + table(rows, ['button', 'strength', 'stance', 'whp_anim', 'close_px', 'brawler_before', 'brawler_after', 'status', 'whp_plays', 'same_animation', 'frames'])
            + '<h2>Specials: every command, its three strength rows</h2>'
            + table(sp, ['input', 'button', 'strength', 'whp_anim', 'exported', 'why', 'distinct_rows', 'model_vs_whp', 'x_bound_from', 'travel', 'height', 'projectile']))
    open(os.path.join(OUT, 'inventory.html'), 'w').write(html)
    added = [r['brawler_after'] for r in rows if r['status'] == 'ADDED' or r['status'].startswith('FIXED')]
    print('normals', len(rows), 'stances;', len([r for r in rows if r['brawler_after']]), 'exported moves;', len(added), 'added / fixed:', added)
    return ex, added

def main():
    ex, added = inventory()
    from labdrive import Lab
    import routes as R, export_bm
    MOVES = export_bm.MOVES
    lab = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
    me = next(f for f in lab['fighters'] if f['name'] == NAME)
    ci = me['id']
    L = Lab(); b = L.b
    pals = [int(p, 16) for p in ex['modes']['palettes']]
    used = sorted({p.get('pal', 0) for fr in ex['frames'] for p in fr['parts']})
    crom = HP.tiles_of(b.rom)
    b.core.retro_get_memory_data.restype = C.c_void_p
    L.start(ci, ci); b.run(30)
    vram = (C.c_uint16 * 65536).from_address(b.core.retro_get_memory_data(3))   # RETRO_MEMORY_VIDEO_RAM
    # 2. frames, both facings
    show = added + ['throw_c', 'throw_d']
    same = diff = 0; worst = []
    for facing in (1, -1):
        rows = []
        for m in show:
            a = ex['anims'][m]; cells = []
            for st in a['steps']:
                fi = st['frame']
                for _ in range(2):
                    b.fset(0, 'facing', facing & 0xFF); b.fset(0, 'frame_ovr', fi); b.fset(0, 'shown_frame', 0xFFFF); b.run(1)
                p = os.path.join(OUT, '_shot.png'); b.screenshot(p)
                x = int(b.fget(0, 'x')) - b.r(b.syms['cam_x'], 2); im = Image.open(p).convert('RGB')
                got = HP.crop_nz(HP.block_image(b, vram, crom, used))
                refi = HP.ref_image(int(ex['frames'][fi]['record'].split('+')[0].split('@')[0], 16), pals)
                ref = HP.crop_nz(refi if facing > 0 else refi[:, ::-1])
                ok = got.shape == ref.shape and (got == ref).all()
                if ok: same += 1
                else: diff += 1; worst.append((m, facing, fi, got.shape, ref.shape))
                # WHP's drawing of the def (render facing right; mirrored for the left-facing row)
                w = int(ex['frames'][fi]['record'].split('+')[0].split('@')[0], 16)
                img = np.zeros((240, 240), np.uint16); whp.render_def(img, w, (128 + 120) * 128, (352 - 210) * 128)
                wi = Image.new('RGB', (240, 240), 'white'); px = wi.load(); P = {}
                for yy, xx in zip(*np.nonzero(img)):
                    v = int(img[yy, xx]); c = P.get(v)
                    if c is None:
                        cc = whp.palette(v >> 4)[v & 15]
                        c = P[v] = (((cc >> 7) & 0x1E | (cc >> 14) & 1) * 8, ((cc >> 3) & 0x1E | (cc >> 13) & 1) * 8, ((cc << 1) & 0x1E | (cc >> 12) & 1) * 8)
                    px[xx, yy] = c
                if facing < 0: wi = wi.transpose(Image.FLIP_LEFT_RIGHT)
                cell = Image.new('RGB', (240, 480), 'white'); cell.paste(wi, (0, 0)); cell.paste(im.crop((x - 120, im.height - 240, x + 120, im.height)), (0, 240))
                ImageDraw.Draw(cell).text((4, 4), f'WHP {w:04X}', fill='black'); ImageDraw.Draw(cell).text((4, 244), 'brawler ' + ('=' if ok else 'DIFF'), fill='black')
                cells.append(cell.resize((160, 320)))
            rows.append((m, cells))
        W = 160 * max(len(c) for _, c in rows) + 130; H = 320
        sheet = Image.new('RGB', (W, H * len(rows)), 'white'); d = ImageDraw.Draw(sheet)
        for i, (m, cells) in enumerate(rows):
            d.text((4, i * H + 4), m, fill='black')
            for j, c in enumerate(cells): sheet.paste(c, (130 + j * 160, i * H)); d.rectangle([130 + j * 160, i * H, 130 + j * 160 + 159, i * H + H - 1], outline='black')
        sheet.save(os.path.join(OUT, f'normals_{"right" if facing > 0 else "left"}.png'))
    b.fset(0, 'frame_ovr', 0xFFFF)
    print(f'frames vs WHP: {same} identical, {diff} differ', worst[:6])
    # 3. each new move in a route, played with the pad
    rres = {}
    air = {'atk_a_jump': 'atk_a_jump', 'atk_a_jump_diag': 'atk_a_jump', 'atk_b_jump': 'atk_b_jump', 'atk_b_jump_diag': 'atk_b_jump',
           'atk_ab_jump': 'atk_ab_jump', 'atk_ab_jump_diag': 'atk_ab_jump', 'atk_cd_jump': 'atk_cd_jump', 'atk_cd_jump_diag': 'atk_cd_jump'}
    for m in added:
        if m in air:
            tree = {'links': {'A': {'move': 'atk_a_far'}}, 'entries': {'air_a': {'move': air[m], 'weight': 'strong', 'effect': 'none'}}}
            script = ('10:b,3:-,3:a,40:-' if not m.endswith('diag') else '10:Rb,3:R,3:a,40:-')   # B held through the prejump: the regular jump
        else:
            tree = {'links': {'A': {'move': m, 'weight': 'strong', 'effect': 'none'}}}
            script = '3:a,50:-'
        blob = list(R.encode(tree, MOVES, set(me['has']) | set(R.AIR_MOVE_NAMES)))
        L.start(ci, ci, blob); b.run(20)
        cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 100, z=30); b.place(2, x=cam + 140, z=30); b.fset(0, 'facing', 1); b.run(3)
        h0 = len(b.hits); seen = []
        for part in script.split(','):
            n, k = part.split(':')
            for _ in range(int(n)):
                b.run(1, p1=k.replace('-', ''))
                a = MOVES[b.fget(0, 'anim')] if b.fget(0, 'anim') < len(MOVES) else b.fget(0, 'anim')
                if not seen or seen[-1] != a: seen.append(a)
        rres[m] = {'played': m in seen, 'anims': seen, 'hits_on_dummy': [(h[1], h[2]) for h in b.hits[h0:]]}
        print(m, 'played' if m in seen else 'NOT played', seen, 'hits', rres[m]['hits_on_dummy'])
    import move_images
    pics = move_images.move_images(GAME, OUT, [NAME], R.MOVE_NAMES + R.AIR_MOVE_NAMES)
    lab_list = {'route_cards': R.MOVE_NAMES, 'air_cards': R.AIR_MOVE_NAMES, 'hanzo_has': me['has'],
                'new_on_cards': [m for m in added if m in R.MOVE_NAMES + R.AIR_MOVE_NAMES + ['atk_a_jump_diag', 'atk_b_jump_diag', 'atk_ab_jump_diag', 'atk_cd_jump_diag']],
                'pictures': sorted(pics.get(NAME, {}).get('moves', {}))}
    json.dump({'routes': rres, 'lab': lab_list}, open(os.path.join(OUT, 'routes.json'), 'w'), indent=1)
    # 4. throws: the brawler's (walk-in grab, then forward / back + A), every 4th frame, next to WHP's
    tres = {}; strips = []
    wcap = json.load(open('/data/tmp/whp6/throw_cap.json'))
    for t, key, rel in (('throw_c', 'fwd', 0xD1), ('throw_d', 'back', 0xD3)):
        L.start(ci, ci); b.run(20)
        cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 120, z=30); b.place(2, x=cam + 180, z=30); b.fset(0, 'facing', 1); b.run(3)
        st0 = None; cells = []; hp0 = b.fget(2, 'hp'); trace = []
        for f in range(40):
            b.run(1, p1='R')
            if b.states[b.fget(0, 'state')] == 'GRAB': break
        grabbed = b.states[b.fget(0, 'state')]
        for f in range(200):
            b.run(1, p1=('Ra' if key == 'fwd' else 'La') if f < 3 else '')
            s = b.states[b.fget(0, 'state')]
            if s == 'THROW' and st0 is None: st0 = f
            trace.append((s, b.states[b.fget(2, 'state')], round(b.fget(2, 'x') - b.fget(0, 'x'), 1), round(b.fget(2, 'y'), 1), b.fget(2, 'hp')))
            if st0 is not None and (f - st0) % 4 == 0 and len(cells) < 40:
                p = os.path.join(OUT, '_shot.png'); b.screenshot(p); x = int(b.fget(0, 'x')) - cam
                cells.append(Image.open(p).convert('RGB').crop((max(0, x - 100), 40, max(0, x - 100) + 260, 224)))
        tres[t] = {'grab_state': grabbed, 'throw_started_frame': st0, 'victim_hp_drop': hp0 - min(x[4] for x in trace), 'victim_x_end': trace[-1][2], 'trace': trace[:160]}
        # WHP's frames (the capture), drawn from the defs both fighters show
        fr = wcap[key]; s0 = next(i for i, q in enumerate(fr) if q[0]['anim'] == rel); wc = []
        for i in range(s0, min(len(fr), s0 + 160), 4):
            img = np.zeros((184, 260), np.uint16); x0 = fr[s0][0]['x'] - 80
            for q in fr[i]:
                whp.render_def(img, q['defw'], int((q['x'] - x0 + 128) * 128), int((352 - 170 + q['y']) * 128), hflip=q['flip'])
            wi = Image.new('RGB', (260, 184), 'white'); px = wi.load()
            for yy, xx in zip(*np.nonzero(img)):
                v = int(img[yy, xx]); cc = whp.palette(v >> 4)[v & 15]
                px[xx, yy] = (((cc >> 7) & 0x1E | (cc >> 14) & 1) * 8, ((cc >> 3) & 0x1E | (cc >> 13) & 1) * 8, ((cc << 1) & 0x1E | (cc >> 12) & 1) * 8)
            wc.append(wi)
        strips.append((t + ' WHP', wc)); strips.append((t + ' brawler', cells))
        print(t, 'grab', grabbed, 'throw from frame', st0, 'victim hp drop', tres[t]['victim_hp_drop'])
    W = 130 + 130 * max(len(c) for _, c in strips); H = 92
    sheet = Image.new('RGB', (W, H * len(strips)), 'white'); d = ImageDraw.Draw(sheet)
    for i, (nm, cells) in enumerate(strips):
        d.text((4, i * H + 4), nm, fill='black')
        for j, c in enumerate(cells): sheet.paste(c.resize((130, 92)), (130 + j * 130, i * H))
    sheet.save(os.path.join(OUT, 'throws.png'))
    tc = subprocess.run([sys.executable, os.path.join(HERE, 'throw_check.py'), '/data/tmp/whp6/throw_cap.json'], capture_output=True, text=True).stdout
    json.dump({'brawler': tres, 'model_vs_whp': tc}, open(os.path.join(OUT, 'throws.json'), 'w'), indent=1)
    json.dump({'frames_same': same, 'frames_differ': diff, 'differ': worst}, open(os.path.join(OUT, 'frames.json'), 'w'), default=str)

if __name__ == '__main__':
    main()
