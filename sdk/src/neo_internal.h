#ifndef NEO_INTERNAL_H
#define NEO_INTERNAL_H

#include "neo_types.h"

extern neo_vram_cmd_t neo_cmd_buf[];
extern uint16_t neo_cmd_count;

static inline void neo_cmd_push(uint16_t addr, uint16_t data) {
    if (neo_cmd_count < NEO_CMD_BUF_SIZE) {
        neo_cmd_buf[neo_cmd_count].addr = addr;
        neo_cmd_buf[neo_cmd_count].data = data;
        neo_cmd_count++;
    }
}

#endif
