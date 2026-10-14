#!/usr/bin/env python3
"""The bonus stages' proof (TODO T7; main.c "bonus stages", game.json "bonus"), in our emulator's core (harness.py),
every run from scenario.py's mode "bonus" (lab req 6: a new game, then the bonus after stage `after`):

    bonus_proof.py GAME_DIR OUT [--sweep]
      pick    AOF2's BONUS GAME screen, the select (cursor right, an empty slot skipped, the clock), the
              title card, then the cursor's game                                                       -> intro, pick*, card.png
      grades  the Ki training pressed at a power of each grade (0-5): grade, drive chunks after          -> tree_g*.png
      win     the posts with Terry: D at each post until all are broken: unlocked, the result         -> posts_win*.png
      fail    the posts with A only (shakes, the lesson) to the clock's end: TIME OVER, still locked   -> posts_fail*.png
      lock    the next stage after each (stage 2): D with the gauge and drive full: no fury while locked,
              the fury after the win                                                                    -> d_locked.png, d_unlocked.png
      --sweep every roster fighter: the posts game played the same way, posts broken / ticks used (OUT/sweep.json)
    a contact sheet OUT/sheet.png; prints one OK / FAIL line per check, exit 1 on any FAIL"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
from PIL import Image, ImageDraw

BN = {'off': 0, 'pick': 1, 'play': 2, 'end': 3, 'intro': 4, 'card': 5}
BP_STAND = 2


class Proof:
    def __init__(self, game, out):
        self.game, self.out = game, out; os.makedirs(out, exist_ok=True)
        self.b = H.Brawler(game=game); self.b.game = game
        self.names = scenario.roster(game); self.fails = 0; self.shots = []
        self.G = json.load(open(os.path.join(game, 'game.json')))['bonus']
        import re
        self.mus = {n: int(v, 16) for n, v in re.findall(r'#define MUS_(\w+) +0x([0-9A-F]+)', open(os.path.join(game, 'build', 'snd', 'songs.h')).read())}

    def r(self, n, size=1):
        v = self.b.r(self.b.syms[n], size); return v - 65536 if size == 2 and v > 32767 else v

    def setup(self, fighter='terry', game='pick', unlocked=False, after=1):
        scenario.setup(self.b, {'setup': {'mode': 'bonus', 'fighter': fighter, 'game': game, 'unlocked': unlocked, 'after': after}})

    def shot(self, name, label):
        p = os.path.join(self.out, name + '.png'); self.b.screenshot(p); self.shots.append((p, label))

    def check(self, ok, what):
        print(('OK  ' if ok else 'FAIL') + ' ' + what, flush=True); self.fails += not ok

    def until(self, cond, n, keys=''):
        for k in range(n):
            if cond(): return k
            self.b.run(1, p1=keys)
        return -1

    # ---- the pick screen
    def pick(self):
        """AOF2's own screens (notes 20261014-085447 / -085507-5d29): BONUS GAME, SELECT BONUS GAME (a slot without a game
        greyed and skipped), the title card, then the game"""
        it, ct = self.G.get('intro', {}).get('ticks', 122), self.G.get('card', {}).get('ticks', 186)
        self.setup(game='pick'); self.b.run(30)
        self.check(self.r('mode') == 6 and self.r('bonus_on') == BN['intro'], 'pick: AOF2\'s BONUS GAME screen first (mode 6)')
        self.shot('intro', 'BONUS GAME')
        last = [0]; k = self.until(lambda: last.__setitem__(0, self.r('bn_t', 2)) if self.r('bonus_on') == BN['intro'] else True, 300)
        self.check(k >= 0 and self.r('bonus_on') == BN['pick'] and last[0] in (it - 1, it), f'pick: the select after the BONUS GAME screen (its clock at {last[0]}, game.json intro.ticks {it})')
        self.b.run(200); self.shot('pick', 'SELECT BONUS GAME (the cursor\'s message)')
        slots = sorted(x['slot'] for x in self.G['games'])
        self.check(self.r('bn_slot') == slots[0] and self.r('bn_cur') == 0, f'pick: the cursor on the first game\'s slot {slots[0]}')
        self.b.seq('4:R,30:-')
        self.check(self.r('bn_cur') == 1 and self.r('bn_slot') == slots[1], f'pick: the stick moves the cursor right, to slot {self.r("bn_slot")} (want {slots[1]}: an empty slot skipped)')
        self.shot('pick_right', 'cursor right')
        self.b.seq('4:R,30:-')
        self.check(self.r('bn_cur') == 1, 'pick: no slot right of the last game')
        k = self.until(lambda: self.r('bonus_on') == BN['card'], self.G['pick']['seconds'] * 60 + 200)
        self.check(k >= 0, f'pick: the clock ran out -> the title card after {k} more ticks')
        self.b.run(60); self.shot('card', 'the title card')
        last = [0]; k = self.until(lambda: last.__setitem__(0, self.r('bn_t', 2)) if self.r('bonus_on') == BN['card'] else True, ct + 10)
        self.check(k >= 0 and self.r('bonus_on') == BN['play'] and last[0] in (ct - 1, ct) and self.r('bn_game') == 1, f'pick: the card (its clock at {last[0]}, card.ticks {ct}) -> the cursor\'s game ({self.G["games"][1]["id"]})')

    # ---- the Ki training: one press per grade
    def grades(self):
        ki = next(x for x in self.G['games'] if x['kind'] == 'gauge'); kk = self.G['games'].index(ki) + 1
        gr = [0] + ki['grades']
        for g in range(6):
            lo = gr[g]; hi = gr[g + 1] if g < 5 else 128
            want = (lo + hi) // 2
            self.setup(game=ki['id']); self.b.run(40)
            c0 = self.r('drive_chunks')
            k = self.until(lambda: abs(self.r('bn_power') - want) <= ki['step'] and lo <= self.r('bn_power') + ki['step'] < hi, 400)
            self.b.run(1, p1='a'); self.b.run(30)
            if g in (0, 5): self.shot(f'tree_g{g}_hit', f'tree grade {g}: the blow')
            win = g >= ki.get('win_grade', 5)
            if win:                                 # (AOF2's top grade: the tree breaks, note 20261014-133606-5d29)
                self.b.run(40); self.shot(f'tree_g{g}_fall', f'tree grade {g}: the top falling')
                self.b.run(36); self.shot(f'tree_g{g}_crown', f'tree grade {g}: the crown landed')
            t = self.until(lambda: self.r('bonus_on') == BN['end'], 300); self.b.run(2)
            got, c1 = self.r('bn_grade'), self.r('drive_chunks')
            self.shot(f'tree_g{g}', f'tree grade {g}: result')
            add = min(ki['chunks'][g], 4 - c0)
            self.check(k >= 0 and got == g and c1 == c0 + add, f'tree: pressed at power ~{want}: grade {got} (want {g}), drive chunks {c0} -> {c1} (want +{add})')
            song = self.r('snd_song'); want_s = self.mus['BONUS_WIN' if win else 'BONUS_OVER']
            self.check(t >= 0 and song == want_s and (self.r('bn_fall_t', 2) > 0) == win,
                       f"tree grade {g}: {'passed' if win else 'failed'} as AOF2: song ${song:02X} (want ${want_s:02X} {'won' if win else 'failed'}), the tree {'falls' if self.r('bn_fall_t', 2) else 'stands'}")
        # the bar after the reward, in the next stage
        self.b.run(400)
        self.check(self.r('bonus_on') == BN['off'] and self.r('mode') == 1 and self.r('camp') == 1, 'tree: the next stage (stage 2) after the result')
        self.b.run(60); self.shot('tree_stage2_bar', 'stage 2: the 4-chunk drive bar')
        self.check(self.r('drive_chunks') == 4, f'tree: the bar keeps {self.r("drive_chunks")} chunks in stage 2 (want 4: 2 + the top grade\'s 2)')

    # ---- the posts: played with D (win) or A only (fail)
    def play_posts(self, fighter, use_d, shots=False, limit=None):
        posts = next(x for x in self.G['games'] if x['kind'] == 'break'); pk = self.G['games'].index(posts) + 1
        self.setup(fighter=fighter, game=posts['id'])
        lock0 = self.r('bn_lock0')                  # (the lock as the game came in: lifted while it plays)
        t = 0; shot_hit = shot_split = shot_lesson = False; px = 241
        limit = limit or (posts['seconds'] * 60 + 400)
        while self.r('bonus_on') == BN['play'] and t < limit:
            st = self.b.states[self.b.fget(0, 'state')]; fx = self.b.fget(0, 'x'); post = self.r('bn_post')
            keys = ''
            if post == BP_STAND and st in ('IDLE', 'WALK'):
                px = self.r('bn_px', 2); right = px > 160          # (the post: right, or left after a rush past it)
                gap = px - fx if right else fx - (px + 64)
                face = self.b.fget(0, 'facing'); face = face - 256 if face > 127 else face
                if gap > (36 if use_d else 50): keys = 'R' if right else 'L'
                elif (face > 0) != right: keys = 'R' if right else 'L'   # (turned to it first)
                elif t & 15 == 0: keys = 'd' if use_d else 'a'
            self.b.run(1, p1=keys); t += 1
            if shots and t == 30: self.shot(f'posts_{"win" if use_d else "fail"}_lesson', 'posts: the lesson box')
            if shots and use_d and not shot_hit and self.r('bn_post') == 3: self.b.run(3); self.shot('posts_win_hit', 'the fury burns the post'); shot_hit = True
            if shots and use_d and not shot_split and self.r('bn_split') and shot_hit: self.b.run(10); self.shot('posts_win_split', 'its splinters'); shot_split = True
            if shots and not use_d and not shot_lesson and self.r('bn_thud') and t > 200: self.shot('posts_fail_thud', 'a normal only shakes it'); shot_lesson = True
        return lock0, t, self.r('bn_left')

    def posts(self):
        posts = next(x for x in self.G['games'] if x['kind'] == 'break')
        lock0, t, left = self.play_posts('terry', True, shots=True)
        self.b.run(20); self.shot('posts_win', 'posts won: the result')
        self.check(lock0 == 1 and left == 0 and self.r('fury_lock') == 0 and self.r('bonus_on') == BN['end'],
                   f'posts win (terry, D): locked before ({lock0}), {posts["count"] - left} / {posts["count"]} broken in {t} ticks, unlocked after ({self.r("fury_lock") == 0})')
        self.check(self.r('snd_song') == self.mus['BONUS_WIN'], f"posts win: AOF2's won song (${self.r('snd_song'):02X}, want ${self.mus['BONUS_WIN']:02X})")
        self.lock_check('d_unlocked', want_fury=True)
        lock0, t, left = self.play_posts('terry', False, shots=True)
        self.b.run(20); self.shot('posts_fail', 'posts failed: TIME OVER')
        self.check(lock0 == 1 and left == posts['count'] and self.r('fury_lock') == 1 and self.r('bonus_on') == BN['end'],
                   f'posts fail (terry, A only): {posts["count"] - left} broken, the clock ran out, still locked ({self.r("fury_lock")})')
        self.check(self.r('snd_song') == self.mus['BONUS_OVER'], f"posts fail: AOF2's failed song (${self.r('snd_song'):02X}, want ${self.mus['BONUS_OVER']:02X})")
        self.lock_check('d_locked', want_fury=False)

    def lock_check(self, name, want_fury):
        """the result passed: stage 2; D with both bars full -> a fury or nothing"""
        self.until(lambda: self.r('bonus_on') == BN['off'] and self.r('mode') == 1, 600, keys='')
        self.b.run(90)
        for i, v in (('drive', 240 * self.r('drive_chunks')), ('fgauge', 100)): self.b.fset(0, i, v)
        self.b.run(1, p1='d'); self.b.run(12)
        st = self.b.states[self.b.fget(0, 'state')]; fury = st == 'SPECIAL' and self.b.fget(0, 'spec_id') == 6
        self.shot(name, 'stage 2, D: ' + ('the fury' if fury else 'nothing (locked)'))
        self.check(fury == want_fury, f'stage 2 D with gauge + drive full: {"fury" if fury else "no fury"} (want {"fury" if want_fury else "none: locked"}), state {st}')

    def sweep(self):
        res = {}
        sel = {r['name'] for r in json.load(open(os.path.join(self.game, 'game.json')))['roster'] if r.get('selectable', True)}
        for f in [n for n in self.names if n in sel]:          # (a form's target, Super Billy: never picked)
            try: lock0, t, left = self.play_posts(f, True, limit=self.G['games'][1]['seconds'] * 60 + 400)
            except Exception as e: res[f] = {'error': str(e)}; print('sweep', f, 'error', e); continue
            n = self.G['games'][1]['count']; res[f] = {'broken': n - left, 'ticks': t}
            print(f'sweep {f}: {n - left} / {n} posts in {t} ticks', flush=True)
        json.dump(res, open(os.path.join(self.out, 'sweep.json'), 'w'), indent=1)
        bad = [f for f, v in res.items() if v.get('broken') != self.G['games'][1]['count']]
        self.check(not bad, f'sweep: every fighter breaks every post with his fury in time (short: {bad})')

    def sheet(self):
        ims = [(Image.open(p).convert('RGB'), l) for p, l in self.shots]
        w, h = ims[0][0].size; cols = 4
        S = Image.new('RGB', (w * cols, (h + 14) * ((len(ims) + cols - 1) // cols)), 'white'); D = ImageDraw.Draw(S)
        for i, (im, l) in enumerate(ims):
            x, y = (i % cols) * w, (i // cols) * (h + 14); S.paste(im, (x, y + 14)); D.text((x + 2, y + 1), l, fill='black')
        S.save(os.path.join(self.out, 'sheet.png'))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(a) != 2: sys.exit(__doc__)
    P = Proof(*a)
    P.pick(); P.grades(); P.posts()
    if '--sweep' in sys.argv: P.sweep()
    P.sheet()
    print('ALL OK' if not P.fails else f'{P.fails} FAIL'); sys.exit(1 if P.fails else 0)


if __name__ == '__main__':
    main()
