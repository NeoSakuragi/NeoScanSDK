/* Chain Lab: the Geolith libretro core (linked in) driven from JavaScript, compiled to WebAssembly by build_wasm.sh.
 * Same core settings as the Android player (android/app/src/main/cpp/player.c): SNK's MVS BIOS (region US), credits
 * counted, 8 px overscan. JavaScript writes /sys/neogeo.zip and /rom/game.neo into the in-memory file system, calls
 * wc_init, then wc_run once per frame: the picture lands in fb (XRGB8888), the audio frames in audio, the pads come
 * from wc_pad. wc_ram is the 68000 work RAM (64 KB at $100000, big-endian words as the core keeps them: see lab.js). */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten/emscripten.h>
#include "libretro.h"

#define MAXW 512
#define MAXH 512
#define AUDIO_MAX 8192
static uint32_t fb[MAXW * MAXH];
static int fb_w = 304, fb_h = 224;
static int16_t audio[AUDIO_MAX * 2];
static int audio_n;
static uint16_t pads[2];                 /* bit = libretro joypad id (B 0 = Neo A, A 8 = Neo B, Y 1 = C, X 9 = D) */
static char region[8] = "us";
static char systype[8] = "mvs", hw[8] = "mvs";   /* wc_system: the feedback replay boots what the player booted */
static char memcard[4] = "off";                  /* wc_memcard: the player's card (meta.json "memcard"; older bundles: on);
                                                    off on MVS (TODO #156: the BIOS's card reminder after every game) */

static void log_cb(enum retro_log_level level, const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    if (level >= RETRO_LOG_ERROR) vfprintf(stderr, fmt, ap);
    va_end(ap);
}
static bool environ_cb(unsigned cmd, void *data) {
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY: *(const char **)data = "/sys"; return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data = "/save"; return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: return *(unsigned *)data == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        static const char *opts[][2] = {
            {"geolith_memcard_wp", "off"}, {"geolith_freeplay", "off"},
            {"geolith_settingmode", "off"}, {"geolith_4player", "off"}, {"geolith_overscan_t", "8"},
            {"geolith_overscan_b", "8"}, {"geolith_overscan_l", "8"}, {"geolith_overscan_r", "8"},
            {"geolith_palette", "resnet"}, {"geolith_aspect", "1:1"}, {"geolith_sprlimit", "96"},
            {"geolith_oc", "off"}, {"geolith_disable_adpcm_wrap", "off"},
        };
        struct retro_variable *v = data;
        unsigned i;
        if (!v->key) return false;
        if (!strcmp(v->key, "geolith_region")) { v->value = region; return true; }
        if (!strcmp(v->key, "geolith_system_type")) { v->value = systype; return true; }
        if (!strcmp(v->key, "geolith_unibios_hw")) { v->value = hw; return true; }
        if (!strcmp(v->key, "geolith_memcard")) { v->value = memcard; return true; }
        for (i = 0; i < sizeof(opts) / sizeof(opts[0]); i++)
            if (!strcmp(v->key, opts[i][0])) { v->value = opts[i][1]; return true; }
        v->value = NULL; return false;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool *)data = false; return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: ((struct retro_log_callback *)data)->log = log_cb; return true;
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned *)data = 2; return true;
    case RETRO_ENVIRONMENT_GET_LANGUAGE: *(unsigned *)data = 0; return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY:
        return true;
    default: return false;
    }
}
static void video_cb(const void *data, unsigned w, unsigned h, size_t pitch) {
    unsigned y;
    if (!data || w > MAXW || h > MAXH) return;
    for (y = 0; y < h; y++) memcpy(fb + y * w, (const uint8_t *)data + y * pitch, w * 4);
    fb_w = w; fb_h = h;
}
static void audio_cb(int16_t l, int16_t r) {
    if (audio_n < AUDIO_MAX) { audio[audio_n * 2] = l; audio[audio_n * 2 + 1] = r; audio_n++; }
}
static size_t audio_batch_cb(const int16_t *d, size_t n) {
    size_t k = n;
    if (audio_n + k > AUDIO_MAX) k = AUDIO_MAX - audio_n;
    memcpy(audio + audio_n * 2, d, k * 4); audio_n += k;
    return n;
}
static void poll_cb(void) {}
static int16_t input_cb(unsigned port, unsigned dev, unsigned idx, unsigned id) {
    if (port > 1 || dev != RETRO_DEVICE_JOYPAD) return 0;
    if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return pads[port];
    return (pads[port] >> id) & 1;
}

/* before wc_init: geolith_system_type (mvs / aes / uni) and geolith_unibios_hw (mvs / aes), as the bundle's meta.json */
EMSCRIPTEN_KEEPALIVE void wc_system(const char *st, const char *h) {
    snprintf(systype, sizeof(systype), "%s", st); snprintf(hw, sizeof(hw), "%s", h);
}
/* before wc_init: geolith_memcard "on" / "off", as the bundle's meta.json (absent: on, the players before 0.0.16) */
EMSCRIPTEN_KEEPALIVE void wc_memcard(const char *m) { snprintf(memcard, sizeof(memcard), "%s", m); }
EMSCRIPTEN_KEEPALIVE int wc_init(void) {
    struct retro_game_info gi = { "/rom/game.neo", NULL, 0, NULL };
    retro_set_environment(environ_cb);
    retro_init();
    retro_set_video_refresh(video_cb); retro_set_audio_sample(audio_cb); retro_set_audio_sample_batch(audio_batch_cb);
    retro_set_input_poll(poll_cb); retro_set_input_state(input_cb);
    return retro_load_game(&gi) ? 1 : 0;
}
EMSCRIPTEN_KEEPALIVE double wc_sample_rate(void) { struct retro_system_av_info av; retro_get_system_av_info(&av); return av.timing.sample_rate; }
EMSCRIPTEN_KEEPALIVE double wc_fps(void) { struct retro_system_av_info av; retro_get_system_av_info(&av); return av.timing.fps; }
EMSCRIPTEN_KEEPALIVE void wc_run(void) { audio_n = 0; retro_run(); }
EMSCRIPTEN_KEEPALIVE void wc_reset(void) { retro_reset(); }
EMSCRIPTEN_KEEPALIVE void wc_pad(int port, int bits) { if (port >= 0 && port < 2) pads[port] = bits; }
EMSCRIPTEN_KEEPALIVE uint32_t *wc_fb(void) { return fb; }
EMSCRIPTEN_KEEPALIVE int wc_fb_w(void) { return fb_w; }
EMSCRIPTEN_KEEPALIVE int wc_fb_h(void) { return fb_h; }
EMSCRIPTEN_KEEPALIVE int16_t *wc_audio(void) { return audio; }
EMSCRIPTEN_KEEPALIVE int wc_audio_n(void) { return audio_n; }
EMSCRIPTEN_KEEPALIVE uint8_t *wc_ram(void) { return retro_get_memory_data(RETRO_MEMORY_SYSTEM_RAM); }
EMSCRIPTEN_KEEPALIVE int wc_ram_size(void) { return (int)retro_get_memory_size(RETRO_MEMORY_SYSTEM_RAM); }
EMSCRIPTEN_KEEPALIVE uint16_t *wc_palram(void) { return retro_get_memory_data(104); }   /* palette RAM, both banks (8192 words, host order) */
EMSCRIPTEN_KEEPALIVE int wc_state_size(void) { return (int)retro_serialize_size(); }
EMSCRIPTEN_KEEPALIVE int wc_save(void *buf, int n) { return retro_serialize(buf, n); }
EMSCRIPTEN_KEEPALIVE int wc_load(void *buf, int n) { return retro_unserialize(buf, n); }
