#!/usr/bin/env python3
"""Samurai Shodown IV captures in our emulator (emu/neogeo_sdl --capture) from the 'vs' state (Haohmaru vs Haohmaru,
/data/neogeo_dict/samsho4/cap/vs.state): per frame the P1 / P2 objects ($103600 / $103A00, $100 bytes each) or the
whole object pool ($100000-$103FFF: projectiles, effects and the weapon are pool objects).

    rows = run(seq1, seq2='', pool=False, extra={}, pokes=None) -> [{'p1': bytes, 'p2': bytes, 'pool': bytes | None}]"""
import os, subprocess, glob, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/samsho4.neo'
VS = '/data/neogeo_dict/samsho4/cap/vs.state'
P1, P2 = 0x103600, 0x103A00

def nframes(seq): return sum(int(x.split(':')[0]) for x in seq.split(',') if x)

def parse(txt):
    out = []
    for w in txt.split():
        if ':' in w: continue
        try: out.append(bytes.fromhex(w))
        except ValueError: pass
    return b''.join(out)

def run(seq1, seq2='', pool=False, extra=None, load=VS, pokes=None, keep=None):
    n = nframes(seq1)
    d = keep or tempfile.mkdtemp(dir='/data/tmp')
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(f'{d}/cap.txt*'): os.remove(f)
    rd = ';'.join(f'{f}:100000:8000' if pool else f'{f}:103600:500' for f in range(n))
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=load, RAMDUMP=rd, **(extra or {}))
    if pokes: env['POKE'] = pokes
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    rows = []
    for f in range(n):
        p = glob.glob(f'{d}/cap.txt.ram{f}_*')
        if not p: continue                              # frame 0 has no dump (the load frame)
        b = parse(open(p[0]).read())
        if pool: rows.append({'p1': b[0x3600:0x3700], 'p2': b[0x3A00:0x3B00], 'pool': b})
        else: rows.append({'p1': b[0:0x100], 'p2': b[0x400:0x500], 'pool': None})
    if not keep: shutil.rmtree(d)
    return rows

def u16(b, o): return b[o] << 8 | b[o + 1]
def s16(b, o): v = u16(b, o); return v - 65536 if v & 0x8000 else v
def u32(b, o): return u16(b, o) << 16 | u16(b, o + 2)
def summary(o):
    return dict(anim=u16(o, 0x22), step=u32(o, 0x4E), ticks=o[0x54], x=s16(o, 0x2E), y=s16(o, 0x32), z=s16(o, 0x36),
                flip=o[0x0F] & 2, st=u16(o, 0x20))
