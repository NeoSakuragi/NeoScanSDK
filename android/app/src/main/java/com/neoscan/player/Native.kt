package com.neoscan.player

import java.nio.ByteBuffer

/** The Geolith core + JNI front end (src/main/cpp/player.c). One thread drives it: [EmuThread]. */
object Native {
    init { System.loadLibrary("neoplayer") }
    /** BIOS dir, save dir, .neo path -> audio sample rate (0 = failed) */
    @JvmStatic external fun load(systemDir: String, saveDir: String, rom: String): Int
    /** one frame: picture into [video] (XRGB8888, rows of [width]), audio frames into [audio]; returns audio frames */
    @JvmStatic external fun runFrame(video: ByteBuffer, audio: ShortArray): Int
    @JvmStatic external fun width(): Int
    @JvmStatic external fun height(): Int
    /** pad bits = libretro joypad ids: see [Pad] */
    @JvmStatic external fun setPad(port: Int, mask: Int)
    /** "mvs" (arcade: SNK's MVS BIOS) or "aes" (console: SNK's AES BIOS when [aesBios], else UniBIOS in AES mode), before [load] */
    @JvmStatic external fun setSystem(hw: String, aesBios: Boolean)
    /** write the core's NVRAM / memory card to the save dir (the core itself only does it on unload); emu thread */
    @JvmStatic external fun flushSaves()
}

/** Neo Geo pad bits as the core reads them (libretro ids; Geolith maps B->A, A->B, Y->C, X->D, SELECT->coin). */
object Pad {
    const val A = 1 shl 0; const val C = 1 shl 1; const val COIN = 1 shl 2; const val START = 1 shl 3
    const val UP = 1 shl 4; const val DOWN = 1 shl 5; const val LEFT = 1 shl 6; const val RIGHT = 1 shl 7
    const val B = 1 shl 8; const val D = 1 shl 9
}
