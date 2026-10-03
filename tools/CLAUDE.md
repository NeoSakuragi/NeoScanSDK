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
| `brawler/` | `export_bm.py`: beat 'em up subset of any KOF96/98/99 fighter (32 moves, boxes with beat 'em up reach, every colour set) as C tables + C1/C2 tiles for `examples/brawler`; `run_test.py`: play an input script on the brawler ROM in our emulator, contact sheet out; `harness.py`: the Geolith core driven from Python frame by frame (RAM read/write, fighter_t decoded via offsetof, place/force fighters, hit log, save states, screenshots); `portraits.py`: KOF96/98/99 HUD portraits (VRAM of a fight via our emulator's VRAMDUMP or MAME `vram_dump.lua`; KOF96 from its ROM tables), PNG + JSON in /data/neogeo_dict/portraits |

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
