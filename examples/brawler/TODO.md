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

- [ ] 143. NEXT (Bruno, 2026-10-06): cancels as engine rules for every fighter: (1) any normal (A routes, air
  normals) cancels into a special (C + direction) or a fury (D / down+D MAX); (2) any special cancels into a fury.
  Defaults until Bruno says otherwise: a normal cancels on contact (hit or guard) during its active / cancel window, as
  KOF; a special cancels into a fury after its first hit lands (KOF's super cancel), the fury's flash and invincibility
  as usual. One rule in fighter.c (no per-move data), documented in docs/brawler_move_vocabulary.md; proofs: per fighter
  normal -> special, normal -> fury, special -> fury (hit and whiff), controls_proof, regress, campaign29.

- [ ] 144. Kim's Hienzan ([2]8C, down C) is missing its BLUE effect (Bruno, 2026-10-06): find the effect object /
  palette Kizuna draws with the rising staff (spawned object or an extra sprite part on the steps, its palette =
  blue), export it through the effects library and play it; check Kim's other moves for missing effects the same way
  (kim_proof frame-identical incl. effect objects vs Kizuna's screen, not just Kim's body).

- [ ] 145. Furies from non-KOF98 sources (Kim / Kizuna, Haohmaru / SS4, Hanzo / WHP, later Double Dragon) have no
  built-in wind-up under the super flash, so they whiff (Bruno, 2026-10-06: e.g. Kim). First confirm the cause (the
  rush moving during the freeze, or no pre-pose before the motion). Rule: a fury whose source has its own flash pose
  (KOF98's $FA flash step) keeps it; otherwise the engine plays the fighter's "flash pose" during the freeze, by
  default its TAUNT (Kim: Kizuna C+D taunt anim 21, ~92 f) cut to the freeze length (~28 f), a per-fighter data choice
  (taunt / charge / win pose; Billy: his power-up), then starts the fury. Concentration glow anchored on the pose's
  reference point (or the default). Proof: Kim's Phoenix, Haohmaru's and Hanzo's furies connecting on a dummy after the
  flash, contact sheets. UPDATE 0.0.67: the whiff's cause was that nobody could hit during the flash and Kim's first hit
  falls inside it; fixed (the fury's own attacker may hit during the flash). The flash pose stays wanted for
  consistency. Bruno: for these fighters the concentration glow emphasizes the HEAD (anchor = the pose's head point).

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
- [ ] 115. (still recorded 2026-10-06: the handler calls the stage-wall test $18092 (as his fury, #118) and branches on vx (+$50)) Rugal fwd A+B = 624A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 116. (still recorded 2026-10-06: Kaiser Wave's hit routine steps a state list through +$C2 and counts its hits in +$138 (a multi-hit object): not modelled) Rugal up A+B = 6426A (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
- [ ] 117. (still recorded 2026-10-06: as 6426A (#116)) Rugal up-fwd A+B = 6426C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
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
- [ ] 118. (still recorded 2026-10-06: the catch decodes, but its routine grinds the victim until the stage wall ($18092: x <= 32 / >= 736 of KOF's 768 px stage); the brawler has no such wall (the screen edge clamps), so its length can't match KOF; connects) Rugal C fury = 23624C (recorded, "off" per Bruno 0.0.55): play it from KOF98's handler code (tools/kof96/handlers98.py); proof romspecials_check-style 0 frame mismatches whiff + hit vs the original game, victim per its reaction table, no stick (holds / command grabs excepted).
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
