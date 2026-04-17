#ifndef NEO_TYPES_H
#define NEO_TYPES_H

#include <stdint.h>

typedef uint8_t neo_bool;
#define NEO_TRUE  1
#define NEO_FALSE 0

#define NEO_MAX_SPRITES       381
#define NEO_MAX_PALETTES      256
#define NEO_COLORS_PER_PAL    16
#define NEO_SCREEN_WIDTH      320
#define NEO_SCREEN_HEIGHT     224
#define NEO_MAX_SPRITE_HEIGHT 33

#define NEO_CMD_BUF_SIZE      512

/*
 * Neo Geo 16-bit color format (scattered RGB5 + dark bit):
 *   Bit 15:    Dark bit
 *   Bit 14:    Red LSB
 *   Bit 13:    Green LSB
 *   Bit 12:    Blue LSB
 *   Bits 11-8: Red[4:1]
 *   Bits 7-4:  Green[4:1]
 *   Bits 3-0:  Blue[4:1]
 */
#define NEO_RGB(r5, g5, b5) \
    ((uint16_t)( \
        (((r5) & 1) << 14) | (((r5) >> 1) << 8) | \
        (((g5) & 1) << 13) | (((g5) >> 1) << 4) | \
        (((b5) & 1) << 12) | (((b5) >> 1) << 0)))

#define NEO_RGB8(r8, g8, b8) \
    NEO_RGB((r8) >> 3, (g8) >> 3, (b8) >> 3)

#define NEO_RGB_DARK(r5, g5, b5) \
    (NEO_RGB(r5, g5, b5) | 0x8000)

#define NEO_COLOR_BLACK   0x0000
#define NEO_COLOR_WHITE   NEO_RGB(31, 31, 31)
#define NEO_COLOR_RED     NEO_RGB(31, 0, 0)
#define NEO_COLOR_GREEN   NEO_RGB(0, 31, 0)
#define NEO_COLOR_BLUE    NEO_RGB(0, 0, 31)

typedef struct {
    uint16_t addr;
    uint16_t data;
} neo_vram_cmd_t;

#endif
