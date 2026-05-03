/* Dump BIOS disassembly at key addresses */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zip.h>

static uint8_t bios[128*1024];

static void byteswap(uint8_t *d, int sz) {
    for (int i = 0; i + 1 < sz; i += 2) { uint8_t t = d[i]; d[i] = d[i+1]; d[i+1] = t; }
}

static uint16_t r16(uint32_t off) {
    off &= 0x1FFFF;
    return (bios[off] << 8) | bios[off+1];
}

static const char *cc_names[] = {"T","F","HI","LS","CC","CS","NE","EQ","VC","VS","PL","MI","GE","LT","GT","LE"};

static int disasm(uint32_t addr) {
    uint16_t op = r16(addr & 0x1FFFF);
    printf("  $%06X: %04X  ", addr, op);

    if (op == 0x4E75) { printf("RTS\n"); return 2; }
    if (op == 0x4E73) { printf("RTE\n"); return 2; }
    if (op == 0x4E71) { printf("NOP\n"); return 2; }
    if ((op & 0xFF00) == 0x6000) {
        int8_t d8 = op & 0xFF;
        if (d8 == 0) { int16_t d16 = (int16_t)r16((addr+2)&0x1FFFF); printf("BRA $%06X\n", addr+2+d16); return 4; }
        printf("BRA $%06X\n", addr+2+d8); return 2;
    }
    if ((op & 0xF000) == 0x6000) {
        int cc = (op>>8)&0xF;
        int8_t d8 = op & 0xFF;
        if (d8 == 0) { int16_t d16 = (int16_t)r16((addr+2)&0x1FFFF); printf("B%s $%06X\n", cc_names[cc], addr+2+d16); return 4; }
        if (cc == 1) { printf("BSR $%06X\n", addr+2+d8); return 2; }
        printf("B%s $%06X\n", cc_names[cc], addr+2+(int8_t)d8); return 2;
    }
    if ((op & 0xFFC0) == 0x4E80) { /* JSR */
        int mode = (op>>3)&7, reg = op&7;
        if (mode==7 && reg==1) { uint32_t a = ((uint32_t)r16((addr+2)&0x1FFFF)<<16)|r16((addr+4)&0x1FFFF); printf("JSR $%06X\n", a); return 6; }
        if (mode==7 && reg==0) { printf("JSR $%04X\n", r16((addr+2)&0x1FFFF)); return 4; }
        printf("JSR (mode=%d,reg=%d)\n", mode, reg); return 2;
    }
    if ((op & 0xFFC0) == 0x4EC0) { /* JMP */
        int mode = (op>>3)&7, reg = op&7;
        if (mode==7 && reg==1) { uint32_t a = ((uint32_t)r16((addr+2)&0x1FFFF)<<16)|r16((addr+4)&0x1FFFF); printf("JMP $%06X\n", a); return 6; }
        if (mode==7 && reg==0) { printf("JMP $%04X\n", r16((addr+2)&0x1FFFF)); return 4; }
        printf("JMP (mode=%d,reg=%d)\n", mode, reg); return 2;
    }
    /* Default: raw opcode */
    uint16_t w2 = r16((addr+2)&0x1FFFF);
    uint16_t w3 = r16((addr+4)&0x1FFFF);
    printf("??? [%04X %04X %04X]\n", op, w2, w3);
    return 2;
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "/home/bruno/roms/neogeo/neogeo.zip";
    int err; zip_t *z = zip_open(path, ZIP_RDONLY, &err);
    if (!z) { fprintf(stderr, "Can't open %s\n", path); return 1; }
    zip_file_t *zf = zip_fopen(z, "sp-s2.sp1", 0);
    if (!zf) { fprintf(stderr, "No sp-s2.sp1\n"); return 1; }
    zip_fread(zf, bios, 128*1024);
    zip_fclose(zf); zip_close(z);
    byteswap(bios, 128*1024);

    /* Dump areas of interest */
    uint32_t areas[][2] = {
        {0xC130A0, 0xC13140},  /* Diagnostic test area */
        {0xC16B20, 0xC16BC0},  /* Error/halt area */
        {0xC1871A, 0xC18730},  /* Game dispatch area */
    };
    for (int a = 0; a < 3; a++) {
        printf("\n=== $%06X - $%06X ===\n", areas[a][0], areas[a][1]);
        uint32_t pc = areas[a][0];
        while (pc < areas[a][1]) {
            pc += disasm(pc);
        }
    }
    return 0;
}
