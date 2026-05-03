/* CPU validation: run Musashi and our CPU68K side by side,
   compare ALL registers after each instruction.
   First divergence = the bug. */

#include "src/cpu68k.h"
#include "src/neogeo.h"
#include "lib/musashi/m68k.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

ng_t ng;

/* Shared memory — both CPUs read/write the same state */
uint8_t  mem_read8(uint32_t a)  { return m68k_read_memory_8(a); }
uint16_t mem_read16(uint32_t a) { return m68k_read_memory_16(a); }
uint32_t mem_read32(uint32_t a) { return m68k_read_memory_32(a); }
void mem_write8(uint32_t a, uint8_t v)   { m68k_write_memory_8(a, v); }
void mem_write16(uint32_t a, uint16_t v) { m68k_write_memory_16(a, v); }
void mem_write32(uint32_t a, uint32_t v) { m68k_write_memory_32(a, v); }

/* Musashi memory handlers — use the same memory map as our emulator */
#include "src/memory.c"
#undef mem_read8
#undef mem_read16
#undef mem_read32
#undef mem_write8
#undef mem_write16
#undef mem_write32

/* Redirect our CPU's mem calls to the shared handlers */

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "Usage: test_cpu bios.zip game.neo\n"); return 1; }

    memset(&ng, 0, sizeof(ng));
    if (ng_load_bios(argv[1]) < 0) return 1;
    if (ng_load_neo(argv[2]) < 0) return 1;
    ng_mem_init();

    /* Init Musashi */
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_init();
    m68k_pulse_reset();

    /* Init our CPU */
    cpu_init();
    cpu_reset();

    printf("Musashi: PC=$%06X SP=$%08X\n", m68k_get_reg(NULL, M68K_REG_PC), m68k_get_reg(NULL, M68K_REG_A7));
    printf("Ours:    PC=$%06X SP=$%08X\n", cpu_get_reg(CPU_PC), cpu_get_reg(CPU_A7));

    /* Run both CPUs instruction by instruction and compare */
    for (int i = 0; i < 100000; i++) {
        /* Execute 1 instruction on each */
        /* TODO: need single-step for both */
    }

    return 0;
}
