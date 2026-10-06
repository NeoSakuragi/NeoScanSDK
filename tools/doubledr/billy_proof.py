#!/usr/bin/env python3
"""Billy Lee (Double Dragon 1995, tools/doubledr/export_dd.py) and his transformed form in the brawler, proved in the
harness (tools/brawler/harness.py: the game's ROM on the Geolith core, our emulator's core). Made from
tools/kizuna/kim_proof.py; the reference is Double Dragon's own drawing of each sprite definition (dd.draw_def, = the
game's VRAM: proof_dd.py, check.json).

    python3 billy_proof.py [OUTDIR]          (default /data/tmp/billy/out)

1. frames: Billy Lee picked on the select screen (the real path), then (Chain Lab training, lab req 1) each form in
   turn: every exported frame (moves, every variant row's animations, the transformation, the rings), both facings,
   shown through the game's renderer (fighter_t.frame_ovr); the sprites read back from VRAM (SCB1-4 of P1's block, the
   brawler's C ROM) as pen + palette index vs DD's drawing of the definition(s) the frame came from, aligned on the
   first opaque pixel -> frames_<form>_<facing>.png (every other frame)
2. specials with the pad against the training dummy (each C slot, the fury): hits, the row played (fighter_t.var =
   bspec_t.vdef); then every row of each variant special (var poked on its first frame; the table is read from then
   on): travel and height per row vs the DD model of that button -> specials.png
3. the form link -> form.png / form.json (see form_proof)"""
import json, os, re, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'kizuna'))
import dd, model_dd as M, export_dd as E
from harness import Brawler
from kim_proof import lab_req, tiles_of, block_image, crop_nz
from PIL import Image, ImageDraw
import ctypes as C

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/billy/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
FORMS = {'billy_lee': 'billy', 'billy_super': 'billy_super'}       # roster name -> bank
FAKE = {'body': 255, 'form': 253}                                   # palette keys drawn through dd.draw_def

def ref_image(layers, pals):
    """DD's drawing (dd.draw_def: the game's VRAM) of the frame's definition layers, facing left (the art's), as
    (0x80 + the export's palette index) * 16 + pen"""
    pw = [(i & 0x0FFF) for i in range(4096)]                       # a colour per (slot, pen): the drawing decodes back
    key_of = {v: k for k, v in FAKE.items()}
    img = np.zeros((640, 640), np.uint16)
    for w, ox, oy, key in layers:
        a = dd.draw_def(w, pw, palette=FAKE.get(key, key), hflip=False, size=(640, 640), origin=(320 + ox, 400 + oy))
        m = a[..., 3] > 0
        if not m.any(): continue
        c5 = a[..., :3].astype(int) >> 3
        raw = ((c5[..., 0] >> 1) << 8) | ((c5[..., 1] >> 1) << 4) | (c5[..., 2] >> 1)
        slot, pen = raw >> 4, raw & 15
        lut = {}
        for s_ in np.unique(slot[m]):
            k = key_of.get(int(s_), str(int(s_)))
            lut[int(s_)] = pals.index(k) if k in pals else 0x70
        idx = np.vectorize(lambda s_: lut.get(int(s_), 0x70))(slot)
        img = np.where(m & (pen > 0), ((0x80 + idx) * 16 + pen).astype(np.uint16), img)
    return img

def setup():
    b = Brawler(game=GAME)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    idx = {n: bcs.index('BC_' + n.upper()) for n in FORMS}
    b.pick(idx['billy_lee'])
    assert b.char_of(0) == idx['billy_lee'], b.char_of(0)
    return b, idx

def bank(rname):
    bk = FORMS[rname]
    return json.load(open(os.path.join(GAME, 'build', f'tmp_doubledr_{bk}', 'kof95_export.json')))['characters'][bk]

def frames_proof(b, idx, res):
    crom = tiles_of(b.rom)
    b.core.retro_get_memory_data.restype = C.c_void_p
    vram = (C.c_uint16 * 65536).from_address(b.core.retro_get_memory_data(101))
    for rname in FORMS:
        ex = bank(rname); pals = ex['modes']['palettes']
        used = sorted({p.get('pal', 0) for fr in ex['frames'] for p in fr['parts']})
        lab_req(b, 1, idx[rname], 0); b.run(60)
        assert b.char_of(0) == idx[rname], (rname, b.char_of(0))
        same = diff = 0; worst = []
        for facing in (1, -1):
            cells = []
            for fi, fr in enumerate(ex['frames']):
                for _ in range(2):
                    b.fset(0, 'facing', facing & 0xFF); b.fset(0, 'frame_ovr', fi); b.fset(0, 'shown_frame', 0xFFFF); b.run(1)
                b.fset(0, 'frame_ovr', fi); b.fset(0, 'facing', facing & 0xFF)
                got = crop_nz(block_image(b, vram, crom, used))
                ref = ref_image(fr['layers'], pals)
                ref = crop_nz(ref if facing < 0 else ref[:, ::-1])
                if got.shape == ref.shape and (got == ref).all(): same += 1
                else: diff += 1; worst.append((fi, fr['record'], facing, got.shape, ref.shape))
                if fi % 2 == 0:
                    p = os.path.join(OUT, '_shot.png'); b.screenshot(p)
                    x = int(b.fget(0, 'x')) - b.r(b.syms['cam_x'], 2); im = Image.open(p)
                    cells.append(im.crop((x - 110, 0, x + 110, im.height)).resize((110, 112)))
            cols = 20
            sheet = Image.new('RGB', (110 * cols, 112 * ((len(cells) + cols - 1) // cols)), 'white')
            for j, c in enumerate(cells): sheet.paste(c, ((j % cols) * 110, (j // cols) * 112))
            sheet.save(os.path.join(OUT, f'frames_{rname}_{"right" if facing > 0 else "left"}.png'))
        res['frames'][rname] = {'identical': same, 'differ': diff, 'frames': len(ex['frames']), 'both_facings': True, 'worst': worst[:8]}
        print(rname, 'frames vs DD:', same, 'identical,', diff, 'differ', worst[:4], flush=True)
        b.fset(0, 'frame_ovr', 0xFFFF)

SLOTS = {'D': 'c', 'fD': 'Rc', 'dD': 'Dc', 'uD': 'Uc'}
def place(b, dist):
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    cam = b.r(b.syms['cam_x'], 2)
    b.place(0, x=cam + 80, z=30); b.place(dm, x=cam + 80 + dist, z=30); b.fset(0, 'facing', 1); b.run(3)
    return dm

def play_special(b, idx, rname, keys, dist, var=None, frames=150):
    shots = var is None                                          # (a screenshot runs a frame: none while a row is poked)
    lab_req(b, 1, idx[rname], 0); b.run(40); b.fset(0, 'meter', 120)
    dm = place(b, dist)
    while b.states[b.fget(0, 'state')] != 'IDLE': b.run(1)
    x0 = b.fget(0, 'x'); h0 = len(b.hits); top = 0.0; xs = []; cells = []; row = None; srow0 = None
    for f in range(frames):
        b.run(1, p1=keys if f < 3 else '')
        st = b.states[b.fget(0, 'state')]
        if st == 'SPECIAL':
            if row is None:
                row = b.fget(0, 'var'); srow0 = b.fget(0, 'srow')
                if var is not None: b.fset(0, 'var', var); row = var
            top = max(top, b.fget(0, 'y')); xs.append(b.fget(0, 'x') - x0)
        elif row is not None and st in ('IDLE', 'WALK'): break
        if f % 6 == 0 and shots:
            p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).resize((160, 112)))
    return {'row': row, 'poked_at_row': srow0 if row is not None else None, 'hits': [(h[1], h[2], h[3]) for h in b.hits[h0:]], 'travel': round(xs[-1] if xs else 0, 1),
            'height': round(top, 1), 'frames': len(xs)}, cells

def specials_proof(b, idx, res):
    rows_img = []
    for rname, keyset in (('billy_lee', {**SLOTS, 'fury D': 'd'}), ('billy_super', SLOTS)):
        ex = bank(rname); g = json.load(open(os.path.join(GAME, 'game.json')))
        slots = next(r for r in g['roster'] if r['name'] == rname)['specials']
        for slot, keys in keyset.items():
            inp = next(r['fury'] for r in g['roster'] if r['name'] == rname) if slot == 'fury D' else slots.get(slot)
            if not inp: continue
            r, cells = play_special(b, idx, rname, keys, 70)
            res['specials'][f'{rname} {slot} {inp}'] = r
            rows_img.append((f'{rname} {slot} {inp}', cells))
            print(rname, slot, inp, r, flush=True)
            sp = next(s for s in ex['specials'] if s['input'] == inp)
            vt = sp['rom']['vtable']
            if not vt['nvar']: continue
            for v, a0 in enumerate(vt['anims']):              # every row: travel / height vs the model (far: a whiff)
                got, _ = play_special(b, idx, rname, keys, 300, var=v)
                ref = M.play(ex['id'], a0)
                want = {'travel': round(ref[-1]['x'], 1), 'height': round(max(q['y'] for q in ref), 1)}
                res['variants'][f'{rname} {inp} {"ABCD"[v]}'] = {'brawler': got, 'dd_model': want}
                print('   row', 'ABCD'[v], got, 'model', want, flush=True)
    W = 160 * max(len(c) for _, c in rows_img) + 200
    sheet = Image.new('RGB', (W, 112 * len(rows_img)), 'white'); d = ImageDraw.Draw(sheet)
    for i, (nm, cells) in enumerate(rows_img):
        d.text((4, i * 112 + 4), nm, fill='black')
        for j, c in enumerate(cells): sheet.paste(c, (200 + j * 160, i * 112))
    sheet.save(os.path.join(OUT, 'specials.png'))

def form_proof(b, idx, res):
    """the form link in the campaign (stage 1, the enemies' own AI, the fight right after the select screen): life set
    to 37 (life carried: not the training's refilled one), down+D with a full meter once an enemy attacks within reach:
    the transition (untouchable: no hit on P1 while it plays), the swap in the air, the landing as the transformed form,
    hit again by the enemies afterwards; then life 1 until a life is lost: back to Billy Lee (exit 'life')"""
    out = {}
    b.pick(idx['billy_lee'])
    for _ in range(900):                                           # an enemy attacking within reach
        b.run(1)
        near = [i for i in range(2, 8) if b.states[b.fget(i, 'state')] == 'ATTACK' and abs(b.fget(i, 'x') - b.fget(0, 'x')) < 90]
        if near and b.states[b.fget(0, 'state')] in ('IDLE', 'WALK'): break
    b.fset(0, 'hp', 37); b.fset(0, 'meter', 120)
    hp0, x0, face0, f0, h0 = b.fget(0, 'hp'), b.fget(0, 'x'), b.fget(0, 'facing'), b.frame, len(b.hits)
    tl, cells = [], []
    for k in range(140):
        b.run(1, p1='Dd' if k < 3 else '')
        tl.append({'f': b.frame - f0, 'state': b.states[b.fget(0, 'state')], 'ch': b.char_of(0), 'spec_id': b.fget(0, 'spec_id'),
                   'y': round(b.fget(0, 'y'), 1), 'x': round(b.fget(0, 'x'), 1), 'hp': b.fget(0, 'hp'), 'inv': b.fget(0, 'inv'),
                   'enemies': [(i, b.states[b.fget(i, 'state')], round(b.fget(i, 'x') - b.fget(0, 'x'))) for i in range(2, 8) if b.states[b.fget(i, 'state')] != 'OFF']})
        if k % 3 == 0:
            p = os.path.join(OUT, '_shot.png'); b.screenshot(p)
            im = Image.open(p); d = ImageDraw.Draw(im); t = tl[-1]
            d.rectangle([0, 196, 200, 212], fill='black'); d.text((4, 198), f"t{t['f']} {t['state']} ch{t['ch']} y{t['y']} hp{t['hp']}", fill='white')
            cells.append(im)
    trans = [t for t in tl if t['state'] == 'SPECIAL' and t['spec_id'] == 8 and t['ch'] == idx['billy_lee']]
    t_start = trans[0]['f'] if trans else None
    swap = next((t for t in tl if t['ch'] == idx['billy_super']), None)
    land = next((t for t in tl if swap and t['f'] > swap['f'] and t['y'] == 0), None)
    hits = b.hits[h0:]
    in_trans = [h for h in hits if h[1] == 0 and trans and trans[0]['f'] + f0 <= h[0] <= trans[-1]['f'] + f0]
    out['transition'] = {'started_at': t_start, 'frames': len(trans), 'swap_at': swap and swap['f'], 'swap_height': swap and swap['y'],
                         'landed_at': land and land['f'], 'hp_before': hp0, 'hp_at_swap': swap and swap['hp'], 'x_before': x0,
                         'x_at_swap': swap and swap['x'], 'facing_kept': True if swap is None else b.fget(0, 'facing') == face0,
                         'untouchable_frames': sum(1 for t in trans if t['inv'] == 255), 'p1_hits_during_transition': in_trans,
                         'enemy_attacks_during': sum(1 for t in trans for e in t['enemies'] if e[1] == 'ATTACK'),
                         'hits_on_enemies_during': [h for h in hits if h[1] >= 2 and trans and h[0] - f0 <= trans[-1]['f']],
                         'end_state': tl[-1]['state'], 'end_ch': tl[-1]['ch']}
    h1 = len(b.hits)
    for _ in range(600):                                           # the enemies go on: P1 hittable as the new form
        b.run(1)
        if any(h[1] == 0 for h in b.hits[h1:]): break
    out['after'] = {'p1_hit_again': [h for h in b.hits[h1:] if h[1] == 0][:1], 'ch': b.char_of(0)}
    b.run(1, p1='Dd'); b.run(2)                                    # the transformed form has no form link of its own
    out['second_trigger'] = {'state': b.states[b.fget(0, 'state')], 'spec_id': b.fget(0, 'spec_id'), 'ch': b.char_of(0)}
    lives = b.r(b.syms['lives'], 1) if 'lives' in b.syms else None
    for _ in range(1500):                                          # a life lost
        if b.fget(0, 'hp') > 1: b.fset(0, 'hp', 1)
        b.run(1)
        if b.char_of(0) == idx['billy_lee']: break
    out['life_lost'] = {'ch': b.char_of(0), 'form_from': b.fget(0, 'form_from'), 'state': b.states[b.fget(0, 'state')],
                        'lives_before': lives, 'lives_after': b.r(b.syms['lives'], 1) if 'lives' in b.syms else None}
    out['timeline'] = tl
    res['form'] = out
    cols = 8; W, H = 320, 224
    sheet = Image.new('RGB', (W * cols, H * ((len(cells) + cols - 1) // cols)))
    for i, c in enumerate(cells): sheet.paste(c.resize((W, H)), ((i % cols) * W, (i // cols) * H))
    sheet.save(os.path.join(OUT, 'form.png'))
    print('form', {k: v for k, v in out.items() if k != 'timeline'}, flush=True)

def main():
    os.makedirs(OUT, exist_ok=True)
    b, idx = setup()
    res = {'frames': {}, 'specials': {}, 'variants': {}}
    which = sys.argv[2:] or ['frames', 'specials', 'form']
    if 'form' in which: form_proof(b, idx, res)
    if 'specials' in which: specials_proof(b, idx, res)
    if 'frames' in which: frames_proof(b, idx, res)
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1, default=str)

if __name__ == '__main__':
    main()
