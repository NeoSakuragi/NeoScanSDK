#include "neo_hw.h"
#include "neo_sound.h"

void SND_play(uint8_t sample_id) {
    REG_SOUND = sample_id;
}

void SND_stopAll(void) {
    REG_SOUND = SND_STOP_ALL;
}

void MUS_play(uint8_t track) {
    REG_SOUND = MUS_CMD_PLAY + track;
}

void MUS_stop(void) {
    REG_SOUND = MUS_CMD_STOP;
}

void VOX_play(uint8_t voice_id) {
    REG_SOUND = VOX_CMD_BASE + voice_id - 1;
}

void VOX_stop(void) {
    REG_SOUND = VOX_CMD_STOP;
}
