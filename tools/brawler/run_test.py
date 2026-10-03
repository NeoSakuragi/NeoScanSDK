#!/usr/bin/env python3
"""Play an input script on the brawler ROM in our emulator (headless capture mode) and make a contact sheet.

    python3 run_test.py OUT.png "p1 0 40 R; p1 40 3 a; ..." [--snaps 10,20,...] [--every N] [--rom path]

Times are frames after the game starts (BOOT frames after power-on). Events use tools/kof95/capture/timeline.py syntax:
"who start frames keys" (who p1/p2; keys from U D L R a b c d)."""
import argparse, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
from timeline import seqs
from PIL import Image
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
ROM = os.path.join(HERE, '..', '..', 'examples', 'brawler', 'brawler.neo')
BOOT = 380                                     # frames until game_tick runs (BIOS + init)

def run(script, snaps, rom=ROM, length=None):
    events = []
    for e in [x.strip() for x in script.split(';') if x.strip()]:
        w, a, n, k = e.split(); events.append(f'{w} {int(a) + BOOT} {n} {k}')
    end = BOOT + (length or max(int(e.split()[1]) + int(e.split()[2]) for e in events) + 60)
    s1, s2 = seqs('; '.join(events), end)
    d = tempfile.mkdtemp(prefix='bmtest_', dir='/tmp/claude-1000')
    env = dict(os.environ, SEQ=s1, SEQ2=s2, SNAPS=','.join(str(BOOT + f) for f in snaps), SNAPDIR=d, OUT='/dev/null')
    subprocess.run([NGSDL, rom, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    return [os.path.join(d, f'snap_{BOOT + f}.ppm') for f in snaps]

def sheet(paths, out, cols=5):
    ims = [Image.open(p) for p in paths if os.path.exists(p)]
    w, h = ims[0].size
    W = Image.new('RGB', (cols * (w + 6), ((len(ims) + cols - 1) // cols) * (h + 6)), 'white')
    for k, im in enumerate(ims): W.paste(im, ((k % cols) * (w + 6), (k // cols) * (h + 6)))
    W.save(out)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('script')
    ap.add_argument('--snaps', default=''); ap.add_argument('--every', type=int, default=0); ap.add_argument('--until', type=int, default=200)
    ap.add_argument('--rom', default=ROM)
    a = ap.parse_args()
    snaps = [int(x) for x in a.snaps.split(',') if x] or list(range(a.every or 20, a.until + 1, a.every or 20))
    sheet(run(a.script, snaps, a.rom), a.out)
