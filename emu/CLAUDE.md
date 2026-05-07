# Emulator — neogeo_sdl

Custom SDL2/OpenGL frontend for Geolith libretro core. Single file: `neogeo_sdl.c`.

## Build

```bash
cc -O2 -o neogeo_sdl neogeo_sdl.c $(pkg-config --cflags --libs sdl2) -ldl -lm -lGL
```

## Geolith core

Source: `../geolith/libretro/libretro.c`. Build: `cd ../geolith/libretro && make -j$(nproc)`. Install: `cp geolith_libretro.so ~/.config/retroarch/cores/`.

Custom memory IDs via `retro_get_memory_data()`:

| ID | Type | What |
|----|------|------|
| 100 | `uint32_t[64]` | Blocked PCs array |
| 101 | `uint16_t[65536]` | VRAM direct |
| 102 | `uint32_t[382]` | Sprite writer PC (68K PC per sprite slot) |
| 103 | `int*` | Pointer to num_blocked_pcs |
| 104 | `uint16_t[8192]` | Palette RAM (16KB) |
| 199 | trigger | Force rerender + video callback |

## Script engine

Scripts are plain text: `<frame> <command> [arg]`. Loaded with `--script path`.

| Command | Arg | What |
|---------|-----|------|
| `key` | key name | Inject KEYDOWN (1,2,3,a-z,F1-F7,UP,DOWN,LEFT,RIGHT) |
| `snap` | path.ppm | Screenshot to PPM |
| `vram` | path.bin | Dump 128KB VRAM |
| `sprdump` | path.bin | Dump sprites + PCs + palette (v2 format, 69KB) |
| `quit` | — | Exit emulator |

### sprdump v2 binary format

```
Header:  uint32 magic "SPRD" (0x53505244)
         uint32 version (2)
         uint32 frame_number
Per slot (382x):
         uint32 pc           — 68K PC that last wrote this slot
         uint16 scb2          — shrink (h_shrink<<8 | v_shrink)
         uint16 scb3          — y_raw(9) | sticky(1) | height(6)
         uint16 scb4          — x_pos(9) | unused(7)
         uint16[64] scb1      — 32 tile+attr pairs
Trailer: uint16[8192] palram  — full palette RAM (v2 only)
```

## Controls

WASD=dirs, U/I/O/P=A/B/C/D, 1=Start, 3=Coin, F1=menu, F3=sprite panel, F5=snap, F6+key=save, F7+key=load, ESC=quit.

## Sprite debug panel (F3)

Groups active sprite chains by 68K PC. Scroll with mouse wheel. Click to select a PC group. ENTER hides that PC's sprites (strips layers). Backspace unhides all.

## Save states

36 slots per game (a-z, 0-9). Files: `~/.config/retroarch/saves/<game>.st<slot>`. Auto-loads slot 's' on boot.

## VRAM layout (Neo Geo)

| Region | Address | Content |
|--------|---------|---------|
| SCB1 | 0x0000-0x6FFF | Tile/attr pairs, 64 words per sprite slot |
| SCB2 | 0x8000 | Shrink data per slot |
| SCB3 | 0x8200 | Y position + sticky bit + height |
| SCB4 | 0x8400 | X position |

SCB1 tile entry: word0 = tile_number[15:0], word1 = [palette:8][vflip:1][hflip:1][auto_anim:2][tile_hi:4].
