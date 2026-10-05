# Brawler data model

Bruno's rule (2026-10-05): everything is data driven. The brawler (examples/brawler) is an engine plus data; the data
lives in one file, `examples/brawler/game.json`, which the Brawler Lab (the web editor; the Chain Lab is its first tab)
will edit. This document is the schema of that file, how the build turns it into tables, the binary layout of each
table in the ROM or in RAM, and which tables can be swapped while the game runs.

Status: step 1 done (2026-10-05, brawler 0.0.34 + the data layer). Today's game is written out in game.json and the
game reads only generated tables; the game plays exactly as 0.0.34 did (proof at the end). Step 2 done (2026-10-05):
enemies are definitions (name, colours, trimmed move list, AI preset + overrides, life, power), the lab's write path
installs stages, enemies and AI rows into the running game (data packs), proofs are keyed by the game's tick counter.

## The four layers

| layer | what | where it lives | edited by |
|---|---|---|---|
| 0, the bank | KOF96 / 98 / 99 fighters as extracted: animations, frames, hit boxes, timing, palettes, captured specials and throws, sound commands per move | /data/neogeo_dict (dictionaries), tools/kof96 (export96), never edited | nobody: templates |
| 1, roster | the playable characters: which bank fighter, select pose, specials mapping, chain routes, unlock; the select screen | game.json `roster`, `select` | Brawler Lab: Characters tab (Chain Lab today) |
| 2, enemies | named enemies on a bank fighter (or a pool of them), life, power, AI preset; the AI presets; the minion tints | game.json `enemies`, `ai`, `tints` | Brawler Lab: Enemies tab |
| 3, stages | background, music, waves (lock points + spawns), the boss with its minions and song; later triggers and drama | game.json `stages` | Brawler Lab: Stages / Waves tab |

## Build flow

```
game.json --build_tables.py roster--> build/roster.json --export_bm.py--> build/bm_chars.c/.h, bm_c1/c2.bin, chainlab.json
          --build_tables.py chars---> the Makefile's CHARS (bank specs, bm_chars order: make_hud.py portraits)
          --build_tables.py tables--> build/game_tables.c/.h (types: examples/brawler/gamedata.h)
```

- `build/roster.json` is rewritten only when the roster's export inputs change (bank, watch, specials, routes), so a wave
  or AI edit rebuilds the small tables (seconds), not the fighters (80 s).
- The generator checks names (fighters, enemies, presets, tints, songs: a wrong song name fails the compile, `MUS_*`),
  counts (6 enemies at once, 5 minions with a boss, 16 select slots, every roster fighter in one slot), lock points
  inside the stage (widths from build/stage.h) and moving forward.
- It writes C with designated initialisers (`.life = 60`), so a field added to gamedata.h needs no generator change to
  compile (it reads 0 until the generator writes it).
- `build_tables.py format game.json` rewrites the file in its canonical layout (one line per spawn, slot, preset
  field group). The lab should write the same layout so diffs stay readable.

## What the game reads

At boot `gdata_init()` (main.c) sets two pointers, `gstages` and `genemies`, to the ROM tables, and copies the AI
presets into RAM (`ai_presets[]`). Everything reads through those, the same pattern as the chain routes (`route_tab[]`
points at each fighter's tree; the Chain Lab writes a tree into `lab.buf` and repoints). Live-swappable therefore means:
a lab writes a replacement table into RAM and changes the pointer (or, for the AI presets, writes the bytes in place).

| table | type (gamedata.h) | size | in | live-swappable |
|---|---|---|---|---|
| AI rows | `ai_preset_t ai_presets[AI_COUNT]` via `ai_tab` | 40 bytes each | RAM (copied at boot) | yes: write the bytes (next decision), or a data pack (next spawn) |
| enemies | `genemy_t genemies_rom[]` via `genemies` | 26 bytes each | ROM, pointer in RAM | yes, a data pack; read at each spawn |
| stages, waves, spawns | `gstage_t`, `gwave_t`, `gspawn_t` via `gstages` | 24 / 6 / 8 bytes | ROM, pointer in RAM | yes, a data pack; `gs` re-read at the safe point, its waves and spawns as they come |
| tints | `gtint_t gtints[]` | 6 bytes each | ROM | not yet (a pointer when the lab needs it) |
| select slots | `sel_slot_t SEL_SLOT[]`, `sel_fighter[]` | 4 + 1 bytes each | ROM; `slot_ch[]` RAM copy made on each select screen | `slot_ch` yes (RAM) |
| unlocks | `roster_unlock[BC_COUNT]` | 1 byte each | ROM | no (save bits follow the stage order) |
| chain routes | `rt_head_t` + `rnode_t[]` (fighter.h) | 16 + 22 bytes a node | ROM, `route_tab[]` in RAM | yes: the Chain Lab (lab.buf, `lab.load`) |
| fighters | `bchar_t bm_chars[]` + everything it points at | ~35 KB each | ROM ($200000) + C ROM | no: new content = a ROM build |

## Layer 0: the bank

One entry per KOF fighter, read by `export_bm.py` from the game's dictionary (`tools/kof96/export96.py`, any of KOF96,
KOF98, KOF99): every animation (6-byte step records: ticks, frame, flags, then commands), the frames (sprite parts and
tiles), hit / hurt boxes, palettes (every colour set), physics, captured specials (scripts of rows) and throws
(thrower and victim timelines), victim postures. The bank is addressed by a spec `game:name` (`kof98:terry`). It is
never edited: layer 1 picks from it.

Sound commands per move are in the bank too (research below): today the export does not keep them.

## Layer 1: roster and select screen

`roster` is a list; its order is the order of `bm_chars[]` (BC_* in bm_chars.h) and of the HUD portraits.

| field | example | meaning |
|---|---|---|
| `name` | `"terry"` | unique; the export name (upper case on screen) |
| `bank` | `"kof98:terry"` | the layer-0 fighter |
| `watch` | `{"frame": 351, "step": -1}` | the select screen's pose: KOF state and step (-1 = its last, held) |
| `routes` | `"tools/brawler/routes/terry.json"` or `"default"` | its chain route tree (routes.py format; default = the pre-Chain-Lab table) |
| `specials` | `{"D": "EX 236C", "fD": "214C", "dD": "623C", "uD": "214D"}` | the KOF input played by D, forward+D, down+D, up+D; null = none. `export_bm.suggest_specials` is the automatic pick that filled these |
| `unlock` | `"always"` or `{"boss_of_stage": 1}` | locked on the select screen until that stage's boss is beaten (save bit stage - 1) |

Later (step 3 and on): `voices` (per move, see below), `palettes` (custom colour sets), `moves` (a trimmed list).

`select.slots`: `{"x": 40, "z": 48, "row": 0, "fighter": "terry"}` per slot; row 0 front, 2 back (`SEL_BACK`, the
bosses). Generated as `SEL_SLOT[]` (x int16, z, row: 4 bytes) and `sel_fighter[]` (bm_chars index, 0xFF empty).

ROM side of a fighter (`bchar_t`, export_bm.py): name, palettes, frames, animations (`banim_t` / `bstep_t`), physics,
throws, victim poses, specials (`bspec_t`, rows of a script), tile page, command normals, its route blob, its index.

## Layer 2: enemies, AI presets, tints

`enemies` is a list of named entries:

| field | example | meaning |
|---|---|---|
| `name` | `"YAKUZA"` | unique (EN_YAKUZA in game_tables.h); shown in the HUD (`_` as a space, 1-10 characters) |
| `hud` | `"fighter"` | the HUD shows the fighter's name instead (today's minions and bosses) |
| `base` | `"mr_big"` or `"pool"` | a roster fighter, or one of `pool` picked per spawn |
| `pool` | `["terry", "ryo", ...]` | base pool: the candidates in roster order; the players' fighters are left out at the stage start |
| `stand_in` | `"yashiro"` | fights when `base` is not in the roster |
| `life` | `100` | life at NORMAL difficulty (EASY x0.5, HARD x1.5, MANIAC x2; the attract demo keeps 60) |
| `power` | `1` | extra damage a hit, on top of the stage's `power` |
| `ai` | `"boss"` | AI preset in the campaign |
| `attract_ai` | `"minion_attract"` | AI preset in the attract demo (default: `ai`) |
| `ai_over` | `{"grab_plan": 6, "hold_gap": 18}` | per-enemy AI: any preset field (flags as a list), merged over `ai` and `attract_ai` at build time into the enemy's own AI row (identical rows shared) |
| `palette` | `{"set": 2}`, `{"tint": "ash", "set": 1}`, `{"custom": [16 colours]}` | its colours; left out: the spawn's `set` / `tint`. `custom`: 16 Neo Geo colour words replacing the first palette of its set (`set`, default 0): ROM or pack bytes and the palette RAM it already uses, nothing else |
| `moves` | `"own"`, `"jabs"`, `"no_specials"`, `"tools/brawler/routes/enemies/viper.json"` | its trimmed move list: its fighter's own tree, a named preset (routes.py `ENEMY_PRESETS`: jabs = A, A, strong close C; no_specials = its own tree without special links) or a routes file (routes.py format); encoded against every fighter it may be (each must have the moves) |

`genemy_t` (26 bytes): 0 base (bm_chars index, 0xFF = pool), 1 ai, 2 attract_ai (AI rows), 3 power, 4 npool, 5 set and
6 tint (0xFF = the spawn's), 7 flags (1 = the HUD shows the fighter's name), 8 life (int16), 10 pool, 14 name, 18 pal (16
words), 22 moves (rt_head_t tree; 0 = route_tab's, the fighter's own); the game gives each spawned enemy its name, custom
palette and tree (fighter_t `name`, `cpal`, `tree`; fighter.c TREE() reads `tree` first).

Examples (no wave uses them yet): YAKUZA (yamazaki, minion + grab_plan 6, custom dark suit, 60 life), VIPER (mai, minion
+ full_speed, short rests, follow-ups 3, attack_dx 30, viper.json: jabs at 1.25x and a tripping sweep, ash tint on set 1,
30 life), SNIPER (ryo, minion with only `projectile`, attack_dx 110, hover_dx 140, spec range 60-220, proj_chance 32,
jabs, colour set 2, 45 life).

`ai.tokens` (1): attack tokens dealt every 16 frames to the closest able enemies. `ai.presets` (today minion,
minion_attract, boss), all fields bytes, `ai_preset_t` (40 bytes) in this order (build_tables.py AI_ORDER; game_tables.c
asserts every offset), then one row per enemy with `ai_over`:

| field | minion | boss | meaning |
|---|---|---|---|
| `flags` | grab, projectile | token, grab, projectile, boss_moves | token: always holds one; grab: approaches may grab; projectile: fires its D at mid range; reversal (rev_*), specials (bspec_*), jump_in (jump_*): the boss block's three, `boss_moves` = all three; full_speed: walks at full speed while positioning (the others at half) |
| `rest_shift`, `rest_random`, `rest_add` | 0, 127, 0 | 2, 31, 0 | a rest = (base >> shift) + (random & rest_random) + rest_add (minion_attract: rest_add 100, no grab, no projectile) |
| `rest_start`, `rest_attack`, `rest_special`, `rest_throw` | 30, 120, 180, 60 | 60, ... | rest bases: at spawn, after a punch string, a D, a throw |
| `grab_plan` | 1 | 1 | approaches of 8 that walk in to grab |
| `attack_dx`, `hover_dx`, `hover_go_dx`, `hover_go_dz` | 36, 90, 16, 8 | same | token holder distance; the others'; when a hoverer sets off again |
| `range_min`, `range_max`, `range_dz` | 20, 52, 6 | same | punch range |
| `spec_min`, `spec_max`, `spec_dz` | 70, 140, 10 | same | D projectile range |
| `follow_ups` (json) -> `follow_mask` | 1 | 1 | 0..N follow-up presses (N + 1 a power of two) |
| `press_gap`, `hold_gap` | 10, 24 | same | frames between presses; between hits in a hold |
| `rev_dx`, `rev_dz`, `rev_chance`, `rest_rev` | - | 56, 12, 4, 160 | boss: down+D against an attack this close, 1 in rev_chance |
| `bspec_min`, `bspec_max`, `bspec_dz`, `bspec_chance`, `rush_dx`, `rest_bspec` | - | 20, 160, 10, 4, 110, 180 | boss: D or forward+D (the rush, 1 in 2 when closer than rush_dx) |
| `jump_min`, `jump_max`, `jump_dz`, `jump_chance`, `rest_jump`, `air_b_dx` | - | 24, 140, 8, 64, 140, 56 | boss: jump-in (jump_chance of 256), air B this close |
| `proj_chance` (json) -> `proj_mask`, `proj_mask2` | 512 | 512 | the projectile, 1 in N a frame in range: (random & proj_mask) == 0, then (random & proj_mask2) == proj_mask2 (512 = 255, 1: the 0.0.34 rule, the same random draws) |

Spec's names for the overrides: aggression = `token` + the rests, rest = `rest_*`, preferred range / depth =
`attack_dx`, `hover_dx`, `range_*`, special / jump-in / grab chance = `proj_chance` and `bspec_chance`, `jump_chance`,
`grab_plan`, reaction to attacks = `reversal` + `rev_*`.

Chances are "1 in N" with N a power of two (the game masks a random byte). The attract demo's player (`ai_bot`) is not
an enemy and keeps its constants in ai.c.

`tints` (the minions' colours, never a playable set): channel = ((l * mix + channel) * mul >> shift) + add, clamped
0-31, l = (5 R + 9 G + 2 B) / 16. shade {1, 11, 5, [0, 0, 0]}, ash {3, 14, 6, [-1, 0, 3]}, rust {1, 12, 5, [3, 0, -2]}.
`gtint_t` (6 bytes): mix, mul, shift, add[3]; index 0 = none.

## Layer 3: stages

| field | example | meaning |
|---|---|---|
| `name` | `"STAGE 1"` | |
| `background` | `0` | stages[] of make_stage_ra.py (Robo Army's parts today) |
| `music` | `"FIGHT"` | songs.json name, started at the stage start |
| `power` | `0` | its enemies' extra damage a hit |
| `waves[]` | | in order; the camera stops at each lock point until its wave is beaten |
| `waves[].lock` | `448` | camera x of the lock point (0 = the stage start) |
| `waves[].seed` | `"0x1D2C"` | the AI random generator's seed at this wave |
| `waves[].spawns[]` | `{"enemy": "MINION", "pick": 3, "set": 1, "walk_in": {"side": "left", "rank": 0}, "z": 17}` | one enemy each, at most 6 |
| spawn `pick` | `3` | pool enemies: pick mod the pool left |
| spawn `set` | `1` | colour set, mod the fighter's sets |
| spawn `x` / `walk_in` | `200` / `{"side": "right", "rank": 1}` | a world x, or off screen walking in: the right (camera + 340 + rank x 36) or the left (camera - 24 - rank x 36, the right when the camera is under x 64) |
| spawn `z` | `17` | depth |
| spawn `tint` | `"ash"` | a tints name (default none) |
| spawn `not_boss` | `true` | a pool pick equal to the stage boss's fighter takes the next one |
| `boss` | `{"enemy": "MR_BIG", "song": "BOSS_MR_BIG", "lock": 2240, "x": 2544, "z": 30, "seed": "0x5B05", "minions": [...]}` | the last lock point; the boss (slot 2) and up to 5 minion spawns |

Binary (all through `gstages`): `gstage_t` 24 bytes: 0 bg, 1 music (driver command), 2 power, 3 nwaves, 4 waves*,
8 spawns*, 12 boss (enemy index), 13 boss_song, 14 unlock (beating it unlocks its fighter), 15 boss_z, 16 boss_lock,
18 boss_x, 20 boss_seed, 22 boss_first, 23 nmin. `gwave_t` 6 bytes: 0 lock, 2 seed, 4 first spawn, 5 n.
`gspawn_t` 8 bytes: 0 enemy, 1 pick, 2 set, 3 tint, 4 x, 6 z, 7 flags (1 walk in, 2 from the left, 4 not the boss,
bits 4-7 rank). One spawn array per stage: the waves' spawns, then the boss's minions.

Rules that stay in the code (main.c): the pool leaves out the players' fighters as the stage starts; the boss never
wears P1's colour set; difficulty scales life; the attract demo plays the first stage's waves on background STAGE
(make STAGE=n) with no boss, its last wave again and again, lock points clamped to that background; beaten waves'
enemies blink out; STAGE CLEAR, the save, BOSS UNLOCKED, the fade.

Today's content (written out from the 0.0.34 formulas): stage s (0-4) wave w (0-4) has min(2 + s + w, 6) spawns, spawn k:
pick 3w + k + s, set w + k, wave 0 at x 200 + 30k, later waves walking in (odd k from the left, rank k / 2), z 6 + 11k,
seed $1D2B + w + 8s; lock points w x (width - 320) / 5 (448 px on the 2560 px stages, 256 on the last); the boss at
the stage end with min(2 + s, 5) minions (pick 3k + s, not the boss, set k + s, tint 1 + (k + s) mod 3, z 6 + 13k),
seed $5B05 + s; life 100 + 4s, power stage + 1.

## Live install: data packs (the Brawler Lab's write path)

The page (lab.js `installPack`, from `build_tables.py pack GAME.json BUILD OUT` today; the Enemies / Stages tabs later)
writes a pack into `lab.pack` (lab_t, after `buf`: `pack_stat` at 3232, `pack` at 3234, at most 4096 bytes) and sets
`lab.load = 3` (with `lab.magic` = LAB1). The game:

1. on its next tick checks the pack (`gd_check`: magic `GD`, version `GD_VERSION` 1, size, nstages = GS_COUNT, every
   table inside the pack and word-aligned, each enemy's base / pool / AI rows / tint / name (1-10 characters, ended
   inside) / palette / route tree (magic, version, node links and moves, speeds), each stage's background, waves (1-6
   spawns), spawns' enemies and tints, boss, minions); `pack_stat` = 1 pending, or 0x80 | the failed check;
2. at the next safe point (a wave's spawn, the boss's, a stage start, the enemy test's respawn) checks it again, copies
   it into its own RAM (`gd_live`), turns the offsets into pointers and points `gstages`, `genemies`, `ai_tab` at it
   (`pack_stat` = 2). Every enemy slot gets its AI row again at that point, so nothing holds the old tables;
3. `lab.load = 4`: back to the ROM's tables at the next safe point (`pack_stat` = 3). A bad pack sent while another
   one is pending cancels it.

`gdpack_t` (18 bytes, big-endian): `GD`, version, nstages, nenemies, nai, size (u16), offsets of the stages, enemies and
AI rows (u16), nspawns (u16: every stage's spawn array holds that many, the last padded), pad. The tables are the ROM's
structs with each pointer an offset from the pack's start (0 = none); then pools, names, palettes, trees, spawns and
waves. Today's game.json packs into 2874 bytes. A stage edit takes effect at the next safe point too: `gs` is re-read and
the wave index clamped to the new stage's waves.

**Enemy test** (`lab.req = 3`, `lab.fighter` = P1's fighter, `lab.dummy` = an enemy index, EN_* order): P1 against that
definition at the dummy's place, its own AI on (seed $1D2B), P1's life refilled, the enemy back 60 frames after it is
beaten (a safe point); `lab.req = 2` re-places both; `lab.active` = 2. `tools/brawler/enemy_test.py` uses it.

## Planned, schema only

**Triggers** (a stage's `triggers[]`, read by a small interpreter in the campaign tick):

| field | values |
|---|---|
| `when` | `{"camera_x": 900}`, `{"wave_clear": 2}`, `{"time": 600}` (frames since the stage start), `{"boss_life": 50}` (percent) |
| `do` | `{"spawn": [spawns]}`, `{"lock": 1200}`, `{"music": "BOSS_GEESE"}`, `{"drama": "geese_intro"}` |
| `once` | true (default) |

Binary: `gtrigger_t` {kind, arg16, action, arg} 6 bytes + a spawn index for spawn actions; the stage gets `triggers*`,
`ntriggers`; fired flags in RAM (a bit per trigger).

**Drama mode** (a boss's short speech): `dramas` at the top level, named, referenced by a trigger or by `boss.drama`:
`{"name": "geese_intro", "bars": true, "lines": [{"who": "geese", "side": "right", "text": "..."}, ...]}`. On screen:
the fight frozen, black bars top and bottom (fix layer rows), the speaker's big portrait (the HUD portrait scaled, or a
new 64x64 fix / sprite portrait from the bank), one text line at a time on the fix layer, A to advance. Binary: lines
as {portrait, side, string offset}, strings in one blob.

## Voices: where KOF triggers them (measured in our emulator, 2026-10-05)

Measured with `emu/neogeo_sdl --capture` (tools/kof96/capture/emu.py, the 'vs' states), SNDLOG (each byte the 68000
writes to REG_SOUND, with the stack) and QLOG (KOF98's sound ring $10D940), plus the P ROMs read with tools/kof96/rom96.py.

1. **The animation stream carries them.** KOF96, KOF98 and KOF99 animations are 6-byte records; a record whose first
   byte is a command (>= $80) is not a step. Known before: $FF loop, $FE hold, $FD box, $FB move. **$FC = play a
   sound**: `FC 00 ii ii 00 00`, ii ii = a sound index. Measured: KOF98 Kyo's 236A (Yami Barai) queued $1D $BD at frame
   39 from code at $5CC8 with the record `FC 00 02 C5 00 00` at $21642C on the stack; the swing $1A $7E at frame 47
   from `FC 00 05 1F` at $2164AA; the second voice $1D $BE from `FC 00 02 C7` at $216530.
2. **The index goes through a per-game table to the driver's command.** KOF98: mapper $7A98, word table $A9BCE
   (prefix << 8 | code): $2C5 -> $1D $BD. KOF96: mapper $6AA8, table $6CAD4 ($2C5 -> $1E $79, measured in a KOF96 capture
   of the same move); KOF99: mapper $6352, table $B1B5C. The indices are shared across games for the same fighter (Kyo
   $2C5-$2D6 in KOF96 and KOF98), the codes are each driver's own. An entry point just before the mapper adds 0-2 to
   the index by the object's screen x (left / middle / right thirds): stereo variants of an effect.
3. **Prefixes** come from the table with the code: KOF98 hits and swings $1A + code, Kyo's voices $1D + code, his
   intro / win lines $17 + code (the earlier MAME tap, sound.h, saw voices as $1C + code: which fighters use which
   voice slot is for the listing step); KOF96 voices $1E + code.
   (docs/kof98_sound_driver.md: each prefix is an effect slot, so a voice never cuts a hit.)
4. **Some specials call it from code.** KOF99 K''s 236A voice ($1D $86, index $A71) is not in an animation: the
   special's start code does `move.w #$A71,d0; jsr $6352` ($38F2E), and stores three more voice indices ($A71-$A73) at
   object +$1BC-$1C0 with a count at +$1BA (alternative lines per hit or per press). So per-move voices are found by
   (a) scanning a fighter's animations for $FC records (static: KOF98 Kyo has 60 of them in 24 indices, KOF96 Kyo 33,
   KOF99 fighter 0 19) and (b) capturing each special with SNDLOG (the specials capture already plays every special).

For the lab: a later step lists each roster fighter's voices (index, prefix, code, the moves whose animation or special
plays it), adds a roster `voices` field (`{"move or special": code}`, null = silent) with the bank's own as the
suggestion, and the export emits a per-move sound byte (a `bstep_t` flag or a parallel table) that fighter.c sends
with `snd_cmd` as the step starts. The brawler's driver is KOF98's: KOF98 fighters' voice codes play as they are once
songs.json lists them (the V ROM carries only listed samples); KOF96 / KOF99 voices need their samples ported into
KOF98's V ROM layout (tools/port/build_snd.py) and new codes.

## Proof that step 1 changed nothing (2026-10-05, our emulator)

- Fighter export byte-identical to 0.0.34: bm_chars.c / .h, C1 / C2, chainlab.json, hud.h (the roster's specials,
  watch poses and routes now come from game.json).
- Minion tints: the table formula equals the old switch for all 32768 colours x 3 tints.
- regress.py: bleed frame-exact (normal and AI_OFF builds); facing matrix (AI_OFF) 208 / 208 traces identical to 0.0.34.
- campaign29.py (5 stages, bosses, unlocks, ending, save, power cycle): log identical to 0.0.34's but for one count
  (stage 4 boss: 11 specials started in its 900-frame window, 10 in 0.0.34's: a lag frame one frame apart, below).
- Chain Lab: proof.sh (desktop core vs the browser's wasm core, own tree and an edited 1.5x tree) identical;
  speed_proof.py timing and hits identical to 0.0.34; its throw trace differs in single mid-tick samples (4 of 54
  frames), as two runs of the same new ROM do.
- RAM traces (tools/brawler/ramtrace.py): attract demo 8100 frames identical to 0.0.34 except the first frame of each
  demo fight (the harness samples mid-tick; the new stage start reaches the spawns sooner: the 448-step divide loop is
  gone); campaign replay (19983 frames, the same inputs and test pokes): every wave and boss phase of the five stages
  identical up to the frame the test poke kills the boss. The build's timing is not cycle-identical (0.5 % more AI
  time in boss fights, cheaper fades), so a lag frame can land one frame apart; a poke made between frames then hits
  another game tick. Counted lag frames in the fights: 575 in both.

## Proof that step 2 changed nothing (2026-10-05, our emulator)

Baseline: 1432bb3 built with the same SDK crt0 (only the tick counter added: `addql #1, game_ticks` before each tick).

- regress.py: bleed frame-exact (normal and AI_OFF builds); facing matrix (AI_OFF) 208 / 208 traces identical.
- campaign29.py: log and campaign.json identical to 1432bb3's (5 stages, bosses, unlocks, ending, save, power cycle).
- ramtrace.py tick-keyed: attract 7707 common ticks, campaign replay (1432bb3's inputs and pokes by tick) all 19033
  ticks identical, every wave and boss fight included; the same with today's game.json sent as a data pack at tick 100
  (installed at the attract demo's stage start): attract and campaign identical too.
- Chain Lab training (labdrive.py): every state and lab event identical; `lab.frame` counts one less (the start tick is
  a lag frame in this build).
- The three examples in the enemy test (enemy_test.py, /data/tmp/enemies/out): names in the HUD, YAKUZA's dark suit
  grabbing, VIPER's ash Mai jabbing (12 strings in 600 frames), SNIPER's set-2 Ryo firing Ko-ou-ken from range.
- Write path: YAKUZA's life 60 -> 90 in an edited game.json, packed (2874 bytes), sent while YAKUZA fights: pending,
  its life still 60; beaten, it comes back with 90 (installed); a version-9 pack refused (check 2), a name offset past
  the end refused (check 9); load 4: back to the ROM, the next YAKUZA has 60.
