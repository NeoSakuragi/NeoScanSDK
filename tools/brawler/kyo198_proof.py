#!/usr/bin/env python3
"""TODO #198 proofs (Kyo's Orochinagi from KOF98's handler $3D4EA: the held button, the MAX version's burning body;
Kyo's flame drawn in its own colours), harness.py on a `make AI_OFF=1` build (the test drives the enemy).

    python3 kyo198_proof.py walkin GAME_DIR [OUT]     the enemy walks into Kyo during the charge (D / down+D held 200
                                                      frames, the enemy 150 px ahead walking in from the fury's first
                                                      frame): the MAX burns it (KOF98 state 195's attack box, a knockdown,
                                                      Kyo still charging), the DM does not (187 has no attack box);
                                                      OUT/walkin_<DM|MAX>.png, OUT/walkin.json
    python3 kyo198_proof.py colours GAME_DIR [BASE_DIR] [OUT]   Kyo's flames against KOF98's: EX 236A's ground flame
                                                      (C, frames 800-804, KOF98 effect palette 37) and Orochinagi's
                                                      flame (D, frames 469-480, palette 33): KOF98 (our emulator) | the
                                                      build before (BASE_DIR) | this build, side by side, and the
                                                      palette the game loaded for those frames (palette RAM) against
                                                      KOF98's ROM palette; OUT/colours.png, OUT/colours.json

The tap / held / MAX-held sheets against KOF98 in a real fight: romspecials_check.py GAME_DIR OUT kyo:C kyo:C~60
kyo:C~200 kyo:M kyo:M~60 kyo:M~200 (its ~H: the button held H frames more). Default OUT /data/tmp/kyo198/out."""
import ctypes as C, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
from harness import Brawler
from PIL import Image, ImageDraw

OUT = '/data/tmp/kyo198/out'
ENEMY = 2

def setup(b, roster, gap, meter=120):
    b.pick(roster.index('kyo'), unlock=True); b.run(10)
    for i in range(1, 8): b.place(i, x=1000, z=0)
    b.place(0, x=80, z=30); b.fset(0, 'facing', 1)
    b.place(ENEMY, x=80 + gap, z=30); b.fset(ENEMY, 'facing', 0xFF)
    b.run(2)
    w = 0
    while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
    b.place(0, x=80, z=30); b.place(ENEMY, x=80 + gap, z=30); b.fset(ENEMY, 'hp', 60); b.fset(0, 'meter', meter)
    b.hits = []

def rec_of(frames, fr):
    return frames['kyo'][fr] if 0 <= fr < len(frames['kyo']) else None

def sheet(shots, path, title, cols=6):
    W, H = 152, 112
    im = Image.new('RGB', (cols * (W + 4) + 4, 20 + ((len(shots) + cols - 1) // cols) * (H + 14)), 'white')
    d = ImageDraw.Draw(im); d.text((4, 4), title, fill='black')
    for i, (lab, p) in enumerate(shots):
        x = 4 + (i % cols) * (W + 4); y = 20 + (i // cols) * (H + 14)
        im.paste(Image.open(p).convert('RGB').resize((W, H)), (x, y + 12)); d.text((x, y), lab, fill='black')
        d.rectangle([x, y + 12, x + W - 1, y + 12 + H - 1], outline='black')
    im.save(path)

# ---- the enemy walks into the charge ----------------------------------------------------------------------------------
def walkin(game, out):
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); res = []
    for label, keys in (('DM', 'd'), ('MAX', 'Dd')):
        setup(b, roster, 150)
        sd = os.path.join(out, 'shots', f'walkin_{label}'); os.makedirs(sd, exist_ok=True); shots = []
        rows, started, hit = [], None, None
        for f in range(320):
            pad = keys if f < 4 else ('d' if f < 200 else '')
            if started is not None and b.states[b.fget(ENEMY, 'state')] in ('IDLE', 'WALK'):
                b.intent(ENEMY, dx=0xFF)                      # the enemy walks in (toward Kyo, on his left)
            if started is not None and (f - started) % 6 == 0 and len(shots) < 36:
                b.pad = [set(pad), set()]; p = os.path.join(sd, f'f{f:03d}.png'); b.screenshot(p); shots.append((f'frame {f - started}', p))
            else: b.run(1, p1=pad)
            st = b.states[b.fget(0, 'state')]
            if started is None and st == 'SPECIAL': started = f
            if started is None: continue
            r = {'f': f - started, 'kyo': st, 'frame': rec_of(frames, b.fget(0, 'frame_ovr')), 'pcnt': b.fget(0, 'pcnt'),
                 'held': b.fget(0, 'pheld'), 'enemy_x': round(b.fget(ENEMY, 'x') - b.fget(0, 'x'), 1),
                 'enemy': b.states[b.fget(ENEMY, 'state')], 'enemy_hp': b.fget(ENEMY, 'hp')}
            rows.append(r)
            if hit is None and len(rows) > 1 and (r['enemy_hp'] < rows[-2]['enemy_hp'] or r['enemy'] in ('HITSTUN', 'KNOCKDOWN') and rows[-2]['enemy'] not in ('HITSTUN', 'KNOCKDOWN')):
                hit = r
            if st != 'SPECIAL' and f > started + 10: break
        charge = [r for r in rows if r['frame'] in ({'DM': '0:564', 'MAX': '0:481'}[label], {'DM': '0:565', 'MAX': '0:482'}[label]) or
                  (label == 'MAX' and r['frame'] and r['frame'].startswith('0:48'))]
        hit_in_charge = hit is not None and any(r['f'] == hit['f'] for r in charge) and hit['f'] >= 30
        s = {'version': label, 'keys': keys + ' then D held to frame 200', 'hit': hit,
             'charge_frames': [charge[0]['f'], charge[-1]['f']] if charge else None,
             'enemy_hits': [(f_ - b.frame, i, hp, st_) for f_, i, hp, st_ in b.hits if i == ENEMY][:6],
             'fury_frames': len(rows), 'ok': hit_in_charge if label == 'MAX' else (hit is None or hit['f'] >= (charge[-1]['f'] if charge else 0))}
        res.append(s); print(json.dumps(s), flush=True)
        json.dump(rows, open(os.path.join(out, 'shots', f'walkin_{label}.json'), 'w'), indent=0)
        sheet(shots, os.path.join(out, f'walkin_{label}.png'),
              f'Kyo {label} Orochinagi held, an enemy walking in from 150 px: ' +
              (f'hit at frame {hit["f"]} ({hit["frame"]}, {hit["enemy"]})' if hit else 'no hit'))
    json.dump(res, open(os.path.join(out, 'walkin.json'), 'w'), indent=1)
    print('walkin:', sum(r['ok'] for r in res), '/', len(res), 'ok')

# ---- the flames' colours --------------------------------------------------------------------------------------------
def part_pals(game, name='kyo'):
    """frame index -> the palette slots of its parts (build/bm_chars.c)"""
    s = open(os.path.join(game, 'build', 'bm_chars.c')).read(); out = {}
    for fi, body in re.findall(r'static const bpart_t %s_f(\d+)\[\] = \{(.*?)\};' % name, s):
        out[int(fi)] = [int(m) for m in re.findall(r'\{-?\d+, -?\d+, \d+, \d+, \d, \d, (\d+), ', body)]
    return out

def palram(b):
    """palette RAM, the bank the game shows (custom core region 104: 2 x 4096 words)"""
    b.core.retro_get_memory_data.restype = C.c_void_p
    w = (C.c_uint16 * 8192).from_address(b.core.retro_get_memory_data(104))
    return [w[k] for k in range(8192)]

FLAMES = [('EX 236A ground flame (C)', 'c', 'EX 236A', 800, 37, 30),       # (label, keys, KOF input, first frame, KOF palette byte, shot at)
          ('Orochinagi flame (D)', 'd', '21426C', 469, 33, 50)]

_B = {}
def brawler_flame(game, keys, first, at, path):
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))
    if game not in _B: _B[game] = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)   # (one core a process)
    b = _B[game]
    setup(b, roster, 400)
    want = f'0:{first}'; seen = None; shot = None
    for f in range(160):
        pad = keys if f < 4 else ''
        b.run(1, p1=pad)
        for i in range(8):                                    # the flame: a projectile entity of Kyo's showing it
            if b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'frame_ovr') < len(frames['kyo']):
                r = frames['kyo'][b.pget(i, 'frame_ovr')]
                if r and first <= int(r.split(':')[1]) <= first + 11 and seen is None: seen = (f, i, r)
        if seen and f >= seen[0] + 6 and shot is None:
            b.screenshot(path); shot = path
            pals = part_pals(game); fi = frames['kyo'].index(want)
            slot = pals[fi][0]; pb = b.fget(0, 'palbase'); ram = palram(b)
            npal = int(re.search(r'\{"KYO", (\d+),', open(os.path.join(game, 'build', 'bm_chars.c')).read()).group(1))
            return {'frame_seen': seen, 'slot': slot, 'npal': npal, 'palbase': pb,
                    'colours': [ram[(pb + slot) * 16 + k] for k in range(16)], 'shot': path}
    return {'frame_seen': seen, 'shot': None}

def flames_of(game, out, tag):
    """brawler_flame for every FLAMES entry on one build, in a process of its own (one core per process)"""
    p = os.path.join(out, 'shots', f'flames_{tag}.json')
    if not os.path.exists(p):
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), 'flames', game, out, tag], check=True)
    return json.load(open(p))

def colours(game, base, out):
    import rom96, export96, romspecials98 as K
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98')
    res = []; rows = []
    for label, keys, inp, first, pbyte, at in FLAMES:
        kof_pal = export96.pal_rom98(m, 0xB80 + (pbyte - 32))           # Kyo's effect palette (export96.palettes98)
        kd = os.path.join(out, 'shots', 'colours_kof'); os.makedirs(kd, exist_ok=True)
        tr, _, _ = K.trace(0, inp.replace('EX ', ''), 'whiff', inp.startswith('EX '), 120, dm=inp == '21426C')
        kf = next((r['f'] for r in tr if any(o['table'] == 0 and first <= (o['rec'] - rom96.frame_record(m, 0, 0)) // 6 <= first + 11 for o in r['objs'])), None)
        kp = None
        if kf is not None:
            K.trace(0, inp.replace('EX ', ''), 'whiff', inp.startswith('EX '), 120, dm=inp == '21426C', snaps=[K.START + kf + 6], snapdir=kd)
            kp = os.path.join(kd, f'snap_{K.START + kf + 6}.ppm')
        tag = first
        r_new = flames_of(game, out, 'new')[str(first)]
        r_old = flames_of(base, out, 'base')[str(first)] if base else None
        s = {'flame': label, 'kof_palette_byte': pbyte, 'kof_colours': kof_pal,
             'this_build': {k: v for k, v in r_new.items() if k != 'shot'}, 'before': r_old and {k: v for k, v in r_old.items() if k != 'shot'},
             'this_build_ok': r_new.get('colours', [None])[1:] == kof_pal[1:],
             'before_ok': r_old.get('colours', [None])[1:] == kof_pal[1:] if r_old else None}
        res.append(s); print(json.dumps({k: v for k, v in s.items() if k not in ('kof_colours',)}), flush=True)
        rows.append((label, kp, r_old and r_old.get('shot'), r_new.get('shot'), s))
    W, H = 304, 224
    im = Image.new('RGB', (3 * (W + 6) + 6, 24 + len(rows) * (H + 30)), 'white'); d = ImageDraw.Draw(im)
    d.text((6, 4), 'Kyo\'s flames: KOF98 (our emulator) | the build before (MAX_PALS 8: palette slot 8 = the next fighter\'s) | this build', fill='black')
    for j, (label, kp, op, np_, s) in enumerate(rows):
        y = 24 + j * (H + 30)
        for i, (p, cap) in enumerate(((kp, 'KOF98'), (op, f'before: slot {s["before"]["slot"] if s["before"] else "-"} of {s["before"]["npal"] if s["before"] else "-"}'),
                                     (np_, f'this build: slot {s["this_build"].get("slot")} of {s["this_build"].get("npal")}'))):
            x = 6 + i * (W + 6)
            d.text((x, y), f'{label}: {cap}, colours {"= KOF98" if (i == 0 or (s["before_ok"] if i == 1 else s["this_build_ok"])) else "NOT KOF98"}', fill='black')
            if p and os.path.exists(p): im.paste(Image.open(p).convert('RGB').resize((W, H)), (x, y + 14))
            d.rectangle([x, y + 14, x + W - 1, y + 14 + H - 1], outline='black')
    im.save(os.path.join(out, 'colours.png'))
    json.dump(res, open(os.path.join(out, 'colours.json'), 'w'), indent=1)
    print('colours:', sum(r['this_build_ok'] for r in res), '/', len(res), 'ok')

if __name__ == '__main__':
    cmd, game = sys.argv[1], sys.argv[2]
    if cmd == 'flames':                                  # (colours' worker: one build)
        out, tag = sys.argv[3], sys.argv[4]; os.makedirs(os.path.join(out, 'shots'), exist_ok=True)
        r = {str(first): brawler_flame(game, keys, first, at, os.path.join(out, 'shots', f'colours_{tag}_{first}.png'))
             for label, keys, inp, first, pbyte, at in FLAMES}
        json.dump(r, open(os.path.join(out, 'shots', f'flames_{tag}.json'), 'w'))
    elif cmd == 'colours':
        base = sys.argv[3] if len(sys.argv) > 3 else None; out = sys.argv[4] if len(sys.argv) > 4 else OUT
        os.makedirs(out, exist_ok=True)
        for t in ('new', 'base'):                        # fresh runs
            if os.path.exists(os.path.join(out, 'shots', f'flames_{t}.json')): os.remove(os.path.join(out, 'shots', f'flames_{t}.json'))
        colours(game, base, out)
    else:
        out = sys.argv[3] if len(sys.argv) > 3 else OUT; os.makedirs(out, exist_ok=True); walkin(game, out)
