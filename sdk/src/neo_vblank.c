#include "neo_hw.h"
#include "neo_sprite.h"
#include "neo_internal.h"

extern volatile uint8_t vblank_flag;

vram_cmd_t neo_cmd_buf[CMD_BUF_SIZE];
uint16_t neo_cmd_count;

void SYS_vblankFlush(void) {
    uint16_t i;
    for (i = 0; i < neo_cmd_count; i++) {
        REG_VRAMADDR = neo_cmd_buf[i].addr;
        REG_VRAMRW = neo_cmd_buf[i].data;
    }
    neo_cmd_count = 0;
}

void SYS_waitVBlank(void) {
    vblank_flag = 0;
    while (!vblank_flag)
        ;
    SYS_vblankFlush();
}
