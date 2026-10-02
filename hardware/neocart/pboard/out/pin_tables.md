# P board v1 — pin tables for the datasheet read-back

Generated from design.py (nets) and lib/pboard.kicad_sym (symbol pin names). Column 4 = what the net does in this design.

## S29GL064N — U1, U2, U3, U4, U5 (64 Mbit NOR, 90 ns, x8/x16, bottom boot - P-ROM (16-bit); LCSC C117907; symbol S29GL064N90TFI040)

| pin | symbol name | U1 | U2 | U3 | U4 | U5 |
|---|---|---|---|---|---|---|
| 1 | A15 | FA15 | VA_ADR16 | VA_ADR16 | VB_ADR16 | VB_ADR16 |
| 2 | A14 | FA14 | VA_ADR15 | VA_ADR15 | VB_ADR15 | VB_ADR15 |
| 3 | A13 | FA13 | VA_ADR14 | VA_ADR14 | VB_ADR14 | VB_ADR14 |
| 4 | A12 | FA12 | VA_ADR13 | VA_ADR13 | VB_ADR13 | VB_ADR13 |
| 5 | A11 | FA11 | VA_ADR12 | VA_ADR12 | VB_ADR12 | VB_ADR12 |
| 6 | A10 | FA10 | VA_ADR11 | VA_ADR11 | VB_ADR11 | VB_ADR11 |
| 7 | A9 | FA9 | VA_ADR10 | VA_ADR10 | VB_ADR10 | VB_ADR10 |
| 8 | A8 | FA8 | VA_ADR9 | VA_ADR9 | VB_ADR9 | VB_ADR9 |
| 9 | A19 | FA19 | VA_ADR20 | VA_ADR20 | VB_ADR20 | VB_ADR20 |
| 10 | A20 | FA20 | VA_ADR21 | VA_ADR21 | VB_ADR21 | VB_ADR21 |
| 11 | ~{WE} | nP_WE | nVA_WE | nVA_WE | nVB_WE | nVB_WE |
| 12 | ~{RESET} | nFLASH_RST | nFLASH_RST | nFLASH_RST | nFLASH_RST | nFLASH_RST |
| 13 | A21 | FA21 | VA_ADR22 | VA_ADR22 | VB_ADR22 | VB_ADR22 |
| 14 | ~{WP}/ACC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 15 | RY/~{BY} | not connected | not connected | not connected | not connected | not connected |
| 16 | A18 | FA18 | VA_ADR19 | VA_ADR19 | VB_ADR19 | VB_ADR19 |
| 17 | A17 | FA17 | VA_ADR18 | VA_ADR18 | VB_ADR18 | VB_ADR18 |
| 18 | A7 | FA7 | VA_ADR8 | VA_ADR8 | VB_ADR8 | VB_ADR8 |
| 19 | A6 | FA6 | VA_ADR7 | VA_ADR7 | VB_ADR7 | VB_ADR7 |
| 20 | A5 | FA5 | VA_ADR6 | VA_ADR6 | VB_ADR6 | VB_ADR6 |
| 21 | A4 | FA4 | VA_ADR5 | VA_ADR5 | VB_ADR5 | VB_ADR5 |
| 22 | A3 | FA3 | VA_ADR4 | VA_ADR4 | VB_ADR4 | VB_ADR4 |
| 23 | A2 | FA2 | VA_ADR3 | VA_ADR3 | VB_ADR3 | VB_ADR3 |
| 24 | A1 | FA1 | VA_ADR2 | VA_ADR2 | VB_ADR2 | VB_ADR2 |
| 25 | A0 | FA0 | VA_ADR1 | VA_ADR1 | VB_ADR1 | VB_ADR1 |
| 26 | ~{CE} | ground | VA_ADR23 | nVA_ADR23 | VB_ADR23 | nVB_ADR23 |
| 27 | VSS | ground | ground | ground | ground | ground |
| 28 | ~{OE} | nP_OE | nVA_OE | nVA_OE | nVB_OE | nVB_OE |
| 29 | Q0 | FD0 | VA_DQ0 | VA_DQ0 | VB_DQ0 | VB_DQ0 |
| 30 | Q8 | FD8 | not connected | not connected | not connected | not connected |
| 31 | Q1 | FD1 | VA_DQ1 | VA_DQ1 | VB_DQ1 | VB_DQ1 |
| 32 | Q9 | FD9 | not connected | not connected | not connected | not connected |
| 33 | Q2 | FD2 | VA_DQ2 | VA_DQ2 | VB_DQ2 | VB_DQ2 |
| 34 | Q10 | FD10 | not connected | not connected | not connected | not connected |
| 35 | Q3 | FD3 | VA_DQ3 | VA_DQ3 | VB_DQ3 | VB_DQ3 |
| 36 | Q11 | FD11 | not connected | not connected | not connected | not connected |
| 37 | VCC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 38 | Q4 | FD4 | VA_DQ4 | VA_DQ4 | VB_DQ4 | VB_DQ4 |
| 39 | Q12 | FD12 | not connected | not connected | not connected | not connected |
| 40 | Q5 | FD5 | VA_DQ5 | VA_DQ5 | VB_DQ5 | VB_DQ5 |
| 41 | Q13 | FD13 | not connected | not connected | not connected | not connected |
| 42 | Q6 | FD6 | VA_DQ6 | VA_DQ6 | VB_DQ6 | VB_DQ6 |
| 43 | Q14 | FD14 | not connected | not connected | not connected | not connected |
| 44 | Q7 | FD7 | VA_DQ7 | VA_DQ7 | VB_DQ7 | VB_DQ7 |
| 45 | Q15/A-1 | FD15 | VA_ADR0 | VA_ADR0 | VB_ADR0 | VB_ADR0 |
| 46 | GND | ground | ground | ground | ground | ground |
| 47 | ~{BYTE} | supply P3V3 | ground | ground | ground | ground |
| 48 | A16 | FA16 | VA_ADR17 | VA_ADR17 | VB_ADR17 | VB_ADR17 |

## SN74LVC16245A — U6 (16-bit transceiver, 68K data bus; LCSC C7824; symbol SN74LVC16245ADGGR)

| pin | symbol name | U6 |
|---|---|---|
| 1 | 1DIR | RW |
| 2 | 1B1 | D0 |
| 3 | 1B2 | D1 |
| 4 | GND | ground |
| 5 | 1B3 | D2 |
| 6 | 1B4 | D3 |
| 7 | VCC | supply P3V3 |
| 8 | 1B5 | D4 |
| 9 | 1B6 | D5 |
| 10 | GND | ground |
| 11 | 1B7 | D6 |
| 12 | 1B8 | D7 |
| 13 | 2B1 | D8 |
| 14 | 2B2 | D9 |
| 15 | GND | ground |
| 16 | 2B3 | D10 |
| 17 | 2B4 | D11 |
| 18 | VCC | supply P3V3 |
| 19 | 2B5 | D12 |
| 20 | 2B6 | D13 |
| 21 | GND | ground |
| 22 | 2B7 | D14 |
| 23 | 2B8 | D15 |
| 24 | 2DIR | RW |
| 25 | ~{2OE} | nXCVR_EN |
| 26 | 2A8 | FD15 |
| 27 | 2A7 | FD14 |
| 28 | GND | ground |
| 29 | 2A6 | FD13 |
| 30 | 2A5 | FD12 |
| 31 | VCC | supply P3V3 |
| 32 | 2A4 | FD11 |
| 33 | 2A3 | FD10 |
| 34 | GND | ground |
| 35 | 2A2 | FD9 |
| 36 | 2A1 | FD8 |
| 37 | 1A8 | FD7 |
| 38 | 1A7 | FD6 |
| 39 | GND | ground |
| 40 | 1A6 | FD5 |
| 41 | 1A5 | FD4 |
| 42 | VCC | supply P3V3 |
| 43 | 1A4 | FD3 |
| 44 | 1A3 | FD2 |
| 45 | GND | ground |
| 46 | 1A2 | FD1 |
| 47 | 1A1 | FD0 |
| 48 | ~{1OE} | nXCVR_EN |

## SN74LVC16244A — U7, U8 (16-bit buffer, 68K A1-A16; LCSC C7822; symbol SN74LVC16244ADGGR)

| pin | symbol name | U7 | U8 |
|---|---|---|---|
| 1 | ~{1OE} | PROG_MODE | PROG_MODE |
| 2 | 1Y1 | FA0 | FA16 |
| 3 | 1Y2 | FA1 | FA17 |
| 4 | GND | ground | ground |
| 5 | 1Y3 | FA2 | FA18 |
| 6 | 1Y4 | FA3 | nROMOE_3 |
| 7 | VCC | supply P3V3 | supply P3V3 |
| 8 | 2Y1 | FA4 | nPORTOEL_3 |
| 9 | 2Y2 | FA5 | nPORTOEU_3 |
| 10 | GND | ground | ground |
| 11 | 2Y3 | FA6 | nPORTADRS_3 |
| 12 | 2Y4 | FA7 | nPORTWEL_3 |
| 13 | 3Y1 | FA8 | nRESET_3 |
| 14 | 3Y2 | FA9 | RMPX_3 |
| 15 | GND | ground | ground |
| 16 | 3Y3 | FA10 | PMPX_3 |
| 17 | 3Y4 | FA11 | FA21 |
| 18 | VCC | supply P3V3 | supply P3V3 |
| 19 | 4Y1 | FA12 | nP_OE |
| 20 | 4Y2 | FA13 | nXCVR_EN |
| 21 | GND | ground | ground |
| 22 | 4Y3 | FA14 | FA19 |
| 23 | 4Y4 | FA15 | FA20 |
| 24 | ~{4OE} | PROG_MODE | PROG_MODE |
| 25 | ~{3OE} | PROG_MODE | PROG_MODE |
| 26 | 4A4 | A16 | BANK1_G |
| 27 | 4A3 | A15 | BANK0_G |
| 28 | GND | ground | ground |
| 29 | 4A2 | A14 | nXCVR_EN_SRC |
| 30 | 4A1 | A13 | nP_OE_SRC |
| 31 | VCC | supply P3V3 | supply P3V3 |
| 32 | 3A4 | A12 | P2 |
| 33 | 3A3 | A11 | SDPMPX |
| 34 | GND | ground | ground |
| 35 | 3A2 | A10 | SDRMPX |
| 36 | 3A1 | A9 | nRESET |
| 37 | 2A4 | A8 | nPORTWEL |
| 38 | 2A3 | A7 | nPORTADRS |
| 39 | GND | ground | ground |
| 40 | 2A2 | A6 | nPORTOEU |
| 41 | 2A1 | A5 | nPORTOEL |
| 42 | VCC | supply P3V3 | supply P3V3 |
| 43 | 1A4 | A4 | nROMOE |
| 44 | 1A3 | A3 | A19 |
| 45 | GND | ground | ground |
| 46 | 1A2 | A2 | A18 |
| 47 | 1A1 | A1 | A17 |
| 48 | ~{2OE} | PROG_MODE | PROG_MODE |

## 74LVC16374A — U10, U11, U12, U13 (16-bit edge register - ADPCM-A address bits 0-9 (SDRMPX rising); LCSC C6074; symbol 74LVC16374ADGG,118)

| pin | symbol name | U10 | U11 | U12 | U13 |
|---|---|---|---|---|---|
| 1 | ~{1OE} | PROG_MODE | PROG_MODE | PROG_MODE | PROG_MODE |
| 2 | 1Q0 | VA_ADR0 | VA_ADR10 | VB_ADR0 | VB_ADR12 |
| 3 | 1Q1 | VA_ADR1 | VA_ADR11 | VB_ADR1 | VB_ADR13 |
| 4 | GND | ground | ground | ground | ground |
| 5 | 1Q2 | VA_ADR2 | VA_ADR12 | VB_ADR2 | VB_ADR14 |
| 6 | 1Q3 | VA_ADR3 | VA_ADR13 | VB_ADR3 | VB_ADR15 |
| 7 | VCC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 8 | 1Q4 | VA_ADR4 | VA_ADR14 | VB_ADR4 | VB_ADR16 |
| 9 | 1Q5 | VA_ADR5 | VA_ADR15 | VB_ADR5 | VB_ADR17 |
| 10 | GND | ground | ground | ground | ground |
| 11 | 1Q6 | VA_ADR6 | VA_ADR16 | VB_ADR6 | VB_ADR18 |
| 12 | 1Q7 | VA_ADR7 | VA_ADR17 | VB_ADR7 | VB_ADR19 |
| 13 | 2Q0 | VA_ADR8 | VA_ADR18 | VB_ADR8 | VB_ADR20 |
| 14 | 2Q1 | VA_ADR9 | VA_ADR19 | VB_ADR9 | VB_ADR21 |
| 15 | GND | ground | ground | ground | ground |
| 16 | 2Q2 | not connected | VA_ADR20 | VB_ADR10 | VB_ADR22 |
| 17 | 2Q3 | not connected | VA_ADR21 | VB_ADR11 | VB_ADR23 |
| 18 | VCC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 19 | 2Q4 | not connected | VA_ADR22 | not connected | not connected |
| 20 | 2Q5 | not connected | VA_ADR23 | not connected | not connected |
| 21 | GND | ground | ground | ground | ground |
| 22 | 2Q6 | not connected | not connected | not connected | not connected |
| 23 | 2Q7 | not connected | not connected | not connected | not connected |
| 24 | ~{2OE} | PROG_MODE | PROG_MODE | PROG_MODE | PROG_MODE |
| 25 | 2CP | RMPX_3 | nRMPX_3 | PMPX_3 | nPMPX_3 |
| 26 | 2D7 | ground | ground | ground | ground |
| 27 | 2D6 | ground | ground | ground | ground |
| 28 | GND | ground | ground | ground | ground |
| 29 | 2D5 | ground | SDRA23 | ground | ground |
| 30 | 2D4 | ground | SDRA22 | ground | ground |
| 31 | VCC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 32 | 2D3 | ground | SDRA21 | SDPA11 | SDPA11 |
| 33 | 2D2 | ground | SDRA20 | SDPA10 | SDPA10 |
| 34 | GND | ground | ground | ground | ground |
| 35 | 2D1 | SDRA9 | SDRA9 | SDPA9 | SDPA9 |
| 36 | 2D0 | SDRA8 | SDRA8 | SDPA8 | SDPA8 |
| 37 | 1D7 | SDRAD7 | SDRAD7 | SDPAD7 | SDPAD7 |
| 38 | 1D6 | SDRAD6 | SDRAD6 | SDPAD6 | SDPAD6 |
| 39 | GND | ground | ground | ground | ground |
| 40 | 1D5 | SDRAD5 | SDRAD5 | SDPAD5 | SDPAD5 |
| 41 | 1D4 | SDRAD4 | SDRAD4 | SDPAD4 | SDPAD4 |
| 42 | VCC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 43 | 1D3 | SDRAD3 | SDRAD3 | SDPAD3 | SDPAD3 |
| 44 | 1D2 | SDRAD2 | SDRAD2 | SDPAD2 | SDPAD2 |
| 45 | GND | ground | ground | ground | ground |
| 46 | 1D1 | SDRAD1 | SDRAD1 | SDPAD1 | SDPAD1 |
| 47 | 1D0 | SDRAD0 | SDRAD0 | SDPAD0 | SDPAD0 |
| 48 | 1CP | RMPX_3 | nRMPX_3 | PMPX_3 | nPMPX_3 |

## SN74AHC273 — U14 (P2 bank latch with clear (3.3 V); LCSC C2877489; symbol SN74AHC273DBR)

| pin | symbol name | U14 |
|---|---|---|
| 1 | ~{CLR} | nRESET_3 |
| 2 | 1Q | BANK0 |
| 3 | 1D | FD0 |
| 4 | 2D | FD1 |
| 5 | 2Q | BANK1 |
| 6 | 3Q | BANK2 |
| 7 | 3D | FD2 |
| 8 | 4D | ground |
| 9 | 4Q | not connected |
| 10 | GND | ground |
| 11 | CLK | nPORTWEL_3 |
| 12 | 5Q | not connected |
| 13 | 5D | ground |
| 14 | 6D | ground |
| 15 | 6Q | not connected |
| 16 | 7Q | not connected |
| 17 | 7D | ground |
| 18 | 8D | ground |
| 19 | 8Q | not connected |
| 20 | VCC | supply P3V3 |

## SN74LVC08A — U15, U16 (quad AND - OE/enable decode; LCSC C465737; symbol SN74LVC08APWR)

| pin | symbol name | U15 | U16 |
|---|---|---|---|
| 1 | 1A | nPORTOEL_3 | BANK1 |
| 2 | 1B | nPORTOEU_3 | P2 |
| 3 | 1Y | nPORTOE | BANK1_G |
| 4 | 2A | nROMOE_3 | ground |
| 5 | 2B | nPORTOE | ground |
| 6 | 2Y | nP_OE_SRC | not connected |
| 7 | GND | ground | ground |
| 8 | 3Y | nXCVR_EN_SRC | not connected |
| 9 | 3A | nP_OE_SRC | ground |
| 10 | 3B | nPORTWEL_3 | ground |
| 11 | 4Y | BANK0_G | not connected |
| 12 | 4A | BANK0 | ground |
| 13 | 4B | P2 | ground |
| 14 | VCC | supply P3V3 | supply P3V3 |

## SN74LVC04A — U17 (hex inverter; LCSC C352968; symbol SN74LVC04APWR)

| pin | symbol name | U17 |
|---|---|---|
| 1 | 1A | nPORTADRS_3 |
| 2 | 1Y | P2 |
| 3 | 2A | RMPX_3 |
| 4 | 2Y | nRMPX_3 |
| 5 | 3A | PMPX_3 |
| 6 | 3Y | nPMPX_3 |
| 7 | GND | ground |
| 8 | 4Y | nVA_ADR23 |
| 9 | 4A | VA_ADR23 |
| 10 | 5Y | nVB_ADR23 |
| 11 | 5A | VB_ADR23 |
| 12 | 6Y | nPROG_MODE |
| 13 | 6A | PROG_MODE |
| 14 | VCC | supply P3V3 |

## 74AHCT245 — U18, U19 (ADPCM-A data to 5 V bus; LCSC C173388; symbol 74AHCT245PW,118)

| pin | symbol name | U18 | U19 |
|---|---|---|---|
| 1 | DIR | supply P5V | supply P5V |
| 2 | A0 | VA_DQ0 | VB_DQ0 |
| 3 | A1 | VA_DQ1 | VB_DQ1 |
| 4 | A2 | VA_DQ2 | VB_DQ2 |
| 5 | A3 | VA_DQ3 | VB_DQ3 |
| 6 | A4 | VA_DQ4 | VB_DQ4 |
| 7 | A5 | VA_DQ5 | VB_DQ5 |
| 8 | A6 | VA_DQ6 | VB_DQ6 |
| 9 | A7 | VA_DQ7 | VB_DQ7 |
| 10 | GND | ground | ground |
| 11 | B7 | SDRAD7 | SDPAD7 |
| 12 | B6 | SDRAD6 | SDPAD6 |
| 13 | B5 | SDRAD5 | SDPAD5 |
| 14 | B4 | SDRAD4 | SDPAD4 |
| 15 | B3 | SDRAD3 | SDPAD3 |
| 16 | B2 | SDRAD2 | SDPAD2 |
| 17 | B1 | SDRAD1 | SDPAD1 |
| 18 | B0 | SDRAD0 | SDPAD0 |
| 19 | ~{OE} | nVA_BUFOE | nVB_BUFOE |
| 20 | VCC | supply P5V | supply P5V |

## SN74HCT32 — U20 (quad OR (5 V) - V data buffer enables; LCSC C132266; symbol SN74HCT32PWR)

| pin | symbol name | U20 |
|---|---|---|
| 1 | 1A | nSDROE |
| 2 | 1B | PROG_MODE |
| 3 | 1Y | nVA_BUFOE |
| 4 | 2A | nSDPOE |
| 5 | 2B | PROG_MODE |
| 6 | 2Y | nVB_BUFOE |
| 7 | GND | ground |
| 8 | 3Y | not connected |
| 9 | 3A | ground |
| 10 | 3B | ground |
| 11 | 4Y | not connected |
| 12 | 4A | ground |
| 13 | 4B | ground |
| 14 | VCC | supply P5V |

## 74HC595 — U21, U22, U23, U24, U25, U26, U27, U28, U29 (programmer address shift register #0 (P A0-7); LCSC C5948; symbol 74HC595PW,118)

| pin | symbol name | U21 | U22 | U23 | U24 | U25 | U26 | U27 | U28 | U29 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Q1 | FA1 | FA9 | FA17 | VA_ADR1 | VA_ADR9 | VA_ADR17 | VB_ADR1 | VB_ADR9 | VB_ADR17 |
| 2 | Q2 | FA2 | FA10 | FA18 | VA_ADR2 | VA_ADR10 | VA_ADR18 | VB_ADR2 | VB_ADR10 | VB_ADR18 |
| 3 | Q3 | FA3 | FA11 | FA19 | VA_ADR3 | VA_ADR11 | VA_ADR19 | VB_ADR3 | VB_ADR11 | VB_ADR19 |
| 4 | Q4 | FA4 | FA12 | FA20 | VA_ADR4 | VA_ADR12 | VA_ADR20 | VB_ADR4 | VB_ADR12 | VB_ADR20 |
| 5 | Q5 | FA5 | FA13 | FA21 | VA_ADR5 | VA_ADR13 | VA_ADR21 | VB_ADR5 | VB_ADR13 | VB_ADR21 |
| 6 | Q6 | FA6 | FA14 | not connected | VA_ADR6 | VA_ADR14 | VA_ADR22 | VB_ADR6 | VB_ADR14 | VB_ADR22 |
| 7 | Q7 | FA7 | FA15 | not connected | VA_ADR7 | VA_ADR15 | VA_ADR23 | VB_ADR7 | VB_ADR15 | VB_ADR23 |
| 8 | GND | ground | ground | ground | ground | ground | ground | ground | ground | ground |
| 9 | Q7S | SR_CHAIN1 | SR_CHAIN2 | SR_CHAIN3 | SR_CHAIN4 | SR_CHAIN5 | SR_CHAIN6 | SR_CHAIN7 | SR_CHAIN8 | not connected |
| 10 | ~{MR} | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |
| 11 | SHCP | SR_CLK | SR_CLK | SR_CLK | SR_CLK | SR_CLK | SR_CLK | SR_CLK | SR_CLK | SR_CLK |
| 12 | STCP | SR_LATCH | SR_LATCH | SR_LATCH | SR_LATCH | SR_LATCH | SR_LATCH | SR_LATCH | SR_LATCH | SR_LATCH |
| 13 | ~{OE} | nPROG_MODE | nPROG_MODE | nPROG_MODE | nPROG_MODE | nPROG_MODE | nPROG_MODE | nPROG_MODE | nPROG_MODE | nPROG_MODE |
| 14 | DS | SR_DATA | SR_CHAIN1 | SR_CHAIN2 | SR_CHAIN3 | SR_CHAIN4 | SR_CHAIN5 | SR_CHAIN6 | SR_CHAIN7 | SR_CHAIN8 |
| 15 | Q0 | FA0 | FA8 | FA16 | VA_ADR0 | VA_ADR8 | VA_ADR16 | VB_ADR0 | VB_ADR8 | VB_ADR16 |
| 16 | VCC | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 | supply P3V3 |

## RP2350B — U30 (USB programmer MCU, 48 GPIO; LCSC C42415655; symbol RP2350B_C42415655)

| pin | symbol name | U30 |
|---|---|---|
| 1 | GPIO4 | FD4 |
| 2 | GPIO5 | FD5 |
| 3 | GPIO6 | FD6 |
| 4 | GPIO7 | FD7 |
| 5 | IOVDD | supply P3V3 |
| 6 | GPIO8 | FD8 |
| 7 | GPIO9 | FD9 |
| 8 | GPIO10 | FD10 |
| 9 | GPIO11 | FD11 |
| 10 | DVDD | supply VDD_CORE |
| 11 | GPIO12 | FD12 |
| 12 | GPIO13 | FD13 |
| 13 | GPIO14 | FD14 |
| 14 | GPIO15 | FD15 |
| 15 | IOVDD | supply P3V3 |
| 16 | GPIO16 | VA_DQ0 |
| 17 | GPIO17 | VA_DQ1 |
| 18 | GPIO18 | VA_DQ2 |
| 19 | GPIO19 | VA_DQ3 |
| 20 | GPIO20 | VA_DQ4 |
| 21 | GPIO21 | VA_DQ5 |
| 22 | GPIO22 | VA_DQ6 |
| 23 | GPIO23 | VA_DQ7 |
| 24 | IOVDD | supply P3V3 |
| 25 | GPIO24 | VB_DQ0 |
| 26 | GPIO25 | VB_DQ1 |
| 27 | GPIO26 | VB_DQ2 |
| 28 | GPIO27 | VB_DQ3 |
| 29 | IOVDD | supply P3V3 |
| 30 | XIN | XIN |
| 31 | XOUT | XOUT |
| 32 | DVDD | supply VDD_CORE |
| 33 | SWCLK | SWCLK |
| 34 | SWDIO | SWDIO |
| 35 | RUN | RUN |
| 36 | GPIO28 | VB_DQ4 |
| 37 | GPIO29 | VB_DQ5 |
| 38 | GPIO30 | VB_DQ6 |
| 39 | GPIO31 | VB_DQ7 |
| 40 | GPIO32 | SR_DATA |
| 41 | IOVDD | supply P3V3 |
| 42 | GPIO33 | SR_CLK |
| 43 | GPIO34 | SR_LATCH |
| 44 | GPIO35 | nP_OE |
| 45 | GPIO36 | nP_WE |
| 46 | GPIO37 | nVA_OE |
| 47 | GPIO38 | nVA_WE |
| 48 | GPIO39 | nVB_OE |
| 49 | GPIO40_ADC0 | nVB_WE |
| 50 | IOVDD | supply P3V3 |
| 51 | DVDD | supply VDD_CORE |
| 52 | GPIO41_ADC1 | PROG_SENSE |
| 53 | GPIO42_ADC2 | VBUS_SENSE |
| 54 | GPIO43_ADC3 | LED_MCU |
| 55 | GPIO44_ADC4 | TP_GPIO44 |
| 56 | GPIO45_ADC5 | TP_GPIO45 |
| 57 | GPIO46_ADC6 | TP_GPIO46 |
| 58 | GPIO47_ADC7 | TP_GPIO47 |
| 59 | ADC_AVDD | supply P3V3 |
| 60 | IOVDD | supply P3V3 |
| 61 | VREG_AVDD | supply VREG_AVDD |
| 62 | VREG_PGND | ground |
| 63 | VREG_LX | supply VREG_LX |
| 64 | VREG_VIN | supply P3V3 |
| 65 | VREG_FB | supply VDD_CORE |
| 66 | USB_DM | USB_DM_MCU |
| 67 | USB_DP | USB_DP_MCU |
| 68 | USB_OTP_VDD | supply P3V3 |
| 69 | QSPI_IOVDD | supply P3V3 |
| 70 | QSPI_SD3 | QSPI_SD3 |
| 71 | QSPI_SCLK | QSPI_SCLK |
| 72 | QSPI_SD0 | QSPI_SD0 |
| 73 | QSPI_SD2 | QSPI_SD2 |
| 74 | QSPI_SD1 | QSPI_SD1 |
| 75 | QSPI_SS | QSPI_SS |
| 76 | IOVDD | supply P3V3 |
| 77 | GPIO0 | FD0 |
| 78 | GPIO1 | FD1 |
| 79 | GPIO2 | FD2 |
| 80 | GPIO3 | FD3 |
| 81 | GND | ground |

## W25Q32JV — U31 (MCU firmware QSPI flash; LCSC C179173; symbol W25Q32JVSSIQ_C179173)

| pin | symbol name | U31 |
|---|---|---|
| 1 | ~{CS} | QSPI_SS |
| 2 | DO(IO1) | QSPI_SD1 |
| 3 | WP#(IO2) | QSPI_SD2 |
| 4 | GND | ground |
| 5 | DI(IO0) | QSPI_SD0 |
| 6 | CLK | QSPI_SCLK |
| 7 | HOLD#orRESET#(IO3) | QSPI_SD3 |
| 8 | VCC | supply P3V3 |

## AMS1117-3.3 — U32 (3.3 V LDO, 1 A; LCSC C6186; symbol AMS1117-3.3)

| pin | symbol name | U32 |
|---|---|---|
| 1 | GND | ground |
| 2 | VOUT | supply P3V3 |
| 3 | VIN | supply P5V |
| 4 | VOUT | supply P3V3 |

## 12 MHz — Y1 (ABM8-272-T3, 10 pF, the RP2350 reference crystal; LCSC C20625731; symbol ABM8-272-T3_C20625731)

| pin | symbol name | Y1 |
|---|---|---|
| 1 | 1 | XIN |
| 2 | GND | ground |
| 3 | 3 | XOUT_R |
| 4 | GND | ground |

## USB-C — J3 (USB 2.0 receptacle, 16-pin; LCSC C165948; symbol TYPE-C-31-M-12)

| pin | symbol name | J3 |
|---|---|---|
| 1 | EH | ground |
| 2 | EH | ground |
| 3 | EH | ground |
| 4 | EH | ground |
| A5 | CC1 | CC1 |
| A6 | DP1 | USB_DP |
| A7 | DN1 | USB_DM |
| A8 | SBU1 | not connected |
| B5 | CC2 | CC2 |
| B6 | DP2 | USB_DP |
| B7 | DN2 | USB_DM |
| B8 | SBU2 | not connected |
| A4B9 | VBUS | supply VBUS |
| B4A9 | VBUS | supply VBUS |
| A1B12 | GND | ground |
| B1A12 | GND | ground |
