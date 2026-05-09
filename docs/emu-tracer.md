# Emulator Per-Frame Tracer

## Overview

The tracer records one CSV line per emulated frame, capturing CPU usage, VRAM activity, bullet state, exceptions, resets, and VBlank misses. Three layers contribute data: the Geolith core, the game's debug RAM block, and the SDL emulator frontend.

## Output

Trace file: `/tmp/danmaku_trace.csv` (created automatically on game launch, closed on quit).

### CSV Columns

| Column | Source | Meaning |
|--------|--------|---------|
| frame | emulator | Emulated frame number (from `frame_count`) |
| game_tick | debug RAM 0x10F204 | Game's tick counter (increments each game_tick call) |
| alive | debug RAM 0x10F206 | 1 if game_tick wrote 0xBEEF this frame, 0 if stale |
| active | debug RAM 0x10F200 | Active bullet count |
| curves | debug RAM 0x10F208 | Bullets with curve active |
| spawns | debug RAM 0x10F20A | Bullets spawned this frame |
| cmds | debug RAM 0x10F20C | cmd_buf entries before flush |
| slot | debug RAM 0x10F20F | Frame scheduler slot (tick & 15) |
| mode | debug RAM 0x10F20E | BIOS_SYSTEM_MODE byte (bit 7 = game active) |
| m68k_cyc | core stats | Total 68K cycles this frame (always ~202,752) |
| vram_wr | core stats | REG_VRAMRW writes this frame |
| vram_addr | core stats | REG_VRAMADDR writes this frame |
| exception | core stats | Exception type (0=none, 2=bus, 3=addr, 4=illegal, 5=divzero) |
| exc_pc | core stats | 68K PC at exception |
| vec_switch | core stats | 1=BIOS→Cart, 2=Cart→BIOS, 0=none |
| watchdog | core stats | 1 if watchdog fired this frame |
| vblank_miss | emulator | 1 if game_tick didn't advance (missed VBlank) |
| wait_spins | debug RAM 0x10F210 | .Lwait loop iterations (idle time) |
| idle_cyc | computed | wait_spins × 20 (idle cycles) |
| work_cyc | computed | 202,752 - idle_cyc (actual game_tick cost) |

## How It Works

### Geolith Core (`geolith/src/`)

`geo_frame_stats_t` struct in `geo.h`:
- Reset to zero at the top of `geo_exec()` in `geo.c`
- `vram_writes` incremented in `geo_lspc_vram_wr()` (geo_lspc.c)
- `vram_addr_sets` incremented in `geo_lspc_vramaddr_wr()` (geo_lspc.c)
- `exception` + `exception_pc` set when vector table reads occur during cart mode (geo_m68k.c)
- `vector_switch` set on REG_SWPBIOS/REG_SWPROM writes (geo_m68k.c)
- `watchdog_fired` set before `geo_reset()` (geo.c)
- Exposed to emulator via `retro_get_memory_data(110)`

### Game Debug RAM (`examples/danmaku/main.c`)

Written every frame in `game_tick()` before `SYS_vblankFlush()`:
- Bullet stats: active_count, max_bullets, curve_count
- Spawn counter: incremented in `BLT_spawn()` (sdk/src/neo_bullet.c), reset each tick
- cmd_buf usage: `neo_cmd_count` before flush
- BIOS mode bit: raw read of 0x10FD80
- Scheduler slot: `tick & 15`
- Wait cycles: `wait_cycles` from crt0.s .Lwait loop

### Wait Cycle Counter (`sdk/boot/crt0.s`)

The `.Lwait` loop spins until `vblank_flag` is set by the VBlank interrupt. Each iteration increments `wait_cycles`. After VBlank fires, game_tick reads this value. More spins = more idle time = more headroom.

Cycle cost per spin: ~20 cycles (addl + tstb + beq.s).

### SDL Emulator (`emu/neogeo_sdl.c`)

After each `core.run()`:
1. Reads game_tick from debug RAM (big-endian)
2. Compares to previous frame — if unchanged, it's a VBlank miss
3. Reads all debug RAM fields + core stats
4. Computes idle/work cycles from wait_spins
5. Writes one CSV line via `fprintf`

## Analysis

```bash
python3 tools/trace_analyze.py /tmp/danmaku_trace.csv
```

Reports:
- Stability: miss rate, exceptions, resets, watchdog fires
- Miss analysis: burst length, per-slot distribution, per-time-window
- Bullets: active/curve/spawn averages and peaks
- CPU: work/idle cycle breakdown, headroom percentage
- VRAM: writes per frame, cmd_buf usage

## Detecting Problems

| Symptom | What to check in trace |
|---------|----------------------|
| Frame drops / slowdown | `vblank_miss=1` rows. Check `work_cyc` — if near 202,752, CPU overrun |
| Game reset | `vec_switch=2` while `alive=1` |
| Illegal instruction | `exception=4`, check `exc_pc` against disassembly |
| Game freeze | `alive` stops being 1, `game_tick` stops advancing |
| Watchdog reset | `watchdog=1` |
| BIOS takeover | `mode` byte loses bit 7 |
| Spawn spike | `spawns` column shows high value on specific `slot` |
| VRAM budget | `vram_wr` shows which frames have most writes |

## Performance Baseline (250 bullets, stock 12MHz)

```
Budget: 202,752 cycles/frame
Work:   avg 191,975 (94%)  peak 202,112 (99%)
Idle:   avg  10,776 (5%)   min 640 (<1%)
Headroom: ~5% average, ~0.3% worst case
```
