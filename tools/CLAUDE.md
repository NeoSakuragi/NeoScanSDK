# Tools

Python scripts organized by function. All target Python 3.

## Build pipeline (ROM creation)

| Script | Input | Output |
|--------|-------|--------|
| `neobuild.py` | manifest + assets | complete .neo ROM |
| `tile_encoder.py` | PNG images | C-ROM binary (4bpp planar, interleaved) |
| `palette_encoder.py` | PNG or palette def | palette binary (16-bit Neo Geo color) |
| `anim_encoder.py` | animation def | animation table binary |
| `font_encoder.py` | font PNG | S-ROM binary (8x8 fix tiles) |
| `player8_encoder.py` | 8-bit PCM | V-ROM ADPCM-A samples |
| `wav_encoder.py` | WAV files | V-ROM encoded audio |
| `softlist.py` | .neo ROM | MAME softlist XML entry |

## Audio authoring

| Script | Purpose |
|--------|---------|
| `neosynth_build.py` | Build NeoSynth Z80 sound driver M-ROM |
| `neosynth_driver.py` | NeoSynth driver source generator |
| `vgm_converter.py` | VGM → NeoSynth sequence data |
| `gen_drum_kit.py` | Generate ADPCM-A drum samples from WAVs |

## Extraction (asset ripping from existing ROMs)

| Script | Purpose |
|--------|---------|
| `cmc50_gfx_decrypt.py` | Decrypt CMC50-protected C-ROM (KOF99+) |
| `kof96_disasm_sections.py` | Disassemble KOF96 P-ROM sections |
| `kof98_prom_scramble.py` | Descramble KOF98 P-ROM |
| `extract_kof96_patches.py` | Extract FM patches from KOF96 Z80 |
| `kof95/` | KOF95 animation dictionary: all 26 fighters' animations, boxes, palettes, physics, special-move inputs (decoded recogniser), specials replays, throws for any victim (decoded ROM tables), MAME capture tooling. **Read `kof95/README.md`** |
| `kof96/` | KOF96 animation dictionary, same depth: 29 fighters, per-part palettes, decoded recogniser, throw lists (victim and thrower side, validated), captured specials; exports in the KOF95 layout for `kof95/gallery.py`. **Read `kof96/README.md`** (MAME needs `-noplugin cart_bridge`) |
| `kof98/` | KOF98 animation dictionary (38 fighters, every animation, supers/MAX/EX, win poses, throws), produced by the shared `kof96/` code with `--game kof98`. **Read `kof98/README.md`** |
| `kof99/` | KOF99 dictionary (34 fighters, every animation, specials/SDMs, throws, win poses), captured in our emulator (`emu/neogeo_sdl --capture`) via `kof96/capture/emu.py`. **Read `kof99/README.md`** |
| `port/` | Song porting between sound engines: `ff3_notes.py` (a MAKOTO v3 song as notes with their full chip state), `ff3_to_kof98.py CMD OUT` (writes it in KOF98's format as command $27 in bank set 6, samples into V ROM only unplayed KOF98 stage themes use, records into unused table entries), `compare_port.py` (both drivers' models, every key event's tick and chip state), `songlab_port.py` (Song Lab "Ports" data). First port: FF3 Terry's stage $2F, 3514/3516 key events identical, measured on the real KOF98 driver in the brawler. Data /data/neogeo_dict/sound/port |
| `songlab/` | Neo Geo Song Lab: one page (`song_lab.html`) for every decoded game (data/games.json + data/<game>/), synthesizing songs in the browser through ymfm's YM2610 compiled to WebAssembly (`ymweb.c` + `inc/`, built with zig: see ymweb.c) from the real driver's captured writes and from our model, A/B switching, mute/solo, click-to-play notes generated on their own; `build_web.py --game kof98\|ff3\|kof94\|kof95\|fatfursp\|aof\|aof2\|aof3\|kizuna\|ninjamas OUT_DIR` writes a game's data. Site with all data: /data/neogeo_dict/sound/songlab/all (published https://claude.ai/artifact/3hckfNGNxgRrm3VvNeqpdX) |
| `kof98snd/` | SNK's own "Sound Driver" line, one code path for every build (`games98.py` = each build's table addresses and the behaviours that changed, the build told from the M1 ID string): KOF98's v1.7 and Kizuna Encounter's Ver 0.0. `song98.py` decoder + tick-exact model, `regs98.py` its YM2610 writes + comparison with a capture, `validate98.py` per-channel check, `ymtap.lua` MAME captures (KOF98), `capture98.py --game kizuna [--songs DIR]` captures in our emulator (makoto3's tap). Kizuna: all 23 songs register-identical. Docs: `docs/kof98_sound_driver.md`, `docs/kof98_songs.md`, `docs/kizuna_sound_driver.md`, `docs/kizuna_songs.md`. Data /data/neogeo_dict/sound/kizuna |
| `makoto3/` | The "Ver 3.0 by MAKOTO" sound driver of Fatal Fury 3, KOF94, KOF95, Fatal Fury Special and Art of Fighting 1-3 (one code path, `games.py` = each build's table addresses and switches, the game told from the M1 ROM; Fatal Fury Special and AOF2 = KOF94's code with other tables; AOF1 = KOF94's music engine with an older command path; AOF3 = KOF95's build + per-channel ADPCM-A sample tables set by opcode `$3C`, 6-byte sample records, no per-octave ADPCM-B mode): `song.py` song decoder + interrupt-exact player model, `regs.py` its YM2610 writes + comparison with a capture, `capture.py [--game ff3\|kof94\|kof95\|fatfursp\|aof\|aof2\|aof3]` the Geolith core with a Z80 port tap driven from Python (every YM write, command, interrupt; `--songs` captures every song). Fatal Fury Special: all 28 songs register-identical; AOF 38, AOF2 42, AOF3 30 songs register-identical. Docs: `docs/ff3_sound_driver.md` (incl. the KOF94, KOF95 and Fatal Fury Special builds), `docs/ff3_songs.md`, `docs/kof94_songs.md`, `docs/kof95_songs.md`, `docs/fatfursp_songs.md`, `docs/aof_songs.md`, `docs/aof2_songs.md`, `docs/aof3_songs.md`. Data /data/neogeo_dict/sound/aof, aof2, aof3. Song Lab data: `songlab/build_web.py --game ff3\|kof94\|kof95\|fatfursp\|aof\|aof2\|aof3` |
| `adksnd/` | ADK's "Operation System Program for Music & Effective Sound Ver. 8.8.9" (Ninja Master's): songs are MML text read by the driver as it plays; music in the main loop, one tick per two timer-A interrupts (timer A = tempo in BPM). `gamesadk.py` (build tables, told from the M1 ID string), `songadk.py` decoder + tick-exact model (each channel's 64-byte driver block kept at the driver's offsets), `regsadk.py` comparison with a capture (walks it with the driver's own clock), `captureadk.py [--songs DIR]` captures in our emulator (makoto3's tap; `$FC` + the command). All 36 songs register-identical. Docs: `docs/ninjamas_sound_driver.md`, `docs/ninjamas_songs.md`. Data /data/neogeo_dict/sound/ninjamas |
| `brawler/` | `export_bm.py`: beat 'em up subset of any KOF96/98/99 fighter (37 moves incl. the KOF97+ command normals, boxes with beat 'em up reach, every colour set) as C tables + C1/C2 tiles for `examples/brawler`; `check_specials.py`: every fighter's picked specials as the brawler plays them (hits, the game's hits, contact freezes removed, impacts and reactions, continuations); `run_test.py`: play an input script on the brawler ROM in our emulator, contact sheet out; `harness.py`: the Geolith core driven from Python frame by frame (RAM read/write, fighter_t decoded via offsetof, place/force fighters, hit log, save states, screenshots); `portraits.py`: KOF96/98/99 HUD portraits (VRAM of a fight via our emulator's VRAMDUMP or MAME `vram_dump.lua`; KOF96 from its ROM tables), PNG + JSON in /data/neogeo_dict/portraits |

## Debug & analysis

| Script | Purpose |
|--------|---------|
| `z80_trace.py` | Trace Z80 execution from SHM bus |
| `z80disasm.py` | Z80 disassembler |
| `neores.py` | ROM resource inspector |

## .neo ROM format

4096-byte header followed by ROM data concatenated in order: P, S, M, V1, V2, C.

```
Offset  Size  Field
0x00    4     Magic
0x04    4     P-ROM size (LE)
0x08    4     S-ROM size (LE)
0x0C    4     M-ROM size (LE)
0x10    4     V1-ROM size (LE)
0x14    4     V2-ROM size (LE)
0x18    4     C-ROM size (LE)
```

C-ROM in .neo is ALREADY interleaved — read tiles directly, no deinterleave step.
