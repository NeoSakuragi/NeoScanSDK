# Examples

Complete reference games built with the NeoScan SDK.

## Build

```bash
make -C examples/hello_neo    # or any example directory
```

After `make`, always:
1. Re-copy donor ROMs if the example uses them
2. Regenerate softlist entry if ADPCM-B changed (`python3 tools/softlist.py`)

## Projects

| Example | Focus | Key features |
|---------|-------|-------------|
| `hello_neo/` | Sprites + input | Basic sprite display, joystick, palette |
| `jukebox/` | FM synthesis | NeoSynth driver, sequencer, FM patches |
| `sound_lab/` | Audio test bench | Drum kits, ADPCM-A samples, SSG |
| `ikari_soccer/` | Sprite chains | Multi-sprite objects, animation |
| `soccerfury_player/` | Animated title | Unity 3D→2D pipeline output |

## Run

```bash
../emu/neogeo_sdl hello_neo/hello_neo.neo
```
