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
