#!/usr/bin/env python3
"""Art of Fighting 1 / 2 bonus games in our emulator's core (makoto3's tap core, Geolith): T7 study, notes in
/data/neogeo_dict/aof/bonus.md.
    bonus_cap.py state GAME                 one credit, Ryo, stage counter $108428 forced to the first bonus stage until the
                                            bonus-select song; state saved at the select screen -> /data/tmp/t7/GAME_sel.state
    bonus_cap.py play GAME NAME CHOICE MODE [FRAMES]
                                            from that state: R x CHOICE, A, then MODE's inputs; every 2nd frame's PNG, every
                                            frame's 68K RAM (/data/tmp/t7/GAME_NAME/ fNNNNN.png, ram.bin = FRAMES x 64 KB),
                                            the music log music.txt (frame after the choice, command)
env T0 (peak's earliest frame, default 520), HOLDB=off:val,... (bytes held every frame)
MODE: none | mash (A every 4 frames) | mashall (A/B/C/D rotating) | hsk[:N] (the Haoh Shoko-ken motion, N frames a direction, + A; repeated)
      | fight (walk right, A/C mashed) | brawl[:BTN:PERIOD] (BTN mashed, walking right / left by turns) | tap@N (A once at frame N after the choice)
      | peak:OFF (A once when the RAM byte at $100000 + OFF reaches 250: the bottle cut / spirit training gauge)"""
import sys, os, ctypes as C
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'makoto3'))
import capture
from games import m1_path, music_cmds
OUT = '/data/tmp/t7'
SEL = {'aof': (3, 0x43), 'aof2': (4, 0x33)}      # stage counter of the first bonus stage, bonus-select song

def core(game):
    capture.GAME = game
    music = set(music_cmds(open(m1_path(game), 'rb').read())); ev = []; arg = [False]
    PREFIX = {0x0A, 0x0E, 0x14, 0x15, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1E}
    class S(capture.Sound):
        def _line(self, t):
            if not t.startswith('c '): return
            c = int(t.split()[1], 16)
            if arg[0]: arg[0] = False; return
            arg[0] = c in PREFIX
            if c in music: ev.append((self.frame, c))
        def shot(self, path, keys=''):
            from PIL import Image
            self._want_video = True; self.run(1, keys); self._want_video = False
            data, w, h, pitch = self._video
            Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(path)
    s = S(); s.out = True
    s.core.retro_get_memory_data.restype = C.c_void_p; s.core.retro_get_memory_size.restype = C.c_size_t
    s.ram = (C.c_uint8 * s.core.retro_get_memory_size(2)).from_address(s.core.retro_get_memory_data(2))
    return s, ev

def state(game):
    s, ev = core(game); cnt, song = SEL[game]
    keys = {1500: 'o', 1560: 'o', 1600: 's', 1800: 'a', 1900: 'a', 2000: 'a'}
    while not any(c == song for f, c in ev) and s.frame < 9000:
        s.run(1, next((k for f, k in keys.items() if f <= s.frame < f + 6), ''))
        if s.frame > 1720: s.ram[0x8428] = cnt >> 8; s.ram[0x8429] = cnt & 255
    s.run(260); open(f'{OUT}/{game}_sel.state', 'wb').write(s.save()); s.shot(f'{OUT}/{game}_sel.png')
    print(game, 'select at', s.frame, [(f, hex(c)) for f, c in ev])

HSK = 'R', 'L', 'DL', 'D', 'DR', 'Ra'                 # forward, back, down-back, down, down-forward, forward + A
PRESSED = [0]
NOSHOT = os.environ.get('NOSHOT') == '1'           # no PNGs (sweeps)
T0 = int(os.environ.get('T0', 520))             # peak: not before this frame (the game's START)
HOLDB = [(int(o, 16), int(v, 16)) for o, v in (x.split(':') for x in os.environ.get('HOLDB', '').split(',') if x)]
def keys_for(mode, t, ram=None):
    if mode.startswith('peak:'):                      # A once, when the RAM byte (offset from $100000) reaches 250
        o = int(mode[5:], 16)
        if ram[o] >= 250 and t > T0 and not PRESSED[0]: PRESSED[0] = t
        return 'a' if PRESSED[0] and t < PRESSED[0] + 3 else ''
    if mode == 'mash': return 'a' if t % 4 < 2 else ''
    if mode == 'mashall': return 'abcd'[t // 4 % 4] if t % 4 < 2 else ''
    if mode.startswith('hsk'):                        # hsk[A]:N[:BUTTON] = N frames a direction, the button on the last
        f = mode.split(':'); n = int(f[1]) if len(f) > 1 else 3; btn = f[2] if len(f) > 2 else 'a'   # forward's 2nd half
        p = 7 * n + 20; i = t % p // n                                                              # (hskA: after it, alone)
        if f[0] == 'hskA' and i == 6: return btn
        if i == 5: return 'R' + (btn if t % p % n >= n // 2 and f[0] != 'hskA' else '')
        return HSK[i] if i < 5 else ''
    if mode == 'fight': return ('a' if t % 16 < 4 else 'c' if 8 <= t % 16 < 12 else '') + ('R' if t % 64 < 40 else '')
    if mode.startswith('brawl'):                      # brawl[:BTN:PERIOD]: the button mashed, walking right / left by turns
        f = mode.split(':'); b = f[1] if len(f) > 1 else 'c'; per = int(f[2]) if len(f) > 2 else 128
        return (b if t % 8 < 3 else '') + ('R' if t // per % 2 == 0 else 'L') * (t % 32 < 12)
    if mode.startswith('tap@'): n = int(mode[4:]); return 'a' if n <= t < n + 3 else ''
    return ''

def play(game, name, choice, mode, frames=1500):
    s, ev = core(game); s.load(open(f'{OUT}/{game}_sel.state', 'rb').read())
    d = f'{OUT}/{game}_{name}'; os.makedirs(d, exist_ok=True); ram = open(d + '/ram.bin', 'wb')
    for _ in range(choice): s.run(4, 'R'); s.run(8)
    s.run(4, 'a'); f0 = s.frame
    for t in range(frames):
        if t % 2 == 0 and not NOSHOT: s.shot(f'{d}/f{t:05d}.png', keys_for(mode, t, s.ram))
        else: s.run(1, keys_for(mode, t, s.ram))
        for o, v in HOLDB: s.ram[o] = v              # HOLDB=off:val,... RAM bytes held every frame (e.g. P1's life)
        ram.write(bytes(s.ram[:0x10000]))
    open(d + '/music.txt', 'w').write(''.join(f'{f - f0} {c:02X}\n' for f, c in ev))
    print(name, [(f - f0, hex(c)) for f, c in ev], 'end', bytes(s.ram[0x8700:0x8712]).hex())

if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'state': state(a[2])
    else: play(a[2], a[3], int(a[4]), a[5], int(a[6]) if len(a) > 6 else 1500)
