/* Shared memory ROM server — serves both P-ROM and C-ROM.
   Protocol: single seq counter at shm[7].
   Address bit 31: 0=P-ROM (uint16 word), 1=C-ROM (byte in low 8 bits of response).
*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>

#define SHM_PATH "/dev/shm/neocart_rom"
#define SHM_SIZE 16

static volatile int running = 1;
void sighandler(int sig) { (void)sig; running = 0; }

static uint8_t *load_file(const char *path, size_t *out_size) {
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "Cannot open %s\n", path); exit(1); }
    fseek(f, 0, SEEK_END); *out_size = ftell(f); rewind(f);
    uint8_t *buf = malloc(*out_size);
    fread(buf, 1, *out_size, f); fclose(f);
    return buf;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;

    /* ── P-ROM ── */
    size_t p1_sz, p2_sz;
    uint8_t *p1 = load_file("/home/bruno/NeoGeo/roms/rbff2/240-p1.p1", &p1_sz);
    uint8_t *p2 = load_file("/home/bruno/NeoGeo/roms/rbff2/240-p2.sp2", &p2_sz);
    size_t prom_total = p1_sz + p2_sz;
    uint8_t *prom_raw = malloc(prom_total);
    memcpy(prom_raw, p1, p1_sz);
    memcpy(prom_raw + p1_sz, p2, p2_sz);
    free(p1); free(p2);
    uint16_t *prom = (uint16_t *)prom_raw;
    size_t prom_words = prom_total / 2;
    printf("P-ROM: %zu words\n", prom_words);

    /* ── C-ROM (interleaved byte pairs: c1+c2, c3+c4, c5+c6) ── */
    const char *c_files[] = {
        "/home/bruno/NeoGeo/roms/rbff2/240-c1.c1",
        "/home/bruno/NeoGeo/roms/rbff2/240-c2.c2",
        "/home/bruno/NeoGeo/roms/rbff2/240-c3.c3",
        "/home/bruno/NeoGeo/roms/rbff2/240-c4.c4",
        "/home/bruno/NeoGeo/roms/rbff2/240-c5.c5",
        "/home/bruno/NeoGeo/roms/rbff2/240-c6.c6",
    };
    int num_c = 6;
    size_t c_file_sz;
    uint8_t *c_data[6];
    for (int i = 0; i < num_c; i++)
        c_data[i] = load_file(c_files[i], &c_file_sz);

    size_t crom_total = c_file_sz * num_c;  /* 48MB total */
    /* Interleave: each pair (c1+c2) goes into even/odd bytes */
    uint8_t *crom = malloc(crom_total);
    for (int pair = 0; pair < num_c / 2; pair++) {
        uint8_t *even = c_data[pair * 2];
        uint8_t *odd  = c_data[pair * 2 + 1];
        size_t base = pair * c_file_sz * 2;
        for (size_t i = 0; i < c_file_sz; i++) {
            crom[base + i * 2]     = even[i];
            crom[base + i * 2 + 1] = odd[i];
        }
    }
    size_t crom_bytes = crom_total;
    for (int i = 0; i < num_c; i++) free(c_data[i]);

    printf("C-ROM: %zu bytes (%zu MB) — C2 toggles every second\n", crom_bytes, crom_bytes / (1024*1024));

    /* ── Shared memory ── */
    int fd = open(SHM_PATH, O_CREAT | O_RDWR | O_TRUNC, 0666);
    ftruncate(fd, SHM_SIZE);
    volatile uint8_t *shm = mmap(NULL, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    memset((void*)shm, 0, SHM_SIZE);

    printf("Ready at %s — P-ROM + C-ROM\n", SHM_PATH);
    signal(SIGINT, sighandler);

    uint8_t expect_seq = 1;
    uint64_t p_count = 0, c_count = 0;

    while (running) {
        while (__atomic_load_n(&shm[7], __ATOMIC_ACQUIRE) != expect_seq && running)
            ;
        if (!running) break;

        uint32_t addr = *(volatile uint32_t *)&shm[0];
        uint16_t resp;

        if (addr & 0x80000000) {
            /* C-ROM byte read */
            uint32_t caddr = addr & 0x7FFFFFFF;
            resp = (caddr < crom_bytes) ? crom[caddr] : 0x00;
            /* Toggle C2 corruption: odd bytes in first pair, every other second */
            if (caddr < c_file_sz * 2 && (caddr & 1)) {
                struct timespec ts;
                clock_gettime(CLOCK_MONOTONIC, &ts);
                if (ts.tv_sec & 1)
                    resp = 0x00;
            }
            c_count++;
            if (c_count <= 5 || c_count % 5000000 == 0)
                printf("  C[%lu]: 0x%06X=0x%02X\n", c_count, caddr, resp);
        } else {
            /* P-ROM word read */
            uint32_t word_idx = addr / 2;
            resp = (word_idx < prom_words) ? prom[word_idx] : 0xFFFF;
            p_count++;
            if (p_count % 5000000 == 0)
                printf("  P: %luM reads\n", p_count / 1000000);
        }

        *(volatile uint16_t *)&shm[4] = resp;
        __sync_synchronize();
        shm[7] = expect_seq + 1;
        expect_seq += 2;

        if ((p_count + c_count) % 50000000 == 0)
            printf("  total: %luM P + %luM C\n", p_count/1000000, c_count/1000000);
    }

    printf("\nDone: %lu P-ROM + %lu C-ROM reads\n", p_count, c_count);
    unlink(SHM_PATH);
    free(prom_raw);
    free(crom);
    return 0;
}
