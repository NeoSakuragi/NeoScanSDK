#!/usr/bin/env python3
"""Rock's specials, supers and throw played in our emulator (cap_garou) -> /data/neogeo_dict/garou/rock_capture.json:
per move every frame from the one its first animation starts to the one he is back in neutral: his animation / step /
frame id, x (forward positive, from the start) and height, his velocity registers, and every object of his ($100600+
tasks with +$10 = his character and an animation: Reppuken's wave, Raging Storm's pillars ...) with its animation, step,
x / height from his start point. The export reads the JSON (no emulator in the build).

    python3 capture_garou.py            (far.state: P1 x 196, P2 x 444 idle: the moves whiff; the gauge poked full for
                                         the supers; close.state for the throw)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cap_garou import Garou, STA
from check_timeline import seq
import harness as HN

class Sounds:
    """the 68000's sound bytes to REG_SOUND ($320000 [meas]: $59F70 writes a prefix ($1C ...) then the code): words
    prefix << 8 | code, per frame"""
    def __init__(self, g):
        self.g = g; self.pending = None; self.frame_words = []
        g._tap = HN.TAP_CB(self.tap); g.core.retro_neoscan_m68k_write_tap(g._tap)
    def tap(self, a, v, size):
        if a not in (0x320000, 0x320001): return
        v &= 0xFF
        if self.pending is None and 0x10 <= v < 0x20: self.pending = v; return
        if self.pending is not None: self.frame_words.append(self.pending << 8 | v); self.pending = None
    def take(self):
        w, self.frame_words = self.frame_words, []; return w

OUT = '/data/neogeo_dict/garou/rock_capture.json'
GAUGE = 0x1004BE                                    # P1 +$BE: the power gauge (+9 a special [meas]); $80 = enough for a super
NEUTRAL = {0, 1, 2, 3, 4, 6, 7}
# input -> (state, script, gauge poke)
MOVES = {
    '236A': ('far', seq('236A'), 0), '236C': ('far', seq('236C'), 0),
    '28A': ('far', '45:D,4:Ua', 0), '28C': ('far', '45:D,4:Uc', 0),
    '214A': ('far', seq('214A'), 0), '214C': ('far', seq('214C'), 0),
    '214B': ('far', seq('214B'), 0), '214D': ('far', seq('214D'), 0),
    '236236A': ('far', seq('236236A'), 0x80), '236236C': ('far', seq('236236C'), 0x80),
    '236236B': ('far', seq('236236B'), 0x80), '236236D': ('far', seq('236236D'), 0x80),
    'AB': ('far', seq('AB'), 0),
}
# the normals and the jump: only their sounds are read (voices.py garou: their animation steps)
NORMALS = {'5A': ('far', seq('A'), 0), '5B': ('far', seq('B'), 0), '5C': ('far', seq('C'), 0), '5D': ('far', seq('D'), 0),
           'c5C': ('close', seq('C'), 0), 'c5D': ('close', seq('D'), 0), '2A': ('far', seq('2A'), 0), '2B': ('far', seq('2B'), 0),
           '2C': ('far', seq('2C'), 0), '2D': ('far', seq('2D'), 0), '6A': ('far', seq('6A'), 0), '6B': ('far', seq('6B'), 0),
           'jC': ('far', '6:U,4:Uc,50:', 0), 'jD': ('far', '6:U,4:Ud,50:', 0)}

def capture_win(g):
    """P2's life poked to 1 in close.state, a stand B: the KO, then 420 frames: Rock's win animation's sounds"""
    g.load(open(f'{STA}/close.state', 'rb').read()); g.w(0x10058E, 1, 1)
    rows = []
    for k in ['b'] * 4 + [''] * 420:
        g.pad = [set(k), set()]; g.core.retro_run(); g.frame += 1
        P = g.obj(0x100400); snd = g.snd.take()
        if P['anim'] == 0x206: rows.append({'anim': P['anim'], 'step': P['step'], 'snd': snd})
    g.pad = [set(), set()]
    return rows

def objects(g, x0, me, before=()):
    """his effect tasks ($100600-$103FFF, unnamed, +$10 = his character) with an animation, except the ones already
    there before the move (before: {(task, anim)}: the stage's / the round's own objects of that character number)"""
    out = []
    for t in range(0x100600, 0x104000, 0x100):
        o = t - 0x100000
        if g.r(t + 0x10) != me or g.r(t + 0x60) == 0 or any(g.ram[o + 0x18:o + 0x1C]): continue
        if (t, g.r(t + 0x60)) in before: continue
        out.append({'task': t, 'anim': g.r(t + 0x60), 'step': g.r(t + 0x66, 1), 'fid': g.r(t + 0x5E) & 0x7FF,
                    'x': g.rs(t + 0x20, 4) / 65536 - x0, 'h': g.rs(t + 0x28, 4) / 65536, 'vx': g.rs(t + 0x34, 4) / 65536,
                    'f6a': g.r(t + 0x6A, 1), 'face': g.r(t + 0x58, 1), 'ended': g.r(t + 0x7E, 1) >> 7})
    return out

def capture(g, inp):
    st, s, poke = {**MOVES, **NORMALS}[inp]
    g.load(open(f'{STA}/{st}.state', 'rb').read())
    if poke: g.w(GAUGE, 1, poke)
    x0 = prev = g.rows_now()['P1']['x']
    before = {(t, g.r(t + 0x60)) for t in range(0x100600, 0x104000, 0x100)}
    rows, started = [], False
    for part in ('1:,' + s + ',240:').split(','):
        if not part: continue
        n, k = part.split(':')
        for _ in range(int(n)):
            g.pad = [set(k), set()]; g.core.retro_run(); g.frame += 1
            snd = g.snd.take()
            P = g.obj(0x100400); P2 = g.obj(0x100500)
            if not started and P['anim'] not in NEUTRAL: started = True; x0 = prev
            prev = P['x']
            if not started: continue
            if P['anim'] in (0, 1) and len(rows) > 3: break
            rows.append({'anim': P['anim'], 'step': P['step'], 'fid': P['fid'], 'x': P['x'] - x0, 'h': P['h'],
                         'vx': P['vx'], 'vh': P['vh'], 'f6a': P['f6a'], 'p2': P2['anim'], 'objs': objects(g, x0, 1, before), 'snd': snd})
        else: continue
        break
    g.pad = [set(), set()]
    return rows

def capture_throw(g):
    """close + forward + C from close.state (12 frames of walking first: within his throw range): both fighters per frame
    from the thrower's first throw animation until the victim stands again"""
    g.load(open(f'{STA}/close.state', 'rb').read())
    rows, started = [], False
    for k in ['R'] * 12 + ['Rc'] * 4 + [''] * 220:
        g.pad = [set(k), set()]; g.core.retro_run(); g.frame += 1
        snd = g.snd.take()
        P = g.obj(0x100400); V = g.obj(0x100500)
        if not started and P['anim'] == THROW_ANIM: started = True; x0 = P['x']
        if not started: continue
        if V['anim'] == 0 and P['anim'] in (0, 1): break
        rows.append({'anim': P['anim'], 'step': P['step'], 'fid': P['fid'], 'x': P['x'] - x0, 'h': P['h'], 'snd': snd,
                     'v': {'anim': V['anim'], 'step': V['step'], 'fid': V['fid'], 'x': V['x'] - x0, 'h': V['h'],
                           'face': V['face'], 'life': g.r(0x10058E, 1)}})
    g.pad = [set(), set()]
    return rows
THROW_ANIM = 0x51

def main():
    g = Garou(); g.snd = Sounds(g); out = {}
    out['throw'] = capture_throw(g)
    out['win'] = capture_win(g)
    out['normals'] = {k: [{'anim': r['anim'], 'step': r['step'], 'snd': r['snd']} for r in capture(g, k)] for k in NORMALS}
    print('throw', len(out['throw']), [f'{a:x}' for a in dict.fromkeys(r['anim'] for r in out['throw'])],
          [f"{a:x}" for a in dict.fromkeys(r['v']['anim'] for r in out['throw'])])
    for inp in MOVES:
        out[inp] = capture(g, inp)
        r = out[inp]
        print(inp, len(r), 'frames, anims', [f'{a:x}' for a in dict.fromkeys(x['anim'] for x in r)], 'dx', round(r[-1]['x'], 1),
              'maxh', round(max(x['h'] for x in r), 1), 'objs', sorted({f"{o['anim']:x}" for x in r for o in x['objs']}),
              'P2', sorted({f"{x['p2']:x}" for x in r}))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w'))

if __name__ == '__main__': main()
