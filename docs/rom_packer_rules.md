# ROM packer rules

Boundary and layout rules the build packer must respect when it places assets into the cartridge regions
(the "web build pipeline" plan, 2026-10-04). Status: **[hw]** hardware fact, **[ours]** a rule our own code imposes,
**[unverified]** from memory / docs, to be checked before the packer relies on it.

## C ROM (sprite tiles, 128 bytes each)

- Tile numbers are 20 bits (1,048,576 tiles = 128 MB). In VRAM SCB1 a tile takes two words: the low 16 bits of
  the number, then an attribute word with palette, flips and the top 4 bits (bits 4-7). **[hw]**
- A **page** = 65,536 tiles = 8 MB (one value of the top 4 bits).
- **All tiles of one fighter must sit in one page**: the brawler's frame tables store only the 16-bit low part and
  `bchar_t.tile_hi` supplies the top 4 bits for the whole fighter (draw.s). **[ours]**
- Pack per fighter (bin packing into pages), not per export block: per-block placement left ~4 MB of padding in the
  16 MB image (measured 2026-10-04). Deduplicate tiles globally across all fighters / stages (~0.9 MB of exact
  duplicates measured); a left/right mirror can be stored once and drawn flipped (small gain, ~0.05 MB).
- Tile 0 = empty; a page's first tile with tile_hi is the page start (blank). **[ours]**
- LSPC auto-animation: animated tiles must be groups of 4 or 8 consecutive tiles, aligned (the low 2 or 3 bits are
  replaced by the animation counter). **[hw]**
- Stage tiles (make_stage_ra.py, one pool for every stage): tiles 1-1535 below the fighters (TILE_BASE 2048), the rest
  after the fighters (each map word carries its own bits 16-19, so stage tiles may cross pages); banner 1536, shadow / box corners
  1664-1669, sparks from 1724. **[ours]**

## S ROM (fix layer, 32 bytes per 8x8 tile)

- 12-bit tile number: 4,096 tiles = 128 KB addressable at once; more needs cart-side banking (later SNK carts).
  **[hw]**
- Ours: font at ASCII codes, bar glyphs from $80 / $B6, arrow $7F, portraits from $100 (16 tiles each). **[ours]**

## V ROM (ADPCM samples)

Built by `tools/port/build_snd.py` from `examples/brawler/songs.json` (2026-10-05): only the samples the manifest's
songs and sound-effect codes play, every sample record rewritten to the new addresses.

- YM2610 sample addresses: start / end registers in 256-byte units, 24-bit addressing = 16 MB per bus. **[hw]**
- **ADPCM-A: a sample must not cross a 1 MB boundary.** **[hw, not checkable in our emulator]** Geolith's YM2610
  (ymfm, `src/ymfm/ymfm_adpcm.c` `adpcm_a_channel_clock`) keeps a full-width address counter (`m_curaddress++`, so a
  sample that crosses a 1 MB boundary plays on into the next megabyte) and compares only the low 20 bits with the end
  address (`((m_curaddress ^ end) & 0xfffff) == 0`; its comment: the YM2610 compares 20 bits, twinspri's select music
  needs it). On the chip the counter itself is 20 bits with the top 4 bits latched (NeoGeo dev wiki), so a crossing
  sample wraps to the start of its own megabyte: our emulator would play a crossing sample correctly and hide the bug.
  The packer never places an ADPCM-A sample across a 1 MB boundary.
- ADPCM-B: no boundary in ymfm (start, end and limit compared at full width, `adpcm_b_channel` end / limit checks);
  none known on the chip. Start / end on 256-byte steps. **[ymfm]**
- Above 16 MB: samples are reached through cart bank switching (NEO-PCM2 on SNK carts): a sample must sit inside
  one bank. **[hw, cart-dependent]**
- Our carts (PROGBK1 layout): ADPCM-A and ADPCM-B share one V bus (16 MB total). **[ours, NeoCart PROG v3]**
- Size: Geolith reads any V size (no address mask: `ymfm_external_read` returns 0 past the end); the build pads to
  64 KB. Brawler 0.0.28: 16 MB (KOF98's whole V ROM); with the manifest: 2.82 MB used (3,014,656 bytes padded).

## M ROM (Z80 sound program)

- The Z80 sees 64 KB: a fixed part ($0000-$7FFF) plus switchable windows (NEO-ZMC on SNK carts). **[hw]**
- **Song data the driver reads through a window must sit entirely inside that window's bank.** KOF98's driver maps
  a song's "bank set" n (byte table `($2E06)[cmd - $20]`, 4-byte sets at `$2708`, 7 of them: n = 0-6) = M1
  $8000 * (n + 1) at Z80 $8000-$FFFF; RAM from $F800, so a song lives in Z80 $8000-$F7FF (30 KB). build_snd.py keeps
  the fixed 64 KB (driver, tables, set 0 = KOF98's menu songs), copies each other set a kept KOF98 song uses (whole,
  renumbered from 1), then packs ported songs first-fit into new sets. **[ours, per driver]**
- Sample tables / instrument records live in the driver's own tables, and their real extents matter (the fixed area
  is packed): KOF98 ADPCM-A tables of slots 0-5 `$3C4C` + $600 n (codes $00-$EF: from $F0 on the driver takes another
  path, `$311B` / `$0618`), slot 6 `$604C` (237 codes: slot 7 starts at `$65FA`), slot 7 = 11-byte looping records
  (`$65FA`, $F0 codes), ADPCM-B 13-byte records `($2E1E)` = `$711A`, 117 of them (other tables follow from
  `$770B`, song `$20`'s header at `$7B0D`). Records no kept song or effect uses are emptied and reused. **[ours, per driver]**
- Size: neobuild pads M to a power of two (256 KB here; 160 KB used: fixed 64 KB + 3 bank sets). **[ours]**

## P ROM (68000 program)

- 1 MB fixed (P1, $000000) + a 1 MB window ($200000) switched by a bank register on the cart. **[hw]**
- **The bank register**: a word write of n to $2FFFF0 maps P ROM MB 1 + n at $200000 (SNK's standard latch).
  Geolith (geo_m68k.c, default board): any write at $2FFFF0-$2FFFFF, n masked to the banks the P ROM has, bank 0 at
  reset, saved in its save states. NeoCart PROG v3 (hardware/neocart/pboard): a 3-bit latch on D0-D2 clocked by
  /PORTWEL, cleared by /RESET, banks 0-6 at flash MB 0-6, P1 at MB 7 (sim_pboard.py; pboard_flash.py writes that map).
  The scheme both do: **banks 0-6, a word write to $2FFFF0, nothing read from the window in an interrupt**
  (`sdk/include/neo_bank.h`: BANK_set keeps a copy, the register is write-only). **[hw + ours]**
- **Link**: sections `.p2bankN` sit at $200000 and load at $200000 + N MB (`sdk/boot/neoscan.ld`; `.p2data` = bank 0);
  tools/neobuild.py drops the $100000-$1FFFFF gap: P ROM = MB1, bank 0, bank 1, ... (1 + N MB, no power of two; more
  than 7 banks refused). A bank keeps its last 16 bytes free (the register's addresses). The linker does not check a
  pointer from one bank into another (the banks share their addresses): tools/brawler/bank_pack.py does. **[ours]**
- **The brawler's rule (TODO #174, 2026-10-06): a fighter's bulk in its bank, everything shared in MB1.** The decision
  was between (a) copying the hot per-frame tables of the fighters in play to work RAM at stage start, (b) grouping a
  stage's cast in one bank, (c) selecting the bank at each access. (a) does not fit: 64 KB of work RAM, 26 KB used,
  and a fighter's tables are 34-117 KB, 8 fighters on screen. (b) cannot
  hold: the players pick any of the roster and the minion pool is 11 fighters. (c) alone would put a bank switch in
  every cross-fighter read (combat: attack box vs hurt box, throws: thrower's script vs victim's postures, the AI).
  Chosen: (c) on a split of the data by who reads it. MB1 keeps every table another fighter, combat, the AI or the HUD
  reads (bchar_t, animations + steps with their boxes, normal and special, throws / holds, postures, palettes, routes,
  voices, the bspec_t / bproj_t headers: 262 KB for 21 fighters, ~12.5 KB a fighter); a fighter's bank holds what only
  its own code reads: frames, parts, tile numbers, its specials' script rows, programs, parts, links, variant columns,
  its projectiles' rows (1.53 MB, ~73 KB a fighter). The bank is then needed in four places only: the fighter's update
  (fighter_update), its projectiles (projectiles_update, proj_row), its drawing (main.c draw: draw.s fighter_tiles /
  fighter_place) and an attacker's box from a script row (combat, dbg_draw: copied out under its bank); each switch
  is BANK_set(CH_BANK(ch)) ... BANK_set(old). Cost: a compare per select, a 16-bit write only when the bank changes;
  measured (tools/brawler/bank_cpu.py, the whole campaign with P1 throwing normals / specials / furies, the game's own
  CPU % per 16-tick window): busiest stage (5) mean 66.2 % -> 67.8 %, worst window 96 % -> 96 % (all stages: worst
  stages 1-5 96 / 94 / 98 / 100 / 96 -> 97 / 95 / 99 / 96 / 96). **[ours]**
- **bank_pack.py** (between the compile of bm_chars.c / bm_spec.c with -fdata-sections and the link): a table of a
  banked type goes to its fighter's bank when that fighter is the only one whose data reaches it (contexts from
  bm_chars[i] down every relocation); shared tables (KOF's common projectile end rows: 2 tables, 16 bytes) and all they
  lead to stay in MB1. A fighter and its form link's target share a bank (form_set swaps bchar_t in place). Fighters
  whole (a form group whole), each bank 1 MB - 16. **Headroom (TODO #190, 2026-10-07)**: the fewest banks in which
  every bank keeps `BANK_MARGIN` bytes free (default 128 KB: more than the largest fighter's bulk, Rugal 125 KB, so one
  more fighter fits in any bank), filled balanced (largest first, each into the emptiest bank, ties to the lowest);
  only when 7 banks cannot keep the margin does it pack to the full 1 MB - 16 (with a warning). A new bank costs 1 MB
  of P ROM and nothing else: Geolith masks the register to the P ROM's banks (geo_calc_mask: 3 banks -> mask 3), the
  Android player and the Lab's core.wasm are that Geolith, the NeoCart PROG v3 latch holds banks 0-6. Refuses any pointer from a bank into another bank, and
  from an MB1 table into a bank unless it is a holder (bchar_t element, bspec_t, bproj_t) of the same fighter. Writes
  build/bm_bank.c (bm_bank[]: each fighter's bank), build/banks.txt / banks.json (per bank: used, free, fighters).
  BANK_SPLIT=mask: proof layouts (bank = parity of the fighter index's bits in the mask). **[ours]**
- **Proof of the reads** (TODO #174): a read made with the wrong bank returns another fighter's bytes only in a layout
  where the two fighters sit in different banks. Masks 1, 2, 4, 8, 17 separate every pair of the 21 fighters at least
  once; built with `-DNEO_BANK_ALWAYS_WRITE` (BANK_set writes every time: the same cycles in every layout, so the
  harness's mid-tick sampling sees the same thing) the 6 layouts gave byte-identical controls / cancel / regress /
  campaign / fury-invincibility / CPU outputs. Against the unbanked build: the same JSON everywhere except regress's
  enemy-placement traces of one fighter and some screenshots' shadow parity: timing (a bank switch costs cycles; the
  harness pokes and samples inside a tick), gone when the timing is equal. tools/brawler/bank_proof.py checks the link,
  the .neo and the NeoCart v3 chip image. **[ours]**
- Brawler 0.0.77 + #174: MB1 419,308 bytes used (code ~90 KB, main.c's stage / HUD tables 61 KB back from $200000,
  fighter tables 262 KB), 629,268 free; bank 0 1,035,800 bytes (12,760 free: 12 fighters), bank 1 496,914 bytes
  (551,646 free: 9 fighters); P ROM 3 MB.
- Brawler 0.0.98 + #184 (before #190, first fit): bank 0 1,036,378 bytes (12,182 free), bank 1 895,518 (153,042 free).
  #190 (balanced, 128 KB margin -> 3 banks, P ROM 4 MB): bank 0 632,728 (415,832 free: 7 fighters), bank 1 633,774
  (414,786 free: 7), bank 2 665,394 (383,166 free: 9 incl. Billy Lee's two forms); MB1 unchanged (463,358 used). **Tables the code reads in one go must not straddle a bank edge** (a table is never split:
  sections are whole). **[ours]**

## Descriptor

Every build writes, per region: total size, used, free, whether banking is used, and per asset (fighter tiles,
stage tiles, song data, samples) its offset and size — so each rule above can be checked from the descriptor.
