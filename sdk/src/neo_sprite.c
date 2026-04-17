#include "neo_hw.h"
#include "neo_sprite.h"
#include "neo_internal.h"

static uint8_t sprite_height[NEO_MAX_SPRITES];
static uint8_t sprite_sticky[NEO_MAX_SPRITES];

static uint16_t encode_scb3(int16_t y, uint8_t sticky, uint8_t height) {
    uint16_t yval = (uint16_t)((496 - y) & 0x1FF);
    return (yval << 7) | ((sticky & 1) << 6) | (height & 0x3F);
}

static uint16_t encode_scb4(int16_t x) {
    return (uint16_t)((x & 0x1FF) << 7);
}

static uint16_t encode_scb1_attr(uint8_t palette, uint8_t h_flip, uint8_t v_flip) {
    return ((uint16_t)palette << 8) | ((v_flip & 1) << 1) | (h_flip & 1);
}

void neo_sprite_show(uint16_t id, uint16_t tile, uint8_t palette,
                     int16_t x, int16_t y, uint8_t height) {
    uint8_t row;
    uint16_t attr = encode_scb1_attr(palette, 0, 0);

    for (row = 0; row < height; row++) {
        neo_cmd_push(NEO_VRAM_SCB1 + id * 64 + row * 2, tile + row);
        neo_cmd_push(NEO_VRAM_SCB1 + id * 64 + row * 2 + 1, attr);
    }

    neo_cmd_push(NEO_VRAM_SCB2 + id, 0x0FFF);
    neo_cmd_push(NEO_VRAM_SCB3 + id, encode_scb3(y, 0, height));
    neo_cmd_push(NEO_VRAM_SCB4 + id, encode_scb4(x));

    sprite_height[id] = height;
    sprite_sticky[id] = 0;
}

void neo_sprite_hide(uint16_t id) {
    neo_cmd_push(NEO_VRAM_SCB3 + id, 0);
    sprite_height[id] = 0;
    sprite_sticky[id] = 0;
}

void neo_sprite_move(uint16_t id, int16_t x, int16_t y) {
    neo_cmd_push(NEO_VRAM_SCB3 + id,
                 encode_scb3(y, sprite_sticky[id], sprite_height[id]));
    neo_cmd_push(NEO_VRAM_SCB4 + id, encode_scb4(x));
}

void neo_sprite_set_tile(uint16_t id, uint8_t row,
                         uint16_t tile, uint8_t palette,
                         uint8_t h_flip, uint8_t v_flip) {
    neo_cmd_push(NEO_VRAM_SCB1 + id * 64 + row * 2, tile);
    neo_cmd_push(NEO_VRAM_SCB1 + id * 64 + row * 2 + 1,
                 encode_scb1_attr(palette, h_flip, v_flip));
}

void neo_sprite_set_shrink(uint16_t id, uint8_t x_shrink, uint8_t y_shrink) {
    neo_cmd_push(NEO_VRAM_SCB2 + id,
                 ((uint16_t)y_shrink << 8) | x_shrink);
}

void neo_sprite_group_show(uint16_t first_id, uint8_t width, uint8_t height,
                           const uint16_t *tiles, uint8_t palette,
                           int16_t x, int16_t y) {
    uint8_t col, row;
    uint16_t attr = encode_scb1_attr(palette, 0, 0);

    for (col = 0; col < width; col++) {
        uint16_t id = first_id + col;
        uint8_t sticky = (col > 0) ? 1 : 0;

        for (row = 0; row < height; row++) {
            uint16_t tile = tiles[col * height + row];
            neo_cmd_push(NEO_VRAM_SCB1 + id * 64 + row * 2, tile);
            neo_cmd_push(NEO_VRAM_SCB1 + id * 64 + row * 2 + 1, attr);
        }

        neo_cmd_push(NEO_VRAM_SCB2 + id, 0x0FFF);
        neo_cmd_push(NEO_VRAM_SCB3 + id, encode_scb3(y, sticky, height));

        if (col == 0)
            neo_cmd_push(NEO_VRAM_SCB4 + id, encode_scb4(x));

        sprite_height[id] = height;
        sprite_sticky[id] = sticky;
    }
}

void neo_sprite_group_hide(uint16_t first_id, uint8_t width) {
    uint8_t col;
    for (col = 0; col < width; col++)
        neo_sprite_hide(first_id + col);
}

void neo_sprite_group_move(uint16_t first_id, int16_t x, int16_t y) {
    uint8_t col;
    uint16_t id = first_id;

    neo_cmd_push(NEO_VRAM_SCB3 + id,
                 encode_scb3(y, 0, sprite_height[id]));
    neo_cmd_push(NEO_VRAM_SCB4 + id, encode_scb4(x));

    for (col = 1; col < NEO_MAX_SPRITES - first_id; col++) {
        id = first_id + col;
        if (!sprite_sticky[id])
            break;
        neo_cmd_push(NEO_VRAM_SCB3 + id,
                     encode_scb3(y, 1, sprite_height[id]));
    }
}
