#ifndef NEO_SPRITE_H
#define NEO_SPRITE_H

#include "neo_types.h"

void SPR_show(uint16_t id, uint16_t tile, uint8_t palette,
              int16_t x, int16_t y, uint8_t height);

void SPR_hide(uint16_t id);

void SPR_move(uint16_t id, int16_t x, int16_t y);

void SPR_setTile(uint16_t id, uint8_t row,
                 uint16_t tile, uint8_t palette,
                 uint8_t h_flip, uint8_t v_flip);

void SPR_setZoom(uint16_t id, uint8_t zoom);
void SPR_setZoomXY(uint16_t id, uint8_t zoom_x, uint8_t zoom_y);

void SPR_groupShow(uint16_t first_id, uint8_t width, uint8_t height,
                   const uint16_t *tiles, uint8_t palette,
                   int16_t x, int16_t y);

void SPR_groupHide(uint16_t first_id, uint8_t width);

void SPR_groupMove(uint16_t first_id, int16_t x, int16_t y);

void SYS_waitVBlank(void);
void SYS_vblankFlush(void);

#endif
