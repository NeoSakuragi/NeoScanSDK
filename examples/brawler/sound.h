/* Sound commands to the Z80 driver (KOF98's M ROM): one byte per frame through REG_SOUND ($320000), the pace KOF98
 * itself keeps. Sequences seen in KOF98 (tools/brawler/sound_tap.lua): sound effect = $1A then the code; voice =
 * $1C then the code; boot = $07 (music unlock). */
#ifndef SOUND_H
#define SOUND_H
#include <stdint.h>
void snd_cmd(uint8_t b);                 /* queue one byte */
void snd_tick(void);                     /* once a frame: send the next queued byte */
extern volatile uint8_t snd_test;        /* test hook: a byte poked here (capture POKE) is queued, then cleared */
void snd_sfx(uint8_t code);              /* $1A + code, skipped when the queue already lags (hit storms) */
void snd_ssg(uint8_t cue);               /* a menu sound: SSG_CURSOR / _CONFIRM / _CANCEL / _UNLOCK (snd/songs.h), an SSG cue
                                            on KOF98's own type-5 path (tools/port/ssg_cues.py): over the music and the
                                            ADPCM effects; a new cue replaces the one playing */
extern uint8_t snd_song;                 /* the last snd_music track */
void snd_music(uint8_t track);           /* a MUS_* command (snd/songs.h); only the songs in songs.json exist */
void snd_reset(void);                    /* drop the queue (the BIOS just reset the sound CPU) */
void snd_voice(uint8_t prefix, uint8_t code);   /* a voice: prefix (snd/voices.h VOICE_PREFIX_*) + code, skipped like snd_sfx */
/* KOF98 codes (measured in MAME, hits on Yuri): swing $1E light (A, C) / $1F heavy (B, D, C+D);
 * hit $11 A, $12 B, $13 C, $14 D, $15 C+D blowback. Every code the game sends must be in songs.json "sfx": the V ROM
 * holds only the samples of the codes listed there */
enum { SFX_SWING_LIGHT = 0x1E, SFX_SWING_HEAVY = 0x1F, SFX_HIT_A = 0x11, SFX_HIT_B = 0x12, SFX_HIT_C = 0x13,
       SFX_HIT_D = 0x14, SFX_HIT_CD = 0x15, SFX_GRAB = 0x19,   /* $19 GRAB START: a command grab connects (TODO #75) */
       SFX_THROW = 0x18,         /* $18 THROW START: the throw-start effect's own sound (KOF98 $3709E: index $80 -> $1A $18;
                                    TODO #166 a: a throw starts, never the walk-in catch) */
       SFX_FIRE = 0x2E };        /* $2E FIRE HIT: KOF96's fire hit, its $1A $1F (songs.json sfx "from", TODO #197) */
/* Music: build/snd/songs.h, generated from songs.json by tools/port/build_snd.py: MUS_<name> = the driver command of
 * each song the build carries (MUS_SELECT, MUS_FIGHT, MUS_JINGLE, MUS_BOSS_MR_BIG, MUS_BOSS_KRAUSER, MUS_BOSS_GEESE,
 * MUS_BOSS_RUGAL, MUS_BOSS_GOENITZ) and BOSS_SONGS, the boss themes in songs.json's "bosses" order */
#include "snd/songs.h"
extern const uint8_t snd_boss_song[N_BOSS_SONGS];
/* the options screen's MUSIC / SOUND PLAYER: every song and effect of the build with its name (songs.json -> songs.h) */
typedef struct { uint8_t cmd; const char *name; } snd_name_t;
extern const snd_name_t snd_songs[N_SONGS], snd_effects[N_SFX];   /* Mr. Big, Krauser, Geese, Rugal, Goenitz: snd_music(snd_boss_song[i]) */
#endif
