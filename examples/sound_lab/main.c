#include <neoscan.h>
#include "resources.h"

/* === SOUND LAB — KOF96 Instrument Kit === */

/*
 * NeoSynth command protocol:
 *   $01         Init/reset
 *   $03         Stop all
 *   $08 + val   Set parameter (two NMIs: $08 then value)
 *   $10+ch      FM key-on ch (0-3), note from param
 *   $14+ch      FM key-off ch (0-3)
 *   $18+ch      FM set patch ch (0-3), patch from param
 *   $20+ch      SSG key-on ch (0-2), note from param
 *   $24+ch      SSG key-off ch (0-2)
 *   $28+ch      SSG set patch ch (0-2), preset from param (0-4)
 *   $30+ch      FM pan ch (0-3), param: 0=L 1=C 2=R
 *   $34+ch      ADPCM-A pan ch (0-5), param: 0=L 1=C 2=R
 *   $40         ADPCM-B play (sample from param)
 *   $41         ADPCM-B stop
 *   $50+N       Play song N (sequencer)
 *   $C0+smp     ADPCM-A trigger sample
 */

#define CMD_INIT       0x01
#define CMD_STOP       0x03
#define CMD_SET_PARAM  0x08
#define CMD_FM_ON      0x10
#define CMD_FM_OFF     0x14
#define CMD_FM_PATCH   0x18
#define CMD_SSG_ON     0x20
#define CMD_SSG_OFF    0x24
#define CMD_SSG_PATCH  0x28
#define CMD_FM_PAN     0x30
#define CMD_ADPCMA_PAN 0x34
#define CMD_ADPCMB_ON  0x40
#define CMD_ADPCMB_OFF 0x41
#define CMD_PLAY_SONG  0x50
#define CMD_ADPCMA     0xC0

/* Simple command queue for multi-frame sequences */
#define CMD_QUEUE_SIZE 8
static uint8_t cmd_queue[CMD_QUEUE_SIZE];
static uint8_t cmd_queue_head;
static uint8_t cmd_queue_tail;

static void cmd_enqueue(uint8_t cmd) {
    uint8_t next = (cmd_queue_head + 1) & (CMD_QUEUE_SIZE - 1);
    if (next != cmd_queue_tail) {
        cmd_queue[cmd_queue_head] = cmd;
        cmd_queue_head = next;
    }
}

static void cmd_flush(void) {
    /* Send one queued command per frame via SND_play */
    if (cmd_queue_tail != cmd_queue_head) {
        SND_play(cmd_queue[cmd_queue_tail]);
        cmd_queue_tail = (cmd_queue_tail + 1) & (CMD_QUEUE_SIZE - 1);
    }
}

/* Send a parameterized command: $08, param_val, action_cmd (3 frames) */
static void cmd_param_action(uint8_t param_val, uint8_t action_cmd) {
    cmd_enqueue(CMD_SET_PARAM);
    cmd_enqueue(param_val);
    cmd_enqueue(action_cmd);
}

/* ---- FM patch names (must match neosynth_build.py FM_PATCHES order) ---- */
#define FM_PATCH_COUNT 20

static const char *FM_PATCH_NAMES[FM_PATCH_COUNT] = {
    "SINE    ",  /*  0 */
    "ORGAN   ",  /*  1 */
    "BRASS   ",  /*  2 */
    "PIANO   ",  /*  3 */
    "KOF LEAD",  /*  4 */
    "KOF STR ",  /*  5 */
    "KOF PERC",  /*  6 */
    "KOF PAD ",  /*  7 */
    "KOF HARD",  /*  8 */
    "KOF ORCH",  /*  9 */
    "KOF SINE",  /* 10 */
    "KOF POWR",  /* 11 */
    "KOF BASS",  /* 12 */
    "KOF DIST",  /* 13 */
    "KOF NASL",  /* 14 */
    "KOF DHVY",  /* 15 */
    "KOF RICH",  /* 16 */
    "KOF GTR ",  /* 17 */
    "KOF BELL",  /* 18 */
    "KOF KEYS",  /* 19 */
};

/* ---- SSG preset names (must match neosynth_build.py SSG_PRESETS order) ---- */
#define SSG_PATCH_COUNT 5

static const char *SSG_PATCH_NAMES[SSG_PATCH_COUNT] = {
    "SQUARE",  /* 0 */
    "PLUCK ",  /* 1 */
    "BELL  ",  /* 2 */
    "NOISE ",  /* 3 */
    "BUZZ  ",  /* 4 */
};

/* ---- Instrument names for the KOF96 ADPCM-A kit ---- */
#define INST_COUNT SND_COUNT

static const char *INST_NAMES[INST_COUNT] = {
    "KICK HVY",   /*  0 */
    "KICK DEP",   /*  1 */
    "SNARE TI",   /*  2 */
    "SNARE MI",   /*  3 */
    "HH CLOS ",   /*  4 */
    "HH OPEN ",   /*  5 */
    "CRASH   ",   /*  6 */
    "BASS LOW",   /*  7 */
    "BASS PLK",   /*  8 */
    "BASS MID",   /*  9 */
    "PERC TOM",   /* 10 */
    "PERC HIT",   /* 11 */
    "GUITAR  ",   /* 12 */
    "MELODIC ",   /* 13 */
    "BRASS HI",   /* 14 */
    "BRASS ST",   /* 15 */
    "VOCAL   ",   /* 16 */
    "IMPACT  ",   /* 17 */
    "WHOOSH  ",   /* 18 */
};

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

/* Auto-test mode: fires sound commands on a timer, no input needed */
static uint16_t auto_frame;
static const char *auto_status = "";

/* Per-menu state */
static uint16_t init_preset;
static uint16_t fm_patch[4];
static uint16_t fm_note[4];
static uint16_t ssg_note[3];
static uint16_t ssg_patch[3];
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
    FIX_print(1, 2, "KOF96 INSTRUMENTS", 0);

    for (i = 0; i < MENU_COUNT; i++) {
        uint8_t row = 4 + i;
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
            if (fm_patch[ch] < FM_PATCH_COUNT) {
                FIX_print(11, row, FM_PATCH_NAMES[fm_patch[ch]], pal);
            } else {
                FIX_print(11, row, "P", pal);
                print_hex(12, row, fm_patch[ch], pal);
            }
            print_note(20, row, fm_note[ch], pal);
            break;
        }
        case MENU_SSG1: case MENU_SSG2: case MENU_SSG3: {
            uint8_t ch = i - MENU_SSG1;
            if (ssg_patch[ch] < SSG_PATCH_COUNT) {
                FIX_print(11, row, SSG_PATCH_NAMES[ssg_patch[ch]], pal);
            }
            print_note(18, row, ssg_note[ch], pal);
            break;
        }
        case MENU_ADPCMA:
            /* Show instrument name instead of just a number */
            if (adpcma_smp < INST_COUNT) {
                FIX_print(11, row, INST_NAMES[adpcma_smp], pal);
            } else {
                FIX_print(11, row, "S", pal);
                FIX_printNum(12, row, adpcma_smp, pal);
                FIX_print(17, row, "   ", pal);
            }
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

    FIX_print(1, 18, "A=PLAY  B=STOP  L/R=VALUE", 0);
    FIX_print(1, 19, "C=CYCLE PATCH(FM/SSG)", 0);

    /* Auto-test status line */
    FIX_print(1, 21, "AUTO:                     ", 1);
    FIX_print(7, 21, auto_status, 1);
    FIX_print(1, 22, "FRAME:      ", 0);
    FIX_printNum(8, 22, auto_frame, 0);

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
    ssg_patch[0] = ssg_patch[1] = ssg_patch[2] = 0; /* default: SQUARE */
    adpcma_ch = 0;
    adpcma_smp = 0;  /* Start at KICK */
    pan_val = 1; /* center */

    /* Init queue */
    cmd_queue_head = 0;
    cmd_queue_tail = 0;

    SND_init();
    SYS_vblankFlush();
}

void game_tick(void) {
    uint16_t pressed = JOY_pressed(0);
    (void)0;

    SYS_kickWatchdog();

    /* Send any pending SND_play2 second byte */
    SND_update();

    /* Flush one queued command per frame */
    cmd_flush();

    auto_frame++;


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
        if (pressed & JOY_RIGHT) { fm_note[ch]++; if (fm_note[ch] > 95) fm_note[ch] = 95; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { if (fm_note[ch] > 0) fm_note[ch]--; menu_dirty = 1; }
        if (pressed & JOY_A) {
            /* Set note param, then FM key-on */
            cmd_param_action((uint8_t)fm_note[ch], CMD_FM_ON + ch);
        }
        if (pressed & JOY_B) {
            /* FM key-off */
            SND_play(CMD_FM_OFF + ch);
        }
        if (pressed & JOY_C) {
            /* Cycle through all 20 FM patches */
            fm_patch[ch] = fm_patch[ch] + 1;
            if (fm_patch[ch] >= FM_PATCH_COUNT) fm_patch[ch] = 0;
            cmd_param_action((uint8_t)fm_patch[ch], CMD_FM_PATCH + ch);
            menu_dirty = 1;
        }
        break;
    }

    case MENU_SSG1: case MENU_SSG2: case MENU_SSG3: {
        uint8_t ch = menu_sel - MENU_SSG1;
        if (pressed & JOY_RIGHT) { ssg_note[ch]++; if (ssg_note[ch] > 95) ssg_note[ch] = 95; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { if (ssg_note[ch] > 0) ssg_note[ch]--; menu_dirty = 1; }
        if (pressed & JOY_A) {
            /* Set note param, then SSG key-on */
            cmd_param_action((uint8_t)ssg_note[ch], CMD_SSG_ON + ch);
        }
        if (pressed & JOY_B) {
            /* SSG key-off */
            SND_play(CMD_SSG_OFF + ch);
        }
        if (pressed & JOY_C) {
            /* Cycle through SSG presets */
            ssg_patch[ch] = ssg_patch[ch] + 1;
            if (ssg_patch[ch] >= SSG_PATCH_COUNT) ssg_patch[ch] = 0;
            cmd_param_action((uint8_t)ssg_patch[ch], CMD_SSG_PATCH + ch);
            menu_dirty = 1;
        }
        break;
    }

    case MENU_ADPCMA:
        if (pressed & JOY_RIGHT) {
            adpcma_smp++;
            if (adpcma_smp >= INST_COUNT) adpcma_smp = 0;
            menu_dirty = 1;
        }
        if (pressed & JOY_LEFT) {
            if (adpcma_smp > 0) adpcma_smp--;
            else adpcma_smp = INST_COUNT - 1;
            menu_dirty = 1;
        }
        if (pressed & JOY_A) {
            /* Trigger ADPCM-A sample (0-based index) */
            cmd_param_action(adpcma_smp & 0xFF, CMD_ADPCMA);
        }
        if (pressed & JOY_B) {
            /* Stop all ADPCM-A */
            SND_play(CMD_STOP);
        }
        break;

    case MENU_ADPCMB:
        if (pressed & JOY_RIGHT) { adpcmb_smp++; if (adpcmb_smp > 18) adpcmb_smp = 0; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { if (adpcmb_smp > 0) adpcmb_smp--; else adpcmb_smp = 18; menu_dirty = 1; }
        if (pressed & JOY_A) {
            /* Set sample param, then ADPCM-B play */
            cmd_param_action((uint8_t)adpcmb_smp, CMD_ADPCMB_ON);
        }
        if (pressed & JOY_B) {
            SND_play(CMD_ADPCMB_OFF);
        }
        break;

    case MENU_MUSIC:
        if (pressed & JOY_RIGHT) { music_song = (music_song < 2) ? music_song + 1 : 0; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { music_song = (music_song > 0) ? music_song - 1 : 2; menu_dirty = 1; }
        if (pressed & JOY_A) {
            /* Play song N via sequencer */
            SND_play(CMD_PLAY_SONG + (music_song & 0x0F));
        }
        if (pressed & JOY_B) {
            SND_play(CMD_STOP);
            menu_dirty = 1;
        }
        break;

    case MENU_PAN:
        if (pressed & JOY_RIGHT) { pan_val = (pan_val < 2) ? pan_val + 1 : 0; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { pan_val = (pan_val > 0) ? pan_val - 1 : 2; menu_dirty = 1; }
        if (pressed & JOY_A) {
            /* Set pan value param, then send FM pan for ch0 */
            cmd_param_action((uint8_t)pan_val, CMD_FM_PAN + 0);
        }
        break;
    }

    draw_menu();
    SYS_vblankFlush();
}
