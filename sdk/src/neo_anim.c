#include "neo_hw.h"
#include "neo_sprite.h"
#include "neo_anim.h"
#include "neo_internal.h"

typedef struct {
    const anim_def_t *def;
    uint16_t first_sprite;
    int16_t  x;
    int16_t  y;
    uint8_t  base_palette;
    uint8_t  mode;
    uint8_t  cur_frame;
    int8_t   dir;
    uint16_t timer;
    uint16_t speed_override;
    uint8_t  playing;
    uint8_t  visible;
    uint8_t  h_flip;
} anim_slot_t;

static anim_slot_t slots[ANIM_MAX_SLOTS];

static void apply_frame(anim_slot_t *s) {
    const anim_def_t *d = s->def;
    const anim_frame_t *f = &d->frames[s->cur_frame];
    uint8_t col, row;
    uint16_t flip_bits = s->h_flip ? 1 : 0;

    for (col = 0; col < d->width; col++) {
        uint16_t id = s->first_sprite + col;
        uint8_t src_col = s->h_flip ? (d->width - 1 - col) : col;
        for (row = 0; row < d->height; row++) {
            uint16_t idx = src_col * d->height + row;
            uint16_t tile = f->tiles[idx];
            uint16_t attr;
            if (f->pal_offsets)
                attr = (uint16_t)(s->base_palette + f->pal_offsets[idx]) << 8;
            else
                attr = (uint16_t)s->base_palette << 8;
            attr |= flip_bits;
            cmd_push(VRAM_SCB1 + id * 64 + row * 2, tile);
            cmd_push(VRAM_SCB1 + id * 64 + row * 2 + 1, attr);
        }
    }
}

static uint16_t frame_duration(anim_slot_t *s) {
    if (s->speed_override)
        return s->speed_override;
    return s->def->frames[s->cur_frame].duration;
}

static void advance_frame(anim_slot_t *s) {
    int8_t next = s->cur_frame + s->dir;

    switch (s->mode) {
    case ANIM_FORWARD:
        if (next >= s->def->num_frames)
            next = 0;
        break;
    case ANIM_REVERSE:
        if (next < 0)
            next = s->def->num_frames - 1;
        break;
    case ANIM_PINGPONG:
        if (next >= s->def->num_frames) {
            s->dir = -1;
            next = s->def->num_frames - 2;
            if (next < 0) next = 0;
        } else if (next < 0) {
            s->dir = 1;
            next = 1;
            if (next >= s->def->num_frames) next = 0;
        }
        break;
    case ANIM_ONCE:
        if (next >= s->def->num_frames || next < 0) {
            s->playing = 0;
            return;
        }
        break;
    }

    s->cur_frame = (uint8_t)next;
    s->timer = frame_duration(s);
    apply_frame(s);
}

void ANIM_init(uint8_t slot, const anim_def_t *def,
               uint16_t first_sprite, uint8_t base_palette) {
    anim_slot_t *s;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    s->def = def;
    s->first_sprite = first_sprite;
    s->base_palette = base_palette;
    s->mode = ANIM_FORWARD;
    s->cur_frame = 0;
    s->dir = 1;
    s->timer = 0;
    s->speed_override = 0;
    s->playing = 0;
    s->visible = 0;
    s->h_flip = 0;
    s->x = 0;
    s->y = 0;
}

void ANIM_play(uint8_t slot, uint8_t mode) {
    anim_slot_t *s;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    if (!s->def) return;
    s->mode = mode;
    s->dir = (mode == ANIM_REVERSE) ? -1 : 1;
    s->playing = 1;
    s->timer = frame_duration(s);
    apply_frame(s);
}

void ANIM_stop(uint8_t slot) {
    if (slot >= ANIM_MAX_SLOTS) return;
    slots[slot].playing = 0;
}

void ANIM_setFrame(uint8_t slot, uint8_t frame) {
    anim_slot_t *s;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    if (!s->def || frame >= s->def->num_frames) return;
    s->cur_frame = frame;
    s->timer = frame_duration(s);
    if (s->visible)
        apply_frame(s);
}

void ANIM_setSpeed(uint8_t slot, uint16_t vblanks_per_frame) {
    if (slot >= ANIM_MAX_SLOTS) return;
    slots[slot].speed_override = vblanks_per_frame;
}

static int16_t flip_anchor_x(anim_slot_t *s) {
    if (s->h_flip)
        return (int16_t)(s->def->width * 16) - s->def->anchor_x;
    return s->def->anchor_x;
}

void ANIM_setPosition(uint8_t slot, int16_t x, int16_t y) {
    anim_slot_t *s;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    s->x = x;
    s->y = y;
    if (s->visible && s->def)
        SPR_groupMove(s->first_sprite,
                      x - flip_anchor_x(s),
                      y - s->def->anchor_y);
}

void ANIM_setFlip(uint8_t slot, uint8_t h_flip) {
    anim_slot_t *s;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    s->h_flip = h_flip ? 1 : 0;
    if (s->visible && s->def) {
        apply_frame(s);
        SPR_groupMove(s->first_sprite,
                      s->x - flip_anchor_x(s),
                      s->y - s->def->anchor_y);
    }
}

void ANIM_show(uint8_t slot, int16_t x, int16_t y) {
    anim_slot_t *s;
    const anim_frame_t *f;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    if (!s->def) return;

    s->x = x;
    s->y = y;
    s->visible = 1;

    f = &s->def->frames[s->cur_frame];
    SPR_groupShow(s->first_sprite, s->def->width, s->def->height,
                  f->tiles, s->base_palette,
                  x - flip_anchor_x(s), y - s->def->anchor_y);

    if (f->pal_offsets || s->h_flip)
        apply_frame(s);
}

void ANIM_hide(uint8_t slot) {
    anim_slot_t *s;
    if (slot >= ANIM_MAX_SLOTS) return;
    s = &slots[slot];
    if (!s->def) return;
    s->visible = 0;
    s->playing = 0;
    SPR_groupHide(s->first_sprite, s->def->width);
}

void ANIM_update(void) {
    uint8_t i;
    for (i = 0; i < ANIM_MAX_SLOTS; i++) {
        anim_slot_t *s = &slots[i];
        if (!s->playing || !s->visible || !s->def)
            continue;
        if (s->timer > 1) {
            s->timer--;
        } else {
            advance_frame(s);
        }
    }
}
