/* Shared memory ROM client — MAME writes address, reads data from shared memory */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

/* Shared memory layout:
   offset 0: request_addr  (uint32_t) — MAME writes the byte address here
   offset 4: response_data (uint16_t) — server writes the ROM word here
   offset 6: ready         (uint8_t)  — server sets to 1 when response is ready
   offset 7: request_flag  (uint8_t)  — MAME sets to 1 to signal a request
*/

#define SHM_PATH "/dev/shm/neocart_rom"
#define SHM_SIZE 16

static volatile uint32_t *req_addr;
static volatile uint16_t *resp_data;
static volatile uint8_t  *ready_flag;
static volatile uint8_t  *request_flag;

int cart_init(const char *unused) {
    (void)unused;
    int fd = open(SHM_PATH, O_RDWR);
    if (fd < 0) {
        perror("SHM_CLIENT: open");
        return -1;
    }
    void *ptr = mmap(NULL, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (ptr == MAP_FAILED) {
        perror("SHM_CLIENT: mmap");
        return -1;
    }
    req_addr     = (volatile uint32_t *)(ptr);
    resp_data    = (volatile uint16_t *)(ptr + 4);
    ready_flag   = (volatile uint8_t  *)(ptr + 6);
    request_flag = (volatile uint8_t  *)(ptr + 7);

    *ready_flag = 0;
    *request_flag = 0;
    printf("SHM_CLIENT: connected to shared memory\n");
    return 0;
}

uint16_t cart_read(uint32_t byte_addr) {
    *ready_flag = 0;
    *req_addr = byte_addr;
    __sync_synchronize();
    *request_flag = 1;

    while (!*ready_flag)
        ;

    return *resp_data;
}

void cart_write(uint32_t byte_addr, uint16_t data) {
    (void)byte_addr;
    (void)data;
}

void cart_reset(void) {}
void cart_destroy(void) {}
