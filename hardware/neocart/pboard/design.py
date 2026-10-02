#!/usr/bin/env python3
"""NeoCart P board v2 - declarative netlist (single source of truth).

PROG board (CTRG2) flash cart, 2 layers, full diag-cart outline, HASL fingers:
- P-ROM: one S29GL064N (8 MB, word mode). P1 sits at MB 7, P2 bank n at MB n (n = 0..6): flash A19..A21 = BANKi OR /PORTADRS.
- ADPCM-A and ADPCM-B share ONE S29GL128P (16 MB, byte mode), like SNK's PCM chip: both 24-bit YM2610 addresses are captured
  by LVC16374 edge registers whose tri-state outputs share the flash address bus. /SDROE and /SDPOE fall together (neogeodev
  wiki, "YM2610 ADPCM bus"): ADPCM-B owns the flash during its 250 ns /SDPOE window, ADPCM-A for the rest of its 1.5 us /SDROE
  window (A latches on the rising edge). Break-before-make: B registers on = /SDPOE OR d, A registers on = NOT(/SDPOE AND d),
  d = /SDPOE delayed by two inverters.
- Every edge pin that reaches a flash pin goes through a 3.3 V LVC output; strobes go straight into 5 V-tolerant LVC/AHC inputs.
- Programmable through the gold fingers (the programmer acts as the console) when JP1 pulls /PROG low:
  /PORTWEU -> P flash /WE, /ROMOEU -> V flash /WE (written through the ADPCM-A path), R/W -> ADPCM-A buffer direction.
  With JP1 parked (PLAY) every flash /WE is held high and the sample buffers only drive flash -> bus.

Pin numbers were checked against the manufacturer datasheets in ./datasheets (S29GL064N Figure 1 models 03/04,
S29GL128P Figure 4.3 56-pin TSOP, TI SN74LVC16245A/16374A, Nexperia 74LVC8T245 table 2, 74LVC32A, TI SN74AHC273,
SN74LVC08A / Nexperia 74LVC08A, SN74LVC04A, Nexperia 74LVC16245A). check() also compares every pin name against the easyeda2kicad symbol.
"""
import os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------------------------------------------
# Parts: ref -> (LCSC, symbol name in lib/pboard.kicad_sym, footprint in lib/pboard.pretty, value, description)
# ---------------------------------------------------------------------------------------------------------------
PARTS = {}
def part(ref, lcsc, symbol, footprint, value, desc):
    PARTS[ref] = dict(lcsc=lcsc, symbol=symbol, footprint=footprint, value=value, desc=desc)

part('U1', 'C117907', 'S29GL064N90TFI040', 'TSOP-48_L12.0-W18.4-P0.50-LS20.0-BL', 'S29GL064N', '64 Mbit NOR, 90 ns - P-ROM, word mode')
part('U2', 'C914939', 'S29GL128P11TFIV10', 'TSOP-56_L18.4-W14.0-P0.50-LS20.0-TL', 'S29GL128P', '128 Mbit NOR, 110 ns - ADPCM-A + ADPCM-B, byte mode')
part('U4', 'C548160', 'SN74LVC16245ADGGR', 'TSSOP-48_L12.5-W6.1-P0.50-LS8.1-BL', '74LVC16245A', '68K data transceiver, DIR = R/W (Nexperia 74LVC16245ADGG: TI pinout, identical land pattern)')
part('U5', 'C548160', 'SN74LVC16245ADGGR', 'TSSOP-48_L12.5-W6.1-P0.50-LS8.1-BL', '74LVC16245A', '68K A1-A16 buffer, DIR tied A->B (Nexperia 74LVC16245ADGG)')
for ref, d in [('U6', 'ADPCM-A bits 0-9 (SDRMPX rising)'), ('U7', 'ADPCM-A bits 10-23 (SDRMPX falling)'),
               ('U8', 'ADPCM-B bits 0-11 (SDPMPX rising)'), ('U9', 'ADPCM-B bits 12-23 (SDPMPX falling)')]:
    part(ref, 'C6074', '74LVC16374ADGG,118', 'TSSOP-48_L12.6-W6.2-P0.50-LS8.1-BL', '74LVC16374A', f'16-bit edge register - {d}')
part('U10', 'C458788', '74LVC8T245PW,118', 'TSSOP-24_L7.8-W4.4-P0.65-LS6.4-BL', '74LVC8T245', 'ADPCM-A data, 3.3 V flash <-> 5 V bus')
part('U11', 'C458788', '74LVC8T245PW,118', 'TSSOP-24_L7.8-W4.4-P0.65-LS6.4-BL', '74LVC8T245', 'ADPCM-B data, 3.3 V flash <-> 5 V bus')
part('U12', 'C2877489', 'SN74AHC273DBR', 'SSOP-20_L7.5-W5.2-P0.65-LS8.0-BL', 'SN74AHC273', 'P2 bank latch (3 bits) with clear')
part('U13', 'C6053', 'SN74LVC08APWR', 'TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL', '74LVC08A', 'quad AND - P output / transceiver enables')
part('U14', 'C6053', 'SN74LVC08APWR', 'TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL', '74LVC08A', 'quad AND - V flash /OE, bus-owner select, buffer enables')
part('U15', 'C6087', '74LVC32APW,118', 'TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL', '74LVC32A', 'quad OR - write strobes gated by /PROG, sample direction')
part('U16', 'C6087', '74LVC32APW,118', 'TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL', '74LVC32A', 'quad OR - bank map, A17 buffer')
part('U17', 'C6087', '74LVC32APW,118', 'TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL', '74LVC32A', 'quad OR - A18/A19 buffers, ADPCM-B register enable')
part('U18', 'C352968', 'SN74LVC04APWR', 'TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL', 'SN74LVC04A', 'hex inverter - MPX falling edges, /SDPOE delay, ADPCM-A register enable')
part('U19', 'C6186', 'AMS1117-3.3', 'SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR', 'AMS1117-3.3', '3.3 V LDO from slot 5 V')
part('JP1', 'C2894926', 'PZ254-1-03-Z-8.5', 'HDR-TH_03P-P2.54-V-M', 'MODE', '1x3 header, hand-soldered: /PROG | GND | park. Jumper 1-2 = PROGRAM, 2-3 = PLAY')

# passives: value -> (LCSC, footprint). One pull value, one decoupling value, one bulk value.
PASSIVE = {'100n': ('C14663', 'C0603'), '10u': ('C15850', 'C0805'), '10k': ('C25804', 'R0603')}

# ---------------------------------------------------------------------------------------------------------------
# Nets. conn(ref, pin_number, net, expected_pin_name)
# ---------------------------------------------------------------------------------------------------------------
NETS = defaultdict(list)        # net -> [(ref, pin)]
EXPECT = {}                     # (ref, pin) -> expected symbol pin name (regex, case-insensitive)
def conn(ref, pin, net, name=None):
    NETS[net].append((ref, str(pin)))
    if name: EXPECT[(ref, str(pin))] = name
def nc(ref, pin, name=None): conn(ref, pin, f'NC_{ref}_{pin}', name)

# --- CTRG2 gold fingers (proven pinout from the blank board): J1 = B side, J2 = A side ---------------------------
CTRG2_A = {**{p: 'GND' for p in (1, 2, 3, 4, 57, 58, 59, 60)}, **{5 + i: f'D{i}' for i in range(16)},
           21: 'RW', 22: 'nAS', 23: 'nROMOEU', 24: 'nROMOEL', 25: 'nPORTOEU', 26: 'nPORTOEL', 27: 'nPORTWEU', 28: 'nPORTWEL',
           **{p: 'VCC5' for p in (29, 30, 31, 32)}, 33: 'nPORTADRS', **{p: f'NC_A{p}' for p in range(34, 42)}, 42: 'nSLOTCS',
           43: 'SDPA8', 44: 'SDPA9', 45: 'SDPA10', 46: 'SDPA11', 47: 'SDPMPX', 48: 'nSDPOE',
           49: 'SDRA8', 50: 'SDRA9', 51: 'SDRA20', 52: 'SDRA21', 53: 'SDRA22', 54: 'SDRA23', 55: 'SDRMPX', 56: 'nSDROE'}
CTRG2_B = {**{p: 'GND' for p in (1, 2, 3, 4, 57, 58, 59, 60)}, **{5 + i: f'A{i + 1}' for i in range(19)}, 24: 'CLK68K',
           25: 'nROMWAIT', 26: 'nPWAIT0', 27: 'nPWAIT1', 28: 'nPDTACK', **{p: 'VCC5' for p in (29, 30, 31, 32)},
           33: 'nROMOE', 34: 'CLK4M', 35: 'nRESET', **{p: f'NC_B{p}' for p in range(36, 41)},
           **{41 + i: f'SDPAD{i}' for i in range(8)}, **{49 + i: f'SDRAD{i}' for i in range(8)}}
for p, n in CTRG2_A.items(): conn('J2', p, n)
for p, n in CTRG2_B.items(): conn('J1', p, n)

# --- Power -------------------------------------------------------------------------------------------------------
conn('U19', 3, 'VCC5', 'VIN'); conn('U19', 2, 'P3V3', 'VOUT'); conn('U19', 4, 'P3V3', 'VOUT'); conn('U19', 1, 'GND', 'GND')

# --- U1 S29GL064N P-ROM (TSOP-48, word mode) -----------------------------------------------------------------------
GL064_ADDR = {0: 25, 1: 24, 2: 23, 3: 22, 4: 21, 5: 20, 6: 19, 7: 18, 8: 8, 9: 7, 10: 6, 11: 5, 12: 4, 13: 3, 14: 2, 15: 1,
              16: 48, 17: 17, 18: 16, 19: 9, 20: 10, 21: 13}
GL064_DQ = {0: 29, 1: 31, 2: 33, 3: 35, 4: 38, 5: 40, 6: 42, 7: 44, 8: 30, 9: 32, 10: 34, 11: 36, 12: 39, 13: 41, 14: 43, 15: 45}
for a, p in GL064_ADDR.items(): conn('U1', p, f'FA{a}', f'A{a}')
for d, p in GL064_DQ.items(): conn('U1', p, f'FD{d}', f'Q{d}' if d < 15 else r'Q15/A-1')
conn('U1', 26, 'GND', r'~\{CE\}'); conn('U1', 28, 'nP_OE', r'~\{OE\}'); conn('U1', 11, 'nP_WE', r'~\{WE\}'); conn('U1', 47, 'P3V3', r'~\{BYTE\}')
conn('U1', 37, 'P3V3', 'VCC'); conn('U1', 27, 'GND', 'VSS'); conn('U1', 46, 'GND', r'GND|VSS')
conn('U1', 12, 'P3V3', r'~\{RESET\}'); conn('U1', 14, 'P3V3', r'~\{WP\}/ACC'); nc('U1', 15, r'RY/~\{BY\}')

# --- U2 S29GL128P V-ROM shared by both buses (TSOP-56, byte mode): YM2610 bit 0 -> DQ15/A-1, bit k -> A(k-1) -------------------------
GL128_ADDR = {0: 31, 1: 26, 2: 25, 3: 24, 4: 23, 5: 22, 6: 21, 7: 20, 8: 10, 9: 9, 10: 8, 11: 7, 12: 6, 13: 5, 14: 4, 15: 3,
              16: 54, 17: 19, 18: 18, 19: 11, 20: 12, 21: 15, 22: 2}
GL128_DQ = {0: 35, 1: 37, 2: 39, 3: 41, 4: 44, 5: 46, 6: 48, 7: 50, 8: 36, 9: 38, 10: 40, 11: 42, 12: 45, 13: 47, 14: 49}
def vflash(ref, pfx):
    conn(ref, 51, f'{pfx}_ADR0', r'DQ15/A-1')
    for k in range(1, 24): conn(ref, GL128_ADDR[k - 1], f'{pfx}_ADR{k}', f'A{k - 1}')
    for d in range(8): conn(ref, GL128_DQ[d], f'{pfx}_DQ{d}', f'DQ{d}')
    for d in range(8, 15): nc(ref, GL128_DQ[d], f'DQ{d}')
    conn(ref, 32, 'GND', r'~\{CE\}'); conn(ref, 34, f'n{pfx}_OE', r'~\{OE\}'); conn(ref, 13, f'n{pfx}_WE', r'~\{WE\}'); conn(ref, 53, 'GND', r'~\{BYTE\}')
    conn(ref, 43, 'P3V3', 'VCC'); conn(ref, 29, 'P3V3', 'VIO'); conn(ref, 33, 'GND', 'VSS'); conn(ref, 52, 'GND', 'VSS')
    conn(ref, 14, 'P3V3', r'~\{RESET\}'); conn(ref, 16, 'P3V3', r'~\{WP\}/ACC'); nc(ref, 17, r'RY/~\{BY\}')
    for p in (1, 27, 28, 30, 55, 56): nc(ref, p, 'NC')
vflash('U2', 'V')

# --- LVC16245 pin map ------------------------------------------------------------------------------------------------
X245_A = {1: [47, 46, 44, 43, 41, 40, 38, 37], 2: [36, 35, 33, 32, 30, 29, 27, 26]}
X245_B = {1: [2, 3, 5, 6, 8, 9, 11, 12], 2: [13, 14, 16, 17, 19, 20, 22, 23]}
def x245_power(ref):
    for p in (7, 18, 31, 42): conn(ref, p, 'P3V3', 'VCC')
    for p in (4, 10, 15, 21, 28, 34, 39, 45): conn(ref, p, 'GND', 'GND')
# U4: A = flash data FD (3.3 V), B = 68K bus D (5 V side). DIR = R/W: read (high) = A -> B.
# Channel k carries bit 15-k: the fingers run D15..D0 left to right, the chip's B row runs 1B1..2B8 left to right at rot 0,
# so reversing the channel order keeps all sixteen traces parallel (channels of a 16245 are interchangeable).
for k in range(16):
    h, b = (1, k) if k < 8 else (2, k - 8); i = 15 - k
    conn('U4', X245_A[h][b], f'FD{i}', f'{h}A{b + 1}'); conn('U4', X245_B[h][b], f'D{i}', f'{h}B{b + 1}')
conn('U4', 1, 'RW', '1DIR'); conn('U4', 24, 'RW', '2DIR'); conn('U4', 48, 'nXCVR_EN', r'~\{1OE\}'); conn('U4', 25, 'nXCVR_EN', r'~\{2OE\}')
x245_power('U4')
# U5: A = edge A1..A16 (5 V tolerant inputs), B = FA0..FA15 (3.3 V). DIR high, always enabled
for i in range(16):
    h, b = (1, i) if i < 8 else (2, i - 8)
    conn('U5', X245_A[h][b], f'A{i + 1}', f'{h}A{b + 1}'); conn('U5', X245_B[h][b], f'FA{i}', f'{h}B{b + 1}')
conn('U5', 1, 'P3V3', '1DIR'); conn('U5', 24, 'P3V3', '2DIR'); conn('U5', 48, 'GND', r'~\{1OE\}'); conn('U5', 25, 'GND', r'~\{2OE\}')
x245_power('U5')

# --- LVC16374 edge registers (CP inputs 5 V tolerant, taken straight from the fingers) --------------------------------
X374_D = {1: [47, 46, 44, 43, 41, 40, 38, 37], 2: [36, 35, 33, 32, 30, 29, 27, 26]}
X374_Q = {1: [2, 3, 5, 6, 8, 9, 11, 12], 2: [13, 14, 16, 17, 19, 20, 22, 23]}
def reg374(ref, cp_net, inputs, outputs, oe_net='GND'):
    """inputs/outputs: 16 net names (half 1 bits 0-7, then half 2); None = grounded input / NC output"""
    for i in range(16):
        h, b = (1, i) if i < 8 else (2, i - 8)
        conn(ref, X374_D[h][b], inputs[i] or 'GND', f'{h}D{b}')
        if outputs[i]: conn(ref, X374_Q[h][b], outputs[i], f'{h}Q{b}')
        else: nc(ref, X374_Q[h][b], f'{h}Q{b}')
    conn(ref, 48, cp_net, '1CP'); conn(ref, 25, cp_net, '2CP')
    conn(ref, 1, oe_net, r'~\{1OE\}'); conn(ref, 24, oe_net, r'~\{2OE\}')
    x245_power(ref)                      # same VCC/GND pin set as the 16245
adpcm_a_lo = [f'SDRAD{i}' for i in range(8)] + ['SDRA8', 'SDRA9'] + [None] * 6
adpcm_a_hi = [f'SDRAD{i}' for i in range(8)] + ['SDRA8', 'SDRA9', 'SDRA20', 'SDRA21', 'SDRA22', 'SDRA23'] + [None] * 2
# both register pairs drive the same flash address bus V_ADR0-23; only one pair has its outputs enabled at any time
reg374('U6', 'SDRMPX', adpcm_a_lo, [f'V_ADR{k}' for k in range(0, 10)] + [None] * 6, 'nASEL_OE')
reg374('U7', 'nRMPX', adpcm_a_hi, [f'V_ADR{k}' for k in range(10, 24)] + [None] * 2, 'nASEL_OE')
adpcm_b = [f'SDPAD{i}' for i in range(8)] + [f'SDPA{k}' for k in range(8, 12)] + [None] * 4
reg374('U8', 'SDPMPX', adpcm_b, [f'V_ADR{k}' for k in range(0, 12)] + [None] * 4, 'nBSEL_OE')
reg374('U9', 'nPMPX', adpcm_b, [f'V_ADR{k}' for k in range(12, 24)] + [None] * 4, 'nBSEL_OE')

# --- U10/U11 74LVC8T245: A = flash data V_DQ (VCCA 3.3 V), B = ADPCM bus (VCCB 5 V). DIR high = A -> B (flash to bus) ------
# U10 (ADPCM-A) also carries programming writes (DIR = VDIR); U11 (ADPCM-B) only ever reads (DIR tied high).
for ref, bus, dir_net, oe_net in [('U10', 'SDRAD', 'VDIR', 'nVA_BUFOE'), ('U11', 'SDPAD', 'P3V3', 'nVB_BUFOE')]:
    for i in range(8): conn(ref, 3 + i, f'V_DQ{i}', f'A{i + 1}'); conn(ref, 21 - i, f'{bus}{i}', f'B{i + 1}')
    conn(ref, 1, 'P3V3', 'VCCA'); conn(ref, 23, 'VCC5', 'VCCB'); conn(ref, 24, 'VCC5', 'VCCB')
    conn(ref, 2, dir_net, 'DIR'); conn(ref, 22, oe_net, r'~\{OE\}')
    for p in (11, 12, 13): conn(ref, p, 'GND', 'GND')

# --- U12 AHC273 bank latch: D from the 3.3 V data bus, clocked by the end of a port-zone lower-byte write -------------
conn('U12', 3, 'FD0', '1D'); conn('U12', 2, 'BANK0', '1Q'); conn('U12', 4, 'FD1', '2D'); conn('U12', 5, 'BANK1', '2Q')
conn('U12', 7, 'FD2', '3D'); conn('U12', 6, 'BANK2', '3Q')
for d, q, n in [(8, 9, 4), (13, 12, 5), (14, 15, 6), (17, 16, 7), (18, 19, 8)]:
    conn('U12', d, 'GND', f'{n}D'); nc('U12', q, f'{n}Q')
conn('U12', 11, 'nPORTWEL', 'CLK'); conn('U12', 1, 'nRESET', r'~\{CLR\}'); conn('U12', 20, 'P3V3', 'VCC'); conn('U12', 10, 'GND', 'GND')

# --- Gates: AND/OR share one pinout (1A,1B,1Y = 1,2,3 ...) --------------------------------------------------------------
GATE2 = {1: (1, 2, 3), 2: (4, 5, 6), 3: (9, 10, 8), 4: (12, 13, 11)}
def gate2(ref, g, a, b, y):
    pa, pb, py = GATE2[g]; conn(ref, pa, a, f'{g}A'); conn(ref, pb, b, f'{g}B'); conn(ref, py, y, f'{g}Y')
# U13 AND: active-low "any" combinations for the P side
gate2('U13', 1, 'nPORTOEL', 'nPORTOEU', 'nPORTOE')        # either byte of a port-window read
gate2('U13', 2, 'nROMOE', 'nPORTOE', 'nP_OE')              # P flash /OE: any P read
gate2('U13', 3, 'nP_OE', 'nPORTWEL', 'nXEN1')             # data transceiver: P read, bank write ...
gate2('U13', 4, 'nXEN1', 'nP_WE', 'nXCVR_EN')              # ... or a programming write
# U14 AND: V side
gate2('U14', 1, 'nSDROE', 'nSDPOE', 'nV_OE')               # flash /OE: either bus reading
gate2('U14', 2, 'nSDPOE', 'PDLY', 'nPOE_BOTH')             # high only once /SDPOE and its delayed copy are both high ...
gate2('U14', 3, 'nSDROE', 'nV_WE', 'nVA_BUFOE')            # ADPCM-A buffer: read strobe or programming write
gate2('U14', 4, 'nSDPOE', 'nSDPOE', 'nVB_BUFOE')           # ADPCM-B buffer: 3.3 V copy of /SDPOE
# U15 OR: programming gates (JP1 parked -> /PROG high -> every /WE high, buffers flash -> bus)
gate2('U15', 1, 'nPORTWEU', 'nPROG', 'nP_WE')
gate2('U15', 2, 'nROMOEU', 'nPROG', 'nV_WE')
gate2('U15', 4, 'RW', 'nPROG', 'VDIR')
pa, pb, py = GATE2[3]; conn('U15', pa, 'GND', '3A'); conn('U15', pb, 'GND', '3B'); nc('U15', py, '3Y')   # spare (was the V-B /WE)
# U16 OR: bank map (P1 at MB 7, P2 bank n at MB n) and A17
gate2('U16', 1, 'BANK0', 'nPORTADRS', 'FA19')
gate2('U16', 2, 'BANK1', 'nPORTADRS', 'FA20')
gate2('U16', 3, 'BANK2', 'nPORTADRS', 'FA21')
gate2('U16', 4, 'A17', 'GND', 'FA16')
# U17 OR: A18/A19 buffers (other input grounded), two spare gates with grounded inputs
gate2('U17', 1, 'A18', 'GND', 'FA17')
gate2('U17', 2, 'A19', 'GND', 'FA18')
gate2('U17', 3, 'nSDPOE', 'PDLY', 'nBSEL_OE')              # ADPCM-B registers on only once /SDPOE and d are both low, off at once on the rise
pa, pb, py = GATE2[4]; conn('U17', pa, 'GND', '4A'); conn('U17', pb, 'GND', '4B'); nc('U17', py, '4Y')
for ref in ('U13', 'U14', 'U15', 'U16', 'U17'): conn(ref, 14, 'P3V3', 'VCC'); conn(ref, 7, 'GND', 'GND')
# U18 LVC04: falling-edge clocks for the high-address registers; spare inverters with grounded inputs
INV = {1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (9, 8), 5: (11, 10), 6: (13, 12)}
for g, a, y in [(1, 'SDRMPX', 'nRMPX'), (2, 'SDPMPX', 'nPMPX'), (3, 'nSDPOE', 'SDPOE_I'), (4, 'SDPOE_I', 'PDLY'), (5, 'nPOE_BOTH', 'nASEL_OE')]:
    pa, py = INV[g]; conn('U18', pa, a, f'{g}A'); conn('U18', py, y, f'{g}Y')   # 3-4: d = /SDPOE delayed by two gates; 5: ... A registers on = NOT(/SDPOE AND d)
pa, py = INV[6]; conn('U18', pa, 'GND', '6A'); nc('U18', py, '6Y')
conn('U18', 14, 'P3V3', 'VCC'); conn('U18', 7, 'GND', 'GND')

# --- JP1: /PROG (pin 1) | GND (pin 2) | park (pin 3). Jumper on 1-2 = PROGRAM, on 2-3 = PLAY (stored, never lost) ---
conn('JP1', 1, 'nPROG'); conn('JP1', 2, 'GND'); nc('JP1', 3)

# --- Test points (1.0 mm plated pads, hand use, not assembled) ------------------------------------------------------
TPS = ['GND', 'P3V3', 'VCC5', 'nPROG']    # through-hole pads cost routing space on both layers: power + mode only; logic is probed on chip pins
for i, n in enumerate(TPS, 1):
    conn(f'TP{i}', 1, n); PARTS[f'TP{i}'] = dict(lcsc=None, symbol=None, footprint='TP_PTH_1.0', value=n, desc=f'test point {n}')

# --- Passives ------------------------------------------------------------------------------------------------------------
RC = []
def R(v, a, b, owner=None): RC.append((f'R{len([x for x in RC if x[1] == "R"]) + 1}', 'R', v, a, b, owner))
def C(v, a, b, owner=None): RC.append((f'C{len([x for x in RC if x[1] == "C"]) + 1}', 'C', v, a, b, owner))
R('10k', 'nPROG', 'P3V3', 'JP1')                                              # PLAY unless the jumper grounds it
for n in ('nROMWAIT', 'nPWAIT0', 'nPWAIT1', 'nPDTACK'): R('10k', n, 'VCC5')    # full speed, like every SNK cart
C('10u', 'VCC5', 'GND', 'U19'); C('10u', 'P3V3', 'GND', 'U19'); C('10u', 'P3V3', 'GND', 'U1')
DECOUPLE = {'U1': 1, 'U2': 1, 'U4': 2, 'U5': 2, 'U6': 2, 'U7': 2, 'U8': 2, 'U9': 2, 'U12': 1,
            'U13': 1, 'U14': 1, 'U15': 1, 'U16': 1, 'U17': 1, 'U18': 1}
for ref, n in DECOUPLE.items():
    for _ in range(n): C('100n', 'P3V3', 'GND', ref)
for ref in ('U10', 'U11'): C('100n', 'P3V3', 'GND', ref); C('100n', 'VCC5', 'GND', ref)   # VCCA and VCCB
OWNER = {}
for ref, kind, v, a, b, owner in RC:
    conn(ref, 1, a); conn(ref, 2, b); OWNER[ref] = owner
    PARTS[ref] = dict(lcsc=PASSIVE[v][0], symbol=None, footprint=PASSIVE[v][1], value=v, desc=f'{kind} {v} {a}-{b}')

# ---------------------------------------------------------------------------------------------------------------
# Electrical rules beyond the pin list
FLASH = ('U1', 'U2')
FIVE_VOLT_NETS = {n for n in list(CTRG2_A.values()) + list(CTRG2_B.values()) if not n.startswith('NC_') and n != 'GND'}

def symbol_pins():
    src = open(os.path.join(HERE, 'lib', 'pboard.kicad_sym')).read()
    sym, stack, top = {}, [], None
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
        if set(spins) - used: problems.append(f'{ref}: symbol pins not connected/NC: {sorted(set(spins) - used, key=lambda s: (len(s), s))}')
        if used - set(spins): problems.append(f'{ref}: pins not in symbol: {sorted(used - set(spins))}')
        for (r, p), pat in EXPECT.items():
            if r == ref and not re.fullmatch(pat, spins.get(p, '?'), re.I):
                problems.append(f'{ref} pin {p}: expected {pat!r}, symbol says {spins.get(p)!r}')
    for net, lst in NETS.items():
        if net.startswith('NC_') and len(lst) == 1: continue
        if len(lst) < 2 and not (len(lst) == 1 and lst[0][0] in ('J1', 'J2')): problems.append(f'net {net} has one pin: {lst}')   # a finger the cart does not use is fine
        if net.startswith('NC_') and len(lst) > 1: problems.append(f'NC net {net} shared: {lst}')
    # no flash pin may touch a finger net (5 V) or the 5 V rail
    for net, lst in NETS.items():
        if net in FIVE_VOLT_NETS or net == 'VCC5':
            bad = [(r, p) for r, p in lst if r in FLASH]
            if bad: problems.append(f'5 V net {net} reaches flash pins {bad}')
    # nobody drives a finger net except the data transceiver B side, the sample buffers B side and pull resistors
    allowed = {'U4', 'U10', 'U11', 'J1', 'J2'}
    return problems

def unique_parts():
    return sorted({(p['lcsc'], p['value']) for p in PARTS.values() if p['lcsc']})

if __name__ == '__main__':
    pr = check()
    for p in pr: print('PROBLEM:', p)
    n_nets = len([n for n in NETS if not n.startswith('NC_')])
    up = unique_parts()
    smt = [u for u in up if u[0] != 'C2894926']
    print(f'{len(PARTS)} parts, {n_nets} nets, {sum(len(v) for v in NETS.values())} pin connections, {len(pr)} problems')
    print(f'{len(up)} unique LCSC parts ({len(smt)} machine-placed): ' + ', '.join(f'{v}' for _, v in up))
    sys.exit(1 if pr else 0)
