#include "neogeo.h"
#include "cpu68k.h"
#include <stdio.h>
#include <string.h>

static uint16_t prom_r16(uint32_t off) {
    if (off + 1 < ng.prom_size)
        return (ng.prom[off + 1] << 8) | ng.prom[off];
    return 0xFFFF;
}
static uint8_t prom_r8(uint32_t off) {
    if (off < ng.prom_size)
        return ng.prom[off ^ 1];
    return 0xFF;
}

static inline void vram_addr_inc(void) {
    ng.vram_addr = (ng.vram_addr & 0x8000) | ((ng.vram_addr + ng.vram_mod) & 0x7FFF);
}
static void vram_write(uint16_t val) {
    uint16_t a = ng.vram_addr;
    if (a < NG_VRAM_SIZE / 2) ng.vram[a] = val;
    vram_addr_inc();
}

/* ---- 8-bit read ---- */
uint8_t mem_read8(uint32_t address) {
    address &= 0xFFFFFF;
    if (address < 0x100000)
        return ng.bios_vec ? ng.bios[address & (NG_BIOS_SIZE-1)] : prom_r8(address);
    if (address < 0x110000) return ng.wram[address & 0xFFFF];
    if (address >= 0x200000 && address < 0x300000) return prom_r8(address & 0xFFFFF);
    if (address >= 0x300000 && address < 0x320000) {
        if (address & 1) return 0xFF;  /* $300001: system status — MVS type, all bits high */
        return ~ng.p1;                 /* $300000: player 1 buttons (active low) */
    }
    if (address >= 0x320000 && address < 0x340000) {
        if (ng.sound_ack_delay <= 0) ng.sound_reply ^= 0x40;
        return ng.sound_reply;
    }
    if (address >= 0x340000 && address < 0x380000) {
        if (address & 1) return 0xFF;  /* $340001: status */
        return ~ng.p2;                 /* $340000: player 2 buttons */
    }
    if (address >= 0x380000 && address < 0x3A0000) {
        uint8_t cal = ng_cal_read();
        return (~ng.sys & 0x3F) | cal;
    }
    if (address >= 0x400000 && address < 0x402000) return ng.palram[address & 0x1FFF];
    if (address >= 0xC00000 && address < 0xD00000) return ng.bios[address & (NG_BIOS_SIZE-1)];
    if (address >= 0xD00000 && address < 0xE00000) return ng.sram[address & 0xFFFF];
    return 0xFF;
}

/* ---- 16-bit read ---- */
uint16_t mem_read16(uint32_t address) {
    address &= 0xFFFFFF;
    if (address < 0x100000) {
        if (ng.bios_vec) { uint32_t o=address&(NG_BIOS_SIZE-1)&~1u; return (ng.bios[o]<<8)|ng.bios[o+1]; }
        return prom_r16(address & ~1u);
    }
    if (address < 0x110000) { uint32_t o=address&0xFFFE; return (ng.wram[o]<<8)|ng.wram[o+1]; }
    if (address >= 0x200000 && address < 0x300000) return prom_r16(address & 0xFFFFE);
    if (address >= 0x300000 && address < 0x320000) return 0xFF00|(uint8_t)(~ng.p1);
    if (address >= 0x320000 && address < 0x340000) {
        if (ng.sound_ack_delay <= 0) ng.sound_reply ^= 0x40;
        return 0xFF00|ng.sound_reply;
    }
    if (address >= 0x340000 && address < 0x380000) return 0xFF00|(uint8_t)(~ng.p2);
    if (address >= 0x380000 && address < 0x3A0000) {
        uint8_t cal = ng_cal_read();
        return 0xFF00 | (~ng.sys & 0x3F) | cal;
    }
    if (address >= 0x3C0000 && address < 0x3E0000) {
        switch (address & 0xE) {
        case 0x0:
        case 0x2: {
            uint16_t a = ng.vram_addr;
            return (a < NG_VRAM_SIZE/2) ? ng.vram[a] : 0;
        }
        case 0x4: return ng.vram_mod;
        case 0x6: return ng.scanline << 7;
        } return 0;
    }
    if (address >= 0x400000 && address < 0x402000) { uint32_t o=address&0x1FFE; return (ng.palram[o]<<8)|ng.palram[o+1]; }
    if (address >= 0xC00000 && address < 0xD00000) { uint32_t o=address&(NG_BIOS_SIZE-1)&~1u; return (ng.bios[o]<<8)|ng.bios[o+1]; }
    if (address >= 0xD00000 && address < 0xE00000) { uint32_t o=address&0xFFFE; return (ng.sram[o]<<8)|ng.sram[o+1]; }
    return 0xFFFF;
}

uint32_t mem_read32(uint32_t address) {
    return ((uint32_t)mem_read16(address) << 16) | mem_read16(address + 2);
}

/* ---- 8-bit write ---- */
void mem_write8(uint32_t address, uint8_t value) {
    address &= 0xFFFFFF;
    if (address >= 0x100000 && address < 0x110000) { ng.wram[address&0xFFFF]=value; return; }
    if (address >= 0x300000 && address < 0x320000) return;
    if (address >= 0x320000 && address < 0x340000) { ng.sound_cmd=value; return; }
    if (address >= 0x380000 && address < 0x3A0000) {
        if ((address & 0xFE) == 0x50) {
            static int first_nmi = 1;
            ng.sound_ack_delay = first_nmi ? 58 : 1;
            first_nmi = 0;
        } else if ((address & 0xFF) < 0x30) {
            ng_cal_write(value);
        }
        return;
    }
    if (address >= 0x3A0000 && address < 0x3C0000) {
        switch (address & 0x1F) {
        case 0x01: break;
        case 0x03: break;
        case 0x0B: ng.bios_vec=1; ng.fix_layer=0; break;
        case 0x0D: ng.sram_lock=1; break;
        case 0x0F: ng.bios_vec=0; break;
        case 0x11: ng.fix_layer=1; break;
        case 0x13: ng.fix_layer=1; break;
        case 0x1D: ng.sram_lock=0; break;
        case 0x1F: break;
        } return;
    }
    if (address >= 0x400000 && address < 0x402000) {
        uint32_t o=address&0x1FFF; ng.palram[o]=value;
        uint32_t wo=o&~1u; ng_pal_write(wo,(ng.palram[wo]<<8)|ng.palram[wo|1]); return;
    }
    if (address >= 0xD00000 && address < 0xE00000) {
        if (!ng.sram_lock) ng.sram[address&0xFFFF]=value;
        return;
    }
}

/* ---- 16-bit write ---- */
void mem_write16(uint32_t address, uint16_t value) {
    address &= 0xFFFFFF;
    if (address >= 0x100000 && address < 0x110000) {
        uint32_t o=address&0xFFFE; ng.wram[o]=value>>8; ng.wram[o+1]=value&0xFF; return;
    }
    if (address >= 0x300000 && address < 0x320000) return;
    if (address >= 0x320000 && address < 0x340000) { ng.sound_cmd=value&0xFF; return; }
    if (address >= 0x3A0000 && address < 0x3C0000) { mem_write8(address+1, value&0xFF); return; }
    if (address >= 0x3C0000 && address < 0x3E0000) {
        switch (address & 0xE) {
        case 0x0: ng.vram_addr = value; break;
        case 0x2: vram_write(value); break;
        case 0x4: ng.vram_mod=value; break;
        case 0xA: break;  /* timer reload low */
        case 0xC:  /* REG_IRQACK: bit2=VBlank, bit1=Timer, bit0=Reset */
            if (value & 0x04) cpu_set_irq(0);
            break;
        } return;
    }
    if (address >= 0x400000 && address < 0x402000) {
        uint32_t o=address&0x1FFE; ng.palram[o]=value>>8; ng.palram[o+1]=value&0xFF;
        ng_pal_write(o,value); return;
    }
    if (address >= 0xD00000 && address < 0xE00000) {
        if (!ng.sram_lock) { uint32_t o=address&0xFFFE; ng.sram[o]=value>>8; ng.sram[o+1]=value&0xFF; }
        return;
    }
}

void mem_write32(uint32_t address, uint32_t value) {
    mem_write16(address, value >> 16);
    mem_write16(address + 2, value & 0xFFFF);
}

void ng_mem_init(void) {
    static const char sram_header[] = "BACKUP RAM OK !";
    memset(ng.sram, 0, sizeof(ng.sram));
    memcpy(ng.sram + 0x10, sram_header, 15);
    ng.sram[0x10 + 15] = 0x80;

    memset(ng.wram, 0, sizeof(ng.wram));
    memset(ng.palram, 0, sizeof(ng.palram));
    memset(ng.vram, 0, sizeof(ng.vram));
    ng.vram_addr = 0;
    ng.vram_mod = 1;
    ng.bios_vec = 1;
    ng.fix_layer = 0;
    ng.sram_lock = 0;
    ng.sound_reply = 0x00;  /* bit 6 clear — BIOS waits for it to go high */
}
