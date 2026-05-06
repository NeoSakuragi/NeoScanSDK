# NeoSynth Sound Engine

Custom Z80 sound driver for the Neo Geo YM2610 (OPNB) chip. Built from scratch in Python-assembled Z80 machine code.

## Hardware

### YM2610 (OPNB)
- **FM synthesis**: 4 channels (YM2610 channels 1, 2, 4, 5 — channels 0 and 3 are not available for FM)
- **SSG (AY-3-8910)**: 3 square wave channels + 1 noise channel, shared mixer
- **ADPCM-A**: 6 channels, 18.5 kHz fixed rate, 256-byte aligned samples in V-ROM
- **ADPCM-B**: 1 channel, variable rate (2-55.5 kHz), streaming from V-ROM

### Z80
- 4 MHz clock
- 64 KB address space: M-ROM mapped at $0000-$FFFF
- Bank switching via ports $08-$0B (4 switchable banks for M-ROM > 32KB)
- Communication with 68K via NMI (triggered by 68K write to REG_SOUND $320000)
- Timer A IRQ used for sequencer tick (~165 Hz)

### Memory Map (Z80)
```
$0000-$7FFF   Static main code bank (32 KB)
$8000-$BFFF   Switchable Bank 0 (16 KB, port $0B)
$C000-$DFFF   Switchable Bank 1 (8 KB, port $0A)
$E000-$EFFF   Switchable Bank 2 (4 KB, port $09)
$F000-$F7FF   Switchable Bank 3 (2 KB, port $08)
$F800-$FFFF   Work RAM (2 KB)
```

### M-ROM Layout
```
$0000-$009F   Z80 code: vectors, NMI handler stub
$00A0-$0FFF   Driver code (NMI dispatch, FM/SSG/ADPCM handlers)
$1000+        Song data, patch tables, frequency tables, sample table
```

## Command Protocol

The 68K sends commands by writing to `REG_SOUND` ($320000). The Z80 receives via NMI and reads the command from port $00.

For commands requiring a parameter, use `SND_play2(param_cmd, action_cmd)`:
1. Send `$08` (SET_PARAM)
2. Send the parameter value (stored in RAM_PARAM)
3. Send the action command (reads RAM_PARAM)

### Commands

| Range | Command | Description |
|-------|---------|-------------|
| `$01` | Init/Reset | Silence all, reset driver state |
| `$03` | Stop All | Stop sequencer, key-off all FM/SSG, dump ADPCM |
| `$08` | Set Param | Next NMI byte stored as parameter |
| `$10+ch` | FM Key-On | ch=0-3, note from param (MIDI note number) |
| `$14+ch` | FM Key-Off | ch=0-3 |
| `$18+ch` | FM Set Patch | ch=0-3, patch index from param |
| `$20+ch` | SSG Key-On | ch=0-2, note from param (MIDI note) |
| `$24+ch` | SSG Key-Off | ch=0-2 |
| `$28+ch` | SSG Set Preset | ch=0-2, preset index from param (0-4) |
| `$30+ch` | FM Panning | ch=0-3, param: 0=L, 1=C, 2=R |
| `$34+ch` | ADPCM-A Panning | ch=0-5, param: 0=L, 1=C, 2=R |
| `$50+N` | Play Song N | Start sequencer song (0-15) |
| `$C0` | ADPCM-A (param) | Trigger sample, index from param (bank 0) |
| `$C1` | ADPCM-A Bank 1 | Trigger sample, index from param (bank 1, +256) |
| `$C4+` | ADPCM-A Inline | Trigger sample index = cmd - $C0 (for indices 4+) |

## FM Synthesis

### Patches (20 available)

| Index | Name | Origin |
|-------|------|--------|
| 0 | Simple Sine | Custom |
| 1 | Organ | Custom |
| 2 | Brass | Custom |
| 3 | Piano | Custom |
| 4 | KOF Lead | Extracted from KOF96 |
| 5 | KOF Strings | KOF96 |
| 6 | KOF FM Perc | KOF96 |
| 7 | KOF Pad Soft | KOF96 |
| 8 | KOF Lead Hard | KOF96 |
| 9 | KOF Orch Strings | KOF96 |
| 10 | KOF Sine Add | KOF96 |
| 11 | KOF Power Lead | KOF96 |
| 12 | KOF Bass Heavy | KOF96 |
| 13 | KOF Dist Pluck | KOF96 |
| 14 | KOF Nasal Lead | KOF96 |
| 15 | KOF Dist Heavy | KOF96 |
| 16 | KOF Pad Rich | KOF96 |
| 17 | KOF Guitar | KOF96 |
| 18 | KOF Bell | KOF96 |
| 19 | KOF Keys | KOF96 |

Each patch is 26 bytes: 24 operator registers (DT/MUL, TL, KS/AR, DR, SR, SL/RR for 4 operators) + FB/ALG + LR/AMS/PMS.

### Note-On Behavior
On note-on, the driver:
1. Key-off the channel (restart envelope)
2. Write all 24 operator registers from the patch
3. Write FB/ALG and LR/AMS/PMS
4. Set frequency (F-number + block from MIDI note lookup table)
5. Key-on the channel

This ensures the envelope always restarts from the attack phase on consecutive notes.

### Frequency Table
12-entry F-number table for equal temperament tuning. MIDI note → octave (block) + semitone (F-number). Range: MIDI 0-127 (C-1 to G9).

## SSG (Square Wave)

### Presets (5 available)

| Index | Name | Vol | Decay | Noise |
|-------|------|-----|-------|-------|
| 0 | Square | 15 | 0 | No |
| 1 | Pluck | 15 | 10 | No |
| 2 | Bell | 15 | 3 | No |
| 3 | Noise HH | 12 | 14 | Yes |
| 4 | Buzz | 5 | 0 | No |

Each preset: 3 bytes (initial_vol, decay_rate, noise_enable).

Software envelope: Timer A IRQ decrements volume at the decay rate. When volume reaches 0, the channel is silenced.

## ADPCM-A Samples

### CrocellKit Drum Library (27 instruments)

| Index | Name | Sample |
|-------|------|--------|
| 0 | Kick L | k_drum_l.wav |
| 1 | Kick R | k_drum_r.wav |
| 2 | Snare | snare.wav |
| 3 | Snare Rim | snare_rim.wav |
| 4 | Rimshot | snare_rim_shot.wav |
| 5 | Snare Rest | snare_rest.wav |
| 6 | HH Closed | hihat_closed.wav |
| 7 | HH Closed NP | hihat_closed_no_pedal.wav |
| 8 | HH Open | hihat_open.wav |
| 9 | HH Semi | hihat_semi_open.wav |
| 10 | HH Pedal | hihat_pedal.wav |
| 11 | HH Pedal Hit | hihat_pedal_hit.wav |
| 12 | Tom 1 | tom1.wav |
| 13 | Tom 2 | tom2.wav |
| 14 | Floor Tom 1 | f_tom1.wav |
| 15 | Floor Tom 2 | f_tom2.wav |
| 16 | Crash L | crash_l.wav |
| 17 | Crash R | crash_r.wav |
| 18 | Crash L Stop | crash_l_stopped.wav |
| 19 | Crash R Stop | crash_r_stopped.wav |
| 20 | Crash Xtra | crash_r_xtra.wav |
| 21 | China L | china_l.wav |
| 22 | China R | china_r.wav |
| 23 | Splash L | splash_l.wav |
| 24 | Splash R | splash_r.wav |
| 25 | Ride | ride_r.wav |
| 26 | Ride Bell | ride_r_bell.wav |

All samples: mono, 16-bit, 18500 Hz, highest velocity from CrocellKit professional drum recordings (close-mic per instrument).

**Note**: In the sequencer ADPCM column, index 0 = no trigger. Sample indices are 0-based for direct commands ($C0+param) but effectively 1-based in the sequencer (0 means silence). Kick L (index 0) cannot be triggered from the sequencer; use Kick R (index 1) instead.

## Music Sequencer

### Format
- 8 bytes per row: `[FM0] [FM1] [FM2] [FM3] [SSG0] [SSG1] [SSG2] [ADPCM_A]`
- Tick-based: Timer A IRQ (~165 Hz) divided by tempo value = rows per second

### Row Byte Values

| Value | Meaning |
|-------|---------|
| `$00` | Sustain (no change) |
| `$01` | Key-off |
| `$02-$7F` | Note-on (MIDI note number) |
| `$80-$BF` | Set patch (patch index = value & $3F), FM/SSG only |
| `$FF` | End of song (loops to start) |

### Tempo
The tempo byte controls how many Timer A IRQs pass between row advances.

| Tempo | Rows/sec | At 4 rows/beat | BPM |
|-------|----------|----------------|-----|
| 10 | 16.5 | 4.1 | 248 |
| 18 | 9.2 | 2.3 | 138 |
| 20 | 8.3 | 2.1 | 125 |
| 43 | 3.8 | 1.0 | 58 |
| 172 | 0.96 | 0.24 | 14 |

Formula: `BPM = (165 / tempo) * (60 / rows_per_beat)`

### Song Table
Songs are stored in M-ROM with a header table:
```
[start_lo] [start_hi] [length_lo] [length_hi] [tempo]
```
Up to 16 songs. Song 0 is triggered by command `$50`, song 1 by `$51`, etc.

## Build Pipeline

### Tools
- `neosynth_build.py` — Assembles the Z80 driver, embeds patches, frequency tables, sample tables, and song data into M-ROM
- `wav_encoder.py` — Converts WAV files to ADPCM-A format for V-ROM
- `neores.py` — Resource pipeline, handles SFX entries in `.res` files
- `neobuild.py` — Packages M-ROM and V-ROM into .neo file (supports `--donor-m1` / `--donor-v1` for pre-built ROMs)

### Building
```bash
cd examples/sound_lab
make clean && make
```

The Makefile:
1. Runs `neores.py` to encode WAV samples → ADPCM-A V-ROM
2. Runs `neosynth_build.py` to assemble Z80 driver → M-ROM (with embedded song data)
3. Runs `neobuild.py` to package everything into .neo

### Adding Songs
Edit `build_test_songs()` in `neosynth_build.py`. Each song is a list of 8-byte rows returned as `(song_bytes, tempo)`.

### MIDI Conversion
Convert a MIDI file to sequencer grids:
1. Parse MIDI into per-channel note events
2. Quantize to 16th-note grid (0.25 beats)
3. Generate grids with note-on values, sustain ($00), and key-off ($01)
4. Map GM percussion to CrocellKit indices
5. Save as JSON, loaded by `build_guile_with_drums()` in `neosynth_build.py`

## SDK API

```c
#include "neo_sound.h"

// In neo_hw.h:
#define REG_SOUND (*(volatile uint8_t *)0x320000)

// Thin wrappers:
SND_init();              // Send $07 (unlock)
SND_play(cmd);           // Send single command
SND_play2(cmd1, cmd2);   // Send cmd1 now, cmd2 next frame
SND_update();            // Call each frame to flush pending cmd2
SND_stop();              // Send $03 (stop all)
```

## Known Limitations

- ADPCM-A sample index 0 unreachable from sequencer (reserved as "no trigger")
- Maximum 16 songs in M-ROM
- Song data shares M-ROM space with driver code (~60 KB available for songs)
- No ADPCM-B support in sequencer (only manual trigger via commands)
- SSG software envelope runs at Timer A rate (~165 Hz), may not be smooth enough for fast decays
- FM patch writes are full (24 registers) on every note-on — audible click possible if patch doesn't change
