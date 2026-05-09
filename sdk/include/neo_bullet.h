#ifndef NEO_BULLET_H
#define NEO_BULLET_H

#include "neo_types.h"

typedef int32_t fp16;
#define FP16(x)      ((fp16)((x) << 16))
#define FP16_FRAC(x) ((fp16)((int32_t)((x) * 65536.0f)))
#define FP16_INT(x)  ((int16_t)((x) >> 16))

#define BULLET_MAX       370
#define BULLET_ANGLE_MAX 256
#define BULLET_SPEED_COUNT 3
#define BULLET_CURVE_MAX 370

#define BLT_SPEED_SLOW   0
#define BLT_SPEED_MED    1
#define BLT_SPEED_FAST   2

typedef struct {
    fp16    x, y;       /* +0, +4: position 16.16 */
    fp16    dx, dy;     /* +8, +12: velocity (cached from table) */
    uint16_t tile;      /* +16 */
    uint8_t  palette;   /* +18 */
    uint8_t  active;    /* +19 */
    uint8_t  angle;     /* +20: direction 0-255 */
    uint8_t  spd_idx;   /* +21: speed tier */
    int8_t   curve;     /* +22: angular vel per turn (0=straight) */
    uint8_t  age;       /* +23: frames alive, max 255 */
} bullet_t; /* 24 bytes */

typedef struct { fp16 dx, dy; } vel_entry_t;
extern const vel_entry_t blt_vel_table[BULLET_SPEED_COUNT][BULLET_ANGLE_MAX];

typedef struct {
    bullet_t pool[BULLET_MAX];
    uint16_t active_count;
    uint16_t first_slot;
    uint16_t max_bullets;
    uint16_t default_tile;
    uint8_t  default_pal;
    uint16_t default_shrink;
    int8_t   default_curve;
    int16_t  player_x, player_y;
    uint8_t  player_hr;
    uint8_t  hit_flag;
    /* Precomputed SCB values — filled by BLT_update, blasted by BLT_render */
    uint16_t scb3_cache[BULLET_MAX];
    uint16_t scb4_cache[BULLET_MAX];
    /* Free list for O(1) spawn/despawn */
    int16_t  free_list[BULLET_MAX];
    int16_t  free_top;
    /* Curve index list — only curving bullet indices, no scanning */
    uint16_t curve_list[BULLET_CURVE_MAX];
    uint16_t curve_count;
} bullet_sys_t;

extern const int16_t bullet_sin[BULLET_ANGLE_MAX];
extern const int16_t bullet_cos[BULLET_ANGLE_MAX];

void BLT_init(bullet_sys_t *sys, uint16_t first_slot, uint16_t max_bullets,
              uint16_t tile, uint8_t palette);
void BLT_clear(bullet_sys_t *sys);

int16_t BLT_spawn(bullet_sys_t *sys, int16_t x, int16_t y,
                  uint8_t angle, int16_t speed);

/* Update + precompute render. frame = game tick for scheduling. */
void BLT_update(bullet_sys_t *sys, uint16_t frame);

/* Blast cached positions to VRAM. Call after SYS_vblankFlush. */
void BLT_render(bullet_sys_t *sys);

static inline void BLT_setPlayer(bullet_sys_t *sys, int16_t x, int16_t y) {
    sys->player_x = x;
    sys->player_y = y;
}

/* Set curve on a bullet and register it in the curve list */
void BLT_setCurve(bullet_sys_t *sys, int16_t idx, int8_t curve);

void BLT_ring(bullet_sys_t *sys, int16_t x, int16_t y,
              uint8_t count, int16_t speed, uint8_t angle_offset);
void BLT_fan(bullet_sys_t *sys, int16_t x, int16_t y,
             uint8_t count, int16_t speed, uint8_t spread);
void BLT_aimed(bullet_sys_t *sys, int16_t x, int16_t y, int16_t speed);
uint8_t BLT_angleToward(int16_t x1, int16_t y1, int16_t x2, int16_t y2);

#endif
