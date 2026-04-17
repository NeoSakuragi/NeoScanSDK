#!/usr/bin/env python3
"""Generate a Neo Geo Z80 M ROM for the sound driver.

Two modes:
  - Silent: no samples, just NMI ack (default)
  - ADPCM-A: loads a sample table, plays samples on command from 68k

68k command protocol (written to REG_SOUND / $320000):
  $00       = no-op
  $01-$3F   = play sample N (1-based) on ADPCM-A channel 0
  $40       = stop all ADPCM-A channels
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


def _emit(mrom, pc, *bytez):
    for b in bytez:
        mrom[pc] = b & 0xFF
        pc += 1
    return pc


def build_mrom(sample_table_bin=None):
    """Build a 128KB Z80 M ROM binary.

    sample_table_bin: bytes with 4 bytes per sample (start_lo, start_hi, end_lo, end_hi).
                      If None, builds a silent driver.
    """
    mrom = bytearray(MROM_SIZE)

    if sample_table_bin:
        num_samples = len(sample_table_bin) // 4
        for i in range(len(sample_table_bin)):
            mrom[TABLE_ADDR + i] = sample_table_bin[i]
    else:
        num_samples = 0

    # === $0000: Entry ===
    pc = _emit(mrom, 0, 0xF3, 0xC3, 0x00, 0x01)  # DI; JP $0100

    # === $0038: Timer B IRQ (IM 1) ===
    pc = 0x38
    pc = _emit(mrom, pc, 0xF3, 0xF5)              # DI; PUSH AF
    pc = _emit(mrom, pc, 0x3E, 0x27, 0xD3, PORT_YM_A_ADDR)  # LD A,$27; OUT
    pc = _emit(mrom, pc, 0x3E, 0x3A, 0xD3, PORT_YM_A_DATA)  # LD A,$3A; OUT
    pc = _emit(mrom, pc, 0xF1, 0xFB, 0xED, 0x4D)  # POP AF; EI; RETI

    # === $0066: NMI handler (68k command) ===
    pc = 0x66
    pc = _emit(mrom, pc, 0xF5, 0xC5, 0xD5, 0xE5)  # PUSH AF,BC,DE,HL
    pc = _emit(mrom, pc, 0xDB, PORT_FROM_68K)       # IN A,(FROM_68K)
    pc = _emit(mrom, pc, 0x47)                       # LD B,A (save cmd)
    pc = _emit(mrom, pc, 0xF6, 0x80)                # OR $80
    pc = _emit(mrom, pc, 0xD3, PORT_TO_68K)          # OUT (TO_68K),A (ack)

    if num_samples == 0:
        # Silent driver: just ack and return
        pass
    else:
        # Check $40 = stop all
        pc = _emit(mrom, pc, 0x78)                   # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0x40)             # CP $40
        stop_jr = pc
        pc = _emit(mrom, pc, 0x28, 0x00)             # JR Z,nmi_done (patch later)

        # Check $01-NUM_SAMPLES
        pc = _emit(mrom, pc, 0x78)                   # LD A,B
        pc = _emit(mrom, pc, 0xFE, 0x01)             # CP $01
        lo_jr = pc
        pc = _emit(mrom, pc, 0x38, 0x00)             # JR C,nmi_done (patch later)
        pc = _emit(mrom, pc, 0xFE, num_samples + 1)  # CP NUM+1
        hi_jr = pc
        pc = _emit(mrom, pc, 0x30, 0x00)             # JR NC,nmi_done (patch later)

        # Valid command: look up sample table
        pc = _emit(mrom, pc, 0x3D)                   # DEC A (0-based)
        pc = _emit(mrom, pc, 0x87, 0x87)             # ADD A,A; ADD A,A (A*4)
        pc = _emit(mrom, pc, 0x6F)                   # LD L,A
        pc = _emit(mrom, pc, 0x26, (TABLE_ADDR >> 8) & 0xFF)  # LD H,hi(TABLE)

        # Key-off channel 0 first (reg $00 = $80 | $01 = $81)
        pc = _emit(mrom, pc, 0x3E, 0x00, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x81, 0xD3, PORT_YM_B_DATA)

        # Total level / master volume (reg $01 = $3F = max)
        pc = _emit(mrom, pc, 0x3E, 0x01, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x3F, 0xD3, PORT_YM_B_DATA)

        # Channel 0 pan + level (reg $08 = $DF = L+R pan, max level)
        pc = _emit(mrom, pc, 0x3E, 0x08, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0xDF, 0xD3, PORT_YM_B_DATA)

        # Start address (regs $10/$18)
        pc = _emit(mrom, pc, 0x3E, 0x10, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)        # (HL) → start_lo
        pc = _emit(mrom, pc, 0x23)                                # INC HL
        pc = _emit(mrom, pc, 0x3E, 0x18, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)        # (HL) → start_hi

        # End address (regs $20/$28)
        pc = _emit(mrom, pc, 0x23)                                # INC HL
        pc = _emit(mrom, pc, 0x3E, 0x20, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)        # (HL) → end_lo
        pc = _emit(mrom, pc, 0x23)                                # INC HL
        pc = _emit(mrom, pc, 0x3E, 0x28, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x7E, 0xD3, PORT_YM_B_DATA)        # (HL) → end_hi

        # Key-on channel 0 (reg $00, value $01 = key-on ch0)
        pc = _emit(mrom, pc, 0x3E, 0x00, 0xD3, PORT_YM_B_ADDR)
        pc = _emit(mrom, pc, 0x3E, 0x01, 0xD3, PORT_YM_B_DATA)

    # NMI done (play falls through here directly)
    nmi_done = pc
    pc = _emit(mrom, pc, 0xE1, 0xD1, 0xC1, 0xF1)  # POP HL,DE,BC,AF
    pc = _emit(mrom, pc, 0xED, 0x45)                # RETN

    if num_samples > 0:
        mrom[stop_jr + 1] = (nmi_done - stop_jr - 2) & 0xFF
        mrom[lo_jr + 1] = (nmi_done - lo_jr - 2) & 0xFF
        mrom[hi_jr + 1] = (nmi_done - hi_jr - 2) & 0xFF

    # === $0100: Init ===
    pc = 0x100
    pc = _emit(mrom, pc, 0x31, 0xFF, 0xFF)          # LD SP,$FFFF
    pc = _emit(mrom, pc, 0xED, 0x56)                 # IM 1
    pc = _emit(mrom, pc, 0xD3, PORT_ENABLE_NMI)      # OUT (ENABLE_NMI),A

    # Timer B setup
    pc = _emit(mrom, pc, 0x3E, 0x26, 0xD3, PORT_YM_A_ADDR)
    pc = _emit(mrom, pc, 0x3E, 0xFF, 0xD3, PORT_YM_A_DATA)
    pc = _emit(mrom, pc, 0x3E, 0x27, 0xD3, PORT_YM_A_ADDR)
    pc = _emit(mrom, pc, 0x3E, 0x3A, 0xD3, PORT_YM_A_DATA)

    pc = _emit(mrom, pc, 0xFB)                       # EI
    mainloop = pc
    pc = _emit(mrom, pc, 0x76)                        # HALT
    pc = _emit(mrom, pc, 0xC3, mainloop & 0xFF, (mainloop >> 8) & 0xFF)  # JP mainloop

    return bytes(mrom)


def main():
    parser = argparse.ArgumentParser(description='Generate Neo Geo Z80 M ROM')
    parser.add_argument('-o', '--output', required=True, help='Output M ROM file')
    parser.add_argument('--sample-table', help='Binary sample table from wav_encoder')
    args = parser.parse_args()

    table_bin = None
    if args.sample_table and os.path.exists(args.sample_table):
        table_bin = open(args.sample_table, 'rb').read()

    mrom = build_mrom(table_bin)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(mrom)

    n = len(table_bin) // 4 if table_bin else 0
    mode = f"ADPCM-A ({n} samples)" if n else "silent"
    print(f"M ROM: {args.output} ({len(mrom)} bytes, {mode})")


if __name__ == '__main__':
    main()
