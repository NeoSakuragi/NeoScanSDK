# NeoScan Emu

Standalone SDL2 frontend for the Geolith Neo Geo libretro core. No RetroArch.

## Build

```
cc -O2 -o neogeo_sdl neogeo_sdl.c $(pkg-config --cflags --libs sdl2) -ldl -lm -lGL
```

## Usage

```
./neogeo_sdl game.neo [--snap F1,F2,... --quit F --script file]
```

## Controls

| Key | Action |
|-----|--------|
| WASD | Directions (P1) |
| U/I/O/P | A/B/C/D |
| 1/2/3 | P1 Start / P2 Start / Coin |
| F1 | Menu (reset, BIOS mode, region) |
| F2 | Toggle CRT shader |
| F3 | Sprite debug panel |
| F5 | Screenshot |
| F6 + A-Z/0-9 | Save state |
| F7 + A-Z/0-9 | Load state |
| ESC | Quit |

## Gamepad

Xbox/PS layout. D-pad + left stick for directions. Face buttons for A/B/C/D.

| Trigger | Combo |
|---------|-------|
| LB | A+B |
| LT | B+C |
| RT | C+D |
| RB | A+B+C |

## Features

- CRT aperture grille shader (diagonal RGB, phosphor bleed, scanlines)
- 36 save state slots per game (A-Z, 0-9)
- Auto-loads state 's' on boot
- F1 menu: BIOS mode (MVS/AES), region (US/JP/EU/AS), cold reset via NVRAM
- F3 sprite debugger: chains grouped by P-ROM writer address, toggle layers
- Script engine for automated testing
- SHM bus auto-detection (activates when server is running)
