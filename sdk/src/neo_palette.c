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

/* The backdrop is the last word of palette RAM ($401FFE, palette 255
 * colour 15), shown wherever no sprite or fix pixel is opaque. */
void PAL_setBackdrop(uint16_t color) {
    PALRAM[255 * COLORS_PER_PAL + 15] = color;
}
