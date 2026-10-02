# P board v1 — datasheet read-back of every pin (2026-09-26)

Method: `out/pin_tables.md` (pad → symbol pin name → net, generated from design.py and the LCSC symbols) read line by line
against the manufacturer PDFs in `datasheets/`. Verdict per chip type. "Verified" = every used pin's function matches its use.

| part | datasheet page read | verdict | notes |
|---|---|---|---|
| S29GL064N (U1–U5) | Infineon, Figure 1 pinout (read visually 2026-09-25) + Table 25 AC | verified | U1 word mode (BYTE#=VCC, DQ15 on pin 45); U2–U5 byte mode (BYTE#=GND, pin 45 = A-1 = VA/VB_ADR0, DQ8–14 left open as the datasheet allows); CE# of U1 grounded, of the V pairs = address bit 23 / its inverse; WP#/ACC at VCC = no boot-sector protection, normal programming; RESET# pulled up, RY/BY# open |
| SN74LVC16245A (U6) | TI pin configuration p.3 | verified | A side = flash/MCU (FD), B side = 68K bus (5 V tolerant); DIR = R/W (high = A→B = flash to CPU on reads); both OE = nXCVR_EN |
| SN74LVC16244A (U7, U8) | TI pin configuration p.3 | verified | U7 = A1–A16 → FA0–FA15; U8 = A17–A19, the six strobes, SDRMPX/SDPMPX, and the 3.3 V-domain enables/bank bits that only need tri-stating in programming mode; all OE = PROG_MODE |
| 74LVC16374A (U10–U13) | TI SN74LVC16374A p.3–4 (Nexperia part, same industry pinout) | verified | D↔Q pairs pin-by-pin; 1CLK/2CLK = MPX (rising register) or inverted MPX (falling register); unused D inputs grounded; OE = PROG_MODE |
| SN74AHC273 (U14) | TI p.3 | verified | 1D–3D = FD0–2 → 1Q–3Q = BANK0–2, unused D grounded; CLR = nRESET_3 (active low); CLK = nPORTWEL_3, rising edge = end of the byte write; the neogeodev PROGBK1 page confirms the mechanism: "any write to an odd address in 0x200000~0x2FFFFF sets the bank … done with the LS74" |
| SN74LVC08A (U15, U16), SN74LVC04A (U17) | TI standard quad/hex pinouts | verified | gate pin maps match AND_PINS / INV_PINS; unused inputs grounded |
| 74AHCT245 (U18, U19) | TI SN74AHCT245 p.3 | verified | A = flash data (3.3 V logic, TTL-threshold inputs), B = SDRAD/SDPAD (5 V swing), DIR tied high = A→B only, so the 245 can never drive 3.3 V nodes; OE = nSDROE/nSDPOE OR PROG_MODE; VCC = 5 V |
| SN74HCT32 (U20) | TI standard pinout | verified | 5 V part so the 5 V PROG_MODE and /SDROE levels are legal; unused inputs grounded |
| 74HC595 (U21–U29) | Nexperia p.4–5 | verified | DS/Q7S chain, SHCP/STCP from the MCU, OE = nPROG_MODE (outputs only in programming mode), MR tied high |
| RP2350B (U30) | Raspberry Pi datasheet Figure 3 QFN-80, p.16 | verified, all 80 pins | GPIO0–47 mapping, XIN/XOUT, SWD, RUN, QSPI_SS/SD0–3/SCLK, USB_DP/DM, VREG_VIN/AVDD/LX/PGND/FB, DVDD ×3, IOVDD ×7, ADC_AVDD, USB_OTP_VDD, QSPI_IOVDD, EP = GND. VREG_PGND (pin 62) is the pin the router had left open; it is now grounded |
| W25Q32JV (U31) | Winbond p.5 | verified | SOIC-8: CS, DO=IO1, WP=IO2, GND, DI=IO0, CLK, HOLD=IO3, VCC ↔ RP2350 QSPI_SS/SD1/SD2/SD0/SCLK/SD3 |
| AMS1117-3.3 (U32) | SOT-223 standard | verified | 1 GND, 2/tab VOUT = P3V3, 3 VIN = P5V |
| B5819W (D1, D2) | LCSC footprint + symbol | verified | footprint pad 1 carries the cathode band and the pin-1 dot; symbol pin 1 = "−" = cathode → P5V, pin 2 = "+" = anode ← VCC5 / VBUS; the OR-ing direction is right. Confirm the graphic in JLCPCB's placement preview before paying |
| USB-C (J3), Y1, L1, LEDs, switches, JP1/JP2 | LCSC symbols | verified | CC1/CC2 5.1 kΩ to GND (device Rd), 27 Ω in D+/D−, VBUS sense 10k/18k; JP1 = 5 V | PROG_MODE | GND so the jumper picks PROG or PLAY and 28 kΩ to GND defaults to PLAY; PROG_SENSE = PROG_MODE × 18/28 = 3.2 V max at the ADC pin |

Things the read-back changed or flagged
- Nothing in the netlist. Every pin matched.
- The 74LVC16374A numbers used in the timing budget are TI's; the part ordered is Nexperia's 74LVC16374ADGG (C6074). Same function and pinout; Nexperia's own limits are in `datasheets/` only via LCSC's PDF, not re-read.
- The V flashes have OE# pulled low permanently in play mode (10 kΩ to GND on nVA_OE/nVB_OE). Exactly one of each pair is chip-selected by bit 23 at any time; the 74AHCT245 gates the bus. Read current is therefore continuous (tens of mA per pair). Accepted for v1.
- Exhaustive driver enumeration (`sim_exhaustive.py`, 16,640 states = every combination of R/W, the five 68K strobes, /SDROE, /SDPOE, PROG_MODE and the six MCU enable lines): the only multi-driver state is flash vs transceiver on FD when /ROMOE is low during a write cycle, which NEO-C1 never produces (read strobes only exist while R/W is high). No physically reachable contention.
