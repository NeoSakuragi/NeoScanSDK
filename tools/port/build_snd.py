#!/usr/bin/env python3
"""The brawler's sound ROMs from its song manifest: KOF98's sound driver (SNK v1.7) with only the songs the game plays,
and a V ROM with only the samples those songs and the game's sound effects use.

    python3 build_snd.py MANIFEST.json OUT_DIR      -> OUT_DIR/m1.bin, v1.bin, songs.h, snd_report.json

Manifest (examples/brawler/songs.json):
    {"driver": "kof98",
     "sfx": {"slot": 1, "prefix": "1A", "codes": ["11", ...],   the effect codes the game sends ($1A prefix = slot 1)
             "names": {"11": "HIT A", ...},                    short names (the options screen's SOUND PLAYER)
             "from": {"8F": {"game": "kof2000", "cmd": "1E8F"}}},  codes playing another SNK 1.x driver game's
                                                                effect (its ADPCM-A record and sample)
     "songs": [{"name": "FIGHT", "source": "fatfury3", "cmd": "2F", "what": "...",
                "label": "FIGHT"}, ...],                      label: the MUSIC PLAYER's name (default: name, _ = space)
     "bosses": ["BOSS_MR_BIG", ...],                          song names, in the campaign's boss order
     "ssg": {"cues": [{"name": "CURSOR", "cmd": "74", "voices": [...]}, ...]}}   menu sounds: SSG cues (ssg_cues.py)
A song whose source is the driver's own game ("kof98") keeps its command and its song data (its bank set block is
copied whole); any other is ported (port98.py) into a free command, in manifest order from $27 (KOF98's empty slot),
then the lowest free music command.

M ROM: the fixed 64 KB (driver, tables, bank set 0 = KOF98's menu songs) + one 32 KB block per further bank set in use
(KOF98 bank set n = M1 $8000*(n+1): Z80 $8000-$F7FF): kept KOF98 sets first, renumbered from 1, then the ports, packed
first-fit. Song pointers of the commands not in the manifest are cleared (the driver plays nothing for them).
V ROM: built from nothing: the samples of the kept songs' notes (song98.py's model of each song to its loop end) and of
the manifest's effect codes, then each port's samples; ADPCM-A samples never cross a 1 MB boundary (the YM2610's
ADPCM-A address counter is 20 bits: docs/rom_packer_rules.md). Every sample record (ADPCM-A tables slots 0-7, ADPCM-B
records) is rewritten to the new addresses; records nobody uses are emptied and become the ports' free entries.
An effect code in sfx "from" (TODO #155: KOF2000's MAX flash) does not keep KOF98's record: its record in the effect
slot becomes the source game's (the 1.x drivers share the 6-byte layout [priority][start][end][level]; found through the
source driver's own table list, $2E0E + 2 * slot), its sample is copied from that game's V ROM, its enable bit set."""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'kof98snd'))
import port98, song98, games98, ssg_cues
from port98 import roms, w16, A_TABLES, A_SLOTS

KOF98 = '/data/roms/kof98.neo'
SLOT7, SLOT7_SIZE = 0x65FA, 11                           # 11-byte looping records (slot 7)
CODES = 0xF0                                              # codes from $F0 on never read a table ($311B, $0618)
A_CODES = [CODES] * 6 + [(SLOT7 - A_TABLES[6]) // 6]      # slot 6's table ends where slot 7's starts: 237 codes
EMPTY_A = bytes([0x01, 0, 0, 0, 0, 0xDC])
EMPTY_B = bytes.fromhex('01 0000 ffff 00 0000 ffff b36e 80'.replace(' ', ''))
MB = 4096                                                 # 1 MB in 256-byte pages

class Target:
    def __init__(self):
        m1, v = roms(KOF98)
        self.m1 = bytearray(m1); self.v_src = v
        self.v = bytearray(); self.gaps = []              # V being built; free page ranges [start, end) inside it
        self.placed = {}                                  # (source, start, end) -> (new start, new end)
        self.w = lambda a: self.m1[a] | self.m1[a + 1] << 8
        self.brecs = self.w(0x2E1E); self.imap = self.w(0x2E08); self.bt = self.w(0x2E06)
        self.n_brecs = 0                                  # the ADPCM-B records: 13 bytes ending in $80 (KOF98: 117,
        while self.m1[self.brecs + 13 * self.n_brecs + 12] == 0x80: self.n_brecs += 1   # then other tables)
        self.sets = {0: None}                             # bank set -> free Z80 address (None: no room / KOF98's own)

    # -- V ROM
    def place(self, src, st, en, src_v, adpcm_a):
        key = (src, st, en)
        if key in self.placed: return self.placed[key]
        n = en - st + 1
        at = None
        for g in self.gaps:
            s0 = g[0]
            if adpcm_a and s0 // MB != (s0 + n - 1) // MB: s0 = (s0 // MB + 1) * MB
            if s0 + n <= g[1]: at = s0; break
        if at is None:
            top = len(self.v) >> 8; at = top
            if adpcm_a and at // MB != (at + n - 1) // MB: at = (at // MB + 1) * MB
            if at > top: self.gaps.append([top, at])
            self.v += bytes(((at + n) << 8) - len(self.v))
        for g in self.gaps:                               # take [at, at + n) out of its gap
            if g[0] <= at and at + n <= g[1]:
                self.gaps.remove(g)
                if g[0] < at: self.gaps.append([g[0], at])
                if at + n < g[1]: self.gaps.append([at + n, g[1]])
                break
        self.gaps.sort()
        self.v[at << 8:(at + n) << 8] = src_v[st << 8:(en + 1) << 8]
        self.placed[key] = (at, at + n - 1)
        return self.placed[key]

    # -- sample records
    def a_records(self):
        for sl, t in enumerate(A_TABLES):
            for c in range(A_CODES[sl]): yield sl, c, t + 6 * c, 6
        for c in range(CODES): yield 7, c, SLOT7 + SLOT7_SIZE * c, SLOT7_SIZE

    def free_acode(self):
        for sl in A_SLOTS:
            for c in range(1, A_CODES[sl]):
                r = A_TABLES[sl] + 6 * c
                if (sl, c) not in self.keep_a and self.m1[r + 1:r + 5] == bytes(4):
                    self.keep_a.add((sl, c)); return sl, c
        raise ValueError('no free ADPCM-A code')

    def free_brec(self):
        for i in range(1, self.n_brecs):
            r = self.brecs + 13 * i
            if i not in self.keep_b and self.m1[self.imap + i] == i and self.m1[r:r + 13] == EMPTY_B:
                self.keep_b.add(i); return i
        raise ValueError('no free ADPCM-B record')

    # -- M ROM bank sets
    def m1_offset(self, bank, z): return 0x8000 * (bank + 1) + z - 0x8000
    def reserve(self, size):
        for b in sorted(self.sets):
            z = self.sets[b]
            if z is not None and z + size <= port98.SONG_Z80_END: self.sets[b] = z + size; return b, z
        b = max(self.sets) + 1
        if b > 6: raise ValueError('no free bank set (KOF98 has 7: $2708 table)')
        self.sets[b] = port98.SONG_Z80 + size
        return b, port98.SONG_Z80

def native_samples(m1, cmd):
    """the (table, code) ADPCM-A records and ADPCM-B (start, end) a KOF98 song plays, to its loop end or its end;
    and its loops {channel: (loop tick, length)} (an ending song: {'end': (tick, 0)})"""
    s = song98.Song(bytes(m1), cmd).run(ticks=20000)
    end = max((a + b for a, b, _ in s.loop_at.values()), default=s.tick) + 1
    s = song98.Song(bytes(m1), cmd).run(ticks=end)
    a, b = set(), set()
    for irq, t, ch, kind, kw in s.out:
        if kind == 'akey': a.add((kw['table'], kw['sample']))
        elif kind == 'bkey': b.add((kw['start'], kw['end']))
    loops = {k: [a_, b_] for k, (a_, b_, _) in s.loop_at.items()} or {'end': [s.tick, 0]}
    return a, b, loops

PREFIX_SLOT = {0x1A: 1, 0x1C: 2, 0x1E: 3, 0x1B: 4, 0x17: 5, 0x16: 6, 0x1D: 7}   # KOF98 $0D7B: effect prefix -> slot
VOICE_PRIO = 0x50                                         # KOF98's voice records (110 of slot 2's 223 used ones)

def voices(t, man, mdir, out):
    """the fighters' voices (TODO #55): only the ones the ROM's voice tables map (export_bm.py build/voice_map.json, from
    game.json roster[].voices), each sample copied from its game's V ROM (tools/brawler/voices.json: the ADPCM-A segments
    its own driver plays) into ours, one record per voice with the same code in every voice slot (players' prefix, enemies'
    prefix: a player's voice never cuts an enemy's): [priority (KOF98's own record's, else $50)][start][end][its level
    byte as the source driver wrote it]. A voice whose driver replays parts (a looped record) keeps its first segment.
    -> OUT/voices.h: per fighter (game.json roster order) voice id -> driver code (0 = not in the V ROM). A slot holds
    codes $11-$EF (223 voices): past them the voices go on in the "overflow" pair of slots (same layout, its own
    prefixes; TODO #161 needed 230), their codes | $100 in voices.h (fighter.c voice_id: VOICE_PREFIX2_*)"""
    cfg = man['voices']
    bank = json.load(open(os.path.join(mdir, cfg['bank'])))['fighters']
    vmap = json.load(open(os.path.join(mdir, cfg['map'])))
    groups = [(cfg['slots'], cfg['prefixes'])] + ([(cfg['overflow']['slots'], cfg['overflow']['prefixes'])] if cfg.get('overflow') else [])
    g = 0; slots = groups[0][0]
    old = bytes(roms(KOF98)[0])                           # KOF98's own records (the build emptied the unused ones)
    srcv = {}
    codes, placed, rep = {}, {}, {'fighters': {}, 'bytes': 0, 'slots': slots, 'prefixes': cfg['prefixes'],
                                  **({'overflow': cfg['overflow']} if cfg.get('overflow') else {})}
    nxt = 0x11                                            # the prefix commands play a code only when its bit is set in
    bits = [t.w(0x2E20 + 2 * sl) for sl in slots]         # the slot's 32-byte enable map ($0F1A: $2E20 + 2 * slot -> map,
    rep['enable_maps'] = [[b, b + 32] for b in bits]      # bit 7 - code % 8 of byte code / 8); KOF98 leaves $00-$10 off
    for sl in sum((s_ for s_, _ in groups[1:]), []):      # the overflow slots: KOF98's records there go unused (the
        assert all(t.m1[A_TABLES[sl] + 6 * c + 1:A_TABLES[sl] + 6 * c + 5] == bytes(4) for c in range(0x11, CODES)), sl   # build emptied them)
    for f in vmap:
        fb = bank.get(f['name'], {'voices': []}); game = fb.get('game')
        codes[f['name']] = [0] * (len(fb['voices']) + 1)
        for i in f['ids']:
            vo = fb['voices'][i - 1]; assert vo['id'] == i
            st, en = vo['segments'][0]
            key = (game, st, en)
            if key not in placed:
                if game not in srcv: srcv[game] = roms(f'/data/roms/{game}.neo')[1] if game != 'kof98' else t.v_src
                while any((sl, nxt) in t.keep_a for sl in slots): nxt += 1   # (records nobody keeps are empty now)
                if nxt >= CODES and g + 1 < len(groups):      # this pair is full: the overflow pair, from $11
                    g += 1; slots = groups[g][0]; nxt = 0x11; bits = [t.w(0x2E20 + 2 * sl) for sl in slots]
                    rep['enable_maps'] += [[b, b + 32] for b in bits]
                    while any((sl, nxt) in t.keep_a for sl in slots): nxt += 1
                assert nxt < CODES, f'no free voice code ({len(placed)} samples placed)'
                ns, ne = t.place(game, st, en, srcv[game], adpcm_a=True)
                pre = int(vo['cmd'][:2], 16); code = int(vo['cmd'][2:], 16); sl0 = PREFIX_SLOT.get(pre)
                prio = VOICE_PRIO
                if game == 'kof98' and sl0:
                    prio = old[SLOT7 + SLOT7_SIZE * code] if sl0 == 7 else old[A_TABLES[sl0] + 6 * code]
                for sl in slots:
                    r = A_TABLES[sl] + 6 * nxt
                    t.m1[r:r + 6] = bytes([prio]) + w16(ns) + w16(ne) + bytes([vo['level']])
                    t.m1[bits[slots.index(sl)] + nxt // 8] |= 0x80 >> (nxt % 8)
                    t.keep_a.add((sl, nxt))
                    assert t.v[ns << 8:(ne + 1) << 8] == srcv[game][st << 8:(en + 1) << 8]
                placed[key] = nxt | g << 8; rep['bytes'] += (en - st + 1) << 8; nxt += 1
            codes[f['name']][i] = placed[key]
        rep['fighters'][f['name']] = {'voices': len(f['ids']), 'codes': {i: codes[f['name']][i] for i in f['ids']}}
    os.makedirs(out, exist_ok=True)
    with open(f'{out}/voices.h', 'w') as h:
        h.write('/* generated by tools/port/build_snd.py: the fighters\' voices in this V ROM, per fighter (bm_chars order) its\n'
                ' * voice id (voices.json) -> KOF98 driver code, sent after VOICE_PREFIX_PLAYER / _ENEMY; 0 = not in the V ROM */\n')
        h.write('#ifndef VOICES_H\n#define VOICES_H\n')
        h.write(f"#define VOICE_PREFIX_PLAYER 0x{cfg['prefixes'][0]}\n#define VOICE_PREFIX_ENEMY 0x{cfg['prefixes'][1]}\n")
        p2 = groups[-1][1]                                # codes | $100: the overflow slots' prefixes (none: the same)
        h.write(f"#define VOICE_PREFIX2_PLAYER 0x{p2[0]}\n#define VOICE_PREFIX2_ENEMY 0x{p2[1]}\n")
        for k, f in enumerate(vmap):
            h.write(f"static const uint16_t vcode_{k}[] = {{ {', '.join(map(str, codes[f['name']]))} }};   /* {f['name']} */\n")
        h.write('#define VOICE_CODES { ' + ', '.join(f'vcode_{k}' for k in range(len(vmap))) + ' }\n')
        h.write('#define VOICE_NCODES { ' + ', '.join(str(len(codes[f['name']])) for f in vmap) + ' }\n#endif\n')
    rep['samples'] = len(placed)
    print(f"voices: {len(placed)} samples, {rep['bytes'] // 1024} KB, codes $11-${nxt - 1:02X} in slots {slots}"
          + (f" (after slots {groups[0][0]} full)" if g else ''), flush=True)
    return rep

def sfx_imports(t, slot, imports, rep):
    """sfx "from": each code plays another SNK 1.x driver game's effect: the source record (its prefix -> slot as KOF98's
    $0D7B, the slot's table from the source driver's list at $2E0E + 2 * slot) with the new sample addresses, the sample
    copied from that game's V ROM, the code's enable bit set. -> the fixed-area ranges written (the slot's enable map)"""
    rep['sfx_from'] = {}; bits = t.w(0x2E20 + 2 * slot)
    for c, f in imports.items():
        code = int(c, 16); pre, scode = int(f['cmd'][:2], 16), int(f['cmd'][2:], 16)
        sm, sv = roms(f'/data/roms/{f["game"]}.neo')
        assert bytes(sm[0x3E:0x56]).startswith((b'Sound Driver(ROM)Ver 1.', b'Sound Driver Ver 0.1')), \
            f'{f["game"]}: not an SNK 1.x / KOF96 Ver 0.1 sound driver'
        # (KOF96's Ver 0.1, TODO #197: the same table list at $2E0E, prefix -> slot and 6-byte records: its $1A $1F is
        # record $4536 = slot 1's table $447C + 6 * $1F, pages $4F8-$521 = the pages its own driver keys on, tap core)
        ssl = PREFIX_SLOT[pre]; tab = sm[0x2E0E + 2 * ssl] | sm[0x2E0F + 2 * ssl] << 8
        rec = sm[tab + 6 * scode:tab + 6 * scode + 6]
        st, en = rec[1] | rec[2] << 8, rec[3] | rec[4] << 8
        assert st and en >= st, (c, f, rec.hex())
        ns, ne = t.place(f['game'], st, en, sv, adpcm_a=True)
        r = A_TABLES[slot] + 6 * code
        t.m1[r:r + 6] = bytes([rec[0]]) + w16(ns) + w16(ne) + bytes([rec[5]])
        t.m1[bits + code // 8] |= 0x80 >> (code % 8)
        t.keep_a.add((slot, code))
        assert t.v[ns << 8:(ne + 1) << 8] == sv[st << 8:(en + 1) << 8]
        rep['sfx_from'][c] = {'game': f['game'], 'cmd': f['cmd'], 'source_record': f'${tab + 6 * scode:04X}',
                              'source_pages': [st, en], 'pages': [ns, ne], 'bytes': (en - st + 1) << 8,
                              'record': t.m1[r:r + 6].hex()}
        print(f"sfx ${c}: {f['game']} ${f['cmd']} (record ${tab + 6 * scode:04X} {rec.hex()}), {(en - st + 1) << 8} bytes", flush=True)
    return [(bits, bits + 32)]

def build(manifest, out):
    man = json.load(open(manifest))
    assert man['driver'] == 'kof98'
    t = Target(); m1 = t.m1; old = bytes(m1)
    music = games98.music_cmds(old)
    natives = [s for s in man['songs'] if s['source'] == 'kof98']
    ports = [s for s in man['songs'] if s['source'] != 'kof98']
    rep = {'songs': [], 'warnings': []}
    # 1. what the kept KOF98 songs and the effects use
    keep_a, keep_b_rng = set(), set()
    tabaddr = {t_: sl for sl, t_ in enumerate(A_TABLES)}; tabaddr[SLOT7] = 7
    nloops = {}
    for s in natives:
        a, b, nloops[s['name']] = native_samples(old, int(s['cmd'], 16))
        keep_a |= {(tabaddr[ta], c) for ta, c in a}; keep_b_rng |= b
    sl = man['sfx']['slot']
    imports = man['sfx'].get('from', {})
    assert all(c in man['sfx']['codes'] for c in imports), 'sfx from: every code must be in sfx codes'
    keep_a |= {(sl, int(c, 16)) for c in man['sfx']['codes'] if c not in imports}
    # 2. bank sets: set 0 stays; each other set a kept song uses is copied to the next free number
    newset = {0: 0}
    for s in natives:
        i = int(s['cmd'], 16) - 0x20; b = old[t.bt + i]
        if b not in newset: newset[b] = len(newset)
        m1[t.bt + i] = newset[b]
    blocks = {nb: old[0x8000 * (b + 1):0x8000 * (b + 2)] for b, nb in newset.items() if b}
    m1[0x10000:] = bytes([0xFF]) * (len(m1) - 0x10000)
    for nb, blk in blocks.items(): m1[0x8000 * (nb + 1):0x8000 * (nb + 2)] = blk; t.sets[nb] = None
    # 3. song pointers: only the kept commands
    keep_cmds = {int(s['cmd'], 16) for s in natives}
    for c in music:
        if c not in keep_cmds: m1[0x329E + 2 * (c - 0x20):0x329E + 2 * (c - 0x20) + 2] = bytes(2)
    # 4. V ROM: kept records -> new addresses, the rest emptied
    t.keep_a, t.keep_b = set(), set()
    jobs = []
    for sl_, c, r, size in t.a_records():
        st, en = t.w(r + 1), t.w(r + 3)
        if (sl_, c) in keep_a and (st or en): jobs.append((en - st, 'a', sl_, c, r, size, st, en))
        elif size == 6: m1[r:r + 6] = EMPTY_A
        else: m1[r:r + size] = bytes([0x01]) + bytes(size - 2) + bytes([0xDC])
    for i in range(t.n_brecs):
        r = t.brecs + 13 * i
        st, en = t.w(r + 1), t.w(r + 3)
        if (st, en) in keep_b_rng: jobs.append((en - st, 'b', None, i, r, 13, st, en))
        elif i and t.w(r + 1) | t.w(r + 3): m1[r:r + 13] = EMPTY_B
    for _, kind, sl_, c, r, size, st, en in sorted(jobs, reverse=True):
        ns, ne = t.place('kof98', st, en, t.v_src, adpcm_a=kind == 'a')
        m1[r + 1:r + 3] = w16(ns); m1[r + 3:r + 5] = w16(ne)
        if kind == 'a' and size == 11:                    # loop start / end inside the sample
            for o in (6, 8): m1[r + o:r + o + 2] = w16(t.w(r + o) - st + ns)
        if kind == 'b':
            for o in (6, 8):
                v = t.w(r + o)
                if st <= v <= en: m1[r + o:r + o + 2] = w16(v - st + ns)
        if kind == 'a': t.keep_a.add((sl_, c))
        else: t.keep_b.add(c)
    for _, kind, sl_, c, r, size, st, en in jobs:         # every kept record: same bytes but the addresses, same sample
        ns, ne = t.w(r + 1), t.w(r + 3)
        assert t.v[ns << 8:(ne + 1) << 8] == t.v_src[st << 8:(en + 1) << 8] and m1[r] == old[r] and m1[r + 5:r + size] == \
            old[r + 5:r + size] or kind == 'b' or size == 11, (kind, sl_, c)
    rep['kept_records_checked'] = len(jobs)
    v_natives = len(t.v)
    imp_ranges = sfx_imports(t, sl, imports, rep) if imports else []
    vrep = voices(t, man, os.path.dirname(os.path.abspath(manifest)), out) if man.get('voices') else None
    for s in natives:
        rep['songs'].append({'name': s['name'], 'cmd': int(s['cmd'], 16), 'source': f"kof98 ${s['cmd'].upper()}",
                             'bank_set': m1[t.bt + int(s['cmd'], 16) - 0x20], 'native': True, 'loops': nloops[s['name']],
                             'kof98_hz_after_losses': 166.83 * song98.Song(bytes(old), int(s['cmd'], 16)).tempo / 208})
    # 5. ports
    free = [0x27] + [c for c in music if c not in keep_cmds and c != 0x27]
    cmds = {s['name']: int(s['cmd'], 16) for s in natives}
    for s in ports:
        dst = free.pop(0)
        p = port98.Port(t, s['source'], int(s['cmd'], 16), dst)
        p.build()
        r = dict(p.report, name=s['name'])
        rep['songs'].append(r); cmds[s['name']] = dst
        print(f"{s['name']}: {s['source']} ${s['cmd']} -> ${dst:02X} bank set {p.at[0]} at ${p.at[1]:04X}, tempo {p.T} x{p.k} "
              f"({p.report['tempo_error_pct']:+.2f} %), "
              f"{p.report['song_bytes']} bytes, {p.report['samples']['bytes'] // 1024} KB of samples", flush=True)
    # 5b. menu sounds: SSG cues on KOF98's generated-sound path (type 5), in the fixed area's free bytes
    cue_ranges, cue_cmds = [], {}
    if man.get('ssg'):
        cue_ranges, cue_cmds, rep['ssg'] = ssg_cues.build(m1, man['ssg'])
        print(f"ssg cues: {', '.join(f'{n} ${c:02X}' for n, c in cue_cmds.items())} ({rep['ssg']['bytes']} bytes)", flush=True)
    # 6. the fixed 32 KB changed only where the build writes: sample tables, song pointers / bank bytes, $2440, cues
    ok = [(A_TABLES[sl], A_TABLES[sl] + 6 * A_CODES[sl]) for sl in range(7)] + [(SLOT7, SLOT7 + SLOT7_SIZE * CODES),
          (t.brecs, t.brecs + 13 * t.n_brecs), (0x329E, 0x329E + 2 * 0x60), (t.bt, t.bt + 0x60), (0x2440, 0x2442)] + \
         [tuple(r) for r in (vrep or {}).get('enable_maps', [])] + cue_ranges + imp_ranges
    bad = [i for i in range(0x8000) if m1[i] != old[i] and not any(a <= i < b for a, b in ok)]
    assert not bad, f'fixed area changed outside the tables: {[hex(i) for i in bad[:8]]}'
    # 7. sizes, files
    nsets = max(t.sets) + 1
    m_size = 0x8000 * (nsets + 1)
    v_used = len(t.v)
    v_size = (v_used + 0xFFFF) & ~0xFFFF
    os.makedirs(out, exist_ok=True)
    open(f'{out}/m1.bin', 'wb').write(bytes(m1[:m_size]))
    open(f'{out}/v1.bin', 'wb').write(bytes(t.v) + bytes(v_size - v_used))
    with open(f'{out}/songs.h', 'w') as h:
        h.write(f'/* generated by tools/port/build_snd.py from {os.path.basename(manifest)}: KOF98 driver music commands */\n')
        h.write('#ifndef SONGS_H\n#define SONGS_H\n')
        for s in man['songs']:
            h.write(f"#define MUS_{s['name']:14s} 0x{cmds[s['name']]:02X}   /* {s['source']} ${s['cmd'].upper()}: {s.get('what', '')} */\n")
        for n, c in cue_cmds.items(): h.write(f"#define SSG_{n:14s} 0x{c:02X}   /* menu sound: SSG cue (ssg_cues.py) */\n")
        h.write(f"#define BOSS_SONGS {{ {', '.join('MUS_' + b for b in man['bosses'])} }}   /* {', '.join(man['bosses'])} */\n")
        h.write(f"#define N_BOSS_SONGS {len(man['bosses'])}\n")
        # the options screen's players (examples/brawler OPTIONS): every song and effect of the build, with a name
        lab = lambda s: s.get('label', s['name'].replace('_', ' '))[:16].upper()
        h.write(f"#define N_SONGS {len(man['songs'])}\n#define SONG_LIST {{ "
                + ', '.join(f'{{ MUS_{s["name"]}, "{lab(s)}" }}' for s in man['songs']) + ' }\n')
        names = man['sfx'].get('names', {})
        h.write(f"#define SFX_PREFIX 0x{man['sfx'].get('prefix', '1A').upper()}\n#define N_SFX {len(man['sfx']['codes'])}\n#define SFX_LIST {{ "
                + ', '.join(f'{{ 0x{c.upper()}, "{names.get(c, "EFFECT " + c.upper())[:16].upper()}" }}' for c in man['sfx']['codes']) + ' }\n')
        h.write('#endif\n')
    if vrep: rep['voices'] = vrep
    rep.update(m_bytes=m_size, bank_sets=nsets, v_bytes=v_size, v_used=v_used, v_kof98_kept=v_natives,
               kept_adpcm_a_records=len(keep_a), kept_adpcm_b_records=len(t.keep_b),
               v_gaps=[[a << 8, b << 8] for a, b in t.gaps])
    json.dump(rep, open(f'{out}/snd_report.json', 'w'), indent=1)
    print(f'M ROM {m_size // 1024} KB ({nsets} bank sets), V ROM {v_size / 2**20:.2f} MB '
          f'({v_used} bytes used, KOF98 kept {v_natives // 1024} KB)')
    return rep

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
