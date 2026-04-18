#ifndef NEO_SOUND_H
#define NEO_SOUND_H

#include "neo_types.h"

#define SND_STOP_ALL  0x40
#define MUS_CMD_PLAY  0x80
#define MUS_CMD_STOP  0x81
#define VOX_CMD_BASE  0x90
#define VOX_CMD_STOP  0xC0

void SND_play(uint8_t sample_id);
void SND_stopAll(void);
void MUS_play(uint8_t track);
void MUS_stop(void);
void VOX_play(uint8_t voice_id);
void VOX_stop(void);

#endif
