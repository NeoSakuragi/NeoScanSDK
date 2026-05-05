#include <neoscan.h>

/* === SOUND LAB — NeoSynth Driver Test Console === */

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
    FIX_print(1, 18, "START=CYCLE FM PATCH", 0);

    /* Auto-test status line */
    FIX_print(1, 20, "AUTO:                     ", 1);
    FIX_print(7, 20, auto_status, 1);
    FIX_print(1, 21, "FRAME:      ", 0);
    FIX_printNum(8, 21, auto_frame, 0);

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

    /* === Auto-test sequence (no user input needed) === */
    /* Each sound event spaced ~150 frames (2.5s), total ~3000 frames */
    auto_frame++;

    switch (auto_frame) {
    /* -- ADPCM-A tests (direct trigger, no param needed) -- */
    case 100:
        SND_play(CMD_ADPCMA + 0);
        auto_status = "ADPCM-A smp 0";
        menu_dirty = 1;
        break;
    case 250:
        SND_play(CMD_ADPCMA + 1);
        auto_status = "ADPCM-A smp 1";
        menu_dirty = 1;
        break;
    case 400:
        SND_play(CMD_ADPCMA + 4);
        auto_status = "ADPCM-A smp 4";
        menu_dirty = 1;
        break;
    case 500:
        SND_play(CMD_STOP);
        auto_status = "STOP ALL";
        menu_dirty = 1;
        break;

    /* -- FM Ch1: C4 (MIDI 48) -- */
    case 550:
        SND_play2(CMD_SET_PARAM, 48);
        auto_status = "FM param C4";
        menu_dirty = 1;
        break;
    case 553:
        SND_play(CMD_FM_ON + 0);
        auto_status = "FM ch0 C4 ~262Hz";
        menu_dirty = 1;
        break;
    case 700:
        SND_play(CMD_FM_OFF + 0);
        auto_status = "FM ch0 off";
        menu_dirty = 1;
        break;

    /* -- FM Ch1: E4 (MIDI 52) -- */
    case 750:
        SND_play2(CMD_SET_PARAM, 52);
        auto_status = "FM param E4";
        menu_dirty = 1;
        break;
    case 753:
        SND_play(CMD_FM_ON + 0);
        auto_status = "FM ch0 E4 ~330Hz";
        menu_dirty = 1;
        break;
    case 900:
        SND_play(CMD_FM_OFF + 0);
        auto_status = "FM ch0 off";
        menu_dirty = 1;
        break;

    /* -- FM Ch1: G4 (MIDI 55) -- */
    case 950:
        SND_play2(CMD_SET_PARAM, 55);
        auto_status = "FM param G4";
        menu_dirty = 1;
        break;
    case 953:
        SND_play(CMD_FM_ON + 0);
        auto_status = "FM ch0 G4 ~392Hz";
        menu_dirty = 1;
        break;
    case 1100:
        SND_play(CMD_FM_OFF + 0);
        auto_status = "FM ch0 off";
        menu_dirty = 1;
        break;

    /* -- FM Ch2: C3 bass (MIDI 36) -- */
    case 1150:
        SND_play2(CMD_SET_PARAM, 36);
        auto_status = "FM param C3";
        menu_dirty = 1;
        break;
    case 1153:
        SND_play(CMD_FM_ON + 1);
        auto_status = "FM ch1 C3 ~131Hz";
        menu_dirty = 1;
        break;
    case 1300:
        SND_play(CMD_FM_OFF + 1);
        auto_status = "FM ch1 off";
        menu_dirty = 1;
        break;

    /* -- SSG Ch1: C5 (MIDI 60) -- */
    case 1350:
        SND_play2(CMD_SET_PARAM, 60);
        auto_status = "SSG param C5";
        menu_dirty = 1;
        break;
    case 1353:
        SND_play(CMD_SSG_ON + 0);
        auto_status = "SSG ch0 C5 ~523Hz";
        menu_dirty = 1;
        break;
    case 1500:
        SND_play(CMD_SSG_OFF + 0);
        auto_status = "SSG ch0 off";
        menu_dirty = 1;
        break;

    /* -- SSG Ch1: E5 (MIDI 64) -- */
    case 1550:
        SND_play2(CMD_SET_PARAM, 64);
        auto_status = "SSG param E5";
        menu_dirty = 1;
        break;
    case 1553:
        SND_play(CMD_SSG_ON + 0);
        auto_status = "SSG ch0 E5 ~659Hz";
        menu_dirty = 1;
        break;
    case 1700:
        SND_play(CMD_SSG_OFF + 0);
        auto_status = "SSG ch0 off";
        menu_dirty = 1;
        break;

    /* -- SSG Ch1: G5 (MIDI 67) -- */
    case 1750:
        SND_play2(CMD_SET_PARAM, 67);
        auto_status = "SSG param G5";
        menu_dirty = 1;
        break;
    case 1753:
        SND_play(CMD_SSG_ON + 0);
        auto_status = "SSG ch0 G5 ~784Hz";
        menu_dirty = 1;
        break;
    case 1900:
        SND_play(CMD_SSG_OFF + 0);
        auto_status = "SSG ch0 off";
        menu_dirty = 1;
        break;

    /* -- SSG Ch2: A4 sustained (MIDI 57) -- */
    case 1950:
        SND_play2(CMD_SET_PARAM, 57);
        auto_status = "SSG param A4";
        menu_dirty = 1;
        break;
    case 1953:
        SND_play(CMD_SSG_ON + 1);
        auto_status = "SSG ch1 A4 ~440Hz";
        menu_dirty = 1;
        break;
    case 2200:
        SND_play(CMD_SSG_OFF + 1);
        auto_status = "SSG ch1 off";
        menu_dirty = 1;
        break;

    /* -- FM with organ patch (patch 1) -- */
    case 2250:
        SND_play2(CMD_SET_PARAM, 1);
        auto_status = "FM set patch organ";
        menu_dirty = 1;
        break;
    case 2253:
        SND_play(CMD_FM_PATCH + 0);
        auto_status = "FM ch0 patch=organ";
        menu_dirty = 1;
        break;
    case 2260:
        SND_play2(CMD_SET_PARAM, 48);
        auto_status = "FM organ C4";
        menu_dirty = 1;
        break;
    case 2263:
        SND_play(CMD_FM_ON + 0);
        auto_status = "FM ch0 organ C4";
        menu_dirty = 1;
        break;
    case 2400:
        SND_play(CMD_FM_OFF + 0);
        auto_status = "FM ch0 off";
        menu_dirty = 1;
        break;

    /* -- FM with brass patch (patch 2) -- */
    case 2450:
        SND_play2(CMD_SET_PARAM, 2);
        auto_status = "FM set patch brass";
        menu_dirty = 1;
        break;
    case 2453:
        SND_play(CMD_FM_PATCH + 0);
        auto_status = "FM ch0 patch=brass";
        menu_dirty = 1;
        break;
    case 2460:
        SND_play2(CMD_SET_PARAM, 55);
        auto_status = "FM brass G4";
        menu_dirty = 1;
        break;
    case 2463:
        SND_play(CMD_FM_ON + 0);
        auto_status = "FM ch0 brass G4";
        menu_dirty = 1;
        break;
    case 2600:
        SND_play(CMD_FM_OFF + 0);
        auto_status = "FM ch0 off";
        menu_dirty = 1;
        break;

    /* -- Final stop before music test -- */
    case 2700:
        SND_play(CMD_STOP);
        auto_status = "STOP (pre-music)";
        menu_dirty = 1;
        break;

    /* -- MUSIC: Play song 2 (Guile's Theme) FIRST -- */
    case 2800:
        SND_play(CMD_PLAY_SONG + 2);
        auto_status = "GUILE THEME";
        menu_dirty = 1;
        break;

    /* -- Let Guile's Theme play ~10 seconds (600 frames) -- */
    case 3100:
        auto_status = "GUILE: playing...";
        menu_dirty = 1;
        break;

    /* -- Stop Guile -- */
    case 3400:
        SND_play(CMD_STOP);
        auto_status = "GUILE: stopped";
        menu_dirty = 1;
        break;

    /* -- MUSIC: Play song 0 (C major scale) -- */
    case 3500:
        SND_play(CMD_PLAY_SONG + 0);
        auto_status = "MUSIC: Song 0 play";
        menu_dirty = 1;
        break;

    /* -- Let music play for ~5 seconds (300 frames) -- */
    case 3800:
        auto_status = "MUSIC: playing...";
        menu_dirty = 1;
        break;

    /* -- Stop music -- */
    case 4100:
        SND_play(CMD_STOP);
        auto_status = "MUSIC: stopped";
        menu_dirty = 1;
        break;

    /* -- MUSIC: Play song 1 (chord progression) -- */
    case 4200:
        SND_play(CMD_PLAY_SONG + 1);
        auto_status = "MUSIC: Song 1 play";
        menu_dirty = 1;
        break;

    /* -- Let music play -- */
    case 4500:
        auto_status = "MUSIC: song 1...";
        menu_dirty = 1;
        break;

    /* -- Final stop -- */
    case 4800:
        SND_play(CMD_STOP);
        auto_status = "ALL DONE - SILENCE";
        menu_dirty = 1;
        break;
    }

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
        if (pressed & JOY_START) {
            /* Cycle through FM patches */
            fm_patch[ch] = (fm_patch[ch] + 1) & 0x03;
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
        break;
    }

    case MENU_ADPCMA:
        if (pressed & JOY_RIGHT) { adpcma_smp = (adpcma_smp + 1) & 0x07; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { adpcma_smp = (adpcma_smp > 0) ? adpcma_smp - 1 : 7; menu_dirty = 1; }
        if (pressed & JOY_A) {
            /* ADPCM-A trigger: direct command, no param needed */
            SND_play(CMD_ADPCMA + (adpcma_smp & 0x3F));
        }
        if (pressed & JOY_B) {
            /* Stop all ADPCM-A */
            SND_play(CMD_STOP);
        }
        break;

    case MENU_ADPCMB:
        if (pressed & JOY_RIGHT) { adpcmb_smp = (adpcmb_smp + 1) & 0x07; menu_dirty = 1; }
        if (pressed & JOY_LEFT)  { adpcmb_smp = (adpcmb_smp > 0) ? adpcmb_smp - 1 : 7; menu_dirty = 1; }
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
