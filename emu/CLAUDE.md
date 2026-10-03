# Emulator — neogeo_sdl

Custom SDL2/OpenGL frontend for Geolith libretro core. Single file: `neogeo_sdl.c`.

## Build

```bash
cc -O2 -o neogeo_sdl neogeo_sdl.c $(pkg-config --cflags --libs sdl2) -ldl -lm -lGL
```

## Geolith core

Source: `../geolith/libretro/libretro.c`. **2026-10-02: the customized core source was lost** (the symlink pointed at `~/CLProjects/geolith`, gone since the 2026-09 reorg; no copy on disk, trash, git or GitHub). `~/CLProjects/geolith` is now a fresh clone of upstream libretro/geolith-libretro (1940249, builds, supports KOF99's SMA) WITHOUT our additions; the installed `geolith_libretro.so` (2026-05-09) is still the customized build, backed up in `/data/neogeo_dict/emu_backup/`. Additions to re-implement before installing a new build: `get_memory_data` regions 100 (blocked PCs), 101 (VRAM), 102 (sprite PC per slot), 103 (number of blocked PCs), 104 (palette RAM), 110 (per-frame stats struct `emu_frame_stats_t`), and the NeoCart SHM bus bridge (`NEOCART_SHM`). `--capture` (headless recorder, see the comment in neogeo_sdl.c) only needs the standard work-RAM region and runs on either core. Build: `cd ../geolith/libretro && make -j$(nproc)`. Install: `cp geolith_libretro.so ~/.config/retroarch/cores/`.

2026-10-03: `~/CLProjects/geolith` also carries a Z80 port tap for `tools/makoto3/capture.py` (`geo_z80.c` `geo_z80_port_tap` + `geo_z80_ram()`; `libretro.c` exports `retro_neoscan_z80_tap`, `retro_neoscan_z80_ram`, `retro_neoscan_sound_cmd`), built to `/data/tmp/snd98/ff3/geolith_tap.so` and **not installed**; it does nothing unless a tap is set.

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
| `key` | key name | Inject KEYDOWN (1,2,3,a-z,F1-F7,UP,DOWN,LEFT,RIGHT); the key stays held |
| `keyup` | key name | Inject KEYUP (release a held key) |
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

WASD=dirs, U/I/O/P=A/B/C/D, 1=Start, 3=Coin, F1=menu, F3=sprite panel, F5=snap, F6+key=save, F7+key=load, **F8=toggle sprite recorder**, ESC=quit.

## Sprite recorder (F8)

Streams per-frame sprite data to `/data/sonicwings/sw2/rec_<timestamp>.sprec`. Delta-compressed: only writes slots that changed. Includes palette RAM every 60 frames.

Workflow: player hits F8 to start, plays game, hits F8 to stop. Python pipeline reads .sprec → extracts animation sequences → exports .ase files.

### .sprec binary format

```
Header:  uint32 magic "SREC" (0x53524543)
         uint32 version (1)
Per frame:
         uint32 frame_number
         uint16 num_active_slots (0 = no change from prev frame)
         Per active slot:
             uint16 slot_id
             uint32 pc
             uint16 scb2, scb3, scb4
             uint8  height (tile count)
             uint16[height*2] scb1 tile+attr pairs
         Optional palette (every 60 frames):
             uint16 marker (0xFFFE)
             uint16[8192] palram
End:     uint32 marker (0xFFFFFFFF)
         uint32 total_frame_count
```

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

## Capture mode (`--capture`)
`./neogeo_sdl game.neo --capture` runs headless and unthrottled (~13x real time), driven by environment variables (full list in the comment above `capture_run` in neogeo_sdl.c): `SEQ`/`SEQ2` inputs, `POKE`, `LOAD` (start state file), `SAVE`, `RELOAD`+`RELOAD_STATE`, `SNAPS`+`SNAPDIR` (PPM), `DUMP` (64 KB work RAM), `PALDUMP` (palette RAM, both banks; the games draw from bank 1), `OUT` (one line per frame: both fighter objects + P1-owned pool objects, the same format as MAME's tools/kof96/capture/record96.lua). Python side: tools/kof96/capture/emu.py picks MAME or neogeo_sdl per game. Used for all of KOF99.
| `VRAMDUMP` | "frame:path;..." | LSPC VRAM (SCB1 $0000, fix $7000, SCB2-4 $8000-$85FF) as big-endian words: which sprites show which tiles, where, in which palette (tools/brawler/portraits.py) |
