/* YM2610 for the browser: Geolith's C port of ymfm (geolith/src/ymfm), driven by register writes from JavaScript.
   V ROM (ADPCM-A and ADPCM-B share it on KOF98) lives in vrom[]; the page copies the sample ranges it needs there. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "ymfm.h"
#include "ymfm_opn.h"

#define VSIZE (16 << 20)
static uint8_t vrom[VSIZE];
static int16_t out[2 * 8192];
static int32_t o[3];

uint8_t ymfm_external_read(uint32_t type, uint32_t address) {
    (void)type;
    return address < VSIZE ? vrom[address] : 0;
}
void ymfm_external_write(uint32_t type, uint32_t address, uint8_t data) { (void)type; (void)address; (void)data; }
void ymfm_sync_mode_write(uint8_t data) { fm_engine_mode_write(data); }
void ymfm_sync_check_interrupts(void) { fm_engine_check_interrupts(); }
void ymfm_set_timer(uint32_t tnum, int32_t duration) { (void)tnum; (void)duration; }
void ymfm_set_busy_end(uint32_t clocks) { (void)clocks; }
bool ymfm_is_busy(void) { return false; }
void ymfm_update_irq(bool asserted) { (void)asserted; }

uint8_t *yw_vrom(void) { return vrom; }
int16_t *yw_out(void) { return out; }
void yw_init(void) { ym2610_init(); ym2610_set_fidelity(OPN_FIDELITY_MED); fm_engine_init(); ym2610_reset(); }
void yw_reset(void) { ym2610_reset(); }
/* port 0 = A (YM offsets 0/1), 1 = B (2/3) */
void yw_write(int port, int reg, int val) { ym2610_write(port * 2, reg); ym2610_write(port * 2 + 1, val); }
/* n stereo samples at 8 MHz / 144 = 55555.6 Hz into out[] (n <= 8192) */
void yw_run(int n) {
    for (int i = 0; i < n; i++) {
        ym2610_generate(o);
        int32_t l = o[0] + o[2], r = o[1] + o[2];
        out[2 * i] = l > 32767 ? 32767 : l < -32768 ? -32768 : l;
        out[2 * i + 1] = r > 32767 ? 32767 : r < -32768 ? -32768 : r;
    }
}

/* freestanding: the two libc calls ymfm makes */
void *memset(void *d, int c, size_t n) { uint8_t *p = d; while (n--) *p++ = (uint8_t)c; return d; }
void *memcpy(void *d, const void *s, size_t n) { uint8_t *p = d; const uint8_t *q = s; while (n--) *p++ = *q++; return d; }

/* save states are not used here: Geolith's serialiser, stubbed */
void geo_serial_push8(uint8_t *st, uint8_t v) { (void)st; (void)v; }
void geo_serial_push16(uint8_t *st, uint16_t v) { (void)st; (void)v; }
void geo_serial_push32(uint8_t *st, uint32_t v) { (void)st; (void)v; }
void geo_serial_push64(uint8_t *st, uint64_t v) { (void)st; (void)v; }
uint8_t geo_serial_pop8(uint8_t *st) { (void)st; return 0; }
uint16_t geo_serial_pop16(uint8_t *st) { (void)st; return 0; }
uint32_t geo_serial_pop32(uint8_t *st) { (void)st; return 0; }
uint64_t geo_serial_pop64(uint8_t *st) { (void)st; return 0; }
void geo_serial_pushblk(uint8_t *dst, uint8_t *src, size_t len) { (void)dst; (void)src; (void)len; }
void geo_serial_popblk(uint8_t *dst, uint8_t *src, size_t len) { (void)dst; (void)src; (void)len; }
