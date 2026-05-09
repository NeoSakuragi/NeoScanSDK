# Neo Geo AES+ (Plaion, Holiday 2026)

## Overview

Re-engineered Neo Geo console by Plaion/SNK. $250 base, anniversary and ultimate editions available. Ships November 2026.

## Hardware

- **Custom ASICs** — not emulation, not FPGA. Original chip architecture (68000 + Z80 + LSPC) re-engineered into new silicon
- **Developers**: Jotego and Furrtek (both known for FPGA Neo Geo cores on MiSTer) provided support for ASIC development
- **Controversy**: FPGA developer Pramod Somashekar alleges it could be the MiSTer Neo Geo core split into separate ASICs ("bait and switch"). ASICs are hard-wired and cannot be updated post-launch, unlike FPGAs

## Outputs

- Low-latency HDMI up to 1080p
- Original AV output for CRT

## Features

- Physical DIP switches on console for:
  - Language selection
  - **Overclock mode**
  - Display modes
- Permanent high score storage
- Compatible with original AES cartridges

## Overclock Mode

- Controlled via DIP switch — no details published on exact clock speed
- Original 68HC000 limits: stock 12MHz, safe overclock to ~14MHz (17%), glitches above ~13.5MHz on original silicon
- If ASIC-based (not bound by 68HC000 electrical limits), overclock could be more aggressive
- Pin 15 on original 68000 is the clock input — the ASIC likely has a configurable clock divider

## Impact on Danmaku Engine

| Clock | 68K cycles/frame | Bullet frame rate (360 bullets) | Headroom |
|-------|------------------|---------------------------------|----------|
| 12MHz (stock) | 202,752 | 91% | ~8% |
| 14MHz (+17%) | 237,216 | ~107% (full 60fps) | ~7% |
| 16MHz (+33%) | 270,336 | ~120% (full 60fps) | ~20% |
| 24MHz (2x) | 405,504 | ~180% (full 60fps) | ~45% |

Even the conservative 14MHz overclock would give our 360-bullet engine full 60fps with room for boss AI, scrolling, and more patterns.

## Sources

- https://plaionreplai.com/products/neogeo-aes
- https://www.timeextension.com/news/2026/04/no-emulation-no-compromise-no-comparison-the-usd250-neo-geoplus-aes-aims-to-be-a-11-replica-of-snks-classic-console
- https://www.timeextension.com/news/2026/05/plaion-answers-ten-of-your-burning-questions-about-the-neo-geo-aesplus
- https://www.notebookcheck.net/FPGA-developer-claims-Plaion-s-NeoGeo-AES-is-effectively-a-bait-and-switch.1279381.0.html
- https://wiki.neogeodev.org/index.php?title=Overclocking
- https://www.neo-geo.com/forums/index.php?threads/68ks-guide-to-overclocking-your-neo-geo-aes.146862/
