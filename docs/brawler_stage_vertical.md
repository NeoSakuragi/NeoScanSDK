# Brawler: Robo Army's vertical parts (study, 2026-10-04)

Labels: **[code]** read in Robo Army's P ROM (`/data/neogeo_dict/roboarmy/p.dis`), **[meas]** measured in our emulator's
core (Geolith driven from Python like `tools/brawler/harness.py`: coin, START, scene byte poked into `$10E056` during the
story intro), **[inf]** inferred. Engine background: `/data/neogeo_dict/roboarmy/README.md`. Horizontal parts are the
brawler's stages 0-5 (`tools/brawler/make_stage_ra.py`, examples/brawler/README.md "Stages").

## What Robo Army does

- **They are descents, not climbs.** [meas] Scene 4 (area 2) and scene 10 (area 5): the camera y `$104048` grows
  0.25 px a frame (15 px a second): area 2 from y ~40 to 960, area 5 from ~40 to 528. New rows enter at the bottom.
- **The player hangs on a wire at a fixed screen place.** [meas] x stays 96, ground `+4` 193; stick left / right does
  nothing, up / down slide along the wire (`$100008`, -24 .. 56); attacks work; enemies hang on wires too.
  [code] `$6400-$6446`: each frame the scroll step `$104058` (= min of the speeds `$104050` / `$104054`) is added to the
  camera y and to every active object's y (62 objects from `$100200`, active = `+$70`), and taken off the players' y
  unless `$10406A` is set: objects stay in screen space, only the background moves. No floor exists in these parts.
- **Row streaming.** [code] `$6400`: when the next row y `$104060` is less than 256 px below the camera, 32 tile words
  are written (one per column, slot 1-32, SCB1 row (y >> 4) & 31) and `$104060` += 16. Data: band y >> 8 (1024 bytes),
  row (y & $F0) >> 4 inside the 16-word column: `$531F2 + area_base*512 + (y >> 8)*1024 + col*32 + row*2`.
  [meas] one row every 64 frames; the ring is 32 sprites x 32 tiles (512 x 512 px), x scroll stays 0, so only columns
  0-19 (320 px) of the 512 px bands are ever on screen.
- **Extent (split points, now measured).** Area 2: bands 0-4 = ids `$14-$1D` (512 x 1280; the camera stops at y 960,
  screen bottom 1183); band 5 (`$1E-$1F`) is never shown; the street part is the boss arena `$1F-$20` (scene 5, full
  refill `$E78` from id `$1F`, camera locked at ring x 192) = brawler stage 2. Area 5: bands 0-2 = ids `$35-$3A`
  (512 x 768); at the bottom the player breaks a window, `$104069` goes 255 -> 1, then a cut to area 6 (scene 11, full
  refill) [meas]. Area 2's change to the arena: the same cut [inf] (not observed: the bottom's enemies were not beaten).
- **Who switches.** [code] An event-script interpreter at `$838A` (per-area scripts) has opcodes that write `$104069`
  (vertical mode, from the scene table `$7640` at scene start, `$751C`), `$10406A` (players carried by the scroll),
  `$10406B` (scroll lock; `$77A2` also sets it, [inf] while a wave is alive) and `$104016` (LSPC auto-animation speed). The
  horizontal streamer `$6292` and the vertical one `$6400` are the same routine's two branches (`tst $104069`).
- Cost in Robo Army: [meas] slots 1-32 at height 32, 20-21 sprites on every line, as in the horizontal parts.
  Area 2's descent: 913 tiles, 16 palettes; area 5's: 274 tiles, 4 palettes, no auto-animation.

## What our engine would need

Today [code]: one plane of 21 sprites (22-42), height `stg->rows` (12), SCB3 written once in `stage_init`, X one run of
21 words a frame, a column of 24 words rewritten when it enters. `floor_top` is a variable (fighter.h) that draw.s,
shadows, sparks, debug boxes and the hit test read, so a floor that moves on screen is one assignment a frame.

Common to every option (vertical drawing): the plane sprites at height 32 (the 512 px vertical ring; SCB1 already has
the room: 64 words a sprite), a camera y, SCB3 as one run of 21 words a frame (y = 496 - (row*16 - cam_y)), and a row
streamer: when a 16 px row enters, 21 tile words of 2 words each (21 short runs, stride 64). The builder exports a
descent as 20 columns x (bands*16) rows (only 320 px is ever shown). Sprites per line unchanged (21), VRAM unchanged,
fix layer / HUD unchanged (the art then fills rows 0-1 behind the HUD, as in Robo Army). C ROM: + 913 / 274 tiles
(117 / 35 KB). ~60 lines of C + ~30 of Python.

- **(a) Fighting during the descent.** Two forms:
  - Robo Army's own model, screen space: fighters keep `floor_top` constant, only the background scrolls. With no floor
    in the art the fighters would need a platform (an elevator) drawn as sprites: a full-width platform under the band
    is ~21 more sprites on lines 158-223, where the fighters already reach 88 of the 96 per line (worst case measured
    in 0.0.26): line_guard would hide fighters. A narrow platform (~8 sprites, 128 px) fits but cramps 8 fighters.
    Or fighters hang on wires as in Robo Army: new animations we don't have (KOF has none).
  - World-fixed floors with a camera following the players up / down: `floor_top = base - cam_y` each frame (no other
    change in the fighter code); Z / Y unchanged. Needs ledges in the art; Robo Army's shafts have only small red
    ledges (area 2) or none (area 5).
- **(b) Transition scene (recommended).** Street stage -> auto-scrolled descent (no fighting, players shown hanging
  or hidden, no enemies) -> next street stage, as Robo Army's area 1 -> area 2 descent -> arena (stage 2). Only the
  vertical drawing above plus a stage sequence (stage_init of the next stage after the scroll ends; a cut or a fade,
  as Robo Army cuts); `floor_top`, Z, the camera's x code and the fighters untouched. 1280 px at Robo Army's
  0.25 px/frame is 85 s; at 2 px/frame 11 s.
- **(c) A static arena cut from it.** A window of the vertical art as a horizontal stage: no engine work (a STAGES
  entry with a row offset). Only area 2's bottom has a floor, and that is already stage 2 (the arena, ids `$1F-$20`);
  area 5's glass facade has none. Not useful beyond stage 2.

Recommendation: **(b)** for the prototype (it reuses Robo Army's flow and costs only the vertical plane drawing);
(a) only if the final game designs climb or elevator sections with its own art, then in the world-fixed form
(`floor_top = base - cam_y`), which the variable `floor_top` already allows. No prototype render was made (not cheap
enough for this round: it needs the vertical builder and drawing above).
