#ifndef NEO_BANK_H
#define NEO_BANK_H

#include "neo_types.h"

/* P ROM bank switching: the P2 window ($200000-$2FFFFF) shows P ROM MB 1 + n after a word write of n to $2FFFF0 (SNK's
 * standard cart latch). Our emulator (Geolith geo_m68k.c, default board): any write at $2FFFF0-$2FFFFF, n masked to the
 * banks the P ROM has, bank 0 at reset. Our cart (NeoCart PROG v3, hardware/neocart/pboard): a 3-bit latch on D0-D2
 * clocked by /PORTWEL, banks 0-6, cleared by /RESET. The register is write-only: neo_bank is the bank mapped now.
 * Link: sections named .p2bankN (or .p2data = bank 0) sit at $200000, loaded at P ROM MB 1 + N (sdk/boot/neoscan.ld,
 * tools/neobuild.py). BANK_set returns the bank it replaced, so a reader puts it back (b = BANK_set(x); ...; BANK_set(b)):
 * nested readers never leave their caller looking at the wrong bank. The memory clobber keeps the compiler from moving
 * a load of banked data across the switch. Nothing in an interrupt may read the P2 window (the vblank handler does not). */
#define REG_P2BANK (*(volatile uint16_t *)0x2FFFF0)
extern uint8_t neo_bank;
static inline uint8_t BANK_set(uint8_t b) {
    uint8_t o = neo_bank;
    if (b != o) { neo_bank = b; REG_P2BANK = b; }
    __asm__ volatile ("" ::: "memory");
    return o;
}
static inline void BANK_init(void) { neo_bank = 0; REG_P2BANK = 0; __asm__ volatile ("" ::: "memory"); }   /* the register
                                                                    and its copy agree (the BIOS may have run in between) */

#endif
