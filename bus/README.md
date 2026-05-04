# NeoScan Bus

Pin-accurate SHM bus simulator for the MVS cart edge connector. Routes all 5 ROM types (P, C, S, M, V) between a cart server and the Geolith emulator via shared memory with atomic DTACK handshake.

## Architecture

448-byte shared memory at `/dev/shm/neocart_bus`, 7 cache lines (64 bytes each):

| Line | Offset | ROM | Thread |
|------|--------|-----|--------|
| 0 | 0 | P-ROM (68K program) | prog |
| 1 | 64 | C-ROM (sprites) | crom |
| 2 | 128 | S-ROM (fix layer) | srom |
| 3 | 192 | M-ROM (Z80 sound) | mrom |
| 5 | 320 | V-ROM (ADPCM audio) | vrom |
| 6 | 384 | Debug (skeleton, pause, step) | — |

## Build

```
gcc -O2 -msse2 -o shm_server shm_server.c -lpthread
gcc -O2 -c shm_client.c -o shm_client.o && ar rcs libshm_client.a shm_client.o
```

## Usage

```
./shm_server game.neo          # Start cart server
python3 neocart_gui.py [game.neo]  # Bus monitor GUI
```

## Files

- `neocart_bus.h` — SHM layout defines, inline helpers
- `shm_server.c` — Cart server (6 threads, per-ROM cache lines)
- `shm_client.c` — Client library linked into Geolith
- `neocart_gui.py` — Tkinter bus monitor with PCB view, skeleton mode, pause/step
