#!/usr/bin/env python3
"""The impact sound library (Bruno 2026-10-09: "scan attack scripts, build a list of addresses of impact sounds, build a
list into an artifact and show me a link for review (keep / discard / comment)"): every hit / impact sound of KOF94,
KOF95, KOF96 and Kizuna Encounter, found statically in each 68000 program and decoded straight from the ROMs.

    python3 impacts.py scan      -> OUT/impacts.json + OUT/wav/<id>.wav (one entry per distinct sample)
    python3 impacts.py check     the static decode against each game's own driver in our emulator's tap core
                                 (voices.probe: the ADPCM-A start / end it keys on), a few words per game

How (per game, the routines read in the disassembly; every table address is asserted on its code bytes):
1. The 68000 side: the code that sends a sound on a hit or an impact, and what it sends. Each game asks for sounds with
   an index into a word table (driver prefix << 8 | code):
   - KOF94 ($6588, table $51924; $656E = index + 0 / 1 / 2 by the object's x on screen: three pan variants) and KOF95
     ($6342, table $59A10): the hit spark spawner (KOF94 $58F0, KOF95 $54E0) picks the hit sound (a cycle of hit
     samples, a strong-hit set, the guard set, the projectile hit, the KO blow, per-move overrides for specials); the
     victim's reaction table (KOF94 $65AC, KOF95 $6366); the floor thuds when a knocked-down body lands (KOF94 $66EA /
     $66FE / $6706 / $670E, KOF95 $65A0 / $65C6 / $65E2: per fighter, the heavy ones have their own); the KO blow
     (KOF95 $6520); the throw scripts' sends (the engine's throw routines, KOF94 $A600-$CC68, KOF95 $AD00-$D750).
   - KOF96 ($6AA8, table $6CAD4): the victim's hit routine $16F7A runs the attacker's hit kind (+$1B8, set by each move:
     23 kinds, 0 = the normals: by the attack box's element and the strength, punch / kick); the hit spark objects
     (table 29, $24C00-$25200); the body hitting the floor (index $89); the stun check $14764.
   - Kizuna ($1D1B0: a spec word = index | random count << 10 | positional bit 14, index table $1D3CC; $1D39C: an
     index): the hit routine $1DB7A (by strength and stance $4DEEE / $4DF4E, per fighter and move $4E0CE / $4E2CE /
     $4E4CE, projectiles $4E6E6, weapons $4E6CE / $4E6DA), the guard $1DDE8, projectiles clashing $1DE46, and the
     sound words of the reaction animations every fighter shares (steps: trailer bit 3).
2. The driver side: prefix + code -> the effect slot's sample record -> the ADPCM-A sample(s) in the V ROM.
   MAKOTO v3 (KOF94, KOF95: docs/ff3_sound_driver.md "KOF94's build" / "KOF95's build"): 11-byte records
   [priority][start][end][loop count][loop start][loop end][pan|level]; KOF95's one-byte commands $C0-$FF are slot 0
   codes $73F4[cmd - $C0]. SNK Ver 0.x (KOF96, Kizuna: docs/kizuna_sound_driver.md): slot pointers $2E0E + 2 * slot,
   prefixes $18 $1A $1C $1E $1B $1D = slots 0-5, 6-byte records [priority][start][end][pan|level], slot 5 11 bytes.
3. Same sample bytes = one entry (every game / code / use listed with it); the WAV is the YM2610 ADPCM-A decode
   (18,518 Hz), trimmed and normalised. A sample identical to one of KOF98's named effects (the brawler's songs.json
   names) carries that name.
OUT = /data/neogeo_dict/sound/impacts (make_site.py copies impacts.json + wav/ to the site's impacts/)."""
import hashlib, json, os, re, struct, subprocess, sys, wave
from collections import OrderedDict
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
NEOSDK = os.path.join(TOOLS, 'neosdk')                      # (nested repo: voices.py's imports need its neogeo package)
if not os.path.isdir(NEOSDK): NEOSDK = os.path.expanduser('~/CLProjects/NeoGeo/tools/neosdk')
sys.path.insert(0, NEOSDK)
from voices import adpcm_a
OUT = '/data/neogeo_dict/sound/impacts'
WORK = os.path.join(OUT, 'work')
RATE = 18518
GAMES = ['kof94', 'kof95', 'kof96', 'kizuna']
TITLE = {'kof94': "KOF '94", 'kof95': "KOF '95", 'kof96': "KOF '96", 'kizuna': 'Kizuna Encounter'}
CASTS = {
    'kof94': ['Heidern', 'Ralf', 'Clark', 'Athena', 'Kensou', 'Chin', 'Kyo', 'Benimaru', 'Goro', 'Heavy D!', 'Lucky',
              'Brian', 'Kim', 'Chang', 'Choi', 'Terry', 'Andy', 'Joe', 'Ryo', 'Robert', 'Takuma', 'Yuri', 'Mai', 'King',
              'Rugal', 'Omega Rugal'],
    'kof95': ['Heidern', 'Ralf', 'Clark', 'Athena', 'Kensou', 'Chin', 'Kyo', 'Benimaru', 'Goro', 'Iori', 'Eiji', 'Billy',
              'Kim', 'Chang', 'Choi', 'Terry', 'Andy', 'Joe', 'Ryo', 'Robert', 'Takuma', 'Yuri', 'Mai', 'King', 'Saisyu',
              'Omega Rugal'],
    'kizuna': ['Hayate', 'Eagle', 'Gozu', 'Mezu', 'Rosa', 'Kim', 'Joker', 'Chung', 'Gordon', 'Shishioh', 'R Shishi',
               'A Chun', 'Jyazu', '?', '?', '?']}


# ---- ROMs ------------------------------------------------------------------------------------------------------------
class Rom:
    def __init__(self, game):
        raw = open(f'/data/roms/{game}.neo', 'rb').read()
        sz = struct.unpack('<6I', raw[4:28]); o = 0x1000
        P = raw[o:o + sz[0]]; o += sz[0] + sz[1]
        self.m1 = raw[o:o + sz[2]]; o += sz[2]
        self.v = raw[o:o + sz[3]]
        p = bytearray(P); p[0::2], p[1::2] = P[1::2], P[0::2]       # .neo P: words little-endian (MAME region order)
        assert p[0x100:0x107] == b'NEO-GEO', game
        self.p = bytes(p); self.game = game
        os.makedirs(WORK, exist_ok=True)
        self.path = os.path.join(WORK, f'{game}_p.bin')
        if not os.path.exists(self.path) or open(self.path, 'rb').read() != self.p: open(self.path, 'wb').write(self.p)
        self._ins = None
    def u8(self, a): return self.p[a]
    def u16(self, a): return struct.unpack_from('>H', self.p, a)[0]
    def u32(self, a): return struct.unpack_from('>I', self.p, a)[0]
    def m16(self, a): return self.m1[a] | self.m1[a + 1] << 8
    def has(self, a, hexbytes): return self.p[a:a + len(hexbytes) // 2] == bytes.fromhex(hexbytes)
    def ins(self):
        """the first MB disassembled, linear: [(address, text)] (objdump; data areas read as code are harmless here)"""
        if self._ins is None:
            d = os.path.join(WORK, f'{self.game}.dis')
            if not os.path.exists(d) or os.path.getmtime(d) < os.path.getmtime(self.path):
                with open(d, 'w') as f:
                    subprocess.run(['m68k-linux-gnu-objdump', '-D', '-b', 'binary', '-m', 'm68k', '--stop-address=0x100000', self.path], stdout=f, check=True)
            self._ins = []
            for l in open(d):
                m = re.match(r'\s+([0-9a-f]+):\t[0-9a-f ]+\t(.*)', l)
                if m: self._ins.append((int(m.group(1), 16), m.group(2).strip()))
        return self._ins
    def routine(self, a, n=60):
        """the instructions from a to the first rts / jmp / bra (straight-line walk of a small handler)"""
        out = []
        dis = subprocess.run(['m68k-linux-gnu-objdump', '-D', '-b', 'binary', '-m', 'm68k', f'--start-address={a}',
                              f'--stop-address={a + 4 * n}', self.path], capture_output=True, text=True).stdout
        for l in dis.split('\n'):
            m = re.match(r'\s+([0-9a-f]+):\t[0-9a-f ]+\t(.*)', l)
            if not m: continue
            out.append((int(m.group(1), 16), m.group(2).strip()))
            if re.match(r'(rts|jmp|bra)', out[-1][1]): break
        return out

    def calls(self, targets, lo=0, hi=0x100000):
        """[(site, d0 constant or None)]: calls of the request routines (jsr / bsr / jmp / bra) with the d0 set by
        a move / moveq in the four instructions before (None: d0 computed)"""
        I = self.ins(); out = []
        for k, (a, t) in enumerate(I):
            if not lo <= a < hi or not re.match(r'(jsr|bsr[wl]?|jmp|bra[wl]?|bne[wsl]?|beq[wsl]?) ', t): continue
            m = re.search(r'0x([0-9a-f]+)\)?$', t)
            if not m or int(m.group(1), 16) not in targets: continue
            v = None
            for b, u in reversed(I[max(0, k - 4):k]):
                mm = re.match(r'(moveq|movew) #(-?\d+),%d0$', u)
                if mm: v = int(mm.group(2)) & 0xFFFF; break
                if '%d0' in u: break
            out.append((a, v, int(m.group(1), 16)))
        return out


# ---- the drivers: prefix + code -> sample segments -------------------------------------------------------------------
def rec11(r):
    st, en, lc, ls, le = r[1] | r[2] << 8, r[3] | r[4] << 8, r[5], r[6] | r[7] << 8, r[8] | r[9] << 8
    if not lc: return [(st, en)]
    seg = [(st, le)] + [(ls, le)] * (1 if lc == 0xFF else lc)
    if en > le: seg.append((le + 1, en))
    return seg

MAKOTO = {   # slot record tables / enable bitmaps (docs/ff3_sound_driver.md), KOF95 one-byte code table $73F4
    'kof94': dict(pre={0x18: 0, 0x1A: 1, 0x1C: 2}, recs=[0x3E73, 0x4973, 0x5473], bits=[0x3E13, 0x3E33, 0x3E53]),
    'kof95': dict(pre={0x18: 0, 0x1A: 1, 0x1C: 2, 0x1E: 3, 0x1B: 4}, recs=[0x425B, 0x4D5B, 0x5850, 0x6350, 0x6B90],
                  bits=[0x41BB, 0x41DB, 0x41FB, 0x421B, 0x423B], onebyte=0x73F4)}
SNK_PRE = {0x18: 0, 0x1A: 1, 0x1C: 2, 0x1E: 3, 0x1B: 4, 0x1D: 5}   # the prefix commands' handlers ($0C17 / $0C18 table)

def sample(R, word):
    """{'slot', 'code', 'record', 'segments': [(start, end) 256-byte units], 'level'} or {'error': why}"""
    pre, code = word >> 8, word & 0xFF
    M = R.m1
    if R.game in MAKOTO:
        D = MAKOTO[R.game]
        if pre == 0 and code >= 0xC0 and 'onebyte' in D: slot, code, gated = 0, M[D['onebyte'] + code - 0xC0], False
        elif pre in D['pre']: slot, gated = D['pre'][pre], True
        else: return {'error': f'not an ADPCM-A effect command ({word:04X})'}
        if gated:                                            # prefix path: the slot's enable bitmap ($0E58 / $0B3F)
            if code < 0x10 or not M[D['bits'][slot] + (code >> 3)] & (0x80 >> (code & 7)):
                return {'error': f'refused by the driver (slot {slot} code ${code:02X} not enabled)'}
        a = D['recs'][slot] + 11 * code; r = M[a:a + 11]
        seg = rec11(r)
    else:
        if pre not in SNK_PRE: return {'error': f'not an ADPCM-A effect command ({word:04X})'}
        slot = SNK_PRE[pre]; base = R.m16(0x2E0E + 2 * slot); size = 11 if slot == 5 else 6
        a = base + size * code; r = M[a:a + size]
        seg = rec11(r) if size == 11 else [(r[1] | r[2] << 8, r[3] | r[4] << 8)]
    if not any(e >= s and (s or e) for s, e in seg): return {'error': f'empty record (slot {slot} code ${code:02X})'}
    return {'slot': slot, 'code': code, 'record': r.hex(), 'rec_at': a, 'segments': seg, 'level': r[-1]}

TYPES = {'kof94': 0x6907, 'kof95': 0x72B4}                  # MAKOTO command -> type (5 = an SSG effect song)
BLOCK = {'kof94': 850, 'kof95': 870, 'kof96': 878, 'kizuna': 880}   # the frame after the game's $07 (makoto3 / kof98snd games)

def ssg_capture(game, cmds, frames=150):
    """the SSG effect songs (no sample: a sequence the driver plays on the SSG) in our emulator's tap core
    (tools/makoto3/capture.py Sound): power on, the game's own commands blocked after its $07, the command sent, the
    core's audio for `frames` frames -> {cmd: wav path, ms}"""
    code = f'''
import sys, json, struct, wave
sys.path.insert(0, {os.path.join(TOOLS, 'makoto3')!r})
import capture as mk
import numpy as np
mk.GAME = {game!r}
s = mk.Sound(work={os.path.join(WORK, 'save_' + game)!r})
s.run({BLOCK[game]}); s.block = {BLOCK[game]}; s.run(20)
base = s.save(); out = {{}}
class Buf:
    def __init__(self): self.b = []
    def write(self, d): self.b.append(d)
for c in {list(cmds)!r}:
    s.load(base); B = Buf(); s.wav = B
    s.send(c); s.run({frames}); s.wav = None
    a = np.frombuffer(b''.join(B.b), np.int16).astype(np.float64).reshape(-1, 2).mean(1)
    loud = np.nonzero(np.abs(a) > 200)[0]
    if not len(loud): out[c] = None; continue
    a = a[max(0, loud[0] - 50):loud[-1] + 1600]
    a = a / np.abs(a).max() * 0.89 * 32767
    p = {os.path.join(OUT, 'wav')!r} + '/ssg_{game}_%02X.wav' % c
    with wave.open(p, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(55555); w.writeframes(a.astype(np.int16).tobytes())
    out[c] = [p, round(len(a) * 1000 / 55555)]
print(json.dumps(out))
'''
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    return {int(k): v for k, v in json.loads(r.stdout.strip().split('\n')[-1]).items()}

def pcm(R, seg):
    out = []
    for s, e in seg: out += adpcm_a(R.v[s << 8:(e + 1) << 8])
    return np.array(out, np.float64)

def write_wav(path, a):
    loud = np.nonzero(np.abs(a) > 64)[0]                    # (the record's tail is silence)
    a = a[:loud[-1] + int(RATE * 0.03)] if len(loud) else a
    a = a / max(1, np.abs(a).max()) * 0.89 * 32767           # normalised to -1 dBFS
    n = min(len(a), int(RATE * 0.006)); a[-n:] *= np.linspace(1, 0, n)
    with wave.open(path, 'wb') as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(RATE); o.writeframes(a.astype(np.int16).tobytes())
    return round(len(a) * 1000 / RATE)


# ---- the 68000 side: what each game sends on hits and impacts ---------------------------------------------------------
class Uses:
    """word -> [use]; a use = {'what': text, 'where': text, 'sites': [hex addresses]}"""
    def __init__(self, R, table):
        self.R, self.table, self.d = R, table, OrderedDict()
    def W(self, i): return self.R.u16(self.table + 2 * i)
    def add(self, word, what, where, sites=()):
        if word in (0, 1, 2) or word >> 8 in (0x01, 0x03, 0x04, 0x05, 0x06, 0x0A): return   # 'nothing' / system words
        L = self.d.setdefault(word, [])
        s = sorted({f'${x:X}' for x in sites})
        for u in L:
            if u['what'] == what: u['sites'] = sorted(set(u['sites']) | set(s)); return
        L.append({'what': what, 'where': where, 'sites': s})
    def idx(self, i, what, where, sites=(), pos=False):
        for k in (range(3) if pos else [0]): self.add(self.W(i + k), what + (f' (pan {"LCR"[k]})' if pos else ''), where, sites)

def immediates(R, a, regs=('d0', 'd1')):
    """the indices a small handler moves into d0 / d1 before its sends, in order"""
    out = []
    for b, t in R.routine(a):
        m = re.match(r'(movew|moveq) #(-?\d+),%(d[01])$', t)
        if m and m.group(3) in regs: out.append(int(m.group(2)) & 0xFFFF)
    return out


def kof94(R):
    U = Uses(R, 0x51924)
    assert R.has(0x6588, '41f900051924'), 'KOF94 request'
    assert R.has(0x656E, '222c0018'), 'KOF94 positional request'
    # the hit spark spawner $58F0 (a4 the victim, a3 the attacker)
    assert R.has(0x595E, '41fa009a') and R.has(0x596A, '41fa009a'), 'KOF94 spark tables'
    for k in range(3):
        U.idx(R.u16(0x59FA + 2 * k), f'Hit (cycle of three, no. {k + 1})', 'hit spark $58F0, table $59FA', [0x59AE], pos=True)
        U.idx(R.u16(0x5A06 + 2 * k), f'Strong hit (attack strength 3, cycle no. {k + 1})', 'hit spark $58F0, table $5A06', [0x59AE], pos=True)
        U.idx(R.u16(0x5A00 + 2 * k), f'Guarded / special victim state (+$7A bit 6, cycle no. {k + 1})', 'hit spark $58F0, table $5A00', [0x598A], pos=True)
    assert R.has(0x590C, '303c0118') and R.has(0x5920, '303c00e7')
    U.idx(0x118, 'Projectile hit', 'hit spark $58F0 ($590C)', [0x590C], pos=True)
    U.add(U.W(0x228), 'KO blow (the victim\'s life at 0)', 'hit spark $58F0 ($5992)', [0x5992])
    U.add(U.W(0x273), 'Hit on Chang (fighter 13) in his special state', 'hit spark $58F0 ($59B8)', [0x59B8])
    # per-move overrides (attacker +$10D: its special's number; +2 the second table when +$E3 bit 1): the specials' impacts
    assert R.has(0x59E2, '41f900050ece') and R.has(0x59EE, '41f9000510e6')
    for t, life in ((0x50ECE, ''), (0x510E6, ' (KO blow)')):
        cnt = {}
        for k in range(268):
            i = R.u16(t + 2 * k)
            if i != 2: cnt.setdefault(i, []).append(k)
        for i, ks in cnt.items():
            U.add(U.W(i), f'Special move hit{life}: ' + (f'{len(ks)} moves use it' if len(ks) > 1 else 'one move uses it'), f'per-move table ${t:X} (attacker +$10D)', [t + 2 * ks[0]])
    # the victim's reaction table $65AC ($516CC + fighter): positional
    assert R.has(0x65AC, '41f9000516cc')
    for i in sorted({R.u16(0x516CC + 2 * k) for k in range(26 * 8)} - {0}):
        U.idx(i, 'Body hit (the victim\'s reaction sound)', 'reaction table $516CC ($65AC)', [0xA576, 0xA5D8, 0xA6FE, 0xA7AA], pos=True)
    # a knocked-down body landing ($66EA / $66FE after the floor check $2E7E; $6706 / $670E: per fighter)
    assert R.has(0x66EA, '303c0105') and R.has(0x66F6, '303c0227')
    U.idx(0x105, 'Body lands on the floor', '$66EA / $66FE (after the floor check)', [0x8488, 0x8C7C], pos=True)
    U.add(U.W(0x227), 'Body lands on the floor, KO', '$66F6', [0x66F6])
    for t, what in ((0x518AC, 'Body falls / bounces'), (0x518E8, 'Landing dust (thud)')):
        by = {}
        for c in range(26):
            i = R.u16(t + 2 * c)
            if i != 2: by.setdefault(i, []).append(CASTS['kof94'][c])
        for i, cs in by.items():
            U.idx(i, f'{what}: ' + (', '.join(cs) if len(cs) < 8 else f'{len(cs)} fighters'), f'per-fighter table ${t:X}', [], pos=True)
    # the throw scripts (engine throw routines $A600-$CC68): their constant sends
    for a, v, _ in R.calls({0x6588, 0x656E, 0x655E}, 0xA600, 0xCC68):
        if v is not None: U.add(U.W(v), f'Throw script (index ${v:X})', f'throw routine ${a:X}', [a])
    return U


def kof95(R):
    U = Uses(R, 0x59A10)
    assert R.has(0x6342, '41f900059a10'), 'KOF95 request'
    # the hit spark spawner $54E0: a cycle of 8 ($5E66 & 7) in $5674, the victim with +$7C bit 6 reads 5 entries on ($567E)
    assert R.has(0x5552, '41fa0120') and R.has(0x5572, '30300010')
    for k in range(8):
        U.idx(R.u16(0x5674 + 2 * k), f'Hit (cycle of eight, no. {k + 1})', 'hit spark $54E0, table $5674', [0x559E])
        U.idx(R.u16(0x567E + 2 * k), f'Hit, victim +$7C bit 6 (cycle no. {k + 1})', 'hit spark $54E0, table $5674 + 10', [0x5572])
    assert R.has(0x551C, '303c000d') and R.has(0x55A8, '303c0164')
    U.idx(0x0D, 'Projectile hit', 'hit spark $54E0 ($551C)', [0x551C])
    U.idx(0x164, 'Hit on Chang (fighter 13) in his special state', 'hit spark $54E0 ($55A8)', [0x55A8])
    for k in range(4): U.idx(R.u16(0x5664 + 2 * k), 'Hit sound, random of four ($5664)', 'hit spark $54E0 ($564E)', [0x5660])
    # the KO blow ($6520 and the spark's $55D6): two sends, by the attacker's +$152
    for i in (0x12, 0x13): U.idx(i, 'KO blow', '$6520 / $55D6 (the victim\'s life at 0)', [0x653C, 0x6554])
    for i in (0x24, 0x25): U.idx(i, 'KO blow (attacker +$152 = 1)', '$6520 / $55D6', [0x656E, 0x6586])
    # the victim's reaction table $6366 ($5967C + fighter +$188, by reaction)
    assert R.has(0x6366, '41f90005967c')
    for i in sorted({R.u16(0x5967C + 2 * k) for k in range(26 * 8)} - {0, 2}):
        U.idx(i, 'Body hit (the victim\'s reaction sound)', 'reaction table $5967C ($6366)', [0xA242, 0xA7E6, 0xA90C, 0xA9B8])
    # a knocked-down body landing ($65A0 / $65C6 / $65E2 after the floor check $2724): per fighter
    assert R.has(0x65B0, '303c0019') and R.has(0x65BE, '303c0021')
    U.idx(0x19, 'Body lands on the floor', '$65A0 (after the floor check)', [0x65B0])
    U.idx(0x21, 'Body lands on the floor (stage mode 5)', '$65A0', [0x65BE])
    for t, what in ((0x59998, 'Body lands on the floor'), (0x599D4, 'Body lands on the floor (stage mode 5)'), (0x5985C, 'Body falls / bounces')):
        by = {}
        for c in range(26):
            i = R.u16(t + 2 * c)
            if i != 2: by.setdefault(i, []).append(CASTS['kof95'][c])
        for i, cs in by.items():
            U.idx(i, f'{what}: ' + (', '.join(cs) if len(cs) < 8 else f'{len(cs)} fighters'), f'per-fighter table ${t:X}', [])
    # the victim burnt / shocked: an attack box of element $70 ($A3C6: reaction state 101 + two effect objects)
    assert R.has(0xA3FE, '303c0022')
    U.idx(0x22, 'Victim burnt / shocked (attack element $70, reaction 101)', '$A3C6', [0xA402])
    for a, v, _ in R.calls({0x6342, 0x6318}, 0xAD00, 0xD750):
        if v is not None: U.add(U.W(v), f'Throw script (index ${v:X})', f'throw routine ${a:X}', [a])
    return U


def kof96(R):
    U = Uses(R, 0x6CAD4)
    assert R.has(0x6AA8, '41f90006cad4'), 'KOF96 request'
    assert R.has(0x16F7A, '7000102c01316b00'), 'KOF96 hit kind dispatcher'
    setters = {}
    for a, t in R.ins():
        m = re.match(r'moveb #(-?\d+),%a4@\(440\)$', t)
        if m: setters.setdefault(int(m.group(1)) & 0xFF, []).append(a)
    rnd4 = [R.u16(0x1722A + 2 * k) for k in range(4)]                 # $1720C: one of four at random
    assert R.has(0x1720C, '4eb900002b2c')
    def handler(a):
        out = immediates(R, a)
        if any('0x1720c' in t for _, t in R.routine(a)): out = rnd4 + out
        return out
    for k in range(1, 23):
        h = R.u32(0x16FD6 + 4 * k); n = len(setters.get(k, []))
        for i in handler(h):
            U.idx(i, f'Hit kind {k}' + (f' (set by {n} move routines)' if n else ''), f'victim hit routine $16F7A, kind handler ${h:X}', setters.get(k, [])[:6])
    # kind 0, the normals: the attack box's element (+$132 = attacker +$7E & $70) picks the handler
    assert R.has(0x17032, '7000102c0132')
    for e in range(8):
        h = R.u32(0x1704C + 4 * e)
        if h == 0x1706C:                                              # element 0 / 7: by strength (+$133), punch / kick
            assert R.has(0x17080, '41fa0010')
            for s in range(6):
                for kick, off in ((0, 0), (1, 6)):
                    U.idx(R.u16(0x17092 + 2 * (s + off)), f'Normal hit, strength {s}, {"kick" if kick else "punch"}', 'victim hit routine, kind 0 ($1706C, table $17092)', [0x1708A])
        else:
            for i in handler(h): U.idx(i, f'Normal hit, attack element {e}', f'victim hit routine, kind 0 element handler ${h:X}', [h])
    # the hit spark objects (effect table 29: the spawner's state routines)
    # the guard ($172F0 from the victim's guard branches $15036 / $15180: light / heavy by strength) and the push back
    assert R.has(0x172F0, '303c0070') and R.has(0x1730A, '303c0088')
    for i, w in zip(immediates(R, 0x172F0), ('light', 'heavy (strength 2+)')): U.idx(i, f'Guard (blocked hit), {w}', 'victim guard $15036 / $15180 -> $172F0', [0x17302])
    U.idx(0x88, 'Victim pushed back (slide)', '$1730A from $15460 / $16514', [0x1730E])
    # the hit spark objects (effect table 29): each send, then the effect state it shows
    I = R.ins(); at = {a: k for k, (a, _) in enumerate(I)}
    for a, v, _ in R.calls({0x6AA8}, 0x24C00, 0x25200):
        if v is None: continue
        st = next((m.group(1) for _, t in I[at[a]:at[a] + 8] for m in [re.match(r'movew #(\d+),%a4@\(114\)$', t)] if m), None)
        U.idx(v, 'Hit spark object' + (f' (spark state {st})' if st else ''), f'spark routine ${a:X}', [a])
    for a, v, _ in R.calls({0x6AA8}):
        if v == 0x89: U.idx(v, 'Body hits the floor', 'index $89', [a])
    for i in immediates(R, 0x14764): U.idx(i, 'Hit with the stun check ($14764, 1 in 4)', 'victim $1489C -> $14764', [0x147BA, 0x147C4])
    return U


def kizuna(R):
    sys.path.insert(0, os.path.join(TOOLS, 'kizuna'))
    U = Uses(R, 0x1D3CC)
    assert R.has(0x1D39C, 'd040303b002c'), 'Kizuna index request'
    assert R.has(0x1D1B0, '48e740804a40'), 'Kizuna spec request'
    def spec(s):
        i, n = s & 0x3FF, (s >> 10) & 15
        if i >= 0x3C0:
            a = 0x4DE54 + R.u16(0x4DE54 + 2 * (0x3FF - i))
            return [R.u16(a + 2 + 2 * k) for k in range(3 if s & 0x4000 else R.u16(a))]
        if s & 0x4000: return [i, i + n + 1, i + 2 * (n + 1)]              # positional ($1D32C): left / middle / right
        return [i + k for k in range(n + 1 if n else 1)]                    # random of n + 1 ($1D2D2)
    def add_spec(s, what, where, sites):
        ix = spec(s); pos = bool(s & 0x4000) and len(ix) == 3
        for k, i in enumerate(ix): U.add(U.W(i), what + (f' (pan {"LCR"[k]})' if pos else f' (random {k + 1} of {len(ix)})' if len(ix) > 1 else ''), where, sites)
    assert R.has(0x1DCF6, '41f90004deee') and R.has(0x1DD00, '41f90004df4e')
    for k in range(48):
        st = ['standing', 'crouching', 'in the air'][k // 16]
        for t, sec in ((0x4DEEE, ''), (0x4DF4E, ', second sound')):
            s = R.u16(t + 2 * k)
            if s: add_spec(s, f'Hit, strength {k % 16}, attacker {st}{sec}', f'hit routine $1DB7A, table ${t:X}', [0x1DD22, 0x1DD2C])
    for t, what in ((0x4E0CE, 'Special hit'), (0x4E2CE, 'Special hit (guard-crush flag)'), (0x4E4CE, 'Special hit (flag bit 7)'), (0x4E6E6, 'Projectile hit')):
        by = {}
        for k in range(256):
            s = R.u16(t + 2 * k)
            if s not in (0, 0xFFFF) and CASTS['kizuna'][k >> 4] != '?': by.setdefault(s, []).append(CASTS['kizuna'][k >> 4])
        for s, cs in by.items():
            add_spec(s, f'{what}: ' + ', '.join(sorted(set(cs))) + f' ({len(cs)} move{"s" if len(cs) > 1 else ""})', f'hit routine $1DB7A, per-move table ${t:X}', [0x1DC3C])
    for t, what in ((0x4E6CE, 'Weapon hit'), (0x4E6DA, 'Weapon hit (guard-crush flag)')):
        for k in range(6):
            add_spec(R.u16(t + 2 * k), f'{what} ({["standing", "crouching", "air"][k % 3]}, set {k // 3 + 1})', f'hit routine $1DB7A, table ${t:X}', [0x1DC86])
    add_spec(0x2164, 'Hit (random of nine)', 'hit routine $1DB7A ($1DBA8)', [0x1DBAC])
    for t, what in ((0x4DFCE, 'Hit by a thrown object'), (0x4DFAE, 'Hit, guard-crush flag')):
        by = {}
        for c in range(13): by.setdefault(R.u16(t + 2 * c), []).append(CASTS['kizuna'][c])
        for i, cs in by.items(): U.idx(i, f'{what}: ' + (', '.join(cs) if len(cs) < 6 else f'{len(cs)} fighters'), f'hit routine $1DB7A, table ${t:X}', [0x1DD46])
    U.idx(0x188, 'Hit, listed attacks ($4DFEE bits)', 'hit routine $1DB7A ($1DCC0)', [0x1DCC4])
    U.idx(0x186, 'Hit by Rosa\'s attack $1A0', 'hit routine $1DB7A ($1DDD6)', [0x1DDDA])
    # the guard $1DDE8 (hit code $7F or the victim guarding)
    assert R.has(0x1DDF4, '303c456f') and R.has(0x1DE02, '303c4570')
    add_spec(0x456F, 'Guard (blocked hit)', 'guard $1DDE8', [0x1DE1E]); add_spec(0x4570, 'Guard (blocked hit), victim +$12B bit 1', 'guard $1DDE8', [0x1DE1E])
    by = {}
    for c in range(13): by.setdefault(R.u16(0x4E08E + 2 * c), []).append(CASTS['kizuna'][c])
    for i, cs in by.items(): U.idx(i, 'Guarded projectile: ' + (', '.join(cs) if len(cs) < 6 else f'{len(cs)} fighters'), 'guard $1DDE8, table $4E08E', [0x1DE40])
    by = {}
    for c in range(13): by.setdefault(R.u16(0x4E0AE + 2 * c), []).append(CASTS['kizuna'][c])
    for i, cs in by.items(): U.idx(i, 'Projectiles clash: ' + (', '.join(cs) if len(cs) < 6 else f'{len(cs)} fighters'), '$1DE46 (from $2B3E6), table $4E0AE', [0x1DE5C])
    # the reaction animations every fighter shares: their steps' sound words (sent as the step starts)
    import kz
    shared = {}
    for ch in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12):
        for n in range(0x80, 0xA0):
            try: steps = kz.parse_anim(ch << 12 | n)
            except Exception: continue
            for k, s in enumerate(steps or []):
                if s['sound'] is not None: shared.setdefault((n, k, s['sound']), set()).add(ch)
    for (n, k, s), chs in sorted(shared.items()):
        if len(chs) >= 9: add_spec(s, f'Reaction animation {n} step {k} (every fighter)', 'animation step sound word', [])
    return U

SCANS = {'kof94': kof94, 'kof95': kof95, 'kof96': kof96, 'kizuna': kizuna}
ORDER = ['Hit', 'Normal hit', 'Strong hit', 'Hit kind', 'Special', 'Projectile', 'Weapon', 'Guard', 'Body hit', 'Body',
         'Landing', 'Reaction', 'KO', 'Throw']


def kof98_names():
    """sample hash -> 'KOF98 $1Axx NAME' for the effects the brawler names (songs.json sfx names, KOF98's slot 1)"""
    R = Rom('kof98')
    names = json.load(open(os.path.join(TOOLS, '..', 'examples', 'brawler', 'songs.json')))['sfx']['names']
    out = {}
    for c, n in names.items():
        s = sample(R, 0x1A00 | int(c, 16))
        if 'segments' in s: out[hashlib.sha1(b''.join(R.v[a << 8:(b + 1) << 8] for a, b in s['segments'])).hexdigest()] = f'KOF98 $1A{c} {n}'
    return out


def scan():
    os.makedirs(os.path.join(OUT, 'wav'), exist_ok=True)
    k98 = kof98_names()
    lib, bad = OrderedDict(), []
    for g in GAMES:
        R = Rom(g); U = SCANS[g](R)
        n = 0; ssg = {}
        for word, uses in U.d.items():
            s = sample(R, word)
            if 'error' in s and g in TYPES and word < 0x100 and R.m1[TYPES[g] + word] == 5: ssg[word] = uses; continue
            if 'error' in s: bad.append({'game': g, 'word': f'{word:04X}', 'why': s['error'], 'uses': uses}); continue
            raw = b''.join(R.v[a << 8:(b + 1) << 8] for a, b in s['segments'])
            h = hashlib.sha1(raw).hexdigest()
            e = lib.get(h)
            if e is None:
                e = lib[h] = {'id': h[:10], 'bytes': len(raw), 'entries': [], 'kof98': k98.get(h)}
                e['ms'] = write_wav(os.path.join(OUT, 'wav', h[:10] + '.wav'), pcm(R, s['segments']))
            e['entries'].append({'game': g, 'word': f'{word:04X}', 'slot': s['slot'], 'code': f'{s["code"]:02X}',
                                 'record': s['record'], 'rec_at': f'${s["rec_at"]:04X}',
                                 'vrom': [[f'${a << 8:06X}', f'${(b + 1 << 8) - 1:06X}'] for a, b in s['segments']], 'uses': uses})
            n += 1
        for c, got in (ssg_capture(g, sorted(ssg)) if ssg else {}).items():   # SSG effect songs: captured, not decoded
            if got is None: bad.append({'game': g, 'word': f'{c:04X}', 'why': 'SSG effect: silent in the capture', 'uses': ssg[c]}); continue
            lib[f'ssg-{g}-{c:02X}'] = {'id': f'ssg_{g}_{c:02X}', 'ms': got[1], 'bytes': 0, 'kof98': None, 'ssg': True,
                                       'entries': [{'game': g, 'word': f'{c:04X}', 'slot': None, 'code': f'{c:02X}', 'record': '',
                                                    'rec_at': '', 'vrom': [], 'uses': ssg[c],
                                                    'note': 'SSG effect song (type 5): the driver plays a sequence on the SSG; captured in our emulator'}]}
            n += 1
        print(g, n, 'words', flush=True)
    rank = lambda w: next((i for i, p in enumerate(ORDER) if w.startswith(p)), len(ORDER))
    out = []
    for e in lib.values():
        e['games'] = [g for g in GAMES if any(x['game'] == g for x in e['entries'])]
        e['rank'] = min(rank(u['what']) for x in e['entries'] for u in x['uses'])
        out.append(e)
    out.sort(key=lambda e: (GAMES.index(e['games'][0]), e['rank'], e['entries'][0]['word']))
    per = {g: sum(1 for e in out for x in e['entries'] if x['game'] == g) for g in GAMES}
    only = {g: sum(1 for e in out if e['games'][0] == g) for g in GAMES}
    res = {'about': __doc__.split('\n\n')[0], 'words_per_game': per, 'samples_first_in_game': only, 'samples': len(out),
           'sounds': out, 'not_decoded': bad}
    json.dump(res, open(os.path.join(OUT, 'impacts.json'), 'w'), indent=1)
    print('words per game', per, '| distinct samples', len(out), '| not decoded', len(bad))
    for b in bad: print('  !!', b['game'], b['word'], b['why'], b['uses'][0]['what'])


def check(n=4):
    """the static decode against the game's own driver (voices.probe, our emulator's tap core)"""
    import voices
    voices.BLOCK.update({'kof94': 850, 'kof95': 870, 'kizuna': 880})
    J = json.load(open(os.path.join(OUT, 'impacts.json')))
    for g in GAMES:
        R = Rom(g)
        words = [int(x['word'], 16) for e in J['sounds'] for x in e['entries'] if x['game'] == g][::7][:n]
        got = voices.probe(g, words)
        for w in words:
            mine = [list(x) for x in sample(R, w)['segments']]; theirs = (got.get(w) or {}).get('segments')
            print(g, f'{w:04X}', 'OK' if theirs and theirs[:len(mine)] == mine else f'DIFF static {mine} driver {theirs}', flush=True)


if __name__ == '__main__':
    {'scan': scan, 'check': check}[sys.argv[1] if len(sys.argv) > 1 else 'scan']()
