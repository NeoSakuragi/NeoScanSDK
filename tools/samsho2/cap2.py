#!/usr/bin/env python3
"""Samurai Shodown II captures in our emulator (emu/neogeo_sdl --capture) from a saved state
(default /data/neogeo_dict/samsho2/cap/vs.state: Haohmaru vs Haohmaru, idle, round 1).
    run(seq1, seq2='', ranges=[(addr, len)], extra={}, load=VS) -> [{addr: bytes}] one dict per frame (frame 0 = the load, no dump)"""
import os, subprocess, glob, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/samsho2.neo'
VS = '/data/neogeo_dict/samsho2/cap/vs.state'

def nframes(seq): return sum(int(x.split(':')[0]) for x in seq.split(',') if x)

def parse(txt):
    out = []
    for w in txt.split():
        if ':' in w: continue
        try: out.append(bytes.fromhex(w))
        except ValueError: pass
    return b''.join(out)

def run(seq1, seq2='', ranges=((0x100000, 0x10000),), extra=None, load=VS, pokes=None, keep=None, frames=None):
    """per-frame dumps of the given RAM ranges; `frames` limits which frames are dumped (default all)"""
    n = nframes(seq1)
    d = keep or tempfile.mkdtemp(dir='/data/tmp')
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(f'{d}/cap.txt*'): os.remove(f)
    fr = list(frames) if frames is not None else range(1, n)
    rd = ';'.join(f'{f}:{a:X}:{l:X}' for f in fr for a, l in ranges)
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2 or f'{n}:-', OUT=f'{d}/cap.txt', RAMDUMP=rd, **(extra or {}))
    if load: env['LOAD'] = load
    if pokes: env['POKE'] = pokes
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    rows = {}
    for f in fr:
        row = {}
        for a, l in ranges:
            p = glob.glob(f'{d}/cap.txt.ram{f}_{a:X}') + glob.glob(f'{d}/cap.txt.ram{f}_{a:x}') + glob.glob(f'{d}/cap.txt.ram{f}_{a:06X}')
            if p: row[a] = parse(open(p[0]).read())
        if row: rows[f] = row
    if not keep: shutil.rmtree(d)
    return rows

def u16(b, o): return b[o] << 8 | b[o + 1]
def s16(b, o): v = u16(b, o); return v - 65536 if v & 0x8000 else v
def u32(b, o): return u16(b, o) << 16 | u16(b, o + 2)
