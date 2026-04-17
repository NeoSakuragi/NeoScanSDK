#include <neoscan.h>
#include "palette.h"
#include "tiles.h"
#include "anim_palette.h"
#include "anim_idle.h"

static int16_t bounce_x;
static int8_t  bounce_dx;

void game_init(void) {
    PAL_setPalette(1, PALETTE);
    PAL_setPalette(2, ANIM_PALETTE);
    PAL_setBackdrop(RGB8(16, 16, 64));

    SPR_show(1, TILE_SPRITES_0, 1, 80, 112, 1);
    SPR_show(2, TILE_SPRITES_1, 1, 152, 112, 1);
    SPR_show(3, TILE_SPRITES_2, 1, 200, 112, 1);

    {
        static const uint16_t group_tiles[] = {
            TILE_SPRITES_0,
            TILE_SPRITES_1,
            TILE_SPRITES_3,
        };
        SPR_groupShow(10, 3, 1, group_tiles, 1, 100, 180);
    }

    ANIM_init(0, &ANIM_IDLE, 20, 2);
    ANIM_show(0, 160, 200);
    ANIM_play(0, ANIM_PINGPONG);

    bounce_x = 80;
    bounce_dx = 1;

    SYS_vblankFlush();
}

void game_tick(void) {
    SYS_kickWatchdog();

    bounce_x += bounce_dx;
    if (bounce_x > 290 || bounce_x < 16)
        bounce_dx = -bounce_dx;

    SPR_move(1, bounce_x, 112);

    ANIM_update();

    SYS_vblankFlush();
}
