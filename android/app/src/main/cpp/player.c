/* NeoScan Player: the Geolith core (linked in, see Android.mk) driven from Kotlin through JNI. Same settings as the
 * desktop front end emu/neogeo_sdl.c (Unibios, MVS, credits counted (free play off), 8 px overscan). One emulation thread calls runFrame:
 * the core runs one frame, the picture lands in a direct ByteBuffer (XRGB8888 words, the GL side swizzles) and the
 * audio frames in a short[] the caller writes to its AudioTrack (whose blocking write paces the emulation). */
#include <jni.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <android/log.h>
#include "libretro.h"

#define TAG "NeoScanPlayer"
#define MAXW 512
#define MAXH 512
#define AUDIO_MAX 8192

static char sys_dir[512], save_dir[512];
static uint32_t fb[MAXW * MAXH];
static int fb_w = 304, fb_h = 224;
static int16_t audio[AUDIO_MAX * 2];
static int audio_n;
static uint16_t pads[2];                  /* bit = libretro joypad id (B 0 = Neo A, A 8 = Neo B, Y 1 = C, X 9 = D) */
static volatile uint16_t held[2], latch[2]; /* touch / pad state from the UI thread; latch keeps a press made and
                                              released between two frames until a frame has seen it */
static int loaded;

static void log_cb(enum retro_log_level level, const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    __android_log_vprint(level >= RETRO_LOG_ERROR ? ANDROID_LOG_ERROR : ANDROID_LOG_INFO, TAG, fmt, ap);
    va_end(ap);
}

static bool environ_cb(unsigned cmd, void *data) {
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY: *(const char **)data = sys_dir; return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data = save_dir; return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: return *(unsigned *)data == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        static const char *opts[][2] = {
            {"geolith_system_type", "uni"}, {"geolith_unibios_hw", "mvs"}, {"geolith_region", "us"},
            {"geolith_memcard", "on"}, {"geolith_memcard_wp", "off"}, {"geolith_freeplay", "off"},
            {"geolith_settingmode", "off"}, {"geolith_4player", "off"}, {"geolith_overscan_t", "8"},
            {"geolith_overscan_b", "8"}, {"geolith_overscan_l", "8"}, {"geolith_overscan_r", "8"},
            {"geolith_palette", "resnet"}, {"geolith_aspect", "1:1"}, {"geolith_sprlimit", "96"},
            {"geolith_oc", "off"}, {"geolith_disable_adpcm_wrap", "off"},
        };
        struct retro_variable *v = data;
        unsigned i;
        if (!v->key) return false;
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
    fb_w = (int)w; fb_h = (int)h;
}
static size_t audio_batch_cb(const int16_t *data, size_t frames) {
    size_t n = frames;
    if (audio_n + (int)n > AUDIO_MAX) n = AUDIO_MAX - audio_n;
    memcpy(audio + audio_n * 2, data, n * 4);
    audio_n += (int)n;
    return frames;
}
static void audio_cb(int16_t l, int16_t r) { int16_t s[2] = { l, r }; audio_batch_cb(s, 1); }
static void poll_cb(void) {}
static int16_t input_cb(unsigned port, unsigned device, unsigned index, unsigned id) {
    (void)index;
    if (port > 1 || device != RETRO_DEVICE_JOYPAD || id > 15) return 0;
    return (pads[port] >> id) & 1;
}

JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_load(JNIEnv *env, jclass cls, jstring jsys, jstring jsave, jstring jrom) {
    struct retro_system_av_info av;
    struct retro_game_info info = {0};
    const char *s = (*env)->GetStringUTFChars(env, jsys, 0), *v = (*env)->GetStringUTFChars(env, jsave, 0);
    const char *r = (*env)->GetStringUTFChars(env, jrom, 0);
    static char rom[512];
    (void)cls;
    snprintf(sys_dir, sizeof(sys_dir), "%s", s); snprintf(save_dir, sizeof(save_dir), "%s", v); snprintf(rom, sizeof(rom), "%s", r);
    (*env)->ReleaseStringUTFChars(env, jsys, s); (*env)->ReleaseStringUTFChars(env, jsave, v); (*env)->ReleaseStringUTFChars(env, jrom, r);
    if (loaded) { retro_unload_game(); retro_deinit(); loaded = 0; }
    retro_set_environment(environ_cb);
    retro_set_video_refresh(video_cb);
    retro_set_audio_sample(audio_cb);
    retro_set_audio_sample_batch(audio_batch_cb);
    retro_set_input_poll(poll_cb);
    retro_set_input_state(input_cb);
    retro_init();
    info.path = rom;
    if (!retro_load_game(&info)) { __android_log_print(ANDROID_LOG_ERROR, TAG, "load failed: %s", rom); retro_deinit(); return 0; }
    retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD);
    retro_set_controller_port_device(1, RETRO_DEVICE_JOYPAD);
    retro_get_system_av_info(&av);
    loaded = 1;
    __android_log_print(ANDROID_LOG_INFO, TAG, "loaded %s: %ux%u, %.3f fps, %.0f Hz", rom, av.geometry.base_width,
                        av.geometry.base_height, av.timing.fps, av.timing.sample_rate);
    return (jint)av.timing.sample_rate;
}

/* one frame: picture -> video (direct buffer, MAXW*MAXH*4 bytes, rows of width()), audio -> audioOut; returns frames */
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_runFrame(JNIEnv *env, jclass cls, jobject video, jshortArray audioOut) {
    jint n;
    (void)cls;
    if (!loaded) return 0;
    audio_n = 0;
    pads[0] = held[0] | latch[0]; pads[1] = held[1] | latch[1];
    latch[0] = latch[1] = 0;
    retro_run();
    memcpy((*env)->GetDirectBufferAddress(env, video), fb, (size_t)fb_w * fb_h * 4);
    n = audio_n;
    if (n * 2 > (*env)->GetArrayLength(env, audioOut)) n = (*env)->GetArrayLength(env, audioOut) / 2;
    (*env)->SetShortArrayRegion(env, audioOut, 0, n * 2, audio);
    return n;
}
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_width(JNIEnv *env, jclass cls) { (void)env; (void)cls; return fb_w; }
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_height(JNIEnv *env, jclass cls) { (void)env; (void)cls; return fb_h; }
JNIEXPORT void JNICALL Java_com_neoscan_player_Native_setPad(JNIEnv *env, jclass cls, jint port, jint mask) {
    (void)env; (void)cls;
    if (port >= 0 && port < 2) { latch[port] |= (uint16_t)(mask & ~held[port]); held[port] = (uint16_t)mask; }
}
