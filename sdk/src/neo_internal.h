#ifndef NEO_INTERNAL_H
#define NEO_INTERNAL_H

#include "neo_types.h"

/* VRAM command queue, written out by SYS_vblankFlush. Runs: {addr, count, count words}, written with VRAMMOD = 1 (the
 * LSPC steps the address after each word). neo_cmd_count = words in use. A full queue is written out right away (in
 * order, so later writes still win) rather than dropping commands: dropped writes left stale sprites on screen. */
extern uint16_t neo_cmd_buf[];
extern uint16_t neo_cmd_count;

void SYS_vblankFlush(void);

/* reserve a run of n consecutive VRAM words starting at addr; returns where to store them (n <= CMD_BUF_SIZE - 2) */
static inline uint16_t *cmd_run(uint16_t addr, uint16_t n) {
    uint16_t *p;
    if (neo_cmd_count + n + 2 > CMD_BUF_SIZE) SYS_vblankFlush();
    p = neo_cmd_buf + neo_cmd_count;
    p[0] = addr; p[1] = n;
    neo_cmd_count += n + 2;
    return p + 2;
}

static inline void cmd_push(uint16_t addr, uint16_t data) { *cmd_run(addr, 1) = data; }

#endif
