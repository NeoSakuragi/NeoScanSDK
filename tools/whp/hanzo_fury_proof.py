#!/usr/bin/env python3
"""Hanzou's fury (World Heroes Perfect's desperation move, tools/whp/handlers_whp.py + export_whp.fury) proved: WHP's
own frames, the model, the export, the brawler.

    python3 hanzo_fury_proof.py [OUTDIR]          (default /data/tmp/hanzofury/out; needs a build of examples/brawler)

1. WHP vs the model (handlers_whp.check): the DM and the hero DM, whiff and hit, every frame of Hanzou (animation, step,
   def, x, y) as WHP played it in our emulator (/data/neogeo_dict/whp/hanzo_dm_capture.json, WHP's freezes left out).
2. WHP's render (whp.render_def, the export's reference) vs WHP's VRAM on every frame of the DM captures: Hanzou's body
   (check_vram's rule) and the DM's effects (kanji $5A, smoke $5D, clone $7A: their objects rendered from the ROM vs
   the VRAM in their palettes).
3. The brawler (harness, Chain Lab training: P1 Hanzou against a standing dummy), D (the fury) and down+D (its MAX
   version), each with the dummy in reach (the dive connects: the ninja sequence) and off the depth line (the whiff),
   facing right and left: the rows played (the parts: the dive, then the landing or the sequence), each row's frame and
   place (x from the part's start, height), every frame's pixels (P1's sprite block in VRAM vs whp.render_def of the
   def the row came from, mirrored facing left) and every script object's (its entity's block vs its def), the hits
   on the dummy and their damage vs WHP's.
4. A contact sheet WHP vs the brawler (the hit, facing right): contact_fury.png / contact_max.png."""
import json, os, re, sys, subprocess, glob, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler', 'chainlab'))
import whp, neo_whp as neo, handlers_whp as H, check_vram as CV, cap_whp as cap
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/hanzofury/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
os.makedirs(OUT, exist_ok=True)
res = {}

# ---- 1. WHP vs the model --------------------------------------------------------------------------------------------
refs = json.load(open(H.REF))
res['model'] = {}
QUICK = os.environ.get('QUICK')                          # (iterating on the brawler side: parts 1 and 2 skipped)
for rec, ref in ({} if QUICK else refs).items():
    n, bad = H.check(ref, rec)
    res['model'][rec] = {'frames': n, 'identical': n - len(bad), 'hits': len(ref['hits'])}
    print(f'1. {rec}: model vs WHP {n - len(bad)} / {n} frames identical, WHP hits {len(ref["hits"])}')

# ---- 2. WHP's render vs WHP's VRAM ------------------------------------------------------------------------------------
def fx_render(o):
    a = np.zeros((224, 320), np.uint16)
    whp.render_def(a, o['defw'], o['x'], o['y'], hflip=o['flip'], pal_add=o['add'] >> 8, offs=None if o['flags'] & 1 else o['offs'])
    return a

res['vram'] = {}
def frame_fx(r, tasks):
    return [o for o in r['fx'] if o['task'] in tasks and o['defw'] != whp.BLANK]
for rec in () if QUICK else ('dm_hit', 'dmh_hit'):
    d = f'/data/tmp/hanzofury/vram_{rec}'
    rows = H.capture(rec, keep=d, vram=True)
    s0 = next(i for i, r in enumerate(rows) if r['p1']['anim'] in (0x128, 0x12A))
    body = [0, 0]; objs = [0, 0]; worst = []; owst = []; pr = None
    for r in rows[s0:]:
        if r['p1']['anim'] not in (0x128, 0x129, 0x12A, 0x12B, 0x1B): break
        v = neo.vram_words(r['vram']); full = None
        # the body (+ the clone $7A: Hanzou's own def in his palette), this frame's objects or the previous frame's
        # (check_vram's rule: a def / place can show a frame late)
        o = r['p1']; po = pr['p1'] if pr else None
        cands = [(o, frame_fx(r, (0x7A, 0x71)))] + ([(po, frame_fx(pr, (0x7A, 0x71))), (dict(po, defw=o['defw']), frame_fx(r, (0x7A, 0x71))),
                                                (dict(o, defw=po['defw']), frame_fx(pr, (0x7A, 0x71)))] if pr else [])
        best = None
        for c, cl in cands:
            a = CV.render(c)
            for ob in cl:
                fa = fx_render(ob); a = np.where(fa > 0, fa, a)
            ps = {int(q) for q in np.unique(a[a > 0] >> 4)} or {0x10}
            df = min(int((a != CV.vram_img(v, ps, bank)).sum()) for bank in (0, 1))
            best = df if best is None else min(best, df)
        body[0] += best == 0; body[1] += 1
        if best: worst.append((r['f'], f"{o['defw']:04X}", best))
        # the effects with palettes of their own (kanji $5A, smoke $5D)
        cur = frame_fx(r, (0x5A, 0x5D))
        if cur:
            bo = None
            for cl in [cur] + ([frame_fx(pr, (0x5A, 0x5D))] if pr else []):
                a = np.zeros((224, 320), np.uint16)
                for ob in cl:
                    fa = fx_render(ob); a = np.where(fa > 0, fa, a)
                ps = {int(q) for q in np.unique(a[a > 0] >> 4)}
                if not ps: continue
                if full is None: full = neo.vram_index(v)[0]
                df = int((a != np.where(np.isin(full >> 4, list(ps)), full, 0)).sum())
                bo = df if bo is None else min(bo, df)
            if bo is not None:
                objs[0] += bo == 0; objs[1] += 1
                if bo: owst.append((r['f'], [f"{q['task']:X}:{q['defw']:04X}" for q in cur], bo))
        pr = r
    res['vram'][rec] = {'body_identical': body[0], 'body_frames': body[1], 'differ': worst[:6], 'fx_identical': objs[0],
                        'fx_frames': objs[1], 'fx_differ': owst[:6]}
    print(f'2. {rec}: render_def vs WHP VRAM: Hanzou (+ clone) {body[0]} / {body[1]} frames identical {worst[:4]}; '
          f'kanji / smoke {objs[0]} / {objs[1]} {owst[:4]}')

# ---- 3. the brawler ----------------------------------------------------------------------------------------------------
from labdrive import Lab
import ctypes as C
ex = json.load(open(os.path.join(GAME, 'build', 'tmp_whp_hanzo', 'kof95_export.json')))['characters']['hanzo']
pals = [int(p, 16) for p in ex['modes']['palettes']]
used = sorted({p.get('pal', 0) for fr in ex['frames'] for p in fr['parts']})
G = json.load(open(os.path.join(GAME, 'game.json')))
ci = [r['name'] for r in G['roster']].index('hanzo')
L = Lab(); b = L.b; ST = b.states

def tiles_of(rom):
    import struct
    dd = open(rom, 'rb').read(); sizes = struct.unpack('<6I', dd[4:0x1C]); off = 0x1000 + sum(sizes[:5])
    return dd[off:off + sizes[5]]
def pens(crom, code):
    bb = np.frombuffer(crom, np.uint8, 128, code * 128).reshape(2, 16, 4)
    bits = np.unpackbits(bb[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    return np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint16)
crom = tiles_of(b.rom)
b.core.retro_get_memory_data.restype = C.c_void_p
vram = (C.c_uint16 * 65536).from_address(b.core.retro_get_memory_data(101))
def block_image(spr, n, pb):
    """an entity's sprite block from VRAM -> pen indices in the export's palette numbering ((0x80 + pal) * 16 + pen)"""
    img = np.zeros((544, 544), np.uint16); sx = sy = sh = 0
    for s in range(spr, spr + n):
        scb3 = vram[0x8200 + s]
        if scb3 & 0x40: sx += 16
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, vram[0x8400 + s] >> 7
        top = (496 - sy) & 0x1FF
        for r in range(min(sh, 32)):
            code = vram[s * 64 + 2 * r]; at = vram[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if not code: continue
            t = pens(crom, code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            p = (at >> 8) - pb
            if not 0 <= p < len(used): continue
            y, x = (top + r * 16 + 160) & 0x1FF, (sx + 96) & 0x1FF   # (shifted: a block across the 512 px wrap stays whole; tall jumps)
            img[y:y + 16, x:x + 16] = np.where(t > 0, (0x80 + used[p]) * 16 + t, img[y:y + 16, x:x + 16])
    return img
def ref_image(w):
    ref = np.zeros((640, 640), np.uint16)
    whp.render_def(ref, w, (320 + 128) * 128, (352 - 560) * 128)
    idx = np.vectorize(lambda p: pals.index(p) if p in pals else 0x70)(ref >> 4) if ref.any() else ref
    return np.where(ref & 15, (0x80 + idx) * 16 + (ref & 15), 0).astype(np.uint16)
def crop(img):
    ys, xs = np.nonzero(img)
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else img[:0, :0]
_refc = {}
def same_as_whp(got, frame_index, facing):
    """the block vs WHP's drawing of the def the export frame came from (mirrored facing left)"""
    w = int(ex['frames'][frame_index]['record'], 16)
    if (w, facing) not in _refc:
        r = ref_image(w); _refc[(w, facing)] = crop(r if facing > 0 else r[:, ::-1])
    ref = _refc[(w, facing)]; g = crop(got)
    return g.shape == ref.shape and bool((g == ref).all()), w

def st(i=0): return ST[b.fget(i, 'state')]
def settle():
    for _ in range(600):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'shot') and not b.fget(0, 'flash'): return
        b.run(1)
    raise RuntimeError('not idle: ' + b.brief((0, 2)))
P1 = b.base
def objects():
    out = []
    for i in range(8):
        if ST[b.pget(i, 'state')] == 'OFF' or b.pget(i, 'owner') != P1: continue
        fo = b.pget(i, 'frame_ovr')
        if fo == 0xFFFF: continue
        out.append((i, fo))
    return out
def blk(i):
    """(spr, ncols, palbase) of P1 (i None) or projectile entity i"""
    if i is None: return b.fget(0, 'spr'), b.fget(0, 'ncols'), b.fget(0, 'palbase')
    a = b.syms['projectiles'] + i * b.fsize
    rd = lambda f: b.r(a + b.layout[f][0], b.layout[f][1])
    return rd('spr'), rd('ncols'), rd('palbase')
def all_blocks(): return {None: blk(None), **{i: blk(i) for i in range(8)}}
def identical(i, fo, fc, prev):
    """an entity's drawing vs WHP's: its sprite block now, or the one it had the frame before (the depth sort hands the
    blocks out again when an entity comes or goes; VRAM shows the frame the game wrote last)"""
    ok, w = same_as_whp(block_image(*blk(i)), fo, fc)
    if not ok and prev and i in prev: ok = same_as_whp(block_image(*prev[i]), fo, fc)[0]
    return ok, w

sps = {sp['input']: sp for sp in ex['specials']}
res['brawler'] = {}
sheet_rows = {}
for key, inp, keys in (('fury', H_INP := '65426AC', 'd'), ('max', 'MAX 65426AC', 'Dd')):
    sp = sps[inp]; parts = sp['parts']; land = parts[0]['end'] - 1
    for case in ('hit', 'whiff'):
        for facing in (1, -1):
            L.start(ci, 0); b.run(30); settle()
            cam = b.r(b.syms['cam_x'], 2)
            x0 = cam + (64 if facing > 0 else 240)               # the hang (48 px back) inside the lab's bounds
            b.place(0, x=x0, z=30); b.fset(0, 'facing', facing & 0xFF)
            b.place(2, x=x0 + facing * 150, z=30 + (70 if case == 'whiff' else 0)); b.fset(2, 'facing', (-facing) & 0xFF)
            b.fset(0, 'meter', 120); b.run(2)
            h0 = len(b.hits); hp0 = b.fget(2, 'hp')
            trace = []; shots = {}; prevb = None; pending = []
            shoot = case == 'hit' and facing > 0
            if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
            for f in range(900):
                if shoot and f >= 3: b.screenshot(os.path.join(OUT, '_shot.png'))   # (a frame like b.run's: its picture)
                else: b.run(1, p1=keys if f < 3 else '')
                s = st(0)
                if s != 'SPECIAL':
                    if trace: break
                    continue
                row = b.fget(0, 'srow') - 1; tx = b.fget(0, 'throw_x0'); tx = (tx - (1 << 32) if tx & 0x80000000 else tx) / 65536
                px_ = b.fget(0, 'x') - cam
                rec_ = dict(row=row, part=b.fget(0, 'spart'), fo=b.fget(0, 'frame_ovr'), dx=round((b.fget(0, 'x') - tx) * facing, 2),
                            wall=px_ <= 40.01 or px_ >= 279.99 or b.fget(0, 'x') <= 16.01,
                            y=round(b.fget(0, 'y'), 2), freeze=b.fget(0, 'freeze'), objs=objects(), hp=b.fget(2, 'hp'))
                if rec_['fo'] >= len(ex['frames']): continue          # (no row yet)
                for t_, k_, i, fo, fc in pending:                     # an entity born / resized last frame: drawn now
                    if (i, fo) in rec_['objs']:
                        t_['opx'][k_] = identical(i, fo, fc, None)[0]
                        if t_['opx'][k_]: t_['obad'] = [q for q in t_.get('obad', []) if q[0] != ex['frames'][fo]['record']]
                pending = []
                if not trace or trace[-1]['row'] != row:
                    ok, w = identical(None, rec_['fo'], facing, prevb)
                    rec_['px'] = ok; rec_['def'] = f'{w:04X}'
                    rec_['opx'] = []
                    for i, fo in rec_['objs']:
                        ox = b.pget(i, 'x') - cam
                        if not -32 <= ox <= 352: rec_['opx'].append(None); continue   # off screen: not drawn
                        fc = facing * (1 if b.pget(i, 'facing') == facing else -1)
                        rec_['opx'].append(identical(i, fo, fc, prevb)[0])
                        if not rec_['opx'][-1]:
                            rec_.setdefault('obad', []).append((ex['frames'][fo]['record'], round(ox), round(b.pget(i, 'y'))))
                            pending.append((rec_, len(rec_['opx']) - 1, i, fo, fc))   # an entity born or grown this
                                                                  # frame: its sprite block comes with the next (depth sort)
                    if shoot and os.path.exists(os.path.join(OUT, '_shot.png')):
                        pth = os.path.join(OUT, f'_b_{key}_{row}.png'); os.replace(os.path.join(OUT, '_shot.png'), pth); shots[row] = pth
                trace.append(rec_)
                prevb = all_blocks()
            played = []
            for t in trace:
                if not played or played[-1] != t['row']: played.append(t['row'])
            first = [t for k, t in enumerate(trace) if k == 0 or trace[k - 1]['row'] != t['row']]
            want = list(range(0, land + 1)) + (list(range(parts[2]['first'], parts[2]['end'])) if case == 'hit' else list(range(parts[1]['first'], parts[1]['end'])))
            mism = []; wall = 0; objbad = []
            for t in first:
                r = sp['script'][t['row']]
                exp_dx, exp_y = r[1], max(0, r[2])
                if t['fo'] != r[0] or abs(t['y'] - exp_y) > 1: mism.append((t['row'], t['fo'], r[0], t['dx'], exp_dx, t['y'], exp_y))
                elif abs(t['dx'] - exp_dx) > 1:
                    if t['wall']: wall += 1                   # the dance's screen wall held him (fighter.c dance_update)
                    else: mism.append((t['row'], t['fo'], r[0], t['dx'], exp_dx, t['y'], exp_y))
                exp_o = [o[0] for o in r[3]]
                if sorted(fo for _, fo in t['objs']) != sorted(exp_o): objbad.append((t['row'], [fo for _, fo in t['objs']], exp_o))
            hits = [(h[2], h[3]) for h in b.hits[h0:] if h[1] == 2]
            out = {'rows_played': len(played), 'rows_expected': len(want), 'order_ok': played == want,
                   'row_mismatch': mism[:5], 'n_row_mismatch': len(mism), 'rows_at_wall': wall, 'object_rows_differ': objbad[:5],
                   'body_px_identical': sum(t['px'] for t in first), 'body_rows': len(first),
                   'body_px_differ': sorted({t['def'] for t in first if not t['px']}),
                   'obj_px_identical': sum(sum(1 for q in t['opx'] if q) for t in first), 'obj_shown': sum(sum(1 for q in t['opx'] if q is not None) for t in first),
                   'obj_offscreen': sum(sum(1 for q in t['opx'] if q is None) for t in first),
                   'obj_px_differ': sorted({ex['frames'][fo]['record'] for t in first for (i, fo), q in zip(t['objs'], t['opx']) if q is False}),
                   'body_px_differ_rows': [(t['row'], t['def']) for t in first if not t['px']][:8],
                   'obj_px_differ_rows': [(t['row'], t['obad']) for t in first if t.get('obad')][:8],
                   'hits': len(hits), 'damage': [h[0] for h in hits], 'life_lost': hp0 - b.fget(2, 'hp'),
                   'whp_hits': len(refs[('dmh' if key == 'max' else 'dm') + '_hit']['hits']) if case == 'hit' else 0}
            res['brawler'][f'{key}_{case}_{"right" if facing > 0 else "left"}'] = out
            print(f'3. {key} {case} facing {facing}: rows {out["rows_played"]} / {out["rows_expected"]} in order {out["order_ok"]}, '
                  f'row data mismatches {out["n_row_mismatch"]} (+{wall} held by the screen wall), object rows differ {len(objbad)}, body pixels {out["body_px_identical"]} / {out["body_rows"]} {out["body_px_differ"]}, '
                  f'objects {out["obj_px_identical"]} / {out["obj_shown"]}, hits {out["hits"]} (WHP {out["whp_hits"]}) damage {out["damage"]}')
            if case == 'hit' and facing > 0: sheet_rows[key] = (sp, shots, land)

# ---- 4. the contact sheet ---------------------------------------------------------------------------------------------
def whp_snaps(rec, frames):
    d = f'/data/tmp/hanzofury/snaps_{rec}'; os.makedirs(d, exist_ok=True)
    for f_ in glob.glob(d + '/*'): os.remove(f_)
    seq, seq2, hero = H.RECIPES[rec]
    pk = ';'.join(f'{f}:10600C=50,10607D=FF' + (',106A13=FF,106A16=00,106A17=DF,106A18=00,106A19=DF' if hero else '') for f in range(4))
    env = dict(os.environ, SEQ=seq, SEQ2=seq2, OUT=d + '/cap.txt', LOAD=cap.VS, POKE=pk, SNAPS=','.join(map(str, frames)), SNAPDIR=d)
    subprocess.run([cap.NGSDL, cap.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {f: f'{d}/snap_{f}.ppm' for f in frames}
SNAP_LAG = 2                                              # a screenshot shows the RAM of 2 frames before [meas: the white flash]
for key, (sp, shots, land) in sheet_rows.items():
    rec = ('dmh' if key == 'max' else 'dm') + '_hit'; fr = refs[rec]['frames']
    p = sp['parts']
    model_k = lambda row: row if row <= land else row - p[2]['first'] + land + 1
    picks = [0, 8, 14, 20, 26, land - 3, land] + [p[2]['first'] + k for k in (2, 10, 22, 40, 50, 62, 75, 90, 110, 130, 150, 170, 185, 200)]
    picks = [r for r in picks if r in shots and model_k(r) < len(fr)]
    snaps = whp_snaps(rec, [fr[model_k(r)]['f'] + SNAP_LAG for r in picks])
    W, Hh = 240, 168
    sheet = Image.new('RGB', (W * 2 + 90, (Hh + 4) * len(picks) + 20), 'white'); dr = ImageDraw.Draw(sheet)
    dr.text((90, 4), 'World Heroes Perfect (our emulator)', fill='black'); dr.text((90 + W, 4), 'brawler', fill='black')
    for i, r in enumerate(picks):
        y = 20 + i * (Hh + 4); k = model_k(r)
        dr.text((2, y + 4), f'row {r}\n{fr[k]["p1"][0]:X}/{fr[k]["p1"][1]}\ndef {fr[k]["p1"][2]:04X}', fill='black')
        if os.path.exists(snaps[fr[k]['f'] + SNAP_LAG]): sheet.paste(Image.open(snaps[fr[k]['f'] + SNAP_LAG]).resize((W, Hh)), (90, y))
        sheet.paste(Image.open(shots[r]).resize((W, Hh)), (90 + W, y))
    sheet.save(os.path.join(OUT, f'contact_{key}.png')); print('4. sheet', os.path.join(OUT, f'contact_{key}.png'), len(picks), 'rows')
for f_ in glob.glob(os.path.join(OUT, '_b_*.png')): os.remove(f_)
json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1, default=str)
