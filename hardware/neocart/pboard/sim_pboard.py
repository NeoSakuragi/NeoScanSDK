#!/usr/bin/env python3
"""Logic-level simulation of the P board v2 netlist (design.py).

Drives the gold fingers the way the MVS (PLAY) or the programmer (PROGRAM) does, models every chip at logic level
and checks what the flash chips see and what comes back on the bus. Any net driven to two different values raises
CONTENTION. Run: python3 sim_pboard.py
"""
import importlib.util, itertools, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

Z = None
POWER = {'P3V3': 1, 'VCC5': 1, 'GND': 0}
def pname(ref, pin): return re.sub(r'[~\\{}]', '', d.EXPECT.get((ref, str(pin)), ''))
PIN_NET, NAME_PIN = {}, {}
for net, lst in d.NETS.items():
    for ref, pin in lst:
        PIN_NET[(ref, pin)] = net; NAME_PIN[(ref, pname(ref, pin))] = pin
def netof(ref, name): return PIN_NET[(ref, NAME_PIN[(ref, name)])]

def pat(a, mask):
    """fake flash contents: every address bit changes the value"""
    x = (a * 2654435761) & 0xFFFFFFFF
    return (x ^ (x >> 13) ^ (x >> 24)) & mask

FINGER = {n for n in list(d.CTRG2_A.values()) + list(d.CTRG2_B.values()) if not n.startswith('NC_') and n not in POWER}

class Sim:
    def __init__(self):
        self.strong, self.weak, self.state, self.prev = {}, {}, {}, {}
        self.mem = {'U1': {}, 'U2': {}}                    # flash contents: word address -> 16 bit (U1), byte address -> 8 bit (U2, shared by both sample buses)
        self.writes = []                                    # (ref, address, data) seen on /WE rising edges
        for net in d.NETS:
            if net in POWER: self.strong[net] = {'power': POWER[net]}
        for ref in d.PARTS:
            if not ref.startswith('R'): continue
            a, b = PIN_NET[(ref, '1')], PIN_NET[(ref, '2')]
            if b in POWER and a not in POWER: self.weak[a] = POWER[b]
            elif a in POWER and b not in POWER: self.weak[b] = POWER[a]
        self.ext = {}                                       # finger nets driven from outside
    # --- net resolution ---
    def drive(self, net, src, val):
        if val is Z: self.strong.setdefault(net, {}).pop(src, None)
        else: self.strong.setdefault(net, {})[src] = val
    def val(self, net):
        s = self.strong.get(net, {})
        if s:
            vals = set(s.values())
            if len(vals) > 1: raise AssertionError(f'CONTENTION on {net}: {s}')
            return vals.pop()
        return self.weak.get(net, Z)
    def v(self, ref, name): return self.val(netof(ref, name))
    frozen = set()
    def out(self, ref, name, val):
        if (ref, name) in self.frozen: return
        self.drive(netof(ref, name), f'{ref}.{name}', val)
    def set(self, **kw):
        for net, val in kw.items(): self.drive(net, 'EXT', val)
        self.settle()
    def bus(self, prefix, width, value, start=0):
        for i in range(width): self.drive(f'{prefix}{start + i}', 'EXT', None if value is None else (value >> i) & 1)
    def read(self, prefix, width, start=0):
        vals = [self.val(f'{prefix}{start + i}') for i in range(width)]
        if any(x is Z for x in vals): return None
        return sum(b << i for i, b in enumerate(vals))
    # --- chip models ---
    def settle(self):
        for _ in range(60):
            before = {n: self.val(n) for n in d.NETS}
            self.step()
            after = {n: self.val(n) for n in d.NETS}
            if before == after: return
        raise AssertionError('did not settle')
    def edge(self, key, clk):
        rising = self.prev.get(key) == 0 and clk == 1
        self.prev[key] = clk
        return rising
    MODELLED = {'SN74LVC16245A', '74LVC16245A', '74LVC8T245', '74LVC16374A', 'SN74AHC273', 'SN74LVC08A', '74LVC08A', '74LVC32A', 'SN74LVC04A',
                'S29GL064N', 'S29GL128P'}
    def step(self):
        for ref, pt in d.PARTS.items():
            val = pt['value']
            if ref.startswith('U') and val not in self.MODELLED and ref != 'U19': raise AssertionError(f'{ref} ({val}) has no simulation model')
            if val in ('SN74LVC16245A', '74LVC16245A'):          # TI and Nexperia: same pinout and function
                for h in (1, 2):
                    oe, dr = self.v(ref, f'{h}OE'), self.v(ref, f'{h}DIR')
                    for b in range(1, 9):
                        a_, b_ = f'{h}A{b}', f'{h}B{b}'
                        if oe == 0 and dr == 1: self.out(ref, a_, Z); self.out(ref, b_, self.v(ref, a_))
                        elif oe == 0 and dr == 0: self.out(ref, b_, Z); self.out(ref, a_, self.v(ref, b_))
                        else: self.out(ref, a_, Z); self.out(ref, b_, Z)
            elif val == '74LVC8T245':
                oe, dr = self.v(ref, 'OE'), self.v(ref, 'DIR')
                for b in range(1, 9):
                    a_, b_ = f'A{b}', f'B{b}'
                    if oe == 0 and dr == 1: self.out(ref, a_, Z); self.out(ref, b_, self.v(ref, a_))
                    elif oe == 0 and dr == 0: self.out(ref, b_, Z); self.out(ref, a_, self.v(ref, b_))
                    else: self.out(ref, a_, Z); self.out(ref, b_, Z)
            elif val == '74LVC16374A':
                for h in (1, 2):
                    if self.edge((ref, h), self.v(ref, f'{h}CP')):
                        self.state[(ref, h)] = [self.v(ref, f'{h}D{b}') for b in range(8)]
                    st = self.state.get((ref, h), [Z] * 8)
                    oe = self.v(ref, f'{h}OE')
                    for b in range(8):
                        if (ref, str(d.X374_Q[h][b])) in PIN_NET and not PIN_NET[(ref, str(d.X374_Q[h][b]))].startswith('NC_'):
                            self.out(ref, f'{h}Q{b}', st[b] if oe == 0 else Z)
            elif val == 'SN74AHC273':
                if self.v(ref, 'CLR') == 0: self.state[(ref, 'q')] = [0] * 8
                elif self.edge((ref, 'clk'), self.v(ref, 'CLK')):
                    self.state[(ref, 'q')] = [self.v(ref, f'{n}D') for n in range(1, 9)]
                if self.v(ref, 'CLR') == 0: self.prev[(ref, 'clk')] = self.v(ref, 'CLK')
                q = self.state.get((ref, 'q'), [Z] * 8)
                for n in range(1, 4): self.out(ref, f'{n}Q', q[n - 1])
            elif val in ('SN74LVC08A', '74LVC08A', '74LVC32A'):
                for g in range(1, 5):
                    if PIN_NET[(ref, str(d.GATE2[g][2]))].startswith('NC_'): continue
                    a, b = self.v(ref, f'{g}A'), self.v(ref, f'{g}B')
                    if val in ('SN74LVC08A', '74LVC08A'): y = 0 if 0 in (a, b) else (1 if a == b == 1 else Z)
                    else: y = 1 if 1 in (a, b) else (0 if a == b == 0 else Z)
                    self.out(ref, f'{g}Y', y)
            elif val == 'SN74LVC04A':
                for g in range(1, 7):
                    a = self.v(ref, f'{g}A'); self.out(ref, f'{g}Y', Z if a is Z else 1 - a)
            elif val in ('S29GL064N', 'S29GL128P'):
                self.flash(ref, val)
    def flash_addr(self, ref, val):
        if val == 'S29GL064N':
            bits = [self.v(ref, f'A{i}') for i in range(22)]
        else:
            bits = [self.v(ref, 'DQ15/A-1')] + [self.v(ref, f'A{i}') for i in range(23)]
        if any(b is Z for b in bits): return None
        return sum(b << i for i, b in enumerate(bits))
    def flash(self, ref, val):
        word = val == 'S29GL064N'
        ce, oe, we = self.v(ref, 'CE'), self.v(ref, 'OE'), self.v(ref, 'WE')
        dq = [f'Q{i}' if word else f'DQ{i}' for i in range(16 if word else 8)]
        if word: dq[15] = 'Q15/A-1'
        if self.edge((ref, 'we'), we) and ce == 0:
            assert oe == 1, f'{ref}: /WE rose while /OE was low'
            a = self.flash_addr(ref, val); data = [self.v(ref, n) for n in dq]
            assert a is not None and all(x is not Z for x in data), f'{ref}: write with floating address/data {a} {data}'
            dv = sum(b << i for i, b in enumerate(data))
            self.mem[ref][a] = dv; self.writes.append((ref, a, dv))
        if ce == 0 and oe == 0 and we == 1:
            a = self.flash_addr(ref, val)
            dv = Z if a is None else self.mem[ref].get(a, pat(a, 0xFFFF if word else 0xFF))
            for i, n in enumerate(dq): self.out(ref, n, Z if dv is Z else (dv >> i) & 1)
        else:
            for n in dq: self.out(ref, n, Z)

# ---------------------------------------------------------------------------------------------------------------
STROBES_HIGH = dict(nROMOE=1, nROMOEU=1, nROMOEL=1, nPORTOEL=1, nPORTOEU=1, nPORTWEL=1, nPORTWEU=1, nPORTADRS=1,
                    nSDROE=1, nSDPOE=1, nRESET=1, RW=1, nAS=1, nSLOTCS=1, SDRMPX=0, SDPMPX=0, CLK68K=0, CLK4M=0)
def fresh(prog=False):
    s = Sim()
    for n in FINGER: s.drive(n, 'EXT', STROBES_HIGH.get(n, 0) if n in STROBES_HIGH else None)
    for n in ('nROMWAIT', 'nPWAIT0', 'nPWAIT1', 'nPDTACK'): s.drive(n, 'EXT', None)      # cart outputs, only pulled
    s.drive('nPROG', 'JUMPER', 0 if prog else None)
    s.set(nRESET=0); s.set(nRESET=1)
    return s

def p_read(s, addr_word, p2=False):
    """68K read of word address addr_word (A1..A19) in P1 ($000000) or the P2 window ($200000)"""
    s.bus('A', 19, addr_word, start=1); s.bus('D', 16, None)
    if p2: s.set(RW=1, nPORTADRS=0, nPORTOEL=0, nPORTOEU=0)
    else: s.set(RW=1, nROMOE=0)
    v = s.read('D', 16)
    s.set(nROMOE=1, nPORTOEL=1, nPORTOEU=1, nPORTADRS=1)
    return v

def bank_write(s, bank):
    s.bus('A', 19, 0x7FFF8, start=1); s.set(nPORTADRS=0, RW=0)        # $2FFFF0: A1..A19 word address 0x7FFF8
    s.bus('D', 16, bank); s.set(nPORTWEL=0); s.set(nPORTWEL=1)
    s.bus('D', 16, None); s.set(RW=1, nPORTADRS=1)

def ym_addr(s, bus, addr):
    """YM2610 address phase: low bits on the rising MPX edge, high bits on the falling edge"""
    if bus == 'A':
        s.bus('SDRAD', 8, addr & 0xFF); s.drive('SDRA8', 'EXT', (addr >> 8) & 1); s.drive('SDRA9', 'EXT', (addr >> 9) & 1)
        s.set(SDRMPX=1)
        s.bus('SDRAD', 8, (addr >> 10) & 0xFF); s.drive('SDRA8', 'EXT', (addr >> 18) & 1); s.drive('SDRA9', 'EXT', (addr >> 19) & 1)
        for k in range(4): s.drive(f'SDRA{20 + k}', 'EXT', (addr >> (20 + k)) & 1)
        s.set(SDRMPX=0)
    else:
        s.bus('SDPAD', 8, addr & 0xFF); [s.drive(f'SDPA{8 + k}', 'EXT', (addr >> (8 + k)) & 1) for k in range(4)]
        s.set(SDPMPX=1)
        s.bus('SDPAD', 8, (addr >> 12) & 0xFF); [s.drive(f'SDPA{8 + k}', 'EXT', (addr >> (20 + k)) & 1) for k in range(4)]
        s.set(SDPMPX=0)

def v_read(s, bus, addr):
    ym_addr(s, bus, addr)
    pad, oe = ('SDRAD', 'nSDROE') if bus == 'A' else ('SDPAD', 'nSDPOE')
    s.bus(pad, 8, None); s.set(**{oe: 0}); v = s.read(pad, 8); s.set(**{oe: 1})
    return v

def v_write(s, bus, addr, data):
    """programmer write cycle on a sample bus; on v3 only the ADPCM-A path (/ROMOEU) can write the flash"""
    ym_addr(s, bus, addr)
    pad, we = ('SDRAD', 'nROMOEU') if bus == 'A' else ('SDPAD', 'nROMOEL')
    s.set(RW=0); s.bus(pad, 8, data); s.set(**{we: 0}); s.set(**{we: 1}); s.bus(pad, 8, None); s.set(RW=1)

def p_write(s, addr_word, data, p2=False):
    s.bus('A', 19, addr_word, start=1)
    if p2: s.set(nPORTADRS=0)
    s.set(RW=0); s.bus('D', 16, data); s.set(nPORTWEU=0); s.set(nPORTWEU=1); s.bus('D', 16, None); s.set(RW=1, nPORTADRS=1)

# ---------------------------------------------------------------------------------------------------------------
results = []
def scenario(name):
    def deco(fn):
        try: fn(); results.append((name, 'OK', ''))
        except AssertionError as e: results.append((name, 'FAIL', str(e)))
        return fn
    return deco

MB_WORDS = 1 << 19
@scenario('PLAY: P1 read returns flash MB 7 (A1..A19 -> flash A0..A18)')
def _():
    s = fresh()
    for w in (0, 1, 0x12345, 0x7FFFF):
        exp = pat(7 * MB_WORDS + w, 0xFFFF)
        got = p_read(s, w); assert got == exp, f'word {w:#x}: got {got}, expected {exp:#06x}'

@scenario('PLAY: P2 reads follow the bank latch (bank n -> flash MB n, n = 0..6)')
def _():
    s = fresh()
    for bank in range(7):
        bank_write(s, bank)
        for w in (0, 0x40001, 0x7FFFF):
            a = bank * MB_WORDS + w; exp = pat(a, 0xFFFF)
            got = p_read(s, w, p2=True); assert got == exp, f'bank {bank} word {w:#x}: got {got}, expected {exp:#06x}'

@scenario('PLAY: /RESET clears the bank latch to 0')
def _():
    s = fresh(); bank_write(s, 5); s.set(nRESET=0); s.set(nRESET=1)
    exp = pat(0 * MB_WORDS, 0xFFFF)
    assert p_read(s, 0, p2=True) == exp

@scenario('PLAY: ADPCM-A 24-bit address capture on both SDRMPX edges, byte out on SDRAD')
def _():
    s = fresh(); rnd = random.Random(1)
    for a in [0, 1, 0xFFFFFF, 0x123456, 0xABCDEF] + [rnd.randrange(1 << 24) for _ in range(20)]:
        got = v_read(s, 'A', a); exp = pat(a, 0xFF)
        assert got == exp, f'A addr {a:#08x}: got {got}, expected {exp:#04x}'

@scenario('PLAY: ADPCM-B 24-bit address capture on both SDPMPX edges, byte out on SDPAD')
def _():
    s = fresh(); rnd = random.Random(2)
    for a in [0, 1, 0xFFFFFF, 0x654321] + [rnd.randrange(1 << 24) for _ in range(20)]:
        got = v_read(s, 'B', a); exp = pat(a, 0xFF)
        assert got == exp, f'B addr {a:#08x}: got {got}, expected {exp:#04x}'

@scenario('PLAY: sample reads still return data while the 68K is in a write cycle (R/W low, independent masters)')
def _():
    s = fresh()
    for bus in ('A', 'B'):
        for a in (0x000123, 0xFEDCBA):
            s.set(RW=0); ym_addr(s, bus, a)
            pad, oe = ('SDRAD', 'nSDROE') if bus == 'A' else ('SDPAD', 'nSDPOE')
            s.bus(pad, 8, None); s.set(**{oe: 0}); got = s.read(pad, 8); s.set(**{oe: 1}); s.set(RW=1)
            exp = pat(a, 0xFF)
            assert got == exp, f'{bus} addr {a:#08x} during a 68K write: got {got}, expected {exp:#04x}'

@scenario('PLAY: console strobes on /PORTWEU, /ROMOEU, /ROMOEL never write a flash (jumper parked)')
def _():
    s = fresh()
    for w in (0, 0x1234):
        p_write(s, w, 0xBEEF); p_write(s, w, 0xBEEF, p2=True)
        v_write(s, 'A', w, 0x77); v_write(s, 'B', w, 0x77)
    assert not s.writes, f'flash writes in PLAY: {s.writes}'

@scenario('PROGRAM: P writes land at the right flash address with the right data (P1 and every P2 bank)')
def _():
    s = fresh(prog=True); rnd = random.Random(3)
    exp = []
    for w in (0, 0x555, 0x2AA, 0x7FFFF):
        data = rnd.randrange(1 << 16); p_write(s, w, data); exp.append(('U1', 7 * MB_WORDS + w, data))
    for bank in range(7):
        bank_write(s, bank); data = rnd.randrange(1 << 16); p_write(s, 0x1000 + bank, data, p2=True)
        exp.append(('U1', bank * MB_WORDS + 0x1000 + bank, data))
    assert s.writes == exp, f'writes {s.writes}\n expected {exp}'
    assert p_read(s, 0x7FFFF) == exp[3][2], 'P1 read-back'

@scenario('PROGRAM: sample writes through the ADPCM-A path land at the right 24-bit byte address; read back through BOTH buses')
def _():
    s = fresh(prog=True); rnd = random.Random(4); exp = []
    for a in [0, 0xAAA, 0x555, 0xFFFFFF, rnd.randrange(1 << 24), rnd.randrange(1 << 24)]:
        data = rnd.randrange(256); v_write(s, 'A', a, data); exp.append(('U2', a, data))
        assert v_read(s, 'A', a) == data, f'A read-back at {a:#08x}'
        assert v_read(s, 'B', a) == data, f'B read-back at {a:#08x}'
    assert s.writes == exp, f'writes {s.writes}\n expected {exp}'

@scenario('PROGRAM: each write strobe reaches only its own flash; /ROMOEL writes nothing')
def _():
    s = fresh(prog=True)
    p_write(s, 0x10, 0x1111); assert [w[0] for w in s.writes] == ['U1']
    v_write(s, 'A', 0x10, 0x22); assert [w[0] for w in s.writes] == ['U1', 'U2']
    v_write(s, 'B', 0x10, 0x33); assert [w[0] for w in s.writes] == ['U1', 'U2'], s.writes

@scenario('PLAY: /SDROE and /SDPOE fall together - ADPCM-B gets its byte during its window, ADPCM-A its own byte after /SDPOE rises')
def _():
    s = fresh(); rnd = random.Random(5)
    for _ in range(12):
        aa, ab = rnd.randrange(1 << 24), rnd.randrange(1 << 24)
        ym_addr(s, 'A', aa); ym_addr(s, 'B', ab)
        s.bus('SDRAD', 8, None); s.bus('SDPAD', 8, None)
        s.set(nSDROE=0, nSDPOE=0)
        got_b = s.read('SDPAD', 8)
        assert got_b == pat(ab, 0xFF), f'B byte during the shared window: {got_b} vs {pat(ab, 0xFF):#04x}'
        s.set(nSDPOE=1)
        got_a = s.read('SDRAD', 8)
        assert got_a == pat(aa, 0xFF), f'A byte after /SDPOE rose: {got_a} vs {pat(aa, 0xFF):#04x}'
        s.set(nSDROE=1)

@scenario('ADDRESS BUS: never both register pairs enabled, in every /SDPOE and delayed-copy state')
def _():
    s = fresh()
    for sd in (0, 1):
        s.set(nSDPOE=sd)
        a_on, b_on = s.val('nASEL_OE') == 0, s.val('nBSEL_OE') == 0
        assert a_on != b_on, f'/SDPOE={sd}: A on {a_on}, B on {b_on}'
    # break-before-make, on the real netlist: freeze the delayed copy d (U18 gate 4 output) at the opposite level of /SDPOE,
    # which is the state the board passes through for ~2 gate delays on every edge. Neither register pair may drive then.
    for sd in (0, 1):
        t = fresh(); t.set(nSDPOE=sd)
        t.frozen = {('U18', '4Y')}; t.drive('PDLY', 'U18.4Y', None); t.drive('PDLY', 'FREEZE', 1 - sd); t.settle()
        assert t.val('nASEL_OE') == 1 and t.val('nBSEL_OE') == 1, f'mid-transition /SDPOE={sd} d={1 - sd}: A /OE {t.val("nASEL_OE")}, B /OE {t.val("nBSEL_OE")}'

def legal_states(prog):
    """every strobe combination the console (PLAY) or the programmer (PROGRAM) can present; R/W low only with every read strobe high"""
    names = ['nROMOE', 'nPORTOEL', 'nPORTOEU', 'nPORTWEL', 'nPORTWEU', 'nROMOEU', 'nROMOEL', 'nSDROE', 'nSDPOE', 'nPORTADRS', 'RW']
    for bits in itertools.product((0, 1), repeat=len(names)):
        st = dict(zip(names, bits))
        # the 68K never reads and writes at once; the YM2610 is a separate master, so in PLAY its /SDROE and /SDPOE are
        # independent of R/W. The programmer is one master: R/W low only with every read strobe high.
        reads68k = [st[n] for n in ('nROMOE', 'nPORTOEL', 'nPORTOEU')]
        if st['RW'] == 0 and 0 in reads68k: continue
        if prog and st['RW'] == 0 and 0 in (st['nSDROE'], st['nSDPOE']): continue
        if prog is False and st['RW'] == 1 and 0 in (st['nPORTWEL'], st['nPORTWEU']): continue   # the 68K writes with R/W low
        yield st

@scenario('CONTENTION: exhaustive strobe combinations, PLAY and PROGRAM, with the outside world driving D when R/W is low and SDRAD/SDPAD whenever their /OE is high')
def _():
    n = 0
    for prog in (False, True):
        for st in legal_states(prog):
            s = fresh(prog)
            s.bus('A', 19, 0x2A5A5, start=1)
            s.bus('D', 16, 0xC3C3 if st['RW'] == 0 else None)
            s.bus('SDRAD', 8, 0x5A if st['nSDROE'] == 1 else None)
            s.bus('SDPAD', 8, 0xA5 if st['nSDPOE'] == 1 else None)
            s.set(**st); n += 1
    results.append((f'  ({n} states checked)', 'OK', ''))

if __name__ == '__main__':
    fails = 0
    for name, st, msg in results:
        print(f'[{st:4}] {name}' + (f'\n        {msg}' if msg else ''))
        fails += st == 'FAIL'
    print(f'{len(results)} checks, {fails} failed')
    sys.exit(1 if fails else 0)
