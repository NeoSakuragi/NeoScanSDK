#!/usr/bin/env python3
"""Pre-scramble a P ROM so MAME's rom_kof98 slot descrambles it correctly.

MAME's kof98 cart applies decrypt_68k() at load time, which unscrambles the
encrypted KOF98 P ROM. To use the rom_kof98 slot with our plaintext homebrew
P ROM, we apply the INVERSE transform: the scrambled output, when fed through
decrypt_68k, produces our original code.

The scramble is a permutation of 16-bit words within 0x200-byte blocks across
the first 1MB of P1. It only rearranges data — no XOR or key-based crypto.
"""
import sys


SEC = [0x000000, 0x100000, 0x000004, 0x100004,
       0x10000a, 0x00000a, 0x10000e, 0x00000e]
POS = [0x000, 0x004, 0x00a, 0x00e]


def _build_forward_map():
    """Build word-position mapping: D[d] = S[map[d]] for decrypt_68k."""
    fwd = {}
    for i in range(0x800, 0x100000, 0x200):
        for j in range(0, 0x100, 0x10):
            for k in range(0, 16, 2):
                s = k // 2
                fwd[i+j+k]       = i+j+SEC[s]+0x100
                fwd[i+j+k+0x100] = i+j+SEC[s]
            if 0x080000 <= i < 0x0c0000:
                for p in range(4):
                    a = i+j+POS[p]
                    fwd[a]       = a
                    fwd[a+0x100] = a+0x100
            elif i >= 0x0c0000:
                for p in range(4):
                    a = i+j+POS[p]
                    fwd[a]       = a+0x100
                    fwd[a+0x100] = a
        fwd[i]       = i
        fwd[i+2]     = i+0x100000
        fwd[i+0x100] = i+0x100
        fwd[i+0x102] = i+0x100100

    return fwd


def scramble(plaintext):
    """Scramble a plaintext P ROM for use with rom_kof98."""
    buf_size = 0x200000
    D = bytearray(buf_size)
    D[:min(len(plaintext), buf_size)] = plaintext[:buf_size]
    S = bytearray(buf_size)
    S[:0x800] = D[:0x800]

    fwd = _build_forward_map()
    inv = {s_pos: d_pos for d_pos, s_pos in fwd.items()}

    for s_pos, d_pos in inv.items():
        if s_pos+2 <= buf_size and d_pos+2 <= buf_size:
            S[s_pos:s_pos+2] = D[d_pos:d_pos+2]

    return bytes(S)


def decrypt_68k(cpurom):
    """MAME's kof98 decrypt_68k (for verification)."""
    src = bytearray(cpurom)
    if len(src) < 0x200000:
        src.extend(b'\x00' * (0x200000 - len(src)))
    dst = bytearray(src[:0x200000])

    for i in range(0x800, 0x100000, 0x200):
        for j in range(0, 0x100, 0x10):
            for k in range(0, 16, 2):
                s = k // 2
                src[i+j+k:i+j+k+2]           = dst[i+j+SEC[s]+0x100:i+j+SEC[s]+0x100+2]
                src[i+j+k+0x100:i+j+k+0x102] = dst[i+j+SEC[s]:i+j+SEC[s]+2]
            if 0x080000 <= i < 0x0c0000:
                for p in range(4):
                    a = i+j+POS[p]
                    src[a:a+2]         = dst[a:a+2]
                    src[a+0x100:a+0x102] = dst[a+0x100:a+0x102]
            elif i >= 0x0c0000:
                for p in range(4):
                    a = i+j+POS[p]
                    src[a:a+2]         = dst[a+0x100:a+0x102]
                    src[a+0x100:a+0x102] = dst[a:a+2]
        src[i:i+2]         = dst[i:i+2]
        src[i+2:i+4]       = dst[i+0x100000:i+0x100002]
        src[i+0x100:i+0x102] = dst[i+0x100:i+0x102]
        src[i+0x102:i+0x104] = dst[i+0x100100:i+0x100102]

    return bytes(src)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Scramble P ROM for MAME rom_kof98 slot')
    parser.add_argument('input', help='Plaintext P ROM')
    parser.add_argument('-o', '--output', required=True, help='Scrambled P ROM output')
    parser.add_argument('--verify', action='store_true', help='Verify roundtrip')
    parser.add_argument('--pad', type=lambda x: int(x, 0), default=0x600000,
                        help='Pad output to this size (default: 0x600000 for kof98 memmove safety)')
    args = parser.parse_args()

    plain = open(args.input, 'rb').read()
    print(f"Input: {args.input} ({len(plain):,} bytes)")

    enc = scramble(plain)

    if args.verify:
        dec = decrypt_68k(enc)
        padded = bytearray(0x200000)
        padded[:len(plain)] = plain[:0x200000]
        # Only verify first 1MB — the shuffle region. 0x100000+ is the memmove
        # region that depends on P2 data (which we don't have).
        if dec[:0x100000] == bytes(padded[:0x100000]):
            print("  Verify: roundtrip OK")
        else:
            diffs = sum(1 for a, b in zip(dec[:0x100000], padded[:0x100000]) if a != b)
            print(f"  Verify: MISMATCH ({diffs} bytes differ in first 1MB)")
            for i in range(0x100000):
                if dec[i] != padded[i]:
                    print(f"    first diff at 0x{i:06X}: got 0x{dec[i]:02X}, want 0x{padded[i]:02X}")
                    break
            sys.exit(1)

    out = bytearray(enc)
    if len(out) < args.pad:
        out.extend(b'\x00' * (args.pad - len(out)))

    with open(args.output, 'wb') as f:
        f.write(bytes(out))
    print(f"Output: {args.output} ({len(out):,} bytes)")


if __name__ == '__main__':
    main()
