/* neocart_bus.h — MVS cart edge connector as shared memory.
   28 bytes = every signal on PROG (CTRG2) and CHA (CTRG1) connectors.
   Matches prog_bus.v and cha_bus.v pin-for-pin.

   MAME writes MVS-side pins (address, control).
   Server writes cart-side pins (data, DTACK).
   GUI reads all pins for visualization.
*/
#ifndef NEOCART_BUS_H
#define NEOCART_BUS_H

#include <stdint.h>

#define NEOCART_SHM_PATH "/dev/shm/neocart_bus"
#define NEOCART_SHM_SIZE 32

/* Debug control: byte 30 = pause flag, byte 31 = step trigger */
#define DBG_PAUSE       30  /* GUI writes: 1=paused, 0=running */
#define DBG_STEP        31  /* GUI writes: 1=do one cycle, server clears to 0 */

/* ═══════════════════════════════════════════════════════════════════
   PROG bus (CTRG2) — bytes 0-11
   68K ↔ P-ROM  +  YM2610 ↔ V-ROM
   ═══════════════════════════════════════════════════════════════════ */

/* Address bus: A1-A19 (19 bits) packed into bytes 0-2 */
#define PROG_ADDR_LO    0   /* [7:0]  ADDR[7:0]   — A1-A8   */
#define PROG_ADDR_MID   1   /* [7:0]  ADDR[15:8]  — A9-A16  */
#define PROG_ADDR_HI    2   /* [2:0]  ADDR[18:16] — A17-A19 */
                            /* [6:3]  REGION[3:0] — A20-A23 */
                            /* [7]    nRW                    */
#define PROG_ADDR_MASK      0x0007FFFF
#define PROG_REGION_SHIFT   3
#define PROG_REGION_MASK    0x0F
#define PROG_NRW_BIT        (1 << 7)  /* in byte 2 */

/* Control signals: byte 3 */
#define PROG_CTRL       3
#define PROG_ROMOE_n    (1 << 0)  /* P-ROM output enable (active low) */
#define PROG_ROMOEU_n   (1 << 1)  /* Upper byte enable (active low)   */
#define PROG_ROMOEL_n   (1 << 2)  /* Lower byte enable (active low)   */
#define PROG_VROM_OE_n  (1 << 3)  /* V-ROM output enable (active low) */

/* P-ROM data bus: D0-D15 (16 bits) — bytes 4-5 */
#define PROG_DATA_LO    4   /* [7:0]  D0-D7  */
#define PROG_DATA_HI    5   /* [7:0]  D8-D15 */

/* V-ROM address: 24 bits — bytes 6-8 */
#define PROG_VADDR_LO   6
#define PROG_VADDR_MID  7
#define PROG_VADDR_HI   8

/* V-ROM data: 8 bits — byte 9 */
#define PROG_VDATA      9

/* Acknowledge signals: byte 10 */
#define PROG_ACK        10
#define PROG_DTACK_n    (1 << 0)  /* P-ROM data ack (active low) */
#define PROG_VDTACK_n   (1 << 1)  /* V-ROM data ack (active low) */

/* byte 11: reserved/padding */


/* ═══════════════════════════════════════════════════════════════════
   CHA bus (CTRG1) — bytes 12-27
   LSPC ↔ C-ROM  +  Fix ↔ S-ROM  +  Z80 ↔ M-ROM
   ═══════════════════════════════════════════════════════════════════ */

/* C-ROM address: P0-P23 (24 bits) — bytes 12-14 */
#define CHA_CADDR_LO    12
#define CHA_CADDR_MID   13
#define CHA_CADDR_HI    14

/* CHA control signals: byte 15 */
#define CHA_CTRL        15
#define CHA_PCK1B       (1 << 0)  /* C-ROM clock 1 (active low edge) */
#define CHA_PCK2B       (1 << 1)  /* C-ROM clock 2 (active low edge) */
#define CHA_SROM_OE_n   (1 << 2)  /* S-ROM read enable / SDMRD       */
#define CHA_MROM_OE_n   (1 << 3)  /* M-ROM read enable               */

/* C-ROM address extension: byte 28 (bits [31:24] of C-ROM address) */
#define CHA_CADDR_EXT   28

/* C-ROM data: CR0-CR31 (32 bits) — bytes 16-19 */
#define CHA_CDATA_0     16  /* CR0-CR7   */
#define CHA_CDATA_1     17  /* CR8-CR15  */
#define CHA_CDATA_2     18  /* CR16-CR23 */
#define CHA_CDATA_3     19  /* CR24-CR31 */

/* S-ROM address: SDA0-SDA23 (24 bits) — bytes 20-22 */
#define CHA_SADDR_LO    20
#define CHA_SADDR_HI    21
#define CHA_SADDR_EXT   22  /* address bits [23:16] */

/* S-ROM data: SDD0-SDD7 (8 bits) — byte 29 */
#define CHA_SDATA       29

/* M-ROM address: 17 bits — bytes 23-25 */
#define CHA_MADDR_LO    23
#define CHA_MADDR_MID   24
#define CHA_MADDR_HI    25  /* [0] = bit 16, [7:1] reserved */
#define CHA_MADDR_B16   (1 << 0)

/* M-ROM data: 8 bits — byte 26 */
#define CHA_MDATA       26

/* CHA acknowledge signals: byte 27 */
#define CHA_ACK         27
#define CHA_CROM_DTACK_n (1 << 0)  /* C-ROM data ack (active low) */
#define CHA_SROM_DTACK_n (1 << 1)  /* S-ROM data ack (active low) */
#define CHA_MROM_DTACK_n (1 << 2)  /* M-ROM data ack (active low) */


/* ═══════════════════════════════════════════════════════════════════
   Inline helpers for bus operations
   ═══════════════════════════════════════════════════════════════════ */

static inline void bus_set_paddr(volatile uint8_t *shm, uint32_t addr) {
    shm[PROG_ADDR_LO]  = addr & 0xFF;
    shm[PROG_ADDR_MID] = (addr >> 8) & 0xFF;
    /* preserve nRW and REGION bits in byte 2 */
    shm[PROG_ADDR_HI]  = (shm[PROG_ADDR_HI] & 0xF8) | ((addr >> 16) & 0x07);
}

static inline uint32_t bus_get_paddr(volatile uint8_t *shm) {
    return shm[PROG_ADDR_LO]
         | (shm[PROG_ADDR_MID] << 8)
         | ((shm[PROG_ADDR_HI] & 0x07) << 16);
}

static inline void bus_set_pregion(volatile uint8_t *shm, uint8_t region) {
    shm[PROG_ADDR_HI] = (shm[PROG_ADDR_HI] & 0x87)
                       | ((region & PROG_REGION_MASK) << PROG_REGION_SHIFT);
}

static inline uint8_t bus_get_pregion(volatile uint8_t *shm) {
    return (shm[PROG_ADDR_HI] >> PROG_REGION_SHIFT) & PROG_REGION_MASK;
}

static inline void bus_set_pdata(volatile uint8_t *shm, uint16_t data) {
    shm[PROG_DATA_LO] = data & 0xFF;
    shm[PROG_DATA_HI] = (data >> 8) & 0xFF;
}

static inline uint16_t bus_get_pdata(volatile uint8_t *shm) {
    return shm[PROG_DATA_LO] | (shm[PROG_DATA_HI] << 8);
}

static inline void bus_set_vaddr(volatile uint8_t *shm, uint32_t addr) {
    shm[PROG_VADDR_LO]  = addr & 0xFF;
    shm[PROG_VADDR_MID] = (addr >> 8) & 0xFF;
    shm[PROG_VADDR_HI]  = (addr >> 16) & 0xFF;
}

static inline uint32_t bus_get_vaddr(volatile uint8_t *shm) {
    return shm[PROG_VADDR_LO]
         | (shm[PROG_VADDR_MID] << 8)
         | (shm[PROG_VADDR_HI] << 16);
}

static inline void bus_set_caddr(volatile uint8_t *shm, uint32_t addr) {
    shm[CHA_CADDR_LO]  = addr & 0xFF;
    shm[CHA_CADDR_MID] = (addr >> 8) & 0xFF;
    shm[CHA_CADDR_HI]  = (addr >> 16) & 0xFF;
    shm[CHA_CADDR_EXT] = (addr >> 24) & 0xFF;
}

static inline uint32_t bus_get_caddr(volatile uint8_t *shm) {
    return shm[CHA_CADDR_LO]
         | (shm[CHA_CADDR_MID] << 8)
         | (shm[CHA_CADDR_HI] << 16)
         | (shm[CHA_CADDR_EXT] << 24);
}

static inline void bus_set_cdata(volatile uint8_t *shm, uint32_t data) {
    shm[CHA_CDATA_0] = data & 0xFF;
    shm[CHA_CDATA_1] = (data >> 8) & 0xFF;
    shm[CHA_CDATA_2] = (data >> 16) & 0xFF;
    shm[CHA_CDATA_3] = (data >> 24) & 0xFF;
}

static inline uint32_t bus_get_cdata(volatile uint8_t *shm) {
    return shm[CHA_CDATA_0]
         | (shm[CHA_CDATA_1] << 8)
         | (shm[CHA_CDATA_2] << 16)
         | (shm[CHA_CDATA_3] << 24);
}

static inline void bus_set_saddr(volatile uint8_t *shm, uint32_t addr) {
    shm[CHA_SADDR_LO]  = addr & 0xFF;
    shm[CHA_SADDR_HI]  = (addr >> 8) & 0xFF;
    shm[CHA_SADDR_EXT] = (addr >> 16) & 0xFF;
}

static inline uint32_t bus_get_saddr(volatile uint8_t *shm) {
    return shm[CHA_SADDR_LO] | (shm[CHA_SADDR_HI] << 8) | (shm[CHA_SADDR_EXT] << 16);
}

static inline void bus_set_maddr(volatile uint8_t *shm, uint32_t addr) {
    shm[CHA_MADDR_LO]  = addr & 0xFF;
    shm[CHA_MADDR_MID] = (addr >> 8) & 0xFF;
    shm[CHA_MADDR_HI]  = (shm[CHA_MADDR_HI] & 0xFE) | ((addr >> 16) & 0x01);
}

static inline uint32_t bus_get_maddr(volatile uint8_t *shm) {
    return shm[CHA_MADDR_LO]
         | (shm[CHA_MADDR_MID] << 8)
         | ((shm[CHA_MADDR_HI] & 0x01) << 16);
}


/* ═══════════════════════════════════════════════════════════════════
   Pin table for GUI visualization (name, byte, bit, direction)
   ═══════════════════════════════════════════════════════════════════ */

typedef struct {
    const char *name;
    uint8_t byte_offset;
    uint8_t bit_mask;   /* 0 = entire byte is the signal */
    uint8_t is_output;  /* 1 = cart drives this pin */
} neocart_pin_t;

#define PIN_IN  0
#define PIN_OUT 1

static const neocart_pin_t PROG_PINS[] = {
    /* Address bus — MVS drives */
    {"A1",  0, 1<<0, PIN_IN}, {"A2",  0, 1<<1, PIN_IN}, {"A3",  0, 1<<2, PIN_IN},
    {"A4",  0, 1<<3, PIN_IN}, {"A5",  0, 1<<4, PIN_IN}, {"A6",  0, 1<<5, PIN_IN},
    {"A7",  0, 1<<6, PIN_IN}, {"A8",  0, 1<<7, PIN_IN},
    {"A9",  1, 1<<0, PIN_IN}, {"A10", 1, 1<<1, PIN_IN}, {"A11", 1, 1<<2, PIN_IN},
    {"A12", 1, 1<<3, PIN_IN}, {"A13", 1, 1<<4, PIN_IN}, {"A14", 1, 1<<5, PIN_IN},
    {"A15", 1, 1<<6, PIN_IN}, {"A16", 1, 1<<7, PIN_IN},
    {"A17", 2, 1<<0, PIN_IN}, {"A18", 2, 1<<1, PIN_IN}, {"A19", 2, 1<<2, PIN_IN},
    {"A20", 2, 1<<3, PIN_IN}, {"A21", 2, 1<<4, PIN_IN}, {"A22", 2, 1<<5, PIN_IN},
    {"A23", 2, 1<<6, PIN_IN},
    {"nRW", 2, 1<<7, PIN_IN},
    /* Control — MVS drives */
    {"ROMOE",  3, 1<<0, PIN_IN}, {"ROMOEU", 3, 1<<1, PIN_IN},
    {"ROMOEL", 3, 1<<2, PIN_IN}, {"VROMOE", 3, 1<<3, PIN_IN},
    /* Data bus — Cart drives */
    {"D0",  4, 1<<0, PIN_OUT}, {"D1",  4, 1<<1, PIN_OUT}, {"D2",  4, 1<<2, PIN_OUT},
    {"D3",  4, 1<<3, PIN_OUT}, {"D4",  4, 1<<4, PIN_OUT}, {"D5",  4, 1<<5, PIN_OUT},
    {"D6",  4, 1<<6, PIN_OUT}, {"D7",  4, 1<<7, PIN_OUT},
    {"D8",  5, 1<<0, PIN_OUT}, {"D9",  5, 1<<1, PIN_OUT}, {"D10", 5, 1<<2, PIN_OUT},
    {"D11", 5, 1<<3, PIN_OUT}, {"D12", 5, 1<<4, PIN_OUT}, {"D13", 5, 1<<5, PIN_OUT},
    {"D14", 5, 1<<6, PIN_OUT}, {"D15", 5, 1<<7, PIN_OUT},
    /* V-ROM address — MVS drives */
    {"VA0", 6, 1<<0, PIN_IN}, {"VA1", 6, 1<<1, PIN_IN}, {"VA2", 6, 1<<2, PIN_IN},
    {"VA3", 6, 1<<3, PIN_IN}, {"VA4", 6, 1<<4, PIN_IN}, {"VA5", 6, 1<<5, PIN_IN},
    {"VA6", 6, 1<<6, PIN_IN}, {"VA7", 6, 1<<7, PIN_IN},
    {"VA8", 7, 1<<0, PIN_IN}, {"VA9", 7, 1<<1, PIN_IN}, {"VA10",7, 1<<2, PIN_IN},
    {"VA11",7, 1<<3, PIN_IN}, {"VA12",7, 1<<4, PIN_IN}, {"VA13",7, 1<<5, PIN_IN},
    {"VA14",7, 1<<6, PIN_IN}, {"VA15",7, 1<<7, PIN_IN},
    {"VA16",8, 1<<0, PIN_IN}, {"VA17",8, 1<<1, PIN_IN}, {"VA18",8, 1<<2, PIN_IN},
    {"VA19",8, 1<<3, PIN_IN}, {"VA20",8, 1<<4, PIN_IN}, {"VA21",8, 1<<5, PIN_IN},
    {"VA22",8, 1<<6, PIN_IN}, {"VA23",8, 1<<7, PIN_IN},
    /* V-ROM data — Cart drives */
    {"VD0", 9, 1<<0, PIN_OUT}, {"VD1", 9, 1<<1, PIN_OUT}, {"VD2", 9, 1<<2, PIN_OUT},
    {"VD3", 9, 1<<3, PIN_OUT}, {"VD4", 9, 1<<4, PIN_OUT}, {"VD5", 9, 1<<5, PIN_OUT},
    {"VD6", 9, 1<<6, PIN_OUT}, {"VD7", 9, 1<<7, PIN_OUT},
    /* Ack — Cart drives */
    {"DTACK", 10, 1<<0, PIN_OUT}, {"VDTACK", 10, 1<<1, PIN_OUT},
    {NULL, 0, 0, 0}
};

static const neocart_pin_t CHA_PINS[] = {
    /* C-ROM address — MVS drives */
    {"P0",  12, 1<<0, PIN_IN}, {"P1",  12, 1<<1, PIN_IN}, {"P2",  12, 1<<2, PIN_IN},
    {"P3",  12, 1<<3, PIN_IN}, {"P4",  12, 1<<4, PIN_IN}, {"P5",  12, 1<<5, PIN_IN},
    {"P6",  12, 1<<6, PIN_IN}, {"P7",  12, 1<<7, PIN_IN},
    {"P8",  13, 1<<0, PIN_IN}, {"P9",  13, 1<<1, PIN_IN}, {"P10", 13, 1<<2, PIN_IN},
    {"P11", 13, 1<<3, PIN_IN}, {"P12", 13, 1<<4, PIN_IN}, {"P13", 13, 1<<5, PIN_IN},
    {"P14", 13, 1<<6, PIN_IN}, {"P15", 13, 1<<7, PIN_IN},
    {"P16", 14, 1<<0, PIN_IN}, {"P17", 14, 1<<1, PIN_IN}, {"P18", 14, 1<<2, PIN_IN},
    {"P19", 14, 1<<3, PIN_IN}, {"P20", 14, 1<<4, PIN_IN}, {"P21", 14, 1<<5, PIN_IN},
    {"P22", 14, 1<<6, PIN_IN}, {"P23", 14, 1<<7, PIN_IN},
    /* Control — MVS drives */
    {"PCK1B", 15, 1<<0, PIN_IN}, {"PCK2B", 15, 1<<1, PIN_IN},
    {"SDMRD", 15, 1<<2, PIN_IN}, {"MROMOE",15, 1<<3, PIN_IN},
    /* C-ROM data — Cart drives */
    {"CR0",  16, 1<<0, PIN_OUT}, {"CR1",  16, 1<<1, PIN_OUT}, {"CR2",  16, 1<<2, PIN_OUT},
    {"CR3",  16, 1<<3, PIN_OUT}, {"CR4",  16, 1<<4, PIN_OUT}, {"CR5",  16, 1<<5, PIN_OUT},
    {"CR6",  16, 1<<6, PIN_OUT}, {"CR7",  16, 1<<7, PIN_OUT},
    {"CR8",  17, 1<<0, PIN_OUT}, {"CR9",  17, 1<<1, PIN_OUT}, {"CR10", 17, 1<<2, PIN_OUT},
    {"CR11", 17, 1<<3, PIN_OUT}, {"CR12", 17, 1<<4, PIN_OUT}, {"CR13", 17, 1<<5, PIN_OUT},
    {"CR14", 17, 1<<6, PIN_OUT}, {"CR15", 17, 1<<7, PIN_OUT},
    {"CR16", 18, 1<<0, PIN_OUT}, {"CR17", 18, 1<<1, PIN_OUT}, {"CR18", 18, 1<<2, PIN_OUT},
    {"CR19", 18, 1<<3, PIN_OUT}, {"CR20", 18, 1<<4, PIN_OUT}, {"CR21", 18, 1<<5, PIN_OUT},
    {"CR22", 18, 1<<6, PIN_OUT}, {"CR23", 18, 1<<7, PIN_OUT},
    {"CR24", 19, 1<<0, PIN_OUT}, {"CR25", 19, 1<<1, PIN_OUT}, {"CR26", 19, 1<<2, PIN_OUT},
    {"CR27", 19, 1<<3, PIN_OUT}, {"CR28", 19, 1<<4, PIN_OUT}, {"CR29", 19, 1<<5, PIN_OUT},
    {"CR30", 19, 1<<6, PIN_OUT}, {"CR31", 19, 1<<7, PIN_OUT},
    /* S-ROM address — MVS drives */
    {"SDA0", 20, 1<<0, PIN_IN}, {"SDA1", 20, 1<<1, PIN_IN}, {"SDA2", 20, 1<<2, PIN_IN},
    {"SDA3", 20, 1<<3, PIN_IN}, {"SDA4", 20, 1<<4, PIN_IN}, {"SDA5", 20, 1<<5, PIN_IN},
    {"SDA6", 20, 1<<6, PIN_IN}, {"SDA7", 20, 1<<7, PIN_IN},
    {"SDA8", 21, 1<<0, PIN_IN}, {"SDA9", 21, 1<<1, PIN_IN}, {"SDA10",21, 1<<2, PIN_IN},
    {"SDA11",21, 1<<3, PIN_IN}, {"SDA12",21, 1<<4, PIN_IN}, {"SDA13",21, 1<<5, PIN_IN},
    {"SDA14",21, 1<<6, PIN_IN}, {"SDA15",21, 1<<7, PIN_IN},
    /* S-ROM data — Cart drives */
    {"SDD0", 22, 1<<0, PIN_OUT}, {"SDD1", 22, 1<<1, PIN_OUT}, {"SDD2", 22, 1<<2, PIN_OUT},
    {"SDD3", 22, 1<<3, PIN_OUT}, {"SDD4", 22, 1<<4, PIN_OUT}, {"SDD5", 22, 1<<5, PIN_OUT},
    {"SDD6", 22, 1<<6, PIN_OUT}, {"SDD7", 22, 1<<7, PIN_OUT},
    /* M-ROM address — MVS drives */
    {"MA0", 23, 1<<0, PIN_IN}, {"MA1", 23, 1<<1, PIN_IN}, {"MA2", 23, 1<<2, PIN_IN},
    {"MA3", 23, 1<<3, PIN_IN}, {"MA4", 23, 1<<4, PIN_IN}, {"MA5", 23, 1<<5, PIN_IN},
    {"MA6", 23, 1<<6, PIN_IN}, {"MA7", 23, 1<<7, PIN_IN},
    {"MA8", 24, 1<<0, PIN_IN}, {"MA9", 24, 1<<1, PIN_IN}, {"MA10",24, 1<<2, PIN_IN},
    {"MA11",24, 1<<3, PIN_IN}, {"MA12",24, 1<<4, PIN_IN}, {"MA13",24, 1<<5, PIN_IN},
    {"MA14",24, 1<<6, PIN_IN}, {"MA15",24, 1<<7, PIN_IN},
    {"MA16",25, 1<<0, PIN_IN},
    /* M-ROM data — Cart drives */
    {"MD0", 26, 1<<0, PIN_OUT}, {"MD1", 26, 1<<1, PIN_OUT}, {"MD2", 26, 1<<2, PIN_OUT},
    {"MD3", 26, 1<<3, PIN_OUT}, {"MD4", 26, 1<<4, PIN_OUT}, {"MD5", 26, 1<<5, PIN_OUT},
    {"MD6", 26, 1<<6, PIN_OUT}, {"MD7", 26, 1<<7, PIN_OUT},
    {NULL, 0, 0, 0}
};

#endif /* NEOCART_BUS_H */
