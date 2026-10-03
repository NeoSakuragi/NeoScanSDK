#include "sound.h"
#define REG_SOUND_B (*(volatile uint8_t *)0x320000)
#define QN 32                            /* power of two */
static uint8_t q[QN], qh, qt;
volatile uint8_t snd_test;

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
/* the BIOS resets the sound CPU ($01 $03) each time it hands control back (attract demo -> title -> demo...), and
   KOF98's driver then ignores music until $07 again: every music start carries its own unlock */
void snd_music(uint8_t track) { snd_cmd(0x07); snd_cmd(track); }
void snd_reset(void) { qh = qt; }       /* the BIOS reset the sound CPU: a queued prefix would pair with the wrong byte */
