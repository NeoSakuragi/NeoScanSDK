#ifndef NEO_SPRITE_H
#define NEO_SPRITE_H

#include "neo_types.h"

/*
 * Show a sprite column at screen position (x, y).
 * height = number of 16x16 tile rows (1-33).
 * All rows initially display the same tile; use neo_sprite_set_tile()
 * to assign different tiles per row.
 */
void neo_sprite_show(uint16_t id, uint16_t tile, uint8_t palette,
                     int16_t x, int16_t y, uint8_t height);

void neo_sprite_hide(uint16_t id);

void neo_sprite_move(uint16_t id, int16_t x, int16_t y);

void neo_sprite_set_tile(uint16_t id, uint8_t row,
                         uint16_t tile, uint8_t palette,
                         uint8_t h_flip, uint8_t v_flip);

/* X shrink: 0=full width .. 0xF=narrowest. Y shrink: 0xFF=full height .. 0=flat. */
void neo_sprite_set_shrink(uint16_t id, uint8_t x_shrink, uint8_t y_shrink);

/*
 * Show a sprite group (sticky chain): width columns x height rows.
 * tiles[] is column-major: tiles[col * height + row].
 * first_id through first_id + width - 1 must be consecutive free slots.
 */
void neo_sprite_group_show(uint16_t first_id, uint8_t width, uint8_t height,
                           const uint16_t *tiles, uint8_t palette,
                           int16_t x, int16_t y);

void neo_sprite_group_hide(uint16_t first_id, uint8_t width);

void neo_sprite_group_move(uint16_t first_id, int16_t x, int16_t y);

/* VBlank synchronization */
void neo_wait_vblank(void);
void neo_vblank_flush(void);

#endif
