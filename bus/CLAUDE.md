# Bus — SHM Cart Simulator

Pin-accurate shared memory bus between emulator and cart server. Simulates all 5 ROM types (P/S/M/V/C) at the signal level.

## Architecture

448-byte POSIX SHM region (`/neocart_bus`), 7 cache lines × 64 bytes. Atomic DTACK handshake protocol: emulator writes address → server writes data → DTACK.

## Components

| File | Purpose |
|------|---------|
| `shm_server.c` | Cart server: loads .neo ROM, serves reads from 6 threads |
| `shm_client.c` | Client lib linked into Geolith (`libshm_client.a`) |
| `neocart_bus.h` | 448-byte SHM layout, protocol constants |
| `neocart_gui.py` | Tkinter bus monitor with PCB view + skeleton mode |

## Usage

```bash
# Start server (loads ROM)
./shm_server /data/roms/kof95.neo

# Emulator auto-detects SHM when server is running
# Set NEOCART_SHM=1 env before retro_init() to force
```

## Build

```bash
gcc -O2 -o shm_server shm_server.c -lpthread -lrt
ar rcs libshm_client.a shm_client.o
```
