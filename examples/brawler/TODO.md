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

- [ ] 67. Samurai Shodown IV fighters into the character bank (Bruno: "start with Haohmaru first"): a full SS4 exporter
  (study: /data/neogeo_dict/samsho4/README.md — own engine, 444/454 frames pixel-exact): Haohmaru end to end into the
  brawler (animations, palettes, boxes, specials, weapon objects as needed), then the others. Running in a worktree
  since 2026-10-05.

- [ ] 68. Brawler Lab for Samurai Shodown IV fighters: the pose picker (char_images.CANDIDATES has no samsho4 list: Haohmaru
  is skipped), check move / special / enemy pictures for samsho4 banks; Haohmaru's SS4 voices (voices.py covers KOF only).

- [ ] 69. Specials from the ROM for everyone: extend tools/kof96/handlers98.py (loops, ROM state tables, inlined
  per-fighter subroutines, owner-watching effects, compare / random branches; est. 60-70 % of KOF98's 415 handlers),
  then KOF96 / KOF99 routine addresses; the captured scripts stay the fallback (Vulcan Punch, command grabs, supers).
  Proof per fighter as romspecials_check.py does (0 frame mismatches whiff + hit). Terry + Ralf done in 0.0.37.

- [ ] 70. Haohmaru's forward+D (SS4 421C) has a baked impact / KO scene (Bruno): recapture it as a whiff, or read it from
  SS4's own code (the handlers98 approach for SS4); also his other open points (memory reference_samsho4_extraction).

- [ ] 71. Controls revamp (Bruno, 2026-10-05): A attack (all normals via routes: direction + position), B jump (also a
  jump-cancel link in routes, on hit only -> air sub-routes), A+B SPECIAL MOVES = the six slots by direction (N, fwd,
  down, up, down-fwd, up-fwd; Power Wave, Power Dunk, Rising Tackle...; also from a grab), C FURY = desperation moves
  (Power Geyser and the other KOF DM / SDM supers, SS4 rage moves), D TAG mode (Bruno will explain). Chord detection
  window (2-3 frames) for A+B; routes / Chain Lab glyphs / Terry's routes and the default trees re-authored for one
  attack button. After the six-slot job.
  SPECIAL METER (Bruno, 2026-10-05): a meter gauge, full at the start; each special move consumes meter; the meter
  refills slowly over time; a special triggered WHILE BEING HIT (allowed: a "get out of trouble" move) costs twice as
  much, and the player's palette flashes fully white for a split second to show something was consumed. Furies (C):
  cost to be decided.

- [ ] 72. Restore KOF98's hit count on Terry 214D (2), 623A (5), 623B (2) and Robert 624D (3) (review round 1): since
  the victim fix (no stick) they hit once less; re-time the missing hit(s) so they land, without sticking the victim
  to the attacker ([[feedback_brawler_no_victim_stick]]).
- [ ] 73. Extract the specials Bruno mapped that the bank lacks: Yamazaki's snake arm 214B (middle) and 214C (low)
  (214A exists), Billy's angled stick attack (find it in KOF98). Then apply the slot mapping from review round 2
  (artifact https://claude.ai/artifact/CpAmeQcqCtmrK9EPJ68HyM, db map/<fighter>) once Bruno says done.

- [ ] 74. Follow-up specials (review round 2): moves that continue on more input. Iori's 214A is a 3-part sequence
  (each part needs its own input): reverse engineer KOF98's logic and play it. K' has many follow-ups, notably after his
  236A, which opens more routes in KOF99: read them from the ROM and support them (one follow-up mechanism for both).

- [ ] 75. Hit sounds by use (review round 2, Bruno's listening): $9C SDM IMPACT on desperation moves' hits (the C fury,
  Yuri's Shin Shoryuken sound), $19 GRAB START when a grab / command grab connects, $17 BLOCKED HIT for guarded hits,
  $3D BACK BREAK on back-breaker throws (Krauser's), $2B SLASH for any blade hit. The menu cursor sound is to change: take
  Fatal Fury 3's own cursor sound (Bruno). Find the command FF3 sends on its menu / select cursor (MAKOTO v3.0 driver,
  tools/makoto3, capture in our emulator), and play that sound in the brawler: as an SSG cue if it is SSG, else port it
  (FM / ADPCM-A sample into the brawler's sound ROMs via songs.json).

### Needs Bruno (the loop never acts on these; it lists them in its report)
- MVS save commit (#48): accept "MVS saves at the ending / game over", or investigate writing our block directly to
  battery RAM (SRAM unlock register) without a BIOS hand-back.
- AES BIOS: neo-epo.bin, from Bruno's own console / set, for the Console mode (UniBIOS-AES until then).
- Desktop emulator and test tools: switch the default from UniBIOS to SNK's MVS BIOS too?
- Life bars on EASY: start full for every enemy (one line), or keep 2 px per life point?
- Fork mame/ and geolith on GitHub (they can't be pushed today)?
- Delete tools/brawler/export_bm.py.rej (a patch leftover; the agents were not allowed to).
- Tablet: update to Player 0.0.11 (the test build there still has the double-download bug).
