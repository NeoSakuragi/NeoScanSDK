#include "neo_hw.h"
#include "neo_bullet.h"
#include "neo_internal.h"

static inline void vdp_write_atomic(uint16_t addr, uint16_t data) {
    uint16_t sr;
    __asm__ volatile ("move.w %%sr, %0" : "=d"(sr));
    __asm__ volatile ("move.w #0x2700, %%sr" ::: "cc", "memory");
    REG_VRAMADDR = addr;
    REG_VRAMRW = data;
    __asm__ volatile ("move.w %0, %%sr" :: "d"(sr) : "cc", "memory");
}

/* Sin/cos tables for BLT_angleToward and spawn velocity */
const int16_t bullet_sin[256] = {
      0,   6,  12,  18,  25,  31,  37,  43,  49,  56,  62,  68,  74,  80,  86,  91,
     97, 103, 109, 114, 120, 125, 131, 136, 141, 146, 151, 156, 161, 166, 170, 175,
    179, 183, 187, 191, 195, 199, 202, 206, 209, 212, 215, 218, 220, 223, 225, 227,
    229, 231, 233, 234, 236, 237, 238, 239, 240, 241, 242, 242, 243, 243, 243, 243,
    243, 243, 243, 243, 243, 242, 242, 241, 240, 239, 238, 237, 236, 234, 233, 231,
    229, 227, 225, 223, 220, 218, 215, 212, 209, 206, 202, 199, 195, 191, 187, 183,
    179, 175, 170, 166, 161, 156, 151, 146, 141, 136, 131, 125, 120, 114, 109, 103,
     97,  91,  86,  80,  74,  68,  62,  56,  49,  43,  37,  31,  25,  18,  12,   6,
      0,  -6, -12, -18, -25, -31, -37, -43, -49, -56, -62, -68, -74, -80, -86, -91,
    -97,-103,-109,-114,-120,-125,-131,-136,-141,-146,-151,-156,-161,-166,-170,-175,
   -179,-183,-187,-191,-195,-199,-202,-206,-209,-212,-215,-218,-220,-223,-225,-227,
   -229,-231,-233,-234,-236,-237,-238,-239,-240,-241,-242,-242,-243,-243,-243,-243,
   -243,-243,-243,-243,-243,-242,-242,-241,-240,-239,-238,-237,-236,-234,-233,-231,
   -229,-227,-225,-223,-220,-218,-215,-212,-209,-206,-202,-199,-195,-191,-187,-183,
   -179,-175,-170,-166,-161,-156,-151,-146,-141,-136,-131,-125,-120,-114,-109,-103,
    -97, -91, -86, -80, -74, -68, -62, -56, -49, -43, -37, -31, -25, -18, -12,  -6,
};
const int16_t bullet_cos[256] = {
    243, 243, 243, 243, 243, 242, 242, 241, 240, 239, 238, 237, 236, 234, 233, 231,
    229, 227, 225, 223, 220, 218, 215, 212, 209, 206, 202, 199, 195, 191, 187, 183,
    179, 175, 170, 166, 161, 156, 151, 146, 141, 136, 131, 125, 120, 114, 109, 103,
     97,  91,  86,  80,  74,  68,  62,  56,  49,  43,  37,  31,  25,  18,  12,   6,
      0,  -6, -12, -18, -25, -31, -37, -43, -49, -56, -62, -68, -74, -80, -86, -91,
    -97,-103,-109,-114,-120,-125,-131,-136,-141,-146,-151,-156,-161,-166,-170,-175,
   -179,-183,-187,-191,-195,-199,-202,-206,-209,-212,-215,-218,-220,-223,-225,-227,
   -229,-231,-233,-234,-236,-237,-238,-239,-240,-241,-242,-242,-243,-243,-243,-243,
   -243,-243,-243,-243,-243,-242,-242,-241,-240,-239,-238,-237,-236,-234,-233,-231,
   -229,-227,-225,-223,-220,-218,-215,-212,-209,-206,-202,-199,-195,-191,-187,-183,
   -179,-175,-170,-166,-161,-156,-151,-146,-141,-136,-131,-125,-120,-114,-109,-103,
    -97, -91, -86, -80, -74, -68, -62, -56, -49, -43, -37, -31, -25, -18, -12,  -6,
      0,   6,  12,  18,  25,  31,  37,  43,  49,  56,  62,  68,  74,  80,  86,  91,
     97, 103, 109, 114, 120, 125, 131, 136, 141, 146, 151, 156, 161, 166, 170, 175,
    179, 183, 187, 191, 195, 199, 202, 206, 209, 212, 215, 218, 220, 223, 225, 227,
    229, 231, 233, 234, 236, 237, 238, 239, 240, 241, 242, 242, 243, 243, 243, 243,
};

#include "blt_vel_table.inc"

static const uint8_t atan_tab[65] = {
     0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 6, 6, 7,
     7, 7, 8, 8, 8, 9, 9, 9,10,10,10,10,11,11,11,11,
    12,12,12,12,13,13,13,13,13,14,14,14,14,14,14,15,
    15,15,15,15,15,15,15,16,16,16,16,16,16,16,16,16,
    16
};

/* ── Init / Clear ── */

static void init_free_list(bullet_sys_t *sys) {
    uint16_t i;
    for (i = 0; i < sys->max_bullets; i++)
        sys->free_list[i] = (int16_t)(sys->max_bullets - 1 - i);
    sys->free_top = sys->max_bullets - 1;
}

void BLT_init(bullet_sys_t *sys, uint16_t first_slot, uint16_t max_bullets,
              uint16_t tile, uint8_t palette) {
    uint16_t i;
    sys->first_slot = first_slot;
    sys->max_bullets = max_bullets > BULLET_MAX ? BULLET_MAX : max_bullets;
    sys->default_tile = tile;
    sys->default_pal = palette;
    sys->default_shrink = 0x0FFF;
    sys->default_curve = 0;
    sys->active_count = 0;
    sys->curve_count = 0;
    sys->player_x = 160;
    sys->player_y = 200;
    sys->player_hr = 2;
    sys->hit_flag = 0;
    for (i = 0; i < BULLET_MAX; i++)
        sys->pool[i].active = 0;
    init_free_list(sys);
    for (i = 0; i < sys->max_bullets; i++)
        vdp_write_atomic(VRAM_SCB3 + first_slot + i, 0);
}

void BLT_clear(bullet_sys_t *sys) {
    uint16_t i;
    for (i = 0; i < BULLET_MAX; i++)
        sys->pool[i].active = 0;
    sys->active_count = 0;
    sys->curve_count = 0;
    init_free_list(sys);
    for (i = 0; i < sys->max_bullets; i++)
        vdp_write_atomic(VRAM_SCB3 + sys->first_slot + i, 0);
}

/* ── Spawn / Despawn ── */

static int16_t find_free(bullet_sys_t *sys) {
    if (sys->free_top < 0) return -1;
    return sys->free_list[sys->free_top--];
}

static void release_slot(bullet_sys_t *sys, uint16_t idx) {
    sys->pool[idx].active = 0;
    sys->active_count--;
    sys->free_list[++sys->free_top] = (int16_t)idx;
}

static void setup_sprite(bullet_sys_t *sys, uint16_t idx) {
    bullet_t *b = &sys->pool[idx];
    uint16_t sid = sys->first_slot + idx;
    uint16_t scb1_addr = VRAM_SCB1 + sid * 64;
    uint16_t tile = b->tile;
    uint16_t attr = (uint16_t)b->palette << 8;
    uint16_t shrink = sys->default_shrink;
    uint16_t sr;
    __asm__ volatile ("move.w %%sr, %0" : "=d"(sr));
    __asm__ volatile ("move.w #0x2700, %%sr" ::: "cc", "memory");
    REG_VRAMADDR = scb1_addr;
    REG_VRAMRW = tile;
    REG_VRAMADDR = scb1_addr + 1;
    REG_VRAMRW = attr;
    REG_VRAMADDR = VRAM_SCB2 + sid;
    REG_VRAMRW = shrink;
    __asm__ volatile ("move.w %0, %%sr" :: "d"(sr) : "cc", "memory");
}

int16_t BLT_spawn(bullet_sys_t *sys, int16_t x, int16_t y,
                  uint8_t angle, int16_t speed) {
    int16_t idx = find_free(sys);
    bullet_t *b;
    if (idx < 0) return -1;
    b = &sys->pool[idx];
    b->x = FP16(x);
    b->y = FP16(y);
    b->angle = angle;
    b->spd_idx = BLT_SPEED_MED;
    b->curve = sys->default_curve;
    if (b->curve && sys->curve_count < BULLET_CURVE_MAX)
        sys->curve_list[sys->curve_count++] = (uint16_t)idx;
    b->dx = ((int32_t)bullet_sin[angle] * speed);
    b->dy = -((int32_t)bullet_cos[angle] * speed);
    b->tile = sys->default_tile;
    b->palette = sys->default_pal;
    b->active = 1;
    b->age = 0;
    sys->active_count++;
    (*(volatile uint16_t *)0x10F20A)++;
    setup_sprite(sys, (uint16_t)idx);
    return idx;
}

void BLT_setCurve(bullet_sys_t *sys, int16_t idx, int8_t curve) {
    if (idx < 0 || !sys->pool[idx].active) return;
    sys->pool[idx].curve = curve;
    if (curve != 0 && sys->curve_count < BULLET_CURVE_MAX)
        sys->curve_list[sys->curve_count++] = (uint16_t)idx;
}

/* ── Update + Render ── */

void BLT_update(bullet_sys_t *sys, uint16_t frame) {
    uint16_t i;
    int16_t px, py, dx, dy;
    int16_t hr = sys->player_hr;
    uint16_t *scb3 = sys->scb3_cache;
    uint16_t *scb4 = sys->scb4_cache;

    sys->hit_flag = 0;

    /* Curve: frames 0-3 of 16, process 1/4 of curve_list per frame.
       Only iterates CURVING bullets (not entire pool). Zero cost on frames 4-15. */
    {
        uint16_t slot16 = frame & 15;
        if (slot16 < 4 && sys->curve_count > 0) {
            uint16_t quarter = (sys->curve_count + 3) >> 2;
            uint16_t start = slot16 * quarter;
            uint16_t end = start + quarter;
            if (end > sys->curve_count) end = sys->curve_count;
            for (i = start; i < end; i++) {
                bullet_t *b = &sys->pool[sys->curve_list[i]];
                if (b->active && b->curve) {
                    uint8_t a = (uint8_t)(b->angle + b->curve);
                    b->angle = a;
                    const vel_entry_t *v = &blt_vel_table[b->spd_idx][a];
                    b->dx = v->dx;
                    b->dy = v->dy;
                }
            }
        }
    }

    /* Main loop: move + bounds + collision + SCB cache. One pass. */
    for (i = 0; i < sys->max_bullets; i++) {
        if ((i & 63) == 0) REG_WATCHDOG = 0;
        bullet_t *b = &sys->pool[i];
        if (!b->active) {
            scb3[i] = 0;
            scb4[i] = 0;
            continue;
        }

        b->x += b->dx;
        b->y += b->dy;
        if (b->age < 255) b->age++;

        px = FP16_INT(b->x);
        py = FP16_INT(b->y);

        if (px < -16 || px > 336 || py < -16 || py > 240 || b->age >= 250) {
            release_slot(sys, i);
            scb3[i] = 0;
            scb4[i] = 0;
            continue;
        }

        dx = px - sys->player_x;
        dy = py - sys->player_y;
        if (dx > -hr && dx < hr && dy > -hr && dy < hr) {
            sys->hit_flag = 1;
            release_slot(sys, i);
            scb3[i] = 0;
            scb4[i] = 0;
            continue;
        }

        scb3[i] = (uint16_t)(((496 - (py - 8)) & 0x1FF) << 7) | 1;
        scb4[i] = (uint16_t)(((px - 8) & 0x1FF) << 7);
    }

    /* Compact curve list: remove dead entries */
    if (sys->curve_count > 0) {
        uint16_t w = 0;
        for (i = 0; i < sys->curve_count; i++) {
            if (sys->pool[sys->curve_list[i]].active)
                sys->curve_list[w++] = sys->curve_list[i];
        }
        sys->curve_count = w;
    }
}

void BLT_render(bullet_sys_t *sys) {
    uint16_t i;
    uint16_t *scb3 = sys->scb3_cache;
    uint16_t *scb4 = sys->scb4_cache;
    uint16_t n = sys->max_bullets;

    REG_WATCHDOG = 0;
    REG_VRAMMOD = 1;
    REG_VRAMADDR = VRAM_SCB3 + sys->first_slot;
    for (i = 0; i < n; i++)
        REG_VRAMRW = scb3[i];

    REG_WATCHDOG = 0;
    REG_VRAMADDR = VRAM_SCB4 + sys->first_slot;
    for (i = 0; i < n; i++)
        REG_VRAMRW = scb4[i];

    REG_VRAMMOD = 0;
}

/* ── Pattern spawners ── */

static uint16_t div_64(uint16_t num, uint16_t den) {
    uint32_t n32 = (uint32_t)num << 6;
    uint16_t result;
    if (den == 0) return 64;
    __asm__ volatile (
        "divu.w %1, %0"
        : "+d" (n32)
        : "d" (den)
    );
    result = (uint16_t)(n32 & 0xFFFF);
    return result > 64 ? 64 : result;
}

uint8_t BLT_angleToward(int16_t x1, int16_t y1, int16_t x2, int16_t y2) {
    int16_t adx, ady;
    uint16_t slope;
    uint8_t a;
    int16_t ddx = x2 - x1;
    int16_t ddy = y2 - y1;
    if (ddx == 0 && ddy == 0) return 0;
    adx = ddx < 0 ? -ddx : ddx;
    ady = ddy < 0 ? -ddy : ddy;
    if (adx == 0) return ddy < 0 ? 0 : 128;
    if (ady == 0) return ddx > 0 ? 64 : 192;
    if (adx >= ady)
        slope = div_64((uint16_t)ady, (uint16_t)adx);
    else
        slope = div_64((uint16_t)adx, (uint16_t)ady);
    a = atan_tab[slope];
    if (adx >= ady) {
        if (ddx > 0 && ddy < 0)      return 64 - a;
        else if (ddx > 0 && ddy >= 0) return 64 + a;
        else if (ddx < 0 && ddy >= 0) return 192 - a;
        else                          return 192 + a;
    } else {
        if (ddx >= 0 && ddy < 0)     return a;
        else if (ddx >= 0 && ddy > 0) return 128 - a;
        else if (ddx < 0 && ddy > 0)  return 128 + a;
        else                          return (uint8_t)(256 - a);
    }
}

static const uint8_t ring_step[33] = {
    0, 0, 128, 85, 64, 51, 42, 36, 32, 28, 25, 23, 21, 19, 18, 17,
    16, 15, 14, 13, 12, 12, 11, 11, 10, 10, 9, 9, 9, 8, 8, 8, 8,
};

void BLT_ring(bullet_sys_t *sys, int16_t x, int16_t y,
              uint8_t count, int16_t speed, uint8_t angle_offset) {
    uint8_t i;
    uint8_t step = (count <= 32) ? ring_step[count] : 4;
    for (i = 0; i < count; i++)
        BLT_spawn(sys, x, y, (uint8_t)(angle_offset + i * step), speed);
}

void BLT_fan(bullet_sys_t *sys, int16_t x, int16_t y,
             uint8_t count, int16_t speed, uint8_t spread) {
    uint8_t aim = BLT_angleToward(x, y, sys->player_x, sys->player_y);
    uint8_t half = spread >> 1;
    uint8_t step, i;
    if (count <= 1) {
        BLT_spawn(sys, x, y, aim, speed);
        return;
    }
    step = (count - 1 <= 32) ? (uint8_t)((uint16_t)spread * ring_step[count - 1] >> 8) : 1;
    if (step == 0) step = 1;
    for (i = 0; i < count; i++)
        BLT_spawn(sys, x, y, (uint8_t)(aim - half + i * step), speed);
}

void BLT_aimed(bullet_sys_t *sys, int16_t x, int16_t y, int16_t speed) {
    uint8_t aim = BLT_angleToward(x, y, sys->player_x, sys->player_y);
    BLT_spawn(sys, x, y, aim, speed);
}
