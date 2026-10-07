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

129 moves are in the game (19 fighters x 6 C slots + fury, minus empty slots; Haohmaru's BUST 236D is both his up+C and
his fury): **95 played from the ROM** (KOF98 / 96 / 99 programs, `bspec_t.prog`) and **34 recorded** (a
per-frame script). By source: KOF98 76, KOF96 28, KOF99 7, Kizuna 6, WHP 7, SS4 5. Every SS4, WHP and Kizuna move is
recorded; so are 16 KOF moves. (2026-10-06, TODO #173: Rugal's last four recorded moves, 624A God Press, 6426A / 6426C
Kaiser Wave and the fury 23624C Gigantic Pressure, + its MAX, are read from KOF98's handlers now: 12 KOF moves recorded.)
(2026-10-07, TODO #133-#138: Kim's 214B, 236A, 236C and [2]8C are programs read from Kizuna's handlers and step commands
(export_kz KzProg); his 421A and 6246A stay recorded: their victims follow Kizuna's reaction code.)
(2026-10-07, TODO #136 / #138: 421A and 6246A are programs too, their victims moved by Kizuna's own reaction code
(`reaction.source_motion`, `hold.victim_phase`): no Kizuna move is recorded any more. 421A's last two hits in Kizuna are
its tag partner's (the relief call), which the brawler does not have.)

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
| `anim.step_spawn` | effect (library id), step (int) | **Implemented** (TODO #173): an effect object an animation step starts (KOF96/98/99's $FA record: kind, x, y; KOF98 $5D1C, routine table $36382). Two routine shapes are read: *pinned* (`bra $37494`: kept at the fighter + (x, y), freed when its step / state changes: Rugal's Kaiser Wave charge in his hand, state 246, every step of 132-134; Gigantic Pressure's push, state 250) and *once* (`bsr $36BAA; bra $36C54`: placed once, plays its animation, freed at its end + 2 frames: Rugal 236A's dust, state 247). A third shape (TODO #202, Kyo's hand fire, kinds $45-$48): `bra $3770C` -> `bra $36C12`, the *once* placement inline. KOF'S SHARED EFFECTS BANK (TODO #214): kinds whose routine draws from table 38 (every fighter's explosions, dust, smoke) play for every KOF98 fighter (`handlers98.SHARED_FX`), *once* shapes only, for the moves the roster plays (its slots and fury: export_bm.played_inputs); their frames are exported into the fighter's own frames (export96 add_frame `tab`, records `38:n`) with ABSOLUTE palettes (KOF98's palette RAM 80-127 = the palette ROM at the same index): one budget for every fighter, SFX_NPAL_MAX 8 at SFX_PAL 232 (bm_sfx_pals, a part's pal \| 0x80; draw.s), never folded by pal_pack nor flashed with the fighter; KOF's draw priority +$2C < 0 = drawn behind its owner (bproj_t back, fighter_t.zfront -1). The routines' state may come from the kind (+$C2: `addi #N`), their sounds are not exported, the screen shakes ($28-$2A) not played. Each is an effect object of its own: never the fighter's shot, never ended by P_FXOFF; in a super flash the attacker's effects born in it run (KOF98's flash priority $5001), the others stay frozen. Data-gated: `handlers98.STEP_FX` (Rugal; Kyo since TODO #202; other fighters after review). | bchar_t.pfx [special, anim, step, robj], bproj_t follow 8 (pinned for its step: fighter_t.fx_pan / fx_step), fighter.c pan_fx; handlers98.step_effects / fx_routine; proof romspecials_check rugal:uD / ufD / D objects (spawn and end frames = KOF's) | Rugal 236A, 6426A, 6426C, 23624C (+ MAX); Kyo 236C, EX 236A, 21426C (+ MAX); the shared bank (TODO #214): Iori 624D / 624B (the release's explosion, states 35 / 36 / 65-67), Rugal 624A (the slam, state 2), Ralf [2]8A / [2]8C (23 / 24 / 59 / 60), Ralf [4]6B / [4]6D and Terry's fury 21416C (34) |
| `anim.no_hurt_step` | steps (step range) | Steps without a hurt box: intrinsic invulnerability of the animation (nothing to hit). | bstep_t flags bit 1 clear (combat() skips the victim). Found (TODO #202, not changed): a ROM special's program steps are not what combat() reads (fighter_step: the animation played before the special), so their gaps do not protect (Kyo's EX 421D hit at frames 2-9 on 0.1.9) | 31 (98 26 96 5) |

### movement

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `move.velocity` | vx (px/frame 16.16, -16..16), vy (px/frame 16.16, -16..20) | Sets the body's velocity; applied each frame by move / fall. | P_SET vx/vy + P_MOVE | 78 (98 53 96 18 99 7) |
| `move.friction` | fric (0.16 multiplier, 0..1) | vx scaled each frame (decelerating rush). | P_SET fric + P_FRICMOVE, P_MUL | 33 (98 23 96 5 99 5) |
| `move.gravity` | g (px/frame^2 16.16, 0..3) | Height += vy, vy -= g each frame; lands at 0. | P_SET g + P_FALL, PC_LAND / PC_FALL | 46 (98 34 96 9 99 3) |
| `air.special` | input (an input of the fighter's bank read from the ROM; game.json roster[].air_special) | **Implemented** (TODO #200, Kizuna's j.2B): a special its source plays from a jump: down+A in a jump plays it in the air normal's place (no meter, no cancels out of it), its program from the press frame (SF_NOW) at the height the jump had; Kim's j.2B = a 45-degree dive (velocity (6, -6) x 0.80, no gravity) until the floor, a hit moves the animation on (the blue effect at his feet, a new hit every 4 steps, a frame in place after each hit-stop), down+A again after a hit at 64 px or more = the second kick (knockdown), then the landing (91). In the air its body and a standing opponent ahead share the push (SF_SHARE). TODO #211, SS2 Hanzo's j.4123S (4 1 2 3 + S in a jump): he hangs in the air (287, 249), throws the shuriken at 249's step 1, hops back and up (vx -1.19, vy 3.1 px, his own gravity 0.30) and lands (3); the shuriken = an **air projectile** (bproj_t air: its rows' heights from his height at the throw, 0.75 px forward / 3.75-4.3 px down a frame with SS2's acceleration, the light reel on a hit; the frame after it reaches the floor its next phase: stuck in the floor 62 frames, shown 4 then every other frame); one projectile at a time (else the air normal). | bchar_t.air_spec, role BS_AIR (fighter.c S_AIR, spec_ix, may_cancel), export_kz AIR (a program: P_SET vx / vy / g, P_MOVE, P_FALL, PC_LAND, PC_HIT, PC_HITANY, PC_LOW, PC_LINK), handlers_ss2 han_j4123s / shuriken (fighter.c proj_start / proj_row / proj_update: bproj_t air); proofs tools/kizuna/kim200_proof.py, tools/samsho2/hanzo211_proof.py | Kim j.2B, Hanzo SS2 j.4123S |
| `attack.down` | input (an input of the fighter's bank read from the ROM; game.json roster[].down_attack), flight (2^a frames) | **Implemented** (TODO #218, Double Dragon's 8 / 2 + a button, every DD fighter's anim 124 > 125, step handler 28 $23012): an attack on an opponent lying on the floor. Up / down + A on the ground with an opponent lying (S_DOWN, alive) within DOWN_REACH (160 px x, any depth) plays it AT that opponent (fighter_t.dtgt): its program's P_HOME aims the leap (vx = the distance >> a, DD's << 10 = 64 frames whatever the distance, the fighter turned to face it; vz its depth >> a: the band), PC_TDOWN ends it when the target no longer lies (DD: the opponent's dizzy flag gone -> the fall), its hit reaches the lying target only (LIE_BOX: DD tests the victim's first record whatever its type, +$F3 bit 7) and pops it off the floor (DD's 119: 2 px a frame away, 4 up, gravity 0.375, friction >> 5; then the brawler's bounce and get-up); the target stays down while the attack comes (dpin, at most DOWN_PIN 96 frames past DOWN_FRAMES: DD's victim lies dizzy 96-160 frames). No meter, no cancels. DD lets it fire only at a DIZZY opponent lying in 71-74; the brawler at any lying one. Its afterimages (DD: every 4th frame by the object's own counter +$3B) are the program's ghost objects. | bchar_t.down_spec, role BS_DOWNATK (fighter.c spec_ix, may_cancel, S_IDLE / S_WALK / S_RUN A, combat, react, fighter_hit), intent_t.lie (main.c close_marks), P_HOME, PC_TDOWN, fighter_t.dtgt / dpin; export_dd program (handler 28: the flight per frame from model_dd); proof tools/doubledr/cf218_proof.py | Cheng Fu (DD 8/2 + button); every DD fighter has one (Billy Lee, Super Billy: not set) |
| `move.nudge` | dx (px, -64..64), dy (px, -64..64) | An instant displacement. | P_NUDGE; P_SET h | 10 (98 9 99 1) |
| `move.step_offset` | dx (px per step, -64..64) | A step moves the body forward as it starts (KOF $FB). | bstep_t.dx | 52 (98 37 96 8 99 7) |
| `stage.wall` | edge (px, 40) | **Engine rule** (Bruno 2026-10-06, TODO #173: "as soon as we're on the edge, actually push the character on the wall, and we should be able to actually see the victim being pushed on the wall"), every special, every fury, every fighter: the screen's edges are walls `WALL_EDGE` = 40 px in (a pinned victim's whole body shows). From a special's hit (its body's or its projectile's) until its victim is down, the victim stays inside the walls: a reel's slide, a blowback, a carry or a catch's placement that would take it out stops at the wall (KOF's corner); while the special plays, its attacker is held back by what its reeling target was held back (a rush / a push stops at the victim pinned on the wall; a launched victim's flight moves nobody); a fury's attacker also stays inside the walls itself (its dance), a special's is not snapped in from the players' 16 px margin. A catch that grinds its victim to the stage wall in KOF (KOF98 $18092: x <= 32 / >= 736 of the 768 px stage, Rugal's God Press and Gigantic Pressure) tests these walls (PC_WALL), so its push ends at the screen edge (KOF's push length follows the distance to its wall: the proof places KOF's fighter as far from its wall as the brawler's). The fury's dance wall (`hold.dance` (c)) is this rule. **A victim list at the wall** (TODO #216, KOF98 `$255B0`, the end of every list place `$25372`): an entry that would put the caught victim at or past a wall moves the ATTACKER instead, to the wall minus the list's farthest offset on that side, and places the victim again from there: every entry then fits inside, the farthest on the wall (Rugal's God Press: he stops at the wall, steps back the slam list's reach, KOF 736 -> 644; the burst at +104 shows on screen). | fighter.c wall_update (after main.c camera and again after combat), fighter_t.wall_by (fighter_hit), wall_lo / wall_hi, PC_WALL, vlist_wall; proof tools/brawler/rugal173_proof.py wall (Rugal 624A, Terry 214C, Billy 426C at both edges) | every special |
| `stage.boss_death` | slow (frames, 300), rate (1 in 3), first / gap (frames, 45 / 40) | **Engine rule** (Bruno 2026-10-06, TODO #172: "as soon as he is being hit, that's the end ... we stop the control of the player, we enter slow motion for five seconds, the boss screams, and everybody else falls and dies, like in traditional beat'em all games"), every stage's boss: the tick the boss's life runs out (any hit, throw impact or projectile) the fight is over. Every intent is off from then on (players and enemies act no more; an attack in progress plays out; the players untouchable; no P2 join, no trigger, queued spawns dropped). Slow motion: the game logic runs one tick in `KO_RATE` (3) frames for `KO_SLOW` (300 = 5 s) frames, the music, voices and drawing at full rate. The boss's death voice (his voice table's VK_KO) on the killing hit's frame; then every enemy still up is knocked down with no life left, one every `KO_GAP` frames from `KO_FIRST`, each with its own death voice as it falls (staggered, never a chorus; no second one at its S_DEAD: `fighter_t.ko_voice`). At 300 frames full rate again (anyone still up goes down), PH_END: the bodies blink out, then STAGE CLEAR and the save as before. | main.c boss_ko_start / boss_ko_tick / ko_fall (game_tick: detection after combat, the slowed logic), campaign PH_BOSS; proof tools/brawler/boss172_proof.py | every boss |
| `move.keyframed_path` | rows ([(frame, x, y)], per frame) | Position per frame from a recorded script (no physics). Captures only: to be replaced by the three above. | bspec_row_t.x / .y (special_update) | 25 (98 10 96 1 SS4 3 WHP 5 KZ 6) |

### attack

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `hit.box` | box (x,y,w,h px), damage (int, 0..60), reaction (enum R_*, 8 values), fx (hit kind 0..32, sound), burn (0..2) | A live attack box; a new hit opens with damage, reaction, hit sound / burn. | bstep_t.atk + flags 1 (ROM, P_ANIM b = damage | reaction << 8, v = fx); bspec_row_t.atk / hit / dmg / fx (recorded) | 99 (98 65 96 15 99 4 SS4 4 WHP 5 KZ 6) |
| `hit.multi` | hits (int, 2..20) | Several hits in one move; same-hit steps chain one hit over several steps. | a new hit per active step (unless the step before has $4000, bstep_t flags 16); bspec_row_t.hit bit 1 | 73 (98 48 96 13 99 3 SS4 1 WHP 2 KZ 6) |
| `hit.reaction_by_height` | standing (R_*), airborne (R_*) | The victim's reaction depends on whether it is standing or juggled (KOF's reaction table by attack box). | bstep_t.hy packed standing | juggled << 4 (fighter_hit) | 57 (98 53 99 4) |
| `hit.no_stop` | - | A hit with no hit-stop for either side; the victim reels in place (barrages, KOF class 4). | bstep_t flags 128 | 6 (98 5 99 1) |
| `hit.slide` | px (int, 0..127 or none) | How far a reel slides the victim (0 = in place). | bstep_t flags 4 (no slide); bspec_row_t.vx (recorded reel slide) | 20 (98 18 99 1 96 1) |
| `reaction.source_motion` | per hit window: standing / airborne reaction (a table entry: slide vx / ax and its frames, flight vx / vy / gravity, landing pause, bounce vx / vy / gravity, posture R_*, hittable in flight) | **Implemented** (TODO #136 / #138, Kizuna): the victim of a source's hit moves as the source's own reaction code moves it, not by KOF98's reaction: Kizuna's hit ($2D4F2) picks the victim's reaction from the attack box's type (`$5FBEE` by type and standing / airborne -> the victim's group-4 handler -> its state -> its reaction animation), that animation's step commands are the motion (a reel slides while it plays, a flight to a floor-wait step, the stop's pause, a 0-tick bounce, lying); the victim stands still the frame after the hit-stop, and so does the attacker (Kizuna's physics skip it); juggle rule = its flight steps carry boxes (32 / 33 / 9B yes, 2C no). Decoded from the code, checked on 48 measured hits (all as decoded). | bm_sreact (bsreact_t, one table), bstep_t.hy under bspec_t.sflags SF_SREACT, fighter.c src_react / src_fall, fighter_t.ksr / ksn / kax / pstill; export_kz.sr_anim / sr_motion / sr_pair / sr_mark; proof tools/kizuna/kim136_proof.py | KZ 7 (Kim's 214B, 236A, 236C, [2]8C, j.2B, 421A, 6246A) |
| `hit.burn` | colour (1 purple / 2 orange) | The victim shows a burn palette until it lands. | fx bits 6-7 -> set_burn | 7 (98 4 99 3) |
| `hit.crowd` | - | **Engine rule** (Bruno 2026-10-06, 0.0.67): an attack instance (a special's / fury's own attack boxes, an eruption, an effect object) hits EACH target at most once per hit window, and EVERY target its boxes touch (a hit mask over the entities, `fighter_t.hit_mask`, cleared when a new hit window opens; a projectile's for its life). A travelling projectile (`spawn.projectile`, kind 1) still ends on its first hit (a fireball); every other kind plays on. An eruption that hit keeps its attack box but its clash box is spent, as KOF's (`pend` 3). One victim: KOF's hits unchanged (romspecials_check). | fighter.c combat (hit_mask), proj_crowd | every special, every eruption |
| `normal.route_node` | move (BA_*), weight (light | strong), effect (none|knockdown|launch|trip|blowback), damage (int, 0..255), push (px, -128..127), speed (8.8, 0x40-0x400), links (RI_* -> node) | A normal attack as a chain-route node (data: tools/brawler/routes/<fighter>.json). | rnode_t / rt_head_t, route_tab | 19 fighters |

### defence

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `inv.fury` | - | Untouchable from the trigger to the end (hits, grabs, pushes). | INV_FURY (start_special, every fury) | 19 (98 11 96 4 99 1 SS4 1 KZ 1 WHP 1) |
| `inv.move` | input (a special of the roster entry: game.json roster[].invincible) | **Implemented** (TODO #202, Bruno 2026-10-07 on Kyo's EX 421D: "just make it invincible"): the fury's rule for a chosen move, untouchable from its first frame to its end, whatever its source's hurt boxes. | bspec_t.sflags SF_INV -> INV_FURY (start_special, held in fighter_update); proof tools/brawler/kyo202_proof.py inv | Kyo EX 421D |
| `hold.dance` | - | **Engine rule** (Bruno 2026-10-06, 0.0.67), every fury: a fighter a fury hits is its dance victim (`fighter_t.dance`). While the fury plays: (a) the victim stays in its reel (no recovery, no special out of the hit) and does not fall when its life runs out: a hit whose reaction is a reel keeps it up, the knockdown / launch comes only with a hit that has one (the finisher); a fury holding its caught victim (`hold.held_reel`) holds the whole crowd it hits (every hit a reel in place, its caught target kept); when the fury ends, a victim still reeling with no life left falls; (c) from the first hit until the victim is down, the victim and the fury stay on screen: the screen edge is a wall (`stage.wall`: `WALL_EDGE` 40 px in, the whole body shows), the attacker held back by what its reeling target was held back (it stops advancing), a launched victim's flight moves nobody. Chosen over a camera that follows: the campaign locks the camera in the waves. (d) (TODO #150, feedback 20261006-160204-b3f3) the dance is checked before the juggle: a fury's reel hit on an airborne victim catches it (the hit's standing reaction, not its juggled one): its flight stops (vx 0), it drops to the floor at twice the knockdown gravity (`DANCE_DROP`, a few frames) in its reel, and the dance goes on as on a ground victim (every later hit lands, only the finisher knocks it down). A dead body (life out, in its KO flight or down) is never hit again by anything (KOF's way: no target, no grab, not a ROM special's nearest opponent): only the fury still dancing it hits it on (its reel with no life left, felled by the finisher). | fighter.c dancing / wall_update (after main.c camera), react (the catch), dead_body (combat); proof tools/brawler/dance150_proof.py | every fury |
| `fx.death_voice` | - | **Engine rule** (Bruno 2026-10-06, 0.0.67): the KO voice plays once per death, when the fighter dies (enters S_DEAD: it lies dead and blinks out, or a player loses a life), never on the hits: a hit plays the hit voice only while the victim has life left (a dance that kills mid-sequence used to repeat the KO voice on every later hit). | fighter.c (S_DOWN -> S_DEAD, fighter_hit, throw impacts) | every fighter |
| `inv.reversal` | frames (int, 0..nrows) | Invincible for the first N frames (up to the last hit or apex). | bspec_t.inv_rows, applied on the down+C slot only (fighter.c) | 19 (98 11 96 4 99 1 SS4 1 WHP 1 KZ 1) |

### spawn

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `spawn.projectile` | def (library id), row (frame), offset (px), react (R_*) | A travelling object with its own attack box; its hit ends it (end rows play, where the hit was: at its place and height, bpend_t x / y from the impact's: TODO #164, Krauser's Kaiser Wave and Blitz Ball, K''s shot read from the ROM drew theirs on the floor; tools/brawler/impact164.py lists every projectile's); one at a time; clashes. | bproj_t kind 1 (proj / robj), P_SPAWN, proj_spawn | 19 (98 8 96 7 99 2 SS4 1 WHP 1) |
| `spawn.eruption` | def (library id), offset (px) | An object that stays where it spawned and plays on after its hit (pillars, Power Geyser, Round Wave). Crowd rule (`hit.crowd`, 0.0.67): it hits every target its box touches, each once; KOF's 1v1 (spent after its first hit) is the one-victim case of it. | bproj_t kind 3 not pinned | 12 (98 5 96 2 99 4 SS4 1) |
| `spawn.pinned_effect` | def (library id), until (fxoff | last row) | An effect attached to the fighter (Burn Knuckle's flame), ended by the move. A ROM object that never reads its owner's +$D1 bit 7 plays on through P_FXOFF (follow bit 32: Kyo's Orochinagi flame, its own end or its owner hit); one that reads it and then plays an end animation plays that in place (follow bit 64: Orochinagi's glow 243 -> 244) (TODO #202). | bproj_t.follow, P_FXOFF (fighter.c prog_fxoff); a script special's (follow bit 4, TODO #144): its rows run with the thrower's script rows (frozen with its hit-stop), ended when the special leaves them (export_kz.effects; proof tools/kizuna/kim_effects_check.py vs Kizuna's screen, kim144_proof.py) | 21 (98 12 96 7 99 2) + KZ 5 (Kim: Hienzan pillar, 214B / 236A ADH EFFE, 421A afterimages, Phoenix feathers) |
| `spawn.boomerang` | speed (px / frame), range / catch (px from the thrower), hover / held (frames), pole (segments, gap, min) | An object that flies out to `range` px from its thrower (or stops at its first hit / clash, its attack then spent), hovers, flies back at the same speed and is caught `catch` px from him: the catch signals the thrower (its program waits on it: PC_SIG7C), it stays `held` frames, then ends; it ends with the special (proj[], no off-screen end). Its hit rule is its rows' boxes: SS2's flag (TODO #176, Kuroko 6 3 2 1 4 A, object 27 $4C274) hits only on its way out (its animation holds a box-less step from its 16th frame, its attack spent by its first hit) [meas: tools/samsho2/boomerang_ss2.py, P2 in its return path not hit]. Optional pole segments placed behind it (SS2's effect objects 40). | bproj_t kind 4 (wrap_x = speed, brange, bcatch, bhover, bheld, bseg / bgap / bsegmin, child = the segment, kind 5), fighter.c boom_update / boom_segs, proof tools/samsho2/kuroko176_proof.py | 1 (SS2 1) |
| `spawn.trail` | child (library id), period (frames) | An object that leaves child objects (no box). Also an object that spawns a copy of itself at its event step (TODO #202: Kyo's MAX Orochinagi, 3 flames 16 px apart, each with its own boxes; a child of its own; handlers98.obj_chain), which keeps spawning after its hit (an eruption). | bproj_t.child / child_b0 / child_period | 0 + Kyo's MAX flames |
| `spawn.loop` | from (row), wrap (1/8 px) | The object's flight repeats from a row, moving on each repeat. | bproj_t.loop / wrap_x | 15 (98 8 96 3 99 2 SS4 1 WHP 1) |
| `spawn.signal` | bits (end / hit) | The object signals its owner (end / hit) and the move branches on it. | bproj_t.sig, PC_SIG7 / SIG7C / SIG6, P_SIGCLR | 2 (96 1 99 1) |
| `spawn.body` | rel / land (rows), damage (6) | **Engine rule** (TODO #146, Final Fight / Streets of Rage 2): a thrown victim, from its release to its landing, is an attack (its body, BODY_BOX): every other enemy it touches is knocked down the throw's way, each once (depth check |dZ| <= 12); the thrown victim takes its landing as an impact. | bthrow_t.rel / land, combat() "thrown bodies", fighter_t.thr / hit_mask | every throw |
| `spawn.script_effect` | rows (per frame) | Up to 2 effect objects placed per row from a recording. | bspec_row_t.obj[2] (recorded) | 15 (98 11 96 2 SS4 1 KZ 1) |
| `object.phase` | next (the object it becomes), hits (int, 1..8), stop (frames), re-arm rows, at (signal / hit) | (TODO #173: `at` hit, bproj_t hitnext: the phase it becomes at its hit, where it is, frozen `stop` frames, then re-armed: Rugal's Kaiser Wave, KOF98 $7F004 steps a state list +$C2 and counts its hits +$138: level 0 one hit (137 -> its end 143), level 1 two (138 -> 139 -> 143), level 2 three (140 -> 141 -> 142 -> 144); handlers98 export_rom 'hits_list') An object whose kind changes over its life (TODO #152): a pinned effect that, on its thrower's signal (P_FXOFF, KOF +$D1 bit 7), becomes its next phase where it is (launched a frame later: KOF runs the object before its thrower), with its own rows, reaction and end; a phase may re-arm its hit on given rows (KOF clears its +$E2 bit 7 on an event step: Billy's ring hits every 25 frames while it circles him) and count hits (KOF +$138: the launched ring ends on its first, the MAX one on its fifth, frozen `stop` frames after each). Decoded from the object's code (handlers98 object_phases: its +$F5 writes as `kind` ops). | bproj_t next / hits / stop, bprow_t flags 4, fighter.c proj_launch / prog_fxoff / proj_hit; proof romspecials_check billy:C / billy:M (hits 6 / 10, ends +-1 frame) | 2 (Billy 23624C, MAX 23624C) |

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
| `input.sustain` | button (the special's), levels (ROM count) | **Implemented** (TODO #173, Rugal's Kaiser Wave $7EDAA): a charge: while the special's button is held (KOF `and.b (fp), d0` on its button mask), the program counts its charge animation's event steps (134: frames 30 and 54); released, or the animation over, it picks the level's path by the count (`tst; beq`, `cmpi #1; bls`). The decode keeps the count a run-time counter and walks each level's path with it known (handlers98.CHARGE). A hold (TODO #198, Kyo's Orochinagi $3D4EA): the button held keeps the charge state playing until a frame counter runs out (+$CA = 90: `subq; bpl yield`), released it goes on at once; every `and.b (fp)` past the move's first frame is this run-time test (handlers98 decode). | PC_HELD (fighter_t.pheld: C held, D for a fury), P_SET / P_ADD cnt, PC_CNTLE / PC_CNT; proof rugal173_proof.py charge (C held 0 / 70 / 95 frames: 1 / 2 / 3 hits), kyo198_proof.py | Rugal 6426A, 6426C; Kyo 21426C + MAX (D / down+D held: up to 90 frames; the MAX burns, KOF's 195 attack box) |
| `branch.on_height` | px (int, 0..255) | Branch on the body's height. | PC_LOW | 1 (98 1) |
| `branch.on_offscreen` | - | Branch when off screen. | PC_OFF | 0 |
| `branch.parts` | parts ([rows]), next (part | end) | A move made of parts that chain. | bspart_t (recorded), the program's own flow (ROM) | 19 (98 10 96 2 99 3 KZ 4) |
| `branch.cancel` | - (engine rule, no per-move data) | KOF's cancels for every fighter (TODO #143, Bruno 2026-10-06): (1) a ground normal (any route node) that made contact cancels, from the end of its hit-stop to its last frame, into a special (C + the stick: the route's own special link when the node has one, else the slot the stick picks) or the fury (D, down+D the MAX); (2) a special (not a fury) whose first hit landed (its body's or its projectile's) cancels into the fury on D, on the ground and not while it holds a caught victim; a catch's final impact (its slam: Rugal's God Press grinding the victim into the wall) lets the victim go (PF_HOLD off) and from that frame the special cancels like any hit, a D pressed since the catch fires then (feedback 20261006-175700 reopened: "after the wall impact I cannot cancel into a fury"); a D before that first hit does nothing; (3) a fury (not a MAX) whose first hit landed cancels the same way into the fighter's MAX fury on down+D (TODO #151; D alone does nothing; a fury's catch routine once it lets the victim go, PF_HOLD off): the MAX from its start, its own flash (orange), charge sound, invincibility and meter; a MAX is never cancelled, nor the fury of a fighter without a MAX (bchar_t.fury_max); the fury's objects (shots, eruptions, pinned effects) end at the cancel, so the MAX spawns whole; (4) a throw's last impact before its control return (forward / back + A: the last such row with the impact flag, the blow or the victim hitting the floor) and the hold finisher's landing are normal hits (feedback 20261006-173012 / 20261006-194211, Bruno: "this hit at the end of the throw ... cancel with a special or even a fury"): from the frame after the impact (after its hit-stop: Ryo's freeze) to the thrower's control return, C + the stick cancels into the special, D into the fury, down+D the MAX; the thrower lets go and the victim plays its script on alone (it still lands, its damage dealt). The victim's landing after the control return (Terry's and Geese's throws: 1-7 frames after the thrower acts again) is not the cancel point, the blow before it is (feedback 20261006-194211 reopened, his replays: a cancel at the landing came from neutral after Ryo had flown away, "it still would not cancel after the impact"); a throw whose only impact comes after the control return cancels from the control return. A throw without an impact row (Yamazaki's back throw, Mai's forward throw) has no cancel. (5) The juggle window (Bruno 2026-10-07: the cancel must connect): a throw cancelled from its impact, or a catch's slam (God Press) cancelled into the fury, opens a window on that victim for the canceller's follow-up only: its special / fury (body or projectiles) hits the victim while it is still thrown (the script ends there, the throw's damage still dealt) or airborne without a hurt box of its own (a body box, JUG_BOX), until it lands (fighter_t.jug_by, juggle_open, juggled); other attackers keep the usual rules. The window for a human: a C / D pressed up to CANCEL_BUF = 24 frames before the first legal frame (hit-stop frames not counted) is buffered and fires on it, a press inside the window fires the next frame, and after the control return the fighter is free (C the special, D the fury). KOF98 measured in our emulator (Kyo vs Yuri, close B / close C then 236A, every press frame): a normal's special cancel takes the press from the normal's startup (3 frames before the impact, the earliest the motion allows) until 9 (close B) / 8 (close C) frames after the impact and fires at the end of the hit-stop. Presses during the move are buffered. The fury plays as from neutral (meter, super flash, charge sound, invincibility); a special cancelled into the fury stops at once (its effects and projectiles end with it). Air normals: no special cancel (no special starts in the air). Players only: enemies keep their routes' special links. Contact = a hit (the brawler has no guard). | fighter.c "cancels": fury_cancel, may_cancel, spec_buf / fury_buf, fighter_t.scancel; rule 4: throw_update, cancel_pick, last_impact, CANCEL_BUF, fighter_t.cnc_buf; proof tools/brawler/cancel_proof.py (fury_max: hit, whiff, plain D, the MAX again), throws166_proof.py d (hold finisher), f (every fighter's throws), g (Bruno's bundle inputs) | every fighter |

### hold

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `hold.catch` | box (attack box), dead (frames, 1..12), routine (phase) | A catch box: no damage, the victim is held, the move goes to its catch phase after dead frames. | bstep_t flags 64, P_ONHIT, fighter_t.pcatch / pdead | 7 (98 6 99 1) |
| `hold.place` | px (int, 0..127) | The caught victim put N px in front, facing the attacker. | P_PUT | 5 (98 4 99 1) |
| `hold.held_reel` | - | The held victim reels in place under every hit until let go. | P_HOLD / P_UNHOLD, PF_HOLD, HOLD_BOX | 3 (98 2 99 1) |
| `hold.contact_grab` | - | A reach that catches without damage; the continuation hits. | bspec_row_t.hit bit 3 (recorded) | 1 (98 1) |
| `hold.victim_list` | lists ([(dx, dy, posture, flags)] per attacker step) | **Implemented** (TODO #173): a catch's victim script, KOF98's way: the catch gives the victim the attacker's +$1A0 routine, which takes a list (`$24B22`: list + map[victim] * size) and places the victim every frame at the attacker + the entry of the attacker's current step (`$25372`: offset, height, posture, facing, drawn in front; flags $01 a blow: the move's damage, its hit sound, no hit-stop; $40 the release: its flight, KOF's 283 = the blowback); the attacker's signal (`ori #$80, +$D1` on the victim: P_VSIG) moves it to its next list; an entry past a wall steps the attacker back instead (`stage.wall`, KOF `$255B0`); a list the engine's throw on the held victim starts (KOF98 `$3F8A` -> `$1E834[id]`, Iori 23624C's finisher, TODO #216: `P_CATCH`, `VL_CATCH`: the throw routine from the next frame, its victim held on that list); the drag's list replayed while the attacker's counter runs (Yamazaki 236236C: A, B, B, C); a MAX test picks the path. The lists of the fighter itself as the victim (the brawler's throw rule). Rugal's God Press / Gigantic Pressure: $299378 (held, pushed) then $299410 (the slam: 425, 426 + blow, 283 release); the MAX: + $29B128 and the push back across. | bspec_t.vlists (bvlist_t / bvent_t, VE_*, VL_CATCH), fighter_t.vlist / vent, fighter.c vlist_apply, P_CATCH; handlers98.victim_lists / victim_entries, op cine; proof romspecials_check rugal:fD / C wall (0 frame mismatches, hits on KOF's frames), yamazaki:C, iori:C | Rugal 624A, 23624C (+ MAX); Iori 624B / 624D, 23624C; Yamazaki 236236C |
| `hold.victim_phase` | bits: snap (to the attacker's place), freeze / thaw (the victim's body held still, its velocity kept), mirror / unmirror (its velocity the attacker's, mirrored) | **Implemented** (TODO #136 / #138, Kizuna): the attacker's handler writes its victim's phase flags (+$1AF bits 4-7, +$1AE bit 0) and the victim's own code reads them every frame ($2CD06: +$106 bit 3 = no physics and no recovery, +$107 bit 2 = $37A20 the attacker's velocity negated, $2CE56 the attacker's x / y copied); its hits do not end them; Kizuna's push (the bodies' first boxes, half the overlap a side, 8 px a frame, a frozen body not moved) for the phased victim; a program condition reads its height (the Phoenix's ceiling). | P_VPHASE (VA_*), fighter_t.vph, fighter.c vphase, combat's phased push (bstep_t flag 4 under SF_SREACT = a push box), PC_THIGH; P_SCREEN (the special's screen effect switched by its program) | KZ 2 (Kim's 421A, 6246A) |
| `hold.carry` | rows ((x, y) per row) | The victim is placed per row relative to the attacker (recorded cinematic). | bspec_row_t.hit bit 2 + vx / vy (recorded) | 7 (98 4 96 1 KZ 2) |
| `hold.throw_script` | rows ((thrower frame, offset, victim pose, offset, flags) per frame), speed (8.8) | A paired attacker / victim script with impacts (the walk-in throws C / D). | bthrow_t / bthrow_row_t, throw_update | 17 fighters |
| `hold.grab_hold` | hits (int, 3), time (frames, 90), hit / fin (moves), dx (px) | **Engine rule** (TODO #146, Final Fight): walk into a standing enemy (grabbable by its current state: idle, walk, reel); A = a hold hit (the fighter's own blow, startup squeezed to 3 frames, a paired script; the move: game.json, default the fastest-startup close normal, TODO #166; its spark on the held victim and its attack box hitting every other enemy in reach, each once per hit: the hold crowd, Final Fight / Streets of Rage), the third the finisher (knockdown, the hold ends; a normal hit: cancellable into a special / the fury, branch.cancel rule 4, as every throw's last impact); the catch is silent; hits keep the hold: free GRAB_TIME frames after the grab or the last hit, never during one; forward / back + A throws at any time; the victim always drawn behind the grabber. | S_GRAB / S_GRABBED, GRAB_* (hold_update), bchar_t.holds (export_bm hold_rows; game.json roster[].throws.hold) | every fighter |
| `hold.paired_script` | rows (thrower frame + offset, victim posture or BA_* animation + offset + facing, impact / turn / front flags per frame), speed (8.8), ret (row), rel / land (rows) | The attacker and its victim played together from one table (TODO #146): the thrower to its CONTROL RETURN row (read from the throw's code: the earliest step start after the last impact, never past the code's own end), the victim on alone to its lying state; the victim drawn behind unless a row says front (data override). Pilot: Terry (KOF98), Geese (KOF96) throws read from the ROM (tools/kof96/throwrom.py: the throw routine, its victim list, its flight routine executed; 0 frame mismatches against the game); the rest of the roster still plays captured scripts through it. | bthrow_t (ret, rel, land) / bthrow_row_t (flags 32), fighter.c paired_update / victim_rows / thrown_update | 2 pilot fighters (4 throws) + 2 hold scripts every fighter |

### variant

| feature | parameters | semantics | implemented by | moves |
|---|---|---|---|---|
| `variant.parameter_set` | variants ([input -> parameter set]: light / heavy / EX / MAX), selector (button, EX flag, MAX bit) | One behaviour (the program) with parameter sets chosen by the input that started it: KOF's handler tests the button (+$1A4 bits 4-7), the EX flag (+$1D6) and a DM's MAX bit (+$E4 bit 0) and writes other speeds, timers, state / spawn tables, counts and damage ids (Double Dragon 1995: 4 per special). | decoded, not played: `handlers98.decode_variants` forks at every selector test (each other way, the tests before it kept, decoded again until no new path), `export_rom` stores every version as `rom.variants`; the game plays the slot's own button | 94 (98 61 96 26 99 7) |
| `variant.table` | rows (parameter rows: one per button), columns (the program's operands that differ: velocities, step counts, damage), default (the row played) | **Engine feature** (2026-10-06, Double Dragon's Billy Lee): one program + N parameter rows. The program's ops name a column instead of a value (`bprim_t.op` bit 7: the value is `vars[var * vcols + b]`), its animations and objects are per row (`anims[a + var * vanim]`, `robj[a + var * vobj]`), the hits' damage is a column (`vdmg`). The row is chosen by the brawler's rule and **latched at the move's start** (`fighter_t.var`): today the row `bspec_t.vdef` = game.json `roster[].variant[input]` (a button letter or a row), else the source's default, the heaviest (D). DD's four buttons: header velocity, the step list (length / loops, so the hits), the level (damage). | bspec_t vars / nvar / vdef / vanim / vobj / vcols / vdmg, fighter.c prog_update; export_dd.special (the columns found by comparing the four programs op by op); proof tools/doubledr/billy_proof.py (every row of every special = DD's model: travel / height) | 7 (DD: Billy 623 / 236 / 214, Super Billy 623 / 41236 / 236 / 214) |

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
| `fx.super_flash` | anchor (optional: dx, dy px from the feet, KOF orientation) | **Engine rule** (TODO #139, 2026-10-06), every fury (D) and MAX fury (down+D) of every fighter: from the fury's frame `start` the game freezes except the attacker for `freeze` frames (enemies, projectiles, camera, waves / timers, other players; nothing hits but the attacker's own boxes: a fury whose first hit falls inside the flash, Kim's Phoenix, connects; KOF's furies hit 39-47 frames in, after it), the fury charge sound (`sound`: KOF98's $1A $3A, sent by its flash routine for every DM and SDM alike) at its start, the stage hidden, the backdrop white `white` frames then dark; KOF98's concentration (glow + rays, the effects library) at the anchor, blue for a fury, orange for its MAX version. Timings / colours game-wide (game.json `super_flash`: KOF98's 1 / 28 / 4); per move only the optional anchor (read from its KOF animation's `$FA` command: handlers98.md "Super flash"), else game.json's. | gflash_t (game.json super_flash), bspec_t.sf_anchor / sf_dx / sf_dy, main.c super_flash, superflash.h (make_sparks.py build_flash) | every fury (anchors: 16 KOF furies + their MAX versions) |
| `fx.super_flash` flash pose | the pose's kind (`rage` / `taunt` / `charge` / `win` / `intro`) or an animation; its head point; `fit` | **Engine rule** (TODO #145, 2026-10-07): a fury whose source game has no flash step of its own (Kizuna, Samurai Shodown II, World Heroes Perfect, Double Dragon; KOF96 / 98 / 99 furies keep their `$FA` flash step and play under the flash) shows the fighter's **flash pose** for the whole freeze: a whole animation of its source game (default per game: Kizuna's C+D taunt, SS2's **rage** = the game's own POW-full animation 140 (TODO #189: every SS2 fighter plays it when the gauge fills, class 0 action 46), WHP's win pose, Double Dragon's power-up stance), its steps cut to `freeze` frames (the last one held when it is shorter) or, `fit` (SS2's rage), the whole animation timed to them; a step on which the source sends one of the fighter's voices sends it as the pose shows it (bfpose_t.voice: the rage shout); nothing of the fury runs, nothing hits; the fury starts from its first frame on the frame after the freeze, with the world moving. The concentration glow is anchored on the pose's **head point** (head_point.py on its first step, or data). | export_bm FLASH_POSES / fpose_steps, game.json roster[].flash_pose, bchar_t.fpose / nfpose / fhead, fighter.c flash_pose, main.c super_flash (anchor) | Kim, Haohmaru, Genjuro, Kuroko, Hanzo, Billy Lee (+ their MAX versions) |
| `fx.throw_start` | row, dx, dy (px forward / up from the thrower) | **Engine rule** (TODO #166, Bruno 2026-10-06): every throw starts with KOF96/98's throw effect (shared effects state 61, the blue streaks, palette 90) and its sound ($1A $18), placed in the world where the throw's own animation spawns it (its `$FA $34` command: tools/kof96/throwrom.throw_fx; Terry forward+C row 3, 40 px forward, 78 up); a throw without the command takes its other throw's, else Terry's. Measured against KOF98 / KOF96 in our emulator: the same frames, from the same row. | bthrow_t.fx_row / fx_dx / fx_dy, fighter.c paired_update, main.c throw_fx (throwfx.h: make_sparks.py build_flash) | every throw |
| `fx.hit_spark` | per attack step: spark kind (its source game's), turned, screen strobe | **Source effect** (TODO #215, 2026-10-07): a fighter whose game draws its own hit sparks plays them instead of the engine's KOF98 spark: a hit landing on an attack step its table names spawns that spark as an effect object (bproj_t kind PK_FX: no box, no shadow, its rows = the game's frames, palettes and motion from the hit point) at the game's hit point (Double Dragon $26AE8: the victim's body box centre + half its half width toward the attacker, the attack box's height), the attacker's facing (turned: DD's height class 3); the strobe (DD's super hits, $25EF2): the stage hidden and the backdrop red 2 + 2 frames twice, as DD's screen. Double Dragon's rule (tools/doubledr/sparks_dd.py): type = $265F2[4 x reaction index + height class], 18 body-hit types (19 frames, palettes 128-131 cycling), every hit of Billy / Super Billy / Cheng-Fu = DD (types, facing, frames, red frames). A projectile's hit, a hold hit and a throw keep the engine's. | bm_hspark (bm_chars.h: map [where, anim, step, spark] + sparks), fighter.c hit_spark / hitflash, main.c screen_fx; export_dd spark_codes / spark_finish | Billy, Super Billy, Cheng-Fu (every normal / special / super hit) |
| `draw.sprite_budget` | - (engine rule, no per-move data) | **Engine rule** (TODO #158 / #170, Bruno 2026-10-06: the select screen's Mr. Big and Billy Lee, and the crowd under Geese's Raging Storm, blinked). The LSPC shows at most 96 sprites on a scanline and drops the highest-numbered ones (the front). Measured with the LSPC's own per-line count (a probe build of our core): the Raging Storm with 6 enemies peaked at 87 on a real line, the blink was the line guard, which counted every actor as sharing one line (it hid an enemy on 46 of 109 frames, alternating); the select screen's 22 actors really passed it (108 on the lines of the bodies; the guard hid 4-5 a frame, alternating). Two rules. (1) **Trimmed columns**: every sprite column of every frame shows only its rows from its first to its last non-empty tile, with its own Y and height (no sticky chains); the trims are computed at export (3 words a column after the part's tiles), so a column counts only on the lines it really covers (select 108 -> 93, Raging Storm 87 -> 82). (2) **The line guard** counts what each band of the screen will show: the entities' shown columns, a ground shadow 2 under the feet on the frames it shows, and what it does not place (the stage plane's 21, or the super flash's glow + rays that replace it; the throw effect; the drama portrait; the hit sparks alive on their span); in three steps, each only when the cheaper one is past 96: the whole scene as one line, per 16-px band with each entity as a box, per 8-px band column by column. An entity is hidden only when a band it covers would pass 96; a shadow that does not fit is left out, its entity stays. **Priority** (placed first): the players; their held / hit victims (GRABBED, THROWN, HITSTUN, KNOCKDOWN); the players' objects and the effects of a fury playing (anyone's); the other enemies and objects, back to front one frame and front to back the next (a crowd past the budget flickers in turn). A fury's effect that does not fit is first thinned (every other column, the others the next frame) before it is hidden; the players are never hidden for the budget. Result: the Raging Storm (fury and MAX) with 6 enemies, Kuroko's and Genjuro's furies and the select screen: nobody hidden, no line past 96 (worst 83 / 93). Cost: stage 5 CPU mean 68.1 -> 68.5 %, worst window 97 -> 98 % (bank_cpu.py); the VRAM queue is shorter (only shown rows). | main.c "the sprite budget" (line_guard, col_trim, guard_tier, thin), draw.s fighter_tiles / fighter_place (trims, place_thin), export_bm.py (the trim words); proof tools/brawler/budget_proof.py, budget_bundle.py (Bruno's #158 inputs) | every entity |
| `life.respawn` | blink (60 frames), drop height (224 px), invincibility after (60) | **Engine rule** (TODO #166, Final Fight): a player out of life falls, lies, then blinks with its death voice; no life left -> the continue; else (or after a continue) it drops from above the screen where it fell, untouchable and without control while falling, and its landing knocks down every enemy on screen (no damage). | fighter.c "death and respawn" (fighter_respawn, fighter_quake, fighter_t.drop), main.c flow / respawn | every player |


Notes from the inventory:
- `spawn.trail` is implemented (`bproj_t.child`) but used by **no** move in the game: Krauser's Blitz Ball and Iori's
  Yami Barai have their trail only in the captured projectile (`proj`); the ROM objects they play (`robj`) dropped it.
- `anim.no_hurt_step` (31 KOF ROM moves) is the only move-intrinsic invulnerability; `inv.reversal` is a slot rule
  (down+C only), `inv.fury` a role rule.
- `hit.reaction_by_height`, `hit.no_stop`, `hit.slide`, `hold.*` exist only for KOF ROM moves: the recorded sources
  cannot express them, which is why their gameplay differs (section 2).
- Branch conditions with one user (`branch.on_distance` K', `branch.on_height` Billy 623D) and `branch.on_offscreen`
  (0 users: objects use it internally) are kept: they are cheap and general.
- Missing from the vocabulary altogether: guard / block, armour (hit-through), a juggle counter (the wall: `stage.wall`, TODO #173; the super flash
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
| cancels | normal -> special / fury on contact, special -> fury after its first hit (branch.cancel), every fighter, players | **KOF**: normals cancel into specials / supers on contact (hit or guard), specials into supers (super cancel, KOF98 MAX / specific moves); **Kizuna / SS4 / WHP**: own cancel tables | which moves cancel: per move in the sources, one rule here | A. one rule for every move (today)<br>B. per-move cancel flags from the sources | A (Bruno 2026-10-06), until a move needs an exception |
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
| ralf AAAA [D] | 81 | done 2026-10-07 (TODO #216): read from KOF98's handler $4FD46 (the state list +$C2 concrete: 128, 129, 131; no further press: the mash's repeat is a press the walk does not make), its dust clouds from the shared bank | done |
| robert 426B [uD] | 83 | decode.kof_trace | a (after analysis) |
| yamazaki 214A [ufD] | 86 | decode.kof_trace | a (after analysis) |
| yamazaki 214B [fD] | - | decode.kof_trace | a (after analysis) |
| yamazaki 214C [dfD] | - | decode.kof_trace | a (after analysis) |
| yamazaki 236236C [fury] | 87 | done 2026-10-07 (TODO #216): read from KOF98's handler $6AB7A: the jump's catch box (hold.catch), the victim lists of its +$1A0 routine $6AEE6 (hold.victim_list; the drag's list replayed while his counter +$D2 runs: A, B, B, C), the drag held at the wall by stage.wall's list rule, its $A5 swirl (anim.step_spawn, shape 'follow'); its MAX not exported yet (a second catch, handlers98.MAX_LATER) | done |
| billy CCCC [D] | 88 | input.sustain, decode.kof_trace | c |
| iori 624B [dfD] | 96 | hold.paired_script | b |
| iori 624D [fD] | 94 | hold.paired_script | b |
| iori 23624C [fury] | 98 | done 2026-10-07 (TODO #216): read from KOF98's handler $71680: the claw held by its victim routine, the finisher = KOF's engine throw ($3F8A, P_CATCH: the throw routine's list, its release's blow and purple burn), the claw's slot-1 hit box; its MAX still captured (down+D) | done |
| rugal 6426A [uD] | 116 | done 2026-10-06 (TODO #173): object.phase at hit + input.sustain + anim.step_spawn | done |
| rugal 6426C [ufD] | 117 | done 2026-10-06 (TODO #173): as 6426A | done |
| rugal 624A [fD] | 115 | done 2026-10-06 (TODO #173): stage.wall + hold.victim_list (the 'branch on vx' was the wall test's d0) | done |
| rugal 23624C [fury] | 118 | done 2026-10-06 (TODO #173): stage.wall + hold.victim_list + anim.step_spawn, its MAX too | done |
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
| hanzo HERO 623AB [fury] (the hero rising, "Super Shoryuha") + MAX = the hero DM 65426AC | - | none: scripts generated from the ROM model (tools/whp/handlers_whp.py, frame-identical to WHP, hanzo_fury_proof.py); fury: parts uppercut / rise (a hit ends the uppercut at once, WHP $4C188), held through the super flash, juggle launches; MAX: parts dive / landing / ninja sequence, carry | done |
| kim 236C [fD] | 134 | decode.kizuna | a (after analysis) |
| kim 214B [D] | 133 | decode.kizuna | a (after analysis) |
| kim [2]8C [dD] | 135 | decode.kizuna | a (after analysis) |
| kim 421A [uD] | 136 | done 2026-10-07 (TODO #136): reaction.source_motion + hold.victim_phase | done |
| kim 6246A [fury] | 138 | done 2026-10-07 (TODO #138): reaction.source_motion + hold.victim_phase + P_SCREEN | done |
| kim 236A [dfD] | 137 | decode.kizuna | a (after analysis) |
| kizuna:gozu/mezu/joker/gordon fury | 77 | hold.paired_script | off build |
| kizuna:hayate [2]8C | 77 | spawn.boomerang | off build |
| kizuna:chung fury, r_shishi 4264A / 214B | 77 | decode.kizuna | off build |
| kizuna:projectiles | 77 | decode.kizuna | off build |
| kof99:k_dash 214D / 236B / 236D / 623A / 23624C follow-ups | 140 | decode.kof_trace | off build |
| kof98:kyo 236C 6A after hit-stop | 140 | - | off build |

| component | kind | extends (regression set size) | only blocker of (in game) | needed by |
|---|---|---|---|---|
| `decode.whp` | analysis | - (0) | 6 | hanzo 236A [D]; hanzo 236D [fD]; hanzo 623A [dfD]; hanzo 623B [dD]; hanzo 214C [uD]; hanzo 214D [ufD] |
| `hold.paired_script` | enh | hold.throw_script, hold.catch (24) | 5 | yamazaki 236236C [fury]; iori 624B [dfD]; iori 624D [fD]; iori 23624C [fury]; goenitz 2141236C [fury]; kim 421A [uD]; kim 6246A [fury]; kizuna:gozu/mezu/joker/gordon fury |
| `decode.ss4` | analysis | - (0) | 5 | haohmaru 236C [D]; haohmaru 623B [dD]; haohmaru 421C [fD]; haohmaru BUST 236D [uD+fury]; haohmaru BUST 623D [dfD] |
| `decode.kof_trace` | analysis | - (0) | 4 | ralf AAAA [D]; robert 426B [uD]; yamazaki 214A [ufD]; yamazaki 214B [fD]; yamazaki 214C [dfD]; billy CCCC [D]; kof99:k_dash 214D / 236B / 236D / 623A / 23624C follow-ups |
| `decode.kizuna` | analysis | - (0) | 4 | kim 236C [fD]; kim 214B [D]; kim [2]8C [dD]; kim 421A [uD]; kim 6246A [fury]; kim 236A [dfD]; kizuna:chung fury, r_shishi 4264A / 214B; kizuna:projectiles |
| `spawn.multihit_object` | enh | spawn.projectile, spawn.eruption (28) | 0 | built as object.phase at hit (TODO #173) |
| `stage.wall` | new | - (0) | 0 | built (TODO #173) |
| `anim.step_spawn` | enh | anim.event_marker, spawn.eruption (53) | 1 | goenitz 214C [dD] |
| `spawn.boomerang` | enh | spawn.projectile (19) | 1 | built (TODO #176: Kuroko 63214A); kizuna:hayate [2]8C |
| `input.sustain` | new | - (0) | 0 | ralf AAAA [D]; billy CCCC [D]; built (TODO #173 Rugal's charge, #198 Kyo's Orochinagi hold) |
| `branch.on_velocity` | enh | branch.on_distance, branch.on_height (2) | 0 | not needed (624A's test was the wall's) |

Debt plan (which component retires the most recorded moves first):
1. **decoders** (analysis, no engine risk): `decode.whp` 6, `decode.ss4` 5, `decode.kizuna` 4 alone (+2 with
   paired_script), `decode.kof_trace` 4. The sheets for Kim 236C and Haohmaru 421C show these moves need **no** new
   feature: Kim 236C = 4 parts + 2 input links + hits; Haohmaru 421C's leap fits `move.velocity` / `move.gravity`
   (vx 9.0, vy 6.27, g 0.47) within 0.57 px of SS4's path.
2. **`hold.paired_script`** (enh of the throw script + catch): the only blocker of 5 moves (Iori 624D / 624B / fury,
   Goenitz fury, Yamazaki fury), needed by 7 in the game + 4 Kizuna furies off the build. Regression set: 17 fighters'
   throws + the 7 catch moves (24).
3. ~~`spawn.multihit_object`~~ done (TODO #173, object.phase at hit): Rugal 6426A / C.
4. ~~`stage.wall`~~ done (TODO #173, with hold.victim_list): Rugal 624A and fury.
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

## Form link (built 2026-10-06: Double Dragon 1995's transformation, Billy Lee -> Super Billy)

The proposal below, promoted to an engine feature, generic for any roster entry (Rugal -> Omega Rugal later):

| feature | parameters | semantics | implemented by |
|---|---|---|---|
| `form.change` | trigger (`down+D full meter`), transition (a special of the fighter's bank), target (a roster entry), carry (life, position, facing, meter), exit (`life` / `stage`) | game.json `roster[].form`. The trigger starts the transition as role BS_FORM (untouchable from its first frame, not cancellable; its own steps have no hurt box). The transition's `P_FORM` op replaces the fighter's character data in place (`fighter_t.ch`: frames, animations, specials, routes, palettes, voices, the HUD face and name) and ends the special; everything in fighter_t stays (life, x / y / z, facing, meter, the enemies' targeting: they hold fighter_t pointers); in the air the new form falls with its own fall and lands with its own landing. Exit `life`: back to the base form when a life is lost (fighter_revive); every player is the base form again at a stage's start (fighter_init). The target is a roster entry with `selectable: false` (no select slot, roster_unlock 0xFF, never a pool pick of the attract demo / P2's join). | bchar_t form_to / form_spec / form_trig / form_exit, fighter_t.form_from, fighter.c "form" (form_swap, form_set), P_FORM |
| `fx.form_effect` | - | Covered by the frame data: DD's dragons are group 1 of the transition's own sprite definitions (palette 128 / 129), exported as parts of its frames with their own palettes; the transformed colours from the step that switches the palette (DD attr bit 4) are a palette key of Billy's bank ('form': Super Billy's colour set). | export_dd Builder (palette keys) |

Billy Lee's choices (for Bruno's review): trigger = down+D with a full meter (his down+D, the MAX slot, is free: DD has no
MAX super; DD itself needs the powered state, life + gauge meeting, and A+B+C+D held), the whole meter spent (with
meter.infinite 1 nothing is spent); exit = a lost life (a brawler has no rounds; DD keeps the form for the round);
Super Billy has no fury (DD gives the form no super; its gauge freezes). Not taken over: DD's +25 % damage and frozen
gauge while powered, the palette cycle of pen 9 (the glow outline: one colour of the eight kept), the camera following
the 193 px rise (the brawler's camera does not scroll up: he leaves the top of the screen for ~0.5 s).

## Proposal: form change (Double Dragon 1995's transformation)

The proposal as written before it was built (above). Source study: `/data/neogeo_dict/doubledr/README.md` ("Transformation"), tool
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
