#ifndef NEO_SOUND_H
#define NEO_SOUND_H

#include "neo_types.h"

#define SND_STOP_ALL  0x40

void SND_play(uint8_t sample_id);
void SND_stopAll(void);

#endif
