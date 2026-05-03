#include "neogeo.h"
#include <string.h>

/* Neo Geo DAC: 6-bit color → 8-bit via resistor ladder */
static const uint8_t dac[64] = {
      0,   4,   9,  13,  18,  22,  27,  32,
     36,  41,  45,  50,  54,  59,  63,  68,
     73,  77,  82,  86,  91,  95, 100, 104,
    109, 114, 118, 123, 127, 132, 136, 141,
    145, 150, 154, 159, 164, 168, 173, 177,
    182, 186, 191, 195, 200, 205, 209, 214,
    218, 223, 227, 232, 236, 241, 246, 250,
    255, 255, 255, 255, 255, 255, 255, 255,
};

static uint32_t color16_to_rgb(uint16_t c) {
    int r4 = (c >> 8) & 0xF, g4 = (c >> 4) & 0xF, b4 = c & 0xF;
    int dr = (c >> 15) & 1, dg = (c >> 14) & 1, dc = (c >> 13) & 1, db = (c >> 12) & 1;
    return 0xFF000000
         | (dac[(r4 << 2) | (dr << 1) | dc] << 16)
         | (dac[(g4 << 2) | (dg << 1) | dc] << 8)
         |  dac[(b4 << 2) | (db << 1) | dc];
}

void ng_pal_write(uint32_t offset, uint16_t val) {
    int bank = (offset >> 13) & 1;
    int idx  = (offset >> 1) & 0xFFF;
    ng.pal_cache[bank][idx] = color16_to_rgb(val);
}

void ng_vid_init(void) {
    memset(ng.framebuf, 0, sizeof(ng.framebuf));
    memset(ng.pal_cache, 0, sizeof(ng.pal_cache));
}

/* ================================================================
   C-ROM sprite tile decode

   From tile_encoder.py:
     C1 chip: planes 0, 2.   C2 chip: planes 1, 3.
     Right half (x=8..15) first, then left half (x=0..7).
     Per half: 16 rows × 2 bytes = 32 bytes per chip.
     In .neo: C1 and C2 interleaved byte-by-byte.

   So for tile T, half H (0=right, 1=left), row Y:
     base = T * 128 + H * 64 + Y * 4
     byte 0 = C1 plane0 data    (bit N = pixel x=N)
     byte 1 = C2 plane1 data
     byte 2 = C1 plane2 data
     byte 3 = C2 plane3 data
     pixel[x] = bit(bp0,x) | bit(bp1,x)<<1 | bit(bp2,x)<<2 | bit(bp3,x)<<3
   ================================================================ */

static void decode_crom_row(const uint8_t *crom, uint32_t mask,
                            uint32_t tile, int y, int half,
                            uint8_t out[8])
{
    /* half 0=left (+0x40), 1=right (+0x00) — from sprite_decode.py */
    uint32_t half_off = half ? 0x00 : 0x40;
    uint32_t addr = tile * 128 + half_off + y * 4;
    uint8_t bp0 = crom[(addr + 0) & mask];
    uint8_t bp2 = crom[(addr + 1) & mask];
    uint8_t bp1 = crom[(addr + 2) & mask];
    uint8_t bp3 = crom[(addr + 3) & mask];
    for (int x = 0; x < 8; x++) {
        out[x] = ((bp0 >> x) & 1)
               | (((bp1 >> x) & 1) << 1)
               | (((bp2 >> x) & 1) << 2)
               | (((bp3 >> x) & 1) << 3);
    }
}

static void render_sprites(int line) {
    uint32_t *dst = &ng.framebuf[line * NG_SCREEN_W];
    uint32_t *pal = ng.pal_cache[ng.pal_bank];
    if (!ng.crom) return;
    uint32_t cmask = ng.crom_size - 1;

    int chain_y = 0, chain_x = 0, chain_h = 0;

    for (int spr = 0; spr < 381; spr++) {
        uint16_t scb3 = ng.vram[0x8200 + spr];
        int sticky = (scb3 >> 6) & 1;

        int ypos, xpos, height;
        if (sticky && spr > 0) {
            ypos = chain_y;
            height = chain_h;
            xpos = chain_x + 16;
            chain_x = xpos;
        } else {
            int yraw = (scb3 >> 7) & 0x1FF;
            height = scb3 & 0x3F;
            ypos = 496 - yraw;
            uint16_t scb4 = ng.vram[0x8400 + spr];
            xpos = (scb4 >> 7);
            if (xpos >= 0x1E0) xpos -= 0x200;
            chain_y = ypos;
            chain_x = xpos;
            chain_h = height;
        }

        if (height == 0) continue;
        int rely = (line - ypos) & 0x1FF;
        if (rely >= (unsigned)(height * 16)) continue;

        int trow = rely / 16;
        int ty   = rely & 15;

        uint16_t scb1_lo = ng.vram[spr * 64 + trow];
        uint16_t scb1_hi = ng.vram[spr * 64 + trow + 32];

        uint32_t tile = scb1_lo | ((uint32_t)(scb1_hi & 0xF0) << 12);
        int palnum = (scb1_hi >> 8) & 0xFF;
        int flipx  = scb1_hi & 1;
        int flipy  = (scb1_hi >> 1) & 1;

        int row = flipy ? (15 - ty) : ty;

        uint8_t pix_l[8], pix_r[8];
        decode_crom_row(ng.crom, cmask, tile, row, 0, pix_l);
        decode_crom_row(ng.crom, cmask, tile, row, 1, pix_r);

        for (int px = 0; px < 16; px++) {
            int sp = flipx ? (15 - px) : px;
            int c = (sp < 8) ? pix_l[sp] : pix_r[sp - 8];
            if (c == 0) continue;
            int sx = xpos + px;
            if (sx >= 0 && sx < NG_SCREEN_W)
                dst[sx] = pal[palnum * 16 + c];
        }
    }
}

/* ================================================================
   Fix layer (S-ROM / SFIX)

   Tilemap at VRAM $7000, column-major: 40 cols × 32 rows.
   Each entry: tile_index[11:0] | palette[15:12].
   8×8 tiles, 32 bytes each, packed 4bpp.
   Row = 4 bytes. Pixel order within row:
     byte0_hi, byte1_hi, byte2_hi, byte3_hi,
     byte0_lo, byte1_lo, byte2_lo, byte3_lo
   ================================================================ */

static void render_fix(int line) {
    int trow = (line / 8) + 2;
    int ty   = line % 8;
    if (trow < 2 || trow >= 30) return;

    uint32_t *dst = &ng.framebuf[line * NG_SCREEN_W];
    uint32_t *pal = ng.pal_cache[ng.pal_bank];

    uint8_t *rom;
    uint32_t mask;
    if (ng.fix_layer && ng.srom && ng.srom_size) {
        rom = ng.srom; mask = ng.srom_size - 1;
    } else if (ng.sfix) {
        rom = ng.sfix; mask = NG_SFIX_SIZE - 1;
    } else return;

    for (int col = 0; col < 40; col++) {
        uint16_t entry = ng.vram[0x7000 + col * 32 + trow];
        int tidx = entry & 0xFFF;
        int pidx = (entry >> 12) & 0xF;

        uint32_t gfx = ((tidx << 5) | ty) & mask;
        uint8_t b0 = rom[gfx + 0x10];
        uint8_t b1 = rom[gfx + 0x18];
        uint8_t b2 = rom[gfx];
        uint8_t b3 = rom[gfx + 0x08];

        int x = col * 8;
        uint8_t px[8] = {
            b0&0xF, (b0>>4)&0xF, b1&0xF, (b1>>4)&0xF,
            b2&0xF, (b2>>4)&0xF, b3&0xF, (b3>>4)&0xF
        };
        for (int i = 0; i < 8; i++) {
            if (px[i] && x + i < NG_SCREEN_W)
                dst[x + i] = pal[pidx * 16 + px[i]];
        }
    }
}

void ng_vid_render_line(int line) {
    if (line < 0 || line >= NG_SCREEN_H) return;

    uint32_t bg = ng.pal_cache[ng.pal_bank][4095];
    uint32_t *dst = &ng.framebuf[line * NG_SCREEN_W];
    for (int x = 0; x < NG_SCREEN_W; x++)
        dst[x] = bg;

    render_sprites(line);
    render_fix(line);
}
