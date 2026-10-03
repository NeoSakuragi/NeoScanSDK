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
