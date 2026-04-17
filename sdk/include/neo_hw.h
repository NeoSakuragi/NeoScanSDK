#ifndef NEO_HW_H
#define NEO_HW_H

#include "neo_types.h"

/* Hardware registers (memory-mapped) */
#define REG_VRAMADDR   (*(volatile uint16_t *)0x3C0000)
#define REG_VRAMRW     (*(volatile uint16_t *)0x3C0002)
#define REG_VRAMMOD    (*(volatile uint16_t *)0x3C0004)
#define REG_IRQACK     (*(volatile uint16_t *)0x3C000C)
#define REG_WATCHDOG   (*(volatile uint8_t  *)0x300001)
#define REG_SOUND      (*(volatile uint8_t  *)0x320000)

/* Palette RAM: 256 palettes x 16 colors x 2 bytes = 8KB */
#define PALRAM         ((volatile uint16_t *)0x400000)

/* BIOS variables in work RAM */
#define BIOS_SYSTEM_MODE   (*(volatile uint8_t *)0x10FD80)
#define BIOS_USER_REQUEST  (*(volatile uint8_t *)0x10FDAE)
#define BIOS_USER_MODE     (*(volatile uint8_t *)0x10FDAF)
#define BIOS_P1CURRENT     (*(volatile uint8_t *)0x10FD96)
#define BIOS_P1CHANGE      (*(volatile uint8_t *)0x10FD97)
#define BIOS_P2CURRENT     (*(volatile uint8_t *)0x10FD98)
#define BIOS_P2CHANGE      (*(volatile uint8_t *)0x10FD99)
#define BIOS_STATCURNT     (*(volatile uint8_t *)0x10FDAC)
#define BIOS_STATCHANGE    (*(volatile uint8_t *)0x10FDAD)

/* Input bit masks */
#define INPUT_UP     (1 << 0)
#define INPUT_DOWN   (1 << 1)
#define INPUT_LEFT   (1 << 2)
#define INPUT_RIGHT  (1 << 3)
#define INPUT_A      (1 << 4)
#define INPUT_B      (1 << 5)
#define INPUT_C      (1 << 6)
#define INPUT_D      (1 << 7)

/* Start/Select/Coin (from BIOS_STATCURNT/STATCHANGE) */
#define INPUT_START  (1 << 0)
#define INPUT_SELECT (1 << 1)

/* BIOS call addresses */
#define BIOS_SYSTEM_INT1   0xC00438
#define BIOS_SYSTEM_RETURN 0xC00444
#define BIOS_SYSTEM_IO     0xC0044A
#define BIOS_FIX_CLEAR     0xC004C2
#define BIOS_LSP_1ST       0xC004C8

/* VRAM address bases for sprite control blocks */
#define VRAM_SCB1  0x0000
#define VRAM_SCB2  0x8000
#define VRAM_SCB3  0x8200
#define VRAM_SCB4  0x8400

/* Inline VRAM access */
static inline void VDP_write(uint16_t addr, uint16_t data) {
    REG_VRAMADDR = addr;
    REG_VRAMRW = data;
}

static inline uint16_t VDP_read(uint16_t addr) {
    REG_VRAMADDR = addr;
    return REG_VRAMRW;
}

static inline void SYS_kickWatchdog(void) {
    REG_WATCHDOG = 0;
}

#endif
