#ifndef NEO_TYPES_H
#define NEO_TYPES_H

#include <stdint.h>

typedef uint8_t neo_bool;
#define NEO_TRUE  1
#define NEO_FALSE 0

#define MAX_SPRITES       381
#define MAX_PALETTES      256
#define COLORS_PER_PAL    16
#define SCREEN_WIDTH      320
#define SCREEN_HEIGHT     224
#define MAX_SPRITE_HEIGHT 33

#define CMD_BUF_SIZE      512

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
#define RGB(r5, g5, b5) \
    ((uint16_t)( \
        (((r5) & 1) << 14) | (((r5) >> 1) << 8) | \
        (((g5) & 1) << 13) | (((g5) >> 1) << 4) | \
        (((b5) & 1) << 12) | (((b5) >> 1) << 0)))

#define RGB8(r8, g8, b8) \
    RGB((r8) >> 3, (g8) >> 3, (b8) >> 3)

#define RGB_DARK(r5, g5, b5) \
    (RGB(r5, g5, b5) | 0x8000)

#define COLOR_BLACK   0x0000
#define COLOR_WHITE   RGB(31, 31, 31)
#define COLOR_RED     RGB(31, 0, 0)
#define COLOR_GREEN   RGB(0, 31, 0)
#define COLOR_BLUE    RGB(0, 0, 31)

typedef struct {
    uint16_t addr;
    uint16_t data;
} vram_cmd_t;

#endif
