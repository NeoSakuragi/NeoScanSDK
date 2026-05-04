#include <neoscan.h>
#include "resources.h"

/* --- KOF96 Sound Commands (v0.1 driver) --- */
static const uint8_t TRACK_CMDS[] = {
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
    0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E,
    0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
    0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D,
};
#define NUM_TRACKS (sizeof(TRACK_CMDS) / sizeof(TRACK_CMDS[0]))

static uint16_t sfx_cmd;
static uint8_t sfx_chan;
static const uint8_t SFX_CHANNELS[] = { 0x1A, 0x1C, 0x1D };
#define NUM_SFX_CHAN 3

static uint8_t cur_track;
static uint8_t playing;

/* --- Menu --- */
#define MENU_TRACK    0
#define MENU_SFX_CHAN  1
#define MENU_SFX      2
#define MENU_ANIM_P1  3
#define MENU_ANIM_P2  4
#define MENU_PAL_P1   5
#define MENU_PAL_P2   6
#define MENU_XPOS     7
#define MENU_YPOS     8
#define MENU_ZOOM     9
#define MENU_COUNT    10

static const char *MENU_LABELS[MENU_COUNT] = {
    "TRACK  ", "SFX CH ", "SFX    ",
    "ANIM P1", "ANIM P2",
    "PAL P1 ", "PAL P2 ", "X-POS  ", "Y-POS  ", "ZOOM   "
};

static uint8_t menu_sel;
static uint8_t blink_timer;
static uint8_t menu_dirty;

/* --- Animations --- */
#define NUM_ANIMS 2
static const anim_def_t *ANIMS[NUM_ANIMS] = {
    &ANIM_TERRY_IDLE, &ANIM_TERRY_WALK
};
static const char *ANIM_NAMES[NUM_ANIMS] = {
    "IDLE  ", "WALK  "
};
static uint8_t anim_p1;
static uint8_t anim_p2;

/* --- Palettes --- */
#define NUM_PALETTES 8
static const char *PAL_NAMES[NUM_PALETTES] = {
    "RED   ", "BLUE  ", "CYAN  ", "BLACK ", "YELLOW", "GREEN ", "PURPLE", "PINK  "
};
static const uint16_t JACKET_COLORS[NUM_PALETTES][3] = {
    { 0, 0, 0 },
    { RGB8(0, 8, 66), RGB8(0, 0, 132), RGB8(0, 16, 173) },
    { RGB8(0, 66, 82), RGB8(0, 120, 148), RGB8(0, 173, 200) },
    { RGB8(16, 16, 16), RGB8(40, 40, 40), RGB8(70, 70, 70) },
    { RGB8(100, 80, 0), RGB8(180, 150, 0), RGB8(220, 200, 0) },
    { RGB8(0, 66, 8), RGB8(0, 132, 0), RGB8(16, 173, 0) },
    { RGB8(50, 0, 66), RGB8(100, 0, 132), RGB8(140, 0, 173) },
    { RGB8(132, 0, 80), RGB8(200, 40, 120), RGB8(240, 100, 160) },
};
static uint8_t pal_p1;
static uint8_t pal_p2;

static const uint16_t TEXT_PAL[16] = {
    0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
};
static const uint16_t RED_PAL[16] = {
    0x8000, COLOR_RED, RGB(25, 5, 5), RGB(31, 15, 0),
};

/* --- Sprites --- */
static int16_t terry_x;
static int16_t terry_y;
static int16_t bounce_x;
static int8_t  bounce_dx;
static uint8_t shrink_y;

static void apply_palette(uint8_t slot, uint8_t idx) {
    uint16_t pal[16];
    uint8_t i;
    for (i = 0; i < 16; i++)
        pal[i] = ANIM_PALETTE[i];
    if (idx > 0) {
        pal[4] = JACKET_COLORS[idx][0];
        pal[7] = JACKET_COLORS[idx][1];
        pal[9] = JACKET_COLORS[idx][2];
    }
    PAL_setPalette(slot, pal);
}

static const uint8_t ANIM_MODES[NUM_ANIMS] = { ANIM_PINGPONG, ANIM_FORWARD };

static uint8_t prev_width[2];
static uint8_t prev_height[2];

static void set_anim(uint8_t slot, uint8_t anim_idx) {
    uint8_t base = (slot == 0) ? 20 : 30;
    uint8_t pal = (slot == 0) ? 3 : 2;
    uint8_t col, row;
    uint8_t new_w = ANIMS[anim_idx]->width;
    uint8_t new_h = ANIMS[anim_idx]->height;

    for (col = 0; col < prev_width[slot]; col++)
        SPR_hide(base + col);

    for (col = 0; col < prev_width[slot] && col < new_w; col++)
        for (row = new_h; row < prev_height[slot]; row++)
            SPR_setTile(base + col, row, 0, 0, 0, 0);

    for (col = new_w; col < prev_width[slot]; col++)
        for (row = 0; row < prev_height[slot]; row++)
            SPR_setTile(base + col, row, 0, 0, 0, 0);

    ANIM_init(slot, ANIMS[anim_idx], base, pal);
    if (slot == 1) ANIM_setFlip(1, 1);
    if (slot == 0)
        ANIM_show(0, terry_x, terry_y);
    else
        ANIM_show(1, terry_x - 70, terry_y);
    ANIM_play(slot, ANIM_MODES[anim_idx]);
    prev_width[slot] = new_w;
    prev_height[slot] = new_h;
}

static void print_hex(uint8_t col, uint8_t row, uint8_t val, uint8_t pal) {
    static const char HEX[] = "0123456789ABCDEF";
    char buf[5];
    buf[0] = '0'; buf[1] = 'x';
    buf[2] = HEX[(val >> 4) & 0xF];
    buf[3] = HEX[val & 0xF];
    buf[4] = 0;
    FIX_print(col, row, buf, pal);
}

static void draw_menu(void) {
    uint8_t i;
    uint8_t prev_blink = (blink_timer >> 3) & 1;
    blink_timer++;
    uint8_t blink_on = (blink_timer >> 3) & 1;

    if (!menu_dirty && prev_blink == blink_on)
        return;

    FIX_print(1, 1, "HELLO NEO  KOF96 SND", 0);

    for (i = 0; i < MENU_COUNT; i++) {
        uint8_t row = 2 + i;
        uint8_t sel = (i == menu_sel);
        uint8_t pal = (sel && blink_on) ? 4 : 0;

        FIX_print(1, row, sel ? ">" : " ", pal);
        FIX_print(2, row, MENU_LABELS[i], pal);

        if (i == MENU_TRACK) {
            print_hex(10, row, TRACK_CMDS[cur_track], pal);
            FIX_print(15, row, playing ? "PLAY" : "STOP", playing ? 4 : 0);
        } else if (i == MENU_SFX_CHAN) {
            print_hex(10, row, SFX_CHANNELS[sfx_chan], pal);
        } else if (i == MENU_SFX) {
            print_hex(10, row, sfx_cmd, pal);
        } else if (i == MENU_ANIM_P1)
            FIX_print(10, row, ANIM_NAMES[anim_p1], 0);
        else if (i == MENU_ANIM_P2)
            FIX_print(10, row, ANIM_NAMES[anim_p2], 0);
        else if (i == MENU_PAL_P1)
            FIX_print(10, row, PAL_NAMES[pal_p1], 0);
        else if (i == MENU_PAL_P2)
            FIX_print(10, row, PAL_NAMES[pal_p2], 0);
        else if (i == MENU_XPOS) {
            FIX_printNum(10, row, terry_x, 0);
            FIX_print(16, row, "    ", 0);
        } else if (i == MENU_YPOS) {
            FIX_printNum(10, row, terry_y, 0);
            FIX_print(16, row, "    ", 0);
        } else if (i == MENU_ZOOM) {
            FIX_printNum(10, row, shrink_y, 0);
            FIX_print(14, row, "      ", 0);
        }
    }

    menu_dirty = 0;
}

void game_init(void) {
    PAL_setPalette(0, TEXT_PAL);
    PAL_setPalette(1, TILES_PALETTE);
    PAL_setPalette(4, RED_PAL);

    pal_p1 = 0;
    pal_p2 = 1;
    apply_palette(3, pal_p1);
    apply_palette(2, pal_p2);
    PAL_setBackdrop(RGB8(16, 16, 64));

    FIX_clear();

    SPR_show(1, TILES_SPRITES_0, 1, 80, 30, 1);
    SPR_show(2, TILES_SPRITES_1, 1, 152, 30, 1);
    SPR_show(3, TILES_SPRITES_2, 1, 200, 30, 1);

    terry_x = 160;
    terry_y = 200;
    shrink_y = 0xFF;

    anim_p1 = 0;
    anim_p2 = 0;
    set_anim(0, anim_p1);
    set_anim(1, anim_p2);

    bounce_x = 80;
    bounce_dx = 1;

    menu_sel = 0;
    cur_track = 0;
    playing = 0;
    menu_dirty = 1;

    SND_init();

    SYS_vblankFlush();
}

void game_tick(void) {
    uint8_t col;
    uint16_t pressed = JOY_pressed(0);
    uint16_t held = JOY_held(0);

    SYS_kickWatchdog();
    SND_update();

    if (pressed & JOY_UP) {
        menu_sel = (menu_sel > 0) ? menu_sel - 1 : MENU_COUNT - 1;
        menu_dirty = 1;
    }
    if (pressed & JOY_DOWN) {
        menu_sel = (menu_sel + 1 < MENU_COUNT) ? menu_sel + 1 : 0;
        menu_dirty = 1;
    }

    switch (menu_sel) {
    case MENU_TRACK:
        if (pressed & JOY_RIGHT) { cur_track = (cur_track + 1 < NUM_TRACKS) ? cur_track + 1 : 0; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { cur_track = (cur_track > 0) ? cur_track - 1 : NUM_TRACKS - 1; menu_dirty = 1; }
        if (pressed & JOY_A)     { SND_play(TRACK_CMDS[cur_track]); playing = 1; menu_dirty = 1; }
        break;

    case MENU_SFX_CHAN:
        if (pressed & JOY_RIGHT) { sfx_chan = (sfx_chan + 1 < NUM_SFX_CHAN) ? sfx_chan + 1 : 0; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { sfx_chan = (sfx_chan > 0) ? sfx_chan - 1 : NUM_SFX_CHAN - 1; menu_dirty = 1; }
        break;

    case MENU_SFX:
        if (pressed & JOY_RIGHT) { sfx_cmd++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { sfx_cmd--; menu_dirty = 1; }
        if (pressed & JOY_A)     { SND_play2(SFX_CHANNELS[sfx_chan], sfx_cmd); }
        break;

    case MENU_ANIM_P1:
        if (pressed & JOY_RIGHT) { anim_p1 = (anim_p1 + 1 < NUM_ANIMS) ? anim_p1 + 1 : 0; set_anim(0, anim_p1); menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { anim_p1 = (anim_p1 > 0) ? anim_p1 - 1 : NUM_ANIMS - 1; set_anim(0, anim_p1); menu_dirty = 1; }
        break;

    case MENU_ANIM_P2:
        if (pressed & JOY_RIGHT) { anim_p2 = (anim_p2 + 1 < NUM_ANIMS) ? anim_p2 + 1 : 0; set_anim(1, anim_p2); menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { anim_p2 = (anim_p2 > 0) ? anim_p2 - 1 : NUM_ANIMS - 1; set_anim(1, anim_p2); menu_dirty = 1; }
        break;

    case MENU_PAL_P1:
        if (pressed & JOY_RIGHT) { pal_p1 = (pal_p1 + 1 < NUM_PALETTES) ? pal_p1 + 1 : 0; apply_palette(3, pal_p1); menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { pal_p1 = (pal_p1 > 0) ? pal_p1 - 1 : NUM_PALETTES - 1; apply_palette(3, pal_p1); menu_dirty = 1; }
        break;

    case MENU_PAL_P2:
        if (pressed & JOY_RIGHT) { pal_p2 = (pal_p2 + 1 < NUM_PALETTES) ? pal_p2 + 1 : 0; apply_palette(2, pal_p2); menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { pal_p2 = (pal_p2 > 0) ? pal_p2 - 1 : NUM_PALETTES - 1; apply_palette(2, pal_p2); menu_dirty = 1; }
        break;

    case MENU_XPOS:
        if (held & JOY_RIGHT) { terry_x += 2; menu_dirty = 1; }
        if (held & JOY_LEFT)  { terry_x -= 2; menu_dirty = 1; }
        break;

    case MENU_YPOS:
        if (held & JOY_RIGHT) { terry_y += 2; menu_dirty = 1; }
        if (held & JOY_LEFT)  { terry_y -= 2; menu_dirty = 1; }
        break;

    case MENU_ZOOM:
        if (held & JOY_RIGHT) { if (shrink_y < 0xFF) { shrink_y++; menu_dirty = 1; } }
        if (held & JOY_LEFT)  { if (shrink_y > 1)    { shrink_y--; menu_dirty = 1; } }
        break;
    }

    if (pressed & JOY_B) {
        SND_stop();
        SND_init();
        playing = 0;
        menu_dirty = 1;
    }

    for (col = 0; col < ANIMS[anim_p1]->width; col++)
        SPR_setZoom(20 + col, shrink_y);
    for (col = 0; col < ANIMS[anim_p2]->width; col++)
        SPR_setZoom(30 + col, shrink_y);

    ANIM_setPosition(0, terry_x, terry_y);
    ANIM_setPosition(1, terry_x - 70, terry_y);

    bounce_x += bounce_dx;
    if (bounce_x > 290 || bounce_x < 16)
        bounce_dx = -bounce_dx;
    SPR_move(1, bounce_x, 30);

    ANIM_update();
    draw_menu();
    SYS_vblankFlush();
}
