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

- YM2610 sample addresses: start / end registers in 256-byte units, 24-bit addressing = 16 MB per bus. **[hw]**
- **ADPCM-A: a sample must not cross a 1 MB boundary** (the address counter). **[unverified]** — check the YM2610
  docs and ymfm / Geolith's implementation.
- ADPCM-B: no 1 MB limit as far as known; start/end on 256-byte steps. **[unverified]**
- Above 16 MB: samples are reached through cart bank switching (NEO-PCM2 on SNK carts): a sample must sit inside
  one bank. **[hw, cart-dependent]**
- Our carts (PROGBK1 layout): ADPCM-A and ADPCM-B share one V bus (16 MB total). **[ours, NeoCart PROG v3]**

## M ROM (Z80 sound program)

- The Z80 sees 64 KB: a fixed part ($0000-$7FFF) plus switchable windows (NEO-ZMC on SNK carts). **[hw]**
- **Song data the driver reads through a window must sit entirely inside that window's bank.** KOF98's driver
  plays ported songs from "bank set 6" (M1 $38000-$3F7FF); tools/port/ff3_to_kof98.py places them there. **[ours,
  per driver]**
- Sample tables / instrument records live in the driver's own tables (KOF98: ADPCM-A tables via $0D, ADPCM-B
  records at $711A); new entries go into unused slots. **[ours, per driver]**

## P ROM (68000 program)

- 1 MB fixed (P1, $000000) + a 1 MB window ($200000) switched by a bank register on the cart. **[hw]**
- **Tables the code reads in one go must not straddle a bank edge**; code that reads banked data switches the bank
  first. Today the brawler fits in 2 MB without banking (~1.7 MB used). **[ours]**

## Descriptor

Every build writes, per region: total size, used, free, whether banking is used, and per asset (fighter tiles,
stage tiles, song data, samples) its offset and size — so each rule above can be checked from the descriptor.
