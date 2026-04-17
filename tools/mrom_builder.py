#!/usr/bin/env python3
"""Generate a minimal silent Z80 M ROM for Neo Geo."""
import sys
import os
import argparse


def build_mrom():
    """Build a 128KB Z80 binary: init, Timer B, NMI ack, halt loop."""
    mrom = bytearray(0x20000)

    PORT_FROM_68K = 0x00
    PORT_YM2610_A_ADDR = 0x04
    PORT_YM2610_A_VAL = 0x05
    PORT_ENABLE_NMI = 0x08
    PORT_TO_68K = 0x0C

    pc = 0
    mrom[pc] = 0xF3; pc += 1                   # DI
    mrom[pc] = 0xC3; pc += 1                    # JP $0100
    mrom[pc] = 0x00; pc += 1
    mrom[pc] = 0x01; pc += 1

    # Timer B IRQ handler ($0038 — IM 1)
    pc = 0x38
    mrom[pc] = 0xF3; pc += 1                    # DI
    mrom[pc] = 0xF5; pc += 1                    # PUSH AF
    mrom[pc] = 0x3E; pc += 1                    # LD A, $27
    mrom[pc] = 0x27; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (YM_A_ADDR), A
    mrom[pc] = PORT_YM2610_A_ADDR; pc += 1
    mrom[pc] = 0x3E; pc += 1                    # LD A, $3A
    mrom[pc] = 0x3A; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (YM_A_VAL), A
    mrom[pc] = PORT_YM2610_A_VAL; pc += 1
    mrom[pc] = 0xF1; pc += 1                    # POP AF
    mrom[pc] = 0xFB; pc += 1                    # EI
    mrom[pc] = 0xED; pc += 1                    # RETI
    mrom[pc] = 0x4D; pc += 1

    # NMI handler ($0066 — 68k command dispatch)
    pc = 0x66
    mrom[pc] = 0xF5; pc += 1                    # PUSH AF
    mrom[pc] = 0xDB; pc += 1                    # IN A, (FROM_68K)
    mrom[pc] = PORT_FROM_68K; pc += 1
    mrom[pc] = 0xF6; pc += 1                    # OR $80
    mrom[pc] = 0x80; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (TO_68K), A
    mrom[pc] = PORT_TO_68K; pc += 1
    mrom[pc] = 0xF1; pc += 1                    # POP AF
    mrom[pc] = 0xED; pc += 1                    # RETN
    mrom[pc] = 0x45; pc += 1

    # Init ($0100)
    pc = 0x100
    mrom[pc] = 0x31; pc += 1                    # LD SP, $FFFF
    mrom[pc] = 0xFF; pc += 1
    mrom[pc] = 0xFF; pc += 1
    mrom[pc] = 0xED; pc += 1                    # IM 1
    mrom[pc] = 0x56; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (ENABLE_NMI), A
    mrom[pc] = PORT_ENABLE_NMI; pc += 1
    mrom[pc] = 0x3E; pc += 1                    # LD A, $26 (Timer B freq reg)
    mrom[pc] = 0x26; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (YM_A_ADDR), A
    mrom[pc] = PORT_YM2610_A_ADDR; pc += 1
    mrom[pc] = 0x3E; pc += 1                    # LD A, $FF
    mrom[pc] = 0xFF; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (YM_A_VAL), A
    mrom[pc] = PORT_YM2610_A_VAL; pc += 1
    mrom[pc] = 0x3E; pc += 1                    # LD A, $27 (Timer control reg)
    mrom[pc] = 0x27; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (YM_A_ADDR), A
    mrom[pc] = PORT_YM2610_A_ADDR; pc += 1
    mrom[pc] = 0x3E; pc += 1                    # LD A, $3A (enable Timer B + reset)
    mrom[pc] = 0x3A; pc += 1
    mrom[pc] = 0xD3; pc += 1                    # OUT (YM_A_VAL), A
    mrom[pc] = PORT_YM2610_A_VAL; pc += 1
    mrom[pc] = 0xFB; pc += 1                    # EI
    mainloop = pc
    mrom[pc] = 0x76; pc += 1                    # HALT
    mrom[pc] = 0xC3; pc += 1                    # JP mainloop
    mrom[pc] = mainloop & 0xFF; pc += 1
    mrom[pc] = (mainloop >> 8) & 0xFF; pc += 1

    return bytes(mrom)


def main():
    parser = argparse.ArgumentParser(description='Generate silent Neo Geo M ROM')
    parser.add_argument('-o', '--output', required=True, help='Output M ROM file')
    args = parser.parse_args()

    mrom = build_mrom()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(mrom)
    print(f"M ROM: {args.output} ({len(mrom)} bytes)")


if __name__ == '__main__':
    main()
