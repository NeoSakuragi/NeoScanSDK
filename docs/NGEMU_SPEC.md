# NG-EMU — Custom Neo Geo Emulator Specification

Purpose-built Neo Geo emulator for NeoScanSDK homebrew development.
Replaces MAME dependency with a lean, SHM-native, debug-first engine.

---

## 1. Goals

| Priority | Goal |
|----------|------|
| P0 | Run NeoScanSDK homebrew ROMs (.neo format) correctly |
| P0 | Full SHM bus connectivity (drop-in replacement for MAME neocart driver) |
| P0 | Accurate enough for homebrew dev (not bit-perfect arcade preservation) |
| P1 | GPU-accelerated rendering (SDL2 + OpenGL/Vulkan) |
| P1 | Step-through debugging (pause, single-step 68K, watch registers) |
| P1 | Multi-threaded: PROG bus + CHA bus on separate threads |
| P2 | Tile-by-tile frame build visualization |
| P2 | Bus trace recording/replay |
| P2 | Integration with neocart_gui.py |

**Non-goals:** Neo Geo CD, encryption/protection emulation, MAME compatibility, arcade preservation accuracy.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    NG-EMU Process                    │
│                                                     │
│  ┌─────────┐   12 MHz    ┌──────────┐  4 MHz       │
│  │  68000   │◄──────────►│   Z80    │              │
│  │  (CPU)   │            │  (Sound) │              │
│  └────┬─────┘            └────┬─────┘              │
│       │                       │                     │
│  ┌────▼─────────────────┐ ┌──▼──────┐              │
│  │   Memory Controller  │ │ YM2610  │──► Audio Out  │
│  │   (NEO-C1 decode)    │ │ (jt12)  │              │
│  └────┬─────────────────┘ └─────────┘              │
│       │                                             │
│  ┌────▼─────────────────────────────────┐           │
│  │         LSPC2 Video Engine           │           │
│  │  Sprites (C-ROM) + Fix (S-ROM)       │           │
│  │  Line buffer → Palette → Framebuffer │           │
│  └──────────────────────┬───────────────┘           │
│                         │                           │
│  ┌──────────────────────▼───────────────┐           │
│  │    SDL2/OpenGL Display (320×224)     │           │
│  └──────────────────────────────────────┘           │
│                                                     │
│  ┌──────────────────────────────────────┐           │
│  │   SHM Bridge (/dev/shm/neocart_bus) │◄──────────┤── External ROM Server
│  │   32-byte atomic bus protocol        │           │   (shm_server / FPGA)
│  └──────────────────────────────────────┘           │
└─────────────────────────────────────────────────────┘
```

### Two ROM modes

1. **Embedded mode** — NG-EMU loads .neo file directly into RAM, serves ROMs internally (default, fast)
2. **SHM mode** — NG-EMU drives the 32-byte SHM bus as the MVS side, external shm_server or FPGA serves ROMs (dev/debug mode, pin-accurate)

In SHM mode the emulator IS the MVS — it writes addresses + control signals, waits for DTACK, reads data. Identical protocol to the current MAME neocart driver.

---

## 3. Timing Model

Reference: FBNeo + MiSTer FPGA core (Furrtek).

### Clocks

| Clock | Frequency | Source |
|-------|-----------|--------|
| Master | 24.000 MHz | Crystal |
| 68000 | 12.000 MHz | Master / 2 |
| Z80 | 4.000 MHz | Master / 6 |
| Pixel | 6.000 MHz | Master / 4 |
| LSPC | 24.000 MHz | Master |

### Frame structure

- **264 scanlines** per frame (8 vblank top + 224 active + 32 vblank bottom)
- **384 pixel clocks** per scanline (320 active + 64 hblank)
- **Refresh rate:** 59.185606 Hz = 24000000 / (264 × 384)
- **68K cycles per frame:** 12000000 / 59.185606 ≈ 202,702
- **68K cycles per scanline:** 202,702 / 264 ≈ 768
- **Z80 cycles per frame:** 4000000 / 59.185606 ≈ 67,567
- **Z80 cycles per scanline:** 67,567 / 264 ≈ 256

### Scanline schedule

```
Scanline 248 (0xF8):  VBlank start → assert IRQ4 (VBlank interrupt)
Scanline 0-247:       Active display
                       IRQ1 fires at programmable raster line (nIRQOffset)
                       IRQ3: timer interrupt (unused by most games)
Scanline 255-263:     VBlank continues
```

### CPU interleaving

Run 68K for one scanline (~768 cycles), then run Z80 proportionally (~256 cycles).
Synchronize Z80 at sound command writes (port $00 from 68K → Z80 NMI).

```
for each frame:
    for scanline = 0..263:
        run_68k(768 cycles)
        sync_z80_to(proportional_cycle)
        if scanline == vblank_line: assert_irq4()
        if scanline == raster_line: assert_irq1()
        render_scanline(scanline)  // if in active range
    end
    mix_audio_frame()
    present_framebuffer()
end
```

---

## 4. Memory Map — 68000

### Address decoding (NEO-C1 logic)

| Address Range | Size | Description | Signal |
|---------------|------|-------------|--------|
| $000000-$0FFFFF | 1MB | System ROM (BIOS/UniBIOS) | nSYSROM |
| $100000-$10FFFF | 64KB | Work RAM | nWRAM |
| $200000-$2FFFFF | 1MB+ | P-ROM bank 0 (cartridge) | nROMOE |
| $300000-$3FFFFF | - | I/O & system registers | (decoded) |
| $400000-$7FFFFF | 4MB | P-ROM banks 1+ (bankswitch) | nPORTOE |
| $800000-$BFFFFF | - | Memory card | nCARD |
| $C00000-$CFFFFF | - | BIOS extension ROM | nROMOEL |
| $D00000-$DFFFFF | 64KB | Backup SRAM | nSRAMOE |

### I/O registers ($300000 range)

| Address | R/W | Description |
|---------|-----|-------------|
| $300000 | R | REG_P1CNT — Player 1 inputs |
| $300001 | W | Watchdog kick |
| $340000 | R | REG_P2CNT — Player 2 inputs |
| $380000 | R | REG_STATUS_A — System status (coin, service) |
| $380051 | W | REG_SWPROM — Select P-ROM bank zone |
| $3A0001 | W | REG_NOSHADOW — Disable shadow mode |
| $3A0003 | W | REG_SHADOW — Enable shadow/dark palette |
| $3A0011 | W | REG_SWPBIOS — Select system ROM vector |
| $3A0013 | W | REG_CRDUNLOCK1 — Memory card unlock |
| $3A001B | W | REG_CRDUNLOCK2 — Memory card unlock |
| $3C0000 | R | REG_VRAMADDR — VRAM address (read back) |
| $3C0000 | W | REG_VRAMADDR — Set VRAM address |
| $3C0002 | R/W | REG_VRAMRW — VRAM data read/write |
| $3C0004 | W | REG_VRAMMOD — VRAM address auto-increment |
| $3C0006 | R | REG_HCOUNT — Horizontal pixel counter |
| $3C0006 | W | REG_TIMERHIGH — Timer high bits |
| $3C0008 | W | REG_TIMERLOW — Timer low bits |
| $3C000A | W | REG_IRQACK — IRQ acknowledge (write bit = ack that level) |
| $3C000C | W | REG_TIMERSTOP — Timer stop control |

### VRAM layout (64KB slow + 4KB fast)

```
Slow VRAM (64KB):
  $0000-$6FFF  Sprite Control Block (SCB1) — tile numbers + palette
               Each sprite: 16-bit tile_number | (palette << 8) | flags
               Up to 381 sprites × 64 tiles each (max)
  $8000-$81FF  SCB2 — horizontal shrink table
  $8200-$83FF  SCB3 — Y position + size + chain flag
  $8400-$85FF  SCB4 — X position
  $E000-$EFFF  Fix layer tilemap — 40×32 = 1280 tiles × 16-bit

Fast VRAM (4KB):
  $0000-$0FFF  Palette indices (not addressable directly — internal)
```

---

## 5. Video Engine (LSPC2)

### Sprite rendering

384 sprites max, evaluated per scanline. Each sprite is a vertical chain of 8×16 pixel tiles.

**SCB1 — Tile data** (at VRAM $0000):
```
For sprite N, tile T:
  VRAM[N*64 + T] = tile_number[19:0] (low 16) | auto_anim[1:0] | flip_x | flip_y
  VRAM[N*64 + T + $10000 offset] = palette[7:0] (bits 8-15 of word)
```

**SCB2 — Horizontal shrink** (at VRAM $8000):
```
VRAM[$8000 + N] = hshrink[3:0]  (0=full width, $F=1 pixel)
```

**SCB3 — Y position + chain** (at VRAM $8200):
```
VRAM[$8200 + N] = sticky[6] | ypos[8:0] (bits 7-15) | size[5:0] (bits 0-5)
```
- sticky=1: chain to previous sprite (inherit Y, continue vertically)
- ypos: 9-bit, range 496-0-255 (wraps, display at 0-223)
- size: number of tiles in chain (0-32)

**SCB4 — X position** (at VRAM $8400):
```
VRAM[$8400 + N] = xpos[8:0] (bits 7-15)
```
- 9-bit signed, display range 0-319

**Vertical shrink:** Applied per-tile via vshrink LUT. Each tile's 16 rows are selectively drawn based on shrink value (0=$FF=all 16 rows, smaller = fewer rows).

**C-ROM tile decode (4bpp planar, 128 bytes per 16×16 tile):**
```
Tile data layout (128 bytes = 8 bytes × 16 rows):
  Row Y (0-15):
    Byte offset = Y * 4 (for planes 0-1) or 64 + Y * 4 (for planes 2-3)
    Planes 0,1: interleaved at bytes [Y*4 + 0..3]
    Planes 2,3: interleaved at bytes [64 + Y*4 + 0..3]

  For each pixel X (0-15):
    bit0 = C1_ROM[ tile*64 + row*4 + (x/8)*2     ] >> (7 - x%8) & 1
    bit1 = C1_ROM[ tile*64 + row*4 + (x/8)*2 + 1 ] >> (7 - x%8) & 1
    bit2 = C2_ROM[ tile*64 + row*4 + (x/8)*2     ] >> (7 - x%8) & 1
    bit3 = C2_ROM[ tile*64 + row*4 + (x/8)*2 + 1 ] >> (7 - x%8) & 1
    pixel = (bit3<<3) | (bit2<<2) | (bit1<<1) | bit0
```

In .neo format, C1 and C2 are pre-interleaved: `crom[i*2]` = C1, `crom[i*2+1]` = C2.

**Rendering order:** sprites are drawn in slot order, so a HIGHER slot number is drawn in front of a lower one. Fix layer is always on top of sprites. The backdrop colour is palette word $FFF ($401FFE).

### Fix layer (S-ROM)

40×32 grid of 8×8 tiles. Tilemap at VRAM $E000.

```
tile_word = VRAM[$E000 + col*32 + row]
tile_index = tile_word & 0x0FFF     (12 bits → 4096 tiles)
palette    = (tile_word >> 12) & 0xF (4 bits → 16 palettes)
```

**S-ROM tile decode (4bpp, 32 bytes per 8×8 tile):**
```
For row Y (0-7):
  byte0 = SROM[tile*32 + Y]       // planes 0+1
  byte1 = SROM[tile*32 + Y + 8]
  byte2 = SROM[tile*32 + Y + 16]  // planes 2+3
  byte3 = SROM[tile*32 + Y + 24]

  For pixel X (0-7):
    bit0 = (byte0 >> (7-X)) & 1
    bit1 = (byte1 >> (7-X)) & 1
    bit2 = (byte2 >> (7-X)) & 1
    bit3 = (byte3 >> (7-X)) & 1
    pixel = (bit3<<3) | (bit2<<2) | (bit1<<1) | bit0
```

Color index 0 in any palette = transparent.

### Palette system

Two banks of 256 palettes × 16 colors = 8192 entries. Active bank selected by REG_PALBANK.

**16-bit color format:**
```
Bit:  15  14  13  12  11-8  7-4  3-0
      DR  DG  Dc  DB  R3-0  G3-0 B3-0

R = (R3:R0 << 2) | (DR << 1) | Dc   → 6-bit red
G = (G3:G0 << 2) | (DG << 1) | Dc   → 6-bit green
B = (B3:B0 << 2) | (DB << 1) | Dc   → 6-bit blue
```

Each 6-bit channel → 8-bit via resistor-weighted DAC lookup (not linear shift).

**Shadow mode:** When enabled via $3A0003, all colors pass through a darkening resistor network (~50% brightness). Games use this for fade effects and shadows.

---

## 6. Sound System

### Z80 (4 MHz)

**Memory map:**
| Range | Size | Description |
|-------|------|-------------|
| $0000-$7FFF | 32KB | M-ROM bank 0 (fixed) |
| $8000-$BFFF | 16KB | M-ROM bank 1 (switchable) |
| $C000-$DFFF | 8KB | M-ROM bank 2 (switchable) |
| $E000-$EFFF | 4KB | M-ROM bank 3 (switchable) |
| $F000-$F7FF | 2KB | Work RAM |
| $F800-$FFFF | 2KB | Work RAM (mirror) |

**I/O ports:**
| Port | R/W | Description |
|------|-----|-------------|
| $00 | R | Sound command from 68K (triggers NMI on write from 68K) |
| $00 | W | Clear sound command pending |
| $04 | R/W | YM2610 address port A |
| $05 | R/W | YM2610 data port A |
| $06 | R/W | YM2610 address port B |
| $07 | R/W | YM2610 data port B |
| $08 | W | ROM bank switch (bank 0) |
| $09 | W | ROM bank switch (bank 1) |
| $0A | W | ROM bank switch (bank 2) |
| $0B | W | ROM bank switch (bank 3) |
| $0C | W | Reply to 68K |
| $18 | W | NMI enable/disable |

### YM2610 (OPNB)

- 4 FM channels (SSG-EG capable)
- 3 SSG channels (AY-3-8910 compatible, via jt49 core)
- 6 ADPCM-A channels (drum/voice samples from V-ROM, 18.5 kHz fixed rate)
- 1 ADPCM-B channel (streaming samples from V-ROM, variable rate 2-55.5 kHz)

**Audio output:** 16-bit stereo PCM at ~55.93 kHz (master / 432).

For homebrew dev, use **jt12** (Jose Tejada's YM2610 implementation) as reference for the sound core. It's already proven in MiSTer.

---

## 7. SHM Bus Protocol

Reuse `neocart_bus.h` exactly as-is. In SHM mode, NG-EMU acts as the MVS side:

### PROG bus operations (68K → P-ROM, YM2610 → V-ROM)

```c
// P-ROM read at word address A:
bus_set_paddr(shm, A);
shm[PROG_CTRL] &= ~PROG_ROMOE_n;           // assert ROMOE
while (shm[PROG_ACK] & PROG_DTACK_n) {}    // wait DTACK
uint16_t data = bus_get_pdata(shm);         // read data
shm[PROG_CTRL] |= PROG_ROMOE_n;            // deassert ROMOE
while (!(shm[PROG_ACK] & PROG_DTACK_n)) {} // wait DTACK release
```

### CHA bus operations (LSPC → C-ROM, Fix → S-ROM, Z80 → M-ROM)

```c
// C-ROM read:
bus_set_caddr(shm, tile_addr);
shm[CHA_CTRL] &= ~CHA_PCK1B;               // clock edge
while (shm[CHA_ACK] & CHA_CROM_DTACK_n) {}
uint8_t pixel = shm[CHA_CDATA_0];
shm[CHA_CTRL] |= CHA_PCK1B;
while (!(shm[CHA_ACK] & CHA_CROM_DTACK_n)) {}

// S-ROM read:
bus_set_saddr(shm, fix_addr);
shm[CHA_CTRL] &= ~CHA_SROM_OE_n;
while (shm[CHA_ACK] & CHA_SROM_DTACK_n) {}
uint8_t tile_byte = shm[CHA_SDATA];
shm[CHA_CTRL] |= CHA_SROM_OE_n;
while (!(shm[CHA_ACK] & CHA_SROM_DTACK_n)) {}

// M-ROM read:
bus_set_maddr(shm, z80_addr);
shm[CHA_CTRL] &= ~CHA_MROM_OE_n;
while (shm[CHA_ACK] & CHA_MROM_DTACK_n) {}
uint8_t opcode = shm[CHA_MDATA];
shm[CHA_CTRL] |= CHA_MROM_OE_n;
while (!(shm[CHA_ACK] & CHA_MROM_DTACK_n)) {}
```

All operations use `__ATOMIC_SEQ_CST`. Debug pause/step via bytes 30-31 honored by both sides.

---

## 8. ROM Loading (.neo format)

```
Offset  Size   Field
0x00    4      Magic "NEO\x01"
0x04    4      P-ROM size (LE)
0x08    4      S-ROM size (LE)
0x0C    4      M-ROM size (LE)
0x10    4      V1-ROM size (LE)
0x14    4      V2-ROM size (LE, usually 0)
0x18    4      C-ROM size (LE, interleaved C1+C2)
0x1C    4      Year
0x20    4      Genre
0x24    4      Screenshot offset
0x28    4      NGH number
0x2C    32     Game name (ASCII, zero-padded)
0x4C    3820   Reserved

[4096-byte header]
[P-ROM: word-swapped for 68K big-endian]
[S-ROM]
[M-ROM]
[V1-ROM]
[V2-ROM]  (if size > 0)
[C-ROM: interleaved C1[0],C2[0],C1[1],C2[1]...]
```

In embedded mode, all ROMs loaded into malloc'd arrays. In SHM mode, only BIOS loaded locally — cart ROMs served by external shm_server.

---

## 9. Input System

### Controller mapping

```
P1/P2 bits (active low):
  Bit 0: Up
  Bit 1: Down
  Bit 2: Left
  Bit 3: Right
  Bit 4: A
  Bit 5: B
  Bit 6: C
  Bit 7: D

System bits ($380000):
  Bit 0: Coin 1
  Bit 1: Coin 2
  Bit 6: Start 1
  Bit 7: Start 2
```

SDL2 keyboard + gamepad mapping. Configurable via JSON or command-line.

---

## 10. Debug Features

### CPU debugger
- Pause/resume execution
- Single-step 68K (one instruction)
- Single-step Z80
- Register inspector (D0-D7, A0-A7, PC, SR, SP for 68K; AF, BC, DE, HL, IX, IY, SP, PC for Z80)
- Memory hex viewer (any address range)
- Breakpoints (PC address, memory read/write watchpoints)
- Disassembly window (current PC ± context)

### Video debugger
- Tile-by-tile frame builder (watch sprites render one at a time)
- VRAM hex viewer (slow VRAM, fast VRAM)
- Sprite list viewer (all 384 sprite attributes)
- Fix layer tilemap viewer
- Palette viewer (both banks, live)
- C-ROM tile browser (navigate all tiles in ROM)

### Bus trace
- Record all SHM bus transactions to ring buffer
- Export trace to CSV/binary for analysis
- Per-ROM-family read counters (already in shm_server stats_thread)

### Integration
- neocart_gui.py connects via the same SHM — sees pin activity in real time
- Debug control bytes 30-31 work identically (GUI can pause/step the emulator)

---

## 11. Technology Stack

| Component | Library/Approach |
|-----------|-----------------|
| Language | C (core) + Python (tooling/GUI) |
| 68000 CPU | Musashi (reference) or custom interpreter |
| Z80 CPU | z80ex or CZ80 (FBNeo's Z80) |
| YM2610 | jt12/jt49 C model (from Jose Tejada's cores) or Nuked-OPN2 adapted |
| Display | SDL2 + OpenGL 3.3 (shader-based scanlines, scaling) |
| Audio | SDL2 audio (ring buffer, 48 kHz output) |
| Input | SDL2 gamecontroller + keyboard |
| SHM | POSIX shared memory (/dev/shm/neocart_bus) |
| Build | Makefile (gcc/clang, -O2 -march=native) |

### CPU core selection rationale

**Musashi** (68K): Battle-tested in MAME, clean C API, cycle-accurate enough. ~50 KLOC but well-structured. Alternative: custom interpreter if we want tighter SHM integration.

**CZ80** (Z80): FBNeo's Z80 core. Small, fast, proven in Neo Geo context. Alternative: z80ex for closer cycle accuracy.

**YM2610:** The hardest part. Options:
1. **MAME's ym2610 core** — proven but GPL and deeply coupled to MAME's sound system
2. **Nuked-OPN2** (adapted) — cycle-accurate OPN2, would need ADPCM-A/B additions
3. **jt12 C model** — Jose Tejada's Verilog core has a C behavioral model, used in MiSTer
4. **Custom from datasheet** — FM synthesis is well-documented, ADPCM-A/B are the tricky parts

Recommendation: Start with a simplified YM2610 that handles ADPCM-A (samples) and basic FM. Full SSG + ADPCM-B can come later. For homebrew dev, ADPCM-A playback + FM channels cover 90% of use cases.

---

## 12. File Structure

```
emu/
├── Makefile
├── src/
│   ├── main.c              — Entry point, SDL init, main loop
│   ├── neogeo.c            — Top-level machine state, reset, frame tick
│   ├── neogeo.h            — Shared state struct, constants
│   ├── cpu_68k.c           — 68K wrapper (Musashi integration)
│   ├── cpu_z80.c           — Z80 wrapper
│   ├── memory.c            — Address decoding, read/write handlers (NEO-C1)
│   ├── video.c             — LSPC2: sprite + fix rendering, VRAM, palette
│   ├── video_render.c      — Scanline renderer, line buffer compositing
│   ├── sound.c             — YM2610 integration, audio mixing
│   ├── input.c             — SDL2 input → Neo Geo button state
│   ├── shm_bridge.c        — SHM bus client (reuses neocart_bus.h)
│   ├── rom_loader.c        — .neo file parser + ROM loading
│   ├── debug.c             — Breakpoints, single-step, trace
│   └── display.c           — SDL2/OpenGL window, scaling, shaders
├── include/
│   └── neocart_bus.h       — Symlink to hardware/neocart/sim/neocart_bus.h
├── lib/
│   ├── musashi/            — 68K CPU core
│   └── cz80/               — Z80 CPU core
└── shaders/
    ├── scanline.frag       — CRT scanline effect
    └── scale.vert          — Integer scaling vertex shader
```

---

## 13. Build & Run

```bash
# Build
cd emu && make

# Run with embedded ROM (fast, self-contained)
./ngemu game.neo

# Run in SHM mode (connect to external ROM server)
./ngemu --shm                     # uses /dev/shm/neocart_bus
./ngemu --shm --bios unibios.rom  # specify BIOS

# Debug mode
./ngemu game.neo --debug           # start paused, open debugger
./ngemu game.neo --trace           # record bus trace
./ngemu game.neo --step-render     # tile-by-tile frame build
```

---

## 14. Implementation Phases

### Phase 1 — Boot to title screen
- 68K + memory map + BIOS boot
- Embedded ROM loading (.neo)
- Basic video (fix layer only — enough to see BIOS text)
- SDL2 window + input
- **Milestone:** UniBIOS menu appears and responds to input

### Phase 2 — Sprites + playable
- Full sprite rendering (SCB1-4, shrink, chain)
- Palette system (both banks, shadow)
- P-ROM banking
- **Milestone:** hello_neo demo runs correctly

### Phase 3 — Sound
- Z80 CPU + M-ROM banking
- YM2610 (FM + ADPCM-A at minimum)
- 68K↔Z80 communication (sound commands, NMI)
- **Milestone:** jukebox example plays music

### Phase 4 — SHM bridge
- SHM bus client (MVS side)
- Per-read P/S/C/M/V-ROM through shared memory
- Debug pause/step integration
- **Milestone:** Runs with shm_server serving ROMs, neocart_gui shows live bus

### Phase 5 — Debug tools
- CPU debugger (breakpoints, registers, disassembly)
- Video debugger (VRAM viewer, tile browser, sprite list)
- Bus trace recording
- Step-through rendering
- **Milestone:** Can debug a broken sprite by watching VRAM + C-ROM reads

---

## 15. Reference Sources

| Source | What to extract |
|--------|----------------|
| **MiSTer NeoGeo** (Furrtek) | LSPC2 scanline timing, NEO-C1 address decode, clock domains, VRAM state machine |
| **FBNeo** | Frame loop structure, sprite attribute parsing, IRQ scheduling, palette math |
| **MAME neogeo driver** | Memory map edge cases, protection variants (not needed for homebrew) |
| **dev-docs (NeoGeo Dev Wiki)** | Register reference, VRAM layout, hardware quirks |
| **NeoScanSDK shm_server** | SHM protocol (already built, proven, atomic) |
| **jt12/jt49** (Jose Tejada) | YM2610 behavioral model, ADPCM decode |
