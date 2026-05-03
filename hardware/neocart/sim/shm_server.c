/* NeoCart SHM server — pin-accurate, all atomic, SEQ_CST.
   Two threads: PROG (P-ROM + V-ROM) and CHA (C-ROM + S-ROM + M-ROM).
   Usage: ./shm_server game.neo
*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include "neocart_bus.h"

#define NEO_HEADER 4096

static volatile int running = 1;
void sighandler(int sig) { (void)sig; running = 0; }

static uint16_t *prom; static uint32_t prom_words;
static uint8_t *crom;  static uint32_t crom_size;
static uint8_t *srom;  static uint32_t srom_size;
static uint8_t *mrom;  static uint32_t mrom_size;
static uint8_t *v1rom; static uint32_t v1rom_size;

static volatile uint8_t *shm;
static uint64_t pc=0, vc=0, cc=0, sc=0, mc=0;

static inline void dbg_wait(void) {
    while (shm[DBG_PAUSE] && !shm[DBG_STEP] && running) ;
    if (shm[DBG_STEP]) shm[DBG_STEP] = 0;
}

void *prog_thread(void *arg) {
    (void)arg;
    while (running) {
        uint8_t ctrl = __atomic_load_n(&shm[PROG_CTRL], __ATOMIC_SEQ_CST);

        if (!(ctrl & PROG_ROMOE_n)) {
            uint32_t a = shm[PROG_ADDR_LO] | (shm[PROG_ADDR_MID]<<8) | (shm[PROG_ADDR_HI]<<16);
            uint32_t w = a / 2;
            uint16_t d = (w < prom_words) ? prom[w] : 0xFFFF;
            shm[PROG_DATA_LO] = d & 0xFF;
            shm[PROG_DATA_HI] = (d >> 8) & 0xFF;
            __sync_synchronize();
            __atomic_and_fetch(&shm[PROG_ACK], ~PROG_DTACK_n, __ATOMIC_SEQ_CST);
            while (!(__atomic_load_n(&shm[PROG_CTRL], __ATOMIC_SEQ_CST) & PROG_ROMOE_n) && running) ;
            __atomic_or_fetch(&shm[PROG_ACK], PROG_DTACK_n, __ATOMIC_SEQ_CST);
            pc++;
            dbg_wait();
        }

        if (!(ctrl & PROG_VROM_OE_n)) {
            uint32_t a = shm[PROG_VADDR_LO] | (shm[PROG_VADDR_MID]<<8) | (shm[PROG_VADDR_HI]<<16);
            uint8_t d = (v1rom && a < v1rom_size) ? v1rom[a] : 0;
            shm[PROG_VDATA] = d;
            __sync_synchronize();
            __atomic_and_fetch(&shm[PROG_ACK], ~PROG_VDTACK_n, __ATOMIC_SEQ_CST);
            while (!(__atomic_load_n(&shm[PROG_CTRL], __ATOMIC_SEQ_CST) & PROG_VROM_OE_n) && running) ;
            __atomic_or_fetch(&shm[PROG_ACK], PROG_VDTACK_n, __ATOMIC_SEQ_CST);
            vc++;
            dbg_wait();
        }
    }
    return NULL;
}

void *cha_thread(void *arg) {
    (void)arg;
    while (running) {
        uint8_t ctrl = __atomic_load_n(&shm[CHA_CTRL], __ATOMIC_SEQ_CST);

        if (!(ctrl & CHA_PCK1B)) {
            uint32_t a = shm[CHA_CADDR_LO] | (shm[CHA_CADDR_MID]<<8) | (shm[CHA_CADDR_HI]<<16) | (shm[CHA_CADDR_EXT]<<24);
            shm[CHA_CDATA_0] = (crom && a+0 < crom_size) ? crom[a+0] : 0;
            shm[CHA_CDATA_1] = (crom && a+1 < crom_size) ? crom[a+1] : 0;
            shm[CHA_CDATA_2] = (crom && a+2 < crom_size) ? crom[a+2] : 0;
            shm[CHA_CDATA_3] = (crom && a+3 < crom_size) ? crom[a+3] : 0;
            __sync_synchronize();
            __atomic_and_fetch(&shm[CHA_ACK], ~CHA_CROM_DTACK_n, __ATOMIC_SEQ_CST);
            while (!(__atomic_load_n(&shm[CHA_CTRL], __ATOMIC_SEQ_CST) & CHA_PCK1B) && running) ;
            __atomic_or_fetch(&shm[CHA_ACK], CHA_CROM_DTACK_n, __ATOMIC_SEQ_CST);
            cc++;
            dbg_wait();
        }

        if (!(ctrl & CHA_SROM_OE_n)) {
            uint32_t a = shm[CHA_SADDR_LO] | (shm[CHA_SADDR_HI]<<8) | (shm[CHA_SADDR_EXT]<<16);
            shm[CHA_SDATA] = (srom && a < srom_size) ? srom[a] : 0;
            __sync_synchronize();
            __atomic_and_fetch(&shm[CHA_ACK], ~CHA_SROM_DTACK_n, __ATOMIC_SEQ_CST);
            while (!(__atomic_load_n(&shm[CHA_CTRL], __ATOMIC_SEQ_CST) & CHA_SROM_OE_n) && running) ;
            __atomic_or_fetch(&shm[CHA_ACK], CHA_SROM_DTACK_n, __ATOMIC_SEQ_CST);
            sc++;
            dbg_wait();
        }

        if (!(ctrl & CHA_MROM_OE_n)) {
            uint32_t a = shm[CHA_MADDR_LO] | (shm[CHA_MADDR_MID]<<8) | ((shm[CHA_MADDR_HI]&1)<<16);
            shm[CHA_MDATA] = (mrom && a < mrom_size) ? mrom[a] : 0;
            __sync_synchronize();
            __atomic_and_fetch(&shm[CHA_ACK], ~CHA_MROM_DTACK_n, __ATOMIC_SEQ_CST);
            while (!(__atomic_load_n(&shm[CHA_CTRL], __ATOMIC_SEQ_CST) & CHA_MROM_OE_n) && running) ;
            __atomic_or_fetch(&shm[CHA_ACK], CHA_MROM_DTACK_n, __ATOMIC_SEQ_CST);
            mc++;
            dbg_wait();
        }
    }
    return NULL;
}

void *stats_thread(void *arg) {
    (void)arg;
    while (running) {
        sleep(5);
        printf("  P:%luM V:%luK C:%luM S:%luK M:%luK\n",
            pc/1000000, vc/1000, cc/1000000, sc/1000, mc/1000);
        fflush(stdout);
    }
    return NULL;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "Usage: %s game.neo\n", argv[0]); return 1; }

    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 1; }
    uint8_t hdr[NEO_HEADER];
    fread(hdr, 1, NEO_HEADER, f);
    if (memcmp(hdr, "NEO", 3)) { fprintf(stderr, "Not a .neo file\n"); return 1; }

    uint32_t p_size  = *(uint32_t*)(hdr+4);
    uint32_t s_size  = *(uint32_t*)(hdr+8);
    uint32_t m_size  = *(uint32_t*)(hdr+12);
    uint32_t v1_size = *(uint32_t*)(hdr+16);
    uint32_t v2_size = *(uint32_t*)(hdr+20);
    uint32_t c_size  = *(uint32_t*)(hdr+24);
    char name[33]={0}; memcpy(name, hdr+0x2C, 32);

    uint8_t *pr = malloc(p_size); fread(pr, 1, p_size, f);
    srom = s_size ? malloc(s_size) : NULL; if (srom) fread(srom, 1, s_size, f);
    mrom = m_size ? malloc(m_size) : NULL; if (mrom) fread(mrom, 1, m_size, f);
    uint8_t *v1 = v1_size ? malloc(v1_size) : NULL; if (v1) fread(v1, 1, v1_size, f);
    if (v2_size) fseek(f, v2_size, SEEK_CUR);
    crom = c_size ? malloc(c_size) : NULL; if (crom) fread(crom, 1, c_size, f);
    fclose(f);

    prom = (uint16_t*)pr; prom_words = p_size/2;
    v1rom = v1; v1rom_size = v1_size;
    srom_size = s_size; mrom_size = m_size; crom_size = c_size;

    printf("Game: %s\n", name);
    printf("P:%uKB S:%uKB M:%uKB V:%uKB C:%uMB\n",
        p_size/1024, s_size/1024, m_size/1024, v1_size/1024, c_size/(1024*1024));

    int fd = open(NEOCART_SHM_PATH, O_CREAT|O_RDWR|O_TRUNC, 0666);
    ftruncate(fd, NEOCART_SHM_SIZE);
    shm = mmap(NULL, NEOCART_SHM_SIZE, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    memset((void*)shm, 0, NEOCART_SHM_SIZE);
    shm[PROG_CTRL] = 0xFF;
    shm[PROG_ACK]  = 0xFF;
    shm[CHA_CTRL]  = 0xFF;
    shm[CHA_ACK]   = 0xFF;

    printf("Ready at %s\n", NEOCART_SHM_PATH);
    fflush(stdout);
    signal(SIGINT, sighandler);

    pthread_t t1, t2, t3;
    pthread_create(&t1, NULL, prog_thread, NULL);
    pthread_create(&t2, NULL, cha_thread, NULL);
    pthread_create(&t3, NULL, stats_thread, NULL);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    pthread_cancel(t3);

    printf("\nP:%lu V:%lu C:%lu S:%lu M:%lu\n", pc, vc, cc, sc, mc);
    unlink(NEOCART_SHM_PATH);
    free(pr); free(crom); free(srom); free(mrom); free(v1);
    return 0;
}
