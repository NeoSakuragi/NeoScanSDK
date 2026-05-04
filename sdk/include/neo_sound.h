#ifndef NEO_SOUND_H
#define NEO_SOUND_H

#include "neo_types.h"
#include "neo_hw.h"

#define SND_CMD_UNLOCK  0x07
#define SND_CMD_STOP    0x03

static inline void SND_init(void) {
    REG_SOUND = SND_CMD_UNLOCK;
}

static inline void SND_play(uint8_t cmd) {
    REG_SOUND = cmd;
}

extern volatile uint8_t _snd_pending;
extern volatile uint8_t _snd_has_pending;

static inline void SND_play2(uint8_t cmd1, uint8_t cmd2) {
    REG_SOUND = cmd1;
    _snd_pending = cmd2;
    _snd_has_pending = 1;
}

static inline void SND_update(void) {
    if (_snd_has_pending) {
        REG_SOUND = _snd_pending;
        _snd_has_pending = 0;
    }
}

static inline void SND_stop(void) {
    REG_SOUND = SND_CMD_STOP;
}

#endif
