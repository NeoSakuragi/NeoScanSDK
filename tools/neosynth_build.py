#!/usr/bin/env python3
"""Build a stub NeoSynth Z80 M-ROM. Boots, responds to BIOS, does nothing else."""
import struct, sys, argparse

def build_stub():
    code = bytearray(0x20000)  # 128KB
    sig = b'NeoSynth v0.1'
    code[0x40:0x40+len(sig)] = sig

    # 0x0000: DI; JP init
    code[0x00] = 0xF3; code[0x01] = 0xC3; code[0x02] = 0x80; code[0x03] = 0x00
    # 0x0038: EI; RETI
    code[0x38] = 0xFB; code[0x39] = 0xED; code[0x3A] = 0x4D
    # 0x0066: NMI — read command, reply, return
    p = 0x0066
    code[p] = 0xF5; p+=1      # PUSH AF
    code[p] = 0xDB; p+=1      # IN A,(00)
    code[p] = 0x00; p+=1
    code[p] = 0xD3; p+=1      # OUT (0C),A
    code[p] = 0x0C; p+=1
    code[p] = 0xF1; p+=1      # POP AF
    code[p] = 0xED; p+=1      # RETN
    code[p] = 0x45; p+=1

    # Init at 0x0080
    p = 0x0080
    code[p] = 0x31; code[p+1] = 0xFC; code[p+2] = 0xFF; p+=3  # LD SP,$FFFC
    code[p] = 0xED; code[p+1] = 0x56; p+=2                      # IM 1
    code[p] = 0xD3; code[p+1] = 0x08; p+=2                      # OUT (08),A — enable NMI
    code[p] = 0xFB; p+=1                                          # EI
    code[p] = 0x18; code[p+1] = 0xFE; p+=2                      # JR $ (main loop)

    return bytes(code)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--output', required=True)
    args = parser.parse_args()
    with open(args.output, 'wb') as f:
        f.write(build_stub())
    print(f"NeoSynth stub: {args.output}")

if __name__ == '__main__':
    main()
