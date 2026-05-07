# NeoScanSDK

Neo Geo homebrew development ecosystem: SDK, emulator, hardware, asset tools.

## Emulator

**We built our own.** It is `emu/neogeo_sdl` — a standalone SDL2 frontend for the Geolith libretro core. NOT MAME. NOT RetroArch. Kill any stale instances with `pkill -f neogeo_sdl` before launching a new one.

```bash
# Build
cd emu && cc -O2 -o neogeo_sdl neogeo_sdl.c $(pkg-config --cflags --libs sdl2) -ldl -lm -lGL

# Run
./emu/neogeo_sdl /data/roms/game.neo

# Run with script
./emu/neogeo_sdl /data/roms/game.neo --script path/to/script.script
```

Geolith core lives at `geolith/` (symlink) and installs to `~/.config/retroarch/cores/geolith_libretro.so`. Rebuild with `cd geolith/libretro && make -j$(nproc)`, then copy the .so.

## ROMs

All ROMs use `.neo` format (4096-byte header + P/S/M/V1/V2/C concatenated). ROMs live in `/data/roms/` (outside repo). Header offsets: P@0x04, S@0x08, M@0x0C, V1@0x10, V2@0x14, C@0x18 (all LE uint32).

## SDK

C dev kit in `sdk/`. Build with `make -C sdk`. Headers in `sdk/include/neo_*.h`, library outputs `sdk/lib/libneoscan.a`. Uses VASM assembler targeting 68000.

## Build a game

```bash
cd examples/hello_neo && make       # builds hello_neo.neo
```

After `make`, always re-copy donor ROMs and regenerate softlist if ADPCM-B changed.

## Directory map

| Directory | What |
|-----------|------|
| `sdk/` | C dev kit (headers, source, boot, linker scripts) |
| `emu/` | SDL2 emulator frontend + Geolith integration |
| `bus/` | SHM pin-accurate cart bus simulator |
| `hardware/neocart/` | FPGA dev cart (ECP5, KiCad, Verilog, firmware) |
| `tools/` | Python scripts: ROM build, asset extraction, audio, debug |
| `examples/` | Reference games (hello_neo, jukebox, sound_lab, etc.) |
| `docs/` | Project specs (emulator arch, sound engine, bytecode) |

## Sound

REG_SOUND is at 0x320000 (NOT 0x320001). SNK sound drivers need cmd 0x07 to unlock music playback; SFX work without it.

## Key conventions

- Neo Geo has NO background layer. Everything (backgrounds + sprites) renders through 381 sprite slots.
- C-ROM tiles: 16x16, 4bpp planar, 128 bytes/tile. Bitplane order: [bp0, bp2, bp1, bp3].
- Always `pkill -f neogeo_sdl` before launching a new emulator instance.
- MAME green screen after 10 seconds = boot loop, ROM data is broken.
