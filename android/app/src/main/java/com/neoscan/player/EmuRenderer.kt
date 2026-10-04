package com.neoscan.player

import android.opengl.GLES20
import android.opengl.GLSurfaceView
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/** Draws the newest frame: a 512x512 RGBA texture (the core's XRGB8888 words = bytes B,G,R,X: the shader swaps
 *  red and blue), the used w x h corner over the picture rectangle of [Screen.picture]; nearest filtering keeps the
 *  pixels sharp. The rest of the surface stays black. */
class EmuRenderer(private val emu: () -> EmuThread?) : GLSurfaceView.Renderer {
    private var prog = 0; private var tex = 0; private var sw = 0; private var sh = 0
    @Volatile var smooth = false                                    // settings: bilinear instead of nearest
    @Volatile var mode = 0                                          // 0 plain, 1 scanlines, 2 subpixel
    @Volatile var dark = 0.5f                                       // scanline darkness
    private var texSmooth = false
    private val quad = ByteBuffer.allocateDirect(16 * 4).order(ByteOrder.nativeOrder()).asFloatBuffer()

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        val vs = "attribute vec2 p; attribute vec2 t; varying vec2 v; void main(){ v = t; gl_Position = vec4(p, 0.0, 1.0); }"
        // mode 0 sharp / smooth (the texture filter decides), 1 scanlines: each source line bright in the middle,
        // darker towards its edges by `dark` (a cosine profile: no moire at non-integer scales), 2 subpixel = emu/
        // neogeo_sdl's shader: every screen pixel lights one of R G B (1.0, the other two 0.08), the triad shifted one
        // step per screen row; the last screen row of each source line dark when a line is 3+ rows (`k`, integer scale)
        val fs = "precision mediump float; varying vec2 v; uniform sampler2D s; uniform int mode; uniform float dark;" +
                 "uniform float k;" +
                 "void main(){ vec3 c = texture2D(s, v).bgr;" +
                 " if (mode == 1) { float f = fract(v.y * 512.0); c *= 1.0 - dark * (0.5 + 0.5 * cos(6.2831853 * f)); }" +
                 " else if (mode == 2) {" +
                 "  float sub = mod(floor(gl_FragCoord.x) + floor(gl_FragCoord.y), 3.0);" +
                 "  vec3 m = sub < 0.5 ? vec3(1.0, 0.08, 0.08) : sub < 1.5 ? vec3(0.08, 1.0, 0.08) : vec3(0.08, 0.08, 1.0);" +
                 "  if (k >= 3.0 && floor(fract(v.y * 512.0) * k) >= k - 1.0) m = vec3(0.0);" +
                 "  c *= m; }" +
                 " gl_FragColor = vec4(c, 1.0); }"
        prog = GLES20.glCreateProgram()
        for ((type, src) in listOf(GLES20.GL_VERTEX_SHADER to vs, GLES20.GL_FRAGMENT_SHADER to fs)) {
            val sh = GLES20.glCreateShader(type); GLES20.glShaderSource(sh, src); GLES20.glCompileShader(sh); GLES20.glAttachShader(prog, sh)
        }
        GLES20.glLinkProgram(prog)
        val ids = IntArray(1); GLES20.glGenTextures(1, ids, 0); tex = ids[0]
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_NEAREST)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_NEAREST)
        GLES20.glTexImage2D(GLES20.GL_TEXTURE_2D, 0, GLES20.GL_RGBA, 512, 512, 0, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, null)
    }
    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) { sw = width; sh = height }
    override fun onDrawFrame(gl: GL10?) {
        GLES20.glViewport(0, 0, sw, sh)
        GLES20.glClearColor(0f, 0f, 0f, 1f); GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        if (smooth != texSmooth) {
            texSmooth = smooth
            val f = if (smooth) GLES20.GL_LINEAR else GLES20.GL_NEAREST
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex)
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, f)
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, f)
        }
        val r = Screen.picture(sw, sh)
        GLES20.glViewport(r.left, sh - r.bottom, r.width(), r.height())          // GL counts y from the bottom
        val e = emu() ?: return
        var w: Int; var h: Int; var vsync: Long
        synchronized(e.lock) {
            w = e.w; h = e.h; vsync = e.frontVsync
            e.front.position(0)
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex)
            GLES20.glTexSubImage2D(GLES20.GL_TEXTURE_2D, 0, 0, 0, w, h, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, e.front)
            val p = FrameStats.produced; if (p > FrameStats.drawn + 1 && FrameStats.drawn > 0) FrameStats.glSkipped += p - FrameStats.drawn - 1
            FrameStats.drawn = p
            val now = System.nanoTime(); if (FrameStats.lastDraw > 0 && now - FrameStats.lastDraw > 25_000_000L) FrameStats.glLong++; FrameStats.lastDraw = now
        }
        val u = w / 512f; val v = h / 512f
        quad.clear(); quad.put(floatArrayOf(-1f, -1f, 0f, v, 1f, -1f, u, v, -1f, 1f, 0f, 0f, 1f, 1f, u, 0f)); quad.position(0)
        GLES20.glUseProgram(prog)
        GLES20.glUniform1i(GLES20.glGetUniformLocation(prog, "mode"), mode)
        GLES20.glUniform1f(GLES20.glGetUniformLocation(prog, "dark"), dark)
        GLES20.glUniform1f(GLES20.glGetUniformLocation(prog, "k"), (r.height() / Screen.PIC_H).toFloat())
        val p = GLES20.glGetAttribLocation(prog, "p"); val t = GLES20.glGetAttribLocation(prog, "t")
        GLES20.glEnableVertexAttribArray(p); GLES20.glEnableVertexAttribArray(t)
        quad.position(0); GLES20.glVertexAttribPointer(p, 2, GLES20.GL_FLOAT, false, 16, quad)
        quad.position(2); GLES20.glVertexAttribPointer(t, 2, GLES20.GL_FLOAT, false, 16, quad)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
    }
}
