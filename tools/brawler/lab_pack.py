#!/usr/bin/env python3
"""The Character Lab's character packs (docs/feedback.md "Character Lab: shell and packs"; Bruno 2026-10-10: "one lab
build and two exported data sets, two characters we could dynamically swap").

    lab_pack.py make F --shell SHELL_BUILD SHELL.neo --build BUILD PACK.neo -o OUT.pack   (examples/brawler: make LAB_PACK=F)
    lab_pack.py info PACK                                                                 (its manifest and regions)
    lab_pack.py apply SHELL.neo PACK OUT.neo                                              (the .neo a swap gives: the proofs)

The shell (make LAB_SHELL=1 -> lab-shell.neo) is the game with one more roster fighter, the SLOT (the last index), whose
data sits in fixed places (examples/brawler/Makefile "the Character Lab's shell"). A pack = the bytes of those places for
fighter F, taken from a build of the same game with F in the slot (make LAB_PACK=F):
  P  .labslot (LABSLOT_AT .. 1 MB: the slot's first-MB tables), the slot's P2 bank (its banked tables), and the slot's
     element of every table indexed by fighter (bm_chars[], the retime rows kept for it, the HUD face's colours...);
  S  its HUD face (16 fix tiles at PORTRAIT_TILE + slot * 16);
  M  its voices' records in the KOF98 driver's two overflow voice slots + their enable bits (build_snd.py SLOT_*);
  V  its voices' samples (build_snd.py SLOT_V from the first 1 MB boundary past every other sample);
  C  its tiles (export_bm.py SLOT_TILES from slot.json's tile_first).
Our fighters are data + interpreted programs: every pointer in the slot's tables points into the slot's regions or at
the shell's own tables, which no pack changes. That is checked, not assumed: the pack's .neo and the shell's must be
byte-identical outside these regions (else the pack is refused, naming the symbols that differ), and every region must
hold what the fighter needs (a pack larger than the slot is refused).

The file (little-endian): 'NGPK', u16 version 1, u16 regions, u32 manifest bytes, u32 x 6 the ROM sizes it fits (the
.neo header's P S M V1 V2 C), the manifest (JSON), then per region (4-byte aligned): u8 rom (0 P, 1 S, 2 M, 3 V1, 4 V2,
5 C), 3 zero bytes, u32 offset, u32 length, u32 zeros (offsets and bytes as in the .neo's regions: P word-swapped as the
.neo keeps it), the length bytes, then zeros bytes of 0 to write after them (a region's blank end is not carried). tools/brawler/chainlab/pack_swap.c applies one to a loaded ROM (the wasm core, the Player)."""
import argparse, hashlib, json, os, re, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
GAME = os.path.join(REPO, 'examples', 'brawler')
MAGIC, VERSION = b'NGPK', 1
ROMS = ['P', 'S', 'M', 'V1', 'V2', 'C']
LABSLOT_AT = 0xE0000                     # examples/brawler/Makefile LABSLOT_AT: .labslot runs to the end of the first MB
LABSLOT_SIZE = 0x100000 - LABSLOT_AT
BANK = 0x100000; BANK_CAP = BANK - 16    # a P2 bank (its last 16 bytes: the bank register)
# the tables indexed by fighter (bm_chars order): the slot's element of each (export_bm.py, build_tables.py, make_hud.py)
SLOT_ARRAYS = ['bm_chars', 'bm_seg', 'bm_air', 'bm_hsnd', 'bm_xthr', 'bm_hspark', 'bm_head', 'bm_bank', 'ai_ready',
               'gblitz_rom', 'gblitz_can', 'grun_bob', 'grun_dash', 'gfury_area', 'gwalk_rom', 'pb_of_fighter',
               'roster_unlock', 'dtier_rom', 'portrait_pal']
WHOLE = ['bm_lab']                       # the Lab build's LAB special (its fighter: the slot's, or none)
GRETIME_ROW, SLOT_RT_ROWS = 8, 16        # gretime_t; build_tables.py SLOT_RT_ROWS (before the 0xFF row)
FIX_TILE = 32                            # S ROM bytes a fix tile


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


def regions(build):
    """the slot's regions of a shell-type build dir: [{rom, offset, size, used, what}] (P offsets = the .neo P region's,
    widened to whole words); the build's facts for the manifest"""
    B = os.path.join(GAME, build) if not os.path.isabs(build) else build
    elf = os.path.join(B, 'rom.elf'); S = syms(elf); sec = sections(elf)
    slot = json.load(open(os.path.join(B, 'slot.json'))); banks = json.load(open(os.path.join(B, 'banks.json')))
    snd = json.load(open(os.path.join(B, 'snd', 'snd_report.json')))['slot']
    hud = open(os.path.join(B, 'hud.h')).read()
    nbc = len(re.search(r'enum \{ (BC_\w+(?:, BC_\w+)*), BC_COUNT \}', open(os.path.join(B, 'bm_chars.h')).read()).group(1).split(','))
    sid = slot['id']; assert sid == nbc - 1, (sid, nbc)
    out = []
    def P(at, size, what, used=None):                    # an ELF address range -> the .neo P region (words)
        if at >= 0x200000: raise ValueError(what)
        a, b = at & ~1, (at + size + 1) & ~1
        out.append({'rom': 'P', 'offset': a, 'size': b - a, 'used': size if used is None else used, 'what': what})
    ls = sec.get('.labslot', (0, LABSLOT_AT, LABSLOT_AT))
    assert ls[1] == LABSLOT_AT and ls[2] == LABSLOT_AT, f'.labslot at {ls[1]:#x} (LABSLOT_AT {LABSLOT_AT:#x})'
    end1 = sec['.data'][2] + sec['.data'][0]
    assert end1 <= LABSLOT_AT, f'the first MB runs to {end1:#x}, past LABSLOT_AT {LABSLOT_AT:#x}'
    P(LABSLOT_AT, LABSLOT_SIZE, '.labslot: the slot\'s first-MB tables', ls[0])
    k = banks['slot']['bank']; bs = sec.get(f'.p2bank{k}', (0, 0, 0))
    out.append({'rom': 'P', 'offset': (1 + k) * BANK, 'size': BANK, 'used': bs[0], 'what': f'P2 bank {k}: the slot\'s banked tables'})
    for n in SLOT_ARRAYS:
        a, size, _ = S[n]; assert size % nbc == 0, (n, size, nbc); e = size // nbc
        P(a + sid * e, e, f'{n}[{sid}]')
    for n in WHOLE:
        a, size, _ = S[n]; P(a, size, n)
    a, size, _ = S['gretime_rom']
    P(a + size - GRETIME_ROW * (SLOT_RT_ROWS + 1), GRETIME_ROW * SLOT_RT_ROWS, f'gretime_rom: the slot\'s {SLOT_RT_ROWS} rows')
    pt = int(re.search(r'#define PORTRAIT_TILE (0x[0-9A-Fa-f]+)', hud).group(1), 16)
    out.append({'rom': 'S', 'offset': (pt + sid * 16) * FIX_TILE, 'size': 16 * FIX_TILE, 'used': 16 * FIX_TILE, 'what': 'the HUD face'})
    for a, b in snd['m']:
        out.append({'rom': 'M', 'offset': a, 'size': b - a, 'used': b - a, 'what': 'voice records / enable bits'})
    out.append({'rom': 'V1', 'offset': snd['v'][0], 'size': snd['v'][1], 'used': snd['v_used'], 'what': 'voice samples'})
    out.append({'rom': 'C', 'offset': slot['tile_first'] * 128, 'size': slot['tiles_kept'] * 128,
                'used': slot['tiles_used'] * 128, 'what': 'tiles'})
    facts = {'slot_id': sid, 'bc_count': nbc, 'bank': k, 'labslot_used': ls[0], 'bank_used': bs[0], 'tile_first': slot['tile_first'],
             'tiles_kept': slot['tiles_kept'], 'tiles_used': slot['tiles_used'], 'voices': snd['voices'], 'voice_codes': snd['codes'],
             'v_used': snd['v_used'], 'v_kept': snd['v'][1], 'fighter': slot['fighter']}
    return out, facts, S


def ram_map(build):
    """the RAM the Player's Character lab reads / writes (the same bytes and addresses as chainlab/lab.js): the lab_t
    mailbox (lab.js LAB offsets + harness LAB_FIELDS from offsetof), the practice block, P1's state byte and the neutral
    states. The shell's code and RAM are every pack's (the engine fingerprint), so any of its packs carries the same."""
    sys.path.insert(0, HERE)
    import harness
    B = os.path.join(GAME, build) if not os.path.isabs(build) else build
    lay, _, states, y = harness._layout(GAME, B)
    return {'base': 0x100000, 'lab': y['lab'], 'lab_off': {'magic': 0, 'fighter': 5, 'load': 7, 'active': 8, 'buf': 400},
            'lab_fields': y['lab_fields'], 'prac': y.get('prac'), 'p1_state': y['fighters'] + lay['state'][0],
            'state_size': lay['state'][1], 'neutral': [states.index('IDLE'), states.index('WALK')]}


def check_fits(regs, facts):
    """a pack larger than the slot is refused (the exporters stop earlier on most: tiles, voices, retime rows)"""
    bad = [f"{r['rom']} {r['what']}: {r['used']:,} bytes, the slot keeps {r['size']:,}" for r in regs if r['used'] > r['size']]
    if facts['bank_used'] > BANK_CAP: bad.append(f"the slot's bank: {facts['bank_used']:,} bytes, a bank holds {BANK_CAP:,}")
    return bad


def masked(data, layout, regs):
    """the .neo with every slot region zeroed (what a pack never changes)"""
    m = bytearray(data)
    for r in regs:
        o = layout[r['rom']][0] + r['offset']; m[o:o + r['size']] = bytes(r['size'])
    return bytes(m)


def outside(a, b, layout, regs, S):
    """the byte ranges where the two .neo files differ outside the slot's regions: [(rom, offset, length, what)]"""
    ma, mb = masked(a, layout, regs), masked(b, layout, regs)   # (the .neo headers: their names differ; sizes checked)
    if ma[0x1000:] == mb[0x1000:]: return []
    out = []; i = 0x1000; n = len(ma)
    step = 1 << 16
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


def build_pack(f, regs, data, layout, sizes, manifest):
    body = b''
    for r in regs:
        o = layout[r['rom']][0] + r['offset']
        b = data[o:o + r['size']]; r['sha256'] = hashlib.sha256(b).hexdigest()
        k = len(b.rstrip(b'\0')); k += k & 1                 # (its blank end: written as zeros, not carried)
        body += struct.pack('<B3xIII', ROMS.index(r['rom']), r['offset'], k, r['size'] - k) + b[:k] + bytes(-k % 4)
    man = json.dumps(manifest, separators=(',', ':')).encode()
    head = MAGIC + struct.pack('<HHI6I', VERSION, len(regs), len(man), *sizes)
    pre = head + man; pre += bytes(-len(pre) % 4)
    return pre + body


def read_pack(path):
    d = open(path, 'rb').read()
    assert d[:4] == MAGIC, 'not a character pack'
    ver, nreg, mlen, *sizes = struct.unpack('<HHI6I', d[4:36])
    man = json.loads(d[36:36 + mlen]); o = 36 + mlen; o += -o % 4
    regs = []
    for _ in range(nreg):
        rom, off, n, z = struct.unpack('<B3xIII', d[o:o + 16]); o += 16
        regs.append((ROMS[rom], off, d[o:o + n] + bytes(z))); o += n + (-n % 4)
    return ver, sizes, man, regs


def cmd_make(a):
    shell_d, shell_sizes, shell_l = neo(os.path.join(GAME, a.shell[1]))
    pack_d, pack_sizes, pack_l = neo(os.path.join(GAME, a.build[1]))
    regs_s, facts_s, _ = regions(a.shell[0])
    regs, facts, S = regions(a.build[0])
    key = lambda rs: [(r['rom'], r['offset'], r['size']) for r in rs]
    if key(regs) != key(regs_s): sys.exit('lab_pack: the slot\'s regions are not the shell\'s: ' + json.dumps([x for x in zip(key(regs), key(regs_s)) if x[0] != x[1]][:5]))
    if pack_sizes != shell_sizes: sys.exit(f'lab_pack: ROM sizes {pack_sizes} differ from the shell\'s {shell_sizes}')
    assert facts['fighter'] == a.fighter, (facts['fighter'], a.fighter)
    bad = check_fits(regs, facts)
    if bad: sys.exit('lab_pack: REFUSED, larger than the slot:\n  ' + '\n  '.join(bad))
    diff = outside(shell_d, pack_d, shell_l, regs, S)
    if diff:
        sys.exit('lab_pack: REFUSED, the build differs from the shell outside the slot (a pointer or a table the slot does '
                 'not own):\n  ' + '\n  '.join(f'{r} +${o:X} {n} bytes {w}' for r, o, n, w in diff))
    fp = hashlib.sha256(masked(shell_d, shell_l, regs)).hexdigest()
    ver = open(os.path.join(GAME, 'VERSION')).read().strip()
    B = os.path.join(GAME, a.build[0])
    lab = json.load(open(os.path.join(B, 'lab.json'))) if os.path.exists(os.path.join(B, 'lab.json')) else None
    cl = next(x for x in json.load(open(os.path.join(B, 'chainlab.json')))['fighters'] if x['name'] == 'slot')
    G = json.load(open(os.path.join(GAME, 'game.json')))
    r = next(x for x in G['roster'] if x['name'] == a.fighter)
    pieces = os.path.join(HERE, 'arb_pieces', a.fighter + '.json')
    ids = os.path.join(HERE, 'arb_pieces', a.fighter + '_ids.json')
    manifest = {'format': 'brawler character pack', 'version': VERSION, 'fighter': a.fighter,
                'display': (r.get('display') or a.fighter).upper(), 'bank': r['bank'],
                'engine': f'{ver}-{fp[:12]}', 'game_version': ver, 'shell_fingerprint': fp,
                'shell_sha256': hashlib.sha256(shell_d).hexdigest(),
                'slot': {'id': facts['slot_id'], 'bc_count': facts['bc_count'], 'p2_bank': facts['bank']},
                'constants': {'nspec': len(cl['pool']), 'pool': [p['input'] for p in cl['pool']], 'specials': cl['specials'],
                              'nvoice': cl['voices']['nvoice'], 'voices_used': facts['voices'],
                              'lab': {'spec': lab['spec'], 'anims': len(lab['anims'])} if lab and lab.get('fighter') == 'slot' else None},
                'usage': {'labslot': [facts['labslot_used'], LABSLOT_SIZE], 'bank': [facts['bank_used'], BANK_CAP],
                          'tiles': [facts['tiles_used'], facts['tiles_kept']], 'voice_bytes': [facts['v_used'], facts['v_kept']],
                          'voices': [facts['voices'], facts['voice_codes'][1]]},
                'pieces': os.path.relpath(pieces, REPO) if os.path.exists(pieces) else None,
                'piece_ids': json.load(open(ids)) if os.path.exists(ids) else None,
                'face': f"/data/neogeo_dict/portraits/{r['bank'].replace(':', '_')}.png",
                'ram': ram_map(a.shell[0]),
                'regions': [{k: v for k, v in x.items()} for x in regs]}
    blob = build_pack(a.fighter, regs, pack_d, pack_l, pack_sizes, manifest)
    os.makedirs(os.path.dirname(os.path.abspath(a.o)), exist_ok=True)
    open(a.o, 'wb').write(blob)
    side = dict(manifest, file=os.path.basename(a.o), size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    json.dump(side, open(os.path.splitext(a.o)[0] + '.json', 'w'), indent=1)
    u = manifest['usage']
    print(f"pack {a.fighter}: {len(blob):,} bytes, {len(regs)} regions, engine {manifest['engine']}; outside the slot: "
          f"identical to the shell")
    print(f"  .labslot {u['labslot'][0]:,} / {u['labslot'][1]:,}   bank {u['bank'][0]:,} / {u['bank'][1]:,}   tiles "
          f"{u['tiles'][0]:,} / {u['tiles'][1]:,}   voices {u['voices'][0]} / {u['voices'][1]} ({u['voice_bytes'][0]:,} / "
          f"{u['voice_bytes'][1]:,} bytes)")


def cmd_info(a):
    ver, sizes, man, regs = read_pack(a.pack)
    print(json.dumps({k: v for k, v in man.items() if k not in ('regions', 'piece_ids')}, indent=1))
    for rom, off, b in regs: print(f'{rom:2} +${off:08X} {len(b):9,} bytes')


def cmd_apply(a):
    """the .neo a swap gives (pack_swap.c does the same in memory): the proofs compare it with the pack's own build"""
    d, sizes, layout = neo(a.shell)
    ver, psizes, man, regs = read_pack(a.pack)
    assert tuple(psizes) == sizes, (psizes, sizes)
    m = bytearray(d)
    for rom, off, b in regs:
        o = layout[rom][0] + off; m[o:o + len(b)] = b
    open(a.out, 'wb').write(bytes(m)); print(a.out, len(m))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('make'); p.add_argument('fighter'); p.add_argument('--shell', nargs=2, required=True, metavar=('BUILD', 'NEO'))
    p.add_argument('--build', nargs=2, required=True, metavar=('BUILD', 'NEO')); p.add_argument('-o', required=True)
    p = sp.add_parser('info'); p.add_argument('pack')
    p = sp.add_parser('apply'); p.add_argument('shell'); p.add_argument('pack'); p.add_argument('out')
    a = ap.parse_args()
    {'make': cmd_make, 'info': cmd_info, 'apply': cmd_apply}[a.cmd](a)


if __name__ == '__main__':
    main()
