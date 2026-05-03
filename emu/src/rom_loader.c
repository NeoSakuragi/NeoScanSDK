#include "neogeo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zip.h>

static void byteswap16(uint8_t *d, uint32_t sz) {
    for (uint32_t i = 0; i + 1 < sz; i += 2) {
        uint8_t t = d[i]; d[i] = d[i+1]; d[i+1] = t;
    }
}

int ng_load_neo(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); return -1; }

    uint8_t hdr[4096];
    if (fread(hdr, 1, 4096, f) != 4096) { fclose(f); return -1; }
    if (memcmp(hdr, "NEO", 3)) { fprintf(stderr, "Not a .neo file\n"); fclose(f); return -1; }

    uint32_t psz  = *(uint32_t*)(hdr+0x04);
    uint32_t ssz  = *(uint32_t*)(hdr+0x08);
    uint32_t msz  = *(uint32_t*)(hdr+0x0C);
    uint32_t v1sz = *(uint32_t*)(hdr+0x10);
    uint32_t v2sz = *(uint32_t*)(hdr+0x14);
    uint32_t csz  = *(uint32_t*)(hdr+0x18);
    memcpy(ng.game_name, hdr+0x2C, 32); ng.game_name[32] = 0;

    printf("NG-EMU: %s  P:%uK S:%uK M:%uK V:%uK C:%uM\n",
           ng.game_name, psz>>10, ssz>>10, msz>>10, v1sz>>10, csz>>20);

    if (psz)  { ng.prom  = malloc(psz);  fread(ng.prom,  1, psz,  f); ng.prom_size  = psz; }
    if (ssz)  { ng.srom  = malloc(ssz);  fread(ng.srom,  1, ssz,  f); ng.srom_size  = ssz; }
    if (msz)  { ng.mrom  = malloc(msz);  fread(ng.mrom,  1, msz,  f); ng.mrom_size  = msz; }
    if (v1sz) { ng.v1rom = malloc(v1sz); fread(ng.v1rom, 1, v1sz, f); ng.v1rom_size = v1sz; }
    if (v2sz) fseek(f, v2sz, SEEK_CUR);
    if (csz)  { ng.crom  = malloc(csz);  fread(ng.crom,  1, csz,  f); ng.crom_size  = csz; }

    fclose(f);
    return 0;
}

static int zip_extract(zip_t *z, const char *name, uint8_t *buf, uint32_t max) {
    zip_stat_t st;
    if (zip_stat(z, name, 0, &st) != 0) return -1;
    zip_file_t *zf = zip_fopen(z, name, 0);
    if (!zf) return -1;
    zip_fread(zf, buf, max);
    zip_fclose(zf);
    return 0;
}

int ng_load_bios(const char *path) {
    ng.bios  = calloc(1, NG_BIOS_SIZE);
    ng.sfix  = calloc(1, NG_SFIX_SIZE);
    ng.lorom = calloc(1, NG_LOROM_SIZE);

    int err;
    zip_t *z = zip_open(path, ZIP_RDONLY, &err);
    if (!z) { fprintf(stderr, "Cannot open %s\n", path); return -1; }

    const char *bios_names[] = {
        "uni-bios_4_0.rom",
        "sp-s2.sp1", NULL
    };
    int loaded = 0;
    for (int i = 0; bios_names[i]; i++) {
        if (zip_extract(z, bios_names[i], ng.bios, NG_BIOS_SIZE) == 0) {
            printf("NG-EMU: BIOS: %s\n", bios_names[i]);
            loaded = 1;
            break;
        }
    }
    if (!loaded) { zip_close(z); fprintf(stderr, "No BIOS found\n"); return -1; }

    byteswap16(ng.bios, NG_BIOS_SIZE);

    /* No BIOS patches — proper IRQ ack at $3C000C fixes the boot */

    zip_extract(z, "sfix.sfix", ng.sfix, NG_SFIX_SIZE);
    zip_extract(z, "000-lo.lo", ng.lorom, NG_LOROM_SIZE);

    zip_close(z);
    return 0;
}
