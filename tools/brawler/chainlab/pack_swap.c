/* The Character Lab's pack swap: see pack_swap.h; the format is tools/brawler/lab_pack.py's (docs/character_lab.md
 * "The pack format").
 * The pack (little-endian): 'NGPK', u16 1, u16 regions, u32 manifest bytes, u32 x 6 the ROM sizes of its build (not
 * checked: the shell's anchor decides), the manifest (JSON starting {"ngpk":{"format":N,"needs":"a b c"}), then from a
 * 4-byte boundary per region: u8 rom, u8 kind, u8 flags (1 = relocated), u8 0, u32 offset (its build's), u32 length,
 * u32 zeros, the length bytes (4-aligned), then zeros bytes of 0 to write after them (the region's blank end).
 * The shell's ANCHOR, in its P ROM at LABANCHOR (big-endian, as the 68000 reads it): 'NGLA', u16 format, u16 regions,
 * u8 slot id, u8 0, u16 features bytes, u32 JSON offset, u32 JSON bytes, then per region u8 kind, u8 rom, u16 0,
 * u32 offset, u32 size, then the features (space separated, NUL ended).
 * Offsets and bytes are the .neo's: its P keeps each 16-bit word low byte first, Geolith swaps them at load, so a P byte
 * at offset i is at i ^ 1 in the core (which keeps P in the 68000's own order: the anchor reads straight). Geolith decodes nothing from the ROMs (tiles, samples, the M ROM's banks are read as they
 * are), so the copy is the whole swap; the reset afterwards runs the shell's program again with the new data. */
#include <string.h>
#include "pack_swap.h"

#define LABANCHOR 0xDC000u     /* lab_pack.py LABANCHOR_AT */
#define MAXREG 16

static char why[512];

static uint32_t rd16(const uint8_t *p) { return p[0] | p[1] << 8; }
static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }

typedef struct { uint8_t kind, rom; uint32_t off, size; } areg_t;
typedef struct { unsigned fmt, nreg; areg_t r[MAXREG]; const uint8_t *p; size_t feat, flen; } anchor_t;

static unsigned pb(const anchor_t *a, size_t i) { return a->p[LABANCHOR + i]; }   /* the anchor's byte i (the core keeps P in the 68000's order) */
static uint32_t pw(const anchor_t *a, size_t i) { return pb(a, i) << 8 | pb(a, i + 1); }
static uint32_t pl(const anchor_t *a, size_t i) { return pw(a, i) << 16 | pw(a, i + 2); }

static int read_anchor(anchor_t *a, const uint8_t *p, size_t psz) {
    unsigned k;
    a->p = p;
    if (!p || psz < LABANCHOR + 0x4000) return NGPK_SHELL;
    if (pb(a, 0) != 'N' || pb(a, 1) != 'G' || pb(a, 2) != 'L' || pb(a, 3) != 'A') return NGPK_SHELL;
    a->fmt = pw(a, 4); a->nreg = pw(a, 6); a->flen = pw(a, 10);
    if (a->nreg > MAXREG || 20 + 12 * a->nreg + a->flen > 0x4000) return NGPK_SHELL;
    for (k = 0; k < a->nreg; k++) {
        size_t o = 20 + 12 * k;
        a->r[k].kind = pb(a, o); a->r[k].rom = pb(a, o + 1); a->r[k].off = pl(a, o + 4); a->r[k].size = pl(a, o + 8);
    }
    a->feat = 20 + 12 * a->nreg;
    return NGPK_OK;
}

/* is the token t (n bytes) one of the shell's features? */
static int has(const anchor_t *a, const char *t, size_t n) {
    size_t i = 0, e = a->flen ? a->flen - 1 : 0;
    while (i < e) {
        size_t j = i;
        while (j < e && pb(a, a->feat + j) != ' ') j++;
        if (j - i == n) { size_t q = 0; while (q < n && pb(a, a->feat + i + q) == (unsigned char)t[q]) q++; if (q == n) return 1; }
        i = j + 1;
    }
    return 0;
}

static void add_why(const char *s, size_t n) {
    size_t l = strlen(why);
    if (l + n + 2 >= sizeof why) return;
    if (l) why[l++] = ' ';
    memcpy(why + l, s, n); why[l + n] = 0;
}

/* the manifest's {"ngpk":{"format":N,"needs":"..."}: its format; *needs / *nlen the needs string */
static int pack_format(const uint8_t *m, size_t mlen, const char **needs, size_t *nlen) {
    static const char a[] = "{\"ngpk\":{\"format\":", b[] = ",\"needs\":\"";
    size_t i = sizeof a - 1, j;
    int f = 0;
    if (mlen < sizeof a + sizeof b || memcmp(m, a, sizeof a - 1)) return -1;
    while (i < mlen && m[i] >= '0' && m[i] <= '9') f = f * 10 + (m[i++] - '0');
    if (i + sizeof b - 1 > mlen || memcmp(m + i, b, sizeof b - 1)) return -1;
    i += sizeof b - 1; j = i;
    while (j < mlen && m[j] != '"') j++;
    if (j >= mlen) return -1;
    *needs = (const char *)m + i; *nlen = j - i;
    return f;
}

static int walk(const uint8_t *pk, size_t n, ngpk_rom_fn rom, int copy) {
    uint32_t nreg, mlen, i, k;
    size_t o, sz[6], nlen = 0;
    uint8_t *base[6];
    const char *needs = 0;
    anchor_t a;
    int f, e, miss = 0;
    if (n < 36) return NGPK_SHORT;
    if (memcmp(pk, "NGPK", 4)) return NGPK_MAGIC;
    if (rd16(pk + 4) != 1) return NGPK_VERSION;
    nreg = rd16(pk + 6); mlen = rd32(pk + 8);
    if (36 + (size_t)mlen > n) return NGPK_SHORT;
    for (k = 0; k < 6; k++) base[k] = rom((int)k, &sz[k]);
    if ((e = read_anchor(&a, base[0], sz[0]))) return e;
    if ((f = pack_format(pk + 36, mlen, &needs, &nlen)) < 0) return NGPK_OLD;
    if (!copy) {                                        /* the format, then every need */
        why[0] = 0;
        if ((unsigned)f != a.fmt || a.fmt != NGPK_FORMAT) {
            char t[64]; int l = 0; unsigned v;
            const char *s1 = "pack format ", *s2 = ", shell format ";
            memcpy(t, s1, 12); l = 12; v = (unsigned)f; t[l++] = (char)('0' + v / 10 % 10); t[l++] = (char)('0' + v % 10);
            memcpy(t + l, s2, 15); l += 15; v = a.fmt; t[l++] = (char)('0' + v / 10 % 10); t[l++] = (char)('0' + v % 10);
            add_why(t, (size_t)l);
            return NGPK_FORMATS;
        }
        for (i = 0; i < nlen;) {
            size_t j = i;
            while (j < nlen && needs[j] != ' ') j++;
            if (j > i && !has(&a, needs + i, j - i)) { add_why(needs + i, j - i); miss = 1; }
            i = j + 1;
        }
        if (miss) return NGPK_NEEDS;
    }
    o = 36 + (size_t)mlen; o += (4 - o % 4) % 4;
    for (i = 0; i < nreg; i++) {
        uint32_t r, kind, fl, off, len, zero, at = 0, room = 0;
        int found = 0;
        if (o + 16 > n) return NGPK_SHORT;
        r = pk[o]; kind = pk[o + 1]; fl = pk[o + 2]; off = rd32(pk + o + 4); len = rd32(pk + o + 8); zero = rd32(pk + o + 12); o += 16;
        if (r > 5 || !base[r]) return NGPK_NOROM;
        if (len > n - o) return NGPK_SHORT;
        for (k = 0; k < a.nreg; k++) if (a.r[k].kind == kind && a.r[k].rom == r) { at = a.r[k].off; room = a.r[k].size; found = 1; }
        if (!found || !kind) return NGPK_KIND;
        if (!(fl & 1) && at != off) return NGPK_PLACE;  /* a fixed region (its data names it): the shell keeps it there */
        if (len > room || zero > room - len) return NGPK_BOUNDS;
        if (at > sz[r] || len > sz[r] - at || zero > sz[r] - at - len) return NGPK_BOUNDS;
        if (r == 0 && ((at | len | zero) & 1)) return NGPK_ODD;
        if (copy) {
            if (r == 0) { uint32_t j; for (j = 0; j < len; j++) base[0][at + (j ^ 1)] = pk[o + j]; }
            else memcpy(base[r] + at, pk + o, len);
            memset(base[r] + at + len, 0, zero);
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
    static char msg[640];
    switch (e) {
    case NGPK_OK: return "ok";
    case NGPK_SHORT: return "the pack is cut short";
    case NGPK_MAGIC: return "not a character pack";
    case NGPK_VERSION: return "a pack container this core does not read";
    case NGPK_SIZES: return "made for another shell (its ROM sizes differ)";
    case NGPK_BOUNDS: return "a region larger than the shell keeps for it";
    case NGPK_ODD: return "a P region not on whole words";
    case NGPK_NOROM: return "a ROM the core has not loaded";
    case NGPK_OLD: return "a pack from before the pack format (it holds the old shell's addresses): rebuild it";
    case NGPK_SHELL: return "the loaded ROM is not a Character Lab shell of the pack format (no anchor)";
    case NGPK_KIND: return "a region this shell has no place for";
    case NGPK_PLACE: return "a fixed region not where this shell keeps it";
    case NGPK_FORMATS:
        strcpy(msg, "another pack format: "); strncat(msg, why, sizeof msg - 40); return msg;
    case NGPK_NEEDS:
        strcpy(msg, "it needs what this shell does not have: "); strncat(msg, why, sizeof msg - 60); return msg;
    default: return "unknown error";
    }
}
