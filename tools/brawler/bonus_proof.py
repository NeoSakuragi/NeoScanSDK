#!/usr/bin/env python3
"""The bonus stages' proof (TODO T7; main.c "bonus stages", game.json "bonus"), in our emulator's core (harness.py),
every run from scenario.py's mode "bonus" (lab req 6: a new game, then the bonus after stage `after`):

    bonus_proof.py GAME_DIR OUT [--sweep]
      pick    AOF2's BONUS GAME screen, the select (cursor right, an empty slot skipped, the clock), the
              title card, then the cursor's game                                                       -> intro, pick*, card.png
      grades  the Ki training pressed at a power of each grade (0-5): grade, drive chunks after          -> tree_g*.png
      win     the posts with Terry (note bonus-pillars-normals: `count` posts, `hp` hits each, any regular attack): A at
              each post until all are broken (the clock kept off its end: the bot's A, A, A needs ~1900 ticks for
              note 20261015-221208-e03d's 5 x 12, printed): unlocked, then the unlock's message box held won_ticks, or
              with won_by referee SS2's referee speaking (tools/brawler/referee_proof.py checks him)  -> posts_win*.png
      dgame   in the posts game, D with the gauge and drive full: no fury (still locked while it plays)  -> posts_d.png
      fail    the posts left alone to the clock's end: TIME OVER, still locked                          -> posts_fail*.png
      lock    the next stage after each (stage 2): D with the gauge and drive full: no fury while locked,
              the fury after the win                                                                    -> d_locked.png, d_unlocked.png
      --sweep every selectable fighter: the posts won with normals (A), posts broken / ticks used (OUT/sweep.json)
    a contact sheet OUT/sheet.png; prints one OK / FAIL line per check, exit 1 on any FAIL"""
import ctypes as C, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
from PIL import Image, ImageDraw

BN = {'off': 0, 'pick': 1, 'play': 2, 'end': 3, 'intro': 4, 'card': 5}
BIG_BONUS_METER = 6                                    # build_tables BIG_USES: big_text.bonus_meter's row in gbig
BP_STAND = 2


class Proof:
    def __init__(self, game, out):
        self.maxc = json.load(open(os.path.join(game, 'game.json')))['meter'].get('max_chunks', 4)   # the bar's most chunks
        self.game, self.out = game, out; os.makedirs(out, exist_ok=True)
        self.b = H.Brawler(game=game); self.b.game = game
        self.names = scenario.roster(game); self.fails = 0; self.shots = []
        self.G = json.load(open(os.path.join(game, 'game.json')))['bonus']
        for x in self.G['games']:                       # (a pile's own count / hp: game.json games[].pile, main.c "the pile")
            if x.get('layout') == 'pile': x['count'] = len(x['pile']['trunks']); x['hp'] = x['pile'].get('hp', x.get('hp', 1))
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
        slots = sorted(x['slot'] for x in self.G['games']); last = len(slots) - 1
        self.check(self.r('bn_slot') == slots[0] and self.r('bn_cur') == 0, f'pick: the cursor on the first game\'s slot {slots[0]}')
        if last:
            self.b.seq('4:R,30:-')
            self.check(self.r('bn_cur') == 1 and self.r('bn_slot') == slots[1], f'pick: the stick moves the cursor right, to slot {self.r("bn_slot")} (want {slots[1]}: an empty slot skipped)')
            self.shot('pick_right', 'cursor right')
        self.b.seq('4:R,30:-')
        self.check(self.r('bn_cur') == last, f'pick: no slot right of the last game (one game: the stick keeps it, 2026-10-17)')
        k = self.until(lambda: self.r('bonus_on') == BN['card'], self.G['pick']['seconds'] * 60 + 200)
        self.check(k >= 0, f'pick: the clock ran out -> the title card after {k} more ticks')
        self.b.run(60); self.shot('card', 'the title card')
        last = [0]; k = self.until(lambda: last.__setitem__(0, self.r('bn_t', 2)) if self.r('bonus_on') == BN['card'] else True, ct + 10)
        self.check(k >= 0 and self.r('bonus_on') == BN['play'] and last[0] in (ct - 1, ct) and self.r('bn_game') == len(self.G['games']) - 1, f'pick: the card (its clock at {last[0]}, card.ticks {ct}) -> the cursor\'s game ({self.G["games"][-1]["id"]})')

    # ---- the Ki training: one press per grade
    def grades(self):
        ki = next((x for x in self.G['games'] if x['kind'] == 'gauge'), None)
        if ki is None: print('SKIP grades: no gauge game in bonus.games (the Ki training benched, 2026-10-17)'); return
        kk = self.G['games'].index(ki) + 1
        gr = [0] + ki['grades']
        for g in range(6):
            lo = gr[g]; hi = gr[g + 1] if g < 5 else 128
            want = (lo + hi) // 2
            self.setup(game=ki['id']); self.b.run(40)
            c0 = self.r('drive_chunks')
            k = self.until(lambda: lo <= self.r('bn_power') < lo + ki['step'] and lo > 0 or g == 0 and self.r('bn_power') < ki['step'], 400)   # (just inside the grade's band: the narrow top ones too; the press reads the next power)
            self.b.run(1, p1='a')
            ba = re.search(r'enum \{ (BA_IDLE[^}]*)\}', open(os.path.join(self.game, 'build', 'bm_chars.h')).read()).group(1).replace(' ', '').split(',')
            cg = ki.get('charge') or {}; win = g >= ki.get('win_grade', 5)
            if cg:                                  # (note 20261014-133606-5d29: AOF2's concentration before the blow)
                self.b.run(cg['stand'] + 6)
                a = ba[self.b.fget(0, 'anim')]
                self.check(a == 'BA_CHARGE', f'tree grade {g}: {cg["stand"] + 6} ticks after the press he concentrates ({a})')
                if g in (0, 5): self.shot(f'tree_g{g}_charge', f'tree grade {g}: the concentration')
                self.b.run(cg['pass' if win else 'fail'] - cg['stand'] - 6)
            self.b.run(3)
            mv = ba[self.b.fget(0, 'anim')] if self.b.states[self.b.fget(0, 'state')] == 'ATTACK' else self.b.states[self.b.fget(0, 'state')]
            blow = ki.get('blows', ['jab'] * 6)[g]       # (results-1014: a jab when the tree holds, the forward finisher when it breaks)
            self.check((mv in ('BA_ATK_A_FAR', 'BA_ATK_A_CLOSE')) == (blow == 'jab'), f'tree grade {g}: the blow {blow}: Terry plays {mv}')
            self.b.run(27)
            if g in (0, 5): self.shot(f'tree_g{g}_hit', f'tree grade {g}: the blow')
            if win:                                 # (AOF2's top grade: the tree breaks, note 20261014-133606-5d29)
                self.b.run(40); self.shot(f'tree_g{g}_fall', f'tree grade {g}: the top falling')
                self.b.run(36); self.shot(f'tree_g{g}_crown', f'tree grade {g}: the crown landed')
            t = self.until(lambda: self.r('bonus_on') == BN['end'], 300); self.b.run(2)
            got, c1 = self.r('bn_grade'), self.r('drive_chunks')
            self.shot(f'tree_g{g}', f'tree grade {g}: result')
            pr = ki.get('pass_reward')                  # (notes 20261016-133045 / -135212-e03d: a pass's chunks by clear)
            add = min(pr['chunks'][0] if win and pr else ki['chunks'][g], self.maxc - c0)
            self.check(k >= 0 and got == g and c1 == c0 + add, f'tree: pressed at power ~{want}: grade {got} (want {g}), drive chunks {c0} -> {c1} (want +{add})')
            if win and pr: self.pass_screen(pr['text'][add], 'the first pass')
            song = self.r('snd_song'); want_s = self.mus['BONUS_WIN' if win else 'BONUS_OVER']
            self.check(t >= 0 and song == want_s and (self.r('bn_fall_t', 2) > 0) == win,
                       f"tree grade {g}: {'passed' if win else 'failed'} as AOF2: song ${song:02X} (want ${want_s:02X} {'won' if win else 'failed'}), the tree {'falls' if self.r('bn_fall_t', 2) else 'stands'}")
        # the bar after the reward, in the next stage
        self.b.run(400)
        self.check(self.r('bonus_on') == BN['off'] and self.r('mode') == 1 and self.r('camp') == 1, 'tree: the next stage (stage 2) after the result')
        self.b.run(60); self.shot('tree_stage2_bar', 'stage 2: the 4-chunk drive bar')
        self.check(self.r('drive_chunks') == 4, f'tree: the bar keeps {self.r("drive_chunks")} chunks in stage 2 (want 4: 2 + the top grade\'s 2)')

    def pass_screen(self, text, what):
        """a pass's result (note 20261016-135212-e03d): its big headline alone (pass_reward.text), nothing on the fix
        layer's rows 4-27 (no grade, no BONUS, the gauge bar gone)"""
        b = self.b; S = b.syms
        n = b.core.retro_get_memory_size(3); vram = (C.c_uint16 * (n // 2)).from_address(b.core.retro_get_memory_data(3))
        b.run(100)                                 # (in the headline's hold: after its slide in and blink)
        use = (b.r(S['bt_s'], 4) - S['gbig']) // 10
        row = lambda r: ''.join(chr(v) if 0x20 < v < 0x7F else ' ' for v in (vram[0x7000 + c * 32 + r + 2] & 0xFFF for c in range(1, 39))).strip()
        tiles = [vram[0x7000 + c * 32 + 9 + 2] & 0xFFF for c in range(12, 28)]
        rows = {r: row(r) for r in range(4, 26) if row(r)}   # (row 26+: the arcade line, version / CPU)
        self.check(b.r(S['bt_n'], 1) > 0 and use == BIG_BONUS_METER and not rows and all(t == 0x20 or t == 0 for t in tiles),
                   f'tree {what}: only the big headline {text!r} ({b.r(S["bt_n"], 1)} glyph columns, use {use}); fix rows {rows}, the gauge bar row 9 {"cleared" if all(t in (0, 0x20) for t in tiles) else tiles}')
        self.shot('tree_pass_' + what.split()[1], f'tree {what}: {text}')

    def second_pass(self, start=None):
        """the same credit's second pass of the gauge game: pass_reward.chunks[1] (bn_clr = 1, as after a first pass); start:
        the bar's chunks before it (note 20261016-152232-e03d: at 4 the pass gives the 5th, meter.max_chunks; at 5 METER
        ALREADY FULL)"""
        ki = next((x for x in self.G['games'] if x['kind'] == 'gauge'), None)
        if ki is None: return
        pr = ki.get('pass_reward')
        if not pr or len(pr['chunks']) < 2: return
        self.setup(game=ki['id']); self.b.run(2)
        self.b.w(self.b.syms['bn_clr'] + self.G['games'].index(ki), 1, 1)   # (one pass of it already this credit)
        if start: self.b.w(self.b.syms['drive_chunks'], 1, start)
        self.b.run(38); c0 = self.r('drive_chunks')
        self.until(lambda: self.r('bn_power') >= ki['grades'][-1] + 2, 400); self.b.run(1, p1='a')
        self.until(lambda: self.r('bonus_on') == BN['end'], 600); self.b.run(2)
        add = min(pr['chunks'][1], self.maxc - c0)
        self.check(self.r('bn_grade') == 5 and self.r('drive_chunks') == c0 + add, f'tree, the second pass this credit: drive chunks {c0} -> {self.r("drive_chunks")} (want +{add}: pass_reward.chunks[1])')
        self.pass_screen(pr['text'][add], 'the second pass' + (f' from {start}' if start else ''))
        if start: self.shot(f'tree_hud_{c0 + add}', f'tree, the second pass from {start}: the HUD bar at {c0 + add} chunks')

    # ---- the posts: played with D (win) or A only (fail)
    def play_posts(self, fighter, key, shots=False, limit=None):
        """the posts game: walk to the post, press `key` (a: normals, d: the fury, '': nothing) every 8 ticks at it"""
        use_d = key == 'd'
        posts = next(x for x in self.G['games'] if x['kind'] == 'break'); pk = self.G['games'].index(posts) + 1
        self.setup(fighter=fighter, game=posts['id'])
        lock0 = self.r('bn_lock0')                  # (the lock as the game came in: lifted while it plays)
        t = 0; shot_hit = shot_split = shot_lesson = False; px = 241
        self.links = 0; self.stops = 0; run = 0; last_node = -1    # the longest chain (links in one string), hit-stop ticks
        limit = limit or (posts['seconds'] * 60 + 400)
        while self.r('bonus_on') == BN['play'] and t < limit:
            st = self.b.states[self.b.fget(0, 'state')]; fx = self.b.fget(0, 'x'); post = self.r('bn_post')
            keys = ''
            if post == BP_STAND and st in ('IDLE', 'WALK'):
                px = self.r('bn_px', 2); right = px + 32 > fx      # (the post / the pile's front trunk: his right or his left)
                gap = px - fx if right else fx - (px + 64)
                face = self.b.fget(0, 'facing'); face = face - 256 if face > 127 else face
                if not key: keys = ''
                elif gap > (36 if use_d else 12): keys = 'R' if right else 'L'
                elif (face > 0) != right: keys = 'R' if right else 'L'   # (turned to it first)
                elif t & (15 if use_d else 7) == 0: keys = key
            elif key == 'a' and post == BP_STAND and st == 'ATTACK' and t & 7 == 0:   # A, A, A: the chain (on a post in
                px = self.r('bn_px', 2); right = px + 32 > fx                             # front of him, near: else he
                gap = px - fx if right else fx - (px + 64)                               # lets it end, then turns / walks)
                face = self.b.fget(0, 'facing'); face = face - 256 if face > 127 else face
                if gap <= 12 and (face > 0) == right: keys = key
            node = self.b.fget(0, 'node')                  # (note 20261014-231537-5d29: a post hit links the chain)
            if st == 'ATTACK':
                if node != last_node:
                    run += 1; last_node = node
                    if shots and key and run >= 2 and run > self.links: self.shot(f'posts_chain_{run}', f'posts: A, A, A: link {run} of the chain (node {node})')
                self.links = max(self.links, run)
            else: run = 0; last_node = -1
            if self.b.fget(0, 'freeze') and st == 'ATTACK': self.stops += 1
            self.b.run(1, p1=keys); t += 1
            if shots and t == 30: self.shot(f'posts_{"win" if key else "fail"}_lesson', 'posts: the lesson box')
            if shots and key and not shot_lesson and self.r('bn_chip_t') == 28: self.shot('posts_win_chip', f'a hit: it shakes, a chip flies ({self.r("bn_hp")} left)'); shot_lesson = True
            if shots and key and not shot_split and self.r('bn_split') == 40: self.shot('posts_win_split', 'the last hit: its splinters'); shot_split = True
        return lock0, t, self.r('bn_left')

    def posts(self):
        posts = next(x for x in self.G['games'] if x['kind'] == 'break')
        run0 = self.b.run
        def run(*a, **k):                                 # (the clock kept off its end for the win)
            if self.r('bonus_on') == BN['play'] and self.r('bn_clock', 2) < 600: self.b.w(self.b.syms['bn_clock'], 2, 99 * 60)
            return run0(*a, **k)
        self.b.run = run
        lock0, t, left = self.play_posts('terry', 'a', shots=True, limit=99 * 60)
        self.b.run = run0
        print(f'     posts won in {t} ticks (the game\'s clock: {posts["seconds"] * 60})')
        self.check(self.links >= 3 and self.stops > 0, f'posts win (terry, A, A, A): the post hits link his chain ({self.links} links in one string, '
                   f'{self.stops} hit-stop ticks; note 20261014-231537-5d29: was 1, no hit-stop)')
        self.b.run(20); self.shot('posts_win', 'posts won: the unlock message')
        self.check(lock0 == 1 and left == 0 and self.r('fury_lock') == 0 and self.r('bonus_on') == BN['end'],
                   f'posts win (terry, A: normals): locked before ({lock0}), {posts["count"] - left} / {posts["count"]} broken in {t} ticks, unlocked after ({self.r("fury_lock") == 0})')
        self.check(self.r('snd_song') == self.mus['BONUS_WIN'], f"posts win: AOF2's won song (${self.r('snd_song'):02X}, want ${self.mus['BONUS_WIN']:02X})")
        hold = self.r('bn_hold', 2); ref = self.r('rf'); n = self.until(lambda: self.r('bonus_on') != BN['end'], 2000)
        if posts.get('won_by') == 'referee':
            self.check(ref != 0 and n > 300, f'posts win: SS2\'s referee speaks (phase {ref} 20 ticks after the win), {n + 20} ticks to the next stage')
        else:
            self.check(hold == posts.get('won_ticks', 300) and n + 20 >= hold - 2, f'posts win: the unlock message held {n + 20} ticks (bn_hold {hold}, want won_ticks {posts.get("won_ticks", 300)})')
        self.lock_check('d_unlocked', want_fury=True)
        self.d_in_game()
        lock0, t, left = self.play_posts('terry', '', shots=True)
        self.b.run(20); self.shot('posts_fail', 'posts failed: TIME OVER')
        self.check(lock0 == 1 and left == posts['count'] and self.r('fury_lock') == 1 and self.r('bonus_on') == BN['end'],
                   f'posts fail (terry, no attack): {posts["count"] - left} broken, the clock ran out, still locked ({self.r("fury_lock")})')
        self.check(self.r('snd_song') == self.mus['BONUS_OVER'], f"posts fail: AOF2's failed song (${self.r('snd_song'):02X}, want ${self.mus['BONUS_OVER']:02X})")
        self.lock_check('d_locked', want_fury=False)

    def d_in_game(self):
        """the posts game: the fury still locked while it plays (D with both bars full: no fury)"""
        posts = next(x for x in self.G['games'] if x['kind'] == 'break')
        self.setup(fighter='terry', game=posts['id']); self.b.run(90)
        for i, v in (('drive', 240 * self.r('drive_chunks')), ('fgauge', 100)): self.b.fset(0, i, v)
        self.b.run(3, p1='d'); self.b.run(10)                   # (held 3 frames: a lag frame drops a 1-frame press)
        st = self.b.states[self.b.fget(0, 'state')]; fury = st == 'SPECIAL' and self.b.fget(0, 'spec_id') == 6
        self.shot('posts_d', 'posts game, D: ' + ('the fury' if fury else 'nothing (locked)'))
        self.check(not fury and self.r('fury_lock') == 1, f'posts game: D with gauge + drive full: {"fury" if fury else "no fury"} (want none: locked while it plays), state {st}')

    def lock_check(self, name, want_fury):
        """the result passed: stage 2; D with both bars full -> a fury or nothing"""
        self.until(lambda: self.r('bonus_on') == BN['off'] and self.r('mode') == 1, 900, keys='')
        self.until(lambda: self.r('in_ph') != 0, 60); self.until(lambda: self.r('in_ph') == 0, 900)   # (stage 2's intro: the walk in, the first wave)
        self.b.run(30)
        for i, v in (('drive', 240 * self.r('drive_chunks')), ('fgauge', 100)): self.b.fset(0, i, v)
        self.b.run(3, p1='d'); self.b.run(10)                   # (held 3 frames: a lag frame drops a 1-frame press)
        st = self.b.states[self.b.fget(0, 'state')]; fury = st == 'SPECIAL' and self.b.fget(0, 'spec_id') == 6
        self.shot(name, 'stage 2, D: ' + ('the fury' if fury else 'nothing (locked)'))
        self.check(fury == want_fury, f'stage 2 D with gauge + drive full: {"fury" if fury else "no fury"} (want {"fury" if want_fury else "none: locked"}), state {st}')

    def sweep(self):
        res = {}
        sel = {r['name'] for r in json.load(open(os.path.join(self.game, 'game.json')))['roster'] if r.get('selectable', True)}
        pi = next(i for i, x in enumerate(self.G['games']) if x['kind'] == 'break')
        for f in [n for n in self.names if n in sel]:          # (a form's target, Super Billy: never picked)
            try: lock0, t, left = self.play_posts(f, 'a', limit=self.G['games'][pi]['seconds'] * 60 + 400)
            except Exception as e: res[f] = {'error': str(e)}; print('sweep', f, 'error', e); continue
            n = self.G['games'][pi]['count']; res[f] = {'broken': n - left, 'ticks': t, 'links': self.links, 'stop_ticks': self.stops}
            print(f'sweep {f}: {n - left} / {n} posts in {t} ticks, chain up to {self.links} links, {self.stops} hit-stop ticks', flush=True)
        json.dump(res, open(os.path.join(self.out, 'sweep.json'), 'w'), indent=1)
        bad = [f for f, v in res.items() if v.get('broken') != self.G['games'][pi]['count']]
        self.check(not bad, f'sweep: every fighter breaks every post with his normals in time (short: {bad})')
        one = [f for f, v in res.items() if v.get('links', 0) < 2]
        self.check(not one, f'sweep: every fighter chains on the posts (A, A, A: 2+ links; stuck at link 1: {one})')

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
    P.pick(); P.grades(); P.second_pass(); P.second_pass(P.maxc - 1); P.second_pass(P.maxc); P.posts()
    if '--sweep' in sys.argv: P.sweep()
    P.sheet()
    print('ALL OK' if not P.fails else f'{P.fails} FAIL'); sys.exit(1 if P.fails else 0)


if __name__ == '__main__':
    main()
