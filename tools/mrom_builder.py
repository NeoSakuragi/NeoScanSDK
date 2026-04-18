#!/usr/bin/env python3
"""Generate a Neo Geo Z80 M ROM for the sound driver.

Supports ADPCM-A sample playback and VGM music streaming.

68k command protocol (written to REG_SOUND / $320000):
  $00       = no-op
  $01-$3F   = play sample N (1-based) on ADPCM-A channel 0
  $40       = stop all ADPCM-A channels
  $80       = start music (VGM playback)
  $81       = stop music
  $90-$BF   = play ADPCM-B voice sample N ($90=1, $91=2, ...)
  $C0       = stop ADPCM-B voice
"""
import argparse
import os
import struct


PORT_FROM_68K      = 0x00
PORT_YM_A_ADDR     = 0x04
PORT_YM_A_DATA     = 0x05
PORT_YM_B_ADDR     = 0x06
PORT_YM_B_DATA     = 0x07
PORT_ENABLE_NMI    = 0x08
PORT_TO_68K        = 0x0C

MROM_SIZE          = 0x20000
TABLE_ADDR         = 0x200
VOICE_TABLE_ADDR   = 0x300
MUSIC_ADDR         = 0x0400

# Z80 RAM
RAM_MUS_PLAYING    = 0xF800
RAM_MUS_POS        = 0xF801  # 2 bytes LE
RAM_MUS_LOOP       = 0xF803  # 2 bytes LE
RAM_TICK_DIV       = 0xF805  # tick divider counter


def _emit(mrom, pc, *bytez):
    for b in bytez:
        mrom[pc] = b & 0xFF
        pc += 1
    return pc


def build_mrom(sample_table_bin=None, music_bin=None, voice_table_bin=None):
    """Build a 128KB Z80 M ROM binary.

    sample_table_bin: bytes with 4 bytes per sample for ADPCM-A.
    music_bin: bytes from vgm_converter.
    voice_table_bin: bytes with 4 bytes per voice for ADPCM-B.
    """
    mrom = bytearray(MROM_SIZE)

    if sample_table_bin:
        num_samples = len(sample_table_bin) // 4
        for i in range(len(sample_table_bin)):
            mrom[TABLE_ADDR + i] = sample_table_bin[i]
    else:
        num_samples = 0

    if voice_table_bin:
        num_voices = len(voice_table_bin) // 4
        for i in range(len(voice_table_bin)):
            mrom[VOICE_TABLE_ADDR + i] = voice_table_bin[i]
    else:
        num_voices = 0

    has_music = music_bin is not None and len(music_bin) > 2
    if has_music:
        for i in range(len(music_bin)):
            mrom[MUSIC_ADDR + i] = music_bin[i]
        loop_rel = struct.unpack_from('<H', music_bin, 0)[0]
        music_data_start = MUSIC_ADDR + 2
        if loop_rel != 0xFFFF:
            music_loop_addr = music_data_start + loop_rel
        else:
            music_loop_addr = 0xFFFF

    # === $0000: Entry ===
    pc = _emit(mrom, 0, 0xF3, 0xC3, 0x00, 0x01)  # DI; JP $0100

    # === $0038: Timer B IRQ (IM 1) ===
    pc = 0x38
    pc = _emit(mrom, pc, 0xF3)                      # DI
    pc = _emit(mrom, pc, 0xF5, 0xC5, 0xD5, 0xE5)   # PUSH AF,BC,DE,HL
    # Ack Timer B
    pc = _emit(mrom, pc, 0x3E, 0x27, 0xD3, PORT_YM_A_ADDR)
    pc = _emit(mrom, pc, 0x3E, 0x3A, 0xD3, PORT_YM_A_DATA)

    if has_music:
        # Check mus_playing
        pc = _emit(mrom, pc, 0x3A, RAM_MUS_PLAYING & 0xFF, RAM_MUS_PLAYING >> 8)
        pc = _emit(mrom, pc, 0xB7)                   # OR A
        vgm_skip_jr = pc
        pc = _emit(mrom, pc, 0x28, 0x00)             # JR Z, skip (patch later)
        pc = _emit(mrom, pc, 0xCD)                    # CALL vgm_process
        vgm_call_addr = pc
        pc = _emit(mrom, pc, 0x00, 0x00)             # placeholder

    # Timer B done
    timer_done = pc
    pc = _emit(mrom, pc, 0xE1, 0xD1, 0xC1, 0xF1)   # POP HL,DE,BC,AF
    pc = _emit(mrom, pc, 0xFB)                       # EI
    pc = _emit(mrom, pc, 0xED, 0x4D)                 # RETI

    if has_music:
        mrom[vgm_skip_jr + 1] = (timer_done - vgm_skip_jr - 2) & 0xFF

    # === $0066: NMI handler (68k command) ===
    pc = 0x66
    pc = _emit(mrom, pc, 0xF5, 0xC5, 0xD5, 0xE5)   # PUSH AF,BC,DE,HL
    pc = _emit(mrom, pc, 0xDB, PORT_FROM_68K)        # IN A,(FROM_68K)
    pc = _emit(mrom, pc, 0x47)                        # LD B,A (save cmd)
    pc = _emit(mrom, pc, 0xF6, 0x80)                 # OR $80
    pc = _emit(mrom, pc, 0xD3, PORT_TO_68K)           # OUT (TO_68K),A (ack)

    if has_music:
        # Check $80 = start music
        pc = _emit(mrom, pc, 0x78)                    # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0x80)              # CP $80
        mus_start_jp = pc
        pc = _emit(mrom, pc, 0xCA, 0x00, 0x00)        # JP Z, music_start (patch)

        # Check $81 = stop music
        pc = _emit(mrom, pc, 0xFE, 0x81)              # CP $81
        mus_stop_jp = pc
        pc = _emit(mrom, pc, 0xCA, 0x00, 0x00)        # JP Z, music_stop (patch)

    if num_voices > 0:
        # Check $C0 = stop voice
        pc = _emit(mrom, pc, 0x78)                    # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0xC0)              # CP $C0
        vox_stop_jp = pc
        pc = _emit(mrom, pc, 0xCA, 0x00, 0x00)        # JP Z, voice_stop (patch)

        # Check $90-$90+NUM_VOICES = play voice
        pc = _emit(mrom, pc, 0x78)                    # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0x90)              # CP $90
        vox_lo_jp = pc
        pc = _emit(mrom, pc, 0xDA, 0x00, 0x00)        # JP C, nmi_done (patch)
        pc = _emit(mrom, pc, 0xFE, 0x90 + num_voices) # CP $90+NUM
        vox_hi_jp = pc
        pc = _emit(mrom, pc, 0xD2, 0x00, 0x00)        # JP NC, nmi_done (patch)

        # Valid voice: A = cmd, subtract $90 for 0-based index
        pc = _emit(mrom, pc, 0xD6, 0x90)              # SUB $90
        pc = _emit(mrom, pc, 0x87, 0x87)              # ADD A,A; ADD A,A (A*4)
        pc = _emit(mrom, pc, 0x6F)                    # LD L,A
        pc = _emit(mrom, pc, 0x26, (VOICE_TABLE_ADDR >> 8) & 0xFF)  # LD H,hi

        # Reset ADPCM-B (reg $10 = $80)
        pc = _emit(mrom, pc, 0x3E, 0x10, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x80, 0xD3, PORT_YM_A_DATA)

        # Pan L+R (reg $11 = $C0)
        pc = _emit(mrom, pc, 0x3E, 0x11, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0xC0, 0xD3, PORT_YM_A_DATA)

        # Start address (regs $12/$13)
        pc = _emit(mrom, pc, 0x3E, 0x12, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x23)
        pc = _emit(mrom, pc, 0x3E, 0x13, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_A_DATA)

        # End address (regs $14/$15)
        pc = _emit(mrom, pc, 0x23)
        pc = _emit(mrom, pc, 0x3E, 0x14, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x23)
        pc = _emit(mrom, pc, 0x3E, 0x15, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_A_DATA)

        # Delta-N = $5555 (22050 Hz playback)
        pc = _emit(mrom, pc, 0x3E, 0x19, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x55, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x1A, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x55, 0xD3, PORT_YM_A_DATA)

        # Volume (reg $1B = $FF = max)
        pc = _emit(mrom, pc, 0x3E, 0x1B, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0xFF, 0xD3, PORT_YM_A_DATA)

        # Start playback (reg $10 = $01: bit0=start)
        pc = _emit(mrom, pc, 0x3E, 0x10, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x01, 0xD3, PORT_YM_A_DATA)

    adpcma_check = pc  # voice out-of-range falls through here

    if num_samples > 0:
        # Check $40 = stop all ADPCM
        pc = _emit(mrom, pc, 0x78)                    # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0x40)              # CP $40
        stop_jp = pc
        pc = _emit(mrom, pc, 0xCA, 0x00, 0x00)        # JP Z,nmi_done (patch)

        # Check $01-NUM_SAMPLES
        pc = _emit(mrom, pc, 0x78)                    # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0x01)              # CP $01
        lo_jp = pc
        pc = _emit(mrom, pc, 0xDA, 0x00, 0x00)        # JP C,nmi_done (patch)
        pc = _emit(mrom, pc, 0xFE, num_samples + 1)   # CP NUM+1
        hi_jp = pc
        pc = _emit(mrom, pc, 0xD2, 0x00, 0x00)        # JP NC,nmi_done (patch)

        # Valid command: look up sample table
        pc = _emit(mrom, pc, 0x3D)                    # DEC A (0-based)
        pc = _emit(mrom, pc, 0x87, 0x87)              # ADD A,A; ADD A,A (A*4)
        pc = _emit(mrom, pc, 0x6F)                    # LD L,A
        pc = _emit(mrom, pc, 0x26, (TABLE_ADDR >> 8) & 0xFF)

        # Key-off channel 4 (bit 4 = ch4, bit 7 = dump)
        pc = _emit(mrom, pc, 0x3E, 0x00, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x90, 0xD3, PORT_YM_B_DATA)

        # Total level (reg $01 = $3F)
        pc = _emit(mrom, pc, 0x3E, 0x01, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x3F, 0xD3, PORT_YM_B_DATA)

        # Channel 4 pan + level (reg $0C = $DF)
        pc = _emit(mrom, pc, 0x3E, 0x0C, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0xDF, 0xD3, PORT_YM_B_DATA)

        # Start address (ch4: regs $14/$1C)
        pc = _emit(mrom, pc, 0x3E, 0x14, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)
        pc = _emit(mrom, pc, 0x23)
        pc = _emit(mrom, pc, 0x3E, 0x1C, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)

        # End address (ch4: regs $24/$2C)
        pc = _emit(mrom, pc, 0x23)
        pc = _emit(mrom, pc, 0x3E, 0x24, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)
        pc = _emit(mrom, pc, 0x23)
        pc = _emit(mrom, pc, 0x3E, 0x2C, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)

        # Key-on channel 4 (bit 4)
        pc = _emit(mrom, pc, 0x3E, 0x00, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x10, 0xD3, PORT_YM_B_DATA)

    # NMI done
    nmi_done = pc
    pc = _emit(mrom, pc, 0xE1, 0xD1, 0xC1, 0xF1)   # POP HL,DE,BC,AF
    pc = _emit(mrom, pc, 0xED, 0x45)                 # RETN

    # Patch JR targets
    if num_samples > 0:
        mrom[stop_jp + 1] = nmi_done & 0xFF
        mrom[stop_jp + 2] = nmi_done >> 8
        mrom[lo_jp + 1] = nmi_done & 0xFF
        mrom[lo_jp + 2] = nmi_done >> 8
        mrom[hi_jp + 1] = nmi_done & 0xFF
        mrom[hi_jp + 2] = nmi_done >> 8

    # === Music command handlers (after NMI done) ===
    if has_music:
        # Music start handler
        music_start = pc
        # mus_pos = music_data_start
        pc = _emit(mrom, pc, 0x21, music_data_start & 0xFF, music_data_start >> 8)  # LD HL, data_start
        pc = _emit(mrom, pc, 0x22, RAM_MUS_POS & 0xFF, RAM_MUS_POS >> 8)  # LD (mus_pos), HL
        # mus_loop = music_loop_addr
        pc = _emit(mrom, pc, 0x21, music_loop_addr & 0xFF, music_loop_addr >> 8)
        pc = _emit(mrom, pc, 0x22, RAM_MUS_LOOP & 0xFF, RAM_MUS_LOOP >> 8)
        # mus_playing = 1
        pc = _emit(mrom, pc, 0x3E, 0x01)
        pc = _emit(mrom, pc, 0x32, RAM_MUS_PLAYING & 0xFF, RAM_MUS_PLAYING >> 8)
        pc = _emit(mrom, pc, 0xC3, nmi_done & 0xFF, nmi_done >> 8)  # JP nmi_done

        # Music stop handler
        music_stop = pc
        pc = _emit(mrom, pc, 0xAF)                   # XOR A
        pc = _emit(mrom, pc, 0x32, RAM_MUS_PLAYING & 0xFF, RAM_MUS_PLAYING >> 8)
        # Silence SSG channels (vol = 0)
        pc = _emit(mrom, pc, 0x3E, 0x08, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0xAF, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x09, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0xAF, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x0A, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0xAF, 0xD3, PORT_YM_A_DATA)
        # Key-off all FM channels
        pc = _emit(mrom, pc, 0x3E, 0x28, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x00, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x28, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x01, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x28, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x02, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x28, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x05, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0xC3, nmi_done & 0xFF, nmi_done >> 8)

        # Patch JP targets for music commands
        mrom[mus_start_jp + 1] = music_start & 0xFF
        mrom[mus_start_jp + 2] = music_start >> 8
        mrom[mus_stop_jp + 1] = music_stop & 0xFF
        mrom[mus_stop_jp + 2] = music_stop >> 8

    # === Voice stop handler ===
    if num_voices > 0:
        voice_stop = pc
        # Stop ADPCM-B: reg $10 = $00 (clear start), then $80 (reset)
        pc = _emit(mrom, pc, 0x3E, 0x10, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x00, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0x3E, 0x10, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x80, 0xD3, PORT_YM_A_DATA)
        pc = _emit(mrom, pc, 0xC3, nmi_done & 0xFF, nmi_done >> 8)

        mrom[vox_stop_jp + 1] = voice_stop & 0xFF
        mrom[vox_stop_jp + 2] = voice_stop >> 8
        mrom[vox_lo_jp + 1] = adpcma_check & 0xFF
        mrom[vox_lo_jp + 2] = adpcma_check >> 8
        mrom[vox_hi_jp + 1] = adpcma_check & 0xFF
        mrom[vox_hi_jp + 2] = adpcma_check >> 8

    # === VGM frame processor subroutine ===
    if has_music:
        vgm_process = pc
        # Patch the CALL address in Timer B ISR
        mrom[vgm_call_addr] = vgm_process & 0xFF
        mrom[vgm_call_addr + 1] = vgm_process >> 8

        # LD HL, (mus_pos)
        pc = _emit(mrom, pc, 0x2A, RAM_MUS_POS & 0xFF, RAM_MUS_POS >> 8)
        # LD A, (HL) — frame count byte
        pc = _emit(mrom, pc, 0x7E)
        # CP $FF — end marker?
        pc = _emit(mrom, pc, 0xFE, 0xFF)
        vgm_end_jr = pc
        pc = _emit(mrom, pc, 0x28, 0x00)             # JR Z, vgm_end (patch)
        # OR A — count == 0? (empty frame)
        pc = _emit(mrom, pc, 0xB7)
        vgm_empty_jr = pc
        pc = _emit(mrom, pc, 0x28, 0x00)             # JR Z, vgm_advance (patch)
        # LD B, A — count
        pc = _emit(mrom, pc, 0x47)

        # Write loop
        vgm_write_loop = pc
        pc = _emit(mrom, pc, 0x23)                    # INC HL
        pc = _emit(mrom, pc, 0x7E)                    # LD A, (HL) — port flag
        pc = _emit(mrom, pc, 0xB7)                    # OR A
        vgm_portb_jr = pc
        pc = _emit(mrom, pc, 0x20, 0x00)              # JR NZ, port_b (patch)

        # Port A write
        pc = _emit(mrom, pc, 0x23)                    # INC HL
        pc = _emit(mrom, pc, 0x7E)                    # LD A, (HL) — reg
        pc = _emit(mrom, pc, 0xD3, PORT_YM_A_ADDR)
        pc = _emit(mrom, pc, 0x23)                    # INC HL
        pc = _emit(mrom, pc, 0x7E)                    # LD A, (HL) — val
        pc = _emit(mrom, pc, 0xD3, PORT_YM_A_DATA)
        vgm_write_next_jr = pc
        pc = _emit(mrom, pc, 0x18, 0x00)              # JR write_done (patch)

        # Port B write
        port_b = pc
        pc = _emit(mrom, pc, 0x23)                    # INC HL
        pc = _emit(mrom, pc, 0x7E)                    # LD A, (HL) — reg
        pc = _emit(mrom, pc, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x23)                    # INC HL
        pc = _emit(mrom, pc, 0x7E)                    # LD A, (HL) — val
        pc = _emit(mrom, pc, 0xD3, PORT_YM_B_DATA)

        # Write done
        write_done = pc
        pc = _emit(mrom, pc, 0x10, (vgm_write_loop - pc - 2) & 0xFF)  # DJNZ write_loop

        # Patch JR targets
        mrom[vgm_portb_jr + 1] = (port_b - vgm_portb_jr - 2) & 0xFF
        mrom[vgm_write_next_jr + 1] = (write_done - vgm_write_next_jr - 2) & 0xFF

        # Advance position: INC HL, store
        vgm_advance = pc
        pc = _emit(mrom, pc, 0x23)                    # INC HL
        pc = _emit(mrom, pc, 0x22, RAM_MUS_POS & 0xFF, RAM_MUS_POS >> 8)  # LD (mus_pos), HL
        pc = _emit(mrom, pc, 0xC9)                    # RET

        # Patch empty frame JR
        mrom[vgm_empty_jr + 1] = (vgm_advance - vgm_empty_jr - 2) & 0xFF

        # VGM end: check loop
        vgm_end = pc
        pc = _emit(mrom, pc, 0x3A, (RAM_MUS_LOOP + 1) & 0xFF, (RAM_MUS_LOOP + 1) >> 8)  # LD A,(mus_loop+1)
        pc = _emit(mrom, pc, 0xFE, 0xFF)              # CP $FF
        vgm_no_loop_jr = pc
        pc = _emit(mrom, pc, 0x28, 0x00)              # JR Z, vgm_stop (patch)
        # Loop: set mus_pos = mus_loop
        pc = _emit(mrom, pc, 0x2A, RAM_MUS_LOOP & 0xFF, RAM_MUS_LOOP >> 8)
        pc = _emit(mrom, pc, 0x22, RAM_MUS_POS & 0xFF, RAM_MUS_POS >> 8)
        pc = _emit(mrom, pc, 0xC9)                    # RET

        # Stop music
        vgm_stop = pc
        pc = _emit(mrom, pc, 0xAF)                    # XOR A
        pc = _emit(mrom, pc, 0x32, RAM_MUS_PLAYING & 0xFF, RAM_MUS_PLAYING >> 8)
        pc = _emit(mrom, pc, 0xC9)                    # RET

        mrom[vgm_end_jr + 1] = (vgm_end - vgm_end_jr - 2) & 0xFF
        mrom[vgm_no_loop_jr + 1] = (vgm_stop - vgm_no_loop_jr - 2) & 0xFF

    # === Init code (placed after all subroutines) ===
    init_addr = max(pc, 0x0100)
    # Fix entry point
    mrom[2] = init_addr & 0xFF
    mrom[3] = init_addr >> 8

    pc = init_addr
    pc = _emit(mrom, pc, 0x31, 0xFF, 0xFF)          # LD SP,$FFFF
    pc = _emit(mrom, pc, 0xED, 0x56)                 # IM 1
    pc = _emit(mrom, pc, 0xD3, PORT_ENABLE_NMI)      # OUT (ENABLE_NMI),A

    # Clear music state
    if has_music:
        pc = _emit(mrom, pc, 0xAF)                   # XOR A
        pc = _emit(mrom, pc, 0x32, RAM_MUS_PLAYING & 0xFF, RAM_MUS_PLAYING >> 8)

    # Timer B setup ($C6 = 60Hz: (256-198)*2304/8MHz = 16.7ms)
    pc = _emit(mrom, pc, 0x3E, 0x26, 0xD3, PORT_YM_A_ADDR)
    pc = _emit(mrom, pc, 0x3E, 0xC6, 0xD3, PORT_YM_A_DATA)
    pc = _emit(mrom, pc, 0x3E, 0x27, 0xD3, PORT_YM_A_ADDR)
    pc = _emit(mrom, pc, 0x3E, 0x3A, 0xD3, PORT_YM_A_DATA)

    pc = _emit(mrom, pc, 0xFB)                       # EI
    mainloop = pc
    pc = _emit(mrom, pc, 0x76)                        # HALT
    pc = _emit(mrom, pc, 0xC3, mainloop & 0xFF, mainloop >> 8)

    return bytes(mrom)


def main():
    parser = argparse.ArgumentParser(description='Generate Neo Geo Z80 M ROM')
    parser.add_argument('-o', '--output', required=True, help='Output M ROM file')
    parser.add_argument('--sample-table', help='Binary sample table from wav_encoder')
    parser.add_argument('--voice-table', help='Binary voice table from wav_encoder --mode b')
    parser.add_argument('--music', help='Binary music stream from vgm_converter')
    args = parser.parse_args()

    table_bin = None
    if args.sample_table and os.path.exists(args.sample_table):
        table_bin = open(args.sample_table, 'rb').read()

    voice_bin = None
    if args.voice_table and os.path.exists(args.voice_table):
        voice_bin = open(args.voice_table, 'rb').read()

    music_bin = None
    if args.music and os.path.exists(args.music):
        music_bin = open(args.music, 'rb').read()

    mrom = build_mrom(table_bin, music_bin, voice_bin)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(mrom)

    n = len(table_bin) // 4 if table_bin else 0
    mode = f"ADPCM-A ({n} samples)" if n else "silent"
    if music_bin:
        mode += f" + VGM music ({len(music_bin)} bytes)"
    print(f"M ROM: {args.output} ({len(mrom)} bytes, {mode})")


if __name__ == '__main__':
    main()
