#!/usr/bin/env python3
"""The Last Blade 2's object frame update, read in the 68000 code and played in Python: a move's descriptor
($2EB26) and its animations' bytecode ($2BD1A), frame by frame, with no opponent hit (a whiff). Its output per frame is
what the game shows: animation, frame id, step, x / height (forward px), the boxes, the sounds and the effect objects.
`check` plays a move here and in the game (our emulator, play_lb2.py) and compares them frame by frame.

The interpreter, per frame [code]:
  1 a motion segment in a mode ($C8 = $8000 until landing: v += a, p += v, landed -> velocities 0, jump to $CC;
    $8100 / $8200 until vy / vx crosses 0)                                          ($2BDD2, $2C088, $2C0AC, $2C0EC)
  2 the commands at +$7C run until a frame word ($2BE36): the frame shows
  3 a counted segment ($C8 >= 0): $C8 -= 1; it ran out -> velocities 0, jump to $CC and read on in the same frame;
    else v += a, p += v                                                              ($2BEC8, $2C078, $2C032, $2BC9C)
  4 the tick: +$B6 -= 1; at 0 the next word (+$7C += 2), unless a running segment's last step is reached ($CA): held
    ($2BF00)
  $FFFF ends the animation: the descriptor's next word next frame (an animation, a control word, or $FFFF / 0: idle).
Coordinates: x forward (the script's x values are the art's, which faces left: forward = -value), height up; 16.16."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lb2 as L

def s16(v): return v - 0x10000 if v & 0x8000 else v
def s8(v): return v - 0x100 if v & 0x80 else v

def descriptor(ch, move):
    """the move's 16-byte descriptor (bank 2): words up to $FFFF"""
    t = L.u32(0x76554 + 4 * (ch & 31))
    out = []
    for k in range(8):
        w = L.u16(t + 16 * move + 2 * k, 2)
        if w == 0xFFFF: break
        out.append(w)
    return out

def transition(row, cls):
    """$A0000[row * 256 + class - 1]: the move a row (input class / recogniser result) starts from a state class"""
    return L.u8(0xA0000 + row * 256 + cls - 1)

# the descriptor's teleport placements (control word op 0, sub-op 9 / 10 / 11: $766D4 -> $2EDF8 / $2EE7C / $2EE9C) [code]:
# x = the opponent's x - 288 (screen-clamped: the camera's edges) / - 80 / + 110 (+ its +$154), toward / past it
WARP = {9: -288, 10: -80, 11: 110}

class Obj:
    def __init__(self, ch=1, mode=0, x=0.0, opp_dx=None, held=0):
        self.held = held                             # frames its button stays held (the $84-$87 waits: Oboro's stand-by)
        self.ch, self.mode = ch, mode
        self.x = self.h = 0.0; self.vx = self.vh = self.ax = self.ah = 0.0
        self.opp_dx = opp_dx                         # the opponent's distance ahead (distance ops), None: far
        self.cls = 1; self.desc = []; self.di = 0; self.ended = False
        self.boxes = {}; self.push = None; self.events = []; self.f = 0
        self.flip = 0; self.x0 = 0.0; self.turned = 0
    # ---- the descriptor ($2EA3E / $2EB26) ----
    def start_move(self, move):
        self.move = move; self.desc = descriptor(self.ch, move); self.di = 0; self.boxes = {}
        self.next_desc()
    def next_desc(self):
        while True:
            if self.di >= len(self.desc): self.set_anim(0); self.done = True; return
            w = self.desc[self.di]; self.di += 1
            if not w & 0x8000:
                self.set_anim(w & 0x1FF); self.done = (w == 0) or (w in (6,) and self.di == len(self.desc)); return
            op, arg = (w >> 9) & 63, w & 0x1FF
            self.events.append((self.f, 'op', op, arg))
            if op == 0 and arg in WARP and self.opp_dx is not None:   # $2EDF8 / $2EE7C / $2EE9C: placed by the opponent
                self.x = self.x0 + self.opp_dx + WARP[arg]; self.events.append((self.f, 'warp', arg, WARP[arg]))
            if op in (14, 15, 16) and self.opp_dx is not None and self.opp_dx >= 96: self.start_move(arg); return
            if op in (17, 18, 19) and self.opp_dx is not None and self.opp_dx >= 176: self.start_move(arg); return
    def set_anim(self, a):
        self.anim = a; self.base = L.anim_addr(self.ch, a); self.off = 0
        self.step = 0; self.tick = 0; self.ticks = 1; self.seg = -1; self.segend = 0; self.segoff = 0
        self.loop = None; self.ended = False; self.disp = (0, 0); self.newword = True
        self.vx = self.vh = self.ax = self.ah = 0.0 if self.h <= 0 else self.vx
        self.readnext = True
    # ---- the frame ----
    def frame(self):
        if self.ended:
            self.next_desc()
        self.seg_modes()
        self.read()
        self.seg_count()
        out = dict(f=self.f, anim=self.anim, frame=self.fid, step=self.step, x=self.x, h=self.h,
                   boxes=dict(self.boxes), push=self.push, cls=self.cls, disp=self.disp, turned=self.turned)
        self.tick_end()
        self.f += 1
        return out
    def integrate(self):
        self.vx += self.ax; self.vh += self.ah; self.x += self.vx; self.h += self.vh
    def seg_modes(self):
        if self.seg == 0x8000:
            self.integrate()
            if self.h > 0: return
            self.vx = self.vh = self.ax = self.ah = 0.0; self.seg = -1; self.h = 0.0; self.jump()
        elif self.seg in (0x8100, 0x8200):
            if self.seg == 0x8100: v, a = self.vh, self.ah
            else: v, a = self.vx, self.ax
            if v != 0:
                nv = v + a
                if (v > 0 and nv > 0) or (v < 0 and nv < 0):
                    if self.seg == 0x8100: self.vh = nv
                    else: self.vx = nv
                    self.x += self.vx; self.h += self.vh; return
            self.vx = self.vh = self.ax = self.ah = 0.0; self.seg = -1
            self.tick = self.ticks; self.step = self.segend + 1; self.jump_noreset()
    def jump(self):
        """$2C032: +$7C = +$CC (past $97 / $9F words), the ticks reloaded, the step = the segment's last + 1"""
        self.off = self.segoff
        while True:
            w = L.u16(self.base + self.off)
            if w >> 8 in (0x97, 0x9F): self.off += 2; continue
            break
        self.tick = self.ticks; self.step = self.segend + 1; self.readnext = True; self.newword = True
    def jump_noreset(self): self.jump()
    def read(self):
        """$2BE36: run the commands up to the frame word at +$7C (a new word: the drawing offset +$4A / +$4C cleared
        first, $2BE24)"""
        if self.newword: self.disp = (0, 0); self.newword = False
        for _ in range(200):
            a = self.base + self.off; w = L.u16(a)
            if w == 0xFFFF:
                self.ended = True; return
            if not w & 0x8000:
                self.fid = w & 0xFFF; self.fflags = w >> 12; return
            op = 0x80 | (w >> 8 & 0x3F)
            b = bytes(L.u8(a + k) for k in range(L.CMDLEN[op]))
            self.cmd(op, b)
        raise RuntimeError('script loop')
    def m(self, b, k):
        """a per-style byte: Power +1, Speed +2 (EX: Speed)"""
        return b[k + (0 if self.mode == 0 else 1)]
    def cmd(self, op, b):
        ln = L.CMDLEN[op]; adv = True
        w = lambda k: s16(b[k] << 8 | b[k + 1])
        if op == 0x81: self.ticks = self.m(b, 1); self.tick = self.ticks
        elif op == 0x82:                                  # $2C4B4: 0 turn around, 1 / 2 face toward / away from the opponent
            self.events.append((self.f, 'face', b[1]))
            if b[1] == 0: self.turned ^= 1
        elif op == 0x83: self.disp = (w(2), w(4)); self.events.append((self.f, 'disp', w(2), w(4)))   # +$4A / +$4C (art px)
        elif op in (0x84, 0x85, 0x9B, 0x9C, 0x9D, 0x9E):
            gate = {0x84: True, 0x85: True, 0x9B: self.mode in (1, 3), 0x9C: self.mode in (1, 3), 0x9D: self.mode == 2, 0x9E: self.mode == 2}[op]
            if gate and (op in (0x85, 0x9C, 0x9E) or self.seg == -1):
                self.segend = b[1] + self.step; self.seg = w(2) & 0xFFFF; self.segoff = w(4)
                if self.seg & 0x8000: pass
                if op in (0x84, 0x9B, 0x9D):
                    self.vx = -w(6) / 256; self.vh = w(8) / 256; self.ax = -w(10) / 256; self.ah = w(12) / 256
                else:
                    self.ax = -w(6) / 256; self.ah = w(8) / 256
                if self.seg == 0x8000 and self.h == 0: self.h = 1 / 65536   # ($2C5A2: height 0 -> 1, airborne)
        elif op == 0x86: self.x += -w(2)
        elif op == 0x88:
            self.h += w(2)
            if self.h < 0: self.h = 0.0
        elif op == 0x8B: self.events.append((self.f, 'snd', b[2] << 8 | b[3]))
        elif op == 0x90:
            self.push = None if b[3] == 0xFF else (b[3] & 7, s8(b[4]), s8(b[6]), s8(b[5]), s8(b[7]))
        elif op in (0x91, 0xB5):
            if op == 0x91: typ, wd, xs = self.m(b, 1), b[4] << 8 | b[5], b[6:10]
            else: typ, wd, xs = b[1], b[2] << 8 | b[3], b[4:8]
            slot = wd >> 8 & 7
            if wd & 0xFF == 0xFF: self.boxes.pop(slot, None)
            else: self.boxes[slot] = (typ, wd & 7, s8(xs[0]), s8(xs[2]), s8(xs[1]), s8(xs[3]))
        elif op == 0xBA: self.boxes.pop(b[1] & 7, None)
        elif op == 0x92: self.cls = self.m(b, 1)
        elif op == 0x96: self.loop = [b[1], self.off + 2, self.step]    # $2CA9A: the count, the place, the step index
        elif op == 0x97:                                  # $2CAC4: count 0 loops for ever; else count - 1 more passes
            if self.loop and (self.loop[0] == 0 or self.loop[0] > 1):
                if self.loop[0]: self.loop[0] -= 1
                self.off = self.loop[1]; self.step = self.loop[2]; self.tick = self.ticks; return   # (+$B8 restored)
            self.loop = None
        elif op == 0x9F:
            self.off = 0; self.step = 0; return
        elif op in (0x99, 0x9A, 0xA3, 0xA7, 0xA8, 0xA9, 0xAA, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3):
            self.events.append((self.f, 'spawn', op, b))
        self.off += ln
    def seg_count(self):
        if 0x8400 <= self.seg < 0x8800 or 0x8F00 <= self.seg < 0x9100:   # $2C186-$2C1B8 (after the commands, $2BED6):
            self.integrate()                              # held while its buttons are ($84 A .. $87 D, $8F A+B, $90 B+C),
                                                          # at most the low byte's frames
            cnt = (self.seg & 0xFF) - 1
            if cnt >= 0 and self.held > 0:
                self.seg = (self.seg & 0xFF00) | cnt; self.held -= 1; return
            self.vx = self.vh = self.ax = self.ah = 0.0; self.seg = -1; self.h = 0.0; self.jump(); self.read(); return
        if self.seg == -1 or self.seg & 0x8000: return
        if self.seg == 0:
            self.vx = self.vh = self.ax = self.ah = 0.0; self.seg = -1; self.jump(); self.read(); return
        self.seg -= 1; self.integrate()
    def tick_end(self):
        if self.ended: return
        self.tick -= 1
        if self.tick > 0: return
        if self.seg != -1 and self.segend <= self.step:
            nxt = L.u16(self.base + self.off + 2)
            if nxt >> 8 == 0x9F: self.off = 0; self.step = 0; self.tick = self.ticks; return
            if nxt >> 8 == 0x97 and self.loop:            # $2BF38: a segment's last step before a loop end loops
                if self.loop[0]:
                    self.loop[0] -= 1
                    if not self.loop[0]: self.tick = 1; return
                self.off = self.loop[1]; self.step = self.loop[2]; self.tick = self.ticks; return
            self.tick = 1; return
        self.tick = self.ticks; self.step += 1; self.off += 2; self.newword = True

def play_move(ch, move, n=400, mode=0, opp_dx=None, held=0):
    o = Obj(ch, mode, opp_dx=opp_dx, held=held); o.start_move(move)
    rows = []
    for _ in range(n):
        r = o.frame(); rows.append(r)
        if getattr(o, 'done', False) and o.anim == 0 and len(rows) > 2: break
    return rows, o.events

if __name__ == '__main__':
    mv = int(sys.argv[1], 0)
    rows, ev = play_move(1, mv)
    for r in rows: print(r['f'], hex(r['anim']), r['frame'], r['step'], round(r['x'], 2), round(r['h'], 2))
    print(ev)
