#!/usr/bin/env python3
"""The two-stage campaign (Bruno 2026-10-17: two stages, ~30 % less scroll, one wave less each, RUGAL then GEESE, the
posts the only bonus, between them; meter + fury unlock kept across a continue; the posts' trunk pile spaced, its boxes
never overlapping, its clock 40 s), in our emulator (harness.py), the game's real paths:

    stages2_proof.py GAME_DIR OUT
      stage1   a new game (coin, START, Terry): the camera at 0, P1 walked in; every wave cleared by poke: the boss lock
               = game.json's (1568), the boss = boss_order[0] (RUGAL)                                -> s1_*.png
      stage2   the posts after stage 1 (scenario mode bonus), left to the clock (TIME 40 at the start): stage 2 begins
               through stage_begin with the camera at stages[].start (672), P1 on screen; its waves, the boss lock
               2240 and GEESE                                                                         -> s2_*.png
      continue stage 2 with the fury unlocked, 4 drive chunks and a full fury gauge: P1's last life lost, CONTINUE,
               coin + START: fury_lock, drive_chunks, his drive and fury gauge after it              -> cont_*.png
      pile     the posts' pile at its start (boxes drawn: wood x .. + 48, top - reach .. bottom), no two boxes overlapping
               (also after each hit), same-layer gaps, each upper trunk on both supports; A, A, A until one falls -> pile_*.png
    a contact sheet OUT/sheet.png; one OK / FAIL line per check, exit 1 on any FAIL"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario, bonus_proof
from PIL import Image, ImageDraw

BN_PLAY, BN_END = 2, 3
TR_SIZE = 12                                             # main.c bn_tr[]: int16 x, h, vy; uint8 st, hp, img, thud, dirty (+ pad)
BT_GONE, BT_REST, BT_FALL = 0, 1, 2


class P(bonus_proof.Proof):
    def s16(self, n): return self.r(n, 2)

    def boss_name(self):
        return self.names[self.b.char_of(2)]

    def clear_to_boss(self, tag):
        """every wave cleared by poke (the enemies off), P1 walking right: until the boss phase"""
        b = self.b; shots = 0
        for _ in range(9000):
            if self.r('phase') == 2: break
            if self.r('phase') == 0 and b.r(b.syms['in_ph'], 1) == 0:
                for i in range(2, 8):
                    if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD'): b.fset(i, 'state', b.states.index('OFF'))
            b.fset(0, 'hp', 60); b.run(1, p1='R')
            if self.r('phase') == 1 and shots < 1 and self.r('wave') == 1: self.shot(f'{tag}_scroll', f'{tag}: scrolling (cam {self.s16("cam_x")})'); shots += 1
        b.run(240, p1='R')

    def stage1(self, G):
        b = self.b
        st = [s for s in G['stages'] if not s.get('off')]
        b.to_fight(cache=False)
        cam, x = self.s16('cam_x'), b.fget(0, 'x')
        self.check(self.r('camp') == 0 and cam == st[0].get('start', 0), f'stage 1: a new game at camp 0, the camera at {cam} (want {st[0].get("start", 0)}), P1 x {x}')
        self.shot('s1_start', f'stage 1 start: cam {cam}')
        self.clear_to_boss('s1')
        lock, cam = self.s16('lock_x'), self.s16('cam_x')
        want = st[0]['boss']['lock']
        self.check(lock == want and cam == want, f'stage 1: the boss lock {lock}, the camera {cam} (want {want}, was 2240)')
        self.check(self.boss_name() == G['boss_order']['bosses'][0].lower(), f'stage 1 boss: {self.boss_name()} (want {G["boss_order"]["bosses"][0]})')
        self.shot('s1_boss', f'stage 1 boss {self.boss_name()}: cam {cam}')

    def to_stage2(self, unlocked=False):
        """the posts after stage 1, its clock run out (or won by the poke 'unlocked'): stage 2 through stage_begin"""
        b = self.b
        posts = next(x for x in self.G['games'] if x['kind'] == 'break')
        self.setup(game=posts['id'], unlocked=unlocked)
        clk = self.r('bn_clock', 2)
        b.w(b.syms['bn_clock'], 2, 5)
        self.until(lambda: self.r('bonus_on') == 0 and self.r('mode') == 1, 2500)
        return clk

    def stage2(self, G):
        b = self.b
        st = [s for s in G['stages'] if not s.get('off')]
        clk = self.to_stage2()
        self.check(2300 <= clk <= 2400, f'posts: the clock at the start {clk} ticks (want 40 s = 2400)')
        cam = self.s16('cam_x')
        self.check(self.r('camp') == 1 and cam == st[1]['start'], f'stage 2: camp {self.r("camp")}, the camera at its start {cam} (want {st[1]["start"]})')
        b.run(40); self.shot('s2_intro', f'stage 2 intro: cam {cam}')
        self.until(lambda: b.r(b.syms['in_ph'], 1) == 0, 900)
        x = b.fget(0, 'x')
        self.check(cam + 16 <= x <= cam + 304, f'stage 2: P1 walked in on screen (x {x}, the screen {cam}..{cam + 320})')
        b.run(30); self.shot('s2_start', f'stage 2 first wave: cam {self.s16("cam_x")}')
        self.clear_to_boss('s2')
        lock, cam = self.s16('lock_x'), self.s16('cam_x')
        want = st[1]['boss']['lock']
        self.check(lock == want and cam == want, f'stage 2: the boss lock {lock}, the camera {cam} (want {want}: the map\'s end unchanged)')
        self.check(self.boss_name() == G['boss_order']['bosses'][1].lower(), f'stage 2 boss: {self.boss_name()} (want {G["boss_order"]["bosses"][1]})')
        self.shot('s2_boss', f'stage 2 boss {self.boss_name()}: cam {cam}')

    def cont(self):
        b = self.b
        self.to_stage2(unlocked=True)
        self.until(lambda: b.r(b.syms['in_ph'], 1) != 0, 60); self.until(lambda: b.r(b.syms['in_ph'], 1) == 0, 900); b.run(30)
        b.w(b.syms['drive_chunks'], 1, 4); b.w(b.syms['lives'], 1, 0); b.fset(0, 'hp', 1)
        k = self.until(lambda: self.r('cont_t', 2) > 0, 4000)          # (the first wave's enemies take his last point)
        b.fset(0, 'drive', 240 * 4); b.fset(0, 'fgauge', 100); b.run(2)   # (out of play: what the continue must keep)
        before = (self.r('fury_lock'), self.r('drive_chunks'), b.fget(0, 'drive'), b.fget(0, 'fgauge'))
        self.shot('cont_ask', 'P1 out: CONTINUE')
        self.check(k >= 0, f'continue: the count after the last life ({k} ticks)')
        b.seq('4:o,60:-,4:s,10:-')
        k = self.until(lambda: b.states[b.fget(0, 'state')] not in ('OFF', 'DEAD'), 300)
        b.run(120)
        after = (self.r('fury_lock'), self.r('drive_chunks'), b.fget(0, 'drive'), b.fget(0, 'fgauge'))
        self.shot('cont_back', f'continued: drive chunks {after[1]}, fury lock {after[0]}')
        self.check(k >= 0 and after[0] == 0 and after[1] == 4 and after[2] == 240 * 4 and after[3] == before[3],
                   f'continue: fury_lock / drive_chunks / drive / fury gauge {before} -> {after} (want the unlock, the 4 chunks, a full bar, the gauge kept)')
        for i, v in (('drive', 240 * self.r('drive_chunks')), ('fgauge', 100)): b.fset(0, i, v)
        b.run(3, p1='d'); b.run(10)
        fury = b.states[b.fget(0, 'state')] == 'SPECIAL' and b.fget(0, 'spec_id') == 6
        self.shot('cont_fury', 'after the continue, D: ' + ('the fury' if fury else 'nothing'))
        self.check(fury, 'continue: D plays the fury after the continue (still unlocked)')

    # ---- the pile
    def trunks(self):
        b = self.b; base = b.syms['bn_tr']; out = []
        posts = next(x for x in self.G['games'] if x['kind'] == 'break'); pl = posts['pile']
        for k in range(len(pl['trunks'])):
            o = base + k * TR_SIZE
            s16 = lambda v: v - 65536 if v > 32767 else v
            out.append({'x': s16(b.r(o, 2)), 'h': s16(b.r(o + 2, 2)), 'st': b.r(o + 6, 1),
                        'reach': s16(b.r(b.syms['bn_reach'] + 2 * k, 2))})
        return out

    def boxes(self, tr, th):
        """each trunk's hit box on the screen (main.c bn_pile_flow): wood x + 8 .. + 56, y top + 4 - reach .. top + th"""
        floor = 224 - 0                                  # (AOF2's floor: the post's bottom; bn_trunk_top)
        r = []
        for k, t in enumerate(tr):
            if t['st'] == BT_GONE: continue
            top = floor - (t['h'] >> 4) - th
            r.append((k, t['x'] + 8, t['x'] + 56, top + 4 - t['reach'], top + th))
        return r

    def overlap(self, bx):
        return [(a[0], c[0]) for i, a in enumerate(bx) for c in bx[i + 1:] if a[1] < c[2] and c[1] < a[2] and a[3] < c[4] and c[3] < a[4]]

    def box_shot(self, name, label, th):
        p = os.path.join(self.out, name + '.png'); self.b.screenshot(p)
        im = Image.open(p).convert('RGB'); D = ImageDraw.Draw(im)
        for k, x0, x1, y0, y1 in self.boxes(self.trunks(), th):
            D.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(255, 0, 0)); D.text((x0 + 2, y1 - 12), str(k), fill=(255, 255, 0))
        im.save(p); self.shots.append((p, label))

    def pile(self):
        b = self.b
        posts = next(x for x in self.G['games'] if x['kind'] == 'break'); pl = posts['pile']; th = pl['trunk_h']
        tr = pl['trunks']
        gaps = sorted({abs(a[0] - c[0]) - 48 for a in tr for c in tr if a is not c and a[1] == c[1] and abs(a[0] - c[0]) < 100})
        self.check(gaps and min(gaps) == 16, f'pile: same-layer gaps {gaps} px (want 16 = a third of the 48 px wood)')
        sup = [sorted(abs(t[0] - u[0]) for u in tr if u[1] == t[1] - 1 and abs(t[0] - u[0]) < 48) for t in tr if t[1]]
        self.check(all(s == [32, 32] for s in sup), f'pile: each upper trunk over the gap of two supports, 32 px off each ({sup})')
        wood = (min(t[0] for t in tr) + 8, max(t[0] for t in tr) + 56)
        self.check(wood[0] >= 16 and wood[1] <= 312, f'pile: the wood {wood[0]}..{wood[1]} on the screen')
        self.setup(game=posts['id']); b.run(40)
        clk = self.r('bn_clock', 2)
        self.check(2300 <= clk <= 2400, f'posts: TIME {clk // 60 + 1} at the start ({clk} ticks; want 40 s)')
        self.shot('pile_start', f'the pile at its start (TIME {clk // 60 + 1})')
        bx = self.boxes(self.trunks(), th)
        self.box_shot('pile_boxes', 'the hit boxes (red): reach only over a free top', th)
        self.check(not self.overlap(bx) and len(bx) == len(tr), f'pile: {len(bx)} boxes, overlaps {self.overlap(bx)}; reach {[t["reach"] for t in self.trunks()]}')
        run0 = b.run; worst = []; fell = [False]
        def run(*a, **k):
            r = run0(*a, **k)
            if self.r('bonus_on') == BN_PLAY:
                if self.r('bn_clock', 2) < 600: b.w(b.syms['bn_clock'], 2, 99 * 60)
                tr_ = self.trunks(); o = self.overlap(self.boxes(tr_, th))
                if o: worst.append(o)
                if not fell[0] and any(t['st'] == BT_FALL for t in tr_):
                    fell[0] = True; run0(6); self.box_shot('pile_fall', 'a trunk falling (its supports broken)', th)
            return r
        b.run = run
        lock0, t, left = self.play_posts('terry', 'a', limit=99 * 60)
        b.run = run0
        self.check(fell[0], 'pile: a trunk fell when its supports broke')
        self.check(not worst, f'pile: no two boxes overlapping in any tick of the game ({len(worst)} ticks with an overlap: {worst[:3]})')
        self.check(left == 0, f'pile: all {len(tr)} trunks broken by Terry\'s A, A, A in {t} ticks')
        b.run(20); self.shot('pile_won', 'the pile won')


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(a) != 2: sys.exit(__doc__)
    game, out = a
    G = json.load(open(os.path.join(game, 'game.json')))
    p = P(game, out)
    p.stage1(G); p.stage2(G); p.cont(); p.pile()
    p.sheet()
    print('ALL OK' if not p.fails else f'{p.fails} FAIL'); sys.exit(1 if p.fails else 0)


if __name__ == '__main__':
    main()
