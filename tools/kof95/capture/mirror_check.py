#!/usr/bin/env python3
"""Throw check per character in a mirror match (X throws X). Both team records are set to X; after P2's hit knocks
P1 out, round 2 is X vs X. One MAME run records both objects every frame and takes screenshots.
Checks: (1) every victim frame resolved from its game state + raw step through X's OWN table equals the frame the
game showed; (2) a sheet of screenshots next to the same frames drawn from the data (victim in the mirror palette).
    python3 capture/mirror_check.py ID [ID ...]  -> capture/mirror/<id>.txt, <id>_shots/, sheet <id>.png"""
import os, sys, glob, subprocess, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import analyze as A, rom, export
from timeline import seqs
from neogeo.sprite_decode import r32, r16
ROUND = 1100
SHOTS = list(range(ROUND + 20, ROUND + 200, 4))
GRAB = {176, 177, 178, 179, 180, 181, 182, 183, 186, 190, 191, 192, 193, 194, 196, 197, 198, 199, 201, 202, 203, 204, 205,
        206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 220, 223, 224, 225, 226, 246, 247}

def run(cid):
    d = os.path.join(HERE, 'mirror'); os.makedirs(d, exist_ok=True)
    out, shots = os.path.join(d, f'{cid}.txt'), os.path.join(d, f'{cid}_shots')
    shutil.rmtree(shots, ignore_errors=True)
    spec = f'p2 20 45 L; p2 70 3 c; p1 {ROUND} 60 R; p1 {ROUND + 20} 3 Rc'
    s1, s2 = seqs(spec, ROUND + 220)
    poke = (f'2:108220=0,108221=1,108222=0,108223=1,10824C=0,10824D=1,' + ','.join(f'10A8{a}={cid:02X}' for a in ('43', '44', '45', '53', '54', '55')) +
            f';{ROUND - 2}:108118=01,108119=90,108318=01,108319=CC')
    env = dict(os.environ, SEQ=s1, SEQ2=s2, POKE=poke, OUT=out, SNAPS=','.join(map(str, SHOTS)), CAM_OUT=out.replace('.txt', '_cam.txt'))
    subprocess.run(['xvfb-run', '-a', 'mame', 'kof95', '-rompath', '/home/bruno/Downloads', '-state', 'a', '-window', '-sound', 'none',
                    '-nothrottle', '-skip_gameinfo', '-noplugin', 'cart_bridge', '-snapshot_directory', shots, '-autoboot_script', os.path.join(HERE, 'record.lua')],
                   env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    return out, sorted(glob.glob(os.path.join(shots, 'kof95', '*.png')))

def check(cid, out, shot_files):
    prom, _ = rom.load()
    r1, r2 = A.load(out, 1), A.load(out, 2)
    sd = {r32(prom, 0x080080 + i * 4): i for i in range(30)}
    who = lambda w: sd.get((w[0x3C // 2] << 16) | w[0x3E // 2])
    assert who(r1[ROUND][3]) == cid and who(r2[ROUND][3]) == cid, f'not a mirror match: {who(r1[ROUND][3])} vs {who(r2[ROUND][3])}'
    st = r32(prom, 0x080000 + cid * 4)
    grab = [n for n, _, _, w in r2[ROUND:] if A.state_of(w) in GRAB]
    if not grab: return {'thrown': False}
    lo = grab[0] - 1; hi = min(len(r2), lo + 160)
    ok = bad = 0; bads = []
    for n, _, _, w in r2[lo:hi]:
        s = A.state_of(w)
        rec = export.frame_at(prom, r32(prom, st + export.state_slot(prom, cid, s) * 4), w[0x74 // 2] // 6)
        if rec == A.frame_of(w): ok += 1
        else: bad += 1; bads.append((n - lo, s, w[0x74 // 2] // 6))
    return {'thrown': True, 'grab_frame': lo, 'frames': ok + bad, 'exact': ok, 'bad': bads[:5]}

if __name__ == '__main__':
    for cid in map(int, sys.argv[1:]):
        out, shots = run(cid)
        try: res = check(cid, out, shots)
        except AssertionError as e: res = {'error': str(e)}
        print(cid, rom.CAST[cid], res, 'shots', len(shots), flush=True)
