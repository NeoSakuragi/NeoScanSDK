#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — PC-side flasher tool

Usage:
  python3 flash_cart.py --port /dev/ttyACM0 --prom game_p1.bin
  python3 flash_cart.py --port /dev/ttyACM0 --prom p.bin --srom s.bin --mrom m.bin
  python3 flash_cart.py --port /dev/ttyACM0 --all game/      # reads p1.bin, s1.bin, m1.bin, c1.bin, c2.bin
  python3 flash_cart.py --port /dev/ttyACM0 --id             # read all chip IDs
  python3 flash_cart.py --port /dev/ttyACM0 --verify --prom p.bin
  python3 flash_cart.py --port /dev/ttyACM0 --dump P 524288 p_dump.bin   # dump P ROM to file
  python3 flash_cart.py --port /dev/ttyACM0 --scan --prom p.bin          # write + immediate verify
"""

import argparse
import os
import sys
import time
import serial


CHIPS = ["P", "S", "M", "C1", "C2", "V1", "V2", "V3", "V4"]
BAUD = 115200
TIMEOUT = 5


def open_port(port):
    ser = serial.Serial(port, BAUD, timeout=TIMEOUT)
    time.sleep(0.5)
    ser.reset_input_buffer()
    return ser


def send_cmd(ser, cmd):
    ser.write((cmd + "\n").encode())
    ser.flush()


def read_line(ser, timeout=TIMEOUT):
    ser.timeout = timeout
    line = ser.readline().decode(errors="replace").strip()
    return line


def ping(ser):
    send_cmd(ser, "PING")
    resp = read_line(ser)
    if resp != "PONG":
        print(f"ERROR: expected PONG, got '{resp}'")
        sys.exit(1)
    print("Cart connected.")


def read_id(ser, chip):
    send_cmd(ser, f"ID {chip}")
    resp = read_line(ser)
    print(f"  {chip}: {resp}")


def erase_chip(ser, chip):
    print(f"Erasing {chip} ROM...", end=" ", flush=True)
    send_cmd(ser, f"ERASE {chip}")

    while True:
        resp = read_line(ser, timeout=30)
        if resp.startswith("PROGRESS"):
            pass
        elif resp == "OK":
            print("done.")
            return
        elif resp.startswith("ERR"):
            print(f"FAILED: {resp}")
            sys.exit(1)
        else:
            print(f"unexpected: {resp}")


def program_chip(ser, chip, data):
    size = len(data)
    print(f"Programming {chip} ROM ({size} bytes)...", flush=True)

    send_cmd(ser, f"PROG {chip} {size}")
    resp = read_line(ser)
    if resp != "READY":
        print(f"ERROR: expected READY, got '{resp}'")
        sys.exit(1)

    chunk_size = 256
    sent = 0
    while sent < size:
        end = min(sent + chunk_size, size)
        ser.write(data[sent:end])
        sent = end

        while ser.in_waiting:
            line = read_line(ser, timeout=0.1)
            if line.startswith("PROGRESS"):
                pct = line.split()[1]
                print(f"\r  {pct}%", end="", flush=True)

    while True:
        resp = read_line(ser, timeout=60)
        if resp.startswith("PROGRESS"):
            pct = resp.split()[1]
            print(f"\r  {pct}%", end="", flush=True)
        elif resp == "OK":
            print("\r  100% done.")
            return
        elif resp.startswith("ERR"):
            print(f"\nFAILED: {resp}")
            sys.exit(1)


def verify_chip(ser, chip, data):
    size = len(data)
    print(f"Verifying {chip} ROM ({size} bytes)...", end=" ", flush=True)

    send_cmd(ser, f"VERIFY {chip} {size}")
    resp = read_line(ser)
    if resp != "READY":
        print(f"ERROR: expected READY, got '{resp}'")
        sys.exit(1)

    readback = ser.read(size)
    if len(readback) != size:
        print(f"FAILED: only read {len(readback)} of {size} bytes")
        sys.exit(1)

    mismatches = 0
    first_mismatch = None
    for i in range(size):
        if readback[i] != data[i]:
            mismatches += 1
            if first_mismatch is None:
                first_mismatch = i

    if mismatches == 0:
        print("OK — verified.")
    else:
        print(f"FAILED — {mismatches} mismatches")
        print(f"  First mismatch at 0x{first_mismatch:06X}: "
              f"expected 0x{data[first_mismatch]:02X}, "
              f"got 0x{readback[first_mismatch]:02X}")
        sys.exit(1)


def dump_chip(ser, chip, size, outpath):
    """Dump entire chip contents to a binary file."""
    print(f"Dumping {chip} ROM ({size} bytes) → {outpath}...", flush=True)

    send_cmd(ser, f"DUMP {chip} {size}")
    resp = read_line(ser)
    if not resp.startswith("DUMP"):
        print(f"ERROR: expected DUMP header, got '{resp}'")
        sys.exit(1)

    data = ser.read(size)
    if len(data) != size:
        print(f"WARNING: got {len(data)} of {size} bytes")

    with open(outpath, "wb") as f:
        f.write(data)

    nonff = sum(1 for b in data if b != 0xFF)
    print(f"  Done. {len(data)} bytes, {nonff} non-0xFF bytes.")
    return data


def scan_chip(ser, chip, filepath):
    """Write + immediate per-byte verify (SCAN command)."""
    with open(filepath, "rb") as f:
        data = f.read()

    size = len(data)
    print(f"Scanning {chip} ROM ({size} bytes — write + verify each byte)...", flush=True)

    erase_chip(ser, chip)

    send_cmd(ser, f"SCAN {chip} {size}")
    resp = read_line(ser)
    if resp != "READY":
        print(f"ERROR: expected READY, got '{resp}'")
        sys.exit(1)

    chunk_size = 256
    sent = 0
    while sent < size:
        end = min(sent + chunk_size, size)
        ser.write(data[sent:end])
        sent = end

        while ser.in_waiting:
            line = read_line(ser, timeout=0.1)
            if line.startswith("PROGRESS"):
                pct = line.split()[1]
                print(f"\r  {pct}%", end="", flush=True)

    while True:
        resp = read_line(ser, timeout=60)
        if resp.startswith("PROGRESS"):
            pct = resp.split()[1]
            print(f"\r  {pct}%", end="", flush=True)
        elif resp.startswith("SCAN OK"):
            print(f"\r  100% — PERFECT. Every byte verified.")
            return
        elif resp.startswith("SCAN FAIL"):
            parts = resp.split()
            mismatches = parts[2] if len(parts) > 2 else "?"
            first = parts[3] if len(parts) > 3 else "?"
            print(f"\r  FAILED — {mismatches} bad bytes, {first}")
            sys.exit(1)
        elif resp.startswith("ERR"):
            print(f"\n  ERROR: {resp}")
            sys.exit(1)


def flash_rom(ser, chip, filepath, do_verify, do_scan=False):
    with open(filepath, "rb") as f:
        data = f.read()

    if do_scan:
        scan_chip(ser, chip, filepath)
    else:
        erase_chip(ser, chip)
        program_chip(ser, chip, data)
        if do_verify:
            verify_chip(ser, chip, data)


def main():
    parser = argparse.ArgumentParser(description="Neo Geo MVS Flash Cart programmer")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port")
    parser.add_argument("--prom", help="P ROM binary file")
    parser.add_argument("--srom", help="S ROM binary file")
    parser.add_argument("--mrom", help="M ROM binary file")
    parser.add_argument("--c1rom", help="C1 ROM binary file")
    parser.add_argument("--c2rom", help="C2 ROM binary file")
    parser.add_argument("--v1rom", help="V1 ROM binary file (ADPCM-A samples)")
    parser.add_argument("--v2rom", help="V2 ROM binary file (ADPCM-B samples)")
    parser.add_argument("--v3rom", help="V3 ROM binary file")
    parser.add_argument("--v4rom", help="V4 ROM binary file")
    parser.add_argument("--all", help="Directory with p1.bin, s1.bin, m1.bin, c1.bin, c2.bin")
    parser.add_argument("--id", action="store_true", help="Read chip IDs")
    parser.add_argument("--verify", action="store_true", help="Verify after programming")
    parser.add_argument("--scan", action="store_true", help="Write + immediate per-byte verify")
    parser.add_argument("--dump", nargs=3, metavar=("CHIP", "SIZE", "FILE"),
                        help="Dump chip to file: --dump P 524288 p_dump.bin")
    parser.add_argument("--dump-all", help="Dump all chips to directory")
    parser.add_argument("--erase-only", help="Erase a chip without programming (P/S/M/C1/C2)")
    args = parser.parse_args()

    ser = open_port(args.port)
    ping(ser)

    if args.id:
        print("Reading chip IDs:")
        for chip in CHIPS:
            read_id(ser, chip)
        ser.close()
        return

    if args.erase_only:
        erase_chip(ser, args.erase_only)
        ser.close()
        return

    if args.dump:
        chip, size_str, outfile = args.dump
        dump_chip(ser, chip, int(size_str), outfile)
        ser.close()
        return

    if args.dump_all:
        d = args.dump_all
        os.makedirs(d, exist_ok=True)
        chip_sizes = [
            ("P", 524288, "p1.bin"),    # 512KB
            ("S", 131072, "s1.bin"),     # 128KB
            ("M", 131072, "m1.bin"),     # 128KB
            ("C1", 524288, "c1.bin"),    # 512KB
            ("C2", 524288, "c2.bin"),    # 512KB
            ("V1", 524288, "v1.bin"),    # 512KB
            ("V2", 524288, "v2.bin"),    # 512KB
            ("V3", 524288, "v3.bin"),    # 512KB
            ("V4", 524288, "v4.bin"),    # 512KB
        ]
        for chip, size, name in chip_sizes:
            dump_chip(ser, chip, size, os.path.join(d, name))
        ser.close()
        return

    if args.all:
        d = args.all
        mapping = [
            ("P",  ["p1.bin", "p.bin"]),
            ("S",  ["s1.bin", "s.bin"]),
            ("M",  ["m1.bin", "m.bin"]),
            ("C1", ["c1.bin"]),
            ("C2", ["c2.bin"]),
            ("V1", ["v1.bin"]),
            ("V2", ["v2.bin"]),
            ("V3", ["v3.bin"]),
            ("V4", ["v4.bin"]),
        ]
        for chip, names in mapping:
            for name in names:
                path = os.path.join(d, name)
                if os.path.exists(path):
                    flash_rom(ser, chip, path, args.verify, args.scan)
                    break
            else:
                print(f"  Skipping {chip} — no file found")
    else:
        chip_files = [
            ("P", args.prom), ("S", args.srom), ("M", args.mrom),
            ("C1", args.c1rom), ("C2", args.c2rom),
            ("V1", args.v1rom), ("V2", args.v2rom),
            ("V3", args.v3rom), ("V4", args.v4rom),
        ]
        for chip, filepath in chip_files:
            if filepath:
                flash_rom(ser, chip, filepath, args.verify, args.scan)

    print("\nAll done.")
    ser.close()


if __name__ == "__main__":
    main()
