#ifndef NEO_PALETTE_H
#define NEO_PALETTE_H

#include "neo_types.h"

void PAL_setPalette(uint16_t slot, const uint16_t colors[16]);
void PAL_setColor(uint16_t slot, uint8_t index, uint16_t color);
void PAL_setBackdrop(uint16_t color);

#endif
