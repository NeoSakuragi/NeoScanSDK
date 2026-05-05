#!/usr/bin/env python3
"""Build a NeoSynth Z80 M-ROM with full YM2610 sound driver.

Features:
  - ADPCM-A sample trigger on channels 0-5  (cmd $C0-$FF)
  - FM note playback on channels 1-4        (cmd $10-$1F)
  - SSG note playback on channels 1-3       (cmd $20-$2F)
  - ADPCM-B playback                        (cmd $40-$4F)
  - Panning control                         (cmd $30-$3F)
  - Tick-based music sequencer              (cmd $50-$5F)
  - Stop/silence all                        (cmd $03)

Command protocol (68K -> Z80 via NMI):
  $01         - Init/reset
  $03         - Stop all (including sequencer)
  $08         - Set param (next NMI byte = param value, via SND_play2)
  $10+ch      - FM key-on ch (0-3), note from param byte (MIDI note)
  $14+ch      - FM key-off ch (0-3)
  $18+ch      - FM set patch ch (0-3), patch from param byte
  $20+ch      - SSG key-on ch (0-2), note from param byte
  $24+ch      - SSG key-off ch (0-2)
  $30+ch      - FM panning ch (0-3), param: 0=L, 1=C, 2=R
  $34+ch      - ADPCM-A panning ch (0-5), param: 0=L, 1=C, 2=R
  $40         - ADPCM-B play (sample from param byte)
  $41         - ADPCM-B stop
  $50+N       - Play song N (tick-based sequencer, Timer A driven)
  $C0+smp     - ADPCM-A trigger sample (on current ADPCM-A channel)

Music engine:
  Timer A IRQ at ~55Hz, software counter divides to sequencer tick rate.
  Song data: 8 bytes/row (FM0-3, SSG0-2, ADPCM-A) in M-ROM.
  Row bytes: $00=sustain, $01=key-off, $02-$7F=note-on, $80-$BF=set-patch.
  $FF = end-of-song (loops to start).
  2 built-in songs: C major scale (song 0), chord progression (song 1).
"""
import struct, sys, argparse

ADPCM_SAMPLES = [
    (0x0000, 0x0040),
    (0x0041, 0x0080),
    (0x0081, 0x00C0),
    (0x00C1, 0x0120),
    (0x5070, 0x5923),
    (0xA470, 0xB521),
    (0x5A69, 0x6423),
    (0x6569, 0x6D23),
]

FM_FNUMS = [618, 627, 636, 645, 655, 664, 674, 683, 694, 704, 714, 724]
SSG_PERIODS_OCT4 = [239, 225, 213, 201, 190, 179, 169, 159, 150, 142, 134, 126]

FM_PATCH_SIMPLE = {
    'DT_MUL': [0x01, 0x00, 0x00, 0x00],
    'TL':     [0x00, 0x7F, 0x7F, 0x7F],
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x00, 0x00, 0x00, 0x00],
    'SR':     [0x00, 0x00, 0x00, 0x00],
    'SL_RR':  [0x0F, 0x0F, 0x0F, 0x0F],
    'FB_ALG': 0x07,
    'LR_AMS_PMS': 0xC0,
}
FM_PATCH_ORGAN = {
    'DT_MUL': [0x01, 0x02, 0x01, 0x02],
    'TL':     [0x23, 0x00, 0x23, 0x00],  # carriers (ops 1,3) at 0, mods at 0x23
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x05, 0x02, 0x05, 0x02],
    'SR':     [0x02, 0x01, 0x02, 0x01],
    'SL_RR':  [0x1A, 0x0F, 0x1A, 0x0F],  # carriers: SL=0, RR=15
    'FB_ALG': 0x35,  # algorithm 5 (2 carriers: ops 1 and 3), FB=6
    'LR_AMS_PMS': 0xC0,
}
FM_PATCH_BRASS = {
    'DT_MUL': [0x01, 0x01, 0x01, 0x01],
    'TL':     [0x1A, 0x00, 0x1C, 0x00],  # ops 1,3 are carriers at 0
    'KS_AR':  [0x1F, 0x1D, 0x1F, 0x1D],
    'AM_DR':  [0x08, 0x04, 0x0A, 0x04],
    'SR':     [0x02, 0x02, 0x02, 0x02],
    'SL_RR':  [0x1A, 0x1F, 0x1A, 0x1F],  # carriers: SL=1, RR=15
    'FB_ALG': 0x35,  # algorithm 5, FB=6
    'LR_AMS_PMS': 0xC0,
}
FM_PATCH_PIANO = {
    'DT_MUL': [0x02, 0x01, 0x03, 0x01],
    'TL':     [0x28, 0x00, 0x30, 0x00],  # ops 1,3 are carriers at 0
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x10, 0x0A, 0x10, 0x0A],
    'SR':     [0x06, 0x04, 0x06, 0x04],
    'SL_RR':  [0x2A, 0x2F, 0x2A, 0x2F],  # carriers: SL=2, RR=15
    'FB_ALG': 0x25,  # algorithm 5, FB=4
    'LR_AMS_PMS': 0xC0,
}

FM_PATCHES = [FM_PATCH_SIMPLE, FM_PATCH_ORGAN, FM_PATCH_BRASS, FM_PATCH_PIANO]
NUM_FM_PATCHES = len(FM_PATCHES)
NUM_SAMPLES = len(ADPCM_SAMPLES)

# RAM addresses ($F800-$FFFF)
RAM_CMD       = 0xF800
RAM_PARAM     = 0xF801
RAM_PARAM_FLAG = 0xF802
RAM_FM_PATCH  = 0xF810
RAM_FM_PAN    = 0xF814
RAM_SSG_VOL   = 0xF818
RAM_ADPCMA_PAN = 0xF81C
RAM_ADPCMA_CH = 0xF822
RAM_TEMP      = 0xF830

# Sequencer RAM
RAM_SEQ_PLAYING   = 0xF840   # 1=playing, 0=stopped
RAM_SEQ_ROW_LO    = 0xF841   # current row pointer low
RAM_SEQ_ROW_HI    = 0xF842   # current row pointer high
RAM_SEQ_START_LO  = 0xF843   # song start addr low
RAM_SEQ_START_HI  = 0xF844   # song start addr high
RAM_SEQ_END_LO    = 0xF845   # song end addr low (addr of $FF marker)
RAM_SEQ_END_HI    = 0xF846   # song end addr high
RAM_SEQ_TICK_CNT  = 0xF847   # tempo counter (decrements each IRQ)
RAM_SEQ_TICK_RATE = 0xF848   # tempo reload value
RAM_SEQ_FM_PATCH0 = 0xF849   # current sequencer FM patch ch0
RAM_SEQ_FM_PATCH1 = 0xF84A   # current sequencer FM patch ch1
RAM_SEQ_FM_PATCH2 = 0xF84B   # current sequencer FM patch ch2
RAM_SEQ_FM_PATCH3 = 0xF84C   # current sequencer FM patch ch3

# Data table addresses (in ROM) - placed at $2000+ to avoid code conflicts
SAMPLE_TABLE   = 0x2000
FM_FNUM_TABLE  = 0x2040
SSG_PERIOD_TABLE = 0x2060
FM_PATCH_TABLE = 0x2080
PATCH_SIZE = 26  # 6 params * 4 ops + FB_ALG + LR_AMS_PMS
SONG_TABLE     = 0x2100      # song table: 5 bytes per song
SONG_DATA_BASE = 0x2200      # song data starts here

# Song data format:
# 8 bytes per row: [FM1] [FM2] [FM3] [FM4] [SSG1] [SSG2] [SSG3] [ADPCM_A_TRIG]
# Values: $00=sustain, $01=key-off, $02-$7F=note-on, $80-$BF=set-patch, $FF=end-of-song
SEQ_COLS = 8
SEQ_SUSTAIN = 0x00
SEQ_KEYOFF  = 0x01
SEQ_END     = 0xFF


class Asm:
    """Minimal Z80 assembler with helper methods for common instructions."""
    def __init__(self):
        self.code = bytearray(0x20000)
        self.pc = 0

    def org(self, addr):
        self.pc = addr

    def db(self, *bs):
        for b in bs:
            self.code[self.pc] = b & 0xFF
            self.pc += 1

    def dw(self, val):
        self.db(val & 0xFF, (val >> 8) & 0xFF)

    def here(self):
        return self.pc

    def patch_jr(self, jr_addr, target):
        offset = target - (jr_addr + 2)
        if offset < -128 or offset > 127:
            raise ValueError(f"JR offset {offset} out of range at 0x{jr_addr:04X} -> 0x{target:04X}")
        self.code[jr_addr + 1] = (offset & 0xFF)

    def patch_jp(self, jp_addr, target):
        self.code[jp_addr + 1] = target & 0xFF
        self.code[jp_addr + 2] = (target >> 8) & 0xFF

    # Emit JP nn, return address for patching
    def jp_ph(self):
        addr = self.pc; self.db(0xC3, 0x00, 0x00); return addr
    # Emit JR cc placeholders
    def jr_z_ph(self):
        addr = self.pc; self.db(0x28, 0x00); return addr
    def jr_nz_ph(self):
        addr = self.pc; self.db(0x20, 0x00); return addr
    def jr_c_ph(self):
        addr = self.pc; self.db(0x38, 0x00); return addr
    def jr_nc_ph(self):
        addr = self.pc; self.db(0x30, 0x00); return addr
    def jr_ph(self):
        addr = self.pc; self.db(0x18, 0x00); return addr

    # === Instructions as raw bytes ===
    def nop(self):       self.db(0x00)
    def halt(self):      self.db(0x76)
    def di(self):        self.db(0xF3)
    def ei(self):        self.db(0xFB)
    def ret(self):       self.db(0xC9)
    def retn(self):      self.db(0xED, 0x45)
    def reti(self):      self.db(0xED, 0x4D)
    def im1(self):       self.db(0xED, 0x56)
    def push_af(self):   self.db(0xF5)
    def push_bc(self):   self.db(0xC5)
    def push_de(self):   self.db(0xD5)
    def push_hl(self):   self.db(0xE5)
    def pop_af(self):    self.db(0xF1)
    def pop_bc(self):    self.db(0xC1)
    def pop_de(self):    self.db(0xD1)
    def pop_hl(self):    self.db(0xE1)
    def xor_a(self):     self.db(0xAF)
    def or_a(self):      self.db(0xB7)
    def or_e(self):      self.db(0xB3)
    def or_l(self):      self.db(0xB5)
    def add_a_c(self):   self.db(0x81)
    def sub_d(self):     self.db(0x92)
    def rlca(self):      self.db(0x07)
    def inc_hl(self):    self.db(0x23)
    def inc_d(self):     self.db(0x14)
    def inc_a(self):     self.db(0x3C)
    def dec_d(self):     self.db(0x15)
    def add_hl_hl(self): self.db(0x29)
    def add_hl_de(self): self.db(0x19)
    def add_hl_bc(self): self.db(0x09)
    def srl_h(self):     self.db(0xCB, 0x3C)
    def rr_l(self):      self.db(0xCB, 0x1D)

    # LD register moves
    def ld_a_b(self):    self.db(0x78)
    def ld_a_c(self):    self.db(0x79)
    def ld_a_d(self):    self.db(0x7A)
    def ld_a_e(self):    self.db(0x7B)
    def ld_a_h(self):    self.db(0x7C)
    def ld_a_l(self):    self.db(0x7D)
    def ld_a_hl(self):   self.db(0x7E)  # LD A,(HL)
    def ld_b_a(self):    self.db(0x47)
    def ld_c_a(self):    self.db(0x4F)
    def ld_d_a(self):    self.db(0x57)
    def ld_e_a(self):    self.db(0x5F)
    def ld_h_a(self):    self.db(0x67)
    def ld_l_a(self):    self.db(0x6F)
    def ld_e_hl(self):   self.db(0x5E)
    def ld_d_hl(self):   self.db(0x56)
    def ld_c_hl(self):   self.db(0x4E)
    def ld_b_hl(self):   self.db(0x46)
    def ld_hl_a(self):   self.db(0x77)  # LD (HL), A
    def ld_c_d(self):    self.db(0x4A)
    def ld_e_c(self):    self.db(0x59)
    def ld_c_e(self):    self.db(0x4B)
    def ld_h_d(self):    self.db(0x62)
    def ld_l_e(self):    self.db(0x6B)

    # LD immediate
    def ld_a_n(self, n):   self.db(0x3E, n & 0xFF)
    def ld_b_n(self, n):   self.db(0x06, n & 0xFF)
    def ld_c_n(self, n):   self.db(0x0E, n & 0xFF)
    def ld_d_n(self, n):   self.db(0x16, n & 0xFF)
    def ld_e_n(self, n):   self.db(0x1E, n & 0xFF)
    def ld_h_n(self, n):   self.db(0x26, n & 0xFF)
    def ld_l_n(self, n):   self.db(0x2E, n & 0xFF)
    def ld_sp_nn(self, nn): self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_nn(self, nn): self.db(0x21, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_de_nn(self, nn): self.db(0x11, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_bc_nn(self, nn): self.db(0x01, nn & 0xFF, (nn >> 8) & 0xFF)

    # LD memory
    def ld_mem_a(self, addr):  self.db(0x32, addr & 0xFF, (addr >> 8) & 0xFF)
    def ld_a_mem(self, addr):  self.db(0x3A, addr & 0xFF, (addr >> 8) & 0xFF)

    # ALU immediate
    def add_a_n(self, n):  self.db(0xC6, n & 0xFF)
    def sub_n(self, n):    self.db(0xD6, n & 0xFF)
    def cp_n(self, n):     self.db(0xFE, n & 0xFF)
    def and_n(self, n):    self.db(0xE6, n & 0xFF)
    def or_n(self, n):     self.db(0xF6, n & 0xFF)

    # I/O
    def out_n_a(self, port): self.db(0xD3, port & 0xFF)
    def in_a_n(self, port):  self.db(0xDB, port & 0xFF)
    # OUT (C), A = ED 79
    def out_c_a(self):       self.db(0xED, 0x79)

    # Additional register moves
    def ld_a_de(self):     self.db(0x1A)  # LD A,(DE)
    def ld_de_a(self):     self.db(0x12)  # LD (DE),A
    def ld_e_b(self):      self.db(0x58)
    def ld_b_c(self):      self.db(0x41)
    def ld_b_d(self):      self.db(0x42)
    def ld_b_e(self):      self.db(0x43)
    def ld_d_e(self):      self.db(0x53)
    def ld_d_b(self):      self.db(0x50)
    def ld_d_c(self):      self.db(0x51)
    def inc_de(self):      self.db(0x13)
    def inc_bc(self):      self.db(0x03)
    def inc_b(self):       self.db(0x04)
    def inc_c(self):       self.db(0x0C)
    def inc_e(self):       self.db(0x1C)
    def dec_a(self):       self.db(0x3D)
    def dec_b(self):       self.db(0x05)
    def dec_c(self):       self.db(0x0D)
    def dec_e(self):       self.db(0x1D)
    def add_a_a(self):     self.db(0x87)
    def add_a_e(self):     self.db(0x83)
    def add_a_l(self):     self.db(0x85)
    def add_a_d(self):     self.db(0x82)
    def or_b(self):        self.db(0xB0)
    def or_c(self):        self.db(0xB1)
    def or_d(self):        self.db(0xB2)
    def and_b(self):       self.db(0xA0)
    def and_c(self):       self.db(0xA1)
    def cp_b(self):        self.db(0xB8)
    def cp_c(self):        self.db(0xB9)
    def cp_d(self):        self.db(0xBA)
    def cp_e(self):        self.db(0xBB)
    def sub_b(self):       self.db(0x90)
    def sub_c(self):       self.db(0x91)
    def sub_e(self):       self.db(0x93)
    def ld_l_d(self):      self.db(0x6A)
    def ld_h_e(self):      self.db(0x63)
    def ld_h_b(self):      self.db(0x60)
    def ld_l_c(self):      self.db(0x69)
    def ld_b_l(self):      self.db(0x45)
    def ld_b_h(self):      self.db(0x44)
    def ld_c_b(self):      self.db(0x48)

    # Jumps and calls
    def jp(self, addr):    self.db(0xC3, addr & 0xFF, (addr >> 8) & 0xFF)
    def call(self, addr):  self.db(0xCD, addr & 0xFF, (addr >> 8) & 0xFF)

    # Patch a CALL instruction
    def patch_call(self, call_addr, target):
        self.code[call_addr + 1] = target & 0xFF
        self.code[call_addr + 2] = (target >> 8) & 0xFF


def build_test_songs():
    """Build test song data. Returns list of (song_bytes, tempo) tuples."""
    songs = []

    # Song 0: C major scale on FM1, bass on FM2, kick/snare on ADPCM-A
    # Each note = 2 rows (one 8th note at 120 BPM with 16th-note grid)
    song = []
    # Set FM1 to patch 2 (brass) and FM2 to patch 1 (organ) at the start
    song.append([0x82, 0x81, 0, 0, 0, 0, 0, 0])  # patch change row

    scale = [48, 50, 52, 53, 55, 57, 59, 60]  # C D E F G A B C (MIDI)
    for i, note in enumerate(scale):
        fm1 = note
        fm2 = 36 if i % 4 == 0 else SEQ_SUSTAIN  # C2 bass every 4 notes
        adpcm = 4 if i % 2 == 0 else 5           # kick(smp4)/snare(smp5) alternating
        song.append([fm1, fm2, 0, 0, 0, 0, 0, adpcm])
        song.append([SEQ_SUSTAIN, SEQ_SUSTAIN, 0, 0, 0, 0, 0, 0])  # sustain row

    # Descending back down
    for i, note in enumerate(reversed(scale[:-1])):
        fm1 = note
        fm2 = 36 if i % 4 == 0 else SEQ_SUSTAIN
        adpcm = 4 if i % 2 == 0 else 5
        song.append([fm1, fm2, 0, 0, 0, 0, 0, adpcm])
        song.append([SEQ_SUSTAIN, SEQ_SUSTAIN, 0, 0, 0, 0, 0, 0])

    # Key-off all, then end marker
    song.append([SEQ_KEYOFF, SEQ_KEYOFF, 0, 0, 0, 0, 0, 0])
    song.append([SEQ_END, 0, 0, 0, 0, 0, 0, 0])

    # Flatten to bytes
    song_bytes = bytearray()
    for row in song:
        for b in row:
            song_bytes.append(b & 0xFF)
    # Tempo: ~7 IRQs per tick at 55Hz IRQ rate = ~8 ticks/sec (120 BPM 16ths)
    songs.append((song_bytes, 7))

    # Song 1: Simple chord progression (FM chords + SSG melody)
    song = []
    # Set patches
    song.append([0x80, 0x80, 0x80, 0x80, 0, 0, 0, 0])  # all FM = simple

    # C major chord (C4, E4, G4) on FM1-3, melody on SSG1
    chords = [
        (48, 52, 55, 60),  # C major
        (48, 52, 55, 64),  # C major, melody E5
        (53, 57, 60, 65),  # F major, melody F5
        (53, 57, 60, 67),  # F major, melody G5
        (55, 59, 62, 67),  # G major, melody G5
        (55, 59, 62, 65),  # G major, melody F5
        (48, 52, 55, 64),  # C major, melody E5
        (48, 52, 55, 60),  # C major, melody C5
    ]
    for fm1, fm2, fm3, ssg1 in chords:
        song.append([fm1, fm2, fm3, 0, ssg1, 0, 0, 4])  # with kick
        for _ in range(3):
            song.append([0, 0, 0, 0, 0, 0, 0, 0])       # sustain 3 rows

    song.append([SEQ_KEYOFF, SEQ_KEYOFF, SEQ_KEYOFF, 0, SEQ_KEYOFF, 0, 0, 0])
    song.append([SEQ_END, 0, 0, 0, 0, 0, 0, 0])

    song_bytes = bytearray()
    for row in song:
        for b in row:
            song_bytes.append(b & 0xFF)
    songs.append((song_bytes, 7))

    return songs


def emit_ym_write_portB(a, reg, data_reg='a'):
    """Emit inline: set port B register to value in A."""
    # Assumes we have the register number and data to write.
    # reg is a constant. data_reg is where the value is.
    a.ld_a_n(reg)
    a.out_n_a(0x06)  # Port B addr
    if data_reg == 'e':
        a.ld_a_e()
    elif data_reg == 'b':
        a.ld_a_b()
    elif data_reg == 'c':
        a.ld_a_c()
    elif data_reg == 'd':
        a.ld_a_d()
    # else assume A already has the value
    a.out_n_a(0x07)  # Port B data


def build_driver():
    a = Asm()

    # ================================================================
    # DATA TABLES
    # ================================================================
    # ADPCM-A sample table (4 bytes each: start_lo, start_hi, end_lo, end_hi)
    for i, (start, end) in enumerate(ADPCM_SAMPLES):
        a.org(SAMPLE_TABLE + i * 4)
        a.db(start & 0xFF, (start >> 8) & 0xFF, end & 0xFF, (end >> 8) & 0xFF)

    # FM F-number table (12 entries, 2 bytes each, little-endian)
    a.org(FM_FNUM_TABLE)
    for fnum in FM_FNUMS:
        a.dw(fnum)

    # SSG period table for octave 4 (12 entries, 2 bytes each)
    a.org(SSG_PERIOD_TABLE)
    for period in SSG_PERIODS_OCT4:
        a.dw(period)

    # FM patch table (26 bytes each)
    a.org(FM_PATCH_TABLE)
    for patch in FM_PATCHES:
        for key in ['DT_MUL', 'TL', 'KS_AR', 'AM_DR', 'SR', 'SL_RR']:
            for op_i in range(4):
                a.db(patch[key][op_i])
        a.db(patch['FB_ALG'])
        a.db(patch['LR_AMS_PMS'])

    # Signature
    a.org(0x0040)
    for b in b'NeoSynth v2.0':
        a.db(b)

    # FM key-on/off value tables
    # YM2610 FM channels: 1,2,4,5 (channels 0,3 are disabled for FM)
    # Key-on encoding: bits 4-7=operator mask, bits 0-1=ch within bank, bit 2=bank
    KEYON_TABLE = 0x0050
    a.org(KEYON_TABLE)
    a.db(0xF1, 0xF2, 0xF5, 0xF6)  # key-on: YM ch1,2,4,5
    KEYOFF_TABLE = 0x0054
    a.org(KEYOFF_TABLE)
    a.db(0x01, 0x02, 0x05, 0x06)  # key-off: YM ch1,2,4,5

    # ================================================================
    # SONG DATA
    # ================================================================
    test_songs = build_test_songs()
    num_songs = len(test_songs)

    # Song table at SONG_TABLE: 5 bytes per song
    # [start_lo, start_hi, length_lo, length_hi, tempo]
    song_data_addr = SONG_DATA_BASE
    a.org(SONG_TABLE)
    song_addrs = []
    for song_bytes, tempo in test_songs:
        song_addrs.append(song_data_addr)
        a.db(song_data_addr & 0xFF, (song_data_addr >> 8) & 0xFF)
        a.db(len(song_bytes) & 0xFF, (len(song_bytes) >> 8) & 0xFF)
        a.db(tempo)
        song_data_addr += len(song_bytes)

    # Write actual song data
    data_addr = SONG_DATA_BASE
    for song_bytes, tempo in test_songs:
        a.org(data_addr)
        for b in song_bytes:
            a.db(b)
        data_addr += len(song_bytes)

    # ================================================================
    # VECTORS
    # ================================================================
    a.org(0x0000)
    a.di()
    a.jp(0x0100)  # JP to init

    # IRQ at $0038: jump to sequencer tick handler
    a.org(0x0038)
    a.jp(0x0080)  # jump to IRQ handler (placed at $0080 for space)

    a.org(0x0066)  # NMI vector
    a.jp(0x0280)

    # ================================================================
    # IRQ HANDLER at $0080 — Timer A tick for sequencer
    # ================================================================
    a.org(0x0080)
    a.push_af()
    a.push_hl()
    a.push_de()
    a.push_bc()

    # Reset Timer A flag: reg $27 = $15 via Port A
    a.ld_a_n(0x27); a.out_n_a(0x04)
    a.ld_a_n(0x15); a.out_n_a(0x05)

    # Check if music is playing
    a.ld_a_mem(RAM_SEQ_PLAYING)
    a.or_a()
    jr_irq_not_playing = a.jr_z_ph()

    # Decrement tick counter
    a.ld_a_mem(RAM_SEQ_TICK_CNT)
    a.sub_n(1)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)
    jr_irq_no_tick = a.jr_nz_ph()

    # Counter reached 0: reload and call sequencer tick
    a.ld_a_mem(RAM_SEQ_TICK_RATE)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)
    # CALL sequencer tick subroutine (patched later)
    jp_seq_tick_call = a.here()
    a.call(0x0000)

    a.patch_jr(jr_irq_no_tick, a.here())
    a.patch_jr(jr_irq_not_playing, a.here())

    # IRQ exit
    IRQ_DONE = a.here()
    a.pop_bc()
    a.pop_de()
    a.pop_hl()
    a.pop_af()
    a.ei()
    a.reti()

    # ================================================================
    # INIT at $0100
    # ================================================================
    a.org(0x0100)
    a.ld_sp_nn(0xFFFC)
    a.im1()

    # === YM2610 full hardware init (matches KOF96 reference) ===

    # FM key-off all 4 channels (reg $28 via Port A)
    # YM2610 FM channels: 1,2,4,5 (channels 0,3 disabled for FM)
    for ch_val in [0x01, 0x02, 0x05, 0x06]:
        a.ld_a_n(0x28); a.out_n_a(0x04)
        a.ld_a_n(ch_val); a.out_n_a(0x05)

    # SSG volumes to 0 (regs $08-$0A via Port A)
    for reg in [0x08, 0x09, 0x0A]:
        a.ld_a_n(reg); a.out_n_a(0x04)
        a.xor_a(); a.out_n_a(0x05)

    # SSG mixer: disable all tone + noise (reg $07 = $3F via Port A)
    a.ld_a_n(0x07); a.out_n_a(0x04)
    a.ld_a_n(0x3F); a.out_n_a(0x05)

    # ADPCM-A dump all channels (Port B reg $00 = $BF)
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0xBF); a.out_n_a(0x07)

    # ADPCM-A master volume: Port B reg $01 = $3F
    a.ld_a_n(0x01); a.out_n_a(0x06)
    a.ld_a_n(0x3F); a.out_n_a(0x07)

    # ADPCM-B stop: Port A reg $10 = $01, then $10 = $00 (stop + clear)
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.xor_a(); a.out_n_a(0x05)

    # Clear ADPCM-B flags (Port A reg $1C = $80, then $1C = $00)
    a.ld_a_n(0x1C); a.out_n_a(0x04)
    a.ld_a_n(0x80); a.out_n_a(0x05)
    a.ld_a_n(0x1C); a.out_n_a(0x04)
    a.xor_a(); a.out_n_a(0x05)

    # Timer A + B flags reset (reg $27 = $30 via Port A)
    a.ld_a_n(0x27); a.out_n_a(0x04)
    a.ld_a_n(0x30); a.out_n_a(0x05)

    # Init RAM: FM pan = $C0 (center) for all 4 channels
    a.ld_a_n(0xC0)
    for i in range(4):
        a.ld_mem_a(RAM_FM_PAN + i)
    # ADPCM-A pan = $C0 for all 6 channels
    for i in range(6):
        a.ld_mem_a(RAM_ADPCMA_PAN + i)

    # Clear param and flags
    a.xor_a()
    a.ld_mem_a(RAM_ADPCMA_CH)
    a.ld_mem_a(RAM_PARAM)
    a.ld_mem_a(RAM_PARAM_FLAG)

    # Default SSG volumes
    a.ld_a_n(0x0F)
    for i in range(3):
        a.ld_mem_a(RAM_SSG_VOL + i)

    # Default FM patches (all ch = patch 0)
    a.xor_a()
    for i in range(4):
        a.ld_mem_a(RAM_FM_PATCH + i)

    # Init sequencer RAM
    a.xor_a()
    a.ld_mem_a(RAM_SEQ_PLAYING)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)
    a.ld_a_n(7)  # default tempo
    a.ld_mem_a(RAM_SEQ_TICK_RATE)
    a.xor_a()
    for addr in [RAM_SEQ_ROW_LO, RAM_SEQ_ROW_HI,
                 RAM_SEQ_START_LO, RAM_SEQ_START_HI,
                 RAM_SEQ_END_LO, RAM_SEQ_END_HI,
                 RAM_SEQ_FM_PATCH0, RAM_SEQ_FM_PATCH1,
                 RAM_SEQ_FM_PATCH2, RAM_SEQ_FM_PATCH3]:
        a.ld_mem_a(addr)

    # Set up Timer A for IRQ (~55 Hz from KOF96 values)
    # reg $24 = Timer A lo 8 bits, reg $25 = Timer A hi 2 bits
    a.ld_a_n(0x24); a.out_n_a(0x04)
    a.ld_a_n(0xAC); a.out_n_a(0x05)
    a.ld_a_n(0x25); a.out_n_a(0x04)
    a.ld_a_n(0x03); a.out_n_a(0x05)
    # Enable Timer A: reg $27 = $15 (reset+load+enable Timer A)
    a.ld_a_n(0x27); a.out_n_a(0x04)
    a.ld_a_n(0x15); a.out_n_a(0x05)

    # Enable NMI
    a.ld_a_n(0x0F)  # just need any value
    a.out_n_a(0x08)
    a.ei()

    # Main loop
    MAIN_LOOP = a.here()
    a.halt()
    a.db(0x18, 0xFD)  # JR $-3 (back to HALT)

    # ================================================================
    # NMI HANDLER at $0280
    # ================================================================
    a.org(0x0280)
    a.push_af()
    a.push_hl()
    a.push_de()
    a.push_bc()

    a.in_a_n(0x00)       # read sound code
    a.out_n_a(0x0C)      # reply
    a.ld_mem_a(RAM_CMD)  # store

    # --- Check param flag first ---
    a.ld_a_mem(RAM_PARAM_FLAG)
    a.or_a()
    jr_no_param = a.jr_z_ph()
    # This byte IS the param value
    a.xor_a()
    a.ld_mem_a(RAM_PARAM_FLAG)
    a.ld_a_mem(RAM_CMD)
    a.ld_mem_a(RAM_PARAM)
    jp_done0 = a.jp_ph()
    a.patch_jr(jr_no_param, a.here())

    # --- Reload cmd and dispatch ---
    a.ld_a_mem(RAM_CMD)

    # $01: init/reset
    a.cp_n(0x01)
    jr_not_01 = a.jr_nz_ph()
    # We'll call stop_all subroutine (address TBD, use JP placeholder)
    jp_call_stop_reset = a.jp_ph()
    a.patch_jr(jr_not_01, a.here())

    # $03: stop all
    a.cp_n(0x03)
    jr_not_03 = a.jr_nz_ph()
    jp_call_stop_all = a.jp_ph()
    a.patch_jr(jr_not_03, a.here())

    # $08: set param flag
    a.cp_n(0x08)
    jr_not_08 = a.jr_nz_ph()
    a.ld_a_n(0x01)
    a.ld_mem_a(RAM_PARAM_FLAG)
    jp_done1 = a.jp_ph()
    a.patch_jr(jr_not_08, a.here())

    # $10-$1F: FM commands
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x10)
    jr_below_10 = a.jr_c_ph()
    a.cp_n(0x20)
    jr_above_1f = a.jr_nc_ph()
    jp_fm_dispatch = a.jp_ph()
    a.patch_jr(jr_below_10, a.here())
    a.patch_jr(jr_above_1f, a.here())

    # $20-$2F: SSG commands
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x20)
    jr_below_20 = a.jr_c_ph()
    a.cp_n(0x30)
    jr_above_2f = a.jr_nc_ph()
    jp_ssg_dispatch = a.jp_ph()
    a.patch_jr(jr_below_20, a.here())
    a.patch_jr(jr_above_2f, a.here())

    # $30-$3F: Pan commands
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x30)
    jr_below_30 = a.jr_c_ph()
    a.cp_n(0x40)
    jr_above_3f = a.jr_nc_ph()
    jp_pan_dispatch = a.jp_ph()
    a.patch_jr(jr_below_30, a.here())
    a.patch_jr(jr_above_3f, a.here())

    # $40: ADPCM-B play
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x40)
    jr_not_40 = a.jr_nz_ph()
    jp_adpcmb_play = a.jp_ph()
    a.patch_jr(jr_not_40, a.here())

    # $41: ADPCM-B stop
    a.cp_n(0x41)
    jr_not_41 = a.jr_nz_ph()
    jp_adpcmb_stop = a.jp_ph()
    a.patch_jr(jr_not_41, a.here())

    # $50-$5F: Play song N
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x50)
    jr_below_50 = a.jr_c_ph()
    a.cp_n(0x60)
    jr_above_5f = a.jr_nc_ph()
    a.sub_n(0x50)
    a.ld_b_a()  # B = song index
    jp_play_song = a.jp_ph()
    a.patch_jr(jr_below_50, a.here())
    a.patch_jr(jr_above_5f, a.here())

    # $C0+: ADPCM-A trigger
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0xC0)
    jr_below_c0 = a.jr_c_ph()
    a.sub_n(0xC0)
    a.ld_b_a()  # B = sample index
    jp_adpcma_trig = a.jp_ph()
    a.patch_jr(jr_below_c0, a.here())

    # NMI done
    NMI_DONE = a.here()
    a.pop_bc()
    a.pop_de()
    a.pop_hl()
    a.pop_af()
    a.retn()

    # Collect all JP-to-done placeholders
    done_patches = [jp_done0, jp_done1]

    # ================================================================
    # SUBROUTINES - placed sequentially after NMI handler
    # ================================================================
    # Start subroutines at $0400 to have plenty of room
    a.org(0x0400)

    # ----------------------------------------------------------------
    # FM DISPATCH (cmd $10-$1F)
    # ----------------------------------------------------------------
    FM_DISPATCH = a.here()
    a.patch_jp(jp_fm_dispatch, FM_DISPATCH)

    a.ld_a_mem(RAM_CMD)
    a.sub_n(0x10)
    # 0-3: key-on, 4-7: key-off, 8-11: set patch
    a.cp_n(0x04)
    jr_not_fmon = a.jr_nc_ph()
    # FM key-on: A = channel (0-3)
    a.ld_b_a()
    jp_fmon = a.jp_ph()  # will patch to FM_KEY_ON
    a.patch_jr(jr_not_fmon, a.here())

    a.cp_n(0x08)
    jr_not_fmoff = a.jr_nc_ph()
    # FM key-off: A-4 = channel
    a.sub_n(0x04)
    a.ld_b_a()
    jp_fmoff = a.jp_ph()
    a.patch_jr(jr_not_fmoff, a.here())

    # FM set patch: A-8 = channel
    a.sub_n(0x08)
    a.ld_b_a()
    jp_fmpatch = a.jp_ph()

    # ----------------------------------------------------------------
    # SSG DISPATCH (cmd $20-$2F)
    # ----------------------------------------------------------------
    SSG_DISPATCH = a.here()
    a.patch_jp(jp_ssg_dispatch, SSG_DISPATCH)

    a.ld_a_mem(RAM_CMD)
    a.sub_n(0x20)
    a.cp_n(0x03)
    jr_not_ssgon = a.jr_nc_ph()
    a.ld_b_a()
    jp_ssgon = a.jp_ph()
    a.patch_jr(jr_not_ssgon, a.here())

    a.cp_n(0x07)
    jr_not_ssgoff = a.jr_nc_ph()
    a.sub_n(0x04)
    a.ld_b_a()
    jp_ssgoff = a.jp_ph()
    a.patch_jr(jr_not_ssgoff, a.here())
    a.jp(NMI_DONE)

    # ----------------------------------------------------------------
    # PAN DISPATCH (cmd $30-$3F)
    # ----------------------------------------------------------------
    PAN_DISPATCH = a.here()
    a.patch_jp(jp_pan_dispatch, PAN_DISPATCH)

    a.ld_a_mem(RAM_CMD)
    a.sub_n(0x30)
    a.cp_n(0x04)
    jr_not_fmpan = a.jr_nc_ph()
    a.ld_b_a()
    jp_fmpan = a.jp_ph()
    a.patch_jr(jr_not_fmpan, a.here())

    a.sub_n(0x04)
    a.cp_n(0x06)
    jr_not_adpcmapan = a.jr_nc_ph()
    a.ld_b_a()
    jp_adpcmapan = a.jp_ph()
    a.patch_jr(jr_not_adpcmapan, a.here())
    a.jp(NMI_DONE)

    # ================================================================
    # STOP ALL (also stops sequencer)
    # ================================================================
    STOP_ALL = a.here()
    a.patch_jp(jp_call_stop_reset, STOP_ALL)
    a.patch_jp(jp_call_stop_all, STOP_ALL)

    # Stop sequencer
    a.xor_a()
    a.ld_mem_a(RAM_SEQ_PLAYING)

    # FM key-off all 4 channels (YM2610: ch 1,2,4,5)
    for val in [0x01, 0x02, 0x05, 0x06]:
        a.ld_a_n(0x28); a.out_n_a(0x04)
        a.ld_a_n(val);  a.out_n_a(0x05)

    # SSG silence: volumes to 0
    for reg in [0x08, 0x09, 0x0A]:
        a.ld_a_n(reg); a.out_n_a(0x04)
        a.xor_a();     a.out_n_a(0x05)

    # ADPCM-A dump all: Port B reg $00 = $BF
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0xBF); a.out_n_a(0x07)

    # ADPCM-B stop: Port A reg $10 = $01
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM KEY-ON (B = channel 0-3, note from RAM_PARAM)
    # ================================================================
    FM_KEY_ON = a.here()
    a.patch_jp(jp_fmon, FM_KEY_ON)

    # First load default patch for this channel
    a.push_bc()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.ld_a_hl()          # A = patch index for this channel
    a.ld_mem_a(RAM_TEMP)  # save patch index
    a.pop_bc()

    # --- Save channel to RAM_TEMP+2 ---
    a.ld_a_b()
    a.ld_mem_a(RAM_TEMP + 2)  # save channel number

    # --- Compute patch data pointer ---
    a.ld_a_mem(RAM_TEMP)
    a.cp_n(NUM_FM_PATCHES)
    jr_pok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_pok, a.here())

    # HL = FM_PATCH_TABLE + A * 26
    # 26 = 2 + 8 + 16  -> *2 + *8 + *16
    a.ld_c_a()           # C = patch index
    a.ld_b_n(0)
    a.ld_h_n(0); a.ld_l_a()  # HL = idx
    a.add_hl_hl()        # *2
    a.push_hl()          # save *2
    a.add_hl_hl()        # *4
    a.add_hl_hl()        # *8
    a.push_hl()          # save *8
    a.add_hl_hl()        # *16
    a.pop_de()           # DE = *8
    a.add_hl_de()        # HL = *24
    a.pop_de()           # DE = *2
    a.add_hl_de()        # HL = *26
    a.ld_de_nn(FM_PATCH_TABLE)
    a.add_hl_de()        # HL = patch data pointer

    # --- Restore channel into B ---
    a.ld_a_mem(RAM_TEMP + 2)
    a.ld_b_a()

    # --- Determine port and ch_offset from B ---
    # YM2610 FM uses channels 1,2,4,5 so offset = (ch & 1) + 1
    a.ld_a_b()
    a.and_n(0x01)
    a.inc_a()                 # offset 1 or 2 (not 0 or 1)
    a.ld_mem_a(RAM_TEMP + 1)  # ch_offset

    a.ld_a_b()
    a.and_n(0x02)
    jr_porta = a.jr_z_ph()
    # Port B: addr=$06, data=$07
    a.ld_c_n(0x06)
    a.ld_d_n(0x07)
    jr_port_done = a.jr_ph()
    a.patch_jr(jr_porta, a.here())
    a.ld_c_n(0x04)
    a.ld_d_n(0x05)
    a.patch_jr(jr_port_done, a.here())

    # --- Write all 24 operator registers ---
    # For each of 6 register groups, 4 operators
    # Reg groups: $30, $40, $50, $60, $70, $80
    # Op offsets: 0, 8, 4, 12
    for reg_base in [0x30, 0x40, 0x50, 0x60, 0x70, 0x80]:
        for op_off in [0, 8, 4, 12]:
            # Read data byte from (HL)
            a.ld_a_hl()       # A = data
            a.push_af()       # save data
            # Compute register: reg_base + op_off + ch_offset
            a.ld_a_mem(RAM_TEMP + 1)
            a.add_a_n(reg_base + op_off)
            # Write addr to port (C)
            a.out_c_a()       # OUT (C), A - sets register address
            # Write data to port (D) - swap C<->D temporarily
            a.pop_af()        # A = data
            a.ld_e_c()        # save C in E
            a.ld_c_d()        # C = data port
            a.out_c_a()       # OUT (C), A - write data
            a.ld_c_e()        # restore C = addr port
            a.inc_hl()        # next patch byte

    # --- Write FB_ALG: reg $B0 + ch_offset ---
    a.ld_a_hl()
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB0)
    a.out_c_a()
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()
    a.ld_c_e()
    a.inc_hl()

    # --- Write LR_AMS_PMS: reg $B4 + ch_offset, merged with panning ---
    a.ld_a_hl()
    a.and_n(0x3F)        # keep AMS/PMS
    a.ld_e_a()
    # Get pan from RAM
    a.ld_a_b()           # channel
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()          # pan value
    a.and_n(0xC0)
    a.or_e()             # merge
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB4)
    a.out_c_a()          # addr
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()          # data
    a.ld_c_e()

    # --- Set frequency ---
    # Get note from param, compute octave/semitone
    a.ld_a_mem(RAM_PARAM)
    a.ld_e_a()           # E = note
    a.ld_d_n(0)          # D = octave counter

    div12 = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_div_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)     # JR back to div12
    a.patch_jr(a.here() - 2, div12)
    a.patch_jr(jr_div_done, a.here())

    # D = octave (block), E = semitone
    # Lookup F-number
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()        # *2
    a.push_de()
    a.ld_de_nn(FM_FNUM_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()          # fnum_lo
    a.ld_e_a()
    a.inc_hl()
    a.ld_a_hl()          # fnum_hi (3 bits)
    a.ld_l_a()           # L = fnum_hi

    # Compute reg $A4 value: (block << 3) | fnum_hi
    a.ld_a_d()           # A = octave
    a.and_n(0x07)
    a.rlca(); a.rlca(); a.rlca()
    a.and_n(0x38)
    a.or_l()             # A = block_fnum_hi
    a.ld_d_a()           # D = block_fnum_hi

    # Write freq regs via correct port (C=addr port, from earlier)
    # But C/D were overwritten! We need to recompute port.
    a.ld_a_b()
    a.and_n(0x02)
    jr_freq_porta = a.jr_z_ph()
    # Port B
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA4)
    a.out_n_a(0x06)
    a.ld_a_d(); a.out_n_a(0x07)
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA0)
    a.out_n_a(0x06)
    a.ld_a_e(); a.out_n_a(0x07)
    jr_freq_done = a.jr_ph()

    a.patch_jr(jr_freq_porta, a.here())
    # Port A
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA4)
    a.out_n_a(0x04)
    a.ld_a_d(); a.out_n_a(0x05)
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA0)
    a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.patch_jr(jr_freq_done, a.here())

    # --- Key-on via reg $28 (always port A) ---
    a.ld_a_b()           # channel
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(KEYON_TABLE)
    a.add_hl_de()
    a.ld_a_hl()          # key-on value
    a.ld_e_a()
    a.ld_a_n(0x28)
    a.out_n_a(0x04)
    a.ld_a_e()
    a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM KEY-OFF (B = channel 0-3)
    # ================================================================
    FM_KEY_OFF = a.here()
    a.patch_jp(jp_fmoff, FM_KEY_OFF)

    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(KEYOFF_TABLE)
    a.add_hl_de()
    a.ld_a_hl()
    a.ld_e_a()
    a.ld_a_n(0x28)
    a.out_n_a(0x04)
    a.ld_a_e()
    a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM LOAD PATCH (B = channel 0-3, patch from RAM_PARAM)
    # Just stores patch index in RAM for next key-on
    # ================================================================
    FM_LOAD_PATCH = a.here()
    a.patch_jp(jp_fmpatch, FM_LOAD_PATCH)

    a.ld_a_mem(RAM_PARAM)
    a.cp_n(NUM_FM_PATCHES)
    jr_lp_ok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_lp_ok, a.here())

    a.ld_e_a()           # E = patch index
    a.ld_a_b()           # channel
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.ld_a_mem(RAM_PARAM)
    a.cp_n(NUM_FM_PATCHES)
    jr_lp2 = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_lp2, a.here())
    a.ld_hl_a()

    a.jp(NMI_DONE)

    # ================================================================
    # SSG KEY-ON (B = channel 0-2, note from RAM_PARAM)
    # ================================================================
    SSG_KEY_ON = a.here()
    a.patch_jp(jp_ssgon, SSG_KEY_ON)

    # Compute octave and semitone from MIDI note
    a.ld_a_mem(RAM_PARAM)
    a.ld_e_a()
    a.ld_d_n(0)

    ssg_div = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_ssg_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)
    a.patch_jr(a.here() - 2, ssg_div)
    a.patch_jr(jr_ssg_done, a.here())

    # D = octave, E = semitone
    # Look up base period (octave 4)
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()
    a.push_de()
    a.ld_de_nn(SSG_PERIOD_TABLE)
    a.add_hl_de()
    a.pop_de()
    # HL -> period entry
    a.push_de()
    a.ld_e_hl()          # E = period_lo
    a.inc_hl()
    a.ld_d_hl()          # D = period_hi
    a.ld_h_d(); a.ld_l_e()  # HL = period
    a.pop_de()           # D = octave

    # Adjust period for octave
    a.ld_a_d()
    a.cp_n(4)
    jr_oct_eq = a.jr_z_ph()
    jr_oct_hi = a.jr_nc_ph()

    # Octave < 4: shift left (4-D) times
    a.ld_a_n(4)
    a.sub_d()
    a.ld_d_a()
    ssg_shl = a.here()
    a.add_hl_hl()
    a.dec_d()
    jr_shl_again = a.jr_nz_ph()
    a.patch_jr(jr_shl_again, ssg_shl)
    jr_ssg_adj_done = a.jr_ph()

    a.patch_jr(jr_oct_hi, a.here())
    # Octave > 4: shift right (D-4) times
    a.ld_a_d()
    a.sub_n(4)
    a.ld_d_a()
    ssg_shr = a.here()
    a.srl_h()
    a.rr_l()
    a.dec_d()
    jr_shr_again = a.jr_nz_ph()
    a.patch_jr(jr_shr_again, ssg_shr)

    a.patch_jr(jr_oct_eq, a.here())
    a.patch_jr(jr_ssg_adj_done, a.here())

    # HL = period. Write to SSG regs via Port A.
    # Tone period low: reg = B*2
    a.ld_a_b()
    a.add_a_n(0)         # A = channel
    a.db(0x87)           # ADD A, A = channel * 2
    a.ld_e_a()           # E = reg number
    a.out_n_a(0x04)      # reg addr
    a.ld_a_l()
    a.out_n_a(0x05)      # period low

    # Tone period high: reg = B*2 + 1
    a.ld_a_e()
    a.inc_a()
    a.out_n_a(0x04)
    a.ld_a_h()
    a.and_n(0x0F)
    a.out_n_a(0x05)

    # Mixer: enable tone for all, disable noise
    a.ld_a_n(0x07); a.out_n_a(0x04)
    a.ld_a_n(0x38); a.out_n_a(0x05)

    # Volume: reg $08+ch = $0F
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.ld_a_n(0x0F)
    a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # SSG KEY-OFF (B = channel 0-2)
    # ================================================================
    SSG_KEY_OFF = a.here()
    a.patch_jp(jp_ssgoff, SSG_KEY_OFF)

    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.xor_a()
    a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # ADPCM-A TRIGGER (B = sample index, channel from RAM_ADPCMA_CH)
    # ================================================================
    ADPCMA_TRIGGER = a.here()
    a.patch_jp(jp_adpcma_trig, ADPCMA_TRIGGER)

    # Bounds check
    a.ld_a_b()
    a.cp_n(NUM_SAMPLES)
    jr_smp_ok = a.jr_c_ph()
    a.jp(NMI_DONE)
    a.patch_jr(jr_smp_ok, a.here())

    # HL = sample table + B*4
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl(); a.add_hl_hl()
    a.ld_de_nn(SAMPLE_TABLE)
    a.add_hl_de()

    # Read: E=start_lo, D=start_hi, C=end_lo, B=end_hi
    a.ld_e_hl(); a.inc_hl()
    a.ld_d_hl(); a.inc_hl()
    a.ld_c_hl(); a.inc_hl()
    a.ld_b_hl()

    # Save addresses on stack
    a.push_bc()  # end addr
    a.push_de()  # start addr

    # Get channel (0-5)
    a.ld_a_mem(RAM_ADPCMA_CH)
    a.and_n(0x07)
    a.cp_n(6)
    jr_ch_ok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_ch_ok, a.here())
    a.ld_mem_a(RAM_TEMP)  # save channel

    # Compute channel bitmask: 1 << channel
    a.ld_e_a()
    a.ld_a_n(0x01)
    a.ld_d_a()            # default mask = 1
    a.ld_a_e()
    a.or_a()
    jr_no_shift = a.jr_z_ph()
    a.ld_d_a()            # D = shift count
    a.ld_a_n(0x01)
    shift_loop = a.here()
    a.rlca()
    a.dec_d()
    jr_shift = a.jr_nz_ph()
    a.patch_jr(jr_shift, shift_loop)
    jr_mask_done = a.jr_ph()
    a.patch_jr(jr_no_shift, a.here())
    a.ld_a_n(0x01)
    a.patch_jr(jr_mask_done, a.here())
    # A = channel mask
    a.ld_mem_a(RAM_TEMP + 1)  # save mask

    # Dump (stop) this channel: reg $00 = mask | $80
    a.or_n(0x80)
    a.ld_e_a()
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_e();     a.out_n_a(0x07)

    # Write start address
    a.ld_a_mem(RAM_TEMP)   # channel
    a.add_a_n(0x10)        # reg $10+ch = start_lo
    a.out_n_a(0x06)
    a.pop_de()             # DE = start addr (E=lo, D=hi)
    a.ld_a_e()
    a.out_n_a(0x07)

    a.ld_a_mem(RAM_TEMP)
    a.add_a_n(0x18)        # reg $18+ch = start_hi
    a.out_n_a(0x06)
    a.ld_a_d()
    a.out_n_a(0x07)

    # Write end address
    a.pop_bc()             # BC = end addr (C=lo, B=hi)
    a.ld_a_mem(RAM_TEMP)
    a.add_a_n(0x20)        # reg $20+ch = end_lo
    a.out_n_a(0x06)
    a.ld_a_c()
    a.out_n_a(0x07)

    a.ld_a_mem(RAM_TEMP)
    a.add_a_n(0x28)        # reg $28+ch = end_hi
    a.out_n_a(0x06)
    a.ld_a_b()
    a.out_n_a(0x07)

    # Volume + panning: reg $08+ch
    a.ld_a_mem(RAM_TEMP)   # channel
    a.add_a_n(0x08)
    a.out_n_a(0x06)
    # Get pan from RAM
    a.ld_a_mem(RAM_TEMP)
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_ADPCMA_PAN)
    a.add_hl_de()
    a.ld_a_hl()            # pan value ($C0, $80, $40)
    a.and_n(0xC0)
    a.or_n(0x1F)           # volume = 31
    a.out_n_a(0x07)

    # Trigger: reg $00 = mask (without $80)
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_mem(RAM_TEMP + 1)  # channel mask
    a.out_n_a(0x07)

    a.jp(NMI_DONE)

    # ================================================================
    # ADPCM-B PLAY (sample from RAM_PARAM)
    # ================================================================
    ADPCMB_PLAY = a.here()
    a.patch_jp(jp_adpcmb_play, ADPCMB_PLAY)

    a.ld_a_mem(RAM_PARAM)
    a.cp_n(NUM_SAMPLES)
    jr_ab_ok = a.jr_c_ph()
    a.jp(NMI_DONE)
    a.patch_jr(jr_ab_ok, a.here())

    # Lookup sample
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl(); a.add_hl_hl()
    a.ld_de_nn(SAMPLE_TABLE)
    a.add_hl_de()

    a.ld_e_hl(); a.inc_hl()
    a.ld_d_hl(); a.inc_hl()
    a.ld_c_hl(); a.inc_hl()
    a.ld_b_hl()

    # Stop first
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)

    # L/R output
    a.ld_a_n(0x11); a.out_n_a(0x04)
    a.ld_a_n(0xC0); a.out_n_a(0x05)

    # Start addr
    a.ld_a_n(0x12); a.out_n_a(0x04)
    a.ld_a_e();     a.out_n_a(0x05)
    a.ld_a_n(0x13); a.out_n_a(0x04)
    a.ld_a_d();     a.out_n_a(0x05)

    # End addr
    a.ld_a_n(0x14); a.out_n_a(0x04)
    a.ld_a_c();     a.out_n_a(0x05)
    a.ld_a_n(0x15); a.out_n_a(0x04)
    a.ld_a_b();     a.out_n_a(0x05)

    # Delta-N: 22050Hz => $6573
    a.ld_a_n(0x19); a.out_n_a(0x04)
    a.ld_a_n(0x73); a.out_n_a(0x05)
    a.ld_a_n(0x1A); a.out_n_a(0x04)
    a.ld_a_n(0x65); a.out_n_a(0x05)

    # Volume
    a.ld_a_n(0x1B); a.out_n_a(0x04)
    a.ld_a_n(0xFF); a.out_n_a(0x05)

    # Start playback
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x80); a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # ADPCM-B STOP
    # ================================================================
    ADPCMB_STOP = a.here()
    a.patch_jp(jp_adpcmb_stop, ADPCMB_STOP)

    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM SET PANNING (B = channel 0-3, param: 0=L, 1=C, 2=R)
    # ================================================================
    FM_SET_PAN = a.here()
    a.patch_jp(jp_fmpan, FM_SET_PAN)

    # Convert param to L/R bits
    a.ld_a_mem(RAM_PARAM)
    a.cp_n(0x00)
    jr_fn_l = a.jr_nz_ph()
    a.ld_a_n(0x80)          # L only
    jr_fp_set = a.jr_ph()
    a.patch_jr(jr_fn_l, a.here())
    a.cp_n(0x02)
    jr_fn_r = a.jr_nz_ph()
    a.ld_a_n(0x40)          # R only
    jr_fp_set2 = a.jr_ph()
    a.patch_jr(jr_fn_r, a.here())
    a.ld_a_n(0xC0)          # Center
    a.patch_jr(jr_fp_set, a.here())
    a.patch_jr(jr_fp_set2, a.here())

    # Store in RAM
    a.ld_e_a()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_e()
    a.ld_hl_a()

    # Write reg $B4+ch_offset via correct port
    # YM2610 FM uses channels 1,2,4,5 so offset = (ch & 1) + 1
    a.ld_a_b()
    a.and_n(0x01)
    a.inc_a()                # offset 1 or 2
    a.add_a_n(0xB4)
    a.ld_d_a()               # D = register

    a.ld_a_b()
    a.and_n(0x02)
    jr_fp_pa = a.jr_z_ph()
    # Port B
    a.ld_a_d(); a.out_n_a(0x06)
    a.ld_a_e(); a.out_n_a(0x07)
    jr_fp_pd = a.jr_ph()
    a.patch_jr(jr_fp_pa, a.here())
    # Port A
    a.ld_a_d(); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.patch_jr(jr_fp_pd, a.here())

    a.jp(NMI_DONE)

    # ================================================================
    # ADPCM-A SET PANNING (B = channel 0-5, param: 0=L, 1=C, 2=R)
    # ================================================================
    ADPCMA_SET_PAN = a.here()
    a.patch_jp(jp_adpcmapan, ADPCMA_SET_PAN)

    a.ld_a_mem(RAM_PARAM)
    a.cp_n(0x00)
    jr_ap_l = a.jr_nz_ph()
    a.ld_a_n(0x80)
    jr_ap_set = a.jr_ph()
    a.patch_jr(jr_ap_l, a.here())
    a.cp_n(0x02)
    jr_ap_r = a.jr_nz_ph()
    a.ld_a_n(0x40)
    jr_ap_set2 = a.jr_ph()
    a.patch_jr(jr_ap_r, a.here())
    a.ld_a_n(0xC0)
    a.patch_jr(jr_ap_set, a.here())
    a.patch_jr(jr_ap_set2, a.here())

    # Store in RAM
    a.ld_e_a()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_ADPCMA_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_e()
    a.ld_hl_a()

    a.jp(NMI_DONE)

    # ================================================================
    # PLAY SONG (B = song index, called from NMI $50+N)
    # ================================================================
    PLAY_SONG = a.here()
    a.patch_jp(jp_play_song, PLAY_SONG)

    # Bounds check: B < num_songs
    a.ld_a_b()
    a.cp_n(num_songs)
    jr_song_ok = a.jr_c_ph()
    a.jp(NMI_DONE)
    a.patch_jr(jr_song_ok, a.here())

    # Look up song table: SONG_TABLE + B * 5
    # Compute B * 5 = B * 4 + B
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)  # HL = B
    a.add_hl_hl()             # HL = B*2
    a.add_hl_hl()             # HL = B*4
    a.ld_d_n(0); a.ld_e_b()
    a.add_hl_de()             # HL = B*5
    a.ld_de_nn(SONG_TABLE)
    a.add_hl_de()             # HL = SONG_TABLE + B*5

    # Read song entry: [start_lo, start_hi, length_lo, length_hi, tempo]
    a.ld_e_hl(); a.inc_hl()   # E = start_lo
    a.ld_d_hl(); a.inc_hl()   # D = start_hi
    # Store start address
    a.ld_a_e(); a.ld_mem_a(RAM_SEQ_START_LO)
    a.ld_a_d(); a.ld_mem_a(RAM_SEQ_START_HI)
    # Also set current row pointer to start
    a.ld_a_e(); a.ld_mem_a(RAM_SEQ_ROW_LO)
    a.ld_a_d(); a.ld_mem_a(RAM_SEQ_ROW_HI)

    # Read length
    a.ld_c_hl(); a.inc_hl()   # C = len_lo
    a.ld_b_hl(); a.inc_hl()   # B = len_hi
    # End address = start + length
    # DE = start, BC = length
    a.push_hl()               # save HL (points to tempo byte)
    a.ld_h_d(); a.ld_l_e()    # HL = start
    a.add_hl_bc()             # HL = start + length = end
    a.ld_a_l(); a.ld_mem_a(RAM_SEQ_END_LO)
    a.ld_a_h(); a.ld_mem_a(RAM_SEQ_END_HI)
    a.pop_hl()

    # Read tempo
    a.ld_a_hl()
    a.ld_mem_a(RAM_SEQ_TICK_RATE)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)  # start counting from full tempo

    # Clear sequencer patch state
    a.xor_a()
    a.ld_mem_a(RAM_SEQ_FM_PATCH0)
    a.ld_mem_a(RAM_SEQ_FM_PATCH1)
    a.ld_mem_a(RAM_SEQ_FM_PATCH2)
    a.ld_mem_a(RAM_SEQ_FM_PATCH3)

    # Set playing = 1
    a.ld_a_n(0x01)
    a.ld_mem_a(RAM_SEQ_PLAYING)

    a.jp(NMI_DONE)

    # ================================================================
    # SEQ_TICK: Advance one row of the sequencer
    # Called from IRQ handler. Uses AF, BC, DE, HL (all saved by caller).
    # Reads 8 bytes from current row pointer, processes each channel.
    # ================================================================
    SEQ_TICK = a.here()
    a.patch_call(jp_seq_tick_call, SEQ_TICK)

    # Load current row pointer into DE
    a.ld_a_mem(RAM_SEQ_ROW_LO)
    a.ld_e_a()
    a.ld_a_mem(RAM_SEQ_ROW_HI)
    a.ld_d_a()

    # Check first byte for end marker ($FF)
    a.ld_a_de()
    a.cp_n(SEQ_END)
    jr_not_end = a.jr_nz_ph()
    # End of song: loop back to start
    a.ld_a_mem(RAM_SEQ_START_LO)
    a.ld_mem_a(RAM_SEQ_ROW_LO)
    a.ld_e_a()
    a.ld_a_mem(RAM_SEQ_START_HI)
    a.ld_mem_a(RAM_SEQ_ROW_HI)
    a.ld_d_a()
    a.patch_jr(jr_not_end, a.here())

    # Now DE = current row pointer (valid data)
    # Process 8 columns: FM0-3 (cols 0-3), SSG0-2 (cols 4-6), ADPCM-A (col 7)

    # --- FM Channel 0 (col 0) ---
    a.ld_a_de()               # A = byte for FM ch0
    a.ld_b_n(0)               # B = FM channel 0
    a.push_de()
    a.call(0x0000)            # CALL SEQ_PROCESS_FM (patched below)
    jp_seq_fm_call_0 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- FM Channel 1 (col 1) ---
    a.ld_a_de()
    a.ld_b_n(1)
    a.push_de()
    a.call(0x0000)
    jp_seq_fm_call_1 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- FM Channel 2 (col 2) ---
    a.ld_a_de()
    a.ld_b_n(2)
    a.push_de()
    a.call(0x0000)
    jp_seq_fm_call_2 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- FM Channel 3 (col 3) ---
    a.ld_a_de()
    a.ld_b_n(3)
    a.push_de()
    a.call(0x0000)
    jp_seq_fm_call_3 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- SSG Channel 0 (col 4) ---
    a.ld_a_de()
    a.ld_b_n(0)
    a.push_de()
    a.call(0x0000)
    jp_seq_ssg_call_0 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- SSG Channel 1 (col 5) ---
    a.ld_a_de()
    a.ld_b_n(1)
    a.push_de()
    a.call(0x0000)
    jp_seq_ssg_call_1 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- SSG Channel 2 (col 6) ---
    a.ld_a_de()
    a.ld_b_n(2)
    a.push_de()
    a.call(0x0000)
    jp_seq_ssg_call_2 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- ADPCM-A (col 7) ---
    a.ld_a_de()
    a.ld_b_a()                # B = sample index
    a.push_de()
    a.call(0x0000)
    jp_seq_adpcm_call = a.pc - 3
    a.pop_de()
    a.inc_de()

    # Update row pointer (DE now points to next row)
    a.ld_a_e(); a.ld_mem_a(RAM_SEQ_ROW_LO)
    a.ld_a_d(); a.ld_mem_a(RAM_SEQ_ROW_HI)

    a.ret()

    # ================================================================
    # SEQ_PROCESS_FM: Process one FM column byte
    # A = byte value, B = FM channel (0-3)
    # $00 = sustain, $01 = key-off, $02-$7F = note-on, $80-$BF = set patch
    # ================================================================
    SEQ_PROCESS_FM = a.here()
    for addr in [jp_seq_fm_call_0, jp_seq_fm_call_1,
                 jp_seq_fm_call_2, jp_seq_fm_call_3]:
        a.patch_call(addr, SEQ_PROCESS_FM)

    # Check for sustain ($00)
    a.or_a()
    jr_fm_not_sustain = a.jr_nz_ph()
    a.ret()
    a.patch_jr(jr_fm_not_sustain, a.here())

    # Check for key-off ($01)
    a.cp_n(SEQ_KEYOFF)
    jr_fm_not_keyoff = a.jr_nz_ph()
    # Key-off: look up keyoff table
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(KEYOFF_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()               # key-off value
    a.ld_e_a()
    a.ld_a_n(0x28); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.ret()
    a.patch_jr(jr_fm_not_keyoff, a.here())

    # Check for set patch ($80-$BF)
    a.cp_n(0x80)
    jr_fm_not_patch = a.jr_c_ph()
    a.cp_n(0xC0)
    jr_fm_patch_too_high = a.jr_nc_ph()
    # Store patch: A & 0x3F = patch index
    a.and_n(0x3F)
    # Store in RAM_SEQ_FM_PATCHx (x = B)
    a.push_af()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_SEQ_FM_PATCH0)
    a.add_hl_de()
    a.pop_de()
    a.pop_af()
    a.ld_hl_a()               # store patch index
    # Also store in the main RAM_FM_PATCH for key-on to use
    a.push_af()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.pop_de()
    a.pop_af()
    a.ld_hl_a()
    a.ret()
    a.patch_jr(jr_fm_not_patch, a.here())
    a.patch_jr(jr_fm_patch_too_high, a.here())

    # Note-on ($02-$7F): A = MIDI note number
    # Full inline FM note-on with patch register write
    a.ld_mem_a(RAM_PARAM)     # store note

    # Save channel in RAM_TEMP+2
    a.ld_a_b()
    a.ld_mem_a(RAM_TEMP + 2)

    # --- Load patch for this channel ---
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()               # A = patch index
    a.ld_mem_a(RAM_TEMP)      # save patch index

    # Bounds check patch
    a.cp_n(NUM_FM_PATCHES)
    jr_seq_pok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_seq_pok, a.here())

    # Compute patch pointer: HL = FM_PATCH_TABLE + A*26
    a.ld_c_a()
    a.ld_h_n(0); a.ld_l_a()
    a.add_hl_hl()             # *2
    a.push_hl()
    a.add_hl_hl()             # *4
    a.add_hl_hl()             # *8
    a.push_hl()
    a.add_hl_hl()             # *16
    a.pop_de()
    a.add_hl_de()             # *24
    a.pop_de()
    a.add_hl_de()             # *26
    a.ld_de_nn(FM_PATCH_TABLE)
    a.add_hl_de()             # HL = patch data pointer

    # Restore channel into B
    a.ld_a_mem(RAM_TEMP + 2)
    a.ld_b_a()

    # Determine port and ch_offset
    a.ld_a_b()
    a.and_n(0x01)
    a.inc_a()
    a.ld_mem_a(RAM_TEMP + 1)  # ch_offset

    a.ld_a_b()
    a.and_n(0x02)
    jr_seq_porta = a.jr_z_ph()
    a.ld_c_n(0x06)            # Port B addr
    a.ld_d_n(0x07)            # Port B data
    jr_seq_port_done = a.jr_ph()
    a.patch_jr(jr_seq_porta, a.here())
    a.ld_c_n(0x04)            # Port A addr
    a.ld_d_n(0x05)            # Port A data
    a.patch_jr(jr_seq_port_done, a.here())

    # Write 24 operator registers (same as FM_KEY_ON)
    for reg_base in [0x30, 0x40, 0x50, 0x60, 0x70, 0x80]:
        for op_off in [0, 8, 4, 12]:
            a.ld_a_hl()
            a.push_af()
            a.ld_a_mem(RAM_TEMP + 1)
            a.add_a_n(reg_base + op_off)
            a.out_c_a()
            a.pop_af()
            a.ld_e_c(); a.ld_c_d()
            a.out_c_a()
            a.ld_c_e()
            a.inc_hl()

    # Write FB_ALG
    a.ld_a_hl()
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB0)
    a.out_c_a()
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()
    a.ld_c_e()
    a.inc_hl()

    # Write LR_AMS_PMS with panning
    a.ld_a_hl()
    a.and_n(0x3F)
    a.ld_e_a()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()
    a.and_n(0xC0)
    a.or_e()
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB4)
    a.out_c_a()
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()
    a.ld_c_e()

    # --- Set frequency ---
    a.ld_a_mem(RAM_PARAM)
    a.ld_e_a()
    a.ld_d_n(0)

    seq_fm_div12 = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_seq_fm_div_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)
    a.patch_jr(a.here() - 2, seq_fm_div12)
    a.patch_jr(jr_seq_fm_div_done, a.here())

    # D = octave, E = semitone. Look up F-number.
    a.push_de()
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()
    a.push_de()
    a.ld_de_nn(FM_FNUM_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_c_hl()               # C = fnum_lo
    a.inc_hl()
    a.ld_a_hl()               # A = fnum_hi
    a.ld_l_a()                # L = fnum_hi
    a.pop_de()                # D = octave

    # Compute block_fnum_hi
    a.ld_a_d()
    a.and_n(0x07)
    a.rlca(); a.rlca(); a.rlca()
    a.and_n(0x38)
    a.or_l()
    a.ld_d_a()                # D = block_fnum_hi
    a.ld_e_c()                # E = fnum_lo

    # Write freq regs
    a.ld_a_mem(RAM_TEMP + 1)  # ch_offset
    a.ld_c_a()

    a.ld_a_b()
    a.and_n(0x02)
    jr_seq_ffreq_pa = a.jr_z_ph()
    # Port B
    a.ld_a_c(); a.add_a_n(0xA4); a.out_n_a(0x06)
    a.ld_a_d(); a.out_n_a(0x07)
    a.ld_a_c(); a.add_a_n(0xA0); a.out_n_a(0x06)
    a.ld_a_e(); a.out_n_a(0x07)
    jr_seq_ffreq_done = a.jr_ph()
    a.patch_jr(jr_seq_ffreq_pa, a.here())
    # Port A
    a.ld_a_c(); a.add_a_n(0xA4); a.out_n_a(0x04)
    a.ld_a_d(); a.out_n_a(0x05)
    a.ld_a_c(); a.add_a_n(0xA0); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.patch_jr(jr_seq_ffreq_done, a.here())

    # Key-on
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(KEYON_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()
    a.ld_c_a()
    a.ld_a_n(0x28); a.out_n_a(0x04)
    a.ld_a_c(); a.out_n_a(0x05)

    a.ret()

    # ================================================================
    # SEQ_PROCESS_SSG: Process one SSG column byte
    # A = byte value, B = SSG channel (0-2)
    # $00 = sustain, $01 = key-off, $02-$7F = note-on
    # ================================================================
    SEQ_PROCESS_SSG = a.here()
    for addr in [jp_seq_ssg_call_0, jp_seq_ssg_call_1,
                 jp_seq_ssg_call_2]:
        a.patch_call(addr, SEQ_PROCESS_SSG)

    # Check sustain
    a.or_a()
    jr_ssg_not_sustain = a.jr_nz_ph()
    a.ret()
    a.patch_jr(jr_ssg_not_sustain, a.here())

    # Check key-off
    a.cp_n(SEQ_KEYOFF)
    jr_ssg_not_keyoff = a.jr_nz_ph()
    # Volume = 0
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.xor_a()
    a.out_n_a(0x05)
    a.ret()
    a.patch_jr(jr_ssg_not_keyoff, a.here())

    # Note-on ($02-$7F): A = MIDI note
    # Compute period and write to SSG regs
    a.ld_mem_a(RAM_PARAM)
    a.ld_e_a()
    a.ld_d_n(0)

    seq_ssg_div = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_seq_ssg_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)
    a.patch_jr(a.here() - 2, seq_ssg_div)
    a.patch_jr(jr_seq_ssg_done, a.here())

    # D = octave, E = semitone
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()
    a.push_de()
    a.ld_de_nn(SSG_PERIOD_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.push_de()
    a.ld_e_hl(); a.inc_hl()
    a.ld_d_hl()
    a.ld_h_d(); a.ld_l_e()    # HL = period
    a.pop_de()                 # D = octave

    # Adjust period for octave
    a.ld_a_d()
    a.cp_n(4)
    jr_seq_oct_eq = a.jr_z_ph()
    jr_seq_oct_hi = a.jr_nc_ph()

    # Octave < 4: shift left
    a.ld_a_n(4)
    a.sub_d()
    a.ld_d_a()
    seq_ssg_shl = a.here()
    a.add_hl_hl()
    a.dec_d()
    jr_seq_shl = a.jr_nz_ph()
    a.patch_jr(jr_seq_shl, seq_ssg_shl)
    jr_seq_adj_done = a.jr_ph()

    a.patch_jr(jr_seq_oct_hi, a.here())
    # Octave > 4: shift right
    a.ld_a_d()
    a.sub_n(4)
    a.ld_d_a()
    seq_ssg_shr = a.here()
    a.srl_h()
    a.rr_l()
    a.dec_d()
    jr_seq_shr = a.jr_nz_ph()
    a.patch_jr(jr_seq_shr, seq_ssg_shr)

    a.patch_jr(jr_seq_oct_eq, a.here())
    a.patch_jr(jr_seq_adj_done, a.here())

    # HL = period, B = channel
    a.ld_a_b()
    a.add_a_a()               # A = channel * 2
    a.ld_e_a()
    a.out_n_a(0x04)
    a.ld_a_l()
    a.out_n_a(0x05)
    a.ld_a_e()
    a.inc_a()
    a.out_n_a(0x04)
    a.ld_a_h()
    a.and_n(0x0F)
    a.out_n_a(0x05)

    # Mixer: enable tone
    a.ld_a_n(0x07); a.out_n_a(0x04)
    a.ld_a_n(0x38); a.out_n_a(0x05)

    # Volume
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.ld_a_n(0x0F)
    a.out_n_a(0x05)

    a.ret()

    # ================================================================
    # SEQ_PROCESS_ADPCM: Process ADPCM-A column byte
    # B = sample byte (raw value from column)
    # $00 = no trigger, anything else = sample index to trigger
    # ================================================================
    SEQ_PROCESS_ADPCM = a.here()
    a.patch_call(jp_seq_adpcm_call, SEQ_PROCESS_ADPCM)

    # Check for no-trigger ($00)
    a.ld_a_b()
    a.or_a()
    jr_adpcm_not_zero = a.jr_nz_ph()
    a.ret()
    a.patch_jr(jr_adpcm_not_zero, a.here())

    # Check bounds
    a.cp_n(NUM_SAMPLES)
    jr_adpcm_ok = a.jr_c_ph()
    a.ret()
    a.patch_jr(jr_adpcm_ok, a.here())

    # Trigger ADPCM-A sample B on channel 0 (sequencer always uses ch 0)
    # HL = sample table + B*4
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl(); a.add_hl_hl()
    a.ld_de_nn(SAMPLE_TABLE)
    a.add_hl_de()

    a.ld_e_hl(); a.inc_hl()   # start_lo
    a.ld_d_hl(); a.inc_hl()   # start_hi
    a.ld_c_hl(); a.inc_hl()   # end_lo
    a.ld_b_hl()               # end_hi

    a.push_bc()               # save end addr
    a.push_de()               # save start addr

    # Dump ch0: reg $00 = $81
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0x81); a.out_n_a(0x07)

    # Start addr: regs $10+0, $18+0
    a.ld_a_n(0x10); a.out_n_a(0x06)
    a.pop_de()
    a.ld_a_e(); a.out_n_a(0x07)
    a.ld_a_n(0x18); a.out_n_a(0x06)
    a.ld_a_d(); a.out_n_a(0x07)

    # End addr: regs $20+0, $28+0
    a.pop_bc()
    a.ld_a_n(0x20); a.out_n_a(0x06)
    a.ld_a_c(); a.out_n_a(0x07)
    a.ld_a_n(0x28); a.out_n_a(0x06)
    a.ld_a_b(); a.out_n_a(0x07)

    # Volume + pan: reg $08+0 = $DF (center + vol 31)
    a.ld_a_n(0x08); a.out_n_a(0x06)
    a.ld_a_n(0xDF); a.out_n_a(0x07)

    # Trigger ch0: reg $00 = $01
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0x01); a.out_n_a(0x07)

    a.ret()

    # ================================================================
    # Patch all done_patches
    # ================================================================
    for jp_addr in done_patches:
        a.patch_jp(jp_addr, NMI_DONE)

    # ================================================================
    # Summary
    # ================================================================
    print(f"NeoSynth v2.0 Driver Map:")
    print(f"  Init:          0x0100")
    print(f"  Main loop:     0x{MAIN_LOOP:04X}")
    print(f"  IRQ handler:   0x0080")
    print(f"  IRQ done:      0x{IRQ_DONE:04X}")
    print(f"  NMI handler:   0x0280")
    print(f"  NMI done:      0x{NMI_DONE:04X}")
    print(f"  Stop All:      0x{STOP_ALL:04X}")
    print(f"  Play Song:     0x{PLAY_SONG:04X}")
    print(f"  Seq Tick:      0x{SEQ_TICK:04X}")
    print(f"  Seq FM:        0x{SEQ_PROCESS_FM:04X}")
    print(f"  Seq SSG:       0x{SEQ_PROCESS_SSG:04X}")
    print(f"  Seq ADPCM:     0x{SEQ_PROCESS_ADPCM:04X}")
    print(f"  FM Key-On:     0x{FM_KEY_ON:04X}")
    print(f"  FM Key-Off:    0x{FM_KEY_OFF:04X}")
    print(f"  FM Load Patch: 0x{FM_LOAD_PATCH:04X}")
    print(f"  SSG Key-On:    0x{SSG_KEY_ON:04X}")
    print(f"  SSG Key-Off:   0x{SSG_KEY_OFF:04X}")
    print(f"  ADPCM-A Trig:  0x{ADPCMA_TRIGGER:04X}")
    print(f"  ADPCM-B Play:  0x{ADPCMB_PLAY:04X}")
    print(f"  ADPCM-B Stop:  0x{ADPCMB_STOP:04X}")
    print(f"  FM Set Pan:    0x{FM_SET_PAN:04X}")
    print(f"  ADPCM-A Pan:   0x{ADPCMA_SET_PAN:04X}")
    print(f"  Sample table:  0x{SAMPLE_TABLE:04X} ({NUM_SAMPLES} entries)")
    print(f"  FM Fnum table: 0x{FM_FNUM_TABLE:04X}")
    print(f"  SSG Period tbl:0x{SSG_PERIOD_TABLE:04X}")
    print(f"  FM Patch table:0x{FM_PATCH_TABLE:04X} ({NUM_FM_PATCHES} patches)")
    print(f"  Song table:    0x{SONG_TABLE:04X} ({num_songs} songs)")
    print(f"  Song data:     0x{SONG_DATA_BASE:04X}")
    print(f"  Code end:      0x{a.pc:04X}")

    return bytes(a.code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--output', required=True)
    args = parser.parse_args()
    mrom = build_driver()
    with open(args.output, 'wb') as f:
        f.write(mrom)
    print(f"Written: {args.output}")


if __name__ == '__main__':
    main()
