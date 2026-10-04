#include <neoscan.h>

/*
 * SoccerFury M1 ROM Sound Player
 *
 * Navigates through all sound commands in the SoccerFury M1 ROM
 * using the v1.7 driver. Uses the original ROM as-is — the
 * 68K just sends command bytes and the Z80 handles everything.
 *
 * Commands in the SoccerFury ROM:
 *   0x20-0x56  Music tracks (51 slots, 6 with data + 3 banked songs)
 *   0xC0-0xFF  SFX (64 slots)
 *   0x65,0x70-0x73,0x7A,0x7F  ADPCM-B samples (7 slots)
 *   0x03       Stop all
 */

#define CMD_STOP  0x03

/* All sound commands to browse */
static const uint8_t MUSIC_CMDS[] = {
    0x25, 0x30, 0x31, 0x32, 0x3A, 0x3F,  /* songs with data in fixed ROM */
    0x20, 0x21, 0x22, 0x23, 0x24,         /* may trigger banked songs */
    0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F,
    0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3B, 0x3C, 0x3D, 0x3E,
    0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4A, 0x4B, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56,
};
#define NUM_MUSIC (sizeof(MUSIC_CMDS) / sizeof(MUSIC_CMDS[0]))

static const uint8_t SFX_CMDS[] = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
    0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF,
    0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7,
    0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF,
    0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
    0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF,
    0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7,
    0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF,
};
#define NUM_SFX (sizeof(SFX_CMDS) / sizeof(SFX_CMDS[0]))

static const uint8_t ADPCMB_CMDS[] = {
    0x65, 0x70, 0x71, 0x72, 0x73, 0x7A, 0x7F,
};
#define NUM_ADPCMB (sizeof(ADPCMB_CMDS) / sizeof(ADPCMB_CMDS[0]))

/* Menu state */
#define MODE_MUSIC   0
#define MODE_SFX     1
#define MODE_ADPCMB  2
#define NUM_MODES    3

static uint8_t mode;
static uint8_t music_idx;
static uint8_t sfx_idx;
static uint8_t adpcmb_idx;
static uint8_t playing;
static uint8_t blink;

static const uint16_t TEXT_PAL[16] = {
    0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
};
static const uint16_t HI_PAL[16] = {
    0x8000, RGB(31, 20, 0), RGB(31, 10, 0), RGB(31, 31, 0),
};
static const uint16_t DIM_PAL[16] = {
    0x8000, RGB(12, 12, 18), RGB(8, 8, 12), RGB(20, 20, 8),
};

static void print_hex(uint8_t col, uint8_t row, uint8_t val, uint8_t pal) {
    static const char HEX[] = "0123456789ABCDEF";
    char buf[5];
    buf[0] = '0';
    buf[1] = 'x';
    buf[2] = HEX[(val >> 4) & 0xF];
    buf[3] = HEX[val & 0xF];
    buf[4] = 0;
    FIX_print(col, row, buf, pal);
}

static uint8_t get_current_cmd(void) {
    if (mode == MODE_MUSIC)  return MUSIC_CMDS[music_idx];
    if (mode == MODE_SFX)    return SFX_CMDS[sfx_idx];
    return ADPCMB_CMDS[adpcmb_idx];
}

static uint8_t get_max_idx(void) {
    if (mode == MODE_MUSIC)  return NUM_MUSIC - 1;
    if (mode == MODE_SFX)    return NUM_SFX - 1;
    return NUM_ADPCMB - 1;
}

static uint8_t *get_idx_ptr(void) {
    if (mode == MODE_MUSIC)  return &music_idx;
    if (mode == MODE_SFX)    return &sfx_idx;
    return &adpcmb_idx;
}

static void draw_screen(void) {
    uint8_t row = 3;
    uint8_t blink_on = (blink >> 4) & 1;

    FIX_print(2, 1, "SOCCERFURY  M1  SOUND  PLAYER", 0);
    FIX_print(2, 2, "SNK Sound Driver v1.7", 2);

    /* Mode tabs */
    FIX_print(2, row, "MUSIC", mode == MODE_MUSIC ? 1 : 2);
    FIX_print(9, row, "SFX", mode == MODE_SFX ? 1 : 2);
    FIX_print(14, row, "ADPCM-B", mode == MODE_ADPCMB ? 1 : 2);

    row = 5;

    /* Current command */
    FIX_print(2, row, "COMMAND:", 0);
    print_hex(12, row, get_current_cmd(), blink_on ? 1 : 0);

    row = 7;

    /* Index */
    FIX_print(2, row, "INDEX:", 0);
    FIX_printNum(12, row, *get_idx_ptr(), 0);
    FIX_print(16, row, "/", 2);
    FIX_printNum(17, row, get_max_idx(), 2);
    FIX_print(21, row, "   ", 0);

    row = 9;

    /* Status */
    FIX_print(2, row, "STATUS:", 0);
    if (playing)
        FIX_print(12, row, "PLAYING ", 1);
    else
        FIX_print(12, row, "STOPPED ", 2);

    /* Controls */
    row = 12;
    FIX_print(2, row,     "LEFT/RIGHT  BROWSE SOUNDS", 2);
    FIX_print(2, row + 1, "UP/DOWN     CHANGE MODE", 2);
    FIX_print(2, row + 2, "A           PLAY", 2);
    FIX_print(2, row + 3, "B           STOP", 2);

    row = 18;
    FIX_print(2, row,     "51 MUSIC  64 SFX  7 ADPCM-B", 2);
    FIX_print(2, row + 1, "3 FULL SONGS IN BANKS 1-3", 2);
}

void game_init(void) {
    PAL_setPalette(0, TEXT_PAL);
    PAL_setPalette(1, HI_PAL);
    PAL_setPalette(2, DIM_PAL);
    PAL_setBackdrop(RGB8(8, 8, 24));
    FIX_clear();

    mode = MODE_MUSIC;
    music_idx = 0;
    sfx_idx = 0;
    adpcmb_idx = 0;
    playing = 0;
    blink = 0;

    draw_screen();
    SYS_vblankFlush();
}

void game_tick(void) {
    uint16_t pressed = JOY_pressed(0);
    uint8_t *idx = get_idx_ptr();
    uint8_t max = get_max_idx();

    SYS_kickWatchdog();
    blink++;

    if (pressed & JOY_RIGHT) {
        *idx = (*idx < max) ? *idx + 1 : 0;
    }
    if (pressed & JOY_LEFT) {
        *idx = (*idx > 0) ? *idx - 1 : max;
    }
    if (pressed & JOY_DOWN) {
        mode = (mode + 1 < NUM_MODES) ? mode + 1 : 0;
    }
    if (pressed & JOY_UP) {
        mode = (mode > 0) ? mode - 1 : NUM_MODES - 1;
    }

    /* A = play current command */
    if (pressed & JOY_A) {
        REG_SOUND = get_current_cmd();
        playing = 1;
    }

    /* B = stop */
    if (pressed & JOY_B) {
        REG_SOUND = CMD_STOP;
        playing = 0;
    }

    draw_screen();
    SYS_vblankFlush();
}
