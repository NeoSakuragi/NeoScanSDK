#include "neo_hw.h"
#include "neo_palette.h"

void neo_palette_set(uint16_t slot, const uint16_t colors[16]) {
    volatile uint16_t *base = &PALRAM[slot * NEO_COLORS_PER_PAL];
    uint8_t i;
    for (i = 0; i < NEO_COLORS_PER_PAL; i++)
        base[i] = colors[i];
}

void neo_palette_set_color(uint16_t slot, uint8_t index, uint16_t color) {
    PALRAM[slot * NEO_COLORS_PER_PAL + index] = color;
}

void neo_palette_set_backdrop(uint16_t color) {
    PALRAM[0] = color;
}
