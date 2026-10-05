/* SNK save conventions: see neo_backup.h. */
#include "neo_hw.h"
#include "neo_backup.h"

/* the BIOS call with every register saved (the BIOS routines use any of them) */
void neo_bios_call(uint32_t addr);
__asm__(
    "    .text\n"
    "    .align 2\n"
    "    .global neo_bios_call\n"
    "neo_bios_call:\n"
    "    move.l  4(%sp), %a0\n"
    "    movem.l %d2-%d7/%a2-%a6, -(%sp)\n"
    "    jsr     (%a0)\n"
    "    movem.l (%sp)+, %d2-%d7/%a2-%a6\n"
    "    rts\n");

uint8_t CARD_call(uint8_t command, void *buf, uint16_t size, uint16_t sub) {
    BIOS_CARD_COMMAND = command;
    BIOS_CARD_MODE = 0;
    BIOS_CARD_START = (uint32_t)buf;
    BIOS_CARD_SIZE = size;
    BIOS_CARD_FCB = CART_NGH();
    BIOS_CARD_SUB = sub;
    neo_bios_call(0xC00468);                                 /* CARD */
    return BIOS_CARD_ANSWER;
}
void CARD_error(void) { neo_bios_call(0xC0046E); }           /* CARD_ERROR */
