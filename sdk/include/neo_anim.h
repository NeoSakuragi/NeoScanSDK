#ifndef NEO_ANIM_H
#define NEO_ANIM_H

#include "neo_types.h"

#define ANIM_FORWARD   0
#define ANIM_REVERSE   1
#define ANIM_PINGPONG  2
#define ANIM_ONCE      3

#define ANIM_MAX_SLOTS 8

typedef struct {
    const uint16_t *tiles;
    const uint8_t  *pal_offsets;
    uint16_t duration;
} anim_frame_t;

typedef struct {
    const anim_frame_t *frames;
    uint8_t  num_frames;
    uint8_t  width;
    uint8_t  height;
    int16_t  anchor_x;
    int16_t  anchor_y;
    uint8_t  num_palettes;
} anim_def_t;

void ANIM_init(uint8_t slot, const anim_def_t *def,
               uint16_t first_sprite, uint8_t base_palette);

void ANIM_play(uint8_t slot, uint8_t mode);
void ANIM_stop(uint8_t slot);

void ANIM_setFrame(uint8_t slot, uint8_t frame);
void ANIM_setSpeed(uint8_t slot, uint16_t vblanks_per_frame);
void ANIM_setPosition(uint8_t slot, int16_t x, int16_t y);

void ANIM_show(uint8_t slot, int16_t x, int16_t y);
void ANIM_hide(uint8_t slot);

void ANIM_update(void);

#endif
