# NeoCart Flash Cart Research — 2026-05-17

## Goal
Cheap, disposable MVS/AES cartridge boards for homebrew game distribution.
Must be compatible with original MVS, original AES, and upcoming AES+ (Nov 2026).

## Architecture Options

### Option A: NOR Flash + 74-series logic (~$42/cart at 1000 units)
Simplest. Fixed game per cart, reflash with TL866 programmer.

**PROG board:**
| Function | Chip | LCSC # | Size | Price @10 |
|----------|------|--------|------|-----------|
| P-ROM | S29GL064N90TFI040 | C117907 | 8MB | $2.81 |
| V-ROM × 2 | S29GL064N90TFI040 | C117907 | 16MB | $5.62 |
| Bank latch | 74HC374 | — | — | $0.06 |
| Addr decode | 74HC138 | — | — | $0.05 |
| Glue logic | 74HC00 | — | — | $0.04 |
| Data bus | SN74LVC16245ADGGR | C7824 | 16-bit | $0.95 |
| LDO | AMS1117-3.3 (BASIC) | C6186 | — | $0.21 |

**CHA board:**
| Function | Chip | LCSC # | Size | Price @10 |
|----------|------|--------|------|-----------|
| C-ROM × 4 | S29GL064N90TFI040 | C117907 | 32MB | $11.24 |
| S+M ROM | S29GL064N90TFI040 | C117907 | 8MB | $2.81 |
| Bank latch | 74HC374 | — | — | $0.06 |
| Addr decode | 74HC138 | — | — | $0.05 |
| Addr shifters × 3 | MDD 74LVC245APW | C53552926 | 8-bit | $0.57 |
| LDO | AMS1117-3.3 (BASIC) | C6186 | — | $0.21 |

### Option B: FPGA + SDRAM + SD card (~$12.50/cart components)
Universal. Any game, swap SD card. Needs Verilog firmware.

| Part | Chip | Cost |
|------|------|------|
| FPGA | Lattice ECP5-25F TQFP-144 | $6.00 |
| SDRAM | 32MB | $1.50 |
| SPI flash (bitstream) | — | $0.50 |
| SD card slot | — | $0.50 |
| Level shifters | 74LVC245 / 74LVC16245 | $3.00 |
| LDO + passives | — | $1.00 |

Pin budget: ~130 of 144 used. Tight but doable with shift registers for address input.
SDRAM bandwidth (200M transfers/sec) is 16× more than all Neo Geo buses combined (~12M).

### Option C: RP2350 + SDRAM (~$8/cart components)
Cheapest. MCU loads from SD into SDRAM, serves bus. Needs firmware + timing validation.

### Option D: Right-sized for danmaku game (~$33/cart)
Option A but fewer chips matched to actual game needs:
- P-ROM: 1× 8MB (code + LUTs + level data)
- C-ROM: 2× 8MB = 16MB sprites (between KOF96 and Last Blade 2)
- S+M ROM: 1× 8MB shared
- V-ROM: 1× 8MB (music + SFX)
- 5 flash chips instead of 9

## NOR Flash Available on LCSC/JLCPCB (May 2026)

| Size | Chip | LCSC # | Price @10 | Stock | Package |
|------|------|--------|-----------|-------|---------|
| 8MB | S29GL064N90TFI040 | C117907 | $2.81 | 227 | TSOP-48 |
| 16MB | S29GL128S10TFI020 | C2832244 | $4.25 | 65 | TSOP-56 |
| 32MB | MX29GL256FDT2I-11G | C2803109 | $4.00 | 10 | TFSOP-56 |
| 32MB | JS28F256P30TFE | C598859 | $3.19 | 17 | TSOP-56 |
| 64MB | S29GL512S10TFI010 | C393876 | $6.09 | 21 | TSOP-56 |
| 128MB | MT28EW01GABA1LJS | C2064354 | $15.05 | 92 | TSOP-56 |

Star part: **S29GL064N (C117907)** — best price/MB, best stock, TSOP-48 (simpler than TSOP-56).

## CPLDs (if needed instead of 74-series)

| Chip | LCSC # | Price @10 | Stock | Macrocells |
|------|--------|-----------|-------|-----------|
| XC9536XL-10VQG44C | C124132 | $5.36 | 320 | 36 |
| XC9572XL-10VQG44C | C569042 | $7.86 | 250 | 72 |
| ATF1502ASL-25AU44 | C1521100 | $4.00 | 22 | 32 |
| EPM240T100C5N | C10041 | $7.55 | 1353 | 240 LE |

## Level Shifters

| Chip | LCSC # | Width | Price @10 | Stock |
|------|--------|-------|-----------|-------|
| MDD 74LVC245APW | C53552926 | 8-bit | $0.19 | 4485 |
| SN74LVC16245ADGGR | C7824 | 16-bit | $0.95 | 3028 |
| SN74LVC4245APW | C354456 | 8-bit bidir | $0.36 | 2841 |

## Voltage Regulators (BASIC parts — no JLCPCB surcharge)

| Chip | LCSC # | Price | Stock |
|------|--------|-------|-------|
| AMS1117-3.3 | C6186 | $0.21 | 2.4M |
| XC6206P332MR-G | C5446 | $0.11 | 674K |

## Cost Comparison at 1000 Units

| Approach | Per cart | 1000 units |
|----------|---------|-----------|
| NOR flash + 74 logic (full) | $42 | $42,000 |
| NOR flash + 74 logic (right-sized) | $33 | $33,000 |
| FPGA + SDRAM + SD | $25 | $25,000 |
| SD + MCU (RP2350) | $18 | $18,000 |

## Cost at Volume with Mask ROM (10,000+ units)

Macronix (Taiwan) offers custom mask ROM service — XtraROM with optional DRM.
- MOQ: ~10,000-50,000 units
- Lead time: 8-12 weeks
- NRE (mask tooling): $5,000-15,000 one-time
- Per-chip cost: $0.30-0.80 at volume

| | Flash (1K) | Flash (10K) | Mask ROM (10K) |
|---|-----------|-------------|---------------|
| ROM chips | $11-20 | $8-15 | $2.50 |
| Total per cart | $42 | $25 | $18 |
| At $199 retail | $157 profit | $174 profit | $181 profit |

Contact: Macronix sales, Hsinchu Taiwan — https://www.macronix.com

## Existing Open-Source References

- **VTXCart** (github.com/xvortex/VTXCart) — proven multicart, Altera EPM3256 CPLD Verilog sources, but uses salvage-only flash chips
- **NeoGeoSDK proposal** (github.com/eaglesoftware777/neogeosdk) — NOR+CPLD+USB architecture doc, no PCB files
- **jwestfall69 daughterboards** — CHA C-ROM replacement modules for 161-in-1
- **pluger PCB scans** — high-res TIFF scans of 161-in-1 V3 PROG+CHA boards

## Neo Geo C-ROM Sizes for Reference

| Game | C-ROM |
|------|-------|
| KOF94 | 6MB |
| Metal Slug | 8MB |
| KOF96 | 10MB |
| Last Blade 2 | 24MB |
| KOF98 | 32MB |
| Garou MOTW | 40MB |

## Market Context (May 2026)

- **AES+ launches Nov 12, 2026** — $250 console, $90 official carts, ASIC-based (no emulation)
- Current homebrew Kickstarter carts: $289-499 (Bang² Busters 2, Metal Mack)
- $199 price point for a new original game undercuts homebrew, justifies premium over official rereleases
- At $199 × 1000 units = $199K revenue, ~$110K profit (flash cart approach)

## Next Steps

1. Prototype with FPGA v4 board (bench testing, Verilog development)
2. Design v5 flash cart PCB using neogeo-diag-mvs-prog outline (correct holes + gold fingers)
3. Kickstarter for 1000 units on flash carts
4. If demand exceeds 10K, switch to Macronix mask ROM for production run
