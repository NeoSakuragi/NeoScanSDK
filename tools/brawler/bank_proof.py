#!/usr/bin/env python3
"""TODO #174 proof: the banked P ROM as the build wrote it, as Geolith maps it and as the NeoCart PROG v3 board holds it.

    python3 bank_proof.py [GAME_DIR]      (default examples/brawler, built)

1. The link: every .p2bankN section of build/rom.elf is whole in the .neo's P region at MB 1 + N (Geolith: bank N =
   P offset (N + 1) MB, geo_m68k.c banksw), MB1 = the ELF's $000000 bytes; the bank's used / free bytes (1 MB - 16).
2. The cart: hardware/neocart/pboard/pboard_flash.images() (the v3 chip map: P1 at flash MB 7, bank n at MB n) holds
   the same bytes at those places (the chip image is the .neo's byte order, pboard_flash.py).
3. The tables: every table linked into a bank belongs to a fighter of that bank (build/banks.json); the pointers
   between tables were checked before the link (bank_pack.py: none from a bank into another)."""
import sys, os, json, struct, subprocess, re
HERE = os.path.dirname(os.path.abspath(__file__))
game = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'hardware', 'neocart', 'pboard'))
import pboard_flash

elf = os.path.join(game, 'build', 'rom.elf'); neo = os.path.join(game, 'brawler.neo')
CAP = 0x100000 - 16
ok = True
def bad(msg):
    global ok
    ok = False; print('FAIL', msg)

# --- 1. the link vs the .neo -----------------------------------------------------------------------------------------
regions = pboard_flash.neo_regions(neo); P = regions['P']
def swap(b): return bytes(b[i ^ 1] for i in range(len(b)))          # the .neo's P is word-swapped (neobuild.py)
secs = {}
for l in subprocess.run(['m68k-linux-gnu-objdump', '-h', elf], capture_output=True, text=True, check=True).stdout.split('\n'):
    f = l.split()
    if len(f) >= 7 and re.match(r'\d+$', f[0]): secs[f[1]] = (int(f[2], 16), int(f[3], 16), int(f[4], 16))   # size, VMA, LMA
banks = sorted(int(n[len('.p2bank'):]) for n in secs if n.startswith('.p2bank'))
print(f'P ROM {len(P):,} bytes = MB1 + {len(P) // 0x100000 - 1} bank(s); ELF banks {banks}')
if len(P) != 0x100000 * (1 + len(banks)): bad('P size is not 1 MB + 1 MB per bank')
for n in banks:
    size, vma, lma = secs[f'.p2bank{n}']
    if vma != 0x200000 or lma != 0x200000 + n * 0x100000: bad(f'bank {n}: VMA {vma:#x} LMA {lma:#x}')
    data = subprocess.run(['m68k-linux-gnu-objcopy', '-O', 'binary', '--only-section', f'.p2bank{n}', elf, '/dev/stdout'],
                          capture_output=True, check=True).stdout
    at = (1 + n) * 0x100000
    same = swap(P[at:at + size]) == data
    print(f'bank {n}: {size:,} bytes used, {CAP - size:,} free; .neo P MB {1 + n} {"=" if same else "!="} the ELF section')
    if not same: bad(f'bank {n} bytes')
    if size > CAP: bad(f'bank {n} over 1 MB - 16')
import tempfile
with tempfile.NamedTemporaryFile(suffix='.bin') as t:                # the whole program as neobuild.py takes it
    subprocess.run(['m68k-linux-gnu-objcopy', '-O', 'binary', elf, t.name], check=True); mb1 = open(t.name, 'rb').read()[:0x100000]
used = secs['.data'][2] + secs['.data'][0]                            # the last byte loaded in MB1: .data's initial values
same = swap(P[:len(mb1)]) == mb1
print(f'MB1: {used:,} bytes used, {0x100000 - used:,} free; .neo P MB 0 {"=" if same else "!="} the ELF')
if not same: bad('MB1 bytes')

# --- 2. the NeoCart PROG v3 chip image -------------------------------------------------------------------------------
img, _ = pboard_flash.images(neo)
chip = img['P']
if chip[7 << 20:(7 << 20) + 0x100000] != P[:0x100000]: bad('cart: P1 is not at flash MB 7')
for n in banks:
    if chip[n << 20:(n << 20) + 0x100000] != P[(1 + n) << 20:(2 + n) << 20]: bad(f'cart: bank {n} is not at flash MB {n}')
print(f'NeoCart PROG v3 image: P1 at flash MB 7, banks {banks} at flash MB {banks}: {"same bytes" if ok else "MISMATCH"}')

# --- 3. the tables ---------------------------------------------------------------------------------------------------
rep = json.load(open(os.path.join(game, 'build', 'banks.json')))
syms = {}                                                             # address -> [(name, size, bank or None)]
where = {}
for l in subprocess.run(['m68k-linux-gnu-objdump', '-t', elf], capture_output=True, text=True, check=True).stdout.split('\n'):
    m = re.match(r'([0-9a-f]{8}) .{7} (\S+)\s+([0-9a-f]{8}) (\S+)$', l)
    if not m: continue
    addr, sec, size, name = int(m.group(1), 16), m.group(2), int(m.group(3), 16), m.group(4)
    b = int(sec[len('.p2bank'):]) if sec.startswith('.p2bank') else None
    where[name] = (addr, size, b, sec)
names = {f: v for f, v in rep['fighters'].items()}
wrong = 0
for name, (addr, size, b, sec) in where.items():
    if b is None or name.startswith('.'): continue
    f = max((p for p in names if name.startswith(p + '_')), key=len, default=None)
    if f is None or names[f]['bank'] != b: wrong += 1; bad(f'{name} in bank {b}, its fighter {f} has bank {names.get(f, {}).get("bank")}')
print(f'{sum(1 for k, v in where.items() if v[2] is not None and not k.startswith(".")):,} banked tables, each in its fighter\'s bank: {"yes" if not wrong else wrong}')
print('ALL OK' if ok else 'FAILED')
sys.exit(0 if ok else 1)
