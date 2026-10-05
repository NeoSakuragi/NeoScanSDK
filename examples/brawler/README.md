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
A police line-up (2026-10-04): the roster stands left to right in its idle pose, 84 px apart, and the camera pans to
keep the selected fighter in the middle; the selected one shows its colours, the others shades of grey (luminance of
their own palettes). "1P" with a down arrow (fix tile $7F, make_hud.py) above the selected head ("2P" above it when a
second player selects). Stick left / right moves; A/B/C/D picks that colour set, KOF style, and plays the win pose.
Then the others walk off the screen outward, the wall and the picked fighter fade to black (32 frames) and the fight
fades in from black (stage, backdrop, fighters). Only the fighters on screen use an entity: the fight's 8 fighter
entities are the line-up's actors, bound to whichever fighters the camera shows. HUD portraits (32x32 fix layer) stay
for the fight.

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

## Sound (`songs.json`, `sound.c`)
SNK's KOF98 sound driver (v1.7) in the M ROM. `songs.json` lists every song the game plays (name, source game,
the song's command there) and the effect codes it sends (`$1A` prefix, slot 1). `make` runs
`tools/port/build_snd.py songs.json build/snd`: M ROM = the driver + only those songs (KOF98's own kept as they are,
songs of other games ported into KOF98's format by `tools/port/port98.py`), V ROM = only their samples and the
effects' (16 MB -> 2.9 MB), `build/snd/songs.h` = `MUS_<name>` (the driver command) and `BOSS_SONGS`
(`snd_boss_song[]`: Mr. Big AOF2 `$21`, Krauser FFS `$3B` "Kaiser Wave", Geese FFS `$43`, Rugal KOF98 `$3B`,
Goenitz KOF96 `$2D`). A new effect code must be added to `songs.json` or it plays nothing.
Checks: `tools/port/compare_port.py build/snd NAME` (port vs original, both drivers' models, chip events),
`tools/port/capture_snd.py --check build/snd` (each song in this ROM in our emulator vs the model, interrupt by
interrupt), `capture_snd.py GAME CMD SECONDS OUT` (a WAV of any song from its own game).

## Debug box viewer
P1 START in a fight (keyboard 1; P2 START joins) toggles it: the four corners of every hurt box (green) and attack
box (red) the hit test uses, as 8x8 brackets on sprites 300-363 (8 boxes per kind).

## Controls (P1 and P2)
Stick walks on the floor (up/down = depth), forward twice = run. A punch, B kick, C jump (tap = hop, hold = regular jump,
stick = vertical / forward / back: see Jumps), D special (C+D blowback when a fighter has none).

| Route | Links (KOF normals) | Ends with |
|---|---|---|
| AAAAA | far A, far A, close C (2 hits on Terry), close D, C+D | knockdown |
| AB / AAB | far A, close D / far A, far A, far D | - / launch |
| BB | close B, close D | knockdown |
| BAB | close B, far C, crouch D | trip |
| any link + forward A / down B | C+D blowback / sweep | knockdown / trip |
| D / forward+D / down+D | the fighter's projectile / forward rush / rising reversal (below); cancels a normal that hit | knockdown, 8 damage |
| run + A | C+D blowback | knockdown |
| air A / air B | the jump kind's C / D air normal (see Jumps) | heavy / knockdown |

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

## Jumps (KOF's two heights, measured 2026-10-04)
C tapped = the **hop**, C held = the **regular jump**, as in KOF96-99 (stick up) and Streets of Rage 2. The decision
window is the fighter's own prejump (`bphys_t.prejump`: Terry 5 frames, most 4, K' 3): C still held on the take-off
frame = regular jump, let go before it = hop (C held 1-4 frames from the press for Terry hops, 6+ jumps; in KOF98 Terry
hops with up held 2-6 frames and jumps from 7, the game reading its input a frame late). Stick at the press: none =
vertical, the way the fighter faces = forward, away from it = KOF's back jump (the fighter keeps facing; a walk turns
the fighter first, so it takes the stick and C on the same frame). Everything comes from the games
(`tools/kof96/capture/jumps.py`, every roster fighter, 6 jump kinds + 4 air normals each):
- Physics from the ROM: launch speed and gravity from the jump table, horizontal speed = the walk table (the prejump code
  loads both), the hop = the same with `vy -= vy >> 2` (KOF98 `$13E2A`, KOF96 `$EF24`, KOF99 `$E578`): 3/4 launch
  speed, same gravity, same horizontal speed. bphys_t `jump_vy0 / gravity / jump_dx` + `hop_vy0 / hop_gravity / hop_dx`.
- Animations: each kind and direction its own (`BA_JUMP_UP/FWD/BACK_RISE/FALL`, `BA_HOP_UP/FWD/BACK_RISE/FALL`; Terry's
  forward / back jump is a somersault, his hops the tuck). No movement in them: the motion is the physics.
- Air normals (A = KOF's C, B = KOF's D): regular jump vertical -> the vertical normal (KOF 100/109), forward or back ->
  the diagonal one (102/111; KOF's back states 104/113 use the diagonal one's animation); hop -> KOF98/99's hop normals
  (122/123, every direction; their animations are mostly the diagonal ones', so a vertical hop's C / D differs from a
  vertical jump's for Kyo D, Mai, Billy, K'); KOF96 has no hop normals, its hop plays the jump's by direction (`export_bm.SOURCES`).

Brawler vs game (harness, AI_OFF build; apex px / frames in the air / forward travel px):

| | hop brawler | hop game | jump brawler | jump game |
|---|---|---|---|---|
| Terry (KOF98) | 52.5 / 28 / 91.9 | 52.4 / 27 / 91.9 | 91.8 / 37 / 120.4 | 91.6 / 36 / 120.4 |
| Kyo (KOF98) | 51.9 / 25 / 80.1 | 51.6 / 24 / 80.1 | 90.5 / 34 / 107.9 | 90.2 / 33 / 107.9 |
| Geese (KOF96) | 45.3 / 26 / 74.9 | 45.2 / 25 / 74.9 | 79.0 / 35 / 99.8 | 78.9 / 34 / 99.8 |
| K' (KOF99) | 51.9 / 25 / 80.1 | 51.6 / 24 / 80.1 | 90.5 / 34 / 107.9 | 90.2 / 33 / 107.9 |

The one frame and ~0.3 px: at the apex the game's rise -> fall state change runs two physics steps in one frame
(measured: Kyo's height step goes 1.0, 0.149, -0.852), the brawler runs one a frame. The regular jump is KOF's full
height: on the back line (Z = 0) only Terry's legs show at the apex, under the HUD (screenshot; Bruno asked for the real
height; until 2026-10-04 the jump was 3/4 speed, which was in fact exactly KOF's hop).

## Command normals (library only, no input yet)
KOF97+'s forward+A / forward+B / down-forward+C / down-forward+D normals are exported as `BA_CMD_FWD_A`, `BA_CMD_FWD_B`,
`BA_CMD_DF_C`, `BA_CMD_DF_D` (end of `MOVES` in export_bm.py), with KOF's boxes and the normals' hit-window rule;
`bchar_t.cmds` bit k = the fighter has `BA_CMD_FWD_A + k` (else the slot holds idle and must not be played). No input
or combo route plays them yet. Found by playing every KOF98 / KOF99 fighter in the game (tools/kof96/capture/cmdnormals.py,
`tools/kof96/cmdnormals_kof98.json` / `_kof99.json`). This roster: Terry 6A (2 hits) + 3C, Ryo 6A, Yamazaki 6A (2),
Billy 6A (2, hop) + 6B (hop), Kyo 6B (2) + 3D (2), Iori 6A + 6B (game 2, here 3: its third window whiffed at point blank
in the game), Mai 6B (hop), Maxima 6A + 3C, K' 6A + 6B (hop); Ralf, Chang, the KOF96 three: none. Moves that go through
several game states (the hops) are built from the captured frames (export96.cmd_frames): `bstep_t.hy` = height, which
the player applies to ground attacks. A hop travels past a point-blank victim (normals have no push box here): K''s 6B
lands from ~100 px. Box rule fix (2026-10-04): a box command on an inactive step only loads the box (Yamazaki 6A 3 -> 2
hits as in KOF98; also K' crouch D 2 -> 1, KOF99 measured 1; Mr. Big crouch C and Krauser close D 2 -> 1, not measured).

## Specials
D (or A+B) = a projectile, forward+D = a move travelling forward, down+D (toward the camera) = a rising reversal,
invincible from its first frame through its last hit or apex. `pick_specials` in export_bm.py picks from each fighter's
captured ground specials; a KOF98 fighter and its EX version are one fighter (Bruno 2026-10-04: same normals, the EX
adds specials), so the pool is both versions' ('EX ...' inputs). D = the fighter's real projectile (below: a travelling
one first, big button first), forward+D = forward >= 60 px staying low, down+D = rising, light buttons last; a fighter
without a move for a role plays the nearest one it has. Picks: Terry EX 236C (EX Power Wave) / 214C / 623C / 214D; Ryo
EX 236C / 214C / EX 623C / 236D; Robert EX 236C / EX 624D / 623D / 623C; Kyo fwd+D EX 624D (the EX picks); Iori, Mai
236C; Geese, Mr. Big 236C (eruptions); Krauser 214C (Blitz Ball, high); K' 236C (eruption); Ralf, Yamazaki, Billy, Kyo,
Yashiro have no projectile. A move that can hit nothing (no attack box, no projectile) is never picked (K''s 236D, whose
object hits nothing in KOF99 either, until 2026-10-04 hit with its sprite bounds; Orochi Yashiro's EX 214C). A special pressed during a normal (even in its hit-stop) cancels
it once it has hit. They play from the per-frame scripts captured in the games (tools/kof96/specials96.py): fighter
frame + offset, up to two script objects per row (effects: `fighter_t` pool entities without a box).

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

## Projectiles (2026-10-04)
How KOF96/98/99 do it: tools/kof98/README.md "Projectiles". A projectile is an entity of its own (`bspec_t.proj` ->
`bproj_t`, exported per projectile special from tools/kof96/projectiles96.py, i.e. our emulator's captures of the move
with the object pool followed by identity): spawned on the thrower's script row where the game spawns it (its event
step), at the game's offset; then it plays its own rows (frame, x from the spawn point in 1/8 px, height, KOF's live
attack box +$90 and its own box), looping a travelling one's flight (`loop`, `wrap_x`). It hits with its own box, once:
a travelling one (KOF object kind 1) then plays its end in place, an eruption (kind 3) plays on with its attack spent;
damage `SPECIAL_DAMAGE`, the victim's reaction and hit sound measured in the game. It dies when its rows end (an
eruption), off screen (x - camera <= -64 or >= 384, the games' own test) or after its end. It flies on whatever its
thrower does (hit out of the special, recovering, walking: KOF's flying routine never reads its owner); the thrower can't
throw another while it flies (`fighter_t.shot`, KOF's owner +$E1 bit 5: D then plays the next role). Neither it nor
its thrower freezes on its hit (the victim does, `HITSTOP`). Two projectiles of the two teams that meet (one's attack
box on the other's own box) both spend their hit (measured in KOF98). A special may throw several (`bspec_t.nproj`: Geese's
Double Reppuken, two eruptions 24 frames and 30 px apart, both hit). A projectile may spawn a trail (`bproj_t.child`,
KOF: objects owned by the projectile, its own table): Krauser's Blitz Ball one on its frames 0, 1, then every 6, Iori's
Yami Barai on 11, then every 12, 7 px behind it, playing their own frames in place. Pool `projectiles[NPJ]` (4, shared
with the script effects, both teams; a script effect's entity is freed as soon as its row shows none): a special thrown
with the pool full shows no projectile, and a trail never takes the last free entity (so the brawler shows 2 of the
Blitz Ball's trail pieces at a time where KOF96 shows 3, Iori's 1 of 2 in a 25-frame flight). `projectiles_update` (main.c, after the
camera) moves them; fighter_t's projectile fields are at its end (draw.s pins the others).

Proof (`tools/brawler/check_projectiles.py`, `make AI_OFF=1`, each fighter picked on the select screen; brawler / game;
frames counted from the special's first script row; game hits from our emulator with P2 (KOF96 / KOF98 Yuri, KOF99 Shingo) 60 / 120 / 200 px ahead):
| fighter | spawn | px/frame | dies at screen x | thrower hit | 60 px hit, frame | 120 px | 200 px | clash |
|---|---|---|---|---|---|---|---|---|
| Terry EX 236C | 15 / 15 | 7 / 7 | 382 / 380.5 | flies on | 1/1, 15/16 | 1/1, 19/18 | 1/1, 30/30 | both end |
| Ryo EX 236C | 14 / 14 | 7 / 7 | 378 / 378.9 | flies on | 1/1, 14/15 | 1/1, 16/15 | 1/1, 27/27 | both end |
| Robert EX 236C | 15 / 15 | 7 / 7 | 382 / 380 | flies on | 1/1, 15/16 | 1/1, 18/18 | 1/1, 30/29 | both end |
| Iori 236C | 10 / 10 | 7 / 7 | 380 / 377.9 | flies on | 1/1, 10/11 | 1/1, 16/16 | 1/1, 28/27 | both end |
| Mai 236C | 15 / 15 | 7 / 7 | 378 / 377.1 | flies on | 1/1, 15/16 | 1/1, 23/22 | 1/1, 34/34 | both end |
| Geese 236C (2 eruptions) | 18, 42 / 18, 42 | eruption, 17 frames / 17 | its end | plays on | 2/2, 20/21 | 2/2, 23/21 | 0/0 | - |
| Mr. Big 236C | 19 / 19 | eruption, 36 / 36 | its end | plays on | 1/1, 21/22 | 1/1, 21/22 | 0/0 | - |
| Krauser 214C | 26 / 26 | 7 / 7 | 382 / 377.6 | flies on | 1/1, 26/27 | 1/1, 29/32 | 1/1, 40/43 | passes (high ball) |
| K' 236C | 11 / 11 | eruption, 31 / 31 | its end | plays on | 1/1, 19/19 | 0/0 | 0/0 | - |
K' 236C (Eins Trigger) is one object standing at K''s hand whose frames are drawn up to ~110 px ahead (the flame arc,
then the burst); its attack box (-52 +- 28 px from the object) reaches ~80 px, so KOF99 hits at 60 px and not at 120
(measured). Side by side, row for row: /data/neogeo_dict/brawler_proof/kdash_236C_kof99_vs_brawler.png.
The game's hit frame is the frame P2's life drops, one after the collision (the brawler counts the collision frame);
the other 1-3 frame differences are the victims' hurt boxes (the game's P2 vs the brawler's enemy). Free-flight life
and travel differ by where the camera stands (the off-screen x matches).

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

## Stages (`tools/brawler/make_stage_ra.py`, needs /data/roms/roboarmy.neo)
**Prototype placeholders** (2026-10-04): Robo Army's horizontal parts, extracted from its ROM (engine decoded in
/data/neogeo_dict/roboarmy/README.md); the final game gets its own hand-drawn art. `make STAGE=n` picks the stage the
fight (and the attract demo) starts on, default 0. The vertical parts (area 2's descent, area 5): docs/brawler_stage_vertical.md.
The former Sengoku 2 castle (`make_stage_s2.py`, two planes with parallax) stays in the repo, not built.

| n | Robo Army | map ids | width | stage tiles | palettes | floor_top |
|---|---|---|---|---|---|---|
| 0 | area 0, the jungle street | $00-$09 | 2560 | 1002 | 25 | 158 |
| 1 | area 1, the highway | $0A-$13 | 2560 | 698 | 21 | 158 |
| 2 | area 2, the boss arena after the descent | $1F-$20 | 512 | 223 | 7 | 158 |
| 3 | area 3, the city / police garage | $21-$2A | 2560 | 985 | 28 | 158 |
| 4 | area 4, the lab (water on the right) | $2B-$34 | 2560 | 689 | 22 | 158 |
| 5 | area 6, the street (its first 100 columns; the rest is the final boss / ending) | $3B-$41 | 1600 | 356 | 9 | 158 |

- One plane each, as Robo Army shows it (no parallax there), scrolling with the camera; sprites 22-42 (1-21 free). Tile
  rows 2-13 (screen y 32-223) in every stage: rows 0-1 are blank (Robo Army's black backdrop behind its HUD), rows 14-15
  below the screen. Backdrop $0000 (Robo Army's palette RAM $401FFE, all 14 scenes).
- `stage.h`: `stages[]` (`stage_t`: map, palettes, columns, rows, y, floor_top, backdrop, REG_LSPCMODE); main.c
  `stage_init(n)` loads the palettes (STAGE_PAL 80 + k, one stage at a time; at most 28), the LSPC speed ($0800 =
  Robo Army's in every scene: a new auto-animation frame every 9 frames) and sets `floor_top` and `world_w`.
- Tiles: one pool for every stage, each Robo Army tile stored once (flipped copies folded into the map words, 4- and
  8-tile auto-animation groups copied whole to aligned places): 4311 tiles, 1525 in the low area 1-1535, 2786 after the
  fighters (99102-101898; the map words carry tile bits 16-19). Robo Army's tile $3FF is its blank (our tile 0); its
  tile 0 is real art. C ROM: 12.68 MB of fighters + 0.36 MB of stages in the 2 x 8 MB image (size unchanged).
- C ROM low area (below the fighters at `TILE_BASE` 2048, export_bm.py): stage pool 1-1535, banner 1536, shadow
  1664-1665, box corners 1666-1669, sparks 1724-1820.
- Floor: `floor_top` (fighter.h; draw.s and the C code read it) = the stage's, `SELECT_FLOOR` 158 on the select screen;
  Z_DEPTH 64. Measured on the art: the walkable band 158-222 is floor in every stage (area 0: dirt from y 160, grass
  tufts over its edge; area 1: road from 160 under a curb 156-159; areas 3, 4 left, 6: floor from 157-158). Robo Army's
  own band is feet y ~170-222 everywhere (object +4 172-224, measured). Stage 2 and stage 4's right half: the floor is
  water (Robo Army's walkers stand in it too).
- The fade-in scales the stage's palettes: ~137 frames with stage 0's 25.
The plane is a ring of 21 sprites: sprite s shows the plane column c with c mod 21 = s, so scrolling rewrites one column
(24 words) when a new one enters; X is one run a frame. Camera: the players' midpoint, 4 px a frame at most, clamped to
the stage; players can't leave the view. The former procedural street (`make_stage.py`) is no longer built
(make_banner.py still imports its colour helper).
Proof (2026-10-04, our emulator, each stage built with `make STAGE=n`): screenshots at camera start / middle / end vs a
render of Robo Army's own map words and palettes from its ROM: 0 wrong pixels in all 18 (45696 compared each, fix layer
masked; the render's auto-animation counter matched, the others differ by 20-1508 px); P1's lowest pixel at y 157 / 221
at z 0 / 64 in every stage (floor_top + z - 1).

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
main.c): the stage plane's 21 + the columns of every on-screen fighter, counted as if all shared the same lines; past 96
the lowest-priority fighter is hidden that frame. A fighter more than 128 px off screen is hidden (placed, its 9-bit X
wrapped it onto the screen: the wave walking in from 512+ px showed at the left edge). Priority: players, then enemies
front to back, reversed every other frame so dropped enemies flicker in turn. Measured: 8 converged fighters use ~77, so
it rarely fires; with the limit forced to 50 it hid 2-3 enemies alternately and never a player. Per-band counting was
exact but cost 22 lines; this costs 8. The castle's back plane needed a second count on its band (lines 0-79); one plane
needs none. Robo Army street (2026-10-04, AI_OFF, 8 fighters converged and attacking for 900 frames, VRAM counted every
frame, same inputs as the castle build: 897 of 900 frames identical): worst line 88 sprites (castle 88), fighters hidden
75 times (castle 127), never more than the castle build on any frame.

## Engine
- `fighter.c`: one state machine for players and AI (intent in, no input code inside): walk/run/jump/attack/hitstun/
  knockdown/down/getup, hit-stop (10 frames, every hit), hits = attack box vs hurt box in X/Y and |dZ| <= 12.
- Coordinates 16.16: X, Z (0 = back of the 64 px floor band), Y up. Feet on screen at floor_top + Z - Y (the stage's). Depth order
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
- Jumps: KOF's hop and regular jump from the ROM's physics (see Jumps).
- Throws (`export_bm.py`): per video frame, thrower frame + offset, victim posture + offset + facing + front flag.
  Postures are the portable names of tools/kof96/victim_poses96/98/99.json ('posture:angle', 28 used by this roster),
  not state numbers (KOF99 re-uses KOF98's numbers with other meanings), so a KOF96 throw plays on a KOF98 victim with
  its own frames. Each fighter's frame for a posture comes from its own game's throws; missing: same posture at the
  nearest angle, else same family (standing / air / head down / floor), else the family's brawler animation. Offsets
  come from the mirror match (KOF keeps one placement list per victim): other victims may sit a few px off.
- Ground shadows (main.c `shadows`): an ellipse under every entity at floor_top + Z, sprites 43-54 (between the
  stage and the fighter blocks at 60+), each shown every other frame (flicker transparency): the half shown on a frame
  (entities 2j + parity) share 6 sprite pairs.
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
