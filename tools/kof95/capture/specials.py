#!/usr/bin/env python3
"""Special-move capture for any KOF95 character (MAME, save state 'a', cast swap as in throws.py).
Before every try both fighters are put 120 px apart at mid-stage, P2's health and the round timer are refilled.
P1 then performs one motion + button. Recorded with record_spawn.lua: P1's object and every pool object P1 owns.

Per try that produced a special (P1 game state >= 112, outside the throw):
  states     P1 game states in order, each with its animation slot from the ROM's state->slot map
  objects    spawned objects: table id (from the sprite-definition pointer), states (= slots of that table) in order,
             spawn offset from P1 (P1-facing x, height), velocity over the first frames, lifetime
    python3 capture/specials.py ID [ID ...]      run MAME + analyse -> capture/specials/<id>.json
    python3 capture/specials.py --reuse ID ...   analyse existing captures only"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
import analyze as A, rom, commands
from neogeo.sprite_decode import r16, r32
from timeline import seqs

ROUND, GAP = 1100, 260
P1X, P2X = 0x190, int(os.environ.get('P2X', '520'))  # P1 at 400; P2 at 520 (P2X=440 for command grabs)
MOTIONS = {                                      # P1 faces right; numpad notation in the name
    '236': ['D', 'DR', 'R'], '214': ['D', 'DL', 'L'], '623': ['R', 'D', 'DR'], '421': ['L', 'D', 'DL'],
    '41236': ['L', 'DL', 'D', 'DR', 'R'], '63214': ['R', 'DR', 'D', 'DL', 'L'], '22': ['D', '-', 'D'],
    '[4]6': ['L'] * 16 + ['R'], '[2]8': ['D'] * 16 + ['U'],
}
AIR = {'j.236': ['D', 'DR', 'R'], 'j.214': ['D', 'DL', 'L'], 'j.22': ['D', '-', 'D']}
BUTTONS = 'abcd'

def tries():
    """motion = 4 frames per direction, then the last direction with the button held together for 8 frames
    (the timing that reliably gives Terry's Power Wave; the game reads the stick a few frames late)"""
    out = []
    for name, dirs in MOTIONS.items():
        for b in BUTTONS:
            ev, t = [], 10                           # 10 neutral frames after the reset
            for d in dirs[:-1]:
                if d != '-': ev.append(f'p1 {t} 4 {d}')
                t += 4
            ev.append(f'p1 {t} 8 {dirs[-1]}{b}')
            out.append((f'{name}{b.upper()}', '; '.join(ev)))
    for name, dirs in AIR.items():
        for b in BUTTONS:
            ev, t = ['p1 10 6 UR'], 20               # jump forward, motion on the way up
            for d in dirs[:-1]:
                if d != '-': ev.append(f'p1 {t} 3 {d}')
                t += 3
            ev.append(f'p1 {t} 6 {dirs[-1]}{b}')
            out.append((f'{name}{b.upper()}', '; '.join(ev)))
    return out
BRUTE = tries()

STICK_DIRS = {1: 'U', 2: 'D', 4: 'L', 8: 'R', 5: 'UL', 9: 'UR', 6: 'DL', 10: 'DR', 0: '-'}   # back = L (P1 faces right)

def command_tries(prom, cid):
    """one try per decoded command (commands.py) and button: weak and strong for P/K, exact buttons otherwise"""
    out = []
    for c in commands.cast_commands(prom)[rom.CAST[cid]]:
        steps = c['pattern']; btn_step = steps[-1]; typ, inp = btn_step[0], btn_step[1]
        if c['condition'] == 'mash':
            letters = [n for b, n in commands.BUTTONS if inp & b]
            variants = [(f"{c['input']}", letters[0].lower())] if typ & 0x80 else [('PPPP(A)', 'a'), ('PPPP(C)', 'c')]
            for label, b in variants:
                ev = [f'p1 {10 + 4 * k} 2 {b}' for k in range(5)]
                out.append((f"{c['slot']}:{label}", '; '.join(ev), c))
            continue
        if typ & 0x80: variants = [(''.join(n for b, n in commands.BUTTONS if inp & b).lower(),)]
        else: variants = [('a' if inp & 0x10 else '') + ('b' if inp & 0x20 else ''), ('c' if inp & 0x10 else '') + ('d' if inp & 0x20 else '')]
        variants = [v if isinstance(v, str) else v[0] for v in variants]
        air = c['condition'] in ('airborne', 'in the air')
        for bt in dict.fromkeys(variants):
            ev, t = ([f'p1 10 6 UR'], 22) if air else ([], 10)
            last = '-'
            for typ_, inp_, mask, frames in steps[:-1]:
                d = STICK_DIRS.get(inp_ & 15, '-')
                n = (frames + 6) if typ_ & 1 else (3 if air else 4)
                if d != '-': ev.append(f'p1 {t} {n} {d}')
                t += n; last = d
            if ev and last != '-' and not (steps[-2][0] & 1):   # button goes in together with the last direction
                t -= int(ev.pop().split()[2])
            ev.append(f'p1 {t} 8 {last if last != "-" else ""}{bt}'.replace(' -', ' '))
            out.append((f"{c['slot']}:{c['input']}:{bt.upper()}", '; '.join(ev), c))
    return out

def plan(prom, cid):
    return command_tries(prom, cid) if os.environ.get('MODE', 'commands') == 'commands' else [(n, e, None) for n, e in BRUTE]

def state_map(prom, cid):
    """game state -> animation slot (ROM table via $57D0A -> $7C948, second byte of each pair = normal play)"""
    ptr = r32(prom, 0x7C948 + r16(prom, 0x57D0A + cid * 2) * 4)
    return lambda s: prom[ptr + 2 * s + 1]

def run(cid):
    prom, _ = rom.load(); TRIES = plan(prom, cid); TOTAL = ROUND + GAP * len(TRIES) + 60
    out = os.path.join(HERE, os.environ.get('SPECIALS_DIR', 'specials'), f'{cid}.txt'); os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = 'p2 20 45 L; p2 70 3 c; ' + '; '.join(
        ' '.join([w, str(int(s) + ROUND + GAP * t), n, i])
        for t, (_, ev, _) in enumerate(TRIES) for w, s, n, i in (e.split() for e in ev.split(';')))
    s1, s2 = seqs(spec, TOTAL)
    per_try = []
    for t in range(len(TRIES)):
        f = ROUND + GAP * t - 2
        # both fighters back to neutral: code pointer -> the generic "move over" routine at $281C8 (clears height,
        # velocity, state 0, installs the idle routine); then positions, P2 health, round timer
        per_try.append(f'{f - 2}:108100=00,108101=02,108102=81,108103=C8,108300=00,108301=02,108302=81,108303=C8;')
        per_try[-1] += (f'{f}:108118={P1X >> 8:02X},108119={P1X & 255:02X},108318={P2X >> 8:02X},108319={P2X & 255:02X},'
                       f'108420=00,108421=CF,108422=00,108423=CF,10844C=00,10844D=CF,10A836=59,108218=00,108219=7F')   # +$118 = power gauge, 127 = full (supers)
    # P1 health 1 + P1 team record ($10A840: +3..+5 = member ids) set to the character: after P2's hit the game
    # loads that fighter for the next round with everything (graphics, moves, throws) of its own
    poke = (f'2:108220=0,108221=1,108222=0,108223=1,10824C=0,10824D=1,10A843={cid:02X},10A844={cid:02X},10A845={cid:02X};' + ';'.join(per_try))
    env = dict(os.environ, SEQ=s1, SEQ2=s2, POKE=poke, OUT=out)
    subprocess.run(['mame', 'kof95', '-rompath', '/home/bruno/Downloads', '-state', 'a', '-video', 'none', '-sound', 'none',
                    '-nothrottle', '-skip_gameinfo', '-noplugin', 'cart_bridge', '-autoboot_script', os.path.join(HERE, 'record_spawn.lua')],
                   env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    return out

def load(path):
    """[(frame, P1 words, [spawned objects])]; object = dict(base, rec, x, y, sdef, face)"""
    rows = []
    for line in open(path):
        parts = line.split()
        w = [int(parts[3][k:k + 4], 16) for k in range(0, len(parts[3]), 4)]
        objs = []
        if parts[-1] != '-':
            for o in parts[-1].split(';'):
                f7 = o.split(':'); b, rec, x, y, sd, f = f7[:6]
                objs.append({'base': b, 'rec': int(rec, 16), 'x': int(x), 'y': int(y), 'sdef': int(sd, 16), 'face': int(f),
                             'pal': int(f7[6], 16) if len(f7) > 6 else None, 'state': int(f7[7]) if len(f7) > 7 else None})
        rows.append((int(parts[0]), w, objs))
    return rows

def analyse(cid, path):
    prom, _ = rom.load(); slot = state_map(prom, cid); TRIES = plan(prom, cid)
    sd_ids = {r32(prom, 0x080080 + i * 4): i for i in range(30)}
    rows = load(path)
    assert sd_ids.get((rows[ROUND][1][0x3C // 2] << 16) | rows[ROUND][1][0x3E // 2]) == cid, 'character swap failed'
    found = []
    for t, (name, _, cmd) in enumerate(TRIES):
        lo, hi = ROUND + GAP * t, min(len(rows), ROUND + GAP * (t + 1) - 4)
        win = rows[lo:hi]
        states = []
        for _, w, _ in win:
            s = A.state_of(w)
            if not states or states[-1][0] != s: states.append([s, 1])
            else: states[-1][1] += 1
        special = [s for s, _ in states if s >= 112 and s != 144]
        if not special: continue
        # spawned objects: group by pool slot + first appearance
        objs = {}
        before = {o['base'] for o in win[0][2]}          # helpers P1 always owns (shadow etc.) are not spawns
        for k, (_, w, os_) in enumerate(win):
            os_ = [o for o in os_ if o['base'] not in before]
            face = 1 if A.facing_of(w) else -1
            for o in os_:
                key = o['base']
                if key not in objs:
                    objs[key] = {'first': k, 'table': sd_ids.get(o['sdef']), 'palette_slot': o['pal'], 'track': []}
                objs[key]['track'].append([k, None, o['x'], o['y'], o['rec'], o['face'], o['state']])
        spawned = []
        for key, o in objs.items():
            tr = o['track']; k0 = tr[0][0]; w0 = win[k0][1]; face = 1 if A.facing_of(w0) else -1
            xs = [p[2] for p in tr]
            vx = [round((xs[i + 1] - xs[i]) * face, 2) for i in range(min(8, len(xs) - 1))]
            spawned.append({'table': o['table'], 'palette_slot': o['palette_slot'], 'appears_after': k0, 'frames': len(tr),
                            'dx': round((xs[0] - A.x_of(w0)) * face, 1), 'height': tr[0][3],
                            'vx_first_frames': vx, 'records': sorted({f'{p[4]:06X}' for p in tr})[:12],
                            'states': [s for i, s in enumerate(p[6] for p in tr) if i == 0 or s != tr[i - 1][6]],
                            'path': [[p[0] - k0, round((p[2] - xs[0]) * face, 1), p[3]] for p in tr]})
        # per-frame replay script from the first special frame until the fighter is neutral and its spawns are gone:
        # [fighter frame record, x from start (fighter-facing), height, [[object record, x, height, table, palette slot,
        #  same facing as fighter] ...]]
        k0 = next(k for k, (_, w, _) in enumerate(win) if A.state_of(w) >= 112 and A.state_of(w) != 144)
        w0 = win[k0][1]; face0 = 1 if A.facing_of(w0) else -1; x0 = A.x_of(w0)
        script = []
        for k in range(max(0, k0 - 2), len(win)):
            _, w, os_ = win[k]
            os_ = [o for o in os_ if o['base'] not in before]
            if k > k0 + 8 and A.state_of(w) in (0, 1, 2) and not os_: break
            script.append([f'{A.frame_of(w):06X}', round((A.x_of(w) - x0) * face0, 1), round(A.y_of(w), 1),
                           [[f"{o['rec']:06X}", round((o['x'] - x0) * face0, 1), o['y'], sd_ids.get(o['sdef']), o['pal'],
                             int(o['face'] == A.facing_of(w))] for o in os_]])
        found.append({'input': name, 'script': script, 'command': ({k: cmd[k] for k in ('slot', 'command', 'input', 'condition')} if cmd else None), 'states': [[s, n, slot(s)] for s, n in states],
                      'special_states': sorted(set(special)), 'spawned': spawned})
    return found

if __name__ == '__main__':
    reuse = sys.argv[1] == '--reuse'
    for cid in map(int, sys.argv[2:] if reuse else sys.argv[1:]):
        path = os.path.join(HERE, os.environ.get('SPECIALS_DIR', 'specials'), f'{cid}.txt') if reuse else run(cid)
        try: res = analyse(cid, path)
        except AssertionError as e: print(cid, e, flush=True); continue
        json.dump(res, open(os.path.join(HERE, os.environ.get('SPECIALS_DIR', 'specials'), f'{cid}.json'), 'w'), indent=1)
        print(cid, rom.CAST[cid], [(r['input'], r['special_states'], len(r['spawned'])) for r in res], flush=True)
