#ifndef NEO_FIX_H
#define NEO_FIX_H

#include "neo_types.h"

#define VRAM_FIX   0x7000
#define FIX_COLS   40
#define FIX_ROWS   28

void FIX_clear(void);
void FIX_clearLine(uint8_t row);
void FIX_setTile(uint8_t col, uint8_t row, uint16_t tile, uint8_t palette);
void FIX_putChar(uint8_t col, uint8_t row, char ch, uint8_t palette);
void FIX_print(uint8_t col, uint8_t row, const char *str, uint8_t palette);
void FIX_printNum(uint8_t col, uint8_t row, int32_t num, uint8_t palette);

#endif
