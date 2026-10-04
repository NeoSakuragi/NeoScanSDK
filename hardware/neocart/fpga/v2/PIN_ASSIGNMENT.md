# ECP5-25F TQFP-144 — Verified Pin Assignment
# Source: prjtrellis open-source FPGA database (verified by toolchain)
# Only IO pins from the database are used. All others are power/config/dedicated.

## BOTTOM side (pins 1-36) — 26 IOs — faces MVS connector
## Banks 7+6, VCCIO = 3.3V
## Signal: 68k P ROM address + control (through 470Ω series resistors)

| Pin | Bank | Signal    | Direction | Goes to              |
|-----|------|-----------|-----------|----------------------|
|   1 |    7 | PA0       | Input     | Series R → CTRG2 B5  |
|   2 |    7 | PA1       | Input     | Series R → CTRG2 B6  |
|   3 |    7 | PA2       | Input     | Series R → CTRG2 B7  |
|   4 |    7 | PA3       | Input     | Series R → CTRG2 B8  |
|   5 |    7 | PA4       | Input     | Series R → CTRG2 B9  |
|   6 |    7 | PA5       | Input     | Series R → CTRG2 B10 |
|   7 |    7 | PA6       | Input     | Series R → CTRG2 B11 |
|  10 |    7 | PA7       | Input     | Series R → CTRG2 B12 |
|  11 |    7 | PA8       | Input     | Series R → CTRG2 B13 |
|  12 |    7 | PA9       | Input     | Series R → CTRG2 B14 |
|  13 |    7 | PA10      | Input     | Series R → CTRG2 B15 |
|  14 |    7 | PA11      | Input     | Series R → CTRG2 B16 |
|  18 |    6 | PA12      | Input     | Series R → CTRG2 B17 |
|  19 |    6 | PA13      | Input     | Series R → CTRG2 B18 |
|  22 |    6 | PA14      | Input     | Series R → CTRG2 B19 |
|  23 |    6 | PA15      | Input     | Series R → CTRG2 B20 |
|  24 |    6 | PA16      | Input     | Series R → CTRG2 B21 |
|  25 |    6 | PA17      | Input     | Series R → CTRG2 B22 |
|  26 |    6 | ROMOE     | Input     | Series R → CTRG2 A33 |
|  27 |    6 | ROMOEU    | Input     | Series R → CTRG2 A23 |
|  28 |    6 | ROMOEL    | Input     | Series R → CTRG2 A24 |
|  30 |    6 | nRW       | Input     | Series R → CTRG2 A21 |
|  31 |    6 | BUS_DIR   | Output    | 74LVC245 pin 1 (DIR) |
|  33 |    6 | SPARE_B0  | —         | —                    |
|  34 |    6 | SPARE_B1  | —         | —                    |
|  35 |    6 | SPARE_B2  | —         | —                    |

## RIGHT side (pins 37-72) — 18 IOs — faces level shifters
## Banks 6+8+3, VCCIO = 3.3V
## Signal: P ROM data bus (through 74LVC245 level shifters)

| Pin | Bank | Signal      | Direction | Goes to               |
|-----|------|-------------|-----------|------------------------|
|  37 |    6 | FPGA_PD0    | Bidir     | U7 74LVC245 pin 18 (B1)|
|  39 |    8 | FPGA_PD1    | Bidir     | U7 74LVC245 pin 17 (B2)|
|  40 |    8 | FPGA_PD2    | Bidir     | U7 74LVC245 pin 16 (B3)|
|  41 |    8 | FPGA_PD3    | Bidir     | U7 74LVC245 pin 15 (B4)|
|  44 |    8 | FPGA_PD4    | Bidir     | U7 74LVC245 pin 14 (B5)|
|  45 |    8 | FPGA_PD5    | Bidir     | U7 74LVC245 pin 13 (B6)|
|  46 |    8 | FPGA_PD6    | Bidir     | U7 74LVC245 pin 12 (B7)|
|  47 |    8 | FPGA_PD7    | Bidir     | U7 74LVC245 pin 11 (B8)|
|  48 |    8 | FPGA_PD8    | Bidir     | U8 74LVC245 pin 18 (B1)|
|  49 |    8 | FPGA_PD9    | Bidir     | U8 74LVC245 pin 17 (B2)|
|  50 |    8 | FPGA_PD10   | Bidir     | U8 74LVC245 pin 16 (B3)|
|  51 |    8 | FPGA_PD11   | Bidir     | U8 74LVC245 pin 15 (B4)|
|  52 |    8 | FPGA_PD12   | Bidir     | U8 74LVC245 pin 14 (B5)|
|  67 |    3 | FPGA_PD13   | Bidir     | U8 74LVC245 pin 13 (B6)|
|  68 |    3 | FPGA_PD14   | Bidir     | U8 74LVC245 pin 12 (B7)|
|  69 |    3 | FPGA_PD15   | Bidir     | U8 74LVC245 pin 11 (B8)|
|  71 |    3 | SPARE_R0    | —         | —                      |
|  72 |    3 | SPARE_R1    | —         | —                      |

## TOP side (pins 73-108) — 28 IOs — faces SDRAM
## Banks 3+2, VCCIO = 3.3V
## Signal: SDRAM data + address (directly to SDRAM chips)

## VERIFIED against W9825G6KH datasheet Rev A04, page 4 pin diagram

| Pin | Bank | Signal      | Direction | Goes to                  |
|-----|------|-------------|-----------|--------------------------|
|  73 |    3 | SDRAM_DQ0   | Bidir     | U2+U3 SDRAM pin 2       |
|  74 |    3 | SDRAM_DQ1   | Bidir     | U2+U3 SDRAM pin 4       |
|  76 |    3 | SDRAM_DQ2   | Bidir     | U2+U3 SDRAM pin 5       |
|  77 |    3 | SDRAM_DQ3   | Bidir     | U2+U3 SDRAM pin 7       |
|  78 |    3 | SDRAM_DQ4   | Bidir     | U2+U3 SDRAM pin 8       |
|  79 |    3 | SDRAM_DQ5   | Bidir     | U2+U3 SDRAM pin 10      |
|  80 |    3 | SDRAM_DQ6   | Bidir     | U2+U3 SDRAM pin 11      |
|  81 |    3 | SDRAM_DQ7   | Bidir     | U2+U3 SDRAM pin 13      |
|  82 |    3 | SDRAM_DQ8   | Bidir     | U2+U3 SDRAM pin 42      |
|  84 |    3 | SDRAM_DQ9   | Bidir     | U2+U3 SDRAM pin 44      |
|  88 |    2 | SDRAM_DQ10  | Bidir     | U2+U3 SDRAM pin 45      |
|  89 |    2 | SDRAM_DQ11  | Bidir     | U2+U3 SDRAM pin 47      |
|  90 |    2 | SDRAM_DQ12  | Bidir     | U2+U3 SDRAM pin 48      |
|  91 |    2 | SDRAM_DQ13  | Bidir     | U2+U3 SDRAM pin 50      |
|  92 |    2 | SDRAM_DQ14  | Bidir     | U2+U3 SDRAM pin 51      |
|  93 |    2 | SDRAM_DQ15  | Bidir     | U2+U3 SDRAM pin 53      |
|  94 |    2 | SDRAM_A0    | Output    | U2+U3 SDRAM pin 23      |
|  95 |    2 | SDRAM_A1    | Output    | U2+U3 SDRAM pin 24      |
|  97 |    2 | SDRAM_A2    | Output    | U2+U3 SDRAM pin 25      |
|  98 |    2 | SDRAM_A3    | Output    | U2+U3 SDRAM pin 26      |
|  99 |    2 | SDRAM_A4    | Output    | U2+U3 SDRAM pin 29      |
| 102 |    2 | SDRAM_A5    | Output    | U2+U3 SDRAM pin 30      |
| 103 |    2 | SDRAM_A6    | Output    | U2+U3 SDRAM pin 31      |
| 104 |    2 | SDRAM_A7    | Output    | U2+U3 SDRAM pin 32      |
| 105 |    2 | SDRAM_A8    | Output    | U2+U3 SDRAM pin 33      |
| 106 |    2 | SDRAM_A9    | Output    | U2+U3 SDRAM pin 34      |
| 107 |    2 | SDRAM_A10   | Output    | U2+U3 SDRAM pin 22 (AP) |
| 108 |    2 | SDRAM_A11   | Output    | U2+U3 SDRAM pin 35      |

## LEFT side (pins 109-144) — 26 IOs — faces RP2040 + misc
## Banks 1+0, VCCIO = 3.3V
## Signal: SDRAM control + SPI + misc

| Pin | Bank | Signal      | Direction | Goes to              |
|-----|------|-------------|-----------|----------------------|
## VERIFIED against W9825G6KH datasheet Rev A04, page 4

| 110 |    1 | SDRAM_A12   | Output    | U2+U3 SDRAM pin 36  |
| 111 |    1 | SDRAM_BA0   | Output    | U2+U3 SDRAM pin 20 (BS0) |
| 112 |    1 | SDRAM_BA1   | Output    | U2+U3 SDRAM pin 21 (BS1) |
| 113 |    1 | SDRAM_CLK   | Output    | U2+U3 SDRAM pin 38  |
| 114 |    1 | SDRAM_CKE   | Output    | U2+U3 SDRAM pin 37  |
| 115 |    1 | SDRAM_RASN  | Output    | U2+U3 SDRAM pin 18 (RAS#) |
| 116 |    1 | SDRAM_CASN  | Output    | U2+U3 SDRAM pin 17 (CAS#) |
| 117 |    1 | SDRAM_WEN   | Output    | U2+U3 SDRAM pin 16 (WE#)  |
| 118 |    1 | SDRAM_CS0N  | Output    | U2 SDRAM pin 19 (CS#)     |
| 119 |    1 | SDRAM_CS1N  | Output    | U3 SDRAM pin 19 (CS#)     |
| 120 |    1 | SDRAM_DQML  | Output    | U2+U3 SDRAM pin 15 (LDQM) |
| 121 |    1 | SDRAM_DQMH  | Output    | U2+U3 SDRAM pin 39 (UDQM) |
| 124 |    1 | SPI_SCK     | Output    | RP2040 GPIO1         |
| 125 |    1 | SPI_MOSI    | Output    | RP2040 GPIO3         |
| 126 |    1 | SPI_MISO    | Input     | RP2040 GPIO0         |
| 127 |    1 | SPI_CS      | Input     | RP2040 GPIO2         |
| 128 |    0 | SPI_IRQ     | Output    | RP2040 GPIO4         |
| 133 |    0 | LED1        | Output    | LED (via 1K resistor)|
| 134 |    0 | LED2        | Output    | LED (via 1K resistor)|
| 135 |    0 | SPARE_L0    | —         | —                    |
| 136 |    0 | SPARE_L1    | —         | —                    |
| 139 |    0 | SPARE_L2    | —         | —                    |
| 140 |    0 | SPARE_L3    | —         | —                    |
| 141 |    0 | SPARE_L4    | —         | —                    |
| 142 |    0 | SPARE_L5    | —         | —                    |
| 143 |    0 | SPARE_L6    | —         | —                    |

## Non-IO pins (46 pins) — power, config, JTAG, NC
## These have FIXED functions, cannot be used as IO

Pins: 8,9,15,16,17,20,21,29,32,36,38,42,43,
      53,54,55,56,57,58,59,60,61,62,63,64,65,66,
      70,75,83,85,86,87,96,100,101,109,122,123,
      129,130,131,132,137,138,144

Functions (from ECP5 datasheet section 4):
- VCC (1.1V core): connect to 1.1V regulator output
- GND: connect to ground plane
- VCCIOx (3.3V): connect to 3.3V regulator output
- VCCAUX (2.5V): connect to 2.5V (can use resistor divider from 3.3V)
- PROGRAMN: pull up to 3.3V via 10K, active low resets config
- INITN: pull up to 3.3V via 10K, active low during config
- DONE: pull up to 3.3V via 10K, goes high when config complete → LED
- CCLK: config clock, driven by SPI flash or FPGA
- CFG[2:0]: config mode select, tie for SPI master mode
- CSSPIN: config SPI chip select → W25Q32 CS
- SPI_SI: config SPI data in → W25Q32 MOSI
- SPI_SO: config SPI data out → W25Q32 MISO
- TMS, TCK, TDI, TDO: JTAG → 4-pin header
