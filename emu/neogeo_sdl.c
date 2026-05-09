/* neogeo_sdl — standalone SDL2 frontend for Geolith libretro core.
   Loads the .so at runtime, hardcoded keyboard input, SHM bridge enabled.
   CRT shader: aperture grille + scanlines via OpenGL.
   Usage: ./neogeo_sdl game.neo [core.so]
*/
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdarg.h>
#include <unistd.h>
#include <time.h>
#include <math.h>
#include <dlfcn.h>
#include <SDL2/SDL.h>
#define GL_GLEXT_PROTOTYPES
#include <SDL2/SDL_opengl.h>

/* ═══ Minimal libretro types (subset of libretro.h) ═══ */

#define RETRO_API_VERSION 1

#define RETRO_DEVICE_JOYPAD 1
#define RETRO_DEVICE_ID_JOYPAD_B      0
#define RETRO_DEVICE_ID_JOYPAD_Y      1
#define RETRO_DEVICE_ID_JOYPAD_SELECT 2
#define RETRO_DEVICE_ID_JOYPAD_START  3
#define RETRO_DEVICE_ID_JOYPAD_UP     4
#define RETRO_DEVICE_ID_JOYPAD_DOWN   5
#define RETRO_DEVICE_ID_JOYPAD_LEFT   6
#define RETRO_DEVICE_ID_JOYPAD_RIGHT  7
#define RETRO_DEVICE_ID_JOYPAD_A      8
#define RETRO_DEVICE_ID_JOYPAD_X      9
#define RETRO_DEVICE_ID_JOYPAD_L     10
#define RETRO_DEVICE_ID_JOYPAD_R     11
#define RETRO_DEVICE_ID_JOYPAD_L2    12
#define RETRO_DEVICE_ID_JOYPAD_R2    13
#define RETRO_DEVICE_ID_JOYPAD_L3    14
#define RETRO_DEVICE_ID_JOYPAD_R3    15

#define RETRO_ENVIRONMENT_EXPERIMENTAL 0x10000
#define RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY   9
#define RETRO_ENVIRONMENT_SET_PIXEL_FORMAT      10
#define RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS 11
#define RETRO_ENVIRONMENT_GET_VARIABLE          15
#define RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE   17
#define RETRO_ENVIRONMENT_GET_LOG_INTERFACE     27
#define RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY    31
#define RETRO_ENVIRONMENT_SET_GEOMETRY          37
#define RETRO_ENVIRONMENT_GET_LANGUAGE          39
#define RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION 52
#define RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY 55
#define RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2   67
#define RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL 68
#define RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK 69

#define RETRO_PIXEL_FORMAT_XRGB8888 1
#define RETRO_MEMORY_SYSTEM_RAM 2

enum retro_log_level { RETRO_LOG_DEBUG=0, RETRO_LOG_INFO, RETRO_LOG_WARN, RETRO_LOG_ERROR };
typedef void (*retro_log_printf_t)(enum retro_log_level, const char *, ...);
struct retro_log_callback { retro_log_printf_t log; };
struct retro_variable { const char *key; const char *value; };

struct retro_game_geometry {
    unsigned base_width, base_height, max_width, max_height;
    float aspect_ratio;
};
struct retro_system_timing { double fps, sample_rate; };
struct retro_system_av_info {
    struct retro_game_geometry geometry;
    struct retro_system_timing timing;
};
struct retro_system_info {
    const char *library_name, *library_version, *valid_extensions;
    bool need_fullpath, block_extract;
};
struct retro_game_info {
    const char *path; const void *data; size_t size; const char *meta;
};

typedef bool (*retro_environment_t)(unsigned, void *);
typedef void (*retro_video_refresh_t)(const void *, unsigned, unsigned, size_t);
typedef void (*retro_audio_sample_t)(int16_t, int16_t);
typedef size_t (*retro_audio_sample_batch_t)(const int16_t *, size_t);
typedef void (*retro_input_poll_t)(void);
typedef int16_t (*retro_input_state_t)(unsigned, unsigned, unsigned, unsigned);

/* ═══ Core function pointers ═══ */

static struct {
    void *handle;
    void (*set_environment)(retro_environment_t);
    void (*set_video_refresh)(retro_video_refresh_t);
    void (*set_audio_sample)(retro_audio_sample_t);
    void (*set_audio_sample_batch)(retro_audio_sample_batch_t);
    void (*set_input_poll)(retro_input_poll_t);
    void (*set_input_state)(retro_input_state_t);
    void (*init)(void);
    void (*deinit)(void);
    unsigned (*api_version)(void);
    void (*get_system_info)(struct retro_system_info *);
    void (*get_system_av_info)(struct retro_system_av_info *);
    void (*set_controller_port_device)(unsigned, unsigned);
    bool (*load_game)(const struct retro_game_info *);
    void (*unload_game)(void);
    void (*run)(void);
    void (*reset)(void);
    size_t (*serialize_size)(void);
    bool (*serialize)(void *, size_t);
    bool (*unserialize)(const void *, size_t);
    void *(*get_memory_data)(unsigned);
    size_t (*get_memory_size)(unsigned);
    void (*neoscan_rerender)(void);
} core;

static bool core_load(const char *path) {
    core.handle = dlopen(path, RTLD_LAZY);
    if (!core.handle) { fprintf(stderr, "dlopen: %s\n", dlerror()); return false; }

    #define LOAD(name) \
        *(void **)(&core.name) = dlsym(core.handle, "retro_" #name); \
        if (!core.name) { fprintf(stderr, "missing: retro_%s\n", #name); return false; }
    LOAD(set_environment) LOAD(set_video_refresh) LOAD(set_audio_sample)
    LOAD(set_audio_sample_batch) LOAD(set_input_poll) LOAD(set_input_state)
    LOAD(init) LOAD(deinit) LOAD(api_version) LOAD(get_system_info)
    LOAD(get_system_av_info) LOAD(set_controller_port_device)
    LOAD(load_game) LOAD(unload_game) LOAD(run) LOAD(reset)
    LOAD(serialize_size) LOAD(serialize) LOAD(unserialize)
    LOAD(get_memory_data) LOAD(get_memory_size)
    *(void **)(&core.neoscan_rerender) = dlsym(core.handle, "retro_neoscan_rerender");
    #undef LOAD
    return true;
}

/* ═══ Environment callback ═══ */

static char sys_dir[512];
static char save_dir[512];

static int opt_hw = 0;    // 0=mvs, 1=aes
static int opt_region = 0; // 0=us, 1=jp, 2=eu, 3=as
static bool opt_vars_dirty = false;
static const char *hw_names[] = {"mvs", "aes"};
static const char *hw_labels[] = {"ARCADE (MVS)", "CONSOLE (AES)"};
static const char *region_names[] = {"jp", "us", "eu", "as"};
static const char *region_labels[] = {"JAPAN", "USA", "EUROPE", "ASIA"};

static void log_cb(enum retro_log_level level, const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

static bool environ_cb(unsigned cmd, void *data) {
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
        *(const char **)data = sys_dir; return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = save_dir; return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return *(unsigned *)data == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *v = data;
        if (!v->key) return false;
        if (!strcmp(v->key, "geolith_system_type"))   { v->value = "uni";     return true; }
        if (!strcmp(v->key, "geolith_unibios_hw"))    { v->value = hw_names[opt_hw]; return true; }
        if (!strcmp(v->key, "geolith_region"))         { v->value = region_names[opt_region]; return true; }
        if (!strcmp(v->key, "geolith_memcard"))         { v->value = "on";      return true; }
        if (!strcmp(v->key, "geolith_memcard_wp"))      { v->value = "off";     return true; }
        if (!strcmp(v->key, "geolith_freeplay"))        { v->value = "on";      return true; }
        if (!strcmp(v->key, "geolith_settingmode"))     { v->value = "off";     return true; }
        if (!strcmp(v->key, "geolith_4player"))         { v->value = "off";     return true; }
        if (!strcmp(v->key, "geolith_overscan_t"))      { v->value = "8";       return true; }
        if (!strcmp(v->key, "geolith_overscan_b"))      { v->value = "8";       return true; }
        if (!strcmp(v->key, "geolith_overscan_l"))      { v->value = "8";       return true; }
        if (!strcmp(v->key, "geolith_overscan_r"))      { v->value = "8";       return true; }
        if (!strcmp(v->key, "geolith_palette"))          { v->value = "resnet";  return true; }
        if (!strcmp(v->key, "geolith_aspect"))           { v->value = "1:1";     return true; }
        if (!strcmp(v->key, "geolith_sprlimit"))         { v->value = "96";      return true; }
        if (!strcmp(v->key, "geolith_oc"))               { v->value = "off";     return true; }
        if (!strcmp(v->key, "geolith_disable_adpcm_wrap")) { v->value = "off";  return true; }
        if (!strcmp(v->key, "geolith_cd_system_type"))   { v->value = "cdz";    return true; }
        if (!strcmp(v->key, "geolith_cd_speed_hack"))    { v->value = "disabled"; return true; }
        if (!strcmp(v->key, "geolith_cd_skip_loading"))  { v->value = "disabled"; return true; }
        v->value = NULL; return false;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = opt_vars_dirty;
        opt_vars_dirty = false;
        return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: {
        struct retro_log_callback *cb = data;
        cb->log = log_cb; return true;
    }
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
        *(unsigned *)data = 2; return true;
    case RETRO_ENVIRONMENT_GET_LANGUAGE:
        *(unsigned *)data = 0; return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY:
    case (RETRO_ENVIRONMENT_EXPERIMENTAL | 36):
        return true;
    default:
        return false;
    }
}

/* ═══ Audio ring buffer ═══ */

#define RING_SIZE 8192
static int16_t ring_buf[RING_SIZE * 2];
static volatile uint32_t ring_w = 0, ring_r = 0;

static uint64_t audio_sum = 0;
static uint32_t audio_count = 0;

static size_t audio_batch_cb(const int16_t *data, size_t frames) {
    for (size_t i = 0; i < frames; i++) {
        uint32_t next = (ring_w + 1) & (RING_SIZE - 1);
        if (next == ring_r) break;
        ring_buf[ring_w * 2]     = data[i * 2];
        ring_buf[ring_w * 2 + 1] = data[i * 2 + 1];
        ring_w = next;
        int32_t l = data[i * 2], r = data[i * 2 + 1];
        audio_sum += (uint64_t)(l * l + r * r);
        audio_count++;
    }
    if (audio_count >= 55555) {
        double rms = sqrt((double)audio_sum / audio_count / 2.0);
        fprintf(stderr, "AUDIO RMS: %.0f / 32768 (%.1f%%)\n", rms, rms * 100.0 / 32768.0);
        audio_sum = 0;
        audio_count = 0;
    }
    return frames;
}

static void audio_sample_cb(int16_t l, int16_t r) { (void)l; (void)r; }

static void sdl_audio_cb(void *ud, uint8_t *stream, int len) {
    (void)ud;
    int16_t *out = (int16_t *)stream;
    int frames = len / 4;
    for (int i = 0; i < frames; i++) {
        if (ring_r != ring_w) {
            out[i * 2]     = ring_buf[ring_r * 2];
            out[i * 2 + 1] = ring_buf[ring_r * 2 + 1];
            ring_r = (ring_r + 1) & (RING_SIZE - 1);
        } else {
            out[i * 2] = out[i * 2 + 1] = 0;
        }
    }
}

/* ═══ Video (OpenGL + CRT shader) ═══ */

static GLuint gl_tex, gl_prog;
static unsigned tex_w, tex_h;

static const char *vert_src =
    "#version 120\n"
    "attribute vec2 pos;\n"
    "varying vec2 uv;\n"
    "void main() {\n"
    "    uv = vec2(pos.x * 0.5 + 0.5, 0.5 - pos.y * 0.5);\n"
    "    gl_Position = vec4(pos, 0.0, 1.0);\n"
    "}\n";

static const char *frag_src =
    "#version 120\n"
    "uniform sampler2D tex;\n"
    "uniform vec2 texSize;\n"
    "uniform vec2 outSize;\n"
    "varying vec2 uv;\n"
    "void main() {\n"
    "    vec3 col = texture2D(tex, uv).rgb;\n"
    "    vec2 px = uv * outSize;\n"
    "    int cx = int(mod(px.x, 3.0));\n"
    "    int cy = int(mod(px.y, 6.0));\n"
    "    vec3 mask = vec3(0.0);\n"
    "    if (cy < 5) {\n"
    "        int sub = int(mod(float(cx) + float(cy), 3.0));\n"
    "        if (sub == 0) mask = vec3(1.0, 0.08, 0.08);\n"
    "        else if (sub == 1) mask = vec3(0.08, 1.0, 0.08);\n"
    "        else mask = vec3(0.08, 0.08, 1.0);\n"
    "    }\n"
    "    gl_FragColor = vec4(col * mask, 1.0);\n"
    "}\n";

static GLuint compile_shader(GLenum type, const char *src) {
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok; glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512]; glGetShaderInfoLog(s, sizeof(log), NULL, log);
        fprintf(stderr, "shader: %s\n", log);
    }
    return s;
}

static GLuint build_program(void) {
    GLuint vs = compile_shader(GL_VERTEX_SHADER, vert_src);
    GLuint fs = compile_shader(GL_FRAGMENT_SHADER, frag_src);
    GLuint p = glCreateProgram();
    glAttachShader(p, vs); glAttachShader(p, fs);
    glBindAttribLocation(p, 0, "pos");
    glLinkProgram(p);
    glDeleteShader(vs); glDeleteShader(fs);
    return p;
}

static int auto_snaps[16];
static int num_auto_snaps = 0;
static int auto_quit_frame = -1;
static int snap_frame = -1;
static char snap_path[512];

static void save_ppm(const void *data, unsigned w, unsigned h, size_t pitch, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fprintf(f, "P6\n%u %u\n255\n", w, h);
    const uint8_t *src = data;
    for (unsigned y = 0; y < h; y++) {
        const uint8_t *row = src + y * pitch;
        for (unsigned x = 0; x < w; x++) {
            fputc(row[x*4+2], f); // R (BGRA→RGB)
            fputc(row[x*4+1], f); // G
            fputc(row[x*4+0], f); // B
        }
    }
    fclose(f);
    fprintf(stderr, "Snap: %s\n", path);
}

static unsigned frame_count = 0;

static void video_cb(const void *data, unsigned w, unsigned h, size_t pitch) {
    if (!data) return;
    frame_count++;
    if ((int)frame_count == snap_frame) {
        save_ppm(data, w, h, pitch, snap_path);
        snap_frame = -1;
    }
    for (int i = 0; i < num_auto_snaps; i++) {
        if ((int)frame_count == auto_snaps[i]) {
            char path[256];
            snprintf(path, sizeof(path), "/tmp/neoscan_f%d.ppm", auto_snaps[i]);
            save_ppm(data, w, h, pitch, path);
        }
    }
    tex_w = w; tex_h = h;
    glBindTexture(GL_TEXTURE_2D, gl_tex);
    glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(pitch / 4));
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, data);
    glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
}

/* ═══ Input ═══ */

static const uint8_t *kbd;
static SDL_GameController *pad[2] = {NULL, NULL};

static void input_poll_cb(void) {}

static int pad_btn(int p, SDL_GameControllerButton btn) {
    return pad[p] ? SDL_GameControllerGetButton(pad[p], btn) : 0;
}
static int pad_axis_neg(int p, SDL_GameControllerAxis axis, int16_t thresh) {
    return pad[p] ? (SDL_GameControllerGetAxis(pad[p], axis) < -thresh) : 0;
}
static int pad_axis_pos(int p, SDL_GameControllerAxis axis, int16_t thresh) {
    return pad[p] ? (SDL_GameControllerGetAxis(pad[p], axis) > thresh) : 0;
}

static int16_t input_state_cb(unsigned port, unsigned dev, unsigned idx, unsigned id) {
    (void)idx;
    if (dev != RETRO_DEVICE_JOYPAD) return 0;

    // Neo Geo button mapping:
    // B=A, A=B, Y=C, X=D, SELECT=coin, START=start
    // Gamepad: face buttons (A/B/X/Y), shoulders for combos, dpad + left stick

    if (port == 0) {
        switch (id) {
        case RETRO_DEVICE_ID_JOYPAD_UP:     return kbd[SDL_SCANCODE_W]     || pad_btn(0, SDL_CONTROLLER_BUTTON_DPAD_UP)    || pad_axis_neg(0, SDL_CONTROLLER_AXIS_LEFTY, 8000);
        case RETRO_DEVICE_ID_JOYPAD_DOWN:   return kbd[SDL_SCANCODE_S]     || pad_btn(0, SDL_CONTROLLER_BUTTON_DPAD_DOWN)  || pad_axis_pos(0, SDL_CONTROLLER_AXIS_LEFTY, 8000);
        case RETRO_DEVICE_ID_JOYPAD_LEFT:   return kbd[SDL_SCANCODE_A]     || pad_btn(0, SDL_CONTROLLER_BUTTON_DPAD_LEFT)  || pad_axis_neg(0, SDL_CONTROLLER_AXIS_LEFTX, 8000);
        case RETRO_DEVICE_ID_JOYPAD_RIGHT:  return kbd[SDL_SCANCODE_D]     || pad_btn(0, SDL_CONTROLLER_BUTTON_DPAD_RIGHT) || pad_axis_pos(0, SDL_CONTROLLER_AXIS_LEFTX, 8000);
        case RETRO_DEVICE_ID_JOYPAD_B:      return kbd[SDL_SCANCODE_U]     || pad_btn(0, SDL_CONTROLLER_BUTTON_X)
            || pad_btn(0, SDL_CONTROLLER_BUTTON_LEFTSHOULDER)    // A+B: LB has A
            || pad_btn(0, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)   // A+B+C: RB has A
            || pad_axis_pos(0, SDL_CONTROLLER_AXIS_TRIGGERLEFT, 8000);  // B+C: LT has A
        case RETRO_DEVICE_ID_JOYPAD_A:      return kbd[SDL_SCANCODE_I]     || pad_btn(0, SDL_CONTROLLER_BUTTON_A)
            || pad_btn(0, SDL_CONTROLLER_BUTTON_LEFTSHOULDER)    // A+B: LB has B
            || pad_btn(0, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)   // A+B+C: RB has B
            || pad_axis_pos(0, SDL_CONTROLLER_AXIS_TRIGGERLEFT, 8000);  // B+C: LT has B
        case RETRO_DEVICE_ID_JOYPAD_Y:      return kbd[SDL_SCANCODE_O]     || pad_btn(0, SDL_CONTROLLER_BUTTON_Y)
            || pad_axis_pos(0, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 8000)  // C+D: RT has C
            || pad_btn(0, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)   // A+B+C: RB has C
            || pad_axis_pos(0, SDL_CONTROLLER_AXIS_TRIGGERLEFT, 8000);  // B+C: LT has C
        case RETRO_DEVICE_ID_JOYPAD_X:      return kbd[SDL_SCANCODE_P]     || pad_btn(0, SDL_CONTROLLER_BUTTON_B)
            || pad_axis_pos(0, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 8000); // C+D: RT has D
        case RETRO_DEVICE_ID_JOYPAD_START:  return kbd[SDL_SCANCODE_1]     || pad_btn(0, SDL_CONTROLLER_BUTTON_START);
        case RETRO_DEVICE_ID_JOYPAD_SELECT: return kbd[SDL_SCANCODE_3]     || pad_btn(0, SDL_CONTROLLER_BUTTON_BACK);
        case RETRO_DEVICE_ID_JOYPAD_L3:     return kbd[SDL_SCANCODE_5];
        case RETRO_DEVICE_ID_JOYPAD_R3:     return kbd[SDL_SCANCODE_6];
        }
    } else if (port == 1) {
        switch (id) {
        case RETRO_DEVICE_ID_JOYPAD_UP:     return kbd[SDL_SCANCODE_UP]    || pad_btn(1, SDL_CONTROLLER_BUTTON_DPAD_UP)    || pad_axis_neg(1, SDL_CONTROLLER_AXIS_LEFTY, 8000);
        case RETRO_DEVICE_ID_JOYPAD_DOWN:   return kbd[SDL_SCANCODE_DOWN]  || pad_btn(1, SDL_CONTROLLER_BUTTON_DPAD_DOWN)  || pad_axis_pos(1, SDL_CONTROLLER_AXIS_LEFTY, 8000);
        case RETRO_DEVICE_ID_JOYPAD_LEFT:   return kbd[SDL_SCANCODE_LEFT]  || pad_btn(1, SDL_CONTROLLER_BUTTON_DPAD_LEFT)  || pad_axis_neg(1, SDL_CONTROLLER_AXIS_LEFTX, 8000);
        case RETRO_DEVICE_ID_JOYPAD_RIGHT:  return kbd[SDL_SCANCODE_RIGHT] || pad_btn(1, SDL_CONTROLLER_BUTTON_DPAD_RIGHT) || pad_axis_pos(1, SDL_CONTROLLER_AXIS_LEFTX, 8000);
        case RETRO_DEVICE_ID_JOYPAD_B:      return pad_btn(1, SDL_CONTROLLER_BUTTON_X)
            || pad_btn(1, SDL_CONTROLLER_BUTTON_LEFTSHOULDER)
            || pad_btn(1, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)
            || pad_axis_pos(1, SDL_CONTROLLER_AXIS_TRIGGERLEFT, 8000);
        case RETRO_DEVICE_ID_JOYPAD_A:      return pad_btn(1, SDL_CONTROLLER_BUTTON_A)
            || pad_btn(1, SDL_CONTROLLER_BUTTON_LEFTSHOULDER)
            || pad_btn(1, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)
            || pad_axis_pos(1, SDL_CONTROLLER_AXIS_TRIGGERLEFT, 8000);
        case RETRO_DEVICE_ID_JOYPAD_Y:      return pad_btn(1, SDL_CONTROLLER_BUTTON_Y)
            || pad_axis_pos(1, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 8000)
            || pad_btn(1, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)
            || pad_axis_pos(1, SDL_CONTROLLER_AXIS_TRIGGERLEFT, 8000);
        case RETRO_DEVICE_ID_JOYPAD_X:      return pad_btn(1, SDL_CONTROLLER_BUTTON_B)
            || pad_axis_pos(1, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 8000);
        case RETRO_DEVICE_ID_JOYPAD_START:  return kbd[SDL_SCANCODE_2]     || pad_btn(1, SDL_CONTROLLER_BUTTON_START);
        case RETRO_DEVICE_ID_JOYPAD_SELECT: return pad_btn(1, SDL_CONTROLLER_BUTTON_BACK);
        }
    }
    return 0;
}

/* ═══ Menu ═══ */

enum { MENU_RESUME, MENU_RESET, MENU_HW, MENU_REGION, MENU_COUNT };
static bool menu_open = false;
static int menu_sel = 0;
static GLuint menu_tex = 0;
static int pending_reset = 0;
static const char *game_path_global;

// Embedded 8x8 font for uppercase A-Z, 0-9, space, colon, parens, slash
static const uint8_t font8x8[128][8] = {
    [' ']={0},
    ['A']={0x3C,0x66,0x66,0x7E,0x66,0x66,0x66,0x00},
    ['B']={0x7C,0x66,0x66,0x7C,0x66,0x66,0x7C,0x00},
    ['C']={0x3C,0x66,0x60,0x60,0x60,0x66,0x3C,0x00},
    ['D']={0x78,0x6C,0x66,0x66,0x66,0x6C,0x78,0x00},
    ['E']={0x7E,0x60,0x60,0x7C,0x60,0x60,0x7E,0x00},
    ['F']={0x7E,0x60,0x60,0x7C,0x60,0x60,0x60,0x00},
    ['G']={0x3C,0x66,0x60,0x6E,0x66,0x66,0x3E,0x00},
    ['H']={0x66,0x66,0x66,0x7E,0x66,0x66,0x66,0x00},
    ['I']={0x3C,0x18,0x18,0x18,0x18,0x18,0x3C,0x00},
    ['J']={0x1E,0x0C,0x0C,0x0C,0x6C,0x6C,0x38,0x00},
    ['K']={0x66,0x6C,0x78,0x70,0x78,0x6C,0x66,0x00},
    ['L']={0x60,0x60,0x60,0x60,0x60,0x60,0x7E,0x00},
    ['M']={0x63,0x77,0x7F,0x6B,0x63,0x63,0x63,0x00},
    ['N']={0x66,0x76,0x7E,0x7E,0x6E,0x66,0x66,0x00},
    ['O']={0x3C,0x66,0x66,0x66,0x66,0x66,0x3C,0x00},
    ['P']={0x7C,0x66,0x66,0x7C,0x60,0x60,0x60,0x00},
    ['Q']={0x3C,0x66,0x66,0x66,0x6A,0x6C,0x36,0x00},
    ['R']={0x7C,0x66,0x66,0x7C,0x6C,0x66,0x66,0x00},
    ['S']={0x3C,0x66,0x60,0x3C,0x06,0x66,0x3C,0x00},
    ['T']={0x7E,0x18,0x18,0x18,0x18,0x18,0x18,0x00},
    ['U']={0x66,0x66,0x66,0x66,0x66,0x66,0x3C,0x00},
    ['V']={0x66,0x66,0x66,0x66,0x66,0x3C,0x18,0x00},
    ['W']={0x63,0x63,0x63,0x6B,0x7F,0x77,0x63,0x00},
    ['X']={0x66,0x66,0x3C,0x18,0x3C,0x66,0x66,0x00},
    ['Y']={0x66,0x66,0x66,0x3C,0x18,0x18,0x18,0x00},
    ['Z']={0x7E,0x06,0x0C,0x18,0x30,0x60,0x7E,0x00},
    ['0']={0x3C,0x66,0x6E,0x76,0x66,0x66,0x3C,0x00},
    ['1']={0x18,0x38,0x18,0x18,0x18,0x18,0x7E,0x00},
    ['2']={0x3C,0x66,0x06,0x1C,0x30,0x60,0x7E,0x00},
    ['3']={0x3C,0x66,0x06,0x1C,0x06,0x66,0x3C,0x00},
    ['4']={0x0C,0x1C,0x3C,0x6C,0x7E,0x0C,0x0C,0x00},
    ['5']={0x7E,0x60,0x7C,0x06,0x06,0x66,0x3C,0x00},
    ['6']={0x3C,0x60,0x60,0x7C,0x66,0x66,0x3C,0x00},
    ['7']={0x7E,0x06,0x0C,0x18,0x30,0x30,0x30,0x00},
    ['8']={0x3C,0x66,0x66,0x3C,0x66,0x66,0x3C,0x00},
    ['9']={0x3C,0x66,0x66,0x3E,0x06,0x06,0x3C,0x00},
    [':']={0x00,0x18,0x18,0x00,0x18,0x18,0x00,0x00},
    ['(']={0x0C,0x18,0x30,0x30,0x30,0x18,0x0C,0x00},
    [')']={0x30,0x18,0x0C,0x0C,0x0C,0x18,0x30,0x00},
    ['/']={0x02,0x06,0x0C,0x18,0x30,0x60,0x40,0x00},
    ['-']={0x00,0x00,0x00,0x7E,0x00,0x00,0x00,0x00},
    ['>']={0x30,0x18,0x0C,0x06,0x0C,0x18,0x30,0x00},
};

#define MENU_TEX_W 256
#define MENU_TEX_H 256

static void menu_render_text(uint32_t *buf, int bw, int x, int y,
                              const char *s, uint32_t color) {
    for (; *s; s++, x += 10) {
        int ch = (unsigned char)*s;
        if (ch >= 128) continue;
        const uint8_t *glyph = font8x8[ch];
        for (int row = 0; row < 8; row++)
            for (int col = 0; col < 8; col++)
                if (glyph[row] & (0x80 >> col)) {
                    int px = x + col, py = y + row;
                    if (px >= 0 && px < bw && py >= 0 && py < MENU_TEX_H)
                        buf[py * bw + px] = color;
                }
    }
}

static void menu_draw(int win_w, int win_h) {
    static uint32_t pixels[MENU_TEX_W * MENU_TEX_H];
    memset(pixels, 0, sizeof(pixels));

    const char *labels[MENU_COUNT];
    char hw_buf[40], reg_buf[40];
    labels[MENU_RESUME] = "RESUME";
    labels[MENU_RESET]  = "RESET";
    snprintf(hw_buf,  sizeof(hw_buf),  "BIOS: %s", hw_labels[opt_hw]);
    snprintf(reg_buf, sizeof(reg_buf), "REGION: %s", region_labels[opt_region]);
    labels[MENU_HW]     = hw_buf;
    labels[MENU_REGION]  = reg_buf;

    // Background
    for (int y = 20; y < 20 + MENU_COUNT * 28 + 20; y++)
        for (int x = 20; x < 236; x++)
            pixels[y * MENU_TEX_W + x] = 0xE0102810;

    // Items
    for (int i = 0; i < MENU_COUNT; i++) {
        int iy = 30 + i * 28;
        if (i == menu_sel) {
            for (int y = iy; y < iy + 20; y++)
                for (int x = 24; x < 232; x++)
                    pixels[y * MENU_TEX_W + x] = 0xFF006820;
        }
        uint32_t col = (i == menu_sel) ? 0xFF44FF88 : 0xFF88CC88;
        menu_render_text(pixels, MENU_TEX_W, 32, iy + 6, labels[i], col);
    }

    // Arrow
    menu_render_text(pixels, MENU_TEX_W, 22, 30 + menu_sel * 28 + 6, ">", 0xFF00FF44);

    if (!menu_tex) {
        glGenTextures(1, &menu_tex);
        glBindTexture(GL_TEXTURE_2D, menu_tex);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    }
    glBindTexture(GL_TEXTURE_2D, menu_tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, MENU_TEX_W, MENU_TEX_H, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, pixels);

    glUseProgram(0);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_TEXTURE_2D);
    glBindTexture(GL_TEXTURE_2D, menu_tex);
    glBegin(GL_QUADS);
    glTexCoord2f(0, 0); glVertex2f(-1,  1);
    glTexCoord2f(1, 0); glVertex2f( 1,  1);
    glTexCoord2f(1, 1); glVertex2f( 1, -1);
    glTexCoord2f(0, 1); glVertex2f(-1, -1);
    glEnd();
    glDisable(GL_BLEND);
    glDisable(GL_TEXTURE_2D);
}

/* ═══ Script engine ═══ */

static uint16_t *vram_ptr_script = NULL; // forward ref for script vram dump
static uint32_t *sprite_pc_ptr_script = NULL;
static uint16_t *palram_ptr = NULL;
static uint8_t *wram_ptr = NULL;  // 68K work RAM (0x100000-0x10FFFF)
static size_t wram_size = 0;
static uint32_t vblank_misses = 0;
static uint16_t vblank_prev_tick = 0;

typedef struct { int frame; char cmd[16]; char arg[256]; } script_cmd_t;
static script_cmd_t script[256];
static int script_len = 0;

static SDL_Scancode key_from_name(const char *name) {
    if (!strcmp(name, "F1")) return SDL_SCANCODE_F1;
    if (!strcmp(name, "F2")) return SDL_SCANCODE_F2;
    if (!strcmp(name, "F3")) return SDL_SCANCODE_F3;
    if (!strcmp(name, "F5")) return SDL_SCANCODE_F5;
    if (!strcmp(name, "F6")) return SDL_SCANCODE_F6;
    if (!strcmp(name, "F7")) return SDL_SCANCODE_F7;
    if (!strcmp(name, "UP")) return SDL_SCANCODE_UP;
    if (!strcmp(name, "DOWN")) return SDL_SCANCODE_DOWN;
    if (!strcmp(name, "LEFT")) return SDL_SCANCODE_LEFT;
    if (!strcmp(name, "RIGHT")) return SDL_SCANCODE_RIGHT;
    if (!strcmp(name, "RETURN")) return SDL_SCANCODE_RETURN;
    if (!strcmp(name, "ESCAPE")) return SDL_SCANCODE_ESCAPE;
    if (!strcmp(name, "BACKSPACE")) return SDL_SCANCODE_BACKSPACE;
    if (!strcmp(name, "DELETE")) return SDL_SCANCODE_DELETE;
    if (!strcmp(name, "1")) return SDL_SCANCODE_1;
    if (!strcmp(name, "2")) return SDL_SCANCODE_2;
    if (!strcmp(name, "3")) return SDL_SCANCODE_3;
    if (strlen(name) == 1 && name[0] >= 'a' && name[0] <= 'z')
        return (SDL_Scancode)(SDL_SCANCODE_A + (name[0] - 'a'));
    return SDL_SCANCODE_UNKNOWN;
}

static void script_load(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[300];
    while (fgets(line, sizeof(line), f) && script_len < 256) {
        if (line[0] == '#' || line[0] == '\n') continue;
        script_cmd_t *c = &script[script_len];
        if (sscanf(line, "%d %15s %255s", &c->frame, c->cmd, c->arg) >= 2) {
            if (sscanf(line, "%d %15s", &c->frame, c->cmd) >= 2 &&
                sscanf(line, "%*d %*s %255[^\n]", c->arg) < 1)
                c->arg[0] = 0;
            script_len++;
        }
    }
    fclose(f);
    fprintf(stderr, "Script: %d commands from %s\n", script_len, path);
}

static void script_inject_key(SDL_Scancode sc) {
    SDL_Event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = SDL_KEYDOWN;
    ev.key.keysym.scancode = sc;
    SDL_PushEvent(&ev);
}

static void script_exec(unsigned fc) {
    for (int i = 0; i < script_len; i++) {
        if (script[i].frame != (int)fc) continue;
        if (!strcmp(script[i].cmd, "key")) {
            SDL_Scancode sc = key_from_name(script[i].arg);
            if (sc != SDL_SCANCODE_UNKNOWN) script_inject_key(sc);
        } else if (!strcmp(script[i].cmd, "snap")) {
            snprintf(snap_path, sizeof(snap_path), "%s", script[i].arg);
            snap_frame = frame_count + 1;
        } else if (!strcmp(script[i].cmd, "quit")) {
            SDL_Event ev; ev.type = SDL_QUIT;
            SDL_PushEvent(&ev);
        } else if (!strcmp(script[i].cmd, "poke")) {
            /* poke <addr_hex> <value_hex>  — write 16-bit to 68K work RAM */
            if (wram_ptr) {
                unsigned addr, val;
                if (sscanf(script[i].arg, "%x %x", &addr, &val) == 2) {
                    unsigned off = addr - 0x100000;
                    if (off + 1 < wram_size) {
                        wram_ptr[off] = (val >> 8) & 0xFF;
                        wram_ptr[off + 1] = val & 0xFF;
                        fprintf(stderr, "POKE: [%06X] = %04X\n", addr, val);
                    }
                }
            }
        } else if (!strcmp(script[i].cmd, "peek")) {
            /* peek <addr_hex>  — read 16-bit from 68K work RAM */
            if (wram_ptr) {
                unsigned addr;
                if (sscanf(script[i].arg, "%x", &addr) == 1) {
                    unsigned off = addr - 0x100000;
                    if (off + 1 < wram_size) {
                        uint16_t val = ((uint16_t)wram_ptr[off] << 8) | wram_ptr[off + 1];
                        fprintf(stderr, "PEEK: [%06X] = %04X (frame %u)\n", addr, val, fc);
                    }
                }
            }
        } else if (!strcmp(script[i].cmd, "vram")) {
            if (vram_ptr_script) {
                FILE *vf = fopen(script[i].arg, "wb");
                if (vf) {
                    fwrite(vram_ptr_script, 2, 0x10000, vf);
                    fclose(vf);
                    fprintf(stderr, "VRAM dump: %s\n", script[i].arg);
                }
            }
        } else if (!strcmp(script[i].cmd, "sprdump")) {
            if (vram_ptr_script && sprite_pc_ptr_script) {
                FILE *sf = fopen(script[i].arg, "wb");
                if (sf) {
                    // Header: magic + version + frame number
                    uint32_t magic = 0x53505244; // "SPRD"
                    uint32_t version = palram_ptr ? 2 : 1;
                    uint32_t fn = fc;
                    fwrite(&magic, 4, 1, sf);
                    fwrite(&version, 4, 1, sf);
                    fwrite(&fn, 4, 1, sf);
                    // 382 sprite slots: PC + SCB1 tiles + SCB2/3/4
                    for (int s = 0; s < 382; s++) {
                        uint32_t pc = sprite_pc_ptr_script[s];
                        uint16_t scb3 = vram_ptr_script[0x8200 + s];
                        uint16_t scb4 = vram_ptr_script[0x8400 + s];
                        uint16_t scb2 = vram_ptr_script[0x8000 + s];
                        fwrite(&pc, 4, 1, sf);
                        fwrite(&scb2, 2, 1, sf);
                        fwrite(&scb3, 2, 1, sf);
                        fwrite(&scb4, 2, 1, sf);
                        // SCB1: 64 words (32 tile+attr pairs)
                        fwrite(&vram_ptr_script[s * 64], 2, 64, sf);
                    }
                    // v2: append palette RAM (8192 words = 16KB)
                    if (palram_ptr) {
                        fwrite(palram_ptr, 2, 8192, sf);
                    }
                    fclose(sf);
                    fprintf(stderr, "Sprite dump v%u: %s (frame %u)\n", version, script[i].arg, fc);
                }
            }
        }
    }
}

/* ═══ Sprite recorder (F8 toggle) ═══ */

static FILE *rec_file = NULL;
static uint32_t rec_frames = 0;
static char rec_path[512];

// Previous frame state for delta compression
static uint16_t prev_scb1[382][64];
static uint16_t prev_scb3[382];
static uint16_t prev_scb4[382];
static uint32_t prev_pc[382];
static bool rec_has_prev = false;

static void rec_start(const char *dir) {
    char ts[32];
    time_t now = time(NULL);
    strftime(ts, sizeof(ts), "%Y%m%d_%H%M%S", localtime(&now));
    snprintf(rec_path, sizeof(rec_path), "%s/rec_%s.sprec", dir, ts);
    rec_file = fopen(rec_path, "wb");
    if (!rec_file) { fprintf(stderr, "REC: failed to open %s\n", rec_path); return; }

    // Header: magic + version
    uint32_t magic = 0x53524543; // "SREC"
    uint32_t version = 1;
    fwrite(&magic, 4, 1, rec_file);
    fwrite(&version, 4, 1, rec_file);

    rec_frames = 0;
    rec_has_prev = false;
    fprintf(stderr, "REC: started → %s\n", rec_path);
}

static void rec_stop(void) {
    if (!rec_file) return;
    // Write frame count at end
    uint32_t marker = 0xFFFFFFFF;
    fwrite(&marker, 4, 1, rec_file);
    fwrite(&rec_frames, 4, 1, rec_file);
    fclose(rec_file);
    fprintf(stderr, "REC: stopped, %u frames → %s\n", rec_frames, rec_path);
    rec_file = NULL;
}

static void rec_frame(unsigned fc) {
    if (!rec_file || !vram_ptr_script || !sprite_pc_ptr_script) return;

    // Collect active slots (non-zero tiles)
    uint8_t active[382];
    int num_active = 0;
    for (int s = 0; s < 382; s++) {
        active[s] = 0;
        uint16_t scb3 = vram_ptr_script[0x8200 + s];
        int height = scb3 & 0x3F;
        for (int t = 0; t < height && t < 32; t++) {
            if (vram_ptr_script[s * 64 + t * 2] != 0) { active[s] = 1; num_active++; break; }
        }
    }

    // Check if anything changed from previous frame
    bool changed = !rec_has_prev;
    if (!changed) {
        for (int s = 0; s < 382 && !changed; s++) {
            if (!active[s] && prev_pc[s] == 0) continue;
            if (sprite_pc_ptr_script[s] != prev_pc[s]) { changed = true; break; }
            if (vram_ptr_script[0x8200 + s] != prev_scb3[s]) { changed = true; break; }
            if (vram_ptr_script[0x8400 + s] != prev_scb4[s]) { changed = true; break; }
            for (int w = 0; w < 64; w++) {
                if (vram_ptr_script[s * 64 + w] != prev_scb1[s][w]) { changed = true; break; }
            }
        }
    }

    // Frame record: frame_num + num_active_slots + per-slot data
    // Only write full frames when something changed, otherwise just frame marker
    uint32_t fn = fc;
    fwrite(&fn, 4, 1, rec_file);

    if (!changed) {
        // Delta: nothing changed, write 0 slots
        uint16_t ns = 0;
        fwrite(&ns, 2, 1, rec_file);
    } else {
        uint16_t ns = (uint16_t)num_active;
        fwrite(&ns, 2, 1, rec_file);

        for (int s = 0; s < 382; s++) {
            if (!active[s]) continue;
            uint16_t slot_id = (uint16_t)s;
            uint32_t pc = sprite_pc_ptr_script[s];
            uint16_t scb2 = vram_ptr_script[0x8000 + s];
            uint16_t scb3 = vram_ptr_script[0x8200 + s];
            uint16_t scb4 = vram_ptr_script[0x8400 + s];

            fwrite(&slot_id, 2, 1, rec_file);
            fwrite(&pc, 4, 1, rec_file);
            fwrite(&scb2, 2, 1, rec_file);
            fwrite(&scb3, 2, 1, rec_file);
            fwrite(&scb4, 2, 1, rec_file);

            int height = scb3 & 0x3F;
            uint8_t h = (uint8_t)(height > 32 ? 32 : height);
            fwrite(&h, 1, 1, rec_file);
            fwrite(&vram_ptr_script[s * 64], 2, h * 2, rec_file);

            // Update prev state
            prev_pc[s] = pc;
            prev_scb3[s] = scb3;
            prev_scb4[s] = scb4;
            memcpy(prev_scb1[s], &vram_ptr_script[s * 64], 128);
        }

        // Write palette on first frame and every 60 frames
        if (palram_ptr && (rec_frames == 0 || rec_frames % 60 == 0)) {
            uint16_t pal_marker = 0xFFFE;
            fwrite(&pal_marker, 2, 1, rec_file);
            fwrite(palram_ptr, 2, 8192, rec_file);
        }
    }

    // Clear prev state for inactive slots
    for (int s = 0; s < 382; s++) {
        if (!active[s]) { prev_pc[s] = 0; prev_scb3[s] = 0; prev_scb4[s] = 0; }
    }
    rec_has_prev = true;
    rec_frames++;
}

/* ═══ Sprite debug panel ═══ */

#define MAX_PC_GROUPS 64
typedef struct {
    uint32_t pc;       // P-ROM address
    int num_chains;    // how many chains this routine manages
    int num_sprites;   // total sprites across all chains
} pc_group_t;

static pc_group_t pc_groups[MAX_PC_GROUPS];
static int num_pc_groups = 0;
static int chain_scroll = 0;
static bool sprite_panel = false;
static bool sprite_step = false;
static int chain_cursor = 0;
static uint16_t *vram_ptr = NULL;
static uint32_t *sprite_pc_ptr = NULL;
static uint32_t *blocked_pcs_ptr = NULL;  // points into Geolith's blocked_pcs[]
static int *num_blocked_ptr = NULL;       // points into Geolith's num_blocked_pcs

static bool is_pc_hidden(uint32_t pc) {
    if (!num_blocked_ptr) return false;
    for (int i = 0; i < *num_blocked_ptr; i++)
        if (blocked_pcs_ptr[i] == pc) return true;
    return false;
}

static void toggle_pc(uint32_t pc) {
    if (!pc || !blocked_pcs_ptr || !num_blocked_ptr) {
        fprintf(stderr, "toggle_pc: NULL ptr (pc=%06X, bpc=%p, nbp=%p)\n", pc, (void*)blocked_pcs_ptr, (void*)num_blocked_ptr);
        return;
    }
    for (int i = 0; i < *num_blocked_ptr; i++) {
        if (blocked_pcs_ptr[i] == pc) {
            blocked_pcs_ptr[i] = blocked_pcs_ptr[--(*num_blocked_ptr)];
            fprintf(stderr, "UNBLOCK PC $%06X (now %d blocked)\n", pc, *num_blocked_ptr);
            return;
        }
    }
    if (*num_blocked_ptr < 64) {
        blocked_pcs_ptr[(*num_blocked_ptr)++] = pc;
        fprintf(stderr, "BLOCK PC $%06X (now %d blocked)\n", pc, *num_blocked_ptr);
    }
}

static void sprite_analyze(void) {
    if (!vram_ptr || !sprite_pc_ptr) return;
    num_pc_groups = 0;

    // Walk all chain heads, group by PC
    for (int i = 1; i < 382; i++) {
        if (vram_ptr[0x8200 + i] & 0x40) continue; // sticky, not a head

        uint32_t pc = sprite_pc_ptr ? sprite_pc_ptr[i] : 0;

        int chain_len = 1;
        int j = i + 1;
        while (j < 382 && (vram_ptr[0x8200 + j] & 0x40)) { chain_len++; j++; }

        // Find or create group
        int gi = -1;
        for (int g = 0; g < num_pc_groups; g++) {
            if (pc_groups[g].pc == pc) { gi = g; break; }
        }
        if (gi < 0 && num_pc_groups < MAX_PC_GROUPS) {
            gi = num_pc_groups++;
            pc_groups[gi].pc = pc;
            pc_groups[gi].num_chains = 0;
            pc_groups[gi].num_sprites = 0;
        }
        if (gi >= 0) {
            pc_groups[gi].num_chains++;
            pc_groups[gi].num_sprites += chain_len;
        }
    }

    // Sort by highest sprite index first (most sprites = background at bottom)
    // Simple: sort by num_sprites ascending so small groups (HUD, chars) come first
    for (int i = 0; i < num_pc_groups - 1; i++)
        for (int j = i + 1; j < num_pc_groups; j++)
            if (pc_groups[i].num_sprites > pc_groups[j].num_sprites) {
                pc_group_t tmp = pc_groups[i];
                pc_groups[i] = pc_groups[j];
                pc_groups[j] = tmp;
            }

    if (chain_cursor < 0) chain_cursor = 0;
    if (chain_cursor >= num_pc_groups) chain_cursor = num_pc_groups > 0 ? num_pc_groups - 1 : 0;
}

#define PANEL_W 300
#define PANEL_ROWS 20

static void sprite_panel_draw(int win_w, int win_h) {
    sprite_analyze();

    static uint32_t pixels[PANEL_W * 512];
    int ph = PANEL_ROWS * 14 + 30;
    memset(pixels, 0, PANEL_W * ph * 4);

    // Background
    for (int y = 0; y < ph; y++)
        for (int x = 0; x < PANEL_W; x++)
            pixels[y * PANEL_W + x] = 0xF0101010;

    // Title
    char title[48];
    snprintf(title, sizeof(title), "  PC     CHN SPR");
    menu_render_text(pixels, PANEL_W, 4, 4, title, 0xFF00FF44);

    int max_scroll = num_pc_groups > PANEL_ROWS ? num_pc_groups - PANEL_ROWS : 0;
    if (chain_scroll > max_scroll) chain_scroll = max_scroll;
    if (chain_scroll < 0) chain_scroll = 0;

    for (int r = 0; r < PANEL_ROWS && (chain_scroll + r) < num_pc_groups; r++) {
        int ci = chain_scroll + r;
        pc_group_t *g = &pc_groups[ci];
        int ry = 20 + r * 14;

        if (ci == chain_cursor) {
            for (int y = ry; y < ry + 12; y++)
                for (int x = 2; x < PANEL_W - 2; x++)
                    pixels[y * PANEL_W + x] = 0xFF003818;
        }

        bool hidden = is_pc_hidden(g->pc);
        char line[48];
        snprintf(line, sizeof(line), "%c %06X  %2d %3d",
                 hidden ? '-' : '*', g->pc & 0xFFFFFF, g->num_chains, g->num_sprites);
        uint32_t col = hidden ? 0xFF555555 : (ci == chain_cursor ? 0xFF44FF88 : 0xFFAADDAA);
        menu_render_text(pixels, PANEL_W, 4, ry + 2, line, col);
    }

    // Upload as texture
    static GLuint panel_tex = 0;
    if (!panel_tex) {
        glGenTextures(1, &panel_tex);
        glBindTexture(GL_TEXTURE_2D, panel_tex);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    }
    glBindTexture(GL_TEXTURE_2D, panel_tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, PANEL_W, ph, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, pixels);

    // Draw on right side of screen
    glUseProgram(0);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_TEXTURE_2D);
    float px = 1.0f - (float)(PANEL_W * 2) / win_w;
    float py = 1.0f;
    float pw = 2.0f * PANEL_W / win_w;
    float pht = 2.0f * ph / win_h;
    glBegin(GL_QUADS);
    glTexCoord2f(0, 0); glVertex2f(px, py);
    glTexCoord2f(1, 0); glVertex2f(px + pw, py);
    glTexCoord2f(1, (float)ph / 512.0f); glVertex2f(px + pw, py - pht);
    glTexCoord2f(0, (float)ph / 512.0f); glVertex2f(px, py - pht);
    glEnd();
    glDisable(GL_BLEND);
    glDisable(GL_TEXTURE_2D);
}

/* ═══ Save states ═══ */

static char state_base[512];
static int state_wait = 0;  // 0=idle, 'S'=waiting for save key, 'L'=waiting for load key
static int state_msg_frames = 0;
static char state_msg[64];

static char slot_char(SDL_Scancode sc) {
    if (sc >= SDL_SCANCODE_A && sc <= SDL_SCANCODE_Z) return 'a' + (sc - SDL_SCANCODE_A);
    if (sc >= SDL_SCANCODE_0 && sc <= SDL_SCANCODE_9) return '0' + (sc - SDL_SCANCODE_0);
    return 0;
}

static void state_save(char slot) {
    size_t sz = core.serialize_size();
    if (!sz) { snprintf(state_msg, sizeof(state_msg), "NO STATE SUPPORT"); state_msg_frames = 120; return; }
    void *buf = malloc(sz);
    if (!core.serialize(buf, sz)) { free(buf); snprintf(state_msg, sizeof(state_msg), "SAVE FAILED"); state_msg_frames = 120; return; }
    char path[576];
    snprintf(path, sizeof(path), "%s/%s.st%c", save_dir, state_base, slot);
    FILE *f = fopen(path, "wb");
    if (f) { fwrite(buf, 1, sz, f); fclose(f); }
    free(buf);
    snprintf(state_msg, sizeof(state_msg), "SAVED: %c", slot >= 'a' ? slot - 32 : slot);
    state_msg_frames = 90;
    fprintf(stderr, "State saved: %s\n", path);
}

static void state_load(char slot) {
    char path[576];
    snprintf(path, sizeof(path), "%s/%s.st%c", save_dir, state_base, slot);
    FILE *f = fopen(path, "rb");
    if (!f) { snprintf(state_msg, sizeof(state_msg), "EMPTY: %c", slot >= 'a' ? slot - 32 : slot); state_msg_frames = 90; return; }
    fseek(f, 0, SEEK_END); size_t sz = ftell(f); fseek(f, 0, SEEK_SET);
    void *buf = malloc(sz);
    fread(buf, 1, sz, f); fclose(f);
    if (!core.unserialize(buf, sz))
        snprintf(state_msg, sizeof(state_msg), "LOAD FAILED: %c", slot >= 'a' ? slot - 32 : slot);
    else
        snprintf(state_msg, sizeof(state_msg), "LOADED: %c", slot >= 'a' ? slot - 32 : slot);
    free(buf);
    state_msg_frames = 90;
    fprintf(stderr, "State loaded: %s\n", path);
}

/* ═══ Main ═══ */

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s game.neo [--snap F1,F2,...] [--quit F] [--script file] [core.so]\n", argv[0]);
        return 1;
    }

    const char *game = argv[1];
    const char *core_override = NULL;
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--snap") && i+1 < argc) {
            char *s = argv[++i];
            while (*s && num_auto_snaps < 16) {
                auto_snaps[num_auto_snaps++] = atoi(s);
                while (*s && *s != ',') s++;
                if (*s == ',') s++;
            }
        } else if (!strcmp(argv[i], "--quit") && i+1 < argc) {
            auto_quit_frame = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--script") && i+1 < argc) {
            script_load(argv[++i]);
        } else {
            core_override = argv[i];
        }
    }

    char default_core[512];
    snprintf(default_core, sizeof(default_core), "%s/.config/retroarch/cores/geolith_libretro.so",
             getenv("HOME"));
    const char *core_path = core_override ? core_override : default_core;

    snprintf(sys_dir, sizeof(sys_dir), "%s/.config/retroarch/system", getenv("HOME"));
    snprintf(save_dir, sizeof(save_dir), "%s/.config/retroarch/saves", getenv("HOME"));

    if (access("/dev/shm/neocart_bus", F_OK) == 0)
        setenv("NEOCART_SHM", "1", 1);

    // Extract game basename for state files (e.g. "kof95" from "/data/roms/kof95.neo")
    const char *bn = strrchr(game, '/');
    bn = bn ? bn + 1 : game;
    snprintf(state_base, sizeof(state_base), "%s", bn);
    char *dot = strrchr(state_base, '.');
    if (dot) *dot = 0;

    if (!core_load(core_path)) return 1;
    printf("Core: %s (API %u)\n", core_path, core.api_version());

    SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER);

    for (int i = 0, p = 0; i < SDL_NumJoysticks() && p < 2; i++) {
        if (SDL_IsGameController(i)) {
            pad[p] = SDL_GameControllerOpen(i);
            if (pad[p]) fprintf(stderr, "Pad %d: %s\n", p, SDL_GameControllerName(pad[p]));
            p++;
        }
    }

    core.set_environment(environ_cb);
    core.set_video_refresh(video_cb);
    core.set_audio_sample(audio_sample_cb);
    core.set_audio_sample_batch(audio_batch_cb);
    core.set_input_poll(input_poll_cb);
    core.set_input_state(input_state_cb);
    core.init();

    game_path_global = game;
    struct retro_game_info info = { .path = game };
    if (!core.load_game(&info)) {
        fprintf(stderr, "Failed to load: %s\n", game);
        core.deinit();
        return 1;
    }

    // Read NVRAM to sync menu with UniBIOS settings
    {
        char nvpath[576];
        snprintf(nvpath, sizeof(nvpath), "%s/%s.nv", save_dir, state_base);
        FILE *nf = fopen(nvpath, "rb");
        if (nf) {
            fseek(nf, 2, SEEK_SET);
            uint8_t mode, reg;
            if (fread(&mode, 1, 1, nf) == 1 && fread(&reg, 1, 1, nf) == 1) {
                opt_hw = (mode == 0x00) ? 1 : 0;
                if (reg <= 3) opt_region = reg;
            }
            fclose(nf);
        }
    }

    blocked_pcs_ptr = (uint32_t *)core.get_memory_data(100);
    vram_ptr = (uint16_t *)core.get_memory_data(101);
    vram_ptr_script = vram_ptr;
    sprite_pc_ptr = (uint32_t *)core.get_memory_data(102);
    sprite_pc_ptr_script = sprite_pc_ptr;
    num_blocked_ptr = (int *)core.get_memory_data(103);
    palram_ptr = (uint16_t *)core.get_memory_data(104);
    wram_ptr = (uint8_t *)core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM);
    wram_size = core.get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
    if (wram_ptr) fprintf(stderr, "WRAM: %zu bytes at %p\n", wram_size, (void*)wram_ptr);

    struct retro_system_av_info av;
    core.get_system_av_info(&av);
    double fps = av.timing.fps;
    int srate = (int)av.timing.sample_rate;
    printf("Video: %ux%u @ %.2f Hz | Audio: %d Hz stereo\n",
           av.geometry.base_width, av.geometry.base_height, fps, srate);

    int scale = 6;
    int win_w = av.geometry.base_width * scale;
    int win_h = av.geometry.base_height * scale;

    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_Window *window = SDL_CreateWindow("NeoScanSDK",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, win_w, win_h,
        SDL_WINDOW_OPENGL);
    SDL_GLContext glctx = SDL_GL_CreateContext(window);
    SDL_GL_SetSwapInterval(0);

    glGenTextures(1, &gl_tex);
    glBindTexture(GL_TEXTURE_2D, gl_tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8,
                 av.geometry.base_width, av.geometry.base_height,
                 0, GL_BGRA, GL_UNSIGNED_BYTE, NULL);

    gl_prog = build_program();
    glUseProgram(gl_prog);
    glUniform1i(glGetUniformLocation(gl_prog, "tex"), 0);

    static const float quad[] = { -1,-1, 1,-1, -1,1, 1,1 };
    GLuint vbo;
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0);

    SDL_AudioSpec want = {0}, have;
    want.freq = srate;
    want.format = AUDIO_S16SYS;
    want.channels = 2;
    want.samples = 1024;
    want.callback = sdl_audio_cb;
    SDL_AudioDeviceID adev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
    if (adev) SDL_PauseAudioDevice(adev, 0);

    kbd = SDL_GetKeyboardState(NULL);

    bool running = true;
    bool crt_on = true;
    int autoload_frame = 30;

    while (running) {
        uint64_t t0 = SDL_GetPerformanceCounter();

        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) running = false;
            if (ev.type == SDL_CONTROLLERDEVICEADDED) {
                for (int p = 0; p < 2; p++) {
                    if (!pad[p]) {
                        pad[p] = SDL_GameControllerOpen(ev.cdevice.which);
                        if (pad[p]) fprintf(stderr, "Pad %d connected: %s\n", p, SDL_GameControllerName(pad[p]));
                        break;
                    }
                }
            }
            if (ev.type == SDL_CONTROLLERDEVICEREMOVED) {
                for (int p = 0; p < 2; p++) {
                    if (pad[p] && ev.cdevice.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pad[p]))) {
                        fprintf(stderr, "Pad %d disconnected\n", p);
                        SDL_GameControllerClose(pad[p]);
                        pad[p] = NULL;
                    }
                }
            }
            if (ev.type == SDL_KEYDOWN) {
                SDL_Scancode sc = ev.key.keysym.scancode;
                if (menu_open) {
                    if (sc == SDL_SCANCODE_F1 || sc == SDL_SCANCODE_ESCAPE) menu_open = false;
                    if (sc == SDL_SCANCODE_UP) menu_sel = (menu_sel + MENU_COUNT - 1) % MENU_COUNT;
                    if (sc == SDL_SCANCODE_DOWN) menu_sel = (menu_sel + 1) % MENU_COUNT;
                    if (sc == SDL_SCANCODE_RETURN) {
                        switch (menu_sel) {
                            case MENU_RESUME: menu_open = false; break;
                            case MENU_RESET: opt_vars_dirty = true; pending_reset = 2; menu_open = false; break;
                            case MENU_HW: opt_hw ^= 1; break;
                            case MENU_REGION: opt_region = (opt_region + 1) % 4; break;
                        }
                    }
                    if (sc == SDL_SCANCODE_LEFT) {
                        if (menu_sel == MENU_HW) opt_hw ^= 1;
                        if (menu_sel == MENU_REGION) opt_region = (opt_region + 3) % 4;
                    }
                    if (sc == SDL_SCANCODE_RIGHT) {
                        if (menu_sel == MENU_HW) opt_hw ^= 1;
                        if (menu_sel == MENU_REGION) opt_region = (opt_region + 1) % 4;
                    }
                } else if (state_wait) {
                    char c = slot_char(sc);
                    if (c) {
                        if (state_wait == 'S') state_save(c);
                        else state_load(c);
                    }
                    state_wait = 0;
                } else {
                    if (sc == SDL_SCANCODE_ESCAPE) running = false;
                    if (sc == SDL_SCANCODE_F1) { menu_open = true; menu_sel = 0; }
                    if (sc == SDL_SCANCODE_F3) {
                        sprite_panel = !sprite_panel;
                        if (sprite_panel) {
                            sprite_analyze();
                            fprintf(stderr, "=== SPRITE DEBUG ===\n");
                            fprintf(stderr, "blocked_pcs_ptr=%p num_blocked_ptr=%p sprite_pc_ptr=%p vram_ptr=%p\n",
                                (void*)blocked_pcs_ptr, (void*)num_blocked_ptr, (void*)sprite_pc_ptr, (void*)vram_ptr);
                            if (num_blocked_ptr) fprintf(stderr, "num_blocked=%d\n", *num_blocked_ptr);
                            fprintf(stderr, "PC groups: %d\n", num_pc_groups);
                            for (int i = 0; i < num_pc_groups && i < 10; i++)
                                fprintf(stderr, "  [%d] PC=$%06X chains=%d sprites=%d\n",
                                    i, pc_groups[i].pc, pc_groups[i].num_chains, pc_groups[i].num_sprites);
                        }
                    }
                    if (sprite_panel && !menu_open) {
                        if (sc == SDL_SCANCODE_PAGEUP) { chain_cursor -= PANEL_ROWS; if (chain_cursor < 0) chain_cursor = 0; }
                        if (sc == SDL_SCANCODE_PAGEDOWN) { chain_cursor += PANEL_ROWS; if (chain_cursor >= num_pc_groups) chain_cursor = num_pc_groups - 1; }
                        if (sc == SDL_SCANCODE_HOME) chain_cursor = 0;
                        if (sc == SDL_SCANCODE_END) chain_cursor = num_pc_groups - 1;
                        if (sc == SDL_SCANCODE_UP) { chain_cursor--; if (chain_cursor < 0) chain_cursor = 0; }
                        if (sc == SDL_SCANCODE_DOWN) { chain_cursor++; if (chain_cursor >= num_pc_groups) chain_cursor = num_pc_groups - 1; }
                        if (sc == SDL_SCANCODE_KP_ENTER || sc == SDL_SCANCODE_BACKSPACE) {
                            if (chain_cursor >= 0 && chain_cursor < num_pc_groups) {
                                toggle_pc(pc_groups[chain_cursor].pc);
                                core.get_memory_data(199); // trigger rerender
                            }
                        }
                        if (sc == SDL_SCANCODE_KP_0 || sc == SDL_SCANCODE_DELETE) {
                            if (num_blocked_ptr) *num_blocked_ptr = 0;
                            core.get_memory_data(199); // trigger rerender
                        }
                        // Keep cursor in scroll view
                        if (chain_cursor < chain_scroll) chain_scroll = chain_cursor;
                        if (chain_cursor >= chain_scroll + PANEL_ROWS) chain_scroll = chain_cursor - PANEL_ROWS + 1;
                    }
                    if (sc == SDL_SCANCODE_F2) crt_on = !crt_on;
                    if (sc == SDL_SCANCODE_F5) {
                        snprintf(snap_path, sizeof(snap_path), "/tmp/neoscan_%u.ppm", frame_count);
                        snap_frame = frame_count + 1;
                    }
                    if (sc == SDL_SCANCODE_F6) { state_wait = 'S'; state_msg_frames = 0; }
                    if (sc == SDL_SCANCODE_F7) { state_wait = 'L'; state_msg_frames = 0; }
                    if (sc == SDL_SCANCODE_F8) {
                        if (rec_file) {
                            rec_stop();
                            snprintf(state_msg, sizeof(state_msg), "REC STOP");
                        } else {
                            rec_start("/data/sonicwings/sw2");
                            snprintf(state_msg, sizeof(state_msg), "REC START");
                        }
                        state_msg_frames = 120;
                    }
                }
            }
        }

        static unsigned tick = 0;
        tick++;
        script_exec(tick);

        if (sprite_panel) sprite_analyze();

        /* ── Frame flags: what to do this iteration ── */
        enum {
            FL_RUN_CORE   = 1 << 0,  // advance emulation
            FL_RERENDER   = 1 << 1,  // re-render without advancing
            FL_DRAW_GAME  = 1 << 2,  // blit game texture
            FL_DRAW_MENU  = 1 << 3,  // draw menu overlay
            FL_DRAW_PANEL = 1 << 4,  // draw sprite debug panel
        };

        unsigned flags = FL_DRAW_GAME;

        if (menu_open)                          flags |= FL_DRAW_MENU;
        else if (sprite_panel)                  flags |= FL_DRAW_PANEL;
        else                                    flags |= FL_RUN_CORE;


        /* ── Execute ── */
        if (flags & FL_RUN_CORE) {
            core.run();
            /* VBlank miss detection: read game tick from debug RAM */
            if (wram_ptr && wram_size >= 0xF206) {
                uint16_t game_tick = ((uint16_t)wram_ptr[0xF204] << 8) | wram_ptr[0xF205];
                if (game_tick > 0 && game_tick == vblank_prev_tick)
                    vblank_misses++;
                vblank_prev_tick = game_tick;
            }
            if (rec_file) rec_frame(tick);
            if (autoload_frame > 0 && (int)frame_count == autoload_frame) {
                state_load('s');
                autoload_frame = 0;
            }
            if (pending_reset > 0 && --pending_reset == 0) {
                void *sysram = core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM);
                size_t ramsz = core.get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
                if (sysram && ramsz) memset(sysram, 0, ramsz);
                core.unload_game();
                core.deinit();
                char nvpath[576];
                snprintf(nvpath, sizeof(nvpath), "%s/%s.nv", save_dir, state_base);
                FILE *nf = fopen(nvpath, "r+b");
                if (nf) {
                    fseek(nf, 2, SEEK_SET);
                    uint8_t mode = opt_hw ? 0x00 : 0x80;
                    uint8_t reg = (uint8_t)opt_region;
                    fwrite(&mode, 1, 1, nf);
                    fwrite(&reg, 1, 1, nf);
                    fclose(nf);
                }
                core.init();
                struct retro_game_info ri = { .path = game_path_global };
                core.load_game(&ri);
                blocked_pcs_ptr = (uint32_t *)core.get_memory_data(100);
                vram_ptr = (uint16_t *)core.get_memory_data(101);
                vram_ptr_script = vram_ptr;
                sprite_pc_ptr = (uint32_t *)core.get_memory_data(102);
                sprite_pc_ptr_script = sprite_pc_ptr;
                num_blocked_ptr = (int *)core.get_memory_data(103);
                palram_ptr = (uint16_t *)core.get_memory_data(104);
                wram_ptr = (uint8_t *)core.get_memory_data(RETRO_MEMORY_SYSTEM_RAM);
                wram_size = core.get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
            }
            if (auto_quit_frame > 0 && (int)frame_count >= auto_quit_frame) running = false;
        }



        /* ── Window title ── */
        if (state_wait)
            SDL_SetWindowTitle(window, state_wait == 'S' ? "NeoScanSDK [SAVE: press A-Z / 0-9]" : "NeoScanSDK [LOAD: press A-Z / 0-9]");
        else if (state_msg_frames > 0) {
            char title[128]; snprintf(title, sizeof(title), "NeoScanSDK [%s]", state_msg);
            SDL_SetWindowTitle(window, title);
            state_msg_frames--;
        } else
            SDL_SetWindowTitle(window, "NeoScanSDK");

        /* ── Render ── */
        if (flags & FL_DRAW_GAME) {
            glViewport(0, 0, win_w, win_h);
            glUseProgram(gl_prog);
            glUniform2f(glGetUniformLocation(gl_prog, "texSize"),
                        (float)tex_w, (float)tex_h);
            glUniform2f(glGetUniformLocation(gl_prog, "outSize"),
                        crt_on ? (float)win_w : 1.0f,
                        crt_on ? (float)win_h : 1.0f);
            glActiveTexture(GL_TEXTURE0);
            glBindTexture(GL_TEXTURE_2D, gl_tex);
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        }
        if (flags & FL_DRAW_PANEL) sprite_panel_draw(win_w, win_h);
        if (flags & FL_DRAW_MENU)  menu_draw(win_w, win_h);
        SDL_GL_SwapWindow(window);

        uint64_t t1 = SDL_GetPerformanceCounter();
        double elapsed = (double)(t1 - t0) / SDL_GetPerformanceFrequency();
        double target_t = 1.0 / fps;
        if (elapsed > target_t * 1.1 && (tick & 63) == 0)
            fprintf(stderr, "FRAME OVERRUN: %.2fms (budget %.2fms) tick=%u\n",
                    elapsed * 1000.0, target_t * 1000.0, tick);
        if (elapsed < target_t) {
            double remain = (target_t - elapsed) * 1000.0;
            if (remain > 1.0) SDL_Delay((uint32_t)(remain - 0.5));
            while ((double)(SDL_GetPerformanceCounter() - t0) / SDL_GetPerformanceFrequency() < target_t)
                ;
        }
    }

    fprintf(stderr, "VBLANK STATS: %u emu_frames, %u misses (%s)\n",
        frame_count, vblank_misses, vblank_misses == 0 ? "SOLID 60fps" : "DROPPING");
    if (adev) { SDL_PauseAudioDevice(adev, 1); SDL_CloseAudioDevice(adev); }
    core.unload_game();
    core.deinit();
    glDeleteTextures(1, &gl_tex);
    glDeleteProgram(gl_prog);
    glDeleteBuffers(1, &vbo);
    SDL_GL_DeleteContext(glctx);
    SDL_DestroyWindow(window);
    SDL_Quit();
    dlclose(core.handle);
    return 0;
}
