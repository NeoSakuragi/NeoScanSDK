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

## Runtime facts (2026-10-03)

- **VRAM queue** (`src/neo_internal.h`): runs `{addr, count, words}`; `cmd_run(addr, n)` reserves n consecutive VRAM words
  and returns where to store them, `cmd_push(addr, data)` is a 1-word run. `SYS_vblankFlush` writes them with
  VRAMMOD = 1 (22 cycles a word) and leaves VRAMMOD at 0. A full queue (4096 words) is flushed early, never dropped.
  Flush at the START of the tick (crt0 calls game_tick right after vblank), not at the end: a flush after the game
  logic lands in active display and tears.
- **`.data` is copied to work RAM** by crt0 (`copy_data`). Before this, initialised non-const globals lived in ROM and
  silently ignored writes.
- **P2 joystick** is `$10FD9C` (BIOS P2CURRENT); the SDK read `$10FD98` (P1's repeat byte) until 2026-10-03.
- **.neo header NGH** (offset 0x28) is written as 0x0B00 by `tools/neobuild.py`: NGH 999/0x3E7 is V-Liner in Geolith's
  database, which disconnects joystick 2.
- No libgcc: a 32-bit multiply/divide in C fails at link time (`__mulsi3`); use 16-bit operands, shifts or pointer steps.
- `make` tracks header dependencies (`-MMD`).
- **Program ROM past 1 MB**: sections named `.p2data` link at $200000 (bank 0 of the P2 window, mapped at reset, no
  switching); rename an object's `.rodata` with `objcopy --rename-section .rodata=.p2data` (examples/brawler/Makefile).
  `tools/neobuild.py` lays the P ROM out as the first MB then the $200000 data, sizes it to fit (1 or 2 MB) and refuses
  more (past $2FFFFF needs P2 bank switching). C ROM is sized to fit too; nothing is truncated silently any more.
- **MVS attract / title / game** (crt0.s, measured with Unibios 4.0 in our emulator): USER request 0 = init (game_init),
  2 = demo and 3 = title both enter the frame loop through `game_enter(request)` (weak default: game_init, the old
  behaviour). DEMO_END (coin during the demo) must not return to the BIOS's SYSTEM_IO (that hangs the game): crt0's
  handler goes straight to SYSTEM_RETURN, the BIOS then calls request 3. PLAYER_START (START with a credit): crt0 runs
  BIOS_CREDIT_DEC $10FDB0 + CREDIT_CHECK $C00450, sets USER_MODE 2 and ORs the players into `bios_start`; the credit
  is already taken (Unibios 4.0: an extra CREDIT_DOWN $C00456 took two; recheck on an SNK MVS BIOS). Credits shown
  from backup RAM $D00034 (BCD); soft DIP values at BIOS RAM $10FD84 (+6 = first list setting); `soft_dip` is weak. `SYS_return()` ends a demo / a game. The BIOS's screens overwrite palette 0: reload it in
  game_enter. An endless demo is cut by the BIOS after ~50 s (sound reset): end the demo yourself (SYS_return).
- **USER request 0 is not every boot**: the BIOS sends it only while the game's backup RAM is uninitialised. crt0's
  `boot_init` (zero .bss, copy .data, game_init) therefore also runs from the demo / title entry when the `.noinit`
  magic says it hasn't run since power-on. Without that, initialised globals read 0 from the second boot on.

