#!/usr/bin/env python3
"""T5 (2026-10-14): The Last Blade 2's impact sounds, measured in our emulator (the repo's Geolith core, play_lb2; the
68000 write tap on $320000 logs every sound byte the game sends).

LB2's hit code ($3AF7E) [code]: the hit word $70270[attack box type] and the box's strength pick a class word $A0nn from
$7A198 ([strength][kind]); $2948E's table maps it to a function that draws list[RNG $3E30 & mask] (functions $29938 ..
$29A74, the lists = songs.json sfx "picks" 'LB2 A0' .. 'LB2 A9', `picks` below reads them). The impact is sent as $17 +
the drawn code (effect slot 5). Which family a move's hit uses is measured here: each move hits P2 (and whiffs, and is
guarded) from vs.state over N RNG states (the start delayed 2 .. N + 1 frames); its impact codes = the $17 codes the hit
sends that the whiff does not; per hit (in order) the family = the smallest list holding every code seen
(-> handlers_lb2 NORMAL_SND / SPECIAL_SND). Guards send $17 $96 / $97 (slashes), $9A / $9B (kicks): not imported (the
brawler has no guard yet); swings $9E / $A2-$A5 / $D9 / $CE / $E9 / $EA, and $AE (the knockdown's landing), not imported.

    python3 hitsound_lb2.py picks                        the families' lists read from the code
    python3 hitsound_lb2.py measure OUT.json [N]         normals + specials (whiff / hit / guard), N RNG states (12)
    python3 hitsound_lb2.py more OUT.json [N]            the follow-ups and supers (style / gauge / life poked)
    python3 hitsound_lb2.py families OUT.json ...        per move and hit: the family (from measure / more outputs)
One emulator process at a time."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAMILIES = {'A0': 0x29938, 'A1': 0x29954, 'A2': 0x2998C, 'A4': 0x299A8, 'A5': 0x299C0, 'A6': 0x299D8, 'A8': 0x299F0,
            'A9': 0x29A0C, 'AA': 0x29A28, 'AC': 0x29A44, 'AD': 0x29A5C, 'AE': 0x29A74}   # $2948E[$20 + n] [code]

def pick(a):
    """a family function: jsr $3E30 (the RNG); andi.b #mask, d0; lea list(pc), a0; move.b (a0, d0), d0 -> the list"""
    import lb2 as L
    assert L.u16(a) == 0x4EB9 and L.u32(a + 2) == 0x3E30, hex(a)
    m = L.u8(a + 9); t = a + 12 + L.u16(a + 12)
    return [L.u8(t + q) for q in range(m + 1)]

def picks():
    import lb2 as L
    for f, a in FAMILIES.items():
        assert L.u32(0x294A6 + 4 * (0x20 + int(f[1], 16))) == a, f
        print(f'LB2 {f}', ' '.join(f'{c:02X}' for c in pick(a)))

CASES = [('stand A', '3:a', 60), ('stand B', '3:b', 70), ('stand C', '3:c', 60), ('crouch A', '3:D,3:Da', 60),
         ('crouch B', '3:D,3:Db', 70), ('crouch C', '3:D,3:Dc', 60), ('fwd B', '3:R,3:Rb', 80), ('back A', '3:L,3:La', 50),
         ('back B', '3:L,3:Lb', 60), ('fwd C', '3:R,3:Rc', 60), ('df C', '3:DR,3:DRc', 60), ('jump A', '1:U,30:-,3:a', 40),
         ('jump B', '1:U,20:-,3:b', 30), ('jump C', '1:U,30:-,3:c', 40),
         ('623A', '3:R,3:D,3:DR,3:a', 60), ('623B', '3:R,3:D,3:DR,3:b', 60), ('236A', '3:D,3:DR,3:R,3:a', 60),
         ('236B', '3:D,3:DR,3:R,3:b', 60), ('214A', '3:D,3:DL,3:L,3:a', 70), ('214B', '3:D,3:DL,3:L,3:b', 70),
         ('214C', '3:D,3:DL,3:L,3:c', 70)]
Z = lambda b: f'3:R,3:D,3:DR,3:{b}'
Q = lambda b: f'3:D,3:DR,3:R,3:{b}'
MORE = [  # name, seq, gap, style (+$17A: 0 Power, 1 Speed, 3 EX), gauge (+$17D), life (+$17E)
    ('Tsukikage A x3', f'{Q("a")},12:-,{Q("a")},12:-,{Q("a")}', 60, 3, 0, 0),
    ('Tsukikage B x4', f'{Q("b")},12:-,{Q("b")},12:-,{Q("b")},12:-,{Q("b")}', 60, 3, 0, 0),
    ('Shingetsu > Sougetsu', f'{Z("a")},8:-,{Z("b")}', 60, 1, 0, 0),
    ('Izayoi Gekka 64123AB', '3:R,3:L,3:DL,3:D,3:DR,3:ab', 60, 0, 64, 0),
    ('Midare 641236B', '3:R,3:L,3:DL,3:D,3:DR,3:R,3:b', 90, 0, 64, 40),
    ('Byakuya 22A', '3:D,3:-,3:D,3:a', 90, 1, 64, 0)]

def _core():
    import play_lb2 as PL
    g = PL.core(); g.watch(0x320000, 1)
    return PL, g

def _play(PL, g, seq, gap, mode, delay, style=None, gauge=0, life=0, tail=90):
    g.load_state(f'{PL.STA}/vs.state'); g.frame = 0; g.log = []
    if style is not None: g.w(PL.P1 + 0x17A, 1, style)
    if gauge: g.w(PL.P1 + 0x17D, 1, gauge)
    if life: g.w(PL.P1 + 0x17E, 2, life)
    keys = PL.expand(f'{delay}:-,' + seq + f',{tail}:-')
    hits = []
    for f, k in enumerate(keys):
        g.pad = [set(k), set('R' if mode == 'guard' else '')]
        if mode == 'whiff' or f < delay + 2: g.w(PL.P2 + 0x80, 2, (g.r(PL.P1 + 0x80) + (300 if mode == 'whiff' else gap)) & 0xFFFF)
        if g.r(PL.P2 + 0x17E) < 100: g.w(PL.P2 + 0x17E, 2, 256)
        l = g.r(PL.P2 + 0x17E)
        g.core.retro_run(); g.frame += 1
        if g.r(PL.P2 + 0x17E) < l: hits.append((f - delay, f'{g.r(PL.P1 + 0x74):X}'))
    b = [v for f, pc, a, v, s in g.log]
    return [(b[i] << 8 | b[i + 1]) for i in range(len(b) - 1) if b[i] == 0x17], hits

def measure(out, n=12):
    PL, g = _core(); res = {}
    for name, seq, gap in CASES:
        sw = set()
        for d in range(2, 2 + n): sw |= set(_play(PL, g, seq, gap, 'whiff', d)[0])
        r = {'whiff': sorted(f'{w:04X}' for w in sw)}
        for mode in ('hit', 'guard'):
            r[mode] = []
            for d in range(2, 2 + n):
                w, h = _play(PL, g, seq, gap, mode, d)
                r[mode].append({'delay': d, 'hits': h, 'impacts': [f'{x & 0xFF:02X}' for x in w if x not in sw]})
        res[name] = r
        print(name, 'hit', sorted({c for p in r['hit'] for c in p['impacts']}), 'guard', sorted({c for p in r['guard'] for c in p['impacts']}), flush=True)
    json.dump(res, open(out, 'w'), indent=0)

def more(out, n=8):
    PL, g = _core(); res = {}
    for name, seq, gap, style, gauge, life in MORE:
        runs = []
        for d in range(2, 2 + n):
            w, h = _play(PL, g, seq, gap, 'hit', d, style, gauge, life, tail=240)
            runs.append({'delay': d, 'hits': h, 'impacts': [f'{x & 0xFF:02X}' for x in w if 0x70 <= x & 0xFF <= 0x95]})
        res[name] = {'hit': runs}
        print(name, [r['impacts'] for r in runs[:3]], flush=True)
    json.dump(res, open(out, 'w'), indent=0)

def families(*paths):
    lists = {}
    import lb2  # noqa: F401 (the ROM)
    for f, a in FAMILIES.items(): lists[f] = pick(a)
    for p in paths:
        for name, r in json.load(open(p)).items():
            nh = max(len(x['impacts']) for x in r['hit'])
            per = [set() for _ in range(nh)]
            for x in r['hit']:
                for i, c in enumerate(x['impacts']): per[i].add(int(c, 16))
            fam = []
            for s in per:
                ok = [k for k, v in lists.items() if s <= set(v)]
                fam.append(min(ok, key=lambda k: len(set(lists[k]))) if ok else None)
            print(f'{name:22}', fam)

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'picks': picks()
    elif c == 'measure': measure(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12)
    elif c == 'more': more(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8)
    elif c == 'families': families(*sys.argv[2:])
