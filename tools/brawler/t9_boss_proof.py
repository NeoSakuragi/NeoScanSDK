#!/usr/bin/env python3
"""T9 proof (Bruno 2026-10-15, tougher bosses): each beta boss alone against P1 (the boss-only scenario: scenarios.json
"boss-mrbig" / "boss-krauser" / "boss-geese" / "boss-rugal", campaign stage k from its boss, difficulty LEVEL-4 = the
arcade's default soft DIP), in our emulator's core (harness.py), P1 driven by a scripted "decent player" bot.

    python3 t9_boss_proof.py fight BOSS [--rom R] [--game G] [--seed N] [--frames F] [--out DIR] [--sheet]
        one fight: the boss layer's event log (ai.c ai_blog: strings in order, guards, counters, the red period, furies),
        the engine's counts (fighter.c stat_blocks / stat_gbreaks / stat_counters / stat_immune), the result; --sheet: a
        contact sheet of its key moments
    python3 t9_boss_proof.py winrate [--rom R] [--game G] [--n N] [--out FILE]
        N fights a boss (seeds 0..N-1): the bot's wins / the boss's life left / P1's, per boss
    python3 t9_boss_proof.py all [--out DIR]          every boss: a fight with its sheet + the log checks

The bot ("decent player"): lines up on the boss's depth line, keeps out of his reach while he winds up, closes in and
plays its chain (A A A A, the forward finisher every other time), walks into him for a grab now and then (then knees and
a throw), answers an attack at close range with its invincible C special (Terry's Rising Tackle) when it has the drive,
and plays its fury when the gauge is ready. A fight: P1 one life (his life bar), the boss's full life; won = the boss
down before P1, else lost (or a draw at --frames)."""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H
import scenario as SC

GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
BOSSES = {'mrbig': 0, 'krauser': 1, 'geese': 2, 'rugal': 3}            # boss -> campaign stage
BE = {1: 'COMBO', 2: 'END', 3: 'GUARD', 4: 'RED', 5: 'SUPER', 6: 'COUNTER', 7: 'RUN'}
RECIPE = lambda st, gap=110: {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': st, 'wave': 99, 'wait': 205,
                                         'alone': True, 'gap': gap, 'lives': 1}}


_B = None
def brawler(rom, game):                                                # (one core a process: the harness's rule)
    global _B
    if _B is None:
        H.OPTIONS.update(SC.SYSTEMS['mvs-mvs'])
        _B = H.Brawler(rom=rom, game=game); _B.game = game
    _B.hits = []
    return _B


class Fight:
    def __init__(self, rom, game, stage, seed=0):
        self.b = b = brawler(rom, game)
        SC.setup(b, RECIPE(stage))
        self.f0 = b.frame
        b.run(seed * 7)                                                # (a seed: the fight starts that many frames later)
        self.syms = b.syms
        self.ev, self.seen = [], b.r(self.syms['ai_blog_n'], 1) if 'ai_blog_n' in self.syms else 0
        self.endless = False; self.deaths = 0; self.dead = False
        self.t = 0; self.cd = 0; self.follow = 0; self.plan = 0; self.walkin = 0; self.held = 0; self.grabs = 0
        self.combos = json.load(open(os.path.join(game, 'game.json')))
        self.names = None

    def stat(self, n): return self.b.r(self.syms[n], 2) if n in self.syms else None

    def poll(self):
        """the new entries of ai_blog"""
        if 'ai_blog_n' not in self.syms: return []
        n = self.b.r(self.syms['ai_blog_n'], 1); out = []
        while self.seen != n:
            a = self.syms['ai_blog'] + (self.seen & 31) * 6
            e = dict(kind=BE.get(self.b.r(a, 1), self.b.r(a, 1)), a=self.b.r(a + 1, 1), b=self.b.r(a + 2, 1), c=self.b.r(a + 3, 1),
                     t=self.b.r(a + 4, 2), frame=self.b.frame - self.f0)
            out.append(e); self.seen = (self.seen + 1) & 0xFF
        self.ev += out
        return out

    def grab_keys(self):
        """the grab test's keys: on his line, walk into him; holding, a throw at once"""
        b = self.b; self.t += 1
        st = b.states[b.fget(0, 'state')]
        dx, dz = b.fget(2, 'x') - b.fget(0, 'x'), b.fget(2, 'z') - b.fget(0, 'z')
        fwd = 'R' if dx > 0 else 'L'
        if st == 'GRAB':
            if not self.held: self.held = 1; self.grabs += 1
            return fwd + 'a' if self.t % 8 == 0 else ''
        self.held = 0
        return ('D' if dz > 2 else 'U' if dz < -2 else '') + fwd

    def keys(self):
        """the decent player's keys this frame"""
        b = self.b; self.t += 1
        st = b.states[b.fget(0, 'state')]; bs = b.states[b.fget(2, 'state')]
        px, pz, bx, bz = b.fget(0, 'x'), b.fget(0, 'z'), b.fget(2, 'x'), b.fget(2, 'z')
        dx, dz = bx - px, bz - pz; adx, adz = abs(dx), abs(dz)
        fwd = 'R' if dx > 0 else 'L'; back = 'L' if dx > 0 else 'R'
        if self.cd: self.cd -= 1
        if st == 'GRAB':                                               # knees, knees, then forward + A: the throw
            return ('a' if b.fget(0, 'grab_hits') < 2 else fwd + 'a') if self.t % 12 == 0 else ''
        if st in ('ATTACK', 'AIR ATK', 'AIR_ATTACK'):                  # the chain: A on every hit, the finisher forward
            if self.follow and b.fget(0, 'landed') and self.t % 3 == 0:
                self.follow -= 1
                return (fwd + 'a') if self.follow == 0 and self.plan & 1 else 'a'
            return ''
        if st not in ('IDLE', 'WALK', 'RUN'): return ''
        threat = bs in ('ATTACK', 'SPECIAL', 'AIR_ATTACK', 'AIR ATK') and adx < 70 and adz < 14
        if threat and b.fget(0, 'drive') >= 240 and not self.cd and self.t % 2 == 0:   # an attack close: the reversal
            self.cd = 50; return 'Dc'
        if b.fget(0, 'fgauge') >= 100 and adx < 90 and adz < 10 and not self.cd: self.cd = 60; return 'd'
        z = 'D' if dz > 3 else 'U' if dz < -3 else ''
        if self.walkin:                                                # a grab: walking into him
            self.walkin -= 1
            if bs in ('IDLE', 'WALK', 'GUARD', 'HITSTUN'): return z + fwd
            self.walkin = 0
        if bs in ('DOWN', 'GETUP', 'KNOCKDN', 'KNOCKDOWN'): return z + (back if adx < 60 else '')   # (wait for him to stand)
        if adx > 46: return z + fwd
        if adx < 20: return z + back
        if adz > 6: return z
        if not self.cd:
            self.plan += 1
            if self.plan % 4 == 0: self.cd = 30; self.walkin = 24; return fwd   # walk in: a grab
            self.cd = 34; self.follow = 3; return 'a'
        return z

    def run(self, frames, each=None, keys=None):
        b = self.b; res = None
        for f in range(frames):
            b.run(1, p1=(keys or self.keys)())
            new = self.poll()
            if each: each(self, new)
            if b.fget(2, 'hp') <= 0: res = 'won'; break
            if self.endless:                                           # (the proof's long fight: P1's lives kept, his deaths
                if b.states[b.fget(0, 'state')] == 'DEAD' and not self.dead: self.deaths += 1   # counted)
                self.dead = b.states[b.fget(0, 'state')] == 'DEAD'
                b.w(self.syms['lives'], 1, 3)
            elif b.fget(0, 'hp') <= 0 or b.states[b.fget(0, 'state')] == 'DEAD': res = 'lost'; break
        return {'result': res or 'draw', 'frames': f + 1, 'boss_hp': b.fget(2, 'hp'), 'boss_max': b.fget(2, 'hp_max'),
                'p1_hp': b.fget(0, 'hp'), 'blocks': self.stat('stat_blocks'), 'guard_breaks': self.stat('stat_gbreaks'),
                'counters': self.stat('stat_counters'), 'immune': self.stat('stat_immune'), 'p1_deaths': self.deaths, 'events': self.ev}


def combos_of(game, boss):
    g = json.load(open(os.path.join(game, 'game.json')))
    n = {'mrbig': 'MR_BIG', 'krauser': 'KRAUSER', 'geese': 'GEESE', 'rugal': 'RUGAL'}[boss]
    e = next(x for x in g['enemies'] if x['name'] == n)
    return (e.get('boss_ai') or {}).get('combos', [])


def log_text(boss, r, combos):
    """the fight log: one line an event, then the checks"""
    out = [f'{boss}: {r["result"]} in {r["frames"]} frames; boss life {r["boss_hp"]}/{r["boss_max"]}, P1 {r["p1_hp"]}/60, '
           f'P1 lives lost {r.get("p1_deaths", 0)}; '
           f'blocked {r["blocks"]}, guard breaks {r["guard_breaks"]}, counter-grabs {r["counters"]}, grabs refused {r["immune"]}']
    order = []
    for e in r['events']:
        k = e['kind']
        if k == 'COMBO': order.append(e['a']); what = f'string {e["a"]} "{combos[e["a"]] if e["a"] < len(combos) else "?"}"'
        elif k == 'END': what = f'  its end: {e["b"]} presses, last move connected {bool(e["c"])}'
        elif k == 'GUARD': what = 'GUARD (his attack starting)'
        elif k == 'RED': what = f'RED PERIOD (life {e["a"]})'
        elif k == 'SUPER': what = ('MAX FURY' if e['a'] else 'FURY') + f' (life {e["b"]})'
        elif k == 'COUNTER': what = 'COUNTER-GRAB: his throw'
        elif k == 'RUN': what = f'run in from {e["a"]} px'
        else: what = str(e)
        out.append(f'  frame {e["frame"]:5d}  {what}')
    # the variety rule (ai.c combo_pick): a string starts only when it is not used yet in this cycle; the cycle starts again
    # (the last one excluded) once every usable string was played (the D strings are usable in the red period only)
    rep, mask, last, red = 0, set(), None, False
    for e in r['events']:
        if e['kind'] == 'RED': red = True
        if e['kind'] != 'COMBO': continue
        i = e['a']
        usable = {j for j, c in enumerate(combos) if red or 'D' not in c.split()}
        if not usable - mask: mask = {last} if last is not None else set()
        if not usable - mask: mask = set()
        if i in mask: rep += 1
        mask.add(i); last = i
    out.append(f'  strings in order: {order}; repeats before the cycle was complete: {rep}')
    return '\n'.join(out), rep


# the contact sheet's moments: (event, frames after it, label); blocks / counter-grabs / refused grabs from the engine's counts
SHOTS = {'GUARD': [(6, 'guard')], 'COMBO': [(10, 'string')], 'RED': [(0, 'red period'), (2, 'red period')],
         'SUPER': [(14, 'fury'), (44, 'fury')], 'COUNTER': [(12, 'his throw')]}
STATS = {'stat_blocks': (2, 'blocked: guard spark'), 'stat_counters': (1, 'counter-grab'), 'stat_immune': (0, 'grab refused'),
         'stat_gbreaks': (2, 'guard broken')}


def frame_png(b):
    from PIL import Image
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def sheet(shots, path, title):
    from PIL import Image, ImageDraw
    if not shots: return
    w, h = shots[0][1].size; cols = 4; rows = (len(shots) + cols - 1) // cols
    im = Image.new('RGB', (w * cols, (h + 14) * rows + 16), 'white'); d = ImageDraw.Draw(im)
    d.text((4, 2), title, fill='black')
    for i, (lab, pic) in enumerate(shots):
        x, y = i % cols * w, 16 + i // cols * (h + 14)
        im.paste(pic, (x, y + 14)); d.text((x + 3, y + 1), lab, fill='black'); d.rectangle([x, y + 14, x + w - 1, y + 14 + h - 1], outline='black')
    im.save(path)


def fight_main(a):
    st = BOSSES[a.boss]
    F = Fight(a.rom, a.game, st, a.seed); F.endless = a.endless
    shots, want, last = [], [], {k: F.stat(k) or 0 for k in STATS}
    if a.sheet: F.b._want_video = True
    cnt = lambda lab: sum(lab in x[1] for x in want) + sum(lab in x[0] for x in shots)
    def each(f, new):
        if not a.sheet: return
        t = f.b.frame - f.f0
        for e in new:
            for dt, lab in SHOTS.get(e['kind'], []):
                n = cnt(lab)
                if n < (6 if lab == 'string' else 2): want.append((t + dt, f'{lab} {e["a"] if e["kind"] == "COMBO" else ""}'.strip()))
        for k, (dt, lab) in STATS.items():
            v = f.stat(k) or 0
            if v != last[k] and cnt(lab) < 3: want.append((t + dt, lab))
            last[k] = v
        for x in [x for x in want if x[0] <= t]:
            want.remove(x)
            if len(shots) < 32: shots.append((f'+{t} {x[1]}', frame_png(f.b)))
    r = F.run(a.frames, each)
    combos = combos_of(a.game, a.boss)
    txt, rep = log_text(a.boss, r, combos)
    print(txt)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        json.dump(r, open(os.path.join(a.out, f'{a.boss}_fight.json'), 'w'), indent=1)
        open(os.path.join(a.out, f'{a.boss}_fight.txt'), 'w').write(txt + '\n')
        if a.sheet:
            for i in range(0, len(shots), 16):
                sheet(shots[i:i + 16], os.path.join(a.out, f'{a.boss}_sheet{i // 16 + 1}.png'), f'T9 {a.boss}: seed {a.seed}, LEVEL-4, P1 Terry (bot)')
    return r, rep


def grabs_main(a):
    """P1 walks into the boss again and again (every grab: a throw at once): his grab responses counted"""
    out = {}
    for boss, st in BOSSES.items():
        if a.boss and boss != a.boss: continue
        F = Fight(a.rom, a.game, st, a.seed)
        r = F.run(a.frames, keys=F.grab_keys)
        ev = [e for e in r['events'] if e['kind'] == 'COUNTER']
        out[boss] = {'P1 grabs that held': F.grabs, 'refused (immune)': r['immune'], 'reversed (counter-grabs)': r['counters'],
                     'his counter throws': len(ev), 'frames': r['frames'], 'result': r['result']}
        print(boss, out[boss], flush=True)
    if a.out: json.dump(out, open(a.out, 'w'), indent=1)


def winrate_main(a):
    out = {}
    for boss, st in BOSSES.items():
        if a.boss and boss != a.boss: continue
        rs = []
        for s in range(a.n):
            F = Fight(a.rom, a.game, st, s)
            r = F.run(a.frames); r.pop('events')
            rs.append(r); print(boss, s, r, flush=True)
        out[boss] = {'wins': sum(r['result'] == 'won' for r in rs), 'n': len(rs),
                     'boss_hp_left': sum(r['boss_hp'] for r in rs) / len(rs), 'p1_hp_left': sum(r['p1_hp'] for r in rs) / len(rs),
                     'frames': sum(r['frames'] for r in rs) / len(rs), 'fights': rs}
        print(boss, {k: v for k, v in out[boss].items() if k != 'fights'}, flush=True)
    if a.out: json.dump(out, open(a.out, 'w'), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('fight', 'winrate', 'grabs'))
    ap.add_argument('boss', nargs='?', default=None)
    ap.add_argument('--rom'); ap.add_argument('--game', default=GAME)
    ap.add_argument('--seed', type=int, default=0); ap.add_argument('--frames', type=int, default=6000)
    ap.add_argument('--n', type=int, default=4); ap.add_argument('--out'); ap.add_argument('--sheet', action='store_true')
    ap.add_argument('--endless', action='store_true', help='fight: P1 keeps his lives (his deaths counted) until the boss is down')
    a = ap.parse_args()
    a.rom = a.rom or os.path.join(a.game, 'brawler.neo')
    if a.cmd == 'fight': fight_main(a)
    elif a.cmd == 'grabs': grabs_main(a)
    else: winrate_main(a)


if __name__ == '__main__':
    main()
