# Neo Geo MVS Flash Cart — Bill of Materials
# For JLCPCB PCBA Assembly
# Rev 1.0 — 2026-04-25

## Flash ROM Chips

| Ref     | Value           | Package   | Qty | Description                        | LCSC (check availability) |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| U_PROM  | AM29F400BB      | TSOP-48   | 1   | P ROM — 4Mbit 16-bit flash (5V)   | C2682159 or equivalent    |
| U_SROM  | SST39SF010A     | PLCC-32   | 1   | S ROM — 1Mbit 8-bit flash (5V)    | C191340 or equivalent     |
| U_MROM  | SST39SF010A     | PLCC-32   | 1   | M ROM — 1Mbit 8-bit flash (5V)    | C191340 or equivalent     |
| U_CROM1 | AM29F400BB      | TSOP-48   | 1   | C1 ROM — sprite data lower 16-bit | C2682159 or equivalent    |
| U_CROM2 | AM29F400BB      | TSOP-48   | 1   | C2 ROM — sprite data upper 16-bit | C2682159 or equivalent    |

## Microcontroller & Support

| Ref     | Value           | Package   | Qty | Description                        | LCSC                      |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| U_MCU   | RP2040          | QFN-56    | 1   | USB programmer MCU                 | C2040                     |
| U_FLASH | W25Q32JVSSIQ    | SOIC-8    | 1   | RP2040 firmware SPI flash (4MB)    | C571986                   |
| Y1      | 12MHz           | 3215      | 1   | Crystal for RP2040                 | C9002                     |
| U_REG   | AMS1117-3.3     | SOT-223   | 1   | 3.3V LDO regulator                | C6186                     |

## Bus Interface

| Ref     | Value           | Package   | Qty | Description                        | LCSC                      |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| U_SR1-3 | 74HC595D        | SOIC-16   | 3   | Shift register (address bus)       | C5947                     |
| U_BUF1  | 74HC245D        | SOIC-20   | 1   | Data bus buffer/level shifter      | C5949                     |
| U_BUF2  | 74HC245D        | SOIC-20   | 1   | Control bus buffer/level shifter   | C5949                     |

## Connectors

| Ref     | Value           | Package   | Qty | Description                        | LCSC                      |
|---------|-----------------|-----------|-----|------------------------------------|---------------------------|
| J_USB   | USB-C 2.0       | SMD       | 1   | USB Type-C receptacle (USB 2.0)    | C168688                   |

## Passive Components

| Ref          | Value  | Package | Qty | Description                    | LCSC   |
|--------------|--------|---------|-----|--------------------------------|--------|
| C1-C13       | 100nF  | 0402    | 13  | Decoupling caps (1 per IC)     | C1525  |
| C14-C16      | 10uF   | 0805    | 3   | Bulk caps (LDO in/out, USB)   | C15850 |
| C17-C18      | 15pF   | 0402    | 2   | Crystal load caps              | C1548  |
| R1           | 1K     | 0402    | 1   | USB boot pull-up (GPIO for bootsel) | C11702 |
| R2-R3        | 27R    | 0402    | 2   | USB series resistors           | C25100 |
| R4-R5        | 5.1K   | 0402    | 2   | USB-C CC resistors (UFP/sink)  | C25905 |
| R6-R7        | 10K    | 0402    | 2   | Pull-ups (SR_nOE, BUF_nOE)    | C25744 |
| D1-D5        | BAT54S | SOT-23  | 5   | Schottky diodes (CE bus OR)    | C82544 |
| D6           | BAT54S | SOT-23  | 1   | Power OR (VBUS / Neo Geo 5V)  | C82544 |

## JLCPCB PCB Specifications

- Layers: 2
- Dimensions: ~140mm x 110mm
- Thickness: 1.6mm
- Surface finish: ENIG (gold fingers required)
- Gold fingers: Yes — beveled, 30° chamfer
- Gold finger length: 6mm
- Min trace width: 0.2mm
- Min via: 0.3mm drill / 0.6mm annular

## Estimated Cost per Board (JLCPCB, qty 5)

- PCB fabrication (ENIG + gold fingers): ~$15-25
- SMT assembly (all components): ~$30-50
- Components: ~$15-25
- Total per assembled board: ~$60-100
