package com.neoscan.player

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Runs the core: one frame, its audio to an AudioTrack whose blocking write paces the loop at the core's own rate
 *  (~59.2 fps), the picture swapped into [front] for the GL thread. */
class EmuThread(private val sysDir: String, private val saveDir: String, private val rom: String,
                private val onFrame: () -> Unit, private val onError: (String) -> Unit) : Thread("emu") {
    @Volatile var running = true
    @Volatile var paused = false                                    // app in the background / settings open
    private var back: ByteBuffer = ByteBuffer.allocateDirect(512 * 512 * 4).order(ByteOrder.nativeOrder())
    @Volatile var front: ByteBuffer = ByteBuffer.allocateDirect(512 * 512 * 4).order(ByteOrder.nativeOrder())
    @Volatile var w = 304; @Volatile var h = 224
    val lock = Object()
    @Volatile var fps = 0f

    override fun run() {
        val rate = Native.load(sysDir, saveDir, rom)
        if (rate <= 0) { onError("Could not load $rom"); return }
        val min = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT)
        val track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_GAME)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(rate).setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).build())
            .setBufferSizeInBytes(maxOf(min, rate / 15 * 4))            // ~66 ms
            .setTransferMode(AudioTrack.MODE_STREAM).build()
        track.play()
        val audio = ShortArray(8192 * 2)
        var frames = 0; var t0 = System.nanoTime(); var written = 0L; val ts = android.media.AudioTimestamp()
        while (running) {
            if (paused) {
                if (track.playState == AudioTrack.PLAYSTATE_PLAYING) { track.pause(); track.flush() }
                sleep(20); continue
            }
            if (track.playState != AudioTrack.PLAYSTATE_PLAYING) track.play()
            val n = Native.runFrame(back, audio)
            synchronized(lock) { val t = front; front = back; back = t; w = Native.width(); h = Native.height() }
            onFrame()
            if (n > 0) { track.write(audio, 0, n * 2); written += n }    // blocks: the audio clock paces the emulation
            frames++
            val t = System.nanoTime()
            if (t - t0 > 1_000_000_000L) { fps = frames * 1e9f / (t - t0); frames = 0; t0 = t; 
                // audio latency = frames written but not yet out of the speaker, from the track's own timestamp
                val lat = if (track.getTimestamp(ts)) (written - ts.framePosition - (t - ts.nanoTime) * rate / 1e9) * 1000.0 / rate else -1.0
                Log.i("NeoScanPlayer", "fps %.1f audio %.0f ms".format(fps, lat)) }
        }
        track.stop(); track.release()
    }
}
