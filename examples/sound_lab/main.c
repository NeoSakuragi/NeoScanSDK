#include <neoscan.h>

/* === SOUND LAB — NeoSynth Driver Test Console === */

/* Menu items */
#define MENU_INIT       0
#define MENU_FM1        1
#define MENU_FM2        2
#define MENU_FM3        3
#define MENU_FM4        4
#define MENU_SSG1       5
#define MENU_SSG2       6
#define MENU_SSG3       7
#define MENU_ADPCMA     8
#define MENU_ADPCMB     9
#define MENU_MUSIC      10
#define MENU_PAN        11
#define MENU_COUNT      12

static const char *MENU_LABELS[MENU_COUNT] = {
    "INIT SEQ",
    "FM  CH1 ",
    "FM  CH2 ",
    "FM  CH3 ",
    "FM  CH4 ",
    "SSG CH1 ",
    "SSG CH2 ",
    "SSG CH3 ",
    "ADPCM-A ",
    "ADPCM-B ",
    "MUSIC   ",
    "PAN     ",
};

static uint8_t menu_sel;
static uint8_t menu_dirty;
static uint8_t blink_timer;

/* Per-menu state */
static uint16_t init_preset;
static uint16_t fm_patch[4];
static uint16_t fm_note[4];
static uint16_t ssg_note[3];
static uint16_t adpcma_ch;
static uint16_t adpcma_smp;
static uint16_t adpcmb_smp;
static uint16_t music_song;
static uint16_t pan_ch;
static uint16_t pan_val;

static void print_hex(uint8_t col, uint8_t row, uint8_t val, uint8_t pal) {
    static const char HEX[] = "0123456789ABCDEF";
    char buf[5];
    buf[0] = '0'; buf[1] = 'x';
    buf[2] = HEX[(val >> 4) & 0xF];
    buf[3] = HEX[val & 0xF];
    buf[4] = 0;
    FIX_print(col, row, buf, pal);
}

static const char *NOTE_NAMES[] = {
    "C ","C#","D ","D#","E ","F ","F#","G ","G#","A ","A#","B "
};

static void print_note(uint8_t col, uint8_t row, uint16_t note_val, uint8_t pal) {
    uint8_t n = note_val;
    uint8_t octave = 0;
    while (n >= 12) { n -= 12; octave++; }
    char buf[4];
    buf[0] = NOTE_NAMES[n][0];
    buf[1] = NOTE_NAMES[n][1];
    buf[2] = '0' + octave;
    buf[3] = 0;
    FIX_print(col, row, buf, pal);
}

static void draw_menu(void) {
    uint8_t i;
    uint8_t prev_blink = (blink_timer >> 3) & 1;
    blink_timer++;
    uint8_t blink_on = (blink_timer >> 3) & 1;

    if (!menu_dirty && prev_blink == blink_on)
        return;

    FIX_print(1, 1, "NEOSCAN SOUND LAB", 0);

    for (i = 0; i < MENU_COUNT; i++) {
        uint8_t row = 3 + i;
        uint8_t sel = (i == menu_sel);
        uint8_t pal = (sel && blink_on) ? 1 : 0;

        FIX_print(1, row, sel ? ">" : " ", pal);
        FIX_print(2, row, MENU_LABELS[i], pal);

        switch (i) {
        case MENU_INIT:
            print_hex(11, row, init_preset, pal);
            break;
        case MENU_FM1: case MENU_FM2: case MENU_FM3: case MENU_FM4: {
            uint8_t ch = i - MENU_FM1;
            FIX_print(11, row, "P", pal);
            print_hex(12, row, fm_patch[ch], pal);
            print_note(17, row, fm_note[ch], pal);
            break;
        }
        case MENU_SSG1: case MENU_SSG2: case MENU_SSG3: {
            uint8_t ch = i - MENU_SSG1;
            print_note(11, row, ssg_note[ch], pal);
            break;
        }
        case MENU_ADPCMA:
            FIX_print(11, row, "CH", pal);
            print_hex(13, row, adpcma_ch, pal);
            FIX_print(18, row, "S", pal);
            print_hex(19, row, adpcma_smp, pal);
            break;
        case MENU_ADPCMB:
            FIX_print(11, row, "S", pal);
            print_hex(12, row, adpcmb_smp, pal);
            break;
        case MENU_MUSIC:
            print_hex(11, row, music_song, pal);
            break;
        case MENU_PAN:
            FIX_print(11, row, "CH", pal);
            print_hex(13, row, pan_ch, pal);
            FIX_print(18, row, pan_val == 0 ? "L  " : pan_val == 1 ? "C  " : "R  ", pal);
            break;
        }
    }

    FIX_print(1, 17, "A=PLAY  B=STOP  L/R=VALUE", 0);
    menu_dirty = 0;
}

void game_init(void) {
    static const uint16_t TEXT_PAL[16] = {
        0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
    };
    static const uint16_t SEL_PAL[16] = {
        0x8000, RGB(31, 31, 0), RGB(31, 20, 0), COLOR_RED,
    };

    PAL_setPalette(0, TEXT_PAL);
    PAL_setPalette(1, SEL_PAL);
    PAL_setBackdrop(RGB8(8, 8, 32));
    FIX_clear();

    menu_sel = 0;
    menu_dirty = 1;

    /* Default values */
    init_preset = 0;
    fm_note[0] = fm_note[1] = fm_note[2] = fm_note[3] = 48; /* C4 */
    ssg_note[0] = ssg_note[1] = ssg_note[2] = 48;
    adpcma_ch = 0;
    pan_val = 1; /* center */

    SND_init();
    SYS_vblankFlush();
}

void game_tick(void) {
    uint16_t pressed = JOY_pressed(0);
    (void)0;

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
    case MENU_INIT:
        if (pressed & JOY_RIGHT) { init_preset++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { init_preset--; menu_dirty = 1; }
        if (pressed & JOY_A)     { SND_play(init_preset); }
        break;

    case MENU_FM1: case MENU_FM2: case MENU_FM3: case MENU_FM4: {
        uint8_t ch = menu_sel - MENU_FM1;
        if (pressed & JOY_RIGHT) { fm_note[ch]++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { fm_note[ch]--; menu_dirty = 1; }
        if (pressed & JOY_A)     {
            /* TODO: send FM note command to driver */
        }
        if (pressed & JOY_B)     {
            /* TODO: send FM key-off */
        }
        break;
    }

    case MENU_SSG1: case MENU_SSG2: case MENU_SSG3: {
        uint8_t ch = menu_sel - MENU_SSG1;
        if (pressed & JOY_RIGHT) { ssg_note[ch]++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { ssg_note[ch]--; menu_dirty = 1; }
        if (pressed & JOY_A)     {
            /* TODO: send SSG note command */
        }
        if (pressed & JOY_B)     {
            /* TODO: send SSG key-off */
        }
        break;
    }

    case MENU_ADPCMA:
        if (pressed & JOY_RIGHT) { adpcma_smp++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { adpcma_smp--; menu_dirty = 1; }
        if (pressed & JOY_A)     {
            /* TODO: trigger ADPCM-A sample */
        }
        break;

    case MENU_ADPCMB:
        if (pressed & JOY_RIGHT) { adpcmb_smp++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { adpcmb_smp--; menu_dirty = 1; }
        if (pressed & JOY_A)     {
            /* TODO: trigger ADPCM-B sample */
        }
        break;

    case MENU_MUSIC:
        if (pressed & JOY_RIGHT) { music_song++; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { music_song--; menu_dirty = 1; }
        if (pressed & JOY_A)     {
            /* TODO: play song */
        }
        if (pressed & JOY_B)     {
            SND_stop();
            SND_init();
            menu_dirty = 1;
        }
        break;

    case MENU_PAN:
        if (pressed & JOY_RIGHT) { pan_val = (pan_val < 2) ? pan_val + 1 : 0; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { pan_val = (pan_val > 0) ? pan_val - 1 : 2; menu_dirty = 1; }
        if (pressed & JOY_A)     {
            /* TODO: set panning */
        }
        break;
    }

    if (pressed & JOY_B && menu_sel < MENU_MUSIC) {
        SND_stop();
        SND_init();
        menu_dirty = 1;
    }

    draw_menu();
    SYS_vblankFlush();
}
