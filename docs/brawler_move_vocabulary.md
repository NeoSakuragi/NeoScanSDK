# Brawler move vocabulary (TODO #142, step 1)

Analysis only: no engine change. Goal (Bruno, 2026-10-06): the brawler as an engine that could cover the whole Neo Geo
repertoire, with one standardized move vocabulary, a shared projectile / effect library, one game-wide ruleset, and an
efficient review pipeline. The original game is the reference (a fidelity report per move), not the acceptance gate.

Everything below is generated or checked by `tools/brawler/convsheet.py` (one code path for every source):

    make -C examples/brawler            # build/bm_spec.c, bm_chars.c, chainlab.json
    python3 tools/brawler/convsheet.py  # -> /data/tmp/vocab/{vocab,ruleset,missing}.json + sheets/<fighter>_<input>.{json,md}
    python3 tools/brawler/convsheet.py kyo:236C iori:623D   # more sheets

It parses the exported tables back (`bm_spec.c`: bspec_t / bspec_row_t / bprim_t / bstep_t / bproj_t / bspart_t /
bslink_t; `bm_chars.c`: throws; `chainlab.json`: pools, games, voices; `game.json`: slots, fury, hit_sfx), so the counts
are what the game plays today, not what the tools intended.

## Today in numbers

Buttons (0.0.64): A attacks (normals by stick + distance), B jumps, **C plays a special, the stick picks one of six
slots** (neutral, forward, down, up, down-forward, up-forward), **D plays the fury, down+D its MAX version** (TODO #139:
`MAX <fury>` in the bank, `bchar_t.fury_max`; none: the fury); the A+B chord is retired. Slot
names in the data and below keep game.json's keys D / fD / dD / uD / dfD / ufD = C neutral / forward / down / up /
down-forward / up-forward; a follow-up link's `again` = C with the move's own direction.

128 moves are in the game (19 fighters x 6 C slots + fury, minus empty slots; Haohmaru's BUST 236D is both his up+C and
his fury): **95 played from the ROM** (KOF98 / 96 / 99 programs, `bspec_t.prog`) and **33 recorded** (a captured
per-frame script). By source: KOF98 76, KOF96 28, KOF99 7, Kizuna 6, WHP 6, SS4 5. Every SS4, WHP and Kizuna move is
recorded; so are 16 KOF moves.

## 1. The standard features

Nine families. A ROM program (`bprim_t` ops) is already a sequence of these features; a recorded move uses the
`keyframed_path` / `script_effect` / `carry` stand-ins, which the ingestion pipeline (section 5) replaces. Counts = moves
in the game using the feature (98 / 96 / 99 = KOF98 / 96 / 99, SS4, WHP, KZ = Kizuna); the move lists are in
`vocab.json`. Fighter-wide mechanisms (route nodes, throws, the walk-in hold, the meter flash) are counted in fighters.

Proposed standard parameter ranges are the ones the data uses today; types are the engine's (16.16 velocities, 0.16
friction, px boxes from the feet, frames at 60 Hz).

### animation

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `anim.play` | anim (animation id, the fighter's banks), speed (8.8 fixed, 0x40-0x400) | Plays an animation: frames with per-step durations (ticks + 1 frames), hurt box per step. | P_ANIM + banim_t/bstep_t (ROM moves); bspec_row_t.frame per row (recorded moves); rnode_t.speed (normals) | 128 (98 76 96 28 99 7 SS4 5 WHP 6 KZ 6) |
| `anim.hold_last` | anim (animation id) | The animation stays on its last step until the move code moves on. | banim_t.hold | 95 (98 62 96 26 99 7) |
| `anim.event_marker` | step (int, step index) | A step flagged as the move's event: timing point for spawns / part switches (KOF $0080). | bstep_t flags 8, PC_EVENT / PC_STEPEV, P_EVCLR | 52 (98 33 96 15 99 4) |
| `anim.no_hurt_step` | steps (step range) | Steps without a hurt box: intrinsic invulnerability of the animation (nothing to hit). | bstep_t flags bit 1 clear (combat() skips the victim) | 31 (98 26 96 5) |

### movement

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `move.velocity` | vx (px/frame 16.16, -16..16), vy (px/frame 16.16, -16..20) | Sets the body's velocity; applied each frame by move / fall. | P_SET vx/vy + P_MOVE | 78 (98 53 96 18 99 7) |
| `move.friction` | fric (0.16 multiplier, 0..1) | vx scaled each frame (decelerating rush). | P_SET fric + P_FRICMOVE, P_MUL | 33 (98 23 96 5 99 5) |
| `move.gravity` | g (px/frame^2 16.16, 0..3) | Height += vy, vy -= g each frame; lands at 0. | P_SET g + P_FALL, PC_LAND / PC_FALL | 46 (98 34 96 9 99 3) |
| `move.nudge` | dx (px, -64..64), dy (px, -64..64) | An instant displacement. | P_NUDGE; P_SET h | 10 (98 9 99 1) |
| `move.step_offset` | dx (px per step, -64..64) | A step moves the body forward as it starts (KOF $FB). | bstep_t.dx | 52 (98 37 96 8 99 7) |
| `move.keyframed_path` | rows ([(frame, x, y)], per frame) | Position per frame from a recorded script (no physics). Captures only: to be replaced by the three above. | bspec_row_t.x / .y (special_update) | 25 (98 10 96 1 SS4 3 WHP 5 KZ 6) |

### attack

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `hit.box` | box (x,y,w,h px), damage (int, 0..60), reaction (enum R_*, 8 values), fx (hit kind 0..32, sound), burn (0..2) | A live attack box; a new hit opens with damage, reaction, hit sound / burn. | bstep_t.atk + flags 1 (ROM, P_ANIM b = damage | reaction << 8, v = fx); bspec_row_t.atk / hit / dmg / fx (recorded) | 99 (98 65 96 15 99 4 SS4 4 WHP 5 KZ 6) |
| `hit.multi` | hits (int, 2..20) | Several hits in one move; same-hit steps chain one hit over several steps. | a new hit per active step (unless the step before has $4000, bstep_t flags 16); bspec_row_t.hit bit 1 | 73 (98 48 96 13 99 3 SS4 1 WHP 2 KZ 6) |
| `hit.reaction_by_height` | standing (R_*), airborne (R_*) | The victim's reaction depends on whether it is standing or juggled (KOF's reaction table by attack box). | bstep_t.hy packed standing | juggled << 4 (fighter_hit) | 57 (98 53 99 4) |
| `hit.no_stop` | - | A hit with no hit-stop for either side; the victim reels in place (barrages, KOF class 4). | bstep_t flags 128 | 6 (98 5 99 1) |
| `hit.slide` | px (int, 0..127 or none) | How far a reel slides the victim (0 = in place). | bstep_t flags 4 (no slide); bspec_row_t.vx (recorded reel slide) | 20 (98 18 99 1 96 1) |
| `hit.burn` | colour (1 purple / 2 orange) | The victim shows a burn palette until it lands. | fx bits 6-7 -> set_burn | 7 (98 4 99 3) |
| `normal.route_node` | move (BA_*), weight (light | strong), effect (none|knockdown|launch|trip|blowback), damage (int, 0..255), push (px, -128..127), speed (8.8, 0x40-0x400), links (RI_* -> node) | A normal attack as a chain-route node (data: tools/brawler/routes/<fighter>.json). | rnode_t / rt_head_t, route_tab | 19 fighters |

### defence

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `inv.fury` | - | Untouchable from the trigger to the end (hits, grabs, pushes). | INV_FURY (start_special, every fury) | 18 (98 11 96 4 99 1 SS4 1 KZ 1) |
| `inv.reversal` | frames (int, 0..nrows) | Invincible for the first N frames (up to the last hit or apex). | bspec_t.inv_rows, applied on the down+C slot only (fighter.c) | 19 (98 11 96 4 99 1 SS4 1 WHP 1 KZ 1) |

### spawn

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `spawn.projectile` | def (library id), row (frame), offset (px), react (R_*) | A travelling object with its own attack box; its hit ends it (end rows play); one at a time; clashes. | bproj_t kind 1 (proj / robj), P_SPAWN, proj_spawn | 19 (98 8 96 7 99 2 SS4 1 WHP 1) |
| `spawn.eruption` | def (library id), offset (px) | An object that stays where it spawned and plays on after its hit (pillars, Power Geyser, Round Wave). | bproj_t kind 3 not pinned | 12 (98 5 96 2 99 4 SS4 1) |
| `spawn.pinned_effect` | def (library id), until (fxoff | last row) | An effect attached to the fighter (Burn Knuckle's flame), ended by the move. | bproj_t.follow, P_FXOFF | 21 (98 12 96 7 99 2) |
| `spawn.trail` | child (library id), period (frames) | An object that leaves child objects (no box). | bproj_t.child / child_b0 / child_period | 0 |
| `spawn.loop` | from (row), wrap (1/8 px) | The object's flight repeats from a row, moving on each repeat. | bproj_t.loop / wrap_x | 15 (98 8 96 3 99 2 SS4 1 WHP 1) |
| `spawn.signal` | bits (end / hit) | The object signals its owner (end / hit) and the move branches on it. | bproj_t.sig, PC_SIG7 / SIG7C / SIG6, P_SIGCLR | 2 (96 1 99 1) |
| `spawn.script_effect` | rows (per frame) | Up to 2 effect objects placed per row from a recording. | bspec_row_t.obj[2] (recorded) | 15 (98 11 96 2 SS4 1 KZ 1) |

### branch

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `branch.on_anim_end` | - | Next phase when the animation ends. | P_BR PC_END | 95 (98 62 96 26 99 7) |
| `branch.on_event` | - | Next phase at the animation's event step. | P_BR PC_EVENT / PC_STEPEV | 49 (98 30 96 15 99 4) |
| `branch.on_land` | - | Next phase on landing / when falling starts. | P_BR PC_LAND / PC_FALL | 46 (98 34 96 9 99 3) |
| `branch.on_timer` | frames (int, 0..255) | Next phase after N frames (a counter). | P_SET cnt, P_DEC, PC_CNT | 7 (98 2 96 3 99 2) |
| `branch.on_hit` | scope (this attack | any since clear) | Branch when the move connected. | PC_HIT / PC_HITANY, P_HITCLR, P_HITOFF; bslink_t trig LK_HIT (parts) | 17 (98 11 96 3 99 1 KZ 2) |
| `branch.on_input` | input (stick + button | again), window (frames), at (now | part end), needs_hit (bool) | A follow-up: a press inside a window switches to another part. | P_CHECK / PC_LINK / PC_WINDOW / P_PART + bslink_t LK_IN (ROM), bspart_t / bslink_t (recorded) | 9 (98 4 99 3 KZ 2) |
| `branch.on_distance` | px (int, 0..400) | Branch on the opponent's distance. | PC_FAR (fighter_t.popp) | 1 (99 1) |
| `branch.on_height` | px (int, 0..255) | Branch on the body's height. | PC_LOW | 1 (98 1) |
| `branch.on_offscreen` | - | Branch when off screen. | PC_OFF | 0 |
| `branch.parts` | parts ([rows]), next (part | end) | A move made of parts that chain. | bspart_t (recorded), the program's own flow (ROM) | 19 (98 10 96 2 99 3 KZ 4) |

### hold

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `hold.catch` | box (attack box), dead (frames, 1..12), routine (phase) | A catch box: no damage, the victim is held, the move goes to its catch phase after dead frames. | bstep_t flags 64, P_ONHIT, fighter_t.pcatch / pdead | 7 (98 6 99 1) |
| `hold.place` | px (int, 0..127) | The caught victim put N px in front, facing the attacker. | P_PUT | 5 (98 4 99 1) |
| `hold.held_reel` | - | The held victim reels in place under every hit until let go. | P_HOLD / P_UNHOLD, PF_HOLD, HOLD_BOX | 3 (98 2 99 1) |
| `hold.contact_grab` | - | A reach that catches without damage; the continuation hits. | bspec_row_t.hit bit 3 (recorded) | 1 (98 1) |
| `hold.carry` | rows ((x, y) per row) | The victim is placed per row relative to the attacker (recorded cinematic). | bspec_row_t.hit bit 2 + vx / vy (recorded) | 7 (98 4 96 1 KZ 2) |
| `hold.throw_script` | rows ((thrower frame, offset, victim pose, offset, flags) per frame), speed (8.8) | A paired attacker / victim script with impacts (the walk-in throws C / D). | bthrow_t / bthrow_row_t, throw_update | 17 fighters |
| `hold.grab_hold` | hits (int, 3), time (frames, 90) | Walk into a standing enemy: hold, knee hits, throw, escape. | S_GRAB / S_GRABBED, GRAB_* (hold_update) | 17 fighters |

### variant

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `variant.parameter_set` | variants ([input -> parameter set]: light / heavy / EX / MAX), selector (button, EX flag, MAX bit) | One behaviour (the program) with parameter sets chosen by the input that started it: KOF's handler tests the button (+$1A4 bits 4-7), the EX flag (+$1D6) and a DM's MAX bit (+$E4 bit 0) and writes other speeds, timers, state / spawn tables, counts and damage ids (Double Dragon 1995: 4 per special). | decoded, not played: `handlers98.decode_variants` forks at every selector test (each other way, the tests before it kept, decoded again until no new path), `export_rom` stores every version as `rom.variants`; the game plays the slot's own button | 94 (98 61 96 26 99 7) |

Every ROM move but one has versions: 73 two, 2 three, 19 four (Goenitz 41236A/B/C/D: one handler, four buttons;
Terry 623A/C + EX 623A/C). Terry's seven: 623C = 623A / 623C / EX 623A / EX 623C (states 140-145 / 141-146 / 484-488
/ 485-489, vx 1 / 8, vy 7 / 11, g 0.32 / 0.51, rise counter 12 / 32, damage id 32 / 33); 214C = 214A / 214C (vx 7 / 9,
vy 1 / 2, damage id 26 / 27); 214D = 214B / 214D; 426B = 426B / 426D; 623D = 623B / 623D; EX 236C = EX 236A / EX 236C
(vx 4 / 7); 21416C = 21416A / 21416C (one pillar, tables $4339A / $4339E) / MAX 21416C (+$E4 bit 0: three pillars 171-173,
tables $433A2 / $433B0, count 3, damage id 39). Since TODO #139 the furies' MAX versions are also played (down+D): export96 adds `MAX <fury>`
(`export_rom` with +$E4 bit 0 set, the fury's own button: the heavy one), the rest stays decoded only.

### presentation

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `fx.backdrop` | rows (range), colours (2 x 16-bit) | The stage hidden, the backdrop alternating 2 colours. | bspec_t.bd_* (main.c screen_fx) | 1 (KZ 1) |
| `fx.voice_extra` | voices ([(id, at)]) | More than one voice line in a move. | bchar_t.vmore | 30 (98 24 96 3 KZ 3) |
| `fx.hit_sound_override` | sfx (songs.json name) | The move's hits play a chosen sound instead of KOF's kind. | game.json roster[].hit_sfx | 2 (SS4 2) |
| `fx.meter_flash` | frames (int, 8) | A special out of a hit spends double meter and flashes white. | gmeter.flash | 19 fighters |
| `fx.super_flash` | anchor (optional: dx, dy px from the feet, KOF orientation) | **Engine rule** (TODO #139, 2026-10-06), every fury (D) and MAX fury (down+D) of every fighter: from the fury's frame `start` the game freezes except the attacker for `freeze` frames (enemies, projectiles, camera, waves / timers, other players; nobody hits), the stage hidden, the backdrop white `white` frames then dark; KOF98's concentration (glow + rays, the effects library) at the anchor, blue for a fury, orange for its MAX version. Timings / colours game-wide (game.json `super_flash`: KOF98's 1 / 28 / 4); per move only the optional anchor (read from its KOF animation's `$FA` command: handlers98.md "Super flash"), else game.json's. | gflash_t (game.json super_flash), bspec_t.sf_anchor / sf_dx / sf_dy, main.c super_flash, superflash.h (make_sparks.py build_flash) | every fury (anchors: 16 KOF furies + their MAX versions) |


Notes from the inventory:
- `spawn.trail` is implemented (`bproj_t.child`) but used by **no** move in the game: Krauser's Blitz Ball and Iori's
  Yami Barai have their trail only in the captured projectile (`proj`); the ROM objects they play (`robj`) dropped it.
- `anim.no_hurt_step` (31 KOF ROM moves) is the only move-intrinsic invulnerability; `inv.reversal` is a slot rule
  (down+C only), `inv.fury` a role rule.
- `hit.reaction_by_height`, `hit.no_stop`, `hit.slide`, `hold.*` exist only for KOF ROM moves: the recorded sources
  cannot express them, which is why their gameplay differs (section 2).
- Branch conditions with one user (`branch.on_distance` K', `branch.on_height` Billy 623D) and `branch.on_offscreen`
  (0 users: objects use it internally) are kept: they are cheap and general.
- Missing from the vocabulary altogether: guard / block, armour (hit-through), a juggle counter, a wall (the super flash
  is in since TODO #139: `fx.super_flash`).

## 2. Game-wide ruleset

As the brawler implements each source today (`fighter.c` constants, `export_bm` / `export_kz` choices), the
disagreements, options, recommendation. Machine-readable: `ruleset.json`.

| rule | brawler today | per source | disagreement | options | recommendation |
|---|---|---|---|---|---|
| hit-stop | HITSTOP 7 frames, both sides, every hit (fighter_hit); projectiles fly on | **KOF98 ROM**: class table by step flags bits 4-6 ($1DCCC, 7-11 frames in KOF); brawler: 7 for all, class 4 = 0 (bstep_t 128); a catch waits 1 + the class hit-stop (P_ONHIT a); **KOF96 ROM**: same engine, table $16E20 (class 4 and 6 = 0); brawler as KOF98; **KOF99 ROM**: table $19832; brawler as KOF98; **KOF captured**: game freezes removed from the recording, brawler 7 at its own hits; **Kizuna**: freezes removed (export_kz frozen()), brawler 7; **SS4**: freezes removed, brawler 7; **WHP**: freezes removed, brawler 7 | KOF varies hit-stop by class (7-11, 0 for barrages); the brawler flattens to 7 + an exception flag; catch dead frames still follow KOF's class table | A. one value (7) + no-stop flag, catch dead frames fixed (today minus the class table)<br>B. three standard classes: none 0 / normal 7 / heavy 11 (finishers, furies, launchers), every source mapped onto them<br>C. keep each source's table | B: designers get one knob with three values; KOF classes map directly, other sources take normal / heavy by reaction |
| hitstun / reel | STUN_LIGHT 36, STUN_HEAVY 54 frames (react); special body hits add KOF98's reel 258 physics (5 frames still, slide 13.5 px x 0.828) | **KOF ROM**: kof_react R_HEAVY slide or none (bstep_t 4); **KOF captured**: slide measured per hit (bspec_row_t.vx); **Kizuna**: reel, no slide data (react_of: launch / knockdown / heavy only); **SS4**: brawler react() only; **WHP**: brawler react() only (no trip in WHP); **normals**: react(): push / 4 per node | two reel models coexist: react() for normals and non-KOF specials, react() + kof_react slide for specials | A. one reel: stun by weight (36 / 54) + slide px parameter per hit (default by weight)<br>B. KOF's reel physics for every hit<br>C. keep both | A: slide becomes a hit parameter (hit.slide), stun stays the beat 'em up length |
| reaction set | R_LIGHT, HEAVY, KNOCKDOWN, LAUNCH, TRIP, BLOWBACK, SLAM, LIFT | **KOF ROM**: reaction table by attack box, standing | juggled (handlers98.box_react) + per move ROM_REACT; default last hit knockdown, others heavy; **KOF captured**: measured on the victim (victim_reaction: heavy / knockdown / launch / trip); **Kizuna**: react_of: launch / knockdown / heavy; **SS4**: projectile knockdown; body hits: default knockdown; **WHP**: projectile heavy; no trip; **normals**: rnode weight + effect (none / knockdown / launch / trip / blowback) | how the reaction is chosen (table by box vs measured vs authored) and two physics: brawler react() vs KOF98 kof_react (specials only) | A. authored per hit from the 8 R_* values, standing / airborne pair, one physics (KOF98's, measured)<br>B. authored per hit, brawler physics<br>C. per source | A: every importer writes the pair (hit.reaction_by_height); one physics table for all hits including normals |
| juggle | falling knockdowns hittable with JUGGLE_BOX, no limit; KOF reaction physics: only launch 286 / 293 keep a hurt box (KM_HURT) | **KOF ROM / captured**: hittable only in launch states (KOF rule) after a special hit; **Kizuna / SS4 / WHP**: brawler rule: always hittable while falling, no limit; **normals**: brawler rule | unlimited juggles vs KOF's by-reaction rule; depends on which hit sent the victim up | A. by reaction: launch / lift juggleable, knockdown / blowback / slam not<br>B. unlimited + juggle counter (e.g. 3 extra hits, then fall untouchable)<br>C. unlimited (today for most) | A + a counter cap of B: readable and stops infinite loops in a 4-player brawl |
| knockdown / getup | GRAVITY_KD 0.31, DOWN_FRAMES 40, INV_GETUP 30, revive invincible 90 | **all**: same for every source; KOF-reaction falls use KOF98 gravities (kof_fall) until the floor | fall arc differs by who hit (normals: brawler gravity; specials: KOF98 per reaction) | A. KOF98 reaction arcs for all hits<br>B. brawler arcs for all<br>C. keep | A (follows the reaction rule) |
| damage scale | life 60; normals per route node; special SPECIAL_DAMAGE 8 split over its hits; throw 12; hold hits 3; splash 6; +power per stage | **KOF ROM / captured**: 8 split (KOF damage tables dropped); **Kizuna**: 8 split, except 6246A: Kizuna's life drop scaled 192 -> 60 (game_damage); **SS4 / WHP**: 8 split; **furies**: 8 split (same as a special) | a fury deals what a special deals; Kizuna's desperation move uses source damage | A. damage tiers: special 8, fury 16, throw 12, split over hits<br>B. source damage scaled to life 60<br>C. flat 8 (today) | A: designers pick a tier; sources only rank moves within a tier |
| guard / chip | none: no block state, no chip damage | **all originals**: have guard and chip; **brawler**: none for any source | none inside the brawler; every source differs from it | A. no guard (beat 'em up)<br>B. enemies guard (AI), players do not<br>C. full guard + chip for specials | B (later): needs a guard reaction in the vocabulary; A until then |
| meter | max 120, special 30, fury 60 (needs 60), +1 per 10 frames, out of a hit x2 + white flash 8 frames (players only) | **KOF**: power stocks / MAX dropped; **Kizuna**: desperation at life <= 96 dropped (421A, 6246A playable anytime); **SS4**: rage / BUST conditions dropped; **WHP**: none | source conditions (life-gated, stock) all replaced by one meter | A. one meter (today)<br>B. one meter + optional life gate per fury<br>C. per source | A |
| invincibility | fury: whole move (INV_FURY); down+C slot: inv_rows (last hit or apex); getup 30; steps without hurt box (ROM anims) | **KOF ROM**: move's own hurt-box gaps kept + slot rule; **captured (all)**: hurt box from the frame's boxes + slot rule | reversal invincibility belongs to the slot, not the move: the same move is vulnerable on another slot | A. a move property inv.reversal (frames), any slot<br>B. slot rule (today)<br>C. only the source's hurt-box gaps | A: the move carries its invincibility; the slot only picks the move |
| push / bodies | specials below 64 px push opponents to 32 px ahead (PUSH_DX); held victims share the push; normals push per node | **KOF**: push boxes and push-back not modelled (x off by up to 28 px in close proofs); **SS4**: low leap held 30 px before the body (AIR_BLOCK_Y rule); **others**: same PUSH_DX | one approximate push vs per-game push boxes | A. PUSH_DX for all (today)<br>B. a push box per fighter<br>C. none | A (keep; it is already source-independent) |
| follow-up input timing | press inside the window [lo, hi) rows or on P_CHECK frames; presses in hit-stop latched (phl) | **KOF98**: read 4 frames after the press (6 for forward+P); **KOF99**: 5 frames; **Kizuna**: windows in script rows, again = same button; **SS4 / WHP**: no follow-ups exported | input lag differs per source; KOF drops some presses right after hit-stop | A. one buffer: a press counts for 8 frames before the window opens, through hit-stop<br>B. source lag<br>C. exact window only | A: one rule, lenient, players never lose a press to hit-stop |
| projectiles | one at a time per thrower, both spent on a clash, gone off screen (-64 / 384 px), hit ends a travelling one | **all**: KOF96/98/99 rules applied to every source | none | keep | keep |

Top disagreements, in order of gameplay impact:
1. **Juggle**: KOF-source specials make the victim untouchable except in launch states; every other hit leaves it
   juggleable without limit. The same victim behaves differently depending on who hit it last.
2. **Reaction physics**: two models (brawler `react()` for normals / non-KOF specials, KOF98 `kof_react` for specials).
3. **Damage**: a fury deals what a special deals (8 split over its hits); only Kim's 6246A uses source damage.
4. **Invincibility belongs to the slot**: a move is a reversal only on down+C.
5. **Hit-stop**: KOF's 7-11 class table flattened to 7 + a no-stop flag, while catch dead frames still use KOF's classes.

## 3. Missing-features tally and debt plan

Every recorded move in the game, what retires it, and the moves off the build (#77 Kizuna fighters, #140 leftovers,
furies' super flash). Component kinds: **enh** = an existing feature extended (its users are the regression set to prove
unchanged), **new** = a library component, **analysis** = decoding work first (no engine change; the capture already
shows which existing features the move would use). Machine-readable: `missing.json` (`items`, `debt_plan`).

| move [slot] | TODO | needs | class |
|---|---|---|---|
| ralf AAAA [D] | 81 | input.sustain, decode.kof_trace | c |
| robert 426B [uD] | 83 | decode.kof_trace | a (after analysis) |
| yamazaki 214A [ufD] | 86 | decode.kof_trace | a (after analysis) |
| yamazaki 214B [fD] | - | decode.kof_trace | a (after analysis) |
| yamazaki 214C [dfD] | - | decode.kof_trace | a (after analysis) |
| yamazaki 236236C [fury] | 87 | hold.paired_script | b |
| billy CCCC [D] | 88 | input.sustain, decode.kof_trace | c |
| iori 624B [dfD] | 96 | hold.paired_script | b |
| iori 624D [fD] | 94 | hold.paired_script | b |
| iori 23624C [fury] | 98 | hold.paired_script | b |
| rugal 6426A [uD] | 116 | spawn.multihit_object | b |
| rugal 6426C [ufD] | 117 | spawn.multihit_object | b |
| rugal 624A [fD] | 115 | stage.wall, branch.on_velocity | c |
| rugal 23624C [fury] | 118 | stage.wall | c |
| goenitz 214C [dD] | 119 | anim.step_spawn | b |
| goenitz 2141236C [fury] | 120 | hold.paired_script | b |
| haohmaru 236C [D] | 121 | decode.ss4 | a (after analysis) |
| haohmaru 623B [dD] | 123 | decode.ss4 | a (after analysis) |
| haohmaru 421C [fD] | 122 | decode.ss4 | a (after analysis) |
| haohmaru BUST 236D [uD+fury] | [124, 126] | decode.ss4 | a (after analysis) |
| haohmaru BUST 623D [dfD] | 125 | decode.ss4 | a (after analysis) |
| hanzo 236A [D] | 127 | decode.whp | a (after analysis) |
| hanzo 236D [fD] | 128 | decode.whp | a (after analysis) |
| hanzo 623A [dfD] | 131 | decode.whp | a (after analysis) |
| hanzo 623B [dD] | 129 | decode.whp | a (after analysis) |
| hanzo 214C [uD] | 130 | decode.whp | a (after analysis) |
| hanzo 214D [ufD] | 132 | decode.whp | a (after analysis) |
| kim 236C [fD] | 134 | decode.kizuna | a (after analysis) |
| kim 214B [D] | 133 | decode.kizuna | a (after analysis) |
| kim [2]8C [dD] | 135 | decode.kizuna | a (after analysis) |
| kim 421A [uD] | 136 | decode.kizuna, hold.paired_script | b |
| kim 6246A [fury] | 138 | decode.kizuna, hold.paired_script | b |
| kim 236A [dfD] | 137 | decode.kizuna | a (after analysis) |
| kizuna:gozu/mezu/joker/gordon fury | 77 | hold.paired_script | off build |
| kizuna:hayate [2]8C | 77 | spawn.boomerang | off build |
| kizuna:chung fury, r_shishi 4264A / 214B | 77 | decode.kizuna | off build |
| kizuna:projectiles | 77 | decode.kizuna | off build |
| kof99:k_dash 214D / 236B / 236D / 623A / 23624C follow-ups | 140 | decode.kof_trace | off build |
| kof98:kyo 236C 6A after hit-stop | 140 | - | off build |
| kof98:kyo 21426C held C | 140 | input.sustain | off build |

| component | kind | extends (regression set size) | only blocker of (in game) | needed by |
|---|---|---|---|---|
| `decode.whp` | analysis | - (0) | 6 | hanzo 236A [D]; hanzo 236D [fD]; hanzo 623A [dfD]; hanzo 623B [dD]; hanzo 214C [uD]; hanzo 214D [ufD] |
| `hold.paired_script` | enh | hold.throw_script, hold.catch (24) | 5 | yamazaki 236236C [fury]; iori 624B [dfD]; iori 624D [fD]; iori 23624C [fury]; goenitz 2141236C [fury]; kim 421A [uD]; kim 6246A [fury]; kizuna:gozu/mezu/joker/gordon fury |
| `decode.ss4` | analysis | - (0) | 5 | haohmaru 236C [D]; haohmaru 623B [dD]; haohmaru 421C [fD]; haohmaru BUST 236D [uD+fury]; haohmaru BUST 623D [dfD] |
| `decode.kof_trace` | analysis | - (0) | 4 | ralf AAAA [D]; robert 426B [uD]; yamazaki 214A [ufD]; yamazaki 214B [fD]; yamazaki 214C [dfD]; billy CCCC [D]; kof99:k_dash 214D / 236B / 236D / 623A / 23624C follow-ups |
| `decode.kizuna` | analysis | - (0) | 4 | kim 236C [fD]; kim 214B [D]; kim [2]8C [dD]; kim 421A [uD]; kim 6246A [fury]; kim 236A [dfD]; kizuna:chung fury, r_shishi 4264A / 214B; kizuna:projectiles |
| `spawn.multihit_object` | enh | spawn.projectile, spawn.eruption (28) | 2 | rugal 6426A [uD]; rugal 6426C [ufD] |
| `stage.wall` | new | - (0) | 1 | rugal 624A [fD]; rugal 23624C [fury] |
| `anim.step_spawn` | enh | anim.event_marker, spawn.eruption (53) | 1 | goenitz 214C [dD] |
| `spawn.boomerang` | enh | spawn.projectile (19) | 1 | kizuna:hayate [2]8C |
| `input.sustain` | new | - (0) | 0 | ralf AAAA [D]; billy CCCC [D]; kof98:kyo 21426C held C |
| `branch.on_velocity` | enh | branch.on_distance, branch.on_height (2) | 0 | rugal 624A [fD] |

Debt plan (which component retires the most recorded moves first):
1. **decoders** (analysis, no engine risk): `decode.whp` 6, `decode.ss4` 5, `decode.kizuna` 4 alone (+2 with
   paired_script), `decode.kof_trace` 4. The sheets for Kim 236C and Haohmaru 421C show these moves need **no** new
   feature: Kim 236C = 4 parts + 2 input links + hits; Haohmaru 421C's leap fits `move.velocity` / `move.gravity`
   (vx 9.0, vy 6.27, g 0.47) within 0.57 px of SS4's path.
2. **`hold.paired_script`** (enh of the throw script + catch): the only blocker of 5 moves (Iori 624D / 624B / fury,
   Goenitz fury, Yamazaki fury), needed by 7 in the game + 4 Kizuna furies off the build. Regression set: 17 fighters'
   throws + the 7 catch moves (24).
3. **`spawn.multihit_object`** (enh): Rugal 6426A / C. Regression set: the 28 projectile / eruption users.
4. **`stage.wall`** (new) with `branch.on_velocity` (enh): Rugal 624A and fury.
5. **`input.sustain`** (new): Ralf AAAA, Billy CCCC (both also need a KOF trace), Kyo's held fury.
6. **`anim.step_spawn`** (enh): Goenitz 214C. Regression set: 53 event / eruption users: largest risk for one move.

## 4. Conversion sheets

`/data/tmp/vocab/sheets/<fighter>_<input>.json` + `.md`, one schema for every source (render-ready):
`source` {kind rom: `code` = per decoded op the 68000 instruction behind it (address, disassembly, the op), `model` =
handler, KOF state order, whiff / catch state runs with frame ranges, hit openings | kind capture: rows, note},
`understood` (one line per phase), `mapping` (phase -> frames -> feature + parameters), `features_used`,
`features_missing`, `ingestion` {class, features, needs [component, kind, extends, spec], regression_set}, `fidelity`
(newest proof per branch: frames KOF / brawler, frame mismatches, hits and hit-frame offsets, max x / height error,
victim error), and for ROM moves (TODO #142 review fixes, 2026-10-06):

- `source.code`: one line per instruction (a named op and the raw bit write behind it are one line); a `set` overwritten
  before any frame plays carries `note` DEAD; a `spawn` the whiff model never reaches is noted (Power Geyser C's
  `spawn 1`: a decode-time place past state 166's only event step, reading the next table word; KOF's capture and the
  model spawn one pillar, 167). `set cnt` is attributed to the counter's write (Rising Tackle $042E14), not its `subq`.
- `source.dead_stores`: field writes overwritten before anything reads them or a frame ends (the decoder's trace,
  `handlers98.dead_stores`: a call is a barrier only for the fields its code may read, `routine_reads`). The step
  mapping leaves them out and names each `set`'s instruction (`at`): Rising Tackle 623C plays vx 8 / vy 11 / g 0.51 /
  counter 32 ($042E14-$042E2A); the 623A values written first ($042DC8-$042DDE) are listed as dead.
- `branches`: the branches the decode decided from a known field: button bit (+$1A4), EX flag (+$1D6), MAX bit
  (+$E4 bit 0), facing (+$31 bit 0, the decoder's assumption), with both ways and the versions each leads to.
- `variants`: every version of the handler side by side (`handlers98.decode_variants` + `variant_summary`, the same code
  path as the export's `rom.variants`): path, states and objects of the whiff model, hit kind, whiff frames, hit
  openings, live field writes (damage id +$EF, counts / tables +$C2-$D8, speeds).
- `bit_writes` / `unexplained`: every bit write the export drops (handlers98 'flag' ops, owner-flag routines), looked up
  in `docs/kof_engine_flags.json` (the shared KOF-engine field / bit / routine table, read from the KOF98 code that reads
  each bit: meaning, effect gameplay / none, how the brawler covers it); no entry = UNEXPLAINED. Terry's seven sheets: 0
  unexplained (Burn Knuckle: +$E2 bit 2 = was hit, its flame frees itself; +$E2 bit 7 = attack boxes off after the hit
  until landing; Power Geyser: the owner flags = the opponent's proximity guard cue). Over all 95 ROM moves the
  unexplained left are +$E5 bit 2, +$E6 bit 0, +$E7 bit 5, +$11D bit 7, +$D1 bit 0 (8 writes, none in Terry's moves).

| sample | source | phases | class | fidelity (existing proofs) |
|---|---|---|---|---|
| Terry 623A Rising Tackle (KOF98 ROM, not on a slot) | handler $42D5E, 36 ops | 4: rise (vx 1, vy 7, g 0.32, nudge 8, timer 12) / friction rise until falling or timer / fall to land / landing | a | no proof of 623A; its twin 623C (same handler): 0 frame mismatches whiff + close, 7 / 7 hits one frame earlier, x within 17 px (push-back) |
| Ryo 23624C Ryuuko Ranbu fury (KOF98 catch + held victim) | handler $481C4 | 9: rush with catch box / catch -> place 70 px, held reel / 12-hit no-stop barrage / finisher 184-187 | a | 0 frame mismatches whiff (103 / 103) + close (241 / 243), 14 / 14 hits on the same frames, victim within 1.75 px x / 26 px height |
| Kim 236C (Kizuna multipart) | capture, 144 rows | 4 parts: 3 hits, again -> 2 hits, again -> 3 hits (launch), recovery | a after analysis (decode.kizuna) | parts identical to Kizuna in all 9 scenarios; hits equal except the triple chain: 8 brawler vs 9 Kizuna (hit), 2 brawler vs 1 Kizuna (whiff) |
| Haohmaru 421C (SS4 capture) | capture, 86 rows | 3: crouch / leap (fitted ballistic, 0.57 px) with 1 knockdown hit / landing | a after analysis (decode.ss4) | render check 794 / 796 frames identical; 1 hit, knockdown; no SS4 timing proof (no decoder) |

Limits of the generator: the phase split follows program order (code after an `end` joins the next phase); a ROM
excerpt is the instruction per decoded op, not the full listing (`handlers98.py CID INPUT` prints the walk); a capture's
phases are its parts, else its ground / air runs.

## 5. Ingestion pipeline (Bruno, 2026-10-06: "never 'recorded' specials in the game ever again")

For each move of a new character:
1. **Decode** its handler (KOF96/98/99: `handlers98.py`; others: the source's decoder, written once per engine). A
   capture is analysis input and the fidelity reference, never played.
2. **Classify** against the vocabulary (`convsheet.py` writes it per move, `ingestion.class`):
   - **(a) covered**: every phase maps onto existing features with parameters. Export, prove fidelity, done.
   - **(b) enhancement** of an existing feature: name the feature; its users (`ingestion.regression_set`, from
     `vocab.json`) are re-proven unchanged (romspecials_check / fury_inv_proof / kim proofs, 0 frame mismatches as
     before) in the same change.
   - **(c) new library component**: specified once (parameters, semantics, which feature family), reusable by any
     fighter; added to `COMPONENTS` and the vocabulary, then the move is (a).
   - **analysis**: the decoder cannot place something yet; the move stays out of the game until it is (a), (b) or (c).
     No recorded fallback.
3. **Prove**: fidelity vs the original (frames, hits, positions), and the regression set for (b).
4. **Tally**: an unresolved move goes into `missing.json` under the component that would retire it, so engine work
   is ordered by `debt_plan`.

**Rule: variants are latched at move start.** The weak / strong (button) variant of a move is chosen once, when the
move starts, and every phase uses it. A source handler that re-reads its variant later is a source quirk, flagged in
the conversion sheet, not reproduced. KOF94 / KOF95 do this: the variant is a bit (+$E3 bit 0) that the command
recogniser rewrites whenever any command completes, even mid-move, and handlers re-read it at each phase start
($4D22 / $5264) and in per-frame code. That gives the mid-move flip to the weak version and Kyo's KOF95 75 Shiki Kai
infinite (qcf B, 236D in the corner). KOF96/98/99 latch the button into +$1A4 at setup (study:
`/data/neogeo_dict/kof95/variant_glitch.md`, tool `tools/kof95/variant_glitch.py`).

**Rule: grabbability is computed from the victim's current state, every time.** A grab (normal throw or command grab)
asks, at the moment it tests, whether the victim is on the ground, standing (not in a hit / knockdown / lying / get-up
/ wake-up state), not held, not invulnerable and in range; never a flag latched by an earlier event. KOF94 shows why:
its catch test accepts a victim in a reaction when the victim's "stun over, throwable" bit (+$E7 bit 3, set when a
hit-stun runs out, cleared only by the reaction's end and the stand routine) is set; a grab landing in that window
(close A cancelled into Heidern's Storm Bringer) replaces the victim's routine, so the bit survives the throw and the
knockdown, and Storm Bringer catches the lying victim again and again (10 in a row, one every 154 frames; raw
Storm Bringer: no catch until the victim stands). Study `/data/neogeo_dict/kof94/otg_grab.md`, tool
`tools/kof94/otg_grab.py`.

Consequence for the 33 recorded moves in the game today: under this rule they are debt, retired by the plan above;
the decoders retire 19 of them without any engine change.

## Proposal: form change (Double Dragon 1995's transformation)

Proposal only, not built. Source study: `/data/neogeo_dict/doubledr/README.md` ("Transformation"), tool
`tools/doubledr/transform_dd.py`, proof sheets `/data/tmp/dd95/out/transform` (sequence, dragon effect, Billy vs the
transformed form side by side).

What the game does: Billy / Jimmy, powered (the power gauge has met the life bar), hold A+B+C+D on the ground: a
62-frame move (no hurt box; a hit box on both sides while the dragons spin; rise to 193 px), the palette switches at
frame 47, the character id becomes the transformed one (0 -> 1, 2 -> 3) at frame 61, he falls and lands with the new
character's own fall / landing (idle at frame 103). Position, facing, life and the powered state carry over; the form
keeps a +25 % damage bonus and a frozen meter; it lasts until the round ends (the round init sets the id back). The
transformed form is a whole other character: own 127 animations and sprites, own command list (623 / 41236 / 236 /
214, no super), own damage and defence rows, walk 2.5 px/f vs 2.25.

| feature | parameters | semantics | needs |
|---|---|---|---|
| `form.change` | trigger (input chord, e.g. A+B+C+D held; ground only), cost (meter: full, or a gate like "powered"), transition (move id), form (fighter form id), at (transition step / frame that swaps), duration (round \| frames \| until KO \| until meter empty), exit (move id or none) | The fighter switches to another form: another move set (slots + fury), sprite bank, palette, stats row; position, facing, life and meter state kept. The transition is an ordinary move (anim, boxes, `inv.fury`-style untouchable, both-side `hit.box`), its marked step does the swap. | fighter_t: a form index; bchar_t: a list of forms (each = bank, palette, move table, stats); the swap at an `anim.event_marker` step |
| `form.stats` | walk vx, jump vx, damage scale (normals, specials), defence scale, meter gain (on / off) | Per form numbers (DD: walk +11 %, normals +29 %, takes +5 %, damage +25 % while powered, no meter gain). | a stats row per form (today the fighter's numbers are global) |
| `fx.form_effect` | layer (frames: def + offset per step), palette, anchor (feet), follows (bool) | The transition's effect drawn with the body (DD: the red / blue dragon spiral = group 1 of the move's own sprite definitions, palette 128, 3 frames per step, ~136 x 160 px, rises with him). | the shared effect library (`spawn.pinned_effect` covers it: follow the fighter, ended by the move) |
| `fx.palette_cycle` | pen, colours, period | One pen cycling while in the form (DD: pen 9, 8 colours, 1 frame each: the glow outline). | palette animation per form |

Mapping onto what exists: the transition move is expressible today (`anim.play`, `move.velocity` + `move.gravity`,
`anim.no_hurt_step` for every step, `hit.box` on both sides, `spawn.pinned_effect` for the dragon, the meter cost as
the fury's). The new parts are the swap itself (a per-fighter form table and the pointer switch at the event step), the
per-form stats row, the duration / exit rule, and the export of a second bank per fighter (DD: Billy 196 frames +
the transformed set; C ROM cost to be measured before adopting it). Brawler fit: a stage-long power-up (a beat 'em up
"rage mode") rather than a per-round one; exit on duration or on meter empty, since a brawl has no rounds.
