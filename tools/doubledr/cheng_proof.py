#!/usr/bin/env python3
"""TODO #212: Cheng-Fu (Double Dragon 1995, doubledr:cheng_fu) in the brawler, proved in the harness (the game's ROM on
the Geolith core) against Double Dragon itself (our emulator, emu/neogeo_sdl --capture). Billy Lee's proof
(billy_proof.py) with his roster entry, plus the real fight per move.

    python3 cheng_proof.py [OUTDIR] [frames] [fight] [variants] [stun]      (default /data/tmp/cheng212/out, all)

frames    every exported frame through the game's renderer, both facings, vs DD's drawing of its definition(s)
          (billy_proof.frames_proof: pen + palette index identical) -> frames_cheng_fu_*.png, dd_vs_brawler_cheng_fu.png
fight     each move in a real fight (the campaign's first wave, AI on: an enemy kept 300 px away = the whiff, one 58 px
          in front = the hit; the throw: walked into, forward + A) next to DD playing it (p1_10.state: P2 Jimmy poked to
          x 768 = the whiff, P1 walked in to 58 px = the hit; the supers with the powered flag poked; the throw: P1 walks
          into P2 and presses forward + C) -> fight_<move>_<whiff|hit>.png (DD above, the brawler below, every 4 frames
          from the press), hits / damage on both sides
variants  every row of the variant specials (var poked at the move's start, far: a whiff): travel / height vs the DD
          model of that button (model_dd = the game: compare_dd.py --far)
stun      the stun strike: the victim's script, then dizzy (fighter_t.dizzy) in its heavy reel for DD's 128 frames, open:
          an A during it lands
-> OUTDIR/proof.json"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'kizuna'))
import dd, model_dd as M, export_dd as E, cap_dd, commands_dd as CM, specials_dd as SD
import billy_proof as BP
from harness import Brawler
from kim_proof import lab_req
from PIL import Image, ImageDraw

args = [a for a in sys.argv[1:] if a not in ('frames', 'fight', 'variants', 'stun')]
OUT = args[0] if args else '/data/tmp/cheng212/out'
WHICH = [a for a in sys.argv[1:] if a in ('frames', 'fight', 'variants', 'stun')] or ['frames', 'fight', 'variants', 'stun']
GAME = BP.GAME
BP.FORMS = {'cheng_fu': 'cheng_fu'}; BP.OUT = OUT
STATE = '/data/neogeo_dict/doubledr/cap/p1_10.state'
FAR = ';'.join(f'{f}:100530=03,100531=00' for f in range(1, 400))         # DD's P2 kept at x 768 (+$06): no contact
POWER = ';'.join(f'{f}:10042A=81' for f in range(1, 80))                   # DD's powered flag (supers, specials_dd)
EVERY, GAP = 4, 58

def entry(note):
    return next(e for e in CM.entries(10) if CM.notation(e) == note and not e['flags'] & 4) if not note.startswith('S') else \
        next(e for e in CM.entries(10) if CM.notation(e) == note[2:] and e['flags'] & 4)

# move: (brawler keys, DD command entry, DD button: the row the brawler plays = bspec_t.vdef, the heaviest)
MOVES = {'214 (D)': ('c', '214+ABCD', 'd'), '236 (fwd+D)': ('Rc', '236+ABCD', 'd'), '623 (down+D)': ('Dc', '623+ABCD', 'd'),
         'SUPER 236 (fury D)': ('d', 'S 236+ABCD', 'a'), 'SUPER 623 (MAX down+D)': ('Dd', 'S 623+ABCD', 'a'),
         'throw (fwd+A)': ('Ra', None, 'c')}

def dd_play(move, label):
    """DD playing the move from p1_10.state: per frame from the press, P1's animation, P2's damage taken; snaps"""
    keys, note, btn = MOVES[move]
    if note is None:                                         # the throw: walk into P2, forward + C
        pre, seq, pokes = '', '70:R', None; seq += f',3:R{btn}'
    else:
        e = entry(note)
        seq = SD.inputs(e, btn)
        pre = '45:L,15:-,' if label == 'whiff' else '30:R,12:-,'
        pokes = ';'.join(x for x in ((FAR if label == 'whiff' else ''), (POWER if e['flags'] & 4 else '')) if x) or None
    full = pre + seq + ',170:-'
    t0 = cap_dd.nframes(pre + seq) - 3
    snaps = ','.join(str(f) for f in range(t0, t0 + 170, EVERY))
    rows = cap_dd.run(full, load=STATE, pokes=pokes, snaps=snaps)
    recs = [(dd.fighter_fields(r['ram'], 0x10042A)['anim'], cap_dd.u16(r['ram'], 0x100550), dd.fighter_fields(r['ram'], 0x10052A)['anim']) for r in rows]
    s = next((i for i in range(t0 - 2, len(recs)) if recs[i][0] not in (0, 1, 2, 3, 13, 14)), t0)
    end = next((i for i in range(s, len(recs)) if recs[i][0] in (0, 1, 2, 3)), len(recs))
    hits = sum(1 for i in range(s, min(end + 30, len(recs))) if recs[i][1] > recs[i - 1][1])
    cells = []
    for f in range(t0, t0 + 170, EVERY):
        p = f'/data/tmp/dd95/snap_{f}.ppm'
        if os.path.exists(p): cells.append(Image.open(p).convert('RGB')); os.remove(p)
    anims = []
    for a, _, _ in recs[s:end]:
        if not anims or anims[-1] != a: anims.append(a)
    p2 = []
    for _, _, a in recs[s:]:
        if not p2 or p2[-1] != a: p2.append(a)
    return {'frames': end - s, 'anims': anims, 'hits': hits, 'damage': recs[min(end + 29, len(recs) - 1)][1] - recs[s - 1][1],
            'victim_anims': p2[:10]}, cells

def br_play(b, start, move, label):
    """the brawler in the campaign's first wave (AI on): the move at an enemy GAP px in front (hit) or kept 300 px away"""
    keys = MOVES[move][0]
    b.load(start); b.run(30)
    en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
    if not en: return {'ok': False, 'why': 'no enemy'}, []
    e = en[0]; cam = b.r(b.syms['cam_x'], 2); gap = 300 if label == 'whiff' else GAP
    b.place(0, x=cam + 40, z=b.fget(e, 'z')); b.place(e, x=cam + 40 + (24 if keys == 'Ra' else gap)); b.fset(0, 'facing', 1); b.fset(e, 'hp', 90)
    b.fset(0, 'meter', 120)
    for i in en[1:]: b.place(i, x=cam + 600)
    if keys == 'Ra':                                          # the throw: walk into it (the grab), then forward + A
        for _ in range(30):
            b.run(1, p1='R')
            if b.states[b.fget(0, 'state')] == 'GRAB': break
    h0 = len(b.hits); cells = []; specs = []; states = []
    for f in range(170):
        kk = keys if f < 3 else ''
        if label == 'whiff':
            for i in en: b.place(i, x=b.fget(0, 'x') + 300)
        else:
            for i in en[1:]: b.place(i, x=b.fget(0, 'x') + 400)
        if f % EVERY == 0: p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).convert('RGB'))
        else: b.run(1, p1=kk)
        st = b.states[b.fget(0, 'state')]; states.append(st)
        if st == 'SPECIAL' and b.fget(0, 'spec_id') not in specs: specs.append(b.fget(0, 'spec_id'))
    hits = [h for h in b.hits[h0:] if h[1] == e]                # (on the target: the others are kept 300 px away, a
    other = [h for h in b.hits[h0:] if h[1] not in (0, e)]        # long move may still reach them)
    n = next((i for i, s in enumerate(states) if s in ('IDLE', 'WALK') and i > 3), len(states))
    return {'roles': specs, 'frames': n, 'hits': len(hits), 'damage': sum(h[2] for h in hits), 'hits_on_others': len(other),
            'victim_states': sorted({h[3] for h in hits}), 'p1_states': list(dict.fromkeys(states[:n + 1]))}, cells

def sheet(name, ddc, brc, info):
    C_, W_, H_ = 12, 200, 140
    n = max(len(ddc), len(brc)); nch = (n + C_ - 1) // C_
    sh = Image.new('RGB', (70 + W_ * C_, (2 * H_ + 22) * nch + 30), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), f'TODO #212 Cheng-Fu {name}: every {EVERY} frames from the press; top Double Dragon, bottom the brawler '
                   f'(real fight). {info}', fill='black')
    for i in range(n):
        y0 = 30 + (2 * H_ + 22) * (i // C_); xx = 70 + W_ * (i % C_)
        if i % C_ == 0: d.text((4, y0 + 60), 'DD', fill='black'); d.text((4, y0 + H_ + 70), 'brawler', fill='black')
        if i < len(ddc): sh.paste(ddc[i].resize((W_, H_)), (xx, y0))
        if i < len(brc): sh.paste(brc[i].resize((W_, H_)), (xx, y0 + H_ + 4))
        d.text((xx + 2, y0 + 2 * H_ + 6), f'+{i * EVERY}', fill='black')
    sh.save(os.path.join(OUT, 'fight_' + re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))

def fight_proof(b, k, res):
    b.pick(k); b.run(200); start = b.save()
    for move in MOVES:
        for label in ('whiff', 'hit'):
            if MOVES[move][1] is None and label == 'whiff': continue
            ddr, ddc = dd_play(move, label)
            br, brc = br_play(b, start, move, label)
            ok = bool(br.get('roles') or move.startswith('throw')) and ((br['hits'] > 0) == (ddr['hits'] > 0) if not move.startswith('throw') else True)
            res['fight'][f'{move} {label}'] = {'ok': ok, 'dd': ddr, 'brawler': br}
            sheet(f'{move} {label}', ddc, brc, f"DD {ddr['hits']} hits {ddr['frames']} f | brawler {br['hits']} hits {br['frames']} f")
            print(f'{move:26s} {label:5s} {"ok" if ok else "FAIL"} DD {ddr} | brawler {br}', flush=True)

def variants_proof(b, idx, res):
    ex = BP.bank('cheng_fu'); g = json.load(open(os.path.join(GAME, 'game.json')))
    slots = next(r for r in g['roster'] if r['name'] == 'cheng_fu')['specials']
    for slot, keys in BP.SLOTS.items():
        inp = slots.get(slot)
        if not inp: continue
        sp = next(s for s in ex['specials'] if s['input'] == inp); vt = sp['rom']['vtable']
        for v, a0 in enumerate(vt['anims']):
            got, _ = BP.play_special(b, idx, 'cheng_fu', keys, 300, var=v)
            ref = M.play(10, a0)
            want = {'travel': round(ref[-1]['x'], 1), 'height': round(max(q['y'] for q in ref), 1), 'frames': len(ref)}
            edge = want['travel'] > got['travel'] + 1.5 and got['travel'] >= 200   # (the 214's 208-361 px: the screen's edge
            ok = (abs(got['travel'] - want['travel']) <= 1.5 or edge) and abs(got['height'] - want['height']) <= 1.5   # stops it;
            got['stopped_by_screen_edge'] = edge                                     # progcheck_dd: its rows = the model)
            res['variants'][f'{inp} {"ABCD"[v]}'] = {'ok': ok, 'brawler': got, 'dd_model': want}
            print('row', inp, 'ABCD'[v], 'ok' if ok else 'FAIL', got, 'model', want, flush=True)

def stun_proof(b, k, res):
    """the stun strike in the campaign: grab, forward + A; the victim's states per frame; then A while it is dizzy"""
    b.pick(k); b.run(200)
    en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
    e = en[0]; cam = b.r(b.syms['cam_x'], 2)
    for i in en[1:]: b.place(i, x=cam + 300)
    b.place(0, x=cam + 60, z=b.fget(e, 'z')); b.place(e, x=cam + 84); b.fset(0, 'facing', 1); b.fset(e, 'hp', 90)
    for _ in range(30):
        b.run(1, p1='R')
        if b.states[b.fget(0, 'state')] == 'GRAB': break
    hp0 = b.fget(e, 'hp'); tl = []; cells = []
    for f in range(260):
        if f % 8 == 0: p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).convert('RGB'))
        else: b.run(1, p1='Ra' if f < 3 else '')
        for i in en[1:]: b.place(i, x=cam + 300)
        tl.append((b.states[b.fget(e, 'state')], b.fget(e, 'dizzy'), round(b.fget(e, 'x') - b.fget(0, 'x'))))
    thrown = sum(1 for s in tl if s[0] == 'THROWN'); dz = [i for i, s in enumerate(tl) if s[0] == 'HITSTUN']
    out = {'grabbed': True, 'thrown_frames': thrown, 'dizzy_frames': len(dz), 'dizzy_value': max((s[1] for s in tl), default=0),
           'hp_lost_by_the_throw': hp0 - b.fget(e, 'hp'), 'victim_x_from_p1': [tl[0][2], tl[thrown][2] if thrown < len(tl) else None],
           'states': list(dict.fromkeys(s[0] for s in tl))}
    # again, and an A into the dizzy victim
    b.pick(k); b.run(200)
    b.place(0, x=cam + 60, z=b.fget(e, 'z')); b.place(e, x=cam + 84); b.fset(0, 'facing', 1)
    for i in en[1:]: b.place(i, x=cam + 300)
    for _ in range(30):
        b.run(1, p1='R')
        if b.states[b.fget(0, 'state')] == 'GRAB': break
    b.run(3, p1='Ra')
    for _ in range(200):
        b.run(1)
        for i in en[1:]: b.place(i, x=cam + 300)
        if b.states[b.fget(e, 'state')] == 'HITSTUN' and b.fget(e, 'dizzy'): break
    b.run(20)
    h0 = len(b.hits)
    b.place(0, x=b.fget(e, 'x') - 40); b.fset(0, 'facing', 1)
    b.run(3, p1='a'); b.run(30)
    out['a_into_dizzy'] = [h for h in b.hits[h0:] if h[1] == e]
    out['ok'] = thrown > 60 and 120 <= len(dz) <= 140 and out['hp_lost_by_the_throw'] == 0 and bool(out['a_into_dizzy'])
    res['stun'] = out
    sh = Image.new('RGB', (160 * 11, 112 * ((len(cells) + 10) // 11)), 'white')
    for i, c in enumerate(cells): sh.paste(c.resize((160, 112)), (160 * (i % 11), 112 * (i // 11)))
    sh.save(os.path.join(OUT, 'stun.png'))
    print('stun', 'ok' if out['ok'] else 'FAIL', out, flush=True)

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler(game=GAME)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    k = bcs.index('BC_CHENG_FU'); idx = {'cheng_fu': k}
    pth = os.path.join(OUT, 'proof.json')
    res = json.load(open(pth)) if os.path.exists(pth) else {}
    for key in ('frames', 'fight', 'variants', 'stun'): res.setdefault(key, {})
    save = lambda: json.dump(res, open(pth, 'w'), indent=1, default=str)
    if 'stun' in WHICH: stun_proof(b, k, res); save()
    if 'fight' in WHICH: fight_proof(b, k, res); save()
    if 'variants' in WHICH:
        b.pick(k); variants_proof(b, idx, res); save()
    if 'frames' in WHICH:                                  # (VRAM: a core with retro_get_memory_data(101), the
        b.pick(k); BP.frames_proof(b, idx, res)            # retroarch build: BRAWLER_CORE)
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(pth, 'w'), indent=1, default=str)

if __name__ == '__main__':
    main()
