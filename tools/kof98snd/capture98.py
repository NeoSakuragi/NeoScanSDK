#!/usr/bin/env python3
"""SNK Sound Driver ground truth in our emulator (games98.py: Kizuna Encounter; KOF98's captures are MAME's, ymtap.lua):
the Geolith core with the Z80 port tap of tools/makoto3/capture.py (class Sound), logging the ymtap.lua format.

    python3 capture98.py --game kizuna OUT FRAMES [--send F:CMD,...] [--block F]
    python3 capture98.py --game kizuna --songs DIR [CMD ...]
                                 every music command (or these): DIR/cap_XX.txt, power-on, the game's commands
                                 blocked from frame BLOCK on, the song sent at SEND (games98.GAMES), length from
                                 song98.py (to the loop point or the end + 15 %)

Lines as ymtap.lua with IRQ=1: "f <frame>", "a/b <reg> <val>" = YM2610 port A / B write, "i <status>" = the ISR's
read of status port $04 (the driver's only read of it), "c <cmd>" = the Z80 reads a sound command (8-bit here,
the 68000's 16-bit word in MAME's captures), "c <cmd> blocked" = a game command after BLOCK, replaced by $00
(Kizuna's NMI handler ignores $00 before touching its ring, $006C); "s <cmd>" = a SEND command.
"q 1" / "q 2" follow an "i" line with the timer-A bit set: q 1 = this interrupt runs the sequencer (the ISR's
re-entry guard, games98 'guard', is 0 when the status is read), q 2 = it arrived while the previous ISR still runs
(the guard is non-zero: the driver drops it)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'makoto3'))
from games98 import GAMES, music_cmds
import capture as mk

GAME = 'kizuna'

class Sound(mk.Sound):
    def __init__(self):
        g = GAMES[GAME]
        super().__init__(rom=g['rom'], work=g['dir'] + '/save')
        self.guard = g['guard']
    def _tap(self, write, port, v):
        r = super()._tap(write, port, v)
        if not write and port & 0xFF == 4 and v & 1:
            self._line('q 1\n' if self.z(self.guard) == 0 else 'q 2\n')
        return r

def capture(out, frames, send=(), block=None, wav=None):
    """power on, log every frame up to `frames`; send = [(frame, cmd)]; block = frame from which the game's own
    commands are replaced by $00"""
    s = Sound()
    s.out = open(out, 'w'); s.block = block
    if wav: s.wav = open(wav, 'wb')
    todo = sorted(send)
    while s.frame < frames:
        while todo and todo[0][0] <= s.frame: s.send(todo.pop(0)[1])
        s.run()
    s.out.close()
    if s.wav: s.wav.close()
    return s

def frames_for(data, cmd):
    """capture length: song98.py's ticks to the loop point or the end, + 15 %"""
    from song98 import Song
    s = Song(data, cmd).run(ticks=30000)
    running = any(c.status for c in s.ch)
    n = s.tick if not running else max((v[0] + v[1] for v in s.loop_at.values()), default=min(s.tick, 3000))
    hz = 166.83 * s.tempo / 208
    return int(n / hz * 59.19 * 1.15) + 120

def capture_songs(out_dir, cmds=None):
    import subprocess
    g = GAMES[GAME]
    m1 = open(g['m1'], 'rb').read()
    os.makedirs(out_dir, exist_ok=True)
    for cmd in cmds or music_cmds(m1):
        n = g['send'] + frames_for(m1, cmd)
        subprocess.run([sys.executable, __file__, '--game', GAME, os.path.join(out_dir, f'cap_{cmd:02X}.txt'), str(n),
                        '--block', str(g['block']), '--send', f'{g["send"]}:{cmd:02X}'], check=True)
        print(f'${cmd:02X}: {n} frames', flush=True)

if __name__ == '__main__':
    a = sys.argv
    if a[1] == '--game': GAME = a[2]; a = a[:1] + a[3:]
    if a[1] == '--songs': capture_songs(a[2], [int(x, 16) for x in a[3:]]); sys.exit()
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    send = [(int(f), int(c, 16)) for f, c in (x.split(':') for x in opt('--send').split(','))] if opt('--send') else []
    capture(a[1], int(a[2]), send, int(opt('--block')) if opt('--block') else None, opt('--wav'))
