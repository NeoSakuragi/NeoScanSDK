#ifndef NEO_BULLET_H
#define NEO_BULLET_H

#include "neo_types.h"

/* Fixed-point: 16.16 for positions, 8.8 for speed/angles */
typedef int32_t fp16;
#define FP16(x)      ((fp16)((x) << 16))
#define FP16_FRAC(x) ((fp16)((int32_t)((x) * 65536.0f)))
#define FP16_INT(x)  ((int16_t)((x) >> 16))

#define BULLET_MAX       370
#define BULLET_ANGLE_MAX 256

typedef struct {
    fp16    x, y;       /* position 16.16 */
    fp16    dx, dy;     /* velocity 16.16 (set at spawn, constant) */
    uint16_t tile;
    uint8_t  palette;
    uint8_t  active;
    uint16_t sprite_id; /* assigned sprite slot */
    uint16_t age;       /* frames alive */
} bullet_t;

typedef struct {
    bullet_t pool[BULLET_MAX];
    uint16_t active_count;
    uint16_t first_slot;    /* first sprite slot reserved for bullets */
    uint16_t max_bullets;   /* max active (sprite slots available) */
    uint16_t default_tile;
    uint8_t  default_pal;
    uint16_t default_shrink; /* SCB2 value: 0x0FFF=full, 0x077F=half */
    /* player hitbox for collision (center point + radius) */
    int16_t  player_x, player_y;
    uint8_t  player_hr;     /* hit radius in pixels (typically 2) */
    uint8_t  hit_flag;      /* set when any bullet hits player */
} bullet_sys_t;

/* Sin/cos table: 256 entries, values are 8.8 FP (-256 to +255) */
extern const int16_t bullet_sin[BULLET_ANGLE_MAX];
extern const int16_t bullet_cos[BULLET_ANGLE_MAX];

/* Initialize bullet system. first_slot = first sprite ID reserved for bullets. */
void BLT_init(bullet_sys_t *sys, uint16_t first_slot, uint16_t max_bullets,
              uint16_t tile, uint8_t palette);

/* Clear all bullets */
void BLT_clear(bullet_sys_t *sys);

/* Spawn one bullet at (x,y) with angle (0-255) and speed (8.8 FP).
   Returns bullet index or -1 if pool full. */
int16_t BLT_spawn(bullet_sys_t *sys, int16_t x, int16_t y,
                  uint8_t angle, int16_t speed);

/* Spawn with explicit velocity */
int16_t BLT_spawn_xy(bullet_sys_t *sys, int16_t x, int16_t y,
                     fp16 dx, fp16 dy);


/* Update all bullets: move + bounds check + collision.
   Call once per frame before BLT_render. */
void BLT_update(bullet_sys_t *sys);

/* Write bullet positions to VRAM. Call during/after VBlank. */
void BLT_render(bullet_sys_t *sys);

/* Set player position for collision checks */
static inline void BLT_setPlayer(bullet_sys_t *sys, int16_t x, int16_t y) {
    sys->player_x = x;
    sys->player_y = y;
}

/* --- Pattern spawners --- */

/* Ring: n bullets evenly spaced, all same speed */
void BLT_ring(bullet_sys_t *sys, int16_t x, int16_t y,
              uint8_t count, int16_t speed, uint8_t angle_offset);

/* Aimed fan: n bullets spread around angle toward player */
void BLT_fan(bullet_sys_t *sys, int16_t x, int16_t y,
             uint8_t count, int16_t speed, uint8_t spread);

/* Aimed single: one bullet toward player */
void BLT_aimed(bullet_sys_t *sys, int16_t x, int16_t y, int16_t speed);

/* Utility: angle from (x1,y1) toward (x2,y2), returns 0-255 */
uint8_t BLT_angleToward(int16_t x1, int16_t y1, int16_t x2, int16_t y2);

#endif
