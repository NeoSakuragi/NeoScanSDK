#include "neo_hw.h"
#include "neo_fix.h"

static void fix_write(uint8_t col, uint8_t row, uint16_t val) {
    uint16_t addr = VRAM_FIX + col * 32 + row;
    uint16_t sr;
    __asm__ volatile ("move.w %%sr, %0" : "=d"(sr));
    __asm__ volatile ("move.w #0x2700, %%sr" ::: "cc", "memory");
    REG_VRAMADDR = addr;
    REG_VRAMRW = val;
    __asm__ volatile ("move.w %0, %%sr" :: "d"(sr) : "cc", "memory");
}

void FIX_clear(void) {
    uint16_t addr, sr;
    __asm__ volatile ("move.w %%sr, %0" : "=d"(sr));
    __asm__ volatile ("move.w #0x2700, %%sr" ::: "cc", "memory");
    for (addr = VRAM_FIX; addr < VRAM_FIX + FIX_COLS * 32; addr++) {
        REG_VRAMADDR = addr;
        REG_VRAMRW = 0;
    }
    __asm__ volatile ("move.w %0, %%sr" :: "d"(sr) : "cc", "memory");
}

void FIX_clearLine(uint8_t row) {
    uint8_t col;
    for (col = 0; col < FIX_COLS; col++)
        fix_write(col, row, 0);
}

void FIX_setTile(uint8_t col, uint8_t row, uint16_t tile, uint8_t palette) {
    fix_write(col, row, ((uint16_t)(palette & 0xF) << 12) | (tile & 0xFFF));
}

void FIX_putChar(uint8_t col, uint8_t row, char ch, uint8_t palette) {
    if (ch < 0x20 || ch > 0x7E)
        return;
    FIX_setTile(col, row, (uint16_t)ch, palette);
}

void FIX_print(uint8_t col, uint8_t row, const char *str, uint8_t palette) {
    uint16_t attr = (uint16_t)(palette & 0xF) << 12;
    while (*str && col < FIX_COLS) {
        char ch = *str++;
        if (ch >= 0x20 && ch <= 0x7E)
            fix_write(col, row, attr | (uint16_t)ch);
        else
            fix_write(col, row, 0);
        col++;
    }
}

static const uint32_t pow10_tbl[] = {
    1000000000, 100000000, 10000000, 1000000, 100000,
    10000, 1000, 100, 10, 1
};

void FIX_printNum(uint8_t col, uint8_t row, int32_t num, uint8_t palette) {
    uint16_t attr = (uint16_t)(palette & 0xF) << 12;
    uint32_t u;
    uint8_t started = 0;
    uint8_t i;

    if (num < 0) {
        fix_write(col++, row, attr | (uint16_t)'-');
        u = (uint32_t)(-(num + 1)) + 1;
    } else {
        u = (uint32_t)num;
    }

    if (u == 0) {
        fix_write(col, row, attr | (uint16_t)'0');
        return;
    }

    for (i = 0; i < 10; i++) {
        uint8_t digit = 0;
        uint32_t p = pow10_tbl[i];
        while (u >= p) {
            u -= p;
            digit++;
        }
        if (digit || started) {
            fix_write(col++, row, attr | (uint16_t)('0' + digit));
            started = 1;
        }
    }
}
