/* Standalone Musashi trace generator — dumps register state per instruction.
   Compile: gcc -O2 -o mtrace musashi_trace.c lib/musashi/m68kcpu.c lib/musashi/m68kops.c lib/musashi/m68kdasm.c lib/musashi/softfloat/softfloat.c -Ilib/musashi -lzip
*/
#include "m68k.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zip.h>

static uint8_t *bios, *prom;
static uint32_t prom_size;
static uint8_t wram[64*1024], palram[8192], sram[65536];
static uint16_t vram[65536];
static uint16_t vram_addr, vram_mod = 1;
static uint8_t bios_vec = 1, sound_reply = 0x40;
static int scanline = 0, total_cycles = 0;

static uint16_t pr16(uint32_t o) { return (o+1<prom_size) ? (prom[o+1]<<8)|prom[o] : 0xFFFF; }
static uint8_t pr8(uint32_t o) { return (o<prom_size) ? prom[o^1] : 0xFF; }

unsigned int m68k_read_memory_8(unsigned int a) {
    a &= 0xFFFFFF;
    if (a < 0x100000) return bios_vec ? bios[a&0x1FFFF] : pr8(a);
    if (a < 0x110000) return wram[a&0xFFFF];
    if (a >= 0x200000 && a < 0x300000) return pr8(a&0xFFFFF);
    if (a >= 0x300000 && a < 0x320000) return 0xFF;
    if (a >= 0x320000 && a < 0x340000) { sound_reply ^= 0x40; return sound_reply; }
    if (a >= 0x340000 && a < 0x380000) return 0xFF;
    if (a >= 0x380000 && a < 0x3A0000) {
        static int tp_ctr; tp_ctr++;
        int tp = (tp_ctr / 30000) & 1;
        int data_out = (tp_ctr / 7) & 1;  /* pseudo-random data bits */
        return (0xFF & ~0xC0) | (tp ? 0x40 : 0) | (data_out ? 0x80 : 0);
    }
    if (a >= 0x400000 && a < 0x402000) return palram[a&0x1FFF];
    if (a >= 0xC00000 && a < 0xD00000) return bios[a&0x1FFFF];
    if (a >= 0xD00000 && a < 0xE00000) return sram[a&0xFFFF];
    return 0xFF;
}
unsigned int m68k_read_memory_16(unsigned int a) {
    a &= 0xFFFFFF;
    if (a < 0x100000) {
        if (bios_vec) { uint32_t o=a&0x1FFFF&~1u; return (bios[o]<<8)|bios[o+1]; }
        return pr16(a&~1u);
    }
    if (a < 0x110000) { uint32_t o=a&0xFFFE; return (wram[o]<<8)|wram[o+1]; }
    if (a >= 0x200000 && a < 0x300000) return pr16(a&0xFFFFE);
    if (a >= 0x300000 && a < 0x320000) return 0xFFFF;
    if (a >= 0x320000 && a < 0x340000) { sound_reply ^= 0x40; return 0xFF00|sound_reply; }
    if (a >= 0x340000 && a < 0x380000) return 0xFFFF;
    if (a >= 0x380000 && a < 0x3A0000) return 0xFFFF;
    if (a >= 0x3C0000 && a < 0x3E0000) {
        switch (a & 0xE) {
        case 0x0: case 0x2: return (vram_addr<65536)?vram[vram_addr]:0;
        case 0x4: return vram_mod;
        case 0x6: return scanline << 7;
        } return 0;
    }
    if (a >= 0x400000 && a < 0x402000) { uint32_t o=a&0x1FFE; return (palram[o]<<8)|palram[o+1]; }
    if (a >= 0xC00000 && a < 0xD00000) { uint32_t o=a&0x1FFFF&~1u; return (bios[o]<<8)|bios[o+1]; }
    if (a >= 0xD00000 && a < 0xE00000) { uint32_t o=a&0xFFFE; return (sram[o]<<8)|sram[o+1]; }
    return 0xFFFF;
}
unsigned int m68k_read_memory_32(unsigned int a) {
    return ((uint32_t)m68k_read_memory_16(a)<<16)|m68k_read_memory_16(a+2);
}
unsigned int m68k_read_immediate_16(unsigned int a) { return m68k_read_memory_16(a); }
unsigned int m68k_read_immediate_32(unsigned int a) { return m68k_read_memory_32(a); }
unsigned int m68k_read_pcrelative_8(unsigned int a) { return m68k_read_memory_8(a); }
unsigned int m68k_read_pcrelative_16(unsigned int a) { return m68k_read_memory_16(a); }
unsigned int m68k_read_pcrelative_32(unsigned int a) { return m68k_read_memory_32(a); }
unsigned int m68k_read_disassembler_8(unsigned int a) { return m68k_read_memory_8(a); }
unsigned int m68k_read_disassembler_16(unsigned int a) { return m68k_read_memory_16(a); }
unsigned int m68k_read_disassembler_32(unsigned int a) { return m68k_read_memory_32(a); }

void m68k_write_memory_8(unsigned int a, unsigned int v) {
    a &= 0xFFFFFF;
    if (a >= 0x100000 && a < 0x110000) { wram[a&0xFFFF]=v; return; }
    if (a >= 0x320000 && a < 0x340000) { sound_reply=(v^0x40)&0xFF; return; }
    if (a >= 0x3A0000 && a < 0x3C0000) {
        switch(a&0x7F) {
        case 0x0B: bios_vec=1; break;
        case 0x0F: bios_vec=0; break;
        case 0x11: bios_vec=1; break;
        case 0x29: { /* Calendar write */
            static int clk_prev, stb_prev, cmd, shift_pos;
            int clk = (v>>1)&1, stb = (v>>2)&1;
            if (clk && !clk_prev) { cmd = (cmd>>1)|((v&1)<<3); shift_pos++; }
            if (stb && !stb_prev) { cmd=0; shift_pos=0; }
            clk_prev=clk; stb_prev=stb;
            break;
        }
        }
        return;
    }
    if (a >= 0x400000 && a < 0x402000) { palram[a&0x1FFF]=v; return; }
    if (a >= 0xD00000 && a < 0xE00000) { sram[a&0xFFFF]=v; return; }
}
void m68k_write_memory_16(unsigned int a, unsigned int v) {
    a &= 0xFFFFFF;
    if (a >= 0x100000 && a < 0x110000) { uint32_t o=a&0xFFFE; wram[o]=v>>8; wram[o+1]=v&0xFF; return; }
    if (a >= 0x320000 && a < 0x340000) { sound_reply=((v&0xFF)^0x40)&0xFF; return; }
    if (a >= 0x3A0000 && a < 0x3C0000) { m68k_write_memory_8(a+1,v&0xFF); return; }
    if (a >= 0x3C0000 && a < 0x3E0000) {
        switch(a&0xE) {
        case 0x0: vram_addr=v; break;
        case 0x2: if(vram_addr<65536) vram[vram_addr]=v; vram_addr+=vram_mod; break;
        case 0x4: vram_mod=v; break; case 0xA: if (v & 1) m68k_set_irq(0); break;
        } return;
    }
    if (a >= 0x400000 && a < 0x402000) { uint32_t o=a&0x1FFE; palram[o]=v>>8; palram[o+1]=v&0xFF; return; }
    if (a >= 0xD00000 && a < 0xE00000) { uint32_t o=a&0xFFFE; sram[o]=v>>8; sram[o+1]=v&0xFF; return; }
}
void m68k_write_memory_32(unsigned int a, unsigned int v) {
    m68k_write_memory_16(a,v>>16); m68k_write_memory_16(a+2,v&0xFFFF);
}
void m68k_write_memory_32_pd(unsigned int a, unsigned int v) { m68k_write_memory_32(a,v); }

static void byteswap(uint8_t *d, uint32_t sz) {
    for (uint32_t i=0;i+1<sz;i+=2) { uint8_t t=d[i]; d[i]=d[i+1]; d[i+1]=t; }
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "Usage: mtrace bios.zip game.neo\n"); return 1; }

    bios = calloc(1, 128*1024);
    int err; zip_t *z = zip_open(argv[1], ZIP_RDONLY, &err);
    if (!z) { fprintf(stderr, "Can't open %s\n", argv[1]); return 1; }
    const char *names[] = {"sp-s2.sp1","uni-bios_4_0.rom",NULL};
    for (int i=0; names[i]; i++) {
        zip_file_t *zf = zip_fopen(z, names[i], 0);
        if (zf) { zip_fread(zf, bios, 128*1024); zip_fclose(zf); printf("BIOS: %s\n", names[i]); break; }
    }
    zip_close(z);
    byteswap(bios, 128*1024);

    FILE *f = fopen(argv[2], "rb");
    uint8_t hdr[4096]; fread(hdr, 1, 4096, f);
    prom_size = *(uint32_t*)(hdr+4);
    prom = malloc(prom_size); fread(prom, 1, prom_size, f);
    fclose(f);

    memcpy(sram+0x10, "BACKUP RAM OK !", 15); sram[0x10+15]=0x80;

    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_init();

    FILE *out = fopen("/tmp/musashi_trace.txt", "w");
    int count = 0;
    m68k_set_instr_hook_callback(NULL);
    m68k_pulse_reset();

    /* Dump state before each instruction using a loop */
    /* Run frame loop matching emulator */
    int frame = 0;
    int found_game = 0;
    for (frame = 0; frame < 500 && !found_game; frame++) {
        for (int line = 0; line < 264; line++) {
            scanline = line;
            /* Run one scanline worth of cycles */
            int target = 768;
            int ran = 0;
            while (ran < target) {
                uint32_t pc = m68k_get_reg(NULL, M68K_REG_PC);
                static uint32_t prev_pcs[8]; static int ppi;
                prev_pcs[ppi++ & 7] = pc;
                if (pc == 0xC16BB0 || pc == 0xC16BAA) {
                    printf("HALT at $%06X! Trail:", pc);
                    for (int j=1;j<=8;j++) printf(" $%06X", prev_pcs[(ppi-j)&7]);
                    printf("\nD0=%08X D1=%08X SR=%04X\n",
                        m68k_get_reg(NULL,M68K_REG_D0), m68k_get_reg(NULL,M68K_REG_D1),
                        m68k_get_reg(NULL,M68K_REG_SR));
                    found_game = 1; break;
                }
                if (pc == 0x200122) {
                    printf("FOUND: JSR $200122 at frame %d, line %d\n", frame, line);
                    printf("  FDAE=%02X FD80=%02X FD94=%02X\n", wram[0xFDAE], wram[0xFD80], wram[0xFD94]);
                    printf("  D0=%08X D1=%08X A7=%08X SR=%04X\n",
                        m68k_get_reg(NULL,M68K_REG_D0), m68k_get_reg(NULL,M68K_REG_D1),
                        m68k_get_reg(NULL,M68K_REG_A7), m68k_get_reg(NULL,M68K_REG_SR));
                    found_game = 1;
                    break;
                }
                ran += m68k_execute(4);
            }
            if (found_game) break;
            if (line == 248) {
                // no FD80 hack
                m68k_set_irq(1);
            } else if (line == 249) {
                m68k_set_irq(0);
            }
        }
        if (frame % 60 == 0)
            printf("Frame %d: PC=%06X FDAE=%02X FD80=%02X bv=%d\n",
                frame, m68k_get_reg(NULL,M68K_REG_PC), wram[0xFDAE], wram[0xFD80], bios_vec);
    }
    fclose(out);
    printf("Musashi trace: 100000 instructions → /tmp/musashi_trace.txt\n");
    return 0;
}
