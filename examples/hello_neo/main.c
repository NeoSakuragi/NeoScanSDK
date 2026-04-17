#include <neoscan.h>
#include "palette.h"
#include "tiles.h"
#include "anim_palette.h"
#include "anim_idle.h"
#include "sounds.h"

static int16_t terry_x;
static int16_t terry_y;
static int16_t bounce_x;
static int8_t  bounce_dx;
static uint8_t shrink_y;

static const uint16_t TEXT_PAL[16] = {
    0x8000,
    COLOR_WHITE,
    RGB(20, 25, 31),
    RGB(31, 31, 0),
};

void game_init(void) {
    PAL_setPalette(0, TEXT_PAL);
    PAL_setPalette(1, PALETTE);
    PAL_setPalette(2, ANIM_PALETTE);
    PAL_setBackdrop(RGB8(16, 16, 64));

    FIX_clear();
    FIX_print(14, 2, "NEOSCAN SDK", 0);
    FIX_print(4, 26, "DPAD:MOVE A/B:ZOOM C:HIT D:BEEP", 0);

    SPR_show(1, TILE_SPRITES_0, 1, 80, 30, 1);
    SPR_show(2, TILE_SPRITES_1, 1, 152, 30, 1);
    SPR_show(3, TILE_SPRITES_2, 1, 200, 30, 1);

    ANIM_init(0, &ANIM_IDLE, 20, 2);
    ANIM_init(1, &ANIM_IDLE, 30, 2);
    ANIM_setFlip(1, 1);
    terry_x = 160;
    terry_y = 200;
    shrink_y = 0xFF;
    ANIM_show(0, terry_x, terry_y);
    ANIM_show(1, terry_x - 70, terry_y);
    ANIM_play(0, ANIM_PINGPONG);
    ANIM_play(1, ANIM_PINGPONG);

    bounce_x = 80;
    bounce_dx = 1;

    SYS_vblankFlush();

    SND_play(SND_HIT);
}

void game_tick(void) {
    uint8_t col;

    SYS_kickWatchdog();

    if (JOY_held(0) & JOY_LEFT)   terry_x -= 2;
    if (JOY_held(0) & JOY_RIGHT)  terry_x += 2;
    if (JOY_held(0) & JOY_UP)     terry_y -= 2;
    if (JOY_held(0) & JOY_DOWN)   terry_y += 2;

    if (JOY_held(0) & JOY_A) {
        if (shrink_y > 2) shrink_y -= 2;
    }
    if (JOY_held(0) & JOY_B) {
        if (shrink_y < 254) shrink_y += 2;
    }

    if (JOY_pressed(0) & JOY_C)
        SND_play(SND_HIT);
    if (JOY_pressed(0) & JOY_D)
        SND_play(SND_BEEP);

    if (JOY_pressed(0) & JOY_START) {
        terry_x = 160;
        terry_y = 200;
        shrink_y = 0xFF;
    }

    for (col = 0; col < ANIM_IDLE.width; col++) {
        SPR_setZoom(20 + col, shrink_y);
        SPR_setZoom(30 + col, shrink_y);
    }

    FIX_print(1, 24, "ZOOM:     ", 0);
    FIX_printNum(6, 24, shrink_y, 0);

    ANIM_setPosition(0, terry_x, terry_y);
    ANIM_setPosition(1, terry_x - 70, terry_y);

    bounce_x += bounce_dx;
    if (bounce_x > 290 || bounce_x < 16)
        bounce_dx = -bounce_dx;
    SPR_move(1, bounce_x, 30);

    ANIM_update();

    SYS_vblankFlush();
}
