# NeoScan SDK

C development kit for Neo Geo homebrew. Targets the 68000 with VASM assembler and outputs .neo ROM files.

## Modules

| Header | Purpose |
|--------|---------|
| `neo_sprite.h` | Sprite management, chains, animation |
| `neo_fix.h` | Fix layer (text/HUD) |
| `neo_palette.h` | Palette loading and management |
| `neo_input.h` | Joystick input polling |
| `neo_anim.h` | Sprite animation engine |
| `neo_hw.h` | Hardware registers, VBlank, IRQ |
| `neo_backup.h` | Save data, SNK conventions: MVS backup RAM block (`NEO_BACKUP`), AES memory card (BIOS CARD call) |

## Build

```
make            # Build SDK library
```

## Examples

See `../examples/` for complete projects using the SDK.
