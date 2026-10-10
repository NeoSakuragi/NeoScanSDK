/* NeoScan Player: the Geolith core (linked in, see Android.mk) driven from Kotlin through JNI. Same settings as the
 * desktop front end emu/neogeo_sdl.c (Unibios, MVS, credits counted (free play off), 8 px overscan). One emulation thread calls runFrame:
 * the core runs one frame, the picture lands in a direct ByteBuffer (XRGB8888 words, the GL side swizzles) and the
 * audio frames in a short[] the caller writes to its AudioTrack (whose blocking write paces the emulation). */
#include <jni.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <android/log.h>
#include "libretro.h"
#include "pack_swap.h"                                  /* tools/brawler/chainlab (Android.mk) */

int geo_savedata_save(unsigned datatype, const char *filename);   /* Geolith (src/geo.c) */

#define TAG "NeoScanPlayer"
#define MAXW 512
#define MAXH 512
#define AUDIO_MAX 8192

static char sys_dir[512], save_dir[512];
static char hw[8] = "mvs";                             /* mvs = arcade, aes = console (setSystem) */
static char systype[8] = "mvs";                        /* geolith_system_type: mvs / aes = SNK's BIOS, uni = UniBIOS */
static char game_base[128];                             /* the ROM's name without extension: the save files' name */
static uint32_t fb[MAXW * MAXH];
static int fb_w = 304, fb_h = 224;
static int16_t audio[AUDIO_MAX * 2];
static int audio_n;
static uint16_t pads[2];                  /* bit = libretro joypad id (B 0 = Neo A, A 8 = Neo B, Y 1 = C, X 9 = D) */
static volatile uint16_t held[2], latch[2]; /* touch / pad state from the UI thread; latch keeps a press made and
                                              released between two frames until a frame has seen it */
static int loaded;
/* TODO #183: one core per process, driven by one thread. load claims the core for the calling thread (refused while
 * another load is live: two EmuThreads once ran the core at once and crashed the 68k core), unload releases it; the
 * calls that run the core (runFrame, reset, flushSaves, feedback, loadState) do nothing on any other thread. */
static pthread_mutex_t core_mx = PTHREAD_MUTEX_INITIALIZER;
static pthread_t owner;
static int claimed;                       /* under core_mx: a thread owns the core (from the start of load to unload) */
static int mine(void) { return loaded && pthread_equal(owner, pthread_self()); }

/* Feedback (docs/feedback.md): an exact replay of the last minute. Every frame's pads go into a ring (port 0, port 1;
 * bit 15 of port 0 = a soft reset ran just before that frame), a save state is kept every SNAP_EVERY frames (the last
 * NSNAP), and Native.feedback writes the oldest state + the inputs since + the state now (the press). frame_no counts
 * the frames run since load; a state "at frame f" = taken before frame f runs. */
#define RING 8192                      /* frames of inputs kept: > NSNAP * SNAP_EVERY */
#define NSNAP 7
#define SNAP_EVERY 600                 /* ~10 s */
#define RESET_BIT 0x8000
static uint16_t ring[RING][2];
static uint64_t frame_no;
static int reset_pending;
static struct { uint64_t frame; uint8_t *data; int valid; } snaps[NSNAP];
static size_t snap_size;

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
            {"geolith_system_type", "(setSystem)"}, {"geolith_unibios_hw", "(setSystem)"}, {"geolith_region", "us"},
            {"geolith_memcard_wp", "off"}, {"geolith_freeplay", "off"},
            {"geolith_settingmode", "off"}, {"geolith_4player", "off"}, {"geolith_overscan_t", "8"},
            {"geolith_overscan_b", "8"}, {"geolith_overscan_l", "8"}, {"geolith_overscan_r", "8"},
            {"geolith_palette", "resnet"}, {"geolith_aspect", "1:1"}, {"geolith_sprlimit", "96"},
            {"geolith_oc", "off"}, {"geolith_disable_adpcm_wrap", "off"},
        };
        struct retro_variable *v = data;
        unsigned i;
        if (!v->key) return false;
        if (!strcmp(v->key, "geolith_system_type")) { v->value = systype; return true; }
        if (!strcmp(v->key, "geolith_memcard")) {             /* the card only on AES, where the brawler saves to it; on */
            v->value = strcmp(hw, "aes") ? "off" : "on"; return true; }   /* MVS (backup RAM) a card made the BIOS say
                                                                    "your card is still inserted" after every game (TODO #156) */
        if (!strcmp(v->key, "geolith_unibios_hw")) {         /* UniBIOS detects AES / MVS from the coin 3-4 bits this sets */
            v->value = hw; return true; }
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
    pthread_mutex_lock(&core_mx);
    if (claimed) {
        pthread_mutex_unlock(&core_mx);
        __android_log_print(ANDROID_LOG_ERROR, TAG, "load refused: the core is live on another thread (TODO #183)");
        return 0;
    }
    claimed = 1; owner = pthread_self();
    pthread_mutex_unlock(&core_mx);
    retro_set_environment(environ_cb);
    retro_set_video_refresh(video_cb);
    retro_set_audio_sample(audio_cb);
    retro_set_audio_sample_batch(audio_batch_cb);
    retro_set_input_poll(poll_cb);
    retro_set_input_state(input_cb);
    retro_init();
    info.path = rom;
    {   const char *b = strrchr(rom, '/'); char *dot;
        snprintf(game_base, sizeof(game_base), "%s", b ? b + 1 : rom);
        if ((dot = strrchr(game_base, '.'))) *dot = 0; }
    if (!retro_load_game(&info)) { __android_log_print(ANDROID_LOG_ERROR, TAG, "load failed: %s", rom); retro_deinit();
        pthread_mutex_lock(&core_mx); claimed = 0; pthread_mutex_unlock(&core_mx); return 0; }
    retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD);
    retro_set_controller_port_device(1, RETRO_DEVICE_JOYPAD);
    retro_get_system_av_info(&av);
    loaded = 1;
    frame_no = 0; reset_pending = 0;
    {   int i; snap_size = retro_serialize_size();
        for (i = 0; i < NSNAP; i++) { free(snaps[i].data); snaps[i].data = malloc(snap_size); snaps[i].valid = 0; } }
    __android_log_print(ANDROID_LOG_INFO, TAG, "loaded %s: %ux%u, %.3f fps, %.0f Hz", rom, av.geometry.base_width,
                        av.geometry.base_height, av.timing.fps, av.timing.sample_rate);
    return (jint)av.timing.sample_rate;
}

/* the owner lets the core go: the saves written (Geolith's retro_unload_game), deinit; any other thread: nothing */
JNIEXPORT void JNICALL Java_com_neoscan_player_Native_unload(JNIEnv *env, jclass cls) {
    (void)env; (void)cls;
    if (!mine()) return;
    loaded = 0;
    retro_unload_game(); retro_deinit();
    pthread_mutex_lock(&core_mx); claimed = 0; pthread_mutex_unlock(&core_mx);
    __android_log_print(ANDROID_LOG_INFO, TAG, "core unloaded");
}

/* one frame: picture -> video (direct buffer, MAXW*MAXH*4 bytes, rows of width()), audio -> audioOut; returns frames */
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_runFrame(JNIEnv *env, jclass cls, jobject video, jshortArray audioOut) {
    jint n;
    (void)cls;
    if (!mine()) return 0;
    audio_n = 0;
    pads[0] = held[0] | latch[0]; pads[1] = held[1] | latch[1];
    latch[0] = latch[1] = 0;
    if (frame_no % SNAP_EVERY == 0) {                  /* the state before this frame, into the oldest slot */
        int i = (int)(frame_no / SNAP_EVERY % NSNAP);
        if (snaps[i].data && retro_serialize(snaps[i].data, snap_size)) { snaps[i].frame = frame_no; snaps[i].valid = 1; }
    }
    ring[frame_no % RING][0] = (uint16_t)(pads[0] | (reset_pending ? RESET_BIT : 0));
    ring[frame_no % RING][1] = pads[1];
    reset_pending = 0;
    retro_run();
    frame_no++;
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

/* "mvs" (arcade) or "aes" (console), read by the core at the next load (Bruno 2026-10-05: SNK's own BIOS for the
 * best compatibility): arcade = SNK's MVS BIOS; console = SNK's AES BIOS (neo-epo.bin) when the BIOS set has it,
 * else UniBIOS in AES mode (it tells AES from MVS by the coin 3-4 bits geolith_unibios_hw sets) */
JNIEXPORT void JNICALL Java_com_neoscan_player_Native_setSystem(JNIEnv *env, jclass cls, jstring jhw, jboolean aes_bios) {
    const char *h;
    (void)cls;
    pthread_mutex_lock(&core_mx);
    if (claimed) { pthread_mutex_unlock(&core_mx); __android_log_print(ANDROID_LOG_ERROR, TAG, "setSystem refused: the core is live"); return; }
    pthread_mutex_unlock(&core_mx);
    h = (*env)->GetStringUTFChars(env, jhw, 0); snprintf(hw, sizeof(hw), "%s", h); (*env)->ReleaseStringUTFChars(env, jhw, h);
    snprintf(systype, sizeof(systype), "%s", strcmp(hw, "aes") ? "mvs" : aes_bios ? "aes" : "uni");
    __android_log_print(ANDROID_LOG_INFO, TAG, "system: %s BIOS, %s hardware", systype, hw);
}

/* write NVRAM / cartridge RAM / memory card / CD backup RAM to the save dir, as Geolith's retro_unload_game does (the
 * core only writes them on unload, and Android never unloads cleanly: the player calls this on every pause and before
 * a restart). Called on the emulation thread between frames. */
JNIEXPORT void JNICALL Java_com_neoscan_player_Native_flushSaves(JNIEnv *env, jclass cls) {
    static const char *ext[] = { "nv", "srm", "mcr", "brm" };
    char name[700]; unsigned i;
    (void)env; (void)cls;
    if (!mine()) return;
    for (i = 0; i < 4; i++) {
        int st; snprintf(name, sizeof(name), "%s/%s.%s", save_dir, game_base, ext[i]); st = geo_savedata_save(i, name);
        if (st != 2) __android_log_print(ANDROID_LOG_INFO, TAG, "save %s: %s", name, st == 1 ? "written" : "FAILED");
    }
}

/* soft reset: Geolith's retro_reset (the system restarts through the BIOS; saves stay). Emulation thread, between frames. */
JNIEXPORT void JNICALL Java_com_neoscan_player_Native_reset(JNIEnv *env, jclass cls) {
    (void)env; (void)cls;
    if (!mine()) return;
    retro_reset();
    reset_pending = 1;                                 /* logged with the next frame: the replay resets there too */
}

/* the Character Lab's pack swap (tools/brawler/chainlab/pack_swap.c, the web core's same path): the character pack at
 * path (tools/brawler/lab_pack.py) into the loaded shell (lab-shell.neo), then a reset (the shell boots into the
 * practice with the new slot fighter). Emulation thread, between frames. 0 = swapped; < 0 = refused (pack_swap.h
 * NGPK_*, logged), the ROM unchanged. Called by the Character lab (CharacterLab.kt, Player 0.0.28). */
uint8_t *retro_neoscan_rom(int region, size_t *size);   /* geolith libretro.c */
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_swapPack(JNIEnv *env, jclass cls, jstring jpath) {
    const char *p; FILE *f; uint8_t *buf = NULL; long n = 0; int e = NGPK_SHORT;
    (void)cls;
    if (!mine()) return NGPK_NOROM;
    p = (*env)->GetStringUTFChars(env, jpath, 0);
    if ((f = fopen(p, "rb"))) {
        if (!fseek(f, 0, SEEK_END) && (n = ftell(f)) > 0 && !fseek(f, 0, SEEK_SET) && (buf = malloc((size_t)n)) &&
            fread(buf, 1, (size_t)n, f) == (size_t)n) e = ngpk_apply(buf, (size_t)n, retro_neoscan_rom);
        fclose(f);
    }
    if (e) __android_log_print(ANDROID_LOG_ERROR, TAG, "pack %s: %s", p, ngpk_error(e));
    else { retro_reset(); reset_pending = 1; __android_log_print(ANDROID_LOG_INFO, TAG, "pack %s swapped in", p); }
    free(buf);
    (*env)->ReleaseStringUTFChars(env, jpath, p);
    return e;
}

/* the Character Lab (Player 0.0.28): the 68000 work RAM ($100000, 64 KB, bytes in the 68000's order: the same view as
 * the web core's wc_ram, chainlab/lab.js r8 / wbytes), read / written between frames on the emulation thread.
 * ramRead: n bytes at the 68000 address addr (null outside the RAM or off the core's thread); ramWrite: 1 = written */
#define RAM_BASE 0x100000u
static uint8_t *ram_at(jint addr, jint n) {
    uint8_t *ram = retro_get_memory_data(RETRO_MEMORY_SYSTEM_RAM);
    size_t size = retro_get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
    if (!mine() || !ram || n < 0 || (uint32_t)addr < RAM_BASE || (size_t)((uint32_t)addr - RAM_BASE) + (size_t)n > size) return NULL;
    return ram + ((uint32_t)addr - RAM_BASE);
}
JNIEXPORT jbyteArray JNICALL Java_com_neoscan_player_Native_ramRead(JNIEnv *env, jclass cls, jint addr, jint n) {
    uint8_t *p = ram_at(addr, n); jbyteArray out;
    (void)cls;
    if (!p) return NULL;
    out = (*env)->NewByteArray(env, n);
    (*env)->SetByteArrayRegion(env, out, 0, n, (const jbyte *)p);
    return out;
}
JNIEXPORT jboolean JNICALL Java_com_neoscan_player_Native_ramWrite(JNIEnv *env, jclass cls, jint addr, jbyteArray data) {
    jint n = (*env)->GetArrayLength(env, data); uint8_t *p = ram_at(addr, n);
    (void)cls;
    if (!p) return JNI_FALSE;
    (*env)->GetByteArrayRegion(env, data, 0, n, (jbyte *)p);
    return JNI_TRUE;
}

static int write_file(const char *path, const void *data, size_t n) {
    FILE *f = fopen(path, "wb"); size_t k;
    if (!f) return 0;
    k = fwrite(data, 1, n, f);
    return fclose(f) == 0 && k == n;
}

/* Feedback capture, emulation thread between frames: into dir writes
 *   press.state                 the state now (frame P = frame_no)
 *   snap_<f>.state              every kept state f (oldest = the replay's start W; the others = checkpoints)
 *   inputs.bin                  "NSIN", u32 1, u64 W, u64 P, then P - W frames of (u16 port0, u16 port1), little endian
 *   screen.raw                  not written: the picture comes from Native.screenshot
 * returns {W, P} or null on a failure */
JNIEXPORT jlongArray JNICALL Java_com_neoscan_player_Native_feedback(JNIEnv *env, jclass cls, jstring jdir) {
    char path[700]; const char *d; uint8_t *press; uint64_t w = frame_no, f; int i, ok = 1; FILE *o;
    jlongArray out; jlong v[2];
    (void)cls;
    if (!mine()) return NULL;
    d = (*env)->GetStringUTFChars(env, jdir, 0);
    press = malloc(snap_size);
    if (!press || !retro_serialize(press, snap_size)) ok = 0;
    snprintf(path, sizeof(path), "%s/press.state", d); if (ok) ok = write_file(path, press, snap_size);
    free(press);
    for (i = 0; i < NSNAP; i++)                         /* the oldest state the ring still covers */
        if (snaps[i].valid && snaps[i].frame <= frame_no && frame_no - snaps[i].frame < RING && snaps[i].frame < w) w = snaps[i].frame;
    for (i = 0; i < NSNAP && ok; i++)
        if (snaps[i].valid && snaps[i].frame >= w && snaps[i].frame <= frame_no) {
            snprintf(path, sizeof(path), "%s/snap_%llu.state", d, (unsigned long long)snaps[i].frame);
            ok = write_file(path, snaps[i].data, snap_size);
        }
    snprintf(path, sizeof(path), "%s/inputs.bin", d);
    if (ok && (o = fopen(path, "wb"))) {
        uint32_t ver = 1; fwrite("NSIN", 1, 4, o); fwrite(&ver, 4, 1, o); fwrite(&w, 8, 1, o); fwrite(&frame_no, 8, 1, o);
        for (f = w; f < frame_no; f++) fwrite(ring[f % RING], 2, 2, o);     /* little endian: arm64, x86_64 */
        ok = fclose(o) == 0;
    } else ok = 0;
    (*env)->ReleaseStringUTFChars(env, jdir, d);
    __android_log_print(ANDROID_LOG_INFO, TAG, "feedback: frames %llu..%llu %s", (unsigned long long)w,
                        (unsigned long long)frame_no, ok ? "written" : "FAILED");
    if (!ok) return NULL;
    out = (*env)->NewLongArray(env, 2); v[0] = (jlong)w; v[1] = (jlong)frame_no;
    (*env)->SetLongArrayRegion(env, out, 0, 2, v);
    return out;
}

/* Player 0.0.22 (docs/feedback.md "Scenarios"): a test scenario's save state (tools/brawler/scenario.py) loaded in place of
 * the running game, emulation thread between frames. The replay ring starts again at frame 0 = this state (the next
 * runFrame keeps it as the first snapshot), so a feedback capture made during the test replays from the scenario.
 * Returns 0 = loaded, 1 = unreadable file, 2 = wrong size (another core build), 3 = the core refused it */
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_loadState(JNIEnv *env, jclass cls, jstring jpath) {
    const char *p; FILE *f; uint8_t *buf; long n; int i, r = 0;
    (void)cls;
    if (!mine()) return 3;
    p = (*env)->GetStringUTFChars(env, jpath, 0);
    f = fopen(p, "rb");
    (*env)->ReleaseStringUTFChars(env, jpath, p);
    if (!f) return 1;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    if (n != (long)snap_size) { fclose(f); return 2; }
    buf = malloc(snap_size);
    if (!buf || fread(buf, 1, snap_size, f) != snap_size) r = 1;
    fclose(f);
    if (!r && !retro_unserialize(buf, snap_size)) r = 3;
    free(buf);
    if (!r) { frame_no = 0; reset_pending = 0; for (i = 0; i < NSNAP; i++) snaps[i].valid = 0; }
    __android_log_print(ANDROID_LOG_INFO, TAG, "loadState: %s", r ? "FAILED" : "loaded");
    return r;
}

/* the last frame's picture as ARGB ints (opaque), rows of width(); returns the pixels written */
JNIEXPORT jint JNICALL Java_com_neoscan_player_Native_screenshot(JNIEnv *env, jclass cls, jintArray jout) {
    jint n = fb_w * fb_h, i; jint *p;
    (void)cls;
    if ((*env)->GetArrayLength(env, jout) < n) return 0;
    p = (*env)->GetIntArrayElements(env, jout, 0);
    for (i = 0; i < n; i++) p[i] = (jint)(fb[i] | 0xFF000000u);
    (*env)->ReleaseIntArrayElements(env, jout, p, 0);
    return n;
}

/* "mvs" / "aes" / "uni": the BIOS the core was told to boot (for the feedback bundle's versions) */
JNIEXPORT jstring JNICALL Java_com_neoscan_player_Native_systemType(JNIEnv *env, jclass cls) { (void)cls; return (*env)->NewStringUTF(env, systype); }
/* "on" / "off": the memory card the core was told about (geolith_memcard; the feedback bundle's meta.json "memcard") */
JNIEXPORT jstring JNICALL Java_com_neoscan_player_Native_memcard(JNIEnv *env, jclass cls) { (void)cls; return (*env)->NewStringUTF(env, strcmp(hw, "aes") ? "off" : "on"); }
