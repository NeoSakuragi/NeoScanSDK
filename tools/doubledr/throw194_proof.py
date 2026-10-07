#!/usr/bin/env python3
"""TODO #194 proof: Billy Lee's throws (Double Dragon's, decoded: throw_dd.py) and his down+C = DD's small 623 (A row).
Our emulator only: DD through `emu/neogeo_sdl --capture` (cap_dd), the brawler through the Geolith harness on a
`make AI_OFF=1` build (the test places the enemy; one core per process).

    python3 throw194_proof.py OUT_DIR [dd|brawler|rise|all]     (default /data/tmp/billy194/out, all)

  dd       throw_dd.check: every form x B / C / D x forward / back, the script vs DD frame by frame (-> throw194.json),
           and DD's pictures of the C throws (P1 Billy / transformed Billy walks into Jimmy, left / right + C)
  brawler  per form (billy_lee; billy_super: P1's bchar poked after the pick) x forward / back + A: the walk-in grab,
           then the throw; per frame P1's state / script row and the victim's place from the thrower (grab facing),
           height, state, life -> brawler_<form>_<throw>.json; compared with the exported script's rows (export =
           DD's decoded C throw); sheet_<form>_<throw>.png: DD (above, its dragon pause dropped) | brawler (below)
  rise     the 623 on down+C: the brawler's height per frame (Billy Lee, the variant row game.json picks) vs DD's 623 A /
           D (model_dd, = the game: compare_dd) -> rise.txt
OUT/summary194.json: every check."""
import json, os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
from PIL import Image, ImageDraw
import dd, model_dd as M, throw_dd as T

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/billy194/out'
WHAT = sys.argv[2] if len(sys.argv) > 2 else 'all'
os.makedirs(OUT, exist_ok=True)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
SUMMARY = os.path.join(OUT, 'summary194.json')
summary = json.load(open(SUMMARY)) if os.path.exists(SUMMARY) else {}
def save(): json.dump(summary, open(SUMMARY, 'w'), indent=1)
FORMS = {'billy_lee': 0, 'billy_super': 1}
KEYS = {'throw_c': ('Ra', False), 'throw_d': ('La', True)}
ENEMY = 2

# ---- DD -------------------------------------------------------------------------------------------------------------------
def dd_pictures(ch, back):
    """DD's screen per frame of the C throw (its pause frames dropped: the frames where nothing moves), cropped around P1"""
    import cap_dd as c
    seq = f'70:R,3:{"L" if back else "R"}c,140:-'
    cap = T.capture(ch, 'C', back)
    t0 = next(i for i, q in enumerate(cap) if q['a1'] == 111)
    keep, prev = [], None
    for q in cap[t0:]:
        k = (q['a1'], q['s1'], q['t1'], q['a2'], q['s2'], round(q['x2'], 3), round(q['y2'], 3))
        if k != prev: keep.append(q['f'])
        prev = k
    keep = keep[:90]
    c.run(seq, load=T.STATES[ch] or c.VS, ram=False, snaps=','.join(str(f + 1) for f in keep))   # (the vblank draws the
    ims = []                                                                                      # previous frame's state)
    for f in keep:
        p = f'/data/tmp/dd95/snap_{f + 1}.ppm'
        ims.append(Image.open(p).convert('RGB') if os.path.exists(p) else None)
        if os.path.exists(p): os.remove(p)
    return ims

def run_dd():
    res = {'tables': {ch: T.table(ch) for ch in (0, 1)}, 'checks': []}
    for ch in (0, 1):
        for b in 'BCD':
            for back in (False, True):
                r = T.compare(ch, b, back); res['checks'].append(r)
    json.dump(res, open(os.path.join(OUT, 'throw194.json'), 'w'), indent=1)
    summary['dd'] = {f"{r['ch']}{r['button']}{'back' if r['back'] else 'fwd'}": dict(mismatches=r['mismatches'], rows=r['rows'],
                     stage_edge=r['at_stage_edge'], release=[r['release'], r['damage_row']], land=[r['land'], r['land_dd']],
                     ret=[r['ret'], r['thrower_end_dd']]) for r in res['checks']}
    summary['dd_ok'] = all(r['mismatches'] == 0 and r['release'] == r['damage_row'] and r['land'] == r['land_dd'] and r['ret'] == r['thrower_end_dd']
                           for r in res['checks'])
    save(); print('dd ok', summary['dd_ok'])

# ---- brawler ------------------------------------------------------------------------------------------------------------
def brawler_case(form, key):
    from harness import Brawler
    b = Brawler(); st = b.states.index
    roster = json.load(open(os.path.join(GAME, 'game.json')))['roster']
    names = [r['name'] for r in roster]
    b.pick(names.index('billy_lee'), unlock=True)
    if form != 'billy_lee':                              # (not on the select screen: the transformed form)
        b.fset(0, 'ch', b.syms['bm_chars'] + names.index(form) * b.syms['sizeof_bchar'])
    for i in range(8):
        if b.fget(i, 'ch') == 0 or (i == 1 and b.fget(i, 'state') == st('OFF')): continue
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.fset(i, 'frame_ovr', 0xFFFF); b.fset(i, 'held', 0); b.intent(i)
    x1 = 160 if key == 'throw_c' else 250                # (the back throw lands ~170 px behind: off the stage's left edge)
    b.place(0, x=x1, z=30); b.fset(0, 'facing', 1)
    b.place(ENEMY, x=x1 + 30, z=30); b.fset(ENEMY, 'facing', 0xFF)
    for j, i in enumerate((3, 4, 5)):
        if b.fget(i, 'ch'): b.place(i, x=900 + 40 * j, z=30)
    b.run(1)
    S = lambda i: b.states[b.fget(i, 'state')]
    for f in range(60):
        b.run(1, p1='R')
        if S(0) == 'GRAB': break
    else: raise RuntimeError('no grab: ' + b.brief())
    rows, ims = [], []
    def cam(): c = b.r(b.syms['cam_x'], 2); return c - 65536 if c > 32767 else c
    grab = dict(p1x=b.fget(0, 'x'), vx=b.fget(ENEMY, 'x') - b.fget(0, 'x'), vy=b.fget(ENEMY, 'y'), p1=S(0), v=S(ENEMY))
    x0 = b.fget(0, 'x'); face = 1
    for f in range(120):
        b.pad = [set(KEYS[key][0] if f == 0 else ''), set()]
        p = os.path.join(OUT, '_tmp.png'); b.screenshot(p)
        im = Image.open(p).convert('RGB'); cx = x0 - cam()
        W_, H_ = im.size; xa = max(0, min(W_ - 240, int(cx - 120))); ims.append(im.crop((xa, H_ - 170, xa + 240, H_ - 10)))
        rows.append(dict(f=f, p1=S(0), srow=b.fget(0, 'srow'), p1x=b.fget(0, 'x') - x0, v=S(ENEMY), vx=(b.fget(ENEMY, 'x') - x0) * face,
                         vy=b.fget(ENEMY, 'y'), hp=b.fget(ENEMY, 'hp'), vface=b.fget(ENEMY, 'facing'), p1face=b.fget(0, 'facing')))
        if f > 40 and rows[-1]['v'] in ('DOWN', 'GETUP', 'IDLE'): break
    if os.path.exists(p): os.remove(p)
    return grab, rows, ims

def script_rows(form, key):
    """the exported throw's rows (build/bm_chars.c: {tframe, tx, ty, vpose, flags, vx, vy}) and its points"""
    import re
    c = open(os.path.join(GAME, 'build', 'bm_chars.c')).read()
    m = re.search(rf'static const bthrow_row_t {form}_{key}\[\] = \{{(.*?)\}};', c, re.S)
    rows = [tuple(int(x) for x in r.split(',')) for r in re.findall(r'\{([^{}]*)\}', m.group(1))]
    t = re.search(rf'static const bthrow_t {form}_throws\[BT_COUNT\] = \{{(.*?)\}};', c, re.S).group(1)
    ent = re.findall(r'\{([^{}]*)\}', t)[0 if key == 'throw_c' else 1].split(',')
    return rows, dict(nrows=int(ent[0]), speed=int(ent[1], 0), ret=int(ent[3], 0), rel=int(ent[4], 0), land=int(ent[5], 0))

def sheet(path, title, top, bottom, labels, step=2, n=72):
    sel = list(range(0, min(n, max(len(top), len(bottom))), step)); cols = 8
    w, h = 240, 160; R = (len(sel) + cols - 1) // cols
    Sh = Image.new('RGB', (cols * (w + 6) + 80, 24 + R * (2 * (h + 2) + 30)), 'white'); d = ImageDraw.Draw(Sh)
    d.text((4, 4), title, fill='black')
    for j, f in enumerate(sel):
        X = 80 + (j % cols) * (w + 6); Y = 24 + (j // cols) * (2 * (h + 2) + 30)
        d.text((X + 2, Y + 2), labels[f] if f < len(labels) else f'row {f}', fill='black')
        for k, seq in enumerate((top, bottom)):
            yy = Y + 16 + k * (h + 2)
            if j % cols == 0: d.text((4, yy + 70), ('DOUBLE DRAGON', 'BRAWLER')[k], fill='black')
            im = seq[f] if f < len(seq) else None
            if im is not None:
                if im.size != (w, h): im = im.resize((w, h))
                Sh.paste(im, (X, yy))
            d.rectangle([X - 1, yy - 1, X + w, yy + h], outline='black')
    Sh.save(path)

def run_brawler():
    for form in FORMS:
        for key in KEYS:
            subprocess.run([sys.executable, __file__, OUT, f'case:{form}:{key}'], check=True)
    summary.update(json.load(open(SUMMARY)))
    summary['brawler_ok'] = all(v['ok'] for k, v in summary.items() if k.startswith('brawler:'))
    save(); print('brawler ok', summary['brawler_ok'])

def run_case(form, key):
    grab, rows, ims = brawler_case(form, key)
    srows, pts = script_rows(form, key)
    t0 = next(i for i, r in enumerate(rows) if r['p1'] == 'THROW')
    th = [r for r in rows[t0:]]
    # the victim's place per row while the script places it (to the landing): brawler vs the exported rows (DD's decode)
    bad, first, lag = 0, None, []
    for i, r in enumerate(th[:pts['land'] + 1]):
        want = (srows[i][5], max(0, srows[i][6]))
        got = (round(r['vx']), round(r['vy']))
        if abs(want[0] - got[0]) > 1 or abs(want[1] - got[1]) > 1:
            prev = (srows[i - 1][5], max(0, srows[i - 1][6]))
            if i == pts['ret'] and abs(prev[0] - got[0]) <= 1 and abs(prev[1] - got[1]) <= 1:
                lag.append(i); continue           # the engine's hand-over before TODO #196 (paired_update returned at the control
            bad += 1; first = first or (i, want, got)   # return before placing the victim: its row ret shows a frame later)
    ret = next((i for i, r in enumerate(th) if r['p1'] != 'THROW'), None)
    dmg = [i for i in range(1, len(th)) if th[i]['hp'] < th[i - 1]['hp']]
    out = dict(grab=grab, throw_from=t0, rows_compared=min(len(th), pts['land'] + 1), place_mismatches=bad, first=first, handover_lag=lag,
               control_return=[ret, pts['ret']], release_row=pts['rel'], land_row=pts['land'], damage_rows=dmg,
               victim_end=th[-1]['v'], hp_lost=th[0]['hp'] - min(r['hp'] for r in th),
               victim_face_first=th[0]['vface'], thrower_face_first=th[0]['p1face'])
    out['ok'] = bad == 0 and ret == pts['ret'] and th[-1]['v'] in ('DOWN', 'GETUP', 'IDLE') and out['hp_lost'] > 0
    json.dump(dict(out, rows=rows), open(os.path.join(OUT, f'brawler_{form}_{key}.json'), 'w'), indent=1)
    dd_ims = dd_pictures(FORMS[form], KEYS[key][1])
    labels = [f"row {i}: {r['p1'][:6]} v{r['vx']:+.0f},{r['vy']:.0f} {r['v'][:7]}" for i, r in enumerate(th)]
    sheet(os.path.join(OUT, f'sheet_{form}_{key}.png'),
          f'TODO #194 {form} {key} ({"back" if KEYS[key][1] else "forward"} + A = DD left / right + C): DD (Billy{" transformed" if FORMS[form] else ""} '
          f'vs Jimmy, its 16-frame dragon pause dropped) | brawler (vs the campaign enemy), every 2nd frame from the throw\'s first',
          dd_ims, ims[t0:], labels)
    # the hold (the walk-in grab, before the press): the frame before the throw
    ims[max(0, t0 - 1)].save(os.path.join(OUT, f'hold_{form}_{key}.png'))
    summary[f'brawler:{form}:{key}'] = out; save(); print(form, key, json.dumps(out))

# ---- the 623 on down+C ----------------------------------------------------------------------------------------------------
def run_rise():
    subprocess.run([sys.executable, __file__, OUT, 'rise_case'], check=True)
    summary.update(json.load(open(SUMMARY)))

def rise_case():
    from harness import Brawler
    b = Brawler(); st = b.states.index
    names = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    b.pick(names.index('billy_lee'), unlock=True)
    b.fset(0, 'state', st('IDLE')); b.place(0, x=160, z=30); b.fset(0, 'facing', 1)
    for i in range(2, 8):
        if b.fget(i, 'ch'): b.place(i, x=900 + 40 * i, z=30)
    b.run(2)
    ys = []
    b.run(1, p1='D'); b.run(1, p1='Dc')
    for f in range(120):
        b.run(1); ys.append(b.fget(0, 'y'))
        if f > 10 and b.states[b.fget(0, 'state')] == 'IDLE': break
    dd_rows = {v: [r['y'] for r in M.play(0, a)] for v, a in zip('ABCD', (87, 88, 89, 90))}
    lines = [f'brawler Billy Lee down+C: peak {max(ys):.1f} px, {len(ys)} frames to idle']
    for v, y in dd_rows.items(): lines.append(f'DD 623 {v} (model_dd = the game): peak {max(y):.1f} px, {len(y)} frames')
    best = min(dd_rows, key=lambda v: abs(max(dd_rows[v]) - max(ys)))
    lines.append(f'closest DD row: {best}')
    open(os.path.join(OUT, 'rise.txt'), 'w').write('\n'.join(lines) + '\n'); print('\n'.join(lines))
    summary['rise'] = dict(brawler_peak=max(ys), dd_peaks={v: max(y) for v, y in dd_rows.items()}, row=best, ok=best == 'A' and abs(max(ys) - max(dd_rows['A'])) <= 2)
    save()

if __name__ == '__main__':
    if WHAT.startswith('case:'): _, f, k = WHAT.split(':'); run_case(f, k); sys.exit(0)
    if WHAT == 'rise_case': rise_case(); sys.exit(0)
    if WHAT in ('dd', 'all'): run_dd()
    if WHAT in ('brawler', 'all'): run_brawler()
    if WHAT in ('rise', 'all'): run_rise()
