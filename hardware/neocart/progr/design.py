#!/usr/bin/env python3
"""NeoCart programmer v1 - declarative netlist (single source of truth).

A USB host for MVS PROG boards (CTRG2): the board plays the console. An RP2350B drives every cart line through 5 V
level shifters, so it can flash and verify the NeoCart PROG board (JP1 on PROGRAM, see ../pboard/PROGRAMMING.md),
dump an original SNK PROG board, and run bus tests driven from the PC (agentic cart debugging).

- MCU: a WeAct Studio RP2350B Core Board plugged into the board (github.com/WeActStudio/WeActStudio.RP2350BCoreBoard,
  HDK/RP2350B_SCH.pdf, RP2350B_PINOUT.png, 尺寸图.pdf): RP2350B with the Raspberry Pi reference circuit, 16 MB flash, 3.3 V
  regulator, USB-C, BOOT/RESET buttons, SWD, all 48 GPIO on two double rows of 15 (2.54 mm). The bare QFN-80 version
  (out/design_v1_bare_rp2350.py) did not route cleanly on 2 layers; the module removes every fine-pitch part from this board.
  The module itself uses GPIO25 (LED, 5.1k) and GPIO23 (KEY to GND, 5.1k pull-up): they become our BUSY LED and FLASH button.
- GPIO0-15 = MD0-15, an internal 16-bit bus shared by the data transceivers (A side) and the address latch inputs.
- GPIO26-40 = 15 cart strobes, contiguous for PIO, straight through a level shifter (RP2350 PIO: ~7 ns steps).
- Addresses that change slowly (A1-A19, ADPCM high address bits, /RESET, 4 MHz, /SLOTCS) come from two 74LVC16374
  latches loaded from MD0-15 (LCLK1, LCLK2), then a level shifter.
- Level shifters toward the cart: SN74LVC16T245, A side 3.3 V, B side = VCART (the switched cart 5 V). With the cart
  unpowered every B port is high impedance (TI "VCC isolation"), so the programmer can never back-power a cart.
- D0-D15 go through a 74LVC16245A at 3.3 V instead: the NeoCart PROG board drives D0-D15 at 3.3 V (its own LVC16245),
  which a 5 V-referenced input (V_IH = 0.7 x 5 V = 3.5 V) would not accept; LVC inputs take 2.0 V and tolerate 5.5 V.
- Sample buses SDRAD0-7 / SDPAD0-7 are 5 V on both sides (the PROG board's 74LVC8T245 B port runs at 5 V and needs
  3.5 V for a high in PROGRAM writes): SN74LVC16T245 with VCCB = VCART.
- Cart 5 V: TPS2553 current-limited switch (R_ILIM 33k: 0.79 A typical), enable + fault to the MCU, VCART on an ADC pin.
- /ROMWAIT, /PWAIT0, /PWAIT1, /PDTACK (cart outputs) into 5 V-tolerant GPIO31-34 (RP2350 "Digital IO (FT)", GPIO0-39:
  tolerate 5.5 V while IOVDD = 3.3 V) through 1k: GPIO16-19.

Pin numbers checked against: WeAct RP2350B core board pinout/drawing, TI SN74LVC16T245 (SCES636B) pin configuration,
Nexperia 74LVC16245A, Nexperia/TI 74LVC16374A, TI TPS2553 (SLVS841F) DBV pinout, Winbond W25Q32JV, the slot drawing
EDAC 345-120-520-201 (2.54 mm pitch, 5.08 mm row spacing). check() also compares every pin name with the symbol.
"""
import importlib.util, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('pboard_design', os.path.join(HERE, '..', 'pboard', 'design.py'))
PB = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(PB)      # the cart side: CTRG2 pinout + PROG board netlist
CTRG2_A, CTRG2_B = PB.CTRG2_A, PB.CTRG2_B

PARTS = {}
def part(ref, lcsc, symbol, footprint, value, desc):
    PARTS[ref] = dict(lcsc=lcsc, symbol=symbol, footprint=footprint, value=value, desc=desc)

part('J1', None, None, 'MVS_SLOT_EDAC_345-120', 'MVS slot', 'EDAC 345-120-520-201 (or Sullins EBC60DCxN): 2x60 card edge, 2.54 mm, hand-soldered, not from LCSC')
part('U1', None, None, 'WEACT_RP2350B_CORE', 'WeAct RP2350B', 'WeAct Studio RP2350B Core Board (bought separately, ~$4.21), on 2 x (2x15) 2.54 mm headers, hand-soldered')
part('U4', 'C55266', 'TPS2553DBVR', 'SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR', 'TPS2553', 'cart 5 V switch, current limit 0.79 A typ (R_ILIM 33k)')
part('U5', 'C548160', 'SN74LVC16245ADGGR', 'TSSOP-48_L12.5-W6.1-P0.50-LS8.1-BL', '74LVC16245A', 'D0-D15 <-> MD0-15 at 3.3 V (5 V tolerant)')
part('U6', 'C148170', 'SN74LVC16T245DGGR', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', 'SN74LVC16T245', 'SDRAD0-7 / SDPAD0-7 <-> MD0-7 / MD8-15, 3.3 V <-> 5 V')
part('U7', 'C148170', 'SN74LVC16T245DGGR', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', 'SN74LVC16T245', '15 strobes GPIO26-40 -> cart, 3.3 V -> 5 V')
part('U8', 'C148170', 'SN74LVC16T245DGGR', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', 'SN74LVC16T245', 'A1-A16 latch outputs -> cart, 3.3 V -> 5 V')
part('U9', 'C148170', 'SN74LVC16T245DGGR', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', 'SN74LVC16T245', 'A17-A19, ADPCM high bits, /RESET, 4 MHz, /SLOTCS -> cart')
part('U10', 'C6074', '74LVC16374ADGG,118', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', '74LVC16374A', 'latch: A1-A16 from MD0-15 (LCLK1)')
part('U11', 'C6074', '74LVC16374ADGG,118', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', '74LVC16374A', 'latch: slow lines from MD0-15 (LCLK2)')
part('LED1', 'C2286', 'KT-0603R', 'LED-SMD_L1.6-W0.8-R-RD', 'CART', 'cart 5 V on')

PASSIVE = {'100n': ('C14663', 'C0603'), '10u': ('C15850', 'C0805'), '10k': ('C25804', 'R0603'), '1k': ('C21190', 'R0603'),
           '33k': ('C4216', 'R0603')}

NETS = defaultdict(list)
EXPECT = {}
def conn(ref, pin, net, name=None):
    NETS[net].append((ref, str(pin)))
    if name: EXPECT[(ref, str(pin))] = name
def nc(ref, pin, name=None): conn(ref, pin, f'NC_{ref}_{pin}', name)

# --- J1 MVS slot: pad "A<k>" touches cart finger A<k> (component side), "B<k>" finger B<k>. Cart 5 V = VCART -----------
CART = {}
for side, table in (('A', CTRG2_A), ('B', CTRG2_B)):
    for k, n in table.items():
        n2 = 'VCART' if n == 'VCC5' else n
        CART[f'{side}{k}'] = n2
        if n2.startswith('NC_'): nc('J1', f'{side}{k}')
        else: conn('J1', f'{side}{k}', n2)

# --- 16-bit transceiver / latch pin tables (identical for 16245, 16T245, 16374: 1A1..1A8, 1B1..1B8, 2A.., 2B..) ---------
X_A1 = [47, 46, 44, 43, 41, 40, 38, 37]; X_B1 = [2, 3, 5, 6, 8, 9, 11, 12]
X_A2 = [36, 35, 33, 32, 30, 29, 27, 26]; X_B2 = [13, 14, 16, 17, 19, 20, 22, 23]
def xcvr(ref, a_nets, b_nets, dir1, dir2, oe1, oe2, dual):
    """16 channels: a_nets/b_nets[0..7] = half 1, [8..15] = half 2. None on the A side = input tied low (unused channel)."""
    for i in range(16):
        pa, pb, h, k = (X_A1[i], X_B1[i], 1, i + 1) if i < 8 else (X_A2[i - 8], X_B2[i - 8], 2, i - 7)
        conn(ref, pa, a_nets[i] or 'GND', f'{h}A{k}')
        if b_nets[i]: conn(ref, pb, b_nets[i], f'{h}B{k}')
        else: nc(ref, pb, f'{h}B{k}')
    conn(ref, 1, dir1, '1DIR'); conn(ref, 24, dir2, '2DIR'); conn(ref, 48, oe1, r'~\{1OE\}'); conn(ref, 25, oe2, r'~\{2OE\}')
    if dual:
        for p in (31, 42): conn(ref, p, 'P3V3', 'VCCA')
        for p in (7, 18): conn(ref, p, 'VCART', 'VCCB')
    else:
        for p in (7, 18, 31, 42): conn(ref, p, 'P3V3', 'VCC')
    for p in (4, 10, 15, 21, 28, 34, 39, 45): conn(ref, p, 'GND', 'GND')
X374_D = X_A1 + X_A2; X374_Q = X_B1 + X_B2
def latch(ref, clk, outs):
    for i in range(16):
        h, k = (1, i) if i < 8 else (2, i - 8)
        conn(ref, X374_D[i], f'MD{i}', f'{h}D{k}')
        if outs[i]: conn(ref, X374_Q[i], outs[i], f'{h}Q{k}')
        else: nc(ref, X374_Q[i], f'{h}Q{k}')
    conn(ref, 48, clk, '1CP'); conn(ref, 25, clk, '2CP'); conn(ref, 1, 'GND', r'~\{1OE\}'); conn(ref, 24, 'GND', r'~\{2OE\}')
    for p in (7, 18, 31, 42): conn(ref, p, 'P3V3', 'VCC')
    for p in (4, 10, 15, 21, 28, 34, 39, 45): conn(ref, p, 'GND', 'GND')

MD = [f'MD{i}' for i in range(16)]
# U5: data bus. DIR high = A -> B = programmer drives the cart (write); XDIR is pulled low (read) at reset
xcvr('U5', MD, [f'D{i}' for i in range(16)], 'XDIR', 'XDIR', 'nOE_D', 'nOE_D', dual=False)
# U6: sample buses, one half each, own enables
xcvr('U6', MD, [f'SDRAD{i}' for i in range(8)] + [f'SDPAD{i}' for i in range(8)], 'XDIR', 'XDIR', 'nOE_VA', 'nOE_VB', dual=True)
# U7: strobes, GPIO16-30, always A -> B
STROBES = ['RW', 'nAS', 'nROMOE', 'nROMOEU', 'nROMOEL', 'nPORTOEU', 'nPORTOEL', 'nPORTWEU', 'nPORTWEL', 'nPORTADRS',
           'SDRMPX', 'nSDROE', 'SDPMPX', 'nSDPOE', 'CLK68K']
xcvr('U7', [f'G_{s}' for s in STROBES] + [None], STROBES + [None], 'P3V3', 'P3V3', 'nOE_OUT', 'nOE_OUT', dual=True)
# U10 -> U8: A1-A16
LAT1 = [f'A{i}' for i in range(1, 17)]
latch('U10', 'LCLK1', [f'L_{n}' for n in LAT1])
xcvr('U8', [f'L_{n}' for n in LAT1], LAT1, 'P3V3', 'P3V3', 'nOE_OUT', 'nOE_OUT', dual=True)
# U11 -> U9: everything else the programmer drives
LAT2 = ['A17', 'A18', 'A19', 'SDRA8', 'SDRA9', 'SDRA20', 'SDRA21', 'SDRA22', 'SDRA23', 'SDPA8', 'SDPA9', 'SDPA10', 'SDPA11', 'nRESET', 'CLK4M', 'nSLOTCS']
latch('U11', 'LCLK2', [f'L_{n}' for n in LAT2])
xcvr('U9', [f'L_{n}' for n in LAT2], LAT2, 'P3V3', 'P3V3', 'nOE_OUT', 'nOE_OUT', dual=True)
CART_INPUTS = ['nROMWAIT', 'nPWAIT0', 'nPWAIT1', 'nPDTACK']

# --- U1 WeAct RP2350B core board: pad name = what the module's header carries (WeAct drawing, top view) ----------------------
# top double row (outer, then inner, left to right): G G 3V3 RUN 46 44 .. 26 | G EN 3V3 47 45 .. 25
# bottom double row (inner, then outer):            5V G 0 2 .. 24         | VBUS G REF 1 3 .. 23
MODULE_ROWS = {
    'top_outer':    ['GND', 'GND', '3V3', 'RUN'] + [f'GP{g}' for g in range(46, 25, -2)],
    'top_inner':    ['GND', 'EN', '3V3'] + [f'GP{g}' for g in range(47, 24, -2)],
    'bottom_inner': ['5V', 'GND', 'GP0'] + [f'GP{g}' for g in range(2, 25, 2)],
    'bottom_outer': ['VBUS', 'GND', 'REF'] + [f'GP{g}' for g in range(1, 24, 2)],
}
MODULE_PADS = {f'{row[0].upper()}{"O" if "outer" in row else "I"}{i + 1}': name for row, names in MODULE_ROWS.items() for i, name in enumerate(names)}
GPIO_NET = {**{i: f'MD{i}' for i in range(16)}, **{26 + i: f'G_{s}' for i, s in enumerate(STROBES)},
            **{16 + i: f'S_{s}' for i, s in enumerate(CART_INPUTS)},
            20: 'XDIR', 21: 'nOE_D', 22: 'nOE_VA', 24: 'nOE_VB', 41: 'nOE_OUT', 42: 'LCLK1', 43: 'LCLK2',
            44: 'VCART_EN', 45: 'nVCART_FAULT', 46: 'VCART_SENSE', 47: 'GPIO47'}
CTRL = {n: g for g, n in GPIO_NET.items() if not n.startswith(('MD', 'G_', 'S_'))}      # name -> GPIO, used by the simulation
MODULE_OWN = {23: 'KEY (button to GND, 5.1k pull-up on the module)', 25: 'LED (5.1k + LED on the module)'}
for pad, name in MODULE_PADS.items():
    if name.startswith('GP'):
        g = int(name[2:])
        if g in GPIO_NET: conn('U1', pad, GPIO_NET[g])
        else: nc('U1', pad)
    elif name == 'GND': conn('U1', pad, 'GND')
    elif name == '3V3': conn('U1', pad, 'P3V3')                 # module regulator output feeds our 3.3 V logic
    elif name == 'VBUS': conn('U1', pad, 'VBUS')                # USB 5 V, straight from the module's USB-C, into the cart switch
    else: nc('U1', pad)                                         # 5V (after the module's power path), EN, RUN, REF

# --- cart power: TPS2553 from the module's VBUS --------------------------------------------------------------------------------
conn('U4', 1, 'VBUS', 'IN'); conn('U4', 2, 'GND', 'GND'); conn('U4', 3, 'VCART_EN', 'EN'); conn('U4', 4, 'nVCART_FAULT', '/FAULT')
conn('U4', 5, 'ILIM', 'ILIM'); conn('U4', 6, 'VCART', 'OUT')
conn('LED1', 1, 'VCART', 'A'); conn('LED1', 2, 'LED1_K', 'K')

TPS = ['GND', 'P3V3', 'VCART', 'VBUS', 'GPIO47']
for i, n in enumerate(TPS, 1):
    conn(f'TP{i}', 1, n); PARTS[f'TP{i}'] = dict(lcsc=None, symbol=None, footprint='TP_PTH_1.0', value=n, desc=f'test point {n}')
for i in range(1, 5):
    PARTS[f'MH{i}'] = dict(lcsc=None, symbol=None, footprint='MH_M3', value='M3', desc='mounting hole, 3.2 mm NPTH')

# --- passives ----------------------------------------------------------------------------------------------------------------
RC = []
def R(v, a, b, owner=None): RC.append((f'R{len([x for x in RC if x[1] == "R"]) + 1}', 'R', v, a, b, owner))
def C(v, a, b, owner=None): RC.append((f'C{len([x for x in RC if x[1] == "C"]) + 1}', 'C', v, a, b, owner))
for n in ('nOE_D', 'nOE_VA', 'nOE_VB', 'nOE_OUT'): R('10k', n, 'P3V3', 'U1')     # every cart-side output off until firmware says so
R('10k', 'XDIR', 'GND', 'U1'); R('10k', 'VCART_EN', 'GND', 'U4'); R('10k', 'nVCART_FAULT', 'P3V3', 'U4')
R('33k', 'ILIM', 'GND', 'U4')                                                     # TPS2553 table 2 / IOSnom = 23950 / 33^0.977 = 0.79 A
R('10k', 'VCART', 'VCART_SENSE', 'U1'); R('10k', 'VCART_SENSE', 'GND', 'U1')       # 5 V -> 2.5 V on ADC4
for s in CART_INPUTS: R('1k', s, f'S_{s}', 'U1')
R('1k', 'LED1_K', 'GND', 'LED1')
C('10u', 'VBUS', 'GND', 'U4'); C('100n', 'VBUS', 'GND', 'U4'); C('10u', 'VCART', 'GND', 'U4'); C('10u', 'VCART', 'GND', 'J1'); C('10u', 'P3V3', 'GND', 'U1')
DECOUPLE = {'U5': 2, 'U10': 2, 'U11': 2}
for ref, n in DECOUPLE.items():
    for _ in range(n): C('100n', 'P3V3', 'GND', ref)
for ref in ('U6', 'U7', 'U8', 'U9'): C('100n', 'P3V3', 'GND', ref); C('100n', 'VCART', 'GND', ref)   # VCCA and VCCB
OWNER = {}
for ref, kind, v, a, b, owner in RC:
    conn(ref, 1, a); conn(ref, 2, b); OWNER[ref] = owner
    PARTS[ref] = dict(lcsc=PASSIVE[v][0], symbol=None, footprint=PASSIVE[v][1], value=v, desc=f'{kind} {v} {a}-{b}')

# ---------------------------------------------------------------------------------------------------------------------------
def symbol_pins():
    sym = {}
    for path in (os.path.join(HERE, 'lib', 'progr.kicad_sym'), os.path.join(HERE, '..', 'pboard', 'lib', 'pboard.kicad_sym')):
        src = open(path).read(); stack, top = [], None
        for m in re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', src):
            t = m.group(0)
            if t == '(': stack.append([])
            elif t == ')':
                node = stack.pop()
                if node and node[0] == 'pin':
                    nm = next((x[1].strip('"') for x in node if isinstance(x, list) and x and x[0] == 'name'), '?')
                    num = next((x[1].strip('"') for x in node if isinstance(x, list) and x and x[0] == 'number'), '?')
                    sym.setdefault(top, {})[num] = nm
                if stack: stack[-1].append(node)
            else:
                if stack: stack[-1].append(t)
                if len(stack) == 2 and stack[-1] and stack[-1][0] == 'symbol' and len(stack[-1]) == 2: top = t.strip('"')
    return sym

# what the PROG board needs from a programmer (PROGRAMMING.md section 4): every net it drives must be driven here
PROGRAMMER_DRIVES = set(STROBES) | set(LAT1) | set(LAT2)
BIDIR = {f'D{i}' for i in range(16)} | {f'SDRAD{i}' for i in range(8)} | {f'SDPAD{i}' for i in range(8)}

def check():
    problems = []
    pins = defaultdict(list)
    for net, lst in NETS.items():
        for ref, p in lst: pins[(ref, p)].append(net)
    for k, v in pins.items():
        if len(v) > 1: problems.append(f'pin {k} on several nets {v}')
    sym = symbol_pins()
    for ref, pt in PARTS.items():
        if not pt['symbol']: continue
        spins = sym.get(pt['symbol'])
        if not spins: problems.append(f'{ref}: symbol {pt["symbol"]} not in library'); continue
        used = {p for (r, p) in pins if r == ref}
        if set(spins) - used: problems.append(f'{ref}: symbol pins not connected/NC: {sorted(set(spins) - used)}')
        if used - set(spins): problems.append(f'{ref}: pins not in symbol: {sorted(used - set(spins))}')
        for (r, p), pat in EXPECT.items():
            if r == ref and not re.fullmatch(pat, spins.get(p, '?'), re.I):
                problems.append(f'{ref} pin {p}: expected {pat!r}, symbol says {spins.get(p)!r}')
    for net, lst in NETS.items():
        if net.startswith('NC_'):
            if len(lst) > 1: problems.append(f'NC net {net} shared: {lst}')
            continue
        if len(lst) < 2 and lst[0][0] != 'J1': problems.append(f'net {net} has one pin: {lst}')
    # 1. the slot carries exactly the PROG board's finger table (imported, so this guards the import itself)
    for k, n in CTRG2_A.items():
        if not n.startswith('NC_') and CART[f'A{k}'] != ('VCART' if n == 'VCC5' else n): problems.append(f'slot A{k} != cart A{k}')
    # 2. a cart inserted backwards (A<k> lands on B<61-k>) never puts 5 V on ground or ground on 5 V
    for k in range(1, 61):
        for s, o in (('A', 'B'), ('B', 'A')):
            a, b = CART[f'{s}{k}'], CART[f'{o}{61 - k}']
            if {a, b} == {'VCART', 'GND'}: problems.append(f'reversed insertion shorts: {s}{k} {a} onto {o}{61 - k} {b}')
    # 3. every line the PROG board expects the console to drive is driven by a cart-side output here
    pb_inputs = {n for n in list(CTRG2_A.values()) + list(CTRG2_B.values()) if not n.startswith('NC_') and n not in ('GND', 'VCC5')}
    out_b = {n for ref in ('U7', 'U8', 'U9') for n, lst in NETS.items() for r, p in lst if r == ref and int(p) in X_B1 + X_B2}
    io_b = {n for ref in ('U5', 'U6') for n, lst in NETS.items() for r, p in lst if r == ref and int(p) in X_B1 + X_B2}
    for n in sorted(pb_inputs):
        if n in CART_INPUTS:
            if not any(r == 'U1' for r, _ in NETS[f'S_{n}']): problems.append(f'cart output {n} not readable')
        elif n in BIDIR:
            if n not in io_b: problems.append(f'bidirectional {n} has no transceiver')
        elif n not in out_b: problems.append(f'cart input {n} not driven by the programmer')
    # 4. nothing cart-side (5 V) touches an MCU pin except the four FT inputs through 1k
    cart_nets = {n for n in CART.values() if n not in ('GND', 'VCART') and not n.startswith('NC_')}
    for n in cart_nets:
        if any(r == 'U1' for r, _ in NETS[n]): problems.append(f'cart net {n} wired straight to the MCU')
    for g, n in GPIO_NET.items():
        if n.startswith('S_') and not g <= 39: problems.append(f'{n} on a non-5V-tolerant GPIO{g}')
        if g in MODULE_OWN: problems.append(f'GPIO{g} is the module\'s {MODULE_OWN[g]}')
    strobe_g = sorted(g for g, n in GPIO_NET.items() if n.startswith('G_'))
    if strobe_g != list(range(strobe_g[0], strobe_g[0] + 15)): problems.append('strobes not on 15 contiguous GPIOs (PIO)')
    if sorted(g for g, n in GPIO_NET.items() if n.startswith('MD')) != list(range(16)): problems.append('MD0-15 not on GPIO0-15')
    if not 40 <= CTRL['VCART_SENSE'] <= 47: problems.append('VCART_SENSE not on an ADC pin')
    if sorted(MODULE_PADS.values()).count('GND') != 5 or len(MODULE_PADS) != 60: problems.append('module pad table is not 60 pads / 5 GND (WeAct drawing)')
    if {int(v[2:]) for v in MODULE_PADS.values() if v.startswith('GP')} != set(range(48)): problems.append('module pad table does not cover GP0-47 once each')
    # 5. every 5 V-side supply of a cart driver is the switched cart rail: an unpowered cart is never driven (TI VCC isolation)
    for ref, pt in PARTS.items():
        if pt['value'] == 'SN74LVC16T245':
            for p in ('7', '18'):
                if next(n for n, lst in NETS.items() if (ref, p) in lst) != 'VCART': problems.append(f'{ref} VCCB pin {p} not on VCART')
    # 6. output-enable pins of every cart-side driver are pulled to the disabled state
    for n in ('nOE_D', 'nOE_VA', 'nOE_VB', 'nOE_OUT'):
        if not any(PARTS[r]['value'] == '10k' and any(rr == r for rr, _ in NETS['P3V3']) for r, _ in NETS[n] if r.startswith('R')):
            problems.append(f'{n} has no pull-up')
    return problems

def unique_parts():
    seen = {}
    for p in PARTS.values():
        if p["lcsc"]: seen.setdefault(p["lcsc"], p["value"])
    return sorted(seen.items())

if __name__ == '__main__':
    pr = check()
    for p in pr: print('PROBLEM:', p)
    up = unique_parts()
    print(f'{len(PARTS)} parts, {len([n for n in NETS if not n.startswith("NC_")])} nets, {len(pr)} problems')
    print(f'{len(up)} unique LCSC parts: ' + ', '.join(v for _, v in up))
    sys.exit(1 if pr else 0)
