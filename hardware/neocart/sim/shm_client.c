/* NeoCart SHM client — pin-accurate MVS bus operations.
   Each ROM type on its own 64-byte cache line.
   CTRL driven by MVS (client), ACK driven by cart (server).
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
    printf("SHM_CLIENT: connected (%d bytes, cache-line aligned)\n", NEOCART_SHM_SIZE);
    return 0;
}

/* ═══ P-ROM read: ROMOE + DTACK on PROG line ═══ */
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

/* ═══ C-ROM 32-bit read: PCK1B + DTACK on CROM line ═══ */
uint32_t cart_read_crom32(uint32_t byte_addr) {
    shm[CROM_ADDR_LO]  = byte_addr & 0xFF;
    shm[CROM_ADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[CROM_ADDR_HI]  = (byte_addr >> 16) & 0xFF;
    shm[CROM_ADDR_EXT] = (byte_addr >> 24) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[CROM_CTRL], ~CROM_PCK1B_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[CROM_ACK], __ATOMIC_SEQ_CST) & CROM_DTACK_n)
        ;

    uint32_t data = shm[CROM_DATA_0]
                  | (shm[CROM_DATA_1] << 8)
                  | (shm[CROM_DATA_2] << 16)
                  | (shm[CROM_DATA_3] << 24);

    __atomic_or_fetch(&shm[CROM_CTRL], CROM_PCK1B_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[CROM_ACK], __ATOMIC_SEQ_CST) & CROM_DTACK_n))
        ;

    return data;
}

/* ═══ C-ROM byte read: PCK1B + DTACK on CROM line ═══ */
uint8_t cart_read_crom_byte(uint32_t byte_addr) {
    shm[CROM_ADDR_LO]  = byte_addr & 0xFF;
    shm[CROM_ADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[CROM_ADDR_HI]  = (byte_addr >> 16) & 0xFF;
    shm[CROM_ADDR_EXT] = (byte_addr >> 24) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[CROM_CTRL], ~CROM_PCK1B_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[CROM_ACK], __ATOMIC_SEQ_CST) & CROM_DTACK_n)
        ;

    uint8_t data = shm[CROM_DATA_0];

    __atomic_or_fetch(&shm[CROM_CTRL], CROM_PCK1B_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[CROM_ACK], __ATOMIC_SEQ_CST) & CROM_DTACK_n))
        ;

    return data;
}

/* ═══ S-ROM read: OE + DTACK on SROM line ═══ */
uint8_t cart_read_srom_byte(uint32_t byte_addr) {
    shm[SROM_ADDR_LO]  = byte_addr & 0xFF;
    shm[SROM_ADDR_HI]  = (byte_addr >> 8) & 0xFF;
    shm[SROM_ADDR_EXT] = (byte_addr >> 16) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[SROM_CTRL], ~SROM_OE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[SROM_ACK], __ATOMIC_SEQ_CST) & SROM_DTACK_n)
        ;

    uint8_t data = shm[SROM_DATA];

    __atomic_or_fetch(&shm[SROM_CTRL], SROM_OE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[SROM_ACK], __ATOMIC_SEQ_CST) & SROM_DTACK_n))
        ;

    return data;
}

/* ═══ M-ROM read: OE + DTACK on MROM line ═══ */
uint8_t cart_read_mrom_byte(uint32_t byte_addr) {
    shm[MROM_ADDR_LO]  = byte_addr & 0xFF;
    shm[MROM_ADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[MROM_ADDR_HI]  = (byte_addr >> 16) & 0x01;
    __sync_synchronize();

    __atomic_and_fetch(&shm[MROM_CTRL], ~MROM_OE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[MROM_ACK], __ATOMIC_SEQ_CST) & MROM_DTACK_n)
        ;

    uint8_t data = shm[MROM_DATA];

    __atomic_or_fetch(&shm[MROM_CTRL], MROM_OE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[MROM_ACK], __ATOMIC_SEQ_CST) & MROM_DTACK_n))
        ;

    return data;
}

/* ═══ V-ROM read: OE + DTACK on VROM line ═══ */
uint8_t cart_read_vrom_byte(uint32_t byte_addr) {
    shm[VROM_ADDR_LO]  = byte_addr & 0xFF;
    shm[VROM_ADDR_MID] = (byte_addr >> 8) & 0xFF;
    shm[VROM_ADDR_HI]  = (byte_addr >> 16) & 0xFF;
    __sync_synchronize();

    __atomic_and_fetch(&shm[VROM_CTRL], ~VROM_OE_n, __ATOMIC_SEQ_CST);

    while (__atomic_load_n(&shm[VROM_ACK], __ATOMIC_SEQ_CST) & VROM_DTACK_n)
        ;

    uint8_t data = shm[VROM_DATA];

    __atomic_or_fetch(&shm[VROM_CTRL], VROM_OE_n, __ATOMIC_SEQ_CST);

    while (!(__atomic_load_n(&shm[VROM_ACK], __ATOMIC_SEQ_CST) & VROM_DTACK_n))
        ;

    return data;
}

void cart_write(uint32_t a, uint16_t d) { (void)a; (void)d; }
void cart_reset(void) {}
void cart_destroy(void) {}
