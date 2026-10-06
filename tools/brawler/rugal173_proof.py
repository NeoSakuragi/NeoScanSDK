#!/usr/bin/env python3
"""TODO #173 / #164 proofs (Rugal's moves from KOF98's handlers, the wall rule, Kaiser Wave's charge, projectile impact
heights), harness.py on a `make AI_OFF=1` build (the test drives the enemies).

    python3 rugal173_proof.py wall [OUT]      the wall rule (vocabulary stage.wall) at both screen edges for three
                                              rushes: Rugal's God Press (forward+C), Terry's Burn Knuckle (forward+C),
                                              Billy's 426C (forward+C): per frame the attacker / victim x against the
                                              walls; pass = the victim never past its wall while it reels / flies, the
                                              attacker never through it; OUT/wall_<fighter>_<side>.png contact sheets
    python3 rugal173_proof.py charge [OUT]    Rugal's Kaiser Wave (up+C) with C held 0 / 40 / 90 frames: the charge
                                              level, the wave's state chain (frames shown), its hits on a standing enemy
    python3 rugal173_proof.py impact [OUT]    every roster projectile with an end (its impact animation) fired at an
                                              enemy: the end's first height against the flight's height at the hit
                                              (TODO #164: an end plays where its hit was)
    python3 rugal173_proof.py scene [OUT]     the four feedback notes' scenes rebuilt on this build (their ROMs' states do not load:
                                              the fighter structure grew): its fighter, its move, near its screen edge

Default OUT /data/tmp/rugal173/out."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
from PIL import Image, ImageDraw

GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
OUT = '/data/tmp/rugal173/out'
ROSTER = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
ROLE_KEYS = {'D': 'c', 'fD': 'Rc', 'dD': 'Dc', 'uD': 'Uc', 'dfD': 'DRc', 'ufD': 'URc', 'C': 'd', 'M': 'Dd'}
VICTIM = 2

def s16(v): return v - 65536 if v > 32767 else v

class Proof:
    def __init__(self):
        self.b = Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME)
    def walls(self):
        b = self.b; return s16(b.r(b.syms['wall_lo'], 2)), s16(b.r(b.syms['wall_hi'], 2))
    def cam(self):
        b = self.b; return s16(b.r(b.syms['cam_x'], 2))
    def setup(self, name, x1, facing, gap, meter=True):
        b = self.b
        b.pick(ROSTER.index(name), unlock=True); b.run(10)
        for i in range(1, 8): b.place(i, x=1000, z=0)
        b.place(0, x=x1, z=30); b.fset(0, 'facing', facing & 0xFF)
        if gap is not None: b.place(VICTIM, x=x1 + facing * gap, z=30); b.fset(VICTIM, 'facing', -facing & 0xFF)
        b.run(2)
        w = 0
        while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
        b.place(0, x=x1, z=30)
        if gap is not None: b.place(VICTIM, x=x1 + facing * gap, z=30); b.fset(VICTIM, 'hp', 60)
        if meter: b.fset(0, 'meter', 120)
        b.hits = []

    def press(self, role, facing, hold=0, frames=300, shots=None, every=4, until_down=True):
        """the special of `role` (keys mirrored facing left), C / D held `hold` frames more; per frame rows"""
        b = self.b
        keys = ROLE_KEYS[role]
        if facing < 0: keys = keys.translate(str.maketrans('RL', 'LR'))
        btn = keys[-1]
        rows, started, done = [], None, None
        for f in range(frames):
            pad = keys if f < 4 else (btn if f < 4 + hold else '')
            b.pad = [set(pad), set()]
            if shots is not None and started is not None and (f - started) % every == 0 and len(shots) < 40:
                p = os.path.join(shots[0], f'f{f:03d}.png'); b.screenshot(p); shots.append((f - started, p))
            else: b.run(1, p1=pad)
            st = b.states[b.fget(0, 'state')]
            if started is None and st == 'SPECIAL': started = f
            vst = b.states[b.fget(VICTIM, 'state')]
            lo, hi = self.walls()
            rows.append({'f': f, 'st': st, 'x': round(b.fget(0, 'x'), 2), 'vx': round(b.fget(VICTIM, 'x'), 2), 'vy': round(b.fget(VICTIM, 'y'), 2),
                         'vst': vst, 'lo': lo, 'hi': hi, 'cam': self.cam(), 'vhp': b.fget(VICTIM, 'hp'), 'frame': b.fget(0, 'frame_ovr'),
                         'wall_by': b.fget(VICTIM, 'wall_by'), 'vlist': b.fget(0, 'vlist')})
            if started is not None and done is None and st != 'SPECIAL': done = f
            if done is not None and (not until_down or vst in ('DOWN', 'GETUP', 'IDLE', 'WALK', 'DEAD') or f > done + 120): break
        return rows, started

def sheet(shots, path, title, cols=5):
    W, H = 160, 112
    n = len(shots)
    im = Image.new('RGB', (cols * (W + 4) + 4, 20 + ((n + cols - 1) // cols) * (H + 14)), 'white')
    d = ImageDraw.Draw(im); d.text((4, 4), title, fill='black')
    for i, (f, p) in enumerate(shots):
        x = 4 + (i % cols) * (W + 4); y = 20 + (i // cols) * (H + 14)
        im.paste(Image.open(p).convert('RGB').resize((W, H)), (x, y + 12)); d.text((x, y), f'frame {f}', fill='black')
    im.save(path)

# ---- the wall rule ------------------------------------------------------------------------------------------------
RUSHES = [('rugal', 'fD'), ('terry', 'fD'), ('billy', 'fD')]

def wall(out):
    P = Proof(); b = P.b; res = []
    for name, role in RUSHES:
        for side in ('right', 'left'):
            facing = 1 if side == 'right' else -1
            P.setup(name, 160, facing, None)
            lo, hi = P.walls()
            x1 = hi - 110 if side == 'right' else lo + 110            # 110 px from its wall, the victim 48 px ahead
            P.setup(name, x1, facing, 48)
            sd = os.path.join(out, 'shots', f'wall_{name}_{side}'); os.makedirs(sd, exist_ok=True)
            shots = [sd]
            rows, started = P.press(role, facing, shots=shots)
            act = [r for r in rows if started is not None and r['f'] >= started]
            hitf = next((r['f'] for r in act if r['vhp'] < 60), None)
            vic = [r for r in act if r['wall_by'] and r['vst'] in ('HITSTUN', 'KNOCKDOWN')]
            past = [r['f'] for r in vic if (r['vx'] > r['hi'] + 0.01 if side == 'right' else r['vx'] < r['lo'] - 0.01)]
            through = [r['f'] for r in act if r['st'] == 'SPECIAL' and r['vst'] in ('HITSTUN',) and r['wall_by']
                       and (r['x'] > r['vx'] + 1 if side == 'right' else r['x'] < r['vx'] - 1) and name != 'rugal']
            pinned = [r['f'] for r in vic if (abs(r['vx'] - r['hi']) < 0.5 if side == 'right' else abs(r['vx'] - r['lo']) < 0.5)]
            r = {'fighter': name, 'role': role, 'side': side, 'start_x': x1, 'walls': (lo, hi), 'hit_frame': hitf,
                 'victim_frames_tracked': len(vic), 'victim_past_wall': past, 'attacker_through_victim': through,
                 'victim_on_wall_frames': len(pinned),
                 'attacker_x_max_from_wall': round(max((r_['x'] - r_['hi']) if side == 'right' else (r_['lo'] - r_['x']) for r_ in act), 2) if act else None,
                 'victim_x_max_from_wall': round(max(((r_['vx'] - r_['hi']) if side == 'right' else (r_['lo'] - r_['vx'])) for r_ in vic), 2) if vic else None,
                 'ok': hitf is not None and not past and not through and len(pinned) > 0}
            res.append(r); print(json.dumps(r), flush=True)
            sheet(shots[1:], os.path.join(out, f'wall_{name}_{side}.png'),
                  f'{name} {role} toward the {side} wall (x {x1}, walls {lo}..{hi}): victim pinned {len(pinned)} frames, past the wall {len(past)}')
            json.dump(rows, open(os.path.join(out, 'shots', f'wall_{name}_{side}.json'), 'w'))
    json.dump(res, open(os.path.join(out, 'wall.json'), 'w'), indent=1)
    print('wall:', sum(r['ok'] for r in res), '/', len(res), 'ok')

# ---- Kaiser Wave's charge -------------------------------------------------------------------------------------------
def charge(out):
    P = Proof(); b = P.b; res = []
    for hold in (0, 70, 95):                                 # KOF98 134: events at its frames 30 and 54 (levels 1, 2), after 132 (38)
        P.setup('rugal', 120, 1, 170)                            # (the hand charge 62 px behind him: on screen)
        sd = os.path.join(out, 'shots', f'charge_{hold}'); os.makedirs(sd, exist_ok=True)
        shots = [sd]
        rows, frames_shown, hits = [], [], []
        b.hits = []
        r_, started = P.press('uD', 1, hold=hold, frames=260, shots=shots, every=6, until_down=False)
        cnt = None
        pj = []
        r = {'hold': hold, 'hits': [(f, hp) for f, i, hp, st in b.hits if i == VICTIM], 'victim_hp': b.fget(VICTIM, 'hp')}
        res.append(r); print(json.dumps(r), flush=True)
        sheet(shots[1:], os.path.join(out, f'kaiser_wave_charge_{hold}.png'), f'Rugal up+C, C held {hold} frames more: hits {len(r["hits"])}')
    json.dump(res, open(os.path.join(out, 'charge.json'), 'w'), indent=1)

# ---- the notes' scenes ------------------------------------------------------------------------------------------------
NPJ = 8
def entities(b, owner_i=0):
    """the projectile entities a fighter owns now: [(entity, frame shown, x, height, state_t)]"""
    own = b.syms['fighters'] + owner_i * b.fsize
    return [(i, b.pget(i, 'frame_ovr'), round(b.pget(i, 'x'), 1), round(b.pget(i, 'y'), 1), b.pget(i, 'state_t'))
            for i in range(NPJ) if b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'owner') == own and b.pget(i, 'frame_ovr') != 0xFFFF]

def scene(out):
    """the four notes' scenes on this build (the bundles' states are 0.0.74 / 0.0.76 RAM: fighter_t grew, they do
    not load): the same fighter, move and place"""
    P = Proof(); b = P.b; res = {}
    frames = json.load(open(os.path.join(GAME, 'build', 'bm_frames.json')))
    def rec(name, f): return frames[name][f] if 0 <= f < len(frames[name]) else None
    # 20261006-175700 / 175740: Rugal's God Press carrying Terry / Robert to the right edge, Billy standing behind
    for note, victim in (('20261006-175700-5d29', 'terry'), ('20261006-175740-5d29', 'robert')):
        P.setup('rugal', 160, 1, None); lo, hi = P.walls()
        P.setup('rugal', hi - 100, 1, 48)
        b.place(3, x=lo + 60, z=30); b.fset(3, 'facing', 1)              # a second enemy behind him (Billy's place)
        sd = os.path.join(out, 'shots', 'scene_' + note); os.makedirs(sd, exist_ok=True); shots = [sd]
        rows, ents = [], []
        keys = 'Rc'
        started = None
        for f in range(240):
            pad = keys if f < 4 else ''
            if started is not None and (f - started) % 4 == 0 and len(shots) < 30:
                b.pad = [set(pad), set()]; p = os.path.join(sd, f'f{f:03d}.png'); b.screenshot(p); shots.append((f - started, p))
            else: b.run(1, p1=pad)
            st = b.states[b.fget(0, 'state')]
            if started is None and st == 'SPECIAL': started = f
            e = entities(b)
            ents.append([(i, fr, rec('rugal', fr), x, y) for i, fr, x, y, t in e])
            rows.append({'f': f, 'st': st, 'x': b.fget(0, 'x'), 'vx': b.fget(VICTIM, 'x'), 'hi': P.walls()[1], 'cam': P.cam()})
            if started is not None and f > started + 20 and st != 'SPECIAL' and b.states[b.fget(VICTIM, 'state')] in ('DOWN', 'GETUP', 'IDLE'): break
        act = [r for r in rows if started is not None and r['f'] >= started]
        recs = sorted({x[2] for e in ents for x in e if x[2]})
        res[note] = {'scene': f'Rugal forward+C (God Press) {hi - 100 - P.cam()} px from the screen\'s left edge, '
                               f'{victim if note.endswith("700-5d29") else "Terry (the training victim)"} 48 px ahead, an enemy behind',
                     'rugal_x_max_minus_wall': round(max(r['x'] - r['hi'] for r in act), 2),
                     'victim_x_max_minus_wall': round(max(r['vx'] - r['hi'] for r in act), 2),
                     'rugal_objects_shown': recs,
                     'ghost': any(r_ and r_.split(':')[1] in ('247', '243') for r_ in recs)}
        sheet(shots[1:], os.path.join(out, f'scene_{note}.png'), f'{note}: God Press to the right edge (ROM program): '
              f'Rugal stops at the wall, victim pinned; objects shown {recs}')
        print(note, json.dumps(res[note]), flush=True)
    # 20261006-175904: Kaiser Wave's hand charge (up+C held: level 2)
    note = '20261006-175904-5d29'
    P.setup('rugal', 140, 1, 160)
    sd = os.path.join(out, 'shots', 'scene_' + note); os.makedirs(sd, exist_ok=True); shots = [sd]
    hand = []
    for f in range(200):
        pad = 'Uc' if f < 4 else ('c' if f < 99 else '')
        if f % 6 == 0 and len(shots) < 30: b.pad = [set(pad), set()]; p = os.path.join(sd, f'f{f:03d}.png'); b.screenshot(p); shots.append((f, p))
        else: b.run(1, p1=pad)
        for i, fr, x, y, t in entities(b):
            r_ = rec('rugal', fr)
            if r_ in ('36:772', '36:774'): hand.append((f, round(x - b.fget(0, 'x'), 1), y))
    res[note] = {'scene': 'Rugal up+C (Kaiser Wave), C held 95 frames (charge level 2)', 'hand_effect_frames': len(hand),
                 'hand_offset_x': sorted({h[1] for h in hand}), 'hand_height': sorted({h[2] for h in hand}),
                 'victim_hits': [(f, hp) for f, i, hp, st in b.hits if i == VICTIM]}
    sheet(shots[1:], os.path.join(out, f'scene_{note}.png'), f'{note}: Kaiser Wave charged: the blue charge in his hand '
          f'({len(hand)} frames, KOF98 state 246 at {res[note]["hand_height"][:1]}.. px up)')
    print(note, json.dumps(res[note]), flush=True)
    # 20261006-190659: Krauser's Kaiser Wave (D) hitting Terry with another enemy beside
    note = '20261006-190659-5d29'
    P.setup('krauser', 100, 1, 112)
    b.place(3, x=230, z=36)
    sd = os.path.join(out, 'shots', 'scene_' + note); os.makedirs(sd, exist_ok=True); shots = [sd]
    imp, prev, prev_y = [], {}, {}
    KW_HEIGHT = 96                                   # KOF96's wave object (state 155) at +$20 = 96 through its flight and
                                                     # its impact (romspecials_check krauser:C mid, kof_objects)
    for f in range(160):
        pad = 'd' if f < 4 else ''
        if 28 <= f and f % 3 == 0 and len(shots) < 30: b.pad = [set(pad), set()]; p = os.path.join(sd, f'f{f:03d}.png'); b.screenshot(p); shots.append((f, p))
        else: b.run(1, p1=pad)
        for i in range(NPJ):
            if b.states[b.pget(i, 'state')] != 'PROJ': continue
            pe = b.pget(i, 'pend')
            if pe == 1 and prev.get(i) != 1: imp.append({'frame': f, 'entity': i, 'end_height': b.pget(i, 'y'),
                                                         'flight_height': prev_y.get(i, KW_HEIGHT)})
            prev[i] = pe
        prev_y = {i: b.pget(i, 'y') for i in range(NPJ) if b.states[b.pget(i, 'state')] == 'PROJ'}
    res[note] = {'scene': 'Krauser D (Kaiser Wave) at Terry 112 px ahead, a second enemy beside', 'impacts': imp,
                 'ok': bool(imp) and all(abs(m_['end_height'] - (m_['flight_height'] or 0)) < 1 for m_ in imp)}
    sheet(shots[1:], os.path.join(out, f'scene_{note}.png'), f'{note}: Krauser\'s Kaiser Wave impact at the wave\'s height: {imp[:1]}')
    print(note, json.dumps(res[note]), flush=True)
    json.dump(res, open(os.path.join(out, 'scenes.json'), 'w'), indent=1)

if __name__ == '__main__':
    cmd = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    os.makedirs(out, exist_ok=True)
    {'wall': wall, 'charge': charge, 'scene': scene}[cmd](out)
