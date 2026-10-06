#!/usr/bin/env python3
"""A vs state with P1 = Kuroko (table 17, the hidden referee: not on the select grid) and P2 = Haohmaru, both idle at the
start of round 1 -> /data/neogeo_dict/samsho2/cap/p1_17.state.
How: mkvs.py's boot with the cursor on Haohmaru's square; P1's selected character, byte $100D0B on the select screen
(found by picking Haohmaru / Genjuro / Kyoshiro: 0 / 12 / 6 there [meas]; copied to $100AD9 when the pick is made),
written 17 from the press of A on until the fight is set up. The game's own unlock (not traced) is not used: the
state only serves the captures (moves/17.json)."""
import os, subprocess
import boot, cap_ss2 as C
STA = '/data/neogeo_dict/samsho2/cap'

def make(frames=1900, save=1800):
    p1, p2 = boot.lanes(frames)
    for f in range(815, frames):
        if f < 900 or f >= 960: p1[f] = p2[f] = "-"
    out = '/data/tmp/samsho2/vs_kuroko'; os.makedirs(out, exist_ok=True)
    tmp = f'{out}/p1.state'
    pokes = ';'.join(f'{f}:100D0B=11' for f in range(880, 1000)) + ';' + ';'.join(f'{f}:100AD9=11' for f in range(945, 1000))
    env = dict(os.environ, SEQ=boot.rle(p1), SEQ2=boot.rle(p2), OUT=f'{out}/b.txt', SAVE=f'{save}:{tmp}', POKE=pokes,
               DUMP=f'{save}:{out}/r.bin', SNAPS=f'{save}', SNAPDIR=out)
    subprocess.run([boot.NGSDL, boot.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    r = open(f'{out}/r.bin', 'rb').read()
    a1, a2 = C.players(r)
    o1, o2 = C.obj(r, a1), C.obj(r, a2)
    assert o1['table'] == 17, ('P1 is not Kuroko', o1)
    st = f'{STA}/p1_17.state'; os.replace(tmp, st)
    return o1, o2, st

if __name__ == '__main__':
    o1, o2, st = make(); print('P1 table', o1['table'], 'anim', o1['anim'], 'P2 table', o2['table'], st)
