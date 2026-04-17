#ifndef NEO_INPUT_H
#define NEO_INPUT_H

#include "neo_types.h"

#define JOY_UP     0x0001
#define JOY_DOWN   0x0002
#define JOY_LEFT   0x0004
#define JOY_RIGHT  0x0008
#define JOY_A      0x0010
#define JOY_B      0x0020
#define JOY_C      0x0040
#define JOY_D      0x0080
#define JOY_START  0x0100
#define JOY_SELECT 0x0200

#define JOY_DIR_MASK  (JOY_UP | JOY_DOWN | JOY_LEFT | JOY_RIGHT)
#define JOY_BTN_MASK  (JOY_A | JOY_B | JOY_C | JOY_D)

extern uint16_t _joy_cur[2];
extern uint16_t _joy_press[2];
extern uint16_t _joy_rel[2];

void JOY_update(void);

static inline uint16_t JOY_held(uint8_t player) {
    return _joy_cur[player];
}

static inline uint16_t JOY_pressed(uint8_t player) {
    return _joy_press[player];
}

static inline uint16_t JOY_released(uint8_t player) {
    return _joy_rel[player];
}

#endif
