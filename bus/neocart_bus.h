/* neocart_bus.h — MVS cart edge connector as shared memory.
   Each ROM type on its own 64-byte cache line to avoid false sharing.

   Client (emulator) writes address + asserts CTRL.
   Server (cart) writes data + asserts DTACK.
   GUI reads everything for visualization.
*/
#ifndef NEOCART_BUS_H
#define NEOCART_BUS_H

#include <stdint.h>

#define NEOCART_SHM_PATH "/dev/shm/neocart_bus"
#define NEOCART_SHM_SIZE 448   /* 7 x 64-byte cache lines */
#define NEOCART_LINE     64


/* ═══════════════════════════════════════════════════════════════════
   Line 0 (offset 0): PROG bus — P-ROM + V-ROM
   ═══════════════════════════════════════════════════════════════════ */

#define PROG_ADDR_LO    0   /* A[7:0]                */
#define PROG_ADDR_MID   1   /* A[15:8]               */
#define PROG_ADDR_HI    2   /* A[18:16], region, nRW */
#define PROG_CTRL       3
#define PROG_DATA_LO    4   /* D[7:0]                */
#define PROG_DATA_HI    5   /* D[15:8]               */
#define PROG_ACK        6

#define PROG_ROMOE_n    (1 << 0)
#define PROG_ROMOEU_n   (1 << 1)
#define PROG_ROMOEL_n   (1 << 2)
#define PROG_DTACK_n    (1 << 0)


/* ═══════════════════════════════════════════════════════════════════
   Line 1 (offset 64): C-ROM
   ═══════════════════════════════════════════════════════════════════ */

#define CROM_ADDR_LO    64  /* P[7:0]    */
#define CROM_ADDR_MID   65  /* P[15:8]   */
#define CROM_ADDR_HI    66  /* P[23:16]  */
#define CROM_ADDR_EXT   67  /* P[31:24]  */
#define CROM_CTRL       68
#define CROM_DATA_0     69  /* CR[7:0]   */
#define CROM_DATA_1     70  /* CR[15:8]  */
#define CROM_DATA_2     71  /* CR[23:16] */
#define CROM_DATA_3     72  /* CR[31:24] */
#define CROM_ACK        73

#define CROM_PCK1B_n    (1 << 0)
#define CROM_DTACK_n    (1 << 0)


/* ═══════════════════════════════════════════════════════════════════
   Line 2 (offset 128): S-ROM
   ═══════════════════════════════════════════════════════════════════ */

#define SROM_ADDR_LO    128
#define SROM_ADDR_HI    129
#define SROM_ADDR_EXT   130
#define SROM_CTRL       131
#define SROM_DATA       132
#define SROM_ACK        133

#define SROM_OE_n       (1 << 0)
#define SROM_DTACK_n    (1 << 0)


/* ═══════════════════════════════════════════════════════════════════
   Line 3 (offset 192): M-ROM
   ═══════════════════════════════════════════════════════════════════ */

#define MROM_ADDR_LO    192
#define MROM_ADDR_MID   193
#define MROM_ADDR_HI    194
#define MROM_CTRL       195
#define MROM_DATA       196
#define MROM_ACK        197

#define MROM_OE_n       (1 << 0)
#define MROM_DTACK_n    (1 << 0)


/* ═══════════════════════════════════════════════════════════════════
   Line 5 (offset 320): V-ROM (YM2610 ADPCM)
   ═══════════════════════════════════════════════════════════════════ */

#define VROM_ADDR_LO    320
#define VROM_ADDR_MID   321
#define VROM_ADDR_HI    322
#define VROM_CTRL       323
#define VROM_DATA       324
#define VROM_ACK        325

#define VROM_OE_n       (1 << 0)
#define VROM_DTACK_n    (1 << 0)


/* ═══════════════════════════════════════════════════════════════════
   Line 6 (offset 384): Debug / control
   ═══════════════════════════════════════════════════════════════════ */

#define DBG_SKELETON    384
#define DBG_PAUSE       385
#define DBG_STEP        386


/* ═══════════════════════════════════════════════════════════════════
   Backward-compat aliases (old CHA_ names → new per-ROM names)
   ═══════════════════════════════════════════════════════════════════ */

#define CHA_CADDR_LO    CROM_ADDR_LO
#define CHA_CADDR_MID   CROM_ADDR_MID
#define CHA_CADDR_HI    CROM_ADDR_HI
#define CHA_CADDR_EXT   CROM_ADDR_EXT
#define CHA_CDATA_0     CROM_DATA_0
#define CHA_CDATA_1     CROM_DATA_1
#define CHA_CDATA_2     CROM_DATA_2
#define CHA_CDATA_3     CROM_DATA_3

#define CHA_SADDR_LO    SROM_ADDR_LO
#define CHA_SADDR_HI    SROM_ADDR_HI
#define CHA_SADDR_EXT   SROM_ADDR_EXT
#define CHA_SDATA        SROM_DATA

#define CHA_MADDR_LO    MROM_ADDR_LO
#define CHA_MADDR_MID   MROM_ADDR_MID
#define CHA_MADDR_HI    MROM_ADDR_HI
#define CHA_MDATA        MROM_DATA

#endif /* NEOCART_BUS_H */
