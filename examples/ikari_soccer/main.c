#include <neoscan.h>
#include "resources.h"

/* --- Player states --- */
#define STATE_IDLE   0
#define STATE_RUN    1
#define STATE_PASS   2
#define STATE_SHOOT  3
#define STATE_WOBBLE 4

/* --- 8 directions --- */
#define DIR_DOWN      0
#define DIR_DOWNRIGHT 1
#define DIR_RIGHT     2
#define DIR_UPRIGHT   3
#define DIR_UP        4
#define DIR_UPLEFT    5
#define DIR_LEFT      6
#define DIR_DOWNLEFT  7

/* Direction → rendered angle index (5 angles, rest are flipped) */
static const uint8_t DIR_TO_ANGLE[] = {
    ANGLE_DOWN, ANGLE_DOWNRIGHT, ANGLE_RIGHT, ANGLE_UPRIGHT, ANGLE_UP,
    ANGLE_UPRIGHT, ANGLE_RIGHT, ANGLE_DOWNRIGHT
};
static const uint8_t DIR_TO_FLIP[] = { 0, 0, 0, 0, 0, 1, 1, 1 };

/* Movement vectors per direction */
static const int8_t DIR_DX[] = {  0,  1,  2,  1,  0, -1, -2, -1 };
static const int8_t DIR_DY[] = {  2,  1,  0, -1, -2, -1,  0,  1 };

/* Joystick direction bits → direction enum (-1 = no input) */
/* Index = RIGHT:LEFT:DOWN:UP as bits 3:2:1:0 */
static const int8_t JOY_TO_DIR[16] = {
    -1,            /* 0000 */
    DIR_UP,        /* 0001 UP */
    DIR_DOWN,      /* 0010 DOWN */
    -1,            /* 0011 */
    DIR_LEFT,      /* 0100 LEFT */
    DIR_UPLEFT,    /* 0101 UP+LEFT */
    DIR_DOWNLEFT,  /* 0110 DOWN+LEFT */
    -1,            /* 0111 */
    DIR_RIGHT,     /* 1000 RIGHT */
    DIR_UPRIGHT,   /* 1001 UP+RIGHT */
    DIR_DOWNRIGHT, /* 1010 DOWN+RIGHT */
    -1, -1, -1, -1, -1
};

/* State → animation index */
static const uint8_t STATE_TO_ANIM[] = {
    ALEX_ANIM_IDLE, ALEX_ANIM_RUN, ALEX_ANIM_PASS,
    ALEX_ANIM_SHOOT, ALEX_ANIM_WOBBLE
};

/* Anim play modes per state */
static const uint8_t STATE_ANIM_MODE[] = {
    ANIM_PINGPONG,  /* IDLE */
    ANIM_FORWARD,   /* RUN */
    ANIM_ONCE,      /* PASS */
    ANIM_ONCE,      /* SHOOT */
    ANIM_ONCE,      /* WOBBLE */
};

static const char *STATE_NAMES[] = {
    "IDLE  ", "RUN   ", "PASS  ", "SHOOT ", "WOBBLE"
};

/* --- Player --- */
static uint8_t player_state;
static uint8_t player_dir;
static int16_t player_x;
static int16_t player_y;

static uint8_t cur_anim;
static uint8_t cur_angle;
static uint8_t cur_flip;

static const uint16_t TEXT_PAL[16] = {
    0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
};

static void set_player_anim(uint8_t anim_idx, uint8_t angle, uint8_t flip) {
    uint8_t same_anim = (anim_idx == cur_anim);
    uint8_t need_reinit = (!same_anim || angle != cur_angle);
    uint8_t need_reflip = (flip != cur_flip);

    if (!need_reinit && !need_reflip)
        return;

    if (need_reinit) {
        uint8_t saved_frame = 0;
        if (same_anim)
            saved_frame = ANIM_getFrame(0);

        ANIM_init(0, ALEX_ANIMS[anim_idx][angle], 1, 1);

        if (same_anim)
            ANIM_setFrame(0, saved_frame);

        ANIM_setFlip(0, flip);
        ANIM_show(0, player_x, player_y);
        ANIM_play(0, STATE_ANIM_MODE[player_state]);
        ANIM_setSpeed(0, 5);
    } else {
        ANIM_setFlip(0, flip);
    }

    cur_anim = anim_idx;
    cur_angle = angle;
    cur_flip = flip;
}

void game_init(void) {
    PAL_setPalette(0, TEXT_PAL);
    PAL_setPalette(1, ALEX_PALETTE);
    PAL_setBackdrop(RGB8(32, 80, 32));
    FIX_clear();

    player_state = STATE_IDLE;
    player_dir = DIR_DOWN;
    player_x = 160;
    player_y = 160;

    cur_anim = 0xFF;
    cur_angle = 0xFF;
    cur_flip = 0xFF;

    set_player_anim(ALEX_ANIM_IDLE, ANGLE_DOWN, 0);

    FIX_print(1, 1, "IKARI SOCCER", 0);
    FIX_print(1, 27, "A:PASS B:WOBBLE C:SHOOT", 2);

    SYS_vblankFlush();
}

void game_tick(void) {
    uint16_t held = JOY_held(0);
    uint16_t pressed = JOY_pressed(0);
    uint8_t dir_bits = held & JOY_DIR_MASK;
    int8_t joy_dir = JOY_TO_DIR[dir_bits];
    uint8_t anim, angle, flip;

    SYS_kickWatchdog();
    ANIM_update();

    switch (player_state) {
    case STATE_IDLE:
    case STATE_RUN:
        if (pressed & JOY_A) {
            player_state = STATE_PASS;
        } else if (pressed & JOY_B) {
            player_state = STATE_WOBBLE;
        } else if (pressed & JOY_C) {
            player_state = STATE_SHOOT;
        } else if (joy_dir >= 0) {
            player_dir = (uint8_t)joy_dir;
            player_state = STATE_RUN;
            player_x += DIR_DX[player_dir];
            player_y += DIR_DY[player_dir];
        } else {
            player_state = STATE_IDLE;
        }
        break;

    case STATE_PASS:
    case STATE_SHOOT:
    case STATE_WOBBLE:
        if (!ANIM_isPlaying(0))
            player_state = STATE_IDLE;
        break;
    }

    anim = STATE_TO_ANIM[player_state];
    angle = DIR_TO_ANGLE[player_dir];
    flip = DIR_TO_FLIP[player_dir];
    set_player_anim(anim, angle, flip);

    ANIM_setPosition(0, player_x, player_y);

    FIX_print(16, 1, STATE_NAMES[player_state], 0);

    SYS_vblankFlush();
}
