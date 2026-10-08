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
| chain routes | `rt_head_t` + `rnode_t[]` (fighter.h) | 16 + 24 bytes a node (tree version 4; revamp 1A: link slot 7 = up+A, `RF_THROW`, the node's last byte its hit-stop, the head's `arch` / `links`; older trees read the same: those bytes were 0) | ROM, `route_tab[]` in RAM | yes: the Chain Lab (lab.buf, `lab.load` 1), the chain tool with its retime table (`lab.load` 5, "The chain tool") |
| chain core rules | `gchain_t gchain` (gamedata.h) | 8 bytes | ROM | no (game.json `chain`, "Chains" below) |
| meter | `gmeter_t gmeter` (gamedata.h) | 20 bytes | ROM | no (game.json `meter`, "Meter, breaker, damage tiers" below) |
| damage tiers | `dtier_rom[BC_COUNT]` (game_tables.h): per fighter [nspec + 2] 8.8 scales | 2 bytes a special | ROM; `dtier_off` RAM test switch | no (game.json `tiers` + tools/brawler/damage_raw.json) |
| specials by role | `bchar_t.spmap` (4 bytes: an index in the fighter's `specials`, 0xFF none) via `spec_tab[]` | 4 bytes a fighter | ROM, `spec_tab[]` in RAM | yes: a data pack's roster section (version 2) |
| fighters | `bchar_t bm_chars[]` + everything it points at | ~35 KB each | ROM ($200000) + C ROM | no: new content = a ROM build |

## Layer 0: the bank

One entry per fighter, read by `export_bm.py` from the game's dictionary (`tools/kof96/export96.py`, any of KOF96,
KOF98, KOF99; `tools/kof94/export94.py`; `tools/samsho4/export_ss4.py` for Samurai Shodown IV, `tools/whp/export_whp.py` for World Heroes Perfect, `tools/kizuna/export_kz.py` for Kizuna Encounter (pre-scaled to its in-play zoom $CC), `tools/doubledr/export_dd.py` for Double Dragon 1995 (Billy Lee + his transformed form, full size; specials as programs with variant tables), the same layout): every animation (6-byte step records: ticks, frame, flags, then commands), the frames (sprite parts and
tiles), hit / hurt boxes, palettes (every colour set), physics, captured specials (scripts of rows) and throws
(thrower and victim timelines), victim postures. The bank is addressed by a spec `game:name` (`kof98:terry`). It is
never edited: layer 1 picks from it.

### World Heroes Perfect's six buttons in the bank (2026-10-07, `tools/whp/moves_whp.py`)

WHP has six attacks: A / B = light / heavy punch, C / D = light / heavy kick, A+B = strong punch, C+D = strong kick
(a chord = the buttons pressed within 3 frames, $2E25C; the press is handled when the window closes, so the stick
counts as it is then). Strengths are named **low / mid / high** (A / B / A+B, C / D / C+D). The importer reads every
fighter's buttons from the ROM's action tables, the same code for the whole cast (a fighter = its row, +$6004 - 1):

- **Normals**, button x stance (`moves_whp.normals`): the ground table word[$349C0 + 32 chord + 2 (stick & 14)] (neutral,
  down, a direction), + 1 with the stick away from the opponent ($3535C), + $18 inside the close reach byte[$34594 +
  32 row + n] + byte[$34574 + victim row] ($353BC), the run normals (+ 3, + $1B with down: the six handlers'
  immediates), the air handler's (vertical / diagonal, $36FBA). Exported (`export_whp.normal_anims`) as: far
  `atk_X_far` (C+D far = `body_toss`), close `atk_X_close`, crouch `atk_X_crouch`, air `atk_X_jump` / `atk_X_jump_diag`,
  a direction's own animation `cmd_fwd_X` (Hanzou: forward + C far $4D, forward + C+D close $6D), running `atk_X_run` /
  `atk_X_run_low`, X = a b ab c d cd. A stance whose animation is another's is that move (Hanzou: 66 stances, 44 moves).
  New BA_* moves (export_bm.MOVES, appended): A+B / C+D in every stance, air A / B / A+B / diagonal C+D, `cmd_fwd_c`,
  `cmd_fwd_cd`, the twelve run normals; all are route cards (routes.MOVE_NAMES, the air ones AIR_MOVE_NAMES: the jump
  picks vertical / diagonal, fighter.c start_node); a fighter without them never plays them (routes.encode `has`; the
  air ones fall back to the jump's C / D / C+D: export_bm SOURCES).
- **The mapping rule** (WHP's six strengths on the brawler's one attack button A): the strengths are route cards, the
  route author places each (light / heavy / strong are different cards: `atk_a_far` / `atk_b_far` / `atk_ab_far`); the
  default tree (routes.default_tree) is unchanged, so a fighter without a routes file plays what it played before.
- **Specials**: every ground special = its command with three rows (`moves_whp.specials`: the punch list $2E40C A /
  B / A+B, the kick list $2E60C C / D / C+D), one program per special with the rows as its variant table
  (`export_whp.rom_special`: each row played by the model handlers_whp.play, its motion in constant-acceleration
  segments, its projectiles spawned on their frame; the head picks the row from column 0; column 1 the damage).
  The row played is `roster[].variant[input]`: a button letter or **low / mid / high**; absent = high (the heaviest).
  Hanzou's picks: 236P low (as before), 236K mid, 623P mid, 214K low, 23536P high (game.json). A command whose three
  entries are one animation, or that is not an attack, is listed in the inventory and not exported (Hanzou's 258P /
  258K: one animation for the three, a vanishing jump to fixed screen places, $35FEA step 8).
- **Throws** (`moves_whp.throws` / `throw_model`): A+B or C+D with a direction near a standing opponent ($315B0, before
  the normal); forward = `throw_c`, back = `throw_d` (#146's walk-in grab + forward / back + A); the thrower's frames
  from the model, the held victim from command 16's table (its defs, feet-centred, postures in
  tools/whp/victim_poses_whp.json), the flight after command 18 as the knockdown animations, impacts = +$60D5 bit 7 steps
  and the landing, control return = the first thrower step after the last impact (throwrom's rule).

Voices are in the bank too: `tools/brawler/voices.json` (tools/brawler/voices.py, "Voices" below): per fighter every
voice sample its KOF plays, with the moves that play it.

## Layer 1: roster and select screen

`roster` is a list; its order is the order of `bm_chars[]` (BC_* in bm_chars.h) and of the HUD portraits.

| field | example | meaning |
|---|---|---|
| `name` | `"terry"` | unique; the export name (upper case on screen) |
| `bank` | `"kof98:terry"` | the layer-0 fighter |
| `watch` | `{"frame": 351, "step": -1}` | the select screen's pose: KOF state and step (-1 = its last, held); optional `"head": [x, y]`: the select cursor's point, px from the feet facing left (default: tools/brawler/head_point.py's rule, TODO #157) |
| `routes` | `"tools/brawler/routes/terry.json"` or `"default"` | its pieces' source (routes.py format; default = the pre-Chain-Lab table): since revamp 1A the game plays the chain `routes.py chain_tree` builds from it ("Chains" below), not the file itself |
| `archetype` | `"balanced"` | revamp 1A: `fast` / `balanced` / `heavy` = its chain's length and damage total (game.json `chain.lengths` / `totals`); every roster fighter has one ("Chains" below: the 25 proposals) |
| `finishers` | `{"launcher": "up", "down": "sweep", "forward": "cmd_fwd_a"}` | revamp 1A: its last link's finishers by the stick: `launcher` = the stick that plays the launcher (`up`, `forward` or `neutral`), `down` = `sweep` (a trip), `slam` (a ground slam, the victim bounces up juggle-able) or null (none); `neutral` / `forward` / `up` / `down_move` = a move (routes.py MOVE_NAMES) instead of the generator's pick (written by tools/brawler/chain_reach.py where the pick never reaches the victim) |
| `specials` | `{"D": "EX 236C", "fD": "214C", "dD": "623C", "uD": "214D", "dfD": "236C", "ufD": "623D"}` | the KOF input played by the six special slots (TODO #71; button C since 2026-10-06; the keys keep the old D names): neutral, forward, down, up, down-forward, up-forward + C (diagonals relative to the facing; down-back = down); null = none (an empty slot plays what the input played before the six slots: down-forward+D = down+D's, up-forward+D = up+D's, then their own fallbacks, fighter.c `special_pick`); any special of the fighter's pool (`export_bm.special_pool`: ground specials of the normal condition), all of which are in the ROM, so a change is live (a data pack). `export_bm.suggest_specials` is the automatic pick that filled these |
| `fury` | `"21416C"` (absent = none) | TODO #71: the fury, button D since 2026-10-06 (down+D in the red state, revamp 2: its MAX version `MAX <fury>` when the bank has one, TODO #139; every fury plays the super flash, `super_flash` below) (costs the whole meter, revamp 2; fully invincible from the trigger to its end): the fighter's main desperation move, any special of its bank (KOF DM / SDM, an SS4 rage move: conditions other than normal too); appended to its pool when not in it, `bchar_t.fury` = its index (0xFF none), played as role `BS_FURY`. Picks (2026-10-05): Terry 21416C Power Geyser, Ryo 23624C Ryuko Ranbu, Ralf 23624C (15 hits), Robert 23624C Ryuko Ranbu, Yamazaki 236236C Guillotine, Billy 236236C Chou Kaen Senpuukon, Kyo 21426C Orochinagi, Iori 23624C Ya Otome, Mai 21426D Chou Hissatsu Shinobi Bachi, Yashiro 21426C Final Impact, Geese 1632143C Raging Storm, Mr. Big 23623C (his only DM), Krauser 641236C (his only DM), K' 23624C Heat Drive, Rugal 23624C Gigantic Pressure, Goenitz 2141236C (his DM; the SDM 6321463214C left), Haohmaru BUST 236D (SS4 rage move), Hanzo HERO 623AB (World Heroes Perfect's 623 + A+B with the hero gauge full, the "Super Shoryuha"; MAX = MAX HERO 623AB, the hero desperation move 65426AC), Kim 6246A (Kizuna Encounter's Phoenix desperation move, life <= 96 there), Rosa 6246A (Kizuna's grab, throw and aerial chase; MAX = her other desperation move, 421A: TODO #213) |
| `air_specials` | `{"dA": "j.2B"}` (absent = none) | TODO #200 / #221: the air-special table, specials of its bank its source plays from a jump (read from the ROM as programs). Key = the stick's slot as the six ground C slots name it (`""` neutral, `f` forward, `d` down, `u` up, `df` down-forward, `uf` up-forward; diagonals relative to the facing, down-back = down) + the button `A` or `C`; value = the special's input in its bank. That press in a jump plays it (fighter.c `air_pick`; a diagonal without an entry plays its vertical's: down-forward -> down, up-forward -> up): an `A` entry in the air normal's place (no meter; not while a jump-cancel's node waits), a `C` entry at a C special's meter (meter.special); a projectile special while its projectile flies: none (the press is then the air normal / nothing). Each is appended to its pool in table order when not in it; `bm_air[id]` = [input, special index] per entry (`bchar_t.nair` entries) (input = slot BS_D..BS_UF_D | AIR_A for A), 0xFF ends; played as role `BS_AIR` (vocabulary `air.special`, no cancels out of it). Rule for a new fighter: put an air version on the same slot + C as its ground version (Rosa's 623C is down+C on the ground, j.623C down+C in a jump), the A button only for a dive that takes the air down+A normal's place. Set: Kim `dA` j.2B (Kizuna Encounter's diving kick, export_kz AIR), Rosa `dA` j.2C (Kizuna's dive with its down+A follow-up, TODO #213) (planned, TODO #221: `dC` j.623C, `uC` j.421C), Hanzo SS2 `dA` j.4123S (Samurai Shodown II's shuriken, 4 1 2 3 + S in a jump there: handlers_ss2 `han_j4123s`, the A+B row, TODO #211; a projectile special) |
| `down_attack` | `"DOWN 8/2"` (absent = none) | TODO #218: a special of its bank its source plays at an opponent lying on the floor (read from the ROM as a program): up / down + A on the ground with an opponent lying within 160 px plays it at that opponent, no meter; appended LAST to its pool (the others keep their indices), `bchar_t.down_spec` = its index (0xFF none), played as role `BS_DOWNATK` (vocabulary `attack.down`). Set: Cheng Fu (Double Dragon's 8 / 2 + a button, export_dd 'DOWN 8/2': 124 > 125). Billy Lee / Super Billy have the same move in DD (not set) |
| `invincible` | `["EX 421D"]` (absent = none) | TODO #202: the inputs of its specials (as in `specials` / `fury`) that are invincible from their first frame to their end, the fury's rule (`INV_FURY`: no hit, grab or push reaches the fighter): `bspec_t.sflags` SF_INV, fighter.c start_special. Bruno's call per move, over the source's own frames (KOF98's EX 421D has none for its first 11 frames only: its steps without a hurt box, which the brawler plays anyway). Set: Kyo EX 421D |
| `hit_sfx` | `{"A": "SLASH", "623B": "SLASH", "throw_c": "BACK BREAK"}` (absent = KOF's own) | TODO #75: hit sounds by use, songs.json sfx names. Keys: a normal's button (`A` `B` `C` `D` `CD`: fighter.c `hit_sound`, `bchar_t.sfx`), a throw's impacts (`throw_c` / `throw_d`), a special's KOF input (export_bm `move_fx`: the KOF98 hit kind playing that code, burn kept). Rules without data: a fury's hits play $9C SDM IMPACT; a grab or a command grab's catch $19 GRAB START. Set: Haohmaru A/B/C/CD + 421C + 623B `SLASH` ($2B; D is his kick), Krauser `throw_c` `BACK BREAK` ($3D). Kyo `21426C` / `MAX 21426C` `FIRE HIT` ($2E alone, KOF96's fire hit: TODO #206; his fury burns by its flames' element, handlers98 `fire_element`). No guard exists in the brawler, so $17 BLOCKED HIT has no event. Proof: /data/tmp/sfx75/sfx75_proof.py |
| `fire` | `["214A", "214B"]` (absent = none) | TODO #163: specials (KOF inputs) whose hits burn the victim (fighter.c `set_burn`, the fighter's flame colour) though their game's hit kind is not a fire one (KOF96 sets no hit kind on the Blitz Ball object: +$1B8 = 0). export_bm `move_fx` (the body's hits and its projectiles'). Set: Krauser's Blitz Ball 214A-D (Bruno 0.0.72: "these are literally fireballs"). |
| `damage` | `3` (absent = 1) | TODO #203: the fighter's damage scale, 1-4: since revamp 2 its measured specials, furies and MAX deal their tier ("Meter, breaker, damage tiers"), the scale stays on a special not measured (its tier scale, build_tables `dtier_tables`); since revamp 1A its normals carry their own damage in their route nodes: the chain's links the archetype's total (the scale no longer applies), the jump-cancel / dash / C-without-special / air entries their damage times this scale (baked by routes.py chain_tree); a fury's hits (D / down+D), throws and hold hits keep the engine's own numbers. Set: the four Samurai Shodown II fighters at 3 (Bruno 20261007-130138-b3f3: "triple the amount of damage per hit"; SS2 measured in our emulator: a slash takes 7-20 % of the life, KOF98's normals 4-10 %, tools/samsho2/dmg203_proof.py). |
| `unlock` | `"always"` or `{"boss_of_stage": 1}` | locked on the select screen until that stage's boss is beaten (save bit stage - 1) |
| `voices` | absent, `"kof"` or `{"kof": true, "set": {"hit": 3, "special:236C": null}}` | absent = silent (none of its samples in the V ROM); `"kof"` = KOF's own voice on every move (the suggestion); an object = that base (`kof` false: none) with these keys changed to a voice id of its list (null: silent). Keys: every BA_* move name, `throw_c` / `throw_d`, `hit`, `ko`, `select`, `special:<input>` of its pool ("Voices" below) |
| `display` | `"BILLY LEE"` | the name shown (HUD, select) when it differs from `name` upper-cased (at most 10 characters) |
| `scale` | `1` | the fighter's size: 1 = its game's art at full size (Double Dragon's Billy Lee, 115 px, Bruno 2026-10-06; Kizuna's fighters are exported at 0.80 by their exporter); a per-fighter value so it can change later (export_dd accepts 1 today) |
| `variant` | `{"623": "A"}` (absent = the source's default, the heaviest) | the row of a special's variant table played (vocabulary `variant.table`: DD's four buttons; WHP: a button or low / mid / high), latched at the move's start |
| `form` | `{"trigger": "down+D full meter", "transition": "FORM", "target": "billy_super", "carry": ["life", "position", "facing", "meter"], "exit": "life"}` | the form link (vocabulary `form.change`): the trigger starts the transition (a special of its bank), which turns the fighter into the target roster entry; exit `life` (a lost life) or `stage` |
| `flash_pose` | `"rage"` / `"taunt"` / `"charge"` / `"win"` / `"intro"`, or `{"anim": 88, "first": 0, "last": null, "head": [x, y], "fit": false, "voice": false}` (absent = the source game's default) | TODO #145, vocabulary fx.super_flash "flash pose": what a fury from a source without a flash step (Kizuna, SS2, WHP, Double Dragon) shows during the super flash's freeze; kinds per game in export_bm FLASH_POSES (Kizuna taunt; SS2 rage (default, TODO #189: the game's own POW-full animation 140, timed to the freeze, its shout sent on its step) / taunt / win; WHP win / intro; Double Dragon charge / win); cut to the freeze (`fit`: timed to it); the glow on its head point (`head` overrides head_point.py). KOF fighters: ignored (their own flash step) |
| `selectable` | `false` (absent = true) | no select slot: a form link's target (Super Billy); never picked (roster_unlock 0xFF) |
| `retime` | `{"214C": [40, 38, 40], "atk_b_far": {"scale": 0.75}, "214B": [16, 1, 8, 6, 30]}` (absent = every move at its source timing) | revamp 1C: target frames per segment of a move, played at run time ("Retiming" below); the data keeps the source timing |

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


## Chains: the chain core (revamp phase 1A, 2026-10-08; docs/brawler_feel.md 8h, docs/brawler_revamp_plan.md 1A)

One standard chain system for every fighter (fighter.c "chain core", routes.py `chain_tree`, game.json `chain` ->
`gchain_t`), Bruno's decisions 8h:

- **Advance only on hit.** A link that whiffs, or the attacker being hit, restarts the chain at link 1 (start_node /
  fighter_hit clear the window). A hit on any enemy counts (Final Fight). A multi-hit link deals its node's whole damage on
  its first hit on each victim (`fighter_t.ldmg`) and the next link waits for its last hit (`hits_to_come`).
- **Window.** The next press is taken from the end of the hit-stop through the link's recovery (a cancel) and
  `chain.window` (35) frames after it, from neutral (`chain_t`, set to window + 1 since it is counted down before read).
- **Latch + buffer.** A press in the hit-stop is latched (its age does not grow while frozen) and fires on the first free
  frame; a player's press older than `chain.buffer` (5) frames (hit-stop frames not counted, `fighter_t.buf_age`) is
  dropped; the AI's presses are kept whatever their age (1B's follow-up timing); a press in a whiffing link's last 5 frames
  starts link 1 as it ends.
- **Length by archetype**: the tree's depth, `chain.lengths` fast 5 / balanced 4 / heavy 3 (Final Fight's Guy / Cody /
  Haggar).
- **Finishers by the stick** on the last link (the last builder's links): A neutral (knockdown), `fA` forward (a push:
  blowback, or the launcher), `uA` up (the launcher by default: tree slot 7, RI_UA; the stick's up = `combo_input` 0x08),
  `dA` down (a sweep: trip, or a slam: RE_SLAM, to the floor at once then a 6 px/f bounce, juggle-able, `kslam`), `bA`
  back = the back throw (RF_THROW node, fighter.c `chain_throw`): the victim the link before hit, reeling on the ground
  within 96 px, is grabbed where it stands and thrown with the fighter's throw whose victim ends behind it (throw D first,
  then C; a stun strike is no throw; none behind: its throw played mirrored, the thrower turned away), the thrower
  untouchable (INV_FURY + `cthrow`) to the throw's control return, the thrown body knocking others down (spawn.body, as
  before), no chain credit. down-forward -> forward; a missing finisher (or no throw / no victim in reach) -> neutral.
- **Hit-stop per node** (`rnode_t.hitstop`, its last byte): link k of N = 6 + 6 (k - 1) / (N - 1) rounded (fast 6 8 9 11
  12, balanced 6 8 10 12, heavy 6 9 12), every finisher 12; other nodes by class (light 6, strong 9, an effect 12); 0 = the
  engine's HITSTOP (7: specials, furies, throws, holds keep it).
- **Juggles**: a hit on a fighter falling in its knockdown counts (`jug_n`); at `chain.juggle_cap` (5) nothing reaches it
  until it lands; once its knockdown touched the floor (`kfloor`) it is downed and untouchable until it stands (a fury's
  own hits, a cancel's juggle window and the down attack, TODO #218, excepted).
- **Hit stun**: an enemy's light reel `chain.stun_light` (28), heavy `stun_heavy` (32); a player's `stun_player` (16) and,
  from the hit, `guard_player` (20) frames in which only the attacker that hit it reaches it (`guard`, `guard_by`; grabs
  too): a crowd cannot juggle a player.
- **Fixed damage**: no random spread; a chain's links scaled so the whole chain (any finisher) totals `chain.totals` fast
  21 / balanced 23 / heavy 27 (Final Fight's 42 / 46 / 54 halved for the brawler's 60 life).

`chain` (game.json): `window`, `buffer`, `juggle_cap`, `stun_player`, `guard_player`, `stun_light`, `stun_heavy` (gchain_t,
the engine's), `lengths`, `totals`, `hitstop` [jab, finisher] (the generator's).

**The generator** (routes.py `chain_tree`, called by export_bm for every roster fighter with its build_tables `chain_cfg`:
archetype, length, total, hit-stop scale, finishers, damage scale): (1) the pieces = the fighter's base tree's ground
move nodes breadth first (its routes file, or the default tree), the main line = the plain-A path from the root's A or
close-A link with the most no-effect pieces; (2) builders (links 1 .. N-1) = the main line's no-effect pieces, the first
N-1 (fast, balanced) or the last N-1 (heavy: the strong end), short of them the tree's other no-effect pieces; (3)
finishers: neutral = the line's next piece after the builders (made a knockdown) or the tree's first knockdown / blowback /
trip piece; the launcher = the tree's first launch piece, else far D, down-forward C / D, far C (not the neutral's move);
forward = a push (the tree's blowback piece, the body toss, forward + A / B, far C / B); down = the tree's trip piece or
crouch D (sweep), or a strong close normal the chain does not play yet (slam); (3b) measured: tools/brawler/chain_reach.py
plays each fighter's chain with every finisher in our emulator and, for one that never reaches the victim, writes the
first candidate that does as the fighter's `finishers` override (Terry forward cmd_fwd_a, Ralf neutral atk_b_far /
forward atk_c_far, Yashiro forward cmd_fwd_b, Cheng-Fu neutral atk_c_close / forward + up atk_c_far); (4) damage: the pieces' own damage as
weights, scaled to the total (largest remainder, ties to the later link), every finisher the neutral's share; (5) the
hit-stop scale; (6) links: builder A -> the next, B -> the base tree's jump-cancel, the six C inputs -> the slots'
specials; the root's A -> link 1 (any stick, close or far). The tree carries a `chain` summary (build/chainlab.json).

**Archetypes** (proposals, Bruno reviews each in phase 4; anchors Krauser heavy, Kim fast, Terry balanced): fast (5
links, 21) Robert, Iori, Mai, K', Hanzo (WHP), Hanzo (SS2), Kim, Rosa: light, quick fighters, the ninjas and the
kickers; balanced (4, 23) Terry, Ryo, Yamazaki, Billy, Kyo, Geese, Goenitz, Genjuro, Billy Lee: the all-rounders;
heavy (3, 27) Ralf, Yashiro, Mr. Big, Krauser, Rugal, Haohmaru, Cheng-Fu, Super Billy: the big bodies, the slow big
sword, the power form. Heavies' down finisher is the slam, everyone else's the sweep; every launcher on up.

Proof (our emulator, /data/tmp/rv1a/out): tools/brawler/chain_proof.py (every rule above, the whole roster's chains,
finishers and damage totals; sheets), chain_reach.py (every finisher reaches), controls_proof / cancel_proof /
fury_inv_proof (whole roster), bank_proof, regress (new attract baseline, no-bleed), campaign29.
Results (2026-10-08, after merging brawler 0.4.1): chain_proof roster 25 / 25 (links, per-link damage and hit-stop,
totals), whiff / window (35 frames exactly) / latch + buffer / juggle cap / downed / special hit-stop 7 / stun (28, 32;
player 16 + guard 20) all ok; finishers 124 / 125 (Mr. Big's back throw tosses the body high: it never meets the
enemy standing behind); controls_proof 25 / 25; cancel_proof all but K''s fury -> MAX (fails on brawler 0.4.1 too);
fury_inv_proof (AI_OFF build) ALL OK; bank_proof ALL OK; regress no-bleed True (frame-exact), the new facing baseline
recorded and a second run identical; campaign29 through. Scenarios rv1a-* (tools/brawler/chain_scenarios_check.py plays
each), scenario.py lint 0.

## Meter, breaker, damage tiers (revamp phase 2, 2026-10-08; docs/brawler_feel.md 8h follow-up, docs/brawler_revamp_plan.md 2)

**The meter** (fighter.c "the meter", game.json `meter` -> `gmeter_t`; players only, enemies pay nothing). 3 stocks =
`max` 300 points (`stock` 100), full at the start and at a new life, a point back every `refill` 4 frames (TODO #71's
gain rule rescaled: 120 points at 10 frames a point = 300 at 4, a full gauge in 20 s, a stock in 6.7 s; no gain on
hits, as before). One price list, one path (`pay`) for every press that spends:

| press | cost | short of the meter |
|---|---|---|
| special: C (the six slots, an air special on C, a normal's / a throw's / the hold's cancel into one) | `special` 100 | `life_special` 6 life (never the last point: life must stay above it), else nothing plays |
| breaker: C in a hit stun or held (TODO #71's "special out of a hit, double cost + white flash", converged) | `breaker` 200 | `life_breaker` 12 life, else no breaker (P1 reels on) |
| fury: D (a normal's / a special's / a throw's cancel into it alike) | `fury` 300 | nothing |
| MAX: down+D in the red state only (a fury that landed cancels into it the same way) | `max_fury` 300 | nothing; down+D outside the red state is the fury |
| the form link (down+D, trigger "down+D full meter") | the whole gauge | nothing |

The breaker's sprite blinks white (`blink` 4 frames white, 4 in its colours) from its start to its end (fighter_t.brk,
`pal_overlay`) and it is untouchable to its end (INV_FURY: the escape; 8h "a special is invincible", applied here to the
breaker only). The **red state** (`fighter_low`): life <= `low` 25 % of the full life (15 of 60) and > 0: the fighter
blinks red (its palettes as reds of their light, 4 frames of 16, Fatal Fury Special's warning), the HUD shows MAX next to
its dots (blinking 8 / 8), and only then does down+D play the MAX (bchar_t.fury_max; a fighter without one plays its fury
as the MAX: its MAX tier). The overlays never cover a burn, ai.c's white pulse or a fury's flash pose. A D that cannot be
paid during a special no longer ends it (it plays on). `infinite` (a test switch) 0.

**HUD** (main.c "bars"): the meter bar under the name shows the whole gauge; three dots beside it (P1 right of its bar,
P2 left of its), a filled disc per full stock and a ring per empty one (S ROM STOCK_TILE, make_hud.py: shapes, not
colours alone); "MAX" next to the dots in the red state.

**Damage tiers** (fighter.c "damage tiers", game.json `tiers`): every special's whole damage on a full connect = `special`
12, every fury's `fury` 30, every MAX's `max` 45, the same for every fighter; `spread` 15 / 20 / 20 % are the allowed
bands (build_tables checks they do not overlap: special < fury < MAX whatever the rounding). Against the chain totals
(fast 21 / balanced 23 / heavy 27 of the life of 60): a special about half a chain for a stock, a fury a heavy chain
and more for the gauge, the MAX two chains for the gauge at a quarter of the life. Method: tools/brawler/damage_tiers.py
plays each fighter's six slot specials, fury and MAX (red state) at a standing dummy at 24 / 40 / 70 / 110 / 160 / 200 px
in our emulator (the scales off: RAM `dtier_off`) and keeps each move's best total (its full connect) ->
tools/brawler/damage_raw.json (`--raw --save`); build_tables `dtier_tables` writes `dtier_rom[fighter]` = tier / own total
(8.8) per special (pool index), then the fury, the MAX (build/dtier.json lists them). At run time a special's, a fury's or
a MAX's hits (its body, its objects; a projectile with its thrower's scale at its spawn: fighter_t.dsc) deal damage x the
scale, the fraction carried on the thrower (dacc, from one half: the total rounded to nearest), so the move's total is its
tier's whatever its number of hits; a partial connect deals its share. Normals (the chain totals), throws and holds keep
theirs. A special never measured (not on a slot: enemies' route specials) keeps the fighter's `damage` scale; a special
that never hits (K' 236B / 236D, Goenitz 214B, Haohmaru 623K / 236K, Hanzo 214K: a counter, a dodge, a follow-up's
opener) has no tier. Air specials on A (free dives), the down attack and follow-up presses are not measured (a
follow-up's part deals the same scaled damage). Before / after table: /data/tmp/rv2/out/damage_table.md
(tools/brawler/damage_table.py): before = brawler 0.5.0 (specials 1-48, furies 5-48, MAX 5-80), after = 12 / 30 / 45 for
all 25 fighters.

Proof (our emulator, /data/tmp/rv2/out): tools/brawler/meter_proof.py (gain trace, special by meter / by life / neither,
breaker by meter with the blink per frame / by life / neither, fury, fury short, MAX only at or under the red line,
the red overlay per frame; HUD shots 0-3 stocks and the red state), damage_tiers.py + damage_table.py (the table),
retime_hit_proof.py (squeezed hits: wherever the source hits the squeezed move hits; 1C lost Terry's 214C at 104-160 px,
623C at 100, Ryo's 623A at 84), meter_scenarios_check.py (scenarios rv2-*), controls_proof / cancel_proof (the meter
topped up between a special and its fury, the fury -> MAX tests in the red state) / fury_inv_proof (AI_OFF build),
chain_proof, retime_proof, bank_proof, regress, campaign29.
Results (2026-10-08, after merging brawler a29b26e): meter_proof ALL OK (Terry, Kim, Krauser, Haohmaru, Billy Lee);
damage table ALL OK (25 / 25: every special 12, fury 30, MAX 45); retime_hit 16 / 16 (1C lost hits on 4 runs, none
now); rv2-* scenarios 8 / 8 (scenario lint 0); controls_proof 25 / 25; cancel_proof all but K''s fury -> MAX (as on
0.5.0); chain_proof all but Mr. Big's back throw (as on 0.5.0); retime_proof 25 / 25; fury_inv_proof (AI_OFF build)
ALL OK; bank_proof ALL OK; regress no-bleed True (frame-exact), the new facing baseline recorded and a second run
identical; campaign29 through.

## The chain tool (revamp phase 5, 2026-10-08; docs/brawler_feel.md 9, docs/brawler_revamp_plan.md 5)

Bruno: "a tool that allows me to explore new things, so I don't want to wait for a new build for a new combo". One data
format, three places: the Lab edits it, the running game reads it from RAM, game.json bakes it.

**The spec** (lab.js `chainTree` / routes.py `chain_tree`): `archetype` (the chain's length and damage total), `links`
(the N-1 moves before the finisher), `finishers` {`launcher` up / forward, `down` sweep / slam / null, `neutral`,
`forward`, `up`, `down_move`} (back = the throw, the chain core's rule), `hitstop` (N values, the finisher's last; null
= the 6 -> 12 scale), `retime` {move: targets per segment} (1C). A named link or finisher takes the piece the generator
would (routes.py `chain_base`: the main line's node of that move, else the base tree's first, breadth first; its
weight, speed, push and its damage as the scaling weight; exported per fighter in chainlab.json `chain_base`); damage
scaled to the archetype's total as before. An unedited chain is the ROM's own tree (lab.js `sameChain`).

**The page** (tools/brawler/chainlab/chaintool.js, the Chain Lab tab above the routes editor; data from make_site.py:
chainlab.json `chain` (game.json chain), `retime_rom` (build/retime.json), per fighter `pieces` (pieces.py catalogue:
tags, appeal, reach, segments, travel to contact)): archetype, launcher side, each link and finisher picked from the
catalogue (sorted by appeal, tags shown), hit-stop per link, each used move's segments as a bar with a handle per
segment (drag or arrow keys, 0.5x-2x of the source; the number beside it), readouts per row: frames S / A / R = total
(source), damage, advantage on hit (the victim's stun light 28 / heavy 32 minus the frames after contact), reach and the
spacing margin (pieces.py's rule; < 0 = WHIFF). Buttons: Push to the game, Play neutral / forward / up / down / back
(the autoplay, lab.js `autoKeys`: positions reset, A every other frame, the stick on the last link's press; the game's
own events then listed: each link's contact frame vs its target startup, damage), Fight with it (campaign stage 1 with
the override), ROM's tables back, Save, Download the entry. Drafts stay in the browser (localStorage).

**The RAM override** (the one game hook, fighter.c `lab_install`, `lab.load` = 5; main.c `lab_tick` keeps 3 / 4 for packs):
lab.buf (3088 bytes) = the tree (rt_head_t + nodes, lab.js `encodeTree`, now tree version 4 complete: up+A slot 7, the
throw flag, per-node hit-stop, the head's archetype / links), then a retime table: `gretime_t` rows of 8 bytes
big-endian {fighter, nseg, move u16 (BA_*), t u32 = an offset from buf}, fighter 0xFF ends it, then the u16 targets
(lab.js `encodeOverride`; the ROM's rows of the other fighters are copied in, the table replaces gretime_rom while it is
pointed at). The game checks the tree (magic, version) and every row inside buf, turns the offsets into pointers and
sets `route_tab[fighter]` = buf and `rt_tab` = the table on its next tick; a bad override puts the ROM's back. Any later
tree load (1, 2, 5) first drops it (`rt_lab`); `lab.load = 2` = the ROM's tree and `rt_tab = 0`. Without a load 5 the
game never touches rt_tab (byte-identical behaviour: proof below). `route_tab` / `rt_tab` are in layout.json, so the
page reads back what the game uses ("Push" prints both addresses).

**Save** (the path to the ROM): "Save" POSTs feedback-api/decision {set `chain-tool`, id = the fighter, choice `save`,
label = a one-line summary, note = {fighter, game_version, entry, spec}} into the feedback service's decisions store
(/data/brawler/feedback/decisions/chain-tool.json on the VPS; no server change). I pull it (`tools/brawler/chain_save.py
pull`), apply it (`chain_save.py apply examples/brawler/game.json SET.json FIGHTER`: when the chain changed the roster
keys `archetype`, `finishers` (all named), `chain` {links, hitstop}; `retime` = the fighter's whole map ({} removes it);
the file in build_tables' canonical layout, the diff printed), Bruno accepts the diff, I commit. A downloaded entry
applies the same way (`chain_save.py entry`). build_tables `chain_cfg` passes `chain.links` / `chain.hitstop` to
routes.py `chain_tree` (`links`, `hitstops`), the retime map goes through `retime_tables` as before.

**The Player app** (not built in this phase, the plan): (1) player.c: `Native.writeRam(addr, bytes)` (Geolith's
RETRO_MEMORY_SYSTEM_RAM, big-endian as the core keeps it, called on the emulation thread between two frames like
`setPad`); (2) the feedback service: `POST /api/chain_push` from the Lab's Push stores the last override per user
{game_version, lab address (layout.json `syms.lab`), fighter, bytes base64} and `GET /brawler/feedback/mine/chain_push`
(the Oros token) hands it to the player; (3) the player (Feedback menu, "Load the Lab's chain"): fetches it, refuses
it unless game_version = the running ROM's, writes the bytes at lab + 400, then `LAB1` at lab + 0, fighter at lab + 5,
5 at lab + 7 (the page's exact writes, lab.js `installChain`); the game takes it on its next tick in any mode (the
campaign included), until a reset. Shared format = the bytes above; nothing in the game changes for it.

**Proof** (2026-10-08, our emulator, /data/tmp/rv5: `chainlab/chaintool_proof_node.js SITE GAME OUT SPEC FIGHTER` = the
page's lab.js + core.wasm; spec /data/tmp/rv5/terry_spec.json: Terry's links close A > far B > close C, hit-stops 6 9
11 14, close A startup 4 -> 8, far B 6/3/10 -> 3/3/5, close D startup 4 -> 6): the page's encoder = the ROM's trees
25 / 25, its chain assembly of every fighter's own chain = the ROM's tree 25 / 25; pushed: route_tab[terry] = lab.buf,
rt_tab inside it, P1 retimed (rt_flags) on every finisher's run, every finisher's 4 links hit, each contact at its
target startup (8, 3, 4, 6 frames after the link's start; the ROM's run 4, 4, 4, 4: offset 0), the dummy frozen the
spec's hit-stops, 23 damage = the balanced total; load 2: the ROM's tree and rt_tab 0 back. The page itself (headless
Chrome, the site served locally): the same spec pushed and "Play up" -> contacts 8 / 3 / 4 / 14, 23 damage, the
override read back (out/page_edit*.png, page_phone.png). No override = no change: regress.py on this build = the
brawler 0.6.0 build's JSON identical (bleed frame-exact, every fighter's facing traces); bm_chars.c identical. Save
round trip: the entry the page saves applied by chain_save.py to a copy of game.json (only Terry's object changed) and
built: its ROM tree = the pushed tree byte for byte (544 bytes), gretime_rom = the pushed rows ({0, 3, 9 / 12 / 15});
played without an override on that build (`--rom-only`), every finisher's run = the pushed run (P1 / dummy state,
anim, step, node, freeze, rt_flags, hp per frame and the lab events, from the run's start; the lab frame counter
sampled one off on one row of two runs, the tick boundary).

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

`meter` (`gmeter_t`, ROM only): the meter, players only (revamp phase 2: "Meter, breaker, damage tiers" below).
`tiers`: the damage tiers (the same section).

`super_flash` (TODO #139, `gflash_t`, ROM only): fx.super_flash, the engine's rule for every fury (D) and MAX fury
(down+D): `start` 1 (the fury's frame it starts on), `freeze` 28 (frames the game freezes except the attacker and the stage
is hidden), `white` 4 (of them, frames the backdrop is `white_colour`, then `dark_colour`), `anchor` [0, -96] (px from the
feet, KOF orientation: where the concentration plays when the move has no anchor of its own). KOF98's values
(tools/kof96/handlers98.md "Super flash"). Blue for a fury, orange for a MAX fury (by role).

`ai.rules`: the enemies' shared rules (section "Enemy rules" below; replaced `ai.tokens`). `ai.presets` (today minion,
minion_attract, boss), all fields bytes, `ai_preset_t` (42 bytes) in this order (build_tables.py AI_ORDER; game_tables.c
asserts every offset), then one row per enemy with `ai_over`:

| field | minion | boss | meaning |
|---|---|---|---|
| `flags` | grab, projectile | token, grab, projectile, boss_moves | token: one attack token kept free for it (Enemy rules); grab: approaches may grab; projectile: fires its C special at mid range; reversal (rev_*), specials (bspec_*): the boss block; jump_in (jump_*, hop_*): any enemy (TODO #58); `boss_moves` = reversal + specials + jump_in; full_speed: walks at full speed while positioning (the others at half); air_cd: the jump-in's air attack is C+D (up+A in the air; else air B, down+A) |
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

### Enemy rules (revamp phase 1B, 2026-10-08; docs/brawler_feel.md 8e / 8g / 8h)

`ai.rules` (ROM only, not in the data pack: `gairules_t gai` + `ai_ready[BC_COUNT][2]` in game_tables.c; ai.c reads them):

| field | value | meaning |
|---|---|---|
| `attackers` | 3 | at most this many enemies hold an attack token at once (approach, ready, attack). Tokens are dealt every 16 frames to the closest rested enemies; a `token` preset (the boss) has one kept free for it; a projectile shooter takes one on the spot. A token goes back when the attack ends (able again), when the enemy is hit, knocked down, grabbed or thrown, or after `approach_max` (150) frames without reaching its range |
| `ready.pose`, `ready.fallback`, `ready.by_fighter` | `["atk_c_close", 0]`, `["atk_a_close", 0]`, 6 overrides | the stance held (fighter_t.frame_ovr) during the wait before an attack: [move, step] of the fighter's own animations; `"tint"` = the white pulse instead. Overrides where close C's first frame looks like the idle: yamazaki, geese, rugal, goenitz close C step 1; krauser, mr_big far C step 0. A fighter without the step uses the fallback, then the pulse |
| `ready.pulse` | 12 | the pulse: the fighter's palettes white for 3 frames every 12 frames (fighter_t.flash; meter_tick restores them) |
| `ready.wait` | 32 entries | the random wait (random & 31): Final Fight's table $2245E (1 x2, 10 x4, 20 x6, 30 x8, 40 x6, 50 x4, 60 x2), mean 31 frames |
| `windup.light`, `windup.heavy`, `windup.heavy_from` | [3, 6], [12, 15], 5 | the wind-up target (frames from the attack's first frame to its first live one) of a normal: route damage < 5 light, else heavy. The attack's first frame is held (fighter_t.freeze, the hit-stop's hold) for target minus the move's own startup (its steps before the first live one at the node's speed); a move slower than the target keeps its own startup |
| `windup.special_hold` | [12, 15] | a special (and the boss's reversal): its own startup plus this hold. Jump-ins (the prejump and flight are the wind-up) and walk-in grabs are not held |
| `rank.start`, `rank.max` | 8, 31 | the hidden difficulty rank (ai_rank) at a new game (main.c stage_begin with `first`), its ceiling |
| `rank.every`, `rank.fast_clear`, `rank.fast`, `rank.clean` | 600, 1200, 1, 1 | + 1 every 600 frames of fighting without a hit taken (a player's life going down); a wave cleared (the last enemy gone) in under 1200 frames + 1, cleared without a hit + 1 |
| `rank.death` | 4 | - 4 when a player loses a life (enters S_DEAD) |
| `rank.wait`, `rank.rest` | 16, 16 | aggression: the ready wait and every rest x (1 - rank x 16 / 1024): rank 31 = x 0.52 |
| `rank.damage` | 11 | damage: an enemy spawned at rank r hits r / 11 harder (fighter_t.power, main.c enemy_init; not in the attract): +1 from 11, +2 from 22 |

The rank shows only in the Brawler Lab's status line (`rank n  attackers k`, symbols `ai_rank`, `ai_tokens` in layout.json).
The formation: a FREE enemy stands at one of 8 slots around its player (4 a side; hover_dx and hover_dx + 36 px out,
depth -12 / +12 / -24 / +24), dealt every 16 frames, the closest enemy first taking the free slot nearest to it.
Known limits: an enemy hit in its ready stance shows the stance one frame more (the AI clears frame_ovr on its next
tick, before the hit-stop ends); a normal whose own startup is longer than its target (Billy's far A 9, Goenitz's 10,
Iori's / Yamazaki's 7) keeps it: shortening is retiming's job (phase 1C).

Proofs (our emulator's core, harness; scripts and outputs in /data/tmp/rv1b, tools/ and out/):
- Attack tokens (`tokens_proof.py`, stage 5 wave 1, 6 enemies, per-frame trace `out/tokens_*.txt`): P1 standing 3600
  frames: tokens never above 3, enemies in an attack state (ATTACK, AIR_ATTACK, SPECIAL, GRAB, THROW) never above 3
  (frames with 0/1/2/3 attackers: 1447/1791/335/27); P1 fighting (2499 frames, the wave beaten): the same (1722/686/84/7).
- Ready pose: `out/ready_sheet.png` (each enemy type in the lab's enemy test: its idle and its READY stance on screen),
  `out/ready_stances_rom.png` (every fighter an enemy may be: idle vs the stance, from the ROM tables), the tint pulse
  in a throwaway build (`out/ready/tint_pulse_*.png`: 14 white flashes in 147 READY frames, frame_ovr never set).
- Wind-up (`windup_proof.py`, every enemy type + stage 5's five waves, `out/windup.txt`): measured from the attack's
  first frame to its first live box: light normals 152 attacks 3-10 frames (mean 5.5; above 6 only the moves whose own
  startup is longer), heavy 6 attacks 13-15, specials 45 measured 26-37 (10 ROM-program specials of the bosses have no
  box the proof can read: their hold is the same 12-15).
- Rank (`rank_proof.py`, `out/rank.png`): stage 1 untouched with fast clears 8 -> 19 (+2 per wave, +1 from the clean
  clock), then standing still to a game over 19 -> 15 -> 11 -> 7 (three lives lost); damage bonus 0 / +1 / 0.
- enemy_test.py (all types + the pack write path), bank_proof ALL OK, campaign29 through (stage 5's enemies: power 4
  instead of 2: the rank's +2, P1 never hit in that proof), regress bleed True (frame-exact; the attract changed: new
  baseline /data/tmp/rv1b/out/regress_new.json), scenarios rv1b-attack-tokens / -ready-pose / -windup / -rank (lint
  OK, states generated; scenario.py lint 0 warnings).

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

## Retiming (revamp phase 1C, 2026-10-08; docs/brawler_feel.md 6 and 8h)

Bruno's design: the brawler embeds every move's ORIGINAL timing exactly as in its source game; the animation player
retimes a move dynamically at run time. Nothing of the exported frames, steps or programs changes; the export only
adds each move's segments.

**Segments** (tools/brawler/retime.py, the export's `move_segments`): a move played alone, frame by frame as the
engine plays it (no opponent, no hit, no button held: its whiff): `startup` = the frames before its first frame with a
live attack box (bstep_t flags 1), then for each active window (a run of frames with one) the window and the recovery
after it (to the next window; the last to the move's end, the frame the fighter acts again). A single-hit move has 3
segments, left punch / pause / right punch 5, Cheng-Fu's 236 13. A move whose body never strikes takes the step it
spawns its object on as its window. Brawler moves: from their animation's steps (a step shows ticks + 1 frames). ROM
specials (KOF handlers, SS2 / Double Dragon / Kizuna / WHP programs): their program played by retime.Prog, a port of
fighter.c prog_update (the variant row the roster plays). Captured scripts (Yamazaki's 214A/B/C, Goenitz's 214C, ...):
no segments, not retimed.

| table | type | size | in | live-swappable |
|---|---|---|---|---|
| segments | `bm_seg[BC_COUNT]` (bm_chars.h `bseg_t`): per fighter [BA_COUNT + nspec, offset per move (0 = none)], then per move [n, source frames of its n segments] | ~0.5 KB a fighter | ROM, first MB | no (the export) |
| targets | `gretime_rom[]` (fighter.h `gretime_t` {fighter = bchar_t.id, nseg, move = BA_* or BA_COUNT + special index, const uint16_t *t}, fighter 0xFF ends) | 8 bytes + 2 a segment | ROM (game_tables.c), read through `rt_tab` | yes: a table in RAM (lab.buf), `rt_tab` pointed at it (0 = the ROM's; tools/brawler/retime_proof.py does it) |

`chainlab.json` lists the segments for the Lab: `fighters[].segs` = {`moves`: {move: [lengths]}, `specials`: [lengths
per pool special, [] none]}; `build/retime.json` every entry built (fighter, move, segments, targets, hand checks).

**game.json** `roster[].retime` = {MOVE: TARGETS}. MOVE: a brawler move (`atk_c_close`) or a special's input as the
roster names it (`214C`, `EX 236C`, `MAX 21416C`). TARGETS: a list, one per segment (`null` = that segment's source
length, `"1.5x"` a ratio); or `[startup, active, recovery]` applied to every window / recovery of a longer move; or
`{"scale": s, "startup": .., "active": .. or [per window], "recovery": .. or [per window]}`; `null` = the original.
build_tables.py checks the move has segments and every segment at least 1 frame; a segment outside 0.5x-2x is built
and printed as `retime: hand check: ...` (and listed in build/retime.json).

**The player** (fighter.c "retiming"): `play()` (a brawler move) and `start_special` look their move up in `rt_tab`
(`fighter_retime(f, targets, n)` sets them for the move playing: archetype defaults, situations). Per segment of S
source frames played in T game frames, a Bresenham clock: each game frame `err += S`, one source frame due each time
`err` passes T, so the segment ends exactly on its T-th frame with its S source frames played and every segment's
first frame shows its own first source frame (each window's contact frame is shown). Source frames are played whole
and in order by the move's own player (anim_tick at 1x, prog_update + its frame voices), so every step entry, step
move, box, effect, sound and program op happens; several in one game frame when T < S (a frame that enters a new hit
window stops there and the rest is carried, paid by the segment's last frame at the latest), none when T > S: a ROM
program's motion of that source frame is then spread over the game frames that show it (`rt_hold`, `rt_dx`, `rt_dy`:
travel per segment unchanged, the place equal to the source's at every frame where its source frame is complete); a
brawler move's travel is its steps' own moves, at their entry. Not scaled: hit-stop (`freeze` stops the clock), the
victim's reaction, projectiles, a ROM special's catch (its dead frames and routine: 1x from the catch on), the route
node's speed (ignored by a retimed move), the engine. Collisions: the frame shown is tested by combat() as every frame;
since revamp 2 every source frame passed inside a game frame (T < S) runs its own hit test at once (fighter.c `rt_probe`
-> `strike`, the attacker's box against every opponent), and a hit stops that game frame there (its hit-stop then stops
the clock, the rest carried): a squeezed hit connects where the source's did (1C tested only the frame shown;
`rt_probe_off`, a RAM test switch, brings that rule back for the proof: tools/brawler/retime_hit_proof.py).
Without an entry nothing of this runs (`rt_flags` 0).

**Proof** (2026-10-08, our emulator, /data/tmp/rv1c/out): build without entries = the brawler branch's in behaviour
(regress.py bleed + facing traces identical); `retime_proof.py OUT` (targets installed in RAM at run time): Terry's B
far (KOF98 normal), Terry's 214C (KOF ROM special, a flight), Haohmaru's 623S (SS2 program), Cheng-Fu's 236 (DD
program, 13 segments), Kim's 214B (Kizuna program, 5 segments with their own targets) at 0.5x / 0.75x / 1.5x / 2x and
odd targets: 25 / 25 exact segments, source frames in order, every segment's first source frame shown, the place equal
to the source's on every settled frame and after the move, hit-stops 7 and the dummy's reaction unchanged;
`retime_rom_check.py` the same from the ROM's own table (a build with entries).

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
