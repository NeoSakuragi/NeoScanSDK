#!/usr/bin/env python3
"""ROM server — loads P-ROM binary, serves word reads over TCP."""
import socket, struct, array

def main():
    p1 = open('/home/bruno/NeoGeo/roms/rbff2/240-p1.p1', 'rb').read()
    p2 = open('/home/bruno/NeoGeo/roms/rbff2/240-p2.sp2', 'rb').read()
    rom = array.array('H')
    rom.frombytes(p1 + p2)
    # ROM files are little-endian words, keep as-is — send as big-endian over TCP
    print(f"ROM loaded: {len(rom)} words")
    print(f"  word[0] = 0x{rom[0]:04X}")
    print(f"  word[1] = 0x{rom[1]:04X}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 41114))
    srv.listen(1)
    print(f"Serving on port 41114")

    while True:
        print("Waiting for MAME...")
        conn, addr = srv.accept()
        print(f"MAME connected from {addr}")
        try:
            serve_client(conn, rom)
        except Exception as e:
            print(f"Client error: {e}")
        conn.close()
        print("Client disconnected")

def serve_client(conn, rom):

    count = 0
    while True:
        # Client sends 6 bytes: [cmd_hi, cmd_lo, addr_b3, addr_b2, addr_b1, addr_b0]
        pkt = b''
        while len(pkt) < 6:
            chunk = conn.recv(6 - len(pkt))
            if not chunk:
                break
            pkt += chunk
        if len(pkt) < 6:
            break

        cmd = (pkt[0] << 8) | pkt[1]
        byte_addr = (pkt[2] << 24) | (pkt[3] << 16) | (pkt[4] << 8) | pkt[5]

        if cmd == 1:  # READ
            word_addr = byte_addr // 2
            word = rom[word_addr] if word_addr < len(rom) else 0xFFFF
            conn.sendall(struct.pack('>H', word))
            count += 1
            if count % 1000000 == 0:
                print(f"  {count//1000000}M reads")
        elif cmd == 2:  # WRITE (bankswitch)
            # Client sends 8 bytes total for write: 6 + 2 data
            data_pkt = b''
            while len(data_pkt) < 2:
                chunk = conn.recv(2 - len(data_pkt))
                if not chunk: break
                data_pkt += chunk
            data = struct.unpack('>H', data_pkt)[0]
            print(f"  BANK={data & 7}")
            conn.sendall(struct.pack('>H', 0))
        else:
            break

    print(f"  Session: {count} reads")

if __name__ == '__main__':
    main()
