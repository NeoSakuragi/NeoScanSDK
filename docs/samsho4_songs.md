# Samurai Shodown IV songs

The 37 music commands of Samurai Shodown IV: Amakusa's Revenge (SNK 1996, MAME `samsho4`), whose sound driver is SNK's `Sound Driver Ver 1.0 96/08/09 To SNK` (`samsho4_sound_driver.md`): catalogue, where each is heard, and the per-song validation of tools/kof98snd's model against the real driver. "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/samsho4/samsho4_m1.bin --catalog
    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/samsho4/samsho4_m1.bin 0x50 --list
    python3 tools/kof98snd/capture98.py --game samsho4 --songs /data/neogeo_dict/sound/samsho4/caps
    python3 tools/kof98snd/regs98.py /data/neogeo_dict/sound/samsho4/samsho4_m1.bin 0x50 /data/neogeo_dict/sound/samsho4/caps/cap_50.txt
    python3 tools/songlab/build_web.py --game samsho4 /data/neogeo_dict/sound/songlab/all/data/samsho4


## Catalogue

Command map (`$2FB0`, index cmd - `$20`): music `$21-$29`, `$2C-$3F`, `$50-$57` (37; `$20`, type 2 as well, is the all-off header the driver plays at a song stop). Captures: power-on, the game's own commands blocked from frame 878 (it sends `$07` at 876 and its first song `$21` at 880), the song sent at frame 900, length from song98.py to the loop point or the end + 15 %. Validation = sequencer interrupts whose register writes are identical in order; the one difference is `$22`'s last interrupt, which the capture cuts in the middle of the handler.

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: the Geolith core with makoto3's port tap, pad input by frame,
68K RAM pokes and watches, a screenshot 90 and 400 frames after each music command; logs and screenshots in
`/data/neogeo_dict/sound/samsho4/attract` (power-on, no input, 43000 frames) and `/data/neogeo_dict/sound/samsho4/run/*` (one credit, the first character, no
input after the select: the match is lost; `st*`: the same with the stage byte forced)). Bytes that follow a system
command taking a parameter (`$0A`, `$0E`, `$14`, `$15`, `$18-$1E`) are that command's argument, not a song: the logs mark them.

The 68K's sound requests: a sound ID indexes the long table `$55DE` (4 bytes sent in order, zeros skipped; `$55A4`;
`$5560` only when the ID differs from the last). **The fight theme** (`$2E600`): the word table `$2E644` indexed by the
opponent's character (`+$1E` of the fighter the long `$108334` points at, `& 31`); when that entry is 0, the word table
`$2E684` indexed by the stage number `$108B2A & 15`. Character order from the ROM's name list (`$38DB2`): Haohmaru,
Nakoruru, Rimururu, Hanzo, Galford, Kyoshiro, Ukyo, Genjuro, Basara, Shizumaru, Gaira, Amakusa, Jubei, Zankuro,
Charlotte, Tam Tam, Kazuki, Sogetsu; eleven have a theme of their own. Measured: Ukyo (the credit's opponent: `$50`,
stage number 6, so the stage numbers follow the character order, *inferred* beyond that). Not reached: a won match.


| Cmd | Header (bank set) | Tempo (ticks/s) | End | Heard at | Validation: identical sequencer interrupts, captured writes |
|---|---|---|---|---|---|
| `$21` | `$6C03` (0) | 80 (64.2) | ends (`$06`), 4082 ticks | opening and title, every attract cycle (measured); ID `$4B8` | 448 / 448, 4889 |
| `$22` | `$74A9` (0) | 141 (113.1) | loops | fight theme of Haohmaru (opponent table `$2E644`) | 629 / 630, 7960 |
| `$23` | `$83AB` (0) | 76 (61.0) | loops | fight theme of Genjuro (opponent table `$2E644`) | 733 / 733, 8100 |
| `$24` | `$924B` (0) | 64 (51.3) | loops | stage-number table `$2E684` entry 0 (Haohmaru's stage, *inferred*), played when the opponent has no theme of his own | 230 / 230, 2600 |
| `$25` | `$96B4` (0) | 90 (72.2) | loops | stage-number table `$2E684` entry 4 (Galford's stage, *inferred*), played when the opponent has no theme of his own | 131 / 131, 902 |
| `$26` | `$9815` (0) | 74 (59.4) | loops | stage-number table `$2E684` entry 7 (Genjuro's stage, *inferred*), played when the opponent has no theme of his own | 72 / 72, 840 |
| `$27` | `$98BD` (0) | 98 (78.6) | loops | stage-number table `$2E684` entry 3 (Hanzo's stage, *inferred*), played when the opponent has no theme of his own | 128 / 128, 1063 |
| `$28` | `$99B0` (0) | 90 (72.2) | loops | stage-number table `$2E684` entry 5 (Kyoshiro's stage, *inferred*), played when the opponent has no theme of his own | 86 / 86, 736 |
| `$29` | `$9AEF` (0) | 98 (78.6) | ends (`$06`), 193 ticks | not identified | 11 / 11, 91 |
| `$2C` | `$9B63` (0) | 90 (72.2) | ends (`$06`), 218 ticks | the map before a stage (measured) | 136 / 136, 849 |
| `$2D` | `$9F0E` (0) | 65 (52.1) | loops | not identified | 866 / 866, 6976 |
| `$2E` | `$AC4F` (0) | 90 (72.2) | loops | not identified | 175 / 175, 2107 |
| `$2F` | `$AE11` (0) | 80 (64.2) | ends (`$06`), 586 ticks | not identified | 89 / 89, 1324 |
| `$30` | `$B0A2` (0) | 145 (116.3) | loops | fight theme of Galford (opponent table `$2E644`) | 1271 / 1271, 16488 |
| `$31` | `$C746` (0) | 75 (60.2) | loops | fight theme of Sogetsu (opponent table `$2E644`) | 1158 / 1158, 9854 |
| `$32` | `$D8C9` (0) | 118 (94.6) | loops | fight theme of Amakusa (opponent table `$2E644`) | 3179 / 3179, 29889 |
| `$33` | `$E905` (0) | 99 (79.4) | loops | fight theme of Zankuro (opponent table `$2E644`) | 2010 / 2010, 22756 |
| `$34` | `$8000` (1) | 60 (48.1) | loops | stage-number table `$2E684` entry 6 (Ukyo's stage, *inferred*), played when the opponent has no theme of his own | 54 / 54, 270 |
| `$35` | `$8112` (1) | 60 (48.1) | loops | stage-number table `$2E684` entry 2 (Rimururu's stage, *inferred*), played when the opponent has no theme of his own | 586 / 586, 4457 |
| `$36` | `$8BAE` (1) | 60 (48.1) | loops | scene before the first stage (night, the clock) (measured); also stage-table entry 1; stage-number table `$2E684` entry 1 (Nakoruru's stage, *inferred*), played when the opponent has no theme of his own | 318 / 318, 2266 |
| `$37` | `$91A5` (1) | 60 (48.1) | loops | stage-number table `$2E684` entry 8 (Basara's stage, *inferred*), played when the opponent has no theme of his own | 105 / 105, 873 |
| `$38` | `$934F` (1) | 90 (72.2) | loops | stage-number table `$2E684` entry 9 (Shizumaru's stage, *inferred*), played when the opponent has no theme of his own; stage-number table `$2E684` entry 10 (Gaira's stage, *inferred*), played when the opponent has no theme of his own; stage-number table `$2E684` entry 11 (Amakusa's stage, *inferred*), played when the opponent has no theme of his own | 545 / 545, 6524 |
| `$39` | `$9E1E` (1) | 135 (108.3) | loops | player select and level choice (measured) | 252 / 252, 2934 |
| `$3A` | `$A08E` (1) | 110 (88.2) | ends (`$06`), 479 ticks | the moonlit scene before a fight; the attract demo (Jubei vs Shizumaru) (measured) | 166 / 166, 1600 |
| `$3B` | `$A54A` (1) | 100 (80.2) | ends (`$06`), 1154 ticks | result of a round ("Conclusion") (measured) | 201 / 201, 1082 |
| `$3C` | `$A8E9` (1) | 150 (120.3) | ends (`$06`), 1729 ticks | winner's scene after a lost match (measured) | 282 / 282, 2995 |
| `$3D` | `$AF84` (1) | 90 (72.2) | ends (`$06`), 193 ticks | continue, through the game over and the data save screen (measured) | 14 / 14, 154 |
| `$3E` | `$B010` (1) | 65 (52.1) | ends (`$06`), 1831 ticks | not identified | 455 / 455, 3467 |
| `$3F` | `$B7CB` (1) | 70 (56.1) | ends (`$06`), 6145 ticks | not identified | 543 / 543, 5710 |
| `$50` | `$C4CB` (1) | 117 (93.8) | loops | fight theme of Ukyo (opponent table `$2E644`; measured) | 1601 / 1601, 9514 |
| `$51` | `$8000` (2) | 96 (77.0) | loops | fight theme of Kazuki (opponent table `$2E644`) | 7324 / 7324, 38809 |
| `$52` | `$A293` (2) | 110 (88.2) | loops | fight theme of Nakoruru (opponent table `$2E644`) | 1087 / 1087, 10890 |
| `$53` | `$B4C4` (2) | 93 (74.6) | loops | fight theme of Rimururu (opponent table `$2E644`) | 1637 / 1637, 16896 |
| `$54` | `$D66B` (2) | 75 (60.2) | loops | fight theme of Charlotte (opponent table `$2E644`) | 854 / 854, 9456 |
| `$55` | `$E2D9` (2) | 80 (64.2) | loops | not identified | 4 / 4, 48 |
| `$56` | `$E313` (2) | 116 (93.0) | loops | not identified | 51 / 51, 364 |
| `$57` | `$E3EA` (2) | 65 (52.1) | loops | not identified | 53 / 53, 657 |
| all 37 | | | | | **27484 / 27485**, 236390 |

