#!/usr/bin/env python3
"""Shared memory ROM server — watches for address requests, writes ROM data back."""
import mmap, struct, array, time, os

SHM_PATH = "/dev/shm/neocart_rom"
SHM_SIZE = 16

# Load ROM
p1 = open('/home/bruno/NeoGeo/roms/rbff2/240-p1.p1', 'rb').read()
p2 = open('/home/bruno/NeoGeo/roms/rbff2/240-p2.sp2', 'rb').read()
rom = array.array('H')
rom.frombytes(p1 + p2)
# No byteswap — little-endian array matches MAME's ROM_LOAD16_WORD_SWAP format
print(f"ROM: {len(rom)} words, word[0]=0x{rom[0]:04X}")

# Create shared file in /dev/shm
with open(SHM_PATH, 'wb') as f:
    f.write(b'\x00' * SHM_SIZE)
fd = os.open(SHM_PATH, os.O_RDWR)
buf = mmap.mmap(fd, SHM_SIZE)
os.close(fd)
buf[:SHM_SIZE] = b'\x00' * SHM_SIZE

print("Shared memory ready — waiting for MAME")

count = 0
t0 = time.time()
import ctypes
# Get raw pointer for volatile access
buf_ptr = ctypes.c_char_p(ctypes.addressof(ctypes.c_char.from_buffer(buf)))
raw = (ctypes.c_uint8 * SHM_SIZE).from_buffer(buf)

try:
    while True:
        while raw[7] == 0:
            pass

        byte_addr = raw[0] | (raw[1]<<8) | (raw[2]<<16) | (raw[3]<<24)
        word_addr = byte_addr // 2
        word = rom[word_addr] if word_addr < len(rom) else 0xFFFF

        raw[4] = word & 0xFF
        raw[5] = (word >> 8) & 0xFF
        raw[6] = 1
        raw[7] = 0

        count += 1
        if count % 1000000 == 0:
            elapsed = time.time() - t0
            print(f"  {count//1000000}M reads ({count/elapsed/1000:.0f}K reads/sec)")
except KeyboardInterrupt:
    print(f"\nDone: {count} reads")
finally:
    os.unlink(SHM_PATH)
