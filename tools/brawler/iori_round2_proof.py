#!/usr/bin/env python3
"""Iori round 2 (voice notes 20261011-224840 / 224757 / 230030 / 225504-5d29, game 0.10.63) in the brawler, in our
emulator (harness.py, BRAWLER_CORE: the Z80 port tap core):
  1. draw order: MAX 23624C (down + D) on Ryo: from the catch to the release the victim is drawn BEHIND Iori (fighter_t
     zfront -1 at the same Z: bvent_t VE_BACK, KOF98 $25372's dx bit 7 clear = the attacker in front, measured in KOF98
     P1 +$2C $101 / P2 $100 every frame); screenshots every 8 frames
  2. 624D (forward + C) release: the effect codes queued (sound.c's queue) and the ADPCM-A key-ons around the release;
     the keyed sample byte-equal to KOF98's own $1A4D (voices.probe: KOF98's driver playing it; KOF98's victim routine
     $70CBC sends index $5B5 = $1A4D at the release, bvlist_t.rsnd), WAVs of both
  3. 624D's explosion as an area hit (game.json roster[].special_final_area "624D"): the dummy + 4 clones (two inside the
     area, two outside: too far ahead / too deep); the inside ones knocked down at the release, the outside ones untouched
  4. the chain's fourth press = forward + B (chain.links[3] cmd_fwd_b): A pressed 4 times next to Ryo
  5. dd + A = 214C Aoi Hana's three parts (214C>142 / >146 / >149), A pressed again for each (note 210904's reopen)
  6. back + A in a forward jump past the dummy = KOF98's j.4B Yuri Ori (state 183) hitting it behind Iori, and in a
     straight jump with the dummy behind (note 210422's reopen)
    python3 iori_round2_proof.py [OUT]     (default /data/tmp/iori2) -> OUT/proof.json, exit 1 on a FAIL"""
import ctypes as C, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import harness, voices as V
from labdrive import Lab
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/iori2'
GAME = harness.GAME
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
gj = json.load(open(os.path.join(GAME, 'game.json'))); NAMES = [r['name'] for r in gj['roster']]
POOL = [p['input'] for p in next(x for x in json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))['fighters'] if x['name'] == 'iori')['pool']]
ROM = os.path.join(GAME, 'brawler.neo')

def setup(L, dummy='ryo', gap=50):
    b = L.b
    L.start(NAMES.index('iori'), NAMES.index(dummy)); b.run(30)
    x0 = b.r(b.syms['cam_x'], 2) + 120
    b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
    b.place(2, x=x0 + gap, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', 120); b.run(2)
    return x0

def spec(b):
    s = b.states[b.fget(0, 'state')]
    return 'SPECIAL ' + POOL[b.fget(0, 'spec_ix')] if s == 'SPECIAL' else s

def draw_order():
    L = Lab(rom=ROM, game=GAME); b = L.b; ST = b.states; M = gj['meter']
    setup(L)
    d = os.path.join(OUT, 'brawler_max'); os.makedirs(d, exist_ok=True)
    held = behind = 0; seen = set()
    for t in range(380):
        if t < 3: b.fset(0, 'hp', 5); b.fset(0, 'drive', M['chunk'] * M['chunks']); b.fset(0, 'fgauge', M['fury_max'])   # (the MAX)
        b.run(1, p1='Dd' if t < 3 else '')
        seen.add(spec(b))
        if b.fget(0, 'state') == ST.index('SPECIAL') and b.fget(2, 'frame_ovr') != 0xFFFF:   # the victim held by the list
            held += 1; behind += b.fget(2, 'zfront') in (-1, 0xFF) and b.fget(2, 'z') == b.fget(0, 'z')
        if t % 8 == 0: b.screenshot(f'{d}/b_{t:03d}.png')
    return {'moves': sorted(seen), 'held_frames': held, 'behind_frames': behind,
            'pass': 'SPECIAL MAX 23624C' in seen and held > 100 and behind == held}

def release_sound():
    L = Lab(rom=ROM, game=GAME); b = L.b; S = b.syms; ST = b.states
    log, reg = [], {}
    def tap(write, port, v):
        if write:
            if port & 0xFF == 6: tap.a = v
            elif port & 0xFF == 7:
                if tap.a == 0 and v and not v & 0x80:            # ADPCM-A key-on: each keyed channel's start / end pages
                    for ch in range(6):
                        if v >> ch & 1:
                            log.append((b.frame, ch, reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0), reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)))
                reg[tap.a] = v
        return v
    tap.a = 0; cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    setup(L)
    oqt = b.r(S['qt'], 1); sent = []; f0 = b.frame; rel = None; seen = set()
    for t in range(120):
        b.run(1, p1='Rc' if t < 3 else '')
        seen.add(spec(b))
        qt = b.r(S['qt'], 1)
        while oqt != qt: sent.append((b.frame - f0, b.r(S['q'] + oqt, 1))); oqt = (oqt + 1) & 31
        if rel is None and ST[b.fget(2, 'state')] == 'KNOCKDOWN': rel = b.frame - f0
    b.run(30)
    d = open(ROM, 'rb').read(); h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]; vb = d[o:o + h[3]]
    kof = V.probe('kof98', [0x1A4D])[0x1A4D]; vk = V.v_rom('kof98'); ks = V.sample_bytes(vk, kof['segments'])
    sd = os.path.join(OUT, 'sound'); os.makedirs(sd, exist_ok=True)
    V.write_wav(f'{sd}/kof98_1A4D.wav', vk, kof['segments'])
    codes = [(f, f'1A{sent[i + 1][1]:02X}') for i, (f, c) in enumerate(sent) if c == 0x1A and i + 1 < len(sent)]
    keys = []
    for f, ch, s, e in log:
        f -= f0
        if rel is not None and rel - 1 <= f <= rel + 4:
            eq = V.sample_bytes(vb, [(s, e)]) == ks
            keys.append({'frame': f, 'ch': ch, 'pages': [s, e], 'equal_kof98_1A4D': eq})
            V.write_wav(f'{sd}/brawler_release_f{f}_ch{ch}.wav', vb, [(s, e)])
    at_rel = [c for f, c in codes if rel is not None and rel - 1 <= f <= rel + 1]
    return {'moves': sorted(seen), 'release_frame': rel, 'effects': codes, 'release_effects': at_rel, 'kof98_1A4D': kof,
            'release_keyons': keys, 'pass': '1A4D' in at_rel and '1A19' not in at_rel and any(k['equal_kof98_1A4D'] for k in keys)}

def area():
    L = Lab(rom=ROM, game=GAME); b = L.b; ST = b.states
    setup(L)
    blob = bytes(b.r(b.base + 2 * b.fsize + k, 1) for k in range(b.fsize))     # the dummy copied into free slots
    rel = {3: (70, 0, True), 4: (-16, 10, True),                                 # inside: 70 ahead / 16 behind, 10 deep
           5: (140, 0, False), 6: (50, 40, False)}                               # outside: 140 ahead / 40 deep
    for i in rel:                                                                # (scenario.py's extra dummies)
        for k, v in enumerate(blob): b.w(b.base + i * b.fsize + k, 1, v)
        b.fset(i, 'idx', i); b.fset(i, 'palbase', 16 + i * 8); b.fset(i, 'ovl', 1); b.fset(i, 'hp', 120)
        b.place(i, x=b.fget(0, 'x') - 200 - 30 * i, z=30)                       # out of the dash's way until the catch
    b.run(1)
    hp0 = {i: b.fget(i, 'hp') for i in rel}; down = {i: False for i in rel}; seen = set(); shot = False; caught = False
    d = os.path.join(OUT, 'area'); os.makedirs(d, exist_ok=True)
    for t in range(140):
        released = b.states[b.fget(2, 'state')] in ('KNOCKDOWN', 'DOWN')
        caught |= b.fget(2, 'frame_ovr') != 0xFFFF
        if caught and not released:                                              # placed around Iori from the catch to
            x, z, f = b.fget(0, 'x'), b.fget(0, 'z'), 1 if b.fget(0, 'facing') == 1 else -1   # the release, standing
            for i, (dx, dz, _) in rel.items():
                b.place(i, x=x + f * dx, z=z + dz); b.fset(i, 'facing', (-f if dx > 0 else f) & 0xFF)
        b.run(1, p1='Rc' if t < 3 else '')
        seen.add(spec(b))
        for i in rel: down[i] |= b.states[b.fget(i, 'state')] in ('KNOCKDOWN', 'DOWN')
        if not shot and b.states[b.fget(2, 'state')] == 'KNOCKDOWN': b.run(6); b.screenshot(f'{d}/release.png'); shot = True
    res = {str(i): {'from_iori': [dx, dz], 'inside': ins, 'hp_lost': hp0[i] - b.fget(i, 'hp'), 'knocked_down': down[i]}
           for i, (dx, dz, ins) in rel.items()}
    return {'moves': sorted(seen), 'caught': caught, 'clones': res,
            'pass': 'SPECIAL 624D' in seen and caught and all(v['knocked_down'] == v['inside'] and (v['hp_lost'] > 0) == v['inside'] for v in res.values())}

def chain4():
    L = Lab(rom=ROM, game=GAME); b = L.b; ST = b.states
    setup(L, gap=44)
    starts, prev = [], None
    for t in range(80):
        b.run(1, p1='a' if t % 12 < 2 else '')
        s = ST[b.fget(0, 'state')]
        k = (s, b.fget(0, 'anim'))
        if s == 'ATTACK' and k != prev: starts.append(b.fget(0, 'anim'))
        prev = k
    import re
    ba = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', open(os.path.join(GAME, 'build', 'bm_chars.h')).read()).group(1).split(', ')
    names = [ba[a] for a in starts]
    return {'starts': names, 'pass': len(names) >= 4 and names[3] == 'BA_CMD_FWD_B'}

def rekka():
    """note 20261011-210904-5d29's reopen: dd + A = 214C Aoi Hana's three parts, each on A again"""
    L = Lab(rom=ROM, game=GAME); b = L.b; ST = b.states
    setup(L, gap=44)
    seen, hits, hp = [], 0, b.fget(2, 'hp')
    keys = ['D', '', 'D', 'Da'] + [''] * 14 + ['a', 'a'] + [''] * 14 + ['a', 'a'] + [''] * 60
    for k in keys:
        b.run(1, p1=k); w = spec(b)
        if w.startswith('SPECIAL') and (not seen or seen[-1] != w): seen.append(w)
        if b.fget(2, 'hp') < hp: hits += 1
        hp = b.fget(2, 'hp')
    return {'parts': seen, 'hits': hits, 'pass': seen == ['SPECIAL 214C>142', 'SPECIAL 214C>146', 'SPECIAL 214C>149'] and hits >= 3}

def crossup():
    """note 20261011-210422-5d29's reopen: a forward jump over the dummy, back + A past it = KOF98's j.4B Yuri Ori
    (air.back atk_ab_jump = $B7, state 183): it hits the dummy BEHIND Iori; a straight jump + back + A plays it too"""
    out = {}
    for tag, jump, dist, t in (('forward', 'Rb', 60, 28), ('straight', 'b', -20, 10)):
        L = Lab(rom=ROM, game=GAME) if not out else L
        b = L.b; ST = b.states
        if not out: setup(L, gap=60); base = b.save()
        b.load(base); x0 = b.fget(0, 'x')
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + dist, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', 60); b.run(2)
        hp = b.fget(2, 'hp'); moves = set(); behind = None
        for k in range(90):
            b.run(1, p1=jump if k < 2 else ('La' if t <= k < t + 2 else ''))
            if ST[b.fget(0, 'state')] == 'AIR_ATTACK': moves.add(b.fget(0, 'anim'))
            if behind is None and b.fget(2, 'hp') < hp:
                behind = (b.fget(2, 'x') - b.fget(0, 'x')) * (1 if b.fget(0, 'facing') == 1 else -1) < 0
        import re
        ba = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', open(os.path.join(GAME, 'build', 'bm_chars.h')).read()).group(1).split(', ')
        out[tag] = {'moves': sorted(ba[a] for a in moves), 'hit_behind': behind}
    return dict(out, **{'pass': all(v['hit_behind'] and any(m.startswith('BA_ATK_AB_JUMP') for m in v['moves']) for v in out.values())})

PARTS = {'draw_order': draw_order, 'release_sound': release_sound, 'area': area, 'chain4': chain4, 'rekka': rekka, 'crossup': crossup}
if __name__ == '__main__':
    import subprocess
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 2:                                # one part in its own process (one core a process)
        json.dump(PARTS[sys.argv[2]](), open(os.path.join(OUT, f'_{sys.argv[2]}.json'), 'w')); sys.exit(0)
    R = {}
    for k in PARTS:
        subprocess.run([sys.executable, __file__, OUT, k], check=True)
        R[k] = json.load(open(os.path.join(OUT, f'_{k}.json')))
    json.dump(R, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    for k, v in R.items(): print(k, 'PASS' if v['pass'] else 'FAIL', json.dumps({x: y for x, y in v.items() if x != 'pass'})[:600])
    ok = all(v['pass'] for v in R.values()); print('ALL OK' if ok else 'FAIL'); sys.exit(0 if ok else 1)
