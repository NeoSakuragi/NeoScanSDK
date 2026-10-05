/* Game save data, the SNK conventions (sdk/src/neo_backup.c).
 *
 * MVS (arcade): the cartridge header names a block of work RAM ($10E: pointer, $112: size; crt0 fills them from the
 * linker's .backup section). The BIOS keeps that block in the board's battery RAM ($D00000, one area per game NGH),
 * restores it into work RAM before the game runs, and USER request 0 (crt0 do_init) asks the game to initialise it the
 * first time. The game just reads and writes the variables. Its first two bytes are the debug dipswitches (SNK; the
 * Unibios debug-dip menu edits them): declare them first (NEO_BACKUP_DIPS).
 *
 * AES (home): no battery RAM. The game saves to the memory card through the BIOS CARD call ($C00468): command, buffer,
 * size, the game's FCB (its NGH number, header $108) and a sub number (save 0-15); the BIOS answers in
 * BIOS_CARD_ANSWER. CARD_ERROR ($C0046E) shows the BIOS's own message for an error answer.
 *
 * BIOS_MVS_FLAG (BIOS RAM $10FD82): 0 = AES, else MVS (measured with the Unibios 4.0 in our emulator: $80 in its MVS
 * mode, 0 in its AES mode). */
#ifndef NEO_BACKUP_H
#define NEO_BACKUP_H
#include "neo_types.h"

#define NEO_BACKUP __attribute__((section(".backup")))
#define BIOS_MVS_FLAG      (*(volatile uint8_t *)0x10FD82)   /* 0 = AES, else MVS (Unibios: $80, its hardware mode) */
static inline uint16_t CART_NGH(void) {        /* the game's NGH number (header $108) = its card FCB */
    uint16_t v; __asm__ volatile ("move.w 0x108, %0" : "=d"(v)); return v;   /* (a C pointer to 0 trips -Warray-bounds) */
}

/* BIOS CARD call parameters (BIOS RAM) */
#define BIOS_CARD_COMMAND  (*(volatile uint8_t  *)0x10FDC4)
#define BIOS_CARD_MODE     (*(volatile uint8_t  *)0x10FDC5)
#define BIOS_CARD_ANSWER   (*(volatile uint8_t  *)0x10FDC6)
#define BIOS_CARD_START    (*(volatile uint32_t *)0x10FDC8)
#define BIOS_CARD_SIZE     (*(volatile uint16_t *)0x10FDCC)
#define BIOS_CARD_FCB      (*(volatile uint16_t *)0x10FDCE)
#define BIOS_CARD_SUB      (*(volatile uint16_t *)0x10FDD0)
enum { CARD_FORMAT, CARD_SEARCH, CARD_LOAD, CARD_SAVE, CARD_DELETE, CARD_TITLE, CARD_USER_SAVE, CARD_USER_LOAD };
enum { CARD_OK = 0x00, CARD_NONE = 0x80, CARD_UNFORMATTED = 0x81, CARD_NO_DATA = 0x82, CARD_FAT_ERROR = 0x83,
       CARD_FULL = 0x84, CARD_WRITE_PROTECT = 0x85 };

/* one BIOS CARD command on this game's data (FCB = CART_NGH()); returns BIOS_CARD_ANSWER */
uint8_t CARD_call(uint8_t command, void *buf, uint16_t size, uint16_t sub);
void    CARD_error(void);                     /* the BIOS's message for the last answer (CARD_ERROR) */

#endif
