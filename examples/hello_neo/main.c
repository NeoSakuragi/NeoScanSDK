#include <neoscan.h>
#include "palette.h"
#include "tiles.h"
#include "anim_palette.h"
#include "anim_idle.h"

static int16_t terry_x;
static int16_t terry_y;
static int16_t bounce_x;
static int8_t  bounce_dx;

void game_init(void) {
    PAL_setPalette(1, PALETTE);
    PAL_setPalette(2, ANIM_PALETTE);
    PAL_setBackdrop(RGB8(16, 16, 64));

    SPR_show(1, TILE_SPRITES_0, 1, 80, 30, 1);
    SPR_show(2, TILE_SPRITES_1, 1, 152, 30, 1);
    SPR_show(3, TILE_SPRITES_2, 1, 200, 30, 1);

    ANIM_init(0, &ANIM_IDLE, 20, 2);
    terry_x = 160;
    terry_y = 200;
    ANIM_show(0, terry_x, terry_y);
    ANIM_play(0, ANIM_PINGPONG);

    bounce_x = 80;
    bounce_dx = 1;

    SYS_vblankFlush();
}

void game_tick(void) {
    SYS_kickWatchdog();

    if (JOY_held(0) & JOY_LEFT)   terry_x -= 2;
    if (JOY_held(0) & JOY_RIGHT)  terry_x += 2;
    if (JOY_held(0) & JOY_UP)     terry_y -= 2;
    if (JOY_held(0) & JOY_DOWN)   terry_y += 2;

    if (JOY_pressed(0) & JOY_A)
        ANIM_setSpeed(0, 2);
    if (JOY_pressed(0) & JOY_B)
        ANIM_setSpeed(0, 0);

    ANIM_setPosition(0, terry_x, terry_y);

    bounce_x += bounce_dx;
    if (bounce_x > 290 || bounce_x < 16)
        bounce_dx = -bounce_dx;
    SPR_move(1, bounce_x, 30);

    ANIM_update();

    SYS_vblankFlush();
}
