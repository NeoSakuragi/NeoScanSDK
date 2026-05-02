/* NeoCart SHM client — pin-accurate MVS bus operations.
   Every signal uses atomic bit ops (&= / |=) with SEQ_CST ordering.
   CTRL byte driven by MVS (client), ACK byte driven by cart (server).

   PROG bus: byte 3 = CTRL, byte 10 = ACK
   CHA bus:  byte 15 = CTRL, byte 27 = ACK
*/
#include <stdio.h>
#include <stdint.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include "neocart_bus.h"

static volatile uint8_t *shm;

int cart_init(const char *u) {
    (void)u;
    int fd = open(NEOCART_SHM_PATH, O_RDWR);
    if (fd < 0) { perror("SHM_CLIENT: open"); return -1; }
    shm = mmap(NULL, NEOCART_SHM_SIZE, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (shm == MAP_FAILED) { perror("SHM_CLIENT: mmap"); return -1; }
    printf("SHM_CLIENT: connected (pin-accurate, %d bytes)\n", NEOCART_SHM_SIZE);
    return 0;
}

/* ═══ P-ROM read: ROMOE + DTACK on PROG bus ═══ */
uint16_t cart_read(uint32_t byte_addr) {
    shm[PROG_ADDR_LO]  = byte_addr & 0xFF;
    shm[PROG_ADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[PROG_ADDR_HI]  = (byte_addr >> 16) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[PROG_CTRL], ~PROG_ROMOE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[PROG_ACK], __ATOMIC_SEQ_CST) & PROG_DTACK_n)
        ;

    uint16_t data = shm[PROG_DATA_LO] | (shm[PROG_DATA_HI] << 8);

    __atomic_or_fetch(&shm[PROG_CTRL], PROG_ROMOE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[PROG_ACK], __ATOMIC_SEQ_CST) & PROG_DTACK_n))
        ;

    return data;
}

/* ═══ C-ROM byte read: PCK1B + CROM_DTACK on CHA bus ═══ */
uint8_t cart_read_crom_byte(uint32_t byte_addr) {
    shm[CHA_CADDR_LO]  = byte_addr & 0xFF;
    shm[CHA_CADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[CHA_CADDR_HI]  = (byte_addr >> 16) & 0xFF;
    shm[CHA_CADDR_EXT] = (byte_addr >> 24) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[CHA_CTRL], ~CHA_PCK1B, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[CHA_ACK], __ATOMIC_SEQ_CST) & CHA_CROM_DTACK_n)
        ;

    uint8_t data = shm[CHA_CDATA_0];

    __atomic_or_fetch(&shm[CHA_CTRL], CHA_PCK1B, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[CHA_ACK], __ATOMIC_SEQ_CST) & CHA_CROM_DTACK_n))
        ;

    return data;
}

/* ═══ S-ROM read: SROM_OE + SROM_DTACK on CHA bus ═══ */
uint8_t cart_read_srom_byte(uint32_t byte_addr) {
    shm[CHA_SADDR_LO] = byte_addr & 0xFF;
    shm[CHA_SADDR_HI] = (byte_addr >> 8) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[CHA_CTRL], ~CHA_SROM_OE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[CHA_ACK], __ATOMIC_SEQ_CST) & CHA_SROM_DTACK_n)
        ;

    uint8_t data = shm[CHA_SDATA];

    __atomic_or_fetch(&shm[CHA_CTRL], CHA_SROM_OE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[CHA_ACK], __ATOMIC_SEQ_CST) & CHA_SROM_DTACK_n))
        ;

    return data;
}

/* ═══ M-ROM read: MROM_OE + MROM_DTACK on CHA bus ═══ */
uint8_t cart_read_mrom_byte(uint32_t byte_addr) {
    shm[CHA_MADDR_LO]  = byte_addr & 0xFF;
    shm[CHA_MADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[CHA_MADDR_HI]  = (byte_addr >> 16) & 0x01;
    __sync_synchronize();

    __atomic_and_fetch(&shm[CHA_CTRL], ~CHA_MROM_OE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[CHA_ACK], __ATOMIC_SEQ_CST) & CHA_MROM_DTACK_n)
        ;

    uint8_t data = shm[CHA_MDATA];

    __atomic_or_fetch(&shm[CHA_CTRL], CHA_MROM_OE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[CHA_ACK], __ATOMIC_SEQ_CST) & CHA_MROM_DTACK_n))
        ;

    return data;
}

/* ═══ V-ROM read: VROM_OE + VROM_DTACK on PROG bus ═══ */
uint8_t cart_read_vrom_byte(uint32_t byte_addr) {
    shm[PROG_VADDR_LO]  = byte_addr & 0xFF;
    shm[PROG_VADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[PROG_VADDR_HI]  = (byte_addr >> 16) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[PROG_CTRL], ~PROG_VROM_OE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[PROG_ACK], __ATOMIC_SEQ_CST) & PROG_VDTACK_n)
        ;

    uint8_t data = shm[PROG_VDATA];

    __atomic_or_fetch(&shm[PROG_CTRL], PROG_VROM_OE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[PROG_ACK], __ATOMIC_SEQ_CST) & PROG_VDTACK_n))
        ;

    return data;
}

void cart_write(uint32_t a, uint16_t d) { (void)a; (void)d; }
void cart_reset(void) {}
void cart_destroy(void) {}
