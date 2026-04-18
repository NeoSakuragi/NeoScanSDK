#include <neoscan.h>
#include "palette.h"
#include "tiles.h"
#include "anim_palette.h"
#include "anim_idle.h"
#include "sounds.h"

#define NUM_PALETTES 8
static const char *PAL_NAMES[NUM_PALETTES] = {
    "RED", "BLUE", "CYAN", "BLACK", "YELLOW", "GREEN", "PURPLE", "PINK"
};

/* Jacket replacement colors: dark / main / bright for each palette */
static const uint16_t JACKET_COLORS[NUM_PALETTES][3] = {
    { 0, 0, 0 },                                          /* red = original */
    { RGB8(0, 8, 66), RGB8(0, 0, 132), RGB8(0, 16, 173) },  /* blue */
    { RGB8(0, 66, 82), RGB8(0, 120, 148), RGB8(0, 173, 200) }, /* cyan */
    { RGB8(16, 16, 16), RGB8(40, 40, 40), RGB8(70, 70, 70) }, /* black */
    { RGB8(100, 80, 0), RGB8(180, 150, 0), RGB8(220, 200, 0) }, /* yellow */
    { RGB8(0, 66, 8), RGB8(0, 132, 0), RGB8(16, 173, 0) },  /* green */
    { RGB8(50, 0, 66), RGB8(100, 0, 132), RGB8(140, 0, 173) }, /* purple */
    { RGB8(132, 0, 80), RGB8(200, 40, 120), RGB8(240, 100, 160) }, /* pink */
};

static uint8_t cur_palette;

static int16_t terry_x;
static int16_t terry_y;
static int16_t bounce_x;
static int8_t  bounce_dx;
static uint8_t shrink_y;

static void apply_jacket_palette(uint8_t idx) {
    uint16_t pal[16];
    uint8_t i;
    for (i = 0; i < 16; i++)
        pal[i] = ANIM_PALETTE[i];
    if (idx > 0) {
        pal[4] = JACKET_COLORS[idx][0];
        pal[7] = JACKET_COLORS[idx][1];
        pal[9] = JACKET_COLORS[idx][2];
    }
    PAL_setPalette(3, pal);
}

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
    cur_palette = 1;
    apply_jacket_palette(cur_palette);
    PAL_setBackdrop(RGB8(16, 16, 64));

    FIX_clear();
    FIX_print(14, 2, "NEOSCAN SDK", 0);
    FIX_print(2, 26, "LR:MOVE UD:PAL A/B:ZOOM C/D:SFX", 0);

    SPR_show(1, TILE_SPRITES_0, 1, 80, 30, 1);
    SPR_show(2, TILE_SPRITES_1, 1, 152, 30, 1);
    SPR_show(3, TILE_SPRITES_2, 1, 200, 30, 1);

    ANIM_init(0, &ANIM_IDLE, 20, 2);
    ANIM_init(1, &ANIM_IDLE, 30, 3);
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
    MUS_play();
}

void game_tick(void) {
    uint8_t col;

    SYS_kickWatchdog();

    if (JOY_held(0) & JOY_LEFT)   terry_x -= 2;
    if (JOY_held(0) & JOY_RIGHT)  terry_x += 2;

    if (JOY_pressed(0) & JOY_UP) {
        cur_palette = (cur_palette + 1 < NUM_PALETTES) ? cur_palette + 1 : 0;
        apply_jacket_palette(cur_palette);
    }
    if (JOY_pressed(0) & JOY_DOWN) {
        cur_palette = (cur_palette > 0) ? cur_palette - 1 : NUM_PALETTES - 1;
        apply_jacket_palette(cur_palette);
    }

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

    if (JOY_pressed(0) & JOY_START)
        MUS_stop();

    for (col = 0; col < ANIM_IDLE.width; col++) {
        SPR_setZoom(20 + col, shrink_y);
        SPR_setZoom(30 + col, shrink_y);
    }

    FIX_print(1, 24, "ZOOM:     ", 0);
    FIX_printNum(6, 24, shrink_y, 0);
    FIX_print(1, 25, "PAL:        ", 0);
    FIX_print(5, 25, PAL_NAMES[cur_palette], 0);

    ANIM_setPosition(0, terry_x, terry_y);
    ANIM_setPosition(1, terry_x - 70, terry_y);

    bounce_x += bounce_dx;
    if (bounce_x > 290 || bounce_x < 16)
        bounce_dx = -bounce_dx;
    SPR_move(1, bounce_x, 30);

    ANIM_update();

    SYS_vblankFlush();
}
