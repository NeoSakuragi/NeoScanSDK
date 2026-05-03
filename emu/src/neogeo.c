#include "neogeo.h"
#include "cpu68k.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

ng_t ng;

void ng_init(void) {
    memset(&ng, 0, sizeof(ng));
    ng.running = true;
    cpu_init();
}

void ng_reset(void) {
    ng_mem_init();
    ng_vid_init();

    ng.bios_vec = 1;
    ng.sound_ack_delay = 58;
    cpu_reset();
    printf("NG-EMU: PC=$%06X SP=$%08X\n", cpu_get_reg(CPU_PC), cpu_get_reg(CPU_A7));
}

int fcount;

void ng_frame(void) {
    for (int line = 0; line < NG_TOTAL_LINES; line++) {
        ng.scanline = line;
        cpu_execute(NG_CYCLES_PER_LINE);
        if (cpu.halted) { ng.running = false; return; }

        if (line == NG_VBLANK_LINE) {
            if (ng.sound_ack_delay > 0) ng.sound_ack_delay--;
            cpu_set_irq(1);
        }

        if (line < NG_SCREEN_H)
            ng_vid_render_line(line);
    }

    if (fcount < 10 || (fcount < 600 && fcount % 60 == 0))
        printf("f%d PC=$%06X FD80=%02X FDAE=%02X bv=%d SR=%04X\n",
               fcount, cpu_get_reg(CPU_PC), ng.wram[0xFD80], ng.wram[0xFDAE],
               ng.bios_vec, cpu.sr);
    fcount++;
}

void ng_shutdown(void) {
    free(ng.prom); free(ng.srom); free(ng.mrom);
    free(ng.v1rom); free(ng.crom); free(ng.bios);
    free(ng.sfix); free(ng.lorom);
}
