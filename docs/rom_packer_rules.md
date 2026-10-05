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
- **Tables the code reads in one go must not straddle a bank edge**; code that reads banked data switches the bank
  first. Today the brawler fits in 2 MB without banking (~1.7 MB used). **[ours]**

## Descriptor

Every build writes, per region: total size, used, free, whether banking is used, and per asset (fighter tiles,
stage tiles, song data, samples) its offset and size — so each rule above can be checked from the descriptor.
