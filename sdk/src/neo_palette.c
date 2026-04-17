#include "neo_hw.h"
#include "neo_palette.h"

void PAL_setPalette(uint16_t slot, const uint16_t colors[16]) {
    volatile uint16_t *base = &PALRAM[slot * COLORS_PER_PAL];
    uint8_t i;
    for (i = 0; i < COLORS_PER_PAL; i++)
        base[i] = colors[i];
}

void PAL_setColor(uint16_t slot, uint8_t index, uint16_t color) {
    PALRAM[slot * COLORS_PER_PAL + index] = color;
}

void PAL_setBackdrop(uint16_t color) {
    PALRAM[0] = color;
}
