#!/usr/bin/env python3
"""TODO #174: the fighters' bulk into P2 banks (docs/rom_packer_rules.md "P ROM"; sdk/include/neo_bank.h).

    python3 bank_pack.py BUILD_DIR      (after bm_chars.o / bm_spec.o are compiled with -fdata-sections)

Every table of the export (export_bm.py: build/bm_chars.c, build/bm_spec.c) is its own section (.rodata.<symbol>). The
tables the engine reads only while the fighter's own bank is mapped (fighter.c "banks": its frames and their tiles, its
specials' script rows, programs, parts, links, variant columns, its projectiles' rows) go to that fighter's bank; the
rest (bchar_t, animation steps with their boxes, throws, postures, palettes, routes, voices, bspec_t / bproj_t
headers: the tables other fighters, combat, the AI and the HUD read every frame) stays in the first MB. A table goes
to the first MB too when a fighter other than its owner refers to it (KOF's shared projectile end rows), and with it
everything it leads to. A fighter and its form link's target share a bank (fighter.c form_set swaps them in place).
Banks (TODO #190): the fewest banks (up to 7) in which every bank keeps MARGIN bytes free (BANK_MARGIN, default 128 KB),
filled balanced: fighters (a form group whole) by decreasing size, each into the emptiest bank; each bank 1 MB - 16.

The Character Lab's shell (make LAB_SHELL=1 / LAB_PACK=<f>; the export's fighter 'slot'): the slot's banked tables get
a bank of their own after the others' (bm_bank: the last), its first-MB tables the section .labslot (linked at a fixed
address, the Makefile's LABSLOT_AT): neither moves whoever fills the slot (lab_pack.py).

Writes BUILD_DIR/bank_rename.txt (objcopy options: .rodata.<symbol> -> .p2bankN), BUILD_DIR/bm_bank.c (bm_bank[]:
each fighter's bank) and BUILD_DIR/banks.json / banks.txt (per bank: used, free, fighters; the first MB's share).
Refuses a reference from one bank into another or from a first-MB table that is not a holder (bchar_t, bspec_t,
bproj_t) into a bank: the engine maps a bank only through a fighter (bm_bank[ch->id]), so such a pointer would be
read with the wrong bank."""
import sys, os, re, json, subprocess

build = sys.argv[1]
SRC = ['bm_chars.c', 'bm_spec.c']
OBJ = ['bm_chars.o', 'bm_spec.o']
CAP = 0x100000 - 16                     # $2FFFF0-$2FFFFF: the bank register (neoscan.ld ASSERT)
MAX_BANKS = 7                           # NeoCart PROG v3: banks 0-6 (tools/neobuild.py)
MARGIN = int(os.environ.get('BANK_MARGIN', '0x20000'), 0)   # TODO #190: free bytes every bank keeps (> the largest
                                                           # fighter's bulk, Rugal 125 KB: room for one more anywhere)
BANKED = {'bframe_t', 'bpart_t', 'bspec_row_t', 'bprow_t', 'bpend_t', 'bprim_t', 'bspart_t', 'bslink_t', 'int32_t'}
TILES = re.compile(r'_f\d+_p\d+$')      # uint16_t: a frame part's tile numbers (palettes and postures are uint16_t too)
HOLDERS = {'bchar_t', 'bspec_t', 'bproj_t'}

# --- the export's tables: type, owner -------------------------------------------------------------------------------
types = {}
text = ''
for s in SRC:
    t = open(os.path.join(build, s)).read(); text += t
    for typ, name in re.findall(r'^(?:static |extern )?const (\w+) (\w+)\s*[\[=;]', t, re.M): types[name] = typ
prefixes = re.findall(r'\{(?:"[^"]*"|slot_name), \d+, \d+, (\w+)_pals, ', text)          # bm_chars[] in BC_* order
nbc = len(re.search(r'enum \{ (BC_\w+(?:, BC_\w+)*), BC_COUNT \}', open(os.path.join(build, 'bm_chars.h')).read()).group(1).split(','))
assert len(prefixes) == nbc, (len(prefixes), nbc)
group = list(range(nbc))                                                    # union-find: form links share a bank
def root(i):
    while group[i] != i: i = group[i]
    return i
forms = list(re.finditer(r'(\w+)_vmore, (\d+), (\d+), (\d+), (\d+), (\d+), \1_holds\b', text))   # bchar_t: ..., vmore,
assert len(forms) == nbc, f'bm_chars[]: the form fields read for {len(forms)} of {nbc} fighters (bchar_t changed?)'   # fury_max,
for m in forms:                                                             # form_to, form_spec, form_trig, form_exit, holds
    i = prefixes.index(m.group(1)); to, trig = int(m.group(3)), int(m.group(5))
    if trig: group[root(i)] = root(to)
by_len = sorted(range(nbc), key=lambda i: -len(prefixes[i]))
def owner(sym):
    for i in by_len:
        if sym.startswith(prefixes[i] + '_'): return i
    return None
def banked_type(sym):
    t = types.get(sym)
    return t in BANKED or (t == 'uint16_t' and TILES.search(sym) is not None)

# --- sections and references (the compiler's: objdump) --------------------------------------------------------------
size, align = {}, {}
refs = {}                                                                   # symbol -> symbols it points to
for o in OBJ:
    p = os.path.join(build, o)
    for l in subprocess.run(['m68k-linux-gnu-objdump', '-h', p], capture_output=True, text=True, check=True).stdout.split('\n'):
        f = l.split()
        if len(f) >= 7 and f[1].startswith('.rodata.') and not f[1].startswith('.rodata.str'):
            sym = f[1][len('.rodata.'):]
            size[sym] = int(f[2], 16); align[sym] = 1 << int(f[6].split('**')[1])
        elif len(f) >= 7 and f[1] in ('.rodata', '.data', '.bss') and int(f[2], 16):
            sys.exit(f'bank_pack: {o} has a plain {f[1]} ({int(f[2], 16)} bytes): compile it with -fdata-sections')
    cur = None
    for l in subprocess.run(['m68k-linux-gnu-objdump', '-r', p], capture_output=True, text=True, check=True).stdout.split('\n'):
        m = re.match(r'RELOCATION RECORDS FOR \[\.rodata\.(\w+)\]', l)
        if m: cur = m.group(1); refs.setdefault(cur, set()); continue
        if l.startswith('RELOCATION RECORDS'): cur = None; continue
        f = l.split()
        if cur and len(f) == 3 and re.match(r'[0-9a-f]+$', f[0]):
            v = f[2].split('+')[0].split('-')[0]
            if v.startswith('.rodata.str'): continue                         # names: first MB
            refs[cur].add((int(f[0], 16), v[len('.rodata.'):] if v.startswith('.rodata.') else v))
missing = [s for s in size if s not in types]
assert not missing, f'sections without a declaration: {missing[:5]}'

# --- which tables go to a bank --------------------------------------------------------------------------------------
# a table's contexts: the fighters (groups) whose code may reach it, from bm_chars[i] (fighter i: its element of the
# array, by the relocation's offset) down every pointer. A table of a banked type goes to a bank only when its one
# context is its owner's group; otherwise (shared), it and everything it leads to stay in the first MB.
CHSIZE = size['bm_chars'] // nbc
def grp(s): o = owner(s); return None if o is None else root(o)
ctx = {}
work = []
for off, t in refs.get('bm_chars', ()):
    ctx.setdefault(t, set()).add(root(off // CHSIZE)); work.append(t)
while work:
    s = work.pop()
    for off, t in refs.get(s, ()):
        c = ctx.setdefault(t, set())
        if not ctx[s] <= c: c |= ctx[s]; work.append(t)
banked = {s for s in size if banked_type(s) and owner(s) is not None and ctx.get(s) == {grp(s)}}
shared = {s for s in size if banked_type(s) and owner(s) is not None and s not in banked}
for s in banked:                                                            # the engine's contract (fighter.c "banks"):
    for off, t in refs.get(s, ()):                                          # a bank table points only into its own bank
        assert t not in banked or grp(t) == grp(s), (s, t)                  # or the first MB; a first-MB table into a
for s, ts in refs.items():                                                  # bank only as a holder of its own fighter's
    if s in banked: continue
    for off, t in ts:
        if t in banked and not (types.get(s) in HOLDERS and (grp(s) == grp(t) or (s == 'bm_chars' and root(off // CHSIZE) == grp(t)))):
            sys.exit(f'bank_pack: {s} ({types.get(s)}, first MB) points to {t} in a bank')

# --- pack -----------------------------------------------------------------------------------------------------------
SLOT = prefixes.index('slot') if 'slot' in prefixes else None              # the shell's slot (packed apart, below)
assert SLOT is None or (root(SLOT) == SLOT and group.count(SLOT) == 1), 'the slot fighter has a form link'
gsize = {}                                                                  # an upper bound: each table's worst padding
for s in banked:
    if grp(s) != SLOT: gsize[grp(s)] = gsize.get(grp(s), 0) + size[s] + align[s] - 1
order = sorted(gsize, key=lambda g: (-gsize[g], g))
bins = []                                                                   # [used, [groups]]
gbank = {}
split = os.environ.get("BANK_SPLIT")                                        # proof layouts (TODO #174): bank = the parity
if split is not None:                                                       # of the fighter index's bits in a mask, so a read
    for g in sorted(gsize):                                                 # in the wrong bank shows in some layout
        k = bin(g & int(split, 0)).count("1") & 1                          # (bank_proof.py)
        while len(bins) <= k: bins.append([0, []])
        bins[k][0] += gsize[g]; bins[k][1].append(g); gbank[g] = k
    for k, b in enumerate(bins):
        if b[0] > CAP: sys.exit(f'bank_pack: BANK_SPLIT={split}: bank {k} needs {b[0]:,} bytes')
else:                                                                       # TODO #190: balanced, with headroom
    def balance(n, cap):                                                    # largest fighter first into the emptiest
        b = [[0, []] for _ in range(n)]                                     # bank (ties: the lowest bank)
        for g in order:
            k = min(range(n), key=lambda k: (b[k][0], k))
            if b[k][0] + gsize[g] > cap: return None
            b[k][0] += gsize[g]; b[k][1].append(g)
        return b
    for cap in (CAP - MARGIN, CAP):                                         # the fewest banks that each keep MARGIN
        for n in range(1, MAX_BANKS + 1):                                   # free; without the margin only when 7
            bins = balance(n, cap)                                          # banks cannot keep it
            if bins: break
        if bins: break
        print(f'bank_pack: WARNING: {MAX_BANKS} banks cannot each keep {MARGIN:,} bytes free')
    if not bins: sys.exit(f'bank_pack: the fighters need more than {MAX_BANKS} banks')
    for k, b in enumerate(bins):
        for g in b[1]: gbank[g] = k
if len(bins) > MAX_BANKS: sys.exit(f'bank_pack: {len(bins)} banks needed, the cart has {MAX_BANKS}')
if SLOT is not None:                                                        # the slot: the next bank, alone
    k = len(bins); n = sum(size[s] + align[s] - 1 for s in banked if grp(s) == SLOT)
    bins.append([n, [SLOT]]); gbank[SLOT] = k; gsize[SLOT] = n
    if len(bins) > MAX_BANKS: sys.exit(f'bank_pack: the slot needs bank {k}, the cart has {MAX_BANKS}')
for g, n in gsize.items():
    if n > CAP: sys.exit(f'bank_pack: {prefixes[g]} needs {n:,} bytes, more than a bank')
bank = [gbank.get(root(i), 0) for i in range(nbc)]

# --- outputs --------------------------------------------------------------------------------------------------------
with open(os.path.join(build, 'bank_rename.txt'), 'w') as f:
    for s in sorted(banked): f.write(f'--rename-section .rodata.{s}=.p2bank{bank[owner(s)]}\n')
    for s in sorted(x for x in size if x not in banked and owner(x) == SLOT and SLOT is not None):   # its first-MB tables
        f.write(f'--rename-section .rodata.{s}=.labslot\n')
with open(os.path.join(build, 'bm_bank.c'), 'w') as f:
    f.write('/* Generated by tools/brawler/bank_pack.py. Do not edit. Each fighter\'s P2 bank (fighter.h CH_BANK). */\n'
            '#include <stdint.h>\n'
            f'const uint8_t bm_bank[{nbc}] = {{' + ', '.join(map(str, bank)) + '};\n')
mb1 = sum(size[s] for s in size if s not in banked)
used = [b[0] for b in bins]                                                 # upper bounds (each table's worst padding)
rep = {'banks': [{'bank': k, 'used': used[k], 'free': CAP - used[k],
                  'fighters': [prefixes[i] for i in range(nbc) if bank[i] == k and any(owner(s) == i for s in banked)]}
                 for k in range(len(bins))],
       'first_mb_fighter_tables': mb1, **({'slot': {'bank': gbank[SLOT], 'banked': sum(size[s] for s in banked if owner(s) == SLOT),
                                             'labslot': sum(size[s] for s in size if s not in banked and owner(s) == SLOT)}} if SLOT is not None else {}), 'shared_to_first_mb': sorted(shared),
       'fighters': {prefixes[i]: {'bank': bank[i], 'banked': sum(size[s] for s in banked if owner(s) == i),
                                  'first_mb': sum(size[s] for s in size if s not in banked and owner(s) == i)} for i in range(nbc)}}
json.dump(rep, open(os.path.join(build, 'banks.json'), 'w'), indent=1)
lines = [f"bank {b['bank']}: {b['used']:,} used at most, {b['free']:,} free at least ({', '.join(b['fighters'])})" for b in rep['banks']]
lines.append(f'first MB: {mb1:,} bytes of fighter tables (steps, throws, postures, palettes, routes, voices, headers); '
             f'{len(shared)} shared tables ({sum(size[s] for s in shared):,} bytes) kept there')
open(os.path.join(build, 'banks.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
