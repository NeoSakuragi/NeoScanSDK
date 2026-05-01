/* Shared memory ROM server — C version, no Python caching issues */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>

#define SHM_PATH "/dev/shm/neocart_rom"
#define SHM_SIZE 16

static volatile int running = 1;
static uint16_t *rom = NULL;
static size_t rom_words = 0;

void sighandler(int sig) { (void)sig; running = 0; }

int main(int argc, char **argv) {
    /* Load ROM */
    const char *p1_path = "/home/bruno/NeoGeo/roms/rbff2/240-p1.p1";
    const char *p2_path = "/home/bruno/NeoGeo/roms/rbff2/240-p2.sp2";

    FILE *f1 = fopen(p1_path, "rb"); fseek(f1, 0, SEEK_END); long s1 = ftell(f1); rewind(f1);
    FILE *f2 = fopen(p2_path, "rb"); fseek(f2, 0, SEEK_END); long s2 = ftell(f2); rewind(f2);

    size_t total = s1 + s2;
    uint8_t *raw = malloc(total);
    fread(raw, 1, s1, f1); fclose(f1);
    fread(raw + s1, 1, s2, f2); fclose(f2);

    rom_words = total / 2;
    rom = (uint16_t *)raw;
    /* ROM files are byte-swapped on disk. Read as little-endian uint16 = correct value. */
    printf("ROM: %zu words, word[0]=0x%04X word[1]=0x%04X\n", rom_words, rom[0], rom[1]);

    /* Create shared memory file */
    int fd = open(SHM_PATH, O_CREAT | O_RDWR | O_TRUNC, 0666);
    ftruncate(fd, SHM_SIZE);
    volatile uint8_t *shm = mmap(NULL, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    memset((void*)shm, 0, SHM_SIZE);

    printf("Shared memory ready at %s — waiting for MAME\n", SHM_PATH);
    signal(SIGINT, sighandler);

    uint64_t count = 0;
    while (running) {
        /* Spin until request */
        while (__atomic_load_n(&shm[7], __ATOMIC_ACQUIRE) == 0 && running)
            ;
        if (!running) break;

        /* Read address */
        uint32_t addr = *(volatile uint32_t *)&shm[0];
        uint32_t word_idx = addr / 2;

        /* Lookup */
        uint16_t raw_word = (word_idx < rom_words) ? rom[word_idx] : 0xFFFF;
        uint16_t word = (raw_word >> 8) | (raw_word << 8);  /* byte-swap for 68K */

        /* Write response */
        *(volatile uint16_t *)&shm[4] = word;
        __sync_synchronize();
        shm[6] = 1;  /* ready */
        __sync_synchronize();
        shm[7] = 0;  /* clear request */

        count++;
        if (count % 5000000 == 0)
            printf("  %luM reads\n", count / 1000000);
    }

    printf("\nDone: %lu reads\n", count);
    unlink(SHM_PATH);
    free(raw);
    return 0;
}
