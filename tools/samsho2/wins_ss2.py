#!/usr/bin/env python3
"""Samurai Shodown II's win poses, read in the 68000 code (voice note 20261011-132148-5d29: "there are multiple win poses
in Samurai Shodown 2 ... play a random one at the end").

The round's end [code] ($7408, the round-end task, entry $746E for a KO / time over): a0 / a1 = the winner / loser
(the players $8A46 / $8A4A, swapped by $8AD5 bit 0), d0 = the winner's stick ($8A35 / $8A39 = BIOS P1 / P2 current
$10FD96 / $10FD9C, its low nibble through $15F2: opposite directions cancel) & 15; $74C0: table $74EE[d0] = up 0, down 1,
left 2, right 3, anything else $FF -> the RNG ($A84E) & 3; + 4 when the loser's +$F1 (the rounds he may still lose,
2 at the start, $7270 subq) is 0: his last round, the match won [meas: poked 0 -> subs 4-7]; the winner's action = class 6, that sub (+$E6 = 6, +$E7). The loser's: 6/8, 6/11
(round) or 6/9, 7/0 (match). So every fighter has 8 win actions, class 6 subs 0-7 of his armed table ($28310 mode 0;
mode 1, unarmed, has its own), several sharing an animation. A win pose = the distinct entry lists of those 8.

Entry routines met there [code] (commands_ss2.descriptor: per entry an animation and a routine, stepped by +$F9):
  $2C504   $2B828 velocities 0; the animation plays and holds (its $00 end command)
  $2B7F6   the animation ended (+$FA) -> the next entry (Genjuro's pipe: 207, then 244 looping)
  $364C2   Haohmaru: velocities 0, +$F9 + 1, object 52 ($439EE; its routine $4C7D8: his sword, animation 151 of his
           table looping one frame a step, born 2 px ahead and 100 px above his feet, vy -4256 / 256 px ($6A68E), gravity
           +96 / 256 a frame ($6A690, its routine adds it before the object moves))
  $364DA   (param) the sword falling (+$56 >= 0) and at or below y 96 (128 px above the floor) -> +$D4 = 1 (the sword
           ends: $4C86E), the next entry: animation 374 (the catch)
  $364FA   rts (374 holds)
  $578E0   jmp $2B7F6 (Genjuro's pipe)
  $578A2   Genjuro: velocities 0; from step 6 of 200 a count of 10, then object 30 ($578BE: a small bird, animation
           246 / 245 of his table, hopping on its own with the RNG: $4DCC2) -> the next entry; $578D2 rts
The brawler: one animation per pose (export_ss2 win_anims), its parts' steps one after the other, a wait = the last
step of the part before held that long (the sword's flight: catch_frames); Haohmaru's sword = an effect object of the
pose (export_bm anim objects: bm_afx), its rows the flight above; Genjuro's bird is not exported (a random hopper:
named in poses()).

    python3 wins_ss2.py [CHAR ...]          the decode (default the brawler's four)
    python3 wins_ss2.py check [CHAR ...]    every stick x round / match win played in our emulator vs the decode
                                            (the winner's +$66 sequence; Haohmaru's sword: its height per frame and
                                            the catch frame)"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss2, neo2 as N
import commands_ss2 as K

CAST = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17, 'hanzo': 2}
STICK = {0: 'U', 1: 'D', 2: 'L', 3: 'R'}                 # $74EE: the stick bit that picks sub 0-3

def stick_table():
    """$74EE[stick & 15] -> sub (0-3) or None (the RNG), [code]"""
    return {k: (None if N.u8(0x74EE + k) == 0xFF else N.u8(0x74EE + k)) for k in range(16)}

# the sword (object 52, $4C7D8) [code]
SWORD = dict(anim=151, dx=2, dy=-100, vy=N.s16(0x6A68E), g=N.s16(0x6A690), catch_y=96)

def sword_flight():
    """(heights, catch): the sword's height above the floor on each frame from the one it is born on (frame 0: it has
    moved once already: the objects run after the players, its first move in its birth frame), and the frame Haohmaru's
    next entry (374, the catch) starts on. [code]: the objects' move adds vy (8.8) to y (down, the floor at 224), then
    its routine ($4C828) adds the gravity to vy; his routine ($364DA, run before the objects) sees the frame before's
    sword: vy >= 0 and y >= 96 -> +$F9 + 1, the animation set the frame after. [meas] in check(): identical"""
    y = (224 + SWORD['dy']) << 8; vy = SWORD['vy']; out = []
    while True:
        y += vy; vy += SWORD['g']
        out.append(224 - (y >> 8))
        if vy >= 0 and (y >> 8) >= SWORD['catch_y']: return out, len(out) + 1

ROUTINES = {0x2C504: 'hold', 0x2B7F6: 'end_next', 0x364C2: 'sword', 0x364DA: 'sword_wait', 0x364FA: 'hold',
            0x578A2: 'bird', 0x578BE: 'bird_count', 0x578D2: 'hold', 0x578E0: 'end_next', 0x578E6: 'hold'}

def poses(ch, mode=0):
    """[{'subs': [class 6 subs], 'parts': [{'anim', 'wait': 'end' | 'sword' | None}], 'sword': bool, 'skipped': [..]}]
    in sub order (the first sub naming each)"""
    out = {}
    for sub in range(8):
        d = K.descriptor(ch, mode, 6, sub)
        ents = [(h, w) for _, h, w in d['entries']]
        key = tuple(ents)
        if key in out: out[key]['subs'].append(sub); continue
        parts, sword, skipped = [], False, []
        for h, w in ents:
            r = ROUTINES.get(h)
            assert r, f'char {ch} class 6 sub {sub}: routine ${h:X} not read'
            if not w & 0x8000: parts.append({'anim': w & 0x3FF, 'wait': None})
            if r == 'end_next': parts[-1]['wait'] = 'end'
            elif r == 'sword': sword = True; parts[-1]['wait'] = 'sword'
            elif r == 'bird': skipped.append('object 30 (a small bird hopping at random, $4DCC2)')
        out[key] = {'subs': [sub], 'parts': parts, 'sword': sword, 'skipped': skipped}
    return list(out.values())

def frames_of(ch, a):
    return sum(s['ticks'] + 1 for s in ss2.parse_anim(ch, a, 400))

# ---- the check in our emulator ---------------------------------------------------------------------------------------
STATES = {'haohmaru': '/data/neogeo_dict/samsho2/cap/p1_00.state', 'genjuro': '/data/neogeo_dict/samsho2/cap/p1_12.state',
          'kuroko': '/data/neogeo_dict/samsho2/cap/p1_17.state', 'hanzo': '/data/neogeo_dict/samsho2/cap/p1_02.state'}
NF = 900
def u16(b, o): return b[o] << 8 | b[o + 1]

def play(name, stick, match, d):
    """P1 wins by time over (tools/brawler/wins184.py's setup: P2 50 px ahead, P1's A lands, the clock at 1), the stick
    held from frame 200 (the round decided, the win action not yet set); match: P2's +$F1 = 0 (his last round)"""
    import cap_ss2 as C, shutil
    st = STATES[name]
    shutil.rmtree(d, ignore_errors=True)
    C.run(d, '4:-', load=st, vram=False, frames=[1], sndlog=False)
    r = C.ram(d, 1); a1, a2 = C.players(r)
    x = u16(r, a1 - 0x100000 + 0x4E) + 50
    pk = [f'{f}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for f in range(1, 4)] + ['40:100AC6=01']
    if match: pk += [f'{f}:{a2 + 0xF1:X}=00' for f in (5, 100, 199)]
    shutil.rmtree(d, ignore_errors=True)
    seq = '10:-,3:a,187:-,' + (f'{NF - 200}:{stick}' if stick else f'{NF - 200}:-')
    C.run(d, seq, load=st, vram=False, frames=range(1, NF), pokes=';'.join(pk), sndlog=False)
    seqa, sword = [], []
    for f in range(1, NF):
        r = C.ram(d, f)
        if r is None: continue
        a1, _ = C.players(r)
        a = u16(r, a1 - 0x100000 + 0x66)
        if not seqa or seqa[-1][0] != a: seqa.append([a, f])
        for o in range(0x2000, 0xA000, 0x20):            # the sword: an object owned by P1 (+$CC) on animation 151
            if r[o + 0xCC:o + 0xD0] == a1.to_bytes(4, 'big') and u16(r, o + 0x66) == SWORD['anim'] and u16(r, o + 0x64) == 0:
                y = u16(r, o + 0x50); sword.append([f, 224 - (y - 0x10000 if y & 0x8000 else y)])
                break
        os.remove(f'{d}/ram{f}.bin')
    return seqa, sword

def check(names):
    tab = stick_table(); ok = True; res = {}
    for name in names:
        ch = CAST[name]; ps = poses(ch)
        by_sub = {s: p for p in ps for s in p['subs']}
        for match in (0, 1):
            for k in range(4):
                sub = k + 4 * match; p = by_sub[sub]
                got, sword = play(name, STICK[k], match, f'/data/tmp/winposes/cap/{name}_{sub}')
                anims = [a for a, _ in got]
                want = [x['anim'] for x in p['parts']]
                i = next((j for j in range(len(anims)) if anims[j:j + len(want)] == want), None)
                good = i is not None
                line = f'{name} sub {sub} ({"match" if match else "round"}, stick {STICK[k]}): decode {want}, game {got[-4:]}'
                if good and p['sword']:
                    t0, t1 = got[i][1], got[i + 1][1]
                    fl, catch = sword_flight()
                    born = sword[0][0] if sword else None
                    hs = [h for _, h in sword][:len(fl)]
                    good = born == t0 and hs == fl and t1 - t0 == catch
                    line += (f'; sword born with 198 ({born == t0}), heights {len(fl)} frames {"identical" if hs == fl else "DIFFER"},'
                             f' 374 {t1 - t0} frames after 198 (decode {catch})')
                print(('OK   ' if good else 'FAIL ') + line, flush=True)
                ok &= good
                res[f'{name}:{sub}'] = {'anims': got, 'sword': sword}
    os.makedirs('/data/tmp/winposes', exist_ok=True)
    json.dump(res, open('/data/tmp/winposes/check.json', 'w'))
    print('ALL OK' if ok else 'FAILED')
    return ok

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == 'check': sys.exit(0 if check(a[1:] or list(CAST)) else 1)
    print('stick table $74EE:', {k: v for k, v in stick_table().items() if v is not None})
    print('sword flight (height per frame):', sword_flight())
    for name in a or list(CAST):
        for p in poses(CAST[name]):
            print(name, 'subs', p['subs'], [(x['anim'], x['wait'], frames_of(CAST[name], x['anim'])) for x in p['parts']],
                  'sword' if p['sword'] else '', p['skipped'] or '')
