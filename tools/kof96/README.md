# KOF96 animation dictionary

Data (exports, gallery pages, MAME save states, capture recordings): `/data/neogeo_dict/` (see its README.md);
the `capture/` recording folders here are symlinks into it.

Gallery artifact: https://claude.ai/artifact/KbLRNbDS2RnysLmk8WTVzS

Same engine family as KOF95 (see `../kof95/README.md`, whose `gallery.py` also renders this export); this file lists
what is decoded for KOF96 and where it differs. ROM: `/data/roms/kof96.neo` (P = 1 MB P1 + 2 MB P2). MAME set:
`/home/bruno/roms/neogeo/kof96.zip` (BIOS `~/Downloads/neogeo.zip`), save state `~/.mame/sta/kof96/vs.sta` (Kyo vs
Yuri, made by `capture/boot.lua`).

**MAME: always pass `-noplugin cart_bridge`.** `/usr/share/games/mame/plugins/cart_bridge/init.lua` (an old NeoCart
test stub, enabled at start) takes a snapshot and exits MAME at screen frame 3400; the frame count is part of a save
state, so a run from `vs` dies after 30 s.

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

## Game states (labelled in MAME on Kyo vs Yuri, `capture/labels.py`)
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
life (supers allowed), P2 far away; one MAME run per fighter. A move is kept when its first special state is new.
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

## RAM (MAME)
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
| `capture/record96.lua` | recorder: scripted inputs, pokes, fighters + P1-owned pool objects per frame |
| `capture/throws96.py`, `capture/specials96.py` | MAME runs per fighter |
| `capture/cmdnormals.py` | KOF98/99 command normals (6A, 6B, 3C, 3D; not in the recogniser lists) played on every fighter, close + far, P2 life drops = hits -> `cmdnormals_<game>.json` (`export96.CMD_NORMALS`: state, hits, frames of the multi-state hops) |
| `capture/jumps.py` | both jump heights x 3 directions + the 4 air normals in each, per fighter (`--tap`: how long the stick must be held for a regular jump) -> `/data/neogeo_dict/captures/kof96/jumps_<game>.json` |
| `capture/boot.lua`, `capture/labels.py` | save state, state labelling |
