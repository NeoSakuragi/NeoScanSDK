package com.neoscan.player

import android.content.Context
import android.os.Build
import android.os.SystemClock
import android.util.Log
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.LinkedBlockingDeque
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPOutputStream

/** SESSION RECORDING (Player 0.0.41, docs/feedback.md "Session recording"; both apps): while the game runs, every ~5 s a
 *  CHUNK of the play session goes to the feedback service (POST sessions/chunk), so the developers can replay a tester's
 *  whole session, or watch it live, in the Lab's Sessions tab (chainlab/sessions.js).
 *  - A chunk (player.c Native.sessionChunk) = the save state at its start + the pads of its ~300 frames, the same pads as
 *    inputs.bin (NSIN v1, bit 15 of port 0 = a soft reset before that frame). The state goes gzip'd (~1/7 of its size).
 *  - A session = one install + its start time ("<install 8>-<yyyyMMdd-HHmmss>"); a new one starts after a pause of more
 *    than [GAP_MS] (the next chunk comes later than that), another ROM / system (another EmuThread) or a new process.
 *  - Only the game build (RomFetch.romFile: brawler.neo), signed in; never the Character lab's shell.
 *  - Never stalls the emulation: the emulation thread only copies the chunk out of the core (JNI); the gzip runs on one
 *    worker with a bounded queue, the uploads on another (bounded too, the oldest dropped when full); offline = retried
 *    with a growing wait, a refused chunk (4xx) dropped. Memory only: nothing is kept across a restart.
 *  Wire format (the POST body, little endian): "NSCK", u32 1, u32 n + n bytes of JSON meta, u32 n + inputs (NSIN v1:
 *  "NSIN", u32 1, u64 W, u64 P, (P - W) x (u16 port0, u16 port1)), u32 n + the gzip'd state (n = 0: no state). */
object Session {
    private const val TAG = "NeoScanPlayer"
    const val GAP_MS = 60_000L                                      // a pause longer than this ends the session
    private const val MAX_QUEUE = 240                               // chunks waiting for the network (~20 min, ~8 MB)
    @Volatile private var app: Context? = null
    fun init(ctx: Context) { app = ctx.applicationContext; sender }

    private class Chunk(val session: String, val seq: Int, val body: ByteArray)
    private val outbox = LinkedBlockingDeque<Chunk>()
    private val packer = ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS, ArrayBlockingQueue(6), ThreadPoolExecutor.DiscardOldestPolicy())

    // the session in progress (emulation thread only)
    private var owner: EmuThread? = null
    private var sid: String? = null
    private var seq = 0
    private var last = 0L
    private var started = 0L
    @Volatile var sent = 0L; @Volatile var dropped = 0L; @Volatile var bytes = 0L   // counters (the log)

    /** the emulation thread, before every frame (mode 1) and while paused (mode 2: the chunk so far is closed) */
    fun tick(e: EmuThread, mode: Int) {
        val ctx = app
        val want = ctx != null && Auth.user(ctx) != null && e.rom == RomFetch.romFile(ctx).absolutePath
        val raw = Native.sessionChunk(if (want) mode else 0) ?: return
        val now = SystemClock.elapsedRealtime()
        if (owner !== e || sid == null || now - last > GAP_MS) {
            owner = e; seq = 0; started = System.currentTimeMillis()
            sid = Feedback.installId(ctx!!).replace("-", "").take(8) + "-" +
                java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date(started))
            Log.i(TAG, "session: $sid starts")
        }
        last = now
        val s = sid!!; val n = seq++; val t0 = started; val hw = e.hw; val rom = File(e.rom); val paused = mode == 2
        packer.execute { try { pack(ctx!!, s, n, t0, hw, rom, raw, paused) } catch (x: Exception) { Log.w(TAG, "session: pack ${x.message}") } }
    }

    private fun pack(ctx: Context, s: String, n: Int, t0: Long, hw: String, rom: File, raw: ByteArray, paused: Boolean) {
        val b = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN)
        val start = b.getLong(0); val frames = b.getInt(8); val ss = b.getInt(12)
        val inputs = ByteBuffer.allocate(24 + frames * 4).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("NSIN".toByteArray()); putInt(1); putLong(start); putLong(start + frames); put(raw, 16, frames * 4) }.array()
        val st = ByteArrayOutputStream(ss / 4)
        GZIPOutputStream(st, 1 shl 16).use { it.write(raw, 16 + frames * 4, ss) }
        val gz = st.toByteArray()
        val sha = MessageDigest.getInstance("SHA-256").apply { update(raw, 16 + frames * 4, ss) }.digest().joinToString("") { "%02x".format(it) }
        val p = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
        val meta = JSONObject().apply {
            put("session", s); put("seq", n); put("start_frame", start); put("frames", frames); put("paused", paused)
            put("state", "gzip"); put("state_size", ss); put("state_sha256", sha)
            put("started", t0); put("sent", System.currentTimeMillis())
            put("rom_sha256", Feedback.sha(rom)); put("rom_version", RomFetch.installed(ctx)); put("rom_build", RomFetch.loadedBuild(ctx))
            put("system", Native.systemType() + "-" + hw); put("hw", hw); put("system_type", Native.systemType()); put("memcard", if (hw == "aes") "on" else "off")
            put("region", "us"); put("app", if (BuildConfig.DEV) "dev" else "brawler"); put("app_version", p.versionName)
            put("app_code", if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else @Suppress("DEPRECATION") p.versionCode.toLong())
            put("device", "${Build.MANUFACTURER} ${Build.MODEL}"); put("android", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            put("install_id", Feedback.installId(ctx)); put("user", Auth.user(ctx) ?: "")
        }.toString().toByteArray()
        val body = ByteBuffer.allocate(12 + meta.size + 4 + inputs.size + 4 + gz.size).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("NSCK".toByteArray()); putInt(1); putInt(meta.size); put(meta); putInt(inputs.size); put(inputs); putInt(gz.size); put(gz) }.array()
        while (outbox.size >= MAX_QUEUE) { outbox.pollFirst(); dropped++ }
        outbox.offerLast(Chunk(s, n, body))
    }

    private val sender: Thread by lazy { Thread({ sendLoop() }, "session-send").apply { isDaemon = true; priority = Thread.MIN_PRIORITY; start() } }

    private fun sendLoop() {
        var wait = 5_000L
        while (true) {
            val c = try { outbox.takeFirst() } catch (x: InterruptedException) { return }
            val ctx = app ?: continue
            val code = post(ctx, c)
            when {
                code == 200 -> { sent++; bytes += c.body.size; wait = 5_000L
                    if (c.seq % 60 == 0) Log.i(TAG, "session: ${c.session} chunk ${c.seq} sent (${c.body.size} bytes; $sent sent, $dropped dropped, ${bytes / 1024} KB)") }
                code in 400..499 && code != 401 && code != 408 && code != 429 -> { dropped++; Log.w(TAG, "session: ${c.session} chunk ${c.seq} refused (HTTP $code), dropped") }
                else -> {                                           // offline / the server down / not signed in yet: later
                    outbox.offerFirst(c)
                    try { Thread.sleep(wait) } catch (x: InterruptedException) { return }
                    wait = minOf(wait * 2, 120_000L)
                }
            }
        }
    }

    private fun post(ctx: Context, c: Chunk): Int = try {
        val u = URL(Auth.feedbackUrl("sessions/chunk"))
        val h = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000; readTimeout = 20000; requestMethod = "POST"; doOutput = true
            setFixedLengthStreamingMode(c.body.size); setRequestProperty("Content-Type", "application/octet-stream")
            setRequestProperty("X-Install-Id", Feedback.installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
            outputStream.use { it.write(c.body) }
        } }
        val code = h.responseCode
        (if (code in 200..299) h.inputStream else h.errorStream)?.use { it.readBytes() }
        code
    } catch (x: Exception) { -1 }
}
