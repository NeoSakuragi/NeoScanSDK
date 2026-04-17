#include "neo_hw.h"
#include "neo_sound.h"

void SND_play(uint8_t sample_id) {
    REG_SOUND = sample_id;
}

void SND_stopAll(void) {
    REG_SOUND = SND_STOP_ALL;
}
