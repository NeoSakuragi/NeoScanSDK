package com.neoscan.player

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaRecorder
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Voice feedback (docs/feedback.md). Hold the mic button: at the press the emulation thread writes an exact replay of
 *  the last minute (the oldest kept save state, the inputs since, the state now: player.c Native.feedback) and the
 *  picture; the voice records while the button is held. Release ([stop]): the game pauses, the voice goes to
 *  <ROM base>/../feedback/transcribe and its text comes back ([transcribe], ~2 s) into an editable box (MainActivity);
 *  Send ([send]): the bundle (states, inputs.bin, screen.png, audio.m4a, meta.json with the final text) is zipped into
 *  files/feedback/queue and POSTed to ../feedback/upload (tools/feedback/server.py); a failed upload stays queued and
 *  is retried ([flush]: at start and every minute). A tap (no voice) opens the box empty: a typed note. Test hook: a file feedback_test_audio.(wav|m4a|mp3|ogg) in the app's external files dir is sent in
 *  place of the microphone (adb push; the emulator has no voice). */
class Feedback(private val ctx: Context, private val rom: File, private val emu: () -> EmuThread?) {
    private var dir: File? = null
    private var rec: MediaRecorder? = null
    private var t0 = 0L
    private var frames: LongArray? = null
    @Volatile private var captured = java.util.concurrent.CountDownLatch(0)   // the press capture is on disk

    val recording get() = dir != null

    /** button down: capture the game now, start the voice ([mic] = the permission is granted) */
    fun start(mic: Boolean, onScreen: (Bitmap) -> Unit = {}) {
        val id = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date()) + "-" + installId(ctx).take(4)
        val d = File(ctx.filesDir, "feedback/work/$id").apply { deleteRecursively(); mkdirs() }
        dir = d; t0 = android.os.SystemClock.uptimeMillis(); frames = null; txId = ""
        val latch = java.util.concurrent.CountDownLatch(1); captured = latch
        val e = emu()
        if (e != null) e.feedbackReq = d to { r, px, w, h ->
            frames = r
            Thread { try { Bitmap.createBitmap(px, w, h, Bitmap.Config.ARGB_8888).also { b ->
                onScreen(b)                                            // the scribble canvas shows it at once
                File(d, "screen.png").outputStream().use { b.compress(Bitmap.CompressFormat.PNG, 100, it) } }
            } catch (x: Exception) { Log.w(TAG, "feedback: screenshot ${x.message}") }
                latch.countDown() }.start()
        } else latch.countDown()
        if (testAudio() == null && mic) try {
            rec = (if (Build.VERSION.SDK_INT >= 31) MediaRecorder(ctx) else @Suppress("DEPRECATION") MediaRecorder()).apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4); setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioSamplingRate(16000); setAudioChannels(1); setAudioEncodingBitRate(32000)
                setMaxDuration(180_000)
                setOutputFile(File(d, "audio.m4a").absolutePath); prepare(); start()
            }
        } catch (x: Exception) { Log.w(TAG, "feedback: mic ${x.message}"); rec = null }
    }

    private var work: File? = null                                   // the bundle being written (after stop, until send / cancel)
    private var heldMs = 0L
    @Volatile private var txId = ""                                   // the server's id of this voice's transcription (its cost)

    /** button up: the voice stops; returns how long the button was held (shorter than [MIN_MS] = a tap: a text note) */
    fun stop(): Long {
        val d = dir ?: return 0; dir = null; work = d
        heldMs = android.os.SystemClock.uptimeMillis() - t0
        val r = rec; rec = null
        try { r?.stop() } catch (x: Exception) { Log.w(TAG, "feedback: mic stop ${x.message}"); File(d, "audio.m4a").delete() }
        r?.release()
        if (heldMs < MIN_MS) File(d, "audio.m4a").delete()                 // a tap: no voice
        else testAudio()?.let { it.copyTo(File(d, "audio." + it.extension), true) }
        return heldMs
    }

    /** the voice of the bundle being written, transcribed by the server at once (blocking: off the UI thread);
     *  null = no voice, or offline / the server failed */
    fun transcribe(): Pair<String, String>? {
        val a = audio() ?: return null
        val u = url(ctx, "transcribe") ?: return null
        return try {
            val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                connectTimeout = 5000; readTimeout = 60000; requestMethod = "POST"; doOutput = true
                setFixedLengthStreamingMode(a.length())
                setRequestProperty("Content-Type", "application/octet-stream"); setRequestProperty("X-Audio-Name", a.name)
                setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                outputStream.use { o -> a.inputStream().use { it.copyTo(o) } }
            } }
            if (c.responseCode != 200) { Log.w(TAG, "feedback: transcribe HTTP ${c.responseCode}"); null }
            else JSONObject(c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }).let { txId = it.optString("tx_id"); it.getString("text") to it.optString("model") }
        } catch (x: Exception) { Log.w(TAG, "feedback: transcribe ${x.message}"); null }
    }

    private fun audio(): File? = work?.listFiles()?.firstOrNull { it.name.startsWith("audio.") }

    /** Send: the final text (+ the server's transcript) goes with the bundle; zipped into the queue and sent in the
     *  background, [done] gets true = sent, false = queued (on that thread) */
    fun send(text: String, raw: String, model: String, transcribeError: Boolean, ink: List<Ink.Stroke>, done: (Boolean) -> Unit) {
        val d = work ?: return; work = null
        val latch = captured
        Thread {
            latch.await(3, java.util.concurrent.TimeUnit.SECONDS)
            val marked = ink.isNotEmpty() && try { Ink.write(d, ink) } catch (x: Exception) { Log.w(TAG, "feedback: scribble ${x.message}"); false }
            File(d, "meta.json").writeText(meta(d.name, heldMs).apply {
                put("final_text", text); put("raw_transcript", raw); put("transcript_model", model)
                put("transcribe_error", transcribeError); put("transcribe_tx", txId)
                if (marked) put("annotation", JSONObject().put("strokes", ink.size).put("scale", Ink.SCALE)
                    .put("files", org.json.JSONArray(listOf("annotation.png", "screen_marked.png"))))
                put("kind", if (d.listFiles()!!.any { it.name.startsWith("audio.") }) "voice" else "text")
            }.toString(2))
            val q = File(ctx.filesDir, "feedback/queue").apply { mkdirs() }
            val zip = File(q, d.name + ".zip"); val part = File(q, d.name + ".zip.part")
            ZipOutputStream(part.outputStream().buffered()).use { z ->
                for (f in d.listFiles()!!.sortedBy { it.name }) {
                    z.setLevel(if (f.extension in setOf("m4a", "mp3", "ogg", "png")) 0 else 6)
                    z.putNextEntry(ZipEntry(f.name)); f.inputStream().use { it.copyTo(z) }; z.closeEntry()
                }
            }
            part.renameTo(zip); d.deleteRecursively()
            done(flush(ctx) && !zip.exists())
        }.start()
    }

    /** Cancel: the bundle is dropped */
    fun cancel() { work?.deleteRecursively(); work = null }

    private fun testAudio(): File? = ctx.getExternalFilesDir(null)?.listFiles()?.firstOrNull { it.name.startsWith("feedback_test_audio.") }

    private fun meta(id: String, held: Long): JSONObject {
        val p = ctx.getPackageManager().getPackageInfo(ctx.packageName, 0)
        val fetch = ctx.getSharedPreferences("fetch", 0)
        val e = emu()
        return JSONObject().apply {
            put("id", id); put("created", iso(System.currentTimeMillis())); put("held_ms", held)
            put("app_version", p.versionName)
            put("app_code", if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else @Suppress("DEPRECATION") p.versionCode.toLong())
            put("rom_file", rom.name); put("rom_size", rom.length()); put("rom_sha256", sha(rom))
            put("rom_version", RomFetch.installed(ctx)); put("rom_build", RomFetch.installedBuild(ctx))
            put("latest_sha256", fetch.getString("sha256", ""))
            put("bios_sha256", sha(File(ctx.filesDir, "system/neogeo.zip")))
            put("hw", e?.hw ?: "?"); put("system_type", if (e != null) Native.systemType() else "?"); put("region", "us")
            put("memcard", if (e != null) Native.memcard() else "?")
            put("device", "${Build.MANUFACTURER} ${Build.MODEL}"); put("android", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            put("install_id", installId(ctx))
            frames?.let { put("window_frame", it[0]); put("press_frame", it[1]) }
            put("audio", File(ctx.filesDir, "feedback/work/$id").listFiles()?.firstOrNull { it.name.startsWith("audio.") }?.name ?: "")
        }
    }

    companion object {
        private const val TAG = "NeoScanPlayer"
        const val MIN_MS = 400L                                      // shorter = a stray touch: cancelled

        fun installId(ctx: Context): String {
            val p = ctx.getSharedPreferences("fetch", 0)
            return p.getString("install", null) ?: java.util.UUID.randomUUID().toString().also { p.edit().putString("install", it).apply() }
        }

        /** the upload URL: <ROM base>/../feedback/upload (canneji.duckdns.org/brawler/feedback/upload) */
        fun url(ctx: Context, what: String = "upload"): URL? = RomFetch.base(ctx)?.let { URL(URL(it), "../feedback/$what") }

        /** send every queued bundle (blocking; off the UI thread); true when the queue is empty afterwards */
        @Synchronized fun flush(ctx: Context): Boolean {
            val q = File(ctx.filesDir, "feedback/queue")
            // 0.0.15: the bundles an older player had queued and the server refused once it needed the login (401) go again
            val fp = ctx.getSharedPreferences("feedback", 0)
            if (!fp.getBoolean("requeued015", false)) {
                q.listFiles { f -> f.name.endsWith(".zip.rejected") }?.forEach { it.renameTo(File(it.path.removeSuffix(".rejected"))) }
                fp.edit().putBoolean("requeued015", true).apply()
            }
            val zips = q.listFiles { f -> f.name.endsWith(".zip") }?.sortedBy { it.name } ?: return true
            val u = url(ctx) ?: return zips.isEmpty()
            for (z in zips) try {
                val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 5000; readTimeout = 30000; requestMethod = "POST"; doOutput = true
                    setFixedLengthStreamingMode(z.length())
                    setRequestProperty("Content-Type", "application/zip"); setRequestProperty("X-Bundle", z.nameWithoutExtension)
                    setRequestProperty("X-Install-Id", installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                    setRequestProperty("X-Device", "${Build.MANUFACTURER} ${Build.MODEL}")
                    if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                    outputStream.use { o -> z.inputStream().use { it.copyTo(o) } }
                } }
                val code = c.responseCode
                if (code == 200) { Log.i(TAG, "feedback: ${z.name} sent: " + c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }); z.delete() }
                else if (code == 401) { Log.w(TAG, "feedback: ${z.name}: not signed in, kept queued"); return false }
                else { Log.w(TAG, "feedback: ${z.name}: HTTP $code"); if (code in 400..499 && code != 408 && code != 429) z.renameTo(File(z.path + ".rejected")); return false }
            } catch (x: Exception) { Log.w(TAG, "feedback: ${z.name} queued (${x.message})"); return false }
            return true
        }

        /** sha256 of a file, cached by (path, size, mtime) */
        private val shas = HashMap<String, String>()
        fun sha(f: File): String {
            if (!f.exists()) return ""
            val k = "${f.path}:${f.length()}:${f.lastModified()}"
            return synchronized(shas) { shas[k] } ?: MessageDigest.getInstance("SHA-256").let { md ->
                f.inputStream().use { i -> val b = ByteArray(1 shl 16); while (true) { val n = i.read(b); if (n < 0) break; md.update(b, 0, n) } }
                md.digest().joinToString("") { "%02x".format(it) }
            }.also { synchronized(shas) { shas[k] = it } }
        }

        private fun iso(t: Long) = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date(t))
    }
}
