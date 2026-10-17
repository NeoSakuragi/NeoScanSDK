#!/usr/bin/env python3
"""The three-stage campaign (Bruno 2026-10-17: three stages, Geese last, the Rugal finale, a bonus stop with the choice of
both games between each two stages, Final Fight's city map at every stage's start and clear, the test cheats, the next
unlock rung as silhouettes on the select), in our emulator (harness.py), the game's real paths. Was the two-stage proof
of 0.10.159 (its name kept: the gates and the docs call it).

    stages2_proof.py GAME_DIR OUT [--quick]
      run      ONE credit played through (coin, START, Terry; every wave cleared by poke, each boss KO'd by poke):
               stage 1 (the map over its fade-in: SLUM blinking; the boss = boss_order[0]; the clear's map: SLUM lit,
               PARK blinking, NEXT BONUS GAME) -> bonus stop 1 (the pick: both games offered; the posts picked and WON)
               -> stage 2 (its map: POLICE HQ blinking; camera 0; boss_order[1]; its clear's map) -> bonus stop 2 (the
               pick: the posts GREYED (won), the Ki training offered; passed) -> stage 3 (from stages[].start; GEESE;
               then the finale: RUGAL with the two greyed bosses, all three on screen; RUGAL down) -> the clear's map
               (all lit, ALL CLEAR) -> the ending                                                        -> run_*.png
      cheat    a new game: P1 holds DOWN + A + B + C + D cheats.stage_clear_hold ticks in stage 1's first wave: the
               stage's end sequence at once (STAGE CLEAR, the win pose, the map, the bonus next)           -> cheat_*.png
      select   a fresh save: the next rung (HAGGAR) as a silhouette, the cursor on it: LOCKED - BEAT THE GAME FIRST,
               A refused; the LADDER cheat (hold UP, then DOWN) once, twice: one rung each, saved; the POWER cheat
               (LEFT, then RIGHT): a new game's drive bar at its most chunks, the fury free              -> sel_*.png
      cont     stage 2 with the fury unlocked, 4 drive chunks and a full fury gauge: P1's last life lost, CONTINUE,
               coin + START: fury_lock, drive_chunks, his drive and fury gauge after it                  -> cont_*.png
      pile     the posts' pile: no two boxes overlapping, a trunk falls when its supports break, all broken -> pile_*.png
    OUT/sheet.png (every shot), OUT/maps.png (the map screens); one OK / FAIL line per check, exit 1 on any FAIL"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario, bonus_proof
from PIL import Image, ImageDraw

BN_PICK, BN_PLAY, BN_END = 1, 2, 3
BP_STAND = 2
TR_SIZE = 12                                             # main.c bn_tr[]: int16 x, h, vy; uint8 st, hp, img, thud, dirty (+ pad)
BT_GONE, BT_REST, BT_FALL = 0, 1, 2
MAP_START, MAP_CLEAR = 1, 2


class P(bonus_proof.Proof):
    def s16(self, n): return self.r(n, 2)
    def boss_name(self): return self.names[self.b.char_of(2)]
    def st(self, i): return self.b.states[self.b.fget(i, 'state')]

    def clear_waves(self, tag):
        """every wave cleared by poke (the enemies off), P1 walking right: until the boss phase"""
        b = self.b; shots = 0
        for _ in range(12000):
            if self.r('phase') == 2: break
            if self.r('phase') == 0 and self.r('in_ph') == 0:
                for i in range(2, 8):
                    if self.st(i) not in ('OFF', 'DEAD'): b.fset(i, 'state', b.states.index('OFF'))
            b.fset(0, 'hp', 60); b.run(1, p1='R')
            if self.r('phase') == 1 and shots < 1 and self.r('wave') == 2: self.shot(f'{tag}_scroll', f'{tag}: scrolling (cam {self.s16("cam_x")})'); shots += 1

    def boss_ko(self, tag, label):
        """the boss walks in (his drama played out with A), then KO'd by poke: his death sequence"""
        b = self.b
        for _ in range(1500):                            # (his drama: A skips its lines)
            if self.r('dr_on') == 0 and self.st(2) not in ('OFF',) and self.s16('cam_x') == self.s16('lock_x'): break
            b.fset(0, 'hp', 60); b.run(1, p1='a' if b.frame & 8 else '')
        b.run(90); self.shot(f'{tag}_boss', label + f' {self.boss_name().upper()}')
        name = self.boss_name()
        b.fset(2, 'hp', 0); b.fset(2, 'state', b.states.index('DEAD')); b.fset(2, 'state_t', 0)
        return name

    def map_shots(self, kind, tag, label):
        """the map up (map_on = kind): a shot in each blink phase; returns the ticks it stayed up"""
        b = self.b
        k = self.until(lambda: self.r('map_on') == kind, 3000)
        if k < 0: self.check(False, f'{tag}: the map ({"start" if kind == MAP_START else "clear"}) never came up'); return 0
        b.run(8); self.shot(f'{tag}_a', label + ' (blink 1)')
        b.run(6); self.shot(f'{tag}_b', label + ' (blink 2)')
        self.maps += [self.shots[-2], self.shots[-1]]
        n = 14 + self.until(lambda: self.r('map_on') != kind, 1200)
        return n

    def pick_and_play(self, want, tag, label):
        """the bonus stop: the pick screen (shot), the cursor to game `want` (an id), A; returns the offered game ids"""
        b = self.b; G = self.G['games']
        self.until(lambda: self.r('mode') == 6 and self.r('bonus_on') == BN_PICK, 2000)
        b.run(40)
        slots = [b.r(b.syms['bn_slot_game'] + k, 1) for k in range(3)]
        offered = [G[g]['id'] for g in slots if g != 0xFF]
        self.shot(f'{tag}_pick', f'{label}: offered {offered}')
        wi = [x['id'] for x in G].index(want)
        for _ in range(4):
            if self.r('bn_cur') == wi: break
            b.seq('4:R,20:-')
        b.seq('4:a,10:-')
        self.until(lambda: self.r('bonus_on') == BN_PLAY, 600)
        return offered

    def play_posts_live(self):
        """the posts game in play (as fpga_playthrough's bot): walk to the front trunk, A, A, A; its clock kept up"""
        b = self.b; t = 0
        while self.r('bonus_on') == BN_PLAY and t < 6000:
            if self.r('bn_clock', 2) < 600: b.w(b.syms['bn_clock'], 2, 99 * 60)
            keys = ''; stn = self.st(0)
            if self.r('bn_post') == BP_STAND and stn in ('IDLE', 'WALK', 'ATTACK'):
                px = self.s16('bn_px'); fx = b.fget(0, 'x'); right = px + 32 > fx
                gap = px - fx if right else fx - (px + 64)
                face = b.fget(0, 'facing'); face = face - 256 if face > 127 else face
                if stn != 'ATTACK' and gap > 12: keys = 'R' if right else 'L'
                elif stn != 'ATTACK' and (face > 0) != right: keys = 'R' if right else 'L'
                elif t & 7 == 0 and gap <= 12: keys = 'a'
            b.run(1, p1=keys); t += 1
        return self.r('bn_left')

    def play_ki_live(self):
        b = self.b; ki = next(x for x in self.G['games'] if x['kind'] == 'gauge')
        k = self.until(lambda: self.r('bn_power') >= ki['grades'][-1] + 2, 1200)
        b.run(1, p1='a')
        self.until(lambda: self.r('bonus_on') == BN_END, 900)
        return self.r('bn_grade')

    def end_bonus(self):
        """the result screens (the referee's speech: A) until the next stage begins"""
        b = self.b
        for _ in range(4000):
            if self.r('bonus_on') == 0 and self.r('mode') == 1: return True
            b.run(1, p1='a' if b.frame % 37 < 2 else '')
        return False

    def run_all(self, G):
        b = self.b; st = [s for s in G['stages'] if not s.get('off')]; bo = G['boss_order']['bosses']; M = G['map']
        stops = M['stops']
        b.core.retro_reset(); b.seq('600:-,4:o,100:-,4:s,100:-,4:a')
        # ---- stage 1
        n = self.map_shots(MAP_START, 'run_s1_map', 'stage 1 start: the map over the fade-in')
        self.check(self.r('camp') == 0 and self.r('in_ph') == 1 and abs(n - M['start_ticks']) <= 12,
                   f'stage 1: the map at its start, over the fade-in (IN_FADE), up {n} ticks (map.start_ticks {M["start_ticks"]})')
        self.check(self.r('map_reached') == 0 and self.r('map_cur') == 0, f'stage 1 start: nothing lit, SLUM blinking (reached {self.r("map_reached")}, current {self.r("map_cur")})')
        b.run(30); self.shot('run_s1_title', 'stage 1: after the map, the title, then the walk-in')
        self.until(lambda: self.r('in_ph') == 0, 900)
        self.clear_waves('run_s1')
        name = self.boss_ko('run_s1', 'stage 1 boss')
        self.check(name == bo[0].lower(), f'stage 1 boss: {name} (want {bo[0]})')
        n = self.map_shots(MAP_CLEAR, 'run_s1_clear', 'stage 1 clear: the map (SLUM lit, PARK next)')
        self.check(self.r('map_reached') == 1 and self.r('map_cur') == 1 and abs(n - M['clear_ticks']) <= 12,
                   f'stage 1 clear: SLUM lit, PARK blinking (reached {self.r("map_reached")}, current {self.r("map_cur")}), up {n} ticks')
        # ---- bonus stop 1
        off = self.pick_and_play('posts', 'run_b1', 'bonus stop 1')
        self.check(sorted(off) == sorted(x['id'] for x in self.G['games']), f'bonus stop 1: both games offered ({off})')
        left = self.play_posts_live()
        self.shot('run_b1_won', 'bonus 1: the posts won')
        self.check(left == 0 and self.r('fury_lock') == 0, f'bonus 1: the posts won (trunks left {left}, fury_lock {self.r("fury_lock")})')
        self.check(self.end_bonus(), 'bonus 1 -> stage 2')
        # ---- stage 2
        n = self.map_shots(MAP_START, 'run_s2_map', 'stage 2 start: SLUM + PARK lit, POLICE HQ blinking')
        self.check(self.r('camp') == 1 and self.r('map_reached') == 2 and self.r('map_cur') == 2, f'stage 2 start: the map (reached {self.r("map_reached")}, current {self.r("map_cur")})')
        self.until(lambda: self.r('in_ph') == 0, 900)
        b.run(20); self.shot('run_s2_start', f'stage 2 (background {st[1]["background"]}): cam {self.s16("cam_x")}')
        self.check(self.s16('cam_x') == st[1].get('start', 0), f'stage 2: the camera at {self.s16("cam_x")} (want {st[1].get("start", 0)})')
        self.clear_waves('run_s2')
        lock = self.s16('lock_x')
        name = self.boss_ko('run_s2', 'stage 2 boss')
        self.check(name == bo[1].lower() and lock == st[1]['boss']['lock'], f'stage 2 boss: {name} at the lock {lock} (want {bo[1]}, {st[1]["boss"]["lock"]})')
        self.map_shots(MAP_CLEAR, 'run_s2_clear', 'stage 2 clear: the map (FACTORY next)')
        self.check(self.r('map_reached') == 3 and self.r('map_cur') == 3, f'stage 2 clear: POLICE HQ lit, FACTORY blinking ({self.r("map_reached")}, {self.r("map_cur")})')
        # ---- bonus stop 2: the posts won = greyed
        off = self.pick_and_play('ki', 'run_b2', 'bonus stop 2 (the posts greyed: won)')
        self.check(off == ['ki'], f'bonus stop 2: only the game not won yet offered ({off}; the posts greyed)')
        g = self.play_ki_live(); b.run(60)
        self.shot('run_b2_ki', f'bonus 2: the Ki training, grade {g}')
        self.check(g == 5, f'bonus 2: the Ki training passed (grade {g})')
        self.check(self.end_bonus(), 'bonus 2 -> stage 3')
        # ---- stage 3: Geese, then the finale
        self.map_shots(MAP_START, 'run_s3_map', 'stage 3 start: GEESE TOWER blinking (FINALE)')
        self.check(self.r('camp') == 2 and self.r('map_reached') == 4 and self.r('map_cur') == 4, f'stage 3 start: the map ({self.r("map_reached")}, {self.r("map_cur")})')
        self.until(lambda: self.r('in_ph') == 0, 900)
        self.check(self.s16('cam_x') == st[2].get('start', 0), f'stage 3: the camera at {self.s16("cam_x")} (want {st[2].get("start", 0)})')
        self.clear_waves('run_s3')
        name = self.boss_ko('run_s3', 'stage 3 boss')
        self.check(name == bo[2].lower(), f'stage 3 boss: {name} (want {bo[2]})')
        fz = st[2]['boss']['finale']
        k = self.until(lambda: self.r('fin_st') == 2, 3000)
        self.check(k >= 0 and self.r('phase') == 2 and self.r('map_on') == 0, f'the finale after {bo[2]}: no stage clear (phase {self.r("phase")}), no map, {k} ticks')
        b.run(20); self.shot('run_fin_entry', f'the finale: {self.boss_name().upper()} enters (his drama)')
        for _ in range(1500):                            # (his drama: A)
            if self.r('dr_on') == 0: break
            b.fset(0, 'hp', 60); b.run(1, p1='a' if b.frame & 8 else '')
        for _ in range(600):                             # all three on the screen
            cam = self.s16('cam_x'); on = [i for i in (2, 3, 4) if self.st(i) not in ('OFF', 'DEAD') and cam < b.fget(i, 'x') < cam + 320]
            if len(on) == 3: break
            b.fset(0, 'hp', 60); b.run(1)
        names = [self.names[b.char_of(i)] for i in (2, 3, 4)]
        self.shot('run_fin_three', f'the finale: {", ".join(n.upper() for n in names)}')
        want = [fz['enemy'].lower()] + [next(e['base'] for e in G['enemies'] if e['name'] == m['enemy']) for m in fz['minions']]
        self.check(names == want and len(on) == 3, f'the finale: {names} on the screen together ({len(on)}; want {want})')
        b.run(120)
        b.fset(2, 'hp', 0); b.fset(2, 'state', b.states.index('DEAD')); b.fset(2, 'state_t', 0)
        b.run(60); self.shot('run_fin_ko', f'{fz["enemy"]} KO\'d: the others knocked down with him')
        n = self.map_shots(MAP_CLEAR, 'run_s3_clear', 'the game clear: every stop lit, ALL CLEAR')
        self.check(self.r('map_reached') == len(stops) and self.r('map_cur') == 0xFF, f'stage 3 clear: all lit ({self.r("map_reached")}), none blinking')
        k = self.until(lambda: self.r('mode') == 4, 3000)
        b.run(60); self.shot('run_ending', 'the ending')
        self.check(k >= 0, f'the ending after {fz["enemy"]} ({k} ticks after the map)')

    def cheat(self, G):
        b = self.b; hold = G['cheats']['stage_clear_hold']
        b.core.retro_reset(); b.seq('600:-,4:o,100:-,4:s,100:-,4:a,100:-')
        self.until(lambda: self.r('in_ph') == 0 and self.r('mode') == 1, 2000)
        b.run(60); self.shot('cheat_before', 'cheat: stage 1, wave 1 (enemies up)')
        b.run(hold - 1, p1='Dabcd')
        self.check(self.r('phase') < 3, f'cheat: not yet after {hold - 1} ticks (phase {self.r("phase")})')
        b.run(2, p1='Dabcd'); b.run(1)
        self.check(self.r('phase') >= 3, f'cheat: DOWN + A + B + C + D held {hold} ticks: the stage\'s end (phase {self.r("phase")})')
        b.run(40); self.shot('cheat_clear', 'cheat: STAGE CLEAR at once')
        self.map_shots(MAP_CLEAR, 'cheat_map', 'cheat: the clear\'s map')
        k = self.until(lambda: self.r('mode') == 6, 2000)
        b.run(30); self.shot('cheat_next', 'cheat: then the bonus stop, as a real clear')
        self.check(k >= 0, 'cheat: the bonus stop after it')

    def select(self, G):
        b = self.b; hold = G['cheats']['hold']; U = G['unlocks']
        b.core.retro_reset()
        scenario.setup(b, {'setup': {'mode': 'select'}})
        b.run(30)
        sc = [b.r(b.syms['slot_ch'] + i, 1) for i in range(self.r('sel_cnt'))]
        nm = [self.names[c] for c in sc]
        self.check(nm == U['starters'] + U['rungs'][0], f'select: the starters + the next rung as silhouettes: {nm}')
        self.shot('sel_before', 'select, a fresh save: HAGGAR a silhouette')
        b.sel_goto(sc[-1]); b.run(20)
        self.check(self.r('cursor') == len(sc) - 1, 'select: the cursor on the silhouette')
        self.shot('sel_locked', 'the cursor on it: LOCKED - BEAT THE GAME FIRST')
        b.seq('4:a,30:-')
        self.check(self.r('picked') == 0, 'select: A on the locked one: refused')
        r0 = b.r(b.syms['save'] + 9, 1)
        for k in (1, 2):
            b.run(hold + 4, p1='U'); b.run(hold + 4, p1='D'); b.run(40)
            sc = [b.r(b.syms['slot_ch'] + i, 1) for i in range(self.r('sel_cnt'))]
            r = b.r(b.syms['save'] + 9, 1)
            want = U['starters'] + [f for rg in U['rungs'][:r + 1] for f in rg]
            nxt = U['rungs'][r] if r < len(U['rungs']) else []
            b.sel_goto(sc[-1]); b.run(20)
            self.shot(f'sel_ladder{k}', f'LADDER x{k}: rungs {r}, next {"+".join(nxt) or "-"} grey')
            self.check(r == r0 + k and [self.names[c] for c in sc] == want,
                       f'LADDER cheat x{k}: save.rungs {r0} -> {r}; on the select {[self.names[c] for c in sc]} (the last {len(nxt)} silhouettes: {nxt})')
        b.run(hold + 4, p1='L'); b.run(hold + 4, p1='R'); b.run(20)
        self.check(b.r(b.syms['save'] + 10, 1) & 1, 'POWER cheat: save.cheat set')
        b.sel_goto(self.names.index('terry')); b.run(20)
        b.seq('4:a,300:-')
        self.until(lambda: self.r('mode') == 1 and self.r('in_ph') == 0, 2000); b.run(30)
        self.shot('sel_power_fight', f'POWER cheat: a new game, drive chunks {self.r("drive_chunks")}, fury lock {self.r("fury_lock")}')
        self.check(self.r('drive_chunks') == G['meter'].get('max_chunks', 4) and self.r('fury_lock') == 0,
                   f'POWER cheat: the bar at its most chunks ({self.r("drive_chunks")}), the fury free ({self.r("fury_lock")})')

    # ---- the continue and the pile (as 0.10.159's proof)
    def to_after_posts(self, unlocked=False):
        b = self.b
        posts = next(x for x in self.G['games'] if x['kind'] == 'break')
        self.setup(game=posts['id'], unlocked=unlocked)
        b.w(b.syms['bn_clock'], 2, 5)
        self.until(lambda: self.r('bonus_on') == 0 and self.r('mode') == 1, 2500)

    def cont(self):
        b = self.b
        self.to_after_posts(unlocked=True)
        self.until(lambda: self.r('in_ph') != 0, 60); self.until(lambda: self.r('in_ph') == 0, 900); b.run(30)
        b.w(b.syms['drive_chunks'], 1, 4); b.w(b.syms['lives'], 1, 0); b.fset(0, 'hp', 1)
        k = self.until(lambda: self.r('cont_t', 2) > 0, 4000)
        b.fset(0, 'drive', 240 * 4); b.fset(0, 'fgauge', 100); b.run(2)
        before = (self.r('fury_lock'), self.r('drive_chunks'), b.fget(0, 'drive'), b.fget(0, 'fgauge'))
        self.shot('cont_ask', 'P1 out: CONTINUE')
        self.check(k >= 0, f'continue: the count after the last life ({k} ticks)')
        b.seq('4:o,60:-,4:s,10:-')
        k = self.until(lambda: self.st(0) not in ('OFF', 'DEAD'), 300)
        b.run(120)
        after = (self.r('fury_lock'), self.r('drive_chunks'), b.fget(0, 'drive'), b.fget(0, 'fgauge'))
        self.shot('cont_back', f'continued: drive chunks {after[1]}, fury lock {after[0]}')
        self.check(k >= 0 and after[0] == 0 and after[1] == 4 and after[2] == 240 * 4 and after[3] == before[3],
                   f'continue: fury_lock / drive_chunks / drive / fury gauge {before} -> {after}')

    def trunks(self):
        b = self.b; base = b.syms['bn_tr']; out = []
        posts = next(x for x in self.G['games'] if x['kind'] == 'break'); pl = posts['pile']
        for k in range(len(pl['trunks'])):
            o = base + k * TR_SIZE
            s16 = lambda v: v - 65536 if v > 32767 else v
            out.append({'x': s16(b.r(o, 2)), 'h': s16(b.r(o + 2, 2)), 'st': b.r(o + 6, 1), 'reach': s16(b.r(b.syms['bn_reach'] + 2 * k, 2))})
        return out

    def boxes(self, tr, th):
        r = []
        for k, t in enumerate(tr):
            if t['st'] == BT_GONE: continue
            top = 224 - (t['h'] >> 4) - th
            r.append((k, t['x'] + 8, t['x'] + 56, top + 4 - t['reach'], top + th))
        return r

    def overlap(self, bx):
        return [(a[0], c[0]) for i, a in enumerate(bx) for c in bx[i + 1:] if a[1] < c[2] and c[1] < a[2] and a[3] < c[4] and c[3] < a[4]]

    def pile(self):
        b = self.b
        posts = next(x for x in self.G['games'] if x['kind'] == 'break'); pl = posts['pile']; th = pl['trunk_h']
        self.setup(game=posts['id']); b.run(40)
        self.shot('pile_start', 'the pile at its start')
        self.check(not self.overlap(self.boxes(self.trunks(), th)), 'pile: no two boxes overlapping at the start')
        run0 = b.run; worst = []; fell = [False]
        def run(*a, **k):
            r = run0(*a, **k)
            if self.r('bonus_on') == BN_PLAY:
                if self.r('bn_clock', 2) < 600: b.w(b.syms['bn_clock'], 2, 99 * 60)
                tr_ = self.trunks(); o = self.overlap(self.boxes(tr_, th))
                if o: worst.append(o)
                if not fell[0] and any(t['st'] == BT_FALL for t in tr_): fell[0] = True
            return r
        b.run = run
        lock0, t, left = self.play_posts('terry', 'a', limit=99 * 60)
        b.run = run0
        self.check(fell[0] and not worst and left == 0, f'pile: a trunk fell ({fell[0]}), no overlap in any tick ({len(worst)}), all broken ({left} left)')

    def sheet_of(self, shots, name):
        ims = [(Image.open(p).convert('RGB'), l) for p, l in shots]
        w, h = ims[0][0].size; cols = 4
        S = Image.new('RGB', (w * cols, (h + 14) * ((len(ims) + cols - 1) // cols)), 'white'); D = ImageDraw.Draw(S)
        for i, (im, l) in enumerate(ims):
            x, y = (i % cols) * w, (i // cols) * (h + 14); S.paste(im, (x, y + 14)); D.text((x + 2, y + 1), l[:52], fill='black')
        S.save(os.path.join(self.out, name))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(a) != 2: sys.exit(__doc__)
    game, out = a
    G = json.load(open(os.path.join(game, 'game.json')))
    p = P(game, out); p.maps = []
    p.run_all(G); p.cheat(G); p.select(G)
    if '--quick' not in sys.argv: p.cont(); p.pile()
    p.sheet_of(p.shots, 'sheet.png'); p.sheet_of(p.maps, 'maps.png')
    print('ALL OK' if not p.fails else f'{p.fails} FAIL'); sys.exit(1 if p.fails else 0)


if __name__ == '__main__':
    main()
