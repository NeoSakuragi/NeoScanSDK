/* Sound commands to the Z80 driver (KOF98's M ROM): one byte per frame through REG_SOUND ($320000), the pace KOF98
 * itself keeps. Sequences seen in KOF98 (tools/brawler/sound_tap.lua): sound effect = $1A then the code; voice =
 * $1C then the code; boot = $07 (music unlock). */
#ifndef SOUND_H
#define SOUND_H
#include <stdint.h>
void snd_cmd(uint8_t b);                 /* queue one byte */
void snd_tick(void);                     /* once a frame: send the next queued byte */
extern volatile uint8_t snd_test;
void snd_sfx(uint8_t code);              /* $1A + code, skipped when the queue already lags (hit storms) */
void snd_music(uint8_t track);           /* KOF98 tracks $21-$3F (most loop; $2C, $24 are short) */
/* KOF98 codes (measured in MAME, hits on Yuri): swing $1E light (A, C) / $1F heavy (B, D, C+D);
 * hit $11 A, $12 B, $13 C, $14 D, $15 C+D blowback */
enum { SFX_SWING_LIGHT = 0x1E, SFX_SWING_HEAVY = 0x1F, SFX_HIT_A = 0x11, SFX_HIT_B = 0x12, SFX_HIT_C = 0x13,
       SFX_HIT_D = 0x14, SFX_HIT_CD = 0x15 };
enum { MUS_SELECT = 0x21, MUS_FIGHT = 0x27, MUS_JINGLE = 0x2C };   /* $27: FF3's Terry stage theme (tools/port) */   /* placeholders until Bruno picks */        /* test hook: a byte poked here (capture POKE) is queued, then cleared */
#endif
