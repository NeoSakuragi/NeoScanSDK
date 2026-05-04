#!/usr/bin/env python3
"""Build a NeoSynth Z80 sound driver M-ROM.

The driver plays a tick-based matrix format:
  14 bytes per row (one per channel), ticked at 16th-note rate.

  Channels: FM1 FM2 FM3 FM4 SSG1 SSG2 SSG3 A1 A2 A3 A4 A5 A6 B1

  Byte values per channel:
    0x00 = sustain (no change)
    0x01 = key off
    0x02-0x7F = note on (MIDI note number, C4=60=0x3C)
    0x80+  = reserved for commands (future)

The Z80 driver:
  - Boots, inits YM2610, enables NMI for 68K commands
  - Timer A IRQ fires at the tick rate
  - Each tick: read 14 bytes, write YM2610 registers per channel
  - Handles 68K commands: 0x01=reset, 0x03=stop, 0x07=unlock, 0x20+=play song
"""

import struct, sys, os

# YM2610 FM F-number table (12 semitones, octave 0)
# F-num = freq * 2^20 / (clock / 144) for YM2610 at 4MHz
FM_FNUMS = [618, 627, 636, 645, 655, 664, 674, 683, 694, 704, 714, 724]

# Z80 driver code
def build_driver(song_data, num_rows, tick_rate_hz=8, num_fm_patches=0, fm_patches=b''):
    """Build complete Z80 driver binary.

    song_data: bytes, 14 bytes per row, num_rows rows
    tick_rate_hz: ticks per second (8 = 16th notes at 120bpm)
    """

    # Timer A period: fires at tick_rate_hz
    # YM2610 Timer A is 10-bit, period = 1024 - N
    # Timer A freq = clock / (144 * 2 * (1024 - N))
    # clock = 4000000 (4 MHz)
    # We want ~8 Hz for 16th notes at 120 BPM
    # N = 1024 - (4000000 / (144 * 2 * tick_rate_hz))
    timer_a_val = int(1024 - (4000000 / (144 * 2 * tick_rate_hz)))
    if timer_a_val < 0: timer_a_val = 0
    if timer_a_val > 1023: timer_a_val = 1023
    timer_a_hi = (timer_a_val >> 2) & 0xFF
    timer_a_lo = timer_a_val & 0x03

    # Song data will be placed at 0x1000 in the fixed bank
    SONG_ADDR = 0x1000
    ROW_SIZE = 14

    # FM frequency table at 0x0200
    FTABLE_ADDR = 0x0200

    # --- Build Z80 code ---
    code = bytearray(0x8000)  # 32KB fixed bank

    # Vector table
    # 0x0000: JP init
    code[0] = 0xC3  # JP
    code[1] = 0x80  # init at 0x0080
    code[2] = 0x00

    # 0x0008: RST 08 - unused
    code[0x08] = 0xC9  # RET

    # 0x0038: IRQ handler (IM1) - Timer A tick
    code[0x38] = 0xC3  # JP
    code[0x39] = 0x00  # irq_handler at 0x0300
    code[0x3A] = 0x03

    # 0x0066: NMI handler - 68K command
    code[0x66] = 0xC3  # JP
    code[0x67] = 0x00  # nmi_handler at 0x0400
    code[0x68] = 0x04

    # Driver signature
    sig = b"NeoSynth Driver v0.1 2026/05/05"
    code[0x40:0x40+len(sig)] = sig

    # --- FM frequency table at 0x0200 (24 bytes = 12 x 2) ---
    for i, fnum in enumerate(FM_FNUMS):
        struct.pack_into('<H', code, FTABLE_ADDR + i*2, fnum)

    # --- Init routine at 0x0080 ---
    pc = 0x0080

    def emit(b):
        nonlocal pc
        code[pc] = b
        pc += 1

    def emit_bytes(bs):
        for b in bs:
            emit(b)

    # LD SP, 0xFFFC
    emit_bytes([0x31, 0xFC, 0xFF])
    # IM 1
    emit_bytes([0xED, 0x56])
    # DI
    emit(0xF3)

    # Clear RAM (0xF800-0xFFFF)
    # XOR A; LD (F800),A; LD HL,F800; LD DE,F801; LD BC,07FF; LDIR
    emit(0xAF)  # XOR A
    emit_bytes([0x32, 0x00, 0xF8])  # LD (F800),A
    emit_bytes([0x21, 0x00, 0xF8])  # LD HL,F800
    emit_bytes([0x11, 0x01, 0xF8])  # LD DE,F801
    emit_bytes([0x01, 0xFF, 0x07])  # LD BC,07FF
    emit_bytes([0xED, 0xB0])        # LDIR

    # Init YM2610 - silence all
    # Write 0x00 to ADPCM-A total level (reg 0x01 via port pair B)
    # Port A: addr=$04, data=$05  (FM ch1-2 + SSG)
    # Port B: addr=$06, data=$07  (FM ch3-4 + ADPCM)

    # Key off all FM channels
    for ch in range(4):
        emit_bytes([0x3E, 0x28])  # LD A, 0x28 (key on/off reg)
        emit_bytes([0xD3, 0x04])  # OUT (04), A  (address)
        emit_bytes([0x3E, ch])    # LD A, ch (key off, no operators)
        emit_bytes([0xD3, 0x05])  # OUT (05), A  (data)

    # Set SSG mixer to all off
    emit_bytes([0x3E, 0x07])  # LD A, 0x07 (mixer reg)
    emit_bytes([0xD3, 0x04])  # OUT (04), A
    emit_bytes([0x3E, 0x3F])  # LD A, 0x3F (all tone+noise off)
    emit_bytes([0xD3, 0x05])  # OUT (05), A

    # ADPCM-A dump all channels
    emit_bytes([0x3E, 0x00])  # LD A, 0x00 (ADPCM-A control)
    emit_bytes([0xD3, 0x06])  # OUT (06), A
    emit_bytes([0x3E, 0xBF])  # LD A, 0xBF (dump all 6 + reset)
    emit_bytes([0xD3, 0x07])  # OUT (07), A

    # Set ADPCM-A master volume
    emit_bytes([0x3E, 0x01])  # reg 0x01
    emit_bytes([0xD3, 0x06])
    emit_bytes([0x3E, 0x3F])  # max volume
    emit_bytes([0xD3, 0x07])

    # Set Timer A value
    emit_bytes([0x3E, 0x24])  # reg 0x24 (Timer A high)
    emit_bytes([0xD3, 0x04])
    emit_bytes([0x3E, timer_a_hi])
    emit_bytes([0xD3, 0x05])
    emit_bytes([0x3E, 0x25])  # reg 0x25 (Timer A low)
    emit_bytes([0xD3, 0x04])
    emit_bytes([0x3E, timer_a_lo])
    emit_bytes([0xD3, 0x05])

    # Enable Timer A + IRQ: reg 0x27, value = 0x15 (load + enable + reset flag)
    emit_bytes([0x3E, 0x27])
    emit_bytes([0xD3, 0x04])
    emit_bytes([0x3E, 0x15])
    emit_bytes([0xD3, 0x05])

    # Init row pointer in RAM
    # F800-F801: current row address (16-bit)
    # F802: playing flag
    # F803: song command from 68K
    emit_bytes([0x21, SONG_ADDR & 0xFF, (SONG_ADDR >> 8) & 0xFF])  # LD HL, SONG_ADDR
    emit_bytes([0x22, 0x00, 0xF8])  # LD (F800), HL
    emit_bytes([0x3E, 0x00])
    emit_bytes([0x32, 0x02, 0xF8])  # playing = 0

    # Set default FM algorithm+feedback for all 4 channels
    # Algo 4 (two parallel pairs), feedback 5
    for ch_pair in range(2):
        port_addr = 0x04 if ch_pair == 0 else 0x06
        port_data = 0x05 if ch_pair == 0 else 0x07
        for ch in range(2):
            emit_bytes([0x3E, 0xB0 + ch])  # reg 0xB0+ch (FB/ALG)
            emit_bytes([0xD3, port_addr])
            emit_bytes([0x3E, 0x2C])       # FB=5, ALG=4
            emit_bytes([0xD3, port_data])
            # Set TL for all 4 operators (volume)
            for op in range(4):
                op_offset = [0, 8, 4, 12][op]  # YM2610 operator order
                emit_bytes([0x3E, 0x40 + op_offset + ch])  # TL reg
                emit_bytes([0xD3, port_addr])
                emit_bytes([0x3E, 0x10 if op == 3 else 0x7F])  # carrier loud, modulators quiet
                emit_bytes([0xD3, port_data])
            # Set DT/MUL for operators
            for op in range(4):
                op_offset = [0, 8, 4, 12][op]
                emit_bytes([0x3E, 0x30 + op_offset + ch])  # DT/MUL reg
                emit_bytes([0xD3, port_addr])
                emit_bytes([0x3E, 0x01])  # DT=0, MUL=1
                emit_bytes([0xD3, port_data])
            # Set AR for all operators (fast attack)
            for op in range(4):
                op_offset = [0, 8, 4, 12][op]
                emit_bytes([0x3E, 0x50 + op_offset + ch])  # KS/AR reg
                emit_bytes([0xD3, port_addr])
                emit_bytes([0x3E, 0x1F])  # AR=31 (fastest)
                emit_bytes([0xD3, port_data])
            # Set DR
            for op in range(4):
                op_offset = [0, 8, 4, 12][op]
                emit_bytes([0x3E, 0x60 + op_offset + ch])
                emit_bytes([0xD3, port_addr])
                emit_bytes([0x3E, 0x05])  # moderate decay
                emit_bytes([0xD3, port_data])
            # Set SR
            for op in range(4):
                op_offset = [0, 8, 4, 12][op]
                emit_bytes([0x3E, 0x70 + op_offset + ch])
                emit_bytes([0xD3, port_addr])
                emit_bytes([0x3E, 0x02])
                emit_bytes([0xD3, port_data])
            # Set SL/RR
            for op in range(4):
                op_offset = [0, 8, 4, 12][op]
                emit_bytes([0x3E, 0x80 + op_offset + ch])
                emit_bytes([0xD3, port_addr])
                emit_bytes([0x3E, 0xF6])  # SL=15, RR=6
                emit_bytes([0xD3, port_data])
            # Set L/R output (both speakers)
            emit_bytes([0x3E, 0xB4 + ch])
            emit_bytes([0xD3, port_addr])
            emit_bytes([0x3E, 0xC0])  # L+R on
            emit_bytes([0xD3, port_data])

    # Enable NMI
    emit_bytes([0xD3, 0x08])  # OUT (08), A — enable NMI
    # EI
    emit(0xFB)

    # Main loop — just kick watchdog and wait for interrupts
    main_loop = pc
    emit_bytes([0x3A, 0x03, 0xF8])  # LD A, (F803) — check 68K command
    emit(0xB7)                       # OR A
    emit_bytes([0x28, 0x0E])         # JR Z, skip (no command)

    # Handle command
    emit_bytes([0xFE, 0x03])         # CP 3 (stop)
    emit_bytes([0x28, 0x06])         # JR Z, do_stop
    emit_bytes([0xFE, 0x07])         # CP 7 (unlock/play)
    emit_bytes([0x28, 0x04])         # JR Z, do_play
    emit_bytes([0x18, 0x06])         # JR skip_cmd

    # do_stop:
    emit_bytes([0xAF])               # XOR A
    emit_bytes([0x32, 0x02, 0xF8])   # LD (F802), A — playing=0
    emit_bytes([0x18, 0x03])         # JR clear_cmd

    # do_play:
    emit_bytes([0x3E, 0x01])
    emit_bytes([0x32, 0x02, 0xF8])   # playing=1

    # clear_cmd:
    emit(0xAF)                       # XOR A
    emit_bytes([0x32, 0x03, 0xF8])   # clear command

    # skip:
    emit_bytes([0xC3, main_loop & 0xFF, (main_loop >> 8) & 0xFF])  # JP main_loop

    # --- IRQ handler at 0x0300 ---
    pc = 0x0300

    # Save registers
    emit(0xF5)  # PUSH AF
    emit(0xC5)  # PUSH BC
    emit(0xD5)  # PUSH DE
    emit(0xE5)  # PUSH HL

    # Reset Timer A flag: write 0x15 to reg 0x27
    emit_bytes([0x3E, 0x27])
    emit_bytes([0xD3, 0x04])
    emit_bytes([0x3E, 0x15])
    emit_bytes([0xD3, 0x05])

    # Check if playing
    emit_bytes([0x3A, 0x02, 0xF8])  # LD A, (F802)
    emit(0xB7)                       # OR A
    emit_bytes([0xCA, 0xF0, 0x03])   # JP Z, irq_done

    # Load row pointer
    emit_bytes([0x2A, 0x00, 0xF8])  # LD HL, (F800)

    # --- Process FM channels 1-2 (port pair A: $04/$05) ---
    for ch in range(2):
        emit_bytes([0x7E])           # LD A, (HL) — read channel byte
        emit_bytes([0x23])           # INC HL
        emit(0xB7)                   # OR A
        emit_bytes([0x28, 42])       # JR Z, next_ch (sustain — skip)
        emit_bytes([0xFE, 0x01])     # CP 1
        emit_bytes([0x20, 0x06])     # JR NZ, note_on
        # Key off
        emit_bytes([0x3E, 0x28])     # LD A, 0x28
        emit_bytes([0xD3, 0x04])     # OUT (04), A
        emit_bytes([0x3E, ch])       # LD A, ch
        emit_bytes([0xD3, 0x05])     # OUT (05), A
        emit_bytes([0x18, 30])       # JR next_ch
        # note_on:
        emit(0xD5)                   # PUSH DE
        # Calculate semitone and octave from MIDI note
        emit_bytes([0xD6, 24])       # SUB 24 (MIDI note 24 = C1)
        emit(0x4F)                   # LD C, A
        emit_bytes([0xE6, 0x0F])     # AND 0x0F... no, need mod 12
        # A = note - 24. Divide by 12 for octave, mod 12 for semitone
        emit_bytes([0x06, 0x00])     # LD B, 0 (octave counter)
        # div12 loop:
        emit_bytes([0xFE, 12])       # CP 12
        emit_bytes([0x38, 0x04])     # JR C, done_div
        emit_bytes([0xD6, 12])       # SUB 12
        emit(0x04)                   # INC B
        emit_bytes([0x18, 0xF8])     # JR div12
        # done_div: A=semitone, B=octave
        # Look up F-number
        emit(0x87)                   # ADD A,A (semitone*2 for table index)
        emit(0x5F)                   # LD E, A
        emit_bytes([0x16, 0x00])     # LD D, 0
        emit_bytes([0xDD, 0x21, FTABLE_ADDR & 0xFF, (FTABLE_ADDR >> 8) & 0xFF])  # LD IX, FTABLE
        emit_bytes([0xDD, 0x19])     # ADD IX, DE
        emit_bytes([0xDD, 0x5E, 0x00])  # LD E, (IX+0) — F-num low
        emit_bytes([0xDD, 0x56, 0x01])  # LD D, (IX+1) — F-num high
        # Write F-number low: reg 0xA0+ch
        emit_bytes([0x3E, 0xA0 + ch])
        emit_bytes([0xD3, 0x04])
        emit_bytes([0x7B])           # LD A, E
        emit_bytes([0xD3, 0x05])
        # Write block + F-number high: reg 0xA4+ch
        emit_bytes([0x78])           # LD A, B (octave)
        emit_bytes([0xCB, 0x27])     # SLA A
        emit_bytes([0xCB, 0x27])     # SLA A
        emit_bytes([0xCB, 0x27])     # SLA A (octave << 3)
        emit_bytes([0xB2])           # OR D (add F-num high bits)
        emit(0x57)                   # LD D, A
        emit_bytes([0x3E, 0xA4 + ch])
        emit_bytes([0xD3, 0x04])
        emit_bytes([0x7A])           # LD A, D
        emit_bytes([0xD3, 0x05])
        # Key on: reg 0x28, value = 0xF0 | ch
        emit_bytes([0x3E, 0x28])
        emit_bytes([0xD3, 0x04])
        emit_bytes([0x3E, 0xF0 | ch])
        emit_bytes([0xD3, 0x05])
        emit(0xD1)                   # POP DE
        # next_ch:

    # --- Skip FM3-4 and other channels for now (just advance HL) ---
    # Skip remaining 12 bytes (FM3, FM4, SSG1-3, ADPCM A1-6, B1)
    emit_bytes([0x11, 12, 0x00])     # LD DE, 12
    emit(0x19)                       # ADD HL, DE

    # Check if past end of song data
    emit(0xD5)                       # PUSH DE
    emit_bytes([0x11, (SONG_ADDR + num_rows * ROW_SIZE) & 0xFF,
                      ((SONG_ADDR + num_rows * ROW_SIZE) >> 8) & 0xFF])
    emit(0xB7)                       # OR A
    emit_bytes([0xED, 0x52])         # SBC HL, DE
    emit(0xD1)                       # POP DE
    emit_bytes([0x38, 0x06])         # JR C, not_end (HL < end)
    # Reset to start
    emit_bytes([0x21, SONG_ADDR & 0xFF, (SONG_ADDR >> 8) & 0xFF])
    emit_bytes([0x18, 0x03])         # JR save_ptr
    # not_end: restore HL (it was modified by SBC)
    emit(0x19)                       # ADD HL, DE (HL = HL + end_addr, undoing the SBC... no)

    # Actually, SBC HL,DE destroys HL. Let me fix this.
    # Save HL before the comparison instead.
    # ... this is getting messy. Let me use a simpler approach.

    # Scrap the end check above. Let me redo the end-of-song part cleanly.
    # I'll rewrite from the "skip 12 bytes" part.

    # --- Let me restart the IRQ handler more carefully ---
    pc = 0x0300

    emit(0xF5)  # PUSH AF
    emit(0xC5)  # PUSH BC
    emit(0xD5)  # PUSH DE
    emit(0xE5)  # PUSH HL
    emit_bytes([0xDD, 0xE5])  # PUSH IX

    # Reset Timer A flag
    emit_bytes([0x3E, 0x27])
    emit_bytes([0xD3, 0x04])
    emit_bytes([0x3E, 0x15])
    emit_bytes([0xD3, 0x05])

    # Check playing flag
    emit_bytes([0x3A, 0x02, 0xF8])
    emit(0xB7)
    emit_bytes([0x28, 0x70])  # JR Z, irq_done (will fix offset later)

    # Load row pointer
    emit_bytes([0x2A, 0x00, 0xF8])

    # --- FM channel 1 (port A: $04/$05, channel 0) ---
    emit(0x7E)   # LD A, (HL) — FM1 byte
    emit(0x23)   # INC HL
    emit(0xB7)   # OR A
    emit_bytes([0x28, 0x2C])  # JR Z, fm1_done (sustain)
    emit_bytes([0xFE, 0x01])  # CP 1 (key off?)
    emit_bytes([0x20, 0x08])  # JR NZ, fm1_note
    # key off FM ch0
    emit_bytes([0x3E, 0x28, 0xD3, 0x04, 0x3E, 0x00, 0xD3, 0x05])
    emit_bytes([0x18, 0x22])  # JR fm1_done
    # fm1_note:
    emit_bytes([0xD6, 24])    # SUB 24
    emit(0x47)                # LD B, A
    emit_bytes([0x06, 0x00])  # LD B, 0 (octave)
    # Oops, I clobbered B. Let me redo.
    # A = midi_note - 24
    emit(0x4F)                # LD C, A (save)
    emit_bytes([0x06, 0x00])  # LD B, 0
    emit(0x79)                # LD A, C
    # div12:
    emit_bytes([0xFE, 12])    # CP 12
    emit_bytes([0x38, 0x04])  # JR C, div_done
    emit_bytes([0xD6, 12])    # SUB 12
    emit(0x04)                # INC B
    emit_bytes([0x18, 0xF8])  # JR div12
    # div_done: A=semi, B=oct
    emit(0xE5)                # PUSH HL
    emit(0x87)                # ADD A,A
    emit(0x6F)                # LD L, A
    emit_bytes([0x26, 0x00])  # LD H, 0
    emit_bytes([0x11, FTABLE_ADDR & 0xFF, (FTABLE_ADDR >> 8) & 0xFF])
    emit(0x19)                # ADD HL, DE — HL = ftable + semi*2
    emit(0x5E)                # LD E, (HL) — fnum low
    emit(0x23)
    emit(0x56)                # LD D, (HL) — fnum high
    emit(0xE1)                # POP HL
    # Write A0 (fnum low)
    emit_bytes([0x3E, 0xA0, 0xD3, 0x04])
    emit_bytes([0x7B, 0xD3, 0x05])  # LD A,E; OUT (05),A
    # Write A4 (block + fnum high)
    emit(0x78)                # LD A, B
    emit_bytes([0xCB, 0x27, 0xCB, 0x27, 0xCB, 0x27])  # SLA A x3
    emit(0xB2)                # OR D
    emit_bytes([0x3E, 0xA4, 0xD3, 0x04])
    # Oops — A got overwritten by 0xA4. Need to save the block+fnum value.
    # Let me use C for the computed value.

    # This is getting error-prone writing Z80 by hand. Let me use a different approach.
    pass

    # I'll write the driver as a proper Z80 assembly source and assemble it.
    return None

# Instead of hand-encoding Z80, let me write it as assembly and use a table-driven approach
def build_driver_v2(song_data, num_rows, tick_rate_hz=8):
    """Build Z80 driver using pre-assembled code + data tables."""

    SONG_ADDR = 0x1000
    FTABLE_ADDR = 0x0200
    SONG_END = SONG_ADDR + num_rows * 14

    code = bytearray(0x8000)

    # FM frequency table
    for i, fnum in enumerate(FM_FNUMS):
        struct.pack_into('<H', code, FTABLE_ADDR + i*2, fnum)

    # Store song parameters at 0x0220
    struct.pack_into('<H', code, 0x0220, SONG_ADDR)      # song start
    struct.pack_into('<H', code, 0x0222, SONG_END)        # song end

    # Timer A value
    timer_a_val = int(1024 - (4000000 / (144 * 2 * tick_rate_hz)))
    timer_a_val = max(0, min(1023, timer_a_val))
    code[0x0224] = (timer_a_val >> 2) & 0xFF  # hi
    code[0x0225] = timer_a_val & 0x03          # lo

    # Hand-assemble a minimal but correct Z80 driver
    # Using a helper to make it cleaner

    asm = bytearray()

    def w(*bs):
        asm.extend(bs)

    # === INIT at 0x0080 ===
    init_code = bytearray()
    def wi(*bs):
        init_code.extend(bs)

    wi(0x31, 0xFC, 0xFF)     # LD SP, $FFFC
    wi(0xED, 0x56)            # IM 1
    wi(0xF3)                  # DI

    # Clear RAM
    wi(0xAF)                  # XOR A
    wi(0x32, 0x00, 0xF8)     # LD ($F800), A
    wi(0x21, 0x00, 0xF8)     # LD HL, $F800
    wi(0x11, 0x01, 0xF8)     # LD DE, $F801
    wi(0x01, 0xFF, 0x07)     # LD BC, $07FF
    wi(0xED, 0xB0)            # LDIR

    # Silence YM2610
    # Key off all FM
    for ch in range(4):
        port_a = 0x04 if ch < 2 else 0x06
        port_d = 0x05 if ch < 2 else 0x07
        ch_id = ch if ch < 2 else ch - 2
        wi(0x3E, 0x28, 0xD3, port_a, 0x3E, ch_id, 0xD3, port_d)

    # SSG mixer off
    wi(0x3E, 0x07, 0xD3, 0x04, 0x3E, 0x3F, 0xD3, 0x05)

    # ADPCM-A dump all
    wi(0x3E, 0x00, 0xD3, 0x06, 0x3E, 0xBF, 0xD3, 0x07)
    # ADPCM-A master vol
    wi(0x3E, 0x01, 0xD3, 0x06, 0x3E, 0x3F, 0xD3, 0x07)

    # Set up simple FM patch for ch0 and ch1 (port pair A)
    for ch in range(2):
        # Algorithm 7 (all carriers = pure sine), feedback 0
        wi(0x3E, 0xB0+ch, 0xD3, 0x04, 0x3E, 0x07, 0xD3, 0x05)
        # TL (volume) for all 4 operators — all audible in algo 7
        for op_i, op_off in enumerate([0, 8, 4, 12]):
            wi(0x3E, 0x40+op_off+ch, 0xD3, 0x04, 0x3E, 0x20, 0xD3, 0x05)
        # MUL=1 for all operators
        for op_off in [0, 8, 4, 12]:
            wi(0x3E, 0x30+op_off+ch, 0xD3, 0x04, 0x3E, 0x01, 0xD3, 0x05)
        # AR=31 (fast attack)
        for op_off in [0, 8, 4, 12]:
            wi(0x3E, 0x50+op_off+ch, 0xD3, 0x04, 0x3E, 0x1F, 0xD3, 0x05)
        # DR=5
        for op_off in [0, 8, 4, 12]:
            wi(0x3E, 0x60+op_off+ch, 0xD3, 0x04, 0x3E, 0x05, 0xD3, 0x05)
        # SR=2
        for op_off in [0, 8, 4, 12]:
            wi(0x3E, 0x70+op_off+ch, 0xD3, 0x04, 0x3E, 0x02, 0xD3, 0x05)
        # SL=15, RR=7
        for op_off in [0, 8, 4, 12]:
            wi(0x3E, 0x80+op_off+ch, 0xD3, 0x04, 0x3E, 0xF7, 0xD3, 0x05)
        # L+R output
        wi(0x3E, 0xB4+ch, 0xD3, 0x04, 0x3E, 0xC0, 0xD3, 0x05)

    # Timer A
    wi(0x3E, 0x24, 0xD3, 0x04, 0x3E, code[0x0224], 0xD3, 0x05)
    wi(0x3E, 0x25, 0xD3, 0x04, 0x3E, code[0x0225], 0xD3, 0x05)
    # Enable Timer A
    wi(0x3E, 0x27, 0xD3, 0x04, 0x3E, 0x15, 0xD3, 0x05)

    # Init row pointer
    wi(0x21, SONG_ADDR & 0xFF, (SONG_ADDR >> 8) & 0xFF)
    wi(0x22, 0x00, 0xF8)
    # playing = 1 (autoplay)
    wi(0x3E, 0x01, 0x32, 0x02, 0xF8)

    # Enable NMI + EI
    wi(0xD3, 0x08)
    wi(0xFB)

    # Main loop
    main_loop_off = len(init_code)
    wi(0x18, 0xFE)  # JR $-2 (infinite loop, IRQ does the work)

    code[0x0080:0x0080+len(init_code)] = init_code

    # === NMI handler at 0x0066 ===
    nmi = bytearray()
    nmi.extend([0xF5])                # PUSH AF
    nmi.extend([0xDB, 0x00])          # IN A, (00) — read command
    nmi.extend([0x32, 0x03, 0xF8])    # LD ($F803), A
    nmi.extend([0xD3, 0x0C])          # OUT ($0C), A — acknowledge
    nmi.extend([0xD3, 0x00])          # OUT ($00), A — clear
    nmi.extend([0xF1])                # POP AF
    nmi.extend([0xED, 0x45])          # RETN
    code[0x0066:0x0066+len(nmi)] = nmi

    # === IRQ handler at 0x0300 ===
    irq = bytearray()
    def wi2(*bs):
        irq.extend(bs)

    wi2(0xF5, 0xC5, 0xD5, 0xE5)  # PUSH AF,BC,DE,HL

    # Reset Timer A flag
    wi2(0x3E, 0x27, 0xD3, 0x04, 0x3E, 0x15, 0xD3, 0x05)

    # Check 68K command first
    wi2(0x3A, 0x03, 0xF8)  # LD A, ($F803)
    wi2(0xB7)               # OR A
    wi2(0x28, 0x12)         # JR Z, no_cmd
    wi2(0xFE, 0x03)         # CP 3
    wi2(0x20, 0x04)         # JR NZ, not_stop
    wi2(0xAF, 0x32, 0x02, 0xF8)  # XOR A; LD ($F802),A  (stop)
    # not_stop:
    wi2(0xFE, 0x07)         # CP 7
    wi2(0x20, 0x04)         # JR NZ, not_play
    wi2(0x3E, 0x01, 0x32, 0x02, 0xF8)  # LD A,1; LD ($F802),A (play)
    # not_play:
    wi2(0xAF, 0x32, 0x03, 0xF8)  # clear command
    # no_cmd:

    # Check playing
    wi2(0x3A, 0x02, 0xF8)  # LD A, ($F802)
    wi2(0xB7)               # OR A
    irq_done_jr_pos = len(irq)
    wi2(0x28, 0x00)         # JR Z, irq_done (patch later)

    # Load row pointer
    wi2(0x2A, 0x00, 0xF8)  # LD HL, ($F800)

    # Process FM1 (ch0, port A)
    wi2(0x7E, 0x23)         # LD A,(HL); INC HL — read FM1 byte
    wi2(0xB7)               # OR A
    fm1_skip_jr = len(irq)
    wi2(0x28, 0x00)         # JR Z, fm1_done (patch)
    wi2(0xFE, 0x01)         # CP 1
    wi2(0x20, 0x08)         # JR NZ, fm1_note
    # key off ch0
    wi2(0x3E, 0x28, 0xD3, 0x04, 0x3E, 0x00, 0xD3, 0x05)
    fm1_koff_jr = len(irq)
    wi2(0x18, 0x00)         # JR fm1_done (patch)
    # fm1_note:
    fm1_note_pos = len(irq)
    wi2(0xD6, 24)           # SUB 24 (base = C1)
    wi2(0x4F)               # LD C, A
    wi2(0x06, 0x00)         # LD B, 0 (octave)
    wi2(0x79)               # LD A, C
    # div12 loop
    div12_pos = len(irq)
    wi2(0xFE, 12)           # CP 12
    wi2(0x38, 0x04)         # JR C, div_done
    wi2(0xD6, 12)           # SUB 12
    wi2(0x04)               # INC B
    wi2(0x18, 0xF8)         # JR div12
    # div_done: A=semitone, B=octave
    wi2(0xE5)               # PUSH HL
    wi2(0x87)               # ADD A,A (semi*2)
    wi2(0x5F)               # LD E, A
    wi2(0x16, 0x00)         # LD D, 0
    wi2(0x21, FTABLE_ADDR & 0xFF, (FTABLE_ADDR >> 8) & 0xFF)  # LD HL, FTABLE
    wi2(0x19)               # ADD HL, DE
    wi2(0x4E)               # LD C, (HL) — fnum low
    wi2(0x23)
    wi2(0x46)               # LD B, (HL) — fnum high (only low 3 bits used)
    wi2(0xE1)               # POP HL
    # Write fnum low to reg A0
    wi2(0x3E, 0xA0, 0xD3, 0x04, 0x79, 0xD3, 0x05)  # reg A0, data=C
    # Compute block|fnum_hi
    wi2(0x78)               # LD A, B (fnum high)
    wi2(0xE6, 0x07)         # AND 7 (keep low 3 bits)
    wi2(0x4F)               # LD C, A (save fnum_hi)
    wi2(0x3A, 0x00, 0x00)   # LD A, octave... wait, B has octave but we used B for fnum_hi
    # Problem: B was used for both octave and fnum_hi. Let me restructure.

    # Let me restart the FM note handler more carefully
    irq = irq[:fm1_note_pos]

    # fm1_note: A = MIDI note
    wi2(0xD6, 24)           # SUB 24
    wi2(0xE5)               # PUSH HL (save row pointer)
    # Compute octave and semitone
    wi2(0x4F)               # LD C, A
    wi2(0x06, 0x00)         # LD B, 0 (octave counter)
    wi2(0x79)               # LD A, C
    div12_pos = len(irq)
    wi2(0xFE, 12)
    wi2(0x38, 0x04)
    wi2(0xD6, 12)
    wi2(0x04)               # INC B
    wi2(0x18, 0xF8)
    # A=semitone(0-11), B=octave
    wi2(0xC5)               # PUSH BC (save octave in B)
    wi2(0x87)               # ADD A,A
    wi2(0x5F)               # LD E,A
    wi2(0x16, 0x00)         # LD D,0
    wi2(0x21, FTABLE_ADDR & 0xFF, (FTABLE_ADDR >> 8) & 0xFF)
    wi2(0x19)               # ADD HL,DE
    wi2(0x5E)               # LD E,(HL) = fnum_lo
    wi2(0x23)
    wi2(0x56)               # LD D,(HL) = fnum_hi
    wi2(0xC1)               # POP BC (B=octave)
    wi2(0xE1)               # POP HL (row pointer)
    # Write fnum_lo to A0
    wi2(0x3E, 0xA0, 0xD3, 0x04, 0x7B, 0xD3, 0x05)
    # Compute block: B<<3 | (D & 0x07)
    wi2(0x78)               # LD A,B (octave)
    wi2(0xCB, 0x27)         # SLA A
    wi2(0xCB, 0x27)         # SLA A
    wi2(0xCB, 0x27)         # SLA A (octave<<3)
    wi2(0x7A)               # LD A,D (fnum_hi)
    wi2(0xE6, 0x07)         # AND 7
    # Oops clobbered A again. Save octave<<3 first.

    irq = irq[:-(2+2+2+1+2)]  # back up
    wi2(0x78)               # LD A,B
    wi2(0xCB, 0x27, 0xCB, 0x27, 0xCB, 0x27)  # SLA x3
    wi2(0x4F)               # LD C,A (octave<<3 in C)
    wi2(0x7A)               # LD A,D (fnum_hi)
    wi2(0xE6, 0x07)         # AND 7
    wi2(0xB1)               # OR C
    wi2(0x3E, 0xA4, 0xD3, 0x04)  # reg A4
    # Oops, A was just set to reg number. Need to save the block value.
    # Use the stack or another register.

    # OK this hand-assembly is a disaster. Let me just write proper Z80 asm
    # to a file and use an assembler. Or use a more structured approach.

    # SIMPLEST POSSIBLE APPROACH: pre-compute all the register values
    # in Python and store them in a lookup table in the M-ROM.
    # The Z80 just reads [reg, val] pairs from the table.
    # No computation on the Z80 side at all.

    return None


def build_driver_v3(song_data, num_rows, tick_rate_hz=8):
    """V3: Pre-compute everything. The Z80 just writes register pairs.

    Song format in ROM: for each row, for each active channel,
    store the YM2610 register writes needed. The Z80 just reads
    and writes them to the ports.

    Per-row per-FM-channel: 0 bytes (sustain) or 7 bytes (key-on):
      [flag] [reg1] [val1] [reg2] [val2] [reg3] [val3]
      flag: 0=sustain, 1=keyoff, 2=keyon

    This is basically VGM-lite. But organized per-tick.
    """

    SONG_ADDR = 0x1000

    # Pre-compute register writes for each row
    reg_data = bytearray()

    for row in range(num_rows):
        row_offset = row * 14
        for ch in range(2):  # FM1 and FM2 only for now
            midi_note = song_data[row_offset + ch]

            if midi_note == 0:  # sustain
                reg_data.append(0x00)
            elif midi_note == 1:  # key off
                reg_data.append(0x01)
                reg_data.append(ch)  # channel to key-off
            else:
                # Compute FM register values
                n = midi_note - 24  # C1 = 0
                if n < 0: n = 0
                octave = n // 12
                semi = n % 12
                fnum = FM_FNUMS[semi]
                fnum_lo = fnum & 0xFF
                fnum_hi = fnum >> 8
                block_fnum = ((octave & 7) << 3) | (fnum_hi & 0x07)

                reg_data.append(0x02)  # key-on flag
                reg_data.append(0xA0 + ch)  # fnum_lo reg
                reg_data.append(fnum_lo)
                reg_data.append(0xA4 + ch)  # block+fnum_hi reg
                reg_data.append(block_fnum)
                reg_data.append(0xF0 | ch)  # key-on value

    # This is variable-length which makes the Z80 code harder.
    # Let me use FIXED size per channel instead:
    # 6 bytes per channel: [flag] [fnum_lo] [block_fnum_hi] [0] [0] [0]
    # flag: 0=sustain, 1=keyoff, 2+=keyon

    reg_data = bytearray()
    BYTES_PER_CH = 3
    BYTES_PER_ROW = BYTES_PER_CH * 2  # 2 FM channels for now

    for row in range(num_rows):
        row_offset = row * 14
        for ch in range(2):
            midi_note = song_data[row_offset + ch]
            if midi_note == 0:
                reg_data.extend([0x00, 0x00, 0x00])
            elif midi_note == 1:
                reg_data.extend([0x01, 0x00, 0x00])
            else:
                n = max(0, midi_note - 24)
                octave = min(7, n // 12)
                semi = n % 12
                fnum = FM_FNUMS[semi]
                reg_data.extend([
                    0x02,
                    fnum & 0xFF,
                    ((octave & 7) << 3) | ((fnum >> 8) & 0x07)
                ])

    SONG_END = SONG_ADDR + len(reg_data)

    code = bytearray(0x20000)  # 128KB M-ROM

    # Frequency table (not needed anymore, pre-computed)
    # Song parameters
    struct.pack_into('<H', code, 0x0220, SONG_ADDR)
    struct.pack_into('<H', code, 0x0222, SONG_END)
    code[0x0224] = BYTES_PER_ROW

    # Timer A
    timer_a_val = int(1024 - (4000000 / (144 * 2 * tick_rate_hz)))
    timer_a_val = max(0, min(1023, timer_a_val))

    # Place song data
    code[SONG_ADDR:SONG_ADDR+len(reg_data)] = reg_data

    # Signature
    sig = b"NeoSynth v0.1"
    code[0x40:0x40+len(sig)] = sig

    # === Z80 CODE ===
    # Now I'll write minimal Z80 code. The IRQ handler just:
    # 1. Load HL from ($F800)
    # 2. For ch0: read 3 bytes [flag, d1, d2]
    #    if flag==0: skip
    #    if flag==1: key-off ch0 (write 0x28/0x00 to port A)
    #    if flag==2: write d1 to reg A0, d2 to reg A4, key-on 0xF0
    # 3. Same for ch1
    # 4. Advance HL, check bounds, save back

    # I'll hand-assemble very carefully this time.

    z = bytearray()

    # --- Vectors ---
    # 0x0000: JP init
    code[0x00] = 0xF3  # DI
    code[0x01] = 0xC3; code[0x02] = 0x80; code[0x03] = 0x00
    # 0x0038: JP irq
    code[0x38] = 0xF3
    code[0x39] = 0xC3; code[0x3A] = 0x00; code[0x3B] = 0x03
    # 0x0066: NMI
    code[0x66] = 0xF5  # PUSH AF
    code[0x67] = 0xDB; code[0x68] = 0x00  # IN A,(0)
    code[0x69] = 0x32; code[0x6A] = 0x03; code[0x6B] = 0xF8  # LD (F803),A
    code[0x6C] = 0xD3; code[0x6D] = 0x0C  # OUT (0C),A
    code[0x6E] = 0xF1  # POP AF
    code[0x6F] = 0xED; code[0x70] = 0x45  # RETN

    # --- INIT at 0x0080 ---
    p = 0x0080
    def e(*bs):
        nonlocal p
        for b in bs:
            code[p] = b; p += 1

    e(0x31, 0xFC, 0xFF)       # LD SP, FFFC
    e(0xED, 0x56)              # IM 1

    # Clear RAM
    e(0xAF)                    # XOR A
    e(0x32, 0x00, 0xF8)
    e(0x21, 0x00, 0xF8)
    e(0x11, 0x01, 0xF8)
    e(0x01, 0xFF, 0x07)
    e(0xED, 0xB0)

    # Key off all FM
    for ch in range(4):
        pa = 0x04 if ch < 2 else 0x06
        pd = 0x05 if ch < 2 else 0x07
        ci = ch if ch < 2 else ch - 2
        e(0x3E, 0x28, 0xD3, pa, 0x3E, ci, 0xD3, pd)

    # SSG all off
    e(0x3E, 0x07, 0xD3, 0x04, 0x3E, 0x3F, 0xD3, 0x05)

    # ADPCM-A dump
    e(0x3E, 0x00, 0xD3, 0x06, 0x3E, 0xBF, 0xD3, 0x07)

    # FM patch for ch0 and ch1 — simple sine (algo 7)
    for ch in range(2):
        e(0x3E, 0xB0+ch, 0xD3, 0x04, 0x3E, 0x07, 0xD3, 0x05)  # ALG=7
        for op_off in [0, 8, 4, 12]:
            e(0x3E, 0x40+op_off+ch, 0xD3, 0x04, 0x3E, 0x18, 0xD3, 0x05)  # TL
        for op_off in [0, 8, 4, 12]:
            e(0x3E, 0x30+op_off+ch, 0xD3, 0x04, 0x3E, 0x01, 0xD3, 0x05)  # MUL=1
        for op_off in [0, 8, 4, 12]:
            e(0x3E, 0x50+op_off+ch, 0xD3, 0x04, 0x3E, 0x1F, 0xD3, 0x05)  # AR=31
        for op_off in [0, 8, 4, 12]:
            e(0x3E, 0x60+op_off+ch, 0xD3, 0x04, 0x3E, 0x00, 0xD3, 0x05)  # DR=0
        for op_off in [0, 8, 4, 12]:
            e(0x3E, 0x70+op_off+ch, 0xD3, 0x04, 0x3E, 0x00, 0xD3, 0x05)  # SR=0
        for op_off in [0, 8, 4, 12]:
            e(0x3E, 0x80+op_off+ch, 0xD3, 0x04, 0x3E, 0x0F, 0xD3, 0x05)  # SL=0,RR=15
        e(0x3E, 0xB4+ch, 0xD3, 0x04, 0x3E, 0xC0, 0xD3, 0x05)  # L+R

    # Timer A setup
    ta_hi = (timer_a_val >> 2) & 0xFF
    ta_lo = timer_a_val & 0x03
    e(0x3E, 0x24, 0xD3, 0x04, 0x3E, ta_hi, 0xD3, 0x05)
    e(0x3E, 0x25, 0xD3, 0x04, 0x3E, ta_lo, 0xD3, 0x05)
    e(0x3E, 0x27, 0xD3, 0x04, 0x3E, 0x15, 0xD3, 0x05)

    # Init row pointer
    e(0x21, SONG_ADDR & 0xFF, (SONG_ADDR >> 8) & 0xFF)
    e(0x22, 0x00, 0xF8)
    # playing = 1
    e(0x3E, 0x01, 0x32, 0x02, 0xF8)
    # Enable NMI
    e(0xD3, 0x08)
    # EI
    e(0xFB)
    # Main loop
    e(0x18, 0xFE)  # JR $

    # --- IRQ handler at 0x0300 ---
    p = 0x0300
    e(0xF5, 0xC5, 0xD5, 0xE5)  # PUSH AF,BC,DE,HL

    # Reset Timer A
    e(0x3E, 0x27, 0xD3, 0x04, 0x3E, 0x15, 0xD3, 0x05)

    # Check playing
    e(0x3A, 0x02, 0xF8)  # LD A,(F802)
    e(0xB7)               # OR A
    e(0x28, 0x40)         # JR Z, irq_done (adjust later)
    irq_jz_pos = p - 1    # position of the offset byte

    # Load row pointer
    e(0x2A, 0x00, 0xF8)  # LD HL,(F800)

    # --- Process ch0 ---
    e(0x7E)               # LD A,(HL)  flag
    e(0x23)               # INC HL
    e(0x4E)               # LD C,(HL)  data1 (fnum_lo)
    e(0x23)               # INC HL
    e(0x46)               # LD B,(HL)  data2 (block_fnum_hi)
    e(0x23)               # INC HL
    e(0xB7)               # OR A
    e(0x28, 0x14)         # JR Z, ch0_done (sustain)
    e(0xFE, 0x01)         # CP 1
    e(0x20, 0x06)         # JR NZ, ch0_keyon
    # key off ch0
    e(0x3E, 0x28, 0xD3, 0x04, 0x3E, 0x00, 0xD3, 0x05)
    e(0x18, 0x0A)         # JR ch0_done
    # ch0_keyon:
    e(0x3E, 0xA0, 0xD3, 0x04, 0x79, 0xD3, 0x05)  # fnum_lo to reg A0
    e(0x3E, 0xA4, 0xD3, 0x04, 0x78, 0xD3, 0x05)  # block to reg A4
    e(0x3E, 0x28, 0xD3, 0x04, 0x3E, 0xF0, 0xD3, 0x05)  # key on ch0
    # ch0_done:

    # --- Process ch1 ---
    e(0x7E)               # LD A,(HL)
    e(0x23)
    e(0x4E)               # LD C,(HL)
    e(0x23)
    e(0x46)               # LD B,(HL)
    e(0x23)
    e(0xB7)
    e(0x28, 0x14)         # JR Z, ch1_done
    e(0xFE, 0x01)
    e(0x20, 0x06)         # JR NZ, ch1_keyon
    e(0x3E, 0x28, 0xD3, 0x04, 0x3E, 0x01, 0xD3, 0x05)  # key off ch1
    e(0x18, 0x0A)
    # ch1_keyon:
    e(0x3E, 0xA1, 0xD3, 0x04, 0x79, 0xD3, 0x05)  # fnum_lo to A1
    e(0x3E, 0xA5, 0xD3, 0x04, 0x78, 0xD3, 0x05)  # block to A5
    e(0x3E, 0x28, 0xD3, 0x04, 0x3E, 0xF1, 0xD3, 0x05)  # key on ch1
    # ch1_done:

    # Save row pointer
    e(0x22, 0x00, 0xF8)  # LD (F800),HL

    # Check end of song
    e(0x11, SONG_END & 0xFF, (SONG_END >> 8) & 0xFF)  # LD DE, song_end
    e(0xB7)  # OR A (clear carry)
    e(0xED, 0x52)  # SBC HL,DE
    e(0x38, 0x08)  # JR C, not_end (HL < end)
    # Reset to start
    e(0x21, SONG_ADDR & 0xFF, (SONG_ADDR >> 8) & 0xFF)
    e(0x22, 0x00, 0xF8)
    # not_end:

    # irq_done:
    irq_done_pos = p
    code[irq_jz_pos] = irq_done_pos - (irq_jz_pos + 1)  # fix JR Z offset

    e(0xE1, 0xD1, 0xC1, 0xF1)  # POP HL,DE,BC,AF
    e(0xFB)  # EI
    e(0xED, 0x4D)  # RETI

    print(f"Driver code: IRQ handler ends at 0x{p:04X}")
    print(f"Song data: 0x{SONG_ADDR:04X}-0x{SONG_END:04X} ({len(reg_data)} bytes, {num_rows} rows)")
    print(f"Timer A: {timer_a_val} ({tick_rate_hz} Hz)")

    return bytes(code)


# --- Build a test song: C minor scale on FM1 ---
def make_test_song():
    """Simple ascending scale on FM1."""
    ROW_SIZE = 14
    # 120 BPM, 16th notes = 8 ticks/sec
    # Each note lasts 4 ticks (= 1 beat = quarter note at 120bpm)

    rows = []

    # C minor scale: C4 D4 Eb4 F4 G4 Ab4 Bb4 C5
    scale = [60, 62, 63, 65, 67, 68, 70, 72]

    for note in scale:
        # Note on
        row = [note] + [0]*13
        rows.append(row)
        # Sustain for 3 more ticks
        for _ in range(3):
            rows.append([0]*14)
        # Key off
        rows.append([1] + [0]*13)
        # Rest
        rows.append([0]*14)

    # Flatten
    data = bytearray()
    for row in rows:
        data.extend(row)

    return bytes(data), len(rows)


if __name__ == '__main__':
    song_data, num_rows = make_test_song()
    print(f"Test song: {num_rows} rows")

    mrom = build_driver_v3(song_data, num_rows, tick_rate_hz=8)

    if mrom:
        out_path = '/home/bruno/CLProjects/NeoScanSDK/examples/hello_neo/res/neosynth_m1.bin'
        with open(out_path, 'wb') as f:
            f.write(mrom)
        print(f"Written: {out_path} ({len(mrom)} bytes)")
