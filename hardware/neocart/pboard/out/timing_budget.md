# P board v1 — timing budget (2026-09-26)

All chip numbers are datasheet maxima at 3.3 V (5 V for the AHCT/HCT parts) from `datasheets/`. The 68000 numbers are the
12.5 MHz column of the MC68000 spec **from memory** (marked ⚠); the neogeodev wiki gives the clock (12 MHz) and the wait-cycle
table but no nanoseconds. Clock period 83.3 ns, half-state 41.7 ns, a read cycle S0–S7 = 333 ns.

| part | parameter | value |
|---|---|---|
| S29GL064N-90 | tACC address→data, tCE, tOE, tDF (OE↑→Hi-Z), tOH | 90, 90, 25, 20, 0 ns |
| SN74LVC16244A | tpd, ten, tdis | 5.2, 8.0, 10.8 ns |
| SN74LVC16245A | tpd, ten, tdis | 5.7, 9.9, 13.9 ns |
| SN74LVC08A / 04A | tpd | 4.1 / 5.5 ns |
| 74LVC16374A | tsu, th, CLK→Q | 2.4, 1.9, 6.5 ns |
| SN74AHC273 (3.3 V) | tsu, th, CLK→Q | 5.5, 1.0, 19.5 ns |
| SN74AHCT245 (5 V) | tpd, ten | 11, 11 ns |
| SN74HCT32 (5 V) | tpd | ≤ 25 ns class |
| MC68000 12 MHz ⚠ | address valid after S0, data-in setup before the S6/S7 edge, data-out hold after DS↑ | ≤ 71.7 ns (S1 + 30), 10 ns, spec min 0 ns / real parts hold to the next S1 (~40 ns) |

## 1. P-ROM read (P1 and P2), the only path with a hard deadline
Data must be at the 68K 10 ns before the S6/S7 clock edge = 281.7 ns after S0.

Address path (does not wait for /ROMOE): 68K address valid ≤ 71.7 → U7/U8 16244 5.2 → flash tACC 90 → U6 16245 5.7 →
**data at 172.6 ns. Margin 109 ns.**

Output-enable path: /ROMOE from NEO-C1, assumed ≤ 143 ns after S0 (S2 + 30 ns strobe + 30 ns decode ⚠) → U8 5.2 →
LVC08 nP_OE_SRC 4.1 → U8 group 4 5.2 → flash tOE 25 → U6 5.7 → **data at 188 ns. Margin 93 ns.**
Transceiver enable on the same trigger: 5.2 + 4.1 (nPORTOE) + 4.1 (nXCVR_EN_SRC) + 5.2 + ten 9.9 = 28.5 ns after /ROMOE,
before the flash data exists (39.5 ns). Nothing is lost.

Release: /ROMOE↑ → flash Hi-Z at 14.5 + 20 = 34.5 ns, transceiver off at 18.6 + 13.9 = 32.5 ns. The next device on the
bus (BIOS, work RAM) is not enabled before its own S2, ≥ 4 clocks later. No overlap.

ROMWAIT and PWAIT0/1 are tied high = full speed. From the neogeodev "Wait cycle" page: ROMWAIT=0 adds 1 cycle in the ROM zone;
PWAIT1/PWAIT0 = 1/0 adds 1, 0/1 adds 2, and 0/0 makes the PORT zone wait **as long as PDTACK is high** — a real handshake exists
there (relevant for the FPGA cart, not for v1).

## 2. Bank write (SN74AHC273 clocked by the end of /PORTWEL)
Setup: the 68K drives data from S3, /PORTWEL rises at S7 → data has been through U6 (5.7) for ≥ 150 ns before the clock;
needs 5.5. Fine.
Hold: clock path 1.0–5.2 ns (U8), data path 1.0–5.7 ns (U6), th 1.0 → the 68K must hold data ≥ 5.2 ns after /PORTWEL rises.
Spec minimum for data-out hold after DS↑ is 0 ns ⚠; real 68000s hold until the next S1 (~40 ns). SNK's own carts latch with a
74LS74 on the same strobe (neogeodev PROGBK1: "Bankswitching is done with the LS74") and need 5 ns hold, so the dependence
is the same as the original hardware's. The transceiver is switched off ~32 ns after the edge, well after the latch clocked.
Bank → flash address: BANK CLK→Q 19.5 + LVC08 4.1 + U8 5.2 = 29 ns; the next P2 fetch is ≥ 333 ns away.

## 3. ADPCM address capture (74LVC16374A on SDRMPX / SDPMPX)
Clock path: MPX → U8 16244 (1.0–5.2 ns) for the rising register; + LVC04 (0.5–5.5) = 1.5–10.7 ns for the falling register.
Data path: SDRAD/SDRA straight into the register (0 ns).
Required from the YM2610: address bits valid ≥ 2.4 − 1.0 = 1.4 ns before the MPX edge; held ≥ 5.2 + 1.9 = 7.1 ns after
the rising edge and ≥ 10.7 + 1.9 = 12.6 ns after the falling edge. The wiki does not give the YM2610's hold. SNK PROG boards
capture the same lines with 74LS373/LS374 behind an LS inverter (10–20 ns) and LS374 hold 0 ns, so the YM2610 holds for at
least that much ⚠ (my recollection of the SNK topology, not re-verified). This is the one number a scope on the KOF96 cart should
confirm: SDRAD hold after each SDRMPX edge.
Data return: latch CLK→Q 6.5 + tACC 90 + AHCT245 11 = 108 ns from the falling edge; the enable path /SDROE → HCT32 ≤ 25 →
AHCT245 ten 11 = 36 ns. ADPCM-B cycles are 1.5 µs, ADPCM-A 9 µs (neogeodev "YM2610 ADPCM bus"). Margin ≥ 1 µs.

## 4. Programming path (RP2350 through 74HC595 chains)
No deadlines: the firmware clocks the chains at a few MHz and respects the flash's tWP/tWPH and write-buffer timings with
software delays. HC595 at 3.3 V: SHCP max 24 MHz worst case; the firmware uses far less.

## Verdict
Both 68K paths close with ~100 ns of margin against conservative assumptions. The bank latch and the ADPCM registers rely on the
same hold behaviour as SNK's LS-logic boards, with slightly tighter numbers (5 ns vs LS74's 5 ns; 12.6 ns vs an LS inverter's
delay). The only measurement worth taking before trusting the ADPCM section blindly is SDRAD hold after SDRMPX on a real cart.
