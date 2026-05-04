#include <neoscan.h>
#include "resources.h"

/* --- Player states --- */
#define STATE_IDLE   0
#define STATE_RUN    1
#define STATE_PASS   2
#define STATE_SHOOT  3
#define STATE_WOBBLE 4
#define STATE_WAIT   5

/* --- 8 directions --- */
#define DIR_DOWN      0
#define DIR_DOWNRIGHT 1
#define DIR_RIGHT     2
#define DIR_UPRIGHT   3
#define DIR_UP        4
#define DIR_UPLEFT    5
#define DIR_LEFT      6
#define DIR_DOWNLEFT  7

static const uint8_t DIR_TO_ANGLE[] = {
    ANGLE_DOWN, ANGLE_DOWNRIGHT, ANGLE_RIGHT, ANGLE_UPRIGHT, ANGLE_UP,
    ANGLE_UPRIGHT, ANGLE_RIGHT, ANGLE_DOWNRIGHT
};
static const uint8_t DIR_TO_FLIP[] = { 0, 0, 0, 0, 0, 1, 1, 1 };

static const int8_t DIR_DX[] = {  0,  1,  2,  1,  0, -1, -2, -1 };
static const int8_t DIR_DY[] = {  2,  1,  0, -1, -2, -1,  0,  1 };

/* --- Players --- */
#define NUM_PLAYERS        7
#define SPRITES_PER_PLAYER 6

#define FIELD_X_MIN  40
#define FIELD_X_MAX  280
#define FIELD_Y_MIN  60
#define FIELD_Y_MAX  200
#define ARRIVE_DIST  6

typedef struct {
    int16_t  x, y;
    int16_t  target_x, target_y;
    uint8_t  dir;
    uint8_t  state;
    uint8_t  anim_slot;
    uint8_t  pal_slot;
    uint16_t first_sprite;
    uint16_t wait_timer;
    uint8_t  cur_anim;
    uint8_t  cur_angle;
    uint8_t  cur_flip;
    uint16_t rng;
} player_t;

static player_t players[NUM_PLAYERS];
static uint8_t  sort_order[NUM_PLAYERS];
static uint8_t  init_count;

/* --- Per-player RNG (16-bit LFSR, maximal taps 0,1,3,12) --- */
static uint16_t prand(player_t *p) {
    uint16_t bit = ((p->rng >> 0) ^ (p->rng >> 1) ^ (p->rng >> 3) ^ (p->rng >> 12)) & 1;
    p->rng = (p->rng >> 1) | (bit << 15);
    return p->rng;
}

static int16_t prand_range(player_t *p, int16_t lo, int16_t hi) {
    return lo + (int16_t)(prand(p) % (uint16_t)(hi - lo + 1));
}

/* --- Palette setup --- */
#define JERSEY_IDX_COUNT 6
static const uint8_t JERSEY_IDX[JERSEY_IDX_COUNT] = { 5, 6, 8, 9, 10, 11 };

static const uint16_t TEAM_JERSEYS[NUM_PLAYERS][JERSEY_IDX_COUNT] = {
    /* RED (original) */
    { 0x3D33, 0x7733, 0x4F00, 0x4F00, 0x0F00, 0x0700 },
    /* BLUE */
    { RGB8(50,50,210), RGB8(40,40,120), RGB8(0,0,255), RGB8(0,0,255), RGB8(0,0,240), RGB8(0,0,110) },
    /* GREEN */
    { RGB8(50,200,50), RGB8(40,120,40), RGB8(0,230,0), RGB8(0,240,0), RGB8(0,220,0), RGB8(0,100,0) },
    /* PURPLE */
    { RGB8(140,50,200), RGB8(80,30,120), RGB8(160,0,255), RGB8(150,0,240), RGB8(140,0,220), RGB8(70,0,110) },
    /* PINK */
    { RGB8(220,80,160), RGB8(140,50,100), RGB8(255,60,180), RGB8(255,50,170), RGB8(240,40,160), RGB8(130,0,80) },
    /* CYAN */
    { RGB8(50,200,210), RGB8(40,120,125), RGB8(0,240,255), RGB8(0,255,255), RGB8(0,220,240), RGB8(0,100,110) },
    /* WHITE */
    { RGB8(180,180,190), RGB8(110,110,120), RGB8(240,240,250), RGB8(255,255,255), RGB8(220,220,230), RGB8(90,90,100) },
};

static void setup_palettes(void) {
    uint8_t p, j;
    uint16_t pal[16];
    for (p = 0; p < NUM_PLAYERS; p++) {
        for (j = 0; j < 16; j++)
            pal[j] = ALEX_PALETTE[j];
        for (j = 0; j < JERSEY_IDX_COUNT; j++)
            pal[JERSEY_IDX[j]] = TEAM_JERSEYS[p][j];
        PAL_setPalette(p + 1, pal);
    }
}

/* Joystick direction bits → direction enum (-1 = no input) */
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

static const uint8_t STATE_ANIM_MODE[] = {
    ANIM_PINGPONG,  /* IDLE */
    ANIM_FORWARD,   /* RUN */
    ANIM_ONCE,      /* PASS */
    ANIM_ONCE,      /* SHOOT */
    ANIM_ONCE,      /* WOBBLE */
    ANIM_PINGPONG,  /* WAIT (AI idle) */
};

static const uint8_t STATE_TO_ANIM[] = {
    ALEX_ANIM_IDLE, ALEX_ANIM_RUN, ALEX_ANIM_PASS,
    ALEX_ANIM_SHOOT, ALEX_ANIM_WOBBLE, ALEX_ANIM_IDLE
};

/* --- Direction from delta --- */
/* Diagonal until one axis is close, then pure cardinal. */
static uint8_t dir_from_delta(int16_t dx, int16_t dy) {
    int16_t ax = dx < 0 ? -dx : dx;
    int16_t ay = dy < 0 ? -dy : dy;

    if (ax <= ARRIVE_DIST)
        return dy > 0 ? DIR_DOWN : DIR_UP;
    if (ay <= ARRIVE_DIST)
        return dx > 0 ? DIR_RIGHT : DIR_LEFT;
    if (dx > 0)
        return dy > 0 ? DIR_DOWNRIGHT : DIR_UPRIGHT;
    return dy > 0 ? DIR_DOWNLEFT : DIR_UPLEFT;
}

/* --- Player animation control --- */
static void player_set_anim(player_t *p, uint8_t anim_id) {
    uint8_t angle = DIR_TO_ANGLE[p->dir];
    uint8_t flip  = DIR_TO_FLIP[p->dir];

    if (anim_id == p->cur_anim && angle == p->cur_angle && flip == p->cur_flip)
        return;

    if (anim_id != p->cur_anim || angle != p->cur_angle) {
        uint8_t saved = 0;
        if (anim_id == p->cur_anim)
            saved = ANIM_getFrame(p->anim_slot);

        ANIM_init(p->anim_slot, ALEX_ANIMS[anim_id][angle],
                  p->first_sprite, p->pal_slot);

        if (anim_id == p->cur_anim)
            ANIM_setFrame(p->anim_slot, saved);

        ANIM_setFlip(p->anim_slot, flip);
        ANIM_show(p->anim_slot, p->x, p->y);
        ANIM_play(p->anim_slot, STATE_ANIM_MODE[p->state]);
        ANIM_setSpeed(p->anim_slot, 5);
    } else {
        ANIM_setFlip(p->anim_slot, flip);
    }

    p->cur_anim  = anim_id;
    p->cur_angle = angle;
    p->cur_flip  = flip;
}

/* --- Init / Tick --- */
static const uint16_t TEXT_PAL[16] = {
    0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0),
};

static void init_player(uint8_t i) {
    player_t *p = &players[i];
    p->x = 60 + (i % 4) * 55;
    p->y = 70 + (i / 4) * 70;
    p->dir = i & 7;
    p->anim_slot = i;
    p->pal_slot = i + 1;
    p->first_sprite = 1 + i * SPRITES_PER_PLAYER;
    p->cur_anim = 0xFF;
    p->cur_angle = 0xFF;
    p->cur_flip = 0xFF;
    p->rng = 0xACE1 + (uint16_t)i * 7919;

    if (i == 0) {
        p->state = STATE_IDLE;
        player_set_anim(p, ALEX_ANIM_IDLE);
    } else {
        p->target_x = prand_range(p, FIELD_X_MIN, FIELD_X_MAX);
        p->target_y = prand_range(p, FIELD_Y_MIN, FIELD_Y_MAX);
        p->state = STATE_RUN;
        player_set_anim(p, ALEX_ANIM_RUN);
    }
}

void game_init(void) {
    PAL_setPalette(0, TEXT_PAL);
    setup_palettes();
    PAL_setBackdrop(RGB8(16, 50, 16));
    FIX_clear();
    FIX_print(1, 1, "IKARI SOCCER", 0);
    FIX_print(1, 27, "A:PASS B:WOBBLE C:SHOOT", 2);

    init_count = 0;
    SYS_vblankFlush();
}

static void update_human(player_t *p) {
    uint16_t held = JOY_held(0);
    uint16_t pressed = JOY_pressed(0);
    uint8_t dir_bits = held & JOY_DIR_MASK;
    int8_t joy_dir = JOY_TO_DIR[dir_bits];

    switch (p->state) {
    case STATE_IDLE:
    case STATE_RUN:
        if (pressed & JOY_A) {
            p->state = STATE_PASS;
        } else if (pressed & JOY_B) {
            p->state = STATE_WOBBLE;
        } else if (pressed & JOY_C) {
            p->state = STATE_SHOOT;
        } else if (joy_dir >= 0) {
            p->dir = (uint8_t)joy_dir;
            p->state = STATE_RUN;
            p->x += DIR_DX[p->dir];
            p->y += DIR_DY[p->dir];
        } else {
            p->state = STATE_IDLE;
        }
        break;

    case STATE_PASS:
    case STATE_SHOOT:
    case STATE_WOBBLE:
        if (!ANIM_isPlaying(p->anim_slot))
            p->state = STATE_IDLE;
        break;
    }

    player_set_anim(p, STATE_TO_ANIM[p->state]);
}

static void update_ai(player_t *p) {
    switch (p->state) {
    case STATE_RUN: {
        int16_t dx = p->target_x - p->x;
        int16_t dy = p->target_y - p->y;
        int16_t ax = dx < 0 ? -dx : dx;
        int16_t ay = dy < 0 ? -dy : dy;

        if (ax <= ARRIVE_DIST && ay <= ARRIVE_DIST) {
            p->state = STATE_WAIT;
            p->wait_timer = prand_range(p, 30, 150);
            player_set_anim(p, ALEX_ANIM_IDLE);
        } else {
            p->dir = dir_from_delta(dx, dy);
            p->x += DIR_DX[p->dir];
            p->y += DIR_DY[p->dir];
            player_set_anim(p, ALEX_ANIM_RUN);
        }
        break;
    }

    case STATE_WAIT:
        if (p->wait_timer > 0) {
            p->wait_timer--;
        } else {
            p->target_x = prand_range(p, FIELD_X_MIN, FIELD_X_MAX);
            p->target_y = prand_range(p, FIELD_Y_MIN, FIELD_Y_MAX);
            p->state = STATE_RUN;
            p->dir = dir_from_delta(p->target_x - p->x,
                                     p->target_y - p->y);
            player_set_anim(p, ALEX_ANIM_RUN);
        }
        break;
    }
}

static void player_reshow(player_t *p) {
    uint8_t frame = ANIM_getFrame(p->anim_slot);
    ANIM_init(p->anim_slot, ALEX_ANIMS[p->cur_anim][p->cur_angle],
              p->first_sprite, p->pal_slot);
    ANIM_setFrame(p->anim_slot, frame);
    ANIM_setFlip(p->anim_slot, p->cur_flip);
    ANIM_show(p->anim_slot, p->x, p->y);
    ANIM_play(p->anim_slot, STATE_ANIM_MODE[p->state]);
    ANIM_setSpeed(p->anim_slot, 5);
}

static void sort_by_y(void) {
    uint8_t i;
    for (i = 0; i < NUM_PLAYERS - 1; i++) {
        uint8_t a = sort_order[i];
        uint8_t b = sort_order[i + 1];
        if (players[a].y > players[b].y) {
            uint16_t tmp;
            sort_order[i] = b;
            sort_order[i + 1] = a;
            tmp = players[a].first_sprite;
            players[a].first_sprite = players[b].first_sprite;
            players[b].first_sprite = tmp;
            player_reshow(&players[a]);
            player_reshow(&players[b]);
        }
    }
}

void game_tick(void) {
    uint8_t i;

    SYS_kickWatchdog();

    if (init_count < NUM_PLAYERS) {
        sort_order[init_count] = init_count;
        init_player(init_count);
        init_count++;
        SYS_vblankFlush();
        return;
    }

    ANIM_update();

    update_human(&players[0]);
    for (i = 1; i < NUM_PLAYERS; i++)
        update_ai(&players[i]);

    for (i = 0; i < NUM_PLAYERS; i++)
        ANIM_setPosition(players[i].anim_slot, players[i].x, players[i].y);

    sort_by_y();

    SYS_vblankFlush();
}
