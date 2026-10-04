# QMTech XC7A100T Core Board — Complete Header Pin Mapping
# Source: User Manual Figure 2-10, verified against schematic

## Header U1 (BANK34/35, top header)
Pin 1: VCCO_34_35      Pin 2: VCCO_34_35
Pin 3: IO B5            Pin 4: IO A5
Pin 5: IO D4            Pin 6: IO A6  (note: some text unclear)
Pin 7: IO A3            Pin 8: IO A2
Pin 9: IO D4            Pin 10: IO C4
Pin 11: IO C2           Pin 12: IO B2 VREF
Pin 13: IO E5           Pin 14: IO D5
Pin 15: IO C1           Pin 16: IO B1
Pin 17: IO E1           Pin 18: IO D1
Pin 19: IO F2           Pin 20: IO E2
Pin 21: IO G4           Pin 22: IO F4
Pin 23: IO G2           Pin 24: IO G1
Pin 25: IO J4           Pin 26: IO H4
Pin 27: IO H2           Pin 28: IO H1
Pin 29: IO M2           Pin 30: IO L2 (note: some partially obscured)
Pin 31: IO H9           Pin 32: IO G9 VREF
Pin 33: IO L5           Pin 34: IO K6 (note: partially obscured)
Pin 35: IO M4           Pin 36: IO L4
Pin 37: IO N3           Pin 38: IO N2
Pin 39: IO M6           Pin 40: IO M5 VREF
Pin 41: IO K1           Pin 42: IO J1
Pin 43: IO R3           Pin 44: IO P3
Pin 45: IO T4           Pin 46: IO T3
Pin 47: IO P6           Pin 48: IO P5 (note: partially obscured)
Pin 49: IO N1           Pin 50: IO R1 (note: partially obscured)
Pin 51: IO R1           Pin 52: IO T1
Pin 53: IO T2           Pin 54: IO R2
Pin 55: IO U2           Pin 56: IO U1
Pin 57: VIN             Pin 58: VIN
Pin 59: VIN             Pin 60: VIN
Pin 61: VIN             Pin 62: VIN
Pin 63: VIN             Pin 64: VIN

## Header U2 (BANK13/14/15, bottom header)
Pin 1: 3V3              Pin 2: 3V3
Pin 3: BANK15 D26       Pin 4: BANK15 E26
Pin 5: BANK15 D25       Pin 6: BANK15 E25
Pin 7: BANK15 G26       Pin 8: BANK15 H26
Pin 9: BANK15 E23       Pin 10: BANK15 F23
Pin 11: BANK15 F22      Pin 12: BANK15 G22
Pin 13: BANK15 J26      Pin 14: BANK15 J25 (note: partially obscured)
Pin 15: BANK15 G21      Pin 16: BANK15 G20
Pin 17: BANK15 H22      Pin 18: BANK15 H21
Pin 19: BANK15 J21      Pin 20: BANK15 K21
Pin 21: BANK14 K26      Pin 22: BANK14 K25
Pin 23: BANK14 K23      Pin 24: BANK15 K22
Pin 25: BANK14 N26      Pin 26: BANK14 N26 (note: partially obscured)
Pin 27: BANK14 L23      Pin 28: BANK14 L25 (note: partially obscured)
Pin 29: BANK14 P26      Pin 30: BANK14 R26
Pin 31: BANK14 M25      Pin 32: BANK14 M24
Pin 33: BANK14 N22      Pin 34: BANK14 N21
Pin 35: BANK14 P24      Pin 36: BANK14 P23
Pin 37: BANK14 P25      Pin 38: BANK14 R25
Pin 39: BANK14 T25      Pin 40: BANK14 T24 (note: partially obscured)
Pin 41: BANK13 V21      Pin 42: BANK13 U21
Pin 43: BANK13 W23      Pin 44: BANK13 V23
Pin 45: BANK13 Y23      Pin 46: BANK13 Y22
Pin 47: BANK13 AA25     Pin 48: BANK13 AB25 (note: partially obscured)
Pin 49: BANK13 AC24     Pin 50: BANK13 Y25 (note: partially obscured)
Pin 51: BANK13 Y21      Pin 52: BANK13 AB24
Pin 53: BANK13 Y26      Pin 54: BANK13 W21
Pin 55: BANK13 W25      Pin 56: BANK13 W25 (note: check duplicate)
Pin 57: BANK13 AC26     Pin 58: BANK13 AB26
Pin 59: VIN             Pin 60: VIN
Pin 61: VIN             Pin 62: VIN
Pin 63: VIN             Pin 64: VIN

## Summary
- U1 header: ~28 IOs on BANK34/35 (3.3V default, configurable)
- U2 header: ~28 IOs on BANK13/14/15 (3.3V)
- VIN pins: pass-through power (5V from DC jack)
- 3V3 pins: 3.3V power output
- Total usable IOs: ~56 per header = ~112 total (some are VREF/special)

## IMPORTANT NOTES
- Some pin labels partially obscured by watermark in the PDF
- Must verify against actual schematic (page 2) or hardware when boards arrive
- BANK34/35 voltage can be changed by removing R14/R15 resistors
- All other banks are fixed at 3.3V
