package com.neoscan.player

import android.view.Choreographer
import java.io.File

/** Frame-pacing measurement (2026-10-04, the Redmi Pad 2 Pro stutter): which emulator frame is on screen at every
 *  display refresh. EmuThread numbers its frames ([produced]), the renderer records the one it drew ([drawn]), a
 *  Choreographer callback samples [drawn] at every vsync. Once a second: a line to files/frames.log and [line] for the
 *  on-screen overlay. Per second: emulator fps, display refreshes, how many refreshes each shown frame lasted
 *  (histogram 1/2/3/4+), frames never shown, audio underruns. */
object FrameStats : Choreographer.FrameCallback {
    @Volatile var produced = 0L                 // emulator frames finished
    @Volatile var drawn = 0L                    // the frame the renderer last uploaded
    @Volatile var underruns = 0                 // AudioTrack underrun count (cumulative)
    @Volatile var audioFill = 0                 // ms of audio queued (EmuThread's estimate)
    @Volatile var dropped = 0L                  // audio frames that didn't fit the track (cumulative)
    @Volatile var glSkipped = 0L                // frames the renderer never drew (cumulative, counted on the GL thread)
    @Volatile var runMax = 0L                   // longest runFrame this second, ns (EmuThread)
    @Volatile var runAvg = 0L                   // mean runFrame this second, ns
    @Volatile var late = 0                      // runFrames over 16.7 ms this second
    @Volatile var lastDraw = 0L; @Volatile var glLong = 0L   // GL draws more than 1.5 refreshes after the previous one (cumulative)
    @Volatile var line = ""
    var enabled = true
    @Volatile var show = false                  // settings: draw [line] over the picture
    private var log: File? = null
    private var lastShown = -1L; private var lastVsync = 0L; private var hold = 0
    private val hist = IntArray(5); private var vsyncs = 0; private var skipped = 0L
    private var t0 = 0L; private var p0 = 0L; private var u0 = 0
    private val iv = ArrayList<Long>()

    fun start(dir: File) {
        log = File(dir, "frames.log").also { it.writeText("time,emu_fps,vsyncs,hz,hold1,hold2,hold3,hold4p,skipped,underruns,audio_ms,vsync_ms_min,vsync_ms_max\n") }
        Choreographer.getInstance().postFrameCallback(this)
    }
    override fun doFrame(t: Long) {
        if (!enabled) return
        Choreographer.getInstance().postFrameCallback(this)
        if (lastVsync != 0L) iv.add(t - lastVsync)
        lastVsync = t; vsyncs++
        val d = drawn
        if (d != lastShown) {
            if (lastShown >= 0) { hist[minOf(hold, 4)]++; if (d > lastShown + 1) skipped += d - lastShown - 1 }
            lastShown = d; hold = 1
        } else hold++
        if (t0 == 0L) { t0 = t; p0 = produced; u0 = underruns }
        if (t - t0 >= 1_000_000_000L) {
            val s = (t - t0) / 1e9; val fps = (produced - p0) / s; val hz = vsyncs / s
            val mn = (iv.minOrNull() ?: 0) / 1e6; val mx = (iv.maxOrNull() ?: 0) / 1e6
            line = "emu %.1f fps | %.0f Hz | held 1:%d 2:%d 3:%d 4+:%d | skip %d | underrun %d | drop %d | audio %d ms | gl-skip %d gl-long %d | run avg %.1f max %.1f ms late %d".format(
                fps, hz, hist[1], hist[2], hist[3], hist[4], skipped, underruns - u0, dropped, audioFill, glSkipped, glLong, runAvg / 1e6, runMax / 1e6, late)
            log?.appendText("%d,%.2f,%d,%.1f,%d,%d,%d,%d,%d,%d,%d,%.2f,%.2f\n".format(System.currentTimeMillis(), fps, vsyncs, hz,
                hist[1], hist[2], hist[3], hist[4], skipped, underruns - u0, audioFill, mn, mx))
            hist.fill(0); vsyncs = 0; skipped = 0; iv.clear(); t0 = t; p0 = produced; u0 = underruns
        }
    }
}
