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
    #undef LOAD
    return true;
}

/* ═══ Environment callback ═══ */

static char sys_dir[512];
static char save_dir[512];

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
        if (!strcmp(v->key, "geolith_unibios_hw"))    { v->value = "mvs";     return true; }
        if (!strcmp(v->key, "geolith_region"))         { v->value = "us";      return true; }
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
        *(bool *)data = false; return true;
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

static size_t audio_batch_cb(const int16_t *data, size_t frames) {
    for (size_t i = 0; i < frames; i++) {
        uint32_t next = (ring_w + 1) & (RING_SIZE - 1);
        if (next == ring_r) break;
        ring_buf[ring_w * 2]     = data[i * 2];
        ring_buf[ring_w * 2 + 1] = data[i * 2 + 1];
        ring_w = next;
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
    "    int subpx = int(mod(px.x, 4.0));\n"
    "    vec3 mask;\n"
    "    if (subpx == 0)      mask = vec3(1.0, 0.0, 0.0);\n"
    "    else if (subpx == 1) mask = vec3(0.0, 1.0, 0.0);\n"
    "    else if (subpx == 2) mask = vec3(0.0, 0.0, 1.0);\n"
    "    else                 mask = vec3(0.0, 0.0, 0.0);\n"
    "    float scanline = (mod(px.y, 4.0) < 3.0) ? 1.0 : 0.0;\n"
    "    gl_FragColor = vec4(col * mask * scanline, 1.0);\n"
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

static void video_cb(const void *data, unsigned w, unsigned h, size_t pitch) {
    if (!data) return;
    tex_w = w; tex_h = h;
    glBindTexture(GL_TEXTURE_2D, gl_tex);
    glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(pitch / 4));
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, data);
    glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
}

/* ═══ Input ═══ */

static const uint8_t *kbd;

static void input_poll_cb(void) {}

static int16_t input_state_cb(unsigned port, unsigned dev, unsigned idx, unsigned id) {
    (void)idx;
    if (dev != RETRO_DEVICE_JOYPAD) return 0;

    if (port == 0) {
        switch (id) {
        case RETRO_DEVICE_ID_JOYPAD_UP:     return kbd[SDL_SCANCODE_W];
        case RETRO_DEVICE_ID_JOYPAD_DOWN:   return kbd[SDL_SCANCODE_S];
        case RETRO_DEVICE_ID_JOYPAD_LEFT:   return kbd[SDL_SCANCODE_A];
        case RETRO_DEVICE_ID_JOYPAD_RIGHT:  return kbd[SDL_SCANCODE_D];
        case RETRO_DEVICE_ID_JOYPAD_B:      return kbd[SDL_SCANCODE_U];
        case RETRO_DEVICE_ID_JOYPAD_A:      return kbd[SDL_SCANCODE_I];
        case RETRO_DEVICE_ID_JOYPAD_Y:      return kbd[SDL_SCANCODE_O];
        case RETRO_DEVICE_ID_JOYPAD_X:      return kbd[SDL_SCANCODE_P];
        case RETRO_DEVICE_ID_JOYPAD_START:  return kbd[SDL_SCANCODE_1];
        case RETRO_DEVICE_ID_JOYPAD_SELECT: return kbd[SDL_SCANCODE_3];
        case RETRO_DEVICE_ID_JOYPAD_L3:     return kbd[SDL_SCANCODE_5];
        case RETRO_DEVICE_ID_JOYPAD_R3:     return kbd[SDL_SCANCODE_6];
        }
    } else if (port == 1) {
        switch (id) {
        case RETRO_DEVICE_ID_JOYPAD_UP:     return kbd[SDL_SCANCODE_UP];
        case RETRO_DEVICE_ID_JOYPAD_DOWN:   return kbd[SDL_SCANCODE_DOWN];
        case RETRO_DEVICE_ID_JOYPAD_LEFT:   return kbd[SDL_SCANCODE_LEFT];
        case RETRO_DEVICE_ID_JOYPAD_RIGHT:  return kbd[SDL_SCANCODE_RIGHT];
        case RETRO_DEVICE_ID_JOYPAD_START:  return kbd[SDL_SCANCODE_2];
        }
    }
    return 0;
}

/* ═══ Main ═══ */

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s game.neo [core.so]\n", argv[0]);
        return 1;
    }

    const char *game = argv[1];
    char default_core[512];
    snprintf(default_core, sizeof(default_core), "%s/.config/retroarch/cores/geolith_libretro.so",
             getenv("HOME"));
    const char *core_path = argc > 2 ? argv[2] : default_core;

    snprintf(sys_dir, sizeof(sys_dir), "%s/.config/retroarch/system", getenv("HOME"));
    snprintf(save_dir, sizeof(save_dir), "%s/.config/retroarch/saves", getenv("HOME"));

    if (access("/dev/shm/neocart_bus", F_OK) == 0)
        setenv("NEOCART_SHM", "1", 1);

    if (!core_load(core_path)) return 1;
    printf("Core: %s (API %u)\n", core_path, core.api_version());

    SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO);

    core.set_environment(environ_cb);
    core.set_video_refresh(video_cb);
    core.set_audio_sample(audio_sample_cb);
    core.set_audio_sample_batch(audio_batch_cb);
    core.set_input_poll(input_poll_cb);
    core.set_input_state(input_state_cb);
    core.init();

    struct retro_game_info info = { .path = game };
    if (!core.load_game(&info)) {
        fprintf(stderr, "Failed to load: %s\n", game);
        core.deinit();
        return 1;
    }

    struct retro_system_av_info av;
    core.get_system_av_info(&av);
    double fps = av.timing.fps;
    int srate = (int)av.timing.sample_rate;
    printf("Video: %ux%u @ %.2f Hz | Audio: %d Hz stereo\n",
           av.geometry.base_width, av.geometry.base_height, fps, srate);

    int scale = 4;
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
    while (running) {
        uint64_t t0 = SDL_GetPerformanceCounter();

        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) running = false;
            if (ev.type == SDL_KEYDOWN) {
                if (ev.key.keysym.scancode == SDL_SCANCODE_ESCAPE) running = false;
                if (ev.key.keysym.scancode == SDL_SCANCODE_F2) crt_on = !crt_on;
            }
        }

        core.run();

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
        SDL_GL_SwapWindow(window);

        uint64_t t1 = SDL_GetPerformanceCounter();
        double elapsed = (double)(t1 - t0) / SDL_GetPerformanceFrequency();
        double target_t = 1.0 / fps;
        if (elapsed < target_t) {
            double remain = (target_t - elapsed) * 1000.0;
            if (remain > 1.0) SDL_Delay((uint32_t)(remain - 0.5));
            while ((double)(SDL_GetPerformanceCounter() - t0) / SDL_GetPerformanceFrequency() < target_t)
                ;
        }
    }

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
