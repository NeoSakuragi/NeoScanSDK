# Brawler POC

How far the Neo Geo goes as a Final Fight style beat 'em up: 2 players, 8 fighters on screen, KOF fighters as the cast.

```bash
make                                    # needs /data/roms/kof98.neo (fighter data) and tools/kof96
../../emu/neogeo_sdl brawler.neo
python3 ../../tools/brawler/run_test.py out.png "p1 0 42 R; p1 42 14 U; p1 60 3 a; p1 71 3 a; p1 82 3 a" --snaps 65,76,87
```

## Arcade flow (MVS, Unibios)
Power on: attract demo = a fight where P1 is `ai_bot` (closes in, combos, grabs, down+D reversal when threatened) against
weak enemies (`ai_weak`), a new fighter each time, INSERT COIN blinking; after 40 s it hands back to the BIOS, which
starts it again. Coin (keyboard 3): title screen (banner, PRESS START); START (keyboard 1) takes a credit -> character
select -> the fight. Game over / stage clear: back to the BIOS (attract, or the title while credits remain).

## Versions, publishing, Android player
`VERSION` (0.0.1 style; `make bump`) is compiled in and shown on the title screen. `make publish-vps` uploads the
build to canneji.duckdns.org/brawler/download/ (shared secret; every check and download logged with the device, see
tools/brawler/publish_vps.sh) and the info page canneji.duckdns.org/brawler/ shows the version. The Android player
(NeoGeo/android, NeoScan Player) fetches the newest build on launch, verifies it, and falls back to the cached one.
The secret is in the APK: it keeps casual visitors out, it is not real protection.

## Character select
The roster as a 7 x 2 grid of 32x32 fix-layer portraits (tools/brawler/make_hud.py), corner-bracket cursors (P1 red,
P2 green), each player's cursor fighter previewed large above it with its name. Stick moves (wraps), A/B/C/D picks that colour set, KOF style, and plays the win pose. Both picked: the fight
starts 90 frames later; the enemies are the first six fighters nobody picked. Same fighter in the same colours: P2
gets the next set.

## Game flow
Three waves of six enemies (the fighters nobody picked, in turn), each walking in from the right; a defeated enemy
blinks and goes. Players: 3 lives, then a 10 s CONTINUE (START with a credit: 3 more). Last wave gone: STAGE CLEAR;
both players out: GAME OVER; both end back at the BIOS (title while credits remain, else the attract demo).

Arcade conventions (SNK MVS; the game draws them, not the BIOS): "LEVEL-n" and "CREDIT nn" on the bottom line of
every screen. LEVEL = the DIFFICULTY setting (LEVEL 1-8, default 4) of the game's soft DIP table (`soft_dip` in
main.c, BIOS game settings menu); CREDIT = backup RAM $D00034. P2 joins mid-fight: "INSERT COIN" / "PRESS START"
blinks above the empty side; START with a credit brings a fighter nobody on screen is. The BIOS PLAYER_START request
goes through `game_start_accept` (crt0 hook): only a player not in play may take a credit, never on the select screen
or under a STAGE CLEAR / GAME OVER banner.

HUD (fix layer, tools/brawler/make_hud.py): P1 portrait, name, KOF94-style life bar with a damage trail, lives, top
left; one player: the enemy P1 last hit, mirrored top right; two players: P2 top right, each player's target under
its own bar. WAVE n and CPU % at the bottom. `rm build/main.o; make PROFILE=1` adds the per-section profiler and the
AI counters; `make AI_OFF=1` builds a test ROM whose enemies stand still.

## Hit sparks
KOF98's two hit sparks (tools/brawler/make_sparks.py, data in sparks98.json, captured from MAME): small for A / B hits,
big for C / D / C+D, knockdowns and specials; at the midpoint of the attack and hurt boxes, mirrored with the attacker.
Sprites 364-375 (4 at once), palette 254, C ROM tiles 700-796.

## Debug box viewer
P1 START in a fight (keyboard 1; P2 START joins) toggles it: the four corners of every hurt box (green) and attack
box (red) the hit test uses, as 8x8 brackets on sprites 300-363 (8 boxes per kind).

## Controls (P1 and P2)
Stick walks on the floor (up/down = depth), forward twice = run. A punch, B kick, C jump, D special (C+D blowback when a fighter has none).

| Route | Links (KOF normals) | Ends with |
|---|---|---|
| AAAAA | far A, far A, close C (2 hits on Terry), close D, C+D | knockdown |
| AB / AAB | far A, close D / far A, far A, far D | - / launch |
| BB | close B, close D | knockdown |
| BAB | close B, far C, crouch D | trip |
| any link + forward A / down B | C+D blowback / sweep | knockdown / trip |
| D / forward+D / down+D | the fighter's projectile / forward rush / rising reversal (below); cancels a normal that hit | knockdown, 8 damage |
| run + A | C+D blowback | knockdown |
| air A / air B | jump C / jump D | heavy / knockdown |

**Hold:** walk into a standing enemy (within 32 px, |dZ| <= 12) to grab it. A = down+C, B = close D (3 damage each, landing
on the move's attack frame); the third hit is always C+D, which knocks it down and ends the hold. Forward+A = the forward throw
(KOF's forward+C), forward+B = the reverse throw (KOF98's forward+D throw), 12 damage, played from its per-frame script; after 90 frames it breaks
free. The thrower can't be hit during a throw; a held enemy hit by someone else ends the hold.

Links chain only when the previous one hit: pressed during the move (remembered, the last press wins) or Final Fight
style up to 30 frames after it ended (`CHAIN_WINDOW`: tap, wait, tap). An attack is never cut: the next one starts when
its animation has finished. A victim stays in hitstun 36 frames (light) / 54 (heavy), 3x a fighting game's; hit-stop is
10 frames for every hit, light ones included, so every impact lands with the same weight (KOF98 measured ~10-12). Multi-hit normals (Terry / Chang close
C, Yamazaki close D, ...) hit once per hit window, damage split over the hits, a knockdown only on the last. One table
(`COMBO[]` in fighter.c) for every fighter: the links are animations every KOF fighter has.

## Specials
D (or A+B) = a projectile, forward+D = a move travelling forward, down+D (toward the camera) = a rising reversal,
invincible from its first frame through its last hit or apex. `pick_specials` in export_bm.py sorts each fighter's
captured ground specials by what the body does (objects while it stays put / forward >= 60 px staying low / rising),
light buttons first; a fighter without a move for a role plays the nearest one it has. Terry: Power Wave / Burn Knuckle /
Rising Tackle; Ryo:
Ko-ou-ken / 624B / Ko-hou. A special pressed during a normal (even in its hit-stop) cancels it once it has hit. They play from the per-frame scripts captured in the games (tools/kof96/specials96.py): fighter
frame + offset, up to two objects per row. Objects are `fighter_t` entities from a pool of 4 (`projectiles[]`), so the
renderer, depth sort, line guard and hit test are the same code; an object's attack box is its sprite bounds (none for
effects that hit nothing in the game: Burn Knuckle's flames). Hit out of a special: its objects go.

How a script hits (export96 `special_entry`, export_bm `special_play` / `special_rows`; `tools/brawler/check_specials.py`
prints all of it per special):
- Body attack box per row = the box of the KOF animation step the fighter was on in the capture (state + step from
  object +$74), live while the step is active (flag $0100, the last box command stays live), with KOF's attack type
  0-63 (keys '1x' / '1xx': types 32-63 used to read as hurt boxes, so Krauser's dropkick, Ryo's Ko-hou never hit).
- Hit version: when the move's close-range capture (opponent 48 px ahead) landed hits, that capture is the script.
  KOF's contact freezes (object +$124 hit-stop counter) are hit markers, not movement: frozen rows are dropped, the row
  before a freeze whose opponent's life drops is an impact. A run of box rows is live only when the game hit inside it,
  opening a hit at its start and at each later impact, so a move hits as often as in the game at point blank (Terry's
  Rising Tackle 7, Mr. Big's 63214D 6). Whiff scripts (no hit captured) keep the step rule of the normals.
- Reaction per hit, measured after each impact from the opponent's state / height: grounded (heavy reel) or ejected
  (knockdown, launch at 48 px+); defaults: last hit ejects, earlier ones reel. Damage 8 split over the hits.
- Between its first and last hit the target is carried where the game's opponent was (KOF's push boxes and juggles),
  and a special pushes an opponent standing in its path 32 px ahead (`PUSH_DX`, measured 27-49 px at the first impacts).
- Hit-confirmed continuations (`bspec_t.cont`): when the close capture goes through states the whiff doesn't, the script
  is the whiff + the continuation; a hit on a whiff row before its recovery jumps there, reaching it without a hit ends
  the move. Geese's Jaei-ken: dash, then two more hits (3); Kyo's Kototsuki You (up+D, 624B): the run catches on
  contact (KOF tests contact by code: the continuation's first box stands in for it), blow, explosion.
- Counter stances are not picked (their close capture stays put with a live box and lands nothing: Geese's
  Atemi-nage, Yamazaki's 426, Billy's 214).

## Enemies (`ai.c`)
Same intents as a joystick, so one state machine runs everybody. Each enemy targets the nearest player and keeps to its
side of him. Two attack tokens, dealt every 16 frames to the closest able enemies (distances computed once a frame).
A token holder closes in to 36 px on the player's depth line, then either presses A one to three times 10 frames apart
(AAA chains only on hits) or, 3 approaches in 8, walks into him with the `grab` intent: contact grabs (enemies only grab
on purpose). Holding, it hits (A or B) every 24 frames and after two may throw (forward+A / forward+B), else its third
hit is the C+D. Any enemy 70-140 px away near the player's depth line fires its D special (the projectile) now and then,
so the hoverers shoot. The others hover around 90 px (walking all the way to their spot, at half speed in 16.16 sub-pixel steps every frame, and setting off
again only when it is 16 px / 8 px deep away: no step-stop-step; an AI fighter goes from walk to idle only after 10 frames
without a walk intent, so the walk never flickers) at a random depth offset. Cooldowns 50-110 frames,
120-180 after a special.

Grabbed player: 4 button presses break free (counted through hit-stop too), then 20 frames invulnerable.
Measured with idle players (30 s): 3 grabs, 19 specials, 1 throw. Profiler HUD (PROFILE_HUD): EG / ES / ET = enemy grabs,
specials, throws; PE = player escapes.

## Stage (`tools/brawler/make_stage.py`)
Placeholder street drawn procedurally: 64 x 14 tiles (1024 x 224 px), 140 unique tiles, palette 1, tiles 1-1023 of the
C ROM (fighters start at 1024). 21 sprites (1-21, behind the fighters at 32+): sprite s shows the stage column c with
c mod 21 = s, so scrolling rewrites one column (28 words) when a new one enters; X of all 21 is one run a frame.
Camera: the players' midpoint, 4 px a frame at most, clamped to the stage; players can't leave the view.

## Roster
`CHARS` in the Makefile: KOF98 Terry, Ryo, Ralf, Chang, Yamazaki, Billy, Kyo, Iori, Mai; KOF96 Geese, Mr. Big, Krauser;
KOF99 Maxima, K' (one export per game). 94,050 tiles = 16 MB of C ROM. The fighter tables (556 KB) live at $200000
(objcopy renames bm_chars.o's .rodata to .p2data), the code (22 KB) at $000000: P ROM 2 MB, no bank switching, room for
about 45 fighters' tables; past that, P2 bank switching. Tile numbers are 20 bits: each game's block sits inside one 64K page
(padded to the next page when it would cross one) and starts with a blank tile, tables keep the low 16 bits and
`bchar_t.tile_hi` gives bits 16-19, which draw.s puts in SCB1 attribute bits 4-7. Here KOF98 is page 0, KOF96 + KOF99
page 1. Only the palettes a fighter's frames use are kept (1-5). Widest frame 19 columns (Billy), inside the 20-column
block. Players pick on the select screen; the others are the enemies, six a wave in turn. Throws work across games:
victim poses are mapped by posture name (see Engine).

## Sprites per line
The LSPC draws at most 96 sprites on a line and drops the highest-numbered (front) ones. Guard (`line_guard` in
main.c): stage 21 + the columns of every on-screen fighter, counted as if all shared the same lines; past 96 the
lowest-priority fighter is hidden that frame. Priority: players, then enemies front to back, reversed every other frame
so dropped enemies flicker in turn. Measured: 8 converged fighters use ~77, so it rarely fires; with the limit forced to
50 it hid 2-3 enemies alternately and never a player. Per-band counting was exact but cost 22 lines; this costs 8.

## Engine
- `fighter.c`: one state machine for players and AI (intent in, no input code inside): walk/run/jump/attack/hitstun/
  knockdown/down/getup, hit-stop (10 frames, every hit), hits = attack box vs hurt box in X/Y and |dZ| <= 12.
- Coordinates 16.16: X, Z (0 = back of the 64 px floor band), Y up. Feet on screen at FLOOR_TOP + Z - Y. Depth order
  = sprite block order (higher block on top); a fighter that changes block gets its tiles rewritten.
- Boxes are KOF's, keyed by type as rom96 stores them: '3x' hurt, '1x' attack (until 2026-10-03 the exporter took the
  low two bits as a slot and lost every C / D attack box). The attack box stays live on every step with KOF's active flag
  ($0100); a step after one without $4000 opens a new hit (bstep flag 4; KOF98 measured, 52 of 54 normals: Billy's close
  D hits twice in KOF98, once here; KOF96 / KOF99 fighters follow the same rule, not measured). Attack boxes stretch back
  to the body line (`export_bm.py`): far normals land point blank; and normals reach at least 96 px forward (`REACH`,
  specials keep KOF's shape), so every hit of a route reaches the same enemies and a group takes the whole route
  together (KOF's boxes run 32-148 px: an enemy behind the first was only reached by the longer hits).
- Moves inside attacks are KOF's own: animation command $FB [00][x:16][00 00] moves the fighter as the next step starts
  (rom96.parse_anim -> bstep_t.dx, forward +). C+D travels 85 px for Terry, 80 Ralf, 56 Chang, 26 Mai: the data's sums
  equal the travel measured in KOF98 under MAME (dummy far away). 19 animations of the roster have moves.
- Jump: 3/4 of KOF's take-off speed (56 % of the height); KOF's full jump leaves the screen.
- Throws (`export_bm.py`): per video frame, thrower frame + offset, victim posture + offset + facing + front flag.
  Postures are the portable names of tools/kof96/victim_poses96/98/99.json ('posture:angle', 28 used by this roster),
  not state numbers (KOF99 re-uses KOF98's numbers with other meanings), so a KOF96 throw plays on a KOF98 victim with
  its own frames. Each fighter's frame for a posture comes from its own game's throws; missing: same posture at the
  nearest angle, else same family (standing / air / head down / floor), else the family's brawler animation. Offsets
  come from the mirror match (KOF keeps one placement list per victim): other victims may sit a few px off.
- Ground shadows (main.c `shadows`): an ellipse under every entity at FLOOR_TOP + Z, sprites 22-45 (between the
  stage and the fighter blocks at 60+), each shown every other frame (flicker transparency; half the sprites a frame).
- `draw.s`: tiles (SCB1 runs, only when the frame changes) and positions (one SCB3 + one SCB4 run for all 128 fighter
  sprites; each part a sticky chain). Offsets pinned by `_Static_assert` in fighter.c.

## Measured (8 fighters, 2026-10-03, our emulator)
With the AI and the scrolling stage: worst frame 30-37 %; update (8 state machines + AI) 24-32 lines.
With the 3-game roster and the guard: worst frame 32-40 % (KOF96 frames have more parts).
With specials (20-column blocks, 4 projectile entities: 240 sprites placed a frame) and their extra frames: 42-47 %,
54 % during a special (a new large frame every row). The fight's first frame rewrites every block (100 %).
Then (2026-10-03): position runs sized to the columns used (and the block's previous ones, to clear them; hidden blocks
cleared once), the frame's column count cached by fighter_tiles for the line guard, flush unrolled 16x (~13.5 cycles a
word), AI distances computed once a frame: worst frame 33-43 % with specials and scrolling.
Sections now (worst lines): flush 10-14, AI 12-13, update 12-14, combat 4-8, sort 4, tiles 21-31, guard 7, place 19-20.

HUD right column = worst raster lines per section over 16 frames (1 line = 768 cycles, frame = 264 lines); CPU = worst
frame, the profiler's own print frame excluded.

| | C renderer | asm renderer |
|---|---|---|
| tiles | 32-48 lines | 15-25 |
| positions | 20-21 | 15-16 |
| flush (vblank) | 19-26 | 17-26 |
| update (8 state machines) | 11-13 | 11-13 |
| worst frame | 30-38 % | 22-31 % |

Next measured options: skip a block's position runs when nothing about it moved (camera still, frame and position
unchanged); the C state machines and AI (~1.5-2k cycles per fighter) are the next asm candidates.
