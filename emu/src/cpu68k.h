#ifndef CPU68K_H
#define CPU68K_H

#include <stdint.h>

/* Registers */
enum {
    CPU_D0, CPU_D1, CPU_D2, CPU_D3, CPU_D4, CPU_D5, CPU_D6, CPU_D7,
    CPU_A0, CPU_A1, CPU_A2, CPU_A3, CPU_A4, CPU_A5, CPU_A6, CPU_A7,
    CPU_PC, CPU_SR, CPU_USP, CPU_SSP
};

/* Status register bits */
#define SR_C  0x0001
#define SR_V  0x0002
#define SR_Z  0x0004
#define SR_N  0x0008
#define SR_X  0x0010
#define SR_I0 0x0100
#define SR_I1 0x0200
#define SR_I2 0x0400
#define SR_S  0x2000
#define SR_T  0x8000

#define SR_IMASK (SR_I0|SR_I1|SR_I2)
#define SR_ISHIFT 8

typedef struct {
    uint32_t d[8];
    uint32_t a[8];
    uint32_t pc;
    uint16_t sr;
    uint32_t usp;
    uint32_t ssp;
    int      irq_level;
    int      cycles;
    int      halted;
    int      stopped;
} cpu68k_t;

extern cpu68k_t cpu;

/* Memory interface — implemented in memory.c */
uint8_t  mem_read8(uint32_t addr);
uint16_t mem_read16(uint32_t addr);
uint32_t mem_read32(uint32_t addr);
void mem_write8(uint32_t addr, uint8_t val);
void mem_write16(uint32_t addr, uint16_t val);
void mem_write32(uint32_t addr, uint32_t val);

void cpu_init(void);
void cpu_reset(void);
int  cpu_execute(int cycles);
void cpu_set_irq(int level);
uint32_t cpu_get_reg(int reg);
void cpu_set_reg(int reg, uint32_t val);

#endif
