#!/usr/bin/env python3
"""The Character Lab's character packs and THE PACK FORMAT (docs/character_lab.md "The pack format"; Bruno 2026-10-10:
"one lab build and two exported data sets, two characters we could dynamically swap", then "why would the packs need a
rebuild? that's insane": an engine or game change rebuilds the shell, never the packs).

    lab_pack.py seal BUILD                       (the Makefile, after the link of a shell / pack build: the slot header +
                                                  the anchor written into BUILD/rom.elf)
    lab_pack.py make F --shell SHELL_BUILD SHELL.neo --build BUILD PACK.neo -o OUT.pack [--strict]
                                                 (examples/brawler: make LAB_PACK=F [STRICT=1])
    lab_pack.py info PACK | anchor SHELL.neo | check PACK SHELL.neo | apply SHELL.neo PACK OUT.neo

THE SHELL (make LAB_SHELL=1 -> lab-shell.neo) is the game with one more roster fighter, the SLOT (the last index), whose
data sits in places a pack can fill without knowing the shell's code:
  P  $E0000-$FFFFF: the slot HEADER (LABHDR_AT: the slot's element of every per-fighter table, HDR_ARRAYS, + bm_lab + its
     16 retime rows; examples/brawler/labslot.h copies them into RAM tables at every reset, the slot's id and its LAB
     special's fighter resolved to the shell's) then .labslot (its first-MB tables);              fixed (FORMAT)
  P  the slot's P2 bank (its banked tables: addresses in the bank window, $200000+)            relocated: any bank
  S  its HUD face (16 fix tiles at PORTRAIT_TILE + slot * 16)                                  relocated
  M  its voice records in the KOF98 driver's two overflow voice slots + their enable bits      relocated
  V  its voice samples (build_snd.py SLOT_V_AT: the records name absolute V addresses)          fixed (FORMAT)
  C  its tiles (export_bm.py SLOT_TILE_FIRST, SLOT_TILES: its frames name absolute tiles)      fixed (FORMAT)
Its ANCHOR (LABANCHOR_AT, 16 KB of the first MB) says where: 'NGLA', the format, the slot id, the features string and
each region (kind, ROM, offset, size), then a JSON for the Player and the pages (the RAM map, the layout, the roster, the
chain rules). The shell's code and every other table may move freely: nothing in a pack points at them.

Scanned 2026-10-10 (robert / kim / iori / hanzo_ss2: every relocation of their slot sections and slot elements): the
only references out of the slot regions were the slot's elements of the per-fighter tables (now the header) and the
game-wide NUMBERED tables a fighter's data indexes: the victim postures (bchar_t.vposes is indexed by the whole list),
the source reactions (bm_sreact) and the shared effect palettes (bm_sfx_pals). Those are "shared ids": the shell's
features name them (vp:<hash>, sr<i>:<hash>, sp<i>:<key>), a pack needs the ones it uses.

COMPATIBILITY = FORMAT + FEATURES: the shell declares {format N, features: the program ops it plays (P_* names), the knob
kinds it reads (knob-*), lab (the LAB special), try2 (TRY blob v2: knob rows), its shared ids}; a pack declares {format N,
needs: what its data uses}; it loads iff same format and needs <= features (pack_swap.c, the Player, tryit.js, here).
FORMAT changes only when the slot's ABI changes (a header table's element, a region's fixed place, a struct the pack's
data is made of, an op renumbered): abi_signature() guards it (FORMATS: a changed signature stops the build).

The file (little-endian; the container Player 0.0.28-0.0.32 read): 'NGPK', u16 1, u16 regions, u32 manifest bytes, u32 x 6
the ROM sizes of its build, the manifest (JSON, starting {"ngpk":{"format":N,"needs":"..."}: pack_swap.c reads it there),
then per region (4-byte aligned): u8 rom (0 P, 1 S, 2 M, 3 V1, 4 V2, 5 C), u8 kind (KINDS), u8 flags (1 relocated), u8 0,
u32 offset (its build's), u32 length, u32 zeros, the length bytes, then zeros bytes of 0 written after them."""
import argparse, hashlib, json, os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
GAME = os.path.join(REPO, 'examples', 'brawler')
MAGIC, VERSION = b'NGPK', 1                  # the container (unchanged: the Players 0.0.28+ read it)
FORMAT = 1                                   # THE PACK FORMAT (labslot.h LAB_FORMAT, pack_swap.c, CharacterLab.kt, tryit.js)
ROMS = ['P', 'S', 'M', 'V1', 'V2', 'C']
LABANCHOR_AT, LABANCHOR_SIZE = 0xDC000, 0x4000   # examples/brawler/Makefile LABANCHOR_AT (main.c .labanchor)
LABHDR_AT, LABHDR_SIZE = 0xE0000, 0x400          # Makefile LABHDR_AT (main.c .labhdr, labslot.h)
LABSLOT_AT = 0xE0400                             # Makefile LABSLOT_AT: .labslot runs to the end of the first MB
SLOT_P_SIZE = 0x100000 - LABHDR_AT               # the fixed P region: the header + .labslot
BANK = 0x100000; BANK_CAP = BANK - 16            # a P2 bank (its last 16 bytes: the bank register)
# the region kinds (pack and anchor); relocated ones go where the shell's anchor says
KINDS = {'slot': 1, 'bank': 2, 'face': 3, 'tiles': 4, 'voices': 5, 'm0': 6, 'm1': 7, 'm2': 8, 'm3': 9}
RELOC = {'bank', 'face', 'm0', 'm1', 'm2', 'm3'}
# the per-fighter tables whose slot element the header carries, in labslot.h / main.c lab_arrs order
HDR_ARRAYS = ['bm_chars', 'bm_seg', 'bm_air', 'bm_hsnd', 'bm_xthr', 'bm_hspark', 'bm_head', 'ai_ready', 'gblitz_rom',
              'gblitz_can', 'grun_bob', 'grun_dash', 'gfury_area', 'gwalk_rom', 'pb_of_fighter', 'roster_unlock',
              'dtier_rom', 'portrait_pal', 'gknob_rom', 'gkcat_rom']
GRETIME_ROW, SLOT_RT_ROWS = 8, 16            # gretime_t; build_tables.py SLOT_RT_ROWS (before the 0xFF row)
FIX_TILE = 32                                # S ROM bytes a fix tile
SLOT_TILE_FIRST, SLOT_TILES = 2048, 24576    # export_bm.py: the slot's C block
SLOT_V_AT, SLOT_V = 0xC00000, 0x80000        # tools/port/build_snd.py: the slot's V area
# FORMAT -> its ABI signature (abi_signature); the ops / knob kinds of the format (later ones are features, appended)
FORMATS = {1: 'abb4122b46488a37'}
BASE_OPS = {1: ['anim', 'set', 'mul', 'move', 'fricmove', 'fall', 'nudge', 'dec', 'br', 'resume', 'resumeat', 'jmp',
                'spawn', 'fxoff', 'end', 'adv', 'check', 'part', 'evclr', 'onhit', 'put', 'hitclr', 'hold', 'unhold',
                'sigclr', 'hitoff', 'add', 'form', 'voice', 'vsig', 'turn', 'vphase', 'screen', 'home', 'catch', 'lanim',
                'warp']}
BASE_KNOBS = {1: ['set', 'pspeed', 'phits', 'dmg']}
WANT = ['lab', 'fighters', 'route_tab', 'rt_tab', 'bm_chars', 'mode', 'cam_x', 'projectiles', 'attract', 'phase', 'wave',
        'lock_x', 'camp', 'game_ticks', 'lab_fields', 'prac', 'q', 'qt']   # the layout's symbols the pages read (lab.js, tryit.js; q / qt: the sound queue, the proofs)


def bdir(build):
    return build if os.path.isabs(build) else os.path.join(GAME, build) if os.path.isdir(os.path.join(GAME, build)) else os.path.abspath(build)


def neo(path):
    d = open(path, 'rb').read()
    sizes = struct.unpack('<6I', d[4:28]); out, off = {}, 0x1000
    for n, sz in zip(ROMS, sizes): out[n] = (off, sz); off += sz
    return d, sizes, out


def syms(elf):
    """{name: (address, size, section)} of the ELF's data symbols (locals too: hud.h's portrait_pal is a static)"""
    out = {}
    for l in subprocess.run(['m68k-linux-gnu-objdump', '-t', elf], capture_output=True, text=True, check=True).stdout.split('\n'):
        m = re.match(r'([0-9a-f]{8}) .{7} (\S+)\s+([0-9a-f]{8}) (\S+)$', l)
        if m: out[m.group(4)] = (int(m.group(1), 16), int(m.group(3), 16), m.group(2))
    return out


def sections(elf):
    out = {}
    for l in subprocess.run(['m68k-linux-gnu-objdump', '-h', elf], capture_output=True, text=True, check=True).stdout.split('\n'):
        f = l.split()
        if len(f) >= 7 and re.match(r'\d+$', f[0]): out[f[1]] = (int(f[2], 16), int(f[3], 16), int(f[4], 16))   # size, VMA, LMA
    return out


class Elf:
    """the bytes of a 68000 ELF's loaded sections by address (big-endian ELF32: section headers only)"""
    def __init__(self, path):
        d = self.d = open(path, 'rb').read()
        shoff, = struct.unpack('>I', d[32:36]); shentsize, shnum = struct.unpack('>HH', d[46:50])
        self.secs = []
        for i in range(shnum):
            n, typ, fl, addr, off, size = struct.unpack('>IIIIII', d[shoff + i * shentsize:shoff + i * shentsize + 24])
            if typ == 1 and fl & 2 and size: self.secs.append((addr, size, off))   # PROGBITS, ALLOC
    def read(self, addr, n):
        for a, sz, off in self.secs:
            if a <= addr and addr + n <= a + sz: return self.d[off + addr - a:off + addr - a + n]
        raise KeyError(f'${addr:X} +{n}: no section holds it')


def nbc_of(B):
    return len(re.search(r'enum \{ (BC_\w+(?:, BC_\w+)*), BC_COUNT \}', open(os.path.join(B, 'bm_chars.h')).read()).group(1).split(','))


# ---- the slot's regions of a build --------------------------------------------------------------------------------------
def regions(build):
    """the slot's regions of a shell-type build dir: [{kind, rom, offset, size, used, what}] (P offsets = the .neo P
    region's); the build's facts"""
    B = bdir(build)
    elf = os.path.join(B, 'rom.elf'); S = syms(elf); sec = sections(elf)
    slot = json.load(open(os.path.join(B, 'slot.json'))); banks = json.load(open(os.path.join(B, 'banks.json')))
    snd = json.load(open(os.path.join(B, 'snd', 'snd_report.json')))['slot']
    hud = open(os.path.join(B, 'hud.h')).read()
    nbc = nbc_of(B); sid = slot['id']; assert sid == nbc - 1, (sid, nbc)
    for n, at in (('.labanchor', LABANCHOR_AT), ('.labhdr', LABHDR_AT), ('.labslot', LABSLOT_AT)):
        s = sec.get(n, (0, at, at))
        assert s[1] == at and s[2] == at, f'{n} at {s[1]:#x} (the pack format keeps it at {at:#x})'
    end1 = max(v[2] + v[0] for k, v in sec.items() if (v[1] < 0x100000 or k == '.data') and k not in ('.labanchor', '.labhdr', '.labslot'))
    assert end1 <= LABANCHOR_AT, f'the first MB runs to {end1:#x}, past the anchor at {LABANCHOR_AT:#x} (a new pack format)'
    ls = sec.get('.labslot', (0, 0, 0))
    out = [{'kind': 'slot', 'rom': 'P', 'offset': LABHDR_AT, 'size': SLOT_P_SIZE, 'used': LABHDR_SIZE + ls[0],
            'what': 'the slot header + .labslot (its first-MB tables)'}]
    k = banks['slot']['bank']; bs = sec.get(f'.p2bank{k}', (0, 0, 0))
    out.append({'kind': 'bank', 'rom': 'P', 'offset': (1 + k) * BANK, 'size': BANK, 'used': bs[0], 'what': f'P2 bank {k}: its banked tables'})
    pt = int(re.search(r'#define PORTRAIT_TILE (0x[0-9A-Fa-f]+)', hud).group(1), 16)
    out.append({'kind': 'face', 'rom': 'S', 'offset': (pt + sid * 16) * FIX_TILE, 'size': 16 * FIX_TILE, 'used': 16 * FIX_TILE, 'what': 'the HUD face'})
    out.append({'kind': 'tiles', 'rom': 'C', 'offset': slot['tile_first'] * 128, 'size': slot['tiles_kept'] * 128,
                'used': slot['tiles_used'] * 128, 'what': 'tiles'})
    out.append({'kind': 'voices', 'rom': 'V1', 'offset': snd['v'][0], 'size': snd['v'][1], 'used': snd['v_used'], 'what': 'voice samples'})
    assert len(snd['m']) == 4, snd['m']
    for i, (a, b) in enumerate(snd['m']):
        out.append({'kind': f'm{i}', 'rom': 'M', 'offset': a, 'size': b - a, 'used': b - a, 'what': 'voice records' if i < 2 else 'voice enable bits'})
    facts = {'slot_id': sid, 'bc_count': nbc, 'bank': k, 'labslot_used': ls[0], 'bank_used': bs[0], 'tile_first': slot['tile_first'],
             'tiles_kept': slot['tiles_kept'], 'tiles_used': slot['tiles_used'], 'voices': snd['voices'], 'voice_codes': snd['codes'],
             'v_used': snd['v_used'], 'v_kept': snd['v'][1], 'fighter': slot['fighter']}
    return out, facts, S


def check_fixed(regs):
    """the regions the format fixes are where it fixes them (else: a new pack format)"""
    want = {'slot': (LABHDR_AT, SLOT_P_SIZE), 'tiles': (SLOT_TILE_FIRST * 128, SLOT_TILES * 128), 'voices': (SLOT_V_AT, SLOT_V)}
    for r in regs:
        if r['kind'] in want: assert (r['offset'], r['size']) == want[r['kind']], f"{r['kind']} at {r['offset']:#x} +{r['size']:#x}: the format keeps {want[r['kind']]}"


# ---- the ABI the format stands for ------------------------------------------------------------------------------------
def _struct_bodies(text, names):
    t = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    out = {}
    for n in names:
        m = re.search(r'typedef struct\s*\w*\s*\{([^{}]*)\}\s*' + n + r'\s*;', t)
        assert m, n
        out[n] = ' '.join(m.group(1).split())
    return out


def _enum(text, first):
    t = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    m = re.search(r'enum\s*\{\s*(' + first + r'\b[^}]*)\}', t)
    return [x.split('=')[0].strip() for x in m.group(1).split(',') if x.strip()] if m else []


def abi(B):
    """what a pack's data and header are made of (the format stands for it): every bm_chars.h struct and enum but the
    roster's (BC_*), the victim postures' count (shared ids) and the ops / branch conditions (append-only: features),
    the route tree / knob / retime structs, the header tables' element sizes, the fixed regions"""
    h = open(os.path.join(B, 'bm_chars.h')).read(); t = re.sub(r'/\*.*?\*/', '', h, flags=re.S)
    keep = []
    for l in t.split('\n'):
        l = ' '.join(l.split())
        if not l or l.startswith('extern') or l.startswith('#') or 'BC_COUNT }' in l or 'VP_COUNT' in l or l.startswith('enum { P_ANIM') or l.startswith('enum { PC_END'):
            continue
        keep.append(l)
    fh = open(os.path.join(GAME, 'fighter.h')).read()
    S = syms(os.path.join(B, 'rom.elf')); nbc = nbc_of(B)
    return {'bm_chars.h': keep, 'fighter.h': _struct_bodies(fh, ['rnode_t', 'rt_head_t', 'gknob_t', 'gkcat_t', 'gretime_t']),
            'route_enums': [_enum(fh, 'RI_'), _enum(fh, 'RE_NONE')],
            'elements': {n: S[n][1] // nbc for n in HDR_ARRAYS} | {'bm_lab': S['bm_lab'][1]},
            'fixed': [LABANCHOR_AT, LABHDR_AT, LABHDR_SIZE, LABSLOT_AT, SLOT_TILE_FIRST, SLOT_TILES, SLOT_V_AT, SLOT_V, SLOT_RT_ROWS]}


def abi_signature(B): return hashlib.sha256(json.dumps(abi(B), sort_keys=True).encode()).hexdigest()[:16]


def check_abi(B):
    """the build's ABI is FORMAT's (else the build stops: a pack of this format would not load right in it); the ops and
    knob kinds only grow (appended: features)"""
    sig = abi_signature(B)
    ops, kn = ops_of(B), knobs_of()
    bad = []
    if FORMATS.get(FORMAT) != sig: bad.append(f'the slot ABI signature is {sig}, format {FORMAT} is {FORMATS.get(FORMAT)}')
    if ops[:len(BASE_OPS[FORMAT])] != BASE_OPS[FORMAT]: bad.append('the program ops were renumbered (P_* in export_bm.py: append new ones only)')
    if kn[:len(BASE_KNOBS[FORMAT])] != BASE_KNOBS[FORMAT]: bad.append('the knob kinds were renumbered (fighter.h KN_*: append new ones only)')
    if bad:
        sys.exit('lab_pack: the PACK FORMAT changed:\n  ' + '\n  '.join(bad) + f'\n  (lab_pack.py abi {B} shows it; a deliberate '
                 'change: FORMAT + 1 here and in labslot.h LAB_FORMAT, pack_swap.c, CharacterLab.kt, tryit.js, its FORMATS / '
                 'BASE_* entries, then every pack is rebuilt once: make lab-publish)')
    return sig


def ops_of(B):
    """the program ops, P_* in their order (bm_chars.h): op k + 1 = its name"""
    return [x[2:].lower() for x in _enum(open(os.path.join(B, 'bm_chars.h')).read(), 'P_ANIM')]


def knobs_of():
    return [x[3:].lower() for x in _enum(open(os.path.join(GAME, 'fighter.h')).read(), 'KN_END')][1:]


def h8(s): return hashlib.sha256(s.encode()).hexdigest()[:8]


def shared_tokens(B, uses=None):
    """the shared ids as feature tokens: the whole victim posture list (vp:), each source reaction (sr<i>:) and shared
    effect palette (sp<i>:); uses = the slot's own (a pack's needs), else all (a shell's features)"""
    sh = json.load(open(os.path.join(B, 'shared_ids.json')))
    u = sh['slot_uses'] if uses else None
    sr = u['sreact'] if u else range(len(sh['sreact']))
    sp = u['sfx_pal'] if u else range(len(sh['sfx_pal']))
    return ['vp:' + h8(json.dumps(sh['pose']))] + [f'sr{i}:' + h8(sh['sreact'][i]) for i in sr] + [f'sp{i}:' + sh['sfx_pal'][i] for i in sp]


def features(B):
    """what the shell plays: its ops, knob kinds, lab, try2, try3 (TRY blob v3: the chain), its shared ids"""
    fh = open(os.path.join(GAME, 'fighter.h')).read()
    return ops_of(B) + ['knob-' + k for k in knobs_of()] + ['lab'] + (['try2'] if 'gkcat_t' in fh else []) + \
        (['try3'] if 'LS_CHAIN' in fh else []) + shared_tokens(B)


def needs(B, E, S):
    """what the slot's data uses: the ops of its programs (bm_spec.c / bm_chars.c slot_*_prog), its knob catalogue's
    kinds (+ try2: its knob rows ride TRY blob v2), its LAB special, its shared ids"""
    ops = ops_of(B); used = set()
    for f in ('bm_spec.c', 'bm_chars.c'):
        for m in re.finditer(r'bprim_t slot_\w*prog\[\] = \{(.*?)\};', open(os.path.join(B, f)).read()):
            used |= {int(x) & 0x7F for x in re.findall(r'\{(\d+),', m.group(1))}
    out = [ops[o - 1] for o in sorted(used)]
    nbc = nbc_of(B); sid = nbc - 1
    a, size, _ = S['gkcat_rom']; p = struct.unpack('>I', E.read(a + sid * (size // nbc), 4))[0]
    kinds = set()
    while p:
        row = E.read(p, 16)
        if row[1] == 0: break
        kinds.add(row[1]); p += 16
    kn = knobs_of()
    out += ['knob-' + kn[k - 1] for k in sorted(kinds)] + (['try2'] if kinds else [])
    if E.read(S['bm_lab'][0], 1)[0] != 0xFF: out.append('lab')
    return out + shared_tokens(B, uses=True)


# ---- seal: the header + the anchor into a build's ELF -------------------------------------------------------------------
def header(B, E, S):
    """the slot header (labslot.h): 'NGSH', u16 format, u16 tables (+ bm_lab), u8 the build's slot id, u8 retime rows,
    u16 bytes, 4 zeros, then [u16 element size][the slot's element] per HDR_ARRAYS table, [u16][bm_lab], the 16 rows"""
    nbc = nbc_of(B); sid = nbc - 1
    body = b''
    for n in HDR_ARRAYS:
        a, size, _ = S[n]; assert size % nbc == 0, (n, size, nbc); e = size // nbc
        body += struct.pack('>H', e) + E.read(a + sid * e, e) + bytes(e & 1)
    a, size, _ = S['bm_lab']; body += struct.pack('>H', size) + E.read(a, size) + bytes(size & 1)
    a, size, _ = S['gretime_rom']; nrow = size // GRETIME_ROW
    rows = E.read(a + (nrow - 1 - SLOT_RT_ROWS) * GRETIME_ROW, SLOT_RT_ROWS * GRETIME_ROW)
    assert E.read(a + (nrow - 1) * GRETIME_ROW, 1) == b'\xFF', 'gretime_rom: its last row is not the end row'
    body += rows
    hdr = b'NGSH' + struct.pack('>HHBBH4x', FORMAT, len(HDR_ARRAYS) + 1, sid, SLOT_RT_ROWS, 16 + len(body)) + body
    assert len(hdr) <= LABHDR_SIZE, f'the slot header: {len(hdr)} bytes, the format keeps {LABHDR_SIZE}'
    return hdr + bytes(LABHDR_SIZE - len(hdr))


def ram_map(B):
    """the RAM the Player's Character lab reads / writes (the same bytes and addresses as chainlab/lab.js): the lab_t
    mailbox (lab.js LAB offsets + harness LAB_FIELDS from offsetof; tblob_size = sizeof lab_t.tblob, the longest live TRY
    blob the Player writes), the practice block, P1's state byte and the neutral states: the SHELL's (its anchor)"""
    sys.path.insert(0, HERE)
    import harness
    lay, _, states, y = harness._layout(GAME, B)
    return {'base': 0x100000, 'lab': y['lab'], 'lab_off': {'magic': 0, 'fighter': 5, 'load': 7, 'active': 8, 'buf': 400},
            'lab_fields': y['lab_fields'], 'tblob_size': y['tblob_size'], 'prac': y.get('prac'), 'p1_state': y['fighters'] + lay['state'][0],
            'state_size': lay['state'][1], 'neutral': [states.index('IDLE'), states.index('WALK')]}


def shell_doc(B, regs, facts, feats, sig):
    """the anchor's JSON: what the Player and the pages need of THIS shell (its RAM map, layout, roster, chain rules)"""
    sys.path.insert(0, HERE)
    import harness
    lay, fsize, states, y = harness._layout(GAME, B)
    cl = json.load(open(os.path.join(B, 'chainlab.json')))
    import ast
    le = ast.literal_eval(re.search(r'^LE_THROWS\s*=\s*(\[[^\]]*\])', open(os.path.join(HERE, 'export_bm.py')).read(), re.M).group(1))
    G = json.load(open(os.path.join(GAME, 'game.json')))
    rt = json.load(open(os.path.join(B, 'retime.json'))) if os.path.exists(os.path.join(B, 'retime.json')) else []
    return {'format': FORMAT, 'abi': sig, 'features': feats, 'game_version': open(os.path.join(GAME, 'VERSION')).read().strip(),
            'slot': {'id': facts['slot_id'], 'bc_count': facts['bc_count'], 'p2_bank': facts['bank']},
            'regions': [{k: r[k] for k in ('kind', 'rom', 'offset', 'size')} for r in regs],
            'ram': ram_map(B), 'fighters': [x['name'] for x in sorted(cl['fighters'], key=lambda x: x['id'])], 'throws': le,
            'layout': {'fields': lay, 'fsize': fsize, 'states': states, 'syms': {k: y[k] for k in WANT if k in y},
                       'sizeof_bchar': y.get('sizeof_bchar')},
            'chain_rules': {k: v for k, v in G['chain'].items() if k != 'about'}, 'ba': cl['ba'],
            'retime_rom': [r for r in rt if r['fighter'] != 'slot']}


def anchor(B, regs, facts, feats, sig):
    """'NGLA', u16 format, u16 regions, u8 slot id, u8 0, u16 features bytes, u32 JSON offset, u32 JSON bytes (from the
    anchor's start), then per region u8 kind, u8 rom, u16 0, u32 offset, u32 size; the features (NUL ended), the JSON"""
    doc = json.dumps(shell_doc(B, regs, facts, feats, sig), separators=(',', ':')).encode()
    fs = ' '.join(feats).encode() + b'\0'
    head = struct.pack('>4sHHBBHII', b'NGLA', FORMAT, len(regs), facts['slot_id'], 0, len(fs), 0, 0)
    rr = b''.join(struct.pack('>BBHII', KINDS[r['kind']], ROMS.index(r['rom']), 0, r['offset'], r['size']) for r in regs)
    jo = len(head) + len(rr) + len(fs); jo += -jo % 4
    head = struct.pack('>4sHHBBHII', b'NGLA', FORMAT, len(regs), facts['slot_id'], 0, len(fs), jo, len(doc))
    a = head + rr + fs; a += bytes(jo - len(a)) + doc
    assert len(a) <= LABANCHOR_SIZE, f'the anchor: {len(a)} bytes, {LABANCHOR_SIZE} kept'
    return a + bytes(LABANCHOR_SIZE - len(a))


def cmd_seal(a):
    B = bdir(a.build); elf = os.path.join(B, 'rom.elf')
    S = syms(elf); E = Elf(elf)
    regs, facts, _ = regions(B); check_fixed(regs)
    sig = check_abi(B)
    feats = features(B)
    hdr = header(B, E, S)
    anc = anchor(B, regs, facts, feats, sig)
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, 'h'), 'wb').write(hdr); open(os.path.join(t, 'a'), 'wb').write(anc)
        subprocess.run(['m68k-linux-gnu-objcopy', '--update-section', '.labhdr=' + os.path.join(t, 'h'),
                        '--update-section', '.labanchor=' + os.path.join(t, 'a'), elf], check=True)
    print(f'lab_pack seal: {os.path.basename(B)}: format {FORMAT} (abi {sig}), slot {facts["slot_id"]} = {facts["fighter"]}, '
          f'header {len(hdr.rstrip(bytes(1)))} B, {len(feats)} features')


def read_anchor(rom_p):
    """the anchor of a shell from its P ROM bytes as the .neo keeps them (each word low byte first) -> (format, slot id,
    features [], {kind: (rom, offset, size)}, the JSON)"""
    a = bytes(rom_p[LABANCHOR_AT + (i ^ 1)] for i in range(64))
    mg, fmt, nreg, sid, _, flen, jo, jl = struct.unpack('>4sHHBBHII', a[:20])
    if mg != b'NGLA': raise ValueError('not a Character Lab shell of the pack format (no anchor)')
    need = max(jo + jl, 20 + 12 * nreg + flen)
    a = bytes(rom_p[LABANCHOR_AT + (i ^ 1)] for i in range(need + (need & 1)))
    regs = {}
    for k in range(nreg):
        kind, rom, _, off, size = struct.unpack('>BBHII', a[20 + 12 * k:32 + 12 * k])
        regs[next(n for n, v in KINDS.items() if v == kind)] = (ROMS[rom], off, size)
    feats = a[20 + 12 * nreg:20 + 12 * nreg + flen - 1].decode().split()
    return fmt, sid, feats, regs, json.loads(a[jo:jo + jl])


# ---- packs --------------------------------------------------------------------------------------------------------------
def masked(data, layout, spans):
    m = bytearray(data)
    for rom, off, size in spans:
        o = layout[rom][0] + off; m[o:o + size] = bytes(size)
    return bytes(m)


def slot_spans(regs, S, nbc):
    """everything a build's slot owns or that seal writes: its regions, the anchor, its element of every header table
    (the ROM copies: the build's own), bm_lab, its retime rows (the DEBUG check masks them; P = .neo P offsets)"""
    sp = [(r['rom'], r['offset'], r['size']) for r in regs] + [('P', LABANCHOR_AT, LABANCHOR_SIZE)]
    sid = nbc - 1
    def P(at, size):
        a, b = at & ~1, (at + size + 1) & ~1; sp.append(('P', a, b - a))
    for n in HDR_ARRAYS:
        a, size, _ = S[n]; e = size // nbc; P(a + sid * e, e)
    P(*S['bm_lab'][:2])
    a, size, _ = S['gretime_rom']; P(a + size - GRETIME_ROW * (SLOT_RT_ROWS + 1), GRETIME_ROW * SLOT_RT_ROWS)
    return sp


def outside(a, b, layout, spans, S):
    """the DEBUG check (--strict): where the two .neo files differ outside the slot: [(rom, offset, length, what)]"""
    ma, mb = masked(a, layout, spans), masked(b, layout, spans)
    if ma[0x1000:] == mb[0x1000:]: return []
    out = []; i = 0x1000; n = len(ma); step = 1 << 16
    while i < n:
        if ma[i:i + step] == mb[i:i + step]: i += step; continue
        j = i
        while j < min(n, i + step):
            if ma[j] != mb[j]:
                k = j
                while k < n and ma[k] != mb[k]: k += 1
                rom = next((r for r, (o, sz) in layout.items() if o <= j < o + sz), 'header')
                off = j - layout[rom][0] if rom != 'header' else j
                what = ''
                if rom == 'P':
                    ad = off if off < BANK else 0x200000 + (off % BANK)
                    hit = [x for x, (sa, sz, sc) in S.items() if sa <= ad < sa + max(sz, 1) and (off < BANK) == (sa < 0x200000)]
                    what = ', '.join(hit[:3]) or f'${ad:06X}'
                out.append((rom, off, k - j, what)); j = k
                if len(out) > 40: return out
            else: j += 1
        i += step
    return out


def build_pack(regs, data, layout, sizes, manifest):
    body = b''
    for r in regs:
        o = layout[r['rom']][0] + r['offset']
        b = data[o:o + r['size']]; r['sha256'] = hashlib.sha256(b).hexdigest()
        k = len(b.rstrip(b'\0')); k += k & 1                 # (its blank end: written as zeros, not carried)
        body += struct.pack('<BBBxIII', ROMS.index(r['rom']), KINDS[r['kind']], 1 if r['kind'] in RELOC else 0,
                            r['offset'], k, r['size'] - k) + b[:k] + bytes(-k % 4)
    man = json.dumps(manifest, separators=(',', ':')).encode()
    head = MAGIC + struct.pack('<HHI6I', VERSION, len(regs), len(man), *sizes)
    pre = head + man; pre += bytes(-len(pre) % 4)
    return pre + body


def read_pack(path):
    d = open(path, 'rb').read() if isinstance(path, str) else path
    assert d[:4] == MAGIC, 'not a character pack'
    ver, nreg, mlen, *sizes = struct.unpack('<HHI6I', d[4:36])
    man = json.loads(d[36:36 + mlen]); o = 36 + mlen; o += -o % 4
    regs = []
    for _ in range(nreg):
        rom, kind, fl, off, n, z = struct.unpack('<BBBxIII', d[o:o + 16]); o += 16
        regs.append({'rom': ROMS[rom], 'kind': next((k for k, v in KINDS.items() if v == kind), None), 'reloc': bool(fl & 1),
                     'offset': off, 'bytes': d[o:o + n] + bytes(z)}); o += n + (-n % 4)
    return ver, sizes, man, regs


def compat(fmt, need, sfmt, feats):
    """None = the pack loads into that shell; else why not, in plain words"""
    if fmt is None: return 'a pack from before the pack format (it holds the old shell\'s addresses): rebuild it'
    if fmt != sfmt: return f'pack format {fmt}, this shell reads format {sfmt}'
    miss = [n for n in need if n not in set(feats)]
    if not miss: return None
    shared = [m for m in miss if re.match(r'(vp|sr\d+|sp\d+):', m)]
    plain = [m for m in miss if m not in shared]
    why = []
    if plain: why.append('it needs ' + ', '.join(plain) + ', which this shell does not have')
    if shared: why.append('its shared tables (' + ', '.join(sorted({re.sub(r'\d*:.*', '', m) for m in shared})) + ') are not this shell\'s')
    return '; '.join(why)


def legacy_engine(shell_d, shell_l, regs):
    """the engine string the Players before 0.0.33 compare (<VERSION>-<the shell, its slot regions and anchor zeroed>)"""
    fp = hashlib.sha256(masked(shell_d, shell_l, [(r['rom'], r['offset'], r['size']) for r in regs] + [('P', LABANCHOR_AT, LABANCHOR_SIZE)])).hexdigest()
    return open(os.path.join(GAME, 'VERSION')).read().strip() + '-' + fp[:12]


def cmd_make(a):
    shell_d, shell_sizes, shell_l = neo(os.path.join(GAME, a.shell[1]))
    pack_d, pack_sizes, pack_l = neo(os.path.join(GAME, a.build[1]))
    sfmt, ssid, sfeats, sregs, sdoc = read_anchor(shell_d[shell_l['P'][0]:shell_l['P'][0] + shell_l['P'][1]])
    B = bdir(a.build[0])
    regs, facts, S = regions(B); check_fixed(regs)
    sig = check_abi(B)
    assert facts['fighter'] == a.fighter, (facts['fighter'], a.fighter)
    assert sig == sdoc['abi'], f'the pack build\'s ABI {sig}, the shell\'s {sdoc["abi"]}'
    bad = [f"{r['rom']} {r['what']}: {r['used']:,} bytes, the slot keeps {r['size']:,}" for r in regs if r['used'] > r['size']]
    if facts['bank_used'] > BANK_CAP: bad.append(f"the slot's bank: {facts['bank_used']:,} bytes, a bank holds {BANK_CAP:,}")
    for r in regs:                                       # the shell's anchor: every kind there, the fixed ones in place
        s = sregs.get(r['kind'])
        if not s: bad.append(f"the shell has no {r['kind']} region")
        elif r['kind'] not in RELOC and (s[1] != r['offset'] or s[0] != r['rom']): bad.append(f"{r['kind']} at {r['offset']:#x}, the shell's at {s[1]:#x}")
        elif r['used'] > s[2]: bad.append(f"{r['kind']}: {r['used']:,} bytes, the shell keeps {s[2]:,}")
    if bad: sys.exit('lab_pack: REFUSED:\n  ' + '\n  '.join(bad))
    E = Elf(os.path.join(B, 'rom.elf'))
    need = needs(B, E, S)
    why = compat(FORMAT, need, sfmt, sfeats)
    if why: sys.exit(f'lab_pack: REFUSED, the shell cannot play {a.fighter}\'s pack: {why}')
    if a.strict:                                         # DEBUG: the same code as the shell, so equal outside the slot
        nbc = nbc_of(B); Ssh = syms(os.path.join(bdir(a.shell[0]), 'rom.elf'))
        spans = slot_spans(regs, S, nbc) + slot_spans(regions(a.shell[0])[0], Ssh, nbc)
        diff = outside(shell_d, pack_d, shell_l, spans, S)
        if diff:
            sys.exit('lab_pack: STRICT: the build differs from the shell outside the slot (a per-fighter table labslot.h '
                     'does not carry, or a pointer out of the slot):\n  ' + '\n  '.join(f'{r} +${o:X} {n} bytes {w}' for r, o, n, w in diff))
    lab = json.load(open(os.path.join(B, 'lab.json'))) if os.path.exists(os.path.join(B, 'lab.json')) else None
    lab = lab if lab and lab.get('fighter') == 'slot' else None
    cl = json.load(open(os.path.join(B, 'chainlab.json')))
    fe = next(x for x in cl['fighters'] if x['name'] == 'slot')
    rt = json.load(open(os.path.join(B, 'retime.json'))) if os.path.exists(os.path.join(B, 'retime.json')) else []
    G = json.load(open(os.path.join(GAME, 'game.json')))
    r = next(x for x in G['roster'] if x['name'] == a.fighter)
    pieces = os.path.join(HERE, 'arb_pieces', a.fighter + '.json')
    ids = os.path.join(HERE, 'arb_pieces', a.fighter + '_ids.json')
    page = {'anims': lab['anims'] if lab else [], 'lab_spec': lab['spec'] if lab else None, 'moves': lab['moves'] if lab else {},
            'chain': {'fighter': fe, 'retime': [x for x in rt if x['fighter'] == 'slot']}}
    data = {'format': FORMAT, 'needs': need, 'regions': [], 'page': page,
            'constants': {'nspec': len(fe['pool']), 'pool': [p['input'] for p in fe['pool']], 'specials': fe['specials'],
                          'nvoice': fe['voices']['nvoice'], 'voices_used': facts['voices'],
                          'lab': {'spec': lab['spec'], 'anims': len(lab['anims'])} if lab else None}}
    manifest = {'ngpk': {'format': FORMAT, 'needs': ' '.join(need)},   # (first: pack_swap.c reads it there)
                'format': 'brawler character pack', 'version': VERSION, 'fighter': a.fighter,
                'display': (r.get('display') or a.fighter).upper(), 'bank': r['bank'], 'abi': sig,
                'built_with': {'game_version': open(os.path.join(GAME, 'VERSION')).read().strip(), 'shell_sha256': hashlib.sha256(shell_d).hexdigest()},
                # the Players before 0.0.33 read these (the shell it was built against): engine, slot, ram
                'engine': legacy_engine(shell_d, shell_l, regions(a.shell[0])[0]), 'slot': {'id': facts['slot_id'], 'bc_count': facts['bc_count'], 'p2_bank': facts['bank']},
                'ram': sdoc['ram'],
                'constants': data['constants'], 'page': page,
                'usage': {'labslot': [facts['labslot_used'], SLOT_P_SIZE - LABHDR_SIZE], 'bank': [facts['bank_used'], BANK_CAP],
                          'tiles': [facts['tiles_used'], facts['tiles_kept']], 'voice_bytes': [facts['v_used'], facts['v_kept']],
                          'voices': [facts['voices'], facts['voice_codes'][1]]},
                'pieces': os.path.relpath(pieces, REPO) if os.path.exists(pieces) else None,
                'piece_ids': json.load(open(ids)) if os.path.exists(ids) else None,
                'face': f"/data/neogeo_dict/portraits/{r['bank'].replace(':', '_')}.png"}
    blob = build_pack(regs, pack_d, pack_l, pack_sizes, manifest)   # (fills each region's sha256)
    data['regions'] = [[x['kind'], x['sha256']] for x in regs]
    data_sha = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.o)), exist_ok=True)
    open(a.o, 'wb').write(blob)
    side = dict(manifest, regions=regs, file=os.path.basename(a.o), size=len(blob), sha256=hashlib.sha256(blob).hexdigest(), data_sha=data_sha)
    json.dump(side, open(os.path.splitext(a.o)[0] + '.json', 'w'), indent=1)
    u = manifest['usage']
    print(f"pack {a.fighter}: {len(blob):,} bytes, {len(regs)} regions, format {FORMAT}, needs {len(need)} "
          f"({' '.join(n for n in need if ':' not in n)} + {sum(':' in n for n in need)} shared ids), data {data_sha[:12]}"
          + (', STRICT: identical to the shell outside the slot' if a.strict else ''))
    print(f"  .labslot {u['labslot'][0]:,} / {u['labslot'][1]:,}   bank {u['bank'][0]:,} / {u['bank'][1]:,}   tiles "
          f"{u['tiles'][0]:,} / {u['tiles'][1]:,}   voices {u['voices'][0]} / {u['voices'][1]} ({u['voice_bytes'][0]:,} / "
          f"{u['voice_bytes'][1]:,} bytes)")


def pack_facts(path):
    """(format, needs) of a pack file (None, [] for a pack from before the format)"""
    ver, sizes, man, regs = read_pack(path)
    g = man.get('ngpk')
    return (g['format'], g['needs'].split()) if g else (None, [])


def cmd_info(a):
    ver, sizes, man, regs = read_pack(a.pack)
    print(json.dumps({k: v for k, v in man.items() if k not in ('piece_ids', 'page', 'ram')}, indent=1))
    for r in regs: print(f"{r['kind'] or '?':7} {r['rom']:2} +${r['offset']:08X} {len(r['bytes']):9,} bytes{' (relocated)' if r['reloc'] else ''}")


def shell_anchor(path):
    d, sizes, layout = neo(path)
    return read_anchor(d[layout['P'][0]:layout['P'][0] + layout['P'][1]])


def cmd_anchor(a):
    fmt, sid, feats, regs, doc = shell_anchor(a.shell)
    print(f'format {fmt}, slot {sid}, {len(feats)} features: ' + ' '.join(f for f in feats if ':' not in f) +
          f' + {sum(":" in f for f in feats)} shared ids')
    for k, (rom, off, size) in regs.items(): print(f'  {k:7} {rom:2} +${off:08X} {size:9,}')
    print('  json:', ', '.join(f'{k} ({len(json.dumps(v))} B)' for k, v in doc.items()))


def cmd_check(a):
    fmt, need = pack_facts(a.pack)
    sfmt, sid, feats, regs, doc = shell_anchor(a.shell)
    why = compat(fmt, need, sfmt, feats)
    print('loads' if not why else 'REFUSED: ' + why); sys.exit(1 if why else 0)


def apply(shell_d, pk):
    """the .neo a swap gives (pack_swap.c does the same in memory): None + why if refused"""
    d, sizes, layout = shell_d
    sfmt, sid, feats, sregs, doc = read_anchor(d[layout['P'][0]:layout['P'][0] + layout['P'][1]])
    ver, psizes, man, regs = read_pack(pk)
    g = man.get('ngpk')
    why = compat(g['format'] if g else None, g['needs'].split() if g else [], sfmt, feats)
    if why: return None, why
    m = bytearray(d)
    for r in regs:
        rom, off, size = sregs[r['kind']]
        assert r['reloc'] or off == r['offset'], r['kind']
        assert len(r['bytes']) <= size, r['kind']
        o = layout[rom][0] + off; m[o:o + len(r['bytes'])] = r['bytes']
    return bytes(m), None


def cmd_apply(a):
    out, why = apply(neo(a.shell), open(a.pack, 'rb').read())
    if why: sys.exit('REFUSED: ' + why)
    open(a.out, 'wb').write(out); print(a.out, len(out))


def cmd_abi(a):
    B = bdir(a.build)
    print(json.dumps(abi(B), indent=1)); print('signature', abi_signature(B), '(format', FORMAT, 'is', FORMATS.get(FORMAT), ')')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('seal'); p.add_argument('build')
    p = sp.add_parser('make'); p.add_argument('fighter'); p.add_argument('--shell', nargs=2, required=True, metavar=('BUILD', 'NEO'))
    p.add_argument('--build', nargs=2, required=True, metavar=('BUILD', 'NEO')); p.add_argument('-o', required=True)
    p.add_argument('--strict', action='store_true', help='DEBUG: also refuse a build that differs from the shell outside the slot')
    p = sp.add_parser('info'); p.add_argument('pack')
    p = sp.add_parser('anchor'); p.add_argument('shell')
    p = sp.add_parser('check'); p.add_argument('pack'); p.add_argument('shell')
    p = sp.add_parser('apply'); p.add_argument('shell'); p.add_argument('pack'); p.add_argument('out')
    p = sp.add_parser('abi'); p.add_argument('build')
    a = ap.parse_args()
    {'seal': cmd_seal, 'make': cmd_make, 'info': cmd_info, 'anchor': cmd_anchor, 'check': cmd_check, 'apply': cmd_apply,
     'abi': cmd_abi}[a.cmd](a)


if __name__ == '__main__':
    main()
