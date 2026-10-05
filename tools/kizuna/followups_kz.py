#!/usr/bin/env python3
"""Kim's multipart moves played by Kizuna Encounter in our emulator (emu/neogeo_sdl --capture, the 'vs' state), whiff
and connect, P2 (Hayate) pinned at its start place only until the move starts (it is pushed / launched freely after):
the parts of each move, what triggers each part, every step of attacker and victim, objects (the Phoenix's flames).

    python3 followups_kz.py [OUT.json] [names...]     (default /data/neogeo_dict/kizuna/kim_followups.json)

Per frame: P1 / P2 [anim n, step, x, y (up +), flip, step pointer, life, zoom, char, cam x, tick acc +$48 word,
cancel window +$10C bit 3, follow-up command +$1EB, cam y $10965E], the objects that were not there at the start [slot, anim id, step,
x, y, flip, step pointer, name], sound bytes.

How Kizuna triggers a follow-up [code $2D948, the command scan of the COMND task]: a command list entry with condition
bit 3 is accepted only while the fighter's +$10C bit 3 (the cancel window) and +$10E bit 0 are set and its +$1EB (the
move's own command) equals the entry's command: the move's code opens the window, the stick + button pattern is the
entry's (commands_kz.py: Kim's 236C $25 cond 0008 / 1008, 2C $28 cond 0028 = down+C in the air). The window and the
part that follows are measured here (MOVES)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_kz as cap

OUT = '/data/neogeo_dict/kizuna/kim_followups.json'
LOW = '108313=14,108315=14,108391=14'                 # P1 life 20 of 192: the desperation moves (cond life <= 96)
NEAR, FAR = 300, 560
M236C = '3:D,3:DR,3:R,3:c,3:c,'
M28C = '40:D,3:Uc,3:Uc,'
RECIPES = {   # name: (P2 x, P1 inputs, pokes every frame)
    '236C_w': (FAR, '2:-,' + M236C + '150:-', None),
    '236C_h': (NEAR, '2:-,' + M236C + '150:-', None),
    '236C2_w': (FAR, '2:-,' + M236C + '21:-,' + M236C + '150:-', None),
    '236C2_h': (NEAR, '2:-,' + M236C + '21:-,' + M236C + '150:-', None),
    '236C3_w': (FAR, '2:-,' + M236C + '21:-,' + M236C + '5:-,' + M236C + '150:-', None),
    '236C3_h': (NEAR, '2:-,' + M236C + '21:-,' + M236C + '29:-,' + M236C + '200:-', None),
    '28C_w': (FAR, '2:-,' + M28C + '150:-', None),
    '28C_h': (NEAR, '2:-,' + M28C + '150:-', None),
    '28C2_w': (FAR, '2:-,' + M28C + ''.join('2:D,2:Dc,' for _ in range(12)) + '150:-', None),
    '28C2_h': (NEAR, '2:-,' + M28C + '21:-,3:D,3:Dc,150:-', None),
    '421A_w': (FAR, '2:-,3:L,3:D,3:DL,3:a,3:a,150:-', LOW),
    '421A_h': (NEAR, '2:-,3:L,3:D,3:DL,3:a,3:a,150:-', LOW),
    '6246A_w': (FAR, '2:-,3:R,3:D,3:L,3:R,3:a,3:a,150:-', LOW),
    '6246A_h': (NEAR, '2:-,3:R,3:D,3:L,3:R,3:a,3:a,400:-', LOW),
    '214B_h': (NEAR, '2:-,3:D,3:DL,3:L,3:b,3:b,150:-', None),
    # the air dive j.2B ($8F) and its follow-up: 2B again after its hit, while still 64 px up or more: $92 (a second
    # dive kick, knocks down); the brawler plays j.2B as an air normal (atk_d_jump), so this one is captured only
    'j2B_h': (330, '2:-,3:UR,10:-,3:Db,90:-', None),
    'j2B2_h': (330, '2:-,3:UR,10:-,3:Db,4:-,3:Db,90:-', None),
}
PIN = 6                                                # P2 pinned before the move starts (its first frames)

def fighter(r, a):
    o = cap.obj(r, a); w = o['raw']
    return [o['anim'] & 0xFFF, o['step'], o['x'], o['y'], o['flags'] >> 1 & 1, o['ptr'], w[0x113], r['cam'][0x2A],
            o['anim'] >> 12, cap.s16(r['cam'], 0x1A), cap.u16(w, 0x48), w[0x10C] >> 3 & 1, w[0x1EB], cap.s16(r['cam'], 0x1E)]

def capture(name):
    p2x, seq, pokes = RECIPES[name]
    n = cap.nframes(seq)
    pk = []
    for f in range(n):
        s = ([f'108424={p2x >> 8:02X},108425={p2x & 255:02X}'] if f < PIN else []) + ([pokes] if pokes else [])
        if s: pk.append(f'{f}:' + ','.join(s))
    rows = cap.run(seq, '', pokes=';'.join(pk) or None)
    base = {k for k in range(0x40) if rows[0]['pool'][k * 0x100 + 0x40:k * 0x100 + 0x42] != b'\0\0'}
    out = []
    for r in rows:
        objs = []
        for k in range(0x40):
            o = r['pool'][k * 0x100:(k + 1) * 0x100]
            if k in base or not cap.u32(o, 0x94): continue
            ob = cap.obj(r, 0x100000 + k * 0x100)
            objs.append([k, ob['anim'], ob['step'], ob['x'], ob['y'], ob['flags'] >> 1 & 1, ob['ptr'], ob['name'].rstrip(' ')])
        out.append([fighter(r, 0x108200), fighter(r, 0x108400), objs, r['snd']])
    return out

def runs(fr, i=0):
    """[(first frame, anim)] of fighter i"""
    out = []
    for k, f in enumerate(fr):
        if not out or out[-1][1] != f[i][0]: out.append((k, f[i][0]))
    return out

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else OUT
    names = sys.argv[2:] or list(RECIPES)
    data = json.load(open(path)) if os.path.exists(path) and sys.argv[2:] else {}
    for k in names:
        fr = capture(k)
        data[k] = {'recipe': RECIPES[k], 'frames': fr}
        print(k, ' '.join(f'{a}:{n:X}' for a, n in runs(fr)), '| P2', ' '.join(f'{a}:{n:X}' for a, n in runs(fr, 1)),
              '| life', fr[0][1][6], '->', fr[-1][1][6])
    json.dump(data, open(path, 'w'))
