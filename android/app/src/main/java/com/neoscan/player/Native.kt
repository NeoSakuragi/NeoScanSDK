package com.neoscan.player

import java.nio.ByteBuffer

/** The Geolith core + JNI front end (src/main/cpp/player.c). One thread drives it: [EmuThread] (one per process). */
object Native {
    init { System.loadLibrary("neoplayer") }
    /** BIOS dir, save dir, .neo path -> audio sample rate (0 = failed, or refused: the core is live on another
     *  thread, TODO #183); the calling thread owns the core until [unload] */
    @JvmStatic external fun load(systemDir: String, saveDir: String, rom: String): Int
    /** the core's owner thread lets it go (saves written, retro_unload_game + retro_deinit); a no-op elsewhere */
    @JvmStatic external fun unload()
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
    /** soft reset (the core's retro_reset: the BIOS boots the cart again, NVRAM / memory card kept); emu thread */
    @JvmStatic external fun reset()
    /** the Character Lab: the character pack at [path] (tools/brawler/lab_pack.py) into the loaded shell, then a reset
     *  (the shell boots into the practice with that fighter); emu thread, between frames; 0 = swapped, < 0 refused
     *  (pack_swap.h NGPK_*: e.g. -4 a pack for another shell), the ROM unchanged. Called by [CharacterLab]. */
    @JvmStatic external fun swapPack(path: String): Int
    /** the 68000 work RAM ($100000-$10FFFF, bytes in the 68000's order, as chainlab/lab.js sees it): [n] bytes at [addr];
     *  null outside it or off the core's thread. Emu thread, between frames (Player 0.0.28, the Character lab) */
    @JvmStatic external fun ramRead(addr: Int, n: Int): ByteArray?
    /** [data] written at the 68000 address [addr]; false outside the RAM or off the core's thread. Emu thread, between frames */
    @JvmStatic external fun ramWrite(addr: Int, data: ByteArray): Boolean
    /** feedback capture into [dir] (press.state, snap_<frame>.state, inputs.bin: see player.c); emu thread, between
     *  frames; returns {window start frame, press frame} or null */
    @JvmStatic external fun feedback(dir: String): LongArray?
    /** a test scenario's save state in place of the game (0.0.22); emu thread, between frames; 0 = loaded, 1 unreadable,
     *  2 another core build (size), 3 refused */
    @JvmStatic external fun loadState(path: String): Int
    /** the last frame's picture as opaque ARGB, rows of [width]; returns the pixels written */
    @JvmStatic external fun screenshot(out: IntArray): Int
    /** the BIOS the core boots: mvs / aes / uni */
    @JvmStatic external fun systemType(): String
    /** the memory card: "on" (AES) / "off" (MVS: no card, TODO #156) */
    @JvmStatic external fun memcard(): String
}

/** Neo Geo pad bits as the core reads them (libretro ids; Geolith maps B->A, A->B, Y->C, X->D, SELECT->coin). */
object Pad {
    const val A = 1 shl 0; const val C = 1 shl 1; const val COIN = 1 shl 2; const val START = 1 shl 3
    const val UP = 1 shl 4; const val DOWN = 1 shl 5; const val LEFT = 1 shl 6; const val RIGHT = 1 shl 7
    const val B = 1 shl 8; const val D = 1 shl 9
}
