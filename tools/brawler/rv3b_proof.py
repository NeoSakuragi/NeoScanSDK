#!/usr/bin/env python3
"""Revamp 3b proof (Bruno's answers 2026-10-08: throws1 + krauser2), in the Chain Lab's training mode (labdrive: P1 = the
fighter, a dummy that never attacks) in our emulator's core (harness).

    python3 rv3b_proof.py OUT_DIR [chain FIGHTER] [furies]   -> OUT_DIR/rv3b.json, chain_<fighter>.png, furies_grab.png

chain:   the fighter's chain (game.json roster[].chain.links + finishers; Krauser's krauser2 answers) played with every
         finisher (neutral / forward / up / down / back) in both facings: the links played = the tree's, each link hits,
         the finisher = the tree's move with its reaction (launch: the victim up > 40 px; knockdown / blowback / trip:
         a knockdown; back: the throw, P1 untouchable through it, the victim behind), the chain's total damage = the
         archetype's (a throw's own damage on back). Sheet: one row per finisher and facing, a shot every SHOT_EVERY.
furies:  every roster fighter flagged `fury_grab` (Rugal, Yamazaki, Genjuro): D with a full meter at a dummy in reach,
         both facings: the fury plays (role BS_FURY, its input = roster[].fury), 300 meter spent, INV_FURY on every frame
         of it, the dummy hit (damage > 0). Sheet: one row per fighter and facing."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import export_bm
from labdrive import Lab
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[2:] or ['chain', 'krauser', 'furies']
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json')))
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
POOL = {f['name']: [p['input'] for p in f['pool']] for f in CL['fighters']}
MOVES = export_bm.MOVES
names = [r['name'] for r in G['roster']]
RO = {r['name']: r for r in G['roster']}
L = Lab(); b = L.b; ST = b.states
INV_FURY, BS_FURY = 0xFF, 6
SHOT_EVERY, SHOTS = 6, 16

def st(i=0): return ST[b.fget(i, 'state')]
def mv(i=0): return MOVES[b.fget(i, 'anim')]
def run(n=1, k=''): b.run(n, p1=k)
def settle():
    for _ in range(900):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'chain_t') and not b.fget(0, 'freeze'): break
        run(1)
    else: raise RuntimeError('never idle: ' + b.brief((0, 2)))
def setpos(dist, face):
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 150
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist * face, z=30); b.fset(0, 'facing', face & 0xFF); b.fset(2, 'facing', -face & 0xFF)
    b.fset(2, 'hp', 60); run(2)
def grab(pics):
    p = os.path.join(OUT, '_s.png'); b.screenshot(p); pics.append(Image.open(p).copy()); os.unlink(p)
def sheet(path, rows):
    w, h = 160, 112
    W = Image.new('RGB', (SHOTS * (w + 4) + 4, len(rows) * (h + 22) + 4), 'white'); d = ImageDraw.Draw(W)
    for i, (title, pics) in enumerate(rows):
        y = 4 + i * (h + 22); d.text((4, y), title, fill='black')
        for k, im in enumerate(pics):
            W.paste(im.resize((w, h)), (4 + k * (w + 4), y + 14))
            d.rectangle((4 + k * (w + 4) - 1, y + 13, 4 + k * (w + 4) + w, y + 14 + h), outline='black')
    W.save(path)

res = json.load(open(os.path.join(OUT, 'rv3b.json'))) if os.path.exists(os.path.join(OUT, 'rv3b.json')) else {}
def save(): json.dump(res, open(os.path.join(OUT, 'rv3b.json'), 'w'), indent=1)

# ---- a fighter's chain with every finisher, both facings ---------------------------------------------------------------
KEY = {'neutral': 'A', 'forward': 'fA', 'up': 'uA', 'down': 'dA', 'back': 'bA'}
def chain_case(fi, d, face, rows):
    tree = CL['fighters'][fi]['tree']; c = tree['chain']; N = c['length']
    want = tree['links']['A']; line = [want['move']]
    for _ in range(N - 2): want = want['links']['A']; line.append(want['move'])
    fin = want['links'].get(KEY[d]) or want['links']['A']
    stick = {'neutral': '', 'up': 'U', 'down': 'D', 'forward': 'R' if face > 0 else 'L', 'back': 'L' if face > 0 else 'R'}[d]
    settle(); setpos(30, face)
    h0 = len(b.hits); links = []; prev = (None, None); t = 0; done = None; pics = []; ymax = 0; vst = set(); inv = []
    x_at = None
    while t < 400:
        k = (stick if len(links) == N - 1 else '') + ('a' if len(links) < N and t % 6 < 2 else '')
        run(1, k); t += 1
        s_, nd = st(0), b.fget(0, 'node')
        if (s_ == 'ATTACK' and (prev[0] != 'ATTACK' or nd != prev[1])) or (s_ == 'THROW' and prev[0] != 'THROW'):
            links.append({'move': mv(0) if s_ == 'ATTACK' else 'throw', 'state': s_, 't': t, 'h': len(b.hits)})
            if len(links) == N: x_at = b.fget(0, 'x')
        if len(links) >= N:
            ymax = max(ymax, b.fget(2, 'y')); vst.add(st(2))
            if s_ == 'THROW': inv.append(b.fget(0, 'inv'))
        if len(links) >= N - 1 and t % SHOT_EVERY == 0 and len(pics) < SHOTS: grab(pics)
        prev = (s_, nd)
        if len(links) >= N and s_ in ('IDLE', 'WALK') and not b.fget(0, 'freeze') and st(2) in ('IDLE', 'WALK', 'DOWN', 'GETUP'):
            if done is None: done = t
            if t - done > 2 and len(pics) >= SHOTS: break
        if len(links) < N and t > 60 and s_ in ('IDLE', 'WALK') and not b.fget(0, 'chain_t') and not b.fget(0, 'freeze'): break
    hits = [x for x in b.hits[h0:] if x[1] == 2]
    per = []
    for i, l in enumerate(links):
        end = links[i + 1]['h'] if i + 1 < len(links) else len(b.hits)
        per.append(sum(x[2] for x in b.hits[l['h']:end] if x[1] == 2))
    vside = (b.fget(2, 'x') - (x_at if x_at is not None else b.fget(0, 'x'))) * face
    r = {'finisher': d, 'facing': 'right' if face > 0 else 'left', 'links_want': line + [fin['move'] + (' (throw)' if fin.get('throw') else '')],
         'links_played': [l['move'] for l in links], 'damage_per_link': per, 'damage': sum(x[2] for x in hits),
         'effect': fin.get('effect'), 'victim_states': sorted(vst), 'victim_max_y': round(ymax)}
    ok_links = len(links) == N and [l['move'] for l in links[:N - 1]] == line and all(p > 0 for p in per[:N - 1])
    if fin.get('throw'):
        r['inv_through_throw'] = bool(inv) and all(v == INV_FURY for v in inv); r['victim_behind'] = vside < 0
        ok_fin = links[-1]['state'] == 'THROW' and r['inv_through_throw'] and r['victim_behind'] if len(links) == N else False
    else:
        okv = {'launch': ymax > 40}.get(fin.get('effect'), 'KNOCKDOWN' in vst)
        ok_fin = len(links) == N and links[-1]['move'] == fin['move'] and per[-1] > 0 and okv
        r['ok_total'] = r['damage'] == c['total']
    r['ok'] = ok_links and ok_fin and r.get('ok_total', True)
    rows.append((f"{names[fi]} {' > '.join(r['links_played'])} [{d}, facing {r['facing']}] damage {r['damage']} {'ok' if r['ok'] else 'FAIL'}", pics))
    return r

if 'chain' in ARGS:
    n = ARGS[ARGS.index('chain') + 1]; fi = names.index(n)
    L.start(fi, 1 if fi == 0 else 0); run(30); blob = b.save()
    out = res['chain_' + n] = {'chain': CL['fighters'][fi]['tree']['chain'], 'game_json': {k: RO[n].get(k) for k in ('archetype', 'finishers', 'chain')}, 'cases': []}
    rows = []
    for d in KEY:
        for face in (1, -1):
            b.load(blob)
            r = chain_case(fi, d, face, rows); out['cases'].append(r)
            print(f"{n} {d:8s} {r['facing']:5s} played {r['links_played']} want {r['links_want']} dmg {r['damage_per_link']} = {r['damage']} "
                  f"victim {r['victim_states']} y {r['victim_max_y']}" + (f" inv {r['inv_through_throw']} behind {r['victim_behind']}" if 'inv_through_throw' in r else '')
                  + ('  ok' if r['ok'] else '  <-- FAIL'), flush=True)
    out['ok'] = all(c['ok'] for c in out['cases'])
    sheet(os.path.join(OUT, f'chain_{n}.png'), rows); save()

# ---- the grab furies on D ------------------------------------------------------------------------------------------------
if 'furies' in ARGS:
    out = res['grab_furies'] = {}; rows = []
    for n in [r['name'] for r in G['roster'] if r.get('fury_grab')]:
        fi = names.index(n); L.start(fi, 1 if fi == 0 else 0); run(30); blob = b.save(); out[n] = []
        for face in (1, -1):
            best = None; bd = {}; allok = True
            for dist in (24, 40, 70, 110, 160):                 # damage_tiers.py's distances: the best = its full connect
                b.load(blob); settle(); setpos(dist, face)
                b.fset(0, 'meter', 300); b.fset(0, 'meter_t', 0); h0 = len(b.hits)
                run(2, 'd')
                r = {'facing': 'right' if face > 0 else 'left', 'distance': dist, 'state': st(0), 'role': b.fget(0, 'spec_id'),
                     'input': POOL[n][b.fget(0, 'spec_ix')] if st(0) == 'SPECIAL' else None, 'meter_spent': 300 - b.fget(0, 'meter')}
                pics = []; fr = invf = 0
                for t in range(600):
                    if st(0) == 'SPECIAL': fr += 1; invf += b.fget(0, 'inv') == INV_FURY
                    if t % 8 == 0 and len(pics) < SHOTS: grab(pics)
                    run(1)
                    if t > 20 and st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK', 'DOWN') and len(pics) >= SHOTS: break
                r['frames'] = fr; r['inv_frames'] = invf
                r['damage'] = sum(x[2] for x in b.hits[h0:] if x[1] == 2)
                r['ok_fury'] = r['state'] == 'SPECIAL' and r['role'] == BS_FURY and r['input'] == RO[n]['fury'] and r['meter_spent'] == 300 \
                    and fr > 0 and invf == fr                       # (every distance, a whiff too)
                r['pics'] = pics; bd[dist] = r['damage']; allok = allok and r['ok_fury']
                if best is None or r['damage'] > best['damage']: best = r
            r = best; pics = r.pop('pics'); fr, invf = r['frames'], r['inv_frames']
            r['all_fury'] = allok; r['damage_by_distance'] = bd
            r['tier'] = G['tiers']['fury']; r['ok_tier'] = abs(r['damage'] - r['tier']) <= r['tier'] * G['tiers']['spread']['fury'] / 100
            r['ok'] = r['all_fury'] and r['ok_tier']
            out[n].append(r)
            rows.append((f"{n} D = fury {RO[n]['fury']} (a grab, provisional) facing {r['facing']} at {r['distance']} px: meter {r['meter_spent']}, "
                         f"inv {invf}/{fr}, damage {r['damage']} {'ok' if r['ok'] else 'FAIL'}", pics))
            print(n, r, flush=True)
    res['grab_furies_ok'] = all(r['ok'] for v in out.values() for r in v)
    sheet(os.path.join(OUT, 'furies_grab.png'), rows); save()

print('ALL OK' if all(v.get('ok', True) for k, v in res.items() if isinstance(v, dict) and 'ok' in v) and res.get('grab_furies_ok', True) else 'NOT OK')
