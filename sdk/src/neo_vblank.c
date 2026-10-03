#include "neo_hw.h"
#include "neo_sprite.h"
#include "neo_internal.h"

extern volatile uint8_t vblank_flag;

uint16_t neo_cmd_buf[CMD_BUF_SIZE];
uint16_t neo_cmd_count;

/* Runs {addr, count, words}: VRAMMOD = 1 so each word goes to the next address. Words go 16 at a time through an
 * unrolled move.w (a0)+,(a2) block, the remainder by a computed jump into the tail of a second one: ~13.5 cycles per word,
 * ~60 per run header. VRAMMOD is left at 0 as the rest of the SDK expects. */
void SYS_vblankFlush(void) {
    uint16_t sr, n = neo_cmd_count;
    uint16_t *c = neo_cmd_buf, *end = neo_cmd_buf + neo_cmd_count;
    if (!n) return;
    __asm__ volatile ("move.w %%sr, %0" : "=d"(sr));
    __asm__ volatile ("move.w #0x2700, %%sr" ::: "cc");
    __asm__ volatile (
        "    lea     0x3C0000, %%a1\n"
        "    lea     0x3C0002, %%a2\n"
        "    move.w  #1, 4(%%a1)\n"
        "1:  move.w  (%0)+, (%%a1)\n"        /* VRAMADDR */
        "    move.w  (%0)+, %%d1\n"          /* words in this run */
        "    cmp.w   #16, %%d1\n"
        "    bcs.s   3f\n"
        "2:  .rept   16\n"
        "    move.w  (%0)+, (%%a2)\n"        /* VRAMRW, address steps by VRAMMOD */
        "    .endr\n"
        "    sub.w   #16, %%d1\n"
        "    cmp.w   #16, %%d1\n"
        "    bcc.s   2b\n"
        "3:  add.w   %%d1, %%d1\n"
        "    lea     4f(%%pc), %%a3\n"
        "    suba.w  %%d1, %%a3\n"
        "    jmp     (%%a3)\n"
        "    .rept   15\n"
        "    move.w  (%0)+, (%%a2)\n"
        "    .endr\n"
        "4:  cmpa.l  %1, %0\n"
        "    bcs.s   1b\n"
        "    clr.w   4(%%a1)\n"
        : "+a"(c) : "a"(end) : "d1", "a1", "a2", "a3", "memory", "cc");
    neo_cmd_count = 0;
    __asm__ volatile ("move.w %0, %%sr" :: "d"(sr) : "cc");
    (void)n;
}

void SYS_waitVBlank(void) {
    vblank_flag = 0;
    while (!vblank_flag)
        ;
    SYS_vblankFlush();
}
