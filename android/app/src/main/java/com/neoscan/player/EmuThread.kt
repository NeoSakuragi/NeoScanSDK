package com.neoscan.player

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Runs the core, paced by the display (2026-10-04, the Redmi Pad 2 Pro stutter): the audio clock used to pace the
 *  loop (a blocking AudioTrack write), but devices that pull audio in big uneven chunks then ran the emulator in bursts
 *  and frames never reached the screen. Now [VsyncPacer] releases one frame per display refresh (every 2nd at 120 Hz;
 *  an accumulator at rates that aren't a multiple of ~60), audio is written without blocking, and the track's playback
 *  rate follows the emulation speed (rate * frames per second / the core's own fps), nudged by the buffer fill so the
 *  queue stays near [TARGET_MS]: a ~1% pitch change at 60 Hz, inaudible. The picture is swapped into [front] for the
 *  GL thread. */
class EmuThread(private val sysDir: String, private val saveDir: String, private val rom: String,
                private val hints: android.os.PerformanceHintManager?, val hw: String,
                private val onFrame: () -> Unit, private val onError: (String) -> Unit) : Thread("emu") {
    @Volatile var running = true
    @Volatile var paused = false                                    // app in the background / settings open
    private var back: ByteBuffer = ByteBuffer.allocateDirect(512 * 512 * 4).order(ByteOrder.nativeOrder())
    @Volatile var front: ByteBuffer = ByteBuffer.allocateDirect(512 * 512 * 4).order(ByteOrder.nativeOrder())
    @Volatile var w = 304; @Volatile var h = 224
    @Volatile var frontVsync = 0L                                   // the refresh that started the frame in [front]
    val lock = Object()
    @Volatile var fps = 0f
    @Volatile var flushed = false                                   // the saves are on disk since the last pause began

    override fun run() {
        Native.setSystem(hw, aesBios(java.io.File(sysDir, "neogeo.zip")))
        val rate = Native.load(sysDir, saveDir, rom)
        if (rate <= 0) { onError("Could not load $rom"); return }
        val min = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT)
        val track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_GAME)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(rate).setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).build())
            .setBufferSizeInBytes(maxOf(min, rate / 4 * 4))             // 250 ms of room; the queue is kept at TARGET_MS
            .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
            .setTransferMode(AudioTrack.MODE_STREAM).build()
        val audio = ShortArray(8192 * 2)
        var frames = 0; var t0 = System.nanoTime(); var written = 0L; var dropped = 0L
        var samples = 0L; var made = 0L                                 // the core's own fps = rate / samples per frame
        val target = rate * TARGET_MS / 1000
        // a streaming track only starts consuming once its buffer reaches the start threshold (by default: full), so
        // the effective size is the cap (2 x target) and playback starts at the target
        track.bufferSizeInFrames = 2 * target
        if (android.os.Build.VERSION.SDK_INT >= 31) track.setStartThresholdInFrames(target)
        var started = false; var runMax = 0L; var runSum = 0L; var late = 0
        // ADPF: report each frame's work against the 16.7 ms budget so the governor clocks the core up before a frame
        // runs late (without it the Redmi Pad 2 Pro ran this thread at ~1.4 of 2.4 GHz with 17 ms spikes)
        val hint = if (android.os.Build.VERSION.SDK_INT >= 31)
            hints?.createHintSession(intArrayOf(android.os.Process.myTid()), 16_666_667L) else null
        while (running) {
            if (paused) {
                if (!flushed) { Native.flushSaves(); flushed = true }   // Android may kill the app any time now
                if (track.playState == AudioTrack.PLAYSTATE_PLAYING) { track.pause(); track.flush(); written = 0; started = false }
                sleep(20); continue
            }
            flushed = false
            val vsync = VsyncPacer.next()                               // waits for the display (100 ms timeout)
            if (vsync < 0) continue
            val r0 = System.nanoTime()
            val n = Native.runFrame(back, audio)
            val work = System.nanoTime() - r0
            runMax = maxOf(runMax, work); runSum += work; if (work > 16_666_667L) late++
            if (android.os.Build.VERSION.SDK_INT >= 31) hint?.reportActualWorkDuration(work)
            synchronized(lock) { val t = front; front = back; back = t; w = Native.width(); h = Native.height(); frontVsync = vsync; FrameStats.produced++ }
            onFrame()
            if (n > 0) {
                samples += n; made++
                val queued = written - (track.playbackHeadPosition.toLong() and 0xFFFFFFFFL)
                // emulation speed / core fps = how fast samples arrive; the fill error trims it (at most +-0.5 %)
                val core = rate.toDouble() * made / samples
                val speed = VsyncPacer.fps / core
                val trim = ((queued - target).toDouble() / target).coerceIn(-1.0, 1.0) * 0.005
                if (made > 30) track.playbackRate = (rate * speed * (1 + trim)).toInt().coerceIn(rate * 9 / 10, rate * 11 / 10)
                // never queue more than twice the target (latency): the excess is dropped
                val room = (2 * target - queued).coerceIn(0L, n.toLong()).toInt()
                val k = if (room > 0) track.write(audio, 0, room * 2, AudioTrack.WRITE_NON_BLOCKING) else 0
                if (k > 0) written += k / 2
                if (k < n * 2) dropped += n - maxOf(k, 0) / 2
                if (!started && written >= target) { track.play(); started = true }
                FrameStats.audioFill = (queued * 1000 / rate).toInt()
            }
            frames++
            val t = System.nanoTime()
            if (t - t0 > 1_000_000_000L) { fps = frames * 1e9f / (t - t0); frames = 0; t0 = t
                FrameStats.runMax = runMax; FrameStats.runAvg = runSum / maxOf(Math.round(fps), 1); FrameStats.late = late; runMax = 0L; runSum = 0L; late = 0
                FrameStats.underruns = track.underrunCount; FrameStats.dropped = dropped
                Log.i("NeoScanPlayer", "fps %.1f rate %d (base %d core %.3f hz %.2f emu %.3f) | %s".format(fps, track.playbackRate,
                    rate, if (samples > 0) rate.toDouble() * made / samples else 0.0, VsyncPacer.hz, VsyncPacer.fps, FrameStats.line)) }
        }
        if (android.os.Build.VERSION.SDK_INT >= 31) hint?.close()
        Native.flushSaves()
        track.stop(); track.release()
    }
    companion object {
        const val TARGET_MS = 60
        /** the BIOS set has SNK's AES BIOS (neo-epo.bin) */
        fun aesBios(zip: java.io.File) = try { java.util.zip.ZipFile(zip).use { it.getEntry("neo-epo.bin") != null } } catch (e: Exception) { false }
    }
}

/** One emulator frame per display refresh: a Choreographer callback adds the elapsed refreshes' share of a frame (1 per
 *  refresh at ~60 Hz, 1/2 at ~120 Hz, otherwise core fps / Hz) and releases a permit each time it reaches a whole frame.
 *  The refresh count comes from the callbacks' timestamps (a busy UI thread skips callbacks: counting callbacks lost
 *  frames), the rate from the display ([hz], kept current by MainActivity's display listener; a mode switch takes
 *  effect a few hundred ms after it is asked for). [fps] = the resulting emulation rate. */
object VsyncPacer : android.view.Choreographer.FrameCallback {
    private const val CORE = 59.185606                             // Geolith MVS; the AES rate is close enough to pick k
    private val permits = java.util.concurrent.Semaphore(0)
    private val times = java.util.concurrent.ConcurrentLinkedQueue<Long>()
    @Volatile var fps = CORE                                        // emulation frames per second
    @Volatile var hz = 60.0                                         // the display's refresh rate
    @Volatile var perFrame = 1L                                     // refreshes per frame when the rate is a multiple (else 0)
    private var acc = 0.0; private var last = 0L; private var running = false
    /** at 2+ refreshes a frame: draw the finished frame at the refresh that starts the next one (drawn as soon as
     *  it finished, a frame ending just after a 120 Hz refresh slipped one: 25 ms then 8 ms on screen) */
    var draw: () -> Unit = {}
    fun start() { if (!running) { running = true; android.view.Choreographer.getInstance().postFrameCallback(this) } }
    override fun doFrame(t: Long) {
        android.view.Choreographer.getInstance().postFrameCallback(this)
        val k = Math.round(hz / CORE).coerceAtLeast(1)            // refreshes per frame when the rate is a multiple
        val share = if (Math.abs(hz / k - CORE) < 1.5) 1.0 / k else CORE / hz
        perFrame = if (share == 1.0 / k) k else 0L
        fps = hz * share
        val n = if (last == 0L) 1L else Math.round((t - last) * hz / 1e9).coerceIn(1L, 8L)
        last = t
        acc += share * n
        var released = false
        while (acc >= 1.0 - 1e-6) { acc -= 1.0; released = true; if (permits.availablePermits() < 2) { times.add(t); permits.release() } }
        if (released && perFrame >= 2) draw()
    }
    /** the refresh time (System.nanoTime base) that released the next frame, or -1 after 100 ms without one */
    fun next(): Long = if (permits.tryAcquire(100, java.util.concurrent.TimeUnit.MILLISECONDS)) times.poll() ?: -1L else -1L
}
