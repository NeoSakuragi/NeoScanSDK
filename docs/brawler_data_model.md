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
| 0, the bank | KOF94 / 96 / 98 / 99, Samurai Shodown IV (tools/samsho4), World Heroes Perfect (tools/whp) and Kizuna Encounter (tools/kizuna) fighters as extracted: animations, frames, hit boxes, timing, palettes, captured specials and throws, sound commands per move | /data/neogeo_dict (dictionaries), tools/kof96 (export96), never edited | nobody: templates |
| 1, roster | the playable characters: which bank fighter, select pose, specials mapping, chain routes, unlock, throws (`throws`: per throw `speed` 8.8, `front` [first, end) rows the victim is drawn in front, `hold` {hit, fin: the hold hits' moves (default: hit = the fastest-startup close normal, fin = close D; TODO #166), dx: px in front}; TODO #146); the select screen | game.json `roster`, `select` | Brawler Lab: Characters tab (+ the Chain Lab for the routes) |
| 2, enemies | named enemies on a bank fighter (or a pool of them), life, power, AI preset; the AI presets; the minion tints | game.json `enemies`, `ai`, `tints` | Brawler Lab: Enemies tab |
| 3, stages | background, music, waves (lock points + spawns), the boss with its minions, song and scene, triggers; dramas and big portraits | game.json `stages`, `dramas`, `portraits` | Brawler Lab: Stages / Waves tab |

## Build flow

```
game.json --build_tables.py roster--> build/roster.json --export_bm.py--> build/bm_chars.c/.h, bm_c1/c2.bin, chainlab.json
          --build_tables.py chars---> the Makefile's CHARS (bank specs, bm_chars order: make_hud.py portraits)
          --build_tables.py tables--> build/game_tables.c/.h (types: examples/brawler/gamedata.h)
```

- `build/roster.json` is rewritten only when the roster's export inputs change (bank, watch, specials, routes), so a wave
  or AI edit rebuilds the small tables (seconds), not the fighters (80 s).
- The generator checks names (fighters, enemies, presets, tints, songs: a wrong song name fails the compile, `MUS_*`),
  counts (6 enemies at once, 5 minions with a boss, 19 select slots, every roster fighter in one slot), lock points
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
| AI rows | `ai_preset_t ai_presets[AI_COUNT]` via `ai_tab` | 42 bytes each | RAM (copied at boot) | yes: write the bytes (next decision), or a data pack (next spawn) |
| enemies | `genemy_t genemies_rom[]` via `genemies` | 26 bytes each | ROM, pointer in RAM | yes, a data pack; read at each spawn |
| stages, waves, spawns | `gstage_t`, `gwave_t`, `gspawn_t` via `gstages` | 24 / 6 / 8 bytes | ROM, pointer in RAM | yes, a data pack; `gs` re-read at the safe point, its waves and spawns as they come |
| tints | `gtint_t gtints[]` | 6 bytes each | ROM | not yet (a pointer when the lab needs it) |
| select slots | `sel_slot_t SEL_SLOT[]`, `sel_fighter[]` | 4 + 1 bytes each | ROM; `slot_ch[]` RAM copy made on each select screen | `slot_ch` yes (RAM) |
| unlocks | `roster_unlock[BC_COUNT]` | 1 byte each | ROM | no (save bits follow the stage order) |
| chain routes | `rt_head_t` + `rnode_t[]` (fighter.h) | 16 + 24 bytes a node (tree version 3; a version 2 tree, 22-byte nodes, still read) | ROM, `route_tab[]` in RAM | yes: the Chain Lab (lab.buf, `lab.load`) |
| specials by role | `bchar_t.spmap` (4 bytes: an index in the fighter's `specials`, 0xFF none) via `spec_tab[]` | 4 bytes a fighter | ROM, `spec_tab[]` in RAM | yes: a data pack's roster section (version 2) |
| fighters | `bchar_t bm_chars[]` + everything it points at | ~35 KB each | ROM ($200000) + C ROM | no: new content = a ROM build |

## Layer 0: the bank

One entry per fighter, read by `export_bm.py` from the game's dictionary (`tools/kof96/export96.py`, any of KOF96,
KOF98, KOF99; `tools/kof94/export94.py`; `tools/samsho4/export_ss4.py` for Samurai Shodown IV, `tools/whp/export_whp.py` for World Heroes Perfect, `tools/kizuna/export_kz.py` for Kizuna Encounter (pre-scaled to its in-play zoom $CC), `tools/doubledr/export_dd.py` for Double Dragon 1995 (Billy Lee + his transformed form, full size; specials as programs with variant tables), the same layout): every animation (6-byte step records: ticks, frame, flags, then commands), the frames (sprite parts and
tiles), hit / hurt boxes, palettes (every colour set), physics, captured specials (scripts of rows) and throws
(thrower and victim timelines), victim postures. The bank is addressed by a spec `game:name` (`kof98:terry`). It is
never edited: layer 1 picks from it.

Voices are in the bank too: `tools/brawler/voices.json` (tools/brawler/voices.py, "Voices" below): per fighter every
voice sample its KOF plays, with the moves that play it.

## Layer 1: roster and select screen

`roster` is a list; its order is the order of `bm_chars[]` (BC_* in bm_chars.h) and of the HUD portraits.

| field | example | meaning |
|---|---|---|
| `name` | `"terry"` | unique; the export name (upper case on screen) |
| `bank` | `"kof98:terry"` | the layer-0 fighter |
| `watch` | `{"frame": 351, "step": -1}` | the select screen's pose: KOF state and step (-1 = its last, held) |
| `routes` | `"tools/brawler/routes/terry.json"` or `"default"` | its chain route tree (routes.py format; default = the pre-Chain-Lab table) |
| `specials` | `{"D": "EX 236C", "fD": "214C", "dD": "623C", "uD": "214D", "dfD": "236C", "ufD": "623D"}` | the KOF input played by the six special slots (TODO #71; button C since 2026-10-06; the keys keep the old D names): neutral, forward, down, up, down-forward, up-forward + C (diagonals relative to the facing; down-back = down); null = none (an empty slot plays what the input played before the six slots: down-forward+D = down+D's, up-forward+D = up+D's, then their own fallbacks, fighter.c `special_pick`); any special of the fighter's pool (`export_bm.special_pool`: ground specials of the normal condition), all of which are in the ROM, so a change is live (a data pack). `export_bm.suggest_specials` is the automatic pick that filled these |
| `fury` | `"21416C"` (absent = none) | TODO #71: the fury, button D since 2026-10-06 (down+D: its MAX version `MAX <fury>` when the bank has one, TODO #139; every fury plays the super flash, `super_flash` below) (needs half the meter, costs half; fully invincible from the trigger to its end): the fighter's main desperation move, any special of its bank (KOF DM / SDM, an SS4 rage move: conditions other than normal too); appended to its pool when not in it, `bchar_t.fury` = its index (0xFF none), played as role `BS_FURY`. Picks (2026-10-05): Terry 21416C Power Geyser, Ryo 23624C Ryuko Ranbu, Ralf 23624C (15 hits), Robert 23624C Ryuko Ranbu, Yamazaki 236236C Guillotine, Billy 236236C Chou Kaen Senpuukon, Kyo 21426C Orochinagi, Iori 23624C Ya Otome, Mai 21426D Chou Hissatsu Shinobi Bachi, Yashiro 21426C Final Impact, Geese 1632143C Raging Storm, Mr. Big 23623C (his only DM), Krauser 641236C (his only DM), K' 23624C Heat Drive, Rugal 23624C Gigantic Pressure, Goenitz 2141236C (his DM; the SDM 6321463214C left), Haohmaru BUST 236D (SS4 rage move), Hanzo HERO 623AB (World Heroes Perfect's 623 + A+B with the hero gauge full, the "Super Shoryuha"; MAX = MAX HERO 623AB, the hero desperation move 65426AC), Kim 6246A (Kizuna Encounter's Phoenix desperation move, life <= 96 there) |
| `hit_sfx` | `{"A": "SLASH", "623B": "SLASH", "throw_c": "BACK BREAK"}` (absent = KOF's own) | TODO #75: hit sounds by use, songs.json sfx names. Keys: a normal's button (`A` `B` `C` `D` `CD`: fighter.c `hit_sound`, `bchar_t.sfx`), a throw's impacts (`throw_c` / `throw_d`), a special's KOF input (export_bm `move_fx`: the KOF98 hit kind playing that code, burn kept). Rules without data: a fury's hits play $9C SDM IMPACT; a grab or a command grab's catch $19 GRAB START. Set: Haohmaru A/B/C/CD + 421C + 623B `SLASH` ($2B; D is his kick), Krauser `throw_c` `BACK BREAK` ($3D). No guard exists in the brawler, so $17 BLOCKED HIT has no event. Proof: /data/tmp/sfx75/sfx75_proof.py |
| `unlock` | `"always"` or `{"boss_of_stage": 1}` | locked on the select screen until that stage's boss is beaten (save bit stage - 1) |
| `voices` | absent, `"kof"` or `{"kof": true, "set": {"hit": 3, "special:236C": null}}` | absent = silent (none of its samples in the V ROM); `"kof"` = KOF's own voice on every move (the suggestion); an object = that base (`kof` false: none) with these keys changed to a voice id of its list (null: silent). Keys: every BA_* move name, `throw_c` / `throw_d`, `hit`, `ko`, `select`, `special:<input>` of its pool ("Voices" below) |
| `display` | `"BILLY LEE"` | the name shown (HUD, select) when it differs from `name` upper-cased (at most 10 characters) |
| `scale` | `1` | the fighter's size: 1 = its game's art at full size (Double Dragon's Billy Lee, 115 px, Bruno 2026-10-06; Kizuna's fighters are exported at 0.80 by their exporter); a per-fighter value so it can change later (export_dd accepts 1 today) |
| `variant` | `{"623": "A"}` (absent = the source's default, the heaviest) | the row of a special's variant table played (vocabulary `variant.table`: DD's four buttons), latched at the move's start |
| `form` | `{"trigger": "down+D full meter", "transition": "FORM", "target": "billy_super", "carry": ["life", "position", "facing", "meter"], "exit": "life"}` | the form link (vocabulary `form.change`): the trigger starts the transition (a special of its bank), which turns the fighter into the target roster entry; exit `life` (a lost life) or `stage` |
| `selectable` | `false` (absent = true) | no select slot: a form link's target (Super Billy); never picked (roster_unlock 0xFF) |

Later: `palettes` (custom colour sets), `moves` (a trimmed list).

`select.slots`: `{"x": 40, "z": 48, "row": 0, "fighter": "terry"}` per slot; row 0 front, 2 back (`SEL_BACK`, the
bosses). Generated as `SEL_SLOT[]` (x int16, z, row: 4 bytes) and `sel_fighter[]` (bm_chars index, 0xFF empty).

ROM side of a fighter (`bchar_t`, export_bm.py): name, palettes, frames, animations (`banim_t` / `bstep_t`), physics,
throws, victim poses, specials (`bspec_t`, rows of a script: its whole pool, `nspec` of them, in build/bm_spec.c, compiled
as plain read-only data into the first program MB: 190 specials, ~500 KB), tile page, command normals, its route blob,
its index, `spmap` (the special each role plays, game.json's `specials`). The game reads a role through `spec_tab[]`
(RAM, fighter.c `spec_ix`); a special keeps the index it started with (`fighter_t.spec_ix`); the down+D role alone gets
the special's invincible rows (`bspec_t.inv_rows`, the rising reversal's rule, computed for every special).
The fury (role `BS_FURY`, every fighter's and every boss's alike) is untouchable once it connects (Bruno 2026-10-05:
"keep the player invincible as soon as the fury connects and starts its script"): its first hit (its body, a script
object or a projectile of its own; a running grab's catch; Kim's Phoenix: the rush's hit that starts the scripted part
1) sets `fighter_t.inv = INV_FURY` (fighter.c `fury_lock`), held while it plays and cleared when it ends
(`special_end`): nothing hits it (enemies, the crowd, projectiles, other players) and no body pushes it (a special's
push, a low leap's stop). Before the connect (the whiff, the rush) the normal rules. Proof: `tools/brawler/fury_inv_proof.py`.

**Follow-ups of ROM specials** (TODO #74, #140): a special read from the ROM continues on the inputs its handler
checks (handlers98 `FOLLOW_CHECKS`), each mapped to one brawler press made while the special plays (`bslink_t`,
export_bm `link_c`; the program decides when it counts: `P_CHECK` on the frames KOF's handler reads, `PC_LINK`):

| fighter, slot (KOF input) | KOF follow-up | brawler press |
|---|---|---|
| Iori ufD (214A Aoi Hana) | 214 + A / C, twice (parts 2, 3) | `again` = up-forward + C, twice |
| Iori uD (623D Kototsuki In) | on hit / block only: 214 + A / C during the kick's hit-stop -> Aoi Hana (A) at the landing, then its two parts | `again` = up + C in the hit-stop, then twice more |
| Kyo fD (236C Dokugami) | 63214 + A / C -> Tsumi Yomi; then 6 + A / C -> Batsu Yomi | `again` = forward + C; then `fA` = forward + A |
| K' D (236C Ein Trigger) | 6 + B -> state 134; 6 + D -> state 135 | `fA` = forward + A; `fAB` = forward + C (the token keeps the old name) |
| K' dD (623C Crow Bites) | 6 + B or D during the rise -> 146 / 147 (the same part) | `fA` or `fAB` |

`again` = the slot's own input (C + its direction). Every other slot special of the three (and their furies) has no follow-up in the
ROM (brute force in our emulator, whiff / hit / block). Proof: `tools/brawler/followups_proof.py` (game vs model,
brawler vs model, both facings), `romspecials_check.py` with `+LINK@T` cases.

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
+ full_speed + jump_in (jump-in from 40-120 px, chance 32, back-hop under 40 px, chance 4), short rests, follow-ups 3, attack_dx 30, viper.json: jabs at 1.25x and a tripping sweep, ash tint on set 1,
30 life), SNIPER (ryo, minion with only `projectile`, attack_dx 110, hover_dx 140, spec range 60-220, proj_chance 32,
jabs, colour set 2, 45 life).

`meter` (TODO #71, `gmeter_t`, ROM only): the special meter, players only: `max` 120 (full at the start and at a new
life), `special` 30 (a C special), `fury` 60 and `fury_min` 60 (D: half the gauge, only from half full), `refill` 10
(frames per point: empty to full in 20 s), `hit_mul` 2 (a special out of a hit, in hitstun or held, costs twice as much),
`flash` 8 (frames the fighter's palettes are fully white when it did). Not enough meter: the press does nothing.
`infinite` 1 (Bruno 2026-10-06, for the time being): no press spends anything and the gauge stays full (the HUD bar
full); the white flash of a special out of a hit still plays. 0 = the costs above.

`super_flash` (TODO #139, `gflash_t`, ROM only): fx.super_flash, the engine's rule for every fury (D) and MAX fury
(down+D): `start` 1 (the fury's frame it starts on), `freeze` 28 (frames the game freezes except the attacker and the stage
is hidden), `white` 4 (of them, frames the backdrop is `white_colour`, then `dark_colour`), `anchor` [0, -96] (px from the
feet, KOF orientation: where the concentration plays when the move has no anchor of its own). KOF98's values
(tools/kof96/handlers98.md "Super flash"). Blue for a fury, orange for a MAX fury (by role).

`ai.tokens` (1): attack tokens dealt every 16 frames to the closest able enemies. `ai.presets` (today minion,
minion_attract, boss), all fields bytes, `ai_preset_t` (42 bytes) in this order (build_tables.py AI_ORDER; game_tables.c
asserts every offset), then one row per enemy with `ai_over`:

| field | minion | boss | meaning |
|---|---|---|---|
| `flags` | grab, projectile | token, grab, projectile, boss_moves | token: always holds one; grab: approaches may grab; projectile: fires its C special at mid range; reversal (rev_*), specials (bspec_*): the boss block; jump_in (jump_*, hop_*): any enemy (TODO #58); `boss_moves` = reversal + specials + jump_in; full_speed: walks at full speed while positioning (the others at half); air_cd: the jump-in's air attack is C+D (up+A in the air; else air B, down+A) |
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
| `jump_min`, `jump_max`, `jump_dz`, `jump_chance`, `rest_jump`, `air_b_dx` | - | 24, 140, 8, 64, 140, 56 | jump-in, any enemy with `jump_in`: the token holder (or a `token` enemy) after its rest, from jump_min to jump_max on the depth line +- jump_dz, jump_chance of 256 a frame: a full forward jump, its air attack (down+A = air B, or up+A = air C+D with `air_cd`) on the way down this close |
| `hop_dx`, `hop_chance` | - | - | with `jump_in`: the token holder resting closer than hop_dx hops back (hop_chance of 256 a frame, 0 = never), out to the jump-in range |
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

`gdpack_t` (20 bytes since version 4, 18 before, big-endian): `GD`, version, nstages, nenemies, nai, size (u16), offsets of the stages, enemies and
AI rows (u16), nspawns (u16: every stage's spawn array holds that many, the last padded), roster (u16, version 2: the
offset of the roster section, 0 = none; version 1: padding). Version 2 (2026-10-05, the Characters tab) adds the roster
section after the stages: per roster fighter (bm_chars order) 4 bytes, the special each role plays as an index in its
pool (0xFF = none), checked against `bchar_t.nspec` (check 16) and installed into `spec_tab[]`; a version 1 pack is still
read and puts the ROM's specials back. `lab.load = 4` does too. The tables are the ROM's
structs with each pointer an offset from the pack's start (0 = none); then pools, names, palettes, trees, spawns and
waves. Today's game.json packs into 2938 bytes (version 2). A stage edit takes effect at the next safe point too: `gs` is re-read and
the wave index clamped to the new stage's waves.

**Enemy test** (`lab.req = 3`, `lab.fighter` = P1's fighter, `lab.dummy` = an enemy index, EN_* order): P1 against that
definition at the dummy's place, its own AI on (seed $1D2B), P1's life refilled, the enemy back 60 frames after it is
beaten (a safe point); `lab.req = 2` re-places both; `lab.active` = 2. `tools/brawler/enemy_test.py` uses it.

**Stages tab** (TODO 52, 2026-10-05; the triggers list and the boss scene: TODO 56 below; tools/brawler/chainlab: stages.js UI, stagepack.js the pack): the five stages
(background picker with the ROM's six Robo Army streets, the 121 other extracted backgrounds listed as "needs a build";
music and boss song played by the game in the page, `lab.req = 5`, `lab.dummy` = the MUS_* command; boss, minions),
the wave designer (the stage strip with its lock points dragged in 8 px steps, entries marked: ▶ walks in, ■ placed,
● the boss; per wave the spawns: enemy with its face, side, delay = walk-in rank (36 px further out each), z, set, pick,
tint; add N at once; the 6-enemy limit), a timeline (per wave who enters first and who a delay step later), the
build_tables.py checks in the page, export of one stage / all stages in game.json's layout, import. Play from here:
the pack (`build_tables.py labstages` writes pack_base's bytes into the site's stages.json, the page appends the stages
exactly as `pack_stages`) and `lab.req = 4` (`lab.fighter` = P1, `lab.dummy` = the stage, `lab.wave` = the first wave,
past the last = the boss) in the same tick: stage_begin installs the pack, then the camera jumps to that wave's lock
point and spawns it. Time-based spawns wait for the triggers below.

Proof (chainlab/stage_proof.sh, 2026-10-05): stage 1 wave 2 edited in the page to 3 YAKUZA from the right; the same
pack played in the page (headless Chrome, its wasm core), in Node (core.wasm) and on the desktop core (ramtrace.py
stage): 1494 ticks identical from the stage start. Unedited: the page's pack = build_tables.py pack byte for byte
(2874 bytes), and played by tick (--replay) identical to the ROM's own tables from wave 2 and from the boss. The release
path is unchanged: attract 7707 ticks and the campaign replay 19031 ticks identical to HEAD's build.

**Enemies tab** (TODO 53, 2026-10-05; tools/brawler/chainlab: enemies.js UI, enemypack.js the pack's enemy half):
the enemy list (add, duplicate, delete), per enemy its name (validated: 1-10 of A-Z 0-9 _, a letter first, unique; the
HUD shows it or the fighter's name), base fighter (a picker of the roster's select poses, or a pool with its fighters
ticked), life, power; colours: colour set, tint (its formula with the numbers), custom 16 colours for palette 0 (a swatch
grid; per colour R / G / B 0-31, the dark bit, a colour picker quantised to 5 bits, the word shown) with the select pose,
idle and close C drawn in the page from index sprites (make_site.py: move_images.enemy_images, every colour set's
palettes) recoloured exactly as fighter_load_pals does (set, custom palette 0, tint on colours 1-15); the AI: preset and
attract preset, every preset field grouped (aggression and rests, range and depth, grab, projectile, strings, the boss
block's reaction / specials / jump-in) with the preset's value beside the override, "● override" marking an overridden
row, a reset per row and for all; moves: own tree, jabs, no_specials or a routes file, the route list shown, "Edit in the
Chain Lab" puts the enemy's tree in the Chain Lab's editor on its fighter and "Use this tree" keeps it as
tools/brawler/routes/enemies/<name>.json (carried by the export). Test it: the pack (this tab's enemies + the Stages
tab's stages; the Stages tab packs with this tab's enemies too) and `lab.req = 3` in the same tick (lab_start installs
it). Export one enemy / all (game.json layout, with the routes files they use), import. Data: `build_tables.py
labenemies` (enemies.json); palette RAM is read in the page through web_core.c `wc_palram` (Geolith's memory id 104).

Proof (chainlab/enemy_proof.sh, 2026-10-05): YAKUZA edited in the page (life 90, grab_plan 8, custom colour 3 red to 31:
$2D74 -> $6F74); the page's enemies merged into game.json and packed by build_tables.py = the page's pack byte for byte
(2874 bytes); tested in the page (headless Chrome, its wasm core) and on the desktop core (ramtrace.py enemy) with that
pack: 1494 ticks identical; the enemy's palette RAM (slots 32-39) identical between the two cores and equal to the page's
swatches; unedited: the page's pack = build_tables.py pack. stage_proof.sh still passes with the tab in the page.

**Characters tab** (TODO 54, 2026-10-05; tools/brawler/chainlab: characters.js, char_images.py the pictures): the roster
in select-screen order (the slot table), per fighter its bank, unlock rule (an edit: "needs a build", the ROM table
`roster_unlock`), the select pose in every colour set; the select pose picker: every candidate frame (first and last of
each intro / win pose / walk-in state: KOF98 / KOF99 336-354, KOF96 202-239, exported by export96 exactly as the game's
own `watch` pose, rendered in colour set 0 at build time), tap-to-pick tiles, the current one with a 6 px border and
CURRENT, the ROM's with a dashed border and IN THE ROM; a change needs a build (exported); the specials: the six roles,
each with its pictures (where it hits, first and last, or throws, + the projectile), frame / hit data (`export_bm.
special_info`: frames, first hit frame, hits and damage, projectile, travel, follow-up), the ROM's pick and
`suggest_specials`' pick ("use it"), "Change…" opens every special of the pool and "none"; "Test on the dummy" sends the
pack (Stages + Enemies tabs' data + this tab's roster section) and `lab.req = 1` (the Chain Lab training) in one tick;
"Open in the Chain Lab" puts the fighter in the Chain Lab tab; export one fighter / the roster in game.json's layout,
import (bank and specials checked against this ROM). Data: chars.json (make_site.py).

Proof (chainlab/char_proof.sh, 2026-10-05): Terry's up+D set in the page from 214D to 426D; the same pack played in the
page (headless Chrome, its wasm core, lab req 1 against Ryo, ramtrace.CHAR_SCRIPT: up+D, D, forward+D, down+D, up+D) and
on the desktop core (ramtrace.py lab): 536 ticks identical, 506 of them differ from the ROM's mapping; the page's roster
merged into game.json and packed by build_tables.py = the page's pack, unedited = build_tables.py pack (2938 bytes). Pose
tiles: each fighter's CURRENT tile = the ROM's watch frame pixel for pixel (16 / 16), in-game select screen beside Terry,
Yamazaki and Krauser (/data/tmp/charstab/out). A version 1 pack is still read (installed, the ROM's specials: 535 ticks
identical on HEAD's build and this one). The release path: attract 7707 ticks and the campaign replay 19031 ticks
identical to HEAD's build (only tick 0 differs: power-on RAM before init), regress.py no-bleed true, campaign29 through.

## Triggers and drama mode (TODO 56, 2026-10-05)

**Triggers** (a stage's `triggers[]`; build_tables.py `trigger()`, stagepack.js the same; main.c `triggers()` in the
campaign tick, never in the attract demo; each fires once a stage, at most 32):

| field | values |
|---|---|
| `when` | `{"camera_x": 900}` (the camera reached x), `{"wave_clear": 2}` (wave index 2 beaten; `"boss"` = the boss), `{"time": 600}` (ticks since the stage start) or `{"time": 120, "wave": 0}` (ticks since wave index 0 came; `"boss"` = since the boss came) |
| `do` | `{"spawn": {"enemy": "MINION", "side": "right", "count": 2, "delay": 60, "z": 20, "pick": 0, "set": 0, "tint": "warm", "not_boss": true}}` (count enemies, one every `delay` ticks: pick + k, z + 11 k; they wait in a queue for a free enemy slot and count as enemies left), `{"lock": 1200}` (the camera stops there, never left of itself nor past the lock already in force, until every enemy on screen and queued is beaten; GO also waits for it), `{"music": "BOSS_GEESE"}`, `{"drama": "geese_intro"}`, `"end_stage"` (every enemy goes down, STAGE CLEAR) |
| `note` | free text |

Waves are counted from 0 in the data (wave 1 on screen = index 0). The real time-delayed spawns replace nothing: a wave's
walk-in "delay" is still the rank (36 px further out). Binary: `gtrigger_t` 18 bytes {when, wave (0xFF = the stage
start), at (s16), action, n, arg (u16: x, MUS_* command, drama index), delay (u16), gspawn_t sp}; per stage a
`gstagex_t` 8 bytes {triggers*, ntrig, drama (the boss's, 0xFF none), pad} beside `gstage_t` (unchanged, so older packs
keep their layout); live pointer `gstagex`. RAM: `trig_fired` (a bit per trigger), `stage_tk`, `wave_t`, `wave_on`,
`waves_cleared`, `trig_held`, the spawn queue `tq` (6).

Pack version 4: the header grows to 20 bytes with `stagex` (u16 offset of gstagex_t[nstages]); after the roster
section each stage's triggers, then the gstagex_t rows (triggers as offsets). `gd_check` 18: the stagex table / a boss
scene past DR_COUNT; 19: a trigger (kinds, actions, spawn count 1-6, enemy, tint, drama). A pack before version 4
(18-byte header) is still read: no triggers, the ROM's boss scenes.

Pack version 5 (TODO #58): AI rows grow to 42 bytes (`hop_dx`, `hop_chance`); `gd_check` 2 refuses any pack before 5
(its AI rows are 40 bytes). The lab builds its pack from game.json each time, so no stored pack is lost.

Pack version 7 (TODO #71, one attack button): route trees version 4 (`TREE_VERSION`; links A, B = jump-cancel, ↓A,
close A, →A, ←A, ↘A, slots 7-8 unused, then the six C specials, data keys AB .. ufAB); only version 7 loads (older packs' trees read the old
buttons: refused, check 2; the version 5 compatibility path is gone). Before (history):

Pack version 6 (2026-10-05, six special slots): the roster section holds 6 bytes per fighter (D, forward+D, down+D, up+D,
down-forward+D, up-forward+D; `GD_ROLES`), the voice offsets follow at roster + BC_COUNT * 6; route trees are version 3
(24-byte nodes: `next[]` + RI_DFD, RI_UFD, the diagonal D route enders: the ↘D / ↗D link, else ↓D's / ↑D's, else D's).
A version 5 pack still loads: its 4 roles copied to RAM (`gd_spec`) with the ROM's two diagonals, its version 2 trees
read at their own stride (`RT_NODE`, `RT_NEXT` = 0 for the diagonal links). The lab mailbox moves with the nodes:
`lab.buf` 3088 bytes, `pack_stat` at 3488, `pack` at 3490 (lab.js LAB). Proof (/data/tmp/sixslots): a v5 pack from the
tools before the change (Terry's up+D = 426D) and a v6 pack (Terry's down-forward+D = 426D) installed on the desktop
core: both installed, each edit played, the other slot the ROM's; Viper's own move list (v2 / v3 tree) plays.

**Specials out of a hold** (2026-10-05): holding a grabbed victim, any of the six D inputs ends the hold and starts the
special at once (fighter.c `hold_update`); the victim is released (never held by a special) into hit stun in its held
pose, which ends with the stun or the special's hit (`react`). forward+A / forward+B (throws) and the A / B hold hits
are unchanged; the AI never presses D in a hold. A fighter without a forward+C throw (Haohmaru) never holds.

**Drama mode** (main.c `drama_*`): `dramas` at the top level, `name: [scenes]`, a scene
`{"speaker": "GEESE", "side": "right", "portrait": "geese", "lines": ["So you made it this far.", "..."], "wait": 120}`
(1-8 scenes, 1-3 lines of at most 34 ASCII characters, speaker 1-16, wait = ticks the scene stays once typed, default
120); a player's reply: speaker `"$P1"` (P1, or P2 when P1 is out) / `"$P2"` (only with both in play, else
skipped), no `portrait` (its own: `pb_of_fighter`, the game.json portrait named like the fighter; none, e.g. K' or
Haohmaru: name plate and text only, a HUD face cannot be scaled up by the hardware), the name plate = the fighter's
name, `"lines_by": {"terry": [...], "*": [...]}` its own lines, else the "*" / `lines` ones; `gsceneby_t` {fighter,
nlines, lines[3]}, gscene_t 28 bytes with `who`, `nby`, `by*`. Proof: Geese's reply with Terry, Kyo, Haohmaru in
/data/tmp/drama/out/p1_*.png (Terry's own line and portrait; Kyo's portrait + the generic line; Haohmaru text only); played by a trigger (`do.drama`) or as a boss walks in (`stages[].boss.drama`: before its song, which starts when
the scene ends). On screen: black bars slide in from the top (fix rows 0-3) and the bottom (rows 20-27), a row every 2
ticks; the fight held (game_tick only draws: no AI, no update, no flow, no HUD; the HUD's rows 4-7 cleared); each
scene's big portrait slides in from its speaker's edge (right as captured, left mirrored), the name plate in yellow on
the bar (row 21, the speaker's side) and the lines typed a character a tick (rows 23-25); A-D / START (either player):
the rest of the text at once, then the next scene; then the bars slide out, the HUD is redrawn whole, the song starts.
Bars and text use `DRAMA_FONT` (make_hud.py: the font on an opaque black cell, S ROM tiles $320-$37F; + ' ' = a black
cell). Binary: `gscene_t` 24 bytes {portrait, side, nlines, wait, speaker*, line*[3]}, `gdrama_t` {n, scenes*} in ROM
(`gdramas[DR_COUNT]`; packs do not carry scenes, only their index).

**Big portraits** (game.json `portraits`: name -> `game:fighter`; tools/brawler/big_portraits.py): `capture` finds each
fighter's win-screen portrait in our emulator (its fight state c<id>, P2's life and the round timer poked so P1 wins
three rounds on time; VRAM + palette RAM every 50 frames; the widest run of tall sprites side by side that stands
still): KOF96 Mr. Big, Krauser, Geese, Goenitz (12-14 columns of 16 tiles, 3-8 palettes), KOF98 Rugal, Terry, Ryo
(16-20 columns of 14 tiles, 8 palettes) -> /data/neogeo_dict/portraits/big_<game>_<name>.json + .png. `build` trims
empty rows / columns, stores identical tiles once after the fighters' tiles (rom_c1/c2.bin = bm_c1/c2.bin + 750 tiles,
93 KB: C ROM 15.56 MB of the 32 MB allowed) and writes build/portraits_big.h (`pbig[]`: columns, rows, palettes, the
map: palette << 24 | flip << 20 | tile). In the game: sprites 300-319 (the box viewer's, hidden meanwhile; dbg_init
gives them back), palettes 240-247, top at y 24 (its first rows under the top bar); the line guard keeps its columns.
The Stages tab edits `triggers` (a list per stage: when / do with their fields, add / remove) and the boss's scene.

Proof (2026-10-05, our emulator only):
- Campaign (/data/tmp/drama/campaign_drama.py = campaign29 + a screenshot of each boss scene, timer-advanced: no
  button): the five boss scenes and Geese's second one (Terry, left) in /data/tmp/drama/out (drama_sheet.png); the
  scenes last 115 ticks after the text is out (260 for Geese's two).
- campaign29.py (unchanged, /data/tmp/drama/out29): through; its log = the previous run's but the boss's AI state counts
  over 900 frames (the scene holds the boss for part of them).
- chainlab/trigger_proof.sh: a trigger added in the page ("Add a trigger": 120 ticks after wave 1, 2 MINION from the
  right, 60 ticks apart): the page's pack = build_tables.py pack of game.json + that trigger (3036 bytes), unedited =
  build_tables.py pack (3018 bytes); played from the stage start in the page, in Node (core.wasm) and on the desktop
  core: 1494 ticks identical; the enemies enter slots 4 and 5 at ticks +120 and +180.
- regress.py bleed True.

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

### The listing, the bank, the game, the lab (TODO #55, 2026-10-05)

**Listing** (`tools/brawler/voices.py`, layer 0 = `tools/brawler/voices.json`, WAVs in /data/neogeo_dict/voices/wav):
- `capture`: every specials pass the bank has (the same tries) re-run in our emulator with WLOG on the mapper's scratch
  word ($10D936 KOF96, $10D93C KOF98, $10D8F0 KOF99): at that store d1 = the index and a4 = the object, so every sound
  is attributed (P1 = $108100) and timed from the special's first frame; plus an events pass (P1 hit by P2's close C
  and close D, P1's forward + C / D, P1 KO'd at life 1).
- `list`: the static $FC scan (every animation slot, the step each record precedes) + the captures -> driver words;
  each word played by its own game's driver in the tap core (tools/makoto3/capture.py: our core with a Z80 port tap,
  the game's commands blocked after its $07): the ADPCM-A start / end it keys on and the level it writes = the sample.
  A voice = one sample, with every index and move that plays it. Prefix $1A (hits, swings) is not a voice; a word 3+
  characters' animations or 3+ roster fighters' captures use is common (KOF98's super flash $1D11). 299 voices: Terry 19,
  Ryo 18, Ralf 20, Robert 19, Yamazaki 17, Billy 16, Kyo 30, Iori 24, Mai 20, Yashiro 26, Rugal 28, Geese 15, Mr. Big 13,
  Krauser 12, Goenitz 10, K' 12 (no looped voice among them: one segment each).
- Code-sent voices are most of them: KOF98 Terry's specials, hit and KO voices come from code (index $AF-$BE), only his
  win / intro lines and a throw voice are $FC records.
- Non-KOF banks (TODO #68, 2026-10-05; voices.py `OWN`, the same voices.json layout, `"kof"` in roster[].voices means
  the fighter's own game): **Samurai Shodown IV** (SNK's driver Ver 1.0): every sound goes through $542C, index -> long
  $55DE + 4 * index = prefix + code, queued at $108EEC (WLOG there: d1 = the word, a4 = the sender); senders = the
  animation steps' extra word (box word bit 3: static scan) and code (the normals' shout $1C81, the specials' lines, the
  hit grunt $1C8A sent by the hit's effect object: the capture_ss4 recipes re-run with WLOG). Haohmaru = prefix $1C:
  28 voices (KO voice not found). **World Heroes Perfect** (ADK's driver, not decoded): one byte a sound or $FC + a byte
  (a second page), all sent by code ($9CCA; no step command carries a sound), so the listing is the captures' (SNDLOG of
  the capture_whp recipes Hanzou plays alone); a voice = a word its own driver keys on ADPCM-A channel 3 (swings / hits
  are channel 5). Hanzou: 8 voices (normals' shouts, his four specials); hit / KO grunts and intro / win lines not found.

**Brawler side**:
- game.json `roster[].voices` (layer 1 table above). Keys (`voices.keys`): every BA_* move, `throw_c` / `throw_d`, `hit`,
  `ko`, `select`, `special:<input>` per special of the pool. KOF's own per key (`voices.suggest`): the $FC record in the
  move's source animation (its step), the throw animation's record (its script row) else its captured voice, the
  captured hit / KO voices, the first intro line for `select`, the special's first captured voice at its frame (as
  played: frozen rows dropped). One voice per key (Kyo's 236A says two lines in KOF: the first is kept).
- Export (`export_bm.voice_data`): `bchar_t.voices` = [voice id, at] per key (VK_* in bm_chars.h: BA_*, VK_THROW +
  BT_*, VK_HIT, VK_KO, VK_SELECT, VK_SPEC + pool index), `nvoice`; build/voice_map.json = the ids each fighter maps.
- Sound build (`build_snd.py voices`, songs.json `voices`): only the mapped voices' samples, copied from their game's
  V ROM; one code per sample from $11 (KOF98's prefix commands play a code only when its bit is set in the slot's
  32-byte enable map, $0F1A: $2E20 + 2 * slot; $00-$10 are off) in slot 2 ($1C, players) and slot 3 ($1E, enemies),
  record [KOF98's own priority (else $50)][start][end][the level its driver writes]; build/snd/voices.h: per fighter
  voice id -> code.
- Game (fighter.c): `voice_tab[]` (RAM, a pack can repoint it); a key fires when its move reaches `at`: an animation
  step entered (play / anim_tick), a special's row reached (special_update), a throw's row (throw_update); `hit` / `ko`
  in fighter_hit and at throw impacts (the victim's), `select` at the pick (main.c). The select screen's previews are
  mute. Players send $1C, enemies $1E, through the queue's guard as effects.
- Pack version 3: the roster section gets per fighter a big-endian offset of its voice table (0 = the ROM's), the
  table only when it differs (build_tables.voice_tabs = chainlab/stagepack.js); checked (ids within its list).
- Lab, Characters tab, "Voices": base (KOF's own / none), per key KOF's own with a play button (the WAV of the sample),
  an override picker (any of the fighter's voices or none), "live" when the sample is in this V ROM, else "NEEDS A
  BUILD"; export / import in the roster's layout (ids checked). Data: chars.json `voices` (make_site.py, WAVs in
  site/voices/<fighter>/).
- Default: every roster fighter `"kof"`: 148 samples, 1.12 MB of voices (codes $11-$A4); V ROM 4,128,768 bytes
  (3.94 MB, was 3.01 MB): all 16 fit a 4 MB V ROM.

**Proof** (2026-10-05, our emulator; /data/tmp/voices):
- `voice_proof.py terry kyo` (the tap core, lab training, D / forward+D / down+D / up+D): EX 236C, 214C, 623C, 214D
  each send $1C + its code, the driver keys on exactly its record, KOF's own voice for that move ($1C4C, $1C4B, $1C4F,
  $1C4D), the played bytes = KOF98's V ROM bytes at the KOF sample, the level written = KOF98's ($DC). `kyo terry`: EX
  624D, 623C, 624B = $1DBB / $1DB9 (KOF98's own), and the dummy Terry's hit voice $1C43 on $1E, all byte-identical.
- Live: Terry's EX 236C set to voice 2 and 214C to voice 5 (not in the V ROM) in the page: the page's pack =
  build_tables.py's pack of the same roster (3130 bytes; unedited 2970 = 2970), installed (status 2): EX 236C plays
  voice 2's sample, 214C silent.
- regress.py bleed True (frame-exact); campaign29.py log identical to the Characters-tab run's.

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
