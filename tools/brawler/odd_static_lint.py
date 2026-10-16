#!/usr/bin/env python3
"""BUILD GATE (2026-10-16, 0.10.153's reset on the FPGA / MVS as the referee walked in): no word / long access at an odd
address anywhere in the ROM's code, found statically (every instruction, run or not). A real 68000 takes an ADDRESS
ERROR there (SNK's MVS BIOS: garbage, a green screen, then the title: a reset; UniBIOS: its ADDRESS ERROR screen); our
stock emulator core ignores it, and hw_strict_proof.py only sees the code a playthrough runs.

    python3 odd_static_lint.py build/rom.elf [-v]          (examples/brawler/Makefile runs it on every link)

The two known sources: byte arrays read as words (export_bm.py's route trees, 0.10.152) and GCC 15's combine pass,
which folds `(int16_t)(long_in_memory >> 8)` into a word read of the long's bytes 1-2 (m68k, -mstrict-align or not:
rf_draw's rf.y in 0.10.153; main.c fx8_int is the safe form). The code = the linker map's .text input sections
(build/rom.map, written by the link: every object's code, C and assembly, none of the .rodata the linker script puts in
.text too; without a map, the ELF's FUNC symbols). Checked, for every word / long sized instruction (.w / .l, MOVEM,
MOVEA, ...; not LEA / PEA / branches):
  - an absolute operand at an odd address (`move.w $100115,d0`): an error;
  - a displacement off an address register (d16(An), d8(An,Xn)): its parity = the displacement's + the base's, the
    base's known when the code just set An from an absolute / immediate address (LEA abs, MOVEA #imm; forgotten at a
    label, a branch target, after an unconditional jump or a call); an odd sum, or an odd displacement off an unknown
    base (a struct pointer: even), is an error.
Exit 1 on any error, each listed with the symbol its instruction and its address fall in."""
import bisect, os, re, subprocess, sys

OBJDUMP, NM, READELF = 'm68k-linux-gnu-objdump', 'm68k-linux-gnu-nm', 'm68k-linux-gnu-readelf'
SIZED = re.compile(r'^(?!b|db|j|lea|pea|s(?!ub|wap)|link|unlk|trap|ext|swap)[a-z]+[wl]$')   # word / long ops


def operands(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch == ',' and depth == 0: out.append(cur.strip()); cur = ''; continue
        depth += ch == '('; depth -= ch == ')'; cur += ch
    if cur.strip(): out.append(cur.strip())
    return out


def code_ranges(elf):
    """(start, size) of the code: the map's .text input sections, else the FUNC symbols"""
    mp = elf.rsplit('.', 1)[0] + '.map'
    if os.path.exists(mp) and os.path.getmtime(mp) >= os.path.getmtime(elf) - 5:
        r, pend = [], False
        for ln in open(mp):
            if re.match(r'^ \.text(\.\S*)?\s*$', ln): pend = True; continue   # (a long name: its numbers on the next line)
            m = None
            if pend or ln.startswith(' .text'):
                m = re.match(r'^ (?:\.text(?:\.\S*)?)?\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+\S', ln)
            pend = False
            if m and int(m.group(2), 16): r.append((int(m.group(1), 16), int(m.group(2), 16)))
        if r: return sorted(r), 'linker map'
    r = []
    for ln in subprocess.run([READELF, '-sW', elf], capture_output=True, text=True, check=True).stdout.splitlines():
        f = ln.split()
        if len(f) >= 8 and f[3] == 'FUNC' and int(f[2], 0) > 0: r.append((int(f[1], 16), int(f[2], 0)))
    return sorted(r), 'FUNC symbols'


def lint(elf, verbose=False):
    ranges, how = code_ranges(elf); starts = [f[0] for f in ranges]
    syms = []
    for ln in subprocess.run([NM, '-n', elf], capture_output=True, text=True).stdout.splitlines():
        f = ln.split()
        if len(f) == 3: syms.append((int(f[0], 16), f[2]))
    sa = [s[0] for s in syms]; at_sym = set(sa)
    def sym(x):
        i = bisect.bisect_right(sa, x) - 1
        return f'{syms[i][1]}+{x - syms[i][0]:#x}' if i >= 0 else '?'
    def incode(a):
        i = bisect.bisect_right(starts, a) - 1
        return i >= 0 and a < ranges[i][0] + ranges[i][1]
    dis = subprocess.run([OBJDUMP, '-d', '--no-show-raw-insn', elf], capture_output=True, text=True, check=True).stdout
    ins = []
    for ln in dis.splitlines():
        m = re.match(r'\s+([0-9a-f]+):\s+(\S+)\s*(.*)', ln)
        if m and incode(int(m.group(1), 16)): ins.append((int(m.group(1), 16), m.group(2), m.group(3)))
    # the parity of each address register (0 even, 1 odd; absent: unknown) before each instruction: a forward dataflow
    # over the branches to a fixed point (a loop stepping An by an even amount keeps its parity)
    idx = {a: i for i, (a, _, _) in enumerate(ins)}
    parsed = [(a, op, operands(args), args) for a, op, args in ins]
    def step(i, st):
        """st after instruction i, and its successors"""
        a, op, ops, _ = parsed[i]; st = dict(st)
        if ops:
            mr = re.fullmatch(r'%(a[0-6]|fp)', ops[-1])
            if mr:
                r = mr.group(1); src = ops[0] if len(ops) > 1 else ''
                ml = re.fullmatch(r'([0-9a-f]+)(?: <[^>]*>)?', src)
                mi = re.fullmatch(r'#(-?\d+)', src)
                mo = re.fullmatch(r'%' + r + r'@\((-?\d+)\)', src)
                if op == 'lea' and ml: st[r] = int(ml.group(1), 16) & 1
                elif op in ('moveal', 'movel') and mi: st[r] = int(mi.group(1)) & 1
                elif op == 'lea' and mo and r in st: st[r] ^= int(mo.group(1)) & 1
                elif op[:4] in ('addq', 'subq', 'adda', 'suba') and mi and r in st: st[r] ^= int(mi.group(1)) & 1
                else: st.pop(r, None)
            for o in ops:                                 # (byte post-increments / pre-decrements move the parity)
                mp = re.fullmatch(r'%(a[0-6]|fp)@[+-]', o)
                if mp and op.endswith('b') and mp.group(1) in st: st[mp.group(1)] ^= 1
            if op.startswith(('jsr', 'bsr')): st.pop('a0', None); st.pop('a1', None)   # (the C ABI's scratch registers)
            if op.startswith('movem') and ops[-1].startswith('%'): st = {}   # (registers loaded from memory)
        succ = []
        if not (op in ('bras', 'braw', 'bral', 'jmp', 'rts', 'rte', 'rtr') or op.startswith('bra')): succ.append(i + 1)
        if op.startswith(('b', 'db')) and not op.startswith(('btst', 'bset', 'bclr', 'bchg', 'bsr')):
            m = re.search(r'(?:^|,)([0-9a-f]+) <', ', '.join(ops))
            if m and int(m.group(1), 16) in idx: succ.append(idx[int(m.group(1), 16)])
        return st, [s for s in succ if s < len(parsed)]
    IN = [None] * len(parsed)
    work = []
    for i, (a, _, _, _) in enumerate(parsed):            # (entries: every symbol, and the code after a gap: unknown)
        if a in at_sym or i == 0 or not incode(a - 2): IN[i] = {}; work.append(i)
    while work:
        i = work.pop()
        out, succ = step(i, IN[i])
        for s in succ:
            if IN[s] is None: IN[s] = out; work.append(s)
            else:
                j = {k: v for k, v in IN[s].items() if out.get(k) == v}   # (the join: what every path agrees on)
                if j != IN[s]: IN[s] = j; work.append(s)
    errs = []
    for i, (a, op, ops, args) in enumerate(parsed):
        if not SIZED.match(op): continue
        st = IN[i] if IN[i] is not None else {}
        for o in ops:
            if o.startswith('#') or '%pc' in o: continue
            ma = re.fullmatch(r'([0-9a-f]+)(?: <[^>]*>)?', o)
            if ma:
                x = int(ma.group(1), 16)
                if x & 1: errs.append((a, sym(a), op, args, f'absolute {x:#08x} ({sym(x)})'))
                continue
            md = re.fullmatch(r'%(a[0-7]|fp|sp)@\((-?[0-9a-fx]+)(,[^)]*)?\)', o)
            if md:
                r, d = md.group(1), md.group(2)
                d = int(d, 16) if md.group(3) else int(d, 0)  # (objdump: d16(An) decimal, d8(An,Xn) hex)
                if r in ('sp', 'a7'): continue                # (the stack: even by construction)
                p = st.get(r)
                if p is None and d & 1: errs.append((a, sym(a), op, args, f'odd displacement {d} off {r} (a pointer: even)'))
                elif p is not None and (p + d) & 1: errs.append((a, sym(a), op, args, f'{r} odd here + {d}: odd'))
    if verbose: print(f'odd_static_lint: {len(ins)} instructions, the code from the {how}')
    return errs


if __name__ == '__main__':
    if len(sys.argv) < 2: sys.exit(__doc__)
    errs = lint(sys.argv[1], '-v' in sys.argv)
    for a, where, op, args, why in errs: print(f'odd_static_lint: {a:#07x} {where}: {op} {args}: {why}')
    print('odd_static_lint: ' + (f'FAIL: {len(errs)} odd word / long accesses (an address error on a 68000)' if errs else 'OK'))
    sys.exit(1 if errs else 0)
