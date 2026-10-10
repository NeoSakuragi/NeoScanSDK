/* The Character Lab's pack swap: see pack_swap.h. The pack's layout is tools/brawler/lab_pack.py's (little-endian):
 * 'NGPK', u16 version 1, u16 regions, u32 manifest bytes, u32 x 6 the ROM sizes (P S M V1 V2 C, as the .neo header), the
 * manifest, then from a 4-byte boundary per region: u8 rom, 3 zero bytes, u32 offset, u32 length, u32 zeros, the length
 * bytes (4-aligned), then zeros bytes of 0 to write after them (the region's blank end).
 * Offsets and bytes are the .neo's: its P keeps each 16-bit word low byte first, Geolith swaps them at load, so a P byte
 * at offset i goes to i ^ 1. Geolith decodes nothing from the ROMs (tiles, samples, the M ROM's banks are read as they
 * are), so the copy is the whole swap; the reset afterwards runs the shell's program again with the new data. */
#include <string.h>
#include "pack_swap.h"

static uint32_t rd16(const uint8_t *p) { return p[0] | p[1] << 8; }
static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }

static int walk(const uint8_t *pk, size_t n, ngpk_rom_fn rom, int copy) {
    uint32_t nreg, mlen, i, k;
    size_t o, sz[6];
    uint8_t *base[6];
    if (n < 36) return NGPK_SHORT;
    if (memcmp(pk, "NGPK", 4)) return NGPK_MAGIC;
    if (rd16(pk + 4) != 1) return NGPK_VERSION;
    nreg = rd16(pk + 6); mlen = rd32(pk + 8);
    for (k = 0; k < 6; k++) {
        uint32_t want = rd32(pk + 12 + 4 * k);
        base[k] = rom((int)k, &sz[k]);
        if (!want) continue;                           /* (a single V ROM, the .neo's V2 0: Geolith's V2 is V1) */
        if (!base[k]) return NGPK_NOROM;
        if (sz[k] != want) return NGPK_SIZES;          /* made for another shell (or another ROM) */
    }
    o = 36 + (size_t)mlen; o += (4 - o % 4) % 4;
    for (i = 0; i < nreg; i++) {
        uint32_t r, off, len, zero;
        if (o + 16 > n) return NGPK_SHORT;
        r = pk[o]; off = rd32(pk + o + 4); len = rd32(pk + o + 8); zero = rd32(pk + o + 12); o += 16;
        if (r > 5 || !base[r]) return NGPK_NOROM;
        if (len > n - o) return NGPK_SHORT;
        if (off > sz[r] || len > sz[r] - off || zero > sz[r] - off - len) return NGPK_BOUNDS;
        if (r == 0 && ((off | len | zero) & 1)) return NGPK_ODD;
        if (copy) {
            if (r == 0) { uint32_t j; for (j = 0; j < len; j++) base[0][off + (j ^ 1)] = pk[o + j]; }
            else memcpy(base[r] + off, pk + o, len);
            memset(base[r] + off + len, 0, zero);
        }
        o += len; o += (4 - o % 4) % 4;
    }
    return NGPK_OK;
}

int ngpk_apply(const uint8_t *pk, size_t n, ngpk_rom_fn rom) {
    int e = walk(pk, n, rom, 0);                        /* every check before the first byte is written */
    return e ? e : walk(pk, n, rom, 1);
}

const char *ngpk_error(int e) {
    switch (e) {
    case NGPK_OK: return "ok";
    case NGPK_SHORT: return "the pack is cut short";
    case NGPK_MAGIC: return "not a character pack";
    case NGPK_VERSION: return "a pack version this core does not read";
    case NGPK_SIZES: return "made for another shell (its ROM sizes differ)";
    case NGPK_BOUNDS: return "a region outside its ROM";
    case NGPK_ODD: return "a P region not on whole words";
    case NGPK_NOROM: return "a ROM the core has not loaded";
    default: return "unknown error";
    }
}
