# Double Dragon songs (SDC_NGSS driver)

The music of Double Dragon (Technos 1995): 20 music commands `$DC-$EF` (19 songs: `$EF` plays `$EE`'s data, which
`$00-$03` also point at). Driver: `doubledr_sound_driver.md`. Tools: `tools/ngss` (decoder + model, captures,
comparison), Song Lab: https://canneji.duckdns.org/neogeo-songlab/#doubledr-E1 (real driver vs model, A/B).

    python3 tools/ngss/song_ngss.py /data/neogeo_dict/sound/doubledr/doubledr_m1.bin 0xE1          summary
    python3 tools/ngss/song_ngss.py /data/neogeo_dict/sound/doubledr/doubledr_m1.bin 0xE1 --list   event listing

## Names

How each name was established:
- **measured in our emulator**: `$E2` opening movie and `$ED` title (attract mode, every 4227 frames: `$E2`, then
  `$ED` with the logo); `$E8` how to play (after START); `$E6` player select; `$DF` the fight of a 2P game whose P2
  picked Dulton (the stage is P2's: `$117C6`); `$E7` the winner's scene after a lost match ("GAAHAAHAA !! I'M THE
  STRONGEST IN THE WORLD"); `$E5` the continue countdown (then `$E2` again: no game-over song).
- **the 68000's tables**: the fight's song = `$129BE`[stage] (`$129AE`, sent before each fight), stage =
  `$11822`[4 × group + `$102268`], group = `$11800`[the opponent's character]: Billy → stage 0 → `$E1`, Marian 1 `$E0`,
  Amon 2 `$EE`, Jimmy 3 `$E9`, Duke 4 `$E4`, Rebecca 5 `$DD`, Cheng-Fu 6 / 9 / 12 `$DC`, Abobo 7 `$DE`, Eddie 8 `$EA`,
  Dulton 10 `$DF` (the measured 2P fight: stage 10, `$DF`), Shuko 11 `$E2` (the final boss's stage shares the opening's
  song), Burnov 13 `$E3`.
- `$EB` and `$EC` were not heard (not in attract, a lost game or the stage tables). Both take ADPCM-A 4-6 as well
  (priority `$45`: no voice can play over them) and `$EB` runs 151 s before its 19 s loop: an ending / staff roll
  *(inferred)*.

## Catalogue

Model run to each channel's first jump back (every song: one tempo on all channels). Loop = (tick, length) of the
first channel's loop; FM patches = `$E1` values on FM 1-4 (26-byte patches at `$2000`); ADPCM-A tables = `$E1` values on
ADPCM-A 1-3 (tables at `$2D00`); notes = notes and samples read up to the loop.

| Cmd | Name | Bank:addr | Channels | Tempo | ticks/s | Loop (tick, length) | Intro + loop | FM patches | ADPCM-A tables | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| $DC | Stage: Cheng-Fu | 3:$8000 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $4E | 50.38 | 385, 3264 | 7.6 + 64.8 s | $41 $69 $6B | 1 3 | 2133 |
| $DD | Stage: Rebecca | 2:$B318 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $52 | 52.96 | 25, 3456 | 0.5 + 65.3 s | $1B $20 $47 $4D $66 $69 $76 | 1 3 | 1873 |
| $DE | Stage: Abobo | 2:$ABB8 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $5D | 60.07 | 1, 3072 | 0.0 + 51.1 s | $00 $1A $41 | 0 1 | 1647 |
| $DF | Stage: Dulton | 2:$A08E | FM1 FM2 FM3 FM4 B A1 A2 A3 | $72 | 73.63 | 1, 3456 | 0.0 + 46.9 s | $00 $08 $10 $13 $14 $1B $41 $46 $4C $66 | 0 1 | 1418 |
| $E0 | Stage: Marian | 2:$919D | FM1 FM2 FM3 FM4 B A1 A2 A3 | $5B | 58.77 | 199, 3072 | 3.4 + 52.3 s | $00 $11 $1B $41 | 0 1 | 2258 |
| $E1 | Stage: Billy | 2:$8000 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $53 | 53.61 | 49, 4032 | 0.9 + 75.2 s | $1A $1B $41 | 0 1 | 2020 |
| $E2 | Opening (attract) / Stage: Shuko | 1:$B2CC | FM1 FM2 FM3 FM4 B A1 A2 A3 SSGB SSGC | $56 | 55.55 | 2689, 4224 | 48.4 + 76.0 s | $13 $20 $41 $4D $66 | 0 1 | 3523 |
| $E3 | Stage: Burnov | 1:$AE95 | FM1 FM2 B A1 A2 A3 | $62 | 63.30 | 95, 3072 | 1.5 + 48.5 s | $41 | 1 3 | 1063 |
| $E4 | Stage: Duke | 1:$9CB0 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $5B | 58.77 | 97, 4128 | 1.6 + 70.2 s | $08 $41 | 0 1 | 2374 |
| $E5 | Continue | 1:$9B51 | FM1 FM2 FM3 FM4 B A2 A3 | $56 | 55.55 | - | 5.4 s (ends) | $1A $41 | 1 | 105 |
| $E6 | Player select | 1:$9224 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $5D | 60.07 | 397, 1536 | 6.6 + 25.6 s | $1A $20 $41 | 1 | 1000 |
| $E7 | Winner's scene (after a lost match) | 1:$8F5C | FM1 FM2 FM3 FM4 B A1 A2 A3 | $58 | 56.84 | - | 27.5 s (ends) | $08 $20 $41 | 1 | 759 |
| $E8 | How to play | 1:$897F | FM1 FM2 FM3 FM4 B A1 A2 A3 | $51 | 52.32 | 1, 768 | 0.0 + 14.7 s | $00 $13 $40 | 0 1 | 558 |
| $E9 | Stage: Jimmy | 1:$8000 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $53 | 53.61 | 97, 2208 | 1.8 + 41.2 s | $00 $10 $41 | 0 1 | 1516 |
| $EA | Stage: Eddie | 0:$A863 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $56 | 55.55 | 769, 2688 | 13.8 + 48.4 s | $00 $41 | 0 1 | 2115 |
| $EB | not traced | 0:$9980 | FM1 FM2 FM3 FM4 B A1 A2 A3 A4 A5 A6 | $37 | 35.52 | 5377, 672 | 151.3 + 18.9 s | $00 $46 $4E $50 $58 | 0 1 | 4053 |
| $EC | not traced | 0:$8E74 | FM1 FM2 FM3 FM4 B A1 A2 A3 A4 A5 A6 | $5F | 61.36 | 769, 1536 | 12.5 + 25.0 s | $1A $20 $41 | 0 1 | 1198 |
| $ED | Title | 0:$86C1 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $56 | 55.55 | 193, 2496 | 3.5 + 44.9 s | $00 $1A $20 $41 $66 | 0 1 | 1232 |
| $EE | Stage: Amon | 0:$8000 | FM1 FM2 FM3 FM4 B A1 A2 A3 | $4E | 50.38 | 25, 3072 | 0.5 + 61.0 s | $13 $1B $41 $69 $6B | 1 3 | 2026 |

`$E5` and `$E7` end (opcode `$F3` with offset 0 on every channel); every other song loops for ever (`$F3 00` + a
backward offset).

## Validation and port

Captures in our emulator (`tools/ngss/capture_ngss.py --songs`, `/data/neogeo_dict/sound/doubledr/cap`), each to the
song's loop point + 15 %; compared pass by pass (`regs_ngss.py`). Port: each song ported alone into KOF98's driver
(`tools/port`, `/data/neogeo_dict/sound/port/dd_all`), chip events identical over the intro + 2 loops
(`compare_port.py`); the reasons are in `doubledr_sound_driver.md` "Conversion to KOF98's driver".

| Cmd | Passes captured | Passes with writes identical | Port to KOF98: chip events identical |
|---|---|---|---|
| $DC | 14108 | 3417 / 3417 | no build: out of ADPCM-B records (many B pitches) |
| $DD | 14209 | 2142 / 2142 | no build: F-number $4CF above KOF98's reach |
| $DE | 10082 | 798 / 798 | 10278 / 10278 |
| $DF | 9258 | 1956 / 1956 | 7914 / 8326 (unequal carrier TLs, FM volume slides) |
| $E0 | 10916 | 1563 / 1563 | no build: port98 KeyError (an ADPCM-A level change of a sample sounding across the loop point) |
| $E1 | 14854 | 4028 / 4028 | no build: F-number $4CE above KOF98's reach |
| $E2 | 23992 | 8059 / 8059 | no build: 85 KB (vibrato as per-tick ties; SSG left out) |
| $E3 | 9856 | 544 / 544 | **6267 / 6267** (proof) |
| $E4 | 14004 | 1887 / 1887 | 11177 / 13562 (unequal carrier TLs, FM volume slides) |
| $E5 | 1357 | 129 / 129 | 252 / 521 (FM volume slides; the port loops, the song ends) |
| $E6 | 6531 | 645 / 645 | 4781 / 5177 (unequal carrier TLs, FM volume slides) |
| $E7 | 5555 | 462 / 462 | 1252 / 3193 (unequal carrier TLs; the port loops, the song ends) |
| $E8 | 3128 | 307 / 307 | 2346 / 2346 |
| $E9 | 8510 | 899 / 899 | **6180 / 6180** (proof) |
| $EA | 12180 | 1198 / 1198 | 7971 / 7971 |
| $EB | 32712 | 4245 / 4245 | no build: 40 KB (vibrato) |
| $EC | 7624 | 1025 / 1025 | 5432 / 5747 (unequal carrier TLs, FM volume slides) |
| $ED | 9540 | 852 / 852 | 7146 / 7570 (unequal carrier TLs) |
| $EE | 12071 | 2292 / 2292 | no build: out of ADPCM-B records |
| $EF | 12071 | 2292 / 2292 | = $EE |

Every song: **register-identical to the real driver on every pass**.
