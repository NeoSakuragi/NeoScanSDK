#include "neo_hw.h"
#include "neo_input.h"

uint16_t _joy_cur[2];
uint16_t _joy_press[2];
uint16_t _joy_rel[2];

void JOY_update(void) {
    uint16_t p1, p2, prev;
    uint8_t stat = BIOS_STATCURNT;

    p1 = BIOS_P1CURRENT;
    if (stat & 0x01) p1 |= JOY_START;
    if (stat & 0x02) p1 |= JOY_SELECT;

    p2 = BIOS_P2CURRENT;
    if (stat & 0x04) p2 |= JOY_START;
    if (stat & 0x08) p2 |= JOY_SELECT;

    prev = _joy_cur[0];
    _joy_press[0] = p1 & ~prev;
    _joy_rel[0]   = ~p1 & prev;
    _joy_cur[0]   = p1;

    prev = _joy_cur[1];
    _joy_press[1] = p2 & ~prev;
    _joy_rel[1]   = ~p2 & prev;
    _joy_cur[1]   = p2;
}
