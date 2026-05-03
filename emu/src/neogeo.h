#ifndef NGEMU_H
#define NGEMU_H

#include <stdint.h>
#include <stdbool.h>

/* Timing */
#define NG_SCREEN_W       320
#define NG_SCREEN_H       224
#define NG_TOTAL_LINES    264
#define NG_VBLANK_LINE    249
#define NG_68K_CLOCK      12000000
#define NG_FPS            (6000000.0 / (264.0 * 384.0))
#define NG_CYCLES_PER_LINE ((int)(NG_68K_CLOCK / NG_FPS / NG_TOTAL_LINES))

/* ROM sizes */
#define NG_BIOS_SIZE   (128 * 1024)
#define NG_WRAM_SIZE   (64 * 1024)
#define NG_SFIX_SIZE   (128 * 1024)
#define NG_LOROM_SIZE  (128 * 1024)
#define NG_PALRAM_SIZE (8192)
#define NG_VRAM_SIZE   (128 * 1024)

typedef struct {
    /* ROMs */
    uint8_t  *bios;
    uint8_t  *sfix;
    uint8_t  *lorom;
    uint8_t  *prom;     uint32_t prom_size;
    uint8_t  *srom;     uint32_t srom_size;
    uint8_t  *mrom;     uint32_t mrom_size;
    uint8_t  *v1rom;    uint32_t v1rom_size;
    uint8_t  *crom;     uint32_t crom_size;

    /* RAM */
    uint8_t  wram[NG_WRAM_SIZE];
    uint8_t  palram[NG_PALRAM_SIZE];
    uint8_t  sram[0x10000];
    uint16_t vram[NG_VRAM_SIZE / 2];

    /* LSPC state */
    uint16_t vram_addr;
    uint16_t vram_mod;
    uint16_t vram_latch;
    int      scanline;

    /* Video output */
    uint32_t framebuf[NG_SCREEN_W * NG_SCREEN_H];
    uint32_t pal_cache[2][4096];
    uint8_t  pal_bank;

    /* System state */
    uint8_t  bios_vec;          /* 1 = BIOS at $000000, 0 = cart */
    uint8_t  fix_layer;         /* 0 = BIOS SFIX ($3A000B), 1 = cart SROM ($3A0011) */
    uint8_t  sram_lock;         /* 1 = SRAM locked ($3A000D) */
    uint8_t  sound_cmd;
    uint8_t  sound_reply;
    int      sound_ack_delay;    /* VBlanks until sound reply toggles (Z80 boot sim) */

    /* Input (active-high: bit set = button pressed) */
    uint8_t  p1;
    uint8_t  p2;
    uint8_t  sys;               /* coin/start/service */

    /* Runtime */
    bool     running;
    int      bypass_bios;
    char     game_name[33];
} ng_t;

extern ng_t ng;

void ng_init(void);
void ng_reset(void);
void ng_reset_direct(void);
int  ng_reset_savestate(const char *statepath);
void ng_frame(void);
void ng_shutdown(void);

int  ng_load_neo(const char *path);
int  ng_load_bios(const char *path);

void ng_mem_init(void);

void ng_vid_init(void);
void ng_vid_render_line(int line);
void ng_pal_write(uint32_t offset, uint16_t val);

void ng_input_init(void);
void ng_input_poll(void);

void ng_cal_write(uint8_t data);
uint8_t ng_cal_read(void);

int  ng_display_init(void);
void ng_display_present(void);
void ng_display_shutdown(void);

#endif
