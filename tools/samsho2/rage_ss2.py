#!/usr/bin/env python3
"""Samurai Shodown II: the rage-full moment (TODO #189), measured in our emulator for every fighter.
The game's code [code]: $25CD2 (per player, every frame) adds the pending POW (+$114, signed) to +$F0 one point a frame;
at +$F0 = 32 it sets the rage time +$B8 = word $6C7CA[+$64 * 2] (frames), clears +$114, sets +$11C bit 0 and clears
+$11D bit 0; the player's action becomes class 0 action 46 (+$E6 = $002E) = descriptor entries
[$2C4E4, anim 140 (armed) / 141 (unarmed), voice index] whose handler returns to idle (+$E6 = 0) at the animation's
end flag (+$FA); the idle is then the rage idle (anim 2).
Here: P1 = CHAR from cap/p1_CC.state, its +$F0 poked to 31 and +$114 to 1 at frame LEAD (the game's own code fills it
the next frame: the same path as a hit's POW), RAM / sound / screenshots per frame.
    python3 rage_ss2.py [CHAR ...]          -> /data/neogeo_dict/samsho2/rage.json + the table on stdout
    python3 rage_ss2.py --hits              Haohmaru: +$F0 poked to 28, P2 (Haohmaru) next to him slashes him until full
Screenshots: /data/tmp/rage189/ss2_CC/snap_<frame>.ppm."""
import os, sys, json, glob, subprocess
import cap_ss2 as C, ss2

STA = '/data/neogeo_dict/samsho2/cap'
OUT = '/data/neogeo_dict/samsho2/rage.json'
TMP = '/data/tmp/rage189'
LEAD, N = 20, 150
CHARS = [c for c in range(18) if c not in (10, 16)]          # the 15 playables + Kuroko (no Mizuki state)

def hx(p):
    return bytes.fromhex(open(p).read().strip()) if os.path.exists(p) else None

def run(char, hits=False):
    state = f'{STA}/p1_{char:02d}.state'
    d0 = f'{TMP}/probe'; C.run(d0, '3:-', load=state, vram=False, sndlog=False)
    r = C.ram(d0, 1); a1, a2 = C.players(r)
    out = f'{TMP}/ss2_{char:02d}{"_hits" if hits else ""}'; os.makedirs(out, exist_ok=True)
    for f in glob.glob(f'{out}/cap.txt*') + glob.glob(f'{out}/snap_*'): os.remove(f)
    if hits:                                                   # P2 next to P1 (56 px), P1 at 28: P2 slashes (A)
        x = C.s16(r, a1 - 0x100000 + 0x4E) + 56
        pokes = f'1:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X};1:{a1 + 0xF0:X}=1C'
        seq2 = f'{LEAD}:-,' + ','.join(['3:a,40:-'] * 8)
        n = 400
    else:
        pokes = f'{LEAD}:{a1 + 0xF0:X}=1F,{a1 + 0x114:X}=01'; seq2 = ''; n = N
    rd = ';'.join(f'{f}:{a1:X}:120;{f}:108AC0:20' for f in range(1, n))
    env = dict(os.environ, SEQ=f'{n}:-', SEQ2=seq2 or f'{n}:-', OUT=f'{out}/cap.txt', LOAD=state, RAMDUMP=rd,
               SNDLOG=f'{out}/snd.txt', POKE=pokes, SNAPS=','.join(map(str, range(1, n))), SNAPDIR=out)
    subprocess.run([C.NGSDL, C.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    snd = {}
    for line in open(f'{out}/snd.txt'):
        snd.setdefault(int(line[:5]), []).append(int(line[6:8], 16))
    rows = []
    for f in range(1, n):
        o = hx(f'{out}/cap.txt.ram{f}_{a1:06X}')
        if o is None: continue
        rows.append(dict(f=f, rage=o[0xF0], pend=C.s16(o, 0x114), time=C.u16(o, 0xB8), cls=o[0xE6], act=o[0xE7],
                         anim=C.u16(o, 0x66), mode=o[0xF4], snd=snd.get(f, [])))
    full = next((x['f'] for x in rows if x['rage'] == 32), None)
    pose = [x for x in rows if x['cls'] == 0 and x['act'] == 46]
    res = dict(char=char, name=ss2.NAMES[char], full=full, out=out)
    if pose:
        res.update(start=pose[0]['f'], end=pose[-1]['f'], frames=len(pose), anim=pose[0]['anim'], time=pose[0]['time'],
                   after=next((x['anim'] for x in rows if x['f'] > pose[-1]['f'] + 2), None),
                   snd=[(x['f'] - pose[0]['f'], v) for x in rows if pose[0]['f'] <= x['f'] <= pose[-1]['f'] for v in x['snd']])
    if hits:
        res['hits'] = [(x['f'], x['rage'], x['cls'], x['act'], x['anim']) for x in rows if x['f'] < (full or n) + 3
                       and x['rage'] != next((y['rage'] for y in rows if y['f'] == x['f'] - 1), None)]
    return res

if __name__ == '__main__':
    if '--hits' in sys.argv:
        print(json.dumps(run(0, hits=True)))
        sys.exit()
    chars = [int(a) for a in sys.argv[1:]] or CHARS
    db = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for c in chars:
        res = run(c); db[str(c)] = res
        st = ss2.parse_anim(c, res.get('anim', 140))
        res['rom_frames'] = sum(s['ticks'] + 1 for s in st)
        res['rom_sounds'] = [(sum(t['ticks'] + 1 for t in st[:k]), v) for k, s in enumerate(st) for n_, v, *_ in
                             [x for x in s['cmds'] if x[0] in ('sound', 'sound_pan')]]
        print(c, res['name'], 'full', res['full'], 'pose', res.get('start'), '-', res.get('end'), res.get('frames'), 'frames anim',
              res.get('anim'), 'rom', res['rom_frames'], 'rage time', res.get('time'), 'then anim', res.get('after'),
              'sounds', res.get('snd'), 'rom sounds', res['rom_sounds'])
    json.dump(db, open(OUT, 'w'), indent=1)
