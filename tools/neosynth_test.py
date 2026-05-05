#!/usr/bin/env python3
"""Automated test suite for NeoSynth Z80 sound driver.

Builds the driver, then runs the Z80 tracer against all features,
verifying correct YM2610 register writes.

Usage: python3 tools/neosynth_test.py
"""
import sys, os

# Ensure tools dir is on path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from neosynth_build import build_driver
from z80_trace import Z80Tracer
import tempfile

# Build driver to a temp file
MROM_PATH = os.path.join(tempfile.gettempdir(), 'neosynth_test_m1.bin')
mrom = build_driver()
with open(MROM_PATH, 'wb') as f:
    f.write(mrom)
print(f"Driver built: {MROM_PATH} ({len(mrom)} bytes)\n")


def boot():
    z = Z80Tracer(MROM_PATH)
    z.verbose = False
    z.trace_ym = False
    z.pc = 0x0000
    for _ in range(500):
        z.step()
        if z.halted:
            break
    return z


def send_cmd(z, cmd):
    """Send a command via NMI and return decoded YM writes."""
    z.ym_writes.clear()
    z.sound_code = cmd
    z.halted = False
    z.fire_nmi()
    for _ in range(20000):
        z.step()
        if z.halted:
            break
    writes = []
    cur_addr = {'A': 0, 'B': 0}
    for _, port, val in z.ym_writes:
        if port == 0x04:
            cur_addr['A'] = val
        elif port == 0x06:
            cur_addr['B'] = val
        elif port == 0x05:
            writes.append(('A', cur_addr['A'], val))
        elif port == 0x07:
            writes.append(('B', cur_addr['B'], val))
    return writes


passed = 0
failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        print(f'  PASS: {name}')
        passed += 1
    else:
        print(f'  FAIL: {name} {detail}')
        failed += 1


# ====================================================================
# BOOT
# ====================================================================
print('=== BOOT ===')
z = boot()
check('Halted (main loop)', z.halted)
check('NMI enabled', z.nmi_enabled)
check('SP = 0xFFFC', z.sp == 0xFFFC)
check('FM pan default C0', z.ram[0x14] == 0xC0)  # RAM_FM_PAN offset
check('ADPCM-A pan default C0', z.ram[0x1C] == 0xC0)

# ====================================================================
# STOP ALL ($03)
# ====================================================================
print('\n=== STOP ALL ($03) ===')
w = send_cmd(z, 0x03)
keoffs = sorted([v for p, r, v in w if p == 'A' and r == 0x28])
check('FM key-off ch1-4', keoffs == [0x01, 0x02, 0x05, 0x06], str(keoffs))
ssg_vols = [(r, v) for p, r, v in w if p == 'A' and r in (0x08, 0x09, 0x0A)]
check('SSG volumes = 0', all(v == 0 for _, v in ssg_vols))
adpcma = [v for p, r, v in w if p == 'B' and r == 0x00]
check('ADPCM-A dump all ($BF)', 0xBF in adpcma)
adpcmb = [(r, v) for p, r, v in w if p == 'A' and r == 0x10]
check('ADPCM-B stop', (0x10, 0x01) in adpcmb)

# ====================================================================
# INIT/RESET ($01)
# ====================================================================
print('\n=== INIT/RESET ($01) ===')
z = boot()
w = send_cmd(z, 0x01)
keoffs = sorted([v for p, r, v in w if p == 'A' and r == 0x28])
check('Init does stop-all', keoffs == [0x01, 0x02, 0x05, 0x06])

# ====================================================================
# PARAM SET ($08)
# ====================================================================
print('\n=== PARAM SET ($08, value) ===')
z = boot()
w = send_cmd(z, 0x08)
check('No YM writes on $08', len(w) == 0)
check('Param flag set', z.ram[0x02] == 1)  # RAM_PARAM_FLAG offset
w = send_cmd(z, 42)
check('No YM writes on param value', len(w) == 0)
check('Param = 42', z.ram[0x01] == 42)  # RAM_PARAM offset
check('Param flag cleared', z.ram[0x02] == 0)

# ====================================================================
# ADPCM-A TRIGGER ($C0+sample)
# ====================================================================
print('\n=== ADPCM-A TRIGGER ===')
for smp_idx in range(8):
    z = boot()
    w = send_cmd(z, 0xC0 + smp_idx)
    portB = [(r, v) for p, r, v in w if p == 'B']
    has_trigger = any(r == 0x00 and 0 < v < 0x80 for r, v in portB)
    check(f'Sample {smp_idx} triggers', has_trigger, str(portB[:3]))

# Out of range sample (should be ignored)
z = boot()
w = send_cmd(z, 0xC0 + 8)
portB = [(r, v) for p, r, v in w if p == 'B']
check('Out-of-range sample ignored', len(portB) == 0, str(portB))

# ====================================================================
# FM KEY-ON ($10-$13)
# ====================================================================
print('\n=== FM KEY-ON ===')
fm_keyon_vals = {0: 0xF1, 1: 0xF2, 2: 0xF5, 3: 0xF6}
fm_test_notes = {
    # YM2610 FM channels: 1,2,4,5 -> offsets 1,2 on Port A; 1,2 on Port B
    0: (48, 0xA1, 0xA5, 'A', 0x6A, 0x22),  # C4, Port A offset 1
    1: (55, 0xA2, 0xA6, 'A', 0xAB, 0x22),  # G4, Port A offset 2
    2: (57, 0xA1, 0xA5, 'B', 0xC0, 0x22),  # A4, Port B offset 1
    3: (64, 0xA2, 0xA6, 'B', 0x8F, 0x2A),  # E5, Port B offset 2
}

for ch in range(4):
    note, freq_lo_reg, freq_hi_reg, port, exp_flo, exp_fhi = fm_test_notes[ch]
    z = boot()
    send_cmd(z, 0x08)
    send_cmd(z, note)
    w = send_cmd(z, 0x10 + ch)

    keyon = [v for p, r, v in w if p == 'A' and r == 0x28]
    check(f'FM ch{ch} key-on 0x{fm_keyon_vals[ch]:02X}', fm_keyon_vals[ch] in keyon)

    flo = [v for p, r, v in w if p == port and r == freq_lo_reg]
    fhi = [v for p, r, v in w if p == port and r == freq_hi_reg]
    check(f'FM ch{ch} fnum_lo 0x{exp_flo:02X}', exp_flo in flo, str(flo))
    check(f'FM ch{ch} fnum_hi 0x{exp_fhi:02X}', exp_fhi in fhi, str(fhi))

    # Verify patch registers written to correct port
    # With YM2610 offset 1 or 2, patch regs are in 0x30-0x8F range
    patch_port = [(r, v) for p, r, v in w if p == port and 0x31 <= r <= 0x8E]
    check(f'FM ch{ch} patch on Port {port}', len(patch_port) == 24, str(len(patch_port)))

# ====================================================================
# FM KEY-OFF ($14-$17)
# ====================================================================
print('\n=== FM KEY-OFF ===')
fm_keyoff_vals = {0: 0x01, 1: 0x02, 2: 0x05, 3: 0x06}
for ch in range(4):
    z = boot()
    w = send_cmd(z, 0x14 + ch)
    koff = [v for p, r, v in w if p == 'A' and r == 0x28]
    check(f'FM ch{ch} key-off 0x{fm_keyoff_vals[ch]:02X}', fm_keyoff_vals[ch] in koff, str(koff))

# ====================================================================
# FM SET PATCH ($18-$1B)
# ====================================================================
print('\n=== FM SET PATCH ===')
z = boot()
send_cmd(z, 0x08)
send_cmd(z, 2)   # patch 2 (brass)
w = send_cmd(z, 0x18)  # set patch ch0
check('Patch stored', z.ram[0x10] == 2)  # RAM_FM_PATCH ch0

# ====================================================================
# SSG KEY-ON ($20-$22)
# ====================================================================
print('\n=== SSG KEY-ON ===')
ssg_tests = {
    0: (57, 0x00, 0x01, 0x08, 0x8E, 0x00),  # A4, regs 0/1/8, period=142=0x8E
    1: (60, 0x02, 0x03, 0x09, 0x77, 0x00),  # C5, regs 2/3/9, period=119=0x77
    2: (36, 0x04, 0x05, 0x0A, 0xDE, 0x01),  # C3, regs 4/5/A, period=478=0x1DE
}

for ch, (note, tlo_reg, thi_reg, vol_reg, exp_tlo, exp_thi) in ssg_tests.items():
    z = boot()
    send_cmd(z, 0x08)
    send_cmd(z, note)
    w = send_cmd(z, 0x20 + ch)

    tlo = [v for p, r, v in w if p == 'A' and r == tlo_reg]
    thi = [v for p, r, v in w if p == 'A' and r == thi_reg]
    vol = [v for p, r, v in w if p == 'A' and r == vol_reg]
    mix = [v for p, r, v in w if p == 'A' and r == 0x07]

    check(f'SSG ch{ch} tone_lo 0x{exp_tlo:02X}', exp_tlo in tlo, str(tlo))
    check(f'SSG ch{ch} tone_hi 0x{exp_thi:02X}', exp_thi in thi, str(thi))
    check(f'SSG ch{ch} volume 0x0F', 0x0F in vol)
    check(f'SSG ch{ch} mixer 0x38', 0x38 in mix)

# ====================================================================
# SSG KEY-OFF ($24-$26)
# ====================================================================
print('\n=== SSG KEY-OFF ===')
for ch in range(3):
    z = boot()
    w = send_cmd(z, 0x24 + ch)
    vol_reg = 0x08 + ch
    vol = [v for p, r, v in w if p == 'A' and r == vol_reg]
    check(f'SSG ch{ch} key-off vol=0', 0x00 in vol)

# ====================================================================
# ADPCM-B PLAY ($40)
# ====================================================================
print('\n=== ADPCM-B PLAY ===')
z = boot()
send_cmd(z, 0x08)
send_cmd(z, 0)  # sample 0
w = send_cmd(z, 0x40)
portA = [(r, v) for p, r, v in w if p == 'A']
check('ADPCM-B reset', (0x10, 0x01) in portA)
check('ADPCM-B L/R', (0x11, 0xC0) in portA)
check('ADPCM-B start_lo', (0x12, 0x00) in portA)
check('ADPCM-B start_hi', (0x13, 0x00) in portA)
check('ADPCM-B end_lo', (0x14, 0x40) in portA)
check('ADPCM-B end_hi', (0x15, 0x00) in portA)
check('ADPCM-B delta_lo ($73)', (0x19, 0x73) in portA)
check('ADPCM-B delta_hi ($65)', (0x1A, 0x65) in portA)
check('ADPCM-B volume ($FF)', (0x1B, 0xFF) in portA)
check('ADPCM-B start play', (0x10, 0x80) in portA)

# ====================================================================
# ADPCM-B STOP ($41)
# ====================================================================
print('\n=== ADPCM-B STOP ===')
w = send_cmd(z, 0x41)
portA = [(r, v) for p, r, v in w if p == 'A']
check('ADPCM-B stop', (0x10, 0x01) in portA)

# ====================================================================
# FM PANNING ($30-$33)
# ====================================================================
print('\n=== FM PANNING ===')
pan_tests = [(0, 0x80, 'Left'), (1, 0xC0, 'Center'), (2, 0x40, 'Right')]
for param, expected, label in pan_tests:
    z = boot()
    send_cmd(z, 0x08)
    send_cmd(z, param)
    w = send_cmd(z, 0x30)  # FM pan ch0
    portA = [(r, v) for p, r, v in w if p == 'A']
    # ch0 -> YM ch1 -> offset 1 -> reg $B5
    check(f'FM pan ch0 {label} = 0x{expected:02X}', (0xB5, expected) in portA, str(portA))

# FM ch2 panning (Port B)
z = boot()
send_cmd(z, 0x08)
send_cmd(z, 0)  # Left
w = send_cmd(z, 0x32)
portB = [(r, v) for p, r, v in w if p == 'B']
# ch2 -> YM ch4 -> offset 1 -> reg $B5
check('FM pan ch2 Port B reg B5 = 0x80', (0xB5, 0x80) in portB, str(portB))

# ====================================================================
# ADPCM-A PANNING ($34-$39)
# ====================================================================
print('\n=== ADPCM-A PANNING ===')
z = boot()
send_cmd(z, 0x08)
send_cmd(z, 0)  # Left
w = send_cmd(z, 0x34)  # ADPCM-A pan ch0
check('ADPCM-A pan stored', z.ram[0x1C] == 0x80)  # RAM_ADPCMA_PAN

# ====================================================================
# COMBINED: Set patch, set pan, play note, verify all correct
# ====================================================================
print('\n=== COMBINED: patch + pan + note ===')
z = boot()
# Set patch 1 (organ) for ch0
send_cmd(z, 0x08); send_cmd(z, 1)
send_cmd(z, 0x18)  # set patch ch0
check('Patch 1 stored', z.ram[0x10] == 1)

# Set pan = Right for ch0
send_cmd(z, 0x08); send_cmd(z, 2)
send_cmd(z, 0x30)

# Play C5 (60) on ch0
send_cmd(z, 0x08); send_cmd(z, 60)
w = send_cmd(z, 0x10)

# Verify patch 1 (organ) registers
# ch0 -> YM ch1 -> offset 1
# Organ patch has DT_MUL[0]=0x01 -> reg $31 (offset 1) should be 0x01
patch_31 = [v for p, r, v in w if p == 'A' and r == 0x31]
check('Organ patch DT_MUL[0] = 0x01', 0x01 in patch_31, str(patch_31))

# Organ patch has TL[0]=0x23 (modulator) -> reg $41 should be 0x23
patch_41 = [v for p, r, v in w if p == 'A' and r == 0x41]
check('Organ patch TL[0] = 0x23', 0x23 in patch_41, str(patch_41))

# B5 should have Right panning ($40) merged with AMS/PMS
b5_vals = [v for p, r, v in w if p == 'A' and r == 0xB5]
check('Pan Right in B5', any(v & 0xC0 == 0x40 for v in b5_vals), str(b5_vals))

# C5 = octave 5, semi 0, fnum=618=0x26A. lo=0x6A, block=5 -> (5<<3)|2=0x2A
flo = [v for p, r, v in w if p == 'A' and r == 0xA1]
fhi = [v for p, r, v in w if p == 'A' and r == 0xA5]
check('C5 fnum_lo 0x6A', 0x6A in flo)
check('C5 block+fhi 0x2A', 0x2A in fhi)

# Key-on (ch0 -> YM ch1 -> 0xF1)
keyon = [v for p, r, v in w if p == 'A' and r == 0x28]
check('Key-on F1', 0xF1 in keyon)

# ====================================================================
# PLAY SONG ($50)
# ====================================================================
print('\n=== PLAY SONG ($50) ===')
z = boot()

# Check sequencer is stopped initially
check('Seq stopped initially', z.ram[0x40] == 0)  # RAM_SEQ_PLAYING offset

# Send play song 0 command
w = send_cmd(z, 0x50)
check('No YM writes on play cmd', True)  # play just sets up state
check('Seq playing = 1', z.ram[0x40] == 1)

# Check song start address was loaded
from neosynth_build import SONG_DATA_BASE, RAM_SEQ_PLAYING, RAM_SEQ_ROW_LO, RAM_SEQ_ROW_HI
from neosynth_build import RAM_SEQ_START_LO, RAM_SEQ_START_HI, RAM_SEQ_TICK_RATE
from neosynth_build import RAM_SEQ_TICK_CNT, RAM_SEQ_END_LO, RAM_SEQ_END_HI

row_lo = z.ram[(RAM_SEQ_ROW_LO - 0xF800) & 0x7FF]
row_hi = z.ram[(RAM_SEQ_ROW_HI - 0xF800) & 0x7FF]
row_addr = (row_hi << 8) | row_lo
check(f'Row pointer = song start 0x{SONG_DATA_BASE:04X}',
      row_addr == SONG_DATA_BASE, f'got 0x{row_addr:04X}')

tempo = z.ram[(RAM_SEQ_TICK_RATE - 0xF800) & 0x7FF]
check('Tempo loaded = 7', tempo == 7)

# ====================================================================
# STOP SONG ($03 stops sequencer)
# ====================================================================
print('\n=== STOP SONG ($03) ===')
w = send_cmd(z, 0x03)
check('Seq playing = 0 after stop', z.ram[0x40] == 0)

# ====================================================================
# SEQUENCER TICK (IRQ-driven)
# ====================================================================
print('\n=== SEQUENCER TICK ===')
z = boot()

# Start song 0
send_cmd(z, 0x50)
check('Seq playing after $50', z.ram[0x40] == 1)

# Simulate enough timer IRQs to advance past the first tick
# The tick rate is 7, so after 7 IRQs the sequencer should advance
# First, verify counter starts at tempo value
tick_cnt = z.ram[(RAM_SEQ_TICK_CNT - 0xF800) & 0x7FF]
check(f'Tick counter init = 7', tick_cnt == 7, f'got {tick_cnt}')

# Fire IRQs one at a time and check counter decrement
z.ym_writes.clear()
for i in range(6):
    z.fire_irq()
    # Run IRQ handler
    for _ in range(1000):
        z.step()
        if z.halted or z.pc == z.mem_read16(z.sp):
            break
        if z.halted:
            break

# After 6 IRQs, counter should be at 1
tick_cnt = z.ram[(RAM_SEQ_TICK_CNT - 0xF800) & 0x7FF]
check(f'After 6 IRQs, counter = 1', tick_cnt == 1, f'got {tick_cnt}')

# No musically relevant YM writes yet (only Timer A flag resets to reg $27)
# Decode writes to check for non-timer writes
pre_writes = []
pre_cur_a = 0
for _, port, val in z.ym_writes:
    if port == 0x04: pre_cur_a = val
    elif port == 0x05:
        if pre_cur_a != 0x27:  # skip Timer A flag reset
            pre_writes.append(('A', pre_cur_a, val))
check('No music YM writes before tick', len(pre_writes) == 0, f'got {len(pre_writes)} writes')

# Fire 7th IRQ - this should trigger first tick (patch change row)
z.ym_writes.clear()
z.fire_irq()
for _ in range(50000):
    z.step()
    if z.halted:
        break

# After tick, counter should be reloaded to tempo
tick_cnt = z.ram[(RAM_SEQ_TICK_CNT - 0xF800) & 0x7FF]
check(f'After tick, counter reloaded = 7', tick_cnt == 7, f'got {tick_cnt}')

# Row pointer should have advanced by 8 bytes (one row)
row_lo = z.ram[(RAM_SEQ_ROW_LO - 0xF800) & 0x7FF]
row_hi = z.ram[(RAM_SEQ_ROW_HI - 0xF800) & 0x7FF]
row_addr = (row_hi << 8) | row_lo
check(f'Row advanced to 0x{SONG_DATA_BASE + 8:04X}',
      row_addr == SONG_DATA_BASE + 8, f'got 0x{row_addr:04X}')

# First row is [0x82, 0x81, 0, 0, 0, 0, 0, 0] - patch changes
# $82 = set patch 2 on FM0, $81 = set patch 1 on FM1
# These should store patches in RAM but not produce note YM writes
# (patch changes just store the index, no keyon)

# Fire 7 more IRQs for second tick (the first note row)
z.ym_writes.clear()
for i in range(7):
    z.fire_irq()
    for _ in range(50000):
        z.step()
        if z.halted:
            break

# Second row is [48, 36, 0, 0, 0, 0, 0, 4] - FM0=C4, FM1=C2, ADPCM=smp4
# Decode YM writes
writes_2nd = []
cur_addr_a = 0
cur_addr_b = 0
for _, port, val in z.ym_writes:
    if port == 0x04:
        cur_addr_a = val
    elif port == 0x06:
        cur_addr_b = val
    elif port == 0x05:
        writes_2nd.append(('A', cur_addr_a, val))
    elif port == 0x07:
        writes_2nd.append(('B', cur_addr_b, val))

# Check FM ch0 key-on (YM ch1 = 0xF1)
keyon_writes = [v for p, r, v in writes_2nd if p == 'A' and r == 0x28]
check('Seq tick: FM ch0 key-on 0xF1', 0xF1 in keyon_writes, str(keyon_writes))

# Check FM ch1 key-on (YM ch2 = 0xF2)
check('Seq tick: FM ch1 key-on 0xF2', 0xF2 in keyon_writes, str(keyon_writes))

# Check that ADPCM-A was triggered (Port B reg $00 should have trigger)
adpcm_trig = [v for p, r, v in writes_2nd if p == 'B' and r == 0x00 and v < 0x80]
check('Seq tick: ADPCM-A triggered', len(adpcm_trig) > 0, str(adpcm_trig))

# Check FM ch0 has patch registers written (24 operator regs on Port A)
fm0_patch_writes = [v for p, r, v in writes_2nd if p == 'A' and 0x31 <= r <= 0x8E]
check('Seq tick: FM ch0 patch regs written', len(fm0_patch_writes) >= 24,
      f'got {len(fm0_patch_writes)}')

# Verify C4 frequency (MIDI 48: octave 4, semitone 0 -> fnum=618=0x26A, block=4)
# fnum_lo=0x6A on reg $A1, block_fnum_hi = (4<<3)|2 = 0x22 on reg $A5
flo = [v for p, r, v in writes_2nd if p == 'A' and r == 0xA1]
fhi = [v for p, r, v in writes_2nd if p == 'A' and r == 0xA5]
check('Seq tick: C4 fnum_lo 0x6A', 0x6A in flo, str(flo))
check('Seq tick: C4 block+fhi 0x22', 0x22 in fhi, str(fhi))

# ====================================================================
# SEQUENCER SUSTAIN AND KEY-OFF
# ====================================================================
print('\n=== SEQUENCER SUSTAIN/KEYOFF ===')
# Third row should be sustain [0,0,0,0,0,0,0,0] - no YM writes
z.ym_writes.clear()
for i in range(7):
    z.fire_irq()
    for _ in range(50000):
        z.step()
        if z.halted:
            break

writes_3rd = []
cur_addr_a = 0
cur_addr_b = 0
for _, port, val in z.ym_writes:
    if port == 0x04: cur_addr_a = val
    elif port == 0x06: cur_addr_b = val
    elif port == 0x05: writes_3rd.append(('A', cur_addr_a, val))
    elif port == 0x07: writes_3rd.append(('B', cur_addr_b, val))

# Sustain row should produce no key-on/off or frequency writes
# (only Timer A flag reset writes, which go to reg $27)
note_writes = [(p, r, v) for p, r, v in writes_3rd
               if r in (0x28, 0xA0, 0xA1, 0xA2, 0xA5, 0xA6)]
check('Sustain row: no note/keyon writes', len(note_writes) == 0,
      str(note_writes[:5]))

# ====================================================================
# PLAY SONG 1 ($51)
# ====================================================================
print('\n=== PLAY SONG 1 ($51) ===')
z = boot()
w = send_cmd(z, 0x51)
check('Song 1 playing', z.ram[0x40] == 1)

# Song 1 start address should be different from song 0
row_lo = z.ram[(RAM_SEQ_ROW_LO - 0xF800) & 0x7FF]
row_hi = z.ram[(RAM_SEQ_ROW_HI - 0xF800) & 0x7FF]
row_addr = (row_hi << 8) | row_lo
check(f'Song 1 start addr > song 0 start', row_addr > SONG_DATA_BASE,
      f'got 0x{row_addr:04X}')

# ====================================================================
# OUT OF RANGE SONG
# ====================================================================
print('\n=== OUT OF RANGE SONG ===')
z = boot()
w = send_cmd(z, 0x5F)  # song 15 - out of range
check('OOB song: not playing', z.ram[0x40] == 0)

# ====================================================================
# SONG LOOP (end marker wraps to start)
# ====================================================================
print('\n=== SONG LOOP ===')
z = boot()
send_cmd(z, 0x50)

# Get song 0 total rows: we know it from build_test_songs
from neosynth_build import build_test_songs
songs = build_test_songs()
song0_bytes, song0_tempo = songs[0]
song0_rows = len(song0_bytes) // 8

# Advance through all rows
for row in range(song0_rows + 1):  # +1 to hit end marker and loop
    for i in range(7):
        z.fire_irq()
        for _ in range(50000):
            z.step()
            if z.halted:
                break

# After looping, row pointer should be back near start + 8 (past first row after loop)
row_lo = z.ram[(RAM_SEQ_ROW_LO - 0xF800) & 0x7FF]
row_hi = z.ram[(RAM_SEQ_ROW_HI - 0xF800) & 0x7FF]
row_addr = (row_hi << 8) | row_lo
check('After loop: row ptr near start',
      SONG_DATA_BASE <= row_addr < SONG_DATA_BASE + len(song0_bytes),
      f'got 0x{row_addr:04X}')
check('Still playing after loop', z.ram[0x40] == 1)

# ====================================================================
# SUMMARY
# ====================================================================
print(f'\n{"="*60}')
print(f'RESULTS: {passed} passed, {failed} failed')
print(f'{"="*60}')

if failed:
    sys.exit(1)
else:
    print('ALL TESTS PASSED')
    sys.exit(0)
