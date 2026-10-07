#!/usr/bin/env python3
"""TODO #191 (b): SS2's rage palette, measured in our emulator. P1 = CHAR from cap/p1_CC.state, its POW (+$F0) poked
to 31 and the pending POW (+$114) to 1 at frame LEAD (rage_ss2.py's path: the game's own code fills it the next frame
and plays anim 140); per frame P1's object (animation, step, its palette bytes +$81 / +$82 / +$83, the rage time +$B8)
and palette RAM (P1's colour palettes 16-23).
    python3 ragepal_ss2.py [CHAR ...]   -> /data/neogeo_dict/samsho2/ragepal.json: per fighter, per frame of anim 140,
                                           the step and the 8 palettes as shown (+ the colour set's own blocks for ref)
The code [code]: $25D3E (every frame) +$81 = (P2: 8) + $25D72[+$F0] (0 below 10 POW, 1 below 20, 2 from 20): the body's
palette offset within the fighter's 8; palette RAM 16-23 is the colour set block $FD10[$FCA4[char] + 18 * set]
($FCB4) and the rage colours are what the palette RAM holds while anim 140 plays (measured here)."""
import os, sys, json, glob, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_ss2 as C, ss2

STA = '/data/neogeo_dict/samsho2/cap'
OUT = '/data/neogeo_dict/samsho2/ragepal.json'
TMP = '/data/tmp/ss2t191/ragepal'
LEAD, N = 20, 130

def hx(p):
    return bytes.fromhex(open(p).read().strip()) if os.path.exists(p) else None

def run(char):
    state = f'{STA}/p1_{char:02d}.state'
    d0 = f'{TMP}/probe'; C.run(d0, '3:-', load=state, vram=False, sndlog=False)
    r = C.ram(d0, 1); a1, a2 = C.players(r)
    out = f'{TMP}/ss2_{char:02d}'; os.makedirs(out, exist_ok=True)
    for f in glob.glob(f'{out}/cap.txt*') + glob.glob(f'{out}/pal*'): os.remove(f)
    pokes = f'{LEAD}:{a1 + 0xF0:X}=1F,{a1 + 0x114:X}=01'
    rd = ';'.join(f'{f}:{a1:X}:120' for f in range(1, N))
    env = dict(os.environ, SEQ=f'{N}:-', SEQ2=f'{N}:-', OUT=f'{out}/cap.txt', LOAD=state, RAMDUMP=rd, POKE=pokes,
               PALDUMP=';'.join(f'{f}:{out}/pal{f}.bin' for f in range(1, N)))
    subprocess.run([C.NGSDL, C.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    rows = []
    idx = {}
    # the active palette bank (PALDUMP holds both: 2 x 4096 words): the one whose P1 palettes are his colour set
    p0 = open(f'{out}/pal1.bin', 'rb').read()
    cs = [ss2.fighter_palettes(char, s) for s in range(2)]
    bank = next(k for k in (0, 1) if any([[p0[2 * (4096 * k + 16 * (16 + q) + j)] << 8 | p0[2 * (4096 * k + 16 * (16 + q) + j) + 1]
                                           for j in range(16)] for q in range(8)] == c for c in cs))
    for f in range(1, N):
        o = hx(f'{out}/cap.txt.ram{f}_{a1:06X}')
        p = f'{out}/pal{f}.bin'
        if o is None or not os.path.exists(p): continue
        pal = open(p, 'rb').read()
        a = C.u16(o, 0x66)
        if a not in idx: idx[a] = {s['addr']: i for i, s in enumerate(ss2.parse_anim(char, a, 400))}
        side = 8 if o[0xEF] else 0
        pals = [[pal[2 * (4096 * bank + 16 * (16 + side + q) + k)] << 8 | pal[2 * (4096 * bank + 16 * (16 + side + q) + k) + 1] for k in range(16)] for q in range(8)]
        rows.append(dict(f=f, anim=a, step=idx[a].get(C.u32(o, 0x6C)), cls=o[0xE6], act=o[0xE7], pow=o[0xF0], p81=o[0x81],
                         p82=o[0x82], p83=o[0x83], time=C.u16(o, 0xB8), pals=pals))
    return rows

if __name__ == '__main__':
    chars = [int(a) for a in sys.argv[1:]] or [0, 12, 17]
    db = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for c in chars:
        rows = run(c)
        pose = [x for x in rows if x['cls'] == 0 and x['act'] == 46]
        base = [ss2.fighter_palettes(c, s) for s in range(2)]
        db[str(c)] = dict(name=ss2.NAMES[c], rows=rows, pose=[x['f'] for x in pose], colour_sets=base)
        changed = sorted({q for x in pose for q in range(8) if x['pals'][q] != base[0][q]})
        body = [x['pals'][x['p81']] for x in pose]          # the body's colours as shown: palette 16 + +$81
        db[str(c)]['body'] = body[0]
        print(c, ss2.NAMES[c], 'pose frames', len(pose), 'p81', sorted({x['p81'] for x in pose}), 'palette RAM changed vs the colour set',
              changed, 'distinct during pose', len({json.dumps(x['pals']) for x in pose}), 'body', ' '.join('%04x' % v for v in body[0]))
    json.dump(db, open(OUT, 'w'))
