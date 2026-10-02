# P board v1 — bring-up checklist

Order: each step only needs the previous one. Stop at the first failing step and measure; every 3.3 V control copy has a test point.

## 0. Before power
- Visual: TSOP-48 pin 1 dots toward the flash's WE#/RESET# side (pins 11/12), QFN-80 pin 1 corner, diode bands (cathode toward P5V).
- Ohmmeter: P5V to GND, P3V3 to GND, VDD_CORE to GND — none shorted. Slot VCC pin to P5V through D1: ~0.3 V drop, not 0 Ω.

## 1. USB only, no MVS, MODE jumper on PROG
- LED1 (3.3 V) on. VDD_CORE test point 1.1 V ± 0.1 (RP2350 regulator running). 
- Hold BOOTSEL, tap RUN: a mass-storage drive appears; copy `firmware/build/pboard_prog.uf2`.
- `python3 pboard_flash.py info`: version 1, prog_mode 1, vbus 1, three flash IDs = manufacturer 0x01, device 0x227E (S29GL064N).
  No ID on one group = that group's 595 chain, /OE or data GPIOs. All three missing = 595 chain (SR_DATA/CLK/LATCH) or nPROG_MODE.

## 2. Flash KOF96
- `python3 pboard_flash.py image /data/roms/kof96.neo out/kof96_images` — P.bin starts 10 00 00 F3 C0 00 02 04.
- `python3 pboard_flash.py flash /data/roms/kof96.neo` — erases, writes and verifies P, VA, VB (several minutes).
- `python3 pboard_flash.py verify /data/roms/kof96.neo` after a power cycle: same result = retention fine.

## 3. In the MVS with the KOF96 CHA board, MODE jumper on PLAY (or removed)
- Expect: BIOS then the KOF96 attract mode. Crosshatch or freeze at boot = P path (probe nROMOE_3, nP_OE, nXCVR_EN test points with the scope while the BIOS polls the cart).
- Game runs but crashes entering a fight or a menu = bank latch (probe BANK0/BANK1 and P2 during play; a P2 read must show FA21 high).
- Sound effects and drums missing but music present = ADPCM section (probe RMPX_3, VA_ADR23 and nVA_BUFOE while a sample should play). Noise instead of silence = demux bit order.
- Works on a 1-slot board but not a multi-slot board = expected in v1 (no slot-select gating).

## 4. Then
- Our own ROM (`examples/danmaku`): image it, flash it, play it. The P image builder handles any P up to 5 MB.
