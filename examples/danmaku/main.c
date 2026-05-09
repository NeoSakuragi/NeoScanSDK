#include <neoscan.h>
#include <neo_bullet.h>
#include "resources.h"

#define TILE_SHIP      (TILES_SPRITES_0 + 0)
#define TILE_BLT_SMALL (TILES_SPRITES_0 + 1)
#define TILE_BLT_MED   (TILES_SPRITES_0 + 2)
#define TILE_ENEMY_A   (TILES_SPRITES_0 + 4)
#define TILE_ENEMY_B   (TILES_SPRITES_0 + 5)
#define TILE_EXPLODE_1 (TILES_SPRITES_0 + 6)
#define TILE_EXPLODE_2 (TILES_SPRITES_0 + 7)
#define TILE_HITBOX    (TILES_SPRITES_0 + 8)
#define TILE_BLUE_ORB  (TILES_SPRITES_0 + 9)
#define TILE_PINK_ORB  (TILES_SPRITES_0 + 9)  /* same tile, different palette */

#define PAL_BLUE_ORB   2
#define PAL_PINK_ORB   3

/* Sprite slots — keep it simple */
#define SPR_PLAYER   1
#define SPR_SHOT0    2
#define SPR_SHOT1    3
#define SPR_SHOT2    4
#define SPR_SHOT3    5
#define SPR_ENEMY0   6
#define SPR_ENEMY1   7
#define SPR_EXPL0    8
#define SPR_EXPL1    9
#define SPR_HITBOX   10
#define SPR_BLT_FIRST 11
#define SPR_BLT_COUNT 250

/* Debug RAM block — read by emulator tracer each frame */
#define DEBUG_RAM_BULLETS ((volatile uint16_t *)0x10F200)
#define DEBUG_RAM_MAXBLT  ((volatile uint16_t *)0x10F202)
#define DEBUG_RAM_FRAME   ((volatile uint16_t *)0x10F204)
#define DEBUG_RAM_ALIVE   ((volatile uint16_t *)0x10F206)
#define DEBUG_RAM_CURVES  ((volatile uint16_t *)0x10F208)
#define DEBUG_RAM_SPAWNS  ((volatile uint16_t *)0x10F20A)
#define DEBUG_RAM_CMDS    ((volatile uint16_t *)0x10F20C)
#define DEBUG_RAM_MODE    ((volatile uint8_t  *)0x10F20E)
#define DEBUG_RAM_SLOT    ((volatile uint8_t  *)0x10F20F)

static uint16_t spawns_this_frame;

#define MAX_SHOTS    4
#define MAX_ENEMIES  2
#define MAX_EXPLS    2

static bullet_sys_t bsys;

/* --- Player --- */
static int16_t px, py;
static uint8_t alive;
static uint8_t lives;
static uint8_t respawn_cd;
static uint8_t invincible;  /* frames of invincibility left */

/* --- Shots --- */
typedef struct { int16_t x, y; uint8_t on; } shot_t;
static shot_t shots[MAX_SHOTS];
static uint8_t shot_cd;

/* --- Enemies --- */
typedef struct {
    fp16 x, y;         /* 16.16 FP position */
    int16_t hp;
    uint8_t on;
    uint8_t type;
    uint8_t fire_cd;
    uint8_t angle;
} enemy_t;
static enemy_t enemies[MAX_ENEMIES];

/* --- Explosions --- */
typedef struct { int16_t x, y; uint8_t ttl; } expl_t;
static expl_t expls[MAX_EXPLS];

/* --- State --- */
static uint16_t tick;
static uint16_t score;

static const uint16_t hud_pal[16] = {
    0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
    COLOR_RED, COLOR_GREEN, 0, 0,
};

/* Cyan orb: big bright core, stays vivid longer, thin dark edge */
static const uint16_t blue_orb_pal[16] = {
    0x0000, /* transparent */
    RGB8(255,255,255), RGB8(220,255,255), RGB8(180,255,255), RGB8(120,255,255),
    RGB8( 60,255,255), RGB8(  0,240,255), RGB8(  0,220,255), RGB8(  0,200,255),
    RGB8(  0,180,240), RGB8(  0,160,220), RGB8(  0,140,200), RGB8(  0,120,180),
    RGB8(  0, 90,150), RGB8(  0, 60,110), RGB8(  0, 30, 70),
};

/* Pink orb: saturated hot pink core, stays bright, thin dark rim */
static const uint16_t pink_orb_pal[16] = {
    0x0000, /* transparent */
    RGB8(255,255,255), RGB8(255,230,255), RGB8(255,200,255), RGB8(255,160,255),
    RGB8(255,100,240), RGB8(255, 60,220), RGB8(255, 30,200), RGB8(240, 10,180),
    RGB8(220,  0,160), RGB8(200,  0,140), RGB8(180,  0,120), RGB8(150,  0,100),
    RGB8(120,  0, 80), RGB8( 80,  0, 55), RGB8( 40,  0, 30),
};

/* ── helpers ── */

static void itoa5(uint16_t v, char *b) {
    static const uint16_t p[5] = {10000,1000,100,10,1};
    uint8_t i;
    for (i = 0; i < 5; i++) {
        uint8_t d = 0;
        while (v >= p[i]) { v -= p[i]; d++; }
        b[i] = '0' + d;
    }
    b[5] = 0;
}

static void show_expl(int16_t x, int16_t y) {
    uint8_t i;
    for (i = 0; i < MAX_EXPLS; i++) {
        if (expls[i].ttl == 0) {
            expls[i].x = x; expls[i].y = y; expls[i].ttl = 12;
            SPR_show(SPR_EXPL0 + i, TILE_EXPLODE_1, 1, x - 8, y - 8, 1);
            return;
        }
    }
}

static void spawn_enemy(uint8_t slot, uint8_t type, int16_t x) {
    enemy_t *e = &enemies[slot];
    e->x = FP16(x); e->y = FP16(-8); e->hp = (type == 0) ? 3 : 6;
    e->on = 1; e->type = type; e->fire_cd = 30; e->angle = 0;
    SPR_show(SPR_ENEMY0 + slot, type == 0 ? TILE_ENEMY_A : TILE_ENEMY_B,
             1, x - 8, -8, 1);
}

/* ── update functions ── all logic + cmd_push, no flushes ── */

static void step_player(void) {
    uint16_t held = JOY_held(0);
    int16_t spd;
    uint8_t i;

    if (!alive) {
        if (respawn_cd > 0) respawn_cd--;
        if (respawn_cd == 0) {
            alive = 1;
            px = 160; py = 190;
            invincible = 180; /* 3 seconds at 60fps */
            SPR_show(SPR_PLAYER, TILE_SHIP, 1, px - 8, py - 8, 1);
        }
        return;
    }

    spd = (held & JOY_B) ? 1 : 2;
    if (held & JOY_UP)    py -= spd;
    if (held & JOY_DOWN)  py += spd;
    if (held & JOY_LEFT)  px -= spd;
    if (held & JOY_RIGHT) px += spd;
    if (px < 8)   px = 8;
    if (px > 312) px = 312;
    if (py < 16)  py = 16;
    if (py > 216) py = 216;
    SPR_move(SPR_PLAYER, px - 8, py - 8);
    SPR_move(SPR_HITBOX, px - 8, py - 8);

    /* invincibility blink */
    if (invincible > 0) {
        invincible--;
        if (invincible & 4)
            SPR_hide(SPR_PLAYER);
        else
            SPR_show(SPR_PLAYER, TILE_SHIP, 1, px - 8, py - 8, 1);
    }

    (void)i;
}

static void step_shots(void) {
    uint8_t i, j;
    for (i = 0; i < MAX_SHOTS; i++) {
        if (!shots[i].on) continue;
        shots[i].y -= 5;
        if (shots[i].y < -8) { shots[i].on = 0; SPR_hide(SPR_SHOT0 + i); continue; }
        SPR_move(SPR_SHOT0 + i, shots[i].x - 8, shots[i].y - 8);

        for (j = 0; j < MAX_ENEMIES; j++) {
            enemy_t *e = &enemies[j];
            if (!e->on) continue;
            if (shots[i].x > FP16_INT(e->x) - 10 && shots[i].x < FP16_INT(e->x) + 10 &&
                shots[i].y > FP16_INT(e->y) - 10 && shots[i].y < FP16_INT(e->y) + 10) {
                shots[i].on = 0; SPR_hide(SPR_SHOT0 + i);
                e->hp--;
                if (e->hp <= 0) {
                    show_expl(FP16_INT(e->x), FP16_INT(e->y));
                    e->on = 0; SPR_hide(SPR_ENEMY0 + j);
                    score += (e->type == 0) ? 100 : 250;
                }
                break;
            }
        }
    }
}

static void step_enemies(void) {
    uint8_t i;
    int16_t spd = 0x0129;

    for (i = 0; i < MAX_ENEMIES; i++) {
        enemy_t *e = &enemies[i];
        if (!e->on) continue;

        /* Movement: 0.25 px/frame via FP16. 0x4000 = 0.25 in 16.16 */
        if (e->type == 0) {
            if (FP16_INT(e->y) < 40) { e->y += 0x10000; }
            e->x += (e->angle & 0x80) ? -0x4000 : 0x4000;
            if (FP16_INT(e->x) > 260) e->angle |= 0x80;
            if (FP16_INT(e->x) < 60)  e->angle &= 0x7F;
        } else {
            if (FP16_INT(e->y) < 30) e->y = FP16(30);
            e->y += (e->angle & 0x80) ? -0x4000 : 0x4000;
            if (FP16_INT(e->y) > 120) e->angle |= 0x80;
            if (FP16_INT(e->y) < 30)  e->angle &= 0x7F;
        }
        SPR_move(SPR_ENEMY0 + i, FP16_INT(e->x) - 8, FP16_INT(e->y) - 8);

        if (e->fire_cd > 0) { e->fire_cd--; }
        /*
         * Frame schedule:
         *   0-3: curve rotation (1/4 per frame)
         *   4:   blue ring batch 1 (8 bullets)
         *   5:   blue ring batch 2 (8 bullets)
         *   8:   HUD
         *  10:   pink fan batch 1 (6 bullets)
         *  12:   pink fan batch 2 (6 bullets)
         */
        {
            uint8_t slot16 = tick & 15;
            int16_t ex = FP16_INT(e->x), ey = FP16_INT(e->y);
            BLT_setPlayer(&bsys, px, py);

            if (e->type == 0 && e->fire_cd == 0) {
                if (slot16 == 4) {
                    uint8_t ring_angle = (e->angle & 0x7F) << 1;
                    bsys.default_curve = 2;
                    BLT_ring(&bsys, ex, ey, 14, spd, ring_angle);
                    bsys.default_curve = 0;
                    e->angle = (e->angle & 0x80) | (((e->angle & 0x7F) + 3) & 0x7F);
                    e->fire_cd = 10;
                } else { continue; }
            } else if (e->type == 1 && e->fire_cd == 0) {
                if (slot16 == 10) {
                    bsys.default_tile = TILE_PINK_ORB;
                    bsys.default_pal = PAL_PINK_ORB;
                    bsys.default_shrink = 0x077F;
                    BLT_fan(&bsys, ex, ey, 12, spd, 50);
                    bsys.default_tile = TILE_BLUE_ORB;
                    bsys.default_pal = PAL_BLUE_ORB;
                    bsys.default_shrink = 0x0FFF;
                    e->fire_cd = 10;
                } else { continue; }
            } else { continue; }
        }

        if (FP16_INT(e->y) > 240) { e->on = 0; SPR_hide(SPR_ENEMY0 + i); }
    }
}

static void step_expls(void) {
    uint8_t i;
    for (i = 0; i < MAX_EXPLS; i++) {
        if (expls[i].ttl == 0) continue;
        expls[i].ttl--;
        if (expls[i].ttl == 6)
            SPR_setTile(SPR_EXPL0 + i, 0, TILE_EXPLODE_2, 1, 0, 0);
        if (expls[i].ttl == 0)
            SPR_hide(SPR_EXPL0 + i);
    }
}

static void step_spawner(void) {
    uint8_t i;
    /* respawn dead enemies */
    for (i = 0; i < MAX_ENEMIES; i++) {
        if (!enemies[i].on && (tick & 0x7F) == (uint16_t)(i << 6)) {
            int16_t x = 60 + ((tick * 97 + i * 130) & 0xFF);
            if (x > 280) x = 280;
            spawn_enemy(i, i & 1, x);
        }
    }
}

static void step_collision(void) {
    if (!alive || invincible > 0) return;
    if (bsys.hit_flag) {
        alive = 0;
        show_expl(px, py);
        SPR_hide(SPR_PLAYER);
        if (lives > 0) lives--;
        respawn_cd = 90;
    }
}

static void itoa3(uint16_t v, char *b) {
    uint8_t d;
    d = 0; while (v >= 100) { v -= 100; d++; } b[0] = '0' + d;
    d = 0; while (v >= 10)  { v -= 10;  d++; } b[1] = '0' + d;
    b[2] = '0' + (uint8_t)v;
    b[3] = 0;
}

static void draw_hud(void) {
    char buf[8];
    FIX_print(1, 2, "SCORE", 4);
    itoa5(score, buf);
    FIX_print(7, 2, buf, 4);

    /* Bullet counter on fix layer */
    FIX_print(15, 2, "BLT", 4);
    itoa3(bsys.active_count, buf);
    FIX_print(19, 2, buf, 4);
    FIX_putChar(22, 2, '/', 4);
    itoa3(bsys.max_bullets, buf);
    FIX_print(23, 2, buf, 4);

    FIX_print(30, 2, "LIVES", 4);
    buf[0] = '0' + lives; buf[1] = 0;
    FIX_print(36, 2, buf, 4);

    /* Write to debug RAM for emulator access */
    *DEBUG_RAM_BULLETS = bsys.active_count;
    *DEBUG_RAM_MAXBLT  = bsys.max_bullets;
    *DEBUG_RAM_FRAME   = tick;
    *DEBUG_RAM_ALIVE   = 0xBEEF;
}

/* ── entry points ── */

void game_init(void) {
    uint8_t i;

    /* Force credits so BIOS doesn't run demo timer */
    *(volatile uint8_t *)0x10FD82 = 0x09;  /* P1 credits = 9 (BCD) */
    *(volatile uint8_t *)0x10FD84 = 0x09;  /* P2 credits = 9 */

    PAL_setPalette(0, hud_pal);
    PAL_setPalette(4, hud_pal);
    PAL_setPalette(1, TILES_PALETTE);
    PAL_setPalette(PAL_BLUE_ORB, blue_orb_pal);
    PAL_setPalette(PAL_PINK_ORB, pink_orb_pal);
    PAL_setBackdrop(RGB8(0, 0, 0));
    FIX_clear();

    px = 160; py = 190;
    alive = 1; lives = 3; respawn_cd = 0;
    tick = 0; score = 0; shot_cd = 0;

    for (i = 0; i < MAX_SHOTS; i++) shots[i].on = 0;
    for (i = 0; i < MAX_ENEMIES; i++) enemies[i].on = 0;
    for (i = 0; i < MAX_EXPLS; i++) expls[i].ttl = 0;

    invincible = 0;
    SPR_show(SPR_PLAYER, TILE_SHIP, 1, px - 8, py - 8, 1);
    SPR_show(SPR_HITBOX, TILE_HITBOX, 1, px - 8, py - 8, 1);
    BLT_init(&bsys, SPR_BLT_FIRST, SPR_BLT_COUNT, TILE_BLUE_ORB, PAL_BLUE_ORB);
    bsys.player_hr = 2;

    SYS_vblankFlush();

    /* Spawn the two enemies */
    spawn_enemy(0, 0, 100);
    spawn_enemy(1, 1, 220);
}

extern uint16_t neo_cmd_count;

void game_tick(void) {
    SYS_kickWatchdog();
    spawns_this_frame = 0;
    *(volatile uint8_t *)0x10FDD4 = 0xFF;
    *(volatile uint8_t *)0x10FDD6 = 0xFF;
    *(volatile uint8_t *)0x10FDDA = 0xFF;
    tick++;

    /* 1. All game logic — generates cmd_push calls */
    step_player();
    step_shots();
    step_enemies();
    step_expls();
    step_spawner();

    BLT_setPlayer(&bsys, px, py);
    BLT_update(&bsys, tick);
    step_collision();

    if ((tick & 15) == 8) draw_hud();

    /* Always update debug RAM for emulator miss detection */
    /* Write full debug block for tracer */
    *DEBUG_RAM_BULLETS = bsys.active_count;
    *DEBUG_RAM_MAXBLT  = bsys.max_bullets;
    *DEBUG_RAM_FRAME   = tick;
    *DEBUG_RAM_ALIVE   = 0xBEEF;
    *DEBUG_RAM_CURVES  = bsys.curve_count;
    *DEBUG_RAM_SPAWNS  = spawns_this_frame;
    *DEBUG_RAM_CMDS    = neo_cmd_count;
    *DEBUG_RAM_MODE    = *(volatile uint8_t *)0x10FD80;
    *DEBUG_RAM_SLOT    = (uint8_t)(tick & 15);
    spawns_this_frame  = 0;

    /* 2. Flush ALL cmd_push to VRAM in one go */
    SYS_vblankFlush();

    /* 3. Bullet positions — direct VRAM writes, after flush */
    BLT_render(&bsys);
}
