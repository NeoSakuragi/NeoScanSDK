#!/usr/bin/env python3
"""SDC_NGSS ground truth in our emulator (Double Dragon, Super Dodge Ball): makoto3's capture core (the Geolith core
with a Z80 port tap, driven from Python), the same line format (tools/makoto3/capture.py: "f", "a", "b", "c", "s").

    python3 capture_ngss.py [--game doubledr] OUT FRAMES [--send F:CMD,...] [--block F]
    python3 capture_ngss.py [--game doubledr] --songs DIR [CMD ...]
                     every music command (or these): DIR/cap_XX.txt, power-on, the game's commands blocked from frame
                     BLOCK on, the song sent at SEND (games_ngss.GAMES), length from song_ngss.py (to the loop point
                     or the end + 15 %)

This driver never reads the YM2610 status: its interrupt handler ($0236) only writes $27 = $2A (timer B flag reset
and reload) and counts. That write, "a 27 2A", is the interrupt marker: regs_ngss.py cuts the capture into main-loop
passes there. A blocked command is replaced by $00, which the NMI handler ignores before storing it ($006D)."""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'makoto3'))
from games_ngss import GAMES, m1_path, music_cmds

GAME = 'doubledr'

def capture(out, frames, send=(), block=None, wav=None):
    import capture as mk                                     # makoto3's tap core
    g = GAMES[GAME]
    s = mk.Sound(g['rom'], work=g['dir'] + '/save')
    s.out = open(out, 'w'); s.block = block
    if wav: s.wav = open(wav, 'wb')
    todo = sorted(send)
    while s.frame < frames:
        while todo and todo[0][0] <= s.frame: s.send(todo.pop(0)[1])
        s.run()
    s.out.close()
    if s.wav: s.wav.close()

def frames_for(data, cmd):
    """capture length: song_ngss.py's passes to the loop point (every looping channel has jumped back once) or the
    end, + 15 %"""
    from song_ngss import loop_passes, PASS_HZ
    n, _ = loop_passes(data, cmd)
    return int(n / PASS_HZ * 59.19 * 1.15) + 120

def capture_songs(out_dir, cmds=None):
    g = GAMES[GAME]
    m1 = open(m1_path(GAME), 'rb').read()
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
