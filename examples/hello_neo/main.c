#include <neoscan.h>
#include "palette.h"
#include "tiles.h"

static int16_t bounce_x;
static int8_t  bounce_dx;

void game_init(void) {
    neo_palette_set(1, PALETTE);
    neo_palette_set_backdrop(NEO_RGB8(16, 16, 64));

    /* Single 16x16 sprite: "N" letter, bouncing */
    neo_sprite_show(1, TILE_SPRITES_0, 1, 80, 112, 1);

    /* Heart at fixed position */
    neo_sprite_show(2, TILE_SPRITES_1, 1, 152, 112, 1);

    /* Arrow at fixed position */
    neo_sprite_show(3, TILE_SPRITES_2, 1, 200, 112, 1);

    /* Sprite group: 3 columns x 1 row (N + heart + star side by side) */
    {
        static const uint16_t group_tiles[] = {
            TILE_SPRITES_0,
            TILE_SPRITES_1,
            TILE_SPRITES_3,
        };
        neo_sprite_group_show(10, 3, 1, group_tiles, 1, 100, 180);
    }

    bounce_x = 80;
    bounce_dx = 1;

    neo_vblank_flush();
}

void game_tick(void) {
    neo_kick_watchdog();

    bounce_x += bounce_dx;
    if (bounce_x > 290 || bounce_x < 16)
        bounce_dx = -bounce_dx;

    neo_sprite_move(1, bounce_x, 112);
    neo_vblank_flush();
}
