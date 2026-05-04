#include <neoscan.h>
#include "resources.h"

/* KOF95 sound driver (SNK MAKOTO v3.0) */
#define SND_INIT  0x01
#define SND_STOP  0x03

/* BGM commands — browse with left/right */
static const uint8_t BGM_CMDS[] = {
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
    0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F,
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37,
};
#define NUM_TRACKS (sizeof(BGM_CMDS) / sizeof(BGM_CMDS[0]))

/* SFX/voice commands */
static const uint8_t SFX_CMDS[] = {
    0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67,
    0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F,
    0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77,
};
#define NUM_SFX (sizeof(SFX_CMDS) / sizeof(SFX_CMDS[0]))

#define MENU_TRACK 0
#define MENU_SFX   1
#define MENU_COUNT 2

static uint8_t menu_sel;
static uint8_t blink_timer;
static uint8_t menu_dirty;
static uint8_t cur_track;
static uint8_t cur_sfx;
static uint8_t playing;
static uint8_t init_delay;

static const uint16_t TEXT_PAL[16] = {
    0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
};
static const uint16_t HI_PAL[16] = {
    0x8000, COLOR_RED, RGB(25, 5, 5), RGB(31, 15, 0),
};

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
    uint8_t prev_blink = (blink_timer >> 3) & 1;
    blink_timer++;
    uint8_t blink_on = (blink_timer >> 3) & 1;

    if (!menu_dirty && prev_blink == blink_on)
        return;

    FIX_print(2, 1, "NEOSCAN JUKEBOX", 0);
    FIX_print(2, 2, "KOF95 SOUND DRIVER", 0);
    FIX_print(2, 3, "A=PLAY B=STOP", 0);

    uint8_t i;
    for (i = 0; i < MENU_COUNT; i++) {
        uint8_t row = 5 + i * 2;
        uint8_t sel = (i == menu_sel);
        uint8_t pal = (sel && blink_on) ? 1 : 0;

        FIX_print(2, row, sel ? ">" : " ", pal);

        if (i == MENU_TRACK) {
            FIX_print(4, row, "TRACK ", pal);
            print_hex(10, row, BGM_CMDS[cur_track], pal);
            FIX_print(16, row, playing ? "PLAY" : "STOP", playing ? 1 : 0);
        } else if (i == MENU_SFX) {
            FIX_print(4, row, "SFX   ", pal);
            print_hex(10, row, SFX_CMDS[cur_sfx], pal);
            FIX_print(16, row, "      ", 0);
        }
    }

    menu_dirty = 0;
}

void game_init(void) {
    PAL_setPalette(0, TEXT_PAL);
    PAL_setPalette(1, HI_PAL);
    PAL_setBackdrop(RGB8(0, 0, 32));
    FIX_clear();

    menu_sel = 0;
    cur_track = 0;
    cur_sfx = 0;
    playing = 0;
    init_delay = 10;
    menu_dirty = 1;

    SYS_vblankFlush();
}

void game_tick(void) {
    uint16_t pressed = JOY_pressed(0);

    SYS_kickWatchdog();

    if (init_delay > 0) {
        init_delay--;
        if (init_delay == 0) {
            /* Try a sweep of commands to find what works */
            REG_SOUND = 0x03; /* stop first */
        }
    }
    /* Auto-sweep: send a new command every 120 frames */
    {
        static uint8_t sweep_cmd = 0x20;
        static uint16_t sweep_timer = 180;
        if (sweep_timer > 0) {
            sweep_timer--;
        } else {
            REG_SOUND = sweep_cmd;
            cur_track = sweep_cmd - 0x20;
            playing = 1;
            menu_dirty = 1;
            sweep_cmd++;
            if (sweep_cmd > 0x40) sweep_cmd = 0x20;
            sweep_timer = 120;
        }
    }

    if (pressed & JOY_UP)   { menu_sel = (menu_sel > 0) ? menu_sel - 1 : MENU_COUNT - 1; menu_dirty = 1; }
    if (pressed & JOY_DOWN) { menu_sel = (menu_sel + 1 < MENU_COUNT) ? menu_sel + 1 : 0; menu_dirty = 1; }

    if (pressed & JOY_RIGHT) {
        menu_dirty = 1;
        if (menu_sel == MENU_TRACK) cur_track = (cur_track + 1 < NUM_TRACKS) ? cur_track + 1 : 0;
        if (menu_sel == MENU_SFX)   cur_sfx = (cur_sfx + 1 < NUM_SFX) ? cur_sfx + 1 : 0;
    }
    if (pressed & JOY_LEFT) {
        menu_dirty = 1;
        if (menu_sel == MENU_TRACK) cur_track = (cur_track > 0) ? cur_track - 1 : NUM_TRACKS - 1;
        if (menu_sel == MENU_SFX)   cur_sfx = (cur_sfx > 0) ? cur_sfx - 1 : NUM_SFX - 1;
    }

    if (pressed & JOY_A) {
        menu_dirty = 1;
        if (menu_sel == MENU_TRACK) { REG_SOUND = BGM_CMDS[cur_track]; playing = 1; }
        if (menu_sel == MENU_SFX)   REG_SOUND = SFX_CMDS[cur_sfx];
    }

    if (pressed & JOY_B) {
        REG_SOUND = SND_STOP;
        playing = 0;
        menu_dirty = 1;
    }

    draw_menu();
    SYS_vblankFlush();
}
