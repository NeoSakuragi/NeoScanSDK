# Danmaku Bullet Engine

## Overview

360-sprite bullet pool on Neo Geo 68K (12MHz), running at solid 60fps with 250 active bullets, 138 curving, two enemy patterns. Built from scratch on the NeoScan SDK.

## Architecture

### Bullet Struct (24 bytes)

```c
typedef struct {
    fp16    x, y;       // 16.16 fixed-point position
    fp16    dx, dy;     // velocity (cached from table on spawn/turn)
    uint16_t tile;
    uint8_t  palette;
    uint8_t  active;
    uint8_t  angle;     // 0-255
    uint8_t  spd_idx;   // speed tier index
    int8_t   curve;     // angular velocity per turn (0=straight)
    uint8_t  age;       // frames alive, max 255
} bullet_t;
```

### Key Optimizations

| Technique | What it does | Cycles saved |
|-----------|-------------|--------------|
| Free list | O(1) spawn/despawn via stack (was O(n) linear scan) | ~50,000/fire frame |
| SCB cache | Precompute SCB3/SCB4 in update, blast to VRAM in render | Eliminates 2nd pool iteration |
| Batch VRAM | Auto-increment sequential writes for SCB3 then SCB4 | No per-write VRAMADDR set |
| Velocity table | 3 speeds × 256 angles in ROM, dx/dy cached at spawn | No runtime trig/multiply |
| Curve index list | Only iterate curving bullets, not full pool | Zero cost when no curves |
| VBlank register save | A0-A3 saved in VBlank handler | Enables batch VRAM without atomic |
| Frame scheduler | Heavy tasks distributed across 16-frame cycle | No frame exceeds budget |

### Frame Scheduler (16-frame cycle)

```
Frame  0-3: Curve rotation (1/4 of curve_list per frame)
Frame  4:   Blue ring spawn (14 bullets, curving)
Frame  8:   HUD update (FIX layer)
Frame 10:   Pink fan spawn (12 bullets, aimed)
Frame 5-7, 9, 11-15: Light frames (move + collision only)
```

Spawning and curve never overlap. HUD updates avoid both. Every frame runs the base loop (move all bullets, bounds check, collision, fill SCB cache, VRAM blast).

### Velocity Table

Pre-computed in ROM: `blt_vel_table[3][256]` — 3 speed tiers × 256 angles. Each entry is `{dx, dy}` in 16.16 FP. 3KB ROM, zero runtime cost.

Speed tiers:
- SLOW: 0x0080 (~0.5 px/frame)
- MED: 0x0129 (~1.16 px/frame)
- FAST: 0x0200 (~2.0 px/frame)

On spawn, dx/dy are cached from the table. On curve turn, angle changes and dx/dy are re-cached. Between turns, just `x += dx; y += dy` — two adds.

### Curve System

Bullets with `curve != 0` are registered in `curve_list[]`. Each frame, 1/4 of the list is processed (frames 0-3 of the 16-frame cycle). Processing = increment angle, re-lookup dx/dy from velocity table. Straight bullets (`curve=0`) have zero curve overhead.

## VRAM Layout

| Sprite slots | Use |
|-------------|-----|
| 1 | Player ship |
| 2-5 | Player shots |
| 6-7 | Enemies |
| 8-9 | Explosions |
| 10 | Hitbox debug dot |
| 11-260 | Bullet pool (250 slots) |

### VRAM Write Path

1. `BLT_update()`: fills `scb3_cache[]` and `scb4_cache[]` arrays (RAM, no VDP)
2. `SYS_vblankFlush()`: writes sprite cmd_buf (enemies, player, etc.) atomically
3. `BLT_render()`: blasts scb3_cache then scb4_cache to VRAM via auto-increment

VBlank handler saves/restores A0-A3 so BIOS SYSTEM_IO can't clobber registers during batch writes.

## Performance

Measured with per-frame tracer on stock 12MHz 68K:

```
Budget:    202,752 cycles/frame
Work avg:  191,975 cycles (94%)
Work peak: 202,112 cycles (99%)
Headroom:  5% average, <1% worst case
VBlank misses: 0 over 7,200 frames (2 minutes)
Active bullets: avg 228, peak 250
Active curves:  avg 117, peak 138
VRAM writes:    avg 514, peak 552
```

## Bullet Types

### Blue Orb (cyan palette, 16×16)
- Fired as 14-bullet ring from sweeping enemy
- Each bullet curves at +2 angle per 4 frames
- Spiral pattern from spawner rotation (`ring_angle += 6` per fire)

### Pink Orb (magenta palette, 16×16 shrunk to 8×8)
- Fired as 12-bullet aimed fan from bouncing enemy
- Straight trajectory, aimed at player via `BLT_angleToward()`
- Hardware shrink via SCB2 = 0x077F

## Collision

Center-to-center comparison. Player hitbox = 2×2 pixels (danmaku style). Bullet center = logical position. Both render offset -8 so sprite center aligns with logical position.

## Bullet Lifecycle

1. **Spawn**: `BLT_spawn()` pops free list, caches dx/dy from velocity table, sets up SCB1/SCB2 via atomic VDP writes
2. **Update**: `BLT_update()` moves position, checks bounds/age/collision, fills SCB cache
3. **Curve**: on scheduled frames, angle increments and dx/dy re-cached from table
4. **Death**: bounds exit, age >= 250, or collision → slot pushed back to free list
5. **Render**: `BLT_render()` blasts cached SCB3/SCB4 to VRAM

## BIOS Integration

- Forced credits (0x10FD82 = 0x09) in `game_init`
- Timer refresh (0x10FDD4/D6/DA = 0xFF) in `game_tick`
- PLAYER_START handler in crt0.s decrements credits
- SYSTEM_IO called from main loop (not VBlank handler) to prevent hang
- Mode bit forced back on after SYSTEM_IO
- `game_active` flag guards VBlank handler during BIOS boot

## Files

| File | Role |
|------|------|
| `sdk/include/neo_bullet.h` | Bullet types, system struct, API |
| `sdk/src/neo_bullet.c` | Engine: spawn, update, render, patterns |
| `sdk/src/blt_vel_table.inc` | Precomputed velocity table (3KB) |
| `sdk/boot/crt0.s` | VBlank handler, wait counter, BIOS integration |
| `examples/danmaku/main.c` | Game logic, frame scheduler, debug RAM |
| `examples/danmaku/gen_assets.py` | Tile generation (ship, bullets, enemies) |

## Known Limits

- Pool ceiling: 250 slots for 0 VBlank misses on stock 12MHz
- Struct stride: 24 bytes — adding fields without removing others costs ~1% per extra byte
- Curve list: BULLET_CURVE_MAX = 370 (matches pool). More curves = more CPU on frames 0-3
- No background layer: all 381 sprite slots available, but backgrounds would eat into bullet budget
- AES+ overclock (14-24MHz) would raise the ceiling proportionally
