# Notes from Eagle Software's NeoGeoSDK (v1.7.0, read 2026-09-30)

Source: github.com/eaglesoftware777/neogeosdk (MIT). Sparse clone of docs, sdk/ and the
sound driver at `/data/ref/eagle_neogeosdk/repo` (no games/ or tools/). The most useful
part is their CHANGELOG: every "correction" there is a mistake made in practice.
The tags say how far each claim was checked: **[MAME]** checked against `mame/src/mame/neogeo`,
**[EMU]** seen in our emulator, **[THEIRS]** only stated by Eagle, and **⚠** means doubtful.

## Applied to our SDK

| Fact | Status |
|---|---|
| Backdrop colour = last palette word `$401FFE` (palette 255 colour 15). `$402000` is a mirror. | **[MAME][EMU]** `PAL_setBackdrop` wrote `$400000` and did nothing; fixed 2026-09-30 |
| FIX map rows 0-1 and 30-31 are in vertical blanking (display is lines 16-239); visible row y = map row y+2 | **[MAME][EMU]** `FIX_*` rows are now visible rows 0..27; every example's row-1 title was invisible before |
| Higher sprite slot is drawn in front | **[MAME]** `docs/NGEMU_SPEC.md` said the opposite; fixed |

## Video
- Palette bank select: `$3A000F` = bank 0, `$3A001F` = bank 1 **[MAME]** (HC259 `write_a3`, Q7). The dev wiki names them the other way round; unused by us.
- `$3A000B` = BIOS SFIX, `$3A001B` = cart S ROM **[MAME]** (Eagle's changelog gets this backwards).
- Palette 0 colour 0 is the reference colour and should be `$8000`. Colour word: bit15 dark, bits 14/13/12 = R/G/B LSB, 11-0 = RGB high nibbles.
- SCB3 = `(496-y)<<7 | sticky<<6 | height`, and y aliases mod 512. Height 0 hides the sprite.
- SCB3 height is the ON-SCREEN height in 16-px rows whatever the Y shrink. Rows needed = `ceil(src_rows*(yshrink+1)/256)`. Changing shrink therefore means rewriting SCB3 too. Only map rows 0-15 are read unless the sprite is taller than 256 lines. **[THEIRS]**
- SCB2: bits 11-8 = X shrink (`(v+1)/16`), bits 7-0 = Y shrink (`(v+1)/256`). Hardware shrink drops rows and columns, with no filtering.
- Chained (sticky) strips read no position, so moving a chain means rewriting only the driving strip.
- Sprite teardown: clear SCB3 (height 0, not sticky), SCB2 `0x0FFF`, X off-screen. Partial clears leave ghosts across scenes.
- Doing VRAM writes before waiting for VBlank, or re-uploading whole tilemaps every frame, overran VBlank and corrupted sprite writes. Queue the writes and flush only what changed.
- Stale software VBlank flag: clear it before waiting, or a long frame inherits last frame's flag.
- VBlank is 40 of 264 lines, about 2.5 ms (Eagle's docs contradict themselves: 1.1 ms / 3 ms).
- The FIX map word has only 4 palette bits, so the FIX layer uses palettes 0-15. BIOS SFIX tile `$FF` is blank. `$20` (space) is opaque.

## Sound (YM2610 / Z80)
- Z80 ports: `in $00` = command; `out $0C` = reply to the 68000; `out $00` = clear latch; `out $08`/`$18` = NMI enable/disable; `in $08-$0B` = bank switch (upper address byte = bank). **[MAME]**
- **Handshake lesson:** Eagle's driver drives the reply to 0 in the NMI and to 1 once the byte is queued. Waiting only for "1" trusted the previous acknowledgement, and 19 of 25 demo chapters went silent. Correct 68000 side: write, wait for the reply to change, then wait for "ready". Our driver echoes the command on `$0C` and keeps ONE slot at `$F803`, which the Timer A IRQ reads. Two `SND_play` calls before the next IRQ lose the first command. Not fixed.
- Timer B period = 144×16×(256−N)/8 MHz (`$E4` gives 124 Hz). In `$27`, bit 1 = load B: writing `$27` with it clear stops Timer B and freezes the music tick. Resting value `$3A`.
- LFO `$22` is chip-global: per-patch writes clobber it. PMS/AMS must be non-zero to hear modulation.
- ADPCM-B: write `$11=$C0` (L/R) on EVERY start, since it is indeterminate after some resets ("mute despite playback"). Delta-N = `round(rate×65536×144/8e6)`: 16 kHz `$49BA`, 32 kHz `$9375`, max about 55.5 kHz. Start and end are in 256-byte units.
- ADPCM-A: start `$10+ch`/`$18+ch`, end `$20+ch`/`$28+ch`, 256-byte units, end inclusive = `(start+size-1)>>8`. A sample must not cross a 1 MiB boundary. Reset end flags with `$1C=mask`, then `$1C=0`. Fixed 18.5 kHz.
- ADPCM-A encoder must match the chip: single rounding of the delta, 12-bit WRAP (not clamp), no synthetic pre-roll (it clicks). Reference decoder: `delta=(2*(c&7)+1)*step//8; acc=(acc±delta)&4095`, step index clamped 0..48.
- SSG: 8 MHz /64, so `f = 125000/TP`. Saturate the period, don't wrap.
- FM: only OPN channels 1, 2, 5 and 6 exist. Write `$A4+` before `$A0+`. Operator offsets +0/+4/+8/+C = op1/op3/op2/op4.
- wla-z80 silently overlaps sections that have fixed `.org` addresses (exit 0, `MEM_INSERT` warning). Treat the warning as fatal.

## System / BIOS
- Watchdog timeout ≈ 3244030 ticks at 24 MHz ≈ 135 ms ≈ 8 frames **[MAME]**. Kick it in VBlank.
- P-ROM bank switching: window `$200000-$2FFFFF`, a write to `$2FFFF0-$2FFFFF` selects `(data&7)+1` MB **[MAME]**. Eagle's linker example is off by one bank. Never switch banks inside an IRQ without saving the bank.
- BIOS RAM: P1 block `$10FD94-99` (STATUS, PREVIOUS, CURRENT, CHANGE, REPEAT, TIMER), P2 `$10FD9A-9F`. START_FLAG `$10FDB4`. Calendar `$10FDD2-D8` (BCD, MVS). Upload call `$10FEF4/F8/FC` + ZONE `$10FEDA`. Credits in backup RAM at `$D00034/35` (BCD).
- BIOS calls: CREDIT_CHECK `$C00450`, CREDIT_DOWN `$C00456`, READ_CALENDAR `$C0045C`, CARD `$C00468`, HOW_TO_PLAY `$C00474`, MESS_OUT `$C004CE`.
- Header `$114` eyecatcher: 0 = BIOS draws it, 1 = game draws it, 2 = none. Soft-DIP option byte: high nibble = default, low nibble = number of choices.
- The MVS BIOS self-test shows a garbled green screen for about 3.5 s. Only a green screen that PERSISTS means a broken ROM.
- An AES attract loop that never returns to the BIOS never gets START.

## Worth borrowing (upstream only, not in the sparse clone)
- `artbox/palette_banks.py`: CIE-Lab palette fitting on the 5-bit lattice, with budgeted per-tile banks seeded from the worst tile.
- `artbox/img2neo.py`: resize in linear light with premultiplied alpha (sRGB averaging lost 8-22% luminance), and alpha bleed before the resize.
- `artbox/img2neo_tile.py`: blue-noise dither between the two nearest palette entries.
- `sound/tools/adpcm_enc.py` (chip-exact ADPCM-A/B), `wav_to_raw_pcm.py` (band-limited polyphase resampler), `vrom.py` (1 MiB page checks).
- Test pattern: a host-side stand-in VRAM array asserting SCB words (`tests/sprite_render_test.c`). MAME Lua `install_write_tap` captures of VRAM, palette and the sound latch (keep the tap handle global or it gets garbage-collected). Audio regressions only show up with a live 68000, not a scripted Z80 feed.

## Their cartridge note
Generic and not buildable: it treats C/S/M/V as plain ROMs on the console address bus and
ignores the PCK1B/PCK2B-latched multiplexed buses. Nothing for NeoCart.
