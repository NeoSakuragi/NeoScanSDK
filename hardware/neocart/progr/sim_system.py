#!/usr/bin/env python3
"""System simulation: the programmer netlist (design.py) plugged into the NeoCart PROG board netlist (../pboard/design.py).

The two netlists are joined at the slot: every finger net keeps its name, the programmer's VCART is the board's VCC5,
every other programmer part and net gets the suffix '@H'. Chip models come from ../pboard/sim_pboard.py (one engine);
this file adds the SN74LVC16T245 (with VCC isolation) and the TPS2553 cart switch, and models the RP2350 firmware as
the only external driver: it can only touch GPIO nets. Run: python3 sim_system.py
"""
import importlib.util, os, random, re, sys, types
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
H = _load('progr_design', os.path.join(HERE, 'design.py'))
SP = _load('sim_pboard', os.path.join(HERE, '..', 'pboard', 'sim_pboard.py'))     # also runs the board's own 14 checks
PB = SP.d
assert all(st == 'OK' for _, st, _ in SP.results), 'PROG board simulation fails on its own'

# --- merged netlist ------------------------------------------------------------------------------------------------------
XDIR, OE_D, OE_VA, OE_VB, OE_OUT, LCLK1, LCLK2, VCART_EN = (H.CTRL[n] for n in ('XDIR', 'nOE_D', 'nOE_VA', 'nOE_VB', 'nOE_OUT', 'LCLK1', 'LCLK2', 'VCART_EN'))
SHARED = {n for n in H.CART.values() if not n.startswith('NC_')} | {'GND'}
def hnet(n):
    if n == 'VCART': return 'VCC5'
    return n if n in SHARED else f'{n}@H'
NETS, EXPECT, PARTS = defaultdict(list), {}, {}
for net, lst in PB.NETS.items(): NETS[net] += lst
EXPECT.update(PB.EXPECT); PARTS.update(PB.PARTS)
for net, lst in H.NETS.items(): NETS[hnet(net)] += [(f'{r}@H', p) for r, p in lst]
for (r, p), v in H.EXPECT.items(): EXPECT[(f'{r}@H', p)] = v
for r, pt in H.PARTS.items(): PARTS[f'{r}@H'] = pt
d = types.SimpleNamespace(NETS=NETS, EXPECT=EXPECT, PARTS=PARTS, X374_Q=PB.X374_Q, GATE2=PB.GATE2)

# point the engine at the merged netlist
SP.d = d
SP.PIN_NET.clear(); SP.NAME_PIN.clear()
for net, lst in NETS.items():
    for ref, pin in lst:
        SP.PIN_NET[(ref, pin)] = net; SP.NAME_PIN[(ref, SP.pname(ref, pin))] = pin
SP.POWER.clear(); SP.POWER.update({'P3V3': 1, 'GND': 0, 'P3V3@H': 1, 'VBUS@H': 1})     # P3V3@H = the module's 3.3 V output      # VCC5 (= VCART) comes from the TPS2553 model

class System(SP.Sim):
    MODELLED = SP.Sim.MODELLED | {'SN74LVC16T245', 'TPS2553', 'WeAct RP2350B'}
    def __init__(self, jumper_prog=True):
        super().__init__()
        self.drive('nPROG', 'JUMPER', 0 if jumper_prog else None)
        for ref in PARTS:                                          # pull-ups to the switched cart 5 V (VCC5 is not a fixed rail here)
            if ref.startswith('R'):
                a, b = SP.PIN_NET[(ref, '1')], SP.PIN_NET[(ref, '2')]
                if b == 'VCC5': self.weak[a] = 1
                elif a == 'VCC5': self.weak[b] = 1
        self.gpio = {}
        self.settle()
    def step(self):
        super().step()                                              # every PROG board chip + the 16245/16374 on the programmer
        for r, a, b in SERIES: self.drive(b, f'{r}.series', self.val(a))       # 1k series resistors: cart output -> MCU input
        for ref, pt in PARTS.items():
            if pt['value'] == 'TPS2553':
                self.out(ref, 'OUT', 1 if self.v(ref, 'EN') == 1 else 0)
            elif pt['value'] == 'SN74LVC16T245':
                powered = self.v(ref, 'VCCA') == 1 and self.v(ref, 'VCCB') == 1
                for h in (1, 2):
                    oe, dr = self.v(ref, f'{h}OE'), self.v(ref, f'{h}DIR')
                    for b in range(1, 9):
                        a_, b_ = f'{h}A{b}', f'{h}B{b}'
                        bpin = NAME_PIN_ok(ref, b_)
                        if not powered or oe != 0 or dr is None:
                            self.out(ref, a_, None)
                            if bpin: self.out(ref, b_, None)
                        elif dr == 1:
                            self.out(ref, a_, None)
                            if bpin: self.out(ref, b_, self.v(ref, a_))
                        else:
                            if bpin: self.out(ref, b_, None)
                            self.out(ref, a_, self.v(ref, b_) if bpin else None)
    # --- firmware (RP2350): it can only drive or read GPIO nets ---------------------------------------------------------
    def pin(self, g, val):
        net = H.GPIO_NET[g]; self.drive(hnet(net), 'MCU', val); self.gpio[g] = val
    def pins(self, kw):
        for g, v in kw.items(): self.pin(g, v)
        self.settle()
    def read_md(self, bits=range(16)):
        for i in range(16): self.pin(i, None)
        self.settle(); vals = [self.val(f'MD{i}@H') if i in bits else 0 for i in range(16)]
        return None if None in vals else sum(b << i for i, b in enumerate(vals))
    def put_md(self, value):
        for i in range(16): self.pin(i, (value >> i) & 1)
    G = {n: g for g, n2 in H.GPIO_NET.items() for n in [n2[2:]] if n2.startswith('G_')}
    def strobe(self, **kw): self.pins({self.G[n]: v for n, v in kw.items()})
    def latch(self, which, value):
        clk = LCLK1 if which == 1 else LCLK2
        self.put_md(value); self.pins({clk: 0}); self.pins({clk: 1}); self.pins({clk: 0})
    slow = dict(A17=0, A18=0, A19=0, SDRA8=0, SDRA9=0, SDRA20=0, SDRA21=0, SDRA22=0, SDRA23=0, SDPA8=0, SDPA9=0, SDPA10=0, SDPA11=0, nRESET=1, CLK4M=0, nSLOTCS=1)
    def set_slow(self, **kw):
        self.slow.update(kw)
        self.latch(2, sum(self.slow[n] << i for i, n in enumerate(H.LAT2)))
    def address(self, word):
        self.latch(1, word & 0xFFFF); self.set_slow(A17=(word >> 16) & 1, A18=(word >> 17) & 1, A19=(word >> 18) & 1)
    def power_on(self):
        """the order the firmware must follow: strobes idle and latches loaded while every output is still disabled,
        then cart power, then the output enables"""
        self.slow = dict(System.slow)
        self.pins({XDIR: 0, OE_D: 1, OE_VA: 1, OE_VB: 1, OE_OUT: 1})              # XDIR read, every OE off
        self.strobe(**{n: (0 if n in ('SDRMPX', 'SDPMPX', 'CLK68K') else 1) for n in H.STROBES})
        self.address(0); self.set_slow(nRESET=0)
        self.pins({VCART_EN: 1})                                          # VCART on
        self.pins({OE_OUT: 0})                                          # strobes + address drivers on
        self.set_slow(nRESET=1)
    def data_out(self, value):          # D0-D15 driven by the programmer
        self.put_md(value); self.pins({XDIR: 1, OE_D: 0})
    def data_release(self):
        self.pins({OE_D: 1, XDIR: 0}); [self.pin(i, None) for i in range(16)]; self.settle()
    def release_md(self):
        for i in range(16): self.pin(i, None)
        self.settle()
    def data_in(self):
        self.release_md()                                           # rule: MD0-15 released BEFORE a transceiver turns toward the MCU
        self.pins({XDIR: 0, OE_D: 0}); v = self.read_md(); self.pins({OE_D: 1}); return v
    # --- cart cycles (same sequences as PROGRAMMING.md section 6) -------------------------------------------------------
    def p_write(self, word, data, p2=False):
        self.address(word)
        if p2: self.strobe(nPORTADRS=0)
        self.strobe(RW=0); self.data_out(data); self.strobe(nPORTWEU=0); self.strobe(nPORTWEU=1)
        self.data_release(); self.strobe(RW=1, nPORTADRS=1)
    def p_read(self, word, p2=False):
        self.address(word)
        if p2: self.strobe(nPORTADRS=0, nPORTOEL=0, nPORTOEU=0)
        else: self.strobe(nROMOE=0)
        v = self.data_in(); self.strobe(nROMOE=1, nPORTOEL=1, nPORTOEU=1, nPORTADRS=1); return v
    def bank_write(self, bank):
        self.address(0x7FFF8); self.strobe(nPORTADRS=0, RW=0); self.data_out(bank)
        self.strobe(nPORTWEL=0); self.strobe(nPORTWEL=1); self.data_release(); self.strobe(RW=1, nPORTADRS=1)
    def ym_addr(self, bus, addr):
        oe = OE_VA if bus == 'A' else OE_VB
        if bus == 'A':
            self.set_slow(SDRA8=(addr >> 8) & 1, SDRA9=(addr >> 9) & 1)
            self.put_md(addr & 0xFF); self.pins({XDIR: 1, oe: 0}); self.strobe(SDRMPX=1)
            self.set_slow(SDRA8=(addr >> 18) & 1, SDRA9=(addr >> 19) & 1, **{f'SDRA{20 + k}': (addr >> (20 + k)) & 1 for k in range(4)})
            self.put_md((addr >> 10) & 0xFF); self.settle(); self.strobe(SDRMPX=0)
        else:
            self.set_slow(**{f'SDPA{8 + k}': (addr >> (8 + k)) & 1 for k in range(4)})
            self.put_md((addr & 0xFF) << 8); self.pins({XDIR: 1, oe: 0}); self.strobe(SDPMPX=1)
            self.set_slow(**{f'SDPA{8 + k}': (addr >> (20 + k)) & 1 for k in range(4)})
            self.put_md(((addr >> 12) & 0xFF) << 8); self.settle(); self.strobe(SDPMPX=0)
        self.pins({oe: 1, XDIR: 0}); [self.pin(i, None) for i in range(16)]; self.settle()
    def v_read(self, bus, addr):
        self.ym_addr(bus, addr); oe = OE_VA if bus == 'A' else OE_VB
        self.strobe(**{('nSDROE' if bus == 'A' else 'nSDPOE'): 0})
        self.release_md(); self.pins({XDIR: 0, oe: 0}); v = self.read_md(range(8) if bus == 'A' else range(8, 16)); self.pins({oe: 1})
        self.strobe(**{('nSDROE' if bus == 'A' else 'nSDPOE'): 1})
        return None if v is None else ((v & 0xFF) if bus == 'A' else (v >> 8))
    def v_write(self, addr, data):
        self.ym_addr('A', addr)
        self.strobe(RW=0); self.put_md(data); self.pins({XDIR: 1, OE_VA: 0})
        self.strobe(nROMOEU=0); self.strobe(nROMOEU=1)
        self.pins({OE_VA: 1, XDIR: 0}); [self.pin(i, None) for i in range(16)]; self.settle(); self.strobe(RW=1)

SERIES = [(f'{r}@H', SP.PIN_NET[(f'{r}@H', '1')], SP.PIN_NET[(f'{r}@H', '2')]) for r in H.PARTS
          if r.startswith('R') and H.PARTS[r]['value'] == '1k' and SP.PIN_NET[(f'{r}@H', '1')] in H.CART_INPUTS]
def NAME_PIN_ok(ref, name):
    pin = SP.NAME_PIN.get((ref, name)); return pin and not SP.PIN_NET[(ref, pin)].startswith('NC_')

# ---------------------------------------------------------------------------------------------------------------------------
results = []
def scenario(name):
    def deco(fn):
        try: fn(); results.append((name, 'OK', ''))
        except AssertionError as e: results.append((name, 'FAIL', str(e)))
        return fn
    return deco
CART_NETS = sorted(SHARED - {'GND', 'nROMWAIT', 'nPWAIT0', 'nPWAIT1', 'nPDTACK'})
MB = 1 << 19

@scenario('POWER-UP: MCU pins at reset (inputs) -> no programmer output drives any cart line, cart 5 V off')
def _():
    s = System()
    assert s.val('VCC5') == 0, 'cart powered at reset'
    drivers = {n: [k for k in s.strong.get(n, {}) if k.endswith('@H')] for n in CART_NETS}
    assert not any(drivers.values()), {n: v for n, v in drivers.items() if v}

@scenario('POWER: cart 5 V on but output enables still high -> still nothing driven by the programmer')
def _():
    s = System(); s.pins({VCART_EN: 1})
    assert s.val('VCC5') == 1
    assert not any(k.endswith('@H') for n in CART_NETS for k in s.strong.get(n, {}))

@scenario('POWER: output enable low while the cart is unpowered -> 16T245 B ports stay off (VCC isolation)')
def _():
    s = System(); s.strobe(**{n: 0 for n in H.STROBES}); s.put_md(0x5AA5); s.pins({XDIR: 1, LCLK1: 1, LCLK2: 1}); s.pins({OE_OUT: 0, OE_VA: 0, OE_VB: 0})
    assert not any(k.endswith('@H') for n in CART_NETS if n not in [f'D{i}' for i in range(16)] for k in s.strong.get(n, {}))

@scenario('IDENTIFY: P1 read through the programmer returns flash MB 7 (the board PLAY read path)')
def _():
    s = System(jumper_prog=False); s.power_on()
    for w in (0, 1, 0x80, 0x12345, 0x7FFFF):
        exp = SP.pat(7 * MB + w, 0xFFFF); got = s.p_read(w)
        assert got == exp, f'word {w:#x}: got {got}, expected {exp:#06x}'

@scenario('PROGRAM: P writes through the programmer land in U1 at the right address (P1 + every P2 bank) and read back')
def _():
    s = System(); s.power_on(); rnd = random.Random(7); exp = []
    for w in (0x555, 0x2AA, 0x7FFFF, 0):
        dv = rnd.randrange(1 << 16); s.p_write(w, dv); exp.append(('U1', 7 * MB + w, dv))
    for bank in range(7):
        s.bank_write(bank); dv = rnd.randrange(1 << 16); s.p_write(0x2000 + bank, dv, p2=True); exp.append(('U1', bank * MB + 0x2000 + bank, dv))
        assert s.p_read(0x2000 + bank, p2=True) == dv, f'bank {bank} read-back'
    assert s.writes == exp, f'{s.writes}\n expected {exp}'
    assert s.p_read(0x7FFFF) == exp[2][2]

@scenario('PROGRAM: sample bytes written through ADPCM-A land in U2 at the 24-bit address; read back through both buses')
def _():
    s = System(); s.power_on(); rnd = random.Random(8); exp = []
    for a in [0, 0xAAA, 0x555, 0xFFFFFF, 0x800000] + [rnd.randrange(1 << 24) for _ in range(6)]:
        dv = rnd.randrange(256); s.v_write(a, dv); exp.append(('U2', a, dv))
        assert s.v_read('A', a) == dv, f'A read-back at {a:#08x}'
        assert s.v_read('B', a) == dv, f'B read-back at {a:#08x}'
    assert s.writes == exp, f'{s.writes}\n expected {exp}'

@scenario('DUMP: unwritten sample space reads the flash pattern through both buses (what a dump of a programmed board sees)')
def _():
    s = System(jumper_prog=False); s.power_on(); rnd = random.Random(9)
    for a in [1, 0x123456] + [rnd.randrange(1 << 24) for _ in range(6)]:
        for bus in ('A', 'B'):
            got = s.v_read(bus, a); assert got == SP.pat(a, 0xFF), f'{bus} {a:#08x}: {got}'

@scenario('CART INPUTS: /ROMWAIT /PWAIT0 /PWAIT1 /PDTACK (pulled up on the board) read 1 on GPIO16-19')
def _():
    s = System(); s.power_on()
    for i in range(4):
        assert s.val(f'S_{H.CART_INPUTS[i]}@H') == 1, H.CART_INPUTS[i]

@scenario('JUMPER on PLAY: the same programmer write sequences change nothing in either flash')
def _():
    s = System(jumper_prog=False); s.power_on()
    s.p_write(0x555, 0xAAAA); s.bank_write(3); s.p_write(0x10, 0x1234, p2=True); s.v_write(0xAAA, 0xAA)
    assert not s.writes, s.writes

if __name__ == '__main__':
    fails = 0
    for name, st, msg in results:
        print(f'[{st:4}] {name}' + (f'\n        {msg}' if msg else ''))
        fails += st == 'FAIL'
    print(f'{len(results)} checks, {fails} failed')
    sys.exit(1 if fails else 0)
