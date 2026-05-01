#!/usr/bin/env python3
"""ROM server — loads P-ROM binary, serves word reads over TCP."""
import socket, struct, array

def main():
    p1 = open('/home/bruno/NeoGeo/roms/rbff2/240-p1.p1', 'rb').read()
    p2 = open('/home/bruno/NeoGeo/roms/rbff2/240-p2.sp2', 'rb').read()
    rom = array.array('H')
    rom.frombytes(p1 + p2)
    rom.byteswap()
    print(f"ROM loaded: {len(rom)} words")
    print(f"  word[0] = 0x{rom[0]:04X}")
    print(f"  word[1] = 0x{rom[1]:04X}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 41114))
    srv.listen(1)
    print(f"Serving on port 41114")

    conn, addr = srv.accept()
    print(f"MAME connected from {addr}")

    count = 0
    bank = 0
    while True:
        header = conn.recv(4)
        if len(header) < 4:
            break
        cmd, byte_addr = struct.unpack('>HH', header)
        # Extended address for > 16 bits
        if cmd == 0x0001:  # READ
            ext = conn.recv(2)
            full_addr = (byte_addr << 16) | struct.unpack('>H', ext)[0]
            word_addr = full_addr // 2
            word = rom[word_addr] if word_addr < len(rom) else 0xFFFF
            conn.sendall(struct.pack('>H', word))
            count += 1
            if count % 1000000 == 0:
                print(f"  {count//1000000}M reads")
        elif cmd == 0x0002:  # WRITE (bankswitch)
            ext = conn.recv(4)
            full_addr = (byte_addr << 16) | struct.unpack('>H', ext[:2])[0]
            data = struct.unpack('>H', ext[2:4])[0]
            bank = data & 7
            print(f"  BANKSWITCH to {bank}")
            conn.sendall(struct.pack('>H', 0))
        elif cmd == 0xFFFF:  # QUIT
            break

    conn.close()
    srv.close()
    print(f"Done — {count} total reads")

if __name__ == '__main__':
    main()
