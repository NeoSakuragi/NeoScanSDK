#include "neo_hw.h"
#include "neo_sound.h"

void SND_play(uint8_t sample_id) {
    REG_SOUND = sample_id;
}

void SND_stopAll(void) {
    REG_SOUND = SND_STOP_ALL;
}

void MUS_play(void) {
    REG_SOUND = MUS_CMD_PLAY;
}

void MUS_stop(void) {
    REG_SOUND = MUS_CMD_STOP;
}
