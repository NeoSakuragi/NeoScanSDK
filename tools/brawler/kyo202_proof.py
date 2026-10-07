#!/usr/bin/env python3
"""TODO #202 proofs (Kyo, Bruno's notes on 0.1.8), harness.py on `make AI_OFF=1` builds (the test drives the enemies).

    python3 kyo202_proof.py inv GAME_DIR [BASE_DIR] [OUT]   EX 421D (its C slot in game.json: forward + C since #207, up-forward + C before; game.json roster kyo "invincible")
                                                    with two minions jabbing (A every frame, re-stood when knocked) on
                                                    each side of Kyo through the move from its frame 0..7 (8 runs): per
                                                    frame of the move Kyo's inv / life / state; the build before
                                                    (BASE_DIR: KOF98's own steps without a hurt box only, frames 0-10)
                                                    against this one (INV_FURY on every frame, 0 life lost, hittable
                                                    again after it); OUT/inv.json, OUT/inv_<build>.png
    python3 kyo202_proof.py bruno GAME_DIR [OUT]    Bruno's own pads of 20261007-124338 (Orochinagi held, released) and
                                                    20261007-124409 (forward + C, 236C) from a fight's start on this
                                                    build: the flames' objects per frame (state, frame, alive) and a
                                                    sheet every 2 frames; OUT/bruno_<id>.png, OUT/bruno.json

The KOF98 | brawler sheets frame by frame: romspecials_check.py with EVERY=1 SHEET_FROM=N NSHOT=M (kyo:C, kyo:M,
kyo:fD). KOF98's EX 421D ($3E0A6) hurt boxes: state 491 (frames 774 / 775, 8 frames) and 493's first step (776, 3 frames)
carry no $0200 (no hurt box), from 493's second step (777, its kick) on every step has one: frames 0-10 invincible, the
rest not (rom96.parse_anim, OUT/inv.json "kof98_hurt")."""
import json, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
from PIL import Image, ImageDraw

OUT = '/data/tmp/kyo202/out'
INV_FURY = 0xFF
MINIONS = (3, 4, 5, 6)
PADKEYS = ((0, 'a'), (8, 'b'), (1, 'c'), (9, 'd'), (4, 'U'), (5, 'D'), (6, 'L'), (7, 'R'))

def sheet(cells, path, title, cols=8, W=160, H=112):
    im = Image.new('RGB', (cols * (W + 4) + 4, 20 + ((len(cells) + cols - 1) // cols) * (H + 14)), 'white')
    d = ImageDraw.Draw(im); d.text((4, 4), title, fill='black')
    for i, (lab, p) in enumerate(cells):
        x = 4 + (i % cols) * (W + 4); y = 20 + (i // cols) * (H + 14)
        im.paste(Image.open(p).convert('RGB').resize((W, H)), (x, y + 12)); d.text((x, y), lab, fill='black')
        d.rectangle([x, y + 12, x + W - 1, y + 12 + H - 1], outline='black')
    im.save(path)

def kof98_hurt():
    import rom96
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98'); out = []; f = 0
    for st in (491, 493, 495):
        steps, _ = rom96.parse_anim(m, rom96.anim_addr(m, 0, rom96.state_slot(m, 0, st)))
        for t, fi, fl, bx, raw, dx in steps:
            out.append({'state': st, 'frame': fi, 'ticks': t, 'hurt_box': bool(fl & 0x200)})
    return out

# ---- EX 421D's invincibility --------------------------------------------------------------------------------------------
def inv_run(game, out, tag):
    from harness import Brawler
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))['kyo']
    kyo = json.load(open(os.path.join(game, 'game.json')))['roster'][roster.index('kyo')]['specials']
    ex_keys = {'D': '', 'fD': 'R', 'dD': 'D', 'uD': 'U', 'dfD': 'DR', 'ufD': 'UR'}[next(k for k, v in kyo.items() if v == 'EX 421D')]   # its
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)                     # slot (forward + C since #207)
    meter = json.load(open(os.path.join(game, 'game.json')))['meter']['max']
    b.pick(roster.index('kyo'), unlock=True); b.run(10)
    for i in range(1, 8): b.place(i, x=1000, z=0)
    b.place(0, x=120, z=30); b.run(2); w = 0
    while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
    start = b.save()
    st = b.states; res = []; cells = []
    natural = None
    for phase in [None] + list(range(8)):                            # (None: alone, the move's own length)
        b.load(start)
        for i in range(1, 8): b.fset(i, 'state', st.index('OFF')) if i not in MINIONS else None
        for i in (0,) + MINIONS:
            b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.place(0, x=120, z=30); b.fset(0, 'facing', 1); b.fset(0, 'meter', meter)   # (a special costs meter)
        for i in MINIONS: b.place(i, x=1000, z=30); b.intent(i)
        rows, started, end = [], None, None
        for f in range(260):
            if started is None and f >= 4 + (phase or 0): keys = ex_keys + 'c' if f < 8 + (phase or 0) else ''
            else: keys = ''
            s0 = st[b.fget(0, 'state')]
            if started is None and s0 == 'SPECIAL': started = f
            if started is not None and end is None and s0 != 'SPECIAL': end = f
            x, z = b.fget(0, 'x'), b.fget(0, 'z')
            for j, i in enumerate(MINIONS):                         # two on each side, 30 / 46 px away, facing him,
                fc = 1 if j < 2 else -1                             # jabbing every frame from the move's frame `phase`
                if started is None or phase is None or f < started + phase: b.place(i, x=1000); b.intent(i); continue
                if st[b.fget(i, 'state')] not in ('IDLE', 'WALK', 'ATTACK'):
                    b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'freeze', 0); b.fset(i, 'y', 0); b.fset(i, 'inv', 0)
                b.fset(i, 'hp', 60)
                b.place(i, x=x - fc * (30 + 16 * (j % 2)), z=z); b.fset(i, 'facing', fc & 0xFF); b.intent(i, press=1, face=fc & 0xFF)
            inv, hp = b.fget(0, 'inv'), b.fget(0, 'hp')
            shot = phase == 0 and started is not None and end is None and (f - started) % 2 == 0
            if shot:
                p = os.path.join(out, 'shots', f'inv_{tag}_{f - started:03d}.png'); b.pad = [set(keys), set()]; b.screenshot(p)
                cells.append((f'frame {f - started}', p))
            else: b.run(1, p1=keys)
            fo = b.fget(0, 'frame_ovr')
            rows.append(dict(f=f, st=s0, inv=inv, hp=hp, hp_after=b.fget(0, 'hp'), st_after=st[b.fget(0, 'state')],
                             frame=frames[fo] if fo < len(frames) else None, spec=b.fget(0, 'spec_id'),
                             swings=sum(st[b.fget(i, 'state')] == 'ATTACK' for i in MINIONS)))
            if end is not None and f - end > 90: break
        if started is None or end is None: res.append({'phase': phase, 'ok': False, 'why': 'no special'}); continue
        if phase is None: natural = end - started; continue
        move = [r for r in rows if started <= r['f'] < end - 1]
        hits = [r['f'] - started for r in move if r['hp_after'] < r['hp'] or (r['st_after'] in ('HITSTUN', 'KNOCKDOWN') and r['st'] == 'SPECIAL')]
        last = rows[end - 1]                                         # the move cut short by a hit (its last frame's
        if last['st_after'] in ('HITSTUN', 'KNOCKDOWN') and last['hp_after'] < last['hp'] and end - started < natural:   # combat; a
            hits.append(end - 1 - started)                           # hit on the move's own last frame: after its end)
        after = [r['f'] - end for r in rows if r['f'] >= end and r['hp_after'] < r['hp']]
        res.append({'phase': phase, 'move_frames': end - started, 'alone': natural, 'ended_in': last['st_after'], 'frames_inv_fury': sum(r['inv'] == INV_FURY for r in move),
                    'not_inv': [r['f'] - started for r in move if r['inv'] != INV_FURY][:12], 'hit_at_move_frames': hits,
                    'life_lost_in_move': sum(r['hp'] - r['hp_after'] for r in move),
                    'minion_swing_frames': sum(r['swings'] for r in move), 'first_hit_after_end': after[0] if after else None,
                    'kof_frames': [r['frame'] for r in move][:16]})
        print(tag, json.dumps(res[-1]), flush=True)
    json.dump({'res': res, 'cells': cells}, open(os.path.join(out, f'inv_{tag}.json'), 'w'), indent=1)

def inv(game, base, out):
    os.makedirs(os.path.join(out, 'shots'), exist_ok=True)
    for g, tag in ((base, 'before'), (game, 'new')):
        if g: subprocess.run([sys.executable, os.path.abspath(__file__), 'invrun', g, out, tag], check=True)   # one core a process
    R = {'kof98_hurt': kof98_hurt()}
    for tag in ('before', 'new'):
        p = os.path.join(out, f'inv_{tag}.json')
        if not os.path.exists(p): continue
        d = json.load(open(p)); R[tag] = d['res']
        hit = sorted({h for r in d['res'] for h in r.get('hit_at_move_frames', [])})
        sheet(d['cells'], os.path.join(out, f'inv_{tag}.png'),
              f'Kyo EX 421D, 4 minions jabbing every frame, {tag} build: Kyo hit at move frames {hit or "none"}')
    new = R.get('new', [])
    R['new_ok'] = bool(new) and all(r.get('move_frames') and r['frames_inv_fury'] >= r['move_frames'] - 1 and not r['hit_at_move_frames']
                                    and r['life_lost_in_move'] == 0 and r['minion_swing_frames'] > 0 and r['first_hit_after_end'] is not None
                                    for r in new)
    if 'before' in R: R['before_hits'] = sorted({h for r in R['before'] for h in r.get('hit_at_move_frames', [])})
    json.dump(R, open(os.path.join(out, 'inv.json'), 'w'), indent=1)
    print('inv:', 'OK' if R['new_ok'] else 'FAIL', 'before: hit at', R.get('before_hits'))

# ---- Bruno's own pads ------------------------------------------------------------------------------------------------------
BUNDLES = {'20261007-124338-b3f3': ('Orochinagi held then released (D)', 6, 96), '20261007-124409-b3f3': ('forward + C: 236C', 1, 0)}   # (label, spec_id, sheet from)

def bruno(game, out):
    from harness import Brawler
    os.makedirs(os.path.join(out, 'shots'), exist_ok=True)
    for bid in BUNDLES:                                              # (first: one core per process, one at a time)
        if not os.path.exists(os.path.join(out, f'his_{bid}.json')):
            subprocess.run([sys.executable, os.path.abspath(__file__), 'his', bid, out], check=True)
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))['kyo']
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    b.pick(roster.index('kyo'), unlock=True); b.run(30); start = b.save(); res = {}
    for bid, (label, spec, sfrom) in BUNDLES.items():
        d = os.path.join('/data/feedback', bid)
        raw = open(os.path.join(d, 'inputs.bin'), 'rb').read(); _, _, W, P = struct.unpack_from('<4sIQQ', raw)
        pads = [''.join(c for bit, c in PADKEYS if struct.unpack_from('<HH', raw, 24 + 4 * i)[0] >> bit & 1) for i in range(P - W)]
        his = json.load(open(os.path.join(out, f'his_{bid}.json')))   # his replay on 0.1.8 (pull.Core): the special's start
        s0 = next(r['f'] for r in his if r['state'] == 'SPECIAL' and r['spec_id'] == spec) - W
        first = max(0, s0 - 40)
        while first > 0 and pads[first - 1]: first -= 1             # from a neutral pad before his motion
        b.load(start)
        for i in range(1, 8): b.fset(i, 'state', b.states.index('OFF'))   # his wave had nobody near him
        b.place(0, x=b.r(b.syms['cam_x'], 2) + 80, z=30); b.fset(0, 'facing', 1)
        rows, cells, started = [], [], None
        for k in range(first, s0 + 200):                              # (past his press: nothing held)
            keys = pads[k] if k < len(pads) else ''
            if started is not None and k >= s0 + sfrom and (k - first) % 2 == 0 and len(cells) < 56:
                p = os.path.join(out, 'shots', f'bruno_{bid}_{k:05d}.png'); b.pad = [set(keys), set()]; b.screenshot(p)
                cells.append((f'{k - s0:+d}', p))
            else: b.run(1, p1=keys)
            stt = b.states[b.fget(0, 'state')]
            if started is None and stt == 'SPECIAL': started = k
            objs = []
            for j in range(8):
                if b.states[b.pget(j, 'state')] != 'PROJ': continue
                fo = b.pget(j, 'frame_ovr'); objs.append([j, frames[fo] if fo < len(frames) else fo])
            rows.append({'pad': k - s0, 'keys': keys, 'state': stt, 'spec': b.fget(0, 'spec_id'),
                         'frame': frames[b.fget(0, 'frame_ovr')] if b.fget(0, 'frame_ovr') < len(frames) else None, 'objects': objs})
        lives = {}
        for r in rows:                                              # each object's frames alive (by its first ROM frame)
            for j, fr in r['objects']:
                key = j; lv = lives.setdefault(key, [])
                if lv and lv[-1]['last'] == r['pad'] - 1: lv[-1]['last'] = r['pad']; lv[-1]['frames'].append(fr)
                else: lv.append({'first': r['pad'], 'last': r['pad'], 'frames': [fr]})
        res[bid] = {'label': label, 'special_from': started - s0 if started is not None else None,
                    'objects': sorted(({'first': l['first'], 'last': l['last'], 'frame0': l['frames'][0], 'n': len(l['frames'])}
                                       for lv in lives.values() for l in lv), key=lambda o: o['first'])}
        print(bid, json.dumps(res[bid]), flush=True)
        sheet(cells, os.path.join(out, f'bruno_{bid}.png'), f"Bruno's pads ({bid}: {label}) on this build, every 2 frames (frame from his special's start)")
    json.dump(res, open(os.path.join(out, 'bruno.json'), 'w'), indent=1)

def his(bid, out):
    """his bundle replayed on its own ROM (tools/feedback/pull.py's Core, the build's snapshot for fighter_t): P1's state
    and special per frame -> OUT/his_<id>.json"""
    import ctypes as C, harness
    sys.path.insert(0, os.path.join(HERE, '..', 'feedback')); import pull
    d = os.path.join('/data/feedback', bid); meta = json.load(open(os.path.join(d, 'meta.json')))
    snap = '/data/feedback/scenarios/_builds/%s/examples/brawler' % meta['rom_sha256'][:12]
    lay, fsize, states, _ = harness._layout(snap)
    nm = subprocess.run(['m68k-linux-gnu-nm', snap + '/build/rom.elf'], capture_output=True, text=True).stdout.split('\n')
    fbase = int(next(l.split()[0] for l in nm if l.endswith(' fighters')), 16)
    raw = open(os.path.join(d, 'inputs.bin'), 'rb').read(); _, _, W, P = struct.unpack_from('<4sIQQ', raw)
    core = pull.Core(pull.find_rom(meta), meta['system_type'], meta['hw'], meta.get('memcard', 'on'))
    core.core.retro_get_memory_data.restype = C.c_void_p; core.core.retro_get_memory_size.restype = C.c_size_t
    ram = (C.c_uint8 * core.core.retro_get_memory_size(2)).from_address(core.core.retro_get_memory_data(2))
    core.load(open(os.path.join(d, f'snap_{W}.state'), 'rb').read())
    def g(f):
        off, sz = lay[f]; a = fbase + off - 0x100000; return int.from_bytes(bytes(ram[a:a + sz]), 'big')
    rows = []
    for i in range(P - W):
        core.frame(*struct.unpack_from('<HH', raw, 24 + 4 * i))
        rows.append({'f': W + i, 'state': states[g('state')] if g('state') < len(states) else g('state'), 'spec_id': g('spec_id')})
    json.dump(rows, open(os.path.join(out, f'his_{bid}.json'), 'w'))

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'invrun': inv_run(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'inv':
        game = sys.argv[2]; base = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != '-' else None
        inv(game, base, sys.argv[4] if len(sys.argv) > 4 else OUT)
    elif cmd == 'bruno': bruno(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else OUT)
    elif cmd == 'his': his(sys.argv[2], sys.argv[3])
