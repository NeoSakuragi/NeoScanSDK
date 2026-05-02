/* Shared memory ROM client — single-flag protocol.
   Layout (16 bytes):
   [0..3]  address   (client writes)
   [4..5]  data      (server writes)
   [6]     unused
   [7]     seq       (0=idle, odd=request pending, even=response ready)
   Client writes address, then sets seq to odd. Server reads address,
   looks up data, writes data, then sets seq to seq+1 (even).
   Client spins until seq is even, reads data.
*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

#define SHM_PATH "/dev/shm/neocart_rom"
#define SHM_SIZE 16

static volatile uint8_t *shm;
static uint8_t seq = 0;

int cart_init(const char *unused) {
    (void)unused;
    int fd = open(SHM_PATH, O_RDWR);
    if (fd < 0) { perror("SHM_CLIENT: open"); return -1; }
    shm = (volatile uint8_t *)mmap(NULL, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (shm == MAP_FAILED) { perror("SHM_CLIENT: mmap"); return -1; }
    shm[7] = 0;
    seq = 0;
    __sync_synchronize();
    printf("SHM_CLIENT: connected to shared memory\n");
    return 0;
}

uint16_t cart_read(uint32_t byte_addr) {
    *(volatile uint32_t *)&shm[0] = byte_addr;
    seq++;  /* odd = request */
    __sync_synchronize();
    shm[7] = seq;

    while (__atomic_load_n(&shm[7], __ATOMIC_ACQUIRE) != (uint8_t)(seq + 1))
        ;

    seq++;  /* now even = matches server */
    return *(volatile uint16_t *)&shm[4];
}

uint8_t cart_read_crom_byte(uint32_t byte_addr) {
    return (uint8_t)cart_read(byte_addr | 0x80000000);
}

void cart_write(uint32_t byte_addr, uint16_t data) {
    (void)byte_addr; (void)data;
}
void cart_reset(void) {}
void cart_destroy(void) {}
