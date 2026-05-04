# NeoScan SDK

C development kit for Neo Geo homebrew. Targets the 68000 with VASM assembler and outputs .neo ROM files.

## Modules

| Header | Purpose |
|--------|---------|
| `neo_sprite.h` | Sprite management, chains, animation |
| `neo_fix.h` | Fix layer (text/HUD) |
| `neo_palette.h` | Palette loading and management |
| `neo_input.h` | Joystick input polling |
| `neo_sound.h` | Z80 sound driver commands |
| `neo_anim.h` | Sprite animation engine |
| `neo_hw.h` | Hardware registers, VBlank, IRQ |

## Build

```
make            # Build SDK library
```

## Examples

See `../examples/` for complete projects using the SDK.
