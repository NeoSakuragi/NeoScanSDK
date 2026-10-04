# Kizuna Encounter songs

The 23 music commands (type 2 in the command table `$2E6C`) of Kizuna Encounter: Super Tag Battle, as SNK's
"Sound Driver Ver 0.0" plays them (docs/kizuna_sound_driver.md). Command `$20` is the all-off header (the game sends it
to stop the music between screens).

Names are the screen the game sent the command on, measured in our emulator (attract mode over 60 000 frames, and a
credit played: coin, how to play, tag team select, one fight lost, continue, game over; screenshots in
`/data/neogeo_dict/sound/kizuna/attract`). The attract demos play only `$21-$24`; the stage songs are named by the
stage on screen, not by character (*the character each stage belongs to is not identified*). `?` = not reached in
those runs. Songs `$37` / `$3A` and `$2F` / `$3B` have the same length and channel set and the same one-shot sample calls at the
same ticks; `$37` and `$2F` add the sequenced effects `$F2` / `$F3` at the end; *probably variants of the same
pieces*.

Columns: tempo = header byte (ticks/s = 166.83 × tempo / 208); channels the header enables; loop = the longest
channel loop period of the model (or "ends"); writes = captured / model writes (timer and end-flag writes excluded,
as regs98.py); identical = sequencer interrupts whose writes are identical in order and value / interrupts with writes.

| Cmd | Screen | Tempo (ticks/s) | Channels | Loop | Writes cap / model | Identical |
|---|---|---|---|---|---|---|
| `$21` | Stage (dusk street, attract demo) | 115 (92.2) | FM1-4 A1-3 B | 9312 ticks | 16504 / 16504 | 1189/1189 |
| `$22` | Stage (night harbour, attract demo) | 102 (81.8) | FM1-4 A1-3 B | 6000 ticks | 17169 / 17169 | 900/900 |
| `$23` | Stage (moonlit rooftop, attract demo) | 132 (105.9) | FM1-4 A1-3 B | 8448 ticks | 21883 / 21883 | 1297/1297 |
| `$24` | Stage (harbour market; the first stage of the played credit) | 86 (69.0) | FM1-4 A1-3 B | 5760 ticks | 16649 / 16649 | 920/920 |
| `$25` | Ranking (attract) | 120 (96.2) | FM1-4 A1-3 B | 4608 ticks | 10633 / 10633 | 580/580 |
| `$2B` | ? | 130 (104.3) | FM1-4 A1-3 B | 8640 ticks | 36795 / 36795 | 1091/1091 |
| `$2C` | ? | 110 (88.2) | FM1-4 A1-4 B | 11160 ticks | 14018 / 14018 | 1323/1323 |
| `$2D` | ? | 104 (83.4) | FM1-4 A1-6 B | 5376 ticks | 15150 / 15151 | 1324/1325 * |
| `$2E` | ? | 106 (85.0) | FM1-4 A1-6 B | 768 ticks | 3752 / 3752 | 230/230 |
| `$2F` | ? | 155 (124.3) | FM1-4 A1-5 B | ends | 6409 / 6409 | 433/433 |
| `$30` | ? | 80 (64.2) | FM1-4 A1-3 A5-6 B | 768 ticks | 2370 / 2370 | 214/214 |
| `$31` | ? | 108 (86.6) | FM1-4 A1-3 A6 B | 768 ticks | 1850 / 1850 | 110/110 |
| `$32` | Tag team select | 145 (116.3) | FM1-4 A1-3 B | 768 ticks | 1913 / 1913 | 153/153 |
| `$33` | ? | 175 (140.4) | FM1-4 A1-3 B | 1536 ticks | 3175 / 3175 | 263/263 |
| `$34` | ? | 105 (84.2) | FM1-4 A1-3 B | 1536 ticks | 3607 / 3607 | 321/321 |
| `$35` | ? | 145 (116.3) | FM1-4 A1-3 B | 1536 ticks | 3107 / 3107 | 241/241 |
| `$36` | Continue (sent 100 frames after `$39`, after a `$20`) | 160 (128.3) | FM1-4 A1-3 B | 768 ticks | 1364 / 1364 | 85/85 |
| `$37` | ? | 167 (133.9) | FM1-4 A1-5 B | ends | 6392 / 6392 | 411/411 |
| `$38` | ? | 155 (124.3) | FM1-4 A1-3 B | 384 ticks | 1688 / 1694 | 102/103 * |
| `$39` | Continue (its first song) | 180 (144.4) | FM1-4 A1-3 B | 1536 ticks | 2589 / 2589 | 214/214 |
| `$3A` | Title (power-on, every attract loop) | 167 (133.9) | FM1-4 A1-5 B | ends | 6359 / 6359 | 404/404 |
| `$3B` | How to play (after a coin) | 155 (124.3) | FM1-4 A1-5 B | ends | 6376 / 6376 | 426/426 |
| `$50` | Game over | 113 (90.6) | FM1-4 A1-3 A5-6 B | ends | 197 / 197 | 19/19 |

\* the one differing interrupt is the capture's last, cut in the middle of the handler.

Attract sequence (measured): `$3A` title at frame 935, fade (`$0A`), `$25` ranking, then a demo fight on `$21`, `$22`,
`$23` or `$24`, back to `$3A`. A credit: coin → `$3B` how to play, `$32` tag team select, `$24` first stage, (fight
lost) `$39` then `$36` continue, `$50` game over.

## Song features (song98.py census, first pass of every song)

Notes `$2A` 25 355 and `$00` 2 316; loops `$07`/`$08`, calls `$09`/`$0A`, goto `$0B`, restart `$16`; pan `$2B` 5 188
(the songs pan almost every phrase); `$0E` 545 (a no-op in this version, used as a timed wait); FM patches `$03` 476;
direct-level mode (`$25` level, `$24` octave, songs `$23`, `$2B`, `$2E`, `$31`, `$50`), the others scaled (`$26`);
detune `$2E` (echo voices, as KOF98); LFO `$11` (`$23`, `$2B`, `$2E`); one effect: ADPCM-B pitch effect type 1
(square, depth 256, speed 7: a trill) in `$34`, `$35`, `$36`. Sample effects from the stream (`$1E`): `$2F`, `$37`,
`$3A`, `$3B` (one-shots `$00`, `$CA`, `$EF` and the sequenced effects `$F2` / `$F3` on A5 / A6).

## Song Lab

`python3 tools/songlab/build_web.py --game kizuna /data/neogeo_dict/sound/songlab/all/data/kizuna` (all 23 songs,
names above), listed in `data/games.json` as "Kizuna Encounter".
