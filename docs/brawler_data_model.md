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
| 1, roster | the playable characters: which bank fighter, select pose, specials mapping, chain routes, unlock, throws (`throws`: per throw `speed` 8.8, `front` [first, end) rows the victim is drawn in front, `hold` {hit, fin: the hold hits' moves (default: hit = the fastest-startup close normal, fin = close D; TODO #166), dx: px in front}; TODO #146; revamp 3: `extra` {u, d, b} the hold's up / down + A and B throws (b: a grab special on B alone, note 20261016-043416-e03d) and `super` the super throw, "Throws" below); the select screen | game.json `roster`, `select` | Brawler Lab: Characters tab (+ the Chain Lab for the routes) |
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
| meter | `gmeter_t gmeter` (gamedata.h) | 24 bytes (revamp 3: the super throw) | ROM | no (game.json `meter`, "Meter, breaker, damage tiers" below) |
| damage tiers | `dtier_rom[BC_COUNT]` (game_tables.h): per fighter [nspec + 3] 8.8 scales (revamp 3: + the super throw) | 2 bytes a special | ROM; `dtier_off` RAM test switch | no (game.json `tiers` + tools/brawler/damage_raw.json) |
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
| `finishers` | `{"launcher": "up", "down": "sweep", "forward": "cmd_fwd_a"}` | revamp 1A: its last link's finishers by the stick: `launcher` = the stick that plays the launcher (`up`, `forward` or `neutral`), `down` = `sweep` (a trip), `slam` (a ground slam, the victim bounces up juggle-able) or null (none); `neutral` / `forward` / `up` / `down_move` = a move (routes.py MOVE_NAMES) instead of the generator's pick (written by tools/brawler/chain_reach.py where the pick never reaches the victim); `df_move` (2026-10-11, Kyo's double sweep, the Assembly's `fin_df`) = the last link + down-forward + A (RI_DFA, a trip; absent = none: down-forward + A falls back to forward, fighter.c next_ri) |
| `specials` | `{"D": "EX 236C", "fD": "214C", "dD": "623C", "uD": "214D", "dfD": "236C", "ufD": "623D"}` | the KOF input played by the six special slots (TODO #71; button C since 2026-10-06; the keys keep the old D names): neutral, forward, down, up, down-forward, up-forward + C (diagonals relative to the facing; down-back = down); null = none (an empty slot plays what the input played before the six slots: down-forward+D = down+D's, up-forward+D = up+D's, then their own fallbacks, fighter.c `special_pick`); any special of the fighter's pool (`export_bm.special_pool`: ground specials of the normal condition), all of which are in the ROM, so a change is live (a data pack). `export_bm.suggest_specials` is the automatic pick that filled these |
| `fury` | `"21416C"` (absent = none) | TODO #71: the fury, button D since 2026-10-06 (down+D in the red state, revamp 2: its MAX version `MAX <fury>` when the bank has one, TODO #139; every fury plays the super flash, `super_flash` below) (costs the whole meter, revamp 2; fully invincible from the trigger to its end): the fighter's main desperation move, any special of its bank (KOF DM / SDM, an SS4 rage move: conditions other than normal too); appended to its pool when not in it, `bchar_t.fury` = its index (0xFF none), played as role `BS_FURY`. Picks (2026-10-05): Terry 21416C Power Geyser, Ryo 23624C Ryuko Ranbu, Ralf 23624C (15 hits), Robert 23624C Ryuko Ranbu, Yamazaki 236236C Guillotine, Billy 236236C Chou Kaen Senpuukon, Kyo 21426C Orochinagi, Iori 23624C Ya Otome, Mai 21426D Chou Hissatsu Shinobi Bachi, Yashiro 21426C Final Impact, Geese 1632143C Raging Storm, Mr. Big 23623C (his only DM), Krauser 641236C (his only DM), K' 23624C Heat Drive, Rugal 23624C Gigantic Pressure, Goenitz 2141236C (his DM; the SDM 6321463214C left), Haohmaru BUST 236D (SS4 rage move), Hanzo HERO 623AB (World Heroes Perfect's 623 + A+B with the hero gauge full, the "Super Shoryuha"; MAX = MAX HERO 623AB, the hero desperation move 65426AC), Kim 6246A (Kizuna Encounter's Phoenix desperation move, life <= 96 there), Rosa 6246A (Kizuna's grab, throw and aerial chase; MAX = her other desperation move, 421A: TODO #213) |
| `air` | `{"forward": "atk_d_jump", "straight": "atk_d_jump", "down": "atk_c_jump", "back": "atk_b_jump"}` (absent = build_tables AIR_DEFAULT, then its bank game's AIR_BANK) | its jump attacks (Bruno 2026-10-08): `forward` = A in a forward jump (its `_diag` twin plays: KOF's diagonal jump normal), `straight` = A in a straight jump, `down` = down + A in any jump; `back` (Iori's note 20261011-210422-5d29 and its reopen) = back + A in ANY jump (its `_diag` twin in a forward / back jump; Iori: KOF98's j.4B Yuri Ori, the cross-up), absent = the jump's own attack (routes.py chain_tree entry `air_ba` -> rt_head_t.pad[1], fighter.c `jump_atk`; the Assembly's `air_ba` row compiles to it). Values: routes.py AIR_MOVE_NAMES |
| `air_specials` | `{"dA": "j.2B"}` (absent = none) | TODO #200 / #221: the air-special table, specials of its bank its source plays from a jump (read from the ROM as programs). Key = the stick's slot as the six ground C slots name it (`""` neutral, `f` forward, `d` down, `u` up, `df` down-forward, `uf` up-forward; diagonals relative to the facing, down-back = down) + the button `A` or `C`, or `dd` + the button (`ddA`: a down,down tap then the button in the jump, the Blitz's reading, any stick; AIR_DD; Bruno 2026-10-09: Kim's j.2B); value = the special's input in its bank. That press in a jump plays it (fighter.c `air_pick`; a diagonal without an entry plays its vertical's: down-forward -> down, up-forward -> up): an `A` entry in the air normal's place (no meter; not while a jump-cancel's node waits), a `C` entry at a C special's meter (meter.special); a projectile special while its projectile flies: none (the press is then the air normal / nothing). Each is appended to its pool in table order when not in it; `bm_air[id]` = [input, special index] per entry (`bchar_t.nair` entries) (input = slot BS_D..BS_UF_D | AIR_A for A), 0xFF ends; played as role `BS_AIR` (vocabulary `air.special`, no cancels out of it). Rule for a new fighter: put an air version on the same slot + C as its ground version (Rosa's 623C is down+C on the ground, j.623C down+C in a jump), the A button only for a dive that takes the air down+A normal's place. Set: Kim `ddA` j.2B (Kizuna Encounter's diving kick, export_kz AIR; down + A in a jump stays his air normal $60), Rosa `dA` j.2C (Kizuna's dive with its down+A follow-up, TODO #213) (planned, TODO #221: `dC` j.623C, `uC` j.421C), Hanzo SS2 `ddA` [j.4123A, j.4123B, j.4123AB] (a SEQUENCE since 2026-10-11, notes 20261011-164455 / 164801: a list value plays its pieces back to back; then, reopened on 0.10.57, TOGETHER (`together`: the three shurikens in one throw), also on a `blitz` slot: docs/brawler_gold.md "A sequence"; before that j.4123AB alone: his air Blitz since 2026-10-11, the A+B version the export played for j.4123S, Bruno's decision; was `dC`, before that `dA` until the SS2 air standard gave jump + down + A the air C+D; `keeps_air_attack`: a jump attack after it; Samurai Shodown II's shuriken, 4 1 2 3 + S in a jump there: handlers_ss2 `han_j4123s`, the A+B row, TODO #211; a projectile special) |
| `blitz_cancel` | `{"dd": ["uu"]}` (absent = none) | Bruno 2026-10-09 (note 20261009-114542-5d29): a fighter's quirk, the Blitz slots a Blitz may cancel into on hit (like the ladder's other rungs; free like any Blitz); every other Blitz -> Blitz stays forbidden (0.8.1). build_tables `blitz_cancels` -> `gblitz_can[fighter][slot]` (bit per target slot), fighter.c `update` / `S_SPECIAL`. Set: Terry dd (426B Power Charge) -> uu (214D Crack Shoot) |
| `blitz_slide` | `{"ff": {"px": 20, "frames": 12}}` (absent = none) | Bruno 2026-10-14 (note 20261014-192939-5d29): a Blitz slot's forward glide on top of its move: px over frames from its first frame, fast first and slowing linearly to a stop (px 1-127, frames 1-60); a hit-stop holds it, a new state (cancel, hit taken) ends it. build_tables `blitz_slides` -> `gblitz_slide[fighter][slot]`, fighter.c `blitz_slide`. Set: Haggar ff (his dash entry, FF's standing finisher) 20 px / 12 frames, starting at his run's 3.08 px a frame |
| `walk_rate` | `1` (absent = the engine's rule) | note 20261014-084140-5d29 (Final Fight's Haggar, "the walk plays too fast"): the walk / run animations' rate fixed, 1 = its steps' own ticks (the source's measured cadence: export_ff WALK_CYCLE, FF's 34 frames a stride), instead of the rule (archetype speed / its source's walk x `walk.anim` 1.5, fighter.c `walk_rate`); build_tables `walk_phys` writes the bphys_t walk that makes the rule give it. Set: Haggar 1 |
| `run` | `{"mode": "dash", "dash": {"start": 2, "frames": 16, "dx": 106, "height": 6}}` or `{"hold_last": true, "float": {"px": 3, "period": 24}}` (absent = its export's run) | Bruno 2026-10-09 (note 20261009-102625-5d29): `mode` "dash" (reopened on 0.10.8: "the kind of dash we had in KOF94 / 95; dash and run are two different things"): forward, forward = one burst that ends on its own, not a run: `start` frames on the ground, then `frames` frames covering `dx` px at a steady speed on a parabola `height` px high (drawn only), then the animation's landing step and neutral (holding forward: the walk); the stick is ignored during it, A / B / C / D still act as from a run (the ff Blitz / dash attack, the jump with run_dx); build_tables `run_bobs` -> `grun_dash`, fighter.c neutral, main.c `run_bob`; export_kz times the run animation's air step to it. `hold_last` = its source's run / dash animation played once and held on its last step; `float` = the body drawn px x (1 - cos) / 2 higher over period frames while running (`grun_bob`; drawn only). `air_buttons` true (note 20261011-114113-5d29; only with mode dash): in the dash's airborne frames the buttons are a jump's (A / down+A: the forward jump's air_cd / air_b, C: an air special; B / D nothing), the press turning the dash into a forward jump on the rest of its course (fighter.c `dash_air`, the dash table's last byte; rule in docs/brawler_gold.md "The dash"). Set: Kim dash (Kizuna's 66 measured: 144 px in 16 air frames, 8 px high, x 0.738); Billy Lee / Super Billy / Cheng-Fu dash + air_buttons (Double Dragon's 66, export_dd DASH) |
| `down_attack` | `"DOWN 8/2"` (absent = none) | TODO #218: a special of its bank its source plays at an opponent lying on the floor (read from the ROM as a program): up / down + A on the ground with an opponent lying within 160 px plays it at that opponent, no meter; appended LAST to its pool (the others keep their indices), `bchar_t.down_spec` = its index (0xFF none), played as role `BS_DOWNATK` (vocabulary `attack.down`). Set: Cheng Fu (Double Dragon's 8 / 2 + a button, export_dd 'DOWN 8/2': 124 > 125). Billy Lee / Super Billy have the same move in DD (not set) |
| `invincible` | `["EX 421D"]` (absent = none) | TODO #202: the inputs of its specials (as in `specials` / `fury`) that are invincible from their first frame to their end, the fury's rule (`INV_FURY`: no hit, grab or push reaches the fighter): `bspec_t.sflags` SF_INV, fighter.c start_special. Bruno's call per move, over the source's own frames (KOF98's EX 421D has none for its first 11 frames only: its steps without a hurt box, which the brawler plays anyway). Set: Kyo EX 421D |
| `juggle` | `["623A"]` (absent = none) | Note 20261011-201837-5d29 (Kyo): the inputs of its ROM-program specials whose body hits leave the victim hittable in the air (each packed reaction nibble gets the hurt-kept bit 8, export_bm rom_c; KOF's own juggle rule otherwise makes a launch untouchable until it lands); the juggle cap still counts. docs/brawler_gold.md "A special whose victim stays juggle-able". Set: Kyo 623A, Moriya 623A, Robert `air 214D` (note 20261016-040850-e03d) |
| `source_flight` | `["EX 421D"]` (absent = none) | Note 20261011-201729-5d29 (Kyo's forward + C triple kick: "the last two hits or the last hit always whiff"): the inputs of its specials whose body hits leave a free victim on its SOURCE's reaction path (KOF98's own: fighter.c kof_react, e.g. 284's slide at 11.4 px x 0.8125 down to 4.5 px a frame, up at 7, gravity 0.5) instead of the brawler's standard arc (std_flight: 2 px a frame away), for a move that chases its victim with later hits of its own. export_bm `bm_srcfly[id]` (bit k = specials[k]; the shell's slot 0; not in the pack header), fighter.c fighter_hit. Set: Kyo EX 421D |
| `together` | `["air_specials.ddA"]` (absent = none) | Bruno 2026-10-11 (note 20261011-164455-5d29): the slot labels (`air_specials.<key>` / `blitz.<k>`) of sequences (a list value) whose pieces play TOGETHER: one throw, the first piece's, every other piece's projectile spawned with its spawn, same frame (export_bm `together`; docs/brawler_gold.md "A sequence played together"). Set: Hanzo SS2 `air_specials.ddA` (A, B and A+B shurikens at once) |
| `keeps_air_attack` | `["j.4123A"]` (absent = none) | Bruno 2026-10-11: the inputs of its specials that leave it airborne with its air attack: from the program part that waits for the landing, A plays the jump's attack (down + A its down attack), once, and it lands as from a jump (`bspec_t.sflags` SF_AIRATK, fighter.c `air_free`; docs/brawler_gold.md "Engine features"). Set: Hanzo SS2 j.4123A (his air shuriken Blitz, `air_specials` `ddA` played together: its first piece; was j.4123AB, the sequence's last). An SS2 multi-button input (`j.4123S`) names each of its button versions |
| `seq_press` | `["blitz.ff"]` (absent = none) | Bruno 2026-10-11 (note 20261011-175657-5d29, Kyo's ff + A = his 236A three times): the SEQUENCES (`blitz.<k>` / `air_specials.<key>` whose value is a list) whose next piece waits for the slot's button pressed again (a Blitz / an `A` entry: A; a `C` entry: C) while the piece plays: pressed, the next piece starts at the piece's follow-up step (its source's $0080 event step, where KOF's handler switches), else at its end; not pressed, the move ends with that piece. Each piece but the last carries the press as its one follow-up link (`bslink_t`, export_bm `sequences`, fighter.c `seq_next` / `seq_wait`; docs/brawler_gold.md "A pressed sequence"). Set: Kyo `blitz.ff` [236A>156, 236A>158, 236A>162], Iori `blitz.dd` [214A>141, 214A>145, 214A>149] (127 Shiki Aoi Hana's three parts, note 20261011-210904-5d29) |
| `seq_hit` | `["specials.D"]` (absent = none) | 2026-10-14 (T6, LB2 Moriya's Ittou Shingetsu > Ittou Sougetsu): `seq_press` sequences whose next piece also needs the piece to have LANDED a hit (LB2 takes Sougetsu only after Shingetsu hit, measured in our emulator: tools/lastbld2/sougetsu_lb2_proof.py); whiffed, the move ends with the piece. Export: the piece's link `LK_IN \| LK_HIT` (fighter.c seq_wait). |
| `keeps_air_attack` | `["j.4123AB"]` (absent = none) | Bruno 2026-10-11: the inputs of its specials that leave it airborne with its air attack: from the program part that waits for the landing, A plays the jump's attack (down + A its down attack), once, and it lands as from a jump (`bspec_t.sflags` SF_AIRATK, fighter.c `air_free`; docs/brawler_gold.md "Engine features"). Set: Hanzo SS2 j.4123AB (his air shuriken Blitz, `air_specials` `ddA`). An SS2 multi-button input (`j.4123S`) names each of its button versions |
| `proj_react` | `{"6321S": {"react": "lift", "juggle_reset": true}}` (absent = none) | Note 20261015-213144-e03d (SS2 Hanzo's Bakuen Ryuu): per special input, the hit of its travelling objects (kind 1, not pinned): `react` = the victim's reaction by name (heavy, knockdown, launch, trip, blowback, slam, lift: `lift` = straight up, juggle-able), `juggle_reset` = its hit puts the victim's juggle count back to 0 (`bproj_t.ppad` bit 1, fighter.c `fighter_hit`). export_bm `proj_react`. Set: Hanzo SS2 6321S. Also since that note: `keeps_air_attack` hands the move to the jump's own controls (A its attack, down,down + A the air Blitz, fighter.c `air_free` -> S_AIR) — Hanzo SS2 63214BCD after its hit. Since its reopen (2026-10-15): `lift` lifts an airborne victim the same (straight up, its full launch, fighter.c `react`), and a `juggle_reset` object hits past the juggle cap |
| `keeps_air_attack` throws | `["throw_c"]` | Note 20261015-212313-e03d (SS2 Hanzo's leap back after his forward throw: "make him controllable, air attacks or Blitz in the air"): the throw names in `keeps_air_attack` (`throw_c` forward + A, `throw_d` back + A): past the throw's release row, in the air, A hands its thrower's leap to the jump's controls at the leap's own velocity (A its attack, down + A its down attack, down,down + A the air Blitz), landing as from a jump (build_tables -> `gthrow_air`, fighter.c `throw_air`). Set: Hanzo SS2 throw_c |
| `hit_sfx` | `{"A": "SLASH", "623B": "SLASH", "throw_c": "BACK BREAK"}` (absent = KOF's own) | TODO #75: hit sounds by use, songs.json sfx names. Keys: a normal's button (`A` `B` `C` `D` `CD`: fighter.c `hit_sound`, `bchar_t.sfx`), a throw's impacts (`throw_c` / `throw_d`), a special's KOF input (export_bm `move_fx`: the KOF98 hit kind playing that code, burn kept). Rules without data: a fury's hits play $9C SDM IMPACT; a grab or a command grab's catch $19 GRAB START. Set: Haohmaru A/B/C/CD + 421C + 623B `SLASH` ($2B; D is his kick), Krauser `throw_c` `BACK BREAK` ($3D). Kyo `21426C` / `MAX 21426C` `94 SUPER HIT` (Bruno 2026-10-09, KOF94's; was `FIRE HIT`; his fury burns by its flames' element, handlers98 `fire_element`), Terry `214C` (Burn Knuckle) `94 KNUCKLE HIT`. A special's value may be `{"states": [...], "sound": name}`: only the hits its ROM program plays in those states (Ryo / Robert `23624C` states 184 185, `MAX 23624C` 196 197: the dragon-punch end of the Ryuko Ranbu, `94 DRAGON HIT`). The KOF94 picks play alone (fighter.c HIT_SFX rows {code, 0xFF}: no fire crackle added). No guard exists in the brawler, so $17 BLOCKED HIT has no event. Proof: /data/tmp/sfx75/sfx75_proof.py A special's value may name a songs.json sfx PICK LIST (`"LB2 A8"`, 2026-10-14 T5: The Last Blade 2's hit-sound families): every hit of its program plays one of the list, drawn as LB2 draws it (export_bm step_snd, bhspark_t.smap, fighter.c step_sound); its projectiles' hits play the list's `fallback`. |
| `swing` | `"own"` (absent = the engine's whoosh) | Bruno 2026-10-14 (decisions ff-sounds H5): every attack sends KOF98's whoosh (`SWING LIGHT` / `SWING HEAVY`) as it starts, hit or whiff; `"own"` = its swings are its source's own, carried by its voice table per animation at the step the source sends them (voices.py; Final Fight: $2F on the jab, $02 / $03 on the finisher, the jump attacks' $05 / $1B / $08 / $0A), no engine whoosh (bm_hsnd key HS_SWING, fighter.c own_swing). Set: Guy, Cody, Haggar. Proof: tools/ffight/ff_proof.py (each scenario's `snd`) vs rec_ff.py's. |
| `fire` | `["214A", "214B"]` (absent = none) | TODO #163: specials (KOF inputs) whose hits burn the victim (fighter.c `set_burn`, the fighter's flame colour) though their game's hit kind is not a fire one (KOF96 sets no hit kind on the Blitz Ball object: +$1B8 = 0). export_bm `move_fx` (the body's hits and its projectiles'). Set: Krauser's Blitz Ball 214A-D (Bruno 0.0.72: "these are literally fireballs"). |
| `damage` | `3` (absent = 1) | TODO #203: the fighter's damage scale, 1-4: since revamp 2 its measured specials, furies and MAX deal their tier ("Meter, breaker, damage tiers"), the scale stays on a special not measured (its tier scale, build_tables `dtier_tables`); since revamp 1A its normals carry their own damage in their route nodes: the chain's links the archetype's total (the scale no longer applies), the jump-cancel / dash / C-without-special / air entries their damage times this scale (baked by routes.py chain_tree); a fury's hits (D / down+D), throws and hold hits keep the engine's own numbers. Set: the four Samurai Shodown II fighters at 3 (Bruno 20261007-130138-b3f3: "triple the amount of damage per hit"; SS2 measured in our emulator: a slash takes 7-20 % of the life, KOF98's normals 4-10 %, tools/samsho2/dmg203_proof.py). |
| `fury_damage_scale` | `2` (absent = 1) | Bruno's note 20261009-122307-5d29 ("double the damage of the Fury of Haohmaru"): this fighter's fury and MAX deal their tier (`tiers.fury` / `tiers.max`) times this number (0.5-4), the only per-fighter exception to the unified fury / MAX tiers; build_tables `dtier_tables` (build/dtier.json `target`). Set: Haohmaru 4 (fury 120, MAX 180 of the life of 60; 2 on 0.10.6, reopened: "still very low, double it") |
| `fury_final_area` | `{"front": 143, "back": 44, "depth": 24, "blows": "all"}` (absent = none) | note 20261009-235250-b3f3 (Iori): the fury's (and its MAX's) blow on its caught victim (a VE_BLOW of its victim lists) also hits every other opponent standing within `front` px ahead of the fighter, `back` px behind, `depth` px (1-127) either side in z, with that blow's damage, burn and release flight, sent away from him (fighter.c `fury_area`; build_tables -> `gfury_area[fighter]` [front, back, depth \| 0x80]). `blows`: `last` (default) = only the last blow, `all` (note 20261011-204335-5d29) = every blow. Set: Iori 112 / 96 / 24 (the Ya Otome's final purple blast), Rugal 143 / 44 / 24 all (the Gigantic Pressure's red column, -4..+103 px from him; the MAX raises two, the second after he turns round) |
| `special_final_area` | `{"624D": {"front": 100, "back": 40, "depth": 24}}` (absent = none) | note 20261011-230030-5d29 (Iori 624D's explosion): `fury_final_area`'s fields per special input: the last blow of that special's victim lists (`blows` "all": every blow) also hits every other opponent within the box around the fighter, with that blow's damage, burn and release flight (export_bm special_area -> the lists' end entry vx / vy, fighter.c fury_area; a MAX takes its DM's entry unless it has its own; a fury keeps `fury_final_area` first). Set: Iori 624D |
| `music` | `"THEME_ROBERT"` (absent = none) | his theme, a songs.json song: stage 1 plays it instead of the stage's own song when he is the selected fighter (P1's, P2's when alone; a P2 joining changes nothing; voice note 20261011-160158-5d29). build_tables `roster_music`, main.c `stage_song`; the Fighter Lab shows it |
| `unlock` | `"always"` or `{"boss_of_stage": 1}` | locked on the select screen until that stage's boss is beaten (save bit stage - 1); ignored while game.json has an `unlocks` block (the ladder below) |
| `voices` | absent, `"kof"` or `{"kof": true, "set": {"hit": 3, "special:236C": null}}` | absent = silent (none of its samples in the V ROM); `"kof"` = KOF's own voice on every move (the suggestion); an object = that base (`kof` false: none) with these keys changed to a voice id of its list (null: silent). Keys: every BA_* move name, `throw_c` / `throw_d`, `hit`, `ko`, `select`, `special:<input>` of its pool ("Voices" below) |
| `display` | `"BILLY LEE"` | the name shown (HUD, select) when it differs from `name` upper-cased (at most 10 characters) |
| `scale` | `1` | the fighter's size: 1 = its game's art at full size (Double Dragon's Billy Lee, 115 px, Bruno 2026-10-06; Kizuna's fighters are exported at 0.80 by their exporter); a per-fighter value so it can change later (export_dd accepts 1 today) |
| `variant` | `{"623": "A"}` (absent = the source's default, the heaviest) | the row of a special's variant table played (vocabulary `variant.table`: DD's four buttons; WHP: a button or low / mid / high), latched at the move's start |
| `form` | `{"trigger": "down+D full meter", "transition": "FORM", "target": "billy_super", "carry": ["life", "position", "facing", "meter"], "exit": "life"}` | the form link (vocabulary `form.change`): the trigger starts the transition (a special of its bank), which turns the fighter into the target roster entry; exit `life` (a lost life) or `stage` |
| `flash_pose` | `"rage"` / `"taunt"` / `"charge"` / `"win"` / `"intro"`, or `{"anim": 88, "first": 0, "last": null, "head": [x, y], "fit": false, "voice": false}` (absent = the source game's default) | TODO #145, vocabulary fx.super_flash "flash pose": what a fury from a source without a flash step (Kizuna, SS2, WHP, Double Dragon) shows during the super flash's freeze; kinds per game in export_bm FLASH_POSES (Kizuna taunt; SS2 rage (default, TODO #189: the game's own POW-full animation 140, timed to the freeze, its shout sent on its step) / taunt / win; WHP win / intro; Double Dragon charge / win; Final Fight stance (Haggar $132B0, his upright stance held still, note 20261014-171937-5d29) / kneel $13C0E); cut to the freeze (`fit`: timed to it); the glow on its head point (`head` overrides head_point.py). KOF fighters: ignored (their own flash step) |
| `fury_throw` | `{"throw": "b", "damage": 7}` (absent = none) | note 20261014-171937-5d29 (Haggar: "at the very end of everything, add the piledriver"): the fury (D, not its MAX) closes with a throw: its victim still reeling on the floor when its last piece ends is grabbed where it stands and thrown by the hold's B throw (`throws.b`, bm_xthr x: Haggar's piledriver), `damage` the throw's (the fury's tier = its pieces + this), invincible as every throw (build_tables -> `gfury_throw`, fighter.c `fury_throw`). Set: Haggar 7 |
| `hold_timeout` | `"stand"` / `"knockdown"` (absent = stand) | note 20261014-193405-5d29: what the holder's hold does when it runs out (GRAB_TIME frames without a hit): `stand` lets the victim go on its feet on the floor (it no longer keeps the hold pose's few px of height), `knockdown` = it falls on its back (the trip's fall, no damage) and gets up (Final Fight's hold break; build_tables -> `ghold_timeout`, fighter.c hold_update). Set: Haggar knockdown |
| `throw_keeps_chain` | `true` (absent = false) | Note 20261015-224938-e03d (Final Fight's quirk): when the chain's back throw (back on the chain's last press) throws its victim into another enemy (the thrown body's hit), the chain does not end: it stays one link in (the link before the one the throw came out of), so the next press within the chain window after the throw's control return is the chain's second link and the one after it the back throw again: jab, jab, throw, jab, throw (FF measured: /data/study/ffight/haggar_rethrow_trace.txt, the jab after the backdrop is A2 = 2). A back throw that hits nobody ends the chain as before (build_tables -> `gthrow_keep`, fighter.c `chain_keep`, fighter_t.tkeep). Set: Haggar |
| `clear_walk` | `{"to": "off"}` or `{"to": 280}` (absent = the win pose) | Note 20261015-224745-e03d (Final Fight tribute): at the stage clear, instead of a win pose, the fighter turns right and walks at his own walk (input held forward) to screen x `to` (160-360), then stands there; `"off"` (the reopen: "walk all the way out of the screen, like he is going to the next stage"): he walks right, the screen edges no longer holding him, until his whole picture (every part of his walk and idle frames) is past the screen, at most WIN_MAX frames. The next screen waits for him as for a pose (WIN_HOLD after he arrives; build_tables -> `gclear_walk`, CLEAR_WALK_OFF; main.c win_tick WIN_WALK). Set: Haggar "off" |
| `selectable` | `false` (absent = true) | no select slot: a form link's target (Super Billy); never picked (roster_unlock 0xFF) |
| `retime` | `{"214C": [40, 38, 40], "atk_b_far": {"scale": 0.75}, "214B": [16, 1, 8, 6, 30]}` (absent = every move at its source timing) | revamp 1C: target frames per segment of a move, played at run time ("Retiming" below); the data keeps the source timing |

Later: `palettes` (custom colour sets), `moves` (a trimmed list).

`select.slots`: `{"x": 40, "z": 48, "row": 0, "fighter": "terry"}` per slot; row 0 front, 2 back (`SEL_BACK`, the
bosses). Generated as `SEL_SLOT[]` (x int16, z, row: 4 bytes) and `sel_fighter[]` (bm_chars index, 0xFF empty).
`select_layout` (when present, it replaces `select.slots`; build_tables.py `select_layout`, the Lab's Select tab):
per fighter `x` (street px 0-767), `y`, `z`, `facing`, `pose`, `slot` (the stick's order; the cursor starts on the
first selectable slot and the camera centres it). Since note 20261011-111259-5d29: Terry is slot 0 at x 480, under
the NEO GEO LAND logo's centre (world x 365-594, camera 320), Robert and Kim either side, the street order turned to
start at him (so the loop left / right is unchanged). Since decision select-bosses (set open-2026-10-11, "Move the
locked bosses to the edges"): the locked bosses stand at the street's outermost places (Mr. Big, Krauser, Geese x 42-100;
Rugal, Goenitz x 685-714), the playable fighters fill the places around the middle three in their former loop order
(places, facings, rows and slots unchanged; each fighter keeps its pose).

**The unlock ladder** (game.json `unlocks`, Bruno 2026-10-15, decisions set unlocks: the beta build; build_tables.py
`unlocks` / `ladder_places`, main.c "the unlock ladder"; edited in the Factory's Roster & select, roster.py merge):

| field | example | meaning |
|---|---|---|
| `starters` | `["terry", "robert"]` | playable from the start |
| `rungs` | `[["haggar"], ["hanzo_ss2", "haohmaru"], ["kim"]]` | the fighters earned, a rung each game clear (the last stage in play's boss beaten), in order; each rung its own size, 1-6 (Bruno 2026-10-15; the older form `ladder` + `rung_size` cuts one list into equal rungs and is still read) |
| `screen` | `{"feet": 200, "from": 24, "to": 296, "scale": 8}` | the ladder screen's line: feet y, first / last feet x; `scale` = the fighters' size in 16ths (the hardware shrink; default from the spacing: `ladder_scale`, 4-8) |

Edited in the Factory (Characters, Roster & select: each row's Ladder picker = Start / Rung n / New rung / off, the
ladder card's rungs with up / down / remove; the draft `unlocks` {starters, rungs}, roster.py merge; proof
`tools/brawler/factory/ladder_proof.js`). While the block is there: only starters + rungs stand on the select screen (select_layout keeps only their places,
renumbered, taken in ladder order; every other roster fighter is an enemy only), a ladder fighter not unlocked yet is NOT
drawn there: n unlocked = the first n on the n middle places of the layout (`select_layers`: places (all - n) / 2 on, a
cursor graph per count, `SEL_NLAY` layers, `sel_lay_n` / `sel_lay_base`, `sel_stick` / `sel_vert` [layer]) (`roster_unlock` = $80 + its rung, 0 a starter, 0xFF off the screen; main.c `char_locked` against `save.rungs`), the
bosses' own `unlock` is ignored (no BOSS UNLOCKED). The save keeps the rungs unlocked (save_t `rungs`, the former first
spare byte: an older save reads 0). The ladder screen (mode 7): every ladder fighter at once on ONE line (`screen`: `feet` their
feet's y, `from` / `to` the first's and the last's feet x, evenly spaced between, each shrunk by the hardware to
`LAD_K` / 16 and centred on its place so none overlaps; `ladder_places`), locked ones as dark silhouettes (two tones,
every other one lighter); ONLY after a game clear that unlocked a rung (the ending's last screen), the new rung revealed
(no title entry; all unlocked: no ladder screen). Tables: `lad_fighter`, `lad_rung`, `lad_slot` (its select slot: its palettes), `lad_pos`
(screen x, feet y, draw order, face). The attract demo plays every starter / ladder fighter whatever the save. Taking
the block out: every selectable fighter from the start (the bosses' own locks back) and the select layout to be placed
again (the full one before the beta: `benched.select_layout_full`). Proof: `tools/brawler/unlock_proof.py`.

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
| Kyo dD (236D 75 Shiki Kai) | B / D pressed during the jump's rise (145), up to its apex: the second kick (148) on the rise's $0080 step or at once past it (a late press = a visible delay, up to 7 frames); none: the jump lands without it (handlers98 FOLLOW_READ, note 20261014-142848-5d29) | `again` = down + C, made in the rise or up to 6 program frames before it (P_CHECK b 3: KOF's 6-frame input path delay as a buffer) |
| K' D (236C Ein Trigger) | 6 + B -> state 134; 6 + D -> state 135 | `fA` = forward + A; `fAB` = forward + C (the token keeps the old name) |
| K' dD (623C Crow Bites) | 6 + B or D during the rise -> 146 / 147 (the same part) | `fA` or `fAB` |

`again` = the slot's own input (C + its direction). Every other slot special of the three (and their furies) has no follow-up in the
ROM (brute force in our emulator, whiff / hit / block). Proof: `tools/brawler/followups_proof.py` (game vs model,
brawler vs model, both facings), `romspecials_check.py` with `+LINK@T` cases; Kyo dD: `tools/brawler/scissor5d29_proof.py`.


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
sword, the power form. Heavies' down finisher is the slam, everyone else's the sweep; every launcher on up. Reviewed fighters' own chains
(game.json `chain` + named finishers, the chain tool's format): Krauser since revamp 3b (docs/brawler_review/krauser.md).

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

### Kim gold (2026-10-08, docs/brawler_gold.md "Kim (fast)"): the engine features it added
- `roster[].finishers` may name a LIST of moves (Kim's down: `["cmd_df_c", "cmd_df_d"]` = $4D then $57): played back to
  back, hit or not (routes.py `named`: the head node's `then` -> `rnode_t.next[RI_THEN]`, slot 8; fighter.c S_ATTACK starts
  it as the move ends); the effect on the last, the finisher's damage shared (floor, the last the rest), each the C cancels.
- A Kizuna fighter's `roster[].scale` = x its $CC size through the same LSPC path (export_kz `set_zoom`: Kim 0.92 -> $BC,
  189 / 256; every distance scaled; the source reactions stay at $CC, world motion, so Kim and Rosa share bm_sreact).
- `roster[].moves` {brawler move: "$NN"}: the move plays his Kizuna animation $NN (ROM steps, boxes, timing; travel from
  the steps' motion commands, export_kz `rom_travel`). Kim: $56 atk_b_far, $96 atk_ab_close, $98 atk_ab_far, $54
  cmd_fwd_c, $9A atk_cd_close, $6D atk_b_close (the hold hit), $59 atk_d_jump(_diag).
- `roster[].anim_specials` {"$NN": heavy | launch | knockdown | reset}: an animation as a special of the pool (one-block
  program, export_kz `anim_special`), so a Blitz / C slot can name it; `reset` = a reel in place (no slide) whose stun
  (stun_heavy 32) outlasts the move: Kim's forward + C $101 leaves him +14 frames, down + C $4D +21 (measured: victim free
  minus Kim free after the last hit), a new chain lands while the victim still reels.
- KOF96 / 98 / 99 fighters take `roster[].anim_specials` too (Krauser gold 2026-10-09: {"$A9": "knockdown"}, his
  up,up + A Blitz): $NN = the animation's state, played as a one-block ROM program (export96.anim_special,
  handlers98.anim_rom: its steps, boxes, voices as the ROM has them); how = heavy | launch | knockdown | kof (KOF's own
  box reactions); the reaction rides P_ANIM (rom_c: the rom's `react`), the knockdown on its last hit.
- `roster[].proj_hits` {special input: {max_hits, hits_per_target[, rehit][, away]}} (Krauser: `{"641236C": {"max_hits":
  10, "hits_per_target": 2}}`, his Kaiser Wave and its MAX): the PROJECTILE HIT BUDGET (docs/brawler_gold.md "Engine
  features"; export_bm.proj_hits). The special's travelling objects pierce: each enemy they cross takes hits_per_target
  (1-4) hits (the damage split over them, a reel until the last), the object frozen `rehit` frames (default
  PROJ_REHIT 7) after each hit then re-armed for the victims it is not done with, and after max_hits (1-15; 0: no cap)
  hits in all it ends there (its end rows); its victims sent away from the thrower unless `away` false. A MAX special
  takes its DM's entry unless it has its own (`"MAX 641236C"`). (bproj_t vhits bits 0-3 / 4-7, ppad; fighter_t vcnt /
  vdone / vtot; fighter.c strike.) Replaces 0.10.46's `roster[].max_hits` (the MAX's hits on each enemy, no cap).
- **Throw direction** (2026-10-11, every fighter, fighter.c `lands_behind` / `throw_start`): forward + A lands the victim
  IN FRONT, back + A (and the chain's back throw) BEHIND. The side is the throw's data: the victim's place relative to
  the thrower on its landing row (bthrow_t.land; none: its last row). A throw landing on the other side of the slot that
  plays it is played turned (its whole script mirrored), the Lab's T- pieces in the grab slots likewise. Samurai Shodown
  II's throws all land in front (its forward / back stick plays the same throw, measured in our emulator, start with the
  victim swapped behind, Hanzo's slash throw excepted): on back + A they now go over to the thrower's back. Kim's /
  Rosa's single throw (it lands behind) now lands in front on forward + A.
- `roster[].throws.back` "throw_c" (Krauser): the back throw (hold + back + A) = the C throw played turned (the victim
  over to his back at the grab); his own BT_THROW_D is left empty (bthrow_t turn, fighter.c throw_start).
- `roster[].throws.timing` {`forward` | `back` | `hold_b`: {`kind` "impact" | "slam", `damage_row`, `eject_row`?,
  `glue_row`?, `from`}} (note 20261016-045300-e03d round 2, Bruno: "throws should be case by case"): a throw's timing as
  Bruno judged it on the throw review page (brawler-lab/review.html?q=throws, data tools/brawler/throw_review.py),
  written by `tools/brawler/throw_answers.py apply` from his answers (decisions store set "throws"), never by hand. Rows
  are the throw's script rows. The whole damage lands on `damage_row` (instead of the 0.10.129 rule, fighter.c slam_row);
  an IMPACT ejects the victim at `eject_row` (default `damage_row`, not before `glue_row`): from that row it is launched
  toward the script's landing place (thrown_release); a SLAM keeps the throw_handoff rule unless `glue_row` holds the
  victim to that row (on the floor there: the landing hand-off). `hold_b` = the extra paired throw (BT_XTHROW: Haggar's
  piledriver). build_tables `throw_timing` -> `gthrow_tm[fighter][TM_*]` {dmg, hand, kind} -> fighter.c throw_start
  (fighter_t slam / eject / ejk). No entry: the rule as before.
- `roster[].throws.events` {`forward` | `back` | `hold_b`: {`impact`: N, `launch`: {`frame`: N, `dir` "up" | "away" |
  "none", `size`? "small" | "medium" | "big"}, `held`?: N, `from`}} (THE THROW REVIEW round 2, Bruno 2026-10-16 after
  0.10.142: "define WHEN THE IMPACT occurs (the visual + the sound), and separately WHEN THE ACTUAL LAUNCH occurs [...]
  Separate these concerns"; brawler-lab/review.html?q=throws2, written by `tools/brawler/throw_answers.py apply2` from
  set "throws2", never by hand). N = the throw's frame: 1 = its first frame, every game frame from its start, as the page
  numbers them (no script rows). `impact`: the spark, the sound, the screen shake and the whole damage on that one frame
  (the script's own impact rows no longer spark / sound). `launch`: the engine takes the victim over on that frame and
  sends it: up (a pop), away (along the throw's way), none (where it is: lying stays down, in the air falls), strength
  game.json `throw_launch[dir][size]` {vy, vx} (default medium). `held`: the victim follows the thrower's grip (the
  script) until that frame, then stays where it is, in its pose, until the launch (default: the launch frame). The
  thrower plays its whole animation (THE THROW'S END). Replaces `throws.timing`, `slam_bounce` and, for SS2 Hanzo's hold
  + B, `special_grab_timing` "623K" for that throw (one path; build_tables `throw_events` refuses a throw with both).
  Until fighter.c plays them (build_tables `ENGINE_PLAYS_EVENTS`), a game.json with events is refused by the build and
  apply2 runs `--dry` only, so his answers are never silently ignored. `tools/brawler/throw_regress.py` checks each throw
  with events (impact frame once, launch frame + direction, held), `--events FILE --events-only` measures a build
  against answers not applied yet.
- `roster[].throws.hold.multi` [k, ...] (Kim: `["fin"]`, note 20261009-011518-5d29): that hold hit plays every hit of
  its move (export_bm hold_rows: an impact row per active step, the tail kept to the last); the finisher's victim reels
  held at each earlier impact (damage / n each) and is knocked down only at the last (the rest: the total unchanged;
  fighter.c victim_rows / paired_update, hold_nimp / hold_last). Kim's $6E: 5 held + 5 knockdown (was 10 at the first).
- `roster[].throws.hold.victim_dx` (px, exact) / `victim_face` ("holder") (note 20261016-100931-e03d, SS2 Hanzo): the
  held victim's place in the hold instead of its forward throw's row 0 (export_bm hold_rows): Hanzo's throw starts with
  SS2's victim 15 px into him, turned away; his hold now 34 px in front, facing him.
- `roster[].throws.run` {special, frames, cost} (note 20261016-100735-e03d, SS2 Hanzo's Mozu Otoshi out of a run): a
  player's run (not a dash) of `frames` frames or more that grabs plays that grab special of its bank instead of the
  hold, for `cost` drive chunks, with the paid special's blue flash; short of the drive: the hold (build_tables
  `run_grab` -> `grun_grab[fighter]` {pool index, frames, cost}; fighter.c run_grab, fighter_t rgrab: started by the
  hold's next update). Its slam: `special_grab_timing` under the special's input (`run 623CD`).
- `referee.jump_sound` / `land_sound` (songs.json sfx names; note 20261016-101200-e03d reused): played as the referee
  leaves the ground and as he lands (main.c rf_tick, gref_t). SS2's own: sfx E8 = samsho2 `00DA` (his jump, $E668's sound
  $2B), E9 = samsho2 `1A73` (his landing voice); build_snd reads SS2's prefix $1A as slot 1.
- `slam_bounce.vx` is away from the thrower (note 20261016-095622-e03d reopen: +1.5); the slam's group impact (throw_body)
  lands on the slam frame and the bouncing victim touches nobody after it (note 20261016-111144-e03d, fighter_t.tb_slam).
- THE THROW'S END (fighter.c throw_follow, note 20261016-134631-e03d): every throw and grab special plays whole, end pose
  included; the only early exit is a follow-up that starts a move: from the throw's damage row (`throws.timing`
  damage_row, else its last impact; fighter_t.tcut) a C / D that buys a special / the fury (rule 4, buffered 24 frames),
  and after a bouncing slam a lone A press on the floor (the jab; A mashed through the throw before the slam marks it
  TB_MASHED: it plays out). The stick, B and a press that buys nothing never cut it (0.10.141: a D with no meter or a
  mashed A cut Terry's back throw). `tools/brawler/throw_regress.py`: every playable fighter x throw x pattern.
- Bonus pick: a game with `unlock` fury is greyed and skipped while the fury is free (fury_lock 0: won this credit, the
  select cheat; main.c bonus_start, note 20261016-132535-e03d); build_tables asserts a game without it exists.
- Haohmaru down + C = the A+B Senpuu Retsuzan (`236AB`) with Bakuen Ryuu's treatment (note 20261016-131850-e03d):
  `proj_react` lift + juggle_reset, `retime` startup 0.5x, `knobs` sp_dc S-003 speed 1.59 (half); 623S moved to up-forward + C.
  Round 2: the recovery 0.5x too (`retime` ["0.5x", null, "0.5x"]), down-forward + C (the 236K feint) emptied.
- Terry (note 20261016-134456-e03d): down + C = Power Wave (`EX 236C`), forward + C = Burn Knuckle (`214C`), up + C =
  Power Dunk (`623B`); C / down-forward / up-forward + C the Rising Tackle (`623C`). `roster[].specials_about`: a note.
- `roster[].special_sounds` {special input: [{sfx: songs.json sfx name, at: [program frames]}]} (note
  20261016-100735-e03d round 3): effects a special sends on its program's frames (build_tables special_sounds ->
  `gspec_snd[]`; fighter.c spec_sounds: fighter_t.srow == at). Hanzo's run Mozu Otoshi: SS2's $1A $2B rising whistle
  (songs.json sfx EA, from samsho2 1A2B) at 14 16 18 20 22 26 31 36 41 46 51 = SS2's heard frames - 1; its $1C $4E
  voice (0.10.140) dropped. tools/samsho2/mozu_run_proof.py: the 11 key-ons byte-equal to SS2's sample.
- A gauge bonus game's `pass_reward` {chunks: [per clear], text: [per chunks added]} (notes 20261016-133045 /
  -135212-e03d): a pass adds chunks[k] on the credit's (k + 1)-th pass of that game (main.c bn_clr), its result =
  text[n] alone in the big font (big_text.bonus_meter), no grade / BONUS line, the gauge bar cleared. Ki training: 2, 1.
- `meter.max_chunks` (note 20261016-152232-e03d): the drive bar's most chunks (5; a bonus reward adds up to it, the
  cheat's full bar = it; main.c MAX_CHUNKS = game_tables.h GM_MAX_CHUNKS). Each chunk is drawn as the 15-cell life bar /
  max_chunks (3 cells): five chunks span the full life bar exactly, fewer keep that size (main.c CHUNK_CELLS; build_tables
  allows 1, 3, 5, 15). bonus_proof.py: the tree's second pass from 4 gives the 5th (1 METER GAINED!), from 5 METER
  ALREADY FULL.
- Win poses 1+ (bm_wins vox): their voices now have samples in the V ROM (export_bm voice_map + WVOX; note
  20261016-133259-e03d: SS2 Haohmaru's poses 198 / 202 / 203 were silent); voices.py list haohmaru adds the shared
  effects his win animations send ($00CC $00D0 $1A $1B $1A $23). tools/samsho2/winsnd_ss2.py (SS2's per pose) /
  winsnd_proof.py (the brawler vs SS2: every sound, frame +-1, sample bytes).
- Posts bonus (BB_ANY): each hit of a move counts once on the post (the striker's hit_mask bit 7, cleared by its next hit
  window), so a two-hit move hits it twice (note 20261016-111341-e03d; was: one count per continuous touch).
- fighter.c `hits_to_come`: the step just entered that opens a hit counts until it is tested (anim_tick runs before
  combat), so a buffered press no longer cancels a multi-hit link on the frame its last hit starts ($96's third).

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

## Throws (revamp phase 3, 2026-10-08; docs/brawler_feel.md 8h, docs/brawler_revamp_plan.md 3)

Bruno's rules: no command-grab inputs, ever; each fighter has throw scripts; grab specials become throws (from the hold,
the chain or the meter super throw, case by case); with meter a throw becomes its super version; a throw is invincible
for its whole animation; a thrown body knocks others down (no chain credit).

**The hold's options** (fighter.c "hold and throws", hold_update), every fighter:

| press in the hold | plays | cost |
|---|---|---|
| A (x3) | the hold hits, the third the finisher (as before) | - |
| forward / back + A | its forward / back throw (paired scripts, as before) | - |
| up / down + A | its extra throw (`bm_xthr[id]` up / down) when it has one, else the hold hit | - |
| B, forward / back + B | its extra paired throw (`bm_xthr[id]` x) when `throws.b` is set (2026-10-14, Final Fight's Haggar: jump in the hold = the piledriver), forward / back + B carried `b.travel` px that way over its airborne rows (`bxthr_t` pad = 1 + travel / 2, travel 0-252); or `throws.extra.b` (note 20261016-043416-e03d, SS2 Hanzo's Mozu Otoshi): B alone plays that grab special as up / down + A's (pad = `XT_PAD_SPEC` 0x80 \| its index; `"throw_x"`: its paired x, no travel); else nothing | - |
| forward / back + C | the super throw: `bm_xthr[id]` sup at the super tier | `meter.super_throw` 100 (one stock); short of it the plain throw pressed, no life paid |
| C, up / down + C | the slot's special out of the hold (as before) | `meter.special` |
| D | the fury (as before) | `meter.fury` |

**game.json** `roster[].throws` (beside `speed`, `front`, `hold`): `loops` {throw: n} (note 20261006-161058-b3f3, Billy Kane: "the throw takes way too much time"): a captured throw's repeated cycle (export_bm.throw_loop: the same thrower and victim rows over and over, the source's looping state; Billy's KOF98 forward+C swings the victim on his pole 8 x 19 rows) played n times (Billy 1: thrower 134 -> 46 frames); `b` {`travel`: px} (hold + B plays its throw_x, forward / back + B carried that far, 0-508 px; Haggar 94, FF measured); `extra` {`u`, `d`}: an input of its bank (a grab special
read from the ROM) or `"throw_x"` (its extra paired throw); `super`: the same, absent = the throw pressed (forward / back)
played at the super tier. The specials named are appended to the fighter's pool when not in it (export_bm
`throw_specials`). `meter.super_throw` = its cost, `tiers.super_throw` = its damage (18, between the special 12 and the
fury 30; build_tables checks nothing more than the meter range).

**Generated**: `bm_xthr[BC_COUNT]` (bm_chars.c, `bxthr_t {x, up, down, sup, pad}`, outside bchar_t whose 128 bytes index
by a shift): `x` = its extra paired throw (`bthrow_t`, 0 none), up / down / sup = a special's index in its pool, `XT_PAIRED`
(0xFE) its `x`, `XT_FWD` (0xFD, sup only) the throw pressed, `XT_NONE` (0xFF). `gmeter.sthrow` / `sthrow_dmg`;
`dtier_rom[fighter]` gains a third tail entry: [pool..., fury, MAX, super throw] (the super special's scale = 18 / its own
measured total, looked up by input in damage_raw.json whichever role measured it; the fury's and MAX's are now looked up
by input too: Rosa's fury 421A was measured as her MAX).

**Engine** (fighter.c): a grab special as a throw = the hold lets go (the victim reels where it stood, `hold_special`, the
one path the hold's C already took) and the special starts with role `BS_THROW` (BS_COUNT + 5: index from the table, no
meter, INV_FURY to its end, no cancel out of it) or, the super throw, as a fury (`BS_FURY`, `fighter_t.sthr` 2: its super
flash / flash pose, INV_FURY, its own tier `dtier_rom[nspec + 2]`, no MAX cancel); its catch takes the reeling victim.
A paired super throw shows the super flash over the hold first (`fighter_t.xwait` = the freeze, the world stopped),
then the throw starts with `thr_dmg` = 18. The extra paired throw is `BT_XTHROW` (= BT_COUNT + 2, after the hold hits:
`thr_of`; `IS_THROW` / `IS_HOLD` tell throws from hold hits: damage, voice VK_THROW, sound SX_THROW_C, the throw-start
effect). Every throw (paired) sets INV_FURY + `cthrow` to its control return (the chain's back throw's rule, now every
throw's). A throw special's victim is a thrown body (`fighter_t.tb_by`, set at its hits) while it falls in its
knockdown until it touches the floor: the same body rule as a paired throw's release-to-landing rows (BODY_DAMAGE,
knockdown, the thrower's target = the one it hit, no chain window).

**Ralf's 426B / D** (KOF98's only command grab, /data/study/grabs/REPORT.md): decoded from KOF98's code by
tools/kof96/throwrom.py (PILOT `('kof98', 10)` key `throw_x`: the throw routine $50334, thrower $5033E states 208 / 209 /
210, victim $50410 lists $25E8C0 and $25EC50; the walk gained `cmpi` with unsigned branches, unknown base registers read
as ROM, blows of a list set after a release). 150 rows: the toss (release 38, height 324), the catch from above (row 96,
impact), the slam (second release = landing 131, impact), control return 145; damage 12 in 2 impacts; the thrown body
from the slam (row 131) to the lying state (150) (throwrom `body`). export96 merges ROM throws into a fighter's captured
ones key by key.

**Placements** (Bruno reviews each; the audit: every special whose program catches, /data/tmp/rv3/out/audit.md): Rosa
214B -> up + A, 6246A -> super (her fury -> 421A, MAX = the fury); Iori 624B -> up + A, 624D -> super (Ya Otome stays:
strikes first); Rugal 624A God Press -> up + A, 23624C Gigantic Pressure -> super (and still his fury: 3b below); Hanzo (SS2) 623K Mozu
Otoshi -> up + A and super; Cheng-Fu SUPER 623 -> super (MAX = his fury); Yamazaki 236236C Guillotine -> super (and still
his fury); Genjuro WFT -> super (and still his fury); Ralf 426B -> up + A and super. Strike rushes whose catch box only locks a
barrage stay (Ryo / Robert / K' furies, Ryo EX 646A, Robert EX 646D). Freed slots with nothing decoded left to fill
them: Iori fD + dfD, Rugal fD, Hanzo (SS2) fD, Rosa fD. Everyone else's super = its forward / back throw at 18.

Proof (our emulator, /data/tmp/rv3/out): tools/brawler/throws_rv3_proof.py (every fighter, every hold option, both
facings: what played, damage, meter, INV_FURY on every throw frame, a second enemy where the body comes down knocked
down with no chain window; sheets throws_<fighter>.png); meter_scenarios_check.py rv3-* scenarios.

**Bruno's answers (decisions set throws1, 2026-10-08; applied in 3b):** the hold mapping ships as is (up + A the extra
throw, free; forward / back + C the super throw, one stock, 18 damage). For the three fighters whose only decoded fury
was a grab he answered "none of these" with no note, so nothing is decided yet and none is left without a fury: Rugal
(23624C Gigantic Pressure), Yamazaki (236236C Guillotine) and Genjuro (WFT, his rage grab) keep that grab as their D fury
(300 meter, INV_FURY to its end like any fury, the fury tier 30) while it stays their super throw (hold + forward / back
+ C, one stock, 18). game.json flags them `roster[].fury_grab: true` (build_tables checks the fury is the super throw's
grab). **Provisional**, pending Bruno's choice (a striking super decoded from KOF98 / SS2 would replace it). On D the grab
connects as its program does: Yamazaki's and Genjuro's full 30 from 24 px on; Rugal's Gigantic Pressure lands both
crushes (30) only at some spacings (measured 90, 110, 115, 135 px; one crush = 15 at the others), and from the hold as
his super throw one crush (9 of the 18): open, to look at with his fury's choice. Proof: tools/brawler/rv3b_proof.py `furies` (/data/tmp/rv3b/out:
furies_grab.png, rv3b.json).
Results 3b (2026-10-08, our emulator, /data/tmp/rv3b/out): rv3b_proof ALL OK (Krauser's chain 10 / 10 cases, the grab
furies 6 / 6); throws_rv3_proof ALL OK (25 fighters, both facings); chain_proof all but Mr. Big's back throw (as before);
controls_proof 25 / 25; cancel_proof all but K''s fury -> MAX (as before); fury_inv_proof (AI_OFF build) ALL OK incl.
Rugal / Yamazaki / Genjuro; meter_proof ALL OK; bank_proof ALL OK; rv1a / rv3b / rv2 / rv3 scenarios as expected
(rv1a-slam and rv1a-juggle-cap moved from Krauser to Ralf: Krauser no longer slams); regress no-bleed True
(frame-exact), two runs identical; campaign29 through (stage 2's boss Krauser: one more ATTACK entry, his new tree).

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

`throw_body` (`gtbody_t`, ROM only; Bruno's note 20261014-132326-5d29, "like in Final Fight"): the thrown body, one rule
for every throw of every fighter (fighter.c combat "THROWN BODIES", build_tables `tbody_tables`). A paired throw's victim
from its release row to its landing row (inclusive), a throw special's victim while it falls, then `floor` frames once it
is on the floor (its impact: `fighter_t.tb_fl`, armed by thrown_land or the first floor frame, also past the landing row
of a throw without a hand-off, Haggar's backdrop rel = land), knocks down every other enemy it touches, each once, the
throw's way: `damage` 8, `hitstop` 6 (the hit one), `body_hitstop` 6 (the body's own, with its thrower while it still
holds it: the pair freezes), `floor` 4, `depth` 12 px, `sound` "15" (songs.json sfx code), `players` false (a thrown body
never hits a player: an enemy's victim never hits its own teammates, a boss's thrown player never hits P2). Hold hits
never make a body (Final Fight's 3rd knee drops its victim where it stands). Final Fight measured in FBNeo (Cody / Guy,
pinned bystanders: /data/tmp/body5d29): 8 + knockdown, 6 frames of freeze on the bystander and on the body, the whole
flight and the landing's first frames (the slide after does not), depth +-9; the chain finisher's and the 3rd knee's
knockdowns hit nobody. Game-wide because it is FF's single rule and Bruno's note asks for it everywhere; a per-throw
override exists for the exceptions: `roster[].throws.body` {`throw_c` | `throw_d` | `throw_x` | `special`: {any of the
fields} | false (that throw's body hits nobody)} -> `gtbody_ovr[]` (none set). Absent: the rule before the note (6, 7,
the flight only, 12 px, $15, players never).

`super_flash` (TODO #139, `gflash_t`, ROM only): fx.super_flash, the engine's rule for every fury (D) and MAX fury
(down+D): `start` 1 (the fury's frame it starts on), `freeze` 28 (frames the game freezes except the attacker and the stage
is hidden), `white` 4 (of them, frames the backdrop is `white_colour`, then `dark_colour`), `anchor` [0, -96] (px from the
feet, KOF orientation: where the concentration plays when the move has no anchor of its own). KOF98's values
(tools/kof96/handlers98.md "Super flash"). Blue for a fury, orange for a MAX fury (by role).

`max_cancel` (`gmaxcan_t`, ROM only; note 20261016-133443-e03d, KOF's Dream Cancel): a player's fury cancels into the MAX
(down + D) once one of its hits landed (`window` "hit"; "any": from its first frame), on the ground, not while it holds a
caught victim, only when that MAX could start on its own (round 2, Bruno: "meter AND life bar AND condition": fighter.c
max_ready, one rule: the fury gauge full, low life = the bar blinking red, meter.max_drive chunks; paid as the MAX; `on`
false = off). The fury's objects end and the MAX plays from its first frame as any MAX: its own super flash is the
freeze; from the cancel to that flash's end the stage is hidden behind the `backdrop` colour (black, over the flash's
white / black) with MAX CANCEL in the big font (big_text.max_cancel) and `sound` (fighter.c fury_buy / may_cancel /
fury_cancel, main.c max_cancel_fx / mc_who / mc_end). 0.10.143's freeze of its own (40 ticks before the MAX's first
frame) showed a stale normal's frame (a jab: start_special sets no frame, the program's first P_ANIM does) and is gone.
Proof: tools/brawler/maxcancel_proof.py (every fighter with a fury: the cancel's flash frames = the plain MAX's, no
cancel at normal life or on D alone).

`hit_sounds` (`ghitsnd_t`, ROM only; Bruno's impact-sound picks 2026-10-09, brawler-lab/impacts.html): songs.json sfx
names. `light` / `strong`: the hit cycles: every A / B normal's hit (a hold's or a throw's that sounds as A / B too) plays
the attacker's next `light` entry, every C / D normal's its next `strong` entry (fighter.c `btn_sound`; C+D and every
knockdown stay $15; a fighter's `hit_sfx` button or a route node's own `sound` list wins). `light` = KOF94's cycle of
three ($59FA, counter $46F8(a5) mod 3 at $594C), `strong` = KOF95's cycle of eight ($5674: $C0 $C1 $C3 $C3 $C1 $C1 $C2
$C3, counter $5E66(a5) & 7 at $5542); both games run one counter for the whole game, the brawler one per attacker
(`fighter_t.hcyc`). `guard`: the guard sound (KOF94's projectile hit; `fighter_guard_sound`, nothing calls it: no guard
yet). `boss_ko` + `scream_delay`: the boss's killing hit plays `boss_ko` (KOF94's KO blow) at once and the boss's death
voice `scream_delay` frames later (120; main.c `boss_ko_tick`; a minion fall due within KO_FIRST frames after the scream
waits for then).

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

### The boss layer (TODO T9, Bruno 2026-10-15: tougher bosses, even at LEVEL-4)

A boss enemy may carry `enemies[].boss_ai` (build_tables.py `boss_ai` -> game_tables `gbossai_rom[enemy]`, gamedata.h
`gbossai_t`; ai.c "the boss layer"), played on top of its preset (made more aggressive per boss with `ai_over`: shorter
rests, fewer blind specials / jump-ins). The beta's four (MR_BIG, KRAUSER, GEESE, RUGAL) have one, harder stage by stage.

| field | what |
|---|---|
| `guard {chance, dx, dz, hold, max, rest}` | an attack of his target starting within dx / dz (facing it): guarded `chance` / 256 times (one roll per attack), held `hold` frames at least and while the attack goes on; `max` hits blocked, the next breaks it; `rest` frames before the next guard |
| `run {chance, from, stop}` | an approach from farther than `from` px runs in (S_RUN) `chance` / 256 times, to `stop` px |
| `grab {immune, counter, delay}` | rolled each time his target comes near (again every 64 frames it stays): a walk-in grab on him does not take (`immune` / 256: he stands firm, the chain's back throw neither) or is reversed (`counter` / 256: he grabs the grabber, SoR2 style, and throws after `delay` frames) |
| `red {low, rest, dx, max}` | the red period: life <= `low` % of his full life: he blinks red (the player's MAX-ready blink) and plays his fury like a player at low life, within `dx` on his target's line, every `rest` frames (stored / 4: up to 1020), the first `max` of them as the MAX (down+D) |
| `ready_shift` | his ready wait (the Final Fight tell, `ai.rules.ready.wait`) >> this |
| `combos` | his strings, e.g. `"A A fA"`, `"A dC"`, `"run A"`, `"jump A A"`, `"grab"`, `"A A C D"`: A / C / D after an optional stick (f b u d df uf), `run` / `jump` first, `grab` last; each attack plays one not used yet this fight (a full cycle before any repeats, the last one not first again); a press goes in once the move before connected (links, the cancel rule into C / D: enemies may cancel like players now); a whiff or a hit taken ends it; a string with a D only in the red period |

The guard is an engine feature (`ai.guard {stun, push, chip}`, fighter.c "guard"): any fighter whose intent holds
`intent_t.guard` from neutral stands in BA_GUARD (KOF's standing guard, state 27; a bank without one: its idle) as
S_GUARD. Blocked (a hit from the front): no damage from a normal, `chip` / 256 of a special's / projectile's (never the
last point), a guard stun (`stun` frames sliding back `push` px), the hit-stop, the guard sound (hit_sounds.guard), the
guard spark (KOF98's small spark in blue-white, palette 247: a stand-in until KOF's own guard spark is captured); the
attacker gets the contact (chain, cancels). Beaten by: a hit from behind, a fury / MAX (unblockable), a grab or a command
grab, a thrown body, and `max` hits in one guard. The players have no guard input (the AI decides).

Proof (`tools/brawler/t9_boss_proof.py`, /data/tmp/t9): `fight BOSS --endless --sheet` per boss = the event log (strings
in order with the no-repeat check, guards, counter-grabs, red period, MAX / furies) + contact sheets; `grabs` (P1 walking
into him: held / refused / reversed); `winrate` (the scripted "decent player", one life, 8 fights a boss). Boss-only
scenarios: scenarios.json `boss-mrbig`, `boss-krauser`, `boss-geese`, `boss-rugal` (stage mode from the boss, alone,
P1 Terry 110 px away, LEVEL-4).

## Layer 3: stages

The campaign = `stages[]` in order without the ones switched off (`"off": true`; build_tables.py `campaign`, every build
reads the stages through it): the beta (Bruno 2026-10-15) plays 4, stage 2 (the garage, background 0) off.
`boss_order.bosses` (`["MR_BIG", "KRAUSER", "GEESE", "RUGAL"]`): the n-th stage in play fights the boss block (of any
stage, on or off) whose `enemy` is bosses[n] (its song, minions, drama, seed, z), at that stage's own boss `lock` / `x`
(its length); one boss a stage in play; absent: each stage its own boss. The last stage in play's boss = the game clear
(the ending, the unlock ladder). Kept out of the build but in game.json: `roster_benched` (Goenitz, Lab-only), `benched`
(his enemy, big portrait, intro drama, ending story, the full select layout), songs.json `songs_benched` (BOSS_GOENITZ,
STAGE_HIGHWAY).

| field | example | meaning |
|---|---|---|
| `name` | `"STAGE 1"` | |
| `off` | `true` (absent = in play) | out of the campaign (its data kept); the Factory's Levels shows it as "off", no number |
| `background` | `0` | stages[] of make_stage_ra.py (Robo Army's parts today) |
| `music` | `"FIGHT"` | songs.json name, started at the stage start (stage 1: the selected fighter's roster `music` first, when he has one) |
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

**The floor's back edge** (top-level `depth`, Bruno 2026-10-09, note 20261009-102742-5d29): per background (stage.h
stages[] index, `"1"`), `[[x, z], ...]` points (world x rising, z = the smallest Z a fighter may have there; straight
lines between them, the end points' Z past them), read on the art (lowest scenery pixel + 2 px). build_tables.py
`depth_tables` -> `gback_rom[background]` = one byte per 16 px column (the largest Z the lines reach in it; 0 = no
table); main.c stage_init sets `zback`, fighter.c `clamp` / `fighter_init` and ai.c `slot_goal` keep every fighter's Z
at or in front of it (players and enemies: walking, spawning, knockback, the AI's goals). Set: background 1 (stage 1).

Rules that stay in the code (main.c): the pool leaves out the players' fighters as the stage starts; the boss never
wears P1's colour set; difficulty scales life; the attract demo plays the first stage's waves on background STAGE
(make STAGE=n) with no boss, its last wave again and again, lock points clamped to that background; beaten waves'
enemies blink out; STAGE CLEAR, the save, BOSS UNLOCKED, the fade.

Today's content (written out from the 0.0.34 formulas): stage s (0-4) wave w (0-4) has min(2 + s + w, 6) spawns, spawn k:
pick 3w + k + s, set w + k, wave 0 at x 200 + 30k, later waves walking in (odd k from the left, rank k / 2), z 6 + 11k,
seed $1D2B + w + 8s; lock points w x (width - 320) / 5 (448 px on the 2560 px stages, 256 on the last); the boss at
the stage end with min(2 + s, 5) minions (pick 3k + s, not the boss, set k + s, tint 1 + (k + s) mod 3, z 6 + 13k),
seed $5B05 + s; life 100 + 4s, power stage + 1.

### Stage intro (voice note 20261014-192343-5d29, 0.10.98)

`stage_intro` (game-wide) and an optional `stages[].intro` (same keys, over it) -> `gintro[GS_COUNT]`
(build_tables.py `intro_of` / `intro_tables`; main.c "the stage intro"). Every campaign stage start (a new game, stage
2+, after a bonus game, a new game from CONTINUE on the title) plays: black, the stage's palettes + backdrop fade in over
`fade` ticks (0 = a cut) with nobody on screen and no HUD; `title` (`{name}` = the stage's name, default
"{name} START") centred on fix row 13 from `title_at` for `title_hold` ticks; at `walk_at` the players (both in 2P) walk
in from `from` px outside the `side` edge (left | right), input locked, their own `gait` (walk | run) animation and
speed, to `marks` ([[x, z] P1, [x, z] P2], x px from that edge), the HUD back; control given, `wave_delay` ticks later
the first wave spawns and the campaign (triggers, waves, the boss) runs as before. Ticks from the stage's start (60 a
second). Defaults: fade 32, title_at 16, title_hold 120, walk_at 136, side left, from 48, marks [[60, 40], [40, 10]] (the
former start places), gait walk, wave_delay 20. The attract demo and the Lab's starts (chain lab, practice, "play from
here", the bonus test) keep their immediate start. The Factory's Levels tab edits the game-wide block (row "Stage
intro"; levels.py `intro`, the marks and a stage's own `intro` stay in game.json).

### Big text (Bruno 2026-10-14: "a BIG bitmap font ... I like the one from SAVAGE REIGN")

`big_text` -> `gbig[BIG_USES]` (build_tables.py `big_tables`; main.c "big text"): which screens draw their headline in
the big font, and how. Uses: `stage_intro` (the stage intro's `title`), `stage_clear`, `game_over`, `time_over` (the
bonus break game's clock out), `bonus_won` (the bonus game's `won_text[0]`), `ladder`, `bonus_meter` (a gauge game's
pass: its `pass_reward.text`), `max_cancel` (the MAX cancel's freeze); a use left out keeps its fix-layer line, and the
detail lines stay small either way. Fields: `y` (the glyphs' top, px; the cell is 48 high), `pitch` (px between the two
lines of a text wider than 304 px, which breaks at its first double space; default 44), `text` (the uses with a text of
their own), `exit` (false: it stays after the headline's hold: GAME OVER, the ladder), `still` (true: no animation, shown
in place until its screen hides it: MAX CANCEL). `headline` -> `gbig_anim` (note 20261016-133635-e03d): THE animation of
every big message (main.c bt_draw): `slide_in` ticks in from the right, `blink` ticks of `blink_cycle` (a look a frame:
shown / hidden / white = the font's palette all white; Savage Reign's round call measured in our emulator: its own
palette and an all-white one on alternate frames while its letters fly), `hold` ticks shown, `slide_out` ticks out to the
left, then gone (16 / 30 / 120 / 16: half a second of blink, 2 s held; note 20261016-133635-e03d round 2). The font's
palette is written in vblank with the tick's sprites (main.c bt_pal_next): written at once, mid-frame, the next tick
put the colours back before a whole frame had shown white, so the white frame never really showed. bigfont_proof.py `--anim RECIPE USE` checks it frame by
frame, and on the pictures that every white tick shows its letters white. With `bonus_won`, CONGRATULATIONS! and BONUS move up to fix rows 10 / 12 and won_text[1] / [2] down
to rows 24 / 25. Every text a use can draw is checked against the font's characters (A-Z 0-9 space ! . - ' : ?) and
the 304 px width at build time (levels.py checks a title edit the same way).

The font (tools/brawler/make_bigfont.py, after staff_roll.py): Savage Reign's round call ("ROUND n", palette $BD, a
16 x 48 sprite a letter; measured in our emulator, bigfont_proof.py) has only R O U N D and the digits 1-4 (+ the small
"-FINAL-" strip, and FIGHT! as one 128 x 64 picture: no letters to cut, none of K.O. / TIME OVER / WINNER exist big).
Those 9 glyphs are kept pixel for pixel; the rest (A-Z, 0, 5-9, ! . - ' : ?) is built in their construction: fill
masks of 5 px stems / 5-row bars with the top-right and bottom-left corners cut at 45 degrees, coloured by
make_bigfont.render (Savage Reign's row gradient, left edge, top highlight, outline), which re-draws R O U N D at 96-98 %
of their pixels. 42 glyphs, 47 sprite columns, 99 tiles (12.4 KB) appended to the C ROM (24.51 -> 24.52 MB of the
32 MB package). In play a glyph column = one sprite (3 tiles), sprites 324-347 (24: the debug boxes' last half,
which wait while a message shows), palette 250; the line guard counts them on every band. Proof: bigfont_proof.py
(/data/tmp/bigfont/proof: sheet.png, Savage Reign's calls next to the brawler's headlines at 1:1; glyphs.png).

### Bonus stages (TODO T7, 2026-10-14; decision sets bonus-game + bonus-followup)

Top-level `bonus` (next to `stages`, build_tables.py `bonus_check` / `bonus_tables` -> `gbonus`, gamedata.h
`gbonus_t`, main.c "bonus stages"; analysis /data/neogeo_dict/aof/bonus.md). A bonus is a level type the engine plays
from data, the scenes are Art of Fighting 2's own sprites (tools/aof/bonus_rip.py dumps AOF2's VRAM + palette RAM in
our emulator to /data/neogeo_dict/aof/rip; tools/brawler/make_bonus.py -> build/bonus.h + 541 tiles, 67 KB of C ROM;
AOF2's screens around a game: `bonus_rip.py screens` -> make_bonus.py "screens", 193 AOF2 tiles + 157 tiles of its fix-layer
texts baked into sprites, 43 KB of C ROM; the 4 AOF2 sounds 66 816 bytes of V ROM, song $4E 579 bytes of M ROM + its samples).

| field | today | meaning |
|---|---|---|
| `after` | `[1, 3]` | stage numbers followed by the bonus pick screen (after the stage clear / BOSS UNLOCKED) |
| `intro` | `{"music": "BONUS_INTRO", "voice": "AOF2 BONUS GAME", "at": 7, "ticks": 122}` | AOF2's own BONUS GAME screen (notes 20261014-085447 / -085507-5d29): the text zooming in as AOF2's, at tick `at` its jingle ($33) + the announcer (`voice`: a songs.json sfx name, AOF2's $1C $AE), `ticks` long |
| `pick` | `{"seconds": 9, "music": "BONUS_SELECT"}` | AOF2's original SELECT BONUS GAME (its 3 pictures, title, TIME, message box and texts; song $4E): stick + A, the cursor's frame flickering as AOF2's, the general message until the stick moves or 3 s pass, then the cursor's game's; TIME `seconds` (3-9) counting down, 1 s at 0, then the cursor's game; a pick: the frame steady 1 s |
| `card` | `{"ticks": 186, "sound": "AOF2 GONG"}` | the picked game's AOF2 title card (white, its kanji + English name), the music off, the game's `voice` + `sound` (AOF2's $1A $20), `ticks` long |
| games[] `slot` / `voice` | ki 0 / `AOF2 SPIRIT CARD`, posts 2 / `AOF2 SDB CARD` | the game's AOF2 select slot (0 Spirit Training, 2 Super Death Blow: its picture, message, title card); a slot without a game (1 Strength Training) is greyed and the cursor skips it; `voice` = the announcer reading the card (AOF2's $1C $CD / $CE) |
| `fury_lock` | `true` | Fury and Fury MAX (D, down+D) locked for the players from a new credit until a game with `unlock: fury` is won; a fail keeps the lock, a continue too; the attract demo and the Lab never locked |
| `over_music` | `"BONUS_OVER"` | the result's jingle |
| games[] `kind` `gauge` | Ki training, scene `tree` | one press on a gauge sweeping 0-127 (`step` a tick, wrapping, `seconds` to press); grade = how many of `grades` it reached (AOF2 Spirit Training's table $17EF8, default row 36 68 92 108 120); `chunks[grade]` drive chunks added to both players' bars for the credit (max 4; today [0,0,0,0,0,2]: AOF2's rule, only the top grade rewards) |
| games[] `kind` `break` | Super Death Blow, scene `posts` | `count` (3) wooden posts, one at a time, in `seconds` (30; the clock holds during a super flash). `breaks_with` `any` (Bruno 2026-10-14, "bonus-pillars-normals"): any regular strike (normals, chain, specials, their objects; fighter.c `fighter_strike_box`) counts a hit each time one starts touching the post, `hp` (4) hits break it: each hit before the last shakes it and a chip flies off, the last splinters it; the fury stays locked while it plays (it is the prize). `fury` (the former rule): only the fury's / MAX's body or its objects break one (class 2), the lock lifted for the game, anything else shakes it. `lesson`: the lesson box's 3 lines (fix rows 20 / 22 / 24, the first highlighted). All broken: `unlock`; the first win shows `won_text` (3 lines: FURY UNLOCKED! PRESS D, the MAX line) under CONGRATULATIONS for `won_ticks` (480; a button ends it after half); a fail: TIME OVER, THE FURY STAYS LOCKED. Factory Levels: Posts + Hits per post. `damage_at` ([3, 6, 9], note 20261015-221208-e03d round 2): the hits taken from which the post shows AOF2's own cracked pictures 1 / 2 / 3 (make_bonus.py post 1-3, AOF2's frames 558 / 840 / 1116); today 4 posts of 12 hits. `won_by` `referee`: SS2's referee says `won_text` (top-level `referee`: mark / from / hold; `hit_text` / `fury_dx` / `fighter` / `life` = the D quirk: D while his message is held runs the fighter to fury_dx px (onto his lane) and fires his fury; as it fires the referee becomes his body, the roster fighter `fighter` (Kuroko, samsho2:kuroko; selectable false) with `life`, a victim that never acts: the whole fury lands on him as on any enemy, his own reactions and get-up, then hit_text, SS2's HORRIBLE ATMOSPHERE. (note 20261016-045652-e03d); proof referee_proof.py GAME OUT FIGHTER auto d: his hits = the same fury's on the practice dummy). Clock fairness: bonus_proof.py --sweep, 4 hits a post, every selectable fighter with A alone: 573 (Hanzo) to 833 ticks (Rugal, 13.9 s) of the 30 s |

A game already won this credit plays for its bonus figure only (the game keeps no score). The leading player plays
alone; P2 sits it out and comes back in the next stage. Editable in the Factory's Levels tab (levels.py `bonus_view` /
`bonus_merge`: after per stage, the pick clock, the lock, each game's name / AOF2 slot / song / clock / posts / top-grade chunks).
Proof: tools/brawler/bonus_screens_proof.py (AOF2 vs brawler side by side, both in our emulator: BONUS GAME, the select,
the cards; the sounds' loudness per frame), tools/brawler/bonus_proof.py (the screens' order and lengths, the pick, every grade, posts win / fail, D locked / unlocked in the next stage;
`--sweep`: every selectable fighter breaks the 3 posts with his normals inside the clock); scenarios t7-* (scenario.py
mode `bonus`, lab req 6).

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
skipped), no `portrait` (its own: `pb_of_fighter`, the game.json portrait named like the fighter; none, e.g.
Haohmaru: name plate and text only, a HUD face cannot be scaled up by the hardware), the name plate = the fighter's
name, `"lines_by": {"terry": [...], "*": [...]}` its own lines, else the "*" / `lines` ones; `"if_portrait": true`: the
scene is skipped when that fighter has no big portrait (gscene_t.flags SC_IF_PORTRAIT; such a scene may have no lines);
`gsceneby_t` {fighter, nlines, lines[3]}, gscene_t 28 bytes with `who`, `nby`, `flags`, `by*`.
**The win poses** (voice note 20261011-132148-5d29: "for fighters with multiple win poses, play a random one at the
end"): no game.json field, the source's own set: `win` (BA_WIN, also the select screen's and the ending's) and the
others the import finds, `win_2` .. `win_4` (export96: KOF98's four of the button held at the KO, KOF99's three, KOF96's
one; export_ss2 `win_anims` from SS2's class 6 win actions decoded in its code by tools/samsho2/wins_ss2.py: Haohmaru
four, Genjuro three, Hanzo three, Kuroko one; WHP / Kizuna / DD / SS4: one). They are not BA_* moves (the enum is the Lab
pack's format): `bm_wins[id]` (build/bm_wins.h `bwin_t` {n, anims, vox, fx, obj}: the other poses' animations, their
voices [pose, step, id] (voices.py's suggestion, as the `win` key gets its own), their step effects [pose, step, object]
-> obj, an effect object born as the pose enters the step: SS2 Haohmaru's thrown sword, pinned, its flight from SS2's
code; note 20261011-225104-5d29, Bruno: "Kyo / Yuri flames, Terry throwing his cap": the KOF poses' own effect objects,
pose 0 `win` included: every object the winner spawns during the pose, captured in our emulator by
tools/kof98/capture/winfx98.py -> wins[_<game>]/winfx.json, exported by export96 `win_objects` as pinned effects of the
fighter's own frames, one row a frame: Kyo A / D hand fire, Terry A / C cap, Robert B / D, Mai A, Yashiro D, Iori D,
Rugal A-C, K' A; game.json roster[].win_fx_off [pose key] leaves a pose without them, its frames not exported: Rugal
["win_4"], his D pose's two thrown objects 510 / 511 need colours his 8 palettes cannot fold (pal_pack: 12 slots, 11
without them -> packed into 8); proof tools/brawler/winfx5d29_proof.py). main.c win_tick -> fighter.c `fighter_win_pose`: pose = (game_ticks + the player's index) % its poses (no draw
from the AI's generator: a replay repeats it), played through `fighter_t.wan` (frames via frame_ovr, KOF's step clock);
a Lab pack's fighter (the shell's slot) has pose 0 only. Proof: tools/brawler/winposes_proof.py (every pose of SS2
Haohmaru / Genjuro / Hanzo, Terry, K', Geese played in stage clears, frames and timing = the ROM's tables, the sword's
89 rows = SS2's flight), tools/samsho2/wins_ss2.py check (the decode vs SS2 in our emulator: 32 / 32 win actions).
**The stage clear's win screen** (note 20261009-230403-b3f3, KOF's winner portrait): top-level `"win_drama": "stage_win"`
(build_tables `DR_WIN`, 0xFF none; "$P1" / "$P2" scenes only): main.c PH_CLEAR plays it once the win poses are done
(STAGE CLEAR erased first), then the next screen as before; `stage_win` = P1's big portrait on the right, P2's on the
left (both in play), `if_portrait`, no lines, 180 ticks each; nobody with a portrait: no drama, as before. Proof: Geese's reply with Terry, Kyo, Haohmaru in
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
(16-20 columns of 14 tiles, 8 palettes), KOF99 K' (17 columns of 14 tiles, 10 palettes: `fold` first tries to fold
palettes with the exact colours (an entry's 4th item = the pen map, `build` stores the tile recoloured), else up to
PB_MAXPAL 10: palettes 240-249, 248-249 shared with the super flash) -> /data/neogeo_dict/portraits/big_<game>_<name>.json + .png. `build` trims
empty rows / columns, stores identical tiles once after the fighters' tiles (rom_c1/c2.bin = bm_c1/c2.bin + 750 tiles,
93 KB: C ROM 15.56 MB of the 32 MB allowed) and writes build/portraits_big.h (`pbig[]`: columns, rows, palettes, the
map: palette << 24 | flip << 20 | tile). In the game: sprites 300-319 (the box viewer's, hidden meanwhile; dbg_init
gives them back), palettes 240-249, top at y 24 (its first rows under the top bar); the line guard keeps its columns.
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
- `roster[].voice_whole` = [special input, ...] (note 20261016-131850-e03d): that special's voice parts keep the source
  game's own spacing, whatever the move's clock. Its further voice (vmore [key, id, row]) becomes [key | VK_WAIT, id,
  frames] (`export_bm.voice_waits`): sent the source's frames between the two sends (voices.json uses `at`) after the
  first is sent, whatever retiming / hit-stop do and after the move ended (fighter.c `vw_n`; dropped when the fighter
  is hit or starts another special). Haohmaru's tornado (236AB, startup and recovery retimed 0.5x): $1A $90 then
  $1A $91 40 frames later, as SS2 (measured: key-ons +1 / +41 on two channels, the 1023 ms first still sounding).
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
