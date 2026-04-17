#ifndef NEO_PALETTE_H
#define NEO_PALETTE_H

#include "neo_types.h"

void neo_palette_set(uint16_t slot, const uint16_t colors[16]);
void neo_palette_set_color(uint16_t slot, uint8_t index, uint16_t color);
void neo_palette_set_backdrop(uint16_t color);

#endif
