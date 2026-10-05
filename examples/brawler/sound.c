#include "sound.h"
#define REG_SOUND_B (*(volatile uint8_t *)0x320000)
#define QN 32                            /* power of two */
static uint8_t q[QN], qh, qt;
volatile uint8_t snd_test;
const uint8_t snd_boss_song[N_BOSS_SONGS] = BOSS_SONGS;
const snd_name_t snd_songs[N_SONGS] = SONG_LIST, snd_effects[N_SFX] = SFX_LIST;

void snd_cmd(uint8_t b) {
    uint8_t n = (qt + 1) & (QN - 1);
    if (n == qh) return;                 /* full: drop (a frame never asks for 32 bytes) */
    q[qt] = b; qt = n;
}
void snd_tick(void) {
    if (snd_test) { snd_cmd(snd_test); snd_test = 0; }
    if (qh != qt) { REG_SOUND_B = q[qh]; qh = (qh + 1) & (QN - 1); }
}

void snd_sfx(uint8_t code) {
    if (((qt - qh) & (QN - 1)) > 6) return;
    snd_cmd(0x1A); snd_cmd(code);
}
void snd_ssg(uint8_t cue) {
    if (((qt - qh) & (QN - 1)) > 6) return;
    snd_cmd(cue);
}
void snd_voice(uint8_t prefix, uint8_t code) {
    if (!code || ((qt - qh) & (QN - 1)) > 6) return;
    snd_cmd(prefix); snd_cmd(code);
}
/* the BIOS resets the sound CPU ($01 $03) each time it hands control back (attract demo -> title -> demo...), and
   KOF98's driver then ignores music until $07 again: every music start carries its own unlock */
uint8_t snd_song;                       /* the last song started (the continue gives the fight its song back) */
void snd_music(uint8_t track) { snd_cmd(0x07); snd_cmd(track); snd_song = track; }
void snd_reset(void) { qh = qt; }       /* the BIOS reset the sound CPU: a queued prefix would pair with the wrong byte */
