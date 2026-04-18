#ifndef NEO_SOUND_H
#define NEO_SOUND_H

#include "neo_types.h"

#define SND_STOP_ALL  0x40
#define MUS_CMD_PLAY  0x80
#define MUS_CMD_STOP  0x81

void SND_play(uint8_t sample_id);
void SND_stopAll(void);
void MUS_play(void);
void MUS_stop(void);

#endif
