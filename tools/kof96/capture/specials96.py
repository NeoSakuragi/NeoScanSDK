#!/usr/bin/env python3
"""KOF96 specials in MAME: every decoded command (commands96.py) of a character with each button, one MAME run per
character (state 'vs', P1 swapped in as for throws; P2 = Yuri knocked down first, then left standing far away).
Each try: positions reset (P1 x $100, P2 x $260), timer 59, P1 life 24 (red life: supers allowed), P2 life full;
see motion() for the input timing. Every non-charge command is also tried in the air (straight jump, motion 6 frames
after take-off). Recorded with record96.lua (fighters + P1-owned pool objects).
    python3 capture/specials96.py ID [ID ...]   -> capture/specials/<id>.txt + <id>.json (tries)
    python3 capture/specials96.py --passes close ID ...   -> <id>_close: ground commands next to P2 (hit versions)"""
import json, os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
from timeline import seqs
import rom96, commands96, emu
REC = os.path.join(HERE, 'record96.lua')
ROMPATH = '/home/bruno/roms/neogeo;/home/bruno/Downloads'          # kof96.zip / kof98.zip + neogeo.zip
START, GAP = 1400, 220
BTN = {'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd'}

def stick_keys(v):
    """history stick bits (facing right list) -> MAME keys"""
    return ''.join(k for bit, k in ((1, 'U'), (2, 'D'), (4, 'L'), (8, 'R')) if v & bit)

def motion(p, button):
    """events (offset, frames, keys) for one pattern. Charge steps (types 3/4) are a latched "held long enough" state
    checked first, not a history byte, so they are played first (held hold + 4 frames); then the other steps in list
    order, 2 frames each. A step whose value has button bits presses the chosen button (3 frames); the final button
    goes ON the last direction step (4 frames) - pressed a step later, KOF98 already reads forward-forward as a run.
    'any' stick steps (type 1) add their bits to the previous direction (623 gets a real down-forward); type 11
    (KOF98) keeps the previous direction only if it is not one of the step's forbidden directions."""
    ev, t = [], 0
    charge = [(ty, v) for ty, v in p['steps'] if ty in (3, 4)]
    rest = [(ty, v) for ty, v in p['steps'] if ty not in (3, 4)]
    for ty, v in charge:
        ev.append((t, p['hold'] + 4, stick_keys(v))); t += p['hold'] + 4
    def pick(v): return button if (v >> (4 + 'ABCD'.index(button))) & 1 else 'ABCD'[[i for i in range(4) if v >> (4 + i) & 1][0]]
    for k, (ty, v) in enumerate(rest):
        last = k == len(rest) - 1
        prev = ev[-1][2].rstrip('abcd') if ev else ''
        keys = stick_keys(v)
        needs_button = v >> 4 and ty not in (0, 5, 6, 10)
        if ty == 11: keys = '' if any(c in stick_keys(v) for c in prev) else prev
        elif ty == 1 and keys: keys = ''.join(c for c in 'UDLR' if c in prev + keys and not ({c} <= set('UD') and set('UD') <= set(prev + keys)))
        elif needs_button and not keys: keys = prev
        if needs_button and last and ev and not ev[-1][2].endswith(tuple('abcd')) and ev[-1][2] == keys and keys:
            o, n, kk = ev.pop(); t = o                      # merge the button into the last direction step
            ev.append((t, 4, keys + BTN[pick(v)])); t += 4; continue
        if needs_button:
            n = 4 if last else 3
            ev.append((t, n, keys + BTN[pick(v)])); t += n
        elif ty == 2 and v == 0:                           # no button pressed
            ev.append((t, 2, '')); t += 2
        else:
            ev.append((t, 2, keys)); t += 2
    return ev

def tries(m, cid, ex=0):
    L = commands96.patterns(m, commands96.lists(m, cid, ex)[1])
    out = []
    for k, p in enumerate(L):
        if p is None or k < 3: continue                  # 0-2: run, backstep, super jump (shared)
        bits = 0
        for ty, v in p['steps']:
            if ty not in (0, 5, 6, 3, 4): bits |= v >> 4      # the button the move code reads: any of the button steps
        buttons = [b for i, b in enumerate('ABCD') if (bits >> i) & 1] or ['A']
        for b in buttons: out.append({'cmd': k, 'button': b, 'notation': commands96.notation(p), 'events': motion(p, b), 'air': False})
        if not any(ty in (3, 4) for ty, v in p['steps']):      # air version: jump straight up, motion 6 frames later
            for b in buttons:
                out.append({'cmd': k, 'button': b, 'notation': commands96.notation(p), 'air': True,
                            'events': [(0, 3, 'U')] + [(t + 6, n, keys) for t, n, keys in motion(p, b)]})
    return out

def outdir(m): return os.path.join(HERE, {'kof96': 'specials', 'kof98': 'specials98'}.get(m.game, 'specials_' + m.game))

def prep(game, cid, ex=False):
    """the fighter's starting state c<cid> (c<cid>x = EX), made once, the same way on both emulators: from 'vs' swap P1
    to cid (team ids + P1 life 1, P2 hits), earn power stocks the game's way (P1 hits P2 with C every 40 frames for
    ~1100 frames: poking stock bytes did not enable KOF98 supers), place both fighters (P1 x $100, P2 x $260, P2 life
    full, timer 59) and save"""
    name = f'c{cid}{"x" if ex else ""}'
    if emu.state_exists(game, name): return
    g = emu.GAMES[game]; L = g['load_frames']; fill_end = L + g.get('fill_frames', 1100)
    spec = ['p2 20 60 L', 'p2 85 3 c'] + [f'p1 {f} 3 c' for f in range(L - L % 40 + 40, fill_end, 40)]
    pokes = [f'2:{emu.swap_pokes(game, cid, ex)}']
    for f in range(L - L % 40 + 40, fill_end, 40):
        pokes.append(f'{f}:108118=01,108119=C0,108318=01,108319=E8,{g["timer"]:X}=59,{emu.life_pokes(game, 0x108300, g["life_full"])}')
    pokes.append(f'{fill_end + 30}:108118=01,108119=00,108318=02,108319=60,{g["timer"]:X}=59,{emu.life_pokes(game, 0x108300, g["life_full"])}')
    s1, s2 = seqs('; '.join(spec), fill_end + 70)
    emu.run(game, '/dev/null', s1, s2, pokes, save=[(fill_end + 60, name)], timeout=900)

prep98 = lambda cid, ex=False: prep('kof98', cid, ex)        # used by throws96 / wins98

def run(cid, m, T=None, tag='', close=False, ex=False):
    """tag '' = all commands (ground + air), '_max' = MAX-mode supers, '_close' = ground commands next to P2
    (command grabs), '_ex' = EX versions. KOF98/KOF99: every try starts from the fighter's prepared state."""
    T = T if T is not None else tries(m, cid)
    out = os.path.join(outdir(m), f'{cid}{tag}.txt'); os.makedirs(os.path.dirname(out), exist_ok=True)
    if m.game != 'kof96':
        prep(m.game, cid, ex); spec, pokes, reload = [], [], []
        s = 40
        for t, tr in enumerate(T):
            gap = tr.setdefault('gap', 320 if tr.get('max') else GAP)     # MAX/counter moves start 40 frames late
            tr['start'] = s; reload.append(s - 4)
            if close: pokes.append(f'{s - 2}:108118=01,108119=80,108318=01,108319=B0')
            for off, n, keys in tr['events']:
                if keys: spec.append(f'p1 {s + off} {n} {keys}')
            s += gap
        s1, s2 = seqs('; '.join(spec), s + 20)
        emu.run(m.game, out, s1, s2, pokes, reload=f'c{cid}{"x" if ex else ""}', reload_frames=reload)
    else:
        spec = ['p2 20 60 L', 'p2 85 3 c']
        pokes = [f'2:108238=0,108239=1,108250=0,108251=1,10A846={cid:02X},10A847={cid:02X},10A848={cid:02X}']
        for t, tr in enumerate(T):
            s = START + GAP * t; tr['start'] = s
            x1, x2 = ('80', 'B0') if close else ('00', '60')          # close pass: P1 x $180, P2 x $1B0, as KOF98's
            pokes.append(f'{s - 3}:108118=01,108119={x1},108318={"01" if close else "02"},108319={x2},10A836=59,108238=0,108239=18,108250=0,108251=18,'
                         f'108438=0,108439=67,108450=0,108451=67')
            for off, n, keys in tr['events']:
                if keys: spec.append(f'p1 {s + off} {n} {keys}')
        s1, s2 = seqs('; '.join(spec), START + GAP * len(T) + 20)
        emu.run('kof96', out, s1, s2, pokes)
    json.dump(T, open(os.path.join(outdir(m), f'{cid}{tag}.json'), 'w'), indent=1)
    return out, T

def max_tries(m, cid, cmds):
    """KOF98 second pass: the commands that gave a super, done in MAX mode (A+B+C, motion 40 frames later): SDMs"""
    out = []
    for tr in tries(m, cid):
        if tr['cmd'] in cmds and not tr['air']:
            ev = [(t + 40, n, keys) for t, n, keys in tr['events']]
            if m.game == 'kof99':                          # KOF99 counter mode: the SDM takes two buttons (A+C / B+D)
                if tr['button'] not in 'AB': continue
                t0, n0, k0 = ev[-1]; ev[-1] = (t0, n0, k0.rstrip('abcd') + ('ac' if tr['button'] == 'A' else 'bd'))
                tr = dict(tr, button='AC' if tr['button'] == 'A' else 'BD')
            out.append(dict(tr, max=True, events=[(0, 3, 'abc')] + ev))
    return out

if __name__ == '__main__':
    args = sys.argv[1:]; game = 'kof96'; passes = ['main']
    if args[:1] == ['--game']: game = args[1]; args = args[2:]
    if args[:1] == ['--passes']: passes = args[1].split(','); args = args[2:]      # main,max,close (KOF98)
    prom, _ = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    sys.path.insert(0, os.path.join(HERE, '..')); import specials96 as analysis
    for cid in map(int, args):
        if 'main' in passes:
            out, T = run(cid, m); print(cid, 'main', len(T), 'tries', flush=True)
        if 'max' in passes:
            sup = {sp['cmd'] for sp in analysis.load(m, cid, tags=['']) if sp['condition'] == 'super'}
            T = max_tries(m, cid, sup)
            if T: run(cid, m, T, '_max')
            print(cid, 'max', len(T), 'tries', flush=True)
        if 'sdm' in passes:                                # KOF99: SDM = the DM motion with two buttons (A+C / B+D)
            sup = {sp['cmd'] for sp in analysis.load(m, cid, tags=['']) if sp['condition'] == 'super'}
            T = []
            for tr in tries(m, cid):
                if tr['cmd'] not in sup or tr['air'] or tr['button'] not in 'AB': continue
                pair = 'ac' if tr['button'] == 'A' else 'bd'
                ev = list(tr['events']); t0, n0, k0 = ev[-1]; ev[-1] = (t0, n0, k0.rstrip('abcd') + pair)
                T.append(dict(tr, button=pair.upper(), sdm=True, events=ev))
            if T: run(cid, m, T, '_sdm')
            print(cid, 'sdm', len(T), 'tries', flush=True)
        if 'ex' in passes:                                 # KOF98 EX versions (incl. Orochi team, Omega Rugal)
            T = tries(m, cid, ex=1)
            run(cid, m, T, '_ex', ex=True); print(cid, 'ex', len(T), 'tries', flush=True)
        if 'close' in passes:
            T = [tr for tr in tries(m, cid) if not tr['air']]
            run(cid, m, T, '_close', close=True); print(cid, 'close', len(T), 'tries', flush=True)
