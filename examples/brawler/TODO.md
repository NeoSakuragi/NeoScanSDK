# Brawler POC: TODO (Bruno's feedback, 2026-10-03)

Work through in order; one item per loop tick when it fits, tested in our emulator before it's checked off.

- [x] 1. AI calmer: enemies move less and attack less (fewer token holders, longer cooldowns, slower approach, rarer
       grabs and specials). Done: 1 token, half walking speed, 1-2 punches, rests 120-247 frames, grabs 1 approach in
       8, specials 1 in 512 frames: an idle player now loses a life in ~33 s (was ~20 s).
- [x] 2. Terry's D = Rising Tackle (KOF98 623A/C), invincible from frame 1 (escape tool); also on A+B.
       Done: D = Rising Tackle (forward+D = Power Wave), invincible from its first frame to its apex (22 of 55 rows),
       A+B (one pressed while the other is held) = D for every fighter. Found and fixed on the way: attack / hurt boxes
       were classified by the box byte's type digit instead of its slot (byte & 3; 0 = attack): some attack boxes were
       dropped and some hurt boxes counted as attacks, for every fighter. Combo routes retested.
- [x] 3. KOF98 M ROM + V ROM as the sound driver and samples (check encryption first); find the music command codes,
       placeholder music on the title, select and fight. Done: KOF98's M (256 KB) and V (16 MB) from its .neo play in
       our emulator as they are (res/, kept out of git). Music = one byte: $21-$3F are tracks ($2C, $24 short, $20 and
       $27 silent); placeholders select $21, fight $23, stage clear $2C; music_audition.mp3 sent for Bruno to pick.
       Our emulator's capture mode got WAV=path (audio checks).
- [x] 4. Hit sound effects: watch KOF98's writes to REG_SOUND ($320000) in MAME while hitting with A, B, C, D and
       C+D; isolate the hit / whiff / block sounds; play them from the brawler on the same events. Done (MAME write
       tap, tools/brawler/sound_tap.lua): every sound = $1A + code, one byte a frame; hit A $11, B $12, C $13, D $14,
       C+D $15; swing light $1E (A, C) / heavy $1F (B, D); voices ($1C + code) skipped: they are KOF98's fighters'.
       Wired: swings on attack start, hits per button, $15 for knockdowns / specials / projectiles, knees $12.
- [x] 5. Credits and attract: coin -> credits, title screen when credits are in, START -> select; no credits ->
       attract mode = a fight where the player is a strong AI against weak enemy AI; back to attract after game over.
       Done: crt0 implements the MVS protocol (demo / title requests, DEMO_END, PLAYER_START with credits, SYS_return);
       attract = ai_bot vs ai_weak, 40 s, cycling fighters; coin -> title -> START -> select -> fight -> BIOS. Tested
       end to end in our emulator. This also explains the music "not looping": the BIOS cut the endless demo at ~50 s.
- [x] 6. Title banner "BRAWLER '27": big italic letters in the style of 90s Neo Geo logos, generated, cut into
       16x16 tiles in the C ROM, shown on the title / attract screens. Done: tools/brawler/make_banner.py (Noto Sans
       Condensed Black, extra slant, hot gradient + highlight, black outline, drop shadow, cold "'27"), 304x64 px =
       19x4 tiles, 51 unique, tiles 512+; title screen (banner, blinking PRESS START) at boot and after game over.
- [x] 7. Shadows on the ground under every fighter (and projectile), drawn on alternate frames: half the sprites per
       frame, flicker-transparent look, and depth / jump height read at a glance. Done: 32x16 ellipse (tiles 640-641,
       palette 251) at FLOOR_TOP + Z, sprites 22-45 behind the fighter blocks (moved to 60+); entities alternate frames
       by draw index; the line guard keeps 12 sprites for them. Fight CPU 43-47 %.
- [x] 8. Debug box viewer: the four corners of every hurt and attack box marked with small 8x8 corner pieces
       (like the KOF96 debug build under Unibios), toggled on/off; helps check and showcase the boxes. Done: P2 START
       (keyboard 2) toggles; 8x8 brackets (tiles 642-645, black edge) on sprites 300-379, hurt green / attack red, the
       boxes the hit test uses (step boxes, special and projectile boxes); 54-61 % CPU while on.

## Android player (APK)

- [x] 9. NDK installed; Geolith core built for arm64-v8a (libretro/jni/Android.mk) as libgeolith.so. Done: NDK r30
       (30.0.16248370); ndk-build APP_ABI=arm64-v8a APP_PLATFORM=android-24 -> libretro.so, 900 KB.
- [x] 10. App skeleton (NeoGeo/android/, Kotlin + JNI): load the core, BIOS (neogeo.zip) and a .neo from app storage,
       run frames on a GL surface (320x224 texture, aspect kept, portrait: picture on top), audio via AAudio/AudioTrack.
       Done: NeoGeo/android (AGP 8.13.2, Kotlin 1.9.22, JDK 17, ndk-build of Geolith + cpp/player.c into
       libneoplayer.so, arm64-v8a + x86_64); AudioTrack blocking writes pace the core; GL ES 2 quad (bgr swizzle);
       BIOS from assets; ROM from the app's external files dir. Android 16 emulator: 58.8-59.8 fps.
- [x] 11. Touch controls under the picture: d-pad (8 directions) left, A/B/C/D right in the Neo Geo arc, COIN and
       START; multi-touch, short vibration on press. Done: PadView; presses latched until a frame sees them (adb
       quick taps were lost); tested in the emulator: COIN -> title, START -> select, A -> fight.
- [x] 12. Bluetooth gamepads: each pad = a player (P1, P2), Android key/axis events mapped to the Neo Geo pad; touch
       stays P1 when no pad claims it. Done: first pad P1, second P2 (touch always P1); A/B/X/Y = Neo A/B/C/D,
       R1 = A+B, L1 = C+D, START, SELECT = coin, d-pad / hat / left stick; tested with emulator gamepad key events
       (coin -> title -> START -> select -> B picks Ryo); two real pads at once still to be tried on the phone.
- [x] 13. Auto-fetch: latest.json (build, size, sha256) next to brawler.neo on a server; the app downloads a newer ROM
       on launch, checks it, else plays the cached one (offline OK); `make publish` in examples/brawler.
       Done (per Bruno + the Canneji session): https://canneji.duckdns.org/brawler/download/ = /data/brawler/builds on
       the VPS, nginx, shared secret (Bearer or ?key=, map in root-only /etc/nginx/brawler.conf; app secret in
       android/local.properties), log /var/log/nginx/brawler.log (IP, device, Android, app + ROM version, install id);
       `make publish-vps` (tools/brawler/publish_vps.sh: versioned brawler-<v>.neo, latest.json, last 3 kept, APK
       too, public info.json); info page /brawler/ + hub "Games" card + README row (Oros/CannejiSite). VERSION file
       (0.0.1, `make bump`) shown on the title and the app's start screen. Tested live from the Android emulator.
- [ ] 14. Sideload on Bruno's phone (adb) and measure: frame rate, audio, input latency.
       2026-10-03, Huawei P40 Pro (ELS-NX9, Android 10, 60 Hz mode), today's ROM pushed by adb: emulation 58.1-60.7 fps
       (core 59.19), emu thread 57 % of one core; SurfaceFlinger: 117 of 120 frames shown once, 2 repeated (59.19 vs 60 Hz,
       about one repeat a second), frame queued -> on screen 38 ms median; audio 87-115 ms behind (AudioTrack timestamp,
       now logged with the fps). Input latency end to end still needs Bruno's hands (no camera measurement).

## HUD and select polish (Bruno, 2026-10-03)

- [x] 15. Life bars in the style of KOF94's fix-layer bars (study its S ROM tiles + palette, rebuild ours to match:
       framed thin bar, gradient fill, damage trail). Done: KOF94's bar read from its S ROM in a demo fight (8 px row,
       white outline, shadow, yellow-orange gradient, 1 px steps, caps); ours redrawn in that style
       (tools/brawler/make_hud.py, 54 glyphs from $80) + a red damage trail (holds 20 frames, shrinks 1 px a frame).
- [x] 16. Fighter portraits on the fix layer: the extracted HUD portraits (/data/neogeo_dict/portraits) cropped to one
       32x32 size, encoded as S tiles, one fix palette each (palettes 2-15); shown in the fight next to the life bars
       (player + target). Done: 28x28 face cores + shared frame, 15 colours, PORTRAIT_TILE $100 + i * 16, fix palettes
       2-15; HUD = P1 portrait / name / bar / lives top left, the current target mirrored top right. Found and fixed on
       the way (SDK crt0): the BIOS sends USER request 0 only on the first boot, so .data / .bss / game_init were
       skipped on later boots; the demo / title entry now runs that init once per power-on (magic in .noinit).
- [x] 17. Character select rebuilt around the portraits: a grid of the 14 faces, cursors on them, the chosen fighter
       previewed large. Done: 7 x 2 grid of the fix-layer portraits (rows 17-25), P1 / P2 cursor = corner-bracket
       sprites around the face (red / green), the fighter previewed above the grid with its name under the title.

## Android player: modes and settings (Bruno, 2026-10-03)

- [x] 18. Portrait and landscape layouts (landscape: picture centred, controls overlaid left / right), following the
       phone's rotation or locked in settings. Done: one layout rule (android Screen.kt) for the GL picture and the
       pad, both full screen; portrait = picture on top + opaque pad panel, landscape = picture centred full height +
       controls over the side bars at 45 % opacity; follows the sensor, rotates live without a restart. Tested in the
       Android emulator: both layouts, COIN tap in landscape -> title, rotation mid-game. Lock: item 19.
- [x] 19. Settings page, tidy sections (Display, Controls, Updates, About): virtual button opacity (and size),
       orientation, filter, scale mode; stored in preferences, applied live. Done: SettingsActivity (code-built, no
       libraries) opened by a gear on the pad or a gamepad's HOME / MODE; Display (orientation follow / portrait /
       landscape, filter sharp / smooth), Controls (landscape opacity 10-100 %, size 70-140 %, vibration, gamepad
       map), Updates (auto-fetch toggle, installed build, source), About. The game pauses (emulation + audio) while
       away. Button arc spaced by size; at big sizes arc + d-pad shrink together until they clear. Tested in the
       Android emulator (its "ignore orientation request" had to be off for the lock; phones honour it).
       Scale / aspect / scanline / subpixel options join the Display section with items 20-22.
- [x] 20. Aspect ratio always correct (304:224 pixels, optional 4:3), letterboxed, never stretched. Done: Screen.kt
       ratio 304:224 (square pixels, default) or exactly 4:3 (plain rectangle, per Bruno: no tube look); Display /
       Aspect setting. Measured on screen in landscape: 1465 x 1080 = 1.356, 1440 x 1080 = 1.333.
- [x] 21. Filters: nearest, bilinear, scanlines (strength), plus integer 2x / 3x scaling when the screen allows it
       without overflowing. Done: one fragment shader with a mode (scanlines = cosine line profile, darkness 10-100 %),
       Display / Scale fit or integer (largest whole multiple of 224 lines; the page shows this phone's: 3x portrait,
       4x landscape on a 1080 x 2400 screen). Measured: landscape 1216 x 896 = 4x, portrait 912 wide = 3x.
- [x] 22. Subpixel shader matching our desktop emulator's rendering (emu/neogeo_sdl), used at integer 2x / 3x when it
       fits. Done: shader mode 2 = neogeo_sdl's maths (one of R G B per screen pixel at 1.0 / 0.08, triad shifted a
       step per row, last row of each source line dark from 3x up); selecting it forces integer scale. Checked in the
       Android emulator at 4x landscape / 3x portrait: diagonal triads, 1 dark row in 4. As dark as the desktop one
       (about a third of the brightness: one channel lit per pixel).

## Arcade conventions (Bruno, 2026-10-03)

- [x] 23. SNK MVS conventions: "LEVEL-n" (a DIFFICULTY soft DIP in the header, LEVEL 1-8, default 4, set in the BIOS
       menu) and "CREDIT nn" (backup RAM) on the bottom line of every screen, as KOF94 does; free play off in our
       emulator and the app so credits count. (The BIOS does not draw them: the game does.) Done: soft_dip table
       (crt0's is now weak), LEVEL-4 / CREDIT nn on row 27 of every screen, rewritten on change; coins counted.
- [x] 24. In-game join: "INSERT COIN" / "PRESS START" blinking above the empty P2 bar; START with a credit joins P2
       mid-fight (BIOS PLAYER_START); continues take a credit. Done: crt0 hook game_start_accept (a START from a
       player in play no longer eats a credit); P2 joins as an unused fighter, HUD switches to P1 left / P2 right;
       continue / rejoin = START; box viewer moved to P1 START. Tested: 3 coins, P1 start, P2 join, continue: 3-2-1-0.
- [x] 25. (done 2026-10-05, TODO #66: KOF98 measured in our emulator: logo 1020 frames, demo fight 1800, ranking 240, its eye-catcher 466; ours: logo 1020 -> demo 1800 -> BIOS, README) Attract mode alternates between the gameplay demo and the logo / title screen, with the same timing as
       regular Neo Geo games (Bruno, 2026-10-04). Measure a real game's attract cycle first (e.g. KOF98 / KOF96 in
       our emulator: how long each demo fight and each logo screen lasts, what the BIOS does between them) and match it.

## Hit feedback (Bruno, 2026-10-03)

- [x] 25. Hit sparks: KOF98's hit spark animations (the ones it draws on a hit: small for A / C, big for B / D /
       C+D, the guard spark) extracted from its ROM (tiles, palette, frames), drawn at the contact point of every hit
       (the overlap of the attack and hurt boxes), a few sprites, own palette. (Already in: debug boxes = item 8,
       P1 START; hit sounds per button A / B / C / D / C+D = item 4.) Done: KOF98 uses two sparks for everyone
       (palette $51, tiles $7C5FE-$7C65E): small (A, B) and big (C, D, C+D), 9 frames each, ~15 game frames;
       captured from MAME VRAM dumps per frame (Terry, close A / D) into tools/brawler/sparks98.json, built by
       make_sparks.py (97 tiles at 700, sparks.h); drawn at the midpoint of the attack / hurt boxes, mirrored with the
       attacker, sprites 364-375 (debug boxes now 8 per kind), palette 254, 6 sprites a line reserved in the guard.
       Big for C / D / knockdowns / specials. Seen in a fight in our emulator: flash, star, burst at the fist.

## Combo feel (Bruno, 2026-10-03)

- [x] 26. Missing attack boxes: the exporter misread KOF's box keys (low 2 bits as a slot): every C / D normal of every
       fighter (and Chang's B) had none, so AAA / AAB / BB / BAB finishers never hit. Now '1x' = attack, '3x' = hurt, and
       the box stays live over KOF's active steps ($0100). Every attack animation has its box.
- [x] 27. Multi-hit normals from KOF's step flags ($4000 = same hit): Terry close C hits twice (KOF98 measured in MAME:
       Terry / Chang close C, Yamazaki / Billy close D), damage split, knockdown on the last hit. Seen in our emulator.
- [x] 28. Hit-stop 4 / 7 -> 13 frames for every hit, light ones included (KOF98 measured ~10-12). Tested: 13 on close A,
       far A and both close C hits.
- [x] 29. Final Fight chain window: a route step that hit continues on A / B up to 30 frames after it ends. Tested: close A,
       wait, far A, wait, close C (2 hits, knockdown).
- [x] 30. Hitstun x3: 36 / 54 frames.
- [x] 31. No animation cutting: a press during an attack is remembered and the next route step starts when the attack's
       animation has finished (the `cancel` column is gone). Tested with A every 8 frames: close A plays its 3 steps, then
       far A, then close C.
- [x] 32. Hit-stop -20 %: 13 -> 10 frames.
- [x] 33. A route (Bruno): far A, far A, close C, close D, C+D (knockdown). KOF98's C+D is state 116, the move the
       export calls body_toss. Presses during hit-stop are kept now (a tap inside the freeze was lost). Tested with one
       tap per move: 6 hits (close C twice), C+D knocks down.
- [x] 34. Groups take the hits together: normals' attack boxes reach at least 96 px forward (KOF's: 32-148 px, so an
       enemy behind the first one dropped out of the route). Tested: two enemies 14 px apart take all 6 hits of the A
       route on the same frames and fly together on the C+D.
- [x] 35. AI walk/idle flicker (Bruno): enemies switched walk <-> idle up to 286 times in 20 s, mostly within 10 frames
       (hover dead band = step-stop-step, and half speed by skipping every other frame = an on/off walk intent). Now:
       hoverers walk all the way to their spot and set off again only beyond 16 px / 8 px deep; half speed is a 16.16
       sub-pixel step every frame (intent `slow`); AI fighters go walk -> idle only after 10 frames without a walk
       intent (Bruno asked 1 s; 60 frames left them walking in place a second after every real stop, measured).
       Measured (harness, 1200 frames): 13-21 switches per enemy, 0-2 under 10 frames, 13-22 frames walking in place.
- [x] 36. tools/brawler/harness.py: the core driven from Python frame by frame (RAM read/write, fighters decoded from
       fighter.h offsets, place/force, hit log, save states, screenshots). Route check, 14 fighters x 3 routes vs two
       dummies: every hit lands on both together, hit counts = the data's.
- [x] 37. One hit sound per attack per frame, however many enemies it hits (each victim queued its own: 3 enemies = 3
       sounds). Harness: 1 / 2 / 3 enemies hit at once -> 1 sound each time; sparks stay one per victim.
- [x] 38. Attacks travel as in KOF (Bruno: C+D felt like push-back baked into the animation): KOF moves the fighter with
       animation command $FB (x, before a step), which the parser skipped, so every normal played on the spot. Now
       parsed into bstep_t.dx and applied as the step starts. KOF98 MAME travel = data sum for Terry 85, Ralf 80, Chang
       56, Mai 26 px; our game: Terry's C+D 85 px.

## AFK work (Bruno, 2026-10-03 15:15) — the loop takes the first open item, notes progress under it

- [x] 39. KOF94 support in the dictionary tools: locate KOF94's animation / frame / sprite-def / palette tables
       (start from tools/kof95/rom.py, KOF95's engine is KOF94's successor; confirm every address in the ROM and in
       our emulator), frames + palettes decoded and rendered to a contact sheet that matches the game.
       Progress: tables found = KOF95's: animations $080000 + id*4, sprite defs $080080 + id*4 (30 ids; 24
       fighters + Rugal 24 + Omega Rugal 25 + effects 26-29). KOF94 sprite defs always use 16-bit column bitmasks
       (neosdk read_sprite_def 'word' mode; KOF95's exporter assumed 8-bit for short sprites). tools/kof94/ids94.py
       renders every id's idle frame: shapes right. Ids by shape: 0-2 Ikari, 3-5 Psycho, 6-8 Japan, 9-11 USA (where
       KOF95 has the rival team), 12-14 Korea, 15-17 Fatal Fury, 18-20 AoF, 21-23 Women, 24 Rugal, 25 Omega Rugal.
       Palettes NOT solved: 44 tagged blocks at $71000 (stride $400), block = id fits some fighters, not Terry/Andy/
       Benimaru. Next: attract demo in our emulator, PALDUMP + VRAMDUMP during a fight, match the real palettes.
       Done: palettes solved from the game's own loader ($330E / $336A, found from a demo fight's palette RAM):
       palette n at $6F000 + n*32 (colour 0 = tag); first palette of (id, colour set) = word table $33D2 + (2*id + set)*2
       ($380 + 14 per entry: 14 palettes per fighter per set); a sprite part uses base + (sdef byte 2 high nibble - 1).
       Player object: id word at +$70, colour set +$D8, palette slot +$30. tools/kof94/ids94.py sheet: all 26 right.
       Cast: 0 Heidern 1 Ralf 2 Clark | 3 Athena 4 Kensou 5 Chin | 6 Kyo 7 Benimaru 8 Goro | 9 Heavy D! 10 Lucky
       Glauber 11 Brian Battler | 12 Kim 13 Chang 14 Choi | 15 Terry 16 Andy 17 Joe | 18 Ryo 19 Robert 20 Takuma |
       21 Yuri 22 Mai 23 King | 24 Rugal 25 Rugal (torn jacket) | 26-29 effects.
- [x] 40. KOF94 USA team (Heavy D!, Lucky Glauber, Brian Battler): animations, boxes, physics, palettes exported in the
       KOF95 layout; brawler subset via export_bm.py; checked in a test ROM (not published).
       Progress: slots = KOF95's for jumps/crouch/normals 82-101/trip 67/knockdown 74/down 78/getup 80; differences
       seen on Terry: light hit 57 (54 empty), no run (49-56 empty), no C+D (34 = a standing pose), win 36, flight 72,
       bounce 74, fall 75 (to confirm in play). Physics record $6D2B8 + id*128 (+$24 walk, +$28 jump, +$2C gravity;
       Terry = KOF95's exactly). Boxes: attack 1x, hurt 3x AND 4x (export_bm only took 3x); step flags have $0100
       active but no $4000 (multi-hit unknown: consecutive active steps = one hit for now); $FB moves as KOF98.
       Next: tools/kof94/export94.py (export96-compatible JSON + kof95_c1/c2), export_bm dispatch on 'kof94', test ROM.
       Done (15:31): tools/kof94/export94.py (CAST: heavy_d, lucky, brian, ..., rugal, rugal2; export96 layout) +
       export_bm dispatch on kof94 (hurt boxes now type 3 and 4, harmless for KOF96+); HUD portraits from ROM
       (portraits.py table94: effect table 28 2x2 sdefs, palette 8 of the set; King/Terry/USA checked), make_hud crop.
       Test ROM (not published, CHARS = USA team + 11 of the roster, /data/tmp/brawler_usa.neo): select screen with
       the KOF94 portraits, Heavy D! as P1, Lucky / Brian as enemies in their colours, A route hits with sparks,
       knockdown flight / down / get-up play right on Lucky. Not done: their throws and specials (KOF94 capture
       tooling = KOF95's, not run), multi-hit normals unmeasured, run = walk, C+D = far D (KOF94 has neither).
- [x] 41. KOF94 both Rugals (Rugal, Omega Rugal): same as 40.
       Done: the bosses' normals are compacted (suited Rugal 8 slots 82-89, Rugal 2 = torn jacket 12 slots 82-93), so
       export94 now finds every move through KOF94's per-fighter game-state map ($7BF48 + id*4 -> word per state, low
       byte = slot; code $4860): each brawler move = the game state Terry's map sends to Terry's slot. E.g. close C:
       Terry 92, Rugal 85, Rugal 2 87. Both forms share Rugal's palettes and one HUD portrait (table 28 sdef 96). No
       win pose (idle). Test ROM /data/tmp/brawler_rugal_aioff.neo: Rugal as P1 vs Rugal 2, A route 7 hits ending in a
       knockdown, portraits right. The HUD shows the second form as RUGAL2 (export name).
- [x] 42. KOF97 support: rom96.GAMES entry (KOF97 = the KOF96/98 engine family): table addresses confirmed, frames
       rendered to a sheet that matches the game.
       Done: KOF97 = KOF98's layout: animations bank 2 $200002, frame records bank 1 $200002, state map $AFBCA
       (code $5A48 = KOF98's $5DAC), sprite definitions bank 1 $250000 (code $5A6E; KOF98 $240000), palettes bank 2
       $2CFFF0 + n*32 (loader = KOF98's at $4AD6...), body n = $100 + id*$40 + $10*set + k as KOF98. All found by
       matching KOF98's code bytes around each address. rom96.GAMES['kof97']; tools/kof97/ids97.py sheet: 35 tables,
       all 32 fighters in their colours. Cast = KOF98's first 28 (kyo .. iori) then 28 Iori (Riot of the Blood),
       29 Leona (Orochi), 30 Orochi, 31 Shingo; 32-34 effects.
- [x] 43. KOF97 Orochi: same as 40 (boss: check its special frames / size against the 20-column sprite block).
       Done: export96 knows kof97 (CAST97 = KOF98's first 28 + iori_riot, leona_orochi, orochi, shingo; MOVES97 =
       KOF98's states minus the win poses, which are elsewhere in KOF97; physics walk $A3710 / jump $A3790 = KOF98's
       values; palette base per game, PAL_ROM). Orochi: 72 frames, widest 8 columns, 10 rows (fits); his boss map
       sends missing moves to what he has (no run / C+D: idle). HUD portraits (portraits.py table97): effect table 34
       sdef 302 + id, 3x2 tiles, body palette 15 (checked on Andy in a demo fight: tile $C2C7, palette RAM 31 =
       ROM $20F). Test ROM /data/tmp/brawler_orochi_aioff.neo: Orochi as P1 in his colours with his portrait, A / far
       A hit; his close C is a rising float that whiffs, so his A route stops at 3 hits (boss data).
- [x] 44. KOF98 sound engine deep dive (docs/kof98_sound_driver.md): Z80 M ROM memory map, command protocol from the
       68000 ($07 unlock, $1A sfx, $1C voice, tracks $21-$3F), timer / IRQ setup, YM2610 register use per channel
       type (FM, SSG, ADPCM-A, ADPCM-B), song data format (table -> per-channel streams -> opcodes), instruments,
       how sfx steal channels; verified by tracing our emulator (Z80 trace) against the disassembly. Ends with what
       our own driver should copy and what it should do differently.
       Progress: KOF98's M ROM (256 KB) = the v1.7 driver already documented in docs/v17_bytecode.md and
       docs/v17_opcodes_complete.md (code $0000-$2C48 byte-identical to the jukebox / soccerfury_player M1), string
       "Sound Driver(ROM)Ver 1.7 98/06/16 To SNK". NMI $0066: command from port $00; 3 = reset at once ($0DC9), 1 = at
       once while $FDBA = 0 ($0DBB), others queued in a 64-entry ring ($FD25, write index $FD67); every command echoed
       to the 68000 on port $0C (reply latch), port $00 written to acknowledge. Reset $00B0: IM 1, RAM $F800-$FDDD
       cleared, YM writes $27=$30 (timers), $21=0, ... IRQ $0038 -> $194C (timer ISR, see v17_bytecode.md).
       Next: main loop / command dispatch, song table, then ground truth = MAME Lua tap on the sound CPU's YM writes.
       Progress: docs/kof98_sound_driver.md started: ports and map, vectors, NMI ring + reply, main loop dispatch
       ($3038 type table), all system commands ($07 unlock = clear music mute + re-arm Timer B), effect prefixes
       ($1A/$1C/$1E/$1B/$17/$16/$1D = slots 1-7: the 68000 picks the channel), ADPCM-A sample records
       [priority][start][end][pan|level] and the priority-stealing allocator over ADPCM-A 1-3, song header (11 enable
       bytes, tempo, 11 stream pointers, bank sets $2708), stream = varlen delta + running-status opcode (corrects
       v17_bytecode.md). Next: MAME tap of YM writes for one song as ground truth, then a decoder checked against it.
       Progress: tools/kof98snd/ymtap.lua (MAME: every YM2610 write of the sound CPU + every 68000 command; the I/O
       tap must cover $0000-$FFFF: OUT (n),A puts A on the upper address lines), keyons.py (key-ons per channel),
       song98.py (decoder: banks, header, varlen delta, running status, flow). Boot capture: $01 $03 $03 $01 $03 $07
       $21 (intro song). Song $21 decodes to 'end' on all 11 channels; FM1's first notes land on the captured key-ons
       at 0.574 frames per tick (104.5 ticks/s, tempo byte 129), then drift (41/77 within 1 frame); FM2-4 and the
       ADPCM channels don't line up yet. Next: find the drift (tempo op $10, loop counts, ties), then map the music's
       ADPCM-A channels to hardware channels.
       Done: docs/kof98_sound_driver.md (protocol, dispatch, every system command, effect slots + ADPCM-A priority
       stealing, sample records, song header, stream encoding, corrected opcodes, instruments, recommendations).
       song98.py validated on song $21: all 11 channels (FM 1-4, ADPCM-A 1-6, ADPCM-B; no SSG) decode to exactly
       their captured key-on counts, each note within 3.8 frames. Corrections to v17_*.md found on the way: stream
       = length varlen + running-status opcode (not "$C0-$FE duration"), $07/$08 loops, $09/$0A call/return, $0C
       queue command, $1A/$1B SSG mixer/envelope, $0D 1 byte, header channels 4-9 = ADPCM-A 1-6 (not SSG).

## Campaign (Bruno, 2026-10-05)

- [x] 45. Campaign mode, Streets of Rage 2 / Golden Axe style: Robo Army stages 0, 1, 3, 4, 5 in one ROM, 5 wave locks
       a stage (camera stuck until the wave is beaten, then GO), 2-6 enemies a wave rising per wave and per stage,
       later stages hit harder; a boss at each stage's end with minions in minion-only colours (tints), boss bar, own
       theme slot, AI that jumps in and uses specials more; bosses locked on the select screen until beaten (BOSS
       UNLOCKED screen); congratulations after stage 5; save (MVS backup RAM block / AES memory card, SNK conventions,
       sdk neo_backup.h): furthest stage + unlocked bosses, title CONTINUE, A+B+C+D 2 s resets. README "Campaign" /
       "Save". Proof: /data/tmp/campaign/out (harness, real game path).
- [ ] 46. Rugal (KOF98) and Goenitz (KOF96) as bosses 4 and 5: they plug in by export name when added to CHARS (main.c
       BOSS[]); their HUD portraits need fix palettes past 15 (2 + fighter): share or move them.
- [ ] 47. Boss themes: convert Mr Big (AOF2), Krauser (FF Special "Kaiser Wave"), Geese (FF Special), Rugal (KOF98),
       Goenitz (KOF96) and put their command bytes in BOSS[].song (placeholders: $27).
- [ ] 48. MVS save commit: the BIOS writes the backup block to battery RAM only when the game returns control; a stage
       cleared then powered off mid-run is lost on MVS (AES card saves at once). Decide whether that is acceptable.

## Bruno, 2026-10-05

- [ ] 49. "Please continue" screen: when the last life is gone, an overlay over the frozen fight with a countdown
  9 -> 0 (START / a coin continues: the player comes back where he fell); at 0 the GAME OVER game state, its own
  screen and music, then back to the attract mode.
- [ ] 50. SSG sounds for the menus: the YM2610's SSG (3 square channels + noise) as a sound layer of its own on top
  of the music (FM) and the PCM sounds (ADPCM-A / B) — check how free it really is in the KOF98 driver (which SSG
  channels its songs / SFX use, the command that plays an SSG sound). Identify the SSG routines and their data in
  Fatal Fury Special and KOF94 (MAKOTO drivers: tools/makoto3), capture them in our emulator, and build a small
  set of menu sounds (cursor move, select, cancel, unlock) the game can trigger alongside everything else.
- [x] 51. Character select as a group photo: the fighters stand in rows like a school photo, front row the playable
  ones, the back row(s) the bosses. A slot layout independent of the characters (slot = row, x, depth, scale /
  priority; a table maps fighters to slots, so a swap on screen is a table change). Look for a "neutral" stance:
  facing the viewer / watching the action, like the background characters in KOF94 / KOF95's stages — find which
  frames those are (the stage audience sprites, or the fighters' own win / intro / taunt poses) and whether every
  fighter has one.

  Done 2026-10-05 (not committed): README Character select; proof /data/tmp/groupphoto/out (groupphoto_sheet.png).
## Open work (2026-10-05) — the 10-minute loop takes the first unchecked item of "Loop queue", one agent at a time

### Loop queue (in order)
- [x] 52. (done 2026-10-05, docs/brawler_data_model.md "Stages tab") Brawler Lab tab: Stages / Waves — background picker (previews of the extracted backgrounds), music picker
  (Song Lab playback), the wave designer: the stage as a horizontal strip with its lock points, enemies dropped onto
  each wave (side, delay, count), a timeline of who comes in when; installs live through the data-pack path; same
  Oros-login site as the Chain Lab (canneji /brawler-lab/).
- [x] 53. (done 2026-10-05, docs/brawler_data_model.md "Enemies tab"; proof chainlab/enemy_proof.sh: page = desktop core 1494 ticks, palette RAM = swatches, packs = build_tables.py) Brawler Lab tab: Enemies — base picker, palette editor (from a colour set / tint / custom 16 colours, live
  sprite preview), AI preset + override sliders, life / power, trimmed move list (a Chain Lab tree), test it live in
  the enemy-test mode (lab.req = 3).
- [x] 54. (done 2026-10-05, docs/brawler_data_model.md "Characters tab"; proof chainlab/char_proof.sh: Terry up+D 214D -> 426D live, page = desktop core 536 ticks, packs = build_tables.py; every special in the ROM, pack v2) Brawler Lab tab: Characters — fold in the select-pose picker (the judging UI), the Chain Lab, the specials
  mapping (each slot picked from the captured specials with impact pictures).
- [x] 55. (done 2026-10-05, docs/brawler_data_model.md "Voices"; 299 voices of the 16 fighters listed with WAVs (tools/brawler/voices.py: $FC scan + captures in our emulator, each sample found by its own driver), all 16 on as KOF's own by default (148 samples, V ROM 3.94 MB), voice_proof.py: Terry's / Kyo's specials and hit voices play KOF's own sample byte for byte, a lab edit live through pack v3) Voices: list every fighter's voices (static scan of the FC 00 <index> play-sound records + a sound capture
  of each special for the KOF99-style code-sent ones), a roster "voices" field, and the lab's suggested voice per move
  with an override.
- [x] 56. (done 2026-10-05, docs/brawler_data_model.md "Triggers and drama mode"; each boss's entry scene with its KOF96/98 win-screen portrait (big_portraits.py, C ROM 15.56 MB), screenshots /data/tmp/drama/out; chainlab/trigger_proof.sh: a trigger added in the page spawns at +120/+180 ticks, page = wasm = desktop 1494 ticks, pack v4 = build_tables.py; campaign29 through, regress bleed True) Triggers + boss drama mode: triggers (camera x / wave clear / time: spawn, lock, music change, drama), the
  boss entrance speech in drama mode (black bars, big portraits, text lines), per boss in game.json.
- [x] 57. (done 2026-10-05, README "Continue / GAME OVER"; /data/tmp/continue/cont.py on SNK's MVS BIOS (us) + UniBIOS-AES: overlay 9 -> 0 at 60 ticks a number, A skips one, START continues where he fell (x 93 -> 93, 3 lives, the fight song back), 0 -> GAME OVER screen + $26 -> SYSTEM_RETURN -> demo, 2P count in the HUD then the shared overlay; regress bleed True, campaign29 log unchanged; SNK's MVS BIOS: P2 needs coin slot 2) TODO #49: the "please continue" overlay (9 -> 0), GAME OVER state with its screen and music, back to attract.
- [x] 58. (done 2026-10-05, docs/brawler_data_model.md AI table; jump_in for any enemy (token holder) + air_cd + back-hop hop_dx/hop_chance, pack v5; VIPER on: 7 jump-ins + 4 back-hops in 1800 ticks of the enemy test, 4 air hits landed, lab jump_chance 0 -> 0 / 64 -> 4 jump-ins live, page pack = build_tables.py; campaign29 log, ramtrace attract + campaign tick-identical to 0.0.39, bleed True) Regular enemies jump (only bosses do): an AI preset field, default off for today's minion preset.
- [x] 59. (done 2026-10-05: KOF96's own 214C never hits a standing P2 (its boxes sit above his head, an anti-air: 0 hits at 20-200 px in our emulator), so not an export error; up+D is now 214A (same move, the forward wind): KOF96 hits at 20-110 px (7/6/3/1 hits at 20-50/80/110, 0 at 120), brawler 10 hits at 20-120, 0 at 140; check_specials 13 hit rows; regress bleed True, campaign29 through) Goenitz's up+D (214C) only hits point-blank: compare with KOF96's own range, fix the export or pick another
  special for the slot.
- [x] 60. (done 2026-10-05: KOF98 really hits once, no fix: our emulator, P2 at 24/36/48/64/80 px -> 1 hit (frame 9), 96 px -> 0; state 196's ROM steps: active 1 ($4704, $4000 same hit) + 2 ($0700), step 4 only re-shows the hit pose inactive ($0600), the likely '2 hits' misreading; brawler 1 hit, frame data '1'; also equal KOF98 = brawler: Terry 6A 2 / close C 2, Kyo 6B 2 / 3D 2, Yamazaki 6A 2 / close D 2; regress bleed True, campaign29 through) Terry's down-forward+C hits once in the brawler, KOF98 may hit twice: measure in KOF98 (our emulator) and fix
  the export if needed.
- [x] 61. (done 2026-10-05: RBFF1 = MAKOTO v3, AOF3's code with other tables, 34 songs 31651/31651; Special = SNK Ver 1.1, KOF97's build byte for byte, 27 songs 36573/36573; RBFF2 = SNK (ROM)Ver 1.6, KOF98's code + Ver 1.0's operator effects, 35 songs 42466/42467; fight themes from the 68K tables by fighter id, all measured; on canneji Song Lab, docs/rbff*_sound_driver.md + rbff*_songs.md) Real Bout Fatal Fury music (1, 2, Special) into the Song Lab (the queued music item), published.
- [x] 62. (done 2026-10-05: tools/kof95/gallery.py; page = roster index (47 KB, was 13.7 MB), each fighter fetched when opened, only on-screen thumbnails animate and redraw on step change; KOF98 headless Chrome CPUx4: first fighter 2.9 s -> 0.7 s, heap 126 -> 44 MB, 27 thumbs on screen 12.8 -> 2.9 ms/frame; data identical per fighter; republish all four) Animation Bank pages: lazy per-fighter loading, animate only the visible ones (the page Bruno found slow).
- [x] 63. TODO #50: SSG menu sounds: done 2026-10-05: CURSOR / CONFIRM / CANCEL / UNLOCK as SSG cues $74-$77 on KOF98's own type-5 path (all of the SSG is free), wired into title / options / select / BOSS UNLOCKED; docs/kof98_sound_driver.md "SSG cues", tools/port/ssg_cues.py.
- [x] 64. (done 2026-10-05: 15 names in songs.json from the KOF98 moves using each hit kind (captures + the ROM's $1B8 writes, hitsfx.py) and WAV spectrograms of each code in our emulator (/data/tmp/sfxnames); sound player AES screenshot fits (16 cols); regress bleed True) Sound player: name the "SPECIAL HIT n" effects (what each sound is), in songs.json's sfx names.
- [x] 65. Vertical parts of Robo Army (areas 2 and 5): the descent as an auto-scrolled transition between stages
  (docs/brawler_stage_vertical.md option b). Built (1a0b555), then dropped by Bruno in review round 1 ("i don't want
  descend"): reverted in 7adc3e3; the stages stay horizontal only.
- [x] 66. (done 2026-10-05: landing = KOF's land animation, 4 frames (Terry / Rugal / Goenitz 5, K' 3), every fighter equal to the jump captures; projectile pool 4 -> 8 in 10-sprite blocks, Blitz Ball's 4 trail objects as KOF96; Mr. Big's colours equal KOF96's ROM, its tan is the stage's light (R +2 / B -1 on every fighter); KOF96 $26 / $29 / $2C register-identical (patch effects, B slur key-off, 16-bit tempo accumulator); attract logo 17 s -> demo 30 s (#25); proof /data/tmp/gaps66/out) Small gaps: landing 2 frames vs KOF's 4-5; projectile pool of 4 (trails thinner); Mr. Big's pale colour set
  vs KOF96's tan; KOF96 songs $26 / $29 / $2C 98-99 % model match; the attract cycle with logo / title timing (#25).

- [x] 71. (done 2026-10-05: A attack via route trees v4 (close / far / crouch / forward / back / air by stick + position), B jump + jump-cancel links -> air sub-routes, A+B = the six slots with a 2-frame chord (A-B / B-A), C fury = per-fighter DM from game.json `fury`, D read only; special meter 120 (special 30, fury 60 from 60, +1 / 10 frames, double + white flash out of a hit) with a HUD bar; Terry + default trees + Chain Lab re-authored; tools/brawler/controls_proof.py all 18 fighters ok, campaign29 through, regress bleed True, Chain Lab proof identical; /data/tmp/controls71/out) Controls revamp (Bruno, 2026-10-05): A attack (all normals via routes: direction + position), B jump (also a
  jump-cancel link in routes, on hit only -> air sub-routes), A+B SPECIAL MOVES = the six slots by direction (N, fwd,
  down, up, down-fwd, up-fwd; Power Wave, Power Dunk, Rising Tackle...; also from a grab), C FURY = desperation moves
  (Power Geyser and the other KOF DM / SDM supers, SS4 rage moves), D TAG mode (Bruno will explain). Chord detection
  window (2-3 frames) for A+B; routes / Chain Lab glyphs / Terry's routes and the default trees re-authored for one
  attack button. After the six-slot job.
  SPECIAL METER (Bruno, 2026-10-05): a meter gauge, full at the start; each special move consumes meter; the meter
  refills slowly over time; a special triggered WHILE BEING HIT (allowed: a "get out of trouble" move) costs twice as
  much, and the player's palette flashes fully white for a split second to show something was consumed. Furies (C):
  cost to be decided (default until Bruno decides: the same meter, half the gauge, only
  usable from half full; a data value, easy to change).
  QUEUED FIRST by Bruno (2026-10-05): the loop takes it before #67-#70.

- [x] 67. (done for Haohmaru, 0.0.42+; the other SS4 fighters wait for Bruno: "we'll do more characters later on") Samurai Shodown IV fighters into the character bank (Bruno: "start with Haohmaru first"): a full SS4 exporter
  (study: /data/neogeo_dict/samsho4/README.md — own engine, 444/454 frames pixel-exact): Haohmaru end to end into the
  brawler (animations, palettes, boxes, specials, weapon objects as needed), then the others. Running in a worktree
  since 2026-10-05.

- [x] 68. (done 2026-10-05: Haohmaru + Hanzou in the Lab with pose pickers, move / special / enemy pictures (frames pixel-equal to SS4 / WHP renders), their own voices (SS4 28, WHP 8, mapped by default, lab override; WHP's ADK driver read by capture), Lab redeployed) Brawler Lab for Samurai Shodown IV fighters: the pose picker (char_images.CANDIDATES has no samsho4 list: Haohmaru
  is skipped), check move / special / enemy pictures for samsho4 banks; Haohmaru's SS4 voices (voices.py covers KOF only).

- [x] 69. (done 2026-10-05: 65 of the KOF fighters' slot specials play from the ROM (46 KOF98, 19 KOF96), each 0 frame mismatches whiff + hit; left as captured scripts: Ralf AAAA, EX Ryo 646A, Robert 426B / EX 646D, Yamazaki 214A, Billy CCCC / 623D, Kyo 421B / EX 421D, Iori MAX 23624D / 623C / 624B / 214A, Rugal 624A / 6426A / 6426C, Geese 63214A / 63214C, Krauser 623B / 623D, Goenitz 214C, all of K' (KOF99 routines mapped), every fury; tools/kof96/handlers98.md) Specials from the ROM for everyone: extend tools/kof96/handlers98.py (loops, ROM state tables, inlined
  per-fighter subroutines, owner-watching effects, compare / random branches; est. 60-70 % of KOF98's 415 handlers),
  then KOF96 / KOF99 routine addresses; the captured scripts stay the fallback (Vulcan Punch, command grabs, supers).
  Proof per fighter as romspecials_check.py does (0 frame mismatches whiff + hit). Terry + Ralf done in 0.0.37.

- [x] 70. (0.0.52: 421A/B/C + Bust 236D/623D recaptured as whiffs, no hit stop / push baked; a low leap is held at a standing body, 421C lands its slash, the brawler's own knockdown; other open points listed in the memory note) Haohmaru's forward+D (SS4 421C) has a baked impact / KO scene (Bruno): recapture it as a whiff, or read it from
  SS4's own code (the handlers98 approach for SS4); also his other open points (memory reference_samsho4_extraction).

- [x] 72. (0.0.54: KOF98's reaction table read from the ROM (box id -> reaction + juggle rule, handlers98.box_react; strict box overlap): Terry 214D 2/2, 623A 5/5, 623B 2/2, Robert 624D close 3/3 (was 4), Ryo 623A 1, Ralf [2]8A 1, victims within 3 px (/data/tmp/hits72/out/table72.txt); LEFT: Robert 624D mid 3 vs 2, Ralf [4]6A 2 vs 1, Kyo 214A 3 vs 1, Kyo EX 421D 1 vs 3, Terry 623C / 623D mid hit where KOF misses (KOF's P2 is Takuma, the brawler's victim Terry: box edges), KOF96 fighters keep the old reactions, projectile victims untouched) (also from #69's notes: at its test distance Ralf [4]6A / [2]8A get extra hits, Ryo 623A 2 vs 1, Kyo 214A 3
  vs 1, Robert 624D 4 vs 3; Ralf [4]6B, Yashiro 214D, Iori 623D land none where KOF lands one; victims after projectile
  hits land far from KOF's spot) Restore KOF98's hit count on Terry 214D (2), 623A (5), 623B (2) and Robert 624D (3) (review round 1): since
  the victim fix (no stick) they hit once less; re-time the missing hit(s) so they land, without sticking the victim
  to the attacker ([[feedback_brawler_no_victim_stick]]).
- [x] 73. (done 2026-10-06: Yamazaki 214B / 214C kept as their own moves (specials96: a main-pass whiff with a new state path is a new move; 128->132 / 133), captured, 2/2 hits each as KOF, fD / dfD; Billy's angled staff = 214B (state 151, ROM frame 397), ROM-driven, ufD, 0 frame mismatches whiff + close (it hits a standing victim once where KOF whiffs Yuri: an anti-air box); Iori fD 'MAX 23624D' is now named 624D (same move); pictures /data/tmp/miss73/out) Extract the specials Bruno mapped that the bank lacks: Yamazaki's snake arm 214B (middle) and 214C (low)
  (214A exists), Billy's angled stick attack (find it in KOF98). Then apply the slot mapping from review round 2
  (artifact https://claude.ai/artifact/CpAmeQcqCtmrK9EPJ68HyM, db map/<fighter>) once Bruno says done.

- [x] 74. (done 2026-10-06: read from the ROM, handlers98 FOLLOW_CHECKS + P_CHECK / PC_LINK; followups_proof.py: game vs model 184/184 runs, brawler vs model 52/52 every chain both facings whiff + hit; romspecials_check 0 frame mismatches on 80 cases incl. 7 follow-up chains, /data/tmp/fu74/out) Follow-up specials (review round 2): moves that continue on more input. Iori's 214A is a 3-part sequence
  (each part needs its own input): reverse engineer KOF98's logic and play it. K' has many follow-ups, notably after his
  236A, which opens more routes in KOF99: read them from the ROM and support them (one follow-up mechanism for both).
  Mechanism DONE 2026-10-05 (with Kim's multipart moves): fighter.c "follow-ups", bspec_t.parts / links (export_bm
  special_parts): a special = parts (script row ranges, each with its `next` part or the end); a link from a part fires
  on a hit landed in its window, on a press in its window ('again' = the A+B role the move started with, or a brawler
  press like 'dA', 'fA', 'AB') or both, and switches at once or when the part ends. The KOF hit-confirmed continuations
  (Geese's Jaei-ken, Kyo's Kototsuki You: former bspec_t.cont) are now two parts + one 'hit, now' link. Iori's 214A =
  three parts linked by 'again' presses; K''s 236A = one part with several press links (fA, fB, ...) to its follow-ups.
  Left: capture Iori's / K''s parts and their windows (KOF98 / KOF99 ROM), as export_kz FOLLOW does for Kim.

- [x] 75. Hit sounds by use (review round 2, Bruno's listening): $9C SDM IMPACT on desperation moves' hits (the C fury,
  Yuri's Shin Shoryuken sound), $19 GRAB START when a grab / command grab connects, $17 BLOCKED HIT for guarded hits,
  $3D BACK BREAK on back-breaker throws (Krauser's), $2B SLASH for any blade hit. The menu cursor sound is to change: take
  Fatal Fury 3's own cursor sound (Bruno). Find the command FF3 sends on its menu / select cursor (MAKOTO v3.0 driver,
  tools/makoto3, capture in our emulator), and play that sound in the brawler: as an SSG cue if it is SSG, else port it
  (FM / ADPCM-A sample into the brawler's sound ROMs via songs.json).
  Cursor DONE 2026-10-05: FF3's character-select cursor is command $60, an SSG effect song (captured in our emulator:
  $60 on every stick move): a 3-voice chord, periods 141/94/138 at level 11 then 4, then 70/56/69 at 9 then 4, steps of
  2 timer-A interrupts (36.8 ms). Now songs.json "ssg" CURSOR ($74): same periods, levels and mixer ($38) register for
  register, timed 3-2-3-3 KOF98 cue ticks (each step end within 5 ms of FF3's); ssg_cues.py notes take "A5+" (half
  semitone). Checks: ssg_cues.py --check all 4 OK; select screen with 5 cursor moves vs none: the 3329 music writes
  identical; regress no-bleed True. WAVs to compare: /data/tmp/ff3cursor/out.
  Done 2026-10-06: fury hits $9C, grab / command-grab catch $19, Krauser's back breaker $3D, Haohmaru's slashes $2B (game.json roster[].hit_sfx, bchar_t.sfx, export_bm move_fx); $17 not wired: the brawler has no guard.

- [x] 76. (0.0.53: his multipart moves + the Phoenix's on-connect sequence and flames play, one follow-up mechanism;
  left: the Phoenix's red backdrop (the brawler shows the empty stage ~12 frames while both fly off-screen), random
  flame feathers replayed as captured, j.2B > 2B follow-up 92 not played) Kim Young Mok leftovers (0.0.50, tools/kizuna, /data/neogeo_dict/kizuna/README.md): his voices into the
  sound ROM (the voice build path reads KOF / SS4 / WHP, not Kizuna's driver: tools/kizuna/voices_kz.py lists 40);
  his stage song (find it among Kizuna's 23 decoded songs, port via songs.json); colour set B ($1C0) checked by eye; the 150 frames
  where Kizuna slides a part by code (6C telescopic staff). A+B dodge / C+D taunt have no brawler slot (not mapped).
  Multipart moves DONE 2026-10-05 (README "Move sub-states": decoded from the 68000 code, cross-checked by brute force
  in our emulator): 236C = 97 + 8E rush, A+B forward again during 8E -> 98, again during 98 -> 9A (Kizuna: 236C again,
  hit, whiff or block); [2]8C: down+A after its airborne hit -> 9D the dive (Kizuna: 2C, hit only); 421A on a hit ->
  101; the C fury (6246A) on a hit -> the Phoenix: 12-hit rush, flight in the flames, dive among falling flame
  feathers, the victim held where Kizuna places it (Hayate's capture), its flames drawn as script objects. Proofs:
  tools/kizuna/kim_followups_proof.py (13 scenarios x facings vs Kizuna, contact sheets /data/tmp/kimseq/out),
  kim_proof.py (every frame of every part identical to Kizuna's render, both facings). Not played: j.2B's follow-up
  (2B again -> 92: j.2B is an air normal in the brawler); the red backdrop flash of the Phoenix.
  Done 2026-10-06: (1) the Phoenix's screen effect: Kizuna hides the stage and strobes its backdrop $7DFF / $4700
  every frame from the launch hit to the dive ($3AC5C sets $27E4 / $27E1, $1FC46 alternates, $3ACDE clears); export_kz
  FOLLOW 'backdrop' -> bspec_t.bd_first / bd_end / bd_col, main.c screen_fx (stage hidden, strobe white first, stage
  back): tools/kizuna/phoenix_backdrop_proof.py (Kizuna 87 strobe frames, the brawler 83: 76 rows + its own hit-stops).
  (2) several voices per special: voices.py extras -> bchar_t.vmore [key, id, at] (fighter.c voice_at), a voice id's
  bit 7 = its game's effect channel (voices.json channel 'fx': the Phoenix's cry $1A68, [2]8C's $1A67) played on the
  other voice slot so it does not cut his shout: the Phoenix now says $1CD1 at the start and $1CD2 with the cry, 236C
  its yells per part ($1CBB $1CB5 $1CB6 x2 $1CB9), [2]8C $1CCE; Kim's voices in the V ROM 13 -> 18 of 25 (+32000 bytes of V ROM).
  (5) the "150 frames slid by code" are not a slide: step attr bit 7 (+$4F bit 2) draws parts 1 / 2 first and part 0
  in front ($14C9C; 6C's staff behind his hand, A+B, C+D): kz.draw_order; check_frames 1005 / 1066 (was 916), the 61
  left are other sprites in front of him (the hit 6C's victim) and the screen's bottom edge on landings (camera y).
  (4) colour B = Kizuna's 2P palette RAM word for word ($1C0 / $1C1 at slots 48 / 49 in a Kim vs Kim colour B fight),
  screenshot /data/tmp/kim76/out/colour_B.png. (6) Phoenix damage: Kizuna's drop is 61 of 192 = 19.06 of the brawler's
  60, the brawler deals 19 over its 12 hits (unchanged: it already matches).
  Left: (3) his stage song: Kizuna ties no stage to a character (vs: a random unplayed stage of 8, $E076; 1P: a random
  remaining opponent slot -> stage $DFA6, stage -> song $4DD18: stages 0/1 $21, 2/3 $22, 4/5 $24, 6/7 $23, 8 $2B, 9 $2C;
  the CPU team is picked apart from the stage), so nothing ported; 7 voices not mapped (alternate yells $1CBC $1CC4,
  $1CC0, the heavy-hit $1CC5, dodge $1CC9, taunt $1CCB, $1CEF: one voice per animation key); j.2B follow-up 92; random
  flame feathers (captured ones played).

- [x] 77. (done 2026-10-06: all 10 extracted, not in the build: tools/kizuna --char NAME, data /data/neogeo_dict/kizuna/<name>/, picks tools/kizuna/picks, routes tools/brawler/routes/<name>.json; every exported frame identical to Kizuna's render in a throwaway build, both facings; left: Gozu / Mezu / Joker / Gordon fury = a grab by code (no box: no hit), Chung no fury (A Chun's 6246A / 646C not captured), Hayate [2]8C boomerangs hit by code (not exported), R Shishi's 4264A / 214B not captured, projectiles drawn but no end rows) Every other Kizuna Encounter fighter extracted, NOT in the build (Bruno, 2026-10-05: "queue all characters, do
  not include them yet in the build"): Hayate, Eagle, Gozu, Mezu, Rosa, Joker, Chung (A Chun shares his animations),
  Gordon, Shishioh (R Shishi shares his), Jyazu (character ids 0-12 in /data/neogeo_dict/kizuna/README.md). Same as Kim:
  pre-scaled to Kizuna's widest zoom $CC (0.80, Bruno: "keep it at 0.80, it's on par with other characters"), every move
  with full metadata (frames, timing, boxes, damage / reaction, movement, inputs, cancels, sounds), the kim_proof-style
  render check per fighter, portraits, a starter routes file + six-slot / fury picks in a side file, banks exportable as
  `kizuna:<name>` -- but no game.json roster entry and no ROM growth until Bruno picks who goes in.

- [x] 145. (done 2026-10-06, 0.0.67) Bruno's feedback on 0.0.66 furies, engine rules (docs/brawler_move_vocabulary.md):
  fury charge sound at the super flash (KOF98's $1A $3A, its flash routine's sound index $99, DM and SDM alike: game.json
  super_flash sound, songs.json FURY CHARGE); `hit.crowd` (an eruption hits every target it touches, each once; a
  fireball still ends on its first hit); `hold.dance` (a fury's victims reel until its finisher, a hold holds the whole
  crowd, no fall on death mid-sequence, screen edge = wall 40 px in, the attacker stops advancing);
  `fx.death_voice` (the KO voice once, at the death); the flash attacker's own boxes hit during the flash (Kim's
  Phoenix connects again). Proofs /data/tmp/fury67/out: Terry's geyser 3 / 3 enemies hit (MAX: 1 + 2 + 2), Ryo 23624C
  at the screen edge (victim upright to the finisher, both visible, one KO voice at the death), $1A $3A + key-on on the
  flash frame; romspecials_check furies = 0.0.66's frame mismatches (Goenitz's first hit now on KOF's frame).

- [x] 143. (done 2026-10-06: fighter.c "cancels" (fury_cancel, fury_buf, scancel; players only, enemies keep their route links), documented as branch.cancel; cancel_proof.py all 19 ok (HEAD fails it), controls_proof / fury_inv_proof all ok, regress no-bleed True, campaign29 passes, attract + campaign RAM traces identical to HEAD) (Bruno, 2026-10-06): cancels as engine rules for every fighter: (1) any normal (A routes, air
  normals) cancels into a special (C + direction) or a fury (D / down+D MAX); (2) any special cancels into a fury.
  Defaults until Bruno says otherwise: a normal cancels on contact (hit or guard) during its active / cancel window, as
  KOF; a special cancels into a fury after its first hit lands (KOF's super cancel), the fury's flash and invincibility
  as usual. One rule in fighter.c (no per-move data), documented in docs/brawler_move_vocabulary.md; proofs: per fighter
  normal -> special, normal -> fury, special -> fury (hit and whiff), controls_proof, regress, campaign29.

- [x] 149. (done 2026-10-06, 0.0.72) Billy Lee from Double Dragon (Technos 1995) with his transformation, the variant
       table and the form link as engine features (docs/brawler_move_vocabulary.md "variant.table", "Form link"):
       tools/doubledr model_dd / export_dd (everything from DD's data: specials as programs + 4-row variant tables),
       Super Billy reachable by down+D with a full meter (not selectable). Proofs: billy_proof.py (frames = DD's
       drawing 644 / 644 both facings, every variant row = DD's model, the transformation in a campaign fight with the
       enemies attacking), progcheck_dd, controls_proof 21 ok, cancel_proof 21 ok, fury_inv_proof (AI_OFF) ALL OK,
       regress no-bleed True, campaign29 through; sheets /data/tmp/billy/out.
- [x] 144. (done 2026-10-06: the pillar = task '503 EFFE' ($509F / $5084, palette 27) the captures missed (half the task pool read); exported with 214B / 236A ADH EFFE, 421A afterimages, the Phoenix's other feathers as pinned effects (bproj_t follow bit 4); kim_effects_check.py (Kizuna's screen, every tile attributed) all ok, kim144_proof / kim_proof 1262/1262 / kim_followups_proof / controls_proof all ok, regress no-bleed True; sheets /data/tmp/kim144/out) Kim's Hienzan ([2]8C, down C) is missing its BLUE effect (Bruno, 2026-10-06): find the effect object /
  palette Kizuna draws with the rising staff (spawned object or an extra sprite part on the steps, its palette =
  blue), export it through the effects library and play it; check Kim's other moves for missing effects the same way
  (kim_proof frame-identical incl. effect objects vs Kizuna's screen, not just Kim's body).

- [ ] 145. (DONE ON BRANCH fix/145-flash-pose 2026-10-07, awaiting Bruno's review; vocabulary fx.super_flash "flash pose": fighter.c flash_pose, export_bm FLASH_POSES (each exporter exports a whole source animation on request), game.json roster[].flash_pose taunt / charge / win / intro or {anim, first, last, head}, bchar_t.fpose / fhead; poses: Kim Kizuna taunt $21, Haohmaru / Genjuro / Kuroko SS2 taunt 88, Hanzo WHP win $00 (WHP has no taunt), Billy Lee DD power-up 81 steps 0-5; the freeze shows the pose, the fury starts from its first frame after it, the glow on the pose's head point. Proof /data/tmp/flash145/out (tools/brawler/flash145_proof.py, real fights): ALL OK, the 6 fighters pose frame for frame, still, no hit in the freeze, anchor = head, fury connects after the flash; Terry's trace identical to 0.0.95's; controls / cancel ok 7 fighters, fury_inv_proof (AI_OFF copy) ALL OK, bank_proof ALL OK, regress no-bleed True, scenario lint 0; scenario145.json + clip.gif: Kim's taunt under the flash, then the Phoenix hits) Furies from non-KOF98 sources (Kim / Kizuna, Haohmaru / SS4, Hanzo / WHP, later Double Dragon) have no
  built-in wind-up under the super flash, so they whiff (Bruno, 2026-10-06: e.g. Kim). First confirm the cause (the
  rush moving during the freeze, or no pre-pose before the motion). Rule: a fury whose source has its own flash pose
  (KOF98's $FA flash step) keeps it; otherwise the engine plays the fighter's "flash pose" during the freeze, by
  default its TAUNT (Kim: Kizuna C+D taunt anim 21, ~92 f) cut to the freeze length (~28 f), a per-fighter data choice
  (taunt / charge / win pose; Billy: his power-up), then starts the fury. Concentration glow anchored on the pose's
  reference point (or the default). Proof: Kim's Phoenix, Haohmaru's and Hanzo's furies connecting on a dummy after the
  flash, contact sheets. UPDATE 0.0.67: the whiff's cause was that nobody could hit during the flash and Kim's first hit
  falls inside it; fixed (the fury's own attacker may hit during the flash). The flash pose stays wanted for
  consistency. Bruno: for these fighters the concentration glow emphasizes the HEAD (anchor = the pose's head point).

- [ ] 146. (PILOT DONE 2026-10-06, awaiting Bruno's review: Terry + Geese throws read from the ROM (tools/kof96/throwrom.py
  executes the throw routine, the victim list and the flight routine: 0 frame mismatches vs the game in our emulator,
  Geese forward+D off only where KOF's stage wall stops the bounce); control return rows Terry fC 56 (code end; lands 57),
  fD 64 (code end; lands 71), Geese fC 59 (code end; lands 64), fD 71 (step after landing 58 + 3; code end 94 trimmed),
  listed in the conversion sheets; 1x speed in data; hold hits from each fighter's own close C / close D (3-frame
  startup), Final Fight hold rule, victim always behind, thrown bodies knock down (3 of 3 in each group test). Roster-wide
  now: victim behind, thrown bodies, the hold rule + hold hits; the rest of the roster keeps its captured scripts at 1.5x
  until its pass. Proof /data/tmp/throws146/out.) THROW SYSTEM REBUILT (Bruno, 2026-10-06: the mechanics are right — walk to grab, forward / back + A to
  throw — the execution is wrong). Rules: (1) no global throw speed multiplier (the early "+50 %"): a per-throw speed
  in data, sane default; (2) a throw ends a few frames after the victim lands: the source's recovery tail trimmed, the
  thrower acts again; (3) dedicated HOLD-HIT animations per fighter with a 2-3 frame startup (a knee / elbow /
  headbutt from the fighter's own frames); (4) HOLD rule, Final Fight style: hits keep the hold, the victim breaks free
  after ~1.5 s without a hit (never while hitting), 3 hits max then the 3rd is a knockdown finisher; forward / back + A
  throws any time; (5) the PAIRED attacker / victim script (vocabulary hold.paired_script, the debt list's top item):
  per frame the victim's pose + offset relative to the attacker, checked visually throw by throw; grabbability from
  the victim's current state (the Heidern rule). Proof: per fighter contact sheets of every throw (attacker + victim
  together) and a 3-hit hold, timings logged; controls / cancel / fury proofs, regress, campaign29. NEXT after the
  Hanzo remap. ALSO (Bruno): (6) the grabbed victim is always drawn BEHIND the grabbing player, catch to release
  (data override only where a throw needs it in front); (7) NO RECORDED THROWS: today the thrower's timeline and the
  approach / post-release flight are captured on Yuri (tools/kof96/throwscripts96.py), only the victim's list phase
  comes from the ROM throw tables (throwtables96.py): decode the throw handlers' code + tables (handlers98 style) and
  express each throw through the paired script; captures only for analysis and the fidelity proof. PILOT FIRST
  (Bruno): Geese Howard and Terry only, made perfect and reviewed by Bruno, then the rest of the roster. (8) CONTROL
  RETURN POINT, chosen from the decoded code, not a fixed rule: per throw, find where the thrower is really done (the
  ROM's own release / "can act" transition, the last impact, the victim's landing) and give control back at the
  earliest step after the last impact where the thrower's follow-through is complete, so the action isn't chopped
  (no mid-pose cut) and no dead idle tail either; list the chosen frame per throw in its conversion sheet. (9) THROWN
  BODIES HIT OTHERS (Bruno, e.g. Geese's back throw): from the release until it lands, the thrown victim is an attack
  (a "body projectile": its body box as attack box) that knocks down every other enemy it touches, each once, with
  modest damage; the knocked-down enemies fall in the throw's direction; standard engine rule for every throw
  (vocabulary hold / spawn family), proof: a throw into a group of 3 enemies (how many fall).
  FEEDBACK 20261006-161058-b3f3 (Bruno in play, 0.0.71: "Here's an example of how the throws can be not fun: the throw
  of Billy Kane takes way too much time."): the replay shows Billy's forward throw (pole lift overhead, then the slam)
  holding him in S_THROW for 173 frames (2.9 s: frame 65320 to press + 76), after a 15-frame S_GRAB (65305); the
  frame before it in the window, another grab -> idle took 176 frames (65124-65300). Exactly rules (2) and (8): the
  control return point from Billy's decoded throw code (KOF98), his recovery tail trimmed; Billy joins the pilot's
  timing sheet as the worst case to measure (throw length per fighter, before / after). STATUS 2026-10-06 (after the
  pilot): the generic rules do NOT shorten it: Billy's forward+C is still a captured script, whose control return is
  its last row (thrower 173 frames at 1.5x in the roster proof, victim down on the same frame); it is the roster pass's
  first case: his KOF98 throw chains three victim lists (thrower states 198 -> 199 -> 200, tables.json: $282A78,
  $282C40, $282E08), so throwrom.py needs the list-to-list hand-over before it can choose his return point.

- [ ] 147. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; proof tools/whp/koryuuha_proof.py -> /data/tmp/var147/out/koryuuha) One handler, three presses (WHP punch command 7, D R + A / B / A+B -> $100 / $101 / $102; byte FE: no hero triple, so no hero version, and only while +$604D is clear: one Koryuu Ha in flight). Each spawns its effect $100-$102 at step 4: the same box (sets 214-216), def cycle and colours, level +$42 0 / 1 / 2, speed 3 / 5.25 / 7.5 px, two trailing parts (vx -0.5 / -0.25 px behind it, gone at its hit) that the old captured version lacked; hit 10 of 192 each. handlers_whp.koryuuha = WHP on every flight frame of the three; export_whp: one special '236P' with A / B / A+B as the variant table (pfx spawn, pvox shout), game.json D = 236P, variant A (what D played; B / AB = one word). Known: WHP cycles the projectile's palettes ($80 / $82 / $83), the brawler shows each def's own (as before). HANZO'S PROJECTILE VARIANTS (feedback 20261006-154517-b3f3, Bruno in play: "There are multiple versions of
  this projectile from Hanzo, can you figure them out?"): decode his projectile special's handler in WHP (tools/whp
  handlers_whp.py) and extract every variant (button A / B / A+B, hero version: speed, colour / palette, hits, size,
  damage) per the extract-all-variants rule; store them in the variant table (the Billy job builds it), the brawler
  plays its latched rule; sheet WHP vs brawler per variant. Close the feedback row as shipped with the release.

- [ ] 148. (REPLACED 2026-10-06, Bruno: "yes replace haoh, put the samsho 2 version": Haohmaru comes from SAMURAI SHODOWN II, exported with Genjuro (#175, same exporter, after #174), every move decoded from SS2's data: specials with their effects attached, his rage move as the fury, his SS2 throw via #146; the roster entry haohmaru switches from samsho4:haohmaru to the SS2 bank; the SS4 tools stay. The notes below are the acceptance list.) (+ 20261006-173459-5d29: "Samsho characters still don't have throws." — also Hanzo / WHP has none) HAOHMARU FROM SS4'S CODE: REAL FURY, SPECIALS, THROW (feedback 20261006-155538-b3f3, Bruno in play, 0.0.71: "I'm not sure that's the fury of
  Haohmaru in Samurai Shodown." The replay shows the fury = "BUST 236D", a powered single flaming slash). Find in
  SAMURAI SHODOWN IV's code his true super moves (its own engine: tools/samsho4, /data/neogeo_dict/samsho4/README.md):
  the Weapon Flipping Technique (rage-full super) and the Rage Explosion's Issen, their commands, conditions,
  handlers, objects, variants; D = the WFT, down+D = the stronger one (Issen or the WFT's variant, say why); decoded,
  not recorded; super flash, fury invincibility, crowd rules; sheet SS4 vs brawler. Close the feedback row as shipped.
  WIDENED (3 more notes, 0.0.71): (a) 20261006-155636-b3f3: "The dragon punch, so down plus C, the movement is
  separated from the special effect. Is this a recorded move or is it decoded from ROM?" — it IS recorded (all his
  specials come from capture_ss4.py captures; the replay shows the 623 flame arc left on the ground while he lands
  elsewhere): decode ALL of Haohmaru's specials from SS4's handlers (effects owned by / pinned to him); (b)
  20261006-155708-b3f3 + 155732: SS4 has throws ("done with C plus D ... or by walking forward and pressing forward and
  C"; "the opponent is kind of thrown on the other side"): decode SS4's throw command + Haohmaru's throw animation and
  victim handling and express it through #146's standard throw (walk-in grab, forward / back + A, the paired script,
  the rules) — after #146's Geese / Terry pilot is approved. Haohmaru = the first fully ROM-decoded non-KOF fighter.
  PROGRESS 2026-10-06 (worktree branch worktree-agent-ad6294cbf3aee0c90, with #175 / #176): Haohmaru is now SS2's
  (samsho2:haohmaru, tools/samsho2/export_ss2.py + handlers_ss2.py; SS4's tools kept): every special decoded from its
  action handlers (236S tornado, 623S Kogetsu Zan with its crescent pinned to him for its life, 623K, 236K, 214A sake),
  A / B / A+B as the variant table (623S on the A row: B / A+B rise 135 / 268 px), the fury = SS2's weapon-flipping
  technique (rage-only, one button: no MAX), his throws (slash 274 / kick 346) as paired scripts from the class 4 / 5
  handlers. Proof /data/tmp/ss2/out: acceptance.json (fury = WFT, the crescent at offset 0, 0 every frame it lives,
  the throw: GRAB -> THROW -> THROWN -> DOWN), frames 542 / 582 identical vs SS2 both facings, specials_haohmaru.png.

- [ ] 150. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; proof /data/tmp/boss172/out dance150.json +
  dance150_3.png / dance150_1.png, tools/brawler/dance150_proof.py) Fix (vocabulary hold.dance (d)): fighter.c react checks the
  dance before the juggle re-launch: a fury's reel hit on an airborne victim catches it (fighter_hit takes the packed
  reaction's standing half for a fury's reel): S_HITSTUN, vx 0, down to the floor at DANCE_DROP (2x the knockdown gravity),
  then the dance as on the ground; kof_react no longer turns that reel into an air knockdown. A dead body (life out) is no
  target any more (KOF's way, dead_body: hits, thrown bodies, the hold crowd, grabs, a ROM special's nearest opponent),
  only the fury still dancing it hits it on. Proof (AI_OFF build): Robert 23624C and Ryo's fury, victim put at 40 px 3
  frames before the ground case's first hit: 14 / 14 dance hits land in both (= the ground case), HITSTUN from the first
  hit to the finisher, vx 0; the group (the note's scene: + a dead body in its KO flight across the rush, + one standing
  behind): the dead body 0 hits, falls, dies; fury_inv_proof ALL OK, cancel_proof all ok 23, controls_proof ok, regress
  no-bleed, campaign29 through the 5 stages.
  A DANCE FURY HITTING AN AIRBORNE VICTIM (feedback 20261006-160204-b3f3, Bruno in play, 0.0.71: "When the dance
  fury of Robert is already started and somebody is in the air, and there's an impact, the victim does not get kind of
  stuck to Robert, it just bounces away and Robert keeps doing the dance on his own."). Replay: Robert's A combo KOs two
  enemies at frames 34978-34999 (life -10 / -7) and launches them (KO flights up to y 108 / 94); D at 35023 starts his
  fury (23624C, the rush moves him 118 px in ~30 frames after the flash); at 35072 (P-20) the rush hits fighter 7 (Mai)
  at height 41 px: she is sent up again (y 41 -> 93) and away, Robert dances alone to the press (35092). Cause:
  fighter.c react(): `if (v->y > 0)` = a juggle re-launch (vy 4-5, vx 1.5 px) BEFORE any dance check; hold.dance only
  holds a victim reeling on the ground. Fix (engine rule, vocabulary hold.dance (d), no per-move data): a dance hit on
  an airborne victim catches it: its flight stops (vx 0), it drops to the ground fast (2x gravity, a few frames) and
  reels there in front of the attacker as a ground victim, so the next dance hits connect and only the finisher
  launches; a dead body still in its KO flight (life <= 0) is caught the same way (or, KOF's way, is no longer a target:
  Bruno to pick). Proof: Robert's 23624C and Ryo's dance on a victim launched by a combo (alive and dead), every hit of
  the dance landing (hit log), contact sheets; fury_inv_proof, cancel_proof, regress, campaign29.

- [ ] 151. FURY -> MAX FURY CANCEL (feedback 20261006-160257-b3f3, Bruno in play, 0.0.71: "A steel cannot cancel a fury
  into a MAX Fury." = "I still cannot..."). Replay: Robert's fury from D at frame 37971 (P-131), its rush lands on
  Yamazaki (~38022); from 38044 (P-58) he presses down+D again and again (38044, 38054, 38063, ...): nothing happens, the
  fury plays to its end. Cause: #143's rule (2) is `f->spec_id != BS_FURY` (fighter.c, the fury_buf buffering and the
  S_SPECIAL cancel test): a fury never cancels. Fix: branch.cancel rule (3): a fury (not a MAX) whose first hit
  landed cancels into the fighter's MAX fury on down+D (on the ground, not while it holds a caught victim), the MAX
  from its start with its own flash (orange), charge sound, invincibility and meter cost (a MAX is never cancelled
  further; a MAX is played with spec_id BS_FURY today, so the fury needs a "MAX" flag to tell them apart). Same rule
  for every fighter, documented in docs/brawler_move_vocabulary.md branch.cancel; cancel_proof.py gains fury -> MAX
  (hit and whiff) per fighter. Quick (< 1 h + proofs).

- [ ] 152. BILLY KANE'S FURY = THE FIRE RING (feedback 20261006-160855-b3f3, Bruno in play, 0.0.71: "That's not the
  standard fury I would like Billy Kane to have, I want this other one with the circle of fire."). Replay: D at frame
  58693 (P-14) starts game.json's fury "236236C" (KOF98 slot 10: the leap with the red pole whirl, no fire; seen
  continuing from the press state). Billy's other KOF98 DM is slot 11 "23624C" (MAX: "MAX 23624A"); played in a test
  build (fury = 23624C, harness, a dummy at 70 px): it is the flaming ring, hits, ROM-decoded like the rest. Fix: game.json
  billy fury "23624C"; down+D = its MAX: export_bm.fury_max_special looks for 'MAX 23624C', which KOF98's export
  doesn't have (only 'MAX 23624A'): fall back to the same command's MAX on another button (or a roster "fury_max"
  field) so down+D doesn't silently play the plain fury. Quick (< 1 h): data + the fallback, romspecials_check,
  fury_inv_proof, a sheet for Bruno.

- [ ] 153. BILLY KANE'S DIAGONAL SPECIAL (feedback 20261006-160912-b3f3, Bruno in play, 0.0.71: "The diagonal move,
  that's not the one I expected."). Replay: up-forward + C at frame 59608 (P-20) plays slot ufD = "214B" (a step-in
  overhead pole strike, ~60 frames to recovery, seen continuing from the press state). Billy's slots: C = CCCC (fire
  pole spin), forward = 426C, down = 623C, up = 623D, down-forward = none (null), up-forward = 214B; his KOF98 moves not
  in a slot: AAAA, 426A, 623A, 623B, 214D (other-button versions). NEEDS BRUNO: which move he expected on the diagonal
  (and the empty down-forward slot): a pick round in the Lab's Characters tab (the specials mapping with impact pictures,
  #54) or the interactive judging page; then a game.json change (quick).

- [ ] 154. (+ 20261006-173221 / 173232 / 173249-5d29: the stage-clear and ending music "not fitting", "weird": pick congratulating tracks in the same audition) CONTINUE AND GAME OVER MUSIC (feedback 20261006-160529-b3f3: "The music is incorrect on the continue screen."
  and 20261006-160539-b3f3: "The music is also incorrect on the game over screen."). Replay (driver command = RAM
  snd_song): CONTINUE? opens at frame 46799 with $2F, GAME OVER at 47290 with $26: what game.json music / songs.json
  ask. Both play exactly as in KOF98 (compare_port.py on the build: CONTINUE 8 / 8 chip events identical, GAME_OVER 1158
  / 1165, 7 ADPCM-A2 level differences). So the CHOICE is wrong, not the port: $2F is an ambience (ADPCM-A only, 3
  channels, no melody; kof98_songs.md: "$51 = $2F looped"), measured as the first command KOF98 sends on its continue
  screen ("prefix $16") but likely not its continue music; $26 is KOF98's loser's-screen tune (KOF98's own GAME OVER plays
  $2C, our stage-clear jingle). Fix: (1) re-measure KOF98's continue and GAME OVER screens in our emulator with the
  REG_SOUND tap over the WHOLE screen (every command, not the first) to know what KOF98 really plays there; (2) an
  audition page (Song Lab / interactive judging) with the candidates (KOF98's, KOF96/97's, Fatal Fury / AOF continue and
  game-over themes) for Bruno to pick; (3) game.json music + songs.json (quick once picked). Our count is 10 s (9 -> 0
  at 60 ticks a number); the pick should fit it.

- [x] 155. (done 2026-10-07: measured in our emulator (KOF2000 fight states /data/neogeo_dict/ngsdl_sta/kof2000, Terry and K' with three stocks; tap core): every DM flash sends $1E $BC, every SDM flash $1E $8F = slot 3 record $541E [53][1908][1936][DB], one ADPCM-A key-on, 12,032 bytes, 1.3 s, peak 3 kHz: the whistle. build_snd.py: songs.json sfx "from" (a code playing another SNK 1.x game's effect: its record + sample copied, enable bit set); the brawler sends it as $1A $8F; game.json super_flash.sound_max = 8F, played by main.c super_flash when the fury is the MAX (sf_col), the fury keeps $3A. V ROM: +12,032 sample bytes (used 5,843,968 -> 5,855,232: it fills a gap), ROM size unchanged 5,898,240. Proof tools/brawler/max155_proof.py: Terry and Ryo MAX queue $1A $8F at the flash frame, its key-on bytes = KOF2000's SDM flash key-on bytes; fury $1A $3A; WAVs /data/tmp/max155/out; voice_proof --all terry ryo identical to the unchanged build, bank_proof ALL OK; scenarios for both notes) KOF2000'S MAX ACTIVATION SOUND FOR THE MAX FURY (+ 20261007-021452-5d29) (feedback 20261006-155931-b3f3, Bruno in play, 0.0.71: "KOF
  2000 has a special sound for triggering a MAX Fury, sort of a high-pitched whistling sound that is very
  characteristic. See if you can track this down and include this, that would help us differentiate the MAX Fury from
  the regular Fury in our game."). Today fx.super_flash plays KOF98's $1A $3A (FURY CHARGE) for a fury and a MAX
  alike (game.json super_flash.sound; KOF98 sends the same $99 index for DM and SDM, measured). Plan: (1) find the
  sound in KOF2000 (/data/roms/kof2000.neo; check its M1 is the decrypted one; its driver is the 1999-2000 SNK line,
  next to garou in tools/kof98snd/games98.py): tap REG_SOUND in our emulator while doing a MAX super and while
  activating MAX mode, isolate the command, the ADPCM sample(s) it plays; (2) bring the sample into our V ROM as a new
  sfx (songs.json sfx from a second source game: build_snd.py today takes effects from KOF98 only); (3)
  super_flash gets a "sound_max" played instead of $3A when the fury is the MAX (needs the MAX flag of #151). Proof: the
  capture's WAV vs KOF2000's, the flash frame's command in a MAX. Big (a new sfx source in the sound build).

- [ ] 156. "YOUR CARD IS STILL INSERTED." AFTER EVERY GAME (feedback 20261006-160546-b3f3, Bruno in play, 0.0.71: "I keep
  having that message, your card is still inserted, each time the game resets. Why is that?"). Replay: GAME OVER, then
  the game returns to the BIOS (SYSTEM_RETURN) and from ~frame 47786 (P-48) SNK's MVS BIOS shows the message to the
  press. ANSWER: it is the MVS BIOS's own reminder when a game ends with a memory card in the slot; the NeoScan Player
  runs Geolith with geolith_memcard "on" (android/.../cpp/player.c environ_cb), so the slot always reports a card. On
  MVS the brawler never uses the card (main.c save_write: MVS = the backup RAM block; the card only on AES). Fix: the
  player sets geolith_memcard "off" for system mvs (on for AES, where the save lives on the card), meta.json records
  the setting and pull.py / fbreplay.js / replay_node.js read it (older bundles: on) so replays stay byte-identical;
  proof: game over -> attract on the MVS BIOS without the message, an AES save still loads. Quick (< 1 h, player
  release).

- [ ] 157. CHARACTER SELECT LAYOUT: HEAD POINTS, THREE EVEN ROWS, KIM (feedback 20261006-160708-b3f3, Bruno, 0.0.71: "The
  cursor is pointing down, but you can see that the cursor is far away from Yashiro's head. I would argue we could use
  some metadata for each sprite of the character select, maybe a position of where the head is, and this would allow us
  to maybe rearrange the character select in a way that the player's heads are kind of spaced equally, and we would
  have three rows ... and we could have the bosses a bit higher. ... Yashiro and K are almost exactly on the same spot,
  ... Hanzo [is] visible on the second row, Mai is barely visible. So yeah, I think we should reorganize the character
  select, or if you have another idea, I'm all for it."; and 20261006-160617-b3f3: "I think we should change the way
  Kim is presented on this character select."). Screens: the arrow (main.c select_arrows) is at slot x - 8 (Yashiro:
  slot 160 -> x 152) and a fixed 120 px above the feet, but each watch pose's head is elsewhere: Yashiro's (KOF98 frame
  340) is ~30 px right of the arrow, on top of K' (slot 200, pose leaning left): the two heads ~10 px apart. Kim sits in
  the BOSSES' back row (row 2, x 280: no room left in the player rows) with Kizuna animation $37 step 0 as his pose (never
  judged: added after the two judging rounds), behind Hanzo / Haohmaru, only his head and staff show. Fix: (1) a head
  point per watch pose (export: the frame's top of head / head box, x and y from the feet) in the roster export; (2)
  the arrow placed on the head point; (3) a generated layout: three rows of player fighters with heads equally spaced
  (x by head, not by slot origin), the bosses' row higher behind them; Kim (and Billy Lee, 0.0.72) in a player row; (4)
  Kim's pose: a judging round of Kizuna's intro / win / taunt frames (the interactive judging page); (5) the per-line
  budget of #158 checked by the generator. Proof: screenshots of the cursor on every fighter, every head visible. Big.
  Points (1), (2), (4) done on branch 2026-10-06 (awaiting Bruno); (3) the regenerated layout and (5) not done.
  (1) head point per watch pose: tools/brawler/head_point.py (the first row from the top with an opaque run >= 8 px,
  x = the middle of the head under it; data override game.json roster[].watch.head: Robert's raised fist, Mai's fan,
  Haohmaru's arm), export_bm.py writes bm_head[BC_COUNT]; (2) main.c select_arrows centres the arrow's 8 px fix cell on
  the head point (mirrored for actors facing right), ending ~2 px above it (row 4 at the highest, under the name).
  Yashiro's arrow is now on Yashiro, not on K'. (4) Kim: Kizuna anim $21 (the C+D taunt), last step: upright, staff
  on the shoulder (kim_select_candidates.png: old $37 s0, A $21 s13 picked, B $38 s17, C $37 s11).
  Proof /data/tmp/polish157/out: new_select.png / old_select.png (every slot, frames n / n+1),
  new_select_every_slot_full.png. Known: the white arrow is hard to see over light grey fighters (Kuroko's slot).

- [ ] 158. SELECT SCREEN BLINKING: THE LINE GUARD (feedback 20261006-161617-b3f3, Bruno in play, 0.0.72: "Mr. Big and
  Billy from Double Dragon are blinking, which tells me that we've exceeded the amount of sprites per row."). Replay: on
  the select screen nf = 20 actors (Billy Lee is the 20th, row 0 x 280); main.c line_guard counts EVERY actor's columns as
  sharing one line (no per-line count) and hides the ones past 96; guard_hidden = 1 every frame of the replay (frames
  1079-1109) and the priority order flips each frame (guard_parity): Mr. Big and Billy Lee are hidden on alternate
  frames = the blink. The LSPC limit itself may not be reached: the rows are staggered vertically. Fix: on the select
  screen (static) count per real line: each actor's watch frame gives its y span; a per-16-px-band count built once at
  slot_show (no per-frame cost), an actor hidden only if a band it covers would pass 96; with #157's layout the
  generator checks the budget per band. Proof: guard_hidden 0 on the select, a sprites-per-line histogram from VRAM
  (SCB2-4) <= 96, no blink in a clip. Quick-to-medium.
  Fixed 2026-10-06 with #170 (docs/brawler_move_vocabulary.md `draw.sprite_budget`): the 22 actors really reached 108
  sprites on the bodies' lines, so per-line counting alone was not enough: every sprite column is now trimmed to its
  non-empty rows (trims from export_bm.py, draw.s), select worst line 93; the guard counts per 8-px band, column by
  column. Bruno's bundle replayed from power-on (tools/brawler/budget_bundle.py): guard hid 4-5 actors on all 408
  select frames before, 0 after. Proof /data/tmp/budget170/out (budget.txt, *_select.png, bundle158_*.png).

- [ ] 159. ROBO ARMY AREA 1: ANIMATED BLOCK WITH THE WRONG PALETTE (feedback 20261006-160946-b3f3, Bruno in play, 0.0.71:
  "If you look in the background, there is some palette glitch in a small part of this background, so yeah, it looks
  like there's some animation, some tile animation, but the palette is wrong."; and 20261006-161029-b3f3: "Here's
  another instance of that background with animation that has the wrong palette."). The block: stage 1 (Robo Army area
  1), columns 36-38 and 57-59, rows 2-5 (48 x 64 px of sky, screen y 32-95), auto-animated 4-frame tiles $68C-$6FC
  (SCB1 bit 2) with palettes 32 / 33 from the per-tile byte table $5C1F2. make_stage_ra.render_rom, straight from Robo
  Army's map words and its ROM palette table, shows the same white / brown / black block: the extraction rule is wrong,
  not our runtime. Lead: /data/neogeo_dict/roboarmy/README.md: 237 of 245 palettes equal the ROM table in play, the
  rest are runtime; palette RAM slot 32 holds three different contents across the attract captures (a/*.pal), so 32 /
  33 are loaded (or cycled) by Robo Army's code. Fix: capture Robo Army in area 1 at those columns in our emulator, take
  palette RAM 32 / 33 (and the SCB1 words) as shown in play (verify.py's frame palettes), find the routine that writes
  them (cycling or not), use that in make_stage_ra.py (cycled = our runtime cycles it the same way); check every stage
  for animated groups whose palette is a runtime one. Proof: stage 1 at those columns vs Robo Army's screen at the
  same scroll, 0 px differ (verify.py). Medium.
  Done on branch 2026-10-06 (awaiting Bruno): 32 / 33 are not cycled: Robo Army's area load ($756A) copies palette
  lists ($30000[i], 16-word records, word 0 = the palette number, loader $6002) over its global table: area 0 list 27,
  area a lists a - 1, a + 8 (area 6: a + 7), 8; area 1's list 9 holds 32 / 33 (the smoke column's colours). The same
  rule fixes area 4's 179 / 180 (stage 4). Robo Army's palette cycles ($6568, id $10407A set by its area scripts;
  table $65CE): 196 (lists 18 / 19, 10 frames each: stage 1's columns 0-7, 132-139) and 240 (22 / 23 / 24 x 16:
  stage 5) now cycle in the brawler too (stage_t.cyc, main.c stage_cycle; Robo Army runs them only while that art is
  on screen). make_stage_ra.py palette(n, area) / area_lists / cycles; every palette a stage uses = Robo Army's palette
  RAM in all /data/neogeo_dict/roboarmy/ver captures and in a walk of scene 2 in our emulator. Proof
  /data/tmp/polish157/out/bg159_before_after_roboarmy.png (camera 432 / 561 vs Robo Army at the same scroll) and
  bg159_check.txt: the block below Robo Army's HUD 0 px differ (at the matching auto-animation frame), all 27 colours.

- [ ] 160. THE BLACK TOP OF THE STAGES (feedback 20261006-161004-b3f3, Bruno in play, 0.0.71: "Also I'm wondering why is
  the top part black? Why don't we have graphics extending all the way up? Is this how Robo Army presented its
  background?"). ANSWER: yes. Robo Army's map has no tiles in rows 0-1 (screen y 0-31) in every horizontal scene: its
  HUD sits there on the black backdrop (palette RAM $401FFE = $0000, measured in all 14 scenes); make_stage_ra.py
  copies that (stage art from y 32), and our HUD (portrait, life and meter bars) uses the same band. Options for Bruno:
  (a) keep it (a HUD band, as Robo Army); (b) fill it: make_stage_ra.py repeats each column's top tile row upward where
  it tiles (sky), 2 more tiles per column sprite, no extra sprites per line; (c) leave it to the final game's own art
  (224 px tall). NEEDS BRUNO (pick); (b) is quick.

- [ ] 161. BILLY LEE / SUPER BILLY VOICES FROM DOUBLE DRAGON'S OWN DATA (feedback 20261006-161844-b3f3, Bruno in play,
  0.0.72: "The sound of the transformation is missing. Billy is shouting a characteristic Shoryuki-sya, some kind of
  Japanese sentence. I would like the sound to be there."; 20261006-161938-b3f3: "That's not the right voice being
  played in the game in that scenario." (Super Billy's 236 ball, frame ~10885); 20261006-162144-b3f3: "This is not the
  right voice. There's a different voice for the dragon punch motion for Billy and Super Billy. This is the voice of
  regular Billy." (Super Billy's 623, frames ~16845 and the press)). Cause (game.json, not the engine): billy_lee
  voices = {"kof": false, "set": {special:236 13, special:623 14, hit 4}}: "kof": false drops every other key of the
  suggestion, among them special:FORM = voice 15 (DD $002B, 2.0 s, at the transition's row 26, voices.json) = the
  transformation shout; billy_super has the same set copied: 13 / 15 there are $0026 / $0028 = REGULAR Billy's 236 /
  623 voices (in Super's list but used by none of his moves), while DD gives Super Billy his own: 236 -> 14 ($0027),
  623 -> 16 ($0029), 41236 -> 12 ($0025), 214 -> 17 ($002A). Fix: both voices "kof": true (= Double Dragon's own voice
  per move, voices.py suggest), or the set corrected (billy_lee + special:FORM 15; billy_super 236 14, 623 16, 41236 12,
  214 17); voice_proof-style check: each DD special sends DD's own code on its frame (both forms), the transformation's
  shout at row 26. Quick (< 1 h).

- [ ] 162. SUPER BILLY'S DRAGON PUNCH: THE A VERSION (feedback 20261006-161912-b3f3, Bruno in play, 0.0.72: "this dragon
  version goes really too high for this game. I would suggest to use the dragon punch done with the A button for that
  particular mapping."). Replay: Super Billy's down + C = "623" (dD) from frame ~10197 (P-16); in 20261006-162144-b3f3 the
  same move takes him off the top of the screen for ~30 frames (16877-16909). game.json billy_super has no "variant", so
  the variant table plays the source's default row, the heaviest (D). Fix: game.json billy_super "variant": {"623":
  "A"} (vocabulary variant.table, latched at the start); check Billy Lee's 623 the same way (same default) and show
  Bruno both rows' heights (billy_proof's travel / height per row). Quick.

- [ ] 163. (+ 20261006-175904-5d29: "the voices repeats Kaiser, Kaiser two times instead of Kaiser wave. I think that's a general issue with special moves having various sounds throughout the special moves, for example Kaiser wave, double repuken, power geyser": a move's voice sends at each of its ROM steps, in order) (+ 20261006-174212-5d29, 0.0.74: "There's still no voice for Rising Storm and Double Repuken.") (+ note 20261006-164210-5d29, 0.0.72: "The jets are missing the voice for the blitz ball of Krauser.") KRAUSER'S BLITZ BALL: NO VOICE, NO FIRE (feedback 20261006-162034-b3f3, Bruno in play, 0.0.72: "Why isn't
  Krauser shouting Blitzball, Blitzball whenever he throws his projectiles? Also, the projectile should induce fire,
  since these are literally fireballs."). Replay (boss Krauser = fighter 2, stage 2): his specials at frames 13392 and
  13653 (role 0 = game.json "D" = 214A, the Blitz Ball): the game's sound queue sends NOTHING during 13653-13701 (no
  voice, no effect). The voice exists and is mapped: voices.json krauser id 9 = KOF96 $1B7C (special 214A-D at row 1),
  in the V ROM (vcode 174), in krauser_voices (key VK_SPEC + 0 -> 9 at 1). Cause: 214A is a ROM program special
  (krauser_specials[0].prog = mai_sp0_prog), and fighter.c special_update plays a program special's voices only when
  bspec_t.pvoice is set (Double Dragon's); KOF programs have pvoice 0, so their special voices are never sent. Likely
  every KOF ROM-program special (the 0.0.72 replay of 20261006-160257-b3f3: Robert's fury sends the flash's $1A $3A,
  then only the victims' hit voices, $1E xx, none of his own): check with voice_proof.py across the roster. Fix: KOF
  program specials time their voice keys by their program's frames as DD's do (pvoice 1, the 'at' = the KOF animation
  step that sends $FC 00 in the ROM, voices.py), one rule for every ROM special; proof voice_proof.py every fighter's
  specials and furies (code + frame = the source's). FIRE: the hit reaction of a fire projectile = burn (fighter_t.burn,
  set_burn): from the ROM's reaction for the Blitz Ball (KOF96's hit type of the projectile; if it is not a fire one
  there, a roster override for Krauser's projectiles, Bruno's call); proof: a Blitz Ball hit -> the victim burns.
  Medium (the voice rule touches every ROM special).

- [ ] 164. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; TODO #173's branch; proof tools/brawler/impact164.py ->
  /data/tmp/rugal173/out/impact164.json, scene_20261006-190659-5d29.png, romspecials_krauser) The end (impact) of an
  object read from the ROM was exported at height 0 (handlers98 export_rom: its hit routine's animation as [frame, 0, 0])
  and bpend_t's height was absolute: drawn on the floor. Rule now: an end plays where its hit was, bpend_t x / y from the
  impact's (fighter.c proj_hit p->py0, proj_row; the captured ones converted: projectiles96 end_rows, export_whp,
  export_ss4, export_dd). Every projectile with an end (46): 5 drew their impact away from the hit before, all ROM
  objects: Krauser's Kaiser Wave A / C (0 under its 96 px flight), Blitz Ball high / low (0 under 88 / 40), K''s shot (0
  under 88-111); now at the hit's height. Mai's fan rises 7 px over its flight in KOF98 too (unchanged). Krauser's Kaiser
  Wave vs KOF96 (romspecials_check mid): the end at 96 px, KOF's height.
  THE NOTES: (SOLVED BY A 2ND NOTE: 20261006-190659-5d29, 0.0.76, typed: "Impact effect of kaizer wave too low" — the blue shards are Krauser's KAISER WAVE impact, drawn at floor level instead of at the wave's hit height: the projectile's end / impact object's y offset (spawn_y / the end rows) lost or relative to the floor; fix in the projectile export, check every projectile's impact height vs KOF) KRAUSER'S BLUE GROUND SHARDS (feedback 20261006-164245-5d29, Bruno, 0.0.72, no words, screenshot circled: a
  cloud of small blue shards on the ground in front of Krauser, beside a white flash, while he strikes Robert / an
  enemy in the air). Find which object draws them (replay the note: frames before the press) and whether it is right
  (KOF98's own effect with its palette?) or a stray / wrong-palette object; ask Bruno only if it matches KOF98.

- [x] 165. (done 2026-10-06: two hidden inputs, both outside the game. 1) harness.py loaded the installed retroarch core (May, pre-fa094e0 v2 states without the 68000 pending cycles / YM2610 pacing): a state loaded right after power-on played differently from the same state loaded after any frame (fighter 15: the same 6 cases as #146's diff), so a live-made vs a cached fight state differed. Now the repo build geolith/libretro/geolith_libretro.so (as tools/feedback), cache keyed by ROM + core. 2) the uPD4990 calendar starts at the host wall clock at load (geo_rtc_init); the BIOS reads it every frame and leaves it on the stack ($10F289): fight states made at another minute differed (fighters 9, 13). Pinned to 2026-01-01 00:00 at every power-on through the save state. Proof /data/tmp/det165: regress 4 runs (3 fresh caches at different times + 1 cached) 260/260 cases + bleed identical; controls_proof and cancel_proof 3 runs each byte-identical JSON) REGRESS HARNESS NON-DETERMINISM (found by #146, 2026-10-06): the same base ROM gives different regress.py
  facing traces in two full runs (4 traces, fighter 11): right after the test places the enemy, it stays idle in one
  run and walks in the other; fighter + AI fields at the start state match, the hidden input is not found (traces
  /data/tmp/throws146/m). The feedback replays are byte-identical, so suspect the harness (state load / RNG seed /
  frame counter / an uninitialised RAM byte in the placement path). Find it: a proof that isn't repeatable is no proof.

- [ ] 166. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; proof /data/tmp/throws166/out, tools/brawler/throws166_proof.py)
  (a) the catch is silent; the throw-start effect decoded: the throw animation's $FA $34 command -> effect routine
  KOF98 $3709E (table $36382[$34]): sound index $80 = $1A $18, shared effects id 38 (KOF96 29) state 61, palette 90;
  played as fx.throw_start on every throw (row / offset from the throw's own command, throwrom.throw_fx; Geese's back
  throw has none in KOF96: takes his forward one's), same frames as KOF98 / KOF96 from row 3 (a_*.png, a_sound.txt).
  (b) hold crowd: the hold hit's attack box hits every other enemy in reach, each once per hit + the spark on the held
  victim (Terry / Geese: both bystanders hit by all 3 hits, knocked down by the finisher, the far one untouched).
  (c) bthrow_t.hanim: Terry = cmd_df_c (game.json), default = the fastest-startup close normal (c_startups.txt; Terry's
  dfC and close C both start in 4 frames). (d) the finisher cancels into a special / the fury (C / D in its hit-stop:
  SPECIAL 7 frames after the impact); whether it reconnects depends on the move (Terry's down+C and fury hit, his
  Power Wave passes under the launched victim; Geese's C and fury hit, his down+C misses). (e) life.respawn: blink 60
  frames + KO voice, then the continue or the drop from 224 px (invincible, no control, 31 frames), landing = every
  enemy on screen knocked down; the continue drops him in the same way. controls / cancel / fury_inv ok (21 fighters),
  #146's control returns unchanged on the deterministic harness (56 / 64 / 59 / 71).
  THROWS ROUND 2 (Bruno's notes on 0.0.73's Geese / Terry pilot, all Player 0.0.15):
  (a) 20261006-172625-5d29: "There's a sound being played whenever I grab an opponent. I want that sound to be played
  only when an actual throw is being triggered." + "in King of Fighters 98 and also 96, there's a little blue special
  effect ... that goes along the throw. Can you locate it and integrate it as standard in Brawler?" -> the catch is
  silent, the throw sound at the throw start; find KOF96/98's throw-start effect object (its code + sprite) and make it
  a standard throw effect (vocabulary fx).
  (b) 20261006-172727-5d29 + 172758 (same request twice): "When I hold an opponent and hit, I want the surrounding
  opponents to also be hit, like in Final Fight or Streets of Rage ... also there may not be an impact effect on that
  hold and hit." -> hold hits get an attack box hitting every enemy in reach (crowd rule, each once per hit) + the
  standard hit spark / impact on the held victim.
  (c) 20261006-172836-5d29: "For the hit animation of Terry, don't use the stand C, use the diagonal C animation, I
  think this one starts faster." -> Terry's hold hit = his down-forward+C (crouching / diagonal C); generalise: a
  per-fighter hold-hit choice in game.json, the default = the fastest-startup close normal (measure startups).
  (d) 20261006-173012-5d29: "This hit at the end of the throw, I want this to be considered a regular hit, so that I
  could cancel with a special or even a fury after that." -> the hold finisher (3rd hit) is a normal hit: cancellable
  into specials / furies per #143's rules (the victim launched, juggle allowed).
  (e) 20261006-172919-5d29: "For the player death sequence ... like Final Fight ... the player dies, then the blinking
  animation together with the death sound, and then the continue screen if there's no more lives. If there's another
  life, then the player respawns in the air and falls on the floor, and as the player falls back, all the enemies are
  pushed down." -> a standard death / respawn sequence (blink + death voice, continue if no lives; else drop from the
  air, landing = a screen-wide knockdown of enemies, invincible while falling).
  Proof: sheets per point, Geese + Terry, then roster-wide rules; the usual proofs. Close the feedback rows shipped.

- [ ] 167. HUD VERSION LABEL (20261006-173317-5d29: "The version that is displayed at the bottom is a bit too close
  from the level 4 label ... I would push this on the bottom left."): move the version text to the bottom-left corner.
  Done on branch 2026-10-06 (awaiting Bruno): main.c arcade_line prints "V0.0.x" at fix column 1 (the bottom-left
  corner), LEVEL-n / CREDIT nn stay where they were. Proof /data/tmp/polish157/out/hud167_before_after.png.

- [ ] 168. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; proofs /data/tmp/var147/out: voice_goenitz, romspecials, goenitz_kof96_soundlog.json) Sounds: KOF96's 41236A-D handler sends $1BBA (voice) at frame 0 and $1AD1 (the wind, effect slot) with each tornado's spawn at frame 19; #163's rule dropped every $1A word. Rule now (handlers98.voice_send fx): a ROM special's code sends its own effect words too, listed by voices.py as the fighter's channel 'fx' voices unless common (43 new over 16 KOF fighters, ~370 KB of V ROM; ids of the old list kept); the brawler sends $1AD1 at 19 like KOF. Not reproduced: KOF stops the wind when the tornado hits ($14 + $1AD1). Teleport: 214B / 214D = Hyouga (handler $4E4A4; B slides 200 px along the floor, D arcs 184 px; states 185 / 186 flicker a blank def = the vanish). 214B was on up+C, which the boss AI never presses: now on forward+C (the boss's rush pick; 41236C moved to up+C); 214D read from the ROM too (pool, Lab). romspecials_check fD: frame, x, objects identical to KOF96 whiff / close / mid. Known: 214D stops at a standing body in the brawler (KOF passes over it). GOENITZ (20261006-173139-5d29: "What is the sound effect of Goenitz? He has like sound effects that he should
  make with every tornado, and he also should have another special move, like a teleport."): decode his KOF96/98
  tornado specials' sound sends (each tornado's wind sound) and his teleport special(s) from the ROM handlers; give
  the teleport a C slot; sheets + sound log vs KOF.

- [x] 169. FEEDBACK THREADS IN THE APK (20261006-173524-5d29 + 173615: "list the status of every open feedback,
  whether it's been treated or fixed in the current build ... provide feedback against that particular feedback to keep
  a trail and a history, and either say ... resolved or ... still here ... adding the voice feedback"; "provide myself a
  feedback in the form of another voice feedback or just a thumbs up, thumbs down"): the APK list (0.0.15, Settings ->
  My feedback notes) gets a filter "open" (not shipped / won't do) and "shipped in a build I can test", and per note a
  reply thread: voice (transcribed, same flow minus the replay) or typed reply, and thumbs up = verified fixed (status
  verified) / thumbs down = still broken (reopens: status reopened); replies in the tracker (table replies), in fb.py
  show, the Lab tab and pull.py's report; pull.py lists reopened notes first.
  Done (Player 0.0.17, docs/feedback.md "Threads"): the list shows the build he runs and filters Open / Shipped: test
  it / All; per note his thread + 👍 Fixed (verified) / 👎 Still broken (reopened, optional reply) / Reply (hold to
  talk -> transcribed, editable; or typed); the in-game note box has "Reply to..." (picks an open / testable note, no
  bundle). Server: POST /brawler/feedback/reply, table replies (origin columns), status change in the history;
  fb.py show, pull.py (report.md thread + /data/feedback/report.md overview, reopened first), Lab tab (thread,
  reopened first). Proven in JanusPhone with brawler-test: text, voice, 👍 shipped -> verified, 👎 verified ->
  reopened, filters 4/1/7 -> 5/0/7, in-game text + voice replies.

- [ ] 170. RAGING STORM BLINKING (20261006-174101-5d29, 0.0.74: blinking whenever Geese's Raging Storm plays): replay
  the note; measure sprites per line during the storm (pillars x fighters x HUD) vs the 96 limit and the line guard
  (main.c guard_hidden, cf. #158): fix by a sprite-budget rule for eruptions (fewer pillar columns drawn, or the
  guard dropping background / far actors first, never the effect itself), sheet before / after.
  Fixed 2026-10-06 (with #158): the LSPC never passed 96 during the storm (worst real line 87, our core's own per-line
  count); the blink was the line guard hiding an enemy (46 of 109 frames, alternating). Now trimmed columns + a per-band
  guard with a priority (players > held / hit victims > fury effects > enemies, a fury effect thinned before hidden):
  Raging Storm fury / MAX, Kuroko's and Genjuro's furies with 6 enemies: nobody hidden, worst line 83. Proof
  tools/brawler/budget_proof.py -> /data/tmp/budget170/out.

- [x] 171. (done 2026-10-07, branch fix/171-uninit-ram: no game code reads stack or RAM it did not write. A read watch in a copy of the core (/data/tmp/uninit171/geolith: a shadow byte per work-RAM byte = never written / BIOS-written / game-written, dead again when the stack pointer pops past it; every read by game code below $10F300 of a byte not game-written, logged with its PC) over the attract, a campaign and the regress cases (/data/tmp/uninit171/out/final/watch_reads.txt, symbolised): only the backup block `save` (the BIOS restores it), init_magic (.noinit, by design), the BIOS's return addresses (rts in stub_rts / player_start) and crt0's vblank_handler testing game_active (.bss) at power-on before boot_init had cleared it: now trusted only once init_magic says boot_init ran. $10F289 is an ordinary stack slot of the game (24 functions, every read after the game's own write); what moved the traces was the timing, not the byte: the calendar changes the BIOS's SYSTEM_IO cycles, so the harness's frame-end reads / pokes landed at another point of the tick (#178). Now with the tick-synced harness another calendar minute gives 286 / 286 identical facing traces (the old harness: 10 differ), and work RAM filled with random bytes at power-on (core copy, 3 seeds) gives 286 / 286 identical regress traces and the attract identical frame for frame from the game's first tick) UNINITIALISED STACK READ (lead from #165): poking $10F289 (a stack byte the BIOS leaves) changes 1 of
  fighter 9's 13 regress traces: some game code reads stack it never wrote. Find it (a read watch in our core on
  never-written work RAM during play) and initialise; real hardware RAM powers up random.

- [ ] 172. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; proof /data/tmp/boss172/out boss172.json +
  boss172_sheet.png, tools/brawler/boss172_proof.py) Engine rule stage.boss_death (docs/brawler_move_vocabulary.md; main.c
  boss_ko_start / boss_ko_tick): the tick the boss's life runs out every intent is off (players untouchable, no P2 join, no
  trigger, queued spawns dropped), the logic runs 1 tick in 3 frames for 300 frames (music / voices / drawing full rate),
  the boss's VK_KO on the kill frame, every enemy still up knocked down with no life at +45, +85, +125 ... (each its own
  VK_KO as it falls, none again at S_DEAD: fighter_t.ko_voice), then PH_END -> STAGE CLEAR. Proof (Krauser + 3 minions,
  Terry): kill frame 230 = input off, slow motion +0..+299 (logic ticks every 3 frames), voices +0 boss, +45 / +85 / +125
  one per minion, minions down +44 / +84 / +124, PH_END +299, STAGE CLEAR +399, P1 pressing keys throughout: x and life
  unchanged, idle once his attack in progress ended.
  BOSS DEATH SEQUENCE (20261006-174259-5d29, 0.0.74: "when the boss dies, as soon as he is being hit, that's
  the end. So we stop the control of the player, we enter slow motion for five seconds, the boss screams, and everybody
  else falls and dies, like in traditional beat'em all games."): a standard stage-end rule: the boss's killing hit ->
  player input off, ~5 s slow motion (frame skip / half-rate game logic, music and voice kept), the boss's death voice,
  every remaining enemy knocked down and dying (no score loss), then the stage clear. Sheet + timing log.

- [ ] 173. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; proof /data/tmp/rugal173/out, tools/brawler/rugal173_proof.py,
  romspecials_check BRANCHES=wall)
  (a) Rugal's 624A God Press WAS RECORDED (a capture: the push followed KOF's stage, 768 px, past the brawler's screen):
  now from KOF98's handler $7F4A8: the rush 162 (8 px a frame, 16 frames), its catch box -> the catch routine (+$19C):
  167 pushes at 8 px a frame until the wall (KOF $18092 -> PC_WALL; the "branch on vx" of #115 was that test's d0), 4
  frames, the victim signalled (P_VSIG), the slam 168, the jump back 169 (KOF's a3 record: vx -10.31, friction $E900,
  vy 4.125, gravity 0.605), 170. The victim follows the catch's own script (vocabulary hold.victim_list: KOF's +$1A0
  routine, lists $299378 pushed / $299410 the slam: grabbed, the blow, the release 283 = its blowback against the
  wall). THE WALL RULE (vocabulary stage.wall, fighter.c wall_update, docs/brawler_move_vocabulary.md): the screen edges
  are walls 40 px in for every special and fury of every fighter (the dance wall made general): from a special's hit
  (body or projectile) until its victim is down it stays inside the walls, its attacker held back by it while the
  special plays; catches that grind to KOF's stage wall test these walls. Proof: romspecials_check rugal:fD wall (KOF98's
  P1 as far from its wall as the brawler's) 0 frame mismatches, the hit on KOF's frame (43); whiff 0; wall.json: Rugal
  624A, Terry 214C, Billy 426C at both edges, 6 / 6: the victim never past its wall, pinned 29-61 frames, the attacker
  stopped (wall_<fighter>_<side>.png).
  (b) the second Rugal in a taunt pose = a projectile-pool entity drawing Rugal's frames 243 / 247 at -202 px from the
  move's start: the RECORDED scripts of 624A, 6426A, 6426C and 23624C all carried it: KOF98's capture took P1's two
  waiting teammates (table 36 states 464 / 469, standing at x 132 / 188 of KOF's stage, off KOF's screen) as the move's
  objects; the brawler replayed them on screen. Fixed by the cause: none of Rugal's moves is recorded now (all eight
  slot moves + the MAX play KOF98's programs), no capture object left; scene check: no Rugal-owned object in God Press.
  (c) Kaiser Wave 6426A / 6426C WERE RECORDED: now from $7EDAA: the charge (C held through 134: the count of its event
  steps, frames 30 / 54 -> levels 0-2; vocabulary input.sustain, PC_HELD / PC_CNTLE), the wave of the level (states 137
  / 138 / 140, 1 / 2 / 3 hits, each hit switching to the list's next state: object.phase at hit, bproj_t hitnext), and
  the blue charge in his hand = the animations' $FA records (kind $DF -> state 246, pinned for its step, 60-66 px back,
  65-90 px up; the capture had kept its height 0: it was drawn on the floor): vocabulary anim.step_spawn (bchar_t.pfx;
  Rugal only for now: handlers98.STEP_FX). Proof: charge.json (C held 0 / 70 / 95 frames -> 1 / 2 / 3 hits), romspecials
  rugal:uD / ufD 0 frame mismatches whiff / close, every hand effect spawned and ended on KOF's frames.
  The fury 23624C Gigantic Pressure (WAS RECORDED) from $7FD1A (+ its MAX, down+D: the turn and the push back): 0 frame
  mismatches whiff (1) / wall (0), hits on KOF's frames; the MAX's second push runs to the screen's other wall, 240 px
  away (KOF's 700: frames differ from the turn on). Voices: the programs' own sends (#163).
  THE NOTES: RUGAL (3 notes, 0.0.74): (a) 20261006-175700-5d29: "This move slides and travels for way too long, it
  feels like as though it was recorded. This move should detect whether we are on the edge of the screen, and then as
  soon as we're on the edge, actually push the character on the wall, and we should be able to actually see the victim
  being pushed on the wall ... look at the real game." (replay: Rugal's rushing strike carries Terry past the right
  edge) -> decode the move from KOF98's handler (is it recorded today? say), and a STANDARD rule for every travelling
  special / rush: at the screen edge (the wall rule of the dance furies) the attacker stops and the victim is pinned
  against the wall, visibly, as KOF does in the corner. (b) 20261006-175740-5d29: "in that special move there's another
  instance of Rugal ... in this taunt pose ... definitely a glitch" (screenshot: a second Rugal, arms crossed, at the
  left edge) -> find the object drawing Rugal's frames (a ghost / afterimage object with the wrong frame, or a
  leftover entity) and fix. (c) 20261006-175904-5d29: "a blue effect that should be in the hand of Rugal, and it's not
  there" (Kaiser Wave's charge in the hand) -> the pinned hand effect from the ROM handler; its voice is in #163.

- [ ] 174. (DONE ON BRANCH 2026-10-06, awaiting Bruno's review; docs/rom_packer_rules.md "P ROM", proof /data/tmp/bank174: each fighter's bulk (frames, tiles, special scripts / programs, projectile rows) in its P2 bank (tools/brawler/bank_pack.py), everything other fighters / combat / AI / HUD read in MB1; MB1 629 KB free, bank 0 12.8 KB free, bank 1 552 KB free, P ROM 3 MB; controls / cancel / fury_inv / campaign29 / romspecials JSON identical to the unbanked build, regress bleed same; 6 bank layouts (BANK_SPLIT, same-cycle builds) byte-identical; CPU busiest stage mean 66.2 -> 67.8 %, worst 96 -> 96 %; Android player and the Lab wasm core run it; NeoCart v3 chip map fixed in pboard_flash.py) P-ROM BANK SWITCHING (2026-10-06): 0.0.76 overflowed the first P MB by 14 bytes; main.o's tables moved
  to .p2data ($200000). Left: ~61 KB in MB1, ~88 KB in MB2. Before the next fighter: P2 bank switching (the cart's
  $2FFFF0 bank register, tools/neobuild.py limits), a bank per fighter group's tables with the code reading them
  through a bank-select at use (or the special tables moved to banks, code + hot tables in MB1); prove every fighter
  in every bank (controls_proof) and the NeoCart flash board's banking matches (hardware/neocart).

- [ ] 175. (PRIORITY Bruno 2026-10-06: "I asked for haohmaru and kuroko": Haohmaru + Kuroko first, Genjuro parked out of the roster) (+ HAOHMARU from SS2 in the same job, replacing the SS4 one: #148) GENJURO (Samurai Shodown II) INTO THE BRAWLER (Bruno, 2026-10-06; AFTER #174 bank switching): study
  /data/neogeo_dict/samsho2/README.md + tools/samsho2 (the study recommends him: 99 px, Terry-sized, 1:1 no scaling);
  an exporter tools/samsho2/export_ss2.py in the export96 layout (like export_ss4 / export_kz / export_dd), every move
  decoded from SS2's data / handlers (no recorded moves), A / B / A+B as rows of the variant table, his rage-only
  move as the fury (D) and the strongest variant as MAX (down+D), the card wave projectile, the 236 slash chain with
  its follow-ups (branch.followup), his throws (close + forward + A+B slash, + D / C+D kick) through #146's standard
  throw; weapon loss not modelled yet (he keeps his sword; the weapon state is a later component); voices from SS2's
  MAKOTO 3.0 driver (tools/makoto3) into the voice path; palettes; frame check vs SS2 both facings; the usual proofs.
  PROGRESS 2026-10-06 (worktree branch worktree-agent-ad6294cbf3aee0c90): Genjuro (samsho2:genjuro): 214S card wave
  (object type 10, its 32-frame life then its break), 236S the three-part slash (follow-ups = the ROM's type-5 cancel:
  a connect + the window steps, C again: chain_proof_ss2.py), 623S, the rage move (6 3 2 1 4 6 A) as the fury (no MAX:
  one button), his throw (274, victim 514), voices (MAKOTO driver samples, voices.py samsho2), palettes A / B, select
  slot middle row; weapon loss not modelled. Proofs /data/tmp/ss2/out (controls, cancel, fury_inv, voice, regress,
  campaign29, bank_proof, frames 566 / 576, specials_genjuro.png).

- [ ] 176. KUROKO (Samurai Shodown II, hidden table 17, 636 animations, 84 px) INTO THE BRAWLER AS A FIGHTER (Bruno,
  2026-10-06: "I want the hidden character kuroko, he has tons of fun special moves"; after #175): his full moveset
  from SS2's data (his special moves are parodies of other fighters' moves: decode every one, its command, its
  objects; flag / referee gags included), exported like Genjuro (variant table, rage move = fury, strongest = MAX,
  throws via #146), voices, palettes, frame check; how he is unlocked in SS2 noted (the brawler: selectable).
  PROGRESS 2026-10-06 (worktree branch worktree-agent-ad6294cbf3aee0c90): Kuroko (samsho2:kuroko) selectable (front
  row): his parodies (results 39-46: anim 29 + the objects type 24 / 25 of $4C07C / $4C12A), the flag sweeps 6+ABC /
  6+BCD, C C C C C with the ghost pinned to him, the rage moves as fury (RAGE, 6 3 2 1 4 6 A+B) and MAX (MAX RAGE,
  6 4 1 2 3 6 C+D: the dance twice); his throw (27); voices incl. the parody shouts. Not in the build: 6 3 2 1 4 A (the
  flag that flies out and comes back: spawn.boomerang), 61236A / 126BC (a 9th / 10th palette). Unlock in SS2: not
  traced (his vs state pokes the selected-character byte $100D0B: mkvs_kuroko.py). Frames 358 / 364 identical.
  PROGRESS 2026-10-07 (branch fix/176-kuroko-boomerang): (a) the flag boomerang 6 3 2 1 4 A (result 50, object 27
  $4C274 decoded + measured, tools/samsho2/boomerang_ss2.py) = the new spawn.boomerang (bproj_t kind 4, fighter.c
  boom_update): out 8 px a frame from 107 to 220 px, 17 hover frames, back to 104 px, the catch signals Kuroko, 2 frames
  in his hand; its pole = 2 segments 48 / 96 behind, never nearer than 64. SS2's flag hits only going out (its animation
  holds a box-less step from its 16th frame; its first hit spends it): measured with P2 put in its return path, not hit,
  so the brawler's does the same. (b) 1 2 6 BC (palettes 38 + 39) and 2 1 4 1 6 BC (178) exported: export_ss2.
  pack_palettes folds palettes into others with exact colours (shared colours share pens, the rest move to free pens,
  the folded parts' tiles copied with renumbered pens): 10 -> 8 (52 + 250, 38 + 39), no runtime palette loading. The
  results 41 / 46 inputs were swapped in the export (61236A = 41, 214161BC = 46): fixed, game.json keeps the same move
  on fD. Slots: D = 63214A, uD = 126BC, dfD = 214161BC (236A, 2363214A, 214A stay in the pool for the Lab). Proof
  /data/tmp/kuroko176/out (kuroko176.json + sheets, ss2proof frames 398 / 404, controls, cancel, regress no-bleed).

- [x] 177. (done 2026-10-06: (a) make_site.py read a voice use's 'states' on the new 'prog' uses (#163): they name their input like a special; deploy_vps.sh rebuilds the wasm when any Geolith source is newer (one geo_m68k.c, desktop = Lab P2 latch); Lab live 0.0.78: Geese (bank 1) vs Kyo (bank 0) and back, every tab loads, note 20261006-155636-b3f3 on its 0.0.71 build replays byte-identical. (b) GCC 15 store merging joined byte stores at odd offsets into word / long moves (clr.w 97(a2): chain_t + spec_buf; lab+9 long) even with -m68000 -mstrict-align: -fno-store-merging in the brawler + SDK Makefiles; odd-access check core (/data/tmp/align177): 822 -> 0 over controls_proof, 637 -> 0 over campaign29 (log identical to the unfixed build's), 0 over regress + cancel_proof; regress no-bleed True, cancel_proof all 21 ok) (found by #174) (a) the Lab deploy is broken since #163's merge: tools/brawler/chainlab/make_site.py
  KeyError 'states' — fix and redeploy the Lab with 0.0.77+; (b) the game does unaligned word writes into `in[]`
  (Geolith logs them; a real 68000 raises an address error on an odd word access): find and fix (proof: no unaligned
  access logged over campaign29).

- [x] 178. (done 2026-10-07, branch fix/171-uninit-ram: the harness read and poked RAM when a video frame ends, a fixed cycle of the frame that falls inside the game's tick, so where in the tick it fell moved with every build's cycle count (struct sizes change multiply timings, code moves; the calendar changes the BIOS's): reads saw some fighters before and some after this tick's update, a place() poke landed mid-tick, and the fight state was saved 10 frames after pick, i.e. a tick earlier in a build that boots a lag frame slower. Now harness.Brawler(tick_sync=True) (used by regress.py; off by default): a write tap on crt0's game_ticks copies work RAM at each tick boundary, reads come from that copy, writes are queued and written there, save states carry both; regress saves the fight state at the stage's tick 180 (stage_tk), not a frame count. Proof /data/tmp/uninit171/out/final (summary.txt, tools in /data/tmp/uninit171/tools): vs the branch build, 286 / 286 facing traces + the bleed trace identical for 4 bytes of unused data before .bss, for 3000 idle cycles before every tick (timing only; the old harness: 45 differ), for 18 bytes added to fighter_t + 2 globals (on the 0.0.95 build: /data/tmp/uninit171/games/fpad; old harness: 24 differ), for another calendar minute and for random power-on RAM (#171); bleed strict True everywhere; bank_proof ALL OK; re-checked after merging 0.0.98: /data/tmp/uninit171/out/final2, padded 286 / 286 identical, bleed True, bank_proof ALL OK) REGRESS IS LAYOUT-SENSITIVE (found by #173, 2026-10-06): a padding-only build of 8d8251e (18 bytes added to
  fighter_t, 2 globals, no logic) diverges from the base on 30 of 260 regress.py facing traces (walk_L / run_L / A / jump_up /
  C of fighters 5-13: the enemy behind P1 walks or grabs a frame apart), both runs from fresh fight states
  (/data/tmp/rugal173/regress_*_fresh.json). Find the timing dependency in the harness (pokes / samples mid-tick): a
  regression check must not move with the RAM layout.

- [ ] 179. SS2 SPECIALS FEEL RECORDED (Bruno in chat, 0.0.85: "they all seem garbage recorded"): audit every SS2
  special's program (decoded from the handler code vs captures replayed), play them in real fights vs SS2 in the same
  situations, re-derive every replayed part from SS2's code. In progress.

- [x] 180. (done 2026-10-07: the ghost was a script object of the Phoenix's export, Kim's frame 195 px behind him on rows 108-186: Kizuna's sound task 'SOUND' (code $1D270, slot 12) holding a dead PALETTE task's Kim animation $50A0 / step $AED1C, never drawn by Kizuna (screen scan), taken as Kim's object; cap_kz.new_objects skips a task whose +$40 / +$94 are still the dead slot's leftovers, captures regenerated (only stale $50A0 objects dropped). Proof tools/kizuna/kim180_proof.py: the Phoenix connecting in a fight, every sprite attributed, nothing of Kim's > 160 px behind him, all flames / feathers kept; sheets /data/tmp/kim180/out (phoenix_brawler.png vs phoenix_kizuna.png, objects.txt); kim_effects_check all ok, bank_proof ALL OK, controls_proof kim ok) KIM: A SECOND KIM DURING HIS FURY (20261007-002048-5d29, 0.0.85: "Why is there another instance of Kim on
  the left side of the screen as he's doing his fury?"; the replay at P-48 shows a partial Kim at the left edge while
  the real one rises in the centre, just before the Phoenix flame). Same family as Rugal's ghost (#173: a recorded
  object that should not be drawn): find which object draws Kim's frames there (afterimage / pinned effect of #144
  with a wrong position or reference, or a capture leftover), fix the cause.

- [x] 181. (done 2026-10-07: 0.0.86 renamed his specials (623A / 214C ... -> 623P / 214K ...) while voices.json still keyed their voices to the old captured inputs, so every program special resolved its step sends to silence. Now voices.py whp_list reads each exported special's sends from WHP's step command 4 (every row; the fury / MAX at their script rows; his own effects $39 / $62 as fx; captures for normals only) and export_bm plays WHP programs through #163's program voice path (pvox). Also: the first step of a WHP program was a frame short (handlers_ss2's start-frame rule missing), so every later step, hit, spawn and sound came a frame early. Proof tools/whp/sound_proof.py -> /data/tmp/whp181/out/sound_proof.json: 15 / 15 rows same words at the same frames as WHP's SNDLOG and every step frame-identical to the model, fury + MAX whiff / hit same words on the same WHP steps; voice_proof --all hanzo 6 / 7 (MAX: FC9E on its step, row 88 played at frame 70 after the hit-link jump), bank_proof, controls_proof hanzo, regress no-bleed True) HANZO'S SPECIALS LOST THEIR SOUND (regression of 0.0.86's WHP six-button import; 20261007-004411-5d29 "The
  sound is no longer here for the special move." on 623P (the rising slash), 20261007-004426-5d29 "This special move
  also has the sound missing." on 214K (the flying spin kick)): the new one-program-per-special exports dropped the
  voice / sound keys the old Hanzo specials had (WHP's ADK driver sends); restore every WHP special's voice and sound
  per row from WHP's code, per #163's rule (each send at its step, in order); voice_proof for hanzo vs WHP's sound log.

- [ ] 182. HUD FONT FROM KIZUNA (20261007-005023-5d29, 0.0.87: "The bitmap font used to display level 4, credit,
  etc. Can we actually leverage the bitmap font used in Kizuna? This particular one ... has the borders around the
  text so that it contrasts with any kind of background."): extract Kizuna Encounter's outlined FIX-layer font (its S
  ROM glyphs + the palette it uses), map it onto the brawler's HUD / system text (STAGE / WAVE / LEVEL / CREDIT /
  version, select screen titles), check every string's glyphs exist (digits, letters, punctuation), sheet before /
  after on the brightest and the darkest stage.

- [x] 183. (done 2026-10-07, Player 0.0.25: one EmuThread per process, EmuThread.claim hands the live one to the resumed MainActivity, a replaced activity no longer starts a game, player.c refuses a second load while one is live; AVD JanusPhone: 20 cycles install-over / relaunch / rotate / background-foreground, 20 processes, never more than one EmuThread, no crash) PLAYER: TWO EMULATION THREADS AT ONCE (found by the 0.0.24 job): right after a reinstall MainActivity started
  twice in one process, each starting an EmuThread loading the core: an intermittent crash in the 68k core. Make the
  emulation thread a single process-wide instance (or guard MainActivity's start), prove with repeated reinstall /
  relaunch / rotate cycles in the AVD.

- [ ] 184. (DONE ON BRANCH fix/184-win-pose 2026-10-07, awaiting Bruno's review; proof tools/brawler/win184_proof.py ->
  /data/tmp/win184/out) STAGE END WIN POSE (20261007-021017-5d29: "Maybe we can shoot a little winning pose here at the end of the
  stage."): after the stage clear (and the boss death sequence), the player plays his own win pose from his source
  game (KOF win poses 336-343 etc., SS2 / Kizuna / WHP / DD equivalents), then the stage transition.
  DONE: STAGE CLEAR turns the input off; each player in play (both in 2P) stands, turns toward the middle of the screen
  and plays his fighter's `win` animation once with the voices its source sends, held; the next screen 45 frames after
  the last pose (never before STAGE CLEAR's 200, at most 720; main.c win_tick). `win` = each source's round-win
  animation read in our emulator after a KO (wins98.py GAME=kof96/98/99, tools/brawler/wins184.py): KOF98 / KOF99 336 +
  337 (A held: Terry Ryo Ralf Robert Yamazaki Billy Kyo Iori Mai Yashiro Rugal, K'), KOF96 209 (Mr. Big, Krauser,
  Goenitz; Geese 209 + 232), SS2 200 (Haohmaru) / 198 (Genjuro, Kuroko; 140 was the sheathing, not the win), WHP $26
  (Hanzou), Kizuna $37 (Kim; $80 was not it; his voice $1CCA captured and added), DD 99 + 42 (Billy Lee: the back flip
  with DD's height / travel, model_dd) / 99 (transformed: Billy's colours back at its step 2). Silent where the source
  is: KOF98 Billy, K', Kuroko, Hanzou. The select pick / BOSS UNLOCKED play the same animation. Known: a win's
  separate effect objects are not played (K''s KOF99 glove flame).

- [x] 185. CAMERA RISING IN FURIES (20261007-020507-5d29, 0.0.92: "Why is the camera going up? That is weird."): the SS2
  audit (0.0.91) made the camera rise during any fury so Genjuro's spin (126 px up) shows. Revert the generic rise;
  keep the action on screen another way (Genjuro's victim carried at a height that fits, or a rise only when an
  object would leave the top, eased, never for ground furies).
  DONE (d8fe6d5): camera_y removed, the camera never moves vertically; Genjuro's WFT heights x WFT_FIT 0.33 (velocities
  and gravity, same timing: spin 42 px, victim 90, under the HUD). Proof /data/tmp/b188/out/c185_*.

- [x] 186. BILLY KANE'S FURY (20261007-014003-5d29: "seems recorded, not decoded ... a multi-hit fury with the movement
  of the character moving forward ... the hits should not make the opponent leave the ground unless it's the final
  one"): check the fire-ring fury's victim handling vs KOF98 (each ring hit's reaction: stagger in place, launch only
  on the last), decoded from the ring object's hit code; say plainly if any part is replayed.
  DONE (634cec6): the note is Billy LEE (Double Dragon; its bundle shows BILLY LEE's SUPER 236). export_dd gave the
  knockdown to every hit of the move's last animation: the first hit launched. Now only the last hit-opening step
  knocks down. DD (our emulator): hits 1-2 reel, 3-5 carry the victim 10-13 px up in its knockdown pose, fall after
  the 5th; the brawler reels on the floor to its 4th (last) hit (4 openings vs DD's 5 hits: not modelled). Nothing
  replayed. Billy Kane's ring: already reel x5 then launch on the 6th, as KOF98 (measured).

- [x] 187. (done 2026-10-07: the stick is a cursor graph computed from the places, build_tables.py select_stick at build time -> game_tables.c sel_stick (right / left) + sel_vert (up / down preferences), main.c sel_move reads it; rows by body centre (feet + head point, a new row past 16 px), right / left along the row and on to the next row (one loop through everyone, locked bosses passed), up / down the nearest by x in the row above / below (wrapping; a locked one: the next nearest). The Lab's Select screen tab computes the same (selectrender.js stick), draws the arrows and a table of the four ways; the list is the start order, and left / right's path only with game.json select.stick "order". harness sel_goto walks the loop. Proof: select_proof.py 39 screens 0 px, editor graph = build graph on 302 layouts, walk 156 presses in our emulator all on the graph (Robert -> right = Terry), /data/tmp/sel187/out select_walk.txt + lab_*.png; bank_proof ALL OK) SELECT STICK ORDER FROM POSITIONS (20261007-012550-5d29: "the layout is awesome ... however the sequencing
  is now messed up ... from Robert going right I end up on Yamazaki top left ... there should be some kind of automatic
  computation of sequencing based on coordinates ... whenever I modify or export a new layout"): compute the cursor
  graph from the fighters' screen positions (right = nearest fighter to the right in roughly the same row, else wrap;
  up / down = nearest above / below), at layout save time in the Lab and at build time; the Lab shows the arrows;
  the manual order list becomes an override only.

- [x] 188. REOPENED (0.0.92 tests): (a) Haohmaru SS2 grab: "the throws are okay ... however the grabbing motion sets the
  player and the victim in a reverse orientation" / "Haohmaru and Ryo are both facing right" (173459, 155732, 155708):
  the hold / grab phase's facing (SS2's mirrored steps in the hold, the victim's facing); (b) the burn palette
  (162034 Blitz Ball, 160855 Billy's ring): "looks nothing like when Terry ... gets engulfed in flame in KOF98": use
  KOF98's own burn palette and its cycle (decoded), for every fire hit; (c) 155538 Haohmaru's fury "still broken" (no
  details: compare his SS2 WFT with SS2 and say what differs).
  DONE: (a) baebd6f: SS2 has no hold, its throw swaps the victim behind on frame 1; the hold is now that picture
  mirrored (face to face, victim in front: bthrow_t.gframe), the throw unchanged. (b) d12b0de: KOF98's burn decoded:
  the victim's own sprite in palette $F8 / $F9, a 5-colour ramp over pens 1-15 rotated every 4 frames (fighter.c
  BURN_RAMP); Billy Kane's ring burns (KOF98 measured). (c) 9f71205: SS2's WFT connect = red backdrop 48 f, hold 40,
  half speed 30, victim thrown 76 f after the hit (SF_BIGHIT); still missing: weapon loss, throw height 74 vs 52.
  Proofs /data/tmp/b188/out.

- [ ] 189. (DONE ON BRANCH fix/189-ss2-rage-pose 2026-10-07, awaiting Bruno's review) SS2'S RAGE ANIMATION AS THE FLASH
  POSE (Bruno: "in Samurai Shodown II there is an animation that is triggered automatically whenever the power bar gets
  full ... it's standard for all characters"). Found [code + meas, study README "The rage-full moment"]: at POW = 32
  ($25CD2) the fighter, once idle ($26A3A), plays class 0 action 46 = **animation 140** for every one of the 16
  fighters (20-93 frames, his shout on an early step, red rage palette, POW sign; no freeze), measured in our emulator
  for all 15 + Kuroko (tools/samsho2/rage_ss2.py -> /data/neogeo_dict/samsho2/rage.json, also filled by real hits).
  Brawler: export_bm FLASH_POSES samsho2 'rage' (now SS2's default; game.json roster haohmaru / genjuro / kuroko
  flash_pose "rage") = anim 140 timed to the 28-frame freeze ('fit': each step scaled, Haohmaru 12 steps, Genjuro 18,
  Kuroko 23 with his flame aura), the shout sent on its step ('voice': bfpose_t.voice, fighter.c flash_pose; Haohmaru
  $1A $99, Genjuro $1A $D2, Kuroko $1A $E3 = SS2's samples byte for byte), the glow on the first step's head. Other
  poses unchanged (Kim / Hanzo / Billy Lee silent as in 0.0.96). Proof /data/tmp/rage189/out (tools/brawler/
  rage189_proof.py): ALL OK (SS2's moment vs the brawler's flash: <name>_ss2_vs_brawler.png; flash145 checks for the
  three; voices); controls_proof 3/3 ok, fury_inv_proof (AI_OFF copy) ALL OK, bank_proof ALL OK, regress no-bleed True;
  scenario todo189-haohmaru-rage-pose (lint 0). Open: the glow stays at the first step's head while Haohmaru drops into
  his low stance; SS2's red rage palette is not shown. Other sources (report only): WHP no animation at a full hero
  gauge [meas: P1's object identical to a run without the fill]; Double Dragon none (powered = the bars meet, "CHARGE";
  the power-up anim 81 is the player's A+B+C+D, already Billy's pose); KOF96 / 98 / 99, Kizuna, SS4 not checked here.

- [ ] 190. (DONE ON BRANCH fix/190-bank-headroom 2026-10-07, awaiting Bruno's review) P ROM BANK HEADROOM: after 0.0.98 +
  #184 bank 0 had 12,182 bytes free (packer bound 2,073), bank 1 153,042: the next fighter / animation would not fit
  bank 0. tools/brawler/bank_pack.py now packs balanced with a margin: the fewest banks in which every bank keeps
  BANK_MARGIN free (default 128 KB > the largest fighter's bulk, Rugal 125 KB), fighters (form groups whole) largest
  first into the emptiest bank; full 1 MB - 16 packing only when 7 banks cannot keep the margin. Result: 3 banks, P ROM
  4 MB (+1 MB): bank 0 415,832 free, bank 1 414,786, bank 2 383,166; MB1 unchanged. 4 MB P checked: Geolith masks the
  register to 3 banks (geo_calc_mask), the Android player and the Lab's core.wasm build that Geolith, NeoCart PROG v3
  latch = banks 0-6 (bank_proof: chip image banks 0-2 at flash MB 0-2, P1 at MB 7). docs/rom_packer_rules.md "P ROM".
  Proofs /data/tmp/bank190: bank_proof ALL OK, controls_proof 23/23 ok, cancel_proof all ok 23, regress no-bleed True
  (frame-exact), campaign29 campaign.json identical to /data/tmp/campaign/out29, Lab core.wasm (Node, make_site)
  vs desktop core 0 ticks differ (Robert stage 5, Ralf stage 1 wave 2, Terry stage 3 boss), Player (AVD JanusPhone,
  APK 0.0.24) loads the 4 MB-P ROM: title + stage 1 fight drawn (player_1.png / player_2.png); after merging brawler 0.1.0
  (/data/tmp/bank190/final): the same bank layout, bank_proof / controls / cancel / regress / campaign29 / core.wasm
  (Robert stage 5) all the same results (the Player run was on the pre-merge ROM, same banks).

- [ ] 192. (DONE ON BRANCH fix/192-billy-lee-fury 2026-10-07, awaiting Bruno's review) BILLY LEE'S FURY = DD'S VICTIM
  HANDLING PER HIT (20261007-014003-5d29, after #186: DD lifts the victim 10-13 px from hit 3 on and lands 5 hits where
  the brawler landed 4). Found in DD's code [code + meas, tools/doubledr/fury_dd.py -> /data/neogeo_dict/doubledr/
  fury192.json]: (a) the hit-clear test ($207B8) runs as the step clock LEAVES a step (+$2C still the old step's box set),
  not on entering one: export_dd.openings read it as entering, so the super's 5th punch (step 14, after step 11's $2B9
  record) never opened; fixed: 5 openings = DD's 5 hits (captured 5 / 5); the 623's rising hit (step 3, after the low
  jab's $B5) opens again too (DD close: 2 hits 55 reel + 67 launch, captured). (b) the reaction per hit ($258EC-$26076):
  index = the step's level + the victim's combo stun +$38 - 1 (+1 for a special record with byte 1 bit 4, +4 for a plain
  category hit), tables $2666A / $26672 / $26682 -> the super: 56, 57 reels, 69 (the knockdown hop) at hits 3, 4, 5;
  every Billy special's predicted reactions = the specials.json captures (623 55/67, 236 69, 214 55/51). export_dd
  dd_reactions / brawler_react now give every special hit DD's reaction: reel R_HEAVY, 67 R_KNOCKDOWN, 69 R_TRIP | 8
  (the last hit R_BLOWBACK | 8). fighter.c kof_react: a trip / blowback with the hittable bit = DD's hop (its pose
  BA_TRIP, up 3.5 px gravity 0.375, again in the air with the rise eaten by the hit's down knock $25B3A, 5 px a frame +
  the push 4.25 / 11.25 x 7/8 the attacker's facing way, hittable); no other fighter's data has the bit on a trip.
  Result (lab, Billy at x 20, Ryo 60 px ahead, proof /data/tmp/billy192/out, tools/doubledr/fury192_proof.py): 5 hits
  (DD 5); reels at 1-2; lifted to 13.8 after hit 3 (DD 12), 15.4 at hit 4 (DD 13), 7.9 at hit 5 (DD 8); the launch
  peaks at 11.6 (DD 12) and carries Ryo 101 px with the camera free (DD 155 incl. its 17-frame dragon pause), against
  the screen edge in the lab (DD in a corner: the same). Side effect (DD's data): Billy's 236 dash now sends the victim
  in DD's low hop (18 px up, 148 px away) instead of KOF's high blowback; 623 lands 2 hits up close. Not modelled: DD's
  global 17-frame pause with the dragon effect ($D6) after the 3rd and 5th hits. Super Billy has no fury (DD gives the
  form none) and Billy's MAX is the transformation (its hit: 67, unchanged). Checks: controls_proof / cancel_proof
  billy_lee + billy_super ok, bank_proof ALL OK, regress no-bleed True (frame-exact), scenario lint 0.

- [ ] 191. (DONE ON BRANCH fix/191-ss2-timing-rage 2026-10-07, awaiting Bruno's review) SS2 TIMING + RAGE PALETTE (found by the Kuroko boomerang job and #189): (a) every Samurai Shodown II move
  (Haohmaru, Genjuro, Kuroko: specials, furies, normals?) runs 2 frames LONGER in the brawler than in SS2 (e.g. Kuroko
  6ABC): find the cause (step-length conversion SS2 ticks -> brawler frames, a first / last step off by one like
  #181's WHP start-frame rule, the program's end condition) and fix it for every SS2 animation; (b) the SS2 rage flash
  pose (anim 140, #189) lacks SS2's red rage palette and its head glow stays at the first frame's head height while
  Haohmaru crouches: show SS2's rage palette (decoded: the palette it switches to) during the flash pose and move the
  glow anchor with each frame's head point. Proof /data/tmp/ss2t191/out: frame counts per SS2 move vs SS2 (before /
  after), ss2_proof frames, rage flash sheet SS2 vs brawler; controls_proof + cancel_proof haohmaru / genjuro / kuroko;
  bank_proof; regress no-bleed.
  DONE (a) [code + meas]: two frames, one at each end, for every SS2 program special / fury (normals were already
  exact: anim_tick plays them from their start frame). Start: SS2's action routine runs in the frame the action is set
  (the class, the animation, its first velocities / counts); the brawler ran no program in start_special's frame, so
  the whole move came a frame late. Now bspec_t.sflags SF_NOW (handlers_ss2 rom['now'] -> export_bm): fighter.c
  start_special runs the program's first frame in the start frame (a fury still after its flash pose). End: an SS2
  routine going back to neutral clears the class in the frame its condition holds; the program yielded one more frame
  before P_END: compile_prog now jumps to P_END in that frame. Also found: SS2's landing is y > 224 ($27802 cmpi #224 /
  beq: the floor line itself is not a landing): P_FALL a = 1 (fighter.c, only SS2 programs set it) -> Haohmaru /
  Genjuro 623S A land on SS2's frame; Haohmaru's Sake Kougeki (214A) played the other weapon mode's anim 329 after 328
  (102 frames, SS2 52): one animation now. handlers_ss2 check: lengths = SS2's, the same 3 rows with mismatches as
  before (they were 5). Table tools/samsho2/timing191.py -> /data/tmp/ss2t191/out/timing191.txt (41 rows: specials
  every button row, furies, normals): before +2 everywhere (214A +50), after 0 except Haohmaru 623S A+B (+2: its rise
  above 240 px, SS2's height rule not decoded, pre-existing y error) and Genjuro 236S A at 300 px (-3: SS2 holds its
  slash 3 frames there, unexplained; the 160 px capture hits first). Note: SS2's rise depends on the players' distance
  (623S 68 / 74 / 99 frames at 160 px, 66 / 71 / 97 at 200-300), so airborne rows are checked at 160 px only.
  (b) [code + meas]: SS2's display code adds the object's +$81 to the first layer's palette ($35C6 / $3656) and $25D3E
  sets it from POW ($25D72: 2 at 32): anim 140's body (palette 16, first layer only) shows the colour set's palette 18
  (tools/samsho2/ragepal_ss2.py: palette RAM unchanged, +$81 = 2 every frame of the pose). export_ss2.rage_palette ->
  bchar_t.fpal / fpal_ix, fighter.c fpose_pal: on through the freeze, the colour set back on the fury's first frame (or
  at special_end). The glow: bfpose_t hx / hy = each pose step's head (head_point on the body palette's parts only:
  Kuroko's aura excluded; other sources keep the one fhead), main.c sf_draw reads fighter_pose_head every frame.
  Proofs /data/tmp/ss2t191/out: timing191.txt / .json, rage/ (rage189_proof: ALL OK incl. rage_palette_ok = SS2's
  measured colours pen for pen, flash145 anchor_is_head frame by frame; <name>_ss2_vs_brawler.png), ss2_proof/ (frames:
  only the known wide / grab-pose differences), controls 3/3 ok, cancel all ok 3, bank_proof ALL OK, regress no-bleed
  True (strict). Scenario todo191-haohmaru-rage-palette (lint 0).

- [ ] 194. (DONE ON BRANCH fix/194-billy-lee-throws 2026-10-07, awaiting Bruno's review) BILLY LEE: THROWS + SMALL DRAGON PUNCH (20261007-110922-b3f3 "Billy does not have any throws yet";
  20261007-111015-b3f3 "For the down + C special move, use the version of the dragon punch that is actually with A, so
  the small" one): Double Dragon's throws decoded (command, animations, victim handling) through #146's standard
  throw, for Billy Lee and Super Billy; down+C = the 623 A row (variant table).
  DONE [code + meas] (tools/doubledr/throw_dd.py, study README "Throws"): DD's normal throw = a button with the stick
  left OR right, close (box gap < 10 / 8 / 6 px for B / C / D), from the THROW TABLE $23C2A + 48 x char (range, the
  thrower's animation 110-112, the VICTIM's 113-115 from its own table, the direction by the stick: not holding toward
  = the thrower turns = the back throw, damage $1000-$1400); the victim's handler 13 ($21AF0) copies the thrower's step
  each frame and places it from table $21B76 (pulled behind the turned thrower, over his head, in front), its step 4 =
  the release (damage, then handler 2's flight from its header: vx 6, vy 2, g 0.375), landing -> 71 bounce / 73. The
  script = DD row for row (victim step, place, height, release = DD's damage frame, landing, thrower end) for both forms
  x B / C / D x forward / back (0 mismatches; D forward: 11 rows at DD's stage edge). Brawler: throw_c = forward + A =
  DD's forward C throw, throw_d = back + A = its back throw (row flag 8), control return 35 rows (DD's own: Billy acts
  while the victim flies), release 25, land 49; the hold = DD's first picture mirrored (gframe, SS2's rule #188 a: the
  victim in front facing him), forward + A then plays DD's swap; victim_poses_dd.json; export_bm keys a throw's
  own-victim rows by the roster name (Billy Lee = doubledr:billy). game.json billy_lee "variant": {"623": "A"}: down+C
  peaks 73.1 px in 53 frames (DD's 623 A 73.1 / 52; D 140). Not modelled: DD's 16-frame dragon pause after the forward
  throw's release. Found (engine, all throws, not changed): fighter.c paired_update returns at the control return before
  placing the victim, so its row `ret` shows a frame late (one 6 px hitch in Billy's flight). Proof /data/tmp/billy194/out:
  throw194.json + summary194.json, sheet_<form>_<throw>.png (DD | brawler), hold_*.png, rise.txt; throws166 f (FIGHTERS=,
  forms by poke): Billy Lee all ok, Super Billy C ok / D n/a (no fury, by design); controls + cancel ok, bank_proof ALL
  OK, regress bleed_same / strict True. Scenarios 20261007-110922-b3f3 / 111015 (verify identical, lint 0).

- [ ] 195. HAOHMARU'S FURY TONED (20261007-113032-b3f3: "the red screen is too much and there shouldn't be so much freeze
  on impact" — the 0.0.93 SS2 hit sequence: red screen 48 f, hold 40 f, slow motion 30 f; 20261007-112936-b3f3: keep
  SS2's red rage palette through the motion after the charge, the big fireball): shorten / soften the red screen and
  the impact freeze (one short flash, a standard hit-stop), keep the rage palette until the fury ends.

- [ ] 196. THROW HITCH (found by #194): every throw's victim appears one frame late at the moment the thrower can act
  again (control return): a 6 px hitch in the flight. fighter.c throw / release code; prove on Terry, Geese, Billy Lee.

- [ ] 197. (DONE ON BRANCH fix/197-fire-hit-sound 2026-10-07, awaiting Bruno's review) KOF96'S FIRE HIT SOUND
  (20261006-162034-b3f3 reopened: "find the specific sound effect of the fire ... dig into KOF96's code: there's a specific
  sound effect played whenever somebody is getting hit by a fireball"): every burning hit plays KOF96's fire-hit sample.
  DONE [code + meas] KOF96's hit dispatcher ($16F7A: the victim's +$131 = the attacker's +$1B8 hit kind) calls the
  kind's handler from table $16FD6 (tools/kof96/hitsfx.py): kind 11 = $1A $13 + $1A $1F, 13 = the heavy hit + $1F, 21 =
  $1A $1F alone. Measured in our emulator (WLOG on the sound mapper's word, /data/tmp/fire197/cap96): Kyo's and Iori's
  623C hits send $1A13 + $1A1F, Iori's 236A and Krauser's Blitz Ball hits $1A1F alone. The sample: KOF96 M1 record
  $4536 (slot 1's table $447C + 6 x $1F) [51][$04F8][$0521][$DA], 10752 bytes, one key-on (its own driver in the tap
  core). KOF98 does not use it: its fire kinds play $1A $2E, another sample (7680 bytes). Brawler: songs.json sfx "from"
  $2E = kof96 $1A1F (build_snd.py now takes KOF96's Ver 0.1 driver: same table list $2E0E and record layout), named
  FIRE HIT (sound player); fighter.c hit_sfx: HIT_SFX's fire kinds already send $2E; a burning hit of another kind
  (roster[].fire: Blitz Ball, Billy Kane's ring) plays $2E in place of its plain hit (KOF96's kind 21), a kind's own
  sound (a fury's SDM IMPACT) gets $2E after it. V ROM used +10,240 bytes (5,976,320 -> 5,986,560), the padded V ROM
  unchanged (6,029,312). Not changed: KOF98's Yami Barai (Iori 236A) is no fire hit in the brawler's KOF98 data (no
  burn), so it keeps $13 (KOF96 sends $1F there). Proof /data/tmp/fire197/out (tools/brawler/fire197_proof.py):
  Kyo 623C, Iori 623C ($13 + $2E), Krauser 214A ($2E alone, as KOF96), Billy 23624C ($9C + $2E): each burns its victim,
  the Z80 keys $2E's pages $1636-$165F whose bytes = KOF96's $4F8-$521 byte for byte; WAVs kof96_1A1F.wav and
  brawler_*.wav; voice_proof --all krauser / billy / kyo: 39 of 44 OK, the 5 others (Billy 426C / 623A / 623B / 214B,
  Kyo 236A: voice timing) fail the same on the 0.1.5 build; bank_proof ALL OK; regress bleed_same / strict True.

- [ ] 142. FOCUS (Bruno, 2026-10-06): the Brawler move vocabulary, rationalizing every special move, and an efficient
  review pipeline (memory project_brawler_engine_vision). Step 1, no engine change: inventory of every mechanism the
  brawler has (prog ops, follow-ups, projectiles / effects, reactions, hit-stop, holds, screen fx, voices) grouped into
  standard features with parameters + which moves use each; the game-wide ruleset compared across sources (KOF96 /
  98 / 99, Kizuna, SS4, WHP) with a proposed standard per rule; the missing-features tally (every recorded / blocked
  move -> the feature it lacks); generated conversion sheets (ROM code -> understanding -> step mapping -> features
  used / missing -> fidelity) for sample moves; then Bruno reviews it on an interactive page. The recorded specials /
  furies below (#78-#138 still open) WAIT for the vocabulary: they need exactly the features it standardizes.

- [ ] 141. Input path recorder for Bruno (2026-10-06: "I will record some paths and you can then analyze them",
  replaces brute-force sweeps): neogeo_sdl gets a record key that saves a start savestate + the pads per frame to a file
  replayable by --script (frame-exact), and an analysis tool that replays it with the capture on and lists the states /
  inputs / windows that produced each follow-up (KOF98 / KOF99 / Kizuna). LOW PRIORITY (Bruno, 2026-10-06).

### KOF slot specials still recorded: FIRST (Bruno, 2026-10-06: "prioritize")
- [x] 79. (done 2026-10-06: KOF98 $48CCC from the ROM: a catch's dead frames are 1 + the catching step's hit-stop ($1B402 counts it down: class 2 = 3 frames), the held victim keeps KOF's held hurt box (states 404-407: $31 0, 192, 48, 64); 0 frame mismatches whiff + close, hits 12 / 12 on the same frames) Ryo up-fwd A+B = EX 646A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 81. (still recorded 2026-10-06: the handler's no-mash path decodes (0 frame mismatches whiff), but KOF's trace has no mash input (romspecials98 never enters the repeat), so the hit side and the A+B-again mapping are not proven) Ralf A+B = AAAA (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 83. (still recorded 2026-10-06: KOF98's capture try for 426B gives a normal (state 90), so no handler is found; it needs a KOF trace that enters the special) Robert up A+B = 426B (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 84. (done 2026-10-06: KOF98 $4A856 from the ROM, as Ryo's EX 646A (#79): 0 frame mismatches whiff + close, hits 12 / 12 on the same frames) Robert up-fwd A+B = EX 646D (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 86. (still recorded 2026-10-06: the snake arm's handler branches on a test the decoder cannot place (an address off a4, `f-1`)) Yamazaki up-fwd A+B = 214A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 88. (still recorded 2026-10-06: a mash move; the capture try gives a normal (state 99), no handler found; needs a KOF trace with the repeated C) Billy A+B = CCCC (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 89. (done 2026-10-06: KOF98 $6F642 from the ROM: the rise's `cmpi #192, +$20; bcs` = PC_LOW (height below N); 0 frame mismatches whiff + close, hits 5 / 5) Billy up A+B = 623D (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 91. (done 2026-10-06: KOF98 $3C262 from the ROM: `addi #16, +$20` = a height nudge; 0 frame mismatches whiff + close, hits 1 / 1) Kyo up A+B = 421B (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 92. (done 2026-10-06: KOF98 $3E0A6 from the ROM (the drift went with the event latch, #139): 0 frame mismatches whiff + close, hits 3 / 3) Kyo up-fwd A+B = EX 421D (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 94. (still recorded 2026-10-06: KOF98 $70A6C decodes (`bcs` on the distance +$BC = near; the brawler's PC_FAR takes the nearest opponent on the lane before a hit) and plays with 0 frame mismatches whiff + close, but its catch sends the victim into KOF's held victim states 432-435, placed each frame from a table ($25376 / $25396, offsets at $2835CA), which the brawler does not model: the explosion misses, hits 1 / 2) Iori fwd A+B = 624D (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 95. (done 2026-10-06: KOF98 $70872 from the ROM, its flames 254 / 255 too: 0 frame mismatches whiff + close, hits 3 / 3) Iori down A+B = 623C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 96. (still recorded 2026-10-06: the same handler as 624D (#94), the same blocker: hits 1 / 2) Iori down-fwd A+B = 624B (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 101. (done 2026-10-06: KOF96 $4A010 from the ROM: 0 frame mismatches whiff + close, hits 3 / 3) Geese fwd A+B = 63214C (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 102. (done 2026-10-06: KOF96 $4A010 from the ROM: 0 frame mismatches whiff + close, hits 3 / 3) Geese up A+B = 63214A (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 105. (done 2026-10-06: KOF96 $4B186 from the ROM: 0 frame mismatches whiff + close, hits 1 / 1) Krauser up A+B = 623B (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 106. (done 2026-10-06: KOF96 $4B186 from the ROM: 0 frame mismatches whiff + close, hits 1 / 1) Krauser up-fwd A+B = 623D (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 115. (done 2026-10-06, TODO #173: God Press played from KOF98's handler; see #173) (still recorded 2026-10-06: the handler calls the stage-wall test $18092 (as his fury, #118) and branches on vx (+$50)) Rugal fwd A+B = 624A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 116. (done 2026-10-06, TODO #173: Kaiser Wave A played from KOF98's handler; see #173) (still recorded 2026-10-06: Kaiser Wave's hit routine steps a state list through +$C2 and counts its hits in +$138 (a multi-hit object): not modelled) Rugal up A+B = 6426A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 117. (done 2026-10-06, TODO #173: Kaiser Wave C played from KOF98's handler; see #173) (still recorded 2026-10-06: as 6426A (#116)) Rugal up-fwd A+B = 6426C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 119. (still recorded 2026-10-06: KOF96 $4E3DE's body plays with 0 frame mismatches whiff + close (0 / 0 hits, as KOF), but its wind objects (states 179-181, picked at random) come from the animate routine's step-effect table ($249E8, init $253D2), not from the handler: the ROM program would drop them) Goenitz down A+B = 214C (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).

- [ ] 140. Every multipart / follow-up special of Kyo, Iori and K' (Bruno, 2026-10-06): #74 only did Iori 214A and K'
  236C / 623C. Search every slot special of the three (Kyo: EX 236A, 236C, 623C, 421B, 214A, EX 421D; Iori: 236A, 624D,
  623C, 623D, 624B; K': 214D, 236B, 236D, 623A) for follow-ups: decoded from the handlers (handlers98.py P_CHECK) AND
  brute force (every button / direction / motion at every frame, whiff / hit / block), then play them through the
  follow-up mechanism; proof followups_proof.py + romspecials_check 0 frame mismatches. FIRST after the furies job.
  Status 2026-10-06 (brute force paused by Bruno; he will record input paths in the game instead): played + proven
  (KOF captures at the decoded windows, romspecials_check 0 frame mismatches whiff + hit per chain, followups_proof game
  vs model 600 / 603 + brawler vs model 96 / 96): Kyo fD 236C -> again (63214A/C: Tsumi Yomi) -> fA (6A/C: Batsu
  Yomi); Iori uD 623D -> again in the kick's hit-stop (214A/C, hit / block only) -> Aoi Hana's 3 parts; Iori ufD,
  K' D / dD unchanged. Disagreements: Iori 623D -> 214C plays Aoi Hana C in KOF, the brawler A (by design); a 214A
  after Aoi Hana ends restarts it in KOF (a new special). Brute-forced (whiff / hit / block, every 2nd frame, partial
  results /data/tmp/fu140/out/brute_*.json): all of Kyo's slots + fury, all of Iori's (no follow-up but 623D);
  decoded-only (no input check found, not brute-forced): K' 214D, 236B, 236D, 623A, 23624C. Left for Bruno's recorded
  paths: those K' moves; Kyo 6A presses just after a hit-stop (KOF misses some the model takes); Kyo fury's held C
  (delays the release, not a follow-up, not played).

- [x] 139. (done 2026-10-06: Geese and Krauser now hit from the ROM (Raging Storm's pillars after their side effects end; Kaiser Wave spawned 87 px ahead, 96 px up): fury_inv_proof all 18 ok, Geese locks from frame 39, Krauser from 61) Geese's fury (1632143C Raging Storm) and Krauser's (641236C) never hit a standing enemy at any distance (no
  attack box on the body or its objects in the export), so they never connect (and never get the fury invincibility,
  b04a9e8). Found by tools/brawler/fury_inv_proof.py; fix with their ROM reading (#78+ items for them).

### Recorded specials to read from the ROM (Bruno, 2026-10-05, after testing 0.0.55: "most recorded specials are off")
One item per assigned special that still replays a capture (artifact grid https://claude.ai/artifact/KRSf1H6UNWyzSmgwZ3FgfY).
- [x] 78. (done 2026-10-06: KOF98 $4322E from the ROM: Power Geyser, its pillar object from the +$C2 table; romspecials_check 0 frame mismatches whiff + close, hits 1 / 1; /data/tmp/fury/out_terry) Terry C fury = 21416C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 80. (done 2026-10-06: KOF98 $481C4 from the ROM: rush 178 catches ($37 box), +$19C routine places the victim 70 px ahead and holds it, 12-hit barrage 181 without hit-stop, finisher 184 / 185; 0 frame mismatches whiff (P2 jumping over) + close, hits 14 / 14 on the same frames, P1 x within 8.5 px, victim within 1.75 px until the launch) Ryo C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 82. (done 2026-10-06: KOF98 $50810 from the ROM: 163 rush + 164 barrage (hit-stop class 4: no stop, the victim reels in place) + 166; 0 frame mismatches whiff + close, hits 15 / 15) Ralf C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 85. (done 2026-10-06: KOF98 $49A88 from the ROM (Ryo's code, Robert's states): close 0 frame mismatches, hits 14 / 14 on the same frames; whiff: KOF's rush catches P2 anywhere, airborne too, so the brawler's whiff is checked against the decoded model: 0 mismatches) Robert C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 87. (still recorded 2026-10-06: a command grab whose hits come from the victim's own scripted states (KOF98 shared victim states 433-442, advanced by the attacker setting the victim's +$D1 bit 7), not from Yamazaki's handler; connects (fury_inv_proof)) Yamazaki C fury = 236236C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 90. (done 2026-10-06: KOF98 $6F9C8 from the ROM: 0 frame mismatches whiff + close, hits 3 / 3) Billy C fury = 236236C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 93. (done 2026-10-06: KOF98 $3D4EA from the ROM (Orochinagi: the held C read as released, no hold in the brawler): 0 frame mismatches whiff + close, hits 1 / 1) Kyo C fury = 21426C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 97. (done 2026-10-06, #74: Iori 214A as 3 parts (again / again: up-forward + A+B) played from the ROM, 0 frame mismatches whiff + hit) Iori up-fwd A+B = 214A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 98. (still recorded 2026-10-06: the rush and its catch decode (claws 165, held victim), but the finisher is the engine's cinematic hit ($1EB20 box + $3F8A test, then $1E7E8's table by +$F8 runs both fighters' states), not Iori's handler; connects) Iori C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 99. (done 2026-10-06: KOF98 $5B7DC from the ROM: 0 frame mismatches whiff + close, hits 6 / 6 (KOF's whiff: her fan reaches the far P2 twice, P1 frames identical)) Mai C fury = 21426D (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 100. (done 2026-10-06: KOF98 $64B9C from the ROM (its A / C mash repeat read as no mash): 0 frame mismatches whiff + close, hits 5 / 5 (its steps' byte 1 = 3: KOF's reel without slide, bstep_t flag 4; before it 4 vs 5)) Yashiro C fury = 21426C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 103. (done 2026-10-06: KOF96 $4A43C from the ROM: its side effects signal their end to Geese (+$D1 bit 7), then the six pillars from their table; 0 frame mismatches whiff + close, hits 1 / 1; it connects (#139)) Geese C fury = 1632143C (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 104. (done 2026-10-06: KOF96 $4C3E6 from the ROM: Blaster Wave's 4 waves from its offset table (the last one state 137); 0 frame mismatches whiff + close (0 / 0: the waves land 128 px out, KOF misses at 48 px too); at 112 px hits 4 vs 3: KOF96's reaction table is not read, the first wave knocks the victim down) Mr. Big C fury = 23623C (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 107. (done 2026-10-06: KOF96 $4B5E8 from the ROM: Kaiser Wave spawned 87 px ahead, 96 px up (the capture had no box); 0 frame mismatches whiff + close (0 / 0, KOF too), at 112 px hits 1 / 1; connects in fury_inv_proof (#139)) Krauser C fury = 641236C (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 108. (done 2026-10-06, #74: K' 236C + fA (6B) / fAB (6D) played from the ROM, 0 frame mismatches whiff + hit) K' A+B = 236C (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 109. (done 2026-10-06, #74: K' 214D played from the ROM, 0 frame mismatches whiff + hit) K' fwd A+B = 214D (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 110. (done 2026-10-06, #74: K' 623C + fA / fAB at the rise played from the ROM, 0 frame mismatches whiff + hit) K' down A+B = 623C (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 111. (done 2026-10-06, #74: K' 236B played from the ROM, 0 frame mismatches whiff + hit) K' up A+B = 236B (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 112. (done 2026-10-06, #74: K' 623A played from the ROM, 0 frame mismatches whiff + hit) K' down-fwd A+B = 623A (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 113. (done 2026-10-06, #74: K' 236D played from the ROM, 0 frame mismatches whiff + hit) K' up-fwd A+B = 236D (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 114. (done 2026-10-06: KOF99 $39B10 from the ROM: the shot's hit (+$D1 bit 7) starts the dash (while the target is over 224 px away) and the lunge's catch, 11-hit rush, finisher; 0 frame mismatches whiff (vs the decoded model: KOF's shot reaches P2 anywhere) + close, hits 13 / 13) K' C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF99's handler code (handlers98.py, KOF99 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [x] 118. (done 2026-10-06, TODO #173: Gigantic Pressure played from KOF98's handler; see #173) (still recorded 2026-10-06: the catch decodes, but its routine grinds the victim until the stage wall ($18092: x <= 32 / >= 736 of KOF's 768 px stage); the brawler has no such wall (the screen edge clamps), so its length can't match KOF; connects) Rugal C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 120. (still recorded 2026-10-06: as Iori's: the catch and rush decode, the finisher is the engine's cinematic hit (KOF96 $17796 box + $3676 test); connects) Goenitz C fury = 2141236C (recorded, "off" per Bruno 0.0.55): play it from KOF96's handler code (handlers98.py, KOF96 routine table); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 121. Haohmaru A+B = 236C (recorded, "off" per Bruno 0.0.55): play it from SS4's 68000 code (tools/samsho4: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 122. Haohmaru fwd A+B = 421C (recorded, "off" per Bruno 0.0.55): play it from SS4's 68000 code (tools/samsho4: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 123. Haohmaru down A+B = 623B (recorded, "off" per Bruno 0.0.55): play it from SS4's 68000 code (tools/samsho4: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 124. Haohmaru up A+B = BUST 236D (recorded, "off" per Bruno 0.0.55): play it from SS4's 68000 code (tools/samsho4: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 125. Haohmaru down-fwd A+B = BUST 623D (recorded, "off" per Bruno 0.0.55): play it from SS4's 68000 code (tools/samsho4: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 126. Haohmaru C fury = BUST 236D (recorded, "off" per Bruno 0.0.55): play it from SS4's 68000 code (tools/samsho4: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 127. Hanzo A+B = 236A (recorded, "off" per Bruno 0.0.55): play it from WHP's 68000 code (tools/whp: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 128. Hanzo fwd A+B = 236D (recorded, "off" per Bruno 0.0.55): play it from WHP's 68000 code (tools/whp: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 129. Hanzo down A+B = 623B (recorded, "off" per Bruno 0.0.55): play it from WHP's 68000 code (tools/whp: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 130. Hanzo up A+B = 214C (recorded, "off" per Bruno 0.0.55): play it from WHP's 68000 code (tools/whp: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 131. Hanzo down-fwd A+B = 623A (recorded, "off" per Bruno 0.0.55): play it from WHP's 68000 code (tools/whp: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 132. Hanzo up-fwd A+B = 214D (recorded, "off" per Bruno 0.0.55): play it from WHP's 68000 code (tools/whp: no handler decoder yet); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 133. Kim A+B = 214B (recorded, "off" per Bruno 0.0.55): play it from Kizuna's handler code (tools/kizuna/substates_kz.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 134. Kim fwd A+B = 236C (recorded, "off" per Bruno 0.0.55): play it from Kizuna's handler code (tools/kizuna/substates_kz.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 135. Kim down A+B = [2]8C (recorded, "off" per Bruno 0.0.55): play it from Kizuna's handler code (tools/kizuna/substates_kz.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 136. Kim up A+B = 421A (recorded, "off" per Bruno 0.0.55): play it from Kizuna's handler code (tools/kizuna/substates_kz.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 137. Kim down-fwd A+B = 236A (recorded, "off" per Bruno 0.0.55): play it from Kizuna's handler code (tools/kizuna/substates_kz.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 138. Kim C fury = 6246A (recorded, "off" per Bruno 0.0.55): play it from Kizuna's handler code (tools/kizuna/substates_kz.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).

### Parked ideas (Bruno, 2026-10-06: kept for later, not queued)
- CPS-2 / CPS-3 bug studies (both fully decrypted; CPS-2 = 68000, CPS-3 = SH-2): captures via the FinalBurn Neo libretro
  core in our harness, an SH-2 disassembler for CPS-3.
- Ryu and Ken from Street Fighter III 3rd Strike in the brawler: feasibility first (colours per 16x16 tile vs the Neo
  Geo's 16-colour palettes, frame count / C ROM bytes, scale, parries as a new vocabulary feature).
- Form links beyond Billy: Rugal -> Omega Rugal (KOF95 data exists, a boss second phase), Iori -> Riot of the Blood (KOF97).

### Needs Bruno (the loop never acts on these; it lists them in its report)
- Billy Lee (#149) choices to review: the transformation's trigger (down+D, a full meter: his MAX slot, DD has no MAX
  super), its exit (a lost life; DD keeps it for the round), Super Billy without a fury (DD gives the form none), the
  C slots (C 214, forward 236, down 623; Super Billy C 41236, forward 236, down 623, up 214), the variant row played
  (the heaviest, D; game.json roster[].variant to change), his voices: only $26 / $28 / $1C fit (KOF98's 223 voice
  codes are taken: a bigger voice table or fewer voices elsewhere for the rest).
- MVS save commit (#48): accept "MVS saves at the ending / game over", or investigate writing our block directly to
  battery RAM (SRAM unlock register) without a BIOS hand-back.
- AES BIOS: neo-epo.bin, from Bruno's own console / set, for the Console mode (UniBIOS-AES until then).
- Desktop emulator and test tools: switch the default from UniBIOS to SNK's MVS BIOS too?
- Life bars on EASY: start full for every enemy (one line), or keep 2 px per life point?
- Fork mame/ and geolith on GitHub (they can't be pushed today)?
- Delete tools/brawler/export_bm.py.rej (a patch leftover; the agents were not allowed to).
- Guard / blocking: the brawler has none, so $17 BLOCKED HIT (#75) has nothing to play on. Add a guard mechanic
  (which button / input?) or drop the sound?
- Tablet: update to Player 0.0.11 (the test build there still has the double-download bug).
