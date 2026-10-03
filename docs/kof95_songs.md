# KOF95 songs

The 27 music commands of The King of Fighters '95, whose sound driver is a reworked build of Fatal Fury 3's "Ver 3.0
by MAKOTO" (`ff3_sound_driver.md`; KOF95's differences in its section "KOF95's build"): catalogue, where each is heard,
techniques, what is shared with KOF94 and FF3, and the per-song validation of tools/makoto3's model against the real
driver. Everything is decoded by `tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator;
*(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/kof95/kof95_m1.bin --catalog       one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/kof95/kof95_m1.bin 0x22 --list     the event listing
    python3 tools/makoto3/capture.py --game kof95 --songs /data/neogeo_dict/sound/kof95/cap  capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/kof95/kof95_m1.bin 0x22 /data/neogeo_dict/sound/kof95/cap/cap_22.txt

## Catalogue

Command map (`$72B4`): music `$20-$2E`, `$30`, `$31`, `$33-$3A`, `$50`, `$5F`; SSG effect songs `$60-$65`, `$6A`,
`$7F`; one-byte ADPCM-B effects `$80-$BF`, one-byte ADPCM-A effects `$C0-$FF`. Columns as in `kof94_songs.md`: "One
pass" = music ticks to the point where the last channel jumps back (looping songs) or to the end, seconds from the
timer-B period including `$33` tempo changes; validation = interrupts whose register writes (minus timer-flag and
end-flag housekeeping) are identical in the capture and in the model, and the number of captured writes compared.

"Heard at" comes from runs of the game in our emulator (`/data/neogeo_dict/sound/kof95/scratch/play.py`: command log
with the stage index and both teams, screenshots 90 / 300 / 520 frames after each music command):
`attract` (power-on, no input, 31 minutes, 17 demo fights), `attract_teams` (12.7 minutes), `play1` (a credit,
buttons mashed, the second player's health held at 1: lost the 4th match, game over), `play2` and `play3` (a credit,
Hero Team, the second player's health held at 1 (`$108420`, `$108422`, `$10844C`, max `$CF`) and the first player's at
`$CF`, every match won: 8 team matches, Saisyu, Omega Rugal, the ending). Stage themes are named by the team whose
stage it is: the 68K picks the theme by the stage index `$10A7E8`, which in all 8 arcade matches was the team of the
opponent's first fighter (cast order in `tools/kof95/rom.py`; the CPU teams are mixed, e.g. Ralf / King / Clark on the
Ikari stage); the stages on screen fit (Ikari: desert with a plane wreck, Women Fighters: King's bar, Art of
Fighting: a dojo).

| Cmd | Header (bank) | TB (ticks/s) | Channels | One pass | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|---|---|
| `$20` | `$74B5` (0) | `$B8` (48.2) | none | — | no channel on | never heard; no channel on (a silence); 68K ID `$48B` has no reference: unused *(inferred)* | 1 / 1, 7 |
| `$21` | `$7520` (0) | `$B5` (46.3) | FM1-4 A1236 B | 1994 ticks, 43.1 s | stops (`$40`) | opening, attract start (measured, every attract cycle, after `$07`; also after the game over) | 263 / 263, 5848 |
| `$22` | `$7AA1` (0) | `$C3` (56.9) | FM1-4 A1-3 B | 3841 ticks, 67.5 s | loops | stage theme, Hero Team (Kyo's team; attract, arcade, measured) | 1128 / 1128, 14947 |
| `$23` | `$9029` (0) | `$94` (32.2) | FM1-4 A1-3 B | 4705 ticks, 146.3 s | loops | stage theme, Korea Team (attract, arcade, measured) | 1815 / 1815, 25470 |
| `$24` | `$A17E` (0) | `$B8` (48.2), `$33` changes | FM1-4 A1-3 B | 4417 ticks, 99.8 s | loops | stage theme, Ikari Team (desert, plane wreck; attract, arcade, measured) | 1905 / 1905, 22447 |
| `$25` | `$B5F1` (0) | `$AE` (42.3) | FM1-4 A1-3 B | 841 ticks, 19.9 s | chains to `$50` (tick 841) | stage theme, Psycho Soldier Team: the intro, then `$50` (attract, arcade, measured) | 1234 / 1234, 20420 |
| `$26` | `$8000` (1) | `$C4` (57.9) | FM1-4 A1-3 B | 4225 ticks, 73.0 s | loops | stage theme, Fatal Fury Team (harbour; attract, arcade, measured) | 1189 / 1189, 14801 |
| `$27` | `$8EA1` (1) | `$B9` (48.9) | FM1-4 A1-3 B | 5377 ticks, 109.9 s | loops | stage theme, Art of Fighting Team (dojo; attract, arcade, measured) | 1475 / 1475, 20704 |
| `$28` | `$9BD4` (1) | `$BD` (51.8) | FM1-4 A1-3 B | 2785 ticks, 53.7 s | loops | stage theme, Women Fighters Team (King's bar; attract, arcade, measured) | 504 / 504, 15925 |
| `$29` | `$AA4C` (1) | `$B9` (48.9) | FM1-4 A1-3 B | 4249 ticks, 86.9 s | loops | stage theme, Rival Team (Iori's team; factory; attract, arcade, measured) | 1074 / 1074, 21535 |
| `$2A` | `$BA47` (1) | `$C0` (54.3) | FM1-4 A1-3 B | 4233 ticks, 78.0 s | loops | Saisyu Kusanagi, the ninth match (stage index 8, measured) | 1188 / 1188, 14999 |
| `$2B` | `$C924` (1) | `$B5` (46.3) | FM1-4 A1234 B | 2833 ticks, 61.2 s | loops | staff roll, after the team ending (measured) | 876 / 876, 10637 |
| `$2C` | `$D294` (1) | `$C3` (56.9) | FM1-4 A1-3 B | 253 ticks, 4.4 s | loops | team select, and the select / VS screens between matches (attract demo and arcade, measured) | 103 / 103, 1870 |
| `$2D` | `$CC2E` (0) | `$9F` (35.8) | FM1-4 A1234 B | 2527 ticks, 70.6 s | loops | start of the between-match screen after the 3rd and the 8th match, replaced by `$2C` 47-78 frames later (measured, under 1.3 s heard); an arrangement of KOF94's `$29` | 686 / 686, 9201 |
| `$2E` | `$D29D` (0) | `$9F` (35.8) | FM1-4 A1234 B | 2497 ticks, 69.8 s | loops | the same after the 6th match, replaced by `$2C` after 47 frames (measured); another version of `$2D` | 730 / 730, 10027 |
| `$30` | `$D4F3` (1) | `$C0` (54.3) | FM1-4 A1236 B | 302 ticks, 5.6 s | stops (`$40`) | after each match: the winners' quote screen (measured) | 58 / 58, 1750 |
| `$31` | `$D7E7` (1) | `$BE` (52.6) | FM1-4 A1234 B | 97 ticks, 1.8 s | stops (`$40`) | game over: the GAME OVER / ranking screen (measured) | 29 / 29, 484 |
| `$33` | `$D79B` (0) | `$A1` (36.5) | FM1-4 A1234 B | 421 ticks, 11.5 s | loops | after Saisyu's defeat, replaced by `$37` 53 frames later (measured) | 106 / 106, 2143 |
| `$34` | `$D9D8` (0) | `$B9` (48.9) | FM1-4 A1236 B | 829 ticks, 17.0 s | loops | not heard; requested by ending-scene code (`$45778`, `$4614C`), another team's ending *(inferred)* | 402 / 402, 6302 |
| `$35` | `$DFBF` (0) | `$8C` (29.9) | FM1-4 A1-3 B | 1093 ticks, 36.5 s | loops | not heard; requested by ending-scene code (`$447D4`, `$4656A`), another team's ending *(inferred)* | 421 / 421, 6989 |
| `$36` | `$E4D2` (0) | `$AB` (40.8) | FM1-4 A1-3 B | 1189 ticks, 29.1 s | loops | team ending (Hero Team; measured) | 432 / 432, 6850 |
| `$37` | `$EA55` (0) | `$BC` (51.1) | FM1-4 A1-3 B | 2953 ticks, 57.8 s | loops | Omega Rugal: his entrance and the fight (measured) | 582 / 582, 20159 |
| `$38` | `$F24A` (0) | `$BB` (50.3) | FM4 A1-3 | 193 ticks, 3.8 s | loops | after START: the how-to-play screen until team select (measured) | 32 / 32, 571 |
| `$39` | `$F35A` (0) | `$A8` (39.5) | FM1-4 A12 B | 1561 ticks, 39.6 s | loops | Omega Rugal defeated (his last scene; measured) | 120 / 120, 2913 |
| `$3A` | `$D920` (1) | `$B5` (46.3) | FM1-4 A1236 B | 217 ticks, 4.7 s | loops | after a coin (measured) | 42 / 42, 1489 |
| `$50` | `$BB1C` (0) | `$BE` (52.6) | FM1-4 A1-3 B | 2665 ticks, 50.7 s | loops | the Psycho Soldier Team theme's main part, reached only by `$25`'s chain (measured) | 1029 / 1029, 17306 |
| `$5F` | `$F563` (0) | `$C0` (54.3) | FM1-4 | 386 ticks, 7.1 s | stops (`$40`) | NEO-GEO logo jingle at boot and every attract cycle, started by command `$02` (measured) | 259 / 259, 1917 |
| all 27 | | | | | | | **17683 / 17683**, 277711 |

Order of a power-on (measured, every attract cycle): `$01`, `$03` resets, `$02` under the NEO-GEO logo (= `$5F`),
`$07` (unlock) at frame 869, `$21` at 874 (the opening), slot-0 effects (`$18` + code) during it, `$2C` for the demo's
team select (with SSG effects `$60` / `$61`), the demo's stage theme, then `$01 $03 $03 $02` again. A credit: `$3A` at
the coin, `$0A` (fade) and `$38` at START (the how-to-play screen), `$2C` at team select, the stage theme; at each
KO `$0A` (fade), then `$30` (winners' quote), `$04 $07 $07`, `$2C` for the next opponent (`$2D` after the 3rd and the
8th match and `$2E` after the 6th, each replaced by `$2C` 47 to 78 frames later). The 8 team matches ran on the stages of
Hero, Women Fighters, Psycho Soldier, Fatal Fury, Rival, Art of Fighting, Ikari and Korea (play3; play2: Hero, Women,
Rival, Fatal Fury, Ikari, Art of Fighting, Korea, Psycho Soldier). The final: `$2A` (Saisyu, stage index 8), `$0A`,
`$33`, `$37` 53 frames later (Omega Rugal's entrance and fight), `$0A`, `$39` (his last scene), `$05 $08 $08`, the team
ending `$36`, `$0A`, the staff roll `$2B`, then the attract (`$21`). Losing with no credit (play1): `$04 $07 $07 $04 $07`,
the silent name entry, `$31` (GAME OVER / ranking), then the attract.

Channel use: FM 1-4 + ADPCM-A 1-3 + ADPCM-B in every stage theme, Saisyu `$2A`, Omega Rugal `$37`, `$35`, `$36`, `$39`
(A1-2) and `$50`. ADPCM-A 4-6 only outside fights: A4 in `$2B`, `$2D`, `$2E`, `$31`, `$33`; A6 in `$21`, `$30`, `$34`,
`$3A`. Unlike FF3 and KOF94, KOF95's effect allocator leaves those channels to the song (`ff3_sound_driver.md`,
"KOF95's build"). `$38` is FM4 + ADPCM-A 1-3 only (a bass and drum loop of 192 ticks); `$5F` FM only; no song uses SSG.

## Techniques in the data

- **Ties for held notes and volume shapes** (as FF3 / KOF94): `$22` 492, `$2A` 311, `$24` 307, `$25` 280, `$36` 233
  ties in their first 8000 ticks.
- **Octave and detune per patch change**: octave bytes in 25 songs (`$23` 132 patch changes with an octave shift),
  detune bytes other than `$B8` (0) in 25 songs.
- **Tempo moves**: only `$24` (Ikari) changes timer B (`$33`, twice). **Chains**: only `$25` → `$50` (opcode `$47` at
  tick 841: a 19.9 s intro at TB `$AE`, then the main part at `$BE`). No gate mode (`$3D`), no hardware LFO (`$4E`), no
  fade opcode (`$3F`), no software vibrato depth in any patch. Four songs stop (`$40`): `$21`, `$30`, `$31`, `$5F`.
- **ADPCM-B** only as one pitched sample (`$46` `$40-$7F`, 24 songs, up to 7 samples a song); neither the drum kit
  (`$46` < `$40`, used by KOF94) nor the per-octave mode is selected.
- **ADPCM-A**: per-song sample tables are back (FF3's scheme; KOF94 had one table), but 25 songs point at the same
  table `$5850` (the records of effect slot 2, whose enable bitmap is empty: the music's own bank); 182 different
  records played, none looping (no loop replays in any capture).
- **An unmatched loop end**: `$29`'s ADPCM-A 3 stream reaches `$34` at `$B6A9` with an empty loop stack (ticks 3097,
  6937). KOF95's driver ignores it (`$2416`); FF3's and KOF94's would decrement the depth from 0 and jump through a
  stale entry. Validated (the capture covers both ticks).

## Shared with KOF94 and FF3

Compared on the decoded note streams of every FM and ADPCM-B channel (`/data/neogeo_dict/sound/kof95/scratch/
shared*.py`): 12-note runs with exact pitches and lengths; runs of intervals with length ratios (key and tempo free);
runs of 12 intervals with at least 6 different ones, rhythm and repeated notes ignored. And byte-identical data.

- **`$2D` / `$2E` are an arrangement of KOF94's `$29`** (Rugal's first-fight theme): same timer B (`$9F`), 42 runs of
  12 notes identical in pitch and length, 30 of 180 rhythm-free melodic runs shared; the streams, patches and parts
  differ (`$2E`'s FM1: 47 % of its first 400 notes align with KOF94's FM1). `$2D` and `$2E` are two versions of it: the same
  2496-tick loop and tempo, about 60 % of their note sequences aligned, different openings (`$2D` begins with a
  30-tick rest).
- **`$5F` (the NEO-GEO logo jingle) is KOF94's data**: the streams are byte-identical except the relocated call
  addresses and the volume bytes, which are FF3's (2 lower than KOF94's); patch numbers are KOF94's, and patches 0 and
  1 are byte-identical with KOF94's.
- **No other song shares melodic material** with any KOF94 or FF3 song by these tests (all channels, all songs). The
  stage themes are new compositions or arrangements too free for them: KOF94's Japan theme `$26` against KOF95's
  Hero Team theme `$22`, for one, has no 12-interval run in common. *(The claim that KOF95 arranges many KOF94 themes
  is not supported by the note data, apart from `$2D` / `$2E`.)*
- Patches: 19 of KOF95's 45 used patch slots hold a patch byte-identical with one of KOF94's (16 distinct patches);
  9 distinct patches are byte-identical with FF3's.
- The M ROM's last 35438 bytes (`$17592-$1FFFF`) are byte-identical with KOF94's at the same offsets: KOF94's song data
  left in the file, outside anything KOF95's songs point to *(inferred from the header table and bank map)*.

## 68K side: who sends what

`ff3_sound_driver.md`, "What the 68000 sends (KOF95)": music IDs `$478-$499` in the table `$59A10`, the stage table
`$3B36C`. Every music command has a constant reference or the stage table behind it except `$20` (empty, ID `$48B`:
unused *(inferred)*); `$50` has no ID (only `$25`'s chain); the ID `$489` → `$32` is a type-0 command in this build
(ignored by the driver) and has no reference. `$34` and `$35` have references in the ending code but were not heard
(one team's ending played). Blind spots: IDs computed at run time (29 call sites), the second P-ROM MB.

## Validation

All 27 commands captured in our emulator (`tools/makoto3/capture.py --game kof95 --songs`): power-on, the game's own
commands blocked from frame 870 (after its `$07` at 869; its first song, `$21`, comes at 874), the song sent at frame
900, captured for its pass + 15 %. The model runs on the captured interrupt order (timer A / timer B, measured) from
the command on and its register writes are compared interrupt by interrupt (`regs.compare`).

- **17683 of 17683 interrupts with writes identical, 277711 captured writes compared, no difference in any song**,
  on the first run with KOF95's table addresses (`games.py`; the depth-4 stack guard added afterwards changes no
  write). Exercised here and not in KOF94: a chain (`$25` → `$50`), tempo changes in a looping song (`$24`), an
  unmatched loop end (`$29`).
- Left out on both sides, as for FF3: `$27` (timer flags), `$1C` (ADPCM end-flag resets), ADPCM-B `$10` = 0, and the
  capture's last interrupt.
- Not exercised by any song: software vibrato, the ADPCM-B pitch / level effects, fades (`$3F`; the game's `$0A` was
  not captured), gate modes, the hardware LFO.
- Song Lab data: `tools/songlab/build_web.py --game kof95` → `/data/neogeo_dict/sound/songlab/all/data/kof95/`.
