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
/* the music stopped under the sounds of this tick (the boss's KO, note 20261009-120007-5d29): KOF98's $04 ($1019) keys
   off FM 1-4, dumps all six ADPCM-A channels (the effects' 4-6 too: $0CF4 / $0C95), resets ADPCM-B, stops the SSG and
   sets $FD11 / $FD12 = $FF, and with $FD12 set the effect / voice path ($0204) drops every prefix sound. So: $04, then
   $09 (clears $FD12 only: effects and voices again, the music still muted until a song's $07), put in front of the
   bytes queued since snd_mark (this tick's: the killing hit's sound, played after the stop instead of cut by it) */
static uint8_t qm;                       /* snd_mark: the queue's end at the start of the tick */
void snd_mark(void) { qm = qt; }
void snd_stop_music(void) {
    uint8_t keep[QN], n = 0, i;
    if (((qt - qm) & (QN - 1)) > ((qt - qh) & (QN - 1))) qm = qh;   /* (the mark already sent: nothing held back) */
    while (qm != qt) { keep[n++] = q[qm]; qm = (qm + 1) & (QN - 1); }
    qt = (qt - n) & (QN - 1);
    snd_cmd(0x04); snd_cmd(0x09);
    for (i = 0; i < n; i++) snd_cmd(keep[i]);
    qm = qt;
}
void snd_reset(void) { qh = qt; }       /* the BIOS reset the sound CPU: a queued prefix would pair with the wrong byte */
