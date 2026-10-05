# KOF96 animation dictionary

Data (exports, gallery pages, save states, capture recordings): `/data/neogeo_dict/` (see its README.md);
the `capture/` recording folders here are symlinks into it.

Gallery artifact: https://claude.ai/artifact/KbLRNbDS2RnysLmk8WTVzS

Same engine family as KOF95 (see `../kof95/README.md`, whose `gallery.py` also renders this export); this file lists
what is decoded for KOF96 and where it differs. ROM: `/data/roms/kof96.neo` (P = 1 MB P1 + 2 MB P2).
Captures run in **our emulator** (`emu/neogeo_sdl --capture` on the capture core, through `capture/emu.py`; see
"Capture in our emulator" below); save states `/data/neogeo_dict/ngsdl_sta/kof96/` (`vs` = Kyo vs Yuri, made by
`capture/boot_ngsdl.py kof96 --save 1590`; `c<id>` by `capture/specials96.prep`). MAME is not needed (its old states
stay in `~/.mame/sta/`, its captures in `/data/neogeo_dict/captures_mame_old/`).

## Memory map
- `$000000-$0FFFFF` P1. `$200000-$2FFFFF` one 1 MB bank of P2: write 0/1 to `$2FFFFE`; the word at `$200000` is the
  bank number. Bank 0 = file P2 first half (frame records, sprite definitions), bank 1 = default (palettes, throw
  lists). `rom96.Mem` reads CPU addresses with a bank.

## Cast
0 Kyo, 1 Benimaru, 2 Goro · 3 Terry, 4 Andy, 5 Joe · 6 Ryo, 7 Robert, 8 Yuri · 9 Leona, 10 Ralf, 11 Clark ·
12 Athena, 13 Kensou, 14 Chin · 15 Kasumi, 16 Mai, 17 King · 18 Kim, 19 Chang, 20 Choi · 21 Iori, 22 Mature, 23 Vice ·
24 Geese, 25 Krauser, 26 Mr. Big · 27 Chizuru · 28 Goenitz (checked by rendering every id's idle frame). 29: shared
effects (super flash = state 58), 30-31 other effect tables.

## Engine (decoded from code)
| What | Where | vs KOF95 |
|---|---|---|
| animation engine | `$4D50` | same structure; step counter `+$80` (KOF95 `+$82`); flags `+$7C/+$7D` |
| state → slot | `$4F24`: remap `$5C2C` (identity 0-34) → `$78624` → **one map shared by all characters**, 1 word per state | KOF95: per-character byte pairs |
| animation tables | `$080000 + id*4` → 512 slots, `$800` per character | 256 slots |
| animation step | `[ticks][byte → +$7E][frame INDEX:16][flags:16]`; `$FD` box `[slot | type<<2][x][y][w][h]` (handler `$4EF8`, slot 0 = attack, 1-3 hurtboxes) | KOF95: 24-bit frame pointer, `$FD TT` |
| frame record | bank 0 `$23C008[id] + index*6`, parts `[x][y][word]`; object `+$28` = current record | word: bits 0-9 sprite def (KOF95 0-8), 13 chain, 15 H flip, 14 V flip |
| sprite definitions | bank 0 `$26C000[id]`, renderer `$5254`, 11 formats via jump table `$54E0` | KOF95: one format |
| palettes | bank 1 `$200002 + n*32`; body block n = `$100 + id*$20` (16 palettes), mirror set n + 16 | sprite-def palette byte `16+k` = palette k of the block (body, accessories and effects) |
| physics | walk `$6E8EE + id*4`, jump vy / gravity `$6E96E + id*8` (16.16); hop = the jump with `vy -= vy >> 2` (code `$EF24`); see Jumps | walking back = walk; jump drift = walk (the prejump loads it from the walk table) |

### Sprite definition formats (from the renderer's handlers)
Header `[palette offset][format][columns][rows]`; column-major grid, masks MSB = top row; tile bits 16-19 in bits 4-7 of
an attribute byte. 0/4: 16-bit masks + 32-bit base, consecutive tiles; 1: 8-bit masks, consecutive; 2: no mask, per
cell 16-bit code + high byte (alternating order, code first); 3: shared high word + 16-bit code per cell; 5/6: 16/8-bit
masks + the format-2 stream (format 6 aligned to even); 7/8: shared high word + 16/8-bit masks + 16-bit codes;
9/10: base word + 16/8-bit masks + one byte per cell (low byte of the code). Implemented in `rom96.sdef`.
(`tools/neosdk`'s KOF96 decoder guessed these and is wrong for formats 6 and 10.)

## Game states (labelled on Kyo vs Yuri, `capture/labels.py`)
Movement 0-14 (idle, walks, jumps by direction), crouch 21-23, guard 26-28 / 32-36, run 48-50, backstep 51-53;
normals 80-115 (per button: close, far, jump, jump diagonal, crouch); C+D 116; specials 117-255; hits 256-266,
blowback 288 → 298 → 334 → 343 → 355 → get-up 66, trip 327; throw poses 400+. `export96.MOVES` names them.

## Jumps (`capture/jumps.py`, KOF96 / KOF98 / KOF99, 2026-10-04)
Two heights. Stick up held = the regular jump, up released before take-off = the hop (KOF98 Terry: up held 2-6 frames
hops, 7+ jumps; K' 2-4 / 5+; one frame of input lag, the prejump lasting 3-5 frames by fighter). States (all three
games, every roster fighter): prejump 3 / 7 / 11 (up / forward / back), jump rise-fall 4-5 / 8-9 / 12-13, hop 15-16 /
17-18 / 19-20, landing 6 / 10 / 14 (one animation slot for the prejumps, one for the landings; jump and hop
animations are distinct slots and differ: Terry's forward / back jumps are somersaults, his hops the vertical tuck).

Physics (code, KOF98 `$13B74`-`$13C00` + `$13E2A`; KOF96 `$EF24`, KOF99 `$E578` the same hop routine): the prejump
copies the fighter's walk speed (walk table) to +$50 and launch speed / gravity (jump table) to +$58 / +$5C; a hop sets
+$E0 bit 3 and takes `vy -= vy >> 2` (lsr.l #2): 3/4 of the launch speed, the same gravity and horizontal speed; a
super jump (down, up) multiplies the horizontal speed by 1.5 (`$13DFA` / `$13E0E`, not measured). Prejump on the ground:
the prejump animation's steps at ticks + 1 frames each, + 1. Checked on 14 fighters x 6 kinds: every launch speed,
gravity and horizontal speed equals the rule bit for bit (`export96.jump_physics`). Per frame: y += vy, then vy -= g;
at the apex the rise -> fall state change runs two steps in one frame (Kyo: steps 1.0, 0.149, -0.852).

| fighter | jump vy / g (px/frame) | hop vy | walk = dx | jump apex / air frames | hop apex / air |
|---|---|---|---|---|---|
| Terry (96 + 98) | 9.4375 / 0.5117 | 7.0781 | 2.969 (96), 3.168 (98) | 91.6 / 36 | 52.4 / 27 |
| Kyo (98), K' (99) | 10.2578 / 0.6172 | 7.6934 | 3.082 | 90.2 / 33 | 51.6 / 24 |
| Kyo (96) | 10.625 / 0.6055 | 7.9688 | 3.082 | 98.3 / 35 | 56.4 / 26 |
| Geese (96), Yamazaki (98) | 8.7031 / 0.5078 | 6.5273 | 2.773 / 2.645 | 78.9 / 34 | 45.2 / 25 |
| Mai (98) | 11.0 / 0.5859 | 8.25 | 3.383 | 108.7 / 37 | 62.2 / 28 |

Air normals (per button A / B / C / D): regular jump vertical 82 / 91 / 100 / 109, forward 84 / 93 / 102 / 111, back
86 / 95 / 104 / 113 (the back state uses the forward one's animation slot). Hop: **KOF96 has no hop normals** (a hop
plays the regular jump's state for its direction); **KOF98 / KOF99: 120 / 121 / 122 / 123 for every hop direction**
(their animations equal the forward jump normals' for the roster checked, except K' D; they differ from the vertical
ones for Kyo D, Mai C / D, Billy C / D, K' C / D).

## Special moves
**Recogniser `$11C76`** (P1 `$11C42`, P2 `$11C4E`; `commands96.py`). Each frame the player's 60-byte input history is
shifted; a byte = stick (bits 0-3 up/down/left/right) | buttons (bits 4-7 A-D). Lists at `$71B9E + id*8` = [facing
left, facing right] (picked by comparing the fighters' x, so forward/back are resolved in the ROM); a list = pattern
pointers ended by a negative long. Pattern `[n][window][hold:16]` + n steps `[type*4][value]`, oldest first, checked
newest first within `window` frames. Step types: 0 byte equal, 1 any bit, 2 buttons equal, 3/4 charge (equal / any,
held ≥ hold), 5 stick equal, 6 stick bits without buttons, 7 buttons without stick, 8 stick and buttons, 9 stick equal
and a button. A match stores the buttons pressed; the character's move code (e.g. Kyo `$17B60`) picks the move by
them (`& $50` = A/C, `& $A0` = B/D). Entries 0-2 are shared: run (6 5 6), backstep (4 5 4), super jump (2 then 8).

**Capture** (`capture/specials96.py` → `specials96.py`): every command of every fighter with each button, on red
life (supers allowed), P2 far away; one emulator run per fighter. A move is kept when its first special state is new.
Projectiles are pool objects (`$100100 + n*$200`, owner at `+$84`) that use the **owner's own animation table**
(`+$70` = owner id); a finished projectile stays allocated, frozen on a step (treated as ended once it stays longer
than that step's ticks). Supers are recognised by the shared super flash (table 29, state 58). Every non-charge command
is also tried in the air. Result: 293 distinct moves (21 aerial), 6-15 per fighter. Not covered: command grabs on a
close opponent (tries are made at distance, so grabs show their whiff), moves that need a condition the tries don't
create (e.g. after a hit, or MAX mode). Checked against MAME screenshots: Kyo's Orochinagi body really is drawn in the
flame palette (frames 738-741). Close pass (`--passes close`, KOF96 too since 2026-10-04: P1 x $180, P2 x $1B0): the hit
versions; `specials96.load` attaches a close try of a kept move as its `close`. Each row also records P1's animation
step (+$74 / 6), live attack box (+$90: type x y w h), hit-stop counter (+$124 high byte: counts down from the hit to 0,
$FF none; measured in KOF96/98/99, starts where P2's life drops), P2's state, life (+$138), height and x.

## Throws
**Victim placement `$1AF72`** (helper `$1B062`): the victim is moved to the thrower and offset by entry
`thrower +$80 − 1` of the list at victim `+$C2` (size `+$C6`). Entry `[dx][dy][word]`: dx/dy = 6-bit magnitude × 4,
bit 6 negative, bit 7 of dx = which fighter is drawn in front; word bits 0-8 = victim state (shared map), bits 9-15
flags (`$40` = release). Lists live in bank 1; list = table base + victim id × size, set by `$1A980` (`$1A992`: by the
opponent's id); each table has 29 lists. **Thrower side `$1B008`**: the thrower holds the list (its own `+$C2`) and
is placed relative to the victim while setting the victim's state: Mai's vault onto the shoulders, Kim's jump, Chin's
hold. Same entry meaning, so one decoder (`throwtables96.py`). **Stage edge `$1B134`**: when the victim would leave
the stage, the thrower is moved so the list's widest offset fits x 32 … 736. Choi's hold uses no list (victim states
432/433 at a fixed 16 px).

**Capture and validation** (`capture/throws96.py`, `capture/throws/tables.json`): forward+C, forward+D and an air
forward+C for every fighter on Yuri; 62 throws by 28 throwers (+ Choi's hold). Every captured list reproduces Yuri's
state and offset frame for frame up to the release (3625 / 3678 frames; the 53 others are Chin's victim after the
release flag). `throwscripts96.py` builds each throw for all 29 victims (thrower timeline from the capture, victim
pose and offset from that victim's list, flight after the release shifted to the release point).

## Capture in our emulator (2026-10-04)
`capture/emu.py` runs every capture in `emu/neogeo_sdl --capture` on the capture core
(`~/.config/retroarch/cores/geolith_capture_libretro.so`, see `emu/CLAUDE.md`); MAME is no longer used. The tracing that
needed MAME is in the recorder: `WLOG`, `SNDLOG`, `QLOG`, `VLOG`, `VFRAMES`, `RAMDUMP`, `PALDUMP` (pass them in
`emu.run(..., extra={...})`; formats in the comment block of `emu/neogeo_sdl.c`). States: `/data/neogeo_dict/ngsdl_sta/<game>/`.

Timing, measured against the MAME captures: MAME's Lua recorder applied a frame's inputs one frame late, so `emu.GAMES`
sets `input_lag` 1 for KOF96 / KOF98 (KOF99, captured in our emulator from the start, 0). With it the boot to `vs` is
frame-identical to MAME's (P1 object counter `+$1D2`): MAME's `vs` = our boot frame 1590 (KOF96) / 1593 (KOF98), and
KOF98's `c<id>` states made on prep98.lua's timeline (`emu.GAMES['kof98']['prep']`) put the fighters where MAME's did
(P1 x $149, P2 $249).

Equivalence (`capture/cmp_captures.py A.txt B.txt tries.json [gap]`, NOOBJ=1 without objects: each try aligned on P1's first state change, frames where the game lost
a frame (P1 `+$1D2` not advancing) skipped, P2's life as hit / no hit; all MAME tries had start lag 0):
- KOF98 specials (all 38 fighters): P1 state, step, frame record, x, height, facing, P2 state, hit frames and distance
  identical in 1969 / 1972 main tries, 1004 / 1018 close, 588 / 588 EX; with P1's objects 1860 / 895 / 568. Command
  normals 608 / 608, jumps 300 / 316, throw tables (base, size, side, states) 38 / 38, win poses 38 / 38 (+1 frame).
- KOF96 specials replayed with the MAME runs' own inputs (`captures_ngsdl/kof96/specials_mame_inputs`): 1379 / 1396
  (the rest: two fighters' supers, then later tries of the same run, which never reloads a state); throw tables 29 / 29
  (id 20: the hand-written hold-throw note). KOF96 jumps 118 / 166: MAME's Terry state `c3` was made by an older procedure.
- KOF99 (states and captures from the old core): byte-identical on the capture core.
- What differs, and why: (1) damage ±1-3 per hit: game-side, the same try started 0-7 frames later gives 85 or 86 on
  one state; (2) game frames lost to slowdown differ (68000 timing of the two emulators): e.g. Terry's close 623B has 7
  lost frames here, none in MAME; supers end a frame apart; (3) pool slots: a projectile can take another object slot
  (Terry's Power Wave at $100700 here, $102900 in MAME: the free-object order inside the `c<id>` state), which the
  former slot rule (`HELPERS_MAX`, $101600) dropped as a helper; since 2026-10-04 `specials96.load` follows objects by
  identity (born during the try; objects alive before it, KOF98's team helpers, never count; a freed object's slot
  may hold a new one: Ryo's Ko-ou-ken takes the slot of the spark before it); finished objects linger for different times;
  (4) sub-pixel P2 distances after hits (1 px).
- Brawler export (`export_bm.py`, all 14 fighters) from the re-capture: **not byte-identical** to the MAME-data build
  (2980 of 9892 arrays; frame numbering cascades): Terry and Yamazaki lose their D projectile pick through (3); KOF96
  main specials also changed inputs (the MAME captures predate today's `motion()`), KOF98 MAX captures used a 220-frame
  gap (now 320). So `/data/neogeo_dict/captures` keeps the MAME captures (canonical, the build reproduces from them);
  the full re-capture is in `/data/neogeo_dict/captures_ngsdl/` (5 GB) for the switch once (3) is solved.

## RAM
Fighters `$108100` / `$108300` (same object layout as KOF95: x `+$18`, height `+$20`, facing `+$31` bit 0, state
`+$72`, step counter `+$80`), health `+$138` (copy `+$150`, 103 = full). Team records P1 `$10A843` (ids
`$10A846-48`), P2 `$10A854` (ids `$10A857-59`). Swap: poke P1's ids and health 1, P2 hits; the new fighter loads by
frame ~1100-1400. Round timer `$10A836` (BCD).

## Files
| File | Purpose |
|---|---|
| `rom96.py` | ROM loading, banked reads, animations, frames, the 11 sprite formats, state map |
| `export96.py` | everything → `kof95_export.json` + C1/C2 in the KOF95 layout (`python3 export96.py OUT all`); then `../kof95/gallery.py --split OUT site/index.html` (atlases as `site/atlas/<name>.png`: the page alone would pass the artifact's 16 MB limit) |
| `commands96.py` | recogniser lists → `commands96.json` |
| `specials96.py` | captured specials → gallery scripts |
| `throwtables96.py` | throw list decoder + validation |
| `throwscripts96.py` | per-victim throw scripts (row key 'state.step' → `victim_poses96.json`) |
| `victim_poses96.json` | portable throw-pose vocabulary: posture + angle for all 164 list poses; the 97 one-step poses (states 385-511) mean the same frame for every fighter, multi-step knockdown/release states are per-fighter (Terry's posture path in 'sequences'); KOF95's postures + 'curled' |
| `capture/emu.py` | the recorder interface: `neogeo_sdl --capture` (scripted inputs, pokes, states, fighters + P1-owned pool objects per frame, tracing: WLOG / SNDLOG / QLOG / VLOG / VFRAMES / RAMDUMP / PALDUMP), per-game RAM addresses and state timeline |
| `capture/throws96.py`, `capture/specials96.py` | one emulator run per fighter |
| `capture/projectiles.py`, `projectiles96.py` | projectiles of the specials, by identity (owner +$84, table +$70, state +$72, kind +$F5; alive = +$06 != $FFFF): every ground special with the pool dumped every frame (RAMDUMP), P2 far / held off the ground (`--dist free`) / standing 60, 120, 200 px ahead -> `/data/neogeo_dict/captures/kof96/projectiles_<game>/`; `projectiles96.definitions(game, id)` = per input (normal and 'EX ...') its spawn row, flight rows (frame, x, height, live attack box +$90, own box), loop, death rule, end rows after a hit, hits per distance. How the games do it: `../kof98/README.md` "Projectiles" |
| `capture/cmdnormals.py` | KOF98/99 command normals (6A, 6B, 3C, 3D; not in the recogniser lists) played on every fighter, close + far, P2 life drops = hits -> `cmdnormals_<game>.json` (`export96.CMD_NORMALS`: state, hits, frames of the multi-state hops) |
| `capture/jumps.py` | both jump heights x 3 directions + the 4 air normals in each, per fighter (`--tap`: how long the stick must be held for a regular jump) -> `/data/neogeo_dict/captures/kof96/jumps_<game>.json` |
| `capture/boot_ngsdl.py`, `capture/labels.py` | the `vs` save state, state labelling |
| `handlers98.py`, `handlers98.md`, `capture/romspecials98.py` | KOF98 specials read from the ROM: a special's 68000 state handler decoded into engine primitives, a model of the animation engine + motion checked frame by frame against the game, the brawler export (`ROM_SPECIALS`: Terry, Ralf); catalogue and results in handlers98.md |
