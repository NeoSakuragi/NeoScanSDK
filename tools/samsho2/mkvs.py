#!/usr/bin/env python3
"""Vs states: P1 = the character at select-grid position (row, col) (cursor moved with the stick, A at 901),
P2 = Haohmaru, both idle at the start of round 1 -> /data/neogeo_dict/samsho2/cap/p1_NN.state (NN = the character
id read back from the P1 object +$64).
    python3 mkvs.py ROW COL [ROW COL ...]      the grid is 2 rows from Haohmaru's square (row 0, column 3)"""
import os, sys, subprocess
import boot, cap_ss2 as C
STA = '/data/neogeo_dict/samsho2/cap'

def make(row, col, frames=1900, save=1800):
    p1, p2 = boot.lanes(frames)
    for f in range(815, frames):
        if f < 900 or f >= 960: p1[f] = p2[f] = "-"
    f = 835
    moves = (['D'] if row else []) + (['R' if col > 0 else 'L'] * abs(col))
    for m in moves:                                   # 8 frames held, 8 released (3-frame taps are not seen)
        for k in range(f, f + 8): p1[k] = m
        f += 16
    out = f'/data/tmp/samsho2/vs_{row}{col}'
    os.makedirs(out, exist_ok=True)
    tmp = f'{out}/p1.state'
    env = dict(os.environ, SEQ=boot.rle(p1), SEQ2=boot.rle(p2), OUT=f'{out}/b.txt', SAVE=f'{save}:{tmp}',
               DUMP=f'{save}:{out}/r.bin', SNAPS=f'{save}', SNAPDIR=out)
    subprocess.run([boot.NGSDL, boot.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    r = open(f'{out}/r.bin', 'rb').read()
    a1, a2 = C.players(r)
    o1, o2 = C.obj(r, a1), C.obj(r, a2); o1['base'], o2['base'] = a1, a2
    st = f'{STA}/p1_{o1["table"]:02d}.state'
    os.replace(tmp, st)
    return o1, o2, st

if __name__ == '__main__':
    a = list(map(int, sys.argv[1:]))
    for row, col in zip(a[0::2], a[1::2]):
        o1, o2, st = make(row, col); print(row, col, 'P1 table', o1['table'], o1['anim'], hex(o1['base']), 'P2', o2['table'], o2['anim'], hex(o2['base']), st)
