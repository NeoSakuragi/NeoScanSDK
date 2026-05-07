# SDK — NeoScan C Dev Kit

C library for Neo Geo 68000 homebrew. VASM assembler, outputs .neo ROM files.

## Build

```bash
make          # builds sdk/lib/libneoscan.a
```

## Modules

| Header | Purpose |
|--------|---------|
| `neo_sprite.h` | Sprite loading, positioning, chain management |
| `neo_anim.h` | Frame-based sprite animation engine |
| `neo_palette.h` | Palette loading, fade, cycling |
| `neo_fix.h` | Fix layer text/HUD (8x8 S-ROM tiles) |
| `neo_input.h` | Joystick polling, edge detection |
| `neo_hw.h` | Hardware registers, VBlank wait, IRQ setup |
| `neo_sound.h` | Sound driver communication (Z80 cmd interface) |
| `neo_types.h` | Base types, fixed-point, common structs |

## Conventions

- All public functions prefixed `neo_` (e.g., `neo_sprite_set_pos`)
- Hardware register writes go through `neo_hw.h` macros, not raw addresses
- VBlank sync via `neo_hw_wait_vblank()` — never busy-loop on register
- Sound commands via `neo_sound_cmd(uint8_t cmd)` — writes to REG_SOUND (0x320000)
